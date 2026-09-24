---
schema: mastermind.autonomy_stage_b_f0_plan.v6
architecture_revision: v6.1-split-initial-and-reuse
operation: stage-b0-r2-alias-carrier-correction-20260903-sol-001
capability: SPEC_ONLY
production_effect: NONE
---

# Stage-B0 V6.1 — alias-scoped CEO carrier implementation plan

## Outcome

```text
CEO-v2 intent
-> root-level COO aggregation responsibility root
-> protected C1 selection
-> C2-PURE V2 retains create/reuse vocabulary
-> C2-R1A creates and claims the initial alias-scoped CEO carrier
-> MAT-S1 materializes that carrier Attempt and owns the canonical current-writer read
-> first-root Stage-B1 assigns the logical office on the source-root aggregate
-> later-root C2-R1B reuses that read only to commit a later source root
-> unchanged Stage-A exact-actor enforcement
```

Many source roots may converge on the same `EXECUTIVE-CEO-CODEX-A` carrier. Carrier identity is protected alias + target-definition fingerprint + generation, never source root. The target remains disabled and globally production-disarmed.

## Correction gate

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{
  "architecture_operation": "stage-b0-r2-alias-carrier-correction-20260903-sol-001",
  "architecture_revision": "v6.1-split-initial-and-reuse",
  "carrier_scope": "one alias-scoped carrier, reusable by many source roots",
  "implementation_dependencies": {
    "C2-R1A": [
      "C2-PURE"
    ],
    "C2-R1B": [
      "MAT-S1"
    ],
    "MAT-S1": [
      "C2-R1A"
    ],
    "MULTI-ROOT-REUSE-CANARY": [
      "C2-R1B",
      "STAGE-B1"
    ],
    "STAGE-B1": [
      "MAT-S1"
    ]
  },
  "implementation_sequence": [
    "C2-PURE",
    "C2-R1A",
    "MAT-S1",
    "STAGE-B1",
    "C2-R1B",
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

## Dependency DAG

1. Protect this exact three-path records correction.
2. Protect C2-PURE V2 on its existing two-path carrier.
3. Build C2-R1A as one existing `BEGIN IMMEDIATE` Runtime transaction for initial carrier creation only.
4. Preserve protected MAT-F0 effect-certain architecture.
5. Build MAT-S1 to materialize only the committed role-null CEO carrier Attempt and extend one canonical current-writer read owner.
6. After MAT-S1, first-root Stage-B1 may proceed independently of C2-R1B.
7. After MAT-S1, build C2-R1B only for later-root reuse, consuming that owner to append a reuse commitment.
8. Run a multi-root reuse canary only after both Stage-B1 and C2-R1B are protected, under separate authorization.

This is a dependency DAG, not a linear release sequence: C2-R1A precedes MAT-S1; MAT-S1 precedes both first-root Stage-B1 and later-root C2-R1B; multi-root reuse/canary requires both children. First-root Stage-B1 is never held on C2-R1B.

## C2-PURE — closed V2 contract

C2-PURE owns only `control_plane/executive_placement_commitment.py` and its focused test. It encodes the closed pairs `new_session_materialization / created` and `existing_session_reuse / reused`. It binds source provenance, C1 evidence, selected Worker/quota/snapshot, alias, target fingerprint, carrier generation, and deterministic carrier creation command. It excludes RuntimeBinding, provider/process/account/model/Slack identity, aggregation-handoff/plan authority, and caller-selected carrier identity.

Proof must show that different source roots derive different commitment commands while the same alias/fingerprint/generation derives one carrier command; mode/disposition drift and forbidden fields must fail closed.

## C2-R1A — initial carrier commitment

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

C2-R1A supports only `new_session_materialization / created`. `existing_session_reuse / reused` remains part of the C2-PURE V2 eventual contract but is `HELD_MAT_S1_CURRENT_WRITER_OWNER` until C2-R1B. C2-R1A must not extend `Runtime.current_harness_binding_source`, read OHF epoch/generation tables directly, or create a role-null current-writer validator.

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

The existing broker, Codex adapter, epoch, generation, receipt, and reconciliation owners remain authoritative. MAT-S1 extends one canonical Runtime read owner for typed `mastermind.sol_session_carrier/v1` provenance, CEO seat, role-null shape, READ-only grant, exact C2 commitment, current Attempt/Worker/placement, OHF attestation, CURRENT epoch/generation, and Executive-held writer. It never projects the COO source root as the CEO RuntimeBinding. MAT-S1 leaves exactly one accepted CURRENT carrier writer alive for assignment.

## C2-R1B — existing carrier reuse

Only after MAT-S1's canonical current-writer read owner is available may C2-R1B consume it on the same transaction. For `existing_session_reuse / reused`, require exactly one valid alias carrier, its exact current Attempt and accepted current OHF writer, and identical Worker/quota/snapshot. Append only the missing source-root commitment. C2-R1B creates no Job or Attempt and changes no carrier Job, quota, lease, fence, provider session, or RuntimeBinding.

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
