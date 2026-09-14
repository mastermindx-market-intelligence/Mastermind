# Executive Job-Bound Worker Readiness Design

**Status:** architecture freeze candidate for P2-1 of the Chairman-approved permanent unattended privileged-execution program. This document grants no runtime authority, installs nothing, and does not arm a root effect.

**Source:** protected Mastermind `af9fce32861f9c1496b85a580e3569712170d92b`; Skillpack `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1.

**Required dependency:** Mastermind PR #613 exact semantic head `2259596e943dabe566203e8dd450888661d4f00c`, or its protected merged descendant with byte-equivalent privileged broker/client contracts. P2-1 must not duplicate or fork that actuator.

## 1. Outcome, machine job, and 10/10 end state

The user job is simple: an assigned Codex or Claude worker should finish approved work without stopping to ask Chris to type an administrator password for a routine, already-reviewed host check.

The P2-1 machine job is narrower: a current Executive Job/Attempt may request **verification of its own assigned worker slot's provider-auth readiness** through the trusted Executive controller. The controller must prove the current Job, Attempt, fence, policy, worker assignment, installed release and current host boot, then invoke exactly the broker action `executive.worker_auth.verify_only`. The worker never receives root, a reusable credential, the broker socket, a lease token, or a caller-selected executable/path/action/slot.

The full 10/10 end state remains the permanent program: useful root operations are admitted from current durable authority, executed once through a fixed actuator, reconciled after interruption, corrected or revoked safely, consumed by real native clients, and proven on each intended host. P2-1 is one vertical slice toward that outcome, not a claim that credential rotation, arbitrary future upgrades, service control, fleet selection, vendor MFA, or all sudo prompts are solved.

## 2. Capability ledger at freeze

| Capability | State | Evidence / boundary |
|---|---|---|
| Six-action root broker and non-root operator CLI | `BUILT_NOT_PROVEN` | PR #613; merge/install/host proof still separate |
| Read-only broker result reconciliation | `BUILT_NOT_PROVEN` | PR #613 status request; never re-executes |
| Administrative broker revocation | `BUILT_NOT_PROVEN` | PR #621; no live grant revocation or updater |
| Current Job/Attempt authority -> worker readiness request | `NOT_BUILT` | This P2-1 design |
| Secret-free credential enrollment/renewal | `NOT_BUILT` | P3; vendor/provider evidence required |
| Authenticated passwordless release update/rollback | `NOT_BUILT` | P4; first bootstrap remains administrator-gated |
| Multi-host/fleet selection and proof | `NOT_BUILT` | P5 |

## 3. Canonical owners and no-rebuild boundary

P2-1 extends existing owners only:

- `Executive OS RuntimeStore` owns Job, Attempt, Worker, quota, fence, event and command-id truth.
- `ExecutiveAuthorityPolicy` owns checked-in worker capability admission and policy digest.
- the existing control service owns trusted deterministic orchestration on the installed host.
- PR #613's privileged broker owns fixed root execution plus its marker/receipt evidence.
- `provider_worker_slots.py` owns the closed worker-slot inventory.
- the installed release and controller environment attestation own release and boot identity.

P2-1 creates no table, queue, scheduler, lease, token registry, permission service, credential store, retry ledger, host registry, transcript plane or second lifecycle. Its durable records are ordinary `events` rows. Broker receipts remain subordinate evidence of one host effect, never an authority source.

## 4. Deliberately narrow capability

Add one checked-in Executive capability:

```text
REQUEST_WORKER_READINESS
```

Its policy scope is exactly:

```text
current_attempt_assigned_worker_slot
```

This capability means “the trusted controller may ask the fixed broker to verify the current Attempt's already-assigned reviewed slot.” It does **not** mean `SERVICE_CONTROL`, `CREDENTIAL_ADMIN`, credential enrollment, recovery, arbitrary slot inspection, or permission to call the broker directly.

Existing mandatory denies remain, including `SERVICE_CONTROL` and `CREDENTIAL_ADMIN`. Adding a YAML string alone remains insufficient: `ExecutiveAuthorityPolicy.load()` must pin the exact revised allow-list and scope value in code.

The first root action is fixed to:

```text
executive.worker_auth.verify_only
```

`verify_ready` is excluded because it requires a truthful credential-expiry source and may execute a provider canary/write readiness state; that belongs to P3. `recover_transaction` and all service actions remain excluded.

## 5. External command contract

The existing Executive control service gains one command and the thin operator CLI gains one matching subcommand:

```text
verify-current-worker-readiness JOB_ID ATTEMPT_ID FENCE_GENERATION
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

The command is available only when the control service is `READY` and through its existing peer-authenticated Unix socket. Worker UIDs do not gain access to the privileged broker. This operator/control consumer is the first production-shaped consumer; a later bounded worker-facing tool may submit the same typed request through the current control owner without changing the authority model.

## 6. Deterministic current-attempt admission

Admission runs inside one `RuntimeStore.transaction()` before any broker I/O. It joins `attempts`, `jobs`, `worker_quota_classes`, and `workers`, and refuses unless all of the following are simultaneously true:

1. Job and Attempt exist and `attempt.job_id == job_id`.
2. Attempt status is one of `CLAIMED`, `RUNNING`, or `CHECKPOINTED`; `CANCEL_REQUESTED` and every terminal state refuse.
3. Job status is the exact active status corresponding to the Attempt.
4. `jobs.current_attempt_id` and `worker_quota_classes.held_attempt_id` both equal the Attempt.
5. caller-supplied fence equals both `attempts.fence_generation` and the quota fence counter.
6. the persisted lease is not expired at the Runtime clock. Its opaque token is never returned, logged, put in an event, or required from the model/operator request.
7. Job, Attempt, and freshly loaded policy hashes agree.
8. fresh `ExecutiveAuthorityPolicy.authorize(...)` succeeds for the Job's stored authority/write/test scope and includes `REQUEST_WORKER_READINESS`.
9. the assigned Worker/Quota remains the current row and the Worker identity is online.
10. assigned `worker_id` resolves through the closed provider-slot catalog; the caller cannot override it.
11. when an orchestration Attempt has an effective grant, its canonical JSON digest, schema, Job identity and authority set validate and include `REQUEST_WORKER_READINESS`. An orchestration Attempt missing its effective grant refuses. Role-null legacy Jobs may use the freshly re-authorized Job grant.

The controller derives, rather than accepts:

- action: `executive.worker_auth.verify_only`;
- `slot_id`: current Attempt `worker_id` after catalog resolution;
- release SHA: installed `ServiceConfig.proof_base_sha`;
- host boot binding: current `ProcessInspector.boot_session_id()`;
- authority policy hash and optional effective-grant digest;
- broker request/operation IDs.

The first slice is local-host only. It binds the current controller boot and exact installed release; P5 later adds authenticated multi-host selection. Hostnames, whichever device is online, an SSH destination, or a model-provided machine label are never authority.

## 7. Binding and identifiers

