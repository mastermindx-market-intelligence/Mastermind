# OHF-P1A-R2 — Durable identity and schema proposal

**Date:** 2026-08-16
**Status:** proposal only. Do not apply a migration in this PR.
**Runtime census from:** `control_plane/executive_runtime.py` (`SCHEMA_VERSION = 2`)
**Typed freeze:** `control_plane/operator_harness_contract.py`

This file does not create `harness.sqlite`, a second queue, or a second lease
DB. All durable OHF state must fit Executive runtime.

P1A-R1 proposed Attempt 1:1 HarnessSession and therefore omitted a session
table. Independent review adopted CARDINALITY_B. A minimal
`harness_session_epochs` table is now justified because restart correctness
requires 1:N sequential primary sessions, one current epoch, historical
`provider_session_id`, abandoned/nonresumable epochs, and ProcessGeneration
ownership without incrementing `attempt_count`.

## 1. Current runtime census

Unchanged from schema v2:

Tables: `workers`, `worker_quota_classes`, `jobs`, `attempts`, `events`,
`schema_migrations`.

Attempt already has `pid`, `pgid`, `process_start_identity`, `boot_id`,
`provider_session_id`. AttemptStatus set is unchanged: CLAIMED, RUNNING,
CHECKPOINTED, CANCEL_REQUESTED, RATE_LIMITED, FAILED, LOST, COMPLETED,
CANCELLED. P1A adds **no** new AttemptStatus.

`workers.account_label` is not unique and is not an auth realm.

`adopt_attempt` rotates lease/fence only. It does not reclaim stdio.

Backup/restore copies the whole SQLite offline. Restore does not match live
OS processes or provider sessions.

## 2. Canonical owners

| Fact | Canonical | Duplicate rule |
|---|---|---|
| provider session identity | `harness_session_epochs.provider_session_id` for rich OHF | `attempts.provider_session_id` is same-txn projection of current epoch, or legacy sealed-worker field when no epoch rows exist |
| session epoch state | `harness_session_epochs.state` | none |
| current ProcessGeneration | generation with `executive_writer_held=1` for the current epoch | `attempts.pid/pgid/start/boot` projection for rich OHF |
| process liveness | generation pid/start/boot + `ended_at_ms` | Attempt pid cache must not be independently authoritative |
| Executive writer ownership | `process_generations.executive_writer_held` | do not derive from `ended_at_ms IS NULL` |
| provider writer observation | `process_generations.provider_writer_state` | never invent RELEASED |
| requested profile | `attempts.requested_execution_profile_json` + digest | no mixed blob |
| observed attestation | `process_generations.observed_attestation_json` + digest | per generation |
| workspace identity | existing workspace receipt (inode/device/uid/gid + base SHA) | cwd string is not identity |
| recovery state | generation-scoped writer/liveness/provider fields | no Attempt `harness_recovery_class` |

Forbidden synonym: `native_session_id`.

Postponed (not in v3): `native_subordinates_json`, `host_id` /
hostname-hash, `runtime_metadata_json`. Future host realm may be added without
redefining Attempt/epoch/generation. Native forks live in typed events.

## 3. Proposed additive migration (NOT APPLIED)

Next version would be `SCHEMA_VERSION = 3` named
`ohf_session_epochs_and_process_generations`.

### 3.1 Attempt extensions

```sql
ALTER TABLE attempts ADD COLUMN requested_execution_profile_json TEXT;
ALTER TABLE attempts ADD COLUMN requested_execution_profile_digest TEXT;
ALTER TABLE attempts ADD COLUMN current_session_epoch_id TEXT;
ALTER TABLE attempts ADD COLUMN current_process_generation_id TEXT;
```

No `native_session_id`. No `execution_profile_json` mixed blob. No
`harness_recovery_class`. No `native_subordinates_json`.
`harness_kind` / `harness_version` are inside requested JSON, not extra
canonical columns.

`provider_session_id` stays. Sealed workers continue to use it as today.
Rich OHF maintains it as a projection of the current epoch in the same
transaction. Mismatch is corruption and must fail closed.

Requested profile JSON/digest are write-once after seal (trigger or service
gate). NULL on historical/sealed rows is valid, not corruption.

### 3.2 `harness_session_epochs`

```sql
CREATE TABLE harness_session_epochs (
  session_epoch_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  worker_id TEXT NOT NULL,
  epoch_number INTEGER NOT NULL CHECK (epoch_number >= 1),
  provider_session_id TEXT,
  state TEXT NOT NULL CHECK (state IN ('CURRENT','TERMINAL','ABANDONED')),
  created_at_ms INTEGER NOT NULL,
  ended_at_ms INTEGER,
  abandonment_class TEXT,
  UNIQUE (attempt_id, epoch_number)
);

CREATE UNIQUE INDEX harness_session_epochs_one_current
  ON harness_session_epochs(attempt_id)
  WHERE state = 'CURRENT';

CREATE UNIQUE INDEX harness_session_epochs_session_realm
  ON harness_session_epochs(worker_id, provider_session_id)
  WHERE provider_session_id IS NOT NULL;
```

