# SOXX — full-entry exit validation and bounded re-entry research

**Research series:** v7, continuation of the October 9, 2026 study  
**Requested-year window:** October 9, 2025–October 8, 2026  
**Earlier comparison:** December 16, 2024–October 8, 2025  
**Status:** retrospective research; no live trades, production changes or true overnight feed

## Executive finding

Restoring the original ten observable entries makes the exit result less spectacular, but more representative of the frozen entry rule. The quarter-sale early-guard strategy averaged **+4.18%**, with **70% wins** and **4.66% recorded drawdown**. The previous eight-entry headline was +5.30%, 75% wins and 2.51% drawdown. The change is sample composition, not a retuned entry or a new stop.

One bounded re-entry after an early exit did not improve the tested strategy. The only re-entry variant that traded in the main sample added two losing legs. Meanwhile, an eight-session timed exit with the same early guard was competitive with the 3H momentum exit. These results strengthen the case for selective entry and early failure protection, but do not establish an optimal exit or demonstrate accurate forecasting of tops.

No new unseen price observations were added. This continuation tests frozen definitions against additional previously excluded entries, simpler controls and wider entry populations from the same historical snapshot.

## 1. Why the original ten entries belong in the main comparison

The preceding exit study required the complete maximum **65-RTH-hour future window** to be available for every comparison. That eliminated the November 5, 2025 and February 2, 2026 entries because source bars were missing later in those maximum windows. This was transparent retrospective data-quality selection, but it was unnecessarily restrictive for policies whose positions closed before the data hole.

This continuation admits the frozen entry without looking at that future maximum window. It simulates the actual exit and then audits the observed path up to that exit. A missing intraday interval or a trade not finished by the dataset endpoint is recorded as unresolved, not assigned a favorable price or silently deleted from the portfolio.

Both restored entries have complete observed actual paths under the headline guard, slow exit and fixed-target rules. The November trade closes before its later data gap; the February trade stops before its later gap. Their contributions are:

| Original entry | Fixed +2% exit | Quarter-sale slow exit | Quarter-sale early guard | Guard exit |
|---|---:|---:|---:|---|
| November 5, 2025, 10:30 ET | +1.90% | −0.72% | +0.13% | November 6, 10:30 ET |
| February 2, 2026, 09:30 ET | +1.90% | −0.72% | −0.72% | February 4, 10:30 ET |

They are not fresh or independent observations. Restoring them removes one specific source of selection, not all retrospective bias. The actual-path audit checks adjacent same-day source bars; it does not independently certify all exchange-calendar sessions, quotes or tick-level execution.

## 2. Full ten-entry results

| Exit policy | Trades | Win rate | Average net return | Compounded return | Recorded drawdown |
|---|---:|---:|---:|---:|---:|
| Sell all at +2% | 10 | 80% | +1.18% | +12.37% | -2.51% |
| 25% at +2%; slow 3H rollover | 10 | 40% | +3.55% | +39.01% | -6.60% |
| 25% at +2%; early guard + slow rollover | 10 | 70% | +4.18% | +48.19% | -4.66% |
| 50% at +2%; early guard + slow rollover | 10 | 80% | +3.18% | +35.65% | -3.27% |
| Quarter-sale guard plus one break/re-entry | 10 | 50% | +3.95% | +44.68% | -5.80% |


All rows use the original 3H-context/1H-pivot entries, a 1.5% initial stop, a maximum 65 observed RTH hours and modeled costs of 5 basis points per side. For re-entry, the maximum clock is measured from the original entry and is not restarted. Partial-sale proceeds remain cash. There is no leverage, new capital or pyramiding.

Returns are per original position. Compounding assumes the entire available hypothetical portfolio is deployed in each non-overlapping original position and otherwise earns zero. It is not personalized account sizing or a recommendation to make a full-account trade. Drawdown is measured at recorded closes and fills, not every intrabar or overnight tick.

The quarter-sale guard's **median** trade was only **+0.56%**, versus a +4.18% mean. The half-sale guard's median was +1.00%. A handful of large recoveries continue to drive much of the mean return. Removing the best requested-year quarter-sale guard trade leaves a +2.91% mean. The five earlier trades average +2.08%; removing their best leaves +1.32%.

At 15 basis points of costs per side, the quarter-sale guard averages **+3.98%** and its win rate drops to **60%**. The half-sale version averages +2.98%, with 70% wins. Very small protected profits should not be described as robust wins independent of execution costs.

## 3. Frozen entry and exit definitions

The entry remains a dramatic downside extension on **3H MACD 8/21/5**, with **Stoch RSI 14/14/3/3** recently at or below 20. The histogram extension is at least twice the root-mean-square magnitude of its preceding 80 bars; the current observation is not used to scale itself. A confirmed smaller price pivot and improving 1H momentum then select the entry. The main lower panel uses MACD 5/13/4, Stoch RSI 7/7/3/3 and conventional RSI(14). The pivot is available only after its confirming bar, not retroactively at its low.

