# Mastermind Executive OS — Phase 1B Real Codex Worker

**Status:** sealed local acceptance proof passed. The authoritative report is
`/private/tmp/mastermind-phase1b-sealed-proof.ToWh0D/phase1b-proof-report.json`, SHA-256
`4d50c098a6c28688717dea43b206dcdb584352e12625c5f36f31106065400104`. It records one
native-Codex success path and one verified process-group kill/restart/requeue path. GitHub
delivery, merge, deployment, and live-host verification have **NOT YET RUN**.

The branch was created from Phase 1A `origin/master` at
`ab9269d12803f0160cc7dc0711ebc1452f4d6707`. That is a design baseline, not the final Phase
1B head, merge, or deployed SHA.

| Evidence lane | State in this draft |
|---|---|
| Durable schema/source review | sealed SQLite receipt, integrity check, migration row, and reopen projections passed |
| Automated focused tests | 126 passed, 1 skipped; exit 0 |
| Real native Codex success path | passed: `JOB-001` / `ATT-d8947b722aff4e36924ebc6323bd70a8` |
| Verified process-group kill/restart/requeue | passed: `JOB-002` / `ATT-2d55e286357741e984690c90d14fd20b` |
| Full local/CI-equivalent suite | local full collection blocked by two missing dependencies; GitHub CI **NOT YET RUN** |
| PR, merge, deployment, health, inertness | **NOT YET RUN** |

## 1. Outcome boundary

Phase 1B is the smallest real-worker vertical slice that connects the Phase 1A registry/FSM
to the durable foundation selected by the Phase 0 census:

```text
explicit operator action
→ fail-closed Executive authority decision
→ durable SQLite Job and fenced Attempt claim
→ isolated credential-free exact-SHA Git clone
→ one attested native Codex process in that clone
→ one declared file change
→ supervisor-owned execution of one persisted Python validation argv
→ schema-valid mastermind.executive_worker_result/v1 manifest
→ transactional terminal Job/Attempt/Event state
```

The bounded proof objective is:

> Create `research/executive_os_phase1b_worker_proof/receipt.md` in an isolated,
> credential-free clone of one exact repository SHA; return a structured artifact with an
> empty model validation list; then have the supervisor execute the one persisted Python
> validation argv directly and record its hash-only `ValidationReceipt`.

The proof has no portfolio, Macro publication, billing, credential-administration, service,
PR, merge, deployment, or capital effect. The receipt is deliberately harmless and can be
discarded with its isolated workspace.

### Explicit non-integration

Phase 1B does **not**:

- import from or register with `app/` or the FastAPI process;
- add an APScheduler job or change any financial cadence;
- start a daemon, systemd unit, background worker, or boot-time supervisor;
- expose a network API or UI;
- call `bridge.job_runner.run_job()` or turn that file helper into a second queue;
- connect the worker to portfolio construction, paper state, Prophet, Neural Web, Macro
  Metabolism, provider rotation, or autonomous delivery;
- grant push, PR, merge, service-control, deploy, credential, billing, delete, or capital
  authority; or
- import the Phase 1A JSON snapshot.

Deploying the code is therefore inert. A deployment copies importable code and policy, but
does not create the Executive database, prepare a workspace, claim a job, or launch Codex.
Only an explicit Phase 1B operator entry point may instantiate and run this path.

## 2. Components and ownership

| Surface | Phase 1B responsibility |
|---|---|
| `control_plane/executive_runtime.py` | SQLite source of truth; migrations; Worker, quota-class, Job, Attempt, lease/fence, event, cancellation, and reconciliation APIs |
| `control_plane/worker_runtime.py` | Phase 1A import compatibility facade; re-exports the durable runtime and never reads the legacy JSON snapshot |
| `control_plane/executive_authority.py` | Code-pinned, YAML-reviewed Executive capability policy and scoped authorization decision |
| `control_plane/executive_workspace.py` | Supervisor-owned exact-SHA private clone with no remote and no shared Git directory |
| `control_plane/codex_worker.py` | `CodexWorkerAdapter`: direct one-shot native Codex adapter, process-group supervision, structured result collection, and validation brokerage |
| `config/authority_map.yml` | Reviewed `executive_worker_policy`; portfolio A0–A7 remains a separate effect taxonomy |
| `scripts/executive_os_phase1b.py` | Claim-neutral durable inspection, worker registration, and authority-aware Job creation |
| `scripts/executive_os_phase1b_proof.py` | Explicit, gated real-process acceptance composition root; no scheduler or app import |

`control_plane.run_events` remains best-effort compatibility telemetry. It is not lifecycle
authority. The SQLite `events` table is the transactional audit record for this slice.

## 3. Durable schema

### 3.1 Location and connection contract

The default store is:

```text
<root>/data/control_plane/executive.sqlite3
```

On the canonical VPS layout that path belongs under the separately mounted runtime-data
tree, not the Git release. `.gitignore` excludes `data/control_plane/` so the database, WAL,
SHM, and local proof receipts cannot enter a commit.

`RuntimeStore` opens SQLite with:

- `PRAGMA foreign_keys=ON` on every connection;
- `PRAGMA journal_mode=WAL`;
- `PRAGMA synchronous=FULL`;
- a deliberate busy timeout; and
- `BEGIN IMMEDIATE` for each state mutation.

The landed constant is `DEFAULT_LEASE_SECONDS = 60`. Heartbeats extend the expiry;
they do not create a second lease.

**Landed defaults and sealed store receipt**

- Phase 1B implementation commit SHA: **NOT YET AVAILABLE**. The proof controller ran from
  an uncommitted Phase 1B task worktree whose checked-out `HEAD` was still the Phase 1A
  baseline; this is a delivery/reproducibility limitation, not a merged-head proof.
- `DEFAULT_LEASE_SECONDS = 60`.
- `DEFAULT_BUSY_TIMEOUT_MS = 5000`.
- Proof database:
  `/private/tmp/mastermind-phase1b-sealed-proof.ToWh0D/data/control_plane/executive.sqlite3`;
  file mode `0600`; SHA-256
  `e5c0a6a00532ab2bc98fe77b83ff438c4742237e3cb34de4ef4b8556db53a7d6`.
- The proof root and database parent were mode `0700`; the isolated clones were pinned to
  `ab9269d12803f0160cc7dc0711ebc1452f4d6707` with zero remotes.

### 3.2 Physical tables

Migration 1, `executive_runtime_core`, creates:

| Table | Durable responsibility |
|---|---|
| `schema_migrations` | Ordered version, name, SHA-256 checksum, and applied timestamp |
| `workers` | Stable logical worker identity, provider/account label, worker type, identity status, metadata, timestamps, and optimistic version |
| `worker_quota_classes` | Independent named capacity under a worker: provider, model, effort, cost class, capabilities, status, held attempt, fence counter, metadata, timestamps, and version |
| `jobs` | Objective, department, priority, status, constraints, assigned capacity, current attempt, inert A0–A7 classification, workspace/branch references, checkpoint/result, retry bounds, availability, cancellation time, timestamps, and version |
| `attempts` | Immutable attempt identity and number, selected capacity, status, fence generation, opaque lease token, owner/expiry/heartbeat, checkpoint sequence and payload, result/error, timestamps, and version |
| `events` | Immutable, sequenced state-change receipt with command identity and Job/Attempt/Worker/quota-class correlation |

Expected schema invariants include:

1. one active leased attempt per Job;
2. one active leased attempt per `(worker_id, quota_class)`;
3. unique `(job_id, attempt_number)`;
4. paired Job worker/quota assignment and a consistent current Attempt foreign key;
5. a `QUEUED` Job has no current Attempt;
6. a completed Job and Attempt have a result;
7. a terminal Attempt has a finish time and no lease token;
8. available capacity has no held Attempt; busy capacity has one;
9. unique per-aggregate event sequence and unique command ID;
10. events cannot be updated or deleted; and
11. terminal Attempts cannot be rewritten. A retry is a new Attempt row.

Opaque lease tokens are stored only in the protected database and returned only on the
in-process `AttemptLease` object. `Attempt.to_dict()`, `AttemptLease.to_dict()`, Event
payloads, logs, and proof transcripts must not expose them.

### 3.3 Worker and result contracts

`WorkerQuotaClass` is the capacity authority. The top-level `Worker.status`, capabilities,
and active Job remain compatibility projections. A worker identity may expose multiple
independent classes without collapsing provider capacity to one scalar.

The provider result contract is named exactly:

```text
mastermind.executive_worker_result/v1
```

The identity-bound schema generated by `worker_result_schema()` closes additional properties
and binds schema version, Job ID, Attempt/run ID, worker ID, terminal status, summary,
completed steps, current state, declared artifact paths, next actions, and errors. The
provider field `validations` is required but constrained to `maxItems: 0`; the model cannot
self-attest validation. Actual validation argv/exit/output hashes, repository base SHA, policy
hash, Git changes, artifact size/hash, process identity, provider session, usage, and stream
hashes are supervisor/runtime receipts outside the provider-authored JSON.

**Result-schema attestation:** the generated 2,017-byte schema at
`runs/ATT-d8947b722aff4e36924ebc6323bd70a8/input/worker-result.schema.json` hashes to
`ae7f49ae53203ea56143c64a8e46ea33df379cc6ff2e3097357f752bd1818d7b`. The validated
770-byte result hashes to
`a75a5e9505bb83db5ae52be3f530bcd523f99539f6550f3b8cc08df912933ae0`; its provider
`validations` value is `[]`. The 3,843-byte accepted collection receipt hashes to
`8c7906d04f8de5fcddf7b5ff79344a6dfba134064d1fd38b282630f5b7e82f21`, and the 721-byte
supervisor validation receipt hashes to
`51c51de289ec63b11a28f71ba186decaa002d32014faa313f37efbedee9b5b98`.

## 4. Migrations and compatibility

`RuntimeStore._migrate()` runs migrations inside `BEGIN EXCLUSIVE`. Each migration is an
append-only `(version, name, statements)` entry. The store hashes normalized statements and
persists the checksum. It fails closed when:

- the database contains an unknown future version;
- a known migration's name or checksum differs from the code;
- a DDL statement fails; or
- `PRAGMA foreign_key_check` reports a violation.

There is no down-migration and no silent reset. Rolling application code backward across an
unknown database version must fail rather than reinterpret newer state.

`control_plane/worker_runtime.py` keeps Phase 1A imports working by re-exporting the durable
module. Its storage contract intentionally changes: `Runtime.at(root)` now opens SQLite,
while the Worker/Job registry shapes and deterministic broker ordering remain compatibility
surfaces.

The old local snapshot remains at the historical location if an operator created one:

```text
jobs/executive_os_phase1a/state.json
```

Phase 1B never reads, imports, deletes, renames, or treats it as authority. It was a disposable
state-machine proof, not production data. Portfolio, learning, governance JSONL, runlog,
APScheduler, and `data/bot.db` state are likewise not migrated.

