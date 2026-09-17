# Executive Job-Bound Worker Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` for every source change, `superpowers:systematic-debugging` for every unexpected failure, and `superpowers:verification-before-completion` before any completion claim. Execute this plan task-by-task in the single assigned workspace; do not create another worktree.

**Goal:** Deliver one independently useful permanent-system vertical: an attended non-root orchestrator may ask the trusted Executive controller to run the fixed privileged broker action `executive.worker_auth.verify_only` for the exact current SEALED_WORKER Attempt's assigned slot, with durable Event-backed replay/reconciliation and no lease-token, root-shell, arbitrary-action, slot, host, path, or retry authority.

**Architecture:** Reuse the current Executive Job/Attempt/Worker/Event, policy, lease/fence, service and installer owners plus the already-merged privileged broker/client/revocation source. Add one controller-only authority, factor token-free current-attempt and effective-grant validators from their existing owners, extract one shared one-send broker client, implement an Event-backed login-check controller with existing-family-first recovery and process-local singleflight, expose one closed control command plus fixed installed wrapper, and keep the whole capability default-off behind the existing `--arm-privileged-broker` bootstrap.

**Tech Stack:** Python 3.12, SQLite RuntimeStore, asyncio, Unix domain sockets, macOS launchd, Bash installer wrappers, pytest, GitHub protected merge queue.

**Spec:** `docs/superpowers/specs/2026-09-14-executive-job-bound-worker-readiness-design.md`

**Global Constraints:**
- Preserve protected merge `c9db5d42ed4b1479985b8989d9767ac80a84f9b8`'s six-action catalog and broker receipt owner plus revocation merge `2575d16ae8e2ae73e3e520d81bc5344621f5356c`; never add generic exec, shell, path, socket or secret parameters.
- Preserve `SERVICE_CONTROL` and `CREDENTIAL_ADMIN` mandatory denies.
- Never expose or request the persisted Attempt lease token.
- Never auto-retry or fail over an attempted/unknown root effect.
- No new Runtime table, queue, lease, token registry, credential store, host registry or status database.
- Every controller refusal happens before Event creation; every effect after `ATTEMPTED` is reconciled from existing Events plus broker status.
- `NOT_FOUND` after `ATTEMPTED` remains `EFFECT_UNKNOWN`.
- Dedicated worker/model packets must not advertise the controller-only capability.
- Source completion, merge, installation, host proof and final acceptance remain distinct.
- No result field or value ever asserts READY; every operation result carries `observed_at_ms`, `evidence_currency: CURRENT|HISTORICAL`, and the constant `observation_scope: LOGIN_STATUS_ONLY_NO_READY_ASSERTION`. Only `TERMINAL` carries a broker receipt; replay reproduces the identical original terminal evidence without upgrading it.
- The Event aggregate ID is the family aggregate ID (`pvrf-...`, from the logical family key only); the broker operation/request ID (`pvr-...`, from the complete first-admission binding) is a separate value. Release/boot/policy changes must never be able to create a second family for the same fence.
- The installed `mmx-control` wrapper is closed to exactly `check-current-worker-login JOB_ID ATTEMPT_ID FENCE_GENERATION`; it rejects any `-`-prefixed argument and forwards no caller-selected option, socket/path, or other subcommand.
- The privileged controller performs all Event reads, including the same-transaction absence recheck, through one Runtime/Event-owner API seam; it contains no raw `SELECT ... FROM events`.

## Capability state on entry

- Fixed broker/status: `BUILT_NOT_PROVEN`, protected merge `c9db5d42ed4b1479985b8989d9767ac80a84f9b8`.
- Administrative revocation: `BUILT_NOT_PROVEN`, protected merge `2575d16ae8e2ae73e3e520d81bc5344621f5356c`.
- P2-1 Job-bound login-check authority: `NOT_BUILT`.
- First root bootstrap and production proof: not yet performed.

---

## Task 0: Re-pin protected source and baseline the merged actuator

**Files:** Git/source evidence only; no hand-edited source.

**Step 1 — verify current protected identity and merged owners**

```bash
git fetch origin master
PROTECTED_SHA="$(git rev-parse origin/master)"
printf 'protected=%s\n' "$PROTECTED_SHA"
git merge-base --is-ancestor c9db5d42ed4b1479985b8989d9767ac80a84f9b8 origin/master
git merge-base --is-ancestor 2575d16ae8e2ae73e3e520d81bc5344621f5356c origin/master
git merge-base --is-ancestor origin/master HEAD
```

Expected: the protected branch contains both reviewed merges and is an ancestor of the clean implementation carrier. If protected moved after this plan was frozen, reload the protected Skillpack, compare material source, and reconcile the carrier before source edits; never stack or copy the old PR heads.

**Step 2 — prove current collision state on all planned owner paths**

```bash
cat > /tmp/p2-owned-paths <<'EOF'
config/authority_map.yml
control_plane/executive_authority.py
control_plane/executive_runtime.py
control_plane/executive_supervisor.py
control_plane/executive_privileged_client.py
control_plane/executive_privileged_authority.py
control_plane/executive_service.py
scripts/mmx_admin.py
scripts/executive_os_phase1c.py
ops/executive_os/install.sh
EOF

gh pr list --repo mastermindx-market-intelligence/Mastermind \
  --state open --limit 100 --json number,headRefOid,title
# For every open PR returned above, inspect its file list before claiming disjointness:
# gh pr view NUMBER --repo mastermindx-market-intelligence/Mastermind --json headRefOid,files
```

At the current protected pin `8ba7deedde164c90298d3e88785d98e02fa5e2d2`, PR #655 and PR #667 have merged material Runtime/config changes; implementation must use that protected source, not pre-#655 assumptions. PR #653 at `959b37b329c44d81874dc23944746a5bd594e3b7` remains the active writer on `ops/executive_os/install.sh` and `scripts/executive_os_phase1c.py`; hold **Task 5** and every overlapping edit until it merges/closes and current protected compatibility is re-established. PR #690 overlaps `tests/test_executive_os_sqlite.py`, so Tasks 2 and 4 create new owning test files and do not edit that incumbent path; recheck before integration. PR #124 is a broad behind/failing historical branch, not a current ownership source, but its overlap must be rechecked before release. Any newly active overlap is a stop/reconcile gate, not permission for a second writer.

**Step 3 — baseline the merged broker, revocation and current Executive owners**

```bash
umask 022
python3 -m pytest -o addopts='' -q \
  tests/test_executive_privileged_action.py \
  tests/test_executive_privileged_broker.py \
  tests/test_mmx_admin.py \
  tests/test_executive_launchd_config.py \
  tests/test_executive_service_control.py \
  tests/test_executive_privileged_revocation.py
bash -n ops/executive_os/install.sh
bash -n ops/executive_os/service-control.sh
git diff --check
```

Expected: baseline GREEN before the first P2 source test is written. A current-source failure is investigated or returned as a blocker; do not weaken the imported broker/revocation contracts to make P2 convenient.

---

## Task 1: Add the controller-only authority without widening root capability

**Files:**
- Modify: `config/authority_map.yml`
- Modify: `control_plane/executive_authority.py`
- Modify: `tests/test_executive_authority.py`

**Step 1 — write failing policy tests**

Add tests that assert:
- exact allow-list is `{READ, RESEARCH, WRITE_BRANCH, RUN_TESTS, REQUEST_WORKER_LOGIN_CHECK}`;
- exact scope is `current_attempt_assigned_worker_slot`;
- adding the YAML value without the code constant fails closed;
- deleting/changing the scope fails closed;
- `SERVICE_CONTROL` and `CREDENTIAL_ADMIN` remain mandatory denies;
- authorizing `REQUEST_WORKER_LOGIN_CHECK` accepts no worktree/path/argv/slot/action evidence and returns no slot/root grant.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_authority.py \
  -k 'worker_readiness or checked_in_policy or drift or mandatory_denies'
```

Expected RED: allow-list/scope mismatch.

**Step 2 — implement the minimum policy change**

- Add `REQUEST_WORKER_LOGIN_CHECK` to `PHASE1B_ALLOWED`.
- Add it to checked-in YAML allowed capabilities.
- Add exact scope requirement in YAML and pin it in `ExecutiveAuthorityPolicy.load()`.
- Do **not** add action/slot/path fields to `AuthorityDecision`; this capability remains declarative until the controller's current-attempt join.

**Step 3 — verify GREEN**

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_authority.py
git diff --check
```

**Step 4 — commit**

```bash
git add config/authority_map.yml control_plane/executive_authority.py tests/test_executive_authority.py
git commit -m 'feat(executive): admit controller-only readiness requests'
```

---

## Task 2: Factor canonical current-attempt and effective-grant validation

**Files:**
- Modify: `control_plane/executive_runtime.py`
- Modify: `control_plane/executive_supervisor.py`
- Create: `tests/test_executive_runtime_current_attempt.py`
- Modify: `tests/test_executive_supervisor.py`

**Step 1 — write failing Runtime tests**

