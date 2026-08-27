# Worker Presence & Dialogue WP-1 — Agent Relay V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-inert, worker-aware `mastermind.agent_dialogue.v2` contract and storeless Agent Relay path that can represent exact Executive worker/Attempt actors without changing ASD v1 semantics or making Slack a lifecycle authority.

**Architecture:** Preserve `mastermind.agent_dialogue.v1` byte-for-behavior compatibility. Add a sibling V2 contract in the existing `integrations/slack_agent_dialogue` package, then extend the existing storeless engine/service with an optional V2 engine and a second control-version dispatcher on the same service boundary. V2 uses typed `actor_ref` plus typed `applies_to`, mechanically enforces worker↔Attempt identity agreement, derives a reserved Mastermind presentation label from trusted structured identity, and preserves current history/edit/delete/effect-unknown laws. This wave performs no Slack network installation, credential enrollment, service arming, Wake work, Job creation or Worker routing.

**Tech Stack:** Python 3.11+, dataclasses, asyncio, existing `integrations.slack_agent_dialogue`, existing AF_UNIX Agent Dialogue service, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md`

## Global Constraints

- Protected pickup/source-law basis for planning: `Mastermind@8affa1c0403f4400825371bea0257f360a4814f2`; implementation MUST re-pin protected `master` and this merged plan/spec before the first code write and again before push.
- Existing `mastermind.agent_dialogue.v1` and `mastermind.agent_dialogue_parent.v1` remain accepted and behaviorally compatible.
- Executive OS remains sole Job/Attempt/Worker/Event lifecycle authority; Slack/ASD never creates, claims, retries or terminalizes work.
- Agent OS remains organizational memory; this wave creates no runtime identity store.
- Use the existing `SlackDialogueClient`, `SlackMessage`, `HistoryPage`, `SlackEffectUnknown`, bounded history and effect-unknown semantics. Do not create a second Slack transport stack.
- One Agent Relay service boundary. No second daemon, socket-owned lifecycle, inbox DB, cursor DB, replay ledger or queue.
- Presentation is derived from trusted structured actor identity and always uses the reserved `Mastermind ·` prefix. It must never impersonate Chairman/human/personal ChatGPT/Claude principals.
- No `chat:write.customize` use, Slack app scope change, Slack API credential, production socket installation or live message in WP-1.
- **Sister-session collision fence:** do not modify Wake PR #174 paths (`control_plane/wake_*`, Wake transport/session-target implementation/docs/tests), ASD-A2 production installation/credential scripts/configuration, C1/B2/C2, CF2/HF1/PF1/MH1, or Session Truth #170.
- If current code moved onto any expected changed path after pickup, STOP and return to Sol; do not rebase over an active carrier.

---

## File Structure

- Create `integrations/slack_agent_dialogue/contract_v2.py` — closed V2 schema, typed actor/applicability validation, semantic fingerprints, rendering/parsing, trusted composition helper and deterministic presentation label.
- Create `integrations/slack_agent_dialogue/engine_v2.py` — storeless V2 history/send/wait engine using the existing injected Slack client and existing transport/effect semantics.
- Modify `integrations/slack_agent_dialogue/service.py` — preserve V1 control path exactly and add an optional V2 engine plus `mastermind.agent_dialogue_control.v2` dispatch on the same AF_UNIX service.
- Create `tests/test_slack_agent_dialogue_contract_v2.py` — closed-schema, actor/applicability, spoofing, fingerprint, v1-compatibility and presentation falsifiers.
- Create `tests/test_slack_agent_dialogue_engine_v2.py` — storeless thread binding/history/send/effect-unknown and actor-context falsifiers.
- Modify `tests/test_slack_agent_dialogue_service.py` — V1 regression plus V2 control-version/operation/peer/bounds tests.
- Do not modify `integrations/slack_agent_dialogue/contract.py` unless an unavoidable shared helper extraction is proven necessary; prefer imports/reuse so V1 semantics cannot drift accidentally.

---

### Task 1: Freeze the V2 closed contract and identity joins

**Files:**
- Create: `integrations/slack_agent_dialogue/contract_v2.py`
- Create: `tests/test_slack_agent_dialogue_contract_v2.py`
- Read-only reference: `integrations/slack_agent_dialogue/contract.py`

**Interfaces:**
- Produces constants:
  - `MESSAGE_SCHEMA_V2 = "mastermind.agent_dialogue.v2"`
  - `MESSAGE_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_V2"`
