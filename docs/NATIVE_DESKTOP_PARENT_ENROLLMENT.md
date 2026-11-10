# Existing Desktop-parent enrollment

This source component binds an already-running original Desktop parent to an
already-admitted canonical Attempt. It does not launch, resume, fork, create a
Job, issue a grant, or turn stored chat metadata into a running process.

`OperatorHarnessRegistry.enroll_existing_desktop_parent` requires:

- an exact canonical original thread and current turn;
- an existing Attempt lease, committed requested-profile seal, effective grant,
  placement, and matching root Job;
- a private host-owner handle bound to a qualified installed service peer;
- the host's actual synchronous current-writer fence and fresh observation of
  thread, turn, process instance, and inherited authority.

The trusted host holds its fence through the SQLite commit. Peer identity and
observation are rechecked before that commit. The existing Runtime epoch,
process-generation, and event tables hold the enrollment. Its operation kind is
`enroll_existing_desktop_parent`, never `start_session`. Exact replay validates
both immutable receipts and the same current generation; it does not commit a
second enrollment. A response failure after commit is recovered with that same
operation, not a new parent or operation ID.

Enrollment alone does not admit work. Existing requested/observed attestation,
principal, placement, grant, lease, and policy checks remain necessary for the
canonical binding projection. That projection is durable Runtime evidence, not
a new live Desktop observation. An authenticated caller must still establish its
current process and capability at the existing service boundary.

The original host retains process and turn control. Generic OperatorHarness
start, turn, stop, cancel, checkpoint, result, and resume mutations reject these
epochs. The enrollment API and attestation seal are the only allowed OHF write
paths. A future host-specific continuation or retirement protocol must be designed
and reviewed explicitly; enrollment is not permission to kill or replace a
Desktop parent. Generic Attempt bookkeeping also does not convey process-control
permission.

## Missing live prerequisite

No host-owner factory, new RPC tool, service flag, or installed binding is enabled
by this change. The private composition function is usable only by a trusted
service that already owns the actual Desktop writer fence and observation; a
caller-created lock or observation does not satisfy that contract. Python private
handles are composition boundaries, not isolation against arbitrary code execution
inside the trusted service process.

The currently inspected Desktop `thread/read` result is stored metadata
(`notLoaded`, direct-input availability unknown). Hook session/turn fields do not
supply an authenticated active-writer process or inherited Runtime grant. Neither
is a production enrollment input. The reachable live condition is a qualified
Desktop-host integration that exposes that exact observation and writer fence,
and an owner-admitted canonical original-parent Attempt/grant. Creating a planner
or substitute chat merely to obtain those records does not satisfy the condition.

Tests use real canonical SQLite lease/grant/attestation machinery and a mocked
host boundary. They prove transaction, refusal, replay, and projection behavior;
they do not attest the real Desktop process, install anything, or prove native
reply consumption. Fixtures create their own test-only jobs and never enroll a
production chat.
