# RELATÓRIO DE AUDITORIA DE DECISÃO DE IMPLEMENTAÇÃO

**Projeto**: DoRafaPDV — Cardápio Online  
**Data**: 2026-07-31  
**Tipo**: Auditoria de Decisão — Análise de Alternativas de Implementação  
**Objetivo**: Resolver decisões técnicas sobre a implementação do Status KDS para pedidos SALÃO

---

## 1. RESPOSTA À QUESTÃO A

**O objeto `pedido` pode ser passado diretamente?**

**RESPOSTA**: **SIM**

**Justificativa**:

1. **O objeto `pedido` é criado imediatamente antes da chamada** (app.js:1132-1154)
2. **Todos os dados necessários estão presentes no objeto**:
   - `pedido.id` → solicitacao_id
   - `pedido.kind` → "SALAO" ou "DELIVERY"
   - `pedido.mesa` → número da mesa (para SALÃO)
   - `pedido.token` → token de autenticação (para SALÃO)
3. **O objeto não é utilizado após a criação** (apenas para montar os dados)
4. **A chamada atual é imediata**: `showPostOrderScreen()` é chamado na linha 1174, logo após `clearPedidoAtual()` na linha 1169
5. **Não há motivo técnico que impeça passar o objeto**: A função atual não recebe parâmetros, mas isso pode ser alterado
6. **Mantém compatibilidade com DELIVERY**: O objeto contém todos os dados necessários para ambos os tipos

**Conclusão**: O fluxo direto `showPostOrderScreen(pedido)` é tecnicamente viável e é a solução mais simples. Não há necessidade de `localStorage` para o transporte dos dados.

---

## 2. RESPOSTA À QUESTÃO B

**SALÃO precisa de localStorage?**

**RESPOSTA**: **NÃO (DESNCESSÁRIO PARA A CORREÇÃO)**

**Justificativa**:

### Análise do Sistema de Tracking Atual

**Funções**:
- `saveTrackingPedido(tracking)` (app.js:976-978)
- `getTrackingPedido()` (app.js:980-987)
- `clearTrackingPedido()` (app.js:989-993)

**Uso atual**:
- Salvo em `enviarPedido()` (app.js:1156-1165) **apenas para DELIVERY**
- Lido em `showPostOrderScreen()` (app.js:1286) para DELIVERY
- Lido em `refreshStatusPublicoNaTela()` (app.js:1325) para DELIVERY
- Limpo em `showMainScreen()` (app.js:1193)

**Propósito**: Acompanhamento de pedidos DELIVERY após envio, permitindo polling de status público

### Análise de Necessidade para SALÃO

**Cenário atual do fluxo SALÃO**:
1. Cliente faz pedido
2. Pedido é enviado
3. Tela pós-pedido é exibida
4. Cliente clicará em "Voltar ao Cardápio"
5. Cliente pode fazer novo pedido imediatamente

**Pergunta**: O cliente precisa sair da tela e retornar posteriormente ao pedido SALÃO?

**Resposta**: **NÃO há evidência de requisito de persistência**

**Evidências**:
1. Comentário no código (app.js:1167-1168): "Fluxo simplificado: após enviar, permite novo pedido imediatamente. O pedido NÃO some do PDV; apenas não mantemos 'pedido atual' nesta tela."
2. O sistema atual não salva `pedido` em localStorage para SALÃO
3. Não há função de "recuperar pedido anterior" para SALÃO
4. O foco é permitir novo pedido imediato, não persistência

**Classificação**:
- **tracking SALÃO**: C — Desnecessário para a correção
- **solicitacao_id SALÃO**: C — Desnecessário para a correção (pode ser passado via parâmetro)
- **mesa SALÃO**: C — Desnecessário para a correção (já está em `state.mesa`)
- **token SALÃO**: C — Desnecessário para a correção (já está em `state.token`)

