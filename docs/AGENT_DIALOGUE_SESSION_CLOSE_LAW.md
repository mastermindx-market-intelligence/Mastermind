# Mastermind Agent Dialogue — Universal Session-Close Law

**Authority:** standing Chairman operating law for every watcher-enabled Sol, Fable, Claude, Codex, Grok, COO, worker and future compatible agent surface.  
**Status:** canonical procedure/source law only. It creates no Job, Attempt, Worker, Wake obligation, watcher daemon, queue, cursor, retry, provider session or transport authority by itself.  
**Relationship to existing architecture:** this law supplements the accepted Worker Presence / Agent Dialogue / Wake architecture. Watchers remain attention/transport behavior only; Executive OS remains the sole Job/Attempt/Worker/Event lifecycle authority.

## 1. Core invariant — every reciprocal dialogue has an explicit edge

Never end a worker/COO dialogue turn, child wave, Sol review, or watcher-enabled session while the counterpart may still be waiting on an armed watcher without explicitly telling it whether to **continue** or **stop**.

Slack delivery, pickup acknowledgement, start, execution, `BLOCKED`, `DECISION_REQUEST`, `RESULT`, Sol adjudication, terminal `STOP`, watcher shutdown and completion are distinct facts.

A worker posting `RESULT` and saying it is awaiting Sol remains nonterminal from that worker's perspective until Sol replies. **Silence is never a terminal receipt.**

This law is symmetric. Sol must not leave a worker hanging, and a worker must not leave Sol hanging when the protocol requires a return or terminal acknowledgement.

### 1.1 Slack exact-carrier root

For a Slack child, exact carrier identity is **workspace + conversation/channel + thread-root timestamp**.
When a Sol/Chairman commission is the top-level parent, that parent timestamp is the immutable dialogue
root for the child. `PICKUP_ACK`, `WATCH_ARMED`/`WATCH_UNAVAILABLE`, `START`, `PROGRESS`, `BLOCKED`,
`DECISION_REQUEST`, `RESULT`, Sol `CONTINUE`/`RULING`/repair, and terminal `STOP` **must be replies under
that exact parent** unless current canonical transport law explicitly establishes a different carrier.

A **top-level post in the same channel is a carrier-root mismatch**. Same workspace and channel do not
make two different parent timestamps the same carrier, and a worker cannot create/move its own carrier
by posting a new top-level ACK. Treat such a post as transport evidence to reconcile, not as a valid
reciprocal edge for the assigned child.

### 1.2 New-child origination and unconsumed delivery

A `DIRECT_TARGETED — NEW CHILD` buried reply under an unrelated parent/program/previous-child root
cannot by itself originate a new independent child and cannot by itself become that child's
receiver-assignment event. It may carry evidence, an already-authorized child return, or a continuation
for that existing child, but it never turns the enclosing root into a new child commission.

A new independent Slack-only child may originate only through a Sol-authored top-level child commission
root, an eligible command-create event, deliberate current live delivery into the actual provider
interaction, or a production-proven exact native wake/resume path that binds that child to an exact root.
These are origin/assignment edges, not a second lifecycle, router, or Slack command bus.

DELIVERY_SENT or a Slack mention without a valid receiver PICKUP_ACK is DELIVERY_UNCONSUMED / PRE_START
and must not be projected as active, STARTED, executing, waiting-on-worker, or watcher-consumed.
PICKUP_ACK and START are separate edges. Executive OS remains the lifecycle owner: a delivery, pickup,
watcher receipt, or this procedure does not create a Job, Attempt, or Worker state.

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
- the worker must remove/disarm the **exact child operation + carrier source** from its temporary watcher/wait path;
- if the underlying watcher resource also serves a permanent seat inbox, principal lane, or sibling child sources, the child STOP must **not** pause, delete, cancel or disable that aggregate resource;
- no further reply is required unless child-source removal itself fails or the current transport contract requires one exact terminal consumption receipt;
- this STOP does not authorize a next child wave;
- any independent next wave requires fresh lawful operation identity, carrier reconciliation, commission/pickup and reciprocal watcher setup.

