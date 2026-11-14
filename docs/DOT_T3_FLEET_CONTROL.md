# Dot / T3 fleet control and canonical returns

Operation: `dot-t3-fleet-20261113-sol-001`. Parent plan: [2026-11-13 Dot/T3 fleet](plans/2026-11-13-dot-t3-fleet.md).

**Status: implemented source and hermetic/in-process integration; NOT installed on the six accounts, NOT a production Dot wake, and NOT completed fleet acceptance.** The live native-environment probe in this operation received an explicit platform safety refusal. That logical call must not be repeated through a new tool, account, provider, encoding, Secretary, or plugin view. Source work and test fixtures do not remove that fence.

## User journey and ownership

A Dot should be able to commission a bounded native task, inspect its exact thread and children, supervise several original runs, consume a native response, and continue the same thread without receiving general shell access. A response must belong to the exact original environment/project/thread/run; a later answer or a worker's summary is not a substitute.

This change extends existing owners rather than installing another orchestration system:

| Concern | Owner / integration |
| --- | --- |
| Native links, projects, threads, runs, queues, questions, transcripts | Native T3 outside-agent MCP through its own CLI authentication |
| Company admission, lifecycle, provider/account/budget | Existing Executive / Capacity owners; a native UI or model catalog is not admission |
| Account-authenticated HTTP and tool exposure | Existing Studio gateway, optional `t3Control` and restricted `t3Only` view |
| Fixed native consumer | `t3_dot_native_owner.py` + `t3_dot_port.py`, over the existing `T3NativeCliTransport` / `T3NativeClient` |
| Original return linkage and observed reply digest | Existing Executive Runtime events, via opt-in `T3OriginalReplySource` |
| Subscription secrets, authorization refresh, callback signatures and delivery | Existing Runtime reply-subscription, retained-authorization and signed-delivery owners |
| Canonical response consumption | Existing `session_reply_read`, extended with an explicit T3 response schema |

No new credential store, transcript database, job lifecycle, callback queue, scheduler, polling daemon, or provider router is introduced. No account or service is armed by importing these modules or merging their source.

## Twenty typed controls

| Group | Tools | Important semantics |
| --- | --- | --- |
| Discovery | `t3_fleet_environments`, `t3_fleet_projects`, `t3_capacity_models` | Current authorized native links/projects/logical models only; unreachable is not ready. URLs and credentials are not exposed. |
| Observation | `t3_thread_list`, `t3_thread_read`, `t3_thread_item`, `t3_thread_children`, `t3_threads_snapshot` | Original native messages/activity, exact item pages and actual subagent lineage. Forks are not relabeled as delegated children. Snapshot reads at most 12 exact targets, with independent failures and no background monitor. |
| Original result | `t3_run_result` | Exact historical run, bounded pagination with returned progress; never substitute the newest thread reply. |
| Execution | `t3_thread_launch`, `t3_thread_send`, `t3_thread_stop` | Capacity-selected logical models. Code writes need an exact isolated-worktree base. Queue, steer and restart are distinct. A stop request is not terminal-stop proof. |
| Native queue | `t3_queue_read`, `t3_queue_change` | Existing queue only. Edit/cancel/reorder/promote retain the exact queued-run identity; edit requires the observed text digest. No automatic retry. |
| Questions | `t3_questions_read`, `t3_question_answer` | Actual native user-input questions only. These tools cannot approve permission requests or authorize new spending/scope. |
| Configuration/lifecycle | `t3_thread_configuration`, `t3_thread_set_model`, `t3_thread_archive`, `t3_thread_delete` | Current native snapshots and Capacity model checks. Strict model/delete operations require the installed native atomic lifecycle extension. Missing extension returns unavailable; no guessed APIs or fallback. Deletion needs an individually enrolled exact thread and explicit title/boolean confirmation. |

Read results are bounded and best-effort secret-pattern redacted; private reasoning item types are omitted. Redaction is not a replacement for native account/project authorization. Work inspection includes actual child-thread messages, activity/tool results and source/artifact references. Existing GitHub readers remain the appropriate way to inspect published diffs. This release does **not** invent a generic remote filesystem or expose arbitrary file paths as a work-inspection shortcut.

## T3-only Dot access

An installed gateway may select `t3Only: true` together with an exact `t3Control` profile. This view exposes only the enrolled T3 tools, `studio_ping`, and bounded original-result paging. It does not proxy Desktop Commander tools, resources, prompts, Git publication, Paper, generic fleet retargeting, Bash, SSH or file access. The generic backend is not needed for the restricted catalog.

The restriction is enforced on calls as well as discovery. Calling a hidden host tool by name is rejected before backend dispatch. Retained output paging rechecks the T3 account profile, so a receipt does not survive revoked permission. Existing full Studio channels remain unchanged unless their owner deliberately selects a configuration; converting an existing full channel to T3-only is not an implicit authorization to remove other users' capabilities.

