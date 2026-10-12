# Original-owner launch evidence — source integration

This is an uninstalled extension of the existing Fabric controller reservation
and process-capture boundaries. It does not supply a production Backend or arm
Executive submission. Existing accepted runs and their records are unchanged.

`fabric_launch_reservation.py` reserves the incumbent `remote_sub.sh` run log
with its existing `O_EXCL` ownership rule. The optional first line binds the
Runtime root/Job/Attempt, grant/commission digests, physical-route digest and
canonical start-request digest. It flushes the file and containing directory
before returning, and checks that the visible reservation still matches its
open handles. A failure leaves the original name consumed. Matching bytes do
not authorize replay; a changed request or route cannot reuse that reservation.

`remote_sub.sh.patch` wires this into the original pre-lease reservation, only
when the embedding owner supplies `REMOTE_SUB_START_BINDING_FILE` (legacy V1)
or `REMOTE_SUB_START_CORRELATION_FILE` (V2). Providing both refuses. The V1
flat correlation remains readable only as V1; it is not a complete bridge
binding. Runtime's root Job ID differs from Fabric's original orchestration
root, so V2 retains `routing_root_id`, `routing_parent_run_id`, and the nested
seven-field `runtime_binding` separately. Its run ID must be the deliberately
assigned new Runtime Attempt ID. It cannot adopt or rename an older manual run.

V2 forwards a canonical snapshot of that exact reserved header through the
existing per-run upload, into a newly created private directory. Existing names
refuse. `fabric_launch_transport.py` checks the fixed run-derived path, digest
and original routing lineage before the executor acquires physical admission.
The nested Runtime fields can be retained by the process-capture contract, but
the public executor now refuses a bound snapshot before physical admission:
correlation alone cannot select the legacy `sub.sh` command as an Executive
worker. Unbound attended shell use keeps its existing behavior. The capture
contract records the snapshot digest in the early receipt and retains that
digest plus the early-receipt digest in the terminal record. These fields remain
correlation, not evidence that Runtime or Capacity granted the operation.
The source collection path retains the early receipt even if stdout delivery
or cleanup remains uncertain; an acquisition failure does not change custody
or authorize a replay. The retained remote receipt is not deleted.

Unbound calls retain their existing path. Bound calls cannot use the legacy
pre-lease continuation exception. The input and log directories must already
satisfy the private-owner checks: this code performs no chmod, chown, directory
repair, lease release or provider operation. `RESERVATION_SOURCE.json` pins the
exact installed preimage; installation must preserve any newer source changes.

The file and its fields are **correlation, not authentication or a grant**.
Reading a reservation always reports `start_authorized:false` and
`UNRESOLVED_BY_RESERVATION`. A missing, empty, partial or legacy log is not an
unused-Attempt proof. The future authenticated Backend must validate the
current Runtime/Capacity assignment and consume its original first-use
authority at the actual launch boundary; this helper cannot manufacture that
authority from an environment variable or file.

The qualified early-launch candidate is now ported onto the current
`lane_runtime.py` in `lane_runtime.py.patch`. `CAPTURE_SOURCE.json` pins the
installed base and candidate; the `fixtures/` snapshot exists only for
reproducible patch validation and is never an installed runtime. The original
parent consumed `fabric-bound-launch-port-01a11e90-v1` and retrieved its exact
manifest artifacts. All 59 existing functions/classes are preserved except
the intended `run_owned_process` extension. The 65 affected checks pass with
inert child programs and mocked kernel identity/census. The patch preserves
the newer operator diagnostic, capture, cleanup and recovery behavior.

The receipt captures the owned gate process's boot/start generation before
releasing target exec. When either new physical-route or request digest is
present, both and all five Runtime correlation fields are required before
spawn. Legacy callers retain their behavior. `PRE_EXEC_HANDSHAKE`,
`correlation_is_authority:false` and `provider_execution_attested:false`
remain explicit. This is source labor, not native mission proof.

The source wire connects the proposed original context to that actual spawn
and settlement. Its remaining integration is the authenticated Backend that
validates the real current Runtime/Capacity assignment and physical route,
consumes first-use authority, and produces complete physical/profile/isolation
and cleanup evidence from the supported harness. A wrapper PID or copied
historical log cannot become a Worker attestation. The controller still waits
for ordinary completion; this source does not implement an early authenticated
Backend start response. Installation, provider/profile admission, assignment
revocation and the real original-parent task proof remain open.

Source validation: 17 focused reservation checks and six checks against the
actual patched reservation fragment passed. They cover concurrent callers,
changed request/route, failure during durability, missing/truncated/legacy
records, wrong root/Attempt, shared directories, symlinks, duplicate JSON keys,
short writes, moved directories and preservation of the unbound controller.
No provider calls, installed-file changes or host probes were part of these
checks. Independent MiniMax review `fabric-bound-reservation-review-01a11e90-v1`
returned 2954 bytes, SHA256
`52c6ddfc7e8f6761a812544c3df72db1409a70d344515cb2748f896100e8fdc7`.
The original parent adjudicated its scoped PASS, exercised two additional
missing-root/malformed-input fragment checks, and recorded reviewer acceptance
once with `ACCEPTED/VALIDATED_OUTCOME` readback. Its same-UID hardlink observations
do not establish tamper-proof evidence: the helper remains correlation-only.
This accepted source review does not release installation or native admission.

