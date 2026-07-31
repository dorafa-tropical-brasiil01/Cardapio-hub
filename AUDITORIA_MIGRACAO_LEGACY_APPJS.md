# RELATÓRIO DE AUDITORIA DE MIGRAÇÃO LEGACY → `app.js`

**Projeto**: DoRafaPDV — Cardápio Online  
**Data**: 2026-07-31  
**Tipo**: Auditoria de Migração — Análise de Funcionalidade KDS  
**Objetivo**: Identificar o conjunto mínimo de componentes necessários para recuperar o Status Público do Pedido/KDS na arquitetura atual baseada em `assets/app.js`

---

## 1. CÓDIGO LEGADO RELEVANTE

### 1.1 Variável `_kdsPollingTimer`

**Localização**: index.html:1729 (dentro de legacyInlineScript)  
**Código**:
```javascript
let _kdsPollingTimer = null;
```

**Uso**:
- Linha 1750-1753: Limpeza de timer anterior em `showPostOrderScreen()`
- Linha 1872: Inicialização com `setInterval(pollKdsStatus, 2500)`
- Linha 1856-1859: Cancelamento quando status é "PRONTO"

### 1.2 Função `showPostOrderScreen(pedidoInfo)`

**Localização**: index.html:1731-1879 (dentro de legacyInlineScript)  
**Assinatura**: `function showPostOrderScreen(pedidoInfo)`

**Responsabilidades**:
1. Ocultar elementos da interface principal (header, search, banner, etc.)
2. Mostrar tela pós-pedido (`postOrderScreen`)
3. Definir `state.postOrderActive = true`
4. Limpar timer KDS anterior (`_kdsPollingTimer`)
5. Exibir imagem pós-pedido
6. **CRIAR dinamicamente infoDiv com informações do pedido para SALÃO** (linhas 1802-1826)
7. **INICIAR polling KDS** se `pedidoInfo.solicitacao_id` e `state.token` existirem (linhas 1828-1877)

**Dados de `pedidoInfo` exigidos**:
- `kind`: "SALAO" ou "DELIVERY"
- `mesa`: número da mesa (para SALÃO)
- `cliente_nome`: nome do cliente (opcional)
- `solicitacao_id`: ID do pedido (CRÍTICO para polling KDS)

**Dados de `state` exigidos**:
- `state.token`: token de autenticação da mesa (CRÍTICO para polling KDS)
- `state.data?.ui`: configurações de UI (imagem pós-pedido)

### 1.3 Função `pollKdsStatus()`

**Localização**: index.html:1837-1869 (definida dentro de `showPostOrderScreen`)  
**Escopo**: Closure dentro de `showPostOrderScreen(pedidoInfo)`

**Assinatura**: `const pollKdsStatus = async () => { ... }`

**Variáveis capturadas da closure**:
- `solicitacaoId`: de `pedidoInfo.solicitacao_id`
- `mesa`: de `pedidoInfo.mesa`
- `token`: de `state.token`

**Endpoint**: `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`  
**Método**: GET  
**Intervalo**: 2500ms (2.5 segundos)

**Comportamento**:
1. Faz fetch ao endpoint kds-status
2. Se resposta ok, extrai `data.status`
3. Atualiza elemento `#kdsStatusText` com texto baseado no status:
   - "AGUARDANDO" → "Pedido recebido"
   - "EM_PREPARO" → "Seu pedido está sendo preparado"
   - "PRONTO" → "Seu pedido está pronto"
4. Se status é "PRONTO", cancela polling (`clearInterval(_kdsPollingTimer)`)
5. Trata erros com try/catch (não interrompe a tela)

### 1.4 Elementos de UI Criados Dinamicamente

**Localização**: index.html:1803-1826

**Elemento criado**: `div` com `data-salao-info="true"`

**Estrutura**:
```html
<div data-salao-info="true" style="...">
    <div>Pedido enviado!</div>
    <div>
        <div>Cliente: [nome]</div>
        <div>Tipo: SALÃO</div>
        <div>Mesa: [número]</div>
    </div>
    <div id="kdsStatusArea" style="...">
        <div>Status:</div>
        <div id="kdsStatusText" style="...">Pedido recebido</div>
    </div>
    <div>Seu pedido foi recebido pela cozinha. Aguarde o preparo.</div>
</div>
```

