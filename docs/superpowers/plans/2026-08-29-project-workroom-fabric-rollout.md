# Project Workroom Fabric — Slack + Linear Rollout Implementation Plan

> **For agentic workers:** use `superpowers:test-driven-development` before production code and `superpowers:verification-before-completion` before any completion claim. Every modifying wave remains independently commissioned, exact-carrier bound, reviewed and explicitly continued/stopped under current Skillpack law.

**Goal:** Make selected Linear Projects operate through coherent Slack Project Workrooms—managed Home, Radar, resources, workflows and exact operation threads—while Agent OS, Executive OS, GitHub, RuntimeBinding and OCR-6 Steward remain the canonical organizational/runtime/proof/continuity owners.

**Architecture:** Add one deterministic Workroom projection seam and one least-privilege Slack Workroom Projector app; evolve the existing Agent Relay from one fixed channel to an exact allowlisted Workroom set; join selected Linear Issues and operation threads through existing MAS-189/AD-DLG2 owners; project accepted Steward facts into managed Workroom surfaces. No new lifecycle, queue, project DB, session registry, retry store, watcher plane, memory plane, synchronizer or canonical truth store is introduced.

**Spec:** `docs/superpowers/specs/2026-08-29-project-workroom-fabric-design.md`

**Operation key:** `mastermind-project-workroom-fabric-20260829-sol-001`

## Current source and owner boundaries

- Protected Mastermind at authoring: `229aebce5e8d0c1c7372f5fead9c24516b027cc1`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.
- Current Macro archaeology pin at authoring: `4c597d851cc01bce9f186a7654e9c266c76da657`.
- Existing organizational parent: `WS:CHAIRMAN-CONTROL-ROOM`; do not mint another workstream or `Slack OS`.
- Mastermind #212 is the independently active autonomous-delegation/continuity DAG. Do not edit its branch from this carrier. Workroom integration consumes AD-CHILD1, AD-DLG2, AD-RET*, AD-SOL1, AD-FLEET1 and AD-CR1 through explicit dependency joins.
- The concurrent Linear Initiative carrier owns Initiative creation/membership/readback. Do not create or reclassify Initiatives here.
- Existing Agent OS -> Linear Project compiler/app-actor/apply and MAS-189 Issue/update promotion remain the only Linear mutation path.
- Existing Agent Relay remains the only operation-dialogue transport. A dedicated Workroom Projector app owns presentation provisioning only.
- OCR-6 Executive Steward/Control Room remains the only cross-owner responsibility/attention/runtime/blocker compositor.
- Existing started/effect-unknown Slack threads remain where they started. Workroom cutover applies to new operations after each work class is promoted.

## Program capability ledger

```text
WR-F0 records architecture/plan                  SPEC_ONLY
WR-R0 platform/API/estate falsifier              NOT_BUILT
WR-P0 pure desired-state planner                 NOT_BUILT
WR-A0 Workroom Projector contract/client         NOT_BUILT
WR-A1 app actor + credential boundary             NOT_BUILT
WR-C0 inert Slack canary                         NOT_BUILT
WR-SURF1 Home/Radar managed surfaces             NOT_BUILT
WR-D0 Agent Relay multi-workroom allowlist       NOT_BUILT
WR-D1 correct-workroom dialogue parent join      NOT_BUILT / owned with AD-DLG2
WR-L0 Linear Project/Issue/workroom join          NOT_BUILT / owned with MAS-189
WR-STEW Steward -> Workroom projection            NOT_BUILT
WR-WF structured Workflow intake                 NOT_BUILT
WR-P1 three-Project pilot                        NOT_BUILT
WR-S0 adversarial multi-agent stress matrix      NOT_BUILT
WR-P2 small fleet                                NOT_BUILT
WR-CUTOVER executive-first/full-fabric cutover   NOT_BUILT
```

## Dependency graph

```text
WR-F0 protected records
   |
   +--> WR-R0 platform/API/estate falsifier
   |      |
   |      +--> WR-P0 pure plan compiler
   |      |      |
   |      |      +--> WR-A0 Slack Workroom Projector client
   |      |              |
   |      |              +--> WR-A1 app/credential boundary
   |      |                      |
   |      |                      +--> WR-C0 inert channel canary
   |      |                              |
   |      |                              +--> WR-SURF1 Home/Radar surfaces
   |      |
   |      +--> WR-WF workflow capability decision
   |
   +--> current Agent Relay source + enrollment/live canary
   |      |
   |      +--> WR-D0 multi-workroom allowlist
   |
   +--> AD-CHILD1 + AD-DLG2
   |      |
   |      +--> WR-D1 exact correct-workroom parent ensure
   |
   +--> normalized Linear Project/Initiative readback
   |      + existing MAS-64/MAS-66/MAS-189
   |      |
   |      +--> WR-L0 Project/Issue/workroom links
   |
   +--> OCR-6 Steward accepted read composition
          |
          +--> WR-STEW managed Home/Radar payloads

WR-C0 + WR-SURF1 + WR-D0 + WR-D1 + WR-L0 + WR-STEW
   -> WR-P1 three-Project pilot
   -> WR-S0 adversarial stress matrix
   -> WR-P2 small fleet
   -> WR-CUTOVER
```

No dependency arrow implicitly authorizes the downstream wave.

---

## Task 0: Protect the Project Workroom architecture and plan

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Existing carrier only:**

```text
branch: sol/project-workroom-fabric-20260829
operation: mastermind-project-workroom-fabric-20260829-sol-001
```

