# Mastermind Executive Attention Economics — Executive Attention Frontier Architecture

**Date:** 2026-08-30  
**Owner:** Sol, AI CEO / Program CEO  
**Chairman:** Chris  
**Status:** `SPEC_ONLY / SOL-FROZEN-CANDIDATE / UNPROTECTED`  
**Operation key:** `mastermind-executive-attention-economics-20260830-sol-001`  
**Canonical records carrier:** `Mastermind:sol/executive-attention-economics-20260830`  
**Protected procedure/source pin:** `mastermindx-market-intelligence/Mastermind@8f0babf473e6e4e8efce697014bd48c594227d94`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1 compatible  
**Current Macro archaeology pin:** `mastermindx-market-intelligence/macro@ca31568272d06f2472f65946d2435517611f31dc`  
**Organizational parent:** existing `WS:CHAIRMAN-CONTROL-ROOM` / Operating-Surface Convergence  
**Implementation predecessor:** Executive Steward PR #228 remains OPEN / `BUILT_NOT_PROVEN / KNOWN_CORRECTNESS_BLOCKER / PRODUCTION_INERT`; this program does not touch its two owned paths until that carrier is protected and accepted.

This document freezes the candidate architecture for the missing executive-attention allocation layer. It creates no Executive Job, Attempt, Worker, Wake obligation, queue, lifecycle state, RuntimeBinding, provider placement, Slack notification, Linear priority, stored inbox, persistent scheduler, Control Room mutation or authority transition by itself.

---

## 1. Chairman outcome

Mastermind-X has increasingly solved a first-order continuity question:

> **Who owes the next semantic turn?**

At portfolio scale that answer is necessary but insufficient. When dozens or hundreds of valid responsibilities legitimately want Sol or Chairman cognition, a flat `needs_sol`, `needs_ceo`, alert stream or notification list becomes a human queue. The missing capability is to explain:

> **Which obligations deserve scarce executive cognition now, which should be batched, which can continue autonomously, which are legitimate waits, and which require truth repair before anyone decides?**

The required outcome is not “rank everything.” It is to reduce Chairman interruption and Meta-CEO context switching while preserving emergencies, hard windows, starvation protection, exact authority and source truth.

The end state must allow Control Room / Executive Steward to answer, from current canonical company state:

- what should receive Sol cognition now and why;
- what genuinely requires Chairman/admin authority rather than routine Sol judgment;
- what can wait without harm and why that wait is intentional;
- what should continue gathering evidence autonomously instead of consuming executive time;
- what independent obligations can be collapsed into one source-grounded batch or root-cause decision;
- what is urgent enough to preempt the current focus;
- what is stale, conflicting or insufficiently grounded and therefore needs verification rather than prioritization;
- what has waited long enough to create starvation risk;
- what is merely noisy transport/projection activity and should not enter the executive frontier at all.

**Priority and authority remain separate absolutely.** A high-priority item cannot grant execution authority, upgrade Sol work into Chairman-only work, select a provider, mutate lifecycle state, retry an ambiguous operation or elect a runtime target.

---

## 2. Product thesis — an attention frontier, not an inbox

The strongest architecture is **not** a universal Executive Attention Prioritizer score. It is an **Executive Attention Frontier (EAF)**: a source-attributed, read-only decision-support projection over facts already owned by Executive OS, Agent OS, GitHub, RuntimeBinding/Wake, Capacity, Agent Dialogue and the Executive Steward.

The Executive Attention Frontier has five jobs:

1. **Partition** unresolved obligations by lawful cognition owner without changing authority.
2. **Protect** emergency, hard-window and truth-reconciliation cases with deterministic guardrails.
3. **Compress** exact duplicates, shared-root-cause fan-in and related decisions into compact attention packets without hiding affected responsibilities.
4. **Expose a partial order** among genuinely comparable ready-to-decide obligations rather than forcing false precision through an opaque scalar.
5. **Shape the cognition session** so related decisions are handled together and intentional waits/autonomous progress stay quiet.

The product promise is:

> **The Chairman sees exceptions; Sol sees the actionable frontier; the rest of the organization keeps moving.**

This architecture deliberately does not treat all organizational attention as a fixed global token pool. Organizational-attention research emphasizes that individual attention is limited while organizational attention is structurally distributed through roles and communication channels. The system should therefore improve distribution, routing and coherence, not invent one universal company-wide “attention budget.”

---

## 3. Research synthesis and architectural consequences

### 3.1 SRE: page only what requires immediate human action

Google SRE distinguishes pages, tickets and ongoing operational responsibility; paging is intentionally narrow because interruption is costly and low-signal paging creates alert fatigue. Its on-call guidance classifies immediate pages separately from next-business-day and informational work and states that paging alerts should be immediately actionable. Managing Operational Load also uses one primary responder to minimize interruption and bystander effects.

**Consequence for Mastermind:** executive interruption must be a distinct class, not the default representation of “work exists.” One accountable cognition owner receives a true interrupt; lower-urgency work belongs in focus/batch/wait/autonomy views.

Primary references:

- https://sre.google/sre-book/dealing-with-interrupts/
- https://sre.google/workbook/on-call/
- https://sre.google/sre-book/being-on-call/
- https://sre.google/workbook/error-budget-policy/

### 3.2 Alertmanager: group, deduplicate and inhibit symptoms behind causes

Prometheus Alertmanager explicitly groups related alerts, deduplicates them, routes them and supports inhibition where a source alert suppresses dependent symptom notifications. `group_wait` expresses a real tradeoff: a short wait is faster but may miss related/inhibiting alerts; a longer wait improves grouping but can delay a real page.

**Consequence for Mastermind:** exact shared decision/root-cause/dependency relations should create one attention packet with all impacted responsibilities attached. Batching may wait briefly when the current source contract permits it, but true emergency/hard-window cases bypass batching. No fuzzy LLM similarity may inhibit an independent obligation.

Primary references:

- https://prometheus.io/docs/alerting/latest/alertmanager/
- https://prometheus.io/docs/alerting/latest/configuration/

### 3.3 Critical-path reasoning: unblock value is dynamic

NASA defines the critical path as the sequence of dependent tasks determining the longest project duration and notes that it changes as tasks complete or slip.

**Consequence for Mastermind:** dependency-unblock value cannot be a static “number of children” badge. It is recomputed from current exact dependency facts. A small decision that releases a current critical path may outrank a larger-looking project; stale dependency graphs degrade the claim instead of preserving an old rank.

Primary reference:

- https://www.nasa.gov/reference/6-1-technical-planning/

### 3.4 Value of information and real options: waiting can be the correct action

Decision analysis treats information itself as having value under uncertainty. Real-options research shows that when a commitment is irreversible and information is expected to improve, waiting can preserve option value. Recent work also distinguishes irreversible investment from experimentation: uncertainty can rationally delay the former while increasing research/experimentation that resolves uncertainty.

**Consequence for Mastermind:** “blocked” is not synonymous with “escalate.” An item can be `VALID_WAIT` or `CONTINUE_AUTONOMOUSLY` when new evidence is expected to materially improve the decision and delay does not violate a hard window. The system should often spend machine/worker effort to resolve uncertainty before it spends Chairman cognition.

Primary references:

- https://gsbpreserve.stanford.edu/view/34085/the-value-of-information-in-monotone-decision-problems
- https://www.nber.org/papers/w3307
- https://www.nber.org/papers/w11430
- https://www.nber.org/papers/w34838

### 3.5 Interruption science: switching has residual cognitive cost

Sophie Leroy’s attention-residue research describes how unfinished or interrupted prior tasks can retain attention after a switch, leaving fewer cognitive resources for the new task.

**Consequence for Mastermind:** context-switch/preemption cost belongs in session composition and batching. It is **not** allowed to suppress a true emergency. Once the urgent guardrail is satisfied, the system should prefer coherent batches and fewer unnecessary project switches.

Primary reference:

- https://www.uwb.edu/business/faculty/sophie-leroy/attention-residue

### 3.6 Attention-based view of the firm: attention is structurally distributed

Recent attention-based-view research emphasizes limited individual attention, organizational distribution through communication channels, temporal dynamics, coherence and the role of structure in shaping what becomes salient.

**Consequence for Mastermind:** the correct product is a structured attentional control surface over existing organizational owners, not a personal productivity score. The architecture must make high-quality distribution visible: who should attend, through which channel, to what issue, with what evidence and with what consequence if delayed.

Primary references:

- https://journals.sagepub.com/doi/10.1177/14761270231223397
- https://journals.sagepub.com/doi/10.1177/10564926241278520

---

## 4. Current estate and capability ledger

The architecture extends the current estate rather than inventing a parallel owner.

| Capability | Current state at this freeze | Consequence |
|---|---|---|
| Chat-native Meta-CEO / Program CEO hierarchy law | `SPEC_ONLY / PROTECTED` architecture | EAF plugs into the hierarchy; it does not create a new CEO/session tree |
| Organizational continuity / `turn_owner` / parent-continuation attention law | `SPEC_ONLY / PROTECTED` architecture with separately evolving implementation | EAF consumes the existing owner classification; it never replaces it |
| Agent OS durable workstreams/decisions/discoveries/handoffs | `PROVEN_LIVE` as organizational knowledge plane | EAF reads workstream facts such as dependencies, waits, blast radius, `needs_ceo`, `next_action`; it creates no task store |
| Agent OS typed waits | live durable organizational facts | valid waits are preserved; review dates trigger reevaluation only, never execution |
| Executive OS Job/Attempt/Worker/Event lifecycle | existing canonical runtime owner | EAF is read-only and cannot mutate/derive lifecycle state by itself |
| RuntimeBinding / Wake / exact action target | existing separate owners / current implementation program | EAF displays their resolution; it never elects a target |
| Executive Capacity Fabric / Model Router | separate active placement/suitability program | EAF may display capacity wait/burn context but may not place workers or rank providers |
| Chairman Control Room P0A/H0 + X1 | accepted/proven local read-only surface according to Agent OS | eventual EAF presentation belongs here |
| OCR-6 Executive Steward protected read core | `NOT_BUILT` on protected master at this exact pin | protected master has no Steward implementation yet |
| OCR-6 Executive Steward PR #228 | `BUILT_NOT_PROVEN / KNOWN_CORRECTNESS_BLOCKER / PRODUCTION_INERT` | no EAF implementation may edit its two paths or pretend Steward is live |
| MAS-218 zero-Slack Chairman cockpit attention views | `NOT_BUILT / TODO`, explicitly gated on Steward/action projections | eventual UI integration target, not a current implementation surface |
| Workroom Home / Radar attention presentation | `NOT_BUILT`; source law says read-only Steward consumer | never implement a second attention engine in Workrooms |
| Executive Attention Economics / portfolio cognition ruler | `NOT_BUILT` | this is the actual gap addressed here |

### 4.1 Existing inputs that are useful but insufficient

Current Agent OS can already express:

- `needs_ceo` with question/options/recommendation/by-when;
- dependencies and blockers;
- blast radius and ambiguity;
- typed intentional `wait` with condition/review time;
- next action;
- durable decisions/discoveries/handoffs.

Those fields are **inputs**, not a priority mechanism. `needs_ceo: true` means an executive question exists. It does not mean “interrupt Chairman now,” and it is not itself a ranking boost.

### 4.2 Current collision / no-touch boundary

Mastermind PR #228 owns exactly:

- `control_plane/executive_steward.py`
- `tests/test_executive_steward.py`

Its current published head remains `7177e8ef29973ccbf62f0ad77850011ef0c91845`, OPEN/unmerged, with the accepted filter-before-identity-grouping correctness blocker. The retained writer operation is separately owned. **EAE-F0 and every pre-#228 wave are prohibited from modifying either path.**

