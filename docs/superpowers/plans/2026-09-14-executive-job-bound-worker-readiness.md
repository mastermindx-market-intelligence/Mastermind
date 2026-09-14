# Executive Job-Bound Worker Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` for every source change, `superpowers:systematic-debugging` for every unexpected failure, and `superpowers:verification-before-completion` before any completion claim. Execute this plan task-by-task in the single assigned workspace; do not create another worktree.

**Goal:** Deliver one independently useful permanent-system vertical: an attended non-root orchestrator may ask the trusted Executive controller to run the fixed privileged broker action `executive.worker_auth.verify_only` for the exact current SEALED_WORKER Attempt's assigned slot, with durable Event-backed replay/reconciliation and no lease-token, root-shell, arbitrary-action, slot, host, path, or retry authority.

**Architecture:** Reuse the current Executive Job/Attempt/Worker/Event, policy, lease/fence, service and installer owners. Stack the reviewed PR #613 broker/client source, add one controller-only authority, factor token-free current-attempt and effective-grant validators from their existing owners, extract one shared one-send broker client, implement an Event-backed readiness controller with existing-family-first recovery and process-local singleflight, expose one closed control command plus fixed installed wrapper, and keep the whole capability default-off behind the existing `--arm-privileged-broker` bootstrap.

**Tech Stack:** Python 3.12, SQLite RuntimeStore, asyncio, Unix domain sockets, macOS launchd, Bash installer wrappers, pytest, GitHub protected merge queue.

**Spec:** `docs/superpowers/specs/2026-09-14-executive-job-bound-worker-readiness-design.md`

**Global Constraints:**
- Preserve PR #613's six-action catalog and broker receipt owner; never add generic exec, shell, path, socket or secret parameters.
- Preserve `SERVICE_CONTROL` and `CREDENTIAL_ADMIN` mandatory denies.
- Never expose or request the persisted Attempt lease token.
- Never auto-retry or fail over an attempted/unknown root effect.
- No new Runtime table, queue, lease, token registry, credential store, host registry or status database.
- Every controller refusal happens before Event creation; every effect after `ATTEMPTED` is reconciled from existing Events plus broker status.
- `NOT_FOUND` after `ATTEMPTED` remains `EFFECT_UNKNOWN`.
- Dedicated worker/model packets must not advertise the controller-only capability.
- Source completion, merge, installation, host proof and final acceptance remain distinct.

## Capability state on entry

- PR #613 fixed broker/status: `BUILT_NOT_PROVEN`, semantic head `2259596e943dabe566203e8dd450888661d4f00c`.
- PR #621 administrative revocation: `BUILT_NOT_PROVEN`.
- P2-1 Job-bound readiness authority: `NOT_BUILT`.
- First root bootstrap and production proof: not yet performed.

---

## Task 0: Reconcile and stack the exact broker dependency

**Files:** Git ancestry only; no hand-edited source.

**Step 1 — verify source identity and current base**

```bash
git fetch origin master sol/privileged-action-broker-20260913
git rev-parse HEAD
git rev-parse origin/master
git rev-parse origin/sol/privileged-action-broker-20260913
```

Expected: this branch contains the reviewed spec commits; broker branch resolves to `2259596e943dabe566203e8dd450888661d4f00c`, or protected master contains a merged descendant whose broker/client blobs are byte-identical. Stop on a moved, unreviewed semantic head.

**Step 2 — prove collision safety before merge**

```bash
git diff --name-only HEAD..origin/master | sort > /tmp/p2-protected-paths
git diff --name-only af9fce32861f9c1496b85a580e3569712170d92b..2259596e943dabe566203e8dd450888661d4f00c | sort > /tmp/p2-broker-paths
comm -12 /tmp/p2-protected-paths /tmp/p2-broker-paths
git merge-tree "$(git merge-base HEAD 2259596e943dabe566203e8dd450888661d4f00c)" HEAD 2259596e943dabe566203e8dd450888661d4f00c | grep -E 'CONFLICT|<<<<<<<|>>>>>>>' && exit 1 || true
```

Expected: no unresolved overlap. If PR #613 is already merged, merge current protected master instead and verify exact broker blobs.

