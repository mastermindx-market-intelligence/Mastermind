# Autonomous Delegation Operational Fluency Implementation Program

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development before production code, and use superpowers:verification-before-completion before any completion claim. Every modifying wave below remains independently commissioned/reviewed and must re-pin current protected source before write.

**Goal:** Convert the Chairman-approved organizational-continuity architecture into a production-fluent delegation fabric where one canonical company responsibility is admitted once, bounded work is placed on lawful capacity, exactly one current worker and one current Sol target can act, provider/model returns are mechanically projected, safe retries/rollovers preserve identity, many independent programs run concurrently, and the Chairman operates from Control Room/Linear/Grok without `#agent-dispatch` or provider-session archaeology.

**Architecture:** Extend existing Executive OS, Agent OS, Agent Dialogue/Relay, WP-TW/Wake, Capacity Fabric, Operator Continuity and OCR-6 only. Future automated CEO admission gets a transport-neutral identity while historical v1 MCP/Slack identity remains frozen. Autonomous child operation identity is a deterministic projection of the existing Executive Job/lineage; Attempt/Worker/fence remains execution authority; Agent Dialogue parent identity remains operation-stable while message applicability is Attempt-local. Provider turns return through governed harness projection rather than model etiquette. Initial fleet concurrency is cross-root only: many roots may run concurrently on distinct lawful Worker realms, while each root has at most one action-authoritative active child until separate intra-root workspace/integration proof exists.

**Tech Stack:** Python 3.12, existing Executive SQLite Runtime/Event command-id idempotency, existing strict-v2 COO cycle, Agent Dialogue V2 + Slack Web API client/runtime, Company Dialogue MCP, WP-TW/Wake, RuntimeBinding/Operator Continuity, Capacity Fabric/Model Router, Chairman Control Room/Executive Steward, pytest, existing hosted CI/CodeQL and governed browser proof.

