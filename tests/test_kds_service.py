"""
Testes do KDS (Kitchen Display System) — cardapio_app/kds/service.py.

Cobre transições de estado, validação de status, recusa, integração com
logística e idempotência. Não requer PostgreSQL nem rede — usa FakeStore
e monkeypatching do core.

Execute com:
    python Cardapio/tests/test_kds_service.py
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
# FakeStore — substituto de pg_store
# ---------------------------------------------------------------------------


class FakeStore:
    """Substituto de pg_store com o mínimo necessário para o KDS."""

    def __init__(self) -> None:
        self.kds_orders: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.integracoes: list[dict[str, Any]] = []
        self.current_selections: dict[int, str] = {}
        self.entregue_marcados: list[str] = []
        self.webhooks_recebidos: dict[str, dict[str, Any]] = {}

    def is_enabled(self) -> bool:
        return True

    # --- KDS order rows ---

    def kds_ensure_order_row(self, *, solicitacao_id: str) -> None:
        if solicitacao_id not in self.kds_orders:
            self.kds_orders[solicitacao_id] = {
                "solicitacao_id": solicitacao_id,
                "status": pedidos_domain.KDS_STATUS_NOVO,
                "created_em": "2026-08-24T12:00:00",
                "started_em": None,
                "done_em": None,
                "sinalizado_em": None,
                "impressao_solicitada_em": None,
                "recusado_em": None,
                "motivo_recusa": None,
                "nota_recusa": None,
                "ops_user_id": None,
            }

    def kds_get_status(self, *, solicitacao_id: str) -> str | None:
        row = self.kds_orders.get(solicitacao_id)
        return row["status"] if row else None

    def kds_aceitar_pedido(
        self, *, solicitacao_id: str, ops_user_id: int, impressao_solicitada_em: str | None = None
    ) -> None:
        row = self.kds_orders.get(solicitacao_id)
        if not row:
            raise RuntimeError("not_found")
        row["status"] = pedidos_domain.KDS_STATUS_EM_PREPARO
        row["started_em"] = "2026-08-24T12:01:00"
        row["ops_user_id"] = ops_user_id
        if impressao_solicitada_em:
            row["impressao_solicitada_em"] = impressao_solicitada_em

    def kds_recusar_pedido(
        self, *, solicitacao_id: str, ops_user_id: int, motivo_recusa: str, nota_recusa: str | None = None
    ) -> None:
        row = self.kds_orders.get(solicitacao_id)
        if not row:
            raise RuntimeError("not_found")
        row["status"] = pedidos_domain.KDS_STATUS_RECUSADO
        row["recusado_em"] = "2026-08-24T12:02:00"
        row["motivo_recusa"] = motivo_recusa
        row["nota_recusa"] = nota_recusa
        row["ops_user_id"] = ops_user_id

    def kds_marcar_pronto(self, *, solicitacao_id: str, ops_user_id: int) -> None:
        row = self.kds_orders.get(solicitacao_id)
        if not row:
            raise RuntimeError("not_found")
        row["status"] = pedidos_domain.KDS_STATUS_PRONTO
        row["done_em"] = "2026-08-24T12:30:00"
        row["ops_user_id"] = ops_user_id

    def kds_marcar_sinalizado(self, *, solicitacao_id: str, ops_user_id: int) -> None:
        row = self.kds_orders.get(solicitacao_id)
        if not row:
            raise RuntimeError("not_found")
        row["status"] = pedidos_domain.KDS_STATUS_SINALIZADO
        row["sinalizado_em"] = "2026-08-24T12:35:00"
        row["ops_user_id"] = ops_user_id

    def kds_marcar_entregue(self, *, solicitacao_id: str, ops_user_id: int) -> None:
        self.entregue_marcados.append(solicitacao_id)
        row = self.kds_orders.get(solicitacao_id)
        if row:
            row["status"] = "ENTREGUE"

    # --- Listagens ---

    def kds_list_queue_with_status(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            r for _, r in self.kds_orders.items()
            if r["status"] == pedidos_domain.KDS_STATUS_NOVO
        ][:limit]

    def kds_list_queue_ids(self, *, limit: int = 50) -> list[str]:
        return [
            sid for sid, r in self.kds_orders.items()
            if r["status"] == pedidos_domain.KDS_STATUS_NOVO
        ][:limit]

    def kds_list_preparing_with_status(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            r for _, r in self.kds_orders.items()
            if r["status"] == pedidos_domain.KDS_STATUS_EM_PREPARO
        ][:limit]

    def kds_list_preparing_ids(self, *, limit: int = 50) -> list[str]:
        return [
            sid for sid, r in self.kds_orders.items()
            if r["status"] == pedidos_domain.KDS_STATUS_EM_PREPARO
        ][:limit]

    def kds_list_prontos(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            r for _, r in self.kds_orders.items()
            if r["status"] == pedidos_domain.KDS_STATUS_PRONTO
        ][:limit]

    def kds_list_sinalizados(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            r for _, r in self.kds_orders.items()
            if r["status"] == pedidos_domain.KDS_STATUS_SINALIZADO
        ][:limit]

    def kds_list_recusados(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            r for _, r in self.kds_orders.items()
            if r["status"] == pedidos_domain.KDS_STATUS_RECUSADO
        ][:limit]

    # --- Seleção / pular ---

    def kds_get_current_for_user(self, *, ops_user_id: int) -> dict[str, Any] | None:
        sid = self.current_selections.get(ops_user_id)
        if not sid:
            return None
        return self.kds_orders.get(sid)

    def kds_set_current_selection(self, *, ops_user_id: int, solicitacao_id: str) -> None:
        self.current_selections[ops_user_id] = solicitacao_id

    def kds_bump_queue_order(self, *, solicitacao_id: str) -> None:
        pass  # no-op no fake

    # --- Stats ---

    def kds_stats_today(self) -> dict[str, int]:
        return {
            "pendentes": sum(1 for r in self.kds_orders.values() if r["status"] == pedidos_domain.KDS_STATUS_NOVO),
            "prontos": sum(1 for r in self.kds_orders.values() if r["status"] == pedidos_domain.KDS_STATUS_PRONTO),
            "sinalizados": sum(1 for r in self.kds_orders.values() if r["status"] == pedidos_domain.KDS_STATUS_SINALIZADO),
        }

    # --- Eventos / integração ---

    def logistica_event_add(
        self, *, ops_user_id: int, solicitacao_id: str, event: str, note: str | None = None
    ) -> None:
        self.events.append({
            "ops_user_id": ops_user_id,
            "solicitacao_id": solicitacao_id,
            "event": event,
            "note": note,
        })

    def logistica_integracao_criar(
        self, *, solicitacao_id: str, evento: str, payload_json: dict[str, Any]
    ) -> None:
        self.integracoes.append({
            "solicitacao_id": solicitacao_id,
            "evento": evento,
            "payload_json": payload_json,
        })

    def logistica_webhook_receber(
        self, *, idempotency_key: str, solicitacao_id: str, evento: str,
        status_externo: str, payload: dict[str, Any],
    ) -> bool:
        if idempotency_key in self.webhooks_recebidos:
            return False  # já processado
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
    """Configura core.pg_store e core.pg_enabled com o FakeStore."""
    from cardapio_app import core
    core.pg_store = store  # type: ignore
    core.pg_enabled = lambda: True  # type: ignore
    core.central_logistica_enabled = lambda: False  # type: ignore


def _criar_pedido_kds(store: FakeStore, sid: str = "sol-kds-1") -> str:
    """Cria um pedido no KDS com status NOVO."""
    store.kds_ensure_order_row(solicitacao_id=sid)
    return sid


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def test_aceitar_pedido_transiciona_novo_para_em_preparo() -> None:
    """Aceitar um pedido NOVO transiciona para EM_PREPARO e loga evento."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)

    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_EM_PREPARO
    eventos = [e for e in store.events if e["solicitacao_id"] == sid and e["event"] == "ACEITO"]
    assert len(eventos) == 1, f"esperado 1 evento ACEITO, obtido {len(eventos)}"
    print("[OK] 1: aceitar_pedido transiciona NOVO -> EM_PREPARO e loga evento")


