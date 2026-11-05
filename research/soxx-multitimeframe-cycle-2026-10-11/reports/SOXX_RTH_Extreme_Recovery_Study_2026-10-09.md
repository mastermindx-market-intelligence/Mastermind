# SOXX: Regular-session continuation — extreme-conditioned recovery

**Research date:** October 9, 2026  
**Requested evaluation period:** October 9, 2025–October 8, 2026  
**Earlier comparison period:** December 16, 2024–October 8, 2025  
**Status:** Completed retrospective RTH experiments; a stronger candidate, not a proven trading edge. BOATS remains a separate user-supplied input. No trades, production changes, repository publication or background job were initiated.

## Executive finding

The strongest new pattern is a sequence: **a dramatic downside MACD histogram extension first arms a setup; the entry waits for the MACD line to cross above its signal line, together with Stochastic RSI recovery.** This is not every crossover and it is not an entry while the histogram is still at its negative extreme. It deliberately enters after recovery has begun, sometimes several sessions after the original stretch.

With a structural stop, the combined 2H/3H/4H candidate produced **9 profitable trades out of 11**, a **+3.69% average net trade**, and **+47.55% compounded strategy return** in the requested year. However, its average initial stop was **6.02% of the SOXX entry price**, and the earlier period's positive mean depends on one large winner. Removing that earlier winner changes the earlier average from **+1.73% to −0.25%**. Those are material limitations, not footnotes.

A less permissive fixed 1.5% stop / 2% target version produced 12 trades, 66.7% wins, +0.73% per trade, and +8.98% compounded. It should remain a risk-controlled reference rather than being discarded in favor of the largest backtest return.

## 1. What was executed

This continuation ran **3,288 main configuration tests**: 1,728 independent-condition variants, 1,320 entry/exit variants, 180 later-confirmation variants, and 60 ordinary-cross controls. Focused checks also examined parameter neighborhoods, repeat-entry cooldowns, shortened candles, entry-hour effects, stop-width limits, data discrepancies, matched-entry placebos and an expanding historical selection exercise. Many configurations reuse the same trades; these counts are not independent evidence or sample sizes.

The original interrupted independent-filter write was reconciled as absent on the original host before it was rewritten. All subsequent research processes completed. The original frozen source snapshot was retained, rather than re-downloading a changed history to improve the fit.

## 2. Exact leading candidate specification

### Setup versus trigger

On each of three session-anchored bar series, evaluate the following fixed profiles:

| Profile | MACD fast / slow / signal EMA lengths | Stoch RSI RSI / stochastic / K / D lengths |
|---|---|---|
| 2H classic | 12 / 26 / 9 | 14 / 14 / 3 / 3 |
| 3H medium | 8 / 21 / 5 | 14 / 14 / 3 / 3 |
| 4H fast | 5 / 13 / 4 | 14 / 14 / 3 / 3 |

Let H denote MACD histogram, meaning MACD line minus signal line. The preceding-80-bar scale is:

`RMS_t = sqrt(sum(H_j^2 for j=t-80,...,t-1) / 80)`

This is a magnitude around zero, **not** a centered standard-deviation z-score. The current histogram observation is excluded from its own scale.

For a long setup, require `H_t <= -2 * RMS_t` and Stoch RSI K at or below 20 in the current or preceding two bars. The setup arms only once per negative-histogram episode. Only completed, covered input bars can arm it. The alert itself does not authorize an immediate buy.

After that qualifying extreme, wait at most **12 aggregate bars on the originating timeframe** for a completed-bar MACD histogram cross from nonpositive to positive, with current Stoch RSI K at least 20 and K at least D. This is a **MACD line / signal-line crossover**, not a requirement that the MACD line itself cross the zero axis. A separate sensitivity imposes a common 19.5 or 26 RTH-hour maximum watch across all three timeframes.

The combined strategy accepts a qualifying setup from **any one** of the three profiles; it does not require all three to agree. Identical entry timestamps are deduplicated in fixed 2H, then 3H, then 4H order. A single portfolio position prevents overlapping trades. New entries are at the next recorded regular-session hourly opening price after the completed confirmation bar. No same-close signal fill is assumed.

### Exits and capital conventions

The main structural stop is the lowest recorded price from the extreme-arm bar through the confirmation bar, minus **0.25 times 14-period hourly ATR**. The known stop level is fixed. Reject an entry if its initial distance to that stop is less than 0.3% or greater than 8% of the opening price. The profit target is twice that initial price risk above entry. Exit any remaining position after at least **19.5 observed RTH hours**, approximately three regular sessions, rounded to the end of the last source bar. The maximum timing overrun is the remainder of that source bar.

