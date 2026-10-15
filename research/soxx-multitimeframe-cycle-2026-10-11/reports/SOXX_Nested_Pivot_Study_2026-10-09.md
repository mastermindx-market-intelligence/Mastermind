# SOXX: lower-timeframe pivots inside a dramatic higher-timeframe setup
## Regular-session nested-pivot study | October 9, 2026 | v4

**Finding:** A confirmed local price pivot is a more promising entry trigger than another oscillator crossover in this sample. The strongest newly identified annual nested-price-pivot candidate is a **3H extreme setup plus a confirmed 1H pivot**, with 8 winners in 10 requested-year trades using a 1.5% stop and 2% target. Requiring higher and lower momentum to be turning together produced 4 winners in 5 trades, but a three-session cooldown reduced that to 2 winners in 3 trades.

**No 15-minute/30-minute winner is established.** Actual subhourly data was obtained, but the matched finer-data window contains only one shared completed long selloff/recovery episode. The 15-, 30-, 45- and 60-minute cases are alternative executions of that same episode, not independent successful predictions. No BOATS data or 24-hour execution was used.

All numerical findings are calculations from the archived Yahoo chart snapshots using the accompanying research code. These are retrospective price-return simulations, not live fills, annual return forecasts, or recommendations to size a position.

## 1. What was tested

The first arm retains the original requested year, **October 9, 2025–October 8, 2026**, for 60-minute entry triggers inside 2H, 3H and 4H setups. The earlier comparison period is December 16, 2024–October 8, 2025. Indicators warm up on additional 2024 history. The requested year has already been inspected repeatedly and is not an untouched holdout.

The finer-data request returned actual 15-minute observations beginning July 17, 2026. After excluding October 9 to preserve the fixed endpoint, the retained input has **1,534 15-minute bars across 59 regular sessions**. The same-window 15/30/45/60-minute comparison starts August 17 to allow lower-timeframe warmup and ends October 8. A one-year 15-minute request was rejected with HTTP 422. No subhourly bars were inferred from hourly OHLC.

A total of **5,840 primary configurations** generated 10,865 configuration-level trade rows. Those are computational counts, not independent opportunities. They include both directions, three higher-timeframe states, six lower-timeframe trigger families, two lower indicator profiles, and alternative stop models. The original high-timeframe profiles were held fixed:

| Higher timeframe | MACD fast/slow/signal | Stoch RSI RSI/stochastic/K/D |
|---|---|---|
| 2H | 12/26/9 | 14/14/3/3 |
| 3H | 8/21/5 | 14/14/3/3 |
| 4H | 5/13/4 | 14/14/3/3 |

Lower-timeframe profiles were MACD **5/13/4 with Stoch RSI 7/7/3/3**, and MACD **8/21/5 with Stoch RSI 14/14/3/3**. A separate conventional RSI(14) was also calculated. RSI and Stoch RSI are not interchangeable; the code uses each explicitly.

## 2. Qualifying the larger setup

For a long, a completed higher-timeframe candle must show a negative MACD histogram at least twice the RMS magnitude of its preceding 80 histogram values, together with Stoch RSI K at or below 20 during the latest three higher-timeframe bars. The current bar is not included in its own historical magnitude scale. This is a zero-centered RMS normalization, not a conventional mean-centered standard-deviation z-score.

Only the first qualifying extreme in each same-sign histogram episode arms a setup. There is no buying every later crossover. The setup expires after **26 observed regular-session hours**; one first lower-timeframe entry candidate is allowed per episode. Risk-bound rejection does not open an unlimited retry loop. One position at a time is enforced, and the combined profile de-duplicates coincident entry times.

Three distinct parent states were compared:

- **Armed extreme context:** the large extension occurred, but higher momentum need not already have turned.
- **Both turning:** the latest completed higher histogram remains negative but is rising; higher Stoch K is rising and at/above D. A lower pivot must qualify while that state holds.
- **Recovered:** the higher histogram is positive and higher Stoch K is at/above D and at least 20.

The first is a nested setup, not proof that both timeframes pivoted together. The second is the closest tested implementation of simultaneous momentum confluence. Simultaneous means both conditions are available from completed bars at the decision time; it does not mean the low points were known retrospectively at exactly the same instant.