A parent program may remain active while one child operation is terminal. A principal/seat watcher resource may likewise remain active while one or all child sources are terminal.

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
3. if the watcher runs in a sidecar/scheduled surface that cannot safely perform the interactive procedure, prefer an accepted **exact-native-task wake/resume action** when the current host/provider surface exposes one. Bind that nudge only to the verified current RuntimeBinding/native task; never choose the newest visible tab/session and never fall back to a different task. The native nudge is attention only: the awakened task must fresh-read the canonical carrier and perform normal procedure before any substantive act;
4. if exact wake/resume is unavailable or the current RuntimeBinding cannot be proven, return the accepted `SESSION_LOST / RUNTIME_BINDING_RECONCILIATION_REQUIRED` or the concrete wake/runtime limitation rather than treating Slack delivery as consumption or silently failing over;
5. do not create a new operation, carrier, receiver, retry, branch, PR, lifecycle state or authority merely because the watcher fired.

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

After receiving terminal `STOP` / `ACCEPTED / STOP` / `CLOSED / STOP`, the worker must stop that child operation and remove the exact child source from its temporary watcher/wait path. A terminal receipt, when required by the currently accepted transport schema, acknowledges consumption of STOP only; it does not create another wave.

If the worker cannot maintain or enter the required watcher/wait path after the checks above, it must return the currently accepted typed blocker such as `WATCH_UNAVAILABLE` rather than disappear.

### 3.5 Watcher resource lifetime and watched-source lifetime are distinct

A temporary or combined watcher **resource** may observe several independent sources, for example:

```text
permanent seat inbox
principal-lane carrier
child A carrier
child B carrier
```

Those source lifetimes are not the resource lifetime.

- A terminal child STOP removes/disarms **only that exact child operation + carrier source**.
- If the watcher resource also serves a permanent seat inbox, principal lane, or sibling sources, the **aggregate resource remains ACTIVE** after the child STOP. Do not pause/delete/cancel the whole heartbeat merely because one child ended.
- **Zero remaining child sources is quiescent, not seat termination.** A permanent seat/principal inbox may continue observing for valid future assignment/continuation edges under its own authority.
- The whole aggregate watcher resource may pause/stop only on explicit seat/principal deregistration, a terminal principal STOP, or an explicit watcher-removal order that targets the aggregate resource itself.
- If removing child A's source fails, report `WATCH_STOP_FAILED` for child A, keep child A terminal, keep the aggregate resource ACTIVE, and continue observing child B/principal/seat sources. The leftover child A source is suppressed from producing a second wake and may not authorize a retry, successor or new wave.

This is resource/attention discipline only. It creates no watcher registry, source database, seat lifecycle, queue or authority owner.

### 3.6 Source-writer stickiness and remote-complete terminality

A Source Continuity receipt reports source identity; it does not replace dialogue or writer authority.
`CHECKPOINT_VERIFIED is never a terminal, retry, transfer, or writer-release edge`. A checkpoint may
truthfully coexist with in-scope dirt, unpushed commits, or an open known effect when the pure verifier
permits it; the already-`START`ed source writer remains sticky to the same operation/carrier/runtime.
`EFFECT_UNKNOWN remains exact-session sticky` and must reconcile before any receiver, retry, failover,
or release-maintainer transition.

`REMOTE_COMPLETE_VERIFIED` is stronger source evidence, but the builder is not terminal merely because
local and remote source now match. The mandatory ordering is:

```text
REMOTE_COMPLETE_VERIFIED
-> SOL_ACCEPTED_BUILDER_RESULT
-> TERMINAL_BUILDER_STOP
-> EXACT_CHILD_SOURCE_REMOVAL_OR_WATCH_STOP_FAILED
-> BRANCH_WRITER_RELEASED
```

