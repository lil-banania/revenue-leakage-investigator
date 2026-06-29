# DECISIONS

This document captures the key technical choices for the Revenue Leakage Investigator,
the alternatives we rejected, and the risks those alternatives would introduce.

| Decision | Rejected alternative | Risk avoided |
|---|---|---|
| Read-only reconciliation tools | Writable tools that auto-correct invoices | Irreversible billing actions from an incorrect diagnosis |
| Deterministic detector for amounts | LLM computes leakage amounts | Hallucinated numbers and non-reproducible financial outputs |
| 3-level trajectory evaluation | Final-outcome-only evaluation | Hidden path failures that pass by chance |
| 2-agent topology | Start directly with 4 agents | Over-engineering and lower reliability at current scope |
| MCP server tool surface | Hardcoded in-agent function calls only | Poor interoperability and weaker external reusability |
| Swappable source interface (`sim|api`) | Single hardcoded dataset origin | Costly migration when moving from demo to production source |
| LangGraph orchestration | Ad-hoc orchestration only | Less explicit control flow and harder conditional handoff governance |
| Pydantic DTO contracts | Untyped dicts across boundaries | Silent schema drift and weaker input guarantees |
| Selective LangChain usage | Use LangChain everywhere | Framework overhead where direct calls are simpler and safer |
| Langfuse optional hook + local JSON traces | Observability only when cloud tracing is configured | No-debug blind spots in local/offline demo runs |

Read-only tools were chosen because this project is positioned as investigation-first: the worst acceptable failure mode is a wrong report, not a wrong write. A write-capable billing agent would need stronger approval gates and human checkpoints than this scope.

A deterministic detector computes quantities and amounts with explicit reconciliation logic, while the LLM is constrained to explanation. This keeps financial math reproducible and auditable, and removes model variability from accounting-critical computations.

The evaluation harness scores outcome, trajectory, and step health because correct final labels alone do not prove reliability. A system can appear correct by coincidence while violating tool-order or guardrail expectations; trajectory-level tests catch that earlier.

We intentionally shipped with two agents (detector, explainer) instead of a full four-agent topology. At this maturity level, fewer agents reduce orchestration fragility and speed iteration, while preserving the core pattern of grounded analysis plus language synthesis.

The MCP server provides a standard tool interface (`list_accounts`, `reconcile_account`, etc.) instead of coupling tool calls to one internal agent runtime. This keeps the reconciliation surface reusable from external hosts and aligns with frontier deployment expectations.

The billing source abstraction (`BillingSource`) keeps the agent independent from data origin (`sim` vs `api`). This enables deterministic local demos now and a low-friction production cutover later, without rewriting agent logic.

LangGraph is used for explicit state-machine orchestration and conditional handoff. The fallback path remains available, but graph-native control flow makes transitions and stop conditions easier to reason about under expansion.

Pydantic models define contracts for source DTOs (`Account`, `UsageEvent`, `Invoice`) and reduce schema ambiguity. Strict typed boundaries prevent subtle reconciliation bugs caused by inconsistent field shapes or value domains.

LangChain is treated as selective, not mandatory. In this codebase, direct SDK/tool calls are preferred by default; LangChain should only be introduced where it concretely simplifies structured generation or integration points.

Langfuse integration is optional behind `LANGFUSE_*` flags, with local JSON traces as default. This avoids a cloud dependency for demo reliability while preserving a clear path to production-grade tracing backends.
