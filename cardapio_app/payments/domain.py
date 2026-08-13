"""
Nível 1 — DOMÍNIO DE PAGAMENTOS (PaymentService).

O PaymentService opera sobre external_payments e PaymentEvent canônico.
Não conhece PSP, método específico, canal ou mecanismo de integração.

Regras canônicas (Contrato 0D):
    - Estados: PENDENTE, APROVADO, RECUSADO, EXPIRADO, CANCELADO
    - Transições:
        PENDENTE → APROVADO (pagamento confirmado)
        PENDENTE → EXPIRADO (expiração local: expires_at < NOW())
        PENDENTE → RECUSADO (PSP recusou)
        PENDENTE → CANCELADO (cancelamento solicitado)
        EXPIRADO → APROVADO (PIX pago após expiração — permitido)
    - Estados terminais: APROVADO, RECUSADO, CANCELADO
    - Não-regressão: estados terminais não podem ser sobrescritos
      (exceção: EXPIRADO → APROVADO)
    - Idempotência: last_event_id evita processar o mesmo evento duas vezes
    - claim: PDV reivindica um pagamento aprovado
    - application: PDV aplica o pagamento a uma venda
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .adapter_contract import (
    CreatePaymentRequest,
    CreatePaymentResult,
    PaymentEvent,
    PaymentMethod,
    PaymentProviderAdapter,
    PaymentStatusResult,
    ProviderPaymentStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status canônico do domínio (external_payments.status)
# ---------------------------------------------------------------------------

class PaymentStatus(str, Enum):
    PENDENTE = "PENDENTE"
    APROVADO = "APROVADO"
    RECUSADO = "RECUSADO"
    EXPIRADO = "EXPIRADO"
    CANCELADO = "CANCELADO"


# Estados terminais — não podem ser sobrescritos (com exceção EXPIRADO → APROVADO)
_TERMINAL_STATES = {PaymentStatus.APROVADO, PaymentStatus.RECUSADO, PaymentStatus.CANCELADO}


# ---------------------------------------------------------------------------
# Mapeamento: ProviderPaymentStatus → PaymentStatus
# ---------------------------------------------------------------------------

_PROVIDER_TO_DOMAIN = {
    ProviderPaymentStatus.PENDING: PaymentStatus.PENDENTE,
    ProviderPaymentStatus.APPROVED: PaymentStatus.APROVADO,
    ProviderPaymentStatus.DECLINED: PaymentStatus.RECUSADO,
    ProviderPaymentStatus.CANCELLED: PaymentStatus.CANCELADO,
    ProviderPaymentStatus.EXPIRED: PaymentStatus.EXPIRADO,
    ProviderPaymentStatus.ERROR: PaymentStatus.RECUSADO,
}


def _normalize_status(provider_status: ProviderPaymentStatus) -> PaymentStatus:
    return _PROVIDER_TO_DOMAIN.get(provider_status, PaymentStatus.PENDENTE)


# ---------------------------------------------------------------------------
# ExternalPayment — representação em memória de um registro de external_payments
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExternalPayment:
    id: str
    provider_id: str
    provider_transaction_id: str
    payment_method: str
    amount: float
    status: PaymentStatus
    reference_id: str | None = None
    qr_code_payload: str | None = None
    qr_code_image_base64: str | None = None
    qr_code_image_url: str | None = None
    expires_at: datetime | None = None
    last_event_id: str | None = None
    claimed_by_pdv_id: str | None = None
    applied_sale_id: int | None = None
    applied_sale_payment_id: int | None = None


# ---------------------------------------------------------------------------
# PaymentService — domínio
# ---------------------------------------------------------------------------

class PaymentService:
    """Serviço de domínio para pagamentos externos.

    Opera sobre external_payments (via pg_store no Cardápio).
    Não conhece PSP, método específico, canal ou mecanismo.
    """

    def __init__(self, *, store: Any, adapter: PaymentProviderAdapter) -> None:
        """
        Args:
            store: módulo pg_store (ou mock) com funções CRUD de external_payments.
            adapter: PaymentProviderAdapter concreto (PagBankAdapter, etc.).
        """
        self._store = store
        self._adapter = adapter

    # ------------------------------------------------------------------
    # Criação de cobrança
    # ------------------------------------------------------------------

    def iniciar_pagamento(
        self,
        *,
        payment_method: PaymentMethod,
        amount: float,
        reference_id: str | None = None,
        description: str | None = None,
        expires_in_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Cria uma cobrança no PSP e registra em external_payments.

        Fluxo:
            1. Gera external_payment_id (UUID)
            2. Chama adapter.create_payment()
            3. Registra em external_payments com status=PENDENTE
            4. Retorna o registro (com QR Code se aplicável)

        Retorna um dict com os dados do pagamento criado.
        """
        payment_id = str(uuid.uuid4())

        request = CreatePaymentRequest(
            amount=amount,
            payment_method=payment_method,
            reference_id=reference_id or payment_id,
            description=description,
            expires_in_seconds=expires_in_seconds,
        )

        logger.info(
            "iniciar_pagamento - payment_id=%s method=%s amount=%s reference=%s",
            payment_id, payment_method.value, amount, reference_id,
        )

        result: CreatePaymentResult = self._adapter.create_payment(request)

        qr_payload = None
        qr_image_b64 = None
        qr_image_url = None
        if result.qr_code is not None:
            qr_payload = result.qr_code.payload
            qr_image_b64 = result.qr_code.image_base64
            qr_image_url = result.qr_code.image_url

        expires_at_iso = result.expires_at.isoformat() if result.expires_at else None

        record = self._store.create_external_payment(
            payment_id=payment_id,
            provider_id=self._adapter.provider_id,
            provider_transaction_id=result.provider_transaction_id,
            payment_method=payment_method.value,
            amount=amount,
            reference_id=reference_id or payment_id,
            qr_code_payload=qr_payload,
            qr_code_image_base64=qr_image_b64,
            qr_code_image_url=qr_image_url,
            expires_at=expires_at_iso,
            metadata={"description": description} if description else None,
        )

        logger.info(
            "iniciar_pagamento - success payment_id=%s provider_tx=%s expires_at=%s",
            payment_id, result.provider_transaction_id, expires_at_iso,
        )

        return record

    # ------------------------------------------------------------------
    # Processamento de webhook
    # ------------------------------------------------------------------

    def processar_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> dict[str, Any] | None:
        """Processa um webhook recebido do PSP.

        Fluxo:
            1. adapter.validate_webhook() → PaymentEvent (ou None se inválido)
            2. Busca external_payment por provider_transaction_id
            3. Verifica idempotência (last_event_id)
            4. Verifica não-regressão (estados terminais)
            5. Atualiza status
            6. Retorna o registro atualizado

        Retorna None se o webhook for inválido ou o pagamento não for encontrado.
        """
        event: PaymentEvent | None = self._adapter.validate_webhook(headers, body)
        if event is None:
            logger.warning("processar_webhook - webhook inválido (validação falhou)")
            return None

        record = self._store.get_external_payment_by_provider_tx(
            provider_id=self._adapter.provider_id,
            provider_transaction_id=event.provider_transaction_id,
        )
        if record is None:
            logger.warning(
                "processar_webhook - pagamento não encontrado provider_tx=%s",
                event.provider_transaction_id,
            )
            return None

        # Idempotência: se last_event_id == event.event_id, já processado
        current_last_event_id = record.get("last_event_id")
        if current_last_event_id is not None and current_last_event_id == event.event_id:
            logger.info(
                "processar_webhook - evento duplicado event_id=%s (ignorado)",
                event.event_id,
            )
            return record

        # Normalizar status
        new_status = _normalize_status(event.status)
        current_status_str = str(record.get("status") or "").upper()

        # Não-regressão de estados terminais
        # Exceção: EXPIRADO → APROVADO é permitido (PIX pago após expiração)
        try:
            current_status = PaymentStatus(current_status_str)
        except ValueError:
            current_status = PaymentStatus.PENDENTE

        if current_status in _TERMINAL_STATES and new_status != current_status:
            logger.info(
                "processar_webhook - não-regressão: %s é terminal, não mudar para %s",
                current_status.value, new_status.value,
            )
            return record

        updated = self._store.update_external_payment_status(
            payment_id=record["id"],
            status=new_status.value,
            last_event_id=event.event_id,
        )

        if not updated:
            logger.warning(
                "processar_webhook - update bloqueado payment_id=%s status=%s",
                record["id"], new_status.value,
            )
            return record

        logger.info(
            "processar_webhook - success payment_id=%s status=%s event_id=%s",
            record["id"], new_status.value, event.event_id,
        )

        return self._store.get_external_payment(payment_id=record["id"])

    # ------------------------------------------------------------------
    # Consulta de status (reconciliação)
    # ------------------------------------------------------------------

    def consultar_pagamento(self, *, payment_id: str) -> dict[str, Any] | None:
        """Consulta o status de um pagamento no PSP e atualiza localmente.

        Usado pela reconciliação Cardápio → PSP (Bloco 3.7).
        """
        record = self._store.get_external_payment(payment_id=payment_id)
        if record is None:
            return None

        provider_tx_id = record.get("provider_transaction_id")
        if not provider_tx_id:
            return record

        result: PaymentStatusResult = self._adapter.get_payment_status(provider_tx_id)
        new_status = _normalize_status(result.status)

        current_status_str = str(record.get("status") or "").upper()
        try:
            current_status = PaymentStatus(current_status_str)
        except ValueError:
            current_status = PaymentStatus.PENDENTE

        if current_status in _TERMINAL_STATES and new_status != current_status:
            return record

        self._store.update_external_payment_status(
            payment_id=payment_id,
            status=new_status.value,
        )

        return self._store.get_external_payment(payment_id=payment_id)

    # ------------------------------------------------------------------
    # Expiração local
    # ------------------------------------------------------------------

    def expirar_pendentes(self) -> int:
        """Expira pagamentos PENDENTE cujo expires_at < NOW().

        Bloco 4.3b — expiração local.
        O PagBank não envia webhook de expiração para PIX QR Code.
        Retorna a quantidade de pagamentos expirados.
        """
        count = self._store.expire_stale_pending_payments()
        if count > 0:
            logger.info("expirar_pendentes - %s pagamento(s) expirado(s)", count)
        return count

    # ------------------------------------------------------------------
    # Claim e application (PDV)
    # ------------------------------------------------------------------

    def listar_aprovados_nao_aplicados(self) -> list[dict[str, Any]]:
        """Lista pagamentos APROVADOS não aplicados (para o PDV descobrir)."""
        return self._store.list_pending_external_payments()

    def claim_pagamento(self, *, payment_id: str, pdv_id: str) -> dict[str, Any] | None:
        """PDV reivindica um pagamento aprovado.

        Retorna o registro atualizado, ou None se já foi reivindicado por outro PDV.
        """
        return self._store.claim_external_payment(
            payment_id=payment_id, pdv_id=pdv_id,
        )

    def aplicar_pagamento(
        self,
        *,
        payment_id: str,
        sale_id: int,
        sale_payment_id: int,
    ) -> bool:
        """PDV aplica o pagamento a uma venda (após claim).

        Retorna True se aplicado, False se já foi aplicado ou não encontrado.
        """
        return self._store.apply_external_payment(
            payment_id=payment_id,
            sale_id=sale_id,
            sale_payment_id=sale_payment_id,
        )

    # ------------------------------------------------------------------
    # Consulta por referência
    # ------------------------------------------------------------------

    def listar_por_referencia(self, *, reference_id: str) -> list[dict[str, Any]]:
        """Lista pagamentos por reference_id (ex.: solicitacao_id do Cardápio)."""
        return self._store.list_pending_by_reference(reference_id=reference_id)

    def obter_pagamento(self, *, payment_id: str) -> dict[str, Any] | None:
        """Busca um pagamento por ID."""
        return self._store.get_external_payment(payment_id=payment_id)
