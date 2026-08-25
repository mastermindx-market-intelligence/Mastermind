# Executive OS Receipt-Gated Autonomy Arm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Every
> production change follows strict red-green-refactor TDD and every completion
> claim follows `superpowers:verification-before-completion`.

**Goal:** Turn one formally accepted, exact-release Executive OS host from the
current production-unarmed composition into a receipt-gated autonomous system,
then prove one typed Chairman intent can advance through the existing Runtime,
COO, Codex worker, independent review, and aggregation path without manual
prompt carriage.

**Architecture:** Add one shared, secret-free autonomy receipt validator; one
root-only transactional `status/arm/disarm` CLI; and narrow control-service and
worker-broker admission guards. Reuse the existing configs, LaunchDaemons,
provider-readiness receipt, acceptance receipt, Gate B receipt, Runtime,
service controller, and bounded COO tick. Add no daemon, lifecycle table,
credential plane, network listener, plugin grant, MCP production write, or
retry/failover path.

**Tech Stack:** Python 3.12 standard library, SQLite through the existing
Executive Runtime, asyncio private AF_UNIX services, launchd shell wrappers,
pytest, macOS ownership/mode/ACL checks, canonical JSON and SHA-256 receipts.

**Spec:**
`docs/superpowers/specs/2026-08-24-executive-os-receipt-gated-autonomy-arm-design.md`

## Global Constraints

- The implementation base is protected master
  `4d323d03e4151449a4b76abfdfefca1d56825fde`; use only the existing carrier
  `codex/executive-autonomy-arm-20260824-g7`.
- Executive Runtime remains the sole Job/Attempt/Worker/Event/session lifecycle
  authority. No new database schema, queue, registry, scheduler, daemon,
  watcher, sidecar, identity store, or retry plane.
- Agent OS remains durable organizational memory; GitHub remains
  implementation and evidence truth.
- Both installed arm bits move together or both converge false. A mixed state,
  incomplete transaction, ambiguous process identity, or rollback uncertainty
  is `EFFECT_UNKNOWN` and is never automatically retried.
- The arm transaction never reads credential bytes, provider-home contents,
  prompt text, model output, cookies, session stores, account identity, private
  URLs, or process arguments. Receipts contain only bounded metadata and
  digests.
- `arm` reuses a current passing provider-readiness receipt. It never calls
  login, identity enrollment, inference, or a canary-spending operation.
- Credential enrollment/replacement is a native operator boundary. It refuses
  while armed and requires a verified `disarm` first.
- Control-service startup and every autonomous cycle, plus worker-broker startup
  and every provider start, fail closed on a missing, stale, expired, or
  mismatched receipt.
- Work already active when readiness expires may only reconcile/finish. No new
  Attempt or provider session may start.
- Plugins remain empty, Executive MCP remains read-only/fixture-only, Docs MCP
  remains the only planner MCP, and the frozen G4 capability/profile/helper/
  security digests remain byte-identical.
- Implementation, green tests, merge, exact install, provider readiness, Gate
  B, formal acceptance, `ARMED_READY`, typed-intent completion, rollback
  rehearsal, final re-arm, and durable closeout are distinct receipts.

---

## File Structure

- `control_plane/executive_autonomy.py` — new pure/shared receipt schema,
  canonical digest, metadata validation, config binding, deadline checks, and
  closed status classification. It imports no service, broker, Runtime, login,
  subprocess, launchd, or provider module.
- `ops/executive_os/autonomy_control.py` — new root-only host policy and
  crash-recoverable `status/arm/disarm` transaction using fixed production
  paths and dependency-injected host adapters for tests.
- `ops/executive_os/autonomy-control.sh` — new fixed wrapper that requires root,
  exact installed-release cwd, and the pinned Executive Python with
  `-I -S -B`.
- `scripts/executive_os_phase1c.py` — load and bind the arm receipt only when
  the control config is armed; inject the same guard into the control service.
