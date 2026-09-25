# IAC-P1 Production Consultation Packet Carriage — Corrected Design

**Date:** 2026-09-25  
**Program:** `agent-fabric-end-to-end-fable-integration-20260913-sol-001`  
**Operation:** `iac1-production-packet-carriage-p1-20260925-sol-001`  
**Chairman:** Chris Wong  
**Meta-CEO:** Sol  
**Protected source and procedure pin:** `a29161fa0a44cca9927afe042b5f7ea25aae1736`  
**Protected tree:** `17b55023edd3e08d0ad45575f8c8b88669ef33cc`  
**Controlling ruling:** Mastermind #600 comment `5825023854`  
**Architecture falsifier:** read-only Opus session `1c41798d-3526-418e-9b71-39192b06b483`; artifact SHA-256 `cecb6ec6f09f58afb6aac82aecf67647283a33f85b448275251e0d22596b5d03`  
**State:** `DESIGN_FROZEN / SOURCE_ONLY / PRODUCTION_DISARMED`

---

## 1. Outcome

IAC-P1 makes one machine-readable Company Consultation QUESTION and one machine-readable ANSWER survive a process restart through the already-existing Agent Relay exact-thread service. It connects the protected #959 `ConsultationPacketCarrier` seam to the incumbent Relay engine/service without creating a mailbox database, second Slack client, packet daemon, queue, retry controller, ACK store, session registry, target router, or lifecycle.

The first bounded vertical is intentionally narrower than the final company outcome:

```text
requester Worker Attempt
  and recipient Worker Attempt
  already share one trusted Agent Relay parent thread

Company Consultation QUESTION
  -> canonical consultation packet wire
  -> incumbent Relay READY / COMMIT
  -> one physical Slack reply in that exact parent thread
  -> fresh-process packet readback
  -> protected Consultation Runtime / Company Inbox / Wake owners

Company Consultation ANSWER
  -> the same path in the reverse party direction
  -> requester-directed answer attention from protected #959
```

P1 is useful because it replaces the process-local test carrier with a durable, restart-safe physical carrier for already-co-located company peers. It does not pretend that a peer in a different session or job can already be reached.

---

## 2. Preserved full ambition and the P1-R dependency

The Chairman’s required product remains arbitrary lawful session-to-session consultation. Protected source does not yet own a trusted projection from one worker’s identity to another worker’s Relay parent thread. Current Agent Relay authority binds one caller to one parent identity:

```text
work_ref
commission_ref
session_ref
operation_key
watch_mode
thread_ts
applicability-carrier job_id
```

Therefore P1 admits only peers whose trusted caller and recipient `DialogueBinding` values match on all seven fields above. Their Worker Attempts and workers may differ.

After P1 source acceptance, a separate reviewed **P1-R reachability amendment** must evolve the incumbent Company Dialogue / Agent Relay binding owner to project one canonical authorized consultation carrier across sessions. P1-R may not add a thread registry, mailbox, router, queue, or second transport owner. Until P1-R exists, cross-session and cross-job consultation remains `NOT_BUILT`, not silently emulated.

---

## 3. Canonical owners and no-rebuild boundary

| Fact or effect | Existing owner | P1 relationship |
|---|---|---|
| consultation frame semantics and fingerprint | `common/agent_dialogue_consultation_contract.py` | add one wire renderer/parser only |
| caller/recipient Runtime identity | protected Consultation Runtime + injected host facts | consume and revalidate |
| exact Relay parent context/thread | Company Dialogue binding owner | consume only; caller/model never supplies it |
| Slack history and physical reply | existing `SlackWebApiDialogueClient` | reuse one client |
| prepare, single-flight, commit and reconcile | existing `DialogueEngineV2` | parameterize by a closed frame kind |
| AF_UNIX authentication and READY/COMMIT | existing Agent Relay service | extend the closed operation set |
| question/answer Runtime facts and Wake | protected #959 owners | preserve and compose |
| installation/enrollment/activation | existing Executive OS scripts | P2 only; no P1 effect |

