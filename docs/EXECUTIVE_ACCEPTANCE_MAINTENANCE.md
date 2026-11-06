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

## Accepted V2/schema 5 to current schema 7

An ordinary V2 preparation cannot adopt a new schema or migration history by
sealing a replacement baseline. Both preparation and admission compare the
accepted predecessor's original schema and migration rows, including their
JSON types. A schema transition uses the explicit route below.

This route starts from an **actually accepted V2 release on schema 5**. It
keeps three distinct states:

| State | Immutable evidence |
| --- | --- |
| Accepted predecessor | Its original V2 baseline, backup, descriptor, PASS summary and carry |
| Post-acceptance schema-5 source | A separate seal including that predecessor's two completed proof jobs |
| New schema-7 working preparation | The exact C67 target, a fresh backup, descriptor and migration evidence |

The new preparation schema is
`mastermind.executive_acceptance_maintenance/accepted_v2_v5_to_v7_v1`.
The schema-source adapter is subordinate to Maintenance. It does not read a
second copy of migration receipts or run migrations. The existing
`schema_upgrade_evidence` owner authenticates P56/C56/P67/C67, their backup,
verification and restore-drill chains, the exact executor, and the original
database identity.

### Cutover order

Use this sequence only within an authorized host acceptance operation. An
unknown prior operation, pending quarantine, or denied host action must be
reconciled through its existing owner before any cutover action.

1. Qualify the actually accepted V2 predecessor, untouched queued root and
   terminal dispatch history. All arms and the worker harness must be closed,
   both services stopped, all Attempts terminal and all quotas unheld. The
   canonical service admission lock must be available. The authoritative
   schema-5 database must have no WAL, SHM or journal sidecars. No P56, C56, P67
   or C67 receipt may already exist.
2. While that predecessor is still the selected installed release, run the
   reviewed, staged successor's Maintenance entry point with the existing
   predecessor, successor and root selectors, `--carry-terminal-dispatch`,
   and **`--seal-accepted-v2-v5-source`**. Omit both recovery selectors and all
   other transition selectors. The staged successor must pass the existing
   exact-release proof. Record the returned `accepted_v2_source_sha256`.
3. Install the exact reviewed successor through the existing installer and
   normal control-config promotion. Preserve all disarmed settings and the
   original Macro source coordinate. Under the existing migration owner's
   separately authorized procedure, complete the closed schema **5→6→7**
   chain exactly once with that same successor as executor.
4. Run the same Maintenance entry point with the same predecessor, successor
   and root selectors, `--carry-terminal-dispatch`,
   **`--accepted-v2-v5-to-v7`**, and
   **`--accepted-v2-source-sha256 <recorded-source-digest>`**. Omit the source
   sealing flag and both recovery selectors. This authenticates the retained
   source against the actual P56 identity and snapshot, requires the source
   seal to precede P56, verifies the complete canonical chain, and publishes
   a separate schema-7 working preparation.
5. Run the existing current-release acceptance with its printed
   `--maintenance-descriptor-sha256`. Admission rechecks the exact INITIAL
   target under the canonical service lock and creates one exclusive run
   marker. It grants no predecessor recovery. The existing proof jobs,
   backup/verification/drill/restore sequence, closed PASS summary and first
   finish remain required.

The source seal is stored under
`acceptance-maintenance/schema-source-<successor>`. Its closed namespace is
`preparing.json`, `intent.json`, `baseline.json`, `prestate.sqlite3`,
`inventory.json`, `prior-secret-canary.json`, and `source-control.json`.
The intent pins the accepted ancestry, actual source database path/device/
inode/size/hash, full schema-5 content, artifacts, prior canary and exact raw
control configuration. It does not overwrite the accepted predecessor.
The working preparation remains at `acceptance-maintenance/<successor>`.

The source and working commands hold their accepted ancestry, configuration,
database, canary and namespace identities through publication. A source
whose ordinary logical rows happen to match is insufficient: the canonical
P56 source identity and full content must also match. A source seal created
after migration cannot repair a missing pre-migration seal. Historical DATA
cannot authorize a fresh descriptor or run marker.

### Finish, future carry and failure

Normal acceptance may restore the live database and restart the Service.
Finish uses the actual acceptance backup and retained HISTORICAL migration
evidence; it does not require the live inode to remain the initial migration
target, demand offline sidecar absence, or take the running Service's lock.
The working baseline must still be the original C67 target. Future carry
reopens the same canonical history and accepted-source provenance, even when
later unrelated rows exist in the current live database.

A failure retains its exact evidence. Existing source seals, source partials,
working partials, descriptors and run markers are never silently replaced or
removed. If restore evidence is sealed but a later source check refuses,
there is no carry PASS and another finish refuses the existing partial
operation. Do not remove that evidence, repeat the old migration, restart an
old schema binary, or fabricate PREPROOF ancestry to continue.

Existing PREPROOF and prepared-successor routes keep their own selectors,
closed material forms and ancestry checks. This accepted-V2 route accepts
only the normal canonical migration chain; it does not convert recovered
pre-census variants or prepared-successor evidence into accepted provenance.
Source qualification and merge establish the implementation only. Installed
host acceptance, original-parent consumption, SUMMON and terminal return
remain separate evidence.

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
