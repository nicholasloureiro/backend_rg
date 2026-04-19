# 3. Service order phase as an explicit state machine

Date: 2026-04-19

## Status

Accepted

## Context

A service order (OS) moves through several business-meaningful states:

```
PENDENTE → EM_PRODUCAO → AGUARDANDO_RETIRADA → AGUARDANDO_DEVOLUCAO → FINALIZADO
                                                                      ↓
                                                                   RECUSADA (from any phase)
                                                                   ATRASADO (derived)
```

Each transition triggers side effects:
- `PENDENTE → EM_PRODUCAO`: set `production_date`
- `AGUARDANDO_RETIRADA → AGUARDANDO_DEVOLUCAO`: set `data_retirado`, optionally record remaining payment
- `AGUARDANDO_DEVOLUCAO → FINALIZADO`: set `data_devolvido`, `data_finalizado`
- any → `RECUSADA`: set `data_recusa`, require `justification_reason`
- `RECUSADA → PENDENTE` (resgate): set `data_resgate`, clear recusa fields

We need admins to override transitions (go backwards) without breaking business data.

## Decision

Store phase as a FK `ServiceOrder.service_order_phase → ServiceOrderPhase`. Each transition is a **dedicated endpoint** that enforces the state machine rules:

| Endpoint | From | To |
|----------|------|-----|
| `POST /<id>/mark-ready/` | EM_PRODUCAO | AGUARDANDO_RETIRADA |
| `POST /<id>/mark-retrieved/` | EM_PRODUCAO / AGUARDANDO_RETIRADA | AGUARDANDO_DEVOLUCAO (rental) or FINALIZADO (sale) |
| `POST /<id>/mark-paid/` | AGUARDANDO_DEVOLUCAO | FINALIZADO |
| `POST /<id>/refuse/` | any non-final | RECUSADA |
| `POST /<id>/return-to-pending/` | any non-FINALIZADO | PENDENTE |
| `POST /<id>/change-phase/` | any (admin only) | any (clears forward timestamps) |

`ATRASADO` is a **derived view**, not a stored phase — it's a query over `AGUARDANDO_DEVOLUCAO` orders past their `devolucao_date`.

Sale orders (`service_type in ["Venda", "Compra"]`) skip `AGUARDANDO_RETIRADA`/`AGUARDANDO_DEVOLUCAO` and go straight to `FINALIZADO` on update.

## Consequences

- Phase transitions are auditable — each endpoint logs in DB via `BaseModel` fields (`date_updated`, `updated_by`).
- Admins can override via `change-phase` without bypassing core invariants (timestamps are cleared appropriately).
- Derived `ATRASADO` means no need to schedule jobs to transition orders — the list is always accurate at query time.
- Adding a new phase requires updating multiple endpoints and the frontend tabs.
