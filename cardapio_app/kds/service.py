from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import core
from ..pedidos import domain
from ..pedidos.service import get_solicitacao_by_id


def _kds_item_to_dict(kds_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(kds_item.get("status") or "").strip(),
        "created_em": kds_item.get("created_em"),
        "started_em": kds_item.get("started_em"),
        "done_em": kds_item.get("done_em"),
        "sinalizado_em": kds_item.get("sinalizado_em"),
        "impressao_solicitada_em": kds_item.get("impressao_solicitada_em"),
        "recusado_em": kds_item.get("recusado_em"),
        "motivo_recusa": kds_item.get("motivo_recusa"),
        "nota_recusa": kds_item.get("nota_recusa"),
        "ops_user_id": kds_item.get("ops_user_id"),
    }


def _enrich_pedido(*, kds_item: dict[str, Any]) -> dict[str, Any]:
    sid = str(kds_item.get("solicitacao_id") or "").strip()
    pedido = get_solicitacao_by_id(solicitacao_id=sid) if sid else None
    if not isinstance(pedido, dict):
        pedido = {"id": sid}
    pedido["kds"] = _kds_item_to_dict(kds_item)
    return pedido


# ------------------------------------------------------------------
# Pedido atual e listagens
# ------------------------------------------------------------------


def get_pedido_atual(*, ops_user_id: int) -> dict[str, Any] | None:
    if not core.pg_enabled():
        return None

    try:
        row = core.pg_store.kds_get_current_for_user(ops_user_id=int(ops_user_id))
    except Exception:
        row = None

    if not isinstance(row, dict):
        return None

    return _enrich_pedido(kds_item=row)


def _listar_por_lista(*, kds_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_enrich_pedido(kds_item=item) for item in (kds_list or []) if str(item.get("solicitacao_id") or "").strip()]


def listar_previas(*, limit: int = 20) -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    try:
        kds_list = core.pg_store.kds_list_queue_with_status(limit=int(limit))
    except Exception:
        kds_list = []
    return _listar_por_lista(kds_list=kds_list)


def listar_fila_ids(*, limit: int = 50) -> list[str]:
    if not core.pg_enabled():
        return []
    try:
        return core.pg_store.kds_list_queue_ids(limit=int(limit))
    except Exception:
        return []


# alias legado
listar_previas_ids = listar_fila_ids


def listar_preparando_ids(*, limit: int = 50) -> list[str]:
    if not core.pg_enabled():
        return []
    try:
        return core.pg_store.kds_list_preparing_ids(limit=int(limit))
    except Exception:
        return []


def listar_preparando_pedidos(*, limit: int = 20) -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    try:
        kds_list = core.pg_store.kds_list_preparing_with_status(limit=int(limit))
    except Exception:
        kds_list = []
    return _listar_por_lista(kds_list=kds_list)


def listar_prontos(*, limit: int = 20) -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    try:
        kds_list = core.pg_store.kds_list_prontos(limit=int(limit))
    except Exception:
        kds_list = []
    return _listar_por_lista(kds_list=kds_list)


def listar_sinalizados(*, limit: int = 20) -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    try:
        kds_list = core.pg_store.kds_list_sinalizados(limit=int(limit))
    except Exception:
        kds_list = []
    return _listar_por_lista(kds_list=kds_list)


def listar_recusados(*, limit: int = 20) -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    try:
        kds_list = core.pg_store.kds_list_recusados(limit=int(limit))
    except Exception:
        kds_list = []
    return _listar_por_lista(kds_list=kds_list)


# alias legado: listar_fila_pedidos passa a listar prévias
listar_fila_pedidos = listar_previas


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


# ------------------------------------------------------------------
# Transições de estado
# ------------------------------------------------------------------


def _log_event(*, ops_user_id: int, solicitacao_id: str, event: str, note: str | None = None) -> None:
    try:
        core.pg_store.logistica_event_add(
            ops_user_id=int(ops_user_id),
            solicitacao_id=str(solicitacao_id or "").strip(),
            event=str(event or "").strip().upper(),
            note=str(note or "").strip() or None,
        )
    except Exception:
        pass


