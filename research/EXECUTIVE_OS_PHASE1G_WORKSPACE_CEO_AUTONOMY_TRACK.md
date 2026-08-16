# Executive OS Phase 1G — Workspace CEO Autonomy Track

**Program:** Mastermind Executive OS / Agent OS  
**Track:** protected Workspace CEO autonomy  
**Status:** architecture and commissioning amendment; **DESIGN ONLY — NO PRODUCTION ARMING**  
**Evidence date:** 2026-08-15  
**Companion masterplan:** `research/EXECUTIVE_OS_PHASE1G_MASTERPLAN_AND_WAVES.md`  
**Companion fabric design:** `research/EXECUTIVE_OS_PHASE1G_AGENT_FABRIC_MASTER_DESIGN.md`  
**Companion infrastructure design:** `research/EXECUTIVE_OS_PHASE1G_INFRASTRUCTURE_DESIGN.md`  
**Workspace evidence register:** `research/EXECUTIVE_OS_PHASE1G_WORKSPACE_CEO_EVIDENCE_REGISTER.md`  
**Existing MCP boundary:** PR #64 / `docs/EXECUTIVE_MCP.md`  

---

## 0. Executive decision

Mastermind will treat the ChatGPT Business Workspace Agent named for the Sol CEO seat as a protected, externally awakenable executive cognition surface — **not** as a worker pool, not as a polling daemon, not as a scheduler, and not as a second control plane.

The canonical runtime remains Executive OS. The canonical priority source remains the Improvement Agenda. Agent OS remains the knowledge plane. The Workspace CEO reasons over canonical state and may submit only reviewed, typed executive actions back into Executive OS.

The production target is:

```text
Chairman / approved constitutional state
                 │
                 ▼
        Mastermind / Executive OS
        canonical state + event engine
        authority + reasoning governor
        scheduler + CEO activation ledger
                 │
                 │ Workspace Agent API trigger
                 ▼
       Sol CEO Workspace Agent
                 │
                 │ private governed MCP
                 ▼
        Executive MCP gateway
                 │
                 ▼
           Executive OS
                 │
                 ▼
       COO / leaders / workers
                 │
                 └── canonical events ──► next CEO wake when policy requires
```

There is no mandatory Grok hop in this control loop.

Grok remains useful as an optional xAI worker/specialist pool under the Agent Fabric. A Grok outage, quota limit, or account problem must not prevent Executive OS from waking the CEO.

---

## 1. Architectural clarification: four different responsibilities

The design separates four functions that must not collapse into one agent.

### 1.1 Executive OS — organization and authority

Executive OS owns:

- durable Job / Attempt / Worker lifecycle;
- canonical events and receipts;
- accepted objectives and project state;
- authority checks and write fences;
- capacity and placement state;
- CEO activation state and activation fencing;
- deterministic reasoning-class policy;
- recurring strategic-review scheduling;
- continuation / retry / timeout policy;
- audit and recovery state.

No model may become the authority for whether an action happened.

### 1.2 Sol Workspace Agent — CEO cognition

The Workspace Agent owns bounded executive judgment:

- strategic synthesis;
- architecture and design reasoning;
- deciding whether an event requires action;
- proposing or initiating projects within delegated CEO authority;
- determining what should be researched or built next;
- evaluating results and redirecting projects;
- requesting deeper reasoning when the initial class is insufficient;
- escalating to Chairman when the issue is authority, objective, taste, risk preference, or constitutional doctrine rather than computation.

Its chat transcript is useful evidence and an operator surface, but it is not company state.

### 1.3 Workspace Agent API trigger — wake path

The API trigger is the inbound wake mechanism. Executive OS calls the published Workspace Agent trigger directly.

MCP is **not** required to push into a sleeping agent.

### 1.4 Executive MCP — senses and governed hands

Once awake, Sol uses MCP to read canonical state and invoke reviewed executive operations.

MCP is the state/action path, not the wake path.

This yields a clean split:

```text
WAKE:   Executive OS ── Workspace Agent Trigger API ──► Sol
STATE:  Sol ◄──────────────── governed MCP ───────────► Executive OS
```

---

## 2. Current external evidence and unresolved product facts

This track must distinguish official product facts from operator-observed UI behavior and architecture inference.

### 2.1 Official: Workspace Agents are externally triggerable

OpenAI currently documents server-side Workspace Agent API triggers. The developer documentation describes:

- a stable published agent trigger identity;
- `input`;
- optional `conversation_key` to continue a stable agent conversation;
- `Idempotency-Key` for safe retries;
- a `conversation_url` response in the developer reference;
- an optional beta run-status facility exposing a run id and states such as queued / in-progress / suspended / completed / failed;
- no API for retrieving the final Workspace Agent response text.

The Help Center and developer reference are presently inconsistent about whether the normal 202 response has a body/run identifier. Therefore **Mastermind correctness may not depend on either field until a live account canary proves the exact behavior available to this workspace**.

### 2.2 Official: Workspace Agents support model/reasoning configuration

OpenAI currently states that builders can select the Workspace Agent model and reasoning effort. Business release notes also describe reasoning-effort controls for Workspace Agents.

### 2.3 Operator evidence: interactive agent conversations expose higher reasoning tiers

The Chairman has observed the live Workspace Agent conversation UI exposing controls from Instant through Extra High and Pro.

This is valuable evidence that the interactive Workspace Agent surface can use high reasoning. It does **not** prove that the external trigger request can dynamically select the tier, because the currently documented trigger request body contains no model or reasoning-effort field.

