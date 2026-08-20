# Executive OS Pro Sol Slack ingress — post-freeze reconciliation

**Date:** 2026-08-20  
**Parent architecture:** `research/EXECUTIVE_OS_PRO_SOL_SLACK_INGRESS_ARCHITECTURE_2026-08-20.md`  
**Linear:** `MAS-48`  
**Status:** records-only current-master reconciliation; no runtime authority is added here.

## Verdict

**KEEP THE MAS-48 ARCHITECTURE FREEZE. PR-A REMAINS THE ONLY NEXT IMPLEMENTATION COMMISSION.**

The architecture was originally pinned at Mastermind `18eb956a7dac0edca6870a39887a964b66c53d72`. Current `master` now includes provider-readiness hardening #92 and the inert Operator Harness / Codex adapter #93. Neither supersedes the Pro-Sol Slack ingress architecture. Current control-service archaeology makes PR-A's command-scoped local authorization requirement *more*, not less, important.

Macro #6071 has also since merged the cross-repository operating law: Slack is transport/acknowledgement, Executive OS owns lifecycle state, Agent OS owns organizational knowledge/work identity, GitHub owns implementation evidence, and Linear is portfolio projection. The earlier reconciliation dependency in the architecture freeze is therefore satisfied.

## Current-master findings

### 1. Executive AF_UNIX authorization is still peer-wide

`control_plane/executive_service.py` authenticates the connecting AF_UNIX peer by UID before dispatch. Once a UID is allowed, the request enters the common `_dispatch_request(...)` command surface.

That surface currently includes high-impact commands such as raw `submit-ceo-intent`, `dispatch`, `cancel`, `requeue`, worker registration/disable, backup/retention operations, and other Executive control commands.

Therefore adding `_mastermind_slack` to `allowed_peer_uids` alone would create exactly the privilege widening the architecture rejected. The Slack principal must be authorized structurally for **one** high-level command only (`submit-ceo-request` or the finally reviewed equivalent), with every existing and future command default-denied.

The check must occur before any privileged handler is reached. Message/request fields cannot widen the peer's command allowance.

### 2. #92 provider identity readiness is orthogonal

PR #92 hardens provider identity/readiness semantics. It does not create a Slack transport, change CEO-intent admission, or introduce peer-specific command authorization. MAS-48 keeps the same boundary.

### 3. #93 Operator Harness is deliberately inert and separate

PR #93 adds an importable but unregistered Operator Harness/Codex adapter and supporting operator runtime. Its own architecture keeps Executive lifecycle identity authoritative and does not register the adapter as a production Executive worker merely because the code exists.

MAS-48 does not use or bypass that provider path. The Pro-Sol writeback canary ends at one canonical QUEUED Executive Job + ACK + readback. `CODEX_EXECUTION_REQUIRED=false` remains part of the proof packet.

This separation is intentional: cognition/CEO communication must not depend on resolving the current Codex workspace/credential entitlement blocker.

### 4. No duplicate Slack state plane is permitted

Macro #6071 is now canonical and agrees with this freeze. MAS-48 must feed the existing Executive CEO-intent/Job/Event lifecycle. It may preserve bounded Slack transport provenance in the existing canonical receipt if compatibility permits; it may not add a Slack queue, Slack lifecycle table, durable seat-inbox database, second scheduler, direct Agent OS write path, or Linear completion authority.

### 5. Wake remains excluded

Nothing in #92 or #93 changes the standing Wake `NOT_ACCEPTED / NOT_ARMED` hold for MAS-48. PR-A/B/C must not import, invoke, arm, or use Wake as delivery proof.

## PR-A authority boundary — unchanged

PR-A is the only next build commission and must deliver one independently useful hermetic capability:

> A fixture/local Slack-like principal submits one **high-level** CEO request through AF_UNIX; trusted Executive code derives the canonical CEO-intent envelope and commits/reconciles exactly one existing Executive Job; the caller can read the resulting identifiers/receipt; and that same principal is structurally denied raw `submit-ceo-intent` and every other Executive command.

PR-A may include:

- one transport-neutral CEO-request normalization/derivation module under `control_plane/`;
- compatible reuse/refactor of current Executive MCP request law;
- one high-level local `submit-ceo-request` command;
- command-scoped peer authorization with future-command default deny;
- optional bounded Slack transport provenance carried through existing canonical `JOB_CREATED` provenance if backward compatibility is proven;
- hermetic tests and readback.

PR-A must not include:

- Slack SDK, Socket Mode, network access or Slack credentials;
- installer/launchd/principal provisioning;
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
5. Slack-like UID can invoke only `submit-ceo-request`;
6. the same UID is denied raw `submit-ceo-intent`, dispatch, cancel, requeue, worker, backup, retention and every other enumerated current command;
7. a newly registered future command is denied to the Slack-like UID by default;
8. MCP schema snapshot, accepted/refused behavior and MCP-specific intent IDs remain unchanged;
9. transport provenance does not affect canonical intent fingerprint;
10. no new Executive table/database/store exists;
11. no Wake import/call occurs;
12. result says queued/accepted only — never running/completed.

## Exact next action

Merge this records freeze only after current-master review/CI is clean. Then open exactly one PR-A implementation issue under `MAS-48`. Do **not** commission PR-B or PR-C concurrently. Sol reviews PR-A adversarially against the original product outcome before any real Slack SDK/runtime is introduced.
