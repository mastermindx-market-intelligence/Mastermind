# Worker Presence & Dialogue WP-1 — Agent Relay V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-inert, worker-aware `mastermind.agent_dialogue.v2` contract and normal storeless Agent Relay path that can represent exact Executive worker/Attempt actors, carries immutable operation/watch admission metadata for the sister turn-watcher lane, preserves ASD v1 semantics, and performs zero Wake classification itself.

**Architecture:** Preserve `mastermind.agent_dialogue.v1` and `mastermind.agent_dialogue_parent.v1` byte-for-behavior compatibility. Add sibling V2 message **and parent** contracts in the existing `integrations/slack_agent_dialogue` package, then add a V2 storeless engine and a second control-version dispatcher on the same AF_UNIX service boundary. V2 uses typed `actor_ref`, typed `applies_to`, an immutable `operation_key`, and a closed nullable `watch_mode` (`null | "turn_watch_v1"`). WP-1 validates and fingerprints watch admission but never interprets it into Wake. The sister WP-TW1 lane owns the pure turn classifier/`AgentDialogueAttention` projection in separate files after this contract is accepted; WP-TW2 later owns observer/Wake composition after #174 reconciliation. This wave performs no Slack network installation, credential enrollment, background observer, Wake work, Job creation, Worker routing or production arming.

**Tech Stack:** Python 3.11+, dataclasses, asyncio, existing `integrations.slack_agent_dialogue`, existing AF_UNIX Agent Dialogue service, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md`

**Sister amendment:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-turn-watcher-amendment.md` — higher precedence only for turn-watch/Wake topics. WP-1 supplies its immutable V2 parent/message seam but does not implement the amendment's classifier/observer/Wake behavior.

## Global Constraints

- Protected pickup/source-law basis for planning: `Mastermind@8affa1c0403f4400825371bea0257f360a4814f2`; implementation MUST re-pin protected `master`, the merged WP-0 source-law carrier, and relevant open sister carriers before the first code write and again before push.
- Existing `mastermind.agent_dialogue.v1` and `mastermind.agent_dialogue_parent.v1` remain accepted and behaviorally compatible. Historical V1 threads remain ordinary ASD threads and are never retroactively watcher-enabled.
- Executive OS remains sole Job/Attempt/Worker/Event lifecycle authority; Slack/ASD never creates, claims, retries or terminalizes work.
- Agent OS remains organizational memory; this wave creates no runtime identity store.
- Use the existing `SlackDialogueClient`, `SlackMessage`, `HistoryPage`, `SlackEffectUnknown`, bounded history and effect-unknown semantics. Do not create a second Slack transport stack.
- One Agent Relay service boundary. No second daemon, socket-owned lifecycle, inbox DB, cursor DB, replay ledger or queue.
- Presentation is derived from trusted structured actor identity and always uses the reserved `Mastermind ·` prefix. It must never impersonate Chairman/human/personal ChatGPT/Claude principals.
- V2 parent `watch_mode` is required and closed to `null | "turn_watch_v1"`; it grants no authority. WP-1 validates/fingerprints it only.
- V2 parent carries one immutable `operation_key`; model-authored message bodies cannot choose or alter it.
- No `chat:write.customize` use, Slack app scope change, Slack API credential, production socket installation, live message, background polling or Wake source creation in WP-1.
- **Sister-session collision fence:**
  - Wake PR #174 owns provider-native Wake transport; no `control_plane/wake_*`, Wake transport/session-target implementation/docs/tests.
  - WP-TW1 reserves `integrations/slack_agent_dialogue/turn_watcher.py` and `tests/test_slack_agent_dialogue_turn_watcher.py`; WP-1 must not create or edit them.
  - WP-TW2 owns any Agent Relay background observer/polling loop, active-waiter suppression registry and Relay→Wake adapter; WP-1 service changes are request/response dispatch only.
  - ASD-A2 owns production Relay app installation/credentials/service arming.
  - No C1/B2/C2, CF2/HF1/PF1/MH1, or Session Truth #170 changes.
- If current code or a sister carrier moves onto an expected WP-1 changed path after pickup, STOP and return to Sol; do not reset/rebase/overwrite concurrent work.

---

## File Structure

