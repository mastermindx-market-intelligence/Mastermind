# OHF-P1A — Durable identity and schema proposal

**Date:** 2026-08-16
**Status:** proposal only. Do not apply a migration in this PR.
**Runtime census from:** `control_plane/executive_runtime.py` on master
`da6bd78e078b96db8c121b16f1b10e3fd70e6fef` (`SCHEMA_VERSION = 2`).

This file does not create `harness.sqlite`, a second queue, or a second lease
DB. All durable OHF state must fit Executive runtime.

## 1. Current runtime census

### 1.1 Schema

`SCHEMA_VERSION = 2` at `control_plane/executive_runtime.py:38`.

Tables: `workers`, `worker_quota_classes`, `jobs`, `attempts`, `events`,
`schema_migrations`.

No `harness_sessions`, `process_generations`, or `execution_profile` tables.

### 1.2 Attempt fields relevant to OHF

From current DDL: `attempt_id`, `job_id`, `attempt_number`, `worker_id`,
`quota_class`, `status`, `fence_generation`, `authority_policy_hash`,
`lease_token`, `lease_owner`, `lease_expires_at_ms`, `heartbeat_at_ms`,
`checkpoint_sequence`, `checkpoint_json`, `result_json`, `error_json`,
**`pid`, `pgid`, `process_start_identity`, `boot_id`, `provider_session_id`**,
stdout/stderr/result paths, `exit_code`, `launch_metadata_json`.

**No `host_id`.** Current process identity is all-or-nothing local
`(pid, pgid, process_start_identity, boot_id)` or else `provider_session_id`.

AttemptStatus: CLAIMED, RUNNING, CHECKPOINTED, CANCEL_REQUESTED, RATE_LIMITED,
FAILED, LOST, COMPLETED, CANCELLED.

### 1.3 Lease / fence

Not a separate table. Claim does `BEGIN IMMEDIATE`, increments
`worker_quota_classes.fence_counter`, stores it as `attempts.fence_generation`,
issues `lease_token`. Mutations require fence match + token compare.
`adopt_attempt` CAS-bumps fence and token (supervisor restart).
Fence counter does not decrement on release.

This is the pattern OHF writer fencing must reuse, not replace.

### 1.4 Events

Append-only, immutable triggers, unique `command_id`, per-aggregate sequence.
Tokens never in payloads.

### 1.5 Worker / account / quota

`workers.account_label` is the account identity. Quota class holds provider,
model, effort, cost_class, capabilities_json, held_attempt_id, fence_counter.
No generic provider-horizon table — and P1A does not add 5h/weekly/monthly
columns.

### 1.6 Backup / restore

`control_plane/executive_backup.py` copies the whole SQLite via
`Connection.backup()`. Verification is migration-exact (`schema_migrations`
checksums + `runtime_schema_version`). Adding a migration changes the contract:
old backups fail against new code until regenerated. No business-table
allowlist — unknown tables after a migrated backup are included automatically.

### 1.7 Census: reuse / extend / new

| Need | Existing | Decision |
|---|---|---|
| Job / Attempt / authority / workspace | `jobs`, `attempts` | reuse |
| Current process cache | `attempts.pid/pgid/boot_id/start_identity` | extend meaning: **current generation only** |
| Native thread id | `attempts.provider_session_id` | extend: store primary native session id here; realm is worker provider+account |
| Lease of Executive Attempt | existing fence/token | reuse; do not conflate with harness writer fence |
| Harness writer history | none | **new table** `process_generations` |
| ExecutionProfile | none | **extend Attempt** with immutable JSON + digest columns |
| Primary HarnessSession row | none | **no extra table in V1** (1:1 with Attempt) |
| Native forks | none | **JSON + events** on Attempt, not Jobs |
| Ambient allowlist | none | Git-backed policy, not SQLite rows per skill |
| Quota horizons | none | event payload, not schema columns |

Why no `harness_sessions` table: P1A freezes 1 Attempt : 1 primary
HarnessSession. A second table would duplicate Attempt identity until design B
is proven. If a later commission reverses cardinality, that is the moment to
add the table — not now.

## 2. Proposed additive migration (NOT APPLIED)

