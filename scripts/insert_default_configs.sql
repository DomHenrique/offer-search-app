-- Script para inserir configurações padrão após criação das tabelas

-- Inserir configurações padrão necessárias para usuários existentes
INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio)
SELECT 
    id as user_id,
    'SERPAPI_KEY' as chave,
    '' as valor,
    'Chave da API do SerpAPI para busca na Amazon' as descricao,
    'password' as tipo,
    true as obrigatorio
FROM users
WHERE id NOT IN (
    SELECT DISTINCT user_id FROM configuracoes WHERE chave = 'SERPAPI_KEY'
);

INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio)
SELECT 
    id as user_id,
    'SUPABASE_URL' as chave,
    '' as valor,
    'URL do projeto Supabase' as descricao,
    'string' as tipo,
    true as obrigatorio
FROM users
WHERE id NOT IN (
    SELECT DISTINCT user_id FROM configuracoes WHERE chave = 'SUPABASE_URL'
);

INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio)
SELECT 
    id as user_id,
    'SUPABASE_KEY' as chave,
    '' as valor,
    'Chave de serviço do Supabase' as descricao,
    'password' as tipo,
    true as obrigatorio
FROM users
WHERE id NOT IN (
    SELECT DISTINCT user_id FROM configuracoes WHERE chave = 'SUPABASE_KEY'
);