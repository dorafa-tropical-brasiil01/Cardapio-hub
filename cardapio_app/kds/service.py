from __future__ import annotations

from typing import Any

from .. import core
from ..pedidos import domain
from ..pedidos.service import get_solicitacao_by_id


def get_pedido_atual(*, ops_user_id: int) -> dict[str, Any] | None:
    if not core.pg_enabled():
        return None

    try:
        row = core.pg_store.kds_get_current_for_user(ops_user_id=int(ops_user_id))
    except Exception:
        row = None

    if not isinstance(row, dict):
        return None

    solicitacao_id = str(row.get("solicitacao_id") or "").strip()
    if not solicitacao_id:
        return None

    pedido = get_solicitacao_by_id(solicitacao_id=solicitacao_id)
    if not isinstance(pedido, dict):
        pedido = {"id": solicitacao_id}

    pedido["kds"] = {
        "status": str(row.get("status") or "").strip() or domain.KDS_STATUS_AGUARDANDO,
        "started_em": row.get("started_em"),
        "done_em": row.get("done_em"),
        "ops_user_id": row.get("ops_user_id"),
    }
    return pedido


def listar_fila_ids(*, limit: int = 50) -> list[str]:
    if not core.pg_enabled():
        return []
    try:
        return core.pg_store.kds_list_queue_ids(limit=int(limit))
    except Exception:
        return []


def listar_fila_pedidos(*, limit: int = 20) -> list[dict[str, Any]]:
    ids = listar_fila_ids(limit=int(limit))
    out: list[dict[str, Any]] = []
    for sid in ids:
        pedido = get_solicitacao_by_id(solicitacao_id=str(sid))
        if isinstance(pedido, dict):
            out.append(pedido)
        else:
            out.append({"id": str(sid)})
    return out


def pular_pedido(*, solicitacao_id: str) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    core.pg_store.kds_bump_queue_order(solicitacao_id=sid)


def selecionar_pedido(*, ops_user_id: int, solicitacao_id: str) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    if not uid or not sid:
        return
    core.pg_store.kds_set_current_selection(ops_user_id=uid, solicitacao_id=sid)


def preparar_pedido(*, solicitacao_id: str, ops_user_id: int) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    core.pg_store.kds_start_order(solicitacao_id=str(solicitacao_id or "").strip(), ops_user_id=int(ops_user_id))


def marcar_pronto(*, solicitacao_id: str, ops_user_id: int) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    core.pg_store.kds_mark_done(solicitacao_id=str(solicitacao_id or "").strip(), ops_user_id=int(ops_user_id))


def stats_hoje() -> dict[str, int]:
    if not core.pg_enabled():
        return {"pendentes": 0, "concluidos": 0}
    try:
        return core.pg_store.kds_stats_today()
    except Exception:
        return {"pendentes": 0, "concluidos": 0}
