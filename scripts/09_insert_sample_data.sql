-- Dados de exemplo para desenvolvimento (opcional)
-- Usuário de teste
INSERT INTO users (email, password_hash, nome) 
VALUES (
    'admin@teste.com', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/VcSAg9S6O', -- senha: admin123
    'Administrador'
) ON CONFLICT (email) DO NOTHING;

-- Configurações de exemplo para o usuário de teste
DO $
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
END $;
