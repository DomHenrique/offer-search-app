CREATE TABLE IF NOT EXISTS lotes_busca (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'pendente', -- pendente, processando, concluido, erro
    total_itens INTEGER DEFAULT 0,
    itens_processados INTEGER DEFAULT 0,
    arquivo_resultado_url TEXT,
    erro_mensagem TEXT,
    criado_em TIMESTAMP DEFAULT NOW(),
    concluido_em TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lote_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    lote_id UUID NOT NULL REFERENCES lotes_busca(id) ON DELETE CASCADE,
    termo VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'pendente', -- pendente, sucesso, erro
    top_5_baratos JSONB,
    top_5_caros JSONB,
    erro_mensagem TEXT,
    criado_em TIMESTAMP DEFAULT NOW(),
    concluido_em TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lotes_busca_user ON lotes_busca(user_id);
CREATE INDEX IF NOT EXISTS idx_lote_itens_lote ON lote_itens(lote_id);
