# OCR-5 Cross-Realm Fable Rollover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that one current **non-modifying** Phase 1F-C Fable/COO orchestration Job can survive a real Claude subscription quota boundary by ending Attempt 1 truthfully, letting the existing COO cycle requeue the same Job, claiming a different capacity-identified Claude realm for Attempt 2, starting a fresh provider session, preparing/acknowledging exactly one immutable continuation capsule, and completing through unchanged orchestration result law—while write-capable or effect-uncertain interruptions remain blocked on the original carrier.

**Architecture:** OCR-5 composes existing owners; it adds no rollover scheduler. A pure safety classifier derives `NON_MODIFYING_ATTEMPT` from canonical Executive effective grant + reviewed execution-capability profile + current OHF/Event evidence. Only an exact read-only quota failure may terminalize through existing `rate_limit_attempt()`. Existing `CooCycle` then requeues the same Job. Existing CF2-I/Model Router/Capacity Fabric law chooses the next already-eligible Worker realm; OCR-2C must have established canonical capacity identity for both source and target Claude realms. OCR-4 starts a fresh provider session for Attempt 2. OCR-3 builds the current semantic draft **after the new session is bound/attested** and Executive PREPARE mints exactly one immutable continuation capsule before the first work turn. Fable continuity stays root Job + COO seat + logical session alias; provider Attempt/Worker/session changes underneath it.

**Tech Stack:** Python 3.12, existing `executive_runtime`, `executive_coo_cycle`, `executive_agent_capabilities`, `executive_operator_supervisor`, Operator Harness, OCR-2C canonical capacity identity, OCR-3 continuation contract, OCR-4 Claude adapter, accepted CF2-I placement, pytest.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-fable-root-seat-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-readonly-quota-rollover-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuation-idempotency-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-native-claude-capacity-identity-amendment.md`

## Dependency Gate

Do not implement/arm OCR-5 until all are accepted/current:

```text
CF2-I with real capacity-aware claim evidence
RF1 provider-neutral suitability
HF1 common worker harness
PF1 real Claude provider vertical
OCR-1 V2 >=2 distinct native Claude realms with WORKER_CONTEXT_AUTH_READY
OCR-2C accepted canonical capacity identity for both rollover realms
OCR-3 continuation/binding implementation
OCR-4A provider-neutral rich harness composition
OCR-4 one-realm sustained Claude operator
```

Phase 1F-C policy remains unchanged: non-review orchestration Jobs retain their current Attempt ceiling. OCR-5 proves one accepted retry; it does not raise Attempt limits or introduce another requeue path.

## Global Constraints

- No rollover daemon, retry table, provider failover service, account scheduler, new Job role, workspace journal, mutation log or Fable session table.
- Automatic quota rollover is **read-only/non-modifying only**. A write-capable or otherwise mutation-capable Attempt never becomes cross-realm retryable merely because no diff/final result is observed.
- A source Attempt is `NON_MODIFYING_ATTEMPT` only when canonical evidence re-derives all of:
  - effective authorities contain no `WRITE_BRANCH` or other modifying grant;
  - allowed write paths are empty;
  - the accepted `ExecutionCapabilityProfile.write_capable` is exactly `False`;
  - sandbox policy is the accepted read-only policy;
  - no effective profile capability grants browser/computer/write-capable MCP/native-helper behavior outside that reviewed read-only profile;
  - observed OHF attestation/principal remains bound to that exact profile/grant.
- `QUOTA_OR_RATE_LIMIT` + dead writer + no candidate/result is not enough. The non-modifying predicate is mandatory.
- Any unreconciled `OPERATOR_OPERATION_EFFECT_UNKNOWN`, unknown process liveness, unknown/held provider writer, current writer/epoch, conflicting candidate/result/seal or exhausted retry lineage blocks terminalization/requeue.
- For a write-capable quota failure: stop/reconcile exact current generation/turn, preserve the Attempt/workspace/evidence, return `RECONCILIATION_REQUIRED`, and perform **zero cross-realm claim** under OCR-5.
- Old realm availability/cooling comes from existing Executive/Provider Control owners. OCR-5 never excludes/selects a realm by Slack/account nickname or ordinal.
- Both source and target realms must carry accepted OCR-2C canonical capacity identities; auth-ready but capacity-unbound realms are ineligible for the automatic canary.
- Attempt 2 must have a different accepted placement/account realm from Attempt 1. Same-realm replacement is not OCR-5.
- Cross-realm always starts a fresh provider-native session. Same-session resume/fork is forbidden across account/auth-home change.
- One target Attempt gets one immutable PREPARED continuation capsule. No capsule is finalized before P2 provider session binding, and no second capsule is rebuilt after PREPARE.
- Continuation ACK is mechanical exact-runtime evidence only; it is not model-authored authority, Job completion or automatic Wake ACK.
- Same Job/root/role/authority/plan lineage/result law remains controlling. Rollover cannot widen any of them.
- Slack/Steward projection belongs to OCR-6 and does not cause the Executive rollover.

---

### Task 1: Implement the closed non-modifying rollover safety classifier

**Files:**
- Create: `control_plane/operator_rollover_safety.py`
- Modify: `control_plane/executive_operator_supervisor.py`
- Create: `tests/test_operator_rollover_safety.py`
- Create: `tests/test_executive_operator_provider_failures.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class OperatorRolloverSafety:
    eligible: bool
    classification: str  # NON_MODIFYING_ATTEMPT | RECONCILIATION_REQUIRED | REFUSED
    reason_codes: tuple[str, ...]


def classify_quota_rollover_safety(
    *,
    effective_authorities: tuple[str, ...],
    allowed_write_paths: tuple[str, ...],
    capability_profile: ExecutionCapabilityProfile,
    requested_profile: RequestedExecutionProfile,
    reconcile: ReconcileObservation,
    unreconciled_effect_unknown_count: int,
    candidate_or_result_exists: bool,
    retry_lineage_available: bool,
) -> OperatorRolloverSafety:
    ...
```

- [ ] **Step 1: Write RED-first positive test**

Construct the current accepted read-only planner-equivalent profile/grant:

```text
authorities = READ only
allowed_write_paths = []
ExecutionCapabilityProfile.write_capable = False
sandbox_policy = read-only
requested profile/observed attestation match exact reviewed profile
process liveness = PROVEN_DEAD
provider writer = RELEASED
unreconciled effect-unknown count = 0
candidate/result/seal absent
retry lineage available
failure class = QUOTA_OR_RATE_LIMIT
```

Require `eligible=True`, `classification=NON_MODIFYING_ATTEMPT`.

- [ ] **Step 2: Write mandatory adverse tests**

Each independently refuses automatic rollover:

```text
WRITE_BRANCH or another modifying authority present
non-empty allowed_write_paths
capability_profile.write_capable == True
sandbox != read-only
profile/attestation mismatch or unknown capability state
liveness UNKNOWN/ALIVE
writer HELD/UNKNOWN
unreconciled EFFECT_UNKNOWN
candidate/result/seal closes retry path
attempt limit/retry lineage exhausted
failure class not QUOTA_OR_RATE_LIMIT
```

Also prove an empty observed Git diff does **not** turn a write-capable grant into read-only eligibility.

- [ ] **Step 3: Run RED**

```bash
pytest -q tests/test_operator_rollover_safety.py tests/test_executive_operator_provider_failures.py
```

- [ ] **Step 4: Implement the pure predicate**

Use existing `ExecutionCapabilityProfile.write_capable`, sandbox/profile identity and typed OHF observations. Do not accept model/provider booleans such as `safe_to_retry=True`.

- [ ] **Step 5: Add supervisor-private terminalization**

Required sequence for the positive subset only:

```text
provider quota failure observed
-> exact generation/turn stop + reconciliation
-> process PROVEN_DEAD + writer RELEASED
-> no current writer/epoch after accepted shutdown/abandon law
-> re-read effective grant/profile/Event facts
-> classify_quota_rollover_safety(...)
-> only NON_MODIFYING_ATTEMPT may call runtime.attempts.rate_limit_attempt(...)
```

For write-capable/mutation-capable or ambiguous states return a bounded `RECONCILIATION_REQUIRED` result and make no `rate_limit_attempt`, requeue or claim call.

- [ ] **Step 6: Run focused + Phase 1F-C regression**

```bash
pytest -q \
  tests/test_operator_rollover_safety.py \
  tests/test_executive_operator_provider_failures.py \
  tests/test_executive_runtime.py \
  tests/test_operator_harness_orchestrator.py \
  tests/test_executive_os_phase1fc.py
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/operator_rollover_safety.py control_plane/executive_operator_supervisor.py tests/test_operator_rollover_safety.py tests/test_executive_operator_provider_failures.py
git commit -m "feat(exec): gate quota rollover to non-modifying Attempts"
```

---

### Task 2: Pin same-Job Phase 1F-C requeue after an accepted read-only quota terminal

**Files:**
- Modify: `tests/test_executive_coo_cycle.py`
- No production source change unless the regression exposes a concrete current-law defect.

**Interfaces:**
- Existing `CooCycle.run_once(root_job_id)` and existing Runtime `requeue_job()` law.

- [ ] **Step 1: Add a discriminating requeue regression**

Given a current read-only `plan` Job whose P1 became `RATE_LIMITED` through Task 1:

```python
outcome = CooCycle(runtime).run_once(root.job_id)
assert outcome.action == "REQUEUED"
assert outcome.selected_job_id == plan_job.job_id
requeued = runtime.jobs.get_job(plan_job.job_id)
assert requeued.status is JobStatus.QUEUED
assert requeued.attempt_count == 1
assert requeued.current_attempt_id is None
```

Require exactly one `JOB_REQUEUED` event naming P1 as `previous_attempt_id`. No new Job is created; root/plan lineage, authority and plan identity stay unchanged.

- [ ] **Step 2: Pin no requeue when Task 1 classified reconciliation-required**

A write-capable quota fixture must remain on its current/blocked Attempt state and produce zero `JOB_REQUEUED` event from OCR-5.

- [ ] **Step 3: Run regression**

```bash
pytest -q tests/test_executive_coo_cycle.py tests/test_operator_rollover_safety.py tests/test_executive_operator_provider_failures.py
```

- [ ] **Step 4: Commit the regression**

```bash
git add tests/test_executive_coo_cycle.py
git commit -m "test(exec): pin read-only quota requeue continuity"
```

---

### Task 3: Prove the normal accepted claim path selects a different capacity-identified Claude realm

**Files:**
- Create: `tests/test_operator_cross_realm_capacity_claim.py`
- Production Capacity Fabric/claim source remains owned by accepted CF2-I and is **not modified by OCR-5** unless a separately reviewed defect is found.

**Interfaces:**
- Existing command-bound Phase 1F-C dispatch/claim path after Task-2 requeue.
- Consumes two Workers whose placement/capacity evidence is already valid under accepted CF2-I + OCR-2C.

- [ ] **Step 1: Build the two-realm fixture**

```text
realm A / Worker A / accepted capacity identity A -> source P1 RATE_LIMITED/unavailable
realm B / Worker B / accepted capacity identity B -> AVAILABLE
same RF1 lawful quality/execution tier
same required non-modifying execution profile/authority class
```

- [ ] **Step 2: Dispatch through the normal COO cycle/claim path**

Do not pass `worker_id=B` from rollover code. Run the same current command-bound dispatcher that any queued orchestration Job uses.

- [ ] **Step 3: Assert new Attempt identity and placement**

Require:

```text
P2.job_id == P1.job_id
P2.attempt_number == 2
P2.worker_id != P1.worker_id
P2 placement/account realm != P1 placement/account realm
P2 capacity identity == accepted realm B identity
same root/job/role/authority/plan lineage
```

No `ROLLOVER_SELECTED` event/table is introduced; existing `JOB_CLAIMED`/accepted Capacity Fabric evidence remains the claim receipt.

- [ ] **Step 4: Add negative capacity cases**

No claim when realm B capacity is stale/unknown, OCR-2C capacity identity is absent/invalidated, wrong RF1 tier/profile, auth/principal incompatible, only realm A remains rate-limited, or Attempt limit is exhausted.

- [ ] **Step 5: Run integration + current claim regressions**

```bash
pytest -q tests/test_operator_cross_realm_capacity_claim.py tests/test_executive_runtime.py tests/test_executive_coo_cycle.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_operator_cross_realm_capacity_claim.py
git commit -m "test(exec): prove normal claim selects replacement Claude realm"
```

---

### Task 4: Bind P1 -> P2 with one immutable OCR-3 continuation after P2 session attestation

**Files:**
- Modify: `control_plane/executive_operator_supervisor.py`
- Create: `tests/test_operator_cross_realm_continuation.py`
- Modify: `tests/test_operator_continuation_integration.py`

**Interfaces:**
- Existing OCR-3 `build_current_continuation_draft(...)`, `prepare_operator_continuation(...)`, RuntimeBinding projection and ACK Event path.

- [ ] **Step 1: Write RED-first ordering test**

Required order is exactly:

```text
P2 claim on realm B
-> P2 TX-2/TX-3 provider session bound
-> P2 TX-4 attestation/admission ALLOW
-> build_current_continuation_draft(P1, P2, current refs)
-> Executive PREPARE finalizes/mints the one capsule for P2
-> first P2 TX-5 input carries exact prepared capsule bytes + ordinary role prompt
-> provider turn acceptance/TX-5 APPLIED
-> exact continuation ACK event for P2 session/capsule
```

No finalized capsule/capsule id exists before PREPARE.

- [ ] **Step 2: Add deterministic continuation renderer**

Pure renderer:

```text
MMX/OPERATOR_CONTINUATION_V1
capsule_id=<prepared sha256>
target_attempt_id=<P2>
<canonical minified prepared capsule JSON>

<ordinary role input follows>
```

Caller/model cannot omit/change prefix fields.

- [ ] **Step 3: Prove no transcript transplantation**

Continuation may carry only contract-approved source Attempt/checkpoint/reference material. It must not copy P1 native provider transcript, P1 native session as target identity, credential/account PII or hidden provider memory into P2.

- [ ] **Step 4: Prove immutable PREPARE replay**

Same P2 + same semantic draft/session -> same prepared bytes/id and one PREPARED Event. Source/ref movement after PREPARE must conflict/trigger current reconciliation/cancel law; it must not rewrite P2 capsule. Provider-dispatch uncertainty reuses exact prepared bytes/id.

- [ ] **Step 5: Add exact ACK tests**

Wrong capsule, P2 provider session change, wrong Attempt, first work turn without a PREPARED continuation, or TX-5 effect unknown must refuse ACK/continuation advancement. ACK is not Job/Wake completion.

- [ ] **Step 6: Run/commit**

```bash
pytest -q tests/test_operator_cross_realm_continuation.py tests/test_operator_continuation_integration.py tests/test_executive_operator_supervisor.py

git add control_plane/executive_operator_supervisor.py tests/test_operator_cross_realm_continuation.py tests/test_operator_continuation_integration.py
git commit -m "feat(exec): continue read-only Fable Job on fresh realm"
```

---

### Task 5: End-to-end hermetic positive + adverse ruler

**Files:**
- Create: `tests/test_operator_cross_realm_rollover.py`

- [ ] **Step 1: Positive sequence**

Prove in one fixture:

```text
strict-v2 root R + read-only plan Job P
P1 claim realm A (capacity identity A)
P1 OHF starts/attests and quota-fails before candidate
P1 exact shutdown/reconcile
NON_MODIFYING_ATTEMPT classifier PASS
P1 -> RATE_LIMITED
CooCycle -> REQUEUED same Job P
normal claim -> P2 realm B (capacity identity B)
P2 fresh provider session S2 + attestation ALLOW
current continuation draft -> one PREPARED capsule
first P2 work turn carries exact capsule
TX-5 APPLIED -> continuation ACK
P2 valid read-only plan result/seal
P2 clean shutdown
P2 COMPLETED
CooCycle accepts/adopts normal plan result
```

- [ ] **Step 2: Assert Fable logical continuity**

Stable:

```text
root_job_id
target seat coo
logical session_alias/commission context
same plan Job id
Phase 1F-C lineage/effective authority ceiling
```

Changed:

```text
Attempt P1 -> P2
Worker/realm A -> B
provider session S1 -> S2
RuntimeBinding identity/generation as dictated by OCR-3
```

- [ ] **Step 3: Mandatory adverse ruler**

Repeat the failure point with each condition and require **zero realm-B claim / zero P2 session**:

```text
WRITE_BRANCH grant
non-empty allowed write paths
write_capable execution profile
unreconciled EFFECT_UNKNOWN
process liveness UNKNOWN
provider writer HELD/UNKNOWN
source capacity identity invalidated
```

The externally visible state is `RECONCILIATION_REQUIRED`/blocked, not `REBINDING`.

- [ ] **Step 4: Prove no duplicate plane**

Source/schema census asserts no rollover queue/table/daemon/provider scheduler/workspace mutation log/session store was added.

- [ ] **Step 5: Run focused/full relevant suite and commit**

```bash
pytest -q \
  tests/test_operator_rollover_safety.py \
  tests/test_executive_operator_provider_failures.py \
  tests/test_operator_cross_realm_capacity_claim.py \
  tests/test_operator_cross_realm_continuation.py \
  tests/test_operator_cross_realm_rollover.py \
  tests/test_executive_coo_cycle.py \
  tests/test_executive_runtime.py \
  tests/test_executive_os_phase1fc.py

