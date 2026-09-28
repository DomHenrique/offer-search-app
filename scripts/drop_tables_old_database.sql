-- ==============================================================================
-- SCRIPT DE REMOÇÃO DEFINITIVA (DROP) DAS TABELAS DO OFFER SEARCH APP
-- Execute este script no SQL Editor do banco ANTIGO (povgswnmwispktahqxzk)
-- ==============================================================================
-- ATENÇÃO:
-- As tabelas da outra aplicação (clients, daily_metrics, organic_metrics,
-- meta_ads_*, gridd360_leads) NÃO constam neste script e NÃO serão afetadas.
-- ==============================================================================

-- 1. Exclui as 17 tabelas da aplicação (ordem segura: filhas -> pais)
DROP TABLE IF EXISTS public.itens_pedido CASCADE;
DROP TABLE IF EXISTS public.pedidos_compra CASCADE;
DROP TABLE IF EXISTS public.catalog_sellers CASCADE;
DROP TABLE IF EXISTS public.sku_catalogs CASCADE;
DROP TABLE IF EXISTS public.catalogos CASCADE;
DROP TABLE IF EXISTS public.produtos_aprovados CASCADE;
DROP TABLE IF EXISTS public.ofertas CASCADE;
DROP TABLE IF EXISTS public.historico_buscas CASCADE;
DROP TABLE IF EXISTS public.agendamentos CASCADE;
DROP TABLE IF EXISTS public.alertas CASCADE;
DROP TABLE IF EXISTS public.configuracoes CASCADE;
DROP TABLE IF EXISTS public.lote_itens CASCADE;
DROP TABLE IF EXISTS public.lotes_busca CASCADE;
DROP TABLE IF EXISTS public.sku_knowledge_base CASCADE;
DROP TABLE IF EXISTS public.sku_reference_listings CASCADE;
DROP TABLE IF EXISTS public.search_logs CASCADE;
DROP TABLE IF EXISTS public.users CASCADE;

-- 2. Exclui funções auxiliares que pertenciam exclusivamente ao Offer Search
DROP FUNCTION IF EXISTS public.limpar_ofertas_antigas() CASCADE;
DROP FUNCTION IF EXISTS public.calcular_proxima_execucao(INTEGER) CASCADE;

-- 3. Consulta de verificação pós-remoção (confirma que apenas a outra aplicação restou)
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
