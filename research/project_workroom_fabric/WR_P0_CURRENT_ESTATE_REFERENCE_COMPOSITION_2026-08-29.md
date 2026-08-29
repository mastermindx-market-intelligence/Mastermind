# Project Workroom WR-P0 — Current-Estate Reference Composition

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Parent operation:** `mastermind-project-workroom-fabric-20260829-sol-001`  
**WR-R0 operation:** `mastermind-project-workroom-wr-r0-20260829-sol-001`  
**Canonical architecture carrier:** Mastermind #240  
**Research carrier:** Mastermind #242  
**Capability state:** `REFERENCE COMPOSITION / RECORDS ONLY / ZERO MUTATION`

This record freezes the expected semantic shape of the first real WR-P0 shadow plan from current source-attributed evidence. It is an implementation target and hostile regression corpus, not a generated plan, Slack/Linear mutation, source of lifecycle truth, or authorization to START WR-P0.

The primary falsifier is:

> With current evidence, a correct planner emits **zero authoritative Workroom create/update actions** and **zero apply-eligible rows**, despite six exact Linear Projects and six static policy selections.

Any implementation that calls the current estate green enough to create a channel fails the architecture.

---

## 1. Input composition

### 1.1 Static policy

Exact policy rows:

```text
WS:CHAIRMAN-CONTROL-ROOM
WS:AGENT-OS
WS:RATES-INFLATION-COMMAND
WS:BIOCATALYST-CORE-PRODUCT
WS:FINANCIAL-INTELLIGENCE-FABRIC
WS:STOCK-IDENTITY
```

Every row is:

```text
visibility_policy = PUBLIC_INTERNAL
rollout_mode       = SHADOW
```

Core surfaces:

```text
CHANNEL
HOME_CANVAS_STATIC
LINEAR_PROJECT_BOOKMARK
CONTROL_ROOM_BOOKMARK
```

Optional surface:

```text
RADAR_LIST
```

### 1.2 Direct canonical Project state

Current direct Agent OS / `linear_portfolio_plan.v1` expectation:

| responsibility_ref | canonical state | Project-plan collection |
|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `active` | `active_projects` |
| `WS:AGENT-OS` | `active` | `active_projects` |
| `WS:RATES-INFLATION-COMMAND` | `awaiting_ci` | `active_projects` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `parked` | `excluded_projects` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `active` | `active_projects` |
| `WS:STOCK-IDENTITY` | `active` | `active_projects` |

BioCatalyst is a required negative control. Linear currently projects it as `In Progress`; that projection cannot reactivate the canonical parked Project.

### 1.3 Live Linear Project bindings

| responsibility_ref | Project ID | observed Project URL |
|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `0cd5fc91-db1d-4f18-a3d1-3a3a4433f226` | `https://linear.app/mastermindx/project/ws:chairman-control-room-chairman-control-room-6c813b5d815d` |
| `WS:AGENT-OS` | `3e16680c-5549-485d-a056-e07d69eaaf43` | `https://linear.app/mastermindx/project/ws:agent-os-mastermind-agent-os-97b24b0deaa0` |
| `WS:RATES-INFLATION-COMMAND` | `ef62f66d-d4c2-4b46-9b48-13722dd57a65` | `https://linear.app/mastermindx/project/ws:rates-inflation-command-rates-and-inflation-command-b20f1395473c` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `4c6706cb-edff-48f2-abcd-0c7045f1723b` | `https://linear.app/mastermindx/project/ws:biocatalyst-core-product-biocatalyst-core-product-1a64bcf3f058` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `2bbb6e6b-8394-4c35-8089-2fd673560e99` | `https://linear.app/mastermindx/project/ws:financial-intelligence-fabric-financial-intelligence-fabric-c63001e9bc5b` |
| `WS:STOCK-IDENTITY` | `bbc7fd3f-c98b-47f9-9edb-8a6d749545a5` | `https://linear.app/mastermindx/project/ws:stock-identity-stock-identity-3b74816066e9` |

All six URLs are exact observed source values. They are not reconstructed from title or Project ID.

### 1.4 Initiative state

Expected Initiative mappings are exact and strategy-valid:

| responsibility_ref | initiative_key | initiative_name |
|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `autonomous-ai-organization` | `Autonomous AI Organization` |
| `WS:AGENT-OS` | `autonomous-ai-organization` | `Autonomous AI Organization` |
| `WS:RATES-INFLATION-COMMAND` | `global-markets-regimes-risk-command` | `Global Markets, Regimes & Risk Command` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `institutional-company-event-intelligence` | `Institutional Company & Event Intelligence` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `institutional-company-event-intelligence` | `Institutional Company & Event Intelligence` |
| `WS:STOCK-IDENTITY` | `canonical-intelligence-substrate-learning` | `Canonical Intelligence Substrate & Learning` |

Current live Linear observation:

```text
Initiatives = 0
all six Project initiative memberships = []
```

Therefore every otherwise active row remains held on `initiative_rollout_pending`; BioCatalyst remains excluded independently.

### 1.5 Slack state

Current WR-R0 Slack snapshot is acting-principal-visible only and explicitly incomplete for authoritative public-channel absence proof.

No exact valid managed Workroom marker has been accepted.

The separate exact object:

```text
C0BTQ71QEA0 / canary-project-workroom-20260829
```

exists but is `INERT / UNMANAGED / NOT A WORKROOM` and cannot be implicitly adopted or retried.

Therefore no row may emit an authoritative `would_create_channel`.

### 1.6 Navigation resources

The exact fixture is:

`tests/fixtures/project_workroom_fabric/project_workroom_resource_snapshot.v1.json`

It is complete for the six responsibility refs and carries their exact Linear Project IDs/URLs.

Current Control Room resource state:

```text
control_room_url        = null
control_room_source_ref = null
```

for all six rows because no Workroom-safe route is canonically published.

---

## 2. Literal Workroom identities

```text
WS:CHAIRMAN-CONTROL-ROOM         -> wr-8fdc7fb3bdae1c694ce522b3
WS:AGENT-OS                      -> wr-aa1bd585243fcb2db1938cfc
WS:RATES-INFLATION-COMMAND       -> wr-510a335cc5b0df7e080b14b9
WS:BIOCATALYST-CORE-PRODUCT      -> wr-63717024397c13fdd9250c8d
WS:FINANCIAL-INTELLIGENCE-FABRIC -> wr-fd40cba30a993c1a107f3dab
WS:STOCK-IDENTITY                -> wr-038719a79b2e84378056b340
```

A changed input byte must change the derived ref or fail exact `WS:<KEY>` validation.

---

## 3. Target-specific Project drift

All six current Linear display names differ from current direct Agent OS-derived desired names.

Expected warning for every row:

```text
project_name_drift
```

BioCatalyst additionally carries:

```text
project_lifecycle_drift
portfolio_workstream_ineligible
```

These are target-specific warnings. One row's warning cannot contaminate another row, and no warning may be silently repaired by WR-P0.

---

## 4. Expected per-row composition

### 4.1 Chairman Control Room

```text
responsibility_ref   = WS:CHAIRMAN-CONTROL-ROOM
workroom_ref         = wr-8fdc7fb3bdae1c694ce522b3
canonical_collection = active_projects
linear_project_id    = 0cd5fc91-db1d-4f18-a3d1-3a3a4433f226
planning_eligible    = false
apply_eligible       = false
normal_actions       = []
holds/warnings:
  - project_name_drift
  - initiative_rollout_pending
  - slack_snapshot_incomplete
  - control_room_resource_missing
  - shadow_mode_no_apply
```

The safe Linear resource exists, but no bookmark action is emitted while the row is otherwise held. A future implementation may choose to project candidate sub-actions separately only if the frozen plan schema explicitly distinguishes non-executable candidate detail from action output; it may never make the row apply-eligible.

### 4.2 Agent OS

```text
responsibility_ref   = WS:AGENT-OS
workroom_ref         = wr-aa1bd585243fcb2db1938cfc
canonical_collection = active_projects
linear_project_id    = 3e16680c-5549-485d-a056-e07d69eaaf43
planning_eligible    = false
apply_eligible       = false
normal_actions       = []
holds/warnings:
  - project_name_drift
  - initiative_rollout_pending
  - slack_snapshot_incomplete
  - control_room_resource_missing
  - shadow_mode_no_apply
```

