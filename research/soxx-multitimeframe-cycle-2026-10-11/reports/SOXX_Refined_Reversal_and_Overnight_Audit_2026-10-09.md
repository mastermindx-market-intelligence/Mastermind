# SOXX — selective reversal assessment and overnight-data audit

**Date:** October 9, 2026  
**Requested evaluation:** October 9, 2025–October 8, 2026  
**Earlier calibration:** December 16, 2024–October 8, 2025  
**Status:** Additional regular-session research completed. Genuine 24-hour backtest **not completed**. No validated best strategy. No trades placed.

## Decision

The earlier best-combination language was too strong. A high three-session rebound hit rate is not the same as an accurately timed, executable reversal. The revised experiment limits each strategy to one first rare-extension setup per same-sign MACD histogram episode, replaces repeated crossover entries with a bounded confirmation sequence, prevents overlapping positions, and examines protective exits and sample adequacy.

The completed revised run evaluated **1,296 parameter/direction/filter/exit configurations**. None passed its predeclared numerical research screen. This is not a proof that no useful strategy exists: the most selective combinations produced too few observations to evaluate, and genuine overnight data remain missing.

A second experiment isolates preconditions rather than accumulating them. Its implementation is locally unit-tested, but it was **not run against market data**: the research host stopped responding while its source file was being transferred. Those prospective experiments have no reported returns.

## 1. Overnight information is materially important here

Using 251 observed SOXX trading sessions, the recorded regular-session endpoints decompose as follows:

| Component | Compounded price return |
|---|---:|
| Previous regular-session close to next regular-session open | +97.476% |
| Same-day regular-session open to close | -2.178% |
| Combined | +93.176% |

Average absolute close-to-open movement was **1.618% per session**. The components compound multiplicatively, not additively. This starts at the close preceding the first evaluated session, whereas the original report's approximately +93.47% benchmark started at the first evaluated opening price. Neither calculation includes dividends or trading costs.

**Crucial qualification:** close-to-open combines after-hours, the true overnight session, and premarket. It does not establish that +97.476% occurred specifically between 20:00 and 04:00 ET, and it does not recover the tradable path between the endpoints. Nevertheless, a day-session-only indicator cannot observe those intervening developments.

## 2. The attempted extended feed was not genuine overnight data

The actual Yahoo hourly request used `includePrePost=true`. Its requested-year coverage audit returned:

| Session | Priced observations | Zero or missing reported volume |
|---|---:|---:|
| Premarket | 1,494 | 1,494 |
| Postmarket | 908 | 907 |
| True overnight, 20:00–04:00 ET | **0** | Not applicable |

Zero reported volume is a limitation of the returned data, **not evidence that no actual trades occurred**. These observations cannot substantiate volume-based liquidity filters or executable overnight fills. No prices, volumes, or overnight candles were fabricated or forward-filled to make the coverage look complete.

Alpaca's official documentation separates the 20:00–04:00 overnight session from pre/post-market and specifies `feed=boats` for historical overnight bars, quotes, and trades. The derived `overnight` feed is not the appropriate historical substitute. Tiingo documents a separate `/boats/<ticker>/prices` historical endpoint and a BOATS entitlement. Neither documentation nor the existence of integration code proves that this account has the required historical SOXX coverage. Full-year start-date availability still needs verification. [S1–S4]

The existing Mastermind Tiingo/BOATS integration draft was inspected; it records no successful authenticated BOATS history or live handshake. This study did not retry its previously blocked authentication operation or search for/export account secrets. No usable alternative overnight connection was established in this session.

## 3. What changed in the completed experiment

The baseline is **not every crossover**. It first arms a rare setup: histogram at least 2 times its own preceding 80-bar RMS in the correct direction, with Stoch RSI recently reaching 20/80. A same-sign histogram episode can generate at most one first setup. The candidate then has a bounded opportunity to confirm; later crossovers do not indefinitely renew a failed setup.

