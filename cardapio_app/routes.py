from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import secrets
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, make_response, request, send_from_directory
from werkzeug.utils import secure_filename

from . import core, rate_limit
from .ops_auth.store import create_password_hash
from .pagamento_online import domain as pay_domain
from .pagamento_online import service as pay_service
from .pedidos import domain as pedidos_domain

logger = logging.getLogger(__name__)

#: Limites de requisição dos endpoints públicos (chave, limite por minuto).
#: Ver cardapio_app/rate_limit.py para a ressalva de contador por processo.
RATE_LIMIT_CRIAR_PEDIDO = 5
RATE_LIMIT_GERAR_PAGAMENTO = 3
RATE_LIMIT_LER_PEDIDO = 30
RATE_LIMIT_LER_STATUS = 60

#: Validade da resposta cacheada por idempotency_key.
IDEMPOTENCY_TTL_SECONDS = 600

IDEMPOTENCY_SCOPE_CRIAR = "criar_pedido"
IDEMPOTENCY_SCOPE_PAGAR = "gerar_pagamento"


def _client_ip() -> str:
    fwd = str(request.headers.get("X-Forwarded-For") or "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    return str(request.remote_addr or "").strip() or "desconhecido"


def _rate_limited(*, key: str, limit: int) -> Any:
    """Retorna a resposta 429 quando o limite é excedido, ou None."""
    allowed, retry_after = rate_limit.check(key=key, limit=limit)
    if allowed:
        return None
    return jsonify({"error": "rate_limit_exceeded", "retry_after": retry_after}), 429


def _request_hash(payload: Any) -> str:
    try:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        canonical = repr(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotency_key_from(body: Any) -> str:
    """Chave de idempotência informada pelo cliente. Opcional por contrato."""
    if not isinstance(body, dict):
        return ""
    return str(body.get("idempotency_key") or "").strip()[:64]


def _idempotency_lookup(*, scope: str, key: str, payload_hash: str) -> Any:
    """Resposta cacheada, conflito de chave, ou None se não houver registro."""
    if not key or not core.pg_enabled():
        return None

    try:
        cached = core.pg_store.idempotency_get(scope=scope, idempotency_key=key)
    except Exception:
        logger.exception("idempotency_get - falha scope=%s", scope)
        return None

    if not isinstance(cached, dict):
        return None

    if str(cached.get("request_hash") or "") != payload_hash:
        return jsonify({"error": "idempotency_key_conflito"}), 400

    return jsonify(cached.get("response_json") or {}), int(cached.get("status_code") or 200)


def _idempotency_store(
    *,
    scope: str,
    key: str,
    payload_hash: str,
    response: dict[str, Any],
    status_code: int,
    solicitacao_id: str | None = None,
) -> None:
    if not key or not core.pg_enabled():
        return
    try:
        core.pg_store.idempotency_put(
            scope=scope,
            idempotency_key=key,
            request_hash=payload_hash,
            response_json=response,
            status_code=status_code,
            ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
            solicitacao_id=solicitacao_id,
        )
    except Exception:
        logger.exception("idempotency_put - falha scope=%s", scope)


def _resposta_publica_pedido(rec: dict[str, Any]) -> dict[str, Any]:
    """Monta a resposta pública de um pedido com pagamento online.

    O objeto `pagamento` passa pela allowlist de campos públicos, de modo que
    provider_transaction_id, claimed_by_pdv_id, applied_sale_id e afins nunca
    chegam ao cliente.
    """
    out: dict[str, Any] = {
        "id": rec.get("id"),
        "token": rec.get("access_token"),
        "status": rec.get("status"),
        "pagamento_online": bool(rec.get("pagamento_online")),
        "subtotal": rec.get("subtotal_estimado"),
        "taxa_entrega": rec.get("taxa_entrega"),
        "total": rec.get("total_estimado"),
        "payment_window_expires_at": rec.get("payment_window_expires_at"),
        "payment_attempts": rec.get("payment_attempts"),
        "pagamento": pay_domain.filtrar_snapshot_publico(rec.get("pagamento")),
        "itens": rec.get("itens"),
        "cliente_nome": rec.get("cliente_nome"),
        "cliente_whatsapp": rec.get("cliente_whatsapp"),
        "tipo_entrega": str(rec.get("tipo_entrega") or "").strip().upper(),
        "endereco": rec.get("endereco"),
        "pagamento_preferido": rec.get("pagamento_preferido"),
    }
    out.update(pay_service.estado_publico(rec))
    return out


def register_routes(app: Flask) -> None:
    def _ctx() -> core.AppContext:
        return app.config["CARDAPIO_CTX"]

    @app.get("/api/_diag")
    def api_diag():
        return jsonify(
            {
                "database_url_configured": core.database_url_configured(),
                "pg_store_loaded": core.pg_store is not None,
                "pg_enabled": core.pg_enabled(),
                "telegram_enabled": core.telegram_enabled(),
                "pg_store_import_error": core.pg_store_import_error(),
            }
        )

    @app.post("/api/pdv/promo/emitir")
    def api_pdv_promo_emitir():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.promo_enabled():
            return jsonify({"error": "promo_desabilitada"}), 404
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        if not core.promo_hmac_secret():
            return jsonify({"error": "promo_secret_nao_configurado"}), 500

        data = request.get_json(silent=True) or {}
        try:
            sale_id = int(data.get("sale_id"))
        except Exception:
            return jsonify({"error": "sale_id_invalido"}), 400

        cliente_nome = str(data.get("cliente_nome") or "").strip()
        cliente_whatsapp = str(data.get("cliente_whatsapp") or "").strip()
        campaign_name = str(data.get("campaign_name") or data.get("promo_campaign_name") or "").strip() or None
        produtos = data.get("produtos")
        if isinstance(produtos, list):
            produtos_txt = ", ".join([str(x or "").strip() for x in produtos if str(x or "").strip()])
        else:
            produtos_txt = str(produtos or "").strip()
        numero_sorteio = str(data.get("numero_sorteio") or "").strip()

        if not cliente_nome or not cliente_whatsapp:
            return jsonify({"error": "dados_cliente_obrigatorios"}), 400
        if not core.is_valid_whatsapp(cliente_whatsapp):
            return jsonify({"error": "whatsapp_invalido"}), 400
        if not produtos_txt:
            return jsonify({"error": "produtos_obrigatorio"}), 400
        if not numero_sorteio:
            return jsonify({"error": "numero_sorteio_obrigatorio"}), 400

        try:
            existing = core.pg_store.get_promo_inscricao_by_sale_id(sale_id=sale_id)
        except Exception:
            existing = None

        if isinstance(existing, dict) and str(existing.get("token") or "").strip():
            tok = str(existing.get("token") or "").strip()
            url = core.promo_base_url() + core.promo_path() + "?t=" + urllib.parse.quote(tok)
            return jsonify({"ok": True, "token": tok, "url": url, "numero_sorteio": existing.get("numero_sorteio")})

        installation_id = str(request.headers.get("X-PDV-ID") or "").strip() or None
        last_err: Exception | None = None
        tok = ""
        for _ in range(6):
            tok = core.promo_make_short_token()
            try:
                core.pg_store.upsert_promo_inscricao_emitida(
                    sale_id=sale_id,
                    campaign_name=campaign_name,
                    cliente_nome=cliente_nome,
                    cliente_whatsapp=cliente_whatsapp,
                    produtos=produtos_txt,
                    numero_sorteio=numero_sorteio,
                    token=tok,
                    pdv_installation_id=installation_id,
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                continue

        if last_err is not None:
            try:
                existing = core.pg_store.get_promo_inscricao_by_sale_id(sale_id=sale_id)
            except Exception:
                existing = None
            if isinstance(existing, dict) and str(existing.get("token") or "").strip():
                tok = str(existing.get("token") or "").strip()
            else:
                return jsonify({"error": "falha_persistir"}), 500

        url = core.promo_base_url() + core.promo_path() + "?t=" + urllib.parse.quote(tok)
        return jsonify({"ok": True, "token": tok, "url": url, "numero_sorteio": numero_sorteio})

    @app.get("/promocao")
    def promocao_page():
        if not core.promo_enabled():
            return make_response("not_found", 404)

        published = core.read_catalogo_publicado(_ctx())
        ui = published.get("ui") if isinstance(published, dict) else {}
        promo_title = core.promo_title_from_ui(ui)
        promo_img = core.normalize_asset_ref(_ctx(), ui.get("promoImage")) if isinstance(ui, dict) else ""
        promo_img_url = ""
        if promo_img:
            promo_img_url = promo_img + ("&" if "?" in promo_img else "?") + "v=" + urllib.parse.quote(uuid.uuid4().hex)
        promo_html = (
            "<div id=\"promo-img\" style=\"margin:12px 0 10px 0;\">"
            f"<img src=\"{promo_img_url}\" alt=\"Promoção\" style=\"width:100%;height:auto;border-radius:12px;display:block;\">"
            "</div>"
            if promo_img
            else ""
        )

        consent = json.dumps(core.promo_consent_text(), ensure_ascii=False)
        html = (
            "<!doctype html>"
            "<html lang=\"pt-BR\">"
            "<head>"
            "<meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Promoção</title>"
            "<style>body{font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:0 auto;padding:18px;}h1{font-size:22px;margin:0 0 10px 0;}button{font-size:16px;padding:12px 16px;border:0;border-radius:10px;background:#111;color:#fff;}button:disabled{opacity:.6;}#msg{margin-top:14px;white-space:pre-line;}.muted{opacity:.78;}#promo-img{margin:0 0 10px 0;}.box{background:rgba(255,255,255,0.65);border:1px solid rgba(0,0,0,0.08);border-radius:12px;padding:12px;margin:10px 0;}#client{margin-top:10px;}#promoTitle{font-weight:900;font-size:20px;margin:0 0 8px 0;}</style>"
            "</head>"
            "<body>"
            + "<div id=\"promoTitle\">Promoção: <span id=\"promoTitleText\"></span></div>"
            + promo_html
            + "<div class=\"box muted\" id=\"promoExplain\">"
            + "Este QR code é de uso único e confirma a participação do cliente na promoção. "
            + "O cadastro é automático: fez o pedido no cardápio online, pagou e gerou o QR code. "
            + "Agora basta ler o QR e confirmar. Não é possível transferir ou usar o mesmo QR em mais de um celular."
            + "</div>"
            + "<div class=\"box\" id=\"client\" style=\"display:none\">"
            + "<div><b>Nome:</b> <span id=\"clientName\"></span></div>"
            + "<div style=\"margin-top:6px\"><b>Contato/WhatsApp:</b> <span id=\"clientPhone\"></span></div>"
            + "</div>"
            + "<p id=\"consent\"></p>"
            + "<button id=\"btn\">Confirmar participação</button>"
            + "<div id=\"msg\"></div>"
            + "<script>"
            + "const consentText="
            + consent
            + ";"
            + "document.getElementById('consent').innerText=consentText;"
            + "const params=new URLSearchParams(window.location.search);"
            + "const t=params.get('t')||'';"
            + "const btn=document.getElementById('btn');"
            + "const msg=document.getElementById('msg');"
            + "const clientBox=document.getElementById('client');"
            + "const clientNameEl=document.getElementById('clientName');"
            + "const clientPhoneEl=document.getElementById('clientPhone');"
            + "const promoTitleText=document.getElementById('promoTitleText');"
            + "if(!t){btn.disabled=true;msg.innerText='Token ausente.';}"
            + "async function loadInfo(){"
            + "  if(!t) return;"
            + "  try {"
            + "    const resp=await fetch('/api/promo/info?t='+encodeURIComponent(t),{method:'GET'});"
            + "    const j=await resp.json().catch(()=>({}));"
            + "    if(!resp.ok||!j||j.ok!==true) return;"
            + "    if(promoTitleText) promoTitleText.innerText=(j.promo_title||''||'');"
            + "    if(j.nome){clientNameEl.innerText=j.nome;}"
            + "    if(j.whatsapp){clientPhoneEl.innerText=j.whatsapp;}"
            + "    if((j.nome||j.whatsapp) && clientBox){clientBox.style.display='block';}"
            + "  } catch(e){}"
            + "}"
            + "loadInfo();"
            + "btn.addEventListener('click', async ()=>{"
            + "  btn.disabled=true; msg.innerText='Confirmando...';"
            + "  try {"
            + "    const resp=await fetch('/api/promo/confirmar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t})});"
            + "    const j=await resp.json().catch(()=>({}));"
            + "    if(!resp.ok||!j||j.ok!==true){msg.innerText=(j&&j.error)?('Erro: '+j.error):'Falha ao confirmar.';btn.disabled=false;return;}"
            + "    let out = (j && j.already_confirmed===true) ? 'QR code já cadastrado.\\nEsse comprovante já confirmou a participação.' : 'Participação confirmada.';"
            + "    if(j.numero_sorteio){out+='\\nNúmero do sorteio: '+j.numero_sorteio;}"
            + "    msg.innerText=out;"
            + "    if(j && j.already_confirmed===true){btn.disabled=true;}"
            + "  } catch(e){ msg.innerText='Falha ao confirmar.'; btn.disabled=false; }"
            + "});"
            + "</script>"
            + "</body>"
            + "</html>"
        )
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/status/<access_token>")
    def status_page(access_token: str):
        if not core.pg_enabled():
            return make_response("Serviço indisponível", 503)

        tok = str(access_token or "").strip()
        if not tok:
            return make_response("Token ausente", 404)

        try:
            rec = core.pg_store.get_solicitacao_by_access_token(access_token=tok)
        except Exception:
            return make_response("Pedido não encontrado", 404)

        if not isinstance(rec, dict):
            return make_response("Pedido não encontrado", 404)

        solicitacao_id = str(rec.get("id") or "").strip()
        if not solicitacao_id:
            return make_response("Pedido não encontrado", 404)

        tipo_entrega = str(rec.get("tipo_entrega") or "").strip().upper()
        if tipo_entrega not in ("DELIVERY", "RETIRADA"):
            tipo_entrega = "DELIVERY"

        total_etapas = 6 if tipo_entrega == "DELIVERY" else 4

        html = (
            "<!doctype html>"
            "<html lang=\"pt-BR\">"
            "<head>"
            "<meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Status do Pedido</title>"
            "<style>"
            "body{font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:0 auto;padding:18px;background:#f5f5f5;color:#333;}"
            "h1{font-size:22px;margin:0 0 16px 0;color:#0a5c2f;}"
            ".card{background:#fff;border-radius:12px;padding:20px;margin:10px 0;box-shadow:0 2px 8px rgba(0,0,0,0.1);}"
            ".status-badge{display:inline-block;padding:8px 16px;border-radius:20px;font-weight:bold;font-size:14px;margin:8px 0;}"
            ".status-enviado{background:#e3f2fd;color:#1565c0;}"
            ".status-aceito{background:#fff3e0;color:#e65100;}"
            ".status-preparando{background:#fff9c4;color:#f57f17;}"
            ".status-pronto{background:#c8e6c9;color:#2e7d32;}"
            ".status-em_entrega{background:#e1bee7;color:#6a1b9a;}"
            ".status-entregue{background:#c8e6c9;color:#1b5e20;}"
            ".message{margin:12px 0;font-size:15px;line-height:1.4;}"
            ".muted{opacity:.6;font-size:13px;}"
            ".loading{text-align:center;padding:20px;}"
            ".error{color:#c62828;padding:12px;background:#ffebee;border-radius:8px;margin:10px 0;}"
            "</style>"
            "</head>"
            "<body>"
            "<h1>Status do Pedido</h1>"
            "<div class=\"card\">"
            "<div id=\"loading\" class=\"loading\">Carregando...</div>"
            "<div id=\"error\" class=\"error\" style=\"display:none\"></div>"
            "<div id=\"content\" style=\"display:none\">"
            "<div><strong>Tipo:</strong> <span id=\"tipoEntrega\"></span></div>"
            "<div style=\"margin-top:8px\"><strong>Status:</strong> <span id=\"statusBadge\" class=\"status-badge\"></span></div>"
            "<div class=\"message\" id=\"message\"></div>"
            "<div class=\"muted\" id=\"atualizadoEm\"></div>"
            "</div>"
            "</div>"
            "<script>"
            f"const SOLICITACAO_ID={json.dumps(solicitacao_id)};"
            f"const ACCESS_TOKEN={json.dumps(tok)};"
            f"const TIPO_ENTREGA={json.dumps(tipo_entrega)};"
            "const MENSAGENS={"
            "'ENVIADO':'Pedido enviado ao estabelecimento.',"
            "'ACEITO':'Pedido aceito pelo estabelecimento.',"
            "'PREPARANDO':'Pedido em preparo.',"
            "'PRONTO_DELIVERY':'Pedido pronto para entrega.',"
            "'PRONTO_RETIRADA':'Seu pedido está pronto para retirada no estabelecimento.',"
            "'EM_ENTREGA':'EM ROTA.',"
            "'ENTREGUE':'Seu pedido foi entregue.'"
            "};"
            "let timer=null;"
            "function renderStatus(data){"
            "  const loading=document.getElementById('loading');"
            "  const error=document.getElementById('error');"
            "  const content=document.getElementById('content');"
            "  if(!data){loading.style.display='none';error.style.display='block';error.innerText='Erro ao carregar status.';return;}"
            "  loading.style.display='none';error.style.display='none';content.style.display='block';"
            "  const tipo=data.tipo_entrega||TIPO_ENTREGA;"
            "  const status=data.status_publico||'';"
            "  document.getElementById('tipoEntrega').innerText=tipo==='DELIVERY'?'Delivery':'Retirada';"
            "  const badge=document.getElementById('statusBadge');"
            "  badge.className='status-badge status-'+status.toLowerCase().replace('_','-');"
            "  badge.innerText=status;"
            "  let msg=MENSAGENS[status];"
            "  if(status==='PRONTO'&&tipo==='RETIRADA')msg=MENSAGENS['PRONTO_RETIRADA'];"
            "  else if(status==='PRONTO'&&tipo==='DELIVERY')msg=MENSAGENS['PRONTO_DELIVERY'];"
            "  document.getElementById('message').innerText=msg||'';"
            "  const atualizado=data.atualizado_em||'';"
            "  if(atualizado){"
            "    const d=new Date(atualizado);"
            "    document.getElementById('atualizadoEm').innerText='Atualizado: '+d.toLocaleString('pt-BR');"
            "  }"
            "  return status;"
            "}"
            "async function fetchStatus(){"
            "  try{"
            "    const resp=await fetch('/api/public/pedidos/'+encodeURIComponent(SOLICITACAO_ID)+'/status?token='+encodeURIComponent(ACCESS_TOKEN));"
            "    if(resp.status===404||resp.status===401){"
            "      if(timer)clearInterval(timer);"
            "      document.getElementById('loading').style.display='none';"
            "      document.getElementById('error').style.display='block';"
            "      document.getElementById('error').innerText='Pedido não encontrado ou token inválido.';"
            "      return;"
            "    }"
            "    const data=await resp.json().catch(()=>null);"
            "    if(!data){return;}"
            "    const status=renderStatus(data);"
            "    if(status==='ENTREGUE'||status==='PRONTO'){"
            "      if(timer)clearInterval(timer);"
            "    }"
            "  }catch(e){}"
            "}"
            "fetchStatus();"
            "timer=setInterval(fetchStatus,2500);"
            "</script>"
            "</body>"
            "</html>"
        )
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/api/promo/info")
    def api_promo_info():
        if not core.promo_enabled():
            return jsonify({"error": "promo_desabilitada"}), 404
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        tok = str(request.args.get("t") or "").strip()
        if not tok:
            return jsonify({"error": "token_ausente"}), 400

        sale_id = core.promo_get_sale_id_from_token(tok)
        if sale_id is None:
            return jsonify({"error": "token_invalido"}), 400

        try:
            rec = core.pg_store.get_promo_inscricao_by_sale_id(sale_id=int(sale_id))
        except Exception:
            rec = None
        if not isinstance(rec, dict):
            return jsonify({"error": "nao_encontrado"}), 404

        published = core.read_catalogo_publicado(_ctx())
        ui = published.get("ui") if isinstance(published, dict) else {}
        promo_title = str(rec.get("campaign_name") or "").strip() or core.promo_title_from_ui(ui)

        return jsonify(
            {
                "ok": True,
                "promo_title": promo_title or "Promoção",
                "nome": core.mask_name(rec.get("cliente_nome")),
                "whatsapp": core.mask_phone(rec.get("cliente_whatsapp")),
            }
        )

    @app.post("/api/promo/confirmar")
    def api_promo_confirmar():
        if not core.promo_enabled():
            return jsonify({"error": "promo_desabilitada"}), 404
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        if not core.promo_hmac_secret():
            return jsonify({"error": "promo_secret_nao_configurado"}), 500

        data = request.get_json(silent=True) or {}
        tok = str(data.get("token") or "").strip()
        if not tok:
            return jsonify({"error": "token_ausente"}), 400

        sale_id: int | None = None
        if "." in tok:
            payload = core.promo_parse_and_verify_token(token=tok)
            if not isinstance(payload, dict):
                return jsonify({"error": "token_invalido"}), 400
            try:
                sale_id = int(payload.get("sale_id"))
            except Exception:
                return jsonify({"error": "token_invalido"}), 400
        else:
            try:
                rec0 = core.pg_store.get_promo_inscricao_by_token(token=tok)
            except Exception:
                rec0 = None
            if not isinstance(rec0, dict):
                return jsonify({"error": "token_invalido"}), 400
            try:
                sale_id = int(rec0.get("sale_id"))
            except Exception:
                return jsonify({"error": "token_invalido"}), 400

        try:
            rec = core.pg_store.confirm_promo_inscricao(sale_id=int(sale_id))
        except Exception:
            rec = None
        if not isinstance(rec, dict):
            return jsonify({"error": "nao_encontrado"}), 404

        already_confirmed = bool(rec.get("already_confirmed"))
        out: dict[str, Any] = {
            "ok": True,
            "already_confirmed": already_confirmed,
        }
        if not already_confirmed:
            out["numero_sorteio"] = rec.get("numero_sorteio")
        return jsonify(out)

    @app.get("/api/pdv/promo/inscricoes")
    def api_pdv_promo_inscricoes():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        ini = str(request.args.get("ini") or "").strip()
        fim = str(request.args.get("fim") or "").strip()
        if not ini or not fim:
            return jsonify({"error": "periodo_invalido"}), 400
        try:
            arr = core.pg_store.list_promo_inscricoes_periodo(ini=ini, fim=fim)
        except Exception:
            arr = []
        return jsonify({"ok": True, "inscricoes": arr})

    @app.get("/api/pdv/ping")
    def api_pdv_ping():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        return jsonify({"ok": True})

    @app.get("/api/pdv/ops_users")
    def api_pdv_ops_users_list():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        role = str(request.args.get("role") or "").strip().upper()
        if not role:
            return jsonify({"error": "role_ausente"}), 400
        try:
            arr = core.pg_store.list_ops_users_by_role(role=role)
        except Exception:
            arr = []

        safe: list[dict[str, Any]] = []
        for u in arr:
            if not isinstance(u, dict):
                continue
            safe.append(
                {
                    "id": u.get("id"),
                    "username": u.get("username"),
                    "role": u.get("role"),
                    "nome": u.get("nome"),
                    "telefone": u.get("telefone"),
                    "telegram": u.get("telegram"),
                    "endereco": u.get("endereco"),
                    "pix": u.get("pix"),
                    "ativo": u.get("ativo"),
                    "criado_em": u.get("criado_em"),
                    "atualizado_em": u.get("atualizado_em"),
                }
            )
        return jsonify({"ok": True, "users": safe})

    @app.post("/api/pdv/ops_users/upsert")
    def api_pdv_ops_users_upsert():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        body = request.get_json(silent=True) or {}
        username = str(body.get("username") or "").strip().lower()
        role = str(body.get("role") or "").strip().upper()
        if not username or not role:
            return jsonify({"error": "username_ou_role_invalido"}), 400

        telegram_raw = body.get("telegram")
        telegram: str | None
        if telegram_raw is None:
            telegram = None
        else:
            tg = str(telegram_raw or "").strip()
            if tg == "":
                telegram = None
            else:
                # chat_id numérico (string). Grupos podem ser negativos.
                if not tg.lstrip("-").isdigit():
                    return jsonify({"error": "telegram_chat_id_invalido"}), 400
                telegram = tg

        password = body.get("password")
        salt: str | None = None
        pwd_hash: str | None = None
        if password is not None:
            p = str(password)
            if len(p) < 4:
                return jsonify({"error": "password_curta"}), 400
            salt, pwd_hash = create_password_hash(p)

        try:
            rec = core.pg_store.upsert_ops_user(
                username=username,
                role=role,
                nome=(str(body.get("nome") or "").strip() or None),
                telefone=(str(body.get("telefone") or "").strip() or None),
                telegram=telegram,
                endereco=(str(body.get("endereco") or "").strip() or None),
                pix=(str(body.get("pix") or "").strip() or None),
                ativo=bool(body.get("ativo", True)),
                password_salt=salt,
                password_hash=pwd_hash,
            )
        except Exception:
            logger.exception("Falha ao upsert ops_user")
            return jsonify({"error": "internal_error"}), 500

        if not isinstance(rec, dict):
            # normalmente acontece quando tentou criar sem senha
            return jsonify({"error": "upsert_failed"}), 400

        return jsonify(
            {
                "ok": True,
                "user": {
                    "id": rec.get("id"),
                    "username": rec.get("username"),
                    "role": rec.get("role"),
                    "nome": rec.get("nome"),
                    "telefone": rec.get("telefone"),
                    "telegram": rec.get("telegram"),
                    "endereco": rec.get("endereco"),
                    "pix": rec.get("pix"),
                    "ativo": rec.get("ativo"),
                    "criado_em": rec.get("criado_em"),
                    "atualizado_em": rec.get("atualizado_em"),
                },
            }
        )

    @app.post("/api/pdv/ops_users/reset_password")
    def api_pdv_ops_users_reset_password():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        body = request.get_json(silent=True) or {}
        username = str(body.get("username") or "").strip().lower()
        password = str(body.get("password") or "")
        if not username:
            return jsonify({"error": "username_invalido"}), 400
        if len(password) < 4:
            return jsonify({"error": "password_curta"}), 400

        salt, pwd_hash = create_password_hash(password)
        try:
            rec = core.pg_store.update_ops_user(username=username, password_salt=salt, password_hash=pwd_hash)
        except Exception:
            logger.exception("Falha ao resetar senha ops_user")
            return jsonify({"error": "internal_error"}), 500
        if not isinstance(rec, dict):
            return jsonify({"error": "not_found"}), 404

        return jsonify({"ok": True})

    @app.get("/api/pdv/ops_metrics")
    def api_pdv_ops_metrics():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        ini = str(request.args.get("ini") or "").strip()
        fim = str(request.args.get("fim") or "").strip()
        if not ini or not fim:
            return jsonify({"error": "periodo_invalido"}), 400

        try:
            kds = core.pg_store.kds_list_done_periodo(ini=ini, fim=fim)
        except Exception:
            kds = []
        try:
            runs = core.pg_store.logistica_list_runs_periodo(ini=ini, fim=fim)
        except Exception:
            runs = []

        try:
            kds_by_user = core.pg_store.kds_summary_by_user_periodo(ini=ini, fim=fim)
        except Exception:
            kds_by_user = []
        try:
            runs_by_user = core.pg_store.logistica_summary_by_user_periodo(ini=ini, fim=fim)
        except Exception:
            runs_by_user = []

        return jsonify(
            {
                "ok": True,
                "kds": kds,
                "runs": runs,
                "kds_by_user": kds_by_user,
                "runs_by_user": runs_by_user,
            }
        )

    @app.get("/")
    def home():
        resp = make_response(send_from_directory(str(_ctx().bundle_dir), "index.html"))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.get("/manifest.json")
    def pwa_manifest():
        manifest = {
            "name": "DORAFA Tropical Brasil - Cardápio",
            "short_name": "DoRafa",
            "description": "Cardápio online DORAFA Tropical Brasil",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#d9f3a2",
            "theme_color": "#0a5c2f",
            "orientation": "portrait",
            "icons": [
                {"src": "/assets/LOGO_2.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/assets/LOGO_2.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        return jsonify(manifest)

    @app.get("/sw.js")
    def pwa_service_worker():
        js = r"""const CACHE_NAME = 'dorafa-cardapio-v1';
const OFFLINE_URL = '/offline.html';
const PRECACHE = [OFFLINE_URL, '/assets/app.css', '/assets/app.js'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (url.pathname === '/' || url.pathname === '/index.html') {
    event.respondWith(
      fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put('/', copy)).catch(() => {});
        return resp;
      }).catch(() => caches.match('/').then((r) => r || caches.match(OFFLINE_URL)))
    );
    return;
  }

  event.respondWith(
    fetch(req).then((resp) => {
      const copy = resp.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
      return resp;
    }).catch(() => caches.match(req).then((r) => r || caches.match(OFFLINE_URL)))
  );
});
"""
        resp = make_response(js, 200)
        resp.headers["Content-Type"] = "application/javascript"
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/offline.html")
    def pwa_offline():
        html = (
            '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1" />'
            '<title>Offline</title></head><body style="font-family:Arial;padding:20px;text-align:center;'
            'background:#d9f3a2;color:#0a5c2f;min-height:100vh;display:flex;align-items:center;'
            'justify-content:center;flex-direction:column">'
            '<h1>Sem conexão</h1>'
            '<p>O cardápio está offline. Verifique a internet e tente novamente.</p>'
            '<a href="/" style="display:inline-block;margin-top:20px;padding:12px 20px;'
            'background:#0a5c2f;color:#fff;text-decoration:none;border-radius:10px;">Tentar novamente</a>'
            '</body></html>'
        )
        resp = make_response(html, 200)
        resp.headers["Content-Type"] = "text/html"
        return resp

    @app.get("/index")
    def legacy_index_redirect():
        resp = make_response("", 302)
        resp.headers["Location"] = "/"
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.get("/produtos.json")
    def block_legacy_bundle_produtos_json():
        return make_response("not_found", 404)

    @app.get("/Cardapio_DoRafa_mesa_<mesa_txt>")
    def cardapio_mesa_comercial(mesa_txt: str):
        try:
            mesa_i = int(str(mesa_txt or "").strip())
        except Exception:
            mesa_i = 0

        if mesa_i < 1 or mesa_i > 30:
            return make_response("Mesa inválida", 404)

        mp = core.get_table_token_map(_ctx())
        token = str(mp.get(int(mesa_i)) or "").strip()
        if not token:
            return make_response("Mesa não cadastrada", 404)

        mesa_json = json.dumps(int(mesa_i), ensure_ascii=False)
        token_json = json.dumps(token, ensure_ascii=False)

        html = (
            "<!doctype html>"
            "<html lang=\"pt-BR\">"
            "<head>"
            "<meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Cardápio</title>"
            "</head>"
            "<body>"
            "<script>"
            "try { localStorage.setItem('cardapio.mesa.v1', String(" + mesa_json + ")); } catch (e) {}"
            "try { localStorage.setItem('cardapio.token.v1', String(" + token_json + ")); } catch (e) {}"
            "window.location.replace('/');"
            "</script>"
            "</body>"
            "</html>"
        )

        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/admin")
    def admin_page():
        if not core.admin_enabled():
            return make_response("not_found", 404)
        denied = core.require_localhost()
        if denied is not None:
            return denied
        resp = make_response(send_from_directory(str(_ctx().bundle_dir), "admin.html"))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.get("/api/data")
    def api_get_data():
        ctx = _ctx()
        if not core.admin_enabled():
            published = core.read_catalogo_publicado(ctx)
            if not isinstance(published, dict):
                published = {"categorias": [], "produtos": [], "ui": {}}

            pub_ui = published.get("ui") if isinstance(published.get("ui"), dict) else {}
            pub_horario = pub_ui.get("horario") if isinstance(pub_ui.get("horario"), dict) else {}
            pub_tz = str(pub_horario.get("tz") or "").strip() or None

            try:
                local = core.read_json_file(ctx.data_file)
            except FileNotFoundError:
                local = {"categorias": [], "produtos": [], "ui": {}}
            if not isinstance(local, dict):
                local = {"categorias": [], "produtos": [], "ui": {}}

            local_products = local.get("produtos") if isinstance(local.get("produtos"), list) else []
            meta_by_code: dict[str, dict[str, Any]] = {}
            for p in local_products:
                if not isinstance(p, dict):
                    continue
                keys = [p.get("pdvCode"), p.get("code"), p.get("id")]
                for k in keys:
                    kk = str(k or "").strip().upper()
                    if kk:
                        meta_by_code[kk] = p

            pub_products = published.get("produtos") if isinstance(published.get("produtos"), list) else []
            merged_products: list[dict[str, Any]] = []
            for p in pub_products:
                if not isinstance(p, dict):
                    continue
                code = str(p.get("id") or p.get("pdvCode") or p.get("code") or "").strip().upper()
                if not code:
                    continue
                meta = meta_by_code.get(code, {})
                out_p = dict(p)
                out_p["id"] = code
                out_p["pdvCode"] = code
                if meta.get("descricao") is not None and str(meta.get("descricao") or "").strip():
                    out_p["descricao"] = meta.get("descricao")
                if meta.get("imagem") is not None and str(meta.get("imagem") or "").strip():
                    out_p["imagem"] = core.normalize_asset_ref(ctx, meta.get("imagem"))
                if meta.get("queridinho") is not None:
                    out_p["queridinho"] = bool(meta.get("queridinho"))
                merged_products.append(out_p)

            merged_products = core.filter_catalogo_items_by_weekday(items=merged_products, tz_name=pub_tz)

            def _code_sort_key(x: dict[str, Any]) -> tuple[str, int, str]:
                code = str(x.get("pdvCode") or x.get("id") or x.get("code") or "").strip().upper()
                prefix_chars: list[str] = []
                num_chars: list[str] = []
                seen_digit = False
                for ch in code:
                    if not seen_digit and ch.isalpha():
                        prefix_chars.append(ch)
                        continue
                    if ch.isdigit():
                        seen_digit = True
                        num_chars.append(ch)
                        continue
                prefix = "".join(prefix_chars)
                try:
                    n = int("".join(num_chars)) if num_chars else 0
                except Exception:
                    n = 0
                return (prefix, n, code)

            merged_products = sorted(merged_products, key=_code_sort_key)

            cat_list = published.get("categorias") if isinstance(published.get("categorias"), list) else []
            cat_name_by_id: dict[str, str] = {}
            for c in cat_list:
                if not isinstance(c, dict):
                    continue
                cid = str(c.get("id") or "").strip()
                cnm = str(c.get("nome") or "").strip()
                if cid and cnm:
                    cat_name_by_id[cid] = cnm

            seen_cat_ids: set[str] = set()
            ordered_cats: list[dict[str, Any]] = []
            for mp in merged_products:
                cid = str(mp.get("categoriaId") or "").strip()
                if not cid or cid in seen_cat_ids:
                    continue
                seen_cat_ids.add(cid)
                ordered_cats.append({"id": cid, "nome": cat_name_by_id.get(cid) or cid})

            out = dict(published)
            out["produtos"] = merged_products
            if ordered_cats:
                out["categorias"] = ordered_cats
            ui = out.get("ui") if isinstance(out.get("ui"), dict) else {}
            if "logo" in ui:
                ui = dict(ui)
                ui["logo"] = core.normalize_asset_ref(ctx, ui.get("logo"))
            if "postOrderImage" in ui:
                ui = dict(ui)
                ui["postOrderImage"] = core.normalize_asset_ref(ctx, ui.get("postOrderImage"))
            if "promoImage" in ui:
                ui = dict(ui)
                ui["promoImage"] = core.normalize_asset_ref(ctx, ui.get("promoImage"))
            if "afterSendImage" in ui:
                ui = dict(ui)
                ui["afterSendImage"] = core.normalize_asset_ref(ctx, ui.get("afterSendImage"))
            if "posEnvioImagem" in ui:
                ui = dict(ui)
                ui["posEnvioImagem"] = core.normalize_asset_ref(ctx, ui.get("posEnvioImagem"))
            banner = ui.get("banner") if isinstance(ui.get("banner"), dict) else {}
            imgs = banner.get("imagens") if isinstance(banner.get("imagens"), list) else []
            banner = dict(banner)
            banner["imagens"] = [core.normalize_asset_ref(ctx, x) for x in imgs if core.normalize_asset_ref(ctx, x)]
            if ui:
                ui = dict(ui)
                ui["banner"] = banner
                out["ui"] = ui
            return jsonify(out)

        try:
            local = core.read_json_file(ctx.data_file)
        except FileNotFoundError:
            local = {"categorias": [], "produtos": [], "ui": {}}
        if not isinstance(local, dict):
            local = {"categorias": [], "produtos": [], "ui": {}}

        pdv_products, pdv_ui = core.fetch_pdv_payload()
        if not pdv_products:
            out2: dict[str, Any] = dict(local)
            out2["produtos"] = []
            return jsonify(out2)

        local_products = local.get("produtos") if isinstance(local.get("produtos"), list) else []
        meta_by_code: dict[str, dict[str, Any]] = {}
        for p in local_products:
            if not isinstance(p, dict):
                continue
            keys = [p.get("pdvCode"), p.get("code"), p.get("id")]
            for k in keys:
                kk = str(k or "").strip().upper()
                if kk:
                    meta_by_code[kk] = p

        merged_products2: list[dict[str, Any]] = []
        for p in pdv_products:
            if not isinstance(p, dict):
                continue
            if p.get("cardapio_show") is False:
                continue
            code = str(p.get("code") or "").strip().upper()
            if not code:
                continue

            meta = meta_by_code.get(code, {})
            featured_raw = p.get("cardapio_featured")
            featured = bool(featured_raw) if featured_raw is not None else bool(meta.get("queridinho"))
            img_raw = p.get("image")
            img = core.normalize_asset_ref(ctx, img_raw)
            merged_products2.append(
                {
                    "id": code,
                    "pdvCode": code,
                    "nome": str(p.get("name") or meta.get("nome") or "").strip() or code,
                    "preco": float(p.get("unit_price") or 0),
                    "ativo": bool(p.get("is_active")) if p.get("is_active") is not None else bool(meta.get("ativo", True)),
                    "categoriaId": "",
                    "descricao": meta.get("descricao") or "",
                    "imagem": img or core.normalize_asset_ref(ctx, meta.get("imagem")),
                    "queridinho": featured,
                    "cardapioSection": p.get("cardapio_section"),
                }
            )

        out2: dict[str, Any] = dict(local)

        section_order: list[str] = []
        section_id_by_name: dict[str, str] = {}
        for mp in merged_products2:
            sec_name = core.normalize_section_name(mp.get("cardapioSection"))
            if sec_name not in section_id_by_name:
                section_id_by_name[sec_name] = core.section_id_from_name(sec_name)
                section_order.append(sec_name)
            mp["categoriaId"] = section_id_by_name[sec_name]

        out_categories: list[dict[str, Any]] = []
        for nm in section_order:
            out_categories.append({"id": section_id_by_name.get(nm) or core.section_id_from_name(nm), "nome": nm})

        out2["categorias"] = out_categories
        out2["produtos"] = merged_products2
        if isinstance(pdv_ui, dict) and pdv_ui:
            local_ui = out2.get("ui") if isinstance(out2.get("ui"), dict) else {}
            merged_ui = dict(local_ui)
            merged_ui.update(pdv_ui)

            if "logo" in merged_ui:
                merged_ui["logo"] = core.normalize_asset_ref(ctx, merged_ui.get("logo"))
            if "postOrderImage" in merged_ui:
                merged_ui["postOrderImage"] = core.normalize_asset_ref(ctx, merged_ui.get("postOrderImage"))
            if "afterSendImage" in merged_ui:
                merged_ui["afterSendImage"] = core.normalize_asset_ref(ctx, merged_ui.get("afterSendImage"))
            if "posEnvioImagem" in merged_ui:
                merged_ui["posEnvioImagem"] = core.normalize_asset_ref(ctx, merged_ui.get("posEnvioImagem"))
            banner = merged_ui.get("banner") if isinstance(merged_ui.get("banner"), dict) else {}
            imgs = banner.get("imagens") if isinstance(banner.get("imagens"), list) else []
            banner = dict(banner)
            banner["imagens"] = [core.normalize_asset_ref(ctx, x) for x in imgs if core.normalize_asset_ref(ctx, x)]
            merged_ui["banner"] = banner

            out2["ui"] = merged_ui
        return jsonify(out2)

    @app.post("/api/data")
    def api_save_data():
        if not core.admin_enabled():
            return jsonify({"error": "forbidden"}), 403
        denied = core.require_localhost()
        if denied is not None:
            return denied

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "json_invalido"}), 400

        if not isinstance(data, dict):
            return jsonify({"error": "json_precisa_ser_objeto"}), 400

        if "produtos" not in data or "categorias" not in data:
            return jsonify({"error": "estrutura_incompleta"}), 400

        core.write_json_file(_ctx().data_file, data)
        return jsonify({"ok": True})

    @app.post("/api/pdv/assets/upload")
    def api_pdv_assets_upload():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        if core.database_url_configured() and not core.pg_enabled():
            return jsonify({"error": "postgres_indisponivel"}), 500

        ct = str(request.content_type or "").lower()
        if "multipart/form-data" not in ct:
            return jsonify({"error": "content_type_invalido"}), 400

        try:
            cl = int(request.content_length or 0)
        except Exception:
            cl = 0
        if cl <= 0:
            return jsonify({"error": "arquivo_nao_enviado"}), 400

        if "file" not in request.files:
            return jsonify({"error": "arquivo_nao_enviado"}), 400

        file = request.files["file"]
        if not file or not file.filename:
            return jsonify({"error": "arquivo_invalido"}), 400

        filename = secure_filename(file.filename)
        if not filename or not core.is_allowed_image_upload_filename(filename):
            return jsonify({"error": "extensao_nao_permitida"}), 400

        ctx = _ctx()
        ctx.assets_dir.mkdir(parents=True, exist_ok=True)
        target = (ctx.assets_dir / filename).resolve()

        base = target.stem
        ext = target.suffix
        i = 1
        while target.exists():
            target = (ctx.assets_dir / f"{base}_{i}{ext}").resolve()
            i += 1

        try:
            file.save(str(target))
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500

        if core.pg_enabled():
            try:
                raw = target.read_bytes()
                ct_guess, _ = mimetypes.guess_type(str(target.name))
                core.pg_store.save_asset(path=f"assets/{target.name}", content=raw, content_type=ct_guess)
            except Exception:
                logger.exception("Falha ao salvar asset no Postgres (path=%s)", f"assets/{target.name}")
                return jsonify({"error": "falha_ao_salvar_postgres"}), 500

        return jsonify({"ok": True, "path": f"assets/{target.name}"})

    @app.post("/api/pdv/catalogo/publicar")
    def api_pdv_publicar_catalogo():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        if core.database_url_configured() and not core.pg_enabled():
            return jsonify({"error": "postgres_indisponivel"}), 500

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        produtos = body.get("produtos")
        categorias = body.get("categorias")
        ui = body.get("ui")
        if not isinstance(produtos, list) or not isinstance(categorias, list):
            return jsonify({"error": "estrutura_incompleta"}), 400
        if ui is not None and not isinstance(ui, dict):
            return jsonify({"error": "ui_invalido"}), 400

        ctx = _ctx()
        if isinstance(ui, dict):
            ui = dict(ui)

            def _ui_first(*keys: str) -> Any:
                for k in keys:
                    if k in ui and str(ui.get(k) or "").strip():
                        return ui.get(k)
                return None

            post_img = _ui_first(
                "postOrderImage",
                "afterSendImage",
                "posEnvioImagem",
                "posPedidoImagem",
                "postPedidoImagem",
                "imagemPosPedido",
                "imagem_pos_pedido",
                "after_send_image",
                "after_send_img",
                "post_order_image",
                "post_order_img",
            )
            if post_img is not None:
                ui["postOrderImage"] = core.normalize_asset_ref(ctx, post_img)
                ui["afterSendImage"] = core.normalize_asset_ref(ctx, post_img)
                ui["posEnvioImagem"] = core.normalize_asset_ref(ctx, post_img)

            if "logo" in ui:
                ui["logo"] = core.normalize_asset_ref(ctx, ui.get("logo"))
            banner = ui.get("banner") if isinstance(ui.get("banner"), dict) else {}
            imgs = banner.get("imagens") if isinstance(banner.get("imagens"), list) else []
            banner = dict(banner)
            banner["imagens"] = [core.normalize_asset_ref(ctx, x) for x in imgs if core.normalize_asset_ref(ctx, x)]
            ui["banner"] = banner

        record = {
            "categorias": categorias,
            "produtos": produtos,
            "ui": ui if isinstance(ui, dict) else {},
            "publicado_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }

        try:
            core.save_catalogo_publicado(ctx=ctx, record=record)
        except Exception:
            logger.exception("Falha ao salvar catalogo_publicado no backend")
            return jsonify({"error": "falha_ao_salvar"}), 500

        return jsonify({"ok": True})

    @app.post("/api/pdv/solicitacoes/<solicitacao_id>/status")
    def api_pdv_set_status(solicitacao_id: str):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        pdv_status = str(body.get("pdv_status") or "").strip().upper()
        if pdv_status not in ("FECHADA", "FINALIZADA"):
            return jsonify({"error": "pdv_status_invalido"}), 400

        if core.pg_enabled():
            try:
                core.pg_store.update_solicitacao_status(solicitacao_id=solicitacao_id, pdv_status=pdv_status)
            except Exception:
                return jsonify({"error": "falha_ao_salvar"}), 500
        else:
            data = core.ensure_solicitacoes_file(_ctx())
            idx, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
            if s is None or idx is None:
                return jsonify({"error": "nao_encontrado"}), 404

            s["pdv_status"] = pdv_status
            s["pdv_status_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            data["solicitacoes"][idx] = s
            core.save_solicitacoes(_ctx(), data)
        return jsonify({"ok": True})

    @app.post("/api/solicitacoes/<solicitacao_id>/comprovante")
    def api_upload_comprovante(solicitacao_id: str):
        mesa = request.args.get("mesa")
        token = request.args.get("token")
        ok, err = core.validate_table_token(ctx=_ctx(), mesa=mesa, token=token)
        if not ok:
            return jsonify({"error": err}), 401

        data = core.ensure_solicitacoes_file(_ctx())
        idx, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None or idx is None:
            return jsonify({"error": "nao_encontrado"}), 404
        if int(s.get("mesa") or 0) != int(mesa):
            return jsonify({"error": "forbidden"}), 403

        cur_status = str(s.get("status") or "").upper()
        resposta = s.get("resposta") if isinstance(s.get("resposta"), dict) else None
        resp_tipo = str((resposta or {}).get("tipo") or "").upper()
        if cur_status != "RESPONDIDA" or resp_tipo != "ENVIAR_PIX":
            return jsonify({"error": "comprovante_indisponivel"}), 409

        if "file" not in request.files:
            return jsonify({"error": "arquivo_nao_enviado"}), 400

        file = request.files["file"]
        if not file or not file.filename:
            inferred_ext = core.infer_ext_from_mimetype(getattr(file, "mimetype", "") or "")
            if not inferred_ext:
                return jsonify({"error": "arquivo_invalido"}), 400
            filename = f"comprovante{inferred_ext}"
        else:
            filename = core.secure_filename(file.filename)
            if not filename:
                inferred_ext = core.infer_ext_from_mimetype(getattr(file, "mimetype", "") or "")
                if not inferred_ext:
                    return jsonify({"error": "arquivo_invalido"}), 400
                filename = f"comprovante{inferred_ext}"

        if not core.is_allowed_comprovante(filename):
            inferred_ext = core.infer_ext_from_mimetype(getattr(file, "mimetype", "") or "")
            if inferred_ext and inferred_ext in core.ALLOWED_COMPROVANTE_EXTENSIONS:
                filename = f"comprovante{inferred_ext}"
            else:
                return jsonify({"error": "extensao_nao_permitida"}), 400

        ext = Path(filename).suffix.lower()
        mesa_i = int(s.get("mesa") or 0)
        target_dir = core.comprovantes_pix_dir()

        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"PIX_MESA_{mesa_i}_{solicitacao_id}_{stamp}{ext}"
        out_path = (target_dir / out_name).resolve()

        try:
            file.save(str(out_path))
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500

        s["comprovante"] = {
            "filename": out_name,
            "path": str(out_path),
            "uploaded_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        if core.pg_enabled():
            try:
                core.pg_store.save_solicitacao(record=s)
            except Exception:
                return jsonify({"error": "falha_ao_salvar"}), 500
        else:
            data["solicitacoes"][idx] = s
            core.save_solicitacoes(_ctx(), data)

        return jsonify({"ok": True})

    @app.post("/api/upload")
    def api_upload():
        if not core.admin_enabled():
            return jsonify({"error": "forbidden"}), 403
        denied = core.require_localhost()
        if denied is not None:
            return denied

        if "file" not in request.files:
            return jsonify({"error": "arquivo_nao_enviado"}), 400

        file = request.files["file"]
        if not file or not file.filename:
            return jsonify({"error": "arquivo_invalido"}), 400

        filename = secure_filename(file.filename)
        if not core.is_allowed_image(filename):
            return jsonify({"error": "extensao_nao_permitida"}), 400

        ctx = _ctx()
        ctx.assets_dir.mkdir(parents=True, exist_ok=True)
        target = ctx.assets_dir / filename

        base = target.stem
        ext = target.suffix
        i = 1
        while target.exists():
            target = ctx.assets_dir / f"{base}_{i}{ext}"
            i += 1

        file.save(str(target))
        return jsonify({"ok": True, "path": f"assets/{target.name}"})

    @app.get("/assets/<path:filename>")
    def assets(filename: str):
        return core.serve_asset(_ctx(), filename)

    @app.get("/api/mesas")
    def api_get_mesas():
        if not core.admin_enabled():
            return jsonify({"error": "forbidden"}), 403
        denied = core.require_localhost()
        if denied is not None:
            return denied
        return jsonify(core.ensure_mesas_file(_ctx()))

    @app.post("/api/solicitacoes")
    def api_create_solicitacao():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        mesa = body.get("mesa")
        token = body.get("token")
        try:
            logger.info(
                "api_create_solicitacao (remote=%s mesa=%s token_prefix=%s)",
                (request.remote_addr or "").strip(),
                mesa,
                str(token or "")[:8],
            )
        except Exception:
            pass
        ok, err = core.validate_table_token(ctx=_ctx(), mesa=mesa, token=token)
        if not ok:
            return jsonify({"error": err}), 401

        pagamento = str(body.get("pagamento_preferido") or "").strip().upper()
        if pagamento not in core.ALLOWED_PAYMENT_METHODS:
            return jsonify({"error": "pagamento_invalido"}), 400

        cliente_nome = str(body.get("cliente_nome") or "").strip()
        if len(cliente_nome) > 60:
            return jsonify({"error": "cliente_nome_invalido"}), 400

        cliente_whatsapp = str(body.get("cliente_whatsapp") or "").strip()
        if cliente_whatsapp:
            if not core.is_valid_whatsapp(cliente_whatsapp):
                return jsonify({"error": "whatsapp_invalido"}), 400

        itens = body.get("itens")
        if not isinstance(itens, list) or len(itens) == 0:
            return jsonify({"error": "itens_obrigatorios"}), 400
        if len(itens) > 50:
            return jsonify({"error": "muitos_itens"}), 400

        norm_items: list[dict[str, Any]] = []
        for it in itens:
            if not isinstance(it, dict):
                return jsonify({"error": "item_invalido"}), 400
            code = str(it.get("product_code") or it.get("pdvCode") or "").strip().upper()
            if not code:
                return jsonify({"error": "product_code_obrigatorio"}), 400
            try:
                qty = float(it.get("qty") or it.get("quantidade") or 0)
            except Exception:
                qty = 0
            if qty <= 0:
                return jsonify({"error": "qty_invalida"}), 400
            norm_items.append(
                {
                    "product_code": code,
                    "nome": str(it.get("nome") or "").strip(),
                    "qty": qty,
                }
            )

        total_estimado = body.get("total_estimado")
        try:
            total_estimado_f = float(total_estimado) if total_estimado is not None else None
        except Exception:
            total_estimado_f = None

        solicitacao_id = uuid.uuid4().hex
        rec: dict[str, Any] = {
            "id": solicitacao_id,
            "mesa": int(mesa),
            "status": "PENDENTE",
            "pagamento_preferido": pagamento,
            "cliente_nome": cliente_nome or None,
            "cliente_whatsapp": cliente_whatsapp or None,
            "itens": norm_items,
            "total_estimado": total_estimado_f,
            "criado_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "atendida_em": None,
            "respondida_em": None,
            "pdv_status": None,
            "pdv_status_em": None,
            "pdv_id": None,
            "operator_user_id": None,
            "sale_id": None,
            "resposta": None,
        }

        data = core.ensure_solicitacoes_file(_ctx())
        if core.pg_enabled():
            try:
                core.pg_store.save_solicitacao(record=rec)
            except Exception as e:
                logger.error(f"Erro ao salvar solicitacao no Postgres: {e}")
            try:
                logger.info(f"Chamando kds_ensure_order_row para solicitacao_id={solicitacao_id}")
                core.pg_store.kds_ensure_order_row(solicitacao_id=solicitacao_id)
                logger.info(f"kds_ensure_order_row executado com sucesso para solicitacao_id={solicitacao_id}")
            except Exception as e:
                logger.error(f"Erro ao chamar kds_ensure_order_row para solicitacao_id={solicitacao_id}: {e}")
        else:
            data["solicitacoes"].append(rec)
            core.save_solicitacoes(_ctx(), data)

        core.notify_telegram_new_order(rec)
        try:
            from .kds.service import notificar_kds_novo_pedido

            notificar_kds_novo_pedido(solicitacao_id=solicitacao_id, base_url=str(request.host_url or ""))
        except Exception:
            pass
        return jsonify({"id": solicitacao_id, "status": "PENDENTE"})

    @app.get("/api/solicitacoes/<solicitacao_id>")
    def api_get_solicitacao(solicitacao_id: str):
        mesa = request.args.get("mesa")
        token = request.args.get("token")
        ok, err = core.validate_table_token(ctx=_ctx(), mesa=mesa, token=token)
        if not ok:
            return jsonify({"error": err}), 401

        data = core.ensure_solicitacoes_file(_ctx())
        _, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None:
            return jsonify({"error": "nao_encontrado"}), 404
        if int(s.get("mesa") or 0) != int(mesa):
            return jsonify({"error": "forbidden"}), 403
        return jsonify(s)

    @app.get("/api/solicitacoes/<solicitacao_id>/kds-status")
    def api_get_solicitacao_kds_status(solicitacao_id: str):
        logger.info(f"api_get_solicitacao_kds_status chamado: solicitacao_id={solicitacao_id}")
        mesa = request.args.get("mesa")
        token = request.args.get("token")
        logger.info(f"api_get_solicitacao_kds_status: mesa={mesa}, token_prefix={str(token or '')[:8]}")
        ok, err = core.validate_table_token(ctx=_ctx(), mesa=mesa, token=token)
        if not ok:
            logger.info(f"api_get_solicitacao_kds_status: token validation failed: {err}")
            return jsonify({"error": err}), 401

        if not core.pg_enabled():
            logger.info(f"api_get_solicitacao_kds_status: pg_disabled")
            return jsonify({"error": "pg_disabled"}), 500

        data = core.ensure_solicitacoes_file(_ctx())
        _, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None:
            logger.info(f"api_get_solicitacao_kds_status: solicitacao not found in file")
            return jsonify({"error": "nao_encontrado"}), 404
        if int(s.get("mesa") or 0) != int(mesa):
            logger.info(f"api_get_solicitacao_kds_status: mesa mismatch")
            return jsonify({"error": "forbidden"}), 403

        try:
            logger.info(f"api_get_solicitacao_kds_status: chamando kds_get_status")
            status = core.pg_store.kds_get_status(solicitacao_id=solicitacao_id)
            logger.info(f"api_get_solicitacao_kds_status: status retornado: {status}")
        except Exception as e:
            logger.error(f"api_get_solicitacao_kds_status: erro ao chamar kds_get_status: {e}")
            return jsonify({"error": "erro_interno"}), 500

        if status is None:
            logger.info(f"api_get_solicitacao_kds_status: status is None")
            return jsonify({"error": "nao_encontrado"}), 404

        logger.info(f"api_get_solicitacao_kds_status: retornando status={status}")
        return jsonify({"status": status})

    @app.post("/api/public/pedidos")
    def api_public_create_pedido():
        limited = _rate_limited(
            key=f"criar_pedido:{_client_ip()}", limit=RATE_LIMIT_CRIAR_PEDIDO
        )
        if limited is not None:
            return limited

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        idem_key = _idempotency_key_from(body)
        idem_hash = _request_hash({k: v for k, v in body.items() if k != "idempotency_key"})
        cached = _idempotency_lookup(
            scope=IDEMPOTENCY_SCOPE_CRIAR, key=idem_key, payload_hash=idem_hash
        )
        if cached is not None:
            return cached

        pagamento = str(body.get("pagamento_preferido") or "").strip().upper()
        if pagamento not in core.ALLOWED_PAYMENT_METHODS:
            return jsonify({"error": "pagamento_invalido"}), 400

        cliente_nome = str(body.get("cliente_nome") or "").strip()
        if not cliente_nome or len(cliente_nome) > 60:
            return jsonify({"error": "cliente_nome_invalido"}), 400

        cliente_whatsapp = str(body.get("cliente_whatsapp") or "").strip()
        if not core.is_valid_whatsapp(cliente_whatsapp):
            return jsonify({"error": "whatsapp_invalido"}), 400

        tipo_entrega = str(body.get("tipo_entrega") or "").strip().upper()
        if tipo_entrega not in ("DELIVERY", "RETIRADA"):
            return jsonify({"error": "tipo_entrega_invalido"}), 400

        endereco = body.get("endereco")
        if tipo_entrega == "DELIVERY":
            if endereco is None:
                return jsonify({"error": "endereco_obrigatorio"}), 400
            if not isinstance(endereco, dict):
                return jsonify({"error": "endereco_invalido"}), 400

            maps_url = str(endereco.get("maps_url") or endereco.get("maps") or endereco.get("localizacao") or "").strip()
            if not maps_url:
                required = ["rua", "numero", "bairro", "cidade"]
                for k in required:
                    if not str(endereco.get(k) or "").strip():
                        return jsonify({"error": "endereco_incompleto"}), 400
        else:
            endereco = None

        troco_para = body.get("troco_para")
        if pagamento == "DINHEIRO" and troco_para is not None:
            try:
                troco_f = float(troco_para)
            except Exception:
                return jsonify({"error": "troco_invalido"}), 400
            if troco_f < 0 or troco_f > 10000:
                return jsonify({"error": "troco_invalido"}), 400

        itens = body.get("itens")
        if not isinstance(itens, list) or len(itens) == 0:
            return jsonify({"error": "itens_obrigatorios"}), 400
        if len(itens) > 80:
            return jsonify({"error": "muitos_itens"}), 400

        norm_items: list[dict[str, Any]] = []
        for it in itens:
            if not isinstance(it, dict):
                return jsonify({"error": "item_invalido"}), 400
            code = str(it.get("product_code") or it.get("pdvCode") or "").strip().upper()
            if not code:
                return jsonify({"error": "product_code_obrigatorio"}), 400
            try:
                qty = float(it.get("qty") or it.get("quantidade") or 0)
            except Exception:
                qty = 0
            if qty <= 0:
                return jsonify({"error": "qty_invalida"}), 400
            norm_items.append(
                {
                    "product_code": code,
                    "nome": str(it.get("nome") or "").strip(),
                    "qty": qty,
                }
            )

        # Cobrança online exige preço vindo do catálogo: o valor cobrado nunca
        # pode depender do que o navegador informou. Fora do fluxo online, o
        # total continua sendo apenas uma estimativa exibida ao operador.
        cobra_online = pay_domain.pix_online_enabled() and pay_domain.is_online_chargeable(pagamento)

        if cobra_online:
            published = core.read_catalogo_publicado(_ctx())
            produtos = published.get("produtos") if isinstance(published, dict) else []
            try:
                subtotal_f, norm_items = pay_domain.calcular_subtotal(
                    produtos=produtos, itens=norm_items
                )
            except pay_domain.ProdutoDesconhecidoError as e:
                return (
                    jsonify({"error": "produto_desconhecido", "product_code": e.product_code}),
                    400,
                )
            total_estimado_f = subtotal_f
        else:
            total_estimado = body.get("total_estimado")
            try:
                total_estimado_f = float(total_estimado) if total_estimado is not None else None
            except Exception:
                total_estimado_f = None

        access_token = secrets.token_urlsafe(24)
        solicitacao_id = uuid.uuid4().hex
        status_inicial = (
            pedidos_domain.SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO
            if cobra_online
            else pedidos_domain.SOLICITACAO_STATUS_PENDENTE
        )
        rec: dict[str, Any] = {
            "id": solicitacao_id,
            "kind": "DELIVERY",
            "access_token": access_token,
            "status": status_inicial,
            "pagamento_preferido": pagamento,
            "cliente_nome": cliente_nome,
            "cliente_whatsapp": cliente_whatsapp,
            "tipo_entrega": tipo_entrega,
            "endereco": endereco,
            "troco_para": troco_para,
            "observacoes": str(body.get("observacoes") or "").strip() or None,
            "itens": norm_items,
            "total_estimado": total_estimado_f,
            # apply_delivery_fee_to_order_record sobrescreve estes dois quando há
            # taxa de entrega a calcular; para RETIRADA eles ficam como estão.
            "subtotal_estimado": total_estimado_f,
            "taxa_entrega": 0.0 if cobra_online else None,
            "criado_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "atendida_em": None,
            "respondida_em": None,
            "pdv_status": None,
            "pdv_status_em": None,
            "pdv_id": None,
            "operator_user_id": None,
            "sale_id": None,
            "resposta": None,
            "comprovante": None,
            "pagamento_online": cobra_online,
            "active_payment_id": None,
            "payment_attempts": 0,
            "payment_window_expires_at": (
                pay_domain.window_deadline_iso() if cobra_online else None
            ),
            "pago_em": None,
            "pagamento": None,
            "ocorrencias_pagamento": [],
        }

        try:
            from .taxa_entrega.service import apply_delivery_fee_to_order_record

            rec = apply_delivery_fee_to_order_record(ctx=_ctx(), rec=rec)
        except Exception:
            pass

        if not cobra_online:
            # Fluxo legado preservado: pedido entra como PENDENTE e a cozinha é
            # avisada na criação, sem qualquer etapa de pagamento.
            if core.pg_enabled():
                try:
                    core.pg_store.save_solicitacao(record=rec)
                except Exception:
                    return jsonify({"error": "falha_ao_salvar"}), 500
                try:
                    core.pg_store.kds_ensure_order_row(solicitacao_id=solicitacao_id)
                except Exception:
                    pass
            else:
                data = core.ensure_solicitacoes_file(_ctx())
                data["solicitacoes"].append(rec)
                core.save_solicitacoes(_ctx(), data)

            core.notify_telegram_new_order(rec)
            try:
                from .kds.service import notificar_kds_novo_pedido

                notificar_kds_novo_pedido(solicitacao_id=solicitacao_id, base_url=str(request.host_url or ""))
            except Exception:
                pass

            resposta = {"id": solicitacao_id, "token": access_token, "status": rec["status"]}
            _idempotency_store(
                scope=IDEMPOTENCY_SCOPE_CRIAR,
                key=idem_key,
                payload_hash=idem_hash,
                response=resposta,
                status_code=200,
                solicitacao_id=solicitacao_id,
            )
            return jsonify(resposta)

        if not core.pg_enabled():
            # A cobrança vive em external_payments; sem Postgres não há como
            # rastrear o pagamento e o pedido não deve ser aceito.
            return jsonify({"error": "pg_disabled"}), 500

        # A solicitação é salva ANTES de criar a cobrança. Se o webhook chegar
        # muito rápido, o orquestrador precisa encontrar o pedido pelo
        # reference_id; criar a cobrança primeiro abriria essa janela de corrida.
        try:
            core.pg_store.save_solicitacao(record=rec)
        except Exception:
            logger.exception("api_public_create_pedido - falha ao salvar sid=%s", solicitacao_id)
            return jsonify({"error": "falha_ao_salvar"}), 500

        try:
            payment = pay_service.criar_cobranca_pix(
                solicitacao_id=solicitacao_id,
                amount=float(rec.get("total_estimado") or 0),
                descricao=f"Pedido {solicitacao_id}",
            )
        except pay_service.CobrancaError as e:
            rec = pay_service.registrar_falha_cobranca(rec, erro=str(e))
            try:
                core.pg_store.save_solicitacao(record=rec)
            except Exception:
                logger.exception("api_public_create_pedido - falha ao registrar erro de cobrança")
            return jsonify({"error": "falha_criacao_pagamento", "detalhe": str(e)}), 502

        rec = pay_service.vincular_cobranca(rec, payment)
        try:
            core.pg_store.save_solicitacao(record=rec)
        except Exception:
            logger.exception("api_public_create_pedido - falha ao vincular cobrança sid=%s", solicitacao_id)
            return jsonify({"error": "falha_ao_salvar"}), 500

        # O KDS NÃO é notificado aqui: a cozinha só recebe o pedido depois da
        # confirmação do pagamento, feita pelo orquestrador do webhook.
        resposta = _resposta_publica_pedido(rec)
        _idempotency_store(
            scope=IDEMPOTENCY_SCOPE_CRIAR,
            key=idem_key,
            payload_hash=idem_hash,
            response=resposta,
            status_code=201,
            solicitacao_id=solicitacao_id,
        )
        return jsonify(resposta), 201

    @app.get("/api/public/pedidos/<solicitacao_id>")
    def api_public_get_pedido(solicitacao_id: str):
        token = (request.args.get("token") or "").strip()
        if not token:
            return jsonify({"error": "token_ausente"}), 401

        limited = _rate_limited(key=f"ler_pedido:{token}", limit=RATE_LIMIT_LER_PEDIDO)
        if limited is not None:
            return limited

        data = core.ensure_solicitacoes_file(_ctx())
        _, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None:
            return jsonify({"error": "nao_encontrado"}), 404

        if str(s.get("kind") or "").upper() != "DELIVERY":
            return jsonify({"error": "forbidden"}), 403

        expected = str(s.get("access_token") or "").strip()
        if not expected or token != expected:
            return jsonify({"error": "unauthorized"}), 401

        out = dict(s)
        # Reaplica a allowlist antes de responder. O snapshot já é gravado
        # filtrado; isto protege registros antigos e falhas futuras.
        out["pagamento"] = pay_domain.filtrar_snapshot_publico(s.get("pagamento"))
        out.update(pay_service.estado_publico(s))
        return jsonify(out)

    @app.post("/api/public/pedidos/<solicitacao_id>/pagar")
    def api_public_pagar_pedido(solicitacao_id: str):
        """Gera uma nova cobrança PIX para um pedido que ainda não foi pago.

        Usado tanto quando a cobrança anterior expirou quanto quando a criação
        original falhou. Uma solicitação nunca tem duas cobranças ativas: a
        anterior é marcada como EXPIRADA antes de criar a nova.
        """
        token = (request.args.get("token") or "").strip()
        if not token:
            return jsonify({"error": "token_ausente"}), 401

        limited = _rate_limited(
            key=f"pagar:{solicitacao_id}", limit=RATE_LIMIT_GERAR_PAGAMENTO
        )
        if limited is not None:
            return limited

        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        if not pay_domain.pix_online_enabled():
            return jsonify({"error": "pagamento_online_desabilitado"}), 403

        body = request.get_json(silent=True) or {}
        idem_key = _idempotency_key_from(body)
        idem_hash = _request_hash({"solicitacao_id": solicitacao_id})
        cached = _idempotency_lookup(
            scope=IDEMPOTENCY_SCOPE_PAGAR, key=idem_key, payload_hash=idem_hash
        )
        if cached is not None:
            return cached

        rec = core.pg_store.get_solicitacao(solicitacao_id=solicitacao_id)
        if not isinstance(rec, dict):
            return jsonify({"error": "nao_encontrado"}), 404

        expected = str(rec.get("access_token") or "").strip()
        if not expected or token != expected:
            return jsonify({"error": "unauthorized"}), 401

        if not rec.get("pagamento_online"):
            return jsonify({"error": "pedido_sem_pagamento_online"}), 409

        status_atual = str(rec.get("status") or "").strip().upper()
        if status_atual != pedidos_domain.SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO:
            return jsonify({"error": "status_invalido", "status": status_atual}), 409

        if pay_service.tem_cobranca_ativa_pendente(rec):
            return jsonify({"error": "pagamento_ativo_pendente"}), 409

        if not pay_domain.pode_retentar(solicitacao=rec):
            return jsonify({"error": "janela_retentativa_encerrada"}), 403

        # O QR anterior não pode ser cancelado no PagBank; marcamos como expirado
        # localmente. Se o cliente pagar o QR antigo mais tarde, o orquestrador
        # trata pela regra de unicidade financeira.
        pay_service.expirar_cobranca_ativa(rec)

        published = core.read_catalogo_publicado(_ctx())
        produtos = published.get("produtos") if isinstance(published, dict) else []
        try:
            subtotal_f, _ = pay_domain.calcular_subtotal(
                produtos=produtos, itens=rec.get("itens") or []
            )
        except pay_domain.ProdutoDesconhecidoError as e:
            return (
                jsonify({"error": "produto_desconhecido", "product_code": e.product_code}),
                400,
            )

        taxa = rec.get("taxa_entrega")
        try:
            taxa_f = float(taxa) if taxa is not None else 0.0
        except (TypeError, ValueError):
            taxa_f = 0.0

        total_f = round(subtotal_f + taxa_f + 1e-9, 2)
        rec["subtotal_estimado"] = subtotal_f
        rec["total_estimado"] = total_f

        try:
            payment = pay_service.criar_cobranca_pix(
                solicitacao_id=solicitacao_id,
                amount=total_f,
                descricao=f"Pedido {solicitacao_id}",
            )
        except pay_service.CobrancaError as e:
            rec = pay_service.registrar_falha_cobranca(rec, erro=str(e))
            try:
                core.pg_store.save_solicitacao(record=rec)
            except Exception:
                logger.exception("api_public_pagar_pedido - falha ao registrar erro")
            return jsonify({"error": "falha_criacao_pagamento", "detalhe": str(e)}), 502

        rec = pay_service.vincular_cobranca(rec, payment)
        try:
            core.pg_store.save_solicitacao(record=rec)
        except Exception:
            logger.exception("api_public_pagar_pedido - falha ao salvar sid=%s", solicitacao_id)
            return jsonify({"error": "falha_ao_salvar"}), 500

        resposta = _resposta_publica_pedido(rec)
        _idempotency_store(
            scope=IDEMPOTENCY_SCOPE_PAGAR,
            key=idem_key,
            payload_hash=idem_hash,
            response=resposta,
            status_code=200,
            solicitacao_id=solicitacao_id,
        )
        return jsonify(resposta)

    @app.get("/api/public/pedidos/<solicitacao_id>/status")
    def api_public_get_pedido_status(solicitacao_id: str):
        token = (request.args.get("token") or "").strip()
        if not token:
            return jsonify({"error": "token_ausente"}), 401

        limited = _rate_limited(key=f"ler_status:{token}", limit=RATE_LIMIT_LER_STATUS)
        if limited is not None:
            return limited

        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        try:
            rec = core.pg_store.get_solicitacao(solicitacao_id=solicitacao_id)
        except Exception:
            return jsonify({"error": "nao_encontrado"}), 404

        if not isinstance(rec, dict):
            return jsonify({"error": "nao_encontrado"}), 404

        expected = str(rec.get("access_token") or "").strip()
        if not expected or token != expected:
            return jsonify({"error": "unauthorized"}), 401

        resultado = pay_service.status_publico(rec)
        resultado["solicitacao_id"] = solicitacao_id
        resultado["tipo_entrega"] = str(rec.get("tipo_entrega") or "").strip().upper()
        resultado["status"] = str(rec.get("status") or "").strip().upper()
        resultado.update(pay_service.estado_publico(rec))
        resultado["pagamento"] = pay_domain.filtrar_snapshot_publico(rec.get("pagamento"))

        # Esses campos sao usados pelo frontend para manter a area de pagamento
        # visivel enquanto o QR aguarda confirmacao e para exibir o resumo do pedido.
        resultado["pagamento_online"] = bool(rec.get("pagamento_online"))
        resultado["subtotal"] = rec.get("subtotal_estimado")
        resultado["taxa_entrega"] = rec.get("taxa_entrega")
        resultado["total"] = rec.get("total_estimado")
        resultado["payment_window_expires_at"] = rec.get("payment_window_expires_at")
        resultado["itens"] = rec.get("itens")
        resultado["cliente_nome"] = rec.get("cliente_nome")
        resultado["cliente_whatsapp"] = rec.get("cliente_whatsapp")
        resultado["endereco"] = rec.get("endereco")
        resultado["pagamento_preferido"] = rec.get("pagamento_preferido")
        resultado["cancelado"] = bool(rec.get("cancelado"))

        return jsonify(resultado)

    @app.post("/api/public/pedidos/<solicitacao_id>/cancelar")
    def api_public_cancelar_pedido(solicitacao_id: str):
        token = (request.args.get("token") or "").strip()
        if not token:
            return jsonify({"error": "token_ausente"}), 401

        limited = _rate_limited(key=f"cancelar_pedido:{token}", limit=RATE_LIMIT_LER_STATUS)
        if limited is not None:
            return limited

        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500

        try:
            rec = core.pg_store.get_solicitacao(solicitacao_id=solicitacao_id)
        except Exception:
            return jsonify({"error": "nao_encontrado"}), 404

        if not isinstance(rec, dict):
            return jsonify({"error": "nao_encontrado"}), 404

        expected = str(rec.get("access_token") or "").strip()
        if not expected or token != expected:
            return jsonify({"error": "unauthorized"}), 401

        res = pay_service.cancelar_pedido_publico(rec)
        if not res.get("ok"):
            return jsonify(res), 409
        return jsonify(res)

    @app.get("/api/pdv/solicitacoes")
    def api_pdv_list_solicitacoes():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        raw = str(request.args.get("status") or "PENDENTE").strip().upper()
        statuses = [st.strip() for st in raw.split(",") if st.strip()]
        if not statuses:
            statuses = ["PENDENTE"]

        if core.pg_enabled():
            try:
                out: list[dict[str, Any]] = []
                seen: set[str] = set()
                for st in statuses:
                    for rec in (core.pg_store.list_by_status(status=st) or []):
                        sid = str(rec.get("id") or "")
                        if sid and sid not in seen:
                            seen.add(sid)
                            out.append(rec)
                out.sort(
                    key=lambda x: (x.get("criado_em") or ""), reverse=True,
                )
            except Exception:
                out = []
            return jsonify({"solicitacoes": out})

        data = core.ensure_solicitacoes_file(_ctx())
        arr = data.get("solicitacoes")
        if not isinstance(arr, list):
            arr = []
        status_set = set(statuses)
        out = [s for s in arr if isinstance(s, dict) and str(s.get("status") or "").upper() in status_set]
        return jsonify({"solicitacoes": out})

    @app.post("/api/pdv/solicitacoes/<solicitacao_id>/atender")
    def api_pdv_atender_solicitacao(solicitacao_id: str):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        data = core.ensure_solicitacoes_file(_ctx())
        idx, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None or idx is None:
            return jsonify({"error": "nao_encontrado"}), 404

        cur_status = str(s.get("status") or "").upper()
        solicitacao_pdv_id = str(s.get("pdv_id") or "").strip()
        request_pdv_id = str(body.get("pdv_id") or "").strip()
        is_online = bool(s.get("pagamento_online")) is True
        active_payment_id = str(s.get("active_payment_id") or "").strip() if is_online else ""

        # Pedido online so pode ir para producao depois do pagamento confirmado.
        if cur_status == "AGUARDANDO_PAGAMENTO":
            return jsonify({"error": "aguardando_pagamento"}), 409

        # Estados finais: nao se pode atender novamente.
        if cur_status in ("RESPONDIDA", "FINALIZADA"):
            return jsonify({"error": "status_invalido", "status": cur_status}), 409

        if cur_status == "EM_ATENDIMENTO":
            # Idempotencia com retomada: o mesmo PDV pode retomar.
            if not (request_pdv_id and solicitacao_pdv_id and request_pdv_id == solicitacao_pdv_id):
                return jsonify({"error": "em_atendimento_por_outro_pdv", "pdv_id": solicitacao_pdv_id}), 409
            # Pedido online: verifica se o pagamento nao foi reivindicado por outro PDV.
            if is_online and active_payment_id and core.pg_enabled():
                payment = core.pg_store.get_external_payment(payment_id=active_payment_id)
                if payment is None:
                    return jsonify({"error": "pagamento_nao_encontrado"}), 409
                claimed_by = str(payment.get("claimed_by_pdv_id") or "").strip()
                if claimed_by and claimed_by != request_pdv_id:
                    return jsonify({"error": "pagamento_reivindicado_por_outro_pdv"}), 409
            return jsonify(s)

        if cur_status != "PENDENTE":
            return jsonify({"error": "status_invalido", "status": cur_status}), 409

        # Pedido online: valida pagamento aprovado e sem reivindicacao de outro PDV.
        # O claim financeiro sera feito no passo PAGAMENTO_APLICADO.
        if is_online and active_payment_id:
            if not core.pg_enabled():
                return jsonify({"error": "pg_nao_habilitado"}), 500
            payment = core.pg_store.get_external_payment(payment_id=active_payment_id)
            if payment is None:
                return jsonify({"error": "pagamento_nao_encontrado"}), 409
            if str(payment.get("status") or "").upper() != "APROVADO":
                return jsonify({"error": "pagamento_nao_aprovado"}), 409
            claimed = str(payment.get("claimed_by_pdv_id") or "").strip()
            if claimed and claimed != request_pdv_id:
                return jsonify({"error": "pagamento_reivindicado_por_outro_pdv"}), 409

        s["status"] = "EM_ATENDIMENTO"
        s["pdv_id"] = body.get("pdv_id")
        s["operator_user_id"] = body.get("operator_user_id")
        s["atendida_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")

        if core.pg_enabled():
            try:
                core.pg_store.save_solicitacao(record=s)
            except Exception:
                return jsonify({"error": "falha_ao_salvar"}), 500
        else:
            data["solicitacoes"][idx] = s
            core.save_solicitacoes(_ctx(), data)
        return jsonify(s)

    @app.post("/api/pdv/solicitacoes/<solicitacao_id>/vincular")
    def api_pdv_vincular_sale(solicitacao_id: str):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400
        sale_id = body.get("sale_id")
        try:
            sale_id_i = int(sale_id)
        except Exception:
            return jsonify({"error": "sale_id_invalido"}), 400

        data = core.ensure_solicitacoes_file(_ctx())
        idx, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None or idx is None:
            return jsonify({"error": "nao_encontrado"}), 404

        existing_sale_id = s.get("sale_id")
        if existing_sale_id is not None and int(existing_sale_id) != sale_id_i:
            return jsonify({"error": "sale_id_divergente", "sale_id_atual": existing_sale_id}), 409

        s["sale_id"] = sale_id_i
        if core.pg_enabled():
            try:
                core.pg_store.save_solicitacao(record=s)
            except Exception:
                return jsonify({"error": "falha_ao_salvar"}), 500
        else:
            data["solicitacoes"][idx] = s
            core.save_solicitacoes(_ctx(), data)
        return jsonify({"ok": True, "sale_id": sale_id_i})

    @app.post("/api/pdv/solicitacoes/<solicitacao_id>/conferir")
    def api_pdv_conferir_solicitacao(solicitacao_id: str):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        data = core.ensure_solicitacoes_file(_ctx())
        idx, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None or idx is None:
            return jsonify({"error": "nao_encontrado"}), 404

        cur_status = str(s.get("status") or "").upper()
        solicitacao_pdv_id = str(s.get("pdv_id") or "").strip()
        request_pdv_id = str(body.get("pdv_id") or "").strip()

        if cur_status == "RESPONDIDA":
            if request_pdv_id and solicitacao_pdv_id and request_pdv_id == solicitacao_pdv_id:
                return jsonify({"ok": True})
            return jsonify({"error": "respondida_por_outro_pdv", "pdv_id": solicitacao_pdv_id}), 409

        if cur_status != "EM_ATENDIMENTO":
            return jsonify({"error": "status_invalido", "status": cur_status}), 409

        if solicitacao_pdv_id and request_pdv_id and request_pdv_id != solicitacao_pdv_id:
            return jsonify({"error": "em_atendimento_por_outro_pdv", "pdv_id": solicitacao_pdv_id}), 409

        # Para pedido online, so pode conferir se o pagamento foi aplicado a uma venda.
        is_online = bool(s.get("pagamento_online"))
        active_payment_id = str(s.get("active_payment_id") or "").strip()
        if is_online and active_payment_id:
            if not core.pg_enabled():
                return jsonify({"error": "pg_nao_habilitado"}), 500
            payment = core.pg_store.get_external_payment(payment_id=active_payment_id)
            if payment is None:
                return jsonify({"error": "pagamento_nao_encontrado"}), 409
            if not payment.get("applied_sale_id") or not payment.get("applied_sale_payment_id"):
                return jsonify({"error": "pagamento_nao_aplicado"}), 409

        s["status"] = "RESPONDIDA"
        s["pdv_status"] = "FINALIZADA"
        s["pdv_status_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        s["respondida_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")

        if core.pg_enabled():
            try:
                core.pg_store.save_solicitacao(record=s)
            except Exception:
                return jsonify({"error": "falha_ao_salvar"}), 500
        else:
            data["solicitacoes"][idx] = s
            core.save_solicitacoes(_ctx(), data)
        return jsonify({"ok": True})

    @app.post("/api/pdv/solicitacoes/<solicitacao_id>/resposta")
    def api_pdv_responder_solicitacao(solicitacao_id: str):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        tipo = str(body.get("tipo") or "").strip().upper()
        if tipo not in ("ENVIAR_PIX", "IR_CAIXA", "PAGAMENTO_CONFIRMADO", "PAGAR_NA_ENTREGA"):
            return jsonify({"error": "tipo_invalido"}), 400

        data = core.ensure_solicitacoes_file(_ctx())
        idx, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None or idx is None:
            return jsonify({"error": "nao_encontrado"}), 404

        cur_status = str(s.get("status") or "").upper()
        prev_resposta = s.get("resposta") if isinstance(s.get("resposta"), dict) else None
        prev_tipo = str((prev_resposta or {}).get("tipo") or "").upper()

        if tipo == "PAGAMENTO_CONFIRMADO":
            if cur_status != "RESPONDIDA" or prev_tipo != "ENVIAR_PIX":
                return jsonify({"error": "status_invalido", "status": cur_status}), 409
            comp = s.get("comprovante") if isinstance(s.get("comprovante"), dict) else None
            if not comp or not str(comp.get("path") or "").strip():
                return jsonify({"error": "comprovante_ausente"}), 409
        else:
            if cur_status not in ("EM_ATENDIMENTO", "PENDENTE"):
                return jsonify({"error": "status_invalido", "status": cur_status}), 409

        resposta: dict[str, Any] = {
            "tipo": tipo,
            "mensagem": str(body.get("mensagem") or "").strip() or None,
            "pix": body.get("pix") if tipo == "ENVIAR_PIX" else None,
        }

        s["status"] = "RESPONDIDA"
        s["respondida_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        s["resposta"] = resposta
        if core.pg_enabled():
            try:
                core.pg_store.save_solicitacao(record=s)
            except Exception:
                return jsonify({"error": "falha_ao_salvar"}), 500
        else:
            data["solicitacoes"][idx] = s
            core.save_solicitacoes(_ctx(), data)

        return jsonify({"ok": True})

    # ==================================================================
    # CONFIGURAÇÃO DE PROVEDORES DE PAGAMENTO
    #
    # Endpoints:
    #   GET    /api/pdv/payment_providers/<provider_id>/config  — obter config
    #   POST   /api/pdv/payment_providers/<provider_id>/config  — salvar config
    #   POST   /api/pdv/payment_providers/<provider_id>/active  — ativar/desativar
    # ==================================================================

    @app.get("/api/pdv/payment_providers/<provider_id>/config")
    def api_get_payment_provider_config(provider_id: str):
        """Obtém a configuração de um provedor (metadados + credenciais criptografadas)."""
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        if not core.pg_enabled():
            return jsonify({"error": "postgres_nao_habilitado"}), 500

        settings = core.pg_store.get_provider_settings(provider_id=provider_id)
        credentials = core.pg_store.get_provider_credentials(provider_id=provider_id)

        if settings is None:
            return jsonify({"configured": False, "credentials": []})

        return jsonify({
            "configured": True,
            "provider_id": settings.get("provider_id"),
            "display_name": settings.get("display_name"),
            "base_url": settings.get("base_url"),
            "environment": settings.get("environment") or "SANDBOX",
            "is_active": bool(settings.get("is_active")),
            "webhook_url": settings.get("webhook_url"),
            "default_expires_in_seconds": settings.get("default_expires_in_seconds"),
            "credentials": credentials or [],
        })

    @app.post("/api/pdv/payment_providers/<provider_id>/config")
    def api_save_payment_provider_config(provider_id: str):
        """Salva a configuração de um provedor (metadados + credenciais criptografadas)."""
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        if not core.pg_enabled():
            return jsonify({"error": "postgres_nao_habilitado"}), 500

        body = request.get_json(silent=True)
        if body is None or not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        display_name = str(body.get("display_name") or provider_id)
        base_url = str(body.get("base_url") or "")
        environment = str(body.get("environment") or "SANDBOX").strip().upper()
        is_active = bool(body.get("is_active", True))
        webhook_url = body.get("webhook_url")
        try:
            default_expires = int(body.get("default_expires_in_seconds") or 0) or None
        except (TypeError, ValueError):
            default_expires = None

        if not base_url:
            return jsonify({"error": "base_url_obrigatorio"}), 400

        # Salvar metadados
        ok = core.pg_store.upsert_provider_settings(
            provider_id=provider_id,
            display_name=display_name,
            base_url=base_url,
            environment=environment,
            default_expires_in_seconds=default_expires,
            webhook_url=webhook_url,
            is_active=is_active,
        )
        if not ok:
            return jsonify({"error": "falha_ao_salvar_settings"}), 500

        # Salvar credenciais (criptografar no Cardápio antes de armazenar)
        credentials = body.get("credentials") or []
        if isinstance(credentials, list):
            from .credential_crypto import encrypt as cred_encrypt, mask as cred_mask

            for cred in credentials:
                if not isinstance(cred, dict):
                    continue
                cred_key = str(cred.get("credential_key") or "")
                plaintext = str(cred.get("value") or "")

                if not cred_key or not plaintext:
                    continue

                encrypted_value = cred_encrypt(plaintext)
                hint = cred_mask(plaintext)

                core.pg_store.upsert_provider_credential(
                    provider_id=provider_id,
                    credential_key=cred_key,
                    encrypted_value=encrypted_value,
                    hint=hint,
                )

        return jsonify({"ok": True})

    @app.post("/api/pdv/payment_providers/<provider_id>/active")
    def api_set_payment_provider_active(provider_id: str):
        """Ativa ou desativa um provedor sem alterar credenciais."""
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        if not core.pg_enabled():
            return jsonify({"error": "postgres_nao_habilitado"}), 500

        body = request.get_json(silent=True) or {}
        is_active = bool(body.get("is_active", True))

        # Buscar config existente para preservar metadados
        settings = core.pg_store.get_provider_settings(provider_id=provider_id)
        if settings is None:
            return jsonify({"error": "provedor_nao_configurado"}), 404

        ok = core.pg_store.upsert_provider_settings(
            provider_id=provider_id,
            display_name=settings.get("display_name") or provider_id,
            base_url=settings.get("base_url") or "",
            environment=settings.get("environment") or "SANDBOX",
            default_expires_in_seconds=settings.get("default_expires_in_seconds"),
            webhook_url=settings.get("webhook_url"),
            is_active=is_active,
        )
        if not ok:
            return jsonify({"error": "falha_ao_atualizar"}), 500

        return jsonify({"ok": True, "is_active": is_active})

    # ==================================================================
    # PAGAMENTOS EXTERNOS — Fase 1 (PIX via PagBank API Order)
    #
    # Endpoints:
    #   POST   /api/payments              — criar cobrança PIX
    #   GET    /api/payments/pending      — listar aprovados não aplicados (PDV polling)
    #   GET    /api/payments/<id>         — obter pagamento por ID
    #   POST   /api/payments/<id>/claim   — PDV reivindica pagamento
    #   POST   /api/payments/<id>/application — PDV aplica à venda
    #   POST   /api/payments/webhook      — webhook do PagBank
    # ==================================================================

    def _get_payment_service():
        """Cria PaymentService com PagBankAdapter usando configuração salva no banco.

        Prioridade:
            1. Configuração salva em payment_provider_settings + credentials (banco)
            2. Variáveis de ambiente (fallback para compatibilidade)

        A construção vive em pagamento_online/service.py para ser compartilhada
        com a orquestração do pagamento online, sem duplicar a leitura de
        credenciais. O comportamento é o mesmo já validado no Sandbox.
        """
        return pay_service.build_payment_service()

    @app.post("/api/payments")
    def api_payments_create():
        """Cria uma cobrança PIX.

        Body: {
            "payment_method": "PIX",
            "amount": 100.00,
            "reference_id": "solicitacao_id ou sale_id",
            "description": "Pagamento pedido #123",
            "expires_in_seconds": 1800
        }
        """
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True)
        if body is None or not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        method_str = str(body.get("payment_method") or "").strip().upper()
        if method_str != "PIX":
            return jsonify({"error": "metodo_nao_suportado", "metodo": method_str}), 400

        try:
            amount = float(body.get("amount") or 0)
        except (TypeError, ValueError):
            return jsonify({"error": "valor_invalido"}), 400
        if amount <= 0:
            return jsonify({"error": "valor_invalido"}), 400

        reference_id = str(body.get("reference_id") or "").strip() or None
        description = str(body.get("description") or "").strip() or None
        try:
            expires_in = int(body.get("expires_in_seconds") or 0) or None
        except (TypeError, ValueError):
            expires_in = None

        try:
            service, PaymentMethod = _get_payment_service()
            record = service.iniciar_pagamento(
                payment_method=PaymentMethod.PIX,
                amount=amount,
                reference_id=reference_id,
                description=description,
                expires_in_seconds=expires_in,
            )
        except RuntimeError as e:
            logger.exception("api_payments_create - erro")
            return jsonify({"error": "erro_criacao", "detalhe": str(e)}), 500

        if record is None:
            return jsonify({"error": "falha_criacao"}), 500

        return jsonify(record), 201

    @app.get("/api/payments/pending")
    def api_payments_pending():
        """Lista pagamentos APROVADOS não aplicados (PDV polling)."""
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        if not core.pg_enabled():
            return jsonify({"payments": []})

        payments = core.pg_store.list_pending_external_payments()
        return jsonify({"payments": payments})

    @app.get("/api/payments/<payment_id>")
    def api_payments_get(payment_id: str):
        """Obtém um pagamento por ID."""
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        if not core.pg_enabled():
            return jsonify({"error": "nao_encontrado"}), 404

        record = core.pg_store.get_external_payment(payment_id=payment_id)
        if record is None:
            return jsonify({"error": "nao_encontrado"}), 404

        return jsonify(record)

    @app.post("/api/payments/<payment_id>/claim")
    def api_payments_claim(payment_id: str):
        """PDV reivindica um pagamento aprovado.

        Idempotente para o mesmo PDV. Para pagamentos de pedidos online,
        a solicitação deve estar EM_ATENDIMENTO e atribuída ao mesmo PDV.
        """
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True) or {}
        pdv_id = str(body.get("pdv_id") or "").strip()
        if not pdv_id:
            return jsonify({"error": "pdv_id_obrigatorio"}), 400

        if not core.pg_enabled():
            return jsonify({"error": "nao_encontrado"}), 404

        payment = core.pg_store.get_external_payment(payment_id=payment_id)
        if payment is None:
            return jsonify({"error": "nao_encontrado"}), 404

        if str(payment.get("status") or "").upper() != "APROVADO":
            return jsonify({"error": "pagamento_nao_aprovado"}), 409

        reference_id = str(payment.get("reference_id") or "").strip()
        solicitacao = core.pg_store.get_solicitacao(solicitacao_id=reference_id)
        if isinstance(solicitacao, dict):
            if str(solicitacao.get("status") or "").upper() != "EM_ATENDIMENTO":
                return jsonify({"error": "solicitacao_nao_em_atendimento"}), 409
            solicitacao_pdv_id = str(solicitacao.get("pdv_id") or "").strip()
            if solicitacao_pdv_id and solicitacao_pdv_id != pdv_id:
                return jsonify({"error": "solicitacao_atribuida_a_outro_pdv"}), 409

        record = core.pg_store.claim_external_payment(
            payment_id=payment_id, pdv_id=pdv_id,
        )
        if record is not None:
            return jsonify(record)

        # Verifica se já foi reivindicado pelo mesmo PDV (condição de corrida).
        atual = core.pg_store.get_external_payment(payment_id=payment_id)
        if isinstance(atual, dict):
            if str(atual.get("claimed_by_pdv_id") or "").strip() == pdv_id:
                return jsonify(atual)

        return jsonify({"error": "ja_reivindicado_ou_nao_aprovado"}), 409

    @app.post("/api/payments/<payment_id>/application")
    def api_payments_apply(payment_id: str):
        """PDV aplica o pagamento a uma venda.

        Realiza claim+apply atomicamente. Idempotente para a tupla
        (payment_id, pdv_id, sale_id, sale_payment_id).
        """
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True) or {}
        pdv_id = str(body.get("pdv_id") or "").strip()
        if not pdv_id:
            return jsonify({"error": "pdv_id_obrigatorio"}), 400

        try:
            sale_id = int(body.get("sale_id") or 0)
            sale_payment_id = int(body.get("sale_payment_id") or 0)
        except (TypeError, ValueError):
            return jsonify({"error": "parametros_invalidos"}), 400

        if sale_id <= 0 or sale_payment_id <= 0:
            return jsonify({"error": "parametros_invalidos"}), 400

        if not core.pg_enabled():
            return jsonify({"error": "nao_encontrado"}), 404

        payment = core.pg_store.get_external_payment(payment_id=payment_id)
        if payment is None:
            return jsonify({"error": "nao_encontrado"}), 404

        if str(payment.get("status") or "").upper() != "APROVADO":
            return jsonify({"error": "pagamento_nao_aprovado"}), 409

        reference_id = str(payment.get("reference_id") or "").strip()
        solicitacao = core.pg_store.get_solicitacao(solicitacao_id=reference_id)
        if isinstance(solicitacao, dict):
            if str(solicitacao.get("status") or "").upper() != "EM_ATENDIMENTO":
                return jsonify({"error": "solicitacao_nao_em_atendimento"}), 409
            solicitacao_pdv_id = str(solicitacao.get("pdv_id") or "").strip()
            if solicitacao_pdv_id and solicitacao_pdv_id != pdv_id:
                return jsonify({"error": "solicitacao_atribuida_a_outro_pdv"}), 409
            solicitacao_sale_id = solicitacao.get("sale_id")
            if solicitacao_sale_id is None:
                return jsonify({"error": "venda_nao_vinculada"}), 409
            if int(solicitacao_sale_id) != sale_id:
                return jsonify({"error": "sale_id_divergente"}), 409
        else:
            # Pagamento presencial: reference_id deve ser o próprio sale_id.
            if reference_id != str(sale_id):
                return jsonify({"error": "sale_id_divergente"}), 409

        ok = core.pg_store.apply_external_payment(
            payment_id=payment_id,
            sale_id=sale_id,
            sale_payment_id=sale_payment_id,
            pdv_id=pdv_id,
        )
        if ok:
            return jsonify({"ok": True})

        # Verifica se já foi aplicado com os mesmos dados (condição de corrida).
        atual = core.pg_store.get_external_payment(payment_id=payment_id)
        if isinstance(atual, dict):
            if (
                str(atual.get("claimed_by_pdv_id") or "").strip() == pdv_id
                and atual.get("applied_sale_id") == sale_id
                and atual.get("applied_sale_payment_id") == sale_payment_id
            ):
                return jsonify({"ok": True})

            if atual.get("applied_sale_id") is not None:
                if atual.get("applied_sale_id") != sale_id or atual.get("applied_sale_payment_id") != sale_payment_id:
                    return jsonify({"error": "ja_aplicado_outra_venda"}), 409

            claimed_by = str(atual.get("claimed_by_pdv_id") or "").strip()
            if claimed_by and claimed_by != pdv_id:
                return jsonify({"error": "claim_outro_pdv"}), 409

        return jsonify({"error": "ja_aplicado_ou_nao_encontrado"}), 409

    @app.post("/api/payments/webhook")
    def api_payments_webhook():
        """Webhook do PagBank.

        Não requer PDV_KEY — é autenticado via assinatura (x-authenticity-token).
        O adapter valida a assinatura internamente.

        O contrato externo é inalterado. Internamente, além de atualizar o
        pagamento, a chamada passa pela orquestração do pagamento online: quando
        houver transição real para APROVADO, a solicitação vinculada avança para
        PENDENTE e a cozinha é notificada. A regra de unicidade financeira é
        aplicada ali, não aqui.
        """
        raw_body = request.get_data() or b""
        headers = {k.lower(): v for k, v in request.headers.items()}

        # Rastro de entrada do webhook. Não registra o corpo: ele carrega
        # nome/e-mail/CPF do cliente. `assinado` diz se o PSP mandou a
        # assinatura — o Sandbox do PagBank não manda.
        logger.info(
            "api_payments_webhook - recebido body_len=%s assinado=%s",
            len(raw_body),
            "x-authenticity-token" in headers,
        )

        try:
            record = pay_service.processar_webhook(
                headers=headers,
                body=raw_body,
                base_url=str(request.host_url or ""),
            )
        except RuntimeError as e:
            logger.exception("api_payments_webhook - erro")
            return jsonify({"error": "erro_webhook", "detalhe": str(e)}), 500

        if record is None:
            # Webhook inválido ou pagamento não encontrado
            # Retornar 200 para o PagBank não reenviar (idempotência)
            return jsonify({"ok": False, "reason": "invalid_or_not_found"}), 200

        return jsonify({"ok": True, "payment_id": record.get("id")}), 200
