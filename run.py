"""CLI entry point.

    python data/generate_data.py     # create the synthetic dataset (once)
    python run.py                     # run the investigation

Add ANTHROPIC_API_KEY for an LLM-written summary; otherwise a templated summary is used.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.investigator import investigate_alert
from src.graph import investigate
from src.schemas import AnomalyAlert


def main():
    state = investigate(period=os.getenv("PERIOD", "2026-05"))

    print("=" * 64)
    print(f"REVENUE LEAKAGE INVESTIGATION — period {state['period']}")
    print("=" * 64)
    print(f"agents run: {' -> '.join(state['visited'])}  (steps={state['steps']})")
    if state.get("halted_reason"):
        print(f"halted: {state['halted_reason']}")
    if state["errors"]:
        print(f"guardrail errors: {state['errors']}")
    print(f"\naccounts flagged: {len(state['findings'])}")
    print(f"net leakage: ${state['total_leakage_usd']:.2f}\n")

    for f in sorted(state["findings"], key=lambda x: x["leakage_usd"], reverse=True):
        print(f"  {f['account_id']:<12} {f['issue']:<24} "
              f"${f['leakage_usd']:>10.2f}   {f['evidence']}")

    if state["findings"]:
        print("\n--- TIER 2 INVESTIGATION REPORTS ---")
        for f in sorted(state["findings"], key=lambda x: x["leakage_usd"], reverse=True):
            alert = AnomalyAlert(
                account_id=f["account_id"],
                period=state["period"],
                discrepancy_amount=float(f["leakage_usd"]),
            )
            report = investigate_alert(alert)
            print(
                f"  {report.status:<24} {f['account_id']} "
                f"cause={report.root_cause_category.value:<26} "
                f"confidence={report.confidence_score:.2f} "
                f"steps={len(report.evidence_chain)}"
            )

    print("\n--- SUMMARY ---")
    print(state["summary"])


if __name__ == "__main__":
    main()
