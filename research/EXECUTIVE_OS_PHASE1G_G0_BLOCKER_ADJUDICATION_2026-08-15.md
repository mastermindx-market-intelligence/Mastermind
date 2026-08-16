# Executive OS Phase 1G — G0 blocker adjudication

**Program:** Mastermind Executive OS / Phase 1G  
**Date:** 2026-08-15  
**Status:** binding design adjudication; **NO PRODUCTION ARMING**  
**Review being adjudicated:** independent fresh-context architecture/security review at PR #66 head `d64349f22327474ec2d862aa8a36bf97a507cc70`, verdict `BLOCK`  
**Scope:** B1–B4, H1–H5, M1–M5, and the load-bearing low findings from that review

---

## 0. Ruling and precedence

The independent review is accepted as a real G0-B review and its `BLOCK` verdict is not weakened.

This document is the Phase 1G authoring-session adjudication of that review. It does **not** convert G0 to PASS. G0 remains blocked until:

1. the source-law changes commissioned here land in a separate reviewed PR;
2. the design branch incorporates this adjudication and the related evidence corrections;
3. X0-A performs the required live zero-write capability canaries; and
4. a fresh-context reviewer re-checks the four blockers and the changed high-risk surfaces.

Where earlier Phase 1G text conflicts with this file, this file governs for:

- executive seat identity and decision authority;
- Chairman-required routing;
- strategic objective / priority / project-admission semantics;
- the Phase 1F §6 rulings;
- Secure MCP Tunnel identity and gateway authentication;
- dissent-review independence;
- conversation-key ownership;
- Workspace trigger-principal lifecycle;
- negative-only provider telemetry;
- attention-state non-dispatch;
- credential trust domains;
- protected constitutional paths.

This file does not override the Charter, current merged `config/authority_map.yml`, current merged `config/strategic_state.yml`, or the merged Phase 1F contract. The source-law corrections below therefore ship in a **separate source-law PR**; PR #66 remains documentation/commissioning only.

---

# 1. B1 — canonical executive authority substrate

## 1.1 Root defect accepted

The review is correct: Phase 1G uses `chairman_required` and "delegated CEO authority" as if the repository already contains a machine-readable executive authority substrate. It does not.

Phase 1F explicitly anticipated the first correct place to add seat identity: a minimal block in the existing reviewed `config/authority_map.yml` when a CEO-wake mechanism first needs to machine-read seats. Phase 1G is that mechanism.

## 1.2 Seat identity is added now, but seat identity never grants capability

A separate source-law PR must add an `executive_seats` block to `config/authority_map.yml` with this semantic contract:

```yaml
executive_seats:
  schema_version: 1
  chairman:
    occupant_label: Chris
    description: human Chairman / standing-mandate authority
    escalation_rank: 300
    authority: none
  ceo:
    occupant_label: Sol
    description: protected AI CEO cognition seat
    escalation_rank: 200
    authority: none
  coo:
    occupant_label: Fable
    description: bounded COO / project-orchestration seat
    escalation_rank: 100
    authority: none
```

Load-bearing interpretation:

- keys (`chairman`, `ceo`, `coo`) are **seat ids**;
- `occupant_label` is descriptive identity, not a security principal;
- `escalation_rank` orders attention altitude only;
- `authority: none` is mandatory and conformance-tested;
- neither the string `Sol`, the model id `gpt-5.6-sol`, the label `Fable`, nor any seat field grants a worker capability;
- runtime capability remains downstream of the existing authority map / packet gate / Executive authority policy.

## 1.3 Sol seat versus Sol model is disambiguated

`config/agents.yml` is model/provider routing only. The string/model `gpt-5.6-sol` is not the CEO seat registry.

Canonical vocabulary after the source-law change:

- **seat id:** `ceo`
- **occupant label:** `Sol`
- **published Workspace Agent route:** separately versioned deployment/config identity
- **model route:** separately versioned model/provider configuration

No implementation may use `sol` as a privilege-bearing seat id simply because a model or agent is named Sol.

## 1.4 A7 `FABLE_HUMAN` is explicitly legacy effect-taxonomy language

The existing A0–A7 ladder predates the Executive OS hierarchy. Its `A7 FABLE_HUMAN` label does **not** mean that the COO/Fable seat outranks or substitutes for the Chairman.

Source-law ruling:

