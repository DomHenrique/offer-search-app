-- Combined SQL script to create all tables and functions for Offer Search App

-- 01_create_users_table.sql
-- Tabela de usuários para autenticação
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nome VARCHAR(255) NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT NOW(),
    ultimo_login TIMESTAMP
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_ativo ON users(ativo);

-- 02_create_ofertas_table.sql
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

-- 03_create_produtos_aprovados_table.sql
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

-- 04_create_agendamentos_table.sql
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

-- 05_create_historico_buscas_table.sql
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

-- 06_create_alertas_table.sql
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

-- 07_create_configuracoes_table.sql
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
DO $
DECLARE
    usr_id INTEGER;
BEGIN
    FOR usr_id IN SELECT id FROM users
    LOOP
        INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio) VALUES
            (usr_id, 'SERPAPI_KEY', '', 'Chave da API do SerpAPI para busca na Amazon', 'password', true),
            (usr_id, 'SUPABASE_URL', '', 'URL do projeto Supabase', 'string', true),
            (usr_id, 'SUPABASE_KEY', '', 'Chave de serviço do Supabase', 'password', true)
        ON CONFLICT (user_id, chave) DO NOTHING;
    END LOOP;
END $;

-- 08_create_triggers_and_functions.sql
-- Função para atualizar timestamp automaticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers para atualizar automaticamente o campo atualizado_em
CREATE TRIGGER update_ofertas_updated_at 
    BEFORE UPDATE ON ofertas 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agendamentos_updated_at 
    BEFORE UPDATE ON agendamentos 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alertas_updated_at 
    BEFORE UPDATE ON alertas 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_configuracoes_updated_at 
    BEFORE UPDATE ON configuracoes 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Função para calcular próxima execução de agendamento
CREATE OR REPLACE FUNCTION calcular_proxima_execucao(intervalo_horas INTEGER)
RETURNS TIMESTAMP AS $$
BEGIN
    RETURN NOW() + (intervalo_horas || ' hours')::INTERVAL;
END;
$$ language 'plpgsql';

-- Função para limpar ofertas antigas (mais de 30 dias)
CREATE OR REPLACE FUNCTION limpar_ofertas_antigas()
RETURNS INTEGER AS $$
DECLARE
    registros_removidos INTEGER;
BEGIN
    DELETE FROM ofertas 
    WHERE criado_em < NOW() - INTERVAL '30 days'
    AND id NOT IN (
        SELECT DISTINCT oferta_id 
        FROM produtos_aprovados 
        WHERE oferta_id IS NOT NULL
    );
    
    GET DIAGNOSTICS registros_removidos = ROW_COUNT;
    RETURN registros_removidos;
END;
$$ language 'plpgsql';

-- 09_insert_sample_data.sql
-- Dados de exemplo para desenvolvimento (opcional)
-- Usuário de teste
INSERT INTO users (email, password_hash, nome) 
VALUES (
    'admin@teste.com', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/VcSAg9S6O', -- senha: admin123
    'Administrador'
) ON CONFLICT (email) DO NOTHING;

-- Configurações de exemplo para o usuário de teste
DO $$
DECLARE
    user_id INTEGER;
BEGIN
    SELECT id INTO user_id FROM users WHERE email = 'admin@teste.com';
    
    IF user_id IS NOT NULL THEN
        INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio) VALUES
        (user_id, 'SERPAPI_KEY', '', 'Chave da API do SerpAPI para busca na Amazon', 'password', true),
        (user_id, 'SUPABASE_URL', '', 'URL do projeto Supabase', 'string', true),
        (user_id, 'SUPABASE_KEY', '', 'Chave de serviço do Supabase', 'password', true)
        ON CONFLICT (user_id, chave) DO NOTHING;
    END IF;
END $$;