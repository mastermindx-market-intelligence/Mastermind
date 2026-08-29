# Mastermind Agent Dialogue — Universal Session-Close Law

**Authority:** standing Chairman operating law for every watcher-enabled Sol, Fable, Claude, Codex, Grok, COO, worker and future compatible agent surface.  
**Status:** canonical procedure/source law only. It creates no Job, Attempt, Worker, Wake obligation, watcher daemon, queue, cursor, retry, provider session or transport authority by itself.  
**Relationship to existing architecture:** this law supplements the accepted Worker Presence / Agent Dialogue / Wake architecture. Watchers remain attention/transport behavior only; Executive OS remains the sole Job/Attempt/Worker/Event lifecycle authority.

## 1. Core invariant — every reciprocal dialogue has an explicit edge

Never end a worker/COO dialogue turn, child wave, Sol review, or watcher-enabled session while the counterpart may still be waiting on an armed watcher without explicitly telling it whether to **continue** or **stop**.

Slack delivery, pickup acknowledgement, start, execution, `BLOCKED`, `DECISION_REQUEST`, `RESULT`, Sol adjudication, terminal `STOP`, watcher shutdown and completion are distinct facts.

A worker posting `RESULT` and saying it is awaiting Sol remains nonterminal from that worker's perspective until Sol replies. **Silence is never a terminal receipt.**

This law is symmetric. Sol must not leave a worker hanging, and a worker must not leave Sol hanging when the protocol requires a return or terminal acknowledgement.

## 2. Mandatory Sol edge after every worker return

After every worker/COO `BLOCKED`, `DECISION_REQUEST`, or `RESULT`, Sol must emit exactly one explicit state in the same lawful carrier/thread.

### 2.1 Nonterminal continuation

Use a clear semantic edge such as:

```text
SOL CONTINUE — <current child operation>
SOL RULING / CONTINUE — <current child operation>
SOL REQUEST_REPAIR — <current child operation>
```

The message must:

1. name the exact current child operation;
2. state what happens next;
3. keep the same lawful carrier/operation binding;
4. tell the worker to re-arm its approved wait/watch path after its next nonterminal return;
5. preserve any current source-law, authority, scope and stop conditions.

### 2.2 Terminal child-wave boundary

Use a clear terminal edge such as:

```text
SOL STOP — <current child operation>
SOL ACCEPTED / STOP — <current child operation>
SOL CLOSED / STOP — <current child operation>
```

The message must explicitly state all of:

- the current child wave is terminal;
- the worker must stop work on that child operation;
- the worker must disarm its temporary watcher/wait path;
- no further reply is required unless watcher shutdown itself fails or the current transport contract requires one exact terminal consumption receipt;
- this STOP does not authorize a next child wave;
- any independent next wave requires fresh lawful operation identity, carrier reconciliation, commission/pickup and reciprocal watcher setup.

A parent program may remain active while one child operation is terminal.

## 3. Worker/COO reciprocal behavior

After a nonterminal return, a watcher-enabled worker/COO must enter the approved exact-carrier wait/watch path rather than silently abandoning the dialogue.

An approved continuation path may be the production-proven canonical Worker Presence / Turn-Watcher path, an accepted already-live exact-carrier waiter, or—while the canonical path is not production-proven—a temporary host-native Task/Automation/scheduled condition watcher that periodically reads the exact carrier. **A Slack connector lacking push/webhook subscriptions does not by itself make watching unavailable.** If the current reasoning surface can create a native scheduled/condition watcher that reads the exact thread, that is a lawful non-authoritative continuity bridge under the commission procedure.

Watcher setup is a **bounded tool action**, not an architecture discussion. Use this order:

