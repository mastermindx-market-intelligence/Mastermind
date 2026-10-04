# Commission 9 — Data Alpha Attribution & Dataset Value Gauntlet
## Complete hardened research package · 2026-10-04

**Status: completed research recommendation; implementation not executed.**

This package replaces the uploaded Commission 9 recommendation with a source-recensused, methodologically hardened plan. It preserves the original goal—prove whether a dataset is worth having—while correcting duplicate-owner proposals, unqualified statistical reuse, temporal ambiguity, holdout loopholes and underspecified decision attribution.

**Read the [complete masterplan](MASTERPLAN.md) first.** The [audit and recensus](AUDIT_AND_RECENSUS.md) explains the material changes. The [validation protocol](VALIDATION_PROTOCOL.md) supplies the statistical, temporal, economic and policy-experiment details. The [exact P0A commission](IMPLEMENTATION_COMMISSION_P0A.md) is the bounded handoff for a later implementation owner. The [source register](SOURCE_REGISTER.md) carries durable source links, evidence classes and current-state limitations. [Synthetic receipts](SYNTHETIC_AUDIT_RECEIPT.json) record three source-expression counterexamples.

## Executive decision

Build a **thin, use-specific research qualification layer over the existing Data OS registry, temporal profiles, TrialLedger, Strategy Lab and canonical Portfolio Snapshot/shadow owners**. Do not build another catalog, ledger, statistics library, temporal warehouse, outcome system, Snapshot or control plane.

The first later commission should be **P0A: owner-native admission, primitive qualification and synthetic end-to-end proof**. No market-outcome access belongs in P0A. Existing-data empirical evaluation is P0B and requires accepted rights/PIT/identity, baseline, method and holdout-custody gates. External samples and prospective decision attribution come later; live authority remains a separate existing-owner approval.

A dataset must be judged against its intended use: incremental prediction, downside/event information, decision improvement, cheaper noninferior replacement, or essential supporting-data quality. There is no universal dataset alpha score. Healthy operational data do not become an extra investment conviction vote.

## What materially changed

The original proposal missed Macro's existing `dataset_registry.v1`, TrialLedger and Lab façade. It also treated existing numerical functions as broadly qualified. This audit demonstrated three specific expression-level hazards in the inspected validation code: future data changing early impact-cost inputs, an initial loss omitted from standalone maximum drawdown, and duplicate columns producing misleadingly low pseudo-inverse VIF. Those helpers were **not repaired** by this research run.

The replacement moves temporal/rights/identity and primitive qualification before outcome access; separates source-PIT reconstruction from actual-system replay; makes exposure survive a renamed experiment generation; preserves the current Trend C1 forward-confirmation rules; distinguishes economic value thresholds from statistical detectable effects; requires common-support comparisons; and separates same-state local decision tests from separately evolving closed-loop shadow policies.

A fixed modern LLM and prompt do not establish historical knowledge. A vendor's history start date or nanosecond timestamp does not prove original-vintage availability. A nonsignificant result does not by itself prove economic futility. These distinctions are enforceable gates and experiment definitions in the packet, not merely cautions in a closing paragraph.

## Contents and original requirements

| Required section | Durable location |
|---|---|
| A — Executive conclusion | `MASTERPLAN.md`, section A |
| B — Current-state census | `MASTERPLAN.md`, section B; full `AUDIT_AND_RECENSUS.md` |
| C — State of the art | `MASTERPLAN.md`, section C; primary sources in `SOURCE_REGISTER.md` |
| D — Source landscape | `MASTERPLAN.md`, section D, including coverage/history/latency/PIT/corrections/rights/cost/use table |
| E — Canonical data model | `MASTERPLAN.md`, section E; owner-native projections and temporal modes |
| F — Derived intelligence | `MASTERPLAN.md`, section F; deterministic and LLM boundaries |
| G — Integration map | `MASTERPLAN.md`, section G |
| H — Empirical validation | `MASTERPLAN.md`, section H; full `VALIDATION_PROTOCOL.md` |
| I — Risks and kill criteria | `MASTERPLAN.md`, section I; detailed audit/protocol |
| J — P0/P1/P2/defer/reject | `MASTERPLAN.md`, section J |
| K — Implementation phases | `MASTERPLAN.md`, section K |
| L — Exact later commission | `MASTERPLAN.md`, section L; full `IMPLEMENTATION_COMMISSION_P0A.md` |

## Source pins and authority

The substantive audit used Mastermind `521720b09be2921e996d9396b522b1c4ca62041c`, Macro `e570025bf3921ac26c3bdcb06ad25303677f325d`, Terminal `1c708450187755160e1a5889b69598a2fcb1f0d1`, and Executive DR vault `ea422c92bd29800d1f7fb3ae850236cc44d8c890`. A publication refresh reconciled Mastermind's intervening managed-workspace-only change to `17b9fa1363db6071d338be3373a4fdb11fc0076d`; the full change list was compared and did not alter the loaded procedures or research sources.

Active adjacent owners were recensed: Snapshot PR #673, temporal research PR #1221, observability research PR #1224, Issuer Inflection PR #1183, and merged Trend C1 PR #1226. Their statuses are observations at the audit, not timeless assertions. Unmerged candidate documents do not become protected law through citation here.

All future implementation must re-pin current source and reconcile path custody. The literal local name “Research Vault” was not proven equivalent to the resolved Executive DR repository. No identity or runtime proof was fabricated to close that gap.

## What was and was not verified

**Performed:** authenticated source/identity and adjacent-PR inspection; same-revision protected procedure loading; primary methodological and vendor-documentation checks; full report/handoff revision; three mathematical counterexamples using synthetic inputs; research-only GitHub publication.

**Not performed or claimed:** production implementation, repository-wide tests, current live-feed/materialized-data certification, vendor sample/quote/contract qualification, procurement, market backtests, protected holdout evaluation, prospective shadow outcomes, live portfolio/trading changes, authority promotion, or independent replication of old results reported in source documents.

The synthetic receipt evaluates exact inspected expressions, **not the complete repository module or test suite**. Code-inspected additional risks are labelled separately. A denied compound remote inspection was not retried or rerouted; remaining attachment-only assertions are explicitly unqualified in the census.

Original attachment SHA-256: `cef7701ab7eaeeae6ff97240387027c2b043c3a2113fe55dbf4a3d373c6854df`.
Synthetic receipt SHA-256: `78683607d648fe4511c2dcb1976e550958419af2329e86da048a6dde3817e8bc`.

## Acceptance boundary

Acceptance of this **research** means the evidence-based recommendation and next bounded commission are accepted. It does not mean the proposed gauntlet exists, that any supplier is worth buying, that a data family has proven alpha, or that a live consumer may change behavior. The later P0A commission must be separately issued and must not execute P0B/P1 automatically.
