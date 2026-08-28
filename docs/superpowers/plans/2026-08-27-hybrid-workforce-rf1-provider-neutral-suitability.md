# RF1 Provider-Neutral Suitability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the existing stateless Model Router so it chooses an ordered set of provider-neutral suitability tiers before Capacity Fabric considers provider/account capacity or marginal cost, while preserving current Codex behavior and preventing model/provider identity from granting executive authority.

**Architecture:** RF1 stays inside `control_plane/model_router.py` and the reviewed `config/executive_worker_routes.json`; it creates no provider scheduler and no lifecycle state. The router will return ordered `SuitabilityTier` objects. A tier is an equivalence set of already-lawful model aliases; Capacity Fabric may later rank only inside the first tier with an eligible candidate. Current single-provider behavior remains semantically unchanged because the first migration groups only aliases already accepted by the current route policy. `frontier_lead` remains an adjudication/decomposition outcome, never a Worker claim.

**Tech Stack:** Python 3.11+, stdlib dataclasses/json/enum, existing Executive OS Model Router, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`

## Global Constraints

- Execute only after the current `CF2-I` capacity-aware claim wave is accepted or a newer Sol ruling explicitly changes that dependency.
- Refresh protected Skillpack, protected `master`, current Macro `WS:EXECUTIVE-CAPACITY-FABRIC`, and open PRs immediately before the first write.
- Executive OS remains sole Job/Attempt/Worker/Event authority.
- Model Router answers suitability only. It must not read live provider quota, cooling, health, Slack identity, host liveness, or credentials.
- Capacity/cost may rank only inside the first lawful suitability tier that contains an Executive-eligible candidate.
- No provider/model name grants `ceo`, `coo`, reviewer, merge, deploy, rights, or security authority.
- Preserve current review-independence and excluded-worker semantics.
- Production routing remains disarmed unless separately released under existing law.

---

### Task 1: Freeze the v2 route contract and ordered suitability tiers

**Files:**
- Modify: `control_plane/model_router.py`
- Modify: `tests/test_executive_model_router.py`

**Interfaces:**
- Produces `ROUTER_SCHEMA_VERSION = "mastermind.executive_worker_routes/v2"`.
- Produces `SuitabilityTier(tier_id: str, model_aliases: tuple[str, ...])`.
- `RoutingDecision.suitability_tiers: tuple[SuitabilityTier, ...]` replaces the flat decision authority of `preferred_model_aliases`; `preferred_model_aliases` remains a compatibility property returning the first tier only.

- [ ] **Step 1: Add failing v2 contract tests**

Add tests that construct a v2 policy with two tiers and assert:

```python
assert decision.suitability_tiers == (
    SuitabilityTier("routine.primary", ("model.a", "model.b")),
    SuitabilityTier("routine.fallback", ("model.c",)),
)
assert decision.preferred_model_aliases == ("model.a", "model.b")
```

Also assert the loader refuses: duplicate tier ids, empty tier alias arrays, an alias repeated across tiers for the same route/risk, unknown/ineligible aliases, and unknown keys in a tier object.

- [ ] **Step 2: Run RED**

Run:

```bash
python -m pytest tests/test_executive_model_router.py -q
```

Expected: failures because v2 tiers and `SuitabilityTier` do not exist.

- [ ] **Step 3: Implement the closed tier parser**

In `control_plane/model_router.py` add:

```python
ROUTER_SCHEMA_VERSION = "mastermind.executive_worker_routes/v2"

@dataclasses.dataclass(frozen=True)
class SuitabilityTier:
    tier_id: str
    model_aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"tier_id": self.tier_id, "model_aliases": list(self.model_aliases)}
```

Normalize each `routes.<task_kind>.<risk>` value as a non-empty list of exact objects with keys `tier_id` and `model_aliases`. Validate tier ids with the existing bounded-id grammar. Validate every alias with the existing model-alias eligibility/capability checks. Reject duplicates across tiers rather than silently deduplicating them.

- [ ] **Step 4: Change `RoutingDecision` without widening authority**

Replace the stored flat alias tuple with:

```python
suitability_tiers: tuple[SuitabilityTier, ...]

@property
def preferred_model_aliases(self) -> tuple[str, ...]:
    if not self.suitability_tiers:
        return ()
    return self.suitability_tiers[0].model_aliases