```text
1. canonical watcher PROVEN_LIVE? -> arm/use it now
2. accepted live exact-carrier waiter exists? -> register/use it now
3. otherwise inspect the current host tool surface once for Task/Automation/schedule/condition-watch
   -> present: invoke its CREATE/ARM action now for the exact carrier/current operation
   -> absent: return WATCH_UNAVAILABLE and name the checked surface
   -> valid create call fails on permission/runtime/unavailability: return WATCH_UNAVAILABLE + exact error
   -> schema/argument error: correct once and retry once, then return the exact failure
```

Do not end the turn saying the watcher is “planned,” “should be possible,” “needs Slack push,” or “is being investigated.” A successful registration produces the required `WATCH_ARMED` receipt. A concrete failed/absent capability produces `WATCH_UNAVAILABLE`. No third speculative setup loop.

The temporary scheduled watcher must remain bounded to the exact current operation/carrier. On each run it reads that exact carrier using the scheduled surface's available connector/read capability, ignores the baseline and older messages, and reacts only to the first qualifying opposite-side reply for the current operation. If that scheduled execution surface cannot access the carrier at run time, report that concrete limitation; do not infer it merely from the interactive connector lacking push.

### 3.1 Resource classes — detect cheaply, reason only on change

Classify the thing doing the waiting rather than treating every poll as equivalent.

**Class E — event-driven / passive wait.** A provider/webhook/native waiter or deterministic blocking tool that does not re-invoke a reasoning model on unchanged state. Prefer this whenever available.

**Class T — tool-only polling.** A deterministic process may poll at a lawful API cadence, but unchanged samples are suppressed and do not instantiate a new reasoning-model turn. Tight tool polling never justifies tight model-wake polling.

**Class M — reasoning-model scheduled polling.** A Task/Automation/background completion that invokes Fable/Opus/Claude/Codex/Sol merely to determine whether something changed.

- **Default interval: 60 minutes.**
- **Absolute minimum interval: 15 minutes** unless a later explicit source-law exception names a safety-critical condition.
- An urgent Class-M watcher may begin at 15 minutes, but `NO_MATERIAL_CHANGE` backs off `15m -> 30m -> 60m` and remains at 60 minutes until a material event resets the cycle.
- Once only an external dependency remains, the reasoning session yields instead of running `check -> no change -> wait a few seconds -> check again` inside one long turn.
- A `NO_MATERIAL_CHANGE` wake performs one bounded exact-carrier/status delta read and exits. It does not redo repo archaeology, launch subagents, rewrite summaries, or manufacture progress.

**Fable/Opus/Claude/Codex/Sol reasoning sessions are principals, not polling daemons.**

### 3.2 Watcher prompt is attention, never a surviving scope fence

A **watcher prompt is not a scope fence**. It may narrow what the watcher inspects and what counts as a qualifying event, but it **cannot override a later valid same-operation carrier edge** or the current protected procedure governing that operation.

A watcher prompt must therefore never encode an unconditional instruction such as “do not locate, ACK, watch, START, execute, continue, or act” that survives after the watcher detects a qualifying carrier event. That shape turns an attention bridge into a self-blocking control instruction.

On a qualifying carrier event for the current operation:

1. fresh-read the exact carrier and identify the latest valid semantic edge;
2. if the watcher is running as a turn of the exact bound reasoning session, **re-enter normal worker procedure** for that same child: reconcile identity/binding, ACK when pickup is owed, arm/update the lawful continuation path, emit a separate truthful START when gates clear, or return the required typed blocker;
3. if the watcher runs in a sidecar/scheduled surface that cannot safely perform the interactive procedure, wake/foreground the exact bound session or return the concrete watcher/runtime inability; the sidecar's limited scope does not bind the subsequently awakened interactive session;
4. do not create a new operation, carrier, receiver, retry, branch, PR, lifecycle state or authority merely because the watcher fired.

A watcher that detects a valid `CONTINUE`, assignment, ruling, repair request or other action-required edge and then only says “attention required” while the same exact reasoning session could continue is the **notification-only anti-pattern**. The correct path is detection -> re-entry -> fresh procedure -> same-carrier action or truthful blocker.

