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

## Native configuration, archive, queue and questions

**Capability-census correction:** the second native toolkit at
`apps/server/src/mcp/toolkits/thread/` in exact upstream
`0770446869d247a8b28c27d7ed93f47f8ff0c1e4` already provides:

- `t3_thread_configure`: read/set provider-model selection; native permission
  modes stay unchanged. The client targets only `capacity_fabric` and observes
  an idle, settled-work boundary, then verifies model/mode readback.
- `t3_thread_organize`: archive/unarchive plus other native organization actions.
  The client exposes archive/unarchive on an observed idle exact target, with
  native readback. Unarchive refuses a non-Capacity execution route.
- `t3_queue`: list/read/edit/cancel/reorder/promote-to-steer. Exact native queued
  run identity remains authoritative. Edits require the observed text fingerprint;
  clipped/stale text refuses. Promotion requires the exact current active run
  and Capacity selection. Cancel does not need a healthy inference provider.
- `t3_pending_request`: list/read/respond to **user-input questions only**.
  Permission approvals are not exposed by this tool. Responses must name the
  actual question and stay inside the original work/authority envelope.

The earlier orchestrator-toolkit-only absence statement was incomplete. Reuse
these native operations; do not introduce replacement model/archive/queue owners.
These APIs commit through T3's command owner and return a native sequence, not
parent acceptance. Readback loss retains the committed sequence in the unknown
postcondition error. Client-side expected timestamp/text checks are **not atomic
multi-writer CAS**; their results explicitly report this limitation. Preserve
one modifying owner, or require the native strict extension before raced writes.

**Deletion and strict atomic guards:** the original native extension task is
being reviewed in its isolated scratch checkout. The first candidate's
check-then-act guards do not satisfy strict atomic acceptance and are not accepted
for installation. Preconditions must be joined to the original serialized native
command decision/commit boundary, not merely checked in an MCP handler. Delete
must be explicit, exact-target, non-bulk and native-tombstone-only: no project,
worktree or file deletion. The parent may not invent or call absent native tools.

Stop-current-run and Stop-all are different operations. A generic request to
build deletion features is not permission to delete existing user threads. No
live Electron/server patch or restart is part of these source clients.

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
- https://github.com/pingdotgg/t3code/blob/0770446869d247a8b28c27d7ed93f47f8ff0c1e4/apps/server/src/mcp/toolkits/thread/tools.ts
- https://developers.openai.com/plugins/build/mcp-events

## Result-resume and stop-scope hardening

`original_result` now returns `ResultProgress` when its page budget ends. Pass that
progress back to continue: it retains only original run/cursor/item references,
not a caller-supplied answer. The final result re-reads the candidate from the
native owner, so an earlier result is not lost when later unrelated turns span
more pages. Changed lineage or a forged/missing candidate refuses. A later complete
original assistant result supersedes an earlier oversized message.

Stop now confirms native project/thread identity even when model capacity is down.
It still never requires the provider to be available to stop, but a fabricated
client-side Thread object cannot target a different project. These changes add
seven focused regressions. The current combined client/notes/mission suite has
123 isolated cases after adding the original second-toolkit coverage.

## Host CLI control path and active native work

The incumbent CLI's `thread` subcommands do not yet expose all native MCP tools.
A disjoint Capacity-backed T3 coordinator (`web-t3-cli-adapter-20261109-a1`) was
assigned exactly one native implementation child to extend the existing CLI with
a closed tool allowlist while reusing its native `withThreadTools` and
EnvironmentAuth lifecycle. No replacement credential store, public server or
live application restart is allowed. This is active source work, not a claimed
installed command. The original lifecycle worker and its queued review/notes
phases remain in their own native thread; neither lane overwrites the other.

T3's own `up --connect` help explicitly warns that a noninteractive restart can
stop running turns. It has not been invoked against active user sessions. Direct
cloud activation therefore remains a deliberate native maintenance/OAuth step,
not a hidden side effect of installing this skill.

## Exact-run versus thread-final settlement

The native T3 `ThreadManagementService.wait` at upstream 0770446 can, with `untilDelegatedWorkSettled`, nominate a thread-wide `resultRun`. That can be a later independently queued user turn. The client therefore keeps `original_result` on exact-run completion (`untilDelegatedWorkSettled=false`) and never substitutes another final run. `wait(..., include_children=true)` remains available as an explicitly separate thread-settlement observation; its returned final-run identity is not silently treated as the original answer. A native restart that changes the run identity remains a visible lineage conflict requiring explicit native recovery rather than a guessed match. Large timeline pages bound their per-item text request and retain exact item expansion.

