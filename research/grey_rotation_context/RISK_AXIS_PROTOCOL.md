# Incremental VIX/VVIX risk-axis diagnostic - frozen before new outcome inspection

This is a narrow adjunct to the rotation-context implementation, not a competing grey-dot trough study. The local team owns its sector-fund/grey-dot tests. This diagnostic asks whether actual options-implied VVIX level and moving-average behavior add forecast information beyond each ETF's own realized risk and VIX. It computes no grey-dot strategy return, opens no 2020+ Rotation Core outcome window, and creates no gating authority.

## Inputs and scope

Reuse the eleven already qualified phase2 ETF prepared-price panels (QQQ, SPY, IWM, XLB, XLE, XLI, XLK, XLP, XLU, XLV, XLY), solely through 2019-12-31. Source identities are captured before use; retained panels are current-vintage reconstructions, not original publication vintages. Do not introduce XLF or replace failed instruments. Read the incumbent Macro data/cboe/vvix.parquet and data/yahoo/_VIX.parquet; inspect exact schema and source semantics. No download, backfill, synthetic VVIX or source splice. If an input is unavailable, report the diagnostic blocked rather than replace it with realized VIX volatility.

Use the explicit ETF session index. Lag VIX and VVIX one ETF session, never forward-fill a missing observation. Historical publication instants are not established by this lag assumption; disclose it. Actual live integration still needs source-known-at validation. The input source stores are read-only; anomalous/quarantined values are not released by this experiment.

## Models, horizon and common target

Four fixed models: own-risk HAR baseline; baseline plus VIX; then plus VVIX level; then plus VVIX moving-average terms. Own-risk features are log trailing mean positive variance over 1,5,22 sessions. VIX features are log lagged level, log(lagged level / 20-session mean), and log(20-session mean / its five-session-lagged value). VVIX level is log actual VVIX. Its two trend additions use the same mean20 ratios as VIX. A VVIX/VIX ratio is deliberately not substituted for these separately identified components.

Fit linear ridge regression to log future mean variance at horizons 5 and20 sessions. Fixed slope penalty .01 on the mean-square objective, unpenalized intercept, training-only standardization and fixed +/-5 standardized-feature clipping. Apply the training-only exponential-residual smearing factor on output. No hyperparameter search, per-asset threshold or best-window selection. Refit every63 observed eligible origins with a minimum504 and maximum1260 matured training rows; a training label enters only when its whole horizon ends by the fit origin. Failed fits are unavailable, not silently replaced.

Evaluate origins 2013-01-02 through the last origin whose entire target matures by2019-12-31. Primary target is the already defined positive overnight-plus-range variance proxy. Score the same forecasts against squared total-return log changes as a separate secondary proxy. Neither is perfect latent volatility truth. Restrict comparisons to the identical observable rows for all four models, report common support and missingness, and retain all eleven instruments.

## Inference and interpretation

Three adjacent contrasts x two horizons x two targets =12 declared tests. Lower QLIKE is better. Average paired loss differences across the available ETFs on each common date, then a calendar-block bootstrap with63-observation blocks,2000 draws and seed20261114. Report raw effects, pointwise intervals, date counts, instrument counts and a Holm adjustment across all12 contrasts. The ETFs overlap and are not independent trials. Report per-asset estimates without choosing winners from them.

This remains retrospective exploratory research relative to the wider programme. Earlier projects have seen market history; a new file does not create a pristine holdout. A positive incremental risk result does not establish a profitable directional entry, a durable trough, or sector selection. A null result does not justify withholding an already measured descriptive source. The actual grey-dot/sector inference must be tested in the existing team's registered panel with common-date and issuer/sector controls.

Implementation tests and known-answer synthetic decompositions are performed separately and never labeled market evidence. No thresholds, sample replacements, forecast arms or primary ruler may change after results without a distinct dated amendment preserving the original outputs.
