from __future__ import annotations


def kds_page_html() -> str:
    return r"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#fd6300" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <link rel="manifest" href="/cozinha/manifest.json" />
  <link rel="icon" href="/assets/KDS_COZINHA.ico" />
  <link rel="apple-touch-icon" href="/assets/KDS_COZINHA.png" />
  <title>Cozinha — Do'Rafa</title>
  <style>
    *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
    html,body{height:100%}
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:0;background:#f3f0e7;color:#1f3322;line-height:1.35}
    #app{max-width:980px;margin:0 auto;padding:14px;padding-bottom:120px}
    .topbar{position:sticky;top:0;z-index:20;background:#0a5c2f;color:#fff;padding:14px 18px;border-radius:0 0 18px 18px;box-shadow:0 4px 12px rgba(0,0,0,0.08)}
    .topbar h1{margin:0;font-size:18px;font-weight:900}
    .topbar .sub{opacity:.85;font-size:12px}
    .topbar .logout{float:right;background:rgba(255,255,255,0.15);border:0;color:#fff;padding:8px 12px;border-radius:10px;font-weight:900;cursor:pointer}
    .tabs{display:flex;overflow-x:auto;padding:14px 0}
    .tabs > * + *{margin-left:6px}
    .tab{flex:0 0 auto;min-width:90px;background:#ffffff;border:2px solid rgba(10,92,47,0.18);border-radius:14px;padding:10px 8px;text-align:center;font-weight:900;font-size:13px;cursor:pointer;white-space:nowrap;color:#1f3322}
    .tab.active{background:#0a5c2f;border-color:#0a5c2f;color:#fff}
    .tab .count{display:block;font-size:11px;font-weight:400;opacity:.85;margin-top:2px}
    .stats{display:flex;margin-bottom:14px}
    .stats > * + *{margin-left:10px}
    .stat{flex:1;background:#ffffff;border:2px solid rgba(10,92,47,0.18);border-radius:14px;padding:12px;text-align:center}
    .stat .value{font-size:22px;font-weight:900;color:#0a5c2f}
    .stat .label{font-size:11px;color:#5c6b5f;text-transform:uppercase}
    .list{display:flex;flex-direction:column}
    .list > * + *{margin-top:12px}
    .card-item{background:#ffffff;border:2px solid rgba(10,92,47,0.18);border-radius:18px;padding:14px;cursor:pointer;transition:transform .05s ease;overflow:hidden}
    .card-item:active{transform:scale(.99)}
    .card-item .header{display:flex;align-items:center;justify-content:space-between;overflow:hidden;min-width:0}
    .card-item .header > * + *{margin-left:10px}
    .card-item .id{font-weight:900;font-size:16px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%}
    .card-item .badge{display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:900;flex-shrink:0;white-space:nowrap}
    .badge.NOVO{background:rgba(10,92,47,.08);color:#0a5c2f;border:1px solid rgba(10,92,47,.2)}
    .badge.EM_PREPARO{background:#fefecf;color:#0a5c2f;border:1px solid #0a5c2f}
    .badge.PRONTO{background:#0a5c2f;color:#fff;border:1px solid #0a5c2f}
    .badge.SINALIZADO{background:#1971c2;color:#fff;border:1px solid #1971c2}
    .badge.ENTREGUE{background:#6b7280;color:#fff;border:1px solid #6b7280}
    .badge.RECUSADO{background:#e03131;color:#fff;border:1px solid #e03131}
    .card-item .cliente{margin-top:8px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .card-item .tipo{color:#5c6b5f;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .card-item .hora{color:#5c6b5f;font-size:12px;margin-top:6px}
    .card-item .card-footer{display:flex;align-items:center;justify-content:space-between;margin-top:6px}
    .card-item .card-total{font-weight:900;font-size:15px;color:#0a5c2f}
    .empty{text-align:center;padding:40px 20px;color:#5c6b5f}

    #drawer{position:fixed;top:0;right:0;bottom:0;left:0;z-index:50;background:rgba(0,0,0,.45);display:none;align-items:flex-end;justify-content:center}
    #drawer.open{display:flex}
    #drawer .sheet{width:100%;max-width:980px;max-height:90vh;background:#ffffff;border-radius:24px 24px 0 0;padding:18px;overflow-y:auto;animation:slideUp .2s ease}
    @keyframes slideUp{from{transform:translateY(100%)}to{transform:translateY(0)}}
    #drawer .close{position:absolute;top:14px;right:18px;background:none;border:0;font-size:24px;color:#5c6b5f;cursor:pointer}
    #drawer h2{margin:0 0 10px 0;font-size:18px}
    #drawer .section{margin:14px 0}
    #drawer .section-title{font-size:13px;font-weight:900;color:#0a5c2f;text-transform:uppercase;margin-bottom:6px}
    #drawer .muted{color:#5c6b5f;font-size:14px;white-space:pre-wrap}
    #drawer .item-row{padding:6px 0;border-bottom:1px solid rgba(10,92,47,.08);font-size:14px}
    #drawer .actions{display:flex;flex-wrap:wrap;margin:13px -5px 0 -5px}
    #drawer .actions > *{margin:5px}
    #drawer .actions button{flex:1;min-width:140px;font-size:15px;padding:16px;border-radius:16px;border:0;font-weight:900;cursor:pointer}
    .btn-primary{background:#0a5c2f;color:#fff}
    .btn-secondary{background:rgba(10,92,47,.08);color:#0a5c2f;border:2px solid rgba(10,92,47,0.18)!important}
    .btn-danger{background:#e03131;color:#fff}
    .btn-wa{background:#25D366;color:#fff;border:2px solid #1da851!important;display:inline-flex;align-items:center;justify-content:center;font-size:15px;padding:16px;border-radius:16px;font-weight:900;text-decoration:none;flex:1;min-width:140px}
    .btn-wa > * + *{margin-left:8px}
    .btn:disabled{opacity:.5;cursor:not-allowed}
    .btn-printer{background:rgba(10,92,47,.08);color:#0a5c2f;border:2px solid rgba(10,92,47,0.18);border-radius:12px;padding:8px 14px;font-size:13px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap}
    .btn-printer > * + *{margin-left:6px}
    .btn-printer.connected{background:#0a5c2f;color:#fff;border-color:#0a5c2f}
    .btn-printer.error{background:#e03131;color:#fff;border-color:#e03131}
    .modal-overlay{position:fixed;top:0;right:0;bottom:0;left:0;z-index:60;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center}
    .modal-overlay.open{display:flex}
    .modal-box{background:#ffffff;border-radius:20px;padding:20px;width:92%;max-width:520px;max-height:90vh;overflow-y:auto}

    #modal-overlay{position:fixed;top:0;right:0;bottom:0;left:0;z-index:60;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center}
    #modal-overlay.open{display:flex}
    #modal{background:#ffffff;border-radius:20px;padding:20px;width:92%;max-width:520px;max-height:90vh;overflow-y:auto}
    #modal h3{margin:0 0 14px 0}
    #modal label{display:block;margin:10px 0 4px 0;font-weight:700}
    #modal select, #modal textarea{width:100%;padding:12px;border-radius:12px;border:2px solid rgba(10,92,47,0.18);font-family:inherit;font-size:15px}
    #modal textarea{min-height:80px;resize:vertical}
    #modal .actions{display:flex;justify-content:flex-end;margin-top:18px}
    #modal .actions > * + *{margin-left:10px}
    #modal .actions button{padding:12px 20px;border-radius:12px;border:0;font-weight:900;cursor:pointer}

    #print-frame{position:fixed;top:0;left:0;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none}
    @media print{
      body *{visibility:hidden}
      #print-frame, #print-frame *{visibility:visible}
      #print-frame{position:absolute;top:0;right:0;bottom:0;left:0;width:100%;height:auto;opacity:1}
    }

    #toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);z-index:70;background:#1f3322;color:#fff;padding:12px 20px;border-radius:12px;font-weight:700;box-shadow:0 4px 12px rgba(0,0,0,.2);display:none}
    #toast.error{background:#e03131}

    @media (max-width: 520px){
      .topbar h1{font-size:16px}
      .tab{font-size:12px;min-width:76px}
      #drawer .actions button{min-width:100%;font-size:14px}
    }

    .hidden{display:none!important}
  </style>

  <!-- Estilos de cupom 80mm -->
  <style media="print">
    @page { size: 80mm auto; margin: 0; }
    body { margin: 0; padding: 0; }
    .cupom { width: 80mm; padding: 4mm; font-family: 'Courier New', monospace; font-size: 12pt; color: #000; }
    .cupom h3 { margin: 0 0 2mm 0; font-size: 14pt; text-align: center; }
    .cupom .linha { display: flex; justify-content: space-between; margin: 1mm 0; }
    .cupom .totais { border-top: 1px dashed #000; margin-top: 3mm; padding-top: 2mm; }
    .cupom .obs { margin-top: 3mm; border-top: 1px dashed #000; padding-top: 2mm; font-size: 10pt; }
    .cupom .endereco { margin-top: 3mm; font-size: 10pt; }
  </style>
</head>
<body>
  <div id="app">
    <!-- Diagnostico: so aparece dentro do APK (WebView com AndroidPrint) -->
    <div id="diag-overlay" style="position:fixed;top:0;left:0;width:50%;z-index:999;background:rgba(26,26,26,0.92);color:#0f0;font-family:monospace;font-size:10px;padding:6px;max-height:45vh;overflow:auto;display:none;white-space:pre-wrap;pointer-events:none"></div>
    <div class="topbar">
      <button class="logout" id="btn-logout" type="button">Sair</button>
      <h1>Cozinha</h1>
      <div class="sub">Painel de preparo</div>
      <button class="btn-printer" id="btn-printer" type="button" onclick="abrirConfigImpressora()" title="Configurar impressora térmica">
        <span id="printer-icon">&#128424;</span>
        <span id="printer-status">Impressora</span>
      </button>
    </div>

    <div class="stats">
      <div class="stat"><div class="value" id="stat-pendentes">0</div><div class="label">Pendentes</div></div>
      <div class="stat"><div class="value" id="stat-prontos">0</div><div class="label">Prontos</div></div>
      <div class="stat"><div class="value" id="stat-sinalizados">0</div><div class="label">Sinalizados</div></div>
    </div>

    <div class="tabs" id="tabs">
      <div class="tab active" data-aba="previas" onclick="setAba('previas')">Prévias<span class="count" id="count-previas"></span></div>
      <div class="tab" data-aba="preparando" onclick="setAba('preparando')">Em preparo<span class="count" id="count-preparando"></span></div>
      <div class="tab" data-aba="prontos" onclick="setAba('prontos')">Prontos<span class="count" id="count-prontos"></span></div>
      <div class="tab" data-aba="sinalizados" onclick="setAba('sinalizados')">Sinalizados<span class="count" id="count-sinalizados"></span></div>
      <div class="tab" data-aba="entregues" onclick="setAba('entregues')">Entregues<span class="count" id="count-entregues"></span></div>
      <div class="tab" data-aba="recusados" onclick="setAba('recusados')">Recusados<span class="count" id="count-recusados"></span></div>
    </div>

    <div id="lista" class="list"></div>
    <div id="empty" class="empty hidden">Nenhum pedido nesta aba.</div>
  </div>

  <div id="drawer">
    <div class="sheet">
      <button class="close" onclick="fecharDrawer()">&times;</button>
      <h2 id="drawer-titulo">Pedido</h2>
      <div id="drawer-conteudo"></div>
      <div class="actions" id="drawer-actions"></div>
    </div>
  </div>

  <div id="modal-overlay">
    <div id="modal">
      <h3>Recusar pedido</h3>
      <label for="motivo-recusa">Motivo</label>
      <select id="motivo-recusa">
        <option value="FALTOU_INGREDIENTE">Faltou ingrediente</option>
        <option value="FORA_HORARIO">Fora do horário de atendimento</option>
        <option value="PEDIDO_MUITO_GRANDE">Pedido muito grande para o momento</option>
        <option value="OUTRO">Outro</option>
      </select>
      <label for="nota-recusa">Observação (opcional)</label>
      <textarea id="nota-recusa" placeholder="Detalhe a recusa..."></textarea>
      <div class="actions">
        <button class="btn-secondary" onclick="fecharModal()">Cancelar</button>
        <button class="btn-danger" id="btn-confirmar-recusa" onclick="confirmarRecusa()">Recusar</button>
      </div>
    </div>
  </div>

  <!-- Modal informativo: impressao USB so funciona dentro do app Cozinha -->
  <div id="printer-overlay" class="modal-overlay">
    <div id="printer-modal" class="modal-box">
      <h3>Impressora Térmica</h3>
      <p class="muted" style="margin:4px 0 14px 0;font-size:13px;white-space:normal">
        A impressão na <b>Bematech MP-4200 TH</b> (USB) só funciona dentro do
        aplicativo <b>DoRafa Cozinha</b>, porque o navegador não tem acesso à
        porta USB do aparelho.
      </p>
      <p class="muted" style="margin:0 0 14px 0;font-size:13px;white-space:normal">
        Abra o app <b>DoRafa Cozinha</b> (ícone da cozinha) neste aparelho,
        faça login e conecte a impressora por lá. Todo o painel funciona igual
        dentro do app.
      </p>
      <div id="printer-apk-download" style="margin:0 0 14px 0"></div>
      <div style="display:flex;justify-content:flex-end;margin-top:18px">
        <button class="btn-primary" onclick="fecharConfigImpressora()">Entendi</button>
      </div>
    </div>
  </div>

  <div id="print-frame"></div>
  <div id="toast"></div>

  <script>
    const ABA_FILTERS = {
      previas: ['NOVO'],
      preparando: ['EM_PREPARO'],
      prontos: ['PRONTO'],
      sinalizados: ['SINALIZADO'],
      entregues: ['ENTREGUE'],
      recusados: ['RECUSADO'],
    };
    let abaAtual = 'previas';
    window.abaAtual = abaAtual;
    let pedidoSelecionado = null;
    let timer = null;

    function safeText(x){ return (x === null || x === undefined) ? '' : String(x); }

    function money(v){
      const n = Number(v || 0);
      return n.toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
    }

    function showToast(msg, isError){
      const el = document.getElementById('toast');
      el.textContent = String(msg || '');
      el.className = isError ? 'error' : '';
      el.style.display = 'block';
      // Erros persistem 15s, sucesso 3s
      clearTimeout(window._toastTimer);
      window._toastTimer = setTimeout(() => { el.style.display = 'none'; }, isError ? 15000 : 3000);
    }

    function statusLabel(status){
      const map = {
        'NOVO': 'NOVO',
        'EM_PREPARO': 'EM PREPARO',
        'PRONTO': 'PRONTO',
        'SINALIZADO': 'SINALIZADO',
        'ENTREGUE': 'ENTREGUE',
        'RECUSADO': 'RECUSADO',
      };
      return map[status] || status;
    }

    function setAba(aba){
      abaAtual = aba;
      window.abaAtual = aba;
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.aba === aba));
      render();
      if (window.AndroidPrint) {
        window._diagRan = false;
        _diagnosticoPedidosReais(window._dadosKDS || {});
      }
    }

    function obterDadosPedido(p){
      const base = p || {};
      const kds = base.kds || {};
      const record = base.record || base;
      const cliente = record.cliente || {};
      const entrega = record.entrega || {};
      const endereco = record.endereco || entrega.endereco || {};
      const numeroOnline = Number(record.numero_online || base.numero_online || 0);
      // ID curto para exibição: On-line_XX (sequencial do cardápio) ou fallback do UUID
      const idCurto = numeroOnline > 0
        ? 'On-line_' + String(numeroOnline).padStart(2, '0')
        : (base.id || '').substring(0, 8);
      return {
        id: base.id,
        idCurto: idCurto,
        numeroOnline: numeroOnline,
        status: kds.status || 'NOVO',
        cliente_nome: cliente.nome || base.cliente_nome || '',
        cliente_whatsapp: cliente.whatsapp || base.cliente_whatsapp || '',
        tipo: record.tipo_entrega || base.tipo_entrega || base.kind || '',
        mesa: base.mesa || record.mesa || '',
        total: Number(record.total_estimado || record.total || base.total || base.total_estimado || 0),
        observacoes: record.observacoes || base.observacoes || base.observacao || '',
        itens: base.itens || record.itens || record.items || [],
        endereco: endereco,
        taxa: Number(record.taxa_entrega || entrega.taxa || base.taxa_entrega || 0),
        kds: kds,
      };
    }

    function renderItens(itens){
      const arr = Array.isArray(itens) ? itens : [];
      if (arr.length === 0) return '<div class="muted">Nenhum item.</div>';
      return arr.map(it => {
        const nome = safeText(it.nome || it.product_name);
        const code = safeText(it.product_code || it.pdvCode);
        const qty = safeText(it.qty || it.quantidade || 1);
        const unit = Number(it.preco_unitario || it.unit_price || it.preco || 0);
        const label = nome || code || 'Item';
        return `<div class="item-row"><b>${qty}x</b> ${label} ${unit ? '('+money(unit)+')' : ''}</div>`;
      }).join('');
    }

    function renderCard(p){
      const d = obterDadosPedido(p);
      const criado = d.kds.created_em ? new Date(d.kds.created_em).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}) : '';
      return `
        <div class="card-item" data-id="${d.id}" data-status="${d.status}">
          <div class="header">
            <div class="id">${d.idCurto}</div>
            <div class="badge ${d.status}">${statusLabel(d.status)}</div>
          </div>
          <div class="cliente">${d.cliente_nome || 'Cliente não informado'}</div>
          <div class="tipo">${d.tipo}${d.mesa ? ' • Mesa ' + d.mesa : ''}</div>
          <div class="card-footer">
            <div class="hora">${criado}</div>
            <div class="card-total">${money(d.total)}</div>
          </div>
        </div>
      `;
    }

    async function carregar(){
      try {
        const [resp, prep, pront, sinal, entre, recu, statsResp] = await Promise.all([
          fetch('/api/kds/previas?limit=50'),
          fetch('/api/kds/preparando?limit=50'),
          fetch('/api/kds/prontos?limit=50'),
          fetch('/api/kds/sinalizados?limit=50'),
          fetch('/api/kds/entregues?limit=50'),
          fetch('/api/kds/recusados?limit=50'),
          fetch('/api/kds/stats'),
        ]);

        const prev = resp.ok ? await resp.json().catch(() => ({})) : {fila: []};
        const prepJ = prep.ok ? await prep.json().catch(() => ({})) : {fila: []};
        const prontJ = pront.ok ? await pront.json().catch(() => ({})) : {fila: []};
        const sinalJ = sinal.ok ? await sinal.json().catch(() => ({})) : {fila: []};
        const entreJ = entre.ok ? await entre.json().catch(() => ({})) : {fila: []};
        const recuJ = recu.ok ? await recu.json().catch(() => ({})) : {fila: []};
        const statsJ = statsResp.ok ? await statsResp.json().catch(() => ({})) : {stats: {}};

        const st = statsJ.stats || {};
        document.getElementById('stat-pendentes').textContent = st.pendentes || 0;
        document.getElementById('stat-prontos').textContent = st.prontos || 0;
        document.getElementById('stat-sinalizados').textContent = st.sinalizados || 0;

        const grupos = {
          previas: prev.fila || [],
          preparando: prepJ.fila || [],
          prontos: prontJ.fila || [],
          sinalizados: sinalJ.fila || [],
          entregues: entreJ.fila || [],
          recusados: recuJ.fila || [],
        };

        Object.keys(grupos).forEach(k => {
          const count = (grupos[k] || []).length;
          const badge = document.getElementById('count-' + k);
          if (badge) badge.textContent = count ? String(count) : '';
        });

        window._dadosKDS = grupos;
        render();
        if (window.AndroidPrint) _diagnosticoPedidosReais(grupos);
      } catch (e) {
        showToast('Erro ao carregar pedidos', true);
      }
    }

    function _diagnosticoPedidosReais(grupos) {
      if (window._diagRan) return;
      window._diagRan = true;
      var el = document.getElementById('diag-overlay');
      if (!el) return;
      // Esperar render() terminar e medir cards reais no DOM
      setTimeout(function() {
        var linhas = el.textContent ? el.textContent.split('\n').slice(0, 30) : [];
        linhas.push('');
        linhas.push('=== ABA ATUAL: ' + (window.abaAtual || '?') + ' ===');
        var container = document.getElementById('lista');
        var cards = container ? container.querySelectorAll('.card-item') : [];
        linhas.push('cards no DOM: ' + cards.length);
        if (cards.length === 0) {
          linhas.push('TROQUE PARA ABA "Em preparo" E RECARREGUE');
        }
        for (var i = 0; i < Math.min(cards.length, 3); i++) {
          var card = cards[i];
          var cs = getComputedStyle(card);
          linhas.push('');
          linhas.push('--- CARD ' + i + ' ---');
          linhas.push('background=' + cs.backgroundColor);
          linhas.push('border=' + cs.border);
          linhas.push('padding=' + cs.padding);
          linhas.push('overflow=' + cs.overflow);
          linhas.push('boxSizing=' + cs.boxSizing);
          linhas.push('width=' + cs.width);
          linhas.push('height=' + cs.height);
          var r = card.getBoundingClientRect();
          linhas.push('rect w=' + r.width + ' h=' + r.height);
          if (card.scrollWidth > card.clientWidth) {
            linhas.push('OVERFLOW H! scroll=' + card.scrollWidth + ' client=' + card.clientWidth);
          }
          if (card.scrollHeight > card.clientHeight) {
            linhas.push('OVERFLOW V! scroll=' + card.scrollHeight + ' client=' + card.clientHeight);
          }
          // Filhos
          var idEl = card.querySelector('.id');
          var badgeEl = card.querySelector('.badge');
          var clienteEl = card.querySelector('.cliente');
          var tipoEl = card.querySelector('.tipo');
          var horaEl = card.querySelector('.hora');
          var totalEl = card.querySelector('.card-total');
          if (idEl) {
            var ir = idEl.getBoundingClientRect();
            var ics = getComputedStyle(idEl);
            linhas.push('.id: w=' + ir.width + ' text="' + idEl.textContent + '" flexShrink=' + ics.flexShrink + ' maxW=' + ics.maxWidth);
          }
          if (badgeEl) {
            var br = badgeEl.getBoundingClientRect();
            var bcs = getComputedStyle(badgeEl);
            linhas.push('.badge: w=' + br.width + ' text="' + badgeEl.textContent + '" flexShrink=' + bcs.flexShrink);
          }
          if (clienteEl) {
            var cr = clienteEl.getBoundingClientRect();
            linhas.push('.cliente: w=' + cr.width + ' h=' + cr.height + ' text="' + clienteEl.textContent.substring(0,40) + '"');
            linhas.push('  overflow=' + getComputedStyle(clienteEl).overflow + ' whiteSpace=' + getComputedStyle(clienteEl).whiteSpace);
          }
          if (tipoEl) {
            var tr = tipoEl.getBoundingClientRect();
            linhas.push('.tipo: w=' + tr.width + ' text="' + tipoEl.textContent.substring(0,40) + '"');
          }
          if (horaEl) linhas.push('.hora: w=' + horaEl.getBoundingClientRect().width + ' text="' + horaEl.textContent + '"');
          if (totalEl) linhas.push('.card-total: w=' + totalEl.getBoundingClientRect().width + ' text="' + totalEl.textContent + '"');
          // Footer
          var footer = card.querySelector('.card-footer');
          if (footer) {
            var fr = footer.getBoundingClientRect();
            var fcs = getComputedStyle(footer);
            linhas.push('.card-footer: w=' + fr.width + ' overflow=' + fcs.overflow + ' display=' + fcs.display);
          }
          // Header
          var header = card.querySelector('.header');
          if (header) {
            var hr = header.getBoundingClientRect();
            var hcs = getComputedStyle(header);
            linhas.push('.header: w=' + hr.width + ' overflow=' + hcs.overflow + ' minWidth=' + hcs.minWidth);
          }
          linhas.push('innerHTML: ' + card.innerHTML.substring(0, 300));
        }
        el.textContent = linhas.join('\n');
      }, 1500);
    }

    function render(){
      const dados = window._dadosKDS || {};
      const lista = dados[abaAtual] || [];
      const container = document.getElementById('lista');
      const empty = document.getElementById('empty');
      if (lista.length === 0){
        container.innerHTML = '';
        empty.classList.remove('hidden');
      } else {
        empty.classList.add('hidden');
        container.innerHTML = lista.map(p => renderCard(p)).join('');
        container.querySelectorAll('.card-item').forEach(c => {
          c.addEventListener('click', () => abrirDrawer(c.dataset.id, c.dataset.status));
        });
      }
    }

    function abrirDrawer(id, status){
      const dados = window._dadosKDS || {};
      let pedido = null;
      Object.values(dados).some(lista => {
        pedido = lista.find(p => (p.id || p.solicitacao_id) === id);
        return !!pedido;
      });
      if (!pedido) return;
      pedidoSelecionado = pedido;
      const d = obterDadosPedido(pedido);
      const end = d.endereco;
      let endText = '';
      if (end && (end.rua || end.bairro || end.cidade)) {
        const parts = [];
        if (end.rua) parts.push(end.rua + (end.numero ? ', ' + end.numero : ''));
        if (end.bairro) parts.push(end.bairro);
        if (end.cidade) parts.push(end.cidade);
        endText = parts.join(' - ');
        if (end.referencia) endText += '\nRef: ' + end.referencia;
      }

      document.getElementById('drawer-titulo').textContent = 'Pedido ' + d.idCurto;
      document.getElementById('drawer-conteudo').innerHTML = `
        <div class="section">
          <div class="section-title">Cliente</div>
          <div class="muted">${d.cliente_nome || 'Não informado'}</div>
          <div class="muted">${d.cliente_whatsapp || ''}</div>
        </div>
        <div class="section">
          <div class="section-title">Entrega</div>
          <div class="muted">${d.tipo || '-'}${d.mesa ? ' • Mesa ' + d.mesa : ''}</div>
          ${endText ? `<div class="muted" style="white-space:pre-wrap">${endText}</div>` : ''}
        </div>
        <div class="section">
          <div class="section-title">Itens</div>
          ${renderItens(d.itens)}
        </div>
        <div class="section">
          <div class="section-title">Observações</div>
          <div class="muted">${d.observacoes || 'Nenhuma observação'}</div>
        </div>
        <div class="section">
          <div class="section-title">Total</div>
          <div class="muted">${money(d.total)} ${d.taxa ? '(taxa ' + money(d.taxa) + ')' : ''}</div>
        </div>
      `;

      let botoes = '';
      const waIcon = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M12 2a9.94 9.94 0 0 0-8.53 15.02L2 22l5.1-1.35A9.96 9.96 0 0 0 12 22a10 10 0 0 0 0-20Zm5.77 14.42c-.24.67-1.21 1.23-1.97 1.39-.52.11-1.2.2-3.48-.74-2.91-1.2-4.79-4.14-4.93-4.33-.14-.19-1.18-1.57-1.18-2.99 0-1.42.74-2.12 1.01-2.41.26-.29.57-.36.76-.36h.55c.17 0 .41-.06.64.49.24.58.82 2 .89 2.14.07.14.11.32.02.51-.09.2-.14.32-.28.49-.14.17-.29.38-.42.51-.14.14-.28.29-.12.58.16.29.7 1.16 1.5 1.88 1.03.92 1.9 1.2 2.19 1.34.29.14.45.12.62-.07.17-.19.71-.82.9-1.1.19-.28.38-.24.64-.14.26.1 1.65.78 1.93.92.29.14.48.22.55.34.07.12.07.68-.17 1.35Z"/></svg>';
      if (d.status === 'NOVO' || d.status === 'AGUARDANDO'){
        botoes = `
          <button class="btn-primary" onclick="aceitarEImprimir('${d.id}')">Aceitar e imprimir</button>
          <button class="btn-danger" onclick="abrirModalRecusa('${d.id}')">Recusar</button>
        `;
        if (d.cliente_whatsapp) {
          botoes += `<a class="btn-wa" href="${waUrl(d.cliente_whatsapp, 'Olá! Estamos entrando em contato sobre seu pedido.')}" target="_blank" rel="noopener">${waIcon} WhatsApp</a>`;
        }
      } else if (d.status === 'EM_PREPARO'){
        botoes = `<button class="btn-primary" onclick="marcarPronto('${d.id}')">Pronto</button>`;
        if (d.cliente_whatsapp) {
          botoes += `<a class="btn-wa" href="${waUrl(d.cliente_whatsapp, 'Olá! Sobre seu pedido, já está em preparo.')}" target="_blank" rel="noopener">${waIcon} WhatsApp</a>`;
        }
      } else if (d.status === 'PRONTO'){
        botoes = `<button class="btn-primary" onclick="sinalEntregar('${d.id}')">Sinal para entregar</button>`;
        if (d.cliente_whatsapp) {
          botoes += `<a class="btn-wa" href="${waUrl(d.cliente_whatsapp, 'Olá! Seu pedido já está pronto.')}" target="_blank" rel="noopener">${waIcon} WhatsApp</a>`;
        }
      } else if (d.status === 'SINALIZADO'){
        botoes = `<button class="btn-secondary" onclick="reimprimir('${d.id}')">Reimprimir</button>`;
        if (d.cliente_whatsapp) {
          botoes += `<a class="btn-wa" href="${waUrl(d.cliente_whatsapp, 'Olá! Seu pedido já está a caminho.')}" target="_blank" rel="noopener">${waIcon} WhatsApp</a>`;
        }
      } else if (d.status === 'RECUSADO'){
        if (d.cliente_whatsapp) {
          botoes = `<a class="btn-wa" href="${waUrl(d.cliente_whatsapp, 'Olá! Infelizmente precisamos falar sobre seu pedido.')}" target="_blank" rel="noopener">${waIcon} WhatsApp</a>`;
        }
      }
      document.getElementById('drawer-actions').innerHTML = botoes;
      document.getElementById('drawer').classList.add('open');
    }

    function fecharDrawer(){
      document.getElementById('drawer').classList.remove('open');
      pedidoSelecionado = null;
    }

    function waUrl(phone, msg){
      let digits = String(phone || '').replace(/\D+/g, '');
      if (!digits) return '';
      if (!digits.startsWith('55')) digits = '55' + digits;
      if (digits.length < 12 || digits.length > 13) return '';
      let url = 'https://wa.me/' + digits;
      const m = String(msg || '').trim();
      if (m) url += '?text=' + encodeURIComponent(m);
      return url;
    }

    // ============================================================
    // MODULO IMPRESSAO ESC/POS — Bematech MP-4200 TH
    // ============================================================
    //
    // Prioridade 1: App nativo DoRafa Cozinha (USB Host API + CDC ACM)
    //   - WebView carrega o KDS, ponte window.AndroidPrint.print(base64)
    //   - Inicializa CDC ACM (SET_LINE_CODING + SET_CONTROL_LINE_STATE)
    //   - Envia bytes ESC/POS via bulkTransfer
    //
    // Prioridade 2: window.print() (fallback, impressora comum do sistema)
    //
    // No navegador (PWA/Chrome) a ponte nativa nao existe: o Chrome nao tem
    // acesso a porta USB CDC ACM da Bematech. Nesse caso o botao "Impressora"
    // orienta o operador a usar o app DoRafa Cozinha.

    function _temPonteNativa() {
      return !!(window.AndroidPrint && typeof window.AndroidPrint.print === 'function');
    }

    // --- Comandos ESC/POS (portado do PDV escpos_printing.py) ---
    const ESC = 0x1B;
    const GS  = 0x1D;
    const ESC_INIT       = new Uint8Array([ESC, 0x40]);              // ESC @ — reset
    const ESC_CP850      = new Uint8Array([ESC, 0x74, 0x01]);        // ESC t 1 — PC850
    const ESC_FONT_A     = new Uint8Array([ESC, 0x4D, 0x00]);        // ESC M 0 — Font A
    const ESC_NORMAL     = new Uint8Array([ESC, 0x21, 0x00]);        // ESC ! 0 — tamanho normal
    const ESC_CENTER     = new Uint8Array([ESC, 0x61, 0x01]);        // ESC a 1 — centralizado
    const ESC_LEFT       = new Uint8Array([ESC, 0x61, 0x00]);        // ESC a 0 — esquerda
    const ESC_BOLD_ON    = new Uint8Array([ESC, 0x45, 0x01]);        // ESC E 1 — negrito
    const ESC_BOLD_OFF   = new Uint8Array([ESC, 0x45, 0x00]);        // ESC E 0 — normal
    const ESC_DOUBLE     = new Uint8Array([ESC, 0x21, 0x30]);        // ESC ! 0x30 — double width+height
    const ESC_CUT        = new Uint8Array([GS, 0x56, 0x42, 0x00]);   // GS V B 0 — corte parcial
    const LF             = new Uint8Array([0x0A]);                   // line feed
    const DASH_LINE      = '-'.repeat(44);

    function _encCP850(text) {
      // Mapa CP850 para caracteres acentuados do português
      const cp850map = {
        0xE1:0xA0, 0xE0:0x85, 0xE2:0x83, 0xE3:0xA6, // á à â ã
        0xE9:0x82, 0xEA:0x88, 0xEB:0x89,             // é ê ë
        0xED:0xA1, 0xEC:0x8D, 0xEE:0x8B, 0xEF:0x8C, // í ì î ï
        0xF3:0xA2, 0xF2:0x95, 0xF4:0x93, 0xF5:0xA8, // ó ò ô õ
        0xFA:0xA3, 0xF9:0x97, 0xFB:0x96, 0xFC:0x81, // ú ù û ü
        0xE7:0x87, 0xC1:0x9A, 0xC0:0xB5, 0xC2:0x90, // ç Á À Â
        0xC3:0xC6, 0xC9:0x90, 0xCA:0xCA, 0xCD:0x9D, // Ã É Ê Í
        0xD3:0xE0, 0xD4:0xE2, 0xD5:0xE9, 0xDA:0xE3, // Ó Ô Õ Ú
        0xC7:0x80, 0xD1:0xA5, 0xF1:0xA4,             // Ç Ñ ñ
      };
      // Substitui caracteres Unicode não suportados
      const repl = {
        '\u2022':'-','\u2013':'-','\u2014':'-','\u2018':"'",'\u2019':"'",
        '\u201c':'"','\u201d':'"','\u2026':'...','\u00a0':' ',
        '\u00ab':'<<','\u00bb':'>>'
      };
      let s = String(text || '');
      for (const [k,v] of Object.entries(repl)) s = s.split(k).join(v);
      // Codifica manualmente em CP850
      const arr = [];
      for (let i = 0; i < s.length; i++) {
        const code = s.charCodeAt(i);
        if (code < 0x80) {
          arr.push(code);
        } else if (cp850map[code]) {
          arr.push(cp850map[code]);
        } else {
          // Tenta decomposição (ex: Á = A + combining accent)
          const decomposed = s.normalize('NFD')[i];
          if (decomposed && decomposed.charCodeAt(0) < 0x80) {
            arr.push(decomposed.charCodeAt(0));
          } else {
            arr.push(0x3F); // '?'
          }
        }
      }
      return new Uint8Array(arr);
    }

    function _centerText(text, width) {
      const len = text.length;
      if (len >= width) return text;
      const pad = Math.floor((width - len) / 2);
      return ' '.repeat(pad) + text;
    }

    function _concatBytes(...arrays) {
      let total = 0;
      for (const a of arrays) total += a.length;
      const out = new Uint8Array(total);
      let off = 0;
      for (const a of arrays) { out.set(a, off); off += a.length; }
      return out;
    }

    function montarCupomEscpos(pedido) {
      const d = obterDadosPedido(pedido);
      const W = 44; // largura útil 80mm (48 chars - 4 margem)
      const parts = [];

      // Inicialização
      parts.push(ESC_INIT);
      parts.push(ESC_CP850);
      parts.push(ESC_FONT_A);
      parts.push(ESC_NORMAL);

      // Cabeçalho centralizado
      parts.push(ESC_CENTER);
      parts.push(_encCP850('DORAFA TROPICAL BRASIL'));
      parts.push(LF);
      parts.push(_encCP850('--- COZINHA ---'));
      parts.push(LF);
      parts.push(LF);

      // Título
      parts.push(ESC_DOUBLE);
      parts.push(_encCP850(_centerText('PEDIDO ' + d.idCurto, W)));
      parts.push(LF);
      parts.push(ESC_NORMAL);
      parts.push(LF);

      // Informações do pedido (esquerda)
      parts.push(ESC_LEFT);
      const criado = d.kds.created_em ? new Date(d.kds.created_em).toLocaleString('pt-BR') : '';
      parts.push(_encCP850('Data: ' + criado));
      parts.push(LF);
      parts.push(_encCP850('Cliente: ' + (d.cliente_nome || '-')));
      parts.push(LF);
      parts.push(_encCP850('Tipo: ' + (d.tipo || '-') + (d.mesa ? '  Mesa: ' + d.mesa : '')));
      parts.push(LF);
      if (d.cliente_whatsapp) {
        parts.push(_encCP850('WhatsApp: ' + d.cliente_whatsapp));
        parts.push(LF);
      }
      parts.push(LF);

      // Separador
      parts.push(_encCP850(DASH_LINE));
      parts.push(LF);

      // Itens
      parts.push(ESC_BOLD_ON);
      parts.push(_encCP850('QTD  DESCRICAO                  VALOR'));
      parts.push(LF);
      parts.push(ESC_BOLD_OFF);
      parts.push(_encCP850(DASH_LINE));
      parts.push(LF);

      const itens = Array.isArray(d.itens) ? d.itens : [];
      for (const it of itens) {
        const nome = safeText(it.nome || it.product_name || it.product_code);
        const qty = safeText(it.qty || it.quantidade || 1);
        const unit = Number(it.preco_unitario || it.unit_price || it.preco || 0);
        const totalItem = Number(it.total) || (Number(qty) * unit);
        const qtyStr = String(qty).padEnd(4, ' ').slice(0, 4);
        const nomeStr = String(nome).padEnd(26, ' ').slice(0, 26);
        const valStr = money(totalItem).padStart(10, ' ');
        parts.push(_encCP850(qtyStr + ' ' + nomeStr + ' ' + valStr));
        parts.push(LF);
      }

      // Separador + totais
      parts.push(_encCP850(DASH_LINE));
      parts.push(LF);
      parts.push(_encCP850('Subtotal:        ' + money(d.total - d.taxa).padStart(14, ' ')));
      parts.push(LF);
      if (d.taxa) {
        parts.push(_encCP850('Taxa entrega:    ' + money(d.taxa).padStart(14, ' ')));
        parts.push(LF);
      }
      parts.push(ESC_BOLD_ON);
      parts.push(_encCP850('TOTAL:           ' + money(d.total).padStart(14, ' ')));
      parts.push(LF);
      parts.push(ESC_BOLD_OFF);
      parts.push(LF);

      // Endereço
      const end = d.endereco;
      if (end && (end.rua || end.bairro || end.cidade)) {
        const ep = [];
        if (end.rua) ep.push(end.rua + (end.numero ? ', ' + end.numero : ''));
        if (end.bairro) ep.push(end.bairro);
        if (end.cidade) ep.push(end.cidade);
        parts.push(_encCP850('Endereco: ' + ep.join(' - ')));
        parts.push(LF);
        if (end.referencia) {
          parts.push(_encCP850('Ref: ' + end.referencia));
          parts.push(LF);
        }
        parts.push(LF);
      }

      // Observações
      if (d.observacoes) {
        parts.push(_encCP850(DASH_LINE));
        parts.push(LF);
        parts.push(ESC_BOLD_ON);
        parts.push(_encCP850('OBS:'));
        parts.push(LF);
        parts.push(ESC_BOLD_OFF);
        parts.push(_encCP850(d.observacoes));
        parts.push(LF);
        parts.push(LF);
      }

      // Rodapé
      parts.push(ESC_CENTER);
      parts.push(_encCP850(DASH_LINE));
      parts.push(LF);
      parts.push(_encCP850(_centerText('Pedido recebido na cozinha', W)));
      parts.push(LF);
      parts.push(LF);
      parts.push(LF);

      // Corte de papel
      parts.push(ESC_CUT);

      return _concatBytes(...parts);
    }

    // --- Estado do botao de impressora ---

    function _loadPrinterConfig() {
      // Limpa config legada do RawBT (nao mais suportado)
      try { localStorage.removeItem('kds_rawbt_url'); } catch(e) {}
      _updatePrinterButton();
    }

    function _updatePrinterButton() {
      const btn = document.getElementById('btn-printer');
      const statusEl = document.getElementById('printer-status');
      if (!btn || !statusEl) return;
      btn.classList.remove('connected', 'error');
      if (!_temPonteNativa()) {
        // Navegador comum: sem acesso USB
        statusEl.textContent = 'Sem USB';
        return;
      }
      if (window.AndroidPrint.isConnected()) {
        btn.classList.add('connected');
        statusEl.textContent = 'USB';
      } else {
        statusEl.textContent = 'Conectar';
      }
    }

    function abrirConfigImpressora() {
      // Dentro do app DoRafa Cozinha: conectar/testar a impressora USB
      if (_temPonteNativa()) {
        if (window.AndroidPrint.isConnected()) {
          _testarImpressaoNativa();
        } else {
          const ok = window.AndroidPrint.connect();
          if (ok) {
            showToast('Impressora USB conectada');
            _updatePrinterButton();
          } else {
            const err = window.AndroidPrint.getLastError ? window.AndroidPrint.getLastError() : '';
            showToast('USB falhou' + (err ? ': ' + err : ''), true);
          }
        }
        return;
      }
      // Navegador comum: explicar que a impressao USB exige o app
      document.getElementById('printer-overlay').classList.add('open');
    }

    function fecharConfigImpressora() {
      document.getElementById('printer-overlay').classList.remove('open');
    }

    function _testarImpressaoNativa() {
      if (!window.AndroidPrint || !window.AndroidPrint.isConnected()) {
        // Mostrar descritor USB para debug
        if (window.AndroidPrint && window.AndroidPrint.listUsbDevices) {
          const devs = window.AndroidPrint.listUsbDevices();
          showToast('USB: ' + devs.substring(0, 200), true);
          console.log('USB descriptor:', devs);
        } else {
          showToast('Impressora não conectada', true);
        }
        return;
      }
      // Cupom de teste minimal: reset + texto + LF + corte
      const ESC = 0x1B, GS = 0x1D;
      const testData = _concatBytes(
        new Uint8Array([ESC, 0x40]),                    // ESC @ — reset
        new Uint8Array([ESC, 0x74, 0x01]),              // ESC t 1 — CP850
        new Uint8Array([ESC, 0x61, 0x01]),              // centralizado
        _encCP850('--- TESTE KDS ---'), new Uint8Array([0x0A]),
        _encCP850('Impressora OK'), new Uint8Array([0x0A, 0x0A, 0x0A]),
        new Uint8Array([GS, 0x56, 0x42, 0x00])          // corte
      );
      const base64 = _bytesToBase64(testData);
      const ok = window.AndroidPrint.print(base64);
      if (ok) {
        showToast('Teste enviado com sucesso');
      } else {
        const err = window.AndroidPrint.getLastError ? window.AndroidPrint.getLastError() : '';
        showToast('Teste falhou' + (err ? ': ' + err : ''), true);
        console.log('print() falhou:', err);
        const devs = window.AndroidPrint.listUsbDevices ? window.AndroidPrint.listUsbDevices() : '';
        console.log('Dispositivos:', devs);
      }
    }

    function montarCupomHtml(pedido){
      const d = obterDadosPedido(pedido);
      const end = d.endereco;
      let endText = '';
      if (end && (end.rua || end.bairro || end.cidade)) {
        const parts = [];
        if (end.rua) parts.push(end.rua + (end.numero ? ', ' + end.numero : ''));
        if (end.bairro) parts.push(end.bairro);
        if (end.cidade) parts.push(end.cidade);
        endText = parts.join(' - ');
        if (end.referencia) endText += '\nRef: ' + end.referencia;
      }
      let itensHtml = '';
      const itens = Array.isArray(d.itens) ? d.itens : [];
      for (const it of itens) {
        const nome = safeText(it.nome || it.product_name || it.product_code);
        const qty = safeText(it.qty || it.quantidade || 1);
        const unit = Number(it.preco_unitario || it.unit_price || it.preco || 0);
        const totalItem = Number(it.total) || (qty * unit);
        itensHtml += `<div class="linha"><span>${qty}x ${nome}</span><span>${money(totalItem)}</span></div>`;
      }
      const criado = d.kds.created_em ? new Date(d.kds.created_em).toLocaleString('pt-BR') : '';
      return `
        <div class="cupom">
          <h3>Pedido ${d.idCurto}</h3>
          <div class="linha"><span>Cliente:</span><span>${d.cliente_nome || '-'}</span></div>
          <div class="linha"><span>Tipo:</span><span>${d.tipo || '-'}</span></div>
          <div class="linha"><span>Mesa:</span><span>${d.mesa || '-'}</span></div>
          <div class="linha"><span>Data:</span><span>${criado}</span></div>
          <div style="margin-top:4mm;border-top:1px dashed #000;padding-top:2mm;">
            ${itensHtml}
          </div>
          <div class="totais">
            <div class="linha"><span>Subtotal</span><span>${money(d.total - d.taxa)}</span></div>
            ${d.taxa ? `<div class="linha"><span>Taxa entrega</span><span>${money(d.taxa)}</span></div>` : ''}
            <div class="linha"><span><b>Total</b></span><span><b>${money(d.total)}</b></span></div>
          </div>
          ${endText ? `<div class="endereco"><b>Endereço:</b><br/>${endText.replace(/\n/g,'<br/>')}</div>` : ''}
          ${d.observacoes ? `<div class="obs"><b>Obs:</b> ${d.observacoes}</div>` : ''}
        </div>
      `;
    }

    async function imprimirCupom(pedido, cb){
      // Prioridade 1: ponte nativa AndroidPrint (app DoRafa Cozinha, USB Host)
      if (_temPonteNativa()) {
        try {
          if (!window.AndroidPrint.isConnected()) {
            const connected = window.AndroidPrint.connect();
            if (!connected) {
              const err = window.AndroidPrint.getLastError ? window.AndroidPrint.getLastError() : '';
              const devs = window.AndroidPrint.listUsbDevices ? window.AndroidPrint.listUsbDevices() : '';
              showToast('USB connect falhou' + (err ? ': ' + err : ''), true);
              console.log('AndroidPrint connect falhou:', err);
              console.log('Dispositivos USB:', devs);
              if (typeof cb === 'function') setTimeout(cb, 300);
              return;
            }
          }
          const data = montarCupomEscpos(pedido);
          const base64 = _bytesToBase64(data);
          const ok = window.AndroidPrint.print(base64);
          if (ok) {
            if (typeof cb === 'function') setTimeout(cb, 300);
            return;
          }
          const err = window.AndroidPrint.getLastError ? window.AndroidPrint.getLastError() : '';
          showToast('Impressora falhou' + (err ? ': ' + err : ''), true);
        } catch(e) {
          console.error('AndroidPrint erro:', e);
          showToast('Erro impressora nativa: ' + e.message, true);
        }
      } else {
        showToast('Impressão USB só no app DoRafa Cozinha', true);
      }
      // Prioridade 2: window.print() com CSS 80mm (impressora do sistema)
      const frame = document.getElementById('print-frame');
      frame.innerHTML = montarCupomHtml(pedido);
      window.print();
      if (typeof cb === 'function') setTimeout(cb, 300);
    }

    function _bytesToBase64(bytes) {
      let binary = '';
      const chunk = 0x8000;
      for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
      }
      return btoa(binary);
    }

    function aceitarEImprimir(id){
      const dados = window._dadosKDS || {};
      let pedido = null;
      Object.values(dados).some(lista => {
        pedido = lista.find(p => (p.id || p.solicitacao_id) === id);
        return !!pedido;
      });
      if (!pedido) return;
      imprimirCupom(pedido, () => {
        fetch('/api/kds/' + encodeURIComponent(id) + '/aceitar', {method: 'POST'})
          .then(r => r.json())
          .then(j => {
            if (j.ok) { showToast('Pedido aceito'); fecharDrawer(); carregar(); }
            else { showToast(j.error || 'Erro ao aceitar', true); }
          })
          .catch(() => showToast('Erro ao aceitar', true));
      });
    }

    function reimprimir(id){
      const dados = window._dadosKDS || {};
      let pedido = null;
      Object.values(dados).some(lista => {
        pedido = lista.find(p => (p.id || p.solicitacao_id) === id);
        return !!pedido;
      });
      if (pedido) imprimirCupom(pedido);
    }

    function marcarPronto(id){
      fetch('/api/kds/' + encodeURIComponent(id) + '/pronto', {method: 'POST'})
        .then(r => r.json())
        .then(j => {
          if (j.ok) { showToast('Marcado como pronto'); fecharDrawer(); carregar(); }
          else { showToast(j.error || 'Erro', true); }
        })
        .catch(() => showToast('Erro ao marcar pronto', true));
    }

    function sinalEntregar(id){
      fetch('/api/kds/' + encodeURIComponent(id) + '/sinal_entregar', {method: 'POST'})
        .then(r => r.json())
        .then(j => {
          if (j.ok) { showToast('Sinalizado para entrega'); fecharDrawer(); carregar(); }
          else { showToast(j.error || 'Erro', true); }
        })
        .catch(() => showToast('Erro ao sinalizar', true));
    }

    function abrirModalRecusa(id){
      document.getElementById('modal-overlay').classList.add('open');
      document.getElementById('motivo-recusa').value = 'OUTRO';
      document.getElementById('nota-recusa').value = '';
      document.getElementById('btn-confirmar-recusa').dataset.id = id;
    }

    function fecharModal(){
      document.getElementById('modal-overlay').classList.remove('open');
    }

    function confirmarRecusa(){
      const id = document.getElementById('btn-confirmar-recusa').dataset.id;
      const motivo = document.getElementById('motivo-recusa').value;
      const nota = document.getElementById('nota-recusa').value;
      fetch('/api/kds/' + encodeURIComponent(id) + '/recusar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({motivo_recusa: motivo, nota_recusa: nota}),
      })
        .then(r => r.json())
        .then(j => {
          fecharModal();
          if (j.ok) { showToast('Pedido recusado'); fecharDrawer(); carregar(); }
          else { showToast(j.error || 'Erro', true); }
        })
        .catch(() => { fecharModal(); showToast('Erro ao recusar', true); });
    }

    document.getElementById('btn-logout').addEventListener('click', () => {
      fetch('/ops/logout', {method: 'POST'}).then(() => location.reload());
    });

    document.addEventListener('DOMContentLoaded', () => {
      _loadPrinterConfig();
      _rodarDiagnosticoWebView();
      carregar();
      timer = setInterval(carregar, 3000);
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/cozinha/sw.js', {scope: '/cozinha/'}).catch(() => {});
      }
    });

    // ============================================================
    // DIAGNOSTICO: coleta evidencias concretas do que a WebView
    // suporta ou nao. So aparece dentro do APK (window.AndroidPrint).
    // ============================================================
    function _rodarDiagnosticoWebView() {
      if (!window.AndroidPrint) return; // so no APK
      var el = document.getElementById('diag-overlay');
      if (!el) return;
      el.style.display = 'block';
      var linhas = [];
      function p(s) { linhas.push(s); }

      // 1. User agent
      p('=== USER AGENT ===');
      p(navigator.userAgent);

      // 2. Viewport
      p('');
      p('=== VIEWPORT ===');
      p('innerWidth=' + window.innerWidth);
      p('innerHeight=' + window.innerHeight);
      p('devicePixelRatio=' + window.devicePixelRatio);
      p('clientWidth=' + document.documentElement.clientWidth);

      // 3. Verificar se o CSS servido e novo (sem var) ou antigo (com var)
      p('');
      p('=== CSS SERVIDO ===');
      try {
        var styles = document.querySelectorAll('style');
        var cssText = '';
        for (var i = 0; i < styles.length; i++) cssText += styles[i].textContent;
        p('tem var(-- = ' + (cssText.indexOf('var(--') >= 0));
        p('tem :root = ' + (cssText.indexOf(':root') >= 0));
        p('tem #0a5c2f = ' + (cssText.indexOf('#0a5c2f') >= 0));
        p('tem gap: = ' + (cssText.indexOf('gap:') >= 0));
        p('tem > * + * = ' + (cssText.indexOf('> * + *') >= 0));
      } catch(e) { p('css check ERRO: ' + e.message); }

      // 4. Service Worker
      p('');
      p('=== SERVICE WORKER ===');
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.getRegistrations().then(function(regs) {
          p('SW registrados = ' + regs.length);
          for (var i = 0; i < regs.length; i++) {
            p('  scope=' + regs[i].scope + ' script=' + (regs[i].active ? regs[i].active.scriptURL : 'none'));
          }
          el.textContent = linhas.join('\n');
        }).catch(function(e) { p('SW ERRO: ' + e.message); });
      } else { p('serviceWorker NAO suportado'); }

      // 5. Computed .stat (sempre visivel)
      p('');
      p('=== .stat ===');
      try {
        var stat = document.querySelector('.stat');
        if (stat) {
          var ss = getComputedStyle(stat);
          p('background=' + ss.backgroundColor);
          p('border=' + ss.border);
          p('padding=' + ss.padding);
          p('boxSizing=' + ss.boxSizing);
          p('width=' + ss.width);
          var r = stat.getBoundingClientRect();
          p('rect w=' + r.width + ' h=' + r.height);
        } else { p('.stat nao encontrado'); }
      } catch(e) { p('.stat ERRO: ' + e.message); }

      // 6. Computed .tab (sempre visivel)
      p('');
      p('=== .tab ===');
      try {
        var tab = document.querySelector('.tab');
        if (tab) {
          var ts2 = getComputedStyle(tab);
          p('background=' + ts2.backgroundColor);
          p('border=' + ts2.border);
          p('padding=' + ts2.padding);
          p('boxSizing=' + ts2.boxSizing);
          p('width=' + ts2.width);
          var r2 = tab.getBoundingClientRect();
          p('rect w=' + r2.width + ' h=' + r2.height);
        } else { p('.tab nao encontrado'); }
      } catch(e) { p('.tab ERRO: ' + e.message); }

      // 7. Card sintetico para medir renderizacao real
      p('');
      p('=== CARD SINTETICO ===');
      try {
        var tc = document.createElement('div');
        tc.className = 'card-item';
        tc.style.position = 'relative';
        tc.style.zIndex = '999';
        tc.innerHTML = '<div class="header"><div class="id">TESTE-001</div><div class="badge NOVO">NOVO</div></div><div class="cliente">Cliente Teste</div><div class="card-footer"><div class="card-total">R$ 25,00</div></div>';
        document.body.appendChild(tc);
        var cs = getComputedStyle(tc);
        p('background=' + cs.backgroundColor);
        p('border=' + cs.border);
        p('borderRadius=' + cs.borderRadius);
        p('padding=' + cs.padding);
        p('overflow=' + cs.overflow);
        p('boxSizing=' + cs.boxSizing);
        p('width=' + cs.width);
        var r3 = tc.getBoundingClientRect();
        p('rect w=' + r3.width + ' h=' + r3.height);
        var idEl = tc.querySelector('.id');
        var badgeEl = tc.querySelector('.badge');
        if (idEl && badgeEl) {
          p('id rect w=' + idEl.getBoundingClientRect().width);
          p('badge rect w=' + badgeEl.getBoundingClientRect().width);
          p('gap id-badge = ' + (badgeEl.getBoundingClientRect().left - idEl.getBoundingClientRect().right) + 'px');
        }
        setTimeout(function() { if (tc.parentNode) tc.parentNode.removeChild(tc); }, 10000);
      } catch(e) { p('card ERRO: ' + e.message); }

      // 8. .topbar
      p('');
      p('=== .topbar ===');
      try {
        var tb = document.querySelector('.topbar');
        if (tb) {
          var ts3 = getComputedStyle(tb);
          p('background=' + ts3.backgroundColor);
          p('position=' + ts3.position);
          p('padding=' + ts3.padding);
          p('borderRadius=' + ts3.borderRadius);
        }
      } catch(e) {}

      el.textContent = linhas.join('\n');
      setTimeout(function() { el.textContent = linhas.join('\n'); }, 3000);
    }
  </script>
</body>
</html>"""