Only after `BRANCH_WRITER_RELEASED` may a separately authorized release owner enter through the fresh
maintenance-only release operation defined by `REVIEW_RETURN.md`. That release operation remains on
the same PR/branch, cannot continue the original builder child, and gains no permission to edit
feature semantics, retry an effect, change receiver identity, mark Ready, merge, deploy, or claim
production merely from a Source Continuity receipt.

## 4. Critical anti-pattern

Forbidden:

> The result is ready for Sol final adjudication. I am not posting anything because the next step is mine.

If the counterpart has already said it is waiting with its watcher armed, this leaves it indefinitely nonterminal.

Required behavior:

```text
SOL STOP — <child operation>
Worker portion complete. This child wave is terminal.
Remove this exact child source from the temporary watcher. No next child wave is authorized.
Keep any independent seat/principal/sibling watcher sources active under their own contracts.
Final CEO adjudication now occurs outside this child operation.
```

Sol may then perform CEO-only review, architecture work, merge/release adjudication, durable closeout, or later mint a separate wave.

## 5. Watcher symmetry and authority boundary

For every watcher-enabled handoff expected to return:

- the commissioning side has a continuation path;
- the executing side has a continuation path;
- every nonterminal reply preserves the same current dialogue cycle;
- every terminal reply explicitly closes that cycle and tells the counterpart to stop waiting on that child source.

A watcher owns **no** Job, Attempt, Worker, completion, retry, provider choice, queue, authority, current work status, durable session identity or next-wave right.

Do not create one watcher daemon/database/cron/automation per handoff **as a second control plane**. This prohibition is about giving a watcher durable semantic/lifecycle authority; it does **not** forbid the explicitly temporary, non-authoritative host-native condition watcher described above. Such a bridge owns no lifecycle/cursor/inbox/retry/truth state. Child sources must be removed on terminal child STOP; an aggregate seat/principal watcher resource may remain active only under the independently valid source contracts described in §3.5.

## 6. Watcher shutdown / child-source removal failure

If either side cannot actually remove/disable the watcher state targeted by the terminal edge:

1. do not pretend it is removed/disabled;
2. explicitly report `WATCH_STOP_FAILED` or the currently accepted typed equivalent for the exact child/source;
3. keep the underlying child operation terminal;
4. ensure the counterpart nevertheless receives the terminal STOP so it is not kept waiting;
5. if the watcher resource is aggregate, keep the aggregate resource ACTIVE and continue observing valid sibling/principal/seat sources;
6. suppress the leftover terminal child source from generating another semantic wake;
7. do not let the leftover child source originate another wave, retry, merge, continuation or authority transition.

Watcher cleanup failure is an attention/transport defect, not permission to reopen completed work or to disable unrelated continuation sources.

## 7. New-wave law

Terminal completion of child operation A closes A's watcher **source/cycle**.

Independent child operation B requires, under the currently accepted carrier vocabulary:

1. a new stable child operation key;
2. one lawful carrier;
3. fresh collision/current-state reconciliation;
4. explicit commission;
5. fresh pickup acknowledgement (`PICKUP_ACK`, `ACK <operation_key>`, or the exact currently accepted typed equivalent — never invent a message type the live contract does not support);
6. a separate explicit start-of-work receipt/state where the current carrier contract supports it;
7. a fresh B source registered in the lawful continuation resource/path.

An aggregate permanent seat/principal watcher resource may be reused as the **resource** for B if current law permits it, but an old child A source, old thread state, provider session, worker seat or prior STOP never implicitly authorizes B.

A receiver assignment is exhausted with the child it assigned. General or standing program intent may
keep Sol authorized to advance the parent program, but it does not let the worker self-mint child B or
reuse child A's assignment. Child B needs the explicit fresh commission/delivery/placement edge above.

