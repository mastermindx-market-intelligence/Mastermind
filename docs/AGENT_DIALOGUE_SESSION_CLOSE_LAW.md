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

After receiving a nonterminal Sol continuation, the worker must reread the lawful thread/context, continue only the same authorized child operation, and re-arm its watcher after its next nonterminal return.

After receiving terminal `STOP` / `ACCEPTED / STOP` / `CLOSED / STOP`, the worker must stop that child operation and disarm its temporary watcher. A terminal receipt, when required by the currently accepted transport schema, acknowledges consumption of STOP only; it does not create another wave.

If the worker cannot maintain or enter the required watcher/wait path, it must return the currently accepted typed blocker such as `WATCH_UNAVAILABLE` rather than disappear.

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

Do not create one watcher daemon/database/cron/automation per handoff as a second control plane.

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

Universal repair:

> **Every reciprocal dialogue loop gets an explicit terminal edge. Never require another agent to infer completion from silence.**
