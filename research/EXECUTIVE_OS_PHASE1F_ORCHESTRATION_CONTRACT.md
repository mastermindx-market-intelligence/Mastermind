# Executive OS Phase 1F — hierarchical orchestration contract

**Status:** Phase 1F-A/1F-B accepted baseline plus Phase 1F-C inert implementation
merged in `db0bac5`. The additive schema-v4/runtime/result/cycle surfaces are
built and deterministically tested, but are not deployed, scheduled, armed, or
accepted as live capability. The governing 1F-C source law is
`research/EXECUTIVE_OS_PHASE1FC_CEO_POLICY_AND_IMPLEMENTATION_COMMISSION_2026-08-20.md`
as accepted by merge `a49ac647fff64d034cc965cf54ac48968d6c15be`; this older design memo is
subordinate where the accepted commission repaired it. The historical
implementation base was Mastermind protected `master`
`90db9baf5bcc5f2221e3c9870c2aa09a95293c99`; current protected master includes
the accepted implementation via `db0bac5`.
**Shipped alongside:** `control_plane/executive_inbox.py` + `scripts/executive_inbox.py`
+ `docs/EXECUTIVE_INBOX.md` (the `mastermind.executive_inbox.v2` read-only projection)
+ `control_plane/executive_runtime.py` schema migration 2.
**Review:** an independent fresh-context adversarial review (2026-08-14) attacked
this memo alongside the 1F-A code; its six memo findings (creator-set escalation
routing, impact-as-ordering, the escalation path's dependence on §5 kinds,
unbounded void-review replacement, review-of-review regress, fleet-wide cycle
dispatch) are fixed in place and marked "review finding N" where they landed.
**Authority:** this memo binds later 1F phases the way
`research/EXECUTIVE_OS_STRATEGIC_STATE_BOOTSTRAP.md` §4 binds strategic-state
consumers: a later phase that wants to violate a law here supersedes the law in
writing first (CEO ruling), never silently.
**Source law above this file:** `research/MASTERMIND_CHARTER_V2.md` (P1–P10),
`config/strategic_state.yml` (`duplicate_control_planes: prohibited`),
`config/authority_map.yml`, `AGENTS.md` § "Executive contract".

---

## §0 What 1F is, in one paragraph

