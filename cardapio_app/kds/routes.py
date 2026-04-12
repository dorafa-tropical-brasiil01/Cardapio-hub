from __future__ import annotations

from flask import Flask, jsonify, make_response, request, session

from ..ops_auth.routes import require_ops_login
from .service import (
    get_pedido_atual,
    listar_fila_pedidos,
    marcar_pronto,
    preparar_pedido,
    pular_pedido,
    selecionar_pedido,
    stats_hoje,
)
from ..logistica.service import notificar_entregadores_pedido_pronto


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

        html = r"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Cozinha</title>
  <style>
    :root{
      --verde: #0a5c2f;
      --amarelo: #fefecf;
      --bg: #d9f3a2;
      --bg2: #f6e27f;
      --card: rgba(254, 254, 207, 0.92);
      --card2: rgba(254, 254, 207, 0.78);
      --border: rgba(10, 92, 47, 0.35);
      --text: #0a5c2f;
    }
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:14px;background:var(--bg);background-color:var(--bg);color:var(--text);line-height:1.35;padding-bottom:calc(86px + 18px + env(safe-area-inset-bottom))}
    .wrap{max-width:760px;margin:0 auto}
    .card{background:var(--card);border:2px solid var(--border);border-radius:20px;padding:14px;margin:12px 0;box-sizing:border-box}
    .topbar{position:sticky;top:-1px;z-index:10;padding:12px 0;background:var(--bg);background-color:var(--bg)}
    .topbar .inner{max-width:760px;margin:0 auto;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;background:var(--card);border:2px solid var(--border);border-radius:20px;box-sizing:border-box}
    .top-title{font-weight:900;font-size:18px}
    .top-sub{opacity:.75;font-size:12px;margin-top:2px}
    .btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
    button{flex:1;min-width:140px;font-size:16px;padding:15px 18px;border-radius:20px;border:0;background:var(--verde);color:#fff;font-weight:900;cursor:pointer}
    button.secondary{background:rgba(10, 92, 47, 0.08);border:2px solid rgba(10, 92, 47, 0.35);color:var(--verde);font-weight:900}
    button:disabled{opacity:.55}
    a.wa{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;background:#2f9e44;color:#fff;padding:15px 18px;border-radius:20px;font-weight:900;width:100%;box-sizing:border-box;overflow-wrap:anywhere;word-break:break-word;text-align:center}
    a.wa.discreet{padding:14px 16px;font-weight:900;opacity:1}
    a.maps{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;background:rgba(10, 92, 47, 0.08);border:2px solid rgba(10, 92, 47, 0.35);color:var(--verde);padding:15px 18px;border-radius:20px;font-weight:900;width:100%;box-sizing:border-box;overflow-wrap:anywhere;word-break:break-word;text-align:center}
    .muted{opacity:.78;overflow-wrap:anywhere;word-break:break-word}

    .queue-item{padding:12px;margin:10px 0;background:var(--card2);border:2px solid rgba(10, 92, 47, 0.22);border-radius:18px}
    .queue-item.selected{border-color:rgba(47,158,68,0.75);box-shadow:0 0 0 3px rgba(47,158,68,0.14) inset}
    .pill{display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:900;padding:4px 10px;border-radius:999px;border:1px solid rgba(255,255,255,0.14);background:rgba(255,255,255,0.06)}
    .pill{background:rgba(10, 92, 47, 0.08);border:1px solid rgba(10, 92, 47, 0.35);color:var(--verde)}
    .pill.sel{background:var(--verde);border-color:var(--verde);color:#fff}

    #bottomBar{position:fixed;left:0;right:0;bottom:0;height:86px;background:var(--verde);z-index:998;display:flex;align-items:center;padding:10px 12px;padding-bottom:calc(10px + env(safe-area-inset-bottom));box-sizing:border-box}
    #bottomBarInner{width:min(920px, 92%);margin:0 auto;display:flex;gap:10px;align-items:center;justify-content:stretch}
    .bottom-action{flex:1 1 0;min-width:0;background:var(--amarelo);color:var(--verde);border:none;border-radius:14px;height:46px;padding:0 10px;font-size:16px;font-weight:900;cursor:pointer;box-shadow:0 10px 22px rgba(0,0,0,0.18);user-select:none;-webkit-tap-highlight-color:transparent;white-space:nowrap;display:flex;align-items:center;justify-content:center;gap:8px;box-sizing:border-box}
    .bottom-action.secondary{background:rgba(254,254,207,0.92)}

    @media (max-width: 520px) {
      body{padding:12px;padding-bottom:calc(66px + 18px + env(safe-area-inset-bottom))}
      .card{padding:12px}
      .topbar .inner{padding:10px 12px;margin:0 12px}
      button{min-width:0;font-size:16px;padding:14px 14px}
      .btns button{flex:1 1 46%}
      .btns button#btn_preparar{flex-basis:100%}
      #bottomBar{height:66px}
      #bottomBarInner{width:92%;gap:6px}
      .bottom-action{height:42px;font-size:14px;padding:0 8px;gap:6px;border-radius:12px}
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="inner">
      <div>
        <div class="top-title">Cozinha</div>
        <div class="top-sub">Painel operacional</div>
      </div>
      <form method="post" action="/ops/logout"><button class="secondary" type="submit" style="min-width:auto">Sair</button></form>
    </div>
  </div>

  <div class="wrap">

    <div class="card" id="pedido">
      <div class="muted" id="stats">Carregando...</div>
      <div style="margin-top:10px" id="pedido_box"></div>
      <div style="margin-top:10px" id="wa_box"></div>
      <div style="margin-top:12px" id="fila_box"></div>
    </div>
  </div>

  <div id="bottomBar">
    <div id="bottomBarInner">
      <button id="btn_preparar" type="button" class="bottom-action">Preparar</button>
      <button id="btn_pronto" type="button" class="bottom-action secondary">Pronto</button>
      <button id="btn_proximo" type="button" class="bottom-action secondary">Próximo</button>
    </div>
  </div>
  <script>
    let currentId = '';
    const statsEl = document.getElementById('stats');
    const pedidoBox = document.getElementById('pedido_box');
    const waBox = document.getElementById('wa_box');
    const filaBox = document.getElementById('fila_box');
    const btnPreparar = document.getElementById('btn_preparar');
    const btnPronto = document.getElementById('btn_pronto');
    const btnProximo = document.getElementById('btn_proximo');

    function setButtons(disabled) {
      btnPreparar.disabled = disabled;
      btnPronto.disabled = disabled;
      btnProximo.disabled = disabled;
    }

    function safeText(x) {
      return (x === null || x === undefined) ? '' : String(x);
    }

    function waUrl(phone, msg) {
      const digits = String(phone || '').replace(/\\D+/g, '');
      if (!digits) return '';
      let url = 'https://wa.me/' + digits;
      const m = String(msg || '').trim();
      if (m) url += '?text=' + encodeURIComponent(m);
      return url;
    }

    function renderItens(itens) {
      const arr = Array.isArray(itens) ? itens : [];
      if (arr.length === 0) return '<div class="muted">Itens: (não informado)</div>';
      const lines = arr.slice(0, 30).map(it => {
        const nome = safeText(it && it.nome);
        const code = safeText(it && (it.product_code || it.pdvCode));
        const qty = safeText(it && (it.qty || it.quantidade));
        const label = nome || code || 'Item';
        return '<div class="muted">- ' + label + (qty ? (' x' + qty) : '') + '</div>';
      });
      return '<div style="margin-top:8px"><div style="font-weight:800">Itens</div>' + lines.join('') + '</div>';
    }

    function renderPedido(p) {
      if (!p || !p.id) {
        currentId = '';
        pedidoBox.innerHTML = '<div class="muted">Sem pedidos na fila.</div>';
        if (waBox) waBox.innerHTML = '';
        return;
      }
      currentId = String(p.id);
      const cliente = safeText(p.cliente_nome);
      const whatsapp = safeText(p.cliente_whatsapp);
      const tipo = safeText(p.tipo_entrega || p.kind);
      const status = (p.kds && p.kds.status) ? String(p.kds.status) : '';
      const obs = safeText(p.observacoes || p.obs || p.observacao);
      const enderecoRaw = (p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco));
      const addr = (() => {
        if (!enderecoRaw) return {text:'', maps:''};
        if (typeof enderecoRaw === 'string') return {text: safeText(enderecoRaw), maps:''};
        if (typeof enderecoRaw !== 'object') return {text:'', maps:''};
        const maps = safeText(enderecoRaw.maps_url || enderecoRaw.maps || enderecoRaw.localizacao);
        const rua = safeText(enderecoRaw.rua);
        const numero = safeText(enderecoRaw.numero);
        const bairro = safeText(enderecoRaw.bairro);
        const cidade = safeText(enderecoRaw.cidade);
        const ref = safeText(enderecoRaw.referencia);
        const parts = [];
        if (rua || numero) parts.push((rua + (numero ? (', ' + numero) : '')).trim());
        if (bairro) parts.push(bairro);
        if (cidade) parts.push(cidade);
        const line = parts.join(' - ').trim();
        const out = [];
        if (line) out.push(line);
        if (ref) out.push('Ref: ' + ref);
        return {text: out.join('\n').trim(), maps: safeText(maps).trim()};
      })();
      const headLines = [];
      headLines.push('<div style="font-weight:900;font-size:16px">Pedido</div>');
      if (cliente) headLines.push('<div class="muted" style="margin-top:6px">Cliente: ' + cliente + '</div>');
      if (tipo) headLines.push('<div class="muted">Tipo: ' + tipo + '</div>');
      if (status) headLines.push('<div class="muted">KDS: ' + status + '</div>');
      if (whatsapp) headLines.push('<div class="muted">WhatsApp: ' + whatsapp + '</div>');

      pedidoBox.innerHTML = headLines.join('');

      if (addr && addr.text) {
        pedidoBox.innerHTML += '<div style="margin-top:8px"><div style="font-weight:800">Endereço</div><div class="muted">' + safeText(addr.text).replace(/\n/g,'<br/>') + '</div></div>';
      }
      if (addr && addr.maps) {
        pedidoBox.innerHTML += '<div style="margin-top:10px"><a class="maps" target="_blank" rel="noopener" href="' + safeText(addr.maps) + '"><span style="opacity:.9">MAPS</span><span>Abrir Localização</span></a></div>';
      }
      if (obs) {
        pedidoBox.innerHTML += '<div style="margin-top:10px"><div style="font-weight:800">Observações</div><div class="muted">' + obs + '</div></div>';
      }
      pedidoBox.innerHTML += '<div style="margin-top:10px">' + renderItens(p.itens) + '</div>';

      if (waBox) {
        const url = waUrl(whatsapp, 'Olá! 😊 Estamos entrando em contato sobre seu pedido.');
        if (url) {
          waBox.innerHTML = '<a class="wa discreet" target="_blank" rel="noopener" href="' + url + '">'
            + '<span aria-hidden="true" style="font-size:16px">🟢</span>'
            + '<span>Falar com o Cliente</span>'
            + '</a>';
        } else {
          waBox.innerHTML = '';
        }
      }
    }

    function renderFila(fila) {
      const arr = Array.isArray(fila) ? fila : [];
      if (arr.length === 0) {
        filaBox.innerHTML = '';
        return;
      }
      const top = arr.slice(0, 8);
      filaBox.innerHTML = '<div style="margin-top:8px"><div style="font-weight:900">Fila</div>'
        + top.map(p => {
          const id = (p && p.id) ? String(p.id) : '';
          const cliente = safeText(p && p.cliente_nome);
          const isSel = (currentId && id && String(id) === String(currentId));
          const pill = isSel ? '<span class="pill sel" style="margin-left:8px">SELECIONADO</span>' : '';
          return '<div class="queue-item' + (isSel ? ' selected' : '') + '">'
            + '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px">'
            + '<div style="font-weight:900">Pedido' + pill + '</div>'
            + '</div>'
            + (cliente ? ('<div class="muted" style="margin-top:6px">Cliente: ' + cliente + '</div>') : '')
            + '<div class="btns" style="margin-top:10px">'
            + '<button type="button" class="secondary" data-select="' + id + '"' + (isSel ? ' disabled' : '') + '>Selecionar</button>'
            + '<button type="button" class="secondary" data-skip="' + id + '">Pular</button>'
            + '</div>'
            + '</div>';
        }).join('')
        + '</div>';

      filaBox.querySelectorAll('button[data-select]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-select');
          if (!sid) return;
          btn.disabled = true;
          try {
            currentId = String(sid);
            await fetch('/api/kds/' + encodeURIComponent(sid) + '/selecionar', {method: 'POST'});
            await load();
          } finally {
            btn.disabled = false;
          }
        });
      });

      filaBox.querySelectorAll('button[data-skip]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-skip');
          if (!sid) return;
          btn.disabled = true;
          try {
            await fetch('/api/kds/' + encodeURIComponent(sid) + '/pular', {method: 'POST'});
            await load();
          } finally {
            btn.disabled = false;
          }
        });
      });
    }

    async function load() {
      try {
        const resp = await fetch('/api/kds/pedido_atual', {method: 'GET'});
        const j = await resp.json().catch(() => ({}));
        if (!resp.ok || !j || j.ok !== true) {
          const err = (j && (j.error || j.message)) ? String(j.error || j.message) : ('HTTP ' + resp.status);
          statsEl.innerText = 'Falha ao carregar: ' + err;
          return;
        }
        const st = j.stats || {};
        const pend = (st && st.pendentes !== undefined && st.pendentes !== null) ? st.pendentes : 0;
        const conc = (st && st.concluidos !== undefined && st.concluidos !== null) ? st.concluidos : 0;
        statsEl.innerText = 'Pendentes: ' + pend + ' | Concluídos hoje: ' + conc;
        if (currentId && (!j.pedido || String(j.pedido.id) !== String(currentId))) {
          // mantém seleção manual se existir (quando usuário escolhe na fila)
          // tenta buscar a fila para renderizar e mostrar o selecionado
        }
        renderPedido(j.pedido);
        try {
          const fr = await fetch('/api/kds/fila?limit=20', {method: 'GET'});
          const fj = await fr.json().catch(() => ({}));
          if (fr.ok && fj && fj.ok === true) {
            renderFila(fj.fila);
          }
        } catch (e) {
          // ignore
        }
      } catch (e) {
        statsEl.innerText = 'Falha ao carregar: erro de rede.';
      }
    }

    function startAutoRefresh() {
      try {
        load();
        setInterval(() => {
          try { load(); } catch (e) {}
        }, 2500);
      } catch (e) {
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
      if (!currentId) {
        load();
        return;
      }
      setButtons(true);
      try {
        await fetch('/api/kds/' + encodeURIComponent(currentId) + '/pular', {method: 'POST'});
      } finally {
        setButtons(false);
        load();
      }
    });

    startAutoRefresh();
  </script>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp
