"""Multi-level evaluation of the agent run.

Mirrors the 3-level agent eval framework:
  Level 1 (outcome):    did detected issues match ground truth? (precision/recall)
  Level 2 (trajectory): was the agent path valid? (detector before explainer, no loops)
  Level 3 (step):       did guardrails pass? (consistency, no errors)
"""
from __future__ import annotations
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph import investigate
from src import guardrails


def load_ground_truth(path="data/ground_truth.csv"):
    with open(path, newline="") as f:
        return {(r["account_id"], r["issue"]) for r in csv.DictReader(f)}


def main():
    gt = load_ground_truth()
    state = investigate()

    # ---- Level 1: outcome (detection precision/recall on account+issue) ----
    detected = {(f["account_id"], f["issue"]) for f in state["findings"]}
    tp = len(detected & gt)
    precision = tp / len(detected) if detected else 0.0
    recall = tp / len(gt) if gt else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    # ---- Level 2: trajectory validity ----
    traj = state["visited"]
    traj_ok = (traj[:1] == ["detector"]
               and ("explainer" not in traj or traj.index("detector") < traj.index("explainer"))
               and len(traj) == len(set(traj)))           # no repeats -> no loop

    # ---- Level 3: step/guardrail health ----
    step_ok = (not state["errors"]) and guardrails.consistency_check(state)

    print("MULTI-LEVEL AGENT EVALUATION")
    print("-" * 40)
    print(f"L1 outcome   precision={precision:.2f}  recall={recall:.2f}  f1={f1:.2f}")
    print(f"             (tp={tp}, detected={len(detected)}, ground_truth={len(gt)})")
    print(f"L2 trajectory valid: {traj_ok}   path={' -> '.join(traj)}")
    print(f"L3 guardrails  ok: {step_ok}   errors={len(state['errors'])}")


if __name__ == "__main__":
    main()