**Migration receipts**

- The sealed database contains exactly migration version `1`, name
  `executive_runtime_core`, checksum
  `a6fdeed00e30d63e9d21a7e595bae44d00a10d39a5097534726e049548faf656`, applied at
  `1786479822233` ms since epoch. `PRAGMA integrity_check` returned `ok` and
  `PRAGMA foreign_key_check` returned no rows.
- The live-connection contract is `journal_mode=WAL`; the passed
  `test_sqlite_defaults_pragmas_migration_and_five_durable_objects` asserts the observed
  value is `wal`. The proof report did not separately serialize that PRAGMA, so source plus
  the focused test—not an invented report field—is the receipt.
- A fresh `RuntimeStore` reopen reconstructed the completed Job and Attempt and the released
  quota snapshot without reapplying or changing the single migration row. Focused tests cover
  per-connection foreign-key enablement and prove that the legacy JSON snapshot is not
  imported.

## 5. Lifecycle and fencing

### 5.1 Normal attempt

The durable lifecycle is:

```text
Job QUEUED
→ AttemptRegistry.claim_job()
→ one eligible AVAILABLE quota class selected in stable worker/class order
→ fence counter increments
→ new opaque lease token and monotonically numbered Attempt in CLAIMED
→ Job RUNNING + Attempt CLAIMED + quota class BUSY + JOB_CLAIMED event
   commit in one transaction
→ CodexWorkerAdapter.start()
→ AttemptRegistry.record_process() persists the complete ProcessRef identity
→ AttemptRegistry.mark_running() changes CLAIMED to RUNNING
→ heartbeat and/or ordered checkpoint under attempt ID + fence + token
→ schema/artifact/validation checks outside model prose
→ complete_attempt() or fail_attempt()
→ terminal Attempt + Job result + capacity release + immutable Event
   commit in one transaction
```

Every worker mutation calls the leased-attempt guard. It rejects an unknown or terminal
Attempt, stale fence generation, wrong lease token, expired lease, non-current Attempt, or
broken Job/capacity link. Token comparison is constant-time. A heartbeat extends the lease
from the later of the current expiry or `now + duration`.

Checkpoint sequence is strictly monotonic. The same checkpoint is written to the Attempt and
Job in one transaction. Completing or failing clears the lease token and releases only the
held quota class.

### 5.2 Rate limiting and requeue

Rate limiting is class-scoped:

```text
Attempt RUNNING/CHECKPOINTED
→ optional ordered checkpoint
→ Attempt RATE_LIMITED (terminal)
→ Job RATE_LIMITED
→ selected quota class RATE_LIMITED and still holding that Attempt
→ explicit JobRegistry.requeue_job()
→ hold and Job assignment clear; checkpoint survives; Job returns QUEUED
```

The affected class remains `RATE_LIMITED` until an explicit capacity update. A sibling class
under the same provider/account identity is not disabled. A retry creates a new Attempt with
a higher attempt number and, on a reused class, a higher fence generation.

### 5.3 Cancellation and lease loss

A queued Job can become `CANCELLED` directly. An active Job becomes `CANCEL_REQUESTED`; only
the holder of the current fence and lease may acknowledge it as cancelled. If that holder
disappears and the lease expires, reconciliation records a lost Attempt and a cancelled Job
rather than inventing success.

For ordinary expiry, `AttemptRegistry.reconcile_expired()` atomically:

- changes the expired active Attempt to `LOST`;
- clears its lease token and records a finish time;
- changes the Job to `LOST`;
- marks only the affected quota class `ERROR` while retaining the hold for inspection; and
- appends `ATTEMPT_LOST` as actor `reconciler`.

An explicit requeue then clears the terminal hold and assignment while preserving the Job
checkpoint. It does not silently make an `ERROR` capacity available; repair or a different
eligible class is required.

Restart recovery has a distinct, transactionally fenced path. `ExecutiveSupervisor` first
reconstructs active Attempts from SQLite and verifies the persisted PID, PGID, start identity,
and boot ID (or provider session where applicable). If the process is absent, it calls
`AttemptRegistry.adopt_attempt(attempt_id, expected_fence_generation, lease_owner)`, which
atomically increments both quota and Attempt fences and rotates the opaque token/owner. The
new holder may then call `mark_lost(..., verified_process_absent=True)` and explicitly requeue.
A still-live process is quarantined; it is never inferred successful from stale memory or a
result file.

## 6. Native Codex invocation

The Phase 1B adapter is a new Executive-only path. It does not call the portfolio-oriented
`brain.codex_bridge.reason()` and does not inherit its MCP or book semantics.

`CodexWorkerAdapter` exposes `start()`, `status()`, `cancel()`, `collect_result()`, and
`run_validation_argv()` around the explicit `LaunchSpec`, `BinaryAttestation`, `ProcessRef`,
`ArtifactReceipt`, `WorkerResult`, `CollectionReceipt`, `CancelReceipt`, and
`ValidationReceipt` contracts.

The native child is launched directly with argv—not `shell=True`—using the attested Codex
binary and this fail-closed command shape:

```text
codex exec
  --json
  --ephemeral
  --ignore-user-config
  --ignore-rules
  --strict-config
  --model <declared model>
  --color never
  -C <isolated no-remote clone>
  --output-schema <mastermind.executive_worker_result/v1 schema path>
  --output-last-message <supervisor-owned result path>
  -c model_reasoning_effort="<declared effort>"
  -c approval_policy="never"
  -c agents.enabled=false
  -c web_search="disabled"
  -c 'projects={"<canonical workspace>"={trust_level="untrusted"}}'
  -c project_doc_max_bytes=0
  -c project_doc_fallback_filenames=[]
  -c mcp_servers={}
  -c 'shell_environment_policy={inherit="none",ignore_default_excludes=false,include_only=[...],set={...}}'
  -c default_permissions="mastermind_exec_read|mastermind_exec_write"
  -c permissions.<profile>.extends=":read-only"
  -c permissions.<profile>.filesystem={<workspace read, exact writes, explicit denies>}
  -c permissions.<profile>.network.enabled=false
  --disable hooks
  --disable apps
  --disable plugins
  --disable plugin_sharing
  --disable browser_use
  --disable computer_use
  --disable image_generation
  --disable memories
  --disable multi_agent
  --disable remote_plugin
  <prompt from stdin>
```

The model invocation intentionally supplies no `--sandbox`: in Codex `0.147.0`, platform
defaults and sandbox/profile precedence can otherwise widen the custom boundary. The selected
custom profile extends built-in `:read-only`, grants explicit `<workspace>/**=read`, grants
write only to exact authorized artifact patterns when `WRITE_BRANCH` is present, denies
controller/runtime/auth/home-secret/production/Git and SQLite database/sidecar paths, and
disables network. It never
extends `:minimal`; native probes showed that `:minimal` allowed broad `/private/tmp` writes
through the macOS platform defaults and invalidated the superseded proof. The permission
profile and post-run Git/artifact validation are both required.

The canonical workspace is explicitly marked untrusted, which skips its project `.codex`
configuration layer. Project instructions are separately disabled with
`project_doc_max_bytes=0` and an empty fallback list; `mcp_servers={}` contributes no runtime
MCP entries but cannot erase managed/system entries, as noted in the limitations. Before
launch, the adapter requires the exact audited regular, non-symlink,
single-link, non-writable `.codex/config.toml` with SHA-256
`d7e836eb5a6cbd4cb4e97de41f8182add663cb2a152dc4e381f82553f571bb7f`; it rejects a root
`config.toml` and every ancestor `.codex/config.toml` layer.

The landed runtime persists binary and launch metadata but does not yet persist the complete
rendered argv or environment-key manifest. No prompt, credential, or lease token belongs in
argv; full non-secret launch attestation remains a Phase 1C requirement.

The subprocess environment is built from an empty dictionary and populated only with the
minimum reviewed execution/locale fields plus dedicated `HOME`, temporary directory, and
`CODEX_HOME`. The single inline `shell_environment_policy` atomically replaces the child
shell environment with the same exact allow-list/set table, so repository variables such as
`BOT_REASONING_LAYER` cannot leak through. It is never a filtered copy of `os.environ`. The workspace has no Git credential
or remote. The expected Codex provider-auth exposure must be stated honestly as the one
necessary credential channel; unrelated provider, Supabase, R2, Stripe, SSH, deploy, Macro,
portfolio, and service variables must be absent. The sealed report does not serialize a
complete environment-key manifest or secret-canary result; source construction and unit
tests therefore remain the evidence for this boundary, not a real-run absence attestation.

The prompt is supplied on stdin. Raw JSONL stdout/stderr, the final-message file, and the
schema-validated result are supervisor-owned artifacts. Logs are owner-only (`0600`) and
bounded by explicit caps. Collection requires a strict JSONL terminal lifecycle, local JSON
Schema validation, and canonical agreement between the structured terminal output and the
final-message file. Artifact paths must remain inside the workspace, cannot be symlinks, and
must match their declared size and hash. A read-only run must leave the Git tree unchanged.
A final agent sentence alone never completes a Job.

For `RUN_TESTS`, model telemetry is not completion authority. After accepted model output,
the supervisor invokes each persisted command through
`CodexWorkerAdapter.run_validation_argv(spec, argv)`. The adapter rejects shell executables,
launches the exact argv directly under `codex sandbox -P mastermind_exec_read`, uses an empty
environment with no `CODEX_HOME`, creates a separate process group, caps output, and persists
only argv, exit code, byte counts, SHA-256 hashes, timeout, and bounded error state in a
`ValidationReceipt`. Timeout/cancellation performs identity-checked whole-group cleanup.
Terminal completion requires these supervisor receipts, not a worker-reported exit code.

`start()` creates a new session/process group. `ProcessRef` records PID, PGID, macOS process
start identity, boot UUID, launch nonce, and binary attestation. `cancel()` and timeout handling
first verify that complete identity, send `TERM` to the process group, and escalate to `KILL`
only after a bounded grace period. No operation signals an unverified raw PID.

**Sealed proof — invocation attestation**

- Absolute binary:
  `/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex`;
  version `0.147.0`; 219,997,536 bytes; SHA-256
  `19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37`;
  signing team `2DC432GLL2`; effective UID `501`.
- The effective command was the profile-only `codex exec` shape above: no legacy
  `--sandbox`, custom `default_permissions`, `--strict-config`, the workspace explicitly
  untrusted, project docs/MCP disabled, atomic empty-built shell policy, stdin prompt, network off,
  and agents, web, hooks, apps, plugins, plugin sharing, browser/computer use, image
  generation, memories, multi-agent, and remote plugins disabled. The report persists the
  binary/launch attestation but not the complete rendered argv or environment-key allow-list;
  those are explicitly deferred to Phase 1C.
