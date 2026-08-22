## ADDED Requirements

### Requirement: Relaxamento e Higienização de Termos Complexos
O sistema DEVE fornecer um mecanismo de limpeza e relaxamento de termos para remover ruídos e especificações técnicas desnecessárias (ex: `-eu`, `-br`, códigos soltos, pontuações) caso a busca principal resulte em 0 ofertas.

#### Scenario: Relaxamento de query em busca vazia
- **WHEN** o termo original retorna 0 ofertas no Mercado Livre ou Amazon
- **THEN** o sistema gera uma query relaxada contendo as palavras-chave essenciais e executa uma segunda tentativa de busca

#### Scenario: Alerta de termo aproximado no frontend
- **WHEN** uma busca tem sucesso através da query relaxada
- **THEN** a interface informa o usuário com um banner: "Exibindo resultados para o termo otimizado: [termo]"
