"""Unit tests for Tier 2 atomic investigator tools."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.investigator_tools import (
    compare_amounts,
    get_custom_pricing_rules,
    get_invoice_lines,
    query_raw_events,
)


def test_compare_amounts_is_deterministic():
    out = compare_amounts(120.0, 100.0)
    assert out["delta"] == 20.0
    assert out["direction"] == "a_gt_b"


def test_query_raw_events_returns_aggregates():
    out = query_raw_events("acct_001", "2026-05", "all")
    assert out["account_id"] == "acct_001"
    assert out["event_count"] >= 1
    assert out["total_quantity"] >= 0


def test_get_invoice_lines_returns_components():
    out = get_invoice_lines("acct_001", "2026-05")
    assert out["account_id"] == "acct_001"
    assert len(out["line_items"]) >= 1
    first = out["line_items"][0]
    assert "subscription_amount" in first
    assert "usage_amount" in first


def test_get_custom_pricing_rules_retrieves_override_docs():
    out = get_custom_pricing_rules("acct_001", query="custom tier override")
    assert out["account_id"] == "acct_001"
    assert out["retrieved_count"] >= 1