- A0–A7 classifies the authority required for existing portfolio/governance effects.
- `FABLE_HUMAN` is a legacy label meaning the existing path requires the reviewed human/Fable approval boundary for those effects.
- It grants no organizational rank to the `coo` seat.
- Executive seat altitude is defined by `executive_seats` and the decision-category policy below.
- Any future rename of A7 is a separate compatibility migration; Phase 1G does not rename it casually.

This resolves the apparent Fable-A7-versus-COO inversion without silently changing existing portfolio governance.

---

# 2. Executive decision-category policy

Seat identity alone is not enough. The deterministic attention floor needs a versioned answer to: **which decisions require which executive altitude?**

A separate source-law PR must add an `executive_decision_policy` block to `config/authority_map.yml` and a conformance test. The **server derives the decision category from the requested operation and canonical state**; a model-supplied category is advisory text and is ignored for authorization.

## 2.1 Chairman-reserved categories

The following are `minimum_decision_seat: chairman` in v1:

| category | boundary |
|---|---|
| `CONSTITUTION_OR_CHARTER_CHANGE` | amend permanent Charter principles or their Executive-OS applicability |
| `EXECUTIVE_HIERARCHY_CHANGE` | add/remove/reorder executive seats or change seat meaning |
| `EXECUTIVE_AUTHORITY_POLICY_CHANGE` | change which decision classes belong to Chairman/CEO/COO or alter authority derivation |
| `COMPANY_PHASE_NORTH_STAR_OR_STANDING_CONSTRAINT_CHANGE` | change company phase, north-star mandate, or standing constraints |
| `PRODUCTION_AUTONOMY_ARM_OR_EXPANSION` | arm or materially widen autonomous production behavior |
| `PRODUCTION_WRITE_TRUST_MODEL_CHANGE` | widen the production MCP/write principal model or lower its authentication bar |
| `AUTONOMOUS_MERGE_DEPLOY_SERVICE_CONTROL_OR_CAPITAL_EXECUTION` | grant the autonomous system merge/deploy/service-control/live-capital capability |
| `CONSTITUTIONAL_PROTECTED_PATH_POLICY_CHANGE` | widen autonomous write access over Charter/authority/strategic/authentication/governance source law |
| `REASONING_GOVERNOR_CONSTITUTIONAL_CHANGE` | change the rules that define or allow cognitive downgrade/Pro requirements/Chairman class |
| `CHAIRMAN_DECISION_REQUEST` | approve/reject a canonical Chairman request |

A model cannot invent a new Chairman category, and a model cannot downgrade one of these categories. Adding/removing/reclassifying a category is itself `EXECUTIVE_AUTHORITY_POLICY_CHANGE` and therefore Chairman-reserved.

## 2.2 CEO-delegated categories

The following are `minimum_decision_seat: ceo` in v1 **only while they remain inside the standing mandate and do not alter a Chairman-reserved field**:

| category | boundary |
|---|---|
| `P0_OBJECTIVE_ADD_RETIRE_OR_RESCOPE` | update the P0 objective set while preserving company phase, north star, and standing constraints |
| `RESOURCE_POLICY_REBALANCE` | rebalance declared resource-policy weights while preserving all standing constraints |
| `PROJECT_INITIATE_WITHIN_ACTIVE_P0` | admit a project under an active strategic objective |
| `PROJECT_STOP_OR_REPRIORITIZE_WITHIN_ACTIVE_P0` | stop/resequence admitted work without changing standing mandate |
| `PROJECT_SCOPE_REFRAME_WITHIN_DELEGATED_AUTHORITY` | reframe objective/scope without expanding protected authority or write domains |
| `EXECUTIVE_REASONING_ESCALATION_REQUEST` | request a higher reasoning class; never self-lower a required class |
| `CEO_ROUTE_REPUBLISH_WITHIN_APPROVED_POLICY` | republish a preapproved logical CEO route without expanding tool/authority surface; acceptance invalidates until config receipt is re-proved |

If the operation crosses a standing constraint, protected-path rule, production-write rule, hierarchy rule, or constitutional boundary, the server maps it to the corresponding Chairman category.

## 2.3 COO-delegated categories

The following are `minimum_decision_seat: coo` in v1:

- decomposition of an already accepted parent project;
- bounded child-job creation inside parent authority/write/cost ceilings;
- bounded repair/review cycles;
- ordinary provider/account routing under deterministic placement policy;
- pausing/stopping work as a shrink-only safety action;
- surfacing exceptions upward.

COO may never widen the parent authority set or convert an exception into a new strategic objective.