def _validar_status(solicitacao_id: str, esperado: str) -> None:
    atual = core.pg_store.kds_get_status(solicitacao_id=solicitacao_id)
    if atual != esperado:
        raise RuntimeError(f"pedido_nao_{esperado.lower().replace(' ', '_')}")


def aceitar_pedido(*, solicitacao_id: str, ops_user_id: int, impressao_solicitada_em: str | None = None) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    sid = str(solicitacao_id or "").strip()
    uid = int(ops_user_id)
    if not sid:
        raise RuntimeError("solicitacao_invalida")

    _validar_status(sid, domain.KDS_STATUS_NOVO)

    try:
        core.pg_store.kds_aceitar_pedido(
            solicitacao_id=sid,
            ops_user_id=uid,
            impressao_solicitada_em=impressao_solicitada_em,
        )
    except Exception as e:
        raise RuntimeError(f"falha_ao_aceitar: {e}") from e

    _log_event(ops_user_id=uid, solicitacao_id=sid, event="ACEITO")


# alias legado
preparar_pedido = aceitar_pedido


def recusar_pedido(
    *,
    solicitacao_id: str,
    ops_user_id: int,
    motivo_recusa: str,
    nota_recusa: str | None = None,
) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    sid = str(solicitacao_id or "").strip()
    uid = int(ops_user_id)
    motivo = str(motivo_recusa or "").strip() or domain.KDS_MOTIVO_OUTRO
    nota = str(nota_recusa or "").strip() or None
    if not sid:
        raise RuntimeError("solicitacao_invalida")

    _validar_status(sid, domain.KDS_STATUS_NOVO)

    try:
        core.pg_store.kds_recusar_pedido(
            solicitacao_id=sid,
            ops_user_id=uid,
            motivo_recusa=motivo,
            nota_recusa=nota,
        )
    except Exception as e:
        raise RuntimeError(f"falha_ao_recusar: {e}") from e

    _log_event(ops_user_id=uid, solicitacao_id=sid, event="RECUSADO", note=nota or motivo)


def marcar_pronto(*, solicitacao_id: str, ops_user_id: int) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    sid = str(solicitacao_id or "").strip()
    uid = int(ops_user_id)
    if not sid:
        raise RuntimeError("solicitacao_invalida")

    _validar_status(sid, domain.KDS_STATUS_EM_PREPARO)

    try:
        core.pg_store.kds_marcar_pronto(solicitacao_id=sid, ops_user_id=uid)
    except Exception as e:
        raise RuntimeError(f"falha_ao_marcar_pronto: {e}") from e

    _log_event(ops_user_id=uid, solicitacao_id=sid, event="PRONTO")


def sinal_entregar(*, solicitacao_id: str, ops_user_id: int) -> None:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    sid = str(solicitacao_id or "").strip()
    uid = int(ops_user_id)
    if not sid:
        raise RuntimeError("solicitacao_invalida")

    _validar_status(sid, domain.KDS_STATUS_PRONTO)

    # Integração com Central Logística: criar ordem e debitar carteira
    remo_status, remo_body = _criar_ordem_na_remo(solicitacao_id=sid)
    if remo_status == 402:
        raise RuntimeError("saldo_insuficiente_carteira_remo")
    if remo_status >= 400:
        # Não quebra o KDS se a REMO estiver fora; continua com fila local
        pass

    try:
        core.pg_store.kds_marcar_sinalizado(solicitacao_id=sid, ops_user_id=uid)
    except Exception as e:
        raise RuntimeError(f"falha_ao_sinalizar: {e}") from e

    _log_event(ops_user_id=uid, solicitacao_id=sid, event="SINALIZADO")

    # Cria fila de integração com a Central Logística
    try:
        _criar_integracao_logistica(solicitacao_id=sid, ops_user_id=uid)
    except Exception:
        # Não pode quebrar a transição do KDS
        pass


