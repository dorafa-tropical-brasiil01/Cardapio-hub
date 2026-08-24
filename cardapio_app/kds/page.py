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
    :root{
      --verde: #0a5c2f;
      --amarelo: #fefecf;
      --verde-claro: #2f9e44;
      --vermelho: #e03131;
      --azul: #1971c2;
      --bg: #f3f0e7;
      --card: #ffffff;
      --border: rgba(10, 92, 47, 0.18);
      --text: #1f3322;
      --muted: #5c6b5f;
    }
    *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
    html,body{height:100%}
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:0;background:var(--bg);color:var(--text);line-height:1.35}
    #app{max-width:980px;margin:0 auto;padding:14px;padding-bottom:120px}
    .topbar{position:sticky;top:0;z-index:20;background:var(--verde);color:#fff;padding:14px 18px;border-radius:0 0 18px 18px;box-shadow:0 4px 12px rgba(0,0,0,0.08)}
    .topbar h1{margin:0;font-size:18px;font-weight:900}
    .topbar .sub{opacity:.85;font-size:12px}
    .topbar .logout{float:right;background:rgba(255,255,255,0.15);border:0;color:#fff;padding:8px 12px;border-radius:10px;font-weight:900;cursor:pointer}
    .tabs{display:flex;gap:6px;overflow-x:auto;padding:14px 0}
    .tab{flex:1;min-width:90px;background:var(--card);border:2px solid var(--border);border-radius:14px;padding:10px 8px;text-align:center;font-weight:900;font-size:13px;cursor:pointer;white-space:nowrap;color:var(--text)}
    .tab.active{background:var(--verde);border-color:var(--verde);color:#fff}
    .tab .count{display:block;font-size:11px;font-weight:400;opacity:.85;margin-top:2px}
    .stats{display:flex;gap:10px;margin-bottom:14px}
    .stat{flex:1;background:var(--card);border:2px solid var(--border);border-radius:14px;padding:12px;text-align:center}
    .stat .value{font-size:22px;font-weight:900;color:var(--verde)}
    .stat .label{font-size:11px;color:var(--muted);text-transform:uppercase}
    .list{display:flex;flex-direction:column;gap:12px}
    .card-item{background:var(--card);border:2px solid var(--border);border-radius:18px;padding:14px;cursor:pointer;transition:transform .05s ease;overflow:hidden}
    .card-item:active{transform:scale(.99)}
    .card-item .header{display:flex;align-items:center;justify-content:space-between;gap:10px;overflow:hidden;min-width:0}
    .card-item .id{font-weight:900;font-size:16px;flex-shrink:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .card-item .badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:900;flex-shrink:0;white-space:nowrap}
    .badge.NOVO{background:rgba(10,92,47,.08);color:var(--verde);border:1px solid rgba(10,92,47,.2)}
    .badge.EM_PREPARO{background:var(--amarelo);color:var(--verde);border:1px solid var(--verde)}
    .badge.PRONTO{background:var(--verde);color:#fff;border:1px solid var(--verde)}
    .badge.SINALIZADO{background:var(--azul);color:#fff;border:1px solid var(--azul)}
    .badge.ENTREGUE{background:#6b7280;color:#fff;border:1px solid #6b7280}
    .badge.RECUSADO{background:var(--vermelho);color:#fff;border:1px solid var(--vermelho)}
    .card-item .cliente{margin-top:8px;font-weight:700}
    .card-item .tipo{color:var(--muted);font-size:13px}
    .card-item .hora{color:var(--muted);font-size:12px;margin-top:6px}
    .empty{text-align:center;padding:40px 20px;color:var(--muted)}

    #drawer{position:fixed;inset:0;z-index:50;background:rgba(0,0,0,.45);display:none;align-items:flex-end;justify-content:center}
    #drawer.open{display:flex}
    #drawer .sheet{width:100%;max-width:980px;max-height:90vh;background:var(--card);border-radius:24px 24px 0 0;padding:18px;overflow-y:auto;animation:slideUp .2s ease}
    @keyframes slideUp{from{transform:translateY(100%)}to{transform:translateY(0)}}
    #drawer .close{position:absolute;top:14px;right:18px;background:none;border:0;font-size:24px;color:var(--muted);cursor:pointer}
    #drawer h2{margin:0 0 10px 0;font-size:18px}
    #drawer .section{margin:14px 0}
    #drawer .section-title{font-size:13px;font-weight:900;color:var(--verde);text-transform:uppercase;margin-bottom:6px}
    #drawer .muted{color:var(--muted);font-size:14px;white-space:pre-wrap}
    #drawer .item-row{padding:6px 0;border-bottom:1px solid rgba(10,92,47,.08);font-size:14px}
    #drawer .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
    #drawer .actions button{flex:1;min-width:140px;font-size:15px;padding:16px;border-radius:16px;border:0;font-weight:900;cursor:pointer}
    .btn-primary{background:var(--verde);color:#fff}
    .btn-secondary{background:rgba(10,92,47,.08);color:var(--verde);border:2px solid var(--border)!important}
    .btn-danger{background:var(--vermelho);color:#fff}
    .btn-wa{background:var(--verde-claro);color:#fff}
    .btn:disabled{opacity:.5;cursor:not-allowed}

    #modal-overlay{position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center}
    #modal-overlay.open{display:flex}
    #modal{background:var(--card);border-radius:20px;padding:20px;width:min(520px,92%);max-height:90vh;overflow-y:auto}
    #modal h3{margin:0 0 14px 0}
    #modal label{display:block;margin:10px 0 4px 0;font-weight:700}
    #modal select, #modal textarea{width:100%;padding:12px;border-radius:12px;border:2px solid var(--border);font-family:inherit;font-size:15px}
    #modal textarea{min-height:80px;resize:vertical}
    #modal .actions{display:flex;gap:10px;justify-content:flex-end;margin-top:18px}
    #modal .actions button{padding:12px 20px;border-radius:12px;border:0;font-weight:900;cursor:pointer}

    #print-frame{position:fixed;top:0;left:0;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none}
    @media print{
      body *{visibility:hidden}
      #print-frame, #print-frame *{visibility:visible}
      #print-frame{position:absolute;inset:0;width:100%;height:auto;opacity:1}
    }

    #toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);z-index:70;background:#1f3322;color:#fff;padding:12px 20px;border-radius:12px;font-weight:700;box-shadow:0 4px 12px rgba(0,0,0,.2);display:none}
    #toast.error{background:var(--vermelho)}

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
    <div class="topbar">
      <button class="logout" id="btn-logout" type="button">Sair</button>
      <h1>Cozinha</h1>
      <div class="sub">Painel de preparo</div>
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
      setTimeout(() => { el.style.display = 'none'; }, 3000);
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
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.aba === aba));
      render();
    }

    function obterDadosPedido(p){
      const base = p || {};
      const kds = base.kds || {};
      const record = base.record || base;
      const cliente = record.cliente || {};
      const entrega = record.entrega || {};
      const endereco = entrega.endereco || {};
      return {
        id: base.id,
        status: kds.status || 'NOVO',
        cliente_nome: cliente.nome || base.cliente_nome || '',
        cliente_whatsapp: cliente.whatsapp || base.cliente_whatsapp || '',
        tipo: record.tipo_entrega || base.tipo_entrega || base.kind || '',
        mesa: base.mesa || record.mesa || '',
        total: record.total || base.total || 0,
        observacoes: record.observacoes || base.observacoes || base.observacao || '',
        itens: base.itens || record.itens || record.items || [],
        endereco: endereco,
        taxa: entrega.taxa || 0,
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
            <div class="id">#${d.id}</div>
            <div class="badge ${d.status}">${statusLabel(d.status)}</div>
          </div>
          <div class="cliente">${d.cliente_nome || 'Cliente não informado'}</div>
          <div class="tipo">${d.tipo}${d.mesa ? ' • Mesa ' + d.mesa : ''}</div>
          <div class="hora">${criado}</div>
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
      } catch (e) {
        showToast('Erro ao carregar pedidos', true);
      }
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

      document.getElementById('drawer-titulo').textContent = 'Pedido #' + d.id;
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
      if (d.status === 'NOVO' || d.status === 'AGUARDANDO'){
        botoes = `
          <button class="btn-primary" onclick="aceitarEImprimir('${d.id}')">Aceitar e imprimir</button>
          <button class="btn-danger" onclick="abrirModalRecusa('${d.id}')">Recusar</button>
        `;
        if (d.cliente_whatsapp) {
          botoes += `<a class="btn-wa" href="${waUrl(d.cliente_whatsapp, 'Olá! Estamos entrando em contato sobre seu pedido.')}" target="_blank" rel="noopener">WhatsApp</a>`;
        }
      } else if (d.status === 'EM_PREPARO'){
        botoes = `<button class="btn-primary" onclick="marcarPronto('${d.id}')">Pronto</button>`;
      } else if (d.status === 'PRONTO'){
        botoes = `<button class="btn-primary" onclick="sinalEntregar('${d.id}')">Sinal para entregar</button>`;
      } else if (d.status === 'SINALIZADO'){
        botoes = `<button class="btn-secondary" onclick="reimprimir('${d.id}')">Reimprimir</button>`;
      } else if (d.status === 'RECUSADO'){
        if (d.cliente_whatsapp) {
          botoes = `<a class="btn-wa" href="${waUrl(d.cliente_whatsapp, 'Olá! Infelizmente precisamos falar sobre seu pedido.')}" target="_blank" rel="noopener">WhatsApp</a>`;
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
          <h3>Pedido #${d.id}</h3>
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

    function imprimirCupom(pedido, cb){
      const frame = document.getElementById('print-frame');
      frame.innerHTML = montarCupomHtml(pedido);
      window.print();
      if (typeof cb === 'function') setTimeout(cb, 300);
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
      carregar();
      timer = setInterval(carregar, 3000);
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/cozinha/sw.js', {scope: '/cozinha/'}).catch(() => {});
      }
    });
  </script>
</body>
</html>"""
