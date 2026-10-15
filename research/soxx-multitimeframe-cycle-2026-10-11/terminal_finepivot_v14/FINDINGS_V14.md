# SOXX 15/30-minute nested pivots and cycle-failure falsification — 2026-10-11

**State:** Exploratory, repeatedly inspected historical year, **NOT a live trading or 24-hour BOATS strategy**. Current research data are retrieved from Mastermind Terminal's existing *public, read-only* `/api/intraday` consumer. Terminal explicitly labels price adjustment, historical point-in-time availability and total session completeness as **not verified**. Original evaluation period: **2025-10-09–2026-10-08 ET**. Models defined and saved in `SPECIFICATION.json` prior to outcome testing. No new parameters were chosen for a purported held-out win.

## Critical new dataset

- **SOXX RTH:** 8,596 15m and 4,298 30m bars, 332 observed sessions from 2025-06-16 through 2026-10-09, sourced from one consistent stored 5m basis plus a smaller live tail.
- **Exactly 4,298/4,298 30m bars reconstruct from pairs of 15m bars** with the same O/H/L/C and volume.
- Three observed early closes: 2025-07-03, 2025-11-28 and 2025-12-24 (14 × 15m / 7 × 30m). No internal RTH missing intervals among the dates SOXX supplied. This does not independently verify the complete NYSE trading-date calendar.
- **Extended 04:00–20:00:** 10,225 SOXX 30m observed bars, uneven daily availability (often fewer than 32); these were audited but **not substituted for the genuine 20:00–04:00 BOATS venue**.
- Additional precommitted stress instruments: **SMH** (8,596 15m), **QQQ** (8,138 15m; 30m missing at start of its first 2025-07-14 *warmup* session, outside study year), **AMD** (8,270 15m). All have coverage of every SOXX-observed trading date during the evaluation year; no source gap in that year was silently treated as an empty session.
- Original 10 SOXX hourly-entry timestamps all mapped to the new source, with a maximum opening-price difference of **0.0335%** versus the older RTH reference.

## Predefined SOXX entry/exit comparison

Entry: higher 3H MACD(8,21,5), Stoch RSI(14), 2× trailing RMS negative-histogram washout, then **first causal confirmed local price pivot**, MACD improvement, RSI(14) rising from ≤45, Stoch RSI K≥D. Exit baseline: emergency 1.5% stop, optional sale of 25% at +2%, maximum 52 observed RTH hours, 5 bps modeled fees each side, conservative stop-first OHLC and next-open signal exits. No actual quote/limit fills are established.

| 3H context / lower pivot | Signals | Timed-exit winners | Timed-exit average net | Finite guard average | Structure-failure average |
|---|---:|---:|---:|---:|---:|
| 1H fast | 10 | 4 | **+3.7041%** | **+4.1793%** | +3.7828% |
| 30m fast | 8 | 1 | **−0.2128%** | +0.1234% | −1.5405% |
| 15m fast | 10 | 3 | **+3.3362%** | +2.1495% | **+3.8916%** |

The 1H reference closely reproduces prior research. **30m fast pivots entered an average 1.1875 observed RTH hours earlier on eight comparable parent episodes, but had much worse performance.** The sooner signal sometimes captured *continuing downside*, not a sustainable cycle low.

The 15m fast structure-failure rule helped four losing SOXX episodes, harmed no previously winning outcome, and increased mean trade return by **+0.5554 percentage points** compared with holding the **same 15m entries**. This attractive small-sample result is not independent validation.

## Falsification on three predeclared comparison instruments

The **same 15m entry, same cycle-failure algorithm, same risk and horizon** was evaluated without changing thresholds or choosing symbols afterward.

| Instrument | 15m entry signals | Same-entry timed mean | Same-entry structure-failure mean |
|---|---:|---:|---:|
| SOXX (design/inspected) | 10 | +3.3362% | +3.8916% |
| SMH | 8 | −0.1783% | −0.0234% |
| QQQ | 7 | +1.7785% | **−0.3098%** |
| AMD | 8 | +6.7489% | **+4.7978%** |

