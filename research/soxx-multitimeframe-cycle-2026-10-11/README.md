# SOXX multi-timeframe pivots, momentum exits and cycle-failure research

## October 11 evening Tiingo source advance (supersedes older unverified-access notes)

Macro Data OS **PR #8698 was merged**, and the actual signed-in Tiingo BOATS add-on is ACTIVE. Two owner-captured historic REST BOATS datasets are available on M2: **AMD 720 one-minute bars** and **AAPL 687 one-minute bars**. The canonical `read_research_view` verified both original raw receipts and their existing L1 projections. The read-only v13 consumer strictly normalized all records: AMD had **one complete 480/480-minute overnight session** (Oct 8 evening–Oct 9 morning), whereas AAPL had **462/480** that same night. Missing AAPL minutes were never forward-filled. These data do **not** constitute historical SOXX observations or complete 24-hour days.

The current native BOATS firehose archive holds an opening event burst, including seven SOXX trade messages and zero SOXX quote messages in the inspected 20 receipts; this is not historical/continuous SOXX quote depth. **Historical Tiingo REST bars cannot retroactively provide order book quotes.** Rights/PIT metadata remain unapproved for reuse beyond bounded retrospective inspection.

The v12/v13 research importer and exact existing Macro L0→L1 reader CLI are under `fullsession_v12/`. **45 distinct unit tests passed** across the original parser, strict v13 adapter, and canonical CLI containment. Actual archive read tests additionally passed on M2 for both AMD and AAPL. See [TIINGO_CANONICAL_READER_REAL_PROOF_2026-10-11.md](TIINGO_CANONICAL_READER_REAL_PROOF_2026-10-11.md) and [SOXX_BOATS_ACQUISITION_CONTRACT_2026-10-11.md](SOXX_BOATS_ACQUISITION_CONTRACT_2026-10-11.md).

**SOXX four-arm backtest remains pending the lawful existing Macro collector's actual SOXX historical bars and separately historical marketable BOATS quotes.** No second producer, vendor authentication, credentials, source permission bypass or trading is enabled by this repository.



**Research status: retrospective / not accepted for live trading.** Last source review 2026-10-11.

This directory preserves the chronological SOXX research commission from 2026-10-09 through 2026-10-11. Reports and tables are included without rewriting successful or failed experiments as hindsight winners. Each report's sample definition controls its own numbers; they **must not** be pooled without checking overlapping entry episodes, transaction costs, exit horizon and OHLC gaps.

## Research chronology

1. **RTH 2H/3H/4H MACD + Stoch RSI** — severe histogram extensions and different momentum thresholds. Tight stops materially weakened seemingly strong rebound prediction. Refer to `reports/SOXX_2H_3H_4H_MACD_StochRSI_Backtest_2026-10-09.md`.
2. **RTH stricter confirmations** — episodes rather than every crossover; data-quality corrections and holdout limitations. See the Refined and RTH Extreme Recovery studies.
3. **Nested 15m/30m/45m/60m pivots** — price-structure confirmation on top of 2H/3H/4H conditions. Sub-hourly public history in the original study spans only a small recent interval, not an independent full year.
4. **Runner/exit research** — 2% full exit versus 3H momentum stretch, rollover, partial runner and long timed holds; higher profits often reflect longer holding and considerable gap risk rather than a well-timed top.
5. **Cycle-failure and structural stop research** — losing the entry thesis vs normal correction, defended higher lows, emergency stops, filled-entry assumptions and gaps. See the October 10 and 11 failure audits.
6. **Independent asset-transfer falsification (additional phase in `cross_asset_v11/`)** — predeclared AMD, AVGO, MU, INTC, NVDA, AMAT, LRCX, KLAC test with frozen SOXX rules. The original 52-hour plus 1.5% stop setup did **not** generalize robustly. Early 1H cycle weakness was often too late to prevent stops or prematurely cut winners.

## Key falsifiers and boundaries

- The evaluation window 2025-10-09–2026-10-08 is repeatedly inspected. Earlier-year comparisons also informed rule selection; neither is a genuinely untouched acceptance holdout.
- The principal 10-trade SOXX 25%-partial + early guard historical sample averaged approximately **+4.18% net/trade**, but the finite guard's apparent improvement came from only three events and did **not** generalize to additional semiconductor names.
- In 53 cross-stock matched observations from 8 new semiconductor names, the finite early guard reduced mean trade return by **0.318 percentage points**, fast weakness by **0.181**, and momentum reset by **0.120** versus matched 52-regular-session-hour holding. Calendar-week block bootstrap intervals include no improvement.
- On those 53 constituent positions with fixed 1.5% initial stop, **48 stopped out** and **26 had stopped by three observed RTH hours**; for **40/55** initial setups, the stop was less than one signal-time hourly ATR.
- A 1-hour ATR stop improved mean gross-notional trade returns but increased loss allowance and left **41 of 50** resolved trades negative. This is not a validated correction.
- Historical mid/last/aggregate OHLC are not executable market quotes. A price-limited buy touched on an OHLC candle cannot be assumed filled; adverse gap fills may exceed the stop. The historical trial included missing session-edge bars.
- Historical figures reflect hypothetical, mostly unlevered one-position/notional comparisons, not personalized trade sizing, a live algorithm, or evidence of future accuracy.

## Complete historical **SOXX** BOATS is not yet acquired for this research

The precise available paths are:
- **Tiingo BOATS** historic venue overnight OHLC: `GET https://api.tiingo.com/boats/{ticker}/prices`, with BOATS entitlement; realtime websocket is **not a historical quote archive**. Source: https://www.tiingo.com/documentation/boats .
- **Alpaca** historical venue BOATS bars, quotes, trades: `https://data.alpaca.markets/v2/stocks/bars?feed=boats` with authenticated API credentials. Alpaca states historical BOATS observations on its Free plan are 15-minute delayed: https://alpaca.markets/learn/how-to-fix-common-trading-api-errors-at-alpaca and https://alpaca.markets/learn/fetch-historical-data .
- Current Terminal implementation candidate: https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/814 ; historical `feed=boats` Quote Hub read, **open/unmerged, not production acceptance**.
- Current Mastermind Tiingo BOATS quote candidate: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1293 ; **open/HOLD**, operator/auth/license gates apply. Its realtime quote adapter is not proof of complete historical data.
- Macro Data OS Tiingo archive candidate: https://github.com/mastermindx-market-intelligence/macro/pull/8698 ; **open**, no authenticated historical BOATS capture proven. Preserve its sole ownership of vendor raw archives; no second collector.

**Do not probe denied credentials through another tool, host, or account.** A lawful authenticated read-only source must already exist or be provided through the incumbent authorized data owner. This research publication neither enables public redistribution nor authorizes trading.

## Research archive and audit contract

- `reports/`: all 11 text studies created over the conversation.
- `tables/`: all 30 associated trade/candidate/exit/falsification CSVs created over the conversation.
- `cross_asset_v11/`: frozen rule source, cross-stock summary, risk feasibility and selected checks.
- `PROVENANCE_AND_GATES.md`: exact data-access requirements, source rights boundaries, and acceptance protocol.
- Raw Yahoo/Tiingo/Alpaca snapshots, credentials and earlier ZIP packages are **not** republished into this public repository. Those remain in the original research artifacts under their own provenance and access controls.

## Completion test (still open)

Acquire truthful 15/30-minute BOATS historical bars with adequate coverage and historical quotes, align 04:00/09:30/16:00/20:00 America/New_York boundaries and half days, preserve indicator-memory equivalence, distinguish information improvement from overnight execution improvement, reconstruct actual fillability, then evaluate **frozen** signal rules on unseen periods. Do not tune these already-inspected SOXX dates again and call the result validated.
