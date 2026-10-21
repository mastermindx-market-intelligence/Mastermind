# Quantitative-validation cases

## Overlapping forward returns
Input: daily observations predict the next five trading days and a split puts
adjacent rows into train and test.
Check label intervals, not just row dates. Purge training labels crossing into
the evaluation interval and choose any embargo from the relevant dependence.
Do not present an arbitrary gap as proof that all leakage is eliminated.

## Full-dataset scaler
Input: features are standardized before the train/test split.
Fit the scaler within each training window, then transform that window's
validation/test. Rerun evaluation at the exact repaired source and disclose that
the earlier performance estimate was contaminated.

## Winner among many trials
Input: the best of 500 strategies has an attractive held-out result, and that
same set was inspected repeatedly during selection.
The selected set is no longer an untouched holdout. Record search history and
multiple-testing uncertainty; require a new holdout or prospective shadow study.
Do not claim the selected maximum estimates deployable performance.

## Attractive gross performance
Input: strategy earns a small average gross edge with high turnover.
Evaluate spread, fees, slippage, latency and plausible fills. Show net results and
sensitivity. Do not silently assume free execution or grant position-size authority.
