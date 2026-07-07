<h1 align="center">🕵️ Revenue Leakage Investigator</h1>
<p align="center">
  <em>A tool-grounded, eval-driven agent that finds revenue leakage in usage-based billing —
  built to demonstrate the decisions that make agentic systems reliable in production.</em>
</p>
<p align="center">
  <a href="https://github.com/lil-banania/revenue-leakage-investigator/actions/workflows/eval.yml"><img src="https://github.com/lil-banania/revenue-leakage-investigator/actions/workflows/eval.yml/badge.svg" alt="Eval CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/runs-offline%20(no%20API%20key)-success" alt="Runs offline">
  <!-- <a href="[DEMO_URL]"><img src="https://img.shields.io/badge/demo-live-orange" alt="Live demo"></a> -->
</p>
<p align="center">
  <a href="#-quickstart">Quickstart</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#-evaluation">Evaluation</a> ·
  <a href="#-design-decisions">Design decisions</a> ·
  <a href="#-roadmap">Roadmap</a>
</p>

The problem

In usage-based SaaS, revenue quietly leaks between metered usage and what actually gets invoiced: usage that arrived late and was never re-billed, duplicate events counted twice, tier-pricing errors, un-applied contract overrides. It's typically 8–15% of ARR — invisible, recurring, unaudited.

Revenue Leakage Investigator reconciles raw metering events against issued invoices and surfaces the leakage — quantified, by root cause, with verifiable evidence.


⚠️ Data disclaimer. This project runs on synthetic, Vynt-shaped data with injected, known discrepancies — no real customer data. The reconciliation logic is real and deterministic; the dataset is generated so the evaluation can be measured against ground truth.



Why it exists

This is a portfolio piece. The point isn't "look, an agent" — it's the engineering decisions that separate a demo from a production system: read-only tools, tool-grounded facts (no hallucinated numbers), trajectory evaluation wired into CI, a swappable data source for shadow deployment, and guardrails on every irreversible action. See DECISIONS.md.

Architecture

                  ┌──────────────┐   findings?    ┌───────────────┐
  period ───────► │   detector   │ ───── yes ───► │   explainer   │ ──► summary
                  │ (deterministic)│               │    (LLM)      │
                  │  tool-grounded │ ── no ──► END │  language only│
                  └──────────────┘                └───────────────┘
                         │
                    BillingSource (adapter)  ── sim ↔ real API via one env var


detector — deterministic. Calls reconciliation tools (dedup events, include late usage, recompute tier price) and emits typed Findings. No hallucination surface: the facts come from tools, not the model.
explainer — LLM. Turns structured findings into a finance-ready summary. Falls back to a templated summary with no API key.
BillingSource — an adapter that decouples the agent from where data lives, enabling shadow deployment before real data exists.



The repo also ships a hand-rolled, read-only MCP tool server and a reusable agent skill so the reconciliation tools are consumable by any MCP host.



✨ What it demonstrates


Multi-step orchestration with LangGraph (conditional handoff) + a dependency-free fallback.
Read-only MCP tool server with strict input schemas.
Structured context transfer — agents exchange a typed object, not free text.
4-layer guardrails — loop guard, step budget, output validation, consistency check.
3-level evaluation (outcome / trajectory / step) against ground truth, running in CI.
Swappable data source (simulator ↔ real API) for shadow-mode rollout.
Observability — one trace span per agent/tool (JSON, optional Langfuse).


🚀 Quickstart

Runs fully offline, no API key required.

bashgit clone https://github.com/lil-banania/revenue-leakage-investigator.git
cd revenue-leakage-investigator
pip install -r requirements.txt

python data/generate_data.py     # synthetic dataset w/ injected, known discrepancies
python run.py                    # run the investigation
python eval/trajectory_eval.py   # multi-level evaluation vs ground truth
pytest -q                        # offline unit tests

Optional:

bashpip install langgraph            # enables the production orchestration path
export ANTHROPIC_API_KEY=sk-...  # enables the LLM-written summary (otherwise templated)
streamlit run app.py             # interactive demo

🧠 How it works

ComponentFileRoleData source (adapter)src/sources/ · config.pyBillingSource interface; sim ↔ api via BILLING_SOURCEReconciliation toolssrc/tools.pydeterministic, unit-tested; re-derive the correct billingShared statesrc/state.pytyped InvestigationState / FindingAgentssrc/agents.pydetector (deterministic) + explainer (LLM)Guardrailssrc/guardrails.pyloop/step/consistency/output checksOrchestrationsrc/graph.pyLangGraph state graph + fallbackMCP servermcp/server.pyread-only tools over stdio (JSON-RPC)Agent skillskill/SKILL.mdreusable packaged capabilityEvaluationeval/3-level eval + golden setObservabilitysrc/tracing.pytrace spans (JSON + optional Langfuse)Demoapp.pyStreamlit UI

📊 Evaluation

Three levels, run in CI (a score below threshold fails the build):


L1 — outcome: precision / recall / F1 on (account_id, issue) vs ground truth.
L2 — trajectory: correct detector → explainer order, no loops.
L3 — step: zero guardrail errors + consistency check (total = Σ findings).


bashpython eval/trajectory_eval.py   # stratified scores per case type

🔌 MCP server

Exposes the reconciliation tools (read-only) to any MCP host (e.g. Claude Desktop). See mcp/README.md.

bashpython mcp/demo_client.py        # calls a tool and prints the result

🚦 Deployment

Designed for risk titration: shadow → copilot → limited autopilot. In shadow mode the agent runs on real traffic without acting, so reliability is measured at zero risk. Any invoice adjustment (irreversible, high-stakes) stays under human validation. See DEPLOYMENT.md.

🧩 Design decisions

Every choice is paired with its rejected alternative and the risk it avoids — see DECISIONS.md. Highlights:

DecisionRejected alternativeRisk avoidedRead-only toolswrite toolsirreversible damage if manipulatedFacts from tools, LLM for languageLLM computes amountshallucinated figuresTrajectory eval (3 levels) in CIfinal-answer eval onlylatent bugs, "right by luck"2-agent scope4 agents up frontfragility, over-engineeringSwappable sourcehardcoded sourcecan't test/deploy before real data

🗺️ Roadmap — Tier 2: Agentic Root-Cause Investigator

The current version is deliberately a deterministic detector + synthesis step — the right call for the detection task. The agentic value lives in root-cause investigation of flagged cases. Next:


Two-tier architecture: Tier 1 (deterministic detection, at scale) → Tier 2 (agentic investigation on flagged accounts only).
Atomic tools (query_raw_events, get_invoice_lines, get_custom_pricing_rules, compare_amounts) orchestrated by the LLM.
InvestigationReport with root_cause_category, an evidence chain, and a confidence score grounded on objective signals (not the model's self-report).
Invariant preserved: the LLM reasons, it never computes (arithmetic delegated to compare_amounts).


📁 Project structure

.
├── src/            # sources (adapter), tools, agents, graph, guardrails, state, tracing
├── mcp/            # read-only MCP tool server + demo client
├── skill/          # reusable agent skill
├── eval/           # 3-level evaluation + golden set
├── data/           # synthetic data generator + ground truth
├── tests/          # offline unit tests
├── app.py          # Streamlit demo
├── DECISIONS.md    # design decisions + alternatives
└── DEPLOYMENT.md   # rollout / shadow-mode guide

🤝 Contributing

Issues and PRs welcome. Please keep the eval green (pytest -q && python eval/trajectory_eval.py) — CI gates on it.

📄 License

MIT © Kevin Begranger — see LICENSE.
