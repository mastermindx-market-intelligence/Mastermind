# Intraday Hierarchical Leadership & Resilience — Extended Review and Audit

**Status:** research architecture audit; no implementation, trading, sizing, data-purchase, or production authority  
**Audit date:** 2026-10-05  
**Protected Mastermind base reviewed:** `7eac3ec252475600147ec9a376b8ca16403ac4c5`  
**Primary commission:** “Intraday Hierarchical Relative Strength, Volatility, Resilience, Theme Leadership & Durable Equity Strength”  
**Verdict:** **ADVANCE WITH MAJOR REVISION**

## 1. Executive answer

The durable-leader thesis is credible enough to justify a new empirical program, but not in the form implied by the motivating narrative and not as a single “leadership” construct.

The strongest defensible research claim is narrower:

> **Conditional response to adverse benchmark shocks may contain stock-level holdability information that is not identical to ordinary trailing momentum, unconditional volatility, or endpoint relative strength.**

That claim is materially more defensible than “leaders are easy to hold because institutions buy every dip.” Price alone cannot identify institutional accumulation, and the literature supports multiple competing mechanisms: passive/index demand, systematic factor demand, information diffusion, short covering, dealer hedging, low-float mechanics, and liquidity provision.

The program should therefore be decomposed into independently falsifiable evidence families. The recommended first-wave ordering is:

1. market-residual strength and time-of-day normalization;
2. **shock resilience** against market shocks;
3. rank persistence;
4. residual continuity/jump concentration;
5. exhaustion/early-warning conditional on already-high medium-horizon RS;
6. PIT industry context after taxonomy repair;
7. economic-link propagation;
8. trade/quote microstructure only after minute-bar evidence survives.

Broad-sector “theme first, stock second” is **not** a justified starting prior. Mastermind’s latest C1 result is a direct warning against it. C1 returned `C1-NULL`: nothing was carried from the tested eleven-sector, as-of-now-labelled, survivor-tilted, daily rank-linear constructions at principally 20- and 60-session horizons. That result does **not** close industry, static-basket, dynamic-theme, economic-network, intraday, or shock-response constructions, but it raises the burden of proof for every new group feature.

Likewise, Wave B/B2 is a critical null. Generic daily path-quality and drawdown-shape variables appeared associated with future drawdown, yet volatility-only simulated markets reproduced much of the behavior. When a strong trailing-return/beta/volatility baseline was used in walk-forward comparison, incremental rank IC was only about 0.001–0.002 on a base near 0.49–0.53 and nothing advanced. Any intraday “smoothness,” “gain retention,” “near highs,” or “easy to hold” feature must therefore beat an explicit volatility/jump/event baseline rather than merely correlate with future drawdown.

**Bottom line:** advance the empirical program, but redefine the north star from “find the leaders institutions are supporting” to **“measure incremental residual strength, conditional shock response, and leadership-state deterioration after conventional momentum, beta, volatility, liquidity, event magnitude, and group exposures are accounted for.”**

## 2. Existing-evidence ledger

| Evidence | What it establishes | What it does **not** establish | Audit consequence |
|---|---|---|---|
| Wave B V1 forward-return result | No tested path/gain-retention family cleared the forward-relative-return gates. | It does not close all intraday conditional-response features. | Do not repackage daily path smoothness as intraday alpha. |
| Wave B/V2 holdout | 29 tests on 12 features passed pre-registered drawdown gates. | The effects were not distinguished from volatility. | Holdability labels must be volatility-aware. |
| Volatility-only simulations | Markets with no trend persistence reproduced many path/drawdown findings. | They do not prove all path information is volatility. | Every path feature needs a volatility/jump null. |
| Wave B2 walk-forward | Incremental model value was negligible; family stopped at Wave B for those constructions. | It does not close conditional shock-response or microstructure features. | Strong baseline is mandatory. |
| Wave C1 | `C1-NULL`; no sector group-return cell carried beyond B*. | Industry, basket, dynamic theme, network, intraday and resilience are untested. | Broad-sector group priors are demoted. |
| `brain/trend_persistence.py` | Existing descriptive return/path/high/drawdown substrate. | Not a validated predictive leadership engine. | Reuse; do not duplicate. |
| `brain/rotation_tensor.py` | Existing owner for pairwise sector RS velocity, breadth migration, leadership churn, RVOL/ETF-flow proxies, episodes. | Does not validate those fields as predictive durable-leader features. | New group measures must extend/feed this owner. |
| Thematic rotation doctrine | Encodes RS/breadth/flow/catalyst/lifecycle hypotheses. | It is doctrine, not empirical truth. | Treat “theme first” and “dip absorption” as hypotheses. |
| Prediction/outcome machinery | Date clustering and realized-outcome ownership already exist. | Minute bars are not independent samples. | No new outcome ledger; cluster by session/event. |

### C1 scope boundary

The current C1 decision is narrow and correctly worded: the family stops at Wave C **for the eleven GICS-sector, as-of-now-labelled constructions tested on that universe, horizons, feature set and rank-linear form**. The result explicitly states that GICS industry-group/industry, basket and dynamic-theme constructions are untested and not closed.

The audit rejects both overstatements:

- “Academic industry momentum proves Mastermind should use group-first leadership.”
- “Mastermind disproved group persistence.”

Neither follows from the evidence.

## 3. Literature reconciliation

### Industry and factor momentum

Moskowitz & Grinblatt (1999) document strong industry momentum and show that controlling for industry momentum materially reduces conventional stock momentum. Ehsani & Linnainmaa (2022) show that momentum in high-eigenvalue factors can subsume much stock momentum in the U.S.; later international evidence is more mixed and reports that empirical factor momentum is neither ubiquitous nor always able to explain stock momentum outside prominent large-cap markets.

This is not inconsistent with C1. The designs differ on taxonomy granularity, era-correct membership, sample, horizon, weighting, baseline strength, and statistical question. C1 asks whether six surviving **broad-sector state features** add cross-sectional predictive information beyond a very strong member-level baseline. The classic industry literature often asks whether industry components themselves explain momentum profits. These are related but not identical estimands.

**Resolution:** industry/factor context remains plausible, but the next test should not be “C1 again with more features.” It should use finer PIT taxonomy and a clean decomposition of systematic versus stock-specific residual return.

### Residual momentum

Blitz, Huij & Martens (2011) report that ranking on residual rather than total returns reduces conventional factor exposures and produces more consistent risk-adjusted momentum in their sample. This supports separating common/group leadership from stock-specific leadership.

But “residual momentum” is not automatically a new signal. If residualization simply removes beta and factors from the same trailing return, the result remains a momentum transformation. The empirical question is whether **conditional response, path, or rank dynamics of residual returns** add information beyond cumulative residual return itself.

### Continuous versus discrete information

Da, Gurun & Warachka (2014) find a large monotonic difference in subsequent momentum between continuous- and discrete-information winners with similar cumulative formation returns. A 2024 study reports that the FIP relationship is concentrated in up-market states, reinforcing the need for regime conditioning. A 2022 JFE paper extends information-discreteness logic to lead-lag returns among economically linked firms.

This motivates residual continuity, but Mastermind’s Wave B/B2 null means the bar is high. Intraday continuity should advance only if, **among stocks matched on cumulative residual return, realized variance/semivariance, jump contribution, gap/event status and liquidity**, it predicts future return, MAE, or rank survival.

### Momentum failure and regime

Daniel & Moskowitz (2016) show momentum crashes concentrate after severe market declines, high volatility, and sharp rebounds. This directly supports regime interaction. The correct use is not an ad hoc crash veto; it is a pre-specified interaction or stratified calibration test.

### Economic links, flows and microstructure

Cohen & Frazzini (2008) document customer-supplier return predictability. Newer production-complementarity work reports cross-industry lead-lag effects. This lane is distinct from static theme ranking because the estimand is **propagation with lag**.

Flow-based research makes capital-flow pressure a plausible mechanism for persistent price effects, but not an inference available from OHLCV. Recent passive-investing work also shows that index flows can disproportionately affect large constituents and can raise idiosyncratic volatility.

Cont, Kukanov & Stoikov (2014) find short-horizon price changes are more robustly related to order-flow imbalance than raw trade volume, with impact inversely related to depth. Queue-imbalance and limit-order-book resiliency studies give “easy to hold” a legitimate microstructure analogue — **resiliency** — while still not allowing price-only inference about who supplied liquidity.

## 4. Major audit findings

### BLOCKER A — sequential residualization is order-dependent

The proposed hierarchy is interpretable, but correlated market/factor/sector/industry/theme returns make sequential residualization order-dependent.

**Required revision:** preregister a primary simultaneous model and treat sequential decomposition as an attribution diagnostic.

For stock (i), session (d), minute (t):

[
r_{i,d,t}=alpha_i+eta_{i,m}r_{m,d,t}+mathbf{b}_{i,f}'mathbf{f}_{d,t}
+gamma_{i,g}r_{g,-i,d,t}^{perp}
+delta_{i,	heta}r_{	heta,-i,d,t}^{perp}+epsilon_{i,d,t}.
]

Use leave-one-out group/theme returns. Exposures must be estimated only from information available before the formation session. If intraday betas are unstable, estimate stable daily exposures on a trailing window and apply them intraday.

Compare market-only, market+factor, market+factor+group, sequential/FWL-equivalent, and shrinkage/ridge versions.

### BLOCKER B — theme-relative historical confirmation is not currently identified

Current C1 sector labels are explicitly as-of-now and survivor-tilted. Dynamic themes are even more vulnerable to back-projection.

**Required revision:** historical confirmatory hierarchy = PIT sector → PIT industry/group → evidenced static baskets. Dynamic themes should begin append-only effective-dated prospective capture. Present-day-membership historical theme tests are exploratory/contaminated only.

### BLOCKER C — shock events must be exogenous to the candidate stock

If a “theme shock” is partly created by stock (i), shock and response are mechanically coupled.

**Required revision:** define benchmark shocks from leave-one-out baskets and impose a refractory period so one shock episode does not become dozens of pseudo-independent minute events.

### MAJOR D — raw downside-capture ratios are unstable

A ratio (r_i/r_b) under small negative benchmark returns can explode. Prefer conditional negative-state slope, standardized response difference, event-window residual return, or trailing downside beta. Keep raw ratios descriptive only with a denominator floor.

### MAJOR E — recovery is a first-passage/censoring problem

For a shock at (t_0), let (C_{i,t}=sum_{	au=t_0}^{t}epsilon_{i,	au}). Define

[
T^{rec}_{i}=inf{h>0:C_{i,t_0+h}ge 0},
]

right-censored at the chosen horizon/session close, and

[
MAE^{res}_{i,H}=min_{0le hle H} C_{i,t_0+h}.
]

This directly operationalizes “dip gets bought” without implying a buyer identity.

### MAJOR F — continuity requires a jump-aware null

Positive-bar fraction or path efficiency can be inverse volatility/jump exposure. Match/control on cumulative residual return, realized variance, downside semivariance, overnight gap, event status and jump contribution.

### MAJOR G — exhaustion needs a landmark/hazard design

