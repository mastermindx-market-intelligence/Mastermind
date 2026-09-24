# Worker Presence & Dialogue WP-TW1 — Stateless Turn Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement one pure, deterministic, zero-network, zero-persistence classifier that converts an explicitly watcher-enabled, fully validated Agent Dialogue V2 thread into either no action, a bounded CEO/COO turn-attention fact, terminal state, or a typed refusal—without creating Wake obligations, routing sessions, calling providers, or introducing a watcher control plane.

**Architecture:** WP-TW1 is a consumer of the accepted WP-1 V2 contract, not a competing dialogue schema. It lives in one new `integrations/slack_agent_dialogue/turn_watcher.py` module and one focused test file. The classifier consumes already-validated V2 parent/message objects plus trusted, caller-injected routing-correlation facts; it never parses arbitrary Slack prose, performs Slack I/O, reads Executive/Wake state, persists cursors, or imports provider/Wake modules. When a turn requires attention it emits a frozen `mastermind.agent_dialogue_attention.v1` value with a deterministic **source reference**, not a new durable attention-ID namespace. WP-TW2 later adapts that source fact into existing Wake vocabulary only after #174/Wake source-law reconciliation.

**Tech Stack:** Python 3.11+, dataclasses, enums, hashlib/json, accepted `integrations.slack_agent_dialogue.contract_v2`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-turn-watcher-amendment.md`

**Parent architecture:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md`

**Dependency:** WP-1 must be accepted/merged first so WP-TW1 consumes one canonical V2 parent/message contract. Do not implement a temporary duplicate V2 schema to make WP-TW1 run earlier.

## Global Constraints

- Implementation pickup MUST re-pin current protected `master`, the merged WP-0 package, accepted WP-1 merge SHA, and open Wake/ASD sister carriers immediately before editing and before push.
- `watch_mode="turn_watch_v1"` on the immutable validated V2 parent is mandatory. Missing/`null`/unknown mode is ordinary ASD and cannot generate automatic attention.
- Raw Slack text, delivery IDs, timestamps, member names, display names and caller-claimed session aliases are never classifier authority.
- The classifier receives already-validated V2 parent/message values; it does not add a second parser, message schema or identity system.
- WP-TW1 performs **zero network**, **zero Slack API**, **zero AF_UNIX service calls**, **zero provider calls**, **zero Wake calls**, **zero Runtime/Agent OS reads**, **zero filesystem writes**, and **zero persistence**.
- WP-TW1 does not modify `integrations/slack_agent_dialogue/service.py`; WP-1 owns normal request/response dispatch and WP-TW2 owns later observer/polling integration.
- WP-TW1 does not modify `control_plane/wake_events.py`, `control_plane/wake_router.py`, SessionTargetRegistry, RuntimeBinding, Wake ledger or provider dispatchers while #174 remains the Wake transport/source-law carrier.
- No new queue, cursor, pending-turn table, watcher registry, last-seen state, session alias registry, retry ledger, daemon or background task.
- The same semantic turn observed repeatedly must produce the same source reference; changed semantic payload under the same message key refuses under existing ASD conflict law.
- Model output has zero authority over target seat, routing identity, bound/unbound status, Wake kind, provider/session destination or source resolution.
- **Sister-session path reservation:** WP-TW1 owns only:
  - `integrations/slack_agent_dialogue/turn_watcher.py`
  - `tests/test_slack_agent_dialogue_turn_watcher.py`
  Any need to modify another production file returns to Sol unless a fresh source-law ruling explicitly widens scope.

---

## File Structure

- Create `integrations/slack_agent_dialogue/turn_watcher.py` — closed classifier/action/refusal vocabulary, trusted admission facts, deterministic attention projection and source-ref derivation.
- Create `tests/test_slack_agent_dialogue_turn_watcher.py` — watcher-mode admission, direction/lineage/terminal/fork/duplicate/source-ref/security/no-side-effect falsifiers.
- Read only: `integrations/slack_agent_dialogue/contract_v2.py` from accepted WP-1.
- Read only: existing V1/V2 tests for message-body and reply-lineage semantics.
- Do not change service/engine/Wake/provider files.

---

### Task 1: Freeze the classifier contracts and deterministic source reference

**Files:**
- Create: `integrations/slack_agent_dialogue/turn_watcher.py`
- Create: `tests/test_slack_agent_dialogue_turn_watcher.py`

