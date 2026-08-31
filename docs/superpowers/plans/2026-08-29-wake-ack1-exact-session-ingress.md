# Wake ACK1 Exact-Session Ingress Implementation Plan

**Current status:** PLAN_ONLY / RECORDS_ONLY / NOT_BUILT. This records repair authorizes no ACK1 implementation START, runtime/provider action, target ACK, source resolution, canary, Ready or merge.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first trusted reasoning-session Wake acknowledgement ingress so an exact currently bound Codex/OHF reasoning session can claim only the opaque Wake obligations it actually consumed, while existing Wake law verifies prior delivery/current binding and existing Executive `events` persist `TARGET_ACKNOWLEDGED` exactly once.

**Architecture:** This plan extends the existing Wake acknowledgement codec/causal law and Executive-events persistence; it creates no ACK database or RuntimeBinding owner. Protected MAS-237 provides the ABA-safe RuntimeBinding projection, while the current W3A owner chain is the existing WorkerBroker / `RemoteCodexOperatorAdapter` / worker-local current `CodexOperatorAdapter` generation and its already-running client. ACK1 acquires the existing Executive `BEGIN IMMEDIATE` transaction, projects the target's current binding inside that lock, validates one closed authenticated worker-local exact-turn projection against the exact prior `DELIVERED` record, and appends the canonical `:ACK` event before releasing the lock. Raw provider/model bytes remain inside the worker-local current generation/client; no control-side App Server, second reader, cold resume, parser store, poller, or session owner is added.

**Tech Stack:** Python 3.11+, existing Executive SQLite `RuntimeStore`, Wake Fabric (`wake_ledger`, `wake_persist`, `session_targets`, `wake_dispatcher`), protected MAS-237 RuntimeBinding projection, existing WorkerBroker/OHF wire, current `RemoteCodexOperatorAdapter`, worker-local current `CodexOperatorAdapter` generation/client, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`

## Global Constraints

- **Protected predecessors:** #257 / MAS-237 RuntimeBinding projection, #262 current-owner architecture, and #254 persisted Wake carrier are protected. Re-prove their exact protected merge ancestry at implementation time; do not copy or reopen them.
- **Current protected source:** `Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc`, which protects Worker Browser B1 / #153. That merge does not replace the ACK1 worker-local exact-turn owner or authorize ACK1 implementation.
- **Unprotected implementation predecessor:** W3A #250 is the sole current native-delivery candidate at `85ba1246b376f6264e59671fd0e228a60866afff`, but is not protected at this plan repair. Do not START ACK1 code until the current W3A owner chain is accepted on then-current protected source. If absent, moved, or unaccepted, return exactly `HOLD — CURRENT_WRITER_ATTENTION_OWNER_NOT_DURABLE`.
- Re-pin protected Mastermind `master`, load `docs/sol_skills/INDEX.md` plus required skills from the same SHA, and repeat the live PR/path census immediately before first write and final release. Planning pin `7b8f3ca580f9872ca8ddf60f90c6022ce4a18e6b` is advisory after source moves.
- Preserve the constitutional split: `ACCEPTED != DELIVERED != TARGET_ACKNOWLEDGED != SOURCE_RESOLVED`.
- Existing Wake obligation/attempt/ACK/source-resolution state remains Executive `events`; create no Wake table, ACK table, queue, scheduler, retry ledger, session registry, provider registry, lock service or lifecycle owner.
- Reuse `RuntimeStore.transaction()` / `BEGIN IMMEDIATE` for the ACK's current-binding + Wake-ledger atomicity. Do not create a second lock/lease/transaction plane.
- The target/model may originate **only opaque canonical `WAKE-*` obligation IDs**. It may not author target seat, session alias, binding id, binding generation, reasoning surface, provider/native handle, nudge id, delivery proof, source-resolution evidence, host identity or authority.
- Raw provider/native handles remain runtime-only and must not be persisted in Wake `events`, logs, Git, Slack or proof artifacts. Safe persisted ACK evidence may include binding id/generation and the canonical delivered-record command id.
- A reasoning-session ACK is invalid unless a prior canonical `DELIVERED` record exists for the same obligation/nudge and matches the exact current RuntimeBinding generation/session alias/reasoning surface.
- `TARGET_ACKNOWLEDGED` must never be derived from App Server delivery, Slack delivery, model prose saying “done”, a watcher fire, a dispatcher receipt or absence of error.
- Preserve existing human-operator acknowledgement semantics. The stricter prior-delivery/current-generation law introduced by this plan applies to `AckMode.REASONING_SESSION`; do not break accepted `AckMode.HUMAN_OPERATOR` authority receipts.
- A valid identical ACK replay reconciles to the same `<WAKE-ID>:ACK` event. Changed claim set, binding generation or delivered-evidence pointer under that command id fails closed as a conflict.
- `EFFECT_UNKNOWN` on ACK submission means read/reconcile the same ACK command id first; never blind-resubmit and never fail over to another session/provider.
- Checked-in `production_armed=false` and target-disabled state remain unchanged. No task in this plan enables a production Wake target or broad autonomous wake loop.
- The first real acceptance vertical is **Codex/OHF-bound reasoning sessions with a canonical Wake obligation containing an Executive Attempt id**. Do not claim this plan proves ChatGPT web, Claude/Fable or workspace-agent ACK ingress.
- A Wake obligation's `attempt_id` is source correlation, not automatically the target's current Attempt. Resolve the target through the canonical Wake route, then require a closed worker-local projection naming the exact target current Attempt and prove that Attempt owns the current RuntimeBinding/generation. Refuse an ambiguous source-Attempt/target-Attempt join.
- Every then-current per-capability source, collision, review, and production gate remains independent from code/CI success. A green ACK1 PR is not merge authority.

---

### Task 0: Re-pin the ACK1 execution boundary and prove MAS-237 is durable

**Files:**
- Read only: `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`
- Read only: `control_plane/runtime_binding_projection.py`
- Read only: `control_plane/executive_runtime.py`
- Read only: `control_plane/wake_ledger.py`
- Read only: `control_plane/wake_persist.py`
- Read only: the accepted current W3A owner implementation on the then-current protected source

**Interfaces:**
- Consumes MAS-237's protected `project_runtime_binding(runtime, attempt_id, target, *, connection=None) -> RuntimeBinding`.
- Produces no code; this task either clears execution or returns a typed hold/collision.

- [ ] **Step 1: Re-pin protected source atomically**

Fetch protected `master`; from that exact SHA load at minimum:

```text
docs/sol_skills/INDEX.md
docs/sol_skills/COLD_START.md
docs/sol_skills/RECONCILE_STATE.md
docs/sol_skills/REVIEW_RETURN.md
docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md
```

Record the exact protected SHA and Skillpack version in the implementation carrier.

- [ ] **Step 2: Prove the RuntimeBinding predecessor exists**

Verify all of the following in protected source:

```python
from control_plane.runtime_binding_projection import project_runtime_binding
```

and the callable accepts an existing Executive-store transaction via keyword-only `connection`.

Verify the Executive runtime read seam returns the CURRENT `SessionEpochRef`, current writer `ProcessGenerationRef`, and bound `provider_session_id` without mutation.

If any prerequisite is absent or materially different, STOP with:

```text
HOLD — RUNTIMEBINDING_PROJECTION_NOT_DURABLE
```

Do not copy MAS-237 implementation into ACK1.

- [ ] **Step 3: Repeat the open-PR path census**

Census active PRs/worktrees for:

```text
control_plane/wake_ledger.py
control_plane/wake_persist.py
control_plane/wake_ack_ingress.py
control_plane/operator_harness_contract.py
control_plane/operator_harness_wire.py
control_plane/codex_operator_adapter.py
control_plane/executive_worker_broker.py
control_plane/remote_codex_operator_adapter.py
integrations/executive_wake/codex_app_server_rpc.py
tests/test_executive_wake_fabric.py
tests/test_executive_wake_fabric_hardening.py
tests/test_executive_wake_persisted_dispatch.py
tests/test_wake_ack_ingress.py
tests/test_codex_app_server_wake_rpc.py
docs/EXECUTIVE_WAKE_FABRIC.md
```

Another live writer on the same logical ACK1 change is `HELD_COLLISION`; do not create a second implementation carrier.

- [ ] **Step 4: Freeze current codec signatures**

Confirm current source still exposes:

```python
TrustedAckContext
WakeAcknowledgement
acknowledge(...)
ack_record(...)
assert_causal(...)
WakeLedgerRepository.list_records(...)
WakeLedgerRepository.append_records_atomic(...)
```

If names moved but ownership is unchanged, update this plan's implementation mechanically on the same carrier before coding; do not invent parallel APIs.

---

### Task 1: Strengthen the canonical reasoning-session ACK record and causal law

**Files:**
- Modify: `control_plane/wake_ledger.py`
- Modify: `tests/test_executive_wake_fabric.py`
- Modify: `tests/test_executive_wake_fabric_hardening.py`
- Modify: `tests/test_executive_wake_persisted_dispatch.py`

**Interfaces:**
- Consumes existing `WakeObligation`, `WakeLedgerRecord`, `DeliveryAttempt`, `TrustedAckContext`, `WakeAcknowledgement` and deterministic ledger command ids.
- Produces a reasoning-session ACK that durably carries safe current-generation + delivered-record evidence without persisting a native handle.

- [ ] **Step 1: Add RED tests for a reasoning ACK with no prior delivery**

Add a focused discriminator using the existing Wake test helpers:

```python
def test_reasoning_ack_without_prior_delivered_record_is_causally_refused() -> None:
    obligation = _wake_obligation()
    ack = acknowledge(
        obligation,
        trusted=TrustedAckContext(
            ack_mode=AckMode.REASONING_SESSION,
            target_seat=obligation.declared_target_seat,
            session_alias="EXECUTIVE-COO-A",
            reasoning_surface="codex",
            binding_id="bind-ack1234",
            binding_generation=3,
        ),
        claimed_obligation_ids=(obligation.obligation_id,),
        delivered_command_id=(
            f"{obligation.obligation_id}:A1:DELIVERED"
        ),
    )
    with pytest.raises(WakeLedgerError, match="matching DELIVERED"):
        assert_causal((requested_record(obligation), ack_record(obligation, ack)))
```

Expected: RED because current ACK wire/causal law does not require this evidence.

- [ ] **Step 2: Add RED stale/mismatched-generation controls**

Create a real `DeliveryAttempt` / `DELIVERED` record at binding generation 2, then attempt reasoning ACKs with:

```text
binding_generation=3 -> REFUSE
wrong binding_id -> REFUSE
wrong session_alias -> REFUSE
wrong reasoning_surface -> REFUSE
reference to A2:DELIVERED when only A1:DELIVERED exists -> REFUSE
matching A1 delivery/binding/generation -> ACCEPT
```

All failure assertions must distinguish the actual mismatch rather than merely asserting a generic exception.

- [ ] **Step 3: Add RED event-codec / replay tests**

Persist a valid reasoning ACK and assert its event payload round-trips these safe fields exactly:

```text
binding_id
binding_generation
delivered_command_id
claimed_obligation_ids
```

Assert raw `native_handle` is absent from the payload.

Then prove:

```text
identical same-command replay -> one existing event, no second row
same <WAKE-ID>:ACK + different binding_generation -> StateConflict
same <WAKE-ID>:ACK + different delivered_command_id -> StateConflict
same <WAKE-ID>:ACK + changed claimed_obligation_ids -> StateConflict
```

- [ ] **Step 4: Preserve human-operator negative controls**

Add/retain a test proving `AckMode.HUMAN_OPERATOR` continues to require `operator_authority_receipt` and does not inherit a fabricated provider delivery requirement.

A human ACK carrying reasoning-session-only `binding_generation` or `delivered_command_id` must be refused rather than silently ignored.

- [ ] **Step 5: Run the RED suite**

Run:

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  tests/test_executive_wake_persisted_dispatch.py \
  -q
```

