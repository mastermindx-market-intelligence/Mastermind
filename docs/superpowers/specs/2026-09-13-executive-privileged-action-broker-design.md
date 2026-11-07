# Executive Privileged Action Broker Design

**Status:** Chairman-approved design for implementation on 2026-09-13.
**Protected design base:** `f087f9cf90a8fc7a81273c2576eefa6d06b54d9e`.

## Outcome

Mastermind orchestrators running in Codex, Claude Code, Web CEO, or the Executive OS must stop blocking on repeated macOS administrator prompts. The system must provide unattended privileged effects without storing Chris's administrator password, granting an agent an arbitrary root shell, or creating a second lifecycle/control plane.

The first production-proven vertical slice must let an authorized local operator session invoke reviewed Executive OS service lifecycle actions and worker-auth verification without a password prompt, while receiving a deterministic, secret-free receipt.

## Non-goals

- No `NOPASSWD: ALL`, setuid shell, reusable administrator password, or password in Keychain/1Password for model consumption.
- No arbitrary `exec`, shell string, caller-selected executable, caller-selected root path, or root execution of a mutable worktree.
- No new Job queue, scheduler, retry engine, identity system, or authority database.
- No autonomous capital execution, billing, deploy, or general credential extraction.
- No bypass of provider/account authentication itself; this solves host privilege and model permission prompts, not vendor login policy.

## Architecture

Add one subordinate privileged executor to Executive OS. It is a launchd socket-activated root process, not a scheduler or resident root worker. launchd owns a private Unix socket. The broker authenticates the kernel peer UID, validates one typed request against a closed action catalog, executes only an exact root-owned installed release action, verifies the return, writes a secret-free receipt, and exits when idle.

The broker's caller surface is a non-root client CLI (`mmx-admin`) usable by Chairman-owned Codex/Claude/Web CEO sessions. Socket permissions and a root-owned config restrict callers to the installed operator UID and `_mastermind_exec`. The request never contains a command line chosen by the model.
## Action contract

V1 exposes only these actions:

| Action | Effect class | Arguments | Root implementation |
|---|---|---|---|
| `executive.services.start` | `SERVICE_CONTROL` | none | installed `ops/executive_os/service-control.sh start` |
| `executive.services.stop` | `SERVICE_CONTROL` | none | installed `ops/executive_os/service-control.sh stop` |
| `executive.services.restart` | `SERVICE_CONTROL` | none | installed `ops/executive_os/service-control.sh restart` |
| `executive.worker_auth.verify_only` | `CREDENTIAL_ADMIN_READINESS` | optional reviewed slot id | installed `provision-worker-auth.sh --verify-only` |
| `executive.worker_auth.verify_ready` | `CREDENTIAL_ADMIN_READINESS` | slot or reviewed credential class, exact UTC expiry | installed `provision-worker-auth.sh --verify-ready ...` |
| `executive.worker_auth.recover_transaction` | `CREDENTIAL_ADMIN_RECOVERY` | optional reviewed slot id | installed `provision-worker-auth.sh --recover-readiness-transaction` |

No V1 action accepts secret bytes. Credential enrollment/replacement remains outside V1 until a separate secret-delivery design prevents model-visible extraction.

Every request carries `schema`, `request_id`, `action`, and an `args` object. `request_id` is an idempotency key. The broker hashes the canonical request before effect. A completed matching request returns the existing receipt; a reused id with different content refuses. A stale in-flight marker is `EFFECT_UNKNOWN` and is never blindly retried.

## Trust boundary

The launchd plist, broker config, Python runtime, broker entrypoint, and installed release must be root-owned and non-group/other-writable. The broker refuses to run unless EUID is 0 and the configured release root is under `/Library/Application Support/MastermindExecutive/releases/<40-hex-sha>` with a valid Executive release manifest.

The broker never imports code from `$HOME`, the caller's current directory, project `.codex` layers, or a mutable Git checkout. It runs with a closed environment and absolute executables. Subprocess calls always use argv arrays with `shell=False` semantics.
## Installation and first arm

The existing exact-release installer gains an explicit `--arm-privileged-broker` flag. Installation materializes a root-owned broker config and launchd plist from the exact release, validates both, and leaves the broker disabled unless the flag is present. With the flag present, the installer enables and bootstraps only the broker after all trust checks pass. Control, worker, backup, and relay lifecycle semantics remain unchanged.

This is the one unavoidable administrator ceremony. The operator runs the reviewed installer once with local sudo from protected master. After that, sessions call `mmx-admin`; they never need the administrator password for catalogued actions.

The broker is socket-activated and has no queue. launchd may retain or restart the broker process, but the process itself owns no work lifecycle beyond one synchronous request. Executive OS remains the owner of Jobs/Attempts/Workers/Events.

## Receipts and correction behavior

Receipts live under `/var/db/mastermind-executive/privileged-actions/receipts/`, owned root:wheel mode 0600 beneath a root:wheel 0700 directory. They contain request id, request SHA-256, action, effect class, started/finished UTC, exit code, bounded/redacted stdout/stderr digests, outcome, installed release SHA, and broker version. Secret values are prohibited by schema and never persisted.

