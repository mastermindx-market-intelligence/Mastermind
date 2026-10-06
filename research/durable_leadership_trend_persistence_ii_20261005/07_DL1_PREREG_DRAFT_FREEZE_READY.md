# 07 — DL-1 Preregistration Draft — Final Freeze-Ready Specification

**SOLE FREEZE-AUTHORITATIVE EXPERIMENT SPECIFICATION. NO EFFICACY OUTCOME ACCESS AUTHORIZED.**

**Scientific ruling:** `CONTINUE — NARROWED`  
**Operational state:** `WAIT_FOR_DATA / SOURCE_GATE`  
**Current protected reconciliation:** Mastermind `d8c302b8a8a65ab13e2afba98cc73481606ed4d0`; Macro `91f274d860e77f245bde31232a617f81d9a5b331`

This document closes the experimental degrees of freedom. It does **not** authorize capture or implementation while DL-0's taxonomy source gate is unresolved.

## 1. Experiment identity and route

Experiment: **DL-1 — additive independent-peer information for 20-session research leadership occupancy**.

Only eventual route: `PROSPECTIVE_US_POST_FREEZE`.

The route becomes operational only after `06_DL0_QUALIFICATION_AND_OWNER_RECONCILIATION.md` records an admitted contemporaneous GICS industry-group source with all required rights/clock/effective-date semantics.

No pre-gate or pre-freeze row enters fitting, power N, confirmation, or inference.

There is no ex-U.S. fallback after freeze and no route switch after outcome access.

## 2. Source/input law

### 2.1 Price/PIT substrate

Use the existing Mastermind research price/PIT owner:

`portfolio.predictions._load_panel()`

as identified by `research/TREND_PERSISTENCE_PROTOCOL.md`.

It supplies the established deep + delisted U.S. research panel and SPY benchmark. DL-1 does not create a new price store or expand source rights.

All return variables are named **panel close returns** or **SPY-relative panel close returns**. They are **not** called total returns unless the owning substrate itself supplies and documents total-return semantics at freeze time.

### 2.2 Taxonomy

The exact contemporaneous GICS industry-group source is **not yet admitted**.

Until DL-0 records one immutable admission receipt with acquisition, processing, storage, research/model-use, redistribution/research-only boundary, source clock, effective/correction semantics, issuer key, and digest:

**DL-1 MAY NOT START.**

EquityDesk-derived GICS fields are not admitted: repository presence records acquisition mechanics but current rights records leave processing/storage/model-use/redistribution unresolved.

Massive's broad enterprise rights do not substitute for identification/admission of an exact GICS-industry-group feed.

### 2.3 Fama/French and UMD inputs

**REMOVED.**

DL-1 uses no SMB, HML, RMW, CMA, UMD, or externally sourced academic factor series. This closes source/vintage/publication-clock/right ambiguity without inspecting outcomes.

### 2.4 Market capitalization

**REMOVED.**

No market-cap variable enters N, S, G, A, challenger, power, calibration, or secondary analysis.

### 2.5 Liquidity

No dollar-volume/liquidity variable enters DL-1. This avoids introducing another unresolved source contract.

## 3. Research state — not product state

For eligible security i at formation close t:

`RS_h(i,t) = R_h_panel(i,t) - R_h_panel(SPY,t)`

for h ∈ {20, 60, 120, 126, 252} trading sessions.

Define:

`DL1_RS126_Q4(t,i)=1`

iff `RS_126(i,t)` is at or above the 75th percentile of the eligible U.S. formation-date cross-section.

This is a **research cohort state only**.

It is not Macro Leader Radar `LEADERSHIP`, Prophet rank, ThemeState, or a production label. Leader Radar retains its own top-decile persistence, lifecycle evidence, hysteresis, and state precedence.

## 4. Final endpoint ruling

### 4.1 Primary — horizon occupancy

`DL1_OCCUPANCY_20(t,i)=1`

iff `DL1_RS126_Q4(t+20,i)=1`.

Truthful claim: **20-trading-session leadership occupancy / re-entry robustness**.

This endpoint permits exit and re-entry between t and t+20. It is **not continuous survival**.

### 4.2 Structural secondary — first-exit survival/hazard

`DL1_FIRST_EXIT_60(t,i)`

is the first trading-session offset k ∈ [1,60] for which `DL1_RS126_Q4(t+k,i)=0`, right-censored at 60 if no exit occurs.

This is the only DL-1 endpoint described as survival/hazard.

### 4.3 Secondary occupancy

`DL1_OCCUPANCY_60(t,i)=1`

iff `DL1_RS126_Q4(t+60,i)=1`.

### 4.4 Falsification firewall

Failure of `DL1_OCCUPANCY_20` falsifies **only** the frozen additive industry-group claim for 20-session horizon occupancy.

It does **not** falsify the distinct first-exit/hazard thesis.

If the primary occupancy gate fails:
- `DL1_FIRST_EXIT_60` is not opened as a rescue;
- `DL1_OCCUPANCY_60` is not used as a rescue;
- no survival/hazard conclusion is drawn.

A future hazard-primary experiment requires a new preregistration and new untouched evidence.

Forward return, MAE, recovery, prior-high reclaim, and Leader Radar state-transfer performance are DO_NOT_READ in DL-1.

## 5. Formation clock and eligible universe

Formation cadence: every fifth U.S. market trading session beginning at future gate-cleared/freeze anchor offset 0.

Feature cutoff: official formation close or earlier.

Outcome clock begins at t+1.

Eligible focal security:
- point-in-time S&P 1500 member under the existing universe owner;
- U.S. primary common-equity listing;
- at least 252 prior valid panel sessions;
- resolved issuer identity;
- valid contemporaneous admitted GICS industry-group classification at t;
- at least 15 valid independent peer issuers after focal/duplicate exclusion.

One primary eligible listing per issuer.

Future delisting information is never a formation feature.

## 6. Peer-universe law

Peers are all other eligible **U.S. issuers** sharing the focal issuer's admitted contemporaneous GICS industry group at t.

No country/regional/global peer pool enters DL-1.

Exclude the focal issuer and every alternate listing/share class mapped to it before any peer statistic.

If valid independent peer count <15:
`ABSTAIN_PEER_N`.

## 7. Frozen group vector G

All features are fixed at formation close t.

### 7.1 Peer leader definition

`PEER_LEADER(t,j)=1`

iff peer j is in the same `DL1_RS126_Q4` research state at t.

This is not Leader Radar `LEADERSHIP`.

### 7.2 `peer_continuity_20`

Observation lag = exactly 20 U.S. trading sessions.

L0 = independent peers that:
- are valid peers at both t−20 and t; and
- are `PEER_LEADER=1` at t−20.

L1 = L0 members also `PEER_LEADER=1` at t.

`peer_continuity_20 = |L1| / |L0|`.

If |L0| <5:
`ABSTAIN_CONTINUITY_N`.

No interpolation.

### 7.3 `breadth_q4_t`

Fraction of valid independent peers with `PEER_LEADER(t)=1`.

### 7.4 `breadth_change_20`

`breadth_q4_t - breadth_q4_(t-20)`.

Each date uses the membership actually effective/captured on that date. No constituent is retroactively carried across taxonomy changes.

### 7.5 `leader_dependency_hhi60`

For each valid peer j:

`c_j = max(RS_60(j,t), 0)`.

If `sum(c_j)>0`:

`leader_dependency_hhi60 = sum((c_j / sum(c))^2)`.

If all `c_j=0`:
- `leader_dependency_hhi60 = 0`;
- `dependency_zero_positive = 1`.

Otherwise `dependency_zero_positive=0`.

The zero-positive indicator is included in G so the zero convention is explicit rather than hidden.

### 7.6 `peer_residual_strength60`

For each security j and each trading session u, compute panel close log return `r_j,u` and SPY panel close log return `r_m,u`.

At formation t, estimate rolling 252-session OLS:

`r_j,u = alpha_j + beta_j * r_m,u + epsilon_j,u`

using the most recent 252 paired sessions through t and requiring at least 200 paired observations.

No SMB/HML/RMW/CMA/UMD series enters residualization.

`resid60_j = sum(epsilon_j,u)` over the most recent 60 sessions through t.

`peer_residual_strength60` = equal-weight mean `resid60_j` across valid independent peers.

Missing required price history => peer excluded; if peer count then falls below 15 => abstain.

### 7.7 Frozen G

G contains exactly:

1. `peer_continuity_20`
2. `breadth_q4_t`
3. `breadth_change_20`
4. `leader_dependency_hhi60`
5. `dependency_zero_positive`
6. `peer_residual_strength60`

No other group feature enters DL-1.

## 8. Identity, missingness, and abstention

Existing issuer-identity owner is authoritative.

