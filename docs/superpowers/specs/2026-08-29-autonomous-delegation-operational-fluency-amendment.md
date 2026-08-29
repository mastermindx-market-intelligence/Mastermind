# Mastermind Autonomous Delegation Operational Fluency — Continuity Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Chairman approval:** explicit approval in the governing Chairman/Sol architecture review after a second-pass operational-fluency stress test.  
**Operation key:** `organizational-continuity-autonomous-delegation-operational-fluency-20260829-sol-001`  
**Protected source basis:** `mastermindx-market-intelligence/Mastermind@adccc544509aaa0ef7c0bb4f8bdbbfab19cf85e2`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.  
**Parent source law:** merged Mastermind #214 / `14056772bda2add31f1596bd89cebd6bf0c31de3`, especially `2026-08-28-organizational-continuity-attention-recovery-amendment.md`, `2026-08-29-project-management-operating-surface-cutover-amendment.md`, and `2026-08-29-organizational-continuity-sol-action-authority-amendment.md`.  
**Authority:** narrow precedence amendment for autonomous delegation identity, retry/concurrency law, provider/worker turn projection, stale-surface authority, and production cutover. It extends the existing Executive OS / Agent OS / Worker Presence / Wake / Capacity / Operator Continuity / OCR-6 architecture and creates no new canonical owner.  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY`. This document creates no Job, Attempt, Worker, provider session, Slack message, Wake obligation, RuntimeBinding, queue, database, scheduler, retry, account binding, browser operation, Linear mutation or production capability.

---

## 1. Chairman outcome and acceptance ruler

The target is not merely “fewer duplicate Slack handoffs.” The target is an organization that remains operationally fluent when many Sol responsibilities and many provider workers are active simultaneously.

After the Chairman establishes or changes company intent, the normal operating experience must require none of the following:

- opening or monitoring `#agent-dispatch`;
- deciding which Claude/Codex account or provider window should receive routine bounded work;
- copying a handoff into a provider session;
- discovering that two Sol sessions commissioned the same child;
- discovering that an old provider task is stale only after manually opening it;
- reminding Codex or Claude to post ACK/START/BLOCKED/RESULT into Slack;
- waking a Sol tab because a worker returned;
- waking a worker tab because Sol continued it;
- identifying which provider session belongs to which logical responsibility;
- repairing local scheduled watchers;
- reconstructing whether a parent program is active after its child was correctly STOPped;
- deciding whether a provider failure should retry, roll over or remain held;
- manually load-balancing the company because one provider account is exhausted.

The end-state operating surfaces remain:

```text
Control Room / Executive Steward = live operating cockpit
Linear                           = selective durable portfolio/project projection
Grok Secretary                   = conversational read/control shell over approved Steward/controls
GitHub                            = implementation/evidence drill-down
Slack #agent-dispatch             = dialogue transport + forensic audit, never Chairman workflow
```

No actionable organizational fact may exist only in Slack after cutover.

The final acceptance statement is:

> The Chairman sets intent. Mastermind admits one logical responsibility, places bounded work on lawful capacity, keeps exactly one action-authoritative executor and one action-authoritative executive turn, projects every semantic return mechanically, safely survives provider/session loss, and presents the whole company in Control Room without Slack archaeology or session hunting.

---

## 2. Why the first continuity design was insufficient

The #214 architecture was directionally correct, but deeper current-code archaeology exposed six additional failure classes that must be closed before automated delegation can replace manual handoffs.

### 2.1 Cross-transport root identity can currently fork

Current `control_plane.ceo_request` deliberately derives transport-specific intent identities for the same caller-authored `operation_key`:

```text
mcp_intent_id(operation_key)   != slack_intent_id(operation_key)
```

That behavior is valid historical v1 compatibility, but it is not acceptable as the identity law for future autonomous delegation. Two ingress surfaces must not be able to create two Executive roots for one already-identified company request merely because transport differs.

### 2.2 Caller/model-authored operation keys are insufficient for autonomous child identity

A stable operation key is useful only if every competing Sol surface chooses the same key. Two Sol sessions can otherwise describe the same intended child with different strings and bypass same-key idempotency.

Fuzzy semantic similarity must not become mutation authority. The system must instead derive automated child identity from already-canonical organizational/Executive lineage.

### 2.3 Content-addressed commission provenance is not long-lived operation identity

Agent Dialogue `commission_ref` correctly binds repository + commit + path + content digest. That is strong provenance, but a legitimate records clarification changes those bytes. A content-addressed document therefore cannot by itself be the durable identity of a long-running operation.

Commission content is frozen provenance at admission; it does not replace Executive root/child identity.

### 2.4 Same logical dialogue across Attempt replacement needs explicit implementation support

Operator Continuity correctly requires one logical Slack/company dialogue to survive safe P1 -> P2 provider/Attempt replacement. The current Agent Dialogue V2 implementation historically compared message applicability too strongly against one current `executive_attempt`, making prior-P1 history incompatible with current-P2 context.

The accepted model is therefore:

```text
parent/thread identity       = operation-level stable context
message applicability        = Attempt-local fact at the time of that message
current outbound authority   = exact current Attempt/Worker only
```

The already-existing WP-1R carrier #217 is the sole current implementation owner of this repair. This amendment does not create a replacement engine lane.

### 2.5 RuntimeBinding alone is not the stale-worker security boundary

RuntimeBinding is a critical routing/continuity projection, but the authoritative stale-executor fence is the existing Executive current Attempt + Worker + lease/fence/quota ownership and the corresponding trusted worker-tool binding.

A stale provider session may physically remain visible. Safety must not depend on closing its UI. It loses sanctioned authority because its Attempt/binding is no longer current.

### 2.6 A perfectly safe one-worker system would still fail operationally at company scale

Current strict-v2 Executive service composition intentionally serializes worker dispatch. That is safe for the existing proof/cycle lane but is not sufficient for a company operating many independent programs at once.

Automated cutover therefore requires bounded **cross-root parallel execution across distinct lawful Worker realms** without creating a second scheduler or lifecycle. Intra-root parallel DAG execution remains a later capability unless per-child workspace/integration isolation is independently proven.

---

## 3. Canonical ownership freeze

This amendment creates no new owner.

| Fact | Canonical owner |
|---|---|
| Chairman/CEO request admission, Job/Attempt/Worker/Event lifecycle, current Attempt, leases/fences, retry/requeue | Executive OS |
| durable workstream/program/decision/discovery/handoff identity | Agent OS |
| strict COO root/child/review/repair lineage | existing Executive orchestration / COO cycle |
| provider/account/host eligibility and capacity evidence | existing Capacity Fabric + Shared AI Provider Control + Model Router |
| provider-native execution/session/process evidence | existing Worker/Operator Harness + provider adapter |
| continuation capsule / Attempt rollover evidence | existing Operator Continuity / Executive Events |
| dialogue parent/messages and Slack transport | existing Agent Dialogue / Agent Relay |
| turn classification | existing WP-TW classifier |
| attention obligation, routing, delivery, ACK/source resolution | existing Executive Wake Fabric |
| exact Sol/COO target binding | existing responsibility / SessionTargetRegistry / RuntimeBinding / dialogue applicability owners |
| implementation/PR/CI/proof | GitHub |
| selective human portfolio projection | Linear |
| cross-owner read/explanation/exception composition | existing OCR-6 Executive Steward / Control Room |

Forbidden replacements include a delegation registry, operation-key database, session database, Slack task queue, watcher registry, Sol-election service, retry table, provider pool manager, duplicate Steward, or another lifecycle.

---

## 4. Identity model — four distinct layers

Do not overload one key to mean every kind of identity.

### 4.1 Request/root identity

Represents one admitted company request/program execution instance.

For the future autonomous path, one already-identified request has one transport-neutral Executive admission identity regardless of whether the authenticated request enters through ChatGPT/Sol, Grok Secretary, Control Room, Slack ingress, MCP or another approved frontend.

Historical v1 transport-specific identity behavior remains immutable compatibility history. Do not silently reinterpret old MCP/Slack roots.

### 4.2 Child responsibility identity

Represents one bounded work/review/repair child inside an admitted root/program.

For autonomous delegation this identity is **not authored by the model**. It is derived deterministically from the existing Executive orchestration lineage/creation command or another already-accepted canonical child responsibility source.

Human-readable titles and wave names remain display/provenance text only.

### 4.3 Attempt/execution identity

Represents one concrete execution attempt:

```text
Job
Attempt
Worker
quota class / placement snapshot
lease token + fence generation
provider/account/host
provider-native session/process
```

A safe retry or provider/account/host rollover may create a new Attempt for the same child Job. It never creates a second logical child solely because physical execution moved.

### 4.4 Dialogue identity

Represents the stable company conversation for one logical child responsibility.

The dialogue parent is derived from/frozen against the child responsibility and admitted provenance. Provider-native sessions are not dialogue identity.

The intended relation is:

```text
one admitted child Job
  -> one logical company operation identity
  -> one canonical dialogue parent/thread
  -> zero or more sequential Attempts
  -> at most one current action-authoritative Attempt
```

---

## 5. Transport-neutral autonomous admission

### 5.1 New automated path only

Do not break historical v1 callers merely to get dedupe.

Add a separately versioned automated admission law whose canonical request identity is independent of ingress transport.

Conceptually:

```text
trusted request_instance_ref / root admission identity
  -> global automated intent_id
  -> existing ceo_intent command_id
  -> existing Executive UNIQUE event idempotency
  -> one root Job
```

The exact schema/name is an implementation decision for the owning CEO-ingress wave, but its properties are frozen here.

### 5.2 Same already-identified request, repeated from another ingress

If one authenticated request instance is submitted concurrently/repeatedly through different approved frontends:

```text
same canonical request identity + same normalized envelope
  -> reconcile exact existing root Job / receipt
  -> zero second root

same canonical request identity + changed normalized envelope
  -> OPERATION/REQUEST CONFLICT
  -> zero modification
```

### 5.3 Do not use semantic similarity for authority

Two free-form Chairman messages that happen to describe similar work are not automatically the same modification.

If no common canonical request identity exists, the system may surface a read-only “possible overlap” observation for Sol/Steward, but it may not suppress, merge or mutate work based on an LLM similarity score.

### 5.4 Repeated business work remains possible

“Run the same monthly audit again” is a new request instance even when its objective text is byte-identical to last month.

Idempotency is about the same **operation instance**, not deduping English descriptions forever.

---

## 6. Deterministic child delegation identity

### 6.1 Model may author mission content, not canonical child identity

For autonomous COO/Sol delegation, the child identity must derive from existing deterministic Executive lineage.

Current strict COO cycle already provides deterministic commands for planner creation, plan admission, work-child creation, review, repair, requeue and dispatch. Reuse that law rather than inventing an operation registry.

Conceptually:

```text
root Job + admitted plan/step/revision role
  -> deterministic existing Executive child creation identity
  -> child Job
  -> deterministic company operation-key projection
```

### 6.2 One child Job is one delegated operation

Frozen invariant:

> One current Executive child Job equals one logical delegated operation.

Therefore:

- retry of the same child = new Attempt, same logical operation;
- safe provider/account/host rollover = new Attempt, same logical operation;
- repair after an independent rejecting review = distinct repair child Job;
- successor wave after a terminal child = distinct newly admitted child Job;
- intentionally repeated task at a later time = distinct root/child instance.

### 6.3 Manual transitional operation keys

Manual/transition Slack work may continue to use explicitly authored operation keys under current Skillpack law until that class is cut over.

Do not pretend those old keys were retroactively Executive-derived.

---

## 7. One canonical dialogue carrier

### 7.1 Carrier creation follows admission/placement identity

Autonomous operation order must be:

```text
canonical child exists
-> lawful current Attempt/Worker binding exists or exact worker-facing dialogue is otherwise required
-> ensure/reconcile one canonical dialogue parent
-> provider execution / reciprocal dialogue
```

Do not broadcast unassigned Slack messages as the source of responsibility.

### 7.2 Idempotent ensure semantics

Conceptual behavior:

```text
0 exact parent matches -> create once
1 exact parent matches  -> reuse
>1 exact parent matches -> CARRIER_BINDING_AMBIGUOUS / launch nothing
```

Slack write timeout/effect uncertainty must reread and reconcile the same prospective parent identity. Never create a second parent because the client did not receive a response.

### 7.3 Stable parent, Attempt-local messages

One child dialogue may contain P1 and P2 messages after a lawful rollover.

Historical message validity is judged against the stable parent plus a lawful applicability carrier, not by requiring every historical message to equal today's Attempt triple.

Current outbound writes still require the exact current actor/applicability binding.

### 7.4 Current owner

Mastermind #217 / MAS-200 remains the sole current WP-1R carrier for this compatibility repair. Its current scope must not be duplicated by this program.

---

## 8. Worker authority and stale provider surfaces

### 8.1 Physical provider windows are not authority

A Codex/Claude/Fable/native provider session can remain visually open after work moves or terminates.

Do not claim the UI itself is erased.

### 8.2 Sanctioned action must validate current execution authority

Before a worker can perform any sanctioned semantic or modifying action, the existing trusted execution/tool boundary must prove the relevant current facts, including where applicable:

```text
job_id still current
attempt_id still current
worker_id still owns the Attempt
lease/fence or Operator Harness equivalent still valid
quota/placement binding still current
dialogue binding still belongs to this child/current Attempt
operation is not terminal/superseded
requested action stays within the effective grant
```

If not:

```text
STALE_EXECUTION_BINDING / TERMINAL_OPERATION / CURRENT_ATTEMPT_MISMATCH
-> zero sanctioned modification
-> zero current RESULT authority
-> provider output may remain historical evidence only
```

