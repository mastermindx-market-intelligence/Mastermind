---
schema: mastermind.w3c_dialogue_observation_authority_plan.v1
operation: w3c-p0-dialogue-observation-authority-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# W3C-P0 Dialogue Observation Authority Plan

## Mission

Freeze the smallest non-duplicative path from validated Agent Dialogue history to current Executive observation authority. The result must let the existing W3C runtime distinguish an active current worker from a terminal RESULT projection without trusting caller callbacks, Slack prose, provider state or filesystem reachability assumptions.

## Precedence

1. Protected Mastermind source and same-SHA Sol Skillpack.
2. The W3C-P0 design and normative contract.
3. Existing protected Executive Runtime, Agent Dialogue, RuntimeBinding, Wake, WP-3 and AD-DLG2 owners.
4. The already-started ORION R2 terminal-to-Relay operation.
5. PR #357 only as a partial consumer; it grants no authority to fill missing sources.

## Non-goals

- No new lifecycle, Job/Attempt/Worker/Event owner.
- No new RuntimeBinding or SessionTarget registry.
- No broad Relay access to the Executive control socket.
- No direct Relay access to Executive SQLite.
- No second Agent Relay daemon, Wake ledger, cursor, inbox, queue, retry or provider process.
- No target arming, listener installation, credential, host action or canary in P0.
- No terminal observation before the existing ORION R2 projection receipt is protected.
- No parallel RET2 terminal-projection operation.

## Dependency gates

### Gate A - R2 active binding source

The existing ORION R2 carrier must protect its admission-owned commission/dialogue provenance and candidate-keyed Runtime resolver. Until then `ACTIVE_CURRENT_WORKER` remains held. Do not create a parallel parent-binding event in W3C.

### Gate B - RET1 and existing ORION R2 terminal projection

RET1 is protected. The already-started ORION R2 operation must protect one immutable parent/message/result projection receipt with known `APPLIED` effect. Until then `TERMINAL_RESULT` remains held. Do not mint a second terminal-projection carrier.

### Gate C - dedicated listener and host reachability

The Executive service must expose one exact operation on a dedicated read-only AF_UNIX listener restricted to the Agent Relay UID. General control and CeoIngress are not substitutes.

The listener uses its own runtime directory rather than the general Executive-control socket family. Current protected enrollment fixes `_mastermind_exec` at UID 450 and `_mastermind_agent_relay` at UID/GID 457, with `_mastermind_exec` admitted to the Relay group. The reviewed host shape is:

```text
parent: /var/run/mastermind-dialogue-observation owner=450 group=457 mode=0710
socket: /var/run/mastermind-dialogue-observation/dialogue-observation.sock owner=450 group=457 mode=0660
peer:   UID 457 only
```

Parent and final socket symlinks are forbidden. Startup may replace a stale socket only after proving it is the expected owned inode; a foreign or ambiguous inode yields `CAPABILITY_NOT_READY`. Shutdown removes only the inode created by the current process. This is reachability and integrity law, not a second service or permission registry.

### Gate D - Relay hot waiter

The existing Relay process must own an exact ephemeral waiter registry around `wait_for_reply`. Missing waiter evidence is a fail-closed W3C hold, not `False`.

## Wave P1 - Executive active observation

**Observable capability:** for one validated parent lookup, the Executive service returns one exact active-current-worker observation or a typed zero-effect refusal/unknown.

**Preferred bounded surface:**

- create `control_plane/executive_dialogue_observation.py`;
- modify `control_plane/executive_service.py` only for the dedicated listener composition;
- modify `scripts/executive_os_phase1c.py` and `ops/executive_os/control.json.template` only for a strict default-disabled all-or-none configuration if current source requires it;
- use existing Executive service/runtime test owners.

**Required method:** deterministic only. Reuse protected R2 binding/resolver and Runtime read owners. Reuse the existing peer-credentialled AF_UNIX service pattern; do not copy a weaker socket implementation. Model output, timestamps, titles, account labels and caller-selected identities have zero authority.

**Acceptance:**

- exact parent binding -> active observation;
- stale/missing parent binding -> `HELD`;
- inactive Attempt or non-BUSY Worker -> `UNAVAILABLE`, never terminal;
- moved/ambiguous RuntimeBinding -> `UNKNOWN`/`CONFLICT`;
- caller-injected Job/Attempt/Worker/mode fields refused;
- response contains no native handle, account, provider, credential or path;
- listener permits only UID 457 and `resolve_dialogue_observation`;
- dedicated parent/socket owner, group and modes are exact;
- parent/final symlinks and foreign stale inodes fail closed;
- the general Executive socket parent is not reused;
- listener configuration is default-disabled and all-or-none;
- zero Runtime, Agent OS, Slack, Wake or provider write.

