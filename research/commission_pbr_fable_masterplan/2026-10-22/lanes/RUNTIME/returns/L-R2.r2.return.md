All steps complete. Final verification summary:

- **Step 0 (baseline):** 4 files error at collection on pristine code (`fastapi` missing: `test_sdk_generation_compatibility.py`, `test_sdk_diagnostic_mounted_consumer.py`, `test_provider_legacy_failure.py`, `test_provider_diagnostic_read.py`; `claude_agent_sdk` also absent), yielding 435 passed / 84 failed / 1 skipped / 14 errors — all environmental, saved to `~/lanes/tmp/pbr-rt-lr2/baseline_fail.txt`.
- **Step 2 (keep-green):** after my change the failing+error set is **byte-identical** to baseline (no new failures, no new errors).
- **Step 3 (old-code proof):** restored the six production files to `origin/master`, moved `brain/provider_failure.py` aside → 24 of 32 new tests fail; restored my versions → 32 pass again. Working tree contains only the allowed files; nothing committed or pushed.

```
RETURN L-R2
files:
  brain/provider_failure.py                  NEW (+152)
  tests/test_provider_failure_typing.py      NEW (+372)
  tests/test_thinking_log_provider_label.py  NEW (+31)
  brain/cli_bridge.py                        +54/-2   (import, _failure_box in _reason + clear + unconditional failure_out= pass + 2 evidence attachments; _via_sdk: failure_out param + docstring + 5 guarded incremental writes)
  brain/provider_waterfall.py                +23/-0   (reason() only: failures list, classify/attach, 2 fallback dicts)
  brain/thinking_log.py                      +10/-3   (build_row provider label only)
  bot/autonomous.py, bot/china.py, bot/hk.py +1/-0 each (one entry key in _append_decision_log)
  tests/test_key_rotor.py                    +2/-1    (failure_out=None in _fake_via_sdk only)
tests: typing 19 passed/0 failed; label 13 passed/0 failed;
  keep-green before 435p/84f/14e after 435p/84f/14e (sets byte-identical);
  new failures vs baseline <none>
  (baseline is environmental: claude_agent_sdk not installed; 4 files error at collection on missing fastapi —
   test_sdk_generation_compatibility.py, test_sdk_diagnostic_mounted_consumer.py, test_provider_legacy_failure.py,
   test_provider_diagnostic_read.py; run used --continue-on-collection-errors, rest executed)
old-code proof: 24 of the new tests fail on origin/master code:
  test_provider_failure_typing.py::test_armed_exception_keeps_legacy_error_and_carries_evidence (KeyError
    result["provider_failure_evidence"]), ::test_tool_activity_before_the_failure_is_observed,
    ::test_terminal_error_path_attaches_evidence_without_a_raise,
    ::test_unknown_or_forged_assistant_error_never_enters_the_evidence[401/None/forged3/something_else],
    ::test_evidence_never_carries_response_or_exception_text,
    ::test_waterfall_types_credential_and_leaves_legacy_fields_untouched, ::test_typed_record_never_authorizes_failover,
    ::test_classify_unit_table, ::test_classify_records_always_have_exactly_the_documented_shape,
    ::test_classify_survives_an_error_whose_str_raises, ::test_no_rungs_fallback_types_availability_without_changing_error,
    ::test_decision_rows_carry_the_typed_record[bot.autonomous-autonomous / bot.china-china / bot.hk-hk] (all ModuleNotFoundError:
    brain.provider_failure or KeyError provider_failure), ::test_waterfall_source_guard_typed_record_never_read_in_control_flow
    (ValueError: "failures.append(" absent);
  test_thinking_log_provider_label.py::test_provider_label_by_model_and_backend[opus-none-claude_code (old returns "openai" —
    the packet's named case), opus[1m]-none, sonnet-api, haiku-none, haiku-fast-none, orca-none (old returns "openai")]
  (the other 8 — diagnostics on/off equality and the label cases whose labels are unchanged — pass on old code too)
invariants: ok/error/text/backend/provider_attempts unchanged = yes (keep-green failing/error sets identical to baseline;
  e.g. test_diagnostics_preserve_all_legacy_control_and_result_fields, test_failed_write_tool_result_never_advances_to_oauth and
  test_actual_handler_contradictory_terminal_keeps_failed_result pin exact legacy values and still pass; only added keys);
  record read by any retry/failover/cooling decision = no (grep audit: writes in _via_sdk, attachments in _reason, classify+attach
  in waterfall reason(), persistence in the three decision logs; _kr.classify_failure/mark_cooling inputs, continue/break/return
  logic and subprocess fallback untouched; source-guard test pins that no if/elif/continue after failures.append() references the record)
deviations from packet:
  1. _via_sdk validates result_subtype against provider_failure._RESULT_SUBTYPE_RE (the module's compiled ^[a-z_]{1,40}$)
     instead of restating the regex — one source of truth, same rule.
  2. Label test table includes one extra case from the packet's own prose ("haiku-fast" → claude_code).
  3. Consequently 24/32 (not all) new tests fail on old code: the diagnostics on/off equality test and the label cases whose
     labels old code already got right pass on both; every test with a packet-named old-code failure does fail.
```