The early guard is unchanged from v6. Between **3 and 6.5 observed RTH hours** after entry, it checks whether the high since entry reached +2%, the completed close subsequently fell below +1%, and either RSI(14) is below 50 or the close is below the 1H EMA10. If so, the remaining shares exit at the next observed open. The special detector expires after 6.5 hours. The original stop never widens and is not automatically moved to breakeven.

For the slow exit, a completed **3H RSI(14) ≥65 and Stoch RSI K ≥80** activates a watch. A subsequent bearish K/D crossover with a falling MACD histogram closes the remainder at the next observed open. The slow exit panel uses MACD 12/26/9 and Stoch RSI 14/14/3/3. It is different from the faster setup panel by design.

Conventional RSI and Stoch RSI thresholds are separate quantities. A histogram downturn means decelerating momentum, not necessarily a negative histogram or proof of a top.

## 4. Bounded re-entry: tested, not supported by these observations

The experiment allowed **one** new leg only after an early-guard exit, not after a hard stop or a mature momentum exit. The prospective definition required one of three completed 1H patterns within either 6.5 or 13 trading hours:

1. Reclaim the higher of the original entry price and failure-signal high, with price above EMA10, RSI at least 50 and the histogram rising.
2. Close above the preceding two highs, above EMA10, with RSI at least 50 and rising, and a rising histogram.
3. Two completed closes above EMA10 with RSI at least 50, plus latest histogram improvement.

The new leg can restore no more than the previously exited remainder. Its purchase is limited by the net sale proceeds and a planned aggregate stop-distance risk budget. A 1.5% stop applies to the new leg; gaps can still exceed that planned loss. Fresh entry and exit costs are charged. The already-realized partial is not implicitly redeployed as a new full-size position.

Only the second pattern with the 13-hour window triggered in the main ten-entry sample:

| Original episode | Early exit net | Re-entry | Additional effect per original position | Final episode net |
|---|---:|---|---:|---:|
| November 5, 2025 | +0.13% | November 10, 10:30 ET | −1.19 percentage points | −1.06% |
| June 8, 2026 | +0.58% | June 10, 10:30 ET | −1.20 percentage points | −0.61% |

The quarter-sale policy's mean fell from **4.18% to 3.95%**, win rate from 70% to 50%, and recorded drawdown increased from 4.66% to 5.80%. The other defined variants made no re-entries and therefore add no new evidence of success.

This result argues against adding this automatic re-entry mechanism to the current frozen candidate. It does not show that every possible re-entry method is ineffective. The experiment deliberately did not search for a rule that rescues these two losing legs after seeing them.

## 5. A simpler exit is competitive

To test whether the oscillator really identifies a useful top, the same quarter-sale strategy and early guard were run with a scheduled time exit replacing the slow momentum condition. When the age threshold is reached at a completed bar, the exit occurs at the **next observed opening price**, matching the information/execution separation used for momentum exits.

| Time exit, then next observed open | Earlier mean (5 trades) | Requested-year mean | Requested-year trades | Compounded return |
|---|---:|---:|---:|---:|
| 13 RTH hours (~2 sessions) | +0.75% | +1.42% | 10 | +14.82% |
| 19.5 RTH hours (~3 sessions) | +0.73% | +2.04% | 10 | +21.71% |
| 26 RTH hours (~4 sessions) | +0.93% | +2.84% | 10 | +31.11% |
| 32.5 RTH hours (~5 sessions) | +0.96% | +4.24% | 10 | +48.89% |
| 39 RTH hours (~6 sessions) | +0.99% | +3.85% | 10 | +43.83% |
| 52 RTH hours (~8 sessions) | +2.23% | +4.34% | 10 | +50.19% |


The 52-hour timer averaged **+4.34%**, compared with **+4.18%** for the slow momentum rule, on the same ten entries. Both had 70% wins and approximately 4.66% recorded drawdown. The earlier five-trade mean was +2.23%, versus +2.08% for momentum. A five-session timer was also competitive in the requested year, but its earlier performance was less convincing.

The 65-hour next-open timer took only nine original entries because an existing position overlapped a later signal. Its results are retained in the table file but excluded from the same-ten headline comparison. The calendar time of a timed trade can be much longer than its observed RTH-hour count because nights, weekends and holidays intervene.

The timer's mean advantage over momentum is only **0.15 percentage points**. Its unadjusted entry-month bootstrap interval is approximately **−0.04 to +0.44 percentage points**. This does not establish an eight-session optimum. It shows that a simple holding-period explanation remains competitive with a claim of momentum-top detection.

## 6. Broader entry audit

