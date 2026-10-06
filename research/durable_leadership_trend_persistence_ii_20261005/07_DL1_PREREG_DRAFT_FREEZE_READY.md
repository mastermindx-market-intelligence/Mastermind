# 07 — DL-1 Preregistration Draft — Final Freeze-Ready Specification

**SOLE FREEZE-AUTHORITATIVE EXPERIMENT SPECIFICATION. NO EFFICACY OUTCOME ACCESS AUTHORIZED.**

**Scientific ruling:** `CONTINUE — NARROWED`  
**Operational state:** `WAIT_FOR_DATA / SOURCE_GATE`  
**Current protected reconciliation:** Mastermind `a6d40ff648671b03bd4d829d84dd066b58ea8c3f`; Macro `eae8baa8d3d4db35d5c9ac4f8e292143cf620854`

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

## 4A. Exhaustive endpoint attrition / delisting law

Post-formation status is part of the endpoint definition. **No future-state row is silently dropped.** Formation-time abstentions in §8 are the only statistical abstentions permitted. After a row forms, every future state maps deterministically to a label/event or to a typed unresolved status that blocks the relevant read.

### 4A.1 Daily Q4 comparison universe

For every U.S. market trading session d used by an occupancy or first-exit endpoint, define `RANK_EXPECTED(d)` as securities that, at d:

- are point-in-time S&P 1500 constituents under the existing membership owner;
- are U.S. primary common-equity listings;
- have resolved canonical issuer identity;
- have at least 126 valid panel-close observations through d;
- have no provenance-backed security termination effective before or on d.

Define `RANK_UNIVERSE(d)` as the subset of `RANK_EXPECTED(d)` with a valid **exact-session** panel close on d and sufficient SPY history to compute `RS_126`.

The focal security does **not** have to remain an S&P 1500 constituent after formation. `RANK_UNIVERSE(d)` supplies the comparison threshold even when the focal has left the index.

A daily threshold is valid only if:

- `|RANK_UNIVERSE(d)| >= 1000`; and
- `|RANK_UNIVERSE(d)| / |RANK_EXPECTED(d)| >= 0.98`.

Otherwise every DL-1 endpoint needing that date receives `PENDING_RANK_THRESHOLD`; the missing date is not skipped or substituted.

For a valid date:

`Q4_THRESHOLD(d) = quantile_0.75({RS_126(j,d): j in RANK_UNIVERSE(d)})`

using Hyndman-Fan type 7 linear interpolation, identical to NumPy `quantile(..., 0.75, method="linear")`.

A price from d−1 or d+1 is never substituted for d.

### 4A.2 Focal-security continuity law

After formation, follow the **formed economic security** through canonical security/issuer lineage:

- pure ticker rename, exchange transfer, or listing migration with provenance-backed continuity of the same security/issuer => continue on the canonical successor listing;
- acquisition/merger that legally terminates the formed security => terminal event even if consideration converts into an acquirer security;
- unproven successor continuity => no guessed splice.

Leaving the S&P 1500 by itself is neither an exit nor a censoring event.

### 4A.3 Deterministic outcome-status table

| Post-formation condition at required session d | `DL1_OCCUPANCY_h` treatment when d=t+h | `DL1_FIRST_EXIT_60` treatment | Statistical treatment |
|---|---|---|---|
| Focal remains PIT S&P 1500 member; exact valid close; valid daily Q4 threshold | 1 iff focal `RS_126(d) >= Q4_THRESHOLD(d)`, else 0 | first session with focal `RS_126(d) < Q4_THRESHOLD(d)` is exit | labeled |
| Focal left S&P 1500 but remains same continuously identified, listed, priceable security | same 0/1 rule against **current** `RANK_UNIVERSE(d)` threshold | same rank-exit rule; index removal alone is not exit | labeled; never dropped for membership attrition |
| Proven ticker rename / exchange transfer / primary-listing migration with canonical same-security continuity | follow successor listing and apply same 0/1 rule | continuity preserved; exit only by rank or later terminal rule | labeled |
| Proven acquisition/merger effective on or before d that terminates formed security | 0 for every endpoint on/after effective session | terminal exit at first U.S. market session on/after effective timestamp | labeled event, never censored |
| Proven delisting/security termination effective on or before d | 0 | terminal exit at first U.S. market session on/after effective timestamp | labeled event |
| Bankruptcy/reorganization **with proven security termination or primary-listing termination** | 0 on/after termination | terminal exit on effective termination session | labeled event |
| Bankruptcy/reorganization filing while the same primary security continues trading | normal rank rule | normal rank rule | labeled; bankruptcy filing alone is not terminal |
| Loss of primary listing with **no** provenance-backed continuous successor | 0 on/after effective loss | terminal exit on effective loss session | labeled event |
| Proven security-specific halt/suspension/no official close on an otherwise open U.S. market session | 0 if the halt spans t+h | first confirmed halt/suspension session is an exit | labeled event; not administrative missingness |
| Exact-session close absent because source delivery/backfill is late, while source/market status does not prove halt or termination | `PENDING_PRICE_DATA` | `PENDING_PRICE_DATA` for that daily state | no label/censor/abstention; read blocked until exact-session fact resolves |
| Price remains permanently unavailable and no provenance-backed halt/terminal/continuity status exists | `UNRESOLVED_PRICE_PERMANENT` | `UNRESOLVED_PRICE_PERMANENT` | no label/censor/abstention; relevant read permanently blocked |
| Price-basis/corporate-action adjustment is unresolved so `RS_126` is not comparable | `UNRESOLVED_PRICE_BASIS` | `UNRESOLVED_PRICE_BASIS` | no imputation; relevant read blocked |
| Daily Q4 threshold fails §4A.1 coverage | `PENDING_RANK_THRESHOLD` | `PENDING_RANK_THRESHOLD` | no label/censor/abstention; relevant read blocked |
| Same security survives and stays at/above Q4 on every determinable session 1..60 | n/a | right-censor at 60 | **only** permitted right-censoring case |

