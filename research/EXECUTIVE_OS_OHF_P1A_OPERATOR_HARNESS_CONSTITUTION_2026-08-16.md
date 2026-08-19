# OHF-P1A-R3 — Operator Harness Constitution

**Date:** 2026-08-18
**Status:** architecture contract after independent review R2. Not accepted law. Not armed.
**Remediation of:** architecture SHA `da746a90c93c168ba696944c9197e7699d05e959`
**Governing review:** `research/EXECUTIVE_OS_OHF_P1A_R2_INDEPENDENT_ARCH_SECURITY_REVIEW_2026-08-16.md` (`dad9d187b2364b78108cc3595d06d5e11cb8bef3`)
**Prior lineage (do not rewrite):** R1 architecture `f3c1cdb7…`, R1 review `3f1ee290…`, R2 architecture `da746a90…`, R2 review `dad9d187…`
**Typed freeze:** `control_plane/operator_harness_contract.py` (`mastermind.operator_harness/v1`)
**Depends on:** merged OHF-P0 (`da6bd78e078b96db8c121b16f1b10e3fd70e6fef`, PR #81)
**Does not depend on:** unmerged PR #66 or PR #72
**Production arming / Phase 1F-C / CodexOperatorAdapter / SCHEMA_VERSION 3: prohibited**

Authoring verdict of this remediation: `READY_FOR_R3_REREVIEW`.
That is not architecture acceptance and not permission to start P1B.

CARDINALITY_B is accepted and is not relitigated here.

## 0. One-sentence law

Executive OS owns organizational work. A native harness owns a local reasoning
loop inside one Attempt. Provider-completed is evidence, never Executive
completion.

Accepted direction, preserved:

- Executive SQLite is the sole organizational lifecycle authority.
- Native harness state is subordinate execution state.
- OS process identity ≠ native harness session identity.
- Process death ≠ provider writer release.
- Native session state never becomes Executive authority.
- Cross-Attempt native-session reuse is prohibited.
- `WorkerExecutionAdapter` remains the sealed-worker floor.
- Native helper/fork ≠ Executive child Job and ≠ independent review.
- Attempt 1:N sequential primary `HarnessSessionEpoch`s.
- Epoch 1:N sequential `ProcessGeneration`s.
- Context rotation may create a new epoch without consuming another Attempt.
- Native process/stdio adoption after controller loss is `NOT_SUPPORTED`.
- `RequestedExecutionProfile` and `ObservedHarnessAttestation` are separate.
- Phase 1F uses a fresh aggregation Attempt + provider-neutral handoff.

## 1. Source hierarchy

Binding / merged: Charter P7/P8, `strategic_state.yml` (`duplicate_control_planes`),
merged `authority_map.yml`, `AGENTS.md`, Phase 1F contract, worker routing,
`executive_runtime.py` (`SCHEMA_VERSION = 2`), `worker_adapter.py`,
`executive_supervisor.py`, `codex_worker.py`, `executive_workspace.py`,
`executive_backup.py`, P0 live acceptance.

Draft / not law: PR #66, PR #72. P1A does not encode G0 seats or 1G runtime.

Superseded: Phase 1G `session_handles` mixing pid with session id; P1A-R1
`Attempt 1:1 HarnessSession`; live App Server stdio adoption; P1A-R2 language
that treated `attempts.provider_session_id` / pid fields as current-epoch or
current-generation projections.

Canonical typed freeze for adapter/identity helpers is
`control_plane/operator_harness_contract.py`. Prose here must not contradict it.

## 2. Definition of Attempt

An Executive Attempt is **one leased execution placement of a Job**:

one claim against one `(worker_id, quota_class)`, one authority-policy hash,
one workspace binding, one lease/fence generation, and one Executive retry slot
(`attempt_number` toward `attempt_limit`).

Native conversational hygiene does not redefine this.

**Immutable after claim:** `attempt_id`, `job_id`, `attempt_number`, `worker_id`,
`quota_class`, `authority_policy_hash`, `started_at_ms`.

**Attempt-immutable placement/security envelope once RequestedExecutionProfile
is sealed:** provider, requested model, harness kind, exact harness binary
digest, workspace identity (path + inode/device/uid/gid + base SHA), sandbox,
approval, network, REQUIRED/FORBIDDEN sets, allowed write paths, native-helper
policy, write-capable flag, auth-realm requirement, expected config digest when
config is load-bearing.

**Must not increment `attempt_count` / `attempt_number`:** context rotation,
compaction, graceful process replacement, SIGKILL recovery, abandoning poisoned
S1 and starting S2, native fork/helper.

**Does consume a retry slot:** a new Attempt created because placement or the
security envelope changed, including Phase 1F aggregation after leader release.

## 2.1 Execution-mode discriminator

`AttemptExecutionMode` is immutable once set, at or before OHF profile seal.

| Mode | Meaning |
|---|---|
| `SEALED_WORKER` | Existing one-process / one-provider-session Attempt. Canonical process and session identity remain `attempts.pid/pgid/process_start_identity/boot_id` and `attempts.provider_session_id`. Historical rows default here. |
| `OPERATOR_HARNESS` | Rich OHF. Canonical identity lives only in `harness_session_epochs` and `process_generations`. Legacy Attempt process/session columns must not be rewritten. |

No Attempt switches mode in place. The discriminator chooses which already-defined
identity model applies. It is not another lifecycle authority.

`adopt_attempt()` remains Executive lease/fence adoption.

- `SEALED_WORKER`: existing durable Attempt process/provider identity.
- `OPERATOR_HARNESS`: reacquire the Attempt lease from OHF durable state
  (epoch, generation, operation receipts, writer ownership). Do not trust
  `attempts.pid` or `attempts.provider_session_id` for rich identity.
- Old stdio / App Server process adoption remains `NOT_SUPPORTED`.

## 3. Identity hierarchy (CARDINALITY_B)

```text
Job
 └── Attempt                                    1:N
      ├── primary HarnessSessionEpoch 1         sequential; Executive allocates IDs
      │     ├── ProcessGeneration 1
      │     └── ProcessGeneration 2
      ├── primary HarnessSessionEpoch 2
      │     └── ProcessGeneration 3
      ├── Turn                                  Executive-allocated inside a generation
      └── subordinate native forks/helpers      not epochs, not Jobs, not Turns
```

ID ownership:

| ID | Allocator | When |
|---|---|---|
| `session_epoch_id`, `epoch_number` | Executive OS | TX-2 INTENT, before adapter side effect |
| `process_generation_id`, `generation_number` | Executive OS | TX-2 INTENT, before adapter side effect |
| `turn_id` | Executive OS | TX-5 INTENT, before `begin_turn` |
| `provider_session_id` | provider/harness | observed, bound immutably in TX-3 |
| provider event / fork / native turn ids | provider/harness | observations/receipts |

The adapter never mints Executive IDs. `start_session` returns
`SessionStartObservation`. `begin_turn` returns `TurnStartObservation`.

### 3.1 HarnessSessionEpoch

One primary provider-native conversational identity used sequentially inside
exactly one Attempt.

`SessionEpochRef(session_epoch_id, attempt_id, worker_id, epoch_number)` does
not require a provider session ID.

Properties:

- belongs to exactly one Attempt
- monotonically increasing `epoch_number`
- `provider_session_id` starts NULL, then immutable once bound
- may own multiple ProcessGenerations sequentially
- can become `TERMINAL` or `ABANDONED` / nonresumable
- cannot become `CURRENT` again after abandonment
- never crosses Attempt boundary
- at most one `CURRENT` primary epoch per Attempt
- CURRENT is uniquely derivable (`state='CURRENT'`). No Attempt current-epoch pointer.

Creates an epoch: first start on an Attempt; intentional context rotation;
session corrupt/lost with placement still valid; abandoning S1 and starting S2.

Rotation may leave the Attempt with no CURRENT epoch between TX-8 and the next
TX-2. That is recoverable. Do not keep a stale CURRENT marker.

Abandoned epoch resume: **forbidden**.

Rotation increments epoch count, **not** Attempt count.

### 3.2 Canonical session identity

One name: `provider_session_id`.

Canonical location for rich OHF: `harness_session_epochs.provider_session_id`.

`attempts.provider_session_id` remains **LEGACY / SEALED-WORKER-ONLY**.
It is not a current-epoch projection and must not be rewritten for
`OPERATOR_HARNESS` Attempts.

`process_generations.provider_session_id` and `process_generations.worker_id`
are **index projections**, written in the same Executive transaction as their
canonical parents. Mismatch is corruption / `StateConflict`.

**`native_session_id` is a forbidden synonym.** Do not add that column.

### 3.3 ProcessGeneration

One concrete OS incarnation of a harness process associated with one primary
session epoch. Not an Attempt, not a native conversation, not a retry slot, not
organizational authority.

`ProcessGenerationRef` is Executive identity only. OS identity
(`pid`, `pgid`, `process_start_identity`, `boot_id`) is observed after launch
and persisted in TX-3.

`attempts.pid/pgid/process_start_identity/boot_id` remain **LEGACY /
SEALED-WORKER-ONLY**. They are not current-generation projections and must not
be rewritten for `OPERATOR_HARNESS` Attempts. Rich OHF must not call sealed
`record_process()` as a generation-rotation mechanism.

`ended_at` means: the OS process was observed terminated. It does **not** mean
Executive writer released, provider writer released, or session resumable.

## 4. Attempt-boundary matrix

Canonical copy: `ATTEMPT_BOUNDARY_MATRIX` in
`control_plane/operator_harness_contract.py`.

| Case | Decision |
|---|---|
| Graceful harness process replacement | SAME_ATTEMPT (same epoch if resume succeeds) |
| Safe crash recovery | SAME_ATTEMPT |
| SIGKILL blocked writer | SAME_ATTEMPT while recovering |
| SIGKILL, abandon S1, start S2 | SAME_ATTEMPT, new epoch |
| Context compaction | SAME_ATTEMPT, same epoch |
| Intentional context rotation | SAME_ATTEMPT, new epoch |
| Fresh primary session, same placement | SAME_ATTEMPT, new epoch |
| Native fork/helper | SAME_ATTEMPT, subordinate |
| Worker / provider / account / auth-home | NEW_ATTEMPT |
| Requested model | NEW_ATTEMPT |
| Harness kind | NEW_ATTEMPT |
| Exact harness binary digest | NEW_ATTEMPT |
| Workspace / base SHA / inode identity | NEW_ATTEMPT |
| Authority / write paths | NEW_ATTEMPT |
| Sandbox / approval / network | NEW_ATTEMPT |
| REQUIRED/FORBIDDEN set change | NEW_ATTEMPT |
| Phase 1F aggregation after leader release | NEW_ATTEMPT |
| Served model ≠ requested | REFUSE |
| Served model UNKNOWN | REFUSE |
| UNCLASSIFIED on write profile | REFUSE |
| FORBIDDEN present / REQUIRED missing | REFUSE |
| Cross-Attempt session reuse | REFUSE |

V1 has **no** patch-compatible harness-version exception inside one Attempt.

## 5. Writer fence — two layers

Layer A — pre-bind / epoch fence, while `provider_session_id` is still NULL:

```text
UNIQUE(session_epoch_id) WHERE executive_writer_held = 1
```

Layer B — post-bind native-session realm fence:

```text
UNIQUE(worker_id, provider_session_id)
WHERE executive_writer_held = 1 AND provider_session_id IS NOT NULL
```

Both are required. One is not a replacement for the other.

Not `account_label`. Not `UNIQUE(provider_session_id)` globally. Not
`WHERE ended_at IS NULL`.

Four distinct facts:

| Fact | Values | Owner |
|---|---|---|
| Process liveness | ALIVE / PROVEN_DEAD / UNKNOWN | ProcessGeneration |
| Executive writer ownership | held or not | ProcessGeneration `executive_writer_held` |
| Provider writer knowledge | HELD / RELEASED / UNKNOWN | ProcessGeneration |
| Resume safety | derived | never independent durable truth; never adapter-asserted |

Process death leaves Executive writer held and provider writer UNKNOWN or HELD
until reconcile or abandonment. Never invent RELEASED.

Abandonment of epoch/S1: Executive promises never to attach another generation
to S1. Provider writer may remain HELD or UNKNOWN forever. Fresh S2 on the same
Attempt and same worker is lawful **only when the local process is PROVEN_DEAD
or proven absent**. UNKNOWN process liveness plus UNKNOWN external effect
blocks any new rich writer on that worker/workspace until absence is proven or
the slot/host is reset. If bounded recovery cannot prove safety: Attempt `LOST`
and the slot stays unavailable for another write-capable rich execution.

Opaque id collision across workers is legal: W1/`abc` and W2/`abc` are different
realms.

## 6. Controller / process topology

Current topology (merged): adapter / `CodexWorker` /
laboratory App Server client spawn via `Popen` or `create_subprocess_exec`.
Pipes live in the spawning process. A restarted controller cannot inherit them.

Three different operations:

| Concept | V1 |
|---|---|
| Executive Attempt lease adoption (`adopt_attempt`) | supported; lease/fence only |
| Native process / stdio / JSON-RPC adoption | **NOT_SUPPORTED** |
| Provider session resume | optional; requires a **new** ProcessGeneration after writer-safe reconcile |

Controller restart law:

```text
reacquire/reconcile Executive Attempt lease
→ identify old process if any
→ do not inherit old stdio
→ terminate/reconcile old process if required
→ determine provider writer state
→ inspect OperationId INTENT vs APPLIED (EFFECT_UNKNOWN is fail-closed)
→ if CURRENT epoch + old generation PROVEN_DEAD + provider RELEASED + resume_safe:
     TX-10 same-epoch ProcessGeneration recovery, then resume_session
     with ProviderSessionHandoff(already-bound S1), then TX-11 process
     identity + APPLIED
→ else if process PROVEN_DEAD: abandon old epoch; start fresh epoch if placement still lawful
→ else if process UNKNOWN: no new writer; Attempt LOST if recovery expires
```

**TX-10 — same-epoch ProcessGeneration recovery.** Distinct from TX-6 (graceful
stop after confirmed provider RELEASED) and TX-8 (abandon epoch / fresh S2).
Entry: epoch `CURRENT`, old generation is the Executive-held writer, process
`PROVEN_DEAD`, provider writer `RELEASED`, Executive-derived `resume_safe`.
One `BEGIN IMMEDIATE` transaction:

1. clear the old generation's `executive_writer_held`
2. allocate the next Executive `process_generation_id` / `generation_number`
   on the **existing** epoch
3. insert the successor with `executive_writer_held=1` and
   `provider_session_id` index projection already bound to S1
4. append `OPERATOR_OPERATION_INTENT` with `command_id=OperationId` and
   Event-plane `payload_json` = typed `OperationIntentTarget`
   (`operation_kind=resume_session`, `attempt_id`, `session_epoch_id`,
   `process_generation_id`, `worker_id`, already-bound `provider_session_id`)

Then, and only then, call `resume_session` with a `ProviderSessionHandoff`
of the already-bound S1. The adapter must not mint a provider session.
TX-10 does **not** create a SessionEpoch and does **not** consume an Attempt.
Hard-dead G1 + `HELD` / `UNKNOWN` provider writer refuses G2 (TX-8 remains
the S2 path). UNKNOWN process refuses G2. Duplicate TX-10 is refused by the
unique writer indexes and unique `command_id`. Crash after INTENT but before
the provider call: retry the **same** OperationId against already-allocated
G2 only if local state proves the adapter was never entered; otherwise
`EFFECT_UNKNOWN` and hold G2. Never allocate G3 as a replay.

**TX-11 — bind resume result.** Distinct from TX-3 (first bind of a NULL
epoch session). After `resume_session` returns an observation, one
`BEGIN IMMEDIATE` transaction:

1. verify TX-10 INTENT for this OperationId, including the typed
   `OperationIntentTarget` against current G2/S1 (`resume_session`, this
   Attempt, this epoch, this generation, this worker, already-bound S1)
2. verify epoch `CURRENT` and G2 still holds the writer
3. verify observed `provider_session_id` equals already-bound S1
4. record G2 process identity (`pid`/`pgid`/`process_start_identity`/`boot_id`)
   using existing Executive law: positive pid/pgid, nonblank trimmed start/boot
5. append `OPERATOR_OPERATION_APPLIED`

TX-11 must **not** mutate `epoch.provider_session_id`, must **not** create a
SessionEpoch, and must **not** consume an Attempt. Observed S2 / NULL /
empty session is `PROVIDER_SESSION_MISMATCH`. Incomplete process identity
is refused. An INTENT whose target is G3, another epoch, another session,
`start_session`, or another Attempt is `INTENT_TARGET_MISMATCH`. Missing
APPLIED after a possible resume call is
`EFFECT_UNKNOWN`; do not allocate G3. Matching TX-11 replay after APPLIED
is a no-op; a different process identity is `ALREADY_APPLIED_CONFLICT`.
G2 still requires TX-4 re-attestation before a work turn
(`new_process_generation`).

No hidden durable broker. No writer stealing. No lock-file deletion.

Host reboot: DESIGNED / UNKNOWN as live evidence. `boot_id` mismatch ⇒ generation
cannot be considered live. That does **not** imply provider RELEASED.

## 7. RequestedExecutionProfile, attestation, and launch comparator

Two concepts. Not one mutable blob.

**RequestedExecutionProfile** is sealed in TX-1 after Attempt claim and **before**
process start. It is Attempt-immutable. It contains every load-bearing expected
value the comparator needs: worker, provider, requested model, harness kind,
exact binary digest/version, workspace identity, sandbox, approval, network,
capability policy, native-helper policy, authority hash, allowed write paths,
write-capable flag, `AuthRealmRequirement`, optional expected provider account
id, optional expected config digest.

**ObservedHarnessAttestation** is collected after process launch + initialize +
effective discovery, sealed in TX-4 **before** the first meaningful work turn.
Unknown stays UNKNOWN. It includes typed `ObservedCapabilityIdentity` values
and `supports_subagent_capability_ceiling` as `VERIFIED|FALSE|UNKNOWN`.

`LaunchDecision = compare_launch(requested, observed)` is a pure Executive
function. The adapter does not supply match booleans, unclassified lists, or
helper-ceiling verdicts. Those are outputs.

Served model UNKNOWN → `REFUSE_SERVED_MODEL_UNKNOWN`.
Served ≠ requested → `REFUSE_SERVED_MODEL_MISMATCH`.
Harness digest UNKNOWN (required) → `REFUSE_UNATTESTABLE`.
Harness digest mismatch → `REFUSE_HARNESS_BINARY_MISMATCH`.
Workspace / sandbox / approval / network / config compared from structures.
`AuthRealmRequirement.SLOT_BOUND_V1` permits current single-slot research when
observed worker_id and provider match, even if provider account id is UNKNOWN.
It does not clear `ACCOUNT_REALM_ATTESTATION_UNPROVEN` or multi-account
production. `VERIFIED_PROVIDER_ACCOUNT` requires a matching non-secret account
id.

If a provider only reveals the served model on first inference, it cannot
satisfy this strict production profile until a bounded identification probe
exists.

Re-attestation: every new ProcessGeneration; after harness config reload; after
authoritative workspace identity change. Harness binary digest change is
NEW_ATTEMPT. Not per-turn.

## 8. Capability policy

The comparator itself derives missing REQUIRED, present FORBIDDEN, recognized
ALLOWED_AMBIENT, and UNCLASSIFIED from requested `CapabilityManifest` plus
observed `ObservedCapabilityIdentity[]`.

REQUIRED missing → REFUSE.
FORBIDDEN present → REFUSE.
UNCLASSIFIED on write-capable profile → REFUSE.
UNCLASSIFIED in explicitly read-only laboratory mode → only when requested
`unclassified_policy == lab_allow_unclassified_readonly`; never silently
promoted to ALLOWED_AMBIENT.

ALLOWED_AMBIENT binds at minimum to harness exact binary digest + capability
name, and where the requested rule carries a digest the observation must prove
it. An expected digest that the harness does not expose is not proven allowed.

Residual Codex 0.147.0 `github:*` / `openai-templates:*` /
`plugin-management` remain UNCLASSIFIED. Architecture: nonblocking.
Write-capable Codex canary: **blocked**. Production arming: **blocked**.

## 9. Auth realm

`account_label` is display/config metadata: not unique, not authenticated,
default `"dedicated-codex-home"`. It is not a security identity.

V1 fence uses `worker_id` (unique slot PK).
**ACCOUNT_REALM_ATTESTATION_UNPROVEN.**

Not identities: `CODEX_HOME` path, `auth.json` inode/mtime, plan type.
Credential refresh in the same account must not create a new Attempt.
A different provider account inside the same home must. Detection of silent
account switch is unproven → production-arming gate.

Production invariant: a `worker_id` used as the V1 session realm must not be
silently rebound to a different provider/auth home/account while historical
native-session bindings exist.

`AuthRealmFact` must support identity = UNKNOWN and must not persist tokens.

## 10. Native helpers

Read-only Attempt: helpers allowed if the parent ceiling is itself enforceably
read-only (`PARENT_READ_ONLY_CEILING`).

Write-capable Attempt: helpers **disabled** unless observed
`supports_subagent_capability_ceiling = VERIFIED` and that ceiling can prevent
writes beyond the subordinate policy. Prompt "read-only" is not a boundary.
The adapter does not pass a caller boolean; the observation is on the
attestation.

Native helper / fork / native review subagent cannot satisfy Phase 1F
independent review. Minimum remains a different `worker_id`. Native forks do
not consume the primary epoch counter and do not need a v3 fork table.

## 11. Phase 1F

```text
bounded planning Attempt
→ durable children
→ leader released (no persistent leader)
→ children execute independently
→ later aggregation Attempt
→ fresh session + provider-neutral handoff
```

**V1_QUALITY_TRADEOFF_ACCEPTED.** Native planner context is lost. Do not park a
thread without a worker lease. Later parity testing must measure the cost.

Aggregation consumes an Attempt. Context rotation does not.

## 12. Adapter contract and OperationId

Sibling of `WorkerExecutionAdapter`. Adapter returns typed observations.
Supervisor decides. Runtime mutates Executive state.

Kitchen-sink `prepare()` is **rejected**. Use `validate_requested_profile`
(required, pure) and optional `stage_operator_config` (Attempt-owned staging
dir only; no credentials; no authoritative workspace mutation; no process start).

`reconcile()` returns `ReconcileObservation`. It must not kill, resume, mark
LOST, start Attempts, select providers, release quota, complete jobs, or assert
`executive_writer_held` / `resume_safe` / workspace or profile match.

`signal_process` is supervisor/runtime machinery, not a provider-neutral method.

`collect_candidate_result()` never calls `complete_job()`.

`describe_capabilities()` returns `HarnessAdapterCapabilities`, not a generic
mapping.

Optional capabilities are typed extension Protocols: `SupportsProbe`,
`SupportsConfigStaging`, `SupportsSessionResume`, `SupportsSteering`,
`SupportsApprovalResponse`, `SupportsNativeFork`, `SupportsCheckpoint`.
Adapters implement only what they support.

### 12.1 OperationId

`OperationId.command_id` is the durable `events.command_id` of
`OPERATOR_OPERATION_INTENT`. Aggregate: `operator_operation` / OperationId.

Before any nontrivial external state-changing operation:

```text
BEGIN IMMEDIATE
  reserve Executive IDs / writer fence
  append OPERATOR_OPERATION_INTENT  (command_id = OperationId)
COMMIT
then adapter side effect
```

Later receipts for the same operation use deterministic derived command IDs
(`:applied`, `:refused`, `:effect-unknown`, `:reconciled`) and the same
aggregate id. No sidecar operation store. Every accepted base OperationId must
leave room for **all** of those derived receipts under Executive
`_COMMAND_ID_RE` (max 128). Construction that matches the base regex but would
overflow `:effect-unknown` is refused. Canonical cap:
`MAX_OPERATION_ID_LEN = 128 - len(":effect-unknown")`.

A committed INTENT is Executive at-most-once **issuance**, not proof that an
external effect did or did not occur. Missing APPLIED after a possible provider
call is `EFFECT_UNKNOWN`. Do not blindly replay. Retry the same OperationId
only when local execution state proves the adapter call never began, or when
the adapter advertises provider-native idempotency and that contract is used.

Idempotency class replaces a boolean: `PURE_IDEMPOTENT`,
`EXECUTIVE_DEDUPED_AT_MOST_ONCE`, `PROVIDER_NATIVE_IDEMPOTENT`,
`NON_REPLAYABLE_ON_UNKNOWN_EFFECT`. State-creating V1 methods are
`NON_REPLAYABLE_ON_UNKNOWN_EFFECT` and require OperationId.

### 12.2 Combined start_session

`start_session` remains one operation. Executive preallocates epoch and
generation. Adapter may launch the process, initialize, and create the native
session. It returns observations. Executive binds `provider_session_id` in TX-3.

### 12.3 Combined resume_session

`resume_session` is optional. Executive already bound S1 in TX-3 and already
allocated G2 in TX-10. Executive passes that bound S1 **into** the adapter as
`ProviderSessionHandoff`. The adapter must not allocate `provider_session_id`
and must not create a new provider session. Observed session must equal the
handoff. Executive records G2 process identity and APPLIED in TX-11 only after
the Event-plane TX-10 INTENT payload proves this OperationId authorized this
exact G2/S1 `resume_session`. TX-11 is
not TX-3: a NULL epoch session cannot be bound on the resume path.

### 12.4 EventCursor

Scoped to one ProcessGeneration: `attempt_id`, `session_epoch_id`,
`process_generation_id`, optional `turn_id`, optional provider replay cursor,
adapter-local monotonic `local_sequence`. A G1 cursor must not be reused against
G2. Providers without stable event IDs get local sequence only; no
cross-generation replay promise. Normalized events flow into the existing
Executive Event plane. No second event store.

## 13. Backup / restore

Option A: backup may capture active OHF history. Restore always invalidates
external-live authority.

A restored provider session id is historical evidence, not authority to resume.
TX-9, before service re-enable: clear `executive_writer_held`; CURRENT epochs
become ABANDONED; OPERATOR_HARNESS active Attempts become existing **LOST**;
append `OHF_RESTORE_INVALIDATED`. Historical `provider_writer_state` and
process observations stay byte-for-byte. Do not rewrite RELEASED into UNKNOWN.

Continuation is a new lawful Attempt from last trusted checkpoint, subject to
`attempt_limit`.

Terminal Attempt with provider writer HELD/UNKNOWN is allowed. Terminalization
ends Executive authority; it does not falsify provider state.

## 14. Rollback wording

Feature disable: stop using OHF. That is not old-binary rollback.
Old binary vs future schema 3: fail closed.
DB restore: offline; invalidate writers as §13.
Forward-fix: the safe escape.
Migration rollback: not promised.

## 15. Architecture consistency table

| Fact | Canonical owner | Durable location (proposed v3) | Immutable? | Change inside Attempt? |
|---|---|---|---|---|
| execution mode | Attempt | `attempts.execution_mode` | after seal | no |
| worker placement | Attempt | `attempts.worker_id` | after claim | no → NEW_ATTEMPT |
| authority | Attempt | `authority_policy_hash` | after claim | no → NEW_ATTEMPT |
| workspace | existing workspace receipt | inode+device+uid+gid+base SHA | after seal | no → NEW_ATTEMPT |
| requested model | RequestedExecutionProfile | Attempt requested JSON | after seal | no → NEW_ATTEMPT |
| harness binary | RequestedExecutionProfile | digest in requested JSON | after seal | no → NEW_ATTEMPT |
| session epoch | HarnessSessionEpoch | `harness_session_epochs` | epoch_number | new epoch, same Attempt |
| provider_session_id | epoch | epoch column; generation copy is index projection | once non-null | no on that epoch |
| ProcessGeneration | generation row | `process_generations` | identity fields | new generation |
| process liveness | generation | pid/start/boot + ended_at | n/a | yes (observation) |
| Executive writer | generation | `executive_writer_held` | n/a | held until release/abandon |
| provider writer | generation | `provider_writer_state` | n/a | HELD/RELEASED/UNKNOWN |
| requested profile | Attempt | requested JSON + digest | after seal | no |
| observed attestation | generation | observed JSON + digest | after seal | re-attest per generation |
| capability policy | requested profile | manifest | after seal | set change → NEW_ATTEMPT |
| OperationId intent | Event plane | `events.command_id` | yes | receipts on same aggregate |
| sealed Attempt pid/session | sealed worker only | `attempts.*` legacy columns | write-once | not used by OHF |

## 16. Preserved gates

- ACCOUNT_REALM_ATTESTATION_UNPROVEN
- residual Codex plugin/template skills → write-canary / production-arming
- native-helper capability ceiling → write-capable-helper gate
- transitive orphan cleanup → UNKNOWN
- host reboot live behavior → UNKNOWN / design only
- multi-host machine identity → postponed; no hostname-hash identity
- worker-slot auth-binding production invariant
- provider writer-steal API → not used
- structured MCP item events → not universal
- live App Server adoption → NOT_SUPPORTED
