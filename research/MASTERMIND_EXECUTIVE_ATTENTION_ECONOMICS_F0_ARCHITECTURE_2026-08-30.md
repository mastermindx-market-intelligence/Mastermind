# Mastermind Executive Attention Economics — F0 Architecture Freeze

**Operation:** `mastermind-executive-attention-economics-20260830-sol-001`  
**Program role:** `PROGRAM_CEO`  
**Cognition route:** `CHAT_PRO_DEFAULT`  
**Status:** `ARCHITECTURE_FREEZE / SPEC_ONLY / RECORDS_ONLY`  
**Frozen from protected Mastermind:** `8f0babf473e6e4e8efce697014bd48c594227d94`  
**Observed Macro main:** `ca31568272d06f2472f65946d2435517611f31dc`  
**Skillpack:** `v1.0.1`, bootstrap major `1`  
**Architecture owner:** Sol, Program CEO  

This document freezes the missing executive-attention allocation layer before implementation. It creates no live queue, scheduler, Wake route, lifecycle transition, authority grant, worker placement, browser action, Slack action, or Control Room ranking by itself.

## 1. Chairman outcome

Mastermind already has increasingly strong answers to **what work exists**, **who owns it**, **what runtime is active**, **who owes the next semantic turn**, **what attention obligation exists**, and **where the corresponding surface is**. At portfolio scale that is not sufficient.

The missing problem is:

> When many responsibilities legitimately request scarce Chairman/Sol cognition at once, which requests merit interruption now, which should be the next focus, which belong in a context batch, which can safely continue autonomously, which are valid waits, and which must be reconciled before anyone trusts the prioritization?

The end-state is not a better inbox. It is an **Executive Attention Frontier** that reduces executive scanning and interruption while making urgent risk, authority, freshness, intentional waits, and anti-starvation behavior explicit.

Priority and authority are different dimensions. A high-priority Sol decision does not become a Chairman decision. A low-urgency Chairman-only decision remains Chairman-only. No priority result may grant permission to mutate state.

## 2. Product thesis

Executive attention is an expensive, interruptible reasoning resource. The allocation system should spend it only when the expected cost of delay, missed option, blocked dependency, active harm, or active resource burn justifies the cognitive and switching cost.

The product should therefore answer six questions in one glance:

1. **Who has the authority to act?**
2. **Does cognition need to happen at all yet?**
3. **If yes, must it interrupt, be next focus, or can it batch?**
4. **What changes if we decide now versus later?**
5. **What work can safely continue while the decision waits?**
6. **Can the evidence be trusted at the precision implied by the recommendation?**

The value is organizational, not cosmetic:

- fewer Chairman interruptions for routine Sol decisions;
- fewer Sol context switches across unrelated programs;
- faster response to real production/user risk and expiring decision windows;
- explicit preservation of useful waiting and evidence collection;
- less duplicate attention from symptoms of one root blocker;
- visible old work that would otherwise starve;
- no hidden authority escalation from urgency or LLM judgment;
- a compact machine-readable frontier that Chat-native Meta-CEO and Program CEOs can consume without scanning the estate.

## 3. Current owner map — do not rebuild

The Executive Attention Frontier is a **derived read consumer**. Existing owners remain authoritative.

| Concern | Canonical owner | EAF relationship |
|---|---|---|
| Job / Attempt / Worker lifecycle, admission, lease/fence, effect reconciliation | Executive OS | Read only; never mutate or reinterpret lifecycle |
| Durable workstreams, decisions, discoveries, handoffs, dependencies, authored waits, `needs_ceo` | Agent OS | Read source-attributed organizational facts |
| Exact current reasoning/execution surface | RuntimeBinding / accepted session-binding owners | Read only; never manufacture session identity |
| Attention obligation, delivery/ACK/source identity | Executive Inbox / Wake | Consume obligations; never become Wake owner |
| Semantic turn ownership | current continuity / turn-owner projection | Input to cognition admission; never become turn owner |
| Provider/account/model eligibility and placement | Model Router + Capacity owners | Read resource-burn/capacity context only; never place workers |
| Responsibility/runtime/attention/surface composition | Executive Steward / OCR-6 | Primary normalized read seam once corrected and protected |
| Chairman operating composition | Control Room | Consumer of EAF; no new Control Room truth store |
| Implementation/evidence | GitHub | Canonical implementation and proof |
| Selected project tracking | Linear | Projection only |
| Transport/hot-state | Slack / Agent Relay | Transport only |
| Workroom composition | Project Workroom Projector | Parallel read consumer; EAF does not become Workroom owner |

