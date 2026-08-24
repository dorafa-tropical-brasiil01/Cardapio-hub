from __future__ import annotations

from flask import Flask, jsonify, make_response, request, session

from ..ops_auth.routes import require_ops_login
from .page import kds_page_html
from .service import (
    aceitar_pedido,
    get_pedido_atual,
    listar_entregues,
    listar_fila_pedidos,
    listar_preparando_pedidos,
    listar_prontos,
    listar_recusados,
    listar_sinalizados,
    marcar_pronto,
    pular_pedido,
    recusar_pedido,
    selecionar_pedido,
    sinal_entregar,
    stats_hoje,
)


def register_kds_routes(app: Flask) -> None:
    @app.get("/api/kds/fila")
    def api_kds_fila():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return jsonify({"ok": True, "fila": listar_fila_pedidos(limit=limit)})

    @app.get("/api/kds/previas")
    def api_kds_previas():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return jsonify({"ok": True, "fila": listar_fila_pedidos(limit=limit)})

    @app.get("/api/kds/preparando")
    def api_kds_preparando():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return jsonify({"ok": True, "fila": listar_preparando_pedidos(limit=limit)})

    @app.get("/api/kds/prontos")
    def api_kds_prontos():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return jsonify({"ok": True, "fila": listar_prontos(limit=limit)})

    @app.get("/api/kds/sinalizados")
    def api_kds_sinalizados():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return jsonify({"ok": True, "fila": listar_sinalizados(limit=limit)})

    @app.get("/api/kds/entregues")
    def api_kds_entregues():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return jsonify({"ok": True, "fila": listar_entregues(limit=limit)})

    @app.get("/api/kds/recusados")
    def api_kds_recusados():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return jsonify({"ok": True, "fila": listar_recusados(limit=limit)})

    @app.post("/api/kds/<solicitacao_id>/pular")
    def api_kds_pular(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        pular_pedido(solicitacao_id=solicitacao_id)
        return jsonify({"ok": True})

    @app.post("/api/kds/<solicitacao_id>/selecionar")
    def api_kds_selecionar(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        selecionar_pedido(ops_user_id=uid, solicitacao_id=solicitacao_id)
        return jsonify({"ok": True})

    @app.get("/api/kds/pedido_atual")
    def api_kds_pedido_atual():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        pedido = get_pedido_atual(ops_user_id=uid)
        st = stats_hoje()
        return jsonify({"ok": True, "pedido": pedido, "stats": st})

    @app.get("/api/kds/stats")
    def api_kds_stats():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        st = stats_hoje()
        return jsonify({"ok": True, "stats": st})

    @app.post("/api/kds/<solicitacao_id>/aceitar")
    def api_kds_aceitar(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        impressao = body.get("impressao_solicitada_em") or None
        aceitar_pedido(
            solicitacao_id=solicitacao_id,
            ops_user_id=uid,
            impressao_solicitada_em=impressao,
        )
        return jsonify({"ok": True})

    # alias legado para a interface atual
    @app.post("/api/kds/<solicitacao_id>/preparar")
    def api_kds_preparar(solicitacao_id: str):
        return api_kds_aceitar(solicitacao_id)

    @app.post("/api/kds/<solicitacao_id>/recusar")
    def api_kds_recusar(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        body = request.get_json(silent=True) or {}
        motivo = body.get("motivo_recusa") or "OUTRO"
        nota = body.get("nota_recusa") or ""
        recusar_pedido(
            solicitacao_id=solicitacao_id,
            ops_user_id=uid,
            motivo_recusa=motivo,
            nota_recusa=nota or None,
        )
        return jsonify({"ok": True})

    @app.post("/api/kds/<solicitacao_id>/pronto")
    def api_kds_pronto(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        marcar_pronto(solicitacao_id=solicitacao_id, ops_user_id=uid)
        return jsonify({"ok": True})

    @app.post("/api/kds/<solicitacao_id>/sinal_entregar")
    def api_kds_sinal_entregar(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        sinal_entregar(solicitacao_id=solicitacao_id, ops_user_id=uid)
        return jsonify({"ok": True})

    # alias legado para a interface atual
    @app.post("/api/kds/<solicitacao_id>/entregar")
    def api_kds_entregar(solicitacao_id: str):
        return api_kds_sinal_entregar(solicitacao_id)

    @app.get("/cozinha")
    def cozinha_page():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        html = kds_page_html()
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/cozinha/manifest.json")
    def cozinha_manifest():
        manifest = {
            "name": "DoRafa Cozinha",
            "short_name": "Cozinha",
            "start_url": "/cozinha",
            "display": "minimal-ui",
            "background_color": "#0d0d0d",
            "theme_color": "#fd6300",
            "orientation": "portrait",
            "icons": [
                {"src": "/assets/KDS_COZINHA.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/assets/KDS_COZINHA.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        return jsonify(manifest)

    @app.get("/cozinha/sw.js")
    def cozinha_sw():
        js = _kds_service_worker_js()
        resp = make_response(js, 200)
        resp.headers["Content-Type"] = "application/javascript"
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/cozinha/offline.html")
    def cozinha_offline():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        html = (
            '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1" />'
            '<title>Offline</title></head><body style="font-family:Arial;padding:20px;text-align:center;">'
            '<h1>Sem conexão</h1><p>O painel da cozinha está offline. Verifique a internet e tente novamente.</p>'
            '<a href="/cozinha" style="display:inline-block;margin-top:20px;padding:12px 20px;'
            'background:#0a5c2f;color:#fff;text-decoration:none;border-radius:10px;">Tentar novamente</a>'
            '</body></html>'
        )
        resp = make_response(html, 200)
        resp.headers["Content-Type"] = "text/html"
        return resp


def _kds_service_worker_js() -> str:
    return r"""const CACHE_NAME = 'dorafa-kds-v2';
const OFFLINE_URL = '/cozinha/offline.html';
const PRECACHE = [OFFLINE_URL];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE))
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
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request).then((r) => r || caches.match(OFFLINE_URL));
    })
  );
});
"""


