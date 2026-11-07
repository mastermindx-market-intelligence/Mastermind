# Early cycle-failure economics, v20–v22

**Status:** retrospective falsification, no accepted trade rule.

Files:
- `oracle_value_v20.py` / `ORACLE_UPPER_BOUND_RESULTS_V20.json`: predeclared three-hour hindsight upper bound on the same 91 entries.
- `SPECIFICATION_V21.json`, `decision_timing_v21.py`, `RESULTS_V21.json`, `DECISION_TIMING_AGGREGATES_V21.csv`: six interventions and their source/eligibility checks.
- `SPECIFICATION_V22.json`, `walkforward_v22.py`, `RESULTS_V22.json`, `WALK_FORWARD_AGGREGATES_V22.csv`: fixed low-capacity earlier-calendar-week economic prediction and the simple below-entry control.
- `VALIDATION_V21_V22.json` and `verify_v21_v22.py`: accounting, timing and artifact checks, including exact v20 parity.
- Derived per-episode outcome tables can be inspected; licensed OHLC price rows and market quotes must remain in the existing private mini4 source dataset.

See [FINDINGS_V20_V22.md](FINDINGS_V20_V22.md) for the honest economic conclusions. Historic simulations use next-five-minute-opening fills and stop-first OHLC, **not executed brokerage fills**. No genuine SOXX historical BOATS night has been provided to this study.