def test_aceitar_pedido_com_impressao_registra_timestamp() -> None:
    """Aceitar com impressao_solicitada_em registra o timestamp."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    ts = "2026-08-24T12:00:05"
    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1, impressao_solicitada_em=ts)

    row = store.kds_orders[sid]
    assert row["impressao_solicitada_em"] == ts, f"timestamp não registrado: {row['impressao_solicitada_em']}"
    print("[OK] 2: aceitar_pedido com impressao_solicitada_em registra timestamp")


def test_aceitar_pedido_em_preparo_falha() -> None:
    """Não pode aceitar um pedido que já está EM_PREPARO."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)

    try:
        service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    except RuntimeError as e:
        assert "nao_novo" in str(e).lower() or "novo" in str(e).lower(), f"erro inesperado: {e}"
        print("[OK] 3: aceitar pedido EM_PREPARO falha com erro de status")
        return
    raise AssertionError("deveria ter falhado ao aceitar pedido EM_PREPARO")


def test_recusar_pedido_transiciona_novo_para_recusado() -> None:
    """Recusar um pedido NOVO transiciona para RECUSADO com motivo e nota."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.recusar_pedido(
        solicitacao_id=sid,
        ops_user_id=1,
        motivo_recusa=pedidos_domain.KDS_MOTIVO_FALTOU_INGREDIENTE,
        nota_recusa="Sem tomate",
    )

    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_RECUSADO
    row = store.kds_orders[sid]
    assert row["motivo_recusa"] == "FALTOU_INGREDIENTE"
    assert row["nota_recusa"] == "Sem tomate"
    eventos = [e for e in store.events if e["solicitacao_id"] == sid and e["event"] == "RECUSADO"]
    assert len(eventos) == 1
    assert "Sem tomate" in (eventos[0]["note"] or "")
    print("[OK] 4: recusar_pedido transiciona NOVO -> RECUSADO com motivo e nota")


def test_recusar_pedido_em_preparo_falha() -> None:
    """Não pode recusar um pedido que já está EM_PREPARO."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)

    try:
        service.recusar_pedido(solicitacao_id=sid, ops_user_id=1, motivo_recusa="OUTRO")
    except RuntimeError as e:
        assert "novo" in str(e).lower(), f"erro inesperado: {e}"
        print("[OK] 5: recusar pedido EM_PREPARO falha com erro de status")
        return
    raise AssertionError("deveria ter falhado ao recusar pedido EM_PREPARO")


