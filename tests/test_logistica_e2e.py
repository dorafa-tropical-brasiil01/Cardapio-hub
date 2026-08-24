"""
Testes E2E de logística — integração Cardápio ↔ CentralLogistica.

Cobre o webhook de retorno da Central Logística (processar_webhook_central),
idempotência, validação de status e marcação de ENTREGUE no KDS.
Não requer PostgreSQL nem rede — usa FakeStore e monkeypatching do core.

Execute com:
    python Cardapio/tests/test_logistica_e2e.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDAPIO_ROOT = REPO_ROOT / "Cardapio"
sys.path.insert(0, str(CARDAPIO_ROOT))

from cardapio_app.pedidos import domain as pedidos_domain  # noqa: E402


# ---------------------------------------------------------------------------
# FakeStore — substituto de pg_store para logística
# ---------------------------------------------------------------------------


class FakeStore:
    """Substituto de pg_store com o mínimo para logística + KDS."""

    def __init__(self) -> None:
        self.kds_orders: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.webhooks_recebidos: dict[str, dict[str, Any]] = {}
        self.entregue_marcados: list[str] = []

    def is_enabled(self) -> bool:
        return True

    # --- KDS ---

    def kds_ensure_order_row(self, *, solicitacao_id: str) -> None:
        if solicitacao_id not in self.kds_orders:
            self.kds_orders[solicitacao_id] = {
                "solicitacao_id": solicitacao_id,
                "status": pedidos_domain.KDS_STATUS_NOVO,
                "created_em": "2026-08-24T12:00:00",
            }

    def kds_get_status(self, *, solicitacao_id: str) -> str | None:
        row = self.kds_orders.get(solicitacao_id)
        return row["status"] if row else None

    def kds_marcar_entregue(self, *, solicitacao_id: str, ops_user_id: int) -> None:
        self.entregue_marcados.append(solicitacao_id)
        row = self.kds_orders.get(solicitacao_id)
        if row:
            row["status"] = "ENTREGUE"

    # --- Logística ---

    def logistica_event_add(
        self, *, ops_user_id: int, solicitacao_id: str, event: str, note: str | None = None
    ) -> None:
        self.events.append({
            "ops_user_id": ops_user_id,
            "solicitacao_id": solicitacao_id,
            "event": event,
            "note": note,
        })

    def logistica_webhook_receber(
        self, *, idempotency_key: str, solicitacao_id: str, evento: str,
        status_externo: str, payload: dict[str, Any],
    ) -> bool:
        if idempotency_key in self.webhooks_recebidos:
            return False  # idempotente — já processado
        self.webhooks_recebidos[idempotency_key] = {
            "solicitacao_id": solicitacao_id,
            "evento": evento,
            "status_externo": status_externo,
            "payload": payload,
        }
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_module(store: FakeStore) -> None:
    """Configura core com FakeStore."""
    from cardapio_app import core
    core.pg_store = store  # type: ignore
    core.pg_enabled = lambda: True  # type: ignore
    core.central_logistica_enabled = lambda: True  # type: ignore
    core.central_logistica_empresa_id = lambda: "EMPRESA01"  # type: ignore


def _webhook_payload(
    *,
    solicitacao_id: str = "sol-1",
    status: str = "ENTREGUE",
    evento: str | None = None,
    empresa_id: str = "EMPRESA01",
    protocolo: str | None = "PROTO-123",
    entregador_nome: str | None = "João",
    nota: str | None = None,
) -> dict[str, Any]:
    return {
        "solicitacao_id": solicitacao_id,
        "status": status,
        "evento": evento or status,
        "empresa_id": empresa_id,
        "protocolo": protocolo,
        "entregador": {"nome": entregador_nome} if entregador_nome else {},
        "nota": nota,
    }


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def test_webhook_entregue_marca_kds_como_entregue() -> None:
    """Webhook ENTREGUE marca o pedido como ENTREGUE no KDS."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-1")

    result = service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-1", status="ENTREGUE"),
        idempotency_key="key-1",
    )

    assert result["ok"] is True
    assert result["solicitacao_id"] == "sol-1"
    assert result["status"] == "ENTREGUE"
    assert "sol-1" in store.entregue_marcados, "KDS não foi marcado como ENTREGUE"
    print("[OK] 1: webhook ENTREGUE marca pedido como ENTREGUE no KDS")


