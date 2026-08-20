# Executive OS Pro Sol Slack ingress — post-freeze reconciliation

**Date:** 2026-08-20  
**Parent architecture:** `research/EXECUTIVE_OS_PRO_SOL_SLACK_INGRESS_ARCHITECTURE_2026-08-20.md`  
**Linear:** `MAS-48`  
**Status:** records-only current-master reconciliation; no runtime authority is added here.

## Verdict

**KEEP THE MAS-48 ARCHITECTURE FREEZE. PR-A REMAINS THE ONLY NEXT IMPLEMENTATION COMMISSION.**

The architecture was originally pinned at Mastermind `18eb956a7dac0edca6870a39887a964b66c53d72`. Current `master` is `4f672b8f6b950010534390001f4a17ed232e0390` and includes provider-readiness hardening #92 plus the inert Operator Harness / Codex adapter #93. Neither supersedes the Pro-Sol Slack ingress architecture. Current control-service archaeology makes PR-A's local admission boundary *more*, not less, important.

Macro #6071 has also since merged the cross-repository operating law: Slack is transport/acknowledgement, Executive OS owns lifecycle state, Agent OS owns organizational knowledge/work identity, GitHub owns implementation evidence, and Linear is portfolio projection. The earlier reconciliation dependency in the architecture freeze is therefore satisfied.

This reconciliation adds two binding R2 corrections discovered after the first freeze:

1. **Production Slack must not share the existing operator control socket or `_mastermind_ops` group.** It gets a dedicated launchd-activated CEO-ingress socket owned by the same Executive control service process.
2. **Slack's Socket Mode protocol ACK is not the Executive ACK.** Slack transport receipt is acknowledged immediately; canonical admission happens afterward; crash recovery replays structured channel history through the existing idempotent CEO-intent law instead of introducing a durable bridge queue.

Where these R2 statements conflict with the parent architecture's earlier generic AF_UNIX or optional transport-provenance wording, **this file governs**.

## Current-master findings

### 1. Executive AF_UNIX authorization is still peer-wide

`control_plane/executive_service.py` authenticates the connecting AF_UNIX peer by UID before dispatch. Once a UID is allowed, the request enters the common `_dispatch_request(...)` command surface.

That surface currently includes high-impact commands such as raw `submit-ceo-intent`, `dispatch`, `cancel`, `requeue`, worker registration, backup/retention operations, and other Executive control commands.

The installed control configuration currently makes `allowed_peer_uids` the control UID plus the interactive operator UID, while `/var/run/mastermind-executive/control.sock` is the **Operator** launchd socket and is grouped to `_mastermind_ops`. Adding `_mastermind_slack` to that group or broad peer list would create exactly the privilege widening this architecture rejects.

### 2. Executive SQLite v3 preserves the required idempotency authority

PR #93 raised the Executive runtime to schema v3 for Operator Harness state, but the canonical `events` table still declares `command_id TEXT NOT NULL UNIQUE`. `JobRegistry.create_job(...)` still documents that a conflicting command ID rolls the losing Job insert back inside the same transaction. MAS-48 therefore still needs no dedupe database or transport queue.

### 3. #92 provider identity readiness is orthogonal

PR #92 hardens provider identity/readiness semantics. It does not create a Slack transport, change CEO-intent admission, or introduce Slack-specific local authorization. MAS-48 keeps the same boundary.

### 4. #93 Operator Harness is deliberately inert and separate

PR #93 adds an importable but unregistered Operator Harness/Codex adapter and supporting operator runtime. Its own architecture keeps Executive lifecycle identity authoritative and does not register the adapter as a production Executive worker merely because the code exists.

MAS-48 does not use or bypass that provider path. The Pro-Sol writeback canary ends at one canonical QUEUED Executive Job + user-visible Slack ACK + MCP readback. `CODEX_EXECUTION_REQUIRED=false` remains part of the proof packet.

This separation is intentional: cognition/CEO communication must not depend on resolving the current Codex workspace/credential entitlement blocker.

### 5. No duplicate Slack state plane is permitted

Macro #6071 is now canonical and agrees with this freeze. MAS-48 feeds the existing Executive CEO-intent/Job/Event lifecycle. It may not add a Slack queue, Slack lifecycle table, durable seat-inbox database, second scheduler, direct Agent OS write path, or Linear completion authority.

**R2 ruling:** MAS-48 V1 does **not** modify canonical `JOB_CREATED` CEO-intent provenance merely to persist Slack transport metadata. The canonical receipt stays transport-neutral. Slack message/thread IDs live in Slack and in the non-secret production proof packet, joined to Executive truth by the deterministic Slack intent ID and the bot ACK. If later audit requirements prove that durable cross-transport provenance inside Executive state is necessary, that is a separate schema/compatibility ruling after the first production proof.

This removes a needless blast-radius change to the established `mastermind.ceo_intent.v1` provenance contract.

### 6. Wake remains excluded

