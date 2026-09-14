# Executive Job-Bound Worker Readiness Design

**Status:** architecture freeze candidate for P2-1 of the Chairman-approved permanent unattended privileged-execution program. This document grants no runtime authority, installs nothing, and does not arm a root effect.

**Source:** protected Mastermind `af9fce32861f9c1496b85a580e3569712170d92b`; Skillpack `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1.

**Required dependency:** Mastermind PR #613 exact semantic head `2259596e943dabe566203e8dd450888661d4f00c`, or its protected merged descendant with byte-equivalent privileged broker/client contracts. P2-1 must not duplicate or fork that actuator.

## 1. Outcome, machine job, and 10/10 end state

The user job is simple: an assigned reviewed worker slot should finish approved work without stopping to ask Chris to type an administrator password for a routine, already-reviewed host check. P2-1 proves the current closed Codex slot catalog; a future separately reviewed slot-catalog extension is required before claiming Claude worker coverage.

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

Existing mandatory denies remain, including `SERVICE_CONTROL` and `CREDENTIAL_ADMIN`. Adding a YAML string alone remains insufficient: `ExecutiveAuthorityPolicy.load()` must pin the exact revised allow-list and scope value in code. The scope string is declarative policy metadata, not slot evidence; only the deterministic controller's current Job/Attempt join enforces the current-assigned-slot boundary. No caller or model may treat an `AuthorityDecision` containing this capability as proof of a worker, slot, fence, host or root action.

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

The command is available only when the control service is `READY`, `privileged_readiness_armed` is true in the root-installed control config, and the request arrives through its existing peer-authenticated Unix socket. Worker UIDs do not gain access to the privileged broker. The installer publishes one fixed non-root `mmx-control` wrapper to the exact installed release and control socket so attended Codex/Claude orchestrators running as the approved operator UID can invoke the command for a named Executive Job/Attempt without discovering a mutable source path. This first consumer is acting on behalf of the selected durable Job; it does not prove that an arbitrary dedicated worker can invoke the command itself. The wrapper accepts no socket/path/action override. A later bounded dedicated-worker tool must bind the caller to its own current Attempt before submitting the same typed request through the current control owner.

## 6. Deterministic current-attempt admission

The controller first derives immutable host/release/policy facts **outside** the Runtime write transaction: installed `proof_base_sha`, the checked-in authority policy plus digest, and the kernel boot-session UUID. This preflight must refuse when macOS `kern.bootsessionuuid` is unavailable, empty, malformed, or falls back to the process-local `adapter-<pid>` identity. A PID-derived fallback never enters a binding.

Current-attempt validation then runs inside one short `RuntimeStore.transaction()` before any broker I/O. `AttemptRegistry` gains a token-free current-row helper on the same canonical owner as `_leased_row`; `_leased_row` delegates its shared currentness/fence/lease/link checks to that helper and adds only caller-token possession. P2-1 does not duplicate those private SQL invariants in the privileged controller and never exposes the stored token.

The transaction refuses unless all of the following are simultaneously true:

1. Job and Attempt exist and `attempt.job_id == job_id`.
2. Attempt status is one of `CLAIMED`, `RUNNING`, or `CHECKPOINTED`; `CANCEL_REQUESTED` and every terminal state refuse.
3. `COALESCE(attempt.execution_mode, 'SEALED_WORKER') == 'SEALED_WORKER'`; `OPERATOR_HARNESS` is excluded because its currentness is owned by epoch/generation state.
4. Job status is the exact active status corresponding to the Attempt.
5. `jobs.current_attempt_id` and `worker_quota_classes.held_attempt_id` both equal the Attempt.
6. caller-supplied fence equals both `attempts.fence_generation` and the quota fence counter.
7. the persisted lease is not expired at the Runtime clock. Its opaque token is never returned, logged, put in an event, or required from the model/operator request.
8. Job, Attempt, and the preloaded immutable policy hashes agree.
9. fresh `ExecutiveAuthorityPolicy.authorize(...)` succeeds for the Job's stored authority/write/test scope and includes `REQUEST_WORKER_READINESS`.
10. the assigned Worker/Quota remains the current row and the Worker identity is not offline.
11. assigned `worker_id` resolves through `get_slot(worker_id)` and the returned exact `slot_id` equals that worker; the caller cannot override either value.
12. effective-grant validation reuses one canonical pure helper factored from `ExecutiveSupervisor._effective_grant`; the supervisor and P2-1 both call it. An orchestration Attempt missing or failing that grant refuses. Role-null legacy Jobs may use the freshly re-authorized Job grant.
13. the preflight release, boot UUID and policy digest still equal the immutable service/policy facts observed by the transaction.

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
  "boot_id": "<validated kernel boot-session UUID>",
  "slot_id": "codex-01"
}
```

Canonical UTF-8 JSON is SHA-256 hashed. Identifiers are derived only from that digest:

- operation / broker request ID: `pvr-<first-48-lowercase-hex>`;
- Event aggregate type: `privileged_readiness`;
- Event aggregate ID: the operation ID;
- INTENT command ID: operation ID;
- later phase command IDs: `<operation_id>:attempted`, `:terminal`, `:broker_refused`, `:effect_unknown`, or `:reconciled`.

All fit existing Event and broker request grammars. Recomputing the binding must reproduce the operation ID. A reused ID with different binding/event/broker data is evidence corruption and refuses.

## 8. Event and external-effect state machine

P2-1 uses the existing EventStore; no sidecar file/table is introduced.

### Existing-family-first recovery

Every invocation first performs a read-only Event query by exact `job_id`, `attempt_id`, and aggregate type `privileged_readiness`, then validates stored binding payloads against the caller's `fence_generation` and fixed action. The logical effect key is therefore `(job_id, attempt_id, fence_generation, executive.worker_auth.verify_only)`, independent of the currently installed release or boot.

- If exactly one valid family exists for that logical key, the controller uses its stored binding and operation/request ID for replay or status-only reconciliation. This path remains available after the Attempt completes, is cancelled, is requeued, loses its lease, or the controller restarts. It is evidence recovery only and never re-authorizes or submits an effect.
- If no family exists, the controller may enter fresh current-attempt admission below.
- If more than one family claims the same logical key, or any family has conflicting binding/phase/command identity, the operation is corrupt and fails closed. A new release, boot UUID, policy digest or service process may not create a second effect family for the same Job/Attempt/fence/action.

This lookup is the restart and Attempt-turnover seam. Current authority is required to create an operation, not to read immutable evidence for an operation that already crossed `ATTEMPTED`.

### Process-local coalescing and first admission

Before Runtime mutation, the async controller derives a preview binding and uses a process-local per-operation singleflight registry. Concurrent same-operation callers await the one owner task; the registry is only in-process coalescing and never durable authority. The owner task revalidates the complete binding inside the Runtime transaction.

In one transaction, after current-attempt admission:

1. refuse any malformed or conflicting existing event family;
2. append `PRIVILEGED_READINESS_INTENT` with the exact binding;
3. append `PRIVILEGED_READINESS_ATTEMPTED` before leaving the transaction;
4. return an in-memory `execute_once=True` result only to the owner task that created `ATTEMPTED`.

The successful `ATTEMPTED` commit is the deterministic authority cut and concurrency fence. No second caller may cross the broker write boundary for the same operation. Authority is not reinterpreted from later model text or a changed current Attempt; the resulting receipt remains bound to the frozen original operation.

### One broker call

The service invokes the shared synchronous privileged-broker client through `asyncio.to_thread`. The client sends the exact validated request once and never retries/fails over. The broker peer is the installed control UID; the worker remains non-root and never sees the socket.