- unresolved focal issuer => `ABSTAIN_IDENTITY`;
- unresolved peer => exclude peer;
- remaining peer count <15 => `ABSTAIN_PEER_N`;
- continuity prior-leader denominator <5 => `ABSTAIN_CONTINUITY_N`;
- missing contemporaneous industry group => `ABSTAIN_TAXONOMY`;
- incomplete G => `ABSTAIN_GROUP_VECTOR`;
- incomplete S => `ABSTAIN_STOCK_VECTOR`;
- source receipt absent/invalid => `ABSTAIN_SOURCE_GATE`.

No primary-analysis imputation.

Primary coverage gate: complete S+G for at least 80% of otherwise eligible `DL1_RS126_Q4` rows.

Below 80% => `WAIT_FOR_DATA_OR_REPAIR`; no efficacy read.

## 9. Frozen nuisance model N

N contains exactly:

- intercept;
- `SPY_R126` — SPY 126-session panel close return;
- `XSEC_SD_RS126` — cross-sectional standard deviation of eligible securities' `RS_126` at formation;
- ten broad-GICS-sector indicator columns with **Communication Services as the fixed reference category**.

Broad sector must come from the same admitted contemporaneous taxonomy source as industry group or be a deterministic parent of its admitted GICS code.

If sector is missing/ambiguous => row abstains.

No other nuisance variable enters N.

## 10. Frozen stock vector S

S = N plus exactly:

- `RS20`
- `RS60`
- `RS120`
- `RS252`
- own `resid60` from the same SPY-only residualization law in §7.6;
- annualized realized log-return volatility over 20 sessions;
- annualized realized log-return volatility over 60 sessions;
- annualized realized log-return volatility over 120 sessions;
- 252-session beta to SPY.

No market cap. No liquidity. No external factor momentum.

## 11. Frozen models

- `N` = nuisance model in §9.
- `G` = N + frozen group vector.
- `S` = N + frozen stock vector.
- `A` = N + frozen stock vector + frozen group vector.

There is **no interaction model I** in DL-1.

No stock×group product term, tree, spline, subgroup search, nonlinear feature discovery, or model-class search.

DL-2 alone may test interactions after a new preregistration on new untouched evidence.

## 12. Deterministic estimator

All N/G/S/A models use the same ridge logistic regression.

For coefficients beta excluding intercept alpha, minimize:

`negative_log_likelihood(alpha,beta) + 0.5 * sum(beta_k^2)`.

Thus fixed ridge penalty lambda = 1.

Rules:
- intercept unpenalized;
- all non-intercept coefficients penalized equally;
- no class weighting;
- no hyperparameter tuning;
- no cross-validation;
- no estimator switch;
- no Firth branch.

Continuous predictors:
1. winsorize using training-set empirical 1st/99th percentiles with linear interpolation;
2. standardize using training-set mean and population standard deviation (ddof=0);
3. apply those frozen transforms to the next evaluation block.

Zero-variance training predictor => evaluation block `WAIT_FOR_MODEL_FIT`; predictor is not silently dropped.

Convergence: maximum absolute gradient <=1e-8 within 200 Newton/IRLS iterations.

Failure to converge => `WAIT_FOR_MODEL_FIT`; no fallback estimator.

## 13. Corrected block/time semantics

A formation occurs every fifth U.S. market trading session.

An evaluation/dependence block is exactly **60 consecutive U.S. market trading sessions**, not 60 formation observations.

Each complete 60-market-session block contains exactly 12 formation dates at offsets 0,5,...,55 relative to that block.

Blocks:
- B1: market-session offsets 0–59
- B2: 60–119
- B3: 120–179
- B4: 180–239
- B5: 240–299
- B6: 300–359
- B7: 360–419
- B8: 420–479
- B9: 480–539

Formation offsets are every fifth session inside each block.

Burn-in B1–B3:
- 180 market sessions;
- 36 formations.

Confirmation B4–B9:
- 360 market sessions;
- 72 formations.

Last confirmatory formation = offset 535.

Last primary t+20 maturity = offset 555.

Last t+60 structural-secondary maturity = offset 595.

Conservative one-reveal horizon = **596 market trading sessions from offset 0 through 595**, approximately 2.37 trading years.

No anchor exists while the source gate is unresolved.

## 14. Prequential fitting / embargo

For evaluation block Bk:

Training rows are all prior matured eligible rows whose **full 60-trading-session post-formation window ends strictly before the first market session of Bk**.

Thus the 60-session embargo is automatic.

