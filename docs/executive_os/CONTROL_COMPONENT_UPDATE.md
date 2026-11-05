# Control component update (configuration-preserving Control source upgrade)

**Kind:** owned, transactional Control source update. **Owner:** the ONE existing
`AUTONOMY_TRANSACTION` in `ops/executive_os/autonomy_control.py`. **Effect:** the
installed Control configuration, the Control plist, the already-inert Worker
plist, the existing disarmed authority receipt and the nonsecret control
observation. Nothing else.

This is the Control half of the existing MCP component update. The MCP
component update already republishes the OS UI/gateway while preserving the
installed settings; it does **not** update the Control BYOK handler/reader
implementation, because a full install regenerates the configuration and stops
unrelated services. This surface performs the Control source upgrade without
regenerating the configuration and without stopping anything but the Control
service itself.

## Staging

The target release must be staged and sealed first, and the installer-owned
administrative checkout that backs the Control configuration's
`proof_source_repository` must exist for the same commit:

```
sudo /bin/bash <installed-release>/ops/executive_os/install.sh \
  --source-repo <repo> --expected-sha <target-40-hex> \
  --operator-user <name> --stage-admin-checkout-only
```

`--stage-admin-checkout-only` seals and publishes the target release and then
prepares `/var/db/mastermind-executive/control/admin-checkout/<target-40-hex>`.
It changes no service, no configuration, no receipt and no selection, and it
returns before the installer's mutation boundary. An occupied target that is
not already the exact expected checkout owned by the control principal refuses
untouched; this preparation never recursively repairs another owner's tree.
`--stage-release-only` keeps its existing behaviour and still returns before
the administrative checkout is prepared.

## Plan, apply, reconcile

The three verbs are dispatched only by the `service-control.sh` of the TARGET
release, under root:

```
sudo /bin/bash /Library/Application\ Support/MastermindExecutive/releases/<target-40-hex>/ops/executive_os/service-control.sh \
  plan-control-component --expected-sha <target-40-hex>
sudo /bin/bash .../service-control.sh \
  apply-control-component --expected-sha <target-40-hex> --plan-sha256 <plan-64-hex>
sudo /bin/bash .../service-control.sh \
  reconcile-control-component --expected-sha <target-40-hex>
```

`plan` is read-only and prints the closed plan document with its digest. The
plan carries only allowed hashes, source identifiers, precondition states and
the closed effect list: no installed configuration, token or credential
content is ever placed in the plan, in any argv or in any caller-readable
staging. `apply` recompiles the plan from the live installed state and refuses
on any digest mismatch. `reconcile` proves one interrupted update to its exact
retained postimages; it never republishes a target, never re-dispatches a
recorded bootout or bootstrap and never rolls back.

## Preconditions the plan proves

Both release seals, the qualified pinned interpreter, the target administrative
checkout, the compatible Control schema, a matching prior Control
configuration and both installed plists, the absence of an incumbent global
transaction, the validity and DISARMED state of the existing authority
receipt, the incumbent owner's runtime quiescence, and a Worker that is already
absent AND disabled. A live or unknown Worker is a pre-effect refusal: it is
never stopped or disarmed to fit. An armed authority receipt is refused too:
the bounded first path requires existing DISARMED authority, because an armed
receipt cannot survive a source change without an authority migration, and
this operation never migrates or refreshes authority.

The pinned interpreter is qualified by the installed peer's own runtime owner
(`installed_peer._verify_python_runtime`), which covers the executable hashes,
the pinned version, the code signature and the ancestor closure. Its
observation and its budget are retained, and the SAME budget rechecks the
runtime (`installed_peer._recheck_python_runtime`) immediately before the
first effect.

The administrative checkout is read through the ONE fixed Control-principal
Git owner (`sudo -u <control principal> git ...`), exactly as the installer
reads it: Git refuses a repository owned by another principal, and this
operation never grants a `safe.directory` or any other trust exception. Its
ownership and its reachable object closure are proved by the installer's own
administrative-checkout qualifiers.

`ceo_ingress_app_armed` is UID458 transport admission, not CEO-submit
authority, and is not consulted as authority.

## The two closed input states

The installed state selects exactly one of two closed modes, and the mode is
bound in both the plan and the sealed component marker:

* **live** — the Control service is registered and enabled. The Worker must
  already be absent AND disabled.
* **offline** — the Control service is genuinely absent AND explicitly
  disabled, and the Worker is absent AND disabled.

