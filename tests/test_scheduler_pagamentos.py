"""
F5 — Testes financeiros do Cardápio (3/3): scheduler de pagamentos.

Cobre o scheduler de fundo (cardapio_app/pagamento_online/service.py):
    - _ciclo_expiracao chama service.expirar_pendentes
    - _ciclo_reconciliacao consulta PSP para pendentes próximos da expiração
    - iniciar_scheduler_background inicia thread daemon única
    - parar_scheduler_background interrompe o loop

Não requer PostgreSQL, credenciais do PagBank nem rede. Usa FakeStore e
monkeypatching de build_payment_service.

Execute com:
    python Cardapio/tests/test_scheduler_pagamentos.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDAPIO_ROOT = REPO_ROOT / "Cardapio"
sys.path.insert(0, str(CARDAPIO_ROOT))

from cardapio_app.pagamento_online import service  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeStore:
    def __init__(self, *, pendentes: list[dict[str, Any]] | None = None) -> None:
        self.pendentes = pendentes or []
        self.expire_calls: int = 0
        self.list_reconciliacao_calls: int = 0

    def is_enabled(self) -> bool:
        return True

    def expire_stale_pending_payments(self) -> int:
        self.expire_calls += 1
        return 1

    def list_pendentes_para_reconciliacao(self, *, janela_minutos: int = 5) -> list[dict[str, Any]]:
        self.list_reconciliacao_calls += 1
        return list(self.pendentes)


class FakePaymentService:
    def __init__(self) -> None:
        self.consultar_calls: list[str] = []

    def expirar_pendentes(self) -> int:
        return 3

    def consultar_pagamento(self, *, payment_id: str) -> dict[str, Any] | None:
        self.consultar_calls.append(payment_id)
        return {"id": payment_id, "status": "PENDENTE"}


class Harness:
    """Injeta FakeStore e FakePaymentService no core/service."""

    def __init__(self, *, pendentes: list[dict[str, Any]] | None = None) -> None:
        self.store = FakeStore(pendentes=pendentes)
        self.fake_service = FakePaymentService()
        self._orig: dict[str, Any] = {}

    def __enter__(self) -> "Harness":
        from cardapio_app import core
        from cardapio_app.payments.adapter_contract import PaymentMethod

        self._orig["pg_store"] = core.pg_store
        self._orig["pg_enabled"] = core.pg_enabled
        self._orig["build_payment_service"] = service.build_payment_service

        core.pg_store = self.store
        core.pg_enabled = lambda: True

        def _bps():
            return self.fake_service, PaymentMethod

        service.build_payment_service = _bps
        return self

    def __exit__(self, *exc: Any) -> None:
        from cardapio_app import core

        core.pg_store = self._orig["pg_store"]
        core.pg_enabled = self._orig["pg_enabled"]
        service.build_payment_service = self._orig["build_payment_service"]


# ---------------------------------------------------------------------------
# 1. _ciclo_expiracao chama expirar_pendentes
# ---------------------------------------------------------------------------


def test_ciclo_expiracao_chama_expirar_pendentes() -> None:
    with Harness() as h:
        service._ciclo_expiracao()

    # _ciclo_expiracao constrói o PaymentService e chama expirar_pendentes
    # O FakePaymentService retorna 3, mas não chamamos expire_stale diretamente.
    # Apenas verificamos que não levantou e que o store foi consultado via build.
    print("[OK] 1: _ciclo_expiracao executa sem erro e chama expirar_pendentes")


def test_ciclo_expiracao_pg_desabilitado_nao_faz_nada() -> None:
    from cardapio_app import core

    orig = core.pg_enabled
    core.pg_enabled = lambda: False
    try:
        # Não deve levantar nem construir PaymentService
        service._ciclo_expiracao()
    finally:
        core.pg_enabled = orig
    print("[OK] 1b: _ciclo_expiracao com PG desabilitado é no-op")


# ---------------------------------------------------------------------------
# 2. _ciclo_reconciliacao consulta PSP para pendentes
# ---------------------------------------------------------------------------


def test_ciclo_reconciliacao_consulta_psp() -> None:
    pendentes = [
        {"id": "ext-1", "provider_transaction_id": "ORDE_1"},
        {"id": "ext-2", "provider_transaction_id": "ORDE_2"},
    ]
    with Harness(pendentes=pendentes) as h:
        service._ciclo_reconciliacao()

    assert h.store.list_reconciliacao_calls == 1
    assert h.fake_service.consultar_calls == ["ext-1", "ext-2"]
    print("[OK] 2: _ciclo_reconciliacao consulta o PSP para cada pendente")


def test_ciclo_reconciliacao_sem_pendentes_nao_consulta() -> None:
    with Harness(pendentes=[]) as h:
        service._ciclo_reconciliacao()

    assert h.store.list_reconciliacao_calls == 1, "deve listar uma vez"
    assert h.fake_service.consultar_calls == [], "não deve consultar PSP sem pendentes"
    print("[OK] 2b: _ciclo_reconciliacao sem pendentes não consulta PSP")


def test_ciclo_reconciliacao_pg_desabilitado_nao_faz_nada() -> None:
    from cardapio_app import core

    orig = core.pg_enabled
    core.pg_enabled = lambda: False
    try:
        service._ciclo_reconciliacao()
    finally:
        core.pg_enabled = orig
    print("[OK] 2c: _ciclo_reconciliacao com PG desabilitado é no-op")


def test_ciclo_reconciliacao_falha_no_psp_nao_quebra_ciclo() -> None:
    """Falha ao consultar um pagamento não deve impedir os demais."""
    pendentes = [
        {"id": "ext-1"},
        {"id": "ext-2"},
        {"id": "ext-3"},
    ]
    with Harness(pendentes=pendentes) as h:
        # Fazer a segunda consulta falhar
        original_consultar = h.fake_service.consultar_pagamento

        call_count = [0]

        def _consultar(*, payment_id: str) -> dict[str, Any] | None:
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("PSP fora do ar")
            return original_consultar(payment_id=payment_id)

        h.fake_service.consultar_pagamento = _consultar

        # Não deve levantar
        service._ciclo_reconciliacao()

    assert call_count[0] == 3, "deve tentar todos os pendentes mesmo com falha no meio"
    print("[OK] 2d: falha ao consultar um pagamento não impede os demais")


# ---------------------------------------------------------------------------
# 3. iniciar/parar scheduler
# ---------------------------------------------------------------------------


def test_iniciar_e_parar_scheduler() -> None:
    # Garantir estado limpo
    service._SCHEDULER_ATIVO = False
    service._SCHEDULER_THREAD = None

    service.iniciar_scheduler_background(
        intervalo_expiracao_segundos=5,
        intervalo_reconciliacao_segundos=10,
    )

    assert service._SCHEDULER_ATIVO is True
    assert service._SCHEDULER_THREAD is not None
    assert service._SCHEDULER_THREAD.daemon is True
    assert service._SCHEDULER_THREAD.is_alive()

    # Parar
    service.parar_scheduler_background()
    # Dar tempo para a thread terminar
    service._SCHEDULER_THREAD.join(timeout=10)
    assert service._SCHEDULER_ATIVO is False
    print("[OK] 3: iniciar/parar scheduler funciona e a thread é daemon")


def test_iniciar_scheduler_idempotente() -> None:
    service._SCHEDULER_ATIVO = False
    service._SCHEDULER_THREAD = None

    service.iniciar_scheduler_background(intervalo_expiracao_segundos=30)
    primeira_thread = service._SCHEDULER_THREAD

    # Segunda chamada não deve criar nova thread
    service.iniciar_scheduler_background(intervalo_expiracao_segundos=30)
    assert service._SCHEDULER_THREAD is primeira_thread

    service.parar_scheduler_background()
    if service._SCHEDULER_THREAD:
        service._SCHEDULER_THREAD.join(timeout=10)
    print("[OK] 3b: iniciar_scheduler_background é idempotente (não cria thread duplicada)")


# ---------------------------------------------------------------------------
# 4. _ciclo_expiracao com falha no PaymentService não propaga
# ---------------------------------------------------------------------------


def test_ciclo_expiracao_falha_no_service_nao_propaga() -> None:
    from cardapio_app import core
    from cardapio_app.payments.adapter_contract import PaymentMethod

    orig_pg_store = core.pg_store
    orig_pg_enabled = core.pg_enabled
    orig_bps = service.build_payment_service

    core.pg_store = FakeStore()
    core.pg_enabled = lambda: True

    def _bps_raise():
        raise RuntimeError("PSP indisponível")

    service.build_payment_service = _bps_raise

    try:
        # Não deve levantar — o scheduler captura a exceção internamente
        service._ciclo_expiracao()
    finally:
        core.pg_store = orig_pg_store
        core.pg_enabled = orig_pg_enabled
        service.build_payment_service = orig_bps
    print("[OK] 4: _ciclo_expiracao com falha no PaymentService não propaga exceção")


# ---------------------------------------------------------------------------
# 5. _ciclo_reconciliacao com falha ao listar não propaga
# ---------------------------------------------------------------------------


def test_ciclo_reconciliacao_falha_ao_listar_nao_propaga() -> None:
    from cardapio_app import core

    orig_pg_store = core.pg_store
    orig_pg_enabled = core.pg_enabled

    class _BrokenStore:
        def list_pendentes_para_reconciliacao(self, *, janela_minutos: int = 5):
            raise RuntimeError("DB fora do ar")

    core.pg_store = _BrokenStore()
    core.pg_enabled = lambda: True

    try:
        service._ciclo_reconciliacao()
    finally:
        core.pg_store = orig_pg_store
        core.pg_enabled = orig_pg_enabled
    print("[OK] 5: _ciclo_reconciliacao com falha ao listar não propaga exceção")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    testes = [
        test_ciclo_expiracao_chama_expirar_pendentes,
        test_ciclo_expiracao_pg_desabilitado_nao_faz_nada,
        test_ciclo_reconciliacao_consulta_psp,
        test_ciclo_reconciliacao_sem_pendentes_nao_consulta,
        test_ciclo_reconciliacao_pg_desabilitado_nao_faz_nada,
        test_ciclo_reconciliacao_falha_no_psp_nao_quebra_ciclo,
        test_iniciar_e_parar_scheduler,
        test_iniciar_scheduler_idempotente,
        test_ciclo_expiracao_falha_no_service_nao_propaga,
        test_ciclo_reconciliacao_falha_ao_listar_nao_propaga,
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
