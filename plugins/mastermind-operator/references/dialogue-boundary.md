# Mastermind Operator dialogue boundary

The operator plugin applies only to one already-bound operation and company dialogue.

Distinct states remain distinct:

```text
delivery
→ pickup ACK
→ watcher/continuation readiness where required
→ START after gates clear
→ execution
→ PROGRESS / BLOCKED / DECISION_REQUEST / RESULT
→ explicit Sol CONTINUE / REQUEST_REPAIR / STOP
→ after terminal STOP, exact child-source removal and required consumption receipt
```

The operator never chooses or overrides actor, Job, Attempt, Worker, commission, provider, account, host, runtime binding, Slack channel, Slack thread, or dialogue parent. It never treats Slack delivery as Executive admission, ACK as START, RESULT as acceptance, CI as production proof, or silence as STOP.

A dialogue write with an ambiguous outcome is never blindly retried. It remains on the same message/operation identity for canonical reconciliation.

After terminal STOP, each side removes only its own exact child operation + carrier source. If a watcher also serves a seat, principal, or sibling source, keep the aggregate resource active. If removal fails, report `WATCH_STOP_FAILED`, keep the child terminal, and suppress the leftover terminal source within the affected side's authority. Do not use one child's STOP to disable another source or to claim the counterpart's cleanup without evidence. STOP does not authorize a successor child.

A pending Sol dialogue does not reopen or change Executive Job or Attempt state. Delivery, dialogue consumption, source cleanup, and Executive lifecycle are separate facts. Preserve any required terminal consumption receipt through the supported current contract; do not invent a new message type or tool. The current protected dialogue close law controls these distinctions, not a new plugin-local state machine.