**Conclusão**: O `localStorage` não é necessário para implementar o polling KDS de SALÃO. O parâmetro direto para `showPostOrderScreen(pedido)` é suficiente. O sistema de tracking pode permanecer exclusivo para DELIVERY.

---

## 3. RESPOSTA À QUESTÃO C

**Qual a melhor integração da UI KDS?**

**RESPOSTA**: **CRIAR ELEMENTOS ESPECÍFICOS PARA SALÃO (NOVOS)**

**Justificativa**:

### Análise da Interface Atual

**Elemento existente**: `#postOrderStatusPublico` (index.html:1008)

**Características**:
- Estilo: Fundo verde, borda verde, texto verde escuro
- Uso atual: Apenas para DELIVERY
- Endpoint: `/api/public/pedidos/<id>/status`
- Dados: `status_publico` (ENVIADO, ACEITO, PREPARANDO, PRONTO, EM_ENTREGA, ENTREGUE)
- Autenticação: `access_token` (token público)

### Diferenças entre SALÃO e DELIVERY

| Aspecto | SALÃO (KDS) | DELIVERY (Status Público) |
|---------|-------------|---------------------------|
| Endpoint | `/api/solicitacoes/<id>/kds-status` | `/api/public/pedidos/<id>/status` |
| Autenticação | `state.token` (token de mesa) | `access_token` (token público) |
| Parâmetros | `mesa`, `token` | `token` |
| Status | AGUARDANDO, EM_PREPARO, PRONTO | ENVIADO, ACEITO, PREPARANDO, PRONTO, EM_ENTREGA, ENTREGUE |
| Fonte | KDS (cozinha) | Backend (status público) |
| Apresentação | Info adicional (cliente, mesa, tipo) | Apenas status |

### Avaliação de Alternativas

**Alternativa 1: Reutilizar `#postOrderStatusPublico`**
- **Problema**: Os estilos são específicos para DELIVERY (fundo verde)
- **Problema**: O legado criava elementos dinâmicos com informações adicionais (cliente, mesa, tipo)
- **Problema**: Os status são diferentes (KDS tem 3 estados, status público tem 6)
- **Risco**: Confusão visual entre os dois tipos de pedido

**Alternativa 2: Criar elementos específicos para SALÃO**
- **Vantagem**: Separação clara entre os dois fluxos
- **Vantagem**: Permite personalização específica para SALÃO (cliente, mesa, tipo)
- **Vantagem**: Evita conflito de estilos e comportamentos
- **Vantagem**: Segue o padrão do legado (que criava elementos dinâmicos)
- **Custo**: Adicionar 2 elementos estáticos ao HTML

**Alternativa 3: Criar elementos dinamicamente (como legado)**
- **Vantagem**: Não altera HTML
- **Problema**: Mais complexo de manter
- **Problema**: Difícil de debug
- **Problema**: Diverge do padrão atual do app.js (que usa elementos estáticos)

**Conclusão**: A melhor alternativa é **criar elementos estáticos específicos para SALÃO** no HTML (`#kdsStatusArea` e `#kdsStatusText`), seguindo o padrão atual do app.js de usar elementos estáticos ao invés de criação dinâmica.

---

## 4. DECISÃO SOBRE TIMER

**RESPOSTA**: **SEGUIR O PADRÃO ATUAL DO app.js (state.timer)**

**Justificativa**:

### Padrão Atual do app.js

**Timer existente**: `state.statusPublicoTimer` (app.js:1351-1365)

**Características**:
- Armazenado no objeto `state`
- Gerenciado por `startStatusPublicoPolling()` e `stopStatusPublicoPolling()`
- Limpo em `showMainScreen()` (app.js:1192)

### Análise de Alternativas

**Alternativa 1: Variável global `_kdsPollingTimer` (legado)**
- **Problema**: Diverge do padrão arquitetural atual
- **Problema**: Mais difícil de gerenciar estado global
- **Problema**: Menos consistente com o restante do app.js