**Elementos críticos**:
- `#kdsStatusArea`: container do status KDS
- `#kdsStatusText`: texto do status KDS (atualizado pelo polling)

---

## 2. FUNCIONALIDADES JÁ PRESENTES NO APP.JS

### 2.1 `showPostOrderScreen()`

**Localização**: assets/app.js:1226-1304  
**Assinatura**: `function showPostOrderScreen()` (sem parâmetros)

**Funcionalidades**:
1. ✅ Ocultar elementos da interface principal (identico ao legado)
2. ✅ Mostrar tela pós-pedido (`postOrderScreen`)
3. ✅ Definir `state.postOrderActive = true`
4. ✅ Exibir imagem pós-pedido
5. ✅ Tratamento de erro para imagem
6. ❌ **NÃO cria infoDiv com informações do pedido**
7. ❌ **NÃO possui polling KDS**
8. ✅ **Possui polling de status público para DELIVERY** (linhas 1284-1303)

### 2.2 Sistema de Status Público (DELIVERY)

**Funções**:
- `renderStatusPublicoNaTela()` (app.js:1306-1322)
- `refreshStatusPublicoNaTela()` (app.js:1324-1349)
- `startStatusPublicoPolling()` (app.js:1351-1358)
- `stopStatusPublicoPolling()` (app.js:1360-1365)

**Endpoint**: `/api/public/pedidos/${tracking.id}/status?token=${tracking.access_token}`  
**Timer**: `state.statusPublicoTimer` (diferente de `_kdsPollingTimer`)  
**Intervalo**: 2500ms (mesmo intervalo do legado)

**Dados usados**:
- `tracking.id`: ID do pedido
- `tracking.access_token`: token de acesso público
- `tracking.kind`: tipo de pedido (DELLIVERY)
- `tracking.tipo_entrega`: tipo de entrega

**UI**: Elemento `#postOrderStatusPublico` (já existe no HTML)

### 2.3 Sistema de Tracking

**Funções**:
- `saveTrackingPedido(tracking)` (app.js:976-978)
- `getTrackingPedido()` (app.js:980-987)
- `clearTrackingPedido()` (app.js:989-993)

**Armazenamento**: `localStorage` com chave `STORAGE_KEYS.trackingPedido`

**Dados salvos**:
```javascript
{
    id: out.id,
    access_token: out.token,
    kind: "DELIVERY",
    tipo_entrega: "DELIVERY" ou "RETIRADA"
}
```

**Salvamento**: Ocorre em `enviarPedido()` (app.js:1156-1165) **apenas para DELIVERY**

### 2.4 `enviarPedido()`

**Localização**: assets/app.js:1010-1175

**Fluxo atual**:
```javascript
// Linha 1130: Resposta do backend
const out = await res.json();

// Linha 1132-1154: Criação do objeto pedido
const pedido = {
    id: out.id,              // ✅ solicitacao_id é extraído
    kind,
    mesa: isSalao ? state.mesa : null,
    token: isSalao ? state.token : null,
    access_token: (!isSalao && out.token) ? out.token : null,
    // ... outros campos
};

// Linha 1156-1165: Salvar tracking Apenas para DELIVERY
if (!isSalao && out.token) {
    const tracking = {
        id: out.id,
        access_token: out.token,
        kind,
        tipo_entrega: String(state.deliveryType || "DELIVERY").toUpperCase()
    };
    saveTrackingPedido(tracking);
}

// Linha 1174: Chamada sem parâmetros
showPostOrderScreen();
```

**⚠️ PROBLEMA CRÍTICO**: Para pedidos de SALÃO, o `solicitacao_id` (out.id) não é salvo em nenhum tracking, e `showPostOrderScreen()` é chamado sem parâmetros.

---

## 3. DIFERENÇAS ENTRE LEGADO E ARQUITETURA ATUAL

### 3.1 Diferenças Relevantes para Status KDS