Expected: only the new ACK-evidence tests fail; existing transport/retry/source-resolution laws remain green.

- [ ] **Step 6: Extend trusted ACK context without adding native identity to the ledger**

Add an optional trusted generation field with a compatibility default:

```python
@dataclasses.dataclass(frozen=True)
class TrustedAckContext:
    ack_mode: AckMode
    target_seat: str
    session_alias: str
    reasoning_surface: str
    binding_id: str | None = None
    binding_generation: int | None = None
    acknowledged_at: str | None = None
    operator_authority_receipt: str | None = None
```

Do **not** add `native_handle` or provider account fields here.

- [ ] **Step 7: Extend the persisted ACK evidence**

Keep existing fields and add only safe proof fields with compatibility defaults:

```python
@dataclasses.dataclass(frozen=True)
class WakeAcknowledgement:
    obligation_id: str
    ack_mode: AckMode
    target_seat: str
    session_alias: str
    reasoning_surface: str
    binding_id: str | None
    acknowledged_at: str
    claimed_obligation_ids: tuple[str, ...]
    operator_authority_receipt: str | None = None
    binding_generation: int | None = None
    delivered_command_id: str | None = None
```

`delivered_command_id` is evidence pointing at the canonical `DELIVERED` event. It does not replace the Wake obligation's identity.

- [ ] **Step 8: Tighten `acknowledge()` for reasoning sessions**

Extend the signature only with a keyword argument:

```python
def acknowledge(
    obligation: WakeObligation,
    *,
    trusted: TrustedAckContext,
    claimed_obligation_ids: Sequence[str],
    delivered_command_id: str | None = None,
) -> WakeAcknowledgement:
    ...
```

For `REASONING_SESSION` require:

```text
seat == obligation.declared_target_seat
binding_id matches BINDING_ID_RE
binding_generation is an actual int >= 1
delivered_command_id is nonempty and belongs to this exact WAKE obligation
operator_authority_receipt is absent
```

For `HUMAN_OPERATOR`, require the existing authority receipt and refuse reasoning-only generation/delivery fields.

- [ ] **Step 9: Enforce the prior-delivery causal invariant**

In `assert_causal()`, when processing `TARGET_ACKNOWLEDGED` with `AckMode.REASONING_SESSION`:

1. find exactly one **earlier** record whose command id equals `ack.delivered_command_id`;
2. require `phase is LedgerPhase.DELIVERED`;
3. require the delivered record's `binding_id`, `binding_generation`, `session_alias`, and `reasoning_surface` equal the ACK evidence;
4. require the requested obligation's declared target seat equals `ack.target_seat`;
5. refuse missing, later, duplicate or mismatched delivery evidence.

Do not require the ACK to adopt delivery attempt identity as its command id; the canonical ACK remains `<WAKE-ID>:ACK`.

- [ ] **Step 10: Update the ACK event codec**

Update `event_payload_for()` / `wake_record_from_event()` so `binding_generation` and `delivered_command_id` round-trip under the existing acknowledgement payload. Decode older optional fields with `.get(...)`; current reasoning-session causal validation decides whether an old row is acceptable.

Do not add `native_handle`, provider account, thread transcript or nudge body to the event payload.

- [ ] **Step 11: Run GREEN and commit**

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  tests/test_executive_wake_persisted_dispatch.py \
  -q

git diff --check
git add control_plane/wake_ledger.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  tests/test_executive_wake_persisted_dispatch.py
git commit -m "fix(exec): bind Wake ACK to exact delivered generation"
```

---

### Task 2: Reuse the Executive transaction for connection-scoped Wake reads/writes

**Files:**
- Modify: `control_plane/wake_persist.py`
- Modify: `tests/test_executive_wake_persisted_dispatch.py`

**Interfaces:**
- Consumes existing `RuntimeStore.transaction()` / `BEGIN IMMEDIATE` and `WakeLedgerRepository` codec/causal validation.
- Produces connection-scoped repository methods so ACK1 can validate RuntimeBinding + delivery and append ACK under the same Executive write lock.

- [ ] **Step 1: Add RED tests for connection-scoped access**

Pin these exact behaviors:

```text
list_ledger_records_on_connection(connection, oid) requires an active transaction
append_records_on_connection(connection, items) requires an active transaction
connection-scoped append has the same causal/replay checks as append_records_atomic
append_records_atomic remains API-compatible and delegates to the connection-scoped implementation
same command/payload replay returns the existing event rather than inserting a second row
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_executive_wake_persisted_dispatch.py -q
```

- [ ] **Step 3: Expose a bounded connection-scoped read**

Add:

```python
def list_ledger_records_on_connection(
    self,
    connection,
    obligation_id: str,
) -> tuple[WakeLedgerRecord, ...]:
    if not connection.in_transaction:
        raise StateConflict("Wake ledger connection read requires an active transaction")
    return tuple(self._records_on_connection(connection, obligation_id))
