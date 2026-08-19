from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from .. import core
from ..pedidos.service import get_solicitacao_by_id


logger = logging.getLogger(__name__)

_PROCESSADOR_ATIVO = False
_PROCESSADOR_THREAD: threading.Thread | None = None


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


# ------------------------------------------------------------------
# INTEGRAÇÃO COM CENTRAL LOGÍSTICA EXTERNA
# ------------------------------------------------------------------


MAX_TENTATIVAS = 3


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _backoff(tentativas: int) -> str:
    """Retorna o próximo timestamp de tentativa com base no número de tentativas."""
    now = datetime.now()
    if tentativas <= 1:
        delta = timedelta(seconds=10)
    elif tentativas == 2:
        delta = timedelta(seconds=30)
    else:
        delta = timedelta(minutes=2)
    return (now + delta).isoformat(timespec="seconds")


def _idempotency_key(*, empresa_id: str, solicitacao_id: str, evento: str) -> str:
    return f"{empresa_id}:{solicitacao_id}:{evento.upper()}"


def _enviar_para_central(*, payload: dict[str, Any], idempotency_key: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    url = str(core.central_logistica_webhook_url() or "").strip()
    if not url:
        return False, None, "url_nao_configurada"

    api_key = str(core.central_logistica_api_key() or "").strip()
    timeout = core.central_logistica_timeout_seconds()

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Idempotency-Key": idempotency_key,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") if resp.read() else ""
            if not raw:
                return True, None, None
            try:
                j = json.loads(raw)
                return True, j if isinstance(j, dict) else None, None
            except Exception:
                return True, None, None
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
        except Exception:
            raw = ""
        return False, None, f"HTTP {e.code}: {raw[:200]}"
    except urllib.error.URLError as e:
        return False, None, f"URL error: {e}"
    except Exception as e:
        return False, None, str(e)[:500]


def processar_pendentes(*, max_tentativas: int = MAX_TENTATIVAS) -> int:
    """Processa um lote de integrações pendentes. Retorna quantos registros tentou enviar."""
    if not core.pg_enabled():
        return 0
    if not core.central_logistica_enabled():
        return 0

    count = 0
    while True:
        reg = core.pg_store.logistica_integracao_pegar_proximo_pendente(
            max_tentativas=max_tentativas,
            for_update=True,
        )
        if not reg:
            break
        count += 1
        _processar_um(reg=reg, max_tentativas=max_tentativas)

    return count


def _processar_um(*, reg: dict[str, Any], max_tentativas: int = MAX_TENTATIVAS) -> None:
    if not isinstance(reg, dict):
        return

    integracao_id = int(reg.get("id") or 0)
    if not integracao_id:
        return

    payload = reg.get("payload_json") or {}
    if not isinstance(payload, dict):
        payload = {}

    empresa_id = str(payload.get("empresa_id") or core.central_logistica_empresa_id() or "EMPRESA01").strip()
    solicitacao_id = str(payload.get("solicitacao_id") or reg.get("solicitacao_id") or "").strip()
    evento = str(reg.get("evento") or "SINALIZADO").strip()
    idempotency_key = _idempotency_key(
        empresa_id=empresa_id,
        solicitacao_id=solicitacao_id,
        evento=evento,
    )

    try:
        core.pg_store.logistica_integracao_marcar_enviando(integracao_id=integracao_id)
    except Exception:
        return

    try:
        ok, resposta, erro = _enviar_para_central(payload=payload, idempotency_key=idempotency_key)
    except Exception as e:
        ok = False
        resposta = None
        erro = str(e)[:500]

    if ok:
        protocolo_externo = resposta.get("protocolo") if isinstance(resposta, dict) else None
        try:
            core.pg_store.logistica_integracao_marcar_enviado(
                integracao_id=integracao_id,
                protocolo_externo=str(protocolo_externo) if protocolo_externo else None,
                resposta_json=resposta,
            )
        except Exception:
            pass
        return

    try:
        tentativas = int(reg.get("tentativas") or 0) + 1
    except Exception:
        tentativas = 1

    proxima_tentativa = _backoff(tentativas=tentativas)
    if tentativas >= max_tentativas:
        proxima_tentativa = None

    try:
        core.pg_store.logistica_integracao_marcar_erro(
            integracao_id=integracao_id,
            ultimo_erro=str(erro or "erro_desconhecido").strip(),
            proxima_tentativa_em=proxima_tentativa,
            max_tentativas=max_tentativas,
        )
    except Exception:
        pass


def reprocessar_integracao(*, integracao_id: int) -> dict[str, Any]:
    if not core.pg_enabled():
        raise RuntimeError("pg_disabled")
    core.pg_store.logistica_integracao_reprocessar(integracao_id=int(integracao_id))
    return {"ok": True}


def listar_integracoes(*, limit: int = 100) -> list[dict[str, Any]]:
    if not core.pg_enabled():
        return []
    return core.pg_store.logistica_integracao_listar_pendentes(limit=limit)


def iniciar_processador_background(intervalo_segundos: int = 30) -> None:
    """Inicia uma thread única que consulta a fila periodicamente."""
    global _PROCESSADOR_ATIVO, _PROCESSADOR_THREAD

    if _PROCESSADOR_ATIVO:
        return

    _PROCESSADOR_ATIVO = True

    def _loop() -> None:
        while _PROCESSADOR_ATIVO:
            try:
                if core.pg_enabled() and core.central_logistica_enabled():
                    processar_pendentes()
            except Exception:
                logger.exception("logistica_processador - erro no loop")
            time.sleep(max(5, int(intervalo_segundos)))

    _PROCESSADOR_THREAD = threading.Thread(target=_loop, name="kds_logistica_processor", daemon=True)
    _PROCESSADOR_THREAD.start()


def parar_processador_background() -> None:
    global _PROCESSADOR_ATIVO
    _PROCESSADOR_ATIVO = False
