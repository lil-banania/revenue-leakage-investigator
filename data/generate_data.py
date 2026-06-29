"""Generate a synthetic but realistic billing dataset with INJECTED discrepancies.

Two tables:
  events.csv   — metering events (account, product, quantity, timestamp, idempotency_key)
  invoices.csv — invoiced quantity & amount per account/product/period

We deliberately inject the two leakage drivers from the docs:
  1. Duplicate events (over-metering -> potential over-billing)
  2. Unreconciled late events (metered-but-not-invoiced -> under-billing / leakage)
  3. Tier misconfiguration (invoiced below correct tier price)

The point: the agent's job is to FIND these, and we know the ground truth, so we can
evaluate it. Deterministic via a fixed seed.
"""
from __future__ import annotations
import csv
import os
import random
from datetime import datetime, timedelta

SEED = 42
PERIOD = "2026-05"
ACCOUNTS = [f"acct_{i:03d}" for i in range(1, 21)]
PRODUCT = "platform"

# graduated tier prices (must match a reference the agent also knows)
TIERS = [(0, 100_000, 0.0), (100_000, 1_000_000, 0.0008),
         (1_000_000, 10_000_000, 0.0005), (10_000_000, None, 0.0003)]


def tier_price_total(qty: int) -> float:
    total, remaining, prev = 0.0, qty, 0
    for lo, hi, price in TIERS:
        cap = (hi - lo) if hi else remaining
        used = max(0, min(qty, hi if hi else qty) - lo)
        if used > 0:
            total += used * price
        prev = lo
    return round(total, 2)


def main(out_dir: str = "data"):
    random.seed(SEED)
    os.makedirs(out_dir, exist_ok=True)
    base = datetime(2026, 5, 1)

    events = []          # raw metering events
    invoices = []        # invoiced rollups
    ground_truth = []    # what the agent SHOULD find

    eid = 0
    for acct in ACCOUNTS:
        true_qty = random.randint(50_000, 3_000_000)
        # emit events summing to true_qty in a handful of batches
        emitted, batches = 0, random.randint(3, 6)
        for b in range(batches):
            q = true_qty // batches if b < batches - 1 else true_qty - emitted
            emitted += q
            ts = base + timedelta(days=random.randint(0, 30),
                                  hours=random.randint(0, 23))
            key = f"{acct}-{b}"
            events.append([f"evt_{eid}", acct, PRODUCT, q, ts.isoformat(), key])
            eid += 1

        invoiced_qty = true_qty
        issue = None

        roll = random.random()
        if roll < 0.20:
            # (1) duplicate event -> over-metered (same idempotency key repeated)
            dup = events[-1][:]
            dup[0] = f"evt_{eid}"; eid += 1
            events.append(dup)
            issue = "duplicate_event"   # over-billing risk if not de-duped
        elif roll < 0.45:
            # (2) late event metered but NOT invoiced -> leakage (under-billing)
            late_q = random.randint(20_000, 120_000)
            ts = base + timedelta(days=33)  # after period close
            events.append([f"evt_{eid}", acct, PRODUCT, late_q,
                           ts.isoformat(), f"{acct}-late"])
            eid += 1
            true_qty += late_q
            issue = "unreconciled_late_event"
        elif roll < 0.60:
            # (3) tier misconfiguration -> invoiced amount uses flat wrong price
            issue = "tier_misconfig"

        # build invoice
        if issue == "tier_misconfig":
            amount = round(invoiced_qty * 0.0003, 2)  # under-priced flat
        else:
            amount = tier_price_total(invoiced_qty)
        invoices.append([acct, PRODUCT, PERIOD, invoiced_qty, amount])

        if issue:
            ground_truth.append([acct, issue])

    _write(os.path.join(out_dir, "events.csv"),
           ["event_id", "account_id", "product_code", "quantity", "timestamp",
            "idempotency_key"], events)
    _write(os.path.join(out_dir, "invoices.csv"),
           ["account_id", "product_code", "period", "invoiced_quantity",
            "invoiced_amount"], invoices)
    _write(os.path.join(out_dir, "ground_truth.csv"),
           ["account_id", "issue"], ground_truth)

    print(f"events={len(events)} invoices={len(invoices)} "
          f"injected_issues={len(ground_truth)}")


def _write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


if __name__ == "__main__":
    main()
