# V26 — causal labels, whole-cohort utility, and independent-review adjudication

Research continuation of Mastermind PR #1338. **No independent strategy-performance validation or live-trading acceptance is claimed.** This phase adds an executable offline accounting component and synthetic falsifiers, not another indicator, collector, calendar, model, or control plane. All v2–v24 source/results remain unchanged.

## Recovered facts

The requested handoff at `7ec0207a5870e8c467b7185afbdcde97c38ef314` was superseded in source by `a914583df5272b28037ed5230bce4b9e69c93c59`. That existing v25 commit changes financial evidence representation, not the D8 identity guard. Hosted CI **38343549349 completed SUCCESS** on a914583. The failed prior run 38336822737 remains historical evidence, not the current candidate's status. No unchanged backtest or guard suite was repeated in this recovery. CI for a later enclosing commit must be observed separately.

The interrupted mini4 clone, original PID 84436, ended with exit 128 after a GitHub connection failure. It did not apply a source change. Remote private research directories were not re-censused after the earlier refused census; their prior custody/hashes remain the retained evidence, not newly verified availability.

## New source-level causal defect, not a refitted result

Frozen `early_failure_v21_v24/walkforward_v22.py`, blob `189fa70a5cf0603348884abea2f12af3e0cd6cf0`, selects training rows with `r['week'] < current`. It carries no paired-path end or label-availability time into that selection. An earlier entry week is insufficient: its 52-RTH-hour continuation can finish after the next model fit. The label must wait for **both** the benchmark and hypothetical intervention paths, plus actual data availability.

A synthetic Friday-entry / Monday-fit example passes the old week comparison but is rejected by `mature_training_labels`. Separate tests reject late receipt availability, future features, naive clocks, equal-time availability, and duplicate labels. This demonstrates a missing guarantee; it does **not** measure how many of the old 90 forecastable rows actually leaked or compute corrected old performance. Preserve the negative v22 results as retrospective exploratory evidence, not verified causal out-of-sample forecasts. No threshold, ridge penalty, clipping level, or inspected historical year was retuned.

## Economic accounting

`utility.py` requires exactly one row for every sealed original episode. Missing, duplicate, and extra episodes fail. Resolved non-actions and verified no-fills have zero incremental return only when the unchanged baseline controls/path are established. Unknown fills stay UNRESOLVED. They either carry explicit stress-inclusive bounds or prevent a finite whole-cohort mean/bound; they are never dropped or treated as zero.

For each resolved episode, after additional execution cost:

`increment = intervention net return - baseline net return`

The primary economic bridge is exact, including returns crossing zero:

`increment = loss reduction + profit increase - profit surrendered - loss increase`.

The separate baseline-sign components identify improved losing episodes, improved winning episodes, harmed winning episodes and worsened losing episodes. These are not interchangeable with a binary classifier's accuracy. A loss converted into a profit is split into avoided loss and new profit rather than mislabelling the entire improvement "losses avoided".

Additional adverse sell cost is `remaining fraction sold * sale/entry ratio * extra bps / 100`, in percentage points of the original position. Baseline fees must already be included; do not charge them again. The bound envelope is **not a confidence interval**, and a positive bound is not source, model, or trading acceptance.

A synthetic falsifier has eight +1 pp improvements on originally losing episodes and one -12 pp lost winner: net -4/9 pp per original episode. High apparent exit accuracy alone does not satisfy the economic objective. This is a unit-test fixture, not an observed SOXX performance result.

`overlap_components` detects connected overlapping exposure intervals across symbols. It deliberately does not manufacture independent trials from correlated names, nor claim non-overlapping components are statistically independent. Exchange-calendar and horizon construction remain upstream-owned.

## Independent review: consumed, not blindly accepted

Original Fabric root and parent: `soxx1338-web-resume-20261013`.

- `soxx1338-ci-review-20261013a`: terminal, rc 0, previously ACCEPTED by reviewer. Reuse; no replacement or repeat acceptance.
- `soxx1338-cycle-review-20261013a`: terminal, rc 0; original route pool `minimax`, host `ubuntu2`. Its 13,467-byte retained result was consumed. SHA256 of the reviewed CLI result stdout: `0d944de7f24fddcae783a0279939562c0f1d0a547dcb32531a4b6b6681a74e4c`. The mixed return remains NOT_ACCEPTED wholesale.
- `soxx1338-accounting-review-20261013a`: original `bailian` / requested `qwen3.8-max`, host `ubuntu0`, lease and launch recorded; later transport polls failed. Current worker/result state is UNKNOWN. Same-carrier `observe-run` returned REFUSED / `original_run_observation_unconfirmed`. Freeze this original task; do not relaunch, change IDs, or infer failure/termination. No new worker was submitted by this phase.

Adjudication of the cycle review:

| Finding | Disposition and evidence |
|---|---|
| F1: break-even requires acting on every opportunity | REJECT that assumption. `p*b-(1-p)*h-c=0` applies to the contemplated action-conditional payoff mix, whatever its coverage. ACCEPT the warning that old forced-action means are not transferable to a selected future policy. No reviewer-invented outlier deletion numbers are treated as evidence. |
| F2: positive/negative deltas mix original winners/losers | ACCEPT as a reporting refinement. The new economic bridge and baseline-sign decomposition make the distinction explicit without altering v23. |
| F3/F5/F15: no untouched/PIT/quote/registration proof | ACCEPT existing limits. A Boolean registration assertion is not publication-time proof. Chronological entry ordering is not outcome maturity. |
| F4: unknown and policy-closed can be conflated | ACCEPT the generic schema weakness in v23's `closed_before_checkpoint`. Do not assert it changed the old sample's numbers without event evidence. New UNRESOLVED and non-action states remain separate. |
| F6: v24 mean excludes all ineligible non-actions | REJECT. v24 appends resolved replay rows regardless of `checker.checked`. Published first all-cohort cell has `n=91`, `discretionary_sales=29`, mean `0.141368`. Future source gaps still require explicit whole-cohort bounds. |
| F7/F14: validation counts prove performance | Only arithmetic/source checks, not independent market evidence. 120 stress cells are 24 five-point slippage sequences, not 120 independent trials. Retain previously accepted replay evidence without rerunning it. |
| F8: divide 91 by symbols, checkpoints and modes | REJECT this sample-size calculation: checkpoint/mode views reuse episodes rather than partition them into independent cells. Effective information is nevertheless limited by overlap, clustering, and regimes. |
| F9/F11: tune ridge grid or symmetrically trim the old year | REJECT as a requirement. It conflicts with preserving the inspected sample. Leave-largest-benefit-out is deliberately a fragility falsifier, not an unbiased estimator. |
| F10/F12/F13 | A leave-week-out ratio can be undefined if a sign disappears from the remainder; report this limitation, not an invented corrected range. Week clustering captures same-week cross-asset dependence but does not prove long-horizon independence. Compare signal-conditional and forced-action payoff distributions separately. |
| Proposed exclusion of unknown/no-fill cases; arbitrary 40-event/25%-no-fill rules; optional composite | REJECT. These can change denominators or introduce unsupported thresholds/model selection. The new component withholds unsupported claims rather than using those rules. |

The independent reviewer is useful adversarial input, **not independent performance validation** and not authority to modify safeguards or accept trading.

## Frozen next-data protocol (not a running collector or a power claim)

The next independent observations must come from incumbent source owners, with qualification completed before outcome scoring. Reserve October 14, 2026 through April 13, 2027 ET as a prospective entry window, with full original horizon follow-through. If publication occurs after the start, no earlier observations may be labelled prospective; revise the window before observing its outcomes. This window is a design choice, not a guarantee of enough events or any scheduled capture.

Copy the original 3H parent-turn entry, 1.5% risk stop, 25%-at-2% partial and 52 observed RTH-hour benchmark unchanged. Evaluate the existing single-check below-entry alternatives at 30 minutes and 3 hours against no additional exit. SOXX must be reported separately; additional instruments are transfer evidence, not a substitute for independent SOXX time evidence. Do not choose the better checkpoint after viewing outcomes. Keep the original v24 delay grid `[1,2,4]` and added-slippage grid `[0,10,25,50,100]` visible; these remain hypothetical stress scenarios until quote execution is qualified.

Predeclare the independent-data analysis, multiplicity treatment, dependence model, economic margin, and stopping rule before reading outcome results. The two checkpoint claims must not be treated as one unselected test. Sample size/power and a confidence procedure are **not established by this accounting module**. Do not choose an arbitrary event minimum, count correlated symbols as independent, or declare GO because a synthetic test passes. Use complete outcome availability for any learned model; otherwise abstain and keep the original-cohort accounting. No v22 model is promoted here.

BOATS and RTH/full-session comparisons remain held pending source qualification; do not splice venue-native BOATS OHLC and daytime reference bars into an assumed executable 24-hour tape. Retain the existing four-arm matched-clock plan and equal economic horizons.

## Source-owner frontier

Existing Macro #8698 comment `6137771857` already requested owner-qualified SOXX receipts or the exact remaining gate. It records the 2026-10-13 03:41 UTC census through canonical `require_external_root`, `validate_receipt`, and `receipt_identity`: two valid historical boats-bars receipts (AAPL, AMD), SOXX zero, invalid zero, not truncated. Reader blob `73c100cc9ab91f443210a1063c28f7390416f020`; metadata report SHA256 `c4e4fe29666571d6b79adf0847df4ea26078463201ac47d30cc54304165111d6`. No subsequent owner response was present when recovered. Reuse the original request, not a duplicate acquisition task.

No vendor authentication, credentials, raw licensed data publication, new collector, quote hub, scheduler, live order, sizing, deployment, or acceptance was performed. The earlier provider/producer refusals remain in force. Tiingo's official BOATS WebSocket documentation distinguishes venue-native live top-of-book/trade updates from REST overnight OHLC history; neither documentation nor ACTIVE entitlement supplies historical SOXX receipt or fill proof.

## Local proof and use

`python -m unittest discover -s tests -p 'test_soxx_v26_prospective_accounting.py' -v`

31 distinct synthetic tests passed; the first 27 were observed failing before implementation. Four additional tests drove immutable bound storage and zero-crossing accounting. Source and test compilation passed. These checks do not rerun v2–v24 and contain no market rows. The component is an offline library; it is not wired to a collector, model, Terminal, or broker. Source/API consistency checks cannot independently authenticate caller-supplied evidence.