def _criar_ordem_na_remo(*, solicitacao_id: str) -> tuple[int, Any]:
    if not core.central_logistica_enabled():
        return 0, None

    sid = str(solicitacao_id or "").strip()
    pedido = get_solicitacao_by_id(solicitacao_id=sid) or {}
    record = pedido.get("record") or pedido
    if not isinstance(record, dict):
        record = {}

    entrega = record.get("entrega") or {}
    if not isinstance(entrega, dict):
        entrega = {}

    taxa = float(entrega.get("taxa") or record.get("taxa_entrega") or 0.0)

    payload = {
        "empresa_id": core.central_logistica_empresa_id(),
        "solicitacao_id": sid,
        "taxa": taxa,
        "payload": {
            "cliente_nome": str(record.get("cliente_nome") or "").strip(),
            "cliente_whatsapp": str(record.get("cliente_whatsapp") or "").strip(),
            "tipo_entrega": str(record.get("tipo_entrega") or record.get("kind") or "").strip().upper(),
            "taxa": taxa,
            "total": float(record.get("total") or record.get("valor") or 0.0),
        },
    }

    status, body = core.central_logistica_post_json(path="/api/v1/ordens", payload=payload)
    return status, body


def _criar_integracao_logistica(*, solicitacao_id: str, ops_user_id: int) -> None:
    if not core.central_logistica_enabled():
        return

    sid = str(solicitacao_id or "").strip()
    pedido = get_solicitacao_by_id(solicitacao_id=sid) or {}

    record = pedido.get("record") or pedido
    if not isinstance(record, dict):
        record = {}

    cliente = record.get("cliente") or {}
    if not isinstance(cliente, dict):
        cliente = {}

    entrega = record.get("entrega") or {}
    if not isinstance(entrega, dict):
        entrega = {}

    endereco = entrega.get("endereco") or {}
    if not isinstance(endereco, dict):
        endereco = {}

    itens = record.get("itens") or record.get("items") or []
    if not isinstance(itens, list):
        itens = []

    payload = {
        "empresa_id": core.central_logistica_empresa_id(),
        "solicitacao_id": sid,
        "origem": "DoRafa_KDS",
        "evento": "SINALIZADO",
        "sinalizado_em": datetime.now().isoformat(timespec="seconds"),
        "cliente": {
            "nome": str(cliente.get("nome") or pedido.get("cliente_nome") or "").strip(),
            "whatsapp": str(cliente.get("whatsapp") or pedido.get("cliente_whatsapp") or "").strip(),
        },
        "entrega": {
            "tipo": str(record.get("tipo_entrega") or record.get("kind") or "").strip().upper(),
            "endereco": {
                "rua": str(endereco.get("rua") or "").strip(),
                "numero": str(endereco.get("numero") or "").strip(),
                "bairro": str(endereco.get("bairro") or "").strip(),
                "cidade": str(endereco.get("cidade") or "").strip(),
                "referencia": str(endereco.get("referencia") or "").strip(),
                "maps_url": str(endereco.get("maps_url") or "").strip(),
            },
            "taxa": float(entrega.get("taxa") or record.get("taxa_entrega") or 0.0),
        },
        "pedido": {
            "itens": itens,
            "total": float(record.get("total") or record.get("valor") or 0.0),
            "observacoes": str(record.get("observacoes") or "").strip(),
        },
    }

    core.pg_store.logistica_integracao_criar(
        solicitacao_id=sid,
        evento="SINALIZADO",
        payload_json=payload,
    )


def stats_hoje() -> dict[str, int]:
    if not core.pg_enabled():
        return {"pendentes": 0, "prontos": 0, "sinalizados": 0}
    try:
        return core.pg_store.kds_stats_today()
    except Exception:
        return {"pendentes": 0, "prontos": 0, "sinalizados": 0}
