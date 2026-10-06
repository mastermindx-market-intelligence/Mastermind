# 07 — DL-1 Preregistration Draft — Final Freeze-Ready Specification

**SOLE FREEZE-AUTHORITATIVE EXPERIMENT SPECIFICATION. NO EFFICACY OUTCOME ACCESS AUTHORIZED.**

**Scientific ruling:** `CONTINUE — NARROWED`  
**Operational state:** `WAIT_FOR_DATA / SOURCE_GATE`  
**Current protected reconciliation:** Mastermind `a6d40ff648671b03bd4d829d84dd066b58ea8c3f`; Macro `e95e32d4418f12c9670a6a4321498d2c641158fd`

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

## 4A. Exhaustive endpoint attrition, delisting, and missing-price law

This section is part of the frozen endpoint definition. A focal row that was valid at formation is **never silently dropped because of what happens later**.

### 4A.1 Formation membership versus endpoint membership

PIT S&P 1500 membership is required **only at formation t**.

After formation, the focal security does **not** have to remain in the S&P 1500 to receive an endpoint label. An ordinary index deletion/rebalance with continued independent public trading is not itself a failure and not a censoring event.

At every endpoint/state observation date d, the comparison threshold is rebuilt from the contemporaneous PIT S&P 1500 universe at d. The focal is compared with that threshold even when it is no longer an index constituent.

### 4A.2 Exact Q4 threshold at an observation date

For market session d, define `Q75_RS126(d)` from distinct canonical issuers that:

- are PIT S&P 1500 constituents effective at d;
- have one resolved primary U.S. common-equity listing at d;
- have a valid panel close on d;
- have enough panel history to compute `RS_126`;
- have resolved issuer identity.

If the focal is itself a constituent at d, it participates in the threshold population exactly once.

`Q75_RS126(d)` is the empirical 75th percentile using **linear interpolation**; a security is in Q4 iff `RS_126 >= Q75_RS126(d)`.

Threshold validity requires both:
- at least 80% of distinct PIT S&P 1500 issuers at d have valid `RS_126`; and
- at least 1,000 distinct issuers contribute.

SPY must have a valid close/history for the same d. If any threshold condition fails, the date is `THRESHOLD_UNRESOLVED`; no focal label is manufactured.

### 4A.3 Security-continuity law

A post-formation symbol/exchange change is followed **only** when the existing identity owner supplies an effective-dated lineage receipt establishing that the successor listing is the **same continuing security**.

A merger/acquisition in which the focal security ceases independent public trading is not spliced into the acquirer. A bankruptcy, liquidation, cancellation, or delisting that terminates the independently traded focal security is likewise terminal.

If continuity versus termination cannot be established from the canonical identity/event evidence, status is `OUTCOME_PENDING_IDENTITY`; no label is imputed.

### 4A.4 Primary occupancy resolution clock

Nominal primary endpoint = market session `t+20`.

A valid focal endpoint observation requires both a valid focal close and sufficient same-security canonical lineage/history to compute `RS_126` without splicing a different security. If such an observation exists on t+20, evaluate occupancy on t+20.

If no valid focal close exists on t+20, no terminal event is known, and the security has not been proven to terminate, allow an exact **five-market-session resolution grace**: t+21 through t+25.

Use the **first** later market session d* in that grace window with a valid focal endpoint observation under the rule above. Evaluate `RS_126` and `Q75_RS126(d*)` on that same d*. Record status `OCCUPANCY_OBSERVED_DELAYED` and `endpoint_delay_sessions = d*-(t+20)`.

If no valid close exists through t+25 and no terminal event can be established, status is `OUTCOME_PENDING_PRICE`. The row remains in the cohort and **blocks the sole efficacy read** until the source is repaired or a terminal/continuity classification becomes available.

The same five-session rule applies to `DL1_OCCUPANCY_60` at nominal t+60.

### 4A.5 Exhaustive outcome-status table

Apply rows in this table by precedence from top to bottom.

