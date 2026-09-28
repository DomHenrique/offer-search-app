-- ==============================================================================
-- SETUP COMPLETO DO BANCO DE DADOS - OFFER SEARCH APP
-- Execute este script no SQL Editor do novo projeto Supabase (qohalxlfeddyijidldsa)
-- ==============================================================================

-- 0. Habilita extensão para geração de UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Tabela de usuários para autenticação
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nome VARCHAR(255) NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT NOW(),
    ultimo_login TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_users_ativo ON public.users(ativo);

-- 2. Tabela de configurações do usuário
CREATE TABLE IF NOT EXISTS public.configuracoes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    chave VARCHAR(100) NOT NULL,
    valor TEXT NOT NULL,
    descricao TEXT,
    tipo VARCHAR(20) DEFAULT 'string',
    obrigatorio BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, chave)
);
CREATE INDEX IF NOT EXISTS idx_configuracoes_user_id ON public.configuracoes(user_id);
CREATE INDEX IF NOT EXISTS idx_configuracoes_chave ON public.configuracoes(chave);

-- 3. Tabela principal de ofertas
CREATE TABLE IF NOT EXISTS public.ofertas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    termo_pesquisa VARCHAR(255) NOT NULL,
    titulo TEXT NOT NULL,
    preco VARCHAR(50),
    preco_numerico DECIMAL(10,2) DEFAULT 0,
    loja VARCHAR(255),
    avaliacao DECIMAL(3,2) DEFAULT 0,
    avaliacoes INTEGER DEFAULT 0,
    imagem TEXT,
    url_produto TEXT,
    marketplace VARCHAR(50) NOT NULL,
    categoria_preco VARCHAR(50),
    score_produto DECIMAL(5,2) DEFAULT 0,
    prime BOOLEAN DEFAULT FALSE,
    patrocinado BOOLEAN DEFAULT FALSE,
    desconto_percent DECIMAL(5,2) DEFAULT 0,
    preco_antigo VARCHAR(50),
    etiquetas TEXT,
    ofertas_especiais TEXT,
    vendidos_mes VARCHAR(100),
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ofertas_termo_pesquisa ON public.ofertas(termo_pesquisa);
CREATE INDEX IF NOT EXISTS idx_ofertas_marketplace ON public.ofertas(marketplace);
CREATE INDEX IF NOT EXISTS idx_ofertas_preco_numerico ON public.ofertas(preco_numerico);
CREATE INDEX IF NOT EXISTS idx_ofertas_score_produto ON public.ofertas(score_produto);
CREATE INDEX IF NOT EXISTS idx_ofertas_criado_em ON public.ofertas(criado_em);

