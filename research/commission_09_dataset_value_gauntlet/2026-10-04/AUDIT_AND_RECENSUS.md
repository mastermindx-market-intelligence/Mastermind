# Commission 9 — Hardening audit and current-state recensus

**Date:** 2026-10-04  
**Disposition:** Retain the Dataset Value Gauntlet thesis; **do not execute the original implementation handoff unchanged**. The replacement plan is a use-specific qualification layer over existing owners, with measurement qualification and temporal admission before outcome access.  
**Capability delivered by this commission:** a completed research recommendation, source/collision census, discriminating synthetic counterexamples, and a bounded later implementation commission. No production capability is claimed.

Read the complete [masterplan](MASTERPLAN.md), [validation protocol](VALIDATION_PROTOCOL.md), [exact P0A implementation handoff](IMPLEMENTATION_COMMISSION_P0A.md), and [source register](SOURCE_REGISTER.md). This audit explains which premises changed and why.

## 1. What was audited

The input was the 1,465-line report `deep-research-report (20).md`, SHA-256 `cef7701ab7eaeeae6ff97240387027c2b043c3a2113fe55dbf4a3d373c6854df`, and the user's full Commission 9 mandate. The report's core question is sound: what information, prediction improvement, and economically useful decision change does a dataset add beyond the exact baseline already available?

The audit independently resolved repository identities; pinned current source; loaded protected procedures at one revision; inspected relevant Macro implementations and registry/temporal contracts; searched active adjacent PRs; read the newly protected Trend Persistence preregistration; checked primary methodological and vendor documentation; and evaluated three inspected mathematical expressions on synthetic data. The source register separates these activities from attachment-derived assertions and prior results merely reported by source documents.

