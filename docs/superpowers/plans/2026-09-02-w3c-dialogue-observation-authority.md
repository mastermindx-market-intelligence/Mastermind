---
schema: mastermind.w3c_dialogue_observation_authority_plan.v1
operation: w3c-p0-dialogue-observation-authority-20260902-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# W3C-P0 Dialogue Observation Authority Plan

## Mission

Freeze the smallest non-duplicative path from validated Agent Dialogue history to current Executive
observation authority. The result must let the existing W3C runtime distinguish an active current
worker from a terminal RESULT projection without trusting caller callbacks, Slack prose, or provider
state.

## Precedence

1. Protected Mastermind source and same-SHA Sol Skillpack.
2. This design and its normative contract.
3. Existing protected Executive Runtime, Agent Dialogue, RuntimeBinding, Wake, WP-3, and AD-DLG2
   owners.
4. Protected ORION R2 and RET2 contracts when they exist.
5. PR #357 only as a partial consumer; it grants no authority to fill missing sources.

## Non-goals

- no new lifecycle, Job/Attempt/Worker/Event owner;
- no new RuntimeBinding or SessionTarget registry;
- no broad Relay access to the Executive control socket;
- no direct Relay access to Executive SQLite;
- no second Agent Relay daemon, Wake ledger, cursor, inbox, queue, retry, or provider process;
- no target arming, listener install, credential, host action, or canary in P0;
- no terminal observation before RET2 projection evidence exists.

## Dependency gates

### Gate A - R2 active binding source

The existing ORION R2 carrier must protect its admission-owned commission/dialogue provenance and
candidate-keyed Runtime resolver. Until then `ACTIVE_CURRENT_WORKER` remains held. Do not create a
parallel parent-binding event in W3C.

### Gate B - RET1 and RET2

RET1 must be protected before RET2. RET2 must protect one immutable parent/message/result projection
receipt with known effect. Until then `TERMINAL_RESULT` remains held.

### Gate C - dedicated listener

The Executive service must expose one exact operation on a dedicated read-only AF_UNIX listener,
restricted to the Agent Relay UID. General control and CeoIngress are not substitutes.

### Gate D - Relay hot waiter

The existing Relay process must own an exact ephemeral waiter registry around `wait_for_reply`.
Missing waiter evidence is a fail-closed W3C hold, not `False`.

## Wave P1 - Executive active observation

**Observable capability:** for one validated parent lookup, the Executive service returns one exact
active-current-worker observation or a typed zero-effect refusal/unknown.

**Preferred bounded surface:**

- create `control_plane/executive_dialogue_observation.py`;
- modify `control_plane/executive_service.py` only for the dedicated listener composition;
- modify `scripts/executive_os_phase1c.py` and `ops/executive_os/control.json.template` only for a
  strict default-disabled all-or-none configuration quartet if current source requires them;
- focused tests in existing service/runtime test owners.

**Required method:** deterministic only. Reuse protected R2 binding/resolver and Runtime read owners.
No model output, timestamps, titles, account labels, or caller-selected identities.

**Acceptance:**

- exact parent binding -> active observation;
- stale/missing parent binding -> HELD;
- inactive Attempt or non-BUSY Worker -> UNAVAILABLE, never terminal;
- moved/ambiguous RuntimeBinding -> UNKNOWN/CONFLICT;
- caller-injected Job/Attempt/Worker/mode fields refused;
- response contains no native handle/account/provider/credential/path;
- listener permits only UID 457 and one operation;
- zero Runtime/AgentOS/Slack/Wake/provider write;
- listener default disabled and no broad control access.

**Stop:** source-only, default-disabled, no install/canary.

## Wave P2 - Relay waiter and async discovery

**Observable capability:** the existing Agent Relay process discovers bounded V2 parents, resolves
observation authority asynchronously, and feeds only resolved active candidates to the existing
observer while continuing to serve V1/V2 AF_UNIX calls.

**Preferred bounded surface:**

