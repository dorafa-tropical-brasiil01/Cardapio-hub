# RELATÓRIO DE AUDITORIA ESTÁTICA — FLUXO DE STATUS PÚBLICO DO PEDIDO / KDS

**Projeto**: DoRafaPDV — Cardápio Online  
**Data**: 2026-07-31  
**Tipo**: Auditoria Estática de Código  
**Objetivo**: Identificar a causa da ausência de chamadas ao endpoint `/api/solicitacoes/<id>/kds-status` pelo frontend após envio de pedido

---

## 1. ARQUIVOS ANALISADOS

| Arquivo | Caminho | Propósito |
|---------|---------|-----------|
| index.html | `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\index.html` | Frontend principal (HTML + JavaScript inline) |
| app.js | `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\assets\app.js` | JavaScript externo do frontend |
| routes.py | `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\cardapio_app\routes.py` | Rotas da API do backend |
| pg_store.py | `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\pg_store.py` | Camada de acesso ao PostgreSQL |
| core.py | `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\cardapio_app\core.py` | Lógica central do backend |

---

## 2. FLUXO ENCONTRADO

### 2.1 Backend — Criação do Pedido (api_create_solicitacao)

**Arquivo**: `cardapio_app/routes.py`  
**Função**: `api_create_solicitacao()` (linha 1225)

```python
# Linha 1291: Geração do solicitacao_id
solicitacao_id = uuid.uuid4().hex

# Linha 1293: Armazenamento no record
rec: dict[str, Any] = {
    "id": solicitacao_id,
    "mesa": int(mesa),
    "status": "PENDENTE",
    # ... outros campos
}

# Linha 1315: Salvamento no PostgreSQL
core.pg_store.save_solicitacao(record=rec)

# Linha 1320: Criação do registro KDS
core.pg_store.kds_ensure_order_row(solicitacao_id=solicitacao_id)

# Linha 1335: Retorno ao frontend
return jsonify({"id": solicitacao_id, "status": "PENDENTE"})
```

**Propriedade JSON retornada**: `"id"` (string hexadecimal de 32 caracteres)

---

### 2.2 Frontend — Recepção da Resposta (enviarPedido)

**Arquivo**: `index.html`  
**Função**: `enviarPedido()` (linha 1528)

```javascript
// Linha 1646: Parse da resposta JSON
const out = await res.json();

// Linha 1647: Determinação do tipo de pedido
const kind = isSalao ? "SALAO" : "DELIVERY";

// Linha 1649: Extração do ID
const pedido = {
    id: out.id,  // ← solicitacao_id do backend
    kind,
    mesa: isSalao ? state.mesa : null,
    token: isSalao ? state.token : null,
    // ... outros campos
};

// Linha 1679: Chamada da tela pós-pedido
showPostOrderScreen({ 
    kind, 
    mesa: isSalao ? state.mesa : null, 
    cliente_nome: String(state.clientName || "").trim(), 
    solicitacao_id: out.id  // ← passagem do solicitacao_id
});
```

**Fluxo do solicitacao_id**: `out.id` → `pedido.solicitacao_id` → `showPostOrderScreen(pedidoInfo)`

---

### 2.3 Frontend — Tela Pós-Pedido (showPostOrderScreen)

**Arquivo**: `index.html`  
**Função**: `showPostOrderScreen(pedidoInfo)` (linha 1731)

```javascript
function showPostOrderScreen(pedidoInfo) {
    // ... código de manipulação de UI
    
    // Linha 1802: Condição para pedidos de salão
    if (pedidoInfo && pedidoInfo.kind === "SALAO" && pedidoInfo.mesa) {
        // ... criação da infoDiv com informações do pedido
        
        // Linha 1828-1831: Condição para iniciar polling
        console.log("showPostOrderScreen: pedidoInfo =", pedidoInfo);
        console.log("showPostOrderScreen: state.token =", state.token);
        
        if (pedidoInfo.solicitacao_id && state.token) {
            const solicitacaoId = pedidoInfo.solicitacao_id;
            const mesa = pedidoInfo.mesa;
            const token = state.token;
            console.log("Iniciando polling KDS: solicitacaoId =", solicitacaoId, ", mesa =", mesa);

            // Linha 1837: Definição da função de polling
            const pollKdsStatus = async () => {
                try {
                    // Linha 1839: Construção da URL
                    const url = `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`;
                    console.log("Polling KDS: fetch", url);
                    
                    // Linha 1841: Execução do fetch
                    const res = await fetch(url);
                    console.log("Polling KDS: response status =", res.status, "ok =", res.ok);
                    
                    if (res.ok) {
                        const data = await res.json();
                        console.log("Polling KDS: response data =", data);
                        const status = data.status;
                        const statusText = document.getElementById("kdsStatusText");
                        if (statusText) {
                            // Linha 1849-1860: Atualização da interface
                            if (status === "AGUARDANDO") {
                                statusText.textContent = "Pedido recebido";
                            } else if (status === "EM_PREPARO") {
                                statusText.textContent = "Seu pedido está sendo preparado";
                            } else if (status === "PRONTO") {
                                statusText.textContent = "Seu pedido está pronto";
                                // Parar polling quando status for PRONTO
                                if (_kdsPollingTimer) {
                                    clearInterval(_kdsPollingTimer);
                                    _kdsPollingTimer = null;
                                }
                            }
                        }
                    } else {
                        console.error("Polling KDS: response not ok, status =", res.status);
                    }
                } catch (err) {
                    console.error("Erro ao consultar status KDS:", err);
                }
            };

            // Linha 1872: Início do polling (setInterval)
            _kdsPollingTimer = setInterval(pollKdsStatus, 2500);
            
            // Linha 1874: Primeira consulta imediata
            pollKdsStatus();
        } else {
            console.log("Polling KDS não iniciado: solicitacao_id =", pedidoInfo.solicitacao_id, ", token =", state.token);
        }
    }
}
```

