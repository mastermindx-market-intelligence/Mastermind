# Fixed original-operation v5-to-v6 pre-census continuation

This protocol handles one retained v5-to-v6 barrier whose first census failed
before a source preflight existed. A barrier alone has no phase or source
prestate. The protocol proves a safe present state; it does not retroactively
certify where the original process stopped. An observed process/controller
handle is not the barrier UUID or an authenticated upgrader PID.

This is a distinct explicit action. Ordinary v5-to-v6 admission still refuses
an occupied barrier and consumed recovery receipts. The original barrier,
operation ID, timestamp and old tool seal are never rewritten to name corrected
code. A current protected, fully sealed recovery tool R executes the continuation
and the later ordinary v6-to-v7 step. Its actual tool fields remain R throughout.

## Read-only inspection

The existing migration CLI's `--inspect-v5-to-v6-pre-census-barrier` action runs
as the existing Control account. It accepts no path, release, CAS or effect
selector. The backup owner opens only the fixed barrier leaf with O_NOFOLLOW and O_NONBLOCK, verifies
actual account/custody/native ACL and canonical closed JSON, and brackets its
named/FD identity and ancestors' permitted metadata. It does not open or list
ancestor directories, read the database, acquire the service lock, invoke a
census, write any receipt, or authorize continuation. Unavailable metadata is
a refusal. The Root issuer below may optionally compare the inspected UUID/hash as CAS
selectors; those values are DATA, not externally supplied authority.

An earlier directory READ denial remains a denial of that action. This fixed
leaf interface does not retry or grant the denied directory READ. Root's later
qualification is a separate explicitly authorized source/preservation action,
not an elevated replacement for Control inspection.

## Root qualification

Keep the original selected v5 configuration and original maintenance bundles
unchanged. Under exclusive administrative custody, use supported readside stop:
Control and relay must be absent, Codex Worker absent, Backup absent under the
supported stop contract; MCP remains running. The maintenance issuer checks
its actual Control/Worker and relay absence predicates; it does not claim that
all host services are stopped or that the service flock is a process census.

The existing maintenance action is explicit:

```
--qualify-v5-pre-census-continuation
--predecessor-sha <original accepted ancestor>
--successor-sha <actual protected sealed recovery tool R>
--root-job-id <original queued aggregation root>
--carry-terminal-dispatch
--supersede-unstarted-preproof-v5-to-v7-sha <original selected v5 release>
--superseded-descriptor-sha256 <exact selected descriptor canonical digest>
[--expected-operation-id <observed original barrier UUID>]
[--expected-barrier-sha256 <observed original barrier raw digest>]
```

The Root owner holds the actual existing Control-owned service.lock without
creating/chowning it, the original barrier leaf, qualified config and complete
selected/deeper source identities. It requires all four migration receipts and
both recovery receipts absent, no authoritative sidecars/unresolved restore
residue, closed intakes/harness, unchanged full preservation inventory and
canary. Existing immutable reads and private temporary verification copies
prove exact v5 DDL, all eight typed tables, sqlite_sequence and all five original
migration timestamps against the original sealed selected backup. It captures
current physical database identity honestly; it invents no pre-failure inode.

The fixed qualification is Root:Control 0440, regular, single-link, no ACL,
created O_EXCL in the canonical database state directory. Its fourteen closed
fields bind original barrier payload/identity and old tool; current recovery
R; current database identity/schema/full-v5 digest/migration vector; selected
raw/canonical descriptor, backup/baseline/inventory/canary digests; original
control-config digest; fixed roots/account; an honest qualification timestamp;
and `backup_inventory_sha256`. That scalar is exactly the existing inventory
algorithm over the physical Control backup root. Root qualifies the whole
preservation inventory; Control may independently recheck its own backup root
without reading Root or Worker private artifacts.

The issuer repeats full source/config/barrier/tool/inventory/canary/absence
checks at the seal boundary before making the child Control-readable. Before
that chmod a partial child remains Root-private 0600 and is not a valid
qualification. Any error preserves it for same-operation inspection; never
unlink/reissue or silently retry. A late result ambiguity after sealing likewise
requires inspection of the fixed artifact, not another issuance attempt.