### 2.4 Official: Secure MCP Tunnel exists for private MCP servers

OpenAI documents Secure MCP Tunnel and an open-source `tunnel-client` for connecting private/local MCP servers to ChatGPT and other supported OpenAI products without exposing the private MCP server to public inbound traffic. The customer-side client initiates outbound HTTPS, polls the OpenAI tunnel service, forwards MCP JSON-RPC locally, and returns responses.

This is the preferred reachability candidate for the Executive MCP gateway because PR #64 deliberately refused public bind.

### 2.5 Unresolved: trusted caller identity through the tunnel

Secure reachability is not equivalent to trusted authorization.

PR #64 correctly leaves production writes unavailable until the gateway can prove the caller is the intended ChatGPT Business workspace/app/principal from trusted platform/transport evidence. A model-supplied username, actor string, workspace id, or prompt field remains untrusted.

The tunnel must therefore be tested as an **identity-bearing security boundary**, not merely as connectivity.

---

## 3. Source-law amendments

These laws extend the Phase 1G design. If a CEO-wake statement in the earlier masterplan conflicts with this track, this section governs the Workspace CEO path.

### C1 — Executive OS wakes Sol directly

The production wake path is Executive OS → OpenAI Workspace Agent trigger. No claimable worker provider, Grok Bot, Slack channel, browser automation, or human relay is a required dependency.

### C2 — Grok is not executive infrastructure

Grok Build/Bot may be commissioned as a worker, researcher, browser specialist, critique model, or fallback implementation provider. It may not become the hidden arbiter of company priority, CEO reasoning class, CEO wake eligibility, or canonical completion.

### C3 — Slack and ordinary ChatGPT sessions are interaction surfaces, not authority bypasses

Slack may invoke or converse with the Workspace CEO where enabled. Ordinary Workspace Agent conversations may also be started by a human. Neither surface becomes lifecycle truth.

Before any consequential modifying action from an interactive Slack/ChatGPT session, the request must be attached to a server-created or server-ratified Executive OS activation/intent and pass the same identity, authority, idempotency, and activation-fence checks as an autonomous trigger. A model-authored `activation_id` cannot create authority by itself.

### C4 — The CEO is event-driven, not continuously burning inference

The organization is continuously alive; the model need not be continuously generating tokens.

Sol wakes on canonical events, **Executive-OS-owned bounded schedules**, explicit Chairman requests, or governed continuation conditions; completes a cognitive cycle; writes a durable outcome; and sleeps.

### C5 — A CEO run must end in a durable outcome

Because trigger APIs do not expose the final response text as a machine-readable return channel, every autonomous activation must terminate with one of a small typed Executive OS outcomes:

```text
DECISION_RECORDED
DIRECTIVE_SUBMITTED
AGENDA_CHANGE_SUBMITTED
PROJECT_PROPOSED
PROJECT_INITIATED
REASONING_ESCALATION_REQUESTED
CONTINUATION_ARMED
NO_ACTION
WAITING_FOR_EVIDENCE
CHAIRMAN_ATTENTION
REFUSED_BY_AUTHORITY
FAILED_BEFORE_COMMIT
```

A pretty ChatGPT answer without a durable outcome is operationally incomplete.

### C6 — Reasoning allocation is Executive OS policy

Grok, Slack, workers, and provider prose do not choose the CEO reasoning tier.

A deterministic Reasoning Governor in Executive OS assigns the initial cognitive class from canonical facts and versioned policy. Sol may request **upward** escalation after inspecting the problem. The governor records both requested and effective class.

### C7 — No silent cognitive downgrade

If an activation requires Pro by policy, the system must either run a proved Pro-capable Workspace Agent route or refuse/degrade visibly. It must never silently route that activation to a lower class.

### C8 — Autonomy cannot rewrite its own constitution

Sol may improve projects, architectures, workflows, tools, evaluations, and much of Mastermind within delegated authority. It may not silently expand its own permissions, rewrite the Chairman charter, loosen authority-map ceilings, disable acceptance gates, alter credential boundaries, or modify the Reasoning Governor to reduce oversight.

### C9 — Autonomous project creation is separate from implementation authority

The CEO may decide that a new project should exist. That decision still enters the Improvement Agenda / accepted strategic-state path and the existing project/Job/orchestration machinery. Creating a project does not confer shell, merge, deploy, credential, or unrestricted worker authority.

Where delegated CEO authority permits a priority change, Sol submits a typed agenda/project operation and Executive OS validates and commits the priority mutation through the existing canonical priority source. Sol does not maintain a parallel priority queue.

### C10 — Wake and write paths fail independently

A trigger may succeed while MCP is unavailable; MCP may be healthy while trigger delivery fails. Both are independently observable and recoverable. No ambiguous partial failure is interpreted as a completed decision.

### C11 — Beta telemetry is advisory

Workspace Agent beta run-status polling may improve observability, but canonical completion comes from Executive OS durable outcomes. If the beta endpoint disappears or changes, the CEO loop must still be correct.

### C12 — One CEO activation owner per scope

Executive OS refuses duplicate concurrent CEO activations for the same governed root/scope unless policy explicitly declares them independent. Retries reuse the same activation identity and idempotency key.

### C13 — Executive OS owns production scheduling

Workspace Agent built-in schedules are not the canonical scheduler for autonomous Mastermind operation. The production strategic heartbeat, retries, continuations, cooldowns, and delayed wakes are represented and generated by Executive OS.

