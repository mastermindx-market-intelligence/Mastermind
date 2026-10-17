# Novel latent-pressure follow-up

Start with `NOVEL_RESEARCH.md`. This is further original problem-solving after LP-ETF-01, not a replacement for the initial report.

The research develops ordered recovery/fatigue, pressure-pause survival, anonymous program ensembles, event/size disagreement, forced-flow resistance, two propagation graphs and event-response fingerprints. A hedging-explanation envelope is an untested additional model-checking proposal. Global novelty is not asserted.

## Executed evidence

`PROTOCOL.json` and `session_pilot.py` were frozen before the new results. `SESSION_PILOT_RESULTS.json` and `RESULT_SUMMARY.json` record the negative two-stock, five-session session-component test. Data are later-vintage, convenience-sampled and explicitly NOT Data OS or PIT admitted. Raw data and per-date predictions are excluded from publication.

`prototype_checks.py` executes constructed order/recovery/prefix examples; `PROTOTYPE_CHECKS.json` records successful checks. These are mechanism demonstrations, not a market-validated simulator or alpha. `REVIEW_ADJUDICATION.json` preserves the useful and rejected parts of the external mathematical audit.

## Reproduction

For constructed checks, run `python3 prototype_checks.py`; only the Python standard library is needed. This writes the small check result beside the script.

The empirical script requires the original authorized data and the parent directory's `pilot.py` for its frozen fitter/metrics. Its input census was private. To reproduce in an isolated copy, create `eod_census_private.json` as a list derived from `SESSION_PILOT_RESULTS.json` -> `sources`: each entry has `symbols:[ticker]`, `rows:rows_used`, `file_sha256:file_sha256`, and `ref` equal to the authorized EOD root plus `relative_path`. There is only one selected snapshot per ticker, so the rows field serves only the deterministic selection. The original M2 input root used by the final hash check is documented in `session_pilot.py`; parameterizing paths on another machine changes the reproduction source and must be recorded. Do not edit the old data flags or pretend changed hashes are exact replication. NumPy, pandas, SciPy and PyArrow are required. The script refuses an existing private_results directory.

No post-result model/window optimization was performed. No deployment, schema changes, purchases, orders or sizing authority were introduced. Original carrier: Mastermind PR1470; original root remains latent-pressure-research-20261014-chatgpt4-001.