**Stop:** source-only and default-disabled; no installation or canary.

## Wave P2 - Relay waiter and async discovery

**Observable capability:** the existing Agent Relay process discovers bounded V2 parents, resolves observation authority asynchronously, and feeds only resolved active candidates to the existing observer while continuing to serve V1/V2 AF_UNIX calls.

**Preferred bounded surface:**

- create one dedicated observation client under `integrations/slack_agent_dialogue/`;
- modify existing `engine_v2.py`, `service.py` and `runtime.py` only as required;
- repair PR #357's routing/runtime tests rather than creating a second W3C runtime owner.

**Ordered implementation:**

1. RED for a blocking synchronous source freezing the accepted service.
2. Replace arbitrary iterable callback with `async -> immutable tuple`.
3. Bound parent history, request time, response size, cardinality and in-flight collection count.
4. Cancel and await one timed-out collection; never offload to an unkillable thread.
5. Register the waiter before the first `wait_for_reply` poll and remove it in `finally`.
6. Key active-waiter lookup by parent fingerprint + operation/session + target seat.
7. Compose the client in the real Agent Relay entrypoint only when explicit default-disabled config is complete.
8. Prove malformed, timeout or overflow input cannot stop the service or produce Wake.

**Acceptance:** service remains responsive under collection failure; maximum one in-flight collection; no synchronous iterable or worker thread; exact hot waiter suppresses cold Wake; missing/failed waiter lookup produces zero persistence/provider effect; restart has no waiter but Wake identity remains the durable duplicate authority; no second service, cursor, queue or provider writer.

**Stop:** `BUILT_NOT_PROVEN / DEFAULT_DISARMED`; no live target.

## Existing ORION R2 - terminal RESULT projection

**Observable capability:** one exact terminal Runtime candidate produces one Relay-owned immutable RESULT frame and one effect-known projection receipt, with complete reread and no blind resend.

Continue `ad-ret1-terminal-return-transport-r2-20260830-orion-001` on its exact native task and preserved effect. Do not put Slack posting into Executive Runtime, add an outbox, or mint a parallel RET2 operation. Persist projection attempt/effect in the existing Event plane owned by the current R2 architecture.

The receipt binds parent fingerprint, operation/session, root/job/attempt/worker, message key/fingerprint, terminal/result digests, projection receipt digest and effect state. Raw body and provider/private identity are excluded.

Acceptance requires exactly one RESULT, exact duplicate idempotency, changed identity conflict, pre-submit-only bounded recovery, post-submit `EFFECT_UNKNOWN` with no resend/failover, complete history reconciliation after restart, recovery proving canonical `APPLIED` rather than inventing `RECOVERED`, terminal truth surviving Slack outage, and no Wake acknowledgement/source resolution invention.

## Wave P3 - terminal observation extension

Extend the same P1 resolver and listener. A terminal response is valid only for an exact ORION R2 `APPLIED` receipt. `ATTEMPTED`, `EFFECT_UNKNOWN`, missing or conflicting projection remains `UNKNOWN`/`HELD` with zero candidate. Active and terminal reducers remain separate closed branches.

## Wave P4 - one-target canary

Prerequisites: P1/P2/R2/P3 protected, Agent Relay healthy, one exact current writer, Wake target default-off except the disposable route, ACK1 protected and production gates explicit.

Journey:

```text
validated parent -> observation authority -> exact Slack leaf -> deterministic attention
-> exact hot-waiter check -> one persisted Wake -> current writer -> one provider turn
-> exact acknowledgement -> source resolution
```

Adverse proof covers restart/reobserve, Slack/listener outage, stale or moved binding, hot waiter, request-only crash, post-submit uncertainty, wrong acknowledgement generation/turn, malformed/forked dialogue, secret leakage and target-unbound. Hard zeros: duplicate RESULT, Wake, provider turn, RuntimeBinding, Worker, Attempt, lifecycle, failover, Chairman message shuttle and title/account/time routing.

## Current disposition

- P0 records: authorized by current Chairman continuation.
- P1/P2/P3/P4: not authorized by P0.
- Existing ORION R2: already STARTED on its preserved exact-session carrier; P0 creates no new child.
- PR #357: DRAFT/HOLD until P0 predecessors and implementation gates close.
- Capability after P0 merge: `SPEC_ONLY / PRODUCTION_INERT`.
