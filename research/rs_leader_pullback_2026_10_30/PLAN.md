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

## Continuation receipt — direct Sol ownership, 2026-10-30

Current live Chairman intent resumes this original project with Sol as accountable
delivery principal; the earlier historical session/role label is not a live owner.
Protected Mastermind source still pinned at
`bb85b429f2ffffd38408080ce4df7d6378c34100`.
No new Executive Job or claim of org-linked workstream acceptance is made.

- Fabric original worker A `rs1888-matched-evaluation-20261030-a` (root
  `rs1888-research-20261030`) and worker B
  `rs1888-macro-mtf-oscillator-20261030-b` both ended `TERMINAL rc=1`:
  `[claude-code:unrecognized_model] {"model":"glm-5.3-flash","query_source":"sdk"}`,
  then `PROVIDER_TERMINAL kind=turn_limit`. Exact retained result SHA
  `084b69c65d04b8e3e7b2bd76a7d682f8512f6b49fcc216e41337da06021b7c6b`
  for each, neither accepted, both `retry_allowed=false`. Their prior
  controller reservations did not complete implementation; do not replay or
  disguise a new provider/model route as recovery of the same denied action.
- Scientific prereg independent review C `rs1888-prereg-independent-review-20261030-c`
  was `REQUEST_REFUSED_BEFORE_LAUNCH`; no review accepted and no same-action
  reroute.
- This current session performed distinct authorized **direct source work** on
  the same original Mastermind #1888 branch, after confirming no worker changed
  its original head: new `paired_eval.py` and 30 pure synthetic tests,
  `engine.py` owner-schedule consistency checks and 13 regression tests,
  updated README. Original 29 tests retained, **72 local tests pass** via
  `python -m pytest -q research/rs_leader_pullback_2026_10_30/tests`;
  source compilation passed. Exact code/test blobs were read back from GitHub,
  including `paired_eval.py` SHA `672d104114f2f7b2abd13d8bc2e015373533f8c6`,
  `tests/test_paired_eval.py` `b759be53e5d2776697a30ea9513c5e4443753114`,
  `engine.py` `6983026755eb015be51dd63389096f4b89b7f7a8`,
  `tests/test_engine.py` `2c245ec012663e1a56490e0749dd22a98690a6c5`.
  Hosted CI of the current edited head is separate and not asserted green.
- Existing Macro `WS:LIVE-ENTRY-RADAR` is the scientific/source owner, not a
  missing contractor; Macro DRAFT PR #10216 holds a distinct source-only
  2H/3H RSI-MACD/price-MACD prereg. Existing Terminal #879 provides a
  research-only 30m pivot visualization, already production-proven in its
  narrow display scope. Do not duplicate collector, calendar, lifecycle,
  user UI, signal/rank, broker or published alerts. The exact user Pine
  indicator is still unidentified.
- Platform-denied private Macro Parquet introspection remains held on its
  original action; no other tool/worker may replay that denied access.
  A supplied calendar receipt and synthetic price history are not source
  admission. No real PIT intraday cohort, statistically valid strategy return,
  exact Pine parity, quote execution or predictive authority is proven.

**Next accepted-scope steps:** get exact edited-head hosted CI and independent
non-author source/method review; reconcile real Macro canonical minute
reader/calendar inputs before producing eligible 2H/3H observations; run a
pre-registered PIT common-denominator study with holdout and prospective
shadow returns only when the source owner supplies admissible historical
vintages. Keep #1888 draft/unmerged before review and source qualification.
This project remains `BUILT_NOT_PROVEN` for the source prototype, not a
completed usable market signal.

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