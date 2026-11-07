# One spent pre-census operation, new ctime epoch

This is a fixed protocol for a still-quarantined v5 operation whose first
Root-qualified continuation has spent its Control intent. It does not resume
that entry point, reissue its qualification, reconstruct a historical phase,
clear a barrier, or provide a general migration retry mechanism.

The original observed failure occurred after the checkpoint call and before
source backup/P56/DDL. A retained later observation found identical database
bytes and semantic content with only ctime changed. This does **not** establish
that the checkpoint caused the change. Local no-sidecar checkpoint experiments
have not reproduced that ctime-only event. Phase history and current safe-state
qualification are separate facts.

## Immutable provenance

Keep the original barrier, Root qualification and spent Control intent exactly
as issued, including their identities, payloads, release bindings and times.
The barrier identifies the original executor; the qualification/intent identify
the first recovery executor. Both releases remain independently sealed. The
actual new executor is separately sealed and must differ from both. None is
relabeled as another release.

The only new paths are, in the fixed authoritative database parent:

- `executive-schema-upgrade.v5-to-v6.spent-pre-census-ctime-reconciliation.json`:
  Root:Control, mode 0440, eight closed fields.
- `executive-schema-upgrade.v5-to-v6.spent-pre-census-ctime-continuation.json`:
  Control:Control, mode 0600, eight closed fields.

Each uses exclusive creation and retained descriptor/name/ancestor/native-ACL
checks. A partial publication remains quarantine; do not remove, overwrite,
regenerate or issue a replacement. The new Control reservation is durable
before migration effects. Missing or swapped original artifacts are refusal,
not permission to reconstruct them.

## Fresh Root boundary

The explicit maintenance action `--reconcile-spent-v5-pre-census-ctime` is
separate from the original qualification action and maintenance-descriptor
issuance. It uses the actual guarded configuration, fixed account identities,
existing canonical service lock and supported Control/Worker/Relay absence
predicates; it does not require all host services to be absent or stop MCP.

Reconstruct the complete original selected v5/deeper lineage, sealed baseline
and source backup, full artifact inventory, historical canary, disarmed config,
closed worker harness and permitted backup-root inventory. Require exact
agreement with the original qualification, alongside current complete v5
schema/vector/full-eight-table content including sequence and migration
receipt timestamps. Every original database-origin field and its raw hash
must agree except for a genuinely different recorded ctime. Equal semantics
with different bytes, replaced inode, changed mtime or altered custody refuses.

Revalidate all of those predicates after durable private candidate creation,
immediately before making the Root receipt Control-readable. Failure retains
the private child. This is fresh PRESENT evidence; it never grants old phase
credit. The original qualification is not edited or reissued.

## Control and retained acceptance

The distinct Control owner revalidates all three old origins plus the new Root
receipt, fixed config, permitted backup inventory, exact newly recorded origin,
canonical flock and the actual independent process/file census. It reserves
once before effects. The current quiescent no-sidecar v5 boundary replaces any
need to replay the spent checkpoint. It then uses the existing real source
backup/drill, P56, exclusive migration, target backup/drill and final proof.
Subsequent checks pin the new complete origin; ctime is not globally ignored.

Recovered completion is published only after final proof and exact removal of
the held original barrier. Missing/partial completion closes ordinary v6→v7;
a durable completion with lost delivery is result ambiguity, not permission to
rerun v5→v6. Ordinary v6→v7 requires the closed completed-variant evidence.

A distinct P56 schema binds the original qualification, spent intent, new Root
reconciliation and new Control reservation. The helper's distinct material
schema carries exactly sixteen origins: the four migration receipts, eight
backup files and those four authority receipts. Normal twelve-origin and old
fourteen-origin schemas remain strict. INITIAL validates actual current target
custody; HISTORICAL rederives the identical immutable sixteen-origin material
without treating live post-restore state as a new INITIAL state. Existing
maintenance selected-source binding continues through the original Root
qualification, preserving its v5 semantics separately from the v7 working proof.

Source tests use disposable SQLite databases and declared synthetic host,
principal, source-seal and inherited ancestor/assignment seams. They do not
establish current host eligibility or authorize installation, receipt issuance,
reservation, migration, service startup, readiness probes or acceptance Jobs.
The existing release owner and action-time controls retain those effects.