The later V2 wire has 25 reservation, eight transport, six actual patched
controller/executor-fragment checks, and 72 affected capture checks passing.
The capture wrapper verifies the pinned base/patch/candidate and replays the
inert suite in a separate process. No live transport, provider, service or host
probe is executed by those checks. The independent V2 review is the original
`fabric-bound-wire-review-01a11e90-v1`; its result must be adjudicated separately.

Independent V2 review returned 34,354 retained bytes, SHA256
`986cc9a55e7971d200f8b3adfb558d8e2d5278e0645bc2800bd10439b195e571`.
Its final findings were useful, but the raw response exceeded the hard 3,500-byte
contract, so the child remains NOT_ACCEPTED. Parent reproduced and repaired the
unanchored sidecar digest: launch now compares it with the original O_EXCL
reservation before sending its literal digest. The actual controller fragment
rejects a self-consistent changed sidecar. Upload explicitly preserves private
mode; the remote file guard is unchanged. Full context conversion keeps physical
and request digests outside the bridge's closed five-field Runtime binding.
Collector construction/start now shares the original gate-close and cleanup
finally path; four injected failures cannot execute the target or claim complete
capture. Final validation is 25 reservation, 10 transport, 7 controller-fragment
and 76 inert capture checks, with exact patch replay. These remain uninstalled
source changes, not authenticated admission or native completion.

## Original controller invocation component

`fabric_reserved_attended_launch.py` checks the complete original request against
its reserved Runtime/Fabric identities and canonical digest. It uses the existing
broker decoder and finite Claude preparer, preserves exact stdin and a closed
environment, and retains immutable validation commands only from the owner's
fixed allowlist. Its output remains preparation, not admission.

The executor patch factors the existing process/capture/cleanup block into one
shared function. The private `_run_reserved_attended_under_lease` component uses
that same function under the original controller's existing lease. It does not
acquire a second lease, add a registry, retry an operation or release custody.
It rechecks the existing in-process `ControlStartAuthority` after preparation
and owner checks, immediately before entering the process runner. Uncertain
cleanup retains the original reconciliation hold; proven exec failure keeps
the original errno/return-code behavior. Finite commands bypass the legacy
inherited environment and PATH augmentation.

The private owner-check callback is a composition/test seam, **not an admission
producer**. A callable or boolean establishes no realm, attendance, canary,
binary, schema or isolation evidence. No production factory or public CLI/RPC
selects this function. Real realm credential insertion, authenticated remote
owner composition, current assignment checks and full post-exec START remain
necessary. The public bound path stays refused until those obligations have
an actual qualified implementation. Control authority is not serialized to an
ordinary SSH principal.

Finite Claude uses `run_dir/home` as its execution HOME. Its actual home
attestation must name that path. The fixed physical route's `provider_home`
continues to identify the credential realm and is checked separately through
the original exact v2 MiniMax canary. The exception cannot be selected by a
bare `passed:true`, a different realm/profile or an unbound home path. Legacy
fixed-home contracts retain their prior semantics.

### Original-handle invocation and once-only START retention

The original runner retains its actual argv, cwd, shell setting, environment
key set, prompt digest, non-secret environment projection digest, original
Popen timestamp and one owner-minted nonce. Credential values are neither
retained nor hashed. The private reserved begin seam binds the exact prepared
descriptor, original request/physical digests and a fixed START filename beside
the original terminal carrier before returning its same live handle. Existing
START bytes refuse before spawn; they do not establish positive first use.

`retain_owned_start_bytes` is a publication mechanic for an already validated
complete result. It checks the live original handle, generation, nonce, start
time and actual invocation against the supplied record. It also checks the
prepared non-secret environment controls, so unchanged key names cannot hide
a changed endpoint, model, HOME or TMP. It uses the existing owner-private
directory check and no-replace immutable inode publication, then fsyncs and
reads back the exact bytes. The early PRE_EXEC receipt keeps its schema and
8 KiB bound; complete retention has a separate 64 KiB bound and filename.

The first attempt consumes the live handle's publication opportunity, including
on failure. A failure holds the original lease for reconciliation, leaves the
same process/collector/finisher untouched and never resends. A successful
publication does not release that lease or assignment exclusion; the concrete
Backend must retain both through Control seal, actual worker denial and durable
Supervisor ACK. A worker-owned file is observation, not restart authority.

This delta does not assemble an attestation or authenticate evidence. The
actual producer must still invoke both complete START validators using a fresh
original-handle image, an independently pinned binary and actual qualified
realm/attendance/Capacity/workspace/HOME/TMP/isolation/canary/assignment inputs.
The runner still has no retained stdout/stderr/result file producer for the
shared START contract. A caller cannot fill those paths with invented names.
No factory, public bound CLI, profile, installed service or provider is enabled.
