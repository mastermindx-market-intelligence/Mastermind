# Numerical repair protocol: seed-free forecasts with honest approximation limits

This is a post-primary, post-extension repair prompted by the prescribed seed audit, not a parameter search to improve returns. The 256-path H20 forecast differed from a 16,384-path reference by more than 200% at one preselected XLV origin. All original forecasts/results remain retained. No original fit is silently replaced.

## Deterministic power-state derivation

For the current empirical innovation/sign-pair assumption, define X=mu^delta, p=1/delta, and A=alpha*(epsilon*(1-gamma*sign))^delta+beta. Then X_next=omega+A*X. With successive empirical draws independent of the current state:

m1_next=omega+E[A]*m1
m2_next=omega^2+2*omega*E[A]*m1+E[A^2]*m2.

Initialize m1=X and m2=X^2 at the known next-session conditional variance. These two moment recursions are exact under that assumed finite empirical transition distribution. The desired E[mu]=E[X^p] is exact at p=1 or p=2. For other admitted p in [0.5,2], use the separately named lognormal two-moment approximation:

estimate=m1^p*(m2/m1^2)^(p*(p-1)/2).

Do not call this fractional-moment closure exact. Report analytic bounds derived from Jensen and moment log-convexity:
- 0<p<1: m1^(2-p)/m2^(1-p) <= E[X^p] <= m1^p.
- 1<p<2: m1^p <= E[X^p] <= m1^(2-p)*m2^(p-1).
- p=1 or p=2: exact corresponding moment.

Average the daily estimates/bounds for horizons 1/5/20. The bounds constrain the conditional expected forecast under the empirical recursion; they are NOT market prediction intervals, data guarantees, or bounds on an actual future market path. Record the relevant moment coefficients, approximation width, nonfinite failures, and large-bound cases. E[A]<1 alone is not sufficient for E[mu] stationarity when p>1; E[A^p] is separately reported. No empirical coefficient proves real-market stationarity.

Reconstruct these forecasts from the original saved fit records and training innovations without refitting. Compare unchanged H1, both loss targets, originally fixed utility rules, and predetermined numerical origins against larger-path references and the analytic bounds. Preserve approximation uncertainty even when the deterministic result looks favorable.

## Exact linear control

Add exactly one fixed-power control: delta=1, with the same QML objective, training window, schedule and two initial omega/alpha/beta/gamma starts as the existing model. This is an asymmetric multiplicative-error variance model with exact multi-step empirical conditional means, not the original free-power APMEM. It tests whether eliminating power-estimation and simulation complexity retains useful accuracy. No power grid, performance-based parameter selection, or extra feature search is authorized by this protocol. Parameter bounds remain unchanged for the four fitted parameters; fit failure is unavailable, never silently substituted.

## Evaluation and retained outputs

Evaluate the deterministic approximation and the fixed-power model against the preserved APMEM, EWMA, HAR and blend results on all eleven admitted assets plus the pre-2010 SPY stress panel. The optional fixed half-model/half-HAR-IV combination uses the already fitted IV forecast and unchanged weights. Reuse both original targets/horizons and existing exposure rules; do not optimize portfolio thresholds. Report numerical stability separately from forecast skill and economic utility. Every new comparison is exploratory after prior evidence.

## Consumer clock correction

Parameter-fit cutoff and current filtered-state date are different facts. An older scheduled parameter fit is valid when the state/features have been updated through the declared origin. The research consumer must check actual input capture and forecast computation clocks, state origin, and every parameter-training cutoff independently; it must not require all fits to finish on the final origin session. Unknown provenance remains an explicit refusal. No change grants rank, sizing, trade or live-alert authority.
