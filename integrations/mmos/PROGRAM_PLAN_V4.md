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
| T1 shared conversation | DONE_WHEN 1 to 3, in the dev bundle against an isolated T3 server, then paired to the real one by the principal | starts now, critical path |
| T2 teammate binding and actor dispatch | The binding record on existing owners; DONE_WHEN 4 and 5 on a test agent in the dev Paperclip instance | starts when L9 has landed |
| T3 Team fork | Teammate list and work cards as a thin fork of the T3 web client | starts when T1 is proven |
| T4 work loop | DONE_WHEN 6 and 10, on TeamLink plus the engine from L1 | after T2 |
| T5 routine and attention | DONE_WHEN 7 and 8 | after T2 |
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