## Resumed Agent Bus integration - v4

Current Chairman assignment resumes Design Agent Bus Architecture: complete the
read / message / queue / steer / start / stop / archive / delete / Capacity-model
selection / shared-notes / long-horizon delegation journey. Original acceptance
is not reduced to a source patch, CLI catalog or merged PR.

Source operation: `t3-agent-bus-v4-20261109`, isolated managed branch
`sol/web-t3-agent-bus-v4-20261109`. Governing protected pin:
`f357bd0b3c31ee40f028590909678f01a3a9d413`. Parent remains
`WS:EXECUTIVE-ECOSYSTEM-COMPLETION`; this extends this existing plan, not a new
programme or lifecycle store.

### Recovered evidence and custody

- Predecessor #2372 is protected-merged at
  `6fc220a1770b196f7b1e79add63698fbed022756`; #2374 is protected-merged at
  `0450fba70006ece6a260d3d606ca2503bb8d9f89`. Preserve their accepted Python
  client, notes and original-run proof; do not recreate those conversations.
- Original lifecycle thread `mcp:f7fefa69-16ce-4d02-a95d-8a8ea0f7ca93`,
  ordinal 7, and CLI coordinator `mcp:5b3b360e-1842-4b27-b510-e38b9546941b`,
  ordinal 4, both returned completed with no active run or pending question.
  Their source-only artifacts remain in their original T3 scratch locations.
  The coordinator consumed its original single child's ordinal-2 result;
  the prior failed ordinal-1 transport attempt remains distinct.
- Both candidates target upstream `pingdotgg/t3code` at
  `0770446869d247a8b28c27d7ed93f47f8ff0c1e4`. No candidate was installed.
  Preserve upstream MIT licensing and original native auth/command owners.
- Current review does not accept same-provider-as-caller as Capacity-only,
  millisecond timestamp equality as a strict revision guard, or unbounded
  output as a bounded native bridge. Repair the relevant original source seams.
- Preserve #2375 continuity, #2394 team graph, #2338 runtime/admission,
  #2401 computer/browser and #2367 live Capacity policy/service writers.
  No provider config, credential, live user thread, server restart or child
  replacement is authorized merely by this plan.

### Implementation and acceptance frontier

| Node | Dependency | Outcome and discriminating acceptance |
| --- | --- | --- |
| AB1 | recovered #2374 | Qualify original CLI bridge, real native catalog/read and exact envelope/error behavior; reject absent/duplicate/malformed capability data and bound transport output. |
| AB2 | AB1 | Compose an injected native-CLI transport with the existing Python client; no subprocess/auth/queue owner added. Preserve cancellation, unknown effects and original request identity. |
| AB3 | original lifecycle patch | Strict native delete/model changes at the existing serialized command boundary: exact target, robust expected state, Capacity-only selection, native permissions and original receipts. Race/foreign-provider/active-child/queued-work tests must fail before effect. |
| AB4 | AB2, AB3 | Expose only actually discovered strict capabilities; explicit delete confirmation and retained-tombstone-only semantics, no filesystem deletion. |
| AB5 | AB1-AB4 | Deterministic exact-base donor package plus focused native/Python security/concurrency tests and a reviewable protected-release candidate. |
| AB6 | AB5, actual installation owner | Non-disruptive eligible CLI installation and native server maintenance only after original work is protected; prove loaded bytes, rollback and actual controls on newly owned disposable targets. |
| AB7 | existing notes/mission/team owners | Consume a real delegated long-horizon result with retained parent/child/run identity, shared-source CAS, queued continuation and original-parent acceptance, without duplicating prior accepted proof. |
| AB8 | actual native connection/event owners | Direct cloud OAuth and signed event return only through existing supported owners and real consent/readback; ordinary ChatGPT foreground reads are not unsolicited wake-up. |

DONE_WHEN: the original authorized user can perform the complete journey through
qualified native owners, Capacity is the sole new-execution/model-selection
route, effects/results remain recoverable under concurrency and disconnection,
and the original parent consumes actual outcomes. Source, protected merge,
installation, native execution and parent acceptance remain separate claims.

Current phase is AB1-AB4 source integration and qualification. The principal
retains the atomic-boundary judgment and direct integration under
`PRINCIPAL_JUDGMENT` / `LOWER_TOTAL_OVERHEAD`; no substitute native labor child is
started. Existing original workers are not resumed or duplicated. All live
activation, actual platform permission and release controls remain binding.
