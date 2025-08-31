-- Script de verificação das tabelas
SELECT 'users' as table_name, COUNT(*) as row_count FROM users
UNION ALL
SELECT 'ofertas' as table_name, COUNT(*) as row_count FROM ofertas
UNION ALL
SELECT 'produtos_aprovados' as table_name, COUNT(*) as row_count FROM produtos_aprovados
UNION ALL
SELECT 'agendamentos' as table_name, COUNT(*) as row_count FROM agendamentos
UNION ALL
SELECT 'historico_buscas' as table_name, COUNT(*) as row_count FROM historico_buscas
UNION ALL
SELECT 'alertas' as table_name, COUNT(*) as row_count FROM alertas
UNION ALL
SELECT 'configuracoes' as table_name, COUNT(*) as row_count FROM configuracoes;