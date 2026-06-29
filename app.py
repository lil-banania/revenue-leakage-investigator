"""Streamlit demo app for Revenue Leakage Investigator."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

import streamlit as st

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


def main() -> None:
    st.set_page_config(page_title="Revenue Leakage Investigator", layout="wide")
    st.title("Revenue Leakage Investigator")
    st.markdown(
        "### Donnees synthetiques iso-Vynt, discordances injectees - aucune donnee client reelle."
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

    st.markdown("[DECISIONS.md](./DECISIONS.md)")

    if not run_clicked:
        st.info("Select controls and click **Run investigation**.")
        return

    scenario_env = {k: "0.0" for k in SCENARIO_KEYS}
    scenario_env["SCENARIO_RATE_NO_ISSUE"] = "0.20"
    scenario_env.update(SCENARIO_PRESETS.get(scenario, {}))
    base_env = {
        "BILLING_SOURCE": "sim",
        "PERIOD": period,
        "SIM_SEED": str(seed),
        **scenario_env,
    }

    with st.spinner("Running investigation..."):
        with env_overrides(base_env):
            state = investigate(period=period)

    c1, c2, c3 = st.columns(3)
    c1.metric("Accounts flagged", len(state.get("findings", [])))
    c2.metric("Net leakage", f"${state.get('total_leakage_usd', 0.0):,.2f}")
    c3.metric("Agent steps", state.get("steps", 0))

    st.subheader("Findings")
    findings = state.get("findings", [])
    if findings:
        findings_sorted = sorted(findings, key=lambda f: f["leakage_usd"], reverse=True)
        st.dataframe(findings_sorted, use_container_width=True, hide_index=True)
    else:
        st.success("No leakage detected for this run.")

    st.subheader("Summary")
    summary = state.get("summary", "")
    if summary:
        st.write(summary)
    else:
        st.write("No summary generated.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        st.caption("LLM summary is optional. Running with deterministic offline explainer.")

    st.subheader("Trace timeline")
    trace_path = state.get("trace_path")
    if trace_path:
        trace = load_trace(trace_path)
        st.caption(f"Trace file: `{trace_path}`")
        for idx, span in enumerate(trace.get("spans", []), start=1):
            token_cost = span.get("token_cost", {})
            with st.expander(
                f"{idx:02d}. {span.get('name')} [{span.get('kind')}] - "
                f"{span.get('latency_ms', 0)}ms - {token_cost.get('total_tokens', 0)} tokens",
                expanded=False,
            ):
                st.write({"inputs": span.get("inputs"), "outputs": span.get("outputs")})
    else:
        st.warning("No trace path found in run state.")


if __name__ == "__main__":
    main()