### 4A.4 Endpoint resolution law

For the **primary occupancy read**, every otherwise analysis-admissible formed row must end in exactly one of:

- `OCCUPIED=1`; or
- `OCCUPIED=0` including deterministic terminal/halt states above.

Required primary endpoint resolution rate = **100%**.

Any `PENDING_*` or `UNRESOLVED_*` primary row means `WAIT_FOR_OUTCOME_DATA`; the row is not removed from N, denominator, power floor, or reporting.

For the structural first-exit endpoint, administrative missingness is never treated as independent censoring. The hazard report may open only when every required daily state through exit/censor is determinable. Otherwise its status is `WAIT_FOR_HAZARD_DATA`. This secondary wait cannot change the primary occupancy verdict.

### 4A.5 Provenance rule for terminal states

A post-formation terminal/halt/continuity classification must be backed by the existing canonical security/identity/corporate-action source available to the study and carry an effective timestamp plus source receipt. If the estate cannot prove which condition occurred, the row remains typed unresolved. **Last price, zero price, average imputation, inferred acquisition, and future constituent status are forbidden substitutes.**

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
- every training row whose endpoint should have matured under the calendar must have a resolved primary status under §4A; otherwise the block is `WAIT_FOR_OUTCOME_DATA`;
- compute transforms from eligible training rows only;
- fit N/G/S/A on training rows only;
- seal all Bk predictions before any Bk outcome matures.

No post-formation missing/terminal row is removed to make a fit possible. Deterministic terminal states enter with their frozen 0 label; administrative unresolved states block the fit until resolved.

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
4. Instantiate NumPy `Generator(PCG64(2026100601))`. For each of exactly 10,000 replicates:
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

## 23. Exact outcome-blind power simulation — literal fitted-procedure refitting

The power calculation must emulate the **same finite-sample fitted S-versus-A procedure** used by the study. No oracle `p_A` may be scored directly against a stored `p_S`.

Confirmatory efficacy outcomes remain sealed. Power may use:

- B1–B3 matured primary labels after §4A resolution;
- all B1–B9 formation-time covariates and row identities because they existed before each row's outcome;
- formation dates, group/sector identities, abstention geometry, and source-quality metadata;
- no B4–B9 outcome labels, A−S differences, G-feature/outcome associations, subgroup efficacy, or hazard outcomes.

If B1–B3 primary labels are not 100% resolved under §4A, power status is `WAIT_FOR_OUTCOME_DATA`.

### 23.1 Frozen baseline outcome generator

Pool B1–B3 rows only.

Using the exact estimator and transform law in §12:

1. estimate S-training winsorization/standardization from pooled B1–B3 S covariates;
2. fit one ridge-logistic **generator-S** to the real B1–B3 `DL1_OCCUPANCY_20` labels;
3. apply that frozen generator transform/model to every B1–B9 row to obtain `p0_i`.

This generator is used only to define the synthetic data-generating process. Its coefficients are not a DL-1 efficacy result and are not shown to the researcher before the final read.

For each B1–B3 formation date t:

- observed rate `q_t=(s_t+0.5)/(n_t+1)`;
- generator mean `m_t=mean_i(p0_i)` across that date's burn-in rows;
- date residual `a_t = logit(q_t) - logit(m_t)`.

Estimate exactly one AR(1):

`phi = clip(sum_{t=2..36}(a_t*a_{t-1}) / sum_{t=1..35}(a_t^2), -0.95, 0.95)`.

Innovation variance:

`sigma2 = mean((a_t - phi*a_{t-1})^2)`, t=2..36.

If the denominator is zero, `phi=0`. If `sigma2=0`, all synthetic date shocks are zero. No alternative dependence model is tried.

### 23.2 Frozen outcome-blind peer-direction score

Construct a simulation-only scalar `z_i` from the five continuous G fields:

- `peer_continuity_20`;
- `breadth_q4_t`;
- `breadth_change_20`;
- negative `leader_dependency_hhi60`;
- `peer_residual_strength60`.

For each field, mean and population SD are estimated **once from pooled B1–B3 formation covariates only**. Standardize every B1–B9 row using those frozen burn-in moments, then take the arithmetic mean of the five standardized values.

