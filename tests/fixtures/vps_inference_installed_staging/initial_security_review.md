**Two findings: one High and one Medium. I would not give this candidate a strict fail-closed source clearance yet.** This is an independent source review only, with no production-install or merge acceptance.

1. **High — The dormant config pair grants historical-result access before independent service enrollment is established.**
   Location: [scripts/executive_os_phase1c.py:2483](./scripts/executive_os_phase1c.py:2483).

   Supplying the two valid fields immediately constructs a binding with a usable `result_read_runtime_factory`. Startup then grants socket access to whatever existing account `pwd.getpwuid(uid)` resolves in [control_plane/executive_service.py:3274](./control_plane/executive_service.py:3274). Neither step establishes that this account is the independently enrolled inference App.

   The exposure includes **direct result content**, not merely status metadata. A process running as the configured UID can supply a known operation key, obtain its terminal reference through status, and pass that reference to the direct reader in [control_plane/executive_inference_ingress.py:81](./control_plane/executive_inference_ingress.py:81). The reference proves result identity; because status supplies it to the same caller, it provides no additional authorization. The HTTP App’s OAuth enrollment check is not on this direct Unix-socket path.

   **Precise threat boundary:** an unrelated UID cannot simply spoof kernel credentials, and a nonexistent UID fails account lookup during ACL setup. The problem is a mistakenly configured, shared, or reused **existing** UID that passes the collision checks. Root-owned configuration establishes who authorized the numeric grant; it does not independently establish that the recipient is the intended restricted service. `admission_armed=False` blocks fresh Jobs but does not prevent this disclosure.

   **Remedy:** keep both service reads and service socket access unavailable until the existing installation/enrollment owner verifies the dedicated OS account and its binding to the intended authenticated service App. Use that existing authority; do not add an issuer or identity registry. Merely removing the read factory is insufficient because the ingress has a fallback status-receipt path. Add negative coverage for an existing, collision-free UID with missing or mismatched enrollment, asserting that neither status metadata nor direct content is returned.

2. **Medium — A read can publish after the service enters a state that would refuse a new inference request.**
   Location: [control_plane/executive_service.py:5370](./control_plane/executive_service.py:5370).

   Before reading, the handler requires `_service_state` to be `READY` or `AWAITING_CANARY`. It then awaits the backend read. Immediately before publication, it rechecks closing, listener readiness, and binding identity—but omits the service-state allowlist. Existing failure paths can set `QUARANTINED` without clearing the listener-ready flag or replacing the inference binding. Consequently, a read already in flight can still return a successful receipt or full result after that transition.

   **Remedy:** recheck the same read-eligibility predicate immediately before sending the response, including the state allowlist. Keep this distinct from the fresh-submission arming predicate so authorized historical reads can remain available while submission is disabled. Add a causal test that pauses a read, changes the service to `QUARANTINED`, resumes it, and verifies refusal without result disclosure.

The remaining inspected controls support a narrower source-level conclusion:

- **Fresh provider work remains blocked in this launcher composition.** Only literal `False` is accepted; grounding deliberately refuses; admission and execution-placement callbacks are absent. I found no route from an inference frame to arming those callbacks.
- **Config validation is appropriately closed for the new fields.** Partial pairs, extra inference-prefixed fields, Boolean/root/nonpositive UIDs, and the listed identity collisions refuse. The production wrapper separately enforces root-owned `0440` configuration. The new fields introduce no caller-selected path or provider.
- **The read factory captures the original constructed service and uses its incumbent namespace custody.** That owner requires the exact active Runtime; the projection checks physical identity and a finalized `SAME` observation. Normal shutdown drains ingress handlers before releasing custody.
- **Default compatibility and transport separation are preserved in the inspected source.** Absent fields leave the binding unset. The gateway retains the company-dialogue framing and separate release/service limits. Inference partial-frame input has a bounded wait.

All five supplied SHA-256 hashes matched at entry and again at completion. `HEAD` remained `770683f9db0261fd967a660004470cce29b8fafd`; `MERGE_HEAD` matched the supplied protected parent `78388ac29f7e54c9dfe7799a8e4769fb46d4aed6`. The reviewed state is the resolved, uncommitted working-tree merge.

I inspected the 23 config cases and temporary-socket test as source; I did not execute tests or verify the reported broad-suite run. No source/test writes, children, network requests, provider calls, credential access, or private-runtime access were performed. The excluded Supervisor reader, snapshot fixes, and stale fixtures were not reopened.

**Installed UID/ACL and OAuth are not proven.** The synthetic UID and mocked ACL calls cannot establish those installation properties.