- Produces functions:
  - `validate_actor_ref(value: Any) -> dict[str, Any]`
  - `validate_applies_to_v2(value: Any) -> dict[str, Any]`
  - `validate_message_v2(value: Any) -> dict[str, Any]`
  - `build_message_v2(value: Mapping[str, Any]) -> dict[str, Any]`
  - `render_message_v2(value: Mapping[str, Any]) -> str`
  - `parse_message_frame_v2(text: str) -> dict[str, Any]`
  - `presentation_label(actor_ref: Mapping[str, Any]) -> str`
- Reuses V1 `validate_commission_ref`, `validate_evidence_ref`/body laws where behavior is exactly shared; do not copy and fork those laws unless import structure makes reuse impossible.

- [ ] **Step 1: Write RED tests for exact actor shapes**

Add tests that accept only these closed forms:

```python
EXECUTIVE_CODEX = {
    "kind": "executive_surface",
    "seat": "ceo",
    "reasoning_surface": "codex",
}
WORKER = {
    "kind": "worker_attempt",
    "job_id": "job-01J00000000000000000000000",
    "attempt_id": "attempt-01J00000000000000000000000",
    "worker_id": "worker-01J00000000000000000000000",
}
```

Do not hard-code the example ID regex until current `executive_runtime` ID generation is inspected. The test must construct one real Job/Attempt/Worker fixture through existing test helpers and use the emitted identifiers as the positive vectors. The contract validator should reuse the existing accepted ID character/length behavior mechanically or validate bounded non-empty identifiers and rely on the worker↔Attempt trusted join; it must not create a competing Executive ID namespace.

Negative vectors must reject:

```text
unknown actor kind
extra actor key
worker_attempt missing job/attempt/worker
executive_surface missing seat/reasoning_surface
seat outside chairman|ceo|coo
secret-shaped leaf
provider account / Slack user / host / native thread injected as extra key
```

- [ ] **Step 2: Write RED tests for typed applicability**

Accept exactly:

```python
{
    "kind": "repository",
    "repository": "mastermindx-market-intelligence/Mastermind",
    "head_sha": "a" * 40,
    "pr": "mastermindx-market-intelligence/Mastermind#177",
}
```

or one real Executive fixture:

```python
{
    "kind": "executive_attempt",
    "job_id": job.job_id,
    "attempt_id": attempt.attempt_id,
    "worker_id": worker.worker_id,
}
```

Pin the load-bearing join:

```python
assert validate_message_v2(worker_message)["actor_ref"] == WORKER
# mutate applies_to.attempt_id or worker_id => MESSAGE_INVALID
```

A `worker_attempt` actor MUST exactly equal the `executive_attempt` applicability triple. An executive-surface actor may speak against either applicability kind but does not gain Job authority from doing so.

- [ ] **Step 3: Write RED tests for direction/authority separation**

Pin these laws:

```text
worker_attempt -> ACK/DECISION_REQUEST/BLOCKED/PROGRESS/RESULT only
executive_surface(coo) -> contributor message families only
executive_surface(ceo) -> contributor families and SOL reply families
executive_surface(chairman) -> SOL reply families only
provider/model/reasoning_surface never changes message authority class
```

Keep actual RULING authority classification under the existing injected `TrustedAuthorityPolicy`; actor validation is eligibility, not sufficient authority.

