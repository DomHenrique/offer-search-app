-- Tabela de histórico de buscas realizadas
CREATE TABLE IF NOT EXISTS historico_buscas (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
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
    agendamento_id INTEGER REFERENCES agendamentos(id) ON DELETE SET NULL,
    executado_em TIMESTAMP DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_historico_buscas_user_id ON historico_buscas(user_id);
CREATE INDEX IF NOT EXISTS idx_historico_buscas_executado_em ON historico_buscas(executado_em);
CREATE INDEX IF NOT EXISTS idx_historico_buscas_status ON historico_buscas(status);