The profile is a bounded access configuration, not an auth or fleet registry. It contains an exact existing tunnel principal, existing native connection, fixed native executable path, T3 home, original local environment, explicitly allowed environment/project pairs, tool allowlist, exact delete targets, and invocation timeout. No wildcard project, caller-provided URL, credential, shell command, provider account, permission mode or callback secret is accepted.

The profile file must be owner-controlled, regular, non-symlink, not group/world writable, bounded, and match its installed SHA-256. The gateway injects its authenticated principal; the model cannot supply another principal. Native T3 access checks still apply on every native operation. `t3Only` is an optional view of the incumbent transport, not a means to evade a prior refusal or to claim company execution admission.

## Original-run return and signed push

`T3OriginalReplySource` is an explicit provider extension to the existing Executive Runtime. It is disabled by default and requires an actual authorized native client factory and current authorization owner. A Studio `p:tunnel:...` string is **not** accepted as an Executive principal. The deployment must resolve the real existing account/permission binding, not manufacture a projection or copy desktop credentials into a daemon.

The source has four separate effects/observations:

1. `bind(principal, run)` observes the exact native run and retains its account/connection/environment/project/thread/run references in Runtime. This creates no worker or subscription. Its deterministic original reference is retained for recovery.
2. `observe(principal, request_ref)` is called by the installed native-event producer. It reads the original native response and commits only its digest/status/provenance. Native T3 remains the only transcript owner. Lost persistence acknowledgments retain an explicit original-reference `T3ReturnEffectUnknown`; no native launch is replayed.
3. The existing reply host's `observe_t3_reply` joins that native observation to the existing subscription and signed-delivery consumer. It rechecks retained authorization and the original native result before sending. Callback 2xx remains `TRANSPORT_ACCEPTED_PARENT_UNPROVEN`; duplicates reuse the incumbent reservation and unknown external receipts are not replayed.
4. The subscribed original Dot calls `session_reply_read` with the exact returned `t3-reply-...` reference. It receives the original response, original run identifiers and digest, redaction indication, and `parent_consumed: false`. Reading, judging and accepting a result are separate.

The event uses the existing `session.reply_committed` catalog and signing owner with a strict T3 namespace. It cannot impersonate an Agent Dialogue result: `t3-request-...`, `t3-reply-...`, and `t3-native-reply-...` are validated together, while the original Codex/Claude namespace remains separately validated. Native notification content cannot authorize a task or become an instruction.

**Source composition is implemented; production selection is unproven.** The existing reply-event host now restores exact-run observers from its retained current subscriptions. Observers use T3's routed `t3_thread_wait` and bounded pending-question reads, share original-run handles across subscribers, stop on unavailable/uncertain source effects, and drain admitted callbacks on unsubscribe/shutdown. They do not launch inference or create another service, credential flow, queue or retry owner. The local-root-only Paperclip native-watch donor was not copied into this fleet path. The source composition is exercised through the actual HTTP MCP/private-bridge/Runtime path with fake native and HTTPS peers; no real Dot subscription was activated.

The authenticated original caller uses `session_t3_return_link` on its exact observed Run receipt. This requires existing submit scope and returns stable `request_ref`/`read_ref` without launching a worker or registering a callback. ChatGPT's MCP Events owner then subscribes to the exact original request using its own callback credentials. `session_t3_return_status` separately reports original-binding and observer state. Callback receipt, original-content read, parent consumption and task acceptance remain distinct.

The same subscription supports exact original answer, pending user-input question, and terminal-without-qualified-answer notifications. `t3-native-question-...` reads return `question_pending` and `run_complete=false`; `t3-native-status-...` reads return the observed terminal status with `answer_qualified=false` and `successful=false`, never fabricated response text. Failed, cancelled, interrupted, rolled-back or completed-without-qualified-answer runs are not silently called successful. Both require their exact notification `message_key`; a default read never substitutes the latest question or status for the original answer. Permission approvals are not user-input answers. Partial pages, unavailable history or an unproven terminal state remain unavailable and never authorize a restart.

## Capability qualifications observed in this operation

- The existing Agent Bus overlay reproduced from upstream T3 commit `0770446869d247a8b28c27d7ed93f47f8ff0c1e4`; its native CLI bundle built successfully in an owned artifact directory, without editing the dirty native checkout or restarting T3.
- Server-only native helper tests: 35 passed.
- The built helper's read-only native catalog against M2 returned 13 actual tool schemas. Strict native lifecycle extension was absent; strict delete/model controls therefore remain unavailable on that observed stock runtime.
- The following native environment read was blocked by platform safety checks. No native launch, original-run round trip, callback registration, runtime activation or account install followed it.
- New Python control/return/contract tests and actual MCP request/response integration tests use simulated native transports/callback receivers. They exercise real parsing, Runtime persistence, encrypted subscription storage and signature/delivery logic, but do not prove production connectivity.
- The existing Executive release has reply-event source installed but `reply_events_armed` is absent/default off. The installed release did not contain the new T3 native consumer. No selection was changed.

