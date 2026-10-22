RETURN L-R4
file: tests/test_retry_no_duplicate_effect.py (624 lines, 10 tests)
results: tests/test_retry_no_duplicate_effect.py: 10 passed; tests/test_provider_waterfall.py: 13 passed / 3 failed (pre-existing: test_available_skips_bad_slot_and_keeps_later_eligible_slot[exception|malformed_result], test_failed_write_tool_result_never_advances_to_oauth — all three import the real engine.llm_auth and vendor/macro_src is absent in this lane checkout; fail identically without my file); tests/test_decision_rows.py: all passed; tests/test_retry_policy.py: all passed
xfail (CR-RT-5 findings): none
earlier-queued-row status after later settlement (D4): still "queued" — superseded intent untouched: executed == [], no settlement_transaction_id, no settled_asof; only the 2026-08-13 row was marked executed, with the MSFT fills
deviations from packet:
  - apscheduler is not installed in ~/lanes/venv, so `_maybe_schedule_brain_retry` returns before add_job; test B2 injects a minimal fake `apscheduler.triggers.date` module chain via monkeypatch.setitem(sys.modules, ...) so the add_job path is observable (monkeypatch-only, per-test reverted)
  - control_plane.run_events' default ledger is the live data/governance/ path; B tests redirect run_events._ledger_path to tmp_path (same pattern as the existing tests/test_scheduler_decision_outcomes.py fixture) so nothing touches the real data/ directory (verified: data/governance never created)
  - the 4-file run reports 3 pre-existing failures in tests/test_provider_waterfall.py caused by the absent vendored engine (vendor/macro dangling symlink in this worktree), unrelated to the new tests; packet's "fall back to python3" not needed — venv python exists
```
