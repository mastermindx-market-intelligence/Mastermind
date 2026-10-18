# Provider-native resource-composition and execution-mode contract — PROPOSAL

STATUS: PROPOSAL — HOLD-FOR-SOL
Census anchor: master@0fe8074ff953b2ced9025ed40f0f66019c759967 (every `file:line` in this document was read at
that commit; nothing here was asserted from memory).
Authority: Sol capacity-routing architecture ruling relayed 2026-09-16T06:52:49Z, consumed as R35; formal review
5220216985, addendum 5694353522, and R42/R51/R52 are additionally binding on this repair. This document
discharges **step A only** ("Freeze resource-composition + execution-mode semantics").
Proposed schema name/version (subject to the architecture review that is this document's release condition):
`mastermind.provider_capacity_resource_composition/v1`, **UNFROZEN pending the repaired semantics** — **not as
an independently acquired capacity truth**. The name is deliberately domain-explicit. The graph
must be embedded as Provider Capacity V2's closed sub-contract or cryptographically bound to exactly one V2
observation (§9.0).
Owner: the existing Shared AI Provider Control / Capacity authority. **No new owner is proposed.**

---

## R41 disposition

Sol R41 rules this proposal **REQUEST_CHANGES / STEP_A_NOT_FROZEN**. The six rulings are closed as follows:

| Ruling | Disposition |
|---|---|
| 1 — approvals and limits | §12 records D1 APPROVED; D2 APPROVED only for proven distinct account resources; D3 APPROVED with the §2.2 axis correction. Placement remains in `research/` while HOLD and is listed UNKNOWN in §9.3. |
| 2 — generation axes | §2.2 replaces one provider-resource generation with six axes and explicit non-effects; §2.3, §3, §4.6, §5.3, §6.3 and §8.3 propagate them. |
| 3 — one canonical Capacity artifact | §9.0 requires embedding in Provider Capacity V2 or exact cryptographic binding to one V2 observation. |
| 4 — existing CAP-C1 tie seam | §11.1 composes economics evidence with the existing reserved `select_placement` tie/preference seam. |
| 5 — one commitment lifecycle | §8.3 replaces the proposed provider-quota ledger with one canonical Executive commitment primitive; step G and the map inherit that gate. |
| 6 — Alibaba routing UNKNOWN | §3.3 and §5.4 record proven order/ceiling but UNKNOWN straddling; §10 compares hypothetical routings; §9.3 lists U1. |

---

## 0. What this document is, and the three things it must not become

Sol's finding (R35 §21): *"the economic calculator is ahead of the canonical capacity contract and live evidence
path. #7116 can reason over richer resource scenarios than `provider_capacity.v1` can truthfully publish today."*

The gap is not a missing balancer. It is that canonical Capacity has **no way to say how a provider's resources
deplete relative to each other**. Today a capacity option is a flat set of independent numbers. Real provider
plans are trees: windows that meter one spend, ceilings that bound a draw, packs that overflow in expiry order,
and accounts that are siblings rather than a pool. Until the tree can be written down, every downstream step
either flattens it — inventing capacity that does not exist, or stranding capacity that does — or stalls.

This contract is **a description language plus its evaluation rules**. It is explicitly NOT:

| NON-GOAL | Why it is excluded |
|---|---|
| A scheduler | Executive OS owns Job/Attempt/claim lifecycle. This contract produces inputs to a claim, never a claim. |
| A balancer or router | Model Router owns suitability; Capacity owns the economic **evidence** for placement inside the first lawful tier, and the existing C1 seam owns the placement act itself (§11.1). Unchanged. |
| A quota database | Provider Control already owns observation. This contract adds a *shape* to what Provider Control publishes, not a second store. |
| A daemon or queue | R35 §7: "Do NOT create a concurrency daemon." §8: "Do this without creating another queue." |
| A new owner | R35 §2: "Do not invent a parallel owner." Every construct below is minted under an existing authority. |
| An edit to strict `provider_capacity.v1` | See §9. That artifact is hash-pinned by a source-closure contract; changing it in place breaks the pin. |
| A reservation microservice | R35 §14: the claim-time hold is one narrow amendment to the existing Executive claim transaction (§8). |

It also does not ship a schema **file**. A machine-readable schema is a separate reviewed act. This document
proposes the semantics in prose plus one fenced illustrative example (§10), so that the review can attack the
semantics before any validator exists to entrench them.

---

## 1. The five separations this contract must preserve

R35 §1 requires five facts to stay distinct. Naming them here because every later rule refers to them:

1. **ENTITLEMENT** — what the contract theoretically grants.
2. **OBSERVED** — what the provider currently reports as remaining.
3. **POLICY-ELIGIBLE** — what the plan permits for *this exact execution mode* (§7).
4. **SCHEDULABLE** — observed minus holds, reserves, uncertainty margin, cooling, concurrency (§6).
5. **EFFECTIVE WORK** — how many accepted jobs of a cohort that schedulable capacity is expected to produce (§6).

Additional hard separation: **EXECUTION_LANES != ENTITLEMENT_RESOURCES.** Worker wrappers, process slots, and
host lanes are execution surfaces. They never multiply one provider resource or its `remaining`. Concurrency is
modelled separately as `safe_parallelism` (§4.3), never by minting another wallet (§5.3, matrix class 29).

A single percentage collapses all five and is therefore never a capacity fact. A provider can report 90 %
remaining and supply **zero** lawful autonomous capacity because (3) fails; it can report 5 % remaining and still
be the only lawful route for a hard job.

---

## 2. Resource identity and generation

### 2.1 Identity
A **provider resource** is an opaque, stable identifier for one bucket of provider-owned value or one
provider-enforced bound. Identity is minted by Provider Control and is never derived from, nor equal to:

- a model name (several models can debit one resource — R35 §5, §16),
- a host name (two Macs on one subscription are one resource — failure class 1),
- a worker id or a Mastermind quota class (those are *our* lifecycle objects),
- an API-key slot (a key is a binding to a resource, not the resource).

Provider Control also owns account identity, enrollment, policy mode, and usage. One login is one opaque
realm/account identity with its own native authentication/configuration partition (for example, one
`CLAUDE_CONFIG_DIR`). **No credential bytes ever live in Executive, Capacity, or Agent OS.** Four logins are
not four entitlements until each is proven lawful and carries `pool_membership_policy_eligible = true`: this is
the credential form of `EXECUTION_LANES != ENTITLEMENT_RESOURCES` (matrix class 29) and the D2 limit. Processes,
credentials, and views are the three forms of the same multiplication error; §5.2 and §5.3 close them together.

**Composition with Family-B.** Family-B (Mastermind #662 / Macro #7162) introduces `capacity_capability_id` as
the logical quota domain and `host_ref + capacity_capability_id + realm_generation` as the executable local realm
(R15). Resource identity is minted **inside** that namespace, not beside it:

> `resource_id := (capacity_capability_id, resource_key)` — where stable `resource_key` is a provider-scoped
> name for the specific bucket (`plan_5h`, `plan_weekly`, `seat_monthly`, `shared_pack:<pack_id>`,
> `member_pack_cap`, `concurrency`).

A stable identity plus a generation — never identity-with-generation-baked-in. A pack's epoch is carried in its
own `resource_generation`; it is not encoded into `resource_key`, which is stable across that epoch. Encoding
both would double-date identity and let a join silently mint a new wallet.

The consequence is the point of the whole exercise: **two `host_ref`s that resolve to the same
`capacity_capability_id` resolve to the same `resource_id`, and therefore to one set of numbers.** Host replicas
cannot multiply capacity by construction, not by a downstream check (failure class 1).

Family-B is composed with, not overloaded. Family-B answers *which logical domain and which executable realm*.
This contract answers *how the buckets inside that domain deplete relative to one another*. Family-B's own
architecture explicitly does not solve nested resource algebra (R35 §21); nothing here is appended to it
silently, and nothing here should be read as accepting Family-B B0 (still unaccepted — R19 (6)).

### 2.2 Generation axes
One word cannot carry all of the epochs that Provider Control, Family-B, and model economics need to date. The
former single "provider-resource generation" is therefore split into six axes. Each axis has one owner, and each
axis states what it does **not** invalidate:

| Axis | Meaning | Owner | Does not invalidate |
|---|---|---|---|
| `capability_generation` | What the subscription contract grants: product, tier, and seat entitlement. | Provider Control enrollment | Freshness alone; a bucket's identity unless that bucket is replaced; calibration governed by other axes. |
| `resource_generation` | The identity epoch of the bucket or wallet itself. It moves only when that bucket is replaced by a different bucket. | Provider Control resource identity | The bucket merely because it refilled; live holds; cohort/debit calibration. |
| `composition_generation` | The shape of the tree: which resources exist, in which operator, in which order, including seat-before-pack, nearest-expiry ordering, and presence of a member ceiling. | Provider Control deduction policy | Observed remaining in an unchanged bucket; live holds; rate/cohort calibration. |
| `realm_binding_generation` | The existing Family-B `realm_generation` field, renamed here only to identify this axis. This contract does not re-mint or replace that field. | Family-B realm owner | Quota amount, bucket identity, observed remaining, or holds bound to the resource epoch. |
| `model_harness_cost_generation` | Model alias/version, harness, debit multipliers, and rate card (or exact digests). | Model catalog / economics owner | The underlying shared wallet's balance or identity; live holds. |
| observation freshness | Not a generation: `observed_at`, the reset boundary, and staleness. It governs usability of a number. | Provider Control observation | Joins, hold binding, or calibration; crossing a reset only makes the old number stale. |

The required non-effects are normative:

- **Ordinary reset or renewal does not automatically create a new resource epoch.** A five-hour reset, weekly
  reset, or ordinary same-tier subscription renewal makes the observation STALE and requires a fresh observation.
  It does not bump `resource_generation`, does not orphan live holds, and does not reset calibration.
- **Key/API realm rotation is realm currentness, not new quota.** Bumping `realm_binding_generation` invalidates the
  executable binding; it does not create a new wallet, does not change observed remaining, and does not release
  or orphan holds bound to the resource epoch.
- **Model, harness, and cost changes invalidate cohort/debit evidence, not the underlying shared wallet.**
  Bumping `model_harness_cost_generation` retires q95/cost calibration to historical and reverts new placement
  to conservative; the resource's balance, identity, and live holds are untouched.
- **Holds bind the resource epoch plus immutable composition/debit evidence.** A hold is keyed by
  `(resource_id, resource_generation)` and additionally records, immutably, the `composition_generation` and
  `model_harness_cost_generation` under which it was computed. Bumping composition or cost re-dates FUTURE
  evaluation; it never rebinds or orphans a live hold.
- **A generation bump is never a reservation release.** Before a new `resource_generation` may authorize any
  claim, every nonterminal old-generation hold must be reconciled, conservatively carried/mapped forward, or the
  resource remains BLOCKED. Carrying the hold preserves its quantity and evidence; it does not rewrite history.
- **Claim evidence binds every applicable axis.** A claim receipt names all axes it was computed under, including
  `realm_binding_generation` and `model_harness_cost_generation`; absence is incomplete evidence, not zero.
- **Never orphan live holds or reset calibration by bumping the wrong axis.** That is the governing rule.

The old G1–G8 event list remains fully mapped; no event is lost:

| Old event | Axis(s) moved | Required non-effects |
|---|---|---|
| G1 plan generation change (tier up/down, plan replacement) | `capability_generation`; a plan replacement that replaces the bucket also moves `resource_generation`; an ordinary same-tier renewal moves neither. | Same-tier renewal is freshness-only and neither orphans holds nor resets calibration. |
| G2 seat assignment/reassignment | `capability_generation`; `resource_generation` only where the seat's bucket is a different bucket; UNKNOWN for Alibaba until enrollment is proven. | Reassignment alone does not create quota or change a surviving wallet's balance. |
| G3 subscription renewal / re-purchase | FRESHNESS ONLY for ordinary renewal at the same entitlement; `capability_generation` only if entitlement changed; a re-purchase that mints a new bucket creates a new `resource_id`. | A new shared pack is not an epoch bump on an existing resource; it is a new resource. |
| G4 API-key or realm binding change (including rotation) | `realm_binding_generation` ONLY. | No new wallet, no changed remaining, no hold release/orphaning. |
| G5 provider model generation change (including silent alias update) | `model_harness_cost_generation` ONLY. | Shared-wallet balance, identity, and live holds are untouched. |
| G6 shared-pack generation (pack purchased/retired) | `composition_generation`; a new pack gets a new `resource_id`. | Existing packs' `resource_generation` is unchanged. |
| G7 provider deduction-policy change | `composition_generation`. | This re-dates future evaluation and does not rebind or orphan live holds. |
| G8 model/harness/rate-card generation change | `model_harness_cost_generation`. | It invalidates cohort/debit evidence, not the shared wallet or live holds. |

### 2.3 Generation is not freshness — reset ≠ observed refill
The generation axes and observation freshness are deliberately separate, because conflating them is how a reset
silently manufactures capacity (R35 §15):

- **Generation axes** govern their respective joins, executable bindings, composition evidence, and calibration
  as stated in §2.2.
- **Observation freshness** governs *usability of a number*. Every observation carries `observed_at` and the
  reset boundary it was taken before. **Crossing a reset boundary makes the observation STALE, not larger.**
  After a reset, a claim requiring that resource waits for a new provider observation; it does not assume the
  entitlement value.

The one exception is a **deterministic refill contract**: an explicitly reviewed, per-resource statement that the
post-reset value is a known function of entitlement. Absent that reviewed statement, post-reset value is UNKNOWN.
A plan upgrade, shared-pack purchase, reset card, or coupon likewise moves the §2.2 axis it actually changes or
requires fresh observation — it never creates a synthetic balance and never bumps `resource_generation` merely
because value may refill.

**Forecast is not observation.** A forecast of capacity available after the next reset may be published for
expiry/stranding reasoning (Stage E, §11) but must carry a distinct field name and must never be summed into, or
substituted for, observed remaining (failure class 20).

---

## 3. The expression language

A **resource expression** `E` describes how one provider-lawful route's capacity depletes. Every node carries
an `id` that is unique inside the enclosing expression, because a CEILING must be able to say *what it bounds*:

```
E        := LEAF | ALL_OF(node, ...) | ORDERED_SPILL(node, ...) { stage_routing }
node     := { id, role, expr: E }
role     := BUDGET
          | CEILING { bounds: <id>, limit, window?, next_reset_at?, capability_generation,
                      resource_generation, composition_generation, realm_binding_generation,
                      model_harness_cost_generation, native_unit, cost_r(c), observation }
          | STAGE                          # the only lawful role inside ORDERED_SPILL
LEAF     := { resource_id, native_unit, capability_generation, resource_generation,
              composition_generation, realm_binding_generation, model_harness_cost_generation,
              cost(c), observation }
observation := { observed_remaining | UNKNOWN, observed_at, next_reset_at, freshness, expires_at? }
stage_routing := PARTITIONED | ATOMIC_FALLBACK        # provider-declared; see §3.3
```

Five well-formedness rules make the grammar evaluable rather than suggestive:

1. **`bounds` must resolve.** A CEILING's `bounds` names exactly one node that is a descendant of the same
   enclosing `ALL_OF`. A CEILING may not bound itself, may not bound a node outside that subtree, and two
   CEILINGs may bound the same node — in which case both apply and the tighter wins.
2. **A CEILING is a fully dated, unit-bound resource, not a constant.** It carries its stable `resource_id`,
   own `native_unit`, per-cohort cost vector, applicable §2.2 generations, `limit`, optional `window` and
   `next_reset_at`, and own `observation`. A *windowed* ceiling resets and goes stale on exactly the same rules
   as a BUDGET (§2.3); a non-windowed ceiling simply has no `next_reset_at`. Its `native_unit` must equal the
   unit of the entire subtree named by `bounds`; a mismatch is ill-formed.
3. **A proportional ceiling must be resolved to an absolute remainder.** A sublimit expressed as a fraction of
   its parent (the Claude/Fable case, §5.5) is
   `limit = fraction × entitlement(parent, current capability_generation)`, and its *remaining* is
   `limit − consumed_by_the_bounded_subtree`. If `consumed_by_the_bounded_subtree` is not observed, the
   ceiling's remaining is **UNKNOWN** and, by §4.5, so is the whole expression. This is the
   contract-level statement of the standing rule that fresh shared-parent telemetry alone can never make a
   subset `capacity_known`.
4. **No resource is a BUDGET twice in one expression.** A `resource_id` may appear once as a BUDGET and may
   additionally be *bounded* by any number of CEILINGs, but a second BUDGET occurrence of the same
   `resource_id` is ill-formed — that is the aliasing shape that double-debits. A resource that is genuinely
   both spent and bounding is written once as the BUDGET and referenced by `bounds` from the CEILING.
5. **Units are explicit and mismatches are ill-formed.** Every BUDGET and CEILING carries a stable
   `resource_id`, `native_unit`, applicable generation axes, and a per-cohort debit requirement `cost_r(c)` in
   that resource's native unit (or an explicit reviewed conversion). All stages of one `ORDERED_SPILL` must be
   unit-compatible. Tokens, requests, currency, and concurrency are not one unit; the evaluator never invents a
   conversion.

### 3.1 LEAF
A leaf names one resource, its provider-native unit (Credits, provider quota units, requests, …), its §2.2
generation axes, and its current observation (`observed_remaining`, `observed_at`, `next_reset_at`, `freshness`).
Native units are never compared across providers (R35 §10); comparison happens only after §6 converts headroom
into job equivalents.

### 3.2 ALL_OF — two child roles, because "and/or" is load-bearing
Sol's text defines ALL_OF as *"All children constrain and/or are debited by the operation."* That `and/or` hides
the single most common modelling error, so this contract splits it into two **typed child roles**:

- **BUDGET** — a depleting allowance denominated in the operation's native unit, with its own reset period. An
  operation of native cost `N` decrements every BUDGET child by `N`.
- **CEILING** — a bound on the cumulative draw routed through one *named sibling subexpression*. A CEILING is
  decremented only by the portion of `N` that was actually drawn through that subexpression. A CEILING never
  holds value and is never a source of capacity.

**The exactly-once invariant.** For one operation of native cost `N`:

> `N` is *partitioned* across ORDERED_SPILL stages (the partition sums to exactly `N`, §3.3), and every enclosing
> BUDGET child is decremented by `N`. **Decrementing two BUDGETs by `N` is one spend of `N` observed in two
> accounting windows — it is never a spend of `2N`, and the two BUDGETs are never summed into available value.**

That sentence is the contract. It is what makes GLM's 5-hour and weekly Credit pools two meters over one spend
rather than two wallets, and it is what makes MiniMax's per-model rows views rather than wallets (§5.3, failure
class 2).

### 3.3 ORDERED_SPILL — and the precondition that keeps it honest
`ORDERED_SPILL(s1, s2, …, sk)` means: the provider's own deduction rule consumes from `s1` until `s1` is
exhausted, then `s2`, and so on, in the order given. Order is provider-defined and is part of the contract — for
Alibaba shared packs the order is **nearest expiry first** (failure class 5).

That order is provider policy, not an evaluator heuristic. Provider Control (the producer) publishes a
**canonical stage order** with its own policy `composition_generation` and provenance. The evaluator validates
and consumes that order; it must never sort stages generically by expiry. A generic expiry policy is lawful only
when the provider contract explicitly defines it for those exact stages. Input that is not the published
canonical order is refused or flagged as ill-formed/inadmissible, never re-sorted.

One operation's cost may straddle a stage boundary: if `s1` has 3,000 units remaining and the operation costs
10,000, the operation debits 3,000 from `s1` and 7,000 from `s2`. The partition sums to exactly the cost — never
10,000 from each (failure class 3).

**Stage routing is a provider-declared fact, not our inference (normative).** Ordered consumption comes in two
provider shapes, and they do not evaluate the same way:

- **`PARTITIONED`** — the provider splits *one* operation across stages, as above. `avail` sums across stages
  (§4.1), because one job may draw from several.
- **`ATOMIC_FALLBACK`** — the provider itself serves one *indivisible* operation wholly from the first stage
  with sufficient balance, and falls back to the next stage otherwise. This is still provider-owned deduction —
  it is lawful `ORDERED_SPILL` — but no single operation may straddle, so `avail` for one operation is the
  **max** over admissible stages, not the sum (§4.1).

**Alibaba Team's stage routing is UNKNOWN, and this contract does not guess it.** Official Team docs prove the
deduction ORDER — seat first, then shared packs nearest expiry first — and the per-member shared-pack ceiling.
They do **not** prove that one request can straddle seat and pack. Until provider evidence or an authorized real
observation proves `PARTITIONED` versus `ATOMIC_FALLBACK`, Alibaba's `stage_routing` is **UNKNOWN** and every
Alibaba expression fails closed under §4.6 (§5.4, §9.3 U1).

**Partitionability precondition (normative).** `ORDERED_SPILL` is lawful only where the provider declares one of
those two routings for these stages. Where the provider declares neither — where *we* would be choosing which
stage to send an operation to — that is **placement among sibling routes**, already owned by Model Router's
gates and the existing C1 placement seam (§11.1), and it must never be written as a resource
operator. The test is *who performs the fallback*: the
provider, or us.

This precondition is not pedantry; it is the difference between a true capacity number and a fiction. Three GLM
Coding Plan Max accounts encoded as a `PARTITIONED` spill would evaluate to the *sum* of their 5-hour pools and
would authorise a job whose cost exceeds any single account's remainder — a job that cannot actually run anywhere
(§5.1). GLM publishes no cross-account fallback, so those accounts are placement, not spill; were a provider to
publish such a fallback, the correct encoding would be `ATOMIC_FALLBACK`, and the arithmetic would differ
accordingly.

### 3.4 What the language deliberately cannot express
There is no `ANY_OF` / alternation operator. Choosing among lawful routes is placement, and placement is an
existing owner's job. Adding alternation here would quietly move the allocator into the description language.

---

## 4. Evaluation semantics

Let `c` be a task cohort. `q95(c)` names the conservative **estimator** that produces each per-resource debit
requirement `cost_r(c)`, keyed on task class, model/harness `model_harness_cost_generation`, effort, context
band, and tool set (R35 §11). It is an upper estimate, never a cohort mean, and never one scalar imposed across
heterogeneous resources.

### 4.1 Typed evaluation and single-operation feasibility
Evaluation returns:

```
EvalResult := KNOWN(value) | KNOWN_ZERO(reason) | INELIGIBLE(reason) | UNKNOWN(reason) | STALE(reason)
```

Every non-KNOWN result carries a typed refusal reason and is reported, never silently zeroed. `avail(E)` is
retained only as the single-operation feasibility and reporting quantity; it is no longer the sizing primitive,
and `startable_jobs` is never `floor(avail/q95)` at the root.

A stage or child is eligible only if its execution mode is policy-eligible (§7), observation is FRESH (§2.3),
applicable §2.2 generations are current, its units are well formed, and it does not expire before the operation's
completion horizon.

`INELIGIBLE` and `KNOWN_ZERO` are different kinds of truth and are never interchangeable. `INELIGIBLE` is an
authority, rights, or execution-mode fact: this route is **not lawful** for this operation, and no amount of
remaining allowance makes it lawful. `KNOWN_ZERO` is a lawful numeric-capacity fact: this route **is** lawful,
current, and eligible, and it presently holds nothing, so a reset or a purchase would make it usable. Collapsing
the first into the second destroys the distinction the typed result and the §7 hard gate exist to preserve, and
downstream economics, reset and cooling logic, observability, and operator explanation all depend on that
distinction surviving composition.

A required `ALL_OF` child is never filtered out, and its class is preserved recursively. The parent's **primary
state** is the highest state present among its required children under the frozen deterministic precedence

```
INELIGIBLE > STALE > UNKNOWN > KNOWN_ZERO > KNOWN
```

read as exactly these five clauses:

1. If any required child is a known policy, rights, or execution-mode refusal — `INELIGIBLE(reason)` — the parent
   is `INELIGIBLE` with that child's reason.
2. Absent any such ineligibility, if any required child is `STALE(reason)`, the parent is `STALE` with that reason.
3. Absent both of those, if any required child is `UNKNOWN(reason)`, the parent is `UNKNOWN` with that reason.
4. Only when every other required child is current and eligible may a `KNOWN_ZERO(reason)` child make the parent
   `KNOWN_ZERO` with that reason.
5. Otherwise every required child is `KNOWN` and the parent is `KNOWN`; normal recursive sizing (§4.2) applies.

The same rule governs equivalent recursive required-child composition at every depth. A nested required `ALL_OF`
is itself a required child, so its own primary state — computed by these same five clauses — is what its parent
reads. A policy refusal at any depth therefore reaches the root as `INELIGIBLE` rather than decaying into a zero.

**Lower-precedence facts are retained, never discarded.** Precedence selects the parent's primary state only; it
never selects which children are reported. Every required child whose state is not `KNOWN` contributes its
`(child_identity, state, reason)` triple to the parent's `non_known_children` aggregate, which is carried
alongside the primary state. Aggregation is deterministic in all three respects:

- **Order** — canonical declared child order, that is, the order in which the children are declared in the
  expression (§3.2), applied pre-order at every depth so that a nested child follows the nested parent that
  declared it. The aggregate is never sorted by state, by precedence, by reason, or by evaluation/discovery order.
- **Deduplication** — triples equal in all three fields collapse to a single occurrence, retaining the earliest
  position in that canonical order. Triples differing in any field are distinct and all of them are kept; two
  children with the same state and reason but different identities are never merged.
- **Completeness** — no required child is omitted from the aggregate for any reason, and least of all because its
  state ranks below the primary state.

Provider-declared fallback skipping is the already-frozen `ORDERED_SPILL` contract stated in the next paragraph
and in §3.3. It governs spill stages only, and it is not — and may never be read as — a way to filter a required
`ALL_OF` child. "Admissible" may never mean "omitted from the min."

An `ORDERED_SPILL` stage may be skipped only under the provider-declared fallback contract. An UNKNOWN, STALE, or
otherwise undecidable earlier stage may not be treated as exhausted; the spill is UNKNOWN from that stage onward.
For homogeneous single-unit reporting:

```
avail(LEAF)                           = usable(LEAF)                         # §6.1
avail(ALL_OF(...))                    = min over BUDGET children, then each CEILING caps its bounded subtree
avail(ORDERED_SPILL, PARTITIONED)     = SUM over admissible stages
avail(ORDERED_SPILL, ATOMIC_FALLBACK) = MAX over admissible stages          # one indivisible operation
```

There is no lawful scalar `avail` for heterogeneous simultaneous budgets: each requirement remains in its own
`native_unit`, and whole-job count is evaluated by §4.2.

### 4.2 Recursive whole-job count
`jobs_fit(c, E)` is the sizing primitive and is evaluated per admitted execution mode (§7):

```
jobs_fit(c, LEAF) = floor(usable(LEAF) / cost_LEAF(c))

jobs_fit(c, ALL_OF(...)) =
    min over BUDGET children of jobs_fit(c, child)
    , then for each CEILING k capped by
      floor(remaining(k) / cost_k(c)) applied to the subtree named by k.bounds

jobs_fit(c, ORDERED_SPILL as PARTITIONED) =
    floor(SUM over admissible stages of avail(stage) / cost(c))

jobs_fit(c, ORDERED_SPILL as ATOMIC_FALLBACK) =
    SUM over admissible stages of jobs_fit(c, stage)
```

`startable_jobs(c, E) = jobs_fit(c, E)`. Heterogeneous simultaneous budgets use
`jobs_fit = min over r of floor(usable_r / cost_r(c))`, never `min(raw avail) / one q95`. A `PARTITIONED` spill
divides once over its stage sum because a job may straddle; `ATOMIC_FALLBACK` sums whole jobs per stage because
no job may straddle. That asymmetry is the point.

### 4.3 Concurrency is not a divisor
Concurrency is an observed dynamic resource (§6.3), not a term inside `startable_jobs`. It bounds *simultaneity*,
not *total count before exhaustion*:
```
safe_parallelism(c, E) = min( observed_safe_concurrency , startable_jobs(c, E) )
```
Folding concurrency into the `min` of §4.1 understates throughput by the ratio of total work to parallel work — a
concurrency of 3 does not mean only 3 jobs may be started before the next reset.

### 4.4 Horizon
`startable_jobs` is a point-in-time quantity. When two BUDGET children have different reset periods, the short
one is a **rate** constraint and the long one a **budget** constraint over any horizon longer than the short
period. Receding-horizon planning (R35 §8) is out of scope for step A, but the contract must carry
`next_reset_at` per leaf so that a later planner can do this without re-deriving the tree.

### 4.5 Stranded value is reported, never rounded away
Every evaluation additionally reports, per resource, the value that is real but unusable by this cohort, under a
typed reason: `stranded_at_ceiling` (a CEILING blocks it), `stranded_at_stage` (an `ATOMIC_FALLBACK` remainder
below `q95`), `stranded_below_cost` (a remainder below one job's cost), `ineligible_by_policy` (§7), and
`expiring_before_horizon`. A zero `startable_jobs` with no stranding reason is an incomplete answer: R35 §17's
"Alibaba: 68 % remaining" failure is precisely a number that conceals which resource is the bottleneck.

These reasons are diagnostics carried alongside `EvalResult`, not substitutes for it, and they never override the
typed state. `ineligible_by_policy` and `expiring_before_horizon` correspond to `INELIGIBLE(reason)`; under §4.1's
frozen precedence a required child in that state makes the parent `INELIGIBLE`, never `KNOWN_ZERO`.
`KNOWN_ZERO(reason)` is reserved for a required child that is lawful, current, and eligible but numerically
exhausted, and it reaches the parent only when every other required child is current and eligible. Stranded value
is reported even when the typed result is INELIGIBLE, UNKNOWN, or STALE, but it never converts that result into
capacity.

### 4.6 Unknown fails closed
If any leaf in `E` has UNKNOWN or STALE observation; unknown `capability_generation`, `resource_generation`,
`composition_generation`, `realm_binding_generation`, or `model_harness_cost_generation`; an unreconciled
`resource_generation` transition; unproven distinct entitlement/account resource status (§5.1–§5.2); unproven
view independence (§5.3); or UNKNOWN provider-declared `stage_routing` (§3.3, §5.4), the expression returns the
corresponding typed `UNKNOWN(reason)` / `STALE(reason)`, never zero and never entitlement. Such a result cannot
size capacity, authorise a claim, or satisfy `capacity_known`. It also does not make the route unusable for a
*human-attended* act — it makes it unusable as **autonomous Fabric capacity**.

---

## 5. Worked expressions for the current portfolio

Every number below that is not receipted at master is marked ILLUSTRATIVE or UNKNOWN. **No enrollment fact is
invented.** Actual Alibaba Team tier, actual MiniMax `capability_generation`, and actual Claude sublimit
remainders are UNKNOWN at this pin; §9 records what master actually models.

### 5.1 GLM Coding Plan Max — three accounts, one placement policy, NOT one pool
The seat currently operates **three** GLM Coding Plan Max accounts (`chairman-max`, `chairman-max-2`,
`chairman-max-3`) behind one shim. The truthful model is three resources:

```
for acct in {chairman-max, chairman-max-2, chairman-max-3}:
    E_glm[acct] = ALL_OF(
        BUDGET  glm_plan_5h[acct],        # Max: 28,000 Credits / 5 h
        BUDGET  glm_plan_weekly[acct]     # Max: 140,000 Credits / week
    )
```

- The two BUDGETs are **two meters over one spend** (§3.2). A 1,000-Credit operation decrements both by 1,000;
  available value is `min(usable_5h, usable_weekly)`, never their sum.
- The three accounts are **sibling routes**, not stages. `ORDERED_SPILL` is unlawful here by §3.3: a GLM request
  is served wholly by one account. Choosing among the three is placement.
- The three accounts are three expressions **only where each is a proven distinct entitlement/account resource**.
  Multiple sessions, hosts, dashboards, or model views of one account remain one expression — never three. Where
  distinctness is not proven, the accounts collapse to one expression and fail closed under §4.6. At this pin,
  that proof is a Provider Control fact we do not hold.
- Model-specific debit (GLM-5.3 ≈ 3× GLM-5.3-Flash for identical token composition, per the published
  multipliers) is a **cost prior**, never a scheduling constant. Master already carries the stronger rule:
  `control_plane/provider_model_economics.py:21` admits `measured_native_delta` as a burn method, and
  `config/provider_model_economics.v1.json` records for `glm.glm-5.3-flash`: *"Do not guess Flash credit
  multipliers; learn native burn from usage deltas by model/task cohort."*
- **Live defect this models.** The kit's local telemetry reports **one** 5-hour figure and one weekly figure
  against a single Max cap (`5h used/cap = …/28000`, `weekly used/cap = …/140000`) for a fabric holding **three**
  such plans — i.e. it publishes one plan's ceiling as the fabric's ceiling, understating the portfolio threefold
  while presenting a single percentage that cannot say which account is the bottleneck. A per-account row exists
  beside it, but it is derived from lane-ledger rows, so an account that has not yet been used simply does not
  appear — an account is invisible until it is spent, which is the wrong direction for a capacity instrument.
  A single aggregate percentage over N accounts is exactly the collapse §1 forbids; under this contract the three
  accounts are three expressions and the aggregate is not a capacity fact at all.
  *(Kit observation, not a Provider Control receipt; by R13-B2 such numbers are `UNVERIFIED_FOR_ROUTING`.
  Recorded as evidence of the defect, never as an enrollment fact.)*

### 5.2 OpenCode Go — one entitlement, three windows, per-model debit weight, policy gate
```
E_go = ALL_OF(
    BUDGET go_rolling_5h,
    BUDGET go_weekly,
    BUDGET go_monthly
)
```
- A request for model `m` debits `w(m)` normalised units, `w ∈ {1, 2, 4}` by published tier ($60/$30/$15 monthly
  per model per account). The weight is a **unit conversion inside one resource**, not a separate resource — this
  is the canonical example of R35 §5's "shared credit system with model-specific debit", and of failure class 2:
  the per-model request tables are conversion rates over one account-wide quota, not per-model pools. They are
  **DEBIT VIEWS over that one allowance, never separate wallets**, under the same rule as MiniMax's views (§5.3).
  The 5-hour, weekly, and monthly windows ($12/$30/$60 equivalents) meter one shared entitlement.
- The frontier budget gate (a weight-4 model refused once the account's monthly used percent reaches its
  threshold) is a **policy gate on placement**, not a capacity fact. It belongs to §7, not to `avail`.
- **MULTI-ACCOUNT POOLING IS HELD.** Go's terms prohibit using multiple accounts to circumvent limits, and its
  documentation says one member per workspace may subscribe. Admission requires
  `pool_membership_policy_eligible = true`, issued by Provider Control, **before any multi-member use**. Without
  that policy evidence there is no lawful pooled entitlement — not a smaller one, none. The schedulable Go
  entitlement count is therefore **1 proven-at-most; actual enrollment is UNKNOWN** (§9.3 U5).
- The first Go proof is exactly **ONE enrolled account** — no rollover, no account-A-to-account-B transfer, and
  no “3x.” **Never multiply limits by key or account count.** This is the same failure as
  `EXECUTION_LANES != ENTITLEMENT_RESOURCES`, arriving through credentials instead of processes (matrix classes
  29 and 33); a reader may not close one form and leave the other open.
- Go is an aggregator **OPTIONALITY** resource, not a cheap wallet. Preserve it for model families that are
  unavailable, ineligible, or exhausted on a direct route; cross-provider review independence; and overflow. Do
  not default Go to Luna, GLM, or MiniMax while abundant lawful direct capacity exists. Conversely, when direct
  MiniMax or Alibaba is UNATTENDED-ineligible, Go's MiniMax-M3 or Qwen route may be the lawful autonomous one:
  **policy eligibility beats prepaid size** (§7 is a hard gate, not a tag).
- Go's provider-intended mode is coding-agent / API use: it validates Claude Code, expects a coding-agent user
  agent, and expects a stable `x-opencode-session`. The mode admitted for Mastermind is therefore bounded
  `CODING_AGENT_API` (§7.1): coding-agent request/result consumption with stable sessions — not scraping,
  extraction, dataset generation, or multi-account pooling.

### 5.3 MiniMax Token Plan — per-model rows are EVIDENCE VIEWS, never wallets
```
E_minimax = ALL_OF(
    BUDGET minimax_plan_5h[capability_generation],
    BUDGET minimax_plan_weekly[capability_generation]
)
views(E_minimax) = { "MiniMax-M2.7": <row>, "MiniMax-M3": <row>, ... }  # independence: UNPROVEN
```
`/token_plan/remains` exposes model-oriented remaining rows and the #7103 parser preserves them. Preserving a row
is not establishing a wallet. Normative rules:

- A view with `independence: UNPROVEN` contributes **zero** additional available value. `avail` is computed from
  the underlying resources only. Views may be displayed; they may never be summed (failure class 14).
- Independence defaults to **UNPROVEN**. Promotion requires either explicit provider contract evidence or a
  reviewed, repeated causal experiment that declares observation resolution, lag budget, the same
  `resource_generation`, isolated operation attribution, and correction/retraction handling. A single observation
  pair is insufficient: reporting lag, rounding, caching, or attribution delay can make view A move while view B
  appears unchanged. Until that evidence exists at current `composition_generation` and
  `model_harness_cost_generation`, independence remains UNPROVEN and fails closed.
- Master already refuses the adjacent error: `config/provider_model_economics.v1.json` records for
  `minimax.minimax-m3` that the Token Plan "is governed by 5-hour rolling, weekly, billing-cycle token allocation
  and concurrency resources", and `tests/test_provider_model_economics.py:91`
  (`test_subscription_burn_method_is_declared_without_quota_balances`) pins that the catalog declares a burn
  *method* without carrying balances.
- The plan's `capability_generation` itself is **UNKNOWN** at this pin (§9).
- **OBSERVED INVENTORY, not enrollment and not authorization:** the installed MiniMax wrapper pins
  **MiniMax-M2.7**, not M3; the installed Alibaba wrapper pins **qwen3.8-max** with no flash/plus/max cohort
  split yet. Counts such as "7/7 minimax idle" or "6/6 bailian" are execution lanes, not entitlement wallets. No
  wrapper change is authorized here.

### 5.4 Alibaba Team — seat → member ceiling → packs by nearest expiry
```
E_alibaba[seat] = ALL_OF(
    BUDGET  ORDERED_SPILL(
                seat_monthly[seat],
                ALL_OF(
                    CEILING member_shared_pack_cap[seat] over the spill below,
                    BUDGET  ORDERED_SPILL(pack_nearest_expiry, pack_next_expiry, ...)
                            { stage_routing: UNKNOWN }
                )
            ) { stage_routing: UNKNOWN }
)
```
This is R35 §2's expression written with the §3.2 roles made explicit. The member cap is a CEILING over the
shared-pack subexpression — it meters the draw routed through the packs and holds no value of its own. §10 works
it numerically.

`stage_routing: UNKNOWN`. Official Team docs prove the deduction order — seat first, then shared packs nearest
expiry first — and the per-member shared-pack ceiling. They do **not** prove that one request can straddle seat
and pack. Until that routing is provider-declared or established by an authorized real observation, this
expression fails closed under §4.6.

**Everything about our actual enrollment here is UNKNOWN**: `stage_routing` (PARTITIONED versus
ATOMIC_FALLBACK), the Team seat tier (Alibaba documents 25k / 100k / 250k Credits per seat per subscription
month and 625k per shared pack, but which we hold is not evidenced at master), seat realm binding, subscription
`capability_generation`, how many packs exist, their identities/expiries, and the member cap value. Official
docs prove order and the member ceiling, not straddling. Master models **Personal**, not Team (§9). Do not
rename the profile to close this gap — R35 §16: bind the actual enrolled Team facts through Provider Control.

### 5.5 Claude / Fable subset ceiling — a ceiling, not a second wallet
```
E_claude[account] = ALL_OF(
    BUDGET  shared_parent_weekly[account],
    CEILING fable_subset_weekly[account] over the Fable-family portion
)
```
Anthropic caps eligible-plan Fable usage at a percentage **inside** the shared weekly allowance — one allowance
with a sublimit, not two wallets (R14). Therefore:

- `avail(Fable-family work) = min( usable(shared_parent_weekly), remaining(fable_subset_weekly) )`.
- Fresh shared-weekly telemetry with a missing or stale sublimit remainder leaves the expression **UNKNOWN**, not
  equal to the shared weekly. Shared telemetry alone must never make Fable `capacity_known` (R14 addendum).
- The same structure is the general answer to failure class 2 on the Claude side: several usage bars over one
  entitlement.

---

## 6. Usable value, holds, reserves, concurrency

### 6.1 usable
Every allocation binds the **exact observation identity/digest** it was computed against. Per R35 §10, for each
leaf:
```
usable_r = observed_remaining_r
         - unreflected_holds_r        # §8, own claims not yet covered by this observation
         - known_unobserved_debits_r  # known actual debit awaiting a covering observation
         - hard_reserve_r             # policy floor
         - soft_reserve_r             # scarcity reserve derived from the READY graph (advisory, later step)
         - uncertainty_margin_r       # observation-freshness and accounting-lag margin
```
`usable_r` is clamped at zero and is never negative-signalled as debt.

A hold is **reflected** once a covering observation exists — same `resource_generation`, `observed_at` at or
after the debit's effective time plus the provider's declared accounting-lag budget, and compatible observation
identity/digest semantics. A reflected hold is never subtracted twice. If an actual debit is KNOWN but the
observation is older, it is retained/transformed as an unobserved debit until a covering observation arrives.
If reflectedness cannot be decided, accounting lag and ambiguity stay conservative and the hold counts as
unreflected — never zero.

### 6.2 Reserve with a conservative cost
Reservations use the q95 estimator (or reviewed policy quantile), never the cohort mean; failed work stays in the cost
of reaching an accepted result; ambiguous shared-consumption attribution is rejected rather than learned from
(R35 §11, failure class 16). A candidate without comparable evidence stays in SHADOW/CANARY rather than receiving
production placement.

Cohort keys bind provider **SURFACE** + `model_harness_cost_generation` + harness. Go/M3 evidence is not
direct-M3 evidence, and the two may never be pooled into one estimate (matrix classes 15 and 35).

### 6.3 Concurrency is an observed dynamic resource
Marketing concurrency values are not scheduler truth (R35 §7). Provider Control owns: observed concurrency
availability, provider cooling/throttle state, last successful parallelism, freshness, and dynamic safety
evidence. Suggested parallelism is an **output** of Capacity (§4.3), not static plan metadata.

- A concurrency reduction or a 429/cooling signal **reduces new starts** and must never move work that has
  already STARTed (failure classes 10, 11), and must never be reported as a credential failure.
- Learned safe parallelism is keyed to `capability_generation` + `realm_binding_generation` (§2.2) and the relevant
  provider scope, so either axis changing resets it conservatively rather than inheriting a stale number.
- Master already carries the shape of the guard on the consumer side:
`control_plane/capacity_economics_projection.py:175` refuses a preview whose `suggested_parallelism` exceeds
`estimated_startable_jobs`.

### 6.4 Time-bound capacity overlays
A provider campaign is modeled as a time / surface / model-qualified **resource-and-debit overlay**, never as a
resource. The current provider campaign facts — not Mastermind enrollment facts — are: GLM-5.3-Flash, 3–20
September 2026, daily 23:00–09:00 Singapore time, on ZCode >= 3.10; Flash consumes zero plan quota on that
surface; other supported Agents get plan quota doubled; GLM-5.3 debits normally; and the campaign is unavailable
once the ordinary 5-hour / weekly limit is already hit.

An overlay carries `effective_from`, `effective_until`, its daily window, the exact supported surface (product
and minimum version), model qualification, a campaign generation/digest, and a HARD expiry. The underlying
entitlement and `resource_generation` are unchanged; an overlay never mints, forks, or replaces a resource.

- "Zero quota consumption" never means numeric infinity. For the exact admitted surface and window, the ordinary
  Flash usage-budget resource is NON-BINDING. READY demand, dynamic concurrency, and policy/quality/host
  constraints still bound starts, so `jobs_fit` remains finite and is still computed.
- "Doubled quota" is a temporary LIMIT overlay, never a second wallet, and never survives the window.
- An overlay is consumed through the existing provider-offer / economics / Provider-Control fact path. It does
  not authorize a promotion scheduler or promotions catalog.
- A promotion change invalidates the advisory plan digest.
- A surface mismatch (wrong product or version below minimum) or a clock outside the window means the overlay
  does not apply; ordinary resource rules bind, fail-closed under §4.6 if surface or window cannot be established.

Harvesting Flash on supported tools before 20 September is genuinely valuable, but it is not permission to arm
autonomous routing or invent work.

---

## 7. Execution-mode classification — a first-class hard gate

A technically reachable subscription is not autonomous Fabric capacity (R35 §6).

### 7.1 The enum
```
PROVIDER_USAGE_MODE :=
    SUPPORTED_TOOL_INTERACTIVE     # a human is driving a provider-supported tool
  | SUPPORTED_TOOL_AGENT_SESSION   # a provider-supported agent session, human-initiated and attended
  | UNATTENDED_BACKGROUND          # our Fabric starting work with no attending human
  | APPLICATION_BACKEND            # serving an application/product backend
  | CODING_AGENT_API               # bounded coding-agent request/result use with stable sessions
  | PROVIDER_USAGE_MODE_UNKNOWN    # the policy owner cannot prove the mode is admitted
```
The vocabulary is offered for freezing at review (R35 §6: "The exact vocabulary can be frozen during contract
review").

`CODING_AGENT_API` is admitted only for coding-agent request/result consumption with stable sessions (including
the expected coding-agent user agent and stable `x-opencode-session`). It is **not** scraping, extraction,
dataset generation, or multi-account pooling. Its admission is per surface, exactly as every other mode is.

### 7.2 The gate
At admission, a job's **requested mode** must intersect the **plan policy's admitted modes for this exact
harness**, resolved through the existing policy owners at the current `capability_generation`.

- If the policy owner cannot prove our invocation mode is admitted → `PROVIDER_USAGE_MODE_UNKNOWN` → the
  subscription is **unavailable for that operation**, regardless of how much quota it shows (failure class 12).
- This is a refusal of the *operation*, not a write-off of the subscription. The same capacity may be used
  aggressively for provider-compliant supported-tool workflows while another execution mode uses PAYG or another
  lawful provider.
- "Supports agent tools" must never be reinterpreted as "all unattended automation is allowed."
- Execution mode is a dimension of the capacity quantity itself, not metadata beside one number. One entitlement
  can expose zero `UNATTENDED_BACKGROUND` capacity and simultaneously positive
  `SUPPORTED_TOOL_INTERACTIVE` capacity. `avail`, `jobs_fit`, and `usable` are evaluated per admitted execution
  mode, and a value computed for one mode may never be read as capacity for another.
- Capacity ranks only within the job's admitted execution mode (Sol R51, verbatim). A candidate whose admitted
  modes do not include the requested mode is excluded by this hard gate before economics sees it (§11.1 step 1);
  economics never compares across modes. **Read "ranks" exactly as R51 means it**: Capacity orders its own
  economic *evidence*, scoped to one admitted mode, and emits it as a typed preference. It does not rank
  candidates for selection and does not choose among them — §11.1's no-second-selector rule governs, and the
  one selector remains `select_placement`.

### 7.3 Binding precedent to fold in
R13 (MiniMax headless ruling) is normative here and is restated so the contract carries it: **`claude -p` one-act
headless runs are UNATTENDED execution** for Mastermind policy unless a current provider-policy receipt
explicitly admits that exact mode under the plan. "Attended in causation" is insufficient. Kit headless runs are
engineering evidence, not governed capacity. An interactive canary never flips a flag (R18 (2)).
Reachability is not entitlement, and a working adapter is not a policy receipt. A technically reachable wrapper
must never be converted into autonomous capacity.

### 7.4 What master already encodes, and what is missing
`config/subscription_provider_profiles.v1.json` (schema `mastermind.subscription_provider_profiles/v1`) carries
three profiles, each with a boolean policy set — `glm-coding-plan` at line 5, `alibaba-token-plan-personal` at
line 33, `minimax-token-plan` at line 62; `autonomous_allowed: false` at lines 24, 52, 81; and a `usage_policy`
block with `interactive_only: true`, `unattended_background_allowed: false`,
`production_backend_allowed: false` at lines 28–30, 56–58 and 85–87.
`tests/test_subscription_provider_profiles.py:142` (`test_usage_policy_cannot_omit_or_weaken_baseline_fences`) and
`tests/test_subscription_provider_profiles.py:34`
(`test_purchased_subscription_profiles_are_not_eligible_for_unattended_production`) defend them.

The booleans are **conservative and correct, and must not be relaxed because the adapters work** (R35 §6). What
is missing is the *typed classification*: there is no `PROVIDER_USAGE_MODE` value, no per-harness resolution, and
no explicit `PROVIDER_USAGE_MODE_UNKNOWN` state distinct from `false`. The proposed enum replaces nothing — it
gives the existing booleans a typed, per-operation, per-harness reading with an explicit unknown.

---

## 8. Claim-time resource-bundle holds — and the one narrow amendment

R35 §14: two workers must not both observe 100 remaining units and each claim a 70-unit job. Preview is not
enough.

### 8.1 Required claim-time sequence
1. Revalidate every §2.2 generation axis and observation freshness (§2.2, §2.3).
2. Resolve the exact resource expression `E` for the chosen route.
3. Compute the conservative required native capacity per resource, by evaluating the debit partition of §3 for
   one operation using the per-resource `cost_r(c)` vector produced by `q95(c)` (the same partition §10 works
   numerically).
4. **Atomically reserve the internal resource bundle together with the existing Executive claim** — one
   transaction, not two.
5. Persist the capacity evidence/reasoning receipt with `JOB_CLAIMED`.
6. On completion: reconcile the actual provider debit through Provider Control; release the internal hold
   **once**; update outcome/cost evidence.
7. If provider accounting lags or the effect is uncertain (`EFFECT_UNKNOWN`), **do not reuse the held capacity**
   and do not economically fail over (failure class 18).

Steps 1, 4, and 7 also bind observation identity/digest and reflectedness: a reflected hold is not subtracted
twice, while an unreflected hold or known unobserved debit remains charged to `usable` (§6.1). A generation
rollover is evaluated before authorization: reconcile or conservatively carry every nonterminal old-generation
hold, or return BLOCKED (§2.2). A bump alone is not release.

### 8.2 What master's claim contract can express today — and what it cannot
Read at master@0fe8074f:

| Fact | Receipt |
|---|---|
| The sole atomic claim transaction | `control_plane/executive_runtime.py:11015` `def _claim_job_in_transaction(` |
| Its public entry | `control_plane/executive_runtime.py:11257` `def claim_job(` |
| The claim consumes ONE capacity row | `control_plane/executive_runtime.py:11020` `capacity: sqlite3.Row,` |
| That row's table | `control_plane/executive_runtime.py:1574` `CREATE TABLE worker_quota_classes (` |
| Its key is a worker slot, not a provider resource | `control_plane/executive_runtime.py:1593` `PRIMARY KEY(worker_id, quota_class),` |
| Its "hold" is a single-attempt exclusion | `control_plane/executive_runtime.py:1587` `held_attempt_id TEXT,` and `:1594` `UNIQUE(held_attempt_id),` |
| An Attempt carries one scalar quota class | `control_plane/executive_runtime.py:1659` `quota_class TEXT NOT NULL,` (table at `:1654`) |
| One live Attempt per Job | `control_plane/executive_runtime.py:1743` `CREATE UNIQUE INDEX one_lease_active_attempt_per_job` |
| The claim receipt | `control_plane/executive_runtime.py:11236` `event_type="JOB_CLAIMED",` with `payload=claim_payload` |
| **No provider-capacity hold ledger exists in the claim path** | scope stated precisely in §8.2.1 — there IS an inactive reservation-bundle design in the tree, for a different resource domain |

So the answer to R35 §14's conditional is: **the existing claim contract cannot express a resource-bundle hold.**
It reserves a *worker slot*, keyed `(worker_id, quota_class)` — a mutual-exclusion lease over one of our own
lifecycle objects. It never reserves a provider-native quantity, and `quota_class` is a scalar, so it cannot name
a bundle.

#### 8.2.1 Scope of that absence — there IS a reservation-bundle design in the tree, in another domain
An earlier draft of this document claimed flatly that "no resource-hold ledger exists". That claim was too broad
and is retracted here; independent review found the counter-evidence, and the corrected statement is narrower and
more useful.

`control_plane/executive_runtime.py:2248` defines `_PHYSICAL_RESOURCE_SCHEMA_CANDIDATE`, introduced by the
comment at `:2246` — *"Inactive candidate only: deliberately NOT a member of `_MIGRATIONS`. A separately reviewed
offline successor is required before any production installation."* It contains
`CREATE TABLE physical_resource_commitments (` (`:2250`) and `CREATE TABLE physical_resource_demands (` (`:2282`),
with the command family `reserve_physical` / `begin_physical` / `observe_physical` / `settle_physical` /
`physical_status` at `control_plane/executive_runtime.py:16594` onward, and it is exercised at
`tests/test_executive_os_sqlite.py:1852`. These receipts are read at the procedure pin
**a78b8fe23d8e1ed129880ac47e97ebe96afa8aea** in §8.3; they are not offered as code authorization to install the
inactive candidate.

Two conclusions, and they point the same way:

1. **It is a different resource domain and cannot be reused as-is.** Its demand rows are constrained to physical
   dimensions — `dimension TEXT NOT NULL CHECK(dimension IN ('memory_bytes','disk_bytes','cpu_us_per_window',
   'io_bytes_per_window','heavy_phase_count'))` at `control_plane/executive_runtime.py:2285` — which contains no
   provider-quota dimension, and it is keyed by `host_id`, not by a provider resource identity. It is also
   inactive, so nothing in the claim path reserves anything through it today. The narrow conclusion of §8.2
   therefore stands unchanged.
2. **It is nevertheless the right precedent, already reviewed in this codebase.** It carries exactly the
   properties §8.3 needs and that a naive "add a table" proposal would have missed: an allocation *generation*
   (`allocation_generation`), a fingerprinted **bundle** (`bundle_fingerprint`, `bundle_manifest_json`), a
   per-dimension charge (`remaining_charge`), event-id provenance, immutability and transition-guard triggers,
   permanent tombstones, and an effect-uncertain lifecycle
   (`state TEXT NOT NULL CHECK(state IN ('RESERVED','EFFECT_MAY_HAVE_BEGUN','ACTIVE','RECONCILIATION_REQUIRED',
   'SETTLED','ABANDONED_NO_EFFECT'))`, `control_plane/executive_runtime.py:2259`).

So A2 below is not "invent a holds table". The inactive candidate is the precedent **and the consolidation
target**; it is not a pattern to instantiate a second time as a parallel provider-quota plane.

### 8.3 The narrow amendment (proposed, to be reviewed as a separate act)
Before any implementation there must be **one canonical Executive resource-commitment primitive**, or an explicit
consolidation, so the physical and provider resource domains share **one lifecycle, one event plane, and one
settlement plane**. Two admissible routes exist and this contract chooses neither:

1. **Generalise the existing primitive.** The separately reviewed successor to
`_PHYSICAL_RESOURCE_SCHEMA_CANDIDATE` is installed as a resource-domain-generic commitment/demand primitive. Its
dimension CHECK at `control_plane/executive_runtime.py:2285@a78b8fe2` and its `host_id` keying are generalized to
a typed resource-domain key; provider-quota holds become demands inside it.
2. **Explicit consolidation.** A reviewed act declares one of the two domains canonical and migrates the other
onto it, with one lifecycle vocabulary, one event family, and one settlement path.

Either route is a separate reviewed act with its own owner. Until that primitive exists, step G
("atomic claim/hold") cannot open, and this contract authorises no second commitment plane in the meantime.

**Division of truth.** Provider Control remains quota truth: it owns observation, entitlement, cooling, deduction
policy, and the actual provider debit. Executive never becomes a quota database. Executive persists only:

1. internal holds against its own canonical commitment plane, and
2. exact source/generation/digest evidence — the source identity the observation came from, the §2.2 axes it was
   computed under, and the digest of its composition/debit evidence.

Executive does not store provider balances, does not recompute them, and settles only against Provider Control's
reconciliation.

The narrow amendment is therefore:

- **A1 — one required field on the claim receipt.** `JOB_CLAIMED`'s payload (written at
  `control_plane/executive_runtime.py:11236`) gains an immutable `capacity_hold` record: the evaluated expression
  identity and its digest; per-`resource_id` reserved native quantity; `resource_generation`; the immutable
  `composition_generation` and `model_harness_cost_generation` under which the debit partition was computed; the
  source identity; exact observation identity/digest and `observed_at`; reflectedness evidence; and every
  applicable generation axis.
- **A2 — canonical primitive rows.** Provider-quota holds are demands on the one canonical primitive selected
  above. A hold is keyed by `(resource_id, resource_generation)` and additionally records immutable
  `composition_generation` and `model_harness_cost_generation` evidence. Concurrent claims serialize on that
  primitive's rows. **The parallel provider-quota `RESERVED / COMMITTED / SETTLED` lifecycle proposed in the
  pre-R41 draft of this section is RETRACTED and does not exist in this contract**: it is not deferred, not
  optional, and not available to a later implementer — there is exactly one commitment lifecycle, and it is
  the canonical Executive primitive selected above (Sol R41 ruling 5). Before a new
  `resource_generation` authorizes, every nonterminal hold from the old generation is reconciled or carried
  forward conservatively; otherwise the resource remains BLOCKED.
- **A3 — settlement folds into the canonical primitive's settlement path.** It is not a separate release
  mechanism. Uncertain effect keeps the canonical hold in `RECONCILIATION_REQUIRED`, outstanding and unavailable
  for reuse, until Provider Control reconciles it (§8.1 step 7).

**A1 is not a new idea — it is the already-designed direction, unimplemented.** The CF2F claim-evidence work
already specifies a closed `JOB_CLAIMED.capacity_evidence` object:
`research/MASTERMIND_EXECUTIVE_CAPACITY_CF2F_CLAIM_EVIDENCE_AND_ACQUISITION_FREEZE_2026-08-25.md:735` (`## 8.
Closed `JOB_CLAIMED.capacity_evidence``) and `:738` ("evidence is one nested object in the existing `JOB_CLAIMED`
payload"). At this pin that object is **not implemented in the claim path**: `capacity_evidence` appears in the
tree only as operator reason codes (`control_plane/operator_continuity_projection.py:509`,
`:517`), never as a field written by `_claim_job_in_transaction`. A1 therefore asks the reviewer to confirm that
the resource-bundle hold rides the *already-designed* nested object rather than minting a parallel one.

No new service, no second lock, no quota microservice (R35 §14). `quota_class` semantics are untouched; the
bundle is additive. Whether the holds table is a new table or additional columns is an implementation choice for
the amendment's own review; the *contract* requirement is only that the hold is keyed by resource identity and
committed in the claim's transaction.

---

## 9. What is left untouched, and what master actually models

### 9.0 Binding to Provider Capacity V2
The graph is **not independently acquired capacity truth**. Exactly two admissible publication forms are
possible; the reviewer chooses one:
The preferred domain-explicit candidate remains
`mastermind.provider_capacity_resource_composition/v1`, UNFROZEN pending the repaired semantics.

1. **Embedded closed sub-contract.** The resource graph is a closed sub-contract inside Provider Capacity V2,
   acquired and published by V2's own producer, in V2's own snapshot, under V2's capability generation. There is
   no separate acquisition, producer, or snapshot.
2. **Cryptographically bound companion.** If published separately, every graph document carries an exact
   cryptographic binding to the V2 observation it derives from: the V2 snapshot digest, V2 producer identity
   (an entrypoint blob pin, in the way
   `ops/executive_os/capacity_source_contract.py:92@a78b8fe2` pins `ENTRYPOINT_GIT_BLOB` for V1), and V2
   capability generation. A graph whose binding does not resolve to exactly one V2 snapshot is **INADMISSIBLE**,
   not merely stale; that is what makes mixing it with another observation epoch impossible.

Family-B B4 already owns V2 `realm_binding`. This contract does not mint, redefine, or duplicate realm binding;
§2.1 composes with and consumes it. V1 remains an exact legacy compatibility projection, never a competing truth
plane. Strict `provider_capacity.v1` is neither extended nor edited in place (§9.1), and any V1 view of a
V2-acquired graph is an exact lossy projection for legacy consumers only.

### 9.1 Strict `provider_capacity.v1` is untouched
R35 §2: "Do NOT append this silently to strict `provider_capacity.v1`." This contract does not modify it, extend
it in place, or redefine any of its fields. It is a **new, separately versioned artifact** that composes with it.

There is also a mechanical reason the in-place edit is forbidden, receipted at this pin: the capacity producer is
a **Macro-side** artifact consumed through a hash-pinned source closure.
`ops/executive_os/capacity_source_contract.py:49` pins `"engine/provider_capacity.py"` and `:52` pins
`"scripts/build_provider_capacity.py"`; `:69` sets `ENTRYPOINT` to that same script;
`:92` pins `ENTRYPOINT_GIT_BLOB`. Editing the strict v1 producer in place invalidates that closure and the host
preparation receipts built on it (`tests/test_executive_capacity_source_contract.py:444`,
`tests/test_executive_capacity_host_preparation.py:178`).

### 9.2 Current-state receipts (master@0fe8074f)

| Thing | Status | Receipt |
|---|---|---|
| Capacity→economics bridge exists, advisory only | EXISTS | `control_plane/capacity_economics_projection.py:18` `QUOTA_PREVIEW_SCHEMA = "mastermind.quota_economics_preview/v1"`, `:19` `PROJECTION_SCHEMA = "mastermind.capacity_economics_projection/v1"` |
| `startable_jobs` is a **scalar consumed**, not composed | PARTIAL | `control_plane/capacity_economics_projection.py:83` `estimated_startable_jobs: int` — the projection validates and forwards an integer supplied by the preview; there is no resource set, so no composed evaluation can happen here today |
| Parallelism bounded by startable jobs | EXISTS | `control_plane/capacity_economics_projection.py:175` + `tests/test_capacity_economics_projection.py:90` |
| Economics may not promote a lower tier | EXISTS | `tests/test_capacity_economics_projection.py:53` `test_refuses_lower_tier_promotion` |
| Burn method is measured, not inferred | EXISTS | `control_plane/provider_model_economics.py:21` `_BURN_METHODS = {"measured_native_delta", ...}` |
| Model economics catalog is inert | EXISTS | `config/provider_model_economics.v1.json` — `"production_armed": false`, `"scope": "routing_models_only"`, schema `mastermind.provider_model_economics/v1` |
| Capacity facts are hermetic/canary-only | EXISTS | `ops/executive_os/capacity_owner_facts.py:44` refuses direct minting; `control_plane/model_router.py:1082` `export_capacity_owner_fact`, `:1108` `verify_capacity_owner_fact` |
| Realm receipts are hermetic | EXISTS | `ops/executive_os/provider_realm_facts.py:40` refuses direct issuance |
| Alibaba modelled as **Personal**, not Team | PARTIAL (product mismatch, R35 §16) | `config/subscription_provider_profiles.v1.json:33` `"alibaba-token-plan-personal"`; `config/provider_model_economics.v1.json` surface `alibaba_token_plan_personal` |
| No shared-pack / seat / member-ceiling model anywhere | MISSING | no `shared_pack`, `seat_monthly` or `member_*_cap` symbol in `config/`, `control_plane/`, `ops/` at this pin |
| Family-B joined identity not present as one construct | PARTIAL | `capacity_capability_id` appears once, at `ops/executive_os/capacity_broker_topology.py:205`; `realm_generation` lives in `control_plane/subscription_canary_admission.py:128`; `host_ref` exists only in `control_plane/executive_recovery_readiness.py:492` (recovery, not capacity). #662 is OPEN/DRAFT; B0 unaccepted |
| Resource-bundle hold | MISSING | §8.2 |
| Typed execution-mode enum | MISSING | §7.4 (booleans exist; classification does not) |

### 9.2.1 Current protected master and path-disjoint precedents
Protected master has moved to `8ba7deedde164c90298d3e88785d98e02fa5e2d2`. The documents' census anchor
`master@0fe8074f…` remains the commit at which their existing master `file:line` receipts were read; that census
pin is not re-anchored. Movement since the census is path-disjoint but capacity-adjacent: #682 (merged
`52bb6026`) binds fresh HP0 evidence to the existing physical-resource BEGIN boundary, and #683 (merged
`a78b8fe2`) adds a bounded read-only host-capacity snapshot. They are useful physical-resource precedents for
freshness, explicit unknowns, host/boot binding, and no implicit placement authority. They do **not** supply
provider-resource composition, provider holds, or any proposed provider-capacity acceptance class, and must not
be relabeled as provider-capacity proof.

### 9.3 UNKNOWN — written as UNKNOWN, per R35 §22 C ("Do not infer this from what we remember buying")
- **U1 — Alibaba `stage_routing`**: PARTITIONED versus ATOMIC_FALLBACK. **UNKNOWN.**
- **U2 — Alibaba Team-tier seat/pack facts**: seat tier, seat realm binding, subscription
  `capability_generation`, shared-pack identity/count/expiries, member shared-pack cap. **UNKNOWN.**
- **U3 — MiniMax**: plan `capability_generation`; whether per-model rows are independent resources.
  **UNKNOWN / UNPROVEN.**
- GLM: per-account entitlement generation and reset anchors as *Provider-Control* facts (the kit's numbers are
  local telemetry, not Provider Control receipts). **UNKNOWN.**
- Claude: Fable-family sublimit remaining per account. **UNKNOWN.**
- **U4 — Document placement**: `research/` while HOLD (R41 ruling 1) versus the earlier census recommendation of
  `docs/superpowers/specs/`. **UNKNOWN; Sol's call at release.**
- **U5 — OpenCode Go enrollment/pool membership**: whether even one Go account is enrolled, and whether any
  multi-member use is policy-eligible. The schedulable entitlement count remains **1 proven-at-most; actual
  enrollment UNKNOWN** (§5.2).
- Every provider: whether our exact autonomous invocation mode is policy-admitted. **PROVIDER_USAGE_MODE_UNKNOWN**
  until a current policy receipt says otherwise.

Provider privacy and retention labels are **DATED OBSERVATIONS, not standing guarantees**. For example, the
DeepSeek V4 Flash zero-data-retention label was stated only through 31 August 2026 and is therefore **STALE /
UNKNOWN** now. A label past its observation date fails closed like any other stale observation (§2.3; B4's typed
STALE; matrix class 36).

---

## 10. Worked numeric example — ORDERED_SPILL debits exactly once, and blind `min()` is wrong

This whole example is **GENERIC and ILLUSTRATIVE**. It assumes `stage_routing = PARTITIONED`
**HYPOTHETICALLY** to exercise the operator, not as an enrolled Alibaba behaviour fact (§5.4, §9.3 U1). All
quantities are likewise illustrative and assert no enrollment.

### 10.1 State
One **hypothetical** Alibaba Team seat `S1`, expression as §5.4 but with `stage_routing` assumed
`PARTITIONED` for the exercise:

| Resource | Role | Observed remaining |
|---|---|---|
| `seat_monthly[S1]` | spill stage 1 | 3,000 Credits |
| `member_shared_pack_cap[S1]` | CEILING over the pack spill | 40,000 Credits of cumulative draw remaining |
| `pack_A` (expires 2026-09-30, nearest) | spill stage 2a | 25,000 Credits |
| `pack_B` (expires 2026-10-31) | spill stage 2b | 600,000 Credits |
| `alibaba_dynamic_concurrency` | observed | safe parallelism 3 |

Cohort `c`: `q95(c) = 10,000` Credits per accepted job.

### 10.2 Evaluation (§4.1, bottom-up)
```
avail(ORDERED_SPILL(pack_A, pack_B))            = 25,000 + 600,000 = 625,000
avail(ALL_OF(CEILING member_cap, that spill))   = min(40,000, 625,000) = 40,000
avail(ORDERED_SPILL(seat_monthly, that ALL_OF)) = 3,000 + 40,000 = 43,000
startable_jobs(c)                               = floor(43,000 / 10,000) = 4
safe_parallelism(c)                             = min(3, 4) = 3
```

### 10.3 The debit walk — exactly once, across seat → pack_A → pack_B, under the ceiling
This is the hypothetical PARTITIONED walk.

| Job | Cost | seat_monthly | pack_A | pack_B | member_cap drawn (cumulative) | Partition sums to cost? |
|---|---|---|---|---|---|---|
| — | — | 3,000 | 25,000 | 600,000 | 0 / 40,000 | — |
| 1 | 10,000 | 3,000 → **0** | 25,000 → 18,000 | 600,000 | 7,000 | 3,000 + 7,000 = 10,000 ✓ |
| 2 | 10,000 | 0 | 18,000 → 8,000 | 600,000 | 17,000 | 10,000 = 10,000 ✓ |
| 3 | 10,000 | 0 | 8,000 → **0** | 600,000 → 598,000 | 27,000 | 8,000 + 2,000 = 10,000 ✓ |
| 4 | 10,000 | 0 | 0 | 598,000 → 588,000 | 37,000 | 10,000 = 10,000 ✓ |
| 5 | 10,000 | — | — | — | ceiling remaining 3,000 | **refused** — 3,000 < 10,000 |

Exactly-once check: total value removed from value-bearing resources
= `3,000 (seat) + 25,000 (pack_A) + 12,000 (pack_B) = 40,000` = `4 × 10,000`. The member cap shows 37,000 drawn —
which is the **same** 37,000 Credits that left the packs, *metered*, not an additional 37,000 removed. A CEILING
never adds to and never subtracts from total value; that is what §3.2 buys.

Job 3 is the case a flat model cannot represent: one job straddles the `pack_A → pack_B` boundary, debiting
8,000 + 2,000. Nearest-expiry order (failure class 5) is what sends the 8,000 to `pack_A`; reversing the order
would strand `pack_A` at expiry while `pack_B` still had 10 months of life.

Job 5 is failure class 4 in miniature: 588,000 Credits sit in `pack_B`, and this seat's effective capacity is
nevertheless exhausted at 3,000 because of the member ceiling.

### 10.4 The same state under ATOMIC_FALLBACK
Under ATOMIC_FALLBACK, per-stage whole jobs: the seat holds `floor(3,000 / 10,000) = 0`; the pack subtree holds
`min(floor(25,000 / 10,000) + floor(600,000 / 10,000), floor(40,000 / 10,000)) = min(62, 4) = 4`. Total
`startable_jobs = 0 + 4 = 4`, the same count as PARTITIONED — but the debit walk differs (no job straddles; each
job is served wholly from one stage), and the stranding report differs: ATOMIC_FALLBACK strands 3,000
`stranded_at_stage` at the seat and 5,000 `stranded_at_stage` at pack_A, where PARTITIONED strands 3,000
`stranded_at_ceiling`. A matching startable count is **not evidence of routing**; that is exactly why
`stage_routing` must be provider-DECLARED and never inferred from a number that agrees.

### 10.5 The counter-example — what blind `min()` gets wrong
Flatten the tree to its leaves and take `min` of per-leaf `floor(usable / q95)`, as R35 §10's simple conjunctive
formula would if applied without the algebra:

```
floor(  3,000 / 10,000) = 0      # seat_monthly
floor( 40,000 / 10,000) = 4      # member_cap
floor( 25,000 / 10,000) = 2      # pack_A
floor(600,000 / 10,000) = 60     # pack_B
blind min  = 0 startable jobs
true value = 4 startable jobs
```

**Blind `min()` reports zero capacity for a route that can lawfully run four jobs.** The mechanism is precise: it
treats an exhausted `ORDERED_SPILL` *stage* as a hard constraint of zero, when an exhausted first stage is not a
constraint at all — it is a transition. In production this is not a rounding error; it is the exact failure mode
R35 §24 names as the metric, *avoidable prepaid stranding*: 43,000 Credits of purchased, in-date, lawful capacity
reported as unusable, with the work spilling to a scarcer or cash-billed route.

The mirror error is equally available and worse. Flatten by **summing** every leaf:
```
(3,000 + 40,000 + 25,000 + 600,000) / 10,000 = 66 startable jobs   # vs. a true 4
```
That is a 16.5× capacity fiction, produced by double-counting the CEILING as value and ignoring it as a bound.

### 10.6 Nested atomic fallback — the scalar-avail error
The recursive rule is not cosmetic. Let a shared BUDGET have 100 units, an `ATOMIC_FALLBACK` spill have two
stages of 60 and 60 units, and each whole job cost 50 units. A scalar root formula would answer
`floor(min(100, max(60, 60)) / 50) = 1`, but two whole jobs can actually run — one per stage — while respecting
the shared budget:

```
jobs_fit(stage_1) = floor(60 / 50) = 1
jobs_fit(stage_2) = floor(60 / 50) = 1
jobs_fit(ALL_OF)  = min(floor(100 / 50), 1 + 1)
                  = min(2, 2) = 2
```

The shared BUDGET constrains the aggregate; the stage sum proves whole-job feasibility per stage. Neither number
alone carries the answer.

### 10.7 Generation rollover — a bump is not release
Resource R is at generation n with `observed_remaining = 100` and one nonterminal hold of 70 keyed `(R, n)`. The
generation bumps to n+1 while `observed_remaining` is again 100. A naive generation-keyed join stops matching
the old hold and authorizes another 70-unit job, committing `70 + 70 = 140` against 100.

The lawful outcomes are exactly two: BLOCK the new generation until reconciliation is complete, or conservatively
carry/map the hold forward so `usable = 100 − 70 = 30`. The rollover never releases the hold, never treats the
old observation as proof of settlement, and never authorizes capacity from ambiguity.

Two further blind-`min()` errors the algebra also removes:
- **Concurrency folded into the min.** Adding `concurrency = 3` as a fifth term would give `min(…, 3)` and
  answer "3 jobs before exhaustion". Concurrency bounds simultaneity, not total count (§4.3); the correct outputs
  are `startable_jobs = 4` and `safe_parallelism = 3`, which are different numbers with different uses.
- **Meters summed as wallets.** Applying the sum-flattening to GLM's `ALL_OF(5h, weekly)` yields
  `28,000 + 140,000 = 168,000` Credits of "capacity" from a plan that can spend at most 140,000 in the week and
  28,000 in any 5-hour window — failure class 2, arrived at by arithmetic rather than by a bad observation.

---

## 11. Where this sits in the lexicographic order

Unchanged from #671 (R35 §9): hard gates first, then Model Router's first lawful tier, then Stage A deadlines →
B unauthorised spend → C scarcity preservation → D repair-adjusted cost → E prepaid stranding → F latency /
continuity → G static provider preference as tie-break only. Economics must never promote a model out of a lower
suitability tier.

This contract contributes to exactly three places and nowhere else:
- the **hard gates** gain §7's execution-mode intersection (and `PROVIDER_USAGE_MODE_UNKNOWN` refuses),
- **Stage C and Stage E** gain truthful inputs, because scarcity and stranding are computed from `avail` over the
  real tree rather than from a flattened percentage,
- the **claim** gains §8's bundle hold.

There is no new stage, no new score, and no `capacity_score` scalar.

### 11.1 Composition with the existing CAP-C1 placement seam
Mastermind #657 (head `bc89980c7e06e81a883da8078660d3bf208e68eb`, OPEN, "feat(capacity): resolve exact
placement ties with source-owned preference") is the **incumbent candidate seam**. It adds
`mastermind.executive_placement_selection.v2` additively and mints
`mastermind.capacity_placement_preference.v1` only for an exact V1 `TIE_ABSTAINED` result. Its receipt binds
`responsibility_ref`, V1 selection-input digest, tied worker set/order, a Capacity-owned CURRENT source ref, and
a preference generation. V2 validates the winner against V1 evidence and keeps
`selection_is_commitment = false`. #657 is BUILT_NOT_PROVEN / REPAIR_REQUIRED (old base, hosted test failed at
head, no independent review) and resumes/repairs on its own incumbent branch after this PR's Step-A freeze. Do
not invent a new tie/preference contract here or reimplement it in #688/#7116.

C1 already owns the tie/preference seam. `control_plane/executive_placement_selection.py:39-44@a78b8fe2` records
Sol addendum (A): C1 has no tie-breaker authority; an exact top tie among eligible candidates always abstains
(`TIE_ABSTAINED`); `select_placement` refuses any non-`None` `accepted_tie_breaker`; and `tie_breaker_used` is a
reserved wire slot for a later typed, source-owned ruling receipt. `_CAPACITY_RANK` is narrower still:
`control_plane/executive_placement_selection.py:159-164@a78b8fe2` ranks eligible candidates by `capacity_state`
only (`AVAILABLE` before `DEGRADED`), and its source comment says nothing else — observation recency,
account-label text, or title — ever breaks a tie. The reserved-slot guards are enforced at
`control_plane/executive_placement_selection.py:790@a78b8fe2`,
`:1186@a78b8fe2`, and `:1637@a78b8fe2`.

The normative order is exactly this:

1. **Model Router's first lawful suitability tier and hard gates**, including §7's execution-mode intersection,
   review independence, and every existing C1 exclusion gate. Economics never promotes a model out of a lower
   suitability tier and never compares candidates across execution modes.
2. **Capacity economics preference/evidence**, as the lexicographic Stages A–G above. This produces a typed
   preference with its evidence; it never produces a selection.