At fixed landmarks, condition on medium-horizon RS still being high and predict a future break. Candidate warnings must be known before the break: 5D/intraday residual-RS slope, shock MAE, recovery time, downside semivariance, rank instability, and PIT group breadth deterioration. The key endpoint is **lead time versus conventional RS roll-over**, not accuracy after breakdown.


## 5. Formal candidate feature specification

### 5.1 Base intraday return

[
r_{i,d,t}=log(P_{i,d,t}/P_{i,d,t-1}).
]

Regular trading hours should be primary in V1. Overnight gap and extended-hours state should be separate covariates, not silently mixed into the same minute-seasonality curve.

### 5.2 Time-of-day standardized residual strength

For residual (epsilon_{i,d,t}), estimate a pre-(d) expected variance curve:

[
hat{sigma}_{i,	au}^{2}=E[epsilon_{i,d,	au}^{2}mid mathcal{F}_{d-1}].
]

Then

[
RSZ_{i,d,t}=
rac{sum_{	aule t}epsilon_{i,d,	au}}
{sqrt{sum_{	aule t}hat{sigma}_{i,	au}^{2}}}.
]

Primary seasonality candidates:

1. stock-specific robust curve when history/liquidity is sufficient;
2. liquidity-bucket curve otherwise;
3. EWMA scale overlay for current market-volatility regime.

Do not use future-known “event adjustment.” Event-day status may be a contemporaneously known control only when its timestamp is PIT-safe.

### 5.3 Residual semivariance

[
RV^+_{i}=sum_t epsilon_{i,t}^{2}mathbf{1}(epsilon_{i,t}>0),quad
RV^-_{i}=sum_t epsilon_{i,t}^{2}mathbf{1}(epsilon_{i,t}<0).
]

[
UpsideShare_i=rac{RV^+_i}{RV^+_i+RV^-_i}.
]

This family is not presumed distinct. It must add beyond total realized variance, downside variance and cumulative residual return.

### 5.4 Shock definition

For benchmark (b), compute time-of-day standardized benchmark residual return (z_{b,d,t}). A primary adverse shock candidate is:

[
Shock_{b,d,t}=1[z_{b,d,t}le -k],
]

with (k) fixed before the confirmatory run. Use a refractory window (R) so repeated threshold crossings inside one episode are one event. Theme/industry shocks must be leave-one-out with respect to stock (i).

The event timestamp is the first threshold crossing. Features measured after the crossing may predict only horizons strictly after their measurement cutoff.

### 5.5 Shock resilience

For event (e=(b,d,t_0)):

**Shock alpha**
[
ShockAlpha_{i,e,H}=sum_{h=0}^{H}epsilon_{i,t_0+h}.
]

**Residual MAE**
[
MAE^{res}_{i,e,H}=min_{0le hle H}sum_{u=0}^{h}epsilon_{i,t_0+u}.
]

**Recovery time**
[
T^{rec}_{i,e}=inf{h>0:sum_{u=0}^{h}epsilon_{i,t_0+u}ge 0}.
]

**Recovery half-life**
[
T^{1/2}_{i,e}=inf{h>0:C_{i,t_0+h}ge 	frac{1}{2}|C_{i,t_0+h^*}|},
]
where (h^*) is the time of maximum adverse residual displacement inside the initial shock window.

**Recovery probability**
[
Pr(T^{rec}_{i,e}le Hmid X_{i,e})
]
for 5m, 15m, 30m, 60m and remainder-of-day horizons.

The primary test should ask whether resilience measured on prior shocks predicts a later outcome, not whether a stock that already recovered is contemporaneously strong.

### 5.6 Asymmetric beta

Estimate on trailing pre-formation data:

[
eta_{up}=rac{Cov(r_i,r_bmid r_b>0)}{Var(r_bmid r_b>0)},qquad
eta_{down}=rac{Cov(r_i,r_bmid r_b<0)}{Var(r_bmid r_b<0)}.
]

Candidate asymmetry:

[
Aeta_i=eta_{up}-eta_{down}.
]

This is a control/competitor to event resilience, not automatically a separate feature family.

### 5.7 Continuous versus discrete residual strength

For positive residual contributions (g_t=max(epsilon_t,0)):

[
GainConcentration_i=sum_tleft(rac{g_t}{sum_j g_j}ight)^2.
]

Also test largest-positive-bar share, sign-based information discreteness, and jump share:

[
JumpShare=rac{max(RV-BV,0)}{RV},
]

where (BV) is a jump-robust bipower-variation estimate.

The critical matched test is: **same cumulative residual return, similar RV/downside RV/jump share/liquidity/event status; different continuity.**

### 5.8 Rank persistence

Let (q_{i,t}in[0,1]) be the cross-sectional residual-strength percentile.

[
RankPersistence_{i,H}(q^*)=rac{1}{N_H}sum_{tin H}mathbf{1}(q_{i,t}ge q^*).
]

Also predefine rank volatility, maximum rank drawdown, first-entry time into the top decile, loss/reclaim count, and area above a threshold. The test must control for endpoint rank and cumulative residual return.

### 5.9 High occupancy

Price high occupancy:

[
HighOcc_{i,H}(c)=rac{1}{N_H}sum_t mathbf{1}(P_{i,t}ge ccdot High_{i,H}(t)).
]

More defensible variants are residual-high occupancy and occupancy conditional on benchmark drawdowns. This family has a high prior probability of redundancy with distance-to-high and volatility and should receive a strict kill rule.

### 5.10 Group state

For PIT group (g), candidate state variables are group residual return/RSZ, breadth, new-high participation, residual-positive share, dispersion, coherence, leader retention, rank churn, downside capture and shock recovery.

