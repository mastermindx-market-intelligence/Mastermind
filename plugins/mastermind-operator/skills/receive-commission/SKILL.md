---
name: receive-commission
description: Receive one bound Mastermind operation, acknowledge pickup, read the exact carrier, and START only after gates clear.
---

# Receive Commission

Use only for one already-bound operation and dialogue. Never self-select work from Slack, Linear, GitHub, a project list, or provider availability.

## Bound operation gate

Require the trusted host or app binding for the exact operation, actor, Job, Attempt, Worker, commission, dialogue parent, and allowed message types. The model must never choose actor, Job, Attempt, Worker, provider, account, host, channel, or thread.

## Procedure

1. Emit exactly one pickup `ACK` for the bound operation.
2. Pickup ACK does not claim START, execution, completion, authority, or acceptance.
3. Read the exact bound thread and carrier plus current commission and source law.
4. Re-pin required repository source and run path and authority collision checks.
5. Arm the exact continuation mechanism when the commission requires it.
6. Emit separate START only after gates clear.
7. Execute only the bounded mission and return through the same operation.

## Output

```text
bound operation identity
pickup ACK receipt
fresh source/carrier read
watcher/continuation readiness
START or exact blocker
next concrete action
```

## Stop conditions

Stop before START on missing binding, current-source failure, scope ambiguity, path collision, credential or admin gate, effect uncertainty, or stale or superseded operation.
