# Linux assignment boundary under the existing Fabric owner

This is source integration for the finite attended worker. It is uninstalled
and does not qualify an Ubuntu host, activate a profile, register a Worker, or
authorize a provider call. Ordinary shared-user Fabric remains on its existing
path. The native integration needs the stronger Executive assignment boundary.

## Mechanism

Reuse the existing dedicated-worker-user and Control-owned-directory design.
The remote Control principal and the preprovisioned worker principal must be
different. Control owns each newly prepared assignment child and retains its
identity; the worker receives only the reviewed group access for that
assignment. Terminalization withdraws that access at the child boundaries and
requires an actual raw-worker denial. Shared host parents, including B's
`0775` boundary, are never changed.

A same-user rootless namespace is not assumed equivalent. An immutable launch
grant, a closed model session, a released capacity lease, or process-group
absence does not withdraw access from a fresh process with that same host UID.
The current `FABRIC_ASSIGNMENT_SEAL_UNAVAILABLE` refusal remains until the
actual producer and host composition are qualified.

## Existing-owner sequence

1. **Prepare as remote Control.** Create new per-assignment children only under
   the qualified roots. Reuse `prepare_credentialless_clone` and
   `validate_shared_git_handoff`; preserve the exact source commit and retained
   input digests. Record remote filesystem identities on the remote host.
2. **Launch as the admitted worker.** At `remote_sub_exec._execute`'s existing
   owned-process boundary, require the installed authenticated owner mechanism
   that actually runs as the dedicated worker UID/GID and exact supplementary
   groups. Execute the fixed attended Claude descriptor under its enrolled
   realm. A user name, UID in JSON, or environment variable cannot grant this
   mechanism. Missing identity or capability refuses before provider launch.
3. **Settle through the same owner.** Retain the ordinary process/capture
   evidence, then use the existing `DedicatedUIDSweeper` as the dedicated
   worker owner. Its Linux census must cover real, effective, saved and
   filesystem UIDs. Preserve the original owner's exclusive admission of that
   dedicated UID while cleanup, seal and readback run. An advisory Python lock
   alone does not exclude other host launchers.
4. **Seal as Control.** Revalidate the original workspace/run directory
   identities through held descriptors, remove worker traversal at those exact
   Control-owned children, and fsync. Never roll back a successful withdrawal
   if another boundary or persistence operation fails. Partial effects retain
   the original Attempt and require reconciliation.
5. **Verify as the former worker.** The installed owner executes a fixed raw
   worker probe. Open, list and stat-through-child must fail with `EACCES`;
   `ENOENT` is not equivalent. An assigned-path positive from before withdrawal
   binds the same resource and sentinel identities. No file contents or
   credentials are returned. The probe is an owner operation, not an
   instruction for the model to change identities.
6. **Retain and deliver.** Persist the original cleanup, filesystem and probe
   records, bound to Job, Attempt, grant, physical route, boot and process
   generation. The existing authenticated transport independently reads those
   retained bytes. Read-only status must never perform a new census, seal,
   probe, signal or lease release. Supervisor consumes qualified evidence
   before a durable terminal transition.

## Linux-specific qualification