Novelty versus C1 must be explicit: finer taxonomy, PIT membership, intraday normalization, conditional shocks, or economic-network structure. Re-running broad-sector daily persistence with renamed variables is not novel.

### 5.11 Exhaustion

At landmark (t), eligible names satisfy a fixed medium-horizon leadership condition such as

[
Rank(RS^{60d}_{i,t})ge 0.90.
]

Define a future leadership break without using post-(t) information in features. Candidate hazard covariates:

[
Delta RS^{5d}, Delta RS^{intra}, DownCapture, T^{rec}, RV^-, RankVol, Delta Breadth_g, Delta LeaderRetention_g.
]

The family advances only if it predicts the break with positive lead time while 60D RS is still high.

## 6. Feature redundancy map

| Candidate | Likely hidden parent | Distinct only if… | Audit prior |
|---|---|---|---|
| Raw RS | momentum | — | baseline |
| Residual RS | momentum + factor neutralization | OOS benefit survives simpler factor controls | test |
| RSZ | residual momentum / volatility scaling | adds beyond residual return + RV | test as normalization, not alpha claim |
| Upside variance share | semivariance | adds beyond RV and downside RV | low-medium |
| Shock MAE/recovery | beta + vol + liquidity | conditional event response adds after controls | **high-value test** |
| Asymmetric beta | conditional beta | adds beyond shock event features | medium/control |
| Gain concentration/FIP | vol + jumps + event magnitude | matched residual-return/vol/jump test survives | medium |
| Rank persistence | momentum path | endpoint RS controlled and path still matters | medium-high |
| High occupancy | distance-to-high + vol | residual/conditional form survives | low |
| RVOL | liquidity/event intensity | non-monotonic or interaction value survives | control |
| Group breadth/state | group momentum | adds after stock momentum and PIT group return | uncertain after C1 |
| OFI/depth/replenishment | microstructure | adds beyond minute-bar resilience | V2 only |

### Minimal nonredundant V1 set

The audit recommends resisting a large feature zoo. The smallest defensible first set is:

1. cumulative market-residual return;
2. time-of-day standardized residual return (normalization);
3. realized variance and downside semivariance;
4. prior-shock residual MAE and recovery-time summary;
5. endpoint residual-rank + rank persistence;
6. jump/gain concentration;
7. liquidity/RVOL/gap/event controls;
8. market regime.

Industry/group fields should enter only after PIT repair. High occupancy is secondary. Raw “gain retention” should not return as a primary family.

## 7. Falsification matrix

| Family | Hypothesis | Major confounds | Mandatory controls | Endpoint | Kill condition | Advance condition |
|---|---|---|---|---|---|---|
| Hierarchical residual RS | Neutralized RS beats raw RS | factor estimation error, collinearity | raw momentum, beta, vol, size, liquidity | forward residual return/rank | no OOS IC/economic gain | stable incremental OOS gain |
| Theme/group interaction | strong group × strong stock helps | stock momentum already contains group return | stock residual RS, group return/vol, PIT membership | return, MAE, rank survival | additive/interaction terms add nothing | robust gain across groups/eras |
| Shock resilience | low capture/fast recovery predicts durability | low beta, low vol, liquidity, event size | beta, asymmetric beta, RV, spread proxy, gap/event | later return, MAE, recovery/rank survival | effect collapses after controls | monotone, OOS, not one regime |
| Continuity | gradual residual gains are more durable | volatility/jumps/events | cumulative residual return, RV, semivariance, jump share | continuation/MAE | matched groups indistinguishable | robust matched OOS difference |
| Rank persistence | persistent top rank matters | endpoint rank/momentum | endpoint RS, RV, liquidity | rank survival/return | path terms vanish | incremental survival/IC |
| RVOL/participation | volume relation is non-monotonic | event days, liquidity | dollar volume, gap, RV, event status | continuation/MAE | simple RVOL dominates | refined participation adds OOS value |
| Exhaustion | deterioration leads RS break | tautology/look-ahead | current 20D/60D RS, RV, regime | future break/hazard | no positive lead time | calibrated hazard + lead time |
| Regime interaction | panic/rebound changes continuation | sparse crashes | predefined regime state | all above | no interaction/calibration gain | stable stratified improvement |
| Economic links | strength propagates with lag | common factors, stale links, multiple testing | factor/group residuals, PIT graph | 30m–20D residual return | effect dies under PIT/lag/FDR | robust edge across link types/eras |
| Microstructure V2 | OFI/depth adds beyond bars | latency, tick size, costs | all V1 features | resilience/short-horizon outcome | negligible incremental value | material OOS gain justifies cost |


## 8. Empirical preregistration proposal

This is a proposal for the next data-science owner to freeze after data QA. It is intentionally conservative.

### Universe

**Primary:** point-in-time S&P 1500 common-stock membership, preserving leavers and ticker history.

**Secondary robustness:** broader U.S. common-stock universe with predeclared price and dollar-volume thresholds. It must not replace the primary after seeing results.

ETFs, ADRs, preferreds, warrants, closed-end funds and other non-common-stock instruments should be separately classified rather than allowed to drift into the primary universe.

### Historical period

Minute aggregates are documented back to 2003-09-10. Proposed research calendar:

- **burn-in / seasonality estimation:** 2003-09-10 through 2004-12-31;
- **development:** 2005-01-03 through 2018-12-31;
- **validation:** 2019-01-02 through 2022-12-30;
- **untouched final holdout:** 2023-01-03 through 2026-06-02.

