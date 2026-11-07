# SOXX — Granular Exit Research, Version 6
## Early-rebound failure versus mature-trend management

**Research date:** October 9, 2026. **Status:** retrospective research, not an admitted live strategy.

**Requested evaluation:** October 9, 2025–October 8, 2026. **Earlier comparison:** December 16, 2024–October 8, 2025. Regular-session price observations only. No BOATS access, trade placement, production change, or broker connection was made in this round.

## Executive finding

The most promising new design separates two jobs that the earlier exits mixed together: detecting a rebound that fails soon after entry, and allowing an established recovery to survive normal retracements. In the tested cases, limiting the fast failure detector to the initial period avoided the premature mature-recovery exits produced by leaving it active indefinitely.

The resulting candidate retains the frozen 3H-extreme/1H-pivot entry, the original 1.5% stop, and a slower 3H momentum exit. It adds a close-confirmed early-failure rule that operates only from three to 6.5 observed regular-session hours after entry. It does not move the stop automatically to breakeven, widen the initial stop, or predict a future high.

The 25%-partial variant averaged 5.30% per original position in the retained year, versus 4.62% with the same 25% partial but no early-failure window. The 50%-partial variant improved from 3.42% to 3.87%. All five earlier-period trade outcomes were unchanged. The additional improvement came from exactly two year trades: June 8 and July 6, 2026.

**This is a coherent research candidate, not independent validation.** The failure pattern and its expiration window were developed after inspecting the data. Five unchanged earlier trades do not constitute five successful tests of the new safeguard. More independent observations are needed to establish its effect.

## 1. Comparison controls and data limitations

The primary entry definition was held fixed: a dramatic negative 3H MACD 8/21/5 histogram extension, recent oversold Stoch RSI 14/14/3/3, and a confirmed 1H price pivot with improving momentum. The principal lower indicators remain MACD 5/13/4, Stoch RSI 7/7/3/3, and conventional RSI(14). The extreme is scaled by the preceding 80-bar root-mean-square histogram magnitude, not a centered standard-deviation z-score. No entry-rule optimization was added to make the new exit look better.

The main common-path cohort contains eight requested-year entries and five earlier entries. Two originally profitable short-target entries, November 5, 2025 at 10:30 ET and February 2, 2026 at 09:30 ET, were excluded from every primary exit comparison because their full 65-hour maximum comparison windows contain missing source bars. This is a retrospective data-quality exclusion, not an executable filter that could be known at entry. It can itself create selection bias.

The original 1.5% stop stays active throughout. The maximum hold is 65 observed regular-session hours, approximately ten normal daytime sessions. Partial targets are resting price limits at +2%. Costs are 5 basis points per side by default. Market exits act at the next observed bar open, not the close that generated the decision. Stop changes apply subsequently and never retrospectively inside the signal candle. A stop crossed by an opening gap fills at the next observed open, not at an invented stop price. A candle touching both stop and limit is handled stop-first by default, except executable opening orders are processed in their observable order.

Prices are hourly OHLCV for the annual test. The subhourly source contains actual 15-minute data from July 17, 2026, with the common recent comparison beginning August 17 after warmup and ending October 8. It contains only one shared completed qualifying long episode. There is no full-year 15/30-minute or true overnight test in this report.

## 2. What was actually tested beyond oscillator thresholds

The new annual research contains 384 exit-rule definitions across four development stages. Applied to the frozen entry families, a larger unfiltered local-pivot control, and the smaller recent-data cohort, these produced 5,112 rule applications and 46,585 configuration-trade rows. These counts are computational workload, not independent market evidence.

