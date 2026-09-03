---
schema: mastermind.autonomy_stage_b_f0_plan.v6
architecture_revision: v6-alias-scoped-ceo-carrier
operation: stage-b0-r2-alias-carrier-correction-20260903-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Stage-B0 V6 — alias-scoped CEO carrier implementation plan

## Outcome

```text
CEO-v2 intent
-> root-level COO aggregation responsibility root
-> protected C1 selection
-> C2 V2 creates or reuses one alias-scoped CEO carrier and commits root-to-carrier evidence
-> MAT-S1 materializes only the carrier Attempt through existing OHF + MAT-F0 semantics
-> Stage-B1 assigns the logical office on the source-root aggregate
-> unchanged Stage-A exact-actor enforcement
```

Many source roots may converge on the same `EXECUTIVE-CEO-CODEX-A` carrier. Carrier identity is protected alias + target-definition fingerprint + generation, never source root. The target remains disabled and globally production-disarmed.

## Correction gate

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{
  "architecture_operation": "stage-b0-r2-alias-carrier-correction-20260903-sol-001",
  "architecture_revision": "v6-alias-scoped-ceo-carrier",
  "carrier_scope": "one alias-scoped carrier, reusable by many source roots",
  "implementation_sequence": [
    "C2-PURE",
    "C2-R1",
    "MAT-S1",
    "STAGE-B1",
    "PRODUCTION-DISARMED-CANARY"
  ],
  "predecessors": [
    "STAGE_B_R2_RECORDS_CORRECTION_PROTECTED",
    "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
    "CAPACITY_C1_PROTECTED",
    "CAPACITY_C2_V2_COMMITMENT_PROTECTED",
    "MAT_F0_EFFECT_CERTAIN_ARCHITECTURE_PROTECTED",
    "MAT_S1_CURRENT_CEO_CARRIER_WRITER_PROTECTED"
  ],
  "production_armed": false,
  "records_path_ceiling": 3,
  "records_paths": [
    "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md",
    "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md",
    "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"
  ],
  "runtime_binding_source": "carrier Attempt only",
  "schema": "mastermind.autonomy_stage_b1_gate.v6",
  "source_root_claimed_by_c2": false,
  "stage_a_changed": false
}
```
<!-- STAGE_B1_CORRECTION_GATE_END -->

## Ordered waves

1. Protect this exact three-path records correction.
2. Protect C2-PURE V2 on its existing two-path carrier.
3. Build C2-R1 as one existing `BEGIN IMMEDIATE` Runtime transaction.
4. Preserve protected MAT-F0 effect-certain architecture.
5. Build MAT-S1 to materialize only the committed role-null CEO carrier Attempt.
6. Build Stage-B1 after the exact current carrier binding exists.
7. Run one separately authorized disposable production-disarmed canary.

Runtime effects are strictly ordered: C2 before MAT-S1, MAT-S1 before Stage-B1, and Stage-B1 before any canary.

## C2-PURE — closed V2 contract

C2-PURE owns only `control_plane/executive_placement_commitment.py` and its focused test. It encodes the closed pairs `new_session_materialization / created` and `existing_session_reuse / reused`. It binds source provenance, C1 evidence, selected Worker/quota/snapshot, alias, target fingerprint, carrier generation, and deterministic carrier creation command. It excludes RuntimeBinding, provider/process/account/model/Slack identity, aggregation-handoff/plan authority, and caller-selected carrier identity.

Proof must show that different source roots derive different commitment commands while the same alias/fingerprint/generation derives one carrier command; mode/disposition drift and forbidden fields must fail closed.

## C2-R1 — atomic carrier commitment

For `new_session_materialization`, one existing Runtime-owned transaction must:

1. reconcile the root commitment command before mutable reads;
2. reread the source root and accepted CEO-v2 provenance without claiming or relabeling it;
3. recompute C1 against current Worker, quota, occupancy, capacity, and effect facts;
4. recompute the protected target-definition fingerprint;
5. prove no generation-1 alias carrier exists;
6. insert the CEO/role-null/READ-only carrier and typed `JOB_CREATED` receipt;
7. reserve quota, mint the first carrier Attempt, persist its snapshot, update the carrier Job, and append `JOB_CLAIMED`;
8. append one source-root-scoped C2 V2 Event;
9. commit every effect together.

Any failure rolls back the carrier Job, quota reservation, Attempt, Job update, and Event.

For `existing_session_reuse`, require exactly one valid alias carrier, its exact current Attempt and accepted current OHF writer, and identical Worker/quota/snapshot. Append only the new source-root commitment. Create no Job/Attempt and change no quota, lease, provider session, or RuntimeBinding.

A terminal, stale, ambiguous, moved, or multiply present carrier is a typed hold. There is no second candidate, replacement carrier, succession, retry, failover, or G3. Replay rereads current source and carrier truth before returning immutable evidence.

## MAT-S1 — role-null CEO carrier materialization

```text
exact committed_carrier_attempt_id
-> existing Operator Harness Runtime broker and Codex adapter
-> one accepted CURRENT writer for EXECUTIVE-CEO-CODEX-A
```

MAT-S1 is a bounded role-null entry through the existing OHF plane. It does not call the plan-only supervisor, run or complete a planner turn, or fabricate an orchestration work-admission receipt.

Reuse MAT-F0 semantics exactly:

- normal start: `INTENT -> APPLIED`;
- recovered start: `INTENT -> EFFECT_UNKNOWN -> RECONCILED(resolution=APPLIED)`;
- unresolved uncertainty or missing receipt: quarantine the same carrier Attempt;
- never append `APPLIED` after `EFFECT_UNKNOWN`;
- never issue a second start, replacement Attempt/carrier, failover, or G3.

The existing broker, Codex adapter, epoch, generation, receipt, and reconciliation owners remain authoritative. A dedicated Runtime read owner validates typed carrier provenance, CEO seat, role-null shape, READ-only grant, C2 commitment, current Attempt/Worker/placement, OHF attestation, CURRENT epoch/generation, and Executive-held writer. It never projects the COO source root as the CEO RuntimeBinding. MAT-S1 leaves exactly one accepted CURRENT carrier writer alive for assignment.

## Stage-B1 — initial source-root assignment

```text
COO aggregation source root
+ exact C2 V2 root-to-carrier commitment
+ exact disabled target definition
+ exact current RuntimeBinding from the carrier Attempt
-> SOL_ACTION_TARGET_ASSIGNED revision 1 on the source root
-> complete-map projection
-> unchanged require_sol_action_authority
```

The trusted service derives every value. Public callers expose no destination, carrier, Worker, Attempt, RuntimeBinding, provider, account, actor, or command identity. V2 command/Event evidence includes exact `carrier_job_id` and `carrier_attempt_id`.

Replay derives and looks up the immutable command, then revalidates source provenance, C2 V2 evidence, alias-carrier cardinality/provenance, exact current carrier Attempt/writer, target definition, and same-alias binding coherence. It returns byte-identical evidence or fails closed. Assignment remains source-root-scoped, initial-only, complete-map, and subject to unchanged Stage A.

## No-rebuild and release boundary

Do not add a table, migration, lifecycle, queue, scheduler, target store, RuntimeBinding store, retry ledger, watcher database, provider/account registry, replacement/succession plane, or alternate selector. Do not duplicate Executive Job/Attempt/Worker/Event, Capacity selection/claim, Operator Harness, RuntimeBinding projection, Wake, or Stage-A owners.

This carrier is records-only. A protected merge authorizes neither C2, MAT-S1, nor Stage-B1 implementation and creates no Runtime, provider, target, Wake, deployment, or production effect. Each later wave remains separately commissioned and predecessor-gated.