| Research condition | Exact tested implementation |
|---|---|
| Dramatic MACD extension | Negative/positive histogram magnitude >= 2 times prior 80-bar RMS; current histogram excluded from scale |
| Stoch RSI turn | K improves and is on the favorable side of D; histogram begins improving |
| Price dislocation | At setup: price at least 1 ATR from EMA20 in reversal direction, with MACD line on the corresponding side of zero |
| Persistent oversold/overbought | At setup: K in the relevant 20/80 zone on at least 2 of the last 3 bars |
| Momentum fade | Two contracting histogram bars and at least 20% retreat from episode histogram peak |
| Actual price reclaim | Completed 1H close beyond prior two highs/lows, favorable higher low/lower high, favorable candle body |
| Daily regime | Previous completed daily close versus EMA200 and five-day EMA50 slope |
| Other-timeframe confirmation | Last available completed peer-timeframe MACD histogram improving; no future peer candle |
| Divergence | Setup compared with a previously confirmed 2-left/2-right price pivot, using only information already available |
| No chasing | Entry no more than one setup-time ATR from the known episode extreme |

The cumulative sequence was rare turn -> dislocation -> persistence -> fade -> price reclaim. Trend, other-timeframe, and divergence variants were branches from that sequence; the full stack adds trend, peer confirmation, and anti-chasing.

This implementation checks some conditions at the initial arming point. A different state machine that first arms on extension and waits for **later** divergence/dislocation is a different hypothesis, not something these results rule out. Divergence's zero-trade result is not evidence that divergence is universally useless.

## 4. Completed results: stricter does not automatically mean better

Each row below is a fixed reference profile, **not a newly selected winner**. All use Stoch RSI 14/14/3/3. MACD profiles are 2H 12/26/9, 3H 8/21/5, and 4H 5/13/4. Stops are 1.5%, targets 2%, with 5 basis points per side, at most one position, and a maximum holding period of 19.5 actual regular-session hours.

| Profile | Rare extension + turn: trades | Win rate | Mean net/trade | Through dislocation + persistence + fade + price reclaim: trades | Win rate | Mean net/trade |
|---|---:|---:|---:|---:|---:|---:|
| 2H 12/26/9 | 7 | 57.14% | +0.3676% | 1 | 100% | +1.8990% |
| 3H 8/21/5 | 11 | 54.55% | +0.2549% | 1 | 100% | +1.8990% |
| 4H 5/13/4 | 10 | 30.00% | -0.9860% | 2 | 50% | +0.1499% |

The two one-trade 100% rows are **not** reliable strategies. Even assuming independent trials and ignoring selection, one win out of one has a descriptive 95% Wilson interval of roughly **20.7%–100%**. At one win out of two, it is approximately **9.5%–90.5%**. These intervals themselves do not correct for parameter search, regime dependence, or overlapping economic episodes across configurations.

The 4H fully price-confirmed reference's mean +0.1499% becomes **-0.0504%** when assumed costs increase from 5 to 15 basis points per side. That is not a robust edge.

The results are not a direct rerun of the old 7/10-trade comparison. Episode de-duplication, Stoch settings, entry rules, actual market-hours holding clock, conservative profit-gap treatment, and exact two-sided costs changed.

### Sample collapse across the whole revised grid

Each stage contains 144 timeframe/parameter/direction/exit variants:

| Filter stage | Median evaluation trades per variant | Maximum evaluation trades |
|---|---:|---:|
| Rare extension + turn | 5 | 14 |
| Add price dislocation | 2 | 10 |
| Add persistent oversold/overbought | 2 | 5 |
| Add momentum fade | 1 | 5 |
| Add price reclaim | 0 | 4 |
| Price-reclaim branch + daily trend | 0 | 4 |
| Price-reclaim branch + peer timeframe | 0 | 3 |
| Price-reclaim branch + divergence at setup | 0 | 0 |
| Full stack | 0 | 1 |

