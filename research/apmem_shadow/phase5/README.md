# Independent sector-recovery research - phase 5

This is research code and retained evidence, not an active trading system. Read RESULTS.md before interpreting any favorable table. The principal owns the work; no T3 handoff or background service is required or claimed.

## Portable tests

The code uses Python 3.10+ with NumPy, pandas and SciPy. Full market-data replay also needs PyArrow and PyYAML for the pinned native-source snapshot. ENVIRONMENT.json records the actual numerical runtime; no repository-wide dependency or provider setting was changed.

From this directory:

```bash
python -m unittest discover -s . -p 'test_*.py'
```

The hermetic accounting, chronology, feature, regression and consumer checks run without network or credentials. NativeTests requires private hash-bound price fixtures and the exact Terminal source; it explicitly skips when those are absent. The actual numerical environment ran all 66 tests, including those native-data checks. A skip is not a native-parity pass.

## Full experiment order

Use the exact retained snapshot layout and hashes from INPUT_MANIFEST.json. Never replace missing source history with newly downloaded data while keeping the old evidence identity. The private inputs are not redistributed. The reserved January 2020-May 2023 interval must not be loaded into features, training or targets. Every runner refuses to overwrite an existing result directory; reconcile an original run rather than duplicate it.

```bash
python experiment.py --root "$STUDY_ROOT" --output "$STUDY_ROOT/primary_results"
python analyze.py --root "$STUDY_ROOT"
python robustness.py --root "$STUDY_ROOT"
python core_complement.py --root "$STUDY_ROOT"
python audit.py --root "$STUDY_ROOT"
python prediction_check.py --root "$STUDY_ROOT"
python phase_selection.py --root "$STUDY_ROOT"
python credit_check.py --root "$STUDY_ROOT"
python native_comparison.py --root "$STUDY_ROOT"
python consumer_witness.py --root "$STUDY_ROOT"
```

The original primary account implementation is preserved in source_versions/experiment_primary.py. The subsequent optional continuing-support exit leaves the default account curves unchanged; original_equity_parity.json records that check. Later input guards and private-fixture portability changes are recorded in HARDENING_SOURCE_RECEIPT.json. Source hashes in individual run receipts identify the code that actually executed, not an assumed latest revision.

## Native dependencies

The original grey-dot math is taken from Terminal commit 82cb8cbf799fc3a91c9bee0f11a4db718fde68eb, signal_layer/confluence.py and confluence_v2.py. native_replay.py executes only the listed pure functions/literal constants and verifies hashes. Its three-day grid is anchored to the available data history, with all phases retained. This is not a claim of true listing-anchor recovery or complete live/provisional parity.

The T1/T2 comparator reuses Mastermind phase3 native.py and replay.py from commit 219b6d355108912f410d09adf35eced45c376797. Those functions consume the exact Macro source manifest at 6bbc4b0fc694c847077661ff5bf4c19ea41e4e81. The actual entry-assessor witness uses Mastermind source 8323d7a774a72da20d0e4db21c9080398da185e7. Neither historical peer-waiver artifacts nor current default network reads are invented. Source snapshots are separate from runtime authority.

## Evidence layout

GitHub aggregate evidence belongs under research/evidence/sector_recovery_phase5/. The downloadable packet places the same small aggregate directories alongside the code for easy reading. Raw parquet histories, per-event source price paths and individual predictions are deliberately excluded; reproduction requires the authorized retained private copies. Aggregate counts are not independent market sample sizes.

The original protocol and each outcome-guided extension retain their own dating and status. No original null result was removed. Source publication, local tests, protected merge, live integration and investment acceptance remain separate facts. No production verdict, ranking, sizing, service, schedule, provider, credential or order was changed.