| Mechanism family | Operational definition and purpose |
|---|---|
| Confirmed swing-low protection | Raise a stop below a newly confirmed local low, buffered by ATR. Pivot timing requires subsequent confirmation, never a backdated low. |
| Rolling-low / Donchian protection | Trail below the lowest completed lows over 3, 5, or 8 bars, with a volatility buffer. |
| Chandelier and volatility budgets | Protect against a retreat from the observed high using 2–4 ATR, or the greater of an ATR allowance and a fraction of accumulated gain. |
| Adaptive volatility trails | Use a wider allowance while price movement is efficient and momentum improves, and a tighter allowance when movement becomes inefficient. |
| Adaptive moving average | Exit after one or two closes below a KAMA-style adaptive average, rather than selling merely because RSI is high. |
| Anchored average-price loss | Track an entry-anchored OHLCV typical-price approximation to VWAP and combine its loss with local trend/momentum deterioration. This is not transaction-level VWAP. |
| Failed breakouts and climax candles | Identify a new high rejected back into the previous range, or a large upper wick/weak close with range expansion and optional relative volume. |
| Confirmed divergence plus break | Require a later higher price high with weaker RSI or MACD, then a local price break. Divergence alone is not an exit. |
| Stagnation / failure to launch | Look for inadequate initial follow-through, or several bars without new progress while local trend measures deteriorate. |
| Initial-risk profit ladder | Increase the protected profit only after progressively larger multiples of original risk. |
| Phase-based voting and trims | Combine local structure breaks, loss of trend, stagnation, climax evidence, and confirmed divergence after higher momentum matures. |
| QQQ and relative-strength conditions | Test whether Nasdaq weakness or a weakening SOXX/QQQ ratio adds useful confirmation to a failed-profit exit. |
| Earlier-data continuation estimate | Use 16 transparent market-state bins trained only on completed earlier next-session outcomes before each quarter, with shrinkage toward the broad mean. Overlapping labels are not independent samples. |
| Bounded early-failure window | Allow initial noise, detect an early rebound that gives most of its initial progress back, and switch this special detector off after the initial period. |

The QQQ benchmark is aligned by exact observation timestamps. Missing or invalid benchmark observations do not silently become fresh evidence: those market-condition exits are disabled while the original stop and slow exit remain active. Relative-volume controls use previous observations in matching UTC slots and durations; they are an approximation and were not selected as the final candidate.

## 3. The new candidate, specified precisely

### Always-active protections

Retain the original stop 1.5% below entry. Do not widen it. The slow 3H momentum exit remains available throughout the position, including during the early window. A 65-RTH-hour maximum hold remains a fallback.

For the balanced candidate, place a limit to sell **25% of the original position at +2%**. Keep **50% at +2%** as the matched conservative reference. A no-partial version was separately tested; its larger average is not evidence that foregoing realized profit is universally preferable.

### Early failure detector

Use the elapsed observed market time since entry, not wall-clock time or the calendar date:

| Position age | Special early-failure rule |
|---|---|
| Less than 3 RTH hours | Inactive. The original stop and slow exit still apply. |
| From 3 through 6.5 RTH hours, inclusive | Active on completed 1H observations. |
| More than 6.5 RTH hours | Expired permanently for this position. Do not confuse a later normal retracement with a failed initial rebound. |

During the active window, exit the remaining position at the next observed open only when all of the following hold:

1. The observed high since entry has reached at least +2%.
2. The current completed close is less than +1% above entry.
3. Conventional 1H RSI(14) is below 50 **or** the current close is below the 1H EMA10.

A decision generated before the window expires may execute on the next observed opening event; expiration does not retrospectively cancel a valid pending order. On partial sessions, the clock uses the actual recorded bar duration. On a 24-hour feed the same number of bars/hours must not be assumed to have equivalent information or liquidity.

### Mature recovery exit

The existing slow reference is a 3H panel with MACD 12/26/9, conventional RSI(14), and Stoch RSI 14/14/3/3. A completed observation with RSI at least 65 and Stoch K at least 80 activates the upper-momentum watch. A subsequent bearish K/D cross with a falling MACD histogram closes the remainder at the next observed open. The histogram need not be negative. The upper-range observation remains recorded after it occurs.

The architectural change is not a new magical overbought level. It is a limited fast failure detector attached to a slower recovery exit.

## 4. Fair comparison: same partial-profit size

All rows below contain the same eight year entries and five earlier entries.

