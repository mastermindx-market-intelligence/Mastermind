# Preserve an admitted root during host acceptance

The normal host acceptance requires an empty runtime. Do not run
`acceptance-retry` against a runtime containing an actual admitted COO root.
The opt-in maintenance owner instead preserves that runtime while the existing
acceptance executes its complete current-release proof.

This route is bounded to one untouched strict-v2 queued root and one exact
requeued harmless proof whose latest Attempt is LOST with verified process
absence and whose unheld quota is ERROR. It does not dispatch the predecessor
proof, rewrite or resubmit the queued root, create another scheduler, or arm
the service.

## Preparation and proof

Use the ordinary source/review/release gates. With all control arms false and
both Executive services stopped, run the reviewed successor's
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

## Continuing the preserved root

After the normal arming ceremony, only the descriptor's exact root may retain
its predecessor source revision. Its admission Event, immutable Job identity,
model, profile, policy, routing, and harness identity must match.

CEO-submit admits while the operator harness is closed. Full arming later
enables global operator capacity. The preserved root keeps its original
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