P1 creates no second source of truth. GitHub remains source/evidence truth. Executive OS remains service/lifecycle truth. Slack is the physical packet carrier, not a lifecycle or acceptance authority.

---

## 4. Same-parent-thread admission contract

The host supplies trusted `DialogueBinding` values for the caller and the resolved recipient. P1 compares the following exact carrier identity before any Runtime or Slack effect:

```python
CarrierIdentity = tuple[
    str,                  # work_ref
    Mapping[str, object], # commission_ref, canonicalized
    str,                  # session_ref
    str,                  # operation_key
    str | None,           # watch_mode
    str,                  # thread_ts
    str,                  # applies_to.job_id
]
```

Admission requires:

1. caller `DialogueBinding.actor_ref` equals the host-injected `CallerIdentity` job/attempt/worker;
2. recipient `DialogueBinding.actor_ref` equals the trusted `RecipientBinding.actor_ref`;
3. caller and recipient carrier identities are equal;
4. the consultation frame requester/recipient actors equal those trusted actors;
5. the frame-carried `recipient_binding` equals the trusted recipient Runtime binding id, generation and reasoning surface;
6. QUESTION sender is the immutable requester; ANSWER sender is the admitted recipient;
7. neither model input nor the consultation frame supplies channel, thread, session, work, commission, operation or carrier authority.

A mismatch is a typed known-no-effect refusal before `ConsultationRuntime.intent()` or `answer_available()`.

---

## 5. Consultation packet wire

The wire is owned by `common/agent_dialogue_consultation_contract.py`:

```text
MMX/AGENT_DIALOGUE_CONSULTATION_PACKET_V1
<canonical consultation JSON>
```

Public constants and functions:

```python
CONSULTATION_PACKET_DISCRIMINATOR = (
    "MMX/AGENT_DIALOGUE_CONSULTATION_PACKET_V1"
)
CONSULTATION_PACKET_MAX_BYTES = MAX_FRAME_BYTES  # initially 4500


def render_consultation_packet(
    value: Mapping[str, Any],
) -> str: ...


def parse_consultation_packet(
    raw: str | bytes,
) -> dict[str, Any]: ...
```

Rules:

- exactly two lines;
- UTF-8 strict decoding;
- QUESTION and ANSWER only;
- full `validate_consultation()` validation, including secret/mention rejection;
- canonical JSON equality on parse, so alternate whitespace, duplicate keys, non-finite numbers and semantic aliases fail;
- rendered UTF-8 length `<= 4500` bytes;
- no truncation, chunking, file upload, attachment, compression or alternate carrier;
- discriminator is not a prefix of, and has no incumbent discriminator as its prefix, for `MMX/AGENT_DIALOGUE_V2` and the V2 parent discriminator.

The 4500-byte ceiling may be lowered by evidence. It may not be raised without a new measured thread-page proof and independent review.

---

## 6. Byte and history budget

Three different byte surfaces must remain distinct:

1. rendered packet bytes;
2. canonical AF_UNIX request-line bytes after the packet is JSON-escaped inside the service request;
3. Slack `conversations.replies` response-page bytes after Slack JSON-escapes the packet text.

The contract ceiling controls (1). The service’s existing `DEFAULT_MAX_REQUEST_BYTES` controls (2). The Slack client’s existing `MAX_RESPONSE_BYTES` controls each page in (3).

The existing Slack client gains bounded read facts, not a new store:

```python
@dataclass(frozen=True)
class BoundedHistoryPage(HistoryPage):
    response_page_bytes: tuple[int, ...]
    response_byte_limit: int
```

`SlackWebApiDialogueClient._collect_history()` records the exact raw body length for every fetched page. Existing `fetch_thread()` still returns a `HistoryPage`-compatible object. Lifecycle callers do not require these facts. Packet preparation fails closed before READY when the client does not provide them.

The existing client also exposes a pure conservative estimator:

```python
def estimate_replies_append_bytes(
    *,
    text: str,
    thread_ts: str,
) -> int: ...
```

It serializes a worst-case Slack message object through the same JSON policy used by the client. Before READY, packet preparation requires:

