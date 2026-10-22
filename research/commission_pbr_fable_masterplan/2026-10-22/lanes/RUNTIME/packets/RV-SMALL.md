# Review lane RV-SMALL: independent review of PRs #1716, #1715 and #1734 (class review, C2)

You are an independent reviewer in the Mastermind repository, a paper-only portfolio bot. You did NOT build these changes.

**Your tree.** The current directory is a detached checkout of `origin/master` d31aade9. The three PR heads are already fetched into this repository. Review each one with `git checkout --detach <sha>`, then `git diff d31aade9 <sha>`.

**Rules.** READ-ONLY. Do not edit, commit or push. Do not run the bot. Do not open network connections. You may run tests. Scratch files go only under `~/lanes/tmp/pbr-rt-rv-small/`.

| PR | head sha | files |
|---|---|---|
| #1716 | fa3253174c2512e4e3b2428354e4b4aa19a272ca | `brain/thinking_log.py` (provider label in `build_row`) + new `tests/test_thinking_log_provider_label.py` |
| #1715 | 0bc5e3f369cadf3d2436ea8bb1bd7ff96813af7e | `tests/test_provider_incident_forward.py` only |
| #1734 | 65b70c766aa4aa5f8cac4d23f31f58c36db73f88 | new `tests/test_retry_no_duplicate_effect.py` only |

## #1716: thinking-log provider label (diagnostic label only)
1. **Mapping.** `claude-*` maps to claude_api. The bare aliases opus/sonnet/haiku (optionally with a `[..]` suffix or a `-variant`) map to claude_code. `gpt-*` and `o<digit>…` map to openai. `deepseek` maps to deepseek. Everything else maps to None. The backend overrides are unchanged: codex gives openai_codex, and sdk/cli give claude_code.
2. **Edge cases.** Name any realistic model string that is now mislabelled, for example `o1-mini`, `gpt-5`, `claude-opus-4`, `Opus`, an empty string, or `None`.
3. **Regression check.** The new tests fail at d31aade9. Run `git checkout --detach d31aade9 -- brain/thinking_log.py`, then run the new test file, then restore with `git checkout --detach fa3253174c2512e4e3b2428354e4b4aa19a272ca`. Report the counts.
4. **Scope.** No other behaviour changes.

## #1715: stat-identity flake fix (tests only)
1. **The defect.** The old asserts compared a full `os.stat_result`, and its `__eq__` includes the int st_atime. So a read under relatime could flip the result. Confirm this from the diff.
2. **The new `slot_identity()`.** It must still detect each of these: a content change, a 1 ns mtime change, a replacement (new inode), and a chmod. It must ignore atime only. Is any identity field lost that the original test intended to pin?
3. **The new test.** Does it actually exercise the atime-only case without relying on `os.utime`? Note that `utime` changes ctime.

## #1734: retry/re-decide no-duplicate fences (tests only)
1. **Hermeticity.** Every test uses `tmp_path` and monkeypatch. Nothing writes the real `data/`: after running, check `git status --short --ignored data`. `apscheduler` is stubbed via monkeypatch only.
2. **Meaningfulness.** Does each of the 10 tests assert the invariant its docstring names? Would it fail under that docstring's named mutation? Spot-check two mutations yourself in a scratch copy, not in the tree.
3. **Domain correctness.** Are the D-section expectations real product rules, or merely the current behaviour? In particular, check that an earlier queued row stays "queued" after a later asof settles. Are they consistent with `bot/settle.py` and `bot/decision_rows.py`?

## Run (report counts per PR, at that PR's head)
```
mkdir -p ~/lanes/tmp/pytest
export PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest
P="~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts= -q"
```
- #1716: `tests/test_thinking_log_provider_label.py tests/test_thinking_log.py`
- #1715: `tests/test_provider_incident_forward.py`
- #1734: `tests/test_retry_no_duplicate_effect.py tests/test_decision_rows.py tests/test_retry_policy.py tests/test_scheduler_decision_outcomes.py`

A failure that is identical at d31aade9, for example because `vendor/macro_src` is absent, is pre-existing. Show that it is identical there.

Findings must be concrete: file:line, input, expected versus actual. Severity levels:
- **BLOCKER:** a wrong label or behaviour change, a non-hermetic write to `data/`, or a test that cannot fail.
- **MAJOR:** an edge case.
- **MINOR:** a doc issue.

## Final message
Emit the full RETURN block as your last message. Give one VERDICT line per PR:
```
RETURN RV-SMALL
#1716 head fa3253174c25 checklist: 1=.. 2=.. 3=<old n failed/n passed> 4=.. run=<n passed/n failed>
#1716 findings: <none | list>
VERDICT #1716: PASS|FAIL|PARTIAL
#1715 head 0bc5e3f369ca checklist: 1=.. 2=.. 3=.. run=<..>
#1715 findings: <none | list>
VERDICT #1715: PASS|FAIL|PARTIAL
#1734 head 65b70c766aa4 checklist: 1=.. 2=<mutations tried -> result> 3=.. run=<..>
#1734 findings: <none | list>
VERDICT #1734: PASS|FAIL|PARTIAL
```
- **PASS:** zero BLOCKER and zero MAJOR findings.
- **PARTIAL:** MAJOR findings only.
- **FAIL:** any BLOCKER.
