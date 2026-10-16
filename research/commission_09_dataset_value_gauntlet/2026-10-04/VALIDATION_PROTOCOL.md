# Commission 9 — Empirical validation and decision-value protocol

**Status:** proposed research protocol, not an executed market experiment.  
**Part of:** [complete Commission 9 masterplan](MASTERPLAN.md).  
**Source and proof boundaries:** [source register](SOURCE_REGISTER.md), [hardening audit](AUDIT_AND_RECENSUS.md).  
**Binding exception:** existing protected family-specific preregistrations and no-rerun/exposure rules control their own experiments. This generic protocol cannot reopen them or replace their frozen tests.

## 1. Register the claim before choosing the statistic

The evaluation unit is a **dataset version for a particular use**, not a provider name in the abstract. The specification must select one primary estimand, one primary direction and a bounded confirmatory family before outcome access.

| Claim type | Primary contrast | Appropriate main evidence | What it cannot establish alone |
|---|---|---|---|
| Additional predictive information | Frozen baseline `M0` versus baseline plus candidate `M1` | OOS proper-loss improvement, rank/prediction improvement on common support | Portfolio utility or causal economic information |
| Downside information | Baseline downside forecast versus augmented forecast | Proper score, actionable tail operating point, severity calibration | Return alpha |
| Event detection | Existing alerts versus candidate-enhanced alerts | Event-matched recall/precision, false-alarm load, lead time | Profit from trading alerts |
| Local decision contribution | Same cutoff, same initial local state, frozen policy with/without family | Changed action/rank/confidence/weight and matured local outcome under a specified experiment | Long-run closed-loop portfolio value |
| Retrained model contribution | Same allowed training process with/without family | OOS improvement under equal selection budget | Effect of simple inference-time masking |
| Closed-loop policy value | Two separately evolving policies with common initial state/environment | Paired net portfolio outcomes and risk constraints | Randomized causal live-market profit |
| Provider substitution | Candidate versus incumbent under the same use | Noninferiority plus net cost/reliability/coverage benefit | New independent alpha |
| Supporting/reference data | Existing owner service versus proposed service | Identity accuracy, coverage, timeliness, incident/abstention improvement | An additional investment conviction vote |

The research profile names which rows apply. Secondary results cannot substitute for a failed primary claim. A newly discovered mechanism is a new exploratory hypothesis with its own budget and future evidence, not a renamed successful original experiment.

## 2. Admission before market labels

No price-return, drawdown, event-outcome or realized-portfolio label may be accessed until a durable admission receipt establishes:

- the exact dataset/use, source version, rights scope and source owner;
- temporal mode and admissible availability rule, including precision bounds;
- identifier, membership, taxonomy and price-adjustment vintages;
- current permitted coverage denominator and missing/failure policies;
- label definition, actual maturity/availability time, target vintage and feasible execution clock;
- frozen split/cohort and exposure status;
- qualified primitive interfaces and a logged complete experiment budget;
- an approved outcome-access action under the existing research owner.

A hash proves identity, not lawful access or historical truth. A checksum of today's corrected file cannot retroactively qualify its original vintage. A record can describe a future scheduled event while being known today; therefore do not apply the false universal rule `event_time <= decision_time`. What must precede the decision is admissible knowledge of the record and the applicable mapping version.

Outcome-blind QA includes source missingness, cadence and coverage. **Testing whether missingness predicts future returns or drawdowns is outcome-bearing** and is charged to the experiment. Even an informal “quick check” belongs to trial/exposure accounting.

The admission can conclude `PROSPECTIVE_ONLY`, `EXPLORATORY_ONLY` or `BLOCKED` without any statistic. That is a valid gauntlet result.

## 3. Temporal cohort, universe and target contract

Each evaluated row has an entity/security ID, formation cutoff, feature-generation references, membership validity, decision timestamp, executable entry, exit, outcome maturity, outcome-generation vintage and missing/censoring reason. Do not rely on row position as time; enforce ordered, unique keys.

### Universe