| Portion sold at +2% | Remaining-position management | Year win rate | Mean net trade | Compounded year return | Recorded drawdown | Earlier mean |
|---:|---|---:|---:|---:|---:|---:|
| None | Slow 3H rollover only | 50.0% | 5.83% | 52.87% | −9.40% | 2.60% |
| None | Early window + slow rollover | 75.0% | 6.74% | 64.70% | −2.91% | 2.60% |
| 25% | Slow 3H rollover only | 50.0% | 4.62% | 41.05% | −6.60% | 2.08% |
| **25%** | **Early window + slow rollover** | **75.0%** | **5.30%** | **49.07%** | **−2.51%** | **2.08%** |
| 50% | Slow 3H rollover only | 62.5% | 3.42% | 29.65% | −4.48% | 1.55% |
| 50% | Early window + slow rollover | 75.0% | 3.87% | 34.47% | −2.51% | 1.55% |

Compounding assumes an unlevered full-notional position on each non-overlapping trade, with partial proceeds held as cash. This is not account risk sizing. Drawdown is measured from recorded bar-close and fill equity, not all ticks or unobserved overnight prices.

Relative to the previous 50%-partial candidate, the new 25%-partial result improves by 1.89 percentage points per trade. Approximately 1.21 points arise from holding a larger remainder even without the new safeguard; approximately 0.68 points arise from the early-failure change at the same 25% partial. Keeping those contributions separate avoids attributing all the gain to improved exit timing.

The no-partial version has the largest mean among these matched candidates, but its 75% win rate drops to 50% when modeled costs rise to 15 basis points per side: the two protected exits are only small positive returns before the higher costs. The 25% and 50% staged versions retain six winners out of eight at both 15 and 30 basis points per side in this sample.

## 5. Exactly which trades changed

The new early window changes **two** retained-year outcomes, and nothing else in the matched comparison:

| Entry | Old 25%-partial return | New 25%-partial return | New remaining-position exit |
|---|---:|---:|---|
| June 8, 2026, 10:30 ET | −0.72% | +0.58% | June 8, 15:30 ET |
| July 6, 2026, 09:30 ET | −3.63% | +0.53% | July 6, 13:30 ET |

Both positions had made at least +2% and then lost most of that initial progress. The guard closes the remaining exposure before the subsequent adverse move. In the July case, the original remainder stayed open for a large gap down the following session. This does not prove the rule forecasts future gaps; it reacts to already-observed loss of follow-through.

The larger winners were unchanged under the same 25%-partial comparison: October 22, 2025 returned 7.45%; March 31, 2026 returned 15.68%; May 19 returned 12.26%; and September 15 returned 9.30%. The two original losing setups in October and December were unchanged as well.

### Why expiration matters

The first guard implementation stayed active indefinitely after its three-hour grace period. In the earlier period, it cut the December 20, 2024 trade from 2.99% to 0.85% and the August 1, 2025 trade from 3.93% to 1.39%, using the 50%-partial comparison. Those exits occurred well after the initial rebound period. The finite early window prevents those particular mature-retracement exits.

This is a useful causal description of the implementation, but the design was refined after seeing these examples. It is not independent earlier-period confirmation. No earlier trade changes under the final finite-window version, so that sample supplies no successful activation examples of the new detector.

## 6. What the additional mechanisms did not solve

A 2H confirmed swing-low stop after taking half at +2% averaged 3.57% versus 3.42% for the prior half/3H rollover rule, with the same measured year drawdown of 4.48%. Its earlier mean was lower, at 1.19% versus 1.55%, and its paired year improvement interval included zero. A 3H five-bar-low stop was similarly close at 3.54%.

The risk-profit ladder looked stronger at 4.38% with half taken at +2%, but four year trades exited on the 65-hour timer. Those results are not evidence that the ladder identified tops. The plain no-target 65-hour control still averaged 7.76%, with 50% wins and approximately 9.07% recorded drawdown. Longer exposure, rather than precise exit forecasting, accounts for a substantial part of the available return.