**Condições críticas para polling**:
1. `pedidoInfo.kind === "SALAO"`
2. `pedidoInfo.mesa` existe
3. `pedidoInfo.solicitacao_id` existe
4. `state.token` existe

---

### 2.4 Backend — Endpoint kds-status (api_get_solicitacao_kds_status)

**Arquivo**: `cardapio_app/routes.py`  
**Função**: `api_get_solicitacao_kds_status(solicitacao_id)` (linha 1354)

```python
@app.get("/api/solicitacoes/<solicitacao_id>/kds-status")
def api_get_solicitacao_kds_status(solicitacao_id: str):
    logger.info(f"api_get_solicitacao_kds_status chamado: solicitacao_id={solicitacao_id}")
    mesa = request.args.get("mesa")
    token = request.args.get("token")
    logger.info(f"api_get_solicitacao_kds_status: mesa={mesa}, token_prefix={str(token or '')[:8]}")
    
    # Linha 1359: Validação do token da mesa
    ok, err = core.validate_table_token(ctx=_ctx(), mesa=mesa, token=token)
    if not ok:
        logger.info(f"api_get_solicitacao_kds_status: token validation failed: {err}")
        return jsonify({"error": err}), 401

    # Linha 1364: Verificação do PostgreSQL
    if not core.pg_enabled():
        logger.info(f"api_get_solicitacao_kds_status: pg_disabled")
        return jsonify({"error": "pg_disabled"}), 500

    # Linha 1368: Busca da solicitação
    data = core.ensure_solicitacoes_file(_ctx())
    _, s = core.find_solicitacao(_ctx(), data, solicitacao_id)
    if s is None:
        logger.info(f"api_get_solicitacao_kds_status: solicitacao not found in file")
        return jsonify({"error": "nao_encontrado"}), 404
    
    # Linha 1373: Validação da mesa
    if int(s.get("mesa") or 0) != int(mesa):
        logger.info(f"api_get_solicitacao_kds_status: mesa mismatch")
        return jsonify({"error": "forbidden"}), 403

    # Linha 1378: Consulta do status KDS
    try:
        logger.info(f"api_get_solicitacao_kds_status: chamando kds_get_status")
        status = core.pg_store.kds_get_status(solicitacao_id=solicitacao_id)
        logger.info(f"api_get_solicitacao_kds_status: status retornado: {status}")
    except Exception as e:
        logger.error(f"api_get_solicitacao_kds_status: erro ao chamar kds_get_status: {e}")
        return jsonify({"error": "erro_interno"}), 500

    if status is None:
        logger.info(f"api_get_solicitacao_kds_status: status is None")
        return jsonify({"error": "nao_encontrado"}), 404

    logger.info(f"api_get_solicitacao_kds_status: retornando status={status}")
    return jsonify({"status": status})
```

**Códigos de erro possíveis**:
- 401: `token_invalido`, `mesa_invalida`, `mesa_fora_do_intervalo`, `token_ausente`, `mesa_nao_cadastrada`
- 403: `forbidden` (mismatch de mesa)
- 404: `nao_encontrado` (pedido não existe)
- 500: `pg_disabled`, `erro_interno`

---

## 3. MATRIZ DE RASTREAMENTO

