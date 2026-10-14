**REQUEST_CHANGES on the frozen snapshot.** The patch closes the stated metadata-only spoof for the default Codex research route, but I found four consequences to address or explicitly constrain. Two are compatibility regressions, one is a producer/consumer contract mismatch, and one is a conditional policy-freshness gap.

The base remains `b9a70ff85ea122f330675ad7fd3f80a2391c133b`. Both supplied SHA-256 values matched before and after review, and the working tree still contains exactly the two named changed/untracked files.

1. **P2 — The matcher ignores the supported custom routing-policy source.**
   At [executive_runtime.py:1142](./control_plane/executive_runtime.py:1142), `ModelRouter.load()` always loads the default policy. However, worker registration and job creation both accept `--routing-policy` and load that supplied policy at [executive_os_phase1b.py:283](./scripts/executive_os_phase1b.py:283) and [executive_os_phase1b.py:361](./scripts/executive_os_phase1b.py:361).

   **Causal result:** a worker and Job created from the same valid custom policy become unclaimable if its version or alias identity differs from the default. The comment claiming the matcher resolves the same policy as Job creation is therefore not universally true.

   **Evidence:** an in-memory probe loaded a valid alternate policy through the actual `ModelRouter.load(path)` implementation. Its matching row returned `False` under the patched matcher and `True` when the matcher received that same router. Acceptance needs a host-controlled policy binding shared by creation and matching; a worker-supplied policy path would not be an appropriate remedy.

2. **P2 — Autonomous alias resolution rejects the existing attended-route contract.**
   The unconditional call at [executive_runtime.py:1148](./control_plane/executive_runtime.py:1148) uses `resolve_model_alias()`, which rejects `worker_eligible=False`. The separate attended resolver deliberately **requires** `worker_eligible=False` and a nonautonomous provider at [fabric_attended_routing.py:91](./control_plane/fabric_attended_routing.py:91). Matching `attended_route` metadata at line 1131 cannot overcome this later rejection.

   **Causal result:** even after separately qualifying an attended composition and resolving the correct policy source, its exact attended alias cannot pass this matcher.

   **Evidence:** the existing discriminator is `test_attended_resolution_never_enters_autonomous_alias_resolver`; the matcher’s positive compatibility assertion is at [test_fabric_attended_routing.py:90](./tests/test_fabric_attended_routing.py:90). A pure in-memory resolver probe also returned `False` with all compared fields matching and autonomous eligibility disabled. **This is a source-contract regression, not evidence that an attended production pool is currently admitted.** Its descriptor remains unimplemented.

3. **P2 — Newly mandatory metadata is absent from an existing pool-binding producer.**
   [executive_runtime.py:1162](./control_plane/executive_runtime.py:1162) now requires quota metadata to contain both `provider_alias` and `adapter_id`. The existing `prepare_pool_binding()` metadata construction at [external_pool_binding.py:503](./control_plane/external_pool_binding.py:503) emits neither. Its registration arguments do carry the physical provider and worker type separately.

   **Causal result:** capacity produced through that seam cannot satisfy the new alias matcher, even when its physical identity and remaining policy fields agree.

   **Evidence:** I evaluated the producer’s actual metadata dictionary expression in memory and supplied it to the actual matcher with an otherwise matching profile. Both fields were absent and matching returned `False`. The new focused tests avoid this mismatch because their helper always supplies both fields at [test_service_capacity_provider_identity.py:39](./tests/test_service_capacity_provider_identity.py:39). This remains a compatibility obligation for that producer’s separately qualified integration; it does **not** establish current external-pool availability.

4. **P2, conditional — Policy freshness is checked per candidate, not held through selection and claim.**
   Each candidate reloads policy at [executive_runtime.py:1142](./control_plane/executive_runtime.py:1142). An accepted candidate remains in `candidates`, and the broker subsequently selects it at [executive_runtime.py:16426](./control_plane/executive_runtime.py:16426), without another routing-policy check before the claim mutation. SQLite’s `BEGIN IMMEDIATE` protects the database, not the policy files.

   **Causal result:** if policy changes during the scan, a row admitted under the old version can still be selected after a later load has observed a version that rejects that Job.

   **Evidence:** executing the actual candidate-loop source in memory with two successive router snapshots selected the first row under the superseded policy; the second load observed `review.revoked.v2`. No database claim was executed. This consequence requires policy files to change during a live operation. A qualified immutable-release/update barrier could exclude that condition, but this patch does not establish one. Acceptance should bind the operation to a coherent policy generation and establish its validity through the claim boundary.

The checks that held are material:

- Both `fast.research` and `standard.research` passed the actual matcher in pure probes. Provider, worker-provider, worker-type, model, effort, and cost mismatches were rejected.
- The generic no-alias/no-profile path remained unchanged. The matcher did not mutate its input constraints.
- Canonical metadata case normalization worked; literal percent-encoded aliases, literal backslash escapes, and NUL-suffixed aliases were rejected.
- Preview and claim both project `worker_type` and invoke the same matcher. Claim rereads persisted Job constraints, so mutating an in-memory preview object does not itself alter claim authority.
- Static policy-version drift fails closed. The concern in finding 4 is movement *during* selection.

Repeated loading also has a measurable cost: 50 identical matcher calls took approximately **65 ms locally**, and the actual candidate loop made **100 full router loads for 100 quota rows that were subsequently rejected as belonging to unrelated quota classes**. Those loads occur inside the claim’s write transaction. This demonstrates scaling and lock-duration overhead; it does not establish a production throughput failure.

**This patch does not permit new external Fabric pools.** The checked-in GLM/Qwen/xAI providers remain disabled and nonautonomous, and `openai-compatible` and `attended-fabric` remain unimplemented descriptors. Separately qualified adapter, provider policy, registration, and capacity admission are still required. The matcher adds consistency checks between registered identities and policy; it does not authenticate the actual provider account or turn copied digests into credentials. Trust in the registration owner and provider/account realm remains an upstream boundary.

I did not rerun the supplied database-backed tests, the broad suite, or the held Supervisor/Bot snapshot tests. The reported six RED cases and eight GREEN tests remain supplied evidence; my additional evidence consists of guarded, memory-only probes and source tracing. Broad-test completion, current protected-branch freshness, and deployment behavior remain unverified. No source modifications, network access, credentials, provider calls, worker operations, or children were used.
