## ADDED Requirements

### Requirement: Barra Flutuante de Ações em Massa (Floating Bulk Action Bar)
O sistema DEVE exibir uma barra flutuante no rodapé sempre que um ou mais itens forem marcados via checkbox nas telas de listagem, ocultando-a quando nenhum item estiver selecionado.

#### Scenario: Exibição reativa da barra flutuante
- **WHEN** o usuário marca pelo menos um checkbox de item
- **THEN** a barra flutuante `#floatingBulkBar` surge animada no rodapé com a contagem de itens selecionados e os botões de ação contextuais.

#### Scenario: Ocultação da barra ao desmarcar todos
- **WHEN** o usuário clica em "Desmarcar Todos" ou desmarca o último item
- **THEN** a barra flutuante é recolhida suavemente e todos os checkboxes são limpos.