**Interfaces:**

Produce constants:

```python
ATTENTION_SCHEMA = "mastermind.agent_dialogue_attention.v1"
ATTENTION_SOURCE_KIND = "agent_dialogue_attention"
ATTENTION_WAKE_KIND = "dialogue_turn_pending"
TURN_WATCH_MODE_V1 = "turn_watch_v1"  # import/re-export WP-1 constant; do not duplicate if possible
```

Produce enums:

```python
class TurnAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    WAKE_CEO = "WAKE_CEO"
    WAKE_COO = "WAKE_COO"
    WAKE_COO_TERMINAL = "WAKE_COO_TERMINAL"
    TERMINAL = "TERMINAL"
    REFUSE = "REFUSE"
```

Produce immutable trusted correlation input:

```python
@dataclass(frozen=True)
class TurnRoutingFacts:
    root_job_id: str | None
    routing_workstream: str | None
    source_workstream: str | None
    ceo_target_bound: bool
    coo_target_bound: bool
```

These are **already-derived caller facts**. The classifier does not resolve SessionTargetRegistry or Executive state itself. Exact accepted ID/workstream validators may be reused where they are pure; otherwise values are bounded/control-free and treated only as correlation, never authority.

Produce attention shape:

```python
@dataclass(frozen=True)
class AgentDialogueAttention:
    schema: str
    source_kind: str
    source_ref: str
    source_dialogue_schema: str
    message_key: str
    message_fingerprint: str
    commission_fingerprint: str
    operation_key: str
    target_seat: str
    attention_kind: str
    root_job_id: str | None
    routing_workstream: str | None
    source_workstream: str | None
    evidence_refs: tuple[str, ...]
```

Produce decision:

```python
@dataclass(frozen=True)
class TurnDecision:
    action: TurnAction
    attention: AgentDialogueAttention | None
    reason: str
    refusal_code: str | None
```

- [ ] **Step 1: Write RED closed-vocabulary tests**

Assert exact enum values above. Unknown actions cannot be constructed through classifier output.

- [ ] **Step 2: Write RED source-reference identity tests**

Freeze the semantic source-ref ingredients to **exactly**:

```text
source_kind = agent_dialogue_attention
commission_fingerprint
message_key
target_seat
attention_kind = dialogue_turn_pending
```

Use canonical sorted compact ASCII JSON and full SHA-256:

```python
source_ref = "agent_dialogue_attention:" + sha256(canonical_identity_bytes).hexdigest()
```

Tests prove source_ref is invariant to:

```text
Slack ts/event id/retry count
observed time
provider/model/account
RuntimeBinding generation/native handle
arbitrary message summary/body prose outside the already-fingerprinted semantic message
routing destination/session alias
```

and changes when any frozen identity ingredient changes.

The source ref is an opaque Wake-source correlation string, **not** a new stored attention primary key and not an `eia-*` identity.

- [ ] **Step 3: Write RED attention-shape tests**

Only target seats `ceo|coo` are valid. Attention kind is exact `dialogue_turn_pending`. Evidence refs are copied only from already-validated V2 message evidence and remain bounded by the V2 contract. No timestamp/provider/native-session/Slack-event/display-name field exists.

- [ ] **Step 4: Implement minimal dataclasses/helpers**

Keep `turn_watcher.py` stdlib + first-party V2 contract imports only. No network/process/database imports.

- [ ] **Step 5: Run RED→GREEN focused tests**

```bash
python -m pytest tests/test_slack_agent_dialogue_turn_watcher.py -q
```

- [ ] **Step 6: Commit**

```bash
git add integrations/slack_agent_dialogue/turn_watcher.py tests/test_slack_agent_dialogue_turn_watcher.py
git commit -m "feat(asd): freeze stateless dialogue turn attention contract"
```

---

### Task 2: Implement watcher admission and closed turn classification

**Files:**
- Modify: `integrations/slack_agent_dialogue/turn_watcher.py`
- Modify: `tests/test_slack_agent_dialogue_turn_watcher.py`

**Interfaces:**

Produce:

```python
def classify_turn(
    *,
    parent: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    routing: TurnRoutingFacts,
) -> TurnDecision:
    ...
```

`parent` and all `messages` MUST be normalized values returned by accepted WP-1 validation. For defense in depth the function may call `validate_parent_v2`/`validate_message_v2` again; it must never accept arbitrary free-form text or transport rows.

