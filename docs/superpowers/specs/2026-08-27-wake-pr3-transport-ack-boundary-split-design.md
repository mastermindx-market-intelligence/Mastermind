# Wake PR3 Transport / ACK Boundary Split

## Status

Chairman-approved architectural ruling for Mastermind PR #174 on 2026-08-27.

This spec freezes Option A: **Wake PR3 remains the provider-native delivery-transport wave. Target acknowledgement ingress is a separate later bounded wave.**

This written spec must be reviewed before implementation planning under the Superpowers architectural workflow. It does not itself arm production, enable any target, add an ACK ingress, or create a new lifecycle/state plane.

## Context

Executive Wake already separates these facts:

```text
WAKE obligation
-> exact route / RuntimeBinding
-> DeliveryAttempt / NudgeAttempt
-> transport ACCEPTED or DELIVERED
-> TARGET_ACKNOWLEDGED
-> SOURCE_RESOLVED
```

The existing Wake ledger contains acknowledgement validation and persistence primitives, including trusted acknowledgement context and Executive-events-backed records. However, current accepted source law does **not** expose a production reasoning-session ingress by which the exact woken target session can originate a bounded ACK claim while trusted host/runtime identity is supplied and verified.

PR #174's original completion text required a live canary through `TARGET_ACKNOWLEDGED -> SOURCE_RESOLVED`. That requirement is not presently satisfiable without either inventing a new ingress or incorrectly treating delivery as acknowledgement.

The constitutional distinction remains:

```text
ACCEPTED != DELIVERED != TARGET_ACKNOWLEDGED != SOURCE_RESOLVED
```

A dispatcher, App Server response, Claude supervisor receipt, Slack message, synthetic test harness, or provider prompt must never author or imply `TARGET_ACKNOWLEDGED` merely because delivery occurred.

## Decision

### 1. PR #174 is transport-only

PR #174 owns provider-native Wake delivery and transport correctness only.

For Codex App Server it may prove:

- the exact current `RuntimeBinding.native_handle` is resumed rather than replaced;
- no `thread/start` or `thread/fork` creates a substitute conversation when an exact native handle is required;
- one bounded opaque Wake nudge is submitted to that exact resumed thread;
- provider/session/process evidence may change while the canonical Wake obligation and executive seat remain unchanged;
- timeout/effect uncertainty stays bound to the same destination and operation; no second turn, new thread, or provider failover is attempted blindly;
- transport `ACCEPTED` and `DELIVERED` remain distinct from target acknowledgement;
- no Executive Job/Attempt/Worker lifecycle ownership is moved into the Wake provider integration.

For Claude/Fable, PR #174 may mark `claude-code-session` implemented only after real installed-version, secret-free host proof establishes all three independently:

1. exact background-session discovery and binding;
2. same-conversation resurrection without minting a new conversation;
3. one scriptable bounded same-conversation nudge ingress.

If any of those is unproven, Claude remains `UNIMPLEMENTED/UNSUPPORTED`. Wake PR3 must not invent a Claude session manager, tmux lifecycle, GUI fallback, hidden socket protocol, or second session registry.

### 2. PR #174 live proof may end at `DELIVERED_UNACKNOWLEDGED`

The harmless Codex canary for PR #174 may truthfully end at:

```text
WAKE obligation
-> exact route / RuntimeBinding
-> bounded native transport attempt
-> exact provider delivery evidence
-> DELIVERED_UNACKNOWLEDGED
```

That canary proves the delivery edge only. It does not prove target consumption, source resolution, production-armed Wake, or complete autonomous continuation.

A transport sub-capability may therefore have genuine live delivery evidence while the overall Wake product remains nonterminal.

### 3. PR #174 remains production-disarmed

Throughout PR #174 implementation and merge:

- `production_armed=false` remains the global kill switch;
- checked-in targets remain disabled;
- `claude-code-session` remains unimplemented unless its host preflight actually passes;
- no production Wake source is resolved from synthetic acknowledgement;
- no runtime/provider credential, host registration, Slack lifecycle, scheduler, retry queue, or session database is added.

PR #174 may merge only after its current transport completion law is met: bounded changed surface, hosted CI/security checks, independent adversarial review, truthful Claude preflight verdict, and the required harmless Codex delivery canary when environment/permissions permit it.

The merge/capability state must not be inflated. Until the later ACK-ingress and arming proof exists, the overall Wake capability remains `BUILT_NOT_PROVEN` / `PARTIAL` rather than production-complete end-to-end Wake.

## Separate ACK-ingress wave

Target acknowledgement becomes a separately approved bounded architecture and implementation wave. It must **reuse** the existing Wake acknowledgement law and Executive `events` persistence rather than introducing another queue, ledger, lifecycle store, retry system, or truth database.

### Canonical responsibility split

```text
provider transport
  -> proves bounded delivery to exact runtime-bound target

target reasoning session
  -> originates only a bounded ACK claim for the opaque Wake obligation it consumed

trusted host/gateway boundary
  -> supplies and verifies current RuntimeBinding / seat / reasoning-surface / generation context
  -> refuses forged, stale, ambiguous or mismatched claims

existing Wake acknowledgement law
  -> validates canonical obligation-level ACK semantics

existing Executive events
  -> persists TARGET_ACKNOWLEDGED

existing Wake source-resolution path
  -> may resolve only after valid acknowledgement law is satisfied
```

