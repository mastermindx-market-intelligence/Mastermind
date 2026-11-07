# Earnings Expectations, Behavioral Repricing and Market Incorporation — Evidence-First Research & Execution Plan

**Date:** 2026-10-13  
**Status:** Research/architecture candidate; no predictive or trading promotion.  
**Scope:** Interpret the Chairman's Q1 discovery → Q2 anticipation → earnings sell-the-event hypothesis, investigate alternatives, reuse the current Mastermind earnings/expectations estate, and specify the next scientifically discriminating vertical.  
**Authority:** This is an additive research handoff, not an Agent OS workstream, a replacement for C19, an approved new engine, or an instruction to change the production Prophet gate.  
**Procedure reference:** Mastermind protected `master` at `d837e04bf60a9fb60b7c530d287115a298fc1af0` (`docs/sol_skills/INDEX.md` schema `mastermind.sol_skillpack.v1`, version 1.0.1).  
**Implementation evidence pin:** Macro `5569baad64b8023e5cb1995c1ce7a30bc8254a7b`. All live-state claims below are bounded by their specific dated source; no fresh production/browser verification was performed in this research phase.

## Decision-level conclusion

The strong-Q1 / priced-in-Q2 hypothesis is plausible but materially underspecified. It combines at least five distinct processes: (1) rational belief updating after operating surprises; (2) expectation extrapolation or miscalibration; (3) changes in intrinsic expected cash flows and horizon-specific analyst forecasts; (4) changes in discount rates and valuation multiples; and (5) investor positioning, market liquidity and peer-information diffusion. The same Q2 operating acceleration can lead to upward repricing or sell-the-event depending on which expectations and economic costs change.

**Do not build a new universal market-belief store or a single `priced_in_score`.** Existing company law explicitly rules this out (see `DEC-MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE`). Model family-specific expectation observations and their comparability, then compose an explainable product view over owner-native facts. MAS-119 federates common expectation semantics; MAS-118 owns market-incorporation science; MAS-271/C19 is qualifying the earnings expectation input; the existing Earnings Intelligence OS/event spine owns the earnings truth; downstream product views consume evidence by reference.

**Next critical dependency:** qualify genuinely comparable, as-known-at analyst baseline observations for at least one real issuer/fiscal target and two earlier collection vintages, *or demonstrate typed noncomparability with a precise missing input*. Without this, an “earnings expectations gap” cannot honestly be computed; the existing reaction-momentum proxy is not an adequate substitute.

## 1. Evidence already in the estate — do not repeat

1. `macro/agentos/decisions/DEC-EARNINGS-INTELLIGENCE-IS-A-CENTRAL-LOBE.md`: explicit decision that Earnings is a central lobe integrated with Company Event, Terminal, dossier and Neural Web, not a separate app.
2. `macro/agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md`: E0, E1, E1P and E2 marked done; recorded AAPL FY2026 Q3 production event workspace and dossier slice. **This proves a bounded slice by its source record, not live coverage for all issuers.** The next E3 product wave is not assigned by that closed record.
3. `macro/research/entry_stack/W4_EARNINGS_REACTION_PRIOR.md`: pre-registered internal analysis of 98,975 Item 2.02 announcement timestamps / 1,314 names in its broad source, and a deep subset of 16,128 events / 200 current-index names across 2004-09 to 2026-05. Deep subset reported reaction decile top-minus-bottom 5d +0.593%, 20d +0.768%, 60d +1.248% before further controls; placebo-adjusted extreme-arm impact about +0.36%/-0.36% over five days, no robust 20d/60d extreme-arm result, a weaker post-2016 era, and no discovery surviving the wide-panel multiplicity check (BH-FDR q > 0.10, reported DSR 0.0). **Internal reported results were not independently recomputed in this turn.** This is a research null against promoting an earnings-reaction-only ranker.
4. `macro/research/prophet_us_audit/EARNINGS_CATALYST_LOBE_ASSESSMENT_2026-08-10.md`: internal pre-event Prophet confluence test, n=726 versus n=9,497: reaction difference -0.305 percentage points, CI -0.690 to +0.079 (indistinguishable). Existing T-3 pre-earnings normal entry holdout was retained because near-event tail downside was materially worse. Do not reinterpret an upward price curl as evidence of informed trading or remove the gate.
5. `macro/collectors/equity_revisions.py`: SRC-A1 append-only Yahoo/yfinance raw expectation captures and attempts with provenance, fiscal-period end, market session, publication/observation timestamps, rights and corrections. The older generic revisions collector explicitly cannot recreate the past from current Yahoo snapshots.
6. `macro/engine/k3e_expectation_surface.py`: EXP-1 declared capture inspection; at source head, `normalized_baseline` is not admitted from raw capture without proper comparability; it is not a published street consensus history.
7. `macro/research/product_intelligence_local_delivery/E0_EXPECTATIONS_ACCEPTANCE_PATH_2026-10-06.md`: documented raw source/reader acceptance and remaining identity, basis, rights and publication constraints at its October 6 source pin.
8. `macro/agentos/workstreams/WS-COMMISSION-19-DATA-INTELLIGENCE.md` and `Mastermind/research/commission_19_fable_masterplan/2026-10-11/WORK_PACKAGES.md`: C19 has an active Fable-owned plan; WP09 (MAS-271) qualifies native comparability; WP10 qualifies *separate* issuer guidance changes. Do not create competing writers or treat guidance as analyst consensus.
9. `macro/agentos/decisions/DEC-K3E-EXPECTATION-MARKET-DYNAMICS-FREEZE.md` and `DEC-MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE.md`: market incorporation must remain family-specific; no universal gap score, independent belief store or unauthorized rank/size authority.
10. Existing `engine/expectation_state.py` provides display-only SUE, streak and price-drift context; `engine/sue.py`, `collectors/edgar_eps.py`, `engine/earnings_blackout.py`, guidance, transcript/evidence and event-workspace components already exist. Do not recreate these systems.

**Capability ledger (source bounded):** earnings event times BUILT; quarterly SUE BUILT/PARTIAL by coverage; transcript provenance BUILT; golden AAPL E2 slice source-reported PROVEN_LIVE; comparable forecast history PARTIAL; expectation normalization/PIT publication PARTIAL; standalone prospective earnings reaction predictive edge NOT_BUILT/not validated; broad issuer-wide full-product live proof NOT ESTABLISHED.

## 2. Additional independently inspected external evidence

2026 earnings releases establish that cloud demand accelerated across the three initial cases:
- Alphabet Q1 release (2026-04-29): Google Cloud +63% YoY, consolidated revenue +22%. https://www.sec.gov/Archives/edgar/data/1652044/000165204426000043/googexhibit991q12026.htm
- Alphabet Q2 release (2026-07-22): Google Cloud +82% YoY, consolidated revenue +24%; other income included a large $98.0B unrealized-investment-related net gain. https://www.sec.gov/Archives/edgar/data/1652044/000165204426000066/googexhibit991q22026.htm
- Amazon Q1 release (2026-04-29): AWS +28% YoY; Amazon reported pre-tax investment gains of $16.8B. https://www.sec.gov/Archives/edgar/data/1018724/000101872426000012/amzn-20260331xex991.htm
- Amazon Q2 release (2026-07-30): AWS +37% YoY and operating income $27.5B. https://www.sec.gov/Archives/edgar/data/1018724/000101872426000024/amzn-20260630xex991.htm
- Microsoft FY2026 Q4 release (2026-07-29): Azure and other cloud services +43% YoY; non-GAAP EPS is reported separately from investment gains. https://www.sec.gov/Archives/edgar/data/789019/000119312526323632/msft-ex99_1.htm

**Implication:** EPS headline “beats” are dangerous without uniform nonrecurring-item and GAAP/non-GAAP treatment. The above releases do not by themselves establish prior expectations, the buy side's belief, price reactions, or causal market psychology. Those require period-matched pre-event vintages and verified tape.

Published research:
- Fink (2021) reviews PEAD and conflicting underreaction, risk, friction mechanisms: https://doi.org/10.1016/j.jbef.2020.100446
- Soffer & Lys (1999) model how prior announcement information diffuses into subsequent-quarter expectations: https://doi.org/10.1111/j.1911-3846.1999.tb00583.x
- Analyst responsiveness and PEAD (2008): timely forecast revisions associate with more of the price adjustment occurring in-event and less afterward: https://doi.org/10.1016/j.jacceco.2008.04.004
- Chordia et al. (2009): liquidity and costs substantially affect attainable PEAD profit: https://business.columbia.edu/faculty/research/liquidity-and-post-earnings-announcement-drift
- Baker et al. (2018): inter-industry peer announcements convey transferable information, with conditioning by economic state and relative size: https://www.sciencedirect.com/science/article/pii/S1057521917300212
- A 2026 SSRN working paper (not established consensus) argues longer drift can disappear under a different expected-return decomposition: https://papers.ssrn.com/sol3/Delivery.cfm/6440878.pdf?abstractid=6440878&mirid=1. Treat as an adversarial hypothesis; do not assert peer-reviewed resolution.

## 3. Scientific problem split: three different forecasts

Do not collapse a fundamental beat, a stock gap and subsequent drift:

**Target F — Fundamental surprise:** for each named metric (adjusted EPS, revenue, margins, product/segment KPIs, guidance midpoint), estimate surprise *only* against an actual period-, currency-, unit-, accounting-basis- and knowledge-time-matched baseline. Store `UNESTIMABLE` when a comparable prior is absent. Regression/class probabilities only after a validated sample exists.

**Target R — Earnings information repricing:** benchmark-/factor-adjusted return measured from the final regular-session close before a valid, timestamped release to the first regular-session close with released information. Explicitly differentiate premarket, after-close, intraday and delayed release. Predict conditional reaction distribution, downside quantiles and magnitude, not just up/down. Options-implied move is a separate forecast/contract, never represented by historical realized volatility as if equivalent.

**Target D — Post-release drift:** from the first actionable post-release decision/price to H5/H10/H21 and optionally H60, adjusted for sector, factor exposure, volatility and costs, including adverse/favorable excursion. Do not leak first-session information into a before-announcement model. Model F, R and D separately and test whether joint output adds information.

A fourth **explanatory** quantity is the *incorporation state*: evidence that the information is already reflected in price or estimates. Avoid a universal numeric “priced-in percentage.” Distinguish measured, bounded-inference, competing-interpretation and unavailable conditions.

### Market-implied expectation identifiability

A price is the output of expected cash flows, discount-rate distribution and time-varying risk premia. Inverting a single current price does **not uniquely identify** investors' expected earnings, growth, or surprise.

Use multiple defensible scenario assumptions: `P = Σ E[FCF_t] / (1 + r_t)^t` plus terminal value. Report ranges of *implied conditions* under independently specified `r_t`, margin, reinvestment and terminal assumptions. Never claim “the market expects cloud growth X%” purely from one valuation. For composable earnings data, use a typed list of native baseline observations instead of a speculative canonical belief number.

### Separate expectation layers

- **Published company guidance:** source-backed manager forecast; not analyst consensus.
- **Surveyed analyst consensus:** requires usable pre-event-vintage individual estimates, comparable basis and rights.
- **Market-implied scenarios:** estimated under explicit model assumptions, not directly observed beliefs.
- **Options-implied risk:** forward risk-neutral move/distribution, not future earnings consensus or objective physical probability.
- **Behavioral/narrative proxies:** attention and sentiment measures, never mind-reading.
- **Price incorporation:** measured relative behavior with factor/sector controls, not automatic causal proof.

## 4. Point-in-time research contract

Event identity: immutable issuer subject + economic fiscal reporting period + canonical event identity/version. GOOG/GOOGL share an issuer event; ticker aliases are effective-dated. Preserve earnings calendar prediction and later actual announcements separately; SEC filing date alone is not always actual first-publication timestamp.

Every feature observation must identify at minimum:
`subject_id`, `fiscal_target`, `metric`, `unit`, `currency`, `accounting_basis`, `aggregation_level`, `native_horizon_label`, `contributor_or_aggregate_class`, `source_id`, `source_published_at`, `provider_observed_at`, `system_observed_at`, `decision_asof`, `rights_class`, `correction_state`, `missing_reason`.

For decision cutoff `T`, admissible information needs *both* public/source availability and platform availability at/before `T`; a superseding correction after `T` cannot silently replace the original observation. No automatic conversion between current 1Q/Y1 relative labels when underlying fiscal period changes. Explicitly distinguish missing from zero, estimated from sourced, revenue from EPS, GAAP from adjusted, basic from diluted, guide range from surveyed average, original from corrected, real expectation revision from provider horizon roll. An intraday date-only forecast vintage is insufficient to prove it preceded the release.

## 5. Prioritized falsifiable experiments

### EXP-0 — Event reconstruction and data adequacy (mandatory first)
Select Alphabet, Amazon and Microsoft 2026 Q1/Q2 plus six negative/control events chosen *before* outcomes are measured. Reconstruct issuer, fiscal targets, SEC/IR release clocks, as-known-at guidance and consensus, 20/10/5/1-day pre-event returns, next actionable session, factor benchmark, and 5/20-day follow-through. Produce nine+ event dossiers. Before measuring event timing outcomes, verify the price data and corporate-action methodology.

**Accept:** each event has complete provenance and either comparable baseline or explicit typed missingness. Identify why each post-event move is explainable by *measured* economic surprises versus unverified narrative. Do not use the prior conversational table of nine stock returns as sourced evidence.

### EXP-1 — Comparable expectation baselines (binding)
Consume existing SRC-A1/EXP-1 and C19 WP09 without changing their writer paths. Choose one real issuer and fixed fiscal EPS/revenue target, inspect two or more consecutive capture vintages, issuer identity, fiscal period, basis/currency/rights and publication clock. Audit an actual normalized analyst baseline only when accepted by the existing owner. Separate analyst estimate revisions from guidance revisions (WP10). Include malformed period roll, missing contributor, stale/withdrawn, late observation and provider-rights counterexamples.

**Accept:** deterministic comparable baseline and valid delta **or** a successful principled refusal with precise gap and no published synthetic consensus. This test is more important than adding features to a model.

### EXP-2 — Re-evaluate simple event science on admitted PIT cohorts
Use the existing Item 2.02/event reaction research as control, not rebuild. On the same cohort and matched non-event days test pre-event abnormal appreciation, estimation revisions, and interaction; include positive and negative news; correct era, cross-issuer, factor, sector and liquidity confounds. Use event-date clustered uncertainty, error rates and multiple-hypothesis discipline. Benchmark against trivial sign/return models.

**Accept:** preregistered null or quantified conditional incremental effect that survives chronological holdout; never infer accuracy from an in-sample story.

### EXP-3 — Earnings-expectation revision acceleration
For consecutive issuer-quarter observations, investigate whether analyst expectation revisions accelerate in the post-Q1/pre-Q2 interval and whether the next surprise and return depend on (revision velocity, revision breadth, valuation appreciation) interactions. Exclude forecasts that arrive after the relevant cutoff; do not treat rollovers as estimate changes. Report sample coverage by vintage.

**Accept:** statistically interpretable conditional effect and specific negative controls; otherwise reject the expectations-ratchet trading edge while retaining descriptive value.

### EXP-4 — Nonlinear valuation and economic investment
Study price decomposition with *fixed fiscal targets* and consistent per-share adjustments. Separate changes in forecast EPS/FCF from forward valuation multiple changes and interest-rate sensitivity; model capex/FCF economics for AI hyperscalers. Challenge the interpretation with risk-premium movement and nonrecurring investment gains.

**Accept:** decomposition reconciles to price changes within stated assumptions and does not describe changing P/E as a behavioral cause by fiat.

### EXP-5 — Peer/read-through value
Anchor mechanisms (customer revenue sensitivity, common demand, input cost, shared infrastructure budget) on disclosed relationships and known earnings event availability. Compare observed peer moves to sector controls and to eventual target reported data; negative-control unrelated peers. Reuse Earnings Neural Graph's three graph families (economic exposure, narrative similarity, residual price behavior) without collapsing them into one ungrounded connection score.

**Accept:** proven incremental information, or display-only source-grounded read-through hypotheses with falsifiers.

### EXP-6 — Independent scientific challenge
Compare a model using only known early signals against additional AI-derived transcript/management narrative. Evaluate neutral and contradictory text, topic novelty, citations, translation quality and event-claim contradictions. Compare against direct numeric signals at equal data availability.

**Accept:** demonstrable incremental validation for model use; otherwise limit LLMs to cited explanatory synthesis.

## 6. Architecture: compose, do not replicate

