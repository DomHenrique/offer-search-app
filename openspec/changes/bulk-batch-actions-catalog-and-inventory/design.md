## Context

O sistema "Traffic AI Busca Ofertas" possui telas de alta densidade de dados onde os usuários trabalham com dezenas de catálogos e produtos simultaneamente. Por exemplo, na tela `/inventory/product/<sku>`, um único SKU pode ter 40 a 50 catálogos conectados do Mercado Livre. O gerenciamento unitário gera atrito e lentidão.

Para resolver isso, este design estabelece:
1. Um padrão de componente de UI flutuante (*Floating Bulk Action Bar*).
2. Endpoints atômicos no backend para manipulação em lote.
3. Fila de scraping controlado para evitar bloqueios por concorrência.

## Goals / Non-Goals

**Goals:**
- Prover seleção múltipla em checkboxes estilizados na listagem de catálogos conectados, no drawer de SKU e na busca de ofertas.
- Implementar uma barra flutuante animada (*Floating Bulk Bar*) no rodapé da janela com feedback reativo de contagem e botões de ação contextuais.
- Permitir desvinculação em massa segura de catálogos com confirmação explícita.
- Permitir vinculação em lote de múltiplos catálogos pesquisados a um SKU existente em 1 clique.
- Permitir disparo sequencial/controlado de varreduras de concorrentes para múltiplos catálogos com barra de progresso.

**Non-Goals:**
- Exclusão irreversível de contas ou bancos de dados em lote.
- Alteração em lote de cookies de autenticação do Mercado Livre/Amazon.

## Decisions

### 1. Padrão de Componente Flutuante (*Floating Action Bar*)
- **Decisão:** Criar um container `#floatingBulkBar` posicionado com `position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); z-index: 1050;`.
- **Por que:** Evita poluir o topo da tabela com botões estáticos pesados e só aparece quando o usuário seleciona pelo menos 1 item (`selectedCount > 0`), mantendo a interface limpa e focada.
- **Alternativa descartada:** Botões fixos no cabeçalho da tabela que ocupam espaço vertical precioso mesmo quando nada está selecionado.

### 2. Endpoints de Desvinculação e Vinculação Atômicos
- **Decisão:** Criar `POST /inventory/unlink-catalogs-batch` recebendo `{ sku: "...", catalog_ids: ["MLB1", "MLB2", ...] }` e `POST /inventory/link-catalogs-batch` recebendo `{ sku: "...", catalogs: [...] }`.
- **Por que:** Reduz de N requisições HTTP para 1 única requisição atômica no Supabase, prevenindo inconsistências e acelerando a resposta de rede.

### 3. Fila Controlada de Varredura de Concorrentes (*Rate-Limiting Friendly*)
- **Decisão:** Ao selecionar múltiplos catálogos para atualizar concorrentes, o frontend envia os IDs e o backend enfileira com intervalo de segurança (respeitando os cookies da sessão) e reporta o progresso percentual acumulado.
- **Por que:** Disparar 20 requisições de scraping simultâneas no Mercado Livre poderia alertar os mecanismos de proteção do marketplace. A fila sequencial garante 100% de sucesso sem CAPTCHA.

## Risks / Trade-offs

- **[Risco] Desvinculação acidental de muitos catálogos** → *Mitigação:* Modal de confirmação com badge de contagem de itens e lista resumida dos catálogos selecionados antes do envio da requisição.
- **[Risco] Grande volume de dados no DOM** → *Mitigação:* Checkboxes leves com classes utilitárias e manipulação de estado via `Set` em JavaScript.
