# Stage-B0-R1 v3 repair plan

Operation `stage-b0-r1-real-owner-gap-repair-20260902-sol-001`; carrier PR #368 / `sol/stage-b0-protected-source-correction-r1-20260902`; records-only; HOLD-FOR-SOL.

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{"schema":"mastermind.autonomy_stage_b1_correction_gate.v3","protected_source_sha":"24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8","repair_operation":"stage-b0-r1-real-owner-gap-repair-20260902-sol-001","pull_request":368,"paths":["docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md","docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md","tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"],"records_only":true,"runtime_effect":false,"provider_effect":false,"production_armed":false,"stage_b1":"PARKED","supported_modes":[],"supported_surfaces":[],"next":"STAGE-B-P0_ROOT_TARGET_AUTHORITY_ARCHITECTURE_FREEZE","global_static_fence_defect":"SEPARATE_PATH_DISJOINT_OPERATION"}
```
<!-- STAGE_B1_CORRECTION_GATE_END -->

<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->
```text
1. PROTECT_V3_CORRECTION
2. KEEP_STAGE_B1_PARKED
3. FREEZE_P0_ROOT_TARGET_AUTHORITY
4. IMPLEMENT_AND_PROVE_ONE_EXISTING_OWNER_VERTICAL
5. PROTECT_P0
6. FREEZE_NEW_STAGE_B1_SOURCE_LAW
7. IMPLEMENT_ONLY_AUTHORIZED_MODES
8. MUTATION_SECURITY_AND_ROW_INTEGRITY_PROOF
9. INDEPENDENT_EXACT_HEAD_REVIEW
10. SOL_EXPECTED_HEAD_RELEASE
11. SEPARATE_PRODUCTION_CANARY
```
<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->

Acceptance: exact three paths; zero modes/surfaces; source-law tests prove missing owner, absent Codex CEO target, `chatgpt-sol`, real typed ACK, complete-map projection, no new store, production disarm, and mutation failures. Repair the unrelated historical static-fence defect on another carrier. Continue with the P0 records freeze, not Stage-B1 code.
