"""Guardrails — the multi-agent safety layer.

Encodes three of the four documented guardrail layers in a small, explicit module:
  - Execution guard:  max steps + visited-agent tracking (loop prevention)
  - Output validation: sanity checks on findings (no NaN, leakage within bounds)
  - Consistency check: total leakage must equal sum of per-finding leakage
"""
from __future__ import annotations
from typing import List

from .state import Finding, InvestigationState

MAX_STEPS = 6


def check_loop(state: InvestigationState, agent: str) -> bool:
    """Return True if running `agent` again would loop or exceed the step budget."""
    if state["steps"] >= MAX_STEPS:
        state["halted_reason"] = f"max steps ({MAX_STEPS}) reached"
        return True
    # detector may run once; explainer may run once -> revisiting is a loop
    if agent in state["visited"]:
        state["halted_reason"] = f"agent '{agent}' already visited (loop guard)"
        return True
    return False


def record_visit(state: InvestigationState, agent: str) -> None:
    state["visited"].append(agent)
    state["steps"] += 1


def validate_findings(findings: List[Finding]) -> List[str]:
    errs = []
    for f in findings:
        if f["correct_amount"] < 0 or f["invoiced_amount"] < 0:
            errs.append(f"{f['account_id']}: negative amount")
        expected = round(f["correct_amount"] - f["invoiced_amount"], 2)
        if abs(expected - f["leakage_usd"]) > 0.01:
            errs.append(f"{f['account_id']}: leakage_usd inconsistent")
    return errs


def consistency_check(state: InvestigationState) -> bool:
    """Total leakage must equal the sum of finding-level leakage (no cascade error)."""
    s = round(sum(f["leakage_usd"] for f in state["findings"]), 2)
    return abs(s - round(state["total_leakage_usd"], 2)) < 0.01
