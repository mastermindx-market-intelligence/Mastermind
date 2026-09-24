# OCR-6 Slack & Executive Steward Continuity Projection Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a successful Executive cross-realm rollover feel continuous to Sol/Chairman: keep the same Fable company-dialogue thread and logical presentation while the underlying Attempt/Worker/realm/provider session changes, and expose the exact current continuity/capacity/blocker state in Chairman Control Room as the first Executive Steward product surface—without letting Slack, Control Room or Steward cause routing/retry/lifecycle changes.

**Architecture:** Add one pure `OperatorContinuityProjection` derived from existing Executive Jobs/Attempts/Events, OCR-3 RuntimeBinding projection and provider-capacity evidence. Agent Relay may mechanically emit an existing V2 `PROGRESS` frame into the already-bound root dialogue thread after a new Attempt has an exact continuation ACK; it does not add a new message type. The V2 actor is the trusted `executive_surface` COO/Claude actor (`Mastermind · Fable`), while `applies_to` moves to the current Attempt. Control Room consumes the same pure projection and renders it read-only. The initial Executive Steward is therefore **a continuity-aware read/attention layer over canonical owners**, not an autonomous scheduler. An optional later OpenClaw bridge may consume this read-only/bounded interface but remains noncanonical and removable.

**Tech Stack:** Python 3.12, existing Executive Runtime/Event APIs, OCR-3 continuation/binding projection, Worker Presence V2/Agent Relay, WP-2 company-dialogue gateway, Chairman Control Room pure compositor, pytest/browser proof.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-fable-root-seat-amendment.md`
- `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md`

## Dependency Gate

Core projection code may be implemented after OCR-3. Slack emission waits for accepted WP-1/WP-2 plus production Agent Relay prerequisites (ASD-A2/A3 or their accepted successor) and OCR-5. Control Room presentation waits for the current Control Room source/product path to be collision-free. OpenClaw integration is a final optional subwave and is not a dependency for any Mastermind continuity capability.

## Global Constraints

- Executive OS remains the only source for Job/Attempt/Worker/lifecycle state. Slack and Control Room never create/requeue/claim/terminalize an Attempt.
- Shared Provider Control/Capacity Fabric owns capacity facts; Control Room displays a sanitized projection only.
- Same Slack parent/thread is the immutable **commission/dialogue context**, not the provider session. Never create a new Slack thread because the provider account changed.
- V2 message type remains existing `PROGRESS`; no `RUNTIME_REBOUND` message-type fork unless future Worker Presence law independently adds one.
- Runtime rebound content is mechanically generated from exact canonical receipts. Provider/model text cannot author old/new Attempt/realm/session identifiers or claim successful continuity.
- A rebound Slack message may be sent only after `OPERATOR_CONTINUATION_ACKNOWLEDGED` exists for the exact current Attempt/provider session. `PREPARED` alone is insufficient.
- Slack delivery/effect-unknown does not change runtime continuity. Reconcile the same V2 message key/thread under existing Agent Relay law; never resend through a personal Claude/ChatGPT principal.
- Control Room/Steward projections are pure/read-only and persist no attention/session/capacity cache or cursor. Existing last-good/degraded behavior may be reused only under current CCR law.
- Provider/account label is an opaque operational realm label (e.g. `claude-pro-02`), not email/account PII.
- OpenClaw cannot own root/thread/Attempt/provider binding, send arbitrary Executive modifications, or use its own model/profile fallback as Mastermind failover.

---

### Task 1: Add a pure canonical continuity projection

**Files:**
- Create: `control_plane/operator_continuity_projection.py`
- Create: `tests/test_operator_continuity_projection.py`

**Interfaces:**
- Produces closed schema `mastermind.operator_continuity_projection.v1`.
- Pure primary builder accepts typed/current facts supplied by gather layer; no I/O in composer.

Target shape:

```python
{
  "schema": "mastermind.operator_continuity_projection.v1",
  "root_job_id": "JOB-001",
  "job_id": "JOB-004",
  "target_seat": "coo",
  "session_alias": "EXECUTIVE-COO-A",
  "logical_actor": "Mastermind · Fable",
  "status": "RUNNING",
  "current": {
    "attempt_id": "ATT-2",
    "worker_id": "claude-worker-b",
    "provider": "claude",
    "account_label": "claude-pro-02",
    "host_ref": "host-opaque-b",
    "provider_session_id_present": True,
    "binding_id": "bind-...",
    "binding_generation": 1,
    "continuation_state": "ACKNOWLEDGED",
    "capsule_id": "...",
  },
  "previous": {
    "attempt_id": "ATT-1",
    "terminal_status": "RATE_LIMITED",
    "account_label": "claude-pro-01",
  },
  "capacity": {
    "state": "available|degraded|unknown",
    "evidence_age_seconds": 12,
    "reason_codes": [],
  },
  "attention": "none|decision_required|reconciliation_required|capacity_risk|transport_degraded",
  "reason_codes": [],
}
```

`provider_session_id` itself is not required in public Control Room projection; use a non-secret presence/binding digest unless exact opaque ID is already an accepted UI field.

- [ ] **Step 1: Write RED-first lifecycle classification tests**

Pin at least:

```text
P1 RATE_LIMITED + JOB_REQUEUED + P2 RUNNING + continuation ACK -> RUNNING/ACKNOWLEDGED
P1 terminal + P2 claimed but no provider session -> REBINDING
P2 continuation PREPARED only -> REBINDING
unreconciled OPERATOR_OPERATION_EFFECT_UNKNOWN -> BLOCKED / reconciliation_required
no available capacity after lawful terminal -> WAITING_CAPACITY
current P2 completed -> COMPLETED
current runtime/placement join ambiguous -> UNKNOWN + degraded reason, never guessed
```

- [ ] **Step 2: Require exact root/current joins**

The gather/query layer may select current Job/Attempt only through exact root/Job fields and Executive current-attempt links. Never infer from Slack title, provider account, branch name or newest timestamp alone.

- [ ] **Step 3: Add capacity projection input as optional evidence**

Use only the accepted secret-free Capacity Fabric projection after CF2-I. Unknown/stale capacity remains `unknown`; it cannot turn the continuity state into `available` by default.

- [ ] **Step 4: Implement deterministic reason/attention classification**

No LLM. One exact rule table maps canonical state to the projection. `attention` is descriptive UI urgency only; it creates no Executive/Wake obligation itself.

- [ ] **Step 5: Mutation/fuzz tests**

Kill false-green mutations such as:

- PREPARED treated as ACKNOWLEDGED;
- Slack delivered treated as runtime running;
- stale provider capacity treated available;
- old Attempt selected after P2 claim;
- same account/provider evidence omitted during a claimed cross-realm rebound;
- effect unknown hidden because a newer Slack message exists.

- [ ] **Step 6: Run/commit**

```bash
pytest -q tests/test_operator_continuity_projection.py
python3 -m compileall -q control_plane/operator_continuity_projection.py

