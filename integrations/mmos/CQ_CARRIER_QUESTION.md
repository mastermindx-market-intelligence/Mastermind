# CQ — the carrier and the teammate's question (MAS-9 follow-up, 2026-11-10)

Lane CQ of plan V4. Branch `t3/mmos-v4-cq`, one commit on top of trunk
`4ec9e58dd`. Only `tools/mmos_teammate/wake_carrier.py`,
`tools/mmos_teammate/cutover_installed.py` (its `carrier_config` only) and
the two test files change. The principal installs with
`cutover_installed.py refresh-carrier <spec>` and tests on the real app;
this lane touched no live system.

## The three faults (issue MAS-9, installed app)

1. Nobody woke the task after the person answered the teammate's question.
   The carrier posted one line and exited; delivering the answer needed a
   human comment on the issue or a move back to todo.
2. Half-finished text was delivered as the answer. A later wake's
   `scan_marker` found assistant text of the marker's run ("I've exhausted
   every reachable source…") and posted it while that same run was still
   waiting on its question.
3. The waiting line told the reader nothing: "teammate is waiting for an
   answer in its T3 thread; issue left in_progress".

## What the carrier does now

**A — a run that has not ended is never a reply.** `scan_marker` takes the
same read's thread dict and returns `pending` when the marker's run id
equals the thread's `activeRunId`, or when `pendingRequestCount > 0` and it
equals `latestRunId`. A dict without those fields behaves as before. All
callers pass the dict: `handle_return`, `handle_feedback`, `run_carrier`,
`wait_for_reply`.

**B — stay with the question, finish in the same run.** One helper,
`stay_with_question`, covers the three entries: the send itself stopped on a
question (the marker is in the thread); the marker is already pending with a
question waiting; or nothing was sent because a question was already waiting
(poll until it clears, re-scan — another wake may have sent the marker — and
only then send). `send_and_stay` wraps `send_once` for all three send sites.
The thread itself tells "already waiting" from "asked during this turn", so
no message is ever sent twice; a stay that already sent once never sends
again even if the marker fails to appear.

**C — a deadline that fits the 1500 s process limit.** New config keys
(defaults): `question_wait_sec` 900, `run_budget_sec` 1320 (from process
start, recorded once in `main()`), `question_poll_interval_sec` 10. The wait
ends at the earlier of the two; unanswered it raises `NeedsHuman`: the issue
stays in_progress, `main()` returns 0, nothing is released. `wait_for_reply`
(the slow-turn wait) still ends in `CarrierError` at its own deadline —
except when a question is waiting at that deadline, which is `NeedsHuman`.
One failed thread read does not end a wait; three in a row do.

**D — a waiting line that says what to do.** Built from config: the roster
name of `PAPERCLIP_AGENT_ID` (else "The teammate"), `question_wait_sec // 60`
minutes, and — only when a loopback `thread_url_template` is configured — a
link with `{thread}` escaped (`:` → `%3A`). Same law as
`issue_url_template`: carrier config only, `http://127.0.0.1:` /
`http://localhost:` only. Posted at most once in a row (newest comment
check via `comment_rows`, read first), including on the bound `in_review`
feedback route that runs before `run_carrier`'s try block.

`cutover_installed.py carrier_config` passes the three keys (with defaults)
and `thread_url_template` through from the spec when present.

## What is not proven here

Fakes only; no live run. Not covered by any test: the real `t3` CLI's exit-2
timing, whether the installed Paperclip preserves the new config keys across
`refresh-carrier`, and the real conversation URL shape (the template comes
from the spec the principal writes). Tests inject the clock and sleep, so
wall-clock behaviour at 900 s is extrapolated, not observed.
