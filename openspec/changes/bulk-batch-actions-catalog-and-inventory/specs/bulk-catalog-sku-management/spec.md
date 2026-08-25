## ADDED Requirements

### Requirement: Desvinculação em Massa de Catálogos do SKU
O sistema DEVE permitir que o usuário selecione múltiplos catálogos conectados a um SKU e execute a desvinculação em lote em uma única requisição.

#### Scenario: Desvinculação múltipla com sucesso
- **WHEN** o usuário seleciona 3 catálogos conectados a um SKU e clica em "Desvincular Selecionados"
- **THEN** o sistema exibe um modal de confirmação, envia a requisição para `/inventory/unlink-catalogs-batch`, remove os registros correspondentes da tabela `sku_catalogs` e atualiza a interface sem recarregar a página inteira.

### Requirement: Vinculação em Lote a partir da Busca de Catálogos
O sistema DEVE permitir que o usuário selecione múltiplos catálogos resultantes de uma pesquisa e os vincule a um SKU selecionado em uma única operação.

#### Scenario: Vinculação múltipla a partir da listagem de busca
- **WHEN** o usuário seleciona múltiplos cards de catálogos na página `/catalog` e clica em "Vincular a SKU"
- **THEN** o sistema abre um seletor de SKU e, após a escolha, executa a requisição atômica vinculando todos os itens selecionados ao SKU informado.
