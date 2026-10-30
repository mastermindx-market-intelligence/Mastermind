# RS-Leader Pullback Strategy: source-bound task tree

Recorded: 2026-10-30 (UTC). Repository: mastermindx-market-intelligence/Mastermind. Branch: sol/rs-leader-pullback-20261030.
Protected-procedure pin: bb85b429f2ffffd38408080ce4df7d6378c34100 (master, mastermind.sol_skillpack.v1 / 1.0.1).
Commission: current Chairman instruction to lead research, testing and implementation of cross-equity RS-leader pullback entries inspired by @1ChartMaster's 30-minute price pivot and independently by MACD/RSI-like below-zero momentum reversals.

## User and machine outcome

A trader can inspect a reproducible head-to-head evaluation of price-pivot entries, momentum-cross entries, and their intersection among point-in-time RS leaders. A deterministic, reusable offline strategy/event-study engine produces complete trade/event records, rejected/no-trade reasons, metrics and falsifiers; qualifying future signals may be evaluated by incumbent production owners only after independent historical and forward confirmation.

DONE_WHEN for research engine: an original, inspectable Python implementation with a documented input schema; fixture tests for causality, gap/open execution, stop/target ambiguity, missing data, relative-strength selection, and session boundaries; proof of a real multi-equity historical run using licensed intraday and PIT reference data with explicit coverage and realistic execution costs; held-out and prospective verdicts reported separately. Product promotion/alerts/order routing require separate owning-service acceptance and proof.

## Scope and current authority

Source-only, isolated under research/rs_leader_pullback_2026_10_30/. No production entry-radar, market data collector, position sizing, broker order, vendor authentication, paid data acquisition, scheduler or live signal publication. Historical bars must come through the existing authorized Macro Data OS owner; do not copy or publish licensed raw bars. No new data collector or independent ranking/risk authority.

No verified existing Agent OS workstream mapping for this particular commission; no WS key invented. Organizational linking and handoff writer unavailable: PLAN_NOT_ORG_LINKED. This GitHub task tree is a research source artifact, not an Executive Job or approved organizational wave. Related non-owning research: Mastermind PR #1338 (SOXX 30m/3h *exit* work; empirical results inconclusive). Avoid touching its path or fabric child.

## Research hypotheses and advance/death rules

- H0: a price pivot provides no net incremental outcome improvement over matched eligible RS-leader entries.
- H1: a MACD-below-zero bullish crossover with an independently defined RSI oversold filter adds timing information.
- H2: pivot + oscillation confirmation outperforms pivot alone after costs, multiple testing and coverage correction.
- H3: 30m RTH is not automatically equivalent to 2H/3H around-the-clock bars because of sampling, liquidity and gap behavior.
- Counterfactual: compare with matched leader entries in the same ticker and regime; count rejected/failed pivots, gaps and stop-outs. Do not choose the successful historical pivot after the fact.
- Negative or unstable out-of-sample incremental value => report null and hold live promotion. No win-rate promise.

## Tasks (editorial, not runtime states)

- P1 [implementation_complete] Scope and source discovery. Evidence: protected master pin above, research/TREND_PERSISTENCE_PREREG_C1.md, brain/trend_persistence.py, loop/engine_backtest.py, and PR #1338. Risks: historical data owner/coverage unknown. No live source overlap identified in this isolated path.
- P2 [implementation_complete] Implement offline signal, execution and measurement library. Depends: P1. Acceptance: deterministic price pivot (first opposite-color bar after configurable red sequence; confirmation on subsequent bar, finite two-bar validity), MACD/RSI proxy, supplied TradingView oscillator columns, hybrid, stop/target/time exits, cost/slippage and next-bar availability; declared identical rules for every ticker. Exclude incomplete bars; explicit ambiguous OHLC precedence. Independent review required before merge.
- P3 [implementation_complete] Build red/green fixture tests and CLI CSV adapter. Depends: P2. Acceptance: tests demonstrate no same-bar future use, daily-as-of RS and index-membership correctness, conservative stop-first ambiguities, gap fills, no fabricated missingness, sector/benchmark availability and time boundaries; tests actually executed and published by exact commit.
- P4 [blocked] Run PIT cross-equity empirical tests. Depends: P2/P3 and qualified historical intraday (RTH and optionally overnight), PIT membership, corporate actions, benchmark/sector histories, correct clocks and realistic bid/ask or spread model. No licensed data presently present in this ChatGPT execution container; Studio/Executive read connections degraded at the start. The data owner must provide the qualified view through existing routes. Acceptance: coverage census, training/embargo/chronological holdout, costs, matched leader control, clustered confidence and confidence-limited verdict. Never substitute synthetic fixture outcomes.
- P5 [blocked] Product integration review. Depends: P4 independently positive; incumbent signal/Entry Radar owner and risk/publication contract. Shadow-first, original producer/consumer real-path check, observed forward performance and independent reviewer. No automatic orders.
- P6 [in_progress] Preserve current branch and PR with receipt, exact tests and explicit empirical-blocker status. Depends: P2/P3. Do not self-merge.

## Research invariants

RTH: America/New_York session; raw timestamps UTC; bar-close signals only, enter at later observable open or qualified stop trigger; open gaps charged at real open; stop-vs-target collision always uses pessimistic stop first. No overlapping same-ticker trades in the baseline engine. Earnings and regime tags are separate upstream as-of inputs, not inferred retroactively. RS league tables use only completed prior daily closes and PIT eligible names. No point-in-time rank if the cross-section is inadequately covered; null data must fail closed.

The signal called MACD/RSI is an explicitly documented *proxy*; exact reproduction of the supplied TradingView 'MACD-RSI' indicator requires its Pine source/settings or bar-by-bar exported oscillator values. Results must not be labeled as that exact proprietary indicator unless verified.

Current implementation receipt (2026-10-30): isolated branch sol/rs-leader-pullback-20261030, tested sources under this directory. Engine Git blob 0847e88e6ecee3dbab21856852763442f3321552; CLI blob ceadd48c2c741411a2596866130ef87b00479c2f; engine tests blob 7013529cb9fb20a3e42bb55128f647fb746b7f3a; CLI tests blob 21b3299d999330eed0ecc0c0c5f5cc573b19f453. Container `python -m pytest -q`: 29 passed (0.96s); `python -m unittest discover -s tests -q`: 29 OK; `python -m compileall`: passed. CLI end-to-end executed against SYNTHETIC fixture, one pivot return ~1.9797R, NOT a historical win rate or real market performance claim. Existing M2 PIT S&P 1500 and daily caches inspected by filenames, but attempts to interrogate the dataset via remote code were blocked by safety checks, and Studio/Executive read returned 404/429; no real licensed intraday export could be tested. Do not retry blocked access through another unapproved carrier. Important external alternative: hfdatalibrary.com IEX-only free series, but historical selection and sparse single-venue fills are not production-grade, and its stated data use is academic research only. Current next action: publish draft PR, obtain qualified data through incumbent Macro owner, independently review fills, then run PIT walk-forward and shadow evaluation.