- Create `integrations/slack_agent_dialogue/contract_v2.py` — closed V2 parent/message schemas, typed actor/applicability validation, immutable operation/watch metadata, semantic fingerprints, rendering/parsing and deterministic presentation label.
- Create `integrations/slack_agent_dialogue/engine_v2.py` — normal storeless V2 thread binding/history/send/wait engine using the existing injected Slack client. It does not classify turns or emit Wake attention.
- Modify `integrations/slack_agent_dialogue/service.py` — preserve V1 control path exactly and add optional V2 engine plus `mastermind.agent_dialogue_control.v2` request dispatch on the same AF_UNIX service. No background loop.
- Create `tests/test_slack_agent_dialogue_contract_v2.py` — closed parent/message schema, actor/applicability, operation/watch, spoofing, fingerprint, v1-compatibility and presentation falsifiers.
- Create `tests/test_slack_agent_dialogue_engine_v2.py` — storeless V2 parent binding/history/send/effect-unknown and actor-context falsifiers.
- Modify `tests/test_slack_agent_dialogue_service.py` — V1 regression plus V2 control-version/operation/peer/bounds tests.
- Do not modify `integrations/slack_agent_dialogue/contract.py` unless an unavoidable shared-helper extraction is proven necessary; prefer imports/reuse so V1 semantics cannot drift accidentally.
- Do not create `turn_watcher.py`, watcher tests, Wake adapters, polling code or persistence.

---

### Task 1: Freeze V2 parent/message contracts and identity joins

**Files:**
- Create: `integrations/slack_agent_dialogue/contract_v2.py`
- Create: `tests/test_slack_agent_dialogue_contract_v2.py`
- Read-only reference: `integrations/slack_agent_dialogue/contract.py`

**Interfaces:**
- Produces constants:
  - `MESSAGE_SCHEMA_V2 = "mastermind.agent_dialogue.v2"`
  - `MESSAGE_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_V2"`
  - `PARENT_SCHEMA_V2 = "mastermind.agent_dialogue_parent.v2"`
  - `PARENT_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_PARENT_V2"`
  - `TURN_WATCH_MODE_V1 = "turn_watch_v1"`
- Produces functions:
  - `validate_actor_ref(value: Any) -> dict[str, Any]`
  - `validate_applies_to_v2(value: Any) -> dict[str, Any]`
  - `validate_parent_v2(value: Any) -> dict[str, Any]`
  - `build_parent_v2(value: Mapping[str, Any]) -> dict[str, Any]`
  - `render_parent_v2(value: Mapping[str, Any]) -> str`
  - `parse_parent_frame_v2(text: str) -> dict[str, Any]`
  - `validate_message_v2(value: Any) -> dict[str, Any]`
  - `build_message_v2(value: Mapping[str, Any]) -> dict[str, Any]`
  - `render_message_v2(value: Mapping[str, Any]) -> str`
  - `parse_message_frame_v2(text: str) -> dict[str, Any]`
  - `presentation_label(actor_ref: Mapping[str, Any]) -> str`
- Reuses V1 commission/body/evidence laws where behavior is exactly shared; do not fork those laws unnecessarily.

- [ ] **Step 1: Write RED tests for the exact V2 parent shape**

V2 parent keys are exactly:

```text
schema
work_ref
commission_ref
session_ref
operation_key
watch_mode
allowed_sol_user_ids
created_at
fingerprint
```

Positive vector:

```python
{
    "schema": PARENT_SCHEMA_V2,
    "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
    "commission_ref": commission(),
    "session_ref": "asd-session-fable0001",
    "operation_key": "worker-presence-dialogue-canary-20260827-001",
    "watch_mode": None,
    "allowed_sol_user_ids": ["U0BRETDUAS2", "U0BSB73JWNL"],
    "created_at": "2026-08-27T13:00:00Z",
}
```

A second positive vector uses `watch_mode="turn_watch_v1"`.

Use a closed operation-key validator with exactly:

```python
r"\A[a-z0-9][a-z0-9._-]{7,127}\Z"
```

unless current protected source already exposes an accepted stricter reusable validator; if so reuse that validator and add parity vectors. Reject whitespace, uppercase, secrets, extra keys, empty/malformed operation keys and any watch mode other than `None` or exact `turn_watch_v1`.

Pin that `watch_mode` and `operation_key` are included in semantic fingerprint identity: changing either changes the parent fingerprint. V1 parent parsing remains unchanged and has no watcher semantics.