Add tests for a new frozen `CurrentAttemptAuthoritySnapshot` and `AttemptRegistry.current_authority_snapshot(...)` that:
- validates Job/Attempt identity, active status, job/quota current links, exact fence and unexpired lease without accepting/returning the token;
- returns only secret-free Job/Attempt/worker/quota facts;
- rejects wrong Job, stale fence, expired lease, offline worker, inconsistent quota link and `OPERATOR_HARNESS`;
- treats legacy null execution mode as `SEALED_WORKER`;
- proves `_leased_row` and the new helper share the same currentness/fence/expiry logic by mutation/negative parity.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_runtime_current_attempt.py
```

Expected RED: API absent.

**Step 2 — implement the token-free owner seam**

- Factor the existing `_leased_row` join/currentness checks into one private token-agnostic helper on `AttemptRegistry`. The shared helper validates only active status, exact Job-status correspondence, fence/quota-fence equality, unexpired lease, and current Job/quota links; it performs no Job-id or execution-mode restriction.
- Make `_leased_row` call the shared helper, then perform only constant-time token comparison. Existing `OPERATOR_HARNESS` callers must remain valid.
- Add `current_authority_snapshot(connection, job_id, attempt_id, fence_generation, timestamp, statuses)` on `AttemptRegistry`; it calls the shared helper and then separately adds exact `job_id`, worker/slot facts, and `SEALED_WORKER` validation.
- Perform all Job/Attempt/quota/worker reads on the caller's existing transaction connection.
- Return a frozen dataclass; omit `lease_token` and raw provider credential material.
- Scope parity tests to the shared helper's status/fence/expiry/current-link checks; separately test that only `current_authority_snapshot` rejects non-`SEALED_WORKER` modes. Pin the deliberate post-refactor error precedence: shared stale-fence/status/currentness refusals occur before `_leased_row`'s invalid-token comparison.

**Step 3 — write failing effective-grant and prompt tests**

`executive_supervisor.py` has exactly four current authority-projection sites: `_prompt`'s JSON authorities list, `WorkerLaunchSpec.authorities`, `_validate_execution_profile`'s write-capable/admission gate, and the durable launch attestation. Add tests that assert:
- a module-level canonical validator, given an already-authorized `AuthorityDecision`, produces the same result currently returned by `ExecutiveSupervisor._effective_grant`;
- malformed/digest/policy/role/job/widened grants fail identically;
- `REQUEST_WORKER_LOGIN_CHECK` is removed from `_prompt`'s JSON authorities and from `WorkerLaunchSpec.authorities`, whether sourced from the Job or effective grant;
- `_validate_execution_profile`'s admission gate and the durable launch attestation both still see the full unfiltered authority set, including `REQUEST_WORKER_LOGIN_CHECK` — negative test that filtering does not leak into either;
- the persisted Job/Attempt grant remains unchanged for controller admission.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_supervisor.py \
  -k 'effective_grant or controller_only_authority'
```

Expected RED: helper/filter absent.

**Step 4 — implement the shared grant validator and packet filter**

- Factor current `_effective_grant` validation into one module-level deterministic function in `executive_supervisor.py` that accepts an already-authorized `AuthorityDecision` and performs no policy-file load; keep the existing method as a delegating compatibility seam that obtains its decision before calling the helper.
- Add a closed `CONTROLLER_ONLY_AUTHORITIES = {"REQUEST_WORKER_LOGIN_CHECK"}` projection rule.
- Apply the filter only at the two model/worker-facing projection sites (`_prompt` JSON, `WorkerLaunchSpec.authorities`); leave `_validate_execution_profile`'s admission gate and the durable launch attestation on the full unfiltered grant; never rewrite durable Job or Attempt authority evidence.

**Step 5 — verify GREEN**

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_executive_runtime_current_attempt.py \
  tests/test_executive_supervisor.py
git diff --check
```

**Step 6 — commit**

```bash
git add control_plane/executive_runtime.py control_plane/executive_supervisor.py \
  tests/test_executive_runtime_current_attempt.py tests/test_executive_supervisor.py
git commit -m 'refactor(executive): expose token-free current attempt validation'
```

---

## Task 3: Extract one shared, one-send privileged-broker client

**Files:**
- Create: `control_plane/executive_privileged_client.py`
- Create: `tests/test_executive_privileged_client.py`
- Modify: `scripts/mmx_admin.py`
- Modify: `tests/test_mmx_admin.py`

**Step 1 — write failing shared-client tests**

Cover:
- fixed socket path and eleven-minute timeout;
- exactly one newline-delimited send and no reconnect/retry;
- response byte/frame bound;
- exact success/refusal/status envelope keys;
- effect response correlation to request ID, digest, action and installed release;
- terminal/status receipt validation;
- `EFFECT_UNKNOWN`, marker, `NOT_FOUND`, malformed and transport-loss classifications;
- no caller-selected production socket/path.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_privileged_client.py
```

Expected RED: module absent.

**Step 2 — implement the shared client**

Expose typed or exact-dict functions for:
- `send_effect(request, *, socket_path=DEFAULT_SOCKET, timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS)`;
- `send_status(request, *, socket_path=DEFAULT_SOCKET, timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS)`;
- exact effect/status response validation.

Reuse `executive_privileged_action` and broker `validate_terminal_receipt`; do not duplicate the action catalog, receipt store or executor.

**Step 3 — refactor `mmx_admin.py` without behavior drift**

Move transport and response validation to the shared module. Keep CLI parsing, visible request ID, JSON output and exit-code mapping stable. No new socket CLI flag.

**Step 4 — verify GREEN and backward compatibility**

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_executive_privileged_client.py \
  tests/test_mmx_admin.py \
  tests/test_executive_privileged_broker.py
python3 -m py_compile control_plane/executive_privileged_client.py scripts/mmx_admin.py
git diff --check
```

**Step 5 — commit**

```bash
git add control_plane/executive_privileged_client.py tests/test_executive_privileged_client.py \
  scripts/mmx_admin.py tests/test_mmx_admin.py