## 3. Defining a tradable local pivot

The local price-pivot trigger uses **two bars to the left and one bar to the right**. The candidate low must be below the two preceding lows and no higher than the following bar's low. It is recognized only after that following bar closes. At confirmation, conventional RSI(14) must be rising after a reading no greater than 45 near the pivot, the lower MACD histogram must be improving, and lower Stoch RSI K must be at/above D. An entry is taken at the next source-bar open, never at the earlier pivot's low.

Other triggers were Stoch K/D crosses after 20 or 30 oversold zones; RSI recovery through 40; a MACD/signal crossover; and a local price reclaim above the previous two highs with a higher low and positive candle body following a recently confirmed pivot.

A lower-timeframe signal uses only higher candles whose closing timestamps have already occurred. Indicator and pivot prefix tests check that appending future candles does not change prior values. This addresses the well-known higher-timeframe lookahead/repainting problem described in TradingView's primary documentation [1]. Pivot-based plots also need confirmation after the low; plotting the final pivot on its earlier candle does not make it knowable there [2].

## 4. Main annual results

Base costs are 5 basis points per side. 'Tight' exits are a 1.5% stop and 2% target. Entries and exits are hypothetical. Compounding assumes unlevered full notional allocated per non-overlapping trade, with cash otherwise, and is not fixed-account-risk sizing.

| Candidate | Earlier trades / win rate | Requested-year trades / win rate | Mean net requested-year trade | Compounded return | Initial stop |
|---|---:|---:|---:|---:|---:|
| 3H extreme context + 1H confirmed pivot, fast lower profile | 5 / 60.0% | **10 / 80.0%** | **+1.1835%** | +12.371% | 1.5% |
| Any qualifying 2H/3H/4H context + 1H pivot, balanced lower profile | 5 / 60.0% | 12 / 75.0% | +1.0112% | +12.674% | 1.5% |
| Higher and lower momentum both turning + 1H pivot | 4 / 75.0% | **5 / 80.0%** | +1.1994% | +6.091% | 1.5% |
| Same 1H pivot, no higher-timeframe extreme prerequisite | 31 / 48.4% | 54 / 55.6% | +0.1836% | +9.212% | 1.5% |
| Higher MACD recovery alone, hourly ATR stop control | 7 / 57.1% | 11 / 72.7% | +1.5129% | +17.510% | Mean 1.9206% |

The higher-timeframe-only ATR control remains competitive and has a higher mean return in units of initial risk: **0.988 R** versus **0.789 R** for the 3H/1H local-pivot candidate. This study does not show that the finer entry universally maximizes returns. Its apparent benefit is earlier entry and a useful tighter-stop profile for a subset of extremes.

### Identical-risk oscillator comparison

Within the same 3H extreme context, with balanced 1H MACD 8/21/5 and Stoch RSI 14/14/3/3, and the same 1.5% stop/2% target:

| 1H entry trigger | Trades | Win rate | Mean net trade |
|---|---:|---:|---:|
| Stoch RSI bullish crossover from an oversold region | 10 | 40% | -0.2513% |
| MACD crosses its signal line | 10 | 50% | +0.1274% |
| **Confirmed price pivot with momentum recovery** | **10** | **80%** | **+1.1835%** |

The ten trades in each row are not necessarily the same entries. The balanced and fast price-pivot variants happened to select the same requested-year trades. They differ in earlier-period observations, so there is not a unique demonstrated best MACD parameterization.

## 5. Did the local pivot actually enter earlier?

Eight parent episodes had both a 3H-context/1H-pivot entry and a later confirmed higher MACD recovery entry with observable exits. On these paired episodes, the local entry averaged **15.3125 RTH hours earlier** and an approximately **1.75% favorable entry-price difference**. Three local entries were actually at worse prices than waiting; the average benefit was not universal.

Using the same 1.5% stop/2% target for each paired entry, the mean trade-return difference was approximately **+0.417 percentage points**. This is a selected paired event comparison, not an independent portfolio comparison or an adjusted significance test. The individual pairs are in `same_episode_entry_pairs.csv`.

## 6. Robustness and reasons not to overstate the result

