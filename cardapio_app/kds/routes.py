from __future__ import annotations

from flask import Flask, jsonify, make_response, request, session

from ..ops_auth.routes import require_ops_login
from .service import get_pedido_atual, marcar_pronto, preparar_pedido, stats_hoje
from ..logistica.service import notificar_entregadores_pedido_pronto


def register_kds_routes(app: Flask) -> None:
    @app.get("/api/kds/pedido_atual")
    def api_kds_pedido_atual():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        pedido = get_pedido_atual(ops_user_id=uid)
        st = stats_hoje()
        return jsonify({"ok": True, "pedido": pedido, "stats": st})

    @app.post("/api/kds/<solicitacao_id>/preparar")
    def api_kds_preparar(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        preparar_pedido(solicitacao_id=solicitacao_id, ops_user_id=uid)
        return jsonify({"ok": True})

    @app.post("/api/kds/<solicitacao_id>/pronto")
    def api_kds_pronto(solicitacao_id: str):
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        marcar_pronto(solicitacao_id=solicitacao_id, ops_user_id=uid)
        try:
            notificar_entregadores_pedido_pronto(solicitacao_id=solicitacao_id, base_url=str(request.host_url or ""))
        except Exception:
            pass
        return jsonify({"ok": True})

    @app.get("/cozinha")
    def cozinha_page():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied

        html = """<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Cozinha</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:14px;background:#0b0b0c;color:#fff}
    .wrap{max-width:520px;margin:0 auto}
    .card{background:#151518;border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:12px;margin:10px 0}
    .btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
    button{flex:1;min-width:140px;font-size:16px;padding:12px;border-radius:12px;border:0;background:#fff;color:#111;font-weight:800}
    button.secondary{background:#2a2a2f;color:#fff;font-weight:700}
    .muted{opacity:.75}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <div style=\"display:flex;justify-content:space-between;align-items:center;\">
        <div>
          <div style=\"font-weight:900;font-size:18px\">Cozinha</div>
          <div class=\"muted\" style=\"font-size:13px\">Painel (em implantação)</div>
        </div>
        <form method=\"post\" action=\"/ops/logout\"><button class=\"secondary\" type=\"submit\" style=\"min-width:auto\">Sair</button></form>
      </div>
    </div>

    <div class=\"card\" id=\"pedido\">
      <div class=\"muted\" id=\"stats\">Carregando...</div>
      <div style=\"margin-top:10px\" id=\"pedido_box\"></div>
      <div class=\"btns\">
        <button id=\"btn_preparar\" type=\"button\">Preparar Pedido</button>
        <button id=\"btn_pronto\" type=\"button\" class=\"secondary\">Pedido Pronto</button>
        <button id=\"btn_proximo\" type=\"button\" class=\"secondary\">Próximo Pedido</button>
      </div>
    </div>
  </div>
  <script>
    let currentId = '';
    const statsEl = document.getElementById('stats');
    const pedidoBox = document.getElementById('pedido_box');
    const btnPreparar = document.getElementById('btn_preparar');
    const btnPronto = document.getElementById('btn_pronto');
    const btnProximo = document.getElementById('btn_proximo');

    function setButtons(disabled) {
      btnPreparar.disabled = disabled;
      btnPronto.disabled = disabled;
      btnProximo.disabled = disabled;
    }

    function renderPedido(p) {
      if (!p || !p.id) {
        currentId = '';
        pedidoBox.innerHTML = '<div class="muted">Sem pedidos na fila.</div>';
        return;
      }
      currentId = String(p.id);
      const cliente = (p.cliente_nome || '').toString();
      const tipo = (p.tipo_entrega || p.kind || '').toString();
      const status = (p.kds && p.kds.status) ? String(p.kds.status) : '';
      pedidoBox.innerHTML = ''
        + '<div style="font-weight:900;font-size:16px">Pedido ' + currentId + '</div>'
        + '<div class="muted" style="margin-top:6px">' + (cliente ? ('Cliente: ' + cliente) : '') + '</div>'
        + '<div class="muted">' + (tipo ? ('Tipo: ' + tipo) : '') + '</div>'
        + '<div class="muted">KDS: ' + status + '</div>';
    }

    async function load() {
      try {
        const resp = await fetch('/api/kds/pedido_atual', {method: 'GET'});
        const j = await resp.json().catch(() => ({}));
        if (!resp.ok || !j || j.ok !== true) {
          statsEl.innerText = 'Falha ao carregar.';
          return;
        }
        const st = j.stats || {};
        statsEl.innerText = 'Pendentes: ' + (st.pendentes ?? 0) + ' | Concluídos hoje: ' + (st.concluidos ?? 0);
        renderPedido(j.pedido);
      } catch (e) {
        statsEl.innerText = 'Falha ao carregar.';
      }
    }

    btnPreparar.addEventListener('click', async () => {
      if (!currentId) return;
      setButtons(true);
      try {
        await fetch('/api/kds/' + encodeURIComponent(currentId) + '/preparar', {method: 'POST'});
      } finally {
        setButtons(false);
        load();
      }
    });

    btnPronto.addEventListener('click', async () => {
      if (!currentId) return;
      setButtons(true);
      try {
        await fetch('/api/kds/' + encodeURIComponent(currentId) + '/pronto', {method: 'POST'});
      } finally {
        setButtons(false);
        load();
      }
    });

    btnProximo.addEventListener('click', async () => {
      load();
    });

    load();
  </script>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp
