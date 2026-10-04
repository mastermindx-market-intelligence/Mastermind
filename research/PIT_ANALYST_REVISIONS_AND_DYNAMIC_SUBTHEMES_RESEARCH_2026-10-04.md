# MastermindX Research — Point-in-Time Analyst Revisions & Dynamic Subtheme Intelligence

**Status:** RESEARCH ONLY — no procurement, production ingestion, deployment, portfolio/trading behavior change, or new source decision authority is authorized by this document.  
**Protected source pin used for publication:** `mastermindx-market-intelligence/Mastermind@84df29801d4078724c2b603a136de5aa1532cdfe`  
**Skillpack:** `mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`  
**Publication date:** 2026-10-04  
**Confidence convention:** HIGH = directly verified in current protected Git or primary vendor documentation; MEDIUM = supported but incomplete; LOW = requires vendor/sample/license confirmation.

> Publication note: the preceding Deep Research run contained several over-broad or weakly sourced current-state claims. This GitHub version tightens the source boundary. Internal Mastermind claims below are limited to facts observed at the protected source pin. Vendor details that were not established from primary documentation are explicitly left unverified rather than filled with assumptions.

## A. Executive conclusion

Mastermind should build the **capability to reconstruct market expectations point-in-time**, with analyst forecast revisions as a first-class, inspectable evidence family. The capability is important because Mastermind already names `fundamental_revisions` / `earnings_expectations` as an evidence family, while current protected research explicitly says the repository does **not** expose a mature historical revisions series suitable for persistence research. The same protected research also says historical fine-grained dynamic subtheme identity must not be fabricated.

The correct P0 is therefore **not “buy vendor X” and not “wire a revisions score into the portfolio.”** It is:

1. establish a canonical bitemporal contract for estimate observations, coverage, fiscal-period identity, corrections, actuals, and consensus snapshots;
2. run a bounded source bake-off proving PIT reconstructability and rights;
3. build deterministic revision/dispersion/breadth/staleness features only from eligible observations;
4. prove incremental predictive value against existing SUE, price, options, news, guidance, fundamentals, flow, theme, and macro evidence;
5. promote only evidence dimensions that survive leakage, cost, correlation, and out-of-sample tests.

**What is proven internally (HIGH):**
- `portfolio/held_risk.py` contains an `earnings_expectation` lane and `_lane_earnings_expectation(...)`; its documented real-data mapping includes earnings summary fields and `revisions.est_chg_30d`.
- `research/TREND_PERSISTENCE_PROTOCOL.md` explicitly says the current census does not expose a mature historical revisions series suitable for the experiment and forbids fabricating analyst-revision persistence.
- The same protocol explicitly says there is no clearly canonical fine-grained dynamic subtheme taxonomy in this repository and requires PIT membership before dynamic subtheme/network persistence work.
- Portfolio V3 source contains `source_family: fundamental_revisions` and `independence_family: earnings_expectations`, and the repository contains a Decision Snapshot implementation plan.
- `brain/signal_history.py` is an existing KEEP-FIRST decision-time history owner; `brain/outcome_ledger.py` joins what the engine predicted, what happened, and what it saw.

**What remains unproven:** which commercial source best satisfies analyst-level PIT reconstruction; exact licensed history/latency/correction semantics by package; economic alpha after modern costs and controls; and whether dynamic subthemes add incremental information beyond existing group/theme evidence.

**Recommendation-changing evidence:** reject or materially down-rank this build if no candidate source can reproduce historical knowledge states without post-hoc correction leakage, if rights prevent required internal use, if analyst-detail adds no material value over PIT consensus, or if the family fails pre-registered incremental OOS tests after realistic costs.

## B. Current-state census

### Verified protected-repository observations

| Artifact | Exact observed symbol/contract | Observed behavior | Temporal semantics | State | Material implication |
|---|---|---|---|---|---|
| `portfolio/held_risk.py` | `_lane_earnings_expectation(sd, run_date)`; lane name `earnings_expectation` | Consumes earnings/SUE-style state plus revision direction; search evidence shows `revisions.est_chg_30d` in the real-data mapping | Decision-time lane, but the search evidence alone does not prove a mature historical analyst-detail source | BUILT | Revisions already have a consumer shape; do not create a parallel evidence plane |
| `tests/test_held_risk.py` | fixtures include `revisions.breadth`, `est_chg_30d`, `est_chg_90d`, `net_up_30d`, `n_analysts` | Tests expected lane behavior with synthetic revision fields | Test fixtures are not proof of live historical source provenance | BUILT test contract | Canonical source work should preserve inspectable dimensions rather than invent a new opaque score |
| `research/TREND_PERSISTENCE_PROTOCOL.md` | “Fundamental-revision gap” and “Theme identity gap” | Explicitly blocks revision persistence until canonical PIT history exists; blocks fabricated historical fine-grained theme membership | Requires PIT histories/effective dating | LIVE research law / charter | Strongest current internal evidence that history is the missing substrate |
| `brain/signal_history.py` | KEEP-FIRST per `(asof, ticker)` lens snapshot + decision | Preserves what the engine saw at decision time | PIT decision snapshot semantics | BUILT | Candidate derived revision evidence should attach to the existing decision-time history rather than create a second memory ledger |
| `brain/outcome_ledger.py` | joins prediction + realized result + decision-time lens snapshot | Grades calibration and lens edge | Historical join over decision-time snapshots and realized outcomes | BUILT | Natural owner for incremental validation outcomes |
| Portfolio V3 design | `source_family: fundamental_revisions`; `independence_family: earnings_expectations` | Specifies evidence-family separation and Decision Snapshot direction | PIT/correction-safe architecture is an explicit design concern | PARTIAL / mixed implementation | New revisions evidence must preserve independence/provenance semantics |
| `docs/superpowers/plans/2026-09-15-mastermind-portfolio-v3-s0-decision-snapshot.md` | Decision Snapshot vertical | Plan describes immutable, bounded, correction-safe PIT snapshot and read-only inspection | Explicit PIT/correction-safe language | PLAN with adjacent implementation evidence in repo | Integrate through existing snapshot/provenance owners; do not create a parallel control plane |
| `research/competitive_intelligence/fiscal/2026-08-22/recon01/observations.jsonl` | observations of estimates/revision-history surfaces | Shows prior lawful reconnaissance of estimate/revision UI capabilities; raw authenticated assets were omitted for rights safety | Remaining unknown explicitly includes provider/PIT export semantics | OBSERVED reconnaissance | Reuse as product-intelligence evidence, not as a licensed historical dataset |

### Gaps that are directly supported by protected source

1. **Historical analyst-revision maturity gap — HIGH.** Protected research says the current census does not expose a mature historical revisions series suitable for the persistence experiment.
2. **Fine-grained dynamic subtheme PIT identity gap — HIGH.** Protected research says no clearly canonical fine-grained dynamic subtheme taxonomy is present and forbids projecting current membership backward.
3. **Consumption vs existence must be separated — HIGH.** Synthetic revision fields in tests and an earnings-expectation consumer do not prove source maturity, historical PIT correctness, or production coverage.
4. **Decision-time evidence has an existing owner — HIGH.** `brain.signal_history` / outcome infrastructure should be extended, not duplicated.

### Not established by this publication

This report does **not** claim that every starting-point file from the original commission has been fully line-by-line re-audited, nor does it claim that Macro, Terminal/charting, or Research Vault repository identities have been completely reconciled here. Those are mandatory pre-build archaeology items for the implementation owner.

## C. State-of-the-art research

### Point-in-time expectation data

Institutional-grade estimate research requires reconstructing what was knowable at a historical decision timestamp, not merely querying a vendor’s latest corrected history. “Estimate date,” “snapshot date,” “vendor as-of,” and “Mastermind known-at” are not interchangeable.

LSEG’s public company-data catalogue states that its company data includes point-in-time data and I/B/E/S estimates, with broad global coverage and multiple delivery surfaces. LSEG’s StarMine Analyst Revisions Model publicly states that it uses earnings, revenue, EBITDA and recommendation revision signals and covers 17,600 public companies since 1995. These claims establish that revision-oriented institutional products exist; they do **not** by themselves prove that every delivery package exposes raw analyst-level bitemporal history suitable for Mastermind’s reconstruction requirements.

WRDS’ I/B/E/S vendor page documents a critical identity hazard: broker and analyst identifiers were reassigned in a major 2018 change, and WRDS warns that additional reshuffles can occur. Therefore analyst/broker IDs must be treated as vendor-vintage-scoped identifiers unless a verified stable crosswalk exists.

### Quant implications

The research program should distinguish:
- **earnings prediction**: whether revisions improve forecasts of future actuals;
- **cross-sectional return prediction**: whether revisions predict residual returns after factor/sector/country/liquidity controls;
- **event interaction**: whether revisions add information conditional on SUE/PEAD, guidance, and earnings-event timing;
- **information decay**: whether any historical anomaly survives in modern samples after transaction costs and crowding.

The literature review for implementation approval must prioritize original papers and modern replications on forecast revisions, dispersion, PEAD/SUE interactions, analyst skill/herding, stale estimates, and anomaly decay. Publication-era results are hypotheses, not promotion evidence.

### Dynamic themes

Protected Mastermind research already has sector/theme/basket context but explicitly lacks canonical fine-grained dynamic subtheme PIT identity. Industry thematic frameworks support the idea that themes evolve and can be measured using text/NLP, but that does not justify backfilling a modern taxonomy into history. Prospective effective-dated capture should begin only under an accepted canonical contract.

## D. Source landscape

| Source | Coverage | History | Latency | PIT quality | Corrections | Rights | Cost class | Best use |
|---|---|---|---|---|---|---|---|---|
| LSEG I/B/E/S / company data | Broad global estimates; exact package scope must be confirmed | Public LSEG material indicates long company-data history; exact detail-history start varies | Package-dependent | Potentially strong; must prove raw/detail reconstruction | Must confirm vintage/correction delivery; WRDS documents ID reshuffles | Commercial license | Enterprise | Candidate analyst-detail and/or consensus source |
| LSEG StarMine ARM | Public claim: 17,600 public companies | Public claim: since 1995 | Model/product dependent | Derived model, not a substitute for raw PIT detail | Model recalibration/inputs require documentation | Commercial license | Enterprise | Benchmark/derived comparison, not canonical raw source |
| S&P Capital IQ Estimates / Visible Alpha | Broad sell-side estimate/model coverage | Deep history claimed by S&P; exact metric/region start must be confirmed | Product dependent | Potentially strong; analyst-detail vs consensus capabilities must be separated | Must confirm correction/vintage semantics | Commercial license | Enterprise | Candidate detailed expectations/KPI source |
| FactSet Estimates | Broad institutional estimate coverage | UNVERIFIED here by primary package documentation | Product dependent | Must prove PIT snapshots/detail rather than assume | Must confirm | Commercial license | Enterprise | Bake-off candidate |
| Bloomberg Estimates | Broad institutional coverage | UNVERIFIED here | Fast/current | Historical analyst-detail reconstructability unverified | Must confirm | Commercial license | Enterprise | Current monitoring / bake-off candidate if licensed |
| WRDS I/B/E/S access | Research access to I/B/E/S where institutionally licensed | Dataset/package dependent | Batch/research | Strong research utility; vintage handling is mandatory | WRDS explicitly warns of analyst/broker ID reshuffles | Academic/institutional license | Institutional | Research-grade validation where available |
| SEC EDGAR/XBRL | US issuer filings/actuals/guidance evidence | Filing history; XBRL era strongest | Filing-time | Strong event timestamp for issuer disclosures; not analyst consensus | Amendments/restatements explicit in filings | Public | Free | Actuals, issuer guidance, filing-time controls; **not a substitute for analyst estimates** |
| Public industry codes (NAICS/SIC) | Broad issuer/entity classification | Scheme/version dependent | Slow | Can be effective-dated if versions/mappings retained | Reclassification/version changes | Public/low | Low | Baseline static cohorts |
| Licensed GICS/ICB/RBICS/theme products | Broad classification depending vendor | Vendor dependent | Periodic | Must retain membership effective dates | Rebalances/reclassifications | Commercial | Enterprise | Candidate baseline taxonomy, not automatically dynamic PIT truth |
| News/transcripts/filings text | Broad event corpus depending rights | Source dependent | Minutes to filing-time | PIT possible if original publication timestamps and corpus versions retained | Corrections/retractions/model-version drift | Mixed | Mixed | Prospective dynamic-theme evidence |

**Do not treat open finance websites as substitutes for PIT estimate history unless they can prove historical vintages, correction behavior, identifiers, and rights.**

### Primary references used for source claims

- LSEG company data: https://www.lseg.com/en/data-catalogue/company-data
- LSEG StarMine Analyst Revisions Model: https://www.lseg.com/en/data-catalogue/analytics/quantitative-analytics/starmine-analyst-revisions-model
- WRDS I/B/E/S vendor page: https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/vendor-partner-ibes/
- S&P Global discussion of Capital IQ / Visible Alpha estimates: https://www.spglobal.com/market-intelligence/en/news-insights/research/2026/08/the-price-of-intelligence
- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- BlackRock thematic investing discussion: https://www.blackrock.com/us/individual/insights/thematic-investing
- MSCI thematic indexes: https://www.msci.com/indexes/category/thematic-indexes

## E. Canonical data model

The canonical model must be **vendor-neutral and bitemporal**. Never use one overloaded `as_of_date` to mean both source publication time and Mastermind knowledge time.

### 1. `security_entity_identity_v1`

Minimum fields:
`entity_id`, `security_id`, `vendor`, `vendor_security_id`, `ticker`, `exchange`, `currency`, `effective_from`, `effective_to`, `known_at`, `ingested_at`, `source_receipt_id`.

Purpose: PIT identifier mapping through ticker changes, listings, mergers, share-class changes, and vendor remaps.

### 2. `analyst_broker_identity_v1`

`vendor`, `vendor_vintage_id`, `vendor_analyst_id`, `vendor_broker_id`, optional normalized internal identity, `effective_from/to`, `known_at`, `correction_generation`, provenance.

**Invariant:** vendor analyst/broker IDs are not assumed stable across vintages.

### 3. `estimate_observation_v1`

`entity_id`, `security_id`, `metric`, `basis` (GAAP/non-GAAP/adjusted/vendor-defined), `period_type`, `fiscal_period_id`, `fiscal_period_end`, `fiscal_period_version`, `currency`, `units`, `split_basis`, `raw_value`, `normalized_value`, analyst/broker-vintage refs, vendor record ID, status, and the full temporal envelope.

### 4. `coverage_event_v1`

Coverage initiation, stop, resume, dropped estimate, broker termination, analyst reassignment, and vendor eligibility events. Coverage changes are signal candidates and missingness controls, not mere null-handling.

### 5. `actual_result_v1`

Actual metric value with issuer/source event time, vendor availability time, correction lineage, basis/currency/units, fiscal-period identity/version, and source receipt.

### 6. `consensus_snapshot_v1`

`entity_id`, metric/period identity, aggregation method, contributor count, mean/median/high/low/dispersion where licensed, stale-count diagnostics, and provenance indicating whether the snapshot is:
- vendor-provided; or
- deterministically derived from eligible analyst observations.

Never claim analyst-level reconstruction from consensus-only history.

### 7. `source_receipt_v1`

Source/vendor, package/version, request/export identity, checksum, acquisition time, documented cutoff/timezone, rights class, correction generation, raw-object locator, normalization version, and quality flags.

### 8. `theme_membership_v1`

`entity_id`, `theme_id`, taxonomy/version, membership source, `effective_from/to`, `known_at`, confidence/score where appropriate, evidence refs, model/version for machine-derived assignments, and correction generation.

### Temporal semantics

Every time-sensitive record must distinguish:
- **event_time** — when the underlying economic/publication event occurred;
- **as_of** — source/vendor snapshot reference time;
- **observed_at** — when the source observation was made by the acquisition process;
- **available_at / known_at** — earliest time Mastermind can prove the information was available to the historical decision process;
- **ingested_at** — when Mastermind persisted it;
- **effective_from / effective_to** — business-valid interval;
- **correction_generation** — lineage for vendor QA, restatement, remap, or normalization corrections.

**Backtest eligibility gate:** a record is eligible only when its proven `known_at/available_at <= decision_cutoff`, under the historical acquisition policy being simulated. A vendor estimate date alone is insufficient.

## F. Derived intelligence

### Deterministic computation graph

`raw receipt → dedupe → correction/vintage selection → temporal eligibility → security/entity resolution → analyst/broker vintage resolution → fiscal-period alignment → basis/unit/currency/split normalization → coverage eligibility → stale-estimate classification → consensus construction → revision/breadth/dispersion calculations → quality/provenance flags → evidence artifact`

No LLM belongs in PIT eligibility, arithmetic normalization, estimate imputation, correction selection, or consensus calculation.

### Candidate deterministic features

Keep dimensions inspectable:
- consensus change over 1d/5d/20d/60d windows;
- revision magnitude scaled by price, prior estimate, or historical forecast error where economically valid;
- upward/downward revision breadth;
- analyst count and active coverage count;
- dispersion and dispersion change;
- stale-estimate share / age distribution;
- revision acceleration/deceleration;
- clustered same-direction revisions;
- initiation/termination/resumption events;
- analyst-detail vs consensus disagreement;
- time-to-earnings and post-earnings revision response;
- actual-vs-prior-PIT-consensus surprise;
- interaction terms with SUE/PEAD, guidance changes, price momentum, options-implied moves, and news intensity.

### Legitimate LLM roles

**Cheap models:** classify text evidence into a fixed taxonomy, extract candidate theme mentions from already timestamped documents, summarize provenance, and flag records for human/data-QA review.

**Frontier models:** research synthesis across heterogeneous evidence, proposed causal explanations, contradiction analysis, and candidate new-theme discovery for later deterministic adjudication.

LLMs must never invent numeric estimates, repair missing observations without trace, decide PIT eligibility, or silently overwrite source values.

## G. Mastermind integration map

| Producer | Canonical owner/artifact | Evidence family | Consumer |
|---|---|---|---|
| Licensed estimate source(s) | vendor-neutral PIT estimate contracts under existing data ownership | `fundamental_revisions` | existing earnings-expectation lane; research/shadow consumers |
| SEC/issuer disclosures | existing fundamental/event owners | actuals / guidance / fundamentals | revision controls, SUE/event interaction |
| Existing decision-time evidence | `brain.signal_history` | decision snapshot evidence | `brain.outcome_ledger`, calibration/research |
| Existing outcome infrastructure | `brain.outcome_ledger` / outcomes | realized grading | validation and promotion decisions |
| Existing Portfolio V3 snapshot/provenance direction | Decision Snapshot contracts | evidence provenance / independence | portfolio research and inspection |
| Effective-dated theme producer | existing theme/group owner once canonical | thematic exposure | rotation/theme research consumers |

**Architecture rule:** analyst revisions are an evidence family, not a new lifecycle, memory, outcome, portfolio-authority, or decision control plane.

## H. Empirical validation program

### Pre-register before looking at results

1. **Universe:** PIT investable universe with delisted securities retained; explicit country/exchange/security-type rules.
2. **Identity:** PIT entity/security mapping; corporate-action handling; no current-ticker backfill.
3. **Clock:** explicit decision cutoff, exchange timezone, market-hours policy, and next-executable-price convention.
4. **Vendor vintage:** fixed correction policy; raw snapshot/receipt hashes retained.
5. **Costs:** spread/slippage/fees, borrow where short legs exist, turnover and capacity.
6. **Controls:** sector/industry/country/size/liquidity, standard factor exposures, price momentum, SUE, guidance, options, news, fundamentals, flows/themes/macro where available.
7. **Horizons:** event-window, 1w, 1m, 3m, 6m; earnings-outcome horizons separately.
8. **OOS:** rolling/walk-forward; embargo/purging for overlapping labels where needed.
9. **Multiplicity:** family-wise or FDR controls across feature/horizon variants.
10. **Missingness:** test coverage initiation/termination and no-coverage as explicit variables.
11. **Ablations:** consensus-only vs analyst-detail; magnitude vs breadth vs dispersion vs staleness; with/without SUE; with/without event conditioning.
12. **Cross-source replication:** where rights/trials allow, compare the same security/date sample across vendors.

### Metrics

- rank IC / ICIR and incremental IC;
- cross-sectional regression alpha/t-stat after controls;
- calibration and error reduction for future earnings outcomes;
- top-minus-bottom spreads and monotonicity;
- turnover, realized costs, capacity and decay;
- regime/subperiod stability;
- missingness/coverage-selection diagnostics;
- incremental explanatory power over existing Mastermind evidence.

### Promotion thresholds

Set exact numerical thresholds in the preregistration after the candidate source sample is known. At minimum promotion requires:
- no unresolved PIT leakage;
- economically material OOS improvement, not statistical significance alone;
- stability across multiple subperiods/regimes;
- acceptable turnover/cost/capacity;
- incremental value after existing-evidence controls;
- reproducibility from retained receipts;
- rights compatible with intended internal use.

### Kill criteria

Reject or defer if any of the following holds:
- historical knowledge state cannot be reconstructed;
- vendor corrections overwrite history without recoverable vintages;
- identifiers cannot be reconciled sufficiently for the intended tests;
- rights block required storage/use;
- analyst-detail does not outperform materially cheaper PIT consensus;
- incremental OOS value disappears after SUE/momentum/news/guidance controls;
- alpha is consumed by costs/turnover/capacity;
- results depend on one fragile metric, era, sector, or vendor definition;
- missingness/coverage bias dominates the signal;
- dynamic theme membership cannot be effective-dated without retrospective leakage.

## I. Risks and failure modes

1. **Lookahead leakage:** post-hoc corrected histories masquerading as historical knowledge.
2. **Consensus/detail confusion:** treating consensus snapshots as if individual analyst histories can be reconstructed.
3. **Identifier instability:** especially analyst/broker IDs across I/B/E/S vintages.
4. **Fiscal-period drift:** FY1/FY2 or quarter identity can roll/remap after corporate calendar changes.
5. **Basis drift:** GAAP/non-GAAP/adjusted metric definitions can change.
6. **Currency/unit/split discontinuity:** revisions can be artifacts of normalization.
7. **Stale estimates:** consensus can move because old observations drop out, not because analysts revised.
8. **Coverage selection:** initiation/termination correlates with issuer size, liquidity and events.
9. **Survivorship:** current-covered issuers are not the historical investable universe.
10. **Correction leakage:** vendor QA performed later can improve historical data ex post.
11. **Evidence duplication:** revisions may repackage earnings, guidance, news and price information.
12. **Vendor lock-in:** proprietary IDs/taxonomies/delivery formats can become architecture.
13. **False precision:** many estimates do not imply independent information.
14. **Theme backfill leakage:** modern themes projected into historical companies create artificial persistence.
15. **LLM model drift:** machine-derived themes can change when model/version/prompts change.

## J. Build priority

**P0**
- Canonical PIT estimate/actual/coverage/identity/correction/source-receipt contracts.
- Source bake-off/trial protocol.
- PIT eligibility and deterministic normalization/revision engine design.
- Pre-registered validation plan.
- Prospective effective-dated theme-membership capture contract if a current owner accepts it.

**P1**
- Bounded research ingestion for approved trial data only.
- Consensus and analyst-detail ablation datasets.
- Deterministic revision/breadth/dispersion/staleness features.
- Shadow evidence artifacts attached to existing decision-time history.
- OOS validation and independence tests.

**P2**
- Dynamic theme extraction/classification after canonical PIT membership exists.
- Cross-source replication and richer analyst-skill/herding features.
- Research/operator inspection surfaces.

**Defer**
- Large proprietary theme graphs before baseline PIT membership and incremental value are proven.
- Recommendation/price-target families unless they add independent value beyond estimate revisions.

**Reject**
- Latest-only estimate feeds presented as historical PIT.
- Retroactively backfilled dynamic themes without evidence-time lineage.
- Opaque composite scores that erase independent evidence dimensions.
- Any implementation that gives a new data family direct portfolio/trading authority.

## K. Proposed implementation phases

### Phase 0 — acceptance and archaeology
Re-pin protected source, complete the exact Mastermind/Macro/Terminal/Research Vault census, identify existing data owners/adapters/contracts, and reconcile any adjacent plan. **No procurement or production write.**

### Phase 1 — source bake-off
Using approved trials or already licensed access, evaluate a fixed security/date/metric sample across candidates for PIT reconstructability, analyst-detail fidelity, corrections, identifiers, history, latency, delivery ergonomics, documentation, rights, and cost class. Produce a scored evidence matrix. **No purchase authority.**

### Phase 2 — canonical contract prototype
Implement research-only schemas and deterministic transformations behind fixtures/samples. Prove bitemporal reconstruction and correction lineage. **No production ingestion.**

### Phase 3 — research dataset and preregistered tests
Build a bounded research dataset, run leakage audits, consensus-vs-detail ablations, incremental tests, costs, factor controls, OOS and falsifiers. Publish receipts and reproducible results.

### Phase 4 — shadow integration
Only if promotion thresholds pass, attach namespaced evidence to existing decision-time history / Decision Snapshot-compatible research surfaces. No sizing, gating, execution, or trading effect.

### Phase 5 — production admission
Separate commission. Requires current source law, license/rights approval, production data ownership, monitoring, correction policy, security review, and explicit portfolio-authority decision. Passing research does not grant this phase.

## L. Exact implementation handoff

### Follow-on commission: PIT Analyst Revisions — Trial, Contract Prototype, and Validation

You are implementing a **research-only, non-production trial** of Mastermind’s point-in-time analyst-revision capability.