- create one dedicated observation client under `integrations/slack_agent_dialogue/`;
- modify existing `engine_v2.py`, `service.py`, and `runtime.py` only as required;
- modify PR #357's routing/runtime tests rather than creating a second W3C runtime owner.

**Ordered implementation:**

1. RED for blocking synchronous callback freezing the service.
2. Replace arbitrary iterable callback with `async -> immutable tuple`.
3. Bound history parents, request time, response size, cardinality, and in-flight collection count.
4. Cancel and await one timed-out collection; never offload to an unkillable thread.
5. Register waiter before the first `wait_for_reply` poll and remove it in `finally`.
6. Change active-waiter lookup to parent fingerprint + operation/session + target seat.
7. Compose the client in the real Agent Relay entrypoint only when explicit default-disabled config
   is complete.
8. Prove malformed/timeout/overflow candidate input cannot stop the service or produce Wake.

**Acceptance:**

- service remains responsive while observation collection blocks/fails;
- maximum one in-flight collection;
- no synchronous iterable or worker thread;
- exact active waiter suppresses cold Wake;
- missing/failed waiter lookup produces zero persistence/provider effect;
- restart has no waiter but Wake ledger prevents duplicate sends;
- no second service, cursor, queue, or provider writer.

**Stop:** built-not-proven/default-disarmed; no live target.

## Wave RET2 - terminal RESULT projection

**Observable capability:** one exact terminal Runtime candidate produces one Relay-owned immutable
RESULT frame and one effect-known projection receipt, with complete reread and no blind resend.

**Owner boundary:** continue the existing ORION return/dialogue carrier architecture. Do not put
Slack posting into Executive Runtime and do not add an outbox. Persist projection attempt/effect in
the existing Event plane owned by the current R2 architecture.

**Required receipt fields:** parent fingerprint, operation/session, root/job/attempt/worker,
message key/fingerprint, terminal/result digests, projection receipt digest, and effect state.
Raw message body and provider/private identity are excluded.

**Acceptance:**

- exactly one RESULT for one terminal candidate;
- exact duplicate is idempotent;
- changed message/parent/terminal identity conflicts;
- pre-submit refusal may retry only under existing bounded law;
- post-submit uncertainty is effect-unknown and never resent/fails over;
- restart reconciles complete Slack history before any action;
- Slack outage leaves terminal truth intact and projection pending/unknown;
- no Wake acknowledgement/source resolution invented.

## Wave P3 - terminal observation extension

Extend the same P1 resolver and listener. A terminal response is valid only for an exact RET2
`APPLIED` or `RECOVERED` receipt. `ATTEMPTED`/`EFFECT_UNKNOWN`/missing/conflicting projection remains
UNKNOWN/HELD with zero candidate.

The active and terminal reducers must be separate closed branches. Tests must mutate a BUSY active
worker into a terminal result and a completed terminal result into an active worker; both refuse.

## Wave P4 - one-target canary

**Prerequisites:** P1/P2/RET2/P3 protected, Agent Relay host healthy, one exact current Codex writer,
Wake target default-off except the disposable route, ACK1 protected and production gates explicit.

**Journey:**

`validated parent -> observation authority -> exact Slack leaf -> deterministic attention -> active
waiter check -> one persisted Wake -> current writer -> one provider turn -> exact ACK -> source
resolution`

**Adverse proof:** restart/reobserve, Slack outage, listener outage, stale/moved binding, active waiter,
request-only crash, post-submit uncertainty, wrong ACK generation/turn, malformed/forked dialogue,
secret leakage, and target-unbound.

**Hard zeros:** duplicate RESULT, Wake, provider turn, RuntimeBinding, Worker, Attempt, lifecycle,
failover, Chairman message shuttle, title/account/time routing.

## Current disposition

- P0 records: authorized by current Chairman continuation.
- P1/P2/P3/P4: not authorized by P0.
- RET2: separate fresh operation after RET1 protection.
- PR #357: remains DRAFT/HOLD until P0 predecessors and implementation gates close.
- Capability after P0 merge: `SPEC_ONLY / PRODUCTION_INERT`.
