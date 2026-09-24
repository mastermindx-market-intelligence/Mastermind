# Mastermind Executive Attention Economics — F0G Consolidated V1 Contract

**Operation:** `mastermind-executive-attention-economics-20260830-sol-001`  
**Program CEO:** Sol  
**Cognition route:** `CHAT_PRO_DEFAULT`  
**Status:** `CONTROLLING_ARCHITECTURE_CONTRACT / SPEC_ONLY / RECORDS_ONLY`  
**Current protected Mastermind reconciled during freeze:** `28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Skillpack:** `mastermind.sol_skillpack.v1` / `1.0.1` / bootstrap `1`  
**Historical design packet:** F0 + F0A + F0B + F0C + F0D + F0E + F0F  

This document is the **single controlling V1 implementation contract** for Executive Attention Frontier (EAF). The earlier F0–F0F records preserve research, rejected alternatives, adversarial findings and architecture history. Where older wording conflicts with this consolidated contract, **F0G controls**.

It creates no live runtime capability by itself.

---

## 1. Outcome

Mastermind already has owners for work identity, runtime lifecycle, attention obligations, exact session/turn identity, worker placement and operating-surface composition. Portfolio scale creates a separate problem:

> Among all **valid** demands for scarce Chairman/Sol cognition, which must interrupt now, which should be the next focus, which can be decided in a related batch, which can continue autonomously, and which are intentional waits — while preserving exact authority, source freshness, correction history, fairness and emergencies?

The target is not a better inbox. It is a **source-attributed cognition-allocation frontier** that materially lowers Chairman interruption and Meta-CEO scanning without turning priority into authority or hiding unserviceable emergencies.

### 10/10 end-state

Given a point-in-time company snapshot, Chairman/Sol can see a compact but complete attention frontier that:

- separates **who may decide** from **how urgently cognition matters**;
- preserves all independent emergencies;
- exposes urgent-but-blocked action paths instead of hiding them;
- collapses exact duplicate/root-cause symptoms without semantic suppression;
- preserves useful waiting and safe autonomous progress;
- prevents ordinary starvation;
- remains honest when evidence is stale, incomplete or conflicting;
- can explain every visible item and every omitted item from exact receipts;
- reduces executive scanning/interruption in a prospective real multi-program interval with no accepted severe-decision misses or authority leakage.

---

## 2. Canonical owner map — EAF extends; it does not absorb

| Concern | Existing canonical owner | EAF law |
|---|---|---|
| Job/Attempt/Worker/Event lifecycle, admission, leases/fences, effects | Executive OS | Read only. Never mutate/retry/fail over from attention pressure. |
| Durable responsibilities, decisions, discoveries, handoffs, dependencies, typed waits, `needs_ceo` | Agent OS | Read explicit structured facts. Never become another org state store. |
| Attention obligation identity/delivery/source | Executive Inbox / Wake | Primary demand source. Never become Wake owner or notification scheduler. |
| Semantic turn ownership | continuity / accepted turn-owner projection | Read. Current turn can exclude executive interruption despite durable accountable owner. |
| Exact Sol action-authoritative runtime | `control_plane/sol_action_target.py` + its existing SessionTarget/RuntimeBinding owners when live evidence is available | Consume exact target resolution. Never transfer/promote targets. |
| Runtime/session identity | RuntimeBinding / SessionTarget owners | Read only. No session registry or inferred alias. |
| Provider/model/account eligibility and placement | Model Router + Capacity / placement owners | Read availability/burn context only. Never place workers. |
| Federated normalized executive read | corrected Executive Steward / OCR-6 | Primary read seam after protection. Never fork around its integrity gate. |
| Chairman operating composition | Control Room | EAF consumer. No second Control Room truth store. |
| Chat-native CEO cognition | Meta-CEO / Program-CEO accepted context path | EAF consumer. No stored chat inbox. |
| Implementation/evidence | GitHub | Canonical implementation/proof. |
| Selected portfolio tracking | Linear | Projection only. |
| Transport/hot state | Slack / Agent Relay | Transport only. |
| Workroom composition | Project Workroom Projector | Parallel consumer; no EAF ownership. |

### Protected action-target development observed during freeze

Protected Mastermind `28d365c...` introduced `mastermind.sol_action_target.v1`, a storeless Stage-A exact Sol target resolver. It requires exact root Job identity and current RuntimeBinding evidence, fails closed on missing/conflicting evidence, never promotes a sister Sol, and owns no target transfer. The protected commit itself states the capability is still `BUILT_NOT_PROVEN / PRODUCTION_INERT`; Stage-B transfer/enforcement remains separately gated.

EAF consumes that owner **only when the relevant source path is actually available for the episode**. Code existence is not live target evidence.

---

## 3. V1 information model — four orthogonal concepts

A valid attention demand is never represented by one magic priority/status field.

### 3.1 Authority requirement

`authority_requirement` answers **which authority class owns the decision/action**.

Conceptual mappings, using accepted source vocabulary wherever possible:

- `CHAIRMAN`
- `SOL`
- `COO_OR_WORKER`
- `EXECUTIVE_PLACEMENT`
- `ADMIN_OR_EXTERNAL`
- `NONE`
- `UNKNOWN`

Rules:

1. Authority is resolved before attention ordering.
2. Priority, economic consequence, age, impact, fan-out, congestion and model output never change authority.
3. `needs_ceo` means CEO consideration; it does not mean Chairman.
4. Unknown/conflicted authority never defaults upward.
5. A current accountable workstream owner is not automatically the current turn owner or exact action target.

### 3.2 Attention class

`attention_class` answers **when scarce cognition matters**, independently of whether action is currently serviceable.

Closed V1 classes:

- `INTERRUPT_NOW`
- `FOCUS_NOW`
- `BATCH_NEXT`
- `AUTONOMOUS_CONTINUE`
- `VALID_WAIT`
- `NON_ACTIONABLE`

Definitions:

**`INTERRUPT_NOW`** — source-backed active harm, imminent irreversible loss, or decision/response window means waiting until the next ordinary focus boundary is unsafe. Rare. No quota/top-N may hide an independent interrupt.

**`FOCUS_NOW`** — should be the next safe executive focus after the current atomic action because delay, no-safe-progress, exact dependency unblock, active burn or a near decision window makes ordinary batching unsafe, but hard preemption is not justified.

**`BATCH_NEXT`** — executive cognition is valid and needed, but safely decidable in the next related context batch.

**`AUTONOMOUS_CONTINUE`** — current worker/placement/autonomous path can make safe useful progress without executive cognition now. Remains observable but should not interrupt.

**`VALID_WAIT`** — explicit accepted wait/evidence/calendar/external condition says waiting is intentional and the review boundary has not arrived. Age does not convert it into false urgency.

**`NON_ACTIONABLE`** — terminal, informational, superseded, or otherwise correctly outside current cognition allocation.

### 3.3 Serviceability

`serviceability` answers **whether the required action/cognition path is safe and usable now**.

Normalized states:

- `READY`
- `BLOCKED`
- `UNKNOWN`
- `NOT_APPLICABLE`

Typed `serviceability_reasons[]` preserve source-specific causes such as:

- authority/identity conflict;
- stale or unknown load-bearing source;
- exact Sol target unavailable/conflicting/unknown;
- `EFFECT_UNKNOWN`;
- other accepted source-owner blockers.

A demand may be `INTERRUPT_NOW + BLOCKED`. This is first-class. Blocked never means unimportant; urgent never means permission.

### 3.4 Projection relation

Compaction/service representation is separate from both urgency and serviceability.

Examples:

- `ROOT_VISIBLE`
- `COVERED_BY_BUNDLE -> bundle_id`
- `DOMINATED_BY -> demand_id`
- `DEFERRED_EQUIVALENT_CONTEXT -> bundle_id`
- `DEFERRED_ORDINARY_SERVICE -> exact reason`

Every omitted ordinary raw demand requires an exact receipt. Independent interrupt roots are never omitted after exact-root fan-in.

---

## 4. Demand admission — strict about existence, honest about missing enrichment

EAF does **not** scan every Markdown workstream and infer executive work.

A demand enters the allocator only from an accepted explicit source such as:

- Wake / Executive Inbox obligation;
- accepted semantic turn-owner fact;
- structured Agent OS `needs_ceo` / decision gate where its contract makes it an attention source;
- another explicitly accepted source-owner contract introduced through versioned architecture.

Do not derive authoritative demand, authority, deadline, impact, wait or urgency from prose such as:

- `Decide ...`
- `Next: Sol commissioning ...`
- `WAITING_CAPACITY / needs_placement`
- `urgent` / `critical` in titles.

Free text can be displayed as context after admission. It cannot create the authoritative factor vector.

### Real canary finding

Current portfolio state proves why this matters:

- Breathing Platform has durable `owner: ceo-sol` while the next live action is placement-owned `WAITING_CAPACITY`; owner != current cognition turn.
- Account Identity Hardening says `Decide the CI gate fix` while its structured owner is `terminal-platform`; verb + user-facing blast radius is not executive authority or actual impact.
- Advanced Data Options prose says `Sol commissioning of AD-1T2` while its prior `needs_ceo` source gate is explicitly retired; semantic text matching must not resurrect it.

---

## 5. Source-backed pressure vector — no global scalar

For admitted demand, derive only facts whose accepted owner can support them.

### 5.1 Time/window pressure

Use explicit source-owned `by_when`, response window, external deadline or incident window.

No deadline field means unknown/open timing, not proof delay is free. Do not NLP-extract dates from prose into authority-grade factors.

### 5.2 Actual impact vs blast radius

Keep separate:

- **actual current impact** — source-owned live user/production/business harm;
- **blast radius/reversibility** — potential consequence of a change/decision.

`blast_radius: user_facing` does not prove users are currently harmed.

### 5.3 Reversibility

Use accepted source facts to distinguish reversible, costly reversal, irreversible/authority-sensitive, unknown. This affects evidence/optionality, not authority.

### 5.4 Exact dependency unblock

Use exact Agent OS dependency/root identities and current readiness. Expose the blocked member set.

Do **not** call descendant count a critical path. `critical path`, float/slack and CPM claims require actual network timing/duration evidence.

### 5.5 Active resource burn

Use only source-owned Executive runtime/Capacity evidence. Current/future burn can raise pressure. Historical sunk tokens/engineering effort are not priority.

Burn never authorizes cancellation, retry, target transfer or failover.

### 5.6 Autonomous progress remaining

Use accepted turn/runtime/placement/blocker facts to identify `NO_SAFE_PROGRESS`, partial safe progress, full safe progress or unknown.

This is central to interruption reduction: valuable work that can safely continue should normally batch rather than interrupt.

### 5.7 Information / option value of waiting

An explicit expected information event, authored typed wait or accepted external/calendar condition can justify waiting when action is reversible/costly to reverse.

Uncertainty alone does not create a valid wait. Missing/stale truth is usually a serviceability/source problem, not option value.

### 5.8 Evidence/freshness

Every load-bearing factor carries owner/source/effective or event time/observation time/freshness/conflict where available.

Freshness is **owner-relative**. No universal `older than N minutes = stale` TTL may be invented across incidents, Agent OS decisions, market-session facts and strategic approvals.

### 5.9 Ready age / fairness

Use the earliest source-backed moment the same unresolved demand became actionable. Repeated Wake delivery, file modification, summary regeneration or observation refresh never resets age.

If no canonical ready time exists, fairness age is `UNKNOWN`; do not create allocator-local age state.

### 5.10 Context affinity

Same responsibility/root/program may reduce switching cost among equivalent/comparable non-emergency work. Context affinity never hides/demotes an interrupt or changes authority.

### 5.11 Cost of Delay

If an accepted owner supplies a real time-dependent delay-cost function/value, EAF may carry it with receipts.

V1 has **no universal WSJF**:

- PR size/story points/implementation duration != executive cognition time;
- worker token/runtime burn != executive service duration;
- model-estimated `minutes to decide` is not authority-grade scheduling data;
- sunk cost is not forward priority.

A later bounded homogeneous decision family may use an explicit validated ratio rule only when both delay-cost and scarce-resource service-time bases are source-backed/comparable.

---

## 6. Classification and service policy

### 6.1 First classify pressure; separately evaluate serviceability

Do not replace urgency with a reconcile bucket.

Examples:

```text
SOL / INTERRUPT_NOW / BLOCKED(ACTION_TARGET_UNAVAILABLE)
CHAIRMAN / INTERRUPT_NOW / BLOCKED(AUTHORITY_SOURCE_CONFLICT)
SOL / FOCUS_NOW / BLOCKED(EFFECT_UNKNOWN)
SOL / BATCH_NEXT / READY
SOL / VALID_WAIT / NOT_APPLICABLE
```

If urgency itself depends on the conflicted source, then urgency cannot be asserted beyond the evidence. Otherwise valid pressure remains visible while action is blocked.

### 6.2 Exact Sol target composition

For Sol-class/root-Job demand, consume the accepted exact action-target resolver when its episode evidence is available:

- exact root Job -> CEO alias;
- complete RuntimeBinding snapshot;
- no fallback to workstream/seat default;
- no sister-Sol promotion;
- observer-only consumer remains non-authoritative;
- enforcement re-resolves current evidence before action.

EAF is a projection consumer, not target-transfer owner.

### 6.3 EFFECT_UNKNOWN

`EFFECT_UNKNOWN` blocks action/retry/failover but does not erase time pressure. Preserve the pressure class and set serviceability blocked.

---

## 7. Exact root fan-in

Automatic bundle/suppression is allowed only on hard canonical relations:

- same exact decision/ref;
- same exact blocker/root responsibility;
- same accepted Wake/source correlation/root Job equivalence;
- exact dependency root;
- exact release/review gate.

Semantic similarity, embeddings or LLM judgment may **not** suppress a demand.

Bundle identity is deterministically derived from canonical root + ordered member identities. No mutable bundle ledger.

If members have different authority/serviceability, the root card preserves those per-member boundaries; context grouping never grants shared permission.

---

## 8. Genuine partial order — no hidden totalization

Within the same authority and actionable pressure class, compare grounded load-bearing dimensions.

Conceptual relations:

- `DOMINATES`
- `EQUIVALENT`
- `INCOMPARABLE_TRADEOFF`
- `INCOMPARABLE_UNKNOWN`
- `INVALID_FOR_COMPARISON`

A demand dominates another only if no worse on every comparable load-bearing pressure dimension and strictly stronger on at least one, with no conflict that invalidates comparison.

When two demands are real tradeoffs — e.g. one has a critical time window while another has larger exact unblock and no safe progress — **both may remain on the frontier**. Do not secretly totalize them through weights, enum order, lexicographic order, ingestion order, random order, title order or a model.

A unique `#1` is an evidence result, not a UI requirement.

