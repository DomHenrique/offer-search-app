-- Tabela principal de ofertas (baseada nos arquivos de scraping)
CREATE TABLE IF NOT EXISTS ofertas (
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

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_ofertas_termo_pesquisa ON ofertas(termo_pesquisa);
CREATE INDEX IF NOT EXISTS idx_ofertas_marketplace ON ofertas(marketplace);
CREATE INDEX IF NOT EXISTS idx_ofertas_preco_numerico ON ofertas(preco_numerico);
CREATE INDEX IF NOT EXISTS idx_ofertas_score_produto ON ofertas(score_produto);
CREATE INDEX IF NOT EXISTS idx_ofertas_criado_em ON ofertas(criado_em);