All 1,296 variants failed the stated numerical screen. The screen was a conservative research criterion, not a theorem or an industry-mandated threshold: >=25 evaluated trades, >=3 active calendar quarters, profit factor >=1.3, positive month-block-bootstrap lower mean bound, positive stressed-cost mean, positive mean after removing the best trade, and positive mean in every active quarter. Here the sample-count requirement alone already disqualified every variant. Therefore it would be wrong to imply that every variant separately failed every statistical criterion.

The 3,771 ledger rows represent the same economic market events repeated across strategy variants and both time periods. They are **not 3,771 independent observations**.

## 5. Execution and validity controls

Entries use the next available RTH hourly opening price after confirmation. Same-hour stop/target ambiguity is resolved against the strategy. A stop gapped through fills at the opening price; a profit target gapped through receives no favorable price improvement. Structural exits were also evaluated: episode extreme plus 0.25 hourly ATR, initial risk 0.3%–3.5% of entry price, 2R target. Excessive risk is rejected rather than widening limits after a loss.

Calibration trades are purged when their exits reach the evaluation boundary. Late-period entries require a complete maximum observation horizon, irrespective of whether they would win quickly, to avoid selective right censoring. Positions do not overlap within a configuration. Indicators exclude future prices. Daily regime information uses the prior completed day. Missing/incomplete aggregates cannot arm or confirm.

Limitations remain substantial: one vendor's OHLC data, no quote-level fill validation, no observed overnight stop path, no dividends, no short borrowing cost/availability, no taxes, no independent second-vendor price audit, and no exact tick-level drawdown. Drawdowns are observed at hourly closes; extremes inside an hour can be worse. Cost scenarios are assumptions, not proof of executable liquidity.

The requested year has already been inspected while selecting candidates in the earlier analysis. It is **retrospective evaluation, not pristine out-of-sample validation**. A chronological split cannot undo prior inspection. No backtest probability here should be treated as a live success probability.

## 6. Why the 24-hour rerun requires more than turning on extended hours

### Separate signal value from execution value

Use a controlled four-arm comparison on identical eligible dates:

| Signal input | Permitted execution | Question |
|---|---|---|
| RTH-only | RTH-only | Original reference |
| Full-session | RTH-only | Does overnight information improve later daytime decisions? |
| RTH-only | Full-session | Does broader execution availability improve exits without new indicators? |
| Full-session | Full-session | Combined information and execution value |

These four arms have **not** been run in this study. They require actual native overnight data and executable quotes. Holding horizons must also be matched: 19.5 regular-session hours is approximately three daytime sessions, but 19.5 continuously traded hours is less than one full day. Compare the same 1/2/3 trading-day endpoints across arms, and report calendar time and tradable time separately.

### Preserve both bar-count and economic-horizon comparability

RTH 4H charts normally have one full 4H candle plus a shorter 2.5H closing candle. A genuinely complete 24H trading session has six full 4H candles. Applying the same MACD(5,13,4) therefore changes its effective multi-day memory, not just the available information.

The next comparison must test both native unchanged parameters and approximately calendar-horizon-matched parameters. As an illustrative, **untested** starting point, a threefold bar-frequency change would put MACD(5,13,4) near (15,39,12). This is not a recommended configuration and not an exact equivalence: exponential decay, missing trades, session boundaries, weekends, and the shortened RTH candle matter.

Use actual 1- or 5-minute data to rebuild 2H/3H/4H candles, with a fixed declared trading-session anchor such as 20:00 ET. Do not split an already aggregated 09:30–10:30 candle to invent 10:00 prices. Preserve holiday/DST handling and distinguish absent trades from absent feed coverage. Rebuild the native data clock rather than treating four RTH candles as eight continuously traded hours.

### Further preconditions worth isolating—not blindly stacking

The next local-tested, market-data-unexecuted experiment separates price reclaim, momentum fade, daily trend, and peer timeframe. It also compares reclaim plus exactly one companion filter and an anti-chasing limit. It avoids requiring every filter simultaneously.

