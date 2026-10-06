# 07 — DL-1 Preregistration Draft — Freeze-Ready Specification

**DRAFT FOR FREEZE. NO EFFICACY OUTCOME ACCESS AUTHORIZED.**

## Identity and route
Experiment: DL-1 additive independent-peer information for research leadership durability.
Fresh route: **PROSPECTIVE_US_POST_FREEZE**. Route locks at freeze. No pre-freeze row enters fitting, power N, confirmation, or inference.

## Research state — not product state
Define `DL1_RS126_Q4(t,i)=1` iff security i's 126-session market-relative total return at formation close t is at or above the 75th percentile of the eligible U.S. cross-section at t.

This is research-only. It is not Macro Leader Radar `LEADERSHIP`, Prophet rank, or ThemeState. Leader Radar keeps its own top-decile persistence, lifecycle evidence, hysteresis, and precedence.

## Endpoints
**Primary: DL1_OCCUPANCY_20.** Equals 1 iff `DL1_RS126_Q4(t+20,i)=1`. This is horizon occupancy, not continuous survival; an interim exit followed by re-entry still counts occupied.

**Structural secondary: DL1_FIRST_EXIT_60.** First session k=1..60 for which `DL1_RS126_Q4(t+k,i)=0`; right-censor at 60. This is the survival/hazard endpoint.

**Secondary: DL1_OCCUPANCY_60.** Q4 occupancy at t+60.

Forward return, MAE, recovery, prior-high reclaim, and Leader Radar product-state transitions are non-gating and default DO_NOT_READ.

## Formation clock and population
- Every fifth U.S. trading session from the first NYSE session after the final prereg freeze; that session is anchor 0.
- Features use formation close or earlier; outcomes begin t+1.
- Point-in-time S&P 1500 member.
- U.S. primary common-equity listing.
- At least 252 prior valid sessions.
- Resolved issuer identity.
- Contemporaneously captured GICS industry group.
- At least 15 independent peer issuers after focal/duplicate exclusion.
- One primary eligible listing per issuer.
- Future delisting is never a formation feature.

## Peer-universe law
Peers are all other eligible U.S. issuers sharing the focal issuer's contemporaneous GICS industry group at t. No international/global peers. Focal issuer and all alternate listings are excluded before statistics. Fewer than 15 peers => `ABSTAIN_PEER_N`.

## Frozen G feature vector

### Peer leader definition
`PEER_LEADER(t,j)=1` iff peer j is in the top quartile of the same 126-session market-relative-return U.S. cross-section. This is not Leader Radar LEADERSHIP.

### peer_continuity_20
Observation lag = 20 sessions. L0 = independent peers that were peer leaders at t-20 and valid peers at both t-20 and t. L1 = L0 members still peer leaders at t. `peer_continuity_20=|L1|/|L0|`. If |L0|<5, group vector is incomplete; abstain.

### breadth_q4_t and breadth_change_20
`breadth_q4_t` = fraction of valid independent peers that are peer leaders at t.
`breadth_change_20 = breadth_q4_t - breadth_q4_(t-20)`, using membership effective at each date. No retroactive constituent carry.

### leader_dependency_hhi60
For each peer j, `c_j=max(R60_market_relative_j,0)`. If sum(c)>0, `HHI=sum((c_j/sum(c))^2)`; otherwise HHI=0 and `dependency_zero_positive=1`.

### peer_residual_strength60
For each security, rolling 252-session OLS of daily excess return on U.S. market excess, SMB, HML, RMW, CMA, and UMD; require >=200 valid observations. `resid60` is sum of last 60 residuals. Peer residual strength is equal-weight mean peer resid60. Missing factor at t => abstain.

Frozen G = peer_continuity_20, breadth_q4_t, breadth_change_20, leader_dependency_hhi60, peer_residual_strength60. No other group feature enters DL-1.

## Identity and missingness
Existing issuer identity owner is authoritative. Unresolved focal identity => `ABSTAIN_IDENTITY`. Unresolved peers are excluded; if peer N falls below 15 => abstain. Any missing G => `ABSTAIN_GROUP_VECTOR`; any missing S => `ABSTAIN_STOCK_VECTOR`. No primary-analysis imputation.

Primary coverage gate: complete S+G for at least 80% of otherwise eligible DL1_RS126_Q4 rows. Below 80% => no efficacy read; `WAIT_FOR_DATA_OR_REPAIR`.

## Frozen stock baseline S
- own 20/60/120/252-session market-relative total returns;
- own resid60;
- annualized realized volatility 20/60/120;
- 252-session market beta;
- log market cap;
- log 20-session median dollar volume;
- broad GICS sector one-hot;
- formation-date market 126-session return;
- formation-date cross-sectional dispersion of 126-session returns.

Continuous predictors are winsorized at 1/99 percentiles and standardized using past-only training data; transforms are then frozen for the next evaluation block.

## Models
N = nuisance/base rate.
G = nuisance + frozen G.
S = frozen stock baseline.
A = S + G.

Primary models are unpenalized logistic regressions. If separation occurs, all four mechanically switch to the same preregistered Firth-logistic implementation.

**No interaction model exists in DL-1.** No stock×group products, tree/spline search, subgroup discovery, or nonlinear feature discovery. DL-2 owns interactions on new untouched evidence.

## Training and evaluation protocol
Formation observations accrue prospectively. Define non-overlapping 60-formation-session blocks B1, B2, ...

For evaluation block Bk:
- train on matured eligible rows in blocks strictly before Bk;
- embargo every training row whose 60-session outcome window overlaps Bk's first formation date;
- estimate winsorization/standardization on training only;
- fit N/G/S/A on training only;
- persist Bk predictions before Bk outcomes mature.