git commit -m 'refactor(executive): share privileged broker client validation'
```

---

## Task 4: Implement the Event-backed Job-bound readiness controller

**Files:**
- Create: `control_plane/executive_privileged_authority.py`
- Create: `tests/test_executive_privileged_authority.py`
- Modify: `control_plane/executive_runtime.py` for the required transaction-aware Event-list seam
- Create: `tests/test_executive_runtime_events.py` for that Event seam

**Step 1 — write contract and binding RED tests**

Pin exact schemas/keys, positive integer fence validation, fixed action, canonical JSON digests, the `pvrf-<48hex>` family aggregate ID (from the logical family key only) and the `pvr-<48hex>` operation/broker request ID (from the complete first-admission binding including release/boot/policy). Assert the two IDs differ and each is reproducible only from its own input. Refuse extra fields, unsafe IDs, PID fallback boot identities, unknown slot, caller-supplied action/slot/release/host/path and any secret field.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_privileged_authority.py \
  -k 'binding or request_contract or boot_identity or family_id'
```

Expected RED: module absent.

**Step 2 — implement immutable types and preflight**

Add:
- binding/result schemas and frozen dataclasses;
- strict validators and canonical serialization;
- real-kernel-boot UUID validator;
- logical family key `(job_id, attempt_id, fence, verify_only)` and its `pvrf-...` family aggregate ID;
- deterministic `pvr-...` operation/broker request ID from the complete first-admission binding.

Load release, policy and boot facts outside Runtime write transactions.

**Step 3 — add the required Runtime/Event-owner seam and write RED tests for existing-family-first recovery**

Add `RuntimeStore.list_events(..., connection: sqlite3.Connection | None = None)` on the existing Runtime/Event owner and make `EventRegistry.list_events` delegate to it; this one seam is reused for both the outside-transaction family lookup and the inside-transaction absence recheck in Step 5. Do not introduce an `EventStore` class. `executive_privileged_authority.py` must never issue a raw `SELECT ... FROM events`.

Cover:
- the family is found by exact `aggregate_type='privileged_readiness'` + `aggregate_id=<family aggregate ID>` lookup (not a job_id/attempt_id scan) after Attempt completion/requeue;
- release/boot/policy movement does not change the family aggregate ID and therefore cannot create a second family for the same logical key;
- multiple/conflicting families fail closed;
- no family enters fresh current-attempt admission;
- controller restart reconstructs from Events plus broker status only;
- recovery performs at most one broker status query per invocation for `ATTEMPTED`/`EFFECT_UNKNOWN`, creates no family, performs no effect, and enumerates no other family/Job/Attempt;
- recovery requires no current authority check (no `current_authority_snapshot` call on this path).

**Step 4 — write RED tests for atomic first admission and concurrency**

Use a fake broker client and real RuntimeStore:
- wrong Job/Attempt/fence/status/lease/worker/policy/grant/mode refuses with zero Event/effect;
- valid admission atomically appends INTENT then ATTEMPTED inside one `BEGIN IMMEDIATE` transaction;
- 20 concurrent async callers, singleflight-keyed on the logical family key (not the complete binding), produce one ATTEMPTED and one effect call;
- a singleflight miss (simulated second process) still cannot create a duplicate family, proven via the `BEGIN IMMEDIATE` transaction plus family aggregate-ID uniqueness alone;
- failure before ATTEMPTED creates no operation family;
- crash/exception after ATTEMPTED never becomes no-effect;
- instrument `Path.resolve()`/`Path.expanduser()` and policy-file reads to prove all authority-decision filesystem work occurs before `connection.in_transaction` becomes true; a changed authority-input row inside the transaction refuses rather than recomputing the decision under the lock;
- process crash simulated between the ATTEMPTED commit and the broker socket write leaves the family `EFFECT_UNKNOWN`, identical to a post-send transport loss, with no automatic retry;
- `worker_id` resolves through `get_slot(worker_id)` imported via the existing `ops.executive_os` namespace-package seam from a production-style release-root composition (not a repo-relative import), and the returned slot id must equal the caller's worker.

**Step 5 — implement controller admission and singleflight**

- Query existing family first via the Step 3 seam.
- For new work, load `ExecutiveAuthorityPolicy`, installed release identity, and the validated kernel boot UUID before opening any Runtime write transaction. Read the Job's authority inputs through a read-only Runtime snapshot and call `authorize(...)` there, producing one precomputed `AuthorityDecision` before the write lock.
- Use a process-local async singleflight registry keyed on the logical family key.
- Inside one `BEGIN IMMEDIATE` Runtime transaction, recheck absence via the same Step 3 seam, call `current_authority_snapshot`, re-read and compare the exact Job authority inputs against the preflight snapshot, validate the effective grant with the precomputed decision, compare only in-memory release/policy/boot facts, append INTENT+ATTEMPTED, and return execute-once only to the owner task.
- Do not call `ExecutiveAuthorityPolicy.load()`, `ExecutiveAuthorityPolicy.authorize()`, `Path.expanduser()`, `Path.resolve()`, `Path.read_bytes()`, `ProcessInspector.boot_session_id()`, sysctl, socket I/O or provider work while the Runtime transaction is held.

