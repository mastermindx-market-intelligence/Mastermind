# SOXX intraday MACD + Stochastic RSI backtest

**Report date:** October 9, 2026  
**Requested evaluation window:** October 9, 2025–October 8, 2026, inclusive.  
**Earlier comparison window:** December 16, 2024–October 8, 2025.  
**Data:** Yahoo Finance SOXX 60-minute regular-session OHLCV candles, with 2H/3H/4H bars aggregated from them; two years of history loaded for indicator warm-up.

## Executive conclusions

1. **Buying downside extensions works better than shorting upside extensions** in the unusually strong 2025–26 SOXX uptrend (SOXX rose approximately 93.5% over the test window on the hourly-source open/close calculation). A signal must be judged against this strong positive drift.
2. **4H MACD(5,13,4) + StochRSI(7,7,3,3) + extreme histogram** was the strongest narrow, strict-extension candidate across the two separate periods: 6/7 profitable after ~3 sessions in the earlier period, 6/7 in the requested year. The latest-year mean was +3.759% after modeled costs, but a tight 1.5% stop / 2% target degraded this to four wins of seven and -0.024% per trade after costs.
3. **2H MACD(12,26,9) + StochRSI(14,14,3,3), 20/80 slope reversal with a 2x histogram extension** had 7/8 earlier-year and 7/10 requested-year profitable 3-session outcomes. More importantly, the requested-year 1.5% stop / 2% target strategy had 6/10 wins and +0.694% average per entry.
4. **3H strict configurations were less stable.** MACD(8,21,5) + StochRSI(21,21,3,3), 10/90 slope reversal, fell from 5/6 to 6/12 three-session wins across the two periods.
5. **Do not use upside extremes alone as a short trigger.** The earlier-year best-looking 4H top MACD(12,26,9) + StochRSI(21,21,3,3), upper-zone slope reversal, went from 8/12 profitable shorts to 4/13 in the requested year, averaging -1.007% per short (3-session hold).

These are **exploratory** comparisons, not predictive certification. The 7,776 grid rows (3 timeframes × 4 MACD settings × 3 StochRSI settings × 12 extreme variants × 3 zone thresholds × 3 confirmations × 2 directions) create substantial selection/multiple-testing bias. Signals across adjacent settings are correlated, not independent.

## Exact entry rule in tested runs

- Compute indicators from completed RTH OHLCV candles; aggregate original hourly candles anchored at 9:30am Eastern each session. A 4-hour session splits into a full 4h bar followed by a shorter 2.5h closing bar; likewise 2h and 3h have shortened final bars.
- MACD parameters vary across `(5,13,4)`, `(8,21,5)`, `(12,26,9)`, `(16,34,9)`.
- Stoch RSI configurations vary across `(7,7,3,3)`, `(14,14,3,3)`, `(21,21,3,3)`; the final 3+3 smoothings are simple moving averages of raw Stoch RSI %K.
- Histogram RMS extension: histogram magnitude at signal or previous two aggregates must have reached >= 1.5x/2x/2.5x/3x RMS of the **preceding 80 completed corresponding-timeframe histograms**, with the correct positive/negative sign. Normalization excludes the current MACD value from the rolling 80 bars.
- Additional tested normalizations: MACD line / trailing 80-bar RMS, histogram / 14-period ATR, and combined histogram+line RMS requirements. Stoch RSI bounds at 10/90, 20/80, 30/70.
- Long: histogram must remain below zero but its latest change must be upward. Stoch RSI K must have reached the low zone and start rising (`slope`), cross over D in the oversold region (`cross`), or reclaim the zone (`reclaim`). Short mirror is reversed.
- Enter at the **next available hourly RTH opening price** after the aggregate closes; not at the earlier visible bottom or signal candle midpoint.
- De-duplicate signals of the same parameter set/direction by at least seven underlying hourly bars.
- Fixed holding horizons: 7, 14, 21 underlying RTH hourly bars (roughly 1, 2, 3 sessions); 0.10% total round-trip trading cost for each completed trade; dividends excluded.
- The fixed-horizon signal table **allows overlapping holding periods** (an event study); a separate realistic single-position strategy permits only one active trade and uses a path-dependent stop/target exit. Both gap exits and adverse-first fills if stop and target lie inside the same hourly candle are addressed.

## Strict extension, long-side comparison

For each row the threshold is histogram ≥2.0x trailing RMS in magnitude, correct negative sign, and histogram starting to turn upward.

