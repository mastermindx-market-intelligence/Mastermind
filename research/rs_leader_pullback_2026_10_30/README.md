# RS-Leader Pullback: research-only event study

**Status: BUILT_NOT_PROVEN (local synthetic tests only).** This is an original research prototype, not the precise proprietary TradingView MACD-RSI formula, not a funded-portfolio backtest, and not a live Mastermind signal.

## What it implements

Three independent long-entry cohorts, sharing the same point-in-time RS leader filter:

1. **`pivot`**: after at least three completed red RTH candles, the first green candle defines its high and low. Within the next two completed RTH candles, crossing above the pivot high + $0.01 triggers a buy-stop. Initial stop is pivot low - $0.01. The trigger bar is resolved with **stop-first** pessimism whenever its full OHLC touches both possible prices. A gap above the entry buys at the actual open, not the desired stop price.
2. **`macd_rsi_proxy`**: crossing of a standard MACD(12,26) above its 9-bar signal while *both* lines remain negative and 14-bar Wilder RSI <=40. Entry at **next bar's open**, stop below the most recent five completed lows. This is **not proof of equivalence** to the chart's unnamed MACD-RSI indicator. To test an exported indicator instead, include `osc_fast`, `osc_slow`, and `osc_oversold` (strict boolean), all computed without future lookahead, on every intraday bar.
3. **`hybrid`**: `pivot` only if a qualifying oscillator cross was already confirmed on the pivot candle or up to two completed bars earlier. A later crossover can never justify an earlier breakout entry.

Exit evaluation: stop below support, profit target +2 initial risk units, or end of fifth session after entry. In same-candle OHLC ambiguities, stop wins. Gap-through-stop sells at the adverse open. An unresolved observation is **censored**, not counted as a win, zero or an imputed exit. A 5-bp cost per side is applied; 5 bp is a *test assumption*, not a verified executable spread. Trade records are event-level outcomes and do not model capital allocation or cross-symbol overlapping positions.

The source's three-red/two-bar defaults mirror the openly described *TenAM Trader* adaptation of a 30-minute pivot, rather than claiming these precise thresholds are required by @1ChartMaster. Source: https://www.tradingview.com/script/fhvOnhag-Elite-30-Min-Pivot-by-TenAM-Trader/ . No third-party source code was copied.

## RTH versus 24-hour sampling

The current code accepts **RTH only**, with bar *end* timestamps in UTC, and `America/New_York` handling DST. A 30m session has 13 eligible completed candles. A 20m, 45m, 2H or 3H RTH chart excludes its incomplete final session fragment. `24H` and unqualified overnight candles are refused, never silently mixed with RTH. Qualified BOATS research must be separate, using the existing licensed Macro Data OS read route; equal-candle-count is not equal-signal behavior.

## Inputs

All datasets must be adjusted and sampled consistently, and legitimately available for historical analysis. **Input provenance, historical coverage and point-in-time eligibility must be externally audited before results are used to evaluate profit potential.**

- `bars.csv`: `timestamp_utc` (fully timezone-qualified candle END, ISO8601 UTC), `symbol,open,high,low,close,volume`, optional `session` (must be `RTH`) and `final` (strict true/false). Optional `osc_fast,osc_slow,osc_oversold` for direct exported indicator. Duplicate, incomplete, inconsistent, misanchored and missing within-session intervals are rejected.
- `daily.csv`: `date` (America/New_York exchange session, YYYY-MM-DD), `symbol,close,volume`. Requires SPY rows for the full *audited* exchange-session calendar. Daily rows for the signal session exist to establish the calendar, but **only the previous SPY session's completed close** may be used for leader classification. All securities need complete 61-session aligned histories for RS(20d,60d), $20M trailing average dollar turnover and a positive 21-session EMA trend.
- `membership.csv`: `symbol,start_date,end_date`, point-in-time membership spans, inclusive end date (blank if still active). This is not today's constituent list retroactively projected backward. A date fails closed if fewer than 95% of PIT members have observations. Leader candidates must be among the top 20% of valid symbols by mean 20d and 60d excess return over SPY, *both* RS windows positive. Default requires >=100 observed constituent symbols on the date.

If adjusted daily data and unadjusted intraday bars are mixed across a split or corporate action, resulting values are invalid. Benchmark time alignment, bankruptcies/delistings and historical security identity must be qualified by the source owner.

## Run on licensed historical CSV exports

    cd research/rs_leader_pullback_2026_10_30
    python -m unittest discover -s tests -v
    python run.py --daily /path/to/daily.csv --membership /path/to/pit_membership.csv --bars /path/to/rth_30m_bars.csv --out /tmp/rs_pullback_30m.json

Use `--timeframe 20`, `--timeframe 45`, `--timeframe 120` or `--timeframe 180` for independently built full bars. Do not simply relabel 30-minute bars as 2H. A source owner should qualify correct interval construction, partial sessions/half-days, missing observations and venue/quote accuracy before a statistical study. The script prints counts and descriptive metrics and writes complete event records and SHA256 of input files. Every output explicitly says `empirical_strategy_edge_verdict: NOT_ESTABLISHED` until an **independent** evaluation process confirms the result.

## Owner-calendar qualification and paired policy comparisons

