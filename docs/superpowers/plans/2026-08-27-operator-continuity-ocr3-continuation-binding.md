# OCR-3 Continuation Capsule & RuntimeBinding Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a newly claimed Operator Harness Attempt a deterministic, source-grounded continuation packet and derive the exact current Wake `RuntimeBinding` from existing Executive/Operator Harness state without creating another session or memory store.

**Architecture:** Add a pure closed `mastermind.operator_continuation.v1` contract plus a runtime projection module. The capsule is rebuilt from typed Executive facts and exact external source references, hashed canonically, and supplied transiently to the provider adapter. Preparation/ACK evidence is appended only to the existing Executive Event table. RuntimeBinding is derived from the current session epoch/process generation/provider session + accepted placement evidence; no new SQLite table or Git configuration is introduced.

**Tech Stack:** Python 3.12, existing `control_plane.executive_runtime`, `control_plane.operator_harness_contract`, `control_plane.session_targets.RuntimeBinding`, canonical JSON/SHA-256, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`

## Global Constraints

- This wave starts only after active Wake PR #174 no longer owns a colliding `session_targets.py`/RuntimeBinding surface. Do not edit #174's branch or widen its completion law.
- No new SQLite table, session database, memory/RAG store, replay cursor, queue or scheduler.
- `capsule_id` is deterministic over a closed contract. Provider/model prose cannot alter source identities, Attempt IDs, authority digest or Slack/GitHub/Agent OS refs.
- The capsule contains references and bounded checkpoint/current-action material, not credentials, raw Slack history, full Agent OS databases or hidden provider transcripts.
- A cross-realm provider/account/placement change is already a new Attempt before this wave runs.
- Continuation ACK is evidence that the target provider session consumed the exact capsule; it is not Job completion or Wake `TARGET_ACKNOWLEDGED` unless a separately accepted Wake ingress establishes that mapping.
- `RuntimeBinding` stays a projection. Native handles/account labels remain runtime evidence and must not be checked into `config/wake_session_targets.json`.

---

### Task 1: Freeze the continuation wire contract

**Files:**
- Create: `control_plane/operator_continuation.py`
- Test: `tests/test_operator_continuation.py`

**Interfaces:**
- Produces: `OPERATOR_CONTINUATION_SCHEMA`, `OperatorContinuation`, `ContinuationAck`, `build_continuation()`, `validate_continuation()`, `validate_continuation_ack()`.

- [ ] **Step 1: Write failing closed-shape/digest tests**

```python
from control_plane.operator_continuation import (
    OPERATOR_CONTINUATION_SCHEMA,
    build_continuation,
    validate_continuation,
)


def _base():
    return {
        "root_job_id": "JOB-001",
        "job_id": "JOB-004",
        "source_attempt_id": "ATT-source",
        "target_attempt_id": "ATT-target",
        "operation_key": "operator-continuity-example-001",
        "target_seat": "coo",
        "session_alias": "EXECUTIVE-COO-A",
        "effective_grant_digest": "a" * 64,
        "source_authority_refs": ["github:Mastermind@" + "b" * 40],
        "agentos_refs": ["WS:EXECUTIVE-CAPACITY-FABRIC"],
        "github_state": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "base_sha": "c" * 40,
            "head_sha": "d" * 40,
            "branch": "sol/example",
            "pr": 999,
        },
        "prior_attempt_receipt": {
            "status": "RATE_LIMITED",
            "attempt_id": "ATT-source",
        },
        "checkpoint": {
            "summary": "bounded",
            "completed_steps": [],
            "current_state": "ready",
            "artifacts": [],
            "next_actions": ["continue bounded work"],
            "errors": [],
        },
        "slack_dialogue_ref": {
            "channel_id": "C0BSBM78V1N",
            "thread_ts": "1787871000.000001",
            "session_ref": "asd-session-example01",
        },
        "accepted_ruling_refs": [],
        "next_action": "continue bounded work",
        "known_unknowns": [],
        "generated_at": "2026-08-27T23:30:00Z",
        "source_revisions": {
            "mastermind": "e" * 40,
            "macro": "f" * 40,
        },
    }


def test_capsule_is_closed_and_digest_is_deterministic():
    first = build_continuation(_base())
    second = build_continuation(_base())
    assert first == second
    assert first["schema"] == OPERATOR_CONTINUATION_SCHEMA
    assert len(first["capsule_id"]) == 64
    assert validate_continuation(first) == first


