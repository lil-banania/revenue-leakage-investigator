"""Streamlit demo app for Revenue Leakage Investigator."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

import streamlit as st

from eval.trajectory_eval import load_ground_truth, trajectory_ok
from mcp.server import _tool_specs
from src import guardrails
from src.graph import investigate


SCENARIO_PRESETS: Dict[str, Dict[str, str]] = {
    "balanced": {},
    "late_events_focus": {
        "SCENARIO_RATE_LATE_EVENTS_UNBILLED": "0.95",
        "SCENARIO_RATE_MISSING_DEDUP": "0.0",
        "SCENARIO_RATE_TIER_STEP_ERROR": "0.0",
        "SCENARIO_RATE_PRORATION_FAILED": "0.0",
        "SCENARIO_RATE_DISCOUNT_NOT_EXPIRED": "0.0",
        "SCENARIO_RATE_DUNNING_GAP": "0.0",
        "SCENARIO_RATE_NO_ISSUE": "0.05",
    },
    "dedup_focus": {
        "SCENARIO_RATE_LATE_EVENTS_UNBILLED": "0.0",
        "SCENARIO_RATE_MISSING_DEDUP": "0.95",
        "SCENARIO_RATE_TIER_STEP_ERROR": "0.0",
        "SCENARIO_RATE_PRORATION_FAILED": "0.0",
        "SCENARIO_RATE_DISCOUNT_NOT_EXPIRED": "0.0",
        "SCENARIO_RATE_DUNNING_GAP": "0.0",
        "SCENARIO_RATE_NO_ISSUE": "0.05",
    },
    "tier_focus": {
        "SCENARIO_RATE_LATE_EVENTS_UNBILLED": "0.0",
        "SCENARIO_RATE_MISSING_DEDUP": "0.0",
        "SCENARIO_RATE_TIER_STEP_ERROR": "0.95",
        "SCENARIO_RATE_PRORATION_FAILED": "0.0",
        "SCENARIO_RATE_DISCOUNT_NOT_EXPIRED": "0.0",
        "SCENARIO_RATE_DUNNING_GAP": "0.0",
        "SCENARIO_RATE_NO_ISSUE": "0.05",
    },
    "no_leak": {
        "SCENARIO_RATE_LATE_EVENTS_UNBILLED": "0.0",
        "SCENARIO_RATE_MISSING_DEDUP": "0.0",
        "SCENARIO_RATE_TIER_STEP_ERROR": "0.0",
        "SCENARIO_RATE_PRORATION_FAILED": "0.0",
        "SCENARIO_RATE_DISCOUNT_NOT_EXPIRED": "0.0",
        "SCENARIO_RATE_DUNNING_GAP": "0.0",
        "SCENARIO_RATE_NO_ISSUE": "1.0",
    },
}

SCENARIO_KEYS = [
    "SCENARIO_RATE_PRORATION_FAILED",
    "SCENARIO_RATE_DISCOUNT_NOT_EXPIRED",
    "SCENARIO_RATE_DUNNING_GAP",
    "SCENARIO_RATE_LATE_EVENTS_UNBILLED",
    "SCENARIO_RATE_MISSING_DEDUP",
    "SCENARIO_RATE_TIER_STEP_ERROR",
    "SCENARIO_RATE_NO_ISSUE",
]


@contextmanager
def env_overrides(overrides: Dict[str, str]):
    previous: Dict[str, str | None] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def load_trace(trace_path: str) -> dict:
    return json.loads(Path(trace_path).read_text(encoding="utf-8"))


def detect_orchestrator() -> str:
    try:
        import langgraph  # noqa: F401

        return "LangGraph"
    except Exception:
        return "Fallback"


def p95(values: list[int]) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = max(0, int(0.95 * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def render_header_chips(source: str, seed: int, scenario: str, orchestrator: str, model: str) -> None:
    st.markdown(
        f"""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px 0;">
  <span style="background:#0B1020;color:#C7D2FE;padding:6px 10px;border-radius:999px;font-size:12px;">source={source}</span>
  <span style="background:#0B1020;color:#C7D2FE;padding:6px 10px;border-radius:999px;font-size:12px;">seed={seed}</span>
  <span style="background:#0B1020;color:#C7D2FE;padding:6px 10px;border-radius:999px;font-size:12px;">scenario={scenario}</span>
  <span style="background:#0B1020;color:#C7D2FE;padding:6px 10px;border-radius:999px;font-size:12px;">orchestrator={orchestrator}</span>
  <span style="background:#0B1020;color:#C7D2FE;padding:6px 10px;border-radius:999px;font-size:12px;">model={model}</span>
  <span style="background:#064E3B;color:#D1FAE5;padding:6px 10px;border-radius:999px;font-size:12px;font-weight:600;">SHADOW MODE</span>
