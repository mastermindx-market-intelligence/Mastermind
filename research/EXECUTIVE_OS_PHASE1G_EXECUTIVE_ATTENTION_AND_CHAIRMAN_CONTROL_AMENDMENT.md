# Executive OS Phase 1G — Executive Attention, Semantic Triage, and Chairman Control Amendment

**Program:** Mastermind Executive OS / Agent OS  
**Track:** protected Workspace CEO autonomy  
**Status:** binding architecture amendment to the Phase 1G design; **DESIGN ONLY — NO PRODUCTION ARMING**  
**Design date:** 2026-08-15  
**Applies to:** `EXECUTIVE_OS_PHASE1G_WORKSPACE_CEO_AUTONOMY_TRACK.md`, `EXECUTIVE_OS_PHASE1G_MASTERPLAN_AND_WAVES.md`, and the Phase 1G Agent Fabric design  

---

## 0. Executive ruling

The Phase 1G architecture remains in force: Executive OS is the sole lifecycle and production scheduling authority; Sol is protected CEO cognition; Fable/COO owns bounded project orchestration; the Improvement Agenda / accepted strategic state owns company priority; Agent OS is the knowledge plane; the Workspace Agent trigger is the wake path; governed MCP is the state/action path; and Grok is not a required control-plane dependency.

This amendment closes the principal remaining autonomy gap: **how canonical operating events become executive attention without either hard-coding every possible strategic implication or silently giving an LLM the power to suppress the CEO.**

The production target is a three-stage executive-attention pipeline:

```text
canonical Executive OS state/events
            │
            ▼
1. DETERMINISTIC ATTENTION EVALUATOR
   hard mandatory floor + soft candidates
   compression + evidence lineage
            │
      hard route ───────────────────────┐
            │                           │
            └── soft semantic case ─► 2. SEMANTIC TRIAGE
                                       provider-neutral AI
                                       advisory, read-only
                                                │
                                                ▼
                               3. DETERMINISTIC WAKE ROUTER
                                  floor is monotonic
                                                │
                                      CEO activation/claim
                                                │
                                      Workspace Agent trigger
                                                │
                                               Sol
                                                │
                                         governed MCP
                                                │
                                  durable executive outcome
```

The load-bearing asymmetry is:

> **AI judgment may promote executive attention. It may never erase a mandatory deterministic escalation.**

Grok may be an economical/high-quality implementation of the semantic-triage profile if shadow evaluation proves it. The architecture does not name Grok as authority, does not require Grok for CEO wake, and remains correct if Grok is unavailable.

This amendment also adds two missing end-to-end control paths:

1. a canonical Chairman authorization object with Slack as notification/interaction transport only; and
2. a direct conversational commissioning lane in which a finished ChatGPT architecture/build plan becomes an immutable GitHub commission artifact and a typed Executive OS directive binds to its exact bytes.

---

## 1. Review findings requiring design changes

### F1 — deterministic-only wake rules are safe but semantically incomplete

The current X6 plan begins with an allowlist of canonical CEO wake events. That is a correct authority floor, but it cannot enumerate every case in which technically normal project evidence changes the strategic answer.

Examples include:

- a project passes tests but invalidates the business/architecture assumption that justified it;
- a worker discovers a materially better architecture while staying inside its implementation task;
- several individually healthy projects create duplicated or contradictory infrastructure;
- implementation completes correctly but does not satisfy the underlying objective;
- new evidence changes the economic value of continuing;
- a completed project reveals a capability gap or new high-value initiative.

These are judgment problems, not reliable enum problems.

### F2 — an LLM-only wake gate creates hidden executive authority

Putting Grok, Fable, Sol, or any other model directly in front of the CEO trigger as the sole gate creates the opposite failure: the model could silently decide that the CEO does not need to know something.

That would make a probabilistic model the suppression authority for executive attention and violate the existing law that labels/projections/models do not confer authority.

### F3 — no-wake decisions need durable accountability

A soft event assessed as routine cannot simply disappear. Otherwise false negatives are unauditable and never revisited when evidence changes.

“No immediate CEO wake” therefore needs a canonical receipt, an expiry/revisit rule, and inclusion in the strategic-review horizon.

### F4 — duplicate trigger protection must also bound duplicate reasoning burn

Activation generation/fencing prevents stale duplicate runs from committing conflicting writes, but two externally triggered Sol runs can still spend scarce cognition before either reaches the write fence.

