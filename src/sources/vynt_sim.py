"""Deterministic synthetic Vynt-like billing source (hybrid subscription + usage)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Dict, List

from .base import Account, BillingSource, Invoice, UsageEvent

PRODUCT = "platform"
TIERS = [
    (0, 100_000, 0.0),
    (100_000, 1_000_000, 0.0008),
    (1_000_000, 10_000_000, 0.0005),
    (10_000_000, None, 0.0003),
]
PLANS = {
    "Starter": 49.0,
    "Pro": 299.0,
    "Scale": 999.0,
}
ACCOUNT_NAMES = [
    "Acme Robotics",
    "Bluebird Health",
    "Northstar Retail",
    "Vertex Legal",
    "Nimbus Security",
    "Atlas Mobility",
    "Helio Energy",
    "Cedar Biotech",
    "Pioneer Labs",
    "Delta Logistics",
    "Sora Learning",
    "Beacon Finance",
    "Quartz Media",
    "Summit AI",
    "Oakline HR",
    "Pulse Commerce",
    "Artemis Cloud",
    "Vanta Ops",
    "Meridian Fleet",
    "Forge Analytics",
]


def tier_price_total(qty: int) -> float:
    total = 0.0
    for lo, hi, price in TIERS:
        used = max(0, min(qty, hi if hi else qty) - lo)
        if used > 0:
            total += used * price
    return round(total, 2)


class VyntSimulatorSource(BillingSource):
    """In-memory deterministic source with injected discrepancies and ground truth."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self._cache: Dict[str, Dict[str, object]] = {}

    def _build_period(self, period: str) -> Dict[str, object]:
        if period in self._cache:
            return self._cache[period]

        rng = random.Random(f"{self.seed}:{period}")
        base = datetime(2026, 5, 1)

        accounts: List[Account] = []
        events_by_account: Dict[str, List[UsageEvent]] = {}
        invoices_by_account: Dict[str, List[Invoice]] = {}
        ground_truth: List[dict] = []

        event_counter = 0
        for i in range(20):
            account_id = f"acct_{i + 1:03d}"
            plan = rng.choices(["Starter", "Pro", "Scale"], weights=[0.5, 0.35, 0.15], k=1)[0]
            account = Account(account_id=account_id, name=ACCOUNT_NAMES[i], plan=plan)
            accounts.append(account)

            true_qty = rng.randint(50_000, 3_000_000)
            batches = rng.randint(3, 6)
            emitted = 0
            account_events: List[UsageEvent] = []

            for b in range(batches):
                q = true_qty // batches if b < batches - 1 else true_qty - emitted
                emitted += q
                ts = base + timedelta(days=rng.randint(0, 30), hours=rng.randint(0, 23))
                account_events.append(
                    UsageEvent(
                        event_id=f"evt_{event_counter}",
                        account_id=account_id,
                        product_code=PRODUCT,
                        quantity=q,
                        timestamp=ts,
                        idempotency_key=f"{account_id}-{b}",
                    )
                )
                event_counter += 1

            invoiced_qty = true_qty
            issue = None
            roll = rng.random()
            if roll < 0.20:
                dup = account_events[-1].model_copy()
                dup.event_id = f"evt_{event_counter}"
                account_events.append(dup)
                event_counter += 1
                issue = "duplicate_event"
            elif roll < 0.45:
                late_q = rng.randint(20_000, 120_000)
                account_events.append(
                    UsageEvent(
                        event_id=f"evt_{event_counter}",
                        account_id=account_id,
                        product_code=PRODUCT,
                        quantity=late_q,
                        timestamp=base + timedelta(days=33),
                        idempotency_key=f"{account_id}-late",
                    )
                )
                event_counter += 1
                true_qty += late_q
                issue = "unreconciled_late_event"
            elif roll < 0.60:
                issue = "tier_misconfig"

            subscription_amount = PLANS[plan]
            if issue == "tier_misconfig":
                usage_amount = round(invoiced_qty * 0.0003, 2)
            else:
                usage_amount = tier_price_total(invoiced_qty)

            invoices_by_account[account_id] = [
                Invoice(
                    account_id=account_id,
                    product_code=PRODUCT,
                    period=period,
                    invoiced_quantity=invoiced_qty,
                    invoiced_amount=round(subscription_amount + usage_amount, 2),
                    subscription_amount=subscription_amount,
                )
            ]
            events_by_account[account_id] = account_events

            if issue:
                ground_truth.append({"account_id": account_id, "issue": issue})

        payload = {
            "accounts": accounts,
            "events": events_by_account,
            "invoices": invoices_by_account,
            "ground_truth": ground_truth,
        }
        self._cache[period] = payload
        return payload

    def list_accounts(self, period: str) -> List[Account]:
        return self._build_period(period)["accounts"]  # type: ignore[return-value]

    def get_events(self, account_id: str, period: str) -> List[UsageEvent]:
        events = self._build_period(period)["events"]  # type: ignore[assignment]
        return list(events.get(account_id, []))

    def get_invoices(self, account_id: str, period: str) -> List[Invoice]:
        invoices = self._build_period(period)["invoices"]  # type: ignore[assignment]
        return list(invoices.get(account_id, []))

    def get_ground_truth(self, period: str) -> List[dict]:
        return list(self._build_period(period)["ground_truth"])  # type: ignore[return-value]