**Alternativa 2: `state.kdsPollingTimer` (padrão app.js)**
- **Vantagem**: Consistente com `state.statusPublicoTimer`
- **Vantagem**: Centralizado no objeto `state`
- **Vantagem**: Mais fácil de debug e gerenciar
- **Vantagem**: Segue o padrão arquitetural estabelecido

**Alternativa 3: Reutilizar `state.statusPublicoTimer`**
- **Problema**: Conflito entre SALÃO e DELIVERY
- **Problema**: Difícil gerenciar qual endpoint está sendo pollado
- **Risco**: Bug se ambos os tipos forem ativados

**Conclusão**: Criar `state.kdsPollingTimer` seguindo o padrão arquitetural atual. Isso garante consistência e evita conflitos.

---

## 5. DECISÃO SOBRE POLLING

**RESPOSTA**: **SEGUIR O PADRÃO ATUAL DO app.js (adaptado para KDS)**

**Justificativa**:

### Padrão Atual do app.js (DELIVERY)

**Funções**:
- `refreshStatusPublicoNaTela()` (app.js:1324-1349) — função de polling
- `startStatusPublicoPolling()` (app.js:1351-1358) — inicia timer
- `stopStatusPublicoPolling()` (app.js:1360-1365) — para timer
- `renderStatusPublicoNaTela()` (app.js:1306-1322) — atualiza UI

**Características**:
- Função de polling separada (`refreshStatusPublicoNaTela`)
- Funções de start/stop independentes
- Função de renderização separada
- Timer em `state.statusPublicoTimer`
- Intervalo: 2500ms

### Padrão Legado (SALÃO)

**Funções**:
- `pollKdsStatus()` — função de polling (closure dentro de `showPostOrderScreen`)
- `setInterval` direto dentro de `showPostOrderScreen`
- `clearInterval` direto quando status é "PRONTO"
- Timer em `_kdsPollingTimer` (variável global)
- Intervalo: 2500ms

### Avaliação

**Opção A: Seguir exatamente o padrão existente**
- Criar `refreshKdsStatusNaTela()`, `startKdsPolling()`, `stopKdsPolling()`, `renderKdsStatusNaTela()`
- **Vantagem**: Consistência total
- **Custo**: 4 funções

**Opção B: Adaptar parcialmente**
- Criar `pollKdsStatus()` (como legado) + `startKdsPolling()` + `stopKdsPolling()`
- **Vantagem**: Menos funções
- **Custo**: 3 funções

**Opção C: Manter o padrão legado**
- Closure dentro de `showPostOrderScreen`
- **Problema**: Diverge do padrão atual
- **Problema**: Mais difícil de testar e debug

**Opção D: Solução híbrida**
- Reutilizar `state.kdsPollingTimer`
- Criar `pollKdsStatus()` como função separada (não closure)
- Criar `startKdsPolling()` e `stopKdsPolling()`
- **Vantagem**: Balance entre simplicidade e padrão
- **Custo**: 3 funções

**Conclusão**: **Opção D (solução híbrida)** — Criar `pollKdsStatus()` como função separada (não closure) + `startKdsPolling()` + `stopKdsPolling()`, usando `state.kdsPollingTimer`. Isso mantém simplicidade (3 funções) enquanto segue o padrão arquitetural de timers em `state`.

---

## 6. DECISÃO SOBRE showPostOrderScreen

**RESPOSTA**: **ALTERAR PARA ACEITAR PARÂMETRO OPCIONAL**

**Justificativa**:

### Alternativas Avaliadas

**Alternativa A: `showPostOrderScreen(pedido)`**
- **Vantagem**: Mais simples
- **Vantagem**: Todos os dados disponíveis imediatamente
- **Vantagem**: Não depende de localStorage
- **Vantagem**: Funciona para ambos os tipos (SALÃO e DELIVERY)
- **Custo**: Alterar assinatura da função
- **Risco**: Precisa garantir compatibilidade com chamadas existentes sem parâmetro

