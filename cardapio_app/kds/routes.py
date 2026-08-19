from __future__ import annotations

from flask import Flask, jsonify, make_response, request, session

from ..ops_auth.routes import require_ops_login
from .service import (
    aceitar_pedido,
    get_pedido_atual,
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

        # A interface existente será reescrita nas Fases 5-7.
        # Por ora, mantemos o HTML legado para não quebrar a experiência.
        html = _cozinha_html_legacy()
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp


def _cozinha_html_legacy() -> str:
    return r"""<!doctype html>
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

    <div class="card" id="stats">
      <div class="muted">Carregando...</div>
    </div>
    <div id="pedidos_box"></div>
  </div>
  <script>
    const statsEl = document.getElementById('stats');
    const pedidosBox = document.getElementById('pedidos_box');

    function safeText(x) {
      return (x === null || x === undefined) ? '' : String(x);
    }

    function waUrl(phone, msg) {
      const originalPhone = phone;
      const digits = String(phone || '').replace(/\D+/g, '');
      if (!digits) return '';
      if (digits.length < 10) return '';
      if (digits.length > 13) return '';
      let urlDigits = digits;
      if (!digits.startsWith('55')) {
        urlDigits = '55' + digits;
      }
      if (urlDigits.length < 12 || urlDigits.length > 13) return '';
      let url = 'https://wa.me/' + urlDigits;
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

    function renderPedidoCard(p) {
      if (!p || !p.id) return '';
      const id = String(p.id);
      const cliente = safeText(p.cliente_nome);
      const whatsapp = safeText(p.cliente_whatsapp);
      const tipo = safeText(p.tipo_entrega || p.kind);
      const status = (p.kds && p.kds.status) ? String(p.kds.status) : 'NOVO';
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

      const statusMap = {
        'NOVO': { label: 'NOVO', cls: 'background:rgba(10, 92, 47, 0.08);border-color:rgba(10, 92, 47, 0.35);color:var(--verde)' },
        'EM_PREPARO': { label: 'EM PREPARO', cls: 'background:var(--amarelo);border-color:var(--verde);color:var(--verde)' },
        'PRONTO': { label: 'PRONTO', cls: 'background:var(--verde);border-color:var(--verde);color:#fff' },
        'SINALIZADO': { label: 'SINALIZADO', cls: 'background:#1565c0;border-color:#1565c0;color:#fff' },
        'RECUSADO': { label: 'RECUSADO', cls: 'background:#e03131;border-color:#e03131;color:#fff' },
      };
      const st = statusMap[status] || { label: status, cls: 'background:rgba(10, 92, 47, 0.08);border-color:rgba(10, 92, 47, 0.35);color:var(--verde)' };

      let buttons = '';
      if (status === 'NOVO' || status === 'AGUARDANDO') {
        buttons = '<button type="button" class="secondary" data-preparar="' + id + '">Preparar</button>';
      } else if (status === 'EM_PREPARO') {
        buttons = '<button type="button" class="secondary" data-pronto="' + id + '">Pronto</button>';
      } else if (status === 'PRONTO') {
        buttons = '<button type="button" class="secondary" data-entregar="' + id + '">Sinal entregar</button>';
      }

      let html = '<div class="card" data-pedido-id="' + id + '">';
      html += '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px">';
      html += '<div style="font-weight:900;font-size:16px">Pedido #' + id + '</div>';
      html += '<span class="pill" style="' + st.cls + '">' + st.label + '</span>';
      html += '</div>';
      if (cliente) html += '<div class="muted" style="margin-top:6px">Cliente: ' + cliente + '</div>';
      if (tipo) html += '<div class="muted">Tipo: ' + tipo + '</div>';
      if (p.mesa) html += '<div class="muted">Mesa: ' + p.mesa + '</div>';
      if (addr && addr.text) {
        html += '<div style="margin-top:8px"><div style="font-weight:800">Endereço</div><div class="muted">' + safeText(addr.text).replace(/\n/g,'<br/>') + '</div></div>';
      }
      if (obs) {
        html += '<div style="margin-top:10px"><div style="font-weight:800">Observações</div><div class="muted">' + obs + '</div></div>';
      }
      html += '<div style="margin-top:10px">' + renderItens(p.itens) + '</div>';

      if (whatsapp) {
        const url = waUrl(whatsapp, 'Olá! Estamos entrando em contato sobre seu pedido.');
        if (url) {
          html += '<div style="margin-top:10px"><a class="wa discreet" target="_blank" rel="noopener" href="' + url + '">'
            + '<span aria-hidden="true" style="font-size:16px">🟢</span>'
            + '<span>Falar com o Cliente</span>'
            + '</a></div>';
        }
      }

      if (buttons) {
        html += '<div class="btns" style="margin-top:10px">' + buttons + '</div>';
      }

      html += '</div>';
      return html;
    }

    async function load() {
      try {
        const [resp, prepResp] = await Promise.all([
          fetch('/api/kds/fila?limit=50', {method: 'GET'}),
          fetch('/api/kds/preparando?limit=50', {method: 'GET'})
        ]);

        const j = await resp.json().catch(() => ({}));
        const prepJ = await prepResp.json().catch(() => ({}));

        if (!resp.ok || !j || j.ok !== true) {
          statsEl.innerHTML = '<div class="muted">Falha ao carregar</div>';
          pedidosBox.innerHTML = '';
          return;
        }

        const stResp = await fetch('/api/kds/stats', {method: 'GET'});
        const stJ = await stResp.json().catch(() => ({}));
        if (stResp.ok && stJ && stJ.ok === true) {
          const st = stJ.stats || {};
          const pend = st.pendentes || 0;
          const prontos = st.prontos || 0;
          const sinalizados = st.sinalizados || 0;
          statsEl.innerHTML = '<div class="muted">Pendentes: ' + pend + ' | Prontos: ' + prontos + ' | Sinalizados: ' + sinalizados + '</div>';
        }

        const fila = j.fila || [];
        const preparando = (prepJ && prepJ.ok === true) ? (prepJ.fila || []) : [];

        let html = '';

        if (fila.length > 0) {
          html += '<div style="font-weight:900;font-size:16px;margin:12px 0 8px 0">NOVOS</div>';
          html += fila.map(p => renderPedidoCard(p)).join('');
        }

        if (preparando.length > 0) {
          html += '<div style="font-weight:900;font-size:16px;margin:20px 0 8px 0">EM PREPARO</div>';
          html += preparando.map(p => renderPedidoCard(p)).join('');
        }

        if (fila.length === 0 && preparando.length === 0) {
          pedidosBox.innerHTML = '<div class="muted">Nenhum pedido na fila.</div>';
          return;
        }

        pedidosBox.innerHTML = html;

        pedidosBox.querySelectorAll('button[data-preparar]').forEach(btn => {
          btn.addEventListener('click', async () => {
            const sid = btn.getAttribute('data-preparar');
            if (!sid) return;
            btn.disabled = true;
            try {
              await fetch('/api/kds/' + encodeURIComponent(sid) + '/preparar', {method: 'POST'});
              await load();
            } finally {
              btn.disabled = false;
            }
          });
        });

        pedidosBox.querySelectorAll('button[data-pronto]').forEach(btn => {
          btn.addEventListener('click', async () => {
            const sid = btn.getAttribute('data-pronto');
            if (!sid) return;
            btn.disabled = true;
            try {
              await fetch('/api/kds/' + encodeURIComponent(sid) + '/pronto', {method: 'POST'});
              await load();
            } finally {
              btn.disabled = false;
            }
          });
        });

        pedidosBox.querySelectorAll('button[data-entregar]').forEach(btn => {
          btn.addEventListener('click', async () => {
            const sid = btn.getAttribute('data-entregar');
            if (!sid) return;
            btn.disabled = true;
            try {
              await fetch('/api/kds/' + encodeURIComponent(sid) + '/entregar', {method: 'POST'});
              await load();
            } finally {
              btn.disabled = false;
            }
          });
        });

      } catch (e) {
        statsEl.innerHTML = '<div class="muted">Falha ao carregar: erro de rede.</div>';
        pedidosBox.innerHTML = '';
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

    startAutoRefresh();
  </script>
</body>
</html>"""
