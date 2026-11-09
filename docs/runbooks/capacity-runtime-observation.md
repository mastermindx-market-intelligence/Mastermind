# Recorded Runtime workload in Capacity observations

The existing `executive_wake_reconcile.py --observe-only` report now includes
`capacity_observation.runtime_workload`. Its optional retained receipt and
offline collection report carry that same object without pooling repeated
snapshots into a fictitious campaign population.

The consumer uses exactly one `Runtime.bounded_acquisition()` snapshot and at
most two SQL-bounded owner pages: up to 128 Jobs and 512 Attempts belonging to
those selected Jobs. It never calls the unbounded history APIs, adds a query
surface, changes schema or writes Runtime state. Overflow remains explicit
partial coverage; read failure remains unavailable and makes the observation
return 2. The existing SQLite reader-bookkeeping caveat is unchanged.

The projection reports observed Job/Attempt status counts, explicit review-slot
and review-required Job counts, plus each Job's recorded creation-to-first-claim
interval. `Attempt.started_at` is set by the existing claim transaction, so this
interval includes admission, dependency and scheduled waiting. It is **not**
ready-queue service time, provider/model reasoning duration, worker execution
time or desktop occupancy. Retries retain the original first claim; unclaimed
Jobs are unfinished, missing or inconsistent records are unavailable, and an
empty population has no invented zero latency. Percentiles use only completed
recorded samples and retain the population/unfinished/unavailable counts.
The public Runtime serializer retains whole seconds. Values are expressed in
milliseconds with an explicit 1000 ms source resolution; the consumer does not
recover or invent subsecond precision from the underlying database.

These rows are unclassified and may include proof or acceptance Jobs. No
objective-name heuristic turns them into ordinary/busy demand, and no raw
objective, result, account, credential or lease token is returned. A complete
bounded pair of pages is not proof of the company's complete demand population.
The workload snapshot is internally consistent but separate from the Wake and
Agent OS reads. Its digest binds only the selected recorded metadata.

The report still claims neither an installed source/Runtime attestation nor a
qualified seven-day campaign. Existing source-only fixtures, a week of recorded
timestamps, zero observations and proof Jobs cannot change those flags. Actual
model/desktop consumption, cost, original-parent disposition and installed
coverage retain their existing unavailable semantics. Capacity economic
previews are not actual spend. Installed peer identity requires the existing
kernel/launchd qualification owner; this observer does not replace that owner.

This is a follow-on data join to the receipt collector, not a scheduler,
campaign registry, worker admission or new acceptance gate.
