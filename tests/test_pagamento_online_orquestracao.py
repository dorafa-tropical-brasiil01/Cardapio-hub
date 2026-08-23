"""
F5 — Testes financeiros do Cardápio (2/3): orquestração pagamento_online.

Cobre o nível de orquestração (cardapio_app/pagamento_online/service.py) que
conecta PaymentService ao ciclo de vida da solicitação e ao KDS.
Não requer PostgreSQL, credenciais do PagBank nem rede. Usa FakeStore e
monkeypatching do core.

Cenários obrigatórios (STATUS_TAREFAS_FINANCEIRO.md, F5):
    1. criar_cobranca_pix vincula por reference_id
    2. orquestrar_pagamento_aprovado respeita unicidade financeira
    3. expirar_cobranca_ativa transiciona PENDENTE → EXPIRADO
    4. cancelar_pedido_publico bloqueia pagamento tardio
    5. orquestrar_pagamento_aprovado com pedido cancelado gera ocorrência
    6. orquestrar_pagamento_aprovado sem reference_id retorna SEM_REFERENCIA
    7. orquestrar_pagamento_aprovado com solicitação inexistente
    8. orquestrar_pagamento_aprovado tardio (EM_ATENDIMENTO) gera ocorrência
    9. orquestrar_pagamento_aprovado normal libera produção (KDS + Telegram)
   10. processar_webhook chama orquestrar_pagamento_aprovado em transição real
   11. processar_webhook não orquestra em transição não-real (recusa)
   12. status_publico reflete estado de pagamento antes da confirmação
   13. estado_publico respeita cancelamento

Execute com:
    python Cardapio/tests/test_pagamento_online_orquestracao.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDAPIO_ROOT = REPO_ROOT / "Cardapio"
sys.path.insert(0, str(CARDAPIO_ROOT))

from cardapio_app.pagamento_online import domain  # noqa: E402
from cardapio_app.pagamento_online import service  # noqa: E402
from cardapio_app.pedidos import domain as pedidos_domain  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _futuro(minutos: int = 30) -> str:
    return _iso(datetime.now() + timedelta(minutes=minutos))


def _passado(minutos: int = 5) -> str:
    return _iso(datetime.now() - timedelta(minutes=minutos))


def _payment_record(
    *,
    payment_id: str = "ext-1",
    status: str = "APROVADO",
    reference_id: str = "sol-1",
    amount: float = 52.00,
) -> dict[str, Any]:
    return {
        "id": payment_id,
        "provider_id": "PAGBANK",
        "provider_transaction_id": "ORDE_SECRETO_123",
        "payment_method": "PIX",
        "amount": amount,
        "currency": "BRL",
        "status": status,
        "reference_id": reference_id,
        "qr_code_payload": "00020126BR.GOV.BCB.PIX",
        "qr_code_image_base64": None,
        "qr_code_image_url": None,
        "expires_at": _futuro(30),
        "last_event_id": "evt-abc",
        "last_event_at": _iso(datetime.now()),
        "claimed_by_pdv_id": None,
        "claimed_at": None,
        "applied_sale_id": None,
        "applied_sale_payment_id": None,
        "applied_at": None,
        "metadata": {"description": "interno"},
    }


def _solicitacao(
    *,
    solicitacao_id: str = "sol-1",
    status: str = pedidos_domain.SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO,
    pagamento: Any = None,
    active_payment_id: str | None = "ext-1",
    window: str | None = None,
    cancelado: bool = False,
) -> dict[str, Any]:
    return {
        "id": solicitacao_id,
        "kind": "DELIVERY",
        "access_token": "tok",
        "status": status,
        "pagamento_online": True,
        "pagamento_preferido": "PIX",
        "active_payment_id": active_payment_id,
        "payment_attempts": 1,
        "payment_window_expires_at": window if window is not None else _futuro(120),
        "total_estimado": 52.00,
        "itens": [{"product_code": "X001", "qty": 2}],
        "pagamento": pagamento,
        "ocorrencias_pagamento": [],
        "cancelado": cancelado,
        "cancelado_em": _iso(datetime.now()) if cancelado else None,
    }


class FakeStore:
    """Substituto de pg_store com o mínimo necessário para a orquestração."""

    def __init__(self) -> None:
        self.solicitacoes: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}
        self.kds_rows: list[str] = []
        self.saves = 0
        self.status_publico: dict[str, dict[str, Any]] = {}

    def is_enabled(self) -> bool:
        return True

    def get_solicitacao(self, *, solicitacao_id: str) -> dict[str, Any] | None:
        rec = self.solicitacoes.get(solicitacao_id)
        return dict(rec) if rec else None

    def save_solicitacao(self, *, record: dict[str, Any]) -> None:
        self.saves += 1
        self.solicitacoes[str(record["id"])] = dict(record)

    def list_pending_by_reference(self, *, reference_id: str) -> list[dict[str, Any]]:
        return [dict(p) for p in self.payments.values() if p.get("reference_id") == reference_id]

    def get_external_payment(self, *, payment_id: str) -> dict[str, Any] | None:
        rec = self.payments.get(payment_id)
        return dict(rec) if rec else None

    def get_external_payment_by_provider_tx(
        self, *, provider_id: str, provider_transaction_id: str
    ) -> dict[str, Any] | None:
        for p in self.payments.values():
            if (
                p.get("provider_id") == provider_id
                and p.get("provider_transaction_id") == provider_transaction_id
            ):
                return dict(p)
        return None

    def update_external_payment_status(
        self, *, payment_id: str, status: str, last_event_id: Any = None
    ) -> bool:
        rec = self.payments.get(payment_id)
        if rec is None:
            return False
        rec["status"] = status
        if last_event_id is not None:
            rec["last_event_id"] = last_event_id
        return True

    def kds_ensure_order_row(self, *, solicitacao_id: str) -> None:
        self.kds_rows.append(solicitacao_id)

    def calcular_status_publico(self, *, solicitacao_id: str) -> dict[str, Any] | None:
        return self.status_publico.get(solicitacao_id)


class FakePaymentService:
    """Stand-in para PaymentService usado por criar_cobranca_pix."""

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record
        self.iniciar_calls: list[dict[str, Any]] = []

    def iniciar_pagamento(self, **kwargs: Any) -> dict[str, Any]:
        self.iniciar_calls.append(kwargs)
        # Sobrescrever reference_id com o que foi passado, para validar o vinculo
        rec = dict(self._record)
        if "reference_id" in kwargs and kwargs["reference_id"] is not None:
            rec["reference_id"] = kwargs["reference_id"]
        if "amount" in kwargs and kwargs["amount"] is not None:
            rec["amount"] = kwargs["amount"]
        return rec


class Harness:
    """Injeta FakeStore e neutraliza notificações / build_payment_service."""

    def __init__(self, *, payment_record: dict[str, Any] | None = None) -> None:
        self.store = FakeStore()
        self.kds_notificacoes: list[str] = []
        self.telegram: list[str] = []
        self._orig: dict[str, Any] = {}
        self._payment_record = payment_record

    def __enter__(self) -> "Harness":
        from cardapio_app import core

        self._orig["pg_store"] = core.pg_store
        self._orig["pg_enabled"] = core.pg_enabled
        self._orig["notify"] = core.notify_telegram_new_order
        self._orig["liberar"] = service._liberar_para_producao
        self._orig["build_adapter"] = service.build_adapter
        self._orig["build_payment_service"] = service.build_payment_service

        core.pg_store = self.store
        core.pg_enabled = lambda: True
        core.notify_telegram_new_order = lambda rec: self.telegram.append(str(rec.get("id")))

        def _liberar(rec: dict[str, Any], *, base_url: str = "") -> None:
            sid = str(rec.get("id") or "")
            self.store.kds_ensure_order_row(solicitacao_id=sid)
            core.notify_telegram_new_order(rec)
            self.kds_notificacoes.append(sid)

        service._liberar_para_producao = _liberar

        if self._payment_record is not None:
            fake_service = FakePaymentService(self._payment_record)

            def _build_payment_service() -> tuple[Any, Any]:
                from cardapio_app.payments.adapter_contract import PaymentMethod

                return fake_service, PaymentMethod

            service.build_payment_service = _build_payment_service

        return self

    def __exit__(self, *exc: Any) -> None:
        from cardapio_app import core

        core.pg_store = self._orig["pg_store"]
        core.pg_enabled = self._orig["pg_enabled"]
        core.notify_telegram_new_order = self._orig["notify"]
        service._liberar_para_producao = self._orig["liberar"]
        service.build_adapter = self._orig["build_adapter"]
        service.build_payment_service = self._orig["build_payment_service"]


# ---------------------------------------------------------------------------
# 1. criar_cobranca_pix vincula por reference_id
# ---------------------------------------------------------------------------


def test_criar_cobranca_pix_vincula_reference_id() -> None:
    payment_record = _payment_record(payment_id="ext-NEW", status="PENDENTE")
    with Harness(payment_record=payment_record):
        result = service.criar_cobranca_pix(
            solicitacao_id="sol-77", amount=42.50, descricao="Pedido 77"
        )

    assert isinstance(result, dict)
    assert result["id"] == "ext-NEW"
    assert result["reference_id"] == "sol-77"
    assert result["status"] == "PENDENTE"
    print("[OK] 1: criar_cobranca_pix cria cobrança vinculada por reference_id")


def test_criar_cobranca_pix_falha_lanca_cobranca_error() -> None:
    with Harness():
        # Sobrescrever build_payment_service para lançar
        def _raise() -> tuple[Any, Any]:
            raise RuntimeError("PSP fora do ar")

        service.build_payment_service = _raise
        try:
            try:
                service.criar_cobranca_pix(solicitacao_id="sol-x", amount=10.00)
            except service.CobrancaError as e:
                assert "PSP fora do ar" in str(e)
                print("[OK] 1b: falha no PSP vira CobrancaError")
                return
            raise AssertionError("deveria ter levantado CobrancaError")
        finally:
            # Restaurar é feito pelo __exit__ do Harness
            pass


# ---------------------------------------------------------------------------
# 2. orquestrar_pagamento_aprovado respeita unicidade financeira
# ---------------------------------------------------------------------------


def test_unicidade_financeira_segundo_aprovado() -> None:
    with Harness() as h:
        rec = _solicitacao(
            status=pedidos_domain.SOLICITACAO_STATUS_PENDENTE,
            pagamento={"external_payment_id": "ext-1", "status": "APROVADO"},
            active_payment_id="ext-1",
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="APROVADO")
        h.store.payments["ext-2"] = _payment_record(payment_id="ext-2", status="APROVADO")

        desfecho = service.orquestrar_pagamento_aprovado(
            _payment_record(payment_id="ext-2", status="APROVADO"), base_url="http://x/"
        )

        salvo = h.store.get_solicitacao(solicitacao_id="sol-1")
        assert desfecho == "EXCEDENTE"
        assert salvo["active_payment_id"] == "ext-1", "active_payment_id não pode mudar"
        assert h.kds_notificacoes == [], "KDS não deve ser renotificado"
        ocorrencias = salvo["ocorrencias_pagamento"]
        assert len(ocorrencias) == 1
        assert ocorrencias[0]["tipo"] == domain.OCORRENCIA_PAGAMENTO_EXCEDENTE
        assert ocorrencias[0]["external_payment_id"] == "ext-2"
    print("[OK] 2: segundo pagamento aprovado gera ocorrência e não substitui o ativo")


# ---------------------------------------------------------------------------
# 3. expirar_cobranca_ativa transiciona PENDENTE → EXPIRADO
# ---------------------------------------------------------------------------


def test_expirar_cobranca_ativa_transiciona_para_expirado() -> None:
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "PENDENTE", "expires_at": _futuro(10)}
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="PENDENTE")

        service.expirar_cobranca_ativa(rec)

        pay = h.store.get_external_payment(payment_id="ext-1")
        assert pay is not None
        assert pay["status"] == "EXPIRADO"
    print("[OK] 3: expirar_cobranca_ativa transiciona PENDENTE -> EXPIRADO")


def test_expirar_cobranca_ativa_ignora_nao_pendente() -> None:
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "APROVADO"}
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="APROVADO")

        service.expirar_cobranca_ativa(rec)

        pay = h.store.get_external_payment(payment_id="ext-1")
        assert pay["status"] == "APROVADO", "APROVADO não deve ser expirado"
    print("[OK] 3b: expirar_cobranca_ativa ignora cobrança não-PENDENTE")


def test_expirar_cobranca_ativa_sem_payment_id_nao_faz_nada() -> None:
    with Harness() as h:
        rec = _solicitacao(active_payment_id=None, pagamento=None)
        # Não deve levantar
        service.expirar_cobranca_ativa(rec)
    print("[OK] 3c: expirar_cobranca_ativa sem active_payment_id é no-op")


# ---------------------------------------------------------------------------
# 4. cancelar_pedido_publico bloqueia pagamento tardio
# ---------------------------------------------------------------------------


def test_cancelar_pedido_publico_bloqueia_tardio() -> None:
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "PENDENTE", "expires_at": _futuro(10)}
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="PENDENTE")

        res = service.cancelar_pedido_publico(rec)
        assert res.get("ok") is True

        salvo = h.store.get_solicitacao(solicitacao_id="sol-1")
        assert salvo.get("cancelado") is True
        pay = h.store.get_external_payment(payment_id="ext-1")
        assert pay["status"] == "CANCELADO"

        # Webhook tardio é rejeitado
        desfecho = service.orquestrar_pagamento_aprovado(
            _payment_record(payment_id="ext-1", status="APROVADO"), base_url="http://x/"
        )
        assert desfecho == "CANCELADO"
        assert h.kds_notificacoes == []
    print("[OK] 4: cancelamento do cliente invalida pedido e bloqueia pagamento tardio")


def test_cancelar_pedido_publico_status_nao_cancelavel() -> None:
    with Harness() as h:
        rec = _solicitacao(status=pedidos_domain.SOLICITACAO_STATUS_PENDENTE)
        h.store.save_solicitacao(record=rec)
        res = service.cancelar_pedido_publico(rec)
        assert res.get("ok") is False
        assert res.get("error") == "status_nao_cancelavel"
    print("[OK] 4b: cancelar pedido em status não-cancelável é rejeitado")


def test_cancelar_pedido_publico_ja_cancelado_idempotente() -> None:
    with Harness() as h:
        rec = _solicitacao(cancelado=True)
        h.store.save_solicitacao(record=rec)
        res = service.cancelar_pedido_publico(rec)
        assert res.get("ok") is True
        assert res.get("ja_cancelado") is True
    print("[OK] 4c: cancelar pedido já cancelado é idempotente")


# ---------------------------------------------------------------------------
# 5. orquestrar com pedido cancelado gera ocorrência
# ---------------------------------------------------------------------------


def test_orquestrar_aprovado_com_pedido_cancelado() -> None:
    with Harness() as h:
        rec = _solicitacao(cancelado=True)
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="APROVADO")

        desfecho = service.orquestrar_pagamento_aprovado(
            _payment_record(payment_id="ext-1", status="APROVADO"), base_url="http://x/"
        )

        assert desfecho == "CANCELADO"
        salvo = h.store.get_solicitacao(solicitacao_id="sol-1")
        ocorrencias = salvo["ocorrencias_pagamento"]
        assert len(ocorrencias) == 1
        assert ocorrencias[0]["tipo"] == domain.OCORRENCIA_PAGAMENTO_TARDIO_IGNORADO
        assert h.kds_notificacoes == []
    print("[OK] 5: aprovação para pedido cancelado gera ocorrência e não confirma")


# ---------------------------------------------------------------------------
# 6. orquestrar sem reference_id
# ---------------------------------------------------------------------------


def test_orquestrar_aprovado_sem_reference_id() -> None:
    with Harness() as h:
        pay = _payment_record(reference_id="")
        desfecho = service.orquestrar_pagamento_aprovado(pay, base_url="http://x/")
        assert desfecho == "SEM_REFERENCIA"
        assert h.kds_notificacoes == []
        assert h.store.saves == 0
    print("[OK] 6: pagamento sem reference_id retorna SEM_REFERENCIA")


# ---------------------------------------------------------------------------
# 7. orquestrar com solicitação inexistente
# ---------------------------------------------------------------------------


def test_orquestrar_aprovado_solicitacao_inexistente() -> None:
    with Harness() as h:
        pay = _payment_record(reference_id="sol-NAOEXISTE")
        desfecho = service.orquestrar_pagamento_aprovado(pay, base_url="http://x/")
        assert desfecho == "SOLICITACAO_NAO_ENCONTRADA"
        assert h.kds_notificacoes == []
    print("[OK] 7: pagamento com reference_id inexistente retorna SOLICITACAO_NAO_ENCONTRADA")


# ---------------------------------------------------------------------------
# 8. orquestrar tardio (EM_ATENDIMENTO)
# ---------------------------------------------------------------------------


def test_orquestrar_aprovado_tardio_em_atendimento() -> None:
    with Harness() as h:
        rec = _solicitacao(
            status=pedidos_domain.SOLICITACAO_STATUS_EM_ATENDIMENTO,
            pagamento={"external_payment_id": "ext-1", "status": "PENDENTE", "expires_at": _futuro(5)},
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="APROVADO")

        desfecho = service.orquestrar_pagamento_aprovado(
            _payment_record(payment_id="ext-1", status="APROVADO"), base_url="http://x/"
        )

        assert desfecho == "TARDIO_IGNORADO"
        salvo = h.store.get_solicitacao(solicitacao_id="sol-1")
        assert salvo["status"] == pedidos_domain.SOLICITACAO_STATUS_EM_ATENDIMENTO
        assert salvo["ocorrencias_pagamento"][0]["tipo"] == domain.OCORRENCIA_PAGAMENTO_TARDIO_IGNORADO
        assert h.kds_notificacoes == []
    print("[OK] 8: aprovação com pedido em atendimento gera ocorrência e não confirma")


# ---------------------------------------------------------------------------
# 9. orquestrar normal libera produção
# ---------------------------------------------------------------------------


def test_orquestrar_aprovado_normal_libera_producao() -> None:
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "PENDENTE", "expires_at": _futuro(10)}
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="APROVADO")

        desfecho = service.orquestrar_pagamento_aprovado(
            _payment_record(payment_id="ext-1", status="APROVADO"), base_url="http://x/"
        )

        salvo = h.store.get_solicitacao(solicitacao_id="sol-1")
        assert desfecho == "CONFIRMADO"
        assert salvo["status"] == pedidos_domain.SOLICITACAO_STATUS_PENDENTE
        assert salvo["active_payment_id"] == "ext-1"
        assert salvo["pagamento"]["status"] == "APROVADO"
        assert salvo["pago_em"]
        assert salvo["pagamento"]["confirmado_em"]
        assert h.kds_notificacoes == ["sol-1"]
        assert h.store.kds_rows == ["sol-1"]
        assert h.telegram == ["sol-1"]
        assert "provider_transaction_id" not in salvo["pagamento"]
    print("[OK] 9: aprovação normal confirma, libera KDS e Telegram")


# ---------------------------------------------------------------------------
# 10. processar_webhook chama orquestrar em transição real
# ---------------------------------------------------------------------------


def test_processar_webhook_transicao_real_orquestra() -> None:
    """Simula webhook do sandbox: sem assinatura, consulta PSP, transição real."""
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "PENDENTE", "expires_at": _futuro(10)}
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="PENDENTE")

        # Mockar build_adapter e build_payment_service para simular webhook
        from cardapio_app.payments.adapter_contract import (
            PaymentEvent,
            PaymentMethod,
            PaymentStatusResult,
            ProviderPaymentStatus,
        )

        class _AdapterStub:
            provider_id = "PAGBANK"

            def validate_webhook(self, headers, body):  # noqa: ANN001
                return None  # sandbox: sem assinatura

            def get_payment_status(self, provider_tx):  # noqa: ANN001
                return PaymentStatusResult(
                    provider_transaction_id=provider_tx,
                    status=ProviderPaymentStatus.APPROVED,
                    amount=52.00,
                )

        class _ServiceStub:
            def processar_webhook_confirmado(self, *, headers, body):  # noqa: ANN001
                # Simula o caminho confirmado: consulta PSP e atualiza
                h.store.update_external_payment_status(
                    payment_id="ext-1", status="APROVADO", last_event_id="evt-new"
                )
                return h.store.get_external_payment(payment_id="ext-1")

        h._orig["build_adapter_tmp"] = service.build_adapter
        h._orig["build_payment_service_tmp"] = service.build_payment_service
        service.build_adapter = lambda: _AdapterStub()

        def _bps():
            return _ServiceStub(), PaymentMethod

        service.build_payment_service = _bps

        try:
            body = json.dumps({"id": "ORDE_SECRETO_123", "charges": [{"status": "PAID"}]}).encode("utf-8")
            result = service.processar_webhook(headers={}, body=body, base_url="http://x/")

            assert result is not None
            assert result["status"] == "APROVADO"
            assert h.kds_notificacoes == ["sol-1"], "deve orquestrar a aprovação"
        finally:
            service.build_adapter = h._orig["build_adapter_tmp"]
            service.build_payment_service = h._orig["build_payment_service_tmp"]
    print("[OK] 10: processar_webhook com transição real chama orquestrar_pagamento_aprovado")


# ---------------------------------------------------------------------------
# 11. processar_webhook não orquestra em transição não-real
# ---------------------------------------------------------------------------


def test_processar_webhook_sem_transicao_nao_orquestra() -> None:
    """Pagamento já APROVADO antes do webhook — não há transição real."""
    with Harness() as h:
        rec = _solicitacao(
            status=pedidos_domain.SOLICITACAO_STATUS_PENDENTE,
            pagamento={"external_payment_id": "ext-1", "status": "APROVADO"},
            active_payment_id="ext-1",
        )
        h.store.save_solicitacao(record=rec)
        h.store.payments["ext-1"] = _payment_record(payment_id="ext-1", status="APROVADO")

        from cardapio_app.payments.adapter_contract import (
            PaymentMethod,
            PaymentStatusResult,
            ProviderPaymentStatus,
        )

        class _AdapterStub:
            provider_id = "PAGBANK"

            def validate_webhook(self, headers, body):  # noqa: ANN001
                return None

            def get_payment_status(self, provider_tx):  # noqa: ANN001
                return PaymentStatusResult(
                    provider_transaction_id=provider_tx,
                    status=ProviderPaymentStatus.APPROVED,
                )

        class _ServiceStub:
            def processar_webhook_confirmado(self, *, headers, body):  # noqa: ANN001
                return h.store.get_external_payment(payment_id="ext-1")

        h._orig["build_adapter_tmp"] = service.build_adapter
        h._orig["build_payment_service_tmp"] = service.build_payment_service
        service.build_adapter = lambda: _AdapterStub()

        def _bps():
            return _ServiceStub(), PaymentMethod

        service.build_payment_service = _bps

        try:
            body = json.dumps({"id": "ORDE_SECRETO_123"}).encode("utf-8")
            result = service.processar_webhook(headers={}, body=body, base_url="http://x/")

            assert result is not None
            assert h.kds_notificacoes == [], "não deve orquestrar sem transição real"
        finally:
            service.build_adapter = h._orig["build_adapter_tmp"]
            service.build_payment_service = h._orig["build_payment_service_tmp"]
    print("[OK] 11: processar_webhook sem transição real não orquestra")


# ---------------------------------------------------------------------------
# 12. status_publico reflete estado de pagamento antes da confirmação
# ---------------------------------------------------------------------------


def test_status_publico_aguardando_pagamento() -> None:
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "PENDENTE", "expires_at": _futuro(10)}
        )
        h.store.save_solicitacao(record=rec)

        result = service.status_publico(rec)
        assert result["status_publico"] == "AGUARDANDO_PAGAMENTO"
        assert result["finalizado"] is False
    print("[OK] 12: status_publico reflete AGUARDANDO_PAGAMENTO com QR pendente")


def test_status_publico_expirado() -> None:
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "EXPIRADO"}
        )
        h.store.save_solicitacao(record=rec)

        result = service.status_publico(rec)
        assert result["status_publico"] == "PAGAMENTO_EXPIRADO"
    print("[OK] 12b: status_publico reflete PAGAMENTO_EXPIRADO")


def test_status_publico_cancelado() -> None:
    with Harness() as h:
        rec = _solicitacao(cancelado=True)
        h.store.save_solicitacao(record=rec)

        result = service.status_publico(rec)
        assert result["status_publico"] == "PEDIDO_CANCELADO"
        assert result["finalizado"] is True
    print("[OK] 12c: status_publico reflete PEDIDO_CANCELADO")


# ---------------------------------------------------------------------------
# 13. estado_publico respeita cancelamento
# ---------------------------------------------------------------------------


def test_estado_publico_cancelado() -> None:
    with Harness() as h:
        rec = _solicitacao(cancelado=True)
        result = service.estado_publico(rec)
        assert result["estado_pagamento"] == "CANCELADO"
        assert result["pode_retentar"] is False
    print("[OK] 13: estado_publico cancelado bloqueia retentativa")


def test_estado_publico_aguardando() -> None:
    with Harness() as h:
        rec = _solicitacao(
            pagamento={"external_payment_id": "ext-1", "status": "PENDENTE", "expires_at": _futuro(10)}
        )
        result = service.estado_publico(rec)
        assert result["estado_pagamento"] == domain.ESTADO_AGUARDANDO
        assert result["pode_retentar"] is False, "QR ativo não permite retentativa"
    print("[OK] 13b: estado_publico aguardando bloqueia retentativa com QR ativo")


# ---------------------------------------------------------------------------
# 14. vincular_cobranca incrementa tentativas
# ---------------------------------------------------------------------------


def test_vincular_cobranca_incrementa_tentativas() -> None:
    rec = _solicitacao(pagamento=None, active_payment_id=None)
    rec["payment_attempts"] = 0
    rec["payment_window_expires_at"] = None

    service.vincular_cobranca(rec, _payment_record(payment_id="ext-7", status="PENDENTE"))
    assert rec["active_payment_id"] == "ext-7"
    assert rec["payment_attempts"] == 1
    assert "provider_transaction_id" not in rec["pagamento"]

    service.vincular_cobranca(rec, _payment_record(payment_id="ext-8", status="PENDENTE"))
    assert rec["payment_attempts"] == 2
    assert rec["active_payment_id"] == "ext-8"
    print("[OK] 14: vincular cobrança troca o ativo e conta a tentativa")


# ---------------------------------------------------------------------------
# 15. registrar_falha_cobranca
# ---------------------------------------------------------------------------


def test_registrar_falha_cobranca() -> None:
    rec = _solicitacao(pagamento=None, active_payment_id=None)
    service.registrar_falha_cobranca(rec, erro="PagBank 500")

    assert rec["pagamento"]["falha"] is True
    assert rec["active_payment_id"] is None
    assert domain.derivar_estado_pagamento(solicitacao=rec) == domain.ESTADO_FALHA
    assert rec["ocorrencias_pagamento"][0]["tipo"] == domain.OCORRENCIA_FALHA_CRIACAO_COBRANCA
    assert domain.pode_retentar(solicitacao=rec) is True
    print("[OK] 15: falha na criação da cobrança é rastreada e permite retentativa")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    testes = [
        test_criar_cobranca_pix_vincula_reference_id,
        test_criar_cobranca_pix_falha_lanca_cobranca_error,
        test_unicidade_financeira_segundo_aprovado,
        test_expirar_cobranca_ativa_transiciona_para_expirado,
        test_expirar_cobranca_ativa_ignora_nao_pendente,
        test_expirar_cobranca_ativa_sem_payment_id_nao_faz_nada,
        test_cancelar_pedido_publico_bloqueia_tardio,
        test_cancelar_pedido_publico_status_nao_cancelavel,
        test_cancelar_pedido_publico_ja_cancelado_idempotente,
        test_orquestrar_aprovado_com_pedido_cancelado,
        test_orquestrar_aprovado_sem_reference_id,
        test_orquestrar_aprovado_solicitacao_inexistente,
        test_orquestrar_aprovado_tardio_em_atendimento,
        test_orquestrar_aprovado_normal_libera_producao,
        test_processar_webhook_transicao_real_orquestra,
        test_processar_webhook_sem_transicao_nao_orquestra,
        test_status_publico_aguardando_pagamento,
        test_status_publico_expirado,
        test_status_publico_cancelado,
        test_estado_publico_cancelado,
        test_estado_publico_aguardando,
        test_vincular_cobranca_incrementa_tentativas,
        test_registrar_falha_cobranca,
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