On 23 matched **peer** trades, the finer failure rule reduced average net returns by **1.2604 percentage points**, rescuing four losers but prematurely selling five winners. An exploratory **entry-week block bootstrap 95% interval was −3.111 to +0.0754 percentage points**. Correlated symbols and historical parameter reuse prevent an independent holdout claim.

The old 3H/1H entry remains more defensible as a comparison. The preferred exit has NOT been determined; a simple time exit remains an essential benchmark.

## Pivot-specific 1.5% structural admission: improved feasibility, not results

Hypothesis fixed before the test: admit only a purchase *above the confirmed local pivot* where **stop = pivot − 0.1 × ATR(lower timeframe)** and the resulting risk from the next observed opening is **0.3%–1.5%**. Reject all other opportunities; preserve rejected winners and losers in the opportunity denominator.

| Asset | 3H / 1H admitted | 3H / 15m admitted |
|---|---:|---:|
| SOXX | 1 / 10 | **6 / 10** |
| SMH | 2 / 8 | **7 / 8** |
| QQQ | 2 / 7 | 3 / 7 |
| AMD | 1 / 6 | 3 / 8 |

For SOXX 15m, the six admitted opportunities averaged **+1.0298% with the time exit**, but two rejected opportunities were previous winners. The return averaged across all original ten opportunities with rejections treated as zero was **+0.6179%**, versus +3.3362% for the unfiltered model. A tighter *coherent* initial stop is physically feasible in more cases, but not a demonstrated payoff improvement. No sizing or wider stop is recommended.

## Causal/execution verification

- **84 independent OHLC path replays matched the main engine, zero net-return difference**; no stop-vs-partial high/low ordering ambiguity arose in those 15m cases. This verifies two *bar-path scenarios*, not historical ticks, spreads or actual bid/ask fills.
- **62 truncated-history prefix checks** preserved earlier eligible entry decisions.
- **63 summary-statistic rows** were recomputed from the private derived-outcome ledger and admission records.
- The 15m sample and 30m sample are two resamplings of the **same** Terminal stored-5m producer: they are not independent data sources. Some recent candles originate from a separate *live-tail* read; separate provider adjustment and known-at claims remain unverified.

## BOATS research boundary and plan

Tiingo BOATS source is now ACTIVE/has real owner-captured source receipts, but the inspected M2 archive contains **historical AAPL (687) and AMD (720)** one-minute BOATS bars, **no full-year SOXX historical BOATS receipt**. Seven SOXX opening trade messages with no quote messages from an isolated firehose burst do not establish historical SOXX bid/ask book or venue continuity. Existing Macro Data OS remains the sole source owner. A **pure/offline** request plan via the incumbent `scripts.tiingo_ingest.plan` covered 53 seven-day SOXX tasks for the original 365-day evaluation or 67 tasks with earlier indicator warmup (starting 2025-07-01); **zero** matching SOXX requests were already archived. No vendor/authenticated request was made here.

Before claiming full-session model superiority, require licensed SOXX historical 20:00–04:00 source, verified 04:00–20:00 daytime venue/adjustment compatibility, evidence of data gaps versus no-trade intervals, and historical marketable bid/ask/size conditions or explicit no-fill bounds. The four RTH/overnight crossed indicator/transaction experiments remain pending.

## Publication/ownership

All source snapshots containing actual market OHLCV are **private**, retained in the mini4 scratch workspace, and **not** published to the public GitHub repository. The present GitHub PR preserves code, parameter specification, derived statistics, failure evidence and source SHA digests. Existing owner: [Mastermind research PR #1338](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1338). Macro source owner is [merged PR #8698](https://github.com/mastermindx-market-intelligence/macro/pull/8698). No trade, provider-credential call, collector, production modification, or new writer was started.