### Local service tie-breakers

For equivalent/comparable ordinary demand only:

- context affinity may choose a related batch;
- source-backed age may support fairness service.

These do not rewrite dominance.

---

## 9. Anti-starvation

For each active executive authority partition with eligible ordinary backlog, expose at least one **oldest-ready fairness sentinel** when it is not already represented.

The sentinel:

- is visibility/service protection, not a priority score;
- never suppresses an interrupt;
- does not make a valid future wait overdue early;
- does not turn an old but materially weaker ordinary demand into a stronger pressure class;
- remains visible as deferred debt during sustained emergency pressure.

Unknown ready time appears as a coverage gap, not age zero.

---

## 10. Concurrent-demand / overload truth

After exact fan-in, every independent `INTERRUPT_NOW` root remains visible.

Per authority, expose conceptual `concurrent_demand` states:

- `NONE`
- `SINGLE`
- `MULTIPLE_INDEPENDENT`
- `PROVEN_WINDOW_COLLISION`
- `FEASIBILITY_UNKNOWN`

Multiple interrupts prove **congestion pressure**, not automatically overload.

`PROVEN_WINDOW_COLLISION` requires source-backed decision windows plus accepted service/capacity evidence showing all independent roots cannot be serviced in time. Missing human cognition-duration/capacity facts => `FEASIBILITY_UNKNOWN`.

