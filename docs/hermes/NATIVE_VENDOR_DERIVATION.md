# Native Hermes vendor derivation

The existing Executive release recipe can select one of two fixed repairs of
the immutable Hermes vendor: `computer_env_guard` or `diagnostic_privacy`. Each
connects its qualified two-file repair to dependency preparation, the role
installer, the existing install receipt and native launch validation. These
source transformations grant no tools and start no driver or service.

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
Existing v1 and selected-child consumer behavior stays intact. An optional
context-v2 consumer requires `diagnostic_privacy`; its absence is refused even
during structural bootstrap, before held semantic qualification. Other recipes
retain the existing pristine path when no derivation is selected. Null, unknown
variants, cross-variant patch identities, combined repairs and a general
dirty-checkout override are rejected.

The patch, manifest and MIT notice are read from the fixed held first-party
`integrations/hermes_qualification/computer_env_guard` package. The actual patch
operation reuses its `prepare_sources()` verifier. The two admitted postimages
are fixed by the source contract:

| Relative path | SHA-256 after repair |
| --- | --- |
| `tools/computer_use/permissions.py` | `c1b1f7b1de10fc14ff2892ec8b0dd7ca2c1976ef76a0d6884e93577caeea8d0d` |
| `tools/computer_use/cua_backend.py` | `b106ce6b1086a932648c141a517821fd503a54b75d52e7cf5b127c94df1de78f` |

### Diagnostic privacy selection

The context-v2 consumer selects kind `diagnostic_privacy`, the same upstream
base, and patch SHA-256
`ded504ad2d660f14c89527ec74593fcc459485666fbb0994bb92f7b02c878bce`.
Its fixed held package is
`integrations/hermes_qualification/diagnostic_privacy`. The six-field receipt
shape and full inventory/custody owner are the same as for the original repair.

| Relative path | SHA-256 after repair |
| --- | --- |
| `agent/agent_init.py` | `eea2233a2b6cd536fca891dc3436a8dd55c1e69f0ad54a5aa6cf8fa58a3c7e08` |
| `agent/memory_caller_scope.py` | `e8924a95d756f0235071a0276763bffdaa7fdf5cef68eda589f7f46939a872a6` |

The credential banner reports only a fixed presence message; it does not print
key fragments or source labels or invoke a credential callback. Caller-scope
and shared-instance refusals retain their decisions and error codes while
omitting raw profile-home arguments from their diagnostics. This is a bounded
repair of these diagnostic sites, not a claim of general log redaction.

The original computer-only patch bytes and postimages remain unchanged. A
privacy-only artifact must contain the original upstream computer files; a
computer-only artifact must contain the original upstream memory files. The
complete Git membership verifier refuses an undeclared combination. Computer
activation remains separately held and is not required by the context consumer.

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
