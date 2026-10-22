# Review lane RV-L-R2T: independent review of PR #1718 (class review, C2)

You are an independent reviewer in the Mastermind repository, a paper-only portfolio bot. You did NOT build this change.

**Your tree.** The current directory is a detached checkout of the exact PR head `42ed995d5fe14a745013fe75f489dee05d6f7e62`. The branch is `claude/ssd-pbr-rt-typed-d869b47ca58d8101` and the base is `origin/master` d31aade9.

**The contract.** The builder's packet is at `~/lanes/tmp/pbr-rt-rv-typed/BUILD_PACKET.md`. The orchestrator split the lane's delivery into two PRs. The label half, `brain/thinking_log.py`, went to a separate PR. This PR carries only the typed half.

**Rules.** READ-ONLY. Do not edit, commit or push. Do not run the bot. Do not open network connections. You may run tests. Scratch files go only under `~/lanes/tmp/pbr-rt-rv-typed/`.

## Seat rulings that bound this change (authoritative)
- **CR-RT-1 (narrow grant).** `brain/cli_bridge.py` may change only to surface two things into the typed record: the SDK `AssistantMessage.error` literal (allowlist: authentication_failed, billing_error, rate_limit, invalid_request, server_error, unknown) and tool-activity-observed. It must not change invocation, retry, auth or env, and it must never log tokens. Tests must fail on the old code.
- **CR-RT-4 (reserved).** Typing only. NO change to retry, failover, cooling or scheduling behaviour: the same rungs are tried in the same order, and they stop on the same conditions.

## The change
Run `git diff d31aade9 HEAD --stat`. It shows:
- new `brain/provider_failure.py`
- new `tests/test_provider_failure_typing.py`
- edits to `brain/cli_bridge.py` (the `failure_out` side channel in `_via_sdk`, and `_failure_box` in `_reason`)
- edits to `brain/provider_waterfall.py` (`provider_failures` / `provider_failure` keys)
- a one-line `provider_failure` key in `_append_decision_log` of `bot/autonomous.py`, `bot/china.py` and `bot/hk.py`
- the `tests/test_key_rotor.py` fake signature

## Review checklist (answer each with PASS/FAIL plus file:line evidence)
1. **No behaviour change (CR-RT-4).** In `provider_waterfall.reason` and `cli_bridge._reason`, confirm that every `continue`/`break`/`return`, every cooling call and every rung-advance condition is byte-identical in effect to d31aade9. The new evidence must never be read by a branch condition. Name any line where control flow could differ, including an exception raised by new code inside the rung loop.
2. **Grant scope (CR-RT-1).** The `cli_bridge` edits only capture `ResultMessage` is_error/subtype/api_error_status, the `AssistantMessage.error` literal (allowlisted), and tool_use/tool_result observation. Each write is wrapped so it cannot raise into the SDK stream. No prompt text, response text, env value or token reaches `failure_out` or `provider_failure_evidence`.
3. **Classifier correctness (`brain/provider_failure.py`).**
   - `classify()` never raises on junk input (None, int, nested dicts, 10 kB strings).
   - Evidence is clipped (≤80 chars).
   - The precedence is: SDK literal, then api_error_status, then error_max_turns, then needles.
   - The text "Claude Code returned an error result: success" alone sets `label_misleading` and is NOT typed as credential or quota.
   - Numeric needles (401/403/429/5xx) match only on word boundaries, so for example "port 4290" is not quota.
   - Construct at least three adversarial inputs and report the records they produce.
4. **Decision-row key.** `provider_failure` is additive in all three books. Run `_append_decision_log` with `brain=None` and with a non-dict `brain`: it must still write a row. No existing key changes.
5. **Tests.**
   - Do the tests assert behaviour (typed kind, precedence, no extra `_reason` calls), not just absence of exceptions?
   - Does the source guard actually pin "no new control flow"?
   - Name one weak test, if any.
6. **Run** (report the counts):
   ```
   mkdir -p ~/lanes/tmp/pytest && PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q tests/test_provider_failure_typing.py tests/test_cli_bridge.py tests/test_key_rotor.py tests/test_provider_waterfall.py tests/test_decision_rows.py tests/test_secret_redaction.py tests/test_provider_start_veto.py tests/test_provider_start_run_binding.py
   ```
   Some `test_provider_waterfall` / `test_cli_bridge` cases may fail only because `vendor/macro_src` is absent in this checkout. Show that such a failure is identical at d31aade9 (`git stash` is NOT allowed: use `git worktree add --detach ~/lanes/tmp/pbr-rt-rv-typed/base d31aade9`, run the same file there, then `git worktree remove --force` it).

Findings must be concrete: file:line, input, expected versus actual. Do not report style preferences as defects. Severity levels:
- **BLOCKER:** a control-flow change, a secret or text leak, or a grant breach.
- **MAJOR:** a mis-typed common failure.
- **MINOR:** a doc or naming issue.

## Final message
Emit the full RETURN block as your last message:
```
RETURN RV-L-R2T
head: 42ed995d5fe14a745013fe75f489dee05d6f7e62
checklist: 1=<PASS|FAIL> 2=<..> 3=<..> 4=<..> 5=<..> 6=<n passed/n failed (+ base comparison)>
findings: <none | numbered list: severity, file:line, input, expected, actual>
adversarial inputs: <input -> record, one line each>
VERDICT: PASS|FAIL|PARTIAL
```
- **PASS:** zero BLOCKER and zero MAJOR findings.
- **PARTIAL:** MAJOR findings only.
- **FAIL:** any BLOCKER.
