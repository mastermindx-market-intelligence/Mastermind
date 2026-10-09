# Commission 9 — Source register and evidence boundaries

Audit date: **2026-10-04**. This register supports the complete hardened report, not a production qualification. Repository links are immutable. Public documentation was checked during this audit; a product page is not a licensed sample, service-level agreement, or rights opinion.

## Evidence classes

`SOURCE_INSPECTED` means the identified source text or code was read. It does not mean a function was executed, a dataset was materialized, or a production consumer used it. `SYNTHETIC_EXPRESSION_PROOF` means the exact inspected expression was evaluated on artificial inputs in the conversation sandbox, not that the repository test suite passed. `CANDIDATE_RESEARCH` is an unmerged proposal. `REPORTED_PRIOR_RESULT` is a finding stated by an existing document, not independently reproduced here. `VENDOR_DOCUMENTATION` establishes only the published capability claim. `RECOMMENDATION` identifies this commission's own design or inference.

## Repository identity and source custody

| Estate | Repository and branch | Audit revision | Observed branch protection |
|---|---|---|---|
| Mastermind | `mastermindx-market-intelligence/Mastermind`, `master` | `521720b09be2921e996d9396b522b1c4ca62041c` | Protected |
| Macro | `mastermindx-market-intelligence/macro`, `main` | `e570025bf3921ac26c3bdcb06ad25303677f325d` | Branch API reported unprotected; this is not permission to bypass source law |
| Terminal | `mastermindx-market-intelligence/mastermind-terminal`, `master` | `1c708450187755160e1a5889b69598a2fcb1f0d1` | Protected |
| Executive DR vault | `mastermindx-market-intelligence/executive-dr-vault`, `main` | `ea422c92bd29800d1f7fb3ae850236cc44d8c890` | Branch API reported unprotected |