```

This is a read over existing `events`, not a new store API.

- [ ] **Step 4: Refactor atomic append into a reusable connection-scoped method**

Add:

```python
def append_records_on_connection(
    self,
    connection,
    items: Sequence[tuple[WakeLedgerRecord, WakeObligation | None]],
    *,
    actor: str = WAKE_EVENT_ACTOR,
) -> tuple[PersistedWakeEvent, ...]:
    if not connection.in_transaction:
        raise StateConflict("Wake ledger connection append requires an active transaction")
    ...
```

Move the existing `proposed_by_oid` + `assert_causal(combined)` + `_append_one(...)` logic into this method without semantic changes.

Then make existing `append_records_atomic()` exactly:

```python
with self.store.transaction() as connection:
    return self.append_records_on_connection(connection, items, actor=actor)
```

Do not expose arbitrary SQL or permit a caller to bypass causal validation.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest tests/test_executive_wake_persisted_dispatch.py -q
git diff --check
git add control_plane/wake_persist.py tests/test_executive_wake_persisted_dispatch.py
git commit -m "refactor(exec): reuse Wake ledger inside Executive transaction"
```

---

### Task 3: Implement the provider-neutral exact-session ACK ingress core

**Files:**
- Create: `control_plane/wake_ack_ingress.py`
- Create: `tests/test_wake_ack_ingress.py`
- Read/consume: `control_plane/runtime_binding_projection.py`
- Read/consume: `control_plane/session_targets.py`
- Read/consume: `control_plane/wake_persist.py`

**Interfaces:**
- Consumes MAS-237 `project_runtime_binding(..., connection=...)`, canonical `SessionTargetRegistry`, canonical delivered Wake records and existing ACK ledger/persistence law.
- Produces only `WakeAckClaim`, `TrustedWorkerWakeAckProjection`, `WakeAckIngressError`, and `acknowledge_consumed_wakes(...)`.

- [ ] **Step 1: Write RED trust-boundary tests**

Create `tests/test_wake_ack_ingress.py` and prove the model/caller claim shape contains only canonical obligation IDs:

```python
from dataclasses import fields

assert [field.name for field in fields(WakeAckClaim)] == ["obligation_ids"]
```

Refuse empty, duplicate, malformed or attempt-command identities such as:

```text
WAKE-...:A1
WAKE-...:A1:DELIVERED
```

Only exact `WAKE_ID_RE` obligation ids are valid claims.

- [ ] **Step 2: Write RED exact-delivery/current-binding tests**

Build an in-memory Executive runtime containing one CURRENT OHF Attempt/epoch/writer, a MAS-237-compatible RuntimeBinding, one `WAKE_REQUESTED` and one matching `DELIVERED` record.

Pin:

```text
DELIVERED + exact target Attempt/current binding + exact worker-local turn projection + same nudge -> ACK persists
ACCEPTED-only -> REFUSE
DELIVERED to prior generation -> REFUSE
DELIVERED to another binding id -> REFUSE
DELIVERED to another session alias/surface -> REFUSE
projection provider_session_id != projected RuntimeBinding.native_handle -> REFUSE
projection target_attempt_id != canonical current target Attempt -> REFUSE
projection provider_native_turn_id != exact W3A delivery turn -> REFUSE
Wake source attempt_id used as the target Attempt without a canonical routing join -> REFUSE
missing/blank projected provider session/native turn -> REFUSE
claim not included in the trusted nudge -> REFUSE
```

- [ ] **Step 3: Write RED coalesced-claim atomicity tests**

Use two Wake obligations delivered in the same nudge/destination and claim both.

Require:

```text
both exact -> two :ACK events commit in one transaction
one invalid/mismatched obligation -> zero ACK events commit
subset of actually delivered obligations -> only that claimed subset ACKs
claim containing an obligation from a different nudge/destination -> REFUSE entire call
```

A claim set is canonicalized to sorted unique `WAKE-*` ids; duplicate input is refused rather than silently collapsed.

- [ ] **Step 4: Write RED idempotence/effect-unknown reconciliation tests**

Call the same exact ingress twice and assert:

```text
one ACK event per obligation
second call returns the existing events / no duplicate rows
```

Then mutate current binding generation or claim set and assert the stable `:ACK` command id conflicts rather than creating another acknowledgement.

This models a caller that lost the first response and reconciles the same operation. No alternate ingress/session is used.

- [ ] **Step 5: Define the closed claim/trusted-observation types**

Create:

```python
@dataclasses.dataclass(frozen=True)
class WakeAckClaim:
    obligation_ids: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class TrustedWorkerWakeAckProjection:
    target_attempt_id: str
    process_generation_id: str
    binding_id: str
    binding_generation: int
    provider_session_id: str
    provider_native_turn_id: str
    nudge_id: str
    obligation_ids: tuple[str, ...]
    terminal_ack_trailer: bool


class WakeAckIngressError(ValueError):
    pass
```

`WakeAckClaim` validates exact `WAKE_ID_RE` ids, nonempty input, uniqueness and canonical sorted order.

`TrustedWorkerWakeAckProjection` is the closed authenticated output of the existing worker-local current generation/client owner. It validates canonical target Attempt, process generation, binding id/generation, provider session, exact provider-native turn, nudge and obligation identities, and requires `terminal_ack_trailer is True`. Raw model/provider bytes are never fields and never cross the WorkerBroker boundary. The model cannot construct this type.

- [ ] **Step 6: Implement one helper to recover the requested obligation**

Inside the new module, from connection-scoped Wake records require exactly one `WAKE_REQUESTED` record containing the canonical `WakeObligation`. Refuse missing/duplicate request records.