| Etapa | Arquivo | Função | Linha | Evidência no código | Condição necessária | Risco encontrado |
|-------|---------|--------|-------|-------------------|-------------------|------------------|
| Criação do pedido | routes.py | api_create_solicitacao | 1291 | `solicitacao_id = uuid.uuid4().hex` | Nenhuma | ❌ Nenhum |
| Geração do ID | routes.py | api_create_solicitacao | 1291 | UUID hex string (32 caracteres) | Nenhuma | ❌ Nenhum |
| Armazenamento no record | routes.py | api_create_solicitacao | 1293 | `rec["id"] = solicitacao_id` | Nenhuma | ❌ Nenhum |
| Salvamento PostgreSQL | routes.py | api_create_solicitacao | 1315 | `core.pg_store.save_solicitacao(record=rec)` | pg_enabled | ⚠️ PostgreSQL required |
| Criação registro KDS | routes.py | api_create_solicitacao | 1320 | `core.pg_store.kds_ensure_order_row(solicitacao_id=solicitacao_id)` | pg_enabled | ⚠️ PostgreSQL required |
| Retorno HTTP | routes.py | api_create_solicitacao | 1335 | `return jsonify({"id": solicitacao_id, "status": "PENDENTE"})` | Nenhuma | ❌ Nenhum |
| Recepção JSON | index.html | enviarPedido | 1646 | `const out = await res.json()` | Resposta HTTP ok | ❌ Nenhum |
| Extração out.id | index.html | enviarPedido | 1649 | `id: out.id` | JSON parse ok | ❌ Nenhum |
| Chamada showPostOrderScreen | index.html | enviarPedido | 1679 | `showPostOrderScreen({ solicitacao_id: out.id })` | Pedido salão | ⚠️ Chamada condicional |
| Parâmetro pedidoInfo | index.html | showPostOrderScreen | 1731 | `function showPostOrderScreen(pedidoInfo)` | Chamada correta | ❌ Nenhum |
| Condição SALAO | index.html | showPostOrderScreen | 1802 | `if (pedidoInfo && pedidoInfo.kind === "SALAO" && pedidoInfo.mesa)` | kind == "SALAO" | ⚠️ Dependente de tipo |
| Condição solicitacao_id | index.html | showPostOrderScreen | 1831 | `if (pedidoInfo.solicitacao_id && state.token)` | Ambos verdadeiros | ⚠️ **RISCO CRÍTICO** |
| Extração solicitacaoId | index.html | showPostOrderScreen | 1832 | `const solicitacaoId = pedidoInfo.solicitacao_id` | Existência | ❌ Nenhum |
| Extração mesa | index.html | showPostOrderScreen | 1833 | `const mesa = pedidoInfo.mesa` | Existência | ❌ Nenhum |
| Extração token | index.html | showPostOrderScreen | 1834 | `const token = state.token` | Existência | ⚠️ Dependente de disponibilidade |
| Definição pollKdsStatus | index.html | showPostOrderScreen | 1837 | `const pollKdsStatus = async () => { ... }` | Nenhuma | ❌ Nenhum |
| Construção URL | index.html | pollKdsStatus | 1839 | `const url = `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`` | Parâmetros válidos | ❌ Nenhum |
| Execução fetch | index.html | pollKdsStatus | 1841 | `const res = await fetch(url)` | URL válida | ❌ Nenhum |
| setInterval | index.html | showPostOrderScreen | 1872 | `_kdsPollingTimer = setInterval(pollKdsStatus, 2500)` | Condição satisfeita | ⚠️ Dependente de condição |
| Primeira consulta | index.html | showPostOrderScreen | 1874 | `pollKdsStatus()` | Nenhuma | ❌ Nenhum |
| Validação token | routes.py | api_get_solicitacao_kds_status | 1359 | `core.validate_table_token(ctx=_ctx(), mesa=mesa, token=token)` | Token válido | ⚠️ Validação estrita |
| Verificação pg_enabled | routes.py | api_get_solicitacao_kds_status | 1364 | `if not core.pg_enabled()` | PostgreSQL ativo | ⚠️ PostgreSQL required |
| Busca solicitação | routes.py | api_get_solicitacao_kds_status | 1369 | `_, s = core.find_solicitacao(_ctx(), data, solicitacao_id)` | Pedido existe | ⚠️ Pedido deve existir |
| Validação mesa | routes.py | api_get_solicitacao_kds_status | 1373 | `if int(s.get("mesa") or 0) != int(mesa)` | Mesa correta | ⚠️ Mesa deve corresponder |
| Chamada kds_get_status | routes.py | api_get_solicitacao_kds_status | 1379 | `core.pg_store.kds_get_status(solicitacao_id=solicitacao_id)` | Nenhuma | ❌ Nenhum |
| Retorno status | routes.py | api_get_solicitacao_kds_status | 1390 | `return jsonify({"status": status})` | Status encontrado | ⚠️ Registro KDS deve existir |
| Atualização interface | index.html | pollKdsStatus | 1847-1860 | `statusText.textContent = ...` | Resposta ok | ❌ Nenhum |

---

## 4. TOKENS

### 4.1 Tabela de Tokens

| Variável | Onde nasce | Tipo | Para que serve | Onde é usada | Formato |
|----------|-----------|------|---------------|-------------|--------|
| `state.token` | assets/app.js:318-327 (getMesaTokenFromUrl) ou assets/app.js:329-337 (getMesaTokenFromLocal) | String | Token de autenticação da mesa para pedidos de salão | Validado pelo backend em `validate_table_token()`, usado em requisições `/api/solicitacoes/*` | String, mínimo 10 caracteres |
| `access_token` | routes.py:1472 (secrets.token_urlsafe(24)) | String | Token público para pedidos de delivery/retirada | Usado em `/api/public/pedidos/*` e página `/status/<access_token>` | URL-safe base64, 32 caracteres |
| `token` (backend) | mesas.json (configuração estática) | String | Configuração estática das mesas | Comparado com `state.token` na validação | String, mínimo 10 caracteres |

### 4.2 Ciclo de Vida do state.token

```text
Inicialização (index.html:2614-2627)
    ↓
const mtUrl = getMesaTokenFromUrl()           // Tenta obter da URL (?mesa=X&token=Y)
    ↓
const mtLocal = getMesaTokenFromLocal()       // Tenta obter do localStorage
    ↓
const mt = (mtUrl && mtUrl.mesa && mtUrl.token) ? mtUrl : mtLocal
    ↓
state.token = mt.token                         // Atribuição ao state
    ↓
Uso em enviarPedido (index.html:1535)         // const isSalao = Boolean(state.mesa && state.token)
    ↓
Uso em showPostOrderScreen (index.html:1831)   // if (pedidoInfo.solicitacao_id && state.token)
```

**Condições de disponibilidade**:
- URL deve conter `?mesa=X&token=Y` **OU**
- localStorage deve conter `cardapio.mesa.v1` e `cardapio.token.v1` válidos
- Token deve ter no mínimo 10 caracteres (validação em getMesaTokenFromUrl)