The existing Darwin `ps` projection is not Linux qualification. Linux exposes
four UID values in `/proc/PID/status`, and filesystem permission checks use
the filesystem IDs and supplementary groups. A process whose effective UID
differs can still hold worker authority through another relevant ID.
See the Linux man-pages project's [status fields](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
and [process credentials](https://man7.org/linux/man-pages/man7/credentials.7.html).

An apparently empty process listing is insufficient. A qualified census must
have the expected host/PID-namespace and procfs visibility; `hidepid` can hide
process directories. Denied, malformed, incomplete, changed or over-bound
observations refuse. PID/start-generation checks must accompany any targeted
process action. No environment or command-line contents are needed. See the
[procfs visibility rules](https://man7.org/linux/man-pages/man5/procfs.5.html).

Changing the probe's real/effective/saved identities requires an already
installed privileged owner operation, or execution by the existing dedicated
worker owner. This source does not add sudo, provision accounts, copy keys,
create a daemon or supply privilege from configuration. Every identity-change
failure must be checked. See [setresuid/setresgid](https://man7.org/linux/man-pages/man2/setresuid.2.html).

## Actual host prerequisite

No applicable authenticated Ubuntu dedicated-principal launch/probe mechanism
or remote assignment-seal receipt has been qualified in the inspected current
composition. The Mac receiver's installed Control service does not establish
those remote facts. The existing Darwin/Grok host qualifier cannot be relabeled
as an Ubuntu/MiniMax qualifier.

Installation therefore still needs the real existing host owner's qualified
principal/group arrangement, exclusive UID admission, root ownership, enrolled
realm, launch/probe mechanism, and positive/negative live evidence. This is an
explicit host qualification requirement, not evidence that a new account must
necessarily be created. No account or host operation is performed by this
document or by inert source tests.

## Returned source adjudication

The original `fabric-linux-assignment-boundary-build-01a11e90-v1` returned
4,641 bytes with SHA-256
`67ccbbdee84f14b567199f8a7aa7bde48067cbd8800d6c99e5215a6e34cca80d`.
All three advertised files were retrieved once and hash matched. The candidate
is **NOT_ACCEPTED_AS_PRODUCED** and is not part of the installed source.

An inert falsifier constructed `OwnerAdmissionExclusion(held=True)` and supplied
an empty fixture directory to its process census. That minted a cleanup
capability without an actual launcher admission fence. Refusing a `from_json`
method does not close this public constructor. The returned helper therefore
cannot establish the required host authority, regardless of its test count.

The real existing broker exclusion is its owned start/active/sweep state under
`WorkerBroker._state_lock`. Current collection clears `_active_run_id` after
terminal sweep, before Control seals the assignment. A receipt from that ended
interval is not itself a live owner scope. This alone does **not** prove an
admitted START race: Runtime holds the claimed `(worker_id, quota_class)` until
after sealing, and the fixed-proof service path serializes its entire finisher.
No competing admitted START has been demonstrated for the current one-leaf
composition. A same-UID, multi-quota READ overlap would require two fully
matching admitted quota rows; that installed composition has not been proven.

The required owner integration must bind its scope to the actual canonical
claim and launch-owner interval through seal, fixed raw-worker probe and
retained readback, and refuse conflicting admission or owner drift. It must
govern the actual launcher, including `remote_sub`/`lane_runtime`; an unrelated
broker's lock is insufficient. The acceptance-only `sudo -u` probe does not
install this production remote operation.


## Source components for the original owner interval

The Linux `ProcessInspector` branch now uses the fixed proc filesystem, a
pinned original PID directory, exact field-22 start ticks and a canonical boot
UUID. Stat/status observations must preserve the process generation and all
real, effective, saved and filesystem principal values. It reads no environment
or command-line contents and cannot redirect inspection to a caller's proc
fixture. Inert tests qualify parsing and failure handling; they do not qualify
a host, proc visibility or the dedicated-UID census.

`BrokerPolicy.require_assignment_seal` is an opt-in source branch, defaulting
to false. No installed entrypoint enables it. When true, startup explicitly
refuses until an authenticated original-assignment reconciliation producer is
composed: empty roots and a startup UID sweep cannot settle a previous effect.
The branch rejects extra supplementary groups and validation effects. It extends
the incumbent broker's existing active-run exclusion, rather than adding a
second admission or lease owner.

After original collection, cancellation and terminal UID sweep have settled:

| Existing broker operation | Required evidence | Admission outcome |
| --- | --- | --- |
| `assignment-seal-prepare` | Original process/grant/Attempt, passing sweep, exact admitted directory identities and protected Control-owned parents | Retain the original active run |
| `assignment-seal-commit` | Matching prepared digest, Control seal, current exact directory identities, raw worker open/traverse/list `EACCES` | Cache the original shielded observation and retain the active run |
| `assignment-seal-finalize` | Authenticated Control's exact observation and durable-retention digests | Release only that original run |

The Supervisor's `_retain_remote_assignment_observation` source seam checks the
original Runtime lease/fence and persisted launch pin, writes the existing
private per-Attempt receipt, and independently reads back its bounded exact
bytes before producing the finalize acknowledgment. The gateway retains no
state. A worker-owned receipt is not durable Control authority. Changed digests
refuse; replay of an old finalized observation cannot release a successor run.
Shutdown drains original owned cancellation, collection, sweep and observation
tasks; disconnecting their caller does not manufacture physical completion.

These source components are not yet a remote seal producer or a production
Backend. The authenticated remote Control operation that prepares and seals the
actual Ubuntu assignment, the worker-principal launch/denial mechanism, restart
reconciliation, enrolled supported-harness profile, Linux census/host binding,
and full real-path acceptance remain separate requirements. The existing
`FABRIC_ASSIGNMENT_SEAL_UNAVAILABLE` refusal remains in force. No source flag,
fixture receipt or Mac Control observation supplies those remote capabilities.

### Authenticated original-owner source connection (2026-10-12)

The optional root-managed gateway `assignment_control` binding now fixes exactly
one worker principal and two Control-owned stores. `assignment-seal` accepts only
the original Attempt ID, obtains the incumbent broker's terminal snapshot, seals
its exact derived roots, and returns the broker's actual worker-denial observation.
It never finalizes the broker. No arbitrary path, executable, account, credential,
root directory, synthetic absence or cleanup claim is accepted from the request.
The source tests use real temporary-directory chmod and loopback mTLS, with
explicitly synthetic worker principals and denial observations. They do not prove
Linux host qualification or a real cross-UID denial.

The existing attended Fabric adapter and bridge now carry closed `assignment-seal`
and `assignment-seal-finalize` messages with original Runtime binding, physical
route digest and exact ProcessRef. `Supervisor.retain_and_acknowledge_remote_assignment`
retains and rereads the observation under the original lease before sending the
exact acknowledgement, then checks the lease and retained bytes again. Modifying
transport loss remains EFFECT_UNKNOWN. None of these paths converts status or a
cleanup read into authority for a filesystem effect.

This is source plumbing, not the admitted production Backend. The current local
bridge is non-Control and must not receive the MH1 Control private key. The concrete
original-owner Backend/transport grant, actual remote preparation and launch,
qualified Linux UID census/namespace and restart reconciliation remain required.
The new Supervisor method does not remove FABRIC_ASSIGNMENT_SEAL_UNAVAILABLE or
change the installed terminalization policy. Gateway binding defaults to absent;
no service config, host principal, profile, provider realm, Worker or arm is enabled.
