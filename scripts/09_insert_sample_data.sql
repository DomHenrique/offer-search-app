-- Dados de exemplo para desenvolvimento (opcional)
-- Usuário de teste
INSERT INTO users (email, password_hash, nome) 
VALUES (
    'admin@teste.com', 
    'pbkdf2:sha256:600000$OOPjlb2lpHhFnC6Y$1db123480830bed903c42a9077aa341fa9c4df0f3bb60899de3ba0cf3dc09187', -- senha: admin123
    'Administrador'
) ON CONFLICT (email) DO NOTHING;

-- Configurações de exemplo para o usuário de teste
DO $$
DECLARE
    v_user_id INTEGER;
BEGIN
    SELECT id INTO v_user_id FROM users WHERE email = 'admin@teste.com';
    
    IF v_user_id IS NOT NULL THEN
        INSERT INTO configuracoes (user_id, chave, valor, descricao, tipo, obrigatorio) VALUES
        (v_user_id, 'SERPAPI_KEY', '', 'Chave da API do SerpAPI para busca na Amazon', 'password', true),
        (v_user_id, 'SUPABASE_URL', '', 'URL do projeto Supabase', 'string', true),
        (v_user_id, 'SUPABASE_KEY', '', 'Chave de serviço do Supabase', 'password', true)
        ON CONFLICT (user_id, chave) DO NOTHING;
    END IF;
END $$;
