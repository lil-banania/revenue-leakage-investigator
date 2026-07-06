"""Tier 2 root-cause investigator built as a bounded LangGraph loop."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Literal, TypedDict

from langgraph.graph import END, StateGraph

from .confidence import compute_confidence_score
from .investigator_tools import (
    compare_amounts,
    get_custom_pricing_rules,
    get_invoice_lines,
    query_raw_events,
)
from .schemas import AnomalyAlert, EvidenceStep, InvestigationReport, RootCauseCategory

MAX_ITERATIONS = 8


class InvestigatorState(TypedDict, total=False):
    alert: dict
    iteration: int
    done: bool
    selected_tool: str
    selected_args: dict
    tool_results: dict
    evidence_chain: list
    scratchpad: list
    report: dict
    status: str


def _offline_plan(state: InvestigatorState) -> tuple[str, Dict[str, Any], str]:
    alert = state["alert"]
    account_id = alert["account_id"]
    period = alert["period"]
    results = state.get("tool_results", {})

    if "raw_events_all" not in results:
        return (
            "query_raw_events",
            {"account_id": account_id, "period": period, "event_type": "all"},
            "Fetch raw event aggregates first to inspect duplicates/late arrivals.",
        )
    if "invoice_lines" not in results:
        return (
            "get_invoice_lines",
            {"account_id": account_id, "period": period},
            "Load billed line items to anchor investigation on invoiced values.",
        )
    if "dup_vs_zero" not in results:
        raw = results["raw_events_all"]
        return (
            "compare_amounts",
            {"a": float(raw["duplicate_event_count"]), "b": 0.0},
            "Check whether duplicate-event signal is materially present.",
        )
    if "late_vs_zero" not in results:
        raw = results["raw_events_all"]
        return (
            "compare_amounts",
            {"a": float(raw["late_event_count"]), "b": 0.0},
            "Check whether late-event signal is materially present.",
        )
    if "contract_rules" not in results:
        return (
            "get_custom_pricing_rules",
            {
                "account_id": account_id,
                "query": "contract pricing override discount tier failed payment retry dunning",
            },
            "Retrieve contract overrides to test pricing mismatch hypotheses.",
        )
    if "rules_vs_zero" not in results:
        rules = results["contract_rules"]
        return (
            "compare_amounts",
            {"a": float(rules["retrieved_count"]), "b": 0.0},
            "Measure if explicit contract evidence exists.",
        )
    return ("finalize", {}, "Sufficient evidence gathered, finalize report.")


def _reason_node(state: InvestigatorState) -> InvestigatorState:
    state["iteration"] = int(state.get("iteration", 0)) + 1
    state.setdefault("scratchpad", [])

    if state["iteration"] > MAX_ITERATIONS:
        state["done"] = True
        state["status"] = "needs_human_escalation"
        state["selected_tool"] = "finalize"
        state["selected_args"] = {}
        state["scratchpad"].append("Reached max iterations; escalating to human analyst.")
        return state

    # Use LLM when key is present, otherwise deterministic planner.
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from anthropic import Anthropic

            planner_prompt = {
                "alert": state["alert"],
                "iteration": state["iteration"],
                "tool_results": state.get("tool_results", {}),
                "available_tools": [
                    "query_raw_events(account_id, period, event_type)",
                    "get_invoice_lines(account_id, period)",
                    "get_custom_pricing_rules(account_id, query)",
                    "compare_amounts(a, b)",
                    "finalize",
                ],
                "constraint": "Never do arithmetic yourself. Use compare_amounts for comparisons.",
            }
            client = Anthropic()
            msg = client.messages.create(
                model=os.getenv("GEN_MODEL", "claude-sonnet-4-6"),
                max_tokens=350,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Return strict JSON: "
                            '{"tool":"...", "args": {...}, "reasoning":"..."}'
                            f"\nContext:\n{json.dumps(planner_prompt)}"
                        ),
                    }
                ],
            )
            txt = "".join(
                block.text for block in msg.content if getattr(block, "type", "") == "text"
            ).strip()
            parsed = json.loads(txt)
            tool = parsed.get("tool", "finalize")
            args = parsed.get("args", {})
            reasoning = parsed.get("reasoning", "LLM selected next investigation step.")
            if tool not in {
                "query_raw_events",
                "get_invoice_lines",
                "get_custom_pricing_rules",
                "compare_amounts",
                "finalize",
            }:
                tool = "finalize"
                args = {}
            state["selected_tool"] = tool
            state["selected_args"] = args
            state["scratchpad"].append(reasoning)
            if tool == "finalize":
                state["done"] = True
            return state
        except Exception:
            # Fall back to deterministic planner when LLM planning fails.
            pass

    tool, args, reasoning = _offline_plan(state)
    state["selected_tool"] = tool
    state["selected_args"] = args
    state["scratchpad"].append(reasoning)
    if tool == "finalize":
        state["done"] = True
    return state


def _tool_node(state: InvestigatorState) -> InvestigatorState:
    if state.get("done"):
        return state

    tool = state.get("selected_tool", "finalize")
    args = state.get("selected_args", {})
    results = state.setdefault("tool_results", {})
    chain = state.setdefault("evidence_chain", [])

    if tool == "query_raw_events":
        result = query_raw_events(**args)
        key = "raw_events_all" if args.get("event_type") == "all" else f"raw_events_{args.get('event_type')}"
    elif tool == "get_invoice_lines":
        result = get_invoice_lines(**args)
        key = "invoice_lines"
    elif tool == "get_custom_pricing_rules":
        result = get_custom_pricing_rules(**args)
        key = "contract_rules"
    elif tool == "compare_amounts":
        result = compare_amounts(**args)
        if "dup_vs_zero" not in results:
            key = "dup_vs_zero"
        elif "late_vs_zero" not in results:
            key = "late_vs_zero"
        else:
            key = "rules_vs_zero"
    else:
        state["done"] = True
        return state

    results[key] = result
    ev = EvidenceStep(
        tool=tool,
        args=args,
        result_summary=str(result),
    )
    chain.append(ev.model_dump())
    return state


def _infer_root_cause(state: InvestigatorState) -> RootCauseCategory:
    results = state.get("tool_results", {})
    invoice_lines = results.get("invoice_lines", {}).get("line_items", [])
    product_code = invoice_lines[0].get("product_code", "") if invoice_lines else ""
    if "#tier_step_error" in product_code:
        return RootCauseCategory.TIER_MISALIGNMENT

    dup = results.get("dup_vs_zero", {})
    if dup.get("direction") == "a_gt_b":
        return RootCauseCategory.DUPLICATE_EVENTS

    late = results.get("late_vs_zero", {})
    if late.get("direction") == "a_gt_b":
        return RootCauseCategory.LATE_EVENT_ARRIVAL

    rules = results.get("rules_vs_zero", {})
    if rules.get("direction") == "a_gt_b":
        return RootCauseCategory.CONTRACT_OVERRIDE_MISSED

    return RootCauseCategory.UNKNOWN


def _finalize_node(state: InvestigatorState) -> InvestigatorState:
    root = _infer_root_cause(state)
    status: Literal["conclusive", "needs_human_escalation"]
    if state.get("iteration", 0) > MAX_ITERATIONS or root == RootCauseCategory.UNKNOWN:
        status = "needs_human_escalation"
    else:
        status = "conclusive"

    reasoning = state.get("scratchpad", [])
    summary = (
        f"Investigated account {state['alert']['account_id']} for period {state['alert']['period']}. "
        f"Most likely root cause: {root.value}. "
        f"Evidence steps: {len(state.get('evidence_chain', []))}."
    )
    if status == "needs_human_escalation":
        summary += " Confidence is insufficient for automated conclusion."

    confidence = compute_confidence_score(
        tool_results=state.get("tool_results", {}),
        iteration_count=int(state.get("iteration", 0)),
        discrepancy_amount=float(state["alert"].get("discrepancy_amount", 0.0)),
    )
    if status == "needs_human_escalation":
        confidence = min(confidence, 0.49)
    report = InvestigationReport(
        status=status,
        root_cause_category=root,
        confidence_score=confidence,
        evidence_chain=state.get("evidence_chain", []),
        analyst_summary=summary + (" Planner notes: " + " | ".join(reasoning[-3:]) if reasoning else ""),
    )
    state["report"] = report.model_dump()
    state["done"] = True
    return state


def _route_after_reason(state: InvestigatorState) -> str:
    if state.get("done"):
        return "finalize"
    return "tool"


def _route_after_tool(state: InvestigatorState) -> str:
    if state.get("done"):
        return "finalize"
    return "reason"


def build_investigator_graph():
    graph = StateGraph(InvestigatorState)
    graph.add_node("reason", _reason_node)
    graph.add_node("tool", _tool_node)
    graph.add_node("finalize", _finalize_node)
    graph.set_entry_point("reason")
    graph.add_conditional_edges("reason", _route_after_reason, {"tool": "tool", "finalize": "finalize"})
    graph.add_conditional_edges("tool", _route_after_tool, {"reason": "reason", "finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()


def investigate_alert(alert: AnomalyAlert | dict, max_iterations: int = MAX_ITERATIONS) -> InvestigationReport:
    if isinstance(alert, dict):
        alert_obj = AnomalyAlert(**alert)
    else:
        alert_obj = alert

    global MAX_ITERATIONS
    old_max = MAX_ITERATIONS
    MAX_ITERATIONS = max_iterations
    try:
        app = build_investigator_graph()
        out = app.invoke(
            {
                "alert": alert_obj.model_dump(),
                "iteration": 0,
                "done": False,
                "tool_results": {},
                "evidence_chain": [],
                "scratchpad": [],
            }
        )
        return InvestigationReport(**out["report"])
    finally:
        MAX_ITERATIONS = old_max
