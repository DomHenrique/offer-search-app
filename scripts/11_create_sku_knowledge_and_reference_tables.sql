-- ============================================================
-- Script 11: Tabelas de Conhecimento do Produto (Dossiê Canônico),
-- Anúncios de Referência e Auditoria de Inteligência Artificial
-- ============================================================

-- 1. Tabela do Dossiê Canônico de Verdade por SKU
CREATE TABLE IF NOT EXISTS sku_knowledge_base (
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

CREATE INDEX IF NOT EXISTS idx_sku_knowledge_user_sku ON sku_knowledge_base(user_id, sku);

-- 2. Tabela de Anúncios Ativos de Referência (Loja Própria / Links Manuais)
CREATE TABLE IF NOT EXISTS sku_reference_listings (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    sku VARCHAR(100) NOT NULL,
    marketplace VARCHAR(50) NOT NULL, -- 'MercadoLivre', 'Amazon', 'LojaPropria', 'Manual'
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

CREATE INDEX IF NOT EXISTS idx_sku_ref_user_sku ON sku_reference_listings(user_id, sku);
CREATE INDEX IF NOT EXISTS idx_sku_ref_listing_id ON sku_reference_listings(listing_id);

-- 3. Adiciona colunas de auditoria na tabela sku_catalogs (caso exista)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sku_catalogs') THEN
        ALTER TABLE sku_catalogs ADD COLUMN IF NOT EXISTS match_score INTEGER DEFAULT NULL;
        ALTER TABLE sku_catalogs ADD COLUMN IF NOT EXISTS match_verdict VARCHAR(50) DEFAULT NULL;
        ALTER TABLE sku_catalogs ADD COLUMN IF NOT EXISTS ai_explanation TEXT DEFAULT NULL;
        ALTER TABLE sku_catalogs ADD COLUMN IF NOT EXISTS audit_details JSONB DEFAULT NULL;
        ALTER TABLE sku_catalogs ADD COLUMN IF NOT EXISTS audited_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
    END IF;
END $$;