**Step 3 — merge the dependency, never copy files**

```bash
git merge --no-ff 2259596e943dabe566203e8dd450888661d4f00c -m 'merge: stack reviewed privileged broker dependency'
```

**Step 4 — baseline the imported capability**

```bash
umask 022
python3 -m pytest -o addopts='' -q \
  tests/test_executive_privileged_action.py \
  tests/test_executive_privileged_broker.py \
  tests/test_mmx_admin.py \
  tests/test_executive_launchd_config.py \
  tests/test_executive_service_control.py
bash -n ops/executive_os/install.sh
bash -n ops/executive_os/service-control.sh
git diff --check HEAD^..HEAD
```

Do not alter imported broker semantics to make later work convenient.

---

## Task 1: Add the controller-only authority without widening root capability

**Files:**
- Modify: `config/authority_map.yml`
- Modify: `control_plane/executive_authority.py`
- Modify: `tests/test_executive_authority.py`

**Step 1 — write failing policy tests**

Add tests that assert:
- exact allow-list is `{READ, RESEARCH, WRITE_BRANCH, RUN_TESTS, REQUEST_WORKER_READINESS}`;
- exact scope is `current_attempt_assigned_worker_slot`;
- adding the YAML value without the code constant fails closed;
- deleting/changing the scope fails closed;
- `SERVICE_CONTROL` and `CREDENTIAL_ADMIN` remain mandatory denies;
- authorizing `REQUEST_WORKER_READINESS` accepts no worktree/path/argv/slot/action evidence and returns no slot/root grant.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_authority.py \
  -k 'worker_readiness or checked_in_policy or drift or mandatory_denies'
```

Expected RED: allow-list/scope mismatch.

**Step 2 — implement the minimum policy change**

- Add `REQUEST_WORKER_READINESS` to `PHASE1B_ALLOWED`.
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
- Modify: `tests/test_executive_os_sqlite.py`
- Modify: `tests/test_executive_supervisor.py`

**Step 1 — write failing Runtime tests**

Add tests for a new frozen `CurrentAttemptAuthoritySnapshot` and `AttemptRegistry.current_authority_snapshot(...)` that:
- validates Job/Attempt identity, active status, job/quota current links, exact fence and unexpired lease without accepting/returning the token;
- returns only secret-free Job/Attempt/worker/quota facts;
- rejects wrong Job, stale fence, expired lease, offline worker, inconsistent quota link and `OPERATOR_HARNESS`;
- treats legacy null execution mode as `SEALED_WORKER`;
- proves `_leased_row` and the new helper share the same currentness/fence/expiry logic by mutation/negative parity.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_os_sqlite.py \
  -k 'current_authority_snapshot or leased_row_parity'
```

Expected RED: API absent.

**Step 2 — implement the token-free owner seam**

- Factor the existing `_leased_row` join/currentness checks into one private helper on `AttemptRegistry`.
- Make `_leased_row` call it, then perform only constant-time token comparison.
- Add `current_authority_snapshot(connection, job_id, attempt_id, fence_generation, timestamp, statuses)` on `AttemptRegistry`.
- Perform all Job/Attempt/quota/worker reads on the caller's existing transaction connection.
- Return a frozen dataclass; omit `lease_token` and raw provider credential material.
- Reject non-`SEALED_WORKER` modes.

**Step 3 — write failing effective-grant and prompt tests**

Add tests that assert:
- a module-level canonical validator produces the same result currently returned by `ExecutiveSupervisor._effective_grant`;
- malformed/digest/policy/role/job/widened grants fail identically;
- `REQUEST_WORKER_READINESS` is removed from worker/model-facing `authorities` whether sourced from the Job or effective grant;
- the persisted Job/Attempt grant remains unchanged for controller admission.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_supervisor.py \
  -k 'effective_grant or controller_only_authority'
