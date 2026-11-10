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
| T6 team server | An always-on headless T3 server owned by Mastermind, separate from the Chairman's T3 Code app, that the window and the teammates use | started 2026-11-10. See section 11 |
| T2 teammate binding and actor dispatch | The binding record on existing owners; DONE_WHEN 4 and 5 on a test agent in the dev Paperclip instance | accepted 2026-11-10 at trunk `da2097e4b` (two test teammates, personas and tool limits, rotation, one wake one return, attack pass with one defect found and fixed; see `T2_TEAMMATE_BINDING_AND_DISPATCH.md` and section 10) |
| T3 Team fork | Teammate list and work cards as a thin fork of the T3 web client | starts when T1 is proven |
| T45 milestone loop | DONE_WHEN 6, 7 and 8 on the two test teammates in the dev instances: assignment alone starts the work, one task with one output that opens from the issue and from the asking conversation, one routine fired once with no window, one attention item cleared | started 2026-11-10. See section 10 |
| T4b governed coding job | DONE_WHEN 10: a task that needs code becomes one governed coding job through the socket door and the L1 engine | after T45 |
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
