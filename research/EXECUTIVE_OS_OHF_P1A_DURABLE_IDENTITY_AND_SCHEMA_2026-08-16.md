# OHF-P1A-R3 — Durable identity and schema proposal

**Date:** 2026-08-18
**Status:** proposal only. Do not apply a migration in this PR.
**Runtime census from:** `control_plane/executive_runtime.py` (`SCHEMA_VERSION = 2`)
**Typed freeze:** `control_plane/operator_harness_contract.py`

This file does not create `harness.sqlite`, a second queue, a second lease DB,
or an operation sidecar table. All durable OHF state must fit Executive runtime
(`attempts`, `harness_session_epochs`, `process_generations`, `events`).

P1A-R1 omitted a session table because it froze Attempt 1:1 HarnessSession.
Independent review adopted CARDINALITY_B. A minimal `harness_session_epochs`
table remains justified. R3 changes the Attempt extension: legacy
process/session columns stay sealed-worker-only, and current-epoch /
current-generation Attempt pointers are not added.

## 1. Current runtime census

Unchanged from schema v2:

Tables: `workers`, `worker_quota_classes`, `jobs`, `attempts`, `events`,
`schema_migrations`.

Attempt already has `pid`, `pgid`, `process_start_identity`, `boot_id`,
`provider_session_id`. Those fields are write-once for sealed workers
(`record_process` COALESCE / already-set conflict). AttemptStatus set is
unchanged: CLAIMED, RUNNING, CHECKPOINTED, CANCEL_REQUESTED, RATE_LIMITED,
FAILED, LOST, COMPLETED, CANCELLED. P1A adds **no** new AttemptStatus.

`workers.account_label` is not unique and is not an auth realm.

`adopt_attempt` rotates lease/fence only. It does not reclaim stdio.

Backup/restore copies the whole SQLite offline. Restore does not match live
OS processes or provider sessions.

`events.command_id TEXT NOT NULL UNIQUE` and
`find_event_by_command_id(command_id)` are the durable OperationId mechanism.

## 2. Canonical owners

| Fact | Canonical | Duplicate rule |
|---|---|---|
| execution mode | `attempts.execution_mode` | immutable; historical NULL ⇒ SEALED_WORKER |
| provider session identity (OHF) | `harness_session_epochs.provider_session_id` | generation copy is index projection, same transaction |
| provider session identity (sealed) | `attempts.provider_session_id` | LEGACY_ONLY; OHF must not rewrite |
| session epoch state | `harness_session_epochs.state` | CURRENT uniquely derivable; no Attempt pointer |
| current ProcessGeneration | generation with `executive_writer_held=1` | no Attempt pointer |
| process identity (OHF) | `process_generations` pid/pgid/start/boot | `attempts.pid*` remain LEGACY_ONLY |
| process liveness | generation pid/start/boot + `ended_at_ms` | never `ended_at IS NULL` as writer fence |
| Executive writer ownership | `process_generations.executive_writer_held` | pre-bind unique on `session_epoch_id`; post-bind unique on realm |
| provider writer observation | `process_generations.provider_writer_state` | never invent RELEASED; restore must not rewrite |
| requested profile | `attempts.requested_execution_profile_json` + digest | no mixed blob |
| observed attestation | `process_generations.observed_attestation_json` + digest | per generation |
| workspace identity | existing workspace receipt (inode/device/uid/gid + base SHA) | cwd string is not identity |
| OperationId | `events.command_id` of INTENT | derived receipts share `aggregate_id` |
| recovery state | generation-scoped writer/liveness/provider fields | no Attempt `harness_recovery_class` |

Forbidden synonym: `native_session_id`.

Postponed (not in v3): `native_subordinates_json`, `host_id` /
hostname-hash, `runtime_metadata_json`, Attempt `current_session_epoch_id`,
Attempt `current_process_generation_id`. Native forks live in typed events.

## 3. Proposed additive migration (NOT APPLIED)

Next version would be `SCHEMA_VERSION = 3` named
`ohf_session_epochs_and_process_generations`.

### 3.1 Attempt extensions

```sql
ALTER TABLE attempts ADD COLUMN execution_mode TEXT
  CHECK (execution_mode IN ('SEALED_WORKER','OPERATOR_HARNESS'));
ALTER TABLE attempts ADD COLUMN requested_execution_profile_json TEXT;
ALTER TABLE attempts ADD COLUMN requested_execution_profile_digest TEXT;
```