**Files:**

- `docs/superpowers/specs/2026-08-29-project-workroom-fabric-design.md`
- `docs/superpowers/plans/2026-08-29-project-workroom-fabric-rollout.md`

**Route:** Sol records/source-law ownership. No worker required.

- [ ] Re-pin protected Mastermind and same-SHA Skillpack before final review.
- [ ] Verify current branch diff is exactly the two records files above.
- [ ] Verify #212, Linear Initiative, Agent Relay, Linear projector, OCR-6, Capacity and current CTO branches were not modified.
- [ ] Run `git diff --check` equivalent and repository required `test` workflow.
- [ ] Self-review for placeholders, contradictions, duplicate owner creation, unfrozen authority and impossible API assumptions.
- [ ] Open one DRAFT PR titled `[ARCHITECTURE][PLAN] Project Workroom Fabric`.
- [ ] Post one coordination pointer to #212 and `#mastermind-exec-ops`; do not edit #212 branch.
- [ ] Require fresh exact-head/current-base CI and final Sol source-law review.
- [ ] Merge only the exact reviewed two-file head under repository protection.

**Acceptance:** protected records make the architecture recoverable. Truth after merge remains `SPEC_ONLY / RECORDS_ONLY`; no Slack/Linear/runtime capability exists.

**Stop:** material protected-source collision -> reconcile this same branch/PR; no replacement carrier.

---

## Task 1: WR-R0 — Slack/Linear platform and current-estate falsifier

**Observable mission:** produce one current, source-attributed readiness matrix proving exactly which Slack channel/Canvas/List/tab/bookmark/Workflow and Linear Project-channel capabilities can be operated safely in the real workspace, with zero mutation and zero secret exposure.

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Files:**

- Create: `research/project_workroom_fabric/PLATFORM_CAPABILITY_CENSUS_2026-08-29.md`
- Create: `research/project_workroom_fabric/slack_surface_contract_snapshot_2026-08-29.json`
- Create: `tests/fixtures/project_workroom_fabric/slack_workspace_snapshot.v1.json`

**Route:** `CTO Sol` or `Terra` for bounded API/security archaeology after source freeze.  
**Why:** exact Slack API/app-scope and current-estate analysis is technically demanding but bounded.  
**Why not Fable:** product/authority architecture is frozen; principal continuity is unnecessary.

### Inputs

- official Slack/Linear API/admin documentation current at execution;
- current Slack workspace/channel inventory, app inventory and non-secret scope/permission metadata;
- current Linear workspace/project/Initiative readback;
- current Agent Relay app/client/enrollment source;
- current connected ChatGPT Slack/Linear tool surface as a convenience witness only.

### Required census

- [ ] Enumerate exact current Slack channels relevant to control/dispatch/build/project collaboration, including privacy/archive state.
- [ ] Determine whether a custom Slack app can enumerate/create/rename/archive public and private channels and the exact scopes/admin restrictions.
- [ ] Determine exact supported APIs for Canvas create/read/update/share/attach and managed-section behavior.
- [ ] Determine exact supported APIs for Slack Lists schema/item CRUD, attachment to a channel and app attribution.
- [ ] Determine exact supported APIs for channel tabs/bookmarks/folders and whether any surface is UI-only.
- [ ] Determine Workflow Builder/custom-function/external-trigger capabilities, admin policy and app scopes.
- [ ] Verify custom channel-template creation/edit availability; treat unavailable product features as unavailable, not assumed.
- [ ] Verify official Linear Project Slack channel, update, unfurl, issue-action and synchronized-thread capabilities and controls.
- [ ] Verify global automatic Linear Project channel creation is disabled or can be kept disabled.
- [ ] Verify current Agent Relay and enrollment remain single-channel and identify exact code/config/scope changes required for allowlisting.
- [ ] Record current privacy/audience risks, especially private Linear content unfurling into public/internal Slack.
- [ ] Record current connector gaps: interactive Slack tools do not constitute the production app contract.

### Closed output

`slack_surface_contract_snapshot_2026-08-29.json` must contain no token, secret, auth code, cookie, raw private payload, provider session ID or customer data. It contains only:

```text
schema
observed_at
workspace_id
capabilities[]
required_scopes[]
admin_requirements[]
unsupported_or_ui_only[]
current_app_identities[]
current_channel_census[]
source_refs[]
```

### Acceptance

- exact capability/method/scope matrix;
- negative proof for every unsupported surface;
- exact V1 core surface set and optional/deferred set;
- no writes and no model-visible secret;
- independent review of privacy and least privilege.

**Stop:** any read requires a secret or admin mutation -> return the exact external gate; do not broaden permissions or install an app.

---

## Task 2: WR-P0 — Pure Workroom policy, identity and desired-state compiler

**Observable mission:** given current Agent OS/Linear/Slack snapshots, deterministically state which selected Workrooms/surfaces should exist and every conflict, with zero network call and zero write.

**Repository:** `mastermindx-market-intelligence/macro`

**Files:**

- Create: `config/project_workroom_policy.v1.json`
- Create: `scripts/project_workroom_plan.py`
- Create: `tests/project_workroom_plan_cases.py`
- Create: `tests/project_workroom_plan_live_cases.py`
- Modify: `.github/ci/legacy-jobs.yml` only if current CI ownership requires explicit suite wiring
- Create evidence fixture: `research/project_workroom_fabric/project_workroom_slack_snapshot_2026-08-29.json`
- Create evidence: `research/project_workroom_fabric/project_workroom_shadow_plan_2026-08-29.json`