</div>
""",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Revenue Leakage Investigator", layout="wide")
    st.title("Revenue Leakage Investigator")
    st.markdown(
        "### Synthetic Vynt-like data with injected discrepancies — no real customer data."
    )

    with st.sidebar:
        st.header("Run controls")
        period = st.selectbox("Period", options=["2026-05"], index=0)
        scenario = st.selectbox(
            "Scenario",
            options=list(SCENARIO_PRESETS.keys()),
            index=0,
            format_func=lambda s: s.replace("_", " ").title(),
        )
        seed = st.number_input("Seed", min_value=1, max_value=999999, value=42, step=1)
        run_clicked = st.button("Run investigation", type="primary", use_container_width=True)
        st.markdown("---")
        st.markdown("[DECISIONS.md](https://github.com/lil-banania/revenue-leakage-investigator/blob/main/DECISIONS.md)")
        st.markdown("[GitHub](https://github.com/lil-banania/revenue-leakage-investigator)")
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            st.caption("Langfuse export: configured")
        else:
            st.caption("Langfuse export: not configured (local traces only)")

    if not run_clicked:
        st.info("Select controls and click **Run investigation**.")
        return

    scenario_env = {k: "0.0" for k in SCENARIO_KEYS}
    scenario_env["SCENARIO_RATE_NO_ISSUE"] = "0.20"
    scenario_env.update(SCENARIO_PRESETS.get(scenario, {}))
    source_kind = "sim"
    orchestrator = detect_orchestrator()
    model = os.getenv("GEN_MODEL", "claude-sonnet-4-6")
    base_env = {
        "BILLING_SOURCE": source_kind,
        "PERIOD": period,
        "SIM_SEED": str(seed),
        **scenario_env,
    }

    with st.spinner("Running investigation..."):
        with env_overrides(base_env):
            state = investigate(period=period)
            gt = load_ground_truth(period)

    findings = state.get("findings", [])
    detected = {(f["account_id"], f["issue"]) for f in findings}
    tp = len(detected & gt)
    precision = tp / len(detected) if detected else 1.0
    recall = tp / len(gt) if gt else (1.0 if not detected else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    l2_ok = trajectory_ok(state)
    l3_ok = (not state.get("errors")) and guardrails.consistency_check(state)

    trace = {}
    spans = []
    if state.get("trace_path"):
        trace = load_trace(state["trace_path"])
        spans = trace.get("spans", [])
    latencies = [int(s.get("latency_ms", 0) or 0) for s in spans]
    total_tokens = sum(int((s.get("token_cost") or {}).get("total_tokens", 0)) for s in spans)
    p95_latency = p95(latencies)

    render_header_chips(source_kind, int(seed), scenario, orchestrator, model)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Accounts flagged", len(findings))
    k2.metric("Net leakage", f"${state.get('total_leakage_usd', 0.0):,.2f}")
    k3.metric("F1 vs ground truth", f"{f1:.2f}")
    k4.metric("Total tokens", total_tokens)
    k5.metric("p95 span latency", f"{p95_latency} ms")

    tab_findings, tab_eval, tab_trace, tab_guards, tab_tools = st.tabs(
        ["Findings", "Evaluation", "Agent trace", "Guardrails", "Tools (MCP)"]
    )

    with tab_findings:
        if findings:
            rows = sorted(findings, key=lambda f: f["leakage_usd"], reverse=True)
            st.dataframe(rows, use_container_width=True, hide_index=True)
            by_issue: Dict[str, float] = {}
            for f in rows:
                by_issue[f["issue"]] = by_issue.get(f["issue"], 0.0) + float(f["leakage_usd"])
            st.caption("Leakage by root cause")
            st.bar_chart(by_issue)
        else:
            st.success("No leakage detected for this run.")
        summary = state.get("summary", "")
        if summary:
            st.markdown("#### Summary")
            st.write(summary)

    with tab_eval:
        c1, c2, c3 = st.columns(3)
        c1.metric("Precision", f"{precision:.2f}")
        c2.metric("Recall", f"{recall:.2f}")
        c3.metric("F1", f"{f1:.2f}")
        s1, s2 = st.columns(2)
        if l2_ok:
            s1.success("L2 trajectory valid")
        else:
            s1.error("L2 trajectory invalid")
        if l3_ok:
            s2.success("L3 step/guardrails clean")
        else:
            s2.error("L3 step/guardrails failed")

        matched = sorted(detected & gt)
        missed = sorted(gt - detected)
        extra = sorted(detected - gt)
        with st.expander(f"✅ Matched ({len(matched)})", expanded=False):
            st.write(matched)
        with st.expander(f"❌ Missed / false negatives ({len(missed)})", expanded=False):
            st.write(missed)
        with st.expander(f"⚠️ Extra / false positives ({len(extra)})", expanded=False):
            st.write(extra)
        st.caption("Evaluated live against injected ground truth - this is real eval, not vibes.")

    with tab_trace:
        path = state.get("visited", [])
        path_text = " -> ".join(path + (["END"] if path else []))
        st.markdown(f"**Executed path:** `{path_text}`")
        if findings:
            st.caption("Conditional handoff: detector -> explainer because findings > 0.")
        else:
            st.caption("Conditional handoff: detector -> END because no findings.")
        st.caption(f"Trace file: `{state.get('trace_path', 'n/a')}`")
        if spans:
            st.write(
                {
                    "span_count": len(spans),
                    "total_latency_ms": sum(latencies),
                    "p95_latency_ms": p95_latency,
                    "total_tokens": total_tokens,
                }
            )
        for idx, span in enumerate(spans, start=1):
            tok = span.get("token_cost", {})
            with st.expander(
                f"{idx:02d}. {span.get('name')} [{span.get('kind')}] - "
                f"{span.get('latency_ms', 0)}ms - {tok.get('total_tokens', 0)} tokens",
                expanded=False,
            ):
                st.write({"inputs": span.get("inputs"), "outputs": span.get("outputs")})

    with tab_guards:
        loop_ok = len(state.get("visited", [])) == len(set(state.get("visited", [])))
        step_budget = 6
        step_ok = int(state.get("steps", 0)) <= step_budget
        consistency_ok = guardrails.consistency_check(state)
        output_ok = len(state.get("errors", [])) == 0
        halted = state.get("halted_reason")

        checks = [
            ("Loop guard", loop_ok, "Prevents agent loops and repeated handoffs."),
            ("Step budget", step_ok, "Bounds runaway orchestration cost and latency."),
            ("Consistency check", consistency_ok, "Ensures totals reconcile with findings."),
            ("Output validation", output_ok, "Keeps structured outputs schema-safe."),
        ]
        for name, ok, why in checks:
            prefix = "✅" if ok else "❌"
            st.write(f"{prefix} **{name}** - {why}")
        if halted:
            st.warning(f"Halted reason: {halted}")
        if state.get("errors"):
            st.error({"errors": state["errors"]})

    with tab_tools:
        for spec in _tool_specs():
            with st.expander(f"🔧 {spec['name']} - {spec['description']}", expanded=False):
                st.json(spec["inputSchema"])
        st.caption(
            "All tools are READ-ONLY. Worst case is a wrong report, never an irreversible billing action."
        )

    if not os.getenv("ANTHROPIC_API_KEY"):
        st.caption("LLM summary is optional. Running with deterministic offline explainer.")


if __name__ == "__main__":
    main()
