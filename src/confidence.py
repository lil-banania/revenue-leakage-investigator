"""Anchored confidence scoring for Tier 2 investigation reports."""
from __future__ import annotations

from typing import Any, Dict


def compute_confidence_score(
    tool_results: Dict[str, Dict[str, Any]],
    iteration_count: int,
    discrepancy_amount: float,
) -> float:
    """Compute confidence from objective evidence quality signals.

    Formula components (weighted sum):
    - evidence convergence (0.40): multiple signals supporting one hypothesis
    - explicit contract evidence (0.20): override docs retrieved
    - iteration penalty (0.20): longer investigation reduces confidence
    - amount coherence (0.20): discrepancy and observed evidence are directionally aligned
    """
    duplicate_signal = tool_results.get("dup_vs_zero", {}).get("direction") == "a_gt_b"
    late_signal = tool_results.get("late_vs_zero", {}).get("direction") == "a_gt_b"
    contract_signal = tool_results.get("rules_vs_zero", {}).get("direction") == "a_gt_b"
    tier_signal = any(
        "#tier_step_error" in item.get("product_code", "")
        for item in tool_results.get("invoice_lines", {}).get("line_items", [])
    )

    positive_signals = [duplicate_signal, late_signal, contract_signal, tier_signal]
    evidence_convergence = min(1.0, sum(1.0 for s in positive_signals if s) / 2.0)

    contract_strength = 1.0 if contract_signal else 0.0
    iteration_score = max(0.0, 1.0 - (max(iteration_count, 1) - 1) / 8.0)

    # Coherence: when discrepancy is non-trivial, we expect at least one positive evidence signal.
    discrepancy_present = abs(float(discrepancy_amount)) >= 1.0
    coherent = (discrepancy_present and any(positive_signals)) or (
        not discrepancy_present and not any(positive_signals)
    )
    amount_coherence = 1.0 if coherent else 0.0

    score = (
        0.40 * evidence_convergence
        + 0.20 * contract_strength
        + 0.20 * iteration_score
        + 0.20 * amount_coherence
    )
    return round(max(0.0, min(1.0, score)), 3)
