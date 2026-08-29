---
name: return-progress
description: Return one concise evidence-backed PROGRESS update on the bound operation without changing lifecycle state.
---

# Return Progress

Use only for one already-bound operation and dialogue. The model must never choose actor, Job, Attempt, Worker, provider, account, host, channel, or thread.

## Bound operation gate

Require the exact current binding and fresh-read the bound carrier after the latest evidence-producing action.

## Procedure

1. Report the current stage, completed observable work, exact evidence references, and next concrete action.
2. Use `progress` at most once for the semantic update.
3. Do not report no-change polling as progress; yield with no message when there is no material change unless the protocol requires a cheap typed no-change receipt.
4. Do not claim Executive status, acceptance, production proof, merge, deployment, or completion.
5. Continue executing within scope after the update; routine progress does not require a Sol ruling.

## Output

```text
stage
completed observable effect
evidence refs
next concrete effect
known blocker = none
```

## Stop conditions

Use `blocked` or `request_decision` instead when work cannot lawfully continue.