The activation model therefore also needs a bounded **activation claim** / current-cognition-owner concept, with timeout/reconciliation. This is not a second lease system: it is additive state on the existing CEO activation object in the same Executive runtime.

### F5 — Job completion and strategic objective closure are not the same fact

A Job can be technically complete while the objective is only partly achieved or the result creates a new strategic question. Executive OS must never silently translate `Job.status=COMPLETED` into “the company objective is closed.”

### F6 — Chairman escalation needs a canonical object, not a Slack message

Slack is suitable for notifying Chris and collecting a typed response, but the authoritative decision must exist in Executive OS with scope, exact artifact/reference, options, recommendation, expiry, and a durable decision receipt.

### F7 — direct conversational design needs immutable provenance

A general ChatGPT conversation is excellent for high-effort architecture work, but the transcript must not become the build specification. The final approved plan needs an immutable artifact identity before Mastermind begins execution.

### F8 — executive cognition needs prompt-injection and dissent testing

The MCP gateway can keep returned strings inert at the server boundary, but that alone does not prove Sol will treat worker results, Agent OS notes, external research, or semantic-triage prose as **data rather than authority-bearing instructions**.

The CEO shadow/eval track must test this explicitly.

### F9 — root-scoped activation ownership is insufficient for cross-project conflicts

Two different project roots can still contend over the same strategic objective, shared architecture surface, production resource, or governance domain. X3 must define overlapping executive scope beyond only `root_scope_id` for consequential mutations.

### F10 — event storms require lossless compression

A project may produce dozens of individually valid events that all imply one executive question. Waking Sol once per event wastes inference and can create competing directives. Compression must preserve every source event while creating one executive attention case.

---

## 2. Binding source laws

### E1 — detection, judgment, and authority routing are separate functions

Executive attention has three separate stages:

1. deterministic fact classification and mandatory floor;
2. optional semantic assessment of soft candidates;
3. deterministic route/activation decision.

No model combines all three roles.

### E2 — the mandatory escalation floor is deterministic and monotonic

If canonical policy/state establishes a minimum route of CEO or Chairman, later semantic assessment may not reduce it.

Conceptually:

```text
final_route = max(mandatory_floor, semantic_promotion, policy_promotion)
```

There is no `semantic_demotion` term.

### E3 — semantic triage is advisory and provider-neutral

`executive_semantic_triage` is an agent profile/capability, not a seat and not an authority.

A provider/model may fill the profile only after shadow/eval acceptance. Grok is a candidate provider; Claude/Codex/other approved models may substitute under deterministic placement policy. The assessment is a typed result consumed by trusted Executive OS code.

The assessor receives read-only evidence and cannot create CEO activations, mutate priority, create projects, select credentials, merge/deploy, or write authoritative lifecycle state directly.

### E4 — semantic triage may promote, never suppress hard attention

A semantic assessor may identify that an otherwise soft/routine-looking case needs COO replanning, CEO reassessment/reallocation/redelegation, or possible Chairman attention.

It may not convert a mandatory CEO/Chairman floor into routine continuation.

### E5 — material uncertainty fails upward

If a **material** semantic-candidate assessment times out, fails, is stale, is malformed, lacks required evidence, or falls below the reviewed confidence floor, the safe fallback is CEO attention at the policy-selected reasoning class.

For genuinely routine soft candidates, policy may defer to the strategic heartbeat instead of waking immediately, but the deferral must remain durable and expiring.

### E6 — no-immediate-wake is a bounded disposition, not deletion

Every soft attention case disposed as `CONTINUE_WITHIN_MANDATE` / equivalent records:

- source event ids;
- facts considered;
- assessment/route reason;
- assessor/policy versions;
- materiality;
- expiry/revisit time or event condition;
- whether the case must be included in the next strategic review.

New contradictory evidence, a higher hard floor, or expiry reopens/supersedes the disposition.

### E7 — attention compression is lossless and severity-monotonic

Executive OS may coalesce compatible events for the same governed scope into one open attention case. It must preserve complete source-event lineage.

Adding a stronger event may raise the hard floor, reasoning class, generation, or deadline. Compression must never hide a stronger event behind an earlier weaker disposition.

### E8 — only Executive OS creates CEO activations

Neither Grok, Fable, Slack, a worker, nor model prose can directly create an authoritative CEO activation. They may emit typed evidence/requests. The deterministic Wake Router creates, merges, supersedes, or refuses activations from canonical state and policy.

