# LP-CLOCK-04: observation-aware pause research

Read `REPORT.md`, then `SUMMARY.json` and `BOUNDARY_STATUS.json`.

**Scientific verdict:** the pause candidate does not improve conditional direction. It improves joint/availability metrics versus the fitted baseline, but the simple training-frequency constant remains better. No forecast promotion. The new verified measurement distinguishes filtered silence from other observed displayed executions.

## Files

`clock_study.py` contains the frozen fixed-clock, two-part model. `PROTOCOL.json` and `PRE_RUN_QUALIFICATION.json` document the pre-run choices and boundary correction. `RESULTS.json` holds aggregate metrics, source/code identities, coverage and per-ticker differences. Full origin-level predictions remain private.

`clock_reader.py` exposes historical execution visibility and leaves all inferred direction, inventory and forecast fields null. `CLOCK_OBSERVATION_EXAMPLE.json` is the actual eight-name 14:00 New York read from October5,2026.

`recovery_incidence.py` adds descriptive competing-outcome calculations for the existing synthetic `RecoveryBook`. It handles unfinished follow-up and displayed-level depletion without claiming real-book reconstruction or calibrated forecast probabilities. The original real-book adapter remains fail-closed.

`VALIDATION.json` records the 45 new passing tests and actual checks. `BOUNDARY_STATUS.json` records the unresolved original GLM return and blocked legacy timestamp-impact audit; neither was retried or routed through another tool. `PRIVATE_MANIFEST.json` records private result identities without redistributing the series.

## Run the tests in the repository

Dependencies: Python, NumPy, pandas and SciPy. The new research directory uses the adjacent `event_recovery/event_study.py` solely for its already qualified CSV loader, symbols and clock, and the adjacent `event_recovery/book_recovery.py` for synthetic book fixtures. The older label-search implementation is not called by the new experiment.

```sh
cd research/latent_pressure/2026-10-14/clock_pause
python3 -m unittest test_clock_study test_recovery_incidence test_clock_reader -v
```

## Read a historical cutoff

Only the previously qualified input SHA is admitted; this is not a generic new-data importer.

```sh
python3 clock_reader.py \
  --executions ../event_recovery/private/full_scan/executions.csv.gz \
  --at 2026-10-05T14:00:00-04:00
```

The empirical script requires the same authorized archive-derived input. It rejects an existing output directory so that prior results cannot be silently overwritten. Exact frozen source is retained at commit `d072e53e8`; the original model was run once after tests, and the result includes its full source digest.

```sh
python3 clock_study.py \
  --executions ../event_recovery/private/full_scan/executions.csv.gz \
  --out private/a-new-recorded-run
```

No source acquisition, production connection or trading occurs. A new dataset or historical day requires its own source qualification and separately recorded study; this command does not grant it. The previous experiments and their raw outputs remain unchanged.

## Interpretation and limits

NO_STANDARD_OBSERVATION is about the selected price stream, not a flat underlying market. Other L activity does not reveal aggressor side or an institution. Conditional-direction loss is reported separately from the four-class data/price score. All blocks come from one previously studied day, so no independent-day or population validation is implied.

The nanosecond scalar-query defect was repaired and tested in this new pipeline. Its exact effect on older event-study labels has not been audited because that requested audit was blocked. Do not claim that older labels were unaffected.

Data provided for free by IEX; use is subject to https://www.iex.io/legal/hist-data-terms . Raw captures and per-origin prediction/price series are not included in publication.
