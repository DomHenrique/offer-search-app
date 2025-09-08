-- Função Supabase para verificar alertas e chamar API Flask
-- Esta função deve ser executada no SQL Editor do Supabase

-- 1. Criar função para verificar alertas
CREATE OR REPLACE FUNCTION check_price_alerts()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    alert_record RECORD;
    product_record RECORD;
    api_url TEXT;
    api_token TEXT;
    request_body JSONB;
    response_status INTEGER;
    response_body TEXT;
BEGIN
    -- Configurar URL da API Flask (substitua pela sua URL)
    api_url := 'https://sua-api-flask.com/alert/api/check-alerts';
    api_token := 'seu_token_aqui'; -- Configure no .env como SUPABASE_ALERT_TOKEN
    
    -- Buscar todos os alertas ativos
    FOR alert_record IN 
        SELECT a.*, u.email, u.nome
        FROM alertas a
        JOIN users u ON a.user_id = u.id
        WHERE a.ativo = true
    LOOP
        -- Buscar produtos recentes que correspondem ao termo do alerta
        FOR product_record IN
            SELECT *
            FROM ofertas
            WHERE LOWER(titulo) LIKE '%' || LOWER(alert_record.produto_nome) || '%'
            AND criado_em > NOW() - INTERVAL '1 hour' -- Produtos das últimas horas
            ORDER BY criado_em DESC
            LIMIT 10
        LOOP
            -- Verificar se o preço atende aos critérios do alerta
            IF (alert_record.tipo_alerta = 'menor_ou_igual' AND product_record.preco_numerico <= alert_record.preco_alvo)
               OR (alert_record.tipo_alerta = 'maior_ou_igual' AND product_record.preco_numerico >= alert_record.preco_alvo)
            THEN
                -- Preparar dados para enviar à API Flask
                request_body := jsonb_build_object(
                    'user_id', alert_record.user_id,
                    'alert_id', alert_record.id,
                    'product', jsonb_build_object(
                        'titulo', product_record.titulo,
                        'preco', product_record.preco,
                        'preco_numerico', product_record.preco_numerico,
                        'url_produto', product_record.url_produto,
                        'marketplace', product_record.marketplace
                    ),
                    'alert', jsonb_build_object(
                        'produto_nome', alert_record.produto_nome,
                        'preco_alvo', alert_record.preco_alvo,
                        'tipo_alerta', alert_record.tipo_alerta,
                        'telefone', alert_record.telefone
                    )
                );
                
                -- Fazer requisição HTTP para a API Flask
                BEGIN
                    SELECT status, content INTO response_status, response_body
                    FROM http((
                        'POST',
                        api_url,
                        ARRAY[http_header('Authorization', 'Bearer ' || api_token),
                              http_header('Content-Type', 'application/json')],
                        'application/json',
                        request_body::text
                    ));
                    
                    -- Se a requisição foi bem-sucedida, atualizar contador de disparos
                    IF response_status = 200 THEN
                        UPDATE alertas 
                        SET total_disparos = total_disparos + 1,
                            ultimo_disparo = NOW()
                        WHERE id = alert_record.id;
                        
                        RAISE NOTICE 'Alerta % disparado para produto %', alert_record.id, product_record.titulo;
                    ELSE
                        RAISE WARNING 'Erro ao chamar API Flask: Status % - %', response_status, response_body;
                    END IF;
                    
                EXCEPTION WHEN OTHERS THEN
                    RAISE WARNING 'Erro na requisição HTTP: %', SQLERRM;
                END;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

-- 2. Criar função para ser chamada por triggers
CREATE OR REPLACE FUNCTION trigger_alert_check()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Executar verificação de alertas em background
    PERFORM pg_notify('alert_check', 'new_product_added');
    RETURN NEW;
END;
$$;

-- 3. Criar trigger para executar verificação quando novos produtos são adicionados
DROP TRIGGER IF EXISTS check_alerts_trigger ON ofertas;
CREATE TRIGGER check_alerts_trigger
    AFTER INSERT ON ofertas
    FOR EACH ROW
    EXECUTE FUNCTION trigger_alert_check();