## 2.4 Shrink-only emergency actions

Stopping, draining, cancelling, disabling a schedule, or disabling a production write arm is **not** treated as a privilege expansion. Lower executive levels may request shrink-only safety actions where the reviewed operation contract allows it.

Re-arming or widening after a drain/kill follows the normal decision category and may require CEO or Chairman approval.

---

# 3. Deterministic `chairman_required`

The hard floor is no longer an undefined prose classification.

The Wake Router computes a source-law decision category from the canonical operation/event and then derives:

```text
minimum_decision_seat = executive_decision_policy[derived_category]
```

Routing law:

```text
if minimum_decision_seat == chairman:
    hard_floor = chairman_required
elif minimum_decision_seat == ceo:
    hard_floor = max(hard_floor, ceo)
elif minimum_decision_seat == coo:
    hard_floor = max(hard_floor, coo)
```

The following are explicitly forbidden:

- taking `decision_category` from model text;
- treating `owner_seat`, `actor`, `business_impact`, provider identity, or model name as authority;
- deriving Chairman authority from a Slack username or chat statement;
- allowing semantic triage to lower the derived minimum seat;
- using the seat registry itself as a capability grant.

Every hard-floor receipt records `{policy_version, derived_decision_category, minimum_decision_seat, hard_reason_codes}`.

---

# 4. B2 — one source of truth per priority concept

## 4.1 Root defect accepted

The independent review is correct that the phrase `Improvement Agenda / accepted strategic state` conflated two different artifacts and falsely implied a mutable canonical priority queue already existed.

That compound phrase is retired.

## 4.2 Correct separation

There are three separate concepts, each with one owner:

### A. Company strategy authority — `config/strategic_state.yml`

`config/strategic_state.yml` is the canonical **strategy decision artifact** for:

- company phase;
- north star;
- active/paused/achieved/retired P0 objectives;
- resource-policy shares;
- standing constraints;
- strategic review triggers.

It remains deliberately **runtime-advisory/orientation-only**. No dispatcher, scheduler, broker, claim path, or worker runtime reads it to decide what to execute.

A strategy change becomes canonical only through a reviewed Git-backed decision that changes the file and lands with the applicable executive authority. The runtime consumes the resulting decision only through a later typed project/directive admission referencing the exact strategy revision; it does not turn YAML into a scheduler.

This preserves the existing strategic-state test invariant and avoids a second control plane.

### B. Candidate-work ranking — Improvement Agenda

`brain/improvement_agenda.py` and its generated agenda artifacts are **derived advisory ranking** over evidence and gaps.

They are not:

- a source of executive authority;
- a mutable CEO project queue;
- a lifecycle store;
- a source that may be patched directly to persist a CEO decision.

A CEO may consume an agenda item as evidence and decide to admit work, but the agenda row itself does not authorize or schedule anything.

### C. Admitted-work lifecycle/order — Executive OS

Executive SQLite remains the lifecycle authority for accepted Jobs/Attempts/activations.

A Job `priority` orders **already admitted and already eligible work** inside Executive OS. It does not decide company strategy and it does not allow a worker/model to self-admit a new objective.

## 4.3 Phase 1F L3 is superseded in wording, not in anti-control-plane intent

Phase 1F L3 says "The Improvement Agenda remains the company priority queue." That wording is no longer sufficiently precise for Phase 1G and is superseded by this ruling.

Replacement law:

> `config/strategic_state.yml` is the sole canonical company-strategy decision artifact. The Improvement Agenda is derived advisory candidate ranking. Executive OS owns lifecycle and ordering only after explicit project/directive admission. None of the three may silently take over another concept.

The source-law PR updates the worker-facing Executive contract to reflect this separation.

## 4.4 Autonomous project admission

A Sol discovery can follow exactly one of these lanes:

### Lane P1 — project within an existing active P0

If the proposed work:

- maps to an active P0;
- remains inside current standing constraints;
- does not change company phase/north star/resource policy;
- does not request a Chairman-reserved capability;

then the CEO may submit a typed `PROJECT_INITIATE_WITHIN_ACTIVE_P0` directive referencing:

```text
strategic_objective_id
strategic_state_commit_sha
commission_ref
scope
requested_authorities
allowed_write_paths
acceptance
operation_key
```

Executive OS validates the reference and creates/adopts the admitted parent objective. No strategic-state mutation is required merely to start an implementation project underneath an already accepted P0.

