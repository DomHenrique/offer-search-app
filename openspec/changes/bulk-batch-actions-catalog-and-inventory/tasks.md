## 1. Backend & Banco de Dados (Endpoints em Lote)

- [ ] 1.1 Implementar método `unlink_catalogs_batch(user_id, sku, catalog_ids)` no `DatabaseManager` (`database/db_manager.py`) para exclusão atômica.
- [ ] 1.2 Implementar método `link_catalogs_batch(user_id, sku, catalogs_data)` no `DatabaseManager` (`database/db_manager.py`) para inserção/atualização atômica.
- [ ] 1.3 Criar rota `POST /inventory/unlink-catalogs-batch` em `routes/inventory_routes.py`.
- [ ] 1.4 Criar rota `POST /inventory/link-catalogs-batch` em `routes/inventory_routes.py`.
- [ ] 1.5 Criar rota `POST /catalog/batch-scrape-sellers` em `routes/catalog_routes.py` para enfileiramento controlado de varredura.

## 2. Design System & CSS da Barra Flutuante

- [ ] 2.1 Criar estilos CSS para `.floating-bulk-bar` (posicionamento fixo, sombras, gradientes, animação slide-up) em `static/css/style.css`.
- [ ] 2.2 Criar estilos para os checkboxes estilizados e estados de seleção ativa (`.item-selected-row`, `.item-checkbox-custom`).

## 3. Gestão em Massa na Página do Produto & Drawer de SKU

- [ ] 3.1 Adicionar checkbox mestre ("Selecionar Todos") e checkboxes individuais nos cards de catálogos em `templates/inventory/product_detail.html`.
- [ ] 3.2 Integrar a Barra Flutuante de Ações com contagem reativa e botões: "Desvincular Selecionados" e "Atualizar Concorrentes em Lote" em `product_detail.html`.
- [ ] 3.3 Adicionar seleção múltipla e ações em massa nos catálogos renderizados no Drawer de SKU (`#skuProductDrawer`) em `templates/inventory/inventory_list.html`.
- [ ] 3.4 Implementar modal de confirmação seguro com resumo dos itens antes da desvinculação em massa.

## 4. Vinculação em Lote a partir da Busca de Catálogos

- [ ] 4.1 Adicionar checkboxes de seleção múltipla nos cards de catálogos em `templates/catalog/catalog_list.html`.
- [ ] 4.2 Adicionar Barra Flutuante na tela de busca com botão "Vincular Selecionados ao SKU" e modal com lista suspensa dos SKUs cadastrados no estoque.
- [ ] 4.3 Implementar fluxo de vinculação em lote e feedback visual instantâneo (*Toast* e atualização de badges).

## 5. Validação e Testes Integrados

- [ ] 5.1 Testar desvinculação em lote com 10+ catálogos conectados a um SKU.
- [ ] 5.2 Testar vinculação em lote de múltiplos catálogos pesquisados a um SKU.
- [ ] 5.3 Testar varredura de concorrentes em lote com fila e barra de progresso consolidada.