The Executive OS runtime (Phase 1A–1E) can durably hold jobs, lease them to isolated
workers, and accept bounded CEO intents. Phase 1F adds the governed organization:
hundreds of worker/job events have no compression into executive attention (fixed by
1F-A's inbox), jobs have no parent/child structure and no independent-review shape
(implemented in §3, with runtime acceptance evidence), and the inert 1F-C branch
adds the bounded COO cycle that turns one accepted parent objective into deterministic
child, review, repair, and aggregation-handoff transitions. It remains fixture/local
implementation evidence until the later live gates are separately accepted. The CEO must
eventually operate by exception. Everything below serves that, under one constraint
repeated until it is boring: **the existing SQLite runtime remains the only lifecycle
authority, and nothing in 1F creates a second control plane.**

---

## §1 The orchestration contract (laws every 1F phase obeys)

L1. **One lifecycle authority.** Job/Attempt/Worker/Event state lives in
    `control_plane/executive_runtime.py`'s store and nowhere else. No sidecar
    orchestration DB, no queue, no scheduler, no lease system, no liveness table, no
    message-bus task store. A 1F phase that needs new durable state extends the
    existing schema via the existing migration mechanism (`SCHEMA_VERSION`,
    `schema_migrations`), additively.

L2. **Projections never gate.** The inbox (and any later report surface) is
    read-only orientation. Nothing may branch on inbox output to decide whether work
    runs. If a field is worth gating on, it belongs in the runtime schema and the
    gate belongs in the runtime/authority policy, reviewed.

L3. **The Improvement Agenda remains the company priority queue.** 1F ranks nothing.
    `priority` on a Job orders already-eligible work inside the runtime; the agenda
    and strategic state own what the company should do next. The inbox identifies
    *attention*, which is neither eligibility nor priority.

L4. **Authority is downstream of the authority map, only.** `owner_seat`,
    `escalation_target`, `business_impact`, `department`, P0 ids, actor names, and
    every other 1F field are descriptive labels. Capability comes exclusively from
    `requested_authorities` × `config/authority_map.yml` × the packet gate ×
    `ExecutiveAuthorityPolicy`. A job owned by "ceo" gets zero extra capability; a
    "critical" job gets zero extra capability; a reviewer gets zero write access to
    the tree it reviews by virtue of being a reviewer.

L5. **Ownership ≠ authority. Review ≠ execution. Escalation ≠ priority.**
    - *Ownership* answers "who is accountable for shepherding this to done."
    - *Review* is a verdict on evidence; it gates **aggregation**, never dispatch.
    - *Escalation* routes attention on exception to a seat; it never reorders the
      queue and never raises capability.

L6. **Bounded everything.** Fan-out, depth, repair rounds, attempts, cost class:
    every 1F-C loop variable has a reviewed ceiling in config, and children may only
    narrow (never exceed) the parent's authority set, write-path set, and cost
    class. Shrink-only, charter P2 flavor.

L7. **Nothing self-invokes upward.** No automatic CEO/Chairman invocation, no
    persistent Sol/Fable process, no push notifications. The inbox is a pull
    surface. The CEO-seat wake mechanism, when it comes, sits ABOVE the worker
    runtime in its own reviewed phase.

L8. **Idempotency rides `command_id`.** Any 1F actor that creates jobs names its
    commands (`coo-cycle:<parent>:<step>:<n>` namespace, exactly like
    `ceo-intent:`), so a crashed and re-run cycle collides atomically in the events
    table instead of duplicating children. No dedupe store.

L9. **Determinism where the CEO reads.** Same canonical state + frozen clock ⇒
    byte-identical projection output. Anything nondeterministic (wall clock, dict
    order, uuids) is a defect in an executive surface.

L10. **Honest degradation.** An unreadable input is a named `degraded` entry, never
    a synthesized empty success, and never a crash that takes unrelated Executive OS
    execution down with it.

---

## §2 The executive-seat audit (deliverable B)

**Question:** does `config/agents.yml` constitute a machine-readable executive-seat
registry, as the Executive contract's prose citation ("AI CEO — GPT-5.6 Sol
(`config/agents.yml` → `codex.model`)") might suggest?

**Finding: NO — it is model/provider routing, not an organizational registry.**
Verified against the file at `9603b408`:

- Its own header: "In-house model-tier routing policy for the Mastermind reasoning
  layer." The `roles:` block (`pm`, `deep`, `analyst`, `scout`, `fable`) maps
  *reasoning-call roles* to *model tiers* (opus/sonnet/haiku/fable). These are call
  shapes, not seats: `pm` is "which model answers a portfolio-manager-shaped call,"
  not "who is the PM of the company."
- `codex.model: gpt-5.6-sol` is the provider default for **every** codex-backend
  role (all five roles map to the same model). Reading it as "the CEO seat" is
  accurate only in the narrow sense that the model id which happens to occupy the
  CEO seat is recorded there. The file declares no hierarchy, no Chairman, no COO,
  no worker identity, and no seat→occupant binding.
- The executive hierarchy (Chairman Chris → CEO Sol → COO Fable → workers) exists
  **in prose only**: `AGENTS.md`/`CLAUDE.md` § "Executive contract". Nothing
  machine-reads seat occupancy today.
- The runtime's `workers` table is an execution-capacity registry (worker_id,
  provider, account_label, quota classes) — capacity, not org structure. `actor` in
  `ceo_intent.v1` is a regex-fenced free-text provenance label with, correctly, no
  privilege attached.

**Consequences for 1F-A (applied):** the inbox needs `coo|ceo|chairman` only as a
routing *vocabulary* for attention targets — words naming altitudes in the prose
hierarchy. It does not need a registry, so none was created. No fictional executives
were invented; no second registry exists to drift against `agents.yml`.

