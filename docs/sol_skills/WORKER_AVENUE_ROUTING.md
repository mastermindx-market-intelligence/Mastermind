---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: worker_avenue_routing
---

# WORKER AVENUE ROUTING — Recommend Capability Without Recreating the Chairman as Dispatcher

Use this skill for every Chairman-mediated/manual Slack handoff or worker-routing recommendation.
It is a narrow routing law for **who chooses the execution avenue, how unbound work is represented,
and when a concrete quota-bearing account/session is actually assigned**.

For manual/Slack preference labels and account binding, this skill is more specific than generic
worker/model examples in `COMMISSION_WAVE.md` and
`docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md`. It does not replace Executive OS lifecycle,
claim, provider-attestation, quota, carrier, watcher or authority law.

## 1. Core ownership split

**CEO Sol chooses the preferred execution avenue. Routine concrete placement is not Chairman labor.**

For ordinary `CAPACITY_SELECTABLE` work:

- when an accepted automated Capacity/Operator-Continuity placement path is live, that existing owner
  selects an eligible concrete receiver;
- when automated placement is not yet live or cannot currently place a receiver, the operation is
  `WAITING_CAPACITY / needs_placement` in the existing organizational/Control-Room/Linear projection;
- Sol must **not** turn that placement debt into a worker-facing `PRECOMMISSION`, `OPEN_PICKUP`, or
  `ACCOUNT_BINDING: CHAIRMAN_SELECTS` merely to keep work moving;
- Sol must **not** ask the Chairman to choose a numbered Claude/Codex account/session as routine
  operating work;
- no receiver-specific worker reasoning watcher is armed while no receiver exists.

`ACCOUNT_BINDING: CHAIRMAN_SELECTS` remains an **explicit manual exception only**. Use it only when
the current live Chairman directive deliberately opts into manually choosing the concrete
quota-bearing account/session for that specific operation, or explicitly names the receiver. Lack of
automated placement, historical habit, apparent Slack availability, account numbering, remembered
quota state, model preference or convenience does not make the Chairman the allocator.

`PRECOMMISSION` is not a canonical worker lifecycle state or required ceremony.

### 1.1 Chat web reasoning-mode barrier for every manual handoff turn

Every Chairman-mediated/manual Slack handoff turn defaults to the included web surface and non-Pro
reasoning, including the turn that drafts, sends, acknowledges, continues, stops, monitors, or
reports on the handoff:

```text
EXECUTION_SURFACE: WEB
COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT
CHAT_REASONING_MODE: NON_PRO_DEFAULT
```

Personal-Pro subscription/account, the Chat web surface, and turn-billed Pro reasoning mode are
separate. The legacy `CHAT_PRO_DEFAULT` is surface-only in historical packets; it is deprecated and
ambiguous and grants no Pro-mode authorization.

The following work is never Pro-eligible: `handoff / ACK / PICKUP_ACK / START / CONTINUE / STOP`;
`status / routing / placement / watcher / monitoring / polling / foregrounding`; message relay;
`mechanical edits / tests / simple review`; and any other short bounded work. The size or importance
of the parent program does not upgrade one of those turns.

Only a genuinely long-horizon frontier-reasoning turn may request Pro mode, and only with the
complete receipt:

```text
COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT
CHAT_REASONING_MODE: PRO_MODE_EXCEPTION
WHY_PRO_MODE: <specific frontier-reasoning advantage required by this turn>
WHY_NON_PRO_INSUFFICIENT: <specific evidence that non-Pro reasoning cannot reliably meet the bar>
PRO_MODE_TASK_CLASS: <one allowed class below>
EXPECTED_DURATION_MINUTES: <integer between 80 and 1440 minutes, inclusive>
STOP_CONDITION: <observable completion or abort condition>
```

The closed task classes are:

```text
LONG_HORIZON_FRONTIER_REASONING
CROSS_SYSTEM_ARCHITECTURE
HARD_DEBUGGING
ADVERSARIAL_JUDGMENT
```

Every field is required. `EXPECTED_DURATION_MINUTES` must be an integer between 80 and 1440 minutes,
inclusive, and therefore at least 80 minutes. Missing, stale, under-duration, over-duration, or
ineligible receipts fail closed:

```text
PRO_MODE_REFUSED / USE_NON_PRO_MODE
```

This is a reasoning-mode gate only. It does not change avenue selection, placement, receiver
binding, carrier, `ACK`, `START`, watcher, lifecycle, authority, or effect law. Pro mode is separate
from `METERED_EXCEPTION`; neither receipt implies or satisfies the other.

## 2. Closed preferred-avenue vocabulary for manual Slack handoffs

When Sol recommends a manual/Slack execution lane, state exactly one of:

```text
PREFERRED_AVENUE: Fable
PREFERRED_AVENUE: Opus
PREFERRED_AVENUE: Grok
PREFERRED_AVENUE: CTO Sol
PREFERRED_AVENUE: Terra
```

These are **avenue labels**, not account IDs and not claims that an Executive-runtime alias is armed.
Do not put `claude4`, `claude8`, `codex2`, another numbered account, or a session/login handle in
`PREFERRED_AVENUE`.

For Chairman-mediated Slack handoffs, this closed avenue vocabulary replaces generic top-level
preferences such as `Sonnet`, `Luna`, `Cursor`, `Codex`, or a raw provider/account name. Those may
still exist as lower-level models, execution surfaces or automated Executive routing choices where
current canonical law allows them; they are not the Chairman-facing routing recommendation.

## 3. Avenue selection policy

### Terra — default bounded engineering/research avenue

Prefer **Terra** for ordinary well-specified repository implementation, bounded refactors, debugging,
research and independent review when it can meet the quality bar.

### CTO Sol — strong Codex-backed specialist avenue

Prefer **CTO Sol** for difficult, reasoning-heavy but still bounded engineering, architecture-sensitive
implementation after CEO architecture freeze, hard debugging/refactors and demanding technical review.

`CTO Sol` is an execution/model avenue. It is **not** the active CEO Sol session and receives no CEO,
merge, release, acceptance or organizational authority merely from the name.

### Grok — alternate frontier avenue

Use **Grok** when provider/model diversity or its available execution environment materially improves a
bounded mission. The label does not assert that the disabled/unproven Executive `xai` provider alias is
production-armed; runtime capability still requires current canonical proof.

### Opus — premium bounded Claude specialist

Use **Opus** for difficult bounded work where Claude's deeper specialist reasoning or workflow surface
is materially useful. Do not spend Opus merely because a numbered Claude account appears free.

### Fable — hardest principal-level avenue only

Reserve **Fable** for the hardest missions: materially high ambiguity, sustained cross-repository
continuity, architecture/authority-sensitive integration, stalled-program recovery or another
principal-level problem where bounded specialist avenues are insufficient.

All existing `WHY FABLE` admission law remains binding.

## 4. Codex-capacity preference

Standing Chairman routing policy is to make active use of the Codex-backed **Terra** and **CTO Sol**
avenues rather than unnecessarily consuming scarcer Claude/Fable capacity.

Therefore, when multiple avenues can reliably satisfy the same bounded mission:

1. prefer **Terra** for standard work;
2. escalate to **CTO Sol** for harder bounded work;
3. use **Grok** or **Opus** when their distinct capability/surface materially improves the mission;
4. use **Fable** only when the principal-level admission test is actually met.

This is a standing scarcity preference, **not a claim about any live token balance**. Live usage,
limits and concrete receiver availability are current Capacity/runtime facts where those owners are
live; otherwise absence of placement is represented truthfully as `WAITING_CAPACITY`, not silently
converted into Chairman work.

## 5. Unbound work and the explicit manual-allocation exception

### 5.1 Default ordinary case — no receiver yet

For ordinary `CAPACITY_SELECTABLE` work with no exact receiver, record:

```text
PREFERRED_AVENUE: <Fable|Opus|Grok|CTO Sol|Terra>
WHY: <why this avenue can reliably satisfy the bounded mission>
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

For non-Fable routes also record `WHY NOT FABLE`; for Fable record `WHY FABLE`.

At this state:

- do not emit a worker-facing Slack commission merely to advertise the job;
- do not use `RECEIVER_MODE: OPEN_PICKUP` as a substitute for missing placement;
- do not tell a nonexistent worker it is `AWAITING_CHAIRMAN_ASSIGNMENT`;
- do not ask the Chairman to select a quota account/session;
- do not arm a receiver-specific watcher;
- preserve the intended operation/scope in the existing organizational/project surfaces until a
  lawful receiver exists.

### 5.2 Explicit Chairman manual-allocation exception

Only when the **current live Chairman explicitly opts into manual account/session allocation for this
exact operation** may Sol use the legacy manual receipt:

```text
PREFERRED_AVENUE: <Fable|Opus|Grok|CTO Sol|Terra>
WHY: <why this avenue can reliably satisfy the bounded mission>
ACCOUNT_BINDING: CHAIRMAN_SELECTS
RECEIVER_BINDING_MODE: <CAPACITY_SELECTABLE|EXACT_SESSION_REQUIRED>
RECEIVER_MODE: OPEN_PICKUP
```

For non-Fable routes also record `WHY NOT FABLE`; for Fable record `WHY FABLE`.

This is an exception, not the fallback when automatic placement is incomplete. A Slack packet created
under this explicit exception still does not let a worker self-claim merely from `PREFERRED_AVENUE`.
Preserve the same operation key/carrier when the explicit manual receiver is later selected; do not
create a second logical operation just because the binding arrived later.

### 5.3 Deliberate live delivery to a concrete session is assignment

When a concrete eligible session is deliberately given a bounded `CAPACITY_SELECTABLE` commission
through the current live Chairman interaction, an already-authorized Sol direct handoff, or the
canonical placement owner, **that delivery is the receiver-assignment edge**.

The receiving session must not demand:

- a second Chairman assignment;
- a separate Slack claim/comment;
- mutation of an earlier packet;
- another cross-channel identity echo solely to prove the current delivery was intentional.

It ACKs using its actual current identity, reads the required canonical sources/carrier, arms the
lawful continuation path, and emits the separate truthful `START` edge when all execution gates are
clear. A packet merely discovered in Slack/GitHub/history remains retrieved data and does not
self-assign a worker.

Receiver assignment is child-specific. A terminal STOP consumes that child assignment. A standing
program instruction does not self-assign a successor child; an independent successor requires a
fresh Sol/Chairman delivery or canonical placement edge plus the fresh operation/carrier/pickup law.
A worker must not mint a successor operation key and treat an older program-level Chairman sentence,
prior STOPped child, seat identity, or historical Slack thread as the receiver-assignment edge.

For a Slack direct-targeted child, preserve the exact parent thread chosen by the live delivery. The
worker ACK belongs under that parent; posting the ACK as a new top-level message in the same channel
does not create or move the carrier.

### 5.4 New-child origination and unconsumed delivery

A `DIRECT_TARGETED — NEW CHILD` reply buried under an unrelated parent/program/previous-child root
cannot by itself originate a new independent child or become that child's receiver-assignment event.
It may carry evidence or continue an already-ACKed child, but `CONTINUE`, `RULING`, and `STOP` remain
reciprocal continuation/terminal edges on the exact root of an already-ACKed child; they cannot become
sole assignment for a new child.

A new independent Slack-only child requires its own Sol-authored top-level child commission root, an
eligible command-create event, deliberate current live delivery into the actual provider interaction,
or a production-proven exact native wake/resume path that binds that child to an exact root. This
procedure preserves, rather than duplicates, Executive OS lifecycle and the accepted placement/router
owners.

DELIVERY_SENT or a Slack mention without a valid receiver PICKUP_ACK is DELIVERY_UNCONSUMED / PRE_START
and must not be projected as active, STARTED, executing, waiting-on-worker, or watcher-consumed.
PICKUP_ACK and START remain separate; Executive OS remains the lifecycle owner.

## 6. Receiver binding mode — capacity-selectable vs exact-session-required

Every bounded handoff must distinguish logical responsibility from the concrete runtime account by
declaring exactly one:

```text
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
RECEIVER_BINDING_MODE: EXACT_SESSION_REQUIRED
```

### 6.1 `CAPACITY_SELECTABLE` — default for new bounded work

Use `CAPACITY_SELECTABLE` when the mission can be performed by any eligible account/session in the
selected avenue and no existing provider-native conversation/session is part of the operation target.
This is the default for new bounded implementation, research, review and other work whose required
context is fully carried by the commission and canonical sources.

Before `START`, a lawful placement owner or a newer explicit current live Chairman/Sol assignment may
replace the concrete account/session while preserving the **same operation key and carrier**. This is
`PRESTART_REBIND`, not retry/failover:

```text
PRESTART_REBIND
precondition = no START / no modifying effect / no effect uncertainty
operation_key = unchanged
carrier = unchanged
logical responsibility = unchanged
concrete account/session = current lawfully assigned receiver
```

A numbered-account mismatch is not a blocker for `CAPACITY_SELECTABLE` work when all of the following
are true:

- the current session was deliberately assigned the same operation through a lawful current delivery;
- no prior receiver emitted `START` or otherwise began an operation effect;
- there is no `EFFECT_UNKNOWN` or conflicting active pickup;
- the current session is eligible for the selected avenue and required capability;
- the operation key, scope, carrier and logical responsibility are unchanged.

The receiving worker must ACK using its **actual** current communication/runtime identity. It must not
pretend to be a previously suggested numbered account. When useful for audit clarity, the ACK may
state `PRESTART_REBIND` and the actual receiver while keeping the same operation key.

If it is unknown whether a prior receiver started, fail closed and reconcile that same operation; do
not call the uncertainty a harmless pre-START rebind.

### 6.2 `EXACT_SESSION_REQUIRED` — strict continuation target

Use `EXACT_SESSION_REQUIRED` when the **exact provider conversation/session is part of the target**,
including provider-native continuation/resume, effect reconciliation, conversation-local state that
cannot be lawfully reconstructed elsewhere, or an acceptance proof that specifically requires that
bound account/session.

For `EXACT_SESSION_REQUIRED`, a different numbered account/session is a real target mismatch and must
block or reconcile under the owning continuity/RuntimeBinding law. Capacity preference does not
silently rewrite an exact-session target.

**Slack user/seat identity is not exact native-session identity.** A mention or delivery addressed to
an account/seat can be transport evidence without proving which provider-native reasoning session
consumed it. When an `EXACT_SESSION_REQUIRED` packet lands in any session other than the frozen native
session, **delivery to a different session is not PICKUP_ACK**. That landing must return
`RECEIVER_SESSION_MISMATCH` (or the current typed equivalent), identify the actual landing session when
safe, perform zero child effect, and **do not spawn or substitute another session**. Preserve the bound
session and any dirty/effectful local state for canonical continuity reconciliation; a shared Slack
identity, seat label, account nickname, or newly spawned same-model session cannot satisfy exactness.

**Slack mention alone is not an exact-session delivery mechanism.** Sol may issue asynchronous
`EXACT_SESSION_REQUIRED` delivery only when the exact provider conversation is already the current
live interaction or a **production-proven exact native wake/resume path** can address that verified
RuntimeBinding/native session. An account/seat mention, ordinary Slack notification, channel
membership, task title, or ability to spawn a fresh same-model session is insufficient. If no proven
exact-session path exists, represent the operation as `WAITING_EXACT_SESSION / wake_unavailable` and
**do not emit an account-targeted DIRECT_TARGETED packet** pretending the named native session will
consume it. Preserve any existing dirty/effectful owner and reconcile/materialize through the
canonical RuntimeBinding/Wake/session-provisioning owners instead.

Do not label ordinary new work `EXACT_SESSION_REQUIRED` merely because Sol happened to mention or tag a
numbered account in an earlier packet. Exactness comes from the operation's real target requirement,
not from accidental transport wording.

### 6.3 START freezes the concrete runtime for this operation

After `START`, the selected concrete runtime binding is sticky for the current operation unless the
accepted RuntimeBinding/Capacity/continuation owner explicitly reconciles and rebinds it.

A later quota or provider-limit event must return a truthful blocker such as `CAPACITY_EXHAUSTED` (or
the currently accepted equivalent) and enter canonical reconciliation. Do not manually paste the
same started operation into another Claude/Codex account and call it continuation. Do not turn
`CAPACITY_SELECTABLE` into permission for mid-effect account hopping.

`EFFECT_UNKNOWN` always blocks a receiver change until the original effect is reconciled.

## 7. Exact-receiver and live-target rules

If the current live Chairman directive explicitly names a concrete receiver/session for ordinary
capacity-selectable work, that live delivery is the current receiver binding. Before START it may be
superseded only by a newer lawful `PRESTART_REBIND` under Section 6.1.

An already-authorized Sol direct handoff or canonical placement owner may likewise bind an eligible
receiver when current law permits it. That receiver does not require a redundant Chairman assignment.

If the operation is `EXACT_SESSION_REQUIRED`, or the Chairman explicitly freezes the exact session as
part of the target, Sol must not substitute a different account based on its own quota guess.

Likewise, if the Chairman explicitly delegates concrete account-selection authority for one operation,
Sol may exercise only that bounded authority and must record the basis for the selection.

## 8. Automated Executive routing is separate

This law does not create a second router or quota ledger. When a production-proven Executive route
lawfully performs deterministic worker/quota claim, Executive OS remains the lifecycle and claim
authority and the accepted Capacity/provider owners select among registered eligible capacity.

Do not copy manual account-selection rules into a second router. Incomplete automated routing degrades
to visible `WAITING_CAPACITY`, not Chairman micromanagement.

## 9. Account-neutral enforcement and default principle

This law applies equally to every Sol/project seat and provider surface. No ChatGPT, Codex, Claude,
Fable, Grok or another surface is exempt because it historically emitted or expected
`PRECOMMISSION`, `OPEN_PICKUP`, or `CHAIRMAN_SELECTS` packets.

> **Sol recommends the capability avenue. Existing capacity/runtime owners choose routine placement.
> Unbound ordinary work is WAITING_CAPACITY, not Chairman work. Deliberate live delivery to a concrete
> eligible session is assignment. Exact-session continuation stays exact; after START, runtime changes
> require canonical reconciliation. Prefer Terra and CTO Sol when sufficient. Fable is for the hardest
> principal-level problems, not the default.**