### 4.3 Validação do Token (validate_table_token)

**Arquivo**: `cardapio_app/core.py`  
**Função**: `validate_table_token()` (linha 863)

```python
def validate_table_token(*, ctx: AppContext, mesa: Any, token: Any) -> tuple[bool, str]:
    try:
        mesa_i = int(mesa)
    except Exception:
        return False, "mesa_invalida"

    if mesa_i < 1 or mesa_i > 30:
        return False, "mesa_fora_do_intervalo"

    tok = str(token or "").strip()
    if not tok:
        return False, "token_ausente"

    mp = get_table_token_map(ctx)
    expected = mp.get(mesa_i)
    if not expected:
        return False, "mesa_nao_cadastrada"
    if tok != expected:
        return False, "token_invalido"

    return True, ""
```

**Condições de validação**:
1. Mesa deve ser inteiro entre 1 e 30
2. Token não pode estar vazio
3. Mesa deve estar cadastrada em mesas.json
4. Token deve corresponder exatamente ao token configurado para a mesa

---

## 5. solicitacao_id

### 5.1 Ciclo Completo

```text
Backend (routes.py:1291)
    ↓
solicitacao_id = uuid.uuid4().hex  // "550e8400-e29b-41d4-a716-446655440000" → "550e8400e29b41d4a716446655440000"
    ↓
Backend (routes.py:1293)
    ↓
rec["id"] = solicitacao_id
    ↓
Backend (routes.py:1315)
    ↓
core.pg_store.save_solicitacao(record=rec)  // Salvo em cardapio_solicitacoes
    ↓
Backend (routes.py:1320)
    ↓
core.pg_store.kds_ensure_order_row(solicitacao_id=solicitacao_id)  // Criado em kds_orders
    ↓
Backend (routes.py:1335)
    ↓
return jsonify({"id": solicitacao_id, "status": "PENDENTE"})
    ↓
Frontend (index.html:1646)
    ↓
const out = await res.json()  // out = { "id": "550e8400e29b41d4a716446655440000", "status": "PENDENTE" }
    ↓
Frontend (index.html:1649)
    ↓
id: out.id  // pedido.id = "550e8400e29b41d4a716446655440000"
    ↓
Frontend (index.html:1679)
    ↓
showPostOrderScreen({ solicitacao_id: out.id })  // pedidoInfo.solicitacao_id = "550e8400e29b41d4a716446655440000"
    ↓
Frontend (index.html:1832)
    ↓
const solicitacaoId = pedidoInfo.solicitacao_id
    ↓
Frontend (index.html:1839)
    ↓
const url = `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`
    ↓
Backend (routes.py:1354)
    ↓
def api_get_solicitacao_kds_status(solicitacao_id: str)
```

### 5.2 Características

- **Formato**: String hexadecimal de 32 caracteres (UUID sem hífens)
- **Origem**: `uuid.uuid4().hex` (Python)
- **Propriedade JSON**: `"id"` no objeto de resposta
- **Uso**: Identificador único do pedido em todo o sistema
- **Persistência**: Salvo em `cardapio_solicitacoes` (PostgreSQL) e `kds_orders` (PostgreSQL)

---

## 6. POLLING

### 6.1 Como Deveria Ser Iniciado (Segundo o Código Atual)

```text
[Linha 1802] if (pedidoInfo && pedidoInfo.kind === "SALAO" && pedidoInfo.mesa)
    ↓
[Linha 1824-1826] if (post && post.parentNode) { post.insertBefore(infoDiv, post.firstChild); }
    ↓
[Linha 1829] console.log("showPostOrderScreen: pedidoInfo =", pedidoInfo)
    ↓
[Linha 1830] console.log("showPostOrderScreen: state.token =", state.token)
    ↓
[Linha 1831] if (pedidoInfo.solicitacao_id && state.token)
    ↓
[Linha 1832] const solicitacaoId = pedidoInfo.solicitacao_id
    ↓
[Linha 1833] const mesa = pedidoInfo.mesa
    ↓
[Linha 1834] const token = state.token
    ↓
[Linha 1835] console.log("Iniciando polling KDS: solicitacaoId =", solicitacaoId, ", mesa =", mesa)
    ↓
[Linha 1837] const pollKdsStatus = async () => { ... }
    ↓
[Linha 1872] _kdsPollingTimer = setInterval(pollKdsStatus, 2500)
    ↓
[Linha 1874] pollKdsStatus()
```

### 6.2 Condições Necessárias

1. **Tipo de pedido**: `pedidoInfo.kind === "SALAO"`
2. **Mesa disponível**: `pedidoInfo.mesa` existe e não é null
3. **solicitacao_id disponível**: `pedidoInfo.solicitacao_id` existe e não é null
4. **Token disponível**: `state.token` existe e não é null

### 6.3 Parâmetros do Polling

- **Intervalo**: 2500ms (2.5 segundos)
- **Método**: GET
- **URL**: `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`
- **Comportamento**: Polling contínuo até status ser "PRONTO"
- **Cancelamento**: Quando status === "PRONTO", `clearInterval(_kdsPollingTimer)`

### 6.4 Tratamento de Resposta

```javascript
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
            if (_kdsPollingTimer) {
                clearInterval(_kdsPollingTimer);
                _kdsPollingTimer = null;
            }
        }
    }
}
```

