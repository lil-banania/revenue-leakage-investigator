# 🕵️ Revenue Leakage Investigator

![Eval](https://github.com/lil-banania/revenue-leakage-investigator/actions/workflows/eval.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Multi-agent revenue assurance demo for a hybrid SaaS billing model (subscription + usage):
the system reconciles metering events vs invoices, quantifies leakage, and explains root causes
with deterministic evidence.

> Demo app: `streamlit run app.py`  
> Public live URL: _to be added after deployment_

## 60-second architecture

```text
period/seed/scenario
        |
        v
  detector agent (deterministic tools)
        |
        +--> reconciliation findings (typed)
        |
        v
  explainer agent (language only)
        |
        v
summary + trace + eval artifacts
```

Core rule: deterministic logic computes amounts; LLM is optional and only used for narrative.

## Why this demonstrates craft

- Swappable source boundary (`sim` vs `api`) with no agent rewrite.
- Read-only reconciliation tooling surfaced through an MCP server.
- Stratified 3-level eval harness (outcome/trajectory/step) with CI threshold gate.
- Local JSON traces + optional Langfuse hook behind env flags.
- Streamlit demo that runs without API key and includes an honesty banner.

## Quick start

```bash
python3 -m pip install -r requirements.txt
python3 data/generate_data.py
python3 run.py
python3 eval/trajectory_eval.py
pytest -q
streamlit run app.py
```

## Links

- Design rationale: [DECISIONS.md](./DECISIONS.md)
- Deployment pattern: [DEPLOYMENT.md](./DEPLOYMENT.md)
- MCP server docs: [mcp/README.md](./mcp/README.md)
- Reusable skill: [skill/SKILL.md](./skill/SKILL.md)

## What I'd do next

- Add deployment-time reliability dashboards and alerting budgets.
- Add reviewer workflows for human approval on invoice-impacting recommendations.
- Expand the agent topology only after maintaining eval stability under higher traffic.
- Publish a live Streamlit URL and attach demo video/GIF at top of README.
