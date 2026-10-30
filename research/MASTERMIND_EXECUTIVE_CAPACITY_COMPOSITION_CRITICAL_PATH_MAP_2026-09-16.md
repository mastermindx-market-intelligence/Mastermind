# Critical path A–H for the resource-composition contract — custody map, PROPOSAL

STATUS: PROPOSAL — HOLD-FOR-SOL
Census anchor: master@0fe8074ff953b2ced9025ed40f0f66019c759967 (Mastermind). PR states were read live on
2026-09-16 and are stamped with the head sha they were read at; a head that moves invalidates the row, not the
map.
Source of the A–H sequence: Sol capacity-routing architecture ruling (R35) §22, verbatim ordering preserved.
Companions: `…_RESOURCE_COMPOSITION_CONTRACT_2026-09-16.md`, `…_ADVERSARIAL_ACCEPTANCE_MATRIX_2026-09-16.md`.

**This document starts nothing.** R35 §22: "Do not start a new program. Continue the existing
EXECUTIVE-CAPACITY-FABRIC." Steps B–H are mapped so that a successor can see the shape; none is commissioned
here, and no custody is claimed over any PR listed below.

Protected master has moved to `8ba7deedde164c90298d3e88785d98e02fa5e2d2`; the census anchor remains
`master@0fe8074f…` for existing receipts. #682 (`52bb6026`) and #683 (`a78b8fe2`) are path-disjoint,
capacity-adjacent physical-resource precedents only. They do not supply provider-resource composition, provider
holds, or any provider-capacity acceptance class.

---

## 0. Custody ledger (read live 2026-09-16, one `gh pr list` call per repository)

| PR | Repo | Head (read 2026-09-16) | State | Labels | autoMerge | Base | Custody / hold |
|---|---|---|---|---|---|---|---|
| #7116 | macro | `4d7ddfd24a5f` | OPEN, DRAFT | none | null | `sol/provider-subscription-catalog-20260913` | **WRITE WITHHELD** (R19 (6), R13). Quota-economics preview across subscriptions. Note it is **not** based on `main` — it stacks on the catalog branch. |
| #7103 | macro | `6ce16e745064` | OPEN, DRAFT | none | null | `main` | **RELEASE HOLD** (R13; seat removed the arms). GLM/Alibaba/MiniMax subscription source; owns the `/token_plan/remains` parser. |
| #7142 | macro | `fe4dd5b142b1` | OPEN, DRAFT | none | null | `main` | **RELEASE HOLD** (R13). Provider account pool selector; subordinate candidate-selection kernel only (contract §11.1). |
| #7162 | macro | `814a58d2c200` | OPEN, DRAFT | none | null | `main` | Family-B, macro half. **B0 gate**: B0 not accepted; do not start B1–B5 (R15). |
| #662 | Mastermind | `fc5bbcf15a4f` | OPEN, DRAFT | none | null | `master` | Family-B, Mastermind half. Same B0 gate. Paired review child `ocr2c-family-b-paired-architecture-review-20260914-sol-001` is PRE_START on its own carrier — **do not steal it** (R15). *(R15 recorded `30f8a4c1`; the head has since moved — this row is the live read.)* |
| #671 | Mastermind | `0cdb3ba422a5` | OPEN, DRAFT | none | null | `master` | **Sol-authored, Sol's writer only.** Accepted at its ceiling: APPROVE_AS_SPEC_ONLY, R2-B1/B2 closed (R34 (1)). Source law for capacity harvesting. |
| #676 | Mastermind | `7e6a35b66e8e` | OPEN, DRAFT | none | null | `master` | **Sol-authored, Sol's writer only.** SOL-ACCEPTED AS SPEC_ONLY; **SOL ACCEPTED / STOP** (R23 (1)). Release/merge is a separate Sol maintenance act; no successor wave. |
| #665 | Mastermind | `ac2552504b31` | OPEN, DRAFT | none | null | `master` | **PARKED** (R13, reaffirmed in the 2026-09-15 seat rulings). MiniMax Codex Responses realm carrier. Re-sequence at the Go/Alibaba realm promotion decision, not before. Do not manufacture a receipt store. |

Two custody rules that govern every row above and are not negotiable by this map:

1. **A Sol-authored PR has a Sol writer.** #671 and #676 are repaired by Sol's own writer on the same branch.
   Nothing in steps A–H authorises a second writer, a replacement PR, or a rebase of those branches.