QQQ weakness, a weakening SOXX/QQQ ratio, and a prior-data conditional-return model were tested, not simply suggested. QQQ confirmation did not fix the indefinite guard's earlier-period weakness. The conditional-return model averaged 3.60% with no partial profit and a 10.53% drawdown; the matched full-position slow-rollover reference averaged 5.83% with a 9.40% drawdown. More complicated contextual inference was not an upgrade here.

The baseline and new safeguards were also applied without retuning to the larger unfiltered 1H-pivot entry set. The finite-window half-partial version averaged 0.78% across 34 year trades, compared with 0.63% for the baseline, but the earlier 27 trades averaged −0.24% and year drawdown was approximately 18.53%. This is not a universal exit that rescues weak entries.

## 7. Stress and sensitivity

For the 25%-partial finite-window candidate:

| Scenario | Year mean | Year recorded drawdown | Earlier mean | Earlier mean excluding best trade |
|---|---:|---:|---:|---:|
| Baseline: 5 basis points per side | 5.30% | −2.51% | 2.08% | 1.32% |
| 15 basis points per side | 5.10% | −2.70% | 1.87% | 1.12% |
| 30 basis points per side | 4.79% | −3.29% | 1.57% | 0.82% |
| Additional one raw bar delay for market exits | 5.61% | −2.51% | 2.31% | 1.43% |
| Additional 25-basis-point slippage on stop fills | 5.24% | −2.75% | 1.98% | 1.20% |
| Combined 15-bp costs, market delay, stop slippage, and 5-bp limit penetration | 5.34% | −2.96% | 2.00% | 1.10% |

These scenarios are hypothetical execution stresses, not estimates of actual historical spreads or fill probabilities. The delayed exit happens to improve this sample; that does not make delay desirable. Resting stops are not delayed by the market-exit latency scenario. A five-basis-point penetration requirement means a sell limit is considered filled only after the observed price exceeds the limit by that margin; it did not change these selected trades.

The grace period matters. With a 6.5-hour expiration and a 1% retained-gain cutoff, moving the grace from three hours to two lowers the half-partial year mean from 3.87% to 2.94%, below the previous 3.42% reference. Four hours gives the same retained-year results as three. Extending the special guard to 9.75 or 13 hours reduces earlier-period performance. These variations expose why the idea is about trade phase, not why any one hour setting is universally correct.

## 8. Subhourly structural exits: informative case, insufficient sample

For the same September 16, 2026, 09:30 ET 30-minute reclaim entry at 507.50, on actual 15-minute execution bars:

| Full-position exit | Net return | Observed RTH hours held | Exit type |
|---|---:|---:|---|
| 15-minute confirmed swing-low trail | 2.19% | 12.0 | Trailing stop |
| 30-minute confirmed swing-low trail | 9.25% | 39.0 | Trailing stop |
| 15-minute 3-ATR Chandelier | 9.01% | 26.0 | Trailing stop |
| 1H 3-ATR Chandelier | 10.33% | 33.25 | Trailing stop |
| Existing full-position 3H momentum rollover | 10.52% | 35.5 | Momentum exit |
| 4H swing-low trail | 11.70% | 65.0 | Time limit, not a structural signal |

These are alternatives for one shared episode. They demonstrate that the mechanism and buffer can matter as much as the timeframe: a 15-minute swing stop exited early, while a volatility-buffered 15-minute trail captured substantially more. They do not establish that 15, 30, or 60 minutes is generally best. The slower timer case must not be misdescribed as accurate top identification.

## 9. Statistical adjudication

There are only seven entry-month groups in the eight-trade primary sample. The matched safeguard improvement at 50% partial is 0.46 percentage points per trade; at 25% partial it is 0.68 points. Their entry-month bootstrap intervals include zero. All the incremental matched benefit comes from the same two events.

An exact entry-month sign-flip reference over the current 384-rule family did not establish selection-adjusted superiority. It assumes exchangeable, symmetric paired differences, covers only this current rule family, and does not account for all earlier research rounds. It is a small-sample diagnostic, not a formal acceptance certificate.

