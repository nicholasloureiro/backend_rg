# 5. CPF validation and duplicate handling

Date: 2026-04-19

## Status

Accepted

## Context

Brazilian CPFs have a well-defined check-digit algorithm. We were previously accepting any 11-digit string, which let invalid CPFs through until later failures. We also had race conditions when two pre-triage entries created persons with the same CPF.

For children (infants) there is no CPF — we need a placeholder.

## Decision

**1. Algorithmic validation** — `accounts/utils.py::validate_cpf(cpf: str) -> bool` checks the 11 digits, rejects all-same-digit patterns, and verifies both check digits.

**2. Validation happens at all entry points:**
- `ServiceOrderCreateAPIView`
- `ServiceOrderUpdateAPIView` (except for drafts — see ADR-0007)
- `ServiceOrderPreTriageAPIView`
- `ClientRegisterAPIView`
- `EmployeeRegisterSerializer.validate_cpf`

**3. Infant placeholder** — when `is_infant=True`, generate `CRIANCA-<uuid12>` as CPF. This bypasses validation but keeps the `unique=True` constraint happy.

**4. Race-safe merge** — when a CPF provided on OS update already exists for another person, we merge contacts/addresses and delete the temporary person. The deletion is wrapped in `transaction.atomic()` with `select_for_update()` to prevent double-deletion under concurrent requests.

## Consequences

- Invalid CPFs are caught early with a clear error instead of failing mysteriously later.
- Infant records don't pollute the CPF uniqueness space.
- Concurrent pre-triage + OS update on the same client no longer loses orders.
- `validate_cpf` is a pure function — easy to unit-test and reuse.