No `native_session_id`. No mixed `execution_profile_json`. No
`harness_recovery_class`. No `native_subordinates_json`. No
`current_session_epoch_id`. No `current_process_generation_id`.
`harness_kind` / `harness_version` stay inside requested JSON.

`attempts.provider_session_id`, `pid`, `pgid`, `process_start_identity`, and
`boot_id` stay as they are. Sealed workers continue to use them as today.
Rich OHF must not rewrite them. Historical NULL `execution_mode` interprets as
`SEALED_WORKER`. Mode cannot change in place (trigger or service gate).

Requested profile JSON/digest are write-once after seal. NULL on
historical/sealed rows is valid, not corruption.

### 3.2 `harness_session_epochs`

```sql
CREATE TABLE harness_session_epochs (
  session_epoch_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  worker_id TEXT NOT NULL,                 -- INDEX PROJECTION of attempts.worker_id
  epoch_number INTEGER NOT NULL CHECK (epoch_number >= 1),
  provider_session_id TEXT,                -- CANONICAL; NULL until TX-3 bind
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

Rules:

- `provider_session_id` NULL until TX-3; UPDATE trigger refuses change once non-null.
- `ABANDONED` / `TERMINAL` cannot return to `CURRENT`.
- Cross-Attempt reuse of `(worker_id, provider_session_id)` is refused for the
  lifetime of that worker slot.
- Different workers may share an opaque provider session id.
- `worker_id` must equal `attempts.worker_id` (BEGIN IMMEDIATE service gate).

### 3.3 `process_generations`

```sql
CREATE TABLE process_generations (
  process_generation_id TEXT PRIMARY KEY,
  session_epoch_id TEXT NOT NULL
    REFERENCES harness_session_epochs(session_epoch_id),
  worker_id TEXT NOT NULL,                 -- INDEX PROJECTION
  provider_session_id TEXT,                -- INDEX PROJECTION
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
  observed_attestation_json TEXT,
  observed_attestation_digest TEXT,
  created_at_ms INTEGER NOT NULL,
  UNIQUE (session_epoch_id, generation_number)
);

CREATE UNIQUE INDEX process_generations_one_epoch_writer
  ON process_generations(session_epoch_id)
  WHERE executive_writer_held = 1;

CREATE UNIQUE INDEX process_generations_one_executive_writer
  ON process_generations(worker_id, provider_session_id)
  WHERE executive_writer_held = 1 AND provider_session_id IS NOT NULL;
```

`ended_at_ms` is process-death observation only. The writer fence is
`executive_writer_held`, not `ended_at_ms IS NULL`.

`worker_id` and `provider_session_id` on the generation are index projections.
Once the epoch is bound, `generation.provider_session_id` must equal
`epoch.provider_session_id` in the same transaction. Mismatch is corruption.

No `host_id`. `boot_id` is host-local process identity, sufficient for
single-host V1.

Do not persist `resume_safe` as independent truth.

### 3.4 Operation events (existing Event plane)

```text
aggregate_type = 'operator_operation'
aggregate_id   = OperationId.command_id
INTENT command_id = OperationId.command_id          -- ohf-op:…
APPLIED / REFUSED / EFFECT_UNKNOWN / RECONCILED
  command_id = '{OperationId}:{suffix}'
