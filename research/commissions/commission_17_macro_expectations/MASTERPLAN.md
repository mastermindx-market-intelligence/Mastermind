# Commission 17 — Macro Expectations, Surprises & Market-Implied Distributions

## Hardened masterplan · revision 2 · 4 October 2026

**Disposition:** completed research and architecture recommendation. Proposed implementation remains **SPEC_ONLY**. This document grants no data purchase, production change, regime retuning, portfolio action, or new source authority.

**Recommendation:** extend the existing Macro Release Intelligence (MRI) and Rates & Inflation Command (RIC) owners with typed, point-in-time expectation evidence. Preserve the existing macro/regime engine and its downstream authority. The highest-value first step is to reconcile and extend what exists, especially the release composer, official-actual receipts, expectation semantics, and consumer path.

This revision supersedes the supplied Commission 17 draft as a research recommendation. It does not supersede protected source law or accepted domain contracts. The original is identified by SHA-256 in [the audit](AUDIT_AND_ACCEPTANCE.md). All external-source checks are dated 2026-10-04; repository findings use the immutable revisions below. See [the evidence register](EVIDENCE_REGISTER.md) for exact files, line ranges, primary sources, limitations, and source-quality distinctions.

### Navigation

1. [Decision and user outcome](#1-decision-and-user-outcome)
2. [Current-state recensus](#2-current-state-recensus)
3. [Owner and integration architecture](#3-owner-and-integration-architecture)
4. [Economic semantics and target identity](#4-economic-semantics-and-target-identity)
5. [Logical contracts](#5-logical-contracts)
6. [Time, availability, corrections, and replay](#6-time-availability-corrections-and-replay)
7. [Surprises, revisions, and forecast distributions](#7-surprises-revisions-and-forecast-distributions)
8. [Policy pricing and probability identification](#8-policy-pricing-and-probability-identification)
9. [Rates, inflation, growth, and central banks](#9-rates-inflation-growth-and-central-banks)
10. [Positioning and event risk](#10-positioning-and-event-risk)
11. [Calculation, estimation, and interpretation](#11-calculation-estimation-and-interpretation)
12. [Empirical validation](#12-empirical-validation)
13. [Source selection and procurement qualification](#13-source-selection-and-procurement-qualification)
14. [Implementation sequence](#14-implementation-sequence)
15. [Acceptance, failure, and promotion gates](#15-acceptance-failure-and-promotion-gates)
16. [Bounded implementation handoff](#16-bounded-implementation-handoff)

## 1. Decision and user outcome

Mastermind needs to explain an economic release in the context of what was expected and what was priced. It should preserve:

**reported economic conditions → prior expectations → traded pricing → newly released information → observed repricing → separately tested implications.**

“Economic reality” is a useful conceptual category, but an official statistic is still an estimate of it. First prints, later economic revisions, and source corrections must remain visible. The system must never pretend that a revised GDP estimate was the number traders saw on release day.

A useful release read should answer five questions without requiring the user to assemble them:

1. **What did the official release say?** Show the first reported measure and any revisions to earlier periods, in native units.
2. **What was expected before release?** Show a lawful, frozen economist consensus when available. Show model forecasts and prediction-market indications separately.
3. **What did markets price?** Show the relevant pre-event policy curve, method-implied policy probabilities, option-implied uncertainty, or inflation compensation with the correct target and timestamp.
4. **What changed?** Show the official release error against each admissible baseline, revisions, and subsequent market repricing as different observations.
5. **What can be inferred?** Give a cited explanation, conflicts, and falsifiable mechanisms. State which interpretation remains a hypothesis.

For example, “core CPI exceeded economist consensus by 0.1 percentage point; the previous month was revised lower; two-year yields fell in the defined event window” is an internally consistent observation. “Hot CPI means risk-off” is an untested policy rule. An explanation involving positioning, a more extreme priced outcome, or simultaneous growth news is a hypothesis until the evidence distinguishes it.

The recommendation has four priorities:

- **Repair semantic ambiguity at existing seams.** The current MRI “expectation read” can take a median across a public nowcast and prediction-market values. That is a display-only model-versus-mixed-benchmark comparison, not economist consensus or a post-release surprise. [C3](EVIDENCE_REGISTER.md#c3)
- **Prove event-time admissibility.** Existing official-actual and vintage machinery is a foundation; its existence does not prove full pre-release consensus history or production replay. [C2](EVIDENCE_REGISTER.md#c2)
- **Add information only when it is identified.** Forecaster disagreement, subjective uncertainty, futures-implied means, methodology-implied policy trees, and option-implied densities are different objects.
- **Earn any predictive use through the existing evaluation and promotion owners.** Descriptive usefulness can justify a feature even when no trading advantage is demonstrated. No expectation family automatically receives scoring, gating, ranking, or sizing authority. [C1](EVIDENCE_REGISTER.md#c1)

### Research completion versus implementation completion

This commission is complete when it supplies a current bounded census, defensible economic semantics, source qualification, exact owner seams, a testable build sequence, and a full acceptance specification. It does **not** claim that the proposed adapters, vendor entitlements, historical datasets, real-time capture, consumer repair, or predictive evidence have been delivered.

The commissioned implementation should eventually let a reviewer reconstruct a release from receipts and distinguish “we possessed this then” from “this was publicly available then” and “we reconstructed this later.” That is the practical completion ruler.

## 2. Current-state recensus

### 2.1 Immutable baseline

| Repository | Audited branch and exact commit | Branch observation |
|---|---|---|
| Mastermind | master at a2646f458f9ff41ddcedd89b338be4a4349e6cd6 | Protected |
| Macro | main at d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3 | Branch API reported protected=false |
| mastermind-terminal | master at 1c708450187755160e1a5889b69598a2fcb1f0d1 | Protected |

The Mastermind Skillpack at the pinned commit reports schema mastermind.sol_skillpack.v1, version 1.0.1, and minimum bootstrap major 1. The protected procedure, current task, and applicable custody/effect gates govern this research publication. [C0](EVIDENCE_REGISTER.md#c0)

At the initial hardening read, the supplied report already used the current Mastermind and Terminal pins. Macro had advanced from 818d1bcea9f878a3872d341b6ee355441fd620cf by one commit, a White House alert update. The major corrections below arise from a more complete census of already-existing source, not a claim that the missing functionality was all added overnight.

**Publication-time recheck:** Mastermind advanced to 521720b09be2921e996d9396b522b1c4ca62041c, adding a Trend Persistence research preregistration; Macro advanced to 59a0789c0e5ffcce15e682b6f3880f3eacc6f6fc through THS collection/CI changes and Trend Persistence Agent OS updates. Terminal was unchanged. Exact commit comparisons changed none of the loaded protected procedure or audited MRI/RIC/expectation-owner files. The deep-census links therefore retain their original immutable pins; the final-head evidence is in [C0](EVIDENCE_REGISTER.md#c0).

No deployment or runtime state was re-proven in this hardening pass. The earlier report's installed-runtime snapshot is historical evidence, not a fresh installation claim. A checked-in artifact proves committed bytes; it does not prove the active website or a scheduled producer served those bytes.

### 2.2 Capability map

| Capability | Current evidence and important limits | State for this commission |
|---|---|---|
| Official release actuals | MRI has release_actual.v1, official-source URL/hash validation, target/unit/period metadata, first-receipt preservation, and correction candidates in engine/release_actuals.py. General multicomponent economic revision lineage still needs qualification. | **BUILT_NOT_PROVEN**, partial for the proposed full contract |
| Same-release vintage reconstruction | engine/release_target_truth.py and the release builder prefer canonical actuals, then same-release-vintage proxies. A legacy fallback is explicitly defect-tagged. An index-derived rounded proxy is not automatically the official printed change. | **PARTIAL** |
| Existing MRI composer and publisher | scripts/build_release_forecast.py publishes release_forecast.v2 to existing release-forecast artifacts. This is the incumbent integration surface. | **BUILT_NOT_PROVEN** |
| Economist consensus | Current methodology metadata says street_consensus is unavailable. No lawful, historical, event-time consensus lane was proven. | **NOT_BUILT in the inspected MRI seam** |
| Mixed “expectation read” | engine/release_market_context.py takes a median of available Cleveland/Kalshi/Polymarket values, compares the model point forecast with it, and tags the result. Its own contract makes it display-only. | **BUILT_NOT_PROVEN**, semantic migration required |
| Prediction-market context | Kalshi/Polymarket adapters and staleness checks exist. A stale non-null preferred-source object does not trigger the same fallback as no object; this policy needs explicit treatment. | **PARTIAL** |
| MRI/event-window consumer | engine/event_window.py expects site/release_forecast/latest.json and top-level uppercase release sections; the inspected builder publishes site/macrodata/release_forecast.json with upcoming[]. Scale-field interpretation also requires reconciliation. | **PARTIAL**, static interface mismatch; live effect unproven |
| Macro “surprise” legacy engine | engine/macro_surprise.py documents the lack of historical Street consensus and its use of priors/latest-revised history. Retain its existing meaning; do not rename its outputs genuine consensus surprises. | **PARTIAL** for this mission |
| Fed path and rates/inflation | collectors/rate_futures.py, engine/fed_path.py, and engine/rates_inflation_command.py already own substantial pricing/context composition. Raw provider quality, PIT history, and exact contract mapping remain source-specific. | **BUILT_NOT_PROVEN** |
| Empirical clean-forward evidence | The committed release-forecast artifact reports clean_forward_cpi_n=0, coherent_current_projection_n=0, and withholds accuracy. | **PARTIAL**; clean-forward statistical proof absent |
| Common expectation federation | MAS-119/Cell C remains the named cross-domain semantic owner in accepted decisions. K3E and Market OS compose over domain truth. | Owner boundary verified; implementation state not re-censused |
| New macro score or duplicate regime engine | Prohibited by the commission and existing composition/authority boundaries. | **REJECTED_BY_DESIGN** |

Evidence: [C2–C8](EVIDENCE_REGISTER.md#c2). These labels describe the particular capability being assessed. A source module can exist while the required full user-to-consumer path remains incomplete.

The broad July census cited by the original draft is insufficient for this lane. The replacement is a bounded producer → artifact → reader → consumer census tied to exact source revisions. A future implementation should generate the corresponding observed inventory from the actual producer and consumer, not refresh a broad census merely to make its date look current.

### 2.3 Current adjacent work

RIC already has an October 3 granular-regime contract handoff and explicit canonical-composition boundaries. The recensus identified policy-pricing/source/roll/ledger carriers #7521, #7923 and #7940; release-reaction carrier #7965; EPMD-related carriers #8312 and #8337; and integrated-regime parent #7088. All were open drafts at the audit. Their proposal content is not protected law or proof of active source custody. An implementation owner must inspect their then-current heads and owned paths before editing. [C8](EVIDENCE_REGISTER.md#c8) [C9](EVIDENCE_REGISTER.md#c9)

Accepted Market Belief and K3E decisions preserve MAS-119 for common ExpectationBaseline semantics and MAS-118 for family-specific incorporation science. This commission neither implements those lanes nor invents a new workstream. No current Linear status is asserted here; the earlier draft's Backlog/In Review labels were not independently refreshed in this pass. [C1](EVIDENCE_REGISTER.md#c1)

## 3. Owner and integration architecture

### 3.1 Reuse the actual owners

| Responsibility | Existing owner/seam | Required change or reuse |
|---|---|---|
| Official release facts and receipts | MRI release_actuals, release_target_truth, release_provenance | Extend or reference existing identities and receipt lineage; qualify revision bundles |
| Pre-release observations | MRI source adapters and build_release_forecast | Add typed economist-poll and public-survey/model observations under the existing owner |
| Release forecasts and display composition | Existing release_forecast.v2 producer and its current schema owner | Add typed evidence by a versioned, compatibility-reviewed change |
| Policy curve, rate and inflation context | Fed-path and RIC owners | Preserve pricing semantics, source references, and model lineage |
| Event-window context | Existing engine/event_window.py and actual publication contract | Reconcile reader path, shape, units, and missingness using the real producer fixture |
| Regime output | Existing Macro regime owner | Initially consume references/context only; retain existing regime classification and scoring |
| Portfolio/Terminal/Prophet consumers | Their existing contracts and projection owners | No new authority; consume only through the accepted downstream seam |
| Cross-domain expectations | MAS-119/Cell C | Future narrow adapter only after accepted common semantics exist |
| Incorporation and residual studies | MAS-118 and existing residual/evaluation owners | Supply owner-native evidence; do not build a competing event/residual engine |
| Organizational/runtime continuity | Agent OS / Executive OS respectively | No new registry, queue, lifecycle, or execution plane |

The proposed “Macro Expectations Evidence Family” names related evidence. It is not a new service, database authority, or regime engine.

~~~mermaid
flowchart TD
    A["Official releases and expectation sources"] --> B["MRI: facts and typed baselines"]
    C["Rates, options and inflation sources"] --> D["RIC: pricing and model context"]
    B --> E["Existing Macro regime/context"]
    D --> E
    B --> F["Existing evaluation and federation seams"]
    D --> F
    E --> G["Existing Mastermind consumers"]
~~~

The arrows represent accepted references or versioned adapters. They do not authorize a new publisher at every boundary.

### 3.2 Migration of the existing expectation read

The current compute_expectation_read compares **our forecast** with a mixed median. Its output must not silently acquire the meaning **actual versus economist consensus**.

The proposed migration is:

1. Inventory every reader of expectation_read, expectation_median, standardized, sigma, and sigma_scale_pp. Include UI tests and the event-window consumer.
2. Preserve the existing field during migration with an explicit legacy mixed-benchmark meaning and source list. Do not change its semantics in place.
3. Introduce separately named typed comparisons: model_vs_economist_consensus, model_vs_nowcast, model_vs_prediction_market, and, only after release, actual_vs_locked_economist_consensus.
4. Make the user-facing headline select a declared comparison, with its source class and availability. Missing consensus displays “economist consensus unavailable.” Another class can be displayed beside it, never silently substituted.
5. Test fresh, stale, absent, corrected, incompatible-target, and conflicting-source cases. Source fallback must distinguish a missing object, an object reporting unavailable data, stale data, and a usable value.
6. Change the actual MRI producer and consumer together in an owner-reviewed compatibility wave. Resolve any then-current schema carrier before editing. The inspected release_forecast_v3.py implements a v3_factor forecast-model challenger; its filename does not establish a release_forecast.v3 publication-schema migration.
7. Preserve all existing defect and accuracy-withholding gates. A new source label does not make historical forecast accuracy valid.

Removing a mixed median from a headline can be a correctness improvement without asserting that the old calculation was a production trading input. Its inspected contract is display-only. [C3](EVIDENCE_REGISTER.md#c3)

## 4. Economic semantics and target identity

### 4.1 Evidence classes

| Class | What it measures | What it cannot establish by itself |
|---|---|---|
| Official statistical observation | A reported estimate for a defined economic period | The unobservable final economic truth |
| Economist point-forecast consensus | Summary of a particular panel and statistic | Everyone's beliefs, subjective uncertainty, or traded pricing |
| Point-forecast distribution | Cross-sectional disagreement among panelists | A probability distribution over realized outcomes |
| Subjective forecast density | A forecaster's probabilities over outcomes | An objectively calibrated probability without evaluation |
| Aggregated survey density | A declared mixture of subjective densities | Independence among respondents or a unique representative forecaster |
| Model nowcast/forecast | Output of a named model using a specified information set | Economist consensus or policymaker judgment |
| Central-bank projection | Conditional policymaker or staff projection | A promise, market distribution, or joint policy trajectory |
| Traded quote or curve | Price of a defined instrument/payoff | An unbiased physical expectation |
| Method-implied policy tree | Probabilities under an explicit inversion and support assumption | Unconstrained market tails or a uniquely identified joint path |
| Option-implied density | A fitted pricing-measure distribution under a model and payoff mapping | Physical probabilities without a separate conversion model |
| Positioning/event-risk context | Reported exposures or priced event uncertainty | Directional conviction inferred from volume/open interest alone |
| Post-event repricing | Observed movement during a specified window | Causality, prior expectations, or an implementable trading return |

Source-family membership is a provenance grouping. **Independence is an empirical property**, not a label assigned because one observation comes from a survey and another from a market.

### 4.2 Target keys precede arithmetic

An exact target must include geography, source concept, units, seasonal adjustment, transformation, frequency, reference period, release stage, and revision/settlement convention. A provider identifier is an alias mapped through the existing identity owner, not the target's sole identity.

| Initial release | Exact comparison target | Common invalid comparison |
|---|---|---|
| Headline/core CPI | Monthly percentage change, seasonally adjusted, official printed metric | CPI index level, unadjusted year-over-year change, or recomputed higher-precision index growth |
| Nonfarm payrolls | Monthly change, thousands of jobs, current release's estimate | Difference between two separately selected first-vintage level observations |
| Unemployment | Official unemployment rate, percentage points | Payroll count or direction-reversed “positive growth surprise” without declared mapping |
| PCE/core PCE | Explicit monthly or annual inflation rate and SA basis | CPI consensus or an unstated annualization |
| GDP | Real GDP quarter-over-quarter SAAR, explicit advance/second/third stage | Annual-average GDP growth, nominal GDP, or calendar-year survey growth |
| FOMC | Complete announced target range and effective date; any scalar comparison declares lower bound, upper bound, or midpoint; EFFR/meeting-pricing remains separate | Target midpoint treated as the realized effective rate |
| Policy survey | Named meeting-end, year-end, or average-rate target | SEP year-end median subtracted from a quarterly SOFR average |
| Inflation compensation | Matched maturity, curve convention, timestamp, and inflation basis | Raw par-yield difference treated as an exact zero-coupon expected-inflation rate |

Above-minus-below is a numeric orientation, not “good” versus “bad” for risk assets. Higher unemployment and higher payroll growth have different economic directions. Keep any growth/inflation-direction mapping explicit and separate from the signed source error.

## 5. Logical contracts

These are **requirements for extensions of existing owner contracts**, not permission to create four replacement databases. Implementation must reconcile actual MRI/RIC versions and active carriers before naming production schemas.

### 5.1 Shared receipt and lineage requirements

Every included observation or model output must resolve to:

- Existing owner and owner-native observation/receipt identity.
- Provider and source-family identity; original document/quote identifier and content hash where retention is permitted.
- Exact target key, native value, source precision, units, rounding rule, and transformation version.
- Publication/availability evidence, actual system receipt, system-ready time, timestamp precision, timezone and clock uncertainty.
- Rights reference for the intended use and recipient; provenance does not itself establish permission.
- Source record generation, correction class, superseded receipt reference, and append-only history.
- Method class and method/version; fitted models additionally require parameter/fit vintage and input lineage.
- Per-field coverage/freshness/quality state, with a reason. No arbitrary numeric confidence score substitutes for these facts.

A missing source value is distinct from a derived field that is not estimable. Both must survive composition.

### 5.2 Release bundle

Reuse release_actual.v1 receipts as leaves. A release bundle groups all observations first disseminated together. It requires:

~~~text
release_bundle_id; existing event/calendar identity
scheduled_publication_at; observed_publication_at; earliest_credible_publication_bound
release_stage; agency; original_document_receipt
observations[]:
  receipt_ref; exact_target_id; reference_period; native_value; source_precision
revisions[]:
  target_id; affected_reference_period
  prior_receipt_ref; replacement_receipt_ref
  revision_kind; revision_delta; expected_revision_ref_optional
corrections[]:
  corrected_receipt_ref; new_receipt_ref; correction_kind; available_time_evidence
~~~

A payroll release can revise two previous months; an annual benchmark can revise many periods. One revised_prior scalar cannot preserve that. CPI seasonal updates and GDP benchmark revisions can also change history. [W6](EVIDENCE_REGISTER.md#w6)

Use separate kinds for **new economic estimate**, **routine statistical revision**, **benchmark/seasonal-method revision**, **agency erratum**, **vendor correction**, and **internal normalization repair**. An agency erratum discovered later is not an observation available in the original announcement window.

### 5.3 Expectation observation

One owner-native expectation record has a tagged payload:

- **Individual point forecast:** value, respondent identity when licensed, forecast target, survey vintage, contribution timestamp when actually known.
- **Panel summary:** supplied statistic, value, panel/contributor count, weighting, coverage, and composition metadata.
- **Individual density:** bin boundaries and inclusivity, probabilities, open-tail flags, conditioning question, respondent and survey identity.
- **Aggregate density:** constituent density references, weights, aggregation method, and retained source rounding.
- **Model forecast:** model/version, run and publication timestamps, input vintages, training/parameter vintage, output target and uncertainty method.
- **Central-bank projection:** institution, participant/staff/publication class, conditioning assumptions, horizon and projection vintage.

For surveys, distinguish survey open/close, participant formation/contribution time, aggregate publication, vendor delivery, and Mastermind receipt. Do not fill missing individual forecast dates with the survey deadline. Store suppressed/missing respondents and panel changes; anonymity or reused IDs can prevent a true matched panel. [W4](EVIDENCE_REGISTER.md#w4)

A set of percentiles of point forecasts belongs to a panel summary. It is not automatically a density with 10% probability below the panel's p10.

### 5.4 Market pricing observation

Use a tagged union with fields appropriate to the payload:

| Payload | Required distinguishing fields |
|---|---|
| Raw quote/settlement | Instrument ID, bid/ask/last/settlement, exchange/source time, delivery time, reference data, quote age, market status |
| Implied rate or curve | Payoff/reference interval, simple/compounded average, day count, curve/bootstrapping convention, raw quote lineage |
| Method-implied discrete tree | Outcome support, probabilities, meeting/effective-rate mapping, tree assumptions, method version |
| Option-implied density | Underlying payoff, expiry, exercise style, pricing measure, surface/fit version, support/tail treatment, input quotes and arbitrage diagnostics |
| Inflation compensation | Nominal/real or swap convention, maturity alignment, index basis/lag, source timestamp |
| Economic decomposition | Model identity, fitted vintage, component definitions, residual, uncertainty, input data lineage |

Treasury curves, swap rates, and futures-implied means do not need empty probability arrays. Unknown tails remain unknown. Each meeting's marginal distribution is not a joint transition model.

### 5.5 Derived evidence view

The derived view is an MRI/RIC composition of references and declared calculations:

~~~text
decision_cutoff; replay_mode; emitted_at; derivation_version
release_bundle_ref
locked_baselines[] with source class and admissibility result
comparisons[] with exact target pair, native-unit difference and optional normalization
revision_edges[]
pricing_refs[] and event-window repricing references
survey_disagreement[]; subjective_uncertainty[] when identified
model_components[] with fitted-vintage references
coverage_by_field[]; contradictions[]; dependency_groups[]
authority: inherited context/research-only restriction
~~~

Do not emit an invented universal expectation_gap_score, macro-belief confidence, or “risk-on probability.” Existing downstream authority must remain unchanged.

## 6. Time, availability, corrections, and replay

### 6.1 Separate three questions

| Mode | What a result may claim | Required availability proof |
|---|---|---|
| **Historical public-information reconstruction** | This evidence could have been known through the specified public/channel information set at the historical cutoff | Contemporaneous publication/channel evidence, content/version identity, and a defensible availability upper bound |
| **Historical Mastermind system replay** | Mastermind actually possessed and could consume this evidence then | Historical entitlement where relevant, actual receipt, normalization/admission-ready timestamp, and original method/configuration |
| **Retrospective research reconstruction** | This later dataset or fixed method reconstructs a historical quantity | Honest ex-post label and full reconstruction lineage; not historical possession or live availability |

A later archive download can support the first or third mode if the evidence warrants it. It cannot manufacture an old system receipt.

Store economic reference period, forecast target, market reference interval, quote timestamp, publication timestamp, vendor availability, received_at, and system_ready_at separately. “As of” must not ambiguously mean all of these.

For a decision cutoff c:

- Historical public reconstruction requires the **latest defensible availability bound** for the chosen generation to be no later than c.
- System replay additionally requires received_at ≤ c and system_ready_at ≤ c, with a valid historical source/channel entitlement when needed.
- If the availability bound is unknown, the observation is inadmissible for that claim.
- A model output additionally requires an admissible model publication/fit vintage and input set. A newly fitted model rerun over old inputs is a research reconstruction unless its historical availability is separately proven.

The derived record's availability cannot precede any parent observation, parameter vintage, or required processing step. Use the existing owner metadata rather than introducing another clock authority.

### 6.2 Intraday cutoffs require intraday evidence

A date-only ALFRED vintage is useful evidence of a historical data vintage. It is not proof that a vendor delivered it before an 08:30 release. FRED explicitly distinguishes source release dates from FRED/ALFRED availability. [W3](EVIDENCE_REGISTER.md#w3)

Represent timestamp precision and, where necessary, an availability interval. A date-only record ordinarily fails an intraday cutoff within that date. Do not stamp midnight merely to force eligibility. Any conservative date-to-time conversion must state the timezone, bound, and basis, and remain distinguishable from an observed timestamp.

For scheduled releases:

1. Use the existing event/calendar identity.
2. Retain scheduled time and the earliest credible dissemination time separately.
3. Freeze the pre-event baseline at the chosen decision cutoff before the earliest credible release, allowing the declared clock/transport uncertainty margin.
4. Reject an apparent “pre-release” input if evidence shows the release or relevant files were already disseminated.
5. Preserve a delayed, cancelled, rescheduled, or unscheduled event as that event state; do not manufacture a normal timestamp.

The May 2024 BLS early-file publication incident and a June 2024 CPI reissue are useful real adversarial cases. They show why a scheduled calendar timestamp and a currently dated archive page do not by themselves prove an untouched first release. [W6](EVIDENCE_REGISTER.md#w6)

For intraday market measurements, endpoints must name a specific instrument and eligible quote convention. For an endpoint t, use the last valid quote at or before t within a declared age limit. Do not use the nearest quote if it can lie after t. A stale daily curve cannot fill a five-minute window.

### 6.3 Consensus locking

Lock the **latest admissible observation**, not the latest value now returned by a vendor API. The lock binds:

- Exact release target and event.
- Selected provider, panel, statistic and observation generation.
- Source publication/channel availability and actual system-readiness evidence for the chosen mode.
- Cutoff policy, event clock generation, and deterministic selection method.
- Source rights and coverage state.

“Final consensus” fetched after the event is admissible only if the provider proves that this exact generation existed before the cutoff. A historical event-date query is not necessarily an as-of query. If only final values are available, preserve the historical-consensus gap and start prospective capture after authorization.

The policy for choosing among multiple qualifying providers must be declared before outcomes are examined. Do not choose whichever median best explains the eventual price move. Preserve competing values and source disagreement.

### 6.4 Correction and vintage selection

Append corrections and supersession edges; never rewrite a receipt that supported an earlier view. A replay at cutoff c resolves only generations admissible at c. Appending a correction after c must leave the earlier replay's selected IDs and digest unchanged.

The existing release_actual.v1 keep-first behavior is valuable, but “first receipt in our ledger” and “first official value disseminated publicly” are different facts. Both may need representation. A late-imported archived release must not receive a fabricated contemporaneous observed_at.

Keep official economic revisions distinct from data repairs. When the agency republishes an erroneous value, preserve what was first disseminated and the later correction. For an economic revision to an older period, preserve the earlier period and connect its old and new estimates through a revision edge.

Payroll change reconstruction must use the level values and revision context **from the same release vintage** where that is the chosen proxy. Subtracting the prior month's original level from the current month's later-vintage level can produce a cross-vintage error. Prefer the agency's explicitly reported change when it matches the target. [C2](EVIDENCE_REGISTER.md#c2)

### 6.5 Freshness and missingness

Freshness is field-specific and purpose-specific:

- A quarterly SPF vintage can be the latest valid survey context while being unsuitable as a current monthly release consensus.
- A CME EOD observation can support an end-of-day state, not an intraday reaction.
- A survey formed before a meeting but published after it is unavailable to a public premeeting decision.
- A fresh file containing a stale event row is still stale for that event.

Use the existing coverage vocabulary with reason codes sufficient to distinguish NO_COVERAGE, NOT_YET_PUBLISHED, NO_ADMISSIBLE_BASELINE, STALE_FOR_PURPOSE, SOURCE_DELAYED, CORRECTION_PENDING, INCOMPATIBLE_TARGET, METHOD_NOT_IDENTIFIED, RIGHTS_UNVERIFIED, and RIGHTS_BLOCKED. These are proposed field-level reasons, not new job/lifecycle states.

Each source manifest must declare cadence, publication/channel lag, maximum age for the particular consumer, completeness expectations, correction behavior, and outage behavior. If the policy is absent, fail that use rather than inventing a universal time-to-live.

## 7. Surprises, revisions, and forecast distributions

### 7.1 Release error in native units

For release component i in event bundle t:

$$
S_{i,t}=A^{first}_{i,t}-E^{locked}_{i,t^-}.
$$

A is the admissible first reported metric; E is the locked expectation for the exact same target. Retain both inputs and their source precision. Call this an economist-consensus surprise only when E is economist consensus. A model error, nowcast error, and prediction-market gap get their own names.

A forecast-versus-baseline gap computed before release is not S. The actual has not arrived. Missing consensus does not make the prior observation an acceptable consensus substitute.

A synthetic payroll example illustrates why revisions remain separate:

| Quantity | Value, thousands |
|---|---:|
| Locked economist median for current month | 180 |
| Official current-month first print | 220 |
| Current-month consensus surprise | +40 |
| Prior month: previously known 200, revised to 180 | −20 revision |
| Month before that: previously known 150, revised to 140 | −10 revision |

The release delivered a +40 current-month surprise and −30 of reported prior-period revisions. Do not compress those into a universal “net surprise +10.” They concern different periods and possibly different economic information.

### 7.2 Revision delta is not automatically revision surprise

For an affected prior period p:

$$
R_{p,t}=A^{new\ vintage}_{p,t}-A^{known\ before\ t}_{p}.
$$

This is an **official revision delta**. A revision surprise requires a separately locked expectation:

$$
RS_{p,t}=R_{p,t}-E^{locked}_{t^-}[R_{p,t}].
$$

If that expectation is unavailable, RS is unavailable. Zero is not a default revision forecast. Benchmark/seasonal changes need separate revision classes and evaluation strata.

The revision contribution can be studied alongside the new print, with disclosed weighting or a vector model. Any weighted total is an estimated research specification, not a new source fact.

### 7.3 Normalization that can actually be implemented

Keep raw error primary. Define two optional historical normalizations clearly:

$$
V_{i,t}=\frac{S_{i,t}}{\widehat{\sigma}_{i,t^-}},
\qquad
Z_{i,t}=\frac{S_{i,t}-\widehat{\mu}_{i,t^-}}{\widehat{\sigma}_{i,t^-}}.
$$

V is a volatility-scaled error; Z additionally removes the historical mean error. They differ when the consensus has bias. Neither implies a Gaussian distribution or supplies a calibrated tail probability.

**Proposed research default, to preregister before scoring:** use the most recent 60 eligible earlier release bundles for the same target, stage, and comparable definition era; require at least 36. Compute sample standard deviation with n−1 degrees of freedom. Store member IDs, n, window, mean, scale, source policy, and method version. This is a conservative engineering starting point, not an empirically optimal parameter.

Only errors with first-print actuals and valid pre-release baselines may enter the scale. At each historical event, use only earlier information available under the declared replay mode. In walk-forward evaluation, freeze hyperparameters within the training fold. Do not let a post-event correction or full-sample fit silently change the scale historically used.

If the estimated scale is non-finite or at/below the declared source-precision floor, refuse the normalized field. Do not add a tiny epsilon and output a huge “surprise.” If 36 valid earlier bundles do not exist, show the raw error and INSUFFICIENT_NORMALIZATION_HISTORY.

An explicitly preregistered robust alternative can use median/MAD, but do not choose between estimators after seeing test performance. Large crisis observations remain in the raw record; any robust treatment is disclosed and compared as a sensitivity analysis.

For contemporary panel disagreement:

$$
D_{i,t}=\frac{A^{first}_{i,t}-\operatorname{median}(F_{i,t^-})}
                   {\operatorname{IQR}(F_{i,t^-})}.
$$

Name it **IQR-scaled error**, not a z-score. Proposed minimum panel size is 10 comparable valid forecasts; IQR must exceed a declared precision floor. If only a median is licensed, do not manufacture dispersion or assume it from historical errors.

### 7.4 Forecast revision paths

Compare forecasts only for the same target period, target definition, horizon convention and statistic. Record the actual age between vintages.

A change in a reported panel median is **aggregate consensus movement**. A matched-panel measure asks how the same respondents revised. They can diverge because of panel entries, exits, changed weights, or reused identifiers.

For a lead interval k, use the eligible snapshot at or before the historical anchor t−k, subject to the source-specific freshness policy. Do not select a later observation merely because it is closer. If both anchors resolve to the same observation ID, label NO_NEW_VINTAGE; do not present “zero revisions” as evidence that participants reaffirmed their forecasts.

Begin with level changes, actual elapsed time, panel overlap and revision breadth. Defer acceleration and high-order trajectories until snapshot frequency and measurement stability justify them. Quarterly surveys do not become daily expectation series through forward filling.

Revision breadth requires valid respondent matching. Report the fraction raised/lowered/unchanged among the matched sample, the matched N, and entrants/exits separately. Do not equate a stable vendor respondent code with a stable person or methodology without documentation.

### 7.5 Disagreement and subjective uncertainty

Panel point dispersion measures disagreement. Subjective density width measures uncertainty. These can move independently; a panel can agree on a mean while each member is highly uncertain. Federal Reserve methodological guidance explicitly distinguishes these concepts. [W24](EVIDENCE_REGISTER.md#w24)

Where compatible individual densities with identifiable moments exist, a weighted mixture obeys:

$$
\operatorname{Var}_{mix}(X)
=\sum_j w_j\operatorname{Var}_j(X)
+\sum_jw_j(\mu_j-\mu_{mix})^2.
$$

The first term is average within-forecaster uncertainty. The second is disagreement among density means. It is not automatically the variance of separately submitted point forecasts, which may represent another summary statistic.

Preserve bin boundaries, open-ended tails, rounding, weights and variable/horizon changes. Open-ended survey bins often do not identify finite moments without assumptions. Store the original bins and refuse moments, or explicitly fit a tail model with an empirical-model label.

Evaluate densities using proper scores against their stated economic target; evaluate point-forecast dispersion separately. Do not assign probabilities of realized outcomes from the empirical ranks of forecasters.

## 8. Policy pricing and probability identification

### 8.1 Futures-implied rate first

For ZQ, the quoted index maps to a contract-month average effective federal funds rate. Under a deliberately simplified one-effective-change month:

$$
\bar r =100-P,\qquad
r_{post}=\frac{D\bar r-\sum_{d\in pre}r_d}{D-n}.
$$

D counts calendar settlement days; n is the number of days before the assumed change takes effect. Weekend/holiday accrual, rate-publication lag, meeting/effective dates, historical fixing corrections and days already realized must follow the contract. Unknown pre-change future days require a disclosed assumption. This is not a license to treat the announced target midpoint as EFFR. [W12](EVIDENCE_REGISTER.md#w12) [W13](EVIDENCE_REGISTER.md#w13)

Handle first/last-day meetings, unscheduled changes, multiple changes, and missing valid contracts explicitly. If the selected method cannot identify the post-change rate, return METHOD_NOT_IDENTIFIED. Do not clip impossible probabilities into [0,1] to hide a calendar or basis error.

### 8.2 A mean does not identify a distribution

**Synthetic arithmetic, not current market data:** assume a 30-day month, 20 pre-effective days at 4.33%, 10 post-effective days, and ZQ price 95.72. Then the implied monthly mean is 4.28%, and:

$$
r_{post}=\frac{30(4.28)-20(4.33)}{10}=4.18\%.
$$

Both distributions reproduce that post-effective mean:

| Assumed distribution | Hold at 4.33% | Cut 25 bp to 4.08% | Cut 50 bp to 3.83% | Mean change | Standard deviation of change |
|---|---:|---:|---:|---:|---:|
| A | 40% | 60% | 0% | −15 bp | 12.25 bp |
| B | 70% | 0% | 30% | −15 bp | 22.91 bp |

The same futures price is compatible with a 60% probability of any cut under A and 30% under B. Additional assumptions or instruments are required to choose.

CME FedWatch makes a specific tree construction with adjacent 25 bp outcomes and calendar/EFFR assumptions. Preserve that as **method-implied policy probabilities**. Do not describe its tails as unconstrained option evidence or assume its first-node entropy adds information independent of the implied mean and support. [W12](EVIDENCE_REGISTER.md#w12)

Each method record must preserve probability_basis, support, meeting mapping, current EFFR/target basis, method version, source quote time, and limitations. Probabilities should sum to one within documented source rounding, but that arithmetic invariant does not establish the economic model.

### 8.3 SOFR and option-implied densities

SR3 references compounded overnight SOFR over a reference quarter. Preserve the quarter, remaining and realized accrual portions, actual day count, instrument and fixing conventions. SOFR, EFFR, and a target-range endpoint are different underlyings. Futures convexity and funding/basis effects also matter. [W13](EVIDENCE_REGISTER.md#w13)

Option-derived densities need a defined payoff and pricing measure. Require:

- Option expiration, underlying futures contract and its final-settlement date/reference quarter, exercise style, settlement and margin convention.
- Eligible bid/ask or settlement observations at a coherent market cut.
- No-arbitrage and stale/crossed-market diagnostics.
- Surface fitting, sparse-strike treatment, support/tails, and parameter version.
- Early-exercise treatment when the option is American.
- Explicit target transformation and resulting uncertainty.

A naive European second-strike-derivative calculation applied to raw American SOFR option premiums is not automatically valid. The option model belongs in the fitted-statistical lane.

Atlanta Fed MPT is a useful benchmark for option-derived distributions of a **three-month compounded-average SOFR**. Its daily, typically previous-day inputs do not supply five-minute announcement prices. Its horizon must not be relabeled as the end-of-next-meeting policy target. An independent reconstruction must also distinguish the futures-price underlier at option expiration from the eventual realized quarterly rate. [W14](EVIDENCE_REGISTER.md#w14)

Do not convert pricing-measure distributions to physical probabilities with an ad hoc risk-premium subtraction. Any conversion is a separately estimated, versioned model evaluated out of sample.

### 8.4 Event repricing and contract roll

Compute repricing on matched instrument/payoff identities at both endpoints. A front-contract series that rolls between samples confounds information with horizon change. If the intended comparison is a constant horizon instead, use an explicit curve interpolation/mapping and retain both endpoint instruments and model assumptions.

Separate:

- Current policy decision and effective date.
- Near-meeting rate repricing.
- Further policy-path repricing.
- Statement/SEP, press conference, and later minutes windows.
- Curve shape and term-premium movement.
- Estimated target/path/information factors.

The last category requires econometric identification. It is not a plain deterministic label derived from one sign.

## 9. Rates, inflation, growth, and central banks

### 9.1 Curves and term premium

The Treasury publishes nominal and real par-curve data. A matched nominal-minus-real published yield is useful inflation-compensation context, but par yields are not zero-coupon discount rates. Keep maturity, quote timing, interpolation and nominal/real construction explicit. [W15](EVIDENCE_REGISTER.md#w15)

Do not plug par yields into an exact zero-coupon forward formula. For continuously compounded zero yields only:

$$
f_{a,b}=\frac{b z_b-a z_a}{b-a}.
$$

Other conventions require their own formula. Missing maturities and non-synchronous quotes remain visible.

NY Fed ACM estimates an expected-short-rate component and term premium. Preserve it as a model output, including its estimation/publication vintage. Downloading today's entire historical file does not establish the estimates available historically. A later constant-method reconstruction can be valuable research when labeled accordingly. [W16](EVIDENCE_REGISTER.md#w16)

A long-yield increase can reflect changes in expected rates, term premium, or model residuals. That decomposition helps interpretation, but it does not independently identify causal policy news.

### 9.2 Inflation breakevens and swaps

Inflation compensation includes expected inflation and risk/liquidity/indexation effects. Its exact interpretation depends on instrument construction. Keep:

- Raw nominal/real yield observations and their compensation measure.
- Model-estimated expected inflation and risk-premium components.
- Inflation-swap quotes/transactions with the appropriate index, lag and payoff.
- Residuals and comparability limitations.

Cleveland's inflation-expectations model is a distinct monthly model; its documentation says it does not use TIPS as inputs. Do not present it as a direct identity decomposition of Mastermind's particular par breakeven series. Record model publication time and data substitutions/revisions. [W17](EVIDENCE_REGISTER.md#w17)

Zero-coupon inflation swaps and year-on-year swaps have different payoffs. Require inflation index, base/reference dates, publication lag, interpolation, seasonal treatment, annualization, collateral/discounting, counterparty/quote convention and corrected-trade lineage. A real transaction is not necessarily an executable two-sided curve observation.

Public SDR prints can support transaction/liquidity research. Smooth curve reconstruction from them is a separate model and may be sparse, delayed, anonymized, amended or cancelled. It is not a free substitute for an institutional pricing surface. [W21](EVIDENCE_REGISTER.md#w21)

Defer a commercial inflation-swap curve until the simpler evidence earns enough value to justify a specific need. ICE's named GBP/EUR benchmark offerings and conditional USD expansion must be distinguished from separate vendor curve products; obtain an exact live USD product specification if USD coverage is required. [W18](EVIDENCE_REGISTER.md#w18)

### 9.3 Growth expectations and model nowcasts

Retain quarterly SAAR, annual-average, year-over-year and level targets separately. GDPNow is a named model forecast, not official Atlanta Fed judgment or economist consensus. Its history includes model-era/publication qualifications. Cleveland inflation nowcasts likewise require the output actually published before the selected release cutoff, not a later same-day update. [W10](EVIDENCE_REGISTER.md#w10)

Compare a model nowcast and survey only when their target, release stage and convention match. Otherwise display them as contextual evidence or perform an explicit documented transformation. Do not manufacture components needed for a transformation.

An input update can move a nowcast without any panelist changing an opinion. Preserve input contribution/model-run lineage where provided; this helps distinguish new economic information from parameter revisions.

### 9.4 Central-bank expectations

SEP projections are conditional on each participant's appropriate policy assumptions. Anonymous dots at different horizons do not supply individually traceable paths; independently reported medians do not necessarily form a coherent representative joint forecast. Keep policy projections distinct from survey and market pricing. [W11](EVIDENCE_REGISTER.md#w11)

NY Fed Survey of Market Expectations questions appear before a meeting, but public results arrive afterward. Only an already-published vintage belongs in the public premeeting information set. Preserve the 2025 survey/panel transition and the public-history limits of predecessor surveys. [W5](EVIDENCE_REGISTER.md#w5)

For ECB/Bank of England and later other jurisdictions, record formation versus publication, policy instrument, horizon and institutional basis. A stale prior survey can be displayed honestly; unpublished same-meeting results cannot be used because their respondents answered earlier. [W25](EVIDENCE_REGISTER.md#w25)

The first global extension should follow a source-qualified target set, not a blanket country rollout. China and other markets need separately validated official-release clocks, units, consensus history and lawful availability. No equivalence to U.S. series is assumed.

## 10. Positioning and event risk

### 10.1 Slow positioning

CFTC positioning records have at least a positions-as-of date and a publication date. Use the latter for knowability. Do not use Tuesday's reported positions in a Wednesday decision if they were not published until Friday. Holiday delays and corrections require actual evidence; older inferred release calendars must be labeled. [W19](EVIDENCE_REGISTER.md#w19)

Category net exposures and changes can provide context, with denominator and normalization history. Preserve futures-only versus futures-and-options-combined scope, trader category, contract universe and open-interest denominator. They do not identify every participant's event bet, hedge, cash exposure, or intraday changes.

### 10.2 Volume, open interest and implied event variance

Every futures contract has both a long and a short. Volume or rising open interest alone does not reveal net bullish intent. Preserve source reference dates separately: a page can pair today's volume with prior-day open interest. [W20](EVIDENCE_REGISTER.md#w20)

Option-implied event variance is an estimated object. A difference between maturities around an event needs a non-event variance baseline, compatible payoffs, appropriate weighting and an unchanged observation cut. Overlapping releases, exercise features, liquidity and surface errors can prevent identification. Preserve a negative/inconsistent residual as a diagnostic rather than silently clipping it and claiming zero event risk.

Only add such features when the existing options owner can supply suitable references and rights. No new options collection or positioning plane is proposed.

### 10.3 Prediction markets

The existing MRI Kalshi/Polymarket inputs deserve an explicit class. Their prices depend on contract wording, settlement source, rounding, thresholds, timing, fees, liquidity and platform structure. They are neither an economist poll nor automatically an unbiased physical probability.

For every contract preserve the economic target and settlement version, including whether settlement uses first release or later corrections. A quoted bucket probability does not always identify a numeric median, mean, or continuous density. Store the original support and document any inferred statistic.

For multimarket aggregation require aligned mutually exclusive/exhaustive outcomes, coherent quote timestamps, no-arbitrage checks where applicable, and disclosed normalization. Missing tail buckets remain missing. Platform disagreement is useful context; averaging venues does not establish independent confirmation.

## 11. Calculation, estimation, and interpretation

The boundary has **three lanes**, not “deterministic code versus LLM.”

| Lane | Responsibilities | Required proof |
|---|---|---|
| **Deterministic record handling and arithmetic** | Identity/target validation; source/version selection; time conversion; cutoff checks; source precision; raw differences; declared fixed-weight summaries; quote/contract mapping; coverage and rights enforcement | Reproducible inputs, invariant tests, exact receipts and method/configuration |
| **Statistical/economic estimation** | Nowcasts; scale fitting; option-density fitting; curve/decomposition models; risk-premium adjustment; PCA target/path factors; residuals; empirical regime interactions; physical-probability calibration | Fit/data vintage, assumptions, uncertainty, training boundary, out-of-sample validation and limitations |
| **Language interpretation** | Explain structured evidence; compare hypotheses; summarize central-bank text; propose transmission mechanisms and falsifiers | Cited inputs, separation of fact/inference, contradiction preservation, no numeric source authority |

Some statistical procedures are computationally deterministic given fixed inputs. That does not turn their estimates into observed facts. A fixed curve algorithm still has assumptions; a fixed PCA implementation still has fitted loadings.

An LLM may suggest an extraction candidate or identify a likely target mismatch, but the existing owner must validate the record before use. Neither a cheap nor frontier model may invent consensus, timestamps, densities, probabilities, revisions, or entitlement. Numeric claims in generated prose must resolve to the structured view.

A release explanation should retain conflict: “consensus error was positive, revisions were negative, and the observed rates response was lower.” It may then propose mechanisms with explicit evidence and falsifiers. It must not fill unknown positioning with a confident story.

## 12. Empirical validation

### 12.1 Preregister different questions separately

The empirical unit is a **release/communication bundle**, not every field, contract, security, or horizon generated from it. CPI headline and core released together do not provide two independent event dates. FOMC statement and press conference windows have different information sets and correlated outcomes.

| Study | Information cutoff | Outcome | Claim it can support |
|---|---|---|---|
| **A. Immediate information response** | Controls and expectations frozen before release; actual surprise is the event information | Matched market changes over a declared announcement window | Descriptive/explanatory association; causal language requires additional identification |
| **B. Post-release continuation** | A specific post-release decision time when actuals, processing and any early reaction are available | Return/change beginning after that decision time | Out-of-sample continuation/reversal forecasting, net of feasible execution when trading is studied |
| **C. Economic forecasting** | Explicit pre-forecast cutoff | Future first release or a separately specified mature-vintage economic estimate | Improvement in forecasting that defined economic target |
| **D. Distribution assessment** | Forecast publication/market cut and defined target horizon | Realization of that target under the relevant settlement/measurement rule | Calibration/sharpness and predictive value for the declared probability interpretation |

A first-print target is correct for “what will the next release say?” A fixed-lag mature-vintage target can be correct for “what economic state eventually emerged?” They are different experiments. The mature target is not leakage merely because it is revised, provided it is an outcome and training only uses labels already mature at the training cutoff.

### 12.2 Avoid conditioning on the answer

For Study A, an existing regime control is admissible only if frozen at t-minus. A post-release regime incorporating the same yields, dollar, or equities used in the outcome is a mediator or response-contaminated control. Using it can create circular attribution.

For Study B, the early price response may be a predictor if it is known at the chosen decision time. Then returns must start afterward. Do not report release-to-close profit while assuming a signal that was computed five minutes after release could trade at the release-time price.

For FOMC studies, distinguish statement, SEP, press conference and minutes. SF Fed USMPD supplies documented event-window observations and code useful for benchmark replication. Its newly published historical data are retrospective evidence, not proof that Mastermind possessed them in past decisions. [W22](EVIDENCE_REGISTER.md#w22)

A target/path factor or “central-bank information shock” requires a named estimated specification, input window, loading/identification restrictions and uncertainty. Competing interpretations exist; a rates/equities sign pair is not unique causal proof. [W23](EVIDENCE_REGISTER.md#w23)

### 12.3 Baselines and incremental information

Freeze the exact current owner output and source revision used as the baseline. If a historical version of the regime cannot be reconstructed lawfully, record that limit and use a separately labeled reproducible baseline; do not call it the historical production state.

Test a small candidate set:

1. Existing admissible macro/regime context and pre-event market state.
2. Add current first-print release error against valid economist consensus.
3. Add official revision vector.
4. Add survey disagreement and matched-target revision movement.
5. Add separately typed model-versus-survey gaps.
6. Add pre-event policy pricing and properly identified distribution features.
7. Add eligible positioning/event-risk context.

Sequential addition is order-dependent. Also run leave-one-family-out comparisons and source-aware dependency analysis. Group mechanically related inputs: a FedWatch mean and entropy derived from that mean/support are not independent families; nominal yield, real yield and their spread are algebraically linked; options, survey and model sources may share inputs.

Assess performance on the same eligible event support, then separately report coverage value. Otherwise a source can appear better because it skips difficult events. Report how missingness correlates with stress, event family, source outages and era.

Avoid an indiscriminate library of interactions. Predeclare a few economic hypotheses, such as whether a labor revision alters the response to the current payroll surprise, or whether survey disagreement changes response magnitude. The existing regime owner retains any later interaction implementation.

### 12.4 Splits, labels and uncertainty

- Use chronological outer evaluation folds and an untouched final holdout; select parameters only within training/inner validation.
- Purge information leakage and overlapping event/label intervals across the split. Embargo by the longest relevant outcome interval; handle training labels that have not yet matured. Shared older lookback inputs alone do not require discarding every overlap: a common trailing normalization window does not automatically imply a 60-event purge.
- Freeze model inputs, fitted parameters, transforms, source mapping and normalization membership per cutoff.
- Cluster uncertainty by announcement/date, with dependence-aware resampling when events or horizons overlap. Hundreds of securities responding to one CPI release are not hundreds of independent macro surprises.
- Report performance by release family, target-definition era, policy regime and volatility/stress subset where sample size permits. If power is inadequate, say so.
- Preregister primary outcome, direction, horizon, minimum useful effect, loss function, comparison, multiplicity policy, exclusion rules and stopping rule.
- Determine required event count through a power/sensitivity analysis using training data or simulations. Do not interpret “three examples passed” or “30 days elapsed” as statistical validation.

Proposed starting research envelope: CPI/core CPI, payrolls/unemployment, and scheduled FOMC communications for which source and market windows are qualified. Add PCE, GDP and retail sales after mapping and sufficient support are proven. Do not claim a regime-general result from a single post-pandemic episode.

Useful metrics depend on the question:

| Question | Primary metrics and checks |
|---|---|
| Numeric forecast | Out-of-sample loss relative to baseline, mean error/bias, MAE/RMSE, uncertainty interval |
| Binary physical forecast | Brier/log score versus unconditional and admissible market baselines, calibration with confidence intervals |
| Subjective density | CRPS/log score when a valid density is available; bin-compatible scoring if only bins are identified |
| Quantiles | Pinball loss and coverage by horizon |
| Immediate/continuation response | Out-of-sample explanatory/predictive loss, sign accuracy as secondary, effect sizes with clustered intervals |
| Economic usefulness | Feasible post-decision performance, costs/latency, robustness and coverage; no authority promotion from gross returns alone |

Pricing-measure probabilities are not required to realize as physical frequencies without adjustment. Evaluate their information content, pricing consistency and any separately estimated physical conversion. Do not call an uncalibrated risk-neutral density a failed options-pricing object solely because realized frequencies differ.

### 12.5 Adversarial leakage tests

These are correctness tests, independent of whether leaked data happen to improve returns:

- Append a post-event “final consensus.” Earlier baseline locks and evidence digests must not change.
- Append a later official revision or vendor correction. Earlier replay remains stable.
- Give a date-only vintage an intraday cutoff. It must fail absent stronger timing evidence.
- Attempt to use a same-meeting survey published after the event. It must fail.
- Feed a training fit containing future or unmatured labels. It must fail.
- Feed a contemporaneous regime that incorporates the response window into Study A. It must fail.
- Attempt to measure an outcome starting before Study B's decision-ready time. It must fail.
- Change one field's quote/reference date while keeping the file timestamp fresh. That field must become ineligible.
- Remove economist consensus. No output may still claim economist-consensus surprise through a fallback.
- Reuse the same inputs, cutoff and method generation. Output and selected-receipt digest must reproduce.

A leaky model can score better or worse. Score movement is never the leakage detector.

### 12.6 What would falsify value?

Maintain separate outcomes:

- **DATA_INVALID:** PIT, units, target, rights or correction lineage cannot support the intended claim.
- **METHOD_NOT_IDENTIFIED:** the observations do not identify the requested distribution, decomposition or event effect.
- **INSUFFICIENT_EVIDENCE:** too few events, unstable support or insufficient power.
- **NO_INCREMENTAL_VALUE:** adequate evaluation fails the preregistered minimum effect against the incumbent.
- **DESCRIPTIVE_VALUE_ONLY:** explanatory/context value exists without reliable forward prediction.
- **ELIGIBLE_FOR_SEPARATE_PROMOTION_REVIEW:** all specific evidence gates pass; authority still unchanged.

An invalid or low-value premium feed can be rejected without discarding valid official-release context. A useful descriptive family can remain permanently context-only.

## 13. Source selection and procurement qualification

### 13.1 Source roles, not one universal vendor

| Source route | Proposed role | Admission limit / missing proof |
|---|---|---|
| Direct BLS/BEA/Fed publications and archives | First-party actuals, release bundles and correction lineage | Capture the actual document/version; old dynamic table links can show latest data |
| FRED/ALFRED | Vintage cross-check and qualified reconstruction where permitted | Date-level timing limits; exact archival/model uses require rights qualification |
| Philadelphia SPF/Livingston | Medium-horizon point forecasts, disagreement and subjective distributions | Variable-specific history, definition/bin changes, corrections, publication and respondent-ID caveats |
| NY Fed SME and predecessors | Policy survey context from already-published vintages | Same-meeting results are not public premeeting inputs |
| LSEG Reuters Polls | Leading enterprise release-consensus candidate | Endpoint-specific PIT snapshots, correction history, contributor access and rights must be demonstrated |
| Trading Economics | Serious challenger for the release-consensus pilot | PIT page alone does not prove arbitrary as-of retrieval or every forecast revision; Forecast and TEForecast differ |
| Bloomberg | Alternative where an existing qualifying entitlement reduces total cost | Specific API/history/redistribution capability and sample remain unverified |
| Consensus Economics | Optional global, medium-horizon forecast-vintage enhancement | Monthly survey history is not a substitute for event-time release consensus |
| GDPNow / Cleveland nowcasts | Independent model baselines | Model/publication era, same-day timing, version history and permitted reuse |
| CME FedWatch API | Methodology-consistent policy-probability observations | EOD/stream/historical-vintage scope and actual entitlements require sample proof |
| CME raw ZQ/SR3 futures/options | Controlled pricing/repricing and later fitted densities | Reference data, calendar/basis, exercise, source time, history and licensing |
| Atlanta MPT | Public methodological benchmark | Daily lag, quarterly SOFR target and reuse conditions |
| Treasury / NY Fed ACM / Cleveland expectations | Curves and separately labeled model decompositions | Timestamp and model-vintage comparability |
| CFTC / existing exchange/options owners | Slow positioning and qualified event risk | Publication lag, historical calendar uncertainty, reference-date differences |
| Public SDR / commercial inflation curves | Later transaction validation or specific curve coverage | Not an automatic smooth or executable curve; exact product and rights needed |
| ECB/BoE official surveys | Targeted subsequent geography | Publication schedules and target definitions differ |

Primary-source support and qualifications are in [W1–W25](EVIDENCE_REGISTER.md#w1).

**Source-rights correction:** public accessibility does not establish every intended archival, database, model, or redistribution use. Current FRED terms specifically address some proposed uses; their applicability must be reconciled against Mastermind's actual agreement/permission. Existing agreements were not inspected. Direct BLS/BEA statistical text/tables provide a better initial route to qualify. [W1](EVIDENCE_REGISTER.md#w1) [W2](EVIDENCE_REGISTER.md#w2)

No purchase or provider enrollment is authorized by this document. No cost estimate is treated as a quote.

### 13.2 LSEG versus Trading Economics: decide with the same sample

The supplied draft selected LSEG too early. Its documented polls history and revision features make it a strong candidate; TE's current PIT offering makes it a credible comparator. Vendor catalogues do not prove a particular contract/endpoint's historical information set. [W7](EVIDENCE_REGISTER.md#w7) [W8](EVIDENCE_REGISTER.md#w8)

The qualification packet should ask each candidate to demonstrate the same bounded cases:

1. A CPI event with at least two pre-event consensus snapshots and a later update.
2. A payroll event with contemporaneous prior values and multiple official revisions.
3. A rescheduled/corrected release or source-format anomaly.
4. Missing panel counts/dispersion and an explicitly missing consensus.
5. A historical as-of query that excludes later forecast corrections.
6. Source formation/publication, vendor availability, update timestamps and timezone precision.
7. Contributor identity/count, statistic definition, source rounding and suppressed values.
8. Original versus vendor-normalized first actual, including correction semantics.
9. Bulk/API delivery, rate limits, retention/replay permissions, downstream display and model uses.
10. A documented outage and recovery policy that cannot replace one evidence class with another.

“Historical series available” is not enough. Require actual returned sample IDs, timestamps, generations, and a reviewer-verifiable explanation of an as-of query. If arbitrary historical snapshots are absent but future capture is lawful, qualify **prospective capture only**.

Rank candidates first on required semantic/PIT/rights gates, then on measured total ownership cost and delivery fit. Existing entitlements can materially change the ranking. Do not buy two overlapping global products without an independently useful second role.

### 13.3 Public-data subtleties that affect the plan

SPF history is not homogeneous back to 1968. Historical release-date uncertainty, the retrospectively collected 1990Q2 survey, changing density targets/bins, and respondent-ID limitations require per-era admission. The current corrected workbook is not automatically the original public vintage. [W4](EVIDENCE_REGISTER.md#w4)

CME now documents an API with EOD and intraday delivery and extended historical availability. That corrects an old “no FedWatch API” assumption, but does not prove complete intraday original-vintage history or a license for Mastermind's exact consumers. [W12](EVIDENCE_REGISTER.md#w12)

BEA's 2026 GDP publication-format changes and warning about historical links that update to latest tables make archive/version identity an operational requirement. Design extraction around the actual published format and original archive, not an old PDF assumption. [W2](EVIDENCE_REGISTER.md#w2)

Use SF Fed USMPD first to replicate a bounded FOMC benchmark where permitted, before commissioning expensive raw-tick reconstruction solely to rediscover standard event-window facts. It does not replace a live policy-pricing input or the release-consensus lane.

### 13.4 Cost and deferral rules

Evaluate annualized source fees, history/backfill access, internal storage and redistribution rights, engineering effort, data operations, correction handling, model maintenance and reviewer burden. Current budget/entitlements are unknown, so a fabricated dollar budget or procurement winner would be false precision.

Defer continuous inflation-swap surfaces, proprietary global panel duplication, unrestricted option-density fitting, high-frequency positioning, and broad geographic rollout until a named consumer question and a discriminating benchmark justify them.

## 14. Implementation sequence

This sequence is a recommendation for a later commissioned owner. Each wave must recheck relevant source movement, active path custody and effect state. Unrelated repository movement alone is not a reason to restart the whole research.

### Wave 0 — Owner seam and source qualification

**Outcome:** a frozen, owner-reviewed MRI/RIC compatibility and source plan.

- Read current MRI/RIC contracts, the relevant open PR heads and actual publication/consumer paths. Distinguish model versions from publication-schema versions.
- Map all release/expectation/pricing fields to their owner, target, clocks and present consumer.
- Select exact production schema-extension/version policy; preserve the existing publisher and release identities.
- Classify the mixed expectation read accurately and specify the compatibility migration.
- Qualify direct official-source receipt use and one release-consensus candidate or an explicit NO_QUALIFIED_RELEASE_CONSENSUS result.
- Freeze intended replay mode, source manifests, pilot targets and acceptance matrix.

**Exit:** an exact changed-path proposal, dependency/custody resolution, source/rights findings, schema examples and negative cases. No source acquisition or production adapter is implied by catalogue research.

### Wave 1 — Extend actuals and temporal selection

**Primary paths:** existing release_actuals, release_target_truth, release_provenance, source adapters, and their existing tests.

**Outcome:** selected release bundles reconstruct first prints and multiple revision/correction edges without losing historical receipt identity.

- Reuse official-actual receipts and correct same-vintage target construction.
- Add missing per-observation publication/receipt/ready-time precision and explicit cutoff selection.
- Preserve agency revision versus erratum/vendor/internal correction distinctions.
- Keep existing defect gates and source-basis labels.
- Add deterministic replay digest and synthetic adversarial fixtures under existing test/evaluation ownership.

**Exit:** real official examples across qualified CPI and payroll targets plus the correction/timing negative matrix. The inspected MRI actual-target table does not include FOMC; policy facts require their separately qualified existing policy/RIC seam in Wave 4. Synthetic fixtures validate rules but do not prove source coverage.

### Wave 2 — Typed pre-event expectations

**Primary paths:** MRI source adapters and existing release composer; relevant model/context helpers.

**Outcome:** a lawful frozen economist baseline is distinguishable from each model, survey, and prediction-market observation.

- Add the source-qualified poll adapter with exact target and snapshot locking.
- Preserve missing consensus rather than filling it with model/prediction-market medians.
- Support panel summaries, and density payloads only where the source actually supplies them.
- Specify field-level freshness/fallback behavior and prospectively preserve admissible snapshots.
- Apply the existing prediction-market source interfaces with their contract and cutoff limitations.

**Exit:** reviewer can reproduce selected baseline IDs at multiple pre-event cutoffs; later updates cannot alter prior locks. If consensus access is not qualified, this wave remains incomplete for consensus even when the public-source foundation passes.

### Wave 3 — Reconcile publication and consumers

**Primary paths:** scripts/build_release_forecast.py, current release-forecast schemas, engine/event_window.py, and actual UI/context readers.

**Outcome:** the real emitted artifact and real reader agree on path, shape, units, timing, field semantics and missingness.

- Add typed comparisons through the existing publication path.
- Migrate the mixed expectation label without silently changing legacy field meaning.
- Repair/resolve the observed event-window path/shape and sigma-unit mismatch.
- Exercise the production-format producer fixture through the actual reader.
- Verify display and machine-context behavior for fresh, missing, stale, corrected, incompatible and contradictory cases.
- Preserve forecast-quality withholding and all score/gate/size/trade authority.

**Exit:** source tests plus a later authorized real producer/consumer proof. Mock-reader success alone is insufficient. This wave is the user-capability proof, not merely schema creation.

### Wave 4 — Pricing upgrade and survey enrichment

**Primary paths:** existing rate-futures, Fed-path, RIC and eligible survey/model adapter seams.

**Outcome:** market-pricing and survey context is typed and cutoff-safe. Qualify the official FOMC decision/statement fact and event-identity seam within the existing Macro policy/RIC ownership before admitting FOMC actuals. Do not assume MRI's current actual-target registry supports them. An unresolved policy-fact binding holds that specific capability.

- Reconcile the held policy-source/basis and matched-contract/roll work before modifying those paths.
- Qualify CME observations and retain method-implied probabilities with assumptions.
- Use MPT/USMPD as bounded reference checks, respecting horizon and publication differences.
- Add already-published SPF/SME/nowcast vintages for their proper roles.
- Reference Treasury/ACM/Cleveland outputs with model-vintage labels.
- Keep option-density reconstruction optional and separately estimated.

**Exit:** pricing invariants, calendar/roll/basis negative cases, source/reference timestamps, and demonstrated consumer interpretation. A complete density is not a mandatory output when inputs do not identify one.

### Wave 5 — Preregistered research and prospective shadow

**Owner:** existing evaluation owner with MRI/RIC evidence and MAS-118 only where incorporation science applies.

**Outcome:** a reproducible comparison answering the specified Study A/B/C/D questions.

- Freeze hypotheses, primary metrics, minimum useful effect, splits, source support and multiplicity policy.
- Run leakage/lineage tests before evaluating performance.
- Replicate a reference event-study slice; document any reconstruction differences.
- Accrue natural prospective receipts and compare published versus replayed states.
- Report negative, descriptive-only and insufficient-power results honestly.

**Exit:** exact code/data/method revisions, provenance and rights, accepted/rejected samples, out-of-sample results with uncertainty, operational failures, and family-by-family disposition. Passing this wave grants no trading authority.

### Wave 6 — Separate promotion decision

Only the existing decision/regime/evaluation owners, under a new applicable authorization, can consider scored or gated use. The candidate must meet the declared statistical and operational criteria, survive independence/coverage review, and define demotion and failure behavior.

A context-only family need not ever become a sizing input. This commission closes before that decision.

## 15. Acceptance, failure, and promotion gates

### 15.1 Distinct proof gates

| Gate | Required evidence | What it does not prove |
|---|---|---|
| **G0 Architecture** | Current owner map, explicit semantic contracts, collision resolution and versioned path plan | Source entitlement or implementation |
| **G1 Source** | Actual authorized sample, target mapping, cutoffs, corrections, rights/use decision and completeness statement | Live reliability or predictive value |
| **G2 Implementation** | Existing producer/reader integration, deterministic replay, adverse-case tests and preserved authority | Deployment or natural release capture |
| **G3 Operational** | Authorized natural-time receipt and consumer proof with timestamp/latency/outage evidence | Statistical generalization |
| **G4 Research** | Preregistered out-of-sample results and uncertainty, independence/coverage/cost review | Permission to score, gate or trade |
| **G5 Promotion** | Separate accepted owner decision and required deployment/demotion proof | Blanket authority for other families |

This research supplies the proposed G0 package and G1 qualification procedure. It does not assert that later gates have passed.

The operational pilot should include real examples from every admitted initial release family and repeat prospective observations. **Proposed minimum evidence:** two natural release bundles per initial family, plus the adverse-case matrix. This is an operational repeatability floor, not a statistical sample-size claim. If sources are only EOD, acceptance must describe EOD capability rather than intraday capability.

### 15.2 Required negative and boundary cases

The complete numbered acceptance specification is in [AUDIT_AND_ACCEPTANCE.md](AUDIT_AND_ACCEPTANCE.md#acceptance-specification). It covers:

- Missing, late, date-only and corrected expectation/actual inputs.
- Early dissemination, rescheduling, DST, unsupported policy calendars and effective-rate mapping.
- Multi-month revisions and cross-vintage payroll errors.
- Changing survey bins, open tails, respondent churn and zero disagreement.
- Mean-only futures data, invalid probability support, American exercise and quarterly-versus-meeting targets.
- Par-versus-zero rate calculations, model vintage leakage, quote/OI reference dates and contract roll.
- Real producer/reader path, shape, unit and authority invariants.
- Regime/outcome contamination, forward label maturity, source support and later-append replay stability.
- Source-rights and consumer restrictions.

### 15.3 Failure and demotion policy

Fail the affected field or use when targets, time, rights or methods are invalid. Preserve other independently valid context. Do not switch to a different class, vendor, instrument, generation or method without recording the explicit permitted fallback.

Reject a proposed implementation that creates a second macro regime, release/event owner, expectation truth store, residual engine, options plane, identity system, or publisher. Reuse the existing MRI/RIC/federation boundaries.

Retain descriptive-only status when incremental predictive value fails. Return INSUFFICIENT_EVIDENCE where sample limitations prevent a conclusion. Reject a commercial source when required rights, original-vintage fidelity or correction visibility cannot be qualified; prospective-only use remains a separately evaluated option.

Before any future authority promotion, require a predeclared operational demotion condition: source failure, stale/missing input, unsupported regime/target era, model drift or loss of calibration must never increase authority.

## 16. Bounded implementation handoff

**Proposed first commission:** MRI expectation semantics and point-in-time compatibility, Waves 0–3.

**Objective:** let a reviewer select a qualified CPI or payroll event and recover the official bundle, each pre-event baseline, its availability evidence, native-unit comparisons, corrections, and the actual emitted consumer view. Consensus must remain unavailable when its source is not qualified. FOMC facts and pricing are a separately qualified policy/RIC dependency in Wave 4; they must not be inserted into MRI's current actual-target table by assumption.

**Existing source owners:** MRI actuals/provenance/target truth, MRI release composer/publisher, the actual event-window/context readers. RIC/pricing changes belong to a separately reconciled bounded dependency; common expectation federation stays with MAS-119.

**Required entry checks:**

1. Repin current protected Mastermind procedure and relevant Macro source.
2. Resolve active MRI/RIC publication-schema and policy-pricing carrier custody; do not overwrite live or effect-unknown work. Do not infer schema custody from the v3_factor model's name.
3. Read the existing producer and actual consumer, preserve current defect/authority gates, and freeze the intended compatibility change.
4. Confirm exact source rights/entitlement and sample. Do not purchase or enroll a provider.
5. Freeze replay modes, cutoffs, target keys, schema version, source/fallback policies and acceptance IDs before production implementation.

**Permitted future implementation scope, only after that commission is assigned:** owner-native schema extensions, source-qualified adapters, receipt selection, typed derived comparisons, compatibility repair, relevant tests and research fixtures. No broad source-plane rewrite.

**Required return:**

- Exact source/branch/PR and method revisions.
- Before/after owner/consumer map.
- Source qualification and unresolved entitlements.
- Real and synthetic fixture identities clearly separated.
- Deterministic replay/correction/negative-case results.
- Real producer-to-reader evidence and, when authorized, natural-time consumer proof.
- Coverage/freshness/latency report.
- Unchanged downstream scoring and trading authority.
- Separate disposition of public actuals, economist consensus, market pricing and consumer proof.
- Exact next unblocked action and any held dependency.

**Held:** buying data; granting new model/source authority; regime retuning; sizing/trading; a universal expectation or gap score; duplicate macro/market-belief infrastructure; broad inflation-swap or global rollout; implementing MAS-119/MAS-118 on their behalf; claiming predictive success from a few examples.

The first owner decision is concrete: approve an extension of the existing MRI/RIC contracts and resolve their current carrier boundaries. The first data decision is equally concrete: qualify one lawful release-consensus channel or explicitly proceed with a partial public/model/pricing foundation. Neither requires pretending that the missing consensus or live proof already exists.
