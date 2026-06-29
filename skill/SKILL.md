# revenue-leakage-investigator

Reusable investigation skill for deterministic revenue leakage analysis on synthetic,
Vynt-like billing data.

## When to use this skill

Use this skill when a user asks to:
- investigate billing discrepancies or revenue leakage,
- reconcile metering events against invoices,
- quantify under-billing or over-billing by account,
- explain leak drivers with deterministic evidence.

## Required tool surface (MCP)

This skill is designed to run against the local MCP server at `mcp/server.py`,
which exposes read-only reconciliation tools:

- `list_accounts(period)`
- `dedup_events(period, account_id)`
- `include_late_events(period, account_id)`
- `recompute_tier_price(quantity)`
- `reconcile_account(period, account_id)`

## Inputs

- `period` (format `YYYY-MM`, example: `2026-05`)
- optional account scope (default: all accounts)

## Investigation workflow

1. Validate `period` format and scope.
2. Call `list_accounts(period)` to enumerate account IDs.
3. For each account in scope:
   - call `reconcile_account(period, account_id)` for primary finding,
   - if needed, call `dedup_events` and `include_late_events` for deeper evidence.
4. Aggregate findings by:
   - root cause,
   - account,
   - net leakage (`correct_amount - invoiced_amount`).
5. Produce a concise summary:
   - number of flagged accounts,
   - top leakage drivers,
   - largest impacted accounts with evidence.

## Guardrails

- Read-only only: never mutate invoices, events, or external systems.
- Deterministic math only for amounts; do not delegate calculations to an LLM.
- If `BILLING_SOURCE=api` is selected and unimplemented, report clearly and stop safely.
- Keep claims grounded in tool outputs and explicit evidence fields.
- State clearly that dataset is synthetic (iso-Vynt), not real customer data.

## Output contract

Return:
- machine-friendly list of findings (`account_id`, `issue`, `leakage_usd`, `evidence`),
- human summary with quantified totals and top root causes,
- explicit note when no leakage is detected.
