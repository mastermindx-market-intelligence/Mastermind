# Executive OS G0 — source-law ruling

**Date:** 2026-08-15  
**Status:** Chairman-directed governance/source-law correction for Phase 1G G0 remediation  
**Origin:** independent fresh-context Phase 1G architecture/security review, verdict `BLOCK`  
**Applies to:** Phase 1F §6 open questions; Phase 1G executive authority, strategy/admission, review independence, and protected-path semantics

---

## 0. Purpose

The Phase 1G review correctly found that the autonomy design depended on executive authority and priority concepts that were not yet represented precisely enough in canonical source law.

This change does not arm CEO wake or production writes. It establishes the governance substrate that later implementation must read and conform to.

`config/authority_map.yml` is the canonical machine-readable home for the rulings below. This memo records the decision rationale and resolves the Phase 1F questions that explicitly said not to build past them without a CEO ruling.

---

## 1. Executive seats

Ruling:

```text
chairman -> occupant_label Chris -> escalation_rank 300 -> authority none
ceo      -> occupant_label Sol   -> escalation_rank 200 -> authority none
coo      -> occupant_label Fable -> escalation_rank 100 -> authority none
```

Seat identity is organizational/routing identity only. It never grants capability.

`config/agents.yml` remains model/provider routing. `gpt-5.6-sol` is a model identifier, not the CEO seat registry or an authentication credential.

The legacy A7 name `FABLE_HUMAN` remains a portfolio/governance effect-taxonomy label for compatibility. It is not executive rank and does not place the COO over the Chairman.

---

## 2. Executive decision altitude

A deterministic server-side operation classifier maps canonical operations/state to the decision categories in `authority_map.yml`.

The model may recommend or describe a category, but that text has zero authority.

Chairman-reserved v1 categories include constitutional/Charter change, hierarchy and authority-policy change, company phase/north-star/standing-constraint change, production autonomy expansion, production-write trust-model change, autonomous merge/deploy/service-control/live-capital authority, protected-path policy change, constitutional Reasoning Governor change, and Chairman decision approval/rejection.

CEO-delegated v1 categories cover P0 add/retire/rescope, resource-policy rebalance, project initiation/stop/reprioritization/reframe inside the standing mandate, reasoning escalation requests, and route republish inside already approved policy.

COO v1 categories cover bounded decomposition, child-job creation, repair/review, deterministic placement, shrink-only pause/stop/drain, and upward exception escalation.

Changing the category table is itself Chairman-reserved.

---

## 3. One owner per priority concept

The previous phrase "Improvement Agenda / accepted strategic state" is retired because it conflated separate concepts.

Canonical split:

1. **Company strategy:** `config/strategic_state.yml` — canonical strategy decision artifact; runtime advisory/orientation-only.
2. **Candidate ranking:** `brain/improvement_agenda.py` — derived advisory ranking; not a mutable executive authority or project queue.
3. **Admitted-work lifecycle/order:** Executive SQLite — lifecycle authority and ordering of work only after explicit admission.

A project underneath an already active P0 may be admitted by a typed, authority-checked directive referencing the exact strategic-state revision. Starting such a project does not require mutating the strategic-state file merely to create work.

A proposed strategy change first follows the applicable CEO/Chairman decision category, then changes the Git-backed strategic-state artifact, and only afterward can an implementation directive reference the new revision.

No runtime scheduler keys directly off `strategic_state.yml`. No model persists a priority decision by patching generated Improvement Agenda output.

---

## 4. Phase 1F §6 rulings

### Q1 — COO bounds

Accept the proposed home and v1 values in `config/authority_map.yml`:

```text
max_fan_out_per_parent = 8
max_depth = 2
max_repair_rounds = 2
max_review_attempts_per_job = 2
max_children_total = 16
allowed_child_cost_classes = [default, small]
```

These are ceilings, never targets.

### Q2 — review verdict vocabulary

Use `approve|reject` for v1. `request_changes` is represented as `reject` plus typed findings/next actions; bounded repair is a cycle action, not a third terminal verdict.

### Q3 — seat registry

Order it now because Phase 1G CEO wake is the first consumer that requires machine-readable executive seat identity. Keep it in `config/authority_map.yml`, with `authority: none` for every seat. Do not create `seats.yml`.

### Q4 — implementation-result independence

Different `worker_id` is the v1 minimum for the Phase 1F implementation-result aggregation gate. Stronger account/provider separation is recorded when achieved but is not silently required for every routine implementation review.

This does not weaken the separate high-impact executive dissent policy, which may require a stronger independence class.

### Q5 — sequencing

Keep 1F-B and 1F-C separate. 1F-B schema/refusals/inbox evidence must land before 1F-C orchestration.

### Q6 — independence starvation

No independence waiver vocabulary in v1. If review attempts are exhausted without a qualifying review, emit the typed exception and escalate. A CEO may re-scope or re-resource the work but cannot retroactively relabel a non-independent review as independent.

---

## 5. Executive dissent

High-impact executive dissent uses a deterministic policy-selected independence class.

If the required class is unavailable:

```text
DISSENT_UNAVAILABLE
```

and the action defers/retries/escalates according to policy. A degraded critic can never return a gate-satisfying `CLEAR` while being represented as independent.

The critic remains read-only challenge evidence and has no veto/write authority of its own.

---

## 6. Protected paths

`authority_map.yml` now declares a minimum constitutional/governance protected-path set including the Charter, authority map, strategic state, worker-facing executive contracts, Executive MCP implementation, Executive OS operations, and CI/workflow policy.

Autonomous workers/models may not receive write authority to those paths merely through a Job payload or model request, and may not widen the protected set themselves.

A proposed change to constitutional/authority/trust/autonomy source law is a separate reviewed change at the required executive decision altitude.

---

## 7. What this does not authorize

This ruling does not:

- arm production MCP writes;
- create CEO wake runtime;
- create a second lifecycle database or scheduler;
- create a new mutable company-priority database;
- authorize merge/deploy/service control/live capital;
- authenticate a caller from a seat/model/actor label;
- let an LLM choose its own decision altitude;
- waive Phase 1C-A or Phase 1F-B/C gates.

Phase 1G production work still requires the later capability, identity, migration, and acceptance gates.
