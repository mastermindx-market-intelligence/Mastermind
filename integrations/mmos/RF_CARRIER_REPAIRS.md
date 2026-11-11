# Lane RF — carrier repairs from the R2a review (2026-11-11)

Scope: the R2a findings (1–15 in `R2A_REVIEW_FINDINGS.md`, 16–31 delivered in
principal messages) applied to the MMOS teammate carrier surface
(`tools/mmos_teammate/wake_carrier.py`, `cutover_installed.py`,
`setup_teammate.py` and their tests), plus one read-only investigation of the
installed Paperclip server (finding 7). Every lane-RF fix has a failing test
first and a red/green pair in `~/.mastermind/mmos_evidence/rf-20261111/`.
Branch `t3/mmos-v4-rf`; this file lands at HEAD with the last fix.

Verify: `TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest
-q -p no:cacheprovider tests/test_mmos_teammate_*.py
tests/test_mmos_coding_job_*.py tests/test_paperclip_result_delivery.py`
— 163 tests in the three teammate files (141 carrier + 21 cutover + 1 setup),
plus the coding-job and paperclip-delivery suites, exit 0.

## The findings, one by one

**1 — teammate tool limits (roster).** Fixed by the principal before this lane
(deny rules for credential folders, other homes, self-limits, charter,
carrier config, preimage). Not lane RF. The one open sub-decision — WebFetch —
is answered in the lane RF return: keep it DENIED. No proven journey uses
outbound web; the carrier posts whatever a teammate writes, so every tool that
pulls outside text into a reply widens that channel for no demonstrated need.
Re-add deliberately if a future task needs it.

**2 — marker discipline (`e76fe19b3`).** A turn marker counts only when a user
message begins with exactly `[op]` and a newline, and the first such message
wins. The last-anywhere-wins reading that let issue X's text answer issue Y is
gone.

**3 — structural ask children (`b3bb8de72`).** An issue is an ask child only
when it has a parent, its description's last line is exactly the marker the
carrier computes for that parent, and the marker is the carrier's own
(checksum over parent title+description). Any `[pc-…]` text a teammate wrote
is stripped from what reaches the child issue. A bracketed marker in ordinary
prose no longer creates or satisfies an ask edge.

