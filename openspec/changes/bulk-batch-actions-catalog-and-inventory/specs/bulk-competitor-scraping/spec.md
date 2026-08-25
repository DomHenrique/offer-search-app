## ADDED Requirements

### Requirement: Atualização Sequencial de Concorrentes em Lote
O sistema DEVE permitir a execução sequencial e controlada da varredura de concorrentes para uma lista de catálogos selecionados.

#### Scenario: Disparo e progresso de varredura em lote
- **WHEN** o usuário seleciona múltiplos catálogos e clica em "Atualizar Concorrentes (X)"
- **THEN** o sistema inicia o processamento sequencial das opções de compra no Mercado Livre, exibindo uma barra de progresso consolidada no drawer e atualizando as ofertas e preços da BuyBox de cada item.
