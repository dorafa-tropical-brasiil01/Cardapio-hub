"""
Nível 3 — IMPLEMENTAÇÃO CONCRETA: PagBankAdapter (PIX via API Order).

Implementa PaymentProviderAdapter para o PagBank usando a API Order (REST).

6 gaps da Auditoria B tratados aqui:
    Gap 1: GET /orders/{id} pode retornar 404 para pedidos não pagos → tratar como PENDING
    Gap 2: Sem endpoint explícito para cancelar QR Code pendente → retornar False
    Gap 3: Webhook não fornece event_id explícito → sintetizar via SHA-256(payload)
    Gap 4: Amount em centavos → converter reais*100 na ida, centavos/100 na volta
    Gap 5: QR Code base64 e image_url em URLs separadas → extrair ambos
    Gap 6: IN_ANALYSIS e AUTHORIZED → normalizar para PENDING

Credenciais (Decisão 6):
    - token: Bearer token para API Order (variável de ambiente ou arquivo local)
    - webhook_token: token da conta para validar assinatura do webhook
    - O adapter recebe as credenciais no construtor; não lê de env diretamente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .adapter_contract import (
    CreatePaymentRequest,
    CreatePaymentResult,
    PaymentEvent,
    PaymentMethod,
    PaymentProviderAdapter,
    PaymentStatusResult,
    ProviderPaymentStatus,
    QRCodeData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

PROVIDER_ID = "PAGBANK"

# Endpoints base
SANDBOX_BASE_URL = "https://sandbox.api.pagseguro.com"
PRODUCTION_BASE_URL = "https://api.pagseguro.com"


# ---------------------------------------------------------------------------
# Normalização de status do PagBank → ProviderPaymentStatus
#
# Gap 6: IN_ANALYSIS e AUTHORIZED → PENDING
# ---------------------------------------------------------------------------

_PAGBANK_STATUS_MAP: dict[str, ProviderPaymentStatus] = {
    "WAITING": ProviderPaymentStatus.PENDING,        # Aguardando pagamento
    "IN_ANALYSIS": ProviderPaymentStatus.PENDING,    # Em análise → PENDING (Gap 6)
    "AUTHORIZED": ProviderPaymentStatus.PENDING,     # Autorizado mas não capturado → PENDING (Gap 6)
    "PAID": ProviderPaymentStatus.APPROVED,          # Pago
    "DECLINED": ProviderPaymentStatus.DECLINED,      # Recusado
    "CANCELED": ProviderPaymentStatus.CANCELLED,     # Cancelado
    "EXPIRED": ProviderPaymentStatus.EXPIRED,        # Expirado
}


def _normalize_pagbank_status(raw_status: str | None) -> ProviderPaymentStatus:
    if raw_status is None:
        return ProviderPaymentStatus.PENDING
    return _PAGBANK_STATUS_MAP.get(
        str(raw_status).strip().upper(),
        ProviderPaymentStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# Conversão monetária (Gap 4)
# ---------------------------------------------------------------------------

def _reais_to_centavos(reais: float) -> int:
    """Converte reais para centavos (inteiro). PagBank espera centavos."""
    return int(round(reais * 100))


def _centavos_to_reais(centavos: int | float | None) -> float | None:
    """Converte centavos para reais."""
    if centavos is None:
        return None
    return float(centavos) / 100.0


# ---------------------------------------------------------------------------
# PagBankAdapter
# ---------------------------------------------------------------------------

class PagBankAdapter(PaymentProviderAdapter):
    """Adapter concreto para o PagBank (API Order — PIX).

    Credenciais são injetadas no construtor (Decisão 6).
    Não lê variáveis de ambiente diretamente — facilita testes com mocks.
    """

    def __init__(
        self,
        *,
        token: str,
        webhook_token: str | None = None,
        webhook_url: str | None = None,
        sandbox: bool = True,
        base_url: str | None = None,
    ) -> None:
        """
        Args:
            token: Bearer token para autenticar na API Order.
            webhook_token: Token da conta para validar assinatura do webhook (SHA-256).
            webhook_url: URL base para onde o PagBank envia notificacoes de pagamento.
                Se informado, e incluido em notification_urls no POST /orders.
            sandbox: True para sandbox, False para produção.
            base_url: URL base override (se None, usa sandbox/produção conforme flag).
        """
        self._token = token
        self._webhook_token = webhook_token
        self._webhook_url = webhook_url.rstrip("/") if webhook_url else None
        self._base_url = (
            base_url.rstrip("/")
            if base_url
            else (SANDBOX_BASE_URL if sandbox else PRODUCTION_BASE_URL)
        )

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _request(
        self,
        *,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DoRafaPDV/2.0",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            logger.warning(
                "PagBank API HTTPError %s url=%s body=%s",
                e.code, url, raw[:500] if raw else b"",
            )
            raise
        except Exception as e:
            logger.error("PagBank API error url=%s err=%s", url, e)
            raise

    # ------------------------------------------------------------------
    # create_payment — POST /orders com qr_codes (PIX)
    # ------------------------------------------------------------------

    def create_payment(self, request: CreatePaymentRequest) -> CreatePaymentResult:
        """Cria uma cobrança PIX via POST /orders com qr_codes.

        PagBank API Order:
            POST /orders
            Body: {
                "reference_id": "...",
                "customer": {name, email, tax_id},  # obrigatorio
                "items": [...],
                "qr_codes": [{
                    "amount": { "value": <centavos> },
                    "expiration_date": "2026-08-13T15:00:00-03:00",
                }],
                "notification_urls": [...],  # opcional
            }
            Response: {
                "id": "ORDE_...",
                "qr_codes": [{
                    "id": "qrcode_...",
                    "text": "00020126...",
                    "links": [{"href": "...", "media": "image/png", "type": "IMAGE"}],
                    "amount": { "value": <centavos> },
                    "expiration_date": "2026-08-13T15:00:00-03:00",
                }],
                "status": "WAITING",
                ...
            }
        """
        # Gap 4: converter reais para centavos
        amount_centavos = _reais_to_centavos(request.amount)

        # Expiration date em ISO 8601
        expiration_date_iso = None
        if request.expires_in_seconds is not None and request.expires_in_seconds > 0:
            from datetime import timedelta
            exp = datetime.now(timezone.utc) + timedelta(seconds=request.expires_in_seconds)
            expiration_date_iso = exp.strftime("%Y-%m-%dT%H:%M:%S-03:00")

        body: dict[str, Any] = {
            "reference_id": request.reference_id,
            "customer": {
                "name": "Cliente PDV",
                "email": "pdv@dorafatropicalbrasil.com.br",
                "tax_id": "12345678909",
            },
            "items": [
                {
                    "name": request.description or "Pagamento",
                    "quantity": 1,
                    "unit_amount": amount_centavos,
                }
            ],
            "qr_codes": [
                {
                    "amount": {"value": amount_centavos},
                }
            ],
        }

        if expiration_date_iso:
            body["qr_codes"][0]["expiration_date"] = expiration_date_iso

        # notification_urls: URL para onde o PagBank envia o webhook de pagamento.
        # Sem isso, o PagBank nao notifica — o pagamento fica invisivel ao sistema.
        if self._webhook_url:
            body["notification_urls"] = [self._webhook_url]

        logger.info(
            "create_payment - reference=%s amount_centavos=%s expires=%s",
            request.reference_id, amount_centavos, expiration_date_iso,
        )

        resp = self._request(method="POST", path="/orders", body=body)

        order_id = str(resp.get("id") or "")
        if not order_id:
            raise RuntimeError("PagBank não retornou Order ID")

        # Extrair QR Code (Gap 5: base64 e image_url em URLs separadas)
        qr_code: QRCodeData | None = None
        qr_codes_list = resp.get("qr_codes") or []
        if qr_codes_list and isinstance(qr_codes_list, list):
            qr = qr_codes_list[0]
            payload_text = str(qr.get("text") or "")
            image_url = None
            image_base64 = None

            # Gap 5: links pode conter URLs para imagem
            links = qr.get("links") or []
            if isinstance(links, list):
                for link in links:
                    if isinstance(link, dict):
                        media = str(link.get("media") or "").upper()
                        if "IMAGE" in media or "PNG" in media:
                            image_url = str(link.get("href") or "") or None
                            break

            if payload_text:
                qr_code = QRCodeData(
                    payload=payload_text,
                    image_base64=image_base64,
                    image_url=image_url,
                )

        # Extrair expiration_date
        expires_at: datetime
        raw_expires = None
        if qr_codes_list and isinstance(qr_codes_list, list):
            raw_expires = qr_codes_list[0].get("expiration_date")
        if raw_expires:
            try:
                expires_at = datetime.fromisoformat(str(raw_expires))
            except ValueError:
                expires_at = datetime.now(timezone.utc)
        else:
            # Fallback: se o PSP não fornecer, usar agora + 24h
            from datetime import timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        # Status inicial (tipicamente WAITING → PENDING)
        raw_status = resp.get("status")
        status = _normalize_pagbank_status(raw_status)

        logger.info(
            "create_payment - success order_id=%s status=%s expires_at=%s",
            order_id, status.value, expires_at.isoformat(),
        )

        return CreatePaymentResult(
            provider_transaction_id=order_id,
            status=status,
            qr_code=qr_code,
            expires_at=expires_at,
        )

    # ------------------------------------------------------------------
    # get_payment_status — GET /orders/{id}
    # Gap 1: 404 para pedidos não pagos → tratar como PENDING
    # ------------------------------------------------------------------

    def get_payment_status(self, provider_transaction_id: str) -> PaymentStatusResult:
        """Consulta o status de uma Order no PagBank.

        Gap 1: GET /orders/{id} pode retornar resource_not_found (404)
        para pedidos não pagos. O adapter trata 404 como PENDING.
        """
        try:
            resp = self._request(
                method="GET",
                path=f"/orders/{provider_transaction_id}",
            )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Gap 1: 404 → PENDING (pedido pode existir mas não foi pago ainda)
                logger.info(
                    "get_payment_status - 404 tratado como PENDING order_id=%s",
                    provider_transaction_id,
                )
                return PaymentStatusResult(
                    provider_transaction_id=provider_transaction_id,
                    status=ProviderPaymentStatus.PENDING,
                )
            raise

        raw_status = resp.get("status")
        status = _normalize_pagbank_status(raw_status)

        # Extrair amount confirmado (se disponível)
        amount = None
        charges = resp.get("charges") or []
        if charges and isinstance(charges, list):
            charge = charges[0]
            amount_cents = charge.get("amount", {}).get("value")
            if amount_cents is not None:
                amount = _centavos_to_reais(int(amount_cents))

        # Se não há charges, tentar qr_codes
        if amount is None:
            qr_codes = resp.get("qr_codes") or []
            if qr_codes and isinstance(qr_codes, list):
                amount_cents = (qr_codes[0].get("amount") or {}).get("value")
                if amount_cents is not None:
                    amount = _centavos_to_reais(int(amount_cents))

        return PaymentStatusResult(
            provider_transaction_id=provider_transaction_id,
            status=status,
            amount=amount,
        )

    # ------------------------------------------------------------------
    # cancel_payment — Gap 2: sem endpoint para cancelar QR Code pendente
    # ------------------------------------------------------------------

    def cancel_payment(self, provider_transaction_id: str) -> bool:
        """Cancela uma cobrança no PagBank.

        Gap 2: o PagBank não tem endpoint explícito para cancelar QR Code
        PIX pendente. O adapter retorna False e aguarda expiração natural.

        Para charges (cartão), pode existir POST /charges/{id}/cancel,
        mas isto será implementado na Fase 2A (cartão).
        """
        logger.info(
            "cancel_payment - QR Code pendente não pode ser cancelado (Gap 2) order_id=%s",
            provider_transaction_id,
        )
        return False

    # ------------------------------------------------------------------
    # validate_webhook — Gap 3: sintetizar event_id via SHA-256(payload)
    # ------------------------------------------------------------------

    def validate_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
    ) -> PaymentEvent | None:
        """Valida e traduz um webhook do PagBank.

        Validação de assinatura (Auditoria B):
            PagBank envia header x-authenticity-token = SHA-256(token + "-" + body)
            O adapter recalcula e compara.

        Gap 3: o PagBank não fornece event_id explícito no webhook.
            O adapter sintetiza via SHA-256(body bruto).

        Formato do webhook do PagBank (API Order):
            {
                "id": "ORDE_...",        # Order ID
                "status": "PAID",        # Status do pedido
                "charges": [...],        # Charges (se houver)
                ...
            }
        """
        # Validar assinatura
        if self._webhook_token:
            signature = headers.get("x-authenticity-token") or ""
            expected = hashlib.sha256(
                f"{self._webhook_token}-{body.decode('utf-8', errors='replace')}".encode("utf-8")
            ).hexdigest()
            if not _safe_str_eq(signature, expected):
                logger.warning("validate_webhook - assinatura inválida")
                return None

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            logger.warning("validate_webhook - body não é JSON válido")
            return None

        if not isinstance(payload, dict):
            return None

        # Extrair provider_transaction_id (Order ID)
        order_id = str(payload.get("id") or "")
        if not order_id:
            logger.warning("validate_webhook - webhook sem Order ID")
            return None

        # Extrair e normalizar status
        raw_status = payload.get("status")
        status = _normalize_pagbank_status(raw_status)

        # Extrair amount (se disponível)
        amount = None
        charges = payload.get("charges") or []
        if charges and isinstance(charges, list):
            charge = charges[0]
            amount_cents = (charge.get("amount") or {}).get("value")
            if amount_cents is not None:
                amount = _centavos_to_reais(int(amount_cents))

        # Extrair reference_id (defesa em profundidade — Bloco 3.5)
        reference_id = str(payload.get("reference_id") or "").strip() or None

        # PagBank API Order opera em BRL; o webhook não envia currency explicitamente.
        currency = "BRL"

        # Gap 3: sintetizar event_id via SHA-256(body bruto)
        event_id = hashlib.sha256(body).hexdigest()

        # Extrair occurred_at (se disponível)
        occurred_at = None
        raw_created = payload.get("created_at")
        if raw_created:
            try:
                occurred_at = datetime.fromisoformat(str(raw_created))
            except ValueError:
                pass

        logger.info(
            "validate_webhook - success order_id=%s status=%s event_id=%s reference=%s",
            order_id, status.value, event_id[:16], reference_id,
        )

        return PaymentEvent(
            provider_transaction_id=order_id,
            status=status,
            amount=amount,
            event_id=event_id,
            occurred_at=occurred_at,
            raw_payload=body.decode("utf-8", errors="replace"),
            reference_id=reference_id,
            currency=currency,
        )


# ---------------------------------------------------------------------------
# Helper: comparação segura de strings (evita timing attack)
# ---------------------------------------------------------------------------

def _safe_str_eq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
