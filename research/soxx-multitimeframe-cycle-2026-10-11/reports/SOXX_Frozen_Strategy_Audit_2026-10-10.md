# SOXX frozen-strategy audit — execution, coverage and transfer

**Research date:** October 10, 2026  
**Requested evaluation window:** October 9, 2025–October 8, 2026  
**Earlier comparison:** December 16, 2024–October 8, 2025  
**Status:** Retrospective research; no accepted trading edge, live trades, production changes or overnight feed.

## Executive finding

The existing quarter-sale/early-guard/slow-rollover strategy still reproduces its ten-trade requested-year result: **70% winning trades, +4.1847% average net return and +48.1900% compounded hypothetical return**. That is not a fresh validation. More demanding checks reveal three vulnerabilities: sensitivity to the actual entry, drawdown hidden between hourly closes, and incomplete coverage in one earlier-period holding path.

The independent intrabar replay raises the quarter-sale strategy's measured maximum drawdown from **4.6640% to 5.5067%**, without changing any realized return. A one-source-bar entry delay reduces the win rate from **70% to 40%**. A purchase price 0.25% worse than the recorded open reduces average return from **4.1847% to 2.6386%** under the low-first intrabar scenario.

The unchanged strategy earns positive requested-year averages on SMH, but all eight SMH entry dates overlap SOXX. QQQ shows little benefit. These are related-market transfer diagnostics, not additional independent trials or new recommendations to trade those instruments.

**Do not replace the frozen definitions with whichever perturbation looks best.** This round deliberately tests fragility instead of adding another layer of retrospective optimization.

## 1. Frozen definitions and comparison design

The baseline entry is unchanged: a dramatic 3H downside MACD histogram extension, with recent oversold Stochastic RSI, followed by a confirmed 1H price pivot with improving momentum. The larger setup uses MACD 8/21/5 and Stochastic RSI 14/14/3/3. The principal lower profile uses MACD 5/13/4, Stochastic RSI 7/7/3/3, and conventional RSI(14). The extension is at least twice the RMS magnitude of the preceding 80 histogram observations; the current observation is excluded from its own scale. One qualifying setup is used per episode.

The frozen exit policies are:

| Code | Definition |
|---|---|
| `fixed2` | Original 1.5% stop; sell the entire position at +2%. |
| `slow_p0.25` | Sell 25% at +2%; manage the remainder with the existing 3H joint-momentum rollover. |
| `guard_p0.25` | Same 25% sale and slow exit, with the expiring early-rebound-failure guard. |
| `guard_p0.5` | Same guard and slow exit, but sell 50% at +2%. |
| `guard_timer52` | Sell 25% at +2%, retain the early guard, and replace the slow rollover with 52 observed RTH hours followed by next-open execution. |
| `plain_timer52` | Same quarter sale and timer, without the early guard. |

The early guard operates only after 3 and through 6.5 **observed RTH trading hours** from entry. It requires a prior +2% high, a completed close below +1% from entry, and RSI(14) below 50 or close below the 1H EMA10. It exits remaining shares at the next observed open. It expires thereafter; it is not a permanent trailing-profit rule.

The slow exit uses a 3H panel with MACD 12/26/9, ordinary RSI(14), and Stochastic RSI 14/14/3/3. A completed observation with RSI at least 65 and K at least 80 arms the watch. A subsequent bearish K/D cross with a falling MACD histogram triggers next-open execution. The stop is not widened. Baseline maximum holding time is 65 observed regular-session hours.

Modeled transaction cost is five basis points per side. Prices and returns are not total returns: cash interest, taxes and dividend cash flows are not modeled. The hypothetical compounding convention invests full unlevered notional in each non-overlapping position and holds partial-sale proceeds in cash. It is not risk-sized account performance or personalized allocation advice.

The SOXX audit contains six policies across seven predeclared diagnostics (42 policy applications). SMH and QQQ receive the six unchanged policies. Separate adverse-fill and independent-replay tests are not additional independent market observations.