3. **#657's own tie/abstention preference seam — the incumbent, not a lookalike.** It stays generic and
   binds responsibility, exact V1 selection-input digest, tied worker set/order, current source ref, and
   preference generation; where the evidence does not discriminate it abstains rather than breaking the tie. Provider
   entitlement/resource/model/rate epochs do not belong in that receipt; they live in the exact, content-addressed
   Capacity SOURCE artifact referencing Provider Capacity V2, the resource graph, and economics output.
4. **Ordinary C2 / Executive commitment**, namely §8's atomic claim, unchanged.

There is **no second selector**. Capacity does not rank candidates, does not choose among them, and implements no
placement function. The one selector is `select_placement`.

Economics must not smuggle preference through back channels:

- **`capacity_state`** — economics may never set or influence AVAILABLE/DEGRADED to move a candidate up
  `_CAPACITY_RANK`; source-owned health/observation is not an economics dial.
- **Account or file order** — the order accounts appear in a config, directory listing, ledger, or pool listing is
  never a preference signal.
- **Candidate ordering** — the order candidates are supplied to `select_placement` is never a preference signal;
  the source comment already forbids recency, label text, and title.

For §5.1 sibling GLM accounts, choosing among proven lawful accounts is therefore **placement**: C1's decision
reached by the order above. This contract supplies only economics evidence. Where evidence does not discriminate,
the lawful outcome is C1's abstention — not a Capacity tie-break.

