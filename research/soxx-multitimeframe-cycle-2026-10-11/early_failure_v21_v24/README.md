# Early-failure research source preservation (v21–v24)

This directory is the missing executable **source + source-result + verification** counterpart to the previously published prose in ../early_failure_v20_v22/FINDINGS_V20_V22.md. It remains retrospective and is not approved for real trades.

- Decision timing: SPECIFICATION_V21.json, decision_timing_v21.py, RESULTS_V21.json, DECISION_TIMING_AGGREGATES_V21.csv
- Chronological model (failed): SPECIFICATION_V22.json, walkforward_v22.py, RESULTS_V22.json, WALK_FORWARD_AGGREGATES_V22.csv; verify_v21_v22.py and VALIDATION_V21_V22.json
- Economic asymmetry: SPECIFICATION_V23.json, economic_asymmetry_v23.py, ECONOMIC_ASYMMETRY_RESULTS_V23.json, ECONOMIC_ASYMMETRY_V23.csv
- Execution stress: SPECIFICATION_V24.json, execution_stress_v24.py, RESULTS_V24.json, EXECUTION_STRESS_V24.csv, verify_v23_v24.py, VERIFICATION_V23_V24.json

[Read the substantive findings](FINDINGS_V23_V24.md).

**Not published:** actual vendor five/15/30-minute bar payloads, private event-by-event market data, DECISION_TIMING_EVENT_DIAGNOSTICS_V21.csv, WALK_FORWARD_DECISIONS_V22.csv, EXECUTION_STRESS_PRIVATE_EVENTS_V24.csv and API credentials. Those remain on mini4 in /private/tmp/soxx_early_failure_frontier_v21_20261012 or the referenced source owner.

Full-period SOXX BOATS history and venue bid/ask are still absent; no trade or production effect was requested or executed.