- [ ] **Step 4: Write RED tests for V2 message keys and semantic fingerprint**

The V2 closed keys are exactly:

```text
schema
message_key
message_type
work_ref
commission_ref
session_ref
actor_ref
reply_to_message_key
applies_to
summary
body
evidence_refs
requires_response
created_at
fingerprint
```

`created_at` and `fingerprint` remain excluded from semantic identity exactly as V1. Extra keys, duplicate JSON keys, noncanonical rendering, oversized frames and secret-shaped leaves must refuse.

- [ ] **Step 5: Implement the minimum V2 contract**

Implement a sibling module. Reuse these V1 functions by import where their semantics remain exact:

```python
from integrations.slack_agent_dialogue.contract import (
    DialogueContractError,
    validate_commission_ref,
    validate_body,
    validate_evidence_ref,
)
```

If one required helper is private in V1, copy only the minimal pure validation helper into V2 and add an explicit parity test; do not refactor V1 in this task merely for aesthetics.

- [ ] **Step 6: Add deterministic presentation derivation**

Pin outputs such as:

```python
presentation_label({"kind": "executive_surface", "seat": "ceo", "reasoning_surface": "codex"})
# "Mastermind · Sol/Codex"

presentation_label({"kind": "executive_surface", "seat": "coo", "reasoning_surface": "claude"})
# "Mastermind · Fable"

presentation_label(worker_actor)
# starts with "Mastermind · Worker " and contains only a bounded suffix of canonical worker_id
```

Unknown reasoning surfaces remain visibly generic, e.g. `Mastermind · CEO/<surface>` or `Mastermind · COO/<surface>`; never fall back to a human name. No caller-provided display string exists.

- [ ] **Step 7: Prove V1 is unchanged**

Run:

```bash
python -m pytest tests/test_slack_agent_dialogue_contract.py tests/test_slack_agent_dialogue_contract_v2.py -q
```

Expected: all existing V1 tests remain green; V2 tests green.

- [ ] **Step 8: Commit**

```bash
git add integrations/slack_agent_dialogue/contract_v2.py tests/test_slack_agent_dialogue_contract_v2.py
git commit -m "feat(asd): add closed worker-aware dialogue v2 contract"
```

---

### Task 2: Add the storeless V2 dialogue engine without a second transport

**Files:**
- Create: `integrations/slack_agent_dialogue/engine_v2.py`
- Create: `tests/test_slack_agent_dialogue_engine_v2.py`
- Read-only/reuse: `integrations/slack_agent_dialogue/engine.py`

**Interfaces:**
- Reuse `SlackDialogueClient`, `SlackMessage`, `HistoryPage`, `SlackEffectUnknown`, `SlackTransportUnavailable` from V1 engine.
- Produce `DialogueContextV2` with `work_ref`, `commission_ref`, `session_ref`, `actor_ref`, `applies_to`.
- Produce `DialogueEngineV2.bind_or_verify_thread`, `.send_message`, `.read_thread`, `.wait_for_reply`, `.status` with V1-equivalent bounded/effect semantics.

- [ ] **Step 1: Write RED thread-binding tests**

Reuse the current V1 top-level parent frame as immutable work/commission/session thread identity. V2 does **not** reinterpret historical parent messages as Worker identity. The trusted V2 context supplies actor/applicability separately.

Tests must prove:

```text
exactly one eligible parent -> bound
0 or >1 matching parents -> THREAD_BINDING_AMBIGUOUS
changed work/commission/session -> THREAD_CONTEXT_MISMATCH
parent edit/delete without creation evidence -> reconciliation refusal
Slack member/display name never supplies actor_ref
```

- [ ] **Step 2: Write RED V2 history tests**

The engine reads only `MMX/AGENT_DIALOGUE_V2` replies for V2 operations. V1 frames in the same thread remain historical/other-protocol evidence and cannot satisfy a V2 request. V2 messages with wrong work/commission/session/applicability must fail closed rather than be silently skipped when they claim the bound protocol/context.