def test_webhook_em_rota_nao_marca_entregue() -> None:
    """Webhook EM_ROTA registra evento mas NÃO marca como ENTREGUE."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-1")

    service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-1", status="EM_ROTA"),
        idempotency_key="key-2",
    )

    assert "sol-1" not in store.entregue_marcados, "não deveria marcar ENTREGUE para EM_ROTA"
    eventos = [e for e in store.events if e["solicitacao_id"] == "sol-1" and e["event"] == "EM_ROTA"]
    assert len(eventos) == 1, f"esperado 1 evento EM_ROTA, obtido {len(eventos)}"
    print("[OK] 2: webhook EM_ROTA registra evento mas não marca ENTREGUE")


def test_webhook_atribuido_registra_evento() -> None:
    """Webhook ATRIBUIDO registra evento com nome do entregador."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-1")

    service.processar_webhook_central(
        payload=_webhook_payload(
            solicitacao_id="sol-1",
            status="ATRIBUIDO",
            entregador_nome="Carlos",
            protocolo="PROTO-456",
        ),
        idempotency_key="key-3",
    )

    eventos = [e for e in store.events if e["solicitacao_id"] == "sol-1" and e["event"] == "ATRIBUIDO"]
    assert len(eventos) == 1
    note = eventos[0]["note"] or ""
    assert "Carlos" in note, f"nome do entregador não está na nota: {note}"
    assert "PROTO-456" in note, f"protocolo não está na nota: {note}"
    print("[OK] 3: webhook ATRIBUIDO registra evento com entregador e protocolo")


def test_webhook_duplicado_e_idempotente() -> None:
    """Webhook duplicado (mesma idempotency_key) não processa de novo."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-1")

    # Primeiro processamento
    r1 = service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-1", status="ENTREGUE"),
        idempotency_key="dup-key-1",
    )
    assert r1["ok"] is True
    assert r1.get("reprocessado") is not True

    # Segundo processamento (duplicado)
    r2 = service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-1", status="ENTREGUE"),
        idempotency_key="dup-key-1",
    )
    assert r2["ok"] is True
    assert r2.get("reprocessado") is True, "segundo processamento deveria ser idempotente"

    # Apenas 1 evento ENTREGUE
    eventos = [e for e in store.events if e["solicitacao_id"] == "sol-1" and e["event"] == "ENTREGUE"]
    assert len(eventos) == 1, f"esperado 1 evento, obtido {len(eventos)} (não idempotente)"
    print("[OK] 4: webhook duplicado é idempotente — não duplica eventos")


def test_webhook_sem_solicitacao_id_falha() -> None:
    """Webhook sem solicitacao_id levanta ValueError."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)

    try:
        service.processar_webhook_central(
            payload=_webhook_payload(solicitacao_id="", status="ENTREGUE"),
            idempotency_key="key-5",
        )
    except ValueError as e:
        assert "solicitacao_id" in str(e).lower(), f"erro inesperado: {e}"
        print("[OK] 5: webhook sem solicitacao_id falha com ValueError")
        return
    raise AssertionError("deveria ter falhado com solicitacao_id ausente")


def test_webhook_status_invalido_falha() -> None:
    """Webhook com status não reconhecido levanta ValueError."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)

    try:
        service.processar_webhook_central(
            payload=_webhook_payload(solicitacao_id="sol-1", status="STATUS_INEXISTENTE"),
            idempotency_key="key-6",
        )
    except ValueError as e:
        assert "status" in str(e).lower(), f"erro inesperado: {e}"
        print("[OK] 6: webhook com status inválido falha com ValueError")
        return
    raise AssertionError("deveria ter falhado com status inválido")


def test_webhook_sem_idempotency_key_gera_automaticamente() -> None:
    """Webhook sem idempotency_key gera uma automaticamente."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-1")

    result = service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-1", status="ENTREGUE"),
        idempotency_key=None,
    )

    assert result["ok"] is True
    assert len(store.webhooks_recebidos) == 1, "deveria ter registrado 1 webhook"
    print("[OK] 7: webhook sem idempotency_key gera chave automática")