| Post-formation condition | Primary/60d occupancy | `DL1_FIRST_EXIT_60` | Cohort treatment |
|---|---|---|---|
| Same security, valid close on nominal endpoint | Compute Q4 against contemporaneous threshold | First observed Q4 exit; otherwise administrative censor at 60 | retained |
| Leaves S&P 1500 but continues independent trading | Compute exactly as above; membership exit alone is not failure | Continue state observations against contemporaneous thresholds | retained |
| Effective-dated symbol/exchange change proven same continuing security | Follow successor security; compute on same canonical lineage | Continue clock without exit | retained |
| Acquisition/merger terminates focal security | `0` if termination effective on/before resolved endpoint observation; never splice acquirer | event at first U.S. market session on/after official termination effective date, if <=60 | retained; terminal failure |
| Delisting/bankruptcy/liquidation/cancellation terminates focal security | `0` if termination effective on/before resolved endpoint observation | event at first U.S. market session on/after official termination effective date, if <=60 | retained; terminal failure |
| Primary listing lost and no same-security successor exists | `0` only when official evidence establishes termination; otherwise pending identity | terminal event if proven; otherwise unresolved | retained |
| Temporary nonterminal no-print at nominal occupancy endpoint | first valid close within +5 sessions; compare on that actual observation date | missing session is neither exit nor carried-forward state; next valid close resumes observation | retained |
| Temporary no-print inside first-exit window that later resumes | not applicable unless it includes occupancy endpoint | no event on the no-print session; event can occur on the first later valid close if Q4 is lost | retained |
| No valid occupancy close through +5 and no proven terminal event | `OUTCOME_PENDING_PRICE`; no 0/1 label | if the 60-session path also ends without a valid resumption, `HAZARD_PENDING_PRICE` | retained; final read blocked |
| Permanent price unavailability with proven terminal event | `0` under terminal rule | terminal event under terminal rule | retained |
| Permanent price unavailability with no proven terminal/continuity event | `OUTCOME_PENDING_PRICE` or `OUTCOME_PENDING_IDENTITY` | `HAZARD_PENDING_PRICE` / `HAZARD_PENDING_IDENTITY` | retained; final read blocked |
| Contemporaneous threshold/benchmark unavailable | `OUTCOME_PENDING_THRESHOLD` | `HAZARD_PENDING_THRESHOLD` if needed before event/censor | retained; final read blocked |

No acquisition premium, last stale mark, zero price, average return, acquirer return, or carry-forward close is used to fabricate a Q4 state.

### 4A.6 First-exit observation law

`DL1_FIRST_EXIT_60` means the first **observable closing-state exit** or proven terminal-security exit within market sessions t+1..t+60.

For each session k:

1. if a proven terminal event for the focal security is effective by that session, record an exit event at that session;
2. else if the focal has a valid close and the contemporaneous threshold is valid, evaluate Q4 and record the first Q4=0 session as the exit;
3. else if the security has a nonterminal no-print, record `STATE_NOT_OBSERVED` for that session and do not carry the prior close forward;
4. else if identity or threshold is unresolved, mark the path pending.

A nonterminal no-print that later resumes does not itself create an exit or censor.

If the path reaches t+60 with valid state observability and no exit, it receives the ordinary administrative censor at 60.

If unresolved price, identity, or threshold status prevents determining the path through t+60, the row is **not** silently censored into the hazard analysis. Its secondary status is pending and the secondary report is `WAIT_FOR_DATA_REPAIR` until resolved.

### 4A.7 Zero post-formation attrition gate

The primary confirmatory analysis requires **100% endpoint-status resolution** for every formation-valid confirmatory row:

- binary occupancy label 0/1 under the table above; and
- recorded endpoint status/reason.

Any `OUTCOME_PENDING_*` row makes `DL1_FINAL_READ_ELIGIBLE=false`.

Thus no post-formation disappearance can improve the result by disappearing from the denominator.

The structural-secondary hazard report, if ever opened after a primary pass, likewise requires zero `HAZARD_PENDING_*` rows; only ordinary administrative censoring at t+60 is permitted in its analyzed population.

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

The frozen five-market-session resolution grace for the last `DL1_OCCUPANCY_60` endpoint expires at offset 600.

Conservative one-reveal horizon = **601 market trading sessions from offset 0 through 600**, approximately 2.38 trading years.

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

All predictions and endpoint labels remain sealed from efficacy analysis until every final-eligibility predicate in §24 is true.

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

The power calculation must estimate the finite-sample behavior of the **actual frozen fitted procedure**. Synthetic oracle probabilities are permitted only to generate synthetic labels; they are never substituted for fitted S/A predictions in calibration or power adjudication.

