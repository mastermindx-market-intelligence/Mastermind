# Mastermind Executive OS — Phase 1C-A Secure Supervisor

**Status (2026-08-11): implementation and deterministic verification are
complete; real-host acceptance is BLOCKED.** This workstation session is UID
501 and cannot perform the required one-time root bootstrap without an
interactive administrator credential. The dedicated `_mastermind_exec` and
`_mastermind_worker` accounts, system LaunchDaemons, protected runtime roots,
and launchd acceptance receipts therefore do not exist yet. No successful
launchd-supervised Codex, interrupted/requeue, canary, or recovery receipt is
claimed in this document.

Phase 1C-A is not complete, merged, deployed, or live until the acceptance
procedure in section 11 passes from the exact `origin/master` merge SHA and the
receipt inventory in section 12 is replaced with observed values.

## 1. Bounded outcome

This slice extends the Phase 1B durable runtime; it does not create a second
queue, scheduler, application integration, or remote control plane.

```text
system launchd
  ├─ control LaunchDaemon (_mastermind_exec)
  │    ├─ root-owned exact-SHA release + policy
  │    ├─ private SQLite/WAL + receipts + backups
  │    ├─ launchd-activated AF_UNIX operator socket
  │    └─ typed requests to the worker broker
  └─ worker LaunchDaemon (_mastermind_worker)
       ├─ dedicated CODEX_HOME
       ├─ launchd-activated AF_UNIX broker socket
       ├─ one active Codex process at a time
       └─ whole-UID residual sweep after cancel/restart/collection
```

The intended success path is:

```text
launchd starts both services
→ control opens and verifies durable SQLite state
→ control remains AWAITING_CANARY until the live-PID boundary proof passes
→ operator explicitly creates and dispatches the fixed harmless proof Job
→ authority is rechecked at creation and claim
→ control prepares a credentialless exact-SHA workspace
→ worker broker validates the typed LaunchSpec and distinct principal
→ complete redacted launch attestation is persisted
→ ATTEMPT_PROCESS_RECORDED is durable before ATTEMPT_RUNNING
→ Codex writes only the declared proof receipt
→ supervisor executes the persisted validation argv itself
→ result, checkpoint, logs, validation, and terminal UID sweep persist
→ control seals workspace/run child roots to control-owned 0700
→ the assignment-seal receipt is durable before the terminal state
→ service restart reconstructs the same state without terminal history
```

The intended interruption path is:

```text
active worker process
→ identity-checked cancel or control restart
→ broker terminates the process group
→ dedicated worker UID sweep catches setsid/detached descendants
→ control-owned reconciliation receipt proves the terminal sweep
→ workspace/run child roots are sealed to control-owned 0700
→ Attempt and Job become LOST, never successful from file presence
→ checkpoint remains durable
→ explicit operator requeue archives the sealed workspace and creates a
  fresh worker-accessible exact-SHA workspace, Attempt, and fence
```

## 2. Non-goals and inertness

Phase 1C-A does not add or activate:

- Claude, Fable, remote MCP, a CEO API, or multi-account routing;
- FastAPI, APScheduler, financial-job, or portfolio-loop registration;
- arbitrary shell/argv RPC;
- push, PR, merge, deploy, billing, credential administration, deletion,
  portfolio mutation, or capital authority;
- a TCP listener, public API, browser UI, or interactive-session dependency; or
- automatic queue polling. A Job runs only after the bounded `dispatch JOB`
  operator command.

Importing or deploying the modules is inert. Host effects require the explicit
root bootstrap/install commands and explicit service start.

## 3. Host and principal contract

Target assumptions:

- dedicated always-on Apple-silicon macOS host with system `launchd`;
- internal APFS storage with ownership enforcement (not an external `noowners`
  volume and not an interactive user Documents/Desktop path subject to TCC);
- a clean checkout whose `HEAD` and `origin/master` both equal the requested
  40-hex merge SHA;
- a pre-provisioned, root-owned, signed, non-group-writable Python 3.12
  standard-library runtime, executed with `-I -S -B`;
- the reviewed root-owned native Codex binary copy, pinned version, SHA-256,
  valid signature, and OpenAI Team ID `2DC432GLL2`;
- one dedicated provider authentication file, owned only by the worker; and
- one serialized worker identity and no other process using that UID.

The reviewed default identities are:

| Principal | UID/GID | Owns | Must not own/read |
|---|---:|---|---|
| root installer only | 0/0 | release, Python trust root, native Codex copy, launchd plists, secret injection file | never runs a Codex Job |
| `_mastermind_exec` | 450/450 | DB, policy/admin clone, control home, receipts, backups, operator service | worker provider auth |
| `_mastermind_worker` | 451/451 | dedicated CODEX_HOME and worker broker state; current assigned workspace/run write surface | DB, control environment, other homes, production credentials, unrelated Git metadata |
| `_mastermind_ops` | GID 453 | permission to reach the bounded operator socket | no direct DB or worker-broker access |

Both service accounts have disabled passwords/authentication, hidden records,
`/usr/bin/false` shells, pinned homes, and checked group membership. The worker
LaunchDaemon sets `InitGroups=false`; it receives no supplementary groups. The
control account may join the worker primary group so it can collect the current
run's artifacts.

Bootstrap, install preflight, and acceptance census every local account and
group record rather than trusting only named memberships. Duplicate UID/GID
owners, hidden `PrimaryGroupID` membership, UUID-only `GroupMembers`, or nested
membership in protected groups fail closed. The release manifest likewise
records and rechecks root:wheel ownership, type, mode, content hash, ACL absence,
and non-symlink identity for every installed object.

Root is an installer, not a resident executor. The two persistent services run
as distinct non-root UIDs. The worker broker accepts only the kernel-reported
control UID through `getpeereid`; it rejects its own worker UID even if that UID
can obtain a socket descriptor.

## 4. Filesystem map

```text
/Library/Application Support/MastermindExecutive/       root:wheel 0755
  bin/codex-<version>                                    root:wheel 0555
  config/control.json                                   root:_mastermind_exec 0440
  config/worker-codex.json                              root:_mastermind_worker 0440
  config/control-env-canary                             root:_mastermind_exec 0440
  releases/<exact-sha>/                                 root:wheel, no go-write
    .executive-release-manifest.json                    root:wheel 0444

/var/db/mastermind-executive/                            root:wheel 0711
  control/                                               _mastermind_exec 0700
    db/                                                  _mastermind_exec 0700
    admin-checkout/<exact-sha>/                          _mastermind_exec 0700
    launch-receipts/                                     _mastermind_exec 0700
    backups/                                             _mastermind_exec 0700
    canaries/                                            _mastermind_exec 0700
  jobs/workspaces/                                       control:worker 0710
  jobs/runs/                                             control:worker 0710
  workers/codex-01/provider-home/                        worker:worker 0700
  workers/codex-01/state/                                worker:worker 0700

/var/run/mastermind-executive/
  control.sock                                           launchd, control:ops 0660
  worker.sock                                            launchd, control:control 0600

/var/log/mastermind-executive/
  control/                                               control:control 0700
  worker/                                                worker:worker 0700
```

Assignment roots remain traversable but non-listable to the worker. Before a
launch, the control principal enumerates their direct children and freezes the
current workspace/run plus all sibling denials into a canonical manifest and
SHA-256. The typed LaunchSpec carries the explicit sibling denial paths and
manifest digest; the worker never enumerates the roots. The service permits
only one active dispatch, so no new sibling can appear during a live Job. The
complete service rejects secure workspace/run roots under `/Users`, and the
Codex profile denies `/Users/**` plus unrelated homes, Git metadata, credentials,
DBs, and prior workspace/run siblings. A narrower compatibility path is retained
only for isolated adapter development without the complete Phase 1C-A manifest;
it is not an acceptable host configuration. Native host acceptance must prove
one assigned-path positive and unrelated `.env`, `.git`, and prior-workspace
negatives without reading secret contents.

Immediately before every durable terminal transition—success, failure,
cancellation, LOST, or expiry—the supervisor requires the final whole-UID sweep,
changes the current workspace and run child roots to control-owned `0700`, fsyncs
them, and writes a control-owned `0600` assignment-seal receipt. Seal failure
leaves the attempt nonterminal and quarantines dispatch. Acceptance derives the
known paths from durable Job/Attempt rows and, as the raw worker UID outside
Codex, requires `EACCES` for open, stat-through-child, and list operations.
Explicit requeue accepts only a sealed old workspace, archives it at `0700`, and
materializes a fresh exact-SHA shared workspace for the new attempt.

## 5. launchd and service lifecycle

The checked-in system LaunchDaemon templates use:

- `RunAtLoad=true`, `KeepAlive=true`, `ProcessType=Background`;
- `Umask=0077`, `ThrottleInterval=10`, `ExitTimeOut=15`;
- `AbandonProcessGroup=false` and bounded core/file-size limits;
- absolute, fixed argv with Python isolation flags;
- launchd socket activation for two pathname Unix stream sockets; and
- no TCP socket declaration.

Installation completes all read-only trust checks before mutation, then
disables and boots out both existing services and verifies both launchd labels
are absent. An exit trap keeps them stopped if replacement fails; no partially
replaced release is allowed to continue running.

The control service opens the existing Phase 1B SQLite runtime, runs the
append-only migration check, checks WAL/integrity/foreign keys, takes a private
service lock, writes a private running marker, and reconciles active attempts
with `requeue_lost=False`. LOST work is never auto-requeued.

On every new control PID, the service starts in `AWAITING_CANARY`. In that
quarantine it exposes only `status` and `health`; it cannot reconcile, register,
create, dispatch, requeue, or back up work. A root/control-only wrapper reads a
sentinel file after launchd has dropped privileges, injects it in the service's
initial `execve` environment, and writes a positive live-process attestation.
The launchd plist never contains the value. The worker-principal probe checks
`launchctl print`, `ps eww`, and Darwin `KERN_PROCARGS2` against that exact PID
and value commitment. The composite receipt binds the current PID/start/boot,
worker UID/GID, config/release/Python digests, probe statuses, protected-path
denials, and dedicated-auth exception. A same-PID `SIGHUP` validates the fresh
receipt and moves the service to `READY`; a restart creates a new PID and must
repeat the proof.

Lifecycle commands are deliberately fixed:

```bash
/bin/bash ops/executive_os/service-control.sh start
/bin/bash ops/executive_os/service-control.sh stop
/bin/bash ops/executive_os/service-control.sh restart
/bin/bash ops/executive_os/service-control.sh status
```

## 6. Bounded operator interface

The operator client sends one bounded JSON frame over AF_UNIX. Kernel peer UID
is checked before dispatch. Supported commands are:

```text
status
health
workers
jobs
job JOB
attempt ATTEMPT
register-worker
create-proof-job
dispatch JOB
cancel JOB
reconcile
requeue JOB
backup
verify-backup NAME.sqlite3
```

The mutating restore command is offline-only and is rejected while the service
marker/lock is live:

```text
restore-backup --config /absolute/control.json NAME.sqlite3
```

`restore-verify --config /absolute/control.json NAME.sqlite3` is a non-mutating
isolated restore drill and may be run while the service is live.

There is no request field for a shell, arbitrary executable, arbitrary prompt,
arbitrary workspace, arbitrary backup path, or arbitrary authority.

## 7. Authority

The executable grant remains exactly:

```text
READ
RESEARCH
WRITE_BRANCH inside the assigned workspace and declared artifact paths
RUN_TESTS through supervisor-owned persisted argv only
```

The mandatory denies remain:

```text
PUSH_BRANCH OPEN_PR MERGE DEPLOY SERVICE_CONTROL CROSS_REPO_PUBLISH
BILLING CREDENTIAL_ADMIN DATA_DELETE PAPER_STATE_MUTATION CAPITAL_EXECUTION
```

`config/authority_map.yml` is reviewed input, while code pins the exact allow
set and required deny set. Adding YAML alone cannot expand authority. The same
policy and scoped-path/argv decision is revalidated before Job creation, claim,
launch, and result acceptance. A policy hash change after claim rejects the
result. Provider-authenticated model output cannot self-attest tests; its
`validations` array must be empty and the supervisor executes the persisted
argv directly.

## 8. Launch attestation

Before an Attempt may enter `RUNNING`, SQLite durably records
`mastermind.executive_launch_attestation/v1` inside
`attempts.launch_metadata_json` and a control-owned private receipt. The
attestation contains only redacted/hash/identity fields:

| Field | Meaning |
|---|---|
| `executable_path`, `binary` | exact native path, version, SHA-256, signer/team, stat identity |
| `rendered_argv` | exact argv with prompt/secret-bearing values redacted |
| `environment_keys` | allow-listed key names only, never values |
| `permission_profile_sha256` | canonical sandbox, network-off, disabled-feature, and isolation-manifest commitment |
| `prompt_sha256` | hash only; no raw prompt in the receipt |
| `expected_base_sha`, `observed_base_sha` | exact detached Git identity |
| `workspace_identity` | canonical path plus device/inode/mode/owner and Git HEAD |
| `worker_identity` | requested account and observed real/effective UID/GID |
| `provider_home_identity` | canonical path and filesystem identity, no auth data |
| `secret_canary_verdict` | strict passing receipt and dedicated-auth exception |
| `launch_nonce` | one attempt-scoped unpredictable nonce |
| `process_identity` | PID, PGID, SID, process-start identity, boot ID, real/effective IDs |

The runtime enforces the event order:

```text
ATTEMPT_PROCESS_RECORDED
ATTEMPT_RUNNING
```

No raw credential, environment value, provider-auth bytes, lease token, or raw
secret is permitted in public projections, events, logs, results, artifact
manifests, launch receipts, backup manifests, or acceptance summaries.

## 9. Process supervision and detached descendants

The Codex child starts in its own session/process group. Normal cancellation
uses the persisted PID/PGID/start/boot identity, TERM grace, then KILL. A result
file never proves success; collection, identity, schema, Git/artifact scope,
supervisor validation, process exit, and a terminal UID sweep all must agree.

`launchd`'s process-group cleanup cannot catch a deliberate `setsid()` child.
For the one-worker Phase 1C-A proof, the worker UID is dedicated and serialized.
The non-root broker can use Darwin `kill(-1, signal)` to reach every process with
its own UID except itself. On broker startup and after cancel/collection/restart
it repeatedly enumerates and terminates every other same-UID process until only
the broker remains. Ambiguous identity or residual state fails/quarantines the
attempt. The control service copies and hashes the passing sweep into its own
reconciliation/launch receipt; worker-owned mutable state is not acceptance
authority.

That passing sweep is also a prerequisite for the control-owned terminal seal.
Both assignment child roots must have the same stable filesystem identity and
be control-owned `0700` before the terminal SQLite transition is permitted.
The acceptance proof uses the raw worker principal—not the Codex profile—to
demonstrate that known completed/LOST workspace and run paths return `EACCES`.

This closes detached descendants only for one exclusive UID and one concurrent
attempt. It is not a claim that an application-level Codex profile alone is a
hostile-code security boundary.

## 10. Backup and recovery

Online backup uses `sqlite3.Connection.backup`, so committed WAL state is
included. The destination directory is private; DB and strict manifest are
`0600`. Verification checks SHA-256/size, schema version, exact migration
name/checksum sequence, SQLite integrity, and foreign keys. The manifest holds
only digests/metadata, never database rows or secrets.

Restore is offline and guarded by both the running marker and a nonblocking
exclusive lock. It verifies and drills the source before touching live state,
copies the current main/WAL/SHM/journal set to a timestamped rollback set,
stages on the same filesystem, atomically replaces, fsyncs, reopens, and
re-verifies. Any failure after sidecar removal or replacement restores and
verifies the prior bytes. The rollback set is retained after success until an
operator deliberately archives it outside this workflow.

## 11. Exact host commands

These commands are the reviewed procedure, not evidence that they ran. Replace
the three absolute prerequisites with host-specific values. The source checkout
must be clean and its `HEAD` and `origin/master` must equal `MERGE_SHA`.

```bash
MERGE_SHA=<40-hex-origin-master-merge-sha>
SOURCE_REPO=/absolute/clean/mastermind-checkout
PYTHON_BINARY=/absolute/root-owned-python-3.12/bin/python3.12
PYTHON_RUNTIME_ROOT=/absolute/root-owned-python-3.12
OPERATOR_USER=chriswong

sudo /bin/bash ops/executive_os/bootstrap-host.sh \
  --operator-user "$OPERATOR_USER"

sudo /bin/bash ops/executive_os/install.sh \
  --source-repo "$SOURCE_REPO" \
  --expected-sha "$MERGE_SHA" \
  --operator-user "$OPERATOR_USER" \
  --python-binary "$PYTHON_BINARY" \
  --python-runtime-root "$PYTHON_RUNTIME_ROOT"

sudo /bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/acceptance.sh" \
  --source-repo "$SOURCE_REPO" \
  --expected-sha "$MERGE_SHA" \
  --operator-user "$OPERATOR_USER"
```

Acceptance must additionally record:

```bash
/usr/bin/plutil -lint \
  /Library/LaunchDaemons/com.mastermind.executive.control.plist \
  /Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist

/bin/launchctl print system/com.mastermind.executive.control
/bin/launchctl print system/com.mastermind.executive.worker.codex

/bin/bash \
  "/Library/Application Support/MastermindExecutive/releases/$MERGE_SHA/ops/executive_os/status.sh"
```

No tmux, Terminal scrollback, desktop login, or uncommitted checkout may be used
as acceptance state.

## 12. Required acceptance receipts

The canonical expected receipt root is:

```text
/var/db/mastermind-executive/control/acceptance/<merge-sha>/
```

