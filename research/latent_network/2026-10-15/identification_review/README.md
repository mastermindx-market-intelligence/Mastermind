# Network information attribution: reproduced confound and executable control

## Decision

**Do not attribute a pending LP-NETWORK-08 gain to new peer information until redundant-basis and penalty sensitivity are checked.** This is not a verdict on the unread real-data result. The original experiment, protocol, graphs, predictions and source remain unchanged.

Reviewed source: `network_study.py` at `566e0db2f3ef3913c8645ce93d2d8ed62f2b3f71`. This addendum is an independently executed mathematical/source review, not a rerun or an alternate access path to restricted outputs. Its constructed observations are not market data or trading performance.

## Source-derived issue

Before per-column clipping, the published construction has the exact identity:

`peer_gap21 = peer21 - ownres21`

The baseline includes `ownres21`; each network candidate adds both `peer21` and `peer_gap21`. Ridge penalizes the supplied coefficients separately with the same numerical lambda. Redundant columns therefore change the effective penalty on the baseline information. Equal estimator names and equal numerical lambda do not guarantee equal effective regularization.

In the one-feature standardized case, adding an exact duplicate `-x` changes the minimum penalty on effective coefficient b from `lambda*b^2` to `lambda*b^2/2`. No new information was observed. Separate clipping can introduce additional deterministic representation effects; the exact linear identity holds where clipping is inactive. The executed counterexample has no clipped observations.

This is not lookahead and does not automatically invalidate all forecasts. It limits the conclusion that a candidate-versus-baseline win measures genuinely new network information. The fixed relabeled controls remain useful; they are not declared invalid. The correlation candidate's gate also lacks a required placebo win, making an information-set control particularly important.

## Executed null-network demonstration

The demonstration uses the published ridge/scaler/clipping formula, the same 34 baseline and eight network-column slots, 4,018 synthetic training rows and 5,096 synthetic test rows in 49-subject cross-sections. All graph weights and peer observations are zero. The only nonzero extra feature is `peer_gap21=-ownres21`.

| Model construction | Mean rank IC | Rank MSE |
|---|---:|---:|
| Baseline | 0.9582721743 | 0.0483274906 |
| Redundant zero-information graph | 0.9706554160 | 0.0416252566 |
| Training-only orthogonal control | 0.9582721743 | 0.0483274906 |

The apparent IC gain is **0.0123832418** and MSE reduction **0.0067022340**, with no new information. They exceed the original point-effect cutoffs of 0.01 and 0.0005; the complete original gate, its uncertainty/era/alert requirements and actual market inputs were NOT tested.

The covariance and target-coefficient example was selected from a small deterministic grid to exhibit existence. No p-value or significance is assigned. High absolute scores are intentionally synthetic and should never appear as market performance. Exact evidence, environment and source hashes are in `EVIDENCE.json`.

## Implemented control

`ridge_identification.py` fits baseline and candidate transforms on training rows only, projects candidate columns onto the transformed baseline plus intercept, and retains only numerically material residual components. Those residuals are scaled without re-clipping, preserving their training orthogonality. The baseline penalty stays unchanged; the saved projection is reused for test observations.

All eight candidate components disappear in the null-network case. Controlled predictions match baseline predictions exactly in the executed sample: maximum difference **0.0**.

This removes linear redundancy in the supplied transformed inputs. It is not a cure for omitted factors, all nonlinear re-expressions, adaptive research, data-vintage problems, latency or causal identification. No claim is made that the control improves real market predictions. It has NOT been run on the restricted network study.

Fifteen passing tests cover the duplicate/half-penalty equivalence, null-network invariance, constants and linear combinations, train-only fitting, residual numerical tolerance, baseline coefficient preservation, rank-target invariance, and invalid inputs. These are principal-executed reference checks, not external independent approval.

## Separate target qualification

The source fits centered cross-sectional ranks of future benchmark-relative returns. Its secondary early-warning function grades future relative-return sign and conditional relative-strength confirmation. Those are different targets.

Relative log returns `[-.02,-.01,0,.01,.02]` and the same vector plus `.05` have identical centered ranks, although the positive-return count changes from two to five. A common negative shift can make all returns negative without changing ranks. The tests reproduce this.

Ranking forecasts and honestly labeled secondary diagnostics remain valid objects to investigate. A ranking gain alone cannot establish a calibrated reversal probability or a useful earlier warning. A separate event/sign target, matched false-alarm test and independent calibration/holdout are needed for that claim; the earlier source disclaimer is retained rather than silently upgraded.

## Reproduction

No market data, credentials or network access are required. Dependencies are Python, NumPy and SciPy.

```sh
python -m unittest test_ridge_identification -v
python demonstrate.py
```

The second command writes the constructed evidence beside these scripts. It never reads the original private experiment or invokes a broker. Published source hashes match the tested conversation-artifact source; a separate archive contains the expanded report.

## Continuity and effects

Original mission/root: `latent-pressure-research-20261014-chatgpt4-001`. Existing carrier: PR1518, child of PR1470. Protected pin: `78388ac29f7e54c9dfe7799a8e4769fb46d4aed6`. Scope is this addendum only. No original model source or output is replaced.

Studio Direct start_process and its liveness probe returned HTTP502 before any requested process receipt in this turn. That is a transport error, not evidence that earlier permission boundaries cleared. Authorized Remote Desktop Commander successfully verified m2studio for an independent options-source feasibility task. A later new options-data acquisition call was explicitly blocked before dispatch; it was not retried, rephrased or rerouted. No successful options dataset acquisition or empirical options test is asserted.

This source review and local constructed calculations are independent permitted work. No restricted network/shock result, original worker return, IEX book documentation or legacy real-data label audit was accessed. Existing uncertain return obligations remain unchanged. No new worker, purchase, live feed, watcher, production schema, ranking, alert, sizing or trading authority was introduced.

The addendum is published through GitHub's existing repository surface. The local M2 research branch must reconcile these new commits before a later push; never replace them with an older checkout. There is no custody transfer or duplicate empirical run.

## Next necessary empirical step

A legitimately permitted review of the retained original network result remains necessary. Inspect that exact output first; do not launch a new run to obtain a denied readout. A subsequent separately recorded information-set sensitivity comparison can remove deterministic gap duplication or use the train-only control. Direction-specific transmission still needs the previously identified reversed-direction comparison and protection against common exposures. Actual capital migration remains unobserved.

The broader early-warning mission remains incomplete. This addendum identifies and controls one reason an attractive result could be credited to the wrong information source; it does not claim to have discovered a profitable signal.
