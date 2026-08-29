---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: worker_avenue_routing
---

# WORKER AVENUE ROUTING — Recommend Capability, Never Spend the Chairman's Account Quota

Use this skill for every Chairman-mediated/manual Slack handoff or worker-routing recommendation.
It is a narrow routing law for **who chooses the execution avenue versus who chooses the concrete
quota-bearing account/session**.

For manual/Slack preference labels and account binding, this skill is more specific than generic
worker/model examples in `COMMISSION_WAVE.md` and
`docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md`. It does not replace Executive OS lifecycle,
claim, provider-attestation, quota, carrier, watcher or authority law.

## 1. Core ownership split

**CEO Sol chooses the preferred execution avenue. The Chairman chooses the concrete account/session
when the Chairman is manually allocating workers by current usage, limits or availability.**

Unless the current live Chairman directive already names an exact receiver/account/session, Sol must
not bind, tag, address or otherwise allocate a quota-bearing account such as `claude4`, `claude8`, a
numbered Claude/Codex account, workspace seat, login, quota slot or session handle.

Do not infer a concrete account from:

- the account used on the previous wave;
- apparent Slack availability;
- remembered or cached quota state;
- account numbering;
- a worker's historical identity;
- a model preference;
- convenience.

The Chairman may know live account utilization that Sol does not. Account allocation therefore stays
Chairman-owned unless the Chairman explicitly delegates that allocation authority for the specific
operation.

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
current canonical law allows them; they are not the Chairman-facing account-allocation recommendation.

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
limits and which concrete account currently has capacity remain Chairman/runtime facts, not Skillpack
state.

## 5. Required manual handoff receipt

Before posting a Chairman-mediated/manual Slack handoff, record:

```text
PREFERRED_AVENUE: <Fable|Opus|Grok|CTO Sol|Terra>
WHY: <why this avenue can reliably satisfy the bounded mission>
ACCOUNT_BINDING: CHAIRMAN_SELECTS
RECEIVER_BINDING_MODE: <CAPACITY_SELECTABLE|EXACT_SESSION_REQUIRED>
```

For non-Fable routes also record:

```text
WHY NOT FABLE: <why principal capacity is unnecessary>
```

For Fable record instead:

```text
WHY FABLE: <specific principal-level ambiguity/continuity/architecture reason>
```

If the exact receiver has not yet been selected, the handoff is not a receiver assignment. Under the
existing `COMMISSION_WAVE.md` receiver vocabulary, use:

```text
RECEIVER_MODE: OPEN_PICKUP
```

and state plainly that **no worker may self-claim merely from `PREFERRED_AVENUE`**. The Chairman's later
same-carrier account/session assignment creates the receiver-binding edge; after that, the selected
worker performs the normal pickup ACK, watcher/readiness and START discipline.

Do not create a second handoff or second logical operation merely because the Chairman supplied the
account binding after the packet was posted. Preserve the same operation key and carrier unless current
reconciliation law requires otherwise.

## 6. Receiver binding mode — capacity-selectable vs exact-session-required

Every Chairman-mediated/manual handoff must distinguish the logical responsibility from the concrete
quota-bearing runtime account by declaring exactly one:

```text
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
RECEIVER_BINDING_MODE: EXACT_SESSION_REQUIRED
```

### 6.1 `CAPACITY_SELECTABLE` — default for new bounded work

Use `CAPACITY_SELECTABLE` when the mission can be performed by any eligible account/session in the
selected avenue and no existing provider-native conversation/session is part of the operation target.
This is the default for new bounded implementation, research, review and other work whose required
context is fully carried by the commission and canonical sources.

Before `START`, the Chairman may replace the concrete account/session while preserving the **same
operation key and carrier**. The **newest explicit live Chairman assignment** to the current session is
the receiver-binding edge for that unstarted operation.

This is `PRESTART_REBIND`, not retry/failover:

```text
PRESTART_REBIND
precondition = no START / no modifying effect / no effect uncertainty
operation_key = unchanged
carrier = unchanged
logical responsibility = unchanged
concrete account/session = Chairman-selected current receiver
```

A numbered-account mismatch is not a blocker for `CAPACITY_SELECTABLE` work when all of the following
are true:

- the current live Chairman deliberately delivered/assigned the same operation to this session;
- no prior receiver has emitted `START` or otherwise begun an operation effect;
- there is no `EFFECT_UNKNOWN` or conflicting active pickup;
- the current session is eligible for the selected avenue and required capability;
- the operation key, scope, carrier and logical responsibility are unchanged.

The receiving worker must ACK using its **actual** current communication/runtime identity. It must not
pretend to be the previously suggested numbered account. When useful for audit clarity, the ACK may
state `PRESTART_REBIND` and the actual receiver while keeping the same operation key.

If it is unknown whether the prior receiver started, fail closed and reconcile that same operation;
do not call the uncertainty a harmless pre-START rebind.

### 6.2 `EXACT_SESSION_REQUIRED` — strict continuation target

Use `EXACT_SESSION_REQUIRED` when the **exact provider conversation/session is part of the target**,
including provider-native continuation/resume, effect reconciliation, conversation-local state that
cannot be lawfully reconstructed elsewhere, or an acceptance proof that specifically requires that
bound account/session.

For `EXACT_SESSION_REQUIRED`, a different numbered account/session is a real target mismatch and must
block or reconcile under the owning continuity/RuntimeBinding law. Chairman preference for a fresher
quota account does not silently rewrite an exact-session target.

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

## 7. Exact-receiver exception

If the current live Chairman directive explicitly names a concrete receiver/session for ordinary
capacity-selectable work, that is the current account binding; the Chairman may still issue a newer
explicit `PRESTART_REBIND` before `START` under Section 6.1.

If the operation is `EXACT_SESSION_REQUIRED`, or the Chairman explicitly freezes the exact session as
part of the target, Sol must not substitute a different account based on its own quota guess.

Likewise, if the Chairman explicitly delegates concrete account-selection authority for one operation,
Sol may exercise only that bounded authority and must record the basis for the selection.

## 8. Automated Executive routing is separate

This law does not make the Chairman manually choose workers for Executive OS Jobs. When a
production-proven Executive route lawfully performs deterministic worker/quota claim, Executive OS
remains the lifecycle and claim authority and may select among registered capacity according to its
canonical policy.

Do not copy manual account-selection rules into a second router or quota ledger.

## 9. Default principle

> **Sol recommends the capability avenue; the Chairman spends the account quota. Ordinary new work is
> capacity-selectable before START; exact-session continuation stays exact; after START, runtime changes
> require canonical reconciliation. Prefer Terra and CTO Sol when sufficient.
> Fable is for the hardest principal-level problems, not the default.**