Mastermind advanced during the audit to `17b9fa1363db6071d338be3373a4fdb11fc0076d`. A native GitHub comparison established one intervening commit and 18 changed paths in managed-workspace documentation, Studio integration, workspace CLI, and associated tests. No loaded `docs/sol_skills` procedure, Commission 9 source path, or Trend Persistence preregistration changed. This is the publication base; the earlier immutable research citations remain valid. [Exact comparison](https://github.com/mastermindx-market-intelligence/Mastermind/compare/521720b09be2921e996d9396b522b1c4ca62041c...17b9fa1363db6071d338be3373a4fdb11fc0076d).

The repositories were resolved through authenticated repository/branch metadata and observed Git remotes, not inferred from folder names. The existence of `executive-dr-vault` does **not** prove that it is the same estate as the prompt's literal local name “Research Vault.” That alias remains unresolved. Terminal and vault checks establish identity/source revision, not a deep audit of their current runtime consumers or private corpus contents.

## Current code and protected research

### C01
[Mastermind INDEX at the audit pin](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/docs/sol_skills/INDEX.md).

Same-revision `COLD_START.md`, `ACTIVE_EXECUTION.md`, `SESSION_RELIABILITY.md`, `REVIEW_RETURN.md`, and `CLOSEOUT.md` were consumed. Skillpack schema `mastermind.sol_skillpack.v1`, version `1.0.1`, minimum bootstrap major `1`. The governing procedures were not edited. Principal research judgment and direct native GitHub publication were used; no worker dispatch or execution authority is inferred.

### C02
[Macro validation primitives](https://github.com/mastermindx-market-intelligence/macro/blob/e570025bf3921ac26c3bdcb06ad25303677f325d/engine/validation.py).

Blob: `e9bbe0e77ae571b62a9f5b8b8e4e7a950c035399`. Inspected regions include lines 1–480 and 600–1180: next-bar backtest/costs, capacity, DSR/effective sample size, purged/combinatorial folds, drawdown, calibration/VIF, rank IC, HAC, BH, CRPS, OOS forecasts, cross-sectional residualization, and RC/SPA preparation. The audit does not claim a full-module proof or full-suite run. Three expression-level counterexamples are in `SYNTHETIC_AUDIT_RECEIPT.json`.

### C03
[Existing Macro TrialLedger](https://github.com/mastermindx-market-intelligence/macro/blob/e570025bf3921ac26c3bdcb06ad25303677f325d/engine/trial_ledger.py).

Blob: `eb364fe9fa53f46d0455e194d3e3ccdbb5732778`. Lines 1–220 inspected. Existing generation-time configuration accounting, JSONL persistence, family identity, deduplication, declared budgets, and DSR interface must be reused. Silent malformed-line/read-error tolerance, in-memory-before-durable-write ordering, and process-local locking require qualification for stronger admission claims.

### C04
[Macro Data OS registry implementation](https://github.com/mastermindx-market-intelligence/macro/blob/e570025bf3921ac26c3bdcb06ad25303677f325d/lib/dataos/registry.py).

Blob: `91c4a8eed34b118902dd2a80678b71472e328dca`. Lines 1–175 inspected. Stable dataset identity, owner, producer, grain, temporal profile, source status, schema, licensing, and static input DAG already have an owner.

### C05
[Macro dataset registry](https://github.com/mastermindx-market-intelligence/macro/blob/e570025bf3921ac26c3bdcb06ad25303677f325d/config/dataset_registry.yml).

Blob: `70a08e25ea45927bed001b3cb1c48e286680525e`. Lines 1–160 inspected. It already declares **`schema: dataset_registry.v1`**. The `updated: 2026-09-20` field is registry metadata, not proof of current feed health. Price-basis, ticker-identity, and adjustment-vintage warnings in this registry constrain downstream historical claims; its historical measurements were not rerun.

### C06
[Macro temporal implementation](https://github.com/mastermindx-market-intelligence/macro/blob/e570025bf3921ac26c3bdcb06ad25303677f325d/lib/dataos/temporal.py).

Blob: `094b149a8b9158f19cb99c4005568c12db96ed41`. Lines 1–210 inspected. Profile-specific clocks, timezone refusal, and recomputation-versus-replay distinctions already exist. Commission 9 must map to these semantics rather than globally redefine `known_at`.

### C07
[Macro temporal standard](https://github.com/mastermindx-market-intelligence/macro/blob/e570025bf3921ac26c3bdcb06ad25303677f325d/research/MASTERMIND_TEMPORAL_DATA_STANDARD.md).

Blob: `74d3d389648875d6c53b08dedbc0b82de21a0134`. Lines 1–160 inspected. This August-dated standard documents earlier latest-vintage historical-fitting/adoption defects and distinguishes them from a current-state read. Its old record counts and caller census are **reported historical evidence**, not current runtime measurements from this audit.

### C08
[Existing Strategy Lab façade](https://github.com/mastermindx-market-intelligence/macro/blob/e570025bf3921ac26c3bdcb06ad25303677f325d/engine/lab.py).

Blob: `430a074000ac259d199ec48c20842d784f611866`. Lines 1–120 inspected. Thin orchestration over shared mathematics and TrialLedger already exists. Its default stock loader explicitly declares survivor-universe limitations; it is not a universally admissible historical universe.

### C09
[Protected Trend Persistence C1 preregistration](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/research/TREND_PERSISTENCE_PREREG_C1.md).

Blob: `8f280bd41430dc0b49551783a1066b42b068ce8d`. Lines 1–160 inspected. PR #1226 was observed merged. This source explicitly identifies previously exposed formation dates, freezes new forward confirmation, reports the earlier incremental-model null, and states that its sector snapshot has `era_correct=False`. Those prior statistical results and corpus counts were not independently rerun here. No V2/B2 result file, sealed outcome panel, or market-outcome experiment was opened or executed by this audit.

### C10
[Mastermind earnings-expectation consumer](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/portfolio/held_risk.py) and [test references](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/tests/test_held_risk.py).

Exact-pin indexed excerpts establish the lane and its test references, not a production execution receipt or mature historical estimate-vintage panel. [Trend protocol](https://github.com/mastermindx-market-intelligence/Mastermind/blob/521720b09be2921e996d9396b522b1c4ca62041c/research/TREND_PERSISTENCE_PROTOCOL.md) also surfaced the historical-revisions gap. Search excerpts were used at their actual evidentiary strength.

## Adjacent work and collision census

### P01
[Mastermind PR #673](https://github.com/mastermindx-market-intelligence/Mastermind/pull/673), observed **open Draft**, head `0b960590c77101b3f3b5545896423f9ad07b7d56`.

[Candidate snapshot contracts](https://github.com/mastermindx-market-intelligence/Mastermind/blob/0b960590c77101b3f3b5545896423f9ad07b7d56/portfolio/decision_snapshot_contracts.py), blob `752c08b2dd44999c6aedfec5f0c5a4d541d7e3f4`, lines 1–150 inspected. Closed receipt/snapshot schemas and failure states exist on the candidate branch. Exact protected-tree path search did not find its planned implementation modules. This is an active owner, not protected/live completion.

### P02
[Mastermind PR #1221](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1221), observed open, head `01fc1846471e482a4d68842ad53c6294478001e2`.

[Temporal audit candidate](https://github.com/mastermindx-market-intelligence/Mastermind/blob/01fc1846471e482a4d68842ad53c6294478001e2/research/BITEMPORAL_POINT_IN_TIME_TRUTH_AUDIT_2026-10-04.md), lines 1–175 inspected. Useful reconciliation input; not protected law. Annual availability proxies, quarterly filing clocks, estimates bake-off details, and additional source histories mentioned there remain candidate-audit leads unless separately verified in C01–C10.

### P03
[Mastermind PR #1224](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1224), observed open, head `7cbb03a85cfa96b2a880c297b01fd1c8df3038d4`.

[Commission 8 observability candidate](https://github.com/mastermindx-market-intelligence/Mastermind/blob/7cbb03a85cfa96b2a880c297b01fd1c8df3038d4/research/DATA_OBSERVABILITY_LIVE_CENSUS_COMMISSION_8_HARDENED_2026-10-04.md), lines 1–100 inspected. Data OS ownership was independently verified through C04–C06. Its other runtime/output-health pointers are leads for the owning census program, not a new runtime qualification in Commission 9.

### P04
[Mastermind PR #1183](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1183), observed open, head `ed4f2283f59cbd328e19aeffccd0d4e9318e3e76`. Issuer Inflection is an adjacent consumer/research program; metadata and changed paths were inspected, not its full scientific packet.

Organization PR/issue searches for the exact phrases “Dataset Value Gauntlet” and “data alpha attribution” returned no existing carrier. This is a bounded search result, not proof that every synonym or private local document was exhausted. A later implementation owner must refresh exact path custody.

## Primary methodological sources

### W01
[Newey and West, A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix](https://www.nber.org/papers/t0055), working paper 1986, journal publication 1987. Supports HAC inference under its assumptions, not immunity to short panels or arbitrary dependence. [Automatic lag selection follow-up](https://www.nber.org/papers/t0144) explicitly motivates checking finite-sample behavior.

### W02
[Clark and West, Approximately Normal Tests for Equal Predictive Accuracy in Nested Models](https://www.nber.org/papers/t0326), working paper 2006, journal publication 2007. Supports the nested forecast comparison adjustment; not a universal test for arbitrary classifiers, prompts, or nonnested policies.

### W03
[Benjamini and Yekutieli, The Control of the False Discovery Rate in Multiple Testing Under Dependency](https://cris.tau.ac.il/en/publications/the-control-of-the-false-discovery-rate-in-multiple-testing-under/), 2001, DOI `10.1214/aos/1013699998`. Distinguishes dependence conditions under which ordinary BH is valid from a more conservative arbitrary-dependence correction.

### W04
[Gneiting and Raftery, Strictly Proper Scoring Rules, Prediction, and Estimation](https://doi.org/10.1198/016214506000001437), 2007. Proper probability/distribution scores support separate evaluation of calibration and distributional usefulness, not confidence inferred from directional accuracy.

### W05
[Bailey and López de Prado, The Deflated Sharpe Ratio](https://doi.org/10.3905/jpm.2014.40.5.094), 2014. Selection and nonnormality adjustment for Sharpe assessment. A DSR output is not a Bayesian posterior probability that a dataset has true economic alpha.

### W06
[Bailey, Borwein, López de Prado and Zhu, The Probability of Backtest Overfitting](https://www.risk.net/ja/node/2471206). Primary journal page. CSCV/PBO concerns the selection procedure; it cannot repair unavailable historical inputs or fictional transaction costs.

### W07
[Hansen, A Test for Superior Predictive Ability](https://www.tandfonline.com/doi/abs/10.1198/073500105000000063), 2005. Family-level model comparison with dependence-sensitive resampling. The web page's later online date is not the original article year.

### W08
[Covert, Lundberg and Lee, Understanding Global Feature Contributions With Additive Importance Measures](https://proceedings.neurips.cc/paper_files/paper/2020/hash/c7bf0b7c1a86d5eb3be2c722cf2cf746-Abstract.html), 2020. SAGE motivates optional interaction-aware predictive attribution; feature contribution is not automatically policy utility, causal information value, or a purchase price.

### W09
[Dudík, Langford and Li, Doubly Robust Policy Evaluation and Learning](https://arxiv.org/abs/1103.4601), 2011. Off-policy inference requires identification/support conditions; deterministic historical actions do not provide missing counterfactuals by themselves.

### W10
[Howard, Ramdas, McAuliffe and Sekhon, Time-uniform, nonparametric, nonasymptotic confidence sequences](https://arxiv.org/abs/1810.08240), first posted 2018. Supports a possible later sequential-testing design under stated assumptions. It does not authorize optional peeking at fixed-horizon tests.

### W11
[Glasserman and Lin, Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis](https://arxiv.org/abs/2309.17322), first posted 2023. Training-period overlap and related information contamination matter for historical LLM experiments. This audit does not claim that anonymization or a fixed prompt removes all such contamination.

## Public and commercial source documentation

### W12
[SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [developer resources](https://www.sec.gov/about/developer-resources). Submissions/XBRL availability, update behavior, and fair-access requirements. Typical update times are not a contracted end-to-end delivery SLA; acceptance, publication, API observation, and Mastermind ingestion are different facts.

### W13
[FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [series observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), and [release dates](https://fred.stlouisfed.org/docs/api/fred/release_dates.html). Vintage-date intervals support revision-sensitive macro work. Date precision and the documented difference between release and FRED availability prevent automatic intraday claims.

### W14
[NYSE Daily TAQ](https://www.nyse.com/data-products/catalog/daily-taq). Published coverage: consolidated US trade/quote/NBBO/administrative data, 1993 onward, prior-day delivery. Exact correction replay and licensed uses require technical/sample/contract qualification.

### W15
[Nasdaq equities data products](https://www.nasdaq.com/products/data/equities/nasdaq). Historical TotalView-ITCH documentation describes history from 2014 and T+1 logs. Nasdaq venue order history is not all-venue US order-book history.

### W16
[FactSet Consensus Estimates DataFeed](https://insight.factset.com/resources/factset-consensus-estimates-datafeed). Published historical consensus/detail capabilities and global history from 1999, with some European history from 1997. Historical correction generations, contributor entitlement and package-specific rights remain sample/contract questions. The original report's specific historical-change-file API claim was **not independently reverified** in this pass and is not used as proof.

### W17
[LSEG I/B/E/S learning path](https://www.lseg.com/en/training/learning-centre/learning-paths/learning-path-for-data-solutions/learn-about-quantitative-data-solutions/learn-about-data-and-content/learn-about-ibes) and [quantitative data products](https://www.lseg.com/en/data-analytics/market-data/quantitative-economic-data-solutions/quantitative-data). Establishes a credible estimates/PIT product candidate, not the exact historical snapshot package, correction retention, or entitlements Mastermind would receive.

### W18
[S&P Capital IQ Estimates dataset](https://www.marketplace.spglobal.com/en/datasets/s-p-capital-iq-estimates-%281%29). Publisher describes broad estimates coverage, history from 1996, delivery options and timestamped PIT capability. These remain vendor claims until a lawful representative sample and rights schedule pass the same tests as competitors.

### W19
[Databento common timestamp fields](https://databento.com/docs/standards-and-conventions/common-fields-enums-types), [architecture](https://databento.com/docs/architecture), [OHLCV schema](https://databento.com/docs/schemas-and-data-formats/ohlcv), and [reference API](https://databento.com/docs/api-reference-reference). Clock names and nanosecond representation do not establish historical capture provenance. OHLCV event time can mark bar start; final bar content is not knowable then. Reference PIT behavior must be explicitly selected and verified.

### W20
[Databento, CME history extended to 2010](https://databento.com/blog/CME-history-extended-to-2010), 2024-12-03, and [MBO snapshot semantics](https://databento.com/docs/standards-and-conventions/mbo-snapshot). Concrete exception: parts of legacy CME history derive both event/receive timestamps from source SendingTime and flag `F_BAD_TS_RECV`; snapshot receive timestamps can describe snapshot generation. This refutes a blanket inference that every `ts_recv` is contemporaneous independent capture.

## What this evidence does not establish

No new licensed data sample, vendor quote, contract/right clearance, market backtest, actual production execution, data-store record count, current feed SLA, or live shadow decision uplift was established. A compound remote read was refused; that exact request was not retried or rerouted. Relevant attachment-only Mastermind store/runtime assertions remain explicitly unverified. Independent native repository reads, public-source research, and synthetic mathematics continued.

Original attachment identity: `deep-research-report (20).md`, 1,465 lines, SHA-256 `cef7701ab7eaeeae6ff97240387027c2b043c3a2113fe55dbf4a3d373c6854df`. Its session-local citation tokens are not durable source receipts and have not been promoted into this register. This packet's source-grounded corrections replace the original Commission 9 recommendation, not protected architecture or the frozen laws of adjacent research families.