-- 4. Tabela de produtos aprovados
CREATE TABLE IF NOT EXISTS public.produtos_aprovados (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    oferta_id UUID REFERENCES public.ofertas(id) ON DELETE CASCADE,
    titulo TEXT NOT NULL,
    preco VARCHAR(50),
    preco_numerico DECIMAL(10,2),
    loja VARCHAR(255),
    marketplace VARCHAR(50),
    imagem TEXT,
    url_produto TEXT,
    avaliacao DECIMAL(3,2),
    avaliacoes INTEGER,
    termo_pesquisa VARCHAR(255),
    categoria_preco VARCHAR(50),
    score_produto DECIMAL(5,2),
    prime BOOLEAN DEFAULT FALSE,
    patrocinado BOOLEAN DEFAULT FALSE,
    desconto_percent DECIMAL(5,2),
    preco_antigo VARCHAR(50),
    etiquetas TEXT,
    ofertas_especiais TEXT,
    vendidos_mes VARCHAR(100),
    observacoes TEXT,
    status VARCHAR(20) DEFAULT 'ativo',
    aprovado_em TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_produtos_aprovados_user_id ON public.produtos_aprovados(user_id);
CREATE INDEX IF NOT EXISTS idx_produtos_aprovados_status ON public.produtos_aprovados(status);
CREATE INDEX IF NOT EXISTS idx_produtos_aprovados_aprovado_em ON public.produtos_aprovados(aprovado_em);

-- 5. Tabela de agendamentos de busca
CREATE TABLE IF NOT EXISTS public.agendamentos (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    termo_pesquisa VARCHAR(255) NOT NULL,
    intervalo_horas INTEGER NOT NULL CHECK (intervalo_horas IN (6, 12)),
    ativo BOOLEAN DEFAULT TRUE,
    proxima_execucao TIMESTAMP NOT NULL,
    ultima_execucao TIMESTAMP,
    total_execucoes INTEGER DEFAULT 0,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agendamentos_user_id ON public.agendamentos(user_id);
CREATE INDEX IF NOT EXISTS idx_agendamentos_ativo ON public.agendamentos(ativo);
CREATE INDEX IF NOT EXISTS idx_agendamentos_proxima_execucao ON public.agendamentos(proxima_execucao);

-- 6. Tabela de histórico de buscas
CREATE TABLE IF NOT EXISTS public.historico_buscas (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    termo_pesquisa VARCHAR(255) NOT NULL,
    total_produtos_encontrados INTEGER DEFAULT 0,
    marketplace_amazon INTEGER DEFAULT 0,
    marketplace_mercadolivre INTEGER DEFAULT 0,
    preco_medio DECIMAL(10,2) DEFAULT 0,
    preco_minimo DECIMAL(10,2) DEFAULT 0,
    preco_maximo DECIMAL(10,2) DEFAULT 0,
    tempo_execucao_segundos INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'concluida',
    erro_mensagem TEXT,
    agendamento_id INTEGER REFERENCES public.agendamentos(id) ON DELETE SET NULL,
    executado_em TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_historico_buscas_user_id ON public.historico_buscas(user_id);
CREATE INDEX IF NOT EXISTS idx_historico_buscas_executado_em ON public.historico_buscas(executado_em);
CREATE INDEX IF NOT EXISTS idx_historico_buscas_status ON public.historico_buscas(status);

-- 7. Tabela de alertas de preço
CREATE TABLE IF NOT EXISTS public.alertas (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    termo_pesquisa VARCHAR(255),
    campo_alerta VARCHAR(255),
    operador VARCHAR(20),
    valor_alerta NUMERIC,
    produto_nome VARCHAR(255),
    preco_alvo DECIMAL(10,2),
    tipo_alerta VARCHAR(20),
    telefone VARCHAR(20),
    ativo BOOLEAN DEFAULT TRUE,
    total_disparos INTEGER DEFAULT 0,
    ultimo_disparo TIMESTAMP,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- Garante que todas as colunas existam mesmo se a tabela já existia no novo banco
ALTER TABLE public.alertas ADD COLUMN IF NOT EXISTS produto_nome VARCHAR(255);
ALTER TABLE public.alertas ADD COLUMN IF NOT EXISTS preco_alvo DECIMAL(10,2);
ALTER TABLE public.alertas ADD COLUMN IF NOT EXISTS tipo_alerta VARCHAR(20);
ALTER TABLE public.alertas ADD COLUMN IF NOT EXISTS telefone VARCHAR(20);
ALTER TABLE public.alertas ADD COLUMN IF NOT EXISTS termo_pesquisa VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_alertas_user_id ON public.alertas(user_id);
CREATE INDEX IF NOT EXISTS idx_alertas_ativo ON public.alertas(ativo);
CREATE INDEX IF NOT EXISTS idx_alertas_produto_nome ON public.alertas(produto_nome);

-- 8. Tabela de pedidos de compra (Estoque)
CREATE TABLE IF NOT EXISTS public.pedidos_compra (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    numero_pedido TEXT NOT NULL,
    fornecedor TEXT,
    data_pedido TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    observacoes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);
ALTER TABLE public.pedidos_compra ALTER COLUMN user_id TYPE text;
CREATE INDEX IF NOT EXISTS idx_pedidos_compra_user_id ON public.pedidos_compra(user_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_compra_numero ON public.pedidos_compra(numero_pedido);

-- 9. Tabela de itens do pedido (Estoque)
CREATE TABLE IF NOT EXISTS public.itens_pedido (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pedido_id UUID REFERENCES public.pedidos_compra(id) ON DELETE CASCADE,
    sku TEXT NOT NULL,
    descricao TEXT NOT NULL,
    ncm TEXT,
    quantidade INTEGER NOT NULL DEFAULT 1,
    preco_custo NUMERIC(12, 2),
    preco_revenda NUMERIC(12, 2),
    preco_site_pix NUMERIC(12, 2),
    link_produto TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);
CREATE INDEX IF NOT EXISTS idx_itens_pedido_pedido_id ON public.itens_pedido(pedido_id);
CREATE INDEX IF NOT EXISTS idx_itens_pedido_sku ON public.itens_pedido(sku);

-- 10. Tabela de catálogos do Mercado Livre
CREATE TABLE IF NOT EXISTS public.catalogos (
    id SERIAL PRIMARY KEY,
    catalog_id VARCHAR(50) NOT NULL,
    nome TEXT NOT NULL,
    imagem TEXT DEFAULT '',
    termo_pesquisa VARCHAR(255) DEFAULT '',
    user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    coletado_em TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_catalog_id UNIQUE (catalog_id)
);
CREATE INDEX IF NOT EXISTS idx_catalogos_catalog_id ON public.catalogos(catalog_id);
CREATE INDEX IF NOT EXISTS idx_catalogos_user_id ON public.catalogos(user_id);
CREATE INDEX IF NOT EXISTS idx_catalogos_coletado_em ON public.catalogos(coletado_em DESC);

-- 11. Tabela de sellers por catálogo
CREATE TABLE IF NOT EXISTS public.catalog_sellers (
    id SERIAL PRIMARY KEY,
    catalog_id VARCHAR(50) NOT NULL,
    seller_name VARCHAR(255) DEFAULT '',
    seller_id_ml VARCHAR(100) DEFAULT '',
    preco NUMERIC(12, 2) DEFAULT 0,
    preco_str VARCHAR(50) DEFAULT '',
    frete_gratis BOOLEAN DEFAULT FALSE,
    frete_full BOOLEAN DEFAULT FALSE,
    reputacao VARCHAR(50) DEFAULT '',
    condicao VARCHAR(20) DEFAULT 'novo',
    is_best_offer BOOLEAN DEFAULT FALSE,
    posicao INTEGER DEFAULT 0,
    coletado_em TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_catalog_sellers_catalog FOREIGN KEY (catalog_id)
        REFERENCES public.catalogos(catalog_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_catalog_sellers_catalog_id ON public.catalog_sellers(catalog_id);
CREATE INDEX IF NOT EXISTS idx_catalog_sellers_coletado_em ON public.catalog_sellers(coletado_em DESC);
CREATE INDEX IF NOT EXISTS idx_catalog_sellers_preco ON public.catalog_sellers(preco ASC);

-- 12. Tabela de vínculo SKU-Catálogos com campos de auditoria de IA
CREATE TABLE IF NOT EXISTS public.sku_catalogs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    sku TEXT NOT NULL,
    catalog_id TEXT NOT NULL,
    catalog_title TEXT,
    catalog_url TEXT,
    catalog_image TEXT,
    buybox_winner TEXT,
    buybox_min_price REAL DEFAULT 0.0,
    sellers_count INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    match_score INTEGER DEFAULT NULL,
    match_verdict VARCHAR(50) DEFAULT NULL,
    ai_explanation TEXT DEFAULT NULL,
    audit_details JSONB DEFAULT NULL,
    audited_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_sku_catalogs_user_sku ON public.sku_catalogs(user_id, sku);
CREATE INDEX IF NOT EXISTS idx_sku_catalogs_catalog_id ON public.sku_catalogs(catalog_id);

-- 13. Tabela do Dossiê Canônico de Verdade por SKU
CREATE TABLE IF NOT EXISTS public.sku_knowledge_base (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    sku VARCHAR(100) NOT NULL,
    brand VARCHAR(150) DEFAULT '',
    model VARCHAR(150) DEFAULT '',
    gtin_ean VARCHAR(50) DEFAULT '',
    canonical_title TEXT DEFAULT '',
    specs JSONB DEFAULT '{}'::jsonb,
    negative_terms JSONB DEFAULT '[]'::jsonb,
    price_sanity_min NUMERIC(12, 2) DEFAULT 0,
    price_sanity_max NUMERIC(12, 2) DEFAULT 0,
    ai_summary TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_sku_knowledge UNIQUE (user_id, sku)
);
CREATE INDEX IF NOT EXISTS idx_sku_knowledge_user_sku ON public.sku_knowledge_base(user_id, sku);

-- 14. Tabela de Anúncios Ativos de Referência
CREATE TABLE IF NOT EXISTS public.sku_reference_listings (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    sku VARCHAR(100) NOT NULL,
    marketplace VARCHAR(50) NOT NULL,
    listing_id VARCHAR(100) DEFAULT '',
    listing_url TEXT NOT NULL,
    title TEXT DEFAULT '',
    price NUMERIC(12, 2) DEFAULT 0,
    image_url TEXT DEFAULT '',
    gtin VARCHAR(50) DEFAULT '',
    raw_attributes JSONB DEFAULT '{}'::jsonb,
    is_own_store BOOLEAN DEFAULT TRUE,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sku_ref_user_sku ON public.sku_reference_listings(user_id, sku);
CREATE INDEX IF NOT EXISTS idx_sku_ref_listing_id ON public.sku_reference_listings(listing_id);

-- 15. Tabela de lotes de busca
CREATE TABLE IF NOT EXISTS public.lotes_busca (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'pendente',
    total_itens INTEGER DEFAULT 0,
    itens_processados INTEGER DEFAULT 0,
    arquivo_resultado_url TEXT,
    erro_mensagem TEXT,
    criado_em TIMESTAMP DEFAULT NOW(),
    concluido_em TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_lotes_busca_user ON public.lotes_busca(user_id);

-- 16. Tabela de itens de lote de busca
CREATE TABLE IF NOT EXISTS public.lote_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    lote_id UUID NOT NULL REFERENCES public.lotes_busca(id) ON DELETE CASCADE,
    termo VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'pendente',
    top_5_baratos JSONB,
    top_5_caros JSONB,
    erro_mensagem TEXT,
    criado_em TIMESTAMP DEFAULT NOW(),
    concluido_em TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_lote_itens_lote ON public.lote_itens(lote_id);

-- 17. Tabela de logs de busca e auditoria
CREATE TABLE IF NOT EXISTS public.search_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID,
    user_email TEXT,
    termo_original TEXT NOT NULL,
    termo_utilizado TEXT NOT NULL,
    status TEXT NOT NULL,
    total_ofertas INTEGER DEFAULT 0,
    ml_ofertas INTEGER DEFAULT 0,
    amazon_ofertas INTEGER DEFAULT 0,
    tempo_execucao_segundos REAL DEFAULT 0.0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_search_logs_created_at ON public.search_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_logs_status ON public.search_logs(status);

-- ==============================================================================
-- FUNÇÕES E TRIGGERS
-- ==============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ofertas_updated_at') THEN
        CREATE TRIGGER update_ofertas_updated_at BEFORE UPDATE ON public.ofertas FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_agendamentos_updated_at') THEN
        CREATE TRIGGER update_agendamentos_updated_at BEFORE UPDATE ON public.agendamentos FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_alertas_updated_at') THEN
        CREATE TRIGGER update_alertas_updated_at BEFORE UPDATE ON public.alertas FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_configuracoes_updated_at') THEN
        CREATE TRIGGER update_configuracoes_updated_at BEFORE UPDATE ON public.configuracoes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION calcular_proxima_execucao(intervalo_horas INTEGER)
RETURNS TIMESTAMP AS $$
BEGIN
    RETURN NOW() + (intervalo_horas || ' hours')::INTERVAL;
END;
$$ language 'plpgsql';

CREATE OR REPLACE FUNCTION limpar_ofertas_antigas()
RETURNS INTEGER AS $$
DECLARE
    registros_removidos INTEGER;
BEGIN
    DELETE FROM public.ofertas 
    WHERE criado_em < NOW() - INTERVAL '30 days'
    AND id NOT IN (
        SELECT DISTINCT oferta_id 
        FROM public.produtos_aprovados 
        WHERE oferta_id IS NOT NULL
    );
    GET DIAGNOSTICS registros_removidos = ROW_COUNT;
    RETURN registros_removidos;
END;
$$ language 'plpgsql';