---

## 5. Canonical ownership freeze

No attention factor may change the owner of its underlying fact.

| Fact | Canonical owner |
|---|---|
| Job / Attempt / Worker / Event lifecycle and admission | Executive OS |
| workstream / wave / decision / discovery / handoff and intentional wait | Agent OS |
| implementation / branch / PR / CI / merge / production proof | GitHub / owning evidence source |
| selected human portfolio projection | Linear |
| dialogue delivery / hot-state carrier evidence | Slack / Agent Relay |
| current exact runtime/session target | RuntimeBinding / accepted current continuity owner |
| wake obligation / targeting / acknowledgement | Wake / current continuity owner |
| worker/provider suitability and capacity | Model Router / Capacity Fabric / source provider owner |
| cross-owner responsibility / blocker / attention composition | OCR-6 Executive Steward |
| Chairman operating projection | Chairman Control Room |
| Project Workroom Home / Radar | presentation consumer only |
| priority/economic recommendation | EAF **derived projection only** |

The EAF therefore owns **no durable truth**. It is a pure/recomputable consumer-compositor within the Steward/Control Room read path.

---

## 6. Architecture alternatives and ruling

### Alternative A — weighted universal priority score

Example shape:

```text
priority = 0.3 * urgency + 0.2 * impact + 0.2 * unblock + ...
```

**Rejected.** It creates false cardinal precision, hides incompatible units, encourages gaming, silently treats unknown as zero, makes weighting authority-like, and can cause a mediocre aggregate score to outrank a hard deadline or emergency. It also gives no principled representation for “these two obligations are incomparable.”

### Alternative B — WSJF / cost-of-delay divided by job size

Useful when value and duration are calibrated and jobs are comparable.

**Rejected as the primary mechanism.** Executive decisions often have poorly estimated cognition time, discontinuous hard windows, non-economic authority gates, option value of waiting and unquantified tail risk. A ratio can be an optional tie-break only where the numerator and denominator are both source-grounded and calibrated.

### Alternative C — earliest-deadline-first

Excellent for deadline-constrained queues under appropriate assumptions.

**Rejected as the whole system.** Many executive obligations have no meaningful deadline; some deadlines are soft; some high-severity incidents preempt regardless; some items should wait for information; and executive cognition is not a homogeneous preemptible CPU workload.

### Alternative D — pure Pareto frontier

Avoids false scalar precision and preserves incomparability.

**Insufficient alone.** A pure frontier can become too wide, does not itself distinguish emergency interruption from ordinary focus, does not protect intentional waits, and does not solve exact batching/root-cause fan-in.

### Chosen architecture — **Guardrails + Dispositions + Exact Fan-In + Partial Order + Session Economics**

The EAF uses a staged deterministic pipeline:

```text
canonical facts
  -> identity + freshness validation
  -> existing authority/turn-owner partition
  -> interrupt / hard-window guardrails
  -> wait / autonomy / information-readiness disposition
  -> exact deduplication + root-cause/dependency fan-in
  -> Pareto frontier among comparable READY obligations
  -> anti-starvation visibility
  -> context-coherent session batching
  -> optional calibrated economic tie-breaks
  -> explanation-first Steward / Control Room projection
```

This produces a compact frontier without claiming that every obligation has one true scalar rank.

---

## 7. The closed attention dispositions

Every unresolved eligible source fact entering EAF must end in exactly one derived disposition. No item disappears merely because it is inconvenient to rank.

```text
PREEMPT_NOW
FOCUS_NEXT
BATCH
CONTINUE_AUTONOMOUSLY
VALID_WAIT
VERIFY_TRUTH
NON_ACTIONABLE
```

These are **presentation/recommendation states only**. They create no lifecycle event, queue position, Job status, Wake, notification, assignment or authority.

### 7.1 `PREEMPT_NOW`

Reserved for a narrow deterministic guardrail where delay before the next normal cognition boundary is expected to cause material harm or lose an irreversible window.

Examples:

- active severe production/user impact requiring the current lawful executive owner;
- an expiring hard legal/credential/market/administrative window with material consequence;
- severe effect-unknown state where current owner reconciliation is needed immediately to prevent unsafe duplicate action;
- an accepted source-law emergency class.

A high self-reported urgency label alone can never produce `PREEMPT_NOW`.

### 7.2 `FOCUS_NEXT`

Ready-to-decide obligations on the current non-dominated executive frontier that should receive cognition at the next focus boundary.

There may be multiple `FOCUS_NEXT` items. The UI may recommend a compact session order, but the architecture does not pretend the set has a universal cardinal ordering.

### 7.3 `BATCH`

Two or more obligations can be decided efficiently together because they share an exact source-grounded relation such as:

- same canonical decision;
- same root blocker;
- same hard dependency;
- same program gate;
- same admin/credential ceremony;
- same current source-reconciliation question.

A batch exposes every member and source reference. It is compression, not suppression.

### 7.4 `CONTINUE_AUTONOMOUSLY`

Executive cognition is not yet the limiting resource and lawful autonomous work can materially improve the eventual decision. Examples include research, proof collection, deterministic reconciliation or bounded implementation already within delegated authority.

This disposition never commissions new work by itself. It only explains that the current executive need is not yet ripe.

### 7.5 `VALID_WAIT`

The source-owned organization is intentionally waiting for evidence, a calendar window or an external dependency; the wait remains fresh and no contradictory emergency/hard-window fact exists.

Passing `review_after` means “reevaluate the wait,” not “execute” or “page Chairman.”

### 7.6 `VERIFY_TRUTH`

A priority decision would be unsafe or misleading because required evidence is stale, missing, conflicting, ambiguous or structurally incomparable in a way that should be repaired first.

`UNKNOWN` is never converted to low urgency, zero impact, infinite capacity or no blocker.

### 7.7 `NON_ACTIONABLE`

The item is resolved, terminal, historical, belongs to a worker/placement owner rather than executive cognition, is superseded, or is merely transport/projection noise with no current executive semantic obligation.

The reason is always visible.

---

## 8. Priority is downstream of authority

### 8.1 Existing `turn_owner` remains controlling

EAF consumes, without redefining, the accepted owner classes such as:

```text
SOL
COO_OR_WORKER
EXECUTIVE_PLACEMENT
ADMIN_OR_CHAIRMAN
NONE_TERMINAL
UNKNOWN
```

A current item enters the **Sol cognition frontier** only when the accepted owner facts say Sol cognition is owed. It enters the **Chairman/Admin frontier** only when existing current law/facts require Chairman/admin authority.

`needs_ceo`, “urgent,” PR priority, number of dependents, value score or model judgment can never turn a routine Sol decision into Chairman-only work.

### 8.2 Chairman-only examples

Legitimate Chairman/Admin cases include current source-law requirements for matters such as:

- a new authority class or strategy choice outside delegated Sol scope;
- irreversible spend or account/admin changes reserved to the human;
- action-time credential confirmation where current law requires a native human boundary;
- irreversible workspace/account merge or externally representative decision;
- another explicitly accepted Chairman gate.

### 8.3 Exact action target remains separate

Even when `turn_owner=SOL`, EAF does not elect which Sol tab/session/account may act. The existing action-authority / RuntimeBinding / continuity owner resolves the exact target. `ATTENTION_OWNER_CONFLICT` or unknown target produces fail-closed `VERIFY_TRUTH`/attention-health output rather than “pick another healthy Sol.”

---

## 9. Candidate semantics and source contract

### 9.1 Reuse Steward identity

EAF must not mint a second durable attention identity. Once the Executive Steward contract is protected, EAF reuses its accepted responsibility/attention identity and source references. If the protected Steward schema differs from current open-PR vocabulary, the protected schema wins.

The EAF may derive ephemeral group identifiers for one response/render, but these identifiers own no history or lifecycle.

### 9.2 Required candidate fields

Conceptual candidate projection:

```text
responsibility_ref
attention_ref / accepted Steward identity when available
canonical_obligation_refs[]
turn_owner
resolved_action_target_ref | null | unknown
current_next_action
source_refs[]
source_freshness[]
source_conflicts[]
intentional_wait | null
deadline_or_window | null
production_or_user_impact | null
reversibility_blast_radius | null
dependency_unblock | null
active_resource_burn | null
effect_uncertainty | null
autonomous_progress | null
information_readiness
age_basis | null
disposition
reason_codes[]
why_now
why_not_wait
why_not_chairman
why_not_interrupt
```

Values remain typed/nullable. Missing observation is `unknown`, never a default healthy/zero value.

### 9.3 Freshness is source-specific

There is no single global “15 minutes = fresh” constant for all facts. Each source class uses its accepted freshness law/budget. A GitHub merge fact, current provider quota, Slack dialogue edge and Agent OS strategic decision have different volatility.

EAF preserves both:

```text
observed_at
source_effective_at / accepted source timestamp
```

where available. Copying old facts into a new wrapper never refreshes them.

---

## 10. Deterministic attention factors

The following factors are explanatory dimensions, not additive points.

### 10.1 Authority requirement

A partition/gate, **not a priority factor**.

### 10.2 Deadline and window decay

Represent separately:

```text
NO_WINDOW
SOFT_WINDOW
HARD_WINDOW
WINDOW_EXPIRED
UNKNOWN
```

with exact timestamps and source refs when available. The consequence of missing the window matters more than proximity alone.

### 10.3 User / production impact

Use only current source-owned impact evidence. Active customer/production harm is qualitatively different from a strategic opportunity.

### 10.4 Blast radius and reversibility

Conceptual bands:

```text
REVERSIBLE
COSTLY_TO_REVERSE
IRREVERSIBLE
UNKNOWN
```

High irreversibility does not automatically mean “do now”; under uncertainty it may increase option value of waiting. Combined with a hard window it can increase urgency.

### 10.5 Downstream unblock and critical path

Count only exact hard dependencies. Prefer current critical-path membership or equivalent dependency impact over raw child count. Cycles, missing parents or stale dependency state degrade the claim.

### 10.6 Active resource burn

Examples: blocked paid capacity, reserved privileged host, live production degradation, workers burning scarce context with no progress.

Resource burn is bounded/banded and source-grounded. Spawning more workers or watchers cannot manufacture executive priority.

### 10.7 Effect uncertainty

`EFFECT_UNKNOWN` is not a score. It invokes current reconciliation law. When effect uncertainty blocks safe continuation, EAF highlights the reconciliation obligation to the already-authoritative owner.

### 10.8 Decision/evidence readiness

```text
READY
NEEDS_FACT
NEEDS_EXPERIMENT
SOURCE_CONFLICT
UNKNOWN
```

An urgent but ungrounded item can still be urgent **to verify**, not urgent to make the substantive decision.

### 10.9 Autonomous progress

```text
CAN_PROGRESS_WITHOUT_EXEC
EXEC_COGNITION_IS_BOTTLENECK
EXTERNAL_WAIT
UNKNOWN
```

When useful autonomous work can continue, executive attention is usually deferred unless a hard window or severe impact overrides.

### 10.10 Option value / value of information

This factor asks whether waiting or experimentation is expected to improve the decision enough to justify delay.

Initially this is a source-attributed qualitative explanation, not an LLM-generated dollar value. A future calibrated statistical model may estimate EVPI/EVSI-like quantities, but such estimates remain advisory until prospective validation proves they improve decisions.

### 10.11 Age / starvation

Age is calculated only from a canonical timestamp that actually represents the current unresolved obligation. Git commit recency, newest Slack message or file modification time must not masquerade as obligation age.

When age cannot be established, output `STARVATION_AGE_UNKNOWN` rather than zero.

### 10.12 Switching / preemption cost