### 8.3 RuntimeBinding role

RuntimeBinding remains the accepted routing/navigation/continuity projection and must remain ABA-safe.

It does not replace Executive Attempt/fence authority.

### 8.4 Cleanup is secondary

Where provider/process APIs support cancellation/stop, use them under existing safe reconciliation law.

Correctness must not depend on successfully closing a provider GUI/tab.

---

## 9. Provider-neutral semantic return projection

### 9.1 Provider model etiquette is not continuity

The autonomous organization must not depend on Codex, Claude or another model remembering to call Slack/MCP after finishing work.

A provider turn is subordinate evidence. Company semantic transitions are produced by the governed worker/harness boundary.

### 9.2 Closed turn-result family

The exact wire may be implemented by the existing Worker/Operator Harness owners, but it must support the semantic equivalent of:

```text
CONTINUE_WORK / PROGRESS
DECISION_REQUEST
BLOCKED
RESULT
terminal provider/execution failure with typed cause
```

A model may use bounded Company Dialogue tools during execution, but end-of-turn organizational projection cannot require voluntary use.

### 9.3 Projection journey

```text
provider turn/output
-> existing harness validates exact current Attempt/Worker/result
-> deterministic semantic-turn classifier
-> existing Agent Dialogue message/frame
-> canonical dialogue carrier
-> WP-TW attention
-> existing Wake
-> exact action-authoritative Sol target
```

For worker continuation after Sol acts, the inverse path uses the existing current RuntimeBinding / worker binding and canonical dialogue context.

### 9.4 Transport degradation

A healthy running Job does not become FAILED merely because Slack is temporarily unavailable.

If work is safely continuing inside a frozen task, it may continue.

When the worker reaches a semantic boundary requiring Sol, execution stops at that boundary until the company return can be durably/reconcilably projected.

Transport health is projected separately, e.g. `TRANSPORT_DEGRADED`; lifecycle remains Executive truth.

---

## 10. Exactly one Sol action authority per child turn

Merged #214 action-authority law remains controlling and is promoted here to an autonomous-cutover prerequisite.

For one unresolved child semantic turn:

```text
turn_owner = SOL
```

does not mean every Sol surface may act.

Exactly one resolved current Sol target is action-authoritative. Other Sols may observe/read/advice only.

Before any modifying Sol edge, the trusted continuation/action path must prove the current exact Sol binding.

If the target is unavailable:

```text
ATTENTION_OWNER_UNRESPONSIVE
-> reconcile/transfer existing responsibility/session binding
-> fresh Sol surface cold-starts from current protected sources
-> only after transfer may it act
```

If two active action-authoritative Sol bindings exist before divergent edges:

```text
ATTENTION_OWNER_CONFLICT
-> fail closed
```

Do not elect a winner by newest browser tab, Slack timestamp, provider health, visible activity or model guess.

---

## 11. Retry and rollover safety

### 11.1 Generic failure is not retry permission

Automatic requeue/rollover must require a typed deterministic retry-safe classification, not merely a broad terminal `FAILED`, `LOST` or provider error string.

Examples that may be eligible only when the owning current source law proves all required safety predicates:

- definitive pre-effect infrastructure failure;
- proven-dead process with no modifying effect ambiguity;
- exact non-modifying provider quota/rate-limit interruption under accepted OCR law;
- other explicitly enumerated safe retry classes.

### 11.2 Mandatory hold classes

These never auto-failover solely because another realm is available:

```text
EFFECT_UNKNOWN
write-capable interruption without definitive outcome
semantic/architecture failure requiring Sol judgment
authority conflict
unknown failure class
unreconciled provider/host response loss
ambiguous current writer/session identity
```

### 11.3 Same operation across safe retry

A retry/requeue keeps the same child Job/operation and creates the next lawful Attempt.

A cross-provider/account/host move follows existing Operator Continuity Attempt-boundary law and continuation-capsule ACK requirements.

### 11.4 Current owner

Operator Continuity / OCR-5/OCR-8 and the existing Executive retry/requeue owner remain authoritative. Do not add a continuity-specific retry service.

---

## 12. Cross-root concurrency and operational throughput

### 12.1 Company-scale requirement

The automated system must support many independent programs at once. A single serialized worker is not sufficient as the final fleet architecture.

### 12.2 Safe first production concurrency model

Initial autonomous fleet cutover should support:

```text
many independent root Jobs
-> each root at most one action-authoritative active child execution at a time
-> different roots may execute concurrently on distinct lawful Worker/quota/host realms
```

This captures most organizational throughput while preserving simple per-program sequencing.

### 12.3 No new scheduler

Extend the existing Executive service/runtime scheduling/composition to allow bounded concurrent dispatch across already-registered independent Worker realms.

Do not create another queue, task scheduler, fleet database or provider dispatcher.

### 12.4 Intra-root parallelism is later

Current strict COO plan may admit multiple logical children, but broad simultaneous write execution within one root is not automatically authorized by this amendment.

Before enabling intra-root parallel write-capable children, separately prove:

- per-child workspace/branch isolation;
- overlap/conflict detection for write paths;
- deterministic integration/review order;
- failure/cancellation isolation;
- no false completion from one sibling;
- Control Room truth for multiple simultaneous current children.

Until then, one active child per root is an intentional safety/fluency tradeoff.

### 12.5 Starvation and fairness

Fleet acceptance must prove that many roots do not silently starve behind one high-priority or long-lived program.

Use existing priority/capacity owners. If fairness policy must change, change it in the existing Executive scheduling owner with explicit source law; do not add a second fairness queue.

---

## 13. Workspace / Git authority

Automated identity safety does not solve Git collisions by itself.

A write-capable child must have an accepted workspace/branch authority that is compatible with its concurrency mode.

For the initial one-active-child-per-root fleet:

- each root's active child may use the existing root-bound reviewed workspace/branch law;
- two different roots must not accidentally share a mutable workspace unless current Executive workspace law explicitly proves that arrangement safe;
- provider/Attempt replacement must preserve or safely rotate the exact Job workspace under existing reconciliation law;
- stale Attempts cannot retain accepted write authority after their fence/binding is invalidated.

Intra-root parallel branch/worktree fanout remains separately gated as §12.4.

---

## 14. Placement and provider policy

The normal autonomous path remains:

```text
Chairman intent
-> Sol freezes strategic boundary / logical capability class
-> canonical Executive request/root admission
-> deterministic child Job
-> Model Router suitability
-> Capacity Fabric fresh eligible placement
-> Executive Attempt/Worker claim
-> provider adapter/harness execution
```

The Chairman does not choose a routine quota account/session.

No legal capacity:

```text
WAITING_CAPACITY / needs_placement
```

not:

```text
ACCOUNT_BINDING: CHAIRMAN_SELECTS
```

for ordinary capacity-selectable work.

Manual binding remains only an explicit transition/Chairman opt-in exception under the current Skillpack until the relevant work class is cut over.

Mastermind #215 remains the sole current Skillpack release carrier for that manual-handoff procedural correction. Do not duplicate its five-file surface here.

---

## 15. Strategic authority modes

Automated delegation does not mean all company thinking becomes an autonomous worker cycle.

### 15.1 Full automatic bounded execution

Appropriate for a frozen child whose mission, authority, data contract, failure behavior and acceptance test are sufficiently explicit, including bounded implementation, research, testing and independent review.

### 15.2 Sol-governed strategic program

Product/architecture/intelligence programs remain Sol responsibilities. Sol may admit bounded implementation/research/review children automatically after architecture/scope is frozen.

Workers do not infer or widen the company thesis merely because the parent program is broad.

### 15.3 Chairman/admin gate

Credentials, new permissions, material spend, materially new company intent, irreversible authority changes and other genuinely Chairman-only decisions remain `needs_chairman`.

Routine provider capacity selection is not a Chairman gate.

---

## 16. Control Room / Steward product law

The Executive Steward / Control Room is the normal operating cockpit and must distinguish identity, execution, turn ownership and transport rather than flattening them into one fake status.

Minimum useful responsibility projection after the relevant owners are live:

```text
parent/workstream
current child Job / human display name
canonical operation identity
Executive lifecycle state
current Attempt / Worker
provider / opaque realm / host when lawful and known
current RuntimeBinding generation
canonical dialogue carrier
latest valid semantic edge
turn_owner role
exact action-authoritative target when known
attention health
transport health
retry/rollover safety state
parent active/no successor condition
current GitHub carrier/evidence
needs_sol
needs_worker_or_coo
needs_placement
needs_chairman
exception reason codes
exact next lawful action
source owner + freshness / unknown reasons
```

Old provider surfaces may remain available as history/debug evidence but must be clearly non-actionable:

```text
SUPERSEDED
TERMINAL
STALE_BINDING
NON_ACTIONABLE
```

They must not appear under normal `Needs Worker`, `Resume`, `Open Current Session`, `Needs Chris` or equivalent action queues.

The normal Chairman summary should make genuine escalation scarcity obvious, e.g. `Needs Chris: 0` when no Chairman decision exists.

---

## 17. Slack final role

After accepted cutover for a work class:

- Slack may carry human-readable/machine dialogue projection and audit evidence;
- Slack is not the task queue;
- Slack top-level messages do not originate autonomous responsibility after Executive admission is live;
- duplicate Slack delivery cannot create a second Job/Attempt;
- missing Slack projection cannot silently hide a worker return from Steward/attention forever;
- the Chairman is not required to open the channel.

No actionable company state may exist only in `#agent-dispatch`.

---

## 18. Current implementation-owner subtraction

This amendment explicitly preserves current carriers. At the protected basis named above:

### Already protected — do not rebuild

- #214 continuity/project-management/action-authority source law;
- #209 WP-TW1 classifier;
- #210 Company Dialogue MCP;
- #216 WP-TW2 observer -> Wake bridge;
- #220 production-disarmed real Slack Web API client;
- merged Wake provider-native transport predecessor;
- existing Executive strict-v2 COO lifecycle/idempotent command machinery;
- existing Operator Continuity continuation contracts and Attempt-boundary law.

### Existing in-flight owners — reconcile, do not replace

- **#217 / MAS-200** — Agent Dialogue V2 RESULT->CONTINUE and P1->P2 same-parent applicability compatibility;
- **#221** — private long-running Agent Relay runtime over the accepted Slack client;
- **#223** — stacked native Agent Relay enrollment/install ceremony; it must reconcile its moving #221 base rather than become a replacement runtime;
- **#222 / MAS-206** — OCR-6R pure Executive Steward read core;
- **#215** — Skillpack/manual-handoff placement/precommission correction;
- existing Capacity Fabric / RF/HF/PF / Operator Continuity/OCR carriers;
- #170 Session Truth where still required for accepted current-source joins;
- #188 Secretary/OpenClaw/Web-Sol architecture and its current bounded descendants.

### New implementation surfaces this amendment identifies

They are new **bounded responsibilities inside existing owners**, not a new program/control plane:

1. automated transport-neutral CEO admission identity;
2. deterministic Executive-child -> company operation identity projection;
3. harness-owned semantic return projection at turn boundaries;
4. runtime enforcement of exact Sol action-authority binding/transfer;
5. typed retry-safe classification/fence before automatic requeue/rollover;
6. cross-root parallel Executive dispatch over multiple existing Worker realms;
7. Steward/Control Room fields and cutover logic required to make stale surfaces non-actionable and Slack unnecessary.

The implementation plan must assign each to an existing owner and check path collisions before commission.

---

## 19. Failure-state matrix

| Condition | Required behavior |
|---|---|
| same identified request concurrently enters two approved frontends | one automated root / same receipt; zero second Job |
| same request identity + changed normalized envelope | conflict/refuse; zero mutation |
| two Sols try to admit the same already-canonical Executive child | deterministic child identity reconciles one child; zero sibling duplicate |
| two unrelated free-form messages look semantically similar | no authoritative fuzzy dedupe; optional read-only overlap warning only |
| Slack parent write times out | reconcile exact parent identity; never blind-create second parent |
| >1 exact dialogue parents already exist | `CARRIER_BINDING_AMBIGUOUS`; launch/write held pending reconciliation |
| provider launch outcome may have occurred | `EFFECT_UNKNOWN`; same Attempt/realm reconciliation; no alternate launch |
| stale P1 calls a sanctioned worker tool after P2 became current | stale/current-Attempt refusal; evidence only |
| stale provider UI remains open after STOP | zero sanctioned authority; UI cleanup optional secondary action |
| worker safely executing while Slack is unavailable | Job remains truthful; transport degraded; continue only until next semantic boundary requiring company return |
| worker returns semantic blocker/result while Slack unavailable | preserve typed current-Attempt result; hold at boundary; reconcile projection; no duplicate execution |
| Sol target is dead | `ATTENTION_OWNER_UNRESPONSIVE`; reconcile/transfer exact Sol binding, then fresh Sol acts |
| two Sol action bindings exist | `ATTENTION_OWNER_CONFLICT`; observers cannot modify |
| generic semantic `FAILED` with unknown cause | no blind auto-retry; needs classification/Sol/reconciliation |
| exact safe non-modifying quota exhaustion | current OCR safety predicate may allow same-Job requeue/new Attempt/realm |
| write-capable or effect-unknown interruption | zero automatic failover |
| all eligible capacity unavailable | `WAITING_CAPACITY`; no Chairman quota-selection requirement |
| child terminal, parent active, no admitted successor | `PARENT_ACTIVE_NO_SUCCESSOR / needs_sol`; no automatic child B |
| material mission changed | safely cancel/close/reconcile old child; admit distinct new child identity |
| same business procedure intentionally repeated later | valid new root/child instance |
| control host restarts | reconcile durable Attempts/processes/session evidence first; no blind dispatch |
| remote host response lost after possible effect | same Attempt/host reconciliation; no cross-host retry |
| many roots compete for capacity | bounded scheduling with visible waits; no silent starvation |