| Aspecto | Legado (index.html) | Atual (app.js) | Impacto |
|---------|-------------------|----------------|---------|
| Assinatura `showPostOrderScreen` | `showPostOrderScreen(pedidoInfo)` | `showPostOrderScreen()` | ❌ Perda de `solicitacao_id` |
| Salvamento de tracking | Não usa tracking | Usa `localStorage` para DELIVERY | ❌ SALÃO não tem tracking |
| Timer KDS | `_kdsPollingTimer` (variável global) | `state.statusPublicoTimer` (para DELIVERY) | ❌ Nenhum timer para SALÃO |
| Endpoint KDS | `/api/solicitacoes/<id>/kds-status` | `/api/public/pedidos/<id>/status` (para DELIVERY) | ❌ Endpoint diferente para SALÃO |
| UI de status KDS | Criada dinamicamente (`#kdsStatusArea`, `#kdsStatusText`) | Elemento estático `#postOrderStatusPublico` | ❌ Elementos não existem |
| Tipo de pedido suportado | SALÃO (com KDS) | DELIVERY (com status público) | ❌ SALÃO sem status |
| Autenticação | `state.token` (token de mesa) | `tracking.access_token` (token público) | ❌ Diferente |

### 3.2 Fluxo Legado × Atual

**Fluxo Legado (SALÃO)**:
```text
enviarPedido()
↓
out.id (solicitacao_id)
↓
showPostOrderScreen({ solicitacao_id: out.id, kind: "SALAO", mesa, cliente_nome })
↓
Cria infoDiv dinâmico com #kdsStatusArea e #kdsStatusText
↓
pollKdsStatus() usando solicitacao_id, mesa, state.token
↓
/api/solicitacoes/<id>/kds-status?mesa=X&token=Y
↓
Atualiza #kdsStatusText
```

**Fluxo Atual (SALÃO)**:
```text
enviarPedido()
↓
out.id (solicitacao_id)
↓
pedido.id = out.id
↓
❌ NÃO salva tracking para SALÃO
↓
showPostOrderScreen() [sem parâmetros]
↓
❌ NÃO cria infoDiv
↓
❌ NÃO inicia polling KDS
↓
Nada acontece
```

**Fluxo Atual (DELIVERY)**:
```text
enviarPedido()
↓
out.id e out.token
↓
Salva tracking em localStorage
↓
showPostOrderScreen() [sem parâmetros]
↓
Lê tracking do localStorage
↓
startStatusPublicoPolling()
↓
/api/public/pedidos/<id>/status?token=Y
↓
Atualiza #postOrderStatusPublico
```

---

## 4. DEPENDÊNCIAS DO POLLING

### 4.1 Dependências do Polling KDS Legado

| Dependência | Tipo | Localização | Situação |
|-------------|------|-------------|----------|
| `solicitacao_id` | Dado | `pedidoInfo.solicitacao_id` | ❌ NÃO disponível no app.js atual |
| `mesa` | Dado | `pedidoInfo.mesa` | ⚠️ Disponível em `state.mesa` |
| `token` | Dado | `state.token` | ⚠️ Disponível em `state.token` |
| `_kdsPollingTimer` | Variável | Global (index.html:1729) | ❌ NÃO existe no app.js |
| `pollKdsStatus()` | Função | Closure em `showPostOrderScreen` | ❌ NÃO existe no app.js |
| `#kdsStatusArea` | Elemento UI | Criado dinamicamente | ❌ NÃO existe no HTML |
| `#kdsStatusText` | Elemento UI | Criado dinamicamente | ❌ NÃO existe no HTML |
| `/api/solicitacoes/<id>/kds-status` | Endpoint | Backend | ✅ COMPATÍVEL (confirmado em auditoria anterior) |
| `fetch()` | API nativa | Navegador | ✅ Disponível |
| `setInterval()` | API nativa | Navegador | ✅ Disponível |
| `clearInterval()` | API nativa | Navegador | ✅ Disponível |

### 4.2 Classificação das Dependências

| Componente | Situação | Migrar? |
|------------|----------|---------|
| `solicitacao_id` | B — precisa ser migrado (tracking para SALÃO) | ✅ SIM |
| `mesa` | A — já existe em `state.mesa` | ❌ NÃO |
| `token` | A — já existe em `state.token` | ❌ NÃO |
| `_kdsPollingTimer` | B — precisa ser migrado | ✅ SIM |
| `pollKdsStatus()` | B — precisa ser migrado | ✅ SIM |
| `#kdsStatusArea` | B — precisa ser migrado (ou criar elemento estático) | ✅ SIM |
| `#kdsStatusText` | B — precisa ser migrado (ou criar elemento estático) | ✅ SIM |
| Endpoint kds-status | C — existe no backend | ❌ NÃO |
| fetch, setInterval, clearInterval | A — já existe | ❌ NÃO |

