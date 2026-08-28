# OCR-5 Cross-Realm Fable Rollover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that one current Phase 1F-C Fable/COO orchestration Job can survive a real Claude subscription quota boundary by ending Attempt 1 truthfully, letting the existing COO cycle requeue the same Job, claiming a different eligible Claude realm for Attempt 2, creating a fresh provider session, delivering/acknowledging the deterministic continuation capsule, and completing through the unchanged orchestration result law—with zero cross-realm movement when the source effect is ambiguous.

**Architecture:** This wave composes existing owners; it does not add a rollover scheduler. `ExecutiveOperatorSupervisor`/Operator Harness observes the provider failure and proves shutdown. Existing `AttemptRegistry.rate_limit_attempt()` terminalizes the old Attempt and marks that quota class `RATE_LIMITED`. Existing `CooCycle.run_once()` already gives recoverable same-Job requeue precedence. Existing CF2-I claim then considers only available eligible capacity and records the new placement. OCR-3 builds the continuation capsule and derives RuntimeBinding. OCR-4 runs the new Claude provider session. Fable continuity stays at root Job + COO seat + logical session alias; the provider Attempt changes underneath it.

**Tech Stack:** Python 3.12, existing `executive_runtime`, `executive_coo_cycle`, `executive_operator_supervisor`, Operator Harness, OCR-3 continuation contract, OCR-4 Claude adapter, CF2-I placement, pytest.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-fable-root-seat-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-auth-compatibility-amendment.md`

## Dependency Gate

Do not implement/arm OCR-5 until:

```text
CF2-I accepted with real multi-account claim evidence
RF1 accepted
HF1 accepted
PF1 real Claude sealed-worker accepted
OCR-1 V2 proves at least two distinct native Claude realms
OCR-3 continuation/binding implementation accepted
OCR-4 one-realm sustained Claude operator accepted
```

Phase 1F-C policy remains unchanged: non-review orchestration Jobs have at most two Attempts. This wave proves one retry path; it does not raise that ceiling.

## Global Constraints

- No `rollover_daemon`, retry table, provider failover service, account scheduler, new Job role or Fable session table.
- Rate-limit detection cannot itself create Attempt 2. It may only produce typed adapter/reconcile evidence. Executive terminalization -> CooCycle requeue -> Executive claim remain distinct steps.
- `QUOTA_OR_RATE_LIMIT` is accepted for automatic same-Job recovery only when the exact source Attempt has **no effect-unknown provider operation, no accepted candidate/result/seal that closes the retry path, and no live/unknown provider writer**.
- Any `OPERATOR_OPERATION_EFFECT_UNKNOWN` relevant to the current provider start/turn/stop path blocks `rate_limit_attempt`/requeue until reconciled under existing OHF law.
- Old realm remains `RATE_LIMITED`/unavailable through its current Executive/Provider Control owners; claim never “excludes Claude5 by name.” It selects from the available eligible set.
- Attempt 2 must have a different accepted placement/account label from Attempt 1 for the cross-realm proof. A same-realm claim is not accepted as OCR-5 even if the provider session changes.
- Cross-realm always starts a fresh provider session. `SupportsSessionResume` is forbidden for Attempt 2 because account/auth-home changed.
- Continuation ACK is deterministic runtime evidence: the exact current provider session accepts the first TX-5 turn whose input binds the exact `capsule_id`; it is not model-authored authority and is not automatically Wake `TARGET_ACKNOWLEDGED`.
- The same Job objective, immutable lineage, authority/effective grant constraints, workspace/base policy and role result schema remain controlling. Rollover cannot widen or “refresh” them.
- Slack/Steward projection is OCR-6 and does not block the core Executive rollover proof.

---

### Task 1: Add fail-closed operator provider-failure terminalization

**Files:**
- Modify: `control_plane/executive_operator_supervisor.py`
- Modify only if a generic helper is needed: `control_plane/operator_harness_orchestrator.py`
- Create: `tests/test_executive_operator_provider_failures.py`

**Interfaces:**
- New supervisor-private decision path only; no new public lifecycle store.
- Consumes an exact `ReconcileObservation` + current Runtime/Event evidence.
- May call existing `runtime.attempts.rate_limit_attempt(...)` only after shutdown/epoch abandonment.

- [ ] **Step 1: Write RED-first rate-limit terminalization test**

Fixture:

```text
strict v2 root
plan Job attempt_limit=2
Attempt P1 claimed on worker claude-a / account_label claude-pro-01
OHF profile/session/turn start committed
provider returns QUOTA_OR_RATE_LIMIT before candidate/result
helper/process generation gracefully stopped
PROVEN_DEAD + ProviderWriterState.RELEASED
no EFFECT_UNKNOWN receipt
no candidate/result seal
```

Expected:

```python
job = supervisor._terminalize_provider_failure(...)
assert job.status is JobStatus.RATE_LIMITED
assert runtime.attempts.get_attempt(p1).status is AttemptStatus.RATE_LIMITED
assert quota("claude-a").status is WorkerStatus.RATE_LIMITED
```

- [ ] **Step 2: Write adverse RED tests**

Refuse terminalization when any of these is true:

- current generation liveness is `UNKNOWN`;
- provider writer is `UNKNOWN`/`HELD`;
- current epoch still exists/writer held;
- any provider operation has unreconciled `EFFECT_UNKNOWN`;
- candidate/result/seal already exists and current Phase 1F-C recovery law disallows retry;
- failure class is generic transport/model failure rather than `QUOTA_OR_RATE_LIMIT`;
- Attempt is no longer current;
- source Job has exhausted attempt limit.

No refusal may call requeue/claim/start another provider.

- [ ] **Step 3: Run RED**

```bash
pytest -q tests/test_executive_operator_provider_failures.py
```

- [ ] **Step 4: Implement deterministic safety predicate**

Prefer a pure helper such as:

```python
@dataclass(frozen=True)
class ProviderFailureTerminalization:
    allowed: bool
    target_status: AttemptStatus | None
    reason_codes: tuple[str, ...]


