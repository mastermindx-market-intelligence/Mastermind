# IAC-P1 Production Consultation Packet Carriage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry one bounded Company Consultation QUESTION and ANSWER through the existing Agent Relay exact-thread service with restart-safe readback and no new transport, store, queue, lifecycle, retry, or installation owner.

**Architecture:** Add a canonical consultation packet frame to the existing consultation contract, parameterize the incumbent Relay history/send/reconciliation path by a closed frame kind, and connect #959’s injected packet-carrier seam to the existing AF_UNIX service. Use the incumbent READY/COMMIT `before_write` hook so Relay deterministic checks happen before the protected Runtime fact commits and the Slack effect begins only afterward. P1 is limited to two Worker Attempts that already share one trusted Relay parent thread; cross-session reachability remains the separately reviewed P1-R dependency.

**Tech Stack:** Python 3.12, `asyncio`, frozen dataclasses/enums, AF_UNIX JSON protocol, existing Slack Web API adapter, pytest, Git/GitHub Source Continuity.

**Spec:** `docs/superpowers/specs/2026-09-25-iac1-production-packet-carriage-p1-design.md`

## Global Constraints

- Protected source/procedure pin is exactly `a29161fa0a44cca9927afe042b5f7ea25aae1736`; repin before each modifying phase and stop on material movement.
- Operation and sole source carrier are `iac1-production-packet-carriage-p1-20260925-sol-001`, branch `sol/iac1-production-packet-carriage-p1-20260925-sol-001`, worktree `/Users/chriswong/.mastermind/agent-workspaces/sol/iac1-production-packet-carriage-p1-20260925-sol-001`.
- Preserve #959/#973 as DO_NOT_REDO.
- P1 supports only peers whose trusted bindings share `work_ref`, `commission_ref`, `session_ref`, `operation_key`, `watch_mode`, `thread_ts`, and applicability `job_id`.
- `CONSULTATION_PACKET_MAX_BYTES` initially equals incumbent `MAX_FRAME_BYTES` (`4500`). It may be lowered, not raised, in this operation.
- No truncation, chunking, compression, upload, attachment, alternate channel/thread, or fallback carrier.
- No new database, registry, queue, retry controller, ACK store, daemon, socket, Slack client, scheduler, lifecycle, identity, or notification plane.
- No `DialogueEngineV2.status()` change.
- No token/config/plist/launchd/service/live-Slack effect. `PRODUCTION_PACKET_CARRIAGE` remains `UNAVAILABLE` in P1.
- Every production-code behavior change follows RED → observed expected failure → minimal GREEN → owning/consumer regression.
- First implementation commit after plan/spec is assertion-neutral async migration only.
- Post-COMMIT ambiguity remains `SEND_EFFECT_UNKNOWN` on the original carrier; never retry or fail over automatically.
- `None` from packet read means complete mutation-complete history proved absence. Unknown history/transport/mutation/conflict uses a distinct typed unknown path.
- Draft PR #124 is a stale 1,239-file path overlap on the consultation contract; do not absorb it, and rerun exact merge-tree collision proof before release.

## Review Focus

1. **READY/Runtime/COMMIT interleaving:** a replay/race loser must close after READY without COMMIT; a committed Runtime fact followed by ambiguous COMMIT must stay effect-unknown on the same carrier.
2. **Byte amplification:** quotes, backslashes, CJK, astral characters, maximum evidence/artifact metadata and nested ANSWER JSON must fit rendered packet, AF_UNIX request and Slack response budgets simultaneously.
3. **History poisoning:** well-formed packets must not affect lifecycle adjudication; malformed or mutation-incomplete packet evidence must be visible and fail reconciliation rather than disappear.
4. **Party and carrier authority:** caller/recipient actors, Runtime binding generation and exact parent-thread carrier identity must come only from host-injected bindings and fail before Runtime mutation when mismatched.
5. **Read uncertainty:** a zero-write Company Consultation read must distinguish proven absence from transport/history uncertainty and must never surface `EFFECT_UNKNOWN` merely because a read failed.

---

### Task 1: Assertion-Neutral Async Carrier Migration

**Files:**
- Modify: `integrations/company_consultation_dispatch.py`
- Modify: `tests/test_company_inbox_iac1.py`

**Interfaces:**
- Consumes: current synchronous `ConsultationPacketCarrier` and `RuntimeConsultationDispatcher.consume_answer()`.
- Produces:

```python
class ConsultationPacketCarrier(Protocol):
    async def put_question(
        self, consultation_id: str, frame: Mapping[str, Any]
    ) -> None: ...

    async def get_question(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None: ...

    async def put_answer(
        self, consultation_id: str, frame: Mapping[str, Any]
    ) -> None: ...

    async def get_answer(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None: ...


async def RuntimeConsultationDispatcher.consume_answer(
    self, consultation_ref: str
) -> dict[str, Any]: ...
```

- [ ] **Step 1: Capture the pre-migration assertion oracle**

Run this before editing:

```bash
python3 - <<'PY'
import ast
from pathlib import Path

path = Path("tests/test_company_inbox_iac1.py")
tree = ast.parse(path.read_text())
items = []
for node in ast.walk(tree):
    if isinstance(node, ast.Assert):
        items.append(("assert", ast.dump(node.test, include_attributes=False)))
    if isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            call = item.context_expr
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "raises"
            ):
                items.append(("raises", ast.dump(call, include_attributes=False)))
for item in sorted(items):
    print(repr(item))
PY
```

Save output outside the repository as `/tmp/iac1-p1-async-assertions.before`.

- [ ] **Step 2: Write the migration-only test discriminator**

Add one test that verifies every carrier method is awaitable without changing semantic assertions:

```python
def test_consultation_packet_carrier_methods_are_async(tmp_path: Path) -> None:
    carrier = InMemoryConsultationPacketCarrier()
    assert inspect.iscoroutinefunction(carrier.put_question)
    assert inspect.iscoroutinefunction(carrier.get_question)
    assert inspect.iscoroutinefunction(carrier.put_answer)
    assert inspect.iscoroutinefunction(carrier.get_answer)
```

- [ ] **Step 3: Run the discriminator to verify RED**

Run:

```bash
python -m pytest -q \
  tests/test_company_inbox_iac1.py::test_consultation_packet_carrier_methods_are_async
```

Expected: FAIL because all four methods are synchronous.

- [ ] **Step 4: Make the smallest async-only production change**

Change only `def` → `async def`, add `await` at exact call sites, and make `consume_answer()` async. Do not add parameters, change return values, move calls, or alter exceptions. In tests, use the existing `_run(...)` helper for direct async calls and make synthetic carrier hooks awaitable while preserving the same ordering.

- [ ] **Step 5: Prove assertions and expected values are unchanged**

Run the Step 1 AST extractor again as `/tmp/iac1-p1-async-assertions.after`, then:

```bash
diff -u \
  /tmp/iac1-p1-async-assertions.before \
  /tmp/iac1-p1-async-assertions.after
```

Expected: no diff.

Also run:

```bash
git diff --word-diff=porcelain -- tests/test_company_inbox_iac1.py \
  | grep -E '^[+-].*(assert|pytest\.raises|state|blocker|attention_requested)' \
  && exit 1 || true
```

Expected: no changed assertion/expected-value token.

- [ ] **Step 6: Run the complete current Company Inbox suite**

```bash
python -m pytest -q tests/test_company_inbox_iac1.py
```

Expected: all current tests plus the new async discriminator pass.

- [ ] **Step 7: Commit the isolated migration**

```bash
git add integrations/company_consultation_dispatch.py tests/test_company_inbox_iac1.py
git commit -m "refactor(consultation): make packet carrier async"
```

The commit must contain no other path and no assertion change.

---

### Task 2: Canonical Consultation Packet Wire

**Files:**
- Modify: `common/agent_dialogue_consultation_contract.py`
- Modify: `tests/test_agent_dialogue_consultation_contract.py`

**Interfaces:**
- Consumes: `validate_consultation()`, `canonical_consultation_json()`, incumbent `MAX_FRAME_BYTES`, incumbent secret/mention rejection.
- Produces:

```python
CONSULTATION_PACKET_DISCRIMINATOR = (
    "MMX/AGENT_DIALOGUE_CONSULTATION_PACKET_V1"
)
CONSULTATION_PACKET_MAX_BYTES = MAX_FRAME_BYTES


def render_consultation_packet(
    value: Mapping[str, Any],
) -> str: ...


def parse_consultation_packet(
    raw: str | bytes,
) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write canonical round-trip RED tests**

Add:

```python
def test_consultation_packet_round_trip_is_canonical_and_bounded() -> None:
    frame = _valid_question_frame()
    rendered = render_consultation_packet(frame)
    assert rendered.split("\n", 1)[0] == CONSULTATION_PACKET_DISCRIMINATOR
    assert len(rendered.encode("utf-8")) <= CONSULTATION_PACKET_MAX_BYTES
    assert parse_consultation_packet(rendered) == validate_consultation(frame)
    assert render_consultation_packet(parse_consultation_packet(rendered)) == rendered
```

- [ ] **Step 2: Write hostile-wire RED tests**

Cover all of these in separate parametrized cases:

```text
alternate JSON whitespace
three lines
wrong discriminator
invalid UTF-8
non-finite JSON
unknown key
fingerprint mismatch
NOTICE
CORRECTION
secret-shaped value
Slack mention-shaped value
limit+1 rendered bytes
```

Every case must raise `DialogueContractError`; oversize must raise `FRAME_TOO_LARGE`.

- [ ] **Step 3: Write discriminator non-prefix RED test**

```python
def test_consultation_packet_discriminator_is_disjoint_from_lifecycle_frames() -> None:
    for incumbent in (MESSAGE_DISCRIMINATOR_V2, PARENT_DISCRIMINATOR_V2):
        assert not CONSULTATION_PACKET_DISCRIMINATOR.startswith(incumbent)
        assert not incumbent.startswith(CONSULTATION_PACKET_DISCRIMINATOR)
```

- [ ] **Step 4: Verify RED**

```bash
python -m pytest -q \
  tests/test_agent_dialogue_consultation_contract.py \
  -k 'consultation_packet'
```

Expected: collection/import failure because packet symbols do not exist.

- [ ] **Step 5: Implement strict two-line render/parse**

Use full validation and canonical re-render equality. The parser must reject duplicate JSON keys through an `object_pairs_hook`; do not import a private parser from another contract module. The renderer must check UTF-8 bytes after complete framing.

- [ ] **Step 6: Run contract and semantics consumers**

```bash
python -m pytest -q \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_agent_dialogue_semantics_compatibility.py
```

Expected: green; no existing schema/fingerprint changes.

- [ ] **Step 7: Commit**

```bash
git add common/agent_dialogue_consultation_contract.py \
        tests/test_agent_dialogue_consultation_contract.py
git commit -m "feat(dialogue): add bounded consultation packet wire"
```

---

### Task 3: Preserve Exact Slack History Byte Facts

**Files:**
- Modify: `integrations/slack_agent_dialogue/slack_web_api.py`
- Modify: `tests/test_slack_agent_dialogue_slack_web_api.py`

**Interfaces:**
- Consumes: existing `HistoryPage`, `_collect_history()`, `MAX_RESPONSE_BYTES`, strict Slack message parser.
- Produces:

```python
@dataclass(frozen=True)
class BoundedHistoryPage(HistoryPage):
    response_page_bytes: tuple[int, ...]
    response_byte_limit: int


def estimate_replies_append_bytes(
    *,
    text: str,
    thread_ts: str,
) -> int: ...
```

`fetch_thread()` remains `HistoryPage` compatible and returns `BoundedHistoryPage` for the real client.

- [ ] **Step 1: Write raw-page accounting RED test**

Construct two paginated `SlackHttpResponse` objects with known raw body sizes. Assert:

```python
page = await client.fetch_thread(...)
assert isinstance(page, BoundedHistoryPage)
assert page.response_page_bytes == (len(first.body), len(second.body))
assert page.response_byte_limit == MAX_RESPONSE_BYTES
```

- [ ] **Step 2: Write escaping estimator RED tests**

For plain ASCII, quotes, backslashes, CJK and astral emoji, build the exact synthetic raw message object used by the estimator and assert the returned value is greater than or equal to its canonical encoded byte length. Assert deterministic equality across calls.

- [ ] **Step 3: Preserve oversize refusal RED control**

Keep the existing raw response `MAX_RESPONSE_BYTES + 1` refusal. Add an assertion that no `BoundedHistoryPage` is returned after oversize input.

- [ ] **Step 4: Verify RED**

```bash
python -m pytest -q \
  tests/test_slack_agent_dialogue_slack_web_api.py \
  -k 'page_bytes or append_bytes'
```

Expected: missing symbols/fields.

- [ ] **Step 5: Implement bounded facts without a cache**

Carry each raw `SlackHttpResponse.body` length through `_get`/history parsing into `_collect_history()`. Do not persist, memoize or expose response bodies. The estimator uses the client’s canonical JSON policy and a conservative fixed set of Slack message fields; it does not call Slack.

- [ ] **Step 6: Run all Slack client tests**

```bash
python -m pytest -q tests/test_slack_agent_dialogue_slack_web_api.py
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add integrations/slack_agent_dialogue/slack_web_api.py \
        tests/test_slack_agent_dialogue_slack_web_api.py
git commit -m "feat(dialogue): expose bounded thread byte facts"
```

---

### Task 4: Classify Packet Frames and Generalize the Incumbent Send Flight

**Files:**
- Modify: `integrations/slack_agent_dialogue/engine.py`
- Modify: `integrations/slack_agent_dialogue/engine_v2.py`
- Modify: `integrations/slack_agent_dialogue/turn_observer.py`
- Modify: `tests/test_slack_agent_dialogue_engine_v2.py`
- Modify: `tests/test_slack_agent_dialogue_turn_observer.py`

**Interfaces:**
- Consumes: Task 2 packet wire, Task 3 `BoundedHistoryPage`, existing lifecycle send/reconcile path.
- Produces:

```python
class DialogueFrameKind(str, Enum):
    LIFECYCLE = "LIFECYCLE"
    CONSULTATION_PACKET = "CONSULTATION_PACKET"


@dataclass(frozen=True)
class ReadConsultationPacket:
    packet: Mapping[str, Any]
    primary_ts: str
    duplicate_timestamps: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparedMessageSend:
    # existing fields unchanged
    frame_kind: DialogueFrameKind = DialogueFrameKind.LIFECYCLE
```

Additive methods:

```python
prepare_send_consultation_packet(...)
commit_send_consultation_packet(...)
send_consultation_packet(...)
read_consultation_packet(...)
```

- [ ] **Step 1: Write classification RED tests**

Add a thread with one valid lifecycle frame and one valid consultation packet. Assert `read_thread()` returns exactly the same lifecycle `ThreadRead` as before, while private classification and `read_consultation_packet()` count/return the packet. Add a malformed packet discriminator case that raises `THREAD_MESSAGE_INVALID`.

- [ ] **Step 2: Write mutation coupling RED tests**

An edited/deleted packet with `created_text=None` must produce:

```text
DialogueEngineV2.read_thread -> THREAD_RECONCILIATION_INCOMPLETE
DialogueTurnObserver.reconcile_once -> RECONCILIATION_INCOMPLETE / MUTATION_RECONCILIATION_INCOMPLETE
```

Do not weaken the mutation-first ordering.

- [ ] **Step 3: Write frame-kind key RED tests**

Use the same `(thread_ts, message_key)` for a lifecycle frame and packet:

```python
lifecycle = await engine.prepare_send_message(...)
packet = await engine.prepare_send_consultation_packet(...)
assert lifecycle.frame_kind is DialogueFrameKind.LIFECYCLE
assert packet.frame_kind is DialogueFrameKind.CONSULTATION_PACKET
```

Concurrent commits must reach separate flights; neither conflicts nor coalesces with the other. Two identical packet commits coalesce to one provider write. Same packet kind/key with changed fingerprint raises `MESSAGE_KEY_CONFLICT`.

- [ ] **Step 4: Write packet reconciliation RED tests**

Cover:

```text
commit then provider throws -> same-carrier reread recovers one packet
provider ambiguous and no packet -> SEND_EFFECT_UNKNOWN, no resend
malformed write receipt -> reread recovers
physical duplicate packet -> MESSAGE_KEY_CONFLICT
complete history, zero match -> None
```

- [ ] **Step 5: Write page-budget RED tests**

Create `BoundedHistoryPage` facts and assert:

```text
facts unavailable -> THREAD_HISTORY_BUDGET_UNAVAILABLE
current page + packet + reserve > limit -> THREAD_HISTORY_BUDGET_EXCEEDED
within limit -> READY candidate
```

Pin `CONSULTATION_PACKET_PAGE_RESERVE_BYTES = 13_096` (`2 * MAX_FRAME_BYTES + 4096`).

- [ ] **Step 6: Verify RED**

```bash
python -m pytest -q \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_turn_observer.py \
  -k 'consultation_packet or frame_kind or history_budget'
```

Expected: missing packet engine methods/types.

- [ ] **Step 7: Implement one private classified-history pass**

Refactor `_history()` into:

```python
async def _classified_history(...) -> _ClassifiedThreadHistory: ...

async def _history(...) -> ThreadRead:
    return (await self._classified_history(...)).lifecycle