```

Expected RED: helper/filter absent.

**Step 4 — implement the shared grant validator and packet filter**

- Factor current `_effective_grant` validation into one module-level pure function in `executive_supervisor.py`; keep the existing method as a delegating compatibility seam.
- Add a closed `CONTROLLER_ONLY_AUTHORITIES = {"REQUEST_WORKER_READINESS"}` projection rule.
- Filter only the model packet; never rewrite durable Job or Attempt authority evidence.

**Step 5 — verify GREEN**

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_executive_os_sqlite.py \
  tests/test_executive_supervisor.py
git diff --check
```

**Step 6 — commit**

```bash
git add control_plane/executive_runtime.py control_plane/executive_supervisor.py \
  tests/test_executive_os_sqlite.py tests/test_executive_supervisor.py
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
- fixed socket path and 660-second timeout;
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
- `send_effect(request, *, socket_path=DEFAULT_SOCKET, timeout_seconds=660)`;
- `send_status(request, *, socket_path=DEFAULT_SOCKET, timeout_seconds=660)`;
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
- Modify: `control_plane/executive_runtime.py` only if a transaction-aware Event-list seam is needed
- Modify: `tests/test_executive_os_sqlite.py` only for that Event seam

**Step 1 — write contract and binding RED tests**

Pin exact schemas/keys, positive integer fence validation, fixed action, canonical JSON digest and `pvr-<48hex>` operation ID. Refuse extra fields, unsafe IDs, PID fallback boot identities, unknown slot, caller-supplied action/slot/release/host/path and any secret field.

```bash
python3 -m pytest -o addopts='' -q tests/test_executive_privileged_authority.py \
  -k 'binding or request_contract or boot_identity'
```

Expected RED: module absent.

**Step 2 — implement immutable types and preflight**

Add:
- binding/result schemas and frozen dataclasses;
- strict validators and canonical serialization;
- real-kernel-boot UUID validator;
- logical effect key `(job_id, attempt_id, fence, verify_only)`;
- deterministic operation/request ID.

Load release, policy and boot facts outside Runtime write transactions.

**Step 3 — write RED tests for existing-family-first recovery**

Cover:
- one exact family is found by Job/Attempt/fence/action after Attempt completion/requeue;
- release/boot/policy movement does not create a second family for the same logical key;
- multiple/conflicting families fail closed;
- no family enters fresh current-attempt admission;
- controller restart reconstructs from Events plus broker status only.

If required, add a transaction-aware `EventStore.list_events(..., connection=...)` on the existing Event owner and make `EventRegistry.list_events` delegate.

**Step 4 — write RED tests for atomic first admission and concurrency**

Use a fake broker client and real RuntimeStore:
- wrong Job/Attempt/fence/status/lease/worker/policy/grant/mode refuses with zero Event/effect;
- valid admission atomically appends INTENT then ATTEMPTED;
- 20 concurrent async callers produce one ATTEMPTED and one effect call;
- failure before ATTEMPTED creates no operation family;
- crash/exception after ATTEMPTED never becomes no-effect.

**Step 5 — implement controller admission and singleflight**

- Query existing family first.
- For new work, use process-local async singleflight by logical effect key.
- Inside one short Runtime transaction, recheck absence, call `current_authority_snapshot`, revalidate policy/effective grant/slot/preflight facts, append INTENT+ATTEMPTED, and return execute-once only to the owner task.
- Do not hold the Runtime transaction over sysctl, file reads, socket I/O or provider work.

**Step 6 — write RED tests for terminal and unknown-effect reconciliation**

Cover:
- terminal effect response -> TERMINAL once;
- broker refusal -> BROKER_REFUSED once with closed reason;
- transport loss -> EFFECT_UNKNOWN;
- status terminal after loss -> RECONCILED with one total effect call;
- marker -> EFFECT_UNKNOWN;
- NOT_FOUND after ATTEMPTED -> EFFECT_UNKNOWN;
- repeated marker/NOT_FOUND/status observation appends no duplicate Event;
- malformed response -> EFFECT_UNKNOWN, no retry;
- cancellation after ATTEMPTED -> EFFECT_UNKNOWN;
- terminal failed receipt remains terminal failed evidence, not controller failure.

**Step 7 — implement reconciliation and result projection**

Use only the shared client's status method after ATTEMPTED. Validate event-family order and exact command IDs. Return secret-free results; never include lease token, provider home, raw credentials, environment or arbitrary paths.

**Step 8 — verify GREEN**

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_executive_privileged_authority.py \
  tests/test_executive_os_sqlite.py \
  tests/test_executive_privileged_client.py \
  tests/test_executive_privileged_broker.py
python3 -m py_compile control_plane/executive_privileged_authority.py
git diff --check
```

**Step 9 — commit**

```bash
git add control_plane/executive_privileged_authority.py tests/test_executive_privileged_authority.py \
  control_plane/executive_runtime.py tests/test_executive_os_sqlite.py
git commit -m 'feat(executive): authorize job-bound worker readiness checks'
```

---

## Task 5: Compose the closed control command and default-off host configuration

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
{"command":"verify_current_worker_readiness","args":{"job_id":"JOB-...","attempt_id":"ATT-...","fence_generation":1}}
```

Prove exact keys/types, no extra fields, no caller action/slot/socket/path, READY-only dispatch, existing kernel peer gate, typed controller errors and exact JSON result.

Add CLI subcommand:

```text
verify-current-worker-readiness JOB_ID ATTEMPT_ID FENCE_GENERATION
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
- cleanup/rollback removes or leaves inert the wrapper when arming fails;
- ordinary control/worker service startup remains separately controlled.

**Step 6 — implement the fixed wrapper and installer fields**

Use an `exec` wrapper to installed Python + installed `scripts/executive_os_phase1c.py` with fixed config/socket arguments and forwarded command argv. Never use `eval`, `bash -c`, a mutable checkout or caller-supplied socket.

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

**Files:**
- Modify: `ops/executive_os/HOST_PREREQUISITES.md`
- Modify: `docs/superpowers/specs/2026-09-14-executive-job-bound-worker-readiness-design.md` only for proven implementation facts, never to weaken acceptance
- Tests as needed, no new product scope.

**Step 1 — add one end-to-end in-process integration test**

Use a real RuntimeStore, control service, Unix socket, fake fixed broker server and CLI request to prove:
- current Job/Attempt/fence -> control service -> controller -> exact verify-only frame;
- one effect despite concurrent callers;
- terminal result through the real control response;
- lost effect response followed by a fresh service/controller instance -> status-only terminal reconciliation;
- stale fence and direct dedicated-worker broker access refuse.

Place the test in `tests/test_executive_service.py` or a narrowly named new integration test if the owning file becomes unwieldy.

**Step 2 — run focused and owning suites**

```bash
umask 022
python3 -m pytest -o addopts='' -q \
  tests/test_executive_authority.py \
  tests/test_executive_os_sqlite.py \
  tests/test_executive_supervisor.py \
  tests/test_executive_privileged_action.py \
  tests/test_executive_privileged_broker.py \
  tests/test_executive_privileged_client.py \
  tests/test_executive_privileged_authority.py \
  tests/test_mmx_admin.py \
  tests/test_executive_service.py \
  tests/test_c1_installer_control_config.py \
  tests/test_executive_launchd_config.py \
  tests/test_executive_service_control.py
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
6. non-root `mmx-control verify-current-worker-readiness ...`;
7. independent slot/readiness target verification;
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
6. Create/claim one real bounded Job with `REQUEST_WORKER_READINESS` for `codex-01`.
7. Invoke installed `mmx-control` as the non-root operator and prove exact root `verify_only` plus independent readiness target state.
8. Reconcile a deliberately lost client response through the control command with exactly one broker effect.
9. Prove wrong Job, stale fence, unauthorized worker socket and arbitrary action/slot/path all refuse.
10. Prove a fresh native Codex orchestrator discovers and consumes the command without asking for sudo/password. Add Claude attended-orchestrator proof only if the provider session is available; do not claim dedicated Claude worker-slot coverage until the slot catalog supports it.
11. Record exact Runtime Events, broker receipt/request ID, merged release SHA, host/boot identity, no-prompt evidence and remaining P3/P4/P5 gates in durable owners.

Only after these observations may P2-1 become `PROVEN_LIVE` on the Studio. Then advance directly to the P3 secret-free credential-renewal vertical.
