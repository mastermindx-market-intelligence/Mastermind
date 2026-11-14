# Incremental VIX/VVIX risk-axis results

Status: completed retrospective development diagnostic; no trading or trough-prediction promotion. Protocol was published before these outcomes. Computational source b3296def15dee575b3a511e8cd6247db8cb7038c; original numerical exit0. Completed2026-11-14T07:50:30.802162Z. Numerical root /tmp/grey-rotation-context-20261114-e9m1oy12/risk_results_schema_fixed.

## What was tested

Eleven fixed ETFs: QQQ,SPY,IWM,XLB,XLE,XLI,XLK,XLP,XLU,XLV,XLY. Only price/index observations through2019-12-31 were read by the statistical pipeline. Evaluation origins begin2013-01-02; 1732 matched five-session origins and1717 matched twenty-session origins per instrument. Targets mature entirely by the cutoff. Four fixed chronological log-ridge forecasts, own realized-risk terms -> add VIX -> add VVIX level -> add VVIX mean-trend terms. All four share the same eligible rows. The complete run contains2464 successful fits and303512 score rows; duplicate targets/models and overlapping ETFs/horizons are NOT independent evidence.

The existing VIX and CBOE VVIX stores were reused with one-session lag and no forward fill. A lag is an availability assumption, not proof of historical publication vintages. The original phase2 scratch root was missing; retained phase3 ETF target copies and their original input fingerprints were recovered, as recorded in INPUT_RECOVERY.md. The initial reader admitted QQQ/SPY/IWM but rejected eight sector files because their declared parquet date index is `Date`, not `date`. The metadata-bound reader was repaired, three real parquet guard assertions passed in the numerical environment, and the three completed instruments were reused only after exact model/filtered-input hash checks. No outcomes or hyperparameters were used to choose that repair. Both runs remain preserved.

## Primary variance-proxy loss, lower is better

| Model | H5 mean QLIKE | H20 mean QLIKE |
|---|---:|---:|
| Own realized-risk HAR | 0.251970376 | 0.224320948 |
| Plus lagged VIX level and mean trend | 0.245719246 | 0.234944204 |
| Plus lagged VVIX level | 0.246864098 | 0.238815957 |
| Plus VVIX mean-trend terms | 0.247841900 | 0.238980078 |

Adding VVIX level or its moving-average terms did not improve these point estimates. No declared comparison passed the Holm-adjusted5% threshold across the12-test family. This does NOT establish that VVIX is useless, nor test whether a rare grey-dot/cohort-washout interaction has value. It directly rejects treating added fear-indicator complexity as a demonstrated risk-forecast upgrade in this specification. Keep VIX/VVIX as separately labeled context; a blanket rising-VVIX entry veto remains unvalidated.

## All twelve declared paired comparisons

Differences are candidate minus baseline QLIKE; negative favors the candidate. Intervals are pointwise calendar-block bootstrap95% intervals, not simultaneous intervals. Holm p-values adjust the whole declared family. The procedure averages paired losses across instruments on each date before block resampling; it does not treat ETF observations as independent.

| H | Target | Added component | Mean loss difference | Pointwise95% interval | Holm12 p |
|---|---|---|---:|---|---:|
| 5 | variance | VIX | -0.006251129 | [-0.025160709, 0.022811141] | 1.000000 |
| 5 | variance | VVIX level | 0.001144851 | [0.000067099, 0.002312306] | 0.445277 |
| 5 | variance | VVIX trend | 0.000977803 | [-0.000807131, 0.002855075] | 1.000000 |
| 5 | squared return | VIX | -0.018599650 | [-0.030686557, -0.005918415] | 0.083958 |
| 5 | squared return | VVIX level | 0.001240730 | [0.000008986, 0.002662783] | 0.555722 |
| 5 | squared return | VVIX trend | 0.000805070 | [-0.001837234, 0.003394351] | 1.000000 |
| 20 | variance | VIX | 0.010623257 | [-0.015956407, 0.056177620] | 1.000000 |
| 20 | variance | VVIX level | 0.003871753 | [0.000822708, 0.007417164] | 0.249875 |
| 20 | variance | VVIX trend | 0.000164120 | [-0.007500171, 0.007159353] | 1.000000 |
| 20 | squared return | VIX | -0.003529869 | [-0.018317914, 0.016037827] | 1.000000 |
| 20 | squared return | VVIX level | 0.004324063 | [0.001300820, 0.008011845] | 0.170415 |
| 20 | squared return | VVIX trend | 0.000333345 | [-0.008431750, 0.008256548] | 1.000000 |

The5-session squared-return point estimate benefits from adding VIX, but the result remains outside the family's5% criterion. The goal is not to turn a near-threshold p-value into a trading permission. None of these tests predicts the sign of a sector move or replicates the team's21/63-session real-trough ruler.

## Scientific limitations

The sample is pre2020 development history, not a fresh untouched holdout. Prices are current-vintage retained reconstructions. VIX/VVIX availability is conservatively lag-assumed, not timestamp-certified. Actual latent volatility is unobserved; overnight-plus-range and squared returns are proxies. The model class is deliberately small and linear in transformed variables; it does not exhaust nonlinear/state-dependent hypotheses. ETF overlap, horizon overlap, regime shifts and the limited number of crisis episodes constrain inference. Bootstrap draws are not new observations. No2020+ outcome statistic, grey-dot strategy return, stop-loss optimization, new collection service, live gate, position size or trade was created.

## Decision

Retain the explicit market-context lane and the simple own-risk/VIX baselines. Do not add a claimed VVIX authority premium or force a universal high/rising-volatility block. The next joint question belongs in the existing team's controlled grey-dot cohort panel: conditional on the same date and comparable market/beta exposure, does risk transition plus genuine cohort recovery improve the registered trough/participation outcome beyond the common washout clock? This diagnostic supplies a falsifier and qualified features, not a competing answer to that held-back test.
