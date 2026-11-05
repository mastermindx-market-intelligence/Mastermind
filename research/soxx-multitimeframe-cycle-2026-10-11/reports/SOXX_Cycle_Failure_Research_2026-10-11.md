# SOXX Cycle-Failure Research: Entry Coherence, Transfer and Volatility

**Research date:** October 11, 2026  
**Primary historical window:** October 9, 2025–October 8, 2026  
**Status:** Exploratory retrospective research only. No verified live trading edge, actual overnight/BOATS data, executed limit fills, or production changes.

## Executive finding

The problem is not simply choosing a better exit. The frozen strategy—dramatic 3H MACD-histogram extension, Stoch RSI washout and confirmed 1H price pivot—behaved differently across instruments. In the eight additional semiconductor names tested without retuning, a 1.5% stop was narrower than one signal-time hourly ATR for **40 of 55** signals. Of **53 resolved** entries under the original stop and holding-period policy, **48 stopped out**, **14 during their first observed hour** and **26 by the third**. A cycle-failure detector requiring a completed 1H candle or three-hour observation window cannot preempt all such losses.

The specific early-failure guard previously favorable on SOXX **did not improve mean returns** in the new eight-symbol basket compared with the same 52-regular-session-hour holding control. Widening stops to the hourly ATR improved average returns mainly through a few larger recoveries; the typical trade remained a loser. This is not a validated strategy for SOXX or its constituents.

## Frozen strategy, comparison and data controls

The original entry rule was held constant: significant negative MACD histogram extension on a 3H chart with recent oversold Stoch RSI, followed by a confirmed 1H local pivot. The main exit comparison used 25% partial profit at +2%, the same five-basis-point modeled transaction cost per side and a maximum 52 observed regular-session trading hours. The compared interventions were the existing finite failed-rebound guard, simple fast 1H momentum weakness, and a momentum-recovery-failure rule. No instrument-specific thresholds were fitted.

The predeclared additional semiconductor basket was **AMD, AVGO, MU, INTC, NVDA, AMAT, LRCX, KLAC**. SOXX and SMH were retained as existing semiconductor references; QQQ, SPY and XLV were controls. The snapshots were 60-minute regular-hours Yahoo Finance OHLCV data with source SHA256 values in the archived manifest. KLAC had a vendor-recorded 10:1 split on June 12, 2026; the historical price series did not show an unadjusted 90% price discontinuity. Some session gaps and incomplete paths remain identified and excluded from resolved comparisons.

### Historical exit interventions on eight additional stocks

All three models were evaluated on **53 matched resolved positions** across **23 entry weeks**. Changes are in percentage points of net return per matched trade versus the 52-hour holding control. The uncertainty intervals use exploratory calendar-week block resampling, **not** a family-wise model-selection correction.

| Frozen intervention | Mean effect | Exploratory week-block interval | Trade effects |
|---|---:|---:|---|
| Existing finite early-rebound-failure guard | **−0.318 pp** | −1.522 to +0.353 pp | 7 helped, 4 harmed |
| Fast momentum weakness | −0.181 pp | −0.849 to +0.333 pp | 9 helped, 3 harmed |
| Momentum recovery reset | −0.120 pp | −0.481 to +0.039 pp | 1 helped, 1 harmed |

The rest were unchanged. All three intervals include zero. Stocks in this basket are highly correlated during common semiconductor shocks, so 53 positions must not be interpreted as 53 independent regime experiments.

### Source-specific entry performance

The **simple 52-hour holding-policy mean** was negative in five of the eight additional semiconductor stocks. This points to problems in *entry admission* as well as exits.

| Stock | Signals (requested year) | Mean net return with 52-hour control | Mean with finite guard |
|---|---:|---:|---:|
| AMD | 6 | −1.453% | −1.453% |
| AVGO | 4 | −1.524% | −1.333% |
| MU | 8 | −1.053% | −0.950% |
| INTC | 6 | +4.754% | +1.889% |
| NVDA | 6 | +0.203% | +0.391% |
| AMAT | 9 | −1.401% | −1.401% |
| LRCX | 6 | +3.197% | +1.850% |
| KLAC | 10 | −0.391% | +0.197% |

These signal counts are opportunities; the reported averages are based on resolved trade paths where available. The strategy was originally developed on the inspected SOXX year; cross-stock application is a diagnostic, not a pristine independent acceptance test.

## Timing: why confirmed exits cannot always save early failures

Among 48 stopped trades across the eight new constituents, stop timing by **observed** market hours was:

| Elapsed regular-session time including stop candle | Stopped trades |
|---|---:|
| In the first source hour | 14 |
| More than 1 hour, at most 3 hours | 12 |
| More than 3 hours, at most 6.5 hours | 9 |
| More than 6.5 hours, at most 13 hours | 10 |
| After 13 hours | 3 |