| Timeframe | MACD | Stoch RSI | Stoch threshold | Confirmation | Previous period (n; win; mean 3-day) | Requested period (n; win; mean 3-day) |
|---|---|---|---|---|---|---|
| 2H | 12/26/9 | 14/14/3/3 | K ≤ 20 | Rising slope | 8; 87.5%; +3.720% | 10; 70.0%; +2.243% |
| 3H | 8/21/5 | 21/21/3/3 | K ≤ 10 | Rising slope | 6; 83.3%; +4.551% | 12; 50.0%; +1.392% |
| 4H | 5/13/4 | 7/7/3/3 | K ≤ 10 | Bullish K/D cross | 7; 85.7%; +2.328% | 7; 85.7%; +3.759% |
| 4H | 5/13/4 | 14/14/3/3 | K ≤ 10 | Bullish K/D cross | 6; 83.3%; +1.741% | 8; 100.0%; +3.262% |
| 4H | 5/13/4 | 21/21/3/3 | K ≤ 10 | Bullish K/D cross | 4; 75.0%; +1.080% | 6; 100.0%; +3.827% |

**Warning:** These five models were chosen while examining results across hundreds of parameter combinations. The 4H 14/14 and 21/21 results are not independent confirmations of the 7/7 results because their entries may coincide. The near-perfect outcome rates are especially vulnerable to small samples and model-selection bias.

## Accuracy changes with holding horizon (requested year)

| Model | n | Mean ~1-session | Mean ~2-session | Mean ~3-session | 3-session win rate |
|---|---:|---:|---:|---:|---:|
| 2H strict long 12/26/9 +14/14 | 10 | +0.175% | +0.954% | +2.243% | 70.0% |
| 3H strict long 8/21/5 +21/21 | 12 | −0.576% | −0.168% | +1.392% | 50.0% |
| 4H strict long 5/13/4 +7/7 | 7 | −0.515% | +0.978% | +3.759% | 85.7% |
| 4H strict long 5/13/4 +14/14 | 8 | +0.021% | +0.323% | +3.262% | 100.0% |

These are **not immediate two-hour turning-point entries**: many become profitable after two or three sessions, with severe temporary drawdowns before then.

## Actual path-dependent stop/target trade results (requested year)

Entries are taken at the next available RTH hourly open; stop and target fills are based on hourly OHLC, with adverse-first precedence when both intrabar levels are hit, and gap crossings filled at the opening price.

| 4H fast 5/13/4 + Stoch 7/7; histogram RMS ≥ 2 | Winners | Mean net return per trade | 1-position compounded return, signal-only exposure |
|---|---:|---:|---:|
| Hold 21 hours, ignore stop/target | 6/7 | +3.759% | Event-only compounded result not recomputed in the stop/target run |
| Stop 1.5%, target 2% | 4/7 | −0.024% | −0.45% |
| Stop 2%, target 3% | 4/7 | −0.046% | −0.76% |
| Stop 3%, target 4% | 4/7 | +0.383% | +2.10% |

| Other strategy (requested year) | Stop / target | Winners | Mean net per entry | Compounded single-position return |
|---|---|---:|---:|---:|
| 2H strict 12/26/9 +14/14 | 1.5% / 2% | 6/10 | +0.694% | +6.95% |
| 2H strict 12/26/9 +14/14 | 2% / 3% | 5/10 | +0.505% | +4.81% |
| 4H fast 5/13/4 +14/14 | 1.5% / 2% | 3/8 | −0.699% | −5.72% |
| 4H fast 5/13/4 +14/14 | 2% / 3% | 4/8 | −0.303% | −2.84% |
| 4H moderate 8/21/5 +7/7 with H/ATR ≥ 0.18 | 1.5% / 2% | 16/31 | +0.360% | +10.82% |
| 4H moderate 8/21/5 +7/7 with H/ATR ≥ 0.18 | 2% / 3% | 16/31 | +0.515% | +15.79% |

The latter 4H moderate normalization was one of the more stable high-frequency long configurations across both years, but **histogram / ATR ≥ 0.18 is substantially less restrictive than a rare ≥2x histogram-RMS extreme**, so it does not meet a strict "dramatic extension only" criterion by itself.

The 4H strict 5/13/4 + 7/7 signals had mean intratrade **maximum adverse excursion −4.176%** in the requested period. Only **28.6%** of those signals appeared within 1.5% of the ex-post two-session local price low. The indicator often forecasts a later rebound **without timing the exact bottom**.

## Classical indicator sensitivity without tuning the period

Fixed MACD 12/26/9, StochRSI 14/14/3/3, 20/80 bullish/bearish K/D cross. The histogram threshold is in RMS multiples of the prior 80 histograms.

