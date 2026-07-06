"""Evaluation harness for Tier 2 investigator root-cause reports."""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph import investigate
from src.investigator import MAX_ITERATIONS, investigate_alert
from src.investigator_tools import (
    compare_amounts,
    get_custom_pricing_rules,
    get_invoice_lines,
    query_raw_events,
)

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "eval" / "golden" / "investigator_cases.json"

TOOL_MAP: Dict[str, Callable[..., Dict[str, Any]]] = {
    "query_raw_events": query_raw_events,
    "get_invoice_lines": get_invoice_lines,
    "get_custom_pricing_rules": get_custom_pricing_rules,
    "compare_amounts": compare_amounts,
}


def load_cases() -> List[dict]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


def check_evidence_hallucinations(evidence_chain: List[dict]) -> int:
    hallucinations = 0
    for raw_step in evidence_chain:
        step = raw_step.model_dump() if hasattr(raw_step, "model_dump") else raw_step
        tool = step.get("tool")
        args = step.get("args", {})
        expected = TOOL_MAP.get(tool)
        if expected is None:
            hallucinations += 1
            continue
        try:
            expected_result = expected(**args)
            observed_result = ast.literal_eval(step.get("result_summary", "{}"))
            if observed_result != expected_result:
                hallucinations += 1
        except Exception:
            hallucinations += 1
    return hallucinations


def main() -> int:
    cases = load_cases()
    state = investigate()
    discrepancy_by_acct = {f["account_id"]: float(f["leakage_usd"]) for f in state.get("findings", [])}

    total = len(cases)
    if total == 0:
        print("No investigator eval cases found.")
        return 1

    correct = 0
    trajectory_valid = 0
    escalation_appropriate = 0
    hallucinated_steps = 0
    rows = []

    for case in cases:
        account_id = case["account_id"]
        period = case["period"]
        expected_root = case["expected_root_cause"]
        discrepancy = discrepancy_by_acct.get(account_id, 0.0)
        report = investigate_alert(
            {"account_id": account_id, "period": period, "discrepancy_amount": discrepancy}
        )

        predicted_root = report.root_cause_category.value
        is_correct = predicted_root == expected_root
        if is_correct:
            correct += 1

        traj_ok = 0 < len(report.evidence_chain) <= MAX_ITERATIONS
        if traj_ok:
            trajectory_valid += 1

        # Escalation is appropriate only if report is explicitly inconclusive.
        escalated = report.status == "needs_human_escalation"
        if escalated:
            escal_ok = expected_root == "unknown"
        else:
            escal_ok = expected_root != "unknown"
        if escal_ok:
            escalation_appropriate += 1

        hallucinations = check_evidence_hallucinations(report.evidence_chain)
        hallucinated_steps += hallucinations

        rows.append(
            {
                "account_id": account_id,
                "expected": expected_root,
                "predicted": predicted_root,
                "status": report.status,
                "confidence": report.confidence_score,
                "steps": len(report.evidence_chain),
                "hallucinations": hallucinations,
            }
        )

    accuracy = correct / total
    escalation_rate = escalation_appropriate / total
    trajectory_rate = trajectory_valid / total
    hallucination_free = 1.0 if hallucinated_steps == 0 else 0.0

    print("INVESTIGATOR EVAL")
    print("-" * 92)
    print(
        f"{'account':<12} {'expected':<26} {'predicted':<26} {'status':<24} {'hallu':>5}"
    )
    print("-" * 92)
    for row in rows:
        print(
            f"{row['account_id']:<12} {row['expected']:<26} {row['predicted']:<26} "
            f"{row['status']:<24} {row['hallucinations']:>5}"
        )

    print("-" * 92)
    print(f"root_cause_accuracy={accuracy:.2f}")
    print(f"escalation_appropriateness={escalation_rate:.2f}")
    print(f"trajectory_validity={trajectory_rate:.2f}")
    print(f"hallucinated_evidence_steps={hallucinated_steps}")
    print(
        f"OVERALL investigator_accuracy={accuracy:.2f} escalation={escalation_rate:.2f} "
        f"trajectory={trajectory_rate:.2f} hallucination_free={hallucination_free:.2f}"
    )

    min_acc = float(os.getenv("INVESTIGATOR_MIN_ACCURACY", "0.85"))
    min_escal = float(os.getenv("INVESTIGATOR_MIN_ESCALATION_APPROPRIATENESS", "0.9"))
    min_traj = float(os.getenv("INVESTIGATOR_MIN_TRAJECTORY_VALIDITY", "1.0"))
    max_hallu = int(os.getenv("INVESTIGATOR_MAX_HALLUCINATIONS", "0"))
    if accuracy < min_acc:
        print(f"FAIL: root_cause_accuracy {accuracy:.2f} < {min_acc:.2f}")
        return 1
    if escalation_rate < min_escal:
        print(f"FAIL: escalation_appropriateness {escalation_rate:.2f} < {min_escal:.2f}")
        return 1
    if trajectory_rate < min_traj:
        print(f"FAIL: trajectory_validity {trajectory_rate:.2f} < {min_traj:.2f}")
        return 1
    if hallucinated_steps > max_hallu:
        print(f"FAIL: hallucinated_evidence_steps {hallucinated_steps} > {max_hallu}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