```

No `operator_operations` table.

## 4. Atomic transaction groups

Canonical copy: `TRANSACTION_GROUPS` in the typed contract.

| TX | Atomic writes | Before external call? |
|---|---|---|
| TX-1 | execution_mode, requested profile JSON+digest, seal receipt | yes — no provider call |
| TX-2 | allocate epoch+generation, CURRENT epoch with NULL session, writer held, INTENT | yes |
| TX-3 | bind provider_session_id, process identity, index projections, APPLIED | after start observation |
| TX-4 | observed attestation JSON+digest | after initialize; before work turn |
| TX-5 | allocate TurnRef, BEGIN_TURN INTENT | yes; APPLIED after ack |
| TX-6 | generation ended, historical provider writer, clear held | after confirmed graceful stop |
| TX-7 | process death observation; held remains; provider not RELEASED | n/a |
| TX-8 | epoch ABANDONED, clear held, preserve provider writer | only if process PROVEN_DEAD |
| TX-9 | OHF Attempts LOST, CURRENT epochs ABANDONED, held cleared, history untouched | before service re-enable |

Context rotation: TX marks old CURRENT TERMINAL, optionally inserts the next
CURRENT epoch without a writer if launch is deferred. Crash between TX-8 and
E2 creation leaves Attempt active, no CURRENT epoch, no writer — recoverable.

## 5. Adversarial schema walks

| Attack | Answer | Site |
|---|---|---|
| Two CURRENT epochs on one Attempt | unique index `harness_session_epochs_one_current` | SQL index |
| Reopen ABANDONED epoch | state trigger/service gate; resume_safety false | SQL trigger + comparator |
| Mutate provider_session_id after first assignment | UPDATE trigger | SQL trigger |
| Two Executive writers before S1 exists | unique index `process_generations_one_epoch_writer` | SQL index |
| Two Executive writers on W1/S1 | unique index `process_generations_one_executive_writer` | SQL index |
| W1/`abc` and W2/`abc` | legal; realm includes worker_id | SQL index |
| Process dies, writer remains | `ended_at_ms` set; `executive_writer_held=1`; provider UNKNOWN/HELD | TX-7 |
| UNKNOWN process + UNKNOWN effect, start E2 | refused until process absence proven; else Attempt LOST | supervisor |
| Terminal Attempt, provider UNKNOWN | allowed; held cleared; provider stays UNKNOWN | TX-8 / terminalize |
| Restore of active snapshot | TX-9: held=0, epochs ABANDONED, Attempt LOST; historical provider fields unchanged | BEGIN IMMEDIATE |
| Legacy Attempt with no epoch rows | valid SEALED_WORKER Attempt; missing OHF state is not corruption | discriminator |
| Sealed adapter beside OHF data | sealed path ignores epoch tables; must not write them; must not call OHF `record_process` rotation | runtime branch |
| Rich OHF rewrites attempts.pid / provider_session_id | forbidden; LEGACY_ONLY | BEGIN IMMEDIATE |
| Adapter mints epoch/generation/turn ids | forbidden; Executive allocates in TX-2/TX-5 | contract + TX |

## 6. Writer constraint cases

1. Same opaque id, different workers: both may exist.
2. Pre-bind: two generations with `executive_writer_held=1` on the same
   `session_epoch_id` are refused even while `provider_session_id` is NULL.
3. Fresh S2 while abandoned S1 is unresolved: S1 epoch ABANDONED, held=0,
   provider maybe HELD; S2 different `provider_session_id`; unique writer
   indexes allow S2 after process PROVEN_DEAD.
4. Duplicate writer same realm: second generation with `executive_writer_held=1`
   for W1/S1 is refused even if the first process is dead.

## 7. Restore law (source law)

Option A: backups may capture active OHF history. Restore never restores live
execution authority over external processes or provider sessions.

After restore of an active snapshot, **before re-enable** (TX-9):

- historical process observation stays evidence
- historical `provider_writer_state` stays byte-for-byte, including RELEASED
- `executive_writer_held` forced to 0
- current epochs become ABANDONED / nonresumable
- OPERATOR_HARNESS Attempt status becomes existing **LOST** (not a new enum)
- continuation only via a new lawful Attempt from last trusted checkpoint

Safety comes from ABANDONED + no Executive writer + LOST Attempt, not from
corrupting evidence into UNKNOWN.

## 8. Legacy compatibility

Historical/sealed Attempts remain valid with NULL OHF columns and zero epoch
rows. `execution_mode` NULL/SEALED_WORKER selects the existing identity path.
Missing OHF state is not corruption.

Sealed `WorkerExecutionAdapter` ignores new tables and keeps
`record_process` / `record_process_exit` semantics. Rich OHF does not call
those as generation rotation.

`adopt_attempt()` for OPERATOR_HARNESS uses epoch/generation/operation
receipts, not `attempts.pid` / `attempts.provider_session_id`.

## 9. Rollback wording

Feature disable: stop writing OHF tables. Not old-binary rollback.
Old binary that requires schema 2 must refuse schema 3.
DB restore: §7.
Forward-fix: the supported escape.
Migration rollback: not promised.

## 10. What stays off the schema

- Browser/devserver leases
- Capacity/account pool tables
- Raw credential payloads
- Per-horizon quota columns
- Native subordinate JSON
- Hostname-hash host identity
- Kitchen-sink runtime_metadata_json
- New AttemptStatus values for harness facts
- Attempt current-epoch / current-generation pointers
- operator_operations sidecar table
