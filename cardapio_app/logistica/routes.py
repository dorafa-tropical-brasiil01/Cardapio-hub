from __future__ import annotations

from flask import Flask, jsonify, make_response, request, session

from ..ops_auth.routes import require_ops_login
from .service import (
    corrida_add,
    corrida_devolver,
    corrida_finish,
    corrida_marcar_entregue,
    corrida_nova,
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

    @app.get("/entregas")
    def entregas_page():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied

        html = r"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Entregas</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:14px;background:#0b0b0c;color:#fff}
    .wrap{max-width:720px;margin:0 auto}
    .card{background:#151518;border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:12px;margin:10px 0}
    h1{font-size:18px;margin:0}
    .muted{opacity:.75}
    .list{margin-top:10px;display:flex;flex-direction:column;gap:10px}
    .item{padding:12px;border:1px solid rgba(255,255,255,0.08);border-radius:12px;background:#0f0f12}
    .item.delivered{opacity:.72;border-color:rgba(255,255,255,0.14)}
    button{font-size:16px;padding:10px 12px;border-radius:12px;border:0;background:#fff;color:#111;font-weight:800}
    button.secondary{background:#2a2a2f;color:#fff;font-weight:700}
    a.wa{display:inline-flex;align-items:center;gap:8px;text-decoration:none;background:#0f2a17;border:1px solid rgba(37,211,102,0.25);color:#d9ffe8;padding:10px 12px;border-radius:12px;font-weight:900}
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
      <div id=\"toast\" class=\"card\" style=\"display:none;margin-top:10px;background:#2a1b1b;border-color:rgba(255,0,0,0.25);\"></div>
      <div class=\"muted\" id=\"corrida_meta\">Carregando...</div>
      <div class=\"list\" id=\"corrida_itens\"></div>
      <div style=\"margin-top:10px;display:flex;gap:10px;flex-wrap:wrap\">
        <button id=\"btn_start\" type=\"button\" class=\"secondary\">Iniciar Corrida</button>
        <button id=\"btn_finish\" type=\"button\" class=\"secondary\">Finalizar Corrida</button>
        <button id=\"btn_new\" type=\"button\" class=\"secondary\">Nova Corrida</button>
      </div>
    </div>
  </div>
  <script>
    const prontosEl = document.getElementById('prontos');
    const corridaMeta = document.getElementById('corrida_meta');
    const corridaItens = document.getElementById('corrida_itens');
    const btnStart = document.getElementById('btn_start');
    const btnFinish = document.getElementById('btn_finish');
    const btnNew = document.getElementById('btn_new');
    const toastEl = document.getElementById('toast');

    let corridaTimerHandle = null;
    let corridaSnapshot = null;

    function showToast(msg) {
      const t = String(msg || '').trim();
      if (!toastEl) return;
      if (!t) { toastEl.style.display = 'none'; toastEl.innerText = ''; return; }
      toastEl.style.display = 'block';
      toastEl.innerText = t;
      setTimeout(() => {
        if (!toastEl) return;
        toastEl.style.display = 'none';
        toastEl.innerText = '';
      }, 5500);
    }

    function waUrl(phone, msg) {
      const digits = String(phone || '').replace(/\\D+/g, '');
      if (!digits) return '';
      let url = 'https://wa.me/' + digits;
      const m = String(msg || '').trim();
      if (m) url += '?text=' + encodeURIComponent(m);
      return url;
    }

    async function api(url, opts) {
      const resp = await fetch(url, opts || {method:'GET'});
      const j = await resp.json().catch(()=>({}));
      if (!resp.ok) {
        const err = (j && j.error) ? j.error : 'erro';
        throw {error: err};
      }
      return j;
    }

    function applyButtonsByStatus(c) {
      const status = String((c && c.status) || '').toUpperCase();
      const hasRun = !!(c && c.id);
      const items = (c && Array.isArray(c.items)) ? c.items : [];

      if (!hasRun) {
        btnStart.disabled = true;
        btnFinish.disabled = true;
        btnNew.disabled = false;
        return;
      }

      if (status === 'MONTANDO') {
        btnStart.disabled = (items.length === 0);
        btnFinish.disabled = true;
        btnNew.disabled = false;
        return;
      }

      if (status === 'EM_ANDAMENTO') {
        btnStart.disabled = true;
        btnFinish.disabled = false;
        btnNew.disabled = true;
        return;
      }

      if (status === 'FINALIZADA') {
        btnStart.disabled = true;
        btnFinish.disabled = true;
        btnNew.disabled = false;
        return;
      }

      btnStart.disabled = true;
      btnFinish.disabled = true;
      btnNew.disabled = false;
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
        const whatsapp = (p && p.cliente_whatsapp) ? String(p.cliente_whatsapp) : '';
        const obs = (p && (p.observacoes || p.obs || p.observacao)) ? String(p.observacoes || p.obs || p.observacao) : '';
        const enderecoRaw = (p && (p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco))) || null;
        const endereco = (() => {
          if (!enderecoRaw) return '';
          if (typeof enderecoRaw === 'string') return String(enderecoRaw);
          if (typeof enderecoRaw !== 'object') return '';
          const maps = String(enderecoRaw.maps_url || enderecoRaw.maps || enderecoRaw.localizacao || '').trim();
          const rua = String(enderecoRaw.rua || '').trim();
          const numero = String(enderecoRaw.numero || '').trim();
          const bairro = String(enderecoRaw.bairro || '').trim();
          const cidade = String(enderecoRaw.cidade || '').trim();
          const ref = String(enderecoRaw.referencia || '').trim();
          const parts = [];
          if (rua || numero) parts.push((rua + (numero ? (', ' + numero) : '')).trim());
          if (bairro) parts.push(bairro);
          if (cidade) parts.push(cidade);
          const line = parts.join(' - ').trim();
          const out = [];
          if (line) out.push(line);
          if (ref) out.push('Ref: ' + ref);
          if (maps) out.push(maps);
          return out.join(' | ').trim();
        })();
        const itens = Array.isArray(p && p.itens) ? p.itens : [];
        const itensHtml = itens.slice(0, 20).map(it => {
          const nome = (it && it.nome) ? String(it.nome) : '';
          const code = (it && (it.product_code || it.pdvCode)) ? String(it.product_code || it.pdvCode) : '';
          const qty = (it && (it.qty || it.quantidade)) ? String(it.qty || it.quantidade) : '';
          const label = nome || code || 'Item';
          return '<div class="muted">- ' + label + (qty ? (' x' + qty) : '') + '</div>';
        }).join('');
        const wa = waUrl(whatsapp, 'Olá! 😊 Estamos entrando em contato sobre seu pedido.');
        const waHtml = wa ? ('<div style="margin-top:10px"><a class="wa" target="_blank" rel="noopener" href="' + wa + '"><span style="opacity:.9">WA</span><span>Falar com o Cliente</span></a></div>') : '';
        return '<div class="item">'
          + '<div style="font-weight:900">Pedido ' + id + '</div>'
          + (cliente ? ('<div class="muted">Cliente: ' + cliente + '</div>') : '')
          + (endereco ? ('<div class="muted">Endereço: ' + endereco + '</div>') : '')
          + (obs ? ('<div class="muted">Obs: ' + obs + '</div>') : '')
          + (itensHtml ? ('<div style="margin-top:8px"><div style="font-weight:800">Itens</div>' + itensHtml + '</div>') : '')
          + waHtml
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
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao aceitar pedido.');
          } finally {
            btn.disabled = false;
          }
        });
      });
    }

    function renderCorrida(c) {
      corridaSnapshot = c || null;
      if (!c || !c.id) {
        corridaMeta.innerText = 'Sem corrida.';
        corridaItens.innerHTML = '';
        if (corridaTimerHandle) { clearInterval(corridaTimerHandle); corridaTimerHandle = null; }
        applyButtonsByStatus(null);
        return;
      }
      const r = (c && c.resumo) ? c.resumo : null;
      const resumoTxt = (r && (r.total !== undefined))
        ? (' | Itens: ' + ((r.total !== undefined && r.total !== null) ? r.total : 0)
          + ' | Entregues: ' + ((r.entregues !== undefined && r.entregues !== null) ? r.entregues : 0)
          + ' | Pendentes: ' + ((r.pendentes !== undefined && r.pendentes !== null) ? r.pendentes : 0))
        : '';

      const isRunning = (String(c.status || '').toUpperCase() === 'EM_ANDAMENTO');
      const startedEm = (c && c.started_em) ? String(c.started_em) : '';
      const tempoTxt = (isRunning && startedEm) ? (' | Tempo: ' + formatElapsedFromIso(startedEm)) : '';
      corridaMeta.innerText = 'Corrida #' + c.id + ' | Status: ' + (c.status || '') + tempoTxt + resumoTxt;
      applyButtonsByStatus(c);

      if (corridaTimerHandle) { clearInterval(corridaTimerHandle); corridaTimerHandle = null; }
      if (isRunning && startedEm) {
        corridaTimerHandle = setInterval(() => {
          if (!corridaSnapshot || !corridaSnapshot.id) return;
          const rr = (corridaSnapshot && corridaSnapshot.resumo) ? corridaSnapshot.resumo : null;
          const resumoTxt2 = (rr && (rr.total !== undefined))
            ? (' | Itens: ' + ((rr.total !== undefined && rr.total !== null) ? rr.total : 0)
              + ' | Entregues: ' + ((rr.entregues !== undefined && rr.entregues !== null) ? rr.entregues : 0)
              + ' | Pendentes: ' + ((rr.pendentes !== undefined && rr.pendentes !== null) ? rr.pendentes : 0))
            : '';
          corridaMeta.innerText = 'Corrida #' + corridaSnapshot.id + ' | Status: ' + (corridaSnapshot.status || '')
            + ' | Tempo: ' + formatElapsedFromIso(startedEm)
            + resumoTxt2;
        }, 1000);
      }

      const items = Array.isArray(c.items) ? c.items : [];
      if (items.length === 0) {
        corridaItens.innerHTML = '<div class="muted" style="margin-top:10px">Nenhum pedido selecionado.</div>';
        return;
      }
      corridaItens.innerHTML = items.map(it => {
        const sid = (it && it.solicitacao_id) ? String(it.solicitacao_id) : '';
        const deliveredEm = (it && it.delivered_em) ? String(it.delivered_em) : '';
        const p = (it && it.pedido) ? it.pedido : null;
        const cliente = (p && p.cliente_nome) ? String(p.cliente_nome) : '';
        const whatsapp = (p && p.cliente_whatsapp) ? String(p.cliente_whatsapp) : '';
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
        const isDelivered = !!deliveredEm;

        const wa = waUrl(whatsapp, 'Olá! 😊 Estamos entrando em contato sobre seu pedido.');
        const waHtml = wa ? ('<div style="margin-top:10px"><a class="wa" target="_blank" rel="noopener" href="' + wa + '"><span style="opacity:.9">WA</span><span>Falar com o Cliente</span></a></div>') : '';

        const btnLabel = isRunning ? 'Devolver' : 'Remover';
        const btnAttr = isRunning ? 'data-return' : 'data-remove';

        let deliveredHtml = '';
        if (isDelivered) {
          deliveredHtml = '<div class="muted" style="margin-top:6px">Status: ENTREGUE</div>';
        } else if (isRunning) {
          deliveredHtml = '<div style="margin-top:10px"><button type="button" data-delivered="' + sid + '">Marcar Entregue</button></div>';
        }

        const cls = isDelivered ? 'item delivered' : 'item';
        return '<div class="' + cls + '">'
          + '<div style="font-weight:900">Pedido ' + sid + '</div>'
          + (cliente ? ('<div class="muted">Cliente: ' + cliente + '</div>') : '')
          + (endereco ? ('<div class="muted">Endereço: ' + endereco + '</div>') : '')
          + (obs ? ('<div class="muted">Obs: ' + obs + '</div>') : '')
          + (itensHtml ? ('<div style="margin-top:8px"><div style="font-weight:800">Itens</div>' + itensHtml + '</div>') : '')
          + waHtml
          + deliveredHtml
          + '<div style="margin-top:10px"><button type="button" class="secondary" ' + btnAttr + '="' + sid + '">' + btnLabel + '</button></div>'
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
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao remover.');
          } finally {
            btn.disabled = false;
          }
        });
      });

      corridaItens.querySelectorAll('button[data-return]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-return');
          if (!sid) return;
          btn.disabled = true;
          try {
            await api('/api/logistica/corrida/devolver', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({solicitacao_id: sid})});
            await load();
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao devolver.');
          } finally {
            btn.disabled = false;
          }
        });
      });

      corridaItens.querySelectorAll('button[data-delivered]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-delivered');
          if (!sid) return;
          btn.disabled = true;
          try {
            await api('/api/logistica/corrida/entregue', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({solicitacao_id: sid})});
            await load();
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao marcar entregue.');
          } finally {
            btn.disabled = false;
          }
        });
      });
    }

    async function load() {
      showToast('');
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

    function formatElapsedFromIso(iso) {
      try {
        const t0 = Date.parse(String(iso || ''));
        if (!t0) return '00:00';
        const diff = Math.max(0, Date.now() - t0);
        const sec = Math.floor(diff / 1000);
        const h = Math.floor(sec / 3600);
        const m = Math.floor((sec % 3600) / 60);
        const s = sec % 60;
        const mm = String(m).padStart(2, '0');
        const ss = String(s).padStart(2, '0');
        if (h > 0) {
          return String(h) + ':' + mm + ':' + ss;
        }
        return mm + ':' + ss;
      } catch (e) {
        return '00:00';
      }
    }

    btnStart.addEventListener('click', async () => {
      btnStart.disabled = true;
      try {
        await api('/api/logistica/corrida/start', {method:'POST'});
        await load();
      } catch (e) {
        showToast((e && e.error) ? e.error : 'Falha ao iniciar corrida.');
      } finally {
        btnStart.disabled = false;
      }
    });

    btnFinish.addEventListener('click', async () => {
      btnFinish.disabled = true;
      try {
        await api('/api/logistica/corrida/finish', {method:'POST'});
        await load();
      } catch (e) {
        showToast((e && e.error) ? e.error : 'Falha ao finalizar corrida.');
      } finally {
        btnFinish.disabled = false;
      }
    });

    btnNew.addEventListener('click', async () => {
      btnNew.disabled = true;
      try {
        await api('/api/logistica/corrida/nova', {method:'POST'});
        await load();
      } catch (e) {
        showToast((e && e.error) ? e.error : 'Falha ao criar nova corrida.');
      } finally {
        btnNew.disabled = false;
      }
    });

    load();
  </script>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp
