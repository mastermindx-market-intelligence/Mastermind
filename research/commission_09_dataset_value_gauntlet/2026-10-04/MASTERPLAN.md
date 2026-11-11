# MastermindX — Data Alpha Attribution & Dataset Value Gauntlet
## Complete hardened research commission 9

**Research date:** 2026-10-04  
**Status:** RESEARCH_ONLY / RECOMMENDATION / NO_PRODUCTION_EFFECT  
**Scope:** Dataset value, incremental evidence, decision improvement, experiment governance and a bounded later implementation plan.  
**Authority:** This document does not authorize procurement, production code, pipeline changes, portfolio/trading changes, new evidence authority, or a second control plane.

This is the full replacement recommendation, not merely an addendum to the uploaded report. Read the accompanying [audit](AUDIT_AND_RECENSUS.md), [detailed empirical protocol](VALIDATION_PROTOCOL.md), [source register](SOURCE_REGISTER.md), and [exact implementation commission](IMPLEMENTATION_COMMISSION_P0A.md). Current protected law always controls over this research proposal. Adjacent open PRs are evidence of work and ownership, not accepted law.

# A. Executive conclusion

## What Mastermind should build

Mastermind should build a **Dataset Value Gauntlet as a thin, use-specific research qualification layer over existing owners**. It should answer five distinct questions:

1. Could the intended consumer lawfully know the exact observation and its identity/correction generation at the required cutoff?
2. Is the source reliable and sufficiently covered for that use?
3. Does its information improve a frozen, credible prediction baseline, or meet a separately registered risk, event, reference-data or replacement objective?
4. Does the information change decisions usefully after feasible execution, risk constraints, stochastic model behavior and all relevant costs?
5. Is the resulting benefit worth the recurring and switching costs, operational complexity and rights burden?

The user-facing outcome is a decision-ready answer: **retain, qualify further, acquire a lawful sample, defer, reject a particular claim, retire a redundant use, or propose bounded promotion**, with inspectable reasons. The answer must identify exactly what has and has not been established. A vendor's attractive backtest, an isolated IC, or a large number of correlated features is not sufficient.