Congestion never grants delegation, target transfer or authority escalation.

Example UI truth:

```text
SOL — 3 interrupts
1 READY
1 BLOCKED: exact target unavailable
1 UNKNOWN: target evidence unavailable
service feasibility: UNKNOWN
```

---

## 11. Anti-gaming and correction law

- Free-text `urgent`, `critical`, `CEO` has zero direct priority/authority power.
- `needs_ceo` is not Chairman, urgency or impact.
- Re-notification/re-render/rewrite timestamps never reset actionable age.
- Unknown is not zero, healthy, unlimited or harmless.
- Semantic/LLM similarity cannot suppress.
- Model summaries have zero authority over admission, grouping, ordering, authority, action, dispatch, retry, merge or release.
- `EFFECT_UNKNOWN` never permits re-carriering or failover.
- High economic delay never changes authority.
- Stage-A target code existence never becomes live target evidence.
- Current corrected truth may not be backdated into historical replay.
- A corrected source snapshot creates a new pure EAF result; no hidden mutable rank ledger is repaired in place.

---

## 12. V1 wire semantics

Exact field names are an A1 contract detail, but semantics must preserve:

```text
schema = mastermind.executive_attention_frontier.v1
snapshot_identity
source_freshness_summary
coverage_summary

authority_frontiers[]
  authority_requirement
  interrupt_root_count
  interrupt_member_count
  concurrent_demand
  feasibility_receipts[]

bundles[]
  bundle_id
  canonical_root_ref
  members[]

items[]
  demand_id
  responsibility_ref
  authority_requirement
  authority_source
  attention_class
  pressure_reasons[]
  serviceability
  serviceability_reasons[]
  exact_action_target|null
  actor_can_act: true|false|unknown
  factor_vector
  became_actionable_at|null
  wait_context|null
  downstream_unblocks[]
  active_resource_burn|null
  cost_of_delay|null
  bundle_id|null
  projection_relation
  explanation_reasons[]
  source_receipts[]
  issues[]

fairness_sentinels[]
```

