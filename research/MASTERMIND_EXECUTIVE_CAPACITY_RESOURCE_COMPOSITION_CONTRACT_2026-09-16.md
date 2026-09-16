# Provider-native resource-composition and execution-mode contract — PROPOSAL

STATUS: PROPOSAL — HOLD-FOR-SOL
Census anchor: master@0fe8074ff953b2ced9025ed40f0f66019c759967 (every `file:line` in this document was read at
that commit; nothing here was asserted from memory).
Authority: Sol capacity-routing architecture ruling relayed 2026-09-16T06:52:49Z, consumed as R35. This document
discharges **step A only** ("Freeze resource-composition + execution-mode semantics").
Proposed schema name/version (subject to the architecture review that is this document's release condition):
`mastermind.provider_resource_composition/v1`.
Owner: the existing Shared AI Provider Control / Capacity authority. **No new owner is proposed.**

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
| A balancer or router | Model Router owns suitability; Capacity owns economic placement inside the first lawful tier. Unchanged. |
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

**Composition with Family-B.** Family-B (Mastermind #662 / Macro #7162) introduces `capacity_capability_id` as
the logical quota domain and `host_ref + capacity_capability_id + realm_generation` as the executable local realm
(R15). Resource identity is minted **inside** that namespace, not beside it:

> `resource_id := (capacity_capability_id, resource_key)` — where `resource_key` is a provider-scoped name for
> the specific bucket (`plan_5h`, `plan_weekly`, `seat_monthly`, `shared_pack:<pack_generation>`,
> `member_pack_cap`, `concurrency`).

The consequence is the point of the whole exercise: **two `host_ref`s that resolve to the same
`capacity_capability_id` resolve to the same `resource_id`, and therefore to one set of numbers.** Host replicas
cannot multiply capacity by construction, not by a downstream check (failure class 1).

Family-B is composed with, not overloaded. Family-B answers *which logical domain and which executable realm*.
This contract answers *how the buckets inside that domain deplete relative to one another*. Family-B's own
architecture explicitly does not solve nested resource algebra (R35 §21); nothing here is appended to it
silently, and nothing here should be read as accepting Family-B B0 (still unaccepted — R19 (6)).

### 2.2 Generation
Every resource carries a `generation`. It is an identity epoch, not a clock. Changing it invalidates joins and
calibration; historical receipts stay immutable and new claims use only the current generation (R35 §3).

Generation-invalidating events (R35 §3 and §15, consolidated — this is the normative list):

| # | Event | Source of truth |
|---|---|---|
| G1 | Plan generation change (tier up/down, plan replacement) | Provider Control enrollment |
| G2 | Seat assignment / reassignment | Provider Control enrollment |
| G3 | Subscription renewal or re-purchase generation | Provider Control billing evidence |
| G4 | API-key or realm binding change (incl. key rotation) | Family-B realm owner |
| G5 | Provider model generation change (incl. a silent alias update) | Model catalog owner |
| G6 | Shared-pack generation (a new pack purchased, a pack retired) | Provider Control enrollment |
| G7 | Provider deduction-policy change (the tree's shape itself changes) | Provider Control policy evidence |
| G8 | Rate-card generation change | Model economics catalog owner |

### 2.3 Generation is not freshness — reset ≠ observed refill
Two clocks, deliberately separate, because conflating them is how a reset silently manufactures capacity
(R35 §15):

- **Generation** governs *joins and calibration*. It changes only on G1–G8.
- **Observation freshness** governs *usability of a number*. Every observation carries `observed_at` and the
  reset boundary it was taken before. **Crossing a reset boundary makes the observation STALE, not larger.**
  After a reset, a claim requiring that resource waits for a new provider observation; it does not assume the
  entitlement value.

The one exception is a **deterministic refill contract**: an explicitly reviewed, per-resource statement that the
post-reset value is a known function of entitlement. Absent that reviewed statement, post-reset value is UNKNOWN.
A plan upgrade, a shared-pack purchase, a reset card or a coupon likewise create a new generation or require
fresh observation — never a synthetic balance.

**Forecast is not observation.** A forecast of capacity available after the next reset may be published for
expiry/stranding reasoning (Stage E, §11) but must carry a distinct field name and must never be summed into, or
substituted for, observed remaining (failure class 20).

---

## 3. The expression language

A **resource expression** `E` describes how one provider-lawful route's capacity depletes. Grammar:

```
E        := LEAF | ALL_OF(child, child, ...) | ORDERED_SPILL(stage, stage, ...)
child    := { role: BUDGET | CEILING, expr: E }
stage    := E
LEAF     := { resource_id, native_unit, generation, observation }
```

### 3.1 LEAF
A leaf names one resource, its provider-native unit (Credits, provider quota units, requests, …), its generation,
and its current observation (`observed_remaining`, `observed_at`, `next_reset_at`, `freshness`). Native units are
never compared across providers (R35 §10); comparison happens only after §6 converts headroom into job
equivalents.

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

One operation's cost may straddle a stage boundary: if `s1` has 3,000 units remaining and the operation costs
10,000, the operation debits 3,000 from `s1` and 7,000 from `s2`. The partition sums to exactly the cost — never
10,000 from each (failure class 3).

**Partitionability precondition (normative).** `ORDERED_SPILL` is lawful **only** where the provider actually
partitions a single operation across the stages. If a single operation must be served wholly by one stage, that
is not spill — it is **placement among sibling routes**, which is already owned by Capacity/Model Router and must
never be written as a resource operator.

This precondition is not pedantry; it is the difference between a true capacity number and a fiction. Three GLM
Coding Plan Max accounts encoded as `ORDERED_SPILL` would evaluate to the *sum* of their 5-hour pools and would
authorise a job whose cost exceeds any single account's remainder — a job that cannot actually run anywhere
(§5.1).

### 3.4 What the language deliberately cannot express
There is no `ANY_OF` / alternation operator. Choosing among lawful routes is placement, and placement is an
existing owner's job. Adding alternation here would quietly move the allocator into the description language.

---

## 4. Evaluation semantics

Let `c` be a task cohort and `q95(c)` its conservative upper native cost for the resource's unit (R35 §11 — a
conservative upper estimate keyed on task class, model/harness/rate generation, effort, context band and tool
set; never a cohort mean).

### 4.1 Available value
`avail(E)` returns available **native value**, recursively:

```
avail(LEAF)            = usable(LEAF)                              # §6.1
avail(ALL_OF(...))     = min over BUDGET children of avail(child)
                         , then capped by every CEILING child:
                         min(that, remaining(ceiling_c)) for each CEILING c
                           whose named subexpression carries the value
avail(ORDERED_SPILL()) = SUM over stages of avail(stage)           # <= the operator blind min() gets wrong
```

`ORDERED_SPILL` **sums**. `ALL_OF` **minimises over BUDGETs and caps by CEILINGs**. Mixing the two up in either
direction is the defect this contract exists to prevent.

### 4.2 startable_jobs is computed at the root, after the algebra
```
startable_jobs(c, E) = floor( avail(E) / q95(c) )
```
Never `min` over per-leaf `floor(usable_r / q95)`. The division happens **once, at the root of the evaluated
expression**, because a spill stage that is exhausted is not a constraint of zero — it is a depleted first stage
whose successor still holds value.

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

### 4.5 Unknown fails closed
If any leaf in `E` has UNKNOWN or STALE observation, unknown generation, or an unproven independence claim
(§5.3), then `avail(E)` is **UNKNOWN**, not zero and not the entitlement. An UNKNOWN expression cannot size
capacity, cannot authorise a claim, and cannot satisfy `capacity_known`. It also does not make the route
unusable for a *human-attended* act — it makes it unusable as **autonomous Fabric capacity**.

---

## 5. Worked expressions for the current portfolio

Every number below that is not receipted at master is marked ILLUSTRATIVE or UNKNOWN. **No enrollment fact is
invented.** Actual Alibaba Team tier, actual MiniMax plan generation and actual Claude sublimit remainders are
UNKNOWN at this pin; §9 records what master actually models.

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
- Model-specific debit (GLM-5.3 ≈ 3× GLM-5.3-Flash for identical token composition, per the published
  multipliers) is a **cost prior**, never a scheduling constant. Master already carries the stronger rule:
  `control_plane/provider_model_economics.py:21` admits `measured_native_delta` as a burn method, and
  `config/provider_model_economics.v1.json` records for `glm.glm-5.3-flash`: *"Do not guess Flash credit
  multipliers; learn native burn from usage deltas by model/task cohort."*
- **Live defect this models.** The kit's own aggregate reports one 5-hour figure (`5h used/cap/pct =
  0.0/28000/0.0%`) for a fabric holding three such plans, while its per-account breakdown lists only the two
  accounts that carry ledger rows. A single aggregate percentage over N accounts is exactly the collapse §1
  forbids; under this contract the three accounts are three expressions and the aggregate is not a capacity fact.
  *(Kit observation, not a master receipt; recorded as evidence of the defect, not as an enrollment fact.)*

### 5.2 OpenCode Go — per-account window triple, per-model debit weight, monthly policy gate
```
for acct in {C1, C2, C3}:
    E_go[acct] = ALL_OF(
        BUDGET go_rolling_5h[acct],
        BUDGET go_weekly[acct],
        BUDGET go_monthly[acct]
    )
```
- A request for model `m` debits `w(m)` normalised units, `w ∈ {1, 2, 4}` by published tier ($60/$30/$15 monthly
  per model per account). The weight is a **unit conversion inside one resource**, not a separate resource — this
  is the canonical example of R35 §5's "shared credit system with model-specific debit", and of failure class 2:
  the per-model request tables are conversion rates over one account-wide quota, not per-model pools.
- The frontier budget gate (a weight-4 model refused once the account's monthly used percent reaches its
  threshold) is a **policy gate on placement**, not a capacity fact. It belongs to §7, not to `avail`.
- **Refinement flagged for Sol.** R35 §2 writes this as `ALL_OF(go_shared_5h, go_shared_weekly, go_shared_monthly,
  go_concurrency)` — singular. That expression is correct *per account*; the fabric holds three of them, so the
  same "sibling routes, not a pool" rule as GLM applies. This is offered as a refinement of the example, not a
  contradiction of the operator set.

### 5.3 MiniMax Token Plan — per-model rows are EVIDENCE VIEWS, never wallets
```
E_minimax = ALL_OF(
    BUDGET minimax_plan_5h[plan_generation],
    BUDGET minimax_plan_weekly[plan_generation]
)
views(E_minimax) = { "MiniMax-M3": <row>, "MiniMax-M2.7": <row>, ... }   # independence: UNPROVEN
```
`/token_plan/remains` exposes model-oriented remaining rows and the #7103 parser preserves them. Preserving a row
is not establishing a wallet. Normative rules:

- A view with `independence: UNPROVEN` contributes **zero** additional available value. `avail` is computed from
  the underlying resources only. Views may be displayed; they may never be summed (failure class 14).
- Independence is proven only by a **discriminating observation pair**: an operation attributed to view A must
  leave view B's remaining unchanged across two observations of the same generation. Until that evidence exists
  at the current generation, independence is UNPROVEN and fails closed.
- Master already refuses the adjacent error: `config/provider_model_economics.v1.json` records for
  `minimax.minimax-m3` that the Token Plan "is governed by 5-hour rolling, weekly, billing-cycle token allocation
  and concurrency resources", and `tests/test_provider_model_economics.py:91`
  (`test_subscription_burn_method_is_declared_without_quota_balances`) pins that the catalog declares a burn
  *method* without carrying balances.
- The plan generation itself is **UNKNOWN** at this pin (§9).

### 5.4 Alibaba Team — seat → member ceiling → packs by nearest expiry
```
E_alibaba[seat] = ALL_OF(
    BUDGET  ORDERED_SPILL(
                seat_monthly[seat],
                ALL_OF(
                    CEILING member_shared_pack_cap[seat] over the spill below,
                    BUDGET  ORDERED_SPILL(pack_nearest_expiry, pack_next_expiry, ...)
                )
            )
)
```
This is R35 §2's expression written with the §3.2 roles made explicit. The member cap is a CEILING over the
shared-pack subexpression — it meters the draw routed through the packs and holds no value of its own. §10 works
it numerically.

**Everything about our actual enrollment here is UNKNOWN**: the Team seat tier (Alibaba documents 25k / 100k /
250k Credits per seat per subscription month and 625k per shared pack, but which we hold is not evidenced at
master), how many packs exist, their expiries, and the member cap value. Master models **Personal**, not Team
(§9). Do not rename the profile to close this gap — R35 §16: bind the actual enrolled Team seat tier, seat realm,
subscription generation and pack generation through Provider Control.

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
Per R35 §10, for each leaf:
```
usable_r = observed_remaining_r
         - outstanding_holds_r        # §8, this fabric's own un-reconciled claims
         - hard_reserve_r             # policy floor
         - soft_reserve_r             # scarcity reserve derived from the READY graph (advisory, later step)
         - uncertainty_margin_r       # observation-freshness and accounting-lag margin
```
`usable_r` is clamped at zero and is never negative-signalled as debt.

### 6.2 Reserve with a conservative cost
Reservations use `q95(c)` (or the reviewed policy quantile), never the cohort mean; failed work stays in the cost
of reaching an accepted result; ambiguous shared-consumption attribution is rejected rather than learned from
(R35 §11, failure class 16). A candidate without comparable evidence stays in SHADOW/CANARY rather than receiving
production placement.

### 6.3 Concurrency is an observed dynamic resource
Marketing concurrency values are not scheduler truth (R35 §7). Provider Control owns: observed concurrency
availability, provider cooling/throttle state, last successful parallelism, freshness, and dynamic safety
evidence. Suggested parallelism is an **output** of Capacity (§4.3), not static plan metadata.

- A concurrency reduction or a 429/cooling signal **reduces new starts** and must never move work that has
  already STARTed (failure classes 10, 11), and must never be reported as a credential failure.
- Learned safe parallelism is keyed to the entitlement/realm/**generation** (§2.2) and the relevant provider
  scope, so a generation change resets it conservatively rather than inheriting a stale number.
- Master already carries the shape of the guard on the consumer side:
  `control_plane/capacity_economics_projection.py:175` refuses a preview whose `suggested_parallelism` exceeds
  `estimated_startable_jobs`.

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
  | PROVIDER_USAGE_MODE_UNKNOWN    # the policy owner cannot prove the mode is admitted
```
The vocabulary is offered for freezing at review (R35 §6: "The exact vocabulary can be frozen during contract
review").

### 7.2 The gate
At admission, a job's **requested mode** must intersect the **plan policy's admitted modes for this exact
harness**, resolved through the existing policy owners at the current plan generation.

- If the policy owner cannot prove our invocation mode is admitted → `PROVIDER_USAGE_MODE_UNKNOWN` → the
  subscription is **unavailable for that operation**, regardless of how much quota it shows (failure class 12).
- This is a refusal of the *operation*, not a write-off of the subscription. The same capacity may be used
  aggressively for provider-compliant supported-tool workflows while another execution mode uses PAYG or another
  lawful provider.
- "Supports agent tools" must never be reinterpreted as "all unattended automation is allowed."

### 7.3 Binding precedent to fold in
R13 (MiniMax headless ruling) is normative here and is restated so the contract carries it: **`claude -p` one-act
headless runs are UNATTENDED execution** for Mastermind policy unless a current provider-policy receipt
explicitly admits that exact mode under the plan. "Attended in causation" is insufficient. Kit headless runs are
engineering evidence, not governed capacity. An interactive canary never flips a flag (R18 (2)).

### 7.4 What master already encodes, and what is missing
`config/subscription_provider_profiles.v1.json` (schema `mastermind.subscription_provider_profiles/v1`) carries
three profiles, each with a boolean policy set — `glm-coding-plan` at line 5, `alibaba-token-plan-personal` at
line 33, `minimax-token-plan` at line 62; `autonomous_allowed: false` at lines 24, 52, 81; and a `usage_policy`
block with `interactive_only: true`, `unattended_background_allowed: false`,
`production_backend_allowed: false` at lines 28–30, 56–58 and 85–87. `tests/test_subscription_provider_profiles.py:142`
(`test_usage_policy_cannot_omit_or_weaken_baseline_fences`) and
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
1. Revalidate generation and observation freshness (§2.2, §2.3).
2. Resolve the exact resource expression `E` for the chosen route.
3. Compute the conservative required native capacity per resource, by evaluating the debit partition of §3 for
   one operation of cost `q95(c)` (the same partition §10 works numerically).
4. **Atomically reserve the internal resource bundle together with the existing Executive claim** — one
   transaction, not two.
5. Persist the capacity evidence/reasoning receipt with `JOB_CLAIMED`.
6. On completion: reconcile the actual provider debit through Provider Control; release the internal hold
   **once**; update outcome/cost evidence.
7. If provider accounting lags or the effect is uncertain (`EFFECT_UNKNOWN`), **do not reuse the held capacity**
   and do not economically fail over (failure class 18).

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
| **No resource-hold ledger exists** | searched `control_plane/`, `ops/`, `sql/` for `CREATE TABLE *hold*` / `*reserv*` / `resource_hold` / `capacity_hold` — the only match is `sql/0001_schema.sql:75` `holdout_touches`, which is a statistics guard, unrelated |

So the answer to R35 §14's conditional is: **the existing claim contract cannot express a resource-bundle hold.**
It reserves a *worker slot*, keyed `(worker_id, quota_class)` — a mutual-exclusion lease over one of our own
lifecycle objects. It never reserves a provider-native quantity, and `quota_class` is a scalar, so it cannot name
a bundle.

### 8.3 The narrow amendment (proposed, to be reviewed as a separate act)
Smallest change that satisfies §8.1 without a second plane:

- **A1 — one required field on the claim receipt.** `JOB_CLAIMED`'s payload (written at
  `control_plane/executive_runtime.py:11236`) gains an immutable `capacity_hold` record: the evaluated expression
  identity, per-`resource_id` reserved native quantity, each resource's `generation`, and the `observed_at` of
  the observation the reservation was computed from.
- **A2 — one holds table, debited inside the same transaction.** A table keyed by `resource_id` (not by
  `worker_id`), written by `_claim_job_in_transaction` (`:11015`) in the same SQLite transaction as the existing
  slot mutation — `control_plane/executive_runtime.py:11090` `updated = connection.execute(` / `:11093`
  `SET status='BUSY',held_attempt_id=?,fence_counter=fence_counter+1,`. Two concurrent claims against one
  `resource_id` then serialise on the same rows, which is what makes failure class 6 structurally impossible
  rather than merely tested.
- **A3 — one release path**, invoked exactly once on reconciliation, with `EFFECT_UNKNOWN` holding the reservation
  rather than releasing it (§8.1 step 7).

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

### 9.1 Strict `provider_capacity.v1` is untouched
R35 §2: "Do NOT append this silently to strict `provider_capacity.v1`." This contract does not modify it, extend
it in place, or redefine any of its fields. It is a **new, separately versioned artifact** that composes with it.

There is also a mechanical reason the in-place edit is forbidden, receipted at this pin: the capacity producer is
a **Macro-side** artifact consumed through a hash-pinned source closure.
`ops/executive_os/capacity_source_contract.py:49` pins `"engine/provider_capacity.py"` and `:52` pins
`"scripts/build_provider_capacity.py"`; `:69` sets `ENTRYPOINT = SOURCE_ROOT / "scripts" / "build_provider_capacity.py"`;
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

### 9.3 UNKNOWN — written as UNKNOWN, per R35 §22 C ("Do not infer this from what we remember buying")
- Alibaba: actual **Team** product enrollment, seat tier, seat realm binding, subscription generation, shared-pack
  identity/count/expiries, member shared-pack cap. **UNKNOWN.**
- MiniMax: plan generation; whether per-model rows are independent resources. **UNKNOWN / UNPROVEN.**
- GLM: per-account entitlement generation and reset anchors as *Provider-Control* facts (the kit's numbers are
  local telemetry, not Provider Control receipts). **UNKNOWN.**
- Claude: Fable-family sublimit remaining per account. **UNKNOWN.**
- Every provider: whether our exact autonomous invocation mode is policy-admitted. **PROVIDER_USAGE_MODE_UNKNOWN**
  until a current policy receipt says otherwise.

---

## 10. Worked numeric example — ORDERED_SPILL debits exactly once, and blind `min()` is wrong

All quantities are **ILLUSTRATIVE**. They are chosen to exercise the operators, not to assert enrollment (§9.3).

### 10.1 State
One Alibaba Team seat `S1`, expression as §5.4:

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

### 10.4 The counter-example — what blind `min()` gets wrong
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

---

## 12. Release condition

This document is a PROPOSAL and is HOLD-FOR-SOL. Its release condition is a Sol architecture review of
**(a)** the contract shape — the two child roles, the partitionability precondition, the evaluation rules of §4,
the generation/freshness split of §2.3, and the claim amendment of §8.3 — and **(b)** the schema name and version
(`mastermind.provider_resource_composition/v1`). The seat does not release it.

Companion documents in this proposal:
- `research/MASTERMIND_EXECUTIVE_CAPACITY_COMPOSITION_ADVERSARIAL_ACCEPTANCE_MATRIX_2026-09-16.md` — the 20
  required failure classes mapped to tests, owners, fixtures and current status at this pin.
- `research/MASTERMIND_EXECUTIVE_CAPACITY_COMPOSITION_CRITICAL_PATH_MAP_2026-09-16.md` — steps A–H with custody.