The 2026-06-02 endpoint aligns with the current membership substrate boundary and avoids pretending later PIT coverage is already repaired. If the final data repair changes the valid end date, change the calendar **before any candidate-label relationship is computed** and re-freeze it.

No dynamic-theme confirmatory test should use this historical split unless PIT membership exists for the entire relevant interval.

### Formation snapshots

Primary fixed RTH snapshots:

- 10:00 ET;
- 11:00 ET;
- 13:00 ET;
- 15:00 ET.

The open and close should be studied separately because auction/opening/closing dynamics differ. Do not add more snapshots after seeing candidate performance.

Shock-event experiments are separate from snapshot experiments.

### Labels

Keep distinct targets.

**Return**
- next 30m residual return;
- next 60m residual return;
- remainder-of-day residual return;
- next-session residual return;
- 5D residual return;
- 20D residual return.

**Holdability**
- forward residual MAE;
- forward maximum drawdown;
- time below formation residual level;
- MFE/MAE;
- gain retention.

**Leadership**
- top-decile rank survival;
- time to first leadership loss;
- loss-and-reclaim probability.

**Resilience**
- recovery within 5/15/30/60m;
- recovery time with censoring;
- post-shock residual MAE.

**Exhaustion**
- future leadership-break hazard while current medium-horizon RS remains above the eligibility threshold.

No generic “leader worked” target.

### Baselines and model comparisons

For each endpoint, compare nested models:

- M0: raw momentum horizons;
- M1: M0 + beta + realized/downside vol + size/liquidity + gap/event + distance-to-high;
- M2: M1 + residual-return definition;
- M3: M2 + one candidate family;
- M4: M2 + all candidate families that individually survived development;
- M5: prespecified interactions only (group × stock; regime × candidate).

Primary estimators should be transparent rank-linear/logistic/survival models. A nonlinear model may be a secondary robustness lane, not the only evidence.

### Inference

The independent unit is session/date for snapshot tests and distinct shock episode for event tests.

Required:

- per-date cross-sectional rank IC;
- date-clustered or event-clustered uncertainty;
- HAC/Newey-West where the time series of per-date statistics overlaps;
- block bootstrap by session/week;
- purged walk-forward folds with embargo at least as long as the longest forward label;
- one untouched holdout;
- family-wise or false-discovery control within declared feature families;
- monotonic bucket analysis;
- leave-one-sector-out and leave-one-era-out concentration checks;
- explicit mega-cap contribution diagnostics.

Thousands of stock-minutes do not create thousands of independent observations.

### Minimum meaningful effect

Do not advance on p-values alone.

Proposed development floors:

- incremental mean per-date rank IC: at least **+0.01** versus the strong baseline for return/rank endpoints;
- forward-MAE improvement: at least **5% relative reduction in MAE error** or a predeclared economically equivalent tail-capture improvement;
- rank-survival/recovery probability: at least **2 percentage points absolute** in a calibrated high-versus-low bucket contrast, with monotonic ordering;
- exhaustion: median warning lead of at least **one full decision interval** before the conventional RS break and a meaningful discrimination/calibration gain versus RS-only.

These are audit recommendations, not frozen law. The data-science owner should run power analysis under the actual date/event count before freezing.

### Advancement rule

A family advances only if it:

1. beats M1/M2 on its primary endpoint in validation;
2. clears the economic floor;
3. has the expected monotonic direction;
4. survives concentration checks;
5. survives the relevant volatility/jump/event null;
6. does not reverse in the final holdout;
7. adds value on at least one target that is not merely a relabeling of the feature itself.

The design must be allowed to advance **nothing**.

## 9. Data feasibility architecture

| Plane | Current feasibility | PIT / quality issue | Priority |
|---|---|---|---|
| Daily prices | existing Mastermind substrate | ticker reuse, total-return consistency | reuse |
| Minute OHLCV | Massive whole-market flat files documented from 2003-09-10 | flat files unadjusted; missing minutes; qualifying-trade rules | **V1 after repair** |
| Trades | Massive tick files, nanosecond timestamps | signing, conditions, scale | V2 |
| Quotes | Massive top-of-book, nanosecond timestamps | depth is top-of-book only; very large storage | V2 |
| Sector identity | current C1 labels not era-correct | historical GICS moves | repair |
| Industry identity | not established as canonical PIT in this audit | taxonomy history | **repair before confirmatory use** |
| Static baskets | viable only with evidenced historical membership | membership provenance | selective |
| Dynamic themes | no complete canonical PIT history established | severe back-projection risk | **capture prospectively** |
| Economic links | literature supports lane; internal PIT source not established | relationship start/end dates | defer/capture |
| Direct flow | ETF/13F-type data can inform mechanisms | low frequency / ownership lag | mechanism only |

### Corporate actions and symbol identity

Massive currently documents all stock Flat Files as **unadjusted** for splits, dividends and other corporate actions. Its current splits/dividends APIs provide historical adjustment factors, but a sound research plane still needs a stable security master.

Required fields include:

- stable security/entity identifier;
- effective-dated ticker;
- exchange/listing;
- split/stock-dividend factors;
- cash-dividend treatment for total-return labels where relevant;
- merger/delisting dates and proceeds where available;
- symbol reuse;
- halt/LULD flags where available;
- session calendar and early closes.

Do not join decades of minute files on today’s ticker alone.

### Missing minutes and sessions

Massive’s minute bars are built only from qualifying trades; a minute with no eligible trade may emit no bar. Therefore “missing bar” is not automatically zero return/zero volume.

Primary RTH research should distinguish:

- no eligible trade;
- halt/LULD;
- listing not active;
- data gap;
- early close/holiday;
- true zero-volume state where defined.