Nothing in #92 or #93 changes the standing Wake `NOT_ACCEPTED / NOT_ARMED` hold for MAS-48. PR-A/B/C must not import, invoke, arm, or use Wake as delivery proof.

## R2 production local-boundary ruling: dedicated CEO-ingress socket

Production V1 has **two transport sockets into one ExecutiveControlService process**, not two control planes:

```text
operator / trusted local tools
    -> /var/run/mastermind-executive/control.sock
       launchd socket name: Operator
       existing operator/control policy unchanged

_mastermind_slack
    -> /var/run/mastermind-executive/ceo-ingress.sock
       launchd socket name: CeoIngress
       owner: _mastermind_exec
       group: _mastermind_slack
       no world bits
       exactly one admitted operation: submit-ceo-request
```

Binding laws:

- both listeners terminate in the **same** `ExecutiveControlService` process and the same Executive runtime;
- `ceo-ingress.sock` is not a second service, database, scheduler, queue, lease plane or authority map;
- `_mastermind_slack` is **not** added to `_mastermind_ops`, `_mastermind_exec`, `_mastermind_worker`, or the operator account's groups;
- the existing `control.sock` path, group and command surface stay byte-for-byte unchanged unless a separately justified compatibility repair is required;
- the ingress listener requires the exact configured Slack UID from trusted peer credentials;
- the ingress listener accepts only the high-level `submit-ceo-request` envelope; it never exposes the generic dispatcher to the Slack connection;
- raw `submit-ceo-intent`, `status`, `health`, `jobs`, `dispatch`, `cancel`, `requeue`, worker-management, backup/restore/retention and every future generic command are structurally unreachable from the ingress listener;
- if implementation chooses one shared internal parser, listener identity is trusted host context and authorization occurs before any privileged command handler;
- production socket ownership/mode and exact UID/GID are install/acceptance facts, not caller fields.

This dedicated-socket topology is stronger than adding a Slack UID to `allowed_peer_uids` and then depending only on a command allowlist. PR-A should model the listener class hermetically; PR-C owns the launchd/config migration and real principal provisioning.

## R2 Slack delivery law: protocol ACK is not Executive ACK

Slack Socket Mode wraps Events API payloads in an envelope carrying `envelope_id`. Slack's documented protocol requires the app to acknowledge receiving each envelope; Slack's SDK guidance says to ACK within three seconds. That transport acknowledgement only tells Slack **the app received the event**. It says nothing about Executive admission.

Therefore V1 has two separate acknowledgements:

1. **Slack protocol ACK** — immediate response carrying `envelope_id`; emitted before waiting on Git/Agent OS grounding, AF_UNIX admission, Executive SQLite or `chat.postMessage`.
2. **Executive user-visible ACK** — a later bot thread reply only after the existing CEO-intent seam has committed/reconciled the canonical Job.

The Slack daemon must never delay protocol ACK until the Executive mutation completes. A slow grounding read or local service stall must not cause Slack retries to masquerade as distinct CEO operations.

The user-visible ACK remains:

```text
ACK | schema=EXECOS/CEO_REQUEST_V1 | operation=<key> | intent=<id> | job=<id> | accepted=<true|false> | duplicate=<true|false> | dispatched=false
```

No Executive ACK means no claim that the request entered canonical state.

## R2 crash-recovery law: replay Slack history, do not add a bridge queue

Immediate Socket Mode ACK introduces one real failure window:

```text
Slack envelope ACKed
    -> daemon crashes
    -> Executive admission not yet committed
```

A purely in-memory task would lose that request. Creating a new local durable queue would violate the one-canonical-system architecture.

V1 closes the window by treating `#ceo-control-room` itself as the recoverable transport log and Executive `command_id`/CEO-intent fingerprint as the idempotent sink.

### Startup/reconnect reconciliation

The Slack app is an internal customer-built app. Current Slack documentation keeps `conversations.history` at Tier 3 for internal apps, with up to 1,000 messages per request and 50+ requests/minute. `channels:history` is already required by V1.

At every daemon start and Socket Mode reconnect:

1. read `#ceo-control-room` from a **host-configured bridge epoch** (`bridge_epoch_ts`) through now;
2. paginate deterministically, oldest-to-newest for processing;
3. inspect only messages with the hard first-line discriminator `EXECOS/CEO_REQUEST_V1`;
4. apply the exact same workspace/channel/sender/subtype/size/schema validation as live delivery;
5. derive the Slack canonical intent ID from transport namespace + `operation_key` only;
6. query/reconcile canonical `ceo_intent_status` first;
7. if the exact normalized request is already committed, do not create another Job; ensure the user-visible ACK exists or repost it idempotently;
8. if no canonical intent exists, submit the high-level request through `ceo-ingress.sock`;
9. if the same operation key resolves to a conflicting fingerprint, emit a typed conflict and create no second Job.

No mutable “last processed Slack event” cursor is required for correctness. Re-reading already-processed structured messages is safe because Executive idempotency is authoritative.