def classify_operator_provider_failure(
    *,
    failure_class: AdapterFailureClass,
    reconcile: ReconcileObservation,
    effect_unknown_count: int,
    candidate_or_result_exists: bool,
    attempt_limit_remaining: bool,
) -> ProviderFailureTerminalization:
    ...
```

The Runtime/Event query that feeds it is supervisor-owned and rechecks the exact current Attempt/generation. No model/adapter boolean may assert `effect_unknown_count=0` or retry eligibility.

- [ ] **Step 5: Terminalize only after existing shutdown law**

Required sequence:

```text
provider failure observed
-> graceful stop / exact reconcile
-> generation PROVEN_DEAD + writer RELEASED
-> epoch ABANDONED under existing Executive transaction
-> safety predicate re-read
-> rate_limit_attempt(...)
```

Use a bounded deterministic `JobPayload` checkpoint such as machine status + next action; do not pretend provider output exists.

- [ ] **Step 6: Run focused + Phase 1F-C regressions**

```bash
pytest -q \
  tests/test_executive_operator_provider_failures.py \
  tests/test_executive_runtime.py \
  tests/test_operator_harness_orchestrator.py \
  tests/test_executive_os_phase1fc.py
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/executive_operator_supervisor.py control_plane/operator_harness_orchestrator.py tests/test_executive_operator_provider_failures.py
git commit -m "feat(exec): terminalize reconciled operator quota failures"
```

---

### Task 2: Prove existing CooCycle requeue preserves the same orchestration Job

**Files:**
- Modify only if missing regression coverage: `tests/test_executive_coo_cycle.py`
- No production code change unless a concrete bug appears.

**Interfaces:**
- Existing `CooCycle.run_once(root_job_id)`.

- [ ] **Step 1: Add a discriminating regression**

Given the Task-1 state:

```python
first = CooCycle(runtime).run_once(root.job_id)
assert first.action == "REQUEUED"
assert first.selected_job_id == plan_job.job_id
requeued = runtime.jobs.get_job(plan_job.job_id)
assert requeued.status is JobStatus.QUEUED
assert requeued.attempt_count == 1
assert requeued.current_attempt_id is None
```

Assert exactly one `JOB_REQUEUED` event names P1 as `previous_attempt_id`. No new Job is created and root/plan lineage/digests remain byte-equal.

- [ ] **Step 2: Prove requeue refuses effect ambiguity**

This should normally be impossible because Task 1 did not terminalize while ambiguity exists. Add a hostile fixture attempting to fabricate a RATE_LIMITED Job alongside unresolved OHF effect evidence and ensure a reviewed upstream predicate or CooCycle lineage validation refuses. If current CooCycle cannot see an impossible corrupted state, keep the corruption test at the Task-1 gate rather than duplicating policy here.

- [ ] **Step 3: Run tests**

```bash
pytest -q tests/test_executive_coo_cycle.py tests/test_executive_operator_provider_failures.py
```

- [ ] **Step 4: Commit only if test/source changed**

```bash
git add tests/test_executive_coo_cycle.py
git commit -m "test(exec): pin same-Job quota requeue for operator continuity"
```

---

### Task 3: Claim a different realm through CF2-I, not rollover-specific selection

**Files:**
- Modify current CF2-I integration tests only after CF2-I is accepted/current; likely `tests/test_executive_capacity_claim.py` or its landed equivalent.
- Modify no provider-selection algorithm specifically for OCR-5 unless a proven CF2-I defect exists.

**Interfaces:**
- Existing claim path after CooCycle requeue.
- Consumes current `mastermind.provider_capacity.v1` evidence through accepted CF2-I seam.

- [ ] **Step 1: Fixture two equivalent Claude realms**

```text
claude-pro-01 -> Worker A -> RATE_LIMITED / not AVAILABLE
claude-pro-02 -> Worker B -> AVAILABLE, same RF1 quality/execution tier, same required profile capability
```

- [ ] **Step 2: Dispatch the requeued plan Job through the normal command-bound CooCycle dispatcher**

The next `run_once(root)` should eventually use the existing dispatcher/claim operation and return Attempt P2 on Worker B. Do not pass `worker_id=B` from the rollover code in production; the test may inspect the deterministic result but selection belongs to CF2-I.

- [ ] **Step 3: Assert placement evidence**

```text
P2.job_id == P1.job_id
P2.attempt_number == 2
P2.worker_id != P1.worker_id
P2 placement/account_label == claude-pro-02
P1 placement/account_label == claude-pro-01
same Job/root/role/authority/plan lineage
```

`JOB_CLAIMED` must carry the accepted CF2-I capacity evidence; no `ROLLOVER_SELECTED` event/table is introduced.

- [ ] **Step 4: Negative candidates**

Prove no claim when:

- realm B capacity is stale/unknown under CF2-I law;
- realm B is wrong RF1 suitability tier;
- realm B profile/auth principal is incompatible;
- only realm A exists and remains RATE_LIMITED;
- attempt limit is exhausted.

- [ ] **Step 5: Run current CF2/claim/Phase1F suites**

Use exact file names landed by CF2-I at implementation time.

- [ ] **Step 6: Commit only bounded integration changes**

```bash
git commit -m "test(exec): prove capacity claim moves a requeued Job to another realm"
```

---

### Task 4: Bind P1 -> P2 through OCR-3 continuation without transcript transplantation

**Files:**
- Modify: `control_plane/executive_operator_supervisor.py`
- Modify: `control_plane/operator_continuation_sources.py`
- Modify: `tests/test_operator_continuation_integration.py`
- Create: `tests/test_operator_cross_realm_continuation.py`

**Interfaces:**
- Existing OCR-3 `build_current_continuation(...)`, RuntimeBinding projection and Event-plane preparation/ACK.

- [ ] **Step 1: Write RED-first cross-realm capsule test**

After P2 claim but before P2 provider start, build a capsule with:

```text
source_attempt_id = P1
target_attempt_id = P2
same root/plan Job
same operation/commission context
prior_attempt_receipt.status = RATE_LIMITED
P1 checkpoint = deterministic pre-candidate provider failure state
P2 placement = claude-pro-02
```

Assert no provider transcript/session id from P1 appears in the semantic continuation body except the exact source Attempt receipt fields explicitly allowed by the contract.

- [ ] **Step 2: Render the exact continuation preamble**

Add a deterministic renderer, for example:

```text
MMX/OPERATOR_CONTINUATION_V1
capsule_id=<sha256>
target_attempt_id=<P2>
<canonical minified capsule JSON>

<existing role prompt follows>
```

The renderer is pure. The model cannot omit or modify the capsule prefix.

- [ ] **Step 3: Prepare only after P2 provider session is bound/attested**

Sequence:

```text
P2 TX-2/TX-3/TX-4 ALLOW
-> build/revalidate current capsule against current P2
-> OPERATOR_CONTINUATION_PREPARED event binds capsule + P2 provider_session_id
-> first P2 TX-5 prompt = exact continuation preamble + ordinary role prompt
```

If source GitHub/Agent OS/source-law revisions changed materially between build and TX-5, rebuild/revalidate before provider dispatch; do not send a stale capsule and update its timestamp afterward.

- [ ] **Step 4: ACK from exact provider turn acceptance**

After the provider returns a valid `TurnStartObservation` and existing TX-5 APPLIED commits for the first P2 turn, record `OPERATOR_CONTINUATION_ACKNOWLEDGED` mechanically with:

```text
target_attempt_id = P2
capsule_id = prepared capsule
provider_session_id = exact P2 session
```

This means the exact bound provider session accepted the turn containing the exact continuation bytes. It is not model-authored executive authority, semantic agreement, Job completion or Wake ACK.

- [ ] **Step 5: Adverse tests**

Refuse:

- P2 provider session changed after preparation;
- capsule rebuilt with changed semantics under same id;
- first turn started without prepared capsule for a cross-realm Attempt;
- TX-5 response effect is unknown;
- wrong source Attempt/job/root;
- source P1 has any unresolved effect unknown;
- P2 is same account/placement in the cross-realm canary.

- [ ] **Step 6: Run tests and commit**

```bash
pytest -q tests/test_operator_continuation_integration.py tests/test_operator_cross_realm_continuation.py

