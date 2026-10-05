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
