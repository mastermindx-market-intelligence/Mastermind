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

## Project tracking

The existing bounded Fabric view joins each descendant through its immediate
coordinator while retaining the original Event-backed workstream root. Planner
identity is unique within each coordinator, so planners in separate delegated
branches remain visible together. Work, review, and repair relationships stay
within that coordinator's plan; identical local step names do not join across
branches.

The view validates the retained ancestry and inherited grants, including all
completed descendants. It does not reopen admission or require a coordinator to
remain queued. A missing parent, invalid grant, or over-budget subtree remains
explicitly unjoined; truncation remains partial. The original 17-Job acquisition
budget, Attempt limits, observation receipt, authorization, and canonical result
reader remain unchanged. A tracking card does not itself accept a result or
prove live provider readiness.

## Schema and rollout

New stores use schema v7. The migration history remains ordered: v6 adds
coordinator-scoped uniqueness/lineage constraints; v7 adds the reviewed physical
resource tables and event constraints. Versions 1-5 and the original hierarchy
v6 identity remain unchanged. Existing stores are never migrated by opening
them.

Use the existing stopped and quiesced service maintenance path and an installed
release qualified for the composed schema. Each invocation performs exactly one
closed transition. First, an exact v5 store can receive hierarchy v6:

```sh
python3 scripts/executive_os_migrate.py --from-version 5 \
  --database /absolute/path/to/executive.sqlite3 \
  --backup-directory /absolute/path/to/backups \
  --release-sha <installed-release-sha>
```

After verifying the v5-to-v6 completion receipt and exact v6 source/backup
proof, the same stopped service can receive physical schema v7:

```sh
python3 scripts/executive_os_migrate.py --transition v6-to-v7 \
  --database /absolute/path/to/executive.sqlite3 \
  --backup-directory /absolute/path/to/backups \
  --release-sha <installed-release-sha>
```

Each transition performs verified source/target backups and restore drills, an
exclusive transaction, and its own completion receipt. The physical transition
preserves all existing rows and migration timestamps 1-6, starts the physical
tables empty, and rejects preexisting physical events. The v6 fingerprint is
`4ed21db1880afe43bdab58ea07da335c2db60a218ccdedee44eaefd1d2175c05`;
the composed v7 fingerprint is
`7692d62bd4126dd6fcaec2873ee9506a1faac96b3246684366e1dfa6e34c6a87`. It retains quarantine on uncertain
post-commit failure. `--from-version 3` (the legacy default) and `4` upgrade one
version only; do not chain upgrades around an unresolved result.

The automated tests use inert Runtime/OHF fixtures. They prove source behavior,
including completion and restart, but do not prove an installed provider round
trip or native Codex tool availability. Live deployment and an original-parent
return must be verified separately through the existing installed owners.