**4 — ask depth, self-asks, cap, paging (`a3721efd0`).** Asked children cannot
ask (depth one; the child's task message says so), an ask to oneself is
refused with one line, `max_asks_per_issue` (config key, default 3) caps asks
per issue, and the children walk pages by offset (10-page bound) instead of
stopping at 50.

**5 — ask-child return and feedback edges (`9a482af45`).** Both edges deliver
with the ask-child flag: the child goes to done with no second board
confirmation.

**6 — retry law (`031d05eb6`).** Only GET/PUT/PATCH retry; POST fails fast. A
failed child-issue create reads the children back for this operation's marker
before doing anything else; a 409 on this op's confirmation key is success.

**7 — two processes, one thread (`ac1ceb966`).** Established read-only from
the installed server bundle: one Paperclip agent CAN run two carrier
processes at once — per-agent concurrency defaults to 20
(`AGENT_DEFAULT_MAX_CONCURRENT_RUNS`, paperclipai
`shared/dist/constants.js:61`), slots are filled by
`startNextQueuedRunForAgent` (`@paperclipai/server`
`dist/services/heartbeat/queue.js`, `availableSlots = maxConcurrentRuns -
runningCount`), each run spawns one child process
(`dist/adapters/process/execute.js`). Only the per-ISSUE execution run is
single-flight (issue row `for update` + `admitWakeBehindIssueExecution`
coalesce/defer, `dist/modules/wake-queue/application/use-cases.js:597`;
`issues.activeRunId` is a single FK). One teammate agent binds one T3 thread
for every issue, so the overlap is real. The carrier now takes an advisory
`flock` on `thread-<thread id>.lock` (directory: `thread_lock_dir` config
key, default the carrier config file's own directory) before any scan,
checkout or send, and holds it to the end of the run. A twin holding the lock
past this run's budget ends the run quietly — inbox untouched, next wake
picks it up. No lock directory configured: exactly the old behavior. The lock
file is never unlinked (an unlink would let a third process lock a fresh
inode beside a live holder).

**8 — waits inside the run budget (`515908896`).** `delivery_reserve_sec`
(default 120) is carved off the end of the run budget; the question wait, the
slow-turn wait, every HTTP timeout and retry sleep, and the `t3` subprocess
timeout are all capped by the remaining waiting budget. No wait can any
longer spend the slice that delivery needs and get the carrier killed
mid-write.

**9 — apply over a shared carrier file (`2d8ad8e03`).** `apply` refuses when
an installed carrier file exists and differs (points at `refresh-carrier`);
installs only when absent, staged copy + one `os.replace`.

**10 — rollback safety (`3722481f6`).** `rollback` refuses on the same
open-work blockers as apply, and removes only `metadata.teammate` from the
CURRENT metadata instead of restoring the whole saved object — binding
changes written after the move survive.

**11 — atomic settings write (`dcf74e9e5`).** `setup_teammate` writes
settings.json via a pid-suffixed staged file (0600 from creation), fsync,
one `os.replace`. The watching server sees old bytes or new bytes, never
partial JSON. (The roster side of 11 is the next lane, with 12 and 14.)

**12 — thread belongs to the bound instance (`5b2589b7b`).** Before any
checkout or send the carrier reads the thread record once and compares its
`providerInstanceId` with the binding's; a mismatch is fatal (exit 1, nothing
sent). A record naming no instance logs and continues (older builds must not
break). (The roster-side recovery fix is the next lane.)

**13 — error text and address pinning (`f376c1c79`).** Release notes carry
only the error type + HTTP status / exit code, never bodies or stderr. The
Paperclip address is pinned by `paperclip_base` in carrier.json (loopback
law: http, no userinfo, real port, no path) and a differing
`PAPERCLIP_API_URL` refuses the run before the first request. Absent key =
old behavior.

**14 — roster runbook / pair command.** Next lane (with the roster side of 11
and 12), per the principal's decision column. Not lane RF.

**15 — person-blocked issues (`ea7059c80`).** A blocked issue with an
answered marker delivers only when the carrier's own waiting line is among
the issue's comments; otherwise a person blocked it and it stays for the
board. Pending/slow markers continue the normal path.

**16 — messages window (`1753cfb3b`).** The marker scan walks
60/180/540/1620 messages (`scan_marker_deep`) on the task and return paths;
the feedback edge reads the deepest window. A window that never short-pages
(`window_exhausted`) posts one machine comment recording the send, which a
later wake checks before re-sending.

**17 — whose answer counts (`b795b2867`).** `last_result_comment` requires
authorType agent AND author id == the child's assignee; a newer bystander
comment never displaces the asked teammate's answer. The fallback names whose
comment it actually is.

**18 — ask block must end the reply (`dca0b5619`).** Nothing but whitespace
may follow the closing fence (the F9 guard); words after the fence mean the
teammate kept talking, and the reply is a plain answer. The code now holds
the rule the ask help text always stated.

**19 — return edge, oldest unanswered first (`828e37482`).** The asker's
return loop visits done ask children oldest-first with a per-child return op
(`{ask_op}-{child id}-ret`; the legacy unsuffixed op is kept when there is
exactly one child, for in-flight replays), reconciles an answered marker, and
refuses to re-ask an open one. A single→multi transition can send one
duplicate return message (a child completed between the two reads); noted,
bounded by exact-text dedupe.

**20 — comment read failures (`741a2d67f`).**
`comment_already_present` raises on a failed read instead of returning False;
deliver and handle_ask fail the run before any POST. `machine_note_once`
keeps its best-effort catch.

**21 — status writes (`6f6fc77f9`).** `deliver` reads status before its write
(done/cancelled are kept); `release_issue` moves only in_progress→todo; a
blocked issue stays blocked with its note.

**22 — post-delivery failures (`ff266c318`).** Once the answer is on the
issue, later exceptions log one machine note and return 0 — no release, no
status write. The coding-job call path gets the same guarantee at the
carrier's catch (the block itself is outside this lane). Output doc keys are
`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.

**23 — redirects (`ac1ad2ca8`).** A `_NoRedirect` opener refuses every 3xx;
the Authorization header can no longer ride a redirect to another origin.
(HTTPError carries type+status only.)

**24 — sent_here arming (`2630634bb`).** The flag arms only as `t3.send`
issues; a question landing between the clear poll and the send's pre-check
now logs "a question landed again" and keeps staying, instead of waiting on
a marker that was never sent.

**25 — checkout 409 (`44b1679ee`).** On 409 the carrier re-reads the issue
and the fresh row decides: this run holds it → proceed with the fresh read;
another run holds it → real refusal. A stale inbox row no longer makes a run
skip its own assignment.

**26 — machine-prefixed answers (`ad127abc0`).** An answer beginning with a
machine prefix (`[coding-job]`, `[t2-carrier]`) is stored under an explicit
`Answer:` line, so it is never mistaken for a carrier line downstream.
Exact-text dedupe is preserved.

**27 — output block F9 guard (`878a9d5c9`).** Same end-of-reply rule as the
ask block. Gap note: the output format has no in-carrier help text; it is
taught in `integrations/mmos/T45_MILESTONE_LOOP.md` (outside this lane's edit
surface). A teammate that writes prose after its output block now silently
loses the document (the comment still delivers). The milestone doc should
state the end-of-reply rule when next edited.

**28 — description label (`5c33ee204`).** A leading `description:` label on
the first description line is stripped; unlabeled and later lines verbatim.

**29 — setup base pinning (`f242115f0`) — credentials surface.**
`setup_teammate.Http` pins its base with `urlsplit`: http, loopback host, no
userinfo, real port, no path/query/fragment. The old string-split parse
accepted https, portless, path-carrying and malformed-port bases.

**30 — unrecognised board shape (`3fad291ba`) — admission surface.**
`rows_of` dies on a page shape it does not recognize instead of returning
`[]`; apply, rollback, refresh-carrier and check all change nothing on a
misread. An `{"error": …}` page can no longer read as "no open issues".

**31 — preimage reuse (`c90fbff67`).** When a preimage exists and the agent
was not moved, the saved values are compared with the agent's current values
in memory (neither side printed); all equal → the file is reused and the move
finishes. Nothing is deleted; exclusive-create is preserved.

## Attack round (deepseek-v4.1-flash, effort max, on pinned a3721efd0)

Read-only attacker on the finding-2/3/4 fixes; 16 findings, all dispositioned:

- **A1 window truncation** — not live at HEAD: R2a-16's lookback + the
  issue-side send record already implement the attacker's own suggested
  guard. No change.
- **A2/A3 rule-A fail-open / dead-run prose** — FIXED `fd1679a7c`: `_marker_run_open`
  reads thread.status; running/queued with no activeRunId pends, dead-run
  statuses never deliver prose, a newer latestRunId still closes the turn.
- **A4 mutable ask marker** — RECORDED NOT FIXED: closing it needs a
  persisted ask-op record (protocol migration, principal decision). At HEAD
  the structural rule + blocker-set binding + ask-cap bound the blast radius
  of a forged child, but a content edit of the parent between ask and return
  can still mismatch the recomputed marker.
- **A5/A9 forged or duplicate child** — FIXED `0bd918e68`: with
  `blockedByIssueIds` recorded, only a child in the blocker set can satisfy
  or suppress the return edge.
- **A6/A7 children walk** — FIXED `4a894bb79`: the walk continues on any
  non-empty page, stamps the parentId the query proves, dedupes, stops on the
  empty-page confirm. (A7 scenario A — a server that serves an unreadable
  parent — recorded: the tri-state park is the principal's; the client treats
  an absent field as unbound as before.)
- **A8 asked child + coding-job door** — FIXED `a28021a1a`: an asked child's
  reply is never parsed for a coding-job block.
- **A10 spoofable marker** — RECORDED NOT FIXED: a per-issue send nonce is a
  protocol migration (principal decision); the marker remains a checksum of
  public text, with the structural and blocker-set guards above.
- **A11 cap poisoning** — accepted trade-off: the cap counts marker-shaped
  children, so overcounting only refuses asks (never loosens).
- **A12 return-path ask parse** — FIXED `cb91f7941`: the asker's post-return
  reply runs the same ask path with the parent's op id.
- **A13 id charset** — FIXED `42a9f3ef8`: the ask-child marker regex covers
  every id `op_id` can produce.
- **A14/15/16 title fallback / cap edges / same-text ask reuse** — FIXED
  `d6fc7a9d1`: marker-only titles get the plain label "Asked work"; the cap
  coerces once (non-numeric → 3, <1 → zero); ask reuse matches the ask itself
  (assignee + sanitized title).

### Late second attack child (kimi-k3.1-pro, finished after the model-rule change)

Started before attack rounds moved to deepseek-v4.1-flash; the Chairman let it
finish. It analyzed the same pin and its list reduces to the round above plus
one genuinely new residual and several sharpened notes:

- **K1 forged return edge on a never-asked parent — RECORDED, needs one
  server fact before fixing.** The blocker-set fix (A5/A9, `0bd918e68`)
  filters children only when the parent HAS a recorded blocker set
  (`wake_carrier.py` `if blocker_ids and ask_children`). Every carrier-asked
  parent records one (`block_issue` since the ask feature was born, pre-R2a),
  but a parent that never asked has none — so a board-side forger who creates
  a child on the victim's issue with the computed marker, sets it done and
  adds an agent comment fires `handle_return` on the victim: the task is
  never sent, the attacker's text enters the victim's thread as
  "Their answer", and the victim's reply is delivered as the issue's answer
  with in_review. A forged **todo** child on a blocked parent additionally
  skips the person-blocked probe branch (finding 15). Exploiter needs board
  write rights (issue create with foreign parentId + status + comment) —
  insider capability, same class the attack round assumed; a teammate agent
  alone cannot (no board token; its only channel is its thread). Fix sketch,
  one line + test: marker-matching ask children with no recorded blocker set
  → leave the issue for a person. **Gated on a server fact the principal
  owns:** does resuming a blocked parent clear `blockedByIssueIds`? If it
  never clears, the tighten is safe; if it clears, the legit return edge
  (children done → board resumes) runs with an empty set and the tighten
  would strand every legit return — fix server-side or snapshot instead.
- **K2 parent edit defeats depth one** — new consequence of recorded A4,
  same root cause: edit the parent's title/description between ask and
  return and the recomputed marker mismatches, so the asked child reads as a
  plain task — its reply can carry an ask block (grandchild; depth one
  bypassed) and the parent is stranded as "blocked, no ask child". Strengthens
  the case for the persisted ask-op record; no new fix here.
- **K3 marker message with no runId reads as absent** — `scan_marker` treats
  a user message beginning `[op]\n` whose `run_id` is `None` as no marker
  (possible duplicate send, bounded by first-wins on the next scan).
  Defensive-only shape: the live server always sets run fields on messages
  (the principal's recorded note covers this family). No change.
- **K4 cap undercount** — a board edit that removes the marker from a child
  description frees cap slots (A11 counted the overcount direction; this is
  the undercount). Consequence: extra ask children on an issue whose
  participants actively conspire; each still blocks and goes to another
  teammate. Accepted with A11.
- **K5 10-page children bound** — beyond ~10 pages of children the walk
  truncates (finding 4's designed bound); not practical, recorded.
- **K6 return op from `children[0]`** — mooted at HEAD by finding 19's
  per-child ret ops (`828e37482`).
- **K7 self-ask via roster alias** — verified caught (id equality).

## Gaps left open, deliberately

- **Finding 20's hold is conservative**: a comment-list read failure during
  the finding-15 check counts as "no carrier line" and holds the issue for a
  person rather than delivering. Fail-closed by design; revisit if the board
  shows stuck issues.
- **Finding 19 single→multi transition** may send one duplicate return
  message (see above).
- **`window_exhausted` on the return edge** raises CarrierError (release,
  exit 1) — an unreadable return marker is never guessed at.
- **K1 forged return edge on a never-asked parent** (see the late-second-
  attack subsection above): guarded only for parents that recorded a blocker
  set; closing it needs one server fact (does resume clear
  `blockedByIssueIds`?) — principal decision.
- **ATK 4 / A7-A / A10** are recorded protocol migrations for the principal,
  not silent omissions. K2 is a new consequence of the same A4 root.
- **27's help-text gap** (above).
- **WebFetch** stays denied; see finding 1.

## Install notes for the principal

- Run `refresh-carrier` for each teammate after merge: carrier.json may gain
  `paperclip_base` (finding 13) and `delivery_reserve_sec` (finding 8);
  `max_asks_per_issue` (finding 4) and `thread_lock_dir` (finding 7) are
  optional — absent keeps the defaults (3; the config file's own directory).
  A hand-added `coding_job_door` key is preserved by refresh-carrier or it is
  NOT a lane RF defect (recorded separately).
- The thread lock needs nothing installed: the lock file appears in the
  carrier config's directory on first overlap.
- No server, port, browser or live journey was touched by this lane; the
  Paperclip server files were read read-only (finding 7) and no filename
  matching the forbidden patterns was opened.

## Round 2 (2026-11-11) — fixtures from the real server's shape

The independent panel scored the round-1 delta "do not install as is" on
one decisive fact: the installed board (build 2026.1106.0) never serves
`blockedByIssueIds` on GET /api/issues/:id — relations arrive as
`blockedBy` summaries — so the blocker-set defence read a field that was
always empty in production. Round-1 tests passed because they injected
the field by hand.

### The fixture rule now in force

Every board answer in this lane's tests is built from sanitized captures
of the real server (`tests/mmos_board_fixtures/*.json`, GET-only against
the installed loopback board, existing issues only, ids kept, free text
placeholdered, no token in any file). The endpoint each capture came
from is listed in `tests/mmos_board_fixtures.py`. Two of those captures
are error bodies captured as they were served (the agent-scoped inbox
answers 401 to the board actor; the company agents list answers 400
without filters) — they document actor scope, not board shapes.

### Board fields the carrier reads, and whether the server serves them

field                      where read                                 served?
-------------------------  -----------------------------------------  --------------------
id / identifier / title /  issue GET, list, inbox, blockedBy          served (captures)
  description / status
assigneeAgentId            issue GET, list rows, blockedBy summaries  served
parentId                   issue GET, list rows                       served
blockedBy (summaries: id,  issue GET (parents)                        served (parent
  status, title, identifier, assigneeAgentId, …)                        captures)
blockedByIssueIds          issue GET                                  NOT SERVED on GET —
                                                                      legacy fallback for
                                                                      boards that did
activeRun                  inbox rows (agent token)                   served on the inbox
                                                                      projection; NOT on
                                                                      an issue GET
checkoutRunId              issue GET (409 recheck)                    served (issue capture)
dependencyReady            inbox rows                                 served (projection)
updatedAt / createdAt      inbox rows / comment rows                  served
body / authorType /        comment rows                               served
  authorAgentId / authorUserId
author.id / authorId       comment rows (last_result_comment)         NOT SERVED — read
                                                                      removed this round
kind / status /            interaction rows                           served
  idempotencyKey / result(.reason)
metadata.teammate.t3       agent GET                                  served

An agent-scoped inbox read cannot be captured with the board actor (the
401 above is the proof); its field list is taken from the installed
projection. Every not-served field above was a finding and is repaired
or removed this round.

### Repairs (this round, red test first)

- 612fc80d9 — the return edge derives its blocker set from the served
  `blockedBy` summaries; a marker-matching done child with no recorded
  relation is left for a person; `last_result_comment` matches
  `authorAgentId` (the served field).
- 651bdce86 — an identical re-ask no longer re-blocks the parent on a
  DONE child (reuse scan checks status).
- 225640be5 — WAIT / unreachable / unreadable coding-job outcomes carry
  a retry line and are re-issued on a later wake; unreadable door
  answers are transient.
- 57c3dc2db — an unreadable interactions list fails the run instead of
  reading as "no feedback" at exit 0.
- af8f6d7d4 — multi-child returns deliver this run's answer, not the
  last-processed one; the create-failure read-back adopts only this
  ask's child; a second ask merges the blocker set instead of replacing
  it; ask action titles are marker-sanitized.
- c25958dbb — re-apply respects changes made after the move (a rotate
  refuses instead of reverting); rollback refuses when a third party
  changed the adapter after the move and marks the result file.
- a6d87be66 — the dev-instance client refuses redirects and prints
  status only; an unsignalable pid means the server runs; issue-list
  reads walk pages; rotate waits for an empty board.
- 58d85ba9a — failed board reads stop lying (comments read, children
  shape, reply-wait tolerance); the 409 recheck reads `checkoutRunId`;
  the live config is written staged at 0600.

### R8 and R11 stay as recorded

- **R8** (a forged-child marker surviving the blocker-set tighten on a
  never-asked parent): closing it fully needs the ask operation
  persisted as board state (on the child or the parent relation) rather
  than inferred from the title hash — an A4-class protocol migration,
  decided by the principal, not patched silently here.
- **R11** (the carrier is not pinned to an exact source revision): the
  pin is an operator-facing config change that belongs to
  refresh-carrier/install time; deciding it here would couple a running
  fleet's wake path to this delta.

### Accepted with a reason (not fixed this round)

- **R23 waiting-note discriminator** — by design (panel q3-8): the
  waiting note is a person-facing line, not a machine protocol.
- **R24 feedback single ~1620-char read / clamp** — a t3 server fact;
  changing the read depth needs a server-side answer, not carrier code.
- **R25 content-edit op change** — A4 protocol migration, principal
  decision.
- **q2-4 / q2-5 / q2-6** — t3 server facts (NEEDS SERVER FACT).
- **R20a deep window per poll** — accepted: read amplification on every
  wake for a window the marker discipline already bounds (R20b's
  tolerant read is fixed).
- **TOCTOU windows on accept/reject** — acknowledged: bounded by
  idempotency keys and status guards; a transactional board API is a
  server change.
- **Directory-mode cosmetics** (0700 on files vs dirs) — no enforcement
  gap; the files that carry secrets are 0600.

No panel finding was judged false after reading the code; none is
refuted.
