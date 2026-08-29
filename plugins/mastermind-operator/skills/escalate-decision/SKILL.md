---
name: escalate-decision
description: Return one bound BLOCKED or DECISION_REQUEST when a material decision prevents lawful continuation.
---

# Escalate Decision

Use only for one already-bound operation and dialogue. The model must never choose actor, Job, Attempt, Worker, provider, account, host, channel, or thread.

## Bound operation gate

Fresh-read the exact carrier and prove the current Attempt and binding remain authoritative before writing.

## Procedure

1. Classify the return as `blocked` or `request_decision`.
2. State the exact blocker or question, outcome impact, work-paused truth, evidence, options, recommendation, and who must act.
3. Stop work at the unsafe boundary; do not route around missing authority or widen scope.
4. Emit one bound tool call. On ambiguous write outcome, do not retry; preserve the same message identity for reconciliation.
5. Keep the existing operation and continuation path active until an explicit Sol edge arrives unless current source law says the operation is terminal.

## Output

```text
BLOCKED | DECISION_REQUEST
exact issue and impact
work_paused = true | false
options and recommendation
evidence refs
needed from Sol | Chairman | dependency owner
```

## Stop conditions

Do not proceed while material authority, architecture, destructive effect, credential or admin action, source conflict, or effect state remains unresolved.
