## Why

Buscas com termos longos ou técnicos (ex: vindos de notas fiscais com códigos como `220v-eu painel br`) frequentemente retornam 0 ofertas no Mercado Livre e Amazon devido a correspondências rígidas de rota. Além disso, a aplicação não possuía um sistema centralizado de logs e auditoria para monitorar em tempo real quem pesquisou, quais termos falharam ou vieram vazios, e quais erros ocorreram.

## What Changes

- **Sistema Centralizado de Logs de Busca e Auditoria (`search_logs`)**: Registro estruturado de todas as buscas contendo usuário, termo original, termo sanitizado, quantidade de ofertas (ML e Amazon), tempo de execução, status (`SUCCESS`, `EMPTY`, `ERROR`, `FALLBACK_RECOVERED`) e detalhes de erro/URL.
- **Motor de Busca Resiliente com Fallback Inteligente (Query Relaxation)**: Se uma busca retornar 0 ofertas na primeira tentativa, o backend automaticamente higieniza e simplifica o termo (removendo códigos, voltagens duplicadas e sufixos técnicos como `-eu`, `painel br`) e realiza uma segunda tentativa imediata, alertando o usuário sobre a recuperação com termo aproximado.
- **Painel Visual de Logs e Diagnóstico (`/logs`)**: Nova tela com métricas de saúde das buscas (Total, Taxa de Sucesso, Buscas Vazias, Erros), tabela com filtros por status e modal para visualização detalhada de cada requisição.

## Capabilities

### New Capabilities
- `search-logging-system`: Registro estruturado de atividades de busca, erros e métricas no banco de dados com visualização em painel de administração/auditoria.
- `query-relaxation-engine`: Algoritmo de relaxamento e sanitização de termos para evitar buscas vazias quando termos contêm ruídos técnicos de importação/faturamento.

### Modified Capabilities
- `search-engine`: Enriquecimento do motor de busca unificado com captura de métricas de log e execução de fallback automático em caso de 0 resultados.

## Impact

- **Banco de Dados**: Criação e gestão da tabela `search_logs` em `database/db_manager.py`.
- **Scraper / Backend**: `scraping/unificar_dados.py`, `scraping/web_scrap_mercado_livre.py`, `routes/search_routes.py`.
- **Novas Rotas e Interface**: `routes/logs_routes.py`, `templates/logs/logs_list.html`, inclusão do link "Logs" no menu de navegação em `templates/base.html`.
