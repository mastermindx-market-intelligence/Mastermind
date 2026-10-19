# Issuer Inflection Intelligence — validation and acceptance contract

**Revision 2 · 2026-10-03 · Proposed policy for W0 ratification, not measured I3 results.**  
Read with the [masterplan](../../../docs/superpowers/plans/2026-10-03-issuer-inflection-intelligence-program.md) and [audited research](../../ISSUER_INFLECTION_INTELLIGENCE_DEEP_RESEARCH_2026-10-03.md). Existing source-owner gates remain controlling; this document cannot loosen them.

## 1. Four questions, four separate verdicts

| Track | Question | Evidence of success | What it does not prove |
|---|---|---|---|
| R — Reconstruction | Did the system preserve what was available, to whom, at the requested cutoff? | Reproducible identities, source spans, periods, rights, timestamps, revisions and explicit refusals | Correct economic interpretation or useful predictions |
| C — Classification | Did the frozen rule describe the measured economic/reporting change correctly? | Independent adjudicated labels, comparable inputs, conditional semantics, error/coverage analysis | Causality, investment value or broad generalization from a narrow corpus |
| U — User utility | Does composition improve analyst decisions about the evidence? | Source-correct task answers and useful monitoring, versus credible baselines | Future returns or trading authority |
| P — Prediction | Does a named feature improve a specified future outcome beyond admitted baselines? | Leakage-controlled prospective/walk-forward evaluation with uncertainty, costs and multiple-testing discipline | Automatic promotion into Prophet money paths |

No aggregate success score may substitute for these verdicts. Engineering deployment, classification accuracy, analyst speed and investment returns are different outcomes. Missing labels or unmatured outcomes are not zero-valued outcomes.

## 2. Preregistration and experiment identity

Before inspecting validation/holdout bodies or outcomes, persist through the existing Research/Brain owner:

- research question, hypothesis and falsifier; feature/rule ID, exact definition and version;
- source scope, rights-purpose profile, issuer/security mapping and timestamp-precision law;
- population eligibility and exclusion reasons, minimum history, strata and preselected sample/split rule;
- outcome definition, horizon, observation clock, treatment of missingness, revisions, delistings and censoring;
- development/validation/holdout identities and source revision families; prior analyst/model exposure to named cases;
- baselines, primary metric, smallest decision-useful effect, uncertainty method, power/sensitivity analysis and stopping rule;
- full registered family of tests and chosen multiplicity control; ablations and sensitivity checks marked secondary;
- intended consumers, authority restrictions, immutable method/code hashes and exposure/outcome owner references.

An amendment creates a new version with reason and prior-result visibility. It cannot silently replace the trial being graded. Any validation case used to repair a method becomes development evidence for that amended method; a fresh holdout is needed. E3's existing sealed eight-revision corpus is **not** an I3 corpus to open. Do not reuse another program's untouched-OOS label for a case this program has already inspected.

Capture begins with W1, not after launch: admitted input revisions, requested cutoff, emitted or reconstructed mode, method, resulting transition or refusal, exposure, later corrections and outcome readiness. Reuse existing lifecycle/ledger owners after a fit decision; a new research JSON file is not by itself a canonical production outcome service.

## 3. Corpus design

### 3.1 Development cases and their purpose

| Case family | Why it exists | Mandatory challenge |
|---|---|---|
| Accepted AAPL FIF/event packages | First deterministic vertical and exact identity/period evidence | A1/A2 unlinked comparative must remain NOT_EVALUABLE; filing accession must not be confused with event accession |
| P&G / CDV-1 private fixtures | Reuse already-built price/volume/mix and reported/core interpretation | Combined volume/mix cannot become pure volume; private context cannot leak publicly |
| Semiconductor / channel cycle | Demand versus sell-in, inventory and capacity timing | Channel fill/destocking can decouple revenue and end demand; capex is not automatically favorable |
| SaaS | Recurring revenue, bookings/RPO/deferred revenue and retention | KPI definition and billing-duration changes can invalidate comparisons |
| Industrial/backlog | Orders, lead times and price/cost mix | Backlog growth may reflect price, acquisitions or cancellations rather than volume |
| Homebuilder / IMCE development evidence | Orders, cancellation denominators, incentives and calendar mismatch | NVR/other business models and differing cancellation denominators cannot be pooled mechanically |
| Bank / financial institution | Deliberately different balance-sheet economics | Industrial DSO/DIO/DPO is not applicable; do not force a generic model |
| Consumer price/mix | Pricing versus units and cash conversion | A headline revenue gain can coexist with declining volumes or weak cash |
| Acquisition-heavy issuer | Reported versus organic perimeter | Do not subtract an invented acquisition/FX bridge |
| FPI / 6-K | Nonstandard cadence, currencies, bilingual or differently structured evidence | Do not assume US quarterly disclosure cadence or transcript roles |
| Restatement/reclassification | Historical knowability and revisions | The original as-known result remains reproducible after correction |
| Financing stress / dilution | Capital flexibility and obligations | Authorization, actual issuance, proceeds, cash and share basis remain distinct |
| Guidance/commitment reversal | A discrete transition that need not await multiple quarters | Compare the same target period and conditions; absent actuals are not a missed commitment |
| Failed turnaround / cyclical false turn | Negative examples and base effects | Do not pick only survivors or label a single rebound durable |
| Durable reacceleration | Positive case that is not merely high static growth | Must distinguish level, rate, change in rate and supporting evidence |