Frozen wider entry definitions were evaluated without the future-65-hour prefilter:

| Entry family with quarter-sale guard | Requested-year episodes | Resolved outcomes | Mean of resolved outcomes | Earlier resolved mean |
|---|---:|---:|---:|---:|
| Main 3H context + 1H pivot | 10 | 10 | +4.18% | +2.08% (5) |
| Any qualifying 2H/3H/4H context + 1H pivot | 13 | 12 | +3.82% | +1.97% (5) |
| 1H pivot without higher-timeframe extreme prerequisite | 45 | 41 | +0.96% | −0.19% (27) |

The combined-timeframe family has one unresolved end-of-sample trade. The unfiltered family has three trades with missing actual intraday paths and one unfinished at the data endpoint. Whole-stream compounded return and drawdown are intentionally blank when any outcome is unresolved. Means of known outcomes are descriptive and can themselves be affected by which outcomes are missing.

The broader unfiltered entry rule did not become robust just because the exit was improved. Its earlier period remained negative. This supports retaining the selected higher-timeframe setup as part of the research hypothesis, not treating the exit as a universal money-making overlay.

## 7. Statistical interpretation

On the full ten-entry comparison, the guard changes three outcomes relative to the same quarter-sale slow exit. The matched mean improvement is **+0.63 percentage points**. A descriptive entry-month block bootstrap gives approximately **0.00 to +1.60 percentage points**, and the exact one-sided sign-flip diagnostic is 0.125. These are exploratory, unadjusted diagnostics; neither is a prospective validation or a correction for all previous strategy searches.

The full data have already been inspected repeatedly. Nearby parameter success, additional configuration rows and resampled trade histories are not new independent market evidence. No untested performance probability is assigned to the 70% win rate.

## 8. Data, execution and verification boundaries

The frozen hourly source contains 3,473 accepted regular-session observations used across the warmup and study periods. No synthetic subhourly prices or overnight bars were generated. Positions may span overnight, but their overnight price paths are unobserved. Stops crossed at an observed gap fill at the next observed price rather than at an invented stop price. Reported stop distances are not guaranteed loss limits.

The main numerical methods are deterministic and replayable from the archive. Verification in this continuation comprised:

- **21 passing local unit tests**, covering cash-limited quantities, aggregate planned risk, re-entry conditions, weighted returns, unresolved-outcome handling and next-open timer decisions.
- **269 truncated-path replay checks** on actual candidate outcomes and four re-entry budget/chronology checks. The four checks cover the same two physical re-entry events under different partial sizes.
- **20 independent arithmetic checks** recomputing the five main summary rows from their ten-trade ledger.
- Algorithm-AST equality for all five new modules between local source and the remotely executed source, plus byte-level checks for the downloaded selected result files.

The truncated-path check reuses the already-computed point-in-time feature panels; it is not a fresh independent recomputation of every indicator on every prefix. Source data were not independently reconciled to a second licensed historical feed, exchange calendar or tick/quote archive in this continuation. Software verification does not prove a financial edge.

The main study comprises 18 policy definitions, two cost assumptions, two sample-handling modes and three entry families, resulting in 432 period summaries. The timer diagnostics add 14 close-fill controls and seven next-open controls. These counts describe experimental work, not independent opportunities.

## 9. Research disposition

Use the full ten-entry audit, not the more attractive eight-entry subset, as the primary account of the original entry rule. Retain both the early-guard/slow-exit and early-guard/52-hour-time-exit definitions as comparisons. Retain quarter and half partials as different risk/return choices; do not claim one is universally optimal. Do not add automatic re-entry on the current evidence.

The next external-data test remains a longer actual subhourly record and the user-supplied BOATS history, with comparable indicator horizons, licensed source provenance, session coverage and executable-price checks. Neither longer historical history nor fresh observations have been substituted by retuning the same sample.

**Execution status:** all research processes finished. No live trades, account authentication, deployment, repository modifications or background research service were created.

## Evidence and reproducibility

Selected CSVs accompany this report. The conversation ZIP contains the research code, tests, selected result files, local validation receipt and this report. It does **not** contain the raw market-data snapshots or the full large simulation result file. Those are preserved in the full remote archive referenced by `remote_receipt.json`.

Frozen source SHA-256: `ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720`.

Protected procedure commit: `326c8469a21d7f50fc9ecb1848196bf1c6e66685`.

Primary external references, used for execution cautions rather than as evidence for the measured strategy returns:

- Investor.gov, *Stop, Stop-Limit, and Trailing Stop Orders*: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15
- TradingView official strategy documentation, broker-emulator and next-tick order mechanics: https://www.tradingview.com/pine-script-docs/concepts/strategies/

All reported historical performance numbers were calculated from the frozen research snapshots and executed code, not taken from those reference pages.