For each Bk:
- compute transforms from eligible training rows only;
- fit N/G/S/A on training rows only;
- seal all Bk predictions before any Bk outcome matures.

B1–B3 are burn-in only. No A−S efficacy statistic or peer-feature outcome association from burn-in is exposed to a researcher.

B4 is the first possible confirmatory prediction block.

A matured earlier block may mechanically enter the fitting set for a later block, but no block-level efficacy statistic is exposed before the single final reveal.

## 15. Look accounting

Evaluation / TrialLedger remains the look owner.

All predictions and endpoint labels remain sealed from efficacy analysis until every final-eligibility predicate in §23 is true.

Exactly one formal efficacy report is permitted.

No interim:
- A−S contrast;
- G-feature/outcome correlation;
- subgroup efficacy;
- first-exit effect;
- occupancy60 effect;
- hazard association.

## 16. Primary estimand

For confirmatory row i:

`d_i = LogLoss_S(i) - LogLoss_A(i)`.

Observed primary model-value contrast:

`DeltaLogLoss20 = mean_i(d_i)`.

Positive values favor A.

Primary null:
`H0: DeltaLogLoss20 <= 0`.

## 17. Exact primary inference algorithm

Use one **circular moving-block bootstrap** over ordered confirmatory formation dates.

There are 72 planned confirmatory formation dates.

A bootstrap block contains exactly **12 consecutive formation dates**, corresponding to 60 market trading sessions.

Algorithm:
1. Compute observed `Delta = mean_i(d_i)`.
2. Center row loss differences: `d_i0 = d_i - Delta`.
3. Let the 72 formation dates be indexed 0..71.
4. For each of exactly 10,000 replicates using PRNG seed `2026100601`:
   - sample six block-start indices independently and uniformly from 0..71 with replacement;
   - for each start, take 12 consecutive formation-date indices with circular wrap modulo 72;
   - concatenate the six blocks;
   - include every row belonging to every selected formation date with multiplicity;
   - compute the row-weighted mean of the selected `d_i0`.
5. One-sided p-value:

`p = (1 + count(Delta_b_star >= Delta)) / 10001`.

No permutation alternative, block-length search, adaptive resampling, or inference substitution is allowed.

Primary statistical gate: `p < 0.05`.

## 18. Practical materiality

Both are required:

1. `DeltaLogLoss20 / mean(LogLoss_S) >= 0.01` — at least 1.0% relative log-loss improvement.
2. `AME_CONTINUITY_PLUS20 >= 0.02`.

For `AME_CONTINUITY_PLUS20`:
- take each confirmatory row with factual `peer_continuity_20 <= 0.80`;
- evaluate A prediction at factual G;
- evaluate A prediction with `peer_continuity_20` increased by exactly 0.20, capped at 1.0, all other predictors fixed;
- average counterfactual minus factual probability.

No high/low confirmation bins exist.

## 19. Calibration gate

Clip predicted probabilities to [1e-6, 1−1e-6] for scoring.

On the untouched confirmatory set, A passes calibration iff all hold:
- logistic recalibration intercept ∈ [−0.10,+0.10];
- logistic recalibration slope ∈ [0.80,1.20];
- expected calibration error <=0.03.

ECE:
- sort by predicted probability;
- tie-break deterministically by `(formation_date, canonical_issuer_id)`;
- partition into 10 equal-count bins whose sizes differ by at most one;
- ECE = row-count-weighted mean of absolute bin observed-rate minus bin mean-prediction.

Any failure blocks advance.

## 20. Stability / concentration gates

### Time
Each B4–B9 block must contain at least 100 complete analyzed rows.

Compute blockwise A−S mean log-loss improvement.

Pass iff:
- at least 5 of 6 block improvements are >0; and
- no two consecutive blocks are <0.

### Industry group
- no single industry group may exceed 20% of analyzed confirmatory rows;
- for every industry group contributing at least 5% of confirmatory rows, leave-one-group-out aggregate `DeltaLogLoss20` must remain >0.

If concentration prevents these rules from being evaluated, verdict = `WAIT_FOR_DATA`.

### Episode
For each B4–B9 block b:

`positive_contribution_b = max(sum_i_in_b(d_i), 0)`.

Total positive contribution = sum across blocks.

Pass iff total positive contribution >0 and no single block contributes >25% of that total.

