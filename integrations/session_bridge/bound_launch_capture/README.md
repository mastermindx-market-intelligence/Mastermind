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
The nested Runtime fields are then passed to the actual process-capture call.
The snapshot digest is recorded in the early receipt; the terminal process
record retains that digest and the exact early-receipt digest. This remains
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