---

## 5. COMPATIBILIDADE COM O BACKEND ATUAL

### 5.1 Endpoint `/api/solicitacoes/<id>/kds-status`

**Verificação**: Confirmado em auditoria anterior (AUDITORIA_KDS_STATUS_FRONTEND.md)

**Método**: GET  
**Parâmetros**:
- `mesa`: número da mesa
- `token`: token de autenticação da mesa

**Resposta**:
```json
{
    "status": "AGUARDANDO" | "EM_PREPARO" | "PRONTO"
}
```

**Autenticação**: Validação via `validate_table_token()` (core.py:863)

**Conclusão**: **COMPATÍVEL** — O código legado espera exatamente o que o backend atual fornece.

---

## 6. O QUE FOI PERDIDO NA MIGRAÇÃO

### 6.1 Informação Perdida

**Dado crítico perdido**: `solicitacao_id` para pedidos de SALÃO

**Como foi perdido**:
1. Legado: Passado como parâmetro para `showPostOrderScreen(pedidoInfo)`
2. Atual: Extraído em `enviarPedido()` mas não salvo em tracking para SALÃO
3. Atual: `showPostOrderScreen()` não recebe parâmetros

**Consequência**: O `solicitacao_id` não está disponível quando `showPostOrderScreen()` é executado para pedidos de SALÃO.

### 6.2 Funcionalidade Perdida

**Funcionalidade perdida**: Polling de Status KDS para pedidos de SALÃO

**Como foi perdida**:
1. Legado: `pollKdsStatus()` definida como closure dentro de `showPostOrderScreen(pedidoInfo)`
2. Atual: `showPostOrderScreen()` não possui nenhuma lógica de polling para SALÃO
3. Atual: Sistema de polling atual (`statusPublicoTimer`) funciona apenas para DELIVERY

**Consequência**: Pedidos de SALÃO não recebem atualização de status da cozinha.

### 6.3 UI Perdida

**Elementos perdidos**:
- `#kdsStatusArea`: Container do status KDS
- `#kdsStatusText`: Texto do status KDS
- `div` com `data-salao-info="true"`: Informações do pedido (cliente, mesa, tipo)

**Como foi perdido**:
1. Legado: Criados dinamicamente dentro de `showPostOrderScreen(pedidoInfo)`
2. Atual: `showPostOrderScreen()` não cria esses elementos
3. Atual: Elemento `#postOrderStatusPublico` existe mas é usado apenas para DELIVERY

**Consequência**: Não há elementos UI para exibir status KDS de pedidos de SALÃO.

---

## 7. O QUE DEVE SER MIGRADO

### 7.1 Conjunto Mínimo de Componentes

**Componente 1: Tracking para SALÃO**

- **O que**: Salvar `solicitacao_id` em tracking para pedidos de SALÃO
- **Onde**: Em `enviarPedido()` do app.js
- **Como**: Estender a lógica de `saveTrackingPedido()` para incluir SALÃO
- **Dados necessários**:
  ```javascript
  {
      id: out.id,              // solicitacao_id
      kind: "SALAO",
      mesa: state.mesa,
      token: state.token
  }
  ```

**Componente 2: Adaptar `showPostOrderScreen()`**

- **O que**: Adicionar parâmetro `pedidoInfo` (opcional) ou ler do tracking
- **Onde**: Em `showPostOrderScreen()` do app.js
- **Como**: 
  - Opção A: Adicionar parâmetro opcional `pedidoInfo`
  - Opção B: Ler tracking do localStorage (se existir)
- **Dados necessários**: `solicitacao_id`, `mesa`, `token`

**Componente 3: Variável de Timer KDS**

- **O que**: Adicionar `_kdsPollingTimer` ou usar `state.kdsPollingTimer`
- **Onde**: Escopo global do app.js
- **Como**: Declarar como `let _kdsPollingTimer = null;` ou adicionar ao `state`

**Componente 4: Função `pollKdsStatus()`**