With genuine overnight data, additional hypotheses should be tied to observed market mechanisms: sweep/reclaim of the prior overnight low/high; return above/below an episode-anchored VWAP; actual quote spread and freshness; sufficient displayed size for the modeled position; cancel a pending order if a new adverse extreme occurs before its fill; and reversal versus trend-pullback regime. No news, breadth, flow, or volume feature should be backfilled with future information or added merely because it explains losing trades after the fact.

A quote-derived setup could be informationally valid but untradeable at the desired size. Define the spread, quote age, price-limit and participation rules **before** evaluating profitability. BOATS is a venue feed; venue top-of-book is not automatically consolidated daytime NBBO. [S4–S5]

## 7. What is completed and what remains

**Completed:** preserved source snapshots and hashes; actual extended-feed coverage audit; 251-session return decomposition; 1,296-configuration stricter episode-based RTH run; selected 27 reference rows and complete filter-count summary copied to this evidence package; 21 local tests passing.

**Not completed:** genuine overnight history retrieval; 24H signal construction and execution results; market-data execution of the independent-condition experiment; quote/liquidity validation; untouched forward acceptance. No production model is admitted.

**Execution interruption:** the remote source write to `/private/tmp/soxx_refined_20261009_v2/independent_gates.py` timed out. Its state remains unknown; readback and a device liveness check also timed out. The write was not replayed. The independent market-data run was never started. The existing completed RTH results were read and hashed before this interruption.

**Exact recovery:** first reconcile that original file on mini4 against local SHA-256 `fc06f847a9b569fd322ed1fbca7f48e1d9e290710e391f594b707a168f31c076`, without overwriting an uncertain effect. Then execute the independent-condition experiment into its separate result directory. For the full-session commission, the remaining data input is an authorized SOXX historical BOATS export/connection covering the requested year and warm-up, paired with daytime data and quotes. Do not send credentials in chat.

## 8. Evidence package and reproducibility

The user download includes code, 21 tests, selected measured result tables, feed audit and continuation checkpoint. It does **not** include all raw price snapshots or the full 1,296-row sweep. Those were verified on mini4 at `/private/tmp/soxx_refined_20261009_v2` before the transport failure; `/private/tmp` can be ephemeral.

Completed run: PID 67010, exit code 0. Main research code SHA-256: `4cc737d79f746acae3119a5f85151c59cb62498602582b315ad48d978b139998`. Completed summary SHA-256: `17ad58121a57edf37c28b4f34c12bd22c3fd13457bad8b4aa2b23252e418aa5e`. Original hourly snapshot SHA-256: `ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720`.

No repository/Agent OS publication was performed. This is a user-facing research deliverable, not a production deployment or corporate acceptance record.

## Sources

S1. Alpaca, 24/5 Trading for Trading API: https://docs.alpaca.markets/us/docs/245-trading-for-trading-api  
S2. Alpaca, historical bars (single symbol): https://docs.alpaca.markets/us/reference/stockbarsingle-1  
S3. Alpaca, historical quotes: https://docs.alpaca.markets/us/reference/stockquotes-1  
S4. Tiingo, overnight data API: https://www.tiingo.com/blog/overnight-stock-data-api/  
S5. Tiingo, BOATS websocket documentation: https://www.tiingo.com/documentation/websockets/boats  
S6. Tiingo, API changelog: https://www.tiingo.com/documentation/general/changelog  
S7. Existing connected Mastermind Tiingo integration draft, inspected during this study: https://github.com/mastermindx-market-intelligence/macro/pull/8698  
Numerical result sources: preserved Yahoo chart snapshots and the completed local/remote research computation identified by the hashes above. Vendor documentation supports feed semantics, not the backtest returns.

S8. Bailey, Borwein, Lopez de Prado and Zhu, The Probability of Backtest Overfitting, author/university abstract: https://scholarworks.wmich.edu/math_pubs/42/  
S9. FINRA, market liquidity and disclosure guidance: https://syndication.finra.org/content/understanding-disclosure-documents