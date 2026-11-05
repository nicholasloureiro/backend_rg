-- Auditoria de índices (ADR 0009). Somente leitura: não cria nem remove nada.
-- Rode em produção depois de alguns dias de uso normal; os contadores vêm do
-- último reset de estatísticas (stats_reset no fim).

-- 1. O que existe, quanto ocupa e quantas vezes foi usado
SELECT s.relname AS tabela,
       s.indexrelname AS indice,
       s.idx_scan AS usos,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS tamanho,
       i.indisunique AS unico,
       pg_get_indexdef(s.indexrelid) AS definicao
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.schemaname = 'public'
ORDER BY s.relname, s.idx_scan, pg_relation_size(s.indexrelid) DESC;

-- 2. Índices com as mesmas colunas, na mesma ordem (candidatos a remoção)
SELECT a.indrelid::regclass AS tabela,
       a.indexrelid::regclass AS indice,
       b.indexrelid::regclass AS igual_a
FROM pg_index a
JOIN pg_index b ON a.indrelid = b.indrelid
               AND a.indexrelid > b.indexrelid
               AND a.indkey::text = b.indkey::text
               AND a.indclass::text = b.indclass::text
               AND COALESCE(pg_get_expr(a.indpred, a.indrelid), '') = COALESCE(pg_get_expr(b.indpred, b.indrelid), '')
WHERE a.indrelid::regclass::text IN (
    'service_orders', 'service_order_items', 'person', 'persons_contacts', 'persons_adresses', 'events'
);

-- 3. Tamanho das tabelas principais e leituras sequenciais x por índice
SELECT relname AS tabela, n_live_tup AS linhas, seq_scan, idx_scan, n_tup_upd, n_tup_hot_upd,
       pg_size_pretty(pg_total_relation_size(relid)) AS total
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 12;

-- 4. Desde quando os contadores valem
SELECT stats_reset FROM pg_stat_database WHERE datname = current_database();