**Standing rule:** do NOT create a seat registry casually. The failure mode is
drift: a `seats.yml` quietly becomes an authority surface ("the file says Sol owns
this, so the session may…") — exactly the label-derived authority L4 prohibits.

**Smallest canonical representation, for a LATER phase (proposed, not built):** a
`seats:` block inside `config/authority_map.yml` — the already-reviewed,
conformance-tested governance file — mapping seat → `{occupant_label, description,
escalation_rank}`, with an explicit `authority: none` marker. Implement only when
something must machine-read seat occupancy (the CEO-wake mechanism above 1F-C is the
first plausible consumer). Until then, 1F-B's `owner_seat` and `escalation_target`
operate as regex-fenced validated vocabulary strings, and the prose contract remains
the source of truth for who occupies what.

---

## §3 Phase 1F-B — hierarchical ownership + independent review (design)

### 3.1 Schema: additive columns on `jobs` (SCHEMA_VERSION 1 → 2)

Extend the existing table via the existing migration mechanism. All columns
nullable or defaulted, so every existing row and every existing caller remains
valid; Phase 1B dispatch ignores all of them.

| column | type | default | meaning |
|---|---|---|---|
| `parent_job_id` | TEXT NULL → FK `jobs(job_id)` | NULL | this job is a child of that parent. **Immutable after creation; no reparenting, ever** — which structurally rules out cycles (a parent must already exist to be named). |
| `root_job_id` | TEXT NOT NULL → FK | self | top of this tree (parent's root, else self). Set by `create_job`, denormalized so tree queries need no recursion. |
| `depth` | INTEGER NOT NULL | 0 | parent.depth + 1. Bounded at creation against the reviewed ceiling (code check, not DDL — the ceiling is policy). |
| `owner_seat` | TEXT NOT NULL | `'coo'` | accountable seat, fenced `^[a-z][a-z0-9_-]{1,31}$`; conventional vocabulary `chairman|ceo|coo|worker`. Descriptive only (L4/L5). |
| `escalation_target` | TEXT NOT NULL | `'coo'` | validated ∈ {`coo`,`ceo`,`chairman`}: who decides when this job lands in a terminal exception the cycle cannot repair within bounds. **This is the structured field 1F-A's inbox deliberately lacks** — with it, CEO attention from runtime state becomes explicit evidence instead of inference. **Creation-bound, shrink-only (review finding 9):** a creator-set string must not become seat routing by fiat. A child's target may never exceed its parent's; `ceo` may be declared only where creation provenance already establishes the CEO seat asked (a `mastermind.ceo_intent.v1`-provenanced job, or a CEO-recorded decision cited in provenance); `chairman` only via a Chairman-recorded decision — there is NO code path that sets it from priority/impact/department. The runtime validates the vocabulary and the shrink rule; it attaches no behavior to the value. |
| `business_impact` | TEXT NOT NULL | `'routine'` | validated ∈ {`routine`,`material`,`critical`}. Classification for display ordering and review-requirement defaults at creation time. Not priority, not authority. |
| `review_required` | INTEGER NOT NULL | 0 | 1 ⇒ the parent may not aggregate this job's result to success without an approving independent review (3.3). |
| `reviews_job_id` | TEXT NULL → FK `jobs(job_id)` | NULL | set ⇒ this job IS a review of that job. A review job is an ordinary Job (same lifecycle, same authority fencing); this pointer is what makes independent review first-class and queryable. **Invariant (review finding 13): `reviews_job_id IS NOT NULL ⇒ review_required = 0`, enforced at creation** — a review is never itself review-required, or a `critical` parent's aggregation becomes an infinite regress of reviewers reviewing reviewers. |

`JOB_CREATED` event payload additionally records `{parent_job_id, root_job_id,
depth, owner_seat, escalation_target, business_impact, review_required,
reviews_job_id}` — no events-schema change needed (payload is free-form JSON).

### 3.2 `JobPayload` gains an optional `verdict`

`verdict: str = ""`, validated ∈ {`""`, `"approve"`, `"reject"`} in
`JobPayload.from_value` (anything else raises `StateConflict` — fail closed).
Additive: existing callers omit it and remain byte-identical. A reviewer expresses
"the work has defects" as `verdict: reject` + specifics in `errors`/`next_actions`;
`errors` alone still means "the review process itself hit errors." Conflating those
two was the alternative, and it is wrong: a clean review that finds bad work is a
*successful* attempt with a *negative* verdict.

### 3.3 The independent-review model

The anti-pattern being eliminated:

```text
same agent plans → same agent builds → same agent declares itself correct
```

- A review job is created (by the 1F-C cycle, or by hand) as a **sibling** under the
  same parent, with `reviews_job_id` → the reviewed job. It runs through the normal
  queue/claim/attempt path — fresh process, fresh worktree, fresh context by
  construction (the supervisor already gives every attempt an isolated process; the
  review job's own worktree/branch make the context fresh).
- The reviewer's objective embeds the reviewed job's **stated acceptance evidence**
  (AGENTS.md completion law), not the builder's self-report.
- Review authority is read-shaped: `READ` (+`RUN_TESTS`) — never `WRITE_BRANCH` on
  the reviewed tree. Reviewing grants nothing (L4).
- **Independence is checked at aggregation, not at dispatch:** a review counts as
  independent only if its completing attempt's `worker_id` differs from the reviewed
  job's completing attempt's `worker_id` (both already persisted on attempts;
  provider/account_label give a stricter optional check). Same worker ⇒ the review
  is **VOID** — not FAILED (the attempt may be honest), just not independent. Void
  is a cycle-level judgment recorded in the replacement review's provenance
  (`{reason: "review_not_independent", voids: <attempt_id>}`); the runtime needs no
  new state for it.
- Creation-time enforcement was considered and rejected: worker assignment happens
  at claim, so the creator cannot know the assignee; constraining provider/quota at
  creation remains available to the creator as an ordinary constraint.

### 3.4 Aggregation: integrity in the runtime, action in the cycle

The runtime gains **refusals only**, never automation:

- `complete_job(parent)` (and the attempt-terminal path that would complete it)
  raises `StateConflict` while any child is non-terminal, or while any child with
  `review_required=1` lacks a completed sibling review with `verdict: approve` whose
  independence check passes.
- `claim_job(job)` refuses a job that has living children (a parent with children is
  a **container**; dispatching it to a worker would run it twice — once as itself,
  once as its tree). This is the fail-closed floor. As an efficiency matter the
  Phase 1B dispatch iteration should also *skip* such parents rather than
  claim-and-refuse each cycle — that is a small change at the existing dispatch
  entry, not a new scheduler.
- Nothing in the runtime walks the tree on its own, completes parents on its own, or
  schedules anything. Aggregation is an explicit act of the 1F-C cycle: it reads
  child results, writes the parent's aggregated `JobPayload` via the existing
  `complete_job`/`fail_job`, and the refusals above make a premature or
  review-skipping aggregation impossible rather than impolite.

### 3.5 What 1F-B explicitly does not do

No new statuses (container-ness is derived from "has children", not a new enum
value). No new event store. No reviewer registry. No automatic review scheduling.
No cross-repo write. No inbox coupling beyond new *fields becoming readable*
(§5). No seat registry (§2).

### 3.6 Tests 1F-B must ship (the load-bearing set)

Migration: v1→v2 upgrade on a populated store preserves every row; idempotent;
fresh-create lands v2. Immutability: reparenting refused. Cycle-proofing: parent
chain cannot loop (parent must exist + immutable ⇒ prove by construction test).
Refusals: premature aggregation, review-skipping aggregation, non-independent
review, parent claim with living children — each refused with a named
`StateConflict`. Verdict vocabulary fail-closed. Review-of-review refused
(`reviews_job_id` + `review_required=1` at creation → `StateConflict`).
Escalation-target shrink rule refused (child target above parent's; `ceo` without
qualifying provenance; `chairman` without a Chairman-recorded decision).
Authority: reviewer job with WRITE_BRANCH on the reviewed
tree is creatable only through the normal authority policy (no review-specific
bypass — assert none exists). Inert-ness: Phase 1B dispatch of a childless job is
byte-identical to v1 behavior.

---

## §4 Phase 1F-C — bounded COO run-once orchestration (design)

### 4.1 Shape

`scripts/executive_os_coo_cycle.py run-once --parent JOB-nnn` — an **explicitly
invoked, run-once, deterministic bookkeeping pass**. No daemon, no polling, no
in-process model calls. All reasoning (planning, building, reviewing) happens inside
dispatched worker jobs through the existing supervisor path; the cycle only creates
jobs (existing API), dispatches (existing broker/phase-1B entry), collects (existing
readers), and aggregates (existing `complete_job`/`fail_job`, under §3.4 refusals).

**Dispatch is subtree-scoped (review finding 14).** The cycle dispatches ONLY jobs
whose `root_job_id` equals its parent's root — never a fleet-wide "dispatch whatever
is QUEUED" pass. The existing `executive_os_phase1b.py run-once` entry dispatches
any queued job with no proof-job gate (1E-A's honest-scope note); a cycle that
called it unscoped would dispatch strangers' jobs as a side effect of orchestrating
its own tree. The 1F-C implementation either passes an explicit job-id set to the
existing dispatch machinery or grows a `--root JOB-nnn` filter on that entry —
either way, the scope restriction is load-bearing, not stylistic.

### 4.2 The cycle state machine (one bounded step per invocation)

```text
accepted parent objective (existing QUEUED Job, e.g. via ceo-intent)
  → [no plan on file]        create ONE planning child; dispatch; stop
  → [plan, no children]      validate plan against bounds; create children
                             (parent-linked, review_required per impact); stop
  → [children terminal]      create missing independent review jobs; dispatch; stop
  → [reviews approved]       aggregate → complete_job(parent)  — or —
    [reviews reject]         create bounded repair children (round R+1); stop
  → [any bound exceeded]     leave parent in exception; the INBOX surfaces it
                             per escalation_target; a human/CEO acts. STOP.
```

"Plan on file" = the planning child's completed result payload (its
`next_actions`/`artifacts` carry the declared decomposition). The cycle never
invents a decomposition; it validates and instantiates one a worker job produced
and a bound permits.

### 4.3 Bounds (reviewed config, no self-granting)

A `coo_cycle_policy` block in `config/authority_map.yml` (same reviewed,
conformance-tested home as `executive_worker_policy`):

```yaml
coo_cycle_policy:
  schema_version: 1
  max_fan_out_per_parent: 8
  max_depth: 1
  max_repair_rounds: 2
  max_review_attempts_per_job: 2
  max_children_total: 16
  max_attempts_per_orchestration_job: 2
  review_job_attempt_limit: 1
  allowed_child_cost_classes: [default, small]
```

Hard rules enforced in the cycle (and, where cheap, as runtime refusals):
children's `requested_authorities` ⊆ parent's; children's `allowed_write_paths` ⊆
parent's; child `cost_class` ⊆ parent's ∩ policy list; `attempt_limit` ≤ parent's.
The cycle itself holds **no special capability**: every job it creates passes the
same `ExecutiveAuthorityPolicy` fence as any other caller, and the executive worker
policy's denied set (OPEN_PR / MERGE / DEPLOY / …) is untouched — so no automatic
merge/deploy authority exists to inherit.

### 4.4 Idempotency and crash-safety

Every cycle act is command-id-named: `coo-cycle:<parent>:<phase>:<n>` (L8). A
re-run after a crash re-issues the same commands and collides harmlessly; the cycle
recomputes its position from canonical state (which children exist, which are
terminal, which reviews approve) rather than from any cycle-local memory. The cycle
keeps **no state of its own** — killing it loses nothing.

### 4.5 Escalation flow (the exception path, closed)

Bound exceeded / repair rounds exhausted / review chronically void ⇒ the cycle
STOPS acting on that tree and the state itself is the signal: the inbox (§5) shows
the parent as a COO exception, or CEO attention when `escalation_target: ceo`. No
automatic CEO invocation (L7): the CEO-seat wake mechanism is a later phase that
sits above this cycle and reads the same inbox. Circularity is structurally absent:
escalation is a *label read by a projection*, not a call.

**Prerequisite (review finding 11): this path does not exist until §5's kinds
ship.** A bound-exceeded parent is a QUEUED container with `attempt_count` far
below its limit — which the SHIPPED 1F-A classifier suppresses into the `queued`
bucket as routine. The `aggregation_blocked` / `escalated_exception` kinds are
therefore a hard prerequisite of 1F-C's escalation story, not an additive
follow-on: they land in 1F-B (with the fields that make them evidence-bound), and
1F-C may not build against an inbox that lacks them. Sequenced in §6.5.

### 4.6 What 1F-C explicitly does not do

No scheduling loop (run-once only). No priority decisions (parent selection is the
caller's `--parent`; "which parent first" belongs to the CEO/agenda). No strategic
scope expansion (a child that needs paths/authorities outside the parent's grant is
a refused creation and an escalation, not a widened grant). No automatic merge,
deploy, or Agent OS/strategic-state writes. No CEO/model invocation from inside the
cycle. No new transport, no Slack, no chat rooms.

---

## §5 Inbox evolution under 1F-B/1F-C (additive)

`mastermind.executive_inbox.v1` is built for this: `kind` is an open (documented)
vocabulary and consumers must treat unknown kinds as attention, never as routine.
When 1F-B fields exist:

- terminal exception + `escalation_target: ceo` ⇒ `target: ceo`, kind
  `escalated_exception` — **and the item's reason must read as the declaration it
  is** ("the job DECLARES escalation_target: ceo", evidence = the column plus the
  creation provenance that qualified it under §3.1's shrink rule), never as the
  projection's own verdict (review finding 9: without the §3.1 creation bound and
  this presentation rule, a creator-set string would be handing out seat routing —
  the exact label-authority drift L4 and §2 prohibit). `chairman` likewise gains
  its first real source, only through §3.1's Chairman-recorded-decision gate. This
  replaces 1F-A's deliberate "runtime never produces CEO attention" stance with
  explicit evidence, not with inference.
- `review_not_independent` (void reviews), `aggregation_blocked` (children done,
  parent unaggregated ≥ N cycles), `repair_rounds_exhausted` ⇒ COO kinds.
- `business_impact` renders as a FIELD on the item, never as an order key (review
  finding 10: for a seat reading top-down, a display order IS a priority queue —
  L3 and the shipped doc's "sorted for determinism, not scored for importance"
  both forbid it; a self-declared creation label ranking the executive's reading
  order would be the hidden queue this contract exists to prevent). Ordering
  stays the 1F-A deterministic key.
- Suppression compresses per-tree: a healthy tree reports as one line
  (`root JOB-012: 6/8 children complete`), counts still reconcile.

Schema stays v1 through additive kinds; field additions to items bump to v2.

---

## §6 Closed Phase 1F-C rulings and remaining live boundary

The accepted Phase 1F-C commission closes the former open questions for inert v1:
policy lives in `config/authority_map.yml` with the exact ceilings in §4.3; review
verdicts are exactly `approve|reject`; live independence requires distinct
completing worker, OS principal/UID, provider home, and account; two VOID reviews
block with `review_not_independent`; there is no waiver. Phase 1F-B remains the
accepted baseline and Phase 1F-C is a separate additive schema-v4 build.

The branch stops before every live G0-G7 claim. It registers no workers or
providers, installs or migrates no host database, creates no scheduling service,
invokes no external model, and grants no Wake, MCP-B, Slack, Agent OS, Linear, PR,
merge, deploy, production, or capital authority. The explicit CLI is one
caller-selected `run-once --parent` mutation against an existing v4 fixture or
operator-selected root; it never polls or selects a parent. Production exact-ID
dispatch and arming require their separately reviewed later gates.

## §7 Architecture contradictions surfaced (for the return handoff)

None that block 1F-A. Two tensions to keep visible:

- `scripts/executive_os_phase1b.py run-once` still dispatches any QUEUED job with
  no proof-job gate (1E-A's honest-scope note). 1F-B's container-claim refusal
  narrows the blast radius for parents, but the underlying "run-once dispatches
  anything queued" remains the door 1F-C must be reviewed against before any
  automation ever wraps it.
- The Executive contract's prose seat citation (`config/agents.yml → codex.model`)
  over-claims what the file is (§2). Amending that one prose line to say "model
  routing policy; seat occupancy is this prose contract" is a docs-only follow-up
  for whichever session next touches `AGENTS.md`.