The 8% upper bound and full-notional return convention are backtest assumptions, **not position-size or risk-budget recommendations**. A gap can exceed a nominal stop. The structural stop averaged 6.0154% and reached 7.6714% in the requested year; its mean net return was 0.5669 times initial price risk. Nine of eleven trades exited on time, one at a stop and one at a target. Most profits therefore do not demonstrate repeated attainment of the 2R target.

Reported compounded returns assume a single unlevered full-notional SOXX position, profits reinvested, and zero return on cash between trades. Dividends, taxes, financing, borrow fees for the short diagnostics and execution-capacity limits are omitted. The requested-year SOXX price benchmark in the earlier source audit was approximately +93.18%; +47.55% is not a claim of beating buy-and-hold on absolute return. Different exposure prevents a simple risk-adjusted comparison.

Base modeled cost is **5 basis points on each side**, with costs proportional to actual entry and exit notional. The stress case is 15 basis points per side. Stops that are crossed in a gap execute at the next recorded opening price; targets crossed in a favorable gap receive only the target price. When stop and target both fall inside one hourly candle, the stop is assigned first. These are OHLC approximations, not bid/ask or tick-level proof.

## 3. Timing matters more than stacking every filter

All three rows below use the same structural-stop formula and 8% admission bound. Entry changes affect stop distances, admission and subsequent overlap, so the rows do not contain identical trade sets.

| Entry sequence after the extreme | Trades | Win rate | Mean net trade | Compounded return | Hour-close maximum drawdown |
|---|---:|---:|---:|---:|---:|
| Extreme, first contraction | 14 | 50.0% | -0.02% | -1.97% | -19.32% |
| Extreme, then price reclaim | 11 | 63.6% | +1.31% | +14.14% | -10.37% |
| Extreme, then MACD signal-line cross | 11 | 81.8% | +3.69% | +47.55% | -6.11% |

The strong result is a **confirmed recovery** result, not evidence of catching the exact low. The original first-contraction rule is materially weaker. Merely adding a price reclaim helps but does not reproduce the later MACD-cross result.

### Fixed risk comparison

| Entry family | Stop / target | Earlier trades / mean | Requested-year trades / wins | Requested-year mean | Compounded return |
|---|---|---|---|---:|---:|
| Ordinary bullish MACD crosses, no extreme prerequisite (control) | 1.5% / 2% | 34 / +0.17% | 47 / 59.6% | +0.40% | +19.44% |
| Extreme first, later bullish MACD cross | 1.5% / 2% | 11 / +0.16% | 12 / 66.7% | +0.73% | +8.98% |
| Ordinary bullish MACD crosses, no extreme prerequisite (control) | 3% / 4% | 30 / +0.25% | 42 / 54.8% | +0.61% | +26.55% |
| Extreme first, later bullish MACD cross | 3% / 4% | 9 / −1.19% | 12 / 75.0% | +1.76% | +22.58% |

Thus the extreme prerequisite improved recent-year **per-trade** quality in these controls, not necessarily total return. The wide fixed-risk version also failed to generalize consistently from the earlier period. The ordinary-cross versions are diagnostic controls, not recommended replacements for the user's required extreme-conditioned strategy.

### Individual timeframes under the later-cross structural rule

| Profile | Earlier trades / mean | Requested-year trades | Win rate | Mean net trade |
|---|---|---:|---:|---:|
| 2H classic | 5 / +2.55% | 2 | 100.0% | +4.77% |
| 3H medium | 3 / +0.41% | 8 | 87.5% | +4.89% |
| 4H fast | 7 / +1.54% | 5 | 60.0% | +0.33% |
| Combined, one position | 8 / +1.73% | 11 | 81.8% | +3.69% |

Standalone counts overlap and cannot be added. These tiny samples do not establish a universal winning timeframe. In this particular later-confirmation family, 3H was more interesting than 4H; that differs from the earlier first-turn comparison and demonstrates why the entry definition must be specified before choosing a timeframe.

## 4. Robustness findings — both favorable and unfavorable

**Nearby parameter behavior:** The 27 later-cross structural combinations of 9/12/15 aggregate-bar expiry, 1.75/2.00/2.25 RMS threshold and 10/20/30 Stoch arm zone all had positive requested-year mean returns, ranging from +2.56% to +4.04%. However, together they represent only **13 distinct entry dates**. Their median entry-date overlap with the main candidate was 76.92%. These are a connected family, not 27 independent validations. All 27 were positive in the earlier period, but only **9 of 27** remained positive after removing their respective best earlier trade.

