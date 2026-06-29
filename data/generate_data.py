"""Generate synthetic billing dataset from the swappable BillingSource layer."""
from __future__ import annotations

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.sources.vynt_sim import VyntSimulatorSource


def main(out_dir: str = "data"):
    period = os.getenv("PERIOD", "2026-05")
    seed = int(os.getenv("SIM_SEED", "42"))
    source = VyntSimulatorSource(seed=seed)
    os.makedirs(out_dir, exist_ok=True)
    accounts = source.list_accounts(period)
    events = []
    invoices = []
    for account in accounts:
        for event in source.get_events(account.account_id, period):
            events.append(
                [
                    event.event_id,
                    event.account_id,
                    event.product_code,
                    event.quantity,
                    event.timestamp.isoformat(),
                    event.idempotency_key,
                ]
            )
        for invoice in source.get_invoices(account.account_id, period):
            invoices.append(
                [
                    invoice.account_id,
                    invoice.product_code,
                    invoice.period,
                    invoice.invoiced_quantity,
                    invoice.invoiced_amount,
                    invoice.subscription_amount,
                ]
            )
    ground_truth = [[entry["account_id"], entry["issue"]] for entry in source.get_ground_truth(period)]

    _write(os.path.join(out_dir, "events.csv"),
           ["event_id", "account_id", "product_code", "quantity", "timestamp",
            "idempotency_key"], events)
    _write(os.path.join(out_dir, "invoices.csv"),
           ["account_id", "product_code", "period", "invoiced_quantity",
            "invoiced_amount", "subscription_amount"], invoices)
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
