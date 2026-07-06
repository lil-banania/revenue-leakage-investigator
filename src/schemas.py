"""Strict Pydantic schemas for Tier 2 investigator."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class RootCauseCategory(str, Enum):
    LATE_EVENT_ARRIVAL = "late_event_arrival"
    TIER_MISALIGNMENT = "tier_misalignment"
    CONTRACT_OVERRIDE_MISSED = "contract_override_missed"
    DUPLICATE_EVENTS = "duplicate_events"
    UNKNOWN = "unknown"


class AnomalyAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    discrepancy_amount: float


class EvidenceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1)
    args: Dict[str, Any] = Field(default_factory=dict)
    result_summary: str = Field(min_length=1)


class InvestigationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["conclusive", "needs_human_escalation"]
    root_cause_category: RootCauseCategory
    confidence_score: float = Field(ge=0.0, le=1.0)
    evidence_chain: List[EvidenceStep] = Field(default_factory=list)
    analyst_summary: str = Field(min_length=1)