- [ ] **Step 1: Write RED watcher-mode admission tests**

Pin:

```text
V2 parent watch_mode == "turn_watch_v1" -> eligible for classification
V2 parent watch_mode is None -> NO_ACTION / WATCH_DISABLED
unknown mode -> validation refusal before classifier
historical V1 parent cannot enter this function as valid V2 parent
changed operation_key/commission/session parent identity -> REFUSE
```

Watcher mode itself grants no execution. If the latest turn requires COO/CEO attention but the corresponding trusted routing fact is false, return `NO_ACTION` with reason/refusal code `DIALOGUE_WAKE_TARGET_UNBOUND`; do not guess another target.

- [ ] **Step 2: Write RED initial-commission tests**

With watcher-enabled parent, complete valid history and **no contributor ACK yet**:

```text
coo_target_bound=true  -> WAKE_COO + attention(target=coo)
coo_target_bound=false -> NO_ACTION / DIALOGUE_WAKE_TARGET_UNBOUND
```

The classifier does not infer that Slack delivery itself means the COO received/claimed work.

- [ ] **Step 3: Write RED COO-origin classification table**

Latest valid semantic leaf from COO/worker contributor:

```text
ACK                         -> NO_ACTION
PROGRESS                    -> NO_ACTION
BLOCKED                     -> WAKE_CEO
DECISION_REQUEST            -> WAKE_CEO
RESULT                      -> WAKE_CEO
```

Use V2 actor/message eligibility; never use Slack author display name. `BLOCKED`/`DECISION_REQUEST`/`RESULT` require `ceo_target_bound=true`, otherwise `DIALOGUE_WAKE_TARGET_UNBOUND`.

- [ ] **Step 4: Write RED Sol-origin classification table**

Latest valid semantic leaf from an eligible CEO executive surface:

```text
RULING replying to current unresolved contributor request -> WAKE_COO
CONTINUE                                      -> WAKE_COO
AMENDMENT_AVAILABLE                           -> WAKE_COO
STOP with no later exact COO consumption      -> WAKE_COO_TERMINAL
STOP with later exact COO terminal ACK/receipt -> TERMINAL
```

A Sol reply to an already-resolved/noncurrent request is `REFUSE / REPLY_LINEAGE_INVALID`, not a new Wake.

- [ ] **Step 5: Implement the closed classifier table**

Use explicit `if`/mapping over known message families. Future/unknown message types never inherit Wake behavior implicitly. Unknown/unclassifiable semantic states return `REFUSE`, not newest-message wins.

- [ ] **Step 6: Run tests**

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_turn_watcher.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add integrations/slack_agent_dialogue/turn_watcher.py tests/test_slack_agent_dialogue_turn_watcher.py
git commit -m "feat(asd): classify watcher-enabled dialogue turns deterministically"
```

---

### Task 3: Enforce semantic lineage, fork refusal and terminal consumption

**Files:**
- Modify: `integrations/slack_agent_dialogue/turn_watcher.py`
- Modify: `tests/test_slack_agent_dialogue_turn_watcher.py`

**Interfaces:** existing classifier.

- [ ] **Step 1: Write RED fork tests**

Construct two independently valid semantic leaves that compete for the same unresolved turn/request. Timestamp ordering must not choose one. Expected:

```text
TurnAction.REFUSE
refusal_code == "DIALOGUE_FORKED"
attention is None
```

Duplicate entries with identical message key + fingerprint are one semantic message and do not create a fork.

- [ ] **Step 2: Write RED changed-payload conflict tests**

Same message key + different fingerprint => `REFUSE / MESSAGE_KEY_CONFLICT`, even if one transport timestamp is newer.

- [ ] **Step 3: Write RED reply-lineage tests**

Require exact `reply_to_message_key` lineage for actionable Sol replies. A RULING/CONTINUE/STOP cannot resolve or wake against an unrelated contributor turn merely because it is later in time.

- [ ] **Step 4: Write RED STOP terminal tests**

Pin exactly one terminal continuation:

```text
STOP first observed -> WAKE_COO_TERMINAL
same STOP re-observed -> same attention source_ref
exact later COO consumption ACK/terminal receipt -> TERMINAL, no attention
later ordinary unrelated ACK -> does not falsely consume STOP
```

Do not create persisted `stop_delivered`/`consumed` state; derive terminality from complete normalized thread history.

- [ ] **Step 5: Implement semantic-leaf reduction**

Create a pure helper that reduces validated message history to the current semantic leaf/leaf set by message keys and reply lineage. Do not use mutable cursors or current wall clock.

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest tests/test_slack_agent_dialogue_turn_watcher.py -q
```