- `control_plane/executive_service.py` — invoke an injected guard at armed
  startup and immediately before each explicit or scheduled COO cycle;
  quarantine and record one bounded refusal without retry.
- `scripts/executive_os_phase1c_worker.py` — load and bind the same arm receipt
  only when the worker config is armed; inject the guard into the broker.
- `control_plane/executive_worker_broker.py` — invoke the guard before every
  sealed-exec or Operator Harness provider start/validation boundary.
- `ops/executive_os/provision-worker-auth.sh` — refuse explicit credential
  enrollment/replacement while the canonical autonomy state/configs are armed.
- `ops/executive_os/install.sh` — install/attest the new wrapper and module;
  continue rendering both arm bits false.
- `ops/executive_os/HOST_PREREQUISITES.md` — exact post-acceptance
  status/arm/proof/disarm/re-arm runbook.
- `tests/test_executive_autonomy.py` — pure schema, status, expiry, digest, and
  secret-hygiene tests.
- `tests/test_executive_autonomy_control.py` — gate, transaction, crash,
  rollback, idempotency, and no-secret host-policy tests.
- Existing service, worker, launchd, installer, worker-auth, and acceptance test
  modules — narrow regression and mutation fences.

---

### Task 1: Pure autonomy receipt and guard contract

**Files:**

- Create: `control_plane/executive_autonomy.py`
- Create: `tests/test_executive_autonomy.py`

**Interfaces:**

- `AutonomyRefusal(code: str)` with a closed reason-code set.
- `ArmBinding` containing only exact release/config/capability/readiness
  digests, credential class, deadlines, and transaction identity.
- `canonical_sha256(value)`, `sha256_file(path)`,
  `validate_receipt_document(payload, ...)`, `validate_receipt_file(path, ...)`,
  and `classify_status(...)`.
- `validate_receipt_file` accepts exact expected values; it does not discover or
  repair config and it never opens the auth file.

- [ ] **Step 1: Write failing schema/digest/happy-path tests.** Cover exact
  field set, canonical digest stability, `root:wheel`/`0444` metadata through an
  injected metadata object, exact release and both config digests, frozen G4
  digests, readiness digest/deadline, and `ARMED_READY`.
- [ ] **Step 2: Run the focused tests and observe the import failure.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_autonomy.py -x
  ```

- [ ] **Step 3: Implement the smallest closed schema and validators.** Use
  canonical UTF-8 JSON with sorted keys, no NaN, bounded strings, exact SHA-256
  regexes, strict UTC timestamps, and an injectable clock.
- [ ] **Step 4: Write failing adverse/status-precedence tests.** Cover missing,
  malformed, extra-field, link-count, ACL, owner/mode, release/config/profile/
  helper/security/readiness mismatch, exact-expiry, near-expiry, transaction
  marker, mixed configs, service ambiguity, and the specified precedence.
- [ ] **Step 5: Implement the adverse cases and rerun the module.**
- [ ] **Step 6: Add a secret-hygiene mutation test.** Reject fields or values
  resembling auth, token, cookie, prompt, model output, provider-home content,
  URLs, process arguments, or account identifiers.
- [ ] **Step 7: Run and commit.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_autonomy.py
  git add control_plane/executive_autonomy.py tests/test_executive_autonomy.py
  git commit -m 'feat(executive): define autonomy receipt guard'
  ```

### Task 2: Read-only host evidence and closed `status`

**Files:**

- Create: `ops/executive_os/autonomy_control.py`
- Create: `ops/executive_os/autonomy-control.sh`
- Create: `tests/test_executive_autonomy_control.py`
- Modify: `ops/executive_os/install.sh`
- Modify: `tests/test_executive_launchd_config.py`

**Interfaces:**

- Fixed production constants for system/config/runtime/release/config/receipt/
  plist/service paths; callers cannot override them.
- `HostEvidence` adapter with bounded methods for safe metadata, installed
  identity, config loading, service state, Runtime quiescence, and JSON output.