```text
max(response_page_bytes)
+ estimate_replies_append_bytes(packet_text, thread_ts)
+ CONSULTATION_PACKET_PAGE_RESERVE_BYTES
<= response_byte_limit
```

The fixed reserve is exactly `CONSULTATION_PACKET_PAGE_RESERVE_BYTES = 13_096` (`2 * 4500 + 4096`): two incumbent maximum lifecycle frames plus JSON envelope margin. Tests pin this constant and prove that the accepted packet cannot consume the whole history page. Unavailable facts are `THREAD_HISTORY_BUDGET_UNAVAILABLE`; an exceeded budget is `THREAD_HISTORY_BUDGET_EXCEEDED`. Both are pre-effect refusals.

The test matrix measures quote-heavy, backslash-heavy, CJK and astral payloads; maximum evidence refs; maximum artifact revisions; all receipts; and the ANSWER’s nested JSON encoding. No size claim is inferred from character count.

---

## 7. Safe answer payload budget

The current consultation contract permits `response_budget.max_payload_bytes` up to 32768, which cannot fit the P1 packet wire. P1 derives and freezes a packet-safe answer budget when the QUESTION is built.

Pure helper in `integrations/company_consultation_dispatch.py`:

```python
def _packet_safe_answer_payload_limit(
    question_frame: Mapping[str, Any],
) -> int: ...
```

The helper uses the actual immutable QUESTION metadata and a binary search over valid worst-case answer payloads, including the maximum allowed evidence references and nested JSON escaping, to find the largest canonical semantic-answer byte count whose complete rendered ANSWER packet stays within `CONSULTATION_PACKET_MAX_BYTES`.

The QUESTION’s persisted response budget becomes:

```python
max_payload_bytes = min(
    requested_max_payload_bytes,
    _packet_safe_answer_payload_limit(question_frame),
)
```

The frame is rebuilt until the clamped budget is stable, then rendered again. At reply time the actual ANSWER packet is rendered before `answer_available()` as a final invariant check. A zero safe budget is `BODY_OVER_BUDGET` with zero effect.

---

## 8. Frame classification without lifecycle reinterpretation

The Relay thread can contain three closed frame families:

- V2 parent frame;
- V2 lifecycle message frame;
- P1 consultation packet frame.

`DialogueEngineV2` performs one mutation-first bounded history scan and classifies every non-parent reply. A private result keeps the families separate:

```python
@dataclass(frozen=True)
class _ClassifiedThreadHistory:
    lifecycle: ThreadRead
    consultation_packets: tuple[ReadConsultationPacket, ...]
    consultation_packet_count: int
```

A well-formed packet is parsed, authority-filtered, counted and excluded from lifecycle `classify_turn()` input. A packet never becomes `PROGRESS`, `RESULT`, `BLOCKED`, `DECISION_REQUEST`, ACK or ruling evidence.

A packet with the exact packet discriminator but malformed content raises `THREAD_MESSAGE_INVALID`. It is never silently skipped. A packet edit/deletion without complete creation evidence preserves the incumbent mutation-first law and raises `THREAD_RECONCILIATION_INCOMPLETE`; the turn observer returns `RECONCILIATION_INCOMPLETE`. This coupling is an explicit P1 ceiling.

`ThreadRead`, lifecycle service results and `DialogueEngineV2.status()` retain their current public shapes. Packet counts stay in the private classified result and in the dedicated packet read result, avoiding an unrelated lifecycle API generation.

The turn observer’s private `_accepted_history()` returns a fourth internal value, `consultation_packet_count`, after validating packet frames. `reconcile_once()` ignores the count for lifecycle adjudication but tests prove it was classified rather than silently skipped.

---

## 9. Engine frame-kind extension

Closed frame kinds:

```python
class DialogueFrameKind(str, Enum):
    LIFECYCLE = "LIFECYCLE"
    CONSULTATION_PACKET = "CONSULTATION_PACKET"
```

`PreparedMessageSend` gains a final defaulted field:

```python
frame_kind: DialogueFrameKind = DialogueFrameKind.LIFECYCLE
```

Lifecycle public methods remain:

```python
prepare_send_message(...)
commit_send_message(...)
send_message(...)
read_thread(...)
```

Packet methods are additive:

```python
async def prepare_send_consultation_packet(
    *,
    thread_ts: str,
    context: DialogueContextV2,
    packet: Mapping[str, Any],
) -> PreparedMessageSend | MessageReceipt: ...

async def commit_send_consultation_packet(
    prepared: PreparedMessageSend | MessageReceipt,
    *,
    fingerprint: str,
) -> MessageReceipt: ...

async def send_consultation_packet(... ) -> MessageReceipt: ...

async def read_consultation_packet(
    *,
    thread_ts: str,
    context: DialogueContextV2,
    consultation_id: str,
    purpose: str,
) -> ReadConsultationPacket | None: ...
```

`ReadConsultationPacket` contains the validated packet, physical timestamp and no duplicate timestamps. Zero exact matches on complete mutation-complete history returns `None`. More than one physical match, conflicting fingerprint or malformed packet raises a typed engine error.

The single-flight key becomes:

```python
(frame_kind, thread_ts, message_key)
```

The same key in different frame kinds neither coalesces nor conflicts. The same kind/key with a different fingerprint remains `MESSAGE_KEY_CONFLICT`. All frame kinds reuse the same `_send_inflight`, lock, provider call, receipt validation and post-effect reconciliation.

---

## 10. AF_UNIX service extension

Closed exact-send operation map:

```python
_EXACT_SEND_OPERATIONS = {
    "send_message": DialogueFrameKind.LIFECYCLE,
    "send_consultation_packet": DialogueFrameKind.CONSULTATION_PACKET,
}
```

The request envelope remains byte-compatible:

```json
{
  "version": "mastermind.agent_dialogue_control.v2",
  "operation": "send_consultation_packet",
  "args": {
    "context": {},
    "thread_ts": "...",
    "message": {},
    "send_protocol": "mastermind.agent_dialogue_exact_send.v1"
  }
}
```

`_is_exact_send_request()`, `_handle_exact_send()` and `call_service()` all derive behavior from the same closed map. READY contains the packet fingerprint. COMMIT retains the same two-key envelope. Any ambiguity after COMMIT is `SEND_EFFECT_UNKNOWN`; a new operation name never falls through to `SERVICE_UNAVAILABLE`.

Read operation:

```json
{
  "version": "mastermind.agent_dialogue_control.v2",
  "operation": "read_consultation_packet",
  "args": {
    "context": {},
    "thread_ts": "...",
    "consultation_id": "consult-...",
    "purpose": "QUESTION"
  }
}
```

The result is either `null` for proven absence or one closed `ReadConsultationPacket`. It never returns the whole thread.

---

## 11. READY / Runtime / COMMIT ordering

The existing `call_service(..., before_write=...)` hook is the crucial no-rebuild seam. For exact send, it runs after the server has completed deterministic prepare/history/budget checks and returned READY, but before the client sends COMMIT.

P1 uses that seam as follows:

### First QUESTION

```text
Relay PREPARE packet
  -> exact thread/context/party validation
  -> packet size and page-budget validation
  -> duplicate readback
  -> READY (no Slack effect)

before_write callback
  -> ConsultationRuntime.intent()
  -> only inserted=True authorizes COMMIT

COMMIT
  -> one incumbent provider write
  -> same-carrier reread/reconciliation
  -> then question Wake request
```

### First ANSWER

```text
Relay PREPARE packet
  -> exact carrier readback and budget validation
  -> READY

before_write callback
  -> ConsultationRuntime.answer_available()
  -> only one newly admitted non-historical answer authorizes COMMIT

COMMIT
  -> one incumbent provider write
  -> same-carrier reread/reconciliation
  -> requester answer-attention request
```

If the Runtime callback returns replay/already-existing state, it raises a local pre-COMMIT abort. Closing the READY connection causes no provider effect. The dispatcher then reconciles the exact existing packet through `read_consultation_packet()`; it never resends.

