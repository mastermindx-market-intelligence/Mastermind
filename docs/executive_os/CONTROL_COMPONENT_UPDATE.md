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
`proof_source_repository` must exist for the same commit.

`--stage-admin-checkout-only` runs `install.sh` **from the same accepted
source checkout** that is passed as `--source-repo`, so the script that
stages the release and the source it stages are one checkout. It also needs
the pinned interpreter coordinates, because the installer refuses to run
without them:

```
cd <accepted-source-checkout>
sudo /bin/bash ./ops/executive_os/install.sh \
  --source-repo <accepted-source-checkout> --expected-sha <target-40-hex> \
  --operator-user <name> \
  --python-binary /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
  --python-runtime-root /Library/Frameworks/Python.framework/Versions/3.12 \
  --stage-admin-checkout-only
```

`--stage-admin-checkout-only` seals and publishes the target release and then
prepares `/var/db/mastermind-executive/control/admin-checkout/<target-40-hex>`.
It changes no service, no configuration, no receipt and no selection, and it
returns before the installer's mutation boundary. An occupied target that is
not already the exact expected checkout owned by the control principal refuses
untouched; this preparation never recursively repairs another owner's tree.
`--stage-release-only` keeps its existing behaviour and still returns before
the administrative checkout is prepared.

`--stage-release-only` and `--stage-admin-checkout-only` are two different
staging intents and are **never combined**: one stages the release tree, the
other prepares the administrative checkout, and a single invocation asks for
both at once.

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

One receipt is read ONCE. The semantic validation, the archived preimage, the
presence flag and the correlation all name the SAME qualified raw bytes, so a
receipt that moves between the validation and the capture can never become an
unjoined archive: the compare-and-swap refuses the moved receipt instead.

Presence is EXPLICIT. It is proven by an absent file, never inferred from the
byte length of an archived preimage, so an empty receipt stays present.

The AUTHORITY receipt and the CEO-SUBMIT receipt are semantically validated:
one that is present but malformed, empty, unreadable or misqualified is
REFUSED before any marker or effect. It is never read as an absent receipt:
the absent receipt and the unreadable one lead to different correlations.

This operation's OWN prior receipt is different, and the difference is
deliberate. It is the output of an EARLIER component update, so it is bound
only by its presence and its exact raw bytes: it is never parsed as a
receipt, and it may legitimately be EMPTY and still PRESENT. Only a proven
absence is absent. It is replaced by an exact-byte compare-and-swap, never
by a re-serialisation of a parse.

## Effect order

The plan's `effects` list is a digest-bound SEQUENCE: it names the exact
order in which the approved effects happen. The two installed plists are
retargeted first, the Control configuration is replaced next, the receipt
correlations follow, and only then is the Control boundary changed.

**Live mode:** one Control bootout (a source switch cannot be kickstart-only:
a kickstart would reuse the already-loaded job definition and keep running the
prior release), then the absence proof and the stopped-boundary recheck, then
the bounded target publications — the Control plist, the Worker plist and the
Control configuration — and the validated receipt correlations, then one
Control bootstrap of the verified new plist, then the wrapper-attested
consumed-config proof (`_control_config_probe` /
`prove_control_admission_bound`: the exact live pid, the boot identity, the
target release and the exact consumed configuration digest), then the control
observation published by the same held owner, then the marker is closed.

**Offline mode:** there is NO bootout to dispatch and NO bootout to record.
The Control absence is proved by observation and recorded as
`CONTROL_ABSENT_PROVEN`. The publications, the receipt correlations and the
target source/PID/boot/consumed-config proof are identical. The Control is
then enabled exactly once (the incumbent stop left it disabled), the disabled
override is read back, and the Control is bootstrapped exactly once. The
enable therefore happens AFTER the publications, immediately before the single
bootstrap.

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

Both ACTUAL configurations are re-read through the incumbent qualified
configuration owner. The retained manifest is never a substitute for the
installed Worker configuration: a Worker that drifted after the interruption
is refused before any publication, lifecycle effect or closeout.

Once the transaction owner is claimed, EVERY qualification or read failure is
an `INCOMPLETE` or `EFFECT_UNKNOWN` outcome. The original marker and its
preimages are retained and the phase that was still incomplete is named; a
claimed transaction is never reported as a zero-effect refusal.

The retained manifest read, the component identity checks, the qualified
transaction identity and the delegated retained-postimage proof are ONE
guarded region that begins immediately after the claim. A malformed or
unexpected retained manifest therefore leaves the ORIGINAL operation
uncertain (`EFFECT_UNKNOWN`) instead of escaping as a generic refusal; it is
never reported as an operation that had no effect. Until the transaction
identity is qualified every unexpected error is `EFFECT_UNKNOWN`; once it is
qualified, a component refusal is the `INCOMPLETE` classification and names
the phase that was still incomplete.

The phase the component publication records, `CONTROL_COMPONENT_PUBLICATION_STARTED`,
is a RECOVERABLE phase. An interruption AFTER the publication is closed by
reading the published observation back EXACTLY: the retained phase is not
admissible for another publication, so the observation is never written twice
and no lifecycle effect is dispatched.
