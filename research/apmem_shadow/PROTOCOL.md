# Frozen original APMEM/options experiment v1

Operation: apmem-shadow-20261113. This protocol is committed before fitting or evaluating the newly located independent OHLC/options panel. It is not a claim that the researchers have never seen overlapping market history. All historical results are retrospective, chronological pseudo-out-of-sample diagnostics, never prospective validation.

## Inputs and rights

Use the incumbent approved Massive daily OHLC and ThetaData-derived index-GEX history. Preserve original-byte digests, observation date, retrieval time, adjustment basis, reconstruction status and missing first-availability clocks. Do not substitute the creator's signals or select thresholds to match their marker dates. Do not publish raw vendor records to this public repository. The existing commercial-rights attestation covers these providers; it does not prove point-in-time history or dealer inventory. The GEX source assumes long calls/short puts; its inferred sign is not observed dealer positioning or a bullish probability.

## Model and baselines

Original implementation of the public APMEM(1,1) recursion: mu[t+1]^delta = omega + alpha * (v[t]*(1-gamma*sign(r[t])))^delta + beta*mu[t]^delta. Scale positive variance proxies by the training-only mean. Fit Chi-square QML (mean log(mu)+v/mu, constants omitted) with two deterministic initializations; choose by training objective only. Bounds: positive omega, alpha and beta; gamma [-0.95,0.95]; delta [0.5,2]. Record optimizer failure and bound hits; do not silently substitute a successful forecast. This bounded specification is our research model, not NYU's exact estimator or the creator's private system. Do not infer stationarity from alpha+beta alone.

The high-low Parkinson proxy receives the causal overnight correction documented by NYU. Its published lambda is 0.05 in a recursion with (1-lambda) on the newest observation. Evaluate that literal convention and a separately labeled engineering comparator lambda=0.94; neither is selected using test returns. Zero/malformed ranges or missing bars are rejected, not silently imputed. Floors must be reported. Forecast only one session ahead; taking a root of a powered multihorizon expectation is not generally an exact mean-variance forecast.

Minimum training: 252 sessions; rolling window: 504; refit every 63 sessions. Fit on the origin and earlier observations only; subsequent states update from observed rows only. Compare on identical valid rows with EWMA(0.94), rolling-20 variance-proxy mean and expanding training mean using QLIKE and squared-error diagnostics. Retain both preprocessing variants and unsuccessful fits.

## Fixed directional ablations

These are hypotheses, not recommendations. A volatility-relief event requires the current next-session forecast to exceed its previous 252-session 80th percentile (minimum 126 prior forecasts), and to decline from its preceding value. Options relief uses the previous session's reconstructed GEX above its preceding 20-session median and its IV30 below the session before it. No missing options value is neutral or bullish. Price relief requires a close at least 5% below its trailing-20 maximum and a positive daily return. Evaluate price-only, volatility-only, options-only, volatility-plus-options, and all-three events without selecting a winning variant.

A separate hypothetical long/cash replay enters at the next session OPEN, holds 20 open-to-open intervals, ignores re-entry while occupied, and exits at the following open. At the evaluation endpoint, retain an explicitly censored final episode rather than treating it as matured. Repeat with an additional one-session entry delay. Charge 5 and 20 basis points per one-way exposure change, including initial entry and terminal liquidation. Cash earns zero. Raw-price results exclude dividends, tax and financing; no short strategy is authorized by this protocol. Baseline buy/hold uses the same dates, opens and cost convention.

Report event count, independent nonoverlapping episodes, exposure, net performance, closing/open-mark drawdown scope, year/episode concentration, and timing sensitivity. No selected positive event fractions become calibrated success probabilities. Small event samples and uncertainty are grounds for HOLD, not permission to retune. Any later specification change requires a distinct version and disclosure of the already-inspected outcomes.

## Consumer and qualification

Provide a strict shadow-only machine consumer with instrument, source digest/version, observation/availability/capture clocks, fit cutoff/completion, units, reconstruction and staleness checks. Actual retrieval timestamps remain actual; never backdate them to simulate historical availability. Historical simulation is a separate evidence mode. Missing or stale inputs, unknown clock lineage, mismatched instruments/units, or future inputs produce explicit abstention. This component emits research context only, with no live rank, trade, sizing or auto-promotion authority.

Acceptance requires deterministic causality/failure tests, actual-data evaluation and a real invocation of this research consumer. Production Prophet integration, any recurring collector, and performance promotion remain separately evidenced obligations. An offline consumer or green unit tests must not be described as a deployed Prophet feature.

## Delegation constraint

The current connected Fabric adapter reports unavailable, and its configured native script is absent. No worker request has been submitted and no worker START is claimed. Continue independently authorized source/research work under NO_ELIGIBLE_PRE_EFFECT_WORKER while diagnosing the original connector. Do not restore an obsolete adapter, invent an execution identity, launch raw native labor, or duplicate a denied/uncertain effect. An eligible distinct exact-head review may be commissioned through an independently permitted existing route.
