# APMEM/options investigation: empirical findings and qualification

As of 2026-11-13. Parent mission: apmem-shadow-20261113. This is an implementation-and-evaluation result, not a production trading release.

## Decision

**Do not promote this original QQQ directional candidate into Prophet ranking, sizing, trading or live alerts.** Retain the original code and frozen negative results as reusable research. The engineering-retention variance model is a promising volatility-forecast research candidate, not a validated directional signal. The creator's published historical regime remains interesting under next-open execution, but his private generator and historical publication timestamps remain unverified.

These conclusions concern three different objects and must not be collapsed: (1) the creator's retrospective published states, (2) our original fixed volatility/options hypothesis using different options inputs, and (3) a variance forecast. Poor performance of (2) does not disprove (1), while improved variance loss in (3) does not establish profitable trading.

## Work performed and evidence identity

The prior 753-row dashboard audit was reproduced. The original protocol and its addendum were committed before the first actual-market-data fit: protocol commit `712bbac79b16517a1cf16a554d9ca7492dafa9c8`, addendum commit `5ab4bdf26949331eb5026b4ae896a92387c5e4b1`. The screenshot and overlapping market history were already known, so this is not an untouched strategy-selection holdout.

Main empirical implementation: commit `e60dd144f362b83dde5b7fcb6f4f698672d5eed3`. Its four substantive Python files were fetched and SHA256-checked against the authored source before execution. Creator next-open audit: commit `2d47977a4269e781ff88964453ba3d99275b5429`. Supplemental uncertainty/export and 57 tests: commit `d13c6edd14e7b47cad88ef17a1eab898c43fdf07`.

Both the principal container and the actual numerical host passed all **57** tests. These verify causality/indexing, numerical recurrences, initialization/fit failure behavior, missing data, execution delays, initial/final costs, scalar replay agreement, block-bootstrap mechanics and consumer abstention. Unit-test success is not predictive-performance validation or hosted-CI proof.

The empirical runtime used NumPy 2.4.6, pandas 3.0.3, SciPy 1.18.0 and PyArrow 24.0.0. The principal environment used NumPy 2.3.5, pandas 2.2.3 and SciPy 1.17.0. No bit-identical cross-version fitting result is claimed.

## Data and comparison windows

QQQ, SPY and IWM each have 4,242 current-vintage raw-OHLC sessions, 2010-01-04 through 2026-11-12, obtained through the existing approved Yahoo/yfinance route. Auto-adjust, back-adjust and repair were disabled; corporate-action fields were retained. No split events were reported in these panels. Distributions are not included in the declared price-return evaluation.

The existing ThetaData-derived reconstructed options archives contain 2,469 QQQ rows, 2,470 SPY rows and 2,469 IWM rows, beginning 2017-01-03 and ending 2026-11-05. The observed root columns match their instruments. GEX assumes long calls/short puts; it is not observed dealer inventory, a bullish probability, or Signal Sigma's proprietary feature set. Historical first-availability clocks are unknown. An explicit one-session options lag is a simulation assumption, not evidence those historical data existed then.

The paired directional comparison begins 2017-02-02 and ends at the 2026-11-12 open. Forecast diagnostics use 3,989 aligned next-session targets after warmup. Each asset/variant has 64 scheduled fits; all 384 selected fits succeeded. Boundary parameters remain common: QQQ has 57/64 boundary fits for retention 0.05 and 47/64 for 0.94. Optimizer success alone is not model adequacy.

QQQ raw prices were cross-checked against the incumbent Massive panel on 1,346 overlapping sessions: maximum absolute close difference 0.0000293; maximum absolute open difference 0.005025. This materially corroborates the numerical price panel, not historical publication availability.

## Frozen original directional experiment

The original APMEM recurrence is fitted only on preceding/current observations, with minimum training 252 sessions, maximum rolling training 504 and refit every 63. The literal published correction retention is 0.05; an explicitly distinct engineering comparator uses 0.94. The correction, scale, rolling thresholds and inputs are causal. This is our bounded specification, not a claim to reproduce NYU's optimizer or the creator's engine.

Volatility relief requires a falling next-session forecast above its preceding-window 80th percentile. Options relief requires prior-session GEX above its preceding 20-session median and falling IV30. Price relief requires a positive daily return while at least 5% below the trailing 20-session closing high. The protocol retains price-only, volatility-only, options-only, volatility-plus-options and all-three ablations.

Simulated entries use the next open, hold 20 open-to-open intervals, ignore re-entry signals originating while occupied, and retain censored endpoint episodes. Both next-open and an extra session of delay, and both 5 and 20 basis points per one-way exposure change, are retained. Cash earns zero. There are no shorts, leverage, distributions, taxes or financing in this original directional test. Drawdown is open-mark, not intraday or closing drawdown.

### QQQ: primary next-open, 5 bp each way