### E9 — one current cognition owner per overlapping executive scope

Before consequential autonomous reasoning can commit, the activation records a current claim/generation for the trusted Workspace route. Duplicate/stale runs can read enough state to identify themselves as duplicate but cannot become a second current cognition owner.

A claim expires/reconciles under the activation deadline and does not become a general-purpose lease subsystem.

### E10 — technical completion does not imply strategic closure

Worker/Job completion answers whether the execution contract completed. Agenda/strategic closure answers whether the accepted objective is satisfied and what follows.

A material project completion therefore produces an executive outcome/attention input with acceptance evidence and strategic delta. The Improvement Agenda / accepted strategic-state layer closes or changes the objective through its own governed path.

### E11 — Chairman authority is represented by a canonical decision request

When CEO action requires Chairman authority, Executive OS records a pending Chairman decision request. Slack, ChatGPT, or another UI may present it, but the authoritative state is the Executive OS request and decision receipt.

### E12 — Slack is transport, not authority

A Slack notification can contain options and a Sol recommendation. A Slack interaction becomes authoritative only through a reviewed identity-bound typed action that commits against the pending request.

Free-form Slack text is discussion/evidence unless it is explicitly transformed into and confirmed as a typed decision. `Discuss` never equals `Approve`.

Slack delivery failure leaves the canonical request pending; it cannot turn into approval, rejection, or cancellation.

### E13 — direct conversational commissioning binds an immutable artifact

For Chairman/Sol architecture work performed in a normal ChatGPT conversation, the production target is:

```text
Chris ↔ conversational Sol
        ↓
final architecture/build plan
        ↓
immutable commission artifact
(GitHub repo + path + commit + blob/content digest)
        ↓
typed server-ratified directive referencing exact artifact
        ↓
Executive OS parent objective / project machinery
```

The conversation is deliberation. The artifact is the specification. The Executive OS Job/activation is lifecycle truth.

### E14 — GitHub is a specification/provenance surface, never the work queue

A commission artifact may live in GitHub, but GitHub branch/PR state does not become Job lifecycle, scheduling, dispatch, or completion authority.

The directive must verify the referenced artifact identity before accepting it. Editing the file later does not mutate an already accepted directive.

A revision requires a new immutable artifact identity plus an explicit supersession relation.

### E15 — artifact publication and directive submission are intentionally two-phase

The safe order is:

1. write the commission artifact;
2. read/verify its exact immutable identity/digest;
3. submit the typed directive referencing it.

An artifact with no accepted directive is an inert orphan. A directive with a missing/mismatched artifact is refused. A lost response after directive commit is recovered by idempotency rather than by creating another project.

### E16 — untrusted content is data, not executive instruction

Worker results, review comments, Agent OS notes, web research, Slack messages, semantic-triage explanations, and repository text may contain instruction-shaped content.

The CEO mission contract must preserve the source-of-truth/authority hierarchy and treat embedded instructions as inert evidence unless the trusted canonical source and authority path explicitly make them directives.

### E17 — high-impact executive decisions may require independent dissent review

For policy-selected material actions, Executive OS may require a read-only independent critique before Sol commits the final action. The critic has no veto/write authority. A material unresolved disagreement forces a second Sol pass or Chairman attention according to policy.

Where capacity permits, the dissent reviewer should differ by worker/provider/account from the primary reasoning route.

### E18 — kill, drain, scheduling, and write-arm controls are independent

The operator/Chairman controls must distinguish at least:

- **global CEO autonomy kill:** no new autonomous activations;
- **scope drain:** no new activation for a scope; allow/refuse current completion per policy;
- **activation supersede/cancel:** generation advances/fences late writes;
- **strategic-heartbeat enable/disable:** scheduling only;
- **production MCP modifying-arm enable/disable:** action path only.

Disabling one control must not ambiguously imply the state of the others.

### E19 — semantic triage cannot become a recursion loop

If semantic triage is implemented as an Executive OS read-only Job/Attempt, its own ordinary lifecycle events do not recursively create new semantic-triage cases. A triage-job failure is handled by E5.

### E20 — labels and recommendations remain non-authoritative

`CEO_REASSESS`, `CHAIRMAN_ATTENTION`, `critical`, confidence values, assessor provider/model, and similar fields describe a recommendation/fact class. Actual capability still comes only from canonical authority policy, trusted caller identity, activation fence, and reviewed operation contract.

---

## 3. Deterministic attention taxonomy