- The prompt reconstructed from the sealed Job/Attempt packet and landed `_prompt()` is 2,022
  bytes, SHA-256
  `b15ed2c5d759e0499e1584d99f9b1bd1161d88b754d526a0b256409e3e56b5c1`; this is a
  reconstruction, not a serialized prompt artifact.
- Provider session: `019ff27e-c9c3-7570-8f7f-710c9756d016`; launch nonce
  `a93523d8848b44f7a7d287dd06748c3b`.
- JSONL stdout:
  `runs/ATT-d8947b722aff4e36924ebc6323bd70a8/logs/stdout.jsonl`; 1,666 bytes;
  SHA-256 `1f18aac1cc23e4dce9907350985a3850593dbbcbe69afe6d308b1b7f075be427`.
- Stderr: `runs/ATT-d8947b722aff4e36924ebc6323bd70a8/logs/stderr.log`; zero bytes;
  SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Final-message/result:
  `runs/ATT-d8947b722aff4e36924ebc6323bd70a8/output/result.json`; 770 bytes;
  SHA-256 `a75a5e9505bb83db5ae52be3f530bcd523f99539f6550f3b8cc08df912933ae0`.

## 7. Workspace and process isolation

`prepare_credentialless_clone()` is supervisor-owned and performs these checks before the
worker starts:

1. validates the Job ID before deriving a destination name;
2. resolves the exact immutable base commit in the source repository;
3. creates a local clone with `--no-hardlinks` rather than a linked worktree;
4. checks out the exact SHA detached, then creates one validated task branch;
5. removes every remote;
6. uses a fresh supervisor Git home with global/system config and prompting disabled;
7. confirms the clone is clean, at the requested SHA, has zero remotes, and owns a private
   `.git` directory; and
8. refuses an existing destination instead of cleaning or overwriting it.

The worker receives the absolute clone path and only the declared relative write path:

```text
research/executive_os_phase1b_worker_proof/receipt.md
```

After Codex exits, the supervisor must inspect the full Git diff. An unexpected path,
symlink escape, submodule change, Git metadata mutation, or undeclared generated file rejects
the result even if the model reports success.

The worker runs in a new process group/session. Before signal delivery, the supervisor must
match the stored PID, PGID, and process-start identity to the live process. Cancellation and
the fault proof target the verified process group and remove same-PGID descendants. The
signal operation is never based on an unverified PID alone; deliberate session-detachment is
listed as a remaining Phase 1C boundary below.

This local proof target is concurrency isolation, not yet the Phase 0 hostile-code boundary.
The host has no `mastermind-worker` account, and the current supervisor defaults to its own
effective user. It does not claim a distinct OS principal, container, transient systemd unit,
mount namespace, or kernel-level denial of the supervisor database. The Codex permission
profile is an application-level boundary, not an OS-user boundary. Those remain Phase 1C
requirements.

**Sealed proof — workspace/process receipts**

- Source repository:
  `/Users/chriswong/Documents/Cluade/Mastermind-executive-os-phase1b-a515a714`; exact base
  `ab9269d12803f0160cc7dc0711ebc1452f4d6707`.
- Success workspace:
  `/private/tmp/mastermind-phase1b-sealed-proof.ToWh0D/workspaces/success`; branch
  `codex/phase1b-real-proof`; remote count `0`; private `.git` receipt `true`.
- Kill workspace: `/private/tmp/mastermind-phase1b-sealed-proof.ToWh0D/workspaces/kill`;
  branch `codex/phase1b-kill-proof`; remote count `0`; private `.git` receipt `true`.
- `prepare_credentialless_clone()` enforced clean-before launch, although that Boolean is not
  a field in the sealed report. The accepted Git manifest retained exact head/base
  `ab9269d12803f0160cc7dc0711ebc1452f4d6707` and exactly one changed path,
  `research/executive_os_phase1b_worker_proof/receipt.md`; status SHA-256
  `7b8205b3f88350c03503f49d52b7b5eb2127547175a134c020a583792964f86d`.
- Success identity: PID/PGID `77724`, start identity `1786479823.109682`, boot session
  `ECD82A73-0F92-4B7D-937E-A35992EFE579`. Kill identity: PID/PGID `78610`, start identity
  `1786479848.508040`, same boot session. Independent post-proof `ps` checks found both PIDs
  absent.

## 8. Executable authority

Portfolio A0–A7 remains an inert effect classification on the Job. Executive worker
capabilities are a separate pre-action grant enforced by
`ExecutiveAuthorityPolicy.load().authorize()`.

Phase 1B code accepts exactly:

```text
READ
RESEARCH
WRITE_BRANCH
RUN_TESTS
```

YAML alone cannot expand that set because `PHASE1B_ALLOWED` is code-pinned. The checked-in
policy must deny, at minimum:

```text
OPEN_PR
MERGE
DEPLOY
SERVICE_CONTROL
CAPITAL_EXECUTION
BILLING
CREDENTIAL_ADMIN
```

The reviewed YAML also denies push, cross-repository publication, paper-state mutation, and
data deletion. Unknown, missing, malformed, overlapping, or drifted policy fails closed.

`WRITE_BRANCH` requires one absolute assigned workspace and at least one safe declared
relative write path. `RUN_TESTS` requires non-empty argv lists; shell command strings are
invalid. Supplying either scope without its capability also fails closed.

The decision records the exact policy-file SHA-256 and schema version. The execution path
must authorize before durable Job creation and again immediately before claim/launch so a
stale earlier decision cannot survive policy drift.