2. **A hold is a merge barrier regardless of label state.** Every row above is DRAFT with empty labels and
   `autoMerge: null`; that is the *enforced* shape of the hold, and this document neither arms nor releases any
   of it.

---

## 1. Step A — Freeze resource-composition + execution-mode semantics

- **Owner**: Sol / Fable architecture responsibility (R35 §22 A).
- **What exists at master**: nothing for the tree. `estimated_startable_jobs` is a scalar consumed by
  `control_plane/capacity_economics_projection.py:83`; there is no operator vocabulary, no resource identity, no
  generation-axis/freshness split, and no claim-side **provider-capacity** hold
  (`control_plane/executive_runtime.py:1593` keys the claim on `(worker_id, quota_class)`; the inactive
  `_PHYSICAL_RESOURCE_SCHEMA_CANDIDATE` at `:2248` is a different resource domain — contract §8.2.1).
- **What this PR contributes**: the contract proposal, its acceptance matrix, and this map — docs only. No `.py`,
  no `config/`, no `schema/`, and strict `provider_capacity.v1` untouched (contract §9.1).
- **Who may write**: this lane wrote the three documents; the seat posts. **Release**: Sol architecture review of
  the contract shape + the still-UNFROZEN domain-explicit schema candidate + the Provider Capacity V2
  embedding/binding decision (contract §9.0).
  The seat does not release.
- **Blocked by**: nothing. This is the step that unblocks the rest.
- **Not done here**: the machine-readable schema file. A schema file is a later reviewed act; freezing semantics
  in prose first is deliberate, so the review can attack the semantics before a validator entrenches them.

## 2. Step B — Finish existing source owners in parallel

R35 §22 B names three, each with an existing owner and an existing hold.

Step B is FROZEN here as a shape, reference only: deterministic receding-horizon over the CURRENT authorized
Executive READY set; hard gates first; constrainedness-before-convenience planning order; conservative debit
plans simulated per C1-top-tied candidate; one-route-per-demand-unit provisional reserves (no multi-provider
double reserve); lexicographic comparison a–i; an ADVISORY plan bound to READY-set identity, C1 inputs, Provider
Capacity V2/resource graph, hold set, cost-calibration generation, routing/policy generation, and
as-of/fresh-until digests; #657-style preference only for the exact current C1 tie; recompute on material events;
no long-lived planner state. **Do not implement Step B before #688's Step-A freeze.**

The frozen shape gains a `portfolio_optionality_cost` lexicographic stage, derived from the number and value of
differentiated future routes that share the same resource. It is a stage in the lexicographic order, **not a
universal score**.

### B/#7103 — reconcile current generation axes
- **What exists**: the subscription source and the `/token_plan/remains` parser that preserves per-model rows.
- **What step B asks**: reconcile current GLM / Alibaba Team / MiniMax `capability_generation`,
  `resource_generation`, `composition_generation`, and `model_harness_cost_generation` facts; retain historical
  generations; **do not infer enrollment**.
- **Custody**: RELEASE HOLD at `6ce16e745064`; the seat removed the arms (R13). Its writer keeps it.
- **Blocked by**: the hold. Composition dependency: contract §2.2 defines the generation axes, and
  §5.3 defines that its per-model rows are views, not wallets — so B/#7103 should not be released before A is
  reviewed, or the parser's rows risk being read as independent resources (failure class 14).

### B/#7116 — publish the already-tested measured-input repair
- **What exists**: the economic calculator that R35 §21 identifies as *ahead of* the canonical contract.
- **What step B asks**: publish the measured-input repair; preserve accepted-result cost and the reserve
  implementation; **do not turn preview inputs into capacity truth**.
- **Custody**: **WRITE WITHHELD** (R19 (6)). Head `4d7ddfd24a5f`, based on
  `sol/provider-subscription-catalog-20260913` rather than `main` — any sequencing must account for that stack.
- **Blocked by**: the write withholding. This is the PR the whole ruling is about: it can reason over richer
  scenarios than Capacity can publish, which is precisely why A must land first.

### B/#671 — harden the source law
- **What exists**: the source law for subscription capacity harvesting, accepted APPROVE_AS_SPEC_ONLY with
  R2-B1/B2 closed at `0cdb3ba4` (R34 (1)).
- **What step B asks**: harden it with the resource-composition / execution-mode / atomic-reservation /
  receding-horizon rules from R35. **No replacement PR for aesthetic consolidation.**
- **Custody**: **Sol-authored; Sol's writer only.** Any hardening is authored there, not here.
- **Blocked by**: nothing procedural, but substantively it consumes A's output — hardening it against an
  unreviewed contract would bake in semantics Sol has not yet accepted.

## 3. Step C — Ground actual enrollment

- **Owner**: Provider Control, without exposing credentials.
- **What step C asks**: for every purchased provider recover actual product; tier; the six
  generation/freshness axes of contract §2.2 (`capability_generation`, `resource_generation`,
  `composition_generation`, `realm_binding_generation`, `model_harness_cost_generation`,
  `observed_at`/reset boundary); seat/realm
  binding; billing/reset generation; shared-pack identity where applicable; usage-policy class. R35 §22 C:
  "Do not infer this from what we remember buying."
- **What exists at master**: the *shape* of a credential ceremony and realm receipts, all hermetic —
  `ops/executive_os/subscription_provider_credential.py` owns the secret-bearing ceremony (R15, no second
  writer); `ops/executive_os/provider_realm_facts.py:40` refuses direct issuance;
  `ops/executive_os/capacity_owner_facts.py:44` refuses direct minting;
  `control_plane/model_router.py:1082` / `:1108` export and verify the capacity owner fact.
- **What is UNKNOWN** (contract §9.3, and this is the whole point of step C): Alibaba **Team** enrollment — master
  models Personal (`config/subscription_provider_profiles.v1.json:33`
  `"alibaba-token-plan-personal"`) — `stage_routing` (PARTITIONED versus ATOMIC_FALLBACK), seat tier,
  shared-pack identity/count/expiry, member cap; MiniMax plan `capability_generation`; GLM per-account
  `capability_generation` as a Provider-Control fact; OpenCode Go actual enrollment and pool-membership policy
  eligibility (schedulable entitlement count: 1 proven-at-most, actual enrollment UNKNOWN).
- **Blocked by**: not by a hold — by the absence of a live evidence path. R15: the realm/capacity facts are
  fixture-only, so today's minting is interactive-canary evidence, not production enrollment. R27 additionally
  records the Executive web→MCP connector at `401 Manual reauthentication required`, so the authenticated surface
  a step-C recovery would use is currently broken.
- **Who may write**: the existing credential/realm owners. **No second writer, no second store** (R15).

## 4. Step D — Obtain fresh native observations

- **Owner**: Provider Control observation path.
- **What step D asks**: GLM 5h + weekly + tool allowance / reset / concurrency; MiniMax shared-plan semantics +
  5h + weekly + dynamic throttling; Alibaba Team `stage_routing`, seat monthly remaining, shared-pack
  remaining/expiry, member limit, and dynamic concurrency. **Unknown stays unknown.**
- **Composition dependency**: contract §2.3 — an observation is only usable inside its freshness window and dies
  at a reset boundary; and §4.5 — one UNKNOWN leaf makes the whole expression UNKNOWN. So step D's product is not
  "numbers" but *dated, generation-stamped* numbers.
- **What exists**: local telemetry in the kit (a shim aggregate and a per-account ledger breakdown) that is
  **not** a Provider Control receipt. R13-B2 is binding here: volatile provider/account numbers without immutable
  or dated Provider-Control receipts are `UNVERIFIED_FOR_ROUTING` — they cannot size capacity, route, purchase,
  or satisfy `capacity_known`.
- **Blocked by**: step C (you cannot stamp an observation with a generation you have not recovered).

## 5. Step E — Qualify model cohorts

- **Owner**: model economics catalog owner + Model Router, with Outcome Learning evidence.
- **What step E asks**: add missing current model-economics entries; run comparable Mastermind jobs; build
  quality/cost cohorts; **promote only from evidence**.
- **What exists**: `config/provider_model_economics.v1.json` — schema
  `mastermind.provider_model_economics/v1`, `"production_armed": false`, `"scope": "routing_models_only"` — with
  `measured_native_delta` admitted as a burn method (`control_plane/provider_model_economics.py:21`) and the
  declaration-without-balances rule pinned (`tests/test_provider_model_economics.py:91`).
- **What is missing**: Alibaba **Team** model entries (the catalog's Alibaba surface is
  `alibaba_token_plan_personal`), and cohort keys that bind model *and* harness *and* `model_harness_cost_generation`
  (contract §2.2; matrix class 15).
