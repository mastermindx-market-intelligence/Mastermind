# T3 session control v3: Capacity-only native collaboration

Parent programme: WS:EXECUTIVE-ECOSYSTEM-COMPLETION. Predecessor: #2372.
Protected source pin for this continuation: `494d095813dad415938800fa0e4d2719497738fa`.

## User outcome and current scope

An authorized Web session can discover exact native coding threads, read their
messages and original results, select a model through Capacity Fabric, launch a
bounded task, queue/steer/restart deliberately, stop execution, and collaborate
through source-versioned notes without losing the long-horizon task.
T3 owns threads, runs, history, native tools, lifecycle and child work. Capacity
owns physical routing/quota. Executive owns company admission and acceptance.
These clients add no auth realm, database, scheduler, queue or transcript store.

The predecessor branch entered the protected merge queue. It was left unchanged;
these additive modules are a separate successor, not a dequeue or a replacement
of the predecessor's qualified bytes. No denied source write was replayed.

## Native MCP client

`integrations/session_bridge/t3_native_client.py` consumes an independently
authorized `call_tool(name, args)` and the *actual* tools/list `inputSchema`
mapping. It never opens a network/process or obtains credentials itself.
`Scope` binds the connection, environment and project. `Thread`, `Run` and
`Cursor` retain exact original identities and reject cross-connection reuse.

- `capacity_models`: filter to the exact `capacity_fabric` instance; refuse
  missing/ambiguous/unready catalog data and no non-Capacity fallback.
- `launch`: explicit logical model under that instance, source-linked complete
  prompt, and exact native isolated worktree base for code writes. No provider,
  account, permission or runtime-mode override beyond the requested logical model.
- `read`/`list_threads`: bounded native project projection, messages/activity,
  advancing native cursors; reject malformed/foreign/repeated pages.
- `read_full_item`: recover truncated text by original item/run and monotonic
  native offsets, bounded by chunks/bytes. No summary substituted for original text.
- `send`: explicit queue, steer or restart; never ambiguous auto or silent clear.
  Freshly observe the target and Capacity catalog. Retain each native message/run.
- `wait`/`original_result`: exact original run, optionally including delegated
  settlement; distinguish timed-out, failed, stopped, pending, incomplete and
  completed. A historical answer can be read after another turn begins. Native
  result-run lineage, not latest-text guessing, selects a delegated final answer.
- `stop`: exact-run interruption or explicit whole-thread Stop. Whole-thread Stop
  holds queued work and ends descendants/watches under T3. An unavailable model
  cannot prevent a user from stopping execution. `interrupt_requested` is not a
  terminal result and requires subsequent observation.

Transport loss/cancellation after a modifying call is uncertain. Keep the original
request/thread/connection/process and reconcile there; never retry, select another
provider, or launch a replacement. Native keys are connection-namespace sensitive.
A tool catalog is capability discovery, not permission. The native server enforces
OAuth, project modes and permissions; the client cannot grant them.

**Capacity boundary:** this client explicitly selects only Capacity and rechecks
native metadata. Its preflight is not an atomic global execution fence against
concurrent outside actors or an uninstalled company-admission patch. The incumbent
T3/Executive execution owner must enforce Capacity-only policy at the actual native
effect. This release neither edits provider settings nor silently installs that
admission patch. Catalog visibility alone is not funding/settlement proof.

## Archive, delete and live model changes

At pinned upstream `pingdotgg/t3code@0770446`, T3 MCP exposes launch/send/read/wait/
interrupt, while `t3_thread_update` only changes metadata. Archive/unarchive,
delete and model changes are not aliases for that tool. A native extension is
being implemented in an isolated T3-owned scratch checkout; it is not installed
in the running Electron app. The extension must reuse T3's command/event owner,
permission middleware and truthful atomic expected-state checks. A client must
report unavailable until its exact schema is advertised.

