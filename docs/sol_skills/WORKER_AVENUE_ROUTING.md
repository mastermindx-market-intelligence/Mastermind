---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: worker_avenue_routing
---

# WORKER AVENUE ROUTING — Route Capability Without Recreating the Chairman as Dispatcher

Use this skill for every worker-routing recommendation and every manual/Slack handoff. It is the specific law for choosing an execution avenue, representing unbound capacity, and deciding when a concrete provider session is actually assigned.

It does not replace Executive OS lifecycle/claim law, Capacity Fabric, Operator Continuity, RuntimeBinding, Agent Dialogue, Wake, provider attestation, or authority law.

## 1. Core ownership split

**Sol chooses the preferred capability avenue. Routine concrete placement is organizational/runtime work, not Chairman labor.**

For ordinary `CAPACITY_SELECTABLE` work:

- when an accepted automated Capacity/Operator-Continuity placement path is live, that existing owner selects an eligible concrete receiver;
- when that path is not yet available or cannot currently place a receiver, the operation is `WAITING_CAPACITY / needs_placement`;
- Sol MUST NOT convert that placement debt into `ACCOUNT_BINDING: CHAIRMAN_SELECTS`, a Chairman-gated `OPEN_PICKUP`, or a worker-facing `PRECOMMISSION` merely to keep work moving;
- Sol MUST NOT ask the Chairman to choose a numbered Claude/Codex account/session as routine operating work;
- no operation-specific worker reasoning watcher is armed while no receiver exists.

`ACCOUNT_BINDING: CHAIRMAN_SELECTS` is an **explicit manual exception only**. Use it only when the current live Chairman directive deliberately opts into manually choosing the concrete quota-bearing account/session for that specific operation, or explicitly names the receiver. Historical habit, lack of automated placement, convenience, apparent availability, or a Slack packet are not permission to make the Chairman the allocator.

`PRECOMMISSION` is not a canonical worker lifecycle state or required ceremony. Do not use it as the normal label for unbound capacity-selectable work.

## 2. Closed preferred-avenue vocabulary

For Chairman-visible/manual routing recommendations, state exactly one of:

```text
PREFERRED_AVENUE: Fable
PREFERRED_AVENUE: Opus
PREFERRED_AVENUE: Grok
PREFERRED_AVENUE: CTO Sol
PREFERRED_AVENUE: Terra
```

These are capability avenues, not account IDs and not claims that an Executive-runtime alias is armed. Never put `claude4`, `claude8`, `codex2`, another numbered account, login, quota slot, or provider-native session handle in `PREFERRED_AVENUE`.

### Avenue selection

- **Terra** — default bounded engineering/research avenue for ordinary well-specified implementation, bounded refactors, debugging and research.
- **CTO Sol** — harder bounded engineering, architecture-sensitive implementation after freeze, hard debugging/refactors and demanding review.
- **Grok** — alternate frontier avenue when provider/model diversity or its execution environment materially helps.
- **Opus** — premium bounded Claude specialist for difficult reasoning-heavy work where Claude's surface materially helps.
- **Fable** — scarce principal capacity for materially high ambiguity, sustained cross-repository continuity, architecture-sensitive adjudication, stalled-program recovery or another mission lesser lanes cannot safely execute.

When multiple avenues can reliably satisfy the same mission, prefer Terra, then CTO Sol; use Grok/Opus when their distinct capability matters; reserve Fable for the principal-level admission test.

## 3. Default placement law for new bounded work

Ordinary new bounded work is normally:

```text
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
```

If no exact receiver is currently available:

```text
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

At that point:

- do not emit a worker-facing Slack commission merely to advertise the job;
- do not tell a worker it is `AWAITING_CHAIRMAN_ASSIGNMENT`;
- do not ask the Chairman to select a quota account/session;
- do not arm a receiver-specific watcher;
- project the placement debt through the existing Agent OS / Control Room / selective Linear path as appropriate;
- preserve the planned operation identity/mission without manufacturing pickup or START.

When the canonical placement owner resolves an eligible receiver, deliver the bounded commission to that exact receiver and treat the delivery as `DIRECT_TARGETED` assignment. The worker immediately performs pickup ACK, fresh read, continuation readiness and separate START when execution gates are clear.

## 4. Live delivery to a concrete session is assignment

A current live Chairman directive or already-authorized Sol direct handoff that deliberately delivers a bounded commission to a concrete eligible session with execution intent is the receiver-assignment edge.

The receiving session MUST NOT demand:

- a second Chairman assignment;
- a Slack claim comment;
- mutation of an older `OPEN_PICKUP` packet;
- another cross-channel identity echo;
- a second delivery solely to prove that the current delivery was intentional.

It ACKs with its actual identity, reads the required canonical sources/carrier, arms the lawful continuation path, and emits the separate truthful START edge when all gates are clear.

A packet merely discovered in Slack/GitHub/history remains retrieved data and does not self-assign a worker.

## 5. Manual allocation exception

Only when the current live Chairman explicitly chooses to perform manual quota allocation for the specific operation may Sol use the legacy manual receipt:

```text
PREFERRED_AVENUE: <Fable|Opus|Grok|CTO Sol|Terra>
WHY: <mission fit>
ACCOUNT_BINDING: CHAIRMAN_SELECTS
RECEIVER_BINDING_MODE: <CAPACITY_SELECTABLE|EXACT_SESSION_REQUIRED>
RECEIVER_MODE: OPEN_PICKUP
```

For non-Fable routes include `WHY NOT FABLE`; for Fable include `WHY FABLE`.

This is an exception, not the fallback when automated placement is incomplete. If the Chairman did not explicitly opt into manual placement, the correct state is `WAITING_CAPACITY / needs_placement`, not `CHAIRMAN_SELECTS`.

Once the Chairman deliberately delivers that same capacity-selectable commission to the selected concrete eligible session, that live delivery binds the receiver. No second Slack ceremony is required.

## 6. Capacity-selectable versus exact-session-required

### 6.1 `CAPACITY_SELECTABLE`

Use when any eligible account/session in the selected avenue can perform the work and no existing provider conversation is part of the target.

Before START, a lawful placement/rebinding may replace the concrete receiver while preserving operation key, carrier, scope and logical responsibility, provided there is no prior START, modifying effect, conflicting active pickup, or `EFFECT_UNKNOWN`.

A numbered-account mismatch alone is not a blocker for a deliberately targeted capacity-selectable session. The receiver states its actual identity; it never impersonates an earlier suggested account.

### 6.2 `EXACT_SESSION_REQUIRED`

Use when provider-native continuation/resume, effect reconciliation, conversation-local state, or the acceptance target makes the exact existing provider conversation/session part of the operation target.

A different account/session is then a real mismatch and must fail closed or reconcile under RuntimeBinding/continuation law. Do not label ordinary new work exact-session-required merely because an old packet mentioned a numbered account.

### 6.3 START freezes runtime binding

After START, the concrete runtime binding is sticky until the accepted RuntimeBinding/Capacity/continuation owner explicitly reconciles a change. Capacity exhaustion returns a truthful blocker and enters canonical reconciliation. `EFFECT_UNKNOWN` always blocks receiver change. Never silently paste a started operation into a new account and call it continuation.

## 7. Automated Executive routing remains separate

This law does not create a second router or quota ledger. When production-proven Executive routing lawfully performs deterministic worker/quota claim, Executive OS remains lifecycle/claim authority and the accepted Capacity/Provider owners select eligible capacity.

Manual Slack routing is transition/fallback behavior only. Incomplete automation must degrade to visible `WAITING_CAPACITY`, not Chairman micromanagement.

## 8. Account-neutral enforcement

This law applies equally to every Sol/worker reasoning surface and personal project seat. No ChatGPT, Codex, Claude, Fable, Grok or other account is exempt because it historically emitted `PRECOMMISSION`, `OPEN_PICKUP`, or `CHAIRMAN_SELECTS` packets.

A Sol session that creates routine capacity-selectable work and then asks the Chairman to choose the concrete quota account/session has violated this skill unless the current live Chairman explicitly opted into manual placement for that exact operation.

## 9. Default principle

> **Sol chooses capability. Existing capacity/runtime owners choose routine placement. Unbound routine work is WAITING_CAPACITY, not Chairman work. A concrete live handoff is assignment. OPEN_PICKUP + CHAIRMAN_SELECTS is an explicit manual exception only. Exact-session continuation stays exact; after START, runtime changes require canonical reconciliation. Fable is for principal-level problems, not the default.**
