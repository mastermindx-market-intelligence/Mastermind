---
name: finish-operation
description: Use when the bound operation has reached a result boundary and exact evidence must be returned for Sol adjudication.
---

# Finish Operation

Use only for one already-bound operation and dialogue. The model must never choose actor, Job, Attempt, Worker, provider, account, host, channel, or thread.

## Bound operation gate

Fresh-read the exact carrier after the latest evidence-producing action and verify the current binding has not been superseded.

## Required package reference

Read `../../references/dialogue-boundary.md` before ACK, START, return, or STOP handling. It defines the state distinctions and no-generic-Slack boundary for this packaged workflow.

## Procedure

1. Freeze the exact implementation or research head, changed paths, test and security evidence, production proof state, negative proof, remaining gaps, and capability state.
2. Emit one `result` call for the bound operation.
3. RESULT is not acceptance or STOP. It does not terminalize Executive state, close Agent OS or Linear, or prove production merely by being sent.
4. Do not blindly retry an ambiguous RESULT write; reconcile the same message and operation identity.
5. After RESULT, await one explicit Sol CONTINUE, REQUEST_REPAIR, or STOP on the same carrier.
6. After terminal STOP, stop this child work and remove only the exact child operation + carrier source from this side's approved continuation path. If the watcher also serves a seat, principal, or sibling source, keep the aggregate resource active. If removal fails, report `WATCH_STOP_FAILED`, keep the child terminal, and suppress only the leftover terminal source within this side's authority; do not disable unrelated sources or manipulate the counterpart's resource.
7. The operator must never self-merge, self-release, self-deploy, self-commission a successor, or reuse the old watcher for new work. A terminal STOP does not authorize a successor child.
8. Return a required terminal consumption receipt only when the current contract and exposed tools support it. If the required receipt cannot be expressed, report the exact transport limitation; do not invent a message type or reuse an unrelated tool. Missing receipt evidence does not reopen terminal work.

## Output

```text
result status
exact immutable evidence
capability state
production proof state
remaining gaps
awaiting explicit Sol edge or consumed terminal STOP
exact child-source cleanup / aggregate watcher state / required receipt status
```

## Stop conditions

The dialogue remains awaiting Sol until an explicit terminal edge is consumed, even when implementation work is finished. A pending Sol dialogue does not reopen or change Executive Job or Attempt state. Runtime lifecycle remains Executive-owned; report dialogue and runtime states separately. Apply the current protected dialogue close law rather than treating this plugin as another lifecycle owner.