git add control_plane/executive_operator_supervisor.py control_plane/operator_continuation_sources.py tests/test_operator_continuation_integration.py tests/test_operator_cross_realm_continuation.py
git commit -m "feat(exec): bind cross-realm Attempt continuation"
```

---

### Task 5: Complete the existing Fable plan role on Attempt 2

**Files:**
- Modify/add integration tests only unless a real provider-neutral supervisor composition gap remains after OCR-4.
- Likely: `tests/test_executive_operator_cross_realm_plan.py`.

- [ ] **Step 1: Build end-to-end hermetic sequence**

```text
root R + plan Job P
P1 claim realm A
P1 OHF provider quota failure before candidate
P1 exact shutdown + RATE_LIMITED
CooCycle REQUEUED P
CooCycle dispatch / CF2-I claim P2 realm B
P2 fresh Claude provider session S2
P1 -> P2 continuation PREPARED
P2 first TX-5 APPLIED -> continuation ACK
P2 valid plan candidate/result seal
P2 shutdown/epoch abandonment
P2 COMPLETED
CooCycle admits the completed plan
```

- [ ] **Step 2: Assert Fable logical continuity**

Stable across the sequence:

```text
root_job_id R
target seat coo
logical session_alias used by current root/dialogue binding
plan Job P
commission/operation context
Phase 1F-C root/plan authority and result schema
```

Changed:

```text
Attempt P1 -> P2
Worker A -> B
account label realm A -> B
provider session S1 -> S2
RuntimeBinding -> new binding life
```

No `fable` Job/role/table exists.

- [ ] **Step 3: Prove the negative integration canary**

Inject an unknown modifying/provider effect before P1 terminalization. Assert:

```text
P1 remains nonterminal/reconciliation-required
zero JOB_RATE_LIMITED
zero JOB_REQUEUED
zero P2
zero provider session on realm B
zero continuation PREPARED
```

This test is release-blocking.

- [ ] **Step 4: Run full relevant suites**

```bash
pytest -q \
  tests/test_executive_operator_provider_failures.py \
  tests/test_executive_coo_cycle.py \
  tests/test_operator_cross_realm_continuation.py \
  tests/test_executive_operator_cross_realm_plan.py