No confirmatory efficacy outcome, confirmatory A−S statistic, confirmatory G-feature/outcome association, subgroup efficacy, or hazard association may enter this procedure.

### 23.1 Inputs allowed before the sole reveal

Power may use only:

- the fixed pre-outcome covariate matrices for all accrued B1–B9 rows;
- formation dates, industry groups, and **formation-time** abstention/source-status geometry only;
- B1–B3 matured `DL1_OCCUPANCY_20` labels;
- the frozen S/G definitions and estimator;
- no B4–B9 outcome label, terminal-event coding, endpoint missingness resolution, post-formation outcome status, or outcome-derived statistic.

B1–B3 labels are development/burn-in inputs. They may be processed mechanically for power and fitting, but no burn-in A−S or G-efficacy statistic is emitted to a researcher.

### 23.2 Baseline generator from S only

Using complete B1–B3 burn-in rows only:

1. fit the frozen ridge-logistic **S** model from §12 once, using the same winsorization/standardization rules;
2. call its fitted probability for any accrued row `p0_i`;
3. no G variable enters this baseline-generator fit.

For each burn-in formation date t:

- `n_t` = number of resolved burn-in rows;
- `s_t` = number with occupancy20=1;
- `q_t=(s_t+0.5)/(n_t+1)`;
- `pbar_t` = mean baseline-generator `p0_i` for rows on t;
- `a_t = logit(q_t) - logit(pbar_t)`, with q/p clipped to [1e-6,1−1e-6].

Estimate exactly one AR(1):

`phi = clip(sum_{t=2..36}(a_t*a_{t-1}) / sum_{t=1..35}(a_t^2), -0.95, 0.95)`.

Innovation variance is the mean squared residual of `a_t - phi*a_{t-1}` for t=2..36.

If the denominator is zero, set `phi=0`. If innovation variance is zero, use zero date shock.

No other dependence model is tried.

### 23.3 Frozen power-only peer direction

Using **B1–B3 covariates only**, compute one fixed mean/SD (ddof=0) for each of:

- `peer_continuity_20`;
- `breadth_q4_t`;
- `breadth_change_20`;
- `leader_dependency_hhi60`;
- `peer_residual_strength60`.

For every accrued row i define:

`z_i = mean(z_continuity, z_breadth, z_breadth_change, -z_dependency_hhi, z_peer_residual_strength)`.

`dependency_zero_positive` is not part of z.

These burn-in transformations are frozen for the entire power calculation.

`z_i` is a **data-generating device only**. It is never a fitted DL-1 feature reduction and never replaces the six-field G vector in A.

### 23.4 Synthetic data-generating law

For each simulation replicate, generate one shared formation-date shock process across **all 108 formation dates B1–B9**.

Use a stationary AR(1):

- `eta_0 ~ Normal(0, sigma2/(1-phi^2))` when `|phi|<1`;
- `eta_t = phi*eta_(t-1) + Normal(0,sigma2)`;
- if `sigma2=0`, all eta are zero.

For row i on formation date t:

`p_gen_i(beta) = logistic(logit(p0_i) + beta*z_i + eta_t)`.

Conditional on `p_gen`, draw each row's synthetic binary occupancy independently.

The oracle `p_gen` is used **only to draw labels**. It is never scored against S, never used as A, and never appears in the §17 test statistic.

### 23.5 Literal `RUN_SYNTHETIC_STUDY` procedure

Every simulated dataset is adjudicated by literal refitting.

For blocks B4, B5, ..., B9 in order:

1. select the synthetic training rows using the exact §14 rule: a row is admissible only when its full 60-market-session post-formation window ends strictly before the first market session of the evaluation block;
2. recompute the frozen §12 1st/99th winsor limits and mean/SD using those admissible training covariates only;
3. fit a fresh frozen ridge-logistic **S** model on the synthetic training labels;
4. fit a fresh frozen ridge-logistic **A** model on the same synthetic training labels;
5. produce OOS S and A predictions for that evaluation block;
6. seal the predictions and continue to the next block; later training may use earlier synthetic rows only when §14 makes them admissible.