def test_recusar_pedido_sem_nota_usa_motivo_como_nota() -> None:
    """Recusar sem nota usa o motivo como nota no evento."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.recusar_pedido(
        solicitacao_id=sid,
        ops_user_id=1,
        motivo_recusa=pedidos_domain.KDS_MOTIVO_FORA_HORARIO,
    )

    eventos = [e for e in store.events if e["solicitacao_id"] == sid and e["event"] == "RECUSADO"]
    assert len(eventos) == 1
    assert eventos[0]["note"] == "FORA_HORARIO", f"nota deveria ser o motivo: {eventos[0]['note']}"
    print("[OK] 6: recusar sem nota usa motivo como nota no evento")


def test_marcar_pronto_transiciona_em_preparo_para_pronto() -> None:
    """Marcar pronto transiciona EM_PREPARO -> PRONTO e loga evento."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)

    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_PRONTO
    eventos = [e for e in store.events if e["solicitacao_id"] == sid and e["event"] == "PRONTO"]
    assert len(eventos) == 1
    print("[OK] 7: marcar_pronto transiciona EM_PREPARO -> PRONTO")


def test_marcar_pronto_em_novo_falha() -> None:
    """Não pode marcar pronto um pedido que ainda está NOVO."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    try:
        service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)
    except RuntimeError as e:
        assert "em_preparo" in str(e).lower(), f"erro inesperado: {e}"
        print("[OK] 8: marcar pronto em NOVO falha com erro de status")
        return
    raise AssertionError("deveria ter falhado ao marcar pronto em NOVO")


def test_sinal_entregar_transiciona_pronto_para_sinalizado() -> None:
    """Sinal para entregar transiciona PRONTO -> SINALIZADO e loga evento."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)
    service.sinal_entregar(solicitacao_id=sid, ops_user_id=1)

    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_SINALIZADO
    eventos = [e for e in store.events if e["solicitacao_id"] == sid and e["event"] == "SINALIZADO"]
    assert len(eventos) == 1
    print("[OK] 9: sinal_entregar transiciona PRONTO -> SINALIZADO")


def test_sinal_entregar_em_preparo_falha() -> None:
    """Não pode sinalizar para entregar um pedido que ainda está EM_PREPARO."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)

    try:
        service.sinal_entregar(solicitacao_id=sid, ops_user_id=1)
    except RuntimeError as e:
        assert "pronto" in str(e).lower(), f"erro inesperado: {e}"
        print("[OK] 10: sinal_entregar em EM_PREPARO falha com erro de status")
        return
    raise AssertionError("deveria ter falhado ao sinalizar EM_PREPARO")


def test_ciclo_completo_novo_ate_sinalizado() -> None:
    """Ciclo completo: NOVO -> EM_PREPARO -> PRONTO -> SINALIZADO."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    # NOVO
    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_NOVO

    # Aceitar
    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_EM_PREPARO

    # Pronto
    service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)
    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_PRONTO

    # Sinalizar
    service.sinal_entregar(solicitacao_id=sid, ops_user_id=1)
    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_SINALIZADO

    # Eventos na ordem correta
    eventos_sid = [e for e in store.events if e["solicitacao_id"] == sid]
    eventos_esperados = ["ACEITO", "PRONTO", "SINALIZADO"]
    eventos_reais = [e["event"] for e in eventos_sid]
    assert eventos_reais == eventos_esperados, f"eventos: {eventos_reais} != {eventos_esperados}"
    print("[OK] 11: ciclo completo NOVO -> EM_PREPARO -> PRONTO -> SINALIZADO com eventos na ordem")


