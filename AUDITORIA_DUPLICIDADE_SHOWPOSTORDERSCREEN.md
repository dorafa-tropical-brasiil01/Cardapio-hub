# RELATÓRIO DE AUDITORIA CIRÚRGICA — DUPLICIDADE DE `showPostOrderScreen()`

**Projeto**: DoRafaPDV — Cardápio Online  
**Data**: 2026-07-31  
**Tipo**: Auditoria Cirúrgica — Análise de Escopo e Sobrescrita  
**Objetivo**: Determinar se a duplicidade de `showPostOrderScreen()` é a causa da ausência de chamadas ao endpoint `/api/solicitacoes/<id>/kds-status`

---

## 1. DEFINIÇÕES ENCONTRADAS

### 1.1 Definições

| Arquivo | Linha | Tipo | Assinatura | Escopo | Polling KDS |
|--------|------:|------|-----------|--------|------------|
| index.html | 1731 | DEFINIÇÃO | `function showPostOrderScreen(pedidoInfo)` | Global (script inline) | ✅ SIM |
| assets/app.js | 1226 | DEFINIÇÃO | `function showPostOrderScreen()` | Global (script externo) | ❌ NÃO |

### 1.2 Chamadas

| Arquivo | Linha | Contexto | Argumento | Tipo |
|--------|------:|----------|-----------|------|
| index.html | 1679 | `enviarPedido()` | `{ kind, mesa, cliente_nome, solicitacao_id: out.id }` | CHAMADA |
| index.html | 2608 | `refreshCatalogo()` | Nenhum | CHAMADA |
| assets/app.js | 1174 | `enviarPedido()` | Nenhum | CHAMADA |
| assets/app.js | 2139 | `refreshCatalogo()` | Nenhum | CHAMADA |

---

## 2. CHAMADAS ENCONTRADAS

### 2.1 Chamada Principal (Fluxo de Envio de Pedido)

**Arquivo**: `index.html`  
**Linha**: 1679  
**Função**: `enviarPedido()`  
**Código**:
```javascript
showPostOrderScreen({ kind, mesa: isSalao ? state.mesa : null, cliente_nome: String(state.clientName || "").trim(), solicitacao_id: out.id });
```

**Argumento**: Objeto com propriedades `kind`, `mesa`, `cliente_nome`, `solicitacao_id`

### 2.2 Chamadas Secundárias

**index.html:2608** (em `refreshCatalogo()`)
```javascript
showPostOrderScreen();
```
- **Argumento**: Nenhum
- **Contexto**: Refresh do catálogo quando `state.postOrderActive` é true

**assets/app.js:1174** (em `enviarPedido()`)
```javascript
showPostOrderScreen();
```
- **Argumento**: Nenhum
- **Contexto**: Após envio bem-sucedido do pedido

**assets/app.js:2139** (em `refreshCatalogo()`)
```javascript
showPostOrderScreen();
```
- **Argumento**: Nenhum
- **Contexto**: Refresh do catálogo quando `state.postOrderActive` é true

---

## 3. ORDEM DE CARREGAMENTO

### 3.1 Estrutura do index.html

```html
<!-- Linha 1030 -->
<script src="/assets/app.js"></script>

<!-- Linha 1032-2677 -->
<script type="text/plain" id="legacyInlineScript">
    [Conteúdo JavaScript]
</script>
```

### 3.2 Análise do Script Externo

**Tag**: `<script src="/assets/app.js"></script>` (linha 1030)  
**Tipo**: Script clássico  
**Atributos**: 
- `src="/assets/app.js"`
- Sem `defer`
- Sem `async`
- Sem `type="module"`

**Comportamento**: Script clássico sem `defer` ou `async` é **executado imediatamente** durante o parsing do HTML, **bloqueando** o parsing até que o script seja baixado e executado.

### 3.3 Análise do Script Inline

**Tag**: `<script type="text/plain" id="legacyInlineScript">` (linha 1032)  
**Tipo**: `type="text/plain"`  
**Comportamento**: Scripts com `type="text/plain"` **NÃO são executados** pelo navegador. O conteúdo é tratado como texto puro e ignorado pelo parser JavaScript.

