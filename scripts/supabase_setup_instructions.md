# Configuração do Sistema de Alertas com Supabase

## 1. Configuração do Supabase

### Habilitar Extensão HTTP
```sql
-- Execute no SQL Editor do Supabase
CREATE EXTENSION IF NOT EXISTS http;
```

### Configurar Variáveis de Ambiente
No painel do Supabase, vá em **Settings > Environment Variables** e adicione:
- `SUPABASE_ALERT_TOKEN`: Token de autenticação para sua API Flask
- `FLASK_API_URL`: URL da sua API Flask (ex: https://sua-api.com)

## 2. Executar Scripts SQL

### Passo 1: Atualizar Schema da Tabela
Execute o script `06_create_alertas_table.sql` atualizado para corrigir o schema.

### Passo 2: Criar Funções Supabase
Execute o script `supabase_alert_function.sql` no SQL Editor do Supabase.

## 3. Configuração da API Flask

### Variável de Ambiente
Adicione no seu arquivo `.env`:
```env
SUPABASE_ALERT_TOKEN=seu_token_secreto_aqui
```

### Endpoints Disponíveis
A API Flask agora possui os seguintes endpoints:

- `POST /alert/api/check-alerts` - Verificar alertas para produtos
- `POST /alert/api/trigger-alert` - Disparar alerta específico

## 4. Como Funciona

### Fluxo Automático
1. Quando um novo produto é inserido na tabela `ofertas`, o trigger é executado
2. O trigger chama a função `trigger_alert_check()`
3. A função verifica se há alertas ativos que correspondem ao produto
4. Se encontrar, faz uma requisição HTTP para a API Flask
5. A API Flask processa o alerta e pode enviar notificações

### Verificação Manual
```sql
-- Verificar todos os alertas
SELECT * FROM manual_alert_check();

-- Verificar alertas de um usuário específico
SELECT * FROM manual_alert_check(1);
```

### Execução Direta
```sql
-- Executar verificação completa
SELECT check_price_alerts();
```

## 5. Testando o Sistema

### Teste 1: Criar um Alerta
1. Acesse a interface web
2. Vá para a página de alertas
3. Crie um novo alerta com:
   - Nome do produto
   - Preço alvo
   - Tipo de alerta
   - Telefone para notificação

### Teste 2: Simular Produto
```sql
-- Inserir um produto de teste
INSERT INTO ofertas (
    titulo, preco, preco_numerico, url_produto, marketplace, criado_em
) VALUES (
    'Smartphone Samsung Galaxy S23',
    'R$ 2.500,00',
    2500.00,
    'https://exemplo.com/produto',
    'MercadoLivre',
    NOW()
);
```

### Teste 3: Verificar Logs
Monitore os logs do Supabase e da API Flask para verificar se as requisições estão sendo feitas corretamente.

## 6. Troubleshooting

### Problema: Função HTTP não encontrada
**Solução**: Execute `CREATE EXTENSION IF NOT EXISTS http;`

### Problema: Erro 401 Unauthorized
**Solução**: Verifique se o token `SUPABASE_ALERT_TOKEN` está configurado corretamente

### Problema: API Flask não responde
**Solução**: 
1. Verifique se a URL está correta
2. Verifique se a API Flask está rodando
3. Verifique se o endpoint existe

### Problema: Alertas não são disparados
**Solução**:
1. Verifique se os alertas estão ativos
2. Verifique se os produtos correspondem aos critérios
3. Execute verificação manual para debug

## 7. Monitoramento

### Logs do Supabase
Monitore os logs no painel do Supabase para verificar execuções das funções.

### Logs da API Flask
Monitore os logs da aplicação Flask para verificar requisições recebidas.

### Métricas
- Total de alertas ativos
- Número de disparos por alerta
- Última execução de cada alerta