- CLI: `status --expected-sha SHA` returns one JSON document and exit `0` only
  for `UNARMED`/`ARMED_READY`; adverse closed statuses use a documented nonzero
  code without traceback or raw command output.

- [ ] **Step 1: Write failing parser and fixed-path tests.** Prove no flags exist
  for system root, runtime root, config path, receipt path, service label,
  release root, or subprocess command.
- [ ] **Step 2: Write failing `UNARMED` and every-precedence status test** using
  a hermetic injected host adapter.
- [ ] **Step 3: Run the focused red tests.**
- [ ] **Step 4: Implement fixed constants, sanitized JSON output, and read-only
  status classification.** Import the existing control/worker config loaders;
  do not duplicate their schema law.
- [ ] **Step 5: Add wrapper/install tests.** Prove the wrapper uses only the
  pinned Executive Python, `-I -S -B`, exact installed-release cwd, and root;
  prove `install.sh` includes/attests it while rendering both arms false.
- [ ] **Step 6: Implement wrapper/install integration and rerun.**
- [ ] **Step 7: Commit.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_autonomy.py \
    tests/test_executive_autonomy_control.py \
    tests/test_executive_launchd_config.py
  git add ops/executive_os/autonomy_control.py \
    ops/executive_os/autonomy-control.sh ops/executive_os/install.sh \
    tests/test_executive_autonomy_control.py \
    tests/test_executive_launchd_config.py
  git commit -m 'feat(executive): add read-only autonomy status'
  ```

### Task 3: Exact arm admission gates before mutation

**Files:**

- Modify: `ops/executive_os/autonomy_control.py`
- Modify: `tests/test_executive_autonomy_control.py`

**Required gates:** exact installed link/manifest/acceptance/requested SHA;
safe ancestors/files; exact passing acceptance summary; exact passing Gate B;
`provider_readiness.py reuse` with reviewed credential kind, binding class, and
expiry; at least thirty minutes remaining; both configs false and mutually
consistent; stopped/unloaded services; Runtime `create=False` integrity and no
live/ambiguous Attempt; no service-UID process after bounded stop/sweep; no
transaction marker.

- [ ] **Step 1: Write one failing happy-path admission test.** Assert the exact
  predicate receipt and verify every evidence method is called once in order.
- [ ] **Step 2: Implement admission without config writes.** Gate B uses the
  existing `git_handoff_preflight.validate_receipt`; acceptance uses the exact
  v1 summary/field law; readiness calls only `reuse` with bounded sanitized
  status capture.
- [ ] **Step 3: Add a table-driven fail-before-write test for every gate.** For
  each injected failure, assert zero config writes, zero service starts, zero
  inference/login commands, and a closed refusal code.
- [ ] **Step 4: Add Runtime quiescence mutation tests.** Cover `CLAIMED`,
  `RUNNING`, `CHECKPOINTED`, `CANCEL_REQUESTED`, malformed status, DB integrity
  failure, absent DB, and read-only/create-false enforcement.
- [ ] **Step 5: Add Gate B/acceptance/readiness freshness and identity mismatch
  tests**, including a moving protected branch that does not invalidate an
  already accepted installed exact SHA.
- [ ] **Step 6: Rerun and commit.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_autonomy_control.py
  git add ops/executive_os/autonomy_control.py \
    tests/test_executive_autonomy_control.py
  git commit -m 'feat(executive): gate autonomy arm on exact receipts'
  ```

### Task 4: Crash-safe two-config arm/disarm transaction

**Files:**

- Modify: `ops/executive_os/autonomy_control.py`
- Modify: `tests/test_executive_autonomy_control.py`

**Transaction phases:** lock; archive two prior configs; derive candidates;
validate under real service UIDs; record prepared digests; worker rename+fsync;
control rename+fsync; arm receipt rename+fsync; start worker then control through
the existing service controller; prove PID/principal/socket/`READY`; remove
marker. Synchronous failure stops services and restores both false. Unproven
rollback retains the marker and returns `EFFECT_UNKNOWN`.