| Policy | Retention | Total price return | CAGR | Open-mark max drawdown | Exposure | Zero-cash Sharpe | Episodes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Buy/hold | Both | 442.80% | 18.89% | -37.09% | 100.00% | 0.889 | 1 |
| Price only | Both | 50.69% | 4.28% | -41.06% | 29.41% | 0.335 | 37 |
| Volatility only | 0.05 | 59.55% | 4.90% | -33.33% | 32.67% | 0.379 | 41 |
| Options only | Both | 191.25% | 11.56% | -43.53% | 78.93% | 0.654 | 97 |
| Volatility + options | 0.05 | 27.97% | 2.55% | -32.99% | 17.09% | 0.271 | 21 |
| All three | 0.05 | 10.53% | 1.03% | -31.76% | 8.95% | 0.150 | 11 |
| Volatility only | 0.94 | 71.68% | 5.69% | -30.52% | 38.36% | 0.404 | 48 |
| Volatility + options | 0.94 | 20.81% | 1.95% | -23.73% | 13.83% | 0.236 | 17 |
| All three | 0.94 | 24.29% | 2.25% | -16.85% | 6.51% | 0.311 | 8 |

Lower return than fully invested buy/hold alone is not a risk-matched alpha test. Nevertheless, low exposure combined with substantial drawdown, weak zero-cash Sharpe, small independent episode counts and unverified data timing does not support promotion of this QQQ candidate. No parameter was retuned to repair this outcome.

The combined 0.05 candidate has 80 mature overlapping events, 66.25% positive 20-session outcomes, median +1.40%, and 21 greedy nonoverlapping events. The combined 0.94 candidate has 59 mature events, 62.71% positive, median +0.90%, and 19 greedy nonoverlapping events. Executable episode counts can differ because the simulator ignores events originating while held. These selected-sample fractions are not calibrated future win probabilities.

For combined QQQ, the four delay/cost scenarios give CAGR 1.90%-3.43% for 0.05 and 1.05%-1.95% for 0.94. The 0.94 candidate's worst completed trade runs 2018-11-30 to 2019-01-02 and loses 10.42% net under the primary convention. Twenty-session rebound labels do not identify exact bottoms.

### Unretuned asset-transfer checks: mixed, not a selected new winner

| Asset/policy | Retention | CAGR | Open-mark max drawdown | Zero-cash Sharpe |
|---|---:|---:|---:|---:|
| SPY buy/hold | Both | 13.02% | -32.45% | 0.791 |
| SPY combined | 0.05 | 5.73% | -15.42% | 0.701 |
| SPY combined | 0.94 | 4.61% | -9.77% | 0.614 |
| IWM buy/hold | Both | 7.77% | -42.32% | 0.440 |
| IWM combined | 0.05 | 4.75% | -17.69% | 0.461 |
| IWM combined | 0.94 | 6.80% | -15.13% | 0.654 |

IWM is favorable counterevidence to a blanket claim that every hybrid is useless. Its options-only ablation is also comparatively strong. It is not permission to replace the primary QQQ test with IWM after observing outcomes. These equity ETFs are correlated, and their historical reconstruction/availability limitations are shared. All 132 strategy/cost/delay rows are retained in the derived result export.

## Forecasting is more promising than the tested trading rule

The strongest simple control is raw-range EWMA multiplied by the already-known next-session correction factor. Comparing only against EWMA of the adjusted proxy would give the model an unnecessarily weak opponent. QLIKE is computed on identical target rows within each preprocessing variant; lower is better.

| Asset | APMEM, literal 0.05 | Strong control | APMEM, engineering 0.94 | 0.94 relative loss improvement |
|---|---:|---:|---:|---:|
| QQQ | 1.20576 | 0.45600 | 0.40045 | 12.18% |
| SPY | 1.22597 | 0.49319 | 0.41438 | 15.98% |
| IWM | 0.99975 | 0.34902 | 0.32001 | 8.31% |

The target itself changes with correction retention; comparing APMEM scores across columns is not a target-invariant model comparison. The control's equal QLIKE across variants is analytically expected: the common positive correction factor cancels in realized/forecast ratios.

Post-evaluation circular moving-block bootstrap diagnostics use 2,000 resamples, seed 20261113, and block lengths 20 and 63. With 63-session blocks, mean APMEM-minus-control QLIKE differences and pointwise 95% percentile intervals are:

| Asset | Retention | Mean difference | Pointwise interval |
|---|---:|---:|---:|
| QQQ | 0.05 | +0.74976 | [+0.68740, +0.81395] |
| SPY | 0.05 | +0.73277 | [+0.65720, +0.82437] |
| IWM | 0.05 | +0.65073 | [+0.60133, +0.70148] |
| QQQ | 0.94 | -0.05555 | [-0.08593, -0.02678] |
| SPY | 0.94 | -0.07882 | [-0.10963, -0.04794] |
| IWM | 0.94 | -0.02901 | [-0.04948, -0.00939] |

The 20-session intervals have the same sign pattern. These intervals are descriptive and pointwise, not multiplicity-adjusted, and assume the resampled blocks are informative about sampling uncertainty. They do not cure regime nonstationarity, selection, revised data or missing historical clocks. The evidence justifies retaining a volatility research candidate, not a production risk estimate or directional trade.