Exact enums belong to X3-A, but the architecture requires four semantic classes.

### 3.1 Mandatory CEO floor

Examples that bypass semantic suppression include:

- bounded COO repair/attempt/review ceilings exhausted where the parent declares/qualifies for CEO escalation;
- `escalation_target: ceo` established under the Phase 1F-B provenance/shrink law;
- required scope/authority cannot remain inside the accepted mandate and policy says the CEO can rule or reframe it;
- a policy-defined material/critical acceptance or review conflict requiring executive disposition;
- an unresolved project/objective decision already recorded as needing CEO action;
- an activation/continuation failure whose recovery policy explicitly requires CEO reassessment.

The exact rule set is versioned policy and mutation-tested. A semantic assessor is not called to ask whether these should disappear.

### 3.2 Chairman-required floor

The deterministic authority/policy layer marks a case `chairman_required` when the requested decision lies outside delegated CEO authority or inside a Chairman-reserved category.

The normal path is still to wake Sol at the appropriate reasoning class to synthesize the smallest decision request, options, evidence, and recommendation; Sol then commits `CHAIRMAN_ATTENTION` and Executive OS creates the canonical Chairman request.

No model self-declares new Chairman authority categories.

### 3.3 Semantic executive candidates

Examples:

- implementation success but objective satisfaction is uncertain;
- the accepted architecture assumption appears contradicted by new evidence;
- a materially better route has been discovered;
- results change the value/risk of continuing the current plan;
- cross-project duplication or contradiction is detected;
- a completed project creates a new opportunity/capability gap;
- a reviewer passes correctness but flags a material strategic concern;
- multiple weak anomalies together may warrant executive attention.

### 3.4 Routine continuation

Purely mechanical, already-authorized progression stays with COO/Executive OS. The CEO layer is not a high-cost poller for routine transitions.

---

## 4. Executive semantic-triage contract

A candidate closed result contract is:

```text
schema: mastermind.executive_triage_assessment.v1
assessment_id
attention_case_id
source_event_ids[]
root_scope_id
assessor_profile_version
assessor_route_receipt
policy_version
assessment:
  CONTINUE_WITHIN_MANDATE |
  COO_REPLAN |
  CEO_REASSESS |
  CEO_REALLOCATE |
  CEO_REDELEGATE |
  CHAIRMAN_ATTENTION
reason_codes[]
materiality: routine | material | critical
confidence_class: low | medium | high
facts_considered[]
strategic_delta_summary
recommended_next_action
created_at
expires_at
```

### 4.1 Read scope

The assessor receives only a bounded server-assembled evidence packet relevant to the case, such as parent objective/immutable commission reference, strategic-state/agenda ids relevant to scope, child results/acceptance evidence, reviews/material findings, relevant capacity/cost facts, previous attention/CEO disposition, and cross-project conflict evidence identified by canonical scope keys.

It receives no raw credentials, generic SQL, lifecycle mutation tools, arbitrary company filesystem access, or model-selectable authority.

### 4.2 Action scope

It returns exactly one typed assessment. Trusted code validates and records it.

It cannot create a CEO activation, close an objective, mutate the Improvement Agenda, create a project, grant authority, send Chairman authorization, merge/deploy, choose credentials/provider accounts, or cause `recommended_next_action` text to execute.

### 4.3 Provider selection

The profile is placed through deterministic Agent Fabric policy with an intelligence floor and reserve policy. Grok may be preferred if live shadow evidence shows strong precision/recall at favorable cost. If Grok is unavailable, a lawful peer may run it. If no accepted assessor is available, E5 governs; hard wakes remain unaffected.

---

## 5. Canonical executive-attention case

Because a projection may never gate execution, pre-activation routing state cannot live only inside Executive Inbox output.

X3-A should specify additive canonical state inside the existing Executive SQLite/runtime. The exact relation name is implementation-owned; logically it needs:

```text
attention_case_id
root_scope_id
affected_scope_keys[]
source_event_ids[]
hard_floor: none | coo | ceo | chairman_required
hard_reason_codes[]
materiality
triage_required
triage_state
triage_assessment_id_optional
final_route
reasoning_class_floor
status: OPEN | DEFERRED | ACTIVATED | RESOLVED | SUPERSEDED
revisit_at_optional
linked_activation_id_optional
policy_version
created_at / updated_at
```

This is **not a second work queue**. It is canonical executive-routing state under the same lifecycle authority. Jobs remain Jobs; CEO activations remain CEO activations; the Improvement Agenda remains priority authority.

