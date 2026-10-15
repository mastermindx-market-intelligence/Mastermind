**Verdict: REQUEST_CHANGES — five findings in the frozen source slice.** The most consequential defect is that the new admission wrapper defeats the canonical sink’s guard-result checks.

Reviewed local branch `sol/vps-fabric-llm-convergence-20261001-sol-001`, at base **`85f34140f3f68c73b046263f1308fef48e4bd8a7`**, plus the six specified uncommitted files. **All six SHA-256 digests matched the supplied manifest both before inspection and immediately before this result.** These are static source findings; I ran no tests, created no children, made no mutations, and used no network.

1. **High / P1 — The admission wrapper turns invalid guard verdicts into approval.**
   At [executive_service.py:4847](./control_plane/executive_service.py:4847), `admitted_guard()` calls the host’s `admission_guard(envelope)` but discards its return value and itself returns `None`. The canonical sink deliberately rejects every non-`None` verdict, including asynchronous guards, at [ceo_intent.py:709](./control_plane/ceo_intent.py:709). The wrapper conceals those verdicts: a guard returning `False`, or an async guard whose body never executes, can pass admission when the remaining inputs are valid. The binding constructor accepts both as callable.

   **Required repair/evidence:** Preserve the synchronous, `None`-only guard contract through the wrapper and reject awaitable results. Existing tests `test_fresh_sink_requires_synchronous_host_guard` and `test_async_and_raised_guards_refuse_without_job` exercise the sink directly; they do not cover this new wrapper. Regression coverage must pass those guard cases through the service binding and prove zero Job creation.

2. **Medium / P2 — Direct reads omit the same-Runtime checks already required for status.**
   The new branch at [executive_inference_ingress.py:50](./control_plane/executive_inference_ingress.py:50) checks only that the supplied reader is a `Runtime`, then projects its result. It skips the path, read-binding, and source-stability checks used by status at lines 80–95. The preliminary lookup also permits an absent operation in the active Runtime.

   Consequently, an incorrectly wired or stale host factory can return a qualified reader for another database, and direct read can publish that database’s result. Its `SAME` observation proves consistency within that reader, not identity with the submitting Runtime. Exact result hashes do not repair that provenance gap.

   **Required repair/evidence:** Apply a shared source-identity check to both status and direct read. Extend the existing `test_foreign_read_runtime_with_same_operation_and_job_number_is_refused` case to `DIRECT_RESULT_SCHEMA`, including an operation absent from the active Runtime. The current direct-socket test checks a forged content digest, not a foreign qualified source.

3. **Medium / P2 — The advertised 60 KiB request allowance is unreachable above 48 KiB.**
   The new schema-specific allowance at [executive_service.py:4800](./control_plane/executive_service.py:4800) executes after an unconditional release-frame ceiling at line 4775. Both listener construction paths also retain `release_ingress.MAX_FRAME_BYTES + 1`; that constant is **49,152 bytes**, while inference advertises **61,440 bytes**.

   A valid inference request near its own 48 KiB payload limit exceeds the earlier limit once the service envelope and grounding are included. The client allows it, but the server rejects it before inference validation.

   **Required repair/evidence:** Make the outer transport ceiling accommodate the admitted frame families while retaining each family’s own limit. `test_larger_service_packet_reaches_existing_sink_without_legacy_8k_gate` uses approximately 20 KB, and the oversized test verifies only client-side refusal. Neither covers valid service frames between 48 and 60 KiB or the preservation of legacy CEO/release limits.

4. **Medium / P2 — Peer validation permits an inference UID that already has Operator authority.**
   The collision check at [executive_service.py:2379](./control_plane/executive_service.py:2379) excludes C1 and the optional Web/COO App UID, but does not exclude the Executive process UID or the Operator allowlist. The Operator listener separately recognizes those identities at lines 3787–3789 and 3852–3853.

   If the service is configured with the Executive UID while C1 uses another UID, the constructor accepts it; that OS principal also owns the private Operator socket and retains broader authority outside the inference dispatcher. **This is a conditional enrollment/configuration defect, not evidence of a deployed escalation.**

   **Required repair/evidence:** Reject overlap with the Executive/Operator privileged identities, or enforce an equivalent host-enrollment invariant before accepting the binding. The new harness uses `peer_uid=os.geteuid()`, so its positive transport results do not demonstrate a restricted OS principal. Despite its name, `test_optional_binding_is_default_off_and_rejects_uid_collision` does not construct a service with colliding UIDs.

5. **Medium / P2 — The newly admitted service peer inherits an unbounded pre-admission connection wait.**
   After accepting the new inference UID, [executive_service.py:4753](./control_plane/executive_service.py:4753) waits for frame completion without a server-side deadline or concurrency bound. The admission-armed check occurs later. An incomplete connection therefore retains a handler even when inference admission is disarmed. Shutdown treats these handlers as work that must drain and retains custody when they do not, at lines 3672–3680.

   This wait predates the slice, but the slice exposes it to the additional service principal. Byte ceilings and client-side timeouts do not bound a direct peer’s connection lifetime.

   **Required repair/evidence:** Bound pre-submission frame acquisition separately from work that may already have committed. Add coverage showing an incomplete service connection expires and cannot prevent shutdown, while preserving the existing non-cancellation protection after submission starts.

The inspected code does preserve several important boundaries: peer selection uses kernel UID rather than caller-supplied UID/group fields; inference peers are excluded from legacy CEO/read/release dispatch; fresh admission defaults off; the canonical sink revalidates task-aware placement; and the App rechecks authentication around result retrieval. Direct-result validation binds operation, request fingerprint, reference, and content hash. The response path also checks the serialized envelope against its ceiling. I found no additional concrete response-budget defect in this slice.

**Verification limits remain material.** The socket tests use the current process UID, and negative peer cases monkeypatch `_peer_uid`; they do not establish Linux `SO_PEERCRED` behavior, actual distinct-UID isolation, group/ACL permissions, or installed access. Terminal results remain synthetic SQL fixtures. I did not rerun the reported 32 passing tests or the parent’s larger regression, and I did not verify remote PR/CI state under the network restriction.

The eight specifically **REFUSED** Supervisor tests, held direct-emitter fixture, and denied Bot snapshot repairs remain untouched and unresolved. This review supplies no deployment, service-enrollment, provider-execution, completed-worker, or release approval.
