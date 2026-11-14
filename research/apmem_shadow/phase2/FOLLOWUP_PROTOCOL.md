# Diagnostic follow-up boundary

This is recorded AFTER viewing initial six-asset results and the primary joint-options result. These follow-ups are explicitly exploratory, not a newly untouched holdout. Original model rules, fits, bad outcomes and the 2,000-resample diagnostics remain retained. No live strategy is changed.

## Fixed attribution question

The joint IV30/GEX extension improves five-day HAR losses on QQQ/SPY/IWM, but that does not identify which input helps or prove an advantage against APMEM. With all original fitting settings unchanged, fit three additional ablations: extended HAR plus IV alone; extended HAR plus GEX alone; original joint-options model with one additional session of lag in its options columns. Add exactly one unoptimized forecast combination: half direct-target APMEM variance plus half HAR-IV variance. Compare all on the same matured observations, for both existing targets and all three horizons; retain era breakdowns, failures and uncertainty. No weight or threshold sweep. Unknown historical options availability remains a hard limitation. This is physical-variance prediction from option-derived inputs, not a claim to observe dealer inventory or the creator's formula.

## Measurement precision and tests

The original 2,000-resample p-value resolution is 1/2,001; for the full 264-comparison primary family, Holm's first threshold cannot be reached at 5%. Recompute only the identical paired-loss inference with 20,000 resamples and the same 63-session blocks/seed, then adjust the complete family. This improves numerical resolution, not sample size or research independence. The original diagnostics remain available. Correlated assets are not independent replications, and bootstrap stationarity remains an assumption.

The hindsight exposure-matched static diagnostic should match the actual delayed, evaluated weights rather than the signal-date average. Recompute that diagnostic exactly from the already generated paths and record its small difference; this is a benchmark-accounting correction, not a strategy modification or prospective comparator. Decompose dynamic-minus-static arithmetic daily returns into avoided negative-day exposure, forgone positive-day exposure and residual transaction-cost effects. These sums are not compounded portfolio wealth.

## Forecast reliability and execution clock

Measure loss/underprediction conditional on the already-known disagreement among EWMA/APMEM/HAR forecasts, using causal trailing-252 percentile ranks. This is a descriptive reliability diagnostic, not a new gate tuned to future outcomes.

For an execution-aligned tail test, at close t forecast the log return from open t+1 to open t+2. Only standardized residuals whose endpoint is already observed (origin <= t-2) may calibrate its lower quantiles. Use the same 504-window/252-minimum, 5% and 1% levels, and compare H1 and H5 variance scales. Report this separately from the primary close-to-close calibration. The variance target and execution interval are not silently relabeled as the same quantity.

Public creator forecast-history comparisons retain both possible date alignments, the common independent target, and unknown timestamp/target semantics. They can motivate a forward head-to-head test, not certify superiority to his private live system.
