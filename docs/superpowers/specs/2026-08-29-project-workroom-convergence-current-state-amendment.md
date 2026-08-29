# Project Workroom Convergence — Current-State / Planner-Input Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Status:** `SPEC_ONLY / CHAIRMAN-APPROVED / RECORDS_ONLY`  
**Operation key:** `project-workroom-convergence-20260829-sol-001`  
**Carrier:** Mastermind PR #232 / `sol/project-workroom-convergence-20260829`  
**Original protected pickup:** `mastermindx-market-intelligence/Mastermind@2962759e8abf6bf722a8582f92af8f84013f5f40`  
**Current protected release basis:** `mastermindx-market-intelligence/Mastermind@1b99ea1d0a6232e11fd46915d348685764cb00cf`  
**Authority:** narrow correction to the Project Workroom design and implementation plan after fresh current-code and live Linear archaeology. For the exact topics below, this amendment wins over the two earlier Workroom files on this carrier. It creates no runtime, Slack or Linear mutation authority.

---

## 0. Current-source reconciliation

Protected Mastermind advanced from the original pickup through #215 / `1b99ea1d0a6232e11fd46915d348685764cb00cf` while PR #232 was in review.

#215 changes only the current Sol Skillpack/manual-handoff placement procedure. It establishes that ordinary unbound `CAPACITY_SELECTABLE` work must surface:

```text
WAITING_CAPACITY / needs_placement
```

instead of routinely emitting `OPEN_PICKUP` or `ACCOUNT_BINDING: CHAIRMAN_SELECTS` and returning the Chairman to provider-account allocation.

That protected movement is compatible with, and strengthens, the Workroom architecture. The Workroom design already requires Capacity/RuntimeBinding/Executive owners to perform routine placement and treats provider accounts as ephemeral runtime facts rather than project/channel ownership.

Current interpretation:

```text
Project Workroom architecture: unchanged
routine unbound child placement: WAITING_CAPACITY / needs_placement
manual Chairman account allocation: explicit transition/exception only
WR-P0 planner: no placement or provider-routing authority
records carrier current-base lineage: reconciled to 1b99ea1d0a6232e11fd46915d348685764cb00cf
```

No #215 file or implementation is copied into this carrier.

---

## 1. Records carrier file census

Supersede Task 0 wording that says the records carrier contains exactly two files.

The exact records-only carrier is now three files:

```text
docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md
docs/superpowers/specs/2026-08-29-project-workroom-convergence-current-state-amendment.md
docs/superpowers/plans/2026-08-29-project-workroom-convergence.md
```

The third file is this bounded correction. No runtime, config, test, Agent OS, Linear, Slack, credential or production path is modified by PR #232.

---

## 2. Workroom strategy must name the expected Initiative exactly

The original strategy field list omitted the Initiative identity needed to reject wrong or missing strategic membership.

Every `workrooms[]` row in `mastermind.project_workroom_strategy.v1` must therefore include:

```text
initiative_key
initiative_name
```

The exact six V1 shadow rows are:

| work_ref | channel_slug | initiative_key | initiative_name |
|---|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `chairman-control-room` | `autonomous-ai-organization` | `Autonomous AI Organization` |
| `WS:AGENT-OS` | `agent-os` | `autonomous-ai-organization` | `Autonomous AI Organization` |
| `WS:RATES-INFLATION-COMMAND` | `rates-inflation` | `global-markets-regimes-risk-command` | `Global Markets, Regimes & Risk Command` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `biocatalyst` | `institutional-company-event-intelligence` | `Institutional Company & Event Intelligence` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `financial-intelligence` | `institutional-company-event-intelligence` | `Institutional Company & Event Intelligence` |
| `WS:STOCK-IDENTITY` | `stock-identity` | `canonical-intelligence-substrate-learning` | `Canonical Intelligence Substrate & Learning` |

Initiative keys are stable strategy identifiers from the protected Linear Initiative architecture. Initiative IDs remain observed live Linear facts and must not be copied into static strategy.

The strategy validator adds these refusal codes:

```text
strategy_missing_initiative_identity
strategy_duplicate_initiative_key_name_mismatch
strategy_unknown_initiative_key
strategy_initiative_name_mismatch
```

---

## 3. Workroom eligibility comes from the existing Agent OS → Linear desired-state compiler

The original design could be misread as asking the Workroom planner to infer canonical eligibility from live Linear status. That is forbidden.

Current Macro `scripts/linear_portfolio_plan.py` already owns the deterministic zero-network `linear_portfolio_plan.v1` contract and derives:

```text
active_projects
review_candidates
excluded_projects
warnings
semantic_hash
```

from direct Agent OS workstream records, with canonical active statuses:

```text
active
blocked
awaiting_ci
awaiting_review
```

and excluded statuses:

```text
done
parked
killed
```

The Project Workroom planner must consume that existing `linear_portfolio_plan.v1` output as an explicit input. It must not reparse Agent OS, duplicate status law, majority-vote sources or use Linear `In Progress` as canonical eligibility.

### 3.1 Correct input set

The pure planner consumes:

```text
mastermind.project_workroom_strategy.v1
linear_portfolio_plan.v1
mastermind.project_workroom_linear_snapshot.v1
mastermind.project_workroom_slack_snapshot.v1
```

The existing portfolio plan supplies canonical workstream/project desired state. The Linear snapshot supplies observed remote Project/Initiative/resource state only. The Slack snapshot supplies observed remote Workroom/surface state only.

### 3.2 Correct compiler interface