Treat `obligation.attempt_id` only as source correlation. It may identify the source Job/Attempt that produced the Wake fact and must never be reused as the target current Attempt merely because it is a canonical `ATT-*`. Resolve the intended target through the obligation's canonical root/workstream/seat route and require the closed worker projection's `target_attempt_id` to be the one current OPERATOR_HARNESS Attempt owning that resolved target. Missing or ambiguous source-to-target routing is a typed refusal.

- [ ] **Step 7: Implement exact delivered-evidence selection**

For each claimed obligation, select exactly one prior record satisfying:

```python
record.phase is LedgerPhase.DELIVERED
and record.nudge_id == trusted.nudge_id
```

Then derive the logical target from canonical data only:

```python
target = registry.get(delivered.session_alias)
```

Do not accept session alias/seat/surface from the caller/model.

- [ ] **Step 8: Acquire Executive atomicity before projecting the binding**

Implement:

```python
def acknowledge_consumed_wakes(
    runtime: Runtime,
    registry: SessionTargetRegistry,
    *,
    claim: WakeAckClaim,
    trusted: TrustedWorkerWakeAckProjection,
) -> tuple[PersistedWakeEvent, ...]:
    repository = WakeLedgerRepository(runtime)
    with runtime.store.transaction() as connection:
        ...
```

The `BEGIN IMMEDIATE` lock is acquired **before** current RuntimeBinding projection or ACK append.

For each claimed obligation call:

```python
binding = project_runtime_binding(
    runtime,
    trusted.target_attempt_id,
    target,
    connection=connection,
)
```

and require:

```text
binding.native_handle == trusted.provider_session_id
binding.binding_id == delivered.binding_id
binding.binding_generation == delivered.binding_generation
binding.session_alias == delivered.session_alias
binding.reasoning_surface == delivered.reasoning_surface
target.target_seat == obligation.declared_target_seat
trusted.binding_id == binding.binding_id
trusted.binding_generation == binding.binding_generation
trusted.process_generation_id == current generation for trusted.target_attempt_id
trusted.provider_native_turn_id == exact provider turn recorded for delivered.nudge_id
trusted.obligation_ids == claim.obligation_ids
trusted.terminal_ack_trailer is True
```

Also require every claimed delivery shares the same trusted `nudge_id`, destination, target current Attempt, process generation, binding generation, provider session and provider-native turn. A coalesced nudge cannot become a cross-destination or cross-Attempt ACK batch.

- [ ] **Step 9: Build only canonical ACK records**

For each obligation build:

```python
ack = acknowledge(
    obligation,
    trusted=TrustedAckContext(
        ack_mode=AckMode.REASONING_SESSION,
        target_seat=obligation.declared_target_seat,
        session_alias=binding.session_alias,
        reasoning_surface=binding.reasoning_surface,
        binding_id=binding.binding_id,
        binding_generation=binding.binding_generation,
    ),
    claimed_obligation_ids=claim.obligation_ids,
    delivered_command_id=delivered.command_id,
)
record = ack_record(obligation, ack)
```

Append all records with the connection-scoped repository method in the same Executive transaction.

Do not persist `trusted.provider_session_id`, `trusted.provider_native_turn_id`, or raw turn data in the ACK payload. The ACK's delivered-command evidence points to the canonical delivery record; safe target-Attempt/current-generation evidence is validation input, not model-authored durable authority.

- [ ] **Step 10: Run GREEN and commit**

```bash
python -m pytest \
  tests/test_wake_ack_ingress.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_persisted_dispatch.py \
  -q
git diff --check
git add control_plane/wake_ack_ingress.py \
  tests/test_wake_ack_ingress.py
git commit -m "feat(exec): add exact-session Wake ACK ingress core"
```

---

### Task 4: Reduce the exact W3A attention turn inside the existing worker-local owner

**Files:**
- Modify: `control_plane/operator_harness_contract.py`
- Modify: `control_plane/operator_harness_wire.py`
- Modify: `control_plane/codex_operator_adapter.py`
- Modify: `control_plane/executive_worker_broker.py`
- Modify: `control_plane/remote_codex_operator_adapter.py`
- Modify: `integrations/executive_wake/codex_app_server_rpc.py`
- Modify: `tests/test_codex_app_server_wake_rpc.py`

**Interfaces:**
- Consumes protected/current W3A `ohf-deliver-attention`, its `AttentionTurnObservation`, the already-owned worker-local current `CodexOperatorAdapter` generation/client, and Task-3 provider-neutral ACK ingress.
- Produces one closed authenticated `TrustedWorkerWakeAckProjection`. The model contributes only terminal `WAKE-*` marker lines; trusted Attempt/generation/binding/provider-session/native-turn/nudge identity comes from the existing owner state. Raw turn bytes never leave the worker-local adapter.
- Adds no App Server process/client, broker endpoint, reader, cold resume, GUI/title fallback, parser store, poller, retry plane, session registry or lifecycle owner.

- [ ] **Step 1: Freeze the exact target-originated marker protocol in RED tests**

The ACK-capable Wake instruction must preserve the existing statement that the **nudge itself acknowledges nothing** and add one bounded target behavior:

```text
After you have actually consumed the supplied Wake obligation(s) and recovered canonical Executive/Agent OS state, emit one final marker line per consumed obligation:
MASTERMIND_WAKE_ACK <WAKE-ID>
Do not put seat, session, binding, provider, host, nudge, source-resolution or authority data in the marker.
```

Tests must prove the instruction does not say delivery/response automatically equals ACK.

- [ ] **Step 2: Extend the existing attention observation with a closed worker-local ACK projection**