**Alternativa B: `showPostOrderScreen({ id, kind, mesa, token })`**
- **Vantagem**: Mais explícito
- **Desvantagem**: Mais verboso
- **Desvantagem**: Duplicação de extração de dados
- **Custo**: Alterar assinatura + extração manual

**Alternativa C: `showPostOrderScreen()` + estado temporário**
- **Desvantagem**: Complexo
- **Desvantagem**: Mais difícil de debug
- **Desvantagem**: Estado global adicional
- **Custo**: Variável global temporária

**Alternativa D: `showPostOrderScreen()` + localStorage**
- **Desvantagem**: Necessidade de salvar tracking para SALÃO (desnecessário)
- **Desvantagem**: Mais complexo
- **Desvantagem**: Dependência de persistência
- **Custo**: Implementar tracking SALÃO

### Decisão

**Alternativa A** é a melhor porque:
1. É a mais simples
2. Não depende de localStorage (confirmado desnecessário na Questão B)
3. Usa o objeto `pedido` que já existe (confirmado viável na Questão A)
4. Pode ser feito compatível com chamadas existentes usando parâmetro opcional: `showPostOrderScreen(pedidoInfo?)`

**Implementação conceitual**:
```javascript
function showPostOrderScreen(pedidoInfo?) {
    // Se pedidoInfo foi passado, usa-o
    // Se não, lê do localStorage (para DELIVERY existente)
    // Isso garante compatibilidade com código existente
}
```

**Conclusão**: Alterar `showPostOrderScreen()` para aceitar parâmetro opcional `pedidoInfo`. Isso permite passagem direta do objeto `pedido` para SALÃO enquanto mantém compatibilidade com DELIVERY (que pode continuar usando localStorage se necessário).

---

## 7. DECISÃO SOBRE HTML

**RESPOSTA**: **ALTERAR (adicionar elementos estáticos para SALÃO)**

**Justificativa**:

### Elementos Necessários

**Elementos para SALÃO**:
- `#kdsStatusArea` — container do status KDS
- `#kdsStatusText` — texto do status KDS

**Localização**: Dentro de `#postOrderScreen` (index.html:1005-1013)

**Estilo**: Similar ao legado (fundo verde claro, borda verde, texto verde escuro)

### Razão para Alterar HTML

1. **Padrão atual do app.js**: Usa elementos estáticos (ex: `#postOrderStatusPublico`)
2. **Diferença de apresentação**: SALÃO precisa de informações adicionais (cliente, mesa, tipo)
3. **Separação de fluxos**: Elementos diferentes para SALÃO e DELIVERY evita conflito
4. **Simplicidade**: Elementos estáticos são mais simples que criação dinâmica

### Alternativa Não Escolhida

**Criação dinâmica** (como legado):
- Não altera HTML
- Mais complexo
- Diverge do padrão atual
- Mais difícil de debug

**Conclusão**: Adicionar elementos estáticos `#kdsStatusArea` e `#kdsStatusText` ao HTML é a solução mais simples e consistente com o padrão arquitetural atual.

---

## 8. ARQUIVOS QUE PRECISARÃO SER ALTERADOS

**RESPOSTA**: **2 ARQUIVOS**

| Arquivo | Classificação | Justificativa |
|---------|--------------|---------------|
| `Cardapio/assets/app.js` | OBRIGATÓRIO | Implementar polling KDS, adaptar `showPostOrderScreen()`, adicionar funções de polling |
| `Cardapio/index.html` | OBRIGATÓRIO | Adicionar elementos UI para SALÃO (`#kdsStatusArea`, `#kdsStatusText`) |
| `Cardapio/cardapio_app/core.py` | NÃO NECESSÁRIO | Endpoint KDS já existe e é compatível |
| `Cardapio/cardapio_app/routes.py` | NÃO NECESSÁRIO | Endpoint KDS já existe e é compatível |
| `Cardapio/cardapio_app/pg_store.py` | NÃO NECESSÁRIO | Funções KDS já existem e são compatíveis |