### 4.3 Rates & Inflation Command

```text
responsibility_ref   = WS:RATES-INFLATION-COMMAND
workroom_ref         = wr-510a335cc5b0df7e080b14b9
canonical_collection = active_projects
canonical_status     = awaiting_ci
linear_project_id    = ef62f66d-d4c2-4b46-9b48-13722dd57a65
planning_eligible    = false
apply_eligible       = false
normal_actions       = []
holds/warnings:
  - project_name_drift
  - initiative_rollout_pending
  - slack_snapshot_incomplete
  - control_room_resource_missing
  - shadow_mode_no_apply
```

`awaiting_ci` remains active for portfolio selection but does not prove a Workroom action is ready.

### 4.4 BioCatalyst

```text
responsibility_ref   = WS:BIOCATALYST-CORE-PRODUCT
workroom_ref         = wr-63717024397c13fdd9250c8d
canonical_collection = excluded_projects
canonical_status     = parked
linear_project_id    = 4c6706cb-edff-48f2-abcd-0c7045f1723b
planning_eligible    = false
apply_eligible       = false
normal_actions       = []
holds/warnings:
  - portfolio_workstream_ineligible
  - project_name_drift
  - project_lifecycle_drift
  - initiative_rollout_pending
  - slack_snapshot_incomplete
  - control_room_resource_missing
  - shadow_mode_no_apply
```

Linear `In Progress` is projection drift, not reactivation authority. No channel, Canvas, Radar or bookmark action is legal.

### 4.5 Financial Intelligence Fabric

```text
responsibility_ref   = WS:FINANCIAL-INTELLIGENCE-FABRIC
workroom_ref         = wr-fd40cba30a993c1a107f3dab
canonical_collection = active_projects
linear_project_id    = 2bbb6e6b-8394-4c35-8089-2fd673560e99
planning_eligible    = false
apply_eligible       = false
normal_actions       = []
holds/warnings:
  - project_name_drift
  - initiative_rollout_pending
  - slack_snapshot_incomplete
  - control_room_resource_missing
  - shadow_mode_no_apply
```

### 4.6 Stock Identity

```text
responsibility_ref   = WS:STOCK-IDENTITY
workroom_ref         = wr-038719a79b2e84378056b340
canonical_collection = active_projects
linear_project_id    = bbc7fd3f-c98b-47f9-9edb-8a6d749545a5
planning_eligible    = false
apply_eligible       = false
normal_actions       = []
holds/warnings:
  - project_name_drift
  - initiative_rollout_pending
  - slack_snapshot_incomplete
  - control_room_resource_missing
  - shadow_mode_no_apply
```

---

## 5. Expected summary

```text
policy_workroom_count         = 6
eligible_workroom_count       = 0
apply_eligible_workroom_count = 0
shadow_workroom_count         = 6
held_workroom_count           = 6
normal_action_count           = 0
```

At minimum, warning/hold counts must reflect:

```text
project_name_drift             = 6
initiative_rollout_pending     = 6
slack_snapshot_incomplete      = 6
control_room_resource_missing  = 6
shadow_mode_no_apply           = 6
portfolio_workstream_ineligible = 1
project_lifecycle_drift        = 1
```

Whether an implementation deduplicates truly global source outages into a plan-level issue in addition to row-level source attribution must be frozen in tests; it may not erase which rows are affected or lower any hold.

---

## 6. Hostile mutations this composition must kill

```text
Linear In Progress makes BioCatalyst eligible
missing Initiatives are treated as empty-success
incomplete Slack census is treated as channel absence
inert C0BTQ71QEA0 is adopted by name
exact Linear URL is reconstructed rather than consumed
Control Room URL is guessed from localhost or private provider binding
project_name_drift is silently repaired or ignored
SHADOW becomes apply authority
a warning on one row blocks or mutates an unrelated row
rows with holds still emit executable actions
input row ordering changes semantic digest
resource observation hash is accepted when semantic bytes disagree
```

---

## 7. Completion boundary

This reference composition is complete when future WR-P0 RED-first tests can reproduce its rows, holds and zero-action summary from normalized fixtures.

It does not make WR-P0 built, a snapshot current forever, a Workroom eligible, a Linear Project canonical, a Slack channel managed or a production action authorized.