A Workspace Agent built-in schedule may be used only for operator convenience or an explicitly reviewed non-authoritative experiment. It may not create an untracked second stream of production CEO activations.

### C14 — Published CEO configurations are deployment artifacts

The mapping from logical reasoning class to published Workspace Agent trigger/configuration is reviewed configuration, not model-selected text.

Mastermind maintains a non-secret registry containing at least the logical route id, published trigger id, intended reasoning class, CEO charter version, expected MCP/tool manifest version, and approval-policy receipt/reference. If OpenAI exposes a trustworthy live config/version identifier, record and verify it. If not, an operator republish/config change invalidates the prior acceptance receipt and requires X0/X4 re-validation before autonomous use resumes.

---

## 4. CEO activation state model

Do not create a second queue or sidecar daemon database.

Add activation state to the existing Executive SQLite/runtime, either as a dedicated `ceo_activations` relation plus immutable events or another schema shape that preserves the same semantics.

**Migration law:** design and fixture work may proceed early, but the production schema migration must be based on the schema version produced by Phase 1F-B and may not merge ahead of G2. This preserves the existing Phase 1G migration-order gate.

Minimum logical fields:

```text
activation_id
activation_generation
root_scope_id
event_id / trigger_reason
conversation_key
reasoning_class_requested
reasoning_route_selected
reasoning_policy_version
agent_route_config_version
agent_trigger_id
trigger_idempotency_key
trigger_attempt_count
trigger_accepted_at
conversation_url_optional
provider_run_id_optional
state
activation_deadline
completion_event_id_optional
decision_id_optional
continuation_depth
parent_activation_id_optional
created_at / updated_at
```

Suggested state machine:

```text
PENDING
  │
  ├─ trigger refused/transient ──► RETRY_WAIT ──► PENDING
  │
  └─ trigger accepted ───────────► AWAITING_CEO_OUTCOME
                                      │
                                      ├─ durable CEO outcome ──► COMPLETED
                                      ├─ reasoning escalation ─► SUPERSEDED
                                      ├─ explicit authority block ─► ESCALATED
                                      ├─ deadline + provider failed ─► FAILED
                                      └─ deadline + ambiguous provider state ─► EXPIRED_UNRESOLVED
```

`COMPLETED` is reached from an Executive OS outcome transaction, not from seeing the provider run status `completed`.

### 4.1 Idempotency

Derive the trigger idempotency identity from a stable Executive OS activation/event id, never from model text.

A retry after network failure must not mint a logically new CEO event.

The trigger idempotency key and an MCP operation idempotency key solve different problems and must not be conflated.

### 4.2 Conversation continuity

Use a stable `conversation_key` only as conversational continuity. Never require the conversation history to reconstruct company state.

Prefer a bounded policy such as one key per durable executive/project scope rather than one immortal company-wide thread. Conversation keys may be rotated when context becomes stale, overgrown, contaminated, or operationally inconvenient because canonical recovery comes from Executive/Agent OS, not the transcript.

A fresh conversation must be able to recover by loading canonical Mastermind state through MCP.

### 4.3 Concurrency

Initial policy should serialize CEO activations that can mutate overlapping executive scope.

Independent read-only analysis may later run in parallel if it cannot cause competing directives or double project initiation.

### 4.4 Activation fence

Every autonomous modifying MCP call must be bound to the current Executive OS activation and its generation/fence.

A candidate modifying envelope includes at least:

```text
activation_id
activation_generation
operation_key
bounded operation payload
```

The server derives caller authority from trusted transport/platform identity and canonical policy — **not** from these model-supplied correlation fields — then additionally requires that:

- the activation exists;
- it is the current nonterminal owner for the affected scope;
- the generation matches;
- the requested operation is permitted for that activation/authority;
- the operation key has not committed a conflicting payload;
- the activation has not completed, been superseded, expired, or been drained.

A stale Workspace conversation that continues generating after the activation closes therefore cannot issue a late second directive. It receives a typed `stale_activation`/equivalent refusal.

### 4.5 Interactive-session ratification

A human-started ChatGPT/Slack interaction that remains read-only may operate without pretending to be an autonomous activation.

Before a production modifying action, the gateway/runtime must create or ratify an Executive OS activation/intent through a reviewed server-side path, bind the operation to it, and apply the same fence/idempotency rules. Interactive UX must never become a hidden bypass around X3/X5 governance.

### 4.6 Completion transaction

When possible, the final CEO outcome and activation terminalization should commit atomically with the durable decision/intent reference.

If the decision commits but the response is lost, retry returns the existing receipt and the activation remains terminal. If no durable decision/outcome committed, the activation remains reconcilable and may retry according to policy.

---

## 5. Reasoning Governor

The Reasoning Governor is deterministic policy in Executive OS. It allocates scarce cognition; it does not decide company priority.

### 5.1 Logical classes

Use stable logical classes rather than hard-coding current UI labels into the database:

```text
R0_FAST
R1_DEEP
R2_PRO
R3_CHAIRMAN
```

Initial mapping target:

```text
R0_FAST  → Instant-class Workspace CEO route
R1_DEEP  → Extra-High-class Workspace CEO route
R2_PRO   → Pro-class Workspace CEO route
R3_CHAIRMAN → do not solve by spending more inference; create Chairman attention
```

Provider/UI names are configuration, not architecture constants.

### 5.2 Initial classification principles

`R0_FAST` examples:

- routine confirmation of expected transitions;
- simple status reconciliation;
- deciding that a known condition requires no action;
- bounded mechanical continuation where strategic judgment is minimal.

