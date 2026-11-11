# CQ — the carrier and the teammate's question (MAS-9 follow-up, 2026-11-10)

Lane CQ of plan V4. Branch `t3/mmos-v4-cq`, first commit on top of trunk
`4ec9e58dd`, second task on top of trunk `905e85458`. Only
`tools/mmos_teammate/wake_carrier.py`,
`tools/mmos_teammate/cutover_installed.py` (its `carrier_config` only, first
task) and the two test files change. The principal installs with
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

*Second clause, checked against the live server (MAS-10, 2026-11-11): the
live server did not need it.* Throughout the question wait and after the
answer the run stayed the thread's `activeRunId`, so the first clause alone
decided. The second clause is kept as written: it guards the shape where a
server ends the run but parks it as the latest with a request still pending
— a shape the installed server has not shown, which is exactly why it is a
separate clause rather than a merged condition.

**B — stay with the question, finish in the same run.** One helper,
`stay_with_question`, covers the three entries: the send itself stopped on a
question (the marker is in the thread); the marker is already pending with a
question waiting; or nothing was sent because a question was already waiting
(poll until it clears, re-scan — another wake may have sent the marker — and
only then send). `send_and_stay` wraps `send_once` for all three send sites.
The thread itself tells "already waiting" from "asked during this turn", so
no message is ever sent twice; a stay that already sent once never sends
again even if the marker fails to appear (now pinned by
`test_stay_never_sends_again_when_the_marker_fails_to_appear`, which fails
if the `sent_here` guard is removed).

**C — a deadline that fits the 1500 s process limit.** New config keys
(defaults): `question_wait_sec` 900, `run_budget_sec` 1320 (from process
start, recorded once in `main()`), `question_poll_interval_sec` 10. The wait
ends at the earlier of the two; unanswered it raises `NeedsHuman`: the issue
stays in_progress, `main()` returns 0, nothing is released. `wait_for_reply`
(the slow-turn wait) still ends in `CarrierError` at its own deadline —
except when a question is waiting at that deadline, which is `NeedsHuman`.
One failed thread read does not end a wait; three in a row do (pinned by
`test_question_wait_survives_two_failed_reads` and
`test_question_wait_fails_after_three_reads_in_a_row`, exactly three
strikes). The run budget caps `wait_for_reply` too
(`test_run_budget_caps_wait_for_reply_too`: the budget, not
`pending_timeout_sec`, sets the end).

**D — a waiting line that says what to do.** Reworded 2026-11-11 (item 7):

> `[t2-carrier] <Name>, an AI teammate, needs your answer to continue this
> task. Open its chat: <url> and reply there. If you answer within <N>
> minutes the task continues by itself. Later than that, add any comment
> here and <Name> picks the work up again.`

