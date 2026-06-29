"""Reconciliation tools — the deterministic 'hands' the detector agent calls.

These are pure functions over the CSVs. They re-derive the CORRECT billable quantity
and price from raw events, then compare against what was invoiced. Every tool is
independently unit-testable (no LLM, no network).
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import List

from config import get_billing_source
from .state import Finding

PERIOD_CLOSE = datetime(2026, 6, 1)   # events after this are 'late' for 2026-05
TIERS = [(0, 100_000, 0.0), (100_000, 1_000_000, 0.0008),
         (1_000_000, 10_000_000, 0.0005), (10_000_000, None, 0.0003)]
RECON_THRESHOLD = 0.005   # 0.5% — matches the documented alert threshold


def tier_price_total(qty: int) -> float:
    total = 0.0
    for lo, hi, price in TIERS:
        used = max(0, min(qty, hi if hi else qty) - lo)
        if used > 0:
            total += used * price
    return round(total, 2)


def dedup_events(events: List[dict]) -> List[dict]:
    """Drop duplicate idempotency keys (per account) — the documented rule."""
    seen, out = set(), []
    for e in events:
        key = (e["account_id"], e["idempotency_key"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def correct_billable_qty(events: List[dict]) -> int:
    """All metered usage that SHOULD be billed: de-duplicated, late events included."""
    return sum(int(e["quantity"]) for e in dedup_events(events))


def had_duplicates(events: List[dict]) -> bool:
    keys = [(e["account_id"], e["idempotency_key"]) for e in events]
    return len(keys) != len(set(keys))


def had_late_events(events: List[dict]) -> bool:
    return any(datetime.fromisoformat(e["timestamp"]) >= PERIOD_CLOSE for e in events)


def reconcile_account(account_id: str, events: List[dict], invoice: dict) -> Finding | None:
    """Compare correct vs invoiced for one account. Return a Finding or None."""
    correct_qty = correct_billable_qty(events)
    subscription_amount = float(invoice.get("subscription_amount", 0.0))
    correct_amount = round(subscription_amount + tier_price_total(correct_qty), 2)
    invoiced_amount = float(invoice["invoiced_amount"])
    invoiced_qty = int(invoice["invoiced_quantity"])

    # classify the root cause
    if had_late_events(events):
        issue = "unreconciled_late_event"
    elif had_duplicates(events):
        issue = "duplicate_event"
    elif abs(correct_amount - invoiced_amount) > 0.01:
        issue = "tier_misconfig"
    else:
        issue = None

    diff = round(correct_amount - invoiced_amount, 2)
    rel = abs(correct_amount - invoiced_amount) / max(correct_amount, 1.0)

    if issue is None and rel <= RECON_THRESHOLD:
        return None

    return Finding(
        account_id=account_id, issue=issue or "amount_mismatch",
        invoiced_amount=invoiced_amount, correct_amount=correct_amount,
        leakage_usd=diff,
        evidence=(f"qty invoiced={invoiced_qty} vs correct={correct_qty}; "
                  f"amount invoiced=${invoiced_amount} vs correct=${correct_amount} "
                  f"({rel:.1%} off)"),
    )


def run_reconciliation(data_dir: str = "data") -> List[Finding]:
    del data_dir  # compatibility; source now provides data.
    period = os.getenv("PERIOD", "2026-05")
    source = get_billing_source()

    try:
        accounts = source.list_accounts(period)
    except NotImplementedError as exc:
        # Clear error surfaced to users while keeping the agent run alive.
        print(f"[billing-source] {exc}")
        return []

    findings: List[Finding] = []
    for account in accounts:
        raw_events = source.get_events(account.account_id, period)
        raw_invoices = source.get_invoices(account.account_id, period)
        if not raw_invoices:
            continue
        invoice = raw_invoices[0]
        invoice_dict = {
            "account_id": invoice.account_id,
            "product_code": invoice.product_code,
            "period": invoice.period,
            "invoiced_quantity": str(invoice.invoiced_quantity),
            "invoiced_amount": str(invoice.invoiced_amount),
            "subscription_amount": str(invoice.subscription_amount),
        }
        event_dicts = [
            {
                "event_id": e.event_id,
                "account_id": e.account_id,
                "product_code": e.product_code,
                "quantity": str(e.quantity),
                "timestamp": e.timestamp.isoformat(),
                "idempotency_key": e.idempotency_key,
            }
            for e in raw_events
        ]
        finding = reconcile_account(account.account_id, event_dicts, invoice_dict)
        if finding:
            findings.append(finding)
    return findings
