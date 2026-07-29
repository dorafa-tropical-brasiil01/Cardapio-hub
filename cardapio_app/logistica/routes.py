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
    listar_prontos,
    obter_corrida_atual,
    pedido_cancelar_definitivo,
    pedido_dessinalizar,
    pedido_sinalizar,
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
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:14px;background:var(--bg);background-color:var(--bg);color:var(--text);line-height:1.35}
    .wrap{max-width:760px;margin:0 auto}
    .card{background:var(--card);border:2px solid var(--border);border-radius:20px;padding:14px;margin:12px 0;box-sizing:border-box}
    .topbar{position:sticky;top:-1px;z-index:10;padding:12px 0;background:var(--bg);background-color:var(--bg)}
    .topbar .inner{max-width:760px;margin:0 auto;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;background:var(--card);border:2px solid var(--border);border-radius:20px;box-sizing:border-box}
    .top-title{font-weight:900;font-size:18px}
    .top-sub{opacity:.75;font-size:12px;margin-top:2px}
    h1{font-size:18px;margin:0}
    .muted{opacity:.78;overflow-wrap:anywhere;word-break:break-word}
    .list{margin-top:10px;display:flex;flex-direction:column;gap:10px}
    .item{padding:12px;border:2px solid rgba(10, 92, 47, 0.22);border-radius:18px;background:var(--card2);overflow-wrap:anywhere;word-break:break-word}
    .item.delivered{opacity:.72;border-color:rgba(255,255,255,0.14)}
    button{font-size:16px;padding:15px 18px;border-radius:20px;border:0;background:var(--verde);color:#fff;font-weight:900;cursor:pointer}
    button.secondary{background:rgba(10, 92, 47, 0.08);border:2px solid rgba(10, 92, 47, 0.35);color:var(--verde);font-weight:900}
    button:disabled{opacity:.55}
    a.wa{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;background:#2f9e44;color:#fff;padding:15px 18px;border-radius:20px;font-weight:900;width:100%;box-sizing:border-box;overflow-wrap:anywhere;word-break:break-word;text-align:center}
    a.maps{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;background:rgba(10, 92, 47, 0.08);border:2px solid rgba(10, 92, 47, 0.35);color:var(--verde);padding:15px 18px;border-radius:20px;font-weight:900;width:100%;box-sizing:border-box;overflow-wrap:anywhere;word-break:break-word;text-align:center}
    .top-actions{display:none}

    .badge{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;border:2px solid rgba(10, 92, 47, 0.35);background:rgba(10, 92, 47, 0.08);font-weight:900;font-size:12px}
    .badge.danger{border-color:rgba(160,0,0,0.25);background:rgba(160,0,0,0.06);color:#7a0000}

    @media (max-width: 520px) {
      body{padding-top:10px}
      .topbar{padding:10px 0}
      .topbar .inner{padding:10px 12px;margin:0 12px}
      button{padding:14px 14px}
      a.wa{padding:13px 14px;font-size:14px;border-radius:16px}
      a.maps{padding:13px 14px;font-size:14px;border-radius:16px}
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="inner">
      <div>
        <div class="top-title">Entregas</div>
        <div class="top-sub">Fila e corridas</div>
      </div>
      <form method="post" action="/ops/logout"><button class="secondary" type="submit">Sair</button></form>
    </div>
  </div>

  <div class="wrap">

    <div class="card">
      <div class="muted">Pedidos prontos para entrega:</div>
      <div class="list">
        <div class="muted" id="prontos">Carregando...</div>
      </div>
    </div>

    <div class="card">
      <div style="font-weight:900">Minha Corrida</div>
      <div id="toast" class="card" style="display:none;margin-top:10px;background:#2a1b1b;border-color:rgba(255,0,0,0.25);"></div>
      <div class="muted" id="corrida_meta">Carregando...</div>
      <div class="list" id="corrida_itens"></div>
      <div style="margin-top:15px;display:flex;gap:10px;flex-wrap:wrap">
        <button type="button" id="btn_start">Iniciar Corrida</button>
        <button type="button" id="btn_finish">Finalizar Corrida</button>
        <button type="button" id="btn_new" class="secondary">Nova Corrida</button>
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

    try {
      const looksLikeLoading = (t) => {
        const s = String(t || '').trim();
        if (!s) return true;
        return s.toLowerCase().indexOf('carregando') >= 0;
      };
      if (prontosEl && looksLikeLoading(prontosEl.innerText)) prontosEl.innerText = 'Iniciando...';
      if (corridaMeta && looksLikeLoading(corridaMeta.innerText)) corridaMeta.innerText = 'Iniciando...';
    } catch (e) {
    }

    try {
      window.addEventListener('error', (ev) => {
        try {
          const msg = (ev && ev.message) ? String(ev.message) : 'Erro de script.';
          showToast(msg);
        } catch (e) {}
      });
      window.addEventListener('unhandledrejection', (ev) => {
        try {
          const reason = (ev && ev.reason) ? String(ev.reason) : 'Falha inesperada.';
          showToast(reason);
        } catch (e) {}
      });
    } catch (e) {}

    let corridaTimerHandle = null;
    let corridaSnapshot = null;

    function fatal(msg) {
      const t = String(msg || '').trim() || 'Falha inesperada.';
      try {
        if (prontosEl) prontosEl.innerText = t;
      } catch (e) {}
      try {
        if (corridaMeta) corridaMeta.innerText = t;
      } catch (e) {}
      try { showToast(t); } catch (e) {}
    }

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

    function parseEndereco(enderecoRaw) {
      if (!enderecoRaw) return {text: '', maps: ''};
      if (typeof enderecoRaw === 'string') {
        const t = String(enderecoRaw || '').trim();
        return {text: t, maps: ''};
      }
      if (typeof enderecoRaw !== 'object') return {text: '', maps: ''};
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
      return {text: out.join(' | ').trim(), maps: maps};
    }

    function intOr0(v) {
      const n = Number(v);
      return Number.isFinite(n) ? Math.trunc(n) : 0;
    }

    async function api(url, opts) {
      const resp = await fetch(url, opts || {method:'GET'});

      const ctype = String(resp.headers.get('content-type') || '').toLowerCase();
      let j = null;
      let raw = '';

      if (ctype.indexOf('application/json') >= 0) {
        j = await resp.json().catch(() => null);
      } else {
        raw = await resp.text().catch(() => '');
      }

      if (!resp.ok) {
        const err = (j && j.error) ? j.error : (raw ? raw.slice(0, 220) : ('http_' + resp.status));
        throw {error: err, status: resp.status};
      }
      if (j === null) {
        throw {error: raw ? ('Resposta não-JSON: ' + raw.slice(0, 220)) : 'Resposta não-JSON vazia.'};
      }
      return j;
    }

    function applyButtonsByStatus(c) {
      const status = String((c && c.status) || '').toUpperCase();
      const hasRun = !!(c && c.id);
      const items = (c && Array.isArray(c.items)) ? c.items : [];

      if (!hasRun) {
        if (btnStart) btnStart.disabled = true;
        if (btnFinish) btnFinish.disabled = true;
        if (btnNew) btnNew.disabled = false;
        return;
      }

      if (status === 'MONTANDO') {
        const startDisabled = (items.length === 0);
        if (btnStart) btnStart.disabled = startDisabled;
        if (btnFinish) btnFinish.disabled = true;
        if (btnNew) btnNew.disabled = false;
        return;
      }

      if (status === 'EM_ANDAMENTO') {
        if (btnStart) btnStart.disabled = true;
        if (btnFinish) btnFinish.disabled = false;
        if (btnNew) btnNew.disabled = true;
        return;
      }

      if (status === 'FINALIZADA') {
        if (btnStart) btnStart.disabled = true;
        if (btnFinish) btnFinish.disabled = true;
        if (btnNew) btnNew.disabled = false;
        return;
      }

      if (btnStart) btnStart.disabled = true;
      if (btnFinish) btnFinish.disabled = true;
      if (btnNew) btnNew.disabled = false;
    }

    function renderProntos(pedidos) {
      if (!prontosEl) return;
      const arr = Array.isArray(pedidos) ? pedidos : [];
      const nowLabel = new Date().toLocaleTimeString();
      if (arr.length === 0) {
        prontosEl.innerHTML = '<div class="muted">Nenhum pedido pronto. ' + (nowLabel ? ('<span style="opacity:.75">(atualizado ' + nowLabel + ')</span>') : '') + '</div>';
        return;
      }
      const head = '<div class="muted" style="margin-bottom:10px">Prontos: ' + arr.length + (nowLabel ? (' • atualizado ' + nowLabel) : '') + '</div>';
      prontosEl.innerHTML = arr.map(p => {
        const id = (p && p.id) ? String(p.id) : '';
        const flag = (p && (p.logistica_flag || p.flag)) ? String(p.logistica_flag || p.flag) : '';
        const cliente = (p && p.cliente_nome) ? String(p.cliente_nome) : '';
        const whatsapp = (p && p.cliente_whatsapp) ? String(p.cliente_whatsapp) : '';
        const obs = (p && (p.observacoes || p.obs || p.observacao)) ? String(p.observacoes || p.obs || p.observacao) : '';
        const enderecoRaw = (p && (p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco))) || null;
        const addr = parseEndereco(enderecoRaw);
        const endereco = addr.text;
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
        const isFlagged = (String(flag || '').trim().toUpperCase() === 'SINALIZADO');
        const flagHtml = isFlagged
          ? ('<div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center">'
            + '<span class="badge danger">SINALIZADO</span>'
            + '<button type="button" class="secondary" data-flag-clear="' + id + '">Desmarcar</button>'
            + '</div>')
          : '';
        const acceptDisabledAttr = isFlagged ? ' disabled' : '';
        return '<div class="item">'
          + '<div style="font-weight:900">Pedido</div>'
          + (cliente ? ('<div class="muted">Cliente: ' + cliente + '</div>') : '')
          + (endereco ? ('<div class="muted">Endereço: ' + endereco + '</div>') : '')
          + (obs ? ('<div class="muted">Obs: ' + obs + '</div>') : '')
          + (itensHtml ? ('<div style="margin-top:8px"><div style="font-weight:800">Itens</div>' + itensHtml + '</div>') : '')
          + waHtml
          + flagHtml
          + '<div style="margin-top:10px"><button type="button" data-id="' + id + '"' + acceptDisabledAttr + '>Aceitar</button></div>'
          + '</div>';
      }).join('');
      prontosEl.innerHTML = head + prontosEl.innerHTML;
      prontosEl.querySelectorAll('button[data-id]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-id');
          if (!sid) return;
          btn.disabled = true;
          try {
            await api('/api/logistica/corrida/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({solicitacao_id: sid})});
            await load();
          } catch (e) {
            const err = (e && e.error) ? String(e.error) : 'Falha ao aceitar pedido.';
            if (err === 'pedido_sinalizado') {
              const pwd = prompt('Pedido SINALIZADO.\n\nSe você for administrador, digite a senha para DES-SINALIZAR e reativar o aceite.');
              if (pwd && String(pwd).trim()) {
                try {
                  await api('/api/logistica/pedido/dessinalizar', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({solicitacao_id: sid, password: String(pwd)})
                  });
                  await load();
                  return;
                } catch (e2) {
                  showToast((e2 && e2.error) ? e2.error : 'Falha ao des-sinalizar.');
                  return;
                }
              }
              showToast('Pedido sinalizado: apenas admin pode reativar.');
              return;
            }
            showToast(err);
          } finally {
            btn.disabled = false;
          }
        });
      });

      prontosEl.querySelectorAll('button[data-flag-clear]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-flag-clear');
          if (!sid) return;
          const pwd = prompt('Desmarcar SINALIZADO (apenas admin).\n\nDigite a senha do administrador:');
          if (!pwd || !String(pwd).trim()) return;
          btn.disabled = true;
          try {
            await api('/api/logistica/pedido/dessinalizar', {
              method:'POST',
              headers:{'Content-Type':'application/json'},
              body: JSON.stringify({solicitacao_id: sid, password: String(pwd)})
            });
            await load();
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao desmarcar.');
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

      const rr0 = (c && c.resumo) ? c.resumo : null;
      const pend0 = intOr0(rr0 && rr0.pendentes);
      const total0 = intOr0(rr0 && rr0.total);
      if (isRunning && total0 > 0 && pend0 === 0) {
        setTimeout(async () => {
          try {
            await api('/api/logistica/corrida/finish', {method:'POST'});
            await load();
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao finalizar corrida automaticamente.');
          }
        }, 250);
      }

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
        const flag = (p && (p.logistica_flag || p.flag)) ? String(p.logistica_flag || p.flag) : '';
        const cliente = (p && p.cliente_nome) ? String(p.cliente_nome) : '';
        const whatsapp = (p && p.cliente_whatsapp) ? String(p.cliente_whatsapp) : '';
        const obs = (p && (p.observacoes || p.obs || p.observacao)) ? String(p.observacoes || p.obs || p.observacao) : '';
        const enderecoRaw = (p && (p.endereco || (p.entrega && p.entrega.endereco) || (p.cliente && p.cliente.endereco))) || null;
        const addr = parseEndereco(enderecoRaw);
        const endereco = addr.text;
        const maps = addr.maps;
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
        const mapsHtml = maps ? ('<div style="margin-top:10px"><a class="maps" target="_blank" rel="noopener" href="' + maps + '" data-maps="' + sid + '"><span style="opacity:.9">MAPS</span><span>Abrir Localização</span></a></div>') : '';

        const isFlagged = (String(flag || '').trim().toUpperCase() === 'SINALIZADO');
        const flagHtml = isFlagged
          ? ('<div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center">'
            + '<span class="badge danger">SINALIZADO</span>'
            + '<button type="button" class="secondary" data-flag-clear="' + sid + '">Desmarcar</button>'
            + '</div>')
          : '';

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
          + '<div style="font-weight:900">Pedido</div>'
          + (cliente ? ('<div class="muted">Cliente: ' + cliente + '</div>') : '')
          + (endereco ? ('<div class="muted">Endereço: ' + endereco + '</div>') : '')
          + (obs ? ('<div class="muted">Obs: ' + obs + '</div>') : '')
          + (itensHtml ? ('<div style="margin-top:8px"><div style="font-weight:800">Itens</div>' + itensHtml + '</div>') : '')
          + waHtml
          + mapsHtml
          + flagHtml
          + deliveredHtml
          + '<div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap">'
          + '<button type="button" class="secondary" ' + btnAttr + '="' + sid + '">' + btnLabel + '</button>'
          + '<button type="button" class="secondary" data-cancel="' + sid + '">Cancelar</button>'
          + '</div>'
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

      corridaItens.querySelectorAll('button[data-cancel]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-cancel');
          if (!sid) return;

          const pwd = prompt('Senha do administrador (opcional para cancelar definitivo).\n\n- Sem senha: devolve para a fila como SINALIZADO.\n- Com senha: remove do fluxo definitivamente.');
          btn.disabled = true;
          try {
            if (pwd && String(pwd).trim()) {
              await api('/api/logistica/pedido/cancelar_definitivo', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({solicitacao_id: sid, password: String(pwd)})
              });
            } else {
              try {
                const st0 = String((corridaSnapshot && corridaSnapshot.status) || '').toUpperCase();
                if (st0 === 'EM_ANDAMENTO') {
                  await api('/api/logistica/corrida/devolver', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({solicitacao_id: sid})});
                } else {
                  await api('/api/logistica/corrida/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({solicitacao_id: sid})});
                }
              } catch (e2) {
              }
              await api('/api/logistica/pedido/sinalizar', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({solicitacao_id: sid, note: 'cancelado_sem_senha'})
              });
            }
            await load();
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao cancelar.');
          } finally {
            btn.disabled = false;
          }
        });
      });

      corridaItens.querySelectorAll('button[data-flag-clear]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const sid = btn.getAttribute('data-flag-clear');
          if (!sid) return;
          const pwd = prompt('Desmarcar SINALIZADO (apenas admin).\n\nDigite a senha do administrador:');
          if (!pwd || !String(pwd).trim()) return;
          btn.disabled = true;
          try {
            await api('/api/logistica/pedido/dessinalizar', {
              method:'POST',
              headers:{'Content-Type':'application/json'},
              body: JSON.stringify({solicitacao_id: sid, password: String(pwd)})
            });
            await load();
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao desmarcar.');
          } finally {
            btn.disabled = false;
          }
        });
      });

      corridaItens.querySelectorAll('a[data-maps]').forEach(a => {
        a.addEventListener('click', async () => {
          try {
            if (!corridaSnapshot || !corridaSnapshot.id) return;
            const st = String(corridaSnapshot.status || '').toUpperCase();
            if (st !== 'MONTANDO') return;
            const items2 = Array.isArray(corridaSnapshot.items) ? corridaSnapshot.items : [];
            if (items2.length === 0) return;
            const firstSid = String((items2[0] && (items2[0].solicitacao_id || (items2[0].pedido && items2[0].pedido.id))) || '').trim();
            const clickedSid = String(a.getAttribute('data-maps') || '').trim();
            if (!firstSid || !clickedSid) return;
            if (firstSid !== clickedSid) return;

            await api('/api/logistica/corrida/start', {method:'POST'});
            await load();
          } catch (e) {
            showToast((e && e.error) ? e.error : 'Falha ao iniciar corrida.');
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
        const msg = (e && e.error) ? e.error : 'Falha ao carregar prontos.';
        prontosEl.innerText = msg;
        showToast(msg);
      }

      try {
        const c = await api('/api/logistica/corrida');
        renderCorrida(c.corrida);
      } catch (e) {
        const msg2 = (e && e.error) ? e.error : 'Falha ao carregar corrida.';
        corridaMeta.innerText = msg2;
        showToast(msg2);
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

    function bindBtn(el, handler) {
      if (!el) return;
      try {
        el.addEventListener('click', handler);
      } catch (e) {
      }
    }

    async function onStart() {
      if (btnStart) btnStart.disabled = true;
      try {
        await api('/api/logistica/corrida/start', {method:'POST'});
        await load();
      } catch (e) {
        showToast((e && e.error) ? e.error : 'Falha ao iniciar corrida.');
      } finally {
        if (btnStart) btnStart.disabled = false;
      }
    }

    async function onFinish() {
      if (btnFinish) btnFinish.disabled = true;
      try {
        await api('/api/logistica/corrida/finish', {method:'POST'});
        await load();
      } catch (e) {
        showToast((e && e.error) ? e.error : 'Falha ao finalizar corrida.');
      } finally {
        if (btnFinish) btnFinish.disabled = false;
      }
    }

    async function onNew() {
      if (btnNew) btnNew.disabled = true;
      try {
        await api('/api/logistica/corrida/nova', {method:'POST'});
        await load();
      } catch (e) {
        showToast((e && e.error) ? e.error : 'Falha ao criar nova corrida.');
      } finally {
        if (btnNew) btnNew.disabled = false;
      }
    }

    bindBtn(btnStart, onStart);
    bindBtn(btnFinish, onFinish);
    bindBtn(btnNew, onNew);

    try {
      if (!prontosEl || !corridaMeta || !corridaItens) {
        fatal('Falha ao iniciar: elementos da página não encontrados.');
      } else {
        if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', () => {
            try { startAutoRefresh(); } catch (e) { fatal('Falha ao iniciar: ' + e); }
          });
        } else {
          startAutoRefresh();
        }
      }
    } catch (e) {
      fatal('Falha ao iniciar: ' + e);
    }
  </script>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp
