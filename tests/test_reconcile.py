"""Offline tests — no LangGraph, no API key required."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data import generate_data
from src import tools, guardrails
from src.graph import investigate
from src.state import new_state


def _ensure_data():
    generate_data.main(os.path.join(ROOT, "data"))


def test_tier_pricing_graduated():
    # 1,200,000 calls: 0 (tier1) + 900k*0.0008 + 200k*0.0005 = 720 + 100 = 820
    assert tools.tier_price_total(1_200_000) == 820.0


def test_dedup_removes_duplicates():
    events = [
        {"account_id": "a", "idempotency_key": "k1", "quantity": "10",
         "timestamp": "2026-05-02T00:00:00"},
        {"account_id": "a", "idempotency_key": "k1", "quantity": "10",
         "timestamp": "2026-05-02T00:00:00"},
    ]
    assert len(tools.dedup_events(events)) == 1
    assert tools.had_duplicates(events) is True


def test_investigation_detects_injected_issues():
    _ensure_data()
    state = investigate()
    assert len(state["findings"]) > 0
    assert state["visited"][:1] == ["detector"]
    # consistency: total equals sum of parts
    assert guardrails.consistency_check(state)


def test_loop_guard_blocks_revisit():
    state = new_state("2026-05")
    state["visited"].append("detector")
    state["steps"] = 1
    assert guardrails.check_loop(state, "detector") is True
