# Executive acceptance maintenance: `supersede_unstarted_preproof_v5_to_v7_v1`

## What this mode is

`mastermind.executive_acceptance_maintenance/supersede_unstarted_preproof_v5_to_v7_v1`
is one new, source-only maintenance admission in
`ops/executive_os/acceptance_maintenance.py`. It retires exactly one installed
unstarted `supersede_preproof_v1` preparation whose *source* release has since
completed the offline `v5 -> v6` and `v6 -> v7` transitions. It exists so the
host can carry the untouched prior PASS chain (and the one failed planner bound
to it) onto a fresh v7 working prestate without relabelling, replaying or
re-adjudicating the selected v5 lineage.

Everything the incumbent modes enforce stays in force:

* the v1 descriptor, the V2 carry, `supersede_unstarted_v1`, `supersede_prejob_v1`,
  `supersede_preproof_v1` and `supersede_unstarted_preproof_v1` keep their exact
  descriptors, selectors, guards, allowlists and refusal rules. The shared
  snapshot reader now explicitly closes its owned SQLite connection; its
  transaction, queries and returned projection remain unchanged. New migration
  behavior otherwise stays in the explicit new-mode branch and its helpers;
* the selected link of the new mode still admits only an original
  `supersede_preproof_v1` preparation — never a nested newtype, an old V2
  supersession or a pre-Job prefix;
* `verify_preserved` is unchanged: the working v7 prestate is compared to the
  post-acceptance store with the same proof/job/event/quota/assignment
  allowances and the same refusal of unrelated drift.

## Descriptor and working bundle

The closed descriptor key set is the V2 working keys plus:

* `superseded_unstarted_preproof_sha` — the selected v5 preparation,
* `superseded_descriptor_sha256` — its exact sealed descriptor digest,
* `schema_upgrade_evidence_sha256` — canonical digest of the sealed
  `schema-upgrade-evidence.json` material,
* `source_control_config_sha256` — SHA-256 of the raw old control-config
  preimage sealed as `source-control.json`.

The published bundle keeps the usual six sealed preparation documents and adds
exactly two Root-sealed migration documents; the closed working namespace is
`descriptor.json`, `preparing.json`, `baseline.json`, `inventory.json`,
`prior-secret-canary.json`, `prestate.sqlite3`, `schema-upgrade-evidence.json`
and `source-control.json`. The baseline, the freshly created Root backup and
the working inventory are all v7. `source-control.json` is written by a
dedicated bounded raw writer (`write_sealed_bytes`) that seals the exact
preimage bytes — JSON whitespace is never rewritten, and the descriptor hashes
the raw bytes. The selected v5 bundle is never modified, relabelled or
overwritten, and a v5-then-v7 publication under one successor SHA is refused
like every existing target.

## The internal old-mode view

`_unstarted_preproof_v5_to_v7_view` projects one closed v5-to-v7 descriptor
onto the internal `supersede_unstarted_preproof_v1` descriptor the unchanged
validators already understand. The view is derived only from the actual
selected descriptor plus the verified source snapshot/inventory/canary
digests; it is never sealed, published or hashed, and the selected/deeper
walk it re-enters (`validate_superseded_binding`, the sealed canary
propagation and `guard.lineage`) therefore never demands that an original
selected v5 hash equals the working v7 prestate. Real semantic drift between
the selected v5 terminal evidence and the current v7 runtime is still
refused: the live terminal carry fields are re-derived with the unchanged
`terminal_carry_fields` over a read-only Runtime and compared against the
selected descriptor's shared V2 fields.

## Frozen evidence material and the original tool release

The stable material record is validated by `_validate_v5_to_v7_material`:
the exact top-level keys `schema_version`, stable INITIAL `phase`, `host`,
`origin_records` and `chain`. `host` holds the actual absolute `runtime_root`
and `backup_root` and actual `control_uid`/`control_gid`; the twelve origin
records remain bound to the genuine owner. At
`material['chain']['tool_release']` — exactly `{'root', 'sha', 'tree_sha',
'manifest_sha256'}`. The mutable whole-config bytes, the working proof digests
and the owner's TEMP paths are deliberately absent from that record, so a
re-derived chain in a later phase can only equal the sealed original by being
the same migration evidence.

`_v5_to_v7_tool_release(material)` returns the ORIGINAL migration tool
release `material['chain']['tool_release']['sha']`. It is used for every
retained/historical verifier call and for the admission requalification. The
descriptor's proof successor is used only where the mode means it: the
issuance-phase INITIAL call and the staged-release proof.

`_v5_to_v7_origin_record` is the closed identity record of one qualified
original backup/manifest: `path, device, inode, uid, gid, mode, nlink, size,
mtime_ns, ctime_ns, sha256`, where `mode` is a permission int (no file-type
bits), `nlink` is exactly 1 and `path` is the original canonical absolute
address. The original addresses are read only from
`origin_identities['database']['path']` and `['manifest']['path']` — never by
recursive key guessing, and never from the temp copy.