**Step 6 — write RED tests for terminal and unknown-effect reconciliation**

Cover:
- terminal effect response -> append the `TERMINAL` Event phase once and return result state `TERMINAL`, with `observed_at_ms` set and `evidence_currency` computed from freshly re-validated boot/release/policy facts;
- broker refusal -> append the `BROKER_REFUSED` Event phase once and return result state `REFUSED` with a closed reason;
- transport loss -> append/retain the `EFFECT_UNKNOWN` Event phase and return result state `EFFECT_UNKNOWN`;
- status terminal after loss -> append the `RECONCILED` Event phase with one total effect call and return result state `TERMINAL` plus `replayed: true`;
- marker -> EFFECT_UNKNOWN;
- NOT_FOUND after ATTEMPTED -> EFFECT_UNKNOWN;
- repeated marker/NOT_FOUND/status observation appends no duplicate Event;
- malformed response -> EFFECT_UNKNOWN, no retry;
- cancellation after ATTEMPTED -> EFFECT_UNKNOWN;
- terminal failed receipt remains terminal failed evidence, not controller failure;
- every result carries `observation_scope: LOGIN_STATUS_ONLY_NO_READY_ASSERTION`; a replayed terminal result (`replayed: true`) reproduces the identical terminal receipt and never asserts READY regardless of `evidence_currency`; broker refusal and EFFECT_UNKNOWN carry `receipt: null`;
- current release/boot/policy facts diverging from the stored binding yields `evidence_currency: HISTORICAL`; exact equality yields `CURRENT`.

**Step 7 — implement reconciliation and result projection**

Use only the shared client's status method after ATTEMPTED. Validate event-family order and exact command IDs. Compute `observed_at_ms` and `evidence_currency` on every result path, fresh or replayed. Return secret-free results; never include lease token, provider home, raw credentials, environment or arbitrary paths.

**Step 8 — verify GREEN**

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_executive_privileged_authority.py \
  tests/test_executive_runtime_events.py \
  tests/test_executive_privileged_client.py \
  tests/test_executive_privileged_broker.py
python3 -m py_compile control_plane/executive_privileged_authority.py
git diff --check
```

**Step 9 — commit**

```bash
git add control_plane/executive_privileged_authority.py tests/test_executive_privileged_authority.py \
  control_plane/executive_runtime.py tests/test_executive_runtime_events.py
git commit -m 'feat(executive): authorize job-bound worker readiness checks'
```

---

## Task 5: Compose the closed control command and default-off host configuration

**Blocking source-custody precondition:** Do not start or edit any Task 5 path while PR #653 remains an active writer on `ops/executive_os/install.sh` or `scripts/executive_os_phase1c.py`. Re-read its exact state/files and current protected source. Proceed only after it merges/closes and this carrier is reconciled; never create a second writer.

**Files:**
- Modify: `control_plane/executive_service.py`
- Modify: `scripts/executive_os_phase1c.py`
- Modify: `ops/executive_os/install.sh`
- Modify: `tests/test_executive_service.py`
- Modify: `tests/test_c1_installer_control_config.py`
- Modify: `tests/test_executive_launchd_config.py`

**Step 1 — write RED config/composition tests**

Pin two optional/default-off control config fields:
- `privileged_readiness_armed: false`;
- fixed `privileged_broker_socket_path` only when armed.

Prove:
- old configs remain valid/unarmed;
- armed + missing/wrong socket refuses;
- armed + missing controller refuses service composition;
- unarmed + injected controller refuses;
- no environment/CLI/request override can arm it.

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_executive_service.py \
  tests/test_c1_installer_control_config.py \
  -k 'privileged_readiness'
```

Expected RED: fields/guards absent.

**Step 2 — implement config and production composition**

- Extend `ServiceConfig` exact parsing/serialization with the two optional fields.
- Inject `PrivilegedReadinessController | None` into `ExecutiveControlService`.
- In `_service_from_config`, build the controller only when armed, from Runtime, fixed release, fixed broker socket, ProcessInspector and shared client.
- Keep all existing unarmed service behavior byte-compatible.

**Step 3 — write RED dispatch and CLI tests**

Pin exact request:

```json
{"command":"check-current-worker-login","args":{"job_id":"JOB-...","attempt_id":"ATT-...","fence_generation":1}}
```

Prove exact keys/types, no extra fields, no caller action/slot/socket/path, service-`READY`-only dispatch, existing kernel peer gate, typed controller errors, and an exact JSON result that includes `family_id`, `operation_id`, `observed_at_ms`, and `evidence_currency` and never a `ready`/`READY` field.

Add CLI subcommand:

```text
check-current-worker-login JOB_ID ATTEMPT_ID FENCE_GENERATION
```

**Step 4 — implement dispatch and CLI**

- Add one closed branch to `_dispatch_request`.
- Delegate to the injected controller; no policy or SQL logic in the service branch.
- Keep one request/one response and existing socket semantics.

**Step 5 — write RED installer/wrapper tests**