git add control_plane/operator_continuity_projection.py tests/test_operator_continuity_projection.py
git commit -m "feat(exec): project operator continuity from canonical runtime"
```

---

### Task 2: Emit one mechanically-derived Fable PROGRESS frame in the existing thread

**Files:**
- Create: `integrations/slack_agent_dialogue/runtime_continuity.py`
- Modify only after WP-1 acceptance: `integrations/slack_agent_dialogue/service.py` if an internal trusted request opcode is needed.
- Create: `tests/test_slack_runtime_continuity_projection.py`

**Interfaces:**
- Internal trusted function, not MCP/model tool:

```python
def build_rebound_progress(
    *,
    parent: DialogueParentV2,
    projection: OperatorContinuityProjection,
    message_key: str,
    created_at: str,
) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write RED-first stable-parent test**

Given one V2 parent with:

```text
work_ref
commission_ref
session_ref
operation_key
watch_mode
```

P1 and P2 must both project into the **same** parent/thread. Changing Attempt/Worker/provider must not create or mutate parent identity/fingerprint.

- [ ] **Step 2: Use existing `PROGRESS` semantics only**

Build an exact trusted actor:

```python
{"kind": "executive_surface", "seat": "coo", "reasoning_surface": "claude"}
```

`presentation_label(...)` must remain `Mastermind · Fable`.

`applies_to` points to current P2:

```python
{
  "kind": "executive_attempt",
  "job_id": projection["job_id"],
  "attempt_id": projection["current"]["attempt_id"],
  "worker_id": projection["current"]["worker_id"],
}
```

Body/summary is fixed, bounded and mechanically generated. Example semantics:

```text
stage = runtime_rebound
completed = "Previous Attempt ended RATE_LIMITED; continuation acknowledged."
next = "Current Attempt is running on the replacement realm."
```

Allowed evidence refs point to Executive/Event/GitHub references under current evidence-ref law. Do not expose host path/account PII/native session text.