These are required failure-mode families, not a claim that all named data are already admitted. W0's corpus manifest must bind real issuer/event/revision IDs, rights and availability. A synthetic fixture is useful for an invariant but does not satisfy real-issuer coverage. A known historical winner or an IMCE case already studied is development evidence regardless of where a file is stored.

### 3.2 Split and labeling rules

Split by issuer/time/source-revision family, not random extracted rows. Keep amendments, syndicated copies, dual-class events and repeated comparisons sharing a load-bearing filing in the same leakage group. Use temporal holdout and issuer holdout where coverage permits; report each separately. Do not use today's index/peer membership to decide historical eligibility.

Two source-qualified annotators independently label the frozen validation/holdout material without future price outcomes or the candidate output. Resolve disagreements with a third adjudication or retain an unresolved label. Record agreement, label confidence and reasons. Missing or ambiguous evidence must remain a valid label, not be coerced into positive/negative.

Count both unique issuer-event units and dependent comparisons. Repeated questions about one filing are not independent observations. Statistical intervals and resampling must respect issuer/event/time-block dependence. Small strata remain underpowered even when pooled totals look impressive.

A historical LLM-generated interpretation is not automatically PIT-clean: a model can know future facts from pretraining. Source-only prompting and blinded evaluation reduce but do not prove absence of that contamination. Treat such historical results as exploratory unless the claim can be deterministically reconstructed from the allowed evidence; prioritize prospective frozen emissions for predictive claims.

## 4. Arithmetic, time and security invariant suite

Every case below needs a positive control, the stated negative mutation and an assertion on the actual emitted/withheld object. Naming a fixture after a failure is not proof that the failure was exercised. Mutation testing must distinguish a forbidden implementation from the accepted one; equivalent mutants are documented rather than counted as killed.