```

`to_dict()` must emit both `suitability_tiers` and the derived `preferred_model_aliases` compatibility projection. `job_constraints()` must keep its existing key set in this RF1 carrier except for the routing policy version change; the later capacity claimant consumes the structured decision through its reviewed RF1 integration seam rather than silently widening persisted v4 Job binding fields.

- [ ] **Step 5: Run GREEN**

Run the focused suite and require all existing v1 behavioral expectations to be updated only where the schema/shape intentionally changed:

```bash
python -m pytest tests/test_executive_model_router.py -q
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/model_router.py tests/test_executive_model_router.py
git commit -m "feat(exec): add provider-neutral suitability tiers"
```

---

### Task 2: Migrate the current policy without changing current routing outcomes

**Files:**
- Modify: `config/executive_worker_routes.json`
- Modify: `tests/test_executive_model_router.py`

**Interfaces:**
- Consumes v2 tier parser from Task 1.
- Current Codex-only routes remain equivalent at the decision boundary.

- [ ] **Step 1: Add migration-equivalence tests**

Pin the current route results before changing the config. For each existing `(task_kind, risk)` pair, assert the aliases that were lawful under v1 are all contained in the first v2 tier, and elevated routes do not gain any alias that was previously unavailable.

The expected migrated first tiers are:

```text
implementation/routine -> fast.engineering, standard.engineering
implementation/elevated -> standard.engineering
mechanical/routine -> fast.engineering, standard.engineering
mechanical/elevated -> standard.engineering
tests/routine -> fast.engineering, standard.engineering
tests/elevated -> standard.engineering
research/routine -> fast.research, standard.research
research/elevated -> standard.research
review/routine -> standard.review
review/elevated -> standard.review
```

- [ ] **Step 2: Run RED against the still-v1 config**

```bash
python -m pytest tests/test_executive_model_router.py -q
```

Expected: schema/tier migration tests fail.

- [ ] **Step 3: Migrate `executive_worker_routes.json`**

Set:

```json
"schema_version": "mastermind.executive_worker_routes/v2"
```

For each route/risk replace the alias array with exactly one current-equivalence tier, e.g.:

```json
"routine": [
  {
    "tier_id": "implementation.routine.primary",
    "model_aliases": ["fast.engineering", "standard.engineering"]
  }
]
```

Do not enable qwen/glm/xai and do not add Claude in this task. RF1 proves the quality-class grammar before heterogeneous execution is armed.

- [ ] **Step 4: Run focused and policy consumers**

```bash
python -m pytest \
  tests/test_executive_model_router.py \
  tests/test_executive_operator_supervisor.py \
  -q
```

Require current Codex decision semantics to remain unchanged apart from the v2 structured tier output.

- [ ] **Step 5: Commit**

```bash
git add config/executive_worker_routes.json tests/test_executive_model_router.py
git commit -m "chore(exec): migrate worker routes to suitability tiers"
```

---

### Task 3: Pin authority and independence falsifiers

**Files:**
- Modify: `tests/test_executive_model_router.py`
- Modify: `docs/EXECUTIVE_WORKER_ROUTING.md`

**Interfaces:**
- Consumes `SuitabilityTier` and current v2 policy.
- Produces durable routing law for later CF2/PF1 consumers.

- [ ] **Step 1: Add authority-failure tests**

Add tests proving all of the following:

```text
model=gpt-5.6-sol + provider=codex does not create a CEO Job or owner_seat
frontier.orchestrator remains worker_eligible=false
high ambiguity or critical risk returns FRONTIER_LEAD before any capacity choice
excluded_worker_ids survive unchanged in the decision
review task routing cannot re-admit an explicitly excluded builder Worker
provider cost_class cannot move an alias from tier 2 into tier 1
```

Use synthetic v2 policies to prove reordering aliases *inside* a tier does not change tier identity or tier precedence, while swapping whole tier order does change the decision.

- [ ] **Step 2: Run tests and confirm discriminating failures before any needed implementation repair**

```bash
python -m pytest tests/test_executive_model_router.py -q
```

If a falsifier unexpectedly passes for the wrong reason, tighten the test before changing production code.

- [ ] **Step 3: Update `docs/EXECUTIVE_WORKER_ROUTING.md`**

Document the exact pipeline:

```text
authority / job constraints
→ independence exclusions
→ first lawful Model Router suitability tier
→ Capacity Fabric ranks only candidates inside that tier
→ Executive OS atomically claims one Worker
```

State explicitly that a Codex runtime may later serve a `ceo`-seat technical-staff commission, but the router itself never grants the seat or role from the model/provider alias.

- [ ] **Step 4: Run combined routing/runtime regressions**

```bash
python -m pytest \
  tests/test_executive_model_router.py \
  tests/test_executive_os_phase1fb.py \
  tests/test_executive_inbox_phase1fb.py \
  -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_executive_model_router.py docs/EXECUTIVE_WORKER_ROUTING.md
git commit -m "test(exec): pin RF1 authority and independence law"
```

---

### Task 4: Exact-head integration proof and stop

**Files:**
- No new production files expected.
- Add sanitized evidence only if the repository's current proof convention requires it.

- [ ] **Step 1: Re-run collision census**

Immediately before push, compare the carrier against current protected master. If CF2-I or another accepted carrier changed `model_router.py`, `executive_worker_routes.json`, or the strict routing consumer contract, stop and reconcile; do not rebase blindly over semantic movement.

- [ ] **Step 2: Run the full relevant gate**

```bash
python -m pytest \
  tests/test_executive_model_router.py \
  tests/test_executive_os_phase1fb.py \
  tests/test_executive_inbox_phase1fb.py \
  tests/test_executive_operator_supervisor.py \
  -q
python -m compileall -q control_plane

git diff --check
```

- [ ] **Step 3: Push one RF1 PR and require hosted CI/CodeQL**

The PR remains one independently useful routing-contract wave. Do not add HF1 adapters or provider credentials.

- [ ] **Step 4: Independent adversarial review**

Reviewer must attempt to falsify: provider order laundering into priority, inadequate-tier promotion via cost, model identity granting CEO authority, exclusion loss, and v1→v2 migration changing current Codex routing.

- [ ] **Step 5: Return to Sol**

Return exact base/head SHA, changed files, v2 migration map, focused/full/hosted test receipts, adversarial verdict, discovered collisions, and confirmation `HF1/PF1/MH1 UNSTARTED FROM THIS CARRIER`.

## Stop Condition

RF1 stops when provider-neutral suitability tiers are implemented, current Codex routing remains behaviorally equivalent, authority/independence falsifiers pass, hosted evidence is green, and Sol has a reviewable exact-head carrier. It does not enable a new provider or perform capacity placement itself.
