"""Shared, STRUCTURED state passed between agents.

Multi-agent lesson encoded here: agents exchange a typed object, not free-form text.
This is the "structured context transfer" pattern — cheaper, lossless, and auditable.
"""
from __future__ import annotations
from typing import List, Optional, TypedDict


class Finding(TypedDict):
    account_id: str
    issue: str                 # duplicate_event | unreconciled_late_event | tier_misconfig
    invoiced_amount: float
    correct_amount: float
    leakage_usd: float         # correct - invoiced (positive = under-billed)
    evidence: str


class InvestigationState(TypedDict, total=False):
    # inputs
    period: str
    # detector outputs
    findings: List[Finding]
    total_leakage_usd: float
    # explainer outputs
    summary: str
    # control / observability (guardrails)
    visited: List[str]         # agents already run -> loop prevention
    steps: int
    errors: List[str]
    halted_reason: Optional[str]


def new_state(period: str) -> InvestigationState:
    return InvestigationState(period=period, findings=[], total_leakage_usd=0.0,
                              summary="", visited=[], steps=0, errors=[],
                              halted_reason=None)