**Sealed proof — authority attestation**

- Policy path `config/authority_map.yml`; launch SHA-256
  `04801ab178062400d1d422c4952f632379ffecfa7911c1399bca8f4b32ad571c`.
- Requested capabilities: `READ`, `RESEARCH`, `RUN_TESTS`, `WRITE_BRANCH`; authorized
  workspace `/private/tmp/mastermind-phase1b-sealed-proof.ToWh0D/workspaces/success`; sole
  write path `research/executive_os_phase1b_worker_proof/receipt.md`.
- Persisted validation argv:
  `[/usr/bin/python3, -c, "from pathlib import Path; p=Path('research/executive_os_phase1b_worker_proof/receipt.md'); t=p.read_text(encoding='utf-8'); assert t.startswith('# Phase 1B Worker Proof'); assert 'Job:' in t and 'Run:' in t and 'Base SHA:' in t"]`.
- Job, Attempt, and launch metadata all contain the same policy hash above, proving the
  create/claim/launch match. The focused authority suite passed the exact allow-set,
  mandatory-deny, unknown/empty, missing/malformed, overlap, schema-drift, allow-drift,
  deny-drift, and scope-drift fail-closed cases.

## 9. Real-worker proof protocol

The success proof was run after the focused suite was green. Repository CI remains a
separate delivery gate because the full local suite could not collect in this environment.

### 9.1 Success path

1. Create a fresh proof root and SQLite database.
2. Load and hash the reviewed authority policy.
3. Register exactly one logical `codex-01` capacity with the required provider/model/effort,
   `WRITE_BRANCH`, and `RUN_TESTS` capabilities.
4. Create the bounded Job with an exact base SHA, absolute workspace, one allowed write path,
   one declared Python argv, and a finite attempt limit.
5. Claim it transactionally and persist the fence/lease state.
6. Prepare the exact-SHA credential-free clone and persist its receipt before launch.
7. Launch the attested native Codex process with the strict invocation in section 6.
8. Heartbeat while it runs; persist an ordered checkpoint before terminal completion.
9. After model exit, have the supervisor run exactly the persisted validation argv without a
   shell and persist the resulting `ValidationReceipt`.
10. Validate the result schema, changed-path allow-list, receipt contents, artifact size/hash,
    validation receipt, base SHA, and policy hash.
11. Commit `COMPLETED` Attempt/Job/Event state transactionally and release only the selected
    capacity.
12. Reopen the runtime from SQLite and reconstruct the same terminal state without terminal
    scrollback or in-memory process objects.

**Sealed proof — real Codex transcript**

```text
20:23:42Z  JOB-001 created QUEUED and ATT-d8947b722aff4e36924ebc6323bd70a8 claimed
20:23:43Z  native ProcessRef recorded, then Attempt changed CLAIMED -> RUNNING
20:24:01Z  model exit 0 persisted; collection accepted SUCCEEDED; provider validations=[]
20:24:08Z  supervisor validation exited 0; checkpoint 1 persisted; Job/Attempt COMPLETED
fresh reopen reconstructed COMPLETED/COMPLETED and codex-01/codex-native AVAILABLE
```

- Job `JOB-001`; Attempt `ATT-d8947b722aff4e36924ebc6323bd70a8`, number `1`; worker
  `codex-01`; quota class `codex-native`; fence generation `1`.
- Model/provider/cost receipt: `gpt-5.6-sol`, effort `xhigh`, provider `codex`, cost class
  `proof`; provider session `019ff27e-c9c3-7570-8f7f-710c9756d016`; model exit `0`.
- Checkpoint sequence `1`; canonical 576-byte checkpoint SHA-256
  `b8f9000770511e78331abb36bb23b5e89079bda8a04873d75732a17ec41aa836`.
- Artifact
  `/private/tmp/mastermind-phase1b-sealed-proof.ToWh0D/workspaces/success/research/executive_os_phase1b_worker_proof/receipt.md`;
  190 bytes; SHA-256
  `aa7de96b867581ab96595cce7aaae6a7bf3014ed5b6c9cb9af0c6a26566c0547`.
- The supervisor executed the persisted Python argv shown in section 8 directly, without a
  shell. Exit code `0`; timed out `false`; error `null`; stdout zero bytes with SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; stderr 1,112
  bytes with SHA-256
  `964169b24d0aa13ec13e816c6db8b054e311808866617f58924e7ea1ef8693a9`. The receipt file
  SHA-256 is `51c51de289ec63b11a28f71ba186decaa002d32014faa313f37efbedee9b5b98`.
- Final Job/Attempt statuses: `COMPLETED` / `COMPLETED`. Events `2`–`9` record
  `JOB_CREATED`, `JOB_CLAIMED`, `ATTEMPT_PROCESS_RECORDED`, `ATTEMPT_RUNNING`, one
  heartbeat, `ATTEMPT_PROCESS_EXITED`, `JOB_CHECKPOINTED`, and `JOB_COMPLETED`.
- Fresh SQLite reopen reconstructed the same Job and Attempt as `COMPLETED`. The captured
  post-success quota projection was `AVAILABLE`, with no active Job or Attempt and fence
  generation `1`.

### 9.2 Kill/restart path

The fault proof uses a second harmless Job and must not target the success Attempt.

1. Create and claim the second Job; persist a checkpoint.
2. Launch its process in a new process group and persist verified PID, PGID, process-start
   identity, Attempt ID, fence, and lease expiry.