---

## 7. ENDPOINT kds-status

### 7.1 Condições Necessárias para Responder

```text
[1] Validação de token da mesa (validate_table_token)
    ↓
Mesa deve ser inteiro entre 1 e 30
    ↓
Token não pode estar vazio
    ↓
Mesa deve estar cadastrada em mesas.json
    ↓
Token deve corresponder exatamente ao configurado
    ↓
[2] Verificação do PostgreSQL (pg_enabled)
    ↓
DATABASE_URL deve estar configurado
    ↓
[3] Busca da solicitação (find_solicitacao)
    ↓
solicitacao_id deve existir em cardapio_solicitacoes
    ↓
[4] Validação da mesa
    ↓
Mesa do pedido deve corresponder à mesa da requisição
    ↓
[5] Consulta do status KDS (kds_get_status)
    ↓
solicitacao_id deve existir em kds_orders
    ↓
[6] Retorno do status
    ↓
return jsonify({"status": status})
```

### 7.2 Códigos de Resposta

| Código | Condição | Mensagem de erro |
|--------|-----------|------------------|
| 200 | Sucesso | `{"status": "AGUARDANDO"|"EM_PREPARO"|"PRONTO"}` |
| 401 | Token inválido | `{"error": "token_invalido"|"mesa_invalida"|"token_ausente"|"mesa_nao_cadastrada"}` |
| 403 | Mesa mismatch | `{"error": "forbidden"}` |
| 404 | Pedido não encontrado | `{"error": "nao_encontrado"}` |
| 500 | PostgreSQL desabilitado ou erro interno | `{"error": "pg_disabled"|"erro_interno"}` |

### 7.3 Logs do Endpoint

O endpoint possui logs detalhados em cada etapa:

```python
logger.info(f"api_get_solicitacao_kds_status chamado: solicitacao_id={solicitacao_id}")
logger.info(f"api_get_solicitacao_kds_status: mesa={mesa}, token_prefix={str(token or '')[:8]}")
logger.info(f"api_get_solicitacao_kds_status: token validation failed: {err}")
logger.info(f"api_get_solicitacao_kds_status: pg_disabled")
logger.info(f"api_get_solicitacao_kds_status: solicitacao not found in file")
logger.info(f"api_get_solicitacao_kds_status: mesa mismatch")
logger.info(f"api_get_solicitacao_kds_status: chamando kds_get_status")
logger.info(f"api_get_solicitacao_kds_status: status retornado: {status}")
logger.error(f"api_get_solicitacao_kds_status: erro ao chamar kds_get_status: {e}")
logger.info(f"api_get_solicitacao_kds_status: status is None")
logger.info(f"api_get_solicitacao_kds_status: retornando status={status}")
```

---

## 8. DUPLICIDADES

### 8.1 showPostOrderScreen

**⚠️ CRÍTICO: Existem duas definições diferentes**

| Localização | Arquivo | Linha | Assinatura | Funcionalidade KDS |
|-------------|---------|-------|------------|-------------------|
| Versão 1 | index.html | 1731 | `function showPostOrderScreen(pedidoInfo)` | **COM** polling KDS completo |
| Versão 2 | assets/app.js | 1226 | `function showPostOrderScreen()` | **SEM** polling KDS |

**Diferenças principais**:
- **Versão 1 (index.html)**: Recebe `pedidoInfo` como parâmetro, contém lógica de polling KDS (linhas 1828-1877)
- **Versão 2 (app.js)**: Não recebe parâmetro, não contém lógica de polling KDS

### 8.2 pollKdsStatus

| Localização | Arquivo | Linha | Status |
|-------------|---------|-------|--------|
| index.html | 1837 | Definida dentro de `showPostOrderScreen()` | ✅ Presente |
| assets/app.js | - | - | ❌ Ausente |

### 8.3 _kdsPollingTimer

| Localização | Arquivo | Linha | Status |
|-------------|---------|-------|--------|
| index.html | 1729 | `let _kdsPollingTimer = null` | ✅ Presente |
| assets/app.js | - | - | ❌ Ausente |

### 8.4 Estrutura de Carregamento de Scripts

```html
<!-- index.html:1030 -->
<script src="/assets/app.js"></script>

<!-- index.html:1032-2677 -->
<script type="text/plain" id="legacyInlineScript">
    <!-- JavaScript inline com outra versão das funções -->
</script>
```

**⚠️ PROBLEMA**: O `index.html` carrega `app.js` **E** possui JavaScript inline. O JavaScript inline contém a versão de `showPostOrderScreen()` com polling KDS, enquanto `app.js` contém uma versão diferente sem essa funcionalidade.

**Possíveis cenários**:
1. Se `app.js` for carregado primeiro, sua versão de `showPostOrderScreen()` (sem polling) pode sobrescrever a versão inline
2. Se o inline for executado depois, pode sobrescrever a versão de `app.js`
3. A ordem de execução determina qual versão prevalece

---

## 9. CACHE / PWA / SERVICE WORKER

### 9.1 Service Worker
- **Status**: Não encontrado
- **Arquivos buscados**: `sw.js`, `service-worker.js`
- **Resultado**: Nenhum arquivo encontrado

### 9.2 PWA Manifest
- **Status**: Não encontrado
- **Arquivos buscados**: `manifest.json`
- **Resultado**: Nenhum arquivo encontrado

