    const STORAGE_KEYS = {
        carrinho: "cardapio.cart.v1",
        pedido: "cardapio.lastPedido.v1",
        trackingPedido: "cardapio.trackingPedido.v1",
        payMethod: "cardapio.payMethod.v1",
        clientName: "cardapio.clientName.v1",
        clientWhatsapp: "cardapio.clientWhatsapp.v1",
        deliveryType: "cardapio.deliveryType.v1",
        deliveryRua: "cardapio.deliveryRua.v1",
        deliveryNumero: "cardapio.deliveryNumero.v1",
        deliveryBairro: "cardapio.deliveryBairro.v1",
        deliveryCidade: "cardapio.deliveryCidade.v1",
        deliveryRef: "cardapio.deliveryRef.v1",
        deliveryMaps: "cardapio.deliveryMaps.v1",
        deliveryObs: "cardapio.deliveryObs.v1",
        deliveryTroco: "cardapio.deliveryTroco.v1",
        mesa: "cardapio.mesa.v1",
        token: "cardapio.token.v1"
    };

    function _safeJsonParse(s) {
        try {
            return JSON.parse(String(s || "") || "{}");
        } catch {
            return null;
        }
    }

    function _parseHm(hm) {
        const m = String(hm || "").trim().match(/^(\d{1,2}):(\d{2})$/);
        if (!m) return null;
        const hh = Number(m[1]);
        const mm = Number(m[2]);
        if (!Number.isFinite(hh) || !Number.isFinite(mm)) return null;
        if (hh < 0 || hh > 23 || mm < 0 || mm > 59) return null;
        return hh * 60 + mm;
    }

    function _weekdayKeyInTz(tz) {
        const d = new Date();
        const parts = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: tz }).format(d);
        const map = { Mon: "mon", Tue: "tue", Wed: "wed", Thu: "thu", Fri: "fri", Sat: "sat", Sun: "sun" };
        return map[String(parts)] || "mon";
    }

    function _timeMinutesInTz(tz) {
        const d = new Date();
        const fmt = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz });
        const out = fmt.format(d);
        const m = String(out).match(/^(\d{2}):(\d{2})$/);
        if (!m) return null;
        const hh = Number(m[1]);
        const mm = Number(m[2]);
        if (!Number.isFinite(hh) || !Number.isFinite(mm)) return null;
        return hh * 60 + mm;
    }

    function _humanTzNow(tz) {
        try {
            return new Intl.DateTimeFormat("pt-BR", {
                timeZone: tz,
                weekday: "long",
                hour: "2-digit",
                minute: "2-digit",
            }).format(new Date());
        } catch {
            return "";
        }
    }

    function _calcOpenStateFromHorario(horario) {
        const mode = String(horario?.mode || "AUTO").trim().toUpperCase();
        const tz = String(horario?.tz || "America/Sao_Paulo").trim() || "America/Sao_Paulo";
        const closedMessage = String(horario?.closedMessage || "Estamos fechados no momento.").trim();

        if (mode === "ABERTO") {
            return { isOpen: true, reason: "override_open", tz, closedMessage, nextOpen: null, nowLabel: _humanTzNow(tz) };
        }
        if (mode === "FECHADO") {
            return { isOpen: false, reason: "override_closed", tz, closedMessage, nextOpen: null, nowLabel: _humanTzNow(tz) };
        }

        const hoursRaw = String(horario?.hours || "").trim();
        const hours = hoursRaw ? _safeJsonParse(hoursRaw) : null;
        if (!hours || typeof hours !== "object") {
            return { isOpen: true, reason: "no_hours", tz, closedMessage, nextOpen: null, nowLabel: _humanTzNow(tz) };
        }

        const dayKey = _weekdayKeyInTz(tz);
        const windows = Array.isArray(hours[dayKey]) ? hours[dayKey] : [];
        const nowMin = _timeMinutesInTz(tz);
        if (nowMin === null) {
            return { isOpen: true, reason: "tz_parse_fail", tz, closedMessage, nextOpen: null, nowLabel: _humanTzNow(tz) };
        }

        let openNow = false;
        let nextOpenMin = null;
        for (const w of windows) {
            const s = String(w || "").trim();
            const mm = s.match(/^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$/);
            if (!mm) continue;
            const a = _parseHm(mm[1]);
            const b = _parseHm(mm[2]);
            if (a === null || b === null) continue;
            if (nowMin >= a && nowMin <= b) {
                openNow = true;
            }
            if (nowMin < a) {
                if (nextOpenMin === null || a < nextOpenMin) nextOpenMin = a;
            }
        }

        let nextOpen = null;
        if (!openNow && nextOpenMin !== null) {
            const hh = String(Math.floor(nextOpenMin / 60)).padStart(2, "0");
            const mi = String(nextOpenMin % 60).padStart(2, "0");
            nextOpen = `${hh}:${mi}`;
        }

        return {
            isOpen: openNow,
            reason: openNow ? "in_window" : "out_window",
            tz,
            closedMessage,
            nextOpen,
            nowLabel: _humanTzNow(tz)
        };
    }

    function aplicarHorarioFuncionamento() {
        const horario = state.data?.ui?.horario;
        const info = _calcOpenStateFromHorario(horario);
        const panel = document.getElementById("closedPanel");
        const msg = document.getElementById("closedMessage");
        const next = document.getElementById("closedNext");
        const now = document.getElementById("closedLocalTime");

        const shouldBlock = !info.isOpen;
        if (panel) panel.style.display = (shouldBlock && !state.postOrderActive) ? "block" : "none";
        if (msg) msg.innerText = info.closedMessage || "";
        if (next) next.innerText = info.nextOpen ? `Próxima abertura hoje: ${info.nextOpen}` : "";
        if (now) now.innerText = info.nowLabel ? `Horário local: ${info.nowLabel}` : "";

        if (!state.postOrderActive) {
            const hideIds = ["queridinhos", "categoriasRow", "listaProdutos"];
            for (const id of hideIds) {
                const el = document.getElementById(id);
                if (!el) continue;
                el.style.display = shouldBlock ? "none" : "";
            }

            const secTitles = Array.from(document.querySelectorAll(".section-title"));
            for (const st of secTitles) {
                const t = String(st?.innerText || "").trim().toUpperCase();
                if (t === "QUERIDINHOS") {
                    st.style.display = shouldBlock ? "none" : "";
                }
            }
        }

        state.isOpenNow = !shouldBlock;
    }

    const state = {
        busca: "",
        categoriaId: "__todas__",
        carrinho: [],
        admin: false,
        bannerIndex: 0,
        bannerTimer: null,
        bannerSig: null,
        refreshTimer: null,
        mesa: null,
        token: null,
        solicitacaoTimer: null,
        data: null,
        sending: false,
        payMethod: "DINHEIRO",
        clientName: "",
        clientWhatsapp: "",
        deliveryType: "DELIVERY",
        deliveryRua: "",
        deliveryNumero: "",
        deliveryBairro: "",
        deliveryCidade: "",
        deliveryRef: "",
        deliveryMaps: "",
        deliveryObs: "",
        deliveryTroco: "",
        deliveryFeePreview: null,
        deliveryFeeDistanceKm: null,
        deliveryFeeEnabled: null,
        deliveryFeeLoading: false,
        deliveryFeeError: "",
        _lastDeliveryFeeMapsUrl: "",
        _skipFeeRefreshOnce: false,
        modalLockUntil: 0,
        modalCloseLabel: "Voltar",
        statusPublicoTimer: null,
        kdsPollingTimer: null,
        kdsPollingSid: null,
        postOrderPedido: null
    };

    async function refreshDeliveryFeePreview() {
        if (state._skipFeeRefreshOnce) {
            state._skipFeeRefreshOnce = false;
            return;
        }

        const isSalao = Boolean(state.mesa && state.token);
        if (isSalao) return;

        const tipo = String(state.deliveryType || "DELIVERY").toUpperCase();
        if (tipo !== "DELIVERY") {
            state.deliveryFeePreview = null;
            state.deliveryFeeDistanceKm = null;
            state.deliveryFeeEnabled = null;
            state.deliveryFeeError = "";
            return;
        }

        const mapsUrl = String(state.deliveryMaps || "").trim();
        if (!mapsUrl) {
            state.deliveryFeePreview = null;
            state.deliveryFeeDistanceKm = null;
            state.deliveryFeeEnabled = null;
            state.deliveryFeeError = "";
            return;
        }

        if (mapsUrl === state._lastDeliveryFeeMapsUrl && state.deliveryFeeEnabled !== null) {
            return;
        }
        state._lastDeliveryFeeMapsUrl = mapsUrl;
        state.deliveryFeeLoading = true;
        state.deliveryFeeError = "";

        try {
            const url = `/api/public/taxa_entrega?maps_url=${encodeURIComponent(mapsUrl)}`;
            const ac = new AbortController();
            const t = setTimeout(() => {
                try { ac.abort(); } catch {}
            }, 3500);
            const res = await fetch(url, { cache: "no-store", signal: ac.signal });
            clearTimeout(t);
            const j = await res.json().catch(() => ({}));

            if (!res.ok) {
                state.deliveryFeePreview = null;
                state.deliveryFeeDistanceKm = null;
                state.deliveryFeeEnabled = null;
                state.deliveryFeeError = String(j && j.error ? j.error : "falha_ao_calcular_taxa");
                return;
            }

            state.deliveryFeeEnabled = Boolean(j && j.enabled);
            if (j && j.ok && j.fee !== undefined && j.fee !== null) {
                const feeNum = Number(j.fee);
                state.deliveryFeePreview = Number.isFinite(feeNum) ? feeNum : null;
                const distNum = Number(j.distance_km);
                state.deliveryFeeDistanceKm = Number.isFinite(distNum) ? distNum : null;
            } else {
                state.deliveryFeePreview = null;
                state.deliveryFeeDistanceKm = null;
            }
        } catch {
            state.deliveryFeePreview = null;
            state.deliveryFeeDistanceKm = null;
            state.deliveryFeeEnabled = null;
            state.deliveryFeeError = "falha_ao_calcular_taxa";
        } finally {
            state.deliveryFeeLoading = false;
        }

        try {
            if (isModalOpen()) {
                const title = String(document.getElementById("modalTitle")?.innerText || "");
                if (title === "Carrinho / Pedido") {
                    const until = Number(state.modalLockUntil || 0);
                    const now = Date.now();
                    if (until && now < until) {
                        const waitMs = Math.min(6500, Math.max(50, until - now + 50));
                        setTimeout(() => {
                            try {
                                if (!isModalOpen()) return;
                                const t2 = String(document.getElementById("modalTitle")?.innerText || "");
                                if (t2 !== "Carrinho / Pedido") return;
                                state._skipFeeRefreshOnce = true;
                                abrirCarrinho(true);
                            } catch {
                            }
                        }, waitMs);
                        return;
                    }
                    state._skipFeeRefreshOnce = true;
                    abrirCarrinho(true);
                }
            }
        } catch {
        }
    }

    function humanStatus(status) {
        const s = String(status || "").toUpperCase();
        if (s === "ENVIADO") return "Aguardando confirmação do pedido";
        if (s === "PENDENTE") return "Aguardando confirmação do pedido";
        if (s === "EM_ATENDIMENTO") return "Pedido em atendimento pelo PDV";
        if (s === "RESPONDIDA") return "Pedido respondido";
        if (s === "CANCELADA" || s === "CANCELADO") return "Pedido cancelado";
        return s || "-";
    }

    function humanCategoryName(nome) {
        const raw = String(nome || "").trim();
        if (!raw) return "";
        const low = raw.toLowerCase();
        if (low === "mocktails" || low === "mocktail") return "Sucos Tropicais";
        return raw;
    }

    function getMesaTokenFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const mesaRaw = params.get("mesa");
        const tokenRaw = params.get("token");
        const mesa = mesaRaw ? Number(mesaRaw) : null;
        const token = tokenRaw ? String(tokenRaw) : null;
        if (!mesa || !Number.isFinite(mesa) || mesa <= 0) return { mesa: null, token: null };
        if (!token || token.length < 10) return { mesa, token: null };
        return { mesa, token };
    }

    function getMesaTokenFromLocal() {
        try {
            const mesaRaw = localStorage.getItem(STORAGE_KEYS.mesa);
            const tokenRaw = localStorage.getItem(STORAGE_KEYS.token);
            const mesa = mesaRaw ? Number(mesaRaw) : null;
            const token = tokenRaw ? String(tokenRaw) : null;
            if (!mesa || !Number.isFinite(mesa) || mesa <= 0) return { mesa: null, token: null };
            if (!token || token.length < 10) return { mesa, token: null };
            return { mesa, token };
        } catch {
            return { mesa: null, token: null };
        }
    }

    function saveMesaTokenToLocal(mesa, token) {
        try {
            if (mesa && token) {
                localStorage.setItem(STORAGE_KEYS.mesa, String(mesa));
                localStorage.setItem(STORAGE_KEYS.token, String(token));
            }
        } catch {
        }
    }

    function setCarrinhoQtd(produtoId, qtd) {
        const pid = String(produtoId || "").trim();
        const q = Number(qtd || 0);
        if (!pid) return;
        if (!Number.isFinite(q)) return;

        const produtos = Array.isArray(state.data?.produtos) ? state.data.produtos : [];
        const p = produtos.find(x => String(x?.id || "") === pid);
        if (!p) return;

        const idx = state.carrinho.findIndex(x => String(x.produtoId) === pid);
        if (q <= 0) {
            if (idx >= 0) state.carrinho.splice(idx, 1);
        } else if (idx >= 0) {
            state.carrinho[idx].qtd = q;
            state.carrinho[idx].nome = String(p.nome || state.carrinho[idx].nome || "");
            state.carrinho[idx].preco = Number(p.preco || state.carrinho[idx].preco || 0);
        } else {
            state.carrinho.push({
                produtoId: pid,
                nome: String(p.nome || ""),
                preco: Number(p.preco || 0),
                qtd: q,
            });
        }

        saveLocal();
        updateCartBadge();
    }

    function clearMesaTokenFromUrl() {
        try {
            const u = new URL(window.location.href);
            if (u.searchParams.has("mesa") || u.searchParams.has("token")) {
                u.searchParams.delete("mesa");
                u.searchParams.delete("token");
                history.replaceState(null, "", u.pathname + u.search + u.hash);
            }
        } catch {
        }
    }

    function formatBRL(valor) {
        return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }

    function loadLocal() {
        try {
            const cartRaw = localStorage.getItem(STORAGE_KEYS.carrinho);
            state.carrinho = cartRaw ? JSON.parse(cartRaw) : [];
        } catch {
            state.carrinho = [];
        }

        try {
            const pm = localStorage.getItem(STORAGE_KEYS.payMethod);
            if (pm) state.payMethod = normalizePayMethod(pm);
        } catch {
        }

        try {
            const cn = localStorage.getItem(STORAGE_KEYS.clientName);
            state.clientName = String(cn || "").trim();
        } catch {
            state.clientName = "";
        }

        try {
            const cw = localStorage.getItem(STORAGE_KEYS.clientWhatsapp);
            state.clientWhatsapp = String(cw || "").trim();
        } catch {
            state.clientWhatsapp = "";
        }

        try {
            const dt = localStorage.getItem(STORAGE_KEYS.deliveryType);
            const v = String(dt || "").trim().toUpperCase();
            if (v === "DELIVERY" || v === "RETIRADA") state.deliveryType = v;
        } catch {
        }

        try { state.deliveryRua = String(localStorage.getItem(STORAGE_KEYS.deliveryRua) || "").trim(); } catch { state.deliveryRua = ""; }
        try { state.deliveryNumero = String(localStorage.getItem(STORAGE_KEYS.deliveryNumero) || "").trim(); } catch { state.deliveryNumero = ""; }
        try { state.deliveryBairro = String(localStorage.getItem(STORAGE_KEYS.deliveryBairro) || "").trim(); } catch { state.deliveryBairro = ""; }
        try { state.deliveryCidade = String(localStorage.getItem(STORAGE_KEYS.deliveryCidade) || "").trim(); } catch { state.deliveryCidade = ""; }
        try { state.deliveryRef = String(localStorage.getItem(STORAGE_KEYS.deliveryRef) || "").trim(); } catch { state.deliveryRef = ""; }
        try { state.deliveryMaps = String(localStorage.getItem(STORAGE_KEYS.deliveryMaps) || "").trim(); } catch { state.deliveryMaps = ""; }
        try { state.deliveryObs = String(localStorage.getItem(STORAGE_KEYS.deliveryObs) || "").trim(); } catch { state.deliveryObs = ""; }
        try { state.deliveryTroco = String(localStorage.getItem(STORAGE_KEYS.deliveryTroco) || "").trim(); } catch { state.deliveryTroco = ""; }
    }

    function saveClientName() {
        try {
            localStorage.setItem(STORAGE_KEYS.clientName, String(state.clientName || ""));
        } catch {
        }
    }

    function saveClientWhatsapp() {
        try {
            localStorage.setItem(STORAGE_KEYS.clientWhatsapp, String(state.clientWhatsapp || ""));
        } catch {
        }
    }

    function onClientNameChange(val) {
        state.clientName = String(val || "").trim();
        saveClientName();
        lockModalRender(6000);
    }

    function onClientWhatsappChange(val) {
        state.clientWhatsapp = String(val || "").trim();
        saveClientWhatsapp();
        lockModalRender(6000);
    }

    function saveDeliveryFields() {
        try { localStorage.setItem(STORAGE_KEYS.deliveryType, String(state.deliveryType || "DELIVERY")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryRua, String(state.deliveryRua || "")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryNumero, String(state.deliveryNumero || "")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryBairro, String(state.deliveryBairro || "")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryCidade, String(state.deliveryCidade || "")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryRef, String(state.deliveryRef || "")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryMaps, String(state.deliveryMaps || "")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryObs, String(state.deliveryObs || "")); } catch {}
        try { localStorage.setItem(STORAGE_KEYS.deliveryTroco, String(state.deliveryTroco || "")); } catch {}
    }

    function onDeliveryTypeChange(val) {
        const v = String(val || "").trim().toUpperCase();
        state.deliveryType = (v === "RETIRADA") ? "RETIRADA" : "DELIVERY";
        saveDeliveryFields();
        state._lastDeliveryFeeMapsUrl = "";
        abrirCarrinho();
        refreshDeliveryFeePreview();
        lockModalRender(6000);
    }

    function onDeliveryFieldChange(key, val) {
        state[key] = String(val || "").trim();
        saveDeliveryFields();
        lockModalRender(6000);
    }

    function _mapsEmbedUrl(raw) {
        const s = String(raw || "").trim();
        if (!s) return "";
        const low = s.toLowerCase();
        if (low.includes("output=embed")) return s;
        const joiner = s.includes("?") ? "&" : "?";
        return s + joiner + "output=embed";
    }

    function setDeliveryMapsUrl(val) {
        state.deliveryMaps = String(val || "").trim();
        saveDeliveryFields();
        lockModalRender(6000);
        state._lastDeliveryFeeMapsUrl = "";
        refreshDeliveryFeePreview();
        try {
            if (isModalOpen()) {
                const title = String(document.getElementById("modalTitle")?.innerText || "");
                if (title === "Carrinho / Pedido") abrirCarrinho();
            }
        } catch {
        }
    }

    function promptDeliveryMaps() {
        const cur = String(state.deliveryMaps || "").trim();
        const next = prompt("Cole aqui o link do Google Maps:", cur);
        if (next === null) return;
        setDeliveryMapsUrl(next);
    }

    function _geoErrorMessage(err) {
        try {
            const code = Number(err && err.code);
            if (code === 1) return "Permissão de localização negada.";
            if (code === 2) return "Localização indisponível.";
            if (code === 3) return "Tempo esgotado ao obter localização.";
        } catch {
        }
        return "Não foi possível obter a localização.";
    }

    function usarMinhaLocalizacao() {
        const btn = (() => {
            try {
                return document.querySelector('button[onclick="usarMinhaLocalizacao()"]');
            } catch {
                return null;
            }
        })();

        const oldBtnText = btn ? String(btn.textContent || "") : "";
        if (btn) {
            try {
                btn.disabled = true;
                btn.textContent = "Obtendo localização...";
            } catch {
            }
        }

        try {
            if (!navigator || !navigator.geolocation) {
                setModal("Localização", `<div><strong>Seu navegador não suporta localização.</strong></div>`);
                abrirModal();
                if (btn) {
                    try {
                        btn.disabled = false;
                        btn.textContent = oldBtnText || "Usar minha localização";
                    } catch {
                    }
                }
                return;
            }
        } catch {
            setModal("Localização", `<div><strong>Seu navegador não suporta localização.</strong></div>`);
            abrirModal();
            if (btn) {
                try {
                    btn.disabled = false;
                    btn.textContent = oldBtnText || "Usar minha localização";
                } catch {
                }
            }
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                try {
                    const lat = Number(pos && pos.coords && pos.coords.latitude);
                    const lng = Number(pos && pos.coords && pos.coords.longitude);
                    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
                        setModal("Localização", `<div><strong>Não foi possível ler as coordenadas.</strong></div>`);
                        abrirModal();
                        return;
                    }
                    _setDeliveryFromLatLng(lat, lng);
                    try {
                        if (_deliveryLeafletMap) {
                            _deliveryLeafletMap.setView([lat, lng], 17);
                            if (_deliveryLeafletMarker) _deliveryLeafletMarker.setLatLng([lat, lng]);
                        }
                    } catch {
                    }
                } catch {
                    setModal("Localização", `<div><strong>Não foi possível obter a localização.</strong></div>`);
                    abrirModal();
                }

                if (btn) {
                    try {
                        btn.disabled = false;
                        btn.textContent = oldBtnText || "Usar minha localização";
                    } catch {
                    }
                }
            },
            (err) => {
                const msg = _geoErrorMessage(err);
                setModal("Localização", `<div><strong>${escapeHtml(msg)}</strong></div>`);
                abrirModal();

                if (btn) {
                    try {
                        btn.disabled = false;
                        btn.textContent = oldBtnText || "Usar minha localização";
                    } catch {
                    }
                }
            },
            { enableHighAccuracy: false, timeout: 20000, maximumAge: 60000 }
        );
    }

    // ESPELHO da fonte unica de verdade das modalidades de pagamento.
    //   Original: PDV/app/core/payment_methods.py
    //   Espelho Python: Cardapio/cardapio_app/payment_methods.py
    // Ao alterar um codigo interno, altere os tres lugares.
    // MISTO nao entra aqui de proposito: dividir um pagamento entre duas
    // modalidades exige informar quanto vai em cada uma, e isso so acontece
    // no PDV fisico, com o operador conferindo cada valor. No pedido online o
    // cliente informa apenas a intencao de pagamento, e "Misto" nao informa
    // nada de util para quem vai receber.
    const PAYMENT_METHODS = [
        { code: "DINHEIRO", label: "Dinheiro" },
        { code: "PIX", label: "PIX" },
        { code: "CARTAO_DEBITO", label: "Cartao de debito" },
        { code: "CARTAO_CREDITO", label: "Cartao de credito" },
    ];

    // "CARTAO" era o codigo generico usado antes da separacao debito/credito.
    // Pedidos e preferencias antigas sao migrados para credito.
    // "MISTO" salvo em navegadores antigos cai no padrao, porque a modalidade
    // deixou de ser ofertada online.
    function normalizePayMethod(val) {
        const code = String(val || "").trim().toUpperCase();
        if (!code) return "DINHEIRO";
        if (code === "CARTAO") return "CARTAO_CREDITO";
        return PAYMENT_METHODS.some((m) => m.code === code) ? code : "DINHEIRO";
    }

    function savePayMethod() {
        try {
            localStorage.setItem(STORAGE_KEYS.payMethod, normalizePayMethod(state.payMethod));
        } catch {
        }
    }

    function onPayMethodChange(val) {
        state.payMethod = normalizePayMethod(val);
        savePayMethod();
        lockModalRender(1500);
    }

    function capturePayMethodFromDom() {
        const el = document.getElementById("payMethod");
        if (!el) return;
        if (!el.value) return;
        state.payMethod = normalizePayMethod(el.value);
        savePayMethod();
    }

    async function uploadComprovante() {
        const pedido = getPedidoAtual();
        if (!pedido || !pedido.id) return;
        if (!state.mesa || !state.token) return;

        const inputFile = document.getElementById("comprovanteFile");
        const file = (inputFile && inputFile.files && inputFile.files.length > 0) ? inputFile.files[0] : null;

        if (!file) {
            setModal("Comprovante", `<div><strong>Selecione o PRINT (captura de tela) do comprovante (ou um PDF).</strong></div><div class="muted" style="margin-top:8px">No app do banco: abra o comprovante, faça um print (captura de tela) e depois volte aqui para selecionar o print na galeria. Se preferir, você também pode enviar o comprovante em PDF.</div>`);
            abrirModal();
            return;
        }

        const form = new FormData();
        form.append("file", file);

        try {
            const url = `/api/solicitacoes/${encodeURIComponent(pedido.id)}/comprovante?mesa=${encodeURIComponent(state.mesa)}&token=${encodeURIComponent(state.token)}`;
            const res = await fetch(url, { method: "POST", body: form });
            if (!res.ok) {
                let j = {};
                try { j = await res.json(); } catch {}

                const err = String(j.error || res.status || "");
                let msg = err;
                if (err === "extensao_nao_permitida") {
                    msg = "Formato não permitido. Envie PDF ou foto (JPG/PNG).";
                } else if (err === "arquivo_invalido" || err === "arquivo_nao_enviado") {
                    msg = "Arquivo inválido. Tente tirar uma foto do comprovante.";
                } else if (err === "comprovante_indisponivel") {
                    msg = "Comprovante disponível apenas quando o pedido for respondido como PIX.";
                }

                setModal("Comprovante", `<div><strong>Falha ao enviar comprovante:</strong> ${msg}</div>`);
                abrirModal();
                return;
            }
        } catch {
            setModal("Comprovante", `<div><strong>Falha ao enviar comprovante.</strong></div>`);
            abrirModal();
            return;
        }

        setModal("Comprovante", `<div><strong>Comprovante enviado com sucesso.</strong></div><div class="muted" style="margin-top:8px">Aguarde o operador confirmar o pagamento.</div>`);
        abrirModal();
        await refreshSolicitacao();
    }

    function saveLocal() {
        localStorage.setItem(STORAGE_KEYS.carrinho, JSON.stringify(state.carrinho));
    }

    function getCartCount() {
        return state.carrinho.reduce((acc, it) => acc + it.qtd, 0);
    }

    function getCartTotal() {
        return state.carrinho.reduce((acc, it) => acc + it.qtd * it.preco, 0);
    }

    function updateCartBadge() {
        document.getElementById("cartCount").innerText = String(getCartCount());
        updateNextStepHints();
    }

    function updateNextStepHints() {
        const hasItems = getCartCount() > 0;
        const ids = ["bottomCartBtn", "floatCartBtn", "sendOrderBtn"];
        for (const id of ids) {
            const el = document.getElementById(id);
            if (!el) continue;
            if (hasItems) el.classList.add("next-step-blink");
            else el.classList.remove("next-step-blink");
        }
    }

    function setModal(title, bodyHtml) {
        document.getElementById("modalTitle").innerText = title;
        document.getElementById("modalBody").innerHTML = bodyHtml;
    }

    function setModalCloseLabel(label) {
        try {
            state.modalCloseLabel = String(label || "Voltar");
            const btn = document.getElementById("modalCloseBtn");
            if (btn) {
                btn.textContent = state.modalCloseLabel;
                const isBack = state.modalCloseLabel.trim().toLowerCase() === "voltar";
                btn.classList.toggle("is-back", isBack);
            }
        } catch {
        }
    }

    function lockModalRender(ms) {
        const dur = Number(ms || 0);
        if (!Number.isFinite(dur) || dur <= 0) return;
        state.modalLockUntil = Date.now() + dur;
    }

    function isModalOpen() {
        const backdrop = document.getElementById("modalBackdrop");
        return Boolean(backdrop && backdrop.style.display === "flex");
    }

    function applyModalStatus(status) {
        const box = document.getElementById("modalBox");
        if (!box) return;

        const s = String(status || "").trim().toUpperCase();
        box.classList.remove("status-pendente", "status-em-atendimento", "status-respondida", "status-rejeitada");

        if (s === "EM_ATENDIMENTO") {
            box.classList.add("status-em-atendimento");
        } else if (s === "RESPONDIDA" || s === "ACEITA" || s === "ACEITO") {
            box.classList.add("status-respondida");
        } else if (s === "REJEITADA" || s === "REJEITADO" || s === "CANCELADA" || s === "CANCELADO") {
            box.classList.add("status-rejeitada");
        } else if (s === "PENDENTE" || s === "ENVIADO") {
            box.classList.add("status-pendente");
        } else {
            box.classList.add("status-pendente");
        }
    }

    function abrirModal() {
        const backdrop = document.getElementById("modalBackdrop");
        backdrop.style.display = "flex";
        backdrop.setAttribute("aria-hidden", "false");
    }

    function fecharModal() {
        setModalCloseLabel("Voltar");
        const backdrop = document.getElementById("modalBackdrop");
        backdrop.style.display = "none";
        backdrop.setAttribute("aria-hidden", "true");
    }

    function irAoInicio() {
        state.categoriaId = "__todas__";
        state.busca = "";
        try {
            const input = document.getElementById("search");
            if (input) input.value = "";
        } catch {
        }

        render();

        const anchor = document.getElementById("listaProdutos");
        if (anchor) {
            try {
                anchor.scrollIntoView({ behavior: "smooth", block: "start" });
                return;
            } catch {
            }
        }

        try {
            window.scrollTo({ top: 0, behavior: "smooth" });
        } catch {
            window.scrollTo(0, 0);
        }
    }

    function abrirCategorias() {
        setModalCloseLabel("Voltar");
        const cats = state.data?.categorias || [];
        const html = `
            <div class="category-list">
                <button class="pill ${state.categoriaId === "__todas__" ? "active" : ""}" onclick="selecionarCategoria('__todas__')">Todas</button>
                ${cats.map(c => `<button class="pill ${state.categoriaId === c.id ? "active" : ""}" onclick="selecionarCategoria('${c.id}')">${escapeHtml(humanCategoryName(c.nome))}</button>`).join("")}
            </div>
        `;
        setModal("Categorias", html);
        abrirModal();
    }

    function selecionarCategoria(categoriaId) {
        state.categoriaId = categoriaId;
        render();
        fecharModal();
    }

    function renderCategoriasRow() {
        const row = document.getElementById("categoriasRow");
        if (!row) return;

        row.innerHTML = "";
    }

    function addCarrinho(produtoId, el) {
        const pid = String(produtoId || "").trim();
        if (!pid) return;

        const produtos = Array.isArray(state.data?.produtos) ? state.data.produtos : [];
        const p = produtos.find(x => String(x?.id || "") === pid);
        if (!p) return;

        try {
            const btn = el && el.classList ? el : null;
            if (btn) {
                btn.classList.add("flash-added");
                window.setTimeout(() => {
                    try { btn.classList.remove("flash-added"); } catch { }
                }, 260);
            }
        } catch {
        }

        const idx = state.carrinho.findIndex(x => String(x.produtoId) === pid);
        if (idx >= 0) {
            state.carrinho[idx].qtd += 1;
        } else {
            state.carrinho.push({
                produtoId: pid,
                nome: String(p.nome || ""),
                preco: Number(p.preco || 0),
                qtd: 1,
            });
        }

        saveLocal();
        updateCartBadge();

        try {
            if (el && el.classList) {
                el.classList.add("flash-added");
                window.setTimeout(() => {
                    try { el.classList.remove("flash-added"); } catch {}
                }, 260);
            }
        } catch {
        }
    }

    function abrirTelaPosEnvio(pedido) {
        const raw = state.data?.ui?.postOrderImage || state.data?.ui?.afterSendImage || state.data?.ui?.posEnvioImagem;
        const imgRaw = normalizeAnyAssetUrl(raw);
        const img = imgRaw
            ? (imgRaw + (imgRaw.includes("?") ? "&" : "?") + "t=" + Date.now())
            : "";
        const imgHtml = img
            ? `<div style="margin-top:10px"><img src="${img}" alt="Pedido enviado" style="width:100%; max-height:320px; object-fit:cover; border-radius:16px"></div>`
            : "";
        const txt = "Seu pedido foi enviado. Aguarde a confirmação.";
        setModal(
            "Pedido enviado",
            `<div><strong>${txt}</strong></div>`
            + imgHtml
            + `<div style="margin-top:14px; display:flex; gap:10px; flex-wrap:wrap">`
            + `<button onclick="fecharModal(); window.scrollTo({ top: 0, behavior: 'smooth' });">Voltar</button>`
            + `</div>`
        );
        abrirModal();
    }

    function alterarQtd(produtoId, delta) {
        const idx = state.carrinho.findIndex(x => x.produtoId === produtoId);
        if (idx < 0) return;
        state.carrinho[idx].qtd += delta;
        if (state.carrinho[idx].qtd <= 0) state.carrinho.splice(idx, 1);
        saveLocal();
        updateCartBadge();
        abrirCarrinho();
    }

    function limparCarrinho() {
        state.carrinho = [];
        saveLocal();
        updateCartBadge();
        abrirCarrinho();
    }

    function getPedidoAtual() {
        try {
            const raw = localStorage.getItem(STORAGE_KEYS.pedido);
            const p = raw ? JSON.parse(raw) : null;
            if (!p || !p.id) return null;
            const kind = String(p.kind || "").toUpperCase();
            // Evita reaproveitar pedido antigo de outra mesa/token
            if (kind !== "DELIVERY") {
                if (state.mesa && String(p.mesa || "") !== String(state.mesa)) return null;
                if (state.token && String(p.token || "") !== String(state.token)) return null;
            }
            // Compatibilidade: versões antigas salvavam status "ENVIADO"
            if (String(p.status || "").toUpperCase() === "ENVIADO") {
                p.status = "PENDENTE";
            }

            // Expira pedidos muito antigos para não aparecerem como "pedido atual" para sempre
            // (o carrinho é um dispositivo de mesa; pedido antigo não deve ficar meses visível).
            try {
                const created = Date.parse(String(p.criadoEm || p.criado_em || ""));
                if (Number.isFinite(created)) {
                    const ageMs = Date.now() - created;
                    if (ageMs > 12 * 60 * 60 * 1000) {
                        return null;
                    }
                }
            } catch {
            }

            return p;
        } catch {
            return null;
        }
    }

    function savePedidoAtual(pedido) {
        localStorage.setItem(STORAGE_KEYS.pedido, JSON.stringify(pedido));
    }

    function clearPedidoAtual() {
        try {
            localStorage.removeItem(STORAGE_KEYS.pedido);
        } catch {
        }
    }

    function saveTrackingPedido(tracking) {
        localStorage.setItem(STORAGE_KEYS.trackingPedido, JSON.stringify(tracking));
    }

    function getTrackingPedido() {
        try {
            const raw = localStorage.getItem(STORAGE_KEYS.trackingPedido);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }

    function clearTrackingPedido() {
        try {
            localStorage.removeItem(STORAGE_KEYS.trackingPedido);
        } catch {
        }
    }

    function safeClearPedidoAtual() {
        const p = getPedidoAtual();
        if (!p) {
            clearPedidoAtual();
            abrirCarrinho();
            return;
        }

        const ok = confirm("Deseja realmente limpar o pedido deste dispositivo?\n\nIsso não cancela no PDV, apenas remove desta tela.");
        if (!ok) return;
        clearPedidoAtual();
        abrirCarrinho();
    }

    async function enviarPedido() {
        if (state.carrinho.length === 0) return;

        if (state.sending) return;

        clearTrackingPedido();

        const pagamento_preferido = normalizePayMethod(state.payMethod);

        const isSalao = Boolean(state.mesa && state.token);
        const produtosMap = new Map((state.data?.produtos || []).map(p => [p.id, p]));
        const itens = state.carrinho.map(it => {
            const p = produtosMap.get(it.produtoId);
            const pdvCode = p && p.pdvCode ? String(p.pdvCode) : "";
            return {
                product_code: pdvCode || String(it.produtoId),
                nome: it.nome,
                qty: it.qtd
            };
        });

        let payload;
        let url;
        if (isSalao) {
            payload = {
                mesa: state.mesa,
                token: state.token,
                cliente_nome: String(state.clientName || "").trim(),
                cliente_whatsapp: String(state.clientWhatsapp || "").trim() || null,
                pagamento_preferido,
                itens,
                total_estimado: getCartTotal()
            };
            url = "/api/solicitacoes";
        } else {
            const nome = String(state.clientName || "").trim();
            const whatsapp = String(state.clientWhatsapp || "").trim();
            if (!nome) {
                setModal("Delivery / Retirada", `<div><strong>Informe o nome do cliente.</strong></div>`);
                abrirModal();
                return;
            }
            if (!whatsapp) {
                setModal("Delivery / Retirada", `<div><strong>Informe o WhatsApp do cliente.</strong></div>`);
                abrirModal();
                return;
            }

            const tipo_entrega = String(state.deliveryType || "DELIVERY").toUpperCase();
            const endereco = {
                rua: String(state.deliveryRua || "").trim() || null,
                numero: String(state.deliveryNumero || "").trim() || null,
                bairro: String(state.deliveryBairro || "").trim() || null,
                cidade: String(state.deliveryCidade || "").trim() || null,
                referencia: String(state.deliveryRef || "").trim() || null,
                maps_url: String(state.deliveryMaps || "").trim() || null,
            };

            if (tipo_entrega === "DELIVERY") {
                const hasMaps = Boolean(String(endereco.maps_url || "").trim());
                if (!hasMaps) {
                    setModal("Delivery / Retirada", `<div><strong>Informe a localização (Google Maps) para Delivery.</strong></div>`);
                    abrirModal();
                    return;
                }
            }

            let troco_para = null;
            if (pagamento_preferido === "DINHEIRO") {
                const trocoRaw = String(state.deliveryTroco || "").trim();
                if (trocoRaw) {
                    const n = Number(trocoRaw.replace(",", "."));
                    if (!Number.isFinite(n) || n < 0) {
                        setModal("Delivery / Retirada", `<div><strong>Troco inválido.</strong></div>`);
                        abrirModal();
                        return;
                    }
                    troco_para = n;
                }
            }

            payload = {
                cliente_nome: nome,
                cliente_whatsapp: whatsapp,
                tipo_entrega: (tipo_entrega === "RETIRADA" ? "RETIRADA" : "DELIVERY"),
                endereco,
                troco_para,
                observacoes: (String(state.deliveryObs || "").trim() || null),
                pagamento_preferido,
                itens,
                total_estimado: getCartTotal()
            };
            url = "/api/public/pedidos";
        }

        let res;
        try {
            state.sending = true;
            abrirCarrinho();
            res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        } catch {
            state.sending = false;
            setModal("Erro", `<div><strong>Não foi possível enviar o pedido.</strong></div>`);
            abrirModal();
            return;
        }

        if (!res.ok) {
            state.sending = false;
            let j = {};
            try { j = await res.json(); } catch {}
            setModal("Erro", `<div><strong>Falha ao enviar:</strong> ${(j.error || "desconhecido")}</div>`);
            abrirModal();
            return;
        }

        const out = await res.json();
        const kind = isSalao ? "SALAO" : "DELIVERY";

        // Na resposta pública de delivery, o backend retorna os campos financeiros
        // quando o pedido é cobrado online (PIX).
        const statusPublico = String(out.status || "").toUpperCase();
        const pagamentoOnline = Boolean(out.pagamento_online);

        const pedido = {
            id: out.id,
            kind,
            mesa: isSalao ? state.mesa : null,
            token: isSalao ? state.token : null,
            access_token: (!isSalao && out.token) ? out.token : null,
            criadoEm: new Date().toISOString(),
            status: statusPublico || "PENDENTE",
            cliente_nome: String(state.clientName || "").trim(),
            cliente_whatsapp: String(state.clientWhatsapp || "").trim() || null,
            tipo_entrega: !isSalao ? String(state.deliveryType || "DELIVERY").toUpperCase() : null,
            endereco: null,
            troco_para: !isSalao ? (String(state.deliveryTroco || "").trim() || null) : null,
            observacoes: null,
            pagamento_preferido,
            pagamento_online: pagamentoOnline,
            pagamento: out.pagamento || null,
            estado_pagamento: out.estado_pagamento || null,
            pode_retentar: Boolean(out.pode_retentar),
            payment_window_expires_at: out.payment_window_expires_at || null,
            itens: state.carrinho.map(it => ({
                produtoId: it.produtoId,
                nome: it.nome,
                qtd: it.qtd,
                preco: it.preco
            })),
            total: Number(out.total) || getCartTotal()
        };

        // Salvar tracking para acompanhamento na tela de agradecimento
        if (!isSalao && out.token) {
            const tracking = {
                id: out.id,
                access_token: out.token,
                kind,
                tipo_entrega: String(state.deliveryType || "DELIVERY").toUpperCase(),
                status: pedido.status,
                pagamento_online: pagamentoOnline,
                pagamento: out.pagamento || null,
                estado_pagamento: out.estado_pagamento || null,
                pode_retentar: Boolean(out.pode_retentar)
            };
            saveTrackingPedido(tracking);
        } else if (isSalao) {
            saveTrackingPedido({
                id: out.id,
                kind,
                mesa: state.mesa,
                token: state.token
            });
        }

        // Fluxo simplificado: após enviar, permite novo pedido imediatamente.
        // O pedido NÃO some do PDV; apenas não mantemos "pedido atual" nesta tela.
        clearPedidoAtual();
        state.sending = false;
        state.carrinho = [];
        saveLocal();
        updateCartBadge();
        showPostOrderScreen(pedido);
    }

    function showMainScreen() {
        const post = document.getElementById("postOrderScreen");
        const header = document.querySelector("header");
        const search = document.querySelector(".search-bar");
        const banner = document.getElementById("banner");
        const sectionTitle = document.querySelector(".section-title");
        const queridinhos = document.getElementById("queridinhos");
        const closedPanel = document.getElementById("closedPanel");
        const toolbar = document.querySelector(".toolbar");
        const list = document.getElementById("listaProdutos");
        const credit = document.getElementById("appFooterCredit");
        const bottomBar = document.getElementById("bottomBar");
        const floating = document.getElementById("floatingActions");
        const whatsFloat = document.getElementById("whatsFloat");

        stopStatusPublicoPolling();
        stopKdsPolling();
        clearTrackingPedido();
        state.postOrderActive = false;
        state.postOrderPedido = null;
        if (post) post.style.display = "none";
        if (header) header.style.display = "flex";
        if (search) search.style.display = "block";
        if (banner) banner.style.display = "block";
        if (sectionTitle) sectionTitle.style.display = "block";
        if (queridinhos) queridinhos.style.display = "flex";
        if (closedPanel) closedPanel.style.display = "none";
        if (toolbar) toolbar.style.display = "block";
        if (list) list.style.display = "block";
        if (credit) credit.style.display = "block";
        if (bottomBar) bottomBar.style.display = "flex";
        if (floating) floating.style.display = "none";
        if (whatsFloat) whatsFloat.style.display = "none";
    }

    function normalizeAnyAssetUrl(v) {
        if (v && typeof v === "object") {
            const any = v;
            const candidate = any.path || any.url || any.src || any.href || "";
            v = candidate;
        }
        const s = String(v || "").trim();
        if (!s) return "";
        const low = s.toLowerCase();
        if (low.startsWith("http://") || low.startsWith("https://")) return s;
        if (s.startsWith("/assets/")) return s;
        if (s.startsWith("assets/")) return "/" + s;
        if (s.startsWith("/")) return s;
        return "/assets/" + s;
    }

    function showPostOrderScreen(pedidoInfo) {
        if (pedidoInfo) {
            state.postOrderPedido = pedidoInfo;
        } else if (state.postOrderPedido) {
            pedidoInfo = state.postOrderPedido;
        }

        const post = document.getElementById("postOrderScreen");
        const header = document.querySelector("header");
        const search = document.querySelector(".search-bar");
        const banner = document.getElementById("banner");
        const sectionTitle = document.querySelector(".section-title");
        const queridinhos = document.getElementById("queridinhos");
        const closedPanel = document.getElementById("closedPanel");
        const toolbar = document.querySelector(".toolbar");
        const list = document.getElementById("listaProdutos");
        const credit = document.getElementById("appFooterCredit");
        const bottomBar = document.getElementById("bottomBar");
        const floating = document.getElementById("floatingActions");
        const whatsFloat = document.getElementById("whatsFloat");
        const img = document.getElementById("postOrderImage");

        state.postOrderActive = true;

        try {
            if (isModalOpen()) {
                fecharModal();
            }
        } catch {
        }

        if (header) header.style.display = "none";
        if (search) search.style.display = "none";
        if (banner) banner.style.display = "none";
        if (sectionTitle) sectionTitle.style.display = "none";
        if (queridinhos) queridinhos.style.display = "none";
        if (closedPanel) closedPanel.style.display = "none";
        if (toolbar) toolbar.style.display = "none";
        if (list) list.style.display = "none";
        if (credit) credit.style.display = "none";
        if (bottomBar) bottomBar.style.display = "none";
        if (floating) floating.style.display = "none";
        if (whatsFloat) whatsFloat.style.display = "none";
        if (post) post.style.display = "block";

        try {
            const raw = state.data?.ui?.postOrderImage || state.data?.ui?.afterSendImage || state.data?.ui?.posEnvioImagem
                || state.data?.ui?.banner?.imagens?.[0]
                || state.data?.ui?.logo;
            const srcRaw = normalizeAnyAssetUrl(raw);
            const src = srcRaw
                ? (srcRaw + (srcRaw.includes("?") ? "&" : "?") + "t=" + Date.now())
                : "";
            if (img && src) {
                img.src = src;
                img.style.display = "block";
                img.onerror = () => { img.style.display = "none"; };
            } else if (img) {
                img.style.display = "none";
            }
        } catch {
            if (img) img.style.display = "none";
        }

        // Fluxo SALAO: se pedidoInfo foi fornecido e kind === "SALAO"
        if (pedidoInfo && pedidoInfo.kind === "SALAO") {
            const solicitacaoId = pedidoInfo.id;
            const mesa = pedidoInfo.mesa;
            const token = pedidoInfo.token;
            const kdsStatusArea = document.getElementById("kdsStatusArea");
            const kdsStatusText = document.getElementById("kdsStatusText");
            const statusPublicoDiv = document.getElementById("postOrderStatusPublico");
            const paymentArea = document.getElementById("postOrderPaymentArea");

            if (paymentArea) {
                paymentArea.style.display = "none";
            }

            if (solicitacaoId && mesa && token && kdsStatusArea && kdsStatusText) {
                kdsStatusArea.style.display = "block";
                kdsStatusText.textContent = "Pedido recebido";
                if (statusPublicoDiv) {
                    statusPublicoDiv.style.display = "none";
                }
                startKdsPolling(solicitacaoId, mesa, token);
            }
        } else {
            // Fluxo DELIVERY: manter mecanismo existente de status público
            try {
                const tracking = getTrackingPedido();
                const statusPublicoDiv = document.getElementById("postOrderStatusPublico");
                if (tracking && tracking.access_token && statusPublicoDiv) {
                    statusPublicoDiv.style.display = "block";

                    // Renderiza pagamento inicial com os dados do tracking (que ja
                    // foram salvos com pagamento, estado_pagamento etc.)
                    if (tracking.pagamento_online) {
                        renderPagamentoNaTela(tracking);
                        const status = String(tracking.estado_pagamento || "").toUpperCase();
                        if (status && status !== "CONFIRMADO" && status !== "NAO_APLICAVEL") {
                            statusPublicoDiv.innerText = "Aguardando pagamento";
                        }
                    }

                    if (!state.statusPublicoTimer) {
                        if (!statusPublicoDiv.innerText) {
                            statusPublicoDiv.innerText = "Carregando status...";
                        }
                        startStatusPublicoPolling();
                    }
                } else if (statusPublicoDiv) {
                    statusPublicoDiv.style.display = "none";
                }
            } catch {
                const statusPublicoDiv = document.getElementById("postOrderStatusPublico");
                if (statusPublicoDiv) {
                    statusPublicoDiv.style.display = "none";
                }
            }
        }
    }

    function renderStatusPublicoNaTela(statusPublico, tipoEntrega) {
        const statusDiv = document.getElementById("postOrderStatusPublico");
        if (!statusDiv) return;

        const tipo = String(tipoEntrega || "").toUpperCase();
        const labels = {
            "ENVIADO": "Pedido enviado",
            "ACEITO": "Pedido aceito",
            "PREPARANDO": "Pedido em preparo",
            "PRONTO": tipo === "RETIRADA" ? "Pedido pronto para retirada" : "Pedido pronto",
            "EM_ENTREGA": "EM ROTA",
            "ENTREGUE": "Pedido entregue",
            "AGUARDANDO_PAGAMENTO": "Aguardando pagamento",
            "PAGAMENTO_EXPIRADO": "QR Code expirado",
            "PAGAMENTO_RECUSADO": "Pagamento recusado",
            "PAGAMENTO_FALHOU": "Falha no pagamento"
        };

        const texto = labels[statusPublico] || statusPublico;
        statusDiv.innerText = texto;
    }

    function _formatarDataHoraBr(iso) {
        if (!iso) return "";
        try {
            const d = new Date(iso);
            if (Number.isNaN(d.getTime())) return String(iso);
            return d.toLocaleString("pt-BR", {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit"
            });
        } catch {
            return String(iso);
        }
    }

    function _qrCodeUrl(v) {
        // Aceita caminhos relativos a /assets, URLs absolutas, ou strings base64.
        const s = String(v || "").trim();
        if (!s) return "";
        if (s.startsWith("http://") || s.startsWith("https://")) return s;
        if (s.startsWith("data:")) return s;
        if (s.startsWith("/")) return s;
        return "/assets/" + s;
    }

    function renderPagamentoNaTela(data) {
        const area = document.getElementById("postOrderPaymentArea");
        if (!area) return;

        const header = document.getElementById("postOrderPaymentHeader");
        const body = document.getElementById("postOrderPaymentBody");
        if (!header || !body) return;

        const pagamentoOnline = Boolean(data && data.pagamento_online);
        const estado = String(data.estado_pagamento || "").toUpperCase();

        // Pedido que nao cobra online, ou ja finalizado: esconde a area de pagamento.
        if (!pagamentoOnline || estado === "NAO_APLICAVEL" || estado === "CONFIRMADO") {
            area.style.display = "none";
            header.innerHTML = "";
            body.innerHTML = "";
            return;
        }

        area.style.display = "block";

        const pagamento = data.pagamento || {};
        const amount = Number(pagamento.amount) || Number(data.total) || 0;
        const payload = String(pagamento.qr_code_payload || "").trim();
        const imageUrl = _qrCodeUrl(pagamento.qr_code_image_url);
        const expiresAt = _formatarDataHoraBr(pagamento.expires_at);
        const podeRetentar = Boolean(data.pode_retentar);
        const windowExpiresAt = _formatarDataHoraBr(data.payment_window_expires_at);

        const titulos = {
            "NAO_INICIADO": "Aguardando pagamento",
            "AGUARDANDO": "Aguardando pagamento",
            "EXPIRADO": "QR Code expirado",
            "RECUSADO": "Pagamento recusado",
            "FALHA": "Falha ao gerar pagamento"
        };
        const titulo = titulos[estado] || "Pagamento";

        let html = "";

        if (estado === "AGUARDANDO" || estado === "NAO_INICIADO") {
            html += `<div class="payment-amount">${formatBRL(amount)}</div>`;
            html += `<div class="payment-hint">Escaneie o QR Code com o app do seu banco ou copie o codigo PIX.</div>`;

            if (imageUrl) {
                html += `<div class="qr-panel"><img src="${escapeHtml(imageUrl)}" alt="QR Code PIX" onerror="this.style.display='none'" /></div>`;
            }

            if (payload) {
                html += `<textarea id="pixPayload" class="qr-payload" rows="3" readonly>${escapeHtml(payload)}</textarea>`;
                html += `<div class="payment-actions"><button type="button" onclick="copiarPix()">Copiar codigo PIX</button></div>`;
            } else if (!imageUrl) {
                html += `<div class="payment-hint">Codigo PIX nao disponivel. Tente gerar novamente.</div>`;
            }

            if (expiresAt) {
                html += `<div class="payment-countdown">V&aacute;lido at&eacute; ${escapeHtml(expiresAt)}</div>`;
            }
        } else if (estado === "EXPIRADO" || estado === "RECUSADO" || estado === "FALHA") {
            html += `<div class="payment-amount">${formatBRL(amount)}</div>`;
            html += `<div class="payment-hint">O pagamento anterior n&atilde;o foi conclu&iacute;do.</div>`;

            if (podeRetentar) {
                html += `<div class="payment-actions"><button type="button" onclick="pagarNovamente()">Gerar novo QR Code</button></div>`;
                if (windowExpiresAt) {
                    html += `<div class="payment-countdown">Voc&ecirc; pode gerar um novo QR at&eacute; ${escapeHtml(windowExpiresAt)}</div>`;
                }
            } else {
                html += `<div class="payment-hint">Janela de retentativa encerrada. Entre em contato com o estabelecimento.</div>`;
            }
        }

        header.innerHTML = escapeHtml(titulo);
        body.innerHTML = html;
    }

    async function pagarNovamente() {
        const tracking = getTrackingPedido();
        if (!tracking || !tracking.id || !tracking.access_token) return;

        const idempotency = (typeof crypto !== "undefined" && crypto.randomUUID)
            ? crypto.randomUUID()
            : (`retentativa-` + Date.now() + "-" + Math.random().toString(36).slice(2));

        try {
            const url = `/api/public/pedidos/${encodeURIComponent(tracking.id)}/pagar?token=${encodeURIComponent(tracking.access_token)}`;
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ idempotency_key: idempotency })
            });

            if (!res.ok) {
                const j = await res.json().catch(() => ({}));
                setModal("Pagamento", `<div><strong>N&atilde;o foi poss&iacute;vel gerar novo QR Code.</strong></div><div class="muted">${escapeHtml(j.error || "tente novamente mais tarde")}</div>`);
                abrirModal();
                return;
            }

            const data = await res.json();

            // Atualiza o status publico para acompanhar a nova cobranca
            renderStatusPublicoNaTela("AGUARDANDO_PAGAMENTO", tracking.tipo_entrega);

            // Atualiza tracking com os novos dados financeiros
            tracking.status = String(data.status || "AGUARDANDO_PAGAMENTO").toUpperCase();
            tracking.pagamento_online = Boolean(data.pagamento_online);
            tracking.pagamento = data.pagamento || null;
            tracking.estado_pagamento = data.estado_pagamento || null;
            tracking.pode_retentar = Boolean(data.pode_retentar);
            tracking.payment_window_expires_at = data.payment_window_expires_at || null;
            tracking.total = Number(data.total) || tracking.total;
            saveTrackingPedido(tracking);

            renderPagamentoNaTela(data);
        } catch (e) {
            setModal("Pagamento", `<div><strong>Erro de conex&atilde;o.</strong></div><div class="muted">N&atilde;o foi poss&iacute;vel gerar o novo QR Code.</div>`);
            abrirModal();
        }
    }

    function copiarPix() {
        const el = document.getElementById("pixPayload");
        if (!el || !el.value) return;

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(el.value).then(() => {
                const original = el.value;
                el.value = "Codigo copiado!";
                setTimeout(() => { el.value = original; }, 1200);
            }).catch(() => {
                _copiarPixFallback(el);
            });
        } else {
            _copiarPixFallback(el);
        }
    }

    function _copiarPixFallback(el) {
        try {
            el.select();
            el.setSelectionRange(0, el.value.length);
            document.execCommand("copy");
            const original = el.value;
            el.value = "Codigo copiado!";
            setTimeout(() => { el.value = original; }, 1200);
        } catch {
        }
    }

    async function refreshStatusPublicoNaTela() {
        const tracking = getTrackingPedido();
        if (!tracking || !tracking.id || !tracking.access_token) return;

        const kind = String(tracking.kind || "").toUpperCase();
        if (kind !== "DELIVERY") return;

        try {
            const url = `/api/public/pedidos/${encodeURIComponent(tracking.id)}/status?token=${encodeURIComponent(tracking.access_token)}`;
            const res = await fetch(url, { cache: "no-store" });
            if (!res.ok) return;

            const data = await res.json();
            const statusPublico = data.status_publico;
            const finalizado = data.finalizado;
            const tipoEntrega = data.tipo_entrega;

            // Mescla dados novos no tracking para ter estado de pagamento atualizado
            tracking.status = String(data.status || tracking.status || "").toUpperCase();
            tracking.pagamento_online = Boolean(data.pagamento_online !== undefined ? data.pagamento_online : tracking.pagamento_online);
            tracking.pagamento = data.pagamento || tracking.pagamento || null;
            tracking.estado_pagamento = data.estado_pagamento || tracking.estado_pagamento || null;
            tracking.pode_retentar = Boolean(data.pode_retentar !== undefined ? data.pode_retentar : tracking.pode_retentar);
            tracking.payment_window_expires_at = data.payment_window_expires_at || tracking.payment_window_expires_at || null;
            tracking.total = Number(data.total) || tracking.total || 0;
            saveTrackingPedido(tracking);

            renderStatusPublicoNaTela(statusPublico, tipoEntrega);
            renderPagamentoNaTela(data);

            if (finalizado === true) {
                stopStatusPublicoPolling();
                clearTrackingPedido();
            }
        } catch (e) {
        }
    }

    function startStatusPublicoPolling() {
        if (state.statusPublicoTimer) {
            clearInterval(state.statusPublicoTimer);
        }
        state.statusPublicoTimer = setInterval(async () => {
            await refreshStatusPublicoNaTela();
        }, 2500);
    }

    function stopStatusPublicoPolling() {
        if (state.statusPublicoTimer) {
            clearInterval(state.statusPublicoTimer);
            state.statusPublicoTimer = null;
        }
    }

    async function pollKdsStatus(solicitacaoId, mesa, token) {
        try {
            const url = `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`;
            const res = await fetch(url);
            if (res.ok) {
                const data = await res.json();
                const status = data.status;
                const statusText = document.getElementById("kdsStatusText");
                if (statusText) {
                    if (status === "AGUARDANDO") {
                        statusText.textContent = "Pedido recebido";
                    } else if (status === "EM_PREPARO") {
                        statusText.textContent = "Seu pedido está sendo preparado";
                    } else if (status === "PRONTO") {
                        statusText.textContent = "Seu pedido está pronto";
                        stopKdsPolling();
                    }
                }
            }
        } catch (err) {
            console.error("Erro ao consultar status KDS:", err);
        }
    }

    function startKdsPolling(solicitacaoId, mesa, token) {
        if (state.kdsPollingSid === String(solicitacaoId)) {
            return;
        }
        if (state.kdsPollingTimer) {
            clearInterval(state.kdsPollingTimer);
        }
        state.kdsPollingSid = String(solicitacaoId);
        state.kdsPollingTimer = setInterval(async () => {
            await pollKdsStatus(solicitacaoId, mesa, token);
        }, 2500);
        pollKdsStatus(solicitacaoId, mesa, token);
    }

    function stopKdsPolling() {
        if (state.kdsPollingTimer) {
            clearInterval(state.kdsPollingTimer);
            state.kdsPollingTimer = null;
        }
        state.kdsPollingSid = null;
    }

    let _deliveryLeafletMap = null;
    let _deliveryLeafletMarker = null;

    function _parseLatLngFromMapsUrl(raw) {
        const s = String(raw || "").trim();
        if (!s) return null;
        const m1 = s.match(/\bq=\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/i);
        if (m1) return { lat: Number(m1[1]), lng: Number(m1[2]) };
        const m2 = s.match(/@\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/i);
        if (m2) return { lat: Number(m2[1]), lng: Number(m2[2]) };
        const m3 = s.match(/\b(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\b/);
        if (m3) return { lat: Number(m3[1]), lng: Number(m3[2]) };
        return null;
    }

    function _setDeliveryFromLatLng(lat, lng) {
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
        const url = `https://www.google.com/maps?q=${lat},${lng}`;
        setDeliveryMapsUrl(url);
    }

    function ensureDeliveryMapInModal() {
        try {
            if (!isModalOpen()) return;
            const title = String(document.getElementById("modalTitle")?.innerText || "");
            if (title !== "Carrinho / Pedido") return;

            const el = document.getElementById("deliveryMap");
            if (!el) return;
            if (typeof L === "undefined") {
                try {
                    el.innerHTML = `<div class="muted" style="padding:10px">Mapa indisponível neste dispositivo.</div>`;
                } catch {
                }
                return;
            }

            try {
                if (_deliveryLeafletMap && _deliveryLeafletMap._container && _deliveryLeafletMap._container !== el) {
                    try { _deliveryLeafletMap.remove(); } catch {}
                    _deliveryLeafletMap = null;
                    _deliveryLeafletMarker = null;
                }
            } catch {
            }

            const cur = _parseLatLngFromMapsUrl(state.deliveryMaps);
            const center = cur && Number.isFinite(cur.lat) && Number.isFinite(cur.lng)
                ? [cur.lat, cur.lng]
                : [-23.55052, -46.633308];

            if (!_deliveryLeafletMap) {
                _deliveryLeafletMap = L.map(el, { zoomControl: true, attributionControl: false }).setView(center, cur ? 17 : 12);
                L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(_deliveryLeafletMap);

                _deliveryLeafletMarker = L.marker(center, { draggable: true }).addTo(_deliveryLeafletMap);
                _deliveryLeafletMarker.on("dragend", () => {
                    try {
                        const p = _deliveryLeafletMarker.getLatLng();
                        _setDeliveryFromLatLng(Number(p.lat), Number(p.lng));
                    } catch {
                    }
                });
            } else {
                _deliveryLeafletMap.setView(center, cur ? 17 : _deliveryLeafletMap.getZoom());
                if (_deliveryLeafletMarker) {
                    try { _deliveryLeafletMarker.setLatLng(center); } catch {}
                }
            }

            try { _deliveryLeafletMap.invalidateSize(); } catch {}
        } catch {
        }
    }

    function voltarAoCardapio() {
        stopStatusPublicoPolling();
        showMainScreen();
    }

    async function refreshSolicitacao() {
        const pedido = getPedidoAtual();
        if (!pedido || !pedido.id) return;

        const kind = String(pedido.kind || "").toUpperCase();
        if (kind !== "DELIVERY") {
            if (!state.mesa || !state.token) return;
        }

        try {
            const url = (kind === "DELIVERY")
                ? `/api/public/pedidos/${encodeURIComponent(pedido.id)}?token=${encodeURIComponent(String(pedido.access_token || ""))}`
                : `/api/solicitacoes/${encodeURIComponent(pedido.id)}?mesa=${encodeURIComponent(state.mesa)}&token=${encodeURIComponent(state.token)}`;
            const res = await fetch(url, { cache: "no-store" });
            if (!res.ok) {
                // Se o pedido não existe mais (ou token inválido), limpa o estado local
                if (res.status === 404 || res.status === 401 || res.status === 403) {
                    clearPedidoAtual();
                    const backdrop = document.getElementById("modalBackdrop");
                    if (backdrop && backdrop.style.display === "flex") {
                        abrirCarrinho();
                    }
                }
                return;
            }
            const s = await res.json();
            pedido.status = s.status || pedido.status;
            pedido.pdv_id = s.pdv_id || pedido.pdv_id || null;
            pedido.sale_id = s.sale_id || pedido.sale_id || null;
            if (s.total_estimado !== undefined) pedido.total_estimado = s.total_estimado;
            pedido.atualizadoEm = new Date().toISOString();
            pedido.resposta = s.resposta || null;
            pedido.comprovante = s.comprovante || null;
            pedido.pdv_status = s.pdv_status || null;
            pedido.pdv_status_em = s.pdv_status_em || null;
            savePedidoAtual(pedido);

            const pdvStatus = String(pedido.pdv_status || "").toUpperCase();
            if (pdvStatus === "FINALIZADA") {
                clearPedidoAtual();
                if (isModalOpen()) {
                    setModal(
                        "Pedido encerrado",
                        `<div><strong>Seu pedido foi finalizado no PDV.</strong></div>`
                        + `<div class="muted" style="margin-top:8px">Você já pode fazer um novo pedido.</div>`
                        + `<div style="margin-top:14px"><button onclick="fecharModal()">OK</button></div>`
                    );
                    abrirModal();
                }
                return;
            }

            if (isModalOpen()) {
                // Evita re-render enquanto o cliente está escolhendo a forma de pagamento
                // (o select pode "fechar sozinho" se o modal for recriado pelo refresh)
                if (Date.now() < (state.modalLockUntil || 0)) return;
                const title = String(document.getElementById("modalTitle")?.innerText || "");
                if (title === "Carrinho / Pedido") {
                    if (!state.postOrderActive) {
                        abrirCarrinho();
                    }
                }
            }
        } catch {
        }
    }

    function atualizarStatusPedido(novoStatus) {
    }

    function abrirCarrinho(skipFeeRefresh) {
        // Se o modal já está aberto, preservar a seleção atual antes de recriar o HTML
        // (evita voltar para o primeiro option em alguns navegadores/mobile)
        if (isModalOpen()) {
            capturePayMethodFromDom();
        }

        const isSalao = Boolean(state.mesa && state.token);

        const pedido = getPedidoAtual();
        const subtotal = getCartTotal();
        const fee = (!isSalao && String(state.deliveryType || "").toUpperCase() === "DELIVERY")
            ? Number(state.deliveryFeePreview)
            : NaN;
        const hasFee = Number.isFinite(fee) && fee >= 0;
        const total = hasFee ? (subtotal + fee) : subtotal;

        if (!skipFeeRefresh) {
            refreshDeliveryFeePreview();
        }

        const cartHtml = state.carrinho.length === 0
            ? `<div class="muted">Carrinho vazio.</div>`
            : state.carrinho.map(it => `
                <div class="cart-row">
                    <div>
                        <div><strong>${it.nome}</strong></div>
                        <div class="muted">${formatBRL(it.preco)} cada</div>
                    </div>
                    <div class="qty">
                        <button onclick="alterarQtd('${it.produtoId}', -1)">-</button>
                        <strong>${it.qtd}</strong>
                        <button onclick="alterarQtd('${it.produtoId}', 1)">+</button>
                    </div>
                    <div><strong>${formatBRL(it.preco * it.qtd)}</strong></div>
                </div>
            `).join("");

        const respostaHtml = pedido && pedido.resposta
            ? (() => {
                if (pedido.resposta.tipo === "IR_CAIXA") {
                    return `<div style="margin-top:10px"><strong>Resposta:</strong> Dirija-se ao caixa para realizar o PAGAMENTO.</div>`;
                }
                if (pedido.resposta.tipo === "ENVIAR_PIX") {
                    const chave = pedido.resposta.pix && pedido.resposta.pix.chave ? pedido.resposta.pix.chave : "";
                    return `<div style="margin-top:10px"><strong>Resposta:</strong> PIX</div><div class="muted">Chave: ${chave || "(não informada)"}</div>`;
                }
                if (pedido.resposta.tipo === "PAGAR_NA_ENTREGA") {
                    const msg = String(pedido.resposta.mensagem || "Aguarde, um atentende vai te chamar no WhatsApp");
                    return `<div style="margin-top:10px"><strong>Resposta:</strong> ${escapeHtml(msg)}</div>`;
                }
                if (pedido.resposta.tipo === "PAGAMENTO_CONFIRMADO") {
                    return `<div style="margin-top:10px"><strong>Pagamento confirmado.</strong></div><div class="muted">Seu pedido está a caminho.</div>`;
                }
                return "";
            })()
            : "";

        const comprovanteUi = isSalao && pedido && pedido.resposta && pedido.resposta.tipo === "ENVIAR_PIX"
            ? (pedido.comprovante
                ? `<div style="margin-top:12px" class="muted">Comprovante enviado.</div>`
                : `
                    <div style="margin-top:12px">
                        <div class="muted" style="margin-bottom:6px">Enviar comprovante (PRINT do app do banco ou PDF):</div>
                        <div class="muted" style="margin-bottom:10px">Preferência: PRINT. Abra o comprovante no app do banco, faça um print (captura de tela) e selecione o print aqui. Alternativa: enviar PDF.</div>
                        <input id="comprovanteFile" type="file" accept="image/*,application/pdf" style="width:100%" />
                        <div style="margin-top:10px"><button class="btn-comprovante" onclick="uploadComprovante()">Enviar comprovante</button></div>
                    </div>
                  `)
            : "";

        const pedidoPay = "";

        const whatsappUi = isSalao
            ? `
                <div style="margin-top:14px">
                    <div class="muted" style="margin-bottom:6px">Cadastre seu WhatsApp para receber nossas promoções.</div>
                    <input id="clientWhatsapp" value="${String(state.clientWhatsapp || "").replace(/"/g, "&quot;")}" onfocus="lockModalRender(6000)" onclick="lockModalRender(6000)" oninput="onClientWhatsappChange(this.value)" placeholder="(99) 99999-9999" style="display:block; width:100%; box-sizing:border-box; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35)" />
                </div>
              `
            : `
                <div style="margin-top:14px">
                    <div class="muted" style="margin-bottom:6px">WhatsApp do cliente (obrigatório):</div>
                    <input id="clientWhatsapp" value="${String(state.clientWhatsapp || "").replace(/"/g, "&quot;")}" onfocus="lockModalRender(6000)" onclick="lockModalRender(6000)" oninput="onClientWhatsappChange(this.value)" placeholder="(99) 99999-9999" style="display:block; width:100%; box-sizing:border-box; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35)" />
                </div>
              `;

        const deliveryUi = isSalao ? "" : (
            `${whatsappUi}

            <div style="margin-top:14px">
                <div class="muted" style="margin-bottom:6px">Entrega:</div>
                <select id="deliveryType" onclick="lockModalRender(6000)" onfocus="lockModalRender(6000)" onchange="onDeliveryTypeChange(this.value)" style="width:100%; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35)">
                    <option value="DELIVERY" ${String(state.deliveryType||"").toUpperCase()==="DELIVERY" ? "selected" : ""}>Delivery</option>
                    <option value="RETIRADA" ${String(state.deliveryType||"").toUpperCase()==="RETIRADA" ? "selected" : ""}>Retirada</option>
                </select>
            </div>

            <div style="margin-top:14px">
                <div class="muted" style="margin-bottom:6px">Localização (Google Maps) ${String(state.deliveryType||"").toUpperCase()==="DELIVERY" ? "(obrigatório)" : "(opcional)"}:</div>
                <div style="margin-top:10px">
                    <div id="deliveryMap" style="width:100%; height:240px; border-radius:12px; overflow:hidden; border:1px solid rgba(10, 92, 47, 0.18); background: rgba(10, 92, 47, 0.06); display:flex; align-items:center; justify-content:center;">
                        <div class="muted" style="padding:10px; text-align:center">Carregando mapa...</div>
                    </div>
                </div>
                <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap">
                    <button type="button" onclick="usarMinhaLocalizacao()">Usar minha localização</button>
                </div>
                <div class="muted" style="margin-top:8px">Você pode ajustar o pino arrastando no mapa.</div>
            </div>

            <div style="margin-top:14px">
                <div class="muted" style="margin-bottom:6px">Referência do local (opcional):</div>
                <input id="deliveryRef" value="${String(state.deliveryRef || "").replace(/"/g, "&quot;")}" onfocus="lockModalRender(6000)" onclick="lockModalRender(6000)" oninput="onDeliveryFieldChange('deliveryRef', this.value)" placeholder="Ex.: perto do mercado, portão azul" style="display:block; width:100%; box-sizing:border-box; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35)" />
            </div>

            <div style="margin-top:14px">
                <div class="muted" style="margin-bottom:6px">Observações (opcional):</div>
                <textarea id="deliveryObs" onfocus="lockModalRender(6000)" onclick="lockModalRender(6000)" oninput="onDeliveryFieldChange('deliveryObs', this.value)" placeholder="Ex.: sem cebola, troco, instruções para entrega" style="display:block; width:100%; box-sizing:border-box; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35); min-height: 86px; resize: vertical">${escapeHtml(String(state.deliveryObs || ""))}</textarea>
            </div>`
        );

        const trocoUi = (!isSalao && normalizePayMethod(state.payMethod) === "DINHEIRO")
            ? `<div style="margin-top:14px">
                    <div class="muted" style="margin-bottom:6px">Troco para (opcional):</div>
                    <input value="${String(state.deliveryTroco||"").replace(/"/g, "&quot;")}" onfocus="lockModalRender(6000)" onclick="lockModalRender(6000)" oninput="onDeliveryFieldChange('deliveryTroco', this.value)" placeholder="Ex.: 100" style="display:block; width:100%; box-sizing:border-box; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35)" />
               </div>`
            : "";

        const paymentUi = `
                <div style="margin-top:14px">
                    <div class="muted" style="margin-bottom:6px">Nome do cliente (${isSalao ? "opcional" : "obrigatório"}):</div>
                    <input id="clientName" value="${String(state.clientName || "").replace(/"/g, "&quot;")}" onfocus="lockModalRender(6000)" onclick="lockModalRender(6000)" oninput="onClientNameChange(this.value)" style="display:block; width:100%; box-sizing:border-box; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35)" />
                </div>

                ${isSalao ? whatsappUi : ""}

                ${deliveryUi}

                <div style="margin-top:14px">
                    <div class="muted" style="margin-bottom:6px">Forma de pagamento (preferência):</div>
                    <select id="payMethod" onclick="lockModalRender(6000)" onfocus="lockModalRender(6000)" onchange="onPayMethodChange(this.value)" style="width:100%; padding:10px; border-radius:12px; border:1px solid rgba(10, 92, 47, 0.35)">
                        ${PAYMENT_METHODS.map((m) => `<option value="${m.code}" ${normalizePayMethod(state.payMethod) === m.code ? "selected" : ""}>${m.label}</option>`).join("")}
                    </select>
                </div>

                ${trocoUi}
              `;

        const actions = `
            <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:16px">
                ${state.carrinho.length > 0
                    ? `<button id="sendOrderBtn" onclick="enviarPedido()" ${state.sending ? "disabled" : ""}>${state.sending ? "Enviando..." : "Enviar pedido"}</button>
                       <button onclick="limparCarrinho()">Limpar</button>`
                    : ""}
            </div>
            ${state.carrinho.length > 0
                ? (() => {
                    if (isSalao) {
                        return `<div style="margin-top:10px; font-size:18px"><strong>Total do carrinho:</strong> ${formatBRL(total)}</div>`;
                    }

                    const tipo = String(state.deliveryType || "DELIVERY").toUpperCase();
                    if (tipo !== "DELIVERY") {
                        return `<div style="margin-top:10px; font-size:18px"><strong>Total:</strong> ${formatBRL(subtotal)}</div>`;
                    }

                    const feeLine = (() => {
                        if (state.deliveryFeeLoading) {
                            return `<div style="margin-top:6px" class="muted"><strong>Taxa de entrega:</strong> calculando...</div>`;
                        }
                        if (hasFee) {
                            const d = Number(state.deliveryFeeDistanceKm);
                            const dist = Number.isFinite(d) ? ` (${d.toFixed(2)} km)` : "";
                            return `<div style="margin-top:6px"><strong>Taxa de entrega:</strong> ${formatBRL(fee)}${dist}</div>`;
                        }
                        if (state.deliveryFeeEnabled === false) {
                            return `<div style="margin-top:6px" class="muted"><strong>Taxa de entrega:</strong> não aplicada</div>`;
                        }
                        if (state.deliveryFeeError) {
                            return `<div style="margin-top:6px" class="muted"><strong>Taxa de entrega:</strong> indisponível</div>`;
                        }
                        return `<div style="margin-top:6px" class="muted"><strong>Taxa de entrega:</strong> a calcular</div>`;
                    })();

                    return `
                        <div style="margin-top:10px; font-size:18px"><strong>Subtotal:</strong> ${formatBRL(subtotal)}</div>
                        ${feeLine}
                        <div style="margin-top:6px; font-size:18px"><strong>Total:</strong> ${formatBRL(total)}</div>
                    `;
                })()
                : ""}
        `;

        setModal("Carrinho / Pedido", cartHtml + paymentUi + actions);
        applyModalStatus(pedido ? pedido.status : null);
        abrirModal();

        try {
            updateNextStepHints();
            setTimeout(() => updateNextStepHints(), 0);
        } catch {
        }

        try {
            setTimeout(() => ensureDeliveryMapInModal(), 120);
            setTimeout(() => ensureDeliveryMapInModal(), 700);
        } catch {
        }

        // Após recriar o HTML, forçar o value do select para refletir o estado persistido
        try {
            const pm = document.getElementById("payMethod");
            if (pm) pm.value = normalizePayMethod(state.payMethod);
        } catch {
        }
    }

    function filtrarProdutos() {
        state.busca = document.getElementById("search").value.toLowerCase();
        render();
    }

    function produtoVisivel(p) {
        if (!p.ativo) return false;
        const nome = (p.nome || "").toLowerCase();
        const desc = getProdutoDescricao(p).toLowerCase();
        const matchBusca = !state.busca || nome.includes(state.busca) || desc.includes(state.busca);
        const matchCat = state.categoriaId === "__todas__" || p.categoriaId === state.categoriaId;
        return matchBusca && matchCat;
    }

    function renderQueridinhos() {
        const container = document.getElementById("queridinhos");
        if (!container) return;
        const queridinhos = (state.data.produtos || [])
            .filter(p => p.ativo && p.queridinho)
            .slice(0, 6);

        container.innerHTML = queridinhos.map(p => `
            <div class="card">
                <img src="${p.imagem}" alt="${escapeHtml(p.nome || "")}" onclick="openProductDetails('${p.id}')">
                <p class="card-title">${escapeHtml(p.nome || "")}</p>
                <div class="product-price" style="margin-top:8px">${formatBRL(p.preco)}</div>
                <button type="button" class="price-btn" aria-disabled="${!p.ativo}" onclick="openProductDetails('${p.id}')">Comprar Agora</button>
            </div>
        `).join("");
    }

    function renderLista() {
        const lista = document.getElementById("listaProdutos");
        if (!lista) return;
        const renderProduto = (p) => `
            <div class="product" data-nome="${(p.nome || "").toLowerCase()}">
                <img src="${p.imagem}" alt="${escapeHtml(p.nome || "")}" onclick="openProductDetails('${p.id}')">
                <div class="product-info">
                    <div class="product-title">${escapeHtml(p.nome || "")}</div>
                    <div class="product-price">${formatBRL(p.preco)}</div>
                </div>
                <div class="product-actions">
                    <button type="button" class="add-btn" aria-disabled="${!p.ativo}" onclick="openProductDetails('${p.id}')"><span>Comprar Agora</span></button>
                </div>
            </div>
        `;

        const produtosAll = (state.data.produtos || []).filter(p => {
            if (!p.ativo) return false;
            const nome = (p.nome || "").toLowerCase();
            const desc = getProdutoDescricao(p).toLowerCase();
            const matchBusca = !state.busca || nome.includes(state.busca) || desc.includes(state.busca);
            return matchBusca;
        });

        if (state.categoriaId !== "__todas__") {
            const produtos = produtosAll.filter(p => p.categoriaId === state.categoriaId);
            if (produtos.length === 0) {
                lista.innerHTML = `<div class="product"><div class="product-info"><strong>Nenhum produto encontrado.</strong><div class="muted">Tente ajustar a busca ou a categoria.</div></div></div>`;
                return;
            }
            lista.innerHTML = produtos.map(renderProduto).join("");
            return;
        }

        if (produtosAll.length === 0) {
            lista.innerHTML = `<div class="product"><div class="product-info"><strong>Nenhum produto encontrado.</strong><div class="muted">Tente ajustar a busca ou a categoria.</div></div></div>`;
            return;
        }

        const cats = Array.isArray(state.data?.categorias) ? state.data.categorias : [];
        const byCat = new Map();
        for (const p of produtosAll) {
            const cid = String(p.categoriaId || "");
            if (!byCat.has(cid)) byCat.set(cid, []);
            byCat.get(cid).push(p);
        }

        const seen = new Set();
        const chunks = [];
        for (const c of cats) {
            const cid = String(c?.id || "");
            const items = byCat.get(cid) || [];
            if (!cid || items.length === 0) continue;
            seen.add(cid);
            chunks.push(`<div class="section-title">${escapeHtml(humanCategoryName(String(c.nome || "")))}</div>`);
            chunks.push(items.map(renderProduto).join("") );
        }

        const leftovers = [];
        for (const [cid, items] of byCat.entries()) {
            if (!cid || seen.has(cid)) continue;
            leftovers.push(...items);
        }
        if (leftovers.length > 0) {
            chunks.push(`<div class="section-title">Produtos</div>`);
            chunks.push(leftovers.map(renderProduto).join("") );
        }

        lista.innerHTML = chunks.join("");
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function getProdutoDescricao(p) {
        if (!p) return "";
        const candidates = [
            p.descricao,
            p.descrição,
            p.description,
            p.desc,
            p.obs,
            p.observacoes,
            p.observações
        ];
        for (const v of candidates) {
            const s = String(v || "");
            if (s.trim()) return s;
        }
        return "";
    }

    function abrirDescricaoProdutoEncoded(produtoId, nomeEnc, descEnc, precoRaw) {
        // Compatibilidade: versões antigas chamavam uma tela simples de descrição.
        // Agora a descrição é a tela de detalhes.
        openProductDetails(String(produtoId || "").trim());
    }

    function getProdutoById(produtoId) {
        const pid = String(produtoId || "").trim();
        if (!pid) return null;
        const produtos = Array.isArray(state.data?.produtos) ? state.data.produtos : [];
        return produtos.find(x => String(x?.id || "") === pid) || null;
    }

    function getCarrinhoQtd(produtoId) {
        const pid = String(produtoId || "").trim();
        if (!pid) return 0;
        const idx = state.carrinho.findIndex(x => String(x.produtoId) === pid);
        if (idx < 0) return 0;
        const q = Number(state.carrinho[idx].qtd || 0);
        return Number.isFinite(q) ? q : 0;
    }

    function openProductDetails(produtoId) {
        const p = getProdutoById(produtoId);
        if (!p) return;
        setModalCloseLabel("Voltar");

        const pid = String(p.id || "");
        const nome = escapeHtml(String(p.nome || pid));
        const rawDesc = String(getProdutoDescricao(p) || "").trim();
        const desc = rawDesc ? escapeHtml(rawDesc.replace(/\\n/g, "\n")) : "";
        const preco = Number(p.preco || 0);
        const img = String(p.imagem || "").trim();
        const qtd = getCarrinhoQtd(pid);

        const body = `
            <div style="display:flex; flex-direction:column; gap:12px">
                ${img ? `<div style="display:flex; justify-content:center"><img class="detail-img" src="${img}" alt="${nome}"></div>` : ""}
                <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap">
                    <div style="font-weight:900; font-size:18px; color: var(--verde)">${nome}</div>
                    <div class="product-price" style="margin-top:0; font-size:18px">${formatBRL(preco)}</div>
                </div>
                ${desc ? `<div style="white-space: pre-wrap; line-height: 1.35">${desc}</div>` : `<div class="muted">Sem descrição.</div>`}

                <div class="detail-actions">
                    <div class="detail-qty">
                        <button type="button" onclick="detailQtyDelta('${pid}', -1)">-</button>
                        <div class="detail-qty-value" id="detailQtyValue">${qtd}</div>
                        <button type="button" onclick="detailQtyDelta('${pid}', 1)">+</button>
                    </div>
                    <button type="button" class="detail-add-btn" onclick="detailAddToPedido('${pid}')">Adicionar</button>
                </div>
            </div>
        `;
        setModal("Produto", body);
        abrirModal();
    }

    function detailQtyDelta(produtoId, delta) {
        const pid = String(produtoId || "").trim();
        if (!pid) return;
        const cur = getCarrinhoQtd(pid);
        let next = cur + Number(delta || 0);
        if (!Number.isFinite(next)) next = cur;
        if (next < 0) next = 0;
        setCarrinhoQtd(pid, next);
        try {
            const el = document.getElementById("detailQtyValue");
            if (el) el.textContent = String(next);
        } catch {
        }
    }

    function detailAddToPedido(produtoId) {
        const pid = String(produtoId || "").trim();
        if (!pid) return;
        const cur = getCarrinhoQtd(pid);
        if (cur <= 0) {
            detailQtyDelta(pid, 1);
        }
        fecharModal();
    }

    function render() {
        if (!state.data) return;
        setModalCloseLabel(state.modalCloseLabel || "Fechar");
        const cats = state.data?.categorias || [];
        if (state.categoriaId !== "__todas__" && !cats.some(c => c.id === state.categoriaId)) {
            state.categoriaId = "__todas__";
        }
        renderCategoriasRow();
        renderQueridinhos();
        renderLista();
    }

    function aplicarUI() {
        const logo = state.data?.ui?.logo;
        const whatsapp = state.data?.ui?.whatsapp;
        const logoImg = document.getElementById("logoImg");
        const brandText = document.getElementById("brandText");
        const whatsBtn = document.getElementById("whatsBtn");
        const whatsFloat = document.getElementById("whatsFloat");
        const whatsFooter = document.getElementById("whatsFooter");

        function normalizeAssetUrl(v) {
            const s = String(v || "").trim();
            if (!s) return "";
            const low = s.toLowerCase();
            if (low.startsWith("http://") || low.startsWith("https://")) return s;
            if (s.startsWith("/assets/")) return s;
            if (s.startsWith("assets/")) return "/" + s;
            if (s.startsWith("/")) return s;
            return "/assets/" + s;
        }

        if (logo) {
            logoImg.src = normalizeAssetUrl(logo);
            logoImg.style.display = "block";
            logoImg.onerror = () => {
                logoImg.style.display = "none";
            };
            brandText.style.display = "none";
        } else {
            logoImg.style.display = "none";
            brandText.style.display = "block";
        }

        try {
            const raw = String(whatsapp || "").trim();
            const digits = raw.replace(/\D+/g, "");
            if (digits.length >= 12) {
                const msg = encodeURIComponent("Olá! Vim pelo cardápio online.");
                const url = `https://wa.me/${digits}?text=${msg}`;
                if (whatsBtn) {
                    whatsBtn.href = url;
                    whatsBtn.style.display = "none";
                }
                if (whatsFloat) {
                    whatsFloat.href = url;
                    whatsFloat.style.display = "none";
                }
                if (whatsFooter) {
                    whatsFooter.href = url;
                    whatsFooter.style.display = "inline-flex";
                }
            } else {
                if (whatsBtn) whatsBtn.style.display = "none";
                if (whatsFloat) whatsFloat.style.display = "none";
                if (whatsFooter) whatsFooter.style.display = "none";
            }
        } catch {
            if (whatsBtn) whatsBtn.style.display = "none";
            if (whatsFloat) whatsFloat.style.display = "none";
            if (whatsFooter) whatsFooter.style.display = "none";
        }
    }

    function iniciarBanner() {
        const imagens = state.data?.ui?.banner?.imagens || [];
        const intervaloMs = state.data?.ui?.banner?.intervaloMs || 3500;
        const bannerImg = document.getElementById("bannerImg");
        const bannerFallback = document.getElementById("bannerFallback");

        function normalizeAssetUrl(v) {
            const s = String(v || "").trim();
            if (!s) return "";
            const low = s.toLowerCase();
            if (low.startsWith("http://") || low.startsWith("https://")) return s;
            if (s.startsWith("/assets/")) return s;
            if (s.startsWith("assets/")) return "/" + s;
            if (s.startsWith("/")) return s;
            return "/assets/" + s;
        }

        if (!Array.isArray(imagens) || imagens.length === 0) {
            bannerImg.style.display = "none";
            bannerFallback.style.display = "block";
            return;
        }

        const normalized = imagens.map(normalizeAssetUrl).filter(Boolean);
        if (normalized.length === 0) {
            bannerImg.style.display = "none";
            bannerFallback.style.display = "block";
            return;
        }

        // Evita reiniciar o banner a cada refresh se nada mudou
        const sig = `${intervaloMs}|${normalized.join("|")}`;
        if (state.bannerSig === sig && state.bannerTimer) {
            return;
        }
        state.bannerSig = sig;

        function setBannerAt(i) {
            const src = normalized[i % normalized.length];
            bannerImg.onerror = () => {
                // tenta próxima imagem; se todas falharem, mostra fallback
                let tries = 0;
                let j = (i + 1) % normalized.length;
                while (tries < normalized.length) {
                    const nextSrc = normalized[j % normalized.length];
                    if (nextSrc && nextSrc !== bannerImg.src) {
                        bannerImg.src = nextSrc;
                        return;
                    }
                    tries += 1;
                    j = (j + 1) % normalized.length;
                }
                bannerImg.style.display = "none";
                bannerFallback.style.display = "block";
            };
            bannerImg.src = src;
            bannerImg.style.display = "block";
            bannerFallback.style.display = "none";
        }

        if (state.bannerTimer) {
            clearInterval(state.bannerTimer);
            state.bannerTimer = null;
        }

        state.bannerIndex = 0;
        setBannerAt(state.bannerIndex);
        state.bannerTimer = setInterval(() => {
            state.bannerIndex = (state.bannerIndex + 1) % normalized.length;
            setBannerAt(state.bannerIndex);
        }, intervaloMs);
    }

    async function carregarDados() {
        const res = await fetch("/api/data", { cache: "no-store" });
        const status = res.status;
        const ct = String(res.headers.get("content-type") || "");
        let bodyText = "";
        try {
            bodyText = await res.text();
        } catch {
            bodyText = "";
        }

        if (!res.ok) {
            const msg = (bodyText || "").slice(0, 500);
            throw new Error(`api_data_http_${status}: ${msg}`);
        }

        if (ct.includes("application/json")) {
            try {
                return JSON.parse(bodyText || "{}");
            } catch {
                throw new Error("api_data_json_parse_error");
            }
        }

        // fallback
        try {
            return JSON.parse(bodyText || "{}");
        } catch {
            throw new Error("api_data_not_json");
        }
    }

    async function refreshCatalogo() {
        try {
            const novo = await carregarDados();
            state.data = novo;
            aplicarUI();
            iniciarBanner();
            aplicarHorarioFuncionamento();
            render();

            if (state.postOrderActive) {
                showPostOrderScreen();
            }
        } catch {
        }
    }

    async function init() {
        const params = new URLSearchParams(window.location.search);
        state.admin = params.get("admin") === "1";
        document.getElementById("adminHint").style.display = state.admin ? "block" : "none";

        const mtUrl = getMesaTokenFromUrl();
        const mtLocal = getMesaTokenFromLocal();
        const mt = (mtUrl && mtUrl.mesa && mtUrl.token) ? mtUrl : mtLocal;
        state.mesa = mt.mesa;
        state.token = mt.token;
        if (mtUrl && mtUrl.mesa && mtUrl.token) {
            saveMesaTokenToLocal(mtUrl.mesa, mtUrl.token);
            clearMesaTokenFromUrl();
        }

        loadLocal();
        updateCartBadge();

        try {
            state.data = await carregarDados();
            aplicarUI();
            iniciarBanner();
            aplicarHorarioFuncionamento();
            render();

            const trackingSalvo = getTrackingPedido();
            showMainScreen();

            if (
                trackingSalvo
                && String(trackingSalvo.kind || "").toUpperCase() === "SALAO"
                && trackingSalvo.id
                && String(trackingSalvo.mesa || "") === String(state.mesa || "")
                && String(trackingSalvo.token || "") === String(state.token || "")
            ) {
                saveTrackingPedido(trackingSalvo);
                showPostOrderScreen(trackingSalvo);
            }

            if (state.solicitacaoTimer) {
                clearInterval(state.solicitacaoTimer);
                state.solicitacaoTimer = null;
            }
            state.solicitacaoTimer = setInterval(async () => {
                await refreshSolicitacao();
            }, 2500);

            if (state.refreshTimer) {
                clearInterval(state.refreshTimer);
                state.refreshTimer = null;
            }
            state.refreshTimer = setInterval(refreshCatalogo, 5000);

            if (state.horarioTimer) {
                clearInterval(state.horarioTimer);
                state.horarioTimer = null;
            }
            state.horarioTimer = setInterval(aplicarHorarioFuncionamento, 30000);
        } catch (e) {
            try { console.error(e); } catch {}
            const msg = (e && e.message) ? String(e.message) : String(e || "erro");
            setModal(
                "Erro ao carregar produtos",
                `<div><strong>Não foi possível carregar os dados do cardápio.</strong></div>`
                + `<div class="muted" style="margin-top:10px">Detalhe: ${escapeHtml(msg)}</div>`
            );
            abrirModal();
        }
    }

    window.addEventListener("keydown", (e) => {
        if (e.key === "Escape") fecharModal();
    });

    init();