- **CF2-I / incumbent C1 note**: #657 (head `bc89980c7e06e81a883da8078660d3bf208e68eb`, OPEN,
  BUILT_NOT_PROVEN / REPAIR_REQUIRED) is the incumbent candidate seam; repair it on its own branch after Step A.
  CF2-I is downstream integration/adoption owner. End state: Model Router first lawful tier → concrete C1 Worker
  candidates → Capacity resource/economics evidence → **#657's exact tie/abstention preference seam** → CF2-I
  → C2 / Executive atomic resource+worker commitment → existing broker/adapter. **No second selector, and no
  dead producer**: the Capacity evidence the seam reads must be an existing, exact/content-addressed producer
  at the seam's own head; a preference receipt naming a producer that does not resolve there is INADMISSIBLE,
  not merely stale. **Current states**: #657 OPEN, BUILT_NOT_PROVEN / REPAIR_REQUIRED at `bc89980c`; CF2-I
  UNBUILT — the integration/adoption owner exists as a named seat, not as merged code, and its RF1 receipts
  are read-only at `8ba7deed`; C2 / Executive atomic commitment UNBUILT — §8.3's canonical primitive is not
  chosen yet, which is why step G cannot open. RF1 receipts:
  `docs/EXECUTIVE_WORKER_ROUTING.md:74@8ba7deed` and `:95@8ba7deed`. Never mint a worker selector, second
  model-to-worker registry, or provider scheduler, and never reorder `preferred_model_aliases` on economics
  grounds.
- **Blocked by**: step C for the Team entries; step A for the cohort-key definition.

## 6. Step F — Shadow portfolio planner

- **Owner**: Capacity, reading the **existing** Executive READY set (R35 §8). It does not claim, does not create
  jobs, does not own lifecycle, and creates no queue.
- **What step F asks**: run the planner against real READY demand with no live placement; compare against
  incumbent routing; measure quality, resource use, stranding, cash, repair, deadline impact.
- **What exists**: the advisory bridge — `control_plane/capacity_economics_projection.py:19`
  `PROJECTION_SCHEMA = "mastermind.capacity_economics_projection/v1"` — whose output is explicitly advisory and
  requires claim-time revalidation. That is the correct seam for a shadow planner to write into.
- **Blocked by**: A (the planner needs a tree to plan over), C+D (it needs real observations to be a shadow of
  anything), E (it needs cohort costs).
- **Not authorised here**: any live placement, and any scheduler/daemon.
- **Adversarial additions**: time-bound offer expiry and surface mismatch (matrix classes 31–32) must be on the
  frozen Step-B test list; a promotion change invalidates the advisory plan digest.