Extend the existing W3A `AttentionTurnObservation` returned by `ohf-deliver-attention`; do not create a second read API. The closed nested projection is:

```python
@dataclasses.dataclass(frozen=True)
class WorkerLocalWakeAckProjection:
    target_attempt_id: str
    process_generation_id: str
    binding_id: str
    binding_generation: int
    provider_session_id: str
    provider_native_turn_id: str
    nudge_id: str
    obligation_ids: tuple[str, ...]
    terminal_ack_trailer: bool
```

The worker-local current `CodexOperatorAdapter` generation/client is the only owner allowed to observe the exact W3A provider turn and reduce exact terminal `MASTERMIND_WAKE_ACK <WAKE-ID>` markers. Reuse its existing completion/event collection and exact provider-native turn correlation. **Raw model text is not passed to the broker, remote adapter, integration layer, or `control_plane`.**

Attempt, process generation, binding, provider-session/native-turn and nudge identities are copied from the already-validated current generation and W3A attention operation, never parsed from model output. The projection is attached only to the matching completed `AttentionTurnObservation`; accepted-but-unobserved-complete remains fenced and carries no ACK projection.

- [ ] **Step 3: Add adversarial worker-local reduction and wire tests**

Using the existing instrumented worker-local adapter/broker/client fixtures, pin:

```text
no marker / active nonterminal turn -> no projection and no ACK mutation
wrong provider session / process generation / target Attempt -> REFUSE
wrong nudge / older provider-native turn -> REFUSE
stale binding id or generation -> REFUSE
malformed marker / attempt command / arbitrary prose -> no valid claim
quoted/fenced/inline/list/prefixed echo or marker before later prose -> no valid claim
duplicate marker id -> REFUSE
one valid terminal marker -> one closed projection and one core ACK
multiple valid markers from same nudge -> atomic claim batch
completion timeout/post-submit ambiguity -> preserve the exact generation-local W3A fence, zero projection, zero resend
late exact matching completion -> worker-local reduction may clear the fence and return the exact closed projection
stale/mismatched late completion -> cannot clear the fence or produce a projection
ordinary active OHF turn -> attention/ACK projection refuses pre-submit
```

Also assert no code path constructs/starts/resumes another App Server, creates a provider thread/session, calls a GUI/title fallback, invokes a second reader, or redelivers the Wake while collecting/reducing the exact turn.

- [ ] **Step 4: Implement reduction inside the existing current generation/client and broker operation**

Inside `CodexOperatorAdapter.deliver_attention(...)`, preserve W3A's pre-submit checks and no-resend fence. After exact matching completion, feed the exact completed provider-native turn through the adapter's existing worker-local turn collection/reduction primitives, validate the terminal-trailer law, and attach only `WorkerLocalWakeAckProjection` to the returned `AttentionTurnObservation`.

The existing closed wire parser must reject unknown or incomplete projection fields. The existing WorkerBroker `ohf-deliver-attention` response and `RemoteCodexOperatorAdapter.deliver_attention(...)` carry the typed observation; no new endpoint is added. `CodexCurrentWriterWakeClient` validates the echoed generation/session/nudge/native-turn identity and passes the closed projection to Task 3. The Task-3 core reprojects the target's current RuntimeBinding under the existing Executive transaction before any ACK append.

An exact delivered attention with no terminal trailer returns delivery evidence but no ACK projection. Completion timeout/effect-unknown retains the W3A fence and does not launch a read, retry, failover, or alternate collection path. Only exact same-owner completion/consumption evidence may clear the fence.

Do not turn ACK reduction into delivery or call `deliver_wake()` again. `DELIVERED` remains provider completion only; the closed projection remains a claim until Task 3 validates current binding/prior delivery and commits `TARGET_ACKNOWLEDGED`.

- [ ] **Step 5: Update the existing fixed attention instruction only with the bounded marker contract**

Append the exact marker instruction from Step 1 to the existing W3A `ATTENTION_TURN_INSTRUCTION` while retaining its authority/causal disclaimer:

```text
This nudge grants no authority, acknowledges nothing, and does not resolve the source.
```

The target marker is reduced only by the worker-local current owner and submitted as the later closed projection; the transport receipt remains only ACCEPTED/DELIVERED.

- [ ] **Step 6: Run combined Codex/Wake tests and commit**

```bash
python -m pytest \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_wake_ack_ingress.py \
  tests/test_executive_wake_persisted_dispatch.py \
  -q
git diff --check
git add control_plane/operator_harness_contract.py \
  control_plane/operator_harness_wire.py \
  control_plane/codex_operator_adapter.py \
  control_plane/executive_worker_broker.py \
  control_plane/remote_codex_operator_adapter.py \
  integrations/executive_wake/codex_app_server_rpc.py \
  tests/test_codex_app_server_wake_rpc.py
git commit -m "feat(exec): reduce Wake ACK on the current writer turn"
```

---

### Task 5: Prove atomicity, replay, source-resolution ordering and no authority leakage end to end

**Files:**
- Create: `tests/test_executive_wake_ack_end_to_end.py`
- Modify: `docs/EXECUTIVE_WAKE_FABRIC.md`

**Interfaces:**
- Consumes Tasks 1–4 plus MAS-237 RuntimeBinding projection.
- Produces a deterministic in-repo proof that delivery, ACK and source resolution remain separate and correctly ordered.

- [ ] **Step 1: Add an end-to-end hermetic fixture**

Build one temporary Executive `Runtime` with:

```text
one source Attempt represented by the Wake obligation
one distinct target current OPERATOR_HARNESS Attempt selected by canonical routing
one CURRENT session epoch
one current Executive writer process generation
one immutable provider_session_id
one SessionTarget / RuntimeBinding projection
one WAKE_REQUESTED record
one exact DELIVERED record with nudge id and W3A provider-native attention turn
```