Freeze the historical eligibility rule, not today's survivor list. Separate listing/security/issuer identifiers, corporate actions, ticker reuse and index membership. Missing sector identity must not be silently assigned from a current taxonomy. The protected C1 source explicitly documents current rather than era-correct sector labels and previously exposed dates; Commission 9 must preserve that limitation. [C09](SOURCE_REGISTER.md#c09).

Report coverage both as eligible security-times and as independent date/group/event cohorts. Include exclusions by region, sector, capitalization, liquidity, listing age, delisting status and relevant regime when those characteristics are themselves historically qualified. A panel can have many rows but very few independent sector-date observations.

### Return labels

Define executable entry and exit, price/return basis, dividends and other cash flows, fees where the label is net, benchmark and currency. A close-derived signal cannot assume a fill earlier in the same close. The convention may be next open, next close or another qualified execution point; it must match the data actually available.

For a forward horizon `h`, the previous row's `h`-period return generally has not matured by the next formation date. Training, expanding-mean benchmarks and calibration must use only labels whose maturity and required publication time precede the current fit cutoff. A one-row shift is not a universal anti-leakage repair. This matters to the existing OOS benchmark helper. [C02](SOURCE_REGISTER.md#c02).

A name ceasing to trade needs an explicit economic terminal-value policy or a disclosed censoring/bound. Carrying the last quote is not proof of a delisting return. Unknown terminal prices must not become favorable missing-case exclusions. The appropriate sensitivity may be conservative outcome bounds, a restricted estimand, or no strong tradable-value claim.

### Drawdown versus adverse excursion

Entry-relative maximum adverse excursion is `min(P_u / P_entry - 1)` over the registered future window. Peak-to-trough maximum drawdown is `min(W_u / max_{v<=u} W_v - 1)` with initial wealth included. These answer different risk questions. A drawdown event must specify threshold, horizon, intraday versus close sampling, treatment of corporate actions and censoring. Initial-capital handling is a demonstrated issue in the inspected standalone helper. [SYN-02](SYNTHETIC_AUDIT_RECEIPT.json).

### Event and revised targets

Freeze event ontology, authoritative timestamp, matching tolerance, entity relationship, repeated-alert cooldown and resolution rules before evaluating detections. Multiple alerts for the same event do not create multiple true positives. A detector reporting after first public availability may be valuable as a monitor but is not an early predictor of that public event.

For revised fundamentals or macro outcomes, state whether the target is first release, a specified later vintage, or eventual economic truth. Training waits for that target vintage to become available. Evaluation must not change target generations silently when a supplier restates history.

## 4. Frozen baseline and common support

The baseline must contain the strongest genuinely available incumbent information relevant to the use. Control candidates include momentum at relevant horizons, reversal, sector/industry, qualified theme exposure, market beta, realized/downside volatility, size, liquidity, valuation/profitability/growth, existing earnings-expectation features, and existing event/news information. Add PIT-known macro/liquidity/volatility context where appropriate.

Maintain two explicit baselines when necessary:

**Historical admissible core:** only controls with defensible past availability. Its result is incremental to that core, not to missing modern news/themes/flow history.

**Actual deployment information set:** the versioned data and policy available prospectively. This is the stronger comparator for a live-use recommendation.

A baseline missing a major known control cannot support an unrestricted “independent alpha” claim. Do not backfill an unavailable control using today's labels merely to make the table complete. Also do not deliberately weaken the baseline to create candidate value.

### Statistical sample versus deployment sample

