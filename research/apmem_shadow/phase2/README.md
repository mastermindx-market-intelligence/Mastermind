# Volatility forecasting, confluence, and loss-control research

This directory is an original research implementation. It is not the external creator's private strategy, an automatic trading feature, or a new data/control plane. The Chairman's continuing mission asks for stronger volatility forecasting and separately evaluated returns, risk-adjusted returns, and loss prevention.

## Reproduction

Use the existing repository research dependency profile. The recorded empirical runtime is NumPy 2.4.6, pandas 3.0.3, SciPy 1.18.0 and PyArrow 24.0.0; principal mechanical tests also run on the separately recorded container versions. Do not claim bit-identical optimization across environments.

```sh
python -m unittest discover -s tests -p 'test_apmem_phase2*.py'
python -m research.apmem_shadow.phase2 --prices-root /licensed/snapshots --options-root /licensed/options --output /new/output --symbols QQQ SPY IWM
python -m research.apmem_shadow.phase2.run_followup --study-root /retained/study --output /new/followup
python -m research.apmem_shadow.phase2.run_extensions --study-root /retained/study --output /new/extensions
python -m research.apmem_shadow.phase2.run_moments --study-root /retained/study --output /new/moment-repair
```

The primary CLI expects `<SYMBOL>_yahoo_raw.parquet`, with normalized economic-session index and explicit OHLC/distributions/actions. Optional `<SYMBOL>_gex.parquet` is supplied by its existing owner. It does not acquire credentials, purchase data, collect feeds, or start a scheduler. Existing output directories are refused rather than silently overwritten. Each scientific extension consumes the original retained inputs and hashes. The full eleven-asset follow-up requires the documented `results/` and `sector_results/` tree. The earlier stress extension uses its separate source receipt.

Five ordinary-split sector panels are admitted only by `corporate_actions.qualify_constant_share_units` after issuer-event and independent-price checks. The adapter does not rewrite already-adjusted prices or cash distributions. XLF's in-kind XLRE distribution is not silently treated as an ordinary split. Raw vendor observations and the public creator's full snapshot are not redistributed here.

## What is being compared

Forecasts predict identical 1/5/20-session targets: a distribution-aware overnight-plus-intraday-range variance proxy, and separately squared total close returns. These are noisy OHLC/return proxies, not measured intraday integrated variance. The primary fixed models are the incumbent estimator, simple controls, original APMEM, direct-horizon HAR and a fixed/adaptive blend. Options attribution and subsequent numerical repairs are explicitly post-primary exploratory work.

`evaluation.portfolio` uses actual drifted-weight rebalancing, cash distributions, costs, cash-rate sensitivities and next-open execution. Raw return, Sharpe, drawdown, expected shortfall, upside capture and exposure are not interchangeable objectives. A hindsight exposure-matched static comparator is a diagnostic, not a deployable strategy.

`calibration` and `followup.execution_quantiles` use only matured residuals. A close-origin forecast for an open t+1 to open t+2 holding interval must not learn from that still-unobserved interval. Nominal 1% or 5% tail coverage is not guaranteed in nonstationary markets.

## Numerical methods and limits

The original 256-path APMEM multi-step method is retained for reproducibility but showed material seed sensitivity. `moments.py` provides deterministic exact first/second powered-state moments, analytic bounds on the assumed conditional mean, a clearly identified fractional-moment approximation, and a separately fitted delta=1 control with exact multi-step means under its empirical transition assumption. Neither mathematical bounds nor optimizer success certify real-market forecasting adequacy. See `NUMERICAL_REPAIR_PROTOCOL.md` and the retained numerical evidence before selecting a method.

## Consumer boundary

`consumer.research_context` separates parameter-training cutoffs, latest filtered state, input observation and forecast computation clocks. It emits research-only context or explicit abstention. It never grants `may_rank`, `may_size`, or `may_trade`. Caller-supplied clocks are not authenticated by the pure checker. An actual reconstructed research-context run is not a historically published forecast, a live collector, or deployed Prophet integration.

## Evidence and protocol order

`PROTOCOL.md` precedes the first new fits. Corporate-action, follow-up, scale-control, extension and numerical-repair protocols record their later scopes and prior evidence exposure. `evidence/` retains aggregate outcomes, not only winners. Original scenario results are preserved when a scientific defect is discovered. More scenarios and fitted windows are not more independent samples; correlated ETFs, overlapping horizons, multiple comparisons and current-vintage inputs limit inference.

No changes to the incumbent live ranker, existing registered Prophet experiments, position sizing, orders, production service or data authority are made by this directory.