- [ ] **Step 3: Write RED send/effect-unknown tests**

Use the existing injected fake Slack client. Pin:

```text
same message_key + same fingerprint already in history -> duplicate receipt, no second post
same message_key + changed fingerprint -> MESSAGE_KEY_CONFLICT
post success -> bounded MessageReceipt
SlackEffectUnknown -> reconcile same thread/key before deciding duplicate/success; never blind resend
transport unavailable before effect -> TRANSPORT_UNAVAILABLE
```

- [ ] **Step 4: Implement `engine_v2.py` by narrow adaptation**

Do not subclass V1 if that obscures protocol selection. It is acceptable to copy the small storeless orchestration skeleton while importing shared transport dataclasses/exceptions, but every copied invariant must have a parity test. There must be no persistence, background loop or new Slack client.

Use V2 `parse_message_frame_v2`, `render_message_v2`, `validate_message_v2` for V2 frames only.

- [ ] **Step 5: Add status output that cannot imply production readiness**

`DialogueEngineV2.status()` may expose bounded configuration/contract metadata but must not claim Slack app installation, Worker execution, Wake readiness, or production arming. Include schema version and `production_armed: false` if current status shape supports it.

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_engine.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add integrations/slack_agent_dialogue/engine_v2.py tests/test_slack_agent_dialogue_engine_v2.py
git commit -m "feat(asd): add storeless worker dialogue v2 engine"
```

---

### Task 3: Extend the one existing AF_UNIX service with a versioned V2 dispatcher

**Files:**
- Modify: `integrations/slack_agent_dialogue/service.py`
- Modify: `tests/test_slack_agent_dialogue_service.py`

**Interfaces:**
- Preserve `CONTROL_VERSION = "mastermind.agent_dialogue_control.v1"` as a compatibility alias.
- Add `CONTROL_VERSION_V2 = "mastermind.agent_dialogue_control.v2"`.
- Change constructor compatibly to `AgentDialogueService(config, engine, *, engine_v2=None)`.
- V2 operations: `status`, `bind_or_verify_thread`, `send_message`, `read_thread`, `wait_for_reply`, using V2 context/message validation.

- [ ] **Step 1: Write RED V1 compatibility tests**

Instantiate the service exactly as current tests do with only the V1 engine. Every existing V1 request must behave identically. A V2 request against a service with `engine_v2=None` must return `REQUEST_INVALID` or a new fixed `PROTOCOL_UNAVAILABLE` error only if that error is added to the closed error set and tested; prefer `REQUEST_INVALID` to avoid widening error vocabulary unnecessarily.

- [ ] **Step 2: Write RED V2 operation tests**

Use a fake V2 engine and send:

```python
{
  "version": "mastermind.agent_dialogue_control.v2",
  "operation": "send_message",
  "args": {"context": ..., "thread_ts": ..., "message": ...},
}
```

Pin exact closed args and response bounding. V2 must not add an operation that creates Jobs, Workers, threads/channels, credentials, Wake obligations or arbitrary Slack posts.

- [ ] **Step 3: Refactor `_dispatch` into explicit version branches**

Use:

```python
if version == CONTROL_VERSION:
    return await self._dispatch_v1(operation, args)
if version == CONTROL_VERSION_V2 and self.engine_v2 is not None:
    return await self._dispatch_v2(operation, args)
raise DialogueServiceError("REQUEST_INVALID")
```

Move existing V1 operation body mechanically into `_dispatch_v1` with no semantic edits. Add `_context_v2` as a separate strict parser using `DialogueContextV2`.

- [ ] **Step 4: Re-run peer, size and malformed JSON tests for V2**

The existing AF_UNIX peer-UID, path ownership, request/response bounds and strict JSON logic must apply before version dispatch, so V2 cannot weaken them.

- [ ] **Step 5: Run service and full ASD suite**

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_contract.py \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_engine.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_service.py \
  -q
```