If the Runtime callback commits and COMMIT is later ambiguous, the Runtime fact is known and packet effect is `EFFECT_UNKNOWN` on the original carrier. The dispatcher returns `CARRIER_RECONCILIATION_REQUIRED` and never retries automatically.

This is not a new transaction coordinator. It is composition of the incumbent READY/COMMIT effect gate with the incumbent Runtime transaction.

---

## 12. Async migration boundary

The first implementation commit after plan/spec is assertion-neutral:

```python
class ConsultationPacketCarrier(Protocol):
    async def put_question(...): ...
    async def get_question(...): ...
    async def put_answer(...): ...
    async def get_answer(...): ...

async def RuntimeConsultationDispatcher.consume_answer(...): ...
```

Only these changes are admitted in that commit:

- `def` to `async def` for the four carrier methods and `consume_answer`;
- `await` at their exact call sites;
- test fixture calls wrapped in the existing async runner;
- async test-carrier hooks that preserve the same ordering.

A token-level proof compares all test assertions and expected literals before/after. No assertion text, expected value, refusal code, state label or ordering comment may change. Semantic packet behavior lands only in later commits with its own RED evidence.

---

## 13. Production carrier

Add `AgentDialogueConsultationPacketCarrier` to the incumbent Company Consultation dispatcher module. It is an adapter, not an owner.

Constructor:

```python
class AgentDialogueConsultationPacketCarrier:
    def __init__(
        self,
        *,
        binding_resolver: DialogueBindingResolver,
        socket_path: Path,
        service_call: ServiceCall = call_service,
        timeout_seconds: float = 30.0,
    ) -> None: ...
```

Each operation resolves the current trusted `DialogueBinding`, builds `DialogueContextV2`, validates the caller’s party/direction, and calls the incumbent service. No direct Slack client is allowed.

Write methods accept one `before_commit` awaitable callback. Read methods return a frame or `None`; `None` is permitted only after a complete, mutation-complete service result proves absence. Transport, incomplete history, mutation uncertainty or conflicting physical packets raise `ConsultationPacketCarrierUnknown`.

The dispatcher catches that exception:

- zero-write `company.consultation` returns an unknown-shaped `CARRIER_RECONCILIATION_REQUIRED` body blocker and never `EFFECT_UNKNOWN`;
- consult/reply after a durable Runtime fact returns the existing committed envelope with `CARRIER_RECONCILIATION_REQUIRED`;
- pre-Runtime unknown returns a known typed refusal with zero Runtime/Wake effect;
- proven absence alone maps to `CARRIER_UNAVAILABLE`.

`PRODUCTION_PACKET_CARRIAGE` remains `UNAVAILABLE` in P1. Source availability is not installed/live availability.

---

## 14. Failure semantics

| Boundary | Truthful state |
|---|---|
| malformed/oversize packet before READY | known zero effect |
| carrier/context/party mismatch before READY | known zero effect |
| history/page-budget unavailable before READY | known zero effect, currentness unknown |
| READY then Runtime callback refusal | known zero Slack effect |
| Runtime commit, COMMIT not sent | Runtime fact known; Slack zero effect |
| COMMIT sent, response/reconcile ambiguous | `SEND_EFFECT_UNKNOWN`; same carrier only |
| complete read proves no packet | absent / `CARRIER_UNAVAILABLE` |
| read transport/incomplete/mutated/conflicting | unknown / `CARRIER_RECONCILIATION_REQUIRED` |
| packet mutation without creation evidence | lifecycle and observer reconciliation incomplete |
| duplicate physical packet | conflict; never select one silently |

No branch, host, account, provider or carrier failover is permitted after possible COMMIT.

---

## 15. Exact source envelope

Expected source files:

```text
common/agent_dialogue_consultation_contract.py
integrations/slack_agent_dialogue/engine.py
integrations/slack_agent_dialogue/engine_v2.py
integrations/slack_agent_dialogue/service.py
integrations/slack_agent_dialogue/slack_web_api.py
integrations/slack_agent_dialogue/turn_observer.py
integrations/company_consultation_dispatch.py
```

Expected tests:

```text
tests/test_agent_dialogue_consultation_contract.py
tests/test_slack_agent_dialogue_slack_web_api.py
tests/test_slack_agent_dialogue_engine_v2.py
tests/test_slack_agent_dialogue_service.py
tests/test_slack_agent_dialogue_turn_observer.py
tests/test_company_inbox_iac1.py
```

The two documentation paths are also owned by this operation. No other source path without a new Sol ruling.

`integrations/mastermind_company_mcp/consultation.py`, Company Dialogue binding code, Wake owners and Executive installation scripts are read/assert consumers only in P1.

---

## 16. Collision and custody

Fresh census at freeze found 228 open Mastermind PRs. Only Draft PR #124 listed a planned P1 path. #124 is an ancient-base liquidity branch with 290 commits and 1,239 changed files; it carries `common/agent_dialogue_consultation_contract.py` as an old added blob `f3bff4055c5baf80865f5fa3ac9df7cb7266403f`, while protected P1 source owns current blob `0d51bbb06e71c0fdc0387ba83ab70a2f973e3da2`. #124 is not the consultation owner and is path-stale, but it remains a release-time merge-tree collision to recheck. P1 does not absorb or repair #124.

No pre-existing P1 source branch, worktree or PR existed. Native workspace acquisition created exactly one carrier:

```text
branch: sol/iac1-production-packet-carriage-p1-20260925-sol-001
worktree: /Users/chriswong/.mastermind/agent-workspaces/sol/iac1-production-packet-carriage-p1-20260925-sol-001
base: a29161fa0a44cca9927afe042b5f7ea25aae1736
host: m1studio
```

Baseline selected contract/engine/service/observer/Company Inbox suites passed before the first edit.

---

## 17. Acceptance evidence

P1 source acceptance requires all of the following on one immutable exact head:

1. contract wire RED→GREEN tests, including byte and discriminator falsifiers;
2. assertion-neutral async migration proof;
3. lifecycle/packet same-key and single-flight discriminators;
4. READY/COMMIT post-effect uncertainty tests for the packet operation;
5. mutation and malformed-packet visibility in lifecycle reader and observer;
6. page-budget facts and poison-prevention tests;
7. pre-INTENT and pre-answer packet budget refusals with zero Runtime/Wake effect;
8. guarded read tests proving unknown is not absence and zero-write reads never report `EFFECT_UNKNOWN`;
9. same-parent-thread authority and party-direction negative matrix;
10. full hermetic A→B→A through real AF_UNIX service, dispatcher restart and carrier restart;
11. no-new-plane static architecture test;
12. all incumbent lifecycle/observer/Wake/Company Inbox suites green;
13. current-base merge-tree proof, Source Continuity, hosted CI and independent exact-head review.

A green source head does not authorize enrollment, activation or a live Slack packet.

---

## 18. P2 and human gates

P1 ends at:

```text
BUILT_NOT_PROVEN / SOURCE_ONLY / PRODUCTION_DISARMED
```

P2 is separate:

1. native-TTY Agent Relay enrollment through the existing owner;
2. exact installed token/config/plist readback;
3. separate activation through the existing closed-label `ops/executive_os/service-control.sh` family;
4. separate first live packet-write approval;
5. same-parent-thread live QUESTION/ANSWER proof;
6. later P1-R reachability source acceptance before cross-session live proof.

No P1 code loads a token, writes config, installs a plist, invokes launchctl, starts a service or writes Slack.

---

## 19. Capability ceiling

A successful P1 source release means:

> Mastermind has a reviewed, source-only, production-disarmed adapter that can carry one bounded machine-readable QUESTION and ANSWER between two lawful Worker Attempts that already share one exact Agent Relay parent thread, with restart-safe readback, incumbent single-flight and READY/COMMIT effect safety, and protected #959 Runtime/Wake consumption.

It does not mean:

- Agent Relay is enrolled or running;
- any token or credential is installed;
- any live Slack packet was written;
- peers in different sessions/jobs are reachable;
- packets larger than the proven 4500-byte wire are supported;
- packet mutation cannot block the shared lifecycle observer;
- Company Inbox is installed or browser-proven;
- product acceptance or program completion has occurred.