```

Classify only after the incumbent mutation checks. Lifecycle public result shape remains unchanged. Turn observer parses and counts valid packets privately, excludes them from `classify_turn()`, and refuses malformed packets.

- [ ] **Step 8: Parameterize the incumbent send path**

Keep one `_send_inflight`, one lock, one `_commit_send_once()` and one `_reconcile_post_effect()`. Add `frame_kind` to the key and dispatch validation/render/history lookup through closed private functions. `commit_send_message()` must reject a packet prepared value; `commit_send_consultation_packet()` must reject lifecycle prepared values.

- [ ] **Step 9: Run lifecycle and observer compatibility**

```bash
python -m pytest -q \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_turn_observer.py \
  tests/test_slack_agent_dialogue_turn_watcher.py \
  tests/test_slack_agent_dialogue_wake_projection.py
```

Expected: green; lifecycle status and message semantics unchanged.

- [ ] **Step 10: Commit**

```bash
git add integrations/slack_agent_dialogue/engine.py \
        integrations/slack_agent_dialogue/engine_v2.py \
        integrations/slack_agent_dialogue/turn_observer.py \
        tests/test_slack_agent_dialogue_engine_v2.py \
        tests/test_slack_agent_dialogue_turn_observer.py
git commit -m "feat(dialogue): carry consultation packets through relay engine"
```

---

### Task 5: Extend READY / COMMIT and Exact Packet Read in the Existing Service

**Files:**
- Modify: `integrations/slack_agent_dialogue/service.py`
- Modify: `tests/test_slack_agent_dialogue_service.py`

**Interfaces:**
- Consumes: Task 4 packet engine methods and existing `EXACT_SEND_PROTOCOL`.
- Produces:

```python
_EXACT_SEND_OPERATIONS = {
    "send_message": DialogueFrameKind.LIFECYCLE,
    "send_consultation_packet": DialogueFrameKind.CONSULTATION_PACKET,
}
```

Add V2 operation `read_consultation_packet` with exact args `context`, `thread_ts`, `consultation_id`, `purpose`.

- [ ] **Step 1: Write exact-send closed-set RED test**

Assert `_is_exact_send_request()` accepts both closed operations and refuses every near-name. Assert `call_service()` classifies both as exact sends and leaves all other operations unchanged.

- [ ] **Step 2: Write real AF_UNIX QUESTION/ANSWER RED tests**

Run the actual service over a temporary Unix socket. For each purpose:

```text
client sends request
server returns READY with exact fingerprint
before_write callback runs exactly once
client sends COMMIT
one provider post occurs
closed parent-bound receipt returns
fresh service call reads exactly that packet
```

- [ ] **Step 3: Write post-COMMIT ambiguity RED tests**

For the packet operation, simulate:

```text
commit bytes sent, response lost
commit handler raises after provider boundary
oversize/malformed response after commit
```

Every case must raise `DialogueServiceError("SEND_EFFECT_UNKNOWN")`, never `SERVICE_UNAVAILABLE`.

- [ ] **Step 4: Write exact-read RED tests**

`read_consultation_packet` returns one closed packet result or `None`; multiple physical packets and malformed packet evidence return typed engine errors. The service never returns a whole `ThreadRead` for this operation.

- [ ] **Step 5: Verify RED**

```bash
python -m pytest -q \
  tests/test_slack_agent_dialogue_service.py \
  -k 'consultation_packet'
```

Expected: `REQUEST_INVALID`/missing operation support.

- [ ] **Step 6: Implement one operation map**

Use `_EXACT_SEND_OPERATIONS` in `_is_exact_send_request()`, `_handle_exact_send()` and `call_service()`. Keep request keys and READY/COMMIT envelopes byte-identical. Select prepare/commit methods by frame kind; do not duplicate the protocol handler.

- [ ] **Step 7: Run complete service suite**

```bash
python -m pytest -q tests/test_slack_agent_dialogue_service.py
```

Expected: green.

- [ ] **Step 8: Commit**

```bash
git add integrations/slack_agent_dialogue/service.py \
        tests/test_slack_agent_dialogue_service.py
git commit -m "feat(dialogue): expose exact consultation packet service"
```

---

### Task 6: Add Trusted Same-Parent Carrier Adapter

**Files:**
- Modify: `integrations/company_consultation_dispatch.py`
- Modify: `tests/test_company_inbox_iac1.py`

**Interfaces:**
- Consumes: existing `DialogueBindingResolver`, `DialogueBinding`, `call_service()`, Task 5 packet operations.
- Produces:

```python
class ConsultationPacketCarrierUnknown(RuntimeError): ...
class ConsultationPacketEffectUnknown(RuntimeError): ...
class ConsultationPacketCommitAborted(RuntimeError): ...


PacketCommitHook = Callable[[], Awaitable[None]]


class ConsultationPacketCarrier(Protocol):
    async def put_question(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None: ...
    # same pattern for put_answer; reads remain async Mapping | None


class AgentDialogueConsultationPacketCarrier:
    def __init__(
        self,
        *,
        binding_resolver: DialogueBindingResolver,
        socket_path: Path,
        service_call: Callable[..., Awaitable[dict[str, Any]]] = call_service,
        timeout_seconds: float = 30.0,
    ) -> None: ...
```

`CallerIdentity` and `RecipientBinding` gain optional host-injected `dialogue_binding: DialogueBinding | None = None` fields. Existing in-memory tests remain valid when both are `None`; production carrier use requires both exact bindings.

- [ ] **Step 1: Write carrier-identity RED tests**

Build trusted caller/recipient bindings. Assert admission only when all of these match:

```text
work_ref
commission_ref
session_ref
operation_key
watch_mode
thread_ts
applies_to.job_id
```

Parametrize one-field drift. Every drift is a typed zero-effect refusal before Runtime INTENT, carrier write or Wake.

- [ ] **Step 2: Write party/direction RED tests**

Assert:

```text
QUESTION binding.actor_ref == requester_actor_ref
ANSWER binding.actor_ref == recipient_actor_ref
frame recipient_binding == trusted recipient Runtime binding
unrelated party cannot read either packet
```

- [ ] **Step 3: Write adapter service-mapping RED tests**

Using a fake `service_call`, prove:

```text
put passes send_consultation_packet with trusted context/thread only
before_commit is passed as call_service.before_write
read passes read_consultation_packet and never read_thread
null result -> None
transport/history error -> ConsultationPacketCarrierUnknown
post-COMMIT SEND_EFFECT_UNKNOWN -> ConsultationPacketEffectUnknown
```

- [ ] **Step 4: Verify RED**

```bash
python -m pytest -q \
  tests/test_company_inbox_iac1.py \
  -k 'agent_dialogue_packet_carrier or same_parent_carrier or packet_party'
```

Expected: carrier class and binding fields missing.

- [ ] **Step 5: Implement adapter and async in-memory hook**

The in-memory carrier calls `await before_commit()` immediately before storing the frame. The production adapter resolves a fresh binding per operation, constructs `DialogueContextV2`, validates exact party/direction and uses only the trusted thread. It never imports or constructs a Slack client.

- [ ] **Step 6: Run focused carrier tests and current Company Inbox tests**

```bash
python -m pytest -q tests/test_company_inbox_iac1.py
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add integrations/company_consultation_dispatch.py \
        tests/test_company_inbox_iac1.py
git commit -m "feat(consultation): add trusted relay packet carrier"
```

---

### Task 7: Compose READY / Runtime / COMMIT in the Dispatcher

**Files:**
- Modify: `integrations/company_consultation_dispatch.py`
- Modify: `tests/test_company_inbox_iac1.py`

**Interfaces:**
- Consumes: Task 2 render/parse, Task 6 callback carrier, protected Consultation Runtime/Wake owners.
- Produces:

```python
def _packet_safe_answer_payload_limit(
    question_frame: Mapping[str, Any],
) -> int: ...
```

and dispatcher ordering that commits Runtime only inside the carrier’s pre-COMMIT callback.

- [ ] **Step 1: Write pre-INTENT byte RED tests**

For oversize QUESTION and a question whose derived safe answer budget is zero, assert:

```text
zero INTENT events
zero carrier puts
zero Wake records
typed INVALID_REQUEST/BODY_OVER_BUDGET
```

Use quote/backslash/CJK/astral and maximum evidence/artifact metadata cases.

- [ ] **Step 2: Write derived answer-budget RED tests**

Build a lawful packet-wire QUESTION at metadata maxima. Assert:

```text
persisted max_evidence_reads == requested max_evidence_reads
persisted max_payload_bytes == pure helper result
plain / quote / backslash / CJK / astral payloads at the semantic limit
  -> complete ANSWER packet <= 4500 bytes
payload one byte above -> dispatcher refuses before ANSWER_AVAILABLE
an evidence-count contract with no positive safe payload
  -> BODY_OVER_BUDGET before Runtime/carrier effects, never silent narrowing
```

The tests must use the actual `_build_answer_frame()` nested JSON path and maximum-length valid evidence references.

- [ ] **Step 3: Write READY/Runtime/COMMIT interleaving RED tests**

Use a controlled async carrier and prove these exact orders:

```text
prepare -> before_commit(INTENT inserted) -> physical QUESTION put -> question Wake
prepare -> before_commit(ANSWER admitted) -> physical ANSWER put -> answer attention
```

A Runtime replay/race loser raises `ConsultationPacketCommitAborted`; no physical write occurs; fresh Runtime+packet readback reconciles instead. The race test must return the winner’s real packet on the initial awaited read, not hide it. If Relay reports a duplicate before this caller’s callback because another identical caller won, return truthful replay/reconciled state with `inserted=False`; if no exact Runtime fact exists, refuse the physical packet as an orphan conflict rather than manufacturing INTENT/ANSWER state.

- [ ] **Step 4: Write post-COMMIT effect-unknown RED tests**

When the Runtime fact commits and the carrier raises `ConsultationPacketEffectUnknown`:

```text
Runtime fact remains durable
no blind resend
result/blocker is CARRIER_RECONCILIATION_REQUIRED
attention_requested uses exact ledger readback True/False/None
identical retry reads the same carrier before any write
```

- [ ] **Step 5: Write guarded-read RED tests**

For QUESTION and ANSWER reads:

```text
complete proven absence -> CARRIER_UNAVAILABLE / body unavailable
carrier unknown -> typed CARRIER_RECONCILIATION_REQUIRED
company.consultation remains ok:true, zero-write, never EFFECT_UNKNOWN
question/answer legs are read independently
known question is preserved when answer history is unknown
canonical Runtime blocker is preserved; carrier_blocker records transport uncertainty
consume/reply map answer unknown without pretending absence or appending events
```

Also add a carrier-adapter discriminator proving an untyped callback/programmer exception is not laundered into `ConsultationPacketCarrierUnknown`, and a pre-callback abort discriminator proving no committed-shaped result can be returned without a Runtime fact.

- [ ] **Step 6: Re-prove async interleavings**

Convert the existing consume-during-answer-put fixture to an actual await boundary. Assert consumption between carrier READY and first answer-Wake append creates zero answer-attention request. Re-run publication uniqueness, no-late-Wake and restart replay tests with asynchronous hooks.

- [ ] **Step 7: Verify RED**

```bash
python -m pytest -q \
  tests/test_company_inbox_iac1.py \
  -k 'packet_budget or ready_runtime_commit or carrier_unknown or consume_during'
```

Expected: current ordering/return semantics fail the new discriminators.

- [ ] **Step 8: Implement minimal dispatcher composition**

Move `intent()` and `answer_available()` into local async `before_commit` callbacks. Preserve existing inserted/replay/refusal identities. Static packet render happens before carrier invocation; Relay prepare/page budget happens before callback. After Runtime replay abort or duplicate-before-callback return, re-read canonical Runtime and the exact packet, default insertion credit to false, and never COMMIT or resend. Catch only typed carrier uncertainty; arbitrary callback defects propagate.

- [ ] **Step 9: Run full protected Company Inbox/Runtime/Wake envelope**

```bash
python -m pytest -q \
  tests/test_company_inbox_iac1.py \
  tests/test_w6c2_consultation_runtime.py \
  tests/test_dialogue_source_resolution.py \
  tests/test_executive_wake_fabric.py
```

Expected: green.

- [ ] **Step 10: Commit**

```bash
git add integrations/company_consultation_dispatch.py \
        tests/test_company_inbox_iac1.py
git commit -m "feat(consultation): commit packets through runtime gate"
```

---

### Task 8: Prove the Complete Source-Only Vertical and Freeze the Release Candidate

**Files:**
- Modify only if a failing test proves a correctness defect in the already-owned P1 paths.
- Test: all paths listed below.

**Interfaces:**
- Consumes: Tasks 1–7 exact committed interfaces.
- Produces: one immutable Draft/HOLD PR candidate with complete source evidence; no installation or live effect.

- [ ] **Step 1: Add full AF_UNIX restart journey test**

Use a real temporary `AgentDialogueService`, real `call_service()`, real `RuntimeConsultationDispatcher`, real Runtime/Wake ledger and fake Slack transport. Prove:

```text
A and B share one trusted parent thread/job carrier
A QUESTION reaches one physical packet
service and dispatcher are destroyed/recreated
B reads the same QUESTION and replies
one physical ANSWER packet appears
service and dispatcher are destroyed/recreated
A reads and explicitly consumes the same ANSWER
one question Wake, one answer-attention Wake, one CONSUMED_BY_REQUESTER
no duplicate physical packet or Wake record
```

- [ ] **Step 2: Add negative architecture test**

Static AST/path assertions must fail if P1 adds any of:

```text
sqlite/table/store/cache/registry/queue/retry/scheduler/daemon
new socket listener
new Slack client construction in company dispatch
launchctl/plist/token/config operations
module-level mutable packet state
```

Run the scan over the operation delta, not inherited protected source, and allow only the existing injected in-memory test carrier.

- [ ] **Step 3: Run the owning and consumer campaign**

```bash
python -m pytest -q \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_agent_dialogue_semantics_compatibility.py \
  tests/test_slack_agent_dialogue_slack_web_api.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_service.py \
  tests/test_slack_agent_dialogue_turn_observer.py \
  tests/test_slack_agent_dialogue_turn_watcher.py \
  tests/test_slack_agent_dialogue_wake_projection.py \
  tests/test_company_inbox_iac1.py \
  tests/test_w6c2_consultation_runtime.py \
  tests/test_dialogue_source_resolution.py \
  tests/test_executive_wake_fabric.py
```

Record collected/passed/skipped counts separately; do not sum incompatible campaigns.

- [ ] **Step 4: Run static gates**

```bash
python -m compileall -q common control_plane integrations tests
find scripts ops/executive_os -type f -name '*.sh' -print0 \
  | xargs -0 -n1 bash -n
git diff --check
git status --short
```

Expected: clean.

- [ ] **Step 5: Execute hostile mutants**

Each mutant must fail a named test, then be fully restored:

```text
change packet discriminator to lifecycle-prefix extension
raise packet ceiling above 4500
remove pre-INTENT render check
remove frame_kind from send-flight key
map packet post-COMMIT failure to SERVICE_UNAVAILABLE
silently skip malformed packet frame
move mutation check after discriminator filter
map unknown read to None
allow caller-supplied thread_ts
send packet before Runtime callback
retry after SEND_EFFECT_UNKNOWN
```

Record the exact test that kills each mutant.

- [ ] **Step 6: Re-pin and reconcile current protected source**

Read protected `master`, Skillpack INDEX and every loaded procedure from one exact commit. Compare every owned path. If protected movement is material, compose current base without reset/rebase/force and rerun affected tests.

- [ ] **Step 7: Re-run open-PR collision census**

Check all open PRs for the exact owned path set. For #124, compare exact current blobs and merge-tree conflict. Do not absorb #124’s stale history. Any new semantic owner collision requires Sol adjudication before publication.

- [ ] **Step 8: Obtain Source Continuity before publication**

Run canonical writer gate and `CHECKPOINT_VERIFIED` against the exact operation, branch, owned paths and `RECONCILED_NO_OPEN_EFFECT`. Stop on dirt, remote drift, another writer or effect uncertainty.

- [ ] **Step 9: Commit final test/evidence delta and push once**

```bash
git add <only owned P1 paths>
git commit -m "test(consultation): prove relay packet carriage vertical"
git push -u origin sol/iac1-production-packet-carriage-p1-20260925-sol-001
```

No blind push retry. Reconcile the original carrier if publication is ambiguous.

- [ ] **Step 10: Open one Draft/HOLD PR**

The PR body must state:

```text
BUILT_NOT_PROVEN / SOURCE_ONLY / PRODUCTION_DISARMED
same-parent-thread only
4500-byte packet ceiling
packet mutation can block shared reconciliation
P1-R required for cross-session reachability
no token/config/plist/service/live Slack effect
```

Request one independent exact-head review after hosted CI starts.

- [ ] **Step 11: Consume exact-head CI and independent review**

Repair only newly proven Critical/Important findings with new RED tests on the same carrier. Approval, CI, source acceptance, merge, installation and live proof remain separate.

- [ ] **Step 12: Terminal source ruling**

Only after exact-head review, hosted required checks, current-base proof and `REMOTE_COMPLETE_VERIFIED` may Sol issue source acceptance/STOP and separately decide release maintenance. P1 acceptance does not authorize P2.
