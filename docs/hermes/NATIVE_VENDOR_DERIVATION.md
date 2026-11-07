# Native Hermes vendor derivation

The existing Executive release recipe can select one named repair of the
immutable Hermes vendor: `computer_env_guard`. This connects the qualified
two-file repair to dependency preparation, the role installer, the existing
install receipt and native launch validation. It grants no computer-use tools
and starts no driver or service.

## Exact selection

The optional `vendor_derivation` member of an existing native gateway recipe is
closed. Its values are fixed except for the owner-approved pristine source path:

```json
{
  "vendor_derivation": {
    "kind": "computer_env_guard",
    "base_sha": "1c0cd667746d3395fe9e1b6c74f8f85952486f18",
    "patch_sha256": "d17af87e60a1f92a52ef446ad393ce2841c876a28e2ae0580bc7e6db09d6721f",
    "source_root": "/opt/hermes/pristine-selected-base"
  }
}
```

This is an illustrative recipe fragment, not an enrolled host path. The outer
`vendor_root` names a separate destination and must remain the first
`import_roots` entry. Source, destination, other import roots, inventory and
first-party release must satisfy their existing path and custody constraints.
All existing native recipe versions and their session/Executive consumer
semantics remain intact. A missing derivation keeps the existing pristine
installation behavior; null, unknown variants and a general dirty-checkout
override are rejected.

The patch, manifest and MIT notice are read from the fixed held first-party
`integrations/hermes_qualification/computer_env_guard` package. The actual patch
operation reuses its `prepare_sources()` verifier. The two admitted postimages
are fixed by the source contract:

| Relative path | SHA-256 after repair |
| --- | --- |
| `tools/computer_use/permissions.py` | `c1b1f7b1de10fc14ff2892ec8b0dd7ca2c1976ef76a0d6884e93577caeea8d0d` |
| `tools/computer_use/cua_backend.py` | `b106ce6b1086a932648c141a517821fd503a54b75d52e7cf5b127c94df1de78f` |

## Preparation and source identity

The incumbent `prepare-hermes-dependencies` root transaction now prepares a
selected derivation before calling its existing `prepare_inventory()` receiver.
The expected inventory digest and size remain independently frozen inputs.
They are never replaced with a digest learned from the candidate being accepted.
Before creating an artifact, the expected complete derived namespace is computed
from the qualified pristine snapshot and exact postimages and compared with
that frozen commitment, including every other selected import root.

The source must be a complete, standalone, root-owned Git checkout. Its actual
regular files, directories, executable bits and tracked blob identities must
match the selected commit. Ignored files, extra empty directories, symlinks,
hardlinks, inaccessible custody, worktree/alternate-object indirection and
changes hidden by `assume-unchanged` or `skip-worktree` are refused. Git status
is not used as the proof of tracked bytes. Git operations use a closed command
environment with replacement objects, lazy fetch and optional index writes
disabled.

A private staging directory receives the proven source bytes and the two fixed
postimages. Git metadata is preserved as part of the frozen complete namespace,
so the native `code_sha` still identifies the upstream base. Files and directory
entries are flushed before an OS-level exclusive rename publishes the new
artifact. Publication cannot replace even an empty racing destination. Existing
destinations are read and adopted only if the repair and complete frozen
inventory match; no chmod, repair, patch reapplication or overwrite occurs.
An error after publication leaves that same destination for reconciliation.

The source module retains the existing member, file, total-byte, ACL, ownership
and link limits. A qualifying artifact must fit those limits. The selected
upstream tree has been inspected: all 20,971 tracked members are regular Git
blobs. That census is not a qualification of any installed host checkout or
its Git metadata.

## Installation and launch

The native installer accepts a derived vendor only through the existing held
release owner. Its selected role/state recipe must exactly match the frozen
installation input. `NativeSourceClosure` qualifies the complete dependency
inventory; the derivation verifier separately checks the upstream tree and the
two postimages. The original pristine path retains its clean-checkout check.

The existing `install-receipt.json` records `native_vendor_derivation`: kind,
base SHA, patch digest, both postimage digests, MIT-notice digest and vendor path.
The receipt still contains the original complete `native_gateway` recipe.
Writing a selected derivation receipt without its qualification is refused.
Before selection the installer rechecks the held source and closure.

`_NativeGatewayLaunch` verifies the same source transformation under its held
owner and compares that evidence with the installed receipt before launching.
The base SHA alone is never treated as proof that the repair is installed. The
existing native readiness, process-image, receipt, role, profile and source
checks continue to apply. No additional readiness store or runtime authority is
introduced.

## Rollback

A native role rollback checks the current and previous complete native recipe,
derivation, launcher/adapter digests, profile digest and actual first-party
launcher target before moving `current`. A different tuple returns
`NATIVE_ROLLBACK_REQUIRES_MATCHING_RELEASE_RECIPE` without switching the role.
The original Executive release owner must restore the matching release,
inventory, role receipt and unit selection together. A compatible role rollback
reports its symlink/manifest result; it does not claim that a service restarted
or passed runtime acceptance. Artifacts are never reverse-patched.

## Verification and production boundary

`tests/test_hermes_vendor_derivation.py` exercises real Git object membership,
hidden index flags, ignored files, mode drift, complete frozen inventory,
OS-level no-replace publication, lost acknowledgement and original-destination
reconciliation. It also enters the actual installer qualification, writes the
actual role receipt, and exercises the actual launch receipt comparison and
rollback guard. Custody/ACL fixtures are explicit doubles; these tests do not
establish root ownership or service isolation on a production host.

Production still requires the real approved source/destination/inventory
inputs, the original root enrollment transaction, and installed-role readback.
The original Ubuntu1 C26 reconciliation remains gated on restoring its original
authorized root/admin connection. No alternate connection is authorized to
replay its denied journal read. M2's attended installation is outside this Linux
recipe and must retain its own installation owner. The managed role's current
tool allowlist continues to refuse computer use until separately enrolled and
proved.