```

Then run current hosted CI/CodeQL and existing Phase 1F-C/OHF/Capacity mutation suites.

- [ ] **Step 5: Commit**

```bash
git add tests/test_executive_operator_cross_realm_plan.py
git commit -m "test(exec): prove Fable plan survives Claude realm rollover"
```

---

### Task 6: Real two-subscription rollover canary

**Files:**
- No source changes unless a concrete same-carrier defect is found.
- Sanitized evidence only.

- [ ] **Step 1: Re-pin exact accepted predecessors**

Require protected Skillpack, current Executive release, two OCR-1 distinct native realms, current CF2-I capacity evidence path, OCR-3/OCR-4 exact accepted heads and current Phase 1F-C policy.

- [ ] **Step 2: Create one harmless real strict-v2 root + plan Job**

Use a test/acceptance objective that exercises real Claude planning without a production repo mutation. Both candidate realms must be configured as equivalent lawful Claude operator capacity.

- [ ] **Step 3: Start Attempt 1 on realm A and induce a controlled safe rate-limit/drain boundary**

Preferred proof is a provider-reported genuine quota/rate-limit when operationally feasible. A separately reviewed canary-only injected failure may prove deterministic state transitions but **cannot** substitute for final provider-real quota proof.

The source Attempt must stop before candidate/result and close its provider writer exactly.

- [ ] **Step 4: Let normal CooCycle/Capacity Fabric perform the replacement**

Do not manually choose realm B after the failure. Observe:

```text
P1 RATE_LIMITED
P REQUEUED
P2 JOB_CLAIMED with realm B capacity evidence
```

- [ ] **Step 5: Prove fresh session + capsule + successful plan**

Require S2 != S1, continuation PREPARED/ACK exact to P2/S2, valid plan result, and normal Phase 1F-C completion/admission.

- [ ] **Step 6: Run adverse effect-unknown canary separately**

Use a safe canary operation where the transport reply is intentionally lost after dispatch. The system must refuse cross-realm movement until exact same-Attempt reconciliation establishes the outcome. Do not generate a real duplicate provider turn merely to prove the negative.

- [ ] **Step 7: Return to Sol**

Return:

```text
exact release/head
root Job / plan Job
P1/P2 Attempt ids
realm A/B opaque labels
capacity snapshot/claim evidence digests
provider session S1/S2 opaque ids
P1 terminal/requeue receipts
continuation capsule/prepared/ACK digests
P2 result/terminal/admission receipts
negative EFFECT_UNKNOWN zero-failover receipt
hosted CI/security/adversarial review
zero duplicate lifecycle/queue/session DB proof
```

## Stop Condition

OCR-5 stops when one real Phase 1F-C Fable planning responsibility successfully moves from one native Claude realm to another through **two Executive Attempts on the same Job**, using the normal Capacity Fabric claim path and deterministic continuation, and an adverse effect-unknown canary proves zero cross-realm failover. It does not yet claim same Slack thread/product UX, Steward automation, cross-host movement or the full five-account pool.
