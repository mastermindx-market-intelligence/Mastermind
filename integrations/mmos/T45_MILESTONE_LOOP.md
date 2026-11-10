# T45 — the milestone loop, live

Lane T45 (branch `t3/mmos-v4-t45`) proved the whole teammate loop live on
the dev pair (Paperclip dev `127.0.0.1:3190`, T3 dev `:3800`, TEST company
`MMOS Dev` only): an issue alone starts work, a teammate can ask another
teammate and gets the answer back, the board's confirm/decline closes or
revises the answer, routines fire once on schedule with no window open, and
an independent attack script tried to break all of it. Evidence:
`~/.mastermind/mmos_evidence/t45-20261110/` (numbered JSON + LEDGER.md).

## What runs where

The carrier `tools/mmos_teammate/wake_carrier.py` is the run command of each
TEST agent. Paperclip wakes it; it sends the task to the agent's T3 primary
thread under a marker op `pc-<issueId>-<sha10>`, waits for that turn's
reply, and delivers: answer comment, a `request_confirmation` with the
`native_completion_review` target (idempotency key `<op>-confirm`), status
`in_review`. The marker rule is the exactly-once spine: one send per op, the
reply bound to the marker's T3 run, deliveries skipped when already present.

## The eight results

1. **Assignment alone starts the work.** Creating an issue assigned to a
   TEST teammate fires `issue_assigned`; that one run does everything
   (baseline double-run fixed by preferring the row whose activeRun is the
   current run). Assignment racing a keyed wake still sends once — the keyed
   wake coalesces into the claimed run. (Evidence 01–03.)
2. **A real task yields a real output.** The turn writes a file and ends
   with a `paperclip-output` block; the carrier upserts it as an issue
   document (the build's existing output surface) and the comment carries
   the absolute path. (Evidence 04.)
3. **Teammate asks teammate.** A fenced `paperclip-ask` block in the reply
   creates one child issue under the parent for a roster-named teammate and
   blocks the parent on it. Live rule found: the unblock owner must be the
   asker itself (403 otherwise). Yes — the build wakes the asker when the
   child completes (`issue_children_completed` ran it; `issue_blockers_
   resolved` exists but fires only when every blocker is done and is
   suppressed by failed-run no-replay holds). The ask child completes with
   `done` (no board confirmation — that would strand the wake); the carrier
   sends one `<op>-ask-ret` message with the child's result and link into
   the asker's thread, and the asker's next answer finishes the parent.
   Unknown or malformed ask blocks create nothing outside the company —
   plain replies. Ran clean twice (MMO-17, MMO-19). (Evidence 05–06.)
4. **Routines fire once, headless.** Cron `* * * * *` created one issue per
   minute (MMO-16/21/22/23), one run and one answer each, no doubles.
   Stopping the server across five due times and restarting produced exactly
   ONE recovery execution at boot plus the next live due — `skip_missed`
   held, no back-fill burst. Restart must go through
   `tools/mmos_dev/paperclip_dev.sh up`; a raw `paperclipai run` respawn is
   refused by the CLI doctor (HOME-isolation note in that script).
   (Evidence 07.)
5. **Attention items clear by action.** The waiting list is
   `GET /api/companies/{cid}/attention`. Accept of the completion-review
   confirmation sets the issue `done` and fires nothing else (MMO-26: zero
   new runs, zero new wakes). Reject-with-comment wakes the teammate once
   (the comment's `issue_commented` wake; the reject's own continuation wake
   coalesced): one new turn sees the decline reason and the board's words,
   one revised answer, a NEW pending confirmation (`<op>-rev1-confirm`), and
   the original task is never resent. A plain confirmation accept returns
   the issue to todo instead of done — that is why the carrier requests the
   `native_completion_review` target. (Evidence 08–09.)
6. **Hot-add provider instance: YES.** A running dev T3 server can serve a
   provider instance added after boot; `t3 thread start --provider <new>`
   works without a restart. Exact commands and output in evidence 10.
7. **Attack.** One child (kimi-k3.1-pro, role test) wrote and committed
   `tools/mmos_teammate/attack_t45.py`; the principal ran it live four
   times, repairing three harness bugs the runs exposed (a bare-scalar
   SQL count, the trigger-create response shape, and the server's 48-hour
   same-title create-dedupe, which silently returned earlier attack
   issues until every probe title carried a per-run tag). Final verdicts,
   all **HELD**: extra keyed wakes and a keyed replay never double-send or
   double-post (and the board round still closes: reject → one revision,
   accept → done with zero follow-on runs); a one-minute routine never
   fires twice in a minute (4 dues, each exactly one issue, one run, one
   answer); the per-run token appears on no scanned surface (0 matches for
   the real `pcp_` key format; all 65 generic long-string hits classified
   as carrier markers, sha256 digests, or server metadata); unknown and
   malformed `paperclip-ask` blocks create nothing (0 children, plain
   replies — the teammate refuses to echo an ask fence at all). The
   child's suspected concurrent double-delivery race was probed directly —
   two extra keyed wakes fired within milliseconds of the assignment wake —
   and held: the wake queue coalesced them into the one active run. Counts
   and adjudication: evidence 11.
8. **Tests.** 45 unit tests in `tests/test_mmos_teammate_carrier.py` cover
   every carrier behavior changed here (assignment preference, race, ask
   placement + 403 owner rule, return edge, blocked eligibility, ask-child
   delivery, board feedback rounds, verdict routing, replay no-resend).

## Where it intentionally stops

Only TEST agents of the TEST company were driven; the installed Paperclip,
the Chairman's T3 Code app, TeamLink, and Hermes were never touched. The
per-run token stays inside the carrier process (attack sequence 4 checks
threads, comments, run rows and argv for leaks). No window was opened for
any routine or wake — servers ran headless throughout.

One boundary remains thin by design: the answer comment is the only
delivery step without a server-side atomic key (agent comments carry no
client-request id in this build). Exactly-once for it rests on the
dispatch-side serialization the attack verified — the wake-queue claim,
the per-issue execution claim, and checkout-refusal — not on the comment
write itself. If a future server change ever lets two carrier runs for one
agent overlap on one issue, the comment is the step that could duplicate;
the confirmation and status steps cannot (idempotency-key conflict).
