# 4. Store payment history in a JSONField on ServiceOrder

Date: 2026-04-19

## Status

Accepted

## Context

A service order can have multiple payments over time: sinal (down payment), restante (remainder), parcial (installments), indenização (client pays for damage), and estorno (refund). Each payment has an amount, a method (PIX, credit, debit, etc.), a type, and a date. We need to:

- Record individual payments for financial reconciliation
- Report total received per day/method (Financeiro page)
- Produce a spreadsheet where each row is a single payment
- Track when a payment was actually made (could be different from order creation date)

Options considered:
1. **Dedicated `Payment` table** with FK to `ServiceOrder` — normalized, flexible, but adds complexity and migrations.
2. **JSONField `payment_details` on ServiceOrder** — pragmatic, queryable via PostgreSQL JSON ops, atomic with the order.

## Decision

Use a **JSONField** `ServiceOrder.payment_details` containing a list of entries:

```json
[
  {"amount": 150.00, "forma_pagamento": "PIX", "tipo": "sinal", "data": "2026-03-24T14:30:00"},
  {"amount": 150.00, "forma_pagamento": "credito", "tipo": "restante", "data": "2026-03-28T10:00:00"},
  {"amount": 50.00, "forma_pagamento": "PIX", "tipo": "estorno", "data": "2026-03-29T09:00:00"}
]
```

Valid `tipo` values: `sinal`, `restante`, `parcial`, `indenizacao`, `estorno`.

Rules:
- `advance_payment` (decimal field on OS) is the sum of all entries' amounts. It's the "single source of truth" for aggregations.
- `estorno` entries are stored as positive amounts but treated as negative (subtracted) in finance totals.
- The Financeiro and Planilha endpoints iterate `payment_details` and filter by the entry's `data`, not the OS `order_date`. This is how a payment made today on an old OS appears in today's report.

## Consequences

- **Pros:** No schema changes when payment types evolve. One query joins OS + payments. Migrations trivial.
- **Cons:** No FK integrity on payment entries. No per-payment row-level permissions. Harder to index individual fields (but we rarely need that).
- Frontend and backend must agree on the JSON shape; breaking changes are a migration pain.
- Future: if we need per-payment rows (e.g. attach receipts), we can migrate to a `Payment` table without breaking the existing JSON data.