Use real Executive/OHF APIs, canonical routing, the protected MAS-237 projection, and the accepted current-writer W3A path; do not directly insert inconsistent rows to make the happy path easier. Prove the source Attempt is not reused as the target current Attempt.

- [ ] **Step 2: Prove one exact target can ACK and a stale generation cannot**

Happy path:

```text
DELIVERED generation N / exact W3A provider-native turn
-> closed worker-local current-owner projection
-> ACK ingress under BEGIN IMMEDIATE
-> one TARGET_ACKNOWLEDGED event
```

Then create lawful target process generation N+1 and prove the old generation/turn's delivery cannot be ACKed by the new current session. Also substitute the Wake source Attempt for the target Attempt and require refusal. A new ACK command is not minted; the old obligation remains unacknowledged unless a valid new delivery exists.

- [ ] **Step 3: Prove the same Executive transaction is used across binding validation + ACK append**

Instrument the test so `project_runtime_binding(..., connection=...)` and `WakeLedgerRepository.append_records_on_connection(...)` both receive the **same active sqlite connection object**, with `connection.in_transaction is True`.

This is the deterministic race discriminator; do not use timing/sleeps as proof.

- [ ] **Step 4: Prove effect-unknown replay is same-command reconciliation**

Persist an ACK, discard the returned Python object to simulate response loss, then call the exact same ingress again.

Assert:

```text
one <WAKE-ID>:ACK event exists
same canonical payload is returned/reconciled
zero second ACK event
```

Then change the binding generation or claim set and assert a conflict.

- [ ] **Step 5: Prove source resolution cannot precede ACK**

Using the existing `resolve_source()` / `resolved_record()` ledger path, assert the source-resolved record is causally refused before a valid ACK.

After the valid ACK, create a healthy canonical source-absent resolution record and assert:

```text
TARGET_ACKNOWLEDGED
-> SOURCE_RESOLVED
```

No delivery/ACK method is allowed to fabricate `source_present=False` or a snapshot digest.

- [ ] **Step 6: Prove transport receipts cannot author target ACK**

Feed authenticated ACCEPTED/DELIVERED transport receipts through the existing persisted dispatcher and assert the reconstructed status remains:

```text
DELIVERED_UNACKNOWLEDGED
```

until the target-claim ingress runs.

- [ ] **Step 7: Update Wake architecture documentation**

Add a concise ACK1 section to `docs/EXECUTIVE_WAKE_FABRIC.md` documenting exactly:

```text
source fact -> obligation
route + RuntimeBinding -> destination
transport -> ACCEPTED/DELIVERED
target model -> opaque WAKE-* claim only
worker-local current generation/client -> exact-turn terminal reduction
closed authenticated projection -> target Attempt + generation + binding + provider turn + nudge + opaque ids
MAS-237 -> current binding/generation
Wake ACK ingress -> TARGET_ACKNOWLEDGED
canonical source reread -> SOURCE_RESOLVED
```

State that first ACK1 support is Codex/OHF-bound only and production remains disarmed.

- [ ] **Step 8: Run the complete deterministic suite and commit**

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  tests/test_executive_wake_persisted_dispatch.py \
  tests/test_wake_ack_ingress.py \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_executive_wake_ack_end_to_end.py \
  tests/test_runtime_binding_projection.py \
  -q