## Fleet and six-account acceptance

The earlier native link census observed M2 plus reachable M1, PC, Ubuntu 0, Ubuntu 2 and Ubuntu 3; Ubuntu 4 was unreachable. Reachability is not inference, current provider admission, or current account authorization. Do not silently fall back to another environment or model after a denied or uncertain call.

The Secretary inspected eight existing Studio channel configurations. Several represent multiple workspaces for the same logical account, so eight channels do not prove six installed users. Account/channel pairings remain unverified. No new Dot/T3 account installation was performed.

The reference-only return also exposed conflicting historical notes: a c4/chatgpt4 lane-driving restriction appears in Secretary instructions without its original protected-law reference, and a skill claims a Ryan channel that is absent from the inspected Studio launchd configuration set. Neither a historical author nor an unverified note is a new universal release gate. Preserve the discrepancy; resolve through the current owner and current outer assignment before account-driving changes. Do not publish account emails, credentials or private tunnel URLs in source evidence.

For each of the six intended accounts, acceptance still requires the actual signed-in identity/workspace, exact selected plugin, authorized T3-only endpoint/profile, catalog read, bounded original native execution/readback, event subscription and correct original Dot consumption, plus revocation/unsubscribe and no-cross-account negative checks. No checkmark may be inferred from a source merge, channel label, tunnel liveness, webhook 2xx, or installed skill alone.

## Installation / rollback sequence for the existing owner

This is an ordered release contract, not permission to repeat the refused live probe:

1. Qualify and protected-release this source under its actual CI/security holds. Preserve the operation's exact head and platform fence.
2. Use the incumbent native release owner to select a qualified CLI artifact and immutable source root. Do not overwrite live dirty native source or restart occupied user threads. Strict lifecycle availability is a separate native runtime selection.
3. Through existing per-account configuration custody, resolve account identities and enroll narrowly allowed native environment/projects and operations. Keep the Dot view T3-only. Profile changes require exact preimages/hash and readback; no broad permission fallback.
4. Resolve the installed Executive principal/native-access composition and original-parent return binding. The Executive daemon and desktop T3 user are different identities; the existence of both is not permission to copy credentials or launch as the desktop user.
5. Select the existing reply-event host only after its encrypted subscription and original-return owners are current. Join the incumbent native event producer to `observe_t3_reply` for trusted exact original requests; prove that path rather than installing another listener/queue.
6. Perform only newly permitted, properly authorized consumer canaries after the safety fence is resolved by its actual owner. Test account isolation, native original-run/child evidence, another enrolled environment, wrong-account refusal, unknown sends, duplicate callbacks, revocation and unsubscribe. Report callback receipt and parent consumption separately.
7. Roll back by deselecting the optional T3 profile/view and provider join through their original owners. Retain original operation/return records and uncertain effects; do not delete native history, terminate unrelated threads, rotate credentials, or remove another account's plugin as a shortcut.

## Tests

Python unit/integration coverage is in `test_t3_dot_tools.py`, `test_t3_dot_native_owner.py`, `test_t3_dot_contract.py`, `test_t3_reply_events.py`, and `test_t3_reply_integration.py`, plus the existing native/session-bridge suites. Node control and actual gateway/MCP coverage is in `t3-control.test.mjs` and `gateway-t3-control.test.mjs`. The generated gateway catalog is checked for exact parity with the Python contract.

The fixtures deliberately use fake native transport and callback endpoints. Never relabel them as a real fleet worker, real Dot, installed event owner, independent review, or completed six-account rollout.

## Exact-message pending-question returns

The existing reply-event host also accepts an original native pending-question observation via `observe_t3_question`. It rereads the actual T3 user-input request and requires native thread/run provenance; older native servers without the reviewed provenance fields fail closed for this asynchronous path. A question is not a permission approval, terminal result, or grant for new work.

A signed `session.reply_committed` notification contains only original references and a `t3-native-question-...` message key. The receiving Dot calls `session_reply_read` with both `read_ref` and this exact `message_key`. It receives `status=question_pending`, the permitted question contents, `run_complete=false` and `parent_consumed=false`. A later answer, changed question, revoked access or expired source invalidates the pending read; the receiver never silently gets a different latest question. The Dot answers through the separately authorized `t3_question_answer` tool. Final results have distinct `t3-native-reply-...` keys and are not inferred from pending-question delivery.

This source path reuses Runtime event persistence, sealed original-subscription authorization, signatures and delivery reservations. Tests simulate native and HTTPS peers. The native overlay and the actual event producer/consumer still require qualified installation and original-Dot proof; this section does not claim a live account was changed.