Existing component owners:
- **Earnings Event / Company Intelligence:** event identity, releases, transcript and guidance evidence, event_workspace/corrections.
- **SRC-A1/EXP-1 under Alpha/expectations owner:** raw estimate observations and admitted comparable baseline (when available).
- **FIF:** financial metric definitions, direct financial arithmetic and PIT financial vintage.
- **MAS-119 Catalyst Federation:** cross-family typed expectation semantics, not a replacement of source native objects.
- **MAS-118 incorporation science:** factor-adjusted market reaction and post-event incorporation evidence.
- **Theme / company relationship owner:** mechanism-specific peer exposures, independent of correlation-only graph.
- **Terminal/dossier/Integrated Answer consumers:** read-only views over accepted native evidence and explicit conflict/missingness.
- **Prophet:** research consumer only; no rank/gate/size authority absent its separate prospective approval.

Proposed minimal **read-only composed view** (not a new source-of-truth store):
`event_ref`, `asof`, `issuer_ref`, `fiscal_target`, `evidence_refs[]`, `guidance_change{status,ref}`, `comparable_consensus{status,ref}`, `fundamental_variance{status,metric,ref}`, `market_incorporation{status,method,window,ref}`, `peer_readthrough[]{mechanism,source,target,ref}`, `conflicts[]`, `missing_reasons[]`, `authority='RESEARCH_DISPLAY_ONLY'`.

Render **what changed / what was already known / what's unestimable / what happened in the tape**. Preserve source links and computation method. Never output `earnings_edge_score`, `gap_score`, buy/sell classification or model-originated sizing from the research view.

## 7. Staged implementation plan (each phase earns its next phase)

**P0 — Source and owner reconciliation.** Consume the existing E0/E2, K3E-0, SRC-A1/EXP-1, C19 MAS-271, MAS-118/119 and Prophet holdout decisions; resolve active writer, current code revisions and acceptance paths before effects. Deliver one source-bound gap ledger. *Acceptance:* no duplicate builder, no changed protected semantics, explicit candidate owner/consumer.

**P1 — One issuer PIT comparability fixture.** Reuse the current owner to qualify the exact estimate/guide fiscal target across vintages and changes. *Acceptance:* positive comparable case plus adversarial null/refusal cases, rights and correction lineage. If no lawful usable baseline exists, proceed with explicit null and evaluate historical licensed-source procurement rather than fabricate history.

**P2 — Exact earnings event dossier.** Render at least one actual event into existing event workspace/Terminal or read-only research report: Q1→Q2 operating figures, prior guidance, independently admitted expectations, event price/path, valuation context and claim citations. *Acceptance:* an entitled user can distinguish what was observed from inferred and absent; corrections propagate; no model-generated trade signal.

**P3 — Historical experiment harness.** Reuse existing event-prior/backtest harness with a preregistered versioned featureset, stronger controls, true PIT estimability mask, joined consensus where lawful. *Acceptance:* accepted numerical tables, era sensitivity, negative cases, multiple-testing accounting, and reproducible provenance; failing signals explicitly rejected.

**P4 — Shadow fundamentals/reaction/drift research.** Only if comparable data sample supports it. Predefine candidate models and strong baselines; walk-forward with purging/embargo across issuer peers, cash-session event times, sample-rights separation, uncertainty calibration. *Acceptance:* prospective shadow outcomes that outperform meaningful baselines net of costs, or a robust negative result. No Prophet promotion from this phase.

**P5 — Peer/read-through and richer explanations.** Extend the existing relationship/graph read-through only for demonstrably useful disclosed economic mechanisms. *Acceptance:* one dated source event produces correctly timed target hypotheses with true/false outcomes and non-correlated negative controls.

**P6 — Product expansion decision.** Compare user value, data rights/cost, experimental success and product maintenance. Only then decide whether additional event sleeve, premium earnings expectation intelligence, or public education surfaces are warranted. Product/release owner separately proves integration, entitlement, user path, and production freshness.

Dependency order: P0 → P1 → P2, while an independent P0-scoped historical-case preparation can run; P1 plus event tape are necessary for P3; P3 precedes P4; P2 permits a research-grade explanatory UI independent of a predictive win; P5 may use its own source-backed mechanism cases after P2; P6 requires real evidence from relevant branches. An absent full consensus history blocks the predictive expectation-gap lane, **not** explanatory issuer event context.

## 8. Data/economic decision gate

