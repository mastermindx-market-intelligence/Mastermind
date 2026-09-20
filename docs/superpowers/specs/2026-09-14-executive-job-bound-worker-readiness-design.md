# Executive Job-Bound Worker Readiness Design

**Status:** architecture freeze candidate for P2-1 of the Chairman-approved permanent unattended privileged-execution program. This document grants no runtime authority, installs nothing, and does not arm a root effect.

**Source:** protected Mastermind `8ba7deedde164c90298d3e88785d98e02fa5e2d2`; Skillpack `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1.

**Current protected dependencies:** protected master `8ba7deedde164c90298d3e88785d98e02fa5e2d2` contains the PR #613 broker/client merge `c9db5d42ed4b1479985b8989d9767ac80a84f9b8` and the PR #621 revocation merge `2575d16ae8e2ae73e3e520d81bc5344621f5356c`. P2-1 extends those merged owners and must not duplicate or fork their actuator, status, receipt, or revocation contracts.

## 1. Outcome, machine job, and 10/10 end state

The user job is simple: an assigned reviewed worker slot should finish approved work without stopping to ask Chris to type an administrator password for a routine, already-reviewed host check. P2-1 proves the current closed Codex slot catalog; a future separately reviewed slot-catalog extension is required before claiming Claude worker coverage.

The P2-1 machine job is narrower: a current Executive Job/Attempt may request **a login-status observation for its own assigned worker slot** through the trusted Executive controller. The controller must prove the current Job, Attempt, fence, policy, worker assignment, installed release and current host boot, then invoke exactly the broker action `executive.worker_auth.verify_only`. The worker never receives root, a reusable credential, the broker socket, a lease token, or a caller-selected executable/path/action/slot.

The full 10/10 end state remains the permanent program: useful root operations are admitted from current durable authority, executed once through a fixed actuator, reconciled after interruption, corrected or revoked safely, consumed by real native clients, and proven on each intended host. P2-1 is one vertical slice toward that outcome, not a claim that credential rotation, arbitrary future upgrades, service control, fleet selection, vendor MFA, or all sudo prompts are solved.

P2-1 covers only Executive workers whose `worker_id` exactly equals a reviewed `provider_worker_slots` slot id (see §13 for the import seam); no other worker-identity resolution path is in scope.

### What a successful `verify_only` proves and does not prove

A successful invocation proves exactly that: the selected slot's `auth.json` is a one-link, non-symlink, nonempty, worker-owned, mode-0600 file with no ACL; pinned Codex `login status` ran as the selected worker against the file credential store with both streams suppressed and exited zero; and that file's metadata was rechecked unchanged after Codex opened it. The validated terminal broker receipt carries the fixed success output that login status passed, that no provider-inference canary ran, and that the slot is **not READY**. It does not prove credential expiry, provider inference, App Server account identity, model execution, or READY state.

This is mechanical, not advisory: the result schema (§10) has no `ready`/`READY` field or value anywhere in its state enum, and every operation result carries the top-level constant `observation_scope: "LOGIN_STATUS_ONLY_NO_READY_ASSERTION"`. `receipt` is a validated terminal broker receipt only for `TERMINAL`; it is `null` for broker refusal or unresolved effect. A replayed terminal result (`replayed: true`) reproduces the identical original terminal evidence and observation scope — replay can never upgrade stale evidence into a current READY claim. `evidence_currency` (§8) separately bounds only how current the release/boot/policy facts are when the result is returned; it never asserts READY.

## 2. Capability ledger at freeze

| Capability | State | Evidence / boundary |
|---|---|---|
| Six-action root broker and non-root operator CLI | `BUILT_NOT_PROVEN` | protected merge `c9db5d42ed4b1479985b8989d9767ac80a84f9b8`; install/host proof still separate |
| Read-only broker result reconciliation | `BUILT_NOT_PROVEN` | protected merge `c9db5d42ed4b1479985b8989d9767ac80a84f9b8`; status request never re-executes |
| Administrative broker revocation | `BUILT_NOT_PROVEN` | protected merge `2575d16ae8e2ae73e3e520d81bc5344621f5356c`; not installed/proven live |
| Current Job/Attempt authority -> worker login-status check | `NOT_BUILT` | This P2-1 design |
| Secret-free credential enrollment/renewal | `NOT_BUILT` | P3; vendor/provider evidence required |
| Authenticated passwordless release update/rollback | `NOT_BUILT` | P4; first bootstrap remains administrator-gated |
| Multi-host/fleet selection and proof | `NOT_BUILT` | P5 |

## 3. Canonical owners and no-rebuild boundary

P2-1 extends existing owners only:

- `Executive OS RuntimeStore` owns Job, Attempt, Worker, quota, fence, event and command-id truth.
- `ExecutiveAuthorityPolicy` owns checked-in worker capability admission and policy digest.
- the existing control service owns trusted deterministic orchestration on the installed host.
- the protected merged privileged broker owns fixed root execution plus its marker/receipt evidence.
- `provider_worker_slots.py` owns the closed worker-slot inventory.
- the installed release and controller environment attestation own release and boot identity.

P2-1 creates no table, queue, scheduler, lease, token registry, permission service, credential store, retry ledger, host registry, transcript plane or second lifecycle. Its durable records are ordinary `events` rows. Broker receipts remain subordinate evidence of one host effect, never an authority source.

## 4. Deliberately narrow capability

Add one checked-in Executive capability:

```text
REQUEST_WORKER_LOGIN_CHECK
```

Its policy scope is exactly:

```text
current_attempt_assigned_worker_slot
```

This capability means “the trusted controller may ask the fixed broker to verify the current Attempt's already-assigned reviewed slot.” It grants no `SERVICE_CONTROL`, `CREDENTIAL_ADMIN`, credential enrollment, recovery, arbitrary slot selection, or dedicated-worker permission to call the broker directly.

P2-1 does **not** narrow the pre-existing P1 operator bridge. The installed operator UID is already an allowed privileged-broker peer, and the installed `mmx-admin` exposes the full reviewed six-action catalog. That inherited operator-admin grant is an accepted residual of the merged broker design: `mmx-control` adds a durable Job-bound consumption path and ergonomics, not host-level containment of the operator principal. Dedicated worker UIDs remain excluded from the privileged socket.

Existing mandatory denies remain, including `SERVICE_CONTROL` and `CREDENTIAL_ADMIN`. Adding a YAML string alone remains insufficient: `ExecutiveAuthorityPolicy.load()` must pin the exact revised allow-list and scope value in code. The scope string is declarative policy metadata, not slot evidence; only the deterministic controller's current Job/Attempt join enforces the current-assigned-slot boundary. No caller or model may treat an `AuthorityDecision` containing this capability as proof of a worker, slot, fence, host or root action.

The first root action is fixed to:

```text
executive.worker_auth.verify_only
```

`verify_ready` is excluded because it requires a truthful credential-expiry source and may execute a provider canary/write readiness state; that belongs to P3. `recover_transaction` and all service actions remain excluded.

## 5. External command contract

The existing Executive control service gains one command and the thin operator CLI gains one matching subcommand:

```text
check-current-worker-login JOB_ID ATTEMPT_ID FENCE_GENERATION
```

The control request arguments are exactly:

```json
{
  "job_id": "JOB-...",
  "attempt_id": "ATT-...",
  "fence_generation": 1
}
```

No caller field may name an action, worker, slot, executable, path, host, release, request ID, credential kind, credential material, expiry, retry instruction or force flag. `fence_generation` must be a positive JSON integer, never boolean/string/float.

The command is available only when the control service is `READY`, `privileged_readiness_armed` is true in the root-installed control config, and the request arrives through its existing peer-authenticated Unix socket. Worker UIDs do not gain access to the privileged broker. The installer publishes one fixed non-root `mmx-control` wrapper to the exact installed release and control socket so attended Codex/Claude orchestrators running as the approved operator UID can invoke the command for a named Executive Job/Attempt without discovering a mutable source path. This first consumer acts on behalf of the selected durable Job; it does not prove that an arbitrary dedicated worker can invoke the command itself. A later bounded dedicated-worker tool must bind the caller to its own current Attempt before submitting the same typed request through the current control owner.

The installed `mmx-control` consumer is a dedicated closed wrapper for `check-current-worker-login` only; it exposes no other subcommand. It accepts exactly three positional arguments, `JOB_ID ATTEMPT_ID FENCE_GENERATION`, in that order, and rejects any argument beginning with `-` before dispatch. The wrapper pins the canonical control socket path and the fixed subcommand internally; it never forwards caller-selected global options, an alternate socket/path, or another subcommand, and performs no argv passthrough beyond the three positional values it validates itself.

The wrapper is an ergonomics and governance consumer, not a sandbox boundary for the operator UID. Any process already running as an allowed control/operator socket peer can construct the same closed control request directly, and the operator UID retains the pre-existing direct `mmx-admin` path to all six broker actions. P2-1 neither widens nor falsely claims to remove that inherited operator authority.

## 6. Deterministic current-attempt admission

Current authority (this section) is required only for **first admission** of a new logical family. Reading an existing family — §8's existing-family-first recovery — requires none of the checks below; it is evidence retrieval, not authority admission.

The controller first derives immutable host/release/policy and Job-authority facts **outside** the Runtime write transaction: installed `ServiceConfig.proof_base_sha`, one fully loaded `ExecutiveAuthorityPolicy` object plus its digest, the kernel boot-session UUID, and one read-only snapshot of the Job's `requested_authorities`, `worktree`, `allowed_write_paths`, and `validation_commands`. It calls `authorize(...)` on that preflight snapshot before acquiring `BEGIN IMMEDIATE`, producing the exact `AuthorityDecision`; this keeps `Path.expanduser()`/`Path.resolve()` and every policy-file read outside the global Runtime write lock. Preflight refuses when macOS `kern.bootsessionuuid` is unavailable, empty, malformed, or falls back to the process-local `adapter-<pid>` identity. A PID-derived fallback never enters a binding. No filesystem resolution, policy-file read, or `sysctl` subprocess occurs while a Runtime write transaction is held.

Current-attempt validation then runs inside one short `RuntimeStore.transaction()` before any broker I/O. `AttemptRegistry` gains one private token-agnostic join/currentness helper that validates active status, exact Job-status correspondence, fence/quota-fence equality, unexpired lease, and current Job/quota links. `_leased_row` calls that helper and adds only constant-time caller-token comparison. `current_authority_snapshot` calls the same helper, then separately adds caller-supplied `job_id` equality, worker/slot facts, and the P2-specific `SEALED_WORKER` gate. This preserves existing `OPERATOR_HARNESS` lease paths while keeping their epoch/generation currentness owner intact. P2-1 does not duplicate those private SQL invariants in the privileged controller and never exposes the stored token.

The transaction refuses unless all of the following are simultaneously true:

1. Job and Attempt exist and `attempt.job_id == job_id`.
2. Attempt status is one of `CLAIMED`, `RUNNING`, or `CHECKPOINTED`; `CANCEL_REQUESTED` and every terminal state refuse.
3. `COALESCE(attempt.execution_mode, 'SEALED_WORKER') == 'SEALED_WORKER'`; `OPERATOR_HARNESS` is excluded because its currentness is owned by epoch/generation state.
4. Job status is the exact active status corresponding to the Attempt.
5. `jobs.current_attempt_id` and `worker_quota_classes.held_attempt_id` both equal the Attempt.
6. caller-supplied fence equals both `attempts.fence_generation` and the quota fence counter.
7. the persisted lease is not expired at the Runtime clock. Its opaque token is never returned, logged, put in an event, or required from the model/operator request.
8. the transaction's freshly re-read Job row has authority inputs exactly equal to the preflight snapshot (`requested_authorities`, `worktree`, `allowed_write_paths`, and `validation_commands`), and Job, Attempt, precomputed `AuthorityDecision`, and loaded policy hashes agree.
9. the precomputed `AuthorityDecision` includes `REQUEST_WORKER_LOGIN_CHECK`; `authorize(...)`, path expansion, and path resolution are never called inside the transaction.
10. the assigned Worker/Quota remains the current row and the Worker identity is not offline.
11. assigned `worker_id` resolves through `get_slot(worker_id)` and the returned exact `slot_id` equals that worker; the caller cannot override either value.
12. effective-grant validation reuses one canonical deterministic helper factored from `ExecutiveSupervisor._effective_grant`; it receives the already-authorized decision/policy facts as inputs and performs no policy load. The supervisor and P2-1 both call it. An orchestration Attempt missing or failing that grant refuses. Role-null legacy Jobs may use the freshly re-authorized Job grant.
13. the preflight release and policy digest equal the in-memory installed `ServiceConfig` and loaded policy object used by the transaction, while the preflight boot UUID remains the process's validated boot fact. The transaction never re-runs `sysctl`, rereads policy bytes, calls `authorize(...)`, or resolves filesystem paths.

The root-installed control config gains two closed host-composition fields:

```json
{
  "privileged_readiness_armed": true,
  "privileged_broker_socket_path": "/var/run/mastermind-executive/privileged.sock"
}
```

Both default false/absent for backward compatibility. Production composition accepts the socket path only when it equals the fixed reviewed path, requires an injected readiness controller when armed, and refuses a controller injection when unarmed. The installer sets the arm only as part of the existing explicit `--arm-privileged-broker` ceremony; there is no request-, environment-, model-, or CLI-controlled arming override.

The controller derives, rather than accepts:

- action: `executive.worker_auth.verify_only`;
- `slot_id`: the exact closed-catalog slot returned for the current Attempt worker;
- release SHA: installed `ServiceConfig.proof_base_sha`;
- host boot binding: validated kernel boot-session UUID;
- authority policy hash and optional effective-grant digest;
- broker request/operation IDs.

The first slice is local-host only. It binds the current controller boot and exact installed release; P5 later adds authenticated multi-host selection. Hostnames, whichever device is online, an SSH destination, a PID fallback, or a model-provided machine label are never authority.

## 7. Binding and identifiers

Two deterministic identifiers exist, from two different digests, and must never be conflated:

- **Family aggregate ID** — SHA-256 of the canonical UTF-8 JSON logical family key `{"schema_version": "mastermind.executive_privileged_readiness_family_key/v1", "action": "executive.worker_auth.verify_only", "job_id": "JOB-...", "attempt_id": "ATT-...", "fence_generation": 1}` only. Format `pvrf-<first-48-lowercase-hex>`. This id is stable across restarts, releases, boot sessions and policy revisions for the same Job/Attempt/fence/action — it is the Event `aggregate_id` and the exact lookup key for existing-family-first recovery (§8).
- **Operation / broker request ID** — SHA-256 of the canonical UTF-8 JSON complete first-admission binding below, which additionally includes `release_sha`, `boot_id`, `authority_policy_hash`, and `effective_grant_digest`. Format `pvr-<first-48-lowercase-hex>`. This id names the one broker call the family will ever make and is what a later `status --request-id` query uses.

The canonical first-admission binding has exact keys:

```json
{
  "schema_version": "mastermind.executive_privileged_readiness_binding/v1",
  "action": "executive.worker_auth.verify_only",
  "job_id": "JOB-...",
  "attempt_id": "ATT-...",
  "worker_id": "codex-01",
  "quota_class": "codex-native",
  "fence_generation": 1,
  "authority_policy_hash": "<sha256>",
  "effective_grant_digest": null,
  "release_sha": "<40-hex>",
  "boot_id": "<validated kernel boot-session UUID>",
  "slot_id": "codex-01"
}
```

Both digests are recomputed identically from immutable stored fields:

- Event aggregate type: `privileged_readiness`;
- Event aggregate ID: the family aggregate ID (`pvrf-...`) — this gives an exact `WHERE aggregate_type='privileged_readiness' AND aggregate_id=?` lookup using the implicit index created by the existing `UNIQUE(aggregate_type, aggregate_id, sequence)` constraint, with no new index or schema migration, and prevents a release/boot/policy change from ever producing a second family for the same fence;
- INTENT command ID: the operation/broker request ID (`pvr-...`);
- later phase command IDs: `<operation_id>:attempted`, `:terminal`, `:broker_refused`, `:effect_unknown`, or `:reconciled`.

All fit existing Event and broker request grammars. Recomputing either input must reproduce its own ID. A reused ID with different binding/event/broker data is evidence corruption and refuses.

## 8. Event and external-effect state machine

P2-1 uses the existing Runtime Event plane; no sidecar file/table is introduced.

### Existing-family-first recovery

Every invocation first computes the family aggregate ID (`pvrf-...`) from the caller's `job_id`, `attempt_id`, `fence_generation`, and the fixed action, then performs one read-only Event query by exact `aggregate_type='privileged_readiness'` and `aggregate_id=<that family aggregate ID>` — an exact indexed lookup, not a scan — and validates the stored binding payload against the caller's request. The logical effect key `(job_id, attempt_id, fence_generation, executive.worker_auth.verify_only)` and its family aggregate ID are therefore independent of the currently installed release, boot session, or policy digest, which enter only the separate operation/broker request ID (§7).

- If exactly one valid family exists for that logical key, the controller uses its stored binding and operation/request ID for replay or status-only reconciliation. This path remains available after the Attempt completes, is cancelled, is requeued, loses its lease, or the controller restarts. It is evidence recovery only and never re-authorizes or submits an effect.
- If no family exists, the controller may enter fresh current-attempt admission below.
- If more than one family claims the same logical key, or any family has conflicting binding/phase/command identity, the operation is corrupt and fails closed. A new release, boot UUID, policy digest or service process may not create a second effect family for the same Job/Attempt/fence/action.

This lookup is the restart and Attempt-turnover seam. Current authority is required to create an operation, not to read immutable evidence for an operation that already crossed `ATTEMPTED`.

Existing-family-first recovery is a deliberate **authority-free operator evidence path**: once a family exists, any caller may read it, subject to nothing but the exact aggregate lookup above. It creates no new family, performs no effect, and enumerates no other family, Job, or Attempt — it returns previously recorded evidence only. For a family in `ATTEMPTED` or `EFFECT_UNKNOWN`, it performs **at most one** broker status query per invocation, never a retry loop, and returns the result explicitly marked `replayed: true` and currency-labelled per the Evidence currency subsection below.

Both the outside-transaction family lookup here and the inside-transaction absence recheck in first admission below call the same Runtime/Event-owner API seam (§13's `RuntimeStore.list_events(..., connection=None)` with `EventRegistry.list_events` delegating); `control_plane/executive_privileged_authority.py` contains no raw `SELECT ... FROM events`.

### Process-local coalescing and first admission

Before Runtime mutation, the async controller computes the logical family key `(job_id, attempt_id, fence_generation, executive.worker_auth.verify_only)` and uses a process-local singleflight registry keyed exactly on that logical family key — not the complete binding, which is not yet knowable pre-transaction. Concurrent same-family callers await the one owner task; the registry is only in-process coalescing and never durable authority. The owner task revalidates the complete binding inside the Runtime transaction.

Durable safety does not depend on the singleflight registry: the owner task's Runtime transaction uses `BEGIN IMMEDIATE`, unique command IDs, and exact family aggregate-ID validation, so a second process, a singleflight miss, or a registry restart still cannot create a duplicate family.

In one `BEGIN IMMEDIATE` transaction, after current-attempt admission:

1. refuse any malformed or conflicting existing event family (recheck by the same Runtime/Event-owner seam used for existing-family-first recovery);
2. append `PRIVILEGED_READINESS_INTENT` with the exact binding;
3. append `PRIVILEGED_READINESS_ATTEMPTED` before leaving the transaction;
4. return an in-memory `execute_once=True` result only to the owner task that created `ATTEMPTED`.

The successful `ATTEMPTED` commit is the deterministic authority cut and concurrency fence. No second caller may cross the broker write boundary for the same operation. Authority is not reinterpreted from later model text or a changed current Attempt; the resulting receipt remains bound to the frozen original operation.

### One broker call

The service invokes the shared synchronous privileged-broker client through `asyncio.to_thread`. The client sends the exact validated request once and never retries/fails over. The broker peer is the installed control UID; the worker remains non-root and never sees the socket.

A validated broker terminal response appends `PRIVILEGED_READINESS_TERMINAL`. Every controller-side admission refusal occurs before Event creation and uses the existing control-service error envelope; it is never rewritten as a broker result. A validated broker pre-effect refusal appends `PRIVILEGED_READINESS_BROKER_REFUSED` with a closed broker reason domain. A transport loss, malformed post-write response, broker `EFFECT_UNKNOWN`, cancellation after `ATTEMPTED`, or any uncertainty appends `PRIVILEGED_READINESS_EFFECT_UNKNOWN`. The system never infers no effect from a timeout/cancelled task.

**Crash window between `ATTEMPTED` and the broker socket write.** A process crash or kill after the `ATTEMPTED` Event commits but before the broker socket write is issued is indistinguishable from a post-send transport loss and is handled identically: the family remains `EFFECT_UNKNOWN`. It stays `EFFECT_UNKNOWN` until a later invocation's broker status query proves a terminal outcome. If no such proof ever becomes available — the broker never received the request and holds no record of it — resolution requires Attempt/fence turnover (a new logical family under a new Attempt or fence) or a later, separately frozen recovery design. P2-1 performs no automatic retry of the same operation in either case.

### Evidence currency

Every result — fresh or replayed — carries `observed_at_ms` (the wall-clock instant the returned evidence was produced or last validated) and `evidence_currency: CURRENT | HISTORICAL`. `CURRENT` asserts only that the stored `boot_id`, `release_sha`, and `authority_policy_hash` in the family's binding equal freshly re-validated current host facts at `observed_at_ms`; any mismatch, or any inability to prove one of those three facts, yields `HISTORICAL`. The authority-free replay path may perform one bounded kernel boot-UUID observation and one bounded current-policy load/digest read per invocation, both outside any Runtime transaction. Neither currency value asserts READY, credential validity, or provider account identity — both remain point-in-time login-status evidence per §1.

### Replay/reconciliation

A later invocation matching an existing logical effect key never submits the effect again, even when current release, boot, policy, assignment, status, or lease facts have moved. It reads and validates the stored phase family and:

- returns the recorded terminal/refused result when present;
- for `ATTEMPTED` or `EFFECT_UNKNOWN`, performs only `status --request-id` semantics against the broker;
- terminal broker evidence appends `PRIVILEGED_READINESS_RECONCILED` once;
- broker marker remains `EFFECT_UNKNOWN` with no write/retry;
- broker `NOT_FOUND` after `ATTEMPTED` remains `EFFECT_UNKNOWN`; marker-store absence is never asserted as no effect in P2-1.

An observation that does not change durable state appends no duplicate phase Event. Repeated marker/NOT_FOUND observations return the existing typed `EFFECT_UNKNOWN` result. A different current fence creates a different logical effect key. A changed release, boot, worker assignment or policy hash does **not** permit a second family for the same old fence; the existing family remains immutable evidence and grants nothing to a successor Attempt. An unknown operation may be retried only by a new Attempt/fence or a future separately frozen recovery design; P2-1 has no same-Attempt retry epoch.

## 9. Shared broker client boundary

P2-1 creates `control_plane/executive_privileged_client.py` as the one importable transport/validation owner used by both the control service and `scripts/mmx_admin.py`.

The client owns:

- canonical privileged socket path;
- bounded one-frame Unix-socket request/response transport;
- eleven-minute client timeout above the installed broker's ten-minute child budget;
- exact request/status validation;
- exact wire-envelope and terminal-receipt validation;
- no automatic retry/failover.

Refactoring the CLI to this module must preserve all six effect/status behavior and exit codes. It does not create another broker or status store.

## 10. Result contract

The control command returns exact JSON:

```json
{
  "schema_version": "mastermind.executive_privileged_readiness_result/v1",
  "family_id": "pvrf-...",
  "operation_id": "pvr-...",
  "state": "TERMINAL",
  "replayed": false,
  "observed_at_ms": 1800000000000,
  "evidence_currency": "CURRENT",
  "observation_scope": "LOGIN_STATUS_ONLY_NO_READY_ASSERTION",
  "binding": {"...": "secret-free exact binding"},
  "receipt": {"...": "validated broker terminal receipt"},
  "reason_origin": null,
  "reason_code": null
}
```

Allowed login-check result states are `TERMINAL`, `REFUSED`, and `EFFECT_UNKNOWN`. `REFUSED` is reserved for a validated broker refusal, sets `receipt: null`, and carries `reason_origin: "BROKER"` plus a closed `reason_code`; `EFFECT_UNKNOWN` also sets `receipt: null` and has no success claim. Controller admission errors use the control-service error envelope and create no operation result. A reconciled terminal result still reports `TERMINAL` with `replayed: true`. No result contains lease tokens, raw credentials, auth files, provider account identifiers, arbitrary child output, environment dumps or filesystem secrets. Broker receipts already expose only bounded redacted excerpts and hashes.

## 11. Failure and correction behavior

- malformed request or stale Job/Attempt/fence: controller refusal before Event creation and no broker call;
- denied/missing capability: controller refusal before Event creation and no broker call;
- policy hash/effective-grant drift: controller refusal before Event creation and no broker call;
- unknown slot/worker offline or non-SEALED_WORKER mode: controller refusal and no broker call;
- unavailable/malformed kernel boot UUID: controller refusal and no operation ID;
- duplicate exact terminal: deterministic replay, no broker effect;
- Event family corruption: fail closed and quarantine the operation; never overwrite/delete;
- broker transport ambiguity: `EFFECT_UNKNOWN`; status-only reconciliation;
- process crash after `ATTEMPTED` commits but before the broker socket write: identical to transport loss, `EFFECT_UNKNOWN`; stays `EFFECT_UNKNOWN` until a later status query proves terminal, or until Attempt/fence turnover or a separately frozen recovery design resolves it — no automatic retry of the same operation either way;
- current Attempt changes after the `ATTEMPTED` authority cut: existing-family-first recovery remains available, while the receipt stays bound to the original operation and grants the successor Attempt nothing;
- control-service shutdown/cancellation while the synchronous broker call may still be running: preserve `ATTEMPTED`/`EFFECT_UNKNOWN`; the ten-second service shutdown grace is not proof that a broker call with an eleven-minute client bound had no effect;
- provider/vendor failure: terminal failed receipt; not converted to authority or success;
- broker `NOT_FOUND` after an attempted/unknown operation: remain `EFFECT_UNKNOWN`; no no-effect assertion or automatic retry;
- repeated identical status observation: no duplicate Event append.

No correction erases old events or root receipts. A later decision may supersede them, but historical uncertainty remains visible.

## 12. Deterministic versus model work

Every admission, binding, ID, policy check, slot selection, Event phase, broker call and result classification is deterministic native code. The durable Job may include the controller-only request capability, but only two of `control_plane/executive_supervisor.py`'s four current authority-projection sites filter it:

1. `_prompt`'s JSON authorities list — filter `REQUEST_WORKER_LOGIN_CHECK`;
2. `WorkerLaunchSpec.authorities` build — filter it;
3. `_validate_execution_profile`'s write-capable/admission gate — keep the full unfiltered authority set; this gate must see the real grant to enforce it;
4. the durable launch attestation — keep the full unfiltered authority set as historical evidence.

The canonical Job/effective grant persisted in Runtime always retains the full capability; only sites 1 and 2 above filter the model/worker-facing projection. The dedicated worker cannot invoke the capability and must not be shown unusable apparent authority. Attended operator-UID orchestrators consume the separate fixed control CLI, while that same operator principal still retains the inherited direct six-action `mmx-admin` broker bridge. P2-1 makes the Job-bound path durable and auditable; it is not a containment boundary for the operator UID. No model can select the root action, slot, release, host, request ID or retry semantics through the P2 controller. Model text, Job prose, A7 labels, Slack messages and metadata booleans grant nothing.

## 13. Source units

P2-1 changes only these responsibilities:

- `config/authority_map.yml`: checked-in capability and exact scope.
- `control_plane/executive_authority.py`: hard-coded revised allow-list and scope validation.
- `control_plane/executive_runtime.py`: token-free current-attempt validator factored on the existing Attempt owner; `_leased_row` reuses it. Also the one transaction-aware Event-owner API seam (`RuntimeStore.list_events(..., connection=None)` with `EventRegistry.list_events` delegating) that both the outside-transaction family lookup and the inside-transaction absence recheck call; `executive_privileged_authority.py` never issues a raw `SELECT ... FROM events`.
- `control_plane/executive_supervisor.py`: factor/reuse canonical effective-grant validation and filter controller-only authority from exactly the two model/worker-facing projection sites (`_prompt` JSON and `WorkerLaunchSpec.authorities`); `_validate_execution_profile`'s admission gate and the durable launch attestation keep the full unfiltered grant.
- `control_plane/executive_privileged_client.py`: reusable one-send broker client.
- `control_plane/executive_privileged_authority.py`: exact binding, Runtime/Event admission, singleflight and phase/reconciliation controller.
- `control_plane/executive_service.py`: closed config fields, one command and injected default-off controller.
- `scripts/mmx_admin.py`: consume shared broker client without behavior drift.
- `scripts/executive_os_phase1c.py`: one thin CLI subcommand and production composition.
- `ops/executive_os/install.sh`: arm the controller only with the existing broker bootstrap flag and install a fixed exact-release `mmx-control` wrapper; no new service or socket.
- `ops/executive_os/provider_worker_slots.py`: existing closed worker-slot inventory, imported through the existing `ops.executive_os` namespace-package seam already demonstrated by current merged source. P2-1 adds no second slot registry, and the import must be proven from a production-style release-root composition, not only a repo-relative import.
- focused owning tests and this design/implementation plan.

No Runtime database migration is expected. Event types remain on the existing unwhitelisted Event plane. The reviewed control-config schema is extended with the two default-off host-composition fields above; that is an installer/config contract change, not a second authority or Runtime state store. If implementation proves a new table/token/lease/schema migration necessary, stop and return for architecture review rather than improvising.

Changing `authority_map.yml` changes the global policy digest and therefore invalidates active Attempts carrying the prior digest. Production rollout must first prove zero active Attempts (or deliberately terminate/requeue them under existing law), install the new exact release, and only then admit Jobs requesting the new capability. A source merge is not an in-place policy migration for living work.

## 14. Acceptance and production proof

Source acceptance requires:

1. policy refuses YAML-only expansion, missing scope, mandatory-deny drift and all direct root effect names;
2. unarmed/missing/wrong privileged socket configuration refuses startup or command dispatch, while the existing non-privileged service remains backward compatible;
3. current-attempt admission positive test plus wrong Job, Attempt, fence, worker, slot, policy, grant, status, expiry and cancellation negatives;
4. invalid boot UUID/PID fallback refuses before operation creation;
5. token-free current-attempt helper and legacy `_leased_row` share the same lease/fence/current-link checks;
6. OPERATOR_HARNESS and stale/abandoned modes refuse;
7. model-visible worker packet omits the controller-only capability;
8. per-operation singleflight proof: concurrent callers produce exactly one `ATTEMPTED` and one broker effect call;
9. lost response -> status terminal reconciliation with one total effect call;
10. marker and `NOT_FOUND` after `ATTEMPTED` both remain durable `EFFECT_UNKNOWN`, no retry/no no-effect assertion;
11. repeated identical status observations append no duplicate Event;
12. an Attempt may become terminal/requeued and a new controller instance still reconciles the old family from Runtime Events plus broker status without requiring current authority;
13. release/boot/policy movement cannot create a second family for the same Job/Attempt/fence/action;
14. controller admission errors and broker refusals are structurally distinguishable and validated;
15. CLI/controller result contains no lease token/credential/path secret;
16. current protected-base integration tests and independent privilege-boundary review.

Production proof is separate and occurs only after the exact protected release containing the merged broker/revocation owners and P2-1 is installed on the Studio. Before installing the revised authority policy, the current Runtime must prove zero living Attempts or explicitly terminate/requeue them under existing law; otherwise the policy-hash transition is held:

- create/claim one real bounded Job requesting `REQUEST_WORKER_LOGIN_CHECK`;
- invoke the control command through the installed non-root CLI;
- observe the root broker execute only `verify_only` for that Attempt's assigned slot;
- verify the exact login-status observation independently of the child exit code and confirm no READY claim is emitted;
- read terminal result after control-client interruption without another effect;
- prove stale fence, wrong Job/Attempt and direct dedicated-worker broker socket access refuse;
- read back the installed broker policy and record that the operator UID still has the inherited direct six-action `mmx-admin` grant; do not claim the `mmx-control` wrapper contains that principal;
- prove no password prompt after the one-time bootstrap.

Until that path is observed, P2-1 is `BUILT_NOT_PROVEN`, not live autonomy.

## 15. Deferred boundaries

P2-1 intentionally defers:

- `verify_ready`, credential expiry/rotation and provider MFA/consent to P3;
- service start/stop/restart request authority to a separate P2 action review;
- transaction recovery to a separate correction capability;
- authenticated installer/update/rollback and online grant revocation to P4;
- multi-host identity/selection and second-host proof to P5;
- direct arbitrary worker access to the root broker permanently;
- narrowing or removing the operator UID's inherited direct six-action broker grant. That host-containment change requires a separate reviewed P4/P2 hardening wave because it changes the already-merged bootstrap and emergency-administration contract.

The next dependency after P2-1 is one secret-free credential renewal vertical, not expansion into generic administrator access.