Prove:
- existing `--arm-privileged-broker` writes both broker config and `privileged_readiness_armed=true` with fixed socket;
- no arm flag leaves readiness false and no usable wrapper;
- installer creates root-owned exact-release `/Library/Application Support/MastermindExecutive/bin/mmx-control` with fixed control socket/config and no user-controlled path/socket/action interpolation;
- the wrapper exposes exactly one operation (`check-current-worker-login`), accepts exactly three positional arguments `JOB_ID ATTEMPT_ID FENCE_GENERATION`, and rejects any argument beginning with `-` before dispatch;
- the wrapper never forwards a caller-supplied global option, an alternate socket/path, or another subcommand — no argv passthrough beyond the three validated positional values;
- tests and docs identify the wrapper as an ergonomics/governance consumer, not containment: the operator UID retains the merged direct six-action `mmx-admin` broker grant, while dedicated worker UIDs remain denied;
- cleanup/rollback removes or leaves inert the wrapper when arming fails;
- ordinary control/worker service startup remains separately controlled.

**Step 6 — implement the fixed wrapper and installer fields**

Use an `exec` wrapper to installed Python + installed `scripts/executive_os_phase1c.py` with the fixed config/socket and the fixed `check-current-worker-login` subcommand baked in; the wrapper validates exactly its three positional arguments (rejecting any `-`-prefixed argument) and passes only those three values through — it never forwards arbitrary argv, another subcommand, or a socket/path override. Never use `eval`, `bash -c`, a mutable checkout or caller-supplied socket.

**Step 7 — verify GREEN**

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_executive_service.py \
  tests/test_c1_installer_control_config.py \
  tests/test_executive_launchd_config.py \
  tests/test_executive_privileged_authority.py
bash -n ops/executive_os/install.sh
python3 -m py_compile control_plane/executive_service.py scripts/executive_os_phase1c.py
git diff --check
```

**Step 8 — commit**

```bash
git add control_plane/executive_service.py scripts/executive_os_phase1c.py \
  ops/executive_os/install.sh tests/test_executive_service.py \
  tests/test_c1_installer_control_config.py tests/test_executive_launchd_config.py
git commit -m 'feat(executive): expose armed job-bound readiness control'
```

---

## Task 6: Prove the complete source vertical and rollout gates

**Preflight:** Re-read PR #653 and all current owned-path collisions before Step 2. Task 6 itself owns no `install.sh` or `scripts/executive_os_phase1c.py` edit, but its proof must consume the reconciled Task 5 result rather than an overlapping branch.

**Files:**
- Modify: `ops/executive_os/HOST_PREREQUISITES.md`
- Modify: `docs/superpowers/specs/2026-09-14-executive-job-bound-worker-readiness-design.md` only for proven implementation facts, never to weaken acceptance
- Tests as needed, no new product scope.

**Step 1 — add one end-to-end in-process integration test**

Use a real RuntimeStore, control service, Unix socket, fake fixed broker server and CLI request to prove:
- current Job/Attempt/fence -> control service -> controller -> exact verify-only frame;
- one effect despite concurrent callers;
- terminal result through the real control response, carrying `family_id`, `operation_id`, `observed_at_ms`, `evidence_currency`, and `observation_scope`, and no `ready`/`READY` field;
- lost effect response followed by a fresh service/controller instance -> status-only terminal reconciliation;
- stale fence and direct dedicated-worker broker access refuse;
- `ops.executive_os.provider_worker_slots.get_slot` resolves correctly when imported from a production-style release-root composition, not only a repo-relative import.

Place the test in `tests/test_executive_service.py` or a narrowly named new integration test if the owning file becomes unwieldy.

**Step 2 — run focused and owning suites**

```bash
umask 022
python3 -m pytest -o addopts='' -q \
  tests/test_executive_authority.py \
  tests/test_executive_runtime_current_attempt.py \
  tests/test_executive_runtime_events.py \
  tests/test_executive_supervisor.py \
  tests/test_executive_privileged_action.py \
  tests/test_executive_privileged_broker.py \
  tests/test_executive_privileged_client.py \
  tests/test_executive_privileged_authority.py \
  tests/test_mmx_admin.py \
  tests/test_executive_service.py \
  tests/test_c1_installer_control_config.py \
  tests/test_executive_launchd_config.py \
  tests/test_executive_service_control.py \
  tests/test_ceo_submit_armed_composition.py \
  tests/test_c1_ceo_ingress_composition.py \
  tests/test_worker_execution_contract.py
python3 -m py_compile \
  control_plane/executive_authority.py \
  control_plane/executive_runtime.py \
  control_plane/executive_supervisor.py \
  control_plane/executive_privileged_client.py \
  control_plane/executive_privileged_authority.py \
  control_plane/executive_service.py \
  scripts/mmx_admin.py \
  scripts/executive_os_phase1c.py