- [ ] **Step 2: Write RED tests for exact actor shapes**

Positive actors:

```python
EXECUTIVE_CODEX = {
    "kind": "executive_surface",
    "seat": "ceo",
    "reasoning_surface": "codex",
}
```

and a worker actor populated from one real current Executive Runtime test fixture:

```python
{
    "kind": "worker_attempt",
    "job_id": job.job_id,
    "attempt_id": attempt.attempt_id,
    "worker_id": worker.worker_id,
}
```

Do not invent a competing Executive ID namespace. Use identifiers emitted by existing Runtime test constructors as positive truth. The V2 validator may enforce bounded non-empty/control-free strings, while exact worker↔Attempt authority is established by the trusted applicability join.

Negative vectors reject unknown actor kind, extra actor key, missing fields, seat outside `chairman|ceo|coo`, secret-shaped leaves, and provider account/Slack user/host/native-thread fields smuggled into actor identity.

- [ ] **Step 3: Write RED tests for typed applicability**

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

For `worker_attempt`, actor and `executive_attempt` applicability triples must match exactly. Mutate one ID and require `MESSAGE_INVALID`.

An executive-surface actor may speak against either applicability kind but does not gain Job authority from doing so.

- [ ] **Step 4: Write RED tests for direction/authority separation**

Pin:

```text
worker_attempt -> ACK/DECISION_REQUEST/BLOCKED/PROGRESS/RESULT only
executive_surface(coo) -> contributor message families only
executive_surface(ceo) -> contributor families and SOL reply families
executive_surface(chairman) -> SOL reply families only
reasoning_surface/provider/model never changes seat or effective authority
```

Actual RULING authority remains under existing injected `TrustedAuthorityPolicy`; actor type is necessary eligibility, never sufficient authority.

- [ ] **Step 5: Write RED tests for V2 message schema/fingerprint**

V2 message keys are exactly:

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

`created_at` and `fingerprint` remain excluded from semantic identity exactly as V1. Extra keys, duplicate JSON keys, noncanonical rendering, oversized frames and secret-shaped leaves refuse.

- [ ] **Step 6: Implement the minimum V2 contract**

Reuse V1 functions by import where semantics remain exact, such as commission/body/evidence validation. If a required helper is private, copy only the minimal pure helper and add a parity test; do not refactor V1 merely for aesthetics.

WP-1 must not import Wake modules or implement `AgentDialogueAttention`/turn classification.

- [ ] **Step 7: Add deterministic presentation derivation**

Pin outputs such as:

```python
presentation_label({"kind": "executive_surface", "seat": "ceo", "reasoning_surface": "codex"})
# "Mastermind · Sol/Codex"

presentation_label({"kind": "executive_surface", "seat": "coo", "reasoning_surface": "claude"})
# "Mastermind · Fable"
```

Worker label begins `Mastermind · Worker ` and contains only a bounded safe suffix derived from canonical `worker_id`. Unknown reasoning surfaces remain visibly generic; never fall back to a human/person account name. No caller-provided display string exists.

- [ ] **Step 8: Prove V1 is unchanged**

```bash
python -m pytest tests/test_slack_agent_dialogue_contract.py tests/test_slack_agent_dialogue_contract_v2.py -q
```

Expected: all existing V1 tests remain green; V2 parent/message tests green.

- [ ] **Step 9: Commit**

```bash
git add integrations/slack_agent_dialogue/contract_v2.py tests/test_slack_agent_dialogue_contract_v2.py
git commit -m "feat(asd): add immutable worker dialogue v2 contract"
```

---

### Task 2: Add the normal storeless V2 dialogue engine without watcher behavior

**Files:**
- Create: `integrations/slack_agent_dialogue/engine_v2.py`
- Create: `tests/test_slack_agent_dialogue_engine_v2.py`
- Read-only/reuse: `integrations/slack_agent_dialogue/engine.py`

**Interfaces:**
- Reuse `SlackDialogueClient`, `SlackMessage`, `HistoryPage`, `SlackEffectUnknown`, `SlackTransportUnavailable` from V1 engine.
- Produce `DialogueContextV2` with `work_ref`, `commission_ref`, `session_ref`, `operation_key`, `watch_mode`, `actor_ref`, `applies_to`.
- Produce `DialogueEngineV2.bind_or_verify_thread`, `.send_message`, `.read_thread`, `.wait_for_reply`, `.status` with V1-equivalent bounded/effect semantics.
- Consume only `PARENT_SCHEMA_V2`/V2 parent for V2 binding.

