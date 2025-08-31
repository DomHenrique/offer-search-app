-- Tabela de configurações do usuário (variáveis de ambiente)
CREATE TABLE IF NOT EXISTS configuracoes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    chave VARCHAR(100) NOT NULL,
    valor TEXT NOT NULL,
    descricao TEXT,
    tipo VARCHAR(20) DEFAULT 'string', -- 'string', 'number', 'boolean', 'password'
    obrigatorio BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, chave)
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_configuracoes_user_id ON configuracoes(user_id);
CREATE INDEX IF NOT EXISTS idx_configuracoes_chave ON configuracoes(chave);

-- Inserir configurações padrão necessárias
INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio) 
SELECT 
    u.id,
    'SERPAPI_KEY',
    '',
    'Chave da API do SerpAPI para busca na Amazon',
    'password',
    true
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM configuracoes c 
    WHERE c.user_id = u.id AND c.chave = 'SERPAPI_KEY'
);

INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio) 
SELECT 
    u.id,
    'SUPABASE_URL',
    '',
    'URL do projeto Supabase',
    'string',
    true
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM configuracoes c 
    WHERE c.user_id = u.id AND c.chave = 'SUPABASE_URL'
);

INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio) 
SELECT 
    u.id,
    'SUPABASE_KEY',
    '',
    'Chave de serviço do Supabase',
    'password',
    true
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM configuracoes c 
    WHERE c.user_id = u.id AND c.chave = 'SUPABASE_KEY'
);