For the 3H-context/1H-pivot candidate, the requested-year mean remained **+1.104% after removing its best trade**, and **+0.9822% at 15 basis points per side**. The earlier-period mean was +0.4997%; removing its best trade left +0.1499%. A three-session cooldown left its ten requested-year trades unchanged. All four active calendar quarters had positive means, but Q4 2025's mean was only +0.1102%.

The nominal binomial 95% interval around 8/10 wins is approximately **49.0%–94.3%**. It does not account for model selection, correlated markets, or thousands of inspected alternatives. Active-month clustered bootstrap intervals are included in provenance as descriptive checks only. They are unadjusted for selection and use very few independent clusters. No corrected statistical edge or production admission is claimed.

Nearby extension levels of 1.75, 2.0 and 2.25 RMS and the two lower profiles stayed positive in the requested year, but many selected identical trades. Their agreement is parameter-insensitivity evidence, not independent replication. A cutoff of 2.25 reduced the sample to seven trades.

The stricter both-turning candidate has **only five requested-year trades**, concentrated in Q1/Q2 2026. A three-session cooldown reduced this to **three trades, two winners, +0.7329% mean**. Requiring the parent candle to have closed at the very same decision boundary also left three trades and two winners. This is materially weaker evidence than the attractive 80% headline suggests.

A same-parent-close filter on the broader 3H candidate selected four winners out of four. That is reported in the sensitivity CSV, not promoted as a perfect strategy. The filter was examined retrospectively and has only four observations.

## 7. Actual 15-/30-/45-/60-minute case studies

The matched finer-data sample has one shared completed long episode across the principal 3H/4H setups, around **September 14–17, 2026**. Each row below represents an alternative simulation of that same event.

### Early local pivot while the larger extreme context is active

The balanced lower profile and local pivot-turn rule produced:

| Lower timeframe | Entry, September 15 ET | Initial micro-structure stop distance | Net result with 2R micro target |
|---|---|---:|---:|
| 15 minutes | 09:45 | 1.2192% | +2.3372% |
| 30 minutes | 10:00 | 1.5126% | +2.9236% |
| 45 minutes | 10:15 | 1.2815% | +2.4617% |
| 60 minutes | 10:30 | 1.2823% | +2.4633% |

All four alternatives also reached the 2% target with the separate 1.5% fixed stop. But the higher momentum had not yet met the strict both-turning state at these local pivots. Requiring that state eliminated all four of these *first local-pivot* entries. This demonstrates the tension between early entry and synchronized confirmation; it does not prove earlier is generally better.

### Later price reclaim while the higher timeframe is turning

For the same larger event, waiting for a recent pivot plus a price reclaim and higher-timeframe recovery state produced:

| Lower timeframe | Entry, September 16 ET | Entry price | Initial micro-stop distance | Net result |
|---|---|---:|---:|---:|
| 15 minutes | 10:00 | $509.34 | 2.5207% | +4.9389% |
| **30 minutes** | **09:30** | **$507.50** | **2.2835%** | **+4.4646%** |
| 45 minutes | 10:15 | $508.08 | 2.4680% | +4.8334% |
| 60 minutes | 10:30 | $508.48 | 2.5739% | +5.0451% |

The 30-minute rule entered before the 15-minute rule here. Different aggregation and pivot confirmation produced different triggers; a smaller bar is not automatically an earlier signal. Higher return percentages in other rows reflect different stop distances and hence different 2R targets, not necessarily superior entry prices.

**All four of these later reclaim entries lost under the separate 1.5% fixed-stop/2% target rules**, even though their wider micro-structure stops survived. A fine entry does not justify placing a stop inside the observed price structure. These are alternatives, not two sequential trades the same strategy was authorized to take.

Rebuilding the higher timeframes from the real 15-minute data, after splicing in pre-window warmup history, did not change the selected later case entries or returns. Aggregated recent 60-minute closes matched the frozen hourly source at all 413 overlapping timestamps. This is internal consistency, not independent-vendor corroboration.

## 8. Execution and data qualifications

Bars are anchored to the 09:30 ET regular-session open. Short closing candles are explicitly shorter: a nominal 3H series has a 30-minute closing stub; nominal 4H has a 2.5-hour closing bar. They are not fabricated full-duration bars. Missing input marks aggregate candles incomplete. A result described as 'hourly-close drawdown' in the reusable code is a source-bar-close measure; it is a 15-minute-close measure in the finer-data arm, not a guaranteed worst tick drawdown.