### 9.3 Cache API
- **Status**: Não há evidência de implementação de cache controlado
- **Conclusão**: O código é servido diretamente do HTML sem versionamento explícito

### 9.4 Cache do Navegador
- **Headers de cache**: Os endpoints do backend usam `Cache-Control: no-store` (confirmado em routes.py:209)
- **HTML estático**: Não há evidência de headers de cache no HTML estático
- **Risco**: O navegador pode estar cacheando uma versão antiga do `index.html`

---

## 10. POSSÍVEIS ERROS DE EXECUÇÃO

### 10.1 Análise Estática de Erros

| Tipo de Erro | Localização | Causa Possível | Probabilidade |
|--------------|-------------|----------------|---------------|
| ReferenceError | index.html:1831 | `pedidoInfo` undefined | Baixa (pedidoInfo é parâmetro) |
| ReferenceError | index.html:1831 | `state` undefined | Baixa (state é global) |
| TypeError | index.html:1831 | `pedidoInfo.solicitacao_id` undefined | **Média** (depende do objeto) |
| TypeError | index.html:1831 | `state.token` undefined | **Média** (depende da disponibilidade) |
| TypeError | index.html:1839 | `solicitacaoId` undefined na concatenação | Baixa (verificado antes) |
| NetworkError | index.html:1841 | Falha no fetch | Baixa (tratado com try/catch) |
| JSONError | index.html:1844 | Resposta não é JSON | Baixa (tratado com try/catch) |

### 10.2 Pontos Críticos

**Ponto 1: Condição de polling (index.html:1831)**
```javascript
if (pedidoInfo.solicitacao_id && state.token)
```
- **Risco**: Se qualquer um dos lados for falsy, o polling nunca inicia
- **Causas possíveis**:
  - `pedidoInfo.solicitacao_id` undefined/null (improvável se backend funcionou)
  - `state.token` undefined/null (possível se mesa/token não configurados)

**Ponto 2: Duplicidade de showPostOrderScreen**
- **Risco**: A versão errada da função pode ser executada
- **Causa possível**: Conflito entre `app.js` e JavaScript inline

**Ponto 3: Ordem de carregamento**
- **Risco**: Script externo pode sobrescrever função inline
- **Causa possível**: `<script src="/assets/app.js"></script>` carregado antes do inline

---

## 11. CLASSIFICAÇÃO DAS HIPÓTESES

### H1 — Frontend servido em versão antiga
**Classificação**: **POSSÍVEL**

**Evidências**:
- Existe duplicidade de scripts (app.js vs inline)
- A ordem de carregamento pode determinar qual versão é executada
- Não há versionamento explícito do HTML estático
- Os console.log adicionados não apareceram no navegador

**Contra-evidências**:
- Backend usa `Cache-Control: no-store` para endpoints dinâmicos
- Não há service worker ou PWA que possa causar cache agressivo

---

### H2 — showPostOrderScreen() não recebe solicitacao_id
**Classificação**: **DESCARTADA**

**Evidências**:
- O código em index.html:1679 passa explicitamente `solicitacao_id: out.id`
- O backend retorna `{"id": solicitacao_id, "status": "PENDENTE"}` (routes.py:1335)
- O frontend extrai `out.id` corretamente (index.html:1649)

**Conclusão**: O solicitacao_id está sendo passado corretamente para a função.

---

### H3 — state.token não está disponível
**Classificação**: **POSSÍVEL**

**Evidências**:
- `state.token` depende de URL parameters ou localStorage
- Se o cliente acessar sem `?mesa=X&token=Y`, o token pode estar ausente
- A função `getMesaTokenFromUrl()` retorna `{mesa: null, token: null}` se parâmetros inválidos
- A condição `if (pedidoInfo.solicitacao_id && state.token)` falharia se token ausente

**Contra-evidências**:
- Os logs do Railway mostram que `api_create_solicitacao` foi executado com sucesso (token foi validado)
- Se o token estivesse ausente, o próprio `api_create_solicitacao` teria falhado (validação em routes.py:1241)

**Conclusão**: O token provavelmente está disponível, mas não pode ser garantido sem instrumentação.

---

### H4 — condição do polling não é satisfeita
**Classificação**: **POSSÍVEL**

**Evidências**:
- A condição `if (pedidoInfo.solicitacao_id && state.token)` depende de múltiplos fatores
- Qualquer um falsy impede o polling
- Existem console.log que indicariam se a condição falhou, mas não apareceram

**Contra-evidências**:
- Se o pedido foi criado com sucesso, `solicitacao_id` deve existir
- Se `api_create_solicitacao` funcionou, o token foi validado

**Conclusão**: A condição deve ser satisfeita, mas não pode ser garantido sem instrumentação.

---

### H5 — polling não é iniciado
**Classificação**: **POSSÍVEL**

**Evidências**:
- Se a condição em linha 1831 for falsa, o setInterval nunca é executado
- Os logs do Railway não mostram chamadas ao endpoint `kds-status`
- Isso é consistente com o polling nunca ter iniciado

**Contra-evidências**:
- O código para iniciar o polling está presente e parece correto

**Conclusão**: O polling provavelmente não está sendo iniciado, mas a causa exata não pode ser determinada estaticamente.

---

### H6 — pollKdsStatus() possui falha lógica
**Classificação**: **DESCARTADA**

