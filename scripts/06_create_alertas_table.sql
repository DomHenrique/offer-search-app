-- Tabela de alertas de preço
CREATE TABLE IF NOT EXISTS alertas (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    termo_pesquisa VARCHAR(255) NOT NULL,
    campo_alerta VARCHAR(50) NOT NULL, -- 'preco_numerico', 'avaliacao', 'score_produto'
    operador VARCHAR(10) NOT NULL, -- 'menor_que', 'maior_que', 'igual_a'
    valor_alerta DECIMAL(10,2) NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    total_disparos INTEGER DEFAULT 0,
    ultimo_disparo TIMESTAMP,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_alertas_user_id ON alertas(user_id);
CREATE INDEX IF NOT EXISTS idx_alertas_ativo ON alertas(ativo);
CREATE INDEX IF NOT EXISTS idx_alertas_campo_alerta ON alertas(campo_alerta);