V1 does not require `priority_score`, `authority_score`, `confidence_score`, mutable queue position, mutable age ledger or model rank.

---

## 13. Control Room experience

The front page becomes calmer **without hiding truth**.

Primary composition:

- Interrupts now
- Focus now
- Context batches next
- Intentional waits
- Autonomous continuation
- Source/action-path issues
- Concurrent executive pressure

Card order:

1. decision/action needed;
2. **attention pressure**;
3. **authority**;
4. **can act now? / exact target if available**;
5. why now;
6. why not later / what can continue;
7. what exact work it unblocks;
8. evidence/freshness;
9. bundle/root context;
10. forensic source/surface navigation.

Do not use red urgency styling to imply permission. Do not use grey blocked styling to imply low urgency.

Chairman view is the canonical Chairman-authority partition, not “top score.” Sol view is the Sol partition. A Sol emergency with unavailable target stays a Sol emergency; it does not become Chairman work.

All raw forensic demands remain reachable. A primary-view card limit is not a lawful omission reason.

---

## 14. Chat-native CEO consumption

A compact snapshot may expose:

```text
CHAIRMAN
  interrupts: <complete root set>
  focus_now: <non-dominated set>
  batch_next: <bounded context groups>
  serviceability_issues: <counts/critical exact refs>

SOL
  interrupts: <complete root set>
  focus_now: <non-dominated set>
  batch_next: <bounded context groups>
  exact_target_status

portfolio
  valid_wait_count + nearest review boundary
  autonomous_continue_count
  oldest_ready_fairness_sentinels
  source_coverage/degraded summary
```

This is context, not a stored inbox. Acting still requires the existing current authority/runtime gates.

---

## 15. Evaluation — point-in-time or it does not count

### S0 — deterministic adversarial corpus

Run the complete frozen corpus, including at minimum:

- Chairman-only emergency vs more urgent Sol item;
- exact root symptom storm vs merely semantically similar items;
- stale/conflicted authority;
- `EFFECT_UNKNOWN` urgent demand;
- old valid wait vs overdue wait;
- safe autonomous progress vs no-safe-progress unblock;
- active burn without authority change;
- timestamp refresh attack;
- context batch/fairness behavior;
- multiple independent emergencies and unknown/proven service feasibility;
- genuine incomparable tradeoff and reversed input order;
- owner-relative freshness;
- implementation-size/WSJF category errors;
- exact Sol target unavailable/conflict/observer-only/missing-live-evidence cases;
- owner fallback attack (`owner: ceo-sol` must not replace missing exact root target).

Permutation stability and exact receipt accounting are mandatory.

### S1 — frozen real-source snapshot

Read current canonical sources and prove identities, unknown handling, owner boundaries, exact fan-in and omission receipts. No historical performance claim.

### S2 — point-in-time historical replay

At replay time `t`, use only facts observable at `t`. Later outcomes/corrections may label the episode but cannot become contemporaneous inputs. Unreconstructable data is `UNREPLAYABLE_INPUT_GAP`.

### S3 — prospective real multi-program shadow

Strongest calibration evidence. Compute EAF report-only at decision time, allow the organization to operate normally, then compare actual interventions/outcomes later.

### S4 — Control Room default composition

Only after accepted S3 may EAF become the default compact attention composition. Raw facts remain available.

### S5 — proactive delivery

Out of initial program scope. Any change to Wake/notification cadence/routing requires a separate architecture/release under the existing Wake owner. EAF success does not grant delivery authority.

### Metric families

Report together:

1. **demand/source coverage** — identity, authority, ready time, deadlines, waits, impact, autonomy, replayability;
2. **compression/fan-in** — raw obligations → exact roots → active frontier, with all suppression receipts;
3. **interrupt safety** — accepted critical recall, misses, authority violations, hidden independent interrupts, false confidence on stale/unknown truth;
4. **interruption reduction** — Chairman/Sol interruption episodes and avoidable interruptions, not raw notification count alone;
5. **delay/starvation** — ready age, fairness debt, decision-window misses, time to decision where source-owned;
6. **wait fidelity** — honored waits, overdue re-evaluation, false early interruptions, invented waits (must be zero);
7. **congestion pressure** — independent interrupt roots, duration, proven collisions, fairness debt under emergencies.

Establish a real baseline before numeric improvement targets. Hard zero-violation laws do not wait for calibration.

---

## 16. Capability ledger at consolidated freeze

| Capability | State |
|---|---|
| Agent OS durable responsibility/dependency/wait truth | `PROVEN_LIVE` |
| Executive lifecycle/effect authority | canonical existing owner |
| Wake/Executive Inbox attention source | `PARTIAL` end-to-end organizational coverage |
| Chat-native Meta-CEO architecture | `SPEC_ONLY` / architecture-frozen elsewhere |
| AD-SOL1 exact Sol action-target Stage A | `BUILT_NOT_PROVEN / PRODUCTION_INERT` on protected source |
| OCR-6 Executive Steward PR #228 | `BUILT_NOT_PROVEN / KNOWN_CORRECTNESS_BLOCKER / PRODUCTION_INERT` at this freeze unless newer canonical proof supersedes it |
| Chairman Control Room existing base | `PROVEN_LIVE` for accepted existing slices |
| EAF F0G architecture | `SPEC_ONLY` until this PR is protected |
| EAF A1 deterministic engine | `NOT_BUILT` |
| EAF A1R independent semantics review | `NOT_BUILT` |
| EAF A2 prospective/report-only shadow | `NOT_BUILT` |
| EAF A3 Control Room product | `NOT_BUILT` |
| EAF A4 Chat-native consumer | `NOT_BUILT` |
| EAF A5 prospective value proof | `NOT_PROVEN` |

---

## 17. Current implementation gate

A1 may not fork or bypass OCR-6 Executive Steward.

At the latest canonical reconciliation during this freeze, #228 remains the existing sole Steward carrier with the known integrity defect where presentation filtering can hide canonical responsibility/attention identity conflicts unless complete grouping happens first. A separate successor operation owns that repair.

**A1 gate:** corrected Steward bytes must be reviewed, accepted and protected before EAF treats Steward as its real normalized source seam.

This gate does not prevent architecture, deterministic fixture preparation or independent source-contract research that does not consume the defective output. It does block claiming the EAF engine is integrated against trustworthy Steward truth.

---

## 18. Bounded build waves

### A1 — deterministic core

**Mission:** immutable explicit attention demands + source-attributed structured context -> deterministic `mastermind.executive_attention_frontier.v1` result with authority/pressure/serviceability/projection separation, exact bundles, partial-order relations, fairness, concurrent-demand truth and receipts.

**Preferred avenue:** `CTO Sol`  
**Receiver mode:** `CAPACITY_SELECTABLE`  
**Placement until gate/receiver:** `WAITING_CAPACITY / needs_placement`  
**Why not Fable:** architecture and authority boundaries are frozen; implementation is difficult but bounded and falsifiable.

No gather daemon, DB, mutable queue, Wake mutation, target transfer, placement, retry engine, LLM ranking or UI in A1.

### A1R — independent adversarial review

Attack authority leakage, urgency/serviceability conflation, exact-target fallback, hidden totalization, semantic suppression, freshness, option-to-wait, fairness, concurrent interrupts, cost-of-delay misuse and point-in-time determinism. Reviewer receives no merge/release authority.

### A2 — real report-only shadow adaptor

Consume current protected owners, expose coverage/degraded metrics and preserve all receipts. No notification/lifecycle/placement side effects.

### A3 — Control Room Attention Frontier

Existing Control Room compositor only. Calm compact surface + forensic drilldown + desktop/narrow browser proof. Preferred bounded UI avenue: Terra unless current capacity/complexity evidence justifies another route.

### A4 — Chat-native CEO consumer

Project same EAF snapshot into accepted Meta-CEO/Program-CEO context path. No stored chat inbox or session identity creation.

### A5 — prospective multi-program calibration/promotion

Measure real baseline, run prospective shadow, adjudicate disputed episodes, freeze numeric thresholds, then decide whether EAF becomes default compact composition. Program is not complete before this real proof.

---

## 19. Absolute no-rebuild boundary

Do not create:

- a new Job/Attempt/Worker lifecycle;
- a new durable attention DB/queue/cursor/age ledger;
- a second Wake/Inbox/delivery scheduler;
- a second RuntimeBinding/SessionTarget registry;
- a target-transfer or sister-Sol promotion path;
- a second Model Router/Capacity placer;
- a model ranker or semantic suppressor;
- a global priority/authority/confidence scalar;
- a universal freshness TTL;
- a false `critical path` from descendant count;
- a global executive WSJF from implementation size;
- automatic dispatch/retry/failover/merge/release from attention state;
- a Control Room-only truth store;
- a historical replay that substitutes current truth for past observable state.

---

## 20. Program completion standard

This program is complete only when:

**Truth** — explicit demand/source coverage is high enough, corrections/freshness/unknowns are honest, and exact target/authority boundaries survive.  
**Intelligence** — valid demand is pressure-classified, serviceability-separated, exact-fanned-in, partial-ordered, optionality-aware and anti-starvation without a magic scalar.  
**Product** — Chairman/Sol can use a calm Control Room and Chat-native frontier across real states.  
**Learning** — a prospective multi-program interval shows materially less executive scanning/interruption versus baseline with no accepted severe-decision misses, no priority-driven authority leakage, no hidden independent interrupts and no harmful severe-decision latency regression.

Until then, EAF is architecture, implementation or shadow evidence — not the accepted cognition-allocation ruler.
