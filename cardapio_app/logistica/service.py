from __future__ import annotations

from typing import Any

from .. import core
from ..pedidos.service import get_solicitacao_by_id


def listar_prontos() -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    out: list[dict[str, Any]] = []
    try:
        ready = core.pg_store.logistica_list_ready_orders()
    except Exception:
        ready = []

    for rec in ready:
        if not isinstance(rec, dict):
            continue
        sid = str(rec.get("solicitacao_id") or "").strip()
        flag = str(rec.get("flag") or "").strip().upper()
        pedido = get_solicitacao_by_id(solicitacao_id=str(sid))
        if isinstance(pedido, dict):
            merged = dict(pedido)
            if flag:
                merged["logistica_flag"] = flag
            out.append(merged)
        else:
            row = {"id": str(sid)}
            if flag:
                row["logistica_flag"] = flag
            out.append(row)
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
    sids: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sid = str(it.get("solicitacao_id") or "").strip()
        if sid:
            sids.append(sid)
        rec = get_solicitacao_by_id(solicitacao_id=sid) or {"id": sid}
        if not isinstance(rec, dict):
            rec = {"id": sid}
        merged = dict(it)
        merged["pedido"] = rec
        enriched.append(merged)

    try:
        flags = core.pg_store.logistica_flags_get_map(solicitacao_ids=sids)
    except Exception:
        flags = {}

    if isinstance(flags, dict) and flags:
        for it in enriched:
            sid = str((it or {}).get("solicitacao_id") or "").strip()
            fl = str(flags.get(sid) or "").strip().upper()
            if not sid or not fl:
                continue
            p = (it or {}).get("pedido")
            if isinstance(p, dict):
                p2 = dict(p)
                p2["logistica_flag"] = fl
                it["pedido"] = p2

    out["items"] = enriched

    total = len(enriched)
    entregues = 0
    pendentes = 0
    for it in enriched:
        delivered_em = (it or {}).get("delivered_em")
        if delivered_em:
            entregues += 1
        else:
            pendentes += 1
    out["resumo"] = {
        "total": total,
        "entregues": entregues,
        "pendentes": pendentes,
    }
    return out


def corrida_add(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_add_order(ops_user_id=int(ops_user_id), solicitacao_id=str(solicitacao_id or "").strip())


def corrida_remove(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_remove_order(ops_user_id=int(ops_user_id), solicitacao_id=str(solicitacao_id or "").strip())


def corrida_devolver(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_return_order(ops_user_id=int(ops_user_id), solicitacao_id=str(solicitacao_id or "").strip())


def corrida_marcar_entregue(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_mark_delivered(ops_user_id=int(ops_user_id), solicitacao_id=str(solicitacao_id or "").strip())


def corrida_nova(*, ops_user_id: int) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_new_draft(ops_user_id=int(ops_user_id))


def corrida_start(*, ops_user_id: int) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_start(ops_user_id=int(ops_user_id))


def corrida_finish(*, ops_user_id: int) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    return core.pg_store.logistica_run_finish(ops_user_id=int(ops_user_id))


def pedido_sinalizar(*, ops_user_id: int, solicitacao_id: str, note: str | None = None) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    core.pg_store.logistica_flag_signal(ops_user_id=int(ops_user_id), solicitacao_id=str(solicitacao_id or "").strip(), note=note)
    core.pg_store.logistica_event_add(
        ops_user_id=int(ops_user_id),
        solicitacao_id=str(solicitacao_id or "").strip(),
        event="SINALIZADO",
        note=note,
    )


def pedido_cancelar_definitivo(*, ops_user_id: int, solicitacao_id: str, note: str | None = None) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    core.pg_store.logistica_cancel_definitivo(
        ops_user_id=int(ops_user_id),
        solicitacao_id=str(solicitacao_id or "").strip(),
        note=note,
    )


def pedido_dessinalizar(*, ops_user_id: int, solicitacao_id: str, note: str | None = None) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    core.pg_store.logistica_flag_clear(
        ops_user_id=int(ops_user_id),
        solicitacao_id=str(solicitacao_id or "").strip(),
        note=note,
    )


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
    tipo_raw = str(pedido.get("tipo_entrega") or pedido.get("kind") or "").strip()
    tipo_up = tipo_raw.upper().replace(" ", "_")
    if tipo_up in ("DELIVERY", "ENTREGA"):
        tipo = "DELIVERY"
    elif tipo_up in ("RETIRADA", "RETIRAR", "PICKUP"):
        tipo = "RETIRADA"
    else:
        tipo = tipo_raw

    link = base + "/entregas"
    msg_lines: list[str] = []
    msg_lines.append("ALERTA: PEDIDO PRONTO")
    if cliente:
        msg_lines.append(f"Cliente: {cliente}")
    if tipo:
        msg_lines.append(f"Tipo: {tipo}")
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