Without a configured `thread_url_template` the link sentence becomes "Open
its chat in the Team list and reply there." `<Name>` is the roster name of
`PAPERCLIP_AGENT_ID`, falling back to "The teammate"; `<N>` is
`question_wait_sec // 60`. Same law as `issue_url_template`: carrier config
only, `http://127.0.0.1:<port>/…` / `http://localhost:<port>/…` only — the
port must be followed by `/`, so a userinfo trick
(`http://127.0.0.1:80@example.com/{thread}`) is rejected exactly as
`issue_link` rejects it (R4b finding 9's class). Posted at most once in a
row (newest comment check), including on the bound `in_review` feedback
route.

`cutover_installed.py carrier_config` passes the three keys (with defaults)
and `thread_url_template` through from the spec when present.

## Second task (2026-11-11): machine comments and the reader side

R4b findings 4/5 (`R4B_REVIEW_FINDINGS.md`): the installed Paperclip records
every loopback write as `authorType: "user"`, so text written by a machine
reached a teammate as if a person on the board had said it. T4c fixes the
writers; this lane fixed the reader. The lane line: door/result-transport
comments start with `[coding-job]`, carrier notes with `[t2-carrier]`.

**Item 1 — one predicate, applied where a comment is read as words.**
`is_machine_comment(body)`: true when the body, after leading whitespace,
starts with `[coding-job]` or `[t2-carrier]` — whatever `authorType` the
row carries. Applied in `board_notes`, `board_feedback` and
`last_result_comment`. Every other comment-row reader was checked and left
as found, deliberately: `comment_rows` (ordering plumbing; its callers
filter), `comment_already_present` (exact-text equality with an unprefixed
teammate reply — a machine comment can never match),
`post_waiting_note_once` (must compare against the carrier's own note, so
it must see machine comments), `handle_coding_job`'s idempotency scan
(scans for its own marker inside machine comments — filtering would break
idempotency), and `handle_ask` (via `comment_already_present`).

**Item 2 — every comment the carrier writes is a machine comment.** The
admission/replay comment in `handle_coding_job` was the one unprefixed
carrier note; it now starts `[t2-carrier] coding job …`. Full audit of
`pc.add_comment` sites: coding-job unreachable-door note (prefixed),
admission/replay (FIXED this task), WAIT note (prefixed), refusal note
(prefixed), the waiting line (prefixed, `[t2-carrier]` kept through the
item-7 reword), `release_issue` note (prefixed), and the teammate's own
reply in `deliver` and `handle_ask` (deliberately NOT prefixed — it is the
human-visible answer, and the reply-equality and last-result readers depend
on that).

**Item 3 — an asked teammate is not offered the coding-job block.** The
`job_help` argument to `build_message` is now `None` for an ask child
exactly as `asking` already was, whatever `coding_job_door` says (R4b
finding 5: the asker owns the job decision).

**Item 4 — one place builds the run opts.** `build_opts(cfg, environ, now)`,
called by `main()`. Every key is mapped there and unit-tested
(`test_build_opts_maps_every_key_and_reads_the_door_from_config_only`),
including the three question keys, `thread_url_template` and `run_start`.
`coding_job_door` is read from the config file only — confirmed: `main()`
never passed it before, so the door was dormant in production; it stays
dormant until the principal adds the key to a spec.

**Item 5 — a blocked task whose turn was in flight finishes.** A blocked
issue with no ask child is no longer blanket-skipped: the carrier computes
the task's marker, reads the thread, and leaves it for a person only when
the marker is absent. With the marker present the normal path runs — an
ended run is delivered, a question wait stays with it, a slow run is waited
on — and board feedback on the same issue is handled through that same gate
(marker present → revision round; absent → left for a person). An unreadable
thread on a blocked issue also leaves it for a person (no forced un-block).

Delivery-from-blocked, inspected: `deliver` PATCHes only `status`
(`in_review`, or `done` for an ask child) after the comment and
confirmation; `checkout` already passes `expectedStatuses` with `blocked`
(the return wake has used this live). The PATCH blocked→in_review is the
same call the live-proven return wake makes on a blocked parent. The
release path's PATCH blocked→todo after a slow-wait deadline is NOT
live-proven; the fakes accept any transition.

**Item 8 — the first return's untested list, closed.** Three-failed-reads
`CarrierError` (one or two do not), `run_budget_sec` capping
`wait_for_reply`, and the one-send-per-stay hardening now each have a test.
These tests passed against the pre-item-8 code, as expected — task 1 had
implemented the behaviors; the tests prove them and pin them.

## What is not proven here

Fakes only; no live run. Not covered by any test: the real `t3` CLI's
exit-2 timing, whether the installed Paperclip preserves the new config
keys across `refresh-carrier` (now also `coding_job_door`, when a spec
carries it), and the real conversation URL shape (the template comes from
the spec the principal writes). Tests inject the clock and sleep, so
wall-clock behaviour at 900 s is extrapolated, not observed. The
PATCH blocked→todo release transition is unproven on the real server (item
5). Comments written by the pre-T4c door (`[t4b-door]` blockers) do not
carry a lane prefix and are not filtered by `is_machine_comment` — pinned
deliberately in the test; whether to rewrite or age out those historical
comments is the principal's call with T4c.
