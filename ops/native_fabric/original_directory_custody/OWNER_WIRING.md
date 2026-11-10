# Fixed original-directory native owner wiring — prospective source only

This component implements the formerly missing composition, without registering
or invoking it. `owner-registration.forward.patch` adds one fixed branch to the
incumbent `artifact_delivery.transport`, a private factory seam to the same
`fabric_task` owner, and an optional expected-inode constraint on its existing
bounded file reader. Removing those additions reproduces both whole original
files; the file reader's default behavior is unchanged. No ordinary CURRENT observation, dispatch, worker, provider, artifact
collection, command parser or registration table changes.

## Exact host integration

The incumbent native host may eventually supply an implementation of
`NativeMetadataPermissionSource`, an extension of the existing
`NativeInvocationOwner`, to `_original_directory_owner_factory(source)`. The
factory reads the incumbent `hosts.json` itself; the host and action are fixed.
Callers supply no path, root, host, account, UID or arbitrary carrier. Factory
construction performs no original-metadata read, diagnosis or intent claim.
Only a distinct explicit authorized invocation of `run_fixed_metadata_action`
can proceed. There is no CLI, environment selector or automatic hook.

The source staging recipe is literal: place the reviewed reader as
`ext/original_directory_custody_reader.py`, the reviewed owner as
`ext/original_directory_custody_owner.py`, and apply the forward patch to the
matched selected40 `ext/artifact_delivery.py` and `ext/fabric_task.py`. The
component pins all four postimages and the exact unchanged supporting sources.
This is a prospective composition recipe, not an installed generation,
selection request, executable permission or original collection recovery.

## The genuine external control still unsupported

The current native CLI factory's documented authority is the invoking OS/tool
permission plus external scoped commission. Its CURRENT owner verifies request
correlation and registry custody but receives no authenticated permission
context. The current Codex `exec_command` interface passes command/workdir and
returns execution facts; it exports no authenticated historical-action grant,
same-SSH-account/expected-UID binding, or reusable current-permission witness to
the child Python process. The consumed Prophet records likewise contain none.
This bounded absence is not a statement about every OS or external record.

The exact unsupported interface is **the trusted native tool host's export of
a current, specifically scoped metadata-action permission context**. It must:

- Authenticate the actual invoking native principal and current OS/tool grant,
  separately from the original Prophet resource root/parent. Neither supplied
  labels nor being the same Unix user authenticates a native thread.
- In `open_permission(view, invoking_uid, source_sha256, host_entry_sha256)`,
  validate the fixed action/original metadata/namespace, this exact accepted
  source closure, whole registry entry, and the actual authorized operation.
  Return an opaque context tied to that existing owner, never a JSON receipt,
  boolean, token minted by this module or general CURRENT-read grant.
- In `binding(context)`, derive `OwnerTransportBinding` from the enrolled
  authenticated SSH account and expected positive remote UID. The registry
  alias and a matching returned UID alone do not prove account identity. No
  UID is guessed and no account/SSH configuration is probed here.
- In `current(context, view, invoking_uid, source_sha256, host_entry_sha256)`,
  revalidate the same permission, native identity, source and account before
  original metadata reads, intent, transport and publication, and after them.
  It must not acquire, refresh, broaden or replay a permission.

The default implementation refuses. An in-process subclass is a trusted host
integration boundary, **not an authentication primitive** or proof of a live
grant. The positive tests declare inert host premises explicitly. A real host
must implement this interface from its genuine permission owner; an always-True
class, model-authored receipt or caller's `CURRENT` grant is not an integration.
No source in this component creates that authority or selects a runtime.

## One fixed intent and carrier

After permission/account checks, the owner reads only the two fixed accepted
binding and original `read-request.json` metadata records with the incumbent
no-follow bounded reader and exact hashes. References inside them are never
followed. No original refusal response, packet, stdout, result, support body,
policy, active entry, lease, credential or provider state is read.

The owner then uses the existing `reserve_destination` / `write_exclusive`
delivery primitives for the fixed separate `metadata-action-v1` leaf under the
MMOS evidence root. The original refused collection destination is untouched.
A fresh leaf and `intent.json` are durable before any remote progression.
Existing/interrupted leaves are refused, not loaded, adopted, released, deleted
or retried. Intent inode and bytes, original metadata hashes, whole registry,
source closure, permission methods/context, account and invoking UID are
rejoined. The intent read pins its actual opened FD to the original inode and
retains the incumbent held/named post-read identity checks. After every local
I/O check, a final authority-only join verifies the same permission, account,
method identities and UID. This closes withdrawal during the last intent read
before carrier progression. A failure leaves `EFFECT_UNKNOWN` and no retry permission.

The carrier accepts only the private active same-owner handoff. Direct request
JSON, a default/CURRENT owner, a foreign owner/view or an unclaimed factory
cannot enter the process. The existing strict SSH carrier, fixed interpreter,
stdin framing, output bound, deadline and own-read process cleanup remain.
The generated program comprises fixed functions from the captured reader and
the unchanged contract/JSON validators; it opens only account-pwd directory
metadata. No artifact contents or original operation is executed or collected.

Only a validated response from the expected UID can be returned. The separate
`observed.json` is historical **metadata-only** correlation with no retry or
original-outcome acceptance; it is not an artifact `COMPLETE` receipt, current
readiness proof, grant, or permission to change directory custody. Late
withdrawal withholds the current return; retained intent/evidence is never
silently removed. Namespace checks and chmod are separate syscalls; this is
trusted-process composition, not a sandbox against arbitrary same-process code.

## Qualification scope

The focused test stages the actual forward patch through the existing provider
composer, loads the real native factory and bounded delivery carrier, and runs
the fixed generated reader in a disposable local Python child instead of SSH.
Its synthetic account-pwd filesystem and original metadata are explicitly
inert. The fresh-destination premise is isolated into an owned temporary leaf;
the real O_EXCL/fsync writer is used. Existing directory-chain/admission reader
proofs remain unchanged and are reused, not counted as new tests. No real
native permission, remote account/UID, original bytes, host, registration or
runtime grant is established by these checks.
