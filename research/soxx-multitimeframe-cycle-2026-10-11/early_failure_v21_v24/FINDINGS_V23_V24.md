# Early cycle-failure economics, v21–v24: timing, asymmetry and execution

**Checkpoint source date: October 12, 2026. Exploratory retrospective, not a live trading model.** Original design originated from the already-inspected 2025-10-09 through 2026-10-08 RTH year. Instruments: SOXX, SMH, QQQ, AMD, NVDA, MU, INTC, AMAT, LRCX, KLAC, XLV, XLE. 91 total eligible parent-turn episodes. AVGO unqualified because full 15-minute warmup was not retrieved. No actual historical 20:00–04:00 SOXX BOATS series, actual quote marketability or point-in-time source vintage.

## Frozen economics

Completed 3H MACD(8,21,5) negative-but-rising histogram and Stoch RSI K rising at or above D, preceded by >=2x its prior 80-bar RMS downside extension and K<=20. Buy at next available RTH 15m open. Protective stop 1.5% below price, hypothetical 25% sale at +2%, 5bp per side costs, 52 *observed RTH hours* maximum hold. Candidate failure exits after completed 5m bars are next-open, never hindsight fills on the triggering close. Emergency stop preempts a discretionary sale.

## v21 — Six predefined intervention times

At each time, the intervention applies only to positions still open. The hypothetical hindsight oracle can choose to exit or keep holding after observing the future; **its upper bound is not predictive accuracy**.

| Decision time (observed RTH) | Eligible / 91 | Perfect-hindsight ceiling per original opportunity | Below-entry exit rule per original opportunity |
|---|---:|---:|---:|
| 15 minutes | 78 | +0.8572 pp | -0.3711 pp |
| 30 minutes | 76 | +0.8826 pp | +0.1414 pp |
| 1 hour | 65 | +0.6423 pp | -0.3278 pp |
| 2 hours | 60 | +0.6553 pp | -0.0802 pp |
| 3 hours | 56 | +0.5427 pp | -0.0150 pp |
| 6 hours | 34 | +0.2260 pp | -0.3461 pp |

The apparently promising 30m below-entry mean has a week-block confidence interval **[-0.2535, +0.4774] pp**. It is *not a robust positive signal* and cannot be selected post-hoc as if it were a preregistered live strategy. The v21 output includes 1,638 policy/checkpoint/event records and 1,092 independently checked exit accounting records.

## v22 — Fixed six-feature chronological ridge regression FAILED

Features available only after the completed 5m bar: accumulated entry-price return, recent 3-bar close momentum, prior high excursion, prior low excursion, close range position, prior 12-bar average range divided by price. Fixed ridge penalty 12; no training on the current test week, minimum 20 past eligible trades across six prior weeks. Exit only if the predicted marginal value of exiting exceeds +0.25 percentage points. Targets clipped at +/-10 pp for training, not trade sizing.

| Decision time | Chronologically eligible observations | Interventions | Incremental net return vs holding |
|---|---:|---:|---:|
| 30 minutes | 56 | 17 | **-0.1512 pp** |
| 3 hours | 34 | 6 | **-0.1980 pp** |

Week-block 95% exploratory intervals include zero: **[-1.0103, +0.4578]** and **[-0.6317, +0.1052]** pp respectively. 182 event/checkpoint records were evaluated; 90 were forecast eligible, 92 lacked enough strictly earlier training. *Do not use this model to make trading decisions.* No pristine out-of-sample cohort was created.

## v23 — The economically asymmetric cost of a false exit

The original research objective is not “detect red candles,” but “avoid a consequential failed cycle without sacrificing a winner's continuation.” A correct early exit has far less economic benefit than a wrong early exit's potential harm.

| Cohort/checkpoint | Checkpoint-eligible | Mean benefit when exit is better | Mean harm when holding was better | Harm / benefit | Required correct-decision proportion under this simple payoff approximation |
|---|---:|---:|---:|---:|---:|
| All instruments, 30 minutes | 76 | +1.544 pp | -10.289 pp | **6.66x** | **86.95%** |
| All instruments, 3 hours | 56 | +1.703 pp | -8.826 pp | **5.18x** | **83.83%** |
| Six newly added semiconductor names, 30 minutes | 35 | +1.589 pp | -14.013 pp | **8.82x** | **89.82%** |
| Six newly added semiconductor names, 3 hours | 20 | +1.720 pp | -11.594 pp | **6.74x** | **87.08%** |

The required proportions are **illustrative economic break-even proportions conditional on making an actual positive-action decision** and using sample mean benefit/cost; they are not validated classification thresholds, sample-free universal prices, or forecast probabilities. They are highly sensitive to a few large rebounds. A forced exit is not a viable substitute for precise failure evidence.

## v24 — Delay / adverse sell execution stress

With the unchanged below-entry exit definition, time-of-decision was held fixed and *additional* sell slippage was charged against the next available 5m opening. The stress grid has 4 asset groups x 2 checkpoints x 3 delays (1,2,4 five-minute bars) x 5 extra slips (0,10,25,50,100 bp) = **120 rows**, with **2,730 per-event counterfactual stress records** retained only in the private research workspace.

At 30m with one-bar execution delay, whole 91-episode mean lift was:

| Added sell slippage | Mean lift |
|---|---:|
| 0 bp | +0.14137 pp |
| 10 bp | +0.11025 pp |
| 25 bp | +0.06357 pp |
| 50 bp | **-0.01423 pp** |

At 3h the original +0-delay-cost lift is **-0.01501 pp**, deteriorating to **-0.12853 pp** by an additional 50bp. Some 2/4-bar delayed scenarios happen to show better backtested prices; this is **not** proof that latency improves execution, and no historical bid/ask data or order queue information was available. Do not cherry-pick delays.

## Saved verification

- Validation v21/v22: 1,638 v21 records, 1,092 source policy checks, 182 v22 event/checkpoint records, 90 forecast-eligible, 23 executed hypothetical model exits and 92 no-prior-training cases. No actual tick fill or untouched history accepted.
- Verification v23/v24: 24 economic asymmetry rows, 120 execution stress rows, 2,730 per-event private stress records, all 120 stress sequences monotone by additional adverse slippage, source and aggregate parity checks passed.
- The code was retained from the original mini4 execution and copied unchanged. The .csv aggregates and .json results are derived summaries, not the licensed actual OHLCV or individual executions.
- The newly published source files are offline-only and require private source snapshots. The original 5m actual bar source on mini4 retains different current/stored tail provenance; historical price adjustment and publication-known-at evidence remain unverified.

**Ruling:** None of v21, v22, v23, v24 establishes a deployable SOXX cycle-failure exit. The next useful advance is an independent sample with actual historical marketability and a frozen decision threshold, not another optimized threshold on the same inspected 2025-26 period.

Reference: parent research [PR #1338](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1338), prior [v20 oracle evidence](../early_failure_v20_v22/FINDINGS_V20_V22.md).