git diff --check
git add tests/test_executive_wake_ack_end_to_end.py docs/EXECUTIVE_WAKE_FABRIC.md
git commit -m "test(exec): prove Wake delivery to exact-session ACK ordering"
```

---

### Task 6: Exact-head adversarial review and harmless real Codex target canary

**Files:**
- No new production file is required by default.
- Sanitized proof records may use the repository's existing review/evidence convention only if current source requires a durable artifact.

**Interfaces:**
- Consumes the exact immutable ACK1 implementation head, one already-owned current `CodexOperatorAdapter` generation/client reached through the existing WorkerBroker/OHF path, one owner-approved disposable/non-production OHF session, and existing Wake source-resolution primitives.
- Produces exact-head evidence only; it does not production-arm Wake.

- [ ] **Step 1: Re-pin and run hosted exact-head proof**

Require on the immutable candidate head:

```text
repository required test = SUCCESS
CodeQL / relevant analyses = SUCCESS
focused Wake/OHF/ACK suites = SUCCESS
secret/leakage scan = clean
git diff --check = clean
```

Do not use historical green from a prior head after a current-source reconciliation.

- [ ] **Step 2: Perform independent adversarial review**

The reviewer must attack at minimum:

```text
ACK with no DELIVERED
ACCEPTED laundered as ACK
wrong native thread
wrong nudge
stale binding generation
new process generation after delivery
wrong seat/surface/session alias
model tries to author binding/native/nudge/seat fields
claim contains attempt command rather than WAKE id
coalesced claim crosses destination
identical replay
changed replay
ACK response lost after commit
source resolution before ACK
provider read failure
new thread/fork/failover attempt
raw native handle leaking into event/log/proof
```

Critical/Important finding -> REQUEST_REPAIR on the same carrier; no merge.

- [ ] **Step 3: Create one isolated harmless runtime-review Wake source**

Use an isolated/non-production Executive runtime:

1. create one source Attempt for the canonical review-required fact and one distinct target current OPERATOR_HARNESS Attempt with an already-owned disposable Codex App Server session;
2. create one completed builder Job whose canonical runtime fact requires review and has no sibling review Job;
3. admit that exact runtime fact through `admit_runtime_review_source(...)` and derive one canonical Wake obligation;
4. persist the obligation, resolve the exact Codex target through canonical root/workstream/seat routing, and project the target current Attempt's RuntimeBinding through MAS-237. Prove the source Attempt is not used as the target Attempt.

Checked-in `production_armed` and target-enabled settings remain false. Only the isolated canary composition may construct the bounded delivery-eligible route needed for this proof.

- [ ] **Step 4: Deliver exactly one Wake turn to the existing Codex thread**

Use the existing Wake dispatcher composed with the accepted W3A `CodexCurrentWriterWakeClient`; require:

```text
no App Server construction/start/resume
no provider thread/start or thread/fork lifecycle operation
same exact provider session from the target current RuntimeBinding
same exact target Attempt/process generation/binding generation
one nudge_id
one provider turn submission
one exact provider-native attention turn identity
terminal authenticated DELIVERED receipt from the current writer
reconstructed status == DELIVERED_UNACKNOWLEDGED
```

A timeout/effect-unknown returns to same-operation reconciliation; never submit a second turn merely to obtain a cleaner result.

- [ ] **Step 5: Require the real target session to originate the bounded marker**

After the target actually consumes the wake and recovers canonical state, its exact same-thread response must contain only the accepted marker for the obligation:

```text
MASTERMIND_WAKE_ACK <WAKE-ID>
```

The same worker-local current generation/client reduces the exact completed provider-native attention turn under the terminal-trailer law. The existing `ohf-deliver-attention` response returns only the closed authenticated projection: target Attempt, process generation, binding id/generation, provider session/native turn, nudge id and extracted canonical obligation id(s).

No Slack message, local operator assertion, control-side reader, second App Server/client, delivery receipt or model-authored identity substitutes for this target-originated marker plus the closed current-owner projection.

- [ ] **Step 6: Persist exactly one canonical ACK through the real ingress**

Call the ACK adapter/core and prove:

```text
exact target current RuntimeBinding/generation is re-projected under BEGIN IMMEDIATE
prior DELIVERED evidence matches the exact target Attempt/generation/provider turn/nudge
<WAKE-ID>:ACK is inserted exactly once
raw native handle is absent from durable ACK payload
reconstructed status == TARGET_ACKNOWLEDGED
```

Query the command id after the write and record only secret-free ids/digests in proof.

- [ ] **Step 7: Exercise existing source-resolution law only after ACK**

In the isolated runtime, create the harmless sibling review Job so the original review-required source condition is now absent. Re-read the canonical source facts; prove the review source is no longer present.

Construct the existing healthy source-resolution evidence with:

```python
resolve_source(
    obligation,
    code=SourceResolutionCode.RUNTIME_REVIEW_ABSENT,
    health=SourceReadHealth.HEALTHY,
    source_present=False,
    snapshot_digest=<digest of the canonical source reread>,
    evidence_refs=(<bounded canary evidence refs>,),
)
```

Append `resolved_record(...)` through the existing Wake ledger repository and require final reconstructed status:

```text
SOURCE_RESOLVED
```

The source-resolution snapshot digest comes from the canonical reread; the target ACK/model never supplies it.

- [ ] **Step 8: Prove terminal negative controls after the live canary**

After SOURCE_RESOLVED:

```text
replaying the same ACK -> same existing ACK event
changed ACK payload -> conflict
second nudge for same resolved obligation -> refused/ineligible under existing Wake law
no new provider thread/session exists
checked-in production_armed remains false
checked-in targets remain disabled
```

- [ ] **Step 9: Return exact capability truth to Sol**

Return an immutable-head RESULT containing:

```text
protected base
implementation head
exact changed files
focused/full test counts
hosted CI/security conclusions
review verdict
real Codex native-thread identity represented only by safe digest/opaque evidence
Wake obligation id
nudge id
DELIVERED command id
ACK command id
SOURCE_RESOLVED command id
confirmation of one provider turn and zero retry/failover/new-thread effects
```

Truthful capability after this canary:

```text
Codex/OHF exact-session ACK ingress = PROVEN_LIVE for the bounded canary path
Wake global production arming = NOT ENABLED
Claude/Fable/ChatGPT-web ACK ingress = NOT PROVEN by this wave
```

Do not enable production targets, create another provider adapter/client/reader, merge under a stale release fence, or start a successor wave from the RESULT.

---

## Self-Review Checklist

Before publishing the implementation carrier, verify this plan itself satisfies:

- [ ] Every reasoning-session ACK path requires prior canonical `DELIVERED` evidence.
- [ ] Binding generation is safe durable ACK evidence; raw native handle is never persisted.
- [ ] Model/caller claim contains only canonical Wake obligation ids.
- [ ] Target Attempt/generation/binding/provider-session/native-turn/nudge identity comes from the existing worker-local current owner, not model output or the Wake source Attempt.
- [ ] Current RuntimeBinding is projected under the same Executive `BEGIN IMMEDIATE` transaction as ACK persistence.
- [ ] Human-operator ACK semantics remain compatible.
- [ ] Identical ACK replay is idempotent; changed replay conflicts.
- [ ] `DELIVERED_UNACKNOWLEDGED` remains truthful until the target-claim ingress runs.
- [ ] Existing source-resolution law remains separate and can only close after ACK.
- [ ] No new table, registry, queue, scheduler, retry plane, session DB or lifecycle authority exists.
- [ ] Protected MAS-237/#257, #262 and #254 are reused rather than copied; the current W3A #250 owner chain must be accepted/protected before ACK1 implementation START.
- [ ] First live proof is Codex/OHF-bound only; no unsupported provider claim is made.
- [ ] Production arming remains independent from ACK1 merge/canary success.
