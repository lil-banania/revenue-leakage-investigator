"""The two agents.

  detector_agent  — deterministic: calls the reconciliation tools, produces Findings.
                    (Tool-grounded, no hallucination surface — by design.)
  explainer_agent — LLM: turns structured Findings into a crisp human summary.
                    Falls back to a templated summary if no ANTHROPIC_API_KEY.

This split mirrors the real lesson: ground the *facts* in tools (detector), use the
LLM only for *language* (explainer), never the reverse.
"""
from __future__ import annotations
import os

from . import tools, guardrails
from .state import InvestigationState

GEN_MODEL = os.getenv("GEN_MODEL", "claude-sonnet-4-6")


def detector_agent(state: InvestigationState) -> InvestigationState:
    if guardrails.check_loop(state, "detector"):
        return state
    guardrails.record_visit(state, "detector")

    findings = tools.run_reconciliation(os.getenv("DATA_DIR", "data"))
    errs = guardrails.validate_findings(findings)
    state["errors"].extend(errs)

    state["findings"] = findings
    state["total_leakage_usd"] = round(sum(f["leakage_usd"] for f in findings), 2)
    return state


def _template_summary(state: InvestigationState) -> str:
    n = len(state["findings"])
    by_issue = {}
    for f in state["findings"]:
        by_issue[f["issue"]] = by_issue.get(f["issue"], 0) + 1
    lines = [f"Found {n} accounts with billing discrepancies for period "
             f"{state['period']}.",
             f"Net leakage (under-billed minus over-billed): "
             f"${state['total_leakage_usd']:.2f}.",
             "Breakdown by root cause: " +
             ", ".join(f"{k}={v}" for k, v in sorted(by_issue.items())) + "."]
    return "\n".join(lines)


def explainer_agent(state: InvestigationState) -> InvestigationState:
    if guardrails.check_loop(state, "explainer"):
        return state
    guardrails.record_visit(state, "explainer")

    if not guardrails.consistency_check(state):
        state["errors"].append("consistency check failed: totals do not reconcile")

    if not os.getenv("ANTHROPIC_API_KEY"):
        state["summary"] = "[offline] " + _template_summary(state)
        return state

    from anthropic import Anthropic
    client = Anthropic()
    findings_json = "\n".join(
        f"- {f['account_id']}: {f['issue']}, leakage ${f['leakage_usd']:.2f} "
        f"({f['evidence']})" for f in state["findings"])
    prompt = (f"You are a revenue-assurance analyst. Summarize these reconciliation "
              f"findings for a finance lead in 4-6 sentences. Be specific about the "
              f"biggest leakage drivers and recommend one action.\n\n"
              f"Period: {state['period']}\nTotal net leakage: "
              f"${state['total_leakage_usd']:.2f}\nFindings:\n{findings_json}")
    msg = client.messages.create(model=GEN_MODEL, max_tokens=500,
                                 messages=[{"role": "user", "content": prompt}])
    state["summary"] = "".join(b.text for b in msg.content
                               if getattr(b, "type", "") == "text")
    return state