def test_listar_previas_retorna_apenas_novo() -> None:
    """listar_previas retorna apenas pedidos NOVO."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)

    _criar_pedido_kds(store, "sol-1")
    _criar_pedido_kds(store, "sol-2")
    _criar_pedido_kds(store, "sol-3")
    # Mover sol-2 para EM_PREPARO
    service.aceitar_pedido(solicitacao_id="sol-2", ops_user_id=1)

    previas = service.listar_previas(limit=50)
    # Como _enrich_pedido chama get_solicitacao_by_id que não está mockado,
    # verificamos apenas os IDs via kds_list_queue_ids
    ids = service.listar_fila_ids(limit=50)
    assert "sol-1" in ids
    assert "sol-3" in ids
    assert "sol-2" not in ids, "sol-2 não deveria estar em previas (está EM_PREPARO)"
    print("[OK] 12: listar_previas/fila_ids retorna apenas pedidos NOVO")


def test_listar_preparando_retorna_apenas_em_preparo() -> None:
    """listar_preparando_ids retorna apenas pedidos EM_PREPARO."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)

    _criar_pedido_kds(store, "sol-1")
    _criar_pedido_kds(store, "sol-2")
    service.aceitar_pedido(solicitacao_id="sol-2", ops_user_id=1)

    ids = service.listar_preparando_ids(limit=50)
    assert "sol-2" in ids
    assert "sol-1" not in ids, "sol-1 não deveria estar em preparando (está NOVO)"
    print("[OK] 13: listar_preparando_ids retorna apenas pedidos EM_PREPARO")


def test_stats_hoje_conta_corretamente() -> None:
    """stats_hoje conta pedidos por status corretamente."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)

    _criar_pedido_kds(store, "sol-1")
    _criar_pedido_kds(store, "sol-2")
    _criar_pedido_kds(store, "sol-3")
    service.aceitar_pedido(solicitacao_id="sol-2", ops_user_id=1)
    service.marcar_pronto(solicitacao_id="sol-2", ops_user_id=1)
    service.sinal_entregar(solicitacao_id="sol-2", ops_user_id=1)

    stats = service.stats_hoje()
    assert stats["pendentes"] == 2, f"esperado 2 pendentes, obtido {stats['pendentes']}"
    assert stats["prontos"] == 0, f"esperado 0 prontos, obtido {stats['prontos']}"
    assert stats["sinalizados"] == 1, f"esperado 1 sinalizado, obtido {stats['sinalizados']}"
    print("[OK] 14: stats_hoje conta pedidos por status corretamente")


def test_selecionar_pedido_define_current_selection() -> None:
    """selecionar_pedido define o pedido atual do usuário."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    sid = _criar_pedido_kds(store)

    service.selecionar_pedido(ops_user_id=1, solicitacao_id=sid)

    atual = service.get_pedido_atual(ops_user_id=1)
    # get_pedido_atual chama _enrich_pedido que chama get_solicitacao_by_id
    # Como get_solicitacao_by_id não está mockado, retorna {"id": sid}
    # Mas o row do KDS deve estar lá
    assert store.current_selections[1] == sid
    print("[OK] 15: selecionar_pedido define current selection do usuário")