### Lane P2 — CEO-delegated strategy amendment

If the proposal adds/retires/rescopes a P0 or changes resource-policy shares without touching Chairman-reserved fields, Sol first submits a typed strategy-amendment proposal. Once the applicable decision is recorded, the strategy artifact is changed in Git and the resulting project directive references the new exact commit.

### Lane P3 — Chairman-reserved strategy/governance amendment

If the proposal changes company phase, north star, standing constraints, executive hierarchy, executive authority policy, production autonomy, protected-path policy, or another Chairman category, Sol creates a canonical Chairman request. No project admission proceeds against the proposed change until the Chairman decision is recorded and the exact source-law revision exists.

## 4.5 No direct agenda mutation tool

There is no X5 tool named "mutate Improvement Agenda priority". Regenerating the derived agenda may reflect new evidence later, but the agenda is not the durable destination of a CEO decision.

---

# 5. B3 — all Phase 1F §6 questions ruled

Phase 1F §6 said "do not build past these." Phase 1G now answers all six so no hidden prerequisite remains.

## Q1 — COO bounds home + values

**RULING:** accept the proposed `coo_cycle_policy` home in `config/authority_map.yml` for v1 and accept the proposed initial ceilings:

```yaml
coo_cycle_policy:
  schema_version: 1
  max_fan_out_per_parent: 8
  max_depth: 2
  max_repair_rounds: 2
  max_review_attempts_per_job: 2
  max_children_total: 16
  allowed_child_cost_classes: [default, small]
```

These are ceilings, not targets. Children still shrink against parent authority/write/cost/attempt limits.

Any future widening of these ceilings is a reviewed policy change, not a model decision.

## Q2 — review verdict vocabulary

**RULING:** binary `approve|reject` is sufficient for v1. `request_changes` is not a third terminal verdict. Repair intent is represented as `reject` plus typed findings/`next_actions`; the cycle then applies its bounded repair policy.

## Q3 — seat registry

**RULING:** order the minimal seat registry now because Phase 1G CEO wake is the first consumer that needs it. It lives in `config/authority_map.yml`, not `seats.yml`, and has `authority: none` for every seat.

## Q4 — implementation-review independence

**RULING:** for the **Phase 1F implementation-result review gate**, a different `worker_id` is the v1 minimum independent-review requirement and is sufficient to satisfy the aggregation gate. Provider/account differences are recorded as stronger evidence but are not silently required for every routine code-review job.

This ruling does **not** govern the separate E17 executive dissent control. High-impact executive dissent uses the stricter policy in §10 below.

The review receipt records an independence class so the evidence cannot imply stronger independence than actually existed:

```text
worker_only
account_separated
provider_separated
```

## Q5 — sequencing

**RULING:** keep 1F-B and 1F-C as separate reviewed changes. 1F-B lands schema/refusals/new inbox evidence first. 1F-C may not land before those invariants exist.

## Q6 — independence starvation

**RULING:** no review-independence waiver vocabulary in v1. If the configured attempts are exhausted without a qualifying independent review, emit the typed exception and escalate. The CEO may re-scope/re-resource the project but may not retroactively label a non-independent review independent.

This is fail-closed and matches the original Phase 1F recommendation.

---

# 6. B4 — Secure MCP Tunnel is connectivity, not principal identity

## 6.1 Reclassification

The earlier Phase 1G assumption that Secure MCP Tunnel might itself expose a trustworthy per-caller Workspace/App/User principal at the private gateway is retired.

New status:

```text
TUNNEL_BORNE_CALLER_IDENTITY = LIKELY_REFUTED / NOT LOAD-BEARING
```

X0-A still tests the live workspace, but production design assumes **the tunnel does not authenticate the executive caller**.

The tunnel authenticates the tunnel runtime/control-plane relationship and carries MCP requests. That is network reachability and daemon identity, not sufficient executive authorization.

## 6.2 Important positive evidence

Current OpenAI tunnel documentation shows that OAuth `Authorization` headers and connector-configured custom MCP request headers can be forwarded through the tunnel to the customer MCP server. Therefore an application-layer principal can be authenticated **through** the tunnel even though the tunnel itself is not the principal.

This becomes the basis of X1-B.

---

# 7. X1-B — gateway-level application authorization

X1-B is now a named prerequisite of any production write path.

## 7.1 Core law

Every MCP call reaching a modifying Executive tool must satisfy all of these independently:

```text
network reachability
AND authenticated application principal
AND principal-to-seat/role policy
AND current activation/intent fence
AND operation-specific authority policy
AND idempotency
```

Failure of any term refuses before mutation.

`activation_id`, `generation`, `operation_key`, `actor`, `seat`, `workspace_id`, model text, Slack text, and tool arguments are **not** authenticators.

## 7.2 Preferred authentication mode — OAuth/OIDC application identity

Preferred production design:

- Mastermind MCP endpoint is an OAuth-protected resource.
- The gateway validates a bearer access token issued by a reviewed authorization service.
- The validated claims include at minimum:

```text
iss
aud = mastermind-executive-mcp
sub = stable principal id
exp / nbf / iat
jti or equivalent replay identifier where supported
scope / role claims from the issuer
```

- Principal mapping is server-side, e.g.:

```text
workspace-sol-service  -> CEO_AGENT
chairman-chris         -> CHAIRMAN_INTERACTIVE
readonly-auditor       -> READONLY
```

- The Workspace Agent uses an **agent-owned/service connection** where the live product supports it; human interactive access uses an end-user identity where the live product supports it.
- Model-visible text cannot select the subject.
- Revocation/rotation is independent of the tunnel runtime key.

The authorization server is its own reviewed service boundary; OpenAI tunnel documentation states the authorization server is not automatically tunneled, so deployment must account for reachability without exposing the Executive MCP server itself.

## 7.3 Bounded fallback — connector-bound secret principal

If OAuth cannot yet be made reliable for the Workspace Agent, a narrow interim path may use a high-entropy connector-specific secret header **only after X0-A proves the required properties**.

Requirements:

- a unique secret per published connector/principal class;
- secret stored in the product connector configuration and Mastermind secret store, never in prompts, Git, tool arguments, model context, or logs;
- gateway stores/verifies a one-way representation where practical;
- independent rotation/revocation;
- no default/fallback secret;
- constant-time comparison;
- source IP/tunnel id never substitutes for the secret;
- a connector cannot select a stronger principal by sending `X-Principal: chairman` or similar;
- X0-A attempts cross-surface replay from Codex, Responses API, ordinary ChatGPT, another agent, and any other principal able to reach the same tunnel;
- if the secret becomes visible to model text or another principal, the path is rejected for production writes.

This is a fallback canary design, not automatic production approval.

## 7.4 Static tunnel-client headers are not caller identity

A header injected by `tunnel-client` itself is common to requests transiting that runtime and therefore may authenticate the local tunnel process to the MCP server, but **cannot distinguish Sol from another OpenAI-side caller using the same tunnel**.

It may be used as an extra transport integrity check, never as the executive principal.

## 7.5 Principal classes

V1 principal classes:

```text
READONLY
CEO_AGENT
CHAIRMAN_INTERACTIVE
ADMIN_OPERATOR   # local/offline administration; not model-routable
```

No principal class is inferred from prose or the model name.

## 7.6 Autonomous Sol write gate

A modifying Sol request requires:

```text
authenticated_principal == CEO_AGENT
AND activation.state is current/write-eligible
AND activation claim belongs to the expected logical route/generation
AND operation is inside CEO delegated decision category
AND operation-specific authority fence passes
AND operation_key is unused-or-idempotent
```

If the operation maps to a Chairman category, CEO_AGENT may create/update the canonical Chairman request only; it may not perform the reserved operation.

## 7.7 Chairman direct gate

`CHAIRMAN_DIRECT` is unavailable until X0-A/X1-B proves an authenticated `CHAIRMAN_INTERACTIVE` principal.

Even then, direct Chairman action is limited to a **typed pending canonical request** or separately reviewed direct-operation contract. Free-form chat text is never parsed as approval.

A Chairman decision checks:

```text
principal == CHAIRMAN_INTERACTIVE
request_id exists and is PENDING
decision applies to the exact current request generation / immutable refs
request not expired/superseded/cancelled
operation_key replay-safe
```

## 7.8 Production dependency

X5, X6, and X7 now depend on X1-B PASS. X0-A proving tunnel reachability without application identity is insufficient.

---

# 8. H1 — Harpoon explicitly disabled for Mastermind

The independent review is correct that `tunnel-client` is not "transport only" if Harpoon targets are configured.

For the Mastermind Executive MCP tunnel profile:

```text
harpoon_target_count == 0
```

is a load-bearing invariant.

Acceptance must prove:

- no `--harpoon.target`;
- no `HARPOON_TARGETS`;
- no Harpoon target in the effective profile;
- a `harpoon` channel invocation is refused/unsupported;
- tunnel profile digest/config receipt records the zero-target state;
- drift from zero invalidates X1-A/X1-B acceptance.

No convenience internal HTTP target is allowed on the Executive tunnel.

---

# 9. H2 — conversation-key ownership and rotation

Conversation continuity is useful only while it cannot reintroduce superseded cognition.

New invariant:

> At most one non-terminal CEO activation generation may own a `conversation_key`.

Rules:

- a continuation inside the **same current activation generation** may reuse its conversation key;
- supersession rotates the key;
- reasoning escalation that creates a successor activation rotates the key;
- scope drain/cancel/supersede rotates the key;
- material context invalidation rotates the key;
- a new root activation receives a new key by default;
- a stale/superseded run's conversation history is never trusted as canonical state by the successor.

X0-A adds an adversarial canary with two distinct triggers sharing one conversation key to observe provider behavior. Until proved safe, overlapping provider runs on one key are forbidden by Mastermind policy.

Canonical company state still comes from Executive/Agent OS evidence, not conversation history.

---

# 10. H5 — executive dissent independence fails closed

Phase 1F implementation-result review and E17 executive dissent are different controls.

For E17 policy-selected high-impact dissent, the required independence class is declared by deterministic policy before the critic is selected.

Suggested v1 classes:

```text
D1_DIFFERENT_WORKER
D2_DIFFERENT_ACCOUNT
D3_DIFFERENT_PROVIDER
```

Every dissent result records:

```text
critic_independence_required
critic_independence_achieved
primary_route_receipt
critic_route_receipt
verdict
```

If `achieved < required`:

```text
verdict = DISSENT_UNAVAILABLE
```

and the action follows policy to defer, retry on lawful independent capacity, or escalate. It can never be recorded `CLEAR` under degraded independence.

The critic has no mutation/veto authority. Its role remains read-only challenge evidence.

---

# 11. H3 — Workspace Agent trigger principal is an explicit dependency

The Workspace Agent API-trigger credential is modeled as a separate ChatGPT-workspace credential domain and as a principal/share dependency, not as a generic OpenAI API key.

Canonical logical fields:

```text
trigger_principal_id
workspace_id
agent_id / published route id
share_or_access_dependency
credential_version
issued_at / expires_at if observable
last_rotation_at
status
```

Required behavior:

- `401`: authentication/credential failure; no blind tight retry;
- `403`: permission/share/principal drift; **non-retryable as a transient** and raises an operator/Executive exception;
- `429`: provider rate limit; bounded retry/backoff;
- network ambiguity after request transmission: retry only with the same trigger idempotency identity where the live endpoint proves such semantics;
- agent share/audience change invalidates the published-route acceptance receipt.

A dedicated service-like workspace user may be preferred operationally if the product/account permits it, but X0-A must establish the actual supported principal model. The architecture does not invent a service account that the product does not provide.

---

# 12. H4 / M3 — provider run status may diagnose failure, never prove success

Provider telemetry remains non-authoritative for Executive completion.

But "advisory" is asymmetric:

- provider `completed` can never mark the Executive activation complete;
- provider `suspended`/approval-blocked, if observable, may raise a diagnostic exception and shorten claim/deadline reconciliation;
- provider `failed` may trigger reconciliation;
- a provider status never commits a business/executive outcome without the durable Executive transaction.

If the live beta surface exposes them, classify:

```text
APPROVAL_BLOCKED
DISPATCH_FAILED
RUN_FAILED
```

Retry rule:

- `DISPATCH_FAILED`: run is evidenced not to have started; same activation/idempotency identity may retry under bounds;
- `RUN_FAILED`: do not assume no effect. Reconcile canonical MCP outcomes/claim/operation keys first, then either close, advance generation, or deliberately retry;
- no observable run status: deadline/claim reconciliation remains correct without it.

X0-A determines whether this telemetry exists on the live account.

---

# 13. M4 — attention state is not a dispatch queue

The executive-attention relation may hold `OPEN/DEFERRED/ACTIVATED/...` and `revisit_at`, but it is forbidden from dispatching work.

Machine invariant:

```text
executive_attention_case
    MAY -> create/coalesce CEO activation through deterministic Wake Router
    MUST NOT -> create Job directly
    MUST NOT -> claim Job
    MUST NOT -> place worker/provider
    MUST NOT -> dispatch worker
    MUST NOT -> mutate company strategy
```

