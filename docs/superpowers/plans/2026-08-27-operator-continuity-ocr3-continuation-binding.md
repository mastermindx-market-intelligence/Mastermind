# OCR-3 Continuation Capsule & RuntimeBinding Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a newly claimed Operator Harness Attempt one immutable, source-grounded continuation capsule and derive its exact current Wake `RuntimeBinding` from existing Executive/Operator Harness state without creating another session, retry or memory store.

**Architecture:** Split continuation into a pure `OperatorContinuationDraft` containing semantic current-source material and a finalized `OperatorContinuation` whose `generated_at` and `capsule_id` are minted atomically by the fenced Executive PREPARE transaction. The existing Executive Event table is the idempotency authority: one target Attempt gets at most one prepared capsule, and every retry/reconciliation reuses those exact bytes. RuntimeBinding remains a read-only projection of the current OHF epoch/generation/provider session + accepted placement evidence; no new SQLite table or Git runtime registry is introduced.

**Tech Stack:** Python 3.12, existing `control_plane.executive_runtime`, `control_plane.operator_harness_contract`, `control_plane.executive_operator_harness_port`, `control_plane.session_targets.RuntimeBinding`, canonical JSON/SHA-256, pytest.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuation-idempotency-amendment.md`

## Global Constraints

- Do not start colliding RuntimeBinding/session-target implementation while active Wake PR #174 owns the same source path. Reconcile/merge/rebase rather than editing #174's carrier.
- No new SQLite table, capsule cache/file, session database, memory/RAG store, replay cursor, retry registry, queue or scheduler.
- External caller/model/adapter/Slack/OpenClaw may not author `generated_at` or `capsule_id`.
- `build_current_continuation_draft()` returns semantic draft material only. Finalization and durable PREPARE happen together under the current target Attempt lease/fence.
- One target Attempt has at most one `OPERATOR_CONTINUATION_PREPARED`. Same semantic replay returns byte-identical finalized capsule; changed semantic draft or provider session conflicts.
- Before PREPARE, source facts may move and the draft may be rebuilt. After PREPARE, source movement never mutates the prepared capsule; if it invalidates safety/authority, refuse/cancel/reconcile the target Attempt rather than preparing capsule #2.
- The capsule contains bounded canonical refs/checkpoint/current-action material, not credentials, raw provider transcripts, raw Slack history or complete Agent OS databases.
- Cross-realm provider/account/placement change has already created a new Attempt before this wave prepares continuation.
- Continuation ACK proves the exact bound provider session accepted/consumed the exact prepared continuation-bearing turn. It is not Job completion and not automatically Wake `TARGET_ACKNOWLEDGED`.
- `RuntimeBinding` stays a projection. Native handles/account labels remain runtime evidence and never enter `config/wake_session_targets.json`.

---

### Task 1: Implement closed draft, finalized capsule and ACK contracts

**Files:**
- Create: `control_plane/operator_continuation.py`
- Create: `tests/test_operator_continuation.py`

**Interfaces:**
- Produces: `OPERATOR_CONTINUATION_SCHEMA`, `OPERATOR_CONTINUATION_ACK_SCHEMA`, `OperatorContinuationDraft`, `OperatorContinuation`, `ContinuationAck`, `semantic_draft_digest()`, `finalize_continuation()`, `validate_continuation()`, `validate_continuation_ack()`.
- `finalize_continuation()` is pure but accepts `generated_at` only from the trusted Executive PREPARE implementation; it is not exposed as the normal current-source builder API.

- [ ] **Step 1: Write RED-first draft/finalized closed-shape tests**

Draft semantic fields are exactly:

```text
root_job_id
job_id
source_attempt_id
target_attempt_id
operation_key
target_seat
session_alias
effective_grant_digest
source_authority_refs
agentos_refs
github_state
prior_attempt_receipt
checkpoint
slack_dialogue_ref
accepted_ruling_refs
next_action
known_unknowns
source_revisions
```

Draft rejects `generated_at`, `capsule_id`, provider account labels, native session ids other than the separately bound current provider session, unknown fields and secret-shaped leaves.

Finalized wire adds only:

```text
schema = mastermind.operator_continuation.v1
generated_at
capsule_id
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_operator_continuation.py
```

- [ ] **Step 3: Implement canonical validation and semantic digest**

Use strict closed JSON, bounded IDs/strings, strict UTC, full Git object ids, lowercase SHA-256 digests, bounded unique refs, no control characters and the existing secret-shaped-value families.

```python
def semantic_draft_digest(draft: OperatorContinuationDraft) -> str:
    return sha256(canonical_json(draft.to_dict()).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Implement trusted finalization**

```python
def finalize_continuation(
    draft: OperatorContinuationDraft,
    *,
    generated_at: str,
) -> OperatorContinuation:
    final_without_id = {
        "schema": OPERATOR_CONTINUATION_SCHEMA,
        **draft.to_dict(),
        "generated_at": generated_at,
    }
    capsule_id = sha256(canonical_json(final_without_id).encode("utf-8")).hexdigest()
    return OperatorContinuation.from_dict({**final_without_id, "capsule_id": capsule_id})
```

Tests prove same draft + same Executive timestamp gives exact bytes/id and any semantic field change changes the semantic digest.

- [ ] **Step 5: Implement closed ACK validation**

ACK wire:

```python
{
    "schema": "mastermind.operator_continuation_ack.v1",
    "target_attempt_id": "ATT-target",
    "capsule_id": "<64hex>",
    "provider_session_id": "provider-session-opaque",
    "accepted": True,
}
```

Reject wrong/blank Attempt, capsule, session or `accepted != True`.

- [ ] **Step 6: Run tests/compile and commit**

```bash
pytest -q tests/test_operator_continuation.py
python3 -m compileall -q control_plane/operator_continuation.py

git add control_plane/operator_continuation.py tests/test_operator_continuation.py
git commit -m "feat(exec): add idempotent continuation contracts"
```

---

### Task 2: Build semantic drafts only from current typed canonical sources

**Files:**
- Create: `control_plane/operator_continuation_sources.py`
- Create: `tests/test_operator_continuation_sources.py`
- Modify: `tests/test_operator_continuation.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ContinuationExternalRefs:
    operation_key: str
    target_seat: str
    session_alias: str
    source_authority_refs: tuple[str, ...]
    agentos_refs: tuple[str, ...]
    github_state: Mapping[str, Any]
    slack_dialogue_ref: Mapping[str, Any] | None
    accepted_ruling_refs: tuple[str, ...]
    source_revisions: Mapping[str, str]


def build_current_continuation_draft(
    runtime: Runtime,
    *,
    source_attempt_id: str,
    target_attempt_id: str,
    refs: ContinuationExternalRefs,
) -> OperatorContinuationDraft:
    ...
```

No timestamp/capsule id parameter is accepted.

- [ ] **Step 1: Write RED-first Runtime fixture tests**

Create one Job with attempt limit >=2; Attempt 1 terminal `RATE_LIMITED` with checkpoint; requeue; Attempt 2 current on a different Worker/account placement. Build a draft P1 -> P2.

Refuse when source Attempt is nonterminal, target is noncurrent, Jobs differ, cross-realm claim is false, effective grant is absent where required, Git refs/source revisions malformed or missing, or an external ref attempts to carry provider credential/session authority.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_operator_continuation_sources.py
```

- [ ] **Step 3: Implement current Runtime reads**

Use existing typed Job/Attempt/checkpoint/placement/grant records. `prior_attempt_receipt` is a closed machine-derived status/identity receipt; do not copy arbitrary provider error prose. `checkpoint` uses existing `JobPayload` material truthfully, including null/empty state when absent.

- [ ] **Step 4: Prove pre-PREPARE source movement rebuilds the draft**

Change a material source ref before PREPARE and require a different semantic draft digest. Change target currentness/authority and require refusal. No durable event is written by draft building.

- [ ] **Step 5: Run tests and commit**

```bash
pytest -q tests/test_operator_continuation.py tests/test_operator_continuation_sources.py

git add control_plane/operator_continuation_sources.py tests/test_operator_continuation.py tests/test_operator_continuation_sources.py
git commit -m "feat(exec): derive continuation draft from current facts"
```

---

### Task 3: Derive ABA-safe RuntimeBinding from the current OHF writer

**Files:**
- Create: `control_plane/runtime_binding_projection.py`
- Modify: `control_plane/executive_runtime.py` only if one read-only typed query is required.
- Create: `tests/test_runtime_binding_projection.py`

**Interfaces:**
- Produces: `ActiveOperatorBindingFacts` (if needed) and `project_runtime_binding(runtime, attempt_id, target) -> RuntimeBinding`.

- [ ] **Step 1: Write RED-first projection tests**

Fixture has one current active OPERATOR_HARNESS Attempt, one CURRENT epoch, one Executive writer generation, bound `provider_session_id` and accepted placement/account/provider evidence.

Require projected:

```text
session_alias = target.session_alias
native_handle = current provider_session_id
account_label = accepted placement account_label
binding_generation = current process generation_number
binding_id = deterministic opaque bind-* derived from Attempt + session_epoch identity
reasoning_surface = target/current accepted provider surface
```

Refuse no/multiple writers, noncurrent epoch/Attempt, unbound provider session, missing placement/principal evidence, seat/surface mismatch, or non-OHF Attempt.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/test_runtime_binding_projection.py
```

- [ ] **Step 3: Add a read-only exact-current query only if needed**

Any new Runtime method uses `store.read()` only and returns the one current OHF epoch/generation plus already-accepted provider/account placement facts. It may not persist RuntimeBinding.

- [ ] **Step 4: Implement ABA-safe binding id**

```python
binding_id = "bind-" + sha256(
    f"{attempt_id}:{session_epoch_id}".encode("utf-8")
).hexdigest()[:40]
```

Same epoch/process replacement -> same binding id, higher generation. New epoch or Attempt -> different binding id. Illegal provider-session drift -> refuse.

- [ ] **Step 5: Run regression/commit**

```bash
pytest -q tests/test_runtime_binding_projection.py tests/test_operator_harness_contract.py tests/test_executive_runtime.py

git add control_plane/runtime_binding_projection.py control_plane/executive_runtime.py tests/test_runtime_binding_projection.py
git commit -m "feat(exec): project Wake binding from Operator Harness"
```

---

### Task 4: Make Executive PREPARE the sole continuation identity/idempotency authority

**Files:**
- Modify: `control_plane/executive_runtime.py`
- Modify: `control_plane/executive_operator_harness_port.py`
- Modify: `control_plane/operator_continuation.py`
- Create: `tests/test_operator_continuation_events.py`

**Interfaces:**
- Produces on the Attempt-bound port:

```python
prepare_operator_continuation(
    attempt_id: str,
    draft: OperatorContinuationDraft,
) -> OperatorContinuation

acknowledge_operator_continuation(
    attempt_id: str,
    ack: ContinuationAck,
) -> None
```

- [ ] **Step 1: Write RED-first PREPARE replay tests**

PREPARE requires the active target Attempt lease/fence, exact current provider session and canonical source/target facts. Its deterministic command id is:

```text
operator-continuation:prepare:<target_attempt_id>
```

subject to current command-id law.

First PREPARE:

1. re-read source terminal / target current / current provider session;
2. revalidate the supplied semantic draft against current facts;
3. mint `generated_at` from `RuntimeStore.now_ms()`;
4. finalize capsule and semantic digest;
5. append exactly one `OPERATOR_CONTINUATION_PREPARED` Event.

PREPARED event payload contains the complete bounded finalized capsule plus at least explicit semantic digest/provider session fields so exact reconstruction is possible without a new store.

- [ ] **Step 2: Prove byte-identical replay**

Call PREPARE twice with same target Attempt, same semantic draft and same current provider session. Require:

```text
returned canonical bytes identical
capsule_id identical
generated_at identical
exactly one PREPARED Event
```

- [ ] **Step 3: Prove conflicts refuse capsule #2**

Same target Attempt + changed semantic draft, source Attempt, authority/source ref or provider session -> conflict/reconciliation. No new PREPARED event and no new capsule id.

- [ ] **Step 4: Implement deterministic ACK Event**

ACK command id derives from target Attempt. It validates exact prepared capsule + exact current provider session. Matching replay is idempotent; changed capsule/session conflicts. Event is `OPERATOR_CONTINUATION_ACKNOWLEDGED` and does not mutate Job completion/Wake ACK.

- [ ] **Step 5: Prove zero schema change**

Compare SQLite schema digest before/after. Existing Event rows are the only durable addition.

- [ ] **Step 6: Run Runtime/port tests and commit**

```bash
pytest -q tests/test_operator_continuation_events.py tests/test_executive_runtime.py tests/test_executive_operator_harness_port.py

git add control_plane/executive_runtime.py control_plane/executive_operator_harness_port.py control_plane/operator_continuation.py tests/test_operator_continuation_events.py
git commit -m "feat(exec): prepare continuation in Executive event plane"
```

---

### Task 5: End-to-end hermetic two-Attempt preparation, binding and ACK proof

**Files:**
- Create: `tests/test_operator_continuation_integration.py`

- [ ] **Step 1: Build the fixture**

Create two workers/account labels, one Job with attempt limit >=2, P1 terminal `RATE_LIMITED` with checkpoint, requeue, P2 claim on other placement, then create/bind/attest one current OHF P2 session.

- [ ] **Step 2: Assert the positive chain**

```python
draft = build_current_continuation_draft(...)
capsule = port.prepare_operator_continuation(p2, draft)
replay = port.prepare_operator_continuation(p2, build_current_continuation_draft(...))
binding = project_runtime_binding(...)
assert replay == capsule
assert binding.account_label == second_account
```

Simulate exact first provider turn acceptance carrying the prepared capsule, then ACK and require exactly one PREPARED + one ACKNOWLEDGED Event.

- [ ] **Step 3: Assert post-PREPARE source movement does not rewrite capsule**

Move a Git/Agent OS reference after PREPARE. A new draft may differ, but PREPARE for the same P2 must conflict rather than update the existing capsule. If the source movement invalidates safety, the test uses existing cancel/reconcile law; no capsule mutation occurs.

- [ ] **Step 4: Assert timeout/effect-uncertain dispatch reuses the same capsule**

After PREPARE, simulate provider-dispatch uncertainty. The recovery path may reconcile/retry only with the exact prepared capsule identity/bytes for P2; it cannot mint another continuation.

- [ ] **Step 5: Run focused/full relevant suite**

```bash
pytest -q \
  tests/test_operator_continuation.py \
  tests/test_operator_continuation_sources.py \
  tests/test_operator_continuation_events.py \
  tests/test_operator_continuation_integration.py \
  tests/test_runtime_binding_projection.py \
  tests/test_executive_operator_harness_port.py \
  tests/test_executive_runtime.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_operator_continuation_integration.py
git commit -m "test(exec): prove idempotent two-Attempt continuation"
```

## Stop Condition

OCR-3 stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT` when one target Attempt can prepare exactly one immutable continuation capsule, exact replay returns identical bytes/id with one Event, changed semantics/session refuse, ACK binds the exact provider session/capsule, RuntimeBinding is derived ABA-safely from OHF state, and zero new lifecycle/session/memory store exists. OCR-3 does not perform provider placement, provider failover, Slack projection or production arming.