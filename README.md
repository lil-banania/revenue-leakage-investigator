# 🕵️ Revenue Leakage Investigator — 2-Agent System (LangGraph)

![Eval](https://github.com/lil-banania/revenue-leakage-investigator/actions/workflows/eval.yml/badge.svg)

A scoped multi-agent system that finds revenue leakage in usage-based billing by
reconciling raw metering events against issued invoices. Built as an AI-PM portfolio
piece to demonstrate **multi-agent orchestration done responsibly** — structured
handoffs, guardrails, and a 3-level evaluation — without over-engineering a 4-agent
production system.

> Deliberately scoped to **2 agents**. The "what I'd do next" section covers scaling to
> the full detector → reconciler → recommender → compliance topology.

---

## The system

```
                 ┌─────────────┐   findings?    ┌──────────────┐
   period ─────► │  detector   │ ──── yes ────► │  explainer   │ ──► summary
                 │ (tools)     │                │  (LLM)       │
                 └─────────────┘ ──── no ───► END└──────────────┘
                    grounded                        language only
```

- **detector_agent** — *deterministic*. Calls reconciliation tools (dedup events,
  include late events, recompute graduated tier price) and emits structured `Finding`s.
  No hallucination surface: the facts come from tools, not the model.
- **explainer_agent** — *LLM*. Turns the structured findings into a finance-ready
  summary. Falls back to a templated summary with no API key.

This split is the core lesson: **ground facts in tools, use the LLM only for language.**

---

## Why this demonstrates AI-PM skill

| Pillar | Where it shows up |
|---|---|
| **Multi-agent orchestration** | `src/graph.py` — LangGraph state graph + conditional handoff |
| **Structured context transfer** | `src/state.py` — typed `InvestigationState`, not free-form text |
| **Guardrails** | `src/guardrails.py` — loop guard, step budget, output validation, consistency check |
| **ReAct-style grounding** | detector reasons then *acts* via reconciliation tools |
| **3-level evaluation** | `eval/trajectory_eval.py` — outcome / trajectory / step |

---

## Quick start (runs fully offline)

```bash
python data/generate_data.py        # synthetic dataset w/ INJECTED, known discrepancies
python run.py                       # run the investigation
python eval/trajectory_eval.py      # multi-level eval vs ground truth
pytest -q                           # 4 offline tests
```

Optional:
```bash
pip install langgraph               # enables the production orchestration path
export ANTHROPIC_API_KEY=sk-ant-... # enables the LLM-written summary
```
The project auto-detects LangGraph; without it, an identical dependency-free
orchestrator runs (`src/graph.py`).

---

## Sample output

```
accounts flagged: 11      net leakage: $860.31
  acct_019  tier_misconfig            $682.40   invoiced $693.59 vs correct $1375.99 (49.6% off)
  acct_002  unreconciled_late_event    $49.46   invoiced $1664.14 vs correct $1713.60 (2.9% off)
  acct_011  duplicate_event             $0.00   over-metering risk flagged (no $ impact)
  ...

MULTI-LEVEL AGENT EVALUATION
L1 outcome   precision=1.00  recall=1.00  f1=1.00   (tp=11, gt=11)
L2 trajectory valid: True   path=detector -> explainer
L3 guardrails  ok: True   errors=0
```

Because the dataset has **known injected issues** (`data/ground_truth.csv`), the eval is
real, not vibes: we measure detection precision/recall against ground truth.

---

## The three leakage drivers modeled
1. **Duplicate events** — over-metering; flagged even at $0 impact (risk signal).
2. **Unreconciled late events** — metered but not invoiced → under-billing (true leakage).
3. **Tier misconfiguration** — invoiced below the correct graduated tier price.

These are the documented top drivers of 8–15% ARR leakage in usage-based pricing.

---

## What I'd do next (the honest scope note)
- Add a **reconciler agent** (proposes the corrective invoice adjustment) and a
  **compliance agent** (checks the adjustment against the dispute-window / refund policy).
- Move from hub-of-two to **hub-and-spoke with a router**; add a consistency-checker agent.
- Replace the rules-based root-cause classifier with a learned classifier once enough
  labeled cases exist.
- Add cost-per-investigation tracking and human-in-the-loop approval before any
  customer-facing adjustment (irreversible + high-stakes → human required).

## Repo map
```
data/generate_data.py     synthetic events/invoices + ground truth (seeded)
src/state.py              typed shared state (structured context transfer)
src/tools.py              reconciliation tools (pure, tested)
src/agents.py             detector (deterministic) + explainer (LLM/stub)
src/guardrails.py         loop/step/output/consistency guards
src/graph.py              LangGraph graph + dependency-free fallback
eval/trajectory_eval.py   3-level evaluation vs ground truth
run.py                    CLI
tests/                    offline pytest
```
