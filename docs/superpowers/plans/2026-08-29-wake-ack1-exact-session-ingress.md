# Wake ACK1 Exact-Session Ingress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first trusted reasoning-session Wake acknowledgement ingress so an exact currently bound Codex/OHF reasoning session can claim only the opaque Wake obligations it actually consumed, while existing Wake law verifies prior delivery/current binding and existing Executive `events` persist `TARGET_ACKNOWLEDGED` exactly once.

**Architecture:** This plan extends the existing Wake acknowledgement codec/causal law and Executive-events persistence; it creates no ACK database or RuntimeBinding owner. MAS-237 / OCR-3 Task 3 must first provide the current ABA-safe RuntimeBinding projection from the one current Operator Harness writer. ACK1 then acquires the existing Executive `BEGIN IMMEDIATE` transaction, projects the current binding inside that lock, validates the target's typed provider observation against an exact prior `DELIVERED` record, and appends the canonical `:ACK` event before releasing the lock. The first provider vertical is Codex App Server; provider-native/model output is reduced to opaque `WAKE-*` claims before entering `control_plane`.

**Tech Stack:** Python 3.11+, existing Executive SQLite `RuntimeStore`, Wake Fabric (`wake_ledger`, `wake_persist`, `session_targets`, `wake_dispatcher`), MAS-237 RuntimeBinding projection, Codex App Server injected-client boundary, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`

## Global Constraints

- **Hard predecessor:** do not START ACK1 code until MAS-237 / OCR-3 Task 3 is protected on then-current Mastermind `master` and exposes `project_runtime_binding(..., connection=...)` backed by the canonical Executive/OHF current writer. If not protected, return exactly `HOLD — RUNTIMEBINDING_PROJECTION_NOT_DURABLE`.
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
- Current `SOL-DIR-PRO` release serialization and every then-current release/collision gate remain independent from code/CI success. A green ACK1 PR is not merge authority.

---

### Task 0: Re-pin the ACK1 execution boundary and prove MAS-237 is durable

**Files:**
- Read only: `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`
- Read only: `control_plane/runtime_binding_projection.py`
- Read only: `control_plane/executive_runtime.py`
- Read only: `control_plane/wake_ledger.py`
- Read only: `control_plane/wake_persist.py`
- Read only: `integrations/executive_wake/codex_app_server.py`

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
integrations/executive_wake/codex_app_server.py
integrations/executive_wake/codex_app_server_ack.py
tests/test_executive_wake_fabric.py
tests/test_executive_wake_fabric_hardening.py
tests/test_executive_wake_persisted_dispatch.py
tests/test_wake_ack_ingress.py
tests/test_codex_app_server_wake_ack.py
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
- Produces only `WakeAckClaim`, `TrustedWakeAckObservation`, `WakeAckIngressError`, and `acknowledge_consumed_wakes(...)`.

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
DELIVERED + exact current binding + exact observed native handle + same nudge -> ACK persists
ACCEPTED-only -> REFUSE
DELIVERED to prior generation -> REFUSE
DELIVERED to another binding id -> REFUSE
DELIVERED to another session alias/surface -> REFUSE
observed native handle != projected RuntimeBinding.native_handle -> REFUSE
missing/blank projected native handle -> REFUSE
obligation without canonical attempt_id in this first vertical -> REFUSE
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
class TrustedWakeAckObservation:
    native_handle: str
    nudge_id: str


class WakeAckIngressError(ValueError):
    pass
```

`WakeAckClaim` validates exact `WAKE_ID_RE` ids, nonempty input, uniqueness and canonical sorted order.

`TrustedWakeAckObservation` validates nonempty native handle and current canonical `NUDGE-*` form. It is constructed only by a trusted provider/host adapter; do not expose it as model input.

- [ ] **Step 6: Implement one helper to recover the requested obligation**

Inside the new module, from connection-scoped Wake records require exactly one `WAKE_REQUESTED` record containing the canonical `WakeObligation`. Refuse missing/duplicate request records.

For this first vertical require `obligation.attempt_id` to be a canonical `ATT-*`; if absent, return a typed ingress refusal rather than guessing a RuntimeBinding source.

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
    trusted: TrustedWakeAckObservation,
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
    obligation.attempt_id,
    target,
    connection=connection,
)
```

and require:

```text
binding.native_handle == trusted.native_handle
binding.binding_id == delivered.binding_id
binding.binding_generation == delivered.binding_generation
binding.session_alias == delivered.session_alias
binding.reasoning_surface == delivered.reasoning_surface
target.target_seat == obligation.declared_target_seat
```

Also require every claimed delivery shares the same trusted `nudge_id`, destination/binding generation and provider-native handle. A coalesced nudge cannot become a cross-destination ACK batch.

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

Do not persist `trusted.native_handle` or `trusted.nudge_id` in the ACK payload; the ACK's delivered-command evidence already points to the canonical delivery record containing that safe route evidence.

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

### Task 4: Add the Codex App Server target-claim adapter without laundering delivery into ACK

**Files:**
- Create: `integrations/executive_wake/codex_app_server_ack.py`
- Create: `tests/test_codex_app_server_wake_ack.py`
- Modify: `integrations/executive_wake/codex_app_server.py`
- Modify: `tests/test_codex_app_server_wake_dispatcher.py`

**Interfaces:**
- Consumes the exact existing Codex App Server native handle/nudge identity and Task-3 provider-neutral ACK ingress.
- Produces one typed provider observation in which the model contributes only `WAKE-*` ids and the trusted client supplies native handle/nudge identity.

- [ ] **Step 1: Freeze the exact target-originated marker protocol in RED tests**

The ACK-capable Wake instruction must preserve the existing statement that the **nudge itself acknowledges nothing** and add one bounded target behavior:

```text
After you have actually consumed the supplied Wake obligation(s) and recovered canonical Executive/Agent OS state, emit one final marker line per consumed obligation:
MASTERMIND_WAKE_ACK <WAKE-ID>
Do not put seat, session, binding, provider, host, nudge, source-resolution or authority data in the marker.
```

Tests must prove the instruction does not say delivery/response automatically equals ACK.

- [ ] **Step 2: Define the trusted Codex observation protocol**

Create:

```python
@dataclasses.dataclass(frozen=True)
class CodexWakeAckObservation:
    native_handle: str
    nudge_id: str
    obligation_ids: tuple[str, ...]


@runtime_checkable
class CodexAppServerWakeAckClient(Protocol):
    async def read_wake_ack_claim(
        self,
        *,
        native_handle: str,
        nudge_id: str,
    ) -> CodexWakeAckObservation | None: ...
```

The injected client is responsible for observing the exact same App Server thread/turn and extracting only exact `MASTERMIND_WAKE_ACK <WAKE-ID>` markers. **Raw model text is not passed into `control_plane`.**

The observation's native handle and nudge id are host/provider evidence, not parsed from model output.

- [ ] **Step 3: Add adversarial adapter tests**

Using a fake injected client, pin:

```text
no marker yet -> no ACK mutation
wrong native_handle -> REFUSE
wrong nudge_id -> REFUSE
malformed marker / attempt command / arbitrary prose -> no valid claim
one valid marker -> one core ACK
multiple valid markers from same nudge -> atomic claim batch
provider read error -> typed failure/no ACK mutation
adapter never calls delivery again while waiting for/processing ACK
```

Also assert the adapter never creates a new provider thread, session or transport fallback.

- [ ] **Step 4: Implement the adapter as composition, not a second dispatcher**

Create a small class:

```python
class CodexAppServerWakeAckIngress:
    def __init__(
        self,
        *,
        runtime: Runtime,
        registry: SessionTargetRegistry,
        client: CodexAppServerWakeAckClient,
    ) -> None:
        ...

    async def consume_claim(
        self,
        *,
        native_handle: str,
        nudge_id: str,
    ) -> tuple[PersistedWakeEvent, ...]:
        ...
```

The method performs exactly one read from the injected ACK client. `None` returns an empty tuple and mutates nothing. A typed observation must echo the exact requested native handle/nudge id before its obligation IDs are passed to `acknowledge_consumed_wakes()`.

Do not make this class a Wake delivery dispatcher and do not call `deliver_wake()` from it.

- [ ] **Step 5: Update the existing Wake instruction only after the adapter exists**

Append the exact marker instruction from Step 1 to `CODEX_WAKE_INSTRUCTION` while retaining the existing sentence:

```text
This nudge grants no authority, acknowledges nothing, and does not resolve the source.
```

The target marker is a claim submitted through the later trusted adapter; the transport receipt remains only ACCEPTED/DELIVERED.

- [ ] **Step 6: Run combined Codex/Wake tests and commit**

```bash
python -m pytest \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_codex_app_server_wake_ack.py \
  tests/test_wake_ack_ingress.py \
  tests/test_executive_wake_persisted_dispatch.py \
  -q