**Existing dependency:** import/reuse `scripts.linear_portfolio_plan`; do not reimplement Agent OS selection/name/status law.

**Route:** `Terra`.  
**Why:** standard deterministic Python planning/validation work with a frozen contract.  
**Why not Fable:** no unresolved principal architecture remains.

### Public interfaces

```python
POLICY_SCHEMA = "mastermind.project_workroom_policy.v1"
SLACK_SNAPSHOT_SCHEMA = "mastermind.project_workroom_slack_snapshot.v1"
PLAN_SCHEMA = "mastermind.project_workroom_plan.v1"
RECEIPT_SCHEMA = "mastermind.project_workroom_plan_receipt.v1"
WORKROOM_BINDING_SCHEMA = "mastermind.project_workroom_binding.v1"
WORKROOM_DOMAIN = b"mastermind.project_workroom.v1\x00"

class WorkroomPlanError(RuntimeError):
    failures: tuple[dict[str, object], ...]


def derive_workroom_ref(responsibility_ref: str) -> str: ...
def load_policy(path: Path) -> dict[str, object]: ...
def load_slack_snapshot(path: Path) -> dict[str, object]: ...
def build_workroom_plan(*, agent_state, project_plan, initiative_snapshot, slack_snapshot, policy) -> dict[str, object]: ...
```

`derive_workroom_ref()` returns `wr-` plus the first 24 lowercase hex characters of SHA-256 over `WORKROOM_DOMAIN + exact responsibility_ref UTF-8`.

### Step 1 — RED identity/schema tests

- [ ] literal vectors for at least five `WS:<KEY>` values;
- [ ] case/whitespace changes do not normalize silently;
- [ ] non-`WS:` identity refuses;
- [ ] duplicate `responsibility_ref`, `workroom_ref`, channel slug or managed marker refuses;
- [ ] policy accepts only stable fields and refuses runtime/worker/status/provider/session fields;
- [ ] policy starts with `rollout_mode=SHADOW` and zero production mutation authority.

### Step 2 — RED exact-join tests

- [ ] exact Project binding passes;
- [ ] title-only/fuzzy Project match refuses;
- [ ] missing/duplicate Project refuses;
- [ ] unresolved Initiative is explicit `initiative_rollout_pending`, not inferred;
- [ ] zero/exactly-one/multiple channel marker behavior;
- [ ] renamed channel with same ID/marker remains bound;
- [ ] wrong visibility or malformed marker produces typed failure;
- [ ] parked/done/archive handling preserves history and refuses active/effect-unknown archival.

### Step 3 — Implement policy and planner

Policy rows contain only:

```text
responsibility_ref
promotion_tier
visibility_policy
preferred_channel_slug
surface_set
retention_policy
```

No live Slack IDs are committed in policy. The planner re-derives them from the complete snapshot.

### Step 4 — Determinism/adversarial proof

- [ ] same inputs -> byte-identical sorted JSON and digest;
- [ ] snapshot row order does not change output;
- [ ] duplicate Slack marker cannot be resolved by recency/name;
- [ ] incomplete snapshot refuses rather than assuming missing;
- [ ] remote/manual fields are preserved outside managed markers;
- [ ] no imports that perform network/filesystem writes during planning;
- [ ] mutation tests kill domain/length changes, fuzzy selection, duplicate tolerance, missing-source coercion and runtime fields in policy.

### Step 5 — Current estate shadow plan

After Initiative owner supplies its accepted readback:

- [ ] capture one normalized read-only Slack snapshot;
- [ ] run current Agent OS -> Linear plan;
- [ ] run Workroom planner with production policy still mutation-disarmed;
- [ ] record every `would_create`, `noop`, duplicate, unresolved Project and unsupported surface;
- [ ] do not add real pilot rows until Sol reviews the current shadow output.

**Acceptance:** pure planner is `BUILT_NOT_PROVEN / PRODUCTION_INERT`; zero Slack/Linear writes.

---

## Task 3: WR-A0 — Production-disarmed Workroom Projector contracts and core Slack client

**Observable mission:** one closed, testable client can read and perform only the exact core Workroom channel mutations allowed by an injected plan, while arbitrary/model-selected Slack actions are impossible.

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Gate:** WR-R0 accepted exact core method/scope set; WR-P0 plan schema accepted. No credential or live Slack call.

**Files:**

- Create: `integrations/slack_project_workrooms/__init__.py`
- Create: `integrations/slack_project_workrooms/contracts.py`
- Create: `integrations/slack_project_workrooms/slack_web_api.py`
- Create: `tests/test_slack_project_workroom_contracts.py`
- Create: `tests/test_slack_project_workroom_web_api.py`

**Route:** `CTO Sol`.  
**Why:** security-sensitive external mutation adapter with effect-unknown and exact-target rules.  
**Why not Fable:** architecture and API boundary are frozen by WR-R0.

### Contract

```python
class WorkroomTransportUnavailable(RuntimeError): ...
class WorkroomEffectUnknown(RuntimeError): ...

@dataclass(frozen=True)
class WorkroomActorExpectation:
    workspace_id: str
    app_id: str
    bot_user_id: str | None
    allowed_scopes: tuple[str, ...]

@dataclass(frozen=True)
class WorkroomMutation:
    operation_id: str
    action: Literal["CREATE_CHANNEL", "UPDATE_CHANNEL", "ARCHIVE_CHANNEL"]
    responsibility_ref: str | None
    workroom_ref: str
    expected_observation_hash: str | None
    desired: Mapping[str, object]
```

The exact core HTTP/API methods are the WR-R0 accepted set. The code contains a fixed allowlist; redirects, ambient proxies, unexpected hosts, response shapes, scopes or object IDs refuse.

### RED tests

- [ ] wrong workspace/app/actor/scope refuses before write;
- [ ] arbitrary channel ID/name supplied outside a validated `WorkroomMutation` refuses;
- [ ] unsupported method/path refuses;
- [ ] create/update/archive response validates exact workspace/channel/marker/desired fields;
- [ ] timeout/5xx/malformed success after POST => `WorkroomEffectUnknown`;
- [ ] read failures => unavailable, never effect-unknown;
- [ ] redirect/proxy/oversize/non-JSON/duplicate JSON keys refuse;
- [ ] token never appears in `repr`, exception, receipt or log seam;
- [ ] private/public visibility mismatch refuses;
- [ ] managed marker grammar is exact;
- [ ] no Canvas/List/Workflow action is accepted in this core task.

### GREEN implementation

Implement only the fixed core channel client using injected token/transport. No token discovery, credential enrollment, daemon, persistence, retry queue or live app installation.

**Acceptance:** `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` core adapter; hosted CI/security/mutation review.

---

## Task 4: WR-A1 — Dedicated Workroom Projector app actor and hidden credential boundary

**Observable mission:** one dedicated Slack app identity can be qualified and enrolled through a reviewed no-echo host ceremony without granting Agent Relay/dialogue or broad workspace authority.

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Files:**

- Create: `ops/executive_os/workroom_projector_enrollment.py`
- Create: `scripts/workroom_projector_apply.py`
- Create: `tests/test_workroom_projector_enrollment.py`
- Create: `tests/test_workroom_projector_apply.py`
- Create only if a supervised one-shot host launcher needs it: `ops/executive_os/com.mastermind.executive.workroom-projector.plist.template`

**Gate:** WR-A0 accepted; current H0/credential/host paths proven disjoint; no reuse of Agent Relay token/principal or Linear Projector credential.

**Route:** `CTO Sol`, with independent `Opus` or separate CTO/Terra security review.  
**Why:** fixed host/secret/Slack actor security boundary.  
**Why not Fable:** no principal product ambiguity; use independent premium review rather than principal implementation.

### Required app properties

- exact name `Mastermind Workroom Projector`;
- correct company Slack workspace;
- exact WR-R0 least-privilege scope set;
- no Agent Relay semantic dialogue authority;
- no Executive/Linear/GitHub/provider authority;
- dedicated host principal/config/token ownership selected by current host architecture, never invented from docs;
- disabled/unloaded/no scheduled apply by default;
- clear revocation/rotation path.

### RED security tests

- [ ] production enroll requires native TTY or reviewed hidden-input boundary;
- [ ] pipe/file/stdin misuse refuses before token qualification/mutation;
- [ ] argv/env/temp/log/model-visible secret surfaces refuse;
- [ ] symlink, wrong owner/group/mode, hard-link count, traversal and replacement races refuse;
- [ ] kernel-bound object identity retained through transaction rollback; no `(device,inode)` ABA assumption;
- [ ] existing foreign files/config/app identity refuse; no blind overwrite;
- [ ] qualification validates workspace/app/bot/scopes with bounded read-only API call;
- [ ] enrollment leaves scheduler/service disabled;
- [ ] apply script requires accepted plan schema/digest and exact actor receipt.

### Admin action

Only after implementation/security acceptance, present one exact Chairman/workspace-admin action to create/restrict the app and enter the secret through the hidden ceremony. No secret appears in chat.

### Isolated actor canary

Before Workroom mutation:

- [ ] authenticate/read current workspace and harmless metadata;
- [ ] prove app—not ChatGPT1/2/3 or an employee—is the actor;
- [ ] prove no unrelated app/channel/Linear/GitHub mutation;
- [ ] record non-secret app ID, scope, actor, credential path owner/mode and revocation location.

**Acceptance:** app actor and secret boundary exist; no Project channel yet and no scheduled automation.

---

## Task 5: WR-C0 — Inert core-channel canary

**Observable mission:** the dedicated Workroom Projector creates, reads, updates, no-ops and archives one unmistakably non-production canary channel with exact effect reconciliation and zero Project/runtime meaning.

**Repositories:** Mastermind runtime/app; Macro WR-P0 policy/plan evidence.

**Canary identity:** generated one-time `MMX-WR-CANARY` marker, never a real `WS:<KEY>` binding.

**Route:** Sol release/admin orchestration plus `CTO Sol` technical execution.

### Sequence

- [ ] Capture current complete Slack snapshot and exact actor receipt.
- [ ] Generate one canary plan under `rollout_mode=CANARY` with no real workstream.
- [ ] Apply channel create once.
- [ ] Read back immutable workspace/channel ID, marker, name, visibility and actor.
- [ ] Reapply identical plan; require zero mutation.
- [ ] Make one allowed managed field update with optimistic precondition/readback.
- [ ] Simulate remote manual movement; require `remote_changed` and zero overwrite.
- [ ] Simulate/induce a controlled ambiguous response at the injected transport boundary; require readback and zero duplicate.
- [ ] Prove no `#agent-dispatch`, `#ceo-control-room`, `#mastermind-exec-ops`, Linear, GitHub, Agent OS or Executive mutation.
- [ ] Archive the exact canary after final readback; never delete historical evidence.

**Acceptance:** core channel projection `PROVEN_LIVE` only for isolated canary behavior. No real Workroom or dialogue capability.

---

## Task 6: WR-SURF1 — Managed Home Canvas and Project Radar surface

**Observable mission:** one inert Workroom canary receives a source-separated Home and Radar that update idempotently, preserve manual content and display unknown/degraded state truthfully.

**Gate:** WR-R0 proves exact Canvas/List/tab/bookmark API and workspace support; WR-C0 accepted. Unsupported List/Workflow functionality remains explicit `SURFACE_CAPABILITY_UNAVAILABLE`, not silently treated as complete.

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Files:**

- Create: `integrations/slack_project_workrooms/surfaces.py`
- Create: `control_plane/project_workroom_projection.py`
- Create: `tests/test_slack_project_workroom_surfaces.py`
- Create: `tests/test_project_workroom_projection.py`
- Modify: `scripts/workroom_projector_apply.py`
- Modify: `tests/test_workroom_projector_apply.py`

**Route:** `Terra` for pure projection/surface implementation; separate `CTO Sol` security/adversarial review.

### Public pure projection contract

```python
HOME_SCHEMA = "mastermind.project_workroom_home.v1"
RADAR_SCHEMA = "mastermind.project_workroom_radar.v1"

@dataclass(frozen=True)
class WorkroomSourceFact:
    owner: Literal["agent_os", "linear", "executive_os", "runtime_binding", "github", "wake", "steward"]
    ref: str
    observed_at: str | None
    freshness: Literal["current", "stale", "unknown"]


def build_home_projection(...) -> dict[str, object]: ...
def build_radar_projection(...) -> dict[str, object]: ...
```

### Home tests

- [ ] stable/manual zone and managed zone use exact markers;
- [ ] managed replacement preserves all text outside markers;
- [ ] duplicate/nested/missing markers refuse;
- [ ] current snapshot names source/freshness/unknown reasons;
- [ ] stale Executive/RuntimeBinding cannot show current worker;
- [ ] Linear/GitHub disagreement remains visible;
- [ ] no secret/private raw payload;
- [ ] exact rerun no-op.

### Radar tests

- [ ] required separate `plan_state`, `runtime_state`, `proof_state`, `turn_owner`, `attention_state` fields;
- [ ] no authoritative single status;
- [ ] Slack RESULT/GitHub merge cannot close proof-gated row;
- [ ] child STOP + active parent/no successor becomes `needs_sol`;
- [ ] provider/account changes do not change logical owner;
- [ ] wrong/missing source produces unknown/degraded, not empty healthy;
- [ ] manual note column preserved; managed columns reject remote movement;
- [ ] one sibling result cannot change another row.

### Canary proof

Apply Home/Radar to one inert channel, read back exact IDs/content/schema, repeat no-op, prove remote-edit refusal and archive with canary.

**Acceptance:** each supported surface is individually `PROVEN_LIVE` on inert canary. Unsupported optional surfaces remain typed gaps.

---

## Task 7: WR-D0 — Evolve Agent Relay from one fixed channel to exact allowlisted Workrooms

**Observable mission:** one existing Agent Relay process can read/post only in an injected, current, exact allowlist of approved Workroom channels while preserving all current single-channel behavior and refusing arbitrary model-selected destinations.

**Gate:** current Agent Relay runtime/enrollment/live A2 canary accepted; WR-P0 binding plan and WR-C0 exact channel behavior accepted. Preserve same Agent Relay owner—no second dialogue service/app/token.

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Expected files after fresh collision census:**

- Modify: `integrations/slack_agent_dialogue/slack_web_api.py`
- Modify: `integrations/slack_agent_dialogue/runtime.py`
- Modify: `integrations/slack_agent_dialogue/service.py` only if exact request schema needs trusted channel binding
- Modify: `ops/executive_os/a2_agent_relay_enrollment.py`
- Modify: `tests/test_slack_agent_dialogue_slack_web_api.py`
- Modify: `tests/test_slack_agent_dialogue_runtime.py`
- Modify: `tests/test_slack_agent_dialogue_service.py`
- Modify: `tests/test_a2_agent_relay_enrollment.py`

**Route:** `CTO Sol`.  
**Why:** architecture-sensitive security evolution of current dialogue transport.  
**Why not Fable:** owner/no-rebuild boundary is frozen; one difficult bounded engineering lane is appropriate.

### Compatibility law

- historical/single-channel configuration remains accepted byte/semantic compatible;
- new configuration adds a closed sorted exact set of allowed channel IDs;
- `#agent-dispatch` remains allowed only for uncut legacy operations during transition;
- no channel discovery or selection from model prose;
- channel binding comes from trusted canonical operation/workroom context;
- no per-channel daemon/client/token/app.

### RED tests

- [ ] one allowed channel behaves exactly as current client;
- [ ] two+ allowed channels support distinct threads;
- [ ] channel outside set refuses before API call;
- [ ] duplicate/malformed/oversized channel set refuses;
- [ ] model/request cannot smuggle channel ID into a semantic message;
- [ ] operation bound to Workroom A cannot post in B;
- [ ] same Slack principal can carry separate allowed operations without cross-thread authority;
- [ ] stale Attempt/parent/applicability refuses regardless of allowed channel;
- [ ] config remote movement/reload ambiguity fails closed;
- [ ] Slack timeout on post remains effect-unknown and same target;
- [ ] legacy #agent-dispatch current behavior remains until explicit cutover.

### Production-disarmed integration proof

Use injected fake transport plus the inert canary channel; no real semantic Project operation yet.

**Acceptance:** `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` multi-workroom Relay. Real dialogue proof belongs WR-D1/P1.

---

## Task 8: WR-D1 — Join AD-DLG2 exactly-one parent ensure to the correct Workroom

**Owner:** existing #212 AD-CHILD1/AD-DLG2 carrier(s). This Workroom program does not open a competing dialogue-parent implementation.

**Observable mission:** a selected new operation resolves its deterministic operation identity and exactly one approved Workroom binding, then idempotently ensures one canonical Agent Dialogue V2 parent in that exact channel.

**Integration contract to add under the current AD-DLG2 owner:**

```text
responsibility_ref
workroom_ref
slack_workspace_id
slack_channel_id
linear_project_id
selected_linear_issue_id when available
canonical operation identity
commission provenance
```

### Required tests

- [ ] same operation/workroom observed twice -> one parent;
- [ ] same operation with changed Workroom/channel -> conflict/refuse;
- [ ] duplicate existing parents across channels -> `CARRIER_BINDING_AMBIGUOUS`;
- [ ] missing/duplicate Workroom binding -> zero parent;
- [ ] channel-level parent cannot be authored by arbitrary Sol/worker;
- [ ] Slack create effect-unknown -> exact parent reconciliation, never second parent;
- [ ] Attempt rollover preserves same parent/workroom;
- [ ] existing legacy `#agent-dispatch` parent remains valid for its started operation;
- [ ] Workroom parent does not admit/claim Worker by itself.

### Real proof

One inert/non-modifying dialogue parent canary in the WR-C0 channel, followed by terminal cleanup/STOP. No code-writing worker operation.

**Acceptance:** exactly-one correct-workroom parent behavior is `PROVEN_LIVE` for canary. No project pilot yet.

---

## Task 9: WR-L0 — Linear Project/Issue/Workroom exact-link projection

**Owner:** existing Linear Projector + MAS-189/OSC-C1. No Slack->Linear sync service.

**Observable mission:** normalized Linear Project and selected Issue show the exact Project Workroom and operation thread as navigation/evidence, while Slack/Linear activity cannot infer runtime or completion.

**Gate:** external Initiative rollout accepted; MAS-64/MAS-66 Project projection accepted/applied; MAS-189 architecture/promotion accepted; WR-P0 exact Workroom binding available.

**Expected Macro files after owner review:**

- Modify the current MAS-189 planner/strategy/adapter files selected by that owner; do not create a second planner.
- Add focused tests for Workroom resource links/binding conflict.

### Required behavior

- [ ] Project adds one managed external resource link to exact Workroom channel;
- [ ] Workroom Home links exact Linear Project/Initiative;
- [ ] selected Issue links exact Slack operation thread and GitHub carrier;
- [ ] remote/manual resource movement uses optimistic re-read/refusal;
- [ ] duplicate/mis-parented Issue/thread binding refuses;
- [ ] raw ACK/START/PROGRESS not copied into Linear;
- [ ] accepted blocker/return/review/proof-frontier updates use deterministic dedupe identity;
- [ ] Slack RESULT/GitHub merge cannot auto-Done;
- [ ] Initiative membership remains read-only external owner.

### Canary

Use one inert selected object under a canary Project or the exact approved pilot Project. Prove create/read/noop/remote-change refusal and zero unrelated Linear mutations.

**Acceptance:** exact link/selected update projection accepted; Linear remains projection.

---

## Task 10: WR-STEW — Project Steward Home/Radar composition from accepted OCR-6 facts

**Observable mission:** Workroom Home/Radar can answer who owes the next turn, current runtime, blocker, proof and next action using accepted Steward outputs without querying canonical stores directly or persisting another state view.

**Gate:** OCR-6 Executive Steward read core and gather adapters accepted; WR-SURF1 pure Home/Radar projection accepted.

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Files:**

- Modify: `control_plane/project_workroom_projection.py`
- Modify: `tests/test_project_workroom_projection.py`
- Modify: `integrations/slack_project_workrooms/surfaces.py`
- Modify: `tests/test_slack_project_workroom_surfaces.py`

**Route:** `CTO Sol` or `Terra` depending current OCR-6 complexity; independent reviewer must differ from builder.

### Authority fence

Workroom projection may consume only typed/source-attributed Steward results. It does not import/query Executive DB, Agent OS, GitHub, Slack, Linear, Wake or RuntimeBinding directly.

### Tests

- [ ] responsibility/workroom exact identity required;
- [ ] stale/ambiguous Steward result displays degraded and refuses action affordance;
- [ ] `needs_sol`, `needs_worker_or_coo`, `needs_placement`, `needs_chairman` remain distinct;
- [ ] provider/account/title/recency never elect owner;
- [ ] `EFFECT_UNKNOWN` shows reconciliation-required and no retry control;
- [ ] stale surfaces marked non-actionable;
- [ ] Project Steward is logical role, not Slack user/session;
- [ ] source failure attributed; no last-good refresh laundering;
- [ ] rendering contains no secrets/private locators.

**Acceptance:** one read-only canary projection shows exact current/unknown/degraded states. It performs zero lifecycle/action mutation.

---

## Task 11: WR-WF — Structured Workroom Workflow intake, no direct execution

**Observable mission:** supported Slack Workflow actions emit one closed non-authoritative candidate envelope in the correct Workroom without creating Jobs, assignments, completion or a new inbox/store.

**Gate:** WR-R0 proves current Workflow/custom-function/external-trigger support and app/admin boundary. Unsupported Workflow capability remains an explicit later gap; channel/thread/Home/Radar may proceed independently.

**Repository:** `mastermindx-market-intelligence/Mastermind`

**Files:**

- Create: `integrations/slack_project_workrooms/workflow_contracts.py`
- Create: `tests/test_project_workroom_workflow_contracts.py`
- Add Slack function/manifest files only at exact paths accepted by WR-R0 and current app architecture.

**Schema:**

```text
mastermind.project_workroom_intake.v1
```

Closed `kind` vocabulary:

```text
PROPOSE_WAVE
RAISE_BLOCKER
REQUEST_SOL_REVIEW
REQUEST_DECISION
RECORD_DISCOVERY_CANDIDATE
ESCALATE_CHAIRMAN_ADMIN
```

Required fields:

```text
schema
kind
responsibility_ref
workroom_ref
submitted_by_transport_actor
submitted_at
summary
source_message_ref
related_operation_ref nullable
related_github_ref nullable
```

### Tests

- [ ] exact Workroom binding required;
- [ ] extra fields / action-smuggling / provider/session/channel target fields refuse;
- [ ] `MARK_COMPLETE`, `RETRY`, `ASSIGN_WORKER`, `MERGE`, `DEPLOY` kinds refuse;
- [ ] Workflow submission produces only structured Slack candidate/pointer;
- [ ] no Executive/Agent OS/Linear/GitHub mutation import/path;
- [ ] duplicate same source message yields same candidate identity/no second top-level post where applicable;
- [ ] model text cannot lower authority or convert candidate to admission;
- [ ] private/audience and secret-shaped content refuses/redacts.

### Canary

Submit one inert `REQUEST_SOL_REVIEW` candidate; prove exact structured message, no Job/Issue/completion effect and explicit human/Sol disposition.

**Acceptance:** Workflow intake is useful but noncanonical. There is no `Mark Complete` action.

---

## Task 12: WR-P1 — Select and run the three-Project pilot

**Observable mission:** three normalized, materially active Projects use coherent Workrooms for new operations, with one logical Sol Project Steward and multiple bounded operators visible without false runtime/completion claims.

**Selection gate:** after Initiative/Project normalization and shadow plan, Sol selects exactly three Projects meeting the spec criteria. Do not choose unresolved compatibility redirects, parked work, effect-unknown carriers or privacy-incompatible projects.

**Pilot mix must include:**

1. one operating-system/control-plane Project;
2. one investor-facing intelligence/product Project;
3. one Project with at least two repositories or several evidence types.

**Policy change:** update `config/project_workroom_policy.v1.json` with exactly those `WS:<KEY>` rows and `rollout_mode=PILOT` on a reviewed Macro carrier.

### Per-Project journey

- [ ] exact Agent OS/Linear Project/Initiative binding read back;
- [ ] Workroom dry-run reviewed;
- [ ] channel/Home/Radar/resources created/read back;
- [ ] logical Sol Project Steward shown with exact action target separately;
- [ ] one new selected operation gets exact Linear Issue and correct Workroom parent;
- [ ] worker ACK/START/BLOCKED/RESULT/CONTINUE/STOP stays in thread;
- [ ] GitHub/proof and Steward/Radar update from canonical sources;
- [ ] old `#agent-dispatch` operations remain in place;
- [ ] no false completion or duplicate object;
- [ ] Chairman can navigate Project -> Workroom -> thread/evidence -> Control Room.

### Multi-operator requirement

Across the three pilots, exercise at least:

- one Sol Project Steward supervising three or more distinct operations;
- at least three different operator/worker avenues;
- at least two simultaneous independent roots where AD-FLEET1/current capacity law permits;
- one held same-root/path collision shown truthfully rather than forced concurrent.

**Acceptance:** three Project pilots complete their declared canary operations with zero duplicate effects, wrong-thread continuation, silent orphan or false completion.

---

## Task 13: WR-S0 — Adversarial multi-agent and outage stress matrix

**Observable mission:** prove the Workroom Fabric remains correct under shared principals, duplicate sessions, Sol loss, worker loss, Slack/Linear outages, manual drift and effect uncertainty.

**Repositories:** Mastermind test/harness owner; Macro policy/plan fixtures where needed.

**Route:** `Opus` or `CTO Sol` independent adversarial specialist; builder and reviewer must differ.  
**Why:** reasoning-heavy bounded failure investigation after architecture freeze.  
**Why not Fable:** no sustained principal ambiguity; premium independent falsification is the need.

### Matrix

Run at least the following agent/session scales:

```text
2 concurrent sessions
5 concurrent sessions
14 concurrent sessions
```

### Required cases

- [ ] many distinct operations behind one Slack principal;
- [ ] two sessions claim same operation;
- [ ] two Sol surfaces see one return;
- [ ] exact Sol target dies before ruling;
- [ ] worker dies before effect, after known effect and at effect-unknown boundary;
- [ ] provider/account rollover preserves operation/thread and invalidates stale worker;
- [ ] Slack unavailable during execution and at semantic return boundary;
- [ ] Linear unavailable during projection/apply;
- [ ] duplicate/malformed Workroom markers;
- [ ] channel rename/archive/manual topic change;
- [ ] Canvas/Radar managed-block remote change;
- [ ] duplicate RESULT and late stale reply after STOP;
- [ ] child STOP with active parent/no successor;
- [ ] GitHub merge with open production gate;
- [ ] privacy/audience mismatch;
- [ ] Workroom surface capability unavailable;
- [ ] no eligible capacity / visible `WAITING_CAPACITY`;
- [ ] sibling path/authority collision;
- [ ] effect-unknown channel/parent/resource write.

### Pass criteria

```text
zero duplicate Executive root/child/parent/channel effect
zero stale sanctioned worker action
zero wrong-workroom post
zero silent orphan
zero false Project/Issue completion
zero hidden Chairman account-selection requirement
zero Workroom/Linear/Slack authority promotion
all unknown/degraded/effect-unknown states visible and source-attributed
```

**Acceptance:** exact stress receipt and independent review. Any constitutional failure blocks fleet promotion.

---

## Task 14: WR-P2 — Small Workroom fleet and learning instrumentation

**Observable mission:** ten to fifteen selected Projects operate through Workrooms for a real sustained interval while Control Room remains the normal monitor and Slack is team collaboration/drill-down.

**Gate:** WR-P1 accepted; WR-S0 passes; AD-FLEET1/current Capacity/RuntimeBinding/Wake/return prerequisites accepted for the work classes used.

### Rollout

- [ ] update static policy with exact reviewed Project set;
- [ ] dry-run all desired Workrooms/surfaces;
- [ ] reconcile every duplicate/unresolved/privacy conflict before apply;
- [ ] apply in bounded batches with readback/noop proof;
- [ ] new selected operations use Workrooms; existing carriers remain where they started;
- [ ] every Workroom has current Home/Radar and exact links;
- [ ] no Project receives a channel solely because it exists in Linear.

### Instrumentation

Measure without creating another lifecycle store:

```text
workroom binding drift count
duplicate marker/parent refusal count
unprojected selected work count
wrong-carrier refusal count
median/p95 worker-return -> Sol edge time
median/p95 Sol-continuation -> worker resume time
parent-active/no-successor dwell time
stale Radar/Home detection time
Linear/Slack projection correction count
Chairman manual message shuttles
Chairman routine account selections
Chairman Slack archaeology events
silent orphan count
duplicate effect count
```

Metrics are derived from existing source/evidence owners and bounded experiment receipts. They do not become a new lifecycle database.

### Acceptance

A sustained interval demonstrates:

- useful collaboration across real projects;
- zero hidden starvation/orphans/duplicate effect;
- no need for Chairman to monitor `#agent-dispatch`;
- Workroom drift corrected safely;
- Project teams understand current truth and next action.

---

## Task 15: WR-CUTOVER — Executive-first Project Workrooms and legacy containment

**Observable mission:** ordinary new selected Project operations begin in their exact Project Workroom and appear in Linear/Control Room automatically, while `#agent-dispatch` becomes legacy/forensic transport for uncut historical work only.

**Gate:** small-fleet proof accepted for each promoted work class; full autonomy/Capacity/Steward/attention path accepted for the relevant class.

### Cutover steps

- [ ] freeze exact promoted work classes and date/revision;
- [ ] set Workroom policy `rollout_mode=EXECUTIVE_FIRST` only for those classes;
- [ ] prevent ordinary new top-level project commissions in `#agent-dispatch` for promoted classes;
- [ ] preserve legacy started/effect-unknown threads as read/write until their natural terminal reconciliation;
- [ ] route new selected operation parents to exact Workroom through AD-DLG2;
- [ ] require Linear Issue/workroom/thread projection before/with normal dispatch;
- [ ] keep Control Room/Secretary as Chairman operating cockpit;
- [ ] archive no historical evidence merely for cleanliness;
- [ ] maintain rollback/disarm that stops new Workroom writes without corrupting canonical state.

### Full-fabric acceptance

For a real multi-Project interval, the Chairman:

- states intent once;
- selects no routine provider account;
- copies no worker handoff;
- monitors no `#agent-dispatch` thread;
- repairs no watcher;
- hunts no Sol/worker session;
- reconstructs no project from Slack history;
- sees every genuine `needs_chairman` decision clearly separated from routine work;
- can enter a Workroom when collaboration detail is useful.

**Final capability state:** `PROVEN_LIVE` only for work classes and Project set that pass the exact production proof. Unsupported classes remain on the prior path with explicit state.

---

## Program-wide review and closeout law

After every wave:

- review against the Chairman outcome, not only code;
- pin exact head/base/changed files/CI/security/proof;
- distinguish records, built, installed, armed, canary and production-live states;
- update the correct Agent OS decision/discovery/handoff without creating a new workstream;
- repair Linear only after canonical truth;
- post bounded Slack/coordination visibility;
- explicitly `CONTINUE`, `REQUEST_REPAIR` or terminal `STOP` every watcher-enabled return;
- disarm temporary watchers on STOP or report `WATCH_STOP_FAILED`;
- mint a fresh operation/carrier for every independent successor;
- never let a freed worker/session self-start the next wave.

## Plan completion boundary

This plan is not complete when all code merges. It is complete only when WR-CUTOVER passes the real Chairman experience and adversarial rulers, durable records identify exact proven work classes, and a fresh Sol can recover current state/limits/next action without this conversation.