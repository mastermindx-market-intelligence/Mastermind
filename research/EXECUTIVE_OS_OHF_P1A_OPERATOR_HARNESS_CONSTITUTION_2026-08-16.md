# OHF-P1A-R2 — Operator Harness Constitution

**Date:** 2026-08-16
**Status:** architecture contract after independent review R1. Not accepted law. Not armed.
**Remediation of:** architecture SHA `f3c1cdb7d3b40103450cf3f845ac0648479585e7`
**Governing review:** `research/EXECUTIVE_OS_OHF_P1A_INDEPENDENT_ARCH_SECURITY_REVIEW_2026-08-16.md` (`3f1ee290ba147313d3bee3a1192e18b21313f88d`)
**Typed freeze:** `control_plane/operator_harness_contract.py` (`mastermind.operator_harness/v1`)
**Depends on:** merged OHF-P0 (`da6bd78e078b96db8c121b16f1b10e3fd70e6fef`, PR #81)
**Does not depend on:** unmerged PR #66 or PR #72
**Production arming / Phase 1F-C / CodexOperatorAdapter / SCHEMA_VERSION 3: prohibited**

Authoring verdict of this remediation: `READY_FOR_R2_REREVIEW`.
That is not architecture acceptance and not permission to start P1B.

## 0. One-sentence law

Executive OS owns organizational work. A native harness owns a local reasoning
loop inside one Attempt. Provider-completed is evidence, never Executive
completion.

Accepted direction from independent review, preserved:

- Executive SQLite is the sole organizational lifecycle authority.
- Native harness state is subordinate execution state.
- OS process identity ≠ native harness session identity.
- Process death ≠ provider writer release.
- Native session state never becomes Executive authority.
- Cross-Attempt native-session reuse is prohibited.
- `WorkerExecutionAdapter` remains the sealed-worker floor.
- Native helper/fork ≠ Executive child Job and ≠ independent review.

## 1. Source hierarchy

Binding / merged: Charter P7/P8, `strategic_state.yml` (`duplicate_control_planes`),
merged `authority_map.yml`, `AGENTS.md`, Phase 1F contract, worker routing,
`executive_runtime.py` (`SCHEMA_VERSION = 2`), `worker_adapter.py`,
`executive_supervisor.py`, `codex_worker.py`, `executive_workspace.py`,
`executive_backup.py`, P0 live acceptance.

Draft / not law: PR #66, PR #72. P1A does not encode G0 seats or 1G runtime.

Superseded by P0 + this remediation: Phase 1G `session_handles` mixing pid with
session id; P1A-R1 `Attempt 1:1 HarnessSession`; live App Server stdio adoption.

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
policy, write-capable flag.

**Must not increment `attempt_count` / `attempt_number`:** context rotation,
compaction, graceful process replacement, SIGKILL recovery, abandoning poisoned
S1 and starting S2, native fork/helper.

**Does consume a retry slot:** a new Attempt created because placement or the
security envelope changed, including Phase 1F aggregation after leader release.

## 3. Identity hierarchy (CARDINALITY_B)

```text
Job
 └── Attempt                                    1:N
      ├── primary HarnessSessionEpoch 1         sequential
      │     ├── ProcessGeneration 1
      │     └── ProcessGeneration 2
      ├── primary HarnessSessionEpoch 2
      │     └── ProcessGeneration 3
      └── subordinate native forks/helpers      not epochs, not Jobs
```

- One Attempt has N **sequential** primary session epochs.
- At most one epoch per Attempt is `CURRENT`.
- A native fork/helper is not a primary epoch and does not consume the epoch
  counter.
- A ProcessGeneration is one OS incarnation of a harness process for one epoch.
- An epoch may have many generations (graceful replace / resume).
- Cross-Attempt session reuse is `REFUSE`.

### 3.1 HarnessSessionEpoch

One primary provider-native conversational identity used sequentially inside
exactly one Attempt.

Properties:

- belongs to exactly one Attempt
- monotonically increasing `epoch_number`
- `provider_session_id` may be NULL until creation completes, then immutable
- may own multiple ProcessGenerations sequentially
- can become `TERMINAL` or `ABANDONED` / nonresumable
- cannot become `CURRENT` again after abandonment
- never crosses Attempt boundary
- at most one `CURRENT` primary epoch per Attempt

Creates an epoch: first start_session on an Attempt; intentional context
rotation; session corrupt/lost with placement still valid; abandoning S1 and
starting S2.

Terminates an epoch: graceful session end with confirmed stop; intentional
rotation of the old epoch; Attempt terminalization.

Abandons an epoch: recovery deadline after unsafe writer state; restore
invalidation; supervisor decision that S1 must never be resumed.

Abandoned epoch resume: **forbidden**.

Rotation increments epoch count, **not** Attempt count.

### 3.2 Canonical session identity

One name: `provider_session_id`.

It already exists on `attempts` for sealed workers (write-once / COALESCE).
For rich OHF it lives on `harness_session_epochs.provider_session_id`.
`attempts.provider_session_id` is then a same-transaction projection of the
current epoch, or the legacy sealed-worker field when no epoch rows exist.

**`native_session_id` is a forbidden synonym.** Do not add that column.

### 3.3 ProcessGeneration

One concrete OS incarnation of a harness process associated with one primary
session epoch. Not an Attempt, not a native conversation, not a retry slot, not
organizational authority.

Canonical process identity: `pid`, `pgid`, `process_start_identity`, `boot_id`
on the generation row. Attempt pid fields are a same-transaction projection of
the current generation for rich OHF, or remain the sealed-worker canonical
fields when no generation rows exist.

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
| UNCLASSIFIED on write profile | REFUSE |
| FORBIDDEN present / REQUIRED missing | REFUSE |
| Cross-Attempt session reuse | REFUSE |

V1 has **no** patch-compatible harness-version exception inside one Attempt.

## 5. Writer fence

V1 realm: `(worker_id, provider_session_id)`.

Not `account_label`. Not `UNIQUE(provider_session_id)` globally. Not
`WHERE ended_at IS NULL`.

Four distinct facts:

| Fact | Values | Owner |
|---|---|---|
| Process liveness | ALIVE / PROVEN_DEAD / UNKNOWN | ProcessGeneration |
| Executive writer ownership | held or not, for that realm | ProcessGeneration `executive_writer_held` |
| Provider writer knowledge | HELD / RELEASED / UNKNOWN | ProcessGeneration |
| Resume safety | derived | never independent durable truth |

Process death leaves Executive writer held and provider writer UNKNOWN or HELD
until reconcile or abandonment. Never invent RELEASED.

Abandonment of epoch/S1: Executive promises never to attach another generation
to S1. Provider writer may remain HELD or UNKNOWN forever. Fresh S2 on the same
Attempt and same worker is lawful. S1 remains nonresumable, including on later
Attempts of the same worker.

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
→ if same epoch resume_safe: new ProcessGeneration, resume provider session
→ else abandon old epoch; start fresh epoch if placement still lawful
```

No hidden durable broker. No writer stealing. No lock-file deletion.

Host reboot: DESIGNED / UNKNOWN as live evidence. `boot_id` mismatch ⇒ generation
cannot be considered live. That does **not** imply provider RELEASED.

## 7. RequestedExecutionProfile and ObservedHarnessAttestation

Two concepts. Not one mutable blob.

**RequestedExecutionProfile** is sealed after Attempt claim and **before**
process start. It is Attempt-immutable. Fields: worker_id, provider, requested
model, harness kind, exact binary digest/version, workspace identity, sandbox,
approval, network, REQUIRED/FORBIDDEN/ALLOWED_AMBIENT policy, native-helper
policy, authority hash, allowed write paths, write-capable flag.

**ObservedHarnessAttestation** is collected after process launch + initialize +
effective discovery, and sealed **before** the first meaningful work turn.
Unknown stays UNKNOWN. Fields: served model, harness version/digest confirmation,
effective skills/MCP/plugins, sandbox/approval, config digest, AuthRealmFact,
workspace observation.

First-turn gate:

```text
claimed Attempt
→ RequestedExecutionProfile sealed
→ ProcessGeneration launched
→ harness initialized
→ ObservedHarnessAttestation collected
→ deterministic LaunchDecision
→ ALLOW: first work turn
→ REFUSE: no work turn; supervisor reconciles/terminates
```

Served ≠ requested → `REFUSE_SERVED_MODEL_MISMATCH`. Do not rewrite the requested
profile. If a provider only reveals the served model on first inference, it is
incapable of pre-work model attestation unless a bounded non-work identification
probe exists. V1 does not hide that limitation.

Re-attestation: every new ProcessGeneration; after harness config reload; after
authoritative workspace identity change. Harness binary digest change is
NEW_ATTEMPT, not an in-Attempt re-attest. Not per-turn.

## 8. Capability policy

REQUIRED missing → REFUSE.
FORBIDDEN present → REFUSE.
UNCLASSIFIED on write-capable profile → REFUSE.
UNCLASSIFIED in explicitly read-only laboratory mode → only under a named lab
policy; never silently promoted to ALLOWED_AMBIENT.

ALLOWED_AMBIENT binds at minimum to harness exact binary digest + capability
name, and where available skill content digest, tool schema digest, and MCP
server identity/version.

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
account switch is unproven → production-arming gate. Fail closed if a provider
reports a changed non-secret account id.

`AuthRealmFact` must support identity = UNKNOWN and must not persist tokens.

## 10. Native helpers

Read-only Attempt: helpers allowed if the parent ceiling is itself enforceably
read-only.

Write-capable Attempt: helpers **disabled** unless the harness proves
`supports_subagent_capability_ceiling` and that ceiling can prevent writes
beyond the subordinate policy. Prompt "read-only" is not a boundary.

Native helper / fork / native review subagent cannot satisfy Phase 1F
independent review. Minimum remains a different `worker_id`.

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

## 12. Adapter contract

Sibling of `WorkerExecutionAdapter`. Adapter returns typed observations.
Supervisor decides. Runtime mutates Executive state.

Kitchen-sink `prepare()` is **rejected**. Use `validate_requested_profile`
(required, pure) and optional `stage_operator_config` (Attempt-owned staging
dir only; no credentials; no authoritative workspace mutation; no process start).

`reconcile()` is observational. It must not kill, resume, mark LOST, start
Attempts, select providers, release quota, or complete jobs.

`signal_process` is supervisor/runtime machinery, not a provider-neutral method.

`collect_candidate_result()` never calls `complete_job()`.

Required methods, optional methods, timeouts, idempotency, side effects, and
failure classes are frozen in `METHOD_CONTRACTS`. State-creating operations
require an Executive `OperationId`.

EventCursor is the reconnect/duplicate/out-of-order contract. Normalized events
carry Attempt, epoch, generation, turn, optional provider event id, optional
subordinate id. No second event store. MCP item events are not universally
required.

## 13. Backup / restore

Option A: backup may capture active OHF history. Restore always invalidates
external-live authority.

A restored provider session id is historical evidence, not authority to resume.
Restored `executive_writer_held` is cleared. Process liveness becomes UNKNOWN.
Provider writer is not rewritten to RELEASED (HELD stays HELD; prior RELEASED
becomes UNKNOWN because restore does not prove current provider state).
Current epochs become ABANDONED. Active Attempts transition to existing
**LOST**. Continuation is a new lawful Attempt from last trusted checkpoint,
subject to `attempt_limit`.

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
| worker placement | Attempt | `attempts.worker_id` | after claim | no → NEW_ATTEMPT |
| authority | Attempt | `authority_policy_hash` | after claim | no → NEW_ATTEMPT |
| workspace | existing workspace receipt | inode+device+uid+gid+base SHA | after seal | no → NEW_ATTEMPT |
| requested model | RequestedExecutionProfile | Attempt requested JSON | after seal | no → NEW_ATTEMPT |
| harness binary | RequestedExecutionProfile | digest in requested JSON | after seal | no → NEW_ATTEMPT |
| session epoch | HarnessSessionEpoch | `harness_session_epochs` | epoch_number | new epoch, same Attempt |
| provider_session_id | epoch | epoch column; Attempt projection | once non-null | no on that epoch |
| ProcessGeneration | generation row | `process_generations` | identity fields | new generation |
| process liveness | generation | pid/start/boot + ended_at | n/a | yes (observation) |
| Executive writer | generation | `executive_writer_held` | n/a | held until release/abandon |
| provider writer | generation | `provider_writer_state` | n/a | HELD/RELEASED/UNKNOWN |
| requested profile | Attempt | requested JSON + digest | after seal | no |
| observed attestation | generation | observed JSON + digest | after seal | re-attest per generation |
| capability policy | requested profile | manifest | after seal | set change → NEW_ATTEMPT |

## 16. Preserved gates

- ACCOUNT_REALM_ATTESTATION_UNPROVEN
- residual Codex plugin/template skills → write-canary / production-arming
- native-helper capability ceiling → write-capable-helper gate
- transitive orphan cleanup → UNKNOWN
- host reboot live behavior → UNKNOWN / design only
- multi-host machine identity → postponed; no hostname-hash identity
- provider writer-steal API → not used
- structured MCP item events → not universal
- live App Server adoption → NOT_SUPPORTED
