from __future__ import annotations

from flask import Flask, jsonify, make_response, request, session

from ..ops_auth.routes import require_ops_login
from .service import (
    corrida_add,
    corrida_finish,
    corrida_remove,
    corrida_start,
    listar_prontos,
    obter_corrida_atual,
)


def register_logistica_routes(app: Flask) -> None:
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
        c = corrida_add(ops_user_id=uid, solicitacao_id=sid)
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
        c = corrida_remove(ops_user_id=uid, solicitacao_id=sid)
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/start")
    def api_logistica_corrida_start():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        c = corrida_start(ops_user_id=uid)
        return jsonify({"ok": True, "corrida": c})

    @app.post("/api/logistica/corrida/finish")
    def api_logistica_corrida_finish():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied
        uid = int(session.get("ops_user_id") or 0)
        out = corrida_finish(ops_user_id=uid)
        return jsonify(dict(out))

    @app.get("/entregas")
    def entregas_page():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied

        html = """<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Entregas</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:14px;background:#0b0b0c;color:#fff}
    .wrap{max-width:720px;margin:0 auto}
    .card{background:#151518;border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:12px;margin:10px 0}
    h1{font-size:18px;margin:0}
    .muted{opacity:.75}
    .list{margin-top:10px;display:flex;flex-direction:column;gap:10px}
    .item{padding:12px;border:1px solid rgba(255,255,255,0.08);border-radius:12px;background:#0f0f12}
    button{font-size:16px;padding:10px 12px;border-radius:12px;border:0;background:#fff;color:#111;font-weight:800}
    button.secondary{background:#2a2a2f;color:#fff;font-weight:700}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\" style=\"display:flex;justify-content:space-between;align-items:center;\">
      <div>
        <h1>Entregas</h1>
        <div class=\"muted\" style=\"font-size:13px\">Fila e corridas (em implantação)</div>
      </div>
      <form method=\"post\" action=\"/ops/logout\"><button class=\"secondary\" type=\"submit\">Sair</button></form>
    </div>

    <div class=\"card\">
      <div class=\"muted\">Pedidos prontos para entrega:</div>
      <div class=\"list\">
        <div class=\"muted\" id=\"prontos\">Carregando...</div>
      </div>
    </div>

    <div class=\"card\">
      <div style=\"font-weight:900\">Minha Corrida</div>
      <div class=\"muted\" id=\"corrida_meta\">Carregando...</div>
      <div class=\"list\" id=\"corrida_itens\"></div>
      <div style=\"margin-top:10px;display:flex;gap:10px;flex-wrap:wrap\">
        <button id=\"btn_start\" type=\"button\" class=\"secondary\">Iniciar Corrida</button>
        <button id=\"btn_finish\" type=\"button\" class=\"secondary\">Finalizar Corrida</button>
      </div>
    </div>
  </div>
  <script>
    const prontosEl = document.getElementById('prontos');
    const corridaMeta = document.getElementById('corrida_meta');
    const corridaItens = document.getElementById('corrida_itens');
    const btnStart = document.getElementById('btn_start');
    const btnFinish = document.getElementById('btn_finish');

    async function api(url, opts) {
      const resp = await fetch(url, opts || {method:'GET'});
      const j = await resp.json().catch(()=>({}));
      if (!resp.ok) throw j;
      return j;
    }

    function renderProntos(pedidos) {
      const arr = Array.isArray(pedidos) ? pedidos : [];
      if (arr.length === 0) {
        prontosEl.innerHTML = '<div class="muted">Nenhum pedido pronto.</div>';
        return;
      }
      prontosEl.innerHTML = arr.map(p => {
        const id = (p && p.id) ? String(p.id) : '';
        const cliente = (p && p.cliente_nome) ? String(p.cliente_nome) : '';
        const obs = (p && (p.observacoes || p.obs || p.observacao)) ? String(p.observacoes || p.obs || p.observacao) : '';
        const endereco = (p && (p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco)))
          ? String(p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco))
          : '';
        const itens = Array.isArray(p && p.itens) ? p.itens : [];
        const itensHtml = itens.slice(0, 20).map(it => {
          const nome = (it && it.nome) ? String(it.nome) : '';
          const code = (it && (it.product_code || it.pdvCode)) ? String(it.product_code || it.pdvCode) : '';
          const qty = (it && (it.qty || it.quantidade)) ? String(it.qty || it.quantidade) : '';
          const label = nome || code || 'Item';
          return '<div class="muted">- ' + label + (qty ? (' x' + qty) : '') + '</div>';
        }).join('');
        return '<div class="item">'
          + '<div style="font-weight:900">Pedido ' + id + '</div>'
          + (cliente ? ('<div class="muted">Cliente: ' + cliente + '</div>') : '')
          + (endereco ? ('<div class="muted">Endereço: ' + endereco + '</div>') : '')
          + (obs ? ('<div class="muted">Obs: ' + obs + '</div>') : '')
          + (itensHtml ? ('<div style="margin-top:8px"><div style="font-weight:800">Itens</div>' + itensHtml + '</div>') : '')
          + '<div style="margin-top:10px"><button type="button" data-id="' + id + '">Aceitar</button></div>'
          + '</div>';
      }).join('');
      prontosEl.querySelectorAll('button[data-id]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-id');
          if (!sid) return;
          btn.disabled = true;
          try {
            await api('/api/logistica/corrida/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({solicitacao_id: sid})});
            await load();
          } finally {
            btn.disabled = false;
          }
        });
      });
    }

    function renderCorrida(c) {
      if (!c || !c.id) {
        corridaMeta.innerText = 'Sem corrida.';
        corridaItens.innerHTML = '';
        return;
      }
      corridaMeta.innerText = 'Corrida #' + c.id + ' | Status: ' + (c.status || '');
      const items = Array.isArray(c.items) ? c.items : [];
      if (items.length === 0) {
        corridaItens.innerHTML = '<div class="muted" style="margin-top:10px">Nenhum pedido selecionado.</div>';
        return;
      }
      corridaItens.innerHTML = items.map(it => {
        const sid = (it && it.solicitacao_id) ? String(it.solicitacao_id) : '';
        const p = (it && it.pedido) ? it.pedido : null;
        const cliente = (p && p.cliente_nome) ? String(p.cliente_nome) : '';
        const obs = (p && (p.observacoes || p.obs || p.observacao)) ? String(p.observacoes || p.obs || p.observacao) : '';
        const endereco = (p && (p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco)))
          ? String(p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco))
          : '';
        const itens = Array.isArray(p && p.itens) ? p.itens : [];
        const itensHtml = itens.slice(0, 20).map(it2 => {
          const nome = (it2 && it2.nome) ? String(it2.nome) : '';
          const code = (it2 && (it2.product_code || it2.pdvCode)) ? String(it2.product_code || it2.pdvCode) : '';
          const qty = (it2 && (it2.qty || it2.quantidade)) ? String(it2.qty || it2.quantidade) : '';
          const label = nome || code || 'Item';
          return '<div class="muted">- ' + label + (qty ? (' x' + qty) : '') + '</div>';
        }).join('');
        return '<div class="item">'
          + '<div style="font-weight:900">Pedido ' + sid + '</div>'
          + (cliente ? ('<div class="muted">Cliente: ' + cliente + '</div>') : '')
          + (endereco ? ('<div class="muted">Endereço: ' + endereco + '</div>') : '')
          + (obs ? ('<div class="muted">Obs: ' + obs + '</div>') : '')
          + (itensHtml ? ('<div style="margin-top:8px"><div style="font-weight:800">Itens</div>' + itensHtml + '</div>') : '')
          + '<div style="margin-top:10px"><button type="button" class="secondary" data-remove="' + sid + '">Remover</button></div>'
          + '</div>';
      }).join('');
      corridaItens.querySelectorAll('button[data-remove]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-remove');
          if (!sid) return;
          btn.disabled = true;
          try {
            await api('/api/logistica/corrida/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({solicitacao_id: sid})});
            await load();
          } finally {
            btn.disabled = false;
          }
        });
      });
    }

    async function load() {
      try {
        const p = await api('/api/logistica/prontos');
        renderProntos(p.pedidos);
      } catch (e) {
        prontosEl.innerText = 'Falha ao carregar prontos.';
      }

      try {
        const c = await api('/api/logistica/corrida');
        renderCorrida(c.corrida);
      } catch (e) {
        corridaMeta.innerText = 'Falha ao carregar corrida.';
      }
    }

    btnStart.addEventListener('click', async () => {
      btnStart.disabled = true;
      try {
        await api('/api/logistica/corrida/start', {method:'POST'});
        await load();
      } finally {
        btnStart.disabled = false;
      }
    });

    btnFinish.addEventListener('click', async () => {
      btnFinish.disabled = true;
      try {
        await api('/api/logistica/corrida/finish', {method:'POST'});
        await load();
      } finally {
        btnFinish.disabled = false;
      }
    });

    load();
  </script>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp
