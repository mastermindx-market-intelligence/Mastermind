# Project Workroom WR-P0 — Current-Estate Reference Composition

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Parent operation:** `mastermind-project-workroom-fabric-20260829-sol-001`  
**WR-R0 operation:** `mastermind-project-workroom-wr-r0-20260829-sol-001`  
**Canonical architecture carrier:** Mastermind #240  
**Research carrier:** Mastermind #242  
**Capability state:** `REFERENCE COMPOSITION / RECORDS ONLY / ZERO MUTATION`

This record freezes the expected semantic shape of the first real WR-P0 shadow plan from current source-attributed evidence. It is an implementation target and hostile regression corpus, not a generated plan, Slack/Linear mutation, lifecycle source or authorization to START WR-P0.

The primary falsifier is:

> With current evidence, a correct planner emits **zero authoritative Workroom create/update actions** and **zero apply-eligible rows**, despite six exact Linear Projects and six static policy selections.

Any implementation that calls the current estate green enough to create or adopt a channel fails the architecture.

---

## 1. Exact input composition

### 1.1 Static policy

The exact six policy rows are:

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

Current direct Agent OS / `linear_portfolio_plan.v1` expectation at Macro main `29a88aaa2caa3aa28c93644cedd9d6c0f3c938ca`:

| responsibility_ref | canonical state | Project-plan collection |
|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `active` | `active_projects` |
| `WS:AGENT-OS` | `active` | `active_projects` |
| `WS:RATES-INFLATION-COMMAND` | `awaiting_ci` | `active_projects` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `parked` | `excluded_projects` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `active` | `active_projects` |
| `WS:STOCK-IDENTITY` | `active` | `active_projects` |

BioCatalyst is the required negative control. Linear projects it as `In Progress`; that projection cannot reactivate the canonical parked Project.

### 1.3 Exact live Linear Project resources

The six objects below were re-read directly from Linear at `2026-08-29T19:23:08-04:00`. URLs are exact object-return values. They are not reconstructed from workstream key, title, Project ID or an earlier slug.

| responsibility_ref | Project ID | exact observed Project URL |
|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `0cd5fc91-db1d-4f18-a3d1-3a3a4433f226` | `https://linear.app/mastermindx/project/wschairman-control-room-chairman-control-room-d16bb6189090` |
| `WS:AGENT-OS` | `3e16680c-5549-485d-a056-e07d69eaaf43` | `https://linear.app/mastermindx/project/wsagent-os-mastermind-agent-os-9481d4d2ca74` |
| `WS:RATES-INFLATION-COMMAND` | `ef62f66d-d4c2-4b46-9b48-13722dd57a65` | `https://linear.app/mastermindx/project/wsrates-inflation-command-rates-and-inflation-command-9cae11cd2296` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `4c6706cb-edff-48f2-abcd-0c7045f1723b` | `https://linear.app/mastermindx/project/wsbiocatalyst-core-product-biocatalyst-core-product-98a65ee3d43a` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `2bbb6e6b-8394-4c35-8089-2fd673560e99` | `https://linear.app/mastermindx/project/wsfinancial-intelligence-fabric-financial-intelligence-fabric-0648e0cdeb4c` |
| `WS:STOCK-IDENTITY` | `bbc7fd3f-c98b-47f9-9edb-8a6d749545a5` | `https://linear.app/mastermindx/project/wsstock-identity-stock-identity-50dc2f74951e` |

The exact fixture is:

```text
tests/fixtures/project_workroom_fabric/project_workroom_resource_snapshot.v1.json
```

Its exact observation hash is:

```text
4464bdf459e3d795aaca6305baad016ecbbf03511d58704ea9748eb75aaef18a
```

The hash is reproducible through the existing Project-plan owner rather than a second digest definition:

```python
sha256(
    scripts.linear_portfolio_plan.canonical_bytes(
        resource_snapshot_without_observation_hash
    )
).hexdigest()
```

That canonical byte contract is sorted compact UTF-8 JSON plus one trailing newline. Coverage and resource rows are sorted and duplicate-free; the coverage set equals the exact responsibility-row set. Every Linear source ref is exactly `linear.project:<project_id>`.

Current Control Room resource state for every row is:

```text
control_room_url        = null
control_room_source_ref = null
```

No Workroom-safe route is canonically published. Private provider/chat surface bindings, localhost, guessed public paths and generic Control Room URLs remain forbidden.

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

Fresh connected Linear observation remains:

```text
Initiative objects       = 0
visible Projects         = 50
Initiative memberships   = 0
```

Every otherwise active row is held on `initiative_rollout_pending`; BioCatalyst is excluded independently.

### 1.5 Slack state

The exact normalized snapshot is:

```text
tests/fixtures/project_workroom_fabric/slack_workspace_snapshot.v1.json
```

It is acting-principal-visible plus one exact channel readback and is explicitly incomplete for authoritative public-channel absence proof:

```text
complete_for_public_channel_absence_proof = false
public_absence_proof_allowed              = false
mutation_allowed                          = false
```

No exact valid managed Workroom marker exists.

The exact object:

```text
C0BTQ71QEA0 / canary-project-workroom-20260829
```

is present in the snapshot with `managed_marker = null`. It is `INERT / UNMANAGED / NOT A WORKROOM` and cannot be adopted, retried, archived or bound by name.

Therefore no row may emit an authoritative `would_create_channel`.

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

A changed responsibility byte must change the derived ref or fail exact `WS:<KEY>` validation. Whitespace trim, case-fold, title substitution or Unicode normalization is not permitted.

---

## 3. Target-specific Project drift

All six live Linear display names differ from the current direct Agent OS-derived desired names.

| responsibility_ref | live Linear name | direct desired name |
|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `WS:CHAIRMAN-CONTROL-ROOM — Chairman Control Room` | `WS:CHAIRMAN-CONTROL-ROOM — Chairman Control Room — cross-session navigation and active dialogue` |
| `WS:AGENT-OS` | `WS:AGENT-OS — Mastermind Agent OS` | `WS:AGENT-OS — Mastermind Agent OS — organizational knowledge and work-identity plane` |
| `WS:RATES-INFLATION-COMMAND` | `WS:RATES-INFLATION-COMMAND — Rates & Inflation Command` | `WS:RATES-INFLATION-COMMAND — Rates & Inflation Command plus Macro Release Intelligence completion` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `WS:BIOCATALYST-CORE-PRODUCT — BioCatalyst Core Product` | `WS:BIOCATALYST-CORE-PRODUCT — BioCatalyst core product — post-P0 clinical/regulatory expansion` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `WS:FINANCIAL-INTELLIGENCE-FABRIC — Financial Intelligence Fabric` | `WS:FINANCIAL-INTELLIGENCE-FABRIC — Mastermind Financial Intelligence Fabric` |
| `WS:STOCK-IDENTITY` | `WS:STOCK-IDENTITY — Stock Identity` | `WS:STOCK-IDENTITY — Bottom-Up Stock Identity & Expert Routing` |

Expected warning for every row:

```text
project_name_drift
```

BioCatalyst additionally carries:

```text
project_lifecycle_drift
portfolio_workstream_ineligible
```

Warnings are target-specific. One row cannot contaminate another, and WR-P0 never repairs Linear.

---

## 4. Expected row composition

Common hold set for the five active/awaiting-ci rows:

```text
project_name_drift
initiative_rollout_pending
slack_snapshot_incomplete
control_room_resource_missing
shadow_mode_no_apply
```

Every row has:

```text
planning_eligible = false
apply_eligible    = false
normal_actions    = []
```

| responsibility_ref | workroom_ref | collection | canonical status | Linear Project ID | additional holds |
|---|---|---|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `wr-8fdc7fb3bdae1c694ce522b3` | `active_projects` | `active` | `0cd5fc91-db1d-4f18-a3d1-3a3a4433f226` | none |
| `WS:AGENT-OS` | `wr-aa1bd585243fcb2db1938cfc` | `active_projects` | `active` | `3e16680c-5549-485d-a056-e07d69eaaf43` | none |
| `WS:RATES-INFLATION-COMMAND` | `wr-510a335cc5b0df7e080b14b9` | `active_projects` | `awaiting_ci` | `ef62f66d-d4c2-4b46-9b48-13722dd57a65` | none |
| `WS:BIOCATALYST-CORE-PRODUCT` | `wr-63717024397c13fdd9250c8d` | `excluded_projects` | `parked` | `4c6706cb-edff-48f2-abcd-0c7045f1723b` | `portfolio_workstream_ineligible`, `project_lifecycle_drift` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `wr-fd40cba30a993c1a107f3dab` | `active_projects` | `active` | `2bbb6e6b-8394-4c35-8089-2fd673560e99` | none |
| `WS:STOCK-IDENTITY` | `wr-038719a79b2e84378056b340` | `active_projects` | `active` | `bbc7fd3f-c98b-47f9-9edb-8a6d749545a5` | none |

BioCatalyst also receives the common hold set. Linear `In Progress` is projection drift, not reactivation authority. No channel, Canvas, Radar or bookmark action is legal.

The exact safe Linear resource exists for every row, but no bookmark action is emitted while the row is otherwise held. A future plan schema may expose non-executable candidate detail only if tests distinguish it from action output and never lower a hold or grant apply eligibility.

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

Minimum row-attributed counts:

```text
project_name_drift              = 6
initiative_rollout_pending      = 6
slack_snapshot_incomplete       = 6
control_room_resource_missing   = 6
shadow_mode_no_apply            = 6
portfolio_workstream_ineligible = 1
project_lifecycle_drift         = 1
```

A plan may also expose a deduplicated plan-level source outage, but it may not erase affected rows or reduce any hold.

---

## 6. Hostile mutations this composition must kill

```text
Linear In Progress makes BioCatalyst eligible
missing Initiatives are treated as empty-success
incomplete Slack census is treated as channel absence
inert C0BTQ71QEA0 is adopted by name
Linear URL is reconstructed rather than consumed from exact object readback
stale or mismatched Project URL is accepted because the Project ID matches
Control Room URL is guessed from localhost or private provider binding
project_name_drift is silently repaired or ignored
SHADOW becomes apply authority
a warning on one row blocks or mutates an unrelated row
rows with holds still emit executable actions
input row ordering changes semantic digest
resource observation hash is accepted when canonical bytes disagree
canonical digest omits the existing owner’s trailing-newline byte contract
```

---

## 7. Completion boundary

This reference composition is complete when future WR-P0 RED-first tests reproduce its rows, holds, exact resources and zero-action summary from normalized fixtures.

It does not make WR-P0 built, a snapshot current forever, a Workroom eligible, a Linear Project canonical, a Slack channel managed or a production action authorized.