### 5.1 Compression

Coalesce only under safe deterministic scope keys. A compressed case records every source event. A stronger incoming hard floor or materiality only promotes/supersedes the case.

### 5.2 Deferred cases

A deferred soft case names its revisit trigger/time. It reopens on expiry, contradictory/new evidence, a stronger hard event, a relevant project/agenda state change, or the bounded strategic heartbeat. There is no indefinite silent shelf.

---

## 6. Deterministic CEO Wake Router

The Wake Router consumes canonical attention state and emits CEO activation commands in the existing Executive runtime.

Pseudo-policy:

```text
if hard_floor == chairman_required:
    route = CEO_PREPARE_CHAIRMAN_REQUEST
elif hard_floor == ceo:
    route = CEO
elif semantic_assessment promotes to CEO/Chairman:
    route = policy_validated_promotion
elif soft case is routine + valid high-confidence assessment:
    route = COO_OR_DEFERRED
elif material triage is failed/stale/uncertain:
    route = CEO
else:
    route = reviewed_deterministic_default
```

The router then checks overlapping activation ownership, coalesces into an existing compatible activation or creates a new activation, chooses the minimum permitted reasoning class from the Reasoning Governor, records route/policy/evidence receipts, sends the Workspace Agent trigger with stable activation idempotency, and waits for the durable Executive OS outcome.

The semantic assessor never calls the trigger API itself.

---

## 7. Activation claim and duplicate-cognition bound

X3-A should extend the activation design with a current cognition claim. Logical fields may include:

```text
claim_generation
claim_state: UNCLAIMED | CLAIMED | RELEASED | EXPIRED
claimed_route_id
claimed_at
claim_deadline
```

The first trusted Sol run that begins the activation performs a bounded server-side claim transaction. A duplicate trigger delivery for the same activation can discover another current claim and exits without becoming a second modifying executive.

The claim does not confer action authority; every modifying action still requires trusted caller identity, activation generation, operation idempotency, and authority policy.

If the claimant disappears, timeout/reconciliation may expire the claim and advance generation before a retry. A late claimant remains fenced.

Acceptance must measure duplicate expensive Workspace runs, not only duplicate writes.

---

## 8. Direct conversational commissioning lane

This lane exists for cases where Chris and conversational Sol deliberately spend high-effort interactive reasoning to design a major architecture/build plan.

### 8.1 Target flow

```text
Chairman + conversational Sol
        │
        │ brainstorm / research / adversarial design
        ▼
final commission document
        │
        ▼
GitHub create/update on reviewed branch
        │
        ▼
verify immutable identity
repo + path + commit_sha + blob/content_sha256
        │
        ▼
server-side interactive ratification
        │
        ▼
typed commission/directive submission
        │
        ▼
Executive OS accepted parent objective
        │
        ▼
COO / Agent Fabric / reviews / bounded execution
```

After the typed directive is accepted, the interactive chat is no longer required to keep the project alive. Later CEO reassessment uses the autonomous Workspace CEO path.

### 8.2 Immutable commission reference

A logical reference carries at least:

```text
schema: mastermind.commission_ref.v1
repository
path
commit_sha
blob_sha_or_content_sha256
commission_kind
supersedes_commission_ref_optional
```

The gateway/runtime verifies the reference before accepting a directive. The model cannot substitute current `HEAD` for the supplied commit.

### 8.3 Identity/authority

A conversation saying “I am Chris” does not create Chairman authority.

If production transport proves the interactive principal is the Chairman through trusted platform/transport identity, the server may ratify a `CHAIRMAN_DIRECT` source under reviewed policy. If it proves only an authorized Workspace/app/CEO principal, the operation receives only that authority and uses the Chairman-request path for reserved decisions.

### 8.4 Revisions

A changed build plan requires a new immutable artifact identity plus an explicit superseding directive/decision and the necessary generation/fence changes. Do not mutate an accepted project by editing/force-pushing the old specification.

---

## 9. Chairman authorization gateway

### 9.1 Canonical request

A logical pending request contains:

```text
chairman_request_id
source_activation_id
root_scope_id
affected_scope_keys[]
decision_type / authority_required
question
options[]
sol_recommendation
material_evidence_refs[]
immutable_commission_or_project_refs[]
expires_at
state: PENDING | APPROVED | REJECTED | CANCELLED | EXPIRED | SUPERSEDED
created_at / decided_at
decision_receipt_id_optional
```