-- 4. Criar função para executar verificação manual
CREATE OR REPLACE FUNCTION manual_alert_check(user_id_param INTEGER DEFAULT NULL)
RETURNS TABLE(
    alert_id INTEGER,
    product_title TEXT,
    product_price DECIMAL,
    target_price DECIMAL,
    alert_type TEXT,
    triggered_at TIMESTAMP
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    alert_record RECORD;
    product_record RECORD;
    api_url TEXT;
    api_token TEXT;
    request_body JSONB;
    response_status INTEGER;
    response_body TEXT;
BEGIN
    -- Configurar URL da API Flask
    api_url := 'https://sua-api-flask.com/alert/api/check-alerts';
    api_token := 'seu_token_aqui';
    
    -- Buscar alertas (todos ou de um usuário específico)
    FOR alert_record IN 
        SELECT a.*, u.email, u.nome
        FROM alertas a
        JOIN users u ON a.user_id = u.id
        WHERE a.ativo = true
        AND (user_id_param IS NULL OR a.user_id = user_id_param)
    LOOP
        -- Buscar produtos que correspondem ao alerta
        FOR product_record IN
            SELECT *
            FROM ofertas
            WHERE LOWER(titulo) LIKE '%' || LOWER(alert_record.produto_nome) || '%'
            AND criado_em > NOW() - INTERVAL '24 hours' -- Produtos das últimas 24 horas
            ORDER BY criado_em DESC
            LIMIT 5
        LOOP
            -- Verificar se o preço atende aos critérios
            IF (alert_record.tipo_alerta = 'menor_ou_igual' AND product_record.preco_numerico <= alert_record.preco_alvo)
               OR (alert_record.tipo_alerta = 'maior_ou_igual' AND product_record.preco_numerico >= alert_record.preco_alvo)
            THEN
                -- Preparar dados para a API
                request_body := jsonb_build_object(
                    'user_id', alert_record.user_id,
                    'products', jsonb_build_array(
                        jsonb_build_object(
                            'titulo', product_record.titulo,
                            'preco', product_record.preco,
                            'preco_numerico', product_record.preco_numerico,
                            'url_produto', product_record.url_produto,
                            'marketplace', product_record.marketplace
                        )
                    )
                );
                
                -- Fazer requisição para a API Flask
                BEGIN
                    SELECT status, content INTO response_status, response_body
                    FROM http((
                        'POST',
                        api_url,
                        ARRAY[http_header('Authorization', 'Bearer ' || api_token),
                              http_header('Content-Type', 'application/json')],
                        'application/json',
                        request_body::text
                    ));
                    
                    -- Retornar resultado
                    IF response_status = 200 THEN
                        alert_id := alert_record.id;
                        product_title := product_record.titulo;
                        product_price := product_record.preco_numerico;
                        target_price := alert_record.preco_alvo;
                        alert_type := alert_record.tipo_alerta;
                        triggered_at := NOW();
                        RETURN NEXT;
                    END IF;
                    
                EXCEPTION WHEN OTHERS THEN
                    RAISE WARNING 'Erro na requisição HTTP: %', SQLERRM;
                END;
            END IF;
        END LOOP;
    END LOOP;
    
    RETURN;
END;
$$;

-- 5. Comentários de uso:
/*
COMO USAR:

1. Configure as variáveis de ambiente no Supabase:
   - SUPABASE_ALERT_TOKEN: Token de autenticação para a API Flask
   - FLASK_API_URL: URL da sua API Flask

2. Execute este script no SQL Editor do Supabase

3. Para verificar alertas manualmente:
   SELECT * FROM manual_alert_check(); -- Todos os usuários
   SELECT * FROM manual_alert_check(1); -- Usuário específico (ID 1)

4. Para executar verificação automática:
   SELECT check_price_alerts();

5. O trigger será executado automaticamente quando novos produtos forem inseridos na tabela 'ofertas'

CONFIGURAÇÃO ADICIONAL:

- Certifique-se de que a extensão 'http' está habilitada no Supabase
- Configure o token de autenticação na variável de ambiente
- Ajuste a URL da API Flask conforme necessário
- Configure o intervalo de tempo para buscar produtos recentes
*/

