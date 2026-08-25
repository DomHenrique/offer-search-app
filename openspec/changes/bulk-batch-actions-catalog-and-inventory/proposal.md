## Why

O gerenciamento de grandes volumes de catálogos (ex: SKUs com 40+ catálogos conectados) e resultados de pesquisa de mercado é inviável quando executado item por item. A ausência de ações em massa (*Bulk Actions*) força o usuário a realizar dezenas de cliques manuais e confirmações repetitivas para desvincular catálogos, vincular novos itens encontrados ou atualizar dados de concorrentes e BuyBox.

Esta mudança introduz um sistema completo e unificado de **Ações em Massa** (seleção múltipla, barra flutuante de ações contextuais, vinculação em lote a SKUs, desvinculação em massa e varredura de concorrentes em lote), aumentando drasticamente a eficiência operacional do usuário.

## What Changes

- **Componente Visual Flutuante (*Floating Bulk Action Bar*):** Ao selecionar 1 ou mais itens via checkboxes (na página de produto, no drawer de SKU ou na listagem de catálogos), uma barra elegante de ações surge na parte inferior com contador e ações contextuais.
- **Desvinculação em Massa no SKU (*Bulk Unlink*):** Checkbox mestre ("Selecionar Todos") e seleção individual na lista de catálogos conectados do SKU, permitindo desvincular múltiplos catálogos em uma única requisição com modal de confirmação claro.
- **Vinculação em Lote a partir da Busca (*Bulk Link to SKU*):** Na tela de Catálogos / Busca de Ofertas, permite marcar múltiplos cards/itens encontrados e vinculá-los diretamente a um SKU existente em um único modal de seleção rápida.
- **Varredura / Atualização de Concorrentes em Lote (*Bulk Competitor Sync*):** Permite selecionar múltiplos catálogos e disparar a atualização de preços da BuyBox e concorrentes em fila controlada, com indicador de progresso consolidado.
- **Novos Endpoints de API em Lote no Backend:**
  - `POST /inventory/unlink-catalogs-batch`: Recebe lista de IDs de catálogo e desvincula do SKU em transação única.
  - `POST /inventory/link-catalogs-batch`: Recebe SKU e lista de catálogos para vinculação atômica.
  - `POST /catalog/batch-scrape-sellers`: Dispara varredura sequencial/controlada para múltiplos catálogos.

## Capabilities

### New Capabilities
- `bulk-catalog-sku-management`: Ações de seleção múltipla, vinculação e desvinculação em massa de catálogos de marketplaces associados a SKUs internos.
- `bulk-competitor-scraping`: Enfileiramento e acompanhamento de varreduras de concorrentes e BuyBox para múltiplos catálogos selecionados.
- `floating-bulk-actions-ui`: Componente de interface de usuário (Barra de Ações Flutuante) com seleção individual, seleção total, contadores reativos e modais de confirmação.

### Modified Capabilities
<!-- Nenhuma especificação anterior teve seus requisitos alterados; esta proposta expande as capacidades existentes -->

## Impact

- **Frontend:** Atualização de `templates/inventory/product_detail.html`, `templates/inventory/inventory_list.html`, `templates/catalog/catalog_list.html` e `static/css/style.css`.
- **Backend:** Criação de rotas em lote em `routes/inventory_routes.py` e `routes/catalog_routes.py`.
- **Database:** Novos métodos no `DatabaseManager` (`db_manager.py`) para operações atômicas em `sku_catalogs`.
- **APIs / Sessões:** Respeito aos rate-limits do Mercado Livre através de fila assíncrona controlada para scraping em lote.