## Qualified Root control config (blocker B repair)

The fixed `SYSTEM_ROOT/config/control.json` preimage is read through the
existing guarded control-principal owner (`_root_json`) as Root-owned,
Control-group, mode `0440`, single link, no ACL — before the canonical lock
is opened — and `_RootConfig` keeps the held descriptor, named identity,
sealed ancestors and raw bytes pinned. Every final edge (preflight return,
the atomic rename, the runmarker) re-proves the same preimage with
`config_holder.check()`. The config legitimately becomes the successor
before admission, so the *current* Root config is qualified separately there
and is never required to equal the sealed old source-control preimage; the
sealed old preimage is still proved against its own descriptor pin.

## Canonical service lock (new mode and preflight only)

Both the preflight and the v5-to-v7 issuance/admission hold the runtime's own
existing canonical lock: `data/control_plane/executive-service.lock` beside
the authoritative database, derived from the qualified actual config. The
authoritative database is at `<runtime_root>/data/control_plane/
executive.sqlite3`, the state directory is `<runtime_root>/data/
control_plane`, and the backup root is `<TOP_RUNTIME>/control/backups`. The
trusted logical alias covers exactly the configured
`/var/db/mastermind-executive/control/db` spelling, mapped to its fixed
physical `/private/var` target with the alias identity and target pinned and
re-checked; any other spelling is never mapped and never generically
resolved. The lock file must already exist as a control-owned single-link
`0600` regular file with no ACL; it is opened `O_NOFOLLOW|O_NONBLOCK`
(never created, chowned, rewritten or removed) and locked with one
nonblocking `flock` held through every snapshot, evidence API call, final
rename or runmarker. `executive-service.running` and
`executive-schema-upgrade.in-progress.json` must be absent and are rechecked.
Occupied/replaced/ancestor/alias/marker/barrier/config drift refuses at the
exact final edges: just before the preflight result is returned, just before
the atomic rename, and just before the runmarker. The lock owner is passed
through preflight, issuance and admission (`lock=`), so the final edge is a
real check and never a discarded `None`. Account provenance comes from the
actual `pwd`/`grp` Control identity, never the caller's UID. The lock is
released before any Control-owned offline migration and before normal Service
startup; the retained/finish/historical paths never acquire or require it,
and no full process census is claimed.

## Read-only source-only preflight

`--qualify-v5-source-only` is an explicit, exclusive *action* that pairs only
with `--supersede-unstarted-preproof-v5-to-v7-sha` and the exact
selected/root/ancestor arguments. It runs while the live store is still the
selected v5 prestate and the installed release is still the selected one, and
produces bounded constraint data on stdout only — no preparation directory,
backup, descriptor, runmarker or any other persistent write. It uses the
actual current v5 snapshot, inventory and secret canary, the full old-mode
view walk and the genuine root/terminal/assignment/selected/deeper guards.
Authoritative v5 SQLite reads use the incumbent immutable reader only while
stopped, sidecar-free and under the held canonical lock. Both the full snapshot
and the full eight-table v5 content digest, including `sqlite_sequence`, must
equal the original Root-sealed selected prestate. A retained no-follow FD copies
that exact hash-qualified sealed prestate into a private Root `0700` temporary
directory / `0600` file. The unchanged `RuntimeStore(..., create=False,
existing_writable=False)` and `Runtime.from_store` decode that verification
copy, never the authoritative v5 store. These temporary verification writes are
explicit and cleaned up; no persistent backup, bundle, marker or cache is
published. The preflight also uses and the staged successor
release proof `executive_backup._prove_upgrade_release`. The retained lock
and the held config preimage are re-pinned at the last edge before the result
is returned and the lock is released. The result is constraint data for the
operator, never write authority; the later issuance re-proves every source
seal against the original selected bytes. The constructor and CLI refuse
mixed actions, recovery grants and old selectors.

## Runbook position

1. Stage the exact successor assets and qualify the v5 source with
   `--qualify-v5-source-only` under exclusive Root custody and the canonical
   lock; release the lock.
2. The existing Control-owned offline owner performs `v5 -> v6` and then
   `v6 -> v7`, each COMPLETE and verified, never chaining on an
   UNKNOWN/barrier/partial receipt and never replaying an existing operation.
3. Root issues exactly one new v7 descriptor with
   `--supersede-unstarted-preproof-v5-to-v7-sha` while the installed config
   still selects the v5 release (`proof_base_sha == selected`), with arms and
   harness closed and services stopped. Issuance re-qualifies the staged
   successor through `_prove_upgrade_release` (code/manifest identity only),
   calls the bridge's INITIAL verifier with the qualified runtime root and
   successor, requires the strict v7 target, proves the selected v5 baseline
   equals `snapshot(e.source_v5_database)` and that the full v5 projection
   digest agrees across source, target and current, merges the exact source
   inventory with the eight qualified additions, pins the held Root config
   preimage, and publishes atomically.
4. The normal config/source/broker owner publishes the final release; the
   separate full acceptance proof runs against the new descriptor exactly as
   for any other successor.

There is no automatic cleanup, retry, restore or rollback here: a failed
preparation directory stays as private evidence, and post-commit uncertainty
follows the existing quarantine and forward-reconciliation rules of the
existing owners.

## Admission: INITIAL requalification through the runmarker (blocker A)

`Maintenance(...)` for the new schema holds the canonical lock from the first
snapshot and re-reads the descriptor before dispatch (expected digest and
schema/guard agreement; a header that flips schema cannot skip its own
guard). The fixed current Root config is qualified before opening the cross-UID lock.
It validates the sealed v7 baseline, upgrade evidence and raw source-control
pin, and opens INITIAL before any authoritative SQLite read. Genuine Runtime
row and terminal decoding uses the helper's qualified private target-v7 copy;
authoritative snapshots and full projections remain immutable, stopped and
sidecar-free under the held lock. It re-enters the retained source/deeper view
while retaining INITIAL with
`open_v5_to_v7_evidence(runtime_root, material['chain']['tool_release']['sha'])`
and proves:

* the freshly derived material equals the sealed original exactly,
* the current Root config the owner observed equals the separately qualified
  held preimage (never the sealed old preimage — the config legitimately
  became the successor before admission),
* the verified source v5 copy equals the selected preparation's own sealed
  baseline and the strict v7 target equals the live working baseline,
* the full v5 projection digest agrees across the original selected sealed
  backup, migration source, target and current, including `sqlite_sequence`,
* the working inventory is exactly the source inventory plus the eight
  qualified additions, re-read fresh.

That INITIAL context is retained, with `evidence.check()` and
`lock.check()`, through the last boundary immediately before the exclusive
run marker is written. There is no later INITIAL fallback: the finish and the
historical carry walk never reopen this verifier.

## First finish and the restore evidence (blockers C and D)

The acceptance run restarts the Service during `backup_restore`; the first
finish therefore never requires a stopped service, sidecar absence, a
quiescent database or a raw-hash match on the live store. Every non-circular
gate is proven *before* the retained owner is opened: the admitted instance
bindings (run marker, descriptor, sealed material, sealed source config), the
real current-run PASS summary digest, and all four actual Control `0400`
receipts read through the existing `_root_json` contracts.

The receipts are the actual v7 producer format. `_validate_v7_restore_receipts`
requires the full original `database_path`/`manifest_path` of the created
receipt to join the actual configured backup root (never a bare basename or a
foreign directory), the verification to carry a manifest binding equal to the
created receipt's, the drill to be a strict v7 drill, the applied receipt to
bind `restored_sha256 == final_runtime_sha256`, `source_backup_sha256` to the
qualified proof backup and `manifest_sha256` to its manifest, and
`restored_database_path` to be exactly the genuine configured authoritative
database. `_qualified_backup_manifest` additionally binds the receipt's
`backup_id`/`created_at`/database filename/sha/size to the actual backup
manifest read beside it. No receipt ever invents an inode.

`e.verification` and `e.restore_drill` are plain detached JSON dicts on the
frozen wire — the previous `.to_dict` calls are gone. Tuples normalize only at
the agreed `_json_data` JSON boundary, never with `default=str`. Only the two
explicitly named copy-address fields are normalized to the qualified original
addresses; every deterministic field compares, and the full canonical drill
dict and digest compare.

`verify_preserved` runs three times with the same working v7 baseline and
proof ids: over the verified proof-backup copy, and over the consistently
snapshotted postrestore store (before and after the retained walk). The
postrestore authority is observed explicitly through a no-follow descriptor,
bracketing the whole finish window: the path/device/inode are real
observations, never a receipt copy and never an invented inode, and no raw
hash or mtime equality with the restore receipt is demanded — legitimate
worker heartbeat and WAL activity under the running Service stays allowed.
The ordered PASS-summary Job IDs must equal the two proof IDs. The unchanged
physical-history projection is recomputed over both the qualified proof-backup
copy and a consistent current SQLite read transaction, and must equal the
applied restore receipt. The strict integer TX-9 invalidation count must equal
the exact active-OPERATOR_HARNESS predicate in the backup; this all-terminal
maintenance proof requires zero. Worker heartbeat/WAL activity is outside that
physical projection. The qualified origins and held live FD/named ancestry are
re-checked through the sealed write edge, then `acceptance-restore-evidence.json` is sealed (exact
closed shape) with the raw four receipt hashes, the qualified origin records,
the verification and drill, the observed postrestore identity, the proof job
ids, the accepted summary digest and the upgrade-evidence pin. The
schema-specific carry receipt then pins both the upgrade evidence and the
sealed restore evidence alongside the normal PASS bindings. The first finish
creates the first carry, so it never requires the not-yet-created carry.

## Future historical carry (blocker E)

A future accepted carry re-enters this mode through
`validate_carry_receipt`, which now dispatches the newtype predecessor to
`_validate_v5_to_v7_carry_history` — there is no caller-supplied
`historical=True` success escape. The genuine sealed schema PASS carry, the
exact digest of the real accepted summary and the pinned restore evidence are
gated first; then the exact closed restore-evidence shape, the four raw
receipt hashes re-read through the existing guarded owner, the actual
qualified origins (all eleven fields, cross-hashed to the pinned backup),
the original tool release/material/source-control pins, the admitted instance
marker and the proof lineage are re-proven — all before the retained owner is
opened. The retained walk then re-derives the immutable migration chain and
the qualified proof backup, verification and drill with the original address
joins, compares them to the pinned run, re-runs `verify_preserved` against
the sealed working v7 baseline and the pinned proof ids over the actual
snapshot of the verified copy, and re-checks the retained state. The
unchanged selected/deeper v5 walk still runs in the `historical` mode carried
by the caller's chain validation.

The historical path never calls INITIAL, never compares the current live
database with the initial migration target, and requires no current database,
quiescence, lock or marker state. The finish-observed database identity stays
exactly the historical observation it was sealed as — it is evidence of that
run, not a fabricated restore field and not a permanent current-inode demand.

## What this mode never does

* never relabels a v5 preparation, snapshot or backup as v7, and never
  overwrites a selected bundle;
* never grants a caller a boolean admission, a lifecycle PASS by assertion, or
  a replacement verifier built from caller dictionaries or stub callbacks;
* never performs, retries or rolls back a migration, and never touches
  `_offline_restore_lock`, the migration census, or the global EUID law;
* never widens the older selectors, drops a proof check, or normalizes away
  real semantic drift.

## Dependency and qualification limits

The actual evidence helper is a separately reviewed source component:
`schema_upgrade_evidence.py` SHA-256
`8c7f1584128a7e1834706bb7d3e02825e6263abba9eaf828d27a254e095b26d7`.
It requires the protected PR1812 manifest reader from the existing autonomy
owner; the earlier v5-only source without that dependency is insufficient.
The API returns detached JSON verification/drill dictionaries and closed
`origin_identities = {database: record, manifest: record}` maps. Temporary
verification addresses never replace authoritative original paths or inodes.

The joined test uses the same actual v5 source from nonissuing preflight through
both closed migrations, the actual helper, preparation, admission, two real
Runtime proof Jobs / three Attempts and the closed recovery-receipt validator,
normal online backup / verification / deterministic drill / offline restore,
the genuine PASS-summary validator, first finish and future historical carry.
It covers physical and normal logical `/var` layouts with fixture-owned aliases,
running WAL/heartbeat changes while the service lock is held, wrong ordered
summary IDs, wrong physical-history claims / strict count types, foreign restore
targets, and a self-rehashed historical receipt forgery. Later unrelated current
Jobs do not impose INITIAL state on a genuine historical carry.

The fixtures explicitly substitute host UID/GID/Root ownership, stopped-service
and release/census observations, and inherited accepted-ancestor/assignment-seal
inputs. The recovery absence observation is inert typed DATA consumed by the
real validator. These are source-composition tests, not genuine host eligibility,
provider execution, sealed historical authority, maintenance permission, consent,
canary readiness or a production acceptance run. No accepting joined path stubs
`verify_preserved`, the helper, summary validation or the backup/restore owners.
Unit scaffolding that lacks the genuine run/restore chain is tested as refusal,
not reported as an accepted predecessor.

New-mode preflight/issuance/admission hold existing canonical service-lock
custody and retain full selected/deeper identities through their final atomic
publication boundary. The separate current-run finish holds the postrestore DB
FD and namespace while allowing data/mtime/size changes from legitimate running
Service activity. There is no global cross-object lock: exclusive administrative
Root custody remains necessary against a noncooperating Root writer. A real
concurrent writer stops the operation. Rechecks do not create absolute atomicity
after descriptors close; no new lock, authority store, rollback, automatic
cleanup or retry is introduced. Failed private preparations remain evidence;
late refusal requires no final bundle or runmarker, not deletion of that evidence.

The raw remote returns and their environment-limited tests remain retained as
unaccepted worker evidence. Actual parent joined checks and the same independent
reviewer determine source acceptance; the final reviewed identity and affected
check results live in the existing source-return artifacts. No source test
permits replay of a prior operation or a live migration/configuration effect.
