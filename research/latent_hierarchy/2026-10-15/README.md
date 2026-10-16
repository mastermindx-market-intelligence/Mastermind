# LP-HIERARCHY-09 — historically defined child participation versus parent RS turns

**Research status:** the new experiment executed to completion with 7,854 forecasts. The runner's already observed terminal line reports `GATE False`. Detailed result inspection was subsequently explicitly blocked by the platform before dispatch. No Brier/precision/CI numbers are supplied without permitted verification; no market signal is accepted. No model was rerun or retuned after results.

This independent research child belongs to the original Mastermind Latent Capital Flow, Accumulation/Distribution & Predictive Rotation commission, under original root `latent-pressure-research-20261014-chatgpt4-001`. The parent research carrier is [PR #1470](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1470). This branch was based on published parent source `16152f1819256a702817d3b298511dff4a1d1845`, and does not modify or republish local-only earlier industry/shock commits or draft network PR #1518.

## What is genuinely different

The experiment directly tests whether **the participation of finer industries improves forecasts of a broader parent industry's 21-day relative-strength reversal**, rather than using today's surviving individual stocks, anonymous statistical connections, or same-stock equal/value weighting as a disguised breadth measure.

`mapping.py` reads French's official `Siccodes10.zip` and `Siccodes49.zip` and computes exact SIC-code intersections. The official ten-way `Other` is a catch-all. A fine industry is retained only if every SIC code in its published range belongs to **one** parent. Thirty-eight of 49 pass; eleven mixed categories are excluded without fractional weighting. Seven parent groups have at least two pure children: NoDur (7), Manuf (8), Enrgy (2), HiTec (4), Shops (2), Hlth (3), Other (10). Telcm and Utils have only one pure child and Durbl none. These subsets are not exhaustive parent holdings and must not be treated as exact accounting decompositions.

The observations are **reconstructed French industry research portfolios** at the August 2026 CRSP vintage, not live-saved point-in-time portfolio versions, investor positions, or investable ETF executions. The code applies parent and child returns observed through each historical close, but retrospective CRSP revisions remain a source limitation. Realistic operational availability and trade costs require separate proof.

## Frozen experiment

The protocol was committed at `10ec37f50` before inspecting outcome performance. `study.py` and the 16-test suite were committed at `534b74e5d`. The initial run exited **before the first model fit** because an object-typed comparison in its causal prefix guard could not be compared numerically; the exact dtype-only correction and successful tests were committed as `f38cd0272` before the single completed empirical run. No model, feature, target, hyperparameter or date range was changed by that correction.

The event is a **meaningful 21-day parent relative-strength sign reversal**, crossing to at least 0.5% in the opposite direction and remaining there for three consecutive trading sessions within a fully observed 21-session forward horizon. Eligible decision dates are actual Fridays; entry is modeled at the following close. Both positive-to-negative and negative-to-positive reversals are tested. Observations whose outcome cannot be completed are omitted, never called non-events. The current relative-strength magnitude must already be at least 0.5%, determined from prior data only.

The baseline includes the parent's 5/21/63/126-session relative history, own price/volatility/trend, its equal-weight-minus-value-weight contrast, market/size/value factors, peer broad-group rank and an explicit **known-rollover calculation**. The rollover control predicts how the 21-session relative-strength statistic would change if every future relative return were zero: already known old returns leave the window. This prevents mechanical dropout from masquerading as developing new participation.

The candidate adds observed SIC-pure child breadth, improving fraction, recovering laggards, fading leaders, group dispersion and parent-child disagreement. Candidate inputs are projected off the baseline using training rows only; a logistic offset locks the baseline coefficients and shrinkage. Redundant child information cannot improve the new model by reallocating baseline regularization. Four fixed seed controls scramble child memberships while preserving all selected children and each parent's child count. These are **identity-specificity diagnostics**, not causal economic propagation tests.

Models are fitted with frozen regularization at annual starts on up to 20 years of prior weekly decisions, requiring complete prior outcome labels before the new calendar year. Development: 2000–2009. Primary: 2010–2025. Reserve: 2026 descriptive only, and too short for standard 26-week-block inferential claims.

The predeclared gate requires paired date-block Brier improvement >=0.002 with positive lower CI, a +2 percentage-point matched-weekly-warning precision gain, positive gains in at least two of three primary eras, no worse logloss, and improvement larger than all four shuffled controls. Even a pass would justify **further research**, not live probability/rank/alert/trade authority.

## Evidence and source reproduction

- `PROTOCOL.json`: frozen hypotheses, targets, model controls and accept/reject criteria.
- `SOURCE_MANIFEST.json`: exact official original URLs, content names, sizes and SHA-256 hashes. Source archives are **private**, not copied into the public repository.
- `MAPPING_AUDIT.json`: deterministic source-backed pure versus mixed industry inclusion and parent coverage.
- `mapping.py`, `study.py`, `test_study.py`: executable taxonomy audit, analysis and 16 pre-run deterministic timing/identification tests.
- `PRE_RUN_QUALIFICATION.json`: prefit test evidence, source hashes, exact dtype repair and independent reviewer refusal.
- `FRONTIER.md`: exact durable effect state, blocked read and next permitted scientific step.

Run the deterministic tests with `python3 test_study.py` (NumPy, pandas, SciPy installed). The empirical code is documented with `python3 study.py --root .` and refuses to overwrite a prior result directory; this documentation is not authorization to **rerun the same original experiment to obtain a previously denied readout**. The single completed original remains at the authorized M2 research path under ignored `private/run01`. Full predictions, licensed/vendor source data and unverified detailed results are not public.

## Exact conclusion

The completed program printed `RESULT_AGGREGATED 7854 GATE False`. This is a verified terminal observation from the original run, **not** independent review of its detailed metrics. A later request to inspect those aggregates was blocked before dispatch; it was not retried or moved to another tool. No new alerting signal has been proven. The independent Fabric reviewer `lp-hierarchy09-crosswalk-review` terminated with rc 78 `canonical_source_unreadable` and produced no scientific audit or approval; no replacement worker was launched.

**Scientific decision:** no predictive promotion. Retain the study as a falsifiable, independently reproducible research method with an honest negative gate, limited to official revised portfolio returns and the selected pure-SIC hierarchy. The critical empirical question—does breadth add calibrated warning value beyond strong price/rollover controls—remains **not positively established**, and the numerical failure analysis is unverified until access to the retained original result is permitted.

No deployment, paid acquisition, source-admission change, instrument ranking, alert, sizing, trade or new control plane occurred.

### Post-run test-only verification

`POST_RUN_QA.json` records 17 passing cases. The later source-only QA added global SIC49 non-overlap and strengthened the previously vacuous model-offset invariance assertion. The frozen predictive implementation, source data, original private forecasts and `GATE False` receipt were not changed or rerun. This is not a new data/performance result.