Next version would be `SCHEMA_VERSION = 3` named
`ohf_process_generations_and_profile_snapshot`.

### 2.1 Attempt extensions

```sql
ALTER TABLE attempts ADD COLUMN native_session_id TEXT;
ALTER TABLE attempts ADD COLUMN harness_kind TEXT;
ALTER TABLE attempts ADD COLUMN harness_version TEXT;
ALTER TABLE attempts ADD COLUMN execution_profile_digest TEXT;
ALTER TABLE attempts ADD COLUMN execution_profile_json TEXT;
ALTER TABLE attempts ADD COLUMN writer_generation_id TEXT;
ALTER TABLE attempts ADD COLUMN harness_recovery_class TEXT;
ALTER TABLE attempts ADD COLUMN native_subordinates_json TEXT;
```

Immutability: `execution_profile_json` / digest may be written once while
CLAIMED/RUNNING start, then CHECK-constrained against updates (trigger
mirroring `events` immutability, or service gate). Native session id is
immutable once recorded.

`provider_session_id` may remain as a synonym during transition; do not store
two different native ids.

### 2.2 `process_generations`

```sql
CREATE TABLE process_generations (
  process_generation_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  native_session_id TEXT NOT NULL,
  generation_number INTEGER NOT NULL CHECK (generation_number >= 1),
  host_id TEXT,
  pid INTEGER,
  pgid INTEGER,
  process_start_identity TEXT,
  boot_id TEXT,
  started_at_ms INTEGER NOT NULL,
  last_observed_at_ms INTEGER,
  ended_at_ms INTEGER,
  termination_class TEXT,
  exit_code INTEGER,
  resume_intent TEXT,
  resume_result TEXT,
  recovery_class TEXT,
  runtime_metadata_json TEXT,
  created_at_ms INTEGER NOT NULL,
  UNIQUE (attempt_id, generation_number)
);
```

Indexes:

- `(native_session_id)`
- partial unique: one open writer
  `UNIQUE(native_session_id) WHERE ended_at_ms IS NULL`
  (SQLite partial unique index)

Generation numbers cannot regress because of the unique `(attempt_id,
generation_number)` plus service gate `MAX+1`.

### 2.3 What stays off the schema

- Recovery conceptual states NEW/PREPARING/STARTING/ACTIVE as extra Attempt enums
- Browser/devserver leases
- Capacity/account pool tables
- Raw credential-bearing provider payloads
- Per-horizon quota columns

## 3. Invariants

| Invariant | SQLite | Service gate |
|---|---|---|
| One primary native session cannot belong to two active Attempts | partial unique on `attempts.native_session_id` where status in active set | also check at `start_session` |
| One HarnessSession has at most one current Executive writer generation | partial unique on open `process_generations.native_session_id` | acquire path |
| Generation numbers cannot regress | UNIQUE(attempt_id, generation_number) | insert uses MAX+1 |
| Native session identity immutable | UPDATE trigger | start_session only |
| Provider/account/harness realm cannot silently change | profile digest stored; worker_id FK | drift matrix refuses in-Attempt change |
| ExecutionProfile historically immutable | UPDATE trigger on digest/json | |
| Process generation cannot outlive terminal HarnessSession incorrectly | FK attempt_id; terminal Attempt must end open generations in the same txn | `_terminal` |
| FKs survive backup/restore | ordinary SQLite FKs; whole-DB backup | restore verify migrations |
| Legacy Jobs/Attempts remain valid | new columns NULL-ok | sealed workers ignore them |

Where SQLite is not enough: writer-safe resume after SIGKILL is a **service**
decision (RECOVERY_BLOCKED_ACTIVE_WRITER). Do not encode "steal" in SQL.

## 4. Migration / rollback

- Additive only. Default NULL for historical rows.
- Sealed `WorkerExecutionAdapter` path ignores new columns.
- Deactivation: stop writing generations; old columns remain; no drop in the
  same release.
- Backup: after apply, regenerate executive backup manifests so
  `runtime_schema_version=3` checksums match.
- Do not apply in P1A.

## 5. Host identity

P0/P1A did not persist `host_id`. The generation table includes a nullable
`host_id` so multi-host later does not require another cardinality fight.
V1 single-host may store hostname hash, not credentials.
