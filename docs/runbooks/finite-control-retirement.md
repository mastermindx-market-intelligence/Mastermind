# Retire the historical finite Control selection

`finite-control-retire` is an authority-shrinking action of the existing
autonomy configuration owner. It removes the historical `minimax-finite-01`
execution selection from Control, preserves its exact protected definition as
inactive provenance, and leaves its profiles, enrollment, accounts, groups,
proof files and Runtime Jobs untouched.

The historical foreground qualification remains fixed to its original request.
This action does not broaden that qualification, install a paid source, create a
Worker or quota class, admit capacity, arm a service, or submit a Job.

## Required state

Use the action from the actually installed successor source after its normal
acceptance/carry has completed and while full autonomy, the operator harness,
foreground mode and CEO submit are disarmed. Control and the primary Worker
must be stopped, Runtime must satisfy its existing quiescence check, and the
fixed finite service must be unloaded with no live finite-worker process.

The command requires the actual current raw Control SHA-256. It rereads the
protected Control/Worker, the exact fixed finite bindings and worker definition,
and their custody before each publication boundary. If `native_capacity_v2` is
present, it must join the same finite worker's retained enrollment and source
proof; an unrelated native stanza cannot be removed. Historical finite service
source is retained as history, not reclassified as the installed successor.

No existing global transaction may be present at initial admission. The normal
owner claims one original `FINITE_CONTROL_RETIRE` marker after its root,
installed-source, acceptance, stopped, unarmed and Runtime predicates. Before
any candidate/config publication it verifies that exact held marker and invokes
the existing fixed-Control-UID quiescer, followed immediately by the unchanged
strict service-UID gate. It repeats this bounded composition after expensive
validation, including the actual candidate validation as the Control user.
Worker ambient-process rules remain unchanged. There is no caller-selected UID,
PID, signal, command, timeout or transaction-existence override.

## Normal commands

The installation owner supplies `SOURCE_SHA`, `RELEASE` and `CONTROL_SHA256`
from actual installed/read-only observations. They are not sample identities.

```bash
sudo /bin/bash "$RELEASE/ops/executive_os/autonomy-control.sh" \
  finite-control-retire \
  --expected-sha "$SOURCE_SHA" \
  --expected-control-sha256 "$CONTROL_SHA256"
```

Retain the actual stdout, stderr and exit status. Success is
`finite_control_retired`, state `UNARMED`, status `FINITE_CONTROL_RETIRED`, with
the actual original transaction ID. The new `retired_finite_composition` field
contains no execution switch and cannot coexist with active finite fields.
The existing finite-stage action cannot reactivate it.

The root-only, fixed config artifacts are:

- `finite-control-retirement-predecessor-v1.json`: exact prior Control, Worker
  and disarm-receipt bytes, original transaction and source. Its hash is bound
  into inactive Control provenance. This file is exclusively created and never
  overwritten.
- `finite-control-retirement-quiescence-v1.json`: bounded original-owner
  observations. Each cleanup is retained as `STARTED` before signaling, then
  records actual signaled PIDs and strict-gate success, or `UNKNOWN` and the
  actual refusal. Unfinished/unknown cleanup is not converted into success or
  automatically attempted again.

Both artifacts use root-only `0400` custody. The quiescence journal changes only
under the held original retirement marker; neither artifact grants execution
authority. Existing disarm authority, readiness and timestamps are preserved;
only its three normal Control/transaction correlation fields change. An absent
disarm receipt is not synthesized.

## Reconcile the original operation

On uncertainty, preserve the original journal and files. Do not rerun retirement,
delete its predecessor, edit Control, or allocate another operation.

```bash
sudo /bin/bash "$RELEASE/ops/executive_os/autonomy-control.sh" \
  finite-control-retire-reconcile --expected-sha "$SOURCE_SHA"
```

Reconciliation only settles the same exact already-published Control, unchanged
Worker and paired disarm receipt. A missing target or paired receipt remains
unknown; the command never replays their writes. A retained `STARTED`/`UNKNOWN`
cleanup refuses before another signal. If the normal global marker is already
gone, reconciliation is read-only under the existing config-directory mutex and
also requires the actual completed Control observation. Later config changes
cannot masquerade as the original retirement postimage.

Acceptance continues to derive the finite supplementary group by joining this
inactive provenance to the actual root-only predecessor and the unchanged
protected worker/binding definitions. It grants no attended placement. All
other group-set checks retain their original strict behavior.

## Follow-on work remains separate

After retirement, the existing `stage-paid` owner may publish a genuinely
qualified canonical paid source. Actual host/account/capacity identity,
initialization, readiness, quota, Worker registration and placement admission
remain requirements of their existing owners. Without eligible work placements,
ordinary foreground operator mode still stops after its validated plan; that
does not prove the H1 hierarchy.

The separate `native_research_only` App path enters the direct-native owner
before generic COO attended qualification. It requires the real App principal,
READY backend, full foreground/CEO arms and current autonomy. It does not use
this historical selector, and its single direct-native Job is not an H1 Fabric
child proof.
