"""Deterministic synthetic Vynt-like billing source (hybrid subscription + usage)."""
from __future__ import annotations

import os
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
        self.scenario_rates = {
            "proration_failed": float(os.getenv("SCENARIO_RATE_PRORATION_FAILED", "0.18")),
            "discount_not_expired": float(os.getenv("SCENARIO_RATE_DISCOUNT_NOT_EXPIRED", "0.18")),
            "dunning_gap": float(os.getenv("SCENARIO_RATE_DUNNING_GAP", "0.16")),
            "late_events_unbilled": float(os.getenv("SCENARIO_RATE_LATE_EVENTS_UNBILLED", "0.18")),
            "missing_dedup": float(os.getenv("SCENARIO_RATE_MISSING_DEDUP", "0.16")),
            "tier_step_error": float(os.getenv("SCENARIO_RATE_TIER_STEP_ERROR", "0.14")),
        }
        self.no_issue_rate = float(os.getenv("SCENARIO_RATE_NO_ISSUE", "0.20"))

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
        guaranteed = [name for name, rate in self.scenario_rates.items() if rate > 0.0]
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
            usage_amount_correct = tier_price_total(invoiced_qty)
            subscription_amount = PLANS[plan]
            issue = None

            # Guarantee one sample per enabled scenario for evaluation stability.
            if i < len(guaranteed):
                scenario = guaranteed[i]
            else:
                weighted = []
                for name, rate in self.scenario_rates.items():
                    if rate > 0:
                        weighted.extend([name] * max(1, int(rate * 100)))
                weighted.extend(["none"] * max(1, int(self.no_issue_rate * 100)))
                scenario = rng.choice(weighted) if weighted else "none"

            usage_amount = usage_amount_correct
            product_code = PRODUCT
            if scenario == "missing_dedup":
                dup = account_events[-1].model_copy()
                dup.event_id = f"evt_{event_counter}"
                account_events.append(dup)
                event_counter += 1
                issue = "missing_dedup"
            elif scenario == "late_events_unbilled":
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
                issue = "late_events_unbilled"
            elif scenario == "tier_step_error":
                usage_amount = round(invoiced_qty * 0.0003, 2)
                issue = "tier_step_error"
            elif scenario == "discount_not_expired":
                discount_pct = rng.choice([0.15, 0.20, 0.25, 0.30])
                usage_amount = round(usage_amount_correct * (1.0 - discount_pct), 2)
                issue = "discount_not_expired"
            elif scenario == "dunning_gap":
                usage_amount = 0.0
                issue = "dunning_gap"
            elif scenario == "proration_failed":
                proration_delta = rng.uniform(45.0, 180.0)
                usage_amount = round(max(0.0, usage_amount_correct - proration_delta), 2)
                issue = "proration_failed"

            if issue:
                product_code = f"{PRODUCT}#{issue}"

            invoices_by_account[account_id] = [
                Invoice(
                    account_id=account_id,
                    product_code=product_code,
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