All lower-timeframe comparisons in the finer arm execute on the same 15-minute source bars. The annual arm executes on 60-minute source bars, so annual-versus-recent results are not interchangeable. OHLC path ambiguity is resolved stop-first; a stop gapped through is filled at the next observed open. A target gap is credited only at the target, not at a windfall opening price. Raw bid/ask spreads, queue priority, tick paths and executable overnight stops are unobserved. The `exit_ET` trade-ledger field identifies the end of the source bar containing the exit, not an exact intrabar fill timestamp. For a gap fill, execution is modeled at that bar's open.

The maximum hold is 19.5 observed regular-session hours, approximately three regular sessions. Trades can span nights, weekends and holidays. Endpoint gaps do not reconstruct overnight trading. Incomplete end-of-sample horizons are rejected regardless of whether a quick stop or target would otherwise have been favorable. Missing within-session execution paths are rejected. Prior-period trades crossing the evaluation boundary are purged. These are price-return calculations without dividend credits, tax, financing or short-borrow modeling; long results are the focus of this report.

The fine-history retention limit is observed in the source request; yfinance's maintainer documentation also describes limited intraday history [3]. The exact returned window, rather than a general vendor promise, governs this study.

## 9. What to preserve for the BOATS comparison

Retain separate hypotheses: (A) 3H extreme context plus a confirmed local pivot; (B) higher/lower momentum turning together plus a local pivot; (C) a later local price reclaim; and (D) higher MACD recovery without a fine trigger. The 3H/1H rule currently has more historical support than a claim that 15 or 30 minutes is best. The 3H/30-minute reclaim rule is a concrete candidate for the next comparison, not an accepted winner.

Once genuine overnight history is available, hold definitions fixed and compare daytime-input/daytime-execution, full-session-input/daytime-execution, and full-session-input/full-session-execution separately. Match the effective indicator memory and holding period across sessions, preserve venue provenance, and use quotes for execution costs. A 24-hour series has more bars per day, so identical indicator period counts do not have identical clock-time memory. This is a design requirement, not a claim of an overnight edge.

## 10. Verification and reproducibility

The final local unit suite has **31 passing tests** for timing, pivot availability, symmetric stops, RSI warmup, aggregate completeness and trigger rules. On actual market data, **3,113 chronological/prefix assertions passed**, and five targeted recomputations matched the primary results. Prefix invariance tests show indicator and pivot values do not change when future data is appended; these assertions do not establish predictive accuracy.

The six delivered CSVs were read back from the remote computation and their exact SHA-256 digests were verified after copying to this conversation. The download package contains code, tests and selected evidence, not the full 5,840-row grid or all raw input snapshots. The complete raw-data/grid archive is retained on mini4 under the existing review-artifact directory. The main downloadable program is AST-equivalent to the executed program; its module documentation differs, so their byte hashes differ.

Source SHA-256:
- Hourly snapshot: `ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720`
- 15-minute snapshot: `f3fd82f86b6264625e1263e4f46fdae08141aceaa1f5fe8e3699c778943c0426`
- Primary grid JSON: `964c58228fa3f1156783ab99e2e73670e4ceac5103694e6aa3c6bbb1c51d6f12`
- Validation JSON: `20454e6b8b9ac843f7f4de81191c502c692aca6f61347ef74753d21d5c84fd02`

## Sources for methodological facts

[1] TradingView, Pine Script concepts: Other timeframes and data. https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/

[2] TradingView, Zigzag indicator: pivot confirmation and delayed knowledge. https://www.tradingview.com/support/solutions/43000591664-zigzag-indicator/

[3] yfinance maintainer documentation, Functions and Utilities: intraday-history limits. https://ranaroussi.github.io/yfinance/reference/yfinance.functions.html

**Status:** regular-session nested-pivot experiments and specified robustness checks completed. No validated best subhourly combination, no genuine overnight performance claim, no production or brokerage changes, and no background process left running. The remaining decisive evidence is longer actual subhourly/BOATS history plus forward or otherwise untouched observations.