3. Re-read the live process identity and prove it matches the persisted receipt.
4. Kill the verified process group. Do not signal a bare or mismatched PID.
5. Construct a new runtime/supervisor instance using only the SQLite path and durable artifact
   roots; discard the original in-memory objects.
6. Verify the persisted process identity is absent, call `adopt_attempt()` with the expected
   fence, and prove the adoption CAS increments the fence and rotates the opaque lease.
7. Call `mark_lost(..., verified_process_absent=True)`; verify Attempt `LOST`, Job `LOST`,
   lease token cleared, affected class `ERROR`, checkpoint unchanged, and one immutable
   `ATTEMPT_LOST` event. `reconcile_expired()` remains the separate fallback for actual expiry.
8. Call `JobRegistry.requeue_job()` and verify the Job returns to `QUEUED`, its checkpoint is
   preserved, assignment/current Attempt clear, and the terminal Attempt row is unchanged.
9. Do not make the errored class available implicitly. Any retry must use an explicitly
   repaired or different eligible capacity and create a new Attempt/fence.

**Sealed proof — kill/restart receipts**

```text
20:24:08Z  JOB-002 created and ATT-2d55e286357741e984690c90d14fd20b claimed, fence 2
20:24:08Z  ProcessRef recorded; Attempt CLAIMED -> RUNNING; checkpoint 1 persisted
             verified PGID 78610 killed; collection observed exit -9 and FAILED
20:24:08Z  fresh supervisor adopted fence 2 -> 3 after process-absence verification
20:24:08Z  Attempt LOST, Job LOST, then explicit requeue -> Job QUEUED
```

- Second Job `JOB-002`; Attempt `ATT-2d55e286357741e984690c90d14fd20b`, number `1`.
  The checkpoint's canonical 208-byte JSON hashes to
  `b77721c5ebc2cbe018afe921a95c4c134fbf7a20a9e3c9ed96cef59abb1ec6bf` and remained at
  sequence `1` through adoption, loss, reopen, and requeue.
- Verified process identity: PID/PGID `78610`, start identity `1786479848.508040`, boot
  session `ECD82A73-0F92-4B7D-937E-A35992EFE579`. The harmless child was killed as a
  verified process group; collection recorded exit `-9`, status `FAILED`, and empty stdout
  and stderr, each SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. No provider
  session started (`thread_started_observed=false`), and a post-proof `ps` check found the PID
  absent.
- Claim event `11` allocated fence `2`. Adoption event `15` changed fence `2` to `3`, owner
  `phase1b-proof-before-restart` to `phase1b-proof-after-restart`, and lease expiry to
  `2026-08-11T20:25:08.931Z`. Reconciliation ran at `2026-08-11T20:24:08Z`, after verified
  absence rather than lease expiry; its receipt is `process_was_live=false`,
  `status=REQUEUED`, `requeued=true`.
- Event `16`, `ATTEMPT_LOST`, records reason
  `process identity absent during supervisor restart` and
  `verified_process_absent=true`. The terminal Attempt is `LOST`, fence `3`, lease token
  cleared. Event `17`, `JOB_REQUEUED`, leaves the Job `QUEUED` with no assignment or current
  Attempt while preserving the checkpoint and immutable old Attempt.
- The affected `codex-01/codex-native` class ends `ERROR`, with no held Attempt and fence
  counter `3`; it was not made available implicitly. The sealed database contains 17 events,
  passes `integrity_check`, and has no foreign-key violations.

## 10. Verification and delivery evidence

Mocked/unit tests establish deterministic contracts; they do not replace the two manual
proofs above. Automated adapter tests must use a fake child and must not spend provider quota
or launch a real model. The separately recorded operator proof is the only evidence that the
native Codex path actually ran. Record both focused and exact repository-CI commands.

**Local test evidence**

- Focused command:
  `python3 -m pytest -q tests/test_executive_os_runtime.py tests/test_executive_os_sqlite.py tests/test_executive_authority.py tests/test_executive_workspace.py tests/test_executive_codex_worker.py tests/test_executive_supervisor.py`.
- Result: 127 collected; 126 passed and 1 skipped
  (`17 + 19 + 43 + 3 + 33 + 12` collected); exit 0. The skipped adapter case is the
  opt-in native sandbox test because `MASTERMIND_CODEX_SANDBOX_BINARY` was unset. Separate
  native probes with the binary configured allowed read/exact-file creation and denied an
  unauthorized sibling write, controller database access, and auth-path access.
- The exact local hermetic-governance selection from `.github/workflows/ci.yml` also passed:
  208 collected, 206 passed, and 2 skipped. The Portfolio v2 selection was separately
  collection-blocked in the ambient Python by missing `claude_agent_sdk`; the hosted job
  installs `.[dev]` before running that gate.
- Whole-suite local command `python3 -m pytest -q`: **NOT GREEN IN THIS LOCAL
  ENVIRONMENT**. Collection stopped with six errors because `claude_agent_sdk` and
  `reportlab` were not installed. This is not represented as a Phase 1B regression or a CI
  pass; exact GitHub CI remains **NOT YET RUN**.
- `python3 -m compileall -q app bot brain bridge control_plane data_layer loop portfolio scripts`:
  passed.
- `find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n`: passed.
- Final `git diff --check` and scoped changed-file list are the last local freeze checks; their
  result is recorded in the task handoff rather than pre-claimed here.