**Remove the best requested-year trade:** Mean return remains +3.08%, versus +3.69% originally. The requested-year result is not solely its best winner.

**Increase modeled costs:** At 15 basis points each side, the mean remains +3.48%. This does not establish that actual spreads and slippage are bounded at that amount.

**Wait-window and repeated-entry controls:** Restricting the alert-to-entry wait to a common 19.5 RTH hours across timeframes gives seven requested-year trades, 85.7% wins and +4.51% mean. The 26-hour version leaves the main eleven trades unchanged. A three-session cooldown also leaves those eleven unchanged, but removes the dominant earlier-period winner and makes that earlier mean negative. That is a failure of historical stability, even though the recent year survives.

**Shortened bars:** Excluding shortened-arm candles leaves the requested-year main result unchanged, but also removes the largest earlier-period winner. Shortened closing candles are therefore not the source of the recent result, yet the earlier positive result is sensitive to them.

**Stop-width limits:** Limiting initial stop width to 5% leaves only four requested-year trades and a negative earlier-period mean. Limiting it to 3.5% leaves one losing requested-year trade. The large headline does not support a tight-stop claim.

**Quarter stability:** Requested-year quarter means were +0.81%, +3.69%, +5.18% and +9.24%, but their counts were only 4, 2, 4 and 1. The final quarter figure is one trade, not a stable quarterly estimate.

**Descriptive uncertainty:** The 9/11 win-rate Wilson interval is approximately 52.3%–94.9%. A 5,000-draw month-block bootstrap gives +1.59% to +6.18% for the requested-year mean. Neither interval accounts for selecting this family after inspecting many alternatives; neither is a calibrated confidence interval for future trading performance.

**Matched-entry placebo:** 5,000 controls matched on calendar quarter, opening hour and risk/target fraction gave a mean of +0.13% versus the observed +3.69%. About 0.24% of control draws met or exceeded the observed average. Each pool had 29–57 alternative entries. The pools were not matched on volatility, simulated selections can overlap, and the calculation is not adjusted for the many strategies inspected. It is a descriptive diagnostic, **not a 99.76% probability that the strategy works**. An earlier, more narrowly stratified control had an inadequately small pool and is not used as supporting inference.

**Historical strategy selection:** An expanding four-fold selector applied to the earlier entry/exit search—not to the subsequently developed late-cross family—produced ten requested-year trades, 40% wins, +0.17% average return and +0.73% compounded. At higher costs its mean was negative. This illustrates why picking the best historical configuration should not be confused with predicting which one will work next.

## 5. The principal unresolved weakness

In the earlier comparison period, the leading structural later-cross candidate won **4 of 8** trades, averaging +1.73%. A trade entered on **April 8, 2025** contributed approximately **+15.57%**. Removing it changes the mean of the other seven to **−0.25%**. The requested year's stronger evidence does not erase that fragility.

The correct status is **promising retrospective recovery candidate, not robustly accepted**. The requested evaluation year has already been inspected repeatedly. Calling it untouched out-of-sample would be false. More parameter searches on these same dates cannot restore independence. Backtest-overfitting research specifically cautions against treating historically selected performance and ordinary holdout tests as sufficient evidence [1].

The mirrored short-side later-cross structural rule yielded seven requested-year trades, 28.6% wins and approximately −0.65% per trade. The corresponding fixed and wide-fixed short versions also lost money. These results do not support using the bullish result symmetrically to short tops.

## 6. Main candidate trade ledger

All displayed timestamps are America/New_York with DST encoded in the accompanying CSV. The exit field is the start of the source hourly window; it is not a claim of the exact intrabar fill time. Stops/targets may be touched within that window. “Risk” means initial entry-to-stop price distance, not the percentage of account capital recommended at risk.

| Entry date/time ET | Originating profile | Alert-to-confirmation RTH hours | Initial stop distance | Net trade return | Exit type |
|---|---|---:|---:|---:|---|
| 2025-10-16 09:30 | 4h_fast | 22.0 | 6.97% | +0.56% | time |
| 2025-10-24 09:30 | 3h_medium | 7.0 | 6.33% | +2.51% | time |
| 2025-11-10 12:30 | 3h_medium | 23.0 | 6.13% | -3.47% | time |
| 2025-12-18 15:30 | 3h_medium | 26.0 | 3.50% | +3.64% | time |
| 2026-02-06 13:30 | 4h_fast | 18.5 | 7.52% | +3.01% | time |
| 2026-03-31 15:30 | 2h_classic | 10.5 | 6.79% | +4.37% | time |
| 2026-04-30 13:30 | 4h_fast | 13.0 | 6.25% | +5.64% | time |
| 2026-05-20 12:30 | 3h_medium | 16.5 | 7.44% | +9.82% | time |
| 2026-06-11 12:30 | 3h_medium | 26.0 | 7.67% | +8.25% | time |
| 2026-06-26 09:30 | 4h_fast | 9.0 | 2.90% | -3.00% | stop |
| 2026-09-17 12:30 | 3h_medium | 16.5 | 4.67% | +9.24% | target |