- [ ] **Step 1: Write RED V2 thread-binding tests**

V2 must bind against exactly one V2 parent whose work/commission/session/operation/watch metadata matches context. Historical V1 parents do not satisfy a V2 binding and cannot become watcher-enabled by inference.

Tests prove:

```text
exactly one matching V2 parent -> bound
0 or >1 matching V2 parents -> THREAD_BINDING_AMBIGUOUS
changed work/commission/session/operation_key/watch_mode -> THREAD_CONTEXT_MISMATCH
parent edit/delete without creation evidence -> reconciliation refusal
Slack member/display name never supplies actor_ref
```

- [ ] **Step 2: Write RED V2 history tests**

The engine reads only `MMX/AGENT_DIALOGUE_V2` replies for V2 operations. V1 frames in the same thread cannot satisfy a V2 request. V2 messages claiming the bound protocol but wrong work/commission/session/applicability must fail closed rather than silently disappear.

The engine preserves `watch_mode` in context but performs no `WAKE_CEO`, `WAKE_COO`, attention-source or observer behavior.

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

Do not subclass V1 if that obscures protocol selection. A narrow copied orchestration skeleton is acceptable while importing shared transport dataclasses/exceptions; every copied invariant receives parity coverage. There is no persistence, background loop, watcher classifier or new Slack client.

- [ ] **Step 5: Add status output that cannot imply watcher/production readiness**

`DialogueEngineV2.status()` may expose schema/config metadata but must not claim Slack app installation, Worker execution, Wake readiness, watcher readiness, or production arming. Include `production_armed: false`/equivalent truthful status if compatible with existing status conventions.

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
git commit -m "feat(asd): add normal storeless worker dialogue v2 engine"
```

---

### Task 3: Extend the one existing AF_UNIX service with versioned V2 request dispatch only

**Files:**
- Modify: `integrations/slack_agent_dialogue/service.py`
- Modify: `tests/test_slack_agent_dialogue_service.py`

**Interfaces:**
- Preserve `CONTROL_VERSION = "mastermind.agent_dialogue_control.v1"` as compatibility alias.
- Add `CONTROL_VERSION_V2 = "mastermind.agent_dialogue_control.v2"`.
- Change constructor compatibly to `AgentDialogueService(config, engine, *, engine_v2=None)`.
- V2 operations remain `status`, `bind_or_verify_thread`, `send_message`, `read_thread`, `wait_for_reply`, using V2 context/message validation.
- No watcher/attention/Wake/background-observer operation is added.

- [ ] **Step 1: Write RED V1 compatibility tests**

Instantiate exactly as current callers do with only V1 engine. Every V1 request behaves identically. A V2 request with `engine_v2=None` returns the existing fixed `REQUEST_INVALID`; do not widen error vocabulary unnecessarily.

- [ ] **Step 2: Write RED V2 operation tests**

Use a fake V2 engine and send exact closed requests with `version="mastermind.agent_dialogue_control.v2"`. Pin exact args/response bounds. V2 adds no operation that creates Jobs/Workers, channels/threads, credentials, Wake obligations, attention facts or arbitrary Slack posts.

- [ ] **Step 3: Refactor dispatch into explicit version branches**

Use conceptually:

```python
if version == CONTROL_VERSION:
    return await self._dispatch_v1(operation, args)
if version == CONTROL_VERSION_V2 and self.engine_v2 is not None:
    return await self._dispatch_v2(operation, args)