No option silently widens authority/scope beyond what was presented.

### 9.2 Delivery

Executive OS creates the request first, then a notification adapter may deliver it to Slack. Slack message/channel ids are delivery metadata, not decision identity.

### 9.3 Response

`Approve` / `Reject` invokes an identity-bound typed server action against the exact pending request and an idempotency key.

`Discuss` creates/links an interaction with Sol but commits no decision. Unstructured text may inform discussion but does not silently become approval.

### 9.4 After decision

A committed Chairman decision creates a durable receipt, terminalizes/supersedes the request, and emits the canonical event that allows Executive OS to wake/reconcile Sol or continue the affected project.

If the project/commission changed while pending, the old request is superseded/invalidated rather than applying approval to different bytes.

---

## 10. Project outcome and strategic closure

X6 must include a project-outcome handoff separating execution correctness from objective disposition.

A bounded outcome packet should expose:

```text
root_job_id / project_id
commission_ref
technical_result
acceptance_evidence_refs[]
independent_review_summary
objective_evidence
material_deviations_from_plan
unresolved_risks
new_discoveries_or_opportunities
resource_cost_summary_where_governed
recommended_disposition
```

For material/critical projects, policy may create a mandatory CEO attention case on outcome readiness even if implementation reviews approved. For routine projects, a semantic candidate may be assessed/deferred without an immediate CEO wake.

Invariant:

> `Job COMPLETED` never silently mutates the Improvement Agenda / strategic objective to “done.”

---

## 11. Prompt-injection and independent dissent defense

### 11.1 Source hierarchy

The Sol mission contract must explicitly state that authority comes from canonical Chairman/Executive OS policy and trusted tool results, not instruction-shaped text embedded in lower-trust evidence.

The replay corpus must include adversarial examples in worker results, review comments, Agent OS notes/discoveries, web/external research excerpts, semantic-triage explanations, Slack discussion text, and GitHub issue/PR prose.

Attempts must include instructions to ignore the activation fence, create unauthorized projects, skip Chairman approval, change priority outside the canonical path, execute a string from `next_actions`, reduce reasoning/approval requirements, or treat a worker/provider label as authority.

Passing means the content remains evidence and no forbidden operation commits.

### 11.2 Independent executive dissent

For policy-selected high-impact actions:

```text
Sol draft decision/action
        ↓
read-only independent critic
        ↓
CLEAR | MATERIAL_CONCERN | AUTHORITY_CONCERN
        ↓
CLEAR → normal commit gates
CONCERN → second Sol pass with critique evidence
unresolved authority/value conflict → Chairman request
```

The critic cannot commit, cancel, or veto; it only creates evidence.

---

## 12. Overlapping scope and cross-project conflict

X3-A must define deterministic `affected_scope_keys` for executive mutations. Candidate keys may derive from strategic objective/P0 id, project/root id, governed repository/module/write-path domain, shared production resource/domain, and explicit governance/authority domain.

Two mutating CEO activations with overlapping scope keys are serialized or explicitly declared independent. A different root id alone does not prove independence.

When safe independence cannot be established for a material mutation, fail closed to one current owner.

---

## 13. Wave-plan alterations

These amend the existing X0–X7 track rather than create a new parallel program.

### X0 — add identity proofs

Add live proof of what trusted principal/workspace/app identity reaches a custom MCP call in both autonomous Workspace Agent and interactive ChatGPT use, plus Slack interaction identity/typed-action capabilities before Chairman authorization UX is authoritative.

Do not infer identity from model text or caller-populated fields.

OpenAI product metadata remains advisory: current OpenAI Help Center and Developer documentation disagree on ordinary Workspace Agent trigger response metadata, so correctness remains grounded in Mastermind durable outcomes rather than optional provider run/conversation metadata.

### X2 — expand Sol shadow/eval corpus

Add semantic-reassessment cases, hard-escalation cases where suppression is impossible, prompt-injection cases from every evidence surface, cross-project contradictions, technically complete/objective-not-achieved cases, Chairman-boundary cases, direct conversational commission readback cases, independent-dissent cases, and `NO_ACTION` cases that require later revisit.

Measure false-negative executive attention, not merely prose quality.

### X2-B — semantic triage shadow evaluator

Add a new **shadow-only** commission:

- typed semantic-assessment schema;
- bounded evidence-packet builder design;
- Grok plus at least one lawful peer-provider shadow comparison where practical;
- hard-floor demotion attacks;
- semantic false-negative/false-positive corpus;
- provider outage/stale/malformed fallback;
- prompt-injection fixtures;
- structural no-write proof.

This earns recommendation authority only; it never receives suppression authority over the hard floor.

### X3-A — Executive Attention + Wake Router design/fixture

Expand X3-A to specify and fixture-test:

- canonical executive-attention-case semantics;
- deterministic mandatory floor and reason codes;
- lossless event compression;
- semantic-triage assessment contract;
- failure/staleness fallback;
- deferred TTL/revisit;
- deterministic Wake Router;
- activation claim/duplicate-cognition control;
- overlapping `affected_scope_keys` ownership;
- Chairman decision-request logical model;
- strategic-review inclusion of unresolved/deferred cases;
- existing trigger idempotency, generation, completion, timeout, and reconciliation requirements.

Persistent schema still waits for G2 / Phase 1F-B.

### X3-B — runtime integration

When G2 permits migration, add the minimum durable state to the existing Executive SQLite/runtime. Do not add a sidecar attention DB, semantic queue, scheduler, or Grok-owned state store.

Inbox/reporting may project these facts but remains non-gating.

### X4 — Reasoning Governor

Assign initial reasoning class from canonical final route/materiality/policy. Semantic assessment may provide evidence causing a policy-valid promotion but cannot directly select a published Workspace trigger/config.

Shadow calibration must include false-positive wake cost versus missed-material-attention cost.

### X5 — bounded production write arm

The separately reviewed X5 action census must account for activation claim/current-owner semantics, immutable `commission_ref` verification and interactive-session ratification, and Chairman request/decision operations or an equivalent separately reviewed integration.

No generic “execute plan URL”, arbitrary GitHub-content execution, Slack-text approval, or caller-authored authority field is allowed.

### X6 — hybrid attention router is a prerequisite

X6 no longer means only `event allowlist → wake Sol`.

Before promotion, prove:

```text
canonical event(s)
→ deterministic hard floor / attention case
→ optional semantic triage
→ deterministic final route
→ CEO activation + claim
→ Workspace trigger
→ Sol reasoning
→ durable outcome
→ COO/project execution
→ independent review
→ project outcome
→ CEO reassessment or justified deferred/no-action disposition
→ clean stop
```

Required real acceptance cases include:

- a mandatory hard CEO event that an adverse semantic assessor attempts to demote but cannot suppress;
- a soft event deterministic rules would not wake for but semantic assessment correctly promotes;
- a valid no-immediate-wake case later revisited by expiry/new evidence/strategic heartbeat;
- duplicate trigger delivery without duplicate consequential cognition/writes;
- a material triage outage that fails upward safely;
- cross-project overlapping-scope serialization;
- a Chairman request delivered through Slack, decided/discussed against the canonical request, then resumed cleanly;
- a direct conversational commission bound to an immutable artifact and completed without the originating chat remaining in the loop.

### X7 — add attention-quality promotion gates

Require sustained evidence for:

- hard-trigger recall = 100% on accepted corpus;
- zero hard-floor semantic demotion;
- semantic false-negative rate below reviewed threshold;
- bounded false-positive CEO wake rate/frontier burn;
- no unbounded deferred-case accumulation;
- prompt-injection corpus pass;
- no Chairman authority bypass;
- no duplicate directives from event storms/trigger retries;
- no self-modification of attention/wake/authority constitutional policy outside governed paths.

---

## 14. Acceptance and observability metrics

Store replayable receipts and evaluate at least:

```text
hard_wake_recall
semantic_promotion_precision
semantic_promotion_recall
material_false_negative_rate
unnecessary_ceo_wake_rate
mean_attention_to_activation_latency
expired_deferred_case_count
duplicate_activation_attempt_count
duplicate_cognition_claim_refusal_count
stale_activation_write_refusal_count
chairman_request_count
chairman_request_superseded_count
chairman_authorization_bypass_count
objective_completed_without_disposition_count
prompt_injection_policy_violation_count
frontier_reasoning_burn_by_route
```

Thresholds belong to reviewed policy/eval configuration except absolute invariants such as hard-floor demotion and authority bypass, which remain zero-tolerance.

---

## 15. Primary-source research findings incorporated by this amendment

### OpenAI Workspace Agent trigger