| Required evidence | Current state |
|---|---|
| `acceptance-summary.json` | **NOT AVAILABLE — root host proof not run** |
| exact release/config/plist/process attestation | **NOT AVAILABLE** |
| fresh control environment + secret-canary composite receipt | **NOT AVAILABLE** |
| real Codex success Job/Attempt/result/validation/UID sweep | **NOT AVAILABLE** |
| completed-state restart with no relaunch | **NOT AVAILABLE** |
| active interruption → LOST → explicit requeue → completion | **NOT AVAILABLE** |
| raw worker-UID terminal seal and requeue/archive boundary | **NOT AVAILABLE** |
| detached `setsid()` descendant cleanup | **NOT AVAILABLE** |
| online backup, verification, offline restore, post-restore reopen | **NOT AVAILABLE** |
| zero TCP listener and no app/scheduler activation | **NOT AVAILABLE** |
| recursive secret-leak scan | **NOT AVAILABLE** |

The acceptance command must fail closed rather than emit a passing summary if
any row is missing. After a genuine run, update this section with Job/Attempt
IDs, receipt paths, SHA-256 digests, exact merge SHA, observed UIDs, and command
exit statuses. Never paste canary values, provider auth, DB rows, lease tokens,
or environment contents into this report.

## 13. Automated verification map

The committed test surface is designed to cover:

| Requirement | Test lane |
|---|---|
| launchd plist semantics and fixed argv | `tests/test_executive_launchd_config.py` |
| migrations, fencing, durable process identity | `tests/test_executive_os_sqlite.py` |
| exact allow/deny authority and scoped writes/argv | `tests/test_executive_authority.py` |
| exact-SHA private clone and narrow shared write path | `tests/test_executive_workspace.py` |
| redacted launch attestation, profile, result validation | `tests/test_executive_codex_worker.py` |
| success, cancel, restart, LOST/requeue, terminal seal, event order | `tests/test_executive_supervisor.py` |
| bounded AF_UNIX service, quarantine, no scheduler import | `tests/test_executive_service.py` |
| typed broker, peer UID, UID sweep, remote receipts | `tests/test_executive_worker_broker.py` |
| distinct-principal/path-free secret canary | `tests/test_executive_canary.py` |
| online backup, tamper, restore, rollback | `tests/test_executive_backup.py` |

Hosted Linux CI proves deterministic code and protocol semantics only. Tests
using mocks do not prove macOS UIDs, launchd, Seatbelt, native Codex, signatures,
TCC, `getpeereid`, `KERN_PROCARGS2`, or whole-UID cleanup. Those remain the
mandatory opt-in real-host acceptance lane.

Current local deterministic evidence on the audited branch is:

- 210 focused Executive OS tests passed and one opt-in platform test skipped;
- the opt-in native Codex Seatbelt profile test separately passed on this Mac;
- the exact hermetic governance test selection passed with two platform skips;
- the exact Portfolio v2 safety gate passed with one platform skip using the
  CI-pinned Macro engine SHA; and
- source compilation, shell syntax checks, `plutil` validation, and diff
  whitespace checks passed.

These results are development evidence, not substitutes for the unavailable
root/launchd receipt inventory in section 12.

## 14. Limitations and Phase 1C-B

Phase 1C-A intentionally pins one worker UID and one concurrent Job. During an
active attempt that UID necessarily owns or can traverse its assigned workspace,
run directory, and provider home; it is not a general hostile multi-tenant
sandbox. Terminal attempts do not retain that exposure: the final UID sweep and
control-owned `0700` seal revoke raw worker-UID traversal before terminal state.
The assignment manifest, protected roots, serialized lifecycle, native Codex
profile, canaries, whole-UID cleanup, and terminal seal are the bounded proof.

The exact Phase 1C-B recommendation is:

1. keep the durable SQLite/runtime and typed Job/Attempt contracts unchanged;
2. split the non-root controller from a minimal root-owned privilege broker;
3. allocate a fresh disposable OS principal or stronger VM/container sandbox
   per attempt, with an ephemeral provider credential handoff;
4. make the broker own per-attempt filesystem materialization, ownership
   handoff, process creation, cross-UID signal/cleanup, and teardown receipts;
5. replace the serialized shared active-assignment UID with per-attempt
   identities and promote sealed control-owned evidence to immutable archives;
6. package and attest a reproducible root-owned Python runtime rather than make
   host provisioning an external prerequisite; and
7. add capacity routing only after one-host, one-worker receipts remain stable.

Phase 1C-B must not add Fable, remote CEO control, scheduler integration,
automatic PR/merge/deploy, portfolio writes, or capital authority as a side
effect of this isolation work.