## Creator output audit: next-open timing preserves a substantial historical advantage

The public dashboard still has the same 753-row canonical snapshot, SHA256 `99b99a1590725062916fb21887033ad671ac4b4685235d7d49ecbb77e9579efb`. The independent-opening-price comparison runs 2023-11-14 through 2026-11-12. It uses the published states, not inferred original rules.

| Published-state policy | Gross price return | Illustrative cost-adjusted price return | Gross open-mark max drawdown |
|---|---:|---:|---:|
| Buy/hold | 77.30% | 77.12% | -24.28% |
| Long/short, next open | 179.63% | 172.74% | -18.13% |
| Long/cash, next open | 126.84% | 125.93% | -13.43% |
| Long/short, one additional open delay | 145.49% | 139.44% | -17.76% |
| Long/cash, one additional open delay | 112.39% | 111.54% | -13.43% |

Illustrative costs are 5 bp per target-exposure change and 3% annual short borrow charged per trading interval. The daily-reset exposure simulation omits maintenance-rebalance turnover, distributions, cash interest, tax and actual financing. It is not a broker-verified net track record, fixed-share short or options implementation.

**Correction to a possible overinterpretation of the earlier close-delay audit:** the earlier 96.77% timing attribution concerned the wealth gap between signal-close and next-close assumptions, not all profits. The advantage does not vanish under next-open timing. The April reversal still needs a genuinely contemporaneous signal receipt; the snapshot has only six state changes/three completed short campaigns and cannot establish that the states existed at each historical decision time.

A new data-quality discrepancy is isolated to the last displayed close: 2026-11-12 is 690.58 on the creator dashboard versus 688.1699829 in Yahoo and 688.17 in Massive. Earlier close differences are essentially floating-point rounding. This may be a quote-timing convention and is not evidence of fraud. The next-open replay uses independent opens and does not depend on that disputed closing value.

## Consumer proof and adoption boundary

The real QQQ invocation returned **ABSTAIN**, with `FIT_CLOCK_UNKNOWN`, `OPTIONS_CLOCK_UNKNOWN`, `OPTIONS_SESSION_MISMATCH`, `OPTIONS_STALE`, and `PRICE_CLOCK_UNKNOWN`. The latest options observation is November 5 versus prices through November 12. Source digests exist, but date-only bars and newly reconstructed historical fits do not supply authentic earlier availability clocks.

This proves the actual rejection path, not a successful live forecast feed, calibrated production feature, or deployed Prophet integration. `may_rank`, `may_size`, and `may_trade` are always false. No production service, collector or scheduler was installed. Current data freshness and source-clock lineage, independently frozen prospective evaluation and the private creator's missing signal logic remain distinct gaps; none is fixed by a profitable replay.

## Team and source custody

The principal performed implementation, source self-review, tests and data evaluation. Connected Fabric reported an unavailable adapter; the separate Executive method-review admission returned `grounding_unavailable`, without a Job/START receipt. No refused or unknown-effect operation was rerouted and no replacement adapter or runtime was installed.

The existing Grok Secretary teammate completed a bounded read-only access diagnostic on Slack thread `1794584248.103159`; the parent consumed it and sent STOP. A separate empirical-results falsification review was deliberately assigned on thread `1794585392.580479`, with exact source, distinct scope, no implementation rights and no formal GitHub approval request. Its final disposition belongs in the release/closeout receipt; delivery or PICKUP_ACK alone is not completed independent review. No full subagent team execution is claimed.

## Reproduction receipts

Actual original runs are retained in the private research scratch `/tmp/apmem-shadow-20261113-rf6af7py`. Raw vendor rows are not published here. Derived export JSON transferred with SHA256 verification: `9ff2e319878e45de8aef3821056ca0f13b4435bf2e0186eeb5b02061aa635d0d` (37,037 bytes; includes all 132 strategy rows, six forecast comparisons/uncertainty records, source/data receipts and creator replay).

Source-manifest SHA256 values:
- QQQ: `366fbd1dc502b34c882da0899c27a746072a5a4cfa238c80e4237d480521c487`.
- SPY: `52ba4cf000925582d8f66012b18e71ceb5f2147ef673a0ca9635618cffcde9ef`.
- IWM: `d257866d1c478c5d0166b1eb8f029d100ed6f4f603e00e775cc66c4d01cee20b`.

Primary reference: https://vlab.stern.nyu.edu/docs/volatility/APMEM . Approved acquisition documentation: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html . These references support methodology/API conventions, not our performance numbers; those come from the identified code and actual run receipts.

## What is not claimed

No exact private-system reconstruction; no verified real-time signal history; no licensed Signal Sigma equivalence; no unseen forward results; no exact-top/bottom prediction; no autonomous market action; no production Prophet deployment; no hosted-CI or protected-merge completion inferred from local tests. A negative qualification is a useful completed research outcome, not a reason to optimize repeatedly until a backtest turns green.
