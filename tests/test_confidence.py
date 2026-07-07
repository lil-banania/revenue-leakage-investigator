"""Tests for anchored confidence scoring."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.confidence import compute_confidence_score


def test_confidence_distinguishes_clear_vs_ambiguous_case():
    clear = compute_confidence_score(
        tool_results={
            "dup_vs_zero": {"direction": "a_lt_b"},
            "late_vs_zero": {"direction": "a_gt_b"},
            "rules_vs_zero": {"direction": "a_lt_b"},
            "invoice_lines": {"line_items": [{"product_code": "platform"}]},
        },
        iteration_count=3,
        discrepancy_amount=120.0,
    )
    ambiguous = compute_confidence_score(
        tool_results={
            "dup_vs_zero": {"direction": "a_lt_b"},
            "late_vs_zero": {"direction": "a_lt_b"},
            "rules_vs_zero": {"direction": "a_lt_b"},
            "invoice_lines": {"line_items": [{"product_code": "platform"}]},
        },
        iteration_count=8,
        discrepancy_amount=120.0,
    )
    assert clear > ambiguous
    assert clear >= 0.5
    assert ambiguous <= 0.4