def test_unknown_field_refuses():
    value = build_continuation(_base())
    value["provider_account"] = "claude5"
    with pytest.raises(ContinuationError, match="CONTINUATION_INVALID"):
        validate_continuation(value)
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_operator_continuation.py`

- [ ] **Step 3: Implement strict canonical JSON + validators**

Use a closed top-level shape exactly matching the spec. Validate:

- bounded IDs and strings;
- lowercase SHA-256 grant/capsule digests;
- full Git object IDs;
- target seat in `chairman|ceo|coo`;
- bounded unique reference arrays;
- strict UTC timestamp;
- no control characters;
- secret-shaped-value rejection using the same families already used by Agent Relay tests.

`capsule_id` is:

```python
sha256(canonical_json({all fields except capsule_id}).encode()).hexdigest()
```

- [ ] **Step 4: Add ACK contract tests and implementation**

Closed ACK wire:

```python
{
    "schema": "mastermind.operator_continuation_ack.v1",
    "target_attempt_id": "ATT-target",
    "capsule_id": "<64 hex>",
    "provider_session_id": "provider-session-opaque",
    "accepted": True,
}
```

Reject wrong Attempt, wrong capsule, blank provider session and `accepted != True` at the admission layer.

- [ ] **Step 5: Run tests and compile**

Run:

```bash
pytest -q tests/test_operator_continuation.py
python3 -m compileall -q control_plane/operator_continuation.py
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/operator_continuation.py tests/test_operator_continuation.py
git commit -m "feat(exec): add operator continuation contract"
```

---

### Task 2: Build a capsule only from typed current Executive facts

**Files:**
- Create: `control_plane/operator_continuation_sources.py`
- Modify: `tests/test_operator_continuation.py`
- Test: `tests/test_operator_continuation_sources.py`

**Interfaces:**
- Consumes: `Runtime`, exact source/target Job + Attempt ids, typed external reference bundle.
- Produces: `build_current_continuation(runtime, request) -> dict[str, Any]`.

- [ ] **Step 1: Write failing fixture-runtime tests**

The test must create a Runtime fixture with:

1. one Job with attempt limit >=2;
2. Attempt 1 terminal `RATE_LIMITED` with a checkpoint;
3. the Job requeued;
4. Attempt 2 claimed on a different worker/account label;
5. a request naming Attempt 1 as source and Attempt 2 as target.

Assert the builder refuses when:

- source Attempt is not terminal;
- target Attempt is not current;
- both Attempts belong to different Jobs;
- target Attempt reuses the same account while caller claims a cross-realm move only in prose;
- effective grant digest is absent for an orchestration Attempt;
- supplied GitHub head/base refs are malformed;
- external source revisions are missing.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_operator_continuation_sources.py`

- [ ] **Step 3: Implement typed request + Runtime reads**

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


def build_current_continuation(
    runtime: Runtime,
    *,
    source_attempt_id: str,
    target_attempt_id: str,
    refs: ContinuationExternalRefs,
    generated_at: str,
) -> dict[str, Any]:
    ...
```

Use existing `JobPayload` checkpoint material directly. Do not invent a summary when the prior checkpoint lacks one; represent missing material truthfully.

- [ ] **Step 4: Prove stale source facts refuse**

After building a request, mutate the target Job/Attempt fixture so it is no longer current. A second build must refuse rather than return the old capsule.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest -q tests/test_operator_continuation.py tests/test_operator_continuation_sources.py
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/operator_continuation_sources.py tests/test_operator_continuation.py tests/test_operator_continuation_sources.py
git commit -m "feat(exec): derive continuation from current runtime facts"
```

---

### Task 3: Derive RuntimeBinding from the current Operator Harness writer

**Files:**
- Create: `control_plane/runtime_binding_projection.py`
- Modify: `control_plane/executive_runtime.py` only to add a read-only typed query if no current public query can provide the exact active epoch/generation/principal facts.
- Test: `tests/test_runtime_binding_projection.py`

**Interfaces:**
- Consumes: current active OPERATOR_HARNESS Attempt + accepted logical `SessionTarget`.
- Produces: `project_runtime_binding(runtime, attempt_id, target) -> RuntimeBinding`.

- [ ] **Step 1: Write failing projection tests**

Create a fixture Attempt with one CURRENT epoch, one current writer generation, bound `provider_session_id`, accepted placement/account label and reasoning surface.

Expected:

```python
binding = project_runtime_binding(runtime, attempt_id=attempt_id, target=target)
assert binding.session_alias == target.session_alias
assert binding.native_handle == "provider-session-1"
assert binding.account_label == "claude-pro-02"
assert binding.binding_generation == 1
assert binding.binding_id.startswith("bind-")
```

Also assert refusal for:

- multiple/no current writers;
- epoch not CURRENT;
- provider session unbound;
- Attempt not current/active;
- target seat/reasoning surface inconsistent with placement;
- missing placement/account evidence;
- non-OHF Attempt.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_runtime_binding_projection.py`

- [ ] **Step 3: Add one read-only registry query if required**

Preferred shape:

```python
@dataclass(frozen=True)
class ActiveOperatorBindingFacts:
    attempt_id: str
    worker_id: str
    session_epoch_id: str
    process_generation_id: str
    generation_number: int
    provider_session_id: str
    provider: str
    account_label: str


def active_binding_facts(self, attempt_id: str) -> ActiveOperatorBindingFacts:
    ...
