-- ============================================================
-- Script 10: Tabelas de Catálogos do Mercado Livre
-- Criadas para suporte à aba "Catálogos" da aplicação
-- ============================================================

-- Tabela principal de catálogos (um registro por catálogo único do ML)
CREATE TABLE IF NOT EXISTS catalogos (
    id SERIAL PRIMARY KEY,
    catalog_id VARCHAR(50) NOT NULL,           -- Ex: MLB45231994
    nome TEXT NOT NULL,                         -- Título do produto do catálogo
    imagem TEXT DEFAULT '',                     -- URL da imagem do produto
    termo_pesquisa VARCHAR(255) DEFAULT '',     -- Termo de busca usado pra encontrar este catálogo
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    coletado_em TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_catalog_id UNIQUE (catalog_id)
);

-- Tabela de sellers (vendedores) por catálogo (histórico por coleta)
CREATE TABLE IF NOT EXISTS catalog_sellers (
    id SERIAL PRIMARY KEY,
    catalog_id VARCHAR(50) NOT NULL,            -- Referência ao catálogo (MLB...)
    seller_name VARCHAR(255) DEFAULT '',        -- Nome/nickname do vendedor
    seller_id_ml VARCHAR(100) DEFAULT '',       -- ID do vendedor no ML (se disponível)
    preco NUMERIC(12, 2) DEFAULT 0,             -- Preço numérico
    preco_str VARCHAR(50) DEFAULT '',           -- Preço formatado "R$ 1.234,56"
    frete_gratis BOOLEAN DEFAULT FALSE,         -- Frete gratuito
    frete_full BOOLEAN DEFAULT FALSE,           -- Envio FULL (Mercado Envios)
    reputacao VARCHAR(50) DEFAULT '',           -- Ex: 'verde', 'amarelo', 'vermelho', ''
    condicao VARCHAR(20) DEFAULT 'novo',        -- 'novo' ou 'usado'
    is_best_offer BOOLEAN DEFAULT FALSE,        -- Seller destacado como "Melhor opção" pelo ML
    posicao INTEGER DEFAULT 0,                  -- Posição na lista de sellers (1 = primeiro)
    coletado_em TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_catalog_sellers_catalog FOREIGN KEY (catalog_id)
        REFERENCES catalogos(catalog_id) ON DELETE CASCADE
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_catalogos_catalog_id ON catalogos(catalog_id);
CREATE INDEX IF NOT EXISTS idx_catalogos_user_id ON catalogos(user_id);
CREATE INDEX IF NOT EXISTS idx_catalogos_coletado_em ON catalogos(coletado_em DESC);

CREATE INDEX IF NOT EXISTS idx_catalog_sellers_catalog_id ON catalog_sellers(catalog_id);
CREATE INDEX IF NOT EXISTS idx_catalog_sellers_coletado_em ON catalog_sellers(coletado_em DESC);
CREATE INDEX IF NOT EXISTS idx_catalog_sellers_preco ON catalog_sellers(preco ASC);
