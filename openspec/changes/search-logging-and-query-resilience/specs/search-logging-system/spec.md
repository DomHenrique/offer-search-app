## ADDED Requirements

### Requirement: Registro Estruturado de Logs de Busca
O sistema DEVE registrar automaticamente cada busca realizada por qualquer usuário na tabela `search_logs`, incluindo termo original, status de sucesso ou erro, total de produtos encontrados por marketplace e tempo de execução.

#### Scenario: Registro de busca bem-sucedida
- **WHEN** uma busca por ofertas é finalizada no backend
- **THEN** o sistema salva uma linha na tabela `search_logs` com status `SUCCESS` e as quantidades de ofertas coletadas

#### Scenario: Registro de busca vazia ou com erro
- **WHEN** uma busca não encontra ofertas ou sofre exceção de conexão/bloqueio
- **THEN** o sistema salva o log com status `EMPTY` ou `ERROR` e a mensagem descritiva do erro

### Requirement: Visualização do Painel de Logs e Auditoria
O sistema DEVE fornecer a rota `/logs` com interface visual para o administrador acompanhar em tempo real todas as buscas, filtrar por status e inspecionar detalhes.

#### Scenario: Acesso ao painel de logs
- **WHEN** o usuário acessa `/logs`
- **THEN** a tela exibe os cards de métricas gerais e a tabela de buscas recentes com paginação e busca por termo