- **Rollout-order reference, FROZEN, not commissioned** (this is the order surfaces come online; it is NOT
  the direct-subscription qualification order, which is in §7): Codex → OpenCode Go coding-agent API (only after
  #7143, this resource contract, and CF2-I) → GLM direct where that execution mode is admitted → direct MiniMax
  and Alibaba only in lawful modes. **Do not activate Go yet.**

## 7. Step G — Bounded real canaries

- **Owner**: whichever vertical Sol selects; one at a time.
- **What step G asks**: for each canary prove the full chain — fresh capacity truth → lawful Model Router tier →
  resource-expression evaluation → atomic claim/hold → existing governed harness → real task → visible useful
  result → independent verification where required → actual provider debit → hold reconciliation → corrected
  fresh capacity.
- **Blocked by**: all of A–F, plus the canonical Executive commitment primitive (contract §8.3), without which
  "atomic claim/hold" cannot open, plus the **execution-mode gate** (contract §7 —
  every current profile is `autonomous_allowed: false` at
  `config/subscription_provider_profiles.v1.json:24`, `:52`, `:81`, and R35 §6 says do not relax that because the
  adapters work).
- **Standing precedent**: an interactive canary never flips a flag (R18 (2)); `claude -p` headless is UNATTENDED
  unless a policy receipt admits that exact mode (R13).
- **Frozen heterogeneous-canary #1, NOT commissioned**: Codex plus **ONE single-account OpenCode Go /
  MiniMax-M3 worker**, through protected #622's single-account path — not direct MiniMax.
- **Gates before any START, in order**: (1) #688's own Step-A resource-semantics freeze — this document is
  gate 1 of the chain; (2) #7103/#7143 reconciliation, with #7143 OPEN/DRAFT at `facf7074`,
  BUILT_NOT_PROVEN, owing one authorized real-account usage observation and exact-head CI; (3) exactly one
  lawful Go entitlement; (4) fresh Go offer/model/privacy digests, with no paid overflow; (5) concrete Go-M3
  Worker registration and harness qualification through the existing adapter/binding owners — no model→worker
  registry; (6) the C1 first-tier candidate set, the #657 preference receipt, CF2-I, and C2 atomic commitment
  (a bounded explicit canary may use a reviewed fixed Worker under canary law and must never be mislabeled as
  general routing); (7) result → usage delta → Provider Control observation → hold settlement.
- **Frozen direct-subscription canary #1, NOT commissioned**: GLM Coding Plan. Neither canary is activated.
- **Frozen direct-subscription QUALIFICATION order, NOT commissioned** — distinct from §6's rollout order
  (which sequences surfaces, Go included) and from the canary sequencing above (which sequences proofs).
  This is the order in which DIRECT subscriptions are qualified after Step A, and it follows from execution
  mode being a dimension of the capacity quantity rather than a tag (contract §7):
  1. **GLM Coding Plan** first, through protected **#581**'s hermetic `interactive_canary` admission seam.
     The binding `glm-coding-plan.claude-code-anthropic` stays **SPEC_ONLY**, and this is a bounded
     interactive canary — **not a flag flip**.
  2. **MiniMax M3** as a utilization target in an interactive/tool lane, on the **#665** incumbent path.
     The host wrapper stays pinned to MiniMax-M2.7 (contract §5.3's observed inventory); a wrapper that can
     reach a model is not an entitlement for it.
  3. **Alibaba Team** as an **`INTERACTIVE_TOOL` capacity domain only** — contract §7.1's
     `SUPPORTED_TOOL_INTERACTIVE` / `SUPPORTED_TOOL_AGENT_SESSION`, never `UNATTENDED_BACKGROUND` or
     `APPLICATION_BACKEND` — because the provider terms prohibit automated backends, and because the
     protected profile still models **Personal** against the Chairman's **Team**. That enrollment identity
     must be fixed before any plan-specific canary (contract §9.3 U2).
  Nothing in this order is started, and none of it is a permission to convert a technically reachable
  wrapper into autonomous capacity.

## 8. Step H — Small live fleet

- **Owner**: Executive, after Capacity and Provider Control have cleared.
- **What step H asks**: only after shared-resource race tests and correction/reset tests pass, enable a small
  number of eligible new-task claims. **Never migrate already-STARTed work for economics.**
- **Blocked by**: the acceptance suite. The race tests are matrix class 6 (currently PARTIAL — worker-slot
  exclusion only) and the correction/reset tests are classes 7 and 8 (currently MISSING). H cannot open while
  those three are not EXISTS. Worth stating plainly because it sizes the remaining work: at this pin **no** class
  of the thirty-nine is fully EXISTS — eleven are PARTIAL, twenty-eight MISSING.

---

## 9. Dependency shape, stated once

```
A (this PR, HOLD-FOR-SOL; release also depends on the V2 embedding/binding decision)
├─► B/#671  harden source law        [Sol's writer]
├─► B/#7103 generation reconciliation [RELEASE HOLD]
├─► B/#7116 measured-input repair     [WRITE WITHHELD]
└─► C ground enrollment  ──► D fresh observations ──► E cohorts ──► F shadow planner ──► G canaries ──► H fleet
        ▲                                                                   ▲
        └── needs the Executive web→MCP reauth (R27)                        └── needs classes 6,7,8 EXISTS
Family-B (#662 / #7162) composes with A at §2.1 and is itself gated on B0 acceptance — it is a peer input to C/D,
not a step in this chain, and its paired review child is PRE_START on its own carrier.
#665 stays PARKED; it re-sequences at the Go/Alibaba realm promotion decision, which is downstream of C.
```

## 10. What a successor must not conclude from this map

- That any B–H step is started. None is. This document maps them.
- That a PR listed in §0 may be edited, armed, marked Ready, rebased or merged by the holder of this map. None
  may.
- That local GLM/OpenCode Go credential counts or any kit-side pool number is a Provider Control capacity fact.
  They are local telemetry and are `UNVERIFIED_FOR_ROUTING` until a dated Provider-Control receipt exists
  (R13-B2).
- That an UNKNOWN in §3/§9.3 of the contract may be closed by inference. R35 §22 C forbids exactly that, and the
  contract writes every one of them as UNKNOWN for that reason.