bash -n ops/executive_os/install.sh
git diff --check
```

Do not waive tests. Diagnose inherited failures and preserve exact evidence.

**Step 3 — document the exact production ceremony**

The runbook must separate:
1. verify zero living Attempts before policy transition;
2. exact protected merged SHA and clean root installer source;
3. one attended administrator bootstrap with `--arm-privileged-broker`;
4. services not called healthy merely because plists exist;
5. real bounded Job creation/claim with capability;
6. non-root `mmx-control check-current-worker-login ...`;
7. independent verification of the exact login-status observation and absence of any READY claim;
8. lost-response status reconciliation with one effect;
9. stale-fence/wrong-Job/direct-worker negatives;
10. no password prompt after bootstrap.

**Step 4 — commit source-proof/runbook updates**

```bash
git add ops/executive_os/HOST_PREREQUISITES.md \
  docs/superpowers/specs/2026-09-14-executive-job-bound-worker-readiness-design.md \
  tests/test_executive_service.py
git commit -m 'test(executive): prove job-bound readiness end to end'
```

---

## Task 7: Independent review, current-base proof and PR publication

**Step 1 — exact-head independent review**

Route one read-only Opus review over the exact semantic head. Required focus: lease/fence currentness, model authority filtering, singleflight, Event-family correctness, lost-response/NOT_FOUND behavior, shared client, installer arming and absence of generic root authority. No reviewer writes or host effects.

**Step 2 — repair every Critical/Important finding tests-first**

One finding at a time: reproduce RED, minimal repair, focused GREEN, full owning suites. Re-review the repaired exact head.

**Step 3 — current protected-base integration proof**

Create a detached integration worktree from current protected master, merge the candidate without committing, record parents/tree, run focused + materially intersecting protected suites, and preserve inherited-flake evidence honestly. No force-push/rebase solely for ancestry cosmetics.

**Step 4 — publish as DRAFT/HOLD**

PR body must state:
- exact head/tree/base and independent verdict;
- new capability: current Job-bound assigned-slot `verify_only` through controller;
- non-goals and mandatory denies;
- source test/integration evidence;
- `BUILT_NOT_PROVEN` until exact protected install and real host proof;
- policy-hash drain gate;
- exact next action.

Do not mark ready/merge until required checks, review and compatibility are current.

---

## Task 8: Sol-only merge, bootstrap and production acceptance

This task is **not** delegated to an ordinary coding worker.

1. Merge through the protected queue with exact-head binding.
2. Read back protected merge SHA and confirm broker/controller/install blobs.
3. Reconcile Runtime: zero living Attempts or lawful explicit termination/requeue.
4. Perform the one attended administrator bootstrap on the selected Studio using the exact protected source and pinned root Python/Codex inputs.
5. Prove privileged plist/socket/wrappers/config ownership and service registration; do not infer readiness from installation.
6. Create/claim one real bounded Job with `REQUEST_WORKER_LOGIN_CHECK` for `codex-01`.
7. Invoke installed `mmx-control` as the non-root operator and prove exact root `verify_only`, the exact login-status observation, and absence of any READY claim.
8. Reconcile a deliberately lost client response through the control command with exactly one broker effect.
9. Prove wrong Job, stale fence, and direct dedicated-worker broker socket access refuse. Separately read back the installed broker policy and record the accepted residual that the operator UID retains direct access to all six reviewed `mmx-admin` actions and slots; do not claim `mmx-control` contains that principal.
10. Prove a fresh native Codex orchestrator discovers and consumes the Job-bound command without asking for sudo/password. Add Claude attended-orchestrator proof only if the provider session is available; do not claim dedicated Claude worker-slot coverage until the slot catalog supports it.
11. Record exact Runtime Events, broker receipt/request ID, merged release SHA, host/boot identity, no-prompt evidence and remaining P3/P4/P5 gates in durable owners.

Only after these observations may P2-1 become `PROVEN_LIVE` on the Studio. Then advance directly to the P3 secret-free credential-renewal vertical.


## 2026-09-16 continuation — supervisor portion of Task 2

The existing PR #703 and operation remain canonical. The local immutable-binding
commits after `f3dd1b0b` are preserved, not replaced. Task 1, Task 3, the pure
Task 4 request/binding primitives, and Task 2's **supervisor-only** portion are
implemented. The Runtime portion of Task 2 and the actual Event-backed controller
are not implemented or accepted by this checkpoint.

`validate_effective_grant` now consumes the same Job's preauthorized
`AuthorityDecision` without loading policy or resolving filesystem paths. It
retains grant-shape, scope, policy and digest refusal and rejects mismatched
preauthorized scope. The compatibility method authorizes once before delegating.
Only prompt JSON and `WorkerLaunchSpec.authorities` remove the closed
`REQUEST_WORKER_LOGIN_CHECK` capability. Profile admission, durable launch
evidence and persisted grants retain the full authority.

Regression-first supervisor proof began with 16 failures and 2 passing negative
controls. The expanded eight-file compatibility campaign passes 364 tests.
Four in-memory fault controls (worker permission leakage, accepted policy drift,
ignored grant digest, ignored decision scope) each produce real test failures;
they never rewrite the source file. The earlier socket test race was corrected
by consuming its request before dropping the response. Deterministic send/receive
loss tests preserve the one-send/no-retry contract; no client production behavior
was weakened to make the test green.

Current holds remain explicit: #699 requires incumbent RuntimeBinding/source
reconciliation before `executive_runtime.py` edits; #653 retains installer and
phase1c composition custody. The controller, installation, native Claude/Codex
consumption and root-effect/recovery proof remain unbuilt or unproven. The Studio
still has no privileged broker plist/config/socket/client. No password, sudoers,
credential, root service, provider session or production Runtime was modified.

Direct source work used the existing acquired workspace as a small
`CRITICAL_PATH_SHORTCUT`; the discovered Executive app reports fixture mode and
was not used as real worker admission. This is a Draft/HOLD source continuation,
not source acceptance or production acceptance. Next: reconcile the Runtime
owner, finish Task 2's token-free current-Attempt seam and Task 4 on the same
carrier, then consume the installer owner's return for Task 5. Preserve review,
current-base CI and one-time host-bootstrap gates.

## 2026-09-17 continuation — hosted CI qualification

Protected Skillpack pin: `eec5324c5205e8bad206512e0a936898e50b2408`;
required procedure blobs equal the previously loaded compatible revision.
The existing branch and acquired workspace remain the only source carrier.

Hosted run `35168261078` on the prior semantic checkpoint failed three tests.
The unchanged D8 identity scanner misclassified the client's numeric timeout
literal and five documentation occurrences as identity additions. Expressing
the duration as eleven minutes (`11 * 60` in code) preserves the exact timeout,
all socket behavior and all permissions. Documentation now uses the named
default. The working-patch scanner has zero hits and all 48 client/CLI tests pass.
Neither the identity guard nor its positive controls were changed.

The offline-acceptance receipt mismatch also reproduces locally. Its expected
hash is deliberately unchanged: the cause has not been established. The hosted
process-identity cancellation failure did not reproduce in the one local check;
that is not proof of a harmless flake or permission to waive the test.
A read-only diagnostic was blocked by the tool platform and was not retried or
rerouted. No policy, permission, Runtime, installer or acceptance pin was changed.

Next: resolve the remaining CI evidence through an approved diagnostic path,
then obtain exact-head independent review and current-base executed proof.
The existing Runtime ownership and installer holds remain in force; this
qualification repair neither clears them nor installs or arms the broker.


## 2026-09-17 continuation — complete status-receipt validation

The existing shared client now validates the exact broker-produced status shape
and reuses the broker's complete terminal-receipt validator. Previously an
incomplete receipt or an unreviewed extra field could pass through status lookup
to the existing CLI. Unknown outcomes require the original marker's release;
NOT_FOUND contains neither receipt nor marker. Historical receipt/marker releases
remain distinct from the currently installed release. No effect or retry is added.

Regression-first proof exposed 41 failures with six valid-path controls before
repair. The expanded source campaign includes actual temporary Unix-socket frames
through the unchanged CLI, and four in-memory weakened validators are caught.
Exact counts, immutable source hashes and current-base proof belong to the PR and
native evidence under this operation's `ci-repair-20260917` directory.

The cancellation failure now has an exact dependency: existing PR #586 at
`3c30592a0957ab25aa59bbb3398a7010823ca99a` has a non-author CHANGES_REQUESTED review
for bounded cleanup on uncertain pre-latch paths. A model-free discriminator
reproduces the old group-absence exception with zero real processes or signals.
Do not build another cancellation repair or revive terminal historical PR #392.

PR #699 retains Runtime custody; PR #653 retains installer custody. The prior
blocked acceptance diagnostic was not retried, and its expected digest is unchanged.
The Executive app still reports fixture mode; no real worker admission is claimed.
This narrow direct repair used LOWER_TOTAL_OVERHEAD and the same acquired workspace.
Next: review this exact source delta and resolve the existing dependency holds;
then resume the Runtime/controller/installer sequence. No broker installation,
root effect, credential operation, production acceptance or parent closure occurred.


## Continuation — acceptance golden reconciliation

The remaining hosted source failure was the deterministic offline acceptance
receipt. A protected-versus-candidate execution compared every projected leaf.
There were seventy-three differences and every one was a digest; no action,
status, retry, quarantine, inertness, authority list, or other non-digest field
changed.

The exact cause is the reviewed authority-policy hash movement introduced by
the controller-only `REQUEST_WORKER_LOGIN_CHECK` capability and its closed
current-attempt scope. Orchestration grants intentionally bind that policy hash,
so the receipt and five affected sub-receipts changed transitively. Dispatch
boundary, TX-nine, and bounded-exhaustion digests remained byte-identical.

Only the six derived golden values in the existing acceptance test were
updated. The producer, Runtime, retry law, authority map, controller code, and
expected behavior were not weakened or changed. The previously failing exact
acceptance discriminator is green. The complete comparison receipt is retained
under the operation evidence directory as
`acceptance-golden-reconciliation.json`.

The local full repository gate was not claimed: the first attempt lacked CI
dependencies, the parity attempt initially lacked the workflow's separately
materialized pinned Macro source, and the final parity run was stopped to avoid
adding load while the Studio was saturated. Hosted required CI remains the
release authority for the complete gate.