If any required burn-in SD is zero, power status is `WAIT_FOR_POWER_GEOMETRY`; no field is dropped or reweighted.

`dependency_zero_positive` remains an A-model feature but is not included in `z_i`.

`z_i` is a synthetic-alternative direction only. It is never a fitted DL-1 score and never enters actual S or A predictions except through A's own six frozen G regressors.

### 23.3 Synthetic outcome law

For a candidate scalar beta >=0, each synthetic dataset spans all B1–B9 rows.

Instantiate independent date shocks:

- initial `eta_1 ~ Normal(0, sigma2/(1-phi^2))` when `sigma2>0`; otherwise 0;
- `eta_t = phi*eta_(t-1) + epsilon_t`;
- `epsilon_t ~ Normal(0, sigma2)`.

For row i on formation date t:

`p_true_i(beta) = logistic(logit(clip(p0_i,1e-6,1-1e-6)) + beta*z_i + eta_t)`.

Generate:

`Y_i ~ Bernoulli(p_true_i(beta))`.

No real B4–B9 endpoint label enters this law.

### 23.4 Literal prequential refit inside every simulated dataset

For **every** synthetic dataset and for every confirmatory block B4 through B9:

1. construct the synthetic training set using exactly §14: only prior rows whose full 60-market-session post-formation window ends strictly before the first market session of the evaluation block;
2. use the synthetic `Y` values for those training rows;
3. re-estimate that block's 1st/99th-percentile winsorization and mean/ddof=0 SD from the synthetic training rows' covariates exactly as §12;
4. literally refit the frozen ridge-logistic **S** model with lambda=1;
5. literally refit the frozen ridge-logistic **A** model with lambda=1;
6. apply those fitted models to the evaluation block's frozen covariates;
7. store the synthetic OOS `LogLoss_S`, `LogLoss_A`, and `d_i`.

The same convergence criterion, zero-variance rule, no-class-weight rule, no-fallback rule, and clipping law apply.

A synthetic dataset in which any required block returns `WAIT_FOR_MODEL_FIT` counts as a **non-rejection** for power. It is never repaired by changing the estimator or dropping a predictor.

This is literal finite-sample refitting. No synthetic oracle probability is used as an evaluated A prediction.

### 23.5 Calibrate beta to the frozen 1% fitted-procedure alternative

Use NumPy `SeedSequence(2026100602)` to spawn exactly 2,000 independent `PCG64` dataset streams. Reuse the same streams/common random numbers for every beta evaluation.

For a given beta:

- simulate each full B1–B9 dataset under §23.3;
- execute the literal refitting procedure in §23.4;
- concatenate B4–B9 OOS predictions;
- for successful-fit simulations compute

`RI_r(beta) = (mean(LogLoss_S) - mean(LogLoss_A)) / mean(LogLoss_S)`;

- failed-fit simulations contribute `RI_r=0`.

Define `F(beta)=mean_r(RI_r(beta))`.

Solve beta on [0,10] by deterministic bisection for:

`F(beta)=0.010000`

with absolute tolerance `1e-5` and at most 60 iterations.

The endpoints beta=0 and beta=10 are evaluated first. If they do not bracket 0.010000, or if bisection does not reach tolerance within 60 iterations, power gate fails with `POWER_ALTERNATIVE_NOT_CALIBRATABLE`.

The 1% target is therefore defined on the **actual fitted prequential A-versus-S procedure**, not on oracle probabilities.

### 23.6 Power estimate under literal refitting

Use independent NumPy `SeedSequence(2026100603)` to spawn exactly 20,000 independent `PCG64` dataset streams.

For each synthetic dataset:

1. generate B1–B9 outcomes using the calibrated beta and §23.3;
2. literally refit S and A for B4–B9 under §23.4;
3. if any required fit fails, record non-rejection;
4. otherwise compute confirmatory `d_i`;
5. apply the exact §17 one-sided circular moving-block bootstrap;
6. record rejection iff `p<0.05`.

Estimated power = rejected datasets / 20,000.

Requirement: **estimated power >=0.80**.

No alpha, effect floor, sample floor, block length, model, or bootstrap count changes if power is below 80%. Status remains `WAIT_FOR_DATA`.

### 23.7 Exact bootstrap acceleration permitted — refitting may not be shortcut

Literal S/A refitting in §23.4 is mandatory.

After a simulated dataset has produced fixed OOS `d_i`, §17's row-level bootstrap may be computed with formation-date sufficient aggregates only:

- `N_t = count(rows on formation date t)`;
- `C_t = sum_i_on_t(d_i - Delta)`.

For any bootstrap multiset of formation dates with multiplicities `m_t`:

`Delta_star = sum_t(m_t*C_t) / sum_t(m_t*N_t)`.

This is **algebraically identical** to duplicating every selected row with the same formation-date multiplicity and taking the row-weighted mean required by §17. Therefore date aggregation changes neither the bootstrap sample nor statistic; it is only a computational representation.

No analogous shortcut is permitted for fitting S or A.

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