Premarket and after-hours are documented as covered, but should be separate experiments because bar sparsity and microstructure differ.

## 10. Market-wide computation architecture

Do not build per-symbol API fanout.

### Historical

1. ingest daily whole-market minute flat files in bulk;
2. map raw ticker records through an effective-dated security master;
3. apply corporate-action normalization consistently;
4. write columnar partitions by **session date** with stable security IDs, because the core operation is cross-sectional ranking at common timestamps;
5. maintain smaller security-index metadata for symbol-history lookups;
6. precompute time-of-day volatility/volume seasonality using only prior data;
7. compute market/group benchmarks once per timestamp, including leave-one-out sufficient statistics;
8. update candidate features in vectorized cross-sectional batches;
9. persist only research features/labels/provenance needed for reproducibility.

### Live/shadow architecture if later validated

Maintain incremental state per security and per group:

- cumulative residual return;
- cumulative expected variance;
- realized positive/negative variance;
- rank state;
- shock-event state;
- recovery clock;
- volume seasonality state.

At each fixed decision snapshot, rank the eligible universe once. Group aggregates should be owned by/flow into the existing rotation/group owner rather than creating a second rotation engine.

A mature evidence snapshot should expose separate fields for residual strength, resilience, rank persistence, continuation probability, MAE risk, exhaustion hazard, coverage and provenance. Do **not** collapse them into a `LeadershipScore`.

## 11. Theme-relative architecture

Recommended progression:

1. **Market** — immediately conceptually viable.
2. **PIT sector** — viable after era-correct repair.
3. **PIT industry / industry group** — highest-priority group retest because it is closer to the academic industry-momentum construct and has more cross-sectional units than eleven sectors.
4. **Static basket** — only where historical membership evidence exists.
5. **Dynamic theme** — prospective effective-dated capture; historical present-day backcasts are exploratory only.
6. **Economic network** — PIT customer/supplier/complementarity graph with relationship effective dates and strict multiple-testing control.

The “theme-first × stock-second” hypothesis should be tested at industry before dynamic themes. If PIT industry state adds nothing beyond stock residual strength, there is little justification for an expensive historical theme reconstruction solely to rescue the thesis.

## 12. Exhaustion research proposal

This lane deserves a dedicated experiment because it may have higher product value than detecting already-obvious leaders.

### Eligibility

At each fixed landmark, include only names that are still conventional leaders, e.g. top decile on 60D RS and above a minimum liquidity threshold.

### Candidate deterioration vector

- 5D residual-RS slope;
- intraday RSZ slope;
- negative-shock capture;
- trailing recovery-time deterioration;
- downside residual semivariance;
- rank volatility / rank drawdown;
- PIT group breadth change;
- group leader-retention change.

### Outcomes

- time to 60D rank falling below a predeclared threshold;
- relative-return decay over 5D/20D;
- forward residual MAE;
- failed-breakout event defined independently of the candidate features.

### Required comparison

1. current 60D RS only;
2. 60D + 20D + 5D RS;
3. model 2 + stock resilience/rank deterioration;
4. model 3 + PIT group deterioration.

A valid early-warning family must improve discrimination/calibration **and** provide positive lead time. A metric that changes only after 20D/60D RS has already rolled over is not an early warning.

## 13. V2 microstructure gate

Do not acquire/store a full quote lake merely because microstructure is theoretically attractive.

Advance to V2 only if V1 shock resilience or exhaustion survives the final holdout and leaves a clear unexplained error mode.

Then sample **event windows** around:

- benchmark shocks;
- leader pullbacks;
- failed versus successful recoveries;
- matched nonleader controls.

Candidate V2 fields:

- signed trade volume;
- trade imbalance;
- top-of-book OFI;
- quoted/effective spread;
- displayed depth;
- depth imbalance;
- bid replenishment after aggressive selling;
- spread/depth recovery;
- residual price impact per unit OFI/depth.

The decisive test is incremental OOS value over the minute-bar model. If negligible, **KILL MICROSTRUCTURE V2**.


## 14. Disagreement ledger

| Claim | Supporting evidence | Contradictory / limiting evidence | Current Mastermind evidence | Resolution |
|---|---|---|---|---|
| Industry/group leadership predicts stock momentum | Moskowitz–Grinblatt; later industry work | common factors can explain much industry momentum; international strength varies | C1 broad-sector increment = null | finer PIT industry remains testable; broad-sector prior demoted |
| Factor momentum explains stock momentum | Ehsani–Linnainmaa U.S. evidence | newer international evidence is mixed | B2 shows strong stock-level baseline absorbs many descriptors | include factor controls; do not assume full explanation |
| Smooth/continuous winners are more durable | Frog-in-the-Pan literature | effect is regime-dependent; path variables can proxy vol/jumps | B/B2 path family largely redundant with volatility | test only residual, matched, jump-aware continuity |
| Near-high behavior predicts continuation | 52-week-high literature | proximity is mechanically related to momentum and vol | Mastermind distance-to-high family did not earn promotion | high occupancy is low-priority and must beat distance-to-high |
| High volume confirms leaders | price/volume literature shows interaction | high-volume winners can reverse faster; event/squeeze volume is ambiguous | rotation tensor treats RVOL as proxy, not proof | raw RVOL is a control; signed/OFI data needed for mechanism |
| Leaders recover faster from shocks | market-resiliency literature supports recovery as meaningful | low beta/low vol/liquidity can generate same appearance | not directly tested by B/B2/C1 | **highest-value new falsification lane** |
| Institutional inflows buy every dip | flow pressure and institutional liquidity supply are plausible | passive flows, systematic demand, short covering, dealer hedging and information repricing are alternatives | no direct institutional-flow observation in proposed V1 | causal claim rejected without direct flow evidence |
| Theme-first × stock-second is superior | thematic doctrine and industry literature | C1 interaction/additive broad-sector state did not carry | C1-NULL | retest only at PIT industry/static basket with strong baseline |
| Group breadth deterioration leads reversal | breadth literature and practitioner logic | breadth may be contemporaneous and regime-specific | C1 daily group features did not carry | test only as exhaustion lead-time feature |
| Microstructure will improve resilience inference | OFI/queue/resiliency literature | predictive horizons can be very short and costly | no Mastermind V2 test | defer until V1 survives |

