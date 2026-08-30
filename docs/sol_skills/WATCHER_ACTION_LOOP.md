---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: watcher_action_loop
---

# WATCHER ACTION LOOP — Sol Watchers Re-enter the Control Loop

Use when Sol arms or operates a Task/Automation/condition-watch for a worker/COO dialogue, or when
such a watcher detects `ACK`, `START`, `BLOCKED`, `DECISION_REQUEST`, `RESULT`,
`WATCH_UNAVAILABLE`, `WATCH_EVENT`, or material carrier/CI/proof movement.

## Mission

**A Sol watcher is an action re-entry hook, not a notification service.**

Its loop is:

```text
DETECT -> RE-PIN -> ADJUDICATE -> ACT -> REPORT
```

The watcher remains transport/attention behavior only. It **never creates or mutates Executive
Job/Attempt/Worker/Event state**, never owns authority, never retries or fails over a carrier, and
never turns Slack delivery into execution truth. Re-entering Sol procedure is not a new control
plane; it means the current Sol session resumes the already-authorized CEO review/continuation job.

Apply `REVIEW_RETURN.md`, `COMMISSION_WAVE.md`, `RECONCILE_STATE.md` when triggered by their
conditions, plus `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` for every watcher-enabled dialogue.

## Required action loop

### 1. DETECT

Read the exact bound carrier and operation key. Ignore the stored baseline and older turns. A wake
without a qualifying new opposite-side turn is `NO_MATERIAL_CHANGE`; do not manufacture work.

### Watcher lifetime invariant — nonterminal events do not end the watch

A continuation watcher spans the **entire current child dialogue cycle**, not merely the first reply
it notices.

- **ACK, WATCH_ARMED, START, and PROGRESS are nonterminal watcher events.** Consume the event,
  advance the consumed baseline and keep or re-arm the Sol watcher before ending the turn. If the
  underlying watcher is one-shot/first-match, a successful nonterminal match means Sol must register
  the next watch against the newest consumed baseline; it is not terminal cleanup.
- **BLOCKED, DECISION_REQUEST, and RESULT are action-required watcher events.** Do not disable the
  watcher and merely report upward. Re-pin, adjudicate, and post exactly one lawful same-carrier Sol
  edge. A nonterminal `CONTINUE`/ruling/repair advances the baseline and keeps/re-arms the watcher for
  the next return.
- `WATCH_UNAVAILABLE` is a continuation defect to adjudicate, not silent permission to abandon the
  counterpart. `WATCH_STOP_FAILED` is handled by the universal session-close law without reopening
  an otherwise terminal child.
- **Never disable Sol's continuation watcher before sending the worker's terminal STOP.** Only after
  the terminal STOP edge is sent may Sol disarm its watcher for that child operation (or report the
  truthful shutdown failure required by current law).

Canonical regression sequence:

```text
ACK -> WATCH_ARMED -> START -> RESULT -> STOP
```

The first four edges are nonterminal from the watcher-lifetime perspective. `RESULT` requires Sol
adjudication; it does not itself close either side's watcher. The watcher cycle closes only after the
explicit terminal Sol edge required by `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`.

### 2. RE-PIN

Before any modifying response, load current protected `docs/sol_skills/INDEX.md`, record its exact
SHA, load the required same-SHA skills/source laws, and reconcile only the canonical evidence needed
for the decision. A watcher prompt must never freeze an old Skillpack SHA as future authority.

### 3. ADJUDICATE

Classify the new turn against the current child operation, stop condition, one-carrier binding,
current GitHub/Agent OS truth and Chairman authorization. Determine whether the next step is inside
Sol's already-authorized authority or crosses the **Chairman-only boundary** below.

### 4. ACT

When the evidence and current authorization are sufficient, **post the actual Sol edge in the same
lawful carrier** before asking the Chairman to relay anything. Use the currently accepted semantic
edge, for example `SOL RULING / CONTINUE`, `SOL REQUEST_REPAIR`, `SOL PARK`, or terminal `SOL STOP`.

**Do not stop at `Sol action required` when current authority permits the action.** Do not tell the
Chairman “send this to the COO” when Sol can lawfully send it directly. The purpose of the watcher is
to remove Chairman message-shuttling from an already-authorized reciprocal program loop.

For a terminal child, send the explicit STOP/close edge and shut down the child watcher cycle. A
**terminal return does not authorize a new independent wave**. A new wave follows the current fresh
operation/carrier/commission/pickup law.

### 5. REPORT

After acting, notify the Chairman only when the action or milestone is materially worth surfacing.
The report states what Sol actually did, not merely what Sol recommends somebody else do.