`worker_id` on the epoch row is a same-transaction copy of `attempts.worker_id`
so the unique index can include the realm. Attempt remains canonical placement.

Rules:

- `provider_session_id` NULL until creation completes; UPDATE trigger refuses
  change once non-null.
- `ABANDONED` / `TERMINAL` cannot return to `CURRENT`.
- Cross-Attempt reuse of a `(worker_id, provider_session_id)` is refused by
  `harness_session_epochs_session_realm` for the lifetime of that worker slot.
- Different workers may share an opaque provider session id.

### 3.3 `process_generations`

```sql
CREATE TABLE process_generations (
  process_generation_id TEXT PRIMARY KEY,
  session_epoch_id TEXT NOT NULL
    REFERENCES harness_session_epochs(session_epoch_id),
  worker_id TEXT NOT NULL,
  provider_session_id TEXT,
  generation_number INTEGER NOT NULL CHECK (generation_number >= 1),
  pid INTEGER,
  pgid INTEGER,
  process_start_identity TEXT,
  boot_id TEXT,
  started_at_ms INTEGER NOT NULL,
  last_observed_at_ms INTEGER,
  ended_at_ms INTEGER,
  termination_class TEXT,
  exit_code INTEGER,
  executive_writer_held INTEGER NOT NULL CHECK (executive_writer_held IN (0,1)),
  provider_writer_state TEXT NOT NULL
    CHECK (provider_writer_state IN ('HELD','RELEASED','UNKNOWN')),
  resume_result TEXT,
  reconciliation_result TEXT,
  observed_attestation_json TEXT,
  observed_attestation_digest TEXT,
  created_at_ms INTEGER NOT NULL,
  UNIQUE (session_epoch_id, generation_number)
);

CREATE UNIQUE INDEX process_generations_one_executive_writer
  ON process_generations(worker_id, provider_session_id)
  WHERE executive_writer_held = 1 AND provider_session_id IS NOT NULL;
```

`ended_at_ms` is process-death observation only. The writer fence is
`executive_writer_held`, not `ended_at_ms IS NULL`.

`worker_id` and `provider_session_id` on the generation are same-transaction
copies used by the unique index. Canonical session id remains the epoch row.

No `host_id`. `boot_id` is host-local process identity, sufficient for
single-host V1.

## 4. Adversarial schema walks

| Attack | Answer |
|---|---|
| Two CURRENT epochs on one Attempt | unique index `harness_session_epochs_one_current` |
| Reopen ABANDONED epoch | state trigger/service gate; resume_safety false |
| Mutate provider_session_id after first assignment | UPDATE trigger |
| Two Executive writers on W1/S1 | unique index `process_generations_one_executive_writer` |
| W1/`abc` and W2/`abc` | legal; realm includes worker_id |
| Process dies, writer remains | `ended_at_ms` set; `executive_writer_held=1`; provider UNKNOWN/HELD |
| Terminal Attempt, provider UNKNOWN | allowed; held cleared; provider stays UNKNOWN |
| Restore of active snapshot | invalidate held; abandon current epochs; Attempt LOST; do not resume ids |
| Legacy Attempt with no epoch rows | valid sealed-worker Attempt; missing OHF state is not corruption |
| Sealed adapter beside OHF data | sealed path ignores epoch tables; must not write them |

## 5. Writer constraint cases

1. Same opaque id, different workers: both may exist.
2. Fresh S2 while abandoned S1 is unresolved: S1 epoch ABANDONED, held=0,
   provider maybe HELD; S2 different `provider_session_id`; unique writer index
   allows S2.
3. Duplicate writer same realm: second generation with `executive_writer_held=1`
   for W1/S1 is refused even if the first process is dead.

## 6. Restore law (source law)

Option A: backups may capture active OHF history. Restore never restores live
execution authority over external processes or provider sessions.

After restore of an active snapshot:

- old ProcessGeneration is not live (`process liveness = UNKNOWN`)
- `executive_writer_held` forced to 0
- provider_writer_state is not set to RELEASED
- current epochs become ABANDONED / nonresumable
- Attempt status becomes existing **LOST** (not a new enum)
- continuation only via a new lawful Attempt from last trusted checkpoint

## 7. Legacy compatibility

Historical/sealed Attempts remain valid with NULL OHF columns and zero epoch
rows. The future runtime must distinguish legacy/sealed Attempts from rich OHF
Attempts. Missing OHF state is not corruption.

Sealed `WorkerExecutionAdapter` ignores new tables.

## 8. Rollback wording

Feature disable: stop writing OHF tables. Not old-binary rollback.
Old binary that requires schema 2 must refuse schema 3.
DB restore: §6.
Forward-fix: the supported escape.
Migration rollback: not promised.

## 9. What stays off the schema

- Browser/devserver leases
- Capacity/account pool tables
- Raw credential payloads
- Per-horizon quota columns
- Native subordinate JSON
- Hostname-hash host identity
- Kitchen-sink runtime_metadata_json
- New AttemptStatus values for harness facts