Before spawning an effect, the broker atomically writes an in-flight marker and fsyncs it. On normal completion it atomically replaces that marker with the terminal receipt. On startup/request, any stale marker for the same request produces `EFFECT_UNKNOWN`; the caller must reconcile the target state or use a dedicated recovery action rather than blind-retry.

## Status query (read-only)

An authorized non-root caller may inspect an earlier request without resubmitting it:
`mmx-admin status --request-id ID`. The client sends
`mastermind.executive_privileged_action_status_request.v1` (exact keys `schema`,
`request_id`) over the same socket, after the same kernel-peer authentication and the
same bounded request-id grammar as effect requests. Status never accepts an effect
argument and never generates an id.

The broker's status handler authenticates the peer, validates the request, and reads
only that id's existing terminal receipt, in-flight marker, and any already-created
broker reconciliation record. A terminal receipt always wins over a leftover marker.
It returns exactly one of:

- `TERMINAL`: the stored child receipt, verbatim, from whatever release produced it;
- `RECONCILED_NOT_APPLIED`: the original marker is still present byte-for-byte and a
  create-only reconciliation record mutually validates that exact marker and the
  independently proven pre-effect readiness state;
- `EFFECT_UNKNOWN`: a marker exists without a valid reconciliation record;
- `NOT_FOUND`: neither terminal nor in-flight/reconciled evidence exists at observation time.

The response also carries `installed_release_sha`, the broker's own current release,
kept separate from any release SHA recorded in historical evidence. A
`RECONCILED_NOT_APPLIED` projection is **not** a synthetic child exit and never means the
original privileged effect succeeded or failed; it means the separately reviewed
reconciliation proof established that the requested business effect was not applied.

Status lookup remains pure observation: it never invokes the executor, creates or
repairs evidence, removes a marker, retries an effect, or recovers a transaction on the
caller's behalf. Creating a reconciliation record is a separate authenticated request
on the same existing broker socket/receipt plane and is permitted only for an exact
`executive.worker_auth.verify_ready` marker after the broker proves the target request
identity/digest, marker bytes/release, pre-effect readiness receipt and identity
continuity, absence of the target deadline, absence of the readiness transaction lock,
and absence of a live verify-ready process. The original marker is preserved.

`NOT_FOUND` is not authority to resubmit. `EFFECT_UNKNOWN` still requires explicit
reconciliation rather than blind retry. After `RECONCILED_NOT_APPLIED`, replay of the
original request id remains refused; any later readiness attempt requires a separately
authorized new request id.

CLI exit codes distinguish successful query retrieval from the original effect outcome:
`0` for a valid `TERMINAL` or `RECONCILED_NOT_APPLIED` projection, `75` for
`EFFECT_UNKNOWN`, `4` for `NOT_FOUND`, and nonzero for malformed or refused
responses. Exit `0` on `RECONCILED_NOT_APPLIED` acknowledges only that the status
projection was successfully validated. The effect actions and their effect exit
semantics are unchanged.

## Provider unattended permissions

Host privilege alone is insufficient if the model product itself pauses for approval. The Mastermind operator profile therefore standardizes:

- Codex: `sandbox_mode = "danger-full-access"` and `approval_policy = "never"` at the user operator layer, with a verifier that detects project-layer drift.
- Claude Code: user setting `permissions.defaultMode = "bypassPermissions"` for the dedicated Chairman-owned development account. Noninteractive launches use `--permission-mode bypassPermissions --permission-prompts none`.

These settings remove provider UI prompts; they do not confer macOS root. Root effects still go through the privileged broker.
## Failure behavior

- Unknown action, extra argument, malformed timestamp, unreviewed slot, unauthorized peer, mutable release, unsafe filesystem metadata, or non-root broker identity: refuse before effect.
- Child nonzero exit: return `FAILED` with bounded sanitized diagnostics; do not reinterpret it as success.
- Client disconnect after spawn: finish the bounded action and persist its receipt; transport loss does not imply no effect.
- Broker termination after the in-flight marker but before terminal receipt: preserve `EFFECT_UNKNOWN` for that request id.
- Receipt directory or fsync failure: refuse before effect when possible; after spawn, return/persist effect uncertainty and never claim success.

## Test strategy

Pure protocol/action validation is Linux-safe and unit tested. Broker tests use temporary sockets/directories and injected subprocess executors so CI never performs root effects. Static launchd/install tests prove root identity, fixed socket/path permissions, closed ProgramArguments, explicit arming, and absence of arbitrary shell surfaces. Provider-profile tests operate on temporary config homes.

Real-host proof runs only after merge from the exact protected master release. It must demonstrate: non-root `mmx-admin executive.worker_auth.verify_only` succeeds without a password prompt; an unknown/root-shell-shaped action is refused; a duplicate request id returns the same receipt; a changed duplicate id refuses; and Claude/Codex permission-profile verification passes.

## Completion

The capability is `PROVEN_LIVE` only when merged source, CI, exact installed release, launchd-activated broker, real non-root request, persisted receipt, and provider permission verification all agree. A green PR or an installed plist alone is `BUILT_NOT_PROVEN`.