No descriptor, acceptance run marker or original bundle is issued or changed
by qualification. Release of the service flock precedes Control migration.

## One-use Control continuation and failure

The migration CLI's mutually exclusive continuation action is:

```
--resume-v5-to-v6-pre-census
--database <fixed authoritative database>
--backup-directory <qualified Control backup root>
--release-sha <actual protected sealed recovery tool R>
--expected-operation-id <exact inspected original barrier UUID>
--expected-barrier-sha256 <exact inspected original barrier raw digest>
```

Do not combine it with ordinary `--transition` or `--from-version`.
The explicit backup-owner continuation validates the actual current Control
principal, fixed qualified Root receipt, old barrier/tool and new R seals,
current source raw identity and full semantics, original config, absent
receipts/sidecars/residue and the qualified backup-root inventory scalar.
It holds the existing canonical service flock and original barrier/source FDs.
It reserves the fixed Control-owned 0600 intent O_EXCL, fsyncs it and its parent
BEFORE any new census/checkpoint/backup/preflight/DDL. Existing or ambiguously
created intent prevents every further execution attempt. Inspection is read-only.

A fresh genuine census must account for exactly the current own lock, retained
barrier and source database read FDs. Only recovered P56 uses the distinct
`mastermind.executive_schema_upgrade_quiesce/pre_census_recovery_v1` census:
three distinct numeric FDs, actual own PID/Control UID, exact fixed paths,
read-only retained barrier/database. Ordinary censuses retain their one-lock
contract. There are no ignored foreign rows.

The normal migration, source/target backup verification and restore drills,
exclusive DDL, commit and completion proof follow. Transaction-owned SQLite
sidecars require their exact normal fixed names and actual held connection
transaction/custody; postcommit sidecar absence remains mandatory. Recovered
C56 is published only after all final source/backup/drill/census proofs and
exact held-original unlink, parent fsync, named absence and the expected one-name
namespace removal. It is O_EXCL/fsynced terminal completion DATA, not an earlier
promise. Ordinary v5-to-v6 keeps its existing publication order and wire.

Any failure before durable C56 retains intent, qualification and all remaining
artifacts. Even after successful unlink, missing/partial C56 blocks v6-to-v7.
Do not regenerate a missing barrier, replace a swapped one, invoke normal
rollback deletion, remove the intent, or create another operation. Missing or
swapped original custody before its qualified unlink stays UNKNOWN/quarantined.
Once genuine durable C56 exists, a later hook/result-delivery error is terminal
result ambiguity: preserve its receipt and intent for same-operation inspection,
never replay v5-to-v6. The ordinary v6-to-v7 gate may consume that exact completed
chain. Ordinary v5-to-v6 cannot run around any consumed recovery residue.

## Retained evidence and subsequent acceptance

Recovered P56 alone has schema
`mastermind.executive_schema_upgrade_pre_census_preflight/v1`, containing the
normal producer keys plus exact qualification/continuation identities. C56,
P67 and C67 retain their ordinary schemas and actual R executor identity.
The original old-tool barrier reference stays distinct and its canonical bytes
remain bound by the Root qualification.

The Root helper's explicit recovered material schema is
`mastermind.executive_schema_upgrade_evidence/pre_census_recovery_v1`.
Exactly fourteen origins are retained: the normal four receipts/eight backup
files plus the Root qualification and Control intent. INITIAL and HISTORICAL
rederive the immutable chain with actual origin custody; normal material still
requires exactly twelve. The helper exposes held qualification DATA so the
maintenance consumer joins its selected-source fields and original config to
the actual selected lineage. Inventory additions remain exactly the eight
qualified backup files. No blanket backup-root exclusion is added. Historical
verification binds the immutable backup-inventory scalar but does not recompute
it after legitimate backups or require the original live database/lock.

After the two genuine transitions, use the existing migration-aware maintenance
producer/admission, normal service startup, real proof jobs, actual backup and
restore, genuine PASS summary and schema-specific finish/carry. Source checks
are not live eligibility, a migration receipt is not acceptance, and old R1
credit or expired readiness consent never transfers to the new release.

The FD/named/metadata checks and final atomic operations are not a global lock
against another Root writer. Exclusive administrative custody remains required;
concurrent external mutation is a stop, not permission to weaken checks.
