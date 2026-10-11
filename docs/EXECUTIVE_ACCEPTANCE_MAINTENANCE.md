# Preserve an admitted root during host acceptance

The normal host acceptance requires an empty runtime. Do not run
`acceptance-retry` against a runtime containing an actual admitted COO root.
The opt-in maintenance owner instead preserves that runtime while the existing
acceptance executes its complete current-release proof.

The v1 route is bounded to one untouched strict-v2 queued root and one exact
requeued harmless proof whose latest Attempt is LOST with verified process
absence and whose unheld quota is ERROR. It does not dispatch the predecessor
proof, rewrite or resubmit the queued root, create another scheduler, or arm
the service.

## V1 preparation and proof

Use the ordinary source/review/release gates. With all control arms false and
both Executive services stopped (each exact `launchctl print` exit 113; loaded,
unknown, timed-out and failed observations refuse), run the reviewed successor's
`ops/executive_os/acceptance_maintenance.py` as root with:

- `--predecessor-sha`: the exact installed release and queued root base.
- `--successor-sha`: the reviewed merged release to install.
- `--root-job-id`: the untouched actual root to preserve.
- `--recovery-job-id` and `--recovery-attempt-id`: the exact prior proof pair.

The command validates the current runtime, records its complete semantic
snapshot and artifact inventory, makes a SQLite backup, and publishes one
root-sealed descriptor under
`/Library/Application Support/MastermindExecutive/acceptance-maintenance/<successor>`.
Raw snapshots and backups remain root-private. Preparation failures retain
private temporary evidence and do not publish a descriptor.

Install the exact reviewed successor through the existing installer, preserving
the runtime and all disarmed settings. Run the normal acceptance command with
the additional `--maintenance-descriptor-sha256` printed by preparation.
It verifies the exact prestate before starting services, recovers only the
permitted predecessor quota through the existing broker-observed CAS owner,
then runs fresh success and interruption/recovery proof jobs. The failed
predecessor job stays unchanged.

Maintenance checks the original rows and events byte-for-byte, permits only
the two new proof roots and their three terminal Attempts, validates both
capacity-recovery receipts, and derives quota fence changes from ordered
claim/adoption events. Existing artifacts are rechecked before and after the
existing backup/restore proof. Canary fixtures are reused only with their
existing identity/permission contract; their previous receipt is preserved.

The usual current-release acceptance summary remains required. Only complete
acceptance with preservation PASS creates `carry-forward.json`. The normal
arming owner additionally requires that exact receipt whenever a maintenance
descriptor exists. A partial run cannot pass the arm gate.

## V2: preserve a failed terminal dispatch across another release

A successor of an already accepted maintenance release may instead preserve
one queued strict-v2 root with exactly one direct FAILED planner and one FAILED
Attempt. The existing Runtime owner must validate its exact unresolved dispatch
marker and terminal claim. Provider/process identities and native harness
history must be absent; the existing control-owned assignment seal must prove
worker access revoked, a passing UID absence sweep, and unchanged directory
identity. All Attempts must be terminal and all quotas unheld. The proof quota
must already be AVAILABLE.

A later release may preserve the same failed planner after its exact dispatch
has been reconciled and the canonical `plan_terminal_adverse` block recorded.
This phase requires the original marker, one matching reconciliation and one
validated block in that order, plus the same terminal claim and cleanup proof.
The descriptor seals this complete effect history. An unresolved marker with
a block, reconciliation without a block, or malformed/extra history refuses.

Use the same preparation owner with predecessor, successor and root selectors,
plus `--carry-terminal-dispatch`; omit both recovery selectors. The predecessor
is the installed release. The root may retain an older base: the owner derives
that base from the predecessor's validated descriptor, acceptance summary and
PASS carry receipt, and seals all three digests. Callers cannot choose a frozen
base. The predecessor summary supplies the completed fixed proof template.

V2 grants no predecessor quota recovery. Acceptance revalidates the entire
semantic descriptor and original snapshot before creating its one-run marker,
skips the predecessor recovery RPC, and permits only the fresh interrupted
proof's recovery receipt. All existing rows, events and artifacts remain exact.
The normal installer, Gate B, readiness, acceptance summary and carry receipt
remain required. Neither preparation nor acceptance resolves the mission's
pending marker or dispatches its failed planner.

After successor PASS and normal arming, the existing COO's first cycle observes
the terminal claim through the read-only Runtime owner and records its exact
reconciliation. It selects no provider or supervisor, obtains no lease, and
creates no Attempt. The next cycle records the ordinary adverse-plan block;
normal selection then skips that root. Preserve both events and the failed
history. Any new acceptance operation uses a new explicit commission/intent
referencing the failed operation and the current host binding. It must not
resubmit the old intent or increase its immutable attempt limit.

Once blocked, the original root receives no historical binding compatibility.
The normal selector validates and skips its canonical block before checking
current dispatch policy. A subsequent capability-policy rotation can therefore
preserve terminal history without re-enabling that operation.

## V3: explicit, offline schema 5 to 6 maintenance

This path consumes the existing `upgrade_v5_to_v6` owner's completed operation.
It never invokes migration, starts a service, clears quarantine, restores a
database, issues an Attempt or publishes acceptance PASS. It is deliberately
limited to an **actually accepted v2 predecessor on exact schema 5**, carrying
the same terminal dispatch/root. It is not a generic schema-version exception.
An unstarted predecessor acceptance (including the retained exact-326c operation)
does not qualify and is not retired by preparing this source change.

The approved cutover plan must bind these phases before execution:

1. Reconcile the predecessor acceptance owner and consume its genuine acceptance
   summary and matching PASS carry. Quiesce through the existing service owner,
   with all arms and the worker harness closed. With that predecessor still
   selected in `control.json`, invoke the reviewed maintenance preparation owner
   with the predecessor/successor/root selectors, `--carry-terminal-dispatch`
   and `--seal-v5-source`. No recovery selectors are permitted. This phase must
   precede migration; existing 5-to-6 preflight/completion receipts refuse a
   retrospective baseline. The current database must be offline with no SQLite
   sidecars. Maintenance does not checkpoint or remove them; that remains an
   existing database-owner/quiescence prerequisite.
2. Retain the exclusive root-owned `schema-source-<successor>` evidence directory
   under `acceptance-maintenance`. Its immutable intent binds the accepted
   predecessor chain/root, exact database path/device/inode/bytes, full schema-5
   snapshot and backup/drill proof, configuration and old artifact inventory.
   It verifies the real predecessor proof delta against the predecessor's
   original sealed baseline. A summary alone, an unaccepted descriptor, or
   unchanged-looking rows cannot replace PASS. The source baseline is never
   overwritten or promoted into a target baseline.
3. Install/seal the reviewed target through the existing owner, preserving the
   qualified namespace, principals and disarmed configuration. Only
   `proof_base_sha` may change in the bound control configuration; any other
   change needs an explicit source/plan reconciliation, not a whitelist override.
   The permitted database principal then runs the existing installed-release
   migration owner once, explicitly from version 5. Maintenance does not supply
   a privilege wrapper, migration implementation, lock or retry path.
4. Consume that same operation's exact owner-return `operation_id`,
   `preflight_receipt_digest` and `completion_receipt_digest`. With the successor
   selected and services still stopped, invoke maintenance with the same
   selectors and `--carry-terminal-dispatch`, plus
   `--schema-transition-operation`, `--migration-preflight-sha256` and
   `--migration-completion-sha256`. These digests use the migration owner's
   canonical JSON encoding. No completion means no target descriptor.
5. Consumption captures private control-owned receipts and both backup/manifest
   pairs through stable, no-follow reads into exclusive root-owned evidence;
   original ownership/permissions remain unchanged. The existing backup owner
   verifies both copies, exact known schema/migration checksums and restore
   drills. Completion must bind preflight, operation, release, namespace,
   source/target schemas, full-v4 history and the migration-5 receipt. Every
   pre-existing table row and migration receipt remains exact; the only history
   addition is M6. No changed root, event, lease, grant, quota or arbitrary
   schema object is admitted. The actual target must match the completed
   operation and verified target backup.
6. Only then prepare a distinct, root-sealed **v3 target acceptance baseline**.
   Its descriptor binds the retained transition-chain digest. It also retains
   every v2 terminal-dispatch/assignment/PASS requirement. Acceptance rechecks
   the immutable source chain, verified backup/drill evidence and target
   namespace/baseline before creating its ordinary one-run marker. Normal
   Runtime reads can materialize an empty WAL/SHM pair; acceptance compares the
   full logical snapshot including WAL. Raw offline evidence capture requires
   no sidecars and uses immutable reads so it does not create them.
7. Run the existing separate successor acceptance with the printed descriptor
   digest. V3 grants no predecessor recovery, uses the same two fresh proof
   jobs/three terminal Attempts as v2, and retains strict target-schema/history
   equality throughout acceptance. Only the existing successful acceptance
   owner can publish the matching summary and carry-forward PASS. Migration
   completion is not that PASS or original-parent/live-provider acceptance.

Ordinary v1/v2 preservation remains strict. An ordinary v2 preparation or
acceptance entry cannot silently rebaseline across a changed predecessor schema
or migration history; it must use the explicit verified transition. Unknown
versions, missing/foreign/partial receipts, replaced database identity, altered
backups or old history, and mismatched predecessor evidence all refuse.

Consumption is single-use. Partial evidence directories are retained, never
deleted or overwritten by retry. If migration committed but completion is
uncertain, preserve the owner's quarantine/barrier and all evidence, reconcile
the same operation, and do not restart the v5 binary, replay migration, copy a
backup over the runtime or synthesize an acceptance receipt. This source contract
does not itself authorize an installed cutover or resolve any human-only gate.

## Continuing the preserved root

After the normal arming ceremony, only the descriptor's exact root may retain
its qualified original source revision (transitively derived for v2). Its admission Event, immutable Job identity,
model, profile, policy, routing, and harness identity must match.

The historical preserved root was admitted while the operator harness was
closed. Full arming later enables global operator capacity. Fresh roots may also
use the [sealed coexistence path](EXECUTIVE_CEO_AUTONOMY_COEXISTENCE.md). The preserved root keeps its original
`operator_harness_armed=false` binding and uses the existing sealed supervisor;
maintenance never promotes it to an operator profile. Ordinary current roots
keep their normal behavior.

If the admitted deterministic workspace is still absent, the existing
serialized COO/service owner materializes it with the existing credentialless
clone allocator, pinned to the preserved base, branch, and path. Existing
workspace checks and direct-child constraints remain mandatory. No commission
source acquisition is inferred from this compatibility receipt.

## Failure boundary

A maintenance proof is one explicit run. It never automatically retries,
archives the runtime, rolls back history, or discards a partial workspace.
Failure keeps the runtime, root-sealed marker, proof receipts, and artifacts
for foreground reconciliation. Do not remove the marker and rerun against
changed state, or use clean-runtime retry as a substitute.

Any later restore must use the existing verified offline backup/restore owner,
after reconciling process absence, the exact maintenance delta, and preservation
of the admitted root. Source tests and maintenance receipts do not prove an
actual SUMMON result, terminal return, or consumption by the original parent.
Those remain separate acceptance evidence.
