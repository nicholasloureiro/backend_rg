# 9. Database indexes managed via indexes.sql, not Django migrations

Date: 2026-04-19

## Status

Accepted

## Context

We analyzed 150+ query patterns across the API and identified significant performance bottlenecks on `service_orders` (date filtering, phase filtering, FK joins), `persons_contacts` (recent-contact lookups), and text search fields.

Django supports `Meta.indexes` and `db_index=True`, but those generate migrations that run synchronously on deploy. For a production DB with millions of rows, creating a GIN trigram index can lock a table for minutes.

## Decision

Maintain indexes in a standalone `indexes.sql` file at the repo root. It uses `CREATE INDEX IF NOT EXISTS` so it's idempotent. The DBA applies it manually (or via a controlled deploy script) with `psql -f indexes.sql`.

Key indexes:
- Compound: `(is_virtual, order_date, service_order_phase_id)` — the single most-hit combination
- Compound: `(employee_id, order_date, service_order_phase_id)` — dashboard metrics
- Date fields: `order_date`, `prova_date`, `retirada_date`, `devolucao_date`
- Recent-lookup compound: `(person_id, date_created DESC, id DESC)` on persons_contacts and persons_adresses
- GIN trigram (optional, requires `pg_trgm` extension) on `person.name` and `products.nome_produto` for ILIKE searches

## Consequences

- Index creation can be scheduled during low-traffic windows (Django migrations would run on deploy regardless).
- `CREATE INDEX CONCURRENTLY` can be used in indexes.sql when the DBA wants non-locking index builds.
- Risk: indexes.sql can drift from the ORM. We audit quarterly by comparing `pg_indexes` to indexes.sql.
- Django's own `db_index=True` and unique constraints remain in models (they're cheap and migration-friendly). indexes.sql is for the compound/partial/GIN indexes.