git add tests/test_operator_cross_realm_rollover.py
git commit -m "test(exec): prove safe cross-realm Fable rollover"
```

---

### Task 6: Real two-subscription production canary

**Authority:** separately released production proof only after Tasks 1-5, all dependencies and current host/provider gates are accepted.

**Files:**
- No source modification during canary unless a reproducible defect is found; any defect returns under `REVIEW_RETURN` before retry.
- Sanitized proof artifact only under the current evidence convention.

- [ ] **Step 1: Select the harmless read-only Fable coordination/plan canary**

Use one real orchestration Job whose effective grant/profile independently passes the exact `NON_MODIFYING_ATTEMPT` classifier. Do not use a write-capable implementation Job merely to demonstrate rollover.

- [ ] **Step 2: Start on capacity-identified realm A**

Require current OCR-1 worker-context auth, OCR-2C capacity identity, CF2 claim receipt, exact provider/OHF session/attestation and current RuntimeBinding projection.

- [ ] **Step 3: Trigger/observe a truthful quota boundary without fabricating provider state**

Use a naturally exhausted/limited realm or a provider-supported bounded canary condition. Do not corrupt credentials, mutate quota ledgers or manufacture a 429. Preserve exact provider outcome evidence.

- [ ] **Step 4: Execute the canonical rollover chain**

Require:

```text
exact shutdown/reconcile
NON_MODIFYING_ATTEMPT PASS
P1 RATE_LIMITED
same Job requeued
normal Capacity Fabric claim picks realm B
fresh P2 provider session
one immutable prepared continuation
first-turn ACK
continued real result
```

- [ ] **Step 5: Run one adverse live refusal or production-faithful shadow**

A write-capable/effect-uncertain equivalent must stop at `RECONCILIATION_REQUIRED` with zero cross-realm dispatch. Do not induce a real ambiguous modification merely for the test if a production-faithful shadow can prove the refusal path.

- [ ] **Step 6: Return exact evidence to Sol**

Return source/target Job/Attempt/Worker/realm/capacity identities, provider outcome class, safety-classification receipt, requeue/claim events, session/binding identities, continuation PREPARE/ACK receipts, result/closeout, adverse refusal, zero-duplicate-plane proof and exact current heads. No credential/account PII.

## Stop Condition

OCR-5 reaches `PROVEN_LIVE` only when a genuine read-only two-subscription canary preserves one Fable/COO logical responsibility through two Executive Attempts and a fresh provider session, with canonical capacity identity and one immutable continuation capsule, and the adverse ruler proves write-capable/effect-uncertain interruptions do **not** fail over. Slack/Steward presentation is still OCR-6; multi-host is OCR-7.