| TF | Side | Hist RMS 1.5x (signals; win; mean) | 2x | 2.5x |
|---|---|---|---|---|
| 2H | Long | 17; 52.9%; +0.728% | 8; 50.0%; +1.110% | 5; 80.0%; +4.601% |
| 3H | Long | 18; 61.1%; +2.502% | 8; 50.0%; +2.630% | 4; 75.0%; +3.278% |
| 4H | Long | 15; 66.7%; +1.678% | 10; 60.0%; +0.563% | 3; 66.7%; +2.079% |
| 2H | Short | 17; 35.3%; −1.612% | 7; 42.9%; −0.978% | 0 |
| 3H | Short | 13; 15.4%; −3.765% | 6; 16.7%; −2.524% | 1; 0%; −0.357% |
| 4H | Short | 7; 14.3%; −2.175% | 5; 0%; −3.001% | 1; 0%; −4.483% |

**More dramatic is not automatically more accurate.** Tightening the MACD threshold dramatically reduces the number of trades; isolated 80–100% rates at 1–5 signals are not credible proof of a superior configuration.

## Tops: promising in the prior period, poor in the requested year

Prior-calibrated 4H top model MACD 12/26/9 + StochRSI 21/21/3/3, positive histogram > 1.5 RMS, upper zone 70, Stoch RSI K turning down:

- Calibration: 12 short signals, 66.7% profitable after three sessions; mean +2.571%.
- Requested year: 13 short signals, 30.8% profitable after three sessions; mean **−1.007%**.
- Requested-year path-executed 1.5% stop / 2% target: 30.8% winning, mean **−0.483%**, a one-position sequence approximately −6.98%.

In this uptrend, upper-zone MACD/Stoch reversal is better investigated as a **profit-protection / caution alert**, not an unconditional short.

## Baseline, quality and validity

- The test-year raw SOXX open-to-last-hour-close appreciation was +93.47%; adjusted total return including dividends is **not** modeled.
- Across all hourly RTH entry points with enough forward history, a long held for 21 regular-session hourly bars averaged +0.836%, with 58.3% winners. These heavily overlapping comparison returns are descriptive, **not** a directly tradable benchmark.
- Raw hourly rows: 3,473 valid bars after exclusion of 24 incomplete or zero-volume records and one 16:00 zero-width marker; missing half-day data excluded. The test year contains approximately 997 aggregated 2H, 746 aggregated 3H, and 500 aggregated 4H bars; roughly one final shortened bar per trading day.
- Backtest ignores leverage, margin borrowing, commissions beyond assumed total 0.10%, taxes, bid/ask variability, liquidity-sensitive slippage, and dividend-adjustment effects. The short side excludes securities-lending fees and borrow constraints.
- In a 4H session model the shortened final 2.5h bar is counted as a completed bar. A vendor chart with different 4H anchoring or extended-market session bars will produce different signals.
- Selecting the best among 7,776 results after seeing the requested year's returns causes **look-ahead at the model-selection level**, even though each individual signal itself uses only data available at the time. Treat the requested year as **exploratory for finalists**, despite the useful earlier-period comparison; a genuinely untouched forward period remains necessary.
- Stop results use next RTH opening prices for gap crossings and pessimistic stop-first intrabar execution. Real commissions and slippage can be higher.

## Research recommendation

For a **strict dramatic downside-extension watchlist**, start with:

- A: 4H MACD 5/13/4, histogram < 0 and ≥2× prior 80-bar RMS in absolute terms, StochRSI 7/7/3/3 or 14/14/3/3 K reaching ≤10, positive-turn K/D cross. Use as a rebound watch signal, **not an automatic buy**. The typical turnaround lag and 4% adverse excursion require a second entry/stop model.
- B: 2H MACD 12/26/9, negative histogram ≥2× RMS and starting to shrink, StochRSI 14/14/3/3 K≤20 with bullish turn. More modest holding-return accuracy but better historical performance of the specified 1.5%/2% protective execution.

Before capital deployment, add macro/sector regime gating, 30m/60m reclaim structure, bar-anchoring sensitivity, volume confirmation, walk-forward multiple-comparison adjustment, realistic friction and overnight gap stress tests. Confirm direction and execution together, not only fixed-horizon accuracy.

**Working evidence on authorized `mini4` at time of run:** `/tmp/soxx_backtest_20261009.py`, `/tmp/soxx_stochmacd_20261009/parameter_grid.csv` (7,776 configurations), `/tmp/soxx_stochmacd_20261009/shortlist_trades.csv` (225 signal rows for targeted models across both periods), `/tmp/soxx_stochmacd_20261009/risk_exit_trades.csv` (675 exit-scenario rows), source hourly snapshot and summary JSON. Files in `/tmp` can be ephemeral and are not automatically transferred to this report download.

**Data references:** [SOXX Yahoo Finance historical prices](https://finance.yahoo.com/quote/SOXX/history/); [StockCharts StochRSI](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/stochrsi); [Fidelity MACD technical indicator](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd).