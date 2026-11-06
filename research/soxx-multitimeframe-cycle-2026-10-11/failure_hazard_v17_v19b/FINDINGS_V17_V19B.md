# SOXX 3H Reversal Cycle Failure: 5-Minute Hazard Falsification (v17–v19b)

**Research record, 2026-10-11/12. Not production-accepted, not investment advice, no quote-verified fills.** Economic results are hypothetical, on a market year examined repeatedly during model design.

## Design, frozen before outcome checks

An eligible opportunity is the **first completed 3-hour MACD(8,21,5) negative-but-improving histogram plus rising Stoch RSI K≥D** following a negative histogram at least twice the previous 80-bar RMS magnitude and a K≤20 washout. Buy at the next observed **15-minute regular-session open**. Original 1.5% price stop remains permanently active; 25% of original exposure is notionally sold at +2%; default remaining exposure is closed after 52 **observed regular-session** trading hours, decision at a completed bar and sale on the next observed five-minute open, with **5 bp per side** modeled costs. No position sizing, leverage, real bid/ask fills or authentic 20:00–04:00 BOATS candles are asserted.

Three studies share this unmodified entry:

- **v17**, frozen cycle/early-guard exit comparison, 34 originally inspected SOXX/SMH/QQQ/AMD entries.
- **v18**, real Terminal 5m OHLC audit and same-34-entry 5m replay.
- **v19**, preregistered exact 3-hour ignition check on seven additional semiconductor names and two control ETFs; **v19b** adds KLAC with exact path-based treatment of missing 5m records.

## v17: existing failure detectors are economically weak

On the **same 34** RTH parent-turn entries (11 SOXX, 8 SMH, 7 QQQ, 8 AMD), compared to an unaltered 52-RTH-hour control:

| Additional exit | Average paired change in net trade return | Previous winners harmed | Losing trades helped |
|---|---:|---:|---:|
| finite early guard | **−1.956 percentage points** | 9 | 3 |
| fast 15m weakness | **−3.666 pp** | 12 | 8 |
| structure-confirmed cycle failure | −0.624 pp | 3 | 6 |
| slow 3H momentum rollover | −1.530 pp | 9 | 0 |

These findings reject any simple claim that “exit early on weakness” accurately distinguishes cycle invalidation from healthy pullbacks. Calendar-week block-bootstrap intervals for the aggressive finite guard and fast weakness were entirely below zero in this exploratory cohort.

## v18: genuine 5m bar resolution and source diagnostics

Terminal's existing read-only intraday API supplied **20,000 5m candles each for SOXX, SMH, QQQ, AMD**, spanning roughly Oct 1, 2025 to Oct 9, 2026. The first partial Oct 1 is outside the evaluated year. Each source was SHA pinned privately. Across overlap, **6,666 fifteen-minute source candles per asset reconstructed exactly on OHLC price** from three 5-minute children. **286 volume-only differences** on SOXX, SMH, AMD (285 on QQQ), confined to Sep 17–Oct 1, 2026, had maximum relative discrepancy below **0.005%**. Volume is not accepted as perfectly matching. Five-minute fill-route replays matched all 34 earlier-parent entries under both ordinary 52h time and structure-failure policies; zero result discrepancies in these observed cases. This is still OHLC route assumption, not historical tick order or bid/ask.

Among 34 original positions at their first 3-RTH-hour moment, 26 remained open and 8 had already closed under the 1.5% emergency stop. **Thirteen eventual winners and thirteen eventual non-winners were still open**. All thirteen eventual winners were above entry after three hours, while five of the non-winners were also above entry. Six hours later, almost all remaining open positions were winners. These are hindsight-labeled diagnostics: they do not provide a future predictor.

## v19: one predeclared failure-to-ignite rule

**Once, at the completed five-minute bar ending three observed RTH hours after entry**, if the position remains open and that candle closes **below the original entry price**, initiate a sale of the *remaining* exposure at the next observed five-minute opening. The original stop takes precedence, remains unchanged, and can exit the trade before the check. The rest of the rules are identical to the 52h baseline.

| Cohort | Trades with resolved counterfactual paths | 3h stops occurred too early to check | Original losers helped | Original winners harmed | Mean incremental return |
|---|---:|---:|---:|---:|---:|
| Previously examined SOXX/SMH/QQQ/AMD | 34 | 8 | 6 | 0 | **+0.209 pp/trade** |
| **Six additional semiconductor names with qualified data** (NVDA, MU, INTC, AMAT, LRCX, KLAC) | **47** | **27** | **7** | **1** | **−0.129 pp/trade** |
| XLV/XLE sector controls | 10 | 0 | 2 | 2 | −0.243 pp/trade |
| **Combined observed 12 instruments** | **91** | **35** | **15** | **3** | **−0.015 pp/trade** |

AVGO's full-year 15m warmup source was unavailable after bounded read timeouts, so it is **not counted as a winner, loser, or cash**. KLAC has **seven missing 5m source intervals** across 2025 Oct/Dec; **none intersects the exact entry-to-either-exit path of its ten qualifying trades**, confirmed using 15m expected timestamps. Missing intervals were never filled; a trade crossing one would be **UNKNOWN**, excluded from paired return averages but retained as an original opportunity.

Additional-semiconductor paired, calendar-week block-bootstrap 95% interval for mean v19 incremental return: **[−0.655,+0.250] pp** (47 resolved observations, 23 entry weeks). All-in 91-trade interval: **[−0.288,+0.231] pp** (27 weeks). Related semiconductor/equity symbols on common shocks are *not independent market eras*. These intervals are exploratory, not selection-adjusted or a pristine out-of-sample test.

The 47 additional-semiconductor trades recorded seven losing trades helped, **but one winner's large continuation was cut**, surrendering **11.64 percentage points** of that trade's return. Total loss avoided among helped additional-stock losers was **5.92 points**. Leave-LRCX-out raises the estimated effect to **+0.137 pp/trade** across 41; preserving LRCX changes it to **−0.129 pp/trade**. This fragility invalidates promoting the rule on the optimistic subset. The **35/91** positions already stopped before the check are fundamentally unreachable by that delayed condition.

## Key decisions / validation

- **Do not install, backtest-optimize or auto-trade** the 3h failure-to-ignite condition based on the original favorable SOXX result.
- Structural premise invalidation is not equivalent to a fast oscillator rollover or a temporary price move below purchase price.
- Source code includes **six synthetic first-principles contract tests** (stop precedence, 3h timing, next-open execution, one-shot behavior and strictly monotonic clock), which passed. All nine M1→mini4 source transfers had raw SHA matched to the original read-only public Terminal receipts; aggregate v14/18 source/independent route proofs were reused.
- No 2025–26 SOXX BOATS historical 20:00–04:00 source or historical marketable quote sequence has been qualified. Existing Macro Data OS owns authentic Tiingo vendor ingestion; **do not create a second collector or retry earlier denied authenticated API/credential effects**.
- The correct next experiment quantifies the **oracle upper bound** at the 3h check (how much economically *can* be saved after stops already happened) and evaluates whether any *causally available* source characteristics separate that potential from healthy corrections. Keep per-original-parent-episode opportunity denominator and a week-block uncertainty measure.

Underlying 5m/15m/30m actual provider OHLC, source raw archives and private execution ledgers remain on mini4 at `/private/tmp/soxx_terminal_finepivot_20261011_v14`. The GitHub research PR publishes only scripts, source SHA manifests, derived returns and aggregate diagnostics. Provenance labels on Terminal explicitly say price adjustment, P-I-T availability and historical executable quotes are not verified.