### 3.4 ⚠️ DESCOBERTA CRÍTICA

**O script com `type="text/plain"` NÃO é executado pelo navegador.**

Isso significa que:
- O JavaScript dentro de `<script type="text/plain" id="legacyInlineScript">` é **ignorado completamente**
- A definição de `showPostOrderScreen(pedidoInfo)` com polling KDS (linha 1731) **NÃO é executada**
- A única definição que é executada é a de `assets/app.js` (linha 1226)

### 3.5 Ordem Efetiva de Execução

```text
1. index.html começa a ser parsed
2. Linha 1030: <script src="/assets/app.js"></script> é encontrado
3. app.js é baixado e executado imediatamente
4. app.js define showPostOrderScreen() [SEM parâmetro, SEM polling] (linha 1226)
5. Linha 1032: <script type="text/plain" id="legacyInlineScript"> é encontrado
6. Conteúdo é ignorado pelo navegador (type="text/plain")
7. Linha 2677: </script> fecha o script inline
8. </body> fecha o documento
9. JavaScript continuamente executado (se houver mais scripts)
```

---

## 4. ESCOPO

### 4.1 Definição em index.html (Linha 1731)

**Escopo**: Script inline com `type="text/plain"`  
**Status**: **NÃO EXECUTADO**  
**Acessibilidade**: Nenhuma (conteúdo ignorado pelo navegador)

### 4.2 Definição em assets/app.js (Linha 1226)

**Escopo**: Script externo clássico  
**Status**: **EXECUTADO**  
**Acessibilidade**: Global (window.showPostOrderScreen)

---

## 5. SOBRESCRITA

### 5.1 Existe Sobrescrita?

**RESPOSTA**: **NÃO**

### 5.2 Explicação

**A definição com polling KDS em index.html NÃO é executada** porque está dentro de um script com `type="text/plain"`, que é ignorado pelo navegador.

Portanto:
- A única definição de `showPostOrderScreen()` que é executada é a de `assets/app.js`
- Não há sobrescrita porque a definição com polling nunca é avaliada
- A definição em app.js permanece como a única versão disponível

---

## 6. IMPLEMENTAÇÃO EFETIVAMENTE ASSOCIADA AO FLUXO

### 6.1 Qual Função é Utilizada

**RESPOSTA**: A versão de `assets/app.js` (linha 1226)

### 6.2 Características da Versão Executada

- **Assinatura**: `function showPostOrderScreen()` (sem parâmetros)
- **Recebe pedidoInfo**: ❌ NÃO
- **Usa solicitacao_id**: ❌ NÃO
- **Usa state.token**: ❌ NÃO
- **Usa state.mesa**: ❌ NÃO
- **Cria polling**: ❌ NÃO
- **Usa setInterval**: ❌ NÃO
- **Chama pollKdsStatus**: ❌ NÃO
- **Chama kds-status**: ❌ NÃO
- **Atualiza status KDS**: ❌ NÃO

### 6.3 Incompatibilidade com a Chamada Principal

**Problema Crítico**: A chamada principal em `index.html:1679` é:

```javascript
showPostOrderScreen({ kind, mesa: isSalao ? state.mesa : null, cliente_nome: String(state.clientName || "").trim(), solicitacao_id: out.id });
```

Porém a função disponível é:

```javascript
function showPostOrderScreen()  // Sem parâmetros
```

**Resultado**: O parâmetro `pedidoInfo` é **ignorado** porque a função não espera nenhum parâmetro.

---

## 7. IMPACTO NO POLLING KDS

### 7.1 A Duplicidade Explica a Ausência da Chamada?

**RESPOSTA**: **NÃO**

### 7.2 Explicação

A ausência de chamadas ao endpoint `/api/solicitacoes/<id>/kds-status` é explicada por:

1. **A definição com polling KDS nunca é executada** (está em script type="text/plain")
2. **A definição executada não possui lógica de polling KDS** (versão de app.js)
3. **A chamada principal passa um parâmetro que é ignorado** pela função executada