This is high-priority institutional research infrastructure because it protects every later data acquisition and evidence-family claim. But the P0 is **measurement and admission correctness**, not an expensive platform build. Macro already owns `dataset_registry.v1`, temporal profiles, a TrialLedger, a Strategy Lab façade and many quantitative primitives. Mastermind already has an active Portfolio V3 Snapshot implementation carrier. The original proposal would duplicate some of those owners and overstate the qualification of others. [C02–C08](SOURCE_REGISTER.md#c02), [P01](SOURCE_REGISTER.md#p01).

The intended flow is:

**Existing dataset identity → use-specific admissibility → descriptive QA → preregistered incremental evaluation → economic evaluation → prospective paired shadow evidence → separate owner-approved authority → monitoring and expiry.**

No stage implies the next. In particular, “dataset exists,” “data are healthy,” “predictive association exists,” “decisions improve,” and “live use is authorized” are different facts.

## What “worth having” means

Not all valuable data have return alpha. A source may improve downside forecasts, detect material events earlier, reduce false alerts, cover previously unobservable entities, replace an expensive incumbent without material loss, or supply essential identifiers. These claims need empirical tests but should not be forced into raw return IC. Conversely, an expensive source that adds no meaningful information or service benefit, is not consumed, or can be replicated with existing lawful data should not be retained because of sunk engineering cost.

Use a portfolio of **explicit claims**, not one opaque score:

- **Incremental predictive information:** baseline-plus-family outperforms baseline on its registered target.
- **Decision improvement:** paired policies improve a registered net objective while respecting risk constraints.
- **Risk/event utility:** better calibrated downside or event information at actionable operating points.
- **Replacement value:** acceptable noninferiority with lower total cost, better coverage, latency or reliability.
- **Supporting-data value:** measurable identity, observability or reference-data quality under the existing operational owner; no fabricated alpha vote.

The economic counterargument is important: governance can cost more than the data being governed. The minimum system must be cheap enough for free/internal sources, progressively stricter for irreversible expenditure or decision authority, and able to conclude **do not build the integration** before a large project starts.

# B. Current-state census

The [audit](AUDIT_AND_RECENSUS.md#3-current-state-census-what-exists-and-what-does-not-follow-from-it) provides the detailed capability table and scope limitations. The independently inspected source changes the architecture materially.

## Existing substrate to reuse

**Macro Data OS:** `config/dataset_registry.yml` and `lib/dataos/registry.py` already define dataset identity, owner, producer, grain, schema, temporal profile, source status, licensing and static dependency edges. The proposed new registry in the original report is therefore not a missing component. [C04–C05](SOURCE_REGISTER.md#c04).

**Temporal owner:** `lib/dataos/temporal.py` already distinguishes source/derived/intelligence profiles, refuses naive times and unsupported PIT reads, and separates recomputation from served replay. Source-specific adoption and evidence quality remain to be demonstrated. The module is a vocabulary/enforcement seam, not proof that every historical dataset is safe. [C06–C07](SOURCE_REGISTER.md#c06).

**Research and trial owners:** `engine/trial_ledger.py` already records generated configurations and family budgets; `engine/lab.py` already provides thin research orchestration. A gauntlet should extend their contracts and use their outputs instead of copying their mathematics or creating another ledger. Stronger admission requirements need explicit integrity qualification. [C03](SOURCE_REGISTER.md#c03), [C08](SOURCE_REGISTER.md#c08).

**Quantitative primitives:** rank IC, HAC, multiple-testing tools, forecast scoring, residualization, cost/impact and family comparisons exist in `engine/validation.py`. Three inspected expressions failed discriminating synthetic invariants; other interface and inference risks were found. The correct state is substantial reusable code with **use-specific qualification gaps**, not a blanket institutional-grade PASS. [C02](SOURCE_REGISTER.md#c02), [synthetic receipts](SYNTHETIC_AUDIT_RECEIPT.json).

**Portfolio evidence:** current source excerpts establish an earnings-expectation lane, but not a mature historical estimates-vintage panel. PR #673 has active Snapshot implementation on its draft branch; the audited protected paths do not establish that implementation as available to production consumers. [C10](SOURCE_REGISTER.md#c10), [P01](SOURCE_REGISTER.md#p01).

## Important constraints newly sharpened

The current Trend C1 preregistration explicitly treats old panel dates as exposed and requires future confirmation. It also documents a sector snapshot whose labels are current rather than era-correct. These are binding reasons not to claim untouched historical tests or historical sector-neutrality merely because membership is PIT-aware. C1's reported earlier incremental-model null is useful precedent, not a fresh result produced by this commission. [C09](SOURCE_REGISTER.md#c09).

The uploaded report's broader price/fundamental/options/news/flow inventory, its signal/outcome histories, and its July static-census date remain relevant leads. This pass did not independently certify their current materialized history or production execution. A rejected compound inspection was not bypassed, and the missing proof remains visible. No new count or “all feeds live” claim is supplied.

## Duplication and integration adjudication

Commission 8's observability research, PR #1221's temporal research, PR #673's Snapshot work and the Trend family are adjacent owners/dependencies, not templates to copy into Commission 9. Issuer Inflection PR #1183 is an adjacent consumer. A bounded search found no existing carrier with the exact Dataset Value Gauntlet title; that does not waive later exact-path collision checks. [P01–P04](SOURCE_REGISTER.md#p01).

The narrow missing capability is **a reproducible join between a dataset-use claim, admissible source receipts, a fully accounted experiment, a credible baseline, costs, and a nonbinding qualification decision**. It is not a new allocator, scheduler, model registry service, lakehouse, global catalog, general-purpose causal inference engine or portfolio state store.

# C. State-of-the-art research and architectural implications

The methodological literature supports complementary safeguards, not a ritual in which several named statistics jointly certify alpha.

**Dependence-aware inference.** HAC estimators address serial dependence under their assumptions. Overlapping labels, common date shocks and sector-level features reduce effective information relative to raw stock-row counts. Short-sample behavior and the actual sampling process still matter. The gauntlet should validate size and power on synthetic processes resembling the intended cohort structure, use common-date/block resampling for paired comparisons, and abstain when inference is not supportable. [W01](SOURCE_REGISTER.md#w01).

**Incrementality rather than standalone predictability.** Comparing a baseline with an augmented model is a different question from testing a univariate feature. Clark–West is relevant to appropriate nested forecast settings; arbitrary nonlinear models and policy decisions require a comparison design matching their estimand rather than automatic application of that statistic. [W02](SOURCE_REGISTER.md#w02).

**Multiple testing.** Ordinary BH needs defensible dependence conditions. More conservative dependence-robust adjustments or valid joint resampling may be necessary. All candidate transformations, horizons, interactions, model/prompt variants and outcome-conditioned missingness investigations belong to the research accounting. Promotion should normally have a small, frozen confirmatory family, not a sprawling retrospective search. [W03](SOURCE_REGISTER.md#w03).

**Forecast quality.** Proper scores evaluate probability/distribution forecasts. A model can discriminate well and remain poorly calibrated; a rare-event detector's operating value also depends on false-alarm burden, event prevalence and action lead time. Proper score improvement is not itself a portfolio improvement claim. [W04](SOURCE_REGISTER.md#w04).

**Selection bias.** DSR and PBO expose different aspects of strategy selection. RC/SPA compares a candidate family against a benchmark. None reconstructs missing historical data, corrects unlicensed access, makes costs realistic, or turns a selected result into an identified causal effect. Use them where their assumptions match the design, report their limits, and do not multiply them into an opaque confidence score. [W05–W07](SOURCE_REGISTER.md#w05).

**Data-family attribution.** Grouped additive importance methods such as SAGE can help describe predictive contributions and interactions. They are a later diagnostic because correlated data, the imputation distribution and interactions affect allocation of value. A feature importance number is not the economic price of a data subscription. [W08](SOURCE_REGISTER.md#w08).

**Decision counterfactuals.** Historical deterministic portfolio choices do not reveal outcomes for all unchosen actions. Off-policy estimators need overlap/logging and identification assumptions. A paired shadow simulator provides controlled evidence about the specified policies and simulator, not a randomized causal estimate of live market profits. [W09](SOURCE_REGISTER.md#w09).

**Sequential governance.** Valid confidence sequences may eventually support repeated evaluation, but their assumptions and stopping rules must be built into the experiment. P0 should use fixed preregistered confirmation cohorts and one outcome-bearing read, not retrospectively invoke sequential terminology to excuse peeking. [W10](SOURCE_REGISTER.md#w10).

**LLM temporal contamination.** Fixing today's prompt and model version does not make a historical forecast historically knowable. The model may already contain future information. Historical LLM-assisted analyses must be labelled current-rule retrospective research unless contemporaneous served artifacts and the relevant model/data knowledge boundary are proven. Prospective evaluation is the preferred route for modern LLM decision contribution. [W11](SOURCE_REGISTER.md#w11).

## Alternatives considered

**Build a separate evaluation platform:** clean conceptual slate, but duplicates owners, splits trial memory and adds custody/maintenance burden. Reject for P0.

**Use existing scripts unchanged:** cheapest initial action, but the audit demonstrated measurement and exposure problems, and scripts do not automatically answer dataset-use or closed-loop questions. Reject as a promotion path; retain qualified primitives.

**Buy institutional data first and prove value later:** may unlock scarce history, but incurs rights and integration cost before the relevant baseline or test is credible. Defer procurement; start with documentation and a later lawful sample gate.

**Thin owner-native qualification profile:** preferred. The falsifier is that existing owners cannot support durable source/experiment integrity without unsafe live changes. In that event stop the bounded integration, obtain an owner decision, and do not quietly create a competing store.

# D. Source landscape

Cost classes below are relative planning categories, **not quotes**: `sunk` means existing access, `$` low incremental direct access cost, `$$–$$$` commercial usage/licensing dependent, `$$$–$$$$` potentially substantial institutional scope. Every class excludes unknown implementation and legal cost. Coverage years are publisher claims for named products, not proof of the specific PIT generations Mastermind can license.

| Source | Coverage | History | Latency | PIT quality | Corrections | Rights | Cost class | Best use |
|---|---|---|---|---|---|---|---|---|
| Existing owner-native artifacts | Current Mastermind/Macro families and research outputs | Highly source-specific; some new histories are short | Existing collection cadence, not remeasured here | Mixed; registry/profile is not row-level proof | Owner-specific, sometimes unrecorded adjustment vintages | Existing entitlement and intended use must still match | sunk / $ | First qualification fixtures and credible incumbent baselines; no procurement assumption. [C03–C08](SOURCE_REGISTER.md#c03) |
| SEC EDGAR APIs | Filings, submissions and XBRL facts | Filing/accession and form dependent | Dissemination driven; typical API timings are not end-to-end SLA | Strong filing lineage when exact availability is proven | Amendments/later filings and aggregation revisions need lineage | Public access with fair-access obligations; intended downstream use reviewed | $ | Filing/fundamental/event truth and clock anchors. [W12](SOURCE_REGISTER.md#w12) |
| FRED / ALFRED | Economic series and vintages | Series dependent | Release/vintage cadence | Strong date-vintage support; not universal intraday receipt proof | Explicit vintage intervals | API/source-series terms may differ | $ | Macro vintage controls, release-sensitive history. [W13](SOURCE_REGISTER.md#w13) |
| NYSE Daily TAQ | US consolidated trades, quotes, NBBO, administrative data | Publisher states 1993 onward | Prior-day historical delivery | Market-event history; capture/use-time qualification still needed | Technical/sample replay required | Exchange commercial agreement | $$$ | Execution/liquidity benchmark when daily data cannot answer the hypothesis. [W14](SOURCE_REGISTER.md#w14) |
| Nasdaq Historical TotalView-ITCH | Nasdaq venue order/trade events | Publisher states 2014 onward | T+1 logs | Event chronology, venue-specific | Verify breaks, corrections and reconstruction | Exchange commercial agreement | $$$ | Venue-specific microstructure and order-book research, not blanket all-market coverage. [W15](SOURCE_REGISTER.md#w15) |
| FactSet Estimates | Consensus, contributor/detail, actuals/guidance per package | Published global history from 1999; some European history from 1997 | Feed/API/package dependent | PIT capability plausible; record-level proof outstanding | Original generations, corrections and fiscal-period treatment require sample | Contributor and storage/derived/model/display rights unknown | $$$–$$$$ | Estimates/revisions candidate, not preselected winner. [W16](SOURCE_REGISTER.md#w16) |
| LSEG I/B/E/S / quantitative products | Estimates/consensus and PIT-oriented product options | Exact package/history not qualified here | Package/SLA dependent | Published PIT offering, no inspected Mastermind sample | Package-specific | Intended broker/model/retention rights unknown | $$$–$$$$ | Competing estimates candidate under identical experiments. [W17](SOURCE_REGISTER.md#w17) |
| S&P Capital IQ Estimates | Broad company estimates and actuals | Publisher states history from 1996 | API/feed/cloud/desktop options; exact SLA unproven | Publisher describes timestamped PIT | Correction generations must be demonstrated | Commercial and derived-use terms unknown | $$$–$$$$ | Competing estimates candidate, including coverage and period comparability. [W18](SOURCE_REGISTER.md#w18) |
| Databento market/reference products | Venue/schema dependent market and reference data | Dataset-specific | Historical/live services | Rich clock fields, with documented exceptions; PIT reference option must be selected | Source corrections, flags, definition and adjustment versions matter | Vendor plus underlying exchange/reference terms | $$–$$$ | Focused timestamp, liquidity and execution-cost qualification before large procurement. [W19–W20](SOURCE_REGISTER.md#w19) |

Public filings and macro vintages are not substitutes for an analyst forecast history. They can support low-cost baselines or other claims, not a fabricated reconstruction of consensus. Likewise, the availability of tick data does not imply a need to buy it.

## Mandatory commercial sample questions

A later sample request must specify a frozen representative slice: ordinary and stressed periods; active and delisted securities; ticker changes and mergers; originally published and corrected records; stale/missing contributors; fiscal-period changes; timezone/daylight-saving boundaries; delivery outages; and records whose publication and vendor receipt differ. Obtain schema definitions, coverage denominator, archive retention rules, bulk/API mechanics, latency distributions and corrections rather than screenshots of a marketing dashboard.

Rights review must separately cover storage, post-termination retention, internal display, model inference, model training, embeddings/retrieval, derived features, redistributing outputs, and raw-data redistribution. A model-use permission is not automatically a training or external-display permission. Commercial claims remain `SAMPLE_REQUIRED` or `RIGHTS_UNKNOWN` until the exact use is evidenced. No vendor contact or spend occurred in this commission.

# E. Minimum canonical data model and temporal semantics

## Design constraint: projections, not new authoritative stores

The names below are **proposed research contracts**, not implemented schemas or permission to mint a second source owner. First resolve each existing field/receipt; extend that owner minimally or expose a read-side projection. The registry's existing `dataset_id` is the join key. Qualification is keyed at minimum by:

`dataset_id + dataset_version + use_case + universe_version + horizon/label + baseline_version + policy_version_if_any + rights_scope + evaluation_generation`.

A single dataset may be qualified for a weekly descriptive use and unqualified for intraday prediction. Its source status `PRODUCED` is independent of its scientific qualification and independent again of live authority.

## 1. Dataset-use profile

Required information:

- existing dataset ID/version, native registry reference and canonical owner;
- provider/product/entitlement reference and source generation;
- purpose: predictive, downside, event, replacement or supporting-data;
- evidence family and lineage/independence-family reference, without equating correlation with causal identity;
- entity grain and identifier mapping version;
- expected universe/coverage denominator version, geography, cadence, latency and freshness limits;
- allowed temporal/replay mode, correction and missingness policies;
- right/use dimensions and expiry; unknown is not false or permission;
- costs in declared currency/time basis, marginal versus shared allocation, switching/termination conditions;
- linked experiments, qualification state, blockers, expiry/retest and authorized review owner.

Do not duplicate source descriptions into a separately mutable authoritative catalog. Retain references and bounded projections with observation times.

## 2. Admissibility/source receipt projection

The receipt must bind exact bytes or owner-native content identities to the proposed use. Minimum fields include observation/source ID; record key; payload/version/hash reference; source receipt; identity/taxonomy/price-adjustment receipt references; original/corrected/superseded status; quality and missing reasons; and the following clock semantics:

| Clock | Required meaning |
|---|---|
| `event_time` | Underlying event instant, where meaningful; a scheduled future event can be known before it occurs. |
| `as_of` or period interval | Period the measurement or forecast describes; never automatically its publication time. |
| `source_observed_at` | Source's observation of the record/event, when documented. |
| `provider_observed_at` | Provider receipt/capture time, with provenance and synthetic/backfill flags. |
| `available_at` | Defensible availability of this exact generation through the declared delivery/entitlement path. |
| `system_observed_at` | Mastermind's recorded first observation on its actual path. |
| `ingested_at` | Durable ingestion time; not a backdated proxy for initial publication. |
| `effective_from` / `effective_to` | Validity interval for facts/mappings/states, separately from when that interval became known. |
| `correction_generation` | Owner-native version/lineage of revisions; no rewrite of older knowledge. |
| `computed_at` / `served_at` | Existing derived/replay clocks, with code/model and input-cutoff references. |

An ambiguous single `observed_at` must carry its observer identity rather than combine source, provider and system clocks. Not every source must supply every clock; absent fields need an explicit reason and a claim ceiling. Timezone, precision, lower/upper availability bounds, clock provenance and uncertainty are part of the receipt. A decision cutoff that overlaps an unresolved availability interval is not admitted merely because its lower bound is earlier.

**Do not overwrite the existing Data OS definition of `known_at`.** Preserve the source owner's field and apply a named admissibility rule in the experiment. [C06](SOURCE_REGISTER.md#c06).

Three modes must remain distinguishable:

- **SOURCE_PIT_RECONSTRUCTION:** exact historical source generations, valid mappings and delivery semantics establish what could have been available under a specified lawful information set. A newly obtained archive does not establish actual past Mastermind possession or entitlement. Where that cannot meet the commission's historical-possession requirement, the result is methodological research only or prospective-only, not historical Mastermind alpha.
- **ACTUAL_SYSTEM_REPLAY:** contemporaneous receipts and served/decision artifacts establish what the actual system consumed. Input hashes alone with today's code are recomputation, not replay. Model, prompt, policy, state and output versions are required for decision claims.
- **PROSPECTIVE:** source and system receipts are captured before each decision, predictions are committed before labels mature, and later outcomes are evaluated under the frozen spec.

A correction can change the effective fact for an old period while having a new availability time. The historical cutoff selects the then-admissible generation, not today's latest row. Effective-dated identifiers and sector mappings themselves also need a knowledge cutoff. A ticker is an alias, not a permanent security identity. Price adjustment vintage and executable raw-price basis must be represented where they affect the claimed feature, liquidity, shares or returns. [C05](SOURCE_REGISTER.md#c05).

## 3. Experiment specification and accounting references

An immutable specification contains the hypothesis/estimand; use scope; eligible universe and cases; feature definitions and units; baseline/control fields and their PIT qualifications; target definitions and outcome vintage/maturity; decision/execution times; split and purge rules; untouched cohort identity and exposure certificate; model/calibration fitting procedure; primary metric and direction; economic threshold; risk/noninferiority margins; power/MDE plan; missingness/failure treatment; cost model; multiplicity family and full trial budget; and stopping/expiry rules.

It also pins data/identity/code/model/prompt/feature/procedure hashes, seed/repetition design where relevant, approval/freeze time, and references the **existing TrialLedger**. Distinct configuration count, execution attempts and outcome exposures are separate accounting dimensions. Failure does not erase an attempt; identical config reruns need not increase distinct-config count but must preserve fresh data/model exposure and result generation. A new experiment generation does not reset exposure to the same outcomes.

## 4. Result bundle

Every metric carries its name, definition/version, units, favorable direction, value, interval, confidence construction, independent cohort count, row/date/event counts, sample-manifest hash, missing/failure exclusions, horizon, costs, multiplicity result and qualification state. Preserve unrounded machine values; round only display copies.

The bundle references the frozen specification, actual trial/attempt, source/feature receipts, predictions and label maturation receipts, primitive qualification, code/environment, all failures and artifact hashes. Store paired date-level differentials where permitted so an independent reader can verify summary statistics. Privacy/licensing may require controlled owner-native storage rather than embedding raw records in GitHub.

## 5. Nonbinding scorecard

Expose independent dimensions: temporal integrity, identity/price basis, rights, coverage, source operability, incremental information, calibration, event/downside value, robustness, economic usability, decision uplift, substitution value, expiry and unresolved blockers. A dimension may be `PASS`, `FAIL`, `UNKNOWN`, `PARTIAL`, `NOT_TESTED` or `NOT_APPLICABLE` with a reason; N/A must not bypass a requirement for the registered use.

The scorecard contains no universal `dataset_score`. It records a proposed advancement/disposition and evidence references. Only the existing authorized owner can grant live use through its own process; a derived scorecard cannot become an authority state machine.

# F. Derived intelligence and deterministic versus LLM work

## Before any outcome access

Deterministically calculate source receipt completeness; duplicate/conflicting records; timezone/precision errors; generation ordering; entity mapping validity; price/volume basis consistency; cadence/freshness/availability distributions; missingness by registered universe, region, size/liquidity and source category; correction frequency/magnitude/lag; and consumer-read availability where established. Coverage must have a versioned expected denominator. A failed probe is `UNKNOWN/COULD_NOT_LOOK`, not healthy or absent.

Latency needs more than one number: event-to-publication, publication-to-provider, provider-to-system, and system-to-usable-feature. Negative or surprising durations require explanation, not automatic clamping. A forecast about a future event legitimately has availability before event time.

## After temporal and experiment admission

Calculate transparent feature components such as level, change, economically meaningful acceleration, expectation surprise, rank, sector-relative rank where valid, breadth, dispersion, disagreement, novelty versus already-known news, and age. For estimates, preserve revision magnitude/direction/breadth, analyst participation, fiscal target, dispersion and time since revision rather than a single “analyst alpha” scalar.

Return-conditioned missingness or availability models are legitimate diagnostics but are outcome-bearing experiments. They must be preregistered or logged as exploration; they are not free descriptive QA. Their purpose is to distinguish content value from a source merely covering larger or more liquid companies.

Prediction and economic derivatives include raw and common-support residual/rank association, baseline augmentation, quantile monotonicity, proper score changes, event matching/lead time, downside discrimination/severity, horizon curves, preregistered regime slices, turnover/exposure/cost differences, and paired policy deltas. Exact definitions are in the [validation protocol](VALIDATION_PROTOCOL.md).

## Deterministic work

Deterministic implementations own timestamps and admission, identity and correction joins, normalization, labels/maturity, splits, ranks, residuals, forecasts' evaluation, calibration metrics, multiplicity, costs, sample counts, paired state transitions, result hashing and gate predicates. The existing owner must be qualified for the exact operation; the word “deterministic” alone is not proof of correctness.

## Cheap LLM work

Small models may classify documentation into a reviewed source profile, draft vendor-question checklists, map prose to pre-existing fields, summarize a frozen scorecard and explain already computed differences. They must carry source references, distinguish unknown from inferred values, and avoid sending restricted material to unapproved providers.

## Frontier LLM work

Frontier models may challenge the hypothesis mechanism, identify omitted baselines or duplicate evidence paths, propose falsifiers before outcome access, review whether a decision comparison actually isolates a family, and synthesize conflicting qualified results. They should be used selectively for ambiguity, not replace arithmetic or routine data validation.

Neither model class may assign historical availability, invent old vintages, backfill missing outcomes as fact, select a post-holdout winner, silently weaken a control, set promotion from prose, or grant allocation/execution authority. Modern-model historical analyses require the temporal qualification described in section E.

# G. Mastermind integration map

| Producer | Existing canonical owner / artifact seam | Evidence role | Consumer and boundary |
|---|---|---|---|
| Source collector | Source store plus Data OS identity/temporal profile | Raw observations, not automatically evidence | Existing deterministic feature owner; no rewrite solely for C9 |
| Data quality / observability owner | Owner-native health/coverage/receipt projection, coordinated with C8 | Validity and availability precondition, not another alpha vote | Gauntlet admission and existing consumer degradation rules |
| Feature computation | Existing feature artifacts with source and transform references | Registered family with explicit lineage | Existing research/Strategy Lab seam |
| Research adapter | Existing Lab and qualified `engine/validation.py` primitives | Research result only | Frozen experiment result/scorecard |
| Trial generation and evaluation | Existing TrialLedger, strengthened through its owner | Configuration, attempt and exposure evidence | Multiplicity and holdout admission; no second store |
| Prediction/outcome owners | Existing canonical histories, only after current qualification | Baseline/prediction/matured-outcome evidence | Family evaluation; do not assume attachment-reported owners are already qualified |
| Portfolio V3 S0 | Existing `mastermind.portfolio_decision_snapshot.v1` and source-receipt direction, after accepted implementation | Actual decision-time information/state provenance | Later paired shadow experiment; no replacement snapshot |
| Existing shadow/portfolio simulation owner | Separately versioned baseline and augmented shadow trajectories | Simulated decision uplift | Research reviewer, never orders or live account mutation |
| Existing portfolio/risk/authority owners | Existing approved admission and rollback process | Bounded accepted evidence use | Production only after a distinct authorization and proof gate |
| Terminal/research display | Read-only projection of scorecard and evidence links | Explanation and traceability | Must show unavailable/uncertain/expired states; no new gate authority |

Source truth remains in its current repository/data owner. GitHub owns this research and implementation evidence. The gauntlet is neither Executive lifecycle authority nor a portfolio controller. A dataset profile or result file is not a new program/job registry.

# H. Empirical validation program

The [detailed protocol](VALIDATION_PROTOCOL.md) is part of this report and contains exact estimands, samples, tests, costs, cohort logic and promotion rules. Its key commitments are:

**Frozen credible baseline.** Control for PIT-known momentum/reversal, sector, available theme exposure, beta, volatility/downside volatility, size/liquidity, fundamentals, existing earnings expectations, and already-known events/news, plus declared regime context. Maintain a historically admissible core baseline and an actual contemporary deployment baseline when they differ. A missing historical news or theme field limits the claim; it is not filled with today's reconstructed knowledge. Compare candidate and baseline on identical cases, while separately measuring full-universe operational utility with the actual missing-input policy.

**Complementary tests.** Measure raw Spearman IC; correctly named residual/partial-rank diagnostics; genuinely OOS baseline-versus-augmented prediction; and complete family ablation. Add availability-only and cheaper-substitute comparisons. A nonlinear interaction claim may be legitimate even with weak raw IC, but must be preregistered and pay its own trial budget.

**Targets and horizons.** Choose a primary label/horizon before analysis. Secondary horizon decay, event detection, rank value, drawdown and calibration are diagnostic unless included in the confirmatory family. Specify executable entry, exit, label maturity, delisting/corporate-action treatment, target vintage and benchmark. Never confuse entry adverse excursion with peak-to-trough drawdown.

**Independence and exposure.** Purge by actual overlapping label/availability intervals and use past-only training for deployment claims. Use date/cohort or group-date dependence units rather than treating every name-row as independent. The new generation/branch/model name does not make an exposed historical sample unseen. Preserve the explicit C1 restrictions and no-rerun law. [C09](SOURCE_REGISTER.md#c09).

**Economic value and power.** Define minimum economically meaningful improvement `delta_min` independently of the detectable effect under the attainable sample size. A confidence interval entirely below the required economic hurdle supports futility; an interval spanning it is insufficient evidence, not necessarily no value. The build-versus-wait-versus-stop decision also considers prospective evidence cost.

**Decision value.** Separate local same-state ablation, retrained-model contribution, closed-loop policy uplift and provider substitution. For continuous shadow policies the arms share an initial state and external environment, not forced identical holdings every subsequent day. Mask every candidate descendant and preserve identical noncandidate information, procedural budgets and risk constraints. Report actual simulated state/decision differences and all failures, not just aggregate return.

**Stochastic reasoning.** Use paired, independently archived repetitions when the policy is stochastic, including prompt/model version and order/latency controls. Do not claim identical outputs from a seed alone. Estimate uncertainty of the mean paired effect and operational risk; an effect smaller than one-run variance is not automatically zero, and one lucky run is not evidence.

**Natural-time proof.** Prospective receipt capture and fully matured independent cohorts are necessary for the strongest decision-evidence claim. Calendar waiting cannot be compressed by reusing old outcomes or treating overlapping name-rows as fresh trials. No such live/prospective performance was produced in this research commission.

# I. Risks, failure modes and kill criteria

## Fatal validity failures

Historical information that cannot be shown knowable at the required cutoff invalidates that historical claim. Revised values without recoverable original generations cannot support original-vintage research. Unqualified identifiers, current-era taxonomy, missing price adjustment vintage, bar-start access to final bar values, future-trained LLM knowledge, and noncausal benchmarks can each create false performance. Rights failure rejects the intended use even if statistics are excellent.

Invalid source generations should be quarantined or restricted to a narrower lawful use. A lack of historical proof may leave prospective research possible; it does not justify silently weakening the claim.

## Correlated information and hidden duplication

A price trend, sector story, ETF-flow feature, options narrative and analyst upgrade can share a catalyst or source. Independence is not established by different column names or providers. Retain source/family lineage, common-information controls and full descendant ablations. Do not demand zero correlation as a universal rule: incremental information can be useful despite correlation, while a weak linear correlation does not prove causal independence.

## Selection, missingness and coverage

Source presence may identify large, liquid, surviving or heavily followed names. Complete-case testing alone can produce a result that disappears across the deployment universe. Report selection into the sample, missed events, unmapped/delisted cases and availability-only predictors. Keep a source missingness state rather than imputing “neutral.” Match candidate and baseline support for statistical comparisons, then report operational coverage losses separately.

## False precision and implementation fiction

Nanosecond storage precision does not guarantee accurate availability. A daily close is not an executable fill merely because a model emits a target weight. Unknown ADV is not free liquidity; an unpriced short borrow is not zero funding cost; a delisted name carried at its last quote is not a proven economic terminal value. Risk/cost assumptions need source and sensitivity ranges, not presentation confidence.

## Operational and contractual drift

Changing vendor methodology, correction behavior, rights, coverage, IDs, model/prompt versions or consumer dependencies can invalidate a qualification. Expiry and bounded requalification belong to the profile. A source outage must flow to the existing consumer's degradation rules; C9 cannot invent a universal “pause trading” policy. Preserve history and record revoked use without erasing prior evidence.

## Hard dispositions, scoped to the claim

| Condition | Disposition |
|---|---|
| Required source availability, identity or correction lineage cannot be established | Reject the historical claim; prospective-only or narrower use may remain |
| Intended storage/model/display/retention rights are absent or unknown | Block that use until qualified; no source-value statistic overrides rights |
| Evaluation used exposed outcomes as untouched confirmation | Invalidate confirmation and record exposure; new future evidence required |
| Primitive or sample alignment is unqualified | No promotion statistic; owner repair/qualification or an explicit blocked result |
| Incremental effect's valid upper bound is below `delta_min` after realistic costs | Kill/defer the economic use; do not buy/build on that claim |
| Interval spans useful and useless effects with insufficient independent cohorts | Inconclusive; compare value of more evidence against its cost |
| Candidate merely duplicates an existing family under the registered tests | Reject extra independent-evidence status; retain only separately demonstrated service/substitution value |
| Apparent value is explained by availability rather than content | Reject the original content claim; any coverage hypothesis is separately registered |
| Improvement is concentrated in an unregistered regime/episode and does not reproduce | Kill the general claim; treat the slice as exploration, not confirmation |
| Net utility fails registered risk/noninferiority constraints | No promotion even with higher headline return |
| Delays, missingness, turnover, borrow or impact remove economic value | Kill the intended tradable use, not automatically every descriptive use |
| Prospective paired policy evidence is insufficient or negative | No decision-evidence promotion |
| A cheaper lawful source is noninferior for the intended use | Prefer substitution subject to switching/continuity proof |
| No consumer uses the data and no justified near-term requirement exists | Review retention/retirement and contractual obligations; sunk cost is not value |

The scorecard should record reject, quarantine, defer, inconclusive and expiry distinctly. “No significant result” is not synonymous with a statistically demonstrated absence of worthwhile value.

# J. Build priority

## P0 — prevent invalid evidence and duplicated infrastructure

P0A should establish owner-native dataset-use/admission/result projections, a truthful nonbinding scorecard, trial/exposure integrity requirements, explicit replay modes and primitive qualification, demonstrated only with synthetic fixtures. It should consume the existing registry and temporal/ledger/Lab owners and expose unresolved dependencies. It must not build a general data-health service or touch live authority.

P0B should run a small, pre-admitted existing-data evaluation only after P0A is accepted. Use lawful data and untouched or honestly exploratory cohorts. Demonstrate a useful candidate if supported, a redundant/negative-control case, and a temporally unqualified case; do not require a positive alpha result as an acceptance condition.

## P1 — candidate samples and prospective decision evidence

Evaluate lawful external samples against qualified internal/cheap baselines. Historical analyst revisions are a plausible candidate but no preferred vendor or expected effect is established. After the canonical Snapshot and shadow consumer path are protected and qualified, conduct prospective paired decision experiments. Record true natural-time maturity and failures.

## P2 — deeper economics and attribution

Provider substitution, source-switch stress tests, calibrated capacity and implementation costs, interaction-aware family attribution, decision decomposition, evidence-decay monitoring, and optional qualified sequential designs. Build only when simpler experiments expose a concrete need.

## Defer

Fine-grained historical subtheme-neutral claims without canonical effective-dated identity; strong individual-stock institutional-flow claims without adequate history; expensive tick/order-book procurement without a resolution-specific hypothesis; causal/off-policy evaluation without identification/support; large stochastic LLM decision fan-outs without a credible prospective information boundary.

## Reject

A new dataset registry or TrialLedger, a second temporal warehouse or Snapshot, a competing allocator/outcome/control plane, a universal opaque alpha score, automatic advancement from p-values/IC/DSR or vendor backtests, all-source historical reconstruction using today's corrected state, and any change of live authority caused merely by publishing this report.

# K. Sequenced implementation recommendation

| Phase | Owner and bounded output | Admission dependency | Exit proof | Not authorized |
|---|---|---|---|---|
| G0 — source/ownership refresh | Later implementer pins then-current Mastermind/Macro/Terminal and reconciles exact active paths; consumes this packet | Protected bootstrap and collision census | Immutable ownership/reuse map and changed-path scope | Taking over adjacent branches, opening outcomes to stay busy |
| P0A-1 — use/admissibility projection | Existing Data OS + research owners; references instead of duplicate metadata | G0; profile semantics accepted | Synthetic records distinguish valid, ambiguous, corrected, unknown rights, wrong identity and future availability | New global registry or raw-store rewrite |
| P0A-2 — primitive/trial qualification | Existing validation/TrialLedger owners; qualification manifest and fail-closed research wrapper | P0A-1 | Counterexamples preserved, unqualified paths blocked, durable attempt/exposure behavior proven | Claiming a full suite passed from three examples; changing live policy |
| P0A-3 — nonbinding end-to-end fixture | Existing Lab/read-only research consumer produces frozen result and multi-axis scorecard | Qualified synthetic path | A clean example and adverse examples reach the real research read seam; zero production authority | Market-outcome tests or source promotion |
| P0B — existing-data proof | Existing research owners | Accepted P0A; actual rights/PIT/sample/holdout certificate; primitive qualification | All trials and losses retained; common-support incremental results; cost/coverage and inconclusive/kill paths | Reopening frozen Trend holdouts or optimizing demos to win |
| P1A — external sample competition | Existing source/procurement/research owners | Explicit sample authorization and rights; same frozen experiments | Comparable coverage/clock/correction/cost scorecards and acquire/defer/reject recommendation | Paid integration or automatic vendor selection |
| P1B — prospective shadow decisions | Canonical Snapshot and existing shadow/portfolio owners | Protected qualified read path and accepted prospective protocol | Separate paired trajectories; mature-cohort net effect and guardrails; reproducible artifacts | Live orders, simulated fills called actual fills, replaced Snapshot |
| P2 — economic optimization and monitoring | Existing owners | Demonstrated need from P0/P1 | Noninferiority/substitution, tail/capacity and expiry evidence | Research scores as live authority |
| Separate production admission | Existing authorized portfolio/data owners | Accepted evidence, lawful rights, operability, bounded rollback and correlation treatment | Actual consumer/release proof required by those owners | Automatic admission from this commission |

### Critical dependency ordering

Outcome-blind source and measurement work can run while Snapshot implementation remains incomplete. Snapshot incompleteness does not justify a substitute snapshot. Conversely, the absence of a Snapshot does not block basic source-quality and feature-level research once their own gates are met. Rights and identity repairs can proceed independently of model selection. Exact empirical work must wait for its own data and holdout gates, not merely for an idle worker.

### Rollout and migration

Adopt existing dataset IDs and append qualification references; preserve source `PRODUCED/PROPOSED/RETIRED` meanings. Read legacy artifacts through explicit compatibility mappings, recording unknown fields instead of inventing them. Add research-only fail-closed admission without altering production consumers. Any necessary owner-side primitive repair gets its own collision-resolved, regression-proven change and current acceptance. Retain old result generations, mark invalidated results with reasons, and requalify rather than silently rewriting a past conclusion.

### Resources and budget

No reliable organization-wide engineering cost, data quote, deployable capital or experiment sample count was established here. Do not invent a schedule, return target or procurement budget. The later owner must size P0A by its finite negative-test matrix, then estimate P0B's required independent cohorts and monetary threshold before allocating broad research capacity. Use small deterministic workloads first; frontier-model reviews are reserved for genuine inference/architecture ambiguity.

# L. Exact implementation handoff

The full bounded commission is [IMPLEMENTATION_COMMISSION_P0A.md](IMPLEMENTATION_COMMISSION_P0A.md). It is part of this report and is intended to be copied in full only after the research is accepted.

Its outcome is **the smallest production-inert owner-native qualification path demonstrated on synthetic fixtures**, not the entire later dataset procurement/shadow/production program. It expressly prohibits market-outcome access, repeat holdout use, vendor spend, live behavior changes, new registries/ledgers/Snapshots, and automatic evidence authority. It requires current source/ownership reconciliation, named negative proofs, honest qualification of existing primitives, and a durable read-side scorecard.

The implementation commission has **not been executed** in this research run. Completion of this report does not mean that P0A, P0B, a live gauntlet, an external dataset's value, or prospective decision uplift has been proven.