`validate_bars(..., session_schedule=owner_calendar, require_complete_sessions=True)`
now checks the **provided** official session open/close against every full supported
bar, including the opening slot, final full slot, known early closes, intervening
missing whole sessions and New York DST. The input calendar is a caller-supplied
**consistency assertion, not authenticated source admission**; use the incumbent
Macro calendar/provenance owner for any historical study. Without it, the default
`session_coverage_state=NO_OWNER_SCHEDULE` and the event study is research-only.
`terminal_stub_minutes` counts the untradeable remainder (normally 30 minutes
for 120m and 180m regular-session charts), not a resized final candle. In partial
current-session mode the returned `PARTIAL_OBSERVATION` must never be relabeled
as a fully qualified historical sample. Existing `run.py` is a source-unqualified
exploratory CLI and does **not** enable the strict calendar gate by itself.

The new pure `paired_eval.py` supports the next, separately qualified research
phase: give it a complete **predeclared** opportunity cohort (including nonfires)
and two owner-evaluated policy outcome rows per opportunity. The comparison is
between candidate `pivot`, `macd_rsi_proxy` or `hybrid` and
`leader_reference` at the **same opportunity ID / decision time**. Each
opportunity specifies symbol, unique episode, ET session date, strictly
timezone-qualified decision / bar / previous-daily-leader / regime known-at
clocks, previous leader session, input digest, eligibility, signal and
chronological split. Each policy outcome supplies `RESOLVED`, `NO_ENTRY`,
`CENSORED` or `UNAVAILABLE`, with resolved net risk-unit return and actual
outcome/availability clocks. A missing paired policy or mismatched population
is an error, never an implicit zero or an unpaired favorable survivor.

```python
import pandas as pd
from paired_eval import PairedProtocol, evaluate_paired

# Both dataframes must come from an independently qualified,
# frozen Macro Data OS observation and execution-cost policy.
report = evaluate_paired(
    opportunities_df, outcomes_df,
    PairedProtocol(candidate="pivot", baseline="leader_reference",
                   registered_at_utc="2026-10-30T20:00:00Z",
                   analysis_asof_utc="2026-12-15T21:00:00Z"),
)
```

The module returns common-denominator/coverage and matched incremental R by
development, calibration and holdout block, with 20-session date-block
bootstrap intervals only when enough paired date clusters exist. It rejects
future features, unsupported outcome clocks, non-entry-as-zero input fields,
random/interleaved splits, overlapping development labels near holdout, and
postdated holdout registration. Non-entry contributes a deliberate zero only
when the policy explicitly says `NO_ENTRY`; censored and unavailable outcomes
remain null. Report labels `source_admission=NOT_ATTESTED_BY_THIS_EVALUATOR`
and `empirical_strategy_edge_verdict=NOT_ESTABLISHED` are intentional even
when supplied synthetic numbers look favorable. Neither a declared registration
timestamp nor a digest validates the provenance of a historical holdout.
The owner must establish source entitlement, PIT issuer/epoch, consistent
execution costs, and actual forward issuance before any edge claim.

Tests: `python -m pytest -q research/rs_leader_pullback_2026_10_30/tests`
(the local source candidate at this update passed 72 synthetic conformance tests).

## Required historical research before signal promotion

- Use original PIT S&P 1500 membership, including leavers, or another explicitly justified universe; delisted ticker identity, prices and corporate actions must be qualified, not inferred from current names.
- At least 2–3 years of complete 30m RTH bars across hundreds of eligible names for exploratory power, preferably multiple distinct market regimes. This is a target, not a claim that this data exists.
- Pre-register a small strategy parameter grid and **freeze it before** an untouched chronological holdout; do not keep peeking at the holdout. Comparisons: pivot, MACD/RSI proxy, hybrid, entry at time-matched RS-leader controls. Report regime and sector splits without conditioning on future information.
- Refuse optimistic OHLC-fill claims: gaps, stops, spreads, opening volatility, latency, overnight exposure and stock/event corporate actions can reverse apparent results. Evaluate 0/5/10/20 bp *per side* (or bid/ask-calibrated estimates) plus extra adverse stop-fill sensitivity.
- Report sample size, rejected/ambiguous/censored trades, median and mean net R, profit factor, drawdown of a **separately specified funded portfolio**, clustered uncertainty by event date and ticker, calendar-year folds, cross-sectional coverage, parameter sensitivity, and forward prospectively observed performance. Follow incumbent Mastermind `loop/` DSR, PBO/CSCV and BH-FDR standards where statistically applicable; no multiple-testing promotion from a single anecdote.
- Never attach live ranking, publication, broker execution, position sizing, alert routing or a new collector without the owning product/research authorities and real-path acceptance.

## Honest limits

The 29 local synthetic tests demonstrate computational invariants, not trading performance. This tool cannot independently prove a vendor archive's historic point-in-time quality, whether the supplied indicator repaints, a real fill, or alpha. The current conversation's connected Studio Direct and Executive read paths were unavailable at the data-acquisition attempt, and this execution container had no historical intraday CSV dataset or network access. Thus **no cross-equity historical win rate, return or comparison is claimed**. Mastermind PR #1338 is related *exit* research, not our entry-study validation, and must not be treated as a completed substitute.