## 15. Existing-system census and owner boundary

| Proposed capability | Existing owner/substrate | Tested null / warning | True missing plane |
|---|---|---|---|
| Daily stock path descriptors | `brain/trend_persistence.py` | Wave B/B2 null on incremental model value | conditional intraday residual response |
| Sector rotation | `brain/rotation_tensor.py` | C1 broad-sector persistence null; tensor remains advisory | validated intraday/PIT group evidence |
| Theme doctrine | `docs/source_thematic_rotation_framework.md` | doctrine not empirical truth | PIT dynamic-theme membership + validation |
| Outcome grading | prediction/outcome machinery | date clustering already required | new labels, not a new ledger |
| Live stock quote access | `data_layer/polygon.py` | current module is per-symbol and not a historical whole-market research plane | bulk flat-file ingestion |
| Group flow proxies | rotation tensor RVOL / ETF shares outstanding | proxy/coverage limits | direct mechanism data if later justified |
| Corporate-action-safe minute history | none established in audited bounded set | current flat files unadjusted | stable-ID adjustment/security-master plane |
| Shock event/recovery state | none | untested | V1 research feature family |
| Trade/quote OFI/depth | none | untested | V2 event-window plane |

No new control plane is recommended. Validated stock snapshots should attach to existing signal/prediction/outcome surfaces; validated group fields should extend/feed the rotation owner.

## 16. Final family classification

### TEST NOW — after the normalized V1 minute panel passes data QA

- market-residual return and RSZ;
- market-shock resilience;
- rank persistence;
- residual continuity/jump concentration;
- exhaustion/early warning;
- regime interaction.

These are conceptually separable from C1 and B/B2 and require no speculative dynamic-theme history.

### TEST AFTER DATA REPAIR

- PIT sector residual strength;
- PIT industry / industry-group state;
- industry-first × stock-second interaction;
- residual high occupancy;
- static baskets whose historical membership can be evidenced.

The blockers are taxonomy history, stable security identity, and corporate-action normalization.

### CAPTURE PROSPECTIVELY

- dynamic-theme membership;
- theme lifecycle changes;
- theme relationship provenance;
- any analyst/LLM-created theme assignment used for future confirmatory work.

Use append-only effective dating. Do not rewrite prior membership when a theme narrative evolves.

### DEFER

- economic-network propagation until a PIT relationship graph is sourced;
- direct institutional-flow mechanism work;
- full trade/quote microstructure;
- price-progress-per-OFI/turnover ratios until denominator stability and V1 need are demonstrated.

### REJECT

- “strong price action implies institutional inflow”;
- raw RVOL as bullish accumulation;
- sequential residualization as the only residual definition;
- generic intraday path efficiency/gain retention without matched volatility/jump controls;
- present-day dynamic-theme membership backcast as confirmatory evidence;
- an opaque `LeadershipScore`;
- a second rotation engine;
- a new outcome ledger.

## 17. Source register

**Retrieval date for external sources: 2026-10-05.**

### Mastermind — pinned internal sources

- Trend Persistence readout, pinned base: https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/research/TREND_PERSISTENCE_READOUT.md
- C1 preregistration: https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/research/TREND_PERSISTENCE_PREREG_C1.md
- C1 result: https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/research/data/trend_persistence_c1_result.json
- B2 result: https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/research/data/trend_persistence_b2_result.json
- Rotation tensor: https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/brain/rotation_tensor.py
- Thematic rotation framework: https://github.com/mastermindx-market-intelligence/Mastermind/blob/7eac3ec252475600147ec9a376b8ca16403ac4c5/docs/source_thematic_rotation_framework.md

### Momentum / group / residual literature

- Moskowitz, T.J. & Grinblatt, M. (1999), “Do Industries Explain Momentum?”, *Journal of Finance* 54(4), 1249–1290. DOI: https://doi.org/10.1111/0022-1082.00146
- Ehsani, S. & Linnainmaa, J.T. (2022), “Factor Momentum and the Momentum Factor”, *Journal of Finance* 77(3), 1877–1919. DOI: https://doi.org/10.1111/jofi.13131
- Blitz, D., Huij, J. & Martens, M. (2011), “Residual Momentum”, *Journal of Empirical Finance* 18(3), 506–521. DOI: https://doi.org/10.1016/j.jempfin.2011.01.003
- Da, Z., Gurun, U.G. & Warachka, M. (2014), “Frog in the Pan: Continuous Information and Momentum”, *Review of Financial Studies* 27(7), 2171–2218. DOI: https://doi.org/10.1093/rfs/hhu003
- Galvani, V. (2024), “Frog in the Pan and the market-state effect on momentum”, *Finance Research Letters* 63, 105374. DOI: https://doi.org/10.1016/j.frl.2024.105374
- George, T.J. & Hwang, C.-Y. (2004), “The 52-Week High and Momentum Investing”, *Journal of Finance* 59(5), 2145–2176. DOI: https://doi.org/10.1111/j.1540-6261.2004.00695.x
- Lee, C.M.C. & Swaminathan, B. (2000), “Price Momentum and Trading Volume”, *Journal of Finance* 55(5), 2017–2069. DOI: https://doi.org/10.1111/0022-1082.00280
- Daniel, K. & Moskowitz, T.J. (2016), “Momentum Crashes”, *Journal of Financial Economics* 122(2), 221–247. DOI: https://doi.org/10.1016/j.jfineco.2015.12.002

