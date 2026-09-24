# Wake PR3 — Provider Effect-Unknown Reconciliation Amendment

**Date:** 2026-08-28  
**Owner:** Sol, AI CEO  
**Existing carrier:** Mastermind PR #174 / `sol/wake-pr3-native-transports-20260827`  
**Existing operation:** `wake-pr3-native-transports-20260827-sol-001`  
**Authority:** narrow behavioral amendment to the accepted Wake PR3 transport-only architecture. It governs provider-call effect uncertainty and same-attempt reconciliation only. It does not authorize target ACK/source resolution, production arming, provider failover, a new Wake store, or a second carrier.

## 1. Defect and safety outcome

Current Wake code can persist or reconstruct an unfinished `DELIVERY_ATTEMPT`, reuse its attempt number, and call the provider again. A lost `turn/start` response or completion timeout can therefore issue a second provider turn even though the first may have committed.

The required invariant is:

```text
one persisted Wake DeliveryAttempt / nudge identity
→ at most one provider-side start/submission effect
→ any uncertain effect remains same-attempt reconciliation-required
→ zero second turn, thread, destination, provider, host or session failover
```

A client timeout, disconnect, process restart or lost response is never a retry permission.

## 2. Existing authority remains

Durable Wake facts remain events in the existing Executive OS `events` table under the existing Wake aggregate. There is no Wake table, retry database, provider-turn registry, cursor, queue or daemon.

Existing identities remain:

- `WakeObligation` — obligation-global source/target identity;
- `DeliveryAttempt` / deterministic `attempt_command_id` — exact route-bound attempt;
- `NudgeAttempt` / deterministic `nudge_id` — coalesced external nudge identity;
- `RuntimeBinding` — exact current target/native handle;
- provider-native thread/session identity — runtime-only transport evidence;
- target ACK and source resolution — existing later Wake phases, not provider output.

## 3. Persist-before-provider law

No provider submission may occur until the exact `DELIVERY_ATTEMPT` record for every coalesced obligation is atomically persisted through `WakeLedgerRepository`.

Required sequence:

```text
read existing Wake aggregate
→ reconcile deterministic command-id replays
→ plan exact route/binding
→ create exact DeliveryAttempt/NudgeAttempt
→ atomically append DELIVERY_ATTEMPT event(s)
→ only then perform one provider call
→ authenticate provider observation
→ atomically append the corresponding terminal attempt event(s)
```

If persistence fails or is ambiguous before the provider call, no provider call is made. If the process dies after persistence but before/during/after provider submission, the durable unfinished attempt remains reconciliation-required.

The current all-in-one `dispatch_nudge()` helper may remain for pure/fixture use only if it cannot be mistaken for the production persisted path. Production composition must use a reviewed persist-before-provider coordinator over the existing repository and dispatcher contracts; do not create a new service lifecycle.

## 4. Effect-state vocabulary

### 4.1 Durable representation

No new terminal ledger phase is required for V1. The durable representation of effect uncertainty is:

```text
WAKE_REQUESTED
+ DELIVERY_ATTEMPT A<n>
+ no ACCEPTED / DELIVERED / FAILED / TARGET_UNAVAILABLE terminal for A<n>
```

That unfinished attempt is an exact fact: the provider effect is not safely known. It must project as `RECONCILIATION_REQUIRED` / `EFFECT_UNKNOWN`, not ordinary retryable pending work.

A later schema may add an explicit event only if the existing aggregate cannot support required correction/audit behavior; that requires a separate architecture review. Do not add a second store merely for a status label.

### 4.2 Public outcome

The nonterminal public/fabric result may use a closed `EFFECT_UNKNOWN` outcome/reason tied to the existing attempt and nudge identity. It:

- is not success;
- is not a terminal attempt phase;
- is not `FAILED`;
- is not `ACCEPTED` or `DELIVERED`;
- cannot authorize a new attempt;
- cannot authorize ACK/source resolution;
- survives process restart through reconstruction of the unfinished attempt.

If adding the public outcome would break an accepted closed wire, use a typed `WakeDispatchError`/reconciliation result that projects the same state and return to Sol before changing the wire version. Never map effect unknown to `FAILED` for convenience.

## 5. Provider boundary: pre-submit failure versus possible effect

A dispatcher/client must distinguish:

### Deterministic pre-submit refusal/failure

Examples:

- RuntimeBinding/native handle invalid before provider write;
- target thread proven absent;
- provider binary/service unavailable before request emission;
- local validation refuses the request.

These may produce existing `TARGET_UNAVAILABLE` or `FAILED` terminal evidence, provided the adapter can prove no provider submission began.

### Possible provider effect

Once request bytes for the exact provider start/submission may have been written, any timeout, disconnect, cancellation, malformed/missing response, controller crash or completion wait failure is `EFFECT_UNKNOWN`.

The dispatcher must not catch every exception and return `FAILED`. The provider integration needs a typed boundary/observation that preserves whether submission could have started. Logs/prose cannot decide this after the fact.

For Codex App Server, `turn/start` is the single provider start effect. `thread/start` and `thread/fork` are forbidden. A lost `thread/resume` response before `turn/start` may be deterministic unavailable only when the client proves no turn submission occurred; otherwise it remains uncertain at the exact native thread.

## 6. Re-entry and reconciliation law

Before creating or executing any attempt, production composition reads the current aggregate.

### Existing terminal event

If the deterministic terminal command already exists, authenticate/replay it and return the existing result. No provider call.

### Existing unfinished attempt