git diff --check
git add integrations/executive_wake/codex_app_server.py \
  integrations/executive_wake/codex_app_server_ack.py \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_codex_app_server_wake_ack.py
git commit -m "feat(exec): bind Codex Wake claim to trusted ACK ingress"
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
one OPERATOR_HARNESS Attempt
one CURRENT session epoch
one current Executive writer process generation
one immutable provider_session_id
one SessionTarget / RuntimeBinding projection
one WAKE_REQUESTED record
one exact DELIVERED record with nudge id
```

Use real Executive/OHF APIs and the protected MAS-237 projection; do not directly insert inconsistent rows to make the happy path easier.

- [ ] **Step 2: Prove one exact target can ACK and a stale generation cannot**

Happy path:

```text
DELIVERED generation N
-> trusted observation native_handle/current nudge
-> ACK ingress under BEGIN IMMEDIATE
-> one TARGET_ACKNOWLEDGED event
```

Then create lawful process generation N+1 and prove the old generation's delivery cannot be ACKed by the new current session. A new ACK command is not minted; the old obligation remains unacknowledged unless a valid new delivery exists.

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
trusted provider/host -> native_handle + nudge observation
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
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_codex_app_server_wake_ack.py \
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
- Consumes the exact immutable ACK1 implementation head, a real installed Codex App Server client, one owner-approved disposable/non-production OHF session, and existing Wake source-resolution primitives.
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

1. create one OPERATOR_HARNESS Attempt with a real owner-approved disposable Codex App Server session;
2. create one completed builder Job whose canonical runtime fact requires review and has no sibling review Job;
3. admit that exact runtime fact through `admit_runtime_review_source(...)` and derive one canonical Wake obligation;
4. persist the obligation and resolve the exact Codex target through the current SessionTarget + MAS-237 RuntimeBinding path.

Checked-in `production_armed` and target-enabled settings remain false. Only the isolated canary composition may construct the bounded delivery-eligible route needed for this proof.

- [ ] **Step 4: Deliver exactly one Wake turn to the existing Codex thread**

Use the existing `CodexAppServerWakeDispatcher`; require:

```text
no thread/start
no thread/fork
same exact native_handle
one nudge_id
one provider turn submission
terminal authenticated DELIVERED receipt
reconstructed status == DELIVERED_UNACKNOWLEDGED
```

A timeout/effect-unknown returns to same-operation reconciliation; never submit a second turn merely to obtain a cleaner result.

- [ ] **Step 5: Require the real target session to originate the bounded marker**

After the target actually consumes the wake and recovers canonical state, its exact same-thread response must contain only the accepted marker for the obligation:

```text
MASTERMIND_WAKE_ACK <WAKE-ID>
```

The injected `CodexAppServerWakeAckClient` returns a typed observation with trusted current native handle/nudge id and only the extracted canonical obligation id(s).

No Slack message, local operator assertion or delivery receipt substitutes for this target-originated marker.

- [ ] **Step 6: Persist exactly one canonical ACK through the real ingress**

Call the ACK adapter/core and prove:

```text
exact current RuntimeBinding/generation is re-projected under BEGIN IMMEDIATE
prior DELIVERED evidence matches the exact target/nudge
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

Do not enable production targets, create another provider adapter, merge under a stale release fence, or start a successor wave from the RESULT.

---

## Self-Review Checklist

Before publishing the implementation carrier, verify this plan itself satisfies:

- [ ] Every reasoning-session ACK path requires prior canonical `DELIVERED` evidence.
- [ ] Binding generation is safe durable ACK evidence; raw native handle is never persisted.
- [ ] Model/caller claim contains only canonical Wake obligation ids.
- [ ] Provider/native handle + nudge identity come from the trusted provider client, not model output.
- [ ] Current RuntimeBinding is projected under the same Executive `BEGIN IMMEDIATE` transaction as ACK persistence.
- [ ] Human-operator ACK semantics remain compatible.
- [ ] Identical ACK replay is idempotent; changed replay conflicts.
- [ ] `DELIVERED_UNACKNOWLEDGED` remains truthful until the target-claim ingress runs.
- [ ] Existing source-resolution law remains separate and can only close after ACK.
- [ ] No new table, registry, queue, scheduler, retry plane, session DB or lifecycle authority exists.
- [ ] MAS-237 is a hard protected-source predecessor, not copied into ACK1.
- [ ] First live proof is Codex/OHF-bound only; no unsupported provider claim is made.
- [ ] Production arming remains independent from ACK1 merge/canary success.