A validated broker terminal response appends `PRIVILEGED_READINESS_TERMINAL`. Every controller-side admission refusal occurs before Event creation and uses the existing control-service error envelope; it is never rewritten as a broker result. A validated broker pre-effect refusal appends `PRIVILEGED_READINESS_BROKER_REFUSED` with a closed broker reason domain. A transport loss, malformed post-write response, broker `EFFECT_UNKNOWN`, cancellation after `ATTEMPTED`, or any uncertainty appends `PRIVILEGED_READINESS_EFFECT_UNKNOWN`. The system never infers no effect from a timeout/cancelled task.

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

Allowed readiness-result states are `TERMINAL`, `REFUSED`, and `EFFECT_UNKNOWN`. `REFUSED` is reserved for a validated broker refusal and carries `reason_origin: "BROKER"` plus a closed `reason_code`; controller admission errors use the control-service error envelope and create no operation result. A reconciled terminal result still reports `TERMINAL` with `replayed: true`. No result contains lease tokens, raw credentials, auth files, provider account identifiers, arbitrary child output, environment dumps or filesystem secrets. Broker receipts already expose only bounded redacted excerpts and hashes.

## 11. Failure and correction behavior

- malformed request or stale Job/Attempt/fence: controller refusal before Event creation and no broker call;
- denied/missing capability: controller refusal before Event creation and no broker call;
- policy hash/effective-grant drift: controller refusal before Event creation and no broker call;
- unknown slot/worker offline or non-SEALED_WORKER mode: controller refusal and no broker call;
- unavailable/malformed kernel boot UUID: controller refusal and no operation ID;
- duplicate exact terminal: deterministic replay, no broker effect;
- Event family corruption: fail closed and quarantine the operation; never overwrite/delete;
- broker transport ambiguity: `EFFECT_UNKNOWN`; status-only reconciliation;
- current Attempt changes after the `ATTEMPTED` authority cut: existing-family-first recovery remains available, while the receipt stays bound to the original operation and grants the successor Attempt nothing;
- provider/vendor failure: terminal failed receipt; not converted to authority or success;
- broker `NOT_FOUND` after an attempted/unknown operation: remain `EFFECT_UNKNOWN`; no no-effect assertion or automatic retry;
- repeated identical status observation: no duplicate Event append.

No correction erases old events or root receipts. A later decision may supersede them, but historical uncertainty remains visible.

## 12. Deterministic versus model work

Every admission, binding, ID, policy check, slot selection, Event phase, broker call and result classification is deterministic native code. The durable Job may include the controller-only request capability, but the worker/model-facing job packet and effective-grant projection must filter `REQUEST_WORKER_READINESS`; the dedicated worker cannot invoke it and must not be shown unusable apparent authority. Attended operator-UID orchestrators consume the separate fixed control CLI. No model can select the root action, slot, release, host, request ID or retry semantics. Model text, Job prose, A7 labels, Slack messages and metadata booleans grant nothing.

## 13. Source units

P2-1 changes only these responsibilities:

- `config/authority_map.yml`: checked-in capability and exact scope.
- `control_plane/executive_authority.py`: hard-coded revised allow-list and scope validation.
- `control_plane/executive_runtime.py`: token-free current-attempt validator factored on the existing Attempt owner; `_leased_row` reuses it.
- `control_plane/executive_supervisor.py`: factor/reuse canonical effective-grant validation and filter controller-only authority from model packets.
- `control_plane/executive_privileged_client.py`: reusable one-send broker client.
- `control_plane/executive_privileged_authority.py`: exact binding, Runtime/Event admission, singleflight and phase/reconciliation controller.
- `control_plane/executive_service.py`: closed config fields, one command and injected default-off controller.
- `scripts/mmx_admin.py`: consume shared broker client without behavior drift.
- `scripts/executive_os_phase1c.py`: one thin CLI subcommand and production composition.
- `ops/executive_os/install.sh`: arm the controller only with the existing broker bootstrap flag and install a fixed exact-release `mmx-control` wrapper; no new service or socket.
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

Production proof is separate and occurs only after PR #613 is merged and the exact protected release is installed on the Studio. Before installing the revised authority policy, the current Runtime must prove zero living Attempts or explicitly terminate/requeue them under existing law; otherwise the policy-hash transition is held:

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