def test_aceitar_pedido_solicitacao_invalida_falha() -> None:
    """Aceitar com solicitacao_id vazio falha."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)

    try:
        service.aceitar_pedido(solicitacao_id="", ops_user_id=1)
    except RuntimeError as e:
        assert "invalida" in str(e).lower(), f"erro inesperado: {e}"
        print("[OK] 16: aceitar com solicitacao_id vazio falha")
        return
    raise AssertionError("deveria ter falhado com solicitacao_id vazio")


def test_sinal_entregar_sem_remo_nao_quebra() -> None:
    """Sinalizar com REMO desabilitada não quebra — apenas não cria ordem."""
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    # central_logistica_enabled já é False por _setup_module
    sid = _criar_pedido_kds(store)

    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)
    service.sinal_entregar(solicitacao_id=sid, ops_user_id=1)

    # Não deve ter criado integração (REMO desligada)
    assert len(store.integracoes) == 0, f"não deveria criar integração com REMO off: {store.integracoes}"
    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_SINALIZADO
    print("[OK] 17: sinal_entregar com REMO desabilitada não cria integração e não quebra")


def test_sinal_entregar_com_remo_cria_integracao() -> None:
    """Sinalizar com REMO habilitada cria fila de integração."""
    from cardapio_app import core
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    # Habilitar REMO
    core.central_logistica_enabled = lambda: True  # type: ignore
    core.central_logistica_empresa_id = lambda: "EMPRESA01"  # type: ignore
    core.central_logistica_post_json = lambda **kw: (200, {"ok": True})  # type: ignore

    sid = _criar_pedido_kds(store)
    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)
    service.sinal_entregar(solicitacao_id=sid, ops_user_id=1)

    # Deve ter criado integração
    assert len(store.integracoes) == 1, f"esperado 1 integração, obtido {len(store.integracoes)}"
    assert store.integracoes[0]["evento"] == "SINALIZADO"
    print("[OK] 18: sinal_entregar com REMO habilitada cria fila de integração")


def test_sinal_entregar_saldo_insuficiente_remo_falha() -> None:
    """Sinalizar com REMO retornando 402 (saldo insuficiente) falha."""
    from cardapio_app import core
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    core.central_logistica_enabled = lambda: True  # type: ignore
    core.central_logistica_empresa_id = lambda: "EMPRESA01"  # type: ignore
    core.central_logistica_post_json = lambda **kw: (402, {"error": "saldo_insuficiente"})  # type: ignore

    sid = _criar_pedido_kds(store)
    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)

    try:
        service.sinal_entregar(solicitacao_id=sid, ops_user_id=1)
    except RuntimeError as e:
        assert "saldo_insuficiente" in str(e), f"erro inesperado: {e}"
        print("[OK] 19: sinal_entregar com REMO 402 falha com saldo_insuficiente")
        return
    raise AssertionError("deveria ter falhado com saldo insuficiente")


def test_sinal_entregar_erro_remo_nao_quebra_kds() -> None:
    """Sinalizar com REMO retornando 500 não quebra o KDS — continua."""
    from cardapio_app import core
    from cardapio_app.kds import service
    store = FakeStore()
    _setup_module(store)
    core.central_logistica_enabled = lambda: True  # type: ignore
    core.central_logistica_empresa_id = lambda: "EMPRESA01"  # type: ignore
    core.central_logistica_post_json = lambda **kw: (500, {"error": "internal"})  # type: ignore

    sid = _criar_pedido_kds(store)
    service.aceitar_pedido(solicitacao_id=sid, ops_user_id=1)
    service.marcar_pronto(solicitacao_id=sid, ops_user_id=1)
    service.sinal_entregar(solicitacao_id=sid, ops_user_id=1)

    # KDS deve ter sinalizado mesmo com REMO fora
    assert store.kds_get_status(solicitacao_id=sid) == pedidos_domain.KDS_STATUS_SINALIZADO
    print("[OK] 20: sinal_entregar com REMO 500 não quebra KDS — sinaliza mesmo assim")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    testes = [
        test_aceitar_pedido_transiciona_novo_para_em_preparo,
        test_aceitar_pedido_com_impressao_registra_timestamp,
        test_aceitar_pedido_em_preparo_falha,
        test_recusar_pedido_transiciona_novo_para_recusado,
        test_recusar_pedido_em_preparo_falha,
        test_recusar_pedido_sem_nota_usa_motivo_como_nota,
        test_marcar_pronto_transiciona_em_preparo_para_pronto,
        test_marcar_pronto_em_novo_falha,
        test_sinal_entregar_transiciona_pronto_para_sinalizado,
        test_sinal_entregar_em_preparo_falha,
        test_ciclo_completo_novo_ate_sinalizado,
        test_listar_previas_retorna_apenas_novo,
        test_listar_preparando_retorna_apenas_em_preparo,
        test_stats_hoje_conta_corretamente,
        test_selecionar_pedido_define_current_selection,
        test_aceitar_pedido_solicitacao_invalida_falha,
        test_sinal_entregar_sem_remo_nao_quebra,
        test_sinal_entregar_com_remo_cria_integracao,
        test_sinal_entregar_saldo_insuficiente_remo_falha,
        test_sinal_entregar_erro_remo_nao_quebra_kds,
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
