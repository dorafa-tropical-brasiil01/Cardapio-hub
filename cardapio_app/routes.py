from __future__ import annotations

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

from . import core

logger = logging.getLogger(__name__)


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

    @app.get("/")
    def home():
        resp = make_response(send_from_directory(str(_ctx().bundle_dir), "index.html"))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
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
            except Exception:
                pass
        else:
            data["solicitacoes"].append(rec)
            core.save_solicitacoes(_ctx(), data)

        core.notify_telegram_new_order(rec)
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

    @app.post("/api/public/pedidos")
    def api_public_create_pedido():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

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

        total_estimado = body.get("total_estimado")
        try:
            total_estimado_f = float(total_estimado) if total_estimado is not None else None
        except Exception:
            total_estimado_f = None

        access_token = secrets.token_urlsafe(24)
        solicitacao_id = uuid.uuid4().hex
        rec: dict[str, Any] = {
            "id": solicitacao_id,
            "kind": "DELIVERY",
            "access_token": access_token,
            "status": "PENDENTE",
            "pagamento_preferido": pagamento,
            "cliente_nome": cliente_nome,
            "cliente_whatsapp": cliente_whatsapp,
            "tipo_entrega": tipo_entrega,
            "endereco": endereco,
            "troco_para": troco_para,
            "observacoes": str(body.get("observacoes") or "").strip() or None,
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
            "comprovante": None,
        }

        if core.pg_enabled():
            try:
                core.pg_store.save_solicitacao(record=rec)
            except Exception:
                return jsonify({"error": "falha_ao_salvar"}), 500
        else:
            data = core.ensure_solicitacoes_file(_ctx())
            data["solicitacoes"].append(rec)
            core.save_solicitacoes(_ctx(), data)

        core.notify_telegram_new_order(rec)
        return jsonify({"id": solicitacao_id, "token": access_token, "status": "PENDENTE"})

    @app.get("/api/public/pedidos/<solicitacao_id>")
    def api_public_get_pedido(solicitacao_id: str):
        token = (request.args.get("token") or "").strip()
        if not token:
            return jsonify({"error": "token_ausente"}), 401

        data = core.ensure_solicitacoes_file(_ctx())
        _, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
        if s is None:
            return jsonify({"error": "nao_encontrado"}), 404

        if str(s.get("kind") or "").upper() != "DELIVERY":
            return jsonify({"error": "forbidden"}), 403

        expected = str(s.get("access_token") or "").strip()
        if not expected or token != expected:
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(s)

    @app.get("/api/pdv/solicitacoes")
    def api_pdv_list_solicitacoes():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        status = str(request.args.get("status") or "PENDENTE").strip().upper()

        if core.pg_enabled():
            try:
                out = core.pg_store.list_by_status(status=status)
            except Exception:
                out = []
            return jsonify({"solicitacoes": out})

        data = core.ensure_solicitacoes_file(_ctx())
        arr = data.get("solicitacoes")
        if not isinstance(arr, list):
            arr = []
        out = [s for s in arr if isinstance(s, dict) and str(s.get("status") or "").upper() == status]
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
        if cur_status != "PENDENTE":
            return jsonify({"error": "status_invalido", "status": cur_status}), 409

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

        s["sale_id"] = sale_id_i
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