Hourly OHLC cannot identify the exact minute of stop activation. Fourteen trades were stopped inside the entry-hour candle, before a newly completed hourly confirmation could have acted. Twenty-six stopped by three observed trading hours, leaving a three-hour-grace indicator exit unable to precede those outcomes. A separate, precommitted emergency risk stop remains necessary even if a later 15/30-minute thesis-invalidation detector is developed.

## Strict pivot-risk admission and hypothetical buy limits

To keep structural invalidation within a 1.5% price stop, a potential maximum purchase price was calculated **from the completed signal** using the original pivot less 0.1 ATR. The price was examined over the following one or two observed hourly bars. The experiment explicitly **does not assume passive limit orders filled**; a touched limit without observed bid/ask, queue and order records is only a possible price contact.

| Two-bar admission result | SOXX (10 opportunities) | Eight new semiconductors (55 opportunities) |
|---|---:|---:|
| Eligible at recorded opening price | 2 | 13 |
| Clean limit-price touch; fill **not verified** | 1 | 9 |
| No clean qualifying entry | 7 | 33 |

Two initially successful SOXX holding-control trades were among the opportunities left without a clean qualifying entry. Limits can preserve the **risk contract** while sacrificing participation; an apparent risk-per-share improvement is not evidence of better opportunity capture. Orders that trade down through the defended pivot were excluded as invalid, rather than treated as profitable limit fills.

## Volatility-normalized stop comparison

A fixed 1.5% initial stop was narrower than one hourly ATR in 40 of 55 semiconductor entry signals. Its median ratio to signal-time hourly ATR was **0.795 ATR**, compared with about **1.31 ATR** for the SOXX candidates. This substantially limits naive transfer of the same percent stop across stocks.

A *distinct hypothetical pre-trade stop policy* of 1× hourly ATR, capped at 3% of purchase price, changed the eight-stock results as follows under the same 52-hour time-exit control:

| Measure | Fixed 1.5% | 1× ATR, cap 3% |
|---|---:|---:|
| Resolved trades | 53 | 50 |
| Winning trades | 5 | 9 |
| Mean net return | +0.196% | +1.274% |
| Median net return | **−1.599%** | **−1.513%** |
| Mean initial risk distance | 1.500% | 1.858% |
| Average net return/initial-risk ratio | +0.130 R | +0.662 R |

Three opportunities were excluded by the ATR-policy cap. On matched events, 16 outcomes improved and 28 worsened. The matched mean gain was about **+0.995 pp**, with exploratory week-cluster interval **−0.259 to +2.800 pp**. The 1.5× ATR alternative similarly had uncertainty crossing zero and typically larger losing trades.

**A wider stop is not a fast-failure detector.** These hypothetical stop policies were defined *before* the trade; they do not authorize widening an existing live stop, using leverage or calculating allocations from this analysis.

## Required next validation

The current evidence cannot establish a profitable cycle-failure classifier. The critical next dataset is authentic, licensed SOXX intraday history over the full requested period, ideally extending into different market regimes, with:

- Actual 15- and 30-minute OHLCV and true 8 p.m.–4 a.m. BOATS bars, distinguishing after-hours, premarket and regular session;
- Time-stamped executable quotes, bid/ask sizes, observed trades, venue and exchange conditions, and corporate-action adjustments;
- An explicit split between **overnight information value** and **overnight execution value**, preserving equivalent indicator memory and calendar/holding clocks;
- Accounting for unfilled orders, gap-through-pivot openings and trades that breach their stop before any completed lower-timeframe failure signal could arrive;
- An untouched future evaluation set and correlated-week/episode statistical treatment.

The research specification for the candidate is **large-timeframe opportunity, close-enough defended entry, independent emergency risk, state-specific failure tests**, then trailing only confirmed continuation structures. Avoid promoting rules until a real-data comparison establishes that they save more losses than winning continuation they sacrifice.

## Reproducibility and ownership

Original source and model scripts, CSV ledgers, source metadata, error boundaries and a SHA256 manifest are archived on the authorized mini4 workstation:

`/Users/mini4/.local/share/mastermind-review-artifacts/SOXX_CYCLE_TRANSFER_20261011_v11.zip`

**ZIP SHA256:** `0ac3ad2da5d02239120fab4985d5812910471c50dcf9aedc2f780b1d840f40eb`  
**Verified archive size:** 1,242,342 bytes; 65 manifested files.  
**Protected Mastermind source-law pin:** `326c8469a21d7f50fc9ecb1848196bf1c6e66685`.

Validation verified 13 source hashes, 78 asset-strategy rows, 264 matched exit records, 182 hypothetical limit-contact rows, 584 risk sensitivity rows, stop-timing bounds, initial risk invariants and the relevant SOXX reference outputs. The archive zip was read back and verified; there are no unresolved research write effects.

**Research remains incomplete, with an external data dependency. No broker orders, live production changes or background monitoring were initiated.**