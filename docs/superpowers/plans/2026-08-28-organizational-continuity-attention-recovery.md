# Organizational Continuity & Attention Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Chairman from routine message shuttling, watcher repair, session hunting and provider-account allocation by completing the existing Agent Dialogue → Wake → RuntimeBinding → Steward continuity path and proving it across real Codex and Claude/Fable work.

**Architecture:** This is a convergence/release plan over existing canonical owners, not a new runtime service. Agent Relay remains the dialogue transport owner, Executive Wake Fabric remains attention-delivery/ACK authority, Executive OS remains Job/Attempt/Worker/Event authority, Agent OS remains organizational truth, Capacity/Operator Continuity remains placement/rebinding authority, and OCR-6 remains the sole Executive Steward/Responsibility Matrix implementation owner. The plan repairs current semantic incompatibilities, then connects the existing owners and retires transition-era session-local watcher dependence only after real zero-touch proof.

**Tech Stack:** Python 3.12, existing Slack Agent Dialogue V2 / AF_UNIX service, existing Slack Web API client boundary, Mastermind Company Dialogue MCP, Executive Wake Fabric + existing Executive OS `events`, RuntimeBinding / SessionTargetRegistry, Operator Continuity, OCR-6 Executive Steward / Chairman Control Room, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-28-organizational-continuity-attention-recovery-amendment.md` (Mastermind PR #211; runtime release is held until that spec is protected/merged)

## Global Constraints

- Re-pin current protected `mastermindx-market-intelligence/Mastermind` `master`, load `docs/sol_skills/INDEX.md`, and load every required same-SHA skill before each modifying task. Skillpack schema remains `mastermind.sol_skillpack.v1`, bootstrap-major 1 compatible.
- PR #211 must merge as the accepted source-law spec before any new runtime implementation task in this plan is released. Planning/review of already-open carriers may continue while its protected merge is gated.
- Executive OS remains the only Job / Attempt / Worker / Event lifecycle and CEO-intent admission owner.
- Agent OS remains the only durable organizational workstream / decision / discovery / handoff owner.
- Slack / Agent Relay owns dialogue transport; Slack never becomes lifecycle truth.
- Wake owns wake obligation, routing, delivery attempt, target ACK and source-resolution law; no second nudge/retry plane.
- One logical modifying operation binds to one carrier until canonically reconciled. Never open a replacement for PR #209, #210, #193, #208, or any active canonical sibling carrier.
- Merged Wake #174 / protected merge `c4c39423f595cfe669961b871405eb2b13ff65c2` is source-durable but remains `BUILT_NOT_PROVEN` until its real exact-thread Codex `DELIVERED_UNACKNOWLEDGED` canary is accepted. Checked-in `production_armed=false` and disabled targets remain binding.
- During OSC-R0 recovery, do not create broad new `OPEN_PICKUP` fanout merely to increase activity. Healthy already-started carriers continue. Unbound frozen work is shown as `WAITING_CAPACITY / needs_placement`, not hidden Chairman labor.
- Use at most one temporary non-authoritative estate-level convergence watch. Existing child-local watchers may finish their current child cycles but gain no semantic authority.
- A local Codex task is not ACK, START, RESULT or liveness proof. Reciprocal work requires a canonical dialogue edge or a production-proven governed bridge that projects it.
- `EFFECT_UNKNOWN` always remains same-operation/same-destination reconciliation with zero blind retry/failover.
- Do not retire temporary session-local watchers until the final canary proves no lost turn across Codex and Claude/Fable.

## File / Owner Map

| Responsibility | Canonical implementation surface |
|---|---|
| V2 dialogue semantics | `integrations/slack_agent_dialogue/engine_v2.py` + `tests/test_slack_agent_dialogue_engine_v2.py` |
| Pure turn classification | PR #209: `integrations/slack_agent_dialogue/turn_watcher.py` + `tests/test_slack_agent_dialogue_turn_watcher.py` |
| Company dialogue MCP | PR #210: `integrations/mastermind_company_mcp/**` + its existing three tests |
| Agent Relay command service | `integrations/slack_agent_dialogue/service.py` + existing service tests |
| Slack transport engine | `integrations/slack_agent_dialogue/engine.py`, `engine_v2.py`, injected `SlackDialogueClient` |
| Wake source/obligation vocabulary | `control_plane/wake_events.py` + existing Wake tests |
| Wake ledger / ACK | `control_plane/wake_ledger.py`, existing persistence/ACK tests |
| Provider-native Wake transport | merged PR #174 / `integrations/executive_wake/**` + `control_plane/wake_dispatcher.py` |
| Continuation capsule | PR #193 / `control_plane/operator_continuation.py` + `tests/test_operator_continuation.py` |
| Capacity / H0 current carrier | PR #208; do not duplicate |
| Steward / Responsibility Matrix | sole OCR-6 owner: future `control_plane/operator_continuity_projection.py`, `control_plane/executive_steward.py`, existing `control_plane/chairman_control_room.py` path per protected OCR-6 plan |

---

### Task 1: Land the Incident Architecture and Freeze the Recovery Census

**Files:**
- Existing carrier only: PR #211, `docs/superpowers/specs/2026-08-28-organizational-continuity-attention-recovery-amendment.md`
- Read-only inputs: current `#agent-dispatch` threads, current Executive/Agent OS/GitHub owner state
- Durable discovery destination: existing `WS:CHAIRMAN-CONTROL-ROOM` / OSC records only if a material discovery needs persistence

**Interfaces:**
- Consumes: Chairman written-spec acceptance recorded on PR #211.
- Produces: protected source-law spec plus one read-only OSC-R0 release matrix; no lifecycle state.

- [ ] **Step 1: Reconcile PR #211 against current protected master**

Require the PR to remain one records file only. Compare its spec with all protected source movement since its authoring pickup. Material authority conflict blocks merge; unrelated implementation movement is recorded, not copied into the spec.

- [ ] **Step 2: Require current-base hosted proof**

Run the repository's protected test workflow on an immutable head whose PR merge ref uses the then-current protected base. Do not accept an older green run after a material protected-source merge.

- [ ] **Step 3: Sol-review and merge the exact accepted head**

Reject any runtime/config/Skillpack/provider/Slack/Agent OS/Linear addition. Merge only the exact reviewed records head.

- [ ] **Step 4: Run OSC-R0 as a source-attributed census**

For each materially active parent/child candidate record:

```text
workstream / parent
child operation_key
canonical carrier/thread
GitHub PR/branch/head when applicable
Executive Job/Attempt/Worker fact when applicable
latest valid dialogue edge
turn owner
watch/attention evidence
implementation evidence
parent terminal/nonterminal fact
next lawful action
exception reason codes
```

Do not persist a census database or cursor.

- [ ] **Step 5: Close obvious duplicate/orphan carriers without spawning replacements**

Exact examples already reconciled: duplicate OCR-3 replacement operation `operator-continuity-ocr3-task1-red-rebuild-20260828-sol-002` is terminally STOPPED because PR #193 is canonical. Apply the same one-carrier law to any equivalent duplicate found by OSC-R0.

- [ ] **Step 6: Commit only material durable discoveries to the existing owner**

No `WS:MASTERMIND-OS`, no supervisor DB, no new lifecycle store.

---

### Task 2: Repair Merged WP-1 V2 Dialogue Semantics

**Files:**
- Modify: `integrations/slack_agent_dialogue/engine_v2.py`
- Modify: `tests/test_slack_agent_dialogue_engine_v2.py`

**Interfaces:**
- Consumes: accepted V2 parent/message contracts and existing `TrustedAuthorityPolicy`.
- Produces: a V2 engine that permits lawful `RESULT -> CONTINUE` and same-parent Attempt applicability movement without weakening actor/applicability validation.

- [ ] **Step 1: Add RED for worker RESULT → Sol CONTINUE**

Use the existing `raw_v2_message()`/`v2_message()` fixtures. Construct one worker `RESULT` root and one CEO `CONTINUE` whose `reply_to_message_key` is the result key. Assert `DialogueEngineV2.read_thread()` / reply adjudication accepts it when `ExactV2AuthorityPolicy.allows_continuation()` returns `True`.

- [ ] **Step 2: Run the exact failing test**

```bash
python -m pytest tests/test_slack_agent_dialogue_engine_v2.py -q -k 'result and continue'
```

Expected RED: `THREAD_CONTEXT_MISMATCH` from the current `CONTINUE` predecessor whitelist.

- [ ] **Step 3: Make RESULT a lawful CONTINUE predecessor**

Change the `CONTINUE` branch in `_adjudicate_reply_v2()` from:

```python
if request_message["message_type"] not in {"ACK", "PROGRESS", "BLOCKED"}:
    raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
```

to:

```python
if request_message["message_type"] not in {"ACK", "PROGRESS", "BLOCKED", "RESULT"}:
    raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
```

Preserve the existing `BLOCKED.needed_from == "sol"` restriction and trusted continuation policy.

- [ ] **Step 4: Add RED for same parent P1 → P2 applicability movement**

Build two valid V2 worker messages with identical `work_ref`, `commission_ref`, `session_ref`, operation parent and lawful actor/applicability joins, but different accepted `applies_to` Attempt identities. Link the P2 message to the P1 message by `reply_to_message_key`. Assert the history is accepted and the latest message remains actionable.

- [ ] **Step 5: Run RED**

```bash
python -m pytest tests/test_slack_agent_dialogue_engine_v2.py -q -k 'applicability or rebound'
```

Expected RED: `THREAD_CONTEXT_MISMATCH` from whole-thread applicability equality.

- [ ] **Step 6: Separate immutable parent identity from per-message applicability**

Change `_message_context_matches()` and `_messages_share_context()` so parent/thread identity compares only:

```python
("work_ref", "commission_ref", "session_ref")
```

Do not compare historical `applies_to` across messages. Keep each message's own `validate_message_v2()` and `DialogueContextV2.normalized()` worker-attempt join validation intact.

- [ ] **Step 7: Run focused and adjacent GREEN**

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_service.py \
  -q
```

Expected: PASS with no V1 regression.

- [ ] **Step 8: Commit on one new bounded WP-1 compatibility carrier**

```bash
git add integrations/slack_agent_dialogue/engine_v2.py tests/test_slack_agent_dialogue_engine_v2.py
git commit -m "fix(dialogue): preserve result continuation and attempt rebound"
```

Stop at DRAFT/HOLD for independent review and exact-head hosted CI. Do not absorb PR #209/#210 paths.

---

### Task 3: Repair and Accept Existing WP-TW1 PR #209

**Files:**
- Existing carrier only: `integrations/slack_agent_dialogue/turn_watcher.py`
- Existing carrier only: `tests/test_slack_agent_dialogue_turn_watcher.py`

**Interfaces:**
- Consumes: Task 2 semantic law and accepted V2 messages.
- Produces: pure deterministic `classify_turn()` + `AgentDialogueAttention`; no side effects.

- [ ] **Step 1: Re-read current #209 head and existing Sol REQUEST_CHANGES**

Do not create another branch/PR. Preserve the two-file boundary.

- [ ] **Step 2: Add RED for RESULT → CONTINUE**

Expected final decision:

```python
assert decision.action is TurnAction.WAKE_COO
assert decision.attention.target_seat == "coo"
```

- [ ] **Step 3: Repair `_ceo_reply_lineage_valid()` minimally**

Allow `RESULT` as a `CONTINUE` predecessor while preserving current decision-request/RULING, BLOCKED-needed-from-Sol, fork, message-key conflict and sender restrictions.

- [ ] **Step 4: Add RED for same-parent P1 → P2 message applicability**

Same parent/commission/session and one linear reply chain with valid per-message actor/applicability joins must classify the latest semantic leaf rather than return `DIALOGUE_CONTEXT_MISMATCH`.

- [ ] **Step 5: Delete the whole-history `first_scope` equality rule**

Do not weaken `_same_parent_context()`; it continues to bind `work_ref`, `commission_ref`, and `session_ref`. Each message remains contract-validated independently.

- [ ] **Step 6: Run exact matrix**

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_contract.py \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_turn_watcher.py \
  -q
python -m compileall -q integrations/slack_agent_dialogue
git diff --check
```

- [ ] **Step 7: Require independent exact-head review + hosted CI/CodeQL**

Accept/merge only as `BUILT_NOT_PROVEN / PRODUCTION_INERT`. Do not start WP-TW2 from #209's authority.

---

### Task 4: Repair and Accept Existing WP-2 Company Dialogue PR #210

**Files:**
- Existing carrier only: `integrations/mastermind_company_mcp/adapter.py`
- Existing carrier tests: `tests/test_mastermind_company_mcp.py`, `tests/test_mastermind_company_mcp_mutation.py`
- Keep the existing seven-path PR boundary unless one test-only path is proven necessary by current source law.

**Interfaces:**
- Consumes: zero-model-input `DialogueBindingResolver` and Agent Dialogue V2 service.
- Produces: six governed MCP tools whose mutating semantic edges form one valid dialogue lineage.

- [ ] **Step 1: Add trusted reply binding to `DialogueBinding`**

Use this exact field:

```python
reply_to_message_key: str | None
```

It is host/resolver supplied and never appears in an MCP tool schema.

- [ ] **Step 2: RED initial ACK and subsequent RESULT cases**

Initial pickup may use `reply_to_message_key=None` when the current accepted V2 initial-edge law permits it. A later `RESULT` fixture must be built with the resolver-supplied current predecessor key.

- [ ] **Step 3: Validate trusted reply keys before transport**

Use the accepted V2 message-key shape by constructing through `build_message_v2()`. A malformed resolver-supplied reply key must produce `BINDING_UNAVAILABLE`/`DIALOGUE_REFUSED` before `_service_call` executes.

- [ ] **Step 4: Replace the hard-coded null**

Change:

```python
"reply_to_message_key": None,
```

to:

```python
"reply_to_message_key": binding.reply_to_message_key,
```

Do not add a read-then-send loop, retry, cursor, or line-of-dialogue database inside the MCP call. `resolve()` already runs once per invocation.

- [ ] **Step 5: Add an integration discriminator using WP-TW1**

Two sequential worker emissions with trusted predecessor binding must reduce to one linear semantic leaf under `classify_turn()`. A second root must fail the test.

- [ ] **Step 6: Preserve effect-unknown**

If the one downstream send has an ambiguous result, return the generated reconciliation message key and do not issue another send.

- [ ] **Step 7: Run GREEN**

```bash
python -m pytest \
  tests/test_mastermind_company_mcp.py \
  tests/test_mastermind_company_mcp_mutation.py \
  tests/test_executive_agent_capabilities.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_turn_watcher.py \
  -q
```

- [ ] **Step 8: Require exact-head independent review + hosted CI/CodeQL**

Merge only as production-inert. No public MCP endpoint or Slack credential is created by this task.

---

### Task 5: Prove the Existing Agent Relay / Company Dialogue Production Carrier

**Files / accepted owner surfaces:**
- `config/slack_agent_relay_app_manifest.yaml`
- `scripts/check_slack_agent_relay_app_manifest.py`
- `research/AGENT_RELAY_SLACK_APP_ADMIN_CEREMONY_2026-08-27.md`
- existing `integrations/slack_agent_dialogue/engine_v2.py`
- existing `integrations/slack_agent_dialogue/service.py`
- merged WP-2 package after Task 4

**Interfaces:**
- Consumes: one installed dedicated least-privilege Agent Relay app/principal and accepted secret-safe credential boundary.
- Produces: real exact-thread V2 read/write proof for the governed company-dialogue surface; no Job/lifecycle authority.

- [ ] **Step 1: Re-run the checked-in manifest guard**

```bash
python scripts/check_slack_agent_relay_app_manifest.py config/slack_agent_relay_app_manifest.yaml
```

Require exactly the protected least-privilege scopes and no Socket Mode/Event API/interactivity widening unless a separately accepted source law already changed them.

- [ ] **Step 2: Run the accepted native admin/credential ceremony**

Never expose the bot credential in chat, Slack prose, GitHub, argv, logs or screenshots. If the accepted secret destination is unavailable, return `BLOCKED` rather than inventing another credential store.

- [ ] **Step 3: Start only the existing Agent Relay service composition**

No second daemon/database. Verify AF_UNIX ownership/peer policy and Slack app identity before any live message.

- [ ] **Step 4: Canary one already-authorized disposable V2 thread**

Prove:

```text
company MCP read_thread -> exact canonical thread
company MCP ACK -> exact same thread
company MCP RESULT with trusted reply binding -> exact same thread
full thread reread -> valid V2 linear lineage
```

- [ ] **Step 5: Codex communication conformance canary**

Use one disposable bounded Codex worker with an exact bound communication principal. The test passes only if the canonical dialogue path receives ACK and RESULT without Chairman prompting. A local task result with no canonical edge must be classified `WORKER_RETURN_NOT_PROJECTED`, not success.

- [ ] **Step 6: Deliberate carrier-split adverse canary**

Have the test harness produce local-task-only evidence while the canonical thread lacks the edge. The operating surface must report `DIALOGUE_CARRIER_SPLIT / SPLIT`; it must not create a new Job/session or retry the work.

- [ ] **Step 7: Record production proof and stop**

Do not yet claim automatic Wake. Task 5 proves the communication edge only.

---

### Task 6: Add Agent Dialogue Attention to Existing Wake Vocabulary

**Files:**
- Modify: `control_plane/wake_events.py`
- Test: `tests/test_executive_wake_fabric.py`
- Test: `tests/test_executive_wake_fabric_hardening.py`
- Test/consumer: `tests/test_slack_agent_dialogue_turn_watcher.py`

**Interfaces:**
- Consumes: `AgentDialogueAttention` from WP-TW1 with `source_ref="agent_dialogue_attention:<64 lower-hex>"`, target seat, optional root Job/workstream correlation.
- Produces: route-independent existing `WakeObligation` with `SourceKind.AGENT_DIALOGUE_ATTENTION` and `WakeKind.DIALOGUE_TURN_PENDING`.

- [ ] **Step 1: RED exact new closed vocabulary**

Add tests requiring:

```python
SourceKind.AGENT_DIALOGUE_ATTENTION.value == "agent_dialogue_attention"
WakeKind.DIALOGUE_TURN_PENDING.value == "dialogue_turn_pending"
```

and requiring malformed dialogue source refs to refuse.

- [ ] **Step 2: Add exact source-ref grammar**

```python
AGENT_DIALOGUE_REF_RE = re.compile(r"^agent_dialogue_attention:[0-9a-f]{64}$")
```

- [ ] **Step 3: Extend the existing enum/closed sets only**

Add the two exact vocabulary values to `SOURCE_KINDS`, `WAKE_KINDS`, `SourceKind`, and `WakeKind`. Do not create another Wake record/table/type hierarchy.

- [ ] **Step 4: Extend `_source_ref()` and `mint_obligation()`**

For `SourceKind.AGENT_DIALOGUE_ATTENTION`, accept only `WakeKind.DIALOGUE_TURN_PENDING` and the exact source-ref grammar. Preserve route-independent identity and optional existing Job/workstream correlation. Do not copy Slack ts/provider/session/native handle into Wake identity.

- [ ] **Step 5: GREEN identity tests**

Repeated observation of the same `AgentDialogueAttention` must mint the same obligation id; changing provider/account/RuntimeBinding destination must not change it; changing the semantic source ref must change it.

- [ ] **Step 6: Run Wake regression**

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  tests/test_executive_wake_persisted_dispatch.py \
  tests/test_slack_agent_dialogue_turn_watcher.py \
  -q
```

- [ ] **Step 7: Commit as a bounded Wake vocabulary carrier**

Stop before Slack observation/provider delivery orchestration. Merged PR #174 transport remains the only provider-native dispatcher owner.

---

### Task 7: Implement WP-TW2 as One Storeless Agent Relay Observer + Existing Wake Adapter

**Files:**
- Create: `integrations/slack_agent_dialogue/turn_observer.py`
- Create: `tests/test_slack_agent_dialogue_turn_observer.py`
- Modify only if required for composition: `integrations/slack_agent_dialogue/service.py`
- Consume, do not duplicate: `integrations/slack_agent_dialogue/turn_watcher.py`, `control_plane/wake_events.py`, existing Wake persistence/router/dispatcher APIs

**Interfaces:**
- Consumes: complete bounded V2 thread history, `TurnRoutingFacts`, pure `classify_turn()`, existing Wake mint/persist/route/dispatch seam.
- Produces: one deterministic attention-to-existing-Wake handoff; no cursor/inbox/session database.

- [ ] **Step 1: Define a pure observation decision contract**

Create:

```python
@dataclass(frozen=True)
class ObservedTurn:
    thread_ts: str
    decision: TurnDecision

async def observe_once(...) -> tuple[ObservedTurn, ...]: ...
```

Dependencies are injected: accepted thread discovery/read function, routing resolver, optional ephemeral active-waiter predicate, and one wake sink callable. The module owns no credential and no persistent state.

- [ ] **Step 2: RED repeated observation dedupe**

Observe the same qualifying thread twice. Both observations derive the same attention/Wake identity; the existing Wake persistence idempotency must prevent duplicate semantic obligations. Do not add an observer cursor to make the test pass.

- [ ] **Step 3: RED active waiter suppression**

When an exact in-process `wait_for_reply` waiter is known active for the same target/turn, `observe_once()` must not issue a redundant provider Wake. Removing/restarting that ephemeral waiter allows the same deterministic source fact to take the cold Wake path.

- [ ] **Step 4: RED restart recovery**

Construct a fresh observer instance with zero memory over the same bounded Slack history. It must recompute the same source/obligation identity and never require a persisted last-seen cursor.

- [ ] **Step 5: Implement bounded history traversal through the existing Agent Relay client/engine**

Use the accepted Slack Web API history/reply surface already injected into Agent Relay. No Socket Mode, webhook service or second Slack app in V1.

- [ ] **Step 6: Route only through existing Wake authority**

The observer may call a narrow injected sink such as:

```python
async def submit_attention(attention: AgentDialogueAttention) -> str:
    ...  # existing Wake mint/persist/route path
```

It must not import provider SDKs or directly call Codex/Claude.

- [ ] **Step 7: Adverse cases**

Refuse/no-action on invalid parent, forked lineage, unbound target, changed message fingerprint, incomplete history, effect-unknown Wake dispatch, or routing ambiguity. Never select a different Sol/COO session as fallback.

- [ ] **Step 8: Run exact tests + hosted review**

Require V1/V2 Agent Relay regression, WP-TW1, Wake persistence/hardening, exact-head hosted CI/CodeQL, and a real Task-5 production Relay dependency receipt before arming.

---

### Task 8: Prove and Accept Wake Delivery, Then Add Target ACK / Source Resolution

**Files / existing owners:**
- Merged transport source from PR #174 (`integrations/executive_wake/**`, `control_plane/wake_dispatcher.py`)
- Existing ACK law: `control_plane/wake_ledger.py`
- New ACK ingress should receive its own bounded plan/carrier under existing Wake authority; do not reopen #174.

**Interfaces:**
- Consumes: a canonical dialogue-generated Wake obligation routed to an exact current RuntimeBinding.
- Produces first: real Codex `DELIVERED_UNACKNOWLEDGED`; later, one trusted reasoning-session ACK and source resolution through existing Wake ledger events.

- [ ] **Step 1: Run the missing post-merge Codex delivery canary**

Required journey:

```text
canonical harmless Wake obligation
→ exact ceo/codex route + current RuntimeBinding
→ one provider-native Codex transport attempt
→ exact existing thread receives bounded wake
→ reconstructed DELIVERED_UNACKNOWLEDGED
```

Checked-in production remains disarmed. The isolated canary may use only an accepted ephemeral exact route.

- [ ] **Step 2: Run lost-response adverse canary**

A timeout/ambiguous response after `turn/start` produces `EFFECT_UNKNOWN / RECONCILIATION_REQUIRED`; a repeated dispatch performs zero second provider turn and zero alternate-provider/session failover.

- [ ] **Step 3: Freeze ACK ingress before implementation**

ACK caller supplies only the opaque Wake obligation claim allowed by current law. Trusted host/gateway composition injects seat, session alias, reasoning surface and current binding identity; the model cannot author them.

- [ ] **Step 4: TDD ACK against `acknowledge()`**

Wrong obligation, wrong seat/surface/binding, stale binding generation, duplicate incompatible ACK, and provider-response-as-ACK all refuse. Correct exact target produces the existing `TARGET_ACKNOWLEDGED` ledger phase.

- [ ] **Step 5: Source resolution for dialogue attention**

Resolution may occur only after rereading the canonical dialogue source and proving the exact attention condition is no longer pending under the accepted classifier. Persist through existing Executive `events`; add no source-resolution table.

- [ ] **Step 6: End-to-end return wake**

Real worker RESULT → typed attention → Wake → exact Sol runtime → target reasoning-session ACK → canonical Sol review/edge. Prove the worker RESULT is not lost and the target ACK is not synthesized by the dispatcher.

---

### Task 9: Complete Existing Operator Continuity / Capacity Gates Without Chairman Account Selection

**Files / carriers:**
- PR #193 — canonical OCR-3 Task 1 continuation contract
- PR #208 — canonical CF2-H0 current-master pin repair
- Existing OCR-1 / OCR-2C / Capacity / PF1 / OCR-3 Tasks 2–5 plans and carriers only

**Interfaces:**
- Consumes: safe Executive Job/Attempt lifecycle and current capacity/realm evidence.
- Produces: lawful RuntimeBinding/placement for supported work classes; no second router/session registry.

- [ ] **Step 1: Independently review and land #193 only after exact-head/current-base proof**

It remains a pure production-inert two-file contract. Do not start Task 2 from PR body authority alone.

- [ ] **Step 2: Continue #208 on its same carrier after its required hosted RED is accepted**

No second H0/bootstrap carrier.

- [ ] **Step 3: Complete the accepted Capacity/OCR dependency order**

Use the protected Operator Continuity program order. Native realm auth readiness is not capacity truth; write/effect-unknown work cannot auto-failover.

- [ ] **Step 4: First automatic placement canary is non-modifying**

Sol selects logical capability avenue; Executive/Capacity selects one eligible concrete realm/Attempt. Chairman chooses no numbered account/session. Record the current RuntimeBinding and result.

- [ ] **Step 5: Adverse capacity case**

No eligible realm must surface `WAITING_CAPACITY / needs_placement`; it must not silently ask the Chairman to find a window or hop to an unverified provider.

- [ ] **Step 6: Remove `ACCOUNT_BINDING: CHAIRMAN_SELECTS` only for proven supported work classes**

Manual selection remains an explicit exceptional/admin path until each relevant class passes its own placement proof.

---

### Task 10: Implement the OCR-6 Executive Steward / Responsibility Matrix Projection

**Files:**
- Existing sole OCR-6 plan: `docs/superpowers/plans/2026-08-27-operator-continuity-ocr6-slack-steward-projection.md`
- Create under that sole carrier: `control_plane/operator_continuity_projection.py`
- Create under that sole carrier: `control_plane/executive_steward.py`
- Modify under that sole carrier only when current source path confirms ownership: `control_plane/chairman_control_room.py`
- Tests: `tests/test_operator_continuity_projection.py`, `tests/test_executive_steward.py`, current Chairman Control Room tests

**Interfaces:**
- Consumes: Executive runtime snapshot, Agent OS direct organizational snapshot/digest, current GitHub carrier evidence, validated Agent Dialogue/turn classification, RuntimeBinding/Capacity facts, existing Control Room source projection.
- Produces: read-only source-attributed responsibility rows; no synthetic lifecycle or mutation authority.

- [ ] **Step 1: Define closed projection enums**

```python
class TurnOwner(str, Enum):
    SOL = "SOL"
    COO_OR_WORKER = "COO_OR_WORKER"
    EXECUTIVE_PLACEMENT = "EXECUTIVE_PLACEMENT"
    ADMIN_OR_CHAIRMAN = "ADMIN_OR_CHAIRMAN"
    NONE_TERMINAL = "NONE_TERMINAL"
    UNKNOWN = "UNKNOWN"

class AttentionHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    SPLIT = "SPLIT"
    UNRESPONSIVE = "UNRESPONSIVE"
    UNKNOWN = "UNKNOWN"
    TERMINAL = "TERMINAL"
```

These are read projections only.

- [ ] **Step 2: Define one immutable responsibility row**

Include exact spec fields: parent/workstream, child operation, accountable executive, logical worker/COO, Executive Job/Attempt/Worker when present, RuntimeBinding/provider/realm/host when present, canonical dialogue carrier, latest valid semantic edge, `turn_owner`, `attention_health`, implementation carrier/PR, parent-continuation condition, `needs_sol`, `needs_coo`, `needs_placement`, `needs_chairman`, exception reason codes, exact next lawful action and source freshness/unknown reasons.

- [ ] **Step 3: RED deterministic turn-owner cases**

Worker `RESULT/BLOCKED/DECISION_REQUEST` with no later Sol edge → `SOL`. Sol `CONTINUE/RULING/REQUEST_REPAIR` with no later worker return → `COO_OR_WORKER`. No lawful RuntimeBinding for frozen executable work → `EXECUTIVE_PLACEMENT`. True new-authority/admin gate → `ADMIN_OR_CHAIRMAN`. Explicit child+parent terminal → `NONE_TERMINAL`. Ambiguity → `UNKNOWN`.

- [ ] **Step 4: RED parent orphaning**

Parent nonterminal + child terminal + no active/admitted successor + authored next dependency/action → exception `PARENT_ACTIVE_NO_SUCCESSOR`, `turn_owner=SOL`, `needs_sol=True`. This must not create or admit the successor.

- [ ] **Step 5: RED carrier-split attention health**

Same operation evidence showing peer wait paths on different semantic carriers → `AttentionHealth.SPLIT` + `DIALOGUE_CARRIER_SPLIT`. A local task result lacking canonical dialogue projection → `WORKER_RETURN_NOT_PROJECTED`. Neither changes Executive Job state.

- [ ] **Step 6: Preserve unknown joins**

Session Truth/Agent OS/Capacity source unavailable or stale must remain source-attributed `UNKNOWN/DEGRADED`, never inferred from Slack/GitHub prose.

- [ ] **Step 7: Compose into Chairman Control Room**

Display the Responsibility Matrix without making the UI a writer. Every field keeps source attribution/navigation to the owning system.

- [ ] **Step 8: Browser/product proof**

Using real current estate data, Chris must be able to answer without opening `#agent-dispatch`: what is active, what is actually executing, who owes the next turn, which attention path is degraded/split, which item needs Sol/COO/placement/Chairman, and what the exact next action is.

---

### Task 11: Retire Transition Watchers Only After the Zero-Touch Canary

**Files / runtime:**
- No new persistence.
- Existing Agent Relay / Wake / Steward / Control Room production surfaces only.
- Temporary ChatGPT/Claude/Codex scheduled watchers are cleanup targets, not source truth.

**Interfaces:**
- Consumes: Tasks 2–10 accepted at their promised capability tier.
- Produces: final organizational-continuity acceptance and safe retirement of temporary watcher scaffolding.

- [ ] **Step 1: Prepare two real bounded operations**

One Codex worker and one Claude/Fable worker, each with exact operation key, canonical Agent Dialogue carrier, lawful RuntimeBinding and no Chairman account-selection action after initial program authorization.

- [ ] **Step 2: Positive Codex journey**

```text
Sol commission
→ canonical ACK projected mechanically
→ Codex work/result
→ canonical RESULT projected mechanically
→ typed attention
→ exact Sol Wake + target ACK
→ Sol CONTINUE or STOP
→ exact worker responsibility resumes/stops
```

Chairman touches nothing after initial authorization.

- [ ] **Step 3: Positive Claude/Fable journey**

Run the same reciprocal cycle on the accepted Claude/Fable substrate. Provider-specific mechanics may differ; company dialogue/attention semantics must not.

- [ ] **Step 4: Parent-continuation canary**

Terminally STOP one child while its parent remains active with an authored next action. Responsibility Matrix must show `PARENT_ACTIVE_NO_SUCCESSOR / needs_sol` without auto-starting the next wave.

- [ ] **Step 5: Split-carrier adverse canary**

Deliberately withhold canonical projection while a local provider task reports a result. Steward must show `DIALOGUE_CARRIER_SPLIT` or `WORKER_RETURN_NOT_PROJECTED`; zero new Job/session/retry occurs.

- [ ] **Step 6: Capacity adverse canary**

Make all eligible capacity unavailable in an isolated supported test. Show `WAITING_CAPACITY / needs_placement`; Chairman receives no “pick account N” requirement.

- [ ] **Step 7: Effect-unknown adverse canary**

Ambiguous Wake/provider modification remains on same operation/destination; prove zero second provider turn and zero failover.

- [ ] **Step 8: Chairman acceptance ruler**

For the full canary window, record:

```text
Chairman message shuttles = 0
Chairman watcher repairs = 0
Chairman session hunts = 0
Chairman provider-account selections = 0
lost reciprocal turns = 0
duplicate Jobs/Attempts from attention = 0
cross-carrier blind retries = 0
```

- [ ] **Step 9: Retire temporary watchers**

After the canonical path is accepted, disarm the one temporary estate-level convergence watch and remove/stop transition-era session-local watcher requirements for normal supported operations. If shutdown fails, report the cleanup defect without reopening completed work.

- [ ] **Step 10: Durable closeout**

Update the existing OSC / Chairman Control Room / Operator Continuity Agent OS records and exact next action. Do not create another workstream or lifecycle plane.

## Self-Review Receipt

- Spec coverage: carrier integrity, Codex return projection, deterministic turn owner, parent-active-no-successor, attention health, manual account-selection removal, OSC-R0 recovery, admission brake and zero-touch acceptance are each mapped to explicit tasks.
- No-placeholder scan: no `TBD`, `TODO`, generic “add error handling”, unnamed code step or unowned new system remains.
- Type/interface consistency: `AgentDialogueAttention.source_ref` is the accepted `agent_dialogue_attention:<64 lower-hex>` form produced by WP-TW1 and consumed by the Wake vocabulary task; `TurnOwner`/`AttentionHealth` names match the incident spec; WP-2 reply lineage is resolver-owned and never model input.
- No-rebuild check: no task creates another lifecycle, queue, watcher registry, session registry, provider router, Slack authority, Wake table or Steward service outside existing owners.