Do not purchase a broad historical-estimates vendor prematurely. First document the exact needed fields: EPS and revenue analyst snapshots as-of the 2026 case events; fiscal target; accounting basis; contributor identity/aggregate method; vintage publication time; coverage; right to store/replay/model and display; correction policy; true historical point-in-time coverage. Compare with (a) current capture accrual for future-only research, (b) narrow licensed historical backfill, and (c) conditional guidance-only analysis. Price the acquisition *only* after a representative sample and rights check. Include one realistic quote/vendor feasibility memo with explicit unknowns, not invented prices.

Do not substitute option-implied move for earnings expectation, or historical volatility for option data. Single-stock options remain a second-phase source class after core expectation history is accepted.

## 9. Risks, falsifiers and critical guardrails

- **Overfitting:** 30 proposed research directions yield many researcher degrees of freedom. Freeze primary outcomes and comparison baselines before outcome inspection.
- **Event misalignment:** SEC Item 2.02 acceptance timestamp can lag the true first public release. Reconstruct source-availability times.
- **Survivorship:** current index members in a 2004-era sample are not a historical universe.
- **Reporting classification:** investment gains may dominate reported EPS. Define recurring versus GAAP/adjusted basis.
- **Forecast identity:** Yahoo '+1q' and '+1y' can roll fiscal targets without any analyst changing an estimate.
- **PIT integrity:** later overwritten/latest snapshots cannot support retrospective trading predictions.
- **Econometric confounds:** macro release, sector news, discount rates, liquidity and share-class links may explain event moves.
- **Vendor rights:** research ingestion rights may differ from data publication rights.
- **Causal limits:** price returns alone do not reveal institutional psychology or options dealer hedge flows.
- **Promotion fence:** output remains evidence, description and hypotheses until independent chronological/prospective validation and existing signal authorities admit it.

## 10. Concrete next action and owner/custody

**Immediate technical research action:** In the current C19 MAS-271 / Alpha SRC-A1/EXP-1 incumbent carrier, choose one real issuer/fiscal period/metric and adjudicate the two-vintage normalization test (WP09). The result should be an exact comparable baseline or a precise rights/basis/identity noncomparability receipt, consumed by an identified event workspace/Integrated Answer user path. This document creates no substitute job or modifying writer.

**Independent immediately ready work:** Reconstruct the 2026 GOOGL/AMZN/MSFT event chronology as a research-only casebook with primary release clocks and precise initial market-price windows; do not score earnings reaction with late consensus. Compare these to named negative controls selected before returns are consulted.

**Not done here:** no backtest was rerun; no license purchased; no live collector/job executed; no product view changed; no source-owner records edited; no trading authority added; no production user-path verified.

## Source navigation

Internal authoritative/context links (immutable Macro source evidence):
- https://github.com/mastermindx-market-intelligence/macro/blob/5569baad64b8023e5cb1995c1ce7a30bc8254a7b/research/entry_stack/W4_EARNINGS_REACTION_PRIOR.md
- https://github.com/mastermindx-market-intelligence/macro/blob/5569baad64b8023e5cb1995c1ce7a30bc8254a7b/research/prophet_us_audit/EARNINGS_CATALYST_LOBE_ASSESSMENT_2026-08-10.md
- https://github.com/mastermindx-market-intelligence/macro/blob/5569baad64b8023e5cb1995c1ce7a30bc8254a7b/agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md
- https://github.com/mastermindx-market-intelligence/macro/blob/5569baad64b8023e5cb1995c1ce7a30bc8254a7b/agentos/decisions/DEC-MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE.md
- https://github.com/mastermindx-market-intelligence/macro/blob/5569baad64b8023e5cb1995c1ce7a30bc8254a7b/agentos/decisions/DEC-K3E-EXPECTATION-MARKET-DYNAMICS-FREEZE.md
- https://github.com/mastermindx-market-intelligence/macro/blob/5569baad64b8023e5cb1995c1ce7a30bc8254a7b/collectors/equity_revisions.py
- https://github.com/mastermindx-market-intelligence/macro/blob/5569baad64b8023e5cb1995c1ce7a30bc8254a7b/engine/k3e_expectation_surface.py
- https://github.com/mastermindx-market-intelligence/Mastermind/blob/d837e04bf60a9fb60b7c530d287115a298fc1af0/research/commission_19_fable_masterplan/2026-10-11/WORK_PACKAGES.md

**This report is research evidence and a plan, not a canonical organizational decision or deployment receipt.**
