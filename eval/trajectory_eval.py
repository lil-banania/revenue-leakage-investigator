"""Stratified multi-level evaluation for golden trajectories.

Levels:
  L1 outcome: precision/recall/f1 on (account_id, issue) pairs
  L2 trajectory: detector->explainer ordering + no loop
  L3 step: no guardrail errors + consistency check
"""
from __future__ import annotations
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph import investigate
from src import guardrails
from config import get_billing_source


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "eval" / "golden" / "cases.json"


@dataclass
class CaseResult:
    case_id: str
    stratum: str
    precision: float
    recall: float
    f1: float
    trajectory_ok: bool
    step_ok: bool
    case_ok: bool
    detected_count: int
    gt_count: int
    issue_types: List[str]


@contextmanager
def env_overrides(overrides: Dict[str, str]):
    previous: Dict[str, str | None] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = str(value)
    try:
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def load_cases() -> List[dict]:
    with open(CASES_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    return payload["cases"]


def load_ground_truth(period: str) -> set[tuple[str, str]]:
    source = get_billing_source()
    gt = getattr(source, "get_ground_truth", None)
    if gt is None:
        return set()
    rows = gt(period)
    return {(r["account_id"], r["issue"]) for r in rows}


def trajectory_ok(state: dict) -> bool:
    traj = state["visited"]
    return (
        traj[:1] == ["detector"]
        and ("explainer" not in traj or traj.index("detector") < traj.index("explainer"))
        and len(traj) == len(set(traj))
    )


def score_case(case: dict) -> CaseResult:
    overrides = {"BILLING_SOURCE": "sim", "PERIOD": case["period"]}
    for k, v in case.get("env", {}).items():
        overrides[k] = str(v)

    with env_overrides(overrides):
        gt = load_ground_truth(case["period"])
        state = investigate(period=case["period"])

    detected = {(f["account_id"], f["issue"]) for f in state["findings"]}
    tp = len(detected & gt)
    precision = tp / len(detected) if detected else 1.0
    recall = tp / len(gt) if gt else (1.0 if not detected else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    l2_ok = trajectory_ok(state)
    l3_ok = (not state["errors"]) and guardrails.consistency_check(state)

    expected = case.get("expected", {})
    detected_issues = sorted({f["issue"] for f in state["findings"]})
    case_ok = True
    if expected.get("no_leak", False):
        case_ok = case_ok and len(state["findings"]) == 0 and abs(state["total_leakage_usd"]) < 1e-9
    min_findings = expected.get("min_findings")
    if isinstance(min_findings, int):
        case_ok = case_ok and len(state["findings"]) >= min_findings
    min_issue_types = expected.get("min_issue_types")
    if isinstance(min_issue_types, int):
        case_ok = case_ok and len(detected_issues) >= min_issue_types
    required_issues = expected.get("required_issues", [])
    if required_issues:
        case_ok = case_ok and all(issue in detected_issues for issue in required_issues)

    case_ok = case_ok and l2_ok and l3_ok
    return CaseResult(
        case_id=case["id"],
        stratum=case["stratum"],
        precision=precision,
        recall=recall,
        f1=f1,
        trajectory_ok=l2_ok,
        step_ok=l3_ok,
        case_ok=case_ok,
        detected_count=len(detected),
        gt_count=len(gt),
        issue_types=detected_issues,
    )


def _avg(values: Iterable[float]) -> float:
    data = list(values)
    return sum(data) / len(data) if data else 0.0


def print_by_stratum(results: List[CaseResult]) -> None:
    strata = sorted({r.stratum for r in results})
    print("STRATIFIED EVAL SCORES")
    print("-" * 104)
    header = (
        f"{'stratum':<12} {'cases':>5} {'precision':>10} {'recall':>8} {'f1':>8} "
        f"{'traj_ok':>8} {'step_ok':>8} {'case_ok':>8}"
    )
    print(header)
    print("-" * 104)
    for s in strata:
        rows = [r for r in results if r.stratum == s]
        print(
            f"{s:<12} {len(rows):>5} "
            f"{_avg(r.precision for r in rows):>10.2f} "
            f"{_avg(r.recall for r in rows):>8.2f} "
            f"{_avg(r.f1 for r in rows):>8.2f} "
            f"{_avg(1.0 if r.trajectory_ok else 0.0 for r in rows):>8.2f} "
            f"{_avg(1.0 if r.step_ok else 0.0 for r in rows):>8.2f} "
            f"{_avg(1.0 if r.case_ok else 0.0 for r in rows):>8.2f}"
        )
    print("-" * 104)


def print_case_details(results: List[CaseResult]) -> None:
    print("\nCASE DETAILS")
    print("-" * 104)
    print(
        f"{'id':<20} {'stratum':<12} {'det':>4} {'gt':>4} "
        f"{'f1':>6} {'traj':>6} {'step':>6} {'ok':>6}  issue_types"
    )
    print("-" * 104)
    for r in results:
        print(
            f"{r.case_id:<20} {r.stratum:<12} {r.detected_count:>4} {r.gt_count:>4} "
            f"{r.f1:>6.2f} {str(r.trajectory_ok):>6} {str(r.step_ok):>6} {str(r.case_ok):>6}  "
            f"{','.join(r.issue_types)}"
        )


def main():
    cases = load_cases()
    results = [score_case(case) for case in cases]
    print_by_stratum(results)
    print_case_details(results)
    overall = _avg(1.0 if r.case_ok else 0.0 for r in results)
    print(f"\nOVERALL case_ok_rate={overall:.2f} ({sum(1 for r in results if r.case_ok)}/{len(results)})")


if __name__ == "__main__":
    main()
