# 7. Draft save bypasses all validation

Date: 2026-04-19

## Status

Accepted

## Context

Attendants fill out long OS forms incrementally — client data, items, sizes, payments. They often need to save mid-flow (phone rings, client leaves). Requiring all fields to be valid before saving forces them to either finish in one go or lose their work.

The regular update endpoint validates CPF, requires valid dates, requires full payment data, and deletes+recreates items.

## Decision

The update endpoint (`PUT /api/v1/service-orders/<id>/update/`) accepts a `?draft=true` query parameter. When present, the view dispatches to a dedicated `_save_draft()` method that:

1. **Skips serializer validation** — reads `request.data` directly
2. **Skips CPF algorithmic validation** — saves whatever CPF was provided (if any)
3. **Skips client merge/creation** — only updates fields on the existing renter
4. **Does NOT delete existing items** unless new items are sent in the payload
5. **Does NOT change phase** — OS stays in current phase
6. **Wraps each field assignment in try/except** — one bad field doesn't break the whole save

A draft save accepts literally any combination of fields (or none at all) and persists what it can.

The frontend exposes this as a "Salvar Rascunho" button visible on non-finalized/non-refused orders.

## Consequences

- Attendants can save partial progress any time without errors.
- Draft data is indistinguishable from a complete OS in the database — there's no `is_draft` flag. The phase (PENDENTE/EM_PRODUCAO) tells you how far along the OS is.
- Finalizing the OS (`Finalizar OS` button) uses the strict update path — full validation, items replacement, phase transition.
- Risk: a draft with garbage data can persist. Mitigated by the fact that fields are optional and the strict path validates on finalize.