Where the current machine schema has not yet implemented a distinct typed `START`, the human/session procedure must still keep pickup acknowledgement and actual execution start conceptually separate; do not claim a runtime `START` receipt exists when it does not.

## 8. Universal session-close checklist

Before any watcher-enabled Sol or worker session considers the current dialogue/child wave cleanly closed, verify:

- Is the latest state explicitly terminal or nonterminal?
- If nonterminal, did I tell the counterpart the exact next action?
- If terminal, did I explicitly send `STOP`, `ACCEPTED / STOP`, or `CLOSED / STOP`?
- Did I tell the counterpart to remove/disarm the exact terminal child source?
- Did I remove/disarm my own terminal child source, or explicitly report watcher shutdown/source-removal failure?
- If this is an aggregate watcher, did I preserve independent seat/principal/sibling sources instead of pausing the whole resource?
- Is anyone still saying or semantically indicating “awaiting your ruling/return” for the terminal child?
- Am I accidentally using an old watcher source/session/thread as authorization for a new child operation?

If any answer is unresolved, the dialogue is **not cleanly closed**.

## 9. Production-enforcement boundary

The accepted turn-watcher architecture already treats a Sol `STOP` as one terminal COO wake followed by terminal consumption. This document makes the **procedural obligation universal** even on manual or temporary watcher surfaces.

It does not by itself prove that every provider, Slack contract, managed-browser surface or worker harness enforces all of these semantics automatically. Runtime enforcement must extend the existing Agent Dialogue / Wake owners rather than creating a new lifecycle or watcher control plane.

## 10. Incident rationale

This law exists because a returned worker result was left waiting after Sol decided that final adjudication belonged to Sol and therefore sent no further message. The worker had correctly re-armed its watcher and remained indefinitely blocked on Sol silence.

A later production incident exposed the reciprocal arming ambiguity: a session equated “Slack has no push subscription” with “watching is unavailable” even though its host surface could create a native scheduled watcher. A second session then stalled while reasoning about how to create that watcher instead of invoking the available host-native create/arm path. The universal repair is tool-first and bounded: attempt the actual capability, then return a concrete receipt or failure.

The 2026-08-29 Codex fleet incident added a third failure class: native Codex task heartbeats were armed with an “attention-only / do not ACK/START/execute” prompt and continued obeying that self-blocking clause even after valid same-operation `SOL-DIR-PRO` continuations existed. Exact tasks were alive but obligations remained unconsumed until manually foregrounded. The repair is explicit: watcher prompts detect; they do not become surviving scope fences. A qualifying event re-enters the exact bound session's normal procedure or truthfully reports that re-entry is unavailable.

Independent adversarial review of that repair exposed a fourth incident-causal defect: a combined Codex heartbeat serving a permanent seat inbox plus child sources was paused wholesale when one child reached terminal STOP. That conflated child-source lifetime with aggregate watcher-resource lifetime and caused a later valid Exec Ops directive to go unseen. The repair is equally explicit: child STOP removes the child source; it does not terminate the seat/principal watcher resource or sibling sources.

The 2026-09-02 Fable carrier incident added a fifth defect: a worker interpreted an older standing Chairman program instruction as a surviving receiver assignment after terminal `SOL ACCEPTED / STOP`, self-minted a successor child, and posted its `PICKUP_ACK` as a new top-level message in the same Slack channel. The repair is now explicit: receiver assignment is child-local, terminal STOP consumes it, and Slack carrier identity includes the exact thread root rather than channel membership alone.

Universal repair:

> **Every reciprocal dialogue loop gets an explicit terminal edge, every promised continuation path must actually be armed, watcher prompts never outrank later valid carrier edges, qualifying events re-enter normal procedure, child-source termination never silently kills an independently valid aggregate seat/principal watcher resource, terminal STOP never self-authorizes a successor child, and Slack reciprocal edges remain under the exact assigned thread root.**