## 7. Data and engineering qualification

The source is a frozen Yahoo Finance 60-minute SOXX OHLCV snapshot with earlier bars for warm-up. It contains 3,473 retained RTH bars across the two-year source window; five null and nineteen zero-volume rows were rejected. Rejected data were not fabricated or forward-filled. Missing observations still limit both indicators and simulated holding paths.

Bars are anchored to the actual 9:30 a.m. session start; shortened closing bars and half-days are not mislabeled full-duration bars. A coverage-incomplete bar cannot arm a setup or confirm a signal, although recorded prior closes still affect indicator state. The audit does not prove official auction-price or consolidated-tape parity.

Over 251 requested-year sessions, median absolute hourly-versus-daily source close discrepancy was 0.01924%, with a maximum of 0.66349%. Four close discrepancies exceeded 0.25%. Both feeds are from the same vendor; this is a consistency check, not independent vendor validation. Excluding trades touching any OHLC discrepancy above 0.25% was a post-hoc data-quality sensitivity, not an executable future-known entry filter.

The main maximum drawdown was −6.11% marked at hourly closes. Two OHLC path-order scenarios gave approximately −6.44%. None supplies actual tick-by-tick drawdown, a liquidity guarantee, or overnight bid/ask paths. The reliance of OHLC backtests on within-bar assumptions is documented by TradingView's broker-emulator specification [2]; our fill rules are specified separately above and do not claim exact TradingView parity.

**Verification:** 47 local unit tests passed. Separately, 396 long/short exits on the actual retained hourly data matched the earlier exit implementation to numerical tolerance. Source transfers were SHA-256 verified before execution. These checks verify specific numerical, causality and execution rules, not the predictive edge or the historical feed's completeness.

No BOATS history was requested or invented in this continuation. RTH positions can span nights, but there is no overnight execution simulation. The user is acquiring the separate BOATS source. The next comparative experiment should retain frozen rule definitions, compare RTH-only input/execution with full-session-input/RTH-execution and full-session-input/full-session-execution, and distinguish unchanged indicator settings from horizon-matched settings. New, genuinely untouched observations remain necessary for independent acceptance.

## 8. Artifacts, source identity and recovery

The downloadable companion ZIP contains source code, unit tests and test logs, selected measured CSV/JSON evidence, this report and a recovery checkpoint. It **does not contain the full raw market snapshot or all grid/trade rows**. The five selected evidence files were copied from observed remote output and verified byte-for-byte against remote SHA-256 receipts.

The full 45-file raw-data, grid and source archive was saved and verified on mini4:

`/Users/mini4/.local/share/mastermind-review-artifacts/SOXX_RTH_20261009_v3.zip`

Archive SHA-256: `1fb9928f3860135869b2415f64b0e0efad526e06ea7739771f042dbf7d8af148`  
Archive bytes: 1,791,948  
Checkpoint SHA-256: `bf03823a2a69102e7a6b30bda312873a86752f59f9bc4abccd5379ede7c6bddc`

Frozen hourly source SHA-256: `ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720`  
Frozen daily warm-up source SHA-256: `11d17b9626819ee31d6c3e9af24b0d8906914937c15a7c8abb29535340067f04`  
Protected procedure pin: `7d82b9adb839d54e4ab25378ca333e498dd83fcc`

All scoped experiment processes finished; no modifying effect remains unresolved. Do not rerun existing output paths blindly: the scripts reject existing output directories. Use the immutable snapshot and new explicitly named result directory for any materially different experiment.

### References

[1] Bailey, Borwein, López de Prado and Zhu, *The Probability of Backtest Overfitting*, author paper and published-paper repository record. Used for the selection-bias limitation, not as evidence for SOXX returns.

```text
https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253
https://scholarworks.wmich.edu/math_pubs/42/
```

[2] TradingView, *Concepts / Strategies — Broker emulator*. Used for the general limitation of OHLC-based within-bar execution assumptions, not for our measured performance.

```text
https://www.tradingview.com/pine-script-docs/concepts/strategies/
```