### 3.3 Read-before-substantive-write carrier freshness fence

Pickup ACK may remain ACK-before-full-read when the controlling commission explicitly requires that order; the ACK asserts receipt/current identity only and no substantive gate or execution state.

Before any later substantive/stateful reciprocal write—including `START`, material `PROGRESS`, `BLOCKED`, `DECISION_REQUEST`, `RESULT`, CI/proof completion, `CONTINUE`, `RULING`, repair, `PARK`, or terminal `STOP`—the sender must:

1. **Fresh-read the exact bound carrier/thread in the same interactive turn.**
2. Perform that read **after the latest local evidence-producing action** the outbound message is about.
3. Compare the result with the last consumed baseline and consume/adjudicate every unseen opposite-side semantic edge before composing the outbound message.
4. Only then write the substantive edge to the same lawful carrier.

An armed watcher, a `WATCH_ARMED` receipt, absence of a notification, local memory, or “I would have been woken if the other side replied” **never satisfies this freshness fence**.

If the carrier cannot be freshly read, do not assert stale state. Preserve the operation and return the accepted read/transport blocker where possible; do not blind retry or fail over.

### 3.4 One-watcher discipline and missed-fire behavior

For one side of one reciprocal dialogue there may be at most one active watcher for the same `side + operation_key + exact carrier + purpose`. Reuse/update an existing equivalent watcher rather than stacking another one.

If multiple expected Class-M fire opportunities pass with no observed run while the dialogue remains nonterminal, watcher silence is degraded evidence, not proof of no change. Fresh-read the exact carrier before the next substantive action; do not compensate by shortening below the resource floor.

Before returning `WATCH_UNAVAILABLE`, the worker/session must therefore reach an actual absent-tool or failed-create result under the sequence above. State which mechanism/surface was checked and the exact failure instead of disappearing.

After receiving a nonterminal Sol continuation, the worker must reread the lawful thread/context, continue only the same authorized child operation, and re-arm its watcher after its next nonterminal return.

After receiving terminal `STOP` / `ACCEPTED / STOP` / `CLOSED / STOP`, the worker must stop that child operation and disarm its temporary watcher. A terminal receipt, when required by the currently accepted transport schema, acknowledges consumption of STOP only; it does not create another wave.

If the worker cannot maintain or enter the required watcher/wait path after the checks above, it must return the currently accepted typed blocker such as `WATCH_UNAVAILABLE` rather than disappear.

## 4. Critical anti-pattern

Forbidden:

> The result is ready for Sol final adjudication. I am not posting anything because the next step is mine.

If the counterpart has already said it is waiting with its watcher armed, this leaves it indefinitely nonterminal.

Required behavior:

```text
SOL STOP — <child operation>
Worker portion complete. This child wave is terminal.
Disarm the temporary watcher. No next child wave is authorized.
Final CEO adjudication now occurs outside this child operation.
```

Sol may then perform CEO-only review, architecture work, merge/release adjudication, durable closeout, or later mint a separate wave.

## 5. Watcher symmetry and authority boundary

For every watcher-enabled handoff expected to return:

- the commissioning side has a continuation path;
- the executing side has a continuation path;
- every nonterminal reply preserves the same current dialogue cycle;
- every terminal reply explicitly closes that cycle and tells the counterpart to stop waiting.

A watcher owns **no** Job, Attempt, Worker, completion, retry, provider choice, queue, authority, current work status, durable session identity or next-wave right.

Do not create one watcher daemon/database/cron/automation per handoff **as a second control plane**. This prohibition is about giving a watcher durable semantic/lifecycle authority; it does **not** forbid the explicitly temporary, non-authoritative host-native condition watcher described above. Such a bridge owns no lifecycle/cursor/inbox/retry/truth state, must stay bound to the exact current operation/carrier, and must be disarmed on terminal STOP.

## 6. Watcher shutdown failure