- [ ] **Step 1: Write a failing happy-path `arm` test.** Assert both bits become
  true, every unrelated config field is byte-for-byte equivalent after
  canonical decode, the receipt binds both final file digests, services start
  worker-first/control-second, and the marker is removed only after `READY`.
- [ ] **Step 2: Implement candidate derivation and durable write primitives.**
  Use same-directory `O_EXCL` temporaries, explicit file/dir fsync, atomic
  rename, root-controlled modes, no symlink traversal, and no generic path
  parameters.
- [ ] **Step 3: Implement arm happy path and idempotent exact replay.** A second
  identical `arm` returns the existing receipt without rewrite or restart;
  changed evidence refuses until disarm.
- [ ] **Step 4: Write failure injection after every durable phase.** Assert
  exact rollback to both false or retained marker; never a success with mixed
  bits; never automatic retry.
- [ ] **Step 5: Implement rollback and retained-marker recovery.** `disarm`
  must be allowed when freshness/acceptance is absent because it only shrinks
  authority, but it must still prove fixed install/config/service identity.
- [ ] **Step 6: Add explicit disarm/idempotency tests.** Prove service stop
  order, both false, `DISARMED` receipt, stopped final state, and safe recovery
  from each partial phase.
- [ ] **Step 7: Rerun and commit.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_autonomy_control.py
  git add ops/executive_os/autonomy_control.py \
    tests/test_executive_autonomy_control.py
  git commit -m 'feat(executive): transact autonomy arm and rollback'
  ```

### Task 5: Control-service runtime enforcement

**Files:**

- Modify: `scripts/executive_os_phase1c.py`
- Modify: `control_plane/executive_service.py`
- Modify: `tests/test_executive_service.py`
- Modify: `tests/test_executive_launchd_config.py`

**Interfaces:**

- `ExecutiveControlService(..., autonomy_guard=None)`; an armed config requires
  a guard, an unarmed config preserves current fixture behavior.
- `_require_current_autonomy()` executes before armed startup reconciliation
  and immediately before `_run_coo_cycle_once` can select/claim/dispatch.
- Failure sets `QUARANTINED`, admits no new work, and records at most one
  secret-free refusal event on a known root.

- [ ] **Step 1: Write failing startup tests.** Armed-without-guard and
  guard-refusal must fail before Runtime mutation, supervisor reconciliation,
  socket serving, or tick creation; unarmed fixtures remain unchanged.
- [ ] **Step 2: Implement constructor/startup enforcement.** The production
  script binds exact config digests, release SHA, receipt path, frozen G4
  digests, and readiness deadline into the shared validator.
- [ ] **Step 3: Write failing pre-cycle and expiry-crossing tests.** Cover
  explicit cycle, scheduled tick, missing/mismatched receipt, and active
  Attempt reconciliation/finish with no new cycle/session.
- [ ] **Step 4: Implement pre-cycle guard/quarantine/refusal behavior.** Do not
  cancel an already running Attempt solely due to time expiry; block only the
  next admission/provider start.
- [ ] **Step 5: Run the focused service suites and commit.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_autonomy.py \
    tests/test_executive_service.py \
    tests/test_executive_launchd_config.py
  git add scripts/executive_os_phase1c.py \
    control_plane/executive_service.py tests/test_executive_service.py \
    tests/test_executive_launchd_config.py
  git commit -m 'feat(executive): enforce arm receipt in control service'
  ```

### Task 6: Worker-broker pre-provider enforcement

**Files:**

- Modify: `scripts/executive_os_phase1c_worker.py`
- Modify: `control_plane/executive_worker_broker.py`
- Modify: `tests/test_executive_worker_broker.py`
- Modify: `tests/test_executive_operator_broker.py`
- Modify: `tests/test_executive_agent_capabilities.py`

**Interfaces:**