The repository delivery contract still applies to tracked code: task branch, scoped commit,
PR to `master`, required strict `test` check, squash merge, exact merged `origin/master` SHA,
and health verification after exact-SHA deployment unless the user explicitly overrides the
deployment step.

Deployment evidence is evidence that inert code reached the release, not that an Executive
worker is scheduled or continuously running.

**GitHub and deployment — NOT YET RUN**

- Local task branch: `codex/executive-os-phase1b-a515a714`.
- Scoped commit SHA: **NOT YET RUN**.
- PR URL/number: **NOT YET RUN**.
- Required `test` check URL/result: **NOT YET RUN**.
- Squash merge SHA: **NOT YET RUN**.
- `origin/master` ancestry receipt: **NOT YET RUN**.
- Deployed SHA: **NOT YET RUN**.
- `/health` exact-SHA/HTTP receipt: **NOT YET RUN**.
- Source review finds no scheduler/app registration; post-deploy inert-runtime verification:
  **NOT YET RUN**.

## 11. Known limitations

Even after both proof transcripts pass, Phase 1B remains intentionally narrow:

- one host and one SQLite writer domain; no multi-host consensus or PostgreSQL failover;
- one manually triggered Codex adapter; no Claude adapter or provider-capacity integration;
- automated tests use fake child processes; the sealed local proof establishes one native
  Codex completion, not repeatability or production-host behavior;
- no persistent supervisor, boot recovery loop, scheduler, API, UI, or alerting;
- no distinct non-root worker identity, container, transient unit, mount namespace, or seccomp
  profile yet;
- the sealed proof used the operator's manually authenticated Codex home and a user-owned
  Homebrew native binary; a separately provisioned worker account, root-owned binary copy,
  and worker-only Codex home remain Phase 1C work;
- no persisted complete rendered-argv/environment-key receipt or real-run secret canary;
- the acceptance controller has not yet been committed at an exact Phase 1B source SHA;
- the worker necessarily receives its dedicated Codex provider authentication, although no
  unrelated credential should cross;
- the custom Codex permission profile plus changed-path validation is a bounded proof, not a
  complete hostile-filesystem boundary;
- `mcp_servers={}` does not erase lower-precedence managed/system MCP tables in Codex 0.147.0.
  This host had no `/etc/codex` managed files, project layers were disabled, user config was
  ignored, and the proof emitted no MCP calls, but the sealed report does not contain a
  portable effective-MCP-empty attestation;
- no Objective, Fable plan, dependency DAG, approval, experiment, or content-addressed
  artifact catalog vertical slice yet;
- adapter/supervisor loops enforce bounded timeout/cancellation and process-group cleanup, but
  there is no persistent daemon to drive them after an operator process disappears;
- same-PGID descendants are terminated, but a hostile child that creates a new session can
  escape PGID cleanup; cancellation during the pre-`ProcessRef` stdin-delivery window and a
  hard supervisor death during direct validation also lack durable child reconciliation;
- no automatic retry: requeue is explicit, attempt-limited, and creates a new attempt;
- no backup, restore drill, retention policy, database replication, or WAL monitoring;
- no automatic recovery of an `ERROR` or `RATE_LIMITED` capacity;
- no interactive `send()`/resume semantics; each worker process is ephemeral;
- no push, PR, merge, deployment, service control, portfolio write, data deletion, billing,
  credential administration, or capital authority; and
- no migration of Phase 1A scratch JSON or any legacy/domain state.

## 12. Phase 1C

The exact next move is **not scheduler or application wiring**. Phase 1C must first run the
supervisor and worker as separate OS principals, place the worker behind a real OS/container
filesystem boundary, and preserve the Phase 1B supervisor-owned direct-argv validation broker
as the only validation completion authority. It must also persist the complete redacted Codex
argv, environment-key allow-list, permission profile, prompt hash, binary attestation, and
secret-canary result before changing `CLAIMED` to `RUNNING`. The acceptance proof must then be
rerun from a clean, committed exact Phase 1B SHA under that distinct-UID boundary.

After that gate, Phase 1C should harden and connect the slice without widening authority by
narrative:

1. Run a small Executive control supervisor as a dedicated non-root principal on the
   canonical runtime-data mount.
2. Launch workers under a distinct restricted identity or container/transient unit with
   explicit read/write paths, process-group ownership, resource ceilings, and no access to
   the control database or administrative Git metadata.
3. Persist and reconcile full `ProcessRef` identity at startup; add timeout/cancellation and
   descendant termination monitors.
4. Add tested database backup/restore, WAL health, corruption handling, artifact retention,
   and operational alerts for stale workers, expired leases, LOST attempts, blocked Jobs,
   invalid results, and pending cancellation.
5. Add the Claude adapter behind the same result, authority, workspace, process, and
   environment contracts; integrate named provider quota classes from Macro's existing
   shared capacity ledger without creating a credential island.
6. Add Objective, immutable plan artifact, dependency/DAG, approval/decision, artifact, and
   current-company-state projections required for the Sol/Fable vertical slice.
7. Broker Git stage/commit/push/PR as separately authorized supervisor effects. Keep merge
   and deploy denied to ordinary workers.
8. Add a read-only local control/status API only after authenticated actor identity and
   runtime policy checks exist.
9. Keep scheduler and application integration dark until restart, cancellation, isolation,
   and recovery acceptance tests pass on the intended host.

Automatic merge/deploy, portfolio mutation, self-tuning, Macro/Prophet/Neural Web writes,
billing, deletion, credential administration, and capital execution remain outside Phase 1C
unless separately designed, reviewed, and explicitly authorized.