- [ ] **Step 6: Commit**

```bash
git add integrations/slack_agent_dialogue/service.py tests/test_slack_agent_dialogue_service.py
git commit -m "feat(asd): serve v1 and worker dialogue v2 on one relay boundary"
```

---

### Task 4: Adversarial no-rebuild and no-authority-laundering acceptance

**Files:**
- Modify: `tests/test_slack_agent_dialogue_contract_v2.py`
- Modify: `tests/test_slack_agent_dialogue_engine_v2.py`
- Modify: `tests/test_slack_agent_dialogue_service.py`
- Add docs only if current repository convention requires a short V2 contract note; do not modify production ASD-A2 runbooks.

**Interfaces:** all previous tasks.

- [ ] **Step 1: Add a mutation/falsifier matrix**

Construct tests that fail when each forbidden mutation is applied:

```text
accept actor_ref from body/prose
accept worker_id that disagrees with applies_to
allow worker_attempt to emit RULING/CONTINUE/STOP
allow reasoning_surface/model name to widen seat/authority
allow caller-supplied presentation label
let V1 frame satisfy V2 request
turn edited/deleted message into current truth without creation evidence
blind resend after SlackEffectUnknown
persist a cursor/inbox/replay row
create a second Slack client/transport implementation
```

For the persistence/transport fences, use AST/source scans narrowly over new V2 files: no `sqlite3`, DB path, queue/scheduler/cron imports, Slack SDK import, or direct network client creation. The only Slack I/O seam is injected `SlackDialogueClient` from existing engine law.

- [ ] **Step 2: Prove source/path collision fences**

Before push:

```bash
git diff --name-only <CURRENT_PROTECTED_MASTER>...HEAD
```

Expected changed implementation paths are limited to:

```text
integrations/slack_agent_dialogue/contract_v2.py
integrations/slack_agent_dialogue/engine_v2.py
integrations/slack_agent_dialogue/service.py
tests/test_slack_agent_dialogue_contract_v2.py
tests/test_slack_agent_dialogue_engine_v2.py
tests/test_slack_agent_dialogue_service.py
```

No `control_plane/wake_*`, Slack production install/config, `control_plane/executive_*` placement, or Agent OS path may be present.

- [ ] **Step 3: Run repository safety gates**

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_contract.py \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_engine.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_service.py \
  -q
python -m compileall -q integrations/slack_agent_dialogue
git diff --check
```

Then run the repository's current hosted CI/CodeQL required by branch protection on the exact head.

- [ ] **Step 4: Independent adversarial review**

Reviewer attacks:

```text
Slack name becomes Worker identity
worker can forge another Attempt
V2 changes V1 meaning
V2 secretly originates work
V2 creates a persistence/retry plane
V2 weakens effect-unknown reconciliation
V2 collides with Wake #174 or ASD-A2 production ownership
custom presentation impersonates a human
```

- [ ] **Step 5: Return to Sol**

Return exact head SHA, changed-file census, focused + hosted CI/CodeQL, falsifier results, reviewer verdict and explicit statements:

```text
WP-1 is production-inert.
ASD v1 remains compatible.
No Slack app/token/scope was created or changed.
No Job/Attempt/Worker/Wake lifecycle was created or mutated.
No production Slack message was sent.
WP-2 remains a separate carrier.
WP-3 remains gated by accepted Agent Relay production proof.
```

## Stop Condition

WP-1 stops when V2 identity/applicability/presentation semantics are mechanically implemented and served through the existing storeless Agent Dialogue service with exact V1 compatibility and exact-head review evidence. It does **not** install/arm the production Agent Relay app, add MCP tooling, bind a real Codex/Worker session, send a live Slack message, implement Wake, or advance CF2/HF1/PF1/MH1.
