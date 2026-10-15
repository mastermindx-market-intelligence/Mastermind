# V30 — actual BOATS SOXX 2H, 3H and 4H source-input readiness

**Capability delivered:** a pure, tested, reusable **higher-timeframe source completeness and reported volume-support observer**, not an OHLC generator, market signal, an original SOXX cycle strategy test, a second calendar/data source or production price feed. Uses **only** original Tiingo receipt-verified research Bar objects from the incumbent Macro Data OS; imports the accepted V29 source/session filter and the original \`fullsession\` ET/UTC clock.

## 1. How an overnight higher-timeframe source should be evaluated

Blue Ocean ATS runs **Sunday–Thursday, 20:00–04:00 ET** where the NYSE TRF calendar permits it; the existing original owner weekday classifier excludes Friday/Saturday starts. Genuine exchange holidays, halts and extraordinary calendars remain **external unproven source gates**. The 8h overnight source interval (480 possible 1m starts) is partitioned into exactly:

- **2H:** four candidate full 120-minute windows, starting at 20:00, 22:00, 00:00, 02:00 ET.
- **3H:** two candidate full 180-minute windows, starting at 20:00 and 23:00 ET. The **trailing two-hour 02:00–04:00 block is explicitly excluded** rather than silently labeled a completed 3H candle. This is *overnight-local* source support, **not** a completed 3-RTH-hour exit decision.
- **4H:** two candidate full 240-minute windows, starting at 20:00 and 00:00 ET.

A candidate source-input window is counted **complete only if every original 1m source timestamp is present**. Every missing timestamp is an unknown source minute. Even an otherwise complete 2H/3H/4H time window is **not trade-price-supported** if it has zero/unknown reported source volume. This diagnostic checks volume support but **does not compute prices, construct candles, fit MACD/Stoch RSI/RSI, splice across overnight/RTH sessions or claim an executable bid/ask**. Longer 24h indicators need separate true source/date-boundary continuity, official RTH calendar and PIT vintages.

## 2. Actual historical SOXX source results — both immutable original receipts

Original canonical data sources, each fetched exactly once by the original human operator and reverified using \`read_research_view(... purpose='INSPECTION')\` and original \`tiingo_l1_v13.l1_to_bars\`:

- October 5–11 request / 2,148 rows: source SHA256 \`1c2a544683a9c270183b52213bdf1445655b237957003ae2e47f40772fcde885\`; original receipt identity \`7dca959c29ee6735307523c40f6d52aa30412473ebbb757ad40cbbda6eb93a11\`.
- October 12–13 request / 720 rows: source SHA256 \`ea6392763b0ea148084c10bd1e98d42273a2479a7625993d5a87e6cad691486e\`; original receipt identity \`a90016abfd49a712215bdea2d08a8fe81bb8c4f398e803472082d8289534c8df\`.

These two original receipts contain **2,868 distinct source-minute timestamps without overlap**. No future-market source, full-year history, historic executable quote replay or independent prospective outcome was introduced.

| Original overnight night start, ET | Original one-minute rows | Full 2H source windows (of 4) | Full 3H source windows (of 2) | Full 4H source windows (of 2) |
|---|---:|---:|---:|---:|
| Oct 4, Sunday (boundary partial) | 240 | 2 | 0 | 1 |
| Oct 5, Monday | 479 | 3 | 1 | 1 |
| Oct 6, Tuesday | 474 | 3 | 1 | 1 |
| Oct 7, Wednesday | 477 | 1 | 0 | 0 |
| Oct 8, Thursday | 478 | 2 | 0 | 0 |
| Oct 11, Sunday (boundary partial) | 240 | 2 | 0 | 1 |
| Oct 12, Monday (full timestamp night) | 480 | 4 | 2 | 2 |

For the **five near-complete/full core nights Oct 5/6/7/8/12**, the readiness rates are:

| Overnight-local source grid | Time-complete source-input windows | Candidate full windows | Full windows with positive source volume in EVERY constituent minute |
|---|---:|---:|---:|
| **2H** | **13** | 20 | **0** |
| **3H** | **4** | 10 | **0** |
| **4H** | **4** | 10 | **0** |

This is particularly diagnostic for **higher-timeframe oscillator research**: a near-full overnight 1m timestamp lattice can lack most complete aligned 3H/4H source windows. Every currently time-complete 2H/3H/4H overnight block among the five core nights includes at least one vendor minute with **zero reported trade volume**. That does **not** prove the provider's OHLC is wrong, nor does an all-positive window prove executable liquidity at a selected order size. It demonstrates the need for explicit price-construction and actual venue quote/size provenance before calibrating an automated 24h loss-cutting or profit-taking rule. Tiingo documents overnight source \`volume\` as BOATS shares traded (https://www.tiingo.com/documentation/boats), while the source's zero-volume/nonflat OHLC semantics remain unexplained.

**No trade signal or strategy decision is selected from these rates.** No retrospective threshold, no new backtest on the inspected historical year, and no independent SOXX economic outcome was generated.

## 3. Executable implementation and independently verified checks

The bounded source module \`prospective_validation_v26/higher_timeframe_support_v30.py\` exports \`audit_overnight_htf_inputs(bars,night_starts_et)\`. It reuses the accepted **original** v13 minute Bar and local timezone classification through \`v29.audit_volume_support\`, including duplicate-minute and closed-Friday/Saturday rejection, before any time-block accounting. It outputs only fixed source-readiness counts, volume category diagnostics and explicit FALSE truth flags for PIT, historical bid/ask execution, capital deployment, forecast quality and price-row publication. **No new market price bars or OHLC extrema are calculated by the V30 module.**

**14 dedicated synthetic tests PASS**, including exactly complete 2H/3H/4H windows, missing opening minute, missing tail of excluded 3H remainder, all-zero or unknown volume and overlapping unknown/zero inputs, source duplicates, corrected Fri/Sat closures and the November 1, 2026 DST fallback Sunday 20:00 start. On the actual original 2,148 + 720 L1 SOXX records, the same module reproduced **all seven per-night counts and the five-night 13/4/4 full higher-timeframe source availability figures** with no venue call, raw price output or archive mutation.

## 4. Current operational frontier

The first two original user-acquired SOXX historical REST receipt paths are complete, immutable and **DO_NOT_REDO**. For further warmup, a pure original offline planner already prepared the next **disjoint** SOXX \`2026-09-28..2026-10-04\` one-request \`boats-bars 1min OHLCV\` selection, original plan SHA256 \`a38824e577de04ff91771866efa1611385de7c2849b6c08448ef59a03a8c772f\`. It has **not** been sent to Tiingo; any next original producer operation requires real current account/request/writer admission. Follow every genuinely new original receipt with the existing L0→L1→v13→V29→V30 chain and preserve source gap, volume and archival truth.

The original frozen prospective entry window is October 14, 2026–April 13, 2027 ET, with full 52-observed-RTH-hour outcome maturity and separate actual marketability. The Oct 4–12 nights are **pre-window inspected source readiness**, not independence or strategy profit proof. Never infer opportunity-count expansion from repeated time blocks; they overlap underlying time regimes.

**Acceptance:** \`RESEARCH_ONLY_MULTITIMEFRAME_INPUT_READINESS_PROVEN_FOR_SEVEN_ARCHIVED_NIGHTS\`, **not** \`PIT_INDICATOR_VALIDATED\`, \`BOATS_MARKETABILITY_PROVEN\` or \`TRADING_STRATEGY_ACCEPTED\`.