**Justificativa para não alterar backend**: O endpoint `/api/solicitacoes/<id>/kds-status` já existe e é compatível com o código legado, conforme confirmado em auditoria anterior. Não há necessidade de alterações no backend.

---

## 9. SOLUÇÃO MÍNIMA

### 1. De onde vem o solicitacao_id?

**Resposta**: Do objeto `pedido` criado em `enviarPedido()` (app.js:1132-1154), especificamente `pedido.id` que recebe `out.id` da resposta do backend.

### 2. Como ele chega à showPostOrderScreen?

**Resposta**: Através de parâmetro opcional: `showPostOrderScreen(pedido)`. O objeto `pedido` contém `pedido.id` (solicitacao_id), `pedido.kind`, `pedido.mesa`, `pedido.token`.

### 3. Como SALÃO é identificado?

**Resposta**: Através de `pedido.kind === "SALAO"` OU pela presença de `pedido.mesa` e `pedido.token` (que são nulos para DELIVERY).

### 4. Onde o polling será iniciado?

**Resposta**: Dentro de `showPostOrderScreen(pedidoInfo)` quando `pedidoInfo.kind === "SALAO"` e existirem `pedidoInfo.id`, `pedidoInfo.mesa`, `pedidoInfo.token`.

### 5. Onde o polling será encerrado?

**Resposta**: Quando o status KDS retornar "PRONTO" (cancelamento automático) OU quando o usuário clicar em "Voltar ao Cardápio" (chamada de `showMainScreen()`, que limpará o timer).

### 6. Qual timer será utilizado?

**Resposta**: `state.kdsPollingTimer` (nova variável seguindo o padrão arquitetural atual de `state.statusPublicoTimer`).

### 7. Qual endpoint será chamado?

**Resposta**: `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}` (GET, 2500ms intervalo).

### 8. Como a UI será atualizada?

**Resposta**: Atualização do elemento `#kdsStatusText` com base no status retornado:
- "AGUARDANDO" → "Pedido recebido"
- "EM_PREPARO" → "Seu pedido está sendo preparado"
- "PRONTO" → "Seu pedido está pronto"

### 9. Como DELIVERY permanecerá intacto?

**Resposta**: 
- A condicional `if (pedidoInfo.kind === "SALAO")` garante que o polling KDS só seja iniciado para SALÃO
- DELIVERY continuará usando o sistema existente (`state.statusPublicoTimer`, `refreshStatusPublicoNaTela()`, endpoint `/api/public/pedidos/<id>/status`)
- O elemento `#postOrderStatusPublico` continuará sendo usado apenas para DELIVERY
- Os elementos novos (`#kdsStatusArea`, `#kdsStatusText`) só serão mostrados para SALÃO

### 10. Quais arquivos serão alterados?

**Resposta**: 
- `Cardapio/assets/app.js` — Adicionar `state.kdsPollingTimer`, `pollKdsStatus()`, `startKdsPolling()`, `stopKdsPolling()`, adaptar `showPostOrderScreen(pedidoInfo?)`, adaptar `enviarPedido()` para passar `pedido`
- `Cardapio/index.html` — Adicionar `#kdsStatusArea` e `#kdsStatusText` dentro de `#postOrderScreen`

---

## 10. RISCOS

### Risco 1: Quebra de DELIVERY

**Probabilidade**: BAIXA  
**Mitigação**: Implementar condicional estrita baseado em `kind`. Testar ambos os tipos de pedido após implementação.

### Risco 2: Conflito de Timers

**Probabilidade**: BAIXA  
**Mitigação**: Usar timers separados (`state.kdsPollingTimer` para SALÃO, `state.statusPublicoTimer` para DELIVERY). Limpar ambos em `showMainScreen()`.

### Risco 3: Elementos UI Não Encontrados

