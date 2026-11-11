# Mastermind OS program plan V4

Date: 2026-11-10. Owner: program principal (Fable). Replaces `PROGRAM_PLAN_V3.md` on the
shell, conversation and runtime decisions. V3 sections 7 (boundaries) and 8a (one initiator
per effect) stay in force. How the team works stays in `OPERATING_METHOD_V3.md`.

Sources: Chairman message of 2026-11-10 (Hermes and its gateway are persistently buggy;
Paperclip has no streaming chat; T3 Code has been as smooth as Claude Code and Codex);
Revision 7 source brief `docs/plans/2026-11-10-t3-team-conversation-reconciliation.md` at
`35693b8d3` (documentation PR #2433, not ours to edit). The Revision 7 masterplan file was
not available to this session: the attachment named "(7)" is Revision 6 (same SHA-256,
`ea887b4f…`). This plan is built from the brief and from our own checks.

## 1. What changed and why

| V3 said | V4 says | Evidence |
| --- | --- | --- |
| Paperclip is the shell the Chairman looks at | Paperclip is the company and work backend. The product the Chairman uses is a conversation. | Paperclip has no streaming chat. Its strength is projects, tasks, routines and results. |
| Hermes is the runtime of every teammate | Hermes is optional. New teammates run as T3 threads. Existing Hermes conversations stay where they are. | 2 of the 13 installed agents are in error; the gateway is the session writer for every Hermes client, so a different Hermes client does not avoid it. |
| Every feature is a Paperclip plugin page | Conversation comes from T3. Plugins are for backend joins and work views only. | This whole program has run on T3 threads for days: streaming, tools, queue, steer, restart, pending requests, child threads. |
| The native app is a thin window on Paperclip | The native app is a thin window on a T3 client, with Work as a second view. | The window lane already built a locked loopback-only window with no native commands. |

## 2. Decisions

1. **Conversation is T3, used whole.** The Mastermind window is a client of a T3 server. We
   do not extract the chat component into the old app and we do not write a chat engine.
   The T3 web client is 1,869 source files, its chat view is 3,999 lines, its client runtime
   is 392 files, and the old app shares none of its foundations. The T3 server already has a
   supported path for a second browser client on loopback (policy `loopback-browser`:
   one-time token, then a session cookie) and a headless serve mode. We use that path.
2. **Then a thin maintained fork, only where Team must differ.** Team needs a teammate list
   instead of a project list, and work cards in context. That is a small fork of the T3 web
   client at a pinned commit, served by the same server, with the MIT notice kept. It starts
   only after decision 1 is proven on screen. This is where we differ from the brief, which
   lists extraction first and the fork as the fallback.
3. **A teammate is a binding, not a process.** Company actor (the existing Paperclip agent
   id) + charter + a T3 provider instance whose home holds the persona and memory + one
   replaceable primary thread + task threads. The persona lives in the runtime's own
   configuration, never in a title or a first message. No new agent registry.
4. **First runtime is the one that already works.** New teammates start on T3 threads over
   the Capacity Fabric provider, which is how every lane of this program runs today.
   DeepSeek Harness is a side qualification, not a gate: its ACP mode sends finished
   messages, not live text.
5. **Paperclip keeps the records.** Company, agents, projects, issues, routines, results.
   Work is shown from Paperclip (its own pages first; selected native views later). We do
   not rebuild those screens.
6. **Live conversation and work return are two channels.** T3's stream is the conversation.
   The existing TeamLink binding (issue to thread, result, explicit acknowledgment) is the
   work return. No second watcher.
7. **One actor at a time.** All 13 installed agents dispatch through `hermes_local`. The
   installed Paperclip build also ships `process`, `http`, `acpx_local`, `claude_local`,
   `codex_local`, `deepseek_local` and `kimi_local` adapters. The dispatch join is proven on
   a test agent in the isolated dev instance first. Changing an installed agent's adapter is
   a separate act, one agent at a time, with the old heartbeat fenced, and is not part of
   any dev lane.
8. **Governed launch stays closed.** A usable T3 screen is not admission. Coding jobs keep
   Executive as the admission owner through the socket door and the engine from L4 and L1.
9. V3 decisions 2 (no login for local use), 7 (production Executive release off the
   critical path), 8 (permanent improvement crew) and 9 (one initiator per effect) stand.

## 3. What stops, what carries over

Stops: Paperclip plugin pages as the product surface; the module map of the old app; the
cold-agent test on module pages as a critical-path item; the window's load proof against
`127.0.0.1:3100` as the product proof; any new work on the Hermes panel as the Team default.

Carries over, unchanged in value:

| Asset | From | Use in V4 |
| --- | --- | --- |
| Locked loopback-only window, dev bundle | L8 | The Mastermind window. The origin becomes a setting. |
| Isolated Paperclip dev instance and module template | L9 | Test bed for the actor dispatch join and for TeamLink. |
| `mastermind-core` module (roster truth, tool, health check) | L9 | Backend and Work view. Not the front door. |
| Executive socket door, peer-uid admission | L4 | Local admission for coding jobs. |
| Coding-job engine, admit-gate fix, reuse map | L1 (closed, trunk `1bf80ab3b`) | The governed coding job in T4. |
| Thread-list and execution-return read producers | L6 | Feed for teammate and work views. |
| Durable T3 adapter state and its five-scenario canary | earlier waves | Kept. Not repeated. |

## 4. DONE_WHEN

1. Opening Mastermind OS on the M2 needs no login and opens Team: a list of teammates and
   the selected conversation.
2. The Chairman sends a message to one teammate and sees live text and tool activity from
   the real provider. Queue, steer and a pending request work.
3. Switching to Code shows the same thread in the full T3 workspace. No new provider session
   starts. After a reconnect or an app restart the same thread and draft are there.
4. Two teammates answer with visibly different personas and tools, fresh and after resume.
   One primary thread is rotated and the teammate keeps its identity and its memory.
5. One company actor is woken through Paperclip, runs in its T3 thread, checks out its
   issue, returns the result to the same issue and has it acknowledged. The old wake owner
   does not also fire.
6. One real task produces one real output that opens from the issue and from the
   conversation that asked for it.
7. One routine fires once with the window closed, with one trigger owner and one result.
8. One real item under "Needs you" is cleared by its action and clears only that item.
9. An existing Hermes conversation still works on its own owner.
10. V3 DONE_WHEN 5 and 9 (a task that needs code becomes one governed coding job; an
    interrupted job is recovered as the same job) and 8 (the improvement loop has run once).

## 5. Lanes

| Lane | Outcome | State |
| --- | --- | --- |
| T1 shared conversation | DONE_WHEN 1 to 3, in the dev bundle against an isolated T3 server, then paired to the real one by the principal | stage 1 accepted 2026-11-10 at trunk `6a2634bb6` (stock client signs in, opens one thread by URL, queues, survives a restart, two views; see `T1_SHARED_CONVERSATION_FINDINGS.md`). Stage 2 (the window) starts when L8 has returned |
| T1s live answer text | Claude-driver threads stream answer text the way Codex-driver threads already do | accepted 2026-11-10 at trunk `1bc6b7574` (patch sha256 `661566e1…5400`, 355 tests in the principal's run; see section 11) |
| T6 team server | An always-on headless T3 server owned by Mastermind, separate from the Chairman's T3 Code app, that the window and the teammates use | **accepted and installed 2026-11-10** at trunk `54da298e1`. See section 12 |
| T2 teammate binding and actor dispatch | The binding record on existing owners; DONE_WHEN 4 and 5 on a test agent in the dev Paperclip instance | accepted 2026-11-10 at trunk `da2097e4b` (two test teammates, personas and tool limits, rotation, one wake one return, attack pass with one defect found and fixed; see `T2_TEAMMATE_BINDING_AND_DISPATCH.md` and section 10) |
| T3 Team view | Teammate list and work cards. **No fork first:** the stock T3 client already shows a roster when each teammate is one pinned, titled thread in a "Team" project | investigation (T3i) accepted 2026-11-10 at trunk `c7dd3ef4d`; see section 13 and `T3_TEAM_VIEW_OPTIONS.md`. **Closed with no fork 2026-11-10** (T7 verdict: fork needed for nothing; section 14) |
| T7 team roster | Two real teammates (Assurance, Design Lead) set up on the team server as pinned threads, checked in a headless browser, with the eight open questions answered | **accepted 2026-11-10** at trunk `e1b338021` (39 tests in the principal's run; see `T7_TEAM_ROSTER.md` and section 14) |
| T45 milestone loop | DONE_WHEN 6, 7 and 8 on the two test teammates in the dev instances: assignment alone starts the work, one task with one output that opens from the issue and from the asking conversation, one routine fired once with no window, one attention item cleared | **accepted 2026-11-10** at trunk `d690165a7` (all eight items with live evidence, attack pass held; see `T45_MILESTONE_LOOP.md`) |
| T1w native window | The Mastermind window opens on a teammate's conversation on the team server, shows work live, survives a server restart | **accepted 2026-11-10** at trunk `f9457a0f5`; paired to the team server by the principal (section 15) |
| CO cut-over | The two installed Paperclip agents run through the carrier into their Team conversations | **done by the principal 2026-11-10** (section 15); tool `tools/mmos_teammate/cutover_installed.py` |
| T4b governed coding job | DONE_WHEN 10: a task that needs code becomes one governed coding job through the socket door and the L1 engine | next |
| T8 the window people open | The installed Mastermind app opens on Team with no login; typing from the window; short names | next |
| L9 module platform | Land what exists (dev instance script, module, template), runbook, close | closing |
| L8 window | Land the locked window with a configurable origin, runbook, close | closing |
| L4 socket door | Listener, wiring, attack, close | closing |
| L6 producers and hygiene | Land items 2 and 3 and the manifest, close | closing |
| L11 improvement crew | Harness defects: replayed turns, false completion, shallow fetches | after the closers return |

## 6. Boundaries added by V4

- The Chairman's running T3 Code (port 3773) and the staged bundle (port 3774) carry this
  program. No lane restarts, reconfigures, pairs with or sends into them. Lanes use their
  own T3 server on their own home directory and port. Pairing the Mastermind window to the
  real server is one act by the principal.
- A pairing token, session cookie or connection string is a credential: read from a file,
  never printed, logged, committed or passed on a command line.
- No installed Paperclip agent is switched, paused, woken or edited by a lane. No Hermes
  credential becomes T3 authority. No timer is armed twice for one routine.
- The machine ran at a load of 300 on 24 cores on 2026-11-10. At most four drivers run at
  once, each with at most two children, until the closing lanes return.

## 7. Open questions, each with its test

| Question | Test | Owner |
| --- | --- | --- |
| Can the stock T3 web client be shown inside the Mastermind window and stay signed in across restarts? | A dev-bundle window on a dev T3 server; restart both; same thread and draft | T1 |
| Team, Code and Work as native tabs over separate locked views, or one host page with frames? | Build the smaller one; check cookies, focus and keyboard in both | T1 |
| Where does the teammate binding live without a new registry? | Two investigators read the Paperclip agent record, RuntimeBinding and the TeamLink plugin | T2 |
| Which Paperclip adapter wakes a T3 thread with the least new code? | `process` or `http` adapter on a test agent in the dev instance, one wake, one return | T2 |
| Does T3's server keep serving and scheduling with every window closed? | Headless serve, close the window, fire one schedule | T5 |

## 8. Amendment, 2026-11-10 14:30 UTC: what "live text" means today

T1 measured it and the principal checked the source at pin `0770446`. On T3 server 0.1.7,
a thread on the Claude driver (every Capacity Fabric model, and Claude itself) shows
thinking and tool activity live, but answer text only when a content block is complete:
`ClaudeAdapterV2.ts` handles `thinking_delta` and has no branch for `text_delta`. The Codex
adapter in the same source does stream answer text. A model that writes its answer as one
block (`glm-5.3`) therefore shows the whole answer at the end of the turn; a model that
alternates text and tools shows each part as it finishes, which is why long working
sessions on T3 feel live.

Consequences:

- DONE_WHEN 2 is read as: live thinking and tool activity, and answer text at least part
  by part. Text appearing while it is written is the target and is lane T1s, not a gate on
  T1 stage 2, T2 or the Team fork.
- The fix is a server patch carried the same way as the existing admission patch
  (`integrations/t3/upstream_patches/`), proven on the dev server. Putting it into the T3
  bundle the Chairman runs is a separate act and is not done by a lane.
- It is not a reason to fork the web client and not a reason to change provider.

## 9. Amendment, 2026-11-10 14:50 UTC: teammate binding and wake path decided

Two investigators (`kimi-k3.1-pro`, `deepseek-v4.1-flash`) read the installed Paperclip
build, the T3 source at the pin and the TeamLink diff independently. Memos:
`~/.mastermind/mmos_evidence/t2-binding-20261110/{kimi,deepseek}/MEMO.md`. They agree on
the binding and the persona. They differed on the wake; the principal settled it on the
code both cited.

- **Binding.** No new registry. The Paperclip agent row is the teammate. The T3 side is one
  key in the existing `agents.metadata`: provider instance, primary thread, a revision.
  The charter is the agent's existing instructions bundle. Paperclip's agent update has no
  expected-revision check, so binding writes are read, compare, write, read back. That is
  not atomic and is recorded as such.
- **Persona.** One T3 provider instance per teammate, each with its own home directory and
  a charter file passed as a launch argument, which T3 re-reads at every turn including
  resumed ones. The Capacity Fabric instance uses the Claude driver, so this applies to
  it. Text is guidance; tool limits are launch arguments, home settings and the tool set.
- **Wake.** TeamLink does not wake a T3 thread on behalf of a Paperclip agent; it wakes an
  agent through that agent's own adapter. So the agent needs an adapter that reaches T3.
  The smallest is Paperclip's `process` adapter running a small wake carrier: it holds the
  per-run Paperclip token, checks out the issue, sends one message to the teammate's
  primary thread, waits, posts the answer on the issue and exits. The token never enters
  the thread.
- **TeamLink (PR #2419)** is open, unmerged and held by its owner. Lane T2 does not depend
  on it. It stays the intended channel for issue-to-task-thread delegation once merged.
  Decision 6 is read accordingly.
- Open, owned by T2: which stock T3 surface the carrier uses to send to a thread and learn
  the turn finished.

## 10. Amendment, 2026-11-10 17:10 UTC: T2 accepted, the work loop is one mechanism

**Accepted (trunk `da2097e4b`, verified by the principal: refs, 18 carrier tests, evidence
files 01 to 11, dev instances stopped).** Two test teammates exist in the dev Paperclip
instance, each bound to its own T3 provider instance and primary thread. Their personas and
tool limits differ and survive a server restart and a thread rotation. One wake produced one
T3 turn and one comment equal to the thread's answer, with the issue left in review and a
pending confirmation. An independent attack found one real defect (a second answer comment
after a kill between comment and status); it was fixed and the fix replayed on the attack's
end state.

**Open question 7.4 is answered.** The `process` adapter wakes a small carrier
(`tools/mmos_teammate/wake_carrier.py`). The carrier sends through the stock
`t3 thread send <thread> - --wait --json` command, message on standard input. The command
makes its own short-lived session from the T3 home directory, so the carrier holds no T3
credential. No T3 patch and no T3 MCP client is needed for dispatch.

**Three facts from T2 that change the next lanes.**

1. Paperclip already wakes an agent when an issue is assigned to it. Today the carrier
   ignores that wake (the issue already carries the run as its active run) and only a
   separate keyed wake does the work. A routine or a teammate that assigns an issue sends
   no keyed wake. So the carrier must do the work on the assignment wake itself. This is
   the first item of the next lane.
2. The wake's idempotency key does not stop Paperclip from starting a second process run.
   One send and one comment are held by the carrier's marker in the thread, not by
   Paperclip. Every later edge must use the same marker rule.
3. The carrier's pending confirmation on the issue is an attention item with one action.
   It is the first real content of "Needs you". No second attention store.

**Decision: every Paperclip-to-conversation edge is the carrier.** Work goes out when a
teammate (or the Chairman, or a routine) creates an issue assigned to a teammate. Work
comes back to the asking conversation the same way: Paperclip wakes the asker's agent when
the issue it asked for returns, and the carrier sends one message with the result and the
link into the asker's primary thread. No watcher, no polling loop in a thread, and no
dependency on TeamLink (PR #2419 stays held and uninstalled). If the installed Paperclip
build has no wake for "work you asked for has returned", the lane reports that with
evidence before building anything in its place.

**Decision: one trigger owner for routines is Paperclip.** A Paperclip routine creates the
issue; assignment wakes the teammate. T3 scheduled tasks are not armed for teammate
routines. This answers question 7.5 the cheap way: the T3 server only has to keep serving
with no window, which T2 already ran.

**Lanes.** T4 and T5 run on the same two dev instances and the same carrier, so they are
one lane with one writer: T45. The governed coding job (DONE_WHEN 10) becomes T4b and
follows it; it is not part of the first milestone.

**After the dev proofs, two acts stay with the principal:** pairing the Mastermind window
to the real T3 server, and moving one installed Paperclip agent onto this path (the six
steps in the T2 note), with its old heartbeat fenced first.

## 11. Amendment, 2026-11-10 17:40 UTC: T1s accepted, the team gets its own T3 server

**T1s accepted (trunk `1bc6b7574`).** The patch makes the Claude driver send answer text as
it is written, into one item per message, the same way the Codex driver does. The
principal reran the adapter and filter suites on pin plus patch: 355 passed. An attack
found that the unpatched server writes the same text two or three times when a message
mixes text and tools; the patch fixes that too.

**"Live text" in T3 is paragraph by paragraph, by upstream design.** T3 has two settings
for answer text: whole turn, or paragraph (the default). In paragraph mode the server
releases text at a blank line, a list item, a closed code block or a heading, at most
every 400 ms. That rule applies to every driver, Codex included. The proof prompt I
pinned for T1s (count 1 to 40 on tight lines) has no such boundary, so it showed no
change; the fault was my prompt, not the lane. With paragraphs the patched server grows
the answer during the turn. We keep upstream's rule and add no third mode. DONE_WHEN 2
now reads: thinking and tools live, answer text paragraph by paragraph.

**Decision: the team runs on its own T3 server, not inside the Chairman's T3 Code app.**
The facts that force it:

1. The Chairman's server (port 3773) is a child of the T3 Code desktop app. When the app
   quits, it stops. A routine with no window open cannot depend on it.
2. The app is a vendor-signed, self-updating bundle. Our server patch cannot go into it
   without breaking the signature and the updates. Port 3774 is not listening today.
3. Adding a teammate means adding a provider instance to that server's settings, which
   T2 did with the server stopped. Stopping the Chairman's server stops his work and this
   program.

So "the real server" in this plan now means the **team server**: headless, loopback only,
kept alive by launchd, its own home directory and port, started from the same T3 release
the Chairman runs. The Mastermind window pairs to it. Teammate threads live on it. The
Chairman's T3 Code app is never restarted, reconfigured or patched by this program.
Installing the team server is one act by the principal after lane T6 proves it in a dev
root. The patched build is a switch on the team server, off until T6 shows that the stock
and patched builds can share one home directory without harming state.

**What this changes in DONE_WHEN 3** ("Code shows the same thread"): the T3 Code app shows
a team thread only if it can add the team server as a second environment. T6 answers that
from the source and a dev proof. If it cannot, team threads open in the Mastermind window
and in a browser, and DONE_WHEN 3 is met there.

**Offered upstream, not done:** the duplicate-text fix and the streaming patch are useful
to T3 itself. Sending them upstream is a public act under the Chairman's name and waits
for his word.

## 12. Amendment, 2026-11-10 18:50 UTC: T6 accepted, the team server is installed

Lane T6 returned and the principal verified it: 23 tests pass, the launcher selftest
passes, every evidence file is valid JSON, and the lane left no launchd job, listener or
home behind. The principal then installed the real server. The note is
`integrations/mmos/T6_TEAM_SERVER.md`; the tool is `tools/mmos_team_server/team_server.sh`.

**What is running now**

| Item | Value |
|---|---|
| launchd label | `com.mastermind.t3-team` (user LaunchAgent, KeepAlive, no secrets in the plist) |
| Address | `127.0.0.1:3780` only. The server process has no other listener |
| Home | `~/.mastermind/t3-team` (state in `home/userdata`, route keys in `fabric.env` mode 0600) |
| Server build | `~/.mastermind/t3-team-server/bin/t3`, a link to `t3-0770446-textdelta`: upstream pin `0770446` plus the T1s patch, bundle sha256 `37271af3a1c6…`, run by `/opt/homebrew/bin/node` |
| Pairing | `~/.mastermind/t3-team/run/access.txt` (0600). The token changes on every server start; a paired browser keeps working across restarts |

Checked on the real server by the principal: one turn on the stock build, `kill -9` and
back in about one second with the thread intact, a second turn after the revival, the
switch to the patched build, a third turn there, and the Chairman's T3 Code server
(pid 17210, port 3773) unchanged throughout. Not checked on the real server: answer text
arriving in steps in a browser. The lane showed 13 steps with this same build file in a
dev root; the principal's own attempt polled too slowly to see them.

**The team server does not run the Chairman's app.** The stock command `~/.t3/bin/t3` is
a wrapper around the T3 Code app bundle, so a team server on it would change whenever the
app updates itself and would run as a second copy of his app. The team server therefore
runs its own build from its own directory. Updating T3 Code no longer touches the team.

**Correction to the lane's report.** T6 wrote that the installed app carries a database
change newer than our build. It is the other way round. The installed app is 0.1.7,
built from upstream commit `322f6544dfad` of 2026-11-04. Our pin `0770446` is 408 commits
later and adds database change 80 (a `thread_mode` column on scheduled tasks). So:

- Our build moves a home forward to 80. The stock app's server then opens that home, logs
  one warning that it does not know change 80, and still works. The principal tested this
  on a throwaway copy of the team home.
- The team home is at 80 now. It was switched while it held one test thread, so nothing
  of value went through the change.
- The stock command prints that warning on standard output, in front of its JSON. A
  script that reads JSON from `~/.t3/bin/t3` against the team home will fail.

**Rule that follows:** anything that talks to the team server uses the team server's own
command, `~/.mastermind/t3-team-server/bin/t3`, with `T3CODE_HOME=~/.mastermind/t3-team/home`.
That includes the wake carrier's `t3_bin` setting for every teammate bound there.

**DONE_WHEN 3, answered.** The T3 Code app cannot hold a second server connection. T3's
supported way is an environment link: `t3 pair` on one server, `t3 environment link` on
the other, and the linked server's threads appear as a group in the sidebar. It needs the
Labs setting for linked environments on both sides. On the team server that is ours to
set. On the Chairman's app it is a change to his app, so it is his to make or to order.
Until then team threads open in the Mastermind window and in a browser, which section 11
already accepts for DONE_WHEN 3.

**Known limits of the install**

- It depends on `/opt/homebrew/bin/node`. A Homebrew upgrade of node changes the runtime
  under it. A pinned node copy is a small follow-up, not done.
- The build directory is a 4 GB copy of a full source tree with its packages. A packed
  build is a follow-up, not done.
- Nothing has run on it for days yet, and it has not been through a reboot.
- The seeded settings give it one provider, the Capacity Fabric route. Teammate personas
  are added when the first installed agent is moved, after T45 returns.

## 13. Amendment, 2026-11-10 19:15 UTC: the Team view starts with no fork

**What was asked.** Lane T3 was written as "a thin fork of the T3 web client". Before
paying for a fork, lane T3i read the client's source (pin `0770446`, read only) to find
the smallest change that gives a teammate list. Its memo is `T3_TEAM_VIEW_OPTIONS.md`.
The principal read it in full and checked four of its source citations; all four matched.

**Decision.** The Team view is built on the stock client first, with no code change:

| Part of the Team view | How the stock client gives it |
| --- | --- |
| Teammate list | One T3 project named "Team". Each teammate is one pinned primary thread titled `Name — role`. Pinned threads form a fixed block at the top of the sidebar, in an order we set, and stay there while working |
| Who is busy, who needs you | Each row already shows a status word (Working, Waiting, Approval, Input, Failed, Done and others), a running timer and the time of the last activity |
| Whose voice | Each teammate is its own provider instance with the teammate's name and an accent colour, so its badge shows on the row |
| Selected conversation | The window opens `http://127.0.0.1:3780/<environmentId>/<threadId>` |
| Work cards | A plain markdown link renders as a link with the site icon; a `t3-thread://` link renders as a live thread chip. The carrier writes the issue as a labelled link next to its marker |

**Three rules that follow**

1. The window never opens the server's root address `/`. The stock client starts a new
   empty thread in the most recent project when it lands there. The window always opens a
   thread address.
2. T3's own "needs you" means a pending request inside a running turn. A Paperclip
   `request_confirmation` is invisible in the sidebar unless the carrier writes it into
   the teammate's thread. So the carrier relays it there, with the issue as a labelled
   link. This is added to the carrier after T45 returns (T45 is the writer on the carrier
   now).
3. A turn that ends with a plain-text question shows as ready, not as "Input". A teammate
   that needs an answer must ask through the request mechanism or through the carrier.

**What the stock client does not give.** A separate role line under the name, one place
that adds up every "Needs you" item across teammates, and a per-thread field for extra
data (there is none; a thread can only be pinned, snoozed, settled, archived or marked
unread). These are the only reasons to fork. The memo sizes that fork at 100 to 200 lines
in one file (`SidebarThreadRow.tsx`), a file that upstream changed four times in five
days, so each upstream update would need the fork redone. A server-fed list (the memo's
candidate 2) is the most expensive and is not built.

**Lane T7 (started 19:05 UTC, GLM 5.3).** It makes the roster real on the team server
with two teammates named after installed agents, Assurance and Design Lead: a home,
a charter, a provider instance, a pinned thread and a write limit for each. It proves a
restart keeps the same thread and that "remember this" lands in the teammate's own
`CLAUDE.md`. It answers in a headless browser the eight questions the memo could not
answer from source (for example whether the pinned block reads as a list at rest, and
whether titles are cut off at window width), checks live text on the real server, and
returns a verdict line: "fork needed for: <list or nothing>". It writes
`tools/mmos_team_server/team_roster.py`, so a third teammate is one command.

T7 sets up the T3 side only. It writes nothing to Paperclip and moves no installed agent.
The installed Assurance and Design Lead agents keep running on Hermes until the cut-over
after T45, which then binds each agent to the thread T7 made. This replaces the last
line of section 12 ("personas are added when the first installed agent is moved").

**Fork decision is deferred to evidence.** If T7 returns "nothing", lane T3 closes with no
fork. If it returns a list, the fork is scoped to that list and nothing else.

## 14. Amendment, 2026-11-10 19:55 UTC: T7 accepted, two teammates are on the team server

**What is there now** (checked by the principal on the running server, not from the report)

| Item | Value |
| --- | --- |
| Project | "Team", workspace `~/.mastermind/t3-team/team-project` |
| Assurance | provider instance `assurance`, pinned thread "Assurance — quality & security", home `~/.mastermind/t3-team/teammates/assurance` |
| Design Lead | provider instance `design-lead`, pinned thread "Design Lead — product design", home `~/.mastermind/t3-team/teammates/design-lead` |
| Charters | persona prose copied from each agent's existing Hermes `SOUL.md`; nothing else was copied |
| Memory | each teammate's own `CLAUDE.md`; a fact told to each came back after a server restart and is on disk |
| Tool limit | read and search anywhere, write only inside its own home, no shell. Both refused a write to `/tmp` |
| Thread addresses | `~/.mastermind/t3-team/run/team_urls.json` (0600, no credential) |
| Tool | `tools/mmos_team_server/team_roster.py apply|status <spec>`; a third teammate is a spec block, one `apply` and one pin |

**Lane T3 closes with no fork.** In a headless browser at 1280 by 800 the two pinned rows
read as a roster: name, status word, time, coloured badge with the teammate's initials. Live
text showed eight separate states on the real server. The sidebar is open by default on a
thread address. The carrier's marker wraps cleanly.

**What is not right yet, and what happens about it**

| Finding | Action |
| --- | --- |
| The role is cut off: "Assurance — quality & secu…" at the default sidebar width. The title box holds about 24 characters | Shorten role lines to fit when the next teammates are added. Needs a thread rename, which like pinning exists only in the web client |
| Pinning has no server command. It was done through the headless browser | Accepted. The paired browser profile for this is kept at `~/.mastermind/t3-team/run/browser-profile` (0700). It holds a session cookie, so it is a credential: the principal moved it there out of the evidence directory |
| The "Done" mark cleared for one teammate on opening and stayed for the other across two opens | Not chased. It follows a visit rule in the client that a headless open may not trigger. To be looked at in the real window |
| A pairing link from `run/access.txt` stops working about two minutes after the server starts | The window is paired with a freshly made code, not the start-up file. Lane T1w's note covers how |
| The page is still T3 Code to look at: its name, a project panel offering "Open in Cursor" and "Initialize Git", a composer hint about files and commands | Not a roster problem and not fixed by this lane. It is the first real reason a small fork might be wanted later, and it is a product call for after the first milestone |
| Teammates have no shell | Deliberate for now. Work that needs to run code goes through the governed coding job (lane T4b), not through a teammate's own shell |

**Settings reload.** The server reads `settings.json` again while running, so a teammate can
be added without a restart. This answers the open item from T45's brief.

**What T7 did not do.** It wrote nothing to Paperclip. The installed Assurance and Design
Lead agents still run on Hermes. Binding each installed agent to the thread above is the
cut-over, one agent at a time, after T45 returns with the carrier.

## 15. Amendment, 2026-11-10 20:55 UTC: both real teammates are cut over; the loop runs on the installed app

**What is true now** (each line read back from the installed Paperclip on port 3100 and the
team server on port 3780, not from a report)

| Item | State |
| --- | --- |
| Assurance | wakes through the carrier into its Team conversation since 20:32 UTC. Old run setup saved privately beside its home; `rollback` puts it back |
| Design Lead | same, since 20:44 UTC |
| Old wake owner | the timer was already off for both; the run command is replaced, not added to. Every wake below produced exactly one run in the company's run list |
| Window | the dev build of the Mastermind window, paired once to the team server, opens on a teammate by name: `tools/mmos_team_server/open_team_window.sh <instance-id>` |

**What ran, on the installed app**

| DONE_WHEN | Proof | Result |
| --- | --- | --- |
| 5 and 6: one wake, one run, one answer, one output | MAS-5, assigned to Assurance: a review of the cut-over tool itself | one run (2 min), one comment, document "Review of the teammate move tool", one request to the board. The work was visible live in the window. Four of its five findings were real defects and are fixed |
| 8: one "Needs you" item cleared by its action | accepting MAS-5 | issue done, "Needs you" 8 to 7, no further run |
| 7: one routine, window closed | routine "Check the teammate move tool against open review findings", one trigger for one minute | MAS-6 created at 20:41:00, one run, one answer (all four fixes confirmed, the fifth correctly left), trigger off and routine paused five seconds after it fired. Accepting it: 8 to 7 again |
| Two teammates on one task | MAS-7, assigned to Design Lead: names that fit the Team list, and the three changes that matter most | three runs and no more: Design Lead worked and asked Assurance (MAS-8), Assurance answered, Design Lead was woken with the answer and finished. Document "Names for the Team list". Its request to the board is **left open on purpose** as a real item for the Chairman |

Evidence: `~/.mastermind/mmos_evidence/cutover-assurance-20261110/` (LEDGER.md) and
`~/.mastermind/mmos_evidence/t1w-team-20261110/`.

**What changed in the carrier for the real app**

- The T3 command line now gets the team server's port and never the Paperclip run token.
- The task message carries a link to the issue page. The link comes from carrier settings
  only and must be a loopback address.
- The task message tells the teammate whom it can ask and how. Names come from carrier
  settings. A teammate that was itself asked is not told this, so asks do not chain. The
  example quoted back unchanged is not taken as an ask.

**Rules added**

- `cutover-preimage.json` in a teammate's home holds the agent's old run command and
  environment. It is private (0600), never printed, never copied into evidence or the repo.
- A cut-over is one agent per spec and refuses while the agent has open work, a live run or
  a timer that is on. It looks again right before the change. Paperclip has no conditional
  update, so this narrows the gap and does not close it.
- The carrier file is shared by all moved teammates. Re-running `apply` for one teammate
  updates it for all.

**DONE_WHEN, honestly**

| # | State |
| --- | --- |
| 1 | The dev build opens on Team with no login prompt. The Chairman's installed app is not switched yet (lane T8) |
| 2 | Live text and tool activity seen for carrier-sent work. Typing from the window against the team server is not tested yet (lane T8) |
| 3 | Not done. Needs the linked-environment switch in the Chairman's T3 Code app, which is his to make or order |
| 4 | Two real teammates with different charters and tool limits. Account rotation proven on test teammates only |
| 5, 6, 7, 8 | Done on the installed app, above |
| 9 | Not checked yet |
| 10 | Not started (lane T4b) |

**Next**

1. T8: build the window people actually open so it lands on Team with no login, make typing
   work there, and apply Design Lead's short names (`Assurance — quality`,
   `Design Lead — product`) in the roster spec and the live titles together.
2. T4b: the governed coding job.
3. Team server hardening: its own Node, a packed build, a restart-after-reboot check.
4. Check 9: an existing Hermes conversation still works.


## 16. Amendment, 2026-11-10 22:25 UTC: check 9 answered, a real task exposed two carrier faults

**Lanes.** H9 (read-only diagnosis of Hermes health and the attention list) is accepted:
`H9_HERMES_AND_ATTENTION_DIAGNOSIS.md`. T8 (the window people open), T4b (the governed coding
job) and TSH (team server hardening and short names) are still running.

**Check 9, the result.** MAS-9 gave Secretary, still on Hermes, a one-comment task with every
fact in the task text. Paperclip woke it, the gateway took the message and the model answered
111 times. Secretary ran for 30 minutes, used tools 53 times, tried twice to patch its own
config (refused), opened a browser, and was stopped by the 30-minute limit with nothing posted.
So: the Hermes transport works; the Hermes agent did not do the task. Evidence:
`~/.mastermind/mmos_evidence/h9-check9-20261110/LEDGER.md`.

The same task, unchanged, was then given to Assurance on the carrier. It ended done with one
record comment, but only after two faults of ours were found and fixed on the way:

| Fault | Effect on MAS-9 | Fix (trunk) |
| --- | --- | --- |
| A board note on a task with no answer yet was read as "the board declined your answer", and the task text was left out | Assurance got a revision with no task. It refused to guess, which was right | `8b532902c`: only a declined confirmation counts as feedback; board notes travel with the task; a revision carries the task when the thread never had it |
| A turn that waits for a person holds the thread. Each retry queued the same message again and added the same "waiting" line | Three copies queued, three identical lines, then Paperclip set the issue blocked | `b752daa02`: nothing is sent while a question waits; the line is said once |

Two tools came out of it. `cutover_installed.py refresh-carrier <spec>` installs a carrier fix
while teammates have open work (plain `apply` refuses then); it still refuses during a live
run. `roster_browser.js answer` answers a teammate's waiting question through the paired
headless tab, because the T3 command line has no way to do it.

**Attention list.** MAS-1 (stale onboarding task whose assignee was terminated) is cancelled;
that removed three rows. Four are left: the MAS-7 confirmation kept for the Chairman, two
blocker rows on MAS-4 and one agent error alert. The last three belong to the Astra session's
work and are not touched.

**Decisions**

1. DONE_WHEN 9 is closed as checked, with the result above. This program does not repair
   Hermes agents. The answer to a Hermes agent that cannot do its work is to move it.
2. Secretary is the third teammate to move, after TSH lands, so it arrives on the hardened
   server. The two-teammate limit is lifted to three for this; no mass move.
3. New gap, queued behind T4b because it touches the same file: when a person answers a
   teammate's question in its conversation, nothing wakes the task. Today someone must also
   comment on the issue or move it back to todo. The fix is for the carrier run to stay with
   the question for a bounded time and finish in the same run.
4. The waiting-question half of DONE_WHEN 2 now has a real case: the question showed in the
   thread as a card with options and an answer box, and the row showed "Input". T8 still owes
   the same from the window people open.

**DONE_WHEN, honestly**

| # | State |
| --- | --- |
| 1, 2 | As in section 15; lane T8 |
| 3 | Not done; the Chairman's switch |
| 4 | Rotation on real teammates still owed |
| 5, 6, 7, 8 | Done on the installed app (MAS-5 to MAS-9) |
| 9 | Checked: transport works, the agent failed the task |
| 10 | Lane T4b |


## 17. Amendment, 2026-11-11 00:20 UTC: the governed coding job is accepted on dev, not installed

**Lane T4b is accepted** and merged into trunk at `4ec9e58dd`. Checked before reading its
report: the commit exists, the remote head matches, the evidence folder is there, its checkout
is clean, its dev servers and door are stopped, its own test sweep and the wider Executive
supervisor, runtime and T3-native tests pass on its head. I read the control-plane diff myself.
Runbook: `T4B_CODING_JOB.md`. Decisions: `T4B_DECISIONS.md`. Attack round:
`T4B_ATTACK_FINDINGS.md`. Evidence: `~/.mastermind/mmos_evidence/t4b-20261110/LEDGER.md`.

**What it proves, and where.** On a dev Paperclip (3190), a dev T3 server and a scratch
Executive store, a teammate's reply that asks for code becomes one governed coding job through
the socket door and the L1 engine. The lane reports four journeys; I did not run them again.

| Journey | Native launches | Result |
| --- | --- | --- |
| default | 1 | result returned to the task as a comment with the job identity |
| crash (door killed after launch) | 1 | a fresh door recovered the same attempt; no second job |
| wait (fleet full) | 0 | the task shows one blocker comment with the reason |
| undeliverable (unknown origin) | 1 | the task shows the refusal code |

The crash journey needed one engine change: a claim that lost its identity is adopted from its
durable provider receipt (`adopt_attempt` with a reattach id, read through
`provider_receipt_reader`). It is a change on a critical surface and goes into the bundle
review below.

**A boundary was crossed, and it is recorded.** During bring-up the door's proof helper ran
`t3 auth pairing create` against the Chairman's own T3 Code app (port 3773) instead of the dev
server: 13 codes labelled `t4b-door-worker` and one labelled `probe-dryrun`, each valid 15
minutes or less, between 21:47 and 21:53 UTC on 2026-11-10. The command line tool picks its
server from its home directory and port settings, not from the helper's address. The lane
reports every code expired unused: its own `pairing list` at 21:59 UTC showed 13 rows, each
never used. It did not delete them, since that would be a second write to the app. After I told
the lane not to touch that app again, it ran one more read-only `pairing list` there. I cannot
check any of this without reading the app's credential store, which stays off-limits; the
Chairman can see paired clients in the app's own settings. The fix is in the code: the door
refuses to start without a dev home and a dev port (3790 to 3810), and no pairing command runs
until the dev server answers. Test: `test_config_requires_the_dev_server_pin`.

**Decisions**

1. DONE_WHEN 10 is split. The recovery half ("an interrupted job is recovered as the same
   job") and the admission half are proven on dev. Neither is on the installed app.
2. The installed carrier may run trunk's carrier file, because the coding-job block does
   nothing without a `coding_job_door` entry in a teammate's config (read at
   `handle_coding_job` and `coding_job_help`). No real teammate gets that entry before the
   bundle review.
3. The CRITICAL review is split in two, so the part T4c waits on does not wait for the other
   lanes. Part one (lane R4b, started 00:35 UTC, read-only, Opus, which wrote none of it):
   the engine reattach (`executive_runtime.py`, `executive_supervisor.py`,
   `t3_native_composition.py`), `paperclip_result_delivery.py`, the door and the carrier's
   coding-job block. Part two, at the release tail once T8, TSH and CQ are in: the socket door
   for local admission, the shell-URL loader, the cut-over tool, the rest of the carrier and
   T8's pairing path.
4. New lane T4c, after that review: the coding job on the installed app. It owes the real
   door composition with a reconcile cadence (attack finding F8, reported and not fixed), a
   Paperclip writer credential for the return transport, and its own local Executive store.
   The production Executive is not that store and is not touched without the Chairman's word.
5. New lane CQ, running now: the carrier stays with a teammate's waiting question for up to 15
   minutes and finishes in the same run; text from a turn that has not ended is never
   delivered as the answer (seen once on MAS-9); the waiting line on the issue says where to
   answer. I test it on the installed app before it stays.
6. The eleven `t3/mmos-t4b-job-*` branches on origin are the journeys' evidence. They stay
   until the release tail, then go in one cleanup.

**DONE_WHEN, honestly**

| # | State |
| --- | --- |
| 1, 2 | Lane T8 |
| 3 | Not done; the Chairman's switch |
| 4 | Rotation on real teammates still owed |
| 5, 6, 7, 8 | Done on the installed app (MAS-5 to MAS-9) |
| 9 | Checked: transport works, the agent failed the task |
| 10 | Coding job and crash recovery proven on dev instances; installed app is lane T4c. The improvement loop has not run |


## 18. Amendment, 2026-11-11 00:30 UTC: the review says the coding job is not safe to build on

**R4b returned**: `R4B_REVIEW_FINDINGS.md` (15 findings, my decision on each, the reviewer's
reproductions). I re-ran the reproductions on trunk; all five reproduce. The reviewer found no
path to a second native launch. It did find that the new engine reattach strands the attempt it
adopts, that a reconcile pass during a live launch would cancel the only native thread, that a
crash at the wrong moment makes the door report a successful job as failed, and that a
worker's text can reach a teammate as the board's words. T4b's own attack round missed all four.

**What changes**

1. T4b's acceptance in section 17 stands as "works on the happy paths on dev". It is withdrawn
   as "ready to install". Nothing from it is installed, so nothing is rolled back.
2. Lane T4c is now the repair, on dev only: the engine findings first, then the door, then one
   owner for recovery (the door composes the real supervisor and runs a real reconcile, which
   also closes attack finding F8), then the journeys again plus four new ones, then an attack by
   a model that wrote none of it. Its first step is the pairing guard, before any server runs.
3. The carrier halves of findings 4, 5 and 12 go to lane CQ's thread when it returns, because
   it holds that file. The agreed line: every comment the door or the transport writes starts
   with `[coding-job]`; every carrier note starts with `[t2-carrier]`; the carrier never treats
   either as a board note, board feedback or an answer.
4. The coding job on the installed app becomes lane T4d, after T4c and after a review of T4c's
   diff. It still owes a Paperclip writer identity that is not the board, a decision on real
   task text as a worker prompt, and its own local Executive store.
5. Two things stay open on purpose: workers run as the same operating-system user as the door
   (so admission by user id cannot tell them apart; the door now also requires the request to
   be visible on the task itself), and the installed Paperclip treats anything on loopback as
   the board. Neither is this program's to change today.

**What this says about method.** An attack round by a cheap model on its own lane's diff found
twelve things and missed the four that mattered. For a critical surface the independent review
goes before acceptance, not at the release tail. The other half of that review (socket door,
shell-URL loader, cut-over tool, the rest of the carrier, T8's pairing path) therefore runs as
soon as T8, TSH and CQ are merged, before any of it is switched on for the Chairman.


## 19. Amendment, 2026-11-11 00:40 UTC: a teammate's question no longer strands its task

**Lane CQ returned and is merged** (`4938b2f9d`, 135 tests). I read the carrier diff line by
line, installed it for Assurance and Design Lead, and tested it on the installed app.

**The live test, MAS-10.** A real task for Assurance that needed one fact from a person.
One run (`96fd0332`, 60 seconds): the question appeared 25 seconds in; the task got one line
naming the teammate with a link to its conversation; I answered in the web page; the same run
delivered the finished reply 14 seconds later with its confirmation; I accepted; the task is
done. No half-finished text was delivered and no board action was needed to continue.
Evidence: `~/.mastermind/mmos_evidence/cq-20261111/`.

**Found while installing.** `refresh-carrier` replaced the carrier file and left each
teammate's settings file as written at cut-over, so a fix that adds a setting was installed
without it. Fixed on trunk (`905e85458`) with a test; both settings files now match their specs.

**Not proven yet.** What happens when nobody answers in time. The carrier ends the run with
the task unchanged; the installed Paperclip retries twice and then marks the task blocked; and
the carrier leaves a blocked task alone, so the line's promise that a comment wakes it is not
true today. This is item 5 of the lane's second task, and I test it live when it returns.

**Lane CQ, second task (running):** the carrier halves of review findings 4 and 5 (a comment
that starts with `[coding-job]` or `[t2-carrier]` is never a person's words, feedback or an
answer), the blocked-task gap above, a stricter check on the conversation link, the waiting
line reworded as Assurance proposed in MAS-10, and tests for the three behaviours the lane
said it had not covered. The door key stays unread by any installed teammate.


## 20. Amendment, 2026-11-11 01:10 UTC: an unanswered question is recoverable, proven live

**Lane CQ's second task returned and is merged** (`ff3552c58`, trunk `8a226cd39`, 151 tests).
I read the carrier diff in full and installed it for both teammates (carrier sha256
`69846ac9…`). Neither settings file has the coding-job door key.

**The live test, MAS-11.** Assurance's question wait was set to 60 seconds for this one test.
A real task that needed one fact from a person, and nobody answered:

| Time (UTC) | What happened |
|---|---|
| 00:58:55 | Task assigned; run starts |
| 00:59:20 | Question asked; the reworded line with the conversation link posted once |
| 01:00:22 | Run ends with the task unchanged; Paperclip retries (two more runs, neither posts the line again) |
| 01:03:56 | Paperclip marks the task blocked and names the board as recovery owner |
| 01:04:18 | I answer in the web page; the teammate finishes its turn; the task stays blocked, no run |
| 01:04:51 | I add one comment on the task; Paperclip wakes Assurance |
| 01:04:54 | The carrier finds the finished reply and delivers it with its confirmation, in a 4-second run |
| — | I accept; the task is done; the attention list drops from 4 to 3 |

So the line's promise holds: answer late, add any comment, and the work is picked up. The
blocked-to-in-review change works on the real server. The wait is back at 15 minutes for both
teammates. Evidence: `~/.mastermind/mmos_evidence/cq-20261111/unanswered/`.

**What the test also showed.**
- With the real 15-minute wait, Paperclip's two retries each stay with the question too, so a
  person has about 45 minutes before the task is marked blocked. The line says 15; it is the
  safe figure and I leave it.
- Assurance's own review in MAS-11: the `[t2-carrier]` tag at the front of the line reads as an
  error code to a first-time reader. The tag is what marks the line as machine text, so it
  stays until the window can hide it; that is a display job for the window lane, not a
  carrier change.

**Closed by this:** the carrier halves of review findings 4 and 5, and the blocked-task gap
from section 19. Still open on the coding job: everything in lane T4c.


## 21. Amendment, 2026-11-11 01:30 UTC: the improvement loop has run once

**Lane IMP returned and is merged** (`7781ccc1d`). It read the plan's amendments, the method,
the findings files and every lane ledger, and produced:

- `IMPROVEMENT_BACKLOG.md`: 29 defects of the working method and its tools, each a real event
  with its source, ordered by cost, with status checked against the repository. Three are
  open: Secretary still on Hermes (moves after TSH), the door's loopback check (lane T4c),
  and steps marked done before their check (now a lane rule).
- `SCOREBOARD_PROPOSAL_20261111.md`: rows for the V4 lanes. Its main finding is about the
  record, not the models: ten of twelve V4 lanes never wrote down which model drove them.
- Changes to the two developer skills, traced to backlog rows.

**What I changed from it.**
- `LANE_RULES_V4.md` has five new rules: work in pushed steps; a step is done only when its
  proof is on disk; every return names its models; an attack round is not a review of a
  critical surface; the `t3` command line picks its server from its environment.
- `OPERATING_METHOD_V3.md` has the new scoreboard rows, with the four lanes whose model I can
  state added, and a routing row: an independent review of a critical surface goes to Opus
  before acceptance.
- One skill line said readers filter any bracketed prefix. They filter two. Corrected.

DONE_WHEN 10's third part (backlog, scoreboard, skill updated from real lane findings) is met.
The loop's next run is due when T8, TSH and T4c have returned.


## 22. Amendment, 2026-11-11 01:55 UTC: the model router failed, three lanes died, and one lane is split

**What happened.** The model router (`ai.mastermind.fabric-router`, not this program's to
change) took a new release at 01:28:49 UTC. Its health check failed, the roll-back was also
unhealthy, and its watchdog restarted it. Further releases went in at 01:34:48, 01:42:14 and
01:45:08. All three running lanes (T8, TSH, T4c) ended with "connection refused". Since
01:45:43 UTC the router answers for `glm-5.3`, `kimi-k3.1-pro` and `deepseek-v4.1-flash`.
Lanes running through the later reloads survived them; only the first, long failure killed.

**What the failure exposed.** T8 and T4c had hours of work that was not committed, and their
branches had never been pushed. Nothing was lost only because the checkouts were intact. This
is the event the pushed-steps rule (section 21) was written for; these lanes were started
before it. Both resumes were told to commit and push first, and both branches are now on
origin (`t3/mmos-v4-t8` at `593aeb9d8`, `t3/mmos-v4-t4c` at `f31bf26b6`).

**Resumed in their own threads:** T8 and T4c, same drivers, same checkouts.

**TSH was not resumed. It is split into two lanes.**
- Its driver was `kimi-k3.1-pro` in one run of 3 hours 47 minutes. That provider allows about
  24,000 new input tokens a minute, so a thread that long cannot be restarted cold. Its
  working tree had an installer that did not parse and one broken test. I saved the tree as
  it was (`daa8f2003` on `t3/mmos-v4-tsh`, labelled work in progress) and cancelled the task.
- The lane had tied a finished, fast part to an unfinished, slow part. The fast part is the
  short teammate names and finding a teammate's thread by something that does not change
  (`859282b2f`, `9b733b1d7`). The slow part is the pinned Node, the packed server build and
  the health check.
- **Lane TSHb** (`glm-5.3`, branch `t3/mmos-v4-tshb`) owns the slow part. It rewrites the
  installer from the last parsing version with the eight findings of the installer review
  written into its brief. The installer decides which downloaded program gets run, so it is a
  critical surface and gets an independent review before the real team server is moved.
- **Lane TSR** (`glm-5.3`, branch `t3/mmos-v4-tsr`) proves the fast part on a team server of
  its own. The two commits have unit tests and have never run against a server. They will be
  applied to the real one, where two teammates hold real work, and a teammate must never end
  up with two primary threads. TSR runs seven steps (create, rename, repeat, lost state, two
  candidates refused, a message still answered, rename back) and writes the commands for the
  real server. Then I apply the short names, and Secretary moves as the third teammate.
  Neither waits for TSHb.

**Rules changed.**
- A lane driver is `glm-5.3`. `kimi-k3.1-pro` is used for one bounded child at a time, never
  as the driver of a lane that runs for hours.
- A child asked to review files gets a commit, and those files stay unchanged until it
  returns. TSH's review ran while its driver edited the same file and saw three versions.
  This is now in `LANE_RULES_V4.md`.

**Running now, at the width cap of four:** T8, T4c, TSHb, TSR.