**Evidências**:
- A função parece logicamente correta para fazer polling e atualizar a interface
- Possui try/catch adequado para erros de rede
- Atualiza a interface corretamente para cada status
- Cancela o polling quando status é "PRONTO"

**Conclusão**: A função não possui falhas lógicas evidentes.

---

### H7 — fetch() está incorreto
**Classificação**: **DESCARTADA**

**Evidências**:
- A URL é construída corretamente: `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`
- Os parâmetros são obtidos das variáveis corretas
- Não há falta de `encodeURIComponent` (embora não seja estritamente necessário para esses valores)

**Conclusão**: O fetch está implementado corretamente.

---

### H8 — token enviado pelo frontend não corresponde ao esperado pelo backend
**Classificação**: **DESCARTADA**

**Evidências**:
- O `state.token` é obtido das mesmas fontes (URL/localStorage) que configuram as mesas no backend
- A validação `validate_table_token()` compara o token recebido com o token configurado em mesas.json
- Se `api_create_solicitacao` funcionou, o token foi validado com sucesso

**Conclusão**: O token enviado deve corresponder ao esperado pelo backend.

---

### H9 — problema no backend
**Classificação**: **DESCARTADA**

**Evidências**:
- O endpoint `kds-status` está implementado corretamente
- Possui logs detalhados em cada etapa
- A função `kds_get_status()` está implementada corretamente em pg_store.py
- Os logs do Railway mostram que `kds_ensure_order_row` foi executado com sucesso

**Conclusão**: O backend não apresenta problemas evidentes.

---

### H10 — problema de atualização da interface
**Classificação**: **DESCARTADA**

**Evidências**:
- A atualização da interface está implementada corretamente em pollKdsStatus
- Os elementos DOM (`kdsStatusText`) são criados corretamente
- A lógica de atualização para cada status está correta

**Conclusão**: A atualização da interface não apresenta problemas evidentes.

---

## 12. CAUSA MAIS PROVÁVEL

**H1 — Frontend servido em versão antiga / Duplicidade de Scripts**

### 12.1 Evidências Principais

**1. Duplicidade crítica de showPostOrderScreen()**

```javascript
// Versão 1: index.html:1731 (COM polling KDS)
function showPostOrderScreen(pedidoInfo) {
    // ... 
    if (pedidoInfo.solicitacao_id && state.token) {
        const pollKdsStatus = async () => { ... }
        _kdsPollingTimer = setInterval(pollKdsStatus, 2500);
        pollKdsStatus();
    }
}

// Versão 2: assets/app.js:1226 (SEM polling KDS)
function showPostOrderScreen() {
    // ... sem lógica de polling KDS
}
```

**2. Ordem de carregamento problemática**

```html
<!-- index.html:1030 -->
<script src="/assets/app.js"></script>

<!-- index.html:1032-2677 -->
<script type="text/plain" id="legacyInlineScript">
    <!-- JavaScript inline com outra versão das funções -->
</script>
```

**3. Conflito de definições**

- Se `app.js` for carregado primeiro, sua versão de `showPostOrderScreen()` (sem polling) pode sobrescrever a versão inline
- Se o inline for executado depois, pode sobrescrever a versão de `app.js`
- A ordem de execução determina qual versão prevalece

**4. Ausência de logs do endpoint**

- Os logs do Railway mostram que `api_create_solicitacao` foi executado com sucesso
- Porém não há logs de `api_get_solicitacao_kds_status`, indicando que o polling nunca iniciou
- Isso é consistente com a versão de `showPostOrderScreen()` sem polling ser executada

**5. Ausência de console.log no navegador**

- Os console.log adicionados à versão inline (linhas 1829-1830, 1835, 1840, 1842, 1845) não apareceram
- Isso sugere que a versão sendo executada não é a versão inline com os logs
- Se a versão de `app.js` estivesse sendo executada, esses logs não existiriam

### 12.2 Cenário Provável

```text
1. Navegador carrega index.html
2. Script <script src="/assets/app.js"></script> é carregado
3. Função showPostOrderScreen() de app.js (SEM polling) é definida
4. JavaScript inline de index.html é executado
5. Função showPostOrderScreen() de index.html (COM polling) é definida
6. A segunda definição sobrescreve a primeira
7. showPostOrderScreen() é chamada com pedidoInfo
8. A versão COM polling é executada
9. ... mas por algum motivo o polling não inicia
```

**OU**:

```text
1. Navegador carrega index.html
2. Script <script src="/assets/app.js"></script> é carregado
3. Função showPostOrderScreen() de app.js (SEM polling) é definida
4. JavaScript inline de index.html NÃO é executado (erro de parsing, cache, etc.)
5. showPostOrderScreen() é chamada com pedidoInfo
6. A versão SEM polling é executada
7. Polling nunca inicia
```

### 12.3 Conclusão

A causa mais provável é que **a versão de `showPostOrderScreen()` sendo executada no navegador não é a versão com polling KDS**, ou que **existe um conflito na ordem de carregamento dos scripts** que impede a execução correta da versão com polling.

Isso explica:
- Por que os logs do endpoint não aparecem no Railway
- Por que os console.log não aparecem no navegador
- Por que o pedido é criado com sucesso mas o polling nunca inicia

---

## 13. LIMITAÇÕES DA AUDITORIA ESTÁTICA

### 13.1 Não é possível provar dinamicamente