- [ ] **Step 3: Gate emission on exact ACK**

`projection.current.continuation_state` must equal `ACKNOWLEDGED`; otherwise no message is constructed/sent.

- [ ] **Step 4: Use a deterministic message key**

Derive from immutable current continuity event identity/capsule, not random retry state, e.g. a bounded hash of:

```text
session_ref + target_attempt_id + capsule_id + "runtime-rebound"
```

Same semantic rebound after process restart maps to the same key and is reconciled through existing Agent Relay history rather than duplicated.

- [ ] **Step 5: Preserve effect-unknown Slack law**

The trusted internal caller sends through existing V2 `send_message`; timeout/unknown reconciles the same key and never mutates Executive state or emits through another Slack principal.

- [ ] **Step 6: Tests/commit**

```bash
pytest -q tests/test_slack_runtime_continuity_projection.py tests/test_slack_agent_dialogue_contract_v2.py tests/test_slack_agent_dialogue_engine_v2.py

git add integrations/slack_agent_dialogue/runtime_continuity.py integrations/slack_agent_dialogue/service.py tests/test_slack_runtime_continuity_projection.py
git commit -m "feat(asd): project Fable runtime rebound in the bound thread"
```

---

### Task 3: Bind company-dialogue capability to the replacement Attempt automatically

**Files:**
- Implement only after accepted WP-2/current live-binding prerequisite; exact file names should follow the landed runtime binding seam.
- Likely modify the existing trusted `DialogueBindingResolver` composition, not `mastermind_company_mcp` tool schemas.
- Create: `tests/test_company_dialogue_cross_attempt_binding.py`.

**Interfaces:**
- Same V2 parent/session/operation context, new exact worker/Attempt actor/application context.

- [ ] **Step 1: Prove P1 binding becomes stale after P2 claim**

A worker-side company MCP call from the dead P1 runtime must refuse because its trusted runtime binding is no longer current. It cannot keep posting as Fable after its Attempt is terminal.

- [ ] **Step 2: Prove P2 receives the same company thread context**

The binding resolver supplies:

```text
same work_ref/commission_ref/session_ref/operation_key/thread_ts
new actor/applicability = P2
```

No provider/account/thread field is model input.

- [ ] **Step 3: Prove P2 can ACK/PROGRESS/RESULT normally**

After continuation ACK and live company-dialogue capability attestation, P2 uses the exact existing WP-2 tools. A provider change does not require a provider-specific MCP/Slack gateway.

- [ ] **Step 4: Negative tests**

Refuse stale P1, wrong P2 worker, different root/commission, expired capability profile, and a P2 runtime attempting to select another Slack thread.

- [ ] **Step 5: Run WP-2/Worker Presence suites and commit**

Use exact current filenames after predecessors land.

---

### Task 4: Add continuity to the existing Chairman Control Room pure composition

**Files:**
- Modify: `control_plane/chairman_control_room.py`
- Modify: existing `tests/test_chairman_control_room.py`
- Modify current local web/UI renderer files only after inspecting current protected paths at implementation time.

**Interfaces:**
- Add one **source-attributed** optional `continuity` block to a work/root card only after an exact root join.
- Do not synthesize overall lifecycle.

- [ ] **Step 1: Write RED pure-compositor tests**

`compose_control_room(...)` receives an optional map keyed by exact `root_job_id`/work join produced by the gather layer. A card with exact matching runtime root gains:

```text
logical_actor
status
current attempt/provider/account_label
previous attempt terminal state
continuation state
capacity state
attention/reason codes
```

A mismatched root remains unjoined/degraded; title similarity never joins.

- [ ] **Step 2: Preserve binding/navigation law**

Runtime continuity does not turn surface bindings into lifecycle truth. Local Claude/Codex app URLs/session locators may remain optional navigation, not current runtime proof.

- [ ] **Step 3: Gather from canonical current sources**

Gather layer reads Executive Runtime + OCR-3 projection and accepted secret-free capacity source. Failures produce named degraded entries. No persistent cache/new DB.

- [ ] **Step 4: Product card design**

A Fable card should make these states visually distinct:

```text
RUNNING — Claude realm 05 · host A
DRAINING — capacity low
REBINDING — old Attempt closed, new session not ACKed
RUNNING — Claude realm 02 · continuity ACKed
BLOCKED — effect reconciliation required
WAITING_CAPACITY — no eligible realm
TRANSPORT_DEGRADED — runtime is healthy, Slack projection uncertain
COMPLETED
```

