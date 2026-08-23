"""
F5 — Testes financeiros do Cardápio (1/3): PaymentService.

Cobre o nível 1 do domínio de pagamentos (cardapio_app/payments/domain.py).
Não requer PostgreSQL, credenciais do PagBank nem rede. Usa mocks para o
adapter e para o store.

Cenários obrigatórios (STATUS_TAREFAS_FINANCEIRO.md, F5):
    1. iniciar_pagamento cria registro com status PENDENTE
    2. processar_webhook com evento duplicado é idempotente
    3. processar_webhook com reference_id divergente é rejeitado
    4. processar_webhook com currency divergente é rejeitado
    5. Não-regressão de estados terminais (APROVADO, RECUSADO, CANCELADO)
    6. EXPIRADO → APROVADO permitido (PIX pago após expiração)
    7. consultar_pagamento atualiza status via PSP
    8. expirar_pendentes delega ao store
    9. processar_webhook_confirmado cai em processar_webhook quando assinatura OK
   10. processar_webhook_confirmado consulta PSP quando assinatura ausente (sandbox)
   11. listar_por_referencia delega ao store
   12. extrair_provider_transaction_id rejeita payload inválido

Execute com:
    python Cardapio/tests/test_payment_service.py
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDAPIO_ROOT = REPO_ROOT / "Cardapio"
sys.path.insert(0, str(CARDAPIO_ROOT))

from cardapio_app.payments.adapter_contract import (  # noqa: E402
    CreatePaymentRequest,
    CreatePaymentResult,
    PaymentEvent,
    PaymentMethod,
    PaymentProviderAdapter,
    PaymentStatusResult,
    ProviderPaymentStatus,
    QRCodeData,
)
from cardapio_app.payments.domain import (  # noqa: E402
    PaymentService,
    PaymentStatus,
    extrair_provider_transaction_id,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeAdapter(PaymentProviderAdapter):
    """Adapter que registra chamadas e devolve resultados configuráveis."""

    def __init__(
        self,
        *,
        provider_id: str = "PAGBANK",
        create_result: CreatePaymentResult | None = None,
        status_result: PaymentStatusResult | None = None,
        webhook_event: PaymentEvent | None = None,
        webhook_valid: bool = True,
    ) -> None:
        self._provider_id = provider_id
        self._create_result = create_result
        self._status_result = status_result
        self._webhook_event = webhook_event
        self._webhook_valid = webhook_valid
        self.create_calls: list[CreatePaymentRequest] = []
        self.status_calls: list[str] = []
        self.webhook_calls: list[tuple[dict[str, str], bytes]] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def create_payment(self, request: CreatePaymentRequest) -> CreatePaymentResult:
        self.create_calls.append(request)
        if self._create_result is not None:
            return self._create_result
        return CreatePaymentResult(
            provider_transaction_id="ORDE_FAKE_" + uuid.uuid4().hex[:8],
            status=ProviderPaymentStatus.PENDING,
            qr_code=QRCodeData(payload="00020126BR.GOV.BCB.PIX", image_base64=None, image_url=None),
            expires_at=datetime.now() + timedelta(seconds=1800),
        )

    def get_payment_status(self, provider_transaction_id: str) -> PaymentStatusResult:
        self.status_calls.append(provider_transaction_id)
        if self._status_result is not None:
            return self._status_result
        return PaymentStatusResult(
            provider_transaction_id=provider_transaction_id,
            status=ProviderPaymentStatus.APPROVED,
            amount=52.00,
        )

    def cancel_payment(self, provider_transaction_id: str) -> bool:
        return False

    def validate_webhook(self, headers: dict[str, str], body: bytes) -> PaymentEvent | None:
        self.webhook_calls.append((headers, body))
        if not self._webhook_valid:
            return None
        return self._webhook_event


class FakeStore:
    """Store em memória que simula external_payments."""

    def __init__(self) -> None:
        self.payments: dict[str, dict[str, Any]] = {}
        self.updates: list[tuple[str, str, str | None]] = []
        self.expired_count: int = 0

    def create_external_payment(self, **kwargs: Any) -> dict[str, Any]:
        pid = kwargs["payment_id"]
        rec = {
            "id": pid,
            "provider_id": kwargs["provider_id"],
            "provider_transaction_id": kwargs["provider_transaction_id"],
            "payment_method": kwargs["payment_method"],
            "amount": kwargs["amount"],
            "currency": "BRL",
            "status": "PENDENTE",
            "reference_id": kwargs.get("reference_id"),
            "qr_code_payload": kwargs.get("qr_code_payload"),
            "qr_code_image_base64": kwargs.get("qr_code_image_base64"),
            "qr_code_image_url": kwargs.get("qr_code_image_url"),
            "expires_at": kwargs.get("expires_at"),
            "last_event_id": None,
            "last_event_at": None,
            "metadata": kwargs.get("metadata"),
        }
        self.payments[pid] = rec
        return dict(rec)

    def get_external_payment(self, *, payment_id: str) -> dict[str, Any] | None:
        rec = self.payments.get(payment_id)
        return dict(rec) if rec else None

    def get_external_payment_by_provider_tx(
        self, *, provider_id: str, provider_transaction_id: str
    ) -> dict[str, Any] | None:
        for rec in self.payments.values():
            if (
                rec.get("provider_id") == provider_id
                and rec.get("provider_transaction_id") == provider_transaction_id
            ):
                return dict(rec)
        return None

    def update_external_payment_status(
        self, *, payment_id: str, status: str, last_event_id: Any = None
    ) -> bool:
        rec = self.payments.get(payment_id)
        if rec is None:
            return False
        self.updates.append((payment_id, status, last_event_id))
        rec["status"] = status
        if last_event_id is not None:
            rec["last_event_id"] = last_event_id
        return True

    def expire_stale_pending_payments(self) -> int:
        self.expired_count += 1
        return 2

    def list_pending_external_payments(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.payments.values() if r.get("status") == "APROVADO"]

    def list_pending_by_reference(self, *, reference_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.payments.values() if r.get("reference_id") == reference_id]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _futuro(segundos: int = 1800) -> str:
    return _iso(datetime.now() + timedelta(seconds=segundos))


def _passado(segundos: int = 60) -> str:
    return _iso(datetime.now() - timedelta(seconds=segundos))


def _build_service(
    *,
    create_result: CreatePaymentResult | None = None,
    status_result: PaymentStatusResult | None = None,
    webhook_event: PaymentEvent | None = None,
    webhook_valid: bool = True,
) -> tuple[PaymentService, FakeStore, FakeAdapter]:
    store = FakeStore()
    adapter = FakeAdapter(
        create_result=create_result,
        status_result=status_result,
        webhook_event=webhook_event,
        webhook_valid=webhook_valid,
    )
    return PaymentService(store=store, adapter=adapter), store, adapter


def _seed_pendente(
    store: FakeStore,
    *,
    payment_id: str = "ext-1",
    provider_tx: str = "ORDE_X1",
    reference_id: str = "sol-1",
    status: str = "PENDENTE",
    last_event_id: str | None = None,
    expires_at: str | None = None,
    currency: str = "BRL",
) -> dict[str, Any]:
    rec = {
        "id": payment_id,
        "provider_id": "PAGBANK",
        "provider_transaction_id": provider_tx,
        "payment_method": "PIX",
        "amount": 52.00,
        "currency": currency,
        "status": status,
        "reference_id": reference_id,
        "qr_code_payload": "00020126",
        "qr_code_image_base64": None,
        "qr_code_image_url": None,
        "expires_at": expires_at or _futuro(),
        "last_event_id": last_event_id,
        "last_event_at": None,
        "metadata": None,
    }
    store.payments[payment_id] = rec
    return dict(rec)


def _webhook_body(
    *,
    provider_tx: str = "ORDE_X1",
    status: str = "PAID",
    reference_id: str | None = None,
    currency: str | None = None,
) -> bytes:
    payload: dict[str, Any] = {
        "id": provider_tx,
        "charges": [{"status": status}],
    }
    if reference_id is not None:
        payload["reference_id"] = reference_id
    if currency is not None:
        payload["currency"] = currency
    return json.dumps(payload).encode("utf-8")


# ---------------------------------------------------------------------------
# 1. iniciar_pagamento cria registro PENDENTE
# ---------------------------------------------------------------------------


def test_iniciar_pagamento_cria_pendente() -> None:
    service, store, adapter = _build_service()
    record = service.iniciar_pagamento(
        payment_method=PaymentMethod.PIX,
        amount=52.00,
        reference_id="sol-1",
        description="Pedido X",
        expires_in_seconds=1800,
    )

    assert isinstance(record, dict)
    assert record["status"] == "PENDENTE"
    assert record["payment_method"] == "PIX"
    assert record["amount"] == 52.00
    assert record["reference_id"] == "sol-1"
    assert record["provider_transaction_id"].startswith("ORDE_FAKE_")
    assert record["qr_code_payload"] == "00020126BR.GOV.BCB.PIX"
    assert len(adapter.create_calls) == 1
    assert adapter.create_calls[0].amount == 52.00
    print("[OK] 1: iniciar_pagamento cria registro PENDENTE com QR Code")


# ---------------------------------------------------------------------------
# 2. processar_webhook idempotente (evento duplicado)
# ---------------------------------------------------------------------------


def test_webhook_evento_duplicado_e_idempotente() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-001",
        amount=52.00,
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, last_event_id="evt-001")

    result = service.processar_webhook(headers={}, body=_webhook_body())

    # Não deve atualizar — evento já processado
    assert result is not None
    assert result["status"] == "PENDENTE"
    assert store.updates == [], "não deve chamar update_external_payment_status"
    print("[OK] 2: evento duplicado (mesmo last_event_id) é idempotente")


# ---------------------------------------------------------------------------
# 3. processar_webhook com reference_id divergente é rejeitado
# ---------------------------------------------------------------------------


def test_webhook_reference_id_divergente_rejeitado() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-002",
        reference_id="sol-OUTRO",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, reference_id="sol-1")

    result = service.processar_webhook(headers={}, body=_webhook_body())

    assert result is None, "webhook com reference_id divergente deve ser rejeitado"
    assert store.updates == []
    print("[OK] 3: reference_id divergente entre evento e registro é rejeitado")


def test_webhook_reference_id_coincidente_aceito() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-003",
        reference_id="sol-1",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, reference_id="sol-1")

    result = service.processar_webhook(headers={}, body=_webhook_body())

    assert result is not None
    assert result["status"] == "APROVADO"
    print("[OK] 3b: reference_id coincidente é aceito")


# ---------------------------------------------------------------------------
# 4. processar_webhook com currency divergente é rejeitado
# ---------------------------------------------------------------------------


def test_webhook_currency_divergente_rejeitado() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-004",
        currency="USD",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, currency="BRL")

    result = service.processar_webhook(headers={}, body=_webhook_body())

    assert result is None, "webhook com currency divergente deve ser rejeitado"
    assert store.updates == []
    print("[OK] 4: currency divergente (USD vs BRL) é rejeitado")


def test_webhook_currency_coincidente_aceito() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-005",
        currency="BRL",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, currency="BRL")

    result = service.processar_webhook(headers={}, body=_webhook_body())

    assert result is not None
    assert result["status"] == "APROVADO"
    print("[OK] 4b: currency coincidente (BRL) é aceito")


# ---------------------------------------------------------------------------
# 5. Não-regressão de estados terminais
# ---------------------------------------------------------------------------


def test_nao_regressao_aprovado() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.DECLINED,
        event_id="evt-010",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, status="APROVADO", last_event_id="evt-old")

    result = service.processar_webhook(headers={}, body=_webhook_body(status="DECLINED"))

    assert result is not None
    assert result["status"] == "APROVADO", "APROVADO é terminal, não pode regredir"
    assert store.updates == []
    print("[OK] 5: APROVADO é terminal — webhook DECLINED não regrediu")


def test_nao_regressao_recusado() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-011",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, status="RECUSADO", last_event_id="evt-old")

    result = service.processar_webhook(headers={}, body=_webhook_body(status="PAID"))

    assert result is not None
    assert result["status"] == "RECUSADO"
    assert store.updates == []
    print("[OK] 5b: RECUSADO é terminal — webhook PAID não regrediu")


def test_nao_regressao_cancelado() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-012",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, status="CANCELADO", last_event_id="evt-old")

    result = service.processar_webhook(headers={}, body=_webhook_body(status="PAID"))

    assert result is not None
    assert result["status"] == "CANCELADO"
    assert store.updates == []
    print("[OK] 5c: CANCELADO é terminal — webhook PAID não regrediu")


# ---------------------------------------------------------------------------
# 6. EXPIRADO → APROVADO permitido
# ---------------------------------------------------------------------------


def test_expirado_para_aprovado_permitido() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-020",
    )
    service, store, _ = _build_service(webhook_event=event)
    _seed_pendente(store, status="EXPIRADO", last_event_id="evt-old", expires_at=_passado())

    result = service.processar_webhook(headers={}, body=_webhook_body(status="PAID"))

    assert result is not None
    assert result["status"] == "APROVADO", "EXPIRADO -> APROVADO deve ser permitido"
    assert store.updates == [("ext-1", "APROVADO", "evt-020")]
    print("[OK] 6: EXPIRADO -> APROVADO e a excecao permitida a nao-regressao")


# ---------------------------------------------------------------------------
# 7. consultar_pagamento atualiza status via PSP
# ---------------------------------------------------------------------------


def test_consultar_pagamento_atualiza_status() -> None:
    status_result = PaymentStatusResult(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        amount=52.00,
    )
    service, store, _ = _build_service(status_result=status_result)
    _seed_pendente(store, status="PENDENTE")

    result = service.consultar_pagamento(payment_id="ext-1")

    assert result is not None
    assert result["status"] == "APROVADO"
    assert store.updates == [("ext-1", "APROVADO", None)]
    print("[OK] 7: consultar_pagamento consulta PSP e atualiza status")


def test_consultar_pagamento_respeita_nao_regressao() -> None:
    status_result = PaymentStatusResult(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.DECLINED,
    )
    service, store, _ = _build_service(status_result=status_result)
    _seed_pendente(store, status="APROVADO")

    result = service.consultar_pagamento(payment_id="ext-1")

    assert result is not None
    assert result["status"] == "APROVADO"
    assert store.updates == [], "APROVADO é terminal — consulta não deve regredir"
    print("[OK] 7b: consultar_pagamento respeita não-regressão de terminal")


# ---------------------------------------------------------------------------
# 8. expirar_pendentes delega ao store
# ---------------------------------------------------------------------------


def test_expirar_pendentes_delega_ao_store() -> None:
    service, store, _ = _build_service()
    count = service.expirar_pendentes()

    assert count == 2
    assert store.expired_count == 1, "deve chamar expire_stale_pending_payments uma vez"
    print("[OK] 8: expirar_pendentes delega ao store e retorna a contagem")


# ---------------------------------------------------------------------------
# 9. processar_webhook_confirmado com assinatura válida delega para processar_webhook
# ---------------------------------------------------------------------------


def test_webhook_confirmado_com_assinatura_valida() -> None:
    event = PaymentEvent(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        event_id="evt-030",
    )
    service, store, adapter = _build_service(webhook_event=event, webhook_valid=True)
    _seed_pendente(store)

    result = service.processar_webhook_confirmado(headers={"x-authenticity-token": "ok"}, body=_webhook_body())

    assert result is not None
    assert result["status"] == "APROVADO"
    # validate_webhook e chamado duas vezes: uma por processar_webhook_confirmado
    # (para decidir o caminho) e outra por processar_webhook (caminho original).
    assert len(adapter.webhook_calls) == 2
    print("[OK] 9: webhook_confirmado com assinatura valida delega para processar_webhook")


# ---------------------------------------------------------------------------
# 10. processar_webhook_confirmado sem assinatura consulta PSP (sandbox)
# ---------------------------------------------------------------------------


def test_webhook_confirmado_sem_assinatura_consulta_psp() -> None:
    status_result = PaymentStatusResult(
        provider_transaction_id="ORDE_X1",
        status=ProviderPaymentStatus.APPROVED,
        amount=52.00,
    )
    service, store, adapter = _build_service(
        webhook_event=None,
        webhook_valid=False,
        status_result=status_result,
    )
    _seed_pendente(store, status="PENDENTE")

    result = service.processar_webhook_confirmado(headers={}, body=_webhook_body())

    assert result is not None
    assert result["status"] == "APROVADO"
    assert len(adapter.status_calls) == 1, "deve consultar o PSP uma vez"
    assert adapter.status_calls[0] == "ORDE_X1"
    print("[OK] 10: webhook_confirmado sem assinatura consulta PSP (modo sandbox)")


def test_webhook_confirmado_pagamento_desconhecido_ignorado() -> None:
    service, store, adapter = _build_service(webhook_valid=False)
    # Não seeda nenhum pagamento

    result = service.processar_webhook_confirmado(headers={}, body=_webhook_body(provider_tx="ORDE_DESC"))

    assert result is None, "pagamento desconhecido deve ser ignorado"
    assert adapter.status_calls == []
    print("[OK] 10b: webhook_confirmado para pagamento desconhecido é ignorado")


# ---------------------------------------------------------------------------
# 11. listar_por_referencia delega ao store
# ---------------------------------------------------------------------------


def test_listar_por_referencia_delega_ao_store() -> None:
    service, store, _ = _build_service()
    _seed_pendente(store, payment_id="ext-1", reference_id="sol-1")
    _seed_pendente(store, payment_id="ext-2", reference_id="sol-1", provider_tx="ORDE_X2")
    _seed_pendente(store, payment_id="ext-3", reference_id="sol-2", provider_tx="ORDE_X3")

    result = service.listar_por_referencia(reference_id="sol-1")

    assert len(result) == 2
    assert all(r["reference_id"] == "sol-1" for r in result)
    print("[OK] 11: listar_por_referencia delega ao store e filtra corretamente")


# ---------------------------------------------------------------------------
# 12. extrair_provider_transaction_id rejeita payload inválido
# ---------------------------------------------------------------------------


def test_extrair_provider_transaction_id_valido() -> None:
    body = json.dumps({"id": "ORDE_ABC123"}).encode("utf-8")
    assert extrair_provider_transaction_id(body) == "ORDE_ABC123"
    print("[OK] 12: extrai id de payload válido")


def test_extrair_provider_transaction_id_payload_invalido() -> None:
    assert extrair_provider_transaction_id(b"not json") is None
    assert extrair_provider_transaction_id(b"") is None
    assert extrair_provider_transaction_id(b"{}") is None
    assert extrair_provider_transaction_id(json.dumps([]).encode("utf-8")) is None
    assert extrair_provider_transaction_id(json.dumps({"id": ""}).encode("utf-8")) is None
    assert extrair_provider_transaction_id(json.dumps({"id": "   "}).encode("utf-8")) is None
    print("[OK] 12b: payload inválido/vazio retorna None sem levantar")


# ---------------------------------------------------------------------------
# 13. Mapeamento de status do provider para o domínio
# ---------------------------------------------------------------------------


def test_mapeamento_status_provider_para_dominio() -> None:
    from cardapio_app.payments.domain import _normalize_status

    casos = [
        (ProviderPaymentStatus.PENDING, PaymentStatus.PENDENTE),
        (ProviderPaymentStatus.APPROVED, PaymentStatus.APROVADO),
        (ProviderPaymentStatus.DECLINED, PaymentStatus.RECUSADO),
        (ProviderPaymentStatus.CANCELLED, PaymentStatus.CANCELADO),
        (ProviderPaymentStatus.EXPIRED, PaymentStatus.EXPIRADO),
        (ProviderPaymentStatus.ERROR, PaymentStatus.RECUSADO),
    ]
    for provider_status, expected in casos:
        obtained = _normalize_status(provider_status)
        assert obtained == expected, f"{provider_status}: esperado {expected}, obtido {obtained}"
    print("[OK] 13: mapeamento ProviderPaymentStatus -> PaymentStatus correto para os 6 status")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def test_feature_flag_cartao_online_desligada_por_padrao() -> None:
    """A flag do cartao online deve ser desligada por padrao (preparacao V2)."""
    import os

    from cardapio_app.pagamento_online import domain as online_domain

    original = os.environ.get("CARDAPIO_CARTAO_ONLINE_ENABLED")
    try:
        os.environ.pop("CARDAPIO_CARTAO_ONLINE_ENABLED", None)
        assert online_domain.cartao_online_enabled() is False, "deve ser desligada por padrao"
        os.environ["CARDAPIO_CARTAO_ONLINE_ENABLED"] = "1"
        assert online_domain.cartao_online_enabled() is True
        os.environ["CARDAPIO_CARTAO_ONLINE_ENABLED"] = "0"
        assert online_domain.cartao_online_enabled() is False
    finally:
        if original is None:
            os.environ.pop("CARDAPIO_CARTAO_ONLINE_ENABLED", None)
        else:
            os.environ["CARDAPIO_CARTAO_ONLINE_ENABLED"] = original
    print("[OK] 14: feature flag CARDAPIO_CARTAO_ONLINE_ENABLED desligada por padrao")


def test_flag_cartao_nao_afeta_pix() -> None:
    """Ligar a flag de cartao nao deve alterar o comportamento do PIX."""
    import os

    from cardapio_app.pagamento_online import domain as online_domain

    original_cartao = os.environ.get("CARDAPIO_CARTAO_ONLINE_ENABLED")
    original_pix = os.environ.get("CARDAPIO_PIX_ONLINE_ENABLED")
    try:
        # Ligar cartao, desligar PIX
        os.environ["CARDAPIO_CARTAO_ONLINE_ENABLED"] = "1"
        os.environ.pop("CARDAPIO_PIX_ONLINE_ENABLED", None)
        assert online_domain.cartao_online_enabled() is True
        assert online_domain.pix_online_enabled() is False
        # PIX continua nao cobravel para cartao
        assert online_domain.is_online_chargeable("CARTAO_CREDITO") is False
        assert online_domain.is_online_chargeable("PIX") is True
    finally:
        if original_cartao is None:
            os.environ.pop("CARDAPIO_CARTAO_ONLINE_ENABLED", None)
        else:
            os.environ["CARDAPIO_CARTAO_ONLINE_ENABLED"] = original_cartao
        if original_pix is None:
            os.environ.pop("CARDAPIO_PIX_ONLINE_ENABLED", None)
        else:
            os.environ["CARDAPIO_PIX_ONLINE_ENABLED"] = original_pix
    print("[OK] 15: flag de cartao ligada nao afeta elegibilidade PIX")


def main() -> int:
    testes = [
        test_iniciar_pagamento_cria_pendente,
        test_webhook_evento_duplicado_e_idempotente,
        test_webhook_reference_id_divergente_rejeitado,
        test_webhook_reference_id_coincidente_aceito,
        test_webhook_currency_divergente_rejeitado,
        test_webhook_currency_coincidente_aceito,
        test_nao_regressao_aprovado,
        test_nao_regressao_recusado,
        test_nao_regressao_cancelado,
        test_expirado_para_aprovado_permitido,
        test_consultar_pagamento_atualiza_status,
        test_consultar_pagamento_respeita_nao_regressao,
        test_expirar_pendentes_delega_ao_store,
        test_webhook_confirmado_com_assinatura_valida,
        test_webhook_confirmado_sem_assinatura_consulta_psp,
        test_webhook_confirmado_pagamento_desconhecido_ignorado,
        test_listar_por_referencia_delega_ao_store,
        test_extrair_provider_transaction_id_valido,
        test_extrair_provider_transaction_id_payload_invalido,
        test_mapeamento_status_provider_para_dominio,
        test_feature_flag_cartao_online_desligada_por_padrao,
        test_flag_cartao_nao_afeta_pix,
    ]

    falhas = 0
    for t in testes:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"[FALHOU] {t.__name__}: {e}")

    print("-" * 70)
    if falhas:
        print(f"{falhas} de {len(testes)} teste(s) falharam")
        return 1
    print(f"{len(testes)} testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