### Identity / coverage
- analyzed focal issuer identity resolution =100%;
- complete S+G coverage >=80% of otherwise eligible research leaders;
- valid peer count >=15 by construction;
- any industry group losing >10% of otherwise eligible peer observations to unresolved peer identity is ineligible for confirmatory inference.

## 21. Deterministic broad-sector challenger

No `when available` branch remains.

For each focal row, using the same admitted contemporaneous broad GICS sector:
- exclude focal issuer and alternate listings;
- require at least 30 independent eligible sector peers.

`SECTOR_REL60` = equal-weight 60-session panel close return of those sector peers minus SPY 60-session panel close return.

`SECTOR_REL120` = analogous 120-session quantity.

If <30 sector peers:
`ABSTAIN_CHALLENGER`
and the row cannot enter primary confirmatory inference.

Define:
- `S_COMMON = S + SECTOR_REL60 + SECTOR_REL120`;
- `S_COMMON_G = S_COMMON + G`.

Independent-peer claim fails if either:
- A does not beat `S_COMMON` on mean log loss; or
- `S_COMMON_G` relative log-loss improvement over `S_COMMON` is <0.005.

No challenger selection after outcomes.

## 22. Structural secondary first-exit model

This section is opened only if the primary occupancy20 experiment passes every gate.

Convert each eligible row into person-session observations k=1..60 until first exit/censor.

Use complementary-log-log discrete-time hazard with four fixed baseline intervals:
- k=1..5
- k=6..20
- k=21..40
- k=41..60

Formation-fixed covariates only.

Fit:
- hazard-S = interval indicators + frozen S covariates;
- hazard-A = interval indicators + frozen S + frozen G.

Use fixed ridge penalty lambda=1 on non-intercept/non-baseline covariate coefficients; baseline interval coefficients are unpenalized.

No time-varying feature update.

Report hazard-A versus hazard-S integrated Brier score through 60 sessions and person-session log loss plus calibration by the same fixed 10-bin rule applied to predicted 60-session survival.

This structural secondary cannot rescue a failed primary and does not convert an occupancy null into a hazard null.

## 23. Exact outcome-blind power simulation

Power may use burn-in endpoint labels and pre-outcome feature/prediction geometry only. It may not use any confirmatory A−S effect, confirmatory feature/outcome correlation, subgroup efficacy, or hazard association.

### 23.1 Burn-in base-rate/dependence calibration

B1–B3 contain 36 formation dates.

For each burn-in formation date t:
- `n_t` = matured eligible primary rows;
- `s_t` = rows with `DL1_OCCUPANCY_20=1`;
- Jeffreys-smoothed rate `q_t=(s_t+0.5)/(n_t+1)`.

Let pooled burn-in rate:
`pi = (sum_t s_t + 0.5) / (sum_t n_t + 1)`.

Define:
`a_t = logit(q_t) - logit(pi)`.

Estimate exactly one AR(1):
`phi = clip(sum_{t=2..36}(a_t*a_{t-1}) / sum_{t=1..35}(a_t^2), -0.95, 0.95)`.

Innovation variance = mean squared residual of:
`a_t - phi*a_{t-1}`
for t=2..36.

If denominator is zero, set `phi=0`.
If innovation variance is zero, use zero date shock.

No alternative dependence model is tried.

### 23.2 Outcome-blind peer score for simulation only

For every planned confirmatory row, before its outcome is available, create:

`z_i = mean(`
- standardized `peer_continuity_20`,
- standardized `breadth_q4_t`,
- standardized `breadth_change_20`,
- negative standardized `leader_dependency_hhi60`,
- standardized `peer_residual_strength60`
`)`.

Standardization uses the mechanically available past-only training transform for that block.

`z_i` is a **power-simulation device only**. It is not a DL-1 fitted score and never enters A.

### 23.3 Alternative calibration

Use each row's stored pre-outcome S probability `p_S,i`.

Synthetic alternative probability:

`p_A,i(beta) = logistic(logit(p_S,i) + beta*z_i + eta_t)`

where `eta_t` follows the burn-in AR(1) law.

Using seed `2026100602`, solve beta >=0 by deterministic bisection on [0,10] until the Monte Carlo expected A-versus-S log-loss improvement equals exactly 1.00% relative to S within absolute tolerance 1e-5.

For each bisection evaluation:
- use exactly 2,000 simulated datasets;
- reuse common random numbers across beta values;
- maximum 60 bisection iterations.

If no beta in [0,10] achieves the target, power gate fails.

### 23.4 Power estimate

