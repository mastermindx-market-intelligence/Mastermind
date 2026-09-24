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
6. On terminal STOP, stop work and disarm the operation-specific watcher. Report failure to disarm honestly.
7. The operator must never self-merge, self-release, self-deploy, self-commission a successor, or reuse the old watcher for new work.

## Output

```text
result status
exact immutable evidence
capability state
production proof state
remaining gaps
awaiting explicit Sol edge
```

## Stop conditions

The child remains nonterminal until an explicit Sol terminal edge exists, even when implementation work is finished.
