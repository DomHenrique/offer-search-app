-- Tabela de produtos aprovados pelo usuário
CREATE TABLE IF NOT EXISTS produtos_aprovados (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    oferta_id UUID,
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
    aprovado_em TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_user
        FOREIGN KEY(user_id) 
        REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_oferta
        FOREIGN KEY(oferta_id) 
        REFERENCES ofertas(id)
        ON DELETE CASCADE
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_produtos_aprovados_user_id ON produtos_aprovados(user_id);
CREATE INDEX IF NOT EXISTS idx_produtos_aprovados_status ON produtos_aprovados(status);
CREATE INDEX IF NOT EXISTS idx_produtos_aprovados_aprovado_em ON produtos_aprovados(aprovado_em);