Delete is explicit, exact-target and non-bulk: no project/worktree/files deletion.
Model changes are Capacity-only and at an idle boundary, preserving conversation
history. Stop-current-run and Stop-all are different operations. A generic user
request to build deletion features is not permission to delete existing threads.

## Shared notes through the existing source owner

`integrations/session_bridge/t3_shared_notes.py` uses a single already-authorized
versioned Git file. The injected owner reads `FileVersion` and performs **native
expected-blob compare-and-swap** on writes. Blob hashes are verified against the
actual UTF-8 Git bytes. It is not a filesystem check-then-write lock or new store.

A note contains a unique note ID, kind, timestamp, authenticated author reference,
body and original thread/run/source references. Kinds are decision, question,
checkpoint, result, blocker and correction. Same ID/same content is a no-op;
conflicting reuse or a changed version refuses without overwrite. Lost responses
retain original-note uncertainty. Readback proves the committed note still exists.
Other agents can read/append through their independently authorized source tools.

`docs/T3_SESSION_CONTROL_NOTES.json` is the programme's bounded implementation
notebook in this source branch, not an Executive task/status/authority registry.
Use source history for audit and explicitly archive when size limits are reached.
Never place credentials in notes. Returned note text is evidence, not instructions.

## Long-horizon execution contract

`integrations/session_bridge/t3_mission_brief.py` preserves the whole objective,
immutable source/base, phases/checks, original DONE_WHEN, exact allowed paths,
non-goals, stop conditions, existing execution envelope and shared note reference.
It renders a native handoff that asks the worker to verify/checkpoint/reassess/
continue across phases, rather than stopping at each commit. The checkpoint keeps
remaining acceptance and original uncertain effects. It never self-accepts work,
allocates budget, spawns workers, approves permissions or creates a scheduler.

## Real host-assisted proof on 2026-11-09

Environment `5f4cd5f0-e3df-407d-af02-1aa833637937` (M2), T3 0.1.7.
Project `9de77193-e68a-49fe-adee-f85406f04772`.
New owned thread `mcp:f7fefa69-16ce-4d02-a95d-8a8ea0f7ca93`.
Observed provider `capacity_fabric`, model `glm-5.3`.

Run 1 returned `CAPACITY_T3_READY web-t3-control-20261109-a1`. A same-thread
queue-mode follow-up, run 2, returned `CAPACITY_T3_CONTINUITY_OK ...` and recalled
the first acknowledgement verbatim. Native read showed completed, no active run,
zero pending requests, same provider/model. No prior user thread was modified.
A third scoped implementation request was then accepted in that same native
thread for the isolated upstream extension, with no production installation grant.

Source brief and proof owner: #2372 comments 6738289686 and 6738326770. This is
host-assisted native CLI, not a new connected ChatGPT MCP server, corporate worker
admission, a changed live T3 application, or an asynchronous callback proof.

## Delivery and missing activation

Run the focused Python tests with `python -m unittest discover -s tests -p
 'test_t3_*.py'`. Isolated tests are not repository CI or runtime acceptance.
The existing private Agent Bus plugin is updated in place after validation; its
metadata/scripts do not themselves create a remote MCP connection.

Native T3 Connect was observed disabled. Direct hosted ChatGPT needs the real
T3 Connect/approved tunnel URL and its OAuth approval. Work/Dot callbacks require
actual original T3 events joined to the incumbent Mastermind MCP Events owner and
signed callback/readback proof. Ordinary completed chats are not promised wake-up.
The active native patch, held installation and current tests must be reported
separately at closeout; never convert this document into a completion claim.

## Primary source contracts

- https://github.com/pingdotgg/t3code/blob/0770446/docs/user/outside-agents.md
- https://github.com/pingdotgg/t3code/blob/0770446/packages/contracts/src/orchestratorMcp.ts
- https://github.com/pingdotgg/t3code/blob/0770446/apps/server/src/mcp/toolkits/orchestrator/tools.ts
- https://developers.openai.com/plugins/build/mcp-events