### Economic links / flows

- Cohen, L. & Frazzini, A. (2008), “Economic Links and Predictable Returns”, *Journal of Finance* 63(4), 1977–2011. DOI: https://doi.org/10.1111/j.1540-6261.2008.01379.x
- Lou, D. (2012), “A Flow-Based Explanation for Return Predictability”, *Review of Financial Studies* 25(12), 3457–3489. DOI: https://doi.org/10.1093/rfs/hhs103
- “Production complementarity and information transmission across industries” (2024), *Journal of Financial Economics* 155, 103812. DOI: https://doi.org/10.1016/j.jfineco.2024.103812
- Jiang, H., Vayanos, D. & Zheng, L., “Passive Investing and the Rise of Mega-Firms”, *Review of Financial Studies* (2025). DOI: https://doi.org/10.1093/rfs/hhaf085

### Intraday volatility / microstructure / resilience

- Gao, L., Han, Y., Li, S.Z. & Zhou, G. (2018), “Market Intraday Momentum”, *Journal of Financial Economics* 129(2), 394–414. DOI: https://doi.org/10.1016/j.jfineco.2018.05.009
- Barndorff-Nielsen, O.E., Kinnebrock, S. & Shephard, N. (2010), “Measuring Downside Risk — Realized Semivariance”, in *Volatility and Time Series Econometrics*. Primary: https://doi.org/10.1093/acprof:oso/9780199549498.003.0007
- Barndorff-Nielsen, O.E. & Shephard, N. (2004), “Power and Bipower Variation with Stochastic Volatility and Jumps”, *Journal of Financial Econometrics* 2(1), 1–37. Primary: https://academic.oup.com/jfec/article/2/1/1/960705
- Cont, R., Kukanov, A. & Stoikov, S. (2014), “The Price Impact of Order Book Events”, *Journal of Financial Econometrics* 12(1), 47–88. DOI: https://doi.org/10.1093/jjfinec/nbt003
- Gould, M.D. & Bonart, J. (2015), “Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book”. DOI: https://doi.org/10.2139/ssrn.2702117
- Lo, D.K. & Hall, A.D. (2015), “Resiliency of the limit order book”, *Journal of Economic Dynamics and Control* 61, 222–244. Primary: https://ideas.repec.org/a/eee/dyncon/v61y2015icp222-244.html
- “Institutional trading and stock resiliency: Evidence from the 2007–2009 financial crisis” (2013), *Journal of Financial Economics* 108(3), 773–797. DOI: https://doi.org/10.1016/j.jfineco.2013.01.007

### Massive data documentation

- Stock Flat Files overview — whole-market day/minute/trade/quote datasets; flat files unadjusted: https://massive.com/docs/flat-files/stocks/overview
- Minute aggregates — documented history back to 2003-09-10: https://massive.com/docs/flat-files/stocks/minute-aggregates
- Stock quote flat files — top-of-book quotes with nanosecond timestamps: https://massive.com/docs/flat-files/stocks/quotes
- Stock WebSocket minute aggregates — premarket/RTH/after-hours coverage and qualifying-trade bar rules: https://massive.com/docs/websocket/stocks/aggregates-per-minute
- Splits endpoint — effective dates and historical adjustment factors: https://massive.com/docs/rest/stocks/corporate-actions/splits
- Dividends endpoint — historical cash distributions and adjustment factors: https://massive.com/docs/rest/stocks/corporate-actions/dividends

## 18. Final decision

**ADVANCE WITH MAJOR REVISION.**

The commission’s core intuition survives only after being stripped of its causal story and decomposed into testable pieces.

The most promising genuinely new plane is **conditional shock resilience**: whether a stock that is already strong, after market/factor neutralization, absorbs exogenous market/group weakness with unusually small residual MAE and unusually fast first-passage recovery — and whether that behavior predicts later continuation, lower adverse excursion, rank survival or earlier exhaustion detection after controlling for beta, volatility, liquidity, gap/event magnitude and conventional momentum.

The second-most promising plane is **leadership deterioration while medium-horizon RS is still high**. This is both empirically distinct and product-relevant if it provides measurable lead time.

Residual continuity and rank persistence are worth testing but face a serious redundancy burden from Wave B/B2. Industry/group context remains plausible but should re-enter only through PIT finer taxonomy and a strong stock baseline. Dynamic themes should be captured prospectively rather than fabricated historically. Microstructure is a V2 explanation/improvement layer, not the first experiment.

A successful outcome of the next program may be that only one of these families survives — or none. That would still be a successful research result.

### Frozen handoff for the next data-science owner

Before computing any candidate-label relationship:

1. repair stable security identity and corporate actions for minute flat files;
2. establish the exact PIT sector/industry source and coverage;
3. freeze the universe/calendar/snapshots/labels;
4. freeze the residualization comparison and shock definition;
5. freeze the strong momentum/beta/volatility/liquidity/event baseline;
6. freeze family-wise kill/advance rules;
7. preserve 2023-01-03 through 2026-06-02 as the untouched holdout unless data QA forces a pre-analysis calendar revision;
8. run market-only V1 before group/theme or microstructure expansion.

No production indicator, composite score, sizing rule or trading gate is justified by this audit.
