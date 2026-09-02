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
→ reciprocal watcher shutdown
```

The operator never chooses or overrides actor, Job, Attempt, Worker, commission, provider, account, host, runtime binding, Slack channel, Slack thread, or dialogue parent. It never treats Slack delivery as Executive admission, ACK as START, RESULT as acceptance, CI as production proof, or silence as STOP.

A dialogue write with an ambiguous outcome is never blindly retried. It remains on the same message/operation identity for canonical reconciliation.