Portanto, o polling KDS nunca inicia porque:
- A função que deveria iniciá-lo não é executada
- A função que é executada não contém essa lógica
- O parâmetro com `solicitacao_id` é perdido

---

## 8. HIPÓTESES H1–H6

### H1 — Existem duas definições de `showPostOrderScreen`

**Classificação**: **CONFIRMADA** (mas com correção técnica)

**Correção**: Existem duas definições no código fonte, mas **apenas uma é executada**.

### H2 — As duas definições estão no mesmo escopo conflitante

**Classificação**: **DESCARTADA**

**Explicação**: A definição em index.html está em script `type="text/plain"` e não é executada, então não há conflito de escopo.

### H3 — A definição sem polling pode sobrescrever a definição com polling

**Classificação**: **DESCARTADA**

**Explicação**: A definição com polling nunca é executada, então não pode sobrescrever nada.

### H4 — A chamada do pedido utiliza a definição sem polling

**Classificação**: **CONFIRMADA**

**Explicação**: A chamada do pedido utiliza a definição de `assets/app.js` (única versão executada), que não possui polling KDS.

### H5 — A duplicidade explica a ausência de chamadas para `kds-status`

**Classificação:** **FORTEMENTE SUSTENTADA (com correção técnica)**

**Correção**: Não é a "duplicidade" em si, mas sim o fato de que **a definição com polling KDS está em um script que não é executado** (`type="text/plain"`).

### H6 — Existe outra causa mais provável

**Classificação**: **SIM**

**Causa**: A definição com polling KDS está em um script `type="text/plain"` e, portanto, nunca é executada pelo navegador.

---

## 9. CAUSA MAIS PROVÁVEL

**A definição de `showPostOrderScreen()` com polling KDS está dentro de um script `type="text/plain"` e, consequentemente, nunca é executada pelo navegador.**

**Evidências**:

1. **Script type="text/plain"** (index.html:1032): Scripts com `type="text/plain"` são ignorados pelo navegador e não são executados
2. **Conteúdo ignorado**: Todo o JavaScript de index.html (linhas 1032-2677) está dentro deste script e não é executado
3. **Definição não executada**: A função `showPostOrderScreen(pedidoInfo)` com polling KDS (linha 1731) nunca é avaliada
4. **Versão executada**: A única versão executada é a de `assets/app.js` (linha 1226), que não possui polling KDS
5. **Incompatibilidade de assinatura**: A chamada principal passa `pedidoInfo` como parâmetro, mas a função executada não recebe parâmetros
6. **Ausência de logs**: Os console.log da versão com polling não aparecem porque essa versão nunca é executada
7. **Ausência de chamadas kds-status**: O endpoint nunca é chamado porque a função que deveria chamar não é executada

---

## 10. PRÓXIMO TESTE

**Alterar o tipo do script inline de `type="text/plain"` para `type="text/javascript"`** na linha 1032 do `index.html`.

Isso fará com que o JavaScript inline seja executado pelo navegador, permitindo que a definição de `showPostOrderScreen()` com polling KDS seja avaliada e sobrescreva a definição de `app.js`.

** Não executar este teste sem autorização.**

---

## 11. ALTERAÇÕES REALIZADAS

**NENHUMA.**

---

## CONCLUSÃO

A duplicidade de `showPostOrderScreen()` **NÃO é a causa direta** do problema. A causa real é que **a definição com polling KDS está dentro de um script `type="text/plain"`** que é completamente ignorado pelo navegador. 

A versão executada é a de `assets/app.js`, que não possui lógica de polling KDS. Além disso, há uma incompatibilidade de assinatura: a chamada principal passa `pedidoInfo` como parâmetro, mas a função executada não recebe parâmetros.

A correção é simples: alterar `type="text/plain"` para `type="text/javascript"` na linha 1032 do `index.html`, o que fará com que a versão com polling KDS seja executada e sobrescreva a versão de `app.js`.