- [ ] **Step 7: Commit**

```bash
git add integrations/slack_agent_dialogue/turn_watcher.py tests/test_slack_agent_dialogue_turn_watcher.py
git commit -m "fix(asd): refuse forked dialogue turns and derive terminal consumption"
```

---

### Task 4: Adversarial no-side-effect/no-control-plane acceptance

**Files:**
- Modify: `tests/test_slack_agent_dialogue_turn_watcher.py`

**Interfaces:** final WP-TW1 module.

- [ ] **Step 1: Add source-structure fences**

AST/source tests must prove `turn_watcher.py` contains/imports none of:

```text
sqlite3
asyncio task/background loop creation
requests/httpx/aiohttp/urllib network use
Slack SDK
socket/subprocess
control_plane.wake_*
control_plane.session_targets
provider SDKs
Executive Runtime/Agent OS clients
filesystem write/open-for-write
thread/session/browser automation
```

Imports are limited to stdlib pure data/hash tools plus accepted V2 contract helpers.

- [ ] **Step 2: Add authority-laundering mutations**

The same invariant must fail after each mutant:

```text
watch_mode None treated as enabled
caller-claimed session alias changes target
Slack display name determines CEO/COO direction
provider/model name changes target seat
unbound target falls through to other seat
new message type inherits wake behavior
newest timestamp resolves semantic fork
changed message payload under same key is accepted
source_ref includes RuntimeBinding/provider/session/timestamp
attention creates eia-* ID or persistence
classifier imports/calls Wake mint_obligation
```

- [ ] **Step 3: Add repeat/restart-equivalence proof**

Calling `classify_turn()` repeatedly with deep-copied semantically identical parent/messages/routing facts must produce byte-equivalent decision dictionaries and identical source refs. No module-global mutable state may affect output.

- [ ] **Step 4: Collision census before push**

Immediately before push:

```text
re-pin protected master
verify accepted WP-1 merge still supplies V2 contract
verify no other PR owns turn_watcher.py/test path
verify #174 remains the sole provider-native Wake transport carrier
verify WP-TW2 has not begun editing service/Wake adapter paths under a competing source law
```

Any collision => STOP for Sol. Do not rename the classifier to create a second implementation.

- [ ] **Step 5: Run exact acceptance suite**

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_contract.py \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_turn_watcher.py \
  -q
python -m compileall -q integrations/slack_agent_dialogue
git diff --check
```

Then require exact-head hosted CI/CodeQL under current branch protection.

- [ ] **Step 6: Independent adversarial review**

Reviewer attacks:

```text
classifier secretly routes sessions/providers
classifier creates Wake obligations
watch mode becomes retroactive
Slack transport facts become authority
fork chooses newest message
terminal STOP loops forever
unbound target silently falls back
source-ref identity changes when runtime destination rotates
new persistence/cache becomes semantic truth
WP-TW1 edits WP-1/WP-TW2/#174 paths
```

- [ ] **Step 7: Return to Sol**

Return exact head, exactly two changed implementation files, test/CI/CodeQL receipts, mutation results, reviewer verdict and explicit capability statement:

```text
WP-TW1 = BUILT_NOT_PROVEN / PRODUCTION_INERT pure classifier
AgentDialogueAttention source projection = BUILT_NOT_PROVEN
Slack observer/polling = NOT_BUILT (WP-TW2)
Wake source vocabulary/adapter = NOT_BUILT (WP-TW2 after #174 reconciliation)
provider-native Wake delivery = unchanged #174 truth
production Agent Relay = unchanged ASD-A2 truth
zero-manual-wake bilateral loop = NOT_BUILT until WP-TW3 real canary
```

## Stop Condition

WP-TW1 stops when a pure function can deterministically classify watcher-enabled V2 dialogue history and emit an identity-stable `AgentDialogueAttention` source fact or typed refusal with **zero side effects and exactly two changed implementation/test files**. It must not modify Agent Relay service/background behavior, call Slack, mint Wake obligations, route sessions, call providers, persist watcher state, or start WP-TW2/WP-TW3.