Supersede the three-input signature in the implementation plan with:

```python
def compile_project_workroom_plan(
    *,
    strategy: Mapping[str, object],
    portfolio_plan: Mapping[str, object],
    linear_snapshot: Mapping[str, object],
    slack_snapshot: Mapping[str, object],
    generated_at: str,
) -> dict[str, object]: ...
```

The CLI adds one required argument:

```text
--portfolio-plan <linear_portfolio_plan.v1 path>
```

The emitted Workroom plan adds:

```text
portfolio_plan_semantic_hash
portfolio_plan_digest
```

and includes the portfolio plan digest in its own deterministic digest.

### 3.3 Eligibility behavior

For each strategy `work_ref`:

- exactly one row in `active_projects` → organizationally eligible for shadow planning, subject to target-specific warnings and live Linear/Initiative checks;
- exactly one row in `review_candidates` → `portfolio_workstream_requires_review`, no live Workroom action;
- exactly one row in `excluded_projects` → `portfolio_workstream_ineligible` with exact canonical status, no channel creation/reactivation;
- absent from all three collections → `portfolio_workstream_missing`;
- present more than once or across collections → `portfolio_workstream_ambiguous`.

A parked BioCatalyst row in static strategy therefore remains useful as a negative-control/shadow candidate but cannot create a live active Workroom until canonical Agent OS state is independently reactivated and the existing portfolio plan places it in `active_projects`.

### 3.4 Target-specific portfolio warnings

A portfolio warning that names the target `workstream_key` is projected into the Workroom row. These warning families hold live apply until reconciled:

```text
existing_project_binding_missing
existing_project_binding_ambiguous
project_name_drift
project_status_drift
project_lifecycle_drift
generated_state_disagrees_with_direct_record
typed_gate_source_missing
```

Shadow output remains allowed and must show `portfolio_warning_hold` plus the exact underlying warning codes. No Workroom planner mutates Agent OS or Linear to remove the warning.

Global malformed/refused portfolio-plan state is a hard plan failure.

---

## 4. Linear snapshot is observation only

`mastermind.project_workroom_linear_snapshot.v1` rows may include:

```text
project_id
work_ref
name
status_name
status_type
initiative_ids
initiative_keys
initiative_names
resource_links
updated_at
observation_hash
```

They must not contain a caller-authored `canonical_status`, `runtime_state`, `worker_state`, `completion`, `eligible_for_workroom` or similar privileged interpretation.

The planner compares observed Linear state with:

- exact Project identity and desired fields from `linear_portfolio_plan.v1`; and
- exact Initiative key/name from Workroom strategy.

Observed Linear `In Progress` cannot override a parked/done canonical workstream. Empty Initiative membership while the concurrent Initiative rollout remains incomplete yields `initiative_rollout_unavailable`, not an invented parent.

Add these refusal/degradation codes:

```text
portfolio_plan_wrong_schema
portfolio_plan_hash_mismatch
portfolio_workstream_missing
portfolio_workstream_ambiguous
portfolio_workstream_requires_review
portfolio_workstream_ineligible
portfolio_warning_hold
linear_project_desired_state_drift
initiative_key_missing
initiative_key_ambiguous
initiative_name_mismatch
control_room_resource_missing
```

---

## 5. Current read-only estate evidence

Fresh connected reads during this correction found:

```text
Linear Initiatives visible: 0
Linear Projects in the six shadow strategy rows: all 6 exist
Initiative parents on those Projects: empty
Slack channels matching `proj-*`: 0
```

This is observation evidence only and can change immediately when the concurrent Initiative carrier applies its accepted plan.

The correct current shadow result is therefore not six unqualified channel creates. It is six source-attributed rows whose live actions are held by `initiative_rollout_unavailable`; additional target-specific portfolio warnings may also hold rows. The planner must reproduce this honestly from explicit input documents.

The Initiative session remains the exclusive modifying owner. PR #232 and WR-P0 perform zero Initiative mutation.

---

## 6. WR-P0 test and file-plan corrections

The WR-P0 file set remains unchanged. Tests and CLI behavior are corrected as follows.

### 6.1 Strategy tests

In addition to prior assertions, require exact `initiative_key` and `initiative_name` values from Section 2.

### 6.2 Portfolio-plan tests

Add RED-first cases for:

```text
wrong schema
semantic hash mismatch
same work_ref in active + excluded
active project positive path
review candidate hold
parked/done/killed exclusion hold
target-specific warning hold
unrelated warning does not contaminate another work_ref
Linear In Progress cannot override excluded canonical status
```

### 6.3 CLI tests

The CLI requires `--portfolio-plan`. Its output digest changes when and only when the semantic portfolio-plan input changes. Malformed/refused portfolio input exits 3 without replacing an existing output. A valid plan with target holds exits 2 and writes the evidence document.

### 6.4 Shadow evidence

The committed research packet includes the exact `linear_portfolio_plan.v1` input or an immutable repository path + digest/source revision sufficient to reproduce it. Do not copy Agent OS source records into the Workroom evidence directory.

---

## 7. No other change

All remaining Workroom hierarchy, Sol Project Steward model, operator isolation, Slack principal split, Canvas/List/workflow law, one-carrier/effect-unknown behavior, security boundaries, rollout stages, failure matrix and acceptance canaries remain unchanged.

This amendment does not make the Initiative rollout, Linear Projector, Workroom Projector, multi-workroom Relay, selected Issue projection, Steward integration or any live Workroom accepted/built.