-- Tabela de alertas de preço
CREATE TABLE IF NOT EXISTS alertas (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    produto_nome VARCHAR(255) NOT NULL,
    preco_alvo DECIMAL(10,2) NOT NULL,
    tipo_alerta VARCHAR(20) NOT NULL, -- 'menor_ou_igual', 'maior_ou_igual'
    telefone VARCHAR(20),
    ativo BOOLEAN DEFAULT TRUE,
    total_disparos INTEGER DEFAULT 0,
    ultimo_disparo TIMESTAMP,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_alertas_user_id ON alertas(user_id);
CREATE INDEX IF NOT EXISTS idx_alertas_ativo ON alertas(ativo);
CREATE INDEX IF NOT EXISTS idx_alertas_produto_nome ON alertas(produto_nome);
