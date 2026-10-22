# Lane L-R4 — negative tests: an ambiguous retry/re-decide never duplicates a target or a fill (class build, C2)

You are a bounded Fabric worker in the Mastermind repository (paper-only portfolio bot). Your working tree is the current
directory, a detached checkout of `origin/master`. You create exactly ONE new file and edit nothing else:
`tests/test_retry_no_duplicate_effect.py`.
Never edit `bot/settle.py`, `portfolio/paper_account.py`, `brain/*`, `app/*` or any existing test. Do not commit, push, run
the bot, or open network connections. Tests use `tmp_path` and `monkeypatch` only — never the real `data/` directory.

## Why
Between 2026-10-12 and 10-21 every CN/HK/US manager run failed on the first OAuth slot and was NOT retried on another rung.
That conservative behavior is intentional: an error after the model may have used typed tools must not be replayed, because a
replay could submit a second target. Separately, the US book is re-decided overnight (02:20 / 06:20 UTC) after its 23:10 run,
so several accepted "queued" targets can exist for one book within hours. These tests pin the invariants that keep retries and
re-decides from duplicating effects. They must PASS on the current code (they are regression fences). If any invariant
FAILS on current code, do not change source: mark that single test `@pytest.mark.xfail(strict=True, reason="CR-RT-5: <what
duplicates>")` with NO `raises=` argument, keep the assertion exact, and report it in your RETURN.

## Read first (do not modify)
- `brain/provider_waterfall.py::reason` (rung loop; oauth rung continues only on "all pool keys cooling/dead" or
  `_failure_kind`), and `tests/test_provider_waterfall.py` for how rungs and `cli_bridge._reason` are monkeypatched.
- `app/scheduler.py::_maybe_schedule_brain_retry`, `_read_pool_exhausted_since`, `_BRAIN_RETRY_JOBS`, `_BRAIN_RETRY_COUNTS`,
  and `brain/retry_policy.py::decide_retry` (MAX_RETRIES_PER_DAY).
- `bot/decision_rows.py::replace_for_asof` and `is_substantive`; `tests/test_decision_rows.py`.
- `bot/settle.py::execute_or_queue` and `settle_open`; `portfolio/paper_account.py::save_pending_target` ("generic PM
  writers retain latest-wins"); and `tests/test_decision_settlement_reconciliation.py` lines 1–93 — copy its setup pattern
  (registry._ROOT → tmp_path, settle.is_open, fx.usd_to, paper_account._current_price, settle._price_and_sources,
  paper_account._save_account seed, module._append_decision_log, paper_account.save_pending_target, settle.settle_open).

## Required tests (each must discriminate: state in a comment which code change would make it fail)
A. Waterfall, no replay after an unclassified provider error:
   1. Two oauth rungs; the first `_reason` returns `{"ok": False, "error": "Exception('Claude Code returned an error result: success')"}`
      → `reason()` calls `_reason` exactly once and returns that failure (no second rung).
   2. Same with first error `"all pool keys cooling/dead"` → the second rung IS called exactly once (control case).
   3. Codex rung first with an unclassified error (e.g. "tool call failed after write") → no further rung.
B. Scheduler retry is not scheduled without the all-cooling marker:
   1. `_read_pool_exhausted_since` → None ⇒ no `add_job` on a fake `_scheduler` (monkeypatch `app.scheduler._scheduler`
      with an object recording `add_job` calls; pick a job id/book pair from `_BRAIN_RETRY_JOBS`).
   2. With a marker and a fixed `now` far from the next scheduled run, calling it repeatedly on the same UTC day schedules
      at most `MAX_RETRIES_PER_DAY` jobs with distinct ids (reset `_BRAIN_RETRY_COUNTS` in the test; monkeypatch
      `_next_scheduled_run` and `_today_iso_utc`; let the real `decide_retry` decide; set jitter deterministically if the
      policy exposes a way, otherwise accept any retry_at).
C. Decision rows: a retry for the same asof keeps exactly one row:
   1. substantive then substantive ⇒ one row, the later one.
   2. substantive then barren (`rejected_no_submission`, decision_effective False, no holdings) ⇒ the substantive row survives.
   3. rows for other asofs are preserved in order.
D. Settlement: re-decides never stack targets or fills (autonomous book, market closed then open):
   1. Two closed-session `execute_or_queue` calls on the same book (asof 2026-08-12, targets {AAPL: 0.20} then
      {MSFT: 0.10}, each with a decision snapshot and `_append_decision_log(..., target_status="queued")`) ⇒ exactly one
      pending target, equal to the second; zero fills recorded.
   2. Then `settle_open("autonomous", "2026-08-13")` ⇒ fills only for MSFT; no AAPL fill.
   3. Calling `settle_open` again for the same day ⇒ no additional fills and no second receipt (idempotent).
   4. If the two decisions use different asofs (2026-08-12 then 2026-08-13 overnight, settle 2026-08-14), the earlier
      queued row must NOT be marked executed with the later target's fills (no misattribution). Assert that exactly; in a
      comment and in your RETURN, record what status the earlier row is left with (e.g. still "queued").

## Run
`mkdir -p ~/lanes/tmp/pytest && PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q tests/test_retry_no_duplicate_effect.py tests/test_provider_waterfall.py tests/test_decision_rows.py tests/test_retry_policy.py`
(fall back to `python3` if the venv python is missing). Report each file's result.

## Final message
Emit the full RETURN block as your last message:
```
RETURN L-R4
file: tests/test_retry_no_duplicate_effect.py (<lines> lines, <n> tests)
results: <file: passed/failed/xfailed> for each file run
xfail (CR-RT-5 findings): <none | test name + what duplicates>
earlier-queued-row status after later settlement (D4): <observed status>
deviations from packet: <none | list>
```