| Test | Mutation / challenge | Required behavior |
|---|---|---|
| T01 | Ticker reused by another issuer or dual-class event duplicated | Canonical issuer resolution refuses ambiguity; one issuer event, distinct securities |
| T02 | FIF entity ID treated as CIK/company ID | Reject unsupported crosswalk rather than joining by string similarity |
| T03 | Quarter substituted for YTD, duration for instant, or different fiscal length | NOT_COMPARABLE/NOT_EVALUABLE with the specific reason; no arithmetic result |
| T04 | Values share a period but come from unlinked revised vintages | Refuse comparison unless the positive cutoff-visible lineage receipt exists |
| T05 | Later restatement substituted into an earlier as-known query | Earlier input/result hashes unchanged; corrected-now mode explicitly differs |
| T06 | Date-only or timezone-ambiguous timestamp coerced to midnight UTC | Preserve precision/interval and withhold unjustified intraday knowability |
| T07 | Earliest source time replaces latest load-bearing input availability | Derived claim cannot appear before the full sufficient evidence set is available |
| T08 | Historical reconstruction labeled as a live emitted alert | Reject mode/clock inconsistency; retain actual emission time |
| T09 | Offline break date used as online detection date | Separate estimated onset and detection; no look-ahead leakage |
| T10 | Zero/negative/near-zero denominator, unit or scale mismatch | Owner-approved absolute comparison or typed refusal; never infinity/NaN/fake percentage |
| T11 | Margin pp/bp confused with relative percent change | Exact unit-aware representation and rounding oracle |
| T12 | YoY acceleration computed without all required periods | Preserve observed growth, withhold unsupported acceleration |
| T13 | FX/M&A/segment/KPI definition discontinuity without a bridge | Report the observation and comparability limitation separately |
| T14 | Bank given industrial working-capital ratios; DPO proxy unlabeled | Sector/definition refusal or explicitly approved proxy, never generic validity |
| T15 | Combined volume/mix treated as independently measured volume | Reuse CDV-1 refusal law; do not invent decomposition |
| T16 | Same disclosure copied across three sources counted as corroboration | One dependence group; confirmation breadth does not increase |
| T17 | Missing demand/cash/consensus rendered as neutral or adverse fact | Typed absence; no invented economic sign, beat/miss or confidence |
| T18 | Guidance for next year compared with prior current-year target | Reject mismatched target-period/condition comparison |
| T19 | Roleless/incomplete transcript produces a sourced management answer | Source-conditioned refusal; no hallucinated role or loosened E3 gate |
| T20 | Private source embedded in public summary/export/cache | Rights intersection denies all derived leakage paths |
| T21 | Permission revoked while cached generation remains | Re-evaluate rights and invalidate/withhold derivatives under owner policy |
| T22 | Shelf authorization treated as actual issuance/proceeds | Distinct event/state classes; no financing arithmetic outside Capital owner |
| T23 | Current peer membership or incomplete peers used historically | Withhold unsupported historical/issuer-specific conclusion; show coverage |
| T24 | Correction arrives between read, compile and publish | One coherent source generation or explicit retry/reconciliation; no mixed snapshot |
| T25 | Crash or duplicate retry after publication/delivery | Idempotent object identity and duplicate suppression; reconcile uncertain effects |
| T26 | Malformed/oversized payload, forged owner hash, malicious source URL | Bounded validation and existing safe resolver; no arbitrary execution/fetch |
| T27 | Filing text instructs the model to ignore policy or expose data | Treat text as evidence only; deterministic facts/rights/authority unchanged |
| T28 | Consumer drops authority flags or treats research sorting as portfolio rank | Reject widening; shadow cannot influence rank/gate/size/entry/exit |
| T29 | All eligible rows are refused but UI says “no changes” | Coverage-aware unavailable/degraded state, never successful empty intelligence |
| T30 | Method/version or reference order changes without content change | Frozen canonicalization and identity rules; semantic change requires a new version |

Do not edit frozen upstream tests to make a new adapter pass. Report incompatibility to the owning wave with a discriminating test. I3 tests add coverage; they do not retroactively authorize source behavior.

## 5. Acceptance gates and denominators

The following quantitative targets are **proposed release policy**, not conclusions derived from the literature or results observed in this audit. W0 must ratify or revise them with a reason before validation bodies/outcomes are inspected. Changes afterward require a new trial version and fresh holdout; “underpowered” must not be converted to “passed.”

### G-R — reconstruction and authority

All emitted assertions must have valid canonical input references, permissible clocks, applicable comparability/definition rules and allowed rights. Required P0 invariant and mutation tests must show zero accepted wrong-issuer, future-input, forbidden-rights or money-path-authority cases. This is an invariant-suite gate, not a claim of zero population risk.

Deterministic components must reproduce byte-identical canonical payloads from the same frozen inputs/method; optional LLM prose is stored separately and never changes deterministic truth. Every specified refusal case must return the exact reason family, and every positive control must still succeed. Always-refuse implementations fail.

### G-C — economic classification

On the independently labeled validation set, proposed overall precision is at least 95% and recall at least 80% for the supported qualified-change classes, with a dependence-aware 95% lower precision bound of at least 85%. Require at least 100 predicted-positive and 100 adjudicated-positive issuer-event units before claiming the pooled gate is adequately observed; record the number of independent clusters and retain an underpowered verdict if dependence defeats that inference.

Report per-family confusion, refusals, coverage and uncertainty; an aggregate pass cannot license an untested sector. For each claimed stratum, require real positive and negative controls and enough observations to justify its declared scope. Rare discrete financing events need a separate population/outcome design, not forced pooling into common quarterly growth cases.

The evaluable denominator is determined independently from admitted source availability, minimum history, definitions and rights. Proposed minimum reconstruction coverage is 80% of that predeclared supported/evaluable universe. Rights-denied and unsupported-source counts remain visible outside that denominator; they cannot be hidden to advertise market-wide coverage. Compute missed-change rates on the sampled eligible universe, not only emitted alerts.

### G-U — analyst utility

Use counterbalanced/randomized tasks with disjoint case assignments where possible. Baselines: (B0) a static latest financial/context view; (B1) simple same-basis deltas; (B2) source-cited event summary; (B3) full I3 composition. Ablations remove contradictions, peer context or longitudinal commitments one at a time.

Primary outcome is source-correct answer quality on a prewritten rubric. Proposed usefulness threshold: at least a 10-percentage-point improvement over the strongest baseline, with a dependence-aware interval excluding no improvement. Secondary targets: at least 20% lower median time to a correct answer and no increase in material unsupported conclusions. These are policy choices to justify before the trial, not promises.

Task mix includes identifying actual changes, refusing incomparable claims, finding contrary evidence, locating first support, recognizing corrections and choosing the next discriminating observation. Measure missed changes, false-alert burden, evidence navigation errors and user confidence calibration. Blind adjudicators to interface assignment when grading answers. Preselect sample size using a pilot that is not reused as the confirmatory evaluation; do not invent statistical power from task count alone.

### G-O — operational/product release

Meet the ratified support matrix and latency/payload/cost budgets from the masterplan. Demonstrate real owner→publisher→immutable generation→authorized reader→browser→machine-consumer continuity. Fixture/mock API tests are necessary but insufficient. Verify unsupported/stale/rights-denied/loading/corrected states, keyboard/focus and responsive behavior, correct source links and stable back/close navigation.

At least one real eligible source update and one genuine source-correction case must traverse the complete supported path. A historical correction replay can test transport and correction semantics when explicitly labeled replay; it does not become a natural live correction or override a source owner's natural-cycle gate. Capital W2C/W2D still requires its specifically prescribed natural chain. Release canary and broad release remain separate records.

### G-P — prediction and shadow

There is no universal required alpha threshold in this plan. Before a feature trial, specify the economically meaningful target and power/sensitivity assumptions appropriate to its frequency, horizon and intended use. At minimum compare: static fundamentals, simple financial deltas, and existing price/technical/theme context. Report incremental value, not standalone correlation.

Separate future fundamental outcomes (for example, same-definition volume or margin change at a fixed future report) from market outcomes. Market studies require exact executable timing, trading calendar, security/share-class identity, corporate actions, delistings, benchmark, overlapping-horizon treatment, realistic costs and cohort/regime analysis. Guidance published after close cannot earn the preceding close-to-close return as attainable performance.

Use walk-forward or prospective evaluation, train-only normalization/model fitting, embargo/purging where outcome windows overlap, and issuer/event/time-block uncertainty. Register all tried feature definitions and control the chosen hypothesis family using a declared procedure such as Holm for confirmatory claims or a justified false-discovery-rate method for exploratory screens. Report effect sizes, intervals and negative results; a lone favorable p-value is not promotion evidence.

Controlled shadow requires safe frozen inputs and isolation from decision paths, **not already-proven predictability**. Grade maturity as collecting, mature-underpowered, rejected, promising-for-further-study or eligible-for-explicit-promotion-review. A named promotion still requires the existing authority owner's recorded decision; no combined Issuer Inflection Score is allowed.

## 6. Release evidence packet

Each wave return must include immutable source/base/head identities; exact source/rights/definition revisions; changed paths and owner grants; new versus reused contracts; test invocation/environment and full outcome; discriminating negative controls; corpus/exposure hashes; actual producer/consumer transport evidence where owed; remaining coverage limits; cost/latency observations; independent review disposition and unresolved effects.

Keep **author-reported**, **audit-reproduced**, **fixture-proven**, **owner-record-attested live** and **fresh production-proven** separate. A green unrelated CI job is not the required proof. An inferred owner, historic Slack message or stale Linear status cannot close a runtime gate.

## 7. Results actually available from this audit

Only the pre-existing CDV-1 interpretation component was executed here. Against Macro `7ce8e6dfaaa8b8effed2430e069e1efe73e47fa6`, its existing `tests/test_earnings_economic_interpretation.py` passed **427 tests in 31.11 seconds**, exit code 0, on Python 3.14.7 in an isolated source snapshot.

Two earlier isolated-snapshot attempts were invalid harness runs: one omitted `engine.press` and failed collection; the next omitted `config/fundamental_forensics_disclosure_diff.v1.json`, producing 346 failures and 81 passes. Restoring the exact same-pin import/registry files, without editing source or tests, produced the final pass. All three attempts are retained in the audit manifest so the final pass does not erase the failed setup evidence.

This was not the original Python 3.12.14 release environment, not the full earnings-economic-dossier CI gate, not a new I3 test suite, not a production replay, not cross-issuer validation and not an investment backtest. **None of G-R/G-C/G-U/G-O/G-P for I3 is claimed passed by this documentation update.**