The Mastermind audit pin was `521720b09be2921e996d9396b522b1c4ca62041c`. Publication-base refresh observed `17b9fa1363db6071d338be3373a4fdb11fc0076d`; the intervening 18-path managed-workspace change was disjoint from the loaded procedures and research dependencies. Macro was inspected at `e570025bf3921ac26c3bdcb06ad25303677f325d`; Terminal at `1c708450187755160e1a5889b69598a2fcb1f0d1`; Executive DR vault at `ea422c92bd29800d1f7fb3ae850236cc44d8c890`. Exact source identities and evidence ceilings are in [C01–C10](SOURCE_REGISTER.md#current-code-and-protected-research).

This is a **source and research audit**, not a fresh materialized-data census or current runtime certification. A compound remote inspection was refused and was not retried through another carrier. No current store counts, pipeline executions, portfolio byte comparisons, or “all feeds live” conclusions are invented to fill that gap.

## 2. Material corrections to the original report

| ID | Severity for implementing the original | Original premise or omission | Hardened correction |
|---|---|---|---|
| A01 | Blocker | Proposes a new `dataset_registry.v1` | That exact schema already exists in Macro Data OS. Reuse stable IDs and owner-native metadata; add qualification references, not a second registry. |
| A02 | Blocker | Proposes a new append-only Trial Ledger | Macro already has `engine/trial_ledger.py`. Extend its existing owner for integrity, attempts and exposure accounting. Do not fork research memory. |
| A03 | Blocker | Treats substantial existing statistics as sufficient qualification | Existing primitives contain demonstrated or inspected hazards. Introduce a primitive-qualification gate before they support acceptance predicates. |
| A04 | Blocker | Existing-data proof precedes the temporal/observability phase | Rights, source clocks, mapping vintages, price basis, correction handling, label maturity and holdout custody must be admitted before outcomes are read. |
| A05 | Blocker | Repeated final-holdout access may create a new generation | A new generation cannot unsee outcomes. Exposure follows the research family and information actually seen, not the branch/spec name. |
| A06 | Major | `known_at` blends source availability and actual system knowledge | Declare source-PIT reconstruction, actual-system replay or prospective evaluation. Do not globally redefine the existing temporal owner's clock. |
| A07 | Major | Broad LIVE/BUILT claims from code and documentation | Code presence, test presence, test execution, materialized history, consumer adoption and runtime proof are different evidence levels. |
| A08 | Major | Snapshot is described as merely unbuilt, without active ownership | Protected implementation is not established, but PR #673 has active draft implementation. Integrate through that owner, not a competing snapshot. |
| A09 | Major | Census repair is a new C9 infrastructure project | Commission 8 and existing Data OS/output-health owners own observability. C9 consumes qualified health/coverage receipts and records blindness. |
| A10 | Major | “Economic MDE” conflates economic value and statistical detectability | Specify economic threshold `delta_min` separately from power-based minimum detectable effect and the available independent sample. |
| A11 | Major | Raw and residual IC are presented as directly comparable | Current helper can use different names/dates and performs semi-partial residual ranking. Freeze common support and name the estimand correctly. |
| A12 | Major | Same portfolio state is required for all paired runs | Correct for a local decision experiment, not continuous closed-loop policy value. Closed-loop arms share initial state, then maintain separate state trajectories. |
| A13 | Major | Removing the candidate field isolates the dataset | Remove the full registered descendant path, including derived features, duplicate feeds, retrieval text, explanations and caches. |
| A14 | Major | Fixed LLM version/prompt establishes historical fairness | It does not remove future knowledge in model training. Historical modern-LLM tests cannot establish actual historical decision replay. |
| A15 | Major | No incremental statistical significance means kill | Distinguish demonstrated futility, insufficient power, use-specific redundancy, risk/event value, and cheaper noninferior replacement. |
| A16 | Major | Dataset-global advancement implies general authority | Qualify a dataset version for a particular use, universe, horizon, baseline/policy and rights scope. Data OS existence status and live authority remain separate. |
| A17 | Major | FactSet is effectively the preferred acquisition path | Retain a vendor-neutral estimates sample competition, including LSEG and S&P. No package, rights, correction guarantee or price was proven. |
| A18 | Major | Drawdown, policy contribution and source value are underspecified | Distinguish initial-capital MDD, entry-relative adverse excursion, local choice effects, retrained model effects, closed-loop effects and provider substitution. |
| A19 | Major | “Descriptive” missingness testing uses future returns | Return-conditioned missingness analysis is an outcome experiment, consumes the trial budget, and belongs after temporal admission. |
| A20 | Major | An IC-centric kill rule applies to every data family | Identity, operational reliability and required reference data can be valuable without return alpha. Apply the claimed-use test, not an indiscriminate alpha test. |

A01–A03 are grounded in [C02–C06](SOURCE_REGISTER.md#c02). A05 is reinforced by the newly protected [C1 exposure rules](SOURCE_REGISTER.md#c09). A08–A09 reconcile active [P01–P03](SOURCE_REGISTER.md#p01). The remaining entries are reasoned design corrections developed in this commission and specified in the replacement protocol.

## 3. Current-state census: what exists and what does not follow from it

| Capability | Current evidence | Classification for this audit | Consequence |
|---|---|---|---|
| Protected bootstrap/source law | Exact INDEX and required companions consumed; refreshed base compared | SOURCE_INSPECTED / governed | Preserve same-revision authority, path custody and research-only limits. |
| Dataset identity/metadata/DAG | Macro registry code and YAML; exact `dataset_registry.v1` schema | BUILT_NOT_PROVEN for current runtime adoption | Reuse; do not establish another dataset ID system. |
| Temporal profiles/PIT refusal | Macro temporal code with timezone refusal and source/replay distinctions | BUILT_NOT_PROVEN / source-specific adoption incomplete or unverified | Add explicit use-mode admissibility projections; do not overwrite the existing meaning of `known_at`. |
| Trial counting | Macro TrialLedger generation-time logging and DSR seam | BUILT_NOT_PROVEN; integrity gaps for stronger gate use | Existing owner must remain canonical; no performance evaluation after an unverified ledger write. |
| Research orchestration | `engine/lab.py` façade over shared primitives | BUILT_NOT_PROVEN | Extend through research-only profile/adaptation; default survivor loader is not a PIT-universe certificate. |
| Rank IC/HAC/BH/DSR/CRPS/RC-SPA | Inspected shared code | BUILT_NOT_PROVEN; several primitives UNQUALIFIED for proposed uses | Qualification is per primitive, input contract and inference claim. |
| Transaction cost/capacity | Single-asset next-bar engine and square-root impact option | PARTIAL for portfolio-level gauntlet requirements | Not a multi-asset constrained execution simulator; warm-up and missing-liquidity issues need owner disposition. |
| Mastermind earnings-expectation lane | Exact-pin consumer/test search excerpts | CODE_PRESENT; runtime/history unproven | Some expectations fields exist; no inference of mature historical broker-estimate vintages. |
| Historical analyst revisions | Original report, trend-protocol excerpt, adjacent estimates research lead | GAP_NOT_CLOSED by evidence reviewed | A representative licensed PIT sample and benchmark are still required. |
| PIT membership and price substrate | Current C1 preregistration identifies prior frozen inputs and their limitations | REPORTED_PRIOR_SUBSTRATE, not a new store audit | Membership, security identity, sector identity and terminal economic returns must be qualified independently. |
| Era-correct historical sectors/subthemes | C1 explicitly says sector snapshot `era_correct=False`; no new subtheme history proven | PARTIAL / unavailable for strong historical-control claims | Current sector labels cannot masquerade as historical controls. Forward capture is a distinct admissible path. |
| Decision Snapshot | Protected-tree search lacks candidate modules; draft PR #673 has code/contracts | SPEC_ONLY on inspected protected paths; ACTIVE_CANDIDATE_IMPLEMENTATION | Block canonical decision attribution pending protected qualified snapshot and actual consumer receipts. |
| Signal history/predictions/outcome learning/shadow books | Described by attachment and adjacent research; no current execution/data audit completed | ATTACHMENT_REPORTED / NOT_REQUALIFIED | Treat as integration candidates, not newly proven live components. |
| Static census freshness | Attachment says July 16 generation; no fresh store/census run here | HISTORICAL_REPORT_ONLY | Do not relabel its old counts as October truth. Consume Commission 8's qualified observability outputs later. |
| Terminal | Repository identity/protected revision resolved | IDENTITY_VERIFIED; consumer implementation not deeply inspected | Reader/projection role only; do not infer a competing outcome or portfolio owner. |
| Research Vault | Executive DR repo resolved; literal local alias not established | PARTIAL_IDENTITY_RESOLUTION | Do not claim a source corpus or fabricate an equivalence. |

`BUILT_NOT_PROVEN` here deliberately does not assert a fresh successful test run. It records code evidence with missing real-path proof. A field labelled PRODUCED in a committed registry also does not establish current freshness, completeness, rights, or predictive usefulness. [Registry source](SOURCE_REGISTER.md#c05).

### Original preliminary hypotheses reconciled

The report's broad list of price, fundamentals, options, themes, filings, news and macro data is retained as an inventory lead, not a newly measured live estate. The earnings-expectation lane has current source evidence. The lack of a mature analyst revision series was not closed. Fine-grained effective-dated subthemes were not found to be newly solved; even the current broad sector substrate has explicitly non-era-correct labels. Individual-stock institutional-flow history was not independently requalified and must not be promoted. Portfolio V3 remains an active dependency rather than a completed source of decision evidence. The strongest confirmed correction is architectural: existing data and research owners are more extensive than the original proposal recognized, but their existence does not eliminate measurement/adoption gaps.

## 4. Measurement red team

The same source that makes reuse attractive makes its qualification essential. The following are not reasons to build a rival statistics library. They are bounded findings for the existing owner.

### Confirmed expression-level counterexamples

The [synthetic receipt](SYNTHETIC_AUDIT_RECEIPT.json) records Python 3.13.5, NumPy 2.3.5 and pandas 2.2.3, exact source commit/blob, inputs, results and scope. No market data or holdout outcomes were used.

**SYN-01 — appending future prices changes an earlier impact input.** The inspected warm-up expression fills rolling-volatility gaps with the entire series' median. On an eight-price alternating prefix, early sigma is `0.011489841990803452`. Appending eight later volatile prices changes that same earlier sigma to `0.44432536067754225`. With fixed eta `0.1` and participation `0.01`, the per-unit-turnover impact rate changes from about **1.15 basis points to 44.43 basis points**. This proves failure of prefix invariance in the inspected expression. It does not quantify damage to a real backtest or prove that every consumer enables this optional impact branch. Required later proof: appending any future suffix cannot alter already-admissible historical cost inputs; initial insufficient data must be explicit rather than filled from the future.

**SYN-02 — initial loss disappears from standalone maximum drawdown.** For returns `[-0.20, +0.10]`, the inspected `_maxdd` expression reports `0.0`; including initial wealth `1.0` gives `-0.20`. It initializes the running peak after the first return. This affects the claim for arbitrary return paths, including resampled paths; it does not prove that every full engine trajectory starts with a nonzero loss. Required later proof: initial capital, recovery, zero-length, bankruptcy and subperiod-start conventions are explicit and consistent between labels and reported risk.

**SYN-03 — singular-design pseudo-inverse is not conventional VIF.** Two identical nonconstant 40-row columns produce diagonal values near `0.25` from the inspected pseudo-inverse. Perfect collinearity instead makes conventional VIF infinite or undefined. This is a discriminating reason not to accept that output as an independence gate. Required later proof: singular/near-singular design is surfaced, not reported as unusually low collinearity.

These are three successful *defect demonstrations*, not three repaired production tests. The helper implementations were not changed.

### Additional code-inspected risks, not execution-proven defects

| Finding | Inspected mechanism | Required owner qualification |
|---|---|---|
| Missing liquidity may become zero impact | Nonpositive/missing ADV can become missing participation and then zero | Missing-cost state must not equal free execution; use approved conservative bounds or abstain. |
| Raw/residual IC support differs | Raw IC is appended before controls are checked; residual IC uses only controls-present subsets | Same sample manifest for every paired comparison; report deployment coverage separately. |
| Partial-rank interpretation is too broad | Raw-space OLS residual is ranked against an unresidualized target | Name semi-partial diagnostic; distinguish rank-residual partial association and OOS forecast value. |
| Default OOS benchmark can use immature labels | Expanding realized-label mean is shifted one row, not necessarily the label horizon | Explicit benchmark computed only from labels mature by each forecast cutoff. |
| CRPS missing-forecast alignment | Forecasts with `None` are filtered, then resulting values are zipped against original outcomes | Preserve row keys through candidate and climatology scoring; missing forecasts cannot shift target alignment. |
| DSR effective-size floor is heuristic | Effective sample size is clamped to at least 30 | Do not interpret this as proven information content or an automatic gate under severe dependence. |
| P-value precision | HAC results are rounded before downstream use in some paths | Store unrounded machine statistics for gates; round presentation only. |
| Fixed-row purge is not full temporal validation | Some helpers trim trailing rows or construct combinations including future groups | Validate actual event/label intervals and chronological deployment estimands separately. |
| Ledger read/write failure can alter counts | Read failures skipped; in-memory dedup updated before successful append | Durable-before-evaluation receipt, corruption failure, restart/retry and concurrent-writer proofs. |
| Same config is not same attempt | Content dedup can suppress repeated configuration records | Retain every attempt/exposure and outcome generation without falsely increasing distinct-config count. |

These observations follow [C02–C03](SOURCE_REGISTER.md#c02). They are not presented as a complete security, numerical, or concurrency audit of either module.

### Inference claims requiring restraint

Existing RC/SPA comments report earlier finite-sample over-rejection for short autocorrelated panels. That is source-reported validation evidence, not a fresh run here. It reinforces the need for null-size and power checks matched to the intended cohort design. Simply reducing a nominal threshold to `0.02` is not a general repair. Similarly, a `(1 + exceedances)/(B + 1)` Monte Carlo correction avoids zero-resolution/tie mistakes; it does not make every fitted block bootstrap an exact finite-sample test. The report must not turn a DSR value into a posterior probability that alpha exists. [C02](SOURCE_REGISTER.md#c02), [W01](SOURCE_REGISTER.md#w01), [W05–W07](SOURCE_REGISTER.md#w05).

## 5. Holdout and historical-identity findings that change the plan

The protected C1 preregistration explicitly states that the Trend family has already seen its historical panel. Formation dates `2022-07-06` through `2026-06-02` were previously used as V2 holdout and B2 test. C1 treats old dates as development and requires later forward dates for new confirmation. Commission 9 must preserve those restrictions; it cannot lease the same outcomes under a newly named dataset experiment and call them unseen. Neither the preregistrations nor their pinned modules/results are to be edited or rerun in this commission. [C09](SOURCE_REGISTER.md#c09).

C1 also states that its sector labels are as-of-current, with `era_correct=False`. That establishes an important distinction: historical index membership does not establish historical sector identity, much less dynamic fine-grained subtheme identity. Historical sector-neutral claims must either qualify era-correct mappings, restrict the estimand explicitly, or remain developmental. Newly captured forward labels may become usable at future cutoffs; they do not repair the past.

The source's prior result sequence is itself instructive: an apparent drawdown relationship did not establish incremental model value against a stronger volatility-aware baseline. This audit uses that sequence only as a **reported prior example** of why raw significance is not dataset value. It has not reopened the original results to produce another claim.

## 6. Research landscape corrections

Public API history is not the same as complete original-vintage replay. SEC filing acceptance, public dissemination, vendor availability and internal receipt must not be conflated. FRED vintage dates are useful but date-level release information does not establish precise intraday availability. Analyst estimate suppliers must prove exact contributor/consensus history, correction semantics and rights, not merely a product history start year. [W12–W18](SOURCE_REGISTER.md#w12).

Market-data timestamp precision also deserves skepticism. Databento documents real cases where legacy history or generated snapshots do not have genuine historical capture timestamps. A field named `ts_recv` cannot override its quality flags and source provenance. For bars, an event timestamp at bar start does not permit consuming the final OHLCV then. These are source-specific counterexamples to the original blanket confidence in timestamp-rich products. [W19–W20](SOURCE_REGISTER.md#w19).

No vendor was contacted, no sample obtained, and no current price or contract rights were proven. Analyst revisions remain a plausible candidate because the gap is strategically relevant, not because the audit established their incremental value or selected a supplier.

## 7. What the replacement changes operationally

The first later implementation should produce a **nonbinding qualification packet** that resolves existing dataset IDs, states its replay mode, records the relevant source/rights/coverage/primitive gates, and demonstrates refusal of invalid cases. It should operate on synthetic fixtures only. It must not manufacture a positive market outcome to prove that the framework works.

The next outcome-bearing commission becomes eligible only after those gates are accepted and lawful data and untouched evaluation cohorts are actually available. Decision-level work additionally requires the existing Snapshot owner to be protected and qualified on the real read path. Production promotion remains a separate decision by the existing portfolio owners. A research scorecard is evidence for that decision, never the mechanism that grants authority.

## 8. Completion boundary

The research commission is complete when this packet is published with its immutable source references, all A–L requirements, explicit audit limitations, synthetic receipts and executable-for-a-later-owner handoff. It does **not** require claiming that the proposed gauntlet is built, that a vendor is worth buying, that all data feeds are live, or that future shadow evidence already exists.

Outstanding implementation/research gates are concrete: qualify or repair the named existing primitives through their owners; obtain admissible source/identity/correction and rights evidence for each proposed use; preserve organization/family outcome exposure; qualify the canonical Snapshot/consumer path; obtain lawful representative samples and economics before procurement. The literal Research Vault alias and attachment-only runtime assertions remain unresolved rather than guessed.
