# Current qualification quiescence, not a historical release acknowledgement

This prospective recovery capability belongs to the existing lease broker. It
adds no controller, lease action, raw database route, worker request or grant.
The original Nov7 Ubuntu4 qualification remains terminal and cannot be replayed.
Its temporary grant output and suppressed release response cannot be reconstructed
as a historical acknowledgement. No new receipt may backfill that missing fact.

The new broker CLI is:

```text
lease_broker.py inspect-qualification-quiescence \
  --orchestrator-id <actual original root> --pool minimax --host ubuntu4
```

The Root must qualify the exact protected source and bind the incumbent broker's
actual existing DB/lock paths through its existing owner configuration. Running a
checkout CLI against its own nonexistent default `broker/` path returns UNKNOWN;
that is not the actual broker. No source selection, installer, alternate account,
new credential or provider operation follows from this document. Actual invocation
requires Root's separate scoped decision. No live DB or broker read was performed
while preparing this source.

The handler runs before `default_broker()`. It opens only existing owned regular
files and the existing broker lock; no constructor, directory creation, migration,
GC, heartbeat, release, snapshot writer or account/provider reader runs. It holds
a shared lock against incumbent broker writers, performs a read-only SQLite
transaction, and rejoins the named lock, DB, parent and sidecars after the read.
When a committed WAL exists it is read, never ignored. With no WAL/SHM under that
lock, an immutable read of the checkpointed database prevents creating sidecars.
A rollback journal or incomplete WAL/SHM pair is UNKNOWN, not recovery permission.
Existing SQLite shared-memory read marks are bookkeeping; lease/DB/WAL data are
not written. The query has a bounded local execution deadline, not a provider,
lease, qualification or commissioning-budget change.

The read covers every account for the exact root+minimax+ubuntu4 scope. Held and
rented rows count even if their TTL is old. Only states already recorded released
or expired by the broker are non-held; this read never expires them. Same-scope
waiters, including unknown-host demand, hold the result. Unknown row states,
busy/replaced lock, malformed/missing DB or namespace drift yield UNKNOWN.

`QUIESCENT_IN_SCOPE` means a current locked snapshot has no matching held/rented
lease and no matching pending waiter. It supplies no original run-ID mapping,
release ACK, host-wide idle claim, retry permission or maintenance authorization.
Together with the independently retained terminal prelaunch/no-START evidence,
it can support Root's current quiescent-maintenance judgment. Root must prevent
new scoped dispatch while performing that maintenance; the installer's separate
all-worker physical admission lock/active-set/currentness fences remain decisive.
The prior install API's settlement prerequisite must not be relabeled as proof of
a historical release ACK. The new read does not itself set that prerequisite.
A detached JSON or `original_settled` boolean is not authorization to install.

For an actual bounded handoff, `Broker.qualification_maintenance_guard` retains
that SAME broker lock across the separately authorized fixed-owner operation. It
yields a non-serializable live guard, checks quiescence before yielding and again
on normal return, and retires on every exit. Its `require_current()` rejects a
closed/replaced/expired guard or a non-quiescent read. Guard currentness
expires after 30 seconds; this is not a provider/lease budget extension and no
timer or cancellation operation is introduced. This blocks normal broker writers
from creating a read-to-maintenance race. Root must prepare/qualify the fixed plan
before entry, keep new scoped dispatch stopped, and perform at most the existing
20-second bounded transport call inside that synchronous context. Do not yield
it across user interaction, turns, arbitrary work or provider/worker operations.
The remote installer still independently holds/rejoins its physical all-host
admission lock and active set; zero original-root rows is never host-wide idle.
Any exceptional or uncertain remote result remains on its original carrier and
cannot be retried. The guard is evidence continuity, not a new dispatch/grant
API; this source contains no broker-to-remote runner or automatic mutation.
Root must adjudicate actual maintenance separately and must not transform an old
snapshot into the existing installer's settlement prerequisite.

# Closed inspector diagnostics

Root's one fixed inspection returned exit78 and only HELD_OR_UNKNOWN. Its exact
cause is still unknown and that operation must not be repeated. The prospective
wrapper now adds one allowlisted `reason` to that same exit78/replay:false reply.
Known ownership, namespace, lock, marker and preimage holds have fixed labels;
only closed filesystem errno categories are disclosed. Unrecognized/private
exceptions remain UNCLASSIFIED; no paths, messages, traceback or credentials are
returned. This changes observability only, not scope, refusal or automatic retry.
Root alone may decide a separately qualified diagnostic read after review.

# Prospective retained grant/release protocol

The remaining future-only improvement is to retain a request-bound lease-grant
receipt immediately after actual acquire and a companion containing the actual
once-only broker release result, in the existing per-run artifact directory.
An effect-free adapter settlement projection can then bind run/root/parent,
request and launch hashes, lease ID and exact acknowledged reply. Missing grant,
failed retention, lost/unqualified reply or mismatched identity must remain UNKNOWN.
No success may be backfilled for the original run. That retention change is not
implemented or claimed by this recovery-read/diagnostic source delta; it must not
hold the current quiescence capability hostage.

Checks use disposable local fixtures only:

```text
python3 -m unittest tests.test_fabric_qualification_quiescence \
  tests.test_ubuntu4_policy_enrollment -q
```