The canonical binding has exact keys:

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
  "boot_id": "<controller-observed boot identity>",
  "slot_id": "codex-01"
}
```

Canonical UTF-8 JSON is SHA-256 hashed. Identifiers are derived only from that digest:

- operation / broker request ID: `pvr-<first-48-lowercase-hex>`;
- Event aggregate type: `privileged_readiness`;
- Event aggregate ID: the operation ID;
- INTENT command ID: operation ID;
- later phase command IDs: `<operation_id>:attempted`, `:terminal`, `:refused`, `:effect_unknown`, `:reconciled`, or `:proven_no_effect`.

All fit existing Event and broker request grammars. Recomputing the binding must reproduce the operation ID. A reused ID with different binding/event/broker data is evidence corruption and refuses.

## 8. Event and external-effect state machine

P2-1 uses the existing EventStore; no sidecar file/table is introduced.

### First admission

In one transaction, after current-attempt admission:

1. refuse any malformed or conflicting existing event family;
2. append `PRIVILEGED_READINESS_INTENT` with the exact binding;
3. append `PRIVILEGED_READINESS_ATTEMPTED` before leaving the transaction;
4. return an in-memory `execute_once=True` result to the one caller that created `ATTEMPTED`.

The `ATTEMPTED` phase is the concurrency fence. No second caller may cross the broker write boundary for the same operation.

### One broker call

The service invokes the shared synchronous privileged-broker client through `asyncio.to_thread`. The client sends the exact validated request once and never retries/fails over. The broker peer is the installed control UID; the worker remains non-root and never sees the socket.

A validated broker terminal response appends `PRIVILEGED_READINESS_TERMINAL`. A validated pre-effect broker refusal appends `PRIVILEGED_READINESS_REFUSED`. A transport loss, malformed post-write response, broker `EFFECT_UNKNOWN`, cancellation after `ATTEMPTED`, or any uncertainty appends `PRIVILEGED_READINESS_EFFECT_UNKNOWN`. The system never infers no effect from a timeout/cancelled task.

### Replay/reconciliation

A later invocation with the same current binding never submits the effect again. It reads the phase family and:

- returns the recorded terminal/refused result when present;
- for `ATTEMPTED` or `EFFECT_UNKNOWN`, performs only `status --request-id` semantics against the broker;
- terminal broker evidence appends `PRIVILEGED_READINESS_RECONCILED`;
- broker marker remains `EFFECT_UNKNOWN` with no write/retry;
- broker `NOT_FOUND` appends `PRIVILEGED_READINESS_PROVEN_NO_EFFECT` and returns a typed refusal requiring a separately authorized new operation. P2-1 does not automatically create or execute that new operation.

A different current fence, release, boot, worker assignment or policy hash yields a different operation ID. The stale operation remains immutable evidence and grants nothing to the new Attempt.

## 9. Shared broker client boundary

P2-1 creates `control_plane/executive_privileged_client.py` as the one importable transport/validation owner used by both the control service and `scripts/mmx_admin.py`.

The client owns:

- canonical privileged socket path;
- bounded one-frame Unix-socket request/response transport;
- 660-second client timeout above the installed broker's 600-second child budget;
- exact request/status validation;
- exact wire-envelope and terminal-receipt validation;
- no automatic retry/failover.

Refactoring the CLI to this module must preserve all six effect/status behavior and exit codes. It does not create another broker or status store.

## 10. Result contract

The control command returns exact JSON:

```json
{
  "schema_version": "mastermind.executive_privileged_readiness_result/v1",
  "operation_id": "pvr-...",
  "state": "TERMINAL",
  "replayed": false,
  "binding": {"...": "secret-free exact binding"},
  "receipt": {"...": "validated broker terminal receipt"},
  "reason_code": null
}
```

Allowed states are `TERMINAL`, `REFUSED`, `EFFECT_UNKNOWN`, and `PROVEN_NO_EFFECT`. A reconciled terminal result still reports `TERMINAL` with `replayed: true`. No result contains lease tokens, raw credentials, auth files, provider account identifiers, arbitrary child output, environment dumps or filesystem secrets. Broker receipts already expose only bounded redacted excerpts and hashes.

## 11. Failure and correction behavior

- malformed request or stale Job/Attempt/fence: known refusal, no Event or broker call;
- denied/missing capability: known refusal, no Event or broker call;
- policy hash/effective-grant drift: evidence refusal, no broker call;
- unknown slot/worker offline: refusal, no broker call;
- duplicate exact terminal: deterministic replay, no broker effect;
- Event family corruption: fail closed and quarantine the operation; never overwrite/delete;
- broker transport ambiguity: `EFFECT_UNKNOWN`; status-only reconciliation;
- current Attempt cancellation/expiry after INTENT but before broker call: the creator rechecks current binding immediately before external I/O; if no longer current, append `REFUSED` without crossing the broker boundary;
- current Attempt changes during the external effect: receipt remains bound to the original operation; it does not grant the successor Attempt anything;
- provider/vendor failure: terminal failed receipt; not converted to authority or success;
- broker `NOT_FOUND` after an attempted/unknown operation: proven no broker admission, but P2-1 still requires a new explicit operation rather than auto-retry.

No correction erases old events or root receipts. A later decision may supersede them, but historical uncertainty remains visible.

## 12. Deterministic versus model work

Every admission, binding, ID, policy check, slot selection, Event phase, broker call and result classification is deterministic native code. The language model may be assigned a Job whose reviewed authority includes the request capability, but it cannot select the root action, slot, release, host, request ID or retry semantics. Model text, Job prose, A7 labels, Slack messages and metadata booleans grant nothing.

## 13. Source units

P2-1 changes only these responsibilities:

- `config/authority_map.yml`: checked-in capability and exact scope.
- `control_plane/executive_authority.py`: hard-coded revised allow-list and scope validation.
- `control_plane/executive_privileged_client.py`: reusable one-send broker client.
- `control_plane/executive_privileged_authority.py`: exact binding, Runtime/Event admission, phase/reconciliation controller.
- `control_plane/executive_service.py`: one closed command and injected controller.
- `scripts/mmx_admin.py`: consume shared broker client without behavior drift.
- `scripts/executive_os_phase1c.py`: one thin CLI subcommand and production composition.
- focused owning tests and this design/implementation plan.

No Runtime database migration is expected. If implementation proves a new table/token/lease/schema migration necessary, stop and return for architecture review rather than improvising.

## 14. Acceptance and production proof

Source acceptance requires:

1. policy refuses YAML-only expansion, missing scope, mandatory-deny drift and all direct root effect names;
2. current-attempt admission positive test plus wrong Job, Attempt, fence, worker, slot, policy, grant, status, expiry and cancellation negatives;
3. concurrency proof: exactly one caller creates `ATTEMPTED` and exactly one broker effect call occurs;
4. lost response -> status terminal reconciliation with one total effect call;
5. marker -> durable `EFFECT_UNKNOWN`, no retry;
6. `NOT_FOUND` -> `PROVEN_NO_EFFECT`, no automatic effect;
7. restart/new controller instance reconstructs state only from Runtime events and broker status;
8. CLI/controller result contains no lease token/credential/path secret;
9. current protected-base integration tests and independent privilege-boundary review.

Production proof is separate and occurs only after PR #613 is merged and the exact protected release is installed on the Studio:

- create/claim one real bounded Job requesting `REQUEST_WORKER_READINESS`;
- invoke the control command through the installed non-root CLI;
- observe the root broker execute only `verify_only` for that Attempt's assigned slot;
- verify target/readiness evidence independently of the child exit code;
- read terminal result after control-client interruption without another effect;
- prove stale fence, wrong Job/Attempt and unauthorized direct worker socket access refuse;
- prove no password prompt after the one-time bootstrap.

Until that path is observed, P2-1 is `BUILT_NOT_PROVEN`, not live autonomy.

## 15. Deferred boundaries

P2-1 intentionally defers:

- `verify_ready`, credential expiry/rotation and provider MFA/consent to P3;
- service start/stop/restart request authority to a separate P2 action review;
- transaction recovery to a separate correction capability;
- authenticated installer/update/rollback and online grant revocation to P4;
- multi-host identity/selection and second-host proof to P5;
- direct arbitrary worker access to the root broker permanently.

The next dependency after P2-1 is one secret-free credential renewal vertical, not expansion into generic administrator access.
