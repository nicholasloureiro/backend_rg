# 6. Planilha is payment-centric, not OS-centric

Date: 2026-04-19

## Status

Accepted

## Context

The ops team uses an Excel spreadsheet to track every payment, with columns: Data, N° OS, Cliente (role), Atendente, Fechamento, Canal, Nome Cliente, Valor, Forma Pgto, Valor Total Venda, Justificativa.

A single OS can generate multiple rows — one for the sinal on day X, another for the restante on day Y. When filtering "today", they want to see every payment made today, even for old orders.

Our first implementation returned one row per OS filtered by `order_date`. Users reported that today's Financeiro showed R$5,910 but the Planilha showed R$5,460 for the same day — the difference was restante payments on older OS that didn't appear.

## Decision

The Planilha endpoint (`GET /api/v1/service-orders/planilha/`) returns **one row per payment entry**, not per OS. Each row contains:

- `data`: the payment's `data` field from `payment_details` (not the OS `order_date`)
- OS-level columns (numero_os, cliente, atendente, canal, etc.) copied from the parent OS
- `valor`: this specific payment's amount (negative for estorno)
- `forma_pgto`: this payment's method
- `tipo`: the payment type (sinal/restante/parcial/indenizacao/estorno)

Orders with no payments (e.g. PENDENTE) get one fallback row using `order_date` and `valor=0`.

Totalizer rules (to avoid double-counting OS metrics across multiple payment rows):

| Metric | Rule |
|--------|------|
| Total de OS | Count unique OS where the **sinal** row falls in the filter range |
| Fechadas | Same, but `fechamento == "SIM"` |
| Conversão | Fechadas / Total de OS |
| Total Vendido | Sum of `total_value` from sinal rows only (non-virtual) |
| Total Recebido | Sum of all payment amounts in range (all types, all orders) |

`fechamento` values:
- `SIM` for confirmed phases (EM_PRODUCAO, AGUARDANDO_RETIRADA, AGUARDANDO_DEVOLUCAO, FINALIZADO)
- `NÃO` for RECUSADA
- empty for PENDENTE and virtual entries

## Consequences

- Planilha totals match Financeiro totals for a given date.
- Metrics reflect the correct business intent: "OS sold today" (sinal today) vs "money received today" (any payment today).
- Adding a new `tipo` requires updating both Planilha totals and Financeiro display logic.