If action cannot lawfully occur, report the exact boundary/gate and, where permitted, still post a
bounded HOLD/PARK/STOP edge so the worker is not left waiting on silence.

## Chairman-only boundary

A watcher must not self-expand authority. Escalate instead of executing the disputed/new act when
current law requires fresh Chairman intent or another unavailable gate, including examples such as:

- a new independent program or authority class not covered by current Chairman intent;
- signal/Prophet/trading/portfolio authority promotion not already approved;
- external communication, credential disclosure/use, or another human-representation decision;
- an effect-unknown/ambiguous prior modification or unresolved one-carrier conflict;
- a destructive or materially scope-widening action whose authorization is not current;
- a required runtime/transport/permission/source-law gate that is unavailable or contradictory.

Escalation does not mean leaving the counterpart hanging. Preserve the dialogue law with the safest
lawful same-carrier edge, then ask the Chairman for the missing decision.

## Watcher prompt contract

A Sol-owned watcher prompt is incomplete unless it contains all of:

- exact carrier + current operation/child keys and the latest consumed baseline;
- qualifying return/event types;
- watcher lifetime behavior: nonterminal matches advance the baseline and keep/re-arm the watcher,
  including explicit re-registration when the host mechanism is one-shot/first-match;
- current-Skillpack re-pin before modifying action;
- minimum canonical evidence reconciliation;
- same-carrier Sol action when current authority/gates permit;
- explicit Chairman-only/new-authority/missing-gate boundaries;
- one-carrier/no-blind-retry/no-lifecycle-inference laws;
- terminal STOP and watcher-cycle shutdown behavior.

A **notification-only watcher** whose sole behavior is “if something changes, notify me with the
Sol action required” is insufficient for an already-authorized Sol-owned continuation loop.

If the scheduled surface can read but cannot write the lawful carrier, it may wake/notify the
interactive Sol surface as a transport bridge. On that first interactive turn, Sol must re-pin,
adjudicate and act before reporting to the Chairman whenever current authority permits. Do not turn
a write-capability limitation into permanent Chairman relay work.

### Structured temporary-Sol watcher contract

Every newly created or materially updated temporary Sol Task/Automation/condition-watch must begin
with this closed, machine-auditable header:

```text
MMX_SOL_WATCHER_V1
WATCHER_ROLE: <ACTION_AUTHORITATIVE|OBSERVER_ONLY|PARENT_ORCHESTRATOR|TRIAGE_ONLY>
OPERATION_KEY: <stable current operation key>
CARRIER: <slack:<channel-id>/<parent-message-ts>|aggregate:<stable-scope-id>>
LATEST_HANDLED_EDGE: <Slack ts, semantic edge id, or NONE>
ACTION_REQUIRED_EVENTS: <closed value required by role>
ACTION_REQUIRED_OUTCOME: <closed value required by role>
SISTER_SOL_POLICY: <closed value required by role>
```

The header owns no authority or task state. It makes the prompt's claimed role and safety contract
auditable against the already-existing responsibility, action-target, carrier and runtime owners.
`ACTION_AUTHORITATIVE` always requires an exact Slack carrier. `aggregate:<stable-scope-id>` is
allowed only for `OBSERVER_ONLY`, `PARENT_ORCHESTRATOR`, or `TRIAGE_ONLY`; it identifies one bounded
read/oversight scope and never grants authority over every child it contains. Any child-semantic
modification still requires an exact current action target and exact lawful carrier.

#### `ACTION_AUTHORITATIVE`

Use only for the exact currently resolved Sol action target for the named child/turn:

```text
ACTION_REQUIRED_EVENTS: BLOCKED,DECISION_REQUEST,RESULT
ACTION_REQUIRED_OUTCOME: SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER
SISTER_SOL_POLICY: OBSERVE_ONLY_UNLESS_EXACT_ACTION_TARGET
```

On an action-required event, this watcher turn must end with either the lawful same-carrier Sol edge
or a typed blocker naming the real boundary, for example `CHAIRMAN_ONLY`,
`ATTENTION_OWNER_CONFLICT`, `EFFECT_UNKNOWN`, `CARRIER_UNREADABLE`, `WRITE_UNAVAILABLE`, or
`SOURCE_LAW_CONFLICT`. A positive terminal instruction such as “Sol action required,” “waiting for
Sol,” or “stand by for Sol's ruling” is `NOTIFICATION_ONLY_SELF_DEADLOCK`: the watcher has identified
its own role as the missing actor and then waited for itself. A prohibition or regression example
such as “do not wait for Sol” is not itself a self-deadlock finding.

#### `OBSERVER_ONLY`

Use for a sister Sol/account/surface allowed to inspect the same child but not modify it:

```text
ACTION_REQUIRED_EVENTS: NONE
ACTION_REQUIRED_OUTCOME: OBSERVE_ONLY_NO_MODIFY
SISTER_SOL_POLICY: NEVER_ACT_WITHOUT_CANONICAL_TRANSFER
```

It may read, reconcile and report, but it may not issue `CONTINUE`, `RULING`, `REQUEST_REPAIR`,
`STOP`, merge/release, retry or commission a successor. Another Sol becomes action-authoritative only
after canonical action-target transfer; never elect by recency, responsiveness, newest tab, newest
Slack message or apparent quota.

#### `PARENT_ORCHESTRATOR`

Use for a program-level loop that acts only on parent transitions and does not race a dedicated
child action watcher:

```text
ACTION_REQUIRED_EVENTS: PARENT_TRANSITION
ACTION_REQUIRED_OUTCOME: PARENT_EDGE_ONLY_NO_CHILD_RACE
SISTER_SOL_POLICY: NEVER_ACT_ON_DEDICATED_CHILD_RETURN
```

A parent orchestrator may use an `aggregate:` carrier for its bounded program scope. It must still
fresh-read each exact child carrier needed for a parent transition and cannot consume or answer a
dedicated child return.

#### `TRIAGE_ONLY`

Use for an estate/continuity audit that detects unconsumed returns without creating duplicate child
authority:

```text
ACTION_REQUIRED_EVENTS: UNCONSUMED_RETURN
ACTION_REQUIRED_OUTCOME: RECONCILE_OR_REPORT_NO_DUPLICATE
SISTER_SOL_POLICY: NEVER_ELECT_BY_RECENCY
```

Triage may use an `aggregate:` carrier for a bounded estate census. It reports or reconciles the
attention defect; it never becomes child action-authoritative merely because it found the defect.
The exact child action surface must act or receive canonical action-target transfer first.

Validate an account-local JSON task export with:

```text
python3 scripts/audit_sol_watchers.py <tasks.json>
```

The validator is read-only and account-local. A passing prompt audit proves contract conformance,
not that a scheduled turn fired, consumed Slack, wrote an edge or made the event-driven Wake path
production-live. Each ChatGPT account may repair only its own native task store unless a separately
accepted host capability explicitly proves broader authority. When an account export includes
ordinary reminders or unrelated scheduled tasks, mark each wrapper entry `audit_kind: NON_WATCHER`;
enabled `NON_WATCHER` entries are listed but excluded from watcher-conformance counts.

## Common mistakes

| Failure | Correct response |
|---|---|
| Watcher detects `PICKUP_ACK` and is disabled because the first reply arrived | Advance the baseline and keep/re-arm the watcher; ACK is nonterminal |
| A one-shot watcher matches `START` or `PROGRESS` and is not re-registered | Re-arm against the newest consumed baseline before ending the turn |
| Watcher detects `RESULT` and only tells Chairman what Sol should do | Re-pin, review, post the lawful Sol edge, then report material outcome |
| Action-authoritative watcher says “waiting for Sol” | Classify `NOTIFICATION_ONLY_SELF_DEADLOCK`; act or return a typed blocker |
| Observer sister Sol acts because the authoritative account looks idle | Fail closed until canonical action-target transfer; never elect by recency |
| Aggregate triage task acts directly on a child it discovered | Route/reconcile attention; exact child action authority remains separate |
| Worker is waiting and Sol says “the next step is mine” | Send explicit CONTINUE or STOP first |
| Watcher sees terminal completion and starts the next wave | STOP/disarm; independent wave needs fresh commission law |
| Wake is treated as permission to merge/retry/fail over | Reconcile authority/carrier first; watcher grants none |
| Slack reply is treated as Job/Worker execution truth | Keep Executive lifecycle separate |

## K3 pass criteria

Given a watcher-enabled COO `RESULT` that is fully decidable inside current Chairman-authorized
scope, a fresh Sol must directly complete the required review and same-carrier continuation/STOP
without requiring the Chairman to notice the alert, copy a prompt, or manually wake the worker.

Given the sequence `ACK -> WATCH_ARMED -> START -> RESULT`, a fresh Sol must keep or re-arm its
continuation watcher after each nonterminal event, adjudicate the `RESULT`, send the required same-
carrier terminal or nonterminal edge, and disarm the child watcher only after terminal STOP. A Sol
that disables its watcher on ACK/START and therefore misses the later RESULT fails this skill.

A structured `ACTION_AUTHORITATIVE` watcher fails K3 if it returns
`NOTIFICATION_ONLY_SELF_DEADLOCK` instead of `SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER`. In a
three-account canary, only the canonically resolved action target may act; both observer accounts must
remain read-only until canonical action-target transfer, and timestamp/recency may never elect a
replacement.
