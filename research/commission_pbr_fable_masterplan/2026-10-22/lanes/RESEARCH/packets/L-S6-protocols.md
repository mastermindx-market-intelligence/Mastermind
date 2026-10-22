# OPERATION pbr-res-ls6-protocols — spec: experiment registry and protocols (W7/W8 freeze)
Class: design · Complexity: C2 · Output: ONE spec document. Docs only; you change no source.

## Inputs (read-only)
- `~/lanes/tmp/pbr-res-ls6-protocols/MASTERPLAN.md` (sha256 4c7a0d44…): §2 (account facts), §6.1–6.3 (mandate, benchmark ladder, metrics), §7.6–7.8, §9.1–9.5 (registry, E0–E6, attribution, statistics, preserved gates), §11.3–11.4 incl. the HK prospective opening checkpoint (around lines 596–600, and the charter excerpt near line 678), §12.
- Repo: `docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md` (V3 ladder, frozen laws), `docs/PORTFOLIO_V2_FORWARD_EVALUATION_2026-08-11.md` and `portfolio/forward_evaluation.py` (the existing V2 forward evaluator, the immutable cohort marker around lines 282 and 528–546 — cite, never redefine its statistics).

## Write `docs/superpowers/specs/2026-10-22-pbr-experiment-registry-and-protocols.md` with:
1. **Authority + non-goals** — protocols only; no code, no promotion, no live effect; the V2 marker and August-11 cohort are never reset or redefined; three verdicts (operationally correct / economically qualified / investment value) are reported separately and this document cannot claim investment value.
2. **Trial registry (§9.1)** — an immutable protocol record schema (`pbr.trial_protocol.v1`): hypothesis, owner, policy version, simulator version, data versions, universe, dates (design/train/validation/test, embargo/purge), cost model, primary metric, economic minimum (declared before unblinding), risk limits, comparison family, sample floors, stopping rule, status, failed/abandoned variants retained. Registration rules (register before running; amendments create a new version; abandoned trials remain in the family for multiple-testing control). State where records live as a proposal (an append-only file under a research path) and flag it as a seat decision.
3. **E0–E6 protocols (§9.2)** — one subsection each: hold-fixed, compared arms (incl. the current categorical allocator and equal-weight controls where §9.2 names them), primary + secondary metrics, economic minimum placeholder with how it is set, main falsifier, sample floor, dependency gates (E1/E2/E5 V3 order; cash/exit diagnostics cannot promote parameters early), what data is prospective vs retrospective, and the common-economic-model rule (identical qualified price/corporate-action/cash/fee/FX/lot/execution conventions; corrected economics never credited as policy alpha).
4. **Benchmark ladder (§6.2) and metrics (§6.3)** — tables, per book/currency.
5. **Statistical discipline (§9.4)** — paired differences, declared block-bootstrap (block length rule), effective-sample reporting, clustered dates/overlapping horizons, multiple-comparison control over the registered family (incl. Deflated Sharpe applicability conditions), cost/delay stress, the "no rescue search" rule, and that a negative/inconclusive result is a valid outcome.
6. **Preserved gates (§9.5)** — V2 first-review floors exactly as the masterplan states them (60 matched sessions, 40 effective PM decisions, 12 material-change decisions, ≥95% applicable coverage, no unresolved integrity defects; churn ruling 30 authoritative full-close episodes) and the V3 ladder table (first vertical / 20 / 60 / 126 / 252 sessions with conditions), quoted with section citations; plus the added power/economic-materiality analysis requirement.
7. **HK prospective opening checkpoint rule** — the masterplan rule as a protocol: components to enumerate, corroborated-vs-assumed labelling, pending-effect disposition, unsupported cost basis cannot become certified realized P&L, the checkpoint stays visible in every affected evaluation; ECON owns any accounting proposal — this doc only defines how evaluations must treat it.
8. **Attribution chain (§9.3)** — `snapshot → claim → PM view → target → feasible order → receipt → fill → position episode → outcome` as the required lineage for every experiment observation; proposed/queued actions are unexecuted until receipts.
9. **Open questions for the seat** — only consequential ones.
Cite masterplan section numbers and repo file:line for every factual claim. Keep it under ~500 lines.

## RETURN block (your last message)
```
RETURN pbr-res-ls6-protocols
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>
SECTIONS: <list>
PRESERVED_FLOORS_QUOTED: yes|no (with masterplan lines)
OPEN_QUESTIONS: <numbered>
```