Any path from attention-case persistence directly to a worker Job is a duplicate-control-plane defect.

X3-A must ship a conformance test proving the attention module cannot import/call worker dispatch/placement/job-creation APIs except the single reviewed activation-creation seam.

---

# 14. M5 — credential trust domains are separated

The architecture now names four independent credential domains:

1. **Workspace Agent trigger token** — ChatGPT workspace credential; wakes the published Workspace Agent; scope/owner/share lifecycle specific to that product.
2. **Tunnel runtime key** — OpenAI Platform tunnel daemon principal; only Tunnels Read + Use for the exact tunnel; never admin CRUD.
3. **Tunnel administration key** — offline/operator control; Tunnels Read + Manage / applicable admin authority; never installed in the long-lived daemon.
4. **Executive MCP application principal credential** — OAuth bearer or connector-bound secret used by the gateway to authenticate `CEO_AGENT`, `CHAIRMAN_INTERACTIVE`, etc.; independent of the tunnel key.

Compromise of one domain does not automatically authorize another.

Each has separate:

- secret storage;
- rotation/revocation;
- audit receipt;
- least privilege;
- blast-radius statement;
- acceptance test.

---

# 15. Constitutional/protected-path enforcement

The earlier prose rule "Sol may not rewrite its constitution" is insufficient by itself.

Before X5/X7, the source-law layer must publish a machine-readable `executive_protected_paths` policy (home: `config/authority_map.yml` or a directly conformance-tested subsection of it) covering at minimum:

```text
research/MASTERMIND_CHARTER_V2.md
config/authority_map.yml
config/strategic_state.yml
AGENTS.md
CLAUDE.md
integrations/executive_mcp/**
ops/executive_os/**
.github/workflows/**
```

and the reviewed files that implement CEO wake, reasoning governance, application authentication, production write arming, and credential policy when those files exist.

Rules:

- autonomous CEO/COO/worker modifying tools do not receive write grants to these paths;
- a proposal to change them becomes a separate commission/change request;
- Chairman-reserved categories apply where the change alters authority/constitution/trust/autonomy;
- ordinary code-review/build paths cannot expand their own allowlist;
- tests assert the protected set cannot be widened by a Job payload, model label, or tool argument.

This converts constitutional self-modification from prose to an enforceable boundary.

---

# 16. Charter applicability clarification (M1)

The trading Charter remains the constitution for the system it names. Phase 1G must stop presenting every generalized orchestration rule as though the Charter literally specifies agent routing.

Ruling:

- where Phase 1G cites P7 (one source of truth per concept), P8 (earned/shadow-first autonomy), or shrink-only principles as an Executive OS design law, it must label the mapping as an **Executive OS adoption/extension of the Charter principle**, unless the Charter text directly governs the object;
- this adoption may never be used to invent new power;
- conflicts with literal Charter text escalate rather than being "interpreted" away;
- executive-specific authority is defined by the explicit source-law additions above, not by metaphorical extension of trading terminology.

---

# 17. Revised X0-A requirements

The existing X0-A matrix remains required and gains these rows:

1. Can any non-Sol OpenAI-side surface reach the same tunnel-backed MCP app/tunnel?
2. Does the local MCP server receive any trustworthy per-agent/per-user identity from the tunnel itself? Expected architectural assumption: **no**.
3. Are connector-configured `Authorization` and custom headers forwarded to the local MCP server on this exact Business workspace/tunnel path?
4. Can Workspace Agent app connections use an agent-owned/service identity for the custom MCP app on this workspace?
5. Can a human interactive connection use a distinct end-user OAuth identity against the same MCP resource?
6. Are app/connector secrets ever visible to model text, tool arguments, exported agent configuration, logs, or another workspace principal?
7. Can Codex, Responses API, another Workspace Agent, or ordinary ChatGPT invoke the same tunnel with no Executive application credential?
8. `conversation_key` behavior under two concurrent/distinct trigger events.
9. Trigger-token owner/principal, lifetime, rotation/revocation, and share/audience drift behavior.
10. `403` behavior when the token's user loses access/share.
11. Whether `suspended`, `dispatch_failed`, `run_failed`, run id, or any beta run-status telemetry is observable on the live account.
12. Whether a write approval can suspend/block an unattended Workspace Agent run.
13. Effective tunnel profile contains zero Harpoon targets.
14. Tunnel runtime key and tunnel admin key can be separated into distinct least-privilege principals.
15. Business app publication/update behavior: whether a changed MCP tool or auth config requires recreate/republish, and how the config receipt can detect drift.