**Spec:** `docs/superpowers/specs/2026-08-29-autonomous-delegation-operational-fluency-amendment.md` (architecture carrier #225). Parent source law remains merged #214. This plan is part of existing organizational-continuity planning carrier #212 and does not create another program.

## Global Constraints

- Protected planning basis at authoring: `Mastermind@adccc544509aaa0ef7c0bb4f8bdbbfab19cf85e2`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1. Every implementation wave must re-pin then-current protected source and same-SHA procedures before write.
- #225 is records/source law only. New runtime waves in this plan do not START until #225 is protected and current-source compatible. Already-started independent carriers continue under their own authority.
- Executive OS remains sole Job/Attempt/Worker/Event/lease/requeue authority. No delegation registry, operation database, retry table, second scheduler, Sol-owner store, session DB, Slack task queue or duplicate Steward.
- Agent OS remains durable organizational truth. GitHub remains implementation/proof. Linear remains selective projection. Slack remains dialogue/transport only.
- Existing carriers are exclusive owners: #217/MAS-200, #221, #223, #222/MAS-206, #215, current Capacity/OCR/RF/HF/PF/MH lanes, #170 where still required, and #188/Web-Sol/Secretary lanes. Do not recreate their scopes.
- Historical v1 `mcp_intent_id()` / `slack_intent_id()` vectors and existing v1 ingress behavior remain byte-compatible. Transport-neutral identity is additive/versioned.
- A stale provider UI may remain visible; sanctioned action authority comes from current Executive Attempt/Worker/fence/tool binding, never GUI presence.
- `EFFECT_UNKNOWN` blocks failover. Generic semantic failure is not automatic retry permission.
- No broad intra-root parallel write execution in this program. Initial fleet concurrency is multiple independent roots with at most one action-authoritative active child per root.
- Green CI, a Slack message, a Wake delivery or a QUEUED Job is not production acceptance.
- No child below is implicitly commissioned by this plan. Each modifying wave requires the normal current Chairman-authorized program scope, current source, collision, runtime and carrier gates.

---

## Dependency DAG

```text
#225 SOURCE LAW
   |
   +--> AD-ID1 transport-neutral automated root identity
   |      |
   |      +--> AD-ID2 approved second-ingress parity / duplicate-race proof
   |
   +--> AD-CHILD1 Executive Job -> company operation identity
   |      |
   |      +--> AD-DLG1 #217 release (existing owner)
   |              |
   |              +--> AD-DLG2 idempotent dialogue-parent ensure
   |                       |
   |                       +--> AD-RET1 sealed-worker mechanical RESULT projection
   |                       +--> AD-RET2 sustained operator semantic-yield projection
   |
   +--> AD-SOL1 exact Sol action-target enforcement / transfer
   |
   +--> AD-RETRY1 typed retry-safe classification
   |
   +--> Capacity + HF/PF/OCR realm prerequisites
          |
          +--> AD-FLEET1 bounded cross-root parallel dispatch

#221 -> #223 -> live Agent Relay prerequisites feed AD-DLG2/AD-RET*
#222/OCR-6R + AD-* projections -> AD-CR1 Chairman Control Room operational cockpit
all above -> SHADOW -> CANARY -> SMALL FLEET -> PRODUCTION FLEET
```

---

### Task 0: Release the revised source law and keep current owners exclusive

**Files / carriers:**
- Architecture carrier: Mastermind #225, exactly `docs/superpowers/specs/2026-08-29-autonomous-delegation-operational-fluency-amendment.md`.
- Planning carrier: Mastermind #212, including this plan and the current-source reconciliation record added beside it.
- No runtime path changes in this task.

- [ ] **Step 1: Verify #225 exact one-file scope**

Require current head, one changed path, no runtime/config/test file, `git diff --check`, required hosted `test`, and a fresh exact-head Sol source-law review against the Chairman outcome.

- [ ] **Step 2: Reconcile protected-source movement**

If protected `master` moves while #225 CI/review is running, compare the material owners named in the spec. Material collision -> reconcile the same #225 carrier and rerun proof. Unrelated movement may be documented only when current branch-protection/current-source law permits it; never blind merge.

- [ ] **Step 3: Merge only the exact accepted #225 head**

Merge under repository protection only after exact-head/current-base proof. Merge makes `SPEC_ONLY` source law; it starts nothing below.

- [ ] **Step 4: Keep #212 DRAFT/HOLD**

Update #212's current-source record and PR body to name #225 plus all current carriers. #212 is the program DAG, not runtime authority.

**Stop condition:** #225 is protected and #212 is current/recoverable. If source-law review finds a material architecture defect, repair #225 before any new runtime wave.

---

### Task 1: AD-ID1 — Add transport-neutral automated CEO request identity without breaking v1

**Files:**
- Modify: `control_plane/ceo_request.py`
- Modify: `control_plane/executive_ceo_ingress.py`
- Modify: `tests/test_executive_ceo_request.py`
- Modify: `tests/test_executive_ceo_ingress.py`
- Read-only regression: `control_plane/ceo_intent.py`
- Read-only regression: `integrations/executive_mcp/schemas.py`

**Interfaces:**

Add to `control_plane.ceo_request`:

```python
AUTOMATED_INTENT_ID_PREFIX = "auto-"
AUTOMATED_REQUEST_REF_RE = re.compile(r"^req-[a-z0-9][a-z0-9._-]{7,95}$")

def normalize_automated_request(payload: Any) -> dict[str, Any]: ...
def automated_intent_id(request_ref: str) -> str: ...
```

Identity domain is exactly:

```python
b"mastermind.executive_automated_request.v1\x00"
```

`automated_intent_id()` returns `auto-` plus the first 32 lowercase hex characters of SHA-256(domain + exact UTF-8 request_ref), and must satisfy existing `ceo_intent.INTENT_ID_RE`.

`normalize_automated_request()` reuses the existing request normalization semantics but **does not accept `operation_key`**. Required semantic fields are exactly:

```text
objective
department
priority
execution_profile
```

Optional fields are exactly the current v1 non-identity option set:

```text
workstream
allowed_write_paths
validation
attempt_limit
```

Add to `control_plane.executive_ceo_ingress`:

```python
SUBMIT_SCHEMA_V2 = "mastermind.executive_ceo_ingress_submit.v2"
STATUS_SCHEMA_V2 = "mastermind.executive_ceo_ingress_status.v2"
```

Exact submit-v2 frame:

```json
{
  "schema": "mastermind.executive_ceo_ingress_submit.v2",
  "request_ref": "req-...",
  "observed_grounding": {"mastermind_sha":"...","macro_sha":"...","boot_packet_schema":"mastermind.ceo_boot_packet.v1"},
  "request": {"objective":"...","department":"...","priority":1,"execution_profile":"research_only"}
}
```

Exact status-v2 frame:

```json
{
  "schema": "mastermind.executive_ceo_ingress_status.v2",
  "request_ref": "req-..."
}
```

V2 derives the `auto-*` intent id internally; callers/models never provide it. V2 uses the existing `ceo_intent.submit_intent()` sink and existing UNIQUE command-id semantics. No new table/dedupe lock/store.

- [ ] **Step 1: RED — freeze historical v1 compatibility and new identity vectors**

Add tests asserting all existing literal MCP/Slack vectors remain unchanged. Add literal automated vectors for at least three request refs and prove the same request ref always produces the same `auto-*` id independent of a simulated ingress label.

- [ ] **Step 2: RED — automated request refuses caller/model operation identity**

Prove `operation_key`, `intent_id`, actor, branch, worktree, provider/account/session/host, requested authorities and every existing privileged field refuse in `normalize_automated_request()`.

- [ ] **Step 3: RED — v2 CeoIngress identical replay and conflict race**

Using a real temporary Executive Runtime, concurrently submit the same `request_ref` + same normalized payload twice and require one Job / same receipt. Mutate one material request field under the same request ref and require `operation_conflict` with zero second Job.

- [ ] **Step 4: Implement the minimum additive identity/request law**

Reuse existing path/validation/profile helpers; do not duplicate normalization behavior. Do not change v1 required/optional field sets.

- [ ] **Step 5: Implement CeoIngress v2 by reusing the existing grounding/replay order**

V2 must preserve the current load-bearing order: normalize -> derive deterministic identity -> exact command lookup -> resolve durable replay before fresh grounding -> for new work perform trusted grounding double-read -> same `ceo_intent` mutation sink.

- [ ] **Step 6: Run focused proof**

```bash
python3 -m pytest -q \
  tests/test_executive_ceo_request.py \
  tests/test_executive_ceo_ingress.py \
  tests/test_ceo_intent.py
python3 -m compileall -q control_plane/ceo_request.py control_plane/executive_ceo_ingress.py
git diff --check
```

- [ ] **Step 7: Adversarial mutation tests**

Kill at minimum: v1 identity changed; transport label enters automated digest; request_ref stripped/case-folded; `operation_key` accepted in automated request; concurrent identical request creates two Jobs; same request_ref changed payload overwrites/reuses without conflict; grounding double-read removed.

**Real proof:** production-disarmed temporary-runtime duplicate race plus hosted exact-head CI/security. No provider execution required.

**Stop condition:** shared transport-neutral admission primitive is `BUILT_NOT_PROVEN / PRODUCTION_INERT`; historical v1 is unchanged. Do not switch a production frontend until AD-ID2 and normal ingress identity/arming gates are separately accepted.

---

### Task 2: AD-ID2 — Prove a second approved frontend resolves to the same automated root

**Files:**
- Modify: `integrations/executive_mcp/schemas.py`
- Modify: `integrations/executive_mcp/adapter.py`
- Modify: `integrations/executive_mcp/server.py`
- Modify: `tests/test_executive_mcp.py`
- Modify: `tests/test_executive_mcp_submit.py`
- Modify: `tests/test_executive_mcp_mutation.py`
- Reuse only: `control_plane/ceo_request.py`, `control_plane/ceo_intent.py`

**Gate:** do not start until AD-ID1 is accepted and current Executive MCP caller-identity/production-write source law permits an additive v2 modifying surface. If that identity gate is not yet accepted, keep this task `WAITING_DEPENDENCY`; do not weaken it to prove dedupe.

**Interface:** add separately versioned tools rather than mutating old tool semantics:

```text
submit_ceo_request_v2
ceo_request_status_v2
```

`submit_ceo_request_v2` accepts `request_ref` + the exact AD-ID1 automated semantic request; it contains no caller-supplied intent id or operation key. `ceo_request_status_v2` accepts only `request_ref`.

- [ ] **Step 1: RED — freeze the old five-tool surface/version**

Pin old tool names/schema snapshot for the old server version unchanged. Add a new server/version snapshot for the additive surface; do not silently widen v1.

- [ ] **Step 2: RED — cross-ingress race**

Against one temporary Runtime, submit the same request ref/envelope concurrently once through CeoIngress v2 and once through Executive MCP v2. Require exactly one `JOB_CREATED` command and the same root Job/intent identity.

- [ ] **Step 3: RED — changed payload conflict across ingress**

One frontend wins with request A; the other submits request B under the same request ref. Require conflict, one Job total.

- [ ] **Step 4: Implement by importing the single AD-ID1 law**

No MCP-specific automated identity derivation. No new dedupe table/lock. The adapter builds the exact same trusted envelope through `control_plane.ceo_request`.

- [ ] **Step 5: Run MCP + ingress matrices**

```bash
python3 -m pytest -q \
  tests/test_executive_ceo_request.py \
  tests/test_executive_ceo_ingress.py \
  tests/test_executive_mcp.py \
  tests/test_executive_mcp_submit.py \
  tests/test_executive_mcp_mutation.py
git diff --check
```

**Stop condition:** two independently authenticated/approved frontends can address one automated request identity with one Executive root. No production write arming is implied by implementation/CI.

---

### Task 3: AD-CHILD1 — Derive company operation/dialogue identity from Executive Job identity

**Files:**
- Create: `control_plane/executive_delegation_identity.py`
- Create: `tests/test_executive_delegation_identity.py`
- Modify: `control_plane/operator_continuation.py` only if current accepted continuation construction still consumes a caller-authored operation key and the exact integration can be made without colliding with an active OCR-3 carrier; otherwise stop after the pure projection and return the concrete integration gate to Sol.
- Read-only: `control_plane/executive_runtime.py`
- Read-only: `integrations/slack_agent_dialogue/contract_v2.py`

**Interfaces:**

```python
@dataclasses.dataclass(frozen=True)
class ExecutiveDelegationIdentity:
    job_id: str
    root_job_id: str
    operation_key: str
    session_ref: str


def derive_delegation_identity(job: Job) -> ExecutiveDelegationIdentity: ...
```

For one canonical Executive Job id `JOB-123`, the exact projections are:

```text
operation_key = exec-job-123
session_ref   = asd-session-exec-job-123
```

No hash, timestamp, provider, Attempt, Worker, Slack timestamp, objective text, commission bytes or model-generated name participates. One canonical Executive Runtime makes `job_id` globally unique for its lifecycle.

Accept only verified Executive orchestration Jobs with canonical `JOB-<digits>` identity and exact root/parent lineage. Refuse malformed/foreign objects rather than formatting their strings.

- [ ] **Step 1: RED — stability across Attempts and provider movement**

Create one strict-v2 child Job, claim P1, terminalize/requeue lawfully, claim P2. `derive_delegation_identity(job)` must remain byte-identical throughout.

- [ ] **Step 2: RED — distinct child identity**

Two different admitted work/review/repair Jobs produce different operation/session refs even when objective text is identical.

- [ ] **Step 3: RED — no semantic/provider entropy**

Mutating objective, provider/account/host fixture text, Attempt id, worker id, timestamps or commission document bytes in test-only mirrors cannot change the identity for the same Job.

- [ ] **Step 4: Implement the pure projection**

No persistence and no lookup by title. The module may import Job typing/validation but performs no I/O or lifecycle mutation.

- [ ] **Step 5: Prove Agent Dialogue validators accept the projection**

Build one V2 parent/context using the derived `operation_key` and `session_ref`; require exact contract validation.

```bash
python3 -m pytest -q \
  tests/test_executive_delegation_identity.py \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_executive_os_runtime.py
git diff --check
```

**Stop condition:** one Executive Job can be projected deterministically into stable company operation/dialogue identity. No Slack parent is created in this task.

---

### Task 4: AD-DLG1 — Release the existing WP-1R cross-Attempt dialogue repair; do not rebuild it

**Existing carrier:** Mastermind #217 / MAS-200 / `wp1r-agent-dialogue-v2-compat-20260829-sol-001`.

**Existing paths:**
- `integrations/slack_agent_dialogue/engine_v2.py`
- `tests/test_slack_agent_dialogue_engine_v2.py`
- `tests/test_slack_agent_dialogue_engine_v2_attempt_rebound.py`

- [ ] **Step 1: Re-pin #217 exact head/current base**

Require the expected three-path scope, terminal hosted CI/security and current-source collision check.

- [ ] **Step 2: Exact-head Sol review**

Must prove:

```text
worker RESULT -> Sol CONTINUE is legal when authority policy allows
same parent/thread contains P1 worker return + Sol reply + P2 worker progress
historical/reply carrier allows only same Executive job_id or same repository+PR
current outbound actor/applicability remains exact current context
foreign job_id / foreign repository PR refuse
```

- [ ] **Step 3: Merge #217 only as production-inert primitive**

No live Agent Relay/Slack proof is inferred from the merge.

**Stop condition:** #217 is protected. Any defect returns to same #217 carrier if still open/reconcilable; no replacement WP-1R branch.

---

### Task 5: AD-DLG2 — Add idempotent canonical V2 parent creation/ensure to the existing Agent Relay

**Gate:** #217 protected; #221 long-running Agent Relay runtime and its #223 enrollment stack must be reconciled/accepted to the point where changing shared Agent Relay service/client paths is collision-free. Do not stack this work onto an unresolved shared-path carrier.

**Files:**
- Modify: `integrations/slack_agent_dialogue/engine.py`
- Modify: `integrations/slack_agent_dialogue/engine_v2.py`
- Modify: `integrations/slack_agent_dialogue/slack_web_api.py`
- Modify: `integrations/slack_agent_dialogue/service.py`
- Modify: `tests/test_slack_agent_dialogue_engine_v2.py`
- Create: `tests/test_slack_agent_dialogue_parent_ensure.py`
- Modify: existing Slack Web API/service tests under their current exact filenames after #221/#223 land; if those files have moved, STOP rather than guess a replacement owner.

**Interfaces:**

Extend the existing injected client with one bounded parent-post primitive:

```python
async def post_parent(*, channel_id: str, text: str) -> SlackMessage: ...
```

Add V2 engine method:

```python
async def ensure_thread(
    *,
    context: DialogueContextV2,
    created_at: str,
) -> BoundThread: ...
```

Semantics:

```text
complete bounded history + 1 exact parent -> reuse
complete bounded history + >1 exact parent -> THREAD_BINDING_AMBIGUOUS
complete bounded history + near/conflicting parent -> THREAD_CONTEXT_MISMATCH
0 exact parents -> build exact V2 parent from context/policy and perform one parent post
post success/unknown -> reread exact history and reconcile
post outcome ambiguous + no provable exact parent -> SEND_EFFECT_UNKNOWN
never issue a second parent post merely because the first response was lost
```

- [ ] **Step 1: RED — existing-parent reuse and duplicate ambiguity**
- [ ] **Step 2: RED — lost post response reconciles one created parent**
- [ ] **Step 3: RED — lost response with unresolvable effect never posts again**
- [ ] **Step 4: RED — same Job/derived identity cannot bind a second parent under provider/Attempt movement**
- [ ] **Step 5: Implement minimum client/engine/service support**
- [ ] **Step 6: Run V1/V2/real-client regressions**

```bash
python3 -m pytest -q \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_parent_ensure.py \
  tests/test_slack_agent_dialogue_service.py \
  tests/test_slack_agent_dialogue_web_api.py
git diff --check
```

**Real proof:** production-disarmed Agent Relay against an approved disposable fixture channel: repeated `ensure_thread` for one derived operation returns the same thread; injected response-loss creates no second parent. No Chairman monitoring.

**Stop condition:** one admitted operation can ensure exactly one canonical dialogue parent through the existing Relay. No worker launch is authorized by this task alone.

---

### Task 6: AD-RET1 — Mechanically project sealed-worker terminal results to Agent Dialogue

**Gate:** AD-CHILD1 + AD-DLG2 accepted; real Agent Relay runtime path available. Preserve current worker result/authority semantics.

**Files:**
- Create: `control_plane/worker_semantic_turn.py`
- Create: `tests/test_worker_semantic_turn.py`
- Create: `integrations/slack_agent_dialogue/worker_result_projection.py`
- Create: `tests/test_slack_worker_result_projection.py`
- Modify: `control_plane/executive_supervisor.py`
- Modify: `tests/test_executive_operator_supervisor.py`
- Reuse only: `integrations/slack_agent_dialogue/contract_v2.py`, `engine_v2.py`, `control_plane/executive_delegation_identity.py`

**Interfaces:**

Pure closed classification:

```python
class WorkerSemanticTurnKind(str, Enum):
    RESULT = "RESULT"
    BLOCKED = "BLOCKED"

@dataclasses.dataclass(frozen=True)
class WorkerSemanticTurn:
    job_id: str
    attempt_id: str
    worker_id: str
    kind: WorkerSemanticTurnKind
    status: str
    summary: str
    evidence_refs: tuple[str, ...]
```

The initial sealed-worker slice maps only already-accepted terminal worker evidence:

```text
accepted terminal COMPLETED -> Agent Dialogue RESULT/PASS
accepted terminal FAILED with a closed non-retry-safe/semantic result -> RESULT/FAIL or BLOCKED according to exact typed failure class
ambiguous collection/validation/seal/effect -> no company RESULT; reconciliation-required error
```

No provider stdout/free prose becomes authority. Summary is bounded/sanitized from the already-validated worker result/receipt.

Trusted projection function:

```python
async def project_worker_semantic_turn(
    *,
    turn: WorkerSemanticTurn,
    binding: DialogueBinding,
    engine: DialogueEngineV2,
    created_at: str,
) -> MessageReceipt: ...
```

Message key is deterministic from exact Job + Attempt + terminal receipt/result digest + semantic kind; retrying projection reconciles the same message.

- [ ] **Step 1: RED — Codex completes without calling Company MCP**

Finish one fake/real sealed worker through `ExecutiveSupervisor`; prove a terminal result can be projected mechanically from trusted receipts with zero model Slack/MCP call.

- [ ] **Step 2: RED — stale Attempt cannot project**

After P2 becomes current, replay P1 terminal projection and require current-binding refusal/no new current semantic edge unless it is explicitly reconstructed as historical evidence by a separate read path.

- [ ] **Step 3: RED — Slack effect unknown never re-executes worker**

Projection loss/uncertainty reconciles only the deterministic dialogue message; it cannot create/requeue/relaunch the Job.

- [ ] **Step 4: Implement pure turn classification and trusted projector**
- [ ] **Step 5: Hook projection after successful terminal acceptance, not before lifecycle truth**

The supervisor first establishes/validates the canonical terminal result under existing law. Dialogue projection is downstream. If projection fails, terminal lifecycle truth remains true and transport is degraded; do not roll back the Job.

- [ ] **Step 6: Run focused proof**

```bash
python3 -m pytest -q \
  tests/test_worker_semantic_turn.py \
  tests/test_slack_worker_result_projection.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_slack_agent_dialogue_engine_v2.py
git diff --check
```

**Real proof:** one bounded Codex sealed worker completes while the provider is never instructed to post Slack; exact canonical RESULT appears through the Relay and WP-TW can classify the return.

**Stop condition:** terminal sealed-worker return projection is proven. Do not claim sustained mid-turn decision/blocker projection yet.

---

### Task 7: AD-RET2 — Project sustained Operator Harness semantic yields without relying on model etiquette

**Gate:** current Operator Continuity/HF/PF sustained-operator contract accepted and collision-free; AD-RET1 accepted. If the sustained provider adapter cannot expose a typed control-yield/result without scraping free-form model output, STOP and return that falsifier to Sol rather than inventing a shadow transcript parser.

**Files:**
- Modify: `control_plane/operator_harness_contract.py`
- Modify: `control_plane/executive_runtime.py` only at the existing Operator Harness event/receipt seam; no new table
- Modify: `control_plane/worker_semantic_turn.py`
- Modify: `integrations/slack_agent_dialogue/worker_result_projection.py`
- Modify: corresponding existing `tests/test_operator_harness_contract.py`
- Modify: `tests/test_worker_semantic_turn.py`
- Modify: `tests/test_slack_worker_result_projection.py`

**Closed semantic yield vocabulary:**

```text
PROGRESS
DECISION_REQUEST
BLOCKED
RESULT
```

Provider-native adapters may produce richer native events, but the accepted harness must normalize only a closed typed semantic yield bound to exact current Job/Attempt/Worker/turn operation. No raw transcript regex or “looks like a blocker” LLM classifier gains authority.

- [ ] **Step 1: RED — typed decision request becomes one V2 DECISION_REQUEST**
- [ ] **Step 2: RED — typed blocker becomes one V2 BLOCKED**
- [ ] **Step 3: RED — exact current Attempt/turn is required**
- [ ] **Step 4: RED — replay/duplicate native event projects one semantic message**
- [ ] **Step 5: Implement by extending the existing Operator Harness receipt/event wire, not a new queue**
- [ ] **Step 6: Prove provider-model silence**

Run a sustained test provider that never calls Company MCP. A typed control yield still reaches Agent Dialogue/Wake.

**Stop condition:** sustained workers can return control to the organization mechanically. Provider-specific conversational richness remains optional.

---

### Task 8: AD-SOL1 — Enforce one exact action-authoritative Sol target and safe transfer

**Gate:** #225 source law protected; current Wake/SessionTarget/RuntimeBinding owner state reconciled; Web-Sol/Secretary modifying surface remains separately gated.

**Files:**
- Create: `control_plane/sol_action_target.py`
- Create: `tests/test_sol_action_target.py`
- Modify: `control_plane/session_targets.py`
- Modify: `tests/test_executive_wake_fabric.py`
- Modify: `integrations/slack_agent_dialogue/turn_wake_adapter.py`
- Modify: `tests/test_slack_agent_dialogue_turn_observer.py`
- Modify: `control_plane/executive_steward.py` only after #222 is accepted/protected; otherwise this projection part stays gated on #222.
- Modify: `tests/test_executive_steward.py` after #222 acceptance.

**Interfaces:**

```python
class SolActionTargetState(str, Enum):
    RESOLVED = "RESOLVED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"

@dataclasses.dataclass(frozen=True)
class SolActionTarget:
    operation_key: str
    target_seat: str
    session_alias: str | None
    binding_id: str | None
    binding_generation: int | None
    state: SolActionTargetState
    reason_codes: tuple[str, ...]
```

The resolver consumes already-owned responsibility/session/runtime binding evidence. It stores nothing and elects nothing.

- [ ] **Step 1: RED — two observers, one resolved actor**

Two Sol surfaces can observe the same worker return; only the one matching the canonical resolved target may receive an executable action grant. The other receives observer-only refusal.

- [ ] **Step 2: RED — dead target does not elect newest tab**

Missing/unavailable current target returns `UNAVAILABLE`; no alternate session is selected by timestamp, health or provider recency.

- [ ] **Step 3: RED — explicit canonical transfer changes only target binding**

Use the existing responsibility/session binding owner to reconcile transfer. After transfer, old binding is refused and new binding is resolved; operation/Job/dialogue identity remains unchanged.

- [ ] **Step 4: RED — conflicting active bindings fail closed**

`ATTENTION_OWNER_CONFLICT`; zero executable Sol action grant.

- [ ] **Step 5: Implement pure resolver + current Wake/Steward projection**

Do not add a Sol registry/election database. Wake targets only the already-resolved destination.

**Real proof:** one worker return wakes exact Sol; simulate that target becoming unavailable; prove no sister Sol acts until a canonical transfer occurs, then fresh Sol can cold-start and continue the same operation.

**Stop condition:** exact Sol action-target state is `BUILT_NOT_PROVEN` and visible to Steward/Wake. Web-Sol/Grok actuation still requires its own accepted surface/permission gate.

---

### Task 9: AD-RETRY1 — Replace broad failure retry with typed retry-safe classification

**Files:**
- Create: `control_plane/executive_retry_safety.py`
- Create: `tests/test_executive_retry_safety.py`
- Modify: `control_plane/executive_coo_cycle.py`
- Modify: `control_plane/executive_runtime.py` only to expose/validate already-owned terminal evidence required by the classifier; no new lifecycle state/table
- Modify: `tests/test_executive_coo_cycle.py`
- Modify: `tests/test_executive_os_runtime.py`
- Read-only: current OCR-5/OCR-8 non-modifying quota rollover source/implementation.

**Interfaces:**

```python
class RetrySafety(str, Enum):
    SAFE_REQUEUE = "SAFE_REQUEUE"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    NEEDS_SOL = "NEEDS_SOL"
    TERMINAL_NO_RETRY = "TERMINAL_NO_RETRY"

@dataclasses.dataclass(frozen=True)
class RetrySafetyDecision:
    job_id: str
    attempt_id: str
    decision: RetrySafety
    reason_code: str
    evidence_digest: str
```

Closed initial `SAFE_REQUEUE` causes may include only causes already proven by current source law, such as definitive pre-effect infrastructure failure / proven-dead safe LOST and accepted exact non-modifying quota exhaustion. Do not add a cause merely because it is convenient.

`EFFECT_UNKNOWN`, write-capable ambiguous interruption, semantic/architecture failure, authority conflict and unknown cause must not classify `SAFE_REQUEUE`.

- [ ] **Step 1: RED — generic FAILED no longer auto-requeues**

Current broad `_RECOVERABLE` behavior is the falsifier. A generic semantic FAILED child must produce `NEEDS_SOL` or `TERMINAL_NO_RETRY` according to closed evidence, not automatic requeue.

- [ ] **Step 2: RED — EFFECT_UNKNOWN blocks**
- [ ] **Step 3: RED — exact safe pre-effect/proven-dead failure may requeue**
- [ ] **Step 4: RED — exact OCR-approved non-modifying quota exhaustion may requeue; write-capable equivalent may not**
- [ ] **Step 5: Implement classifier as pure policy over existing receipts/events**
- [ ] **Step 6: Make COO cycle consult classifier before `requeue_job()`**

A non-safe decision returns a bounded blocked/no-action outcome/attention projection under the existing lifecycle rather than inventing a retry state.

```bash
python3 -m pytest -q \
  tests/test_executive_retry_safety.py \
  tests/test_executive_coo_cycle.py \
  tests/test_executive_os_runtime.py
git diff --check
```

**Stop condition:** automatic requeue exists only for closed current-source-approved safe causes.

---

### Task 10: AD-FLEET1 — Allow bounded cross-root parallel dispatch over independent Worker realms

**Gate:** current CF2/RF/HF/PF/OCR realm and provider-neutral harness prerequisites accepted; at least two distinct lawful Worker/quota realms are production-proven enough for a non-destructive fleet canary. AD-RETRY1 accepted. Do not fake parallelism by running multiple Executive databases or services.

**Files:**
- Modify: `control_plane/executive_service.py`
- Modify: `tests/test_executive_service.py`
- Modify: `control_plane/executive_coo_cycle.py` only where fleet selection currently assumes a single globally serialized dispatch; preserve one-mutation-per-root-cycle semantics
- Modify: `tests/test_executive_coo_cycle.py`
- Modify: `scripts/executive_os_phase1c.py`
- Modify: existing host/service composition tests under `tests/test_executive_launchd_config.py`
- Reuse: existing Runtime Worker/quota claim transaction, Capacity/Model Router and Worker/remote transport owners.

**V1 fleet invariant:**

```text
many independent strict-v2 roots may have one active child each
one Worker/quota class can hold only one Attempt as today
a root has at most one action-authoritative active child execution
different roots may run concurrently only when their claimed Worker/quota/workspace authority is disjoint/lawful
```

- [ ] **Step 1: RED — two roots + two Workers can dispatch concurrently**

Current global `_dispatch_tasks`/serialized-worker refusal should fail this test before repair.

- [ ] **Step 2: RED — two roots cannot double-claim one Worker/quota class**

Keep existing atomic quota claim as the authoritative fence.

- [ ] **Step 3: RED — same root cannot run two write-capable children concurrently**

Even with spare Worker capacity, second child of the same root remains queued while one active child exists.

- [ ] **Step 4: RED — independent roots with colliding workspace identity refuse**

Do not gain concurrency by letting two write-capable roots share one mutable workspace accidentally.

- [ ] **Step 5: RED — one long-lived/high-priority root cannot silently starve all others**

Within current reviewed priority/capacity law, exercise at least five queued roots over multiple Worker realms and bound the observed scheduling progress/wait. If a new fairness rule is actually required, STOP and return a specific Executive scheduling source-law question to Sol rather than hiding a second queue in code.

- [ ] **Step 6: Generalize service dispatch coordination, not lifecycle**

Replace the single-global-active-dispatch guard with keyed coordination over existing root/Worker/workspace facts. Keep one `ExecutiveControlService`, one Runtime and existing task lifecycle; no new scheduler object with durable state.

- [ ] **Step 7: Run concurrency/restart/adverse suites**

```bash
python3 -m pytest -q \
  tests/test_executive_service.py \
  tests/test_executive_coo_cycle.py \
  tests/test_executive_os_runtime.py \
  tests/test_executive_launchd_config.py
git diff --check
```

**Real proof:** five independent non-destructive roots execute concurrently across at least two real lawful realms; each has one active child max; no duplicate Attempt/Worker/carrier; service restart reconciles every active Attempt before new claim.

**Stop condition:** cross-root concurrency is `BUILT_NOT_PROVEN` until real multi-realm proof. Intra-root parallelism remains explicitly NOT BUILT.

---

### Task 11: AD-CR1 — Make Control Room the sole normal operating cockpit for delegated responsibilities

**Gate:** #222/OCR-6R accepted; current Control Room owner collision-free; AD-CHILD1, AD-SOL1 and available continuity/attention projections accepted enough to compose truthfully.

**Files:**
- Modify: `control_plane/executive_steward.py`
- Modify: `tests/test_executive_steward.py`
- Modify: `control_plane/chairman_control_room.py`
- Modify: `tests/test_chairman_control_room.py`
- Modify: `app/static/chairman_control/index.html`
- Modify: `app/static/chairman_control/control_room.js`
- Modify: `app/static/chairman_control/control_room.css`
- Modify: current Control Room server/gatherer path only after current protected source confirms its exact existing filename; if it differs from `scripts/chairman_control_room.py`, STOP for collision/source reconciliation instead of creating a sibling server.

**Required responsibility card fields when source owners can supply them:**

```text
parent/workstream
current child Job + display name
canonical operation identity
Executive lifecycle
current Attempt / Worker
provider / opaque realm / host
RuntimeBinding generation
canonical dialogue carrier
latest valid semantic edge
turn_owner
exact action-authoritative target
attention health
transport health
retry/rollover safety
parent-active/no-successor
current GitHub carrier/evidence
needs_sol
needs_worker_or_coo
needs_placement
needs_chairman
exception reason codes
exact next lawful action
source/freshness/unknown reasons
```

- [ ] **Step 1: RED — current vs stale surface navigation**

Only the exact current actionable RuntimeBinding/surface may appear under normal `Open Current Session` / Resume behavior. Historical bindings render `SUPERSEDED / STALE_BINDING / NON_ACTIONABLE` with no action control.

- [ ] **Step 2: RED — `Needs Chris` excludes routine operational debt**

`WAITING_CAPACITY`, dead worker/Sol recovery, transport degradation, normal Sol review and parent continuation must not appear as Chairman-required. Credentials/new permissions/material company decisions may.

- [ ] **Step 3: RED — no actionable state is Slack-only**

Given worker RESULT, Sol continuation owed, transport split, retry hold, capacity wait and parent orphan fixtures, Control Room must surface the condition from canonical/derived owners even when the Chairman-facing view never reads free-form Slack history directly.

- [ ] **Step 4: Implement pure composition first, then UI**

Do not synthesize an overall lifecycle. Unknown joins stay unknown/degraded.

- [ ] **Step 5: Browser proof**

Desktop + narrow breakpoint with at least:

```text
RUNNING
NEEDS_SOL
NEEDS_WORKER
WAITING_CAPACITY
TRANSPORT_DEGRADED
ATTENTION_OWNER_UNRESPONSIVE
ATTENTION_OWNER_CONFLICT
RECONCILIATION_REQUIRED
PARENT_ACTIVE_NO_SUCCESSOR
COMPLETED
STALE/SUPERSEDED historical surface
```

**Stop condition:** Chairman can answer who owes every next turn and what genuinely needs Chairman action without `#agent-dispatch`. UI proof is product evidence, not lifecycle authority.

---

### Task 12: AD-CUTOVER — Staged production acceptance and removal of Chairman Slack dependency

**Files:**
- Prefer existing acceptance/Control Room/operations proof paths; do not create a new runtime service.
- Create records-only acceptance report only after real canaries: `research/AUTONOMOUS_DELEGATION_OPERATIONAL_FLUENCY_ACCEPTANCE_2026-08-29.md`.
- Update existing Agent OS/Linear/Control Room operating records through their current canonical owners after proof.

#### Stage 1 — SHADOW

- [ ] Derive automated root/child identity, placement candidate, turn owner, Sol target, retry decision and expected current surface for real manual operations without provider launch.
- [ ] Measure false conflict/duplicate/retry/placement decisions. Any authoritative false positive blocks canary.

#### Stage 2 — CANARY

- [ ] Run 2–3 bounded responsibilities: at least one read-only/research and one isolated code task.
- [ ] Chairman supplies initial intent only; zero Slack monitoring/provider-account choice.

#### Stage 3 — SMALL FLEET

- [ ] Run 5–10 independent roots across multiple lawful Worker realms.
- [ ] Prove one active child/root, no double claim, bounded queue progress, exact Control Room state.

#### Stage 4 — PRODUCTION FLEET

- [ ] Run 20–30+ responsibilities long enough to exercise real scheduling/attention behavior.
- [ ] No hidden starvation, duplicate child/carrier, stale-surface action or routine Chairman placement.

#### Mandatory adverse canaries

- [ ] Cross-ingress same request race -> one root.
- [ ] Sister-Sol same child race -> one child and one Sol action-authority target.
- [ ] Provider launch response lost -> same Attempt reconciliation, no alternate launch.
- [ ] P1 stale after P2 rebound -> stale sanctioned action refused.
- [ ] Codex/Claude returns without voluntary Slack/MCP -> mechanical semantic return projected.
- [ ] Sleeping/dead Sol -> exact Wake or canonical transfer before another Sol acts.
- [ ] Slack/Agent Relay unavailable -> runtime truth survives; semantic boundary holds and reconciles without duplicate execution.
- [ ] Retry taxonomy: safe pre-effect, generic semantic failure, write/effect-unknown, non-modifying quota exhaustion all classify correctly.
- [ ] Capacity saturation -> `WAITING_CAPACITY`, not Chairman account selection.
- [ ] Child terminal + active parent -> `PARENT_ACTIVE_NO_SUCCESSOR`, no automatic successor.
- [ ] Old native task physically remains available -> Control Room marks it non-actionable and sanctioned tools refuse it.
- [ ] Control host restart -> reconcile existing Attempts before fresh dispatch.

#### Final Chairman zero-touch proof

After initial authorization, for the measured acceptance interval the Chairman performs:

```text
zero #agent-dispatch opens required for operation
zero message shuttling
zero watcher repair
zero Sol-tab waking
zero worker-tab waking
zero provider-account/session selection
zero stale-task hunting
```

Genuine Chairman-only decisions may still be surfaced through Control Room/Grok and acted on explicitly.

- [ ] **Retire temporary convergence/session-local watcher scaffolding only after the canonical replacement path is PROVEN_LIVE for its work class.**

**Stop condition:** final acceptance report cites real Executive/Agent Dialogue/Wake/Capacity/Control Room/GitHub receipts and shows the Chairman-zero-touch outcome. Anything less remains `PARTIAL` / `BUILT_NOT_PROVEN` with the exact missing gate named.

---

## Self-review checklist for this plan

- [x] Preserves one canonical Executive lifecycle and existing owner planes.
- [x] Historical v1 cross-transport identity is preserved rather than silently rewritten.
- [x] Removes model-authored autonomous child identity without semantic-similarity mutation authority.
- [x] Distinguishes request, child, Attempt and dialogue identity.
- [x] Makes stale provider UI a non-authority condition instead of pretending it disappears.
- [x] Keeps #217/#221/#223/#222/#215 and Capacity/OCR carriers exclusive.
- [x] Makes provider return projection mechanical instead of etiquette-dependent.
- [x] Separates Slack transport failure from Executive lifecycle failure.
- [x] Preserves one exact Sol action-authority target and requires canonical transfer.
- [x] Replaces broad retry intuition with typed retry safety.
- [x] Addresses company-scale throughput through cross-root concurrency without a new scheduler.
- [x] Holds intra-root parallel writes behind separate workspace/integration proof.
- [x] Defines Control Room as the Chairman cockpit and stale native tasks as non-actionable history.
- [x] Requires staged cutover and real zero-touch/adverse canaries before retirement of manual scaffolding.
