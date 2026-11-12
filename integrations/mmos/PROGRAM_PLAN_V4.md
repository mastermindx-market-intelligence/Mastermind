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

## 23. Amendment, 2026-11-11 02:20 UTC: short names are live and Secretary is the third teammate

**Lane TSR is accepted and merged** (`0bc336a1f`, trunk `d798d9f34`). It ran all seven
steps on a team server of its own and found three defects that the unit tests had not, each
fixed with a test that failed first:
- The rename helper called a browser-only function from Node, so every rename failed.
- The roster spec could not describe the long-title starting state or the way back. A spec
  can now say `"allow_long_titles": true`.
- A warning was printed into the `status` output, which is meant to be machine-readable. It
  now goes to the error stream.

**The short names are on the real team server** (applied by me, 02:05 UTC). The threads
are `Assurance — quality` and `Design Lead — product`. Thread ids and pins are unchanged, no
thread was created, and a second apply changed nothing. The real spec lacked the
`browser_profile` key the rename needs; the runbook did not say so. The key is now in the
spec.

**Secretary is the third teammate** (cut over 02:13:47 UTC, trunk `2f543e683`). Its thread
is `mcp:7955c764-a883-4774-abb8-297a4579ebf8`, pinned. Its Hermes persona file has almost no
role prose, so I wrote its charter: it keeps the view of a piece of work, states a request
back, routes the specialist part to a teammate, checks what comes back, and keeps the
company record. It cannot decide strategy or approve a release. The other two teammates'
carrier configs were refreshed, so each of the three can ask the other two. The way back is
`cutover_installed.py rollback tools/mmos_teammate/specs/secretary.installed.json`. The
limit of three teammates is reached; ten agents stay on Hermes.

**Proof on the installed app: MAS-12 and MAS-13.** Secretary was asked to write the day's
company record after asking Design Lead one question. This is the kind of task it failed on
Hermes in MAS-9, where the run ended after thirty minutes with nothing written.
- Three runs, all succeeded, 61 seconds end to end (02:14:34 to 02:15:35 UTC): Secretary
  asked, Design Lead answered in MAS-13, the answer woke Secretary, Secretary posted the
  record and asked for confirmation.
- I accepted the confirmation. MAS-12 and MAS-13 are done.

**Design Lead's answer changed the product.** The question was whether `follow-up` is the
right word after Secretary's name. Its answer: no, it names an activity rather than a domain
and is the weakest of the three; use `records`. I adopted it. The thread is now
`Secretary — records`, renamed through the same proven path, pin unchanged, and the charter
says what the record is. This is the first product change that came from one teammate
asking another.

**What the attention list shows now:** three items, all Astra's (the Meta-CEO agent's error
and MAS-4). None is from this program.

**DONE_WHEN.** Item 4 now has three teammates with different charters and tools; the
rotation proof on a real teammate is still owed. Items 1 and 2 wait on T8. Item 3 waits on
the Chairman's linked-environment switch. Item 10's installed coding job is lane T4d, after
T4c and an independent review.

**The second critical review starts now, in the free slot, on what is already live.** Lane
R2a (Opus, read-only, started 02:30 UTC) reads the carrier, the cut-over tool and the roster
tool at `5459b33fa`. Three real teammates run on them, so this half does not wait for T8 and
TSHb. It asks about the run token, whose words the carrier trusts, ask loops between three
teammates, exactly-once writes, the cut-over's preimage, and the rename path's cookie
profile. The other half (socket door, shell-URL loader, T8's pairing path, TSHb's installer)
follows when those two lanes are merged. No more agents move onto the carrier before R2a
returns.

**Running now, at the width cap of four:** T8, T4c, TSHb, R2a.

Evidence: `~/.mastermind/mmos_evidence/short-names-20261111/LEDGER.md`.

## 24. Amendment, 2026-11-11 03:00 UTC: review R2a returned; one hole closed live, the rest is lane RF

**Verdict.** Safe to keep the three teammates running. Not safe to move more agents onto the
carrier until findings 1 to 4 are fixed. The run token stays inside the carrier on every path
the reviewer traced. Fifteen findings: four high, eight medium, three low. Each one and my
decision on it is in `integrations/mmos/R2A_REVIEW_FINDINGS.md`. I re-ran the reviewer's probe
for findings 2, 3 and 4 and all three reproduce.

**Finding 1 is fixed and live.** A teammate could read any file this Mac user can read
(pairing file, browser cookies, its own cut-over preimage) and could rewrite its own limits
and charter. I changed the roster tool so each teammate's limits now refuse reads of the
server's private folders, the other teammates' homes, its own preimage and the credential
folders named in the spec, and refuse writes to its own limits, charter, carrier config and
preimage. Applied to all three with no run live; titles, threads and pins unchanged.

**The teammate checked its own limits (MAS-14).** I asked Assurance to try five file actions
and report what happened. Reading a file in the server's private folder: refused. Reading
Design Lead's charter: refused. Reading its own charter: allowed. Editing its own charter:
refused. Adding a line to its own memory: allowed. All five as intended. The session was
already running when the limits changed and picked them up on its next turn, so tightening
limits needs no restart.