def test_ciclo_completo_logistico() -> None:
    """Ciclo completo: ATRIBUIDO -> EM_ROTA -> ENTREGUE."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-ciclo")

    # ATRIBUIDO
    service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-ciclo", status="ATRIBUIDO", entregador_nome="Pedro"),
        idempotency_key="ciclo-1",
    )
    assert "sol-ciclo" not in store.entregue_marcados

    # EM_ROTA
    service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-ciclo", status="EM_ROTA"),
        idempotency_key="ciclo-2",
    )
    assert "sol-ciclo" not in store.entregue_marcados

    # ENTREGUE
    service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-ciclo", status="ENTREGUE"),
        idempotency_key="ciclo-3",
    )
    assert "sol-ciclo" in store.entregue_marcados, "deveria ter marcado ENTREGUE no final"

    # 3 eventos na ordem correta
    eventos = [e for e in store.events if e["solicitacao_id"] == "sol-ciclo"]
    eventos_esperados = ["ATRIBUIDO", "EM_ROTA", "ENTREGUE"]
    eventos_reais = [e["event"] for e in eventos]
    assert eventos_reais == eventos_esperados, f"eventos: {eventos_reais} != {eventos_esperados}"
    print("[OK] 8: ciclo completo ATRIBUIDO -> EM_ROTA -> ENTREGUE com eventos na ordem")


def test_webhook_com_nota_incluida_no_evento() -> None:
    """Webhook com nota inclui a nota no evento registrado."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-1")

    service.processar_webhook_central(
        payload=_webhook_payload(
            solicitacao_id="sol-1",
            status="EM_ROTA",
            nota="Cliente não atendeu",
        ),
        idempotency_key="key-nota-1",
    )

    eventos = [e for e in store.events if e["solicitacao_id"] == "sol-1" and e["event"] == "EM_ROTA"]
    assert len(eventos) == 1
    note = eventos[0]["note"] or ""
    assert "Cliente não atendeu" in note, f"nota não incluída: {note}"
    print("[OK] 9: webhook com nota inclui a nota no evento")


def test_webhook_empresa_id_diferente_gera_keys_diferentes() -> None:
    """Webhooks de empresas diferentes não colidem na idempotency_key."""
    from cardapio_app.logistica import service
    store = FakeStore()
    _setup_module(store)
    store.kds_ensure_order_row(solicitacao_id="sol-1")

    # Mesmo solicitacao_id, mesma empresa, status diferente — keys diferentes
    r1 = service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-1", status="ATRIBUIDO", empresa_id="EMPRESA01"),
        idempotency_key=None,  # gera automática
    )
    r2 = service.processar_webhook_central(
        payload=_webhook_payload(solicitacao_id="sol-1", status="EM_ROTA", empresa_id="EMPRESA01"),
        idempotency_key=None,
    )

    assert r1["ok"] is True
    assert r2["ok"] is True
    assert len(store.webhooks_recebidos) == 2, "deveria ter 2 webhooks (keys diferentes)"
    print("[OK] 10: webhooks com status diferente geram idempotency_keys diferentes")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    testes = [
        test_webhook_entregue_marca_kds_como_entregue,
        test_webhook_em_rota_nao_marca_entregue,
        test_webhook_atribuido_registra_evento,
        test_webhook_duplicado_e_idempotente,
        test_webhook_sem_solicitacao_id_falha,
        test_webhook_status_invalido_falha,
        test_webhook_sem_idempotency_key_gera_automaticamente,
        test_ciclo_completo_logistico,
        test_webhook_com_nota_incluida_no_evento,
        test_webhook_empresa_id_diferente_gera_keys_diferentes,
    ]

    falhas = 0
    for t in testes:
        try:
            t()
        except Exception as e:
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