Do not show raw provider session IDs, private hostnames or account PII.

- [ ] **Step 5: Browser proof**

Use the existing governed browser/devserver path at current accepted state. Prove desktop and narrow breakpoint cards with real fixture/production-safe data and all states above. Screenshots are product evidence, not runtime authority.

- [ ] **Step 6: Tests/commit**

```bash
pytest -q tests/test_chairman_control_room.py tests/test_operator_continuity_projection.py
```

Commit only current bounded CCR/UI paths.

---

### Task 5: Define the Executive Steward read-only operating API

**Files:**
- Create: `control_plane/executive_steward.py`
- Create: `tests/test_executive_steward.py`

**Interfaces:**
- `ExecutiveStewardSnapshot` is a pure/read-only composition over existing sources.
- Initial public operations are read/navigation/attention only.

Conceptual methods:

```text
list_responsibilities()
get_responsibility(root_job_id)
get_current_runtime(root_job_id, seat)
explain_blocker(root_job_id)
get_attention()
```

Optional navigation methods may return existing `surface_bindings`/Slack/PR refs but do not open/modify anything themselves unless current Control Room has a separately accepted navigation actuator.

- [ ] **Step 1: RED tests for authority boundary**

Source/AST tests must prove no calls to:

```text
create_job
requeue_job
claim_job
rate_limit_attempt
complete_attempt
Wake dispatch
Slack send
provider adapter start/resume
capacity selection
```

- [ ] **Step 2: Compose answers from exact canonical projections**

The Steward must be able to answer:

```text
"Where is Fable running?"
"Why did it move?"
"Is continuity acknowledged?"
"Why is this program blocked?"
"Which item needs Sol/Chairman?"
```

using structured state, not LLM inference as canonical fact.

- [ ] **Step 3: Attention law**

Reuse existing Executive Inbox/Wake/Worker Presence attention where accepted. Continuity projection may enrich explanatory context but does not create another durable attention queue.

- [ ] **Step 4: Tests/commit**

```bash
pytest -q tests/test_executive_steward.py tests/test_operator_continuity_projection.py

git add control_plane/executive_steward.py tests/test_executive_steward.py
git commit -m "feat(exec): add read-only Executive Steward projection"
```

---

### Task 6: Optional OpenClaw subordinate bridge — after core Steward acceptance

**Files:**
- New integration package/path only after current OpenClaw installation/version/API is re-researched and pinned.
- Must not modify Executive lifecycle or Agent Relay canonical paths simply to fit OpenClaw.

**Mission:** Let OpenClaw host a conversational/operator shell or paired-node convenience over the **accepted Executive Steward read API and separately approved bounded actuator calls**, while proving Mastermind state is unchanged if OpenClaw is offline/removed.

- [ ] **Step 1: Re-falsify current OpenClaw capabilities at implementation time**

Pin exact installed/current documentation/version for nodes, ACP/harness sessions, Claude/Codex integration, Slack/channel behavior and authentication. Do not build against assumptions from the 2026-08-27 research pass if the contract moved.

- [ ] **Step 2: Freeze an allowlisted Mastermind tool surface**

Start read-only:

```text
steward.list_responsibilities
steward.get_responsibility
steward.get_attention
steward.get_current_runtime
```

No generic shell/SSH, provider profile selection, OpenClaw session failover or Slack posting.

- [ ] **Step 3: Keep OpenClaw session IDs noncanonical**

They may be local UI/session convenience only. Never map OpenClaw session identity into Job/Attempt/Worker/RuntimeBinding or dialogue parent identity.

- [ ] **Step 4: Prove unplug test**

With OpenClaw stopped/removed:

```text
Executive Runtime remains correct
current Fable binding remains recoverable
Slack thread identity remains recoverable
Control Room/Steward core continues
no queued work is lost or duplicated
```

- [ ] **Step 5: Later bounded actuation only by separate release**

If OpenClaw is used as a host/node actuator, each command must be one already-authorized Mastermind operation with exact operation/Attempt identity; OpenClaw cannot select another provider/host on failure. Ambiguous remote modification returns to Executive reconciliation.

## Stop Condition

OCR-6 core stops when a real OCR-5 rollover remains one visible Fable company thread, the rebound is mechanically projected only after exact continuation ACK, stale Attempt dialogue is fenced, and Control Room/Executive Steward show the current runtime/capacity/blocker state read-only. OpenClaw is optional and cannot be used to claim core OCR-6 completion.