The target/model may never author trusted fields such as seat, binding generation, reasoning surface, delivery proof, authority, source resolution, or host identity. Those values must come from accepted host/runtime context.

### ACK-ingress identity law

A valid ACK must bind the consumed Wake obligation to the **exact current reasoning-session identity** without making route-attempt identity authoritative over the obligation itself.

At minimum, the future ingress must fail closed on:

- wrong or missing RuntimeBinding;
- wrong provider session/native conversation;
- stale binding generation;
- wrong executive seat;
- wrong reasoning surface;
- obligation that was never validly claimed/routed/delivered to that target;
- model-authored or caller-authored trusted identity fields;
- delivery evidence without target consumption;
- duplicate ACK under the same stable operation identity with changed semantic payload;
- ambiguous/effect-unknown ACK writes followed by a blind retry;
- an ACK attempt that would require a new provider conversation, new lifecycle state, or transport failover.

A valid duplicate with identical canonical payload must reconcile to the same logical acknowledgement rather than create another lifecycle fact.

### Effect-unknown law

ACK submission is a modifying operation. If the client loses the response after submission may have begun:

```text
EFFECT_UNKNOWN
-> preserve the same ACK operation identity and carrier
-> query/reconcile the canonical Executive/Wake status
-> never blind-resubmit or fail over to another ingress
```

## Supersession

This ruling supersedes **only** the PR #174 completion clause that required the transport wave itself to prove:

```text
TARGET_ACKNOWLEDGED -> SOURCE_RESOLVED
```

All other accepted Wake architecture remains controlling, including:

- Executive OS owns canonical lifecycle and events;
- Wake is a notification/continuation layer, not a second lifecycle;
- `ACCEPTED != DELIVERED != ACK != SOURCE_RESOLVED`;
- `RuntimeBinding` is runtime/session evidence, not executive identity;
- no new Wake queue, scheduler, session DB, retry ledger, provider control plane, or Slack lifecycle authority;
- effect uncertainty remains bound to the same destination/operation;
- production arming and checked-in target enabling are independent gates from implementation merge.

The overall Autonomy V1 outcome is unchanged: a sleeping exact executive/reasoning session must eventually receive a bounded wake, recover canonical company state, acknowledge consumption through a trusted existing-law ingress, and allow source resolution without duplicating control planes.

## Capability ledger after this split

The intended truth vocabulary is:

- Codex-Sol identity/authority conformance (#173): accepted/merged conformance; no production Wake claim.
- Codex native Wake transport (#174): implementation/live-delivery proof as earned, but overall Wake remains `BUILT_NOT_PROVEN` / `PARTIAL` while disarmed and unacknowledged.
- Claude native Wake transport (#174): `BUILT_NOT_PROVEN` only if all installed-host preflight sub-capabilities pass; otherwise `NOT_BUILT` / `UNSUPPORTED` for the missing sub-capability.
- target reasoning-session ACK ingress: `NOT_BUILT` until the separate bounded wave is designed, reviewed, implemented and proven.
- Wake end-to-end `obligation -> delivery -> ACK -> source resolution`: `NOT_BUILT` / `PARTIAL` until the ACK-ingress wave and later production arming proof close the chain.

## Acceptance boundaries

### PR #174 transport acceptance

PR #174 may be accepted when all of the following are true on the exact accepted head:

- provider-native dispatcher composition remains fail-closed and transport-identity-bound;
- Codex App Server delivery preserves exact native thread identity and the no-fork/no-new-thread law;
- timeout/effect uncertainty cannot produce a second nudge or hidden failover;
- production kill switch and target-disabled state remain intact;
- Claude receives a truthful supported/unsupported preflight verdict with no guessed transport;
- hosted CI/security checks are green;
- independent adversarial review is clean;
- harmless Codex canary proves exactly the delivery claim being accepted, and no stronger claim.

### Future ACK-ingress acceptance

The separate ACK-ingress wave must not be called complete until:

- its architecture is reviewed before implementation;
- all identity/replay/forgery/effect-unknown falsifiers are mechanically discriminated;
- it reuses existing acknowledgement and Executive-events persistence rather than creating a new truth plane;
- a real target reasoning session originates the bounded ACK claim after consuming a real delivered Wake;
- trusted host/runtime context proves exact target identity;
- the resulting canonical `TARGET_ACKNOWLEDGED` record is persisted once;
- only then does existing source-resolution law close the originating Wake source;
- no transport success is laundered into acknowledgement.

## Implementation sequence after written-spec review

After the Chairman reviews this written spec:

1. create a bounded implementation plan that amends PR #174 source-law/completion text to the transport-only boundary without widening provider code;
2. finish/review/prove PR #174 against the transport-only acceptance law;
3. keep production disarmed and merge only at the truthful capability level;
4. separately design/plan the ACK-ingress wave against the existing Wake acknowledgement and Executive-events path;
5. implement and prove that ingress in its own bounded carrier;
6. only after valid target ACK and source-resolution proof consider the later production-arming acceptance wave.

No step may collapse delivery, acknowledgement, source resolution, and arming into one synthetic receipt.