A chronological selector using only completed training trades before each quarterly boundary also did not reproduce the most attractive fixed-candidate statistics. Across all 384 rules, it produced 3.17% average return, 50% wins, 26.57% compounded return, and 9.07% recorded drawdown. Restricted to 192 partial-profit rules, it produced 4.75%, 50%, 42.35%, and 6.60%, respectively. Candidate definitions were still developed retrospectively, so these are not pristine out-of-sample results either.

**Research judgment:** retain the bounded early-failure architecture as the most useful new hypothesis; do not claim a robust optimum or a proven 75% future win rate. Keep same-fraction slow-exit controls and the time-only control in future evaluation. More formula search on these same events cannot manufacture independent evidence.

## 10. Verification, reproduction, and next data boundary

The current source passed 60 local unit tests. Default outputs for all 384 annual rules matched their recorded grid results after optional execution-stress controls were added. The new engine also reproduced 26 original v5 fixed-target/full-rollover trade results exactly. There were 24 actual-data feature-prefix comparisons and 105 action-prefix experiments checking that removing future observations did not change prior features or decisions. Quantity conservation, positive fills, and upward-only stop changes were also checked. These observations validate specified software behavior, not predictive accuracy.

The downloadable package contains code, tests, selected CSV evidence, this report, and digests. It does **not** contain the complete raw price snapshots or every grid trade row. The full local-host archive contains the frozen SOXX hourly and recent 15-minute snapshots, QQQ benchmark snapshot, implementations, grid results, detailed validation, and the compact checkpoint. Its canonical artifact owner is:

`/Users/mini4/.local/share/mastermind-review-artifacts/SOXX_GRANULAR_EXITS_20261009_v6`

Protected procedure was pinned at `326c8469a21d7f50fc9ecb1848196bf1c6e66685`. No uncertain modifying effects or active background processes remain at closeout.

The next material data-dependent evaluation requires independent new observations and longer genuine subhourly history. BOATS can test overnight information and execution separately, with verified venue timestamps, bid/ask evidence, comparable time horizons, and explicit session conventions. These results should not be relabeled as 24-hour results when that feed arrives.

## Evidence files

- `matched_comparison.csv`: six same-size comparisons; isolates the early-window effect.
- `matched_trade_ledger.csv`: all 39 combinations of 13 entry dates and three partial fractions, old versus new.
- `broad_comparison.csv`: selected alternatives, prior results, timer counts, and paired diagnostics.
- `stress.csv`: cost, latency, stop-fill, limit-fill, and path-order tests.
- `window_sensitivity.csv`: the early-window neighborhood.
- `transfer.csv`: unchanged rules on alternative entry sets.
- `recent_30m_entry_case.csv`: actual subhourly single-episode alternatives.
- `chronological_selection.csv`: quarterly choices and subsequent fold outcomes.

## Methodological sources

These sources support execution and inference cautions, not the SOXX performance numbers, which are computed from the recorded research snapshots.

1. TradingView, *Strategies*: historical OHLC assumptions, gap fills, and execution modeling. https://www.tradingview.com/pine-script-docs/concepts/strategies/
2. TradingView, *Strategy FAQ: trailing stops*: distinction between historical intrabar assumptions and close-updated custom trails. https://www.tradingview.com/pine-script-docs/faq/strategies/
3. SEC Investor.gov, *Stop, Stop-Limit, and Trailing Stop Orders — Investor Bulletin*: stop prices do not guarantee execution prices. https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15
4. Bailey, Borwein, López de Prado and Zhu, *The Probability of Backtest Overfitting*: limitations of selection based on historical simulations. https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253
5. CFA Institute, *Why One Stop-Loss Rule Cannot Fit Every Holding* (September 8, 2026): volatility- and purpose-aware stop design. https://rpc.cfainstitute.org/blogs/enterprising-investor/2026/one-stop-loss-rule-cannot-fit-every-holding