No live result creates production write authority by itself.

---

# 18. Revised wave dependencies

The Workspace CEO path is now:

```text
G0 source-law adjudication
  ├─ source-law PR: seats + decision policy + priority semantics + protected paths + 1F rulings
  └─ PR #66 design adjudication
          |
          +--> X0-A live capability matrix
          |
          +--> X1-A private READONLY reachability
          |       |
          |       +--> X1-B application-principal authentication proof
          |
          +--> X2-A CEO mission/eval corpus
          +--> X2-B semantic-triage shadow evaluator
          +--> X3-A attention/wake/activation fixture design
                     |
                     +--> X4 reasoning-route proof
                     |
G1 + G2 + X1-B trusted application identity
                     |
                     +--> X5 bounded production write arm
                              |
W13/G9 -----------------------+--> X6 autonomous continuation/project initiation
                                      |
                                      +--> X7 sustained autonomous improvement
```

No X5/X6/X7 path depends on tunnel identity alone.

---

# 19. Required implementation commissions after G0

The refreshed commission set must include:

- **SOURCE-LAW-A:** `authority_map.yml` executive seats, decision categories, COO bounds, protected-path policy, conformance tests; Executive-contract/strategic-state prose corrections; Phase 1F §6 ruling record.
- **X0-A:** live Business Workspace capability/evidence matrix.
- **X1-A:** Secure MCP Tunnel + existing READONLY gateway reachability; zero Harpoon targets; no production writes.
- **X1-B:** gateway application authentication/OAuth-or-bounded-secret proof, principal mapping, rotation/revocation/replay tests.
- **X2-A:** CEO mission contract + prompt-injection/NO_ACTION/strategy-boundary corpus.
- **X2-B:** provider-neutral semantic triage shadow evaluator.
- **X3-A:** Executive Attention + Wake Router + activation claim + conversation-key ownership + non-dispatch proofs.
- **X4-A:** Reasoning Governor and published-route/Pro proof.
- **X5-A:** bounded production modifying tool census using authenticated application principal + activation/intent fence; immutable commission ratification; Chairman request/decision contract.

---

# 20. Re-review acceptance packet

The fresh reviewer does not need to redo the entire 5,000-line baseline unless it chooses to. The mandatory re-review packet is:

1. this adjudication;
2. the separate source-law PR diff and tests;
3. updated G0 acceptance index/evidence register;
4. updated PR #66 binding-file/precedence list;
5. X0-A results available at re-review time;
6. the original independent review for finding traceability.

Required determinations on re-review:

```text
B1 authority substrate: CLOSED | OPEN
B2 priority/source-of-truth split: CLOSED | OPEN
B3 Phase 1F §6 rulings: CLOSED | OPEN
B4 application principal / tunnel assumption: CLOSED | OPEN
H5 dissent fail-closed: CLOSED | OPEN
```

And explicitly:

```text
more than one lifecycle authority? YES|NO|UNRESOLVED
more than one production scheduler? YES|NO|UNRESOLVED
more than one company-strategy authority? YES|NO|UNRESOLVED
hidden semantic suppression authority? YES|NO|UNRESOLVED
Chairman authorization bypass? YES|NO|UNRESOLVED
stale/duplicate CEO write path? YES|NO|UNRESOLVED
autonomous constitutional self-modification path? YES|NO|UNRESOLVED
```

G0 may move to PASS only after the reviewer finds no remaining blocking architecture defect and the source-law prerequisites it relied on are present in the reviewed repository state.

---

# 21. Non-goals preserved

Nothing in this adjudication authorizes:

- production MCP writes;
- direct shell/SQL/tmux/credential access;
- autonomous merge/deploy/service control;
- autonomous live-capital execution;
- model-derived principal identity;
- Slack free-text approval;
- a new priority database;
- a new lifecycle database;
- a new scheduler;
- Grok as a control-plane authority;
- semantic demotion of hard attention;
- model self-editing of source law;
- bypass of Phase 1C-A or Phase 1F-B/C gates.

The independent review's strongest positive finding remains intact: the monotonic executive-attention pipeline and activation claim/fence model are retained. This adjudication supplies the missing authority/strategy/authentication substrate underneath them.