## 2. Coverage correction: the earlier-period portfolio is not fully observed

The old path audit detected missing bars between neighboring observations on the same date. It did not detect a missing final observation immediately before the next session. The new audit checks the session opening, internal continuity, final close and wholly missing scheduled sessions against the vendor's `tradingPeriods` metadata.

| Source, including warmup | Accepted bars | Scheduled sessions | Missing intervals | Missing RTH hours |
|---|---:|---:|---:|---:|
| SOXX | 3,473 | 501 | 19 | 15.0 |
| SMH | 3,473 | 500 | 12 | 8.5 |
| QQQ | 3,424 | 500 | 38 | 56.0 |

SOXX contains eleven internal gaps and eight missing 30-minute session tails. The tail dates are November 29 and December 24, 2024; July 3, November 13, November 28, December 2 and December 24, 2025; and January 7, 2026. These counts span warmup and evaluation history, not just the requested year.

On December 24, 2024, the accepted series ends at 12:30 p.m. ET even though that day's scheduled close was 1:00 p.m. ET. The early-close time is also documented in NYSE Group's official 2024–2026 calendar announcement [1]. The missing final half-hour intersects the position opened December 20, 2024.

All ten main requested-year positions have observed paths through their actual exits under these frozen policies. **But one of the five earlier positions is unresolved for the runner exits.** Its later numerical result must not be treated as a verified execution. The four known earlier quarter-guard outcomes average +1.7099%, with two winners, but there is no complete earlier-period cumulative return or drawdown. Removing the best of those four leaves +0.5840%; that conditional statistic does not repair the missing fifth outcome.

The earlier fixed-2% policy closed before the missing interval, so all five of its results remain observed. Missing observations were not imputed. A strategy can have an observed holding path while earlier input gaps still affect indicator values. Execution-path completeness is not proof of an entirely clean indicator feed or chart-platform parity.

The schedule itself is primarily vendor metadata. Selected early closes were independently checked, not every historical session. Bid/ask, auction prints, tick sequencing and overnight prices remain unverified.

## 3. Entry delay: profitability can persist while accuracy collapses

The original event candidates were held fixed, then purchases were delayed by one or two recorded source bars. Stops, partial targets and the early guard are referenced to the actual delayed entry price and time.

| Entry rule | Quarter-guard mean | Quarter-guard wins | Fixed-2% mean | Fixed-2% wins |
|---|---:|---:|---:|---:|
| Original next-open entry | +4.1847% | 70% | +1.1835% | 80% |
| One additional source bar | +3.7608% | 40% | +0.1274% | 50% |
| Two additional source bars | +3.4598% | 40% | +0.0905% | 50% |

Each row contains ten requested-year entries. A source bar is normally an hour but can be the shortened final bar, and delaying across the close can move a fill into the next session. This is a coarse entry-timing perturbation, **not** evidence about a seconds-level processing delay.

The large winners keep the runner's arithmetic average positive while several small protected outcomes disappear. A positive mean therefore should not be described as stable 70–80% entry accuracy. The half-sale guard also falls from 80% wins to 50% with a one-bar delay.

## 4. Adverse entry price is different from subtracting an extra fee

The separate price experiment buys at the recorded opening price multiplied by 1 plus 0, 5, 10 or 25 basis points. The original 1.5% stop is then measured below that actual assumed purchase price, and profit milestones are measured from it. The observed candle path stays unchanged; baseline fees remain five basis points per side.

| Worse purchase price | Quarter-guard mean | Wins | Intrabar-scenario drawdown |
|---|---:|---:|---:|
| None | +4.1847% | 70% | 5.5067% |
| 0.05% | +4.1722% | 70% | 5.4457% |
| 0.10% | +4.1439% | 70% | 5.4573% |
| 0.25% | +2.6386% | 50% | 7.0348% |

