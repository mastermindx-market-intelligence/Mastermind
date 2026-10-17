# Bounded coordinator hierarchy

Execution plan v5 lets the existing COO cycle coordinate up to four levels:
root (depth 0), coordinator (depth 1), coordinator (depth 2), workers (depth 3).
The original root has **16 total descendant Job slots**. Every planner,
coordinator, work, review, and repair Job consumes that same allowance, including
retained terminal Jobs. Creating a coordinator does not create a new allowance.
Native Codex's configured concurrent-child ceiling is a separate host setting.

## Plan and reservation

The public planner schema defaults to the frozen V1 wire and eight-step limit.
Trusted callers may select `orchestration_result_schema("plan",
plan_schema_version="mastermind.execution_plan/v5")` and obtain its distinct
digest through `role_schema_digest` with the same selector. V3/V4 retain their
existing closed schemas. Schema selection does not change a native helper's
contract, select an adapter, or admit a live Runtime Attempt; those bindings
must be supplied by the existing version-aware host composition. Default native
V1 handshakes remain unchanged.

Use `mastermind.execution_plan/v5` with `root_job_id` equal to the original root
and `coordinator_job_id` equal to the coordinator whose planner produced the plan.
Each step retains v4 routing and dependency fields and adds `delegation`:

- A leaf uses `"delegation": null`.
- A coordinator uses `"delegation": {"descendant_limit": 8, "max_depth": 3}`.
  Its grant is smaller than its parent's and includes its own planner and all
  descendants. `max_depth` is absolute, not relative. Coordinator steps use
  `review_required: false`; their aggregate requires accepted scoped children.
  Material leaf work still requires its reserved independent review capacity.

Admission atomically reserves one planner slot plus every step's complete
allowance. A coordinator step costs one Job plus its delegated descendant limit.
A reviewed leaf reserves the existing review/repair allowance. An oversubscribed
plan creates no partial batch. An admitted v5 plan has admission wire v3; old
plans v1-v4 retain their original policy and reservation wire.

For example, a root planner plus a coordinator with allowance 14 consumes all 16
root slots. That coordinator can reserve its planner plus another coordinator
with allowance 12. The latter can reserve its planner and eleven leaf workers.
This is four useful levels with 16 descendants in total, not 16 at every branch.

Model selection remains with existing routing and capacity. A plan may choose
Sol or Astra using v4/v5 `placement.model` within an already admitted pool; an
unavailable model produces no capacity. Planner routing options v2 expose the
immediate coordinator and inherited hierarchy grant without account or host
identities. Routine work should prefer the existing economical Fabric route.

## Lifecycle and returns

Call the existing `CooCycle.run_once(original_root_id)` repeatedly through its
current owner. It descends into admitted coordinators; no separate scheduler or
new operation root is introduced. Commands use the immediate coordinator scope.
Jobs, result envelopes, admission v3, aggregation handoff v2, and aggregation
result v2 preserve the original root and distinguish the local coordinator.

Parent cancellation stops new descendants at the same transaction boundary as
creation. Existing attempts retain their original settlement paths. Uncertain
returns reconcile the same command and Attempt; they are never reissued under
another root or ID. Unrelated reserved read-only branches may progress.
Aggregation waits for all transitive descendants and unresolved dispatch-return
markers before producing its immutable handoff.

## Schema and rollout

New stores use schema v6. Existing v5 stores are never migrated by opening them.
The explicit upgrade adds coordinator-scoped uniqueness/lineage constraints and
preserves all existing rows and migration receipts. Use the existing stopped and
quiesced service maintenance path, then run the installed release's command:

```sh
python3 scripts/executive_os_migrate.py --from-version 5 \
  --database /absolute/path/to/executive.sqlite3 \
  --backup-directory /absolute/path/to/backups \
  --release-sha <installed-release-sha>
```

This performs verified source/target backups and restore drills, an exclusive
transaction, and a completion receipt. It retains quarantine on uncertain
post-commit failure. `--from-version 3` (the legacy default) and `4` upgrade one
version only; do not chain upgrades around an unresolved result.

The automated tests use inert Runtime/OHF fixtures. They prove source behavior,
including completion and restart, but do not prove an installed provider round
trip or native Codex tool availability. Live deployment and an original-parent
return must be verified separately through the existing installed owners.
