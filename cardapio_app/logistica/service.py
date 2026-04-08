from __future__ import annotations

from typing import Any

from .. import core
from ..pedidos.service import get_solicitacao_by_id


def listar_prontos() -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    out: list[dict[str, Any]] = []
    try:
        ids = core.pg_store.logistica_list_ready_order_ids()
    except Exception:
        ids = []

    for sid in ids:
        pedido = get_solicitacao_by_id(solicitacao_id=str(sid))
        if isinstance(pedido, dict):
            out.append(pedido)
        else:
            out.append({"id": str(sid)})
    return out


def obter_corrida_atual(*, ops_user_id: int) -> dict[str, Any]:
    if not core.pg_enabled():
        return {"items": []}
    try:
        run = core.pg_store.logistica_get_or_create_draft_run(ops_user_id=int(ops_user_id))
    except Exception:
        return {"items": []}

    out = dict(run) if isinstance(run, dict) else {"items": []}
    items = out.get("items")
    if not isinstance(items, list):
        items = []

    enriched: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sid = str(it.get("solicitacao_id") or "").strip()
        rec = get_solicitacao_by_id(solicitacao_id=sid) or {"id": sid}
        if not isinstance(rec, dict):
            rec = {"id": sid}
        merged = dict(it)
        merged["pedido"] = rec
        enriched.append(merged)

    out["items"] = enriched
    return out


def corrida_add(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_add_order(ops_user_id=int(ops_user_id), solicitacao_id=str(solicitacao_id or "").strip())


def corrida_remove(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_remove_order(ops_user_id=int(ops_user_id), solicitacao_id=str(solicitacao_id or "").strip())


def corrida_start(*, ops_user_id: int) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_start(ops_user_id=int(ops_user_id))


def corrida_finish(*, ops_user_id: int) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_finish(ops_user_id=int(ops_user_id))


def notificar_entregadores_pedido_pronto(*, solicitacao_id: str, base_url: str) -> None:
    if not core.pg_enabled():
        return
    if not core.telegram_bot_enabled():
        return

    sid = str(solicitacao_id or "").strip()
    if not sid:
        return

    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return

    try:
        users = core.pg_store.list_ops_users_by_role(role="LOGISTICA")
    except Exception:
        users = []
    if not users:
        return

    pedido = get_solicitacao_by_id(solicitacao_id=sid) or {}
    cliente = str(pedido.get("cliente_nome") or "").strip()
    tipo = str(pedido.get("tipo_entrega") or pedido.get("kind") or "").strip()

    link = base + "/entregas"
    msg_lines: list[str] = []
    msg_lines.append("PEDIDO PRONTO PARA ENTREGA")
    msg_lines.append(f"Pedido: {sid}")
    if cliente:
        msg_lines.append(f"Cliente: {cliente}")
    if tipo:
        msg_lines.append(f"Tipo: {tipo}")
    msg_lines.append("")
    msg_lines.append("Acesse o painel:")
    msg_lines.append(link)
    msg = "\n".join(msg_lines).strip()

    for u in users:
        chat_id = str((u or {}).get("telegram") or "").strip()
        if not chat_id:
            continue
        if not chat_id.lstrip("-").isdigit():
            continue
        try:
            core.telegram_send_message_to(chat_id=chat_id, text=msg)
        except Exception:
            continue