`R1_DEEP` should be the normal executive reasoning class for:

- prioritization among active projects;
- interpreting unexpected results;
- deciding the next bounded project action;
- reviewing moderate architecture or research findings;
- project continuation/repair decisions.

`R2_PRO` examples:

- new Mastermind system architecture;
- multi-layer orchestration or control-plane design;
- major cross-project strategic redesign;
- deciding which major capability Mastermind should build next;
- high-impact or difficult-to-reverse architecture choices;
- contradictory evidence where a shallow answer could create large downstream cost;
- self-improvement changes that alter how Mastermind reasons, evaluates, delegates, or allocates resources.

`R3_CHAIRMAN` is for missing authority or objective rather than insufficient intelligence:

- changing the constitutional objective or Chairman doctrine;
- expanding CEO permissions;
- material risk/capital/taste choices outside delegated policy;
- weakening a production safety gate;
- other decisions reserved by Charter or `authority_map.yml`.

### 5.3 Escalation

Sol may call a reviewed action such as:

```text
request_reasoning_escalation(
  activation_id,
  activation_generation,
  target_class=R2_PRO,
  reason_code,
  bounded_rationale,
  evidence_refs
)
```

Executive OS validates the upward transition, terminalizes/supersedes the lower-class activation, and wakes the proved higher-class route with linked lineage.

After an escalation request commits, the lower-class activation may not make further consequential writes. Any late call is rejected by the activation fence.

### 5.4 Dynamic effort is a hard acceptance question

The currently documented trigger request does not expose a reasoning-effort field. Before implementation chooses a routing shape, run a live capability spike.

Accepted outcomes:

**A. Dynamic effort is externally selectable and proved.**  
One published CEO route may be sufficient if the trigger/platform provides a trusted deterministic selection mechanism.

**B. Effort is fixed per published agent/config.**  
Publish logically identical CEO configurations for the needed classes, for example `sol-fast`, `sol-deep`, `sol-pro`, all bound to the same charter/MCP but different reasoning configuration.

**C. Effective effort cannot be proved.**  
Autonomous cognitive routing remains shadow-only. Do not claim R2_PRO execution.

The system records the selected route/config version and acceptance receipt so later audits can prove which cognitive class was intended.

### 5.5 Reasoning policy separation

Reasoning class may depend on canonical properties such as novelty, impact, reversibility, architecture scope, contradictory evidence, prior failed attempts, and task class.

It may not silently convert low organizational priority into high priority. The Improvement Agenda/accepted strategic state answers **what matters**; the Reasoning Governor answers **how much cognition an already-legitimate executive question should receive**.

---

## 6. CEO mission loop

The CEO should not require Chairman prompt injection to continue ordinary executive work.

Every autonomous activation follows the same structured metaprocess even when the subject matter is novel:

```text
1. ORIENT
   load Charter + strategic state + Improvement Agenda + Executive Inbox
   + relevant project tree + recent decisions + evidence + capacity state

2. INTERPRET
   identify why this activation exists and whether the triggering evidence is valid/current

3. DIAGNOSE
   identify bottleneck, opportunity, risk, missing evidence, or completion state

4. DECIDE COGNITIVE SUFFICIENCY
   continue at current class, request Pro escalation, or request Chairman authority

5. CHOOSE EXECUTIVE ACTION
   continue / redirect / stop / commission research / propose agenda change
   / propose project / initiate project / request review / wait / no action
   / Chairman attention

6. COMMIT
   invoke only typed governed MCP action(s) under the current activation fence;
   record rationale/evidence references

7. ARM CONTINUATION IF NEEDED
   declare exact canonical condition or Executive-OS-owned bounded schedule
   that justifies another CEO wake

8. CLOSE
   write one durable CEO activation outcome and stop
```

The goal is not for Sol to constantly invent work. The goal is for Sol to repeatedly ask, from canonical state, **what is the highest-value executive action now?** and to be allowed to answer `NO_ACTION` when appropriate.

### 6.1 Strategic heartbeat

Purely reactive wakes are insufficient for an autonomous CEO whose mandate includes discovering what to build next.

Executive OS therefore supports a bounded recurring `STRATEGIC_REVIEW`/equivalent canonical wake source. Its cadence is configuration, not embedded in this design. On that activation Sol reviews strategic state, Improvement Agenda, project outcomes, bottlenecks, capability gaps, external evidence already ingested into Mastermind, and available capacity.

A strategic heartbeat must be allowed to end in `NO_ACTION`; it is not a requirement to manufacture a project every cycle.

The heartbeat is scheduled by Executive OS, not a hidden Workspace Agent schedule, so dedupe, budgeting, drain, audit, and restart semantics remain under the one control plane.

---

## 7. Autonomous project initiation and Mastermind improvement

### 7.1 What Sol may eventually do

After promotion gates pass, Sol may autonomously:

- detect an unowned capability gap;
- commission bounded research;
- compare candidate architectures;
- invoke Pro reasoning for major design work;
- submit a governed Improvement Agenda/priority change when delegated authority permits;
- create a project under existing strategic objectives;
- decompose it through Phase 1F-C leader/orchestration machinery;
- inspect results and independent review;
- initiate bounded repair or a successor project;
- retire a project whose evidence no longer supports continued investment;
- improve Mastermind's tools/evals/workflows through the same governed project path.

### 7.2 What Sol may not bootstrap around

Sol may not create a new route that bypasses:

- the Improvement Agenda / accepted strategic state;
- Executive OS lifecycle authority;
- authority-map ceilings;
- parent/child/review bounds;
- path/write capability shrinkage;
- production MCP identity gates;
- provider credential isolation;
- deployment/real-host acceptance rules;
- independent review requirements.

### 7.3 Agenda intake and priority authority

Autonomous discovery becomes organizational work only through the canonical priority path.

A proposed pattern is:

```text
Sol detects gap/opportunity
  ↓
typed agenda/project proposal under active CEO activation
  ↓
Executive OS validates CEO authority + strategic envelope + idempotency
  ↓
canonical Improvement Agenda/accepted strategic state is updated or proposal is held
  ↓
project/parent Job creation becomes eligible according to existing orchestration law
```

If the priority change is outside delegated CEO authority, the outcome is `CHAIRMAN_ATTENTION`, not a shadow priority ledger or direct worker dispatch.

### 7.4 Self-improvement must remain falsifiable

A self-improvement project must define an evaluation target before promotion. “The CEO believes the new loop is better” is not acceptance evidence.

Examples of measurable outcomes:

- higher independent-review approval rate;
- lower repair rounds at equal outcome quality;
- fewer human escalations without increased authority violations;
- lower frontier cognition burn per accepted project;
- improved time-to-detect stalled/failed work;
- higher project success under fixed budgets;
- fewer duplicate/conflicting directives.

---

## 8. MCP production surface

PR #64's existing five-tool READONLY/FIXTURE surface remains the baseline. Production write capability must be a separate reviewed arm.

Do not simply flip the current fixture modifying path to production.

Candidate executive operations should be typed around organizational meaning, not implementation mechanics. The exact census requires a separate commission, but likely categories are:

```text
read:
  executive_state
  executive_inbox
  executive_project
  executive_job
  executive_capacity
  ceo_intent_status
  ceo_activation_status

modify, bounded:
  submit_production_ceo_intent
  submit_agenda_change / create_or_propose_project
  request_dispatch / request_orchestration
  record_ceo_decision
  request_reasoning_escalation
  arm_ceo_continuation
  acknowledge_ceo_activation
  escalate_to_chairman
```

A generic SQL, shell, tmux, arbitrary HTTP, credential, merge, deploy, or service-control tool remains forbidden.

Every modifying call must carry an activation id/generation plus idempotency/operation key and receive a durable server-generated receipt. The activation id is correlation/fencing state; it does not confer caller authority.

---

## 9. Private MCP transport and identity

### 9.1 Preferred reachability topology

Evaluate Secure MCP Tunnel before inventing a public ingress proxy:

```text
Sol Workspace Agent
      │
      │ OpenAI connector / tunnel endpoint
      ▼
OpenAI Secure MCP Tunnel
      ▲
      │ outbound HTTPS only
      │
tunnel-client
 dedicated least-privilege principal
      │
      │ loopback / Unix socket / private HTTP
      ▼
Executive MCP gateway
      │
      ▼
Executive OS control boundary
```

The tunnel client is transport. It is not a scheduler, queue, database, authority source, or worker.

### 9.2 Least privilege

The tunnel-facing runtime must not run as root, `_mastermind_exec`, the interactive operator, or a worker provider principal if a narrower dedicated principal can be used.

It should have only what is required to:

- read its protected tunnel runtime credential/reference;
- reach the one reviewed local MCP endpoint;
- emit bounded health/transport logs;
- make outbound HTTPS to the OpenAI tunnel service.

It gets no direct database path and no worker provider homes.

### 9.3 Identity acceptance

Before production writes, prove on the real path:

1. the intended ChatGPT workspace/app can reach the gateway;
2. an unauthorized workspace/app/principal cannot reach the protected modifying surface;
3. caller identity/authorization derives from trusted platform/transport evidence rather than model-authored fields;
4. tunnel identifiers and runtime API credentials alone cannot be replayed by a model to impersonate the CEO;
5. app action approval configuration behaves as intended for autonomous bounded writes;
6. read-only operations remain available or fail closed according to policy when modifying authorization is absent;
7. activation correlation fields cannot substitute for caller authentication.

If the transport cannot convey trustworthy caller identity to the local gateway, production writes remain blocked and a separate auth layer must be designed.

---

## 10. Trigger dispatcher, scheduler, and secret boundary

Executive OS needs a narrow outbound trigger dispatcher. The existing Executive OS control plane also remains the owner of recurring CEO schedules/continuations.

The trigger dispatcher owns only:

- the approved published Workspace Agent trigger/config mapping;
- a protected API access credential/reference;
- bounded HTTP client behavior;
- idempotency headers;
- retry/backoff policy;
- sanitized trigger receipts.

The scheduler owns only canonical wake timing/conditions; it does not perform CEO reasoning.

The trigger credential never enters:

- Job prompts;
- SQLite event payloads;
- MCP results;
- worker environments;
- Git;
- Agent OS;
- Slack;
- model-visible diagnostics.

Responses are treated conservatively because current OpenAI docs conflict. The dispatcher records optional `conversation_url` and optional provider run id when present, but neither is required for correctness.

A built-in Workspace Agent schedule is not configured as a production source of autonomous CEO state transitions unless a future separately reviewed design makes Executive OS the canonical owner/registrar of that schedule. The default architecture does not need it.

---

## 11. Failure and recovery model

Every failure below needs a named typed state and test.

### 11.1 Trigger failures

- authentication/authorization refusal;
- malformed or stale published trigger id/config mapping;
- 429/rate limit;
- transient 5xx/network loss;
- timeout after provider may have accepted;
- duplicate retry;
- provider accepts but returns no response body;
- beta run-status unavailable;
- agent republished/config changed without a fresh route acceptance receipt.

Recovery: reuse activation id + idempotency key; do not create duplicate executive intent.

### 11.2 Agent/MCP failures

- Sol wakes but tunnel is offline;
- Sol can read but modifying action is denied;
- app write confirmation blocks unattended completion;
- Sol produces prose but no durable outcome;
- Sol partially submits an idempotent intent then loses connection;
- stale state changes between read and write;
- stale/duplicate Sol continues generating after its activation completed;
- Slack/manual session attempts a modifying call without a ratified activation;
- lower-class Sol requests Pro and then attempts another consequential write;
- trigger route points at wrong/stale agent config;
- intended Pro route actually runs a lower class or cannot be proved.

Recovery: outcome remains incomplete until Executive OS sees the durable receipt. Re-trigger or escalate according to bounded policy; never infer success from conversation prose. Activation fencing rejects late or superseded writes.

### 11.3 Scheduling failures

- duplicate strategic heartbeat after restart;
- two schedulers emit the same logical wake;
- delayed continuation fires after the root project is terminal;
- built-in Workspace schedule creates an untracked wake;
- clock/timezone drift causes repeated/missed review window.

Recovery: all production schedules resolve to stable Executive OS logical schedule/event ids, dedupe through the activation ledger, and re-evaluate the current canonical condition before waking Sol.

### 11.4 Runaway prevention

Initial production policy must include:

- maximum automatic activation chain depth per root event/project transition;
- dedupe/debounce for equivalent events;
- maximum unresolved activations per scope;
- per-window budget/reserve for Pro activations;
- cooldown after repeated trigger or MCP failure;
- no self-wake from bookkeeping events unless a reviewed continuation condition says so;
- bounded recurring strategic review rather than continuous token burn;
- explicit `NO_ACTION` completion to stop pointless loops;
- activation-generation fencing against stale conversations;
- Chairman kill/drain control that stops new autonomous CEO triggers while preserving/reconciling already-durable state.

The exact numeric limits are configuration decisions for a later implementation PR, not invented in this design document.

---

## 12. Shadow evaluation program

Workspace CEO autonomy earns authority through measured shadow evidence.

### 12.1 Corpus

Build a replayable corpus from real historical Executive OS situations plus synthetic adversarial cases:

- routine completion;
- worker failure and exhausted attempts;
- stalled project;
- conflicting reviewer findings;
- capacity exhaustion;
- architecture design request;
- ambiguous scope;
- high-impact irreversible proposal;
- missing Chairman authority;
- prompt-injected worker text;
- stale Agent OS evidence;
- duplicate events;
- failure after commit before response;
- stale activation attempting a second write;
- human Slack request attempting to bypass activation creation;
- strategic heartbeat with no worthwhile action;
- strategic heartbeat with a genuine unowned capability gap;
- Pro-worthy problem initially misclassified as deep;
- harmless problem overclassified as Pro.

### 12.2 Scorecards

Measure:

```text
action correctness
canonical grounding completeness
authority compliance
no-action precision
project-initiation precision
agenda-change precision
reasoning-class calibration
Pro escalation precision / recall
independent-review agreement
write/idempotency/fence correctness
human intervention rate
activation loops per resolved event
frontier cognition cost per accepted executive outcome
```

### 12.3 Comparison

Compare at least:

- read-only Workspace Sol against the existing human/CEO decisions where available;
- R1_DEEP versus R2_PRO on a representative hard subset;
- one-run direct Pro against deep→escalate-to-Pro where applicable;
- event-driven-only behavior versus event + strategic-heartbeat coverage;
- current normal ChatGPT Pro planning on a bounded benchmark only if it can be compared without contaminating canonical state.

Promote from shadow based on outcome quality, not model branding.

---

## 13. Parallel implementation track

The current masterplan's W0–W13 Agent Fabric sequence remains valid. CEO autonomy should not wait as one monolithic final W14 because several zero-write questions can be answered safely in parallel.

### X0 — Capability and contract spike

**May start immediately; design/fixture only.**

Prove and record on the live Business workspace:

- exact Workspace Agent publish/trigger lifecycle;
- actual trigger HTTP contract available to this account;
- whether `conversation_url` appears;
- whether beta run-status is available;
- `conversation_key` behavior;
- idempotent retry behavior;
- model/reasoning configuration available in builder/UI;
- whether externally triggered runs can be deterministically bound to Instant / Extra High / Pro, and by what mechanism;
- whether current agent/config/version metadata can be queried or must be governed by operator publication receipts;
- app action approval behavior;
- Secure MCP Tunnel availability for this workspace;
- Workspace Agent built-in schedule behavior only as evidence, not as production scheduler design.

**Exit:** an evidence matrix with every unknown marked PROVED, REFUTED, or STILL UNKNOWN. No production writes.

### X1 — Private read-only MCP reachability

**May proceed before G1 because it cannot mutate production.**

- connect PR #64's READONLY gateway through Secure MCP Tunnel or another separately reviewed private route;
- use a dedicated tunnel principal;
- prove public bind remains impossible;
- run Workspace Sol against `executive_state`, `executive_inbox`, `executive_job`, and `ceo_intent_status`;
- prove prompt-injected canonical text remains inert.

**Exit:** real Workspace Agent can read bounded Executive state without any production modifying capability.

### X2 — Sol CEO charter and shadow executive loop

**May proceed before G1; read-only/shadow.**

- freeze a versioned CEO mission prompt/charter supplement;
- implement ORIENT→INTERPRET→DIAGNOSE→DECIDE→COMMIT/NO_ACTION→CONTINUE/CLOSE semantics in shadow;
- prohibit implementation actions;
- score historical/synthetic activation corpus;
- prove it can decide to propose agenda changes/new projects without creating them;
- include strategic-heartbeat cases where the correct answer is `NO_ACTION`.

**Exit:** shadow quality and authority-compliance gate passes.

### X3 — External trigger dispatcher + activation ledger

**Design/fixture work may proceed before G1/G2. Production schema merge waits for G2.**

X3A, early design/fixture:

- specify canonical CEO activation state and events;
- implement/test outbound trigger dispatcher against fixture/shadow state;
- idempotency and retry;
- optional run-status telemetry;
- deadline/expiry/reconciliation;
- activation generation/fence semantics;
- strategic-review schedule identity/dedupe semantics;
- durable `NO_ACTION` / shadow-decision completion path in a temporary/fixture runtime.

X3B, persistent runtime integration:

- base the additive Executive SQLite migration on the Phase 1F-B schema version;
- merge only after G2;
- preserve migration/backup/restore/idempotency proofs;
- no second queue/database/scheduler;
- keep all production modifying CEO actions unavailable until X5.

**Exit:** trigger loss, duplicate retry, missing response body, restart, stale-write, duplicate-schedule, and stuck-run mutations all converge deterministically.

### X4 — Reasoning Governor and Pro-routing proof

**May proceed before G1 in shadow; persistent integration follows applicable schema/config gates.**

- implement R0/R1/R2/R3 policy in shadow;
- prove actual route/config mapping for Instant / Extra High / Pro;
- if per-trigger effort cannot be selected, publish separate logically equivalent routes and pin reviewed route/config receipts;
- implement upward escalation lineage and stale-lower-run fencing;
- add reserve/budget telemetry;
- measure calibration and Pro benefit on the hard corpus.

**Hard gate:** if Pro execution cannot be deterministically selected/proved, R2 remains unavailable for autonomous production.

### X5 — Production MCP write arm

**Requires G1 Phase 1C-A PASS, G2 where project-tree/activation migration semantics require it, plus the PR #64 caller-identity and least-privilege gates.**

- commission exact production tool census;
- prove trusted Workspace/App identity on the real transport;
- arm only bounded typed writes;
- require activation id/generation for autonomous modifying actions;
- ratify interactive modifying sessions server-side;
- pin schema snapshot;
- adversarial/mutation review;
- one harmless idempotent CEO-intent canary;
- one stale-activation refusal canary;
- rollback/drain proof.

**Exit:** bounded production executive write works; no autonomous project fan-out yet.

### X6 — Autonomous continuation and project initiation

**Requires X5 + W13 / G9 hierarchical orchestration PASS.**

- enable canonical event→reasoning class→trigger rules for a small allowlist;
- enable Executive-OS-owned continuation conditions and bounded schedules;
- enable a bounded recurring strategic-review wake source;
- allow governed Improvement Agenda/project proposals and project initiation inside current strategic/authority envelope;
- enforce activation fences, chain depth, cooldown, Pro budget, and one-owner rules;
- all implementation routes through existing Phase 1F-C / Agent Fabric machinery;
- Chairman attention for R3 or authority gaps.

**Exit:** one real end-to-end autonomous project cycle completes from event/strategic review through CEO decision, canonical agenda/project admission, child work, independent review, CEO reassessment, and clean stop without Chairman prompt injection.

### X7 — Autonomous improvement promotion

**Requires sustained X6 evidence and independent architecture/security review.**

- allow Sol to originate Mastermind improvement projects inside a reviewed domain;
- require predeclared evals for self-improvement proposals;
- keep constitutional/governance/security files outside autonomous write authority;
- monitor outcome quality, frontier burn, duplicate directives, stale-write refusals, runaway chains, and human escalation;
- maintain immediate drain/kill switch.

**Exit:** autonomous CEO mode is promoted only when measured project outcomes improve without authority or lifecycle regression.

---

## 14. Dependency graph

```text
Agent Fabric track
W0 ──► W1 1C-A ───────────────────────────────────────┐
 │                                                    │
 └──► W2 1F-B / G2 ─► W3..W12 ─► W13 / G9           │
          │                         │                  │
          └────────► X3B runtime ───┼──────────┐       │
                                    │          │       │
Executive Autonomy track            │          │       │
X0 ─► X1 ─► X2                     │          │       │
  └──────► X3A design ─► X4        │          │       │
                         │          │          │       │
G1 + G2 + identity ──────┴────► X5 ┘          │       │
                                           X6 ◄───────┘
                                            │
                                            ▼
                                           X7
```

X0–X4 answer platform/reasoning questions early in read-only/shadow/fixture form. X3B respects the existing G2 schema-order gate. X5–X7 remain gated by the secure runtime, identity, and orchestration prerequisites.

---

## 15. Program-level acceptance invariants

Before X7 promotion, all of the following must be true:

1. **One truth:** Executive SQLite remains the only CEO activation/lifecycle state authority.
2. **One scheduler:** Executive OS owns production strategic heartbeat, retries, continuations, and delayed wakes; Workspace Agent schedules do not form a second autonomous scheduler.
3. **Wake independence:** Executive OS can wake Sol without Grok, Slack, or a worker provider.
4. **Private reachability:** Executive MCP is not publicly exposed merely to serve ChatGPT.
5. **Trusted identity:** production writes prove authorized Workspace/App caller identity from trusted evidence.
6. **Activation fence:** late, duplicate, superseded, expired, and drained Sol runs cannot issue consequential writes.
7. **No prose completion:** every autonomous run resolves through a durable Executive OS outcome.
8. **Idempotent wake:** ambiguous trigger retries cannot duplicate executive action.
9. **Restart safety:** Executive OS restart reconstructs pending CEO activations/schedules and reconciles them.
10. **No silent downgrade:** R2_PRO is either proved Pro or refused.
11. **Bounded escalation:** Sol can escalate reasoning but cannot expand its own authority; the lower-class activation becomes stale for writes.
12. **Bounded continuation:** no unbounded self-trigger chain, recursive project fan-out, or zero-value polling loop.
13. **Strategic initiative:** a bounded Executive-OS-owned strategic review can discover new work, while `NO_ACTION` remains a valid result.
14. **Chairman boundary:** objective/authority questions escalate instead of being guessed.
15. **Canonical priority:** autonomous discoveries become projects only through the Improvement Agenda/accepted strategic-state authority; no shadow priority queue exists.
16. **Governed project creation:** autonomous new projects enter existing Job/review/orchestration controls.
17. **Independent review:** material architecture/self-improvement work retains reviewer independence.
18. **Credential separation:** Workspace trigger/tunnel credentials never enter worker or model-visible state.
19. **Slack non-authority:** Slack/manual ChatGPT sessions cannot bypass canonical activation, state, or write policy.
20. **Grok non-dependency:** xAI capacity failure cannot block CEO wake/control.
21. **Config integrity:** approved logical reasoning routes map to reviewed published-agent configuration receipts; republish/config drift invalidates acceptance until re-proved.
22. **Kill/drain:** operator can stop new autonomous wakes while preserving/reconciling already-durable state.
23. **Observable cost:** reasoning class and protected frontier usage are measurable per executive outcome.
24. **Falsifiable improvement:** self-improvement promotion requires eval evidence, not agent self-assertion.
25. **No skipped prior gates:** this track does not waive Phase 1C-A, Phase 1F-B/C, MCP identity, migration order, provider/security, or deployment acceptance.

---

## 16. Immediate commissions produced by this amendment

These are design/fixture commissions only until their explicit gates allow more.

### Commission X0-A — Workspace Agent capability evidence

Produce a dated live evidence matrix for trigger contract, run telemetry, `conversation_key`, idempotency, reasoning-tier routing, agent-config/version observability, write approvals, and tunnel availability.

### Commission X1-A — Secure MCP Tunnel read-only spike

Connect the existing PR #64 READONLY gateway to the Workspace Agent without public bind. Do not add a production write mode.

### Commission X2-A — CEO mission contract + eval corpus

Version the autonomous CEO metaprocess and build a replay corpus, including periodic strategic-review / `NO_ACTION` cases. No production write authority.

### Commission X3-A — CEO activation/dispatcher/scheduler design

Specify additive Executive SQLite state/events, activation fencing, retry/reconciliation, strategic-review scheduling, and migration semantics. Fixture only until G2 permits a real migration.

### Commission X4-A — Reasoning Governor shadow design

Specify policy inputs, R0–R3 outputs, escalation lineage, route/config evidence, and Pro reserve accounting.

Do not commission X5 production writes until G1, G2 where applicable, and the trusted-caller identity boundary are satisfied.

---

## 17. External evidence used for this amendment

Re-check before implementation because product behavior is volatile.

- OpenAI Help Center — ChatGPT Workspace Agents for Enterprise and Business: model/reasoning controls, apps/tools/custom MCP, schedules, Slack, API triggers.
- OpenAI Developers — Workspace Agent trigger API: trigger endpoint, `conversation_key`, idempotency, optional beta run status; final response text unavailable by API.
- OpenAI Developers — Secure MCP Tunnel / `openai/tunnel-client`: outbound-only private MCP connectivity for ChatGPT and supported OpenAI products.
- OpenAI Business release notes / rate card: current Workspace Agent model/reasoning and token-based usage behavior.

The operator-observed Instant / Extra High / Pro controls are recorded as workspace-specific evidence and require X0 to determine how they interact with externally triggered runs.

---

## 18. Final architecture verdict

The durable CEO system is not “Grok keeps ChatGPT alive.”

It is:

```text
Executive OS keeps the organization alive.
Executive OS owns production event and schedule generation.
Executive OS decides when CEO cognition is required.
Executive OS decides the initial reasoning class.
Executive OS creates/fences the CEO activation.
The Workspace Agent performs bounded CEO cognition.
The CEO may request deeper cognition or Chairman authority.
MCP is the governed read/write path.
The trigger API is the wake path.
Secure MCP Tunnel is the preferred private transport candidate.
Slack/manual ChatGPT are interaction surfaces, not write-policy bypasses.
Grok is an optional specialist/worker provider.
All consequential outcomes return to Executive OS as durable state.
```

This preserves one control plane while allowing Sol to become genuinely autonomous: it can discover what to do next through both canonical events and bounded strategic review, originate agenda/project proposals, commission work, evaluate results, and continue improving Mastermind without requiring a new Chairman prompt for every turn — but only inside explicit authority, reasoning, activation-fence, cost, retry, schedule, and lifecycle bounds.