With independent seed `2026100603`:
- generate exactly 20,000 synthetic confirmatory datasets under the calibrated 1% alternative and observed/planned 72-date geometry;
- for each dataset, generate formation-date AR(1) shocks using the burn-in phi/innovation variance;
- generate Bernoulli outcomes from `p_A,i(beta)`;
- calculate synthetic row log-loss difference using stored `p_S,i` versus `p_A,i(beta)`;
- apply the exact 10,000-replicate circular block bootstrap from §17;
- record whether one-sided p<0.05.

Estimated power = fraction rejected.

Requirement: **power >=0.80**.

This defines power for rejecting zero model-value improvement when the true alternative is 1% relative log-loss improvement. The separate observed >=1% materiality gate remains required at final reveal.

The power simulation cannot be executed before the taxonomy source gate provides lawful prospective peer geometry.

## 24. Final-read eligibility

`DL1_FINAL_READ_ELIGIBLE=true` requires all:

- DL-0 taxonomy source gate cleared before anchor;
- immutable preregistration frozen before anchor;
- >=80% power under §23;
- B1–B3 completed;
- B4–B9 completed;
- all 72 confirmatory formation dates accrued;
- all confirmatory t+60 windows matured through offset 595;
- >=12 distinct confirmatory formation months;
- >=365 calendar days between first and last confirmatory formation date;
- >=1,000 matured primary rows;
- >=250 unique analyzed issuers;
- >=8 industry groups each with >=50 analyzed rows;
- each B4–B9 has >=100 complete rows;
- S+G coverage >=80%;
- identity/peer/challenger gates satisfied;
- exactly zero prior efficacy reveal.

Any unmet predicate => `WAIT_FOR_DATA` or the typed source/model/coverage wait state. No threshold lowering.

## 25. Advance rule

DL-1 advances to separately preregistered DL-2 only if ALL:

1. primary one-sided circular-block-bootstrap p<0.05;
2. relative A−S log-loss improvement >=1.0%;
3. `AME_CONTINUITY_PLUS20 >= +0.02`;
4. calibration gate passes;
5. time stability passes;
6. industry-group concentration passes;
7. episode concentration passes;
8. identity/coverage/peer/challenger gates pass;
9. A beats `S_COMMON`;
10. `S_COMMON_G` improves over `S_COMMON` by >=0.5% relative log loss;
11. G beats N on mean log loss (>0).

Otherwise the frozen additive occupancy construction does not advance.

## 26. Permanent closure law

A failed DL-1 permanently closes this exact combination:

- `DL1_RS126_Q4` cohort;
- `DL1_OCCUPANCY_20` primary endpoint;
- admitted GICS industry-group grouping;
- frozen six-field G vector;
- frozen S and N;
- additive A−S contrast;
- prospective-U.S. route.

No same-evidence retuning of threshold, horizon, peer floor, windows, residualization, estimator, materiality, calibration, concentration, challenger, or subgroup is allowed.

**Primary occupancy failure does not close the distinct first-exit/hazard thesis.** That thesis receives no DL-1 result and would need a new preregistration plus new untouched evidence.

## 27. DO_NOT_READ

Before final eligibility:
- A−S efficacy;
- G-feature/outcome correlations;
- subgroup efficacy;
- first-exit/hazard effect;
- occupancy60 effect;
- raw-return/MAE/recovery efficacy;
- Leader Radar product-state transfer performance;
- PSS prospective outcomes;
- Top Anatomy OOT.

If occupancy20 fails, do not open hazard as rescue.

## 28. DO_NOT_REDO

- B2 path-shape family;
- C1/C2 eleven-sector construction;
- contaminated dates as fresh confirmation;
- current taxonomy backcast;
- DL-1 interaction discovery;
- duplicate Leader Radar lifecycle;
- duplicate peer engine;
- duplicate ThemeState;
- duplicate timeframe owner;
- duplicate outcome ledger;
- duplicate Prophet/Conditional-Fusion ranker.

## 29. Start gate

Before any DL-1 capture/instrument work:

1. DL-0 admits the exact contemporaneous GICS industry-group source and five-rights receipt.
2. This experiment text is accepted/frozen as an immutable preregistration artifact.
3. Exact Mastermind/Macro pins are recorded.
4. Existing Evaluation/TrialLedger registers the one-reveal experiment.
5. The first eligible formation date/anchor is recorded.
6. Only then may outcome-blind prospective capture begin.

**No DL-1 instrument implementation occurs in the present repair pass.**