If either side cannot actually disable its watcher:

1. do not pretend it is disabled;
2. explicitly report `WATCH_STOP_FAILED` or the currently accepted typed equivalent;
3. keep the underlying child operation terminal;
4. ensure the counterpart nevertheless receives the terminal STOP so it is not kept waiting;
5. do not let the leftover watcher originate another wave, retry, merge, continuation or authority transition.

Watcher cleanup failure is an attention/transport defect, not permission to reopen completed work.

## 7. New-wave law

Terminal completion of child operation A closes A's watcher cycle.

Independent child operation B requires, under the currently accepted carrier vocabulary:

1. a new stable child operation key;
2. one lawful carrier;
3. fresh collision/current-state reconciliation;
4. explicit commission;
5. fresh pickup acknowledgement (`PICKUP_ACK`, `ACK <operation_key>`, or the exact currently accepted typed equivalent — never invent a message type the live contract does not support);
6. a separate explicit start-of-work receipt/state where the current carrier contract supports it;
7. newly armed reciprocal continuation paths/watchers.

An old watcher, old thread state, provider session, worker seat or prior STOP never implicitly authorizes B.

Where the current machine schema has not yet implemented a distinct typed `START`, the human/session procedure must still keep pickup acknowledgement and actual execution start conceptually separate; do not claim a runtime `START` receipt exists when it does not.

## 8. Universal session-close checklist

Before any watcher-enabled Sol or worker session considers the current dialogue/child wave cleanly closed, verify:

- Is the latest state explicitly terminal or nonterminal?
- If nonterminal, did I tell the counterpart the exact next action?
- If terminal, did I explicitly send `STOP`, `ACCEPTED / STOP`, or `CLOSED / STOP`?
- Did I tell the counterpart to disarm its watcher/wait path?
- Did I disarm my own temporary watcher, or explicitly report watcher shutdown failure?
- Is anyone still saying or semantically indicating “awaiting your ruling/return”?
- Am I accidentally using an old watcher/session/thread as authorization for a new child operation?

If any answer is unresolved, the dialogue is **not cleanly closed**.

## 9. Production-enforcement boundary

The accepted turn-watcher architecture already treats a Sol `STOP` as one terminal COO wake followed by terminal consumption. This document makes the **procedural obligation universal** even on manual or temporary watcher surfaces.

It does not by itself prove that every provider, Slack contract, managed-browser surface or worker harness enforces all of these semantics automatically. Runtime enforcement must extend the existing Agent Dialogue / Wake owners rather than creating a new lifecycle or watcher control plane.

## 10. Incident rationale

This law exists because a returned worker result was left waiting after Sol decided that final adjudication belonged to Sol and therefore sent no further message. The worker had correctly re-armed its watcher and remained indefinitely blocked on Sol silence.

A later production incident exposed the reciprocal arming ambiguity: a session equated “Slack has no push subscription” with “watching is unavailable” even though its host surface could create a native scheduled watcher. A second session then stalled while reasoning about how to create that watcher instead of invoking the available host-native create/arm path. The universal repair is tool-first and bounded: attempt the actual capability, then return a concrete receipt or failure.

The 2026-08-29 Codex fleet incident added a third failure class: native Codex task heartbeats were armed with an “attention-only / do not ACK/START/execute” prompt and continued obeying that self-blocking clause even after valid same-operation `SOL-DIR-PRO` continuations existed. Exact tasks were alive but obligations remained unconsumed until manually foregrounded. The repair is explicit: watcher prompts detect; they do not become surviving scope fences. A qualifying event re-enters the exact bound session's normal procedure or truthfully reports that re-entry is unavailable.

Universal repair:

> **Every reciprocal dialogue loop gets an explicit terminal edge, every promised continuation path must actually be armed, watcher prompts never outrank later valid carrier edges, and a qualifying watcher event re-enters normal procedure instead of becoming notification-only dead air.**
