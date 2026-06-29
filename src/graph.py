"""Orchestration: detector --(handoff if findings)--> explainer.

Primary implementation uses LangGraph (the production-grade choice: explicit state
graph, conditional edges). A dependency-free fallback orchestrator with identical
handoff logic is provided so the project runs even before `pip install langgraph`.

Handoff rule (conditional edge): only hand off to the explainer if the detector
actually found something; otherwise end. This is the 'don't wake the next agent for
nothing' guard.
"""
from __future__ import annotations

from .state import InvestigationState, new_state
from .agents import detector_agent, explainer_agent
from .tracing import TraceRecorder


def _route_after_detector(state: InvestigationState) -> str:
    if state.get("halted_reason"):
        return "end"
    return "explainer" if state["findings"] else "end"


# ---------- LangGraph implementation ----------
def build_langgraph():
    from langgraph.graph import StateGraph, END
    g = StateGraph(InvestigationState)
    g.add_node("detector", detector_agent)
    g.add_node("explainer", explainer_agent)
    g.set_entry_point("detector")
    g.add_conditional_edges("detector", _route_after_detector,
                            {"explainer": "explainer", "end": END})
    g.add_edge("explainer", END)
    return g.compile()


# ---------- dependency-free fallback (same logic) ----------
def _run_manual(period: str) -> InvestigationState:
    state = new_state(period)
    state = detector_agent(state)
    if _route_after_detector(state) == "explainer":
        state = explainer_agent(state)
    return state


def investigate(period: str = "2026-05", use_langgraph: bool | None = None) -> InvestigationState:
    """Run the investigation. Tries LangGraph, falls back to manual orchestration."""
    recorder = TraceRecorder(period=period)

    if use_langgraph is None:
        try:
            import langgraph  # noqa: F401
            use_langgraph = True
        except Exception:
            use_langgraph = False

    state = new_state(period)
    state["trace_recorder"] = recorder
    if use_langgraph:
        app = build_langgraph()
        out = app.invoke(state)
    else:
        out = state
        out = detector_agent(out)
        if _route_after_detector(out) == "explainer":
            out = explainer_agent(out)
    trace_path = recorder.finalize(out)
    out["trace_path"] = trace_path
    return out