**Authority boundary**
- Do not purchase or license data.
- Do not deploy production ingestion.
- Do not modify live portfolio/trading behavior, sizing, gating, execution, or settlement.
- Do not grant a new source or evidence family decision authority.
- Do not bypass current Mastermind bootstrap, admission, source-custody, rights, or protected-procedure gates.
- Use only already licensed access or separately approved vendor trials.
- Treat any later procurement, production build, and production admission as separate gates/commissions.

**Required source recovery**
1. Pin current protected `mastermindx-market-intelligence/Mastermind` master.
2. Load current `docs/sol_skills/INDEX.md` and required companions from that same commit.
3. Resolve the actual current Mastermind, Macro, Terminal/charting, and Research Vault repositories/owners relevant to estimates and themes.
4. Census existing estimate/fundamental/theme adapters and adjacent plans before creating anything.

**Phase A — bake-off**
Evaluate approved candidate sources on the same fixed security/date/metric sample. Measure:
- PIT reconstructability;
- analyst-detail vs consensus capability;
- correction/vintage transparency;
- analyst/broker/security identity stability;
- fiscal-period mapping;
- coverage/history/latency;
- API/bulk ergonomics;
- rights and retention constraints;
- cost class;
- cross-source disagreement.

Deliver a source-evidence matrix and an unverified/vendor-confirmation register. Do not select a vendor merely from marketing claims.

**Phase B — canonical research contracts**
Prototype vendor-neutral research contracts for:
- security/entity identity;
- analyst/broker vintage identity;
- estimate observation/revision;
- coverage stop/resume;
- actual result;
- consensus snapshot;
- fiscal-period identity/version;
- source receipt/correction lineage.

The temporal envelope must explicitly separate `event_time`, `as_of`, `observed_at`, `available_at/known_at`, `ingested_at`, `effective_from/to`, and `correction_generation`.

**Phase C — deterministic engine**
Implement only research-scoped deterministic steps:
dedupe → correction/vintage selection → PIT eligibility → identity resolution → fiscal-period alignment → basis/unit/currency/split normalization → coverage eligibility → staleness → consensus/revision/breadth/dispersion → provenance/quality flags.

LLMs may classify/summarize already timestamped text or propose research hypotheses. They may not determine PIT eligibility, invent estimates, or repair numeric history without trace.

**Phase D — validation**
Pre-register and execute:
- PIT universe + delisting controls;
- market-clock/execution assumptions;
- factor/sector/country/size/liquidity controls;
- SUE/PEAD, price, options, guidance, news, fundamentals, flow/theme/macro controls;
- consensus-vs-detail ablations;
- revision magnitude/breadth/dispersion/staleness ablations;
- rolling OOS/walk-forward;
- multiple-testing control;
- transaction costs/turnover/capacity;
- missingness and coverage-event tests;
- cross-source replication where lawful;
- negative controls and falsifiers.

**Promotion output**
Return one of:
- `PROMOTE_TO_SHADOW_RESEARCH`
- `MORE_EVIDENCE_REQUIRED`
- `REJECT_DATA_FAMILY`

A promotion result authorizes only a later shadow-research commission. It does not authorize procurement, production deployment, or portfolio/trading effects.

## Unverified / needs vendor confirmation register

- Exact earliest analyst-detail history by region/metric/package for each commercial vendor.
- Whether historical exports preserve original observations versus retrospectively corrected values.
- Exact availability timestamp semantics and timezone/cutoff policy.
- Treatment of late-arriving estimates, stopped estimates, broker mergers, and analyst reassignment.
- Corporate-action, currency, unit, basis, and fiscal-period remapping policy.
- API/bulk delivery entitlements and retention/redistribution restrictions.
- Commercial cost class for Mastermind’s intended use; no price is asserted here.
- Whether any already licensed Mastermind/Macro estate access can satisfy the bake-off without new procurement.
- Full current identities and source pins for Macro, Terminal/charting, and Research Vault estates.

---

### Protected Mastermind evidence references

- `portfolio/held_risk.py`
- `tests/test_held_risk.py`
- `research/TREND_PERSISTENCE_PROTOCOL.md`
- `brain/signal_history.py`
- `brain/outcome_ledger.py`
- `docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md`
- `docs/superpowers/plans/2026-09-15-mastermind-portfolio-v3-s0-decision-snapshot.md`
- `research/competitive_intelligence/fiscal/2026-08-22/recon01/observations.jsonl`

All internal references above were evaluated against the protected source pin declared at the top of this report unless explicitly marked as an unverified follow-up.
