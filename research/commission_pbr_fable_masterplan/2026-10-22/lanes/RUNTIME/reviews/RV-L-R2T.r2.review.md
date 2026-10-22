<!-- run-id pbr-rt-rv-typed-r2 | host ubuntu0 | model glm-5.3 | class review C2 | PR #1718 head 42ed995d5fe14a745013fe75f489dee05d6f7e62 | source sha256 b6d0b9956d0a6cb4ed428e2e107bf4839232732547bc364de1d4b58cfd77928a | token-shaped fixture strings redacted | retained 2026-10-22T11:36:39Z -->
Review complete. All checks done: function-level diffs against base, repo-wide consumer grep, adversarial classifier probes, decision-row probes, test runs at head and base (via throwaway worktree, removed). Tree left clean and read-only.

## Review summary

**1. No behaviour change (CR-RT-4) — PASS.** Function-level diff of `provider_waterfall.reason` shows only additive blocks; the ok/return check (`brain/provider_waterfall.py:268`), the oauth `continue`/`return` (`:274-278`) and codex `return` (`:282-283`) are byte-identical and sit below the new code. Lines where control flow could in principle differ, and why it cannot:
- `provider_waterfall.py:256-266` (new code inside the rung loop): `classify` wraps its whole body in `try/except` (`brain/provider_failure.py:99-152`); the only statement outside the try is a dict literal (`:65-79`). It cannot raise. `result` is always a dict; `list(failures)`/assignment cannot raise.
- `cli_bridge.py:675`, `cli_bridge.py:791`: `dict(_failure_box)` copies a module-local plain dict immediately before an unchanged `break`.
- `cli_bridge.py:662`: keyword-only addition; all three `_via_sdk` call sites (`cli_bridge.py:658`, `tests/test_provider_start_veto.py:45`, `tests/test_provider_start_run_binding.py:180`) are keyword-form past `arm`, so the inserted parameter shifts nothing.
- `cli_bridge.py:1052-1056, 1068-1080, 1083-1090, 1118-1122, 1136-1140`: every `failure_out` write is inside its own `try/except Exception: pass`, nested inside the unchanged per-message handler, so a guard failure can never reach the outer `except BaseException: raise`.
- Repo-wide grep: the only reader of `provider_failure_evidence` is the `classify` input at `provider_waterfall.py:259`; `provider_failure`/`provider_failures` are write-only (waterfall `:216-217, 265-266, 292-293`; books) — no branch anywhere reads them.

**2. Grant scope (CR-RT-1) — PASS.** `failure_out` receives only: bools (`tool_activity_observed`), the allowlisted literal (`provider_failure.py:26-33` is exactly the six CR-RT-1 strings), and on ResultMessage `is_error` (bool only), `subtype` (`^[a-z_]{1,40}$` only), `api_error_status` (int, not bool) — the enumerated checklist scope. No prompt/response text, env value or token can enter (the subtype regex structurally excludes payloads; test 6 pins it).

**3. Classifier — PASS.** Never raised on any junk input (None, int, nested dict, 10 kB strings, `__str__` that raises, dict whose `.get` raises); evidence always ≤80 chars and needle-only (a secret-shaped error yields evidence `"401"`, never the token); precedence literal→status→max_turns→needles confirmed by three dedicated probes; the misleading label alone → `unclassified` + `label_misleading: true`; `"port 4290"` → unclassified.

**4. Decision-row key — PASS.** One-line additive insert in each book (`bot/autonomous.py:898`, `bot/china.py:781`, `bot/hk.py:781`); `brain=None`, `brain="not-a-dict"` and dict-without-key all still write rows (`provider_failure=None`, `error` unchanged).

**5. Tests — PASS, one weak test.** Assertions are behavioural: typed kind/evidence/source, exact evidence-dict equality, exact `provider_attempts` list, `calls == ["codex"]` / `calls2 == ["cli"]` pinning no-extra-`_reason`-calls, and decisions.jsonl row equality. The source guard pins only `if`/`elif`/`continue` lines in provider_waterfall.py after `failures.append(` (packet-sanctioned minimum; I verified the remainder by function-level diff). Weak: `test_diagnostics_disabled_leaves_legacy_and_evidence_paths_equal` (`tests/test_provider_failure_typing.py:94`) passes vacuously on old code.

**6. Run.** HEAD: **196 passed / 28 failed / 1 skipped**. Base d31aade9 (same 7 pre-existing files, throwaway worktree, removed): **177 passed / 28 failed / 1 skipped** — failure node-id sets byte-identical (verified by sorted diff); all 28 are environmental (`No module named 'fastapi'`, vendored `engine`/`lib` unimportable). New file: 19/19 pass at HEAD; 18/19 fail on old code (the 19th is the equality test above).

```
RETURN RV-L-R2T
head: 42ed995d5fe14a745013fe75f489dee05d6f7e62
checklist: 1=PASS 2=PASS 3=PASS 4=PASS 5=PASS 6=196 passed/28 failed, 1 skipped (base d31aade9: 177/28, 1 skipped on the same 7 files — failure node-id sets byte-identical, all environmental: fastapi missing, vendored engine/lib unimportable; new file 19/19 at head, 18/19 fail on old code)
findings:
  1. MINOR — tests/test_provider_failure_typing.py:94 — test_diagnostics_disabled_leaves_legacy_and_evidence_paths_equal on old code: expected (per packet "each new test must fail on origin/master") a failure, actual PASS (both runs lack the new key, so equality holds vacuously). Invariant guard still valid going forward; not a code defect.
  2. MINOR — brain/cli_bridge.py:1074 — uses the private provider_failure._RESULT_SUBTYPE_RE instead of a public helper; naming-level, no behaviour impact.
adversarial inputs:
  - classify() -> unclassified, all fields None, full 12-key shape
  - classify(error=40129) -> unclassified (int str "40129" has no \b401\b match)
  - classify(error={"a":{"b":[{"c":"revoked"}]}}) -> credential, evidence "revoked" (needle only, no surrounding structure)
  - classify(error="x"*10000 + " timed out") -> transport, evidence "timed out", ≤80 chars
  - classify(error="connect EADDRINUSE port 4290 in use") -> unclassified (NOT quota; \b429\b fails inside 4290)
  - classify(error="Exception('Claude Code returned an error result: success')") -> unclassified + label_misleading=True (not credential/quota)
  - classify(error=<production 401 legacy str>, evidence={assistant_error: authentication_failed, result_is_error: True, result_subtype: success, tool_activity_observed: False}) -> credential, evidence sdk_assistant_error:authentication_failed, label_misleading True
  - classify(evidence={assistant_error: rate_limit, api_error_status: 401}) -> quota (SDK literal outranks status)
  - classify(evidence={api_error_status: 529, result_subtype: error_max_turns}) -> availability (status outranks max_turns)
  - classify(error="timed out", evidence={result_subtype: error_max_turns}) -> deadline (max_turns outranks text needle)
  - classify(evidence=EvilDict(get raises)) -> unclassified, no raise
  - classify(error=obj whose __str__ raises) -> unclassified, no raise
  - classify(error="401 sk-ant-[REDACTED]…revoked") -> credential, evidence "401" only — token never enters the record
VERDICT: PASS
```