Switch cost shapes **session ordering and batching after semantic urgency is determined**. It never prevents a true `PREEMPT_NOW`.

---

## 11. Hard guardrail law

The pipeline evaluates guardrails before ordinary comparative reasoning.

### 11.1 Emergency / immediate-harm guard

A candidate may become `PREEMPT_NOW` only when all are true:

1. an accepted source establishes a current material harm/hard-window class;
2. the current semantic action is immediately actionable by the already-resolved authority owner;
3. required evidence is fresh enough for that claim, or the immediate action is itself typed reconciliation/verification;
4. no existing terminal/superseding/effect-unknown rule forbids the proposed action.

No quota can suppress a valid emergency.

### 11.2 Hard-window guard

For ready items sharing comparable consequence class, hard-window proximity can create a lexicographic ordering analogous to deadline scheduling. This rule is local; it does not turn all executive work into EDF.

### 11.3 Truth guard

Missing, stale, conflicting or ambiguous required source truth yields `VERIFY_TRUTH` when proceeding would rely on an invented default.

### 11.4 Authority guard

A candidate cannot move to another executive frontier because of urgency. If the source says worker/placement owns the next turn, it remains outside executive cognition unless a distinct independently valid executive obligation exists.

---

## 12. Exact fan-in, deduplication and inhibition

### 12.1 Exact grouping only

Allowed grouping relations must come from canonical identity/graph facts, for example:

- same `decision_ref`;
- same exact root blocker;
- same dependency gate;
- same operation family where accepted source law defines one shared ruling;
- same native admin ceremony;
- same current proof failure/root cause.

### 12.2 Root-cause inhibition

If one source-grounded root cause explains several dependent symptoms, EAF may make the root decision the parent attention packet and list symptoms as impacted members.

The member obligations remain visible. “Inhibited” means **do not interrupt separately**, not “pretend resolved.”

### 12.3 No semantic similarity suppression

LLMs may suggest potential affinity for analyst review, but model similarity cannot:

- hide a candidate;
- merge identities;
- change authority;
- suppress a notification;
- create a root cause;
- claim duplicate work.

### 12.4 Batch window

A future existing-cadence Meta-CEO/Control Room consumer may choose a small presentation delay to improve grouping for non-emergencies, analogous to alert grouping. EAF itself creates no timer/daemon/scheduler. `PREEMPT_NOW` bypasses batching.

---

## 13. Partial-order frontier

After guardrails, wait/autonomy disposition and exact grouping, READY executive obligations are compared on a small set of source-grounded dimensions.

### 13.1 Dominance rule

Candidate A may dominate B only when:

- both have the same lawful cognition owner class;
- both are READY enough to compare;
- all required dimensions being used are known and comparable;
- A is no worse than B on every selected delay-harm dimension; and
- A is strictly stronger on at least one dimension.

Otherwise they remain incomparable and may both appear on the frontier.

### 13.2 Recommended first-wave dimensions

Use a deliberately small set:

1. severity / material harm if delayed;
2. hard-window decay;
3. current dependency/critical-path unblock;
4. active resource burn/waste;
5. starvation age where canonical.

Reversibility, information value and autonomy are principally used to decide READY vs WAIT/AUTONOMY/VERIFY rather than to inflate the dominance vector.

### 13.3 No hidden tie-break

If two candidates remain incomparable, EAF says so. The UI may then recommend a context-coherent session order, but must not display that order as an objective total priority ranking.

---

## 14. Economic tie-breaks — optional and calibrated only

The system may eventually compute an **attention-value rate** for comparable candidates:

```text
expected material delay loss avoided
------------------------------------
expected executive cognition minutes
```

but only when both quantities have a source-backed calibrated estimate and an uncertainty interval.

Rules:

- unknown numerator or denominator => no ratio;
- no LLM-made dollars/minutes as authoritative input;
- no ratio can cross an authority boundary;
- no ratio can demote a `PREEMPT_NOW` guardrail;
- no ratio can turn a valid wait into a decision unless the wait law is independently satisfied;
- all estimates show confidence and calibration cohort.

Until prospective evidence exists, EAF uses qualitative economics and partial order rather than fake precision.

---

## 15. Anti-starvation and fairness

The system must not solve overload by permanently hiding hard-to-compare work.

### 15.1 Complete-partition invariant

Every current candidate must reconcile into one visible disposition or one explicit exclusion reason. Counts reconcile back to the input responsibility/attention set.

### 15.2 Aging without a new queue

EAF does not store a “times deferred” counter. It derives age only from accepted current obligation timestamps and/or existing owner review dates.

A sufficiently old READY obligation gains a `STARVATION_RISK` reason and remains visible on a dedicated aging edge even when it is not otherwise non-dominated. The threshold is versioned policy, not a hidden model weight.

### 15.3 Review-date protection

An intentional wait with a passed `review_after` re-enters assessment. It does not become an automatic interrupt. The reviewer may renew the wait only with fresh reason/evidence according to the owning source’s law.

### 15.4 Emergencies remain unquotaed

There is no daily Chairman interruption quota that can hide emergencies. The objective is to make Chairman interruption rare by classifying and batching correctly, not by dropping messages after N alerts.

---

## 16. Anti-gaming law

The following manipulations must fail:

- adding `urgent` prose does not create severity;
- adding `needs_ceo` does not create Chairman authority;
- creating more workers does not amplify resource-burn weight without real source evidence;
- creating more child workstreams does not multiply unblock value unless exact hard dependencies exist;
- repeated Slack messages do not create additional attention demand;
- a high Linear priority does not outrank canonical source truth;
- stale quota/impact evidence does not become fresh because another surface repeated it;
- title similarity cannot create batches;
- old Git commits cannot manufacture obligation age;
- an LLM cannot promote its own recommendation to an emergency;
- a project cannot evade a valid wait by emitting another notification;
- a high priority cannot authorize merge, retry, credential use, provider selection or RuntimeBinding transfer.

The architecture should include hostile fixtures for each case before production promotion.

---

## 17. Deterministic versus statistical/model-generated behavior

### Deterministic / contract-owned

- source identity joins;
- source freshness classification under accepted owner rules;
- `turn_owner` / current authority partition;
- terminal/superseded/effect-unknown handling;
- typed wait handling;
- exact dependency/root-cause grouping when relations exist;
- guardrail predicates;
- Pareto dominance over typed known dimensions;
- complete-partition reconciliation;
- reason-code generation;
- stable source citations.

### Statistical / model-assisted, advisory only

- summarizing `why now` into concise natural language;
- suggesting possible but unconfirmed cross-project affinity;
- estimating value-of-information or cognition duration after calibration exists;
- identifying candidate root-cause hypotheses for a human/owner to verify;
- predicting likely context-switch cost or meeting duration.

Model output may not change authority, suppress an item, create an exact relation, trigger a page, mutate lifecycle or originate a trade/portfolio action.

---

## 18. Proposed read contract

The eventual pure projection may use a schema conceptually equivalent to:

```text
mastermind.executive_attention_frontier.v1
```

The exact machine schema is frozen only after #228’s protected Steward contract is known.

Conceptual response:

```json
{
  "schema": "mastermind.executive_attention_frontier.v1",
  "observed_at": "...",
  "scope": "company|program|responsibility",
  "source_health": {
    "status": "FRESH|DEGRADED|UNKNOWN",
    "reasons": []
  },
  "preempt_now": [],
  "sol_frontier": [],
  "chairman_frontier": [],
  "batches": [],
  "continue_autonomously": [],
  "valid_waits": [],
  "verify_truth": [],
  "non_actionable": [],
  "reconciliation": {
    "input_count": 0,
    "output_member_count": 0,
    "unaccounted_refs": []
  }
}
```

A group/card contains exact source references, authority owner, reason codes and all member responsibilities. No scalar `priority_score` is required or preferred.

---

## 19. Explanation contract

Every surfaced executive candidate must answer these questions without requiring a second archaeology pass:

```text
WHY NOW?
WHAT HAPPENS IF WE WAIT?
WHY IS THIS SOL OR CHAIRMAN WORK?
CAN THE ORGANIZATION KEEP MOVING WITHOUT THIS DECISION?
WHAT NEW INFORMATION WOULD CHANGE THE DECISION?
WHAT IS BATCHED OR INHIBITED BEHIND THIS ITEM?
HOW FRESH ARE THE FACTS?
WHAT IS THE EXACT NEXT LAWFUL ACTION?
WHAT SOURCE PROVES EACH CLAIM?
```

For a Chairman card, add:

```text
WHY CAN SOL NOT DECIDE THIS UNDER EXISTING AUTHORITY?
```

If that question cannot be answered from current law/source facts, the item stays out of the Chairman frontier.

---

## 20. Control Room experience architecture

EAF becomes a read-only layer inside the existing Chairman Control Room / Steward experience after its prerequisites are protected.

### 20.1 Top-level composition

A premium dense view should present, in order:

1. **PREEMPT NOW** — only if non-empty; immediate harm/window and exact owner.
2. **SOL FOCUS** — current non-dominated Sol cognition frontier, grouped by coherent session.
3. **CHAIRMAN DECISIONS** — only genuine Chairman/admin boundaries; batched by ceremony/decision context.
4. **BATCH / DIGEST** — decisions that are real but need not interrupt.
5. **KEEP MOVING** — autonomous progress with current next action.
6. **VALID WAITS** — intentional waits with condition and next review boundary.
7. **VERIFY TRUTH** — stale/conflicted/unknown source conditions preventing safe allocation.
8. **AGING / STARVATION RISK** — unresolved ready work that has remained deferred long enough to warrant explicit review.

The default viewport is compact; all suppressed/related members remain inspectable.

### 20.2 Card anatomy

Each card should show:

- responsibility / program identity;
- current semantic obligation;
- `turn_owner` and exact action target when resolved;
- disposition and reason codes;
- deadline/window and consequence;
- production/user impact;
- dependencies unblocked / critical-path evidence;
- active burn if material;
- autonomy / wait / information-readiness status;
- age/starvation basis;
- `why now` and `why not wait`;
- exact next lawful action;
- source freshness and citations.

### 20.3 What the UI must not show as authority

Do not present:

- a giant ranked `1..N` inbox;
- a magical `98/100 priority` badge;
- “Chairman” merely because `needs_ceo=true`;
- provider/account as owner;
- Slack activity as execution;
- Linear priority/status as canonical completion;
- a Resume/Open button before exact action target is resolved;
- a batch that hides its member responsibilities.

---

## 21. Failure and degraded states

### 21.1 Required source unavailable

Return the affected factor as unknown and move unsafe comparisons to `VERIFY_TRUTH`. Do not copy stale values into a fresh wrapper.

### 21.2 Conflicting authority / action target

Expose `ATTENTION_OWNER_CONFLICT` / current accepted typed conflict and fail closed. Priority never chooses the winner.

### 21.3 Dependency graph cycle or unresolved parent

Mark dependency-unblock/critical-path factor unknown or invalid. Do not award unblock value from a broken graph.

### 21.4 Root-cause grouping uncertain

Keep items independent. Advisory model similarity may be displayed as a hypothesis only.

### 21.5 Intentional wait conflicts with emergency evidence

The contradiction is surfaced explicitly and reevaluated under source precedence/freshness. The wait is not blindly trusted and the emergency is not blindly trusted; canonical owner/freshness decides.

### 21.6 Frontier too wide

Do not invent a scalar. Prefer exact grouping, program-scoped session composition and explicit incomparability. Surface the width as an overload signal requiring architecture/organizational intervention.

### 21.7 No actionable executive work

Show an explicit healthy empty state such as “No executive cognition currently required” while continuing to expose valid waits/autonomous progress summaries. Never manufacture work to fill the dashboard.

---

## 22. Real-estate reference compositions

These are architecture canaries, not claims that implementation is live.

### 22.1 Executive Steward #228 correctness repair

Current facts:

- one exact existing Steward PR/branch;
- known correctness blocker;
- sole retained repair writer exists;
- Control Room attention UI depends on Steward release;
- this is a Sol/program-owner implementation review/repair obligation, not Chairman authority.

Expected EAF behavior after sources are supported:

```text
turn_owner: SOL
chairman_frontier: NO
possible disposition: FOCUS_NEXT or CONTINUE_AUTONOMOUSLY depending current worker state
reason: blocks Steward -> Control Room attention read path
no duplicate writer / no branch retry
```

### 22.2 Chairman Control Room P0B credential ceremony

Current Agent OS source law requires action-time native credential confirmation before a bounded disposable canary.

Expected behavior:

```text
turn_owner: ADMIN_OR_CHAIRMAN for the exact human confirmation only
chairman_frontier: YES
PREEMPT_NOW: only if a real hard window/material harm exists; otherwise batch/digest
Sol remains owner of the surrounding review/orchestration
```

### 22.3 Waiting-capacity implementation wave

If an operation is lawfully `WAITING_CAPACITY / needs_placement` and no separate executive decision is owed:

```text
turn_owner: EXECUTIVE_PLACEMENT
executive frontier: NON_ACTIONABLE
```

Scarcity of a worker is not automatically a Chairman interrupt.

### 22.4 Intentional natural-evidence wait

A fresh Agent OS wait for natural evidence with a future review boundary and no contradictory hard window:

```text
VALID_WAIT
no page
review when condition/review boundary becomes due
```

### 22.5 Newly merged records-only architecture

A new protected source-law/spec merge that creates no live runtime capability should not surface merely because it is recent or high-profile. Attention requires a current semantic obligation, not commit recency.

---

## 23. Value model

### 23.1 Chairman value

- fewer interrupts;
- fewer false “needs Chris” escalations;
- high-severity exceptions remain impossible to hide behind batching/quota;
- decisions arrive with source-grounded options, consequence and why Sol cannot decide;
- related admin/strategy decisions are grouped into coherent ceremonies.

### 23.2 Sol / Program CEO value

- no estate-wide scan to discover the next focus;
- dynamic critical-path and dependency visibility;
- less attention residue through context-coherent session batches;
- stale/unknown truth is separated from actual decision work;
- autonomous research/implementation keeps moving until cognition is genuinely the bottleneck.

### 23.3 Machine/organizational value

- deterministic attention semantics over existing owners;
- less notification fan-out and duplicate recovery work;
- bounded, source-attributed context packets for Meta-CEO and Program CEOs;
- a clear line between execution scheduling and cognition allocation.

### 23.4 Research / investment-system value

This layer does **not** gain signal/trading authority. Its value to research is operational: scarce CEO cognition can be directed toward the highest-leverage research, evidence and system decisions while routine pipelines continue. Any Prophet/trading/portfolio authority remains governed by its existing promotion law.

### 23.5 Learning/data moat

The defensible learning asset is a rights-safe history of **attention recommendations and observed outcomes** tied to real operational evidence: what was surfaced, what was batched, what waited, what became urgent, what decision unblocked work and whether an interruption was avoidable.

This history must use existing accepted analytics/instrumentation/evidence homes; EAF may not create a private lifecycle or queue database to collect it.

---

## 24. Measurement and promotion gauntlet

EAF must prove it reduces cognitive load without hiding important work.

### 24.1 Core metrics

- Chairman interrupts per real operating interval;
- avoidable Chairman interruption rate;
- missed high-severity / hard-window decisions (**target: zero** during promotion canaries);
- time-to-cognition for `PREEMPT_NOW` and hard-window classes;
- false positive / false negative attention classification;
- batch compression ratio: member obligations / delivered attention packets;
- percentage of work correctly left `CONTINUE_AUTONOMOUSLY`;
- valid-wait false-wake rate;
- `VERIFY_TRUTH` incidence and repair latency;
- starvation-risk count and maximum attributable unresolved age;
- context switches per executive focus interval;
- dependency-unblock latency;
- proportion of Chairman items with explicit “why Sol cannot decide” source proof.

### 24.2 Shadow mode first

The first real portfolio proof is read-only shadow mode:

- no notifications;
- no Wake;
- no lifecycle mutation;
- no placement;
- no merge/retry;
- no automatic suppression outside the EAF display;
- compare EAF output with actual Sol/Chairman decisions and severe outcomes.

### 24.3 Promotion criteria

No Chairman-interruption behavior is armed until a frozen representative corpus plus live shadow interval demonstrates:

- zero missed accepted emergency/hard-window cases;
- no authority promotions;
- no stale/unknown defaulting;
- exact batch-member reconciliation;
- anti-gaming fixtures pass;
- starvation cases remain visible;
- source citations are complete;
- shadow recommendations materially reduce redundant/avoidable executive touches relative to flat `needs_*` scanning.

The exact quantitative thresholds are established from the calibration corpus; they are not invented in this architecture document.

---

## 25. Architecture freeze / no-rebuild boundaries

The following are frozen unless new evidence falsifies them:

1. **No new lifecycle, queue, inbox, scheduler or attention database.**
2. **EAF is a derived Steward/Control Room projection.**
3. **Priority never changes authority.**
4. **Exact `turn_owner` / RuntimeBinding / Wake owners remain external and controlling.**
5. **Capacity and Model Router remain separate from cognition priority.**
6. **Agent OS waits remain intentional organizational facts; EAF cannot execute them.**
7. **Workroom Home/Radar is a consumer, not the attention engine.**
8. **No universal opaque scalar is the primary prioritization mechanism.**
9. **Emergency/hard-window guardrails precede comparative ranking.**
10. **Unknown/stale/conflicting evidence degrades truthfully rather than becoming zero.**
11. **Exact grouping may compress notifications but never erase member obligations.**
12. **Model judgment is advisory and cannot suppress, authorize or create exact joins.**
13. **No Chairman hard quota may suppress a true emergency.**
14. **#228’s Steward paths remain exclusively owned by its current carrier until protected and accepted.**
15. **A program is not complete until real multi-program Control Room/Steward shadow and production proof demonstrate lower interruption without missed severe decisions.**

---

## 26. Bounded implementation sequence

No coding wave starts merely because this candidate spec exists.

### EAE-F0 — records architecture and organizational ruling

Mission: protect this architecture, research basis, owner boundaries, capability ledger and implementation DAG as records only.

Proof: current-source review, path-only diff, hosted repository checks, exact-head Sol review, expected-head merge.

Stop: source law protected; no runtime capability claimed.

### EAE-R0 — frozen representative portfolio corpus

Mission: build a read-only fixture/corpus from source-attributed real estate examples spanning emergency, hard window, Chairman-only, Sol-only, placement wait, worker turn, intentional wait, stale source, effect unknown, dependency fan-in, root-cause grouping, starvation and normal autonomous progress.

Non-goal: no production EAF endpoint/UI.

Stop: the corpus is reviewable, privacy/rights-safe and captures expected dispositions with source explanations.

### EAE-P0 — pure reference evaluator

Mission: implement a deterministic pure evaluator over frozen typed inputs **outside #228’s owned paths**.

Must prove RED-first hostile tests for authority separation, unknown handling, grouping, dominance, valid waits, starvation visibility and anti-gaming.

Stop: evaluator passes fixtures but remains disconnected from Steward/Control Room.

### EAE-I1 — Steward composition integration

Dependency: #228 protected and accepted; no current Steward writer collision.

Mission: consume the final protected Steward responsibility/attention contract and produce EAF without a new store or owner.

Stop: exact current-source read integration returns source-attributed frontier; no UI/notification.

### EAE-U1 — Control Room experience

Mission: integrate compact frontier views into the existing Control Room, including all failure states and responsive browser proof.

Stop: real-data Chairman/Sol views are usable; no notification/interruption behavior yet.

### EAE-S1 — live shadow canary

Mission: run EAF read-only against a real multi-program interval, compare to actual decisions and collect evaluation metrics through accepted instrumentation/evidence homes.

Stop: calibration report with false positives/negatives, missed severe cases, batch compression, wait correctness, starvation and interruption delta.

### EAE-L1 — Sol frontier promotion

Mission: make the accepted frontier a normal Meta-CEO/Program CEO read input. It may guide Sol focus but still cannot mutate execution or authority.

Stop: Sol operates a real portfolio interval from the frontier without estate scanning and without missed material work.

### EAE-C1 — Chairman exception routing

Dependency: accepted shadow gauntlet and separate release decision.

Mission: route only proven Chairman/Admin `PREEMPT_NOW` exceptions immediately; batch ordinary Chairman decisions into the normal Control Room/Meta-CEO review path using existing transport/wake infrastructure.

Stop: materially fewer Chairman interruptions with zero missed accepted high-severity/hard-window cases over the canary interval.

### EAE-Z1 — end-to-end acceptance / durable closeout

Mission: prove the full 10/10 outcome across real responsibilities and update durable Agent OS/Control Room/Linear projection as appropriate.

Stop: source truth, intelligence, product and learning criteria all pass; no parallel attention owner exists; exact next operating action is recoverable cold.

---

## 27. Worker-routing law for later waves

This program remains Sol-Pro strategy-owned. After architecture protection, bounded implementation/review work may be delegated under current Skillpack routing law.

Routing defaults:

- pure deterministic evaluator / fixtures: Terra or Codex-class concrete builder if current routing/availability permits;
- UX implementation: appropriate bounded front-end/operator route;
- independent adversarial architecture/calibration review: Opus/Grok-grade independent reviewer is sufficient unless ambiguity grows materially;
- Fable is reserved for a justified principal-level cross-repository challenge, not routine implementation.

Every later commission must include the exact mission, source precedence, current carrier state, scope/non-goals, data/null/time/correction semantics, deterministic/model boundary, failure states, acceptance proof, stop condition and continuation handoff.

---

## 28. Acceptance falsifiers

The architecture is rejected or returned to Sol if any implementation:

- persists its own attention queue/inbox/history as a second truth plane;
- uses a weighted scalar as unreviewable authority;
- pages Chairman because `needs_ceo=true` without proving Chairman-only authority;
- interprets unknown/stale facts as zero/no-risk;
- suppresses a true emergency because a batch/quota is full;
- lets high priority select a provider/runtime or create a Wake;
- treats Slack/Linear recency as execution truth;
- hides a candidate because an LLM says it is “similar” to another;
- counts soft prose links as hard dependencies;
- loses valid intentional waits;
- permanently hides old unresolved work;
- edits #228 while its current exclusive repair carrier is unresolved;
- proves only unit ranking rather than the real Control Room/Steward user journey;
- lowers Chairman interruption by simply not surfacing decisions that should have been seen.

---

## 29. 10/10 completion law

The program is complete only when all four layers are proven together:

### Truth

Fresh, exact, source-attributed, correction-safe responsibility/attention facts; unknown and conflicts remain explicit.

### Intelligence

Guardrails, readiness/wait logic, dependency economics, exact fan-in, partial-order frontier, batching, starvation protection and explanations reliably identify where cognition adds value.

### Product

Meta-CEO/Program CEOs operate from a compact frontier; Chairman receives genuine exceptions and coherent decision batches through the existing Control Room/Steward experience.

### Learning

Real operating telemetry/evidence shows fewer Chairman interruptions and fewer unnecessary executive context switches **without missed severe decisions, hidden stalled work or authority drift**.

A scoring function, schema, merged evaluator or dashboard alone is not completion.