- **O que**: Migrar lógica de polling KDS
- **Onde**: Como função separada ou closure em `showPostOrderScreen()`
- **Como**: 
  - Endpoint: `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`
  - Intervalo: 2500ms
  - Cancelamento: Quando status === "PRONTO"

**Componente 5: Elementos UI**

- **O que**: Adicionar elementos para exibir status KDS de SALÃO
- **Onde**: No HTML (`index.html`) ou criar dinamicamente
- **Como**: 
  - Opção A: Adicionar elementos estáticos `#kdsStatusArea` e `#kdsStatusText` ao HTML
  - Opção B: Criar dinamicamente (como no legado)
  - Opção C: Reutilizar `#postOrderStatusPublico` com lógica condicional

**Componente 6: Condicional de Tipo de Pedido**

- **O que**: Diferenciar comportamento entre SALÃO e DELIVERY
- **Onde**: Em `showPostOrderScreen()` do app.js
- **Como**: 
  - Se `kind === "SALAO"`: Usar polling KDS com endpoint `/api/solicitacoes/<id>/kds-status`
  - Se `kind === "DELIVERY"`: Usar polling status público existente com endpoint `/api/public/pedidos/<id>/status`

---

## 8. O QUE NÃO DEVE SER MIGRADO

### 8.1 Lista Explícita

- ❌ **Reativar `legacyInlineScript` inteiro**: Proibido por decisão arquitetural
- ❌ **Alterar `type="text/plain"`**: Proibido por decisão arquitetural
- ❌ **Copiar ~1600 linhas do legado**: Apenas funcionalidade KDS é necessária
- ❌ **Funções não relacionadas a KDS**: Ex: `_mapsEmbedUrl`, `setDeliveryMapsUrl`, `usarMinhaLocalizacao`
- ❌ **Lógica de catálogo**: Já migrada para app.js
- ❌ **Lógica de delivery**: Já existe no app.js (`_deliveryLeafletMap`, etc.)
- ❌ **Listeners antigos**: Já migrados para app.js
- ❌ **Estruturas duplicadas**: App.js já possui versões de muitas funções
- ❌ **Funções de modal**: Já existem no app.js
- ❌ **Funções de carrinho**: Já existem no app.js
- ❌ **Funções de UI geral**: Já existem no app.js

### 8.2 Justificativa

O `legacyInlineScript` contém código antigo que foi migrado para `app.js`. Reativá-lo inteiro causaria:
- Duplicação de funções
- Conflitos de escopo
- Manutenção desnecessária
- Dificuldade de debug

Apenas a funcionalidade KDS para SALÃO não foi migrada e precisa ser adicionada.

---

## 9. RISCOS DA FUTURA IMPLEMENTAÇÃO

### 9.1 Riscos Identificados

**Risco 1: Conflito de Timers**

- **Descrição**: Dois timers simultâneos (`_kdsPollingTimer` e `state.statusPublicoTimer`)
- **Condição**: Se ambos os sistemas forem ativados indevidamente
- **Mitigação**: Garantir que apenas um timer esteja ativo por tipo de pedido (SALÃO usa KDS, DELIVERY usa status público)

**Risco 2: Conflito de UI**

- **Descrição**: Dois elementos de status sendo atualizados simultaneamente
- **Condição**: Se `#kdsStatusArea` e `#postOrderStatusPublico` forem usados juntos
- **Mitigação**: Usar condicional baseado em `kind` para mostrar apenas um elemento

**Risco 3: Sobrescrita de Função**

- **Descrição**: Duas definições de `showPostOrderScreen()` em conflito
- **Condição**: Se legado for reativado indevidamente
- **Mitigação**: Manter `type="text/plain"` e não reativar legado

**Risco 4: Perda de Funcionalidade DELIVERY**

- **Descrição**: Alteração indevida quebrar polling de DELIVERY
- **Condição**: Se condicional de tipo não for implementada corretamente
- **Mitigação**: Testar ambos os tipos de pedido após implementação

**Risco 5: Incompatibilidade de Endpoint**

- **Descrição**: Endpoint KDS não funcionar com token de mesa
- **Condição**: Se validação do backend mudou
- **Mitigação**: Confirmar compatibilidade com backend atual (já confirmado em auditoria anterior)

### 9.2 Risco de Quebrar Funcionalidades Atuais

