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

## Common mistakes

| Failure | Correct response |
|---|---|
| Watcher detects `RESULT` and only tells Chairman what Sol should do | Re-pin, review, post the lawful Sol edge, then report material outcome |
| Worker is waiting and Sol says “the next step is mine” | Send explicit CONTINUE or STOP first |
| Watcher sees terminal completion and starts the next wave | STOP/disarm; independent wave needs fresh commission law |
| Wake is treated as permission to merge/retry/fail over | Reconcile authority/carrier first; watcher grants none |
| Slack reply is treated as Job/Worker execution truth | Keep Executive lifecycle separate |

## K3 pass criteria

Given a watcher-enabled COO `RESULT` that is fully decidable inside current Chairman-authorized
scope, a fresh Sol must directly complete the required review and same-carrier continuation/STOP
without requiring the Chairman to notice the alert, copy a prompt, or manually wake the worker.