**Probabilidade**: BAIXA  
**Mitigação**: Verificar existência dos elementos antes de atualizar (como feito no código atual).

### Risco 4: Endpoint KDS Incompatível

**Probabilidade**: BAIXA  
**Mitigação**: Endpoint já confirmado compatível em auditoria anterior. Testar com pedido real.

### Risco 5: Parâmetro Opcional Não Funcionar

**Probabilidade**: BAIXA  
**Mitigação**: JavaScript permite parâmetros opcionais nativamente. Fallback para localStorage se parâmetro não fornecido.

---

## 11. PLANO DE IMPLEMENTAÇÃO FUTURA

### PASSO 1 — Alterar HTML

- Adicionar elementos `#kdsStatusArea` e `#kdsStatusText` dentro de `#postOrderScreen` em `index.html`
- Estilo similar ao legado (fundo verde claro, borda verde)

### PASSO 2 — Adicionar Timer ao state

- Adicionar `state.kdsPollingTimer = null` ao objeto `state` em `app.js`

### PASSO 3 — Implementar Funções de Polling KDS

- Criar `pollKdsStatus(solicitacaoId, mesa, token)` em `app.js`
- Endpoint: `/api/solicitacoes/${solicitacaoId}/kds-status?mesa=${mesa}&token=${token}`
- Atualizar `#kdsStatusText` com base no status
- Retornar `true` se deve continuar polling, `false` se deve parar (status "PRONTO")

- Criar `startKdsPolling(solicitacaoId, mesa, token)` em `app.js`
- Limpar timer anterior se existir
- Configurar `setInterval` com `pollKdsStatus`, 2500ms
- Armazenar em `state.kdsPollingTimer`

- Criar `stopKdsPolling()` em `app.js`
- Limpar `state.kdsPollingTimer` se existir
- Setar para `null`

### PASSO 4 — Adaptar showPostOrderScreen()

- Alterar assinatura para `showPostOrderScreen(pedidoInfo?)`
- Se `pedidoInfo` fornecido: usar diretamente
- Se não fornecido: ler do localStorage (compatibilidade com DELIVERY existente)
- Implementar condicional:
  - Se `pedidoInfo.kind === "SALAO"`: Mostrar `#kdsStatusArea`, iniciar `startKdsPolling()`
  - Se `pedidoInfo.kind === "DELIVERY"`: Manter lógica existente (`#postOrderStatusPublico`, `startStatusPublicoPolling()`)

### PASSO 5 — Adaptar enviarPedido()

- Passar `pedido` como parâmetro: `showPostOrderScreen(pedido)`
- Manter salvamento de tracking para DELIVERY (não alterar)

### PASSO 6 — Adaptar showMainScreen()

- Adicionar `stopKdsPolling()` para limpar timer KDS
- Manter `stopStatusPublicoPolling()` para DELIVERY

### PASSO 7 — Teste

- Testar pedido SALÃO: Verificar polling KDS, atualização de UI, cancelamento quando "PRONTO"
- Testar pedido DELIVERY: Verificar que polling status público continua funcionando
- Verificar que não há conflito de timers
- Verificar que não há conflito de UI

---

## 12. ALTERAÇÕES REALIZADAS

**NENHUMA.**

---

## CONFIRMAÇÃO DE RESTRIÇÕES

A futura implementação NÃO deverá:

❌ Reativar legacyInlineScript  
❌ Alterar type="text/plain"  
❌ Recuperar as 1600 linhas  
❌ Criar tracking SALÃO em localStorage (confirmado desnecessário)  
❌ Duplicar o sistema de DELIVERY  
❌ Alterar backend (confirmado não necessário)  
❌ Refatorar funcionalidades não relacionadas  
❌ Criar nova arquitetura de polling (seguir padrão existente)  
❌ Alterar funcionalidades que já estão funcionando (DELIVERY)  

---

**FIM DO RELATÓRIO**