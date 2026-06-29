# DEPLOYMENT

## Deployment pattern for real customer environments

This project is designed for high-stakes billing diagnostics. The rollout pattern is
intentionally conservative: start in shadow mode, earn reliability, then expand.

## Phase 1: Shadow mode first

- Connect the agent to production-like billing sources in read-only mode.
- Run investigations on a fixed cadence (daily/weekly) without touching invoices.
- Compare findings against finance-team reviews and existing reconciliation workflows.
- Track disagreement rate between agent findings and human adjudication.

Exit criteria:
- stable precision/recall across representative account cohorts,
- low false-positive rate on high-value accounts,
- trace completeness and reproducibility for every run.

## Phase 2: Human approval on all invoice-impacting actions

- Keep reconciliation tools read-only by default.
- If adding corrective recommendations, route all adjustments to a human reviewer.
- Require explicit approval for any action that could impact billing outcomes.
- Log decision provenance: finding evidence, reviewer, timestamp, final action.

Rationale:
- billing corrections are financially and legally sensitive,
- human-in-the-loop prevents irreversible harm from model or data errors.

## Phase 3: Reliability gates before widening scope

- Define SLA-style reliability gates:
  - minimum case-level eval score in CI,
  - maximum tolerated regression budget,
  - alerting on degraded trajectory/guardrail metrics.
- Expand rollout by segment only after passing gates:
  - low-risk cohort -> medium-risk cohort -> full portfolio.

## Operations and maintenance

- Keep `eval/golden/` updated as pricing policies evolve.
- Re-index/recompute simulator and golden cases whenever schema or rules change.
- Version pricing logic and scenario injections; tie each release to eval artifacts.
- Monitor trace volumes and error classes for drift detection.

## Incident response

- If reliability drops below threshold:
  - halt expansion,
  - revert to previous validated version,
  - re-run stratified eval and root-cause analysis using traces.

## Security and governance stance

- No customer write-path in default architecture.
- Synthetic-data demo remains available even without external API keys.
- Optional observability integrations are behind environment flags.