- `ExecutiveWorkerBroker(..., autonomy_guard=None)`; an armed Operator Harness
  requires the guard, while unarmed and hermetic test configurations preserve
  existing behavior.
- Guard at broker startup and before ordinary sealed-exec `start`, OHF
  validation, OHF start/resume, and every new App Server session/turn boundary
  that can create provider effect.

- [ ] **Step 1: Write failing startup and ordinary-exec tests.** Refusal occurs
  before adapter construction, process spawn, run-root creation, or busy-state
  mutation.
- [ ] **Step 2: Write failing OHF tests.** Cover validate/start/resume/new turn;
  collection/reconciliation of an existing run remains available without
  opening a new provider session.
- [ ] **Step 3: Implement the injected guard and production binding.** The
  worker script loads the exact same receipt but verifies its own config digest
  and expected control digest.
- [ ] **Step 4: Run capability mutation fences.** Prove profile, capability,
  native-helper, security config, Docs MCP, no-plugin, no-write-helper, and
  subagent inheritance contracts are unchanged.
- [ ] **Step 5: Commit.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_worker_broker.py \
    tests/test_executive_operator_broker.py \
    tests/test_executive_agent_capabilities.py
  git add scripts/executive_os_phase1c_worker.py \
    control_plane/executive_worker_broker.py \
    tests/test_executive_worker_broker.py \
    tests/test_executive_operator_broker.py \
    tests/test_executive_agent_capabilities.py
  git commit -m 'feat(executive): guard every worker provider start'
  ```

### Task 7: Credential rotation interlock and host runbook

**Files:**

- Modify: `ops/executive_os/provision-worker-auth.sh`
- Modify: `tests/test_executive_worker_auth_provisioner.py`
- Modify: `ops/executive_os/HOST_PREREQUISITES.md`
- Modify: `tests/test_executive_python_runtime_provisioner.py`

- [ ] **Step 1: Write failing static and hermetic shell tests.** Explicit
  enrollment/replacement modes must check canonical autonomy state and both
  configs before readiness deletion, logout, stdin/token handling, or device
  login. `--verify-only` and `--verify-ready` remain read-only and allowed.
- [ ] **Step 2: Implement the fixed disarm interlock.** It does not call the arm
  CLI or edit configs; it refuses with a bounded message directing the operator
  to the explicit shrink-only command.
- [ ] **Step 3: Write the exact host journey.** Install false; native enroll;
  readiness; Gate B; acceptance; status; arm; typed intent proof; disarm
  rehearsal; unchanged-input final re-arm; expiry/rotation recovery. Include
  distinct receipts and stop conditions.
- [ ] **Step 4: Add documentation/static assertions and commit.**

  ```bash
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_worker_auth_provisioner.py \
    tests/test_executive_python_runtime_provisioner.py
  git add ops/executive_os/provision-worker-auth.sh \
    ops/executive_os/HOST_PREREQUISITES.md \
    tests/test_executive_worker_auth_provisioner.py \
    tests/test_executive_python_runtime_provisioner.py
  git commit -m 'docs(executive): gate credential rotation on disarm'
  ```

### Task 8: Integrated regression, mutation review, and delivery

**Files:**

- Modify only as required by concrete failing evidence from Tasks 1-7.
- Add: exact implementation/evidence record in the existing repository-owned
  durable location selected by current protected Skillpack instructions.

- [ ] **Step 1: Run formatting/static checks and the focused Executive gate.**

  ```bash
  git diff --check
  /private/tmp/mastermind-fixed-port-repair.9Ju4RK/venv/bin/python -m pytest -q \
    tests/test_executive_autonomy.py \
    tests/test_executive_autonomy_control.py \
    tests/test_executive_launchd_config.py \
    tests/test_executive_acceptance_observability.py \
    tests/test_executive_worker_auth_provisioner.py \
    tests/test_executive_agent_capabilities.py \
    tests/test_executive_service.py \
    tests/test_executive_supervisor.py \
    tests/test_executive_operator_broker.py \
    tests/test_executive_worker_broker.py
  ```

- [ ] **Step 2: Run the repository contract gate used by protected master.**
  Record exact command, result, count, duration, and any environment-only skip.
- [ ] **Step 3: Perform adversarial self-review.** Inspect the full base diff
  for duplicate lifecycle/state, secret reads, dynamic path/label/command
  inputs, login/inference reachability, unsafe filesystem operations, mixed
  configs, swallowed `EFFECT_UNKNOWN`, automatic retry, provider starts without
  guards, and G4 capability drift.
- [ ] **Step 4: Re-run all affected tests after review fixes.**
- [ ] **Step 5: Re-pin protected master and reconcile ancestry.** If master
  moved, inspect semantic overlap and rebase only while the carrier is clean;
  rerun the full proof after any rebase.
- [ ] **Step 6: Push one carrier, open one PR, and wait for all CI.** Do not
  merge on local green alone. Record PR/head/base/checks.
- [ ] **Step 7: Merge only after green independent review.** Verify the merged
  protected-master SHA and exact changed files.

### Task 9: Exact-host acceptance and final autonomy proof

**Prerequisite:** The dedicated worker credential exists under the worker-only
provider home and a current finite expiry is available without exposing the
credential. This is the only required native user handoff.

- [ ] **Step 1: Install the exact merged SHA with both arm bits false.** Verify
  release manifest, current link, file identities, plists, pinned Python/Codex,
  and stopped services.
- [ ] **Step 2: Mint/reuse provider readiness.** Spend at most one canary only
  when no valid receipt exists; never retry an ambiguous inference effect.
- [ ] **Step 3: Run Gate B exactly once and inspect its sanitized receipt.**
- [ ] **Step 4: Run formal Phase 1C-A acceptance and inspect every named PASS.**
- [ ] **Step 5: Run `status`, then one `arm`.** Require exact `UNARMED` followed
  by exact `ARMED_READY`; no manual config edit.
- [ ] **Step 6: Submit one harmless strict-v2 Chairman intent.** It must be
  independently useful, bounded to the existing test/repository authority, and
  require one OpenAI Docs lookup so the exact parent/helper/Docs-MCP lineage can
  be proven without recording content.
- [ ] **Step 7: Observe the same Runtime root to terminal completion or honest
  exception.** Prove planner, work, independent review, any bounded repair/null,
  aggregation, and no extra child/MCP/plugin/skill/account/session/process.
- [ ] **Step 8: Disarm and prove rollback.** Both services stopped, both bits
  false, `DISARMED` receipt, second status `UNARMED`.
- [ ] **Step 9: Final re-arm.** Allowed under the approved rollout only if every
  receipt/digest/input is unchanged and no new authority appeared; otherwise
  stop for fresh Chairman authorization.
- [ ] **Step 10: Update the canonical Agent OS durable handoff.** Record exact
  SHAs, PR, install, readiness/Gate B/acceptance/arm/intent/disarm/re-arm receipt
  digests, terminal state, known exclusions, next OAuth/plugin wave, and exact
  recovery command. Never record secrets, prompts, outputs, private paths that
  disclose identity, or session-store contents.

## Completion Evidence

The wave is complete only when all of the following are separately proven:

1. merged protected-master implementation and green CI;
2. exact installed release with both configs initially false;
3. current dedicated-worker provider readiness;
4. exact-SHA Gate B PASS;
5. exact-SHA formal acceptance PASS;
6. one root-only transaction reaches `ARMED_READY`;
7. one real typed intent completes or reaches an honest surfaced exception
   without Chairman prompt carriage;
8. exact G4 parent/helper/Docs-MCP lineage and no extra capability;
9. disarm rehearsal proves stopped services and both bits false;
10. unchanged-input final re-arm reaches `ARMED_READY`; and
11. canonical durable Agent OS handoff makes the next session recoverable
    without this chat.