B1-B3 are burn-in only: no efficacy statistic or A-S outcome comparison may be inspected. First possible confirmatory block is B4, subject to final-read eligibility.

All predictions and matured labels remain sealed from efficacy analysis until the existing Evaluation/TrialLedger owner marks `DL1_FINAL_READ_ELIGIBLE=true`. One formal report, once. No interim A-S, feature-outcome, subgroup, or hazard-effect read.

## Primary estimand and materiality
Primary contrast: `DeltaLogLoss20 = mean(LogLoss_S)-mean(LogLoss_A)` on untouched confirmatory rows. Positive favors A.

One-sided H0: DeltaLogLoss20 <= 0. Inference uses 10,000 moving-block resamples/permutations with 60-formation-session blocks, seed 2026100601, preserving formation-date clusters; alpha 0.05.

Practical materiality requires BOTH:
1. `DeltaLogLoss20/mean(LogLoss_S) >= 0.01` (at least 1% relative log-loss improvement); and
2. `AME_CONTINUITY_PLUS20 >= 0.02`.

For AME_CONTINUITY_PLUS20, evaluate A prediction at factual G and at peer_continuity_20 increased by exactly 0.20 (capped at 1), all else fixed, averaging probability differences over rows with factual continuity <=0.80. This contrast is frozen independently; there is no post-read high/low group bin.

## Executable calibration gate
On untouched confirmation:
- calibration intercept in [-0.10,+0.10];
- calibration slope in [0.80,1.20];
- 10-equal-count-bin ECE <=0.03.
Any failure blocks advance.

## Executable stability/concentration gates
**Time:** for each confirmatory 60-session block with >=100 rows, compute DeltaLogLoss20. At least 70% must be >0 and no two consecutive eligible blocks may be <0.

**Industry group:** no single group may exceed 20% of confirmatory rows. For every group contributing >=5%, leave-one-group-out DeltaLogLoss20 must remain >0. Otherwise fail or WAIT_FOR_DATA if concentration is a coverage condition.

**Episode:** a 60-formation-session block may not contribute >25% of aggregate positive A-S log-loss improvement.

**Identity/coverage:** analyzed focal identity resolution =100%; complete S+G coverage >=80%; groups with >10% otherwise-eligible rows lost to unresolved peer identity cannot contribute to confirmatory inference.

## Challenger absorption gate
Fit `S_PLUS_COMMON` = S plus UMD cumulative returns over 20/60/120 sessions and broad-sector equal-weight 60/120-session relative returns excluding focal issuer when available.

Independent-peer claim fails if either:
- A does not beat S_PLUS_COMMON on log loss; or
- adding G to S_PLUS_COMMON yields <0.5% relative log-loss improvement.

No challenger selection after outcomes.

## Structural secondary hazard
Only after the primary occupancy20 gate passes may the sole report compute a discrete-time complementary-log-log model for DL1_FIRST_EXIT_60 using the same formation-fixed S and G. Report A-S hazard log-loss/integrated-Brier difference and calibration. Hazard cannot rescue a failed primary.

Occupancy60 is secondary and cannot rescue failure.

## Power and final-read eligibility
Before any efficacy read, an outcome-blind power receipt may use only observed eligible-row counts, primary endpoint base rate, missingness, and formation/group dependence. It may not use A-S differences or feature-outcome associations.

`DL1_FINAL_READ_ELIGIBLE=true` requires all:
- >=80% simulated power for the frozen 1% relative-log-loss materiality target at alpha .05 under the 60-session block procedure;
- >=12 distinct formation months;
- >=365 calendar days first-to-last confirmatory formation;
- >=6 eligible confirmatory 60-session blocks after burn-in;
- >=1,000 matured primary endpoint rows;
- >=250 unique issuers;
- >=8 industry groups with >=50 analyzed rows each;
- all identity/coverage gates above.

Any unmet floor => **WAIT_FOR_DATA**. No threshold lowering.

## Advance rule
Advance to separately preregistered DL-2 only if ALL:
1. primary one-sided A-S p<.05;
2. relative log-loss improvement >=1%;
3. AME_CONTINUITY_PLUS20 >=+0.02;
4. calibration passes;
5. time/group/episode stability passes;
6. identity/coverage passes;
7. challenger absorption gate passes;
8. G beats N on log loss (>0) as the group-information interpretation check.

Otherwise close this frozen additive industry-group construction.

## Permanent closure
Failure closes this exact combination: DL1_RS126_Q4 cohort, occupancy20 primary, GICS industry group, five-feature G, additive A-S, prospective-US route. No same-evidence retuning of threshold, horizon, peer floor, windows, factors, materiality, calibration, or subgroup.

## Abstention
Research row abstains on unresolved identity, missing contemporaneous industry group, <15 peers, incomplete G, incomplete S, or unavailable residualization factors. Abstention is reported, never imputed.

## DO_NOT_READ
Before final eligibility: A-S outcomes; G-feature/outcome correlations; subgroup efficacy; first-exit effect; occupancy60 effect; raw-return/MAE/recovery efficacy; Leader Radar transfer performance; PSS prospective outcomes; Top Anatomy OOT.

## DO_NOT_REDO
B2 path-shape family; C1/C2 sector construction; contaminated dates as confirmation; current taxonomy backcast; interaction discovery on DL-1 evidence; duplicate Leader Radar, peer engine, ThemeState, timeframe owner, outcome ledger, or ranker.

## Freeze requirements
Before DL-1 starts:
1. accept/merge an immutable prereg artifact;
2. record exact Mastermind/Macro pins;
3. record exact contemporaneous taxonomy capture source and five-rights basis;
4. register with existing look accounting;
5. record first eligible formation date;
6. begin outcome-blind prospective capture.

No DL-1 instrument implementation occurs in the present hardening pass.