- **Qual versão da função está sendo executada**: Sem instrumentação em runtime, não é possível determinar se a versão de `app.js` ou a versão inline de `index.html` está sendo executada
- **Ordem exata de execução dos scripts**: Sem análise do runtime, não é possível determinar a ordem exata de carregamento e execução
- **Valores reais das variáveis**: Sem instrumentação, não é possível confirmar se `state.token` e `pedidoInfo.solicitacao_id` estão realmente preenchidos

### 13.2 Não é possível verificar sem inspeção do cliente

- **Cache do navegador**: Não é possível confirmar se há cache do navegador servindo versão antiga sem inspeção do cliente
- **Estado do localStorage**: Não é possível verificar o conteúdo real do localStorage em produção
- **Parâmetros da URL**: Não é possível confirmar quais parâmetros o cliente está usando na URL

### 13.3 Depende de execução dinâmica

- **Execução real do setInterval**: A existência do código não prova que `setInterval` foi executado
- **Chamadas reais ao fetch**: A existência do código não prova que `fetch` foi chamado
- **Respostas reais do backend**: A análise estática não pode confirmar o comportamento real em produção

---

## 14. PRÓXIMA ETAPA RECOMENDADA

### 14.1 Teste de Instrumentação Mínima

**Objetivo**: Confirmar qual versão de `showPostOrderScreen()` está sendo executada

**Passos**:

1. **Adicionar marcador único na versão inline** (index.html):
```javascript
function showPostOrderScreen(pedidoInfo) {
    console.log("[DEBUG-INLINE] showPostOrderScreen executado - VERSÃO COM POLLING");
    // ... restante do código
}
```

2. **Adicionar marcador diferente na versão de app.js**:
```javascript
function showPostOrderScreen() {
    console.log("[DEBUG-APPJS] showPostOrderScreen executado - VERSÃO SEM POLLING");
    // ... restante do código
}
```

3. **Fazer um pedido real** e verificar qual marcador aparece no console do navegador

4. **Verificar os logs do Railway** simultaneamente para confirmar se o endpoint `kds-status` é chamado

### 14.2 Teste Alternativo (Sem Modificação de Código)

**Objetivo**: Verificar qual versão está sendo servida

**Passos**:

1. **Inspecionar o HTML servido** usando curl ou ferramenta similar:
```bash
curl https://dominio-do-cardapio.com/index.html
```

2. **Verificar se o JavaScript inline está presente** no HTML servido

3. **Verificar se o script app.js está sendo carregado**:
```bash
curl https://dominio-do-cardapio.com/assets/app.js
```

4. **Comparar os arquivos** com as versões locais para identificar discrepâncias

### 14.3 Não Executar Sem Autorização

**⚠️ IMPORTANTE**: Não executar estes testes sem autorização explícita do usuário, pois envolvem modificação do código em produção ou acesso aos logs do Railway.

---

## 15. HISTÓRICO DE MUDANÇAS

### 15.1 Modificações Recentes

**Data**: 2026-07-31  
**Tipo**: Reversão de instrumentação indevida  
**Ação**: Usuário reverteu manualmente alterações não autorizadas no `index.html`

**Contexto**: Durante uma tentativa anterior de diagnóstico, foi adicionada instrumentação temporária (painel de debug visual) ao `index.html` sem autorização. O usuário reverteu essas alterações manualmente.

**Estado atual**: O arquivo `index.html` está no estado original, sem a instrumentação temporária.

---

## 16. REFERÊNCIAS

### 16.1 Arquivos Principais

- `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\index.html` (2680 linhas)
- `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\assets\app.js` (2207 linhas)
- `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\cardapio_app\routes.py` (1716 linhas)
- `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\pg_store.py` (1990 linhas)
- `C:\Users\pwo\Desktop\App_DoRafa\Cardapio\cardapio_app\core.py` (1012 linhas)

### 16.2 Funções Principais Auditadas

- `api_create_solicitacao()` (routes.py:1225)
- `api_get_solicitacao_kds_status()` (routes.py:1354)
- `enviarPedido()` (index.html:1528)
- `showPostOrderScreen()` (index.html:1731 / app.js:1226)
- `validate_table_token()` (core.py:863)
- `kds_ensure_order_row()` (pg_store.py:575)
- `kds_get_status()` (pg_store.py:686)

### 16.3 Tabelas do PostgreSQL

- `cardapio_solicitacoes` (armazena pedidos)
- `kds_orders` (armazena status KDS)
- `cardapio_mesas` (armazena configuração de mesas)

---

## 17. CONCLUSÃO

A auditoria estática identificou uma **duplicidade crítica** na definição da função `showPostOrderScreen()`, com duas versões diferentes存在于 `index.html` (com polling KDS) e `assets/app.js` (sem polling KDS). 

A causa mais provável do problema é que **a versão sendo executada no navegador não é a versão com polling KDS**, devido a conflito na ordem de carregamento dos scripts ou execução de versão incorreta.

Esta conclusão é baseada em:
1. Ausência de logs do endpoint `kds-status` no Railway
2. Ausência de console.log no navegador
3. Estrutura de carregamento de scripts problemática
4. Duplicidade de definições de funções críticas

A próxima etapa recomendada é uma instrumentação mínima para confirmar qual versão da função está sendo executada em runtime.

---

**Relatório gerado em**: 2026-07-31  
**Tipo de auditoria**: Estática  
**Status**: Concluído  
**Próxima ação**: Aguardar autorização para instrumentação mínima