The table uses open→low→high→close within each candle. The two plausible OHLC orders agree at baseline and at 5 and 10 basis points in the tested cases. At 25 basis points, the May 19, 2026 entry becomes order-sensitive: its initial candle can touch the adjusted stop as well as the partial-profit level. The quarter-guard mean is approximately +2.6386% under low-first or +2.7260% under high-first ordering. Neither sequence is claimed as the real sequence.

The May 19 quarter-guard trade changes from +12.2550% at the original entry to −1.5993% under the adverse-fill/low-first scenario. The November 5 trade changes from +0.1321% to −1.5993%. This is a threshold effect, not simply 0.25% subtracted from every finished trade.

Small price changes need not produce monotonic observed results because they move stop and target levels and can change which event occurs first. Favorable changes at five basis points are not evidence that paying more helps. No historical spread or market-order execution guarantee is implied. Testing a price-limited admission policy would additionally require handling unfilled orders; this study does not assume every limit is filled.

## 5. Independent intrabar replay increases measured risk

A second implementation interpolates threshold crossings along open→high→low→close and open→low→high→close. It processes opening gaps, executable partial limits, stops and next-open market decisions with explicit position/cash accounting. It records equity at the extrema and threshold events instead of only at closes and fills.

All 180 baseline trade-path replays matched the incumbent engine's returns exactly, with no exit-time disagreement. Returns were not revised. The marked equity path was.

| Frozen policy | Previous closes/fills drawdown | OHLC-route drawdown |
|---|---:|---:|
| Sell everything at +2% | 2.5058% | 3.1305% |
| Quarter sale + slow rollover | 6.5962% | 8.4121% |
| Quarter sale + early guard + rollover | 4.6640% | 5.5067% |
| Half sale + early guard + rollover | 3.2687% | 4.0678% |

Both tested orders produce the same baseline figures in this cohort. These are still hypothetical paths consistent with OHLC, not tick reconstruction or a bound on unobserved overnight drawdown. TradingView's own strategy documentation explicitly explains similar dependence on inferred intrabar movement when lower-level history is absent [2]. Agreement between engines tests implementation consistency; it does not validate the underlying market data.

## 6. Other instruments: transfer is limited and highly dependent

SMH and QQQ were declared as transfer controls before fetching their public hourly histories. The entry and exit parameters, fractional stop and profit milestones were copied unchanged. The new source snapshots include October 9, 2026, but analysis ends October 8 to preserve the original window.

| Instrument | Requested-year trades | Quarter-guard mean | Wins | Mean without early guard |
|---|---:|---:|---:|---:|
| SOXX | 10 | +4.1847% | 70.0% | +3.5523% |
| SMH | 8 | +3.1275% | 50.0% | +2.9342% |
| QQQ | 7 | +0.2660% | 28.6% | +0.2660% |

SMH preserves positive recent-period payoff but does not supply an independent eight-trade validation: **all eight SMH entry dates overlap SOXX entry dates**. Correlation of matched hourly open-to-close log returns is 0.9841 across 1,729 bars. QQQ correlation is 0.8478 across 1,682 matching bars; four of seven QQQ entry dates overlap SOXX.

The early guard adds approximately +0.1933 percentage points per SMH trade and changes no QQQ outcomes. QQQ's source has materially more gaps; exact intratrade coverage does not make the upstream indicators gap-free. The earlier SMH and QQQ runner samples also contain unresolved holding paths, so no complete earlier portfolio return is asserted.

These tests use fixed percentage risk, not volatility-matched risk across instruments. Poor QQQ transfer neither disproves a SOXX-specific hypothesis nor supports claiming a universal one. The instruments and dates remain economically related, and the shared year has already been inspected.

## 7. Stop width and candle alignment

At the original SOXX entries, a 1.25% stop produces a +2.9089% quarter-guard mean and 60% wins. The unchanged 1.5% stop gives +4.1847% and 70%; widening to 1.75% gives +4.1319% and 70%. This is sensitivity evidence, not a new instruction to widen risk or a calibrated optimal stop.