For every pair `M0/M1`, freeze the same names, dates, weights, labels and benchmark. Raw and controlled diagnostic comparisons use that same joint support. Current `incremental_ic` can otherwise calculate raw and residual metrics on different cases. [C02](SOURCE_REGISTER.md#c02).

Then evaluate a separate full-deployment-universe result using the actual frozen policy for missing, stale and failed candidate inputs. This prevents a high complete-case IC from concealing that the source is unavailable on most decisions. Report both results; neither replaces the other.

Missing-value imputation, standardization, winsorization and model selection are fit on training information only. Cross-sectional normalization using contemporaneously available features may be valid at a cutoff, but its universe and feature availability must be frozen; it may not use test outcomes or future membership. All models receive the same procedural tuning budget.

### Minimum comparison set

A candidate should face the baseline alone, baseline plus availability/coverage indicator, baseline plus candidate content under a declared missing policy, and at least one plausible existing/cheap substitute when available. Full-family removal measures whether the content is redundant in the actual information set. An independently published duplicate fact already available in the baseline remains a legitimate baseline competitor; do not remove it merely to make a paid source look valuable.

## 5. Predictive measurements

### Raw rank IC

For date `t` and horizon `h`, calculate `Spearman(x_t, y_t,h)` on the frozen eligible cases. Report dates used, names per date, ties/constant features, invalid dates, distribution, mean, dispersion, sign frequency and dependence-aware uncertainty. Equal-date and any capitalization weighting are different estimands; choose before evaluation.

Cross-sectional subtraction of a constant benchmark return changes spreads but not ranks. “Relative-to-SPY rank IC” is therefore not a new independent statistic relative to raw return rank IC on the same date.

### Residual and partial-rank diagnostics

The existing helper residualizes candidate values in raw space against controls and then ranks the residual against the original outcome. Name this **semi-partial residual rank diagnostic**, not a full conditional-independence test. Ranking after OLS does not preserve every raw-space orthogonality property.

A separately specified partial-rank diagnostic can residualize both ranked variables against a defined control design and correlate their residuals. When evaluation outcomes enter a same-date residual regression, that is a retrospective association statistic, not a feature or forecast that existed at formation. Do not feed fitted target residuals back into a supposedly ex-ante predictor.

Check design rank, degrees of freedom, sample support and numerical conditioning. The pseudo-inverse VIF behavior found in this audit must not certify independence. Exact duplicates should be explicitly detected; near-collinear designs require regularized or reduced predeclared controls and a changed estimand, not false confidence. [SYN-03](SYNTHETIC_AUDIT_RECEIPT.json).

### OOS model augmentation

Train `M0: y=f(Z)` and `M1: y=g(Z,D)` within the frozen chronological procedure. Use only mature training labels. Evaluate paired OOS loss differences on identical test cases. For returns report OOS R-squared relative to an explicit causal benchmark, forecast-loss improvement, rank quality and economically interpretable spreads. A near-zero benchmark error denominator invalidates an unstable ratio claim.

Clark–West is used only where the specified models/loss satisfy its nested-forecast setting. It is not automatically valid for arbitrary machine learning, classifiers or policy utilities. Other settings require a qualified paired comparison of their own loss differentials and selection procedure. [W02](SOURCE_REGISTER.md#w02).

### Rank value and horizon decay

Report predeclared quantile portfolios/spreads, monotonicity, tail asymmetry and concentration. A one-tail event detector should not be sold as a symmetric ranking factor. Horizon curves may include 1, 5, 21 or 63 trading days when economically relevant, but only the registered primary horizon is confirmatory unless the extra horizons are in the multiplicity family. A curve's best observed point is not a free horizon selection.

### Probabilities and distributions

For binary labels use Brier and, where registered, log loss; specify probability clipping before evaluation and report boundary behavior. Keep reliability diagrams, calibration intercept/slope and discrimination separate. ECE is bin-dependent and a diagnostic, not the only promotion statistic. Fit recalibration only on training/validation data, never on the final evaluation labels.

For distributions use the appropriate qualified proper score such as CRPS and evaluate interval coverage/sharpness. Missing forecasts remain keyed to their original targets and baseline predictions; they cannot be dropped from one list and then zipped against another. The inspected CRPS wrapper needs precisely that alignment test. [C02](SOURCE_REGISTER.md#c02), [W04](SOURCE_REGISTER.md#w04).

### Drawdown and rare events

Report proper probability loss, PR-AUC with the prevalence baseline, recall/precision at predeclared actionable thresholds, false alarms per security-time, severity calibration and event coverage. ROC-AUC can be secondary; it must not hide rare-positive operating failure. Threshold selection occurs inside training/validation or is frozen by an operational cost rule.

For events report lead-time distribution relative to a qualified canonical availability timestamp, not only median lead time among successes. Include missed events, late detections, duplicate alerts and censoring. Bootstrap the relevant event/date clusters, not each alert independently.

## 6. Splits, dependence and honest uncertainty

A deployment claim requires chronological fitting. For each train/evaluation boundary, remove training examples whose label interval, required target vintage or availability reaches into the evaluation information window. Record actual intervals; a fixed number of purged rows may be insufficient when examples have variable horizons or publication delays.

A combinatorial split with future observations in training can be a retrospective robustness diagnostic; it is not proof of the information set a deployed model could have had. Embargo length follows the label/dependency geometry and the intended claim, not an arbitrary ritual. [C02](SOURCE_REGISTER.md#c02).

For cross-sectional models, first aggregate the paired metric or loss difference to the declared decision date/cohort; retain the cross-sectional nesting. For sector/group features, report effective group-date support. Use the same resampled dates/blocks for both arms and every compared model. Do not bootstrap names independently across common date shocks or independently resample baseline and candidate outcomes.

HAC lag choice must consider label overlap and additional serial dependence. Report requested/effective lags, bandwidth rule, cohort spacing, sample size and degenerate cases. `h-1` lags may cover mechanical overlap but need not cover all dependence. Rounded p-values are display outputs, not adequate raw inputs for precise downstream gates. [W01](SOURCE_REGISTER.md#w01), [C02](SOURCE_REGISTER.md#c02).

Block bootstrap conclusions depend on block length, weak-dependence/stationarity assumptions and the statistic. Preregister a primary construction and limited sensitivity range. Do not select the block producing significance. Preserve complete paired rows and failure policy. A bootstrap path is not a new real market regime.

A primitive-qualification suite should simulate null and known-effect cases with the intended cross-sectional correlation, serial dependence, missingness and sample lengths. Report empirical false-positive behavior and power, including uncertainty from finite simulation counts. Three unit examples cannot qualify a full statistical inference suite; their job is to demonstrate specific failures and enforce refusal until the owner qualifies the intended use.

## 7. Trial accounting and multiplicity

### Three ledgers in meaning, one existing owner in authority

The existing TrialLedger remains canonical. Its contract must distinguish:

- **configuration identity:** distinct hypothesis/feature/horizon/model/prompt specifications competing for the conclusion;
- **attempt identity:** each executed run, including failed, timed-out and replayed runs, with exact data/model generation;
- **outcome exposure:** which labels/metrics were revealed to which research generation/agents and for which inferential family.

These are semantic dimensions/references, not permission to create three rival stores. Durable-before-evaluation, corruption refusal, crash recovery, idempotency and cross-process custody must be demonstrated by the existing owner. A failure before results are produced still needs an attempt record. A repeated identical configuration can be one distinct config and multiple attempts/exposures.

### Adjustment matches the selection problem

Exploratory FDR can use BH under justified independence/positive-dependence conditions. Otherwise use a qualified conservative dependence-robust procedure or valid family resampling. Report the full registered family, including failed or unestimable outcomes and their explicit treatment; do not shrink the family to winners. [W03](SOURCE_REGISTER.md#w03).

For promotion, prefer a small frozen primary hypothesis or predeclared fixed-sequence/strong family-error-controlled design, consistent with the applicable protected protocol. RC/SPA applies to a family of comparable loss series; preserve joint dependence and report small-sample limits. DSR applies to selected Sharpe evaluation and PBO to a strategy-selection procedure. They are diagnostics for different questions, not several independent votes that compound confidence. [W05–W07](SOURCE_REGISTER.md#w05).

Record Monte Carlo resolution and never report zero p-value from a finite number of resamples. A plus-one p-value construction does not by itself establish exact exchangeability or make a fitted financial block bootstrap finite-sample exact.

## 8. Holdout custody and organizational exposure

The holdout is an outcome-information boundary, not a file name. Before freezing, record its date/entity/label scope, exact data generation, access owner, prior experiment overlap, known public/research exposure, and the model/retrieval knowledge boundary.

Final evaluation is opened only under the registered access condition. Feature selection, hypothesis revision, prompt optimization, regime discovery and model/hyperparameter choice occur before that boundary. The evaluator can return the registered result; it cannot release a sequence of selective slices to help the proposer tune.

**A new generation, branch, prompt, provider or dataset name does not restore unseen status to old outcomes.** Exposure carries across closely related hypotheses and any agent that has received the results, including through summaries, retrieval or public dashboards. A software correction after exposure may justify a transparent corrected exploratory result, but not a fresh confirmatory claim on the same seen data.

For the Trend family, the current protected C1 document explicitly names used historical dates and fixes forward confirmation. Do not run V2/B2 again, modify their preregistrations or pinned files, or treat C1's bridge interval as unseen. [C09](SOURCE_REGISTER.md#c09).

For a modern LLM, a fixed model identifier and withheld prompt context do not prove that its training lacked the target events. Historical LLM output is not actual-system replay absent contemporaneous evidence. Anonymization may be a sensitivity experiment, not a general contamination certificate. Prospective generation with archived requests/responses is the preferred decision-evidence path. [W11](SOURCE_REGISTER.md#w11).

Operational risk stops can occur immediately under existing safety owners. Positive-performance stopping may not be introduced after looking at results. A later sequential design needs its own qualified time-uniform inference and error budget; it cannot retroactively legalize peeking. [W10](SOURCE_REGISTER.md#w10).

## 9. Economic threshold, detectable effect and procurement value

Let `delta_min` be the smallest improvement that justifies the intended use after its relevant economic costs or operational benefit. It is a business/scientific design input, not the smallest p-value-supported effect.

Let statistical MDE describe what the planned independent sample and variance permit detecting at registered type-I error and power. For an illustrative mean-difference design with long-run standard deviation `sigma_LR`, effective chronological sample size `N`, and target alternative `delta_alt > delta_min`, a normal-approximation planning relation is:

`N ≈ [(z_(1-alpha) + z_(1-beta)) * sigma_LR / (delta_alt - delta_min)]^2`.

This is a planning approximation, not a universal formula for rank IC, rare events or maximum drawdown. Estimate nuisance variability only from permissible development data or conservative assumptions, then validate the actual test's size/power by the qualified simulation procedure. Do not use an optimistic same-holdout variance estimate to justify fewer confirmatory observations after seeing the effect.

Promotion evidence should answer whether a valid lower confidence bound clears the registered useful-effect threshold, subject to multiplicity and guardrails. Economic futility is supported when a valid upper bound lies below it. An interval spanning both sides is **inconclusive**, not proof of no value. If waiting for enough forward cohorts is too expensive, procurement can rationally be deferred without pretending the dataset has been scientifically disproven.

### Costs

Report gross and net results separately. Trading costs include executable lag, spreads, fees, slippage, impact, turnover, cash/funding, borrow availability/cost where relevant, corporate-action frictions and outages. Each input must be known at the relevant decision or explicitly modelled conservatively. Missing ADV or spread is not zero cost. Capacity depends on the strategy/universe and size; a single-asset helper's buy-and-hold comparison is not a portfolio capacity certificate.

Data economics include license and exchange fees, storage/egress, compute/model inference, monitoring, engineering maintenance, rights/security review, migration and termination/retention obligations. Separate sunk from marginal and fixed from variable costs; allocate shared costs under a declared rule and avoid subtracting them twice.

For a return-valued use, an illustrative annual benefit expression is:

`net_value(A) = A * incremental_return_after_trading_costs(A) - annual_incremental_data_and_operating_costs(A)`.

Capital `A`, scale effects and costs are unknown in this commission. No numerical break-even AUM is asserted. Because impact changes with size, larger capital does not automatically rescue a data purchase. A better Brier score or event detector is not converted to dollars without a registered action/utility model or explicit service budget.

### Substitute versus new information

A source with zero incremental alpha can still be a cheaper, faster or more reliable replacement. Define a noninferiority margin before testing. Require the candidate's valid lower quality-effect bound to exceed the negative margin, all mandatory rights/temporal/coverage/risk constraints to pass, and total switching-adjusted savings to be worthwhile. Do not use equivalence language merely because a difference was nonsignificant.

## 10. Decision improvement: four different experiments

### A. Frozen-policy local sensitivity

At a qualified Decision Snapshot, compare a fixed policy with/without the candidate information from the **same local portfolio state**. Preserve universe, other information, risk constraints, decision timestamp and execution assumptions. This establishes what the data changed in that particular decision architecture. It does not show what an entire strategy would have learned or held without the data.

Inference-time masking can put a model outside its trained input distribution. Use a declared missing-input representation and record this limitation. Do not substitute such a sensitivity experiment for retraining when the claimed value is learning a better model.

### B. Retrained-model contribution

Train baseline and augmented systems separately, following the same allowed tuning/model-selection procedure and comparable budgets. Freeze the procedure before outcomes. Improvements can then include learnable interactions; they are not necessarily recoverable from a frozen-model mask.

### C. Closed-loop shadow policies

Initialize the baseline and augmented arms with identical capital, holdings and constraints. Thereafter each arm evolves **its own** holdings, cash, risk state, costs, turnover and eligibility as its own earlier decisions dictate. Both receive the same exogenous qualified information stream except the candidate-family access difference. Forcing the same state again at every later decision erases compounding and path dependence and answers only repeated local questions.

Record both trajectories through the existing shadow owner. Simulated orders/fills must remain explicitly simulated. Do not place actual orders, write to live portfolio state, or infer market impact feedback not represented by the simulator. The canonical Snapshot dependency is not satisfied by a newly invented C9 snapshot. [P01](SOURCE_REGISTER.md#p01).

For continuous policies, compare paired chronological net return/risk series and predeclared whole-path objectives, not a sum of overlapping local cohort P&Ls. Apply paired block uncertainty only under its stated assumptions; resampling a realized path does not reconstruct a new behavioral market environment. Uninterrupted out-of-sample periods and prospective monitoring remain important robustness evidence.

### D. Provider replacement

Hold canonical feature definitions and the consumer policy fixed while switching source generation, then separately test any source-specific retraining strategy if that is the actual deployment proposal. Charge both to the trial budget. Measure source disagreements, failures, coverage and costs alongside economic output.

### Complete information removal

Mask the registered candidate's complete descendant graph: directly derived features, summaries, retrieval documents, prompt sections, cached model responses and any downstream state carrying its information. Recompute affected derived inputs through the existing owner. Do not remove unrelated independent incumbent information to artificially weaken the baseline. The information boundary and lineage hashes must be auditable.

### Stochastic policies

Archive model/version, prompt, tools, retrieval inputs, request/response IDs, sampling parameters, available seed, order and latency. Hosted systems may not reproduce bit-identical outputs from a seed. Use predeclared paired repetitions and capture all failures; randomize arm order where service drift could bias results. Candidate-induced token/context/latency cost is part of value, not noise to discard.

Report within-run and across-date variation. Compare the estimated paired effect with its uncertainty and decision risk; do not compare a mean effect's units directly with a variance or declare that an effect smaller than one-run noise is automatically valueless.

## 11. Decision attribution without false additivity

Report changed inclusion/exclusion, rank, predicted distribution/confidence, target weights, cash, sector/theme/factor exposure, timing, turnover, costs and constraint violations. Attach exact information and state references so a reviewer can answer what changed and why.

Selection, sizing, timing and risk interact. A decomposition is not uniquely causal merely because the components sum to P&L. A bounded first version can use a predeclared ordered/telescoping substitution and report its order dependence and interaction remainder. Later grouped Shapley/SAGE-style analyses can examine predictive interactions, but must state masking/imputation distributions, computation budgets and whether the estimand is prediction or policy utility. [W08](SOURCE_REGISTER.md#w08).

A utility may be a predeclared scalar primary decision criterion for a specific mandate, while the report still preserves the separate net return, drawdown, expected shortfall, turnover, exposure and calibration dimensions. This is different from a universal opaque dataset score. A higher scalar primary value cannot compensate for a failed hard rights or risk constraint.

Historical off-policy claims require the additional logging/overlap/identification conditions appropriate to the estimator. Without them, label the output policy sensitivity or simulation, not causal value learned from actual historical choices. [W09](SOURCE_REGISTER.md#w09).

## 12. Regime robustness and negative controls

Predeclare economically meaningful PIT-known regimes rather than mine labels after seeing outcomes. Report every cell with counts and uncertainty. Variation in effect magnitude is not automatically disqualifying; unexplained sign reversal, extreme concentration or lack of reproduction can invalidate a general claim. A one-episode sample usually supports only a narrow claim or insufficient evidence.

Useful negative/discriminating controls include an exact incumbent-feature duplicate, a deliberately future-shifted timestamp rejected before scoring, corrected generations unavailable at earlier cutoffs, a permuted/synthetic no-information feature, a constant feature, candidate availability without content, and a plausible cheap substitute. Never append artificial nulls to a family merely to alter its chosen multiple-testing behavior.

The framework's acceptance must not require finding one positive real-data candidate. It must correctly preserve an inconvenient null, mark insufficient power, reject a leaky source and refuse a false independence claim.

## 13. Advancement and expiry

The requested evidence ladder remains:

`raw → descriptive → predictive → shadow_advisory → decision_evidence → production`.

It applies to the registered predictive/risk/event use, not to every supporting-data asset. Nonpredictive reference/health uses remain under their existing operational qualification/authority processes. They cannot obtain an investment evidence vote by being healthy.

| State | Required evidence for that registered use | Authority ceiling |
|---|---|---|
| raw | Lawful access/storage and source identity, explicit temporal/rights unknowns | Research storage only; no predictive claim |
| descriptive | Qualified descriptive coverage/identity/clock/correction QA | Clearly labelled nonpredictive display |
| predictive | Valid OOS use-specific incremental or registered replacement evidence; qualified inference and economics where claimed | Research forecast only |
| shadow_advisory | Qualified live input capture, explanation/missing-state contract and prospectively frozen evaluation | Nonbinding research/shadow context, never execution authority |
| decision_evidence | Sufficient prospective paired policy evidence under qualified Snapshot/state/cost contracts and risk gates | Evidence for an authorized review, not automatic live use |
| production | Separate existing-owner approval, exact allowed consumer use, rights, release/runtime proof, monitoring and rollback | Only the explicitly approved scope; revocable |

`QUARANTINED`, `REJECTED_FOR_USE`, `INCONCLUSIVE`, `EXPIRED_RETEST_REQUIRED` and `RETIRED_FOR_USE` remain distinct dispositions. They must not overwrite source existence status or erase old results. Proposed state is a scorecard recommendation; the existing authority owner records actual permissions.

Any material source-methodology, identifier, correction, rights, model/prompt, policy, coverage or cost change requires an impact assessment and may expire the affected qualification. Production monitoring should use registered thresholds and ownership, not repeatedly test returns until a pleasing p-value appears. No positive advancement beyond synthetic fixture states is executed by the current research commission.

## 14. Acceptance matrix for later implementation

| Test family | Discriminating proof required | Failure interpretation |
|---|---|---|
| Source clocks | Future/ambiguous availability rejected; scheduled future event with earlier genuine publication handled correctly | Temporal contract invalid, not weak alpha |
| Corrections | Late correction cannot rewrite historical input; original and correction generations replay distinctly | Historical claim blocked |
| Identity/basis | Future mapping/current taxonomy and mismatched raw/adjusted price use rejected or claim-limited | Identity/priceability unqualified |
| Trial durability | Failed append, corruption, crash/retry, duplicate config with new attempt and concurrent custody retain honest accounting | No outcome evaluation until owner resolves |
| Exposure | New branch/generation/prompt cannot reopen exposed cohort | Confirmation refused |
| Sample alignment | Raw/controlled and forecast/climatology comparisons use same keyed cases | Paired statistic invalid |
| Cost prefix | Future suffix cannot change earlier admitted cost; missing ADV not zero cost | Economic metric unqualified |
| Risk geometry | Initial capital and adverse-excursion/MDD definitions distinguished | Risk claim unqualified |
| Dependence | Null-size/power behavior documented for intended cohort structure | Inference unavailable, not merely a large p-value |
| Baseline maturity | No fit/benchmark uses immature forward labels | OOS claim invalid |
| Information removal | Candidate descendants absent in masked arm; independent incumbent data retained | Attribution contrast invalid |
| Stateful shadow | Same initial state, separate evolving trajectories, equal external environment | Not closed-loop value evidence |
| Authority | Scorecard cannot write portfolio/source permissions; future states remain gated | Stop and correct ownership boundary |

These are required later proofs, not a claim that those tests have been implemented or passed in this research run.
