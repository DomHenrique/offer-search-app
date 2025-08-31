-- Tabela de agendamentos de busca
CREATE TABLE IF NOT EXISTS agendamentos (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    termo_pesquisa VARCHAR(255) NOT NULL,
    intervalo_horas INTEGER NOT NULL CHECK (intervalo_horas IN (6, 12)),
    ativo BOOLEAN DEFAULT TRUE,
    proxima_execucao TIMESTAMP NOT NULL,
    ultima_execucao TIMESTAMP,
    total_execucoes INTEGER DEFAULT 0,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_agendamentos_user_id ON agendamentos(user_id);
CREATE INDEX IF NOT EXISTS idx_agendamentos_ativo ON agendamentos(ativo);
CREATE INDEX IF NOT EXISTS idx_agendamentos_proxima_execucao ON agendamentos(proxima_execucao);
