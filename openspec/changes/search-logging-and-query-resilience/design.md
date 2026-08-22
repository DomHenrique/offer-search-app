## Context

As buscas no aplicativo de ofertas precisam ser altamente tolerantes a termos importados de Notas Fiscais ou planilhas que contêm sufixos e detalhes em excesso (ex: `220v-eu painel br`, códigos de fabricante). Além disso, os administradores precisam de um dashboard de logs para auditar o uso, identificar termos sem ofertas e diagnosticar problemas de raspagem e bloqueios em tempo real.

## Goals / Non-Goals

**Goals:**
- Criar a tabela `search_logs` no Supabase e métodos em `database/db_manager.py` para registro assíncrono e consulta paginada.
- Implementar algoritmo de **Query Relaxation**:
  - Limpa ruídos como `220v-eu`, `110v-br`, `painel br`, parênteses, códigos soltos.
  - Se a busca principal retornar 0 ofertas, dispara automaticamente a versão relaxada.
  - Alerta o usuário no frontend: `Resultados encontrados com termo otimizado: "gerador delta 3 plus 1800w"`.
- Criar a blueprint `routes/logs_routes.py` com rotas `/logs` e `/logs/api/list`.
- Criar a interface visual `templates/logs/logs_list.html` com filtros (Sucesso, Vazio, Erro, Recuperado) e modal de detalhes do log.

**Non-Goals:**
- Bloquear a execução da busca em caso de falha de gravação do log (logging deve ser não-bloqueante).

## Decisions

### 1. Estrutura da Tabela `search_logs`
```sql
CREATE TABLE IF NOT EXISTS search_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    user_email TEXT,
    termo_original TEXT NOT NULL,
    termo_utilizado TEXT NOT NULL,
    status TEXT NOT NULL, -- 'SUCCESS', 'EMPTY', 'ERROR', 'FALLBACK_RECOVERED'
    total_ofertas INTEGER DEFAULT 0,
    ml_ofertas INTEGER DEFAULT 0,
    amazon_ofertas INTEGER DEFAULT 0,
    tempo_execucao_segundos REAL DEFAULT 0.0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 2. Algoritmo de Relaxamento de Query (`relax_search_query`)
```python
def relax_search_query(term: str) -> str:
    # 1. Remove sufixos como '-eu', '-br', '-us', '220v-eu', etc.
    # 2. Remove pontuações e parênteses estranhos
    # 3. Mantém apenas palavras-chave relevantes (máximo 4-5 palavras principais)
```

### 3. Painel Visual `/logs`
- Acessível no menu superior da barra de navegação.
- Cards estatísticos com contadores em tempo real.
- Tabela moderna com badges coloridos e link para testar o termo novamente com 1 clique.

## Risks / Trade-offs

- **[Tabela `search_logs` ausente no Supabase]** → Tratamento gracioso no `db_manager.py` com criação automática ou fallback silencioso para não interromper a busca do usuário.