### Bounded reconciliation and fail-closed overflow

The bridge epoch is install/config identity, not a hidden mutable lifecycle cursor. Reconciliation is bounded by explicit configured limits (message/page/time budget). If Slack history is unavailable, truncated, rate-limited beyond the allowed budget, or the bridge epoch cannot be fully traversed, daemon health becomes **DEGRADED / RECONCILIATION_INCOMPLETE** and the bridge must not claim lossless recovery.

An operator may advance `bridge_epoch_ts` only through a separate explicit maintenance procedure that proves every earlier structured request is either represented by canonical Executive intent state or intentionally rejected/voided. PR-C must write that proof requirement into the runbook; the runtime does not silently roll the epoch forward.

### Edit/delete correction law

- `message_changed` / edited structured requests are never treated as in-place mutation of an accepted operation.
- A history-reconciled message carrying Slack's edited marker is refused as `edited_request_requires_new_message`; the operator/Sol must send a new message with a new operation key.
- A deletion **before canonical Executive acceptance** voids the transport request because there is no remaining source message and no user-visible Executive ACK.
- A deletion **after canonical acceptance** cannot roll back the Executive Job; canonical state wins.
- bot/self messages and bot ACK replies are excluded before the discriminator parser so ACK cannot recurse.

This preserves the rule that Slack is transport, not mutable canonical state.

## PR-A authority boundary — R2

PR-A is still the only next build commission and must deliver one independently useful **hermetic** capability:

> A fixture/local Slack-like principal reaches a dedicated high-level ingress listener; trusted Executive code derives the canonical CEO-intent envelope and commits/reconciles exactly one existing Executive Job; the caller can read the resulting identifiers/receipt; and that ingress path cannot reach raw `submit-ceo-intent` or any other Executive control command.

PR-A may include:

- one transport-neutral CEO-request normalization/derivation module under `control_plane/`;
- compatible reuse/refactor of current Executive MCP request law;
- Slack-specific deterministic intent namespace while leaving MCP IDs unchanged;
- one high-level internal `submit-ceo-request` operation;
- a hermetic second-listener / listener-class seam in `ExecutiveControlService` with future-command default deny;
- tests proving the existing operator listener behavior is unchanged;
- hermetic E2E and canonical readback.

PR-A must **not** include:

- Slack SDK, Socket Mode, Web API, network access or Slack credentials;
- Slack history reconciliation code (PR-B);
- installer/launchd/principal provisioning (PR-C);
- modification of canonical CEO-intent provenance solely for Slack metadata;
- public webhook listener;
- direct Executive SQLite access outside the existing control service;
- raw actor/authority/worktree/branch/validation-argv authoring from the request;
- a new dedupe/lifecycle/queue/inbox table;
- dispatch, worker execution or Wake;
- Agent OS, Linear or GitHub mutation;
- changes to the reviewed public MCP schema or existing MCP intent-ID semantics merely to serve Slack.

## Required adversarial proof before PR-B

PR-A is not accepted until tests prove at minimum:

1. high-level `research_only` CEO request -> exactly one canonical Job + `JOB_CREATED`;
2. same operation key + same normalized payload -> same Job / duplicate receipt;
3. same operation key + changed normalized payload -> refusal, zero second Job;
4. malformed/unknown privileged fields cannot reach canonical derivation;
5. Slack-like UID can connect to the ingress listener and invoke the one high-level operation;
6. the ingress listener cannot reach raw `submit-ceo-intent`, status/health, dispatch, cancel, requeue, worker, backup/retention or any generic current command;
7. a newly registered future generic command remains unreachable from the ingress listener by construction;
8. existing Operator listener accepted/refused behavior is unchanged;
9. MCP schema snapshot, accepted/refused behavior and MCP-specific intent IDs remain unchanged;
10. no canonical CEO-intent provenance schema is widened for Slack;
11. no new Executive table/database/store exists;
12. no Wake import/call occurs;
13. result says queued/accepted only — never running/completed.

## PR-B additional acceptance created by R2

PR-B is not commissioned until PR-A is Sol-accepted. When later commissioned, it must additionally prove:

- Socket Mode `envelope_id` protocol ACK occurs independently of Executive admission and within the reviewed time budget;
- crash after protocol ACK but before local admission is recovered by history reconciliation;
- history replay after an already committed request creates zero second Job;
- history replay repairs a missing user-visible bot ACK without changing canonical state;
- edited/deleted/self/bot messages follow the correction law above;
- full traversal failure reports `RECONCILIATION_INCOMPLETE` rather than silently going healthy;
- no durable Slack queue/cursor database is introduced.

## Exact next action

1. Let hosted checks run on this amended records head.
2. If green, merge PR #91 as **architecture acceptance only**.
3. Create exactly one PR-A implementation issue under `MAS-48` using this R2 contract as precedence.
4. Do **not** commission PR-B or PR-C concurrently.
5. Sol adversarially reviews PR-A against the original product outcome before any real Slack SDK/runtime is introduced.