```

The query runs under `store.read()` and derives exactly one current writer. It writes no state.

- [ ] **Step 4: Implement ABA-safe projection**

Derive:

```python
binding_id = "bind-" + sha256(
    f"{attempt_id}:{session_epoch_id}".encode("utf-8")
).hexdigest()[:40]
```

Use `generation_number` as `binding_generation` and `provider_session_id` as `native_handle`. The session epoch is UUID-based Executive identity, so a restarted/new epoch cannot reuse the old binding ID.

- [ ] **Step 5: Mutation tests**

Change only the process generation: same binding ID, higher generation. Change the session epoch or Attempt: different binding ID. Change provider session without a legal Executive transition: query/projection must refuse.

- [ ] **Step 6: Run relevant suites**

```bash
pytest -q tests/test_runtime_binding_projection.py tests/test_operator_harness_contract.py tests/test_executive_runtime.py
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/runtime_binding_projection.py control_plane/executive_runtime.py tests/test_runtime_binding_projection.py
git commit -m "feat(exec): project Wake runtime binding from Operator Harness"
```

---

### Task 4: Persist preparation and ACK only through the existing Executive Event plane

**Files:**
- Modify: `control_plane/executive_runtime.py`
- Modify: `control_plane/executive_operator_harness_port.py`
- Modify: `control_plane/operator_continuation.py`
- Test: `tests/test_operator_continuation_events.py`

**Interfaces:**
- Produces: `prepare_operator_continuation(...)` and `acknowledge_operator_continuation(...)` on the existing Attempt-bound port.
- No new SQLite schema object.

- [ ] **Step 1: Write failing Event-plane tests**

Preparation event:

```text
event_type = OPERATOR_CONTINUATION_PREPARED
aggregate_type = attempt
aggregate_id = target_attempt_id
attempt_id = target_attempt_id
payload = {
  schema_version,
  capsule_id,
  source_attempt_id,
  provider_session_id
}
```

ACK event:

```text
event_type = OPERATOR_CONTINUATION_ACKNOWLEDGED
aggregate_type = attempt
aggregate_id = target_attempt_id
attempt_id = target_attempt_id
payload = {
  schema_version,
  capsule_id,
  provider_session_id
}
```

Require exactly one semantic preparation and one exact ACK. Same capsule replay is idempotent; changed capsule/provider session conflicts.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_operator_continuation_events.py`

- [ ] **Step 3: Implement fenced registry mutations**

Both calls must use the active Attempt lease/fence. Preparation requires:

- target Attempt is current and RUNNING/CHECKPOINTED;
- current Operator Harness generation is admitted/attested;
- capsule target Attempt matches;
- capsule provider session is not model-authored and is matched against the current binding.

ACK additionally validates `ContinuationAck` against the prepared capsule and current provider session.

- [ ] **Step 4: Prove zero schema/table change**

Test `sqlite_master` before/after and assert identical schema digest. Events are the only durable addition.

- [ ] **Step 5: Run runtime + port suites**

```bash
pytest -q tests/test_operator_continuation_events.py tests/test_executive_runtime.py tests/test_executive_operator_harness_port.py
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/executive_runtime.py control_plane/executive_operator_harness_port.py control_plane/operator_continuation.py tests/test_operator_continuation_events.py
git commit -m "feat(exec): bind continuation ACK to existing Event plane"
```

---

### Task 5: End-to-end hermetic two-Attempt continuation proof

**Files:**
- Create: `tests/test_operator_continuation_integration.py`
- Documentation update only if test exposes a real contract clarification.

**Interfaces:**
- Proves: old Attempt terminal -> requeue -> new Attempt/current realm -> capsule -> provider session -> ACK -> RuntimeBinding projection.

- [ ] **Step 1: Build the integration fixture**

Create two workers with distinct account labels, one Job with attempt limit >=2, Attempt 1 `RATE_LIMITED` with checkpoint, requeue, claim Attempt 2, then create/bind/attest one OHF session for Attempt 2.

- [ ] **Step 2: Assert the complete positive chain**

```python
capsule = build_current_continuation(...)
port.prepare_operator_continuation(...)
binding = project_runtime_binding(...)
port.acknowledge_operator_continuation(...)
assert binding.account_label == second_account
assert runtime.events contains exactly one PREPARED and one ACKNOWLEDGED event
```

- [ ] **Step 3: Assert adverse fences**

Separate tests must kill these mutations:

- source Attempt still active;
- target Attempt from another Job;
- target realm equals stale/wrong placement evidence;
- wrong provider session ACK;
- stale target Attempt after another claim;
- duplicate changed capsule;
- an existing `OPERATOR_OPERATION_EFFECT_UNKNOWN` on the source work path treated as safe rollover.

The final adverse case must refuse before continuation preparation.

- [ ] **Step 4: Run full focused suite + compile**

```bash
pytest -q tests/test_operator_continuation*.py tests/test_runtime_binding_projection.py
python3 -m compileall -q control_plane
```

- [ ] **Step 5: Return for Sol review**

Return exact head, changed paths, schema-digest proof, focused/full CI, no-new-table scan, hostile/mutation proof, and confirmation that no Wake/Slack/provider production action occurred.

## Stop Condition

OCR-3 stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT` after the hermetic two-Attempt continuation chain passes. It does not implement the Claude adapter, live provider call, cross-account selection, Worker Presence, Slack posting, Steward UI or MH1. Those are separately gated waves.
