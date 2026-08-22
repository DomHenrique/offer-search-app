## 1. Banco de Dados e Modelagem de Logs

- [x] 1.1 Criar métodos em `database/db_manager.py` para salvar log de busca (`save_search_log`) e listar logs paginados com filtros (`get_search_logs`, `get_search_logs_stats`)
- [x] 1.2 Implementar função de relaxamento de termos (`relax_search_query`) em `scraping/unificar_dados.py`

## 2. Backend e Motor de Busca Resiliente

- [x] 2.1 Atualizar `scraping/unificar_dados.py` e `routes/search_routes.py` para disparar fallback relaxado automaticamente quando 0 ofertas forem encontradas
- [x] 2.2 Integrar a gravação de logs assíncrona no fluxo de busca de `routes/search_routes.py`
- [x] 2.3 Criar blueprint `routes/logs_routes.py` com endpoints `/logs` e `/logs/api/list`

## 3. Frontend — Painel Visual de Logs e Auditoria

- [x] 3.1 Criar template `templates/logs/logs_list.html` com métricas de saúde, tabela de buscas e modal de detalhes
- [x] 3.2 Adicionar o link "Logs" no menu de navegação em `templates/base.html`
- [x] 3.3 Exibir alerta informativo em `templates/search/results.html` quando resultados vierem de um termo relaxado/aproximado

## 4. Validação e Testes

- [x] 4.1 Validar busca de termo complexo com auto-recuperação e registro correto no painel de logs
- [x] 4.2 Comitar as alterações no repositório Git