After B9:
- concatenate only B4–B9 OOS predictions;
- compute `d_i = LogLoss_S - LogLoss_A`;
- compute the same `DeltaLogLoss20` and relative improvement as §§16/18;
- when the caller requests inferential adjudication, apply the exact §17 circular moving-block-bootstrap test using the same fixed 10,000 bootstrap block-index draws generated once from seed `2026100601`.

For §23.6 beta calibration, `RUN_SYNTHETIC_STUDY` performs every literal prequential S/A refit and OOS prediction above but does **not** run the bootstrap because `M(beta)` uses only fitted relative log-loss improvement. For §23.7 power estimation, the bootstrap is run exactly. This is a computational omission of an unused statistic, not an estimator shortcut.

No oracle shortcut is permitted.

If any S or A fit in any block violates the frozen §12 convergence rule, the entire power calculation returns `WAIT_FOR_MODEL_FIT`; failed simulation replicates are not silently discarded.

### 23.6 Calibrate the frozen 1% alternative on the fitted procedure

Define, for candidate beta:

`M(beta) = mean over synthetic datasets of [DeltaLogLoss20 / mean(LogLoss_S)]`

where every value is produced by `RUN_SYNTHETIC_STUDY`, not by oracle probabilities.

Using PRNG seed `2026100602`:

- generate exactly 2,000 full B1–B9 simulation random-number tapes and reuse the same tapes for every beta;
- bracket beta on [0,10];
- require `M(0) < 0.01` and `M(10) >= 0.01`; otherwise power eligibility fails;
- perform deterministic bisection for exactly 40 iterations:
  - midpoint = (lo+hi)/2;
  - if `M(midpoint) >=0.01`, set hi=midpoint;
  - otherwise set lo=midpoint;
- define `beta_star = hi`;
- require `|M(beta_star)-0.01| <= 0.0001`; otherwise return `WAIT_FOR_POWER_CALIBRATION`.

Thus the alternative is calibrated to **1.00% expected relative log-loss improvement of the actual finite-sample prequential fitted A over fitted S**, not to an oracle model.

### 23.7 Power estimate under literal refitting

Using independent PRNG seed `2026100603`:

1. generate exactly 20,000 new full B1–B9 synthetic datasets using `beta_star`;
2. for each dataset run `RUN_SYNTHETIC_STUDY` literally;
3. record success iff the §17 one-sided p-value is <0.05;
4. do not substitute the materiality, calibration, stability, or challenger gates into the statistical-power calculation; those remain separate final advancement requirements.

Estimated power:

`POWER = (# simulations with p<0.05) / 20000`.

Requirement: **POWER >=0.80**.

Monte Carlo standard error must be reported as `sqrt(POWER*(1-POWER)/20000)`; it does not change the 0.80 threshold.

### 23.8 Power firewall

The power engine may not:

- read B4–B9 real outcomes;
- fit A to any real confirmatory outcome;
- tune beta from real G/outcome associations;
- alter alpha, block length, sample floors, estimator, feature vector, or 1% effect floor;
- replace literal refitting with an oracle or analytical shortcut unless a later prereg amendment proves exact mathematical equivalence **before any efficacy read**.

The power calculation cannot run before the taxonomy source gate supplies lawful prospective peer geometry and B1–B3 have matured.

## 24. Final-read eligibility

`DL1_FINAL_READ_ELIGIBLE=true` requires all:

- DL-0 taxonomy source gate cleared before anchor;
- immutable preregistration frozen before anchor;
- >=80% power under §23;
- B1–B3 completed;
- B4–B9 completed;
- all 72 confirmatory formation dates accrued;
- all confirmatory t+60 windows matured and the five-session occupancy-resolution grace expired through offset 600;
- >=12 distinct confirmatory formation months;
- >=365 calendar days between first and last confirmatory formation date;
- >=1,000 matured primary rows;
- >=250 unique analyzed issuers;
- >=8 industry groups each with >=50 analyzed rows;
- each B4–B9 has >=100 complete rows;
- S+G coverage >=80%;
- identity/peer/challenger gates satisfied;
- exactly zero prior efficacy reveal;
- zero `OUTCOME_PENDING_*` primary rows;
- valid contemporaneous Q4 threshold for every resolved occupancy observation date;
- if the structural secondary is opened, zero `HAZARD_PENDING_*` rows.

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