### OCR-6 dependency

At freeze time Mastermind PR #228 is the real OCR-6 Executive Steward carrier and is open with a known correctness blocker: presentation filtering must not occur before full canonical identity grouping. A sole repair writer already exists. EAF implementation **must not fork, modify, or bypass that repair**. Any wave that consumes the Steward contract is gated on a corrected protected Steward base.

## 4. Capability ledger at freeze

| Capability | State | Ruling |
|---|---|---|
| Agent OS responsibility/decision/wait/dependency records | `PROVEN_LIVE` | Durable organizational source; not scheduler/queue |
| Executive lifecycle/admission/effect authority | existing canonical owner | EAF consumes; never duplicates |
| Wake obligation contract / source-attributed attention | `PARTIAL` at organizational end-to-end level | Existing owner; EAF never owns delivery |
| Chat-native Meta-CEO architecture | `SPEC_ONLY / ARCHITECTURE_FROZEN` | Intended executive consumer |
| OCR-6 Executive Steward PR #228 | `BUILT_NOT_PROVEN / KNOWN_CORRECTNESS_BLOCKER / PRODUCTION_INERT` | Correctness repair must land first |
| Chairman Control Room P0A/H0 | `PROVEN_LIVE` | Existing operating surface |
| Control Room X1 | `ACCEPTED / PROVEN_LIVE_LOCAL` | Existing read-only product surface |
| AD-CR1 full zero-Slack operational cockpit | `TODO / WAITING_STEWARD_AND_ACTION_PROJECTIONS` | Future consumer seam |
| Executive Attention Frontier engine | `NOT_BUILT` | This program owns it |
| EAF Control Room projection | `NOT_BUILT` | This program owns bounded consumer integration |
| EAF Chat-native Meta-CEO / Program CEO projection | `NOT_BUILT` | Required end-state consumer |
| Real portfolio reduction in Chairman interruptions without missed severe decisions | `NOT_PROVEN` | Final promotion evidence |

## 5. Research rulings

### 5.1 SRE: bother a human only for actionable work

Google SRE distinguishes immediate human action, non-immediate human action, and information that should merely be logged. Its on-call guidance emphasizes high signal-to-noise and immediately actionable pages; practical alerting also explicitly supports inhibition, deduplication, fan-in and fan-out.

**Ruling:** EAF must first decide whether scarce cognition is actually required. Healthy autonomous progress and informational state do not enter an executive decision queue merely because they are interesting.

Primary references:

- https://sre.google/sre-book/introduction/
- https://sre.google/workbook/on-call/
- https://sre.google/sre-book/practical-alerting/
- https://sre.google/resources/practices-and-processes/incident-management-guide/

### 5.2 Scheduling: no universal scalar is justified

Single-machine weighted-completion rules are optimal only under narrow assumptions. Add precedence constraints, release dates, heterogeneous objectives or multiple scarce resources and the scheduling problem changes materially; precedence-constrained weighted completion is NP-hard. Deadline-first rules optimize a different objective from weighted completion. Strict priority also risks starvation.

**Ruling:** do not manufacture `priority_score = 87.4` and pretend it is globally meaningful. Use closed admission/disposition classes, a partial order, Pareto dominance on source-backed factors, and deterministic local service rules.

References:

- Hall, Schulz, Shmoys & Wein, *Precedence constrained scheduling to minimize sum of weighted completion times on a single machine*, Discrete Applied Mathematics 98 (1999), DOI 10.1016/S0166-218X(98)00143-7.
- Standard single-machine weighted-completion / Smith-rule literature is useful only as a local analogy, not a company-wide optimizer.

### 5.3 Critical paths require real timing data

Critical Path Method depends on explicit network logic, durations and float. Raw descendant count is not a critical path.

**Ruling:** V1 may expose exact downstream unblock leverage from Agent OS dependencies, but may not label it `critical path`, `float`, or `slack` unless the required duration/schedule facts actually exist.

Reference:

- https://www.pmi.org/learning/library/critical-path-method-calculations-scheduling-8040

### 5.4 Value of information and option value of waiting

When an action is costly to reverse and useful information is expected to arrive, waiting can have positive option value. Bernanke's irreversible-investment model explicitly frames acting when costs of further deferral exceed expected information value; later real-options work likewise shows that immediate action rules can ignore valuable waiting.

**Ruling:** an explicit valid wait is not backlog failure. EAF must preserve intentional evidence waits and must not let simple aging turn them into false urgency. Uncertainty without an authored evidence/wait path, however, is not automatically valuable waiting; it may be a reconciliation problem.

References:

- https://www.nber.org/papers/w0502
- https://www.nber.org/papers/w1019

### 5.5 Interruption science: switching has recovery cost

Microsoft Research studies of information workers and developers document difficulty shifting among numerous tasks, longer resumption cost for irrelevant interruptions, and reliance on notes/cues when resuming interrupted programming work.

**Ruling:** context affinity and batching are legitimate local tie-breakers when urgency is comparable, but they may never suppress a true interrupt.

References:

- https://www.microsoft.com/en-us/research/?p=157989
- https://www.microsoft.com/en-us/research/publication/effects-of-instant-messaging-interruptions-on-computing-tasks-2/
- https://www.microsoft.com/en-us/research/?p=159976

## 6. Core architecture — Executive Attention Frontier

The architecture is a pure deterministic transform:

```text
canonical source facts
  -> normalized attention demands
  -> authority partition
  -> cognition-admission gate
  -> disposition classifier
  -> exact root-cause / context bundler
  -> Pareto frontier + deterministic local service policy
  -> read-only projections
       - Chairman Control Room
       - Meta-CEO / Program CEO compact context
       - forensic raw drilldown
```

It has **no durable mutable queue state**. A new canonical snapshot yields a new frontier. Corrections naturally change the next projection.

### 6.1 Inputs

Required families are source-attributed facts from existing owners. The exact implementation contract may reuse corrected Steward types and add bounded immutable read-context types where Steward does not expose a needed Agent OS fact.

Candidate facts include:

- canonical `responsibility_ref` and accountable/target seat;
- one or more Wake/Executive Inbox attention obligations;
- authored Agent OS `needs_ceo` question/options/recommendation/`by_when` when present;
- Agent OS dependency edges and wave readiness;
- Agent OS `blast_radius` and ambiguity;
- Agent OS authored wait `kind`, `review_after`, `condition`;
- Executive runtime/blocker/effect facts;
- RuntimeBinding continuity facts;
- exact source-backed user/production-impact facts when an owner actually supplies them;
- Capacity/runtime evidence for active resource burn when available;
- source event/decision timestamps that truly mean `became_actionable_at` or equivalent;
- source freshness/conflict state.

Retrieval time is not ready time. A refreshed observation timestamp must never reset age.

### 6.2 Authority partition — absolute boundary

`authority_requirement` is derived before priority/disposition and is immutable to all later stages.

Canonical classes are conceptual mappings onto existing source-law seats/owners, for example:

- `CHAIRMAN`
- `SOL`
- `COO_OR_WORKER`
- `EXECUTIVE_PLACEMENT`
- `ADMIN_OR_EXTERNAL`
- `NONE`
- `UNKNOWN`

The implementation should reuse existing accepted vocabulary where possible instead of minting a competing ontology.

Hard laws:

1. Priority never changes authority.
2. `needs_ceo` does not itself mean `needs_chairman`.
3. Chairman-only requires an actual current authority/admin/spend/consent/strategy gate from an accepted owner or law.
4. Routine Sol choices inside delegated authority remain Sol even if very urgent.
5. Unknown/conflicted authority fails to reconciliation; it does not default upward to Chairman.
6. EAF cannot authorize, execute, dispatch, retry, merge, release, spend, rotate credentials, or mutate runtime state.

### 6.3 Cognition-admission gate

Before ranking anything, EAF asks whether executive cognition is currently useful and actionable.

Exclude from the active executive frontier when canonical facts show:

- terminal/non-actionable state;
- healthy autonomous progress with no current executive decision gate;
- valid authored wait that has not reached its review boundary and whose known condition is unsatisfied;
- existing owner/worker/placement turn rather than executive turn;
- duplicate symptom covered by a visible exact-root bundle.

Do not exclude merely because an optional impact/dependency factor is unknown.

### 6.4 Closed disposition classes

Every admitted demand gets exactly one read-only disposition:

#### `INTERRUPT_NOW`

A human/executive action is required immediately or before the next ordinary focus boundary to prevent source-backed active harm, imminent irreversible loss, or an expiring response window. This class bypasses batching/fairness quotas. It must be rare and strongly evidenced.

#### `FOCUS_NOW`

Executive cognition should be the next safe focus after the current atomic operation: meaningful cost of delay, no safe autonomous progress, strong dependency unblock, material active resource burn, or a source-backed decision window makes ordinary batching unsafe, but hard preemption is not justified.

#### `BATCH_NEXT`

A valid executive decision is needed, but it can safely wait for the next related context batch without material expected harm. This is the normal executive work class.

#### `AUTONOMOUS_CONTINUE`

No executive cognition is required before the current autonomous/worker/placement path can make safe useful progress. The item may remain observable with its next review condition but is removed from active executive demand.

#### `VALID_WAIT`

Agent OS explicitly records a legitimate evidence/external/calendar/action wait and the review boundary has not been reached. The wait remains visible as intentional state and does not accrue false urgency merely from age.

#### `RECONCILE_FIRST`

Required identity, authority, freshness, effect, or source facts are stale/conflicted/unknown at a precision that makes prioritization unsafe. The output explains exactly what must be reconciled. `EFFECT_UNKNOWN` always lands here for any decision that would imply replay/failover/mutation.

#### `COVERED_BY_BUNDLE`

The demand is a visible member of an exact canonical root-cause bundle whose root card is on the active frontier. The member is never deleted and remains drillable with its receipts.

#### `NON_ACTIONABLE`

Terminal, informational, superseded, or otherwise correctly outside current cognition allocation.

These are **attention dispositions, not lifecycle states**.

## 7. Factor model — vectors, not a magic score

Within actionable dispositions, EAF derives a source-backed vector. Unknown values remain unknown and cannot silently count as zero.

### 7.1 Time pressure

Representative ordinal states:

- `WINDOW_BREACHED`
- `WINDOW_CRITICAL`
- `WINDOW_NEAR`
- `OPEN`
- `UNKNOWN`

Use explicit `by_when`, external windows, incident state, or owner-supplied response constraints. Do not guess response lead time from prose.

### 7.2 Impact pressure

Separate actual current impact from architectural blast radius.

Examples:

- source-backed active production/user harm;
- user-blocking but contained issue;
- program/dependency blocking;
- no current harm;
- unknown.

`blast_radius: user_facing` means a change can affect users; it is not proof that users are currently harmed.

### 7.3 Reversibility / consequence

Use Agent OS blast-radius and accepted operation/source facts:

- irreversible / authority-sensitive;
- costly reversal;
- reversible;
- unknown.

Reversibility influences option value and required evidence, never authority by itself.

### 7.4 Dependency-unblock leverage

Calculate only from exact Agent OS dependency identities and readiness facts:

- root blocker for multiple currently-ready descendants;
- single direct unblock;
- local/no unblock;
- unknown.

Expose the exact blocked member set. Do not call this `critical path` without durations/float.

### 7.5 Active resource burn

Use only source-owned runtime/capacity evidence, e.g. workers/attempts or expensive scarce capacity provably idle or blocked on the decision.

Unknown burn is unknown, not zero. Burn may increase attention pressure but does not authorize cancellation/retry/failover.

### 7.6 Autonomy remaining

- `NO_SAFE_PROGRESS`
- `PARTIAL_SAFE_PROGRESS`
- `FULL_SAFE_PROGRESS`
- `UNKNOWN`

This is central to reducing interruptions: a valuable decision that does not yet block safe progress should normally batch rather than interrupt.

### 7.7 Information / wait option

- explicit expected information before review boundary;
- no expected information / delay only decays options;
- authored external/calendar wait;
- unknown.

No model may invent an expected-information event merely because a case is uncertain.

### 7.8 Evidence quality

For every load-bearing factor expose:

- owner;
- exact source ref;
- event/effective time if available;
- observation time;
- freshness;
- conflict/unknown state.

Low evidence quality does not mechanically mean low priority. It can force `RECONCILE_FIRST`.

### 7.9 Ready age / fairness

Use the earliest source-backed moment the same unresolved demand became actionable. Cosmetic updates, regenerated files, repeated Wake delivery, or observation refresh must not reset it.

If canonical ready time is unavailable, report fairness age `UNKNOWN`; do not invent an allocator-local clock or queue row to compensate.

### 7.10 Context affinity

Context affinity is a local switching-cost tie-breaker only:

- same exact responsibility;
- same program/root bundle;
- unrelated program;
- unknown.

It never suppresses `INTERRUPT_NOW` or changes authority.

## 8. Partial order and frontier selection

EAF combines **closed classes + partial ordering + local deterministic service**, rather than one weighted sum.

### 8.1 Hard precedence

1. `RECONCILE_FIRST` is never presented as a trusted action recommendation.
2. `INTERRUPT_NOW` is always visible and may preempt other cognitive work.
3. `FOCUS_NOW` is next after current atomic safety boundaries.
4. `BATCH_NEXT` is served in context-efficient groups with fairness protection.
5. `AUTONOMOUS_CONTINUE`, `VALID_WAIT`, `COVERED_BY_BUNDLE`, and `NON_ACTIONABLE` remain observable but do not consume active frontier slots.

### 8.2 Pareto dominance

Within the same authority partition and disposition, compare only source-backed comparable pressure dimensions. Demand A may dominate demand B only if A is no worse on every comparable load-bearing pressure dimension and strictly stronger on at least one, with no unknown/conflict that invalidates the comparison.

Unknown optional dimensions make items less comparable, not automatically less important.

The non-dominated set is the raw **attention frontier**.

### 8.3 Compact service selection

A UI/API does not have to dump every non-dominated item. It may select a compact set using deterministic local rules:

1. all `INTERRUPT_NOW` items;
2. the most time-constrained/root-unblocking `FOCUS_NOW` bundle(s) per authority partition;
3. context-adjacent `BATCH_NEXT` bundles that can be decided together;
4. one **oldest-ready fairness sentinel** per active executive authority partition when backlog exists.

The fairness sentinel is an anti-starvation visibility/service rule, not a quota. It never suppresses emergencies. A valid intentional wait is excluded from fairness aging until review is due.

## 9. Exact root-cause fan-in and batching

EAF may automatically bundle only on hard canonical relations, such as:

- same exact Agent OS decision/ref;
- same exact blocker/root responsibility;
- same Wake source/correlation/root Job where source law defines equivalence;
- explicit dependency root;
- exact same release/review gate identity.

It must **not** auto-deduplicate or suppress work because titles, embeddings, prose, or an LLM say two items are similar.

A bundle has a deterministic identity derived from the canonical root + ordered member identities. It stores no mutable queue record.

If members require different authority, they may share a visual context group but must remain separate action decisions. A Chairman-only member may never cause the Sol members in the same context group to become Chairman work.

A root card must show:

- why the root deserves cognition;
- exact member/fan-out count;
- what decisions/work it unblocks;
- which members are only symptoms;
- authority of each actionable decision;
- source receipts.

## 10. Valid waits and option value

Agent OS already models waits as organizational state, not scheduling authority. EAF preserves that law.

A future `review_after` is a strong reason not to interrupt merely because the item is old. When `review_after` passes, the wait becomes **due for review**; the underlying wait record is not erased, but the cognition gate is reconsidered using current facts.

If an explicit condition has become true from a canonical observable source, the demand may re-enter. If the condition cannot be observed, do not hallucinate that it cleared.

An `UNKNOWN` caused by stale/missing evidence is not automatically `VALID_WAIT`. It is often `RECONCILE_FIRST`.

## 11. Failure and anti-gaming law

### 11.1 Priority inflation

Free-form words such as `urgent`, `critical`, or `CEO` in titles/prose carry zero direct priority authority. Every factor must name an accepted source owner.

`needs_ceo` admits a question into CEO consideration; it does not set urgency, Chairman authority, impact, or a score.

### 11.2 Timestamp gaming

Repeated notification, projection refresh, branch update, file modification, or regenerated summaries may not reset `became_actionable_at`.

### 11.3 Duplicate alert storms

Repeated equivalent obligations fan in by exact identity/root. Suppression is allowed only when the visible bundle preserves every member receipt.

### 11.4 Stale truth

Stale required facts degrade to reconciliation, never confident demotion. Unknown capacity is not unlimited; unknown impact is not harmless; missing deadline is not proof of no deadline.

### 11.5 Authority laundering

No ranking class, model summary, dependency count, production impact, or fairness age may change the canonical authority seat.

### 11.6 LLM gaming / opaque inference

Models may summarize an already-determined frontier for readability, but model output has zero authority over:

- admission;
- authority;
- disposition;
- grouping/suppression;
- ordering/tie-breaking;
- lifecycle;
- dispatch;
- retry/failover;
- merge/release.

The V1 engine is deterministic.

### 11.7 Effect uncertainty

`EFFECT_UNKNOWN` is never a reason to send the same operation elsewhere. EAF must surface reconciliation and preserve one-carrier/no-blind-retry law.

## 12. Wire/product contract direction

The implementation should produce a versioned pure result such as `mastermind.executive_attention_frontier.v1`. Exact schema is an A1 implementation detail, but the following semantics are frozen:

```text
snapshot_identity
source_freshness_summary
raw_demand_count
frontier_count
bundles[]
  bundle_id
  canonical_root_ref
  members[]
  authority_partitions[]
items[]
  demand_id
  responsibility_ref
  disposition
  authority_requirement
  authority_source
  attention_sources[]
  factor_vector
  became_actionable_at|null
  wait_context|null
  downstream_unblocks[]
  active_resource_burn|null
  bundle_id|null
  explanation_reasons[]
  source_receipts[]
  issues[]
fairness_sentinels[]
```

No `priority_score`, `authority_score`, `confidence_score` or mutable rank ledger is required in V1.

## 13. Control Room experience architecture

EAF must make the front page calmer, not denser.

### 13.1 Primary compact composition

A compact Attention Frontier header should answer:

- interrupts now;
- focus now;
- context batches next;
- intentional waits;
- autonomous continuations;
- reconciliation required.

The primary executive surface should show only a small number of actionable cards plus an explicit `show all` forensic route. Raw Steward/Agent OS facts remain accessible.

### 13.2 Card anatomy

Each actionable card should show, in this order:

1. **Decision/action needed** — one sentence.
2. **Authority** — Chairman, Sol, other owner; visually separate from urgency.
3. **Why now** — source-backed time/impact/unblock/burn reason.
4. **Why not later / what can continue** — autonomy and option value.
5. **What it unlocks** — exact dependency members/fan-out.
6. **Evidence state** — current/stale/unknown with source receipt count.
7. **Bundle context** — root + member count if applicable.
8. **Open exact surface / forensic facts** — navigation only through existing Control Room/SurfaceBinding mechanisms.

### 13.3 Intentional waits

Valid waits should look calm and intentional, with review condition/date, not like red overdue backlog. Once due, they re-enter evaluation.

### 13.4 Unknown/reconcile

Unknown/conflicted/effect-uncertain cases must be visually explicit. The interface must never use a polished ranking to hide degraded truth.

### 13.5 Chairman vs Sol views

The Chairman view is not “the highest score.” It is the subset whose **canonical authority requirement is Chairman**, then attention-dispositioned within that partition.

The Sol view is the corresponding CEO/Sol partition. A high-pressure Sol item stays out of Chairman interruption unless a separate accepted authority fact says otherwise.

## 14. Chat-native Meta-CEO / Program CEO consumption

The machine/CEO consumer should receive a compact context block, not a second mutable inbox:

```text
INTERRUPT_NOW: <0..n exact demands>
FOCUS_NOW: <bounded current bundles>
BATCH_NEXT: <context bundles + oldest-ready sentinel>
VALID_WAIT: <count + nearest source-backed review boundary>
AUTONOMOUS_CONTINUE: <count>
RECONCILE_FIRST: <count + critical unknowns>
```

A fresh Sol may query/drill into source receipts before acting. The projection itself grants no authority and does not mark items complete.

## 15. Measurement and promotion gauntlet

A deterministic unit test is not product proof. EAF promotes only through a real multi-program shadow interval.

### 15.1 Shadow-first

Initial implementation is `REPORT_ONLY / SHADOW`:

- no lifecycle mutation;
- no automatic Wake changes;
- no dispatch;
- no Chairman notification side effects;
- no scheduling;
- no Control Room suppression of raw facts.

### 15.2 Required evaluation corpus

Before real-data shadowing, the frozen adversarial corpus must include at least:

1. true immediate Chairman-only decision;
2. more urgent Sol decision that must not escalate to Chairman;
3. twenty symptoms of one canonical root blocker;
4. semantically similar items with no canonical join that must not be bundled;
5. stale/conflicted authority;
6. `EFFECT_UNKNOWN` operation;
7. old but still-valid intentional wait;
8. overdue wait due for review;
9. safe autonomous progress despite executive interest;
10. no-safe-progress high-unblock decision;
11. active resource burn without authority change;
12. missing optional impact evidence that must not demote to harmless;
13. repeated notification refresh that must not reset age;
14. context-adjacent batch versus unrelated batch;
15. new emergency arriving while an old fairness sentinel exists.

Output must be permutation-stable and source-order independent.

### 15.3 Real portfolio proof

Shadow evaluation must compare EAF against actual current portfolio/Chairman/Sol intervention behavior and preserve receipts. Promotion requires evidence for:

- zero missed true `INTERRUPT_NOW` cases in the accepted canary corpus/interval;
- zero priority-driven authority escalations;
- zero invalid suppression from semantic similarity;
- zero valid waits incorrectly turned into urgency;
- all stale/unknown/effect-uncertain critical cases degraded truthfully;
- exact fan-in receipts for every suppressed bundle member;
- oldest-ready fairness visibility for eligible backlog when no emergency prevents service;
- materially fewer top-level executive attention objects than the raw valid-obligation set;
- materially fewer Chairman interruptions for routine Sol work without increased severe-decision latency;
- browser proof at relevant Control Room breakpoints after UI integration;
- a real Chat-native CEO consumer demonstrating compact frontier use without lifecycle mutation.

Do not freeze arbitrary percentage targets before the shadow baseline exists. Record baseline, then set promotion thresholds against observed company demand while preserving the zero-miss/zero-authority-violation invariants above.

## 16. Architecture alternatives rejected

### A. One global weighted score

**Rejected.** It collapses incomparable objectives, hides unknowns, encourages priority gaming, and creates false precision.

### B. Flat `needs_sol` / `needs_chairman` inbox

**Rejected.** It reproduces the human queue at larger scale and fails to preserve waits/autonomy/root-cause fan-in.

### C. New persistent attention queue or database

**Rejected.** Wake, Agent OS and Executive OS already own the relevant durable/runtime truths. A new queue would become a third control plane and create correction/retry ambiguity.

### D. LLM-ranked estate

**Rejected.** Models can explain but may not rank, suppress, group, grant authority or originate lifecycle actions.

### E. Pure deadline scheduler

**Rejected.** Many valid executive decisions have no source-backed deadline; deadlines optimize only one objective and can starve strategically important non-deadline work.

### F. Pure dependency-count ranking

**Rejected.** Descendant count is not critical path and can overvalue large low-consequence subgraphs.

### G. Hard Chairman attention quota

**Rejected.** Emergencies and genuine Chairman-only authority cannot be suppressed to satisfy a quota. The design reduces interruption structurally through admission, delegation, batching and fan-in instead.

## 17. No-rebuild / no-crossing boundaries

The following are frozen:

- no new Job/Attempt/Worker lifecycle;
- no new Executive/Agent/Slack/Workroom truth store;
- no new Wake owner, route ledger, notification scheduler or retry engine;
- no new Capacity/Model Router or provider-account selector;
- no mutable attention inbox/cursor database;
- no priority-to-authority conversion;
- no Chairman default for unknown authority;
- no auto-dispatch from attention state;
- no cross-carrier retry/failover from urgency;
- no semantic/LLM dedup suppression;
- no global scalar priority score in V1;
- no `critical path` claim without real schedule/float data;
- no silent treatment of unknown as zero/healthy/harmless;
- no suppression of raw forensic facts in the first shadow release;
- no implementation fork around OCR-6 PR #228 correctness repair.

## 18. Bounded implementation waves

### F0 — source law and durable program home

This document plus Agent OS workstream/decision/discovery records. `SPEC_ONLY / RECORDS_ONLY`.

### A1 — pure deterministic Attention Frontier engine

**Observable mission:** given a corrected immutable Steward snapshot plus bounded source-attributed Agent OS attention context, return deterministic EAF v1 classes, factor vectors, bundles, source receipts and fairness sentinel with no side effects.

**Gate:** corrected OCR-6 Steward protected base.

Expected implementation home: a bounded Mastermind `control_plane` module and tests; do not add gather/daemon/database behavior.

**Preferred avenue:** `CTO Sol` for the contract-sensitive deterministic engine after this freeze.  
**Why:** reasoning-heavy but bounded single-purpose implementation with adversarial semantics.  
**Why not Fable:** architecture/authority boundaries are now frozen and the implementation can be tested deterministically.

### A1R — independent adversarial semantics review

Review authority separation, stale/unknown handling, bundle suppression, anti-gaming, fairness and permutation stability. Cross-model/provider diversity is preferred when lawful capacity exists. Reviewer receives no merge/release authority.

### A2 — real portfolio shadow adaptor + forensic projection

Consume real existing owners through corrected Steward/current Agent OS reads and expose report-only EAF JSON/CLI/Control Room internal read seam. Prove real source receipts and degraded states. No UI suppression or notification side effects.

### A3 — Control Room Attention Frontier experience

Integrate the compact experience into the existing Control Room compositor. Preserve raw drilldown, valid-wait visualization, authority/urgency separation and responsive browser proof.

**Preferred avenue:** `Terra` once A2 contracts are frozen.  
**Why not Fable:** bounded user-facing implementation over an accepted read contract.

### A4 — Chat-native CEO consumer

Project the same EAF result into the existing Meta-CEO/Program-CEO context/boot/query path without creating session identity, stored inbox state, or new authority.

### A5 — calibration, real multi-program canary, promotion

Run the accepted shadow measurement interval/corpus, compare against actual executive interventions, tune only policy thresholds that the architecture explicitly leaves configurable, and decide whether EAF remains report-only or becomes the default Control Room attention composition.

No automatic Wake/dispatch behavior is implied by A5. Any future proactive delivery change requires a separate explicit architecture/release through existing Wake ownership.

## 19. Completion standard

This program is not complete when a classifier or dashboard exists. It is complete only when:

**Truth** — source-attributed current/correction-safe facts degrade honestly.  
**Intelligence** — demands are admitted, authority-partitioned, bundled, optionality-aware and anti-starvation without an opaque scalar.  
**Product** — Chairman/Sol can use a calm compact Control Room frontier and forensic drilldown.  
**Learning** — a real multi-program interval shows materially lower executive scanning/interruption without missed high-severity decisions or authority leakage.

## 20. Current next action

1. Protect this F0 architecture source law and its Agent OS records.
2. Observe/reconcile OCR-6 PR #228 repair; do not collide with its sole writer.
3. After corrected Steward is protected, commission A1 on the exact frozen contract.
4. Keep implementation report-only until A1R and real portfolio shadow proof.