**What the fix does not do.** It is a list of refused paths, and the teammate is the same Mac
user as everything else. A new credential folder that is not on the list is readable until it
is added. The stronger design (reads allowed only from named places, the limits file kept
outside the teammate's writable home) is not built or proven. It goes to the next independent
review together with whether teammates keep web fetch.

**Lane RF repairs the rest (started 02:55 UTC, GLM 5.3, one Kimi attack child).** Findings 2,
3 and 4 first: a turn marker counts only as the first line of a message the carrier itself
sent; an issue is an asked child only by structure the carrier wrote; an asked teammate
cannot ask again, nobody can ask themselves, at most three asks per issue. Then the mediums in
the carrier and the cut-over tool. Unit-level only; it touches no server. Its diff and my
finding-1 diff then go to an independent read-only reviewer, and only after that do I install
with `refresh-carrier` (no run live) and repeat the ask journey and the unanswered-question
journey on the installed app.

**Ruling.** Ten agents stay on Hermes until that install is proven. The roster-side findings
(atomic settings write, one primary thread per agent checked against Paperclip, the pairing
command accepting only the local team server) follow RF in the same file I just changed.

**Correction to earlier sections.** MAS-7's confirmation was not left pending: it was accepted
at 01:00 UTC and MAS-7 is done.

**Running now, at the width cap of four:** T8, T4c, TSHb, RF.

Evidence: `~/.mastermind/mmos_evidence/r2a-20261111/LEDGER.md`.

## 25. Amendment, 2026-11-11 03:05 UTC: cheap models carry the work; a hole in my own fix; six lanes

**New economics (Chairman).** DeepSeek Flash is as good as unlimited (a shared pool of about
2,000 tokens a second). Kimi is free but slow and shared (about 150 tokens a second across
everything we run). GLM is cheap on the direct subscription. Opus and Fable are expensive and
are for mission-critical or extremely hard work the open models cannot do. This changes how
the program runs, in four ways:

1. **Width is no longer capped by cost.** The old cap (four drivers, two children each) was
   set when GLM quota ran out and Kimi rate-limited. The limits that remain are real ones: my
   capacity to check returns, one writer per file, and the Kimi pool. New rule: up to six lanes
   when their files do not overlap; each driver may run up to four DeepSeek children for work
   with a mechanical check, two GLM children, and one Kimi child at a time. Read-only helpers
   that write only to a scratch folder do not count as lanes.
2. **Drivers stop doing lookups themselves.** `LANE_RULES_V4.md` now says what each model is
   for. A census, a test run, a failing test for a stated defect or one bounded edit goes to a
   DeepSeek child with the check that proves it.
3. **I stop doing them too.** Small fixes on a file I am already holding stay with me (they
   cost less than a brief). Anything that needs a dev server, more than one file, or a design
   answer goes to a lane.
4. **Opus reviews have to earn their place.** Review R2a (Opus) found 15 defects and is the
   only measured reference we have. Before the next critical review I am measuring whether the
   open models find the same ones: four blind reviewers (one GLM over the whole scope, three
   DeepSeek each on one question) are reading the same commit R2a read, without its findings.
   If together they find the four high findings and most of the mediums, critical reviews move
   to a GLM plus Kimi plus DeepSeek panel and Opus is kept for the few surfaces where a miss
   cannot be undone. If they do not, Opus stays for critical surfaces and I say so with the
   numbers. An attack round or a panel that finds nothing still proves nothing by itself.

**A hole in my own fix, found by asking the teammate.** A teammate's home is also its Claude
configuration folder, and the limits let it create any new file there. Assurance created a
settings file, an MCP file and a skill in its home when asked (MAS-16). A settings file can
carry a command to run, so a steered teammate could give itself the shell its limits deny.
I added write denies for the configuration names and applied them to all three.

**A wrong sentence in section 24.** Limits are read when a teammate's process starts, not when
the file changes. The first fix bound in MAS-14 only because that process started after the
file was written. MAS-16 ran in a process that predated the second fix, which is why the
second fix did not bind there. Design Lead and Secretary had no process and start under the
new file. Assurance gets it when its idle process exits and restarts; I check again then.

**What the three checks proved (MAS-14, 15, 16):** Read, Edit, Write, Grep and Glob all obey
deny rules for the server's private folder, other teammates' homes and the teammate's own
charter. Not yet proven: the configuration denies on a restarted process.

**Lane RL (new, GLM 5.3).** The roster side of findings 11, 12 and 14, and the stronger
design for limits: reads allowed only from named roots, writes only to the memory file and
one notes folder, proven on its own dev server with process start times stated. It also
establishes whether the runtime loads a settings file from the home, and adds a line to
`apply` saying when new limits are not yet in force.

**Running now, six lanes:** T8, T4c, TSHb, RF, RL, and the calibration panel (four read-only
reviewers, scratch only).

## 26. Amendment, 2026-11-11 03:40 UTC: reviews leave Opus; the second limits fix is proven; the server hardening is merged

**The measurement asked for in section 25 is in.** Four reviewers read the commit review R2a
(Opus) had read, without its findings. Scores, my checks of every new finding and the session
search behind the correction below are in `~/.mastermind/mmos_evidence/r2cal-20261111/SCORE.md`.

| Reviewer | Cost to us | R2a HIGH found | R2a findings found | New real findings |
| --- | --- | --- | --- | --- |
| Opus, whole scope (R2a itself) | expensive | 4 of 4 | 15 | the baseline |
| GLM 5.3, whole scope | cheap | 2 of 3 | 5.5 of 14 | 5 |
| DeepSeek, three narrow questions, together | free | 3 of 3 | 11 of 14 | 13 |

Finding 1 is left out of both open-model rows: every child session starts with the recent
commit subjects, and one of them named finding 1's fix. None of the four opened the findings
file. What decided the result was the question, not the model. The whole-scope GLM reviewer
wrote that the exactly-once core was sound; the DeepSeek reviewer asked only "whose words does
the carrier trust, and can the wrong ones win" found and reproduced finding 2. The three
findings the panel missed (5, 7, 15) are one kind: what the code does when the record is in a
state its author did not walk through. Opus missed 13 real defects the panel found.

**Ruling.** Reviews of critical surfaces are done by a panel of DeepSeek reviewers, one narrow
question each, blind to each other and to the lane's own attack round, each with probes:
1. whose words or bytes does this code trust, and can the wrong ones win;
2. what happens when each call fails, times out, or succeeds without its answer arriving;
3. for every state the record can be in and every reason the code can be woken, what does it
   do (added because of the three misses);
4. installation, cut-over and rollback.
Kimi adds one attacker's-view pass when its pool is free. I check every HIGH finding against
the code before acting on it. Opus is kept for one case: a change that cannot be undone once
applied, where the panel's answers disagree. A panel that finds nothing still proves nothing
by itself. Long DeepSeek runs died on a gateway error twice in one hour and finished after one
restart; `LANE_RULES_V4.md` now tells every DeepSeek child to write its result file early.

**The second limits fix binds after a restart (MAS-17).** Assurance's idle process exited by
itself. In a process started after the limits file was written, it could not create a settings
file, an MCP file or a skill in its home, and could still write a notes file and its memory.
I checked the file system and the process start time, not only its report. Section 25's
"not yet proven" line is closed.

**Lane TSHb is merged, not applied.** The pinned-Node installer, the packed server and the
runner are on the trunk with their runbook. The real team server is unchanged. The installer
decides which downloaded program gets run, so two reviewers are reading it now (Kimi from an
attacker's view; DeepSeek on failure, rollback and the runbook's steps). I make the real switch
after their findings are dealt with, with no teammate run live.

**Lane RF now holds findings 2 to 31**, the last sixteen from the panel. Fixed and pushed so
far: 2, 3, 4, 6 and 9, each with a failing test first. Lane RL holds the roster side of 11, 12
and 14 (pushed), the report line for limits not yet in force (pushed), finding 32 (a spec's
`slug` is not validated) and the allow-list design. RF's delta and my own two limits commits
go to the panel before anything is installed.

**DONE_WHEN.** Unchanged from section 25's count: 5, 6, 7 and 8 done on the installed app; 9
checked; 10's improvement loop met; 1 and 2 with lane T8; 3 needs the linked-environment
switch in the Chairman's app; 4 owes rotation on a real teammate; 10's coding job on the
installed app is lane T4d, after T4c and its review.

### 26a. Kimi is scarce (Chairman, 2026-11-11)

Kimi's provider cut our limit by 70 percent. Where sections 25 and 26 give Kimi a standing
place (one Kimi child per driver, one attacker's pass in every panel), read this instead:
Kimi is started only for a problem a GLM child has already failed at twice, or by the
principal for one attacker's pass on a surface that decides what program runs or who holds a
credential when the DeepSeek answers disagree. The panel's attacker brief goes to DeepSeek.
`LANE_RULES_V4.md` and `REVIEW_PANEL.md` carry the rule. Running lanes were told at 03:55 UTC.

## 27. Amendment, 2026-11-11 04:10 UTC: one thread, workers in several projects (lane XP)

**Request.** From the Sector Intelligence programme (thread `2f136a11-91f9-4bca-bf10-8a1d8b7f4e5d`,
Macro Dashboard project), routed by the Chairman on 2026-11-11 about 03:50 UTC: "For the T3
problem, communicate to the T3 Hermes Engineering program so they engineer some kind of fix
for this into Mastermind OS, our own harness that is built with T3 integrated in, this way we
have a solution for this. Note that Claude Code already has a solution for this so the owner
for the mastermind OS project can evaluate and get that implemented into Mastermind OS
harness."

**The problem, as they tested it.** A thread can start workers only in its own project. Their
programme spans two repositories (`macro` and `mastermind-terminal`), so every worker for the
second repository is a separate top-level thread:

1. `delegate_task` with `target.projectId` of another local project is refused ("A local task
   runs in this thread's project…"), also when `target.environmentId` names the same machine.
2. `t3_thread_update` cannot move a thread to another workspace.
3. `t3_thread_launch` into the other project works, but the new thread has no parent link, its
   finish does not wake the launcher, and it shows as a separate thread.
4. A new worktree with `baseRef: "master"` was cut from the machine's local `master` (a commit
   of 2026-10-23) and not from `origin/master`; files merged since were missing.
   `workspaceStrategy.startFromOrigin` exists and was not tested.

**Decision: adopted, as a cross-project child in our T3 build.** I read the pinned source
(`apps/server/src/mcp/OrchestratorMcpService.ts`, `delegateTask`). The refusal is one check on
`target.projectId`. Just above it, the same function already handles a child in a linked
environment: "The task's child runs as an ordinary thread there; this thread keeps the task."
So the server already knows how to keep a task on the parent while its child is an ordinary
thread somewhere else, and how to bring the result back. The local other-project case is that
mechanism without the network hop.

Claude Code's multi-directory session (`--add-dir`, `permissions.additionalDirectories`) is
not the answer by itself. It lets one session read and edit a second folder. It gives the
worker no isolated checkout, our worktree-isolation hook refuses git commands aimed at another
tree, and the second repository's instructions and hooks are not the session's own. It stays
useful for a parent that only needs to read the second repository; the lane says whether our
build should pass the other project's root as an extra read-only folder to the parent.

**Done when** (theirs, kept): from a thread in project A one call starts a worker in project
B; the worker has an isolated checkout at the remote default head; B's instructions and hooks
apply to it; the parent is woken with the result; the worker's permissions are no broader
than the parent's.

**Lane XP.** A GLM driver, own clone of the pinned T3 source, own dev T3 server with two test
projects. Output: a patch under `integrations/t3/upstream_patches/` with its entry in
`MANIFEST.md`, tests in the T3 tree's own test files, and a live proof. It decides who may be
a target (a registered project on this server, with the provider enabled there), so it is a
critical surface and gets a panel review before it is installed on the team server.

**What this does not do.** The Sector Intelligence thread runs in the Chairman's T3 Code app,
which this programme does not patch. They get the fix when their programme runs on a
Mastermind OS server, or if the patch is sent upstream, which is a public act and waits for
the Chairman's word. Until then: launch the other-project thread with
`workspaceStrategy.startFromOrigin`, and put in its brief that it ends by sending its result
to the parent thread with `t3_thread_send`.

## 28. Amendment, 2026-11-11 10:50 UTC: harness access, browser use and computer use (lanes BR, HX, BCU)

Two orders arrived on 2026-11-11. The Chairman ordered a browser-use and computer-use layer
built into T3 and into Mastermind OS: several connected browsers through the Mastermind
extension, computer use, and a vision relay for models that cannot see images. The Sector
Intelligence programme relayed a second instruction from him: clear the harness faults that
cost their sessions time, twelve items, each answered to their thread with one line
(`HARNESS <n>: fixed — <how to use>` or `HARNESS <n>: needs human action — <exact action>`).

**A correction to how I work.** I spent about 25 minutes diagnosing the browser fault myself.
The Chairman stopped that: diagnosis is lane work too. A new problem gets a few minutes of
orientation from me, then a brief to a GLM lane that owns the diagnosis and the repair.

**Lanes.** Each has a GLM driver in its own checkout and installs nothing; every change comes
back staged with its install command, the sha256 of the file it replaces, and a rollback.

| Lane | Owns | Harness items |
| --- | --- | --- |
| BR | The page-read fault in the Mastermind extension (`snapshot` fails in two profiles), a documented paste path, error messages that name their cause | 1, 3, 4 |
| HX | Fleet browser registration, the worktree quarantine on worker start, the shell guard refusing read-only commands, silent worker stops and restart recovery, the cross-machine thread link, MCP servers that need sign-in | 6, 8, 9, 10, 11, 12 |
| BCU | Computer use, the vision relay, the browser tools as one layer, a guidance file, registration in both homes | 5 |
| XPb (section 27) | Cross-project workers | 7 |

Item 2 (submitting the other programme's research prompts) is not ours and was not claimed.

**Order of work, changed the same day.** The Chairman's later word, relayed: computer use
ahead of browser use, no key-by-key typing, no burst of sessions. BCU therefore delivers one
slice first: bring a named window to the front, click, paste with the paste chord and restore
the pasteboard, click a send control, read that one window. The browser tool remains for
reading.

**Rules the layer carries.**
- One window per capture, never the full screen. Password managers, Keychain Access and the
  privacy panes of System Settings are refused for capture, click and paste alike.
- Every action returns APPLIED, NOT_APPLIED or EFFECT_UNKNOWN. The layer never retries an
  uncertain action.
- One holder of the screen at a time, by a lease with an owner and an expiry.
- No action while a person is using the Mac (idle period, default 3 minutes); a sequence
  aborts if input arrives in the middle.
- A minimum interval between paste-and-send sequences per window.
- It is plain automation. Nothing is built to disguise it from a website or a provider. A
  challenge, CAPTCHA, sign-in, rate-limit or unusual-activity notice stops the action; the
  worker reports it and does not retry or switch route.
- macOS Accessibility and Screen Recording grants are given by a person.

**Reserved to me.** Installing any staged change; turning the layer on for a real teammate
(per-teammate switch, default off); any router change; driving another host's screen. The
shell guard, the worktree hook and the computer-use server decide what a worker may touch, so
each gets a blind panel before install.

**The second T3 build** (`~/Applications/T3-Queue-Stall-Staged-20261109/`) was read. It holds
four commits of merge-queue and stall recovery for pull-request watching and nothing for
browser or computer use. Nothing is adopted from it now.

**Panels, as run from today.** A GLM panel lead builds the blind export, starts the DeepSeek
reviewers, checks every HIGH and MED finding against the code itself and writes `SCORE.md`.
I read the score. First result (lane RF): do not install as written; three HIGH findings, one
of them a defence that read a field the server never sends and passed two attack rounds
because the tests supplied the field by hand. Rule added to `REVIEW_PANEL.md` practice: a
defence that reads a server field is tested against a captured real response.

## 29. Amendment, 2026-11-11 12:40 UTC: Chairman rulings on computer use and admin steps; four panel scores

**Chairman rulings, 2026-11-11.**
- Computer use runs on Peekaboo. Workers drive it; the principal does not. Workers on Terra,
  Sol and GLM must each be able to drive it, so the first slice (bring a named window to the
  front, click, paste by chord, click send, look) is proven once per model, DeepSeek Flash
  included, each as a worker started by T3. The Chairman's own Peekaboo daemons are not
  stopped or restarted by any lane.
- Steps that need only the Mac admin password are the principal's to run and no longer wait
  on the Chairman. The password reaches the principal through the secret prompt as a file and
  goes to `sudo` on standard input; it is never printed, logged, committed, placed on a
  command line or handed to a worker. A lane that meets such a step returns
  `NEEDS PRINCIPAL ADMIN STEP` with the exact command or pane, the check and the undo.
  Touch ID, passkeys, CAPTCHA and provider sign-ins stay with a person. This covers settings
  and installs that assigned work on this Mac needs; it does not cover purchases, security
  changes on outside accounts, turning off System Integrity Protection, or editing the macOS
  privacy database directly.

**Panel scores and what follows from each.**

| Lane | Score | Decision |
| --- | --- | --- |
| TSHc (team server installer) | 23 real; two HIGH: the packed server tree is never checked against its digests, and any answer on the port counts as a healthy server | Repair round 2 running; delta panel; then the real server switch |
| XPb (cross-project worker) | Four repairs verified; one MED: the raw socket door writes the child's run mode without the parent's cap | Repair round 2 running; small delta check; installed with or after the server switch |
| RL (teammate limits) | 19 real; six HIGH. The claim "a teammate writes only inside its home" is false as built | Repair round 1 running, with the design change below |
| RF (ask and return) | Do not install as written (section 28) | Repair round 2 running; second panel |

**Design change for teammate limits.** A list of denied names taken from the disk at install
time cannot cover a name that does not exist yet, a folder made later, a teammate added later
or another spelling of the same path. The primary fence becomes a check that runs before every
file and web tool call: it resolves the real path, allows writes only inside the teammate's
home (less its own configuration, charter, limits and preimage) and reads only inside the home
and the named read roots, and refuses everything else, including a tool it does not know.
Searches are checked on their starting folder; web fetches to this Mac and to private
addresses are refused. The generated deny rules remain as a second layer. The lane proved in
its first round that such a check runs inside teammate turns. If it cannot carry one of these
duties the lane returns early with the evidence.

**Harness answers sent.** Item 6: `mini1` is usable when the call names the host; `ubuntu4`
and the `m2` MastermindX profile need the extension loaded from the right folder, which the
computer-use worker does once its first slice passes review. Item 12: one interactive sign-in
by the Chairman.

## 30. Amendment, 2026-11-11 12:55 UTC: browser repair lane BF, three accepted results, the silent-stop patch, a short Opus window

**Priority change from Sector Intelligence.** Their team will use the browser for ChatGPT Pro
runs with sends at least a minute apart, so harness item 1 (page reads fail in the ChatGPT
profiles) is at the front again and item 5 (computer use) no longer blocks them.

**Lane BF (browser fix), by the Chairman's order.** One `glm-5.3` engineering worker repairs
the ChatGPT profiles where the page cannot be read. What it established: ChatGPT1, 2 and 3
loaded the extension before its site permission existed and were never reloaded; ChatGPT4
already works and is left alone. The repaired extension files from lane BR were scored
`reload-ready` by a second check and sit staged in the ChatGPT1 and ChatGPT2 folders. BF finds
the Reload control on the real Chrome window by its label, presses it once per profile in the
order 1, 2, 3 (stopping if the first press gives no working page read), then proves a page
read and one text fill in its own new ChatGPT tab in each profile, a minute apart, never
sending. BF touches no tab it did not open. Harness answers 1, 3 and 4 follow its receipts.

**Accepted since section 29.**

| Lane | Result | State |
| --- | --- | --- |
| HX (harness access) | Items 8, 9, 11 answered; item 10 diagnosed with patch points | Notes merged; the read-only allow fragment for item 9 is not installed (principal's decision: the guard that causes the prompts is inside the CLI binary and no allow rule passes it) |
| T8b (window pairing) | Two MED from the panel fixed: default-browser opens are rate limited; no false signed-out state before the hold time | Merged; the release bundle is built and not installed; the on-screen proof is owed at the real switch |
| BR (browser plugin) | Seven of seven repairs; delta check `reload-ready` | Staged; merge to trunk after BF's proof. Installing a new bridge release still needs the Chairman's word |

**Lane T10 (silent stops), harness item 10.** A patch to our T3 pin so that a child whose run
ends without a normal result always settles with a return line naming the cause and wakes its
parent once, and so that after a server restart every running child is resumed or settled and
reported. A resume never re-sends a prompt that may already have run tools. Own source clone,
own dev server, tests beside the code, no Mastermind names in T3 code. It is an exactly-once
surface: a blind panel scores it before it goes on the team server. It repairs our own server
only; this programme does not patch the Chairman's T3 Code app.

**Computer-use server review.** The layer lane BCU built is scored by a blind panel against
its eleven product rules before it is registered in any provider home or switched on for any
teammate. BCU's four-model first-slice proof runs through a command-line entry on the same
code, so no registration is needed for the proof.

**Opus window.** The Chairman opened the Opus pool for new lanes for one to two hours on
2026-11-11 (a limit on one account that would otherwise lapse; the pool is shared with the CI
programme). Two lanes use it: T10 and the BCU panel lead, each with DeepSeek Flash children.
After the window, routing returns to section 26: `glm-5.3` drives lanes and leads panels,
DeepSeek Flash reviews and tests.

## 31. Amendment, 2026-11-11 14:20 UTC: browser control restored, four panels scored, the order of installs

**Browser control works in ChatGPT1 to 4 (harness items 1, 3, 4).** Lane BF could not press
Reload by any route: this Mac's Chrome serves no accessibility tree, and macOS refused the
helper that would have asked for one. That refusal was final and was not worked around. The
Chairman loaded the repaired extension himself with **Load unpacked** from the three staged
folders. BF then proved open, page read, text fill, read-back and close in its own tab in
each profile, sending nothing. Two standing facts follow:

- An extension change on this Mac reaches a profile only when a person presses Load unpacked.
  Staged extension changes are batched so the Chairman does one round, not several.
- No lane tries to drive Chrome's own windows or settings pages.

One limit was found in the proof: a text fill of about 1,900 characters applies and one of
6,001 is refused. Lane BR has a third round to find where that limit lives, how newlines
behave in the composer, and a proven path to 20,000 characters with paragraphs. An extension
change comes back staged; a bridge release install still needs the Chairman's word.

**Harness item 8 corrected.** The quarantine that stopped Sector Intelligence's read-only
children is a hook in the Macro repository, which fires for any session rooted in a Macro
checkout that is not on a `claude/*` branch. Two brief lines avoid it for read-only work and
are now standard in every brief this programme writes: ignore the quarantine notice's remedy
and finish the read-only task with plain single commands; and do not end a turn while a
command is still running. A one-sentence change to the hook's own remedy text is staged in
`integrations/mmos/harness/` and is not opened as a Macro change without the Chairman's word.

**Scores since section 30.**

| Lane | Head scored | Score | Next |
| --- | --- | --- | --- |
| XPb (cross-project child) | `b00c97e3b` | `install-ready` after two repair rounds | Merged. Installed with the team server switch; then harness item 7 |
| RF (ask and return) | `608ea1ccc` | 17 real of 25, one HIGH (the carrier returned the oldest answer, not the newest) | Repair round 3 running; delta check; then the carrier is refreshed for one teammate at a time |
| RL (teammate limits) | `7e9a29aa4` | 9 real of 50, three HIGH (web address check, host parsing, own preimage readable) | Repair round 2 running; the rule layer shrinks from about 66,000 rules to a few hundred once the hook fails closed |
| BCU (computer use) | `de986c5a6` | 25 real of 57, four HIGH; nine of eleven product rules only partly enforced | Repair round 1 running; delta check; then the principal chooses which homes register it |
| TSHc (server installer) | `3f79ffc40` | Repair round 2 returned; second delta panel running | The real server switch, by the principal |

**Principal rulings in those repairs.**

- Computer use: a captured image is never returned to the calling session; it goes only to
  the vision model on the local router and is deleted after the answer. Environment variables
  may tighten a rule, never loosen one.
- Teammate web access: the check reads exactly the address the tool will fetch and refuses
  any address-literal host, embedded sign-in, backslash, percent escape or non-default port.
  One list of unreadable paths serves Read, Glob and Grep.
- One writer per file across lanes: BCU's edit to RL's function was reverted; RL makes it.

**Order of installs on the real team server.** Each step waits for the one before it and for
no teammate run being live; each has its rollback written in its score.

1. Server installer (TSHc) together with the cross-project patch in the same build.
2. Window switch to the T8b bundle, with the on-screen and rotation proof.
3. Teammate limits (RL), then the ask-and-return carrier refresh (RF), one teammate at a time.
4. Silent-stop patch (T10) after its own blind panel.
5. Computer-use registration (BCU) in the homes the principal names.

**Routing.** The Opus window of section 30 is closed. Three lanes used it (T10, the BCU
panel, the second RL panel). New lanes follow section 26 again.

## 32. Amendment, 2026-11-11 15:20 UTC: the team server and the window are switched

**Installs 1 and 2 of section 31 are done, by the principal.**

| What | Now live | Check | Way back |
| --- | --- | --- | --- |
| Team server | Its own pinned Node (v24.22.2) and a packed release `t3team-0.1.7-pin0770446-2`, built from the pin with the text-streaming and cross-project patches; folder closed to other accounts; every start checks both trees against their recorded digests | `doctor` exit 0: loaded, answering process is the job's own, both trees verified. Five threads and all run history unchanged | The score's "Going back" sequence to the previous binary, which was not touched. The new trees stay 48 hours either way |
| Window | The reviewed T8b bundle at `~/Applications/Mastermind OS.app`, set to open on Secretary's conversation and sign itself in | The app's own config check passed; one sign-in on first open, none on reopen | `window_config.sh clear --bundle release` and move the kept copy of the old app back |

**What went wrong in the server switch.** The planned one to three minutes of downtime became
twenty-two. Started by launchd on a loaded machine, the start-up digest check took about five
and a half minutes, against under a minute from a shell. The installer waits three minutes,
saw no answer, and unloaded the job, twice, with an empty log each time. The server came up
once the job was loaded and left to finish. The first `doctor` run then wrongly named the
job's own listener as foreign; the second run was right.

Until the repair lands, a restart of the team server at high load takes minutes, not
seconds. It does come back by itself: launchd keeps the job alive and has no time limit.

**Lane TSHc round 3** proves the cause of the slow start and fixes it without weakening the
digest check; makes the installer tell "still checking" from "dead" and never unload a job
that is checking; makes the runner write to the log at each stage; makes `doctor` report an
unknown as unknown; and takes the ten small follow-ups the second delta panel listed.

**Still unproven on the window.** What it shows on screen (the principal could not read its
text), and one refused-navigation record on every launch. Lane T8b reads the real window,
without typing or clicking in it, and explains or repairs the refused navigation.

**Harness item 7** is answered: cross-project workers work on the team server. Sector
Intelligence runs in the Chairman's T3 Code app, which this programme does not patch, so it
changes nothing for them without his word.

**Lane T10 returned** with the silent-stop patch: six of seven stop paths closed or already
closed, one open (a repeated request after a restart can start a second child). A blind panel
scores it before install 4.

**Routing, by the Chairman (15:15 UTC).** The Opus pool is spent. Opus is for the hardest
tasks and deputy roles only; `gpt-6.1-sol` may be used where Opus would have been.

## 33. Amendment, 2026-11-11 15:35 UTC: an operating deputy, the bridge release, the GitHub-link paste route

**Operating deputy adopted.** The Sector Intelligence COO forwarded the pattern at the
Chairman's request, and the Chairman ruled that Opus is for the hardest tasks and deputy
roles. This programme has eight lanes returning with repairs and trade-offs, which is the
case the pattern is for. One long-lived Opus deputy thread (`mmos-v4-deputy-20261111-a`)
now runs the control loop: it steers lanes, starts panels and delta checks, sorts findings,
merges reviewed branches into the trunk and records each decision. Its standing brief is
`integrations/mmos/deputy/BRIEF.md`, the principal's rulings are
`integrations/mmos/deputy/RULINGS.md`, and its state file is
`~/.mastermind/mmos_evidence/deputy/STATE.md`. Reserved to the principal: every install or
change on a real root, scope and limit changes, accepting a known HIGH or MED, admin-password
and human steps, messages to other programmes and the Chairman, uncertain effects and
refusals, and starting Opus, `gpt-6.1-sol` or Kimi children. The principal reads the named
evidence itself before any install. Measure: principal turns per accepted outcome; if
escalations pass a quarter of the deputy's runs, its rights are widened with one ruling.

**Lane RF repair 3** returned at `42b0ffe1d` (ten of ten required findings, seven extras,
`paperclip_base` required and loopback only). Its third delta check is running.

**Lane BR round 3.** The live fill limit is 8,000 characters (the pinned bridge protocol),
with a 32,768-byte envelope cap in the MCP server, and ChatGPT's composer flattens line
breaks on the live build. The staged change at `8f14c2604` raises the limit to 30,000 and
inserts real paragraphs; its delta check asks whether paragraph insertion can send the
message in an Enter-to-send editor.

**Bridge release.** The Chairman gave his word (15:25 UTC): "yes to bridge release as
needed". The install stays the principal's act, after the delta check, by the steps in
`br-20261111/mcp_bridge_install.md`; going back is re-pinning `5aa30969…`. The extension half
still needs one Load unpacked round by the Chairman, asked once, batched.

**GitHub-link paste route (the Chairman's).** For a ChatGPT prompt longer than the fill
limit, a subagent posts the text as a GitHub issue or comment and the operator fills only
the link and one line of instruction. Sent to Sector Intelligence as an addition to harness
item 3. Not yet checked: that each ChatGPT account's GitHub connector can open the link.

## 34. Amendment, 2026-11-11 18:50 UTC: the first day under the deputy, a provider-path defect, the Grok Bot link lane

**The real team server could not start Claude runs** from the 15:05 switch until 18:22 UTC.
The window showed "Claude Agent CLI (claude) was not found on PATH": the runner's PATH
(`bin/server_runner.sh` lines 57 and 155) does not include `~/.local/bin`. Remedy without a
restart, applied by the principal: `binaryPath` set on the four provider instances in the
team server's `settings.json` (0600 backup `settings.json.pre-binarypath-20261111` beside
it). The banner was read gone at 18:24 UTC. The durable repair is lane TSHc's item F
(`config/provider-cli-dir`, head `f1c8354af`); release `-3`'s last step decides whether
`binaryPath` stays. Not yet proven: one real teammate run on the real server. Lesson: the
switch proof in section 32 read the window and the server's answer, not a run; a switch
proof now includes one teammate turn.

**The slow start is explained.** Lane TSHc proved the 22-minute restart was the launchd job
running at background priority (no `ProcessType`); with `ProcessType=Interactive` the same
boot took 22 s instead of 282 s under load. Delta check 3 at `aec3ff23b` is not ready: three
HIGHs in the code that round added (a `curl` with no time limit that can hang the install,
a node verify that writes no progress note so a live verify is booted out, and a two-walk
cache race that would let the mandatory digest check pass on changed files). One micro-fix
round of four listed items and a narrow delta check follow.

**Rulings 7 to 10** (`integrations/mmos/deputy/RULINGS.md`): a reviewed patch is not held
for defects that were already in the code under it (7); changes that each need a restart
ride one packed release and one restart (8); a HIGH first seen at a late check gets one
more limited round, and "better than what is live" does not install a known HIGH (9);
ruling 2's stop counts only a HIGH an earlier check listed, and any HIGH after the extra
round stops the lane (10).

**Panel results since section 33.** T10 (silent stops): install-ready, merged to the trunk
at `5a7aad8e3b29`, waits for release `-3`. RL (teammate limits) at `45a3ea404`: not ready
(DNS rebinding in the web check, unreadable set too narrow, a firmlink path, an interpreter
on PATH) and a new HIGH, the `webReader` tool outside the fence; install 3 does not go
ahead with it reachable, and if the web check cannot pin the address it fetches, teammates
get no general web fetch in install 3. RF (ask and return) at `42b0ffe1d`: two HIGHs first
seen at delta 3 (answers of two finished asks delivered in the wrong order); round 4 is
out. BR (browser fill) at `8f14c2604`: the fill reports `APPLIED` without reading the
content back; round 4 is out and also carries a paged whole-page read.

**Harness item 13 (Sector Intelligence, 16:09 UTC):** reading a finished ChatGPT answer
whole. Not possible today: the page read stops at 10,000 characters from the top of the
page and has no offset. The paged read is ordered into the same bridge release; the
debugger route is closed in their profile by another extension and is not routed around.

**Lane GBL (the Chairman's order, 15:38 UTC):** a two-way link between bots in Grok Bot
and Mastermind OS teammates, team threads and the T3 development threads. Architecture
first: Grok Bot's real capabilities from its own documentation, three transports compared
(direct connector, Slack thread relay, routine or webhook), addressing, the return path,
admission, exactly-once, and the human-only steps. The first run on `gpt-6.1-sol` looped
for three hours on tool calls with empty input and wrote nothing; relaunched on `glm-5.3`
with staged deliverables in `~/.mastermind/mmos_evidence/gbl-20261111/`.

**Routing fact.** Three `gpt-6.1-sol` children on two programmes showed that loop between
18:05 and 18:40 UTC. It is not dispatched again until one small canary child completes.
A long-running child with a climbing item count and no output file gets one activity read.

**Deputy, first measure.** Nine deputy wakes, one escalation, twelve recorded decisions.
Two panel verdicts reached the principal two hours late because a panel lead's interim note
arrives as "completed"; the principal now reads the final with one status call after any
interim note.

## 35. Amendment, 2026-11-12 00:15 UTC: release -3 is live, the review loop gets an end, install 3 without the router

**Release -3 is installed on the real team server.** One pack and one restart (ruling 8)
carried the silent-stop patch and the installer repairs through MF2. Downtime was about two
and a half minutes. Proofs: `doctor` exit 0 with the tree verified, one delegated child
waking its parent exactly once, and a real Secretary turn answering in six seconds. The
temporary `binaryPath` setting from section 34 is cleared; a second Secretary turn ran
without it, so the provider CLI resolves through the recorded folder alone. Release -2 is
byte-unchanged and stays as the rollback until about 15:20 UTC on 2026-11-13. Not yet
proven: that the reply text shows in the Mastermind OS window.

**Returns are sent, not waited for (ruling 11).** Seven finished returns sat unread for up
to four hours because a lane or panel lead can end without waking its sender. Every send
now ends with an instruction to send the return line to the deputy thread, and the deputy
lists what it cannot read for the principal.

**The review loop gets an end (ruling 12).** Three lanes stopped on the same pattern: each
blind check closed everything it was given and then found something new in code the round
had not touched. The installed code is worse than every head under review, so waiting for
a clean check costs more than it buys. A stopped lane gets one final round on a short named
list; the check of the changed lines ends the loop; anything first found in unchanged code
comes to the principal as one list with costs. Applied to ask-and-return, the browser fill
and the Grok Bot link client.

**What a fill receipt claims (ruling 13).** APPLIED means the box held the asked content
after the page's pending microtasks and one stated settle interval. A page that changes
the box later is outside the receipt; the operator rule is to read the box before sending.

**Install 3 goes ahead without the router change.** The upstream web reader is attached to
the teammates' model by the upstream account, not by anything this programme generates. It
is offered today; the limits install neither adds nor worsens it and removes the credential
reads that make it dangerous. This reverses the earlier ruling that install 3 waits for the
web reader to be closed. Closing it means changing the Fabric router that every session on
this Mac uses, which is the Chairman's; he has been asked once. Meanwhile a read-only census
checks whether another model on the team route comes without the tool.

**Grok Bot link.** The design, its addendum and the ruling are in `integrations/mmos/gbl/`.
Contract and bridge core passed their panel; the Paperclip client is in its final round.

**Macro CI.** A capacity report from Sector Intelligence was forwarded to the CI Lightning
thread, which owns CI across the three repositories. It is not this programme's work.

## 36. Amendment, 2026-11-12 01:10 UTC: install 3 is live; the web reader comes and goes

**Install 3 is on the real team server.** The three teammates now run under the reviewed
limits and the gate hook, with no web tools. The server was not restarted; only teammate
sessions were. `status` went from exit 1 (no gate) to exit 0 with every row true. In each
teammate's fresh session a read of the server's run folder and a write to its own limits
file were refused, a write to its notes folder was allowed, and a search rooted at its
home was refused by the hook under the pinned interpreter. Charters and server settings
are byte-identical to their backups.

**One step ran differently from the reviewed list.** A web fetch cannot be forced on the
real seat, because the deny rule removes the tool from what the session is offered. The
hook's refusal was therefore read from the wired command run directly for each teammate.
The step list now says: confirm the tool is not offered, and run the wired command.

**The web reader is intermittent, not gone.** Of three sessions started within four
minutes on the same model and route, one was offered the upstream web reader and two were
not. A single absent reading proves nothing, so the census is reported as a rate. Install
3 does not control this tool. The route change that would is still the Chairman's, and the
question to him stands.

**Remaining order.** Ask-and-return refresh for the three teammates after its final check;
the browser bridge release after its final check, with one round of extension reloads for
the Chairman; computer use after I choose its homes; the Grok Bot link install and one
sitting with the Chairman.

## 37. Amendment, 2026-11-12 02:40 UTC: a development board joined the real store; three class rulings; the Paper lane

**What happened.** A lane's abandoned start of a development Paperclip joined the real database
for about ninety seconds. I reconciled it myself by comparing the whole store before and after:
one effect, two permission rows whose update time was re-stamped and nothing else changed. No
repair was needed. The lane's own three-table check had missed it.

**Rulings that follow (text in `deputy/RULINGS.md`).**
- Ruling 14: a development board starts only through a launcher that pins the instance home,
  database port and database folder, and the start banner is read first. A "not written" claim
  needs a whole-store comparison. The development launcher is being rewritten to meet this; the
  Grok Bot link's board steps wait for it.
- Ruling 15: when the check that ends a review loop finds required items in lines the last round
  changed, I may grant one micro-fix, checked by the panel lead alone, with no further round.
  First used on the browser fill.
- Window proofs: a proof is met when the reply text is in the window's own accessibility text for
  the open conversation. No lane scrolls the Chairman's window to improve a proof.

**A lane that had stopped silently.** The computer-use lane was recorded as waiting for an idle
screen; it had stopped the previous afternoon behind a monitor that never fired. It was restarted
with an order to run in the idle window without a monitor. Rule for lane state: a "waiting" row is
checked against the lane's own task record, not copied forward.

**New lane: Paper (Chairman's order, 02:28 UTC).** One Opus lead, reporting to me, with two
outcomes: one reviewed path by which a session on any host can read, screenshot and, where its
brief allows, edit Paper files held on a studio Mac; and a design skillpack (protocols, specialist
skills, ready briefs for design children) for the Sector Intelligence and Prophet programmes,
built on the three existing design skills rather than beside them. The lane installs nothing and
returns staged changes. Existing mockups are read-only for it. Its design note comes to me for a
ruling before anything is built. Both programmes were told the lane exists; the "Paper is ready"
notice goes out only when the path is installed and proven.

**Order of work now.** Browser-fill micro-fix, then the bridge release and one round of extension
reloads; the ask-and-return carrier refresh after its final check; the launcher rewrite, then the
Grok Bot link proofs and one sitting; computer-use runs, its delta check and my choice of homes;
the Paper design note and ruling.

## 38. Amendment, 2026-11-12 03:05 UTC: a failed bridge install, the Paper route, a full worktree pool

**The browser bridge install failed and was rolled back.** I ran the lane's five install steps.
Every check in the list passed, and a fresh session on the new release still could not reach any
browser profile. An old-against-new comparison in the same minute put the fault in the new release
folder: the steps copy 15 pinned files, and the working release folder holds about 175. Changing
the pin also made every session that was already running refuse browser calls until I restored it,
three minutes later. The old release is live and the root is as it was. Record:
`br-install-20261112/RESULT.md`.

- Ruling 16 follows: install steps are rehearsed end to end against a copy before they reach me,
  and they state what the change does to sessions already running. A method that makes running
  sessions fail is not installed while other programmes have operators at work.
- The browser lane now owes the cause, a rehearsal that ends with five local profiles connected,
  and a switch that leaves running sessions working. The extension reload round is not asked of
  the Chairman until the bridge is live.

**Ask-and-return: one micro-fix.** The final check found three required items in changed lines
(a reply could be attributed to the wrong child by age; an unattributed child halted every wake;
one exit was logged but not noted on the issue). Ruling 15 applies: one micro-fix of those three,
checked by the panel lead alone, then merge and the carrier refresh.

**Paper: the route is ruled.** The lane's design note compared four ways for a session on another
host to reach Paper on the M2. Ruled:

- The route is the guarded Paper server over SSH, one key per remote host and profile, each key
  tied to a fixed command that gives no shell and no forwarding. It adds no listener, no tunnel
  and no new sign-in service. It is staged for me, rehearsed under ruling 16 and independently
  reviewed before I install it.
- The M2 is the only Paper host in this delivery. A second host editing the same file would not
  share the M2's lock.
- Until the route is installed, a remote session reads and screenshots through a short-lived
  child on the M2. That works today, so the programmes get the skillpack and a first notice
  before the install.
- On the M2 itself the vendor relay stays, and the one named canvas writer of a document may use
  its write tools until a guarded local registration replaces it. The skill states what the relay
  lacks and the rule after an unclear result: stop, inspect, never repeat.
- One canvas writer per document per programme, named in that programme's design log. The shared
  Sector and Prophet pages get one writer at a time, agreed between the two leads.

**A finding outside this programme's custody.** The lane found that an existing private-network
path to the Studio Direct design gateway admits any device on the private network with no
credential; two remote hosts listed its tools, including the edit tools, without signing in. Edits
refuse today only because that gateway's Paper runtime is too old for the installed Paper. The
path and Studio Direct are the Chairman's, so this goes to him with one recommendation: remove
that path, or restrict it to the M2, before that runtime is ever upgraded. No lane uses it.

**The worktree pool is below its floor.** Both external volumes are a few GiB under the 160 GiB
floor, so the storage helper refuses every new worktree for every session on the M2. The automatic
reaper is not reclaiming: its last run judged 406 of 415 trees as errors and none safe. A
read-only lane is finding the reaper's failing check, where the space went, and a ranked list of
safe candidates. I decide the reclaim from its report. The floor and the cleanup jobs are not
changed by any lane. T3's own worktrees are on the internal disk and are not affected.

**Order of work now.** Paper: inventory, skillpack and first notice, then the staged route. The
pool diagnosis and reclaim. The browser lane's rehearsed release. The ask-and-return micro-fix and
carrier refresh. The launcher rewrite, then the Grok Bot link proofs and one sitting. Computer-use
runs, the delta check and my choice of homes.

## 39. Amendment, 2026-11-12 04:10 UTC: Paper is connected, the pool diagnosis is in

**Paper, installed by me (03:41 to 03:57 UTC).** I read every staged script and the source at the
lane's commit before running anything. Each staged hash matched and each step ran as written.

- The design skillpack is installed in the T3 skill bundle on the M2 and on ubuntu2. It carries the
  carrier rules, the ten-step studio protocol, the design-memory convention, a batch screenshot
  exporter and five specialist child briefs (art director, canvas designer, design critic, UI
  implementer, visual verifier).
- A new guarded Paper runtime is built on the M2. It replaces nothing.
- ubuntu2 has one key for the design profile, admitted on the M2 for one fixed command only, and
  one new MCP entry in its provider home. Checked from ubuntu2 over the real route: five tools
  listed, the inspect call answered connected, a requested shell command was ignored and a
  terminal was refused.
- Both programme leads have the notice: what already lives in Paper for them, how to connect, the
  one-writer rule, the skills, the specialist briefs, the holds and the limits.

**Not yet proven, so not yet opened.** A read and a screenshot from a new T3 session on ubuntu2
through the registered entry, and one guarded edit with readback on a throwaway file, including a
stale-snapshot refusal. Until the lane returns that proof, remote guarded edits stay held; reads
and screenshots are open. The Prophet lead was told this in the notice and gets one line when it
changes.

**Still to install.** The read profile on the other linked hosts, one host at a time, after the
session proof passes. The lane stages a keygen brief and a register brief per host and says which
hosts cannot take the route as staged. Then the qualification fix for the three tools the guarded
server does not yet admit, and a guarded local registration on the M2 to replace the vendor relay.

**Two defects in the staged text, returned to the lane.** The notice said two skill folders on the
M2 are links into the bundle; they are real folders without these skills. The install steps gave
no way to list the hidden registration backup, and a child rightly stopped there.

**The worktree pool.** The read-only lane found one cause. The scheduled reaper's Python process is
denied reads on both external volumes by the operating system's privacy control, so every tree is
judged an error and none is ever safe. Separately, the scheduled job is started with both the apply
and the dry-run flags, so it could not remove anything even if it could read. Space is going at
about 11 GiB an hour per volume: 152 new trees were minted in one day and nothing is reclaimed.
Candidates on the second volume alone: 146 clean, merged, idle trees, about 190 GiB. A further 779
orphaned folders are outside the reaper's scope and need their own ruled path.

What I do with it: run the incumbent reaper from this session, report-only first, and apply only
if it classifies and only through its own guards (three days old, content on the remote, clean, no
process inside, non-force removal, human roots protected). I change neither the floor nor the
scheduled jobs. The privacy grant for the scheduled process and the job's flags are the storage
owner's settings; they go to the Chairman as one line with the evidence.

## 40. Amendment, 2026-11-12 07:15 UTC: Paper is proven and read on five hosts; the pool rule for dead folders

**Paper is proven.** From ubuntu2 a session read a file and took a screenshot, made a guarded edit
on the throwaway file with a readback, and had a stale snapshot refused. I read the proof and
viewed the image. The hold on Prophet's remote guarded edits is lifted and the Prophet lead was
told. The read profile (three tools: catalog, inspect, read) is now registered on m1studio,
ubuntu0, ubuntu3 and mastermind-pc as well. Each host has its own key, made on that host; each key
line on the M2 is restricted to that host's address and to one fixed command, and was appended with
a backup. A probe and two refusal checks passed on every host. A new-session proof per host is
running. ubuntu4 is offline and has nothing.

Next for the lane, all staged for me to install: the three tools the guarded server does not yet
admit (new artboard, create and set tokens); a guarded local registration for sessions on the M2;
and the skillpack for the four hosts that have an old one or none.

**Ruling 17 is in force** (section 39 was written before it): two sides that cannot switch in the
same instant overlap for exactly one release. The bridge release waits on the round built to it.

**The worktree pool: what holds it today.** Three hand runs of the incumbent reaper from this
session removed 55 trees through its own guards. Margin above the floor is about 49 GiB on the
first volume and 5.6 GiB on the second. Each further run frees only what has just turned three
days old, and so far that has all been on the first volume.

**A correction to section 39.** The scheduled job is not denied on every run. The denial comes and
goes per start; the job's flags still make it report-only. Both are the storage owner's settings.

**What does not hold: 779 dead folders on the second volume.** Their pointer names a worktree entry
that no longer exists, so the reaper never sees them. They cannot be proven clean the old way: the
commits they were made from are gone from the store, and the harness writes its own files into
every tree. The archived-worktrees folder (67.5 GiB) is the same class. The incumbent archive tool
skips any folder with a git pointer, so it does not cover them either.

**Ruling for the class.** A dead folder is removed only when, immediately before removal, every
file in it falls in one of three groups:

| Group | Test | What happens |
|---|---|---|
| On the remote | The file's bytes are a blob reachable from a remote ref of its store | Nothing kept; it can be fetched again |
| Regenerable | It sits under a named build or cache folder on a short list I rule | Nothing kept |
| Unique | Everything else | Copied to an archive, listed back, every hash compared; then the folder goes |

A folder is left and reported when its unique bytes pass a cap, when a process is inside, when it is
under three days old, when its pointer is in fact live, or when anything is unclear. The run stops
at the first unclear result. This replaces "prove the whole tree against one commit", which removes
nothing, with a proof per file that loses nothing.

A lane builds the tool and tests it on fixtures only, reports on a sample of 40 real folders by
reading, and finishes the first volume's census. Running it for real is mine, after an independent
review of the tool and my own read of it. Folders that belong to another programme's proof work
(the first volume's `tmp/`) are asked about, not swept.

**A class rule from another programme's question.** A child that is already isolated in a worktree
does not mint a second tree. The harness refuses to enter it and refuses git commands aimed outside
its own tree; that refusal is a real control. Two branches at once means two children. The recipe
text in the Macro guard says otherwise and its correction waits for the Chairman's word.

## 41. Amendment, 2026-11-12 08:05 UTC: the Chairman's four orders; carrier installed; E1 decided

**Orders received 07:28–07:30 UTC.** (1) Move every Hermes bot, with its conversation history
and memory, into Mastermind OS. (2) Link the persistent memory the Hermes bots use (the `omh`
memory provider) so always-on teammates can reach it. (3) He is now a daily user of the
Mastermind OS app, so builds launch as a new app (ruling 18). (4) A dedicated Cloudflare tunnel
is accepted as the public endpoint for the Grok Bot link, and a subagent may create it using
the Cloudflare session in his personal Chrome profile. He also handed me the E1 decision.

**Lane HM (Hermes bots and memory), one lead for both orders.** Three defaults, mine, which the
lane may only overturn with census evidence:

| Subject | Default |
| --- | --- |
| Bots | Each distinct working profile becomes a teammate through the existing set-up and cut-over tooling, one at a time, by the principal. Duplicate or experimental profiles are listed for a ruling, not moved. This replaces the earlier limit of three teammates. |
| History | Exported, not transplanted. Each bot's past conversations go into a read-only archive in its own teammate home with a search tool. Nothing is written into the team server's database by hand. If the server has a supported way to create a conversation with earlier messages, the lane proposes it and proves it on a development server. |
| Memory | One store, not two. Teammates reach the same `omh` memory Hermes uses, through a narrow tool that calls `omh`'s own code. If two writers are not safe, reading is linked first and writing comes back as a design. |

The lane works on copies, in its own folder, and installs nothing. It replaces the Revision 7
line "do not copy internal session databases into another runtime" only to this extent: a copy
into the lane's private scratch folder for the export, deleted afterwards.

**Cloudflare tunnel.** One child creates a named tunnel and one hostname and leaves it not
running. The tunnel client is installed and started by the principal when the bridge is ready.
The Chairman's sitting for the Grok Bot link loses its tunnel step.

**E1, decided: the two private-network paths stay.** `/studio-fabric` and `/studio-design` are
the addresses the existing Subagent Fabric gives its remote workers and its operator stop hook
(`ops/native_fabric/*/native_remote.py`, `integrations/session_bridge/paid_operator/`). Removing
them would break that Fabric. The exposure is limited to devices on the Chairman's own private
network. The repair is a credential check inside the gateway; it goes on the later list and is
not a Paper lane matter. Paper's own remote route does not use these paths.

**Wake carrier.** Installed for all three teammates at 07:15 UTC (old `69846ac9…`, new
`3b546177…`). Design Lead and Assurance each answered a real task on it. Secretary's proof is
waiting: a session started from the app inside Secretary's conversation chose another provider,
and the carrier refuses a conversation whose provider differs from the teammate's binding. That
is correct behaviour for the carrier and a product gap for the app: a teammate's conversation
should not offer another provider. It goes to the team-roster work.

**Paper.** New sessions on four more hosts each reached the M2's Paper and read the test file.
Three of them could not read the text in the returned image; that is the missing auxiliary
vision, which lane BCU owns, not a Paper fault. The inspect tool takes no file and returns
whatever file is open on the M2; the skillpack must tell designers to name the file.

## 42. Amendment, 2026-11-12 08:45 UTC: a teammate is its provider instance; first census of the Hermes bots

**What happened.** The Chairman used the Mastermind OS window to talk in Secretary's
conversation and the window let him pick the general provider and another model. Those two
turns (07:23 to 08:12 UTC) ran without Secretary's charter and without the teammate fence,
because both are attached to the launch of the `secretary` provider instance and nowhere else.
The gate file, the limits file and the charter are unchanged; nothing was broken or bypassed by
a lane. The conversation still points at the general provider, so the wake carrier refuses
Secretary's board tasks and Secretary's board status reads `error`.

**Ruling 20** (deputy rulings): a teammate is its own provider instance, not its conversation.

| Part | Owner | State |
| --- | --- | --- |
| Fresh primary conversation for a cut-over teammate (the existing `rotate` needs a file that cut-over teammates do not have and refuses on status `error`) | lane RF through the deputy; independent review; rehearsed on a dev copy that reproduces the provider switch; the principal installs | ordered |
| Secretary's task-edge proof, the return edge and the baseline (carrier refresh steps 2e, 3, 4) | principal | waits for the row above |
| The window must not offer another provider in a teammate's conversation; plain notice until then | team-roster work (release -4 list) | ordered |
| Findings of the Chairman's own session (preview browser is not disabled; device keys default off; the pinned fetch tool is the one real build; a managed MCP config path; two of its children disagree on whether ambient MCP servers reach a live session) | deputy hands them to BR, BCU and HX so they are not rediscovered | sent |

**Hermes census (lane HM, first file).** Fifteen bots, not fourteen: the default Hermes home is
itself the Slack "Meta-CEO" and the Chairman's main Hermes chat. Three are moved, nine distinct
ones are staged next, one is an experiment made today, and two share the Meta-CEO identity.
5,093 conversations and 209,475 message rows across 15 stores, no conversation in two stores.
Memory is two layers: small per-bot files, and ONE shared `omh` store outside `~/.hermes` with
288 approved records. One finding changes the order of work: Secretary was moved on the board
but ten of its eleven Hermes timers are still armed, so today two systems can act as Secretary.
That is the "one initiator per effect" rule (plan V3 section 8a) already broken, and the lane's
install list treats it first. Moving or disarming those timers is a write to Hermes and is the
principal's act on the lane's rehearsed list.

**Cloudflare tunnel.** The first child stopped cleanly before authorising: the zone
`mastermindx.ai` was found by rule (one of five zones), but the browser plugin cannot click a
table row that is not a link or button, and the debugger path is refused in that profile
because another extension has a frame in the page (not routed around). Nothing was created. A
second child reads the plugin's own contract first and, if the plugin cannot do it, uses
Peekaboo on that one window under the idle rule. The plugin gap (clickable rows are not
offered as elements) goes on lane BR's later list.

