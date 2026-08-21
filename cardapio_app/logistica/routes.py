from __future__ import annotations

import os

from flask import Flask, jsonify, make_response, request, session

from ..ops_auth.routes import require_ops_login
from ..ops_auth.store import auth_user
from .service import (
    corrida_add,
    corrida_devolver,
    corrida_finish,
    corrida_marcar_entregue,
    corrida_nova,
    corrida_remove,
    corrida_start,
    listar_integracoes,
    listar_prontos,
    obter_corrida_atual,
    pedido_cancelar_definitivo,
    pedido_dessinalizar,
    pedido_sinalizar,
    processar_pendentes,
    reprocessar_integracao,
)


def register_logistica_routes(app: Flask) -> None:
    def _verify_admin_password(password: str) -> bool:
        pwd = str(password or "")
        if not pwd:
            return False

        configured_pwd = str(os.environ.get("OPS_ADMIN_PASSWORD") or "").strip()
        if configured_pwd:
            return pwd == configured_pwd

        admin_username = str(os.environ.get("OPS_ADMIN_USERNAME") or "").strip().lower()
        if admin_username:
            rec = auth_user(username=admin_username, password=pwd)
            return rec is not None

        return False

    @app.get("/api/logistica/prontos")
    def api_logistica_prontos():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        return jsonify({"ok": True, "pedidos": listar_prontos()})

    @app.get("/api/logistica/corrida")
    def api_logistica_corrida():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        return jsonify({"ok": True, "corrida": obter_corrida_atual(ops_user_id=uid)})

    @app.post("/api/logistica/corrida/add")
    def api_logistica_corrida_add():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        sid = str(body.get("solicitacao_id") or "").strip()
        if not sid:
            return jsonify({"error": "solicitacao_id_ausente"}), 400
        try:
            c = corrida_add(ops_user_id=uid, solicitacao_id=sid)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/nova")
    def api_logistica_corrida_nova():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        try:
            c = corrida_nova(ops_user_id=uid)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/entregue")
    def api_logistica_corrida_entregue():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        sid = str(body.get("solicitacao_id") or "").strip()
        if not sid:
            return jsonify({"error": "solicitacao_id_ausente"}), 400
        try:
            c = corrida_marcar_entregue(ops_user_id=uid, solicitacao_id=sid)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/remove")
    def api_logistica_corrida_remove():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        sid = str(body.get("solicitacao_id") or "").strip()
        if not sid:
            return jsonify({"error": "solicitacao_id_ausente"}), 400
        try:
            c = corrida_remove(ops_user_id=uid, solicitacao_id=sid)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/devolver")
    def api_logistica_corrida_devolver():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        sid = str(body.get("solicitacao_id") or "").strip()
        if not sid:
            return jsonify({"error": "solicitacao_id_ausente"}), 400
        try:
            c = corrida_devolver(ops_user_id=uid, solicitacao_id=sid)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/start")
    def api_logistica_corrida_start():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        try:
            c = corrida_start(ops_user_id=uid)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/finish")
    def api_logistica_corrida_finish():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        try:
            out = corrida_finish(ops_user_id=uid)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify(dict(out))

    @app.post("/api/logistica/pedido/sinalizar")
    def api_logistica_pedido_sinalizar():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        sid = str(body.get("solicitacao_id") or "").strip()
        note = str(body.get("note") or "").strip() or None
        if not sid:
            return jsonify({"error": "solicitacao_id_ausente"}), 400
        try:
            pedido_sinalizar(ops_user_id=uid, solicitacao_id=sid, note=note)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True})

    @app.post("/api/logistica/pedido/dessinalizar")
    def api_logistica_pedido_dessinalizar():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        sid = str(body.get("solicitacao_id") or "").strip()
        pwd = str(body.get("password") or "")
        note = str(body.get("note") or "").strip() or None
        if not sid:
            return jsonify({"error": "solicitacao_id_ausente"}), 400

        if not _verify_admin_password(pwd):
            return jsonify({"error": "senha_invalida"}), 403
        try:
            pedido_dessinalizar(ops_user_id=uid, solicitacao_id=sid, note=note)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True})

    @app.post("/api/logistica/pedido/cancelar_definitivo")
    def api_logistica_pedido_cancelar_definitivo():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        sid = str(body.get("solicitacao_id") or "").strip()
        pwd = str(body.get("password") or "")
        note = str(body.get("note") or "").strip() or None
        if not sid:
            return jsonify({"error": "solicitacao_id_ausente"}), 400

        if not _verify_admin_password(pwd):
            return jsonify({"error": "senha_invalida"}), 403
        try:
            pedido_cancelar_definitivo(ops_user_id=uid, solicitacao_id=sid, note=note)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True})

    @app.post("/api/logistica/processar_pendentes")
    def api_logistica_processar_pendentes():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        try:
            processados = processar_pendentes()
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "processados": processados})

    @app.get("/api/logistica/integracoes")
    def api_logistica_integracoes():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 100)
        except Exception:
            limit = 100
        return jsonify({"ok": True, "integracoes": listar_integracoes(limit=limit)})

    @app.post("/api/logistica/integracoes/<int:integracao_id>/reprocessar")
    def api_logistica_integracao_reprocessar(integracao_id: int):
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        try:
            reprocessar_integracao(integracao_id=integracao_id)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True})

    @app.post("/api/external/logistica/status")
    def api_external_logistica_status():
        from .service import processar_webhook_central

        auth = str(request.headers.get("Authorization") or "").strip()
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1].strip()
        else:
            token = auth

        valid = False
        configured_key = str(os.environ.get("CENTRAL_LOGISTICA_API_KEY") or "").strip()
        fallback = str(os.environ.get("LOGISTICA_WEBHOOK_SECRET") or "").strip()
        if configured_key and token == configured_key:
            valid = True
        if fallback and token == fallback:
            valid = True
        if not valid:
            return jsonify({"error": "nao_autorizado"}), 401

        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"error": "payload_invalido"}), 400

        key = str(request.headers.get("X-Idempotency-Key") or "").strip() or None
        try:
            out = processar_webhook_central(payload=body, idempotency_key=key)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 503
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return jsonify(out)

    @app.get("/entregas")
    def entregas_page():
        """Logística desativada no Cardápio — redireciona para a REMO."""
        remo_url = str(os.environ.get("CENTRAL_LOGISTICA_WEBHOOK_URL") or "").strip().rstrip("/")
        if not remo_url:
            return make_response(
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<title>Logística</title></head><body style='font-family:Arial;padding:40px'>"
                "<h2>Logística centralizada</h2>"
                "<p>A logística de entregas agora é gerenciada pela Central Logística (REMO).</p>"
                "<p>Configure a variável <code>CENTRAL_LOGISTICA_WEBHOOK_URL</code> para o redirecionamento automático.</p>"
                "</body></html>",
                200,
            )
        return make_response(
            f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta http-equiv='refresh' content='0; url={remo_url}'>"
            f"<title>Redirecionando...</title></head><body style='font-family:Arial;padding:40px'>"
            f"<h2>Redirecionando para a Central Logística...</h2>"
            f"<p>Se não redirecionar automaticamente, <a href='{remo_url}'>clique aqui</a>.</p>"
            f"</body></html>",
            302,
        )