---

## 20. Production cutover stages

Do not flip the full company from Slack-manual handoff to automation in one release.

### Stage 0 — Current / manual-transition

Manual carriers remain under current Skillpack safety law. OSC continuity watch may remain temporary compatibility scaffolding. Chairman-facing pain is still acknowledged, not normalized.

### Stage 1 — SHADOW

For selected work classes, the new system derives proposed request/child identity, turn owner, placement and retry decision but does not launch autonomous provider execution.

Compare against real current operator decisions. Measure false duplicate/conflict/placement/retry classifications.

### Stage 2 — CANARY

2–3 bounded responsibilities, including at least one read-only/research task and one isolated code task.

Chairman provides initial intent only. No Slack monitoring or provider-account choice.

### Stage 3 — SMALL FLEET

5–10 concurrent independent roots across multiple proven Worker realms. One active child per root remains the default.

Control Room is the normal monitor. Slack is audit/debug only.

### Stage 4 — PRODUCTION FLEET

20–30+ concurrent responsibilities with demonstrated bounded scheduling latency, no hidden starvation, safe Sol/worker continuation, capacity saturation behavior and production Control Room truth.

### Stage 5 — ADVANCED INTRA-ROOT PARALLELISM

Only after the separate workspace/integration requirements in §12.4 are proven.

Temporary manual/session-local watcher scaffolding is retired only after the corresponding canonical attention path is production-proven.

---

## 21. Required acceptance canaries

### Canary A — cross-ingress duplicate root race

Submit one already-identified request simultaneously through two approved automated frontends.

Expected:

```text
one durable root Job
one canonical request receipt identity
one planning/orchestration lineage
zero second root
```

Then change one material normalized field under the same request identity and require conflict/refusal.

### Canary B — sister-Sol same-child race

Two Sol surfaces independently observe the same unresolved parent responsibility and attempt to admit its same canonical child.

Expected:

```text
one Executive child
one operation identity
one dialogue parent
zero duplicate Worker launch
```

### Canary C — provider launch response lost

Lose the client response after provider/Worker launch may have begun.

Expected:

```text
same Attempt only
EFFECT_UNKNOWN / reconciliation
zero alternate Worker/provider/host
zero duplicate dialogue parent
```

### Canary D — stale worker after rebound

Run P1, safely terminalize/requeue, establish P2, then make P1 attempt a current worker semantic/tool action.

Expected: P1 is refused as stale; P2 remains sole current action-authoritative executor.

### Canary E — Codex/Claude mechanical return projection

Provider completes or blocks without voluntarily calling Slack/Company MCP.

Expected: governed harness produces the semantic company return and the exact Sol attention path without Chairman intervention.

### Canary F — sleeping Sol

Worker return arrives while the action-authoritative Sol reasoning surface is inactive.

Expected: exact Sol target wakes/resumes or is canonically transferred if unavailable; no sister Sol acts before transfer.

### Canary G — Slack unavailable

Interrupt Agent Relay/Slack transport while a safe bounded worker is running.

Expected: runtime remains truthful; work does not falsely fail solely due to transport. At the next semantic boundary the return is preserved/held and projection is reconciled without duplicate execution.

### Canary H — retry taxonomy

Inject separately:

1. definitive pre-effect infrastructure failure;
2. generic semantic failure;
3. write-capable effect-unknown loss;
4. exact non-modifying quota exhaustion.

Expected: only explicitly retry-safe cases requeue/roll over. Generic semantic failure and effect-unknown do not.

### Canary I — cross-root parallel fleet

Run at least five independent roots on distinct lawful Worker realms concurrently.

Expected:

```text
multiple simultaneous active Attempts across roots
one active action-authoritative child per root
no shared-worker double claim
no duplicate Job/carrier
bounded progress for lower-priority roots
```

### Canary J — stale Chairman navigation

Create a superseded provider/session binding and keep the old native task physically available.

Expected: Control Room exposes only the current actionable binding in normal queues; old surface is history/debug with `STALE_BINDING / NON_ACTIONABLE` semantics.

### Canary K — parent continuation

Finish child A correctly while parent remains active with authored next dependency and no successor.

Expected: `PARENT_ACTIVE_NO_SUCCESSOR / needs_sol`; Sol admits or parks B only after current-state reconciliation.

### Canary L — Chairman zero-touch production journey

Across a representative multi-project period include:

- worker return;
- Sol continuation;
- provider/session loss;
- safe retry/rollover;
- unsafe effect-unknown hold;
- capacity saturation;
- child terminal + active parent;
- stale provider surface;
- at least one genuine Chairman decision and multiple non-Chairman operational exceptions.

After initial intent the Chairman performs:

```text
zero Slack archaeology
zero message shuttling
zero watcher repair
zero Sol-tab waking
zero worker-tab waking
zero provider account/session selection
zero stale-task hunting
```

Control Room/Linear/Grok surface every meaningful state and only genuine Chairman gates appear as `Needs Chris`.

---

## 22. Operational learning

Use existing canonical events/receipts and read-only derived telemetry. Do not add another metrics truth database solely for this program.

Track at minimum where source evidence permits:

```text
duplicate admission reconciliations
operation conflicts
carrier ambiguity incidents
provider launch effect-unknown count/duration
stale binding refusals
worker semantic-return projection latency
Sol attention/wake/transfer latency
Sol action-owner conflicts
safe vs refused retry counts by typed cause
WAITING_CAPACITY duration
cross-root queue/wait latency
worker realm utilization
root starvation/fairness indicators
parent-orphan detections and resolution latency
manual Chairman placement frequency
Chairman Slack-touch count during acceptance canaries
```

Unknown denominators remain unknown. These metrics are descriptive V1 learning and do not dynamically grant authority or rewrite routing policy.

---

## 23. No-rebuild and non-goals

This amendment does not authorize:

- a new delegation/operation registry;
- semantic-embedding dedupe as modification authority;
- a new scheduler or queue;
- a new retry plane;
- a new provider/session database;
- a new Sol owner/election database;
- Slack as lifecycle/task truth;
- one persistent provider session per program as organizational identity;
- automatic successor-child creation from child STOP;
- automatic retry of generic `FAILED` or `EFFECT_UNKNOWN`;
- provider/account/host change inside the same Attempt when existing Attempt-boundary law requires a new Attempt;
- broad intra-root parallel writes before workspace/integration proof;
- Grok/OpenClaw/browser state selecting action authority;
- model-generated summaries deciding lifecycle, dedupe, placement, retry or completion;
- bypassing branch protection or treating green CI as production acceptance.

---

## 24. Precedence / supersession

This amendment has narrow precedence over earlier continuity/plan language only for the following topics:

1. automated root identity is transport-neutral for the new cutover path; historical v1 transport-specific intent identity remains compatibility history;
2. autonomous child operation identity is derived from canonical Executive/organizational lineage rather than freely model-authored naming;
3. content-addressed commission provenance is not long-lived operation identity;
4. stale-provider safety is enforced by current Executive Attempt/Worker/fence/tool binding, with RuntimeBinding as routing/continuity projection;
5. provider return projection is a governed harness responsibility, not model etiquette;
6. automatic retry requires typed retry-safe classification;
7. cross-root multi-worker concurrency is a production-cutover requirement while broad intra-root parallelism remains separately gated;
8. full cutover requires Control Room to hide stale/non-actionable native surfaces from normal action queues.

All #214 no-rebuild, action-authority, parent-continuation, Slack role, Capacity/Operator Continuity, OCR-6 and project-management laws remain controlling unless explicitly narrowed above.

Existing implementation carriers retain authority over their current scopes. This document must not be used to reopen landed work or create replacement carriers.

---

## 25. Completion standard

This amendment becomes `PROVEN_LIVE` only through the combined accepted implementation owners and real canaries—not because this records file merges.

Completion requires:

- **Truth:** one canonical operation/root/child identity per work instance, current Attempt/fence truth, correction-safe dialogue lineage and explicit unknown/effect-unknown behavior;
- **Intelligence:** deterministic turn owner, exact action target, retry-safety classification, parent continuation and transport/attention exceptions;
- **Product:** Control Room/Linear/Grok let the Chairman operate the company without Slack or session archaeology;
- **Execution:** multiple independent roots can use lawful worker capacity concurrently without duplicate claims/carriers or Chairman account selection;
- **Continuity:** provider and Sol reasoning surfaces are replaceable without losing organizational responsibility;
- **Learning:** the system measures duplicates, stale bindings, attention latency, retry decisions, capacity waits, starvation and Chairman intervention.

Final release ruler:

> Mastermind may call autonomous delegation production-ready only when a realistic multi-project fleet can run with the Chairman outside `#agent-dispatch`, stale provider sessions cannot regain sanctioned authority, two Sols cannot create duplicate children or divergent executive turns, provider/model silence cannot hide a semantic return, and provider failure produces either a lawful same-operation continuation or an explicit safe hold—not organizational chaos.
