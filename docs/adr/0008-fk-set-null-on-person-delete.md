# 8. Foreign keys to Person use SET_NULL, not CASCADE

Date: 2026-04-19

## Status

Accepted

## Context

Originally `ServiceOrder.renter`, `.employee`, `.attendant` were `on_delete=CASCADE`. When an admin wanted to delete a client (e.g. GDPR-style removal, or a data cleanup), all their service orders — potentially with valid financial history — would be cascade-deleted too. This made client deletion effectively impossible without destroying audit trail.

## Decision

Change `on_delete` for all three FKs on `ServiceOrder` (`renter`, `employee`, `attendant`) to `SET_NULL`. The OS survives the person's deletion; the column goes to NULL.

Admin-only client delete endpoint: `DELETE /api/v1/clients/<person_id>/delete/`
- Removes contacts and addresses
- Sets all referencing `ServiceOrder.renter` to NULL
- Deletes the Person

Admin-only CPF edit endpoint: `PUT /api/v1/clients/<person_id>/update-cpf/`
- Validates the new CPF algorithmically
- Checks uniqueness
- Updates the Person's CPF

Consumers of the API (list/detail views, dashboard aggregations) must be null-safe — any code path accessing `order.renter.name` must check for None.

## Consequences

- Pros: Admin workflows for client management are possible without destroying financial records.
- Cons: Every serializer and list view had to be audited for `None` renter/employee/attendant. A few `__str__` methods crashed until updated.
- Orphaned OSs (no renter) appear with `client_name` fallback or an empty "Nome Cliente" cell in reports.