**Probabilidade**: BAIXA a MÉDIA

**Justificativa**:
- A funcionalidade DELIVERY já usa um sistema separado (`statusPublicoTimer`)
- A implementação KDS será condicional (apenas para SALÃO)
- O sistema de tracking já existe e funciona para DELIVERY
- Os elementos UI são separados (`#postOrderStatusPublico` para DELIVERY, novos elementos para SALÃO)

**Mitigação**:
- Implementar condicional estrita baseada em `kind`
- Testar ambos os tipos de pedido
- Não alterar lógica existente de DELIVERY

---

## 10. ARQUITETURA FUTURA RECOMENDADA

### 10.1 Desenho da Solução

```
index.html
    ↓
Estrutura HTML (adicionar #kdsStatusArea e #kdsStatusText para SALÃO)
    ↓
assets/app.js
    ↓
enviarPedido()
    ↓
SALÃO: Salvar tracking com solicitacao_id, mesa, token
DELIVERY: Salvar tracking com access_token (já existe)
    ↓
showPostOrderScreen(pedidoInfo?) [parâmetro opcional]
    ↓
SALÃO:
    - Ler tracking do localStorage
    - Criar/mostrar #kdsStatusArea e #kdsStatusText
    - Iniciar pollKdsStatus() com _kdsPollingTimer
    - Endpoint: /api/solicitacoes/<id>/kds-status?mesa=X&token=Y
DELIVERY:
    - Ler tracking do localStorage (já existe)
    - Mostrar #postOrderStatusPublico (já existe)
    - Iniciar startStatusPublicoPolling() com state.statusPublicoTimer (já existe)
    - Endpoint: /api/public/pedidos/<id>/status?token=Y
```

### 10.2 Componentes da Arquitetura

**Estrutura de Dados**:
```javascript
// tracking (localStorage)
{
    id: solicitacao_id,
    kind: "SALAO" | "DELIVERY",
    // Para SALÃO:
    mesa: number,
    token: string (token de mesa)
    // Para DELIVERY:
    access_token: string (token público),
    tipo_entrega: "DELIVERY" | "RETIRADA"
}
```

**Estado**:
```javascript
state.kdsPollingTimer = null;  // Novo: para SALÃO
state.statusPublicoTimer = null;  // Existente: para DELIVERY
```

**Funções**:
```javascript
// Novas ou adaptadas:
showPostOrderScreen(pedidoInfo?)  // Adaptar para aceitar parâmetro opcional
pollKdsStatus()  // Nova: para SALÃO
startKdsPolling()  // Nova: para SALÃO
stopKdsPolling()  // Nova: para SALÃO

// Existentes (não alterar):
refreshStatusPublicoNaTela()  // Para DELIVERY
startStatusPublicoPolling()  // Para DELIVERY
stopStatusPublicoPolling()  // Para DELIVERY
```

**UI**:
```html
<!-- Existente (DELIVERY) -->
<div id="postOrderStatusPublico"></div>

<!-- Novo (SALÃO) -->
<div id="kdsStatusArea" style="display:none">
    <div>Status:</div>
    <div id="kdsStatusText"></div>
</div>
```

---

## 11. PLANO DE IMPLEMENTAÇÃO

### PASSO 1 — Adicionar Elementos UI ao HTML

- Adicionar `#kdsStatusArea` e `#kdsStatusText` ao `index.html`
- Posicionar dentro de `#postOrderScreen`
- Estilo similar ao legado

### PASSO 2 — Estender Sistema de Tracking para SALÃO

- Modificar `enviarPedido()` em app.js
- Salvar tracking para SALÃO (atualmente salva apenas para DELIVERY)
- Incluir: `id`, `kind`, `mesa`, `token`

### PASSO 3 — Adaptar `showPostOrderScreen()`

- Adicionar parâmetro opcional `pedidoInfo` OU ler do tracking
- Implementar condicional baseado em `kind`
- Para SALÃO: Mostrar `#kdsStatusArea` e `#kdsStatusText`
- Para DELIVERY: Manter lógica existente (`#postOrderStatusPublico`)

### PASSO 4 — Implementar `pollKdsStatus()`