If A<n> has `DELIVERY_ATTEMPT` but no terminal:

- reuse the exact same attempt and nudge identity;
- do not call `nudge()` or allocate A<n+1>;
- do not route to a new binding, destination, session, account, provider or host;
- enter provider-specific **read-only reconciliation** if and only if a reviewed exact-session observation seam exists;
- otherwise return `EFFECT_UNKNOWN / RECONCILIATION_REQUIRED` and stop.

A provider reconciler may append an existing terminal phase only when it proves the exact prior nudge identity against the exact native thread/session and current attempt snapshot. Provider text/model output cannot author this evidence.

### Definitive not-applied observation

V1 does not automatically resubmit even when a provider-specific read claims the nudge is absent. Automatic same-attempt resubmission requires a separately accepted provider idempotency/absence contract proving the prior submission cannot later commit. Without that proof, remain reconciliation-required.

### Binding rotation

A changed RuntimeBinding or provider session does not clear an unfinished Wake attempt. The unresolved attempt remains bound to its persisted destination. Rotation/failover is held until exact reconciliation closes it under accepted law.

## 7. Retry policy

`WakeRetryPolicy` may govern only attempts whose prior attempt has a truthful terminal result that permits retry under its accepted semantics. It cannot treat unfinished/effect-unknown attempts as cooldown-expired retryable work.

Required changes:

- `eligible_for_nudge()` returns false for an unfinished attempt;
- `next_attempt_n()` may continue returning the unfinished number for identity reconstruction, but the production coordinator must branch to reconciliation and never call the provider again;
- status projection distinguishes ordinary pending/retryable from effect unknown;
- maximum-attempt counters do not erase or terminalize unresolved effects.

## 8. Coalesced nudges

A single provider nudge can carry multiple obligations. Persist all corresponding `DELIVERY_ATTEMPT` records atomically before the provider call. If persistence is partial/ambiguous, do not call the provider.

After a possible provider effect:

- all obligations in the exact `NudgeAttempt` share the same nudge reconciliation state;
- do not split unresolved obligations into new nudges;
- a terminal provider observation must authenticate the exact shared `nudge_id` and every attempt command identity before terminal records are appended.

## 9. Codex reconciliation interface

The existing injected Codex client remains transport-only and secret-free. The smallest accepted shape is conceptually:

```text
deliver_wake(exact native thread, exact nudge identity, fixed envelope)
reconcile_wake(exact native thread, exact nudge identity, exact attempt identities)
```

`reconcile_wake` is read-only. It may return only a closed observation such as:

```text
PROVEN_ACCEPTED
PROVEN_DELIVERED
PROVEN_NOT_APPLIED   # informational only in V1; no automatic resubmit
UNKNOWN
TARGET_GONE
```

Every positive observation must be derived from a reviewed provider-native read correlated to the exact thread and nudge/attempt identity. If the installed App Server exposes no sufficient read method, implement `UNKNOWN` and leave the Wake unresolved rather than inventing transcript parsing or a provider-turn store.

Do not import a production dependency directly from a laboratory-only `scripts/ohf/**` module if current architecture forbids it. Factor one neutral App Server primitive and keep OHF and Wake consuming/retesting the same implementation; never copy a second JSON-RPC stack.

## 10. Required RED-first falsifiers

At minimum:

1. provider start response is lost after request write; invoke the outer persisted fabric twice; provider start call count remains exactly 1;
2. provider completion wait times out after start; invoke twice; start call count remains 1;
3. process exits after persisting `DELIVERY_ATTEMPT` and before provider call; restart enters reconciliation-required and makes zero provider call;
4. terminal event persisted but caller response lost; replay returns the terminal result and makes zero provider call;
5. unfinished A1 plus rotated binding/destination cannot create A2 or call another provider;
6. unfinished coalesced nudge cannot split into separate retries;
7. deterministic pre-submit target absence may terminalize `TARGET_UNAVAILABLE` and does not become effect unknown;
8. generic exception after possible request write cannot become `FAILED`;
9. provider reconciler wrong thread/nudge/attempt identity is refused;
10. no provider read seam -> remains effect unknown;
11. effect unknown cannot ACK, source-resolve, claim delivered/success or count as a terminal failure;
12. no new Wake table/store/cursor/daemon/provider-session registry exists;
13. production checked-in registry/targets remain disarmed/disabled;
14. no `thread/start`, `thread/fork`, provider/session failover or second `turn/start` occurs.

Mutation tests must kill removal of persist-before-provider, unfinished-attempt eligibility refusal, exact destination/binding/nudge joins and the pre-submit/possible-effect distinction.

## 11. Acceptance and stop condition

This amendment allows #174 to continue only through a transport-only implementation that proves:

```text
one exact persisted attempt
→ at most one provider turn/start
→ truthful DELIVERED_UNACKNOWLEDGED on the positive Codex canary
```

and an adverse canary:

```text
lost provider response after possible turn/start
→ durable unfinished attempt
→ repeated outer call
→ zero second provider turn
→ EFFECT_UNKNOWN / RECONCILIATION_REQUIRED
```

Claude remains `UNIMPLEMENTED/UNSUPPORTED` unless exact discovery, same-conversation resurrection and bounded same-session ingress are proven on the installed host. Target reasoning-session ACK ingress and source resolution remain later separately released work. Production arming remains false.

#174 stays DRAFT/HOLD-FOR-SOL through RED-first implementation, current-base reconciliation, exact-head hosted CI/security, independent review and both canaries. Merge alone does not arm Wake.