Every other combination — unknown, mixed or mismatched — refuses before any
effect. In particular a Control that is absent but not explicitly disabled,
and a Control that is registered while explicitly disabled, match neither
mode. Nothing is ever stopped or disarmed to fit a mode.

The offline mode exists because the incumbent `service-control.sh stop`
disables and boots out the Control before the Worker and leaves the Control
disabled. It is the smallest legitimate first cutover: the parent runs the
incumbent stop after its own active-work and custody observations, and this
operation then takes over the Control boundary alone.

## What changes, and what does not

The Control configuration changes `proof_base_sha` and the installer-owned
`proof_source_repository` only; the installed Macro root is preserved and never
exported. The Control plist and the already-inert Worker plist change their
target release substitutions only. The existing disarmed authority receipt is
correlated through the incumbent validator: its source release, configuration
digest correlation and transaction label move, and no authority, state,
evidence, policy, scope or timestamp moves. The Worker configuration and the
whole Worker runtime state are preserved; the Worker daemon is never started,
stopped, enabled or disarmed. No Relay, MCP, Backup or privileged-broker
action is taken, and the original publish-os-gateway receipt and its history
are excluded.

## Receipt preimages

The plan and the sealed marker bind the PRESENCE and the exact raw-byte
SHA-256 preimage of every receipt this operation may replace: the authority
receipt, the CEO-submit receipt and the component receipt itself. The
archived preimage is the EXACT bytes that were on disk, never a re-encoded
parse of them. Immediately before each replacement the receipt on disk must
still be exactly the sealed prior bytes; a receipt that moved after the seal is
an unbound later receipt and is never overwritten.

## Effect order

**Live mode:** one Control bootout (a source switch cannot be kickstart-only:
a kickstart would reuse the already-loaded job definition and keep running the
prior release), then the absence proof and the stopped-boundary recheck, then
the bounded target publications and the validated receipt correlations, then
one Control bootstrap of the verified new plist, then the wrapper-attested
consumed-config proof (`_control_config_probe` /
`prove_control_admission_bound`: the exact live pid, the boot identity, the
target release and the exact consumed configuration digest), then the control
observation published by the same held owner, then the marker is closed.

**Offline mode:** there is NO bootout to dispatch and NO bootout to record.
The Control absence is proved by observation and recorded as
`CONTROL_ABSENT_PROVEN`. The publications, the receipt correlations and the
target source/PID/boot/consumed-config proof are identical. The Control is
then enabled exactly once (the incumbent stop left it disabled), the disabled
override is read back, and the Control is bootstrapped exactly once.

**The stopped boundary** proves the incumbent Runtime quiescence, the fixed
service-UID census through the incumbent owner, and the launchd absence and
disabled override of both boundaries. The census observes only; it never sweeps
or signals, and it accepts no caller-selected UID, PID or timeout.

**Under the claimed transaction** every sealed preimage is rechecked — both
installed plists, the installed configuration, all three receipt preimages and
both launchd disabled preimages — together with the target source (the sealed
target release and the administrative checkout that backs it), the Runtime
quiescence, the fixed absence of both boundaries and the fixed service-UID
custody. The retained interpreter qualification is rechecked under the SAME
budget it was observed under, before the first effect; the recheck follows the
marker claim directly, so the budget it spends is the budget the observation
opened.

The Worker is never restored by this operation. After the component closes its
transaction, the parent restores the original loaded and enabled Worker
separately, with the incumbent `service-control.sh start`: the Worker first,
and an already-running Control gets a kickstart WITHOUT `-k`. That restoration
is outside this component.

## Interruption and reconciliation

The preimages (both installed plists and all three receipts) are sealed into
the private transaction generation before the canonical marker path can become
visible. An interrupted action retains the original transaction and its
preimages; there is no automatic rollback.

A refusal raised AFTER the transaction marker was claimed is never reported as
a zero-effect refusal: the original transaction is retained, the phase that was
still incomplete is named, and the outcome is `INCOMPLETE`. Nothing is rolled
back and nothing is replayed.

`reconcile` freshly qualifies the target release seal, the administrative
checkout, the runtime, the installed configuration and the lifecycle, compares
the retained component receipt against the byte-identical document the
original operation owed, and completes the marker only when all of them hold.
It never republishes a target, never re-dispatches a recorded bootout, enable
or bootstrap, and never rolls back.