raise DialogueServiceError("REQUEST_INVALID")
```

Move existing V1 operation body mechanically into `_dispatch_v1` with no semantic edits. Add strict `_context_v2` parsing.

Do **not** add service start-up polling, eligible-thread caches, waiter registration changes or Wake calls. Those are WP-TW2-owned future changes after source-law/dependency gates.

- [ ] **Step 4: Re-run peer/size/malformed-JSON tests for V2**

Existing AF_UNIX peer-UID, path ownership, request/response bounds and strict JSON logic apply before version dispatch, so V2 cannot weaken them.

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

### Task 4: Adversarial no-rebuild, watcher-boundary and no-authority-laundering acceptance

**Files:**
- Modify: `tests/test_slack_agent_dialogue_contract_v2.py`
- Modify: `tests/test_slack_agent_dialogue_engine_v2.py`
- Modify: `tests/test_slack_agent_dialogue_service.py`

**Interfaces:** all previous tasks.

- [ ] **Step 1: Add a mutation/falsifier matrix**

Construct tests that fail when each forbidden mutation is applied:

```text
accept actor_ref from body/prose
accept worker_id that disagrees with applies_to
allow worker_attempt to emit RULING/CONTINUE/STOP
allow reasoning_surface/model name to widen seat/authority
allow caller-supplied presentation label
allow changed operation_key/watch_mode to bind same V2 parent
allow unknown watch_mode
infer watch_mode for historical V1 parent
let V1 frame satisfy V2 request
turn edited/deleted message into current truth without creation evidence
blind resend after SlackEffectUnknown
persist a cursor/inbox/replay row
create a second Slack client/transport implementation
emit AgentDialogueAttention/Wake from WP-1
add service background polling/watcher loop
```

Use narrow AST/source scans over new V2 files: no `sqlite3`, DB path, queue/scheduler/cron imports, Slack SDK import, Wake module import, or direct network-client creation. The only Slack I/O seam is injected existing `SlackDialogueClient`.

- [ ] **Step 2: Prove source/path collision fences**

Immediately before push:

```bash
git diff --name-only <CURRENT_PROTECTED_MASTER>...HEAD
```

Expected WP-1 implementation paths only:

```text
integrations/slack_agent_dialogue/contract_v2.py
integrations/slack_agent_dialogue/engine_v2.py
integrations/slack_agent_dialogue/service.py
tests/test_slack_agent_dialogue_contract_v2.py
tests/test_slack_agent_dialogue_engine_v2.py
tests/test_slack_agent_dialogue_service.py
```

Explicitly absent:

```text
integrations/slack_agent_dialogue/turn_watcher.py
tests/test_slack_agent_dialogue_turn_watcher.py
control_plane/wake_*
Slack production install/config
Executive placement/provider paths
Agent OS paths
```

If a sister branch/PR now owns `service.py`, STOP and reconcile rather than stack both carriers. In that case WP-1 may be narrowed to contract+engine only by a fresh Sol ruling; the worker cannot self-narrow source law.

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

Then require current exact-head hosted CI/CodeQL under branch protection.

- [ ] **Step 4: Independent adversarial review**

Reviewer attacks:

```text
Slack name becomes Worker identity
worker forges another Attempt
V2 changes V1 meaning
V1 thread becomes retroactively watcher-enabled
operation_key/watch_mode omitted from immutable parent identity
WP-1 secretly originates work or Wake
WP-1 creates persistence/retry plane
WP-1 weakens effect-unknown reconciliation
WP-1 takes WP-TW1 turn_watcher paths
WP-1 adds WP-TW2 background observer/polling
WP-1 collides with Wake #174 or ASD-A2 production ownership
presentation impersonates a human
```

- [ ] **Step 5: Return to Sol**

Return exact head SHA, changed-file census, focused + hosted CI/CodeQL, falsifier results, reviewer verdict and explicit statements:

```text
WP-1 is production-inert.
ASD v1 remains compatible.
V2 parent fingerprints operation_key + watch_mode.
Historical V1 parents are not watcher-enabled.
WP-1 performs zero turn classification, AgentDialogueAttention or Wake.
No Slack app/token/scope was created or changed.
No Job/Attempt/Worker/Wake lifecycle was created or mutated.
No production Slack message was sent.
WP-TW1 remains the separate pure classifier lane.
WP-TW2 remains later and gated by #174/Agent Relay production law.
WP-2 remains a separate MCP carrier.
WP-3 remains gated by accepted Agent Relay production proof.
```

## Stop Condition

WP-1 stops when V2 parent/message identity, applicability, presentation and normal storeless service semantics are mechanically implemented with exact V1 compatibility and exact-head review evidence. It deliberately includes immutable watcher **admission metadata** but no watcher behavior. It does **not** install/arm the production Agent Relay app, add MCP tooling, bind a real Codex/Worker session, send a live Slack message, classify a turn, create `AgentDialogueAttention`, implement Wake/observer polling, or advance CF2/HF1/PF1/MH1.