Moving only the 3H entry aggregation anchor by 60 or 120 minutes leaves nine entries instead of ten. Both shifted variants average +4.5905% with 66.7% wins. Their higher mean is not a paired improvement: the entry sample changed. The standard exit-panel anchors were retained, and shortened session-edge candles were not discarded.

The zero-offset rebuild matched all 1,490 original 3H bars. Twelve truncated-history checks reproduced 8,316 completed aggregate bars, showing the tested aggregation does not borrow later observations for already completed candles. That is not full equivalence with an external charting platform's indicator initialization.

## 8. Decision and exact frontier

Keep the frozen quarter- and half-sale guarded rules as **research candidates**, and retain the guarded 52-hour timer as a non-indicator comparator. The timer's requested-year +4.3359% mean remains competitive with the momentum exit's +4.1847%; both have the same 70% wins and 5.5067% OHLC-route drawdown. This does not establish an ability to identify the precise top.

The critical next evidence is not another historical threshold search. It is longer authentic subhourly/BOATS data, repair or explicit resolution of the missing session edges, point-in-time signals and executable prices, and observations not used to design the strategy. A follow-on must preserve the entry/exit definitions, represent unfilled price-limited orders honestly, and compare matched trading horizons. No arbitrary entry-drift limit is promoted from these few sensitivity cases.

This round completes the frozen-rule execution, coverage and transfer audit. It does not complete proof of profitability or a 24-hour trading strategy. No unattended work, order, scheduled job or production deployment was created.

## Evidence and reproducibility

New local verification: **25 unit tests passed**. Remote evidence includes **16 prior-summary metric reproductions**, **180 independent trade-path replays**, **1,490 zero-anchor bar matches**, and **8,316 completed-bar prefix matches across 12 truncations**. These are software checks, not independent trades.

The supplied CSVs use percentages, including negative `mdd` values. `entry_bps` is adverse purchase-price change, not commission. `prior` means the earlier comparison; `year` means the requested window. Null portfolio statistics mean at least one candidate is unresolved, not zero return. Peer `n` counts candidates and `known` counts resolved outcomes; timing and fill `n` count evaluated resolved trades in the selected current-year tables. The fill table is the conservative low-first scenario. The drawdown table reports the independent intrabar baseline.

Full raw snapshots, complete summaries, ledgers and source code are retained in the verified remote archive:

`/Users/mini4/.local/share/mastermind-review-artifacts/SOXX_FROZEN_AUDIT_20261010_v8.zip`

Archive SHA-256: `52aeef00cb0ec872bb5dbf9f6855489170c717461ae93ee5c886e9de5deae956`. The conversation ZIP includes selected results, exact computation code and tests, but does not include the large raw market snapshots. The selected JSON was transferred and verified against its remote canonical SHA-256:

`537532e27431715b2a36b887774e401592dfebc6417d4014cc5a42d0dfa2f81c`

Raw snapshot SHA-256 identities:
- SOXX: `ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720`
- SMH: `d944772022e2d5a55afbdfab286b010e5a3eaa8c0b23e706c530f0bf341609a9`
- QQQ: `14b123c80e0ed29dfd5a8091871f970f1e1f11d68d34a5d0a155968d3c051dab`

## Public methodological references

[1] NYSE Group / Intercontinental Exchange, *NYSE Group Announces 2024, 2025 and 2026 Holiday and Early Closings Calendar*, December 2023. Official calendar includes December 24, 2024, 1:00 p.m. ET equity-market close. https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx

[2] TradingView, Pine Script documentation, *Strategies — Broker emulator; Adjusting historical bar detail*. Documentation consulted October 10, 2026. https://www.tradingview.com/pine-script-docs/concepts/strategies/

These references explain schedule and simulation constraints; they do not independently substantiate this strategy's measured returns.