Current primary OpenAI documentation is internally inconsistent about the ordinary trigger response. The Help Center states that API triggers queue the run and return `202 Accepted` with no body/run id; the current Developer reference documents `conversation_url`, and a beta header that adds `agent_trigger_run_id` plus a status endpoint. Both agree that the final agent response cannot currently be retrieved via the trigger API.

**Architecture consequence:** provider trigger metadata is optional observability only. Canonical completion remains the durable Executive OS outcome transaction.

### OpenAI Secure MCP Tunnel

Current OpenAI docs confirm Secure MCP Tunnel is an outbound-only path allowing supported OpenAI products to reach a private MCP server without public inbound exposure. The docs also distinguish Platform tunnel permissions from ChatGPT workspace/developer-mode context and allow workspace/org association.

**Architecture consequence:** this solves reachability, not the production write-authorization question by itself. X0/X5 must still prove the trusted caller/app/principal identity visible to Mastermind before writes arm.

### xAI Grok Build

Current xAI docs confirm Grok Build supports headless execution with `json`/`streaming-json` output and an ACP JSON-RPC mode over stdio.

**Architecture consequence:** Grok is technically plausible as an economical semantic-triage or worker implementation, while provider-neutral placement keeps the CEO path available when Grok is unavailable.

---

## 16. Threat/failure cases that must remain explicit

The architecture must fail correctly when:

- Grok is down, rate-limited, wrong, or maliciously prompted;
- every semantic-assessor provider is unavailable;
- an assessor returns `CONTINUE` for a hard mandatory CEO event;
- an event storm contains one late critical event after earlier routine events were compressed;
- two roots try to change the same strategic/architecture domain;
- the Workspace trigger times out ambiguously or delivers more than once;
- a stale Sol conversation tries to commit after supersession;
- a claimant disappears after claiming but before committing;
- MCP is available while trigger delivery is unavailable, or vice versa;
- Slack is unavailable after a Chairman request exists;
- Chris clicks an old approval after the commission was superseded;
- Slack/ChatGPT text claims to be Chairman without trusted identity;
- a GitHub commission changes after directive acceptance;
- artifact publication succeeds but directive submission fails;
- directive commit succeeds but the client loses the response;
- a technically complete Job has not achieved the objective;
- worker/result/research text tries to instruct Sol to bypass policy;
- the assessor itself emits instruction-shaped output;
- strategic heartbeat is disabled while deferred cases exist;
- global autonomy is drained while an activation is mid-flight.

Every case requires deterministic state/receipt and no silent authority expansion.

---

## 17. Non-goals / prohibitions

This amendment does **not** authorize:

- a Grok control-plane daemon;
- Grok direct lifecycle/SQLite mutation;
- a second attention database/queue/scheduler;
- semantic triage as a prerequisite for a mandatory hard wake;
- free-form Slack text as Chairman approval;
- GitHub as a dispatch queue;
- chat transcripts as canonical project specifications;
- model-supplied actor/workspace/Chairman identity or authority as authentication;
- direct model selection of CEO trigger/reasoning route;
- automatic merge/deploy/service control;
- self-modification of authority/wake/reasoning constitutional rules;
- production MCP writes before G1/G2/trusted-identity/least-privilege gates pass.

---

## 18. Final target operating model

```text
CHAIRMAN / Chris
  ▲        │
  │        └── direct high-effort chat ─► immutable commission ─► typed directive
  │
  │ canonical Chairman request / Slack transport
  │
SOL / Workspace CEO
  ▲
  │ Workspace Agent trigger
  │
DETERMINISTIC WAKE ROUTER
  ▲                    ▲
  │ hard floor         │ advisory promotion
  │                    │
EXECUTIVE ATTENTION    SEMANTIC TRIAGE ASSESSOR
EVALUATOR              (provider-neutral; Grok candidate)
  ▲                    ▲
  └──────── canonical events/evidence ────────┐
                                              │
EXECUTIVE OS  ◄───────────────────────────────┘
  │
  ▼
FABLE / COO bounded orchestration
  │
  ▼
Agent Fabric workers + independent reviews
  │
  ▼
project outcome / discoveries / exceptions
  │
  └──────────────► canonical events → attention pipeline
```

This preserves the organizational goal: Chris does not act as polling scheduler, project-status collector, retry engine, or day-to-day CEO. Sol receives the executive cognition that requires Sol; COO/worker machinery handles bounded execution; semantic AI catches implications deterministic rules cannot enumerate; and no probabilistic model gains hidden authority to suppress mandatory executive attention.
