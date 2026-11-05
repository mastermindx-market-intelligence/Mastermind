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

`ceo_ingress_app_armed` is UID458 transport admission, not CEO-submit
authority, and is not consulted as authority.

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

## Effect order

One Control bootout (a source switch cannot be kickstart-only: a kickstart
would reuse the already-loaded job definition and keep running the prior
release), then the absence proof and the quiescence/Worker recheck, then the
bounded target publications and the validated receipt correlations, then one
Control bootstrap of the verified new plist, then the wrapper-attested
consumed-config proof (`_control_config_probe` /
`prove_control_admission_bound`: the exact live pid, the boot identity, the
target release and the exact consumed configuration digest), then the control
observation published by the same held owner, then the marker is closed.

The preimages (both installed plists and both receipts) are sealed into the
private transaction generation before the canonical marker path can become
visible. An interrupted action retains the original transaction and its
preimages; there is no automatic rollback.
