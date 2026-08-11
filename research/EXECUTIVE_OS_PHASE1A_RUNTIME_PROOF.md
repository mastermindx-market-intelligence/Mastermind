# Mastermind Executive OS — Phase 1A Worker Runtime Proof

## Outcome

Phase 1A proves one local, persisted worker/job lifecycle inside Mastermind's existing
`control_plane` package:

```text
create job with eligible quota/capability classes
→ persist job
→ select an eligible AVAILABLE worker capacity class
→ atomically mark job RUNNING and only that capacity class BUSY
→ operator/mock task records a structured checkpoint
→ rate-limited capacity class moves only its active job to RATE_LIMITED
→ atomically requeue the job and detach that capacity class
→ select another eligible worker/class
→ preserve the checkpoint through reassignment
→ atomically persist the result, complete the job, and release its assigned capacity class
```

This is an inert local proof. It does not launch Codex or Claude, manage OAuth or
credentials, schedule autonomous work, touch trading state, or activate a production
runtime.

The Phase 0 technical census merged to `master` while this proof was in flight. Its
production architecture is now the governing next-step boundary: a dedicated SQLite
store on the canonical runtime mount, transactional attempts/leases/events, and a
separate non-root supervisor. This Phase 1A JSON snapshot is intentionally a disposable
state-machine proof; it is not that Executive source of truth and must not be promoted or
wired into a service.

## Reused infrastructure

- `control_plane/` remains the single Mastermind control plane. No second package or
  parallel authority mechanism was created.
- `control_plane.locks.acquire()` provides the existing process-scoped `fcntl.flock`
  primitive. Every state mutation holds one `global:executive_os_phase1a` lock across
  read, validation, mutation, and durable replace.
- `control_plane.run_events.append()` receives bounded post-commit transition receipts.
  It remains best-effort telemetry and is never treated as current-state authority.
- The existing gitignored `jobs/` boundary established by `bridge/job_runner.py` holds
  the local snapshot at `jobs/executive_os_phase1a/state.json`.
- The durable write follows the repository's `portfolio.paper_account` pattern: unique
  same-directory temp file, file `fsync`, `os.replace`, and best-effort directory `fsync`.
- The canonical A0–A7 ladder remains unchanged. `Job.authority_level` defaults to `A0`
  and is stored as inert classification only; Phase 1A does not grant or enforce authority.

Deliberately not reused:

- `control_plane.decision_packet` is the portfolio pre-sizing boundary, not a generic
  worker result schema.
- `control_plane.governance` is reserved for authority/configuration changes; ordinary
  worker capacity and job lifecycle events do not belong there.
- `control_plane.run_ledger.RunHandle` contains an in-process monotonic clock and cannot
  represent a job spanning separate CLI invocations.
- `bridge.job_runner.run_job()` launches a real model, which Phase 1A explicitly forbids.
- Trading SQLite and APScheduler state are domain-specific and are not reused as an
  Executive OS state store.

## Added files and changes

- `control_plane/worker_runtime.py`
  - `Worker`, `Job`, and `JobPayload` dataclasses;
  - worker/job status enums;
  - strict, locked, whole-state `RuntimeStore`;
  - `WorkerRegistry`, `JobRegistry`, and `ResourceBroker`;
  - independent quota-class capacity beneath each worker identity;
  - atomic assign, class-scoped rate-limit, requeue, fail, and complete transitions.
- `scripts/executive_os_phase1a.py`
  - small JSON-printing operator CLI with no provider execution path.
- `tests/test_executive_os_runtime.py`
  - registration, creation, assignment, checkpoint, rate-limit, requeue, failover,
    multi-class concurrency, completion/release, broker mismatch, corruption, lock refusal,
    and CLI persistence tests.
- `.github/workflows/ci.yml`
  - explicitly runs the new runtime proof because this repository's CI names test files.
- `.gitignore`
  - makes the existing `data/governance/` and `data/locks/` runtime boundaries portable
    to clean clones; the state itself is already covered by `jobs/`.
- `control_plane/__init__.py`
  - records the new substrate without implying automatic execution integration.
- `research/EXECUTIVE_OS_PHASE1A_RUNTIME_PROOF.md`
  - this operator and handoff record.

## Objects

`Worker` stores:

```text
worker_id, provider, account_label, worker_type, status, capabilities,
active_job_id, last_seen_at, metadata, quota_classes
```

`quota_classes` is a mapping owned by one provider/account worker identity. Each named
class has its own `status`, `capabilities`, and `active_job_id`. For example, one Claude
account may expose independent `fable-eligible` and `claude-native` capacity. The broker
can assign one job to each class at the same time, and rate limiting either class does not
consume or disable the other.

The required top-level `status`, `capabilities`, and `active_job_id` remain as derived
compatibility summaries, not capacity authority. A running class makes the summary
`BUSY`; otherwise any available class makes it `AVAILABLE`. When multiple classes run,
top-level `active_job_id` is only the first stable representative; every authoritative
job link remains under `quota_classes`. Selection always inspects the named class state.
There is deliberately no scalar `remaining_quota` field.

`Job` stores:

```text
job_id, objective, department, priority, status, assigned_worker_id,
assigned_quota_class, authority_level, branch, worktree, checkpoint, result,
created_at, updated_at
```

One additional `constraints` mapping is necessary for the requested broker behavior. It
supports only `provider`, `required_capabilities`, and `eligible_quota_classes`; it is not
a new authority object. A job may list more than one eligible class so the same job can
fail over across differently named provider capacity pools. Jobs that omit the option are
normalized to the `default` class rather than gaining wildcard access to every pool.

Both checkpoints and results use the same complete structured payload:

```text
summary, completed_steps, current_state, artifacts, next_actions, errors
```

Worker IDs are operator-supplied and validated. Job IDs are allocated from a counter in
the same locked snapshot (`JOB-001`, `JOB-002`, ...), so allocation is atomic and a job's
identity never changes across requeue or failover.

## State machine

### Worker quota-class transitions

| From | Event | To | Active job link |
|---|---|---|---|
| `AVAILABLE` | assign/dispatch to this class | `BUSY` | set |
| `BUSY` | operator reports quota loss for this class | `RATE_LIMITED` | retained until requeue |
| `RATE_LIMITED` | requeue active job | `RATE_LIMITED` | cleared |
| `BUSY` | job completes | `AVAILABLE` | cleared |
| `BUSY` | job fails | `AVAILABLE` | cleared |

These transitions apply to one quota class, not the whole provider account. `DRAINING`,
`OFFLINE`, and `ERROR` are valid class states and are ineligible for broker selection.
The operator may still update all classes explicitly when an entire identity is affected.
Phase 1A adds no heartbeat, lease-expiry, quota meter, or automatic recovery policy.

### Job transitions

| From | Event | To | Checkpoint |
|---|---|---|---|
| `QUEUED` | assign/dispatch to eligible class | `RUNNING` | preserved |
| `RUNNING` | checkpoint | `CHECKPOINTED` | replaced atomically |
| `RUNNING` / `CHECKPOINTED` | assigned quota class rate-limited | `RATE_LIMITED` | preserved |
| `RUNNING` / `CHECKPOINTED` / `RATE_LIMITED` / `FAILED` | requeue | `QUEUED` | preserved |
| `RUNNING` / `CHECKPOINTED` | complete | `COMPLETED` | preserved; result added |
| non-terminal | fail | `FAILED` | preserved; error result added |

`CANCELLED` is part of the initial enum but Phase 1A intentionally adds no cancellation
workflow because it was not required for the proof.

## Persistence and consistency

Workers and jobs live in one versioned JSON snapshot. This is load-bearing: separate files
would create crash windows in which `job.assigned_worker_id/assigned_quota_class` and the
matching `worker.quota_classes[*].active_job_id/status` disagree.

Every write:

1. acquires the existing global `flock` non-blockingly;
2. strictly loads and validates schema plus worker/job cross-links;
3. mutates both linked records in memory;
4. validates the resulting state again;
5. `fsync`s a unique temp file and atomically replaces the snapshot;
6. `fsync`s the containing directory where supported;
7. releases the lock; and
8. emits best-effort operational telemetry.

Lock contention or lock-path failure is a visible operator error; the runtime never writes
unlocked. Malformed or unknown state fails closed and is never silently reset.

This is local-proof durability, not distributed consensus or a production ownership
model. `flock` does not coordinate two hosts and its default namespace follows the chosen
root. The completed Phase 0 census has already selected dedicated SQLite—with migrations,
foreign keys, transactional events, leases/fencing, and a canonical service-owned path—for
the credible runtime. This snapshot exists only to prove the smaller linked state machine.

## Run the demonstration

Use a scratch root to keep the proof separate from any other local operator state:

```bash
DEMO_ROOT="$(mktemp -d)"

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" \
  register-worker claude-01 --provider claude --account-label claude-a \
  --worker-type mock --capability research \
  --quota-class fable-eligible --quota-class claude-native

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" \
  register-worker codex-01 --provider codex --account-label codex-a \
  --worker-type mock --capability research --quota-class codex-native

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" \
  create-job "Investigate foo" --department research --capability research \
  --quota-class fable-eligible --quota-class codex-native

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" workers
python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" jobs

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" dispatch JOB-001

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" \
  checkpoint JOB-001 --summary "Evidence collected" \
  --completed-step "read inputs" --current-state "ready for synthesis" \
  --artifact "jobs/JOB-001/evidence.json" --next-action "write conclusion"

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" \
  worker-status claude-01 RATE_LIMITED --quota-class fable-eligible

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" requeue JOB-001
python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" dispatch JOB-001

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" \
  complete JOB-001 --summary "Investigation complete" \
  --completed-step "write conclusion" --current-state done \
  --artifact "jobs/JOB-001/result.json"

python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" workers
python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" jobs
```

The CLI can also persist a structured failure:

```bash
python3 -m scripts.executive_os_phase1a --root "$DEMO_ROOT" \
  fail JOB-001 --error "mock worker error"
```

That command is valid only from a non-terminal job state.

## Verification

Focused tests:

```text
python3 -m pytest -q tests/test_executive_os_runtime.py tests/test_control_plane.py
57 passed
```

The manual lifecycle was also run through nine separate CLI processes. `claude-01` kept
its independent `claude-native` class available when only `fable-eligible` was rate
limited; that available class was deliberately ineligible for this job, so the broker
reassigned the same job to `codex-01/codex-native`. The final persisted receipt was:

```json
{
  "assigned_worker_id": "codex-01",
  "assigned_quota_class": "codex-native",
  "checkpoint_summary": "Evidence collected",
  "claude_active_job_id": null,
  "claude_fable_status": "RATE_LIMITED",
  "claude_native_status": "AVAILABLE",
  "claude_status": "AVAILABLE",
  "codex_active_job_id": null,
  "codex_status": "AVAILABLE",
  "job_id": "JOB-001",
  "job_status": "COMPLETED",
  "result_summary": "Investigation complete"
}
```

## Limitations

- One local host and one cooperative `flock` domain only.
- One replaceable JSON snapshot; no queue service, database server, migration framework,
  retention policy, or history replay.
- Not the Phase 0 census's production store: no SQLite transaction log, immutable event
  table, attempts, leases, fencing tokens, optimistic versions, or restart reconciliation.
- Deterministic first eligible worker by `worker_id`, then quota-class name; no price,
  latency, measured quota, or quality optimization.
- No lease, timeout, heartbeat monitor, retry budget, attempt ledger, or automatic recovery.
- Provider/account and quota-class values are labels only. There is no scalar quota
  assumption, but Phase 1A does not measure remaining capacity, reset windows, token
  budgets, or provider-specific limits. No secret resolution, OAuth switching, account
  discovery, or provider health authority exists here.
- No model process is invoked. Execution is represented by manual checkpoint/complete/fail
  commands or test mocks.
- No production service, scheduler job, API endpoint, or UI was added.

## Phase 1B connection seam

Phase 1B should connect, not redesign:

1. Port these registry/FSM seams into the completed Phase 0 census's dedicated SQLite
   core before any service integration; add migrations, attempt/lease/fencing records,
   transactional events, and restart reconciliation there rather than expanding this JSON.
2. Add a narrow worker adapter that reads capacity from Macro Dashboard's existing shared
   provider ledger/admin control plane and updates each named quota class independently;
   do not create a Mastermind credential island or collapse the classes into one scalar.
3. Map a selected registered worker to the existing provider waterfall in
   `brain/provider_waterfall.py` and the bounded job envelope in `bridge/job_runner.py`.
4. Wrap one manually triggered mock/CLI execution with the existing job-level run ledger,
   then translate its result into `JobPayload`.
5. Add leases/heartbeats and explicit attempt records before any unattended execution.
6. Preserve the proven registry and state-transition behavior as an adapter boundary while
   replacing this local snapshot; do not migrate its scratch data into authority state.

Autonomous CEO behavior, trading authority, OAuth automation, broad Fable orchestration,
and production activation remain out of scope.