- Criar função `pollKdsStatus()` em app.js
- Endpoint: `/api/solicitacoes/${id}/kds-status?mesa=${mesa}&token=${token}`
- Atualizar `#kdsStatusText` com base no status
- Cancelar polling quando status === "PRONTO"

### PASSO 5 — Implementar Timer KDS

- Adicionar `state.kdsPollingTimer` ao app.js
- Criar `startKdsPolling()` e `stopKdsPolling()`
- Iniciar em `showPostOrderScreen()` para SALÃO
- Limpar em `showMainScreen()`

### PASSO 6 — Condicional de Tipo de Pedido

- Em `showPostOrderScreen()`:
  - Se `kind === "SALAO"`: Usar sistema KDS
  - Se `kind === "DELIVERY"`: Usar sistema status público existente
- Garantir que apenas um timer esteja ativo

### PASSO 7 — Teste

- Testar pedido de SALÃO: Verificar polling KDS
- Testar pedido de DELIVERY: Verificar polling status público
- Verificar que não há conflito de timers
- Verificar que não há conflito de UI

---

## 12. ALTERAÇÕES REALIZADAS

**NENHUMA.**

---

## CONCLUSÃO OBRIGATÓRIA

### A — O polling KDS legado pode ser migrado isoladamente?

**SIM.**

A funcionalidade KDS do legado é isolada e pode ser migrada independentemente do restante do código legado. As dependências são:
- Dados: `solicitacao_id`, `mesa`, `token` (já disponíveis em `state`)
- Endpoint: `/api/solicitacoes/<id>/kds-status` (já existe no backend)
- API nativa: `fetch`, `setInterval`, `clearInterval` (já disponíveis)
- UI: Elementos simples (`#kdsStatusArea`, `#kdsStatusText`)

### B — É necessário reativar o `legacyInlineScript` inteiro?

**NÃO.**

**Justificativa técnica**:
1. O `legacyInlineScript` contém ~1600 linhas de código, mas apenas ~50 linhas são relevantes para o KDS
2. A maior parte do código já foi migrada para `app.js` (catálogo, carrinho, modais, delivery, etc.)
3. Reativar o legado inteiro causaria duplicação de funções, conflitos de escopo e dificuldade de manutenção
4. A funcionalidade KDS pode ser implementada isoladamente no `app.js` com poucas linhas de código
5. A arquitetura atual baseada em `app.js` é mais limpa e sustentável

### C — Qual é o menor conjunto de alterações futuras?

1. **Adicionar elementos UI** ao HTML (`#kdsStatusArea`, `#kdsStatusText`)
2. **Estender tracking** para incluir SALÃO (salvar `solicitacao_id`, `mesa`, `token`)
3. **Adaptar `showPostOrderScreen()`** para aceitar parâmetro opcional ou ler do tracking
4. **Implementar `pollKdsStatus()`** com endpoint `/api/solicitacoes/<id>/kds-status`
5. **Adicionar timer KDS** (`state.kdsPollingTimer`) com `startKdsPolling()` e `stopKdsPolling()`
6. **Implementar condicional** baseado em `kind` (SALÃO usa KDS, DELIVERY usa status público)

### D — Existe algum risco de quebrar funcionalidades atuais ao fazer essa migração?

**Risco BAIXO a MÉDIO.**

**Justificativa**:
- A funcionalidade DELIVERY usa um sistema separado (`statusPublicoTimer`, endpoint diferente, UI diferente)
- A implementação será condicional baseada em `kind`, garantindo isolamento
- O sistema de tracking já existe e funciona para DELIVERY
- Os elementos UI são separados (`#postOrderStatusPublico` para DELIVERY, novos elementos para SALÃO)

**Mitigação**:
- Implementar condicional estrita
- Testar ambos os tipos de pedido após implementação
- Não alterar lógica existente de DELIVERY

### E — A implementação futura deve permanecer exclusivamente em `assets/app.js`?

**SIM.**

**Justificativa**:
1. A arquitetura atual baseada em `app.js` é limpa e sustentável
2. Manter a implementação em `app.js` evita duplicação de código
3. O `legacyInlineScript` deve permanecer como `type="text/plain"` (histórico)
4. A funcionalidade KDS é pequena e cabe naturalmente no `app.js`
5. Manter tudo em `app.js` facilita manutenção e debug futuros

---

**FIM DO RELATÓRIO**