CF2-I is the downstream integration/adoption owner. Its chain is: hard gates → first lawful Model Router tier →
Capacity supplies typed economics **evidence** over the concrete C1 candidate set inside that tier → #657's
exact tie/abstention seam consumes that evidence → Executive atomically claims one Worker. **Capacity never
ranks candidates and never chooses among them**, here or anywhere else in this document; any sentence
that reads as if it does is the second selector this contract forbids, and is to be read against the
rule above. Economics must ultimately
output concrete WORKER IDs through existing Worker / Runtime / Model-Router facts; WorkerRegistry/quota metadata
(model alias, provider alias, routing policy/profile/capability digests) is the lawful router-alias-to-worker
join. Never mint a capacity-worker-selector, second model-to-worker registry, or provider scheduler, and never
reorder `preferred_model_aliases` on economics grounds. RF1 compatibility receipts are
`docs/EXECUTIVE_WORKER_ROUTING.md:74@8ba7deed` ("### RF1 — provider-neutral suitability tiers") and
`docs/EXECUTIVE_WORKER_ROUTING.md:95@8ba7deed` ("preferred_model_aliases ... projects *only the first tier*").

End state, stated once: **Model Router first lawful tier → concrete C1 Worker candidates → Capacity
resource/economics evidence → #657's exact tie/abstention preference seam → CF2-I → C2 / Executive atomic
resource+worker commitment → existing broker/adapter.**

Two properties of that chain are normative. **No second selector**: every link is an existing owner, and a new
one may not be introduced to carry preference. **No dead producer**: the Capacity evidence the seam consumes
must be an existing, exact/content-addressed producer resolvable at the seam's own head — a preference receipt
naming a producer that does not resolve there is **INADMISSIBLE**, not merely stale, and the lawful outcome is
C1's abstention. Current states, so the chain is not read as built: **#657** OPEN, BUILT_NOT_PROVEN /
REPAIR_REQUIRED at `bc89980c`; **CF2-I** UNBUILT, a named integration/adoption owner rather than merged code,
whose RF1 receipts are read-only at `8ba7deed`; **C2 / Executive atomic commitment** UNBUILT, because §8.3's
one canonical primitive has not been chosen. Three of the chain's six links therefore do not exist yet, which
is exactly why this document freezes semantics and starts nothing.

**Placement authority for account pools is the #688 resource graph → the #657 candidate-preference seam → the
CF2-I consumer / C2 commitment; Macro #7142 is a subordinate candidate-selection kernel and never a second
capacity or account owner.** Protected #622 retains the pooled transport (source-protected `25ea63b7`), but
admission carries the §5.2 policy gate. Macro #7142 remains production-inert and must gain that gate; its
`build_snapshot()` carries no policy field, and legitimacy may never be inferred from a caller-supplied member
count.

---

## 12. Declared departures and refinements from the verbatim ruling

R35 is the frozen requirement. Three refinements were declared for review. Sol R41 has now ruled on them:
D1 APPROVED, D2 APPROVED only per proven distinct entitlement/account resource, and D3 APPROVED with the §2.2
generation-axis correction.

### D1 — Concurrency is an output, not a term inside `startable_jobs`
- **Ruling text (§10)**: *"`startable_jobs(c) = minimum jobs_fit across every conjunctive resource, plus the
  current concurrency limit.`"*
- **This document (§4.3)**: `startable_jobs` counts jobs before exhaustion and excludes concurrency;
  `safe_parallelism = min(observed_safe_concurrency, startable_jobs)` is published as a second output.
- **Why**: a concurrency of 3 does not mean only 3 jobs may be started before the next reset. Folding it into the
  same `min` conflates a simultaneity bound with a depletion count and understates throughput by the ratio of
  total work to parallel work. The ruling's own §7 supports the split — *"Suggested parallelism is an output of
  Capacity"* — so this reads as making the "plus" explicit rather than contradicting it.
- **Live obligation**: every consumer of the preview must be told which of the two numbers it is reading:
  `startable_jobs` is the depletion count (how many jobs fit before exhaustion), and `safe_parallelism` is a
  separate simultaneity bound. Master's existing consumer already carries both notions separately
  (`control_plane/capacity_economics_projection.py:83` `estimated_startable_jobs` and the parallelism bound at
  `:175`), and any presentation that merges them back into one number is defective.

### D2 — OpenCode Go is one proven-at-most entitlement, not a shared set or credential pool
- **Ruling text (§2)**: *"OpenCode Go: `ALL_OF(go_shared_5h, go_shared_weekly, go_shared_monthly,
  go_concurrency)`"* — singular.
- **This document (§5.2)**: exactly that singular entitlement shape, with **1 proven-at-most schedulable
  entitlement** and actual enrollment UNKNOWN.
- **Why**: Go's terms prohibit multiple accounts used to circumvent limits, and its documentation says one member
  per workspace may subscribe. Multi-account pooling is HELD pending `pool_membership_policy_eligible = true`
  from Provider Control.
- **Sol rulings**: R41 approved distinctness only as a generic D2 limit; R55 supplies the narrower Go-specific
  answer. Multiple sessions, hosts, dashboards, model views, keys, or logins never multiply the entitlement.
- **Superseded draft**: the prior text treating three Go accounts as three sibling expressions is withdrawn.

### D3 — Generation and observation freshness are two clocks
- **Ruling text**: §3 lists generation-invalidating events; §15 separately says a reset makes an observation
  stale and must not manufacture capacity.
- **This document (§2.2–§2.3)**: makes the separation explicit — the generation axes govern joins, bindings and
  calibration, freshness governs usability of a number, and a reset moves only the second.
- **Why**: the ruling implies the distinction but does not name it, and conflating them produces both of the bad
  outcomes it warns about — a reset treated as a new generation discards valid calibration, while a generation
  change treated as mere staleness keeps joining across an epoch boundary.
- **Sol ruling**: APPROVED ONLY with the epoch correction of §2.2. Ordinary reset/renewal moves FRESHNESS, never
  the resource epoch.

Two further constructs are additions rather than departures, and are flagged so the review does not mistake them
for ruling text: the **BUDGET / CEILING child roles** (§3.2) and the **stage-routing declaration** with its
partitionability precondition (§3.3). The ruling's §2 says *"The invariant is more important than the syntax"*
and names the invariant as knowing *"whether provider resources are simultaneously depleted, shared, nested
ceilings, or ordered overflow"* — these two constructs are this document's proposal for how to carry that
invariant. If Sol prefers a different syntax for the same invariant, nothing else in this contract changes.

---

## 13. Release condition

This document is a PROPOSAL and is HOLD-FOR-SOL. Its release condition is a Sol architecture review of
**(a)** the contract shape — the two child roles, the partitionability precondition, the evaluation rules of §4,
the generation axes/freshness rules of §2.2–§2.3, typed evaluation and recursive `jobs_fit`, per-resource units,
hold reflectedness and generation rollover, execution-mode dimensions, time-bound overlays, and the claim
amendment of §8.3 — and **(b)** the still-UNFROZEN schema name/version and its Provider Capacity V2
embedding-or-binding decision (§9.0). It stays in `research/` while
HOLD and is not promoted to `docs/superpowers/specs/`, protected source-law, or any spec location merely to look
final. The earlier census recommendation of `docs/superpowers/specs/` is superseded for now; final placement is
Sol's call at release (§9.3 U4). The seat does not release it.

Companion documents in this proposal:
- `research/MASTERMIND_EXECUTIVE_CAPACITY_COMPOSITION_ADVERSARIAL_ACCEPTANCE_MATRIX_2026-09-16.md` — the 20
  R35-minimum failure classes plus the additional classes required by formal review 5220216985 and its addendum,
  mapped to tests, owners, fixtures and current status at this pin.
- `research/MASTERMIND_EXECUTIVE_CAPACITY_COMPOSITION_CRITICAL_PATH_MAP_2026-09-16.md` — steps A–H with custody.
