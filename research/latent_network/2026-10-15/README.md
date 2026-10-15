# Network propagation research — LP-NETWORK-08

**Status: implementation and timing checks complete; empirical result is not verified.**

This is an independent test of whether other industries' behavior adds forward information beyond an industry's own history and common market context. It is not another run of the earlier weighting-contrast or shock-response models, and it does not contain their unpublished work.

## What is being tested

The source is the existing August2026-vintage French49 industry daily return archive. Historical portfolio construction is preferable to selecting today's surviving companies, but these are reconstructed research portfolios—not original release-time data, tradable ETF prices or order flows.

Each Friday, the study forecasts the cross-sectional rank of the next5- or21-session benchmark-relative return, with entry delayed to the following session's close. Annual ridge models use only complete historical labels from the previous20years.

The baseline contains own price/relative strength/trend/volatility, market/size/value context, other-industry aggregate behavior, and its own factor-residual history. This isolates the value of *which other industries are connected*, rather than merely providing new residual or common-factor inputs to the candidate.

Two network candidates use only data before the corresponding calendar year:

1. **Correlation neighbors:** the topfive positive residual-correlation neighbors per industry.
2. **Directed neighbors:** topfive positive lead-asymmetry scores based on five-session residual returns and five-session lag.

Four fixed controls relabel the directed graph's industry identities while retaining its topology and weights. Every candidate/control uses the same model class, features, labels and evaluation observations. The graph formula, horizons and controls were fixed before this experiment's outputs.

Statistical edges do not identify supplier/customer links, investor ownership, causal information flow or capital transfers. A good ranking score would also not automatically demonstrate an early reversal probability. The protocol separately requires early-warning precision and conditional lead denominators.

## Verification already performed

Thirteen focused tests passed. They cover prefix-only factor fitting, graph orientation on a known constructed leader, graph-date boundaries, fixed-label permutation invariants, source-prefix invariance, delayed entry, missing outcomes, centered ranking targets, training-only scaling and suppression of unreliable short-sample inference.

The local empirical process reached the final2026 annual fit for both horizons. A subsequent attempt to inspect its aggregate output was blocked before dispatch. **No numerical result, promotion verdict or completed-output claim is made.** No new experiment is a substitute for reading that original result; no duplicate was launched.

See `BOUNDARY_STATUS.json` and `FRONTIER.md` for the exact unresolved run and original method-review worker. `VALIDATION.json` contains source hashes and test scope. `SOURCES.md` distinguishes literature support and contrary evidence from this implementation.

## Reproduce the method

Python, NumPy, pandas and SciPy are required; observed versions are in `ENVIRONMENT.json`.

```sh
python3 -m unittest test_network_study -v
python3 network_study.py --inputs /authorized/hash-matched/archives --out /new/empty/run
```

The two input ZIPs and exact expected hashes are in `SOURCE_MANIFEST.json`. The script rejects changed inputs and an existing result directory. Existing `private/run01` is the original active/retained run and must not be overwritten or duplicated as a result-access workaround. The command above documents reproducibility, not authorization to bypass an access boundary.

Raw source archives and per-date predictions are ignored/private. Publication contains only this independent protocol/source/tests and their verified state. No production model, schema, collection service, ranking, alert, sizing or trading authority is created.

## Scientific acceptance remains open

The study must beat the strong baseline, its prespecified ranking-error and correlation thresholds, multiple-testing correction and era/early-warning checks. Directed links must also beat the strongest fixed relabeled-network control. Short2026 data remain descriptive; earlier tests already examined broad historical periods, so this is adaptive research rather than untouched global validation.

A permitted review of the retained original output is the next scientific dependency. The full quote-recovery hypothesis additionally retains its separate source-semantic and independent-day requirements. No result of this study is asserted to settle that different question.
