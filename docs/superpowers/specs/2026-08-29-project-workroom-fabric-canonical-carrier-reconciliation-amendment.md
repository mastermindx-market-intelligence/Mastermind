# Project Workroom Fabric — Canonical Carrier and Planner-Source Reconciliation Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `SPEC_ONLY / CHAIRMAN-AUTHORIZED / RECORDS_ONLY`  
**Canonical operation:** `mastermind-project-workroom-fabric-20260829-sol-001`  
**Canonical carrier:** Mastermind PR #240 / `sol/project-workroom-fabric-20260829`  
**Superseded operation:** `project-workroom-convergence-20260829-sol-001`  
**Superseded carrier:** Mastermind PR #233; closed-unmerged PR #232 remains metadata history only  
**Skillpack compatibility:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Linear:** MAS-231 / MAS-233 / MAS-235 / MAS-236; MAS-220 and MAS-221 are duplicate projections  
**Organizational parent:** existing `WS:CHAIRMAN-CONTROL-ROOM`

This amendment resolves the duplicate Project Workroom architecture families and freezes the exact pure-planner contract. For carrier identity, WR-P0 ownership, input schemas, source provenance, Initiative comparison, resource/navigation evidence, portfolio eligibility, shadow/apply semantics, action emission and supersession, this amendment has narrow precedence over:

- `docs/superpowers/specs/2026-08-29-project-workroom-fabric-design.md`;
- `docs/superpowers/specs/2026-08-29-project-workroom-fabric-wr-r0-amendment.md`;
- `docs/superpowers/plans/2026-08-29-project-workroom-fabric-rollout.md`;
- the five historical records on Mastermind PR #233.

Current protected revisions, merged prerequisites, current carrier heads and release ordering live in:

`docs/superpowers/plans/2026-08-29-project-workroom-current-source-reconciliation.md`.

That current-source record may move without changing this static planner contract. All other accepted Project Workroom outcome, canonical ownership, public-internal V1, least-privilege Slack principal split, exact identity, effect-unknown, no-rebuild, dialogue, Steward, rollout and production-proof laws remain unchanged.

This records amendment creates no Slack channel, app, Canvas, List, Workflow, Linear Initiative/Project/Issue mutation, Agent OS mutation, Executive Job/Attempt/Worker, RuntimeBinding, credential, host effect, service, worker assignment or production capability.

---

## 1. Canonical-carrier ruling

The Project Workroom program has one canonical architecture and rollout carrier:

```text
operation = mastermind-project-workroom-fabric-20260829-sol-001
PR        = Mastermind #240
branch    = sol/project-workroom-fabric-20260829
Linear    = MAS-231 / MAS-233 / MAS-235 / MAS-236
```

The older overlapping family is superseded history:

```text
operation = project-workroom-convergence-20260829-sol-001
PR        = Mastermind #233
Linear    = MAS-220
```

Closed-unmerged #232 remains draft-metadata history only. MAS-221 is also a duplicate program projection and may not originate another carrier.

This ruling is not based on recency alone. #240 is canonical because it includes the stronger current-platform and adversarially reviewed V1:

- projector-created public-internal Workrooms first;
- private Workrooms deferred;
- no implicit channel adoption or `channels:join`;
- static channel-read-only Home Canvas with standalone-plus-bookmark fallback;
- Control Room as dynamic current truth;
- optional app-owned, channel-read-only Radar List with `todo_mode=false`;
- no undocumented native tab, bookmark-folder or channel-template dependency;
- optional/deferred Workflows;
- dedicated Workroom Projector separate from Agent Relay;
- narrow public-channel/Canvas/bookmark/optional-List authority;
- exact Project, Workroom, operation, runtime and proof separation.

#233 contained valid load-bearing planner and source-provenance rulings. This amendment adopts them explicitly before supersession. No valid unique law is discarded.

After the supersession receipt:

- do not reopen #232 or #233;
- do not reuse `project-workroom-convergence-20260829-sol-001`;
- do not implement from #233 file paths or private-by-default assumptions;
- do not create another Workroom architecture carrier;
- use #233 only as historical evidence for the clauses adopted here.

---

## 2. Canonical ownership and capability boundary

The Workroom program changes no canonical owner:

| Fact | Canonical owner |
|---|---|
| workstream/program/wave/decision/discovery/handoff | Agent OS |
| Job/Attempt/Worker/Event, claim, fence, retry/requeue | Executive OS |
| current native target/session/host generation | RuntimeBinding / Operator Continuity |
| implementation, PR, exact head, CI, merge, deploy, proof | GitHub / owning evidence source |
| Initiative, Project and selected Issue human projection | Linear |
| collaboration and exact dialogue transport | Slack / Agent Relay |
| current responsibility, attention, blocker and next-action composition | OCR-6 Executive Steward / Control Room |

The following remain false equivalences:

```text
Slack START or RESULT       != Executive running or completion
Linear In Progress or Done  != Executive running or production acceptance
GitHub merge                != product/production completion
channel membership          != worker assignment or authority
Slack principal             != RuntimeBinding or action-authoritative Sol
Canvas/List content         != canonical current truth
```

Current capability classification remains source-specific:

```text
Workroom architecture / rollout source            SPEC_ONLY
WR-R0 platform/API/current-estate research         RESEARCH / RECORDS_ONLY
WR-P0 pure desired-state compiler                  NOT BUILT
WR-A0 Workroom Projector client                    NOT BUILT
WR-A1 Workroom Projector app/credential boundary  NOT BUILT
WR-C0 accepted inert Slack canary                  NOT BUILT
WR-SURF1 Home/Radar actuator                       NOT BUILT
WR-D0 multi-workroom Relay                         NOT BUILT
WR-D1 correct-workroom parent ensure               NOT BUILT
WR-L0 Linear Project/Issue/workroom join            NOT BUILT
WR-STEW Workroom Steward projection                NOT BUILT
real Project Workroom pilot                        NOT BUILT
small fleet / production cutover                   NOT BUILT
```

Local scratch files, chat summaries, generated receipts, Slack object existence and Linear statuses cannot advance GitHub implementation truth.

---

## 3. WR-P0 ownership and method

WR-P0 is a pure deterministic compiler implemented in `mastermindx-market-intelligence/macro`. It performs zero network calls and zero Slack/Linear writes.

It consumes accepted normalized inputs from existing owners. It does not reparse Agent OS, create Initiatives, decide Project lifecycle, discover Slack channels, invent URLs or maintain a Workroom registry.

The exact schema constants are:

```python
POLICY_SCHEMA = "mastermind.project_workroom_policy.v1"
SLACK_SNAPSHOT_SCHEMA = "mastermind.project_workroom_slack_snapshot.v1"
RESOURCE_SNAPSHOT_SCHEMA = "mastermind.project_workroom_resource_snapshot.v1"
PLAN_SCHEMA = "mastermind.project_workroom_plan.v1"
RECEIPT_SCHEMA = "mastermind.project_workroom_plan_receipt.v1"
WORKROOM_BINDING_SCHEMA = "mastermind.project_workroom_binding.v1"
WORKROOM_DOMAIN = b"mastermind.project_workroom.v1\x00"
```

The controlling interface is:

```python
def build_workroom_plan(
    *,
    project_plan: Mapping[str, object],
    initiative_plan: Mapping[str, object],
    initiative_snapshot: Mapping[str, object],
    slack_snapshot: Mapping[str, object],
    resource_snapshot: Mapping[str, object],
    policy: Mapping[str, object],
) -> dict[str, object]: ...
```

WR-P0 must not:

- parse `agentos/workstreams/**` directly;
- duplicate canonical workstream selection or status law;
- create/update a Linear Initiative, Project or Issue;
- treat Linear status as canonical eligibility;
- infer Initiative membership from names;
- use Slack channel names as identity;
- construct navigation URLs from title, slug, Project ID or responsibility key;
- read private provider/chat surface bindings;
- call a network;
- write Slack or Linear;
- store live IDs or URLs in a new registry;
- decide whether a worker may run.

Deterministic versus model-generated method:

```text
policy validation, identity, joins, warnings, actions and digests = deterministic
model-generated interpretation or authority                       = none
```

---

## 4. Workroom identity

One Workroom projection identity is derived from the exact organizational key:

```python
def derive_workroom_ref(responsibility_ref: str) -> str:
    return "wr-" + hashlib.sha256(
        WORKROOM_DOMAIN + responsibility_ref.encode("utf-8")
    ).hexdigest()[:24]
```

The input must match the accepted exact `WS:<KEY>` grammar. It is not trimmed, case-folded, Unicode-normalized or title-matched.

Literal vectors:

```text
WS:CHAIRMAN-CONTROL-ROOM         -> wr-8fdc7fb3bdae1c694ce522b3
WS:AGENT-OS                      -> wr-aa1bd585243fcb2db1938cfc
WS:RATES-INFLATION-COMMAND       -> wr-510a335cc5b0df7e080b14b9
WS:BIOCATALYST-CORE-PRODUCT      -> wr-63717024397c13fdd9250c8d
WS:FINANCIAL-INTELLIGENCE-FABRIC -> wr-fd40cba30a993c1a107f3dab
WS:STOCK-IDENTITY                -> wr-038719a79b2e84378056b340
```

`workroom_ref` identifies a projection relationship only. It is never an Executive Job, operation, RuntimeBinding, Slack channel, Agent OS record or completion authority.

---

## 5. Static policy contract

The static policy schema is:

```text
mastermind.project_workroom_policy.v1
```

Top-level keys are exactly:

```text
schema
source_records
workspace_id
workrooms
```

Each `workrooms[]` row contains exactly stable presentation strategy:

```text
responsibility_ref
initiative_key
initiative_name
promotion_tier
visibility_policy
preferred_channel_slug
surface_set
retention_policy
rollout_mode
```

The policy must refuse runtime, worker, provider, account, session, attention, retry, completion, Slack channel ID, Linear Project ID, Initiative ID, URL, Job ID, Attempt ID, branch, PR or mutable status fields.

Required hard failures include:

```text
policy_wrong_schema
policy_unknown_key
policy_runtime_field_refused
policy_duplicate_responsibility_ref
policy_duplicate_workroom_ref
policy_duplicate_channel_slug
policy_missing_initiative_identity
policy_unknown_initiative_key
policy_initiative_name_mismatch
policy_private_visibility_refused_v1
policy_non_shadow_initial_corpus_refused
```

### 5.1 Initial six-row shadow corpus

The first policy corpus contains exactly:

| responsibility_ref | preferred_channel_slug | initiative_key | initiative_name |
|---|---|---|---|
| `WS:CHAIRMAN-CONTROL-ROOM` | `chairman-control-room` | `autonomous-ai-organization` | `Autonomous AI Organization` |
| `WS:AGENT-OS` | `agent-os` | `autonomous-ai-organization` | `Autonomous AI Organization` |
| `WS:RATES-INFLATION-COMMAND` | `rates-inflation` | `global-markets-regimes-risk-command` | `Global Markets, Regimes & Risk Command` |
| `WS:BIOCATALYST-CORE-PRODUCT` | `biocatalyst` | `institutional-company-event-intelligence` | `Institutional Company & Event Intelligence` |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | `financial-intelligence` | `institutional-company-event-intelligence` | `Institutional Company & Event Intelligence` |
| `WS:STOCK-IDENTITY` | `stock-identity` | `canonical-intelligence-substrate-learning` | `Canonical Intelligence Substrate & Learning` |

For every row:

```text
visibility_policy = PUBLIC_INTERNAL
rollout_mode       = SHADOW
```

The exact core surface set is:

```text
CHANNEL
HOME_CANVAS_STATIC
LINEAR_PROJECT_BOOKMARK
CONTROL_ROOM_BOOKMARK
```

The optional surface is:

```text
RADAR_LIST
```

Working Notes and Workflow intake are not core WR-P0 promises. They remain separately promoted optional surfaces.

These six rows are calibration candidates, not channel-creation authority. A parked, review-held, missing, ambiguous or warning-held responsibility remains a negative-control row and emits no live create/update action.

---

## 6. Atomic source-provenance law

The policy carries one immutable source set:

```text
source_records:
  repository
  protected_revision
  paths
```

The repository is exactly:

```text
mastermindx-market-intelligence/Mastermind
```

`protected_revision` is the exact 40-lowercase-hex protected merge commit that contains the canonical #240 source set. Until #240 has a protected merge commit, WR-P0 implementation START remains held.

The exact sorted, duplicate-free source paths are:

```text
docs/superpowers/specs/2026-08-29-project-workroom-fabric-canonical-carrier-reconciliation-amendment.md
docs/superpowers/specs/2026-08-29-project-workroom-fabric-design.md
docs/superpowers/specs/2026-08-29-project-workroom-fabric-wr-r0-amendment.md
```

The rollout and current-source plans are execution/current-state records, not static policy authority.

Required failures:

```text
policy_source_records_invalid
policy_source_repository_mismatch
policy_source_revision_invalid
policy_source_paths_mismatch
policy_source_paths_duplicate
```

The compiler must not discover source law by directory scan, filename similarity, newest timestamp or branch name.

---

## 7. Canonical Project-plan input

`linear_portfolio_plan.v1` is the exclusive deterministic Agent OS → Linear Project desired-state owner.

For each policy `responsibility_ref`, WR-P0 resolves exactly one row across:

```text
active_projects
review_candidates
excluded_projects
```

Presence in more than one collection or more than once is ambiguous and refuses.

### 7.1 Active Project

Exactly one row in `active_projects` may be planning-eligible, subject to exact Initiative, resource, Slack and warning checks.

Normal Workroom actions require one exact observed Linear Project ID that agrees across Initiative and resource snapshots. A missing or ambiguous Project binding emits no normal Workroom create/update action.

### 7.2 Review candidate

Exactly one row in `review_candidates` yields:

```text
portfolio_workstream_requires_review
```

and zero normal create/update actions.

### 7.3 Excluded Project

Exactly one row in `excluded_projects` yields:

```text
portfolio_workstream_ineligible
```

and zero channel, Canvas, Radar or bookmark create/update actions.

If an exact already-bound Workroom exists, WR-P0 may emit only:

```text
would_archive_after_acceptance
```

as a non-mutating review candidate. It may not archive or reactivate.

### 7.4 Missing or ambiguous identity

Missing from all Project-plan collections yields:

```text
portfolio_workstream_missing
```

Ambiguity yields:

```text
portfolio_workstream_ambiguous
```

Both emit zero normal actions.

### 7.5 Target-specific warnings

Project-plan warnings naming the exact target are projected into that row and hold normal action:

```text
existing_project_binding_missing
existing_project_binding_ambiguous
project_name_drift
project_status_drift
project_lifecycle_drift
generated_state_disagrees_with_direct_record
typed_gate_source_missing
```

Unrelated warnings do not contaminate another responsibility. A refused or malformed Project plan is a hard WR-P0 failure.

Linear status cannot override Project-plan eligibility. In the initial corpus, `WS:BIOCATALYST-CORE-PRODUCT` is a required negative control: direct Agent OS currently says `parked` while Linear may display `In Progress`; the planner must emit `portfolio_workstream_ineligible` and zero normal actions.

---

## 8. Initiative plan and observed membership

`linear_initiative_plan.v1` is the accepted strategic Initiative desired-state/membership owner. `linear_initiative_snapshot.v1` is normalized observed live Initiative/Project membership readback.

Policy `initiative_key` and `initiative_name` are expected stable strategic identities. Live Initiative IDs remain snapshot facts and never enter static policy.

The planner compares each selected row against both accepted inputs:

- exact key/name/membership agreement → Initiative check passes;
- Initiative objects absent → `initiative_rollout_pending`;
- expected Initiative missing → `initiative_key_missing`;
- more than one match → `initiative_key_ambiguous`;
- name differs → `initiative_name_mismatch`;
- Project membership absent → `initiative_membership_missing`;
- Project belongs to multiple Initiatives → `initiative_membership_ambiguous`;
- wrong Initiative → `initiative_membership_wrong`;
- accepted plan/snapshot digest mismatch → hard refusal.

The Workroom planner never creates or repairs Initiatives or memberships.

If the Initiative compiler is not accepted/protected or the normalized post-apply snapshot is unavailable, WR-P0 may emit a typed evidence hold but may not manufacture readiness.

---

## 9. Slack observed-state input

`mastermind.project_workroom_slack_snapshot.v1` is a complete normalized observation of the public-channel surface required by the policy.

The snapshot is remote evidence only. It is not a channel registry, task database, cursor, lifecycle or mutation plan.

Required behavior:

- incomplete public-channel census → `slack_snapshot_incomplete` and no authoritative create action;
- zero exact managed markers with complete census → channel may be absent;
- exactly one valid marker → immutable channel ID is the binding;
- more than one exact marker → `duplicate_workroom` and zero mutation;
- malformed/conflicting marker → `workroom_marker_invalid`;
- rename with same immutable ID/marker preserves identity;
- channel name is presentation only;
- current bot/app membership and app-owned surface checks are required before explicit existing-channel adoption;
- no implicit adoption or `channels:join`.

The previously created public channel `C0BTQ71QEA0` is `APPLIED / INERT / UNMANAGED / NOT A WORKROOM`. It cannot be retried, implicitly adopted, archived or treated as a passed canary by WR-P0.

---

## 10. Navigation-resource snapshot

WR-P0 receives exact navigation evidence through:

```text
mastermind.project_workroom_resource_snapshot.v1
```

This snapshot is an ephemeral read-only normalized projection from existing owners. It is not a durable registry, identity authority, URL builder, deployment record or mutation plane.

Top-level keys are exactly:

```text
schema
observed_at
workspace_id
complete_for_responsibility_refs
resources
observation_hash
```

`complete_for_responsibility_refs` is a sorted, duplicate-free list. It must exactly cover every policy responsibility for which the snapshot claims complete resource observation.

Each `resources[]` row contains exactly:

```text
responsibility_ref
linear_project_id
linear_project_url
control_room_url
linear_source_ref
control_room_source_ref
```

Value contracts:

```text
responsibility_ref      exact policy/Project-plan WS:<KEY>
linear_project_id       exact observed immutable Linear Project ID or null only when unavailable
linear_project_url      exact observed URL string or null only when unavailable
control_room_url        exact accepted published route or null only when unavailable
linear_source_ref       non-empty source-attribution receipt when Linear fields are present
control_room_source_ref non-empty accepted publication receipt when Control Room URL is present
```

The resource snapshot must not contain:

- provider conversation or browser-seat URLs;
- private `surface_bindings` locators;
- credentials, usernames, passwords, bearer material or cookies;
- inferred URLs built from title, slug, Project ID or responsibility key;
- current Worker/Attempt/runtime/attention/completion state.

### 10.1 Exact joins

For each responsibility:

- exactly one resource row is required when that responsibility is listed as complete;
- duplicate rows → `resource_binding_ambiguous`;
- missing row under a claimed-complete snapshot → `resource_binding_missing`;
- `linear_project_id` must match the normalized Initiative/Project observation;
- mismatch → `resource_project_id_mismatch` and zero bookmark action;
- workspace mismatch → `resource_snapshot_workspace_mismatch`;
- wrong schema/hash → hard refusal.

### 10.2 Safe Linear Project URL

A V1 Linear Project URL is safe only when it is an exact observed source value paired with the exact Project ID and satisfies all of:

```text
scheme = https
host   = linear.app
port   = absent
username/password = absent
query  = absent
fragment = absent
path begins with /mastermindx/project/
```

The URL is never reconstructed from Project ID, title or slug.

Missing Linear URL:

```text
omit would_add_linear_bookmark
emit linear_project_resource_missing
```

Unsafe, credential-bearing, host-mismatched, query-bearing or fragment-bearing Linear URL:

```text
omit action
emit linear_project_resource_refused
```

### 10.3 Control Room URL

No Workroom-safe, responsibility-specific Control Room route is currently published by a canonical source. Private provider/chat surface locators are explicitly forbidden.

Initial V1 resource snapshots therefore carry:

```text
control_room_url        = null
control_room_source_ref = null
```

and WR-P0 must:

```text
omit would_add_control_room_bookmark
emit control_room_resource_missing
```

A later protected amendment may promote an exact Control Room allowed origin/path and accepted publication source. Until then, no localhost, private-seat, provider-chat, guessed public route or generic Control Room URL enters a Workroom action.

### 10.4 Snapshot completeness and freshness

An incomplete resource snapshot cannot prove absence or health. It emits:

```text
resource_snapshot_incomplete
```

The planner may still render source-attributed holds but cannot emit a missing-resource claim as though the complete source was observed.

`observed_at` is evidence time only. WR-P0 performs no freshness fetch. Any accepted freshness budget is supplied by the caller/release contract; stale evidence is typed, not refreshed by wrapper timestamp.

---

## 11. Planning eligibility versus apply eligibility

WR-P0 separates:

```text
planning_eligible
apply_eligible
```

A row may be planning-eligible only when exact canonical and observed checks pass.

A row is apply-eligible only when all planning gates pass and:

```text
rollout_mode in {CANARY, ACTIVE}
```

`SHADOW` is never apply authority.

Every initial row emits:

```text
shadow_mode_no_apply
apply_eligible = false
```

even when all observations are otherwise clean.

The summary contains distinct counts:

```text
eligible_workroom_count
apply_eligible_workroom_count
shadow_workroom_count
held_workroom_count
```

`eligible_workroom_count` must never be interpreted as safe to mutate Slack.

With current live evidence, the initial six-row corpus must produce:

```text
apply_eligible_workroom_count = 0
```

because all rows are `SHADOW`, Initiative rollout is absent and the Slack census is incomplete; BioCatalyst is additionally canonically excluded.

---

## 12. Closed action-emission semantics

The deterministic action vocabulary is:

```text
would_create_channel
would_rename_channel
would_update_managed_purpose
would_create_home_canvas
would_update_managed_canvas_block
would_create_project_radar
would_update_managed_radar_rows
would_add_linear_bookmark
would_add_control_room_bookmark
would_archive_after_acceptance
noop
```

Deterministic precedence is the order above unless implementation freezes another explicit tested order.

Rules:

- review, excluded, missing, ambiguous or unbound Project rows emit zero normal create/update actions;
- missing safe navigation resource omits that bookmark action and records a typed hold;
- never emit `url = null`, empty URL, guessed URL or unreviewed scheme;
- channel-name drift on an exact immutable channel ID emits `would_rename_channel`;
- channel-purpose drift remains a separate `would_update_managed_purpose`;
- a manual rename never changes Workroom identity;
- pure WR-P0 may report observed drift but may not claim a between-read-and-write race;
- `remote_changed` / `manual_remote_change` belongs to WR-A0/WR-C0 immediate pre-write reread;
- incomplete Slack census cannot prove absence and cannot emit an authoritative create action;
- duplicate or malformed managed markers fail closed;
- static policy and all snapshots remain zero-network inputs.

Required typed holds/refusals include:

```text
linear_project_missing
linear_project_ambiguous
initiative_rollout_pending
initiative_key_missing
initiative_key_ambiguous
initiative_name_mismatch
initiative_membership_missing
initiative_membership_ambiguous
initiative_membership_wrong
slack_snapshot_incomplete
duplicate_workroom
workroom_marker_invalid
resource_snapshot_incomplete
resource_snapshot_workspace_mismatch
resource_binding_missing
resource_binding_ambiguous
resource_project_id_mismatch
linear_project_resource_missing
linear_project_resource_refused
control_room_resource_missing
surface_capability_unavailable
shadow_mode_no_apply
```

---

## 13. Semantic digests and determinism

The emitted plan and receipt carry and verify:

```text
project_plan_semantic_hash
initiative_plan_semantic_hash
initiative_snapshot_observation_hash
slack_snapshot_observation_hash
resource_snapshot_observation_hash
policy_semantic_hash
workroom_plan_semantic_hash
```

Changed semantic input must change the Workroom plan digest. Mapping/list ordering where order is not semantic must not.

The planner must emit sorted JSON with stable action/warning ordering and no absolute local paths, timestamps generated at plan time, random IDs or host-specific values in the semantic digest.

The following are hard failures:

```text
project_plan_wrong_schema
project_plan_hash_invalid
initiative_plan_wrong_schema
initiative_plan_hash_invalid
initiative_snapshot_wrong_schema
initiative_snapshot_hash_invalid
slack_snapshot_wrong_schema
slack_snapshot_hash_invalid
resource_snapshot_wrong_schema
resource_snapshot_hash_invalid
policy_hash_invalid
```

---

## 14. Required RED-first discriminating corpus

WR-P0 must prove at least:

```text
literal workroom_ref vectors and no silent normalization
non-WS identity refusal
complete atomic source_records at one protected merge
old/single-path source key refusal
missing/extra/duplicate source path refusal
exact six policy rows and Initiative mappings
runtime/provider/session/completion/URL policy field refusal
linear_portfolio_plan.v1 is the only workstream eligibility input
wrong Project-plan schema or hash refusal
same workstream across Project-plan collections refusal
active Project positive planning path
review candidate emits zero normal actions
parked/done/killed emits zero normal actions
BioCatalyst Linear In Progress cannot override Agent OS parked
missing/ambiguous Linear Project emits zero unbound actions
target-specific warning holds only its target
accepted Initiative plan/snapshot digest agreement
missing/ambiguous/wrong Initiative membership behavior
shadow row can be planning-eligible but never apply-eligible
CANARY or ACTIVE is required before apply eligibility
eligible/apply-eligible/shadow/held counts are distinct
zero/one/multiple/malformed Workroom marker behavior
incomplete Slack census refuses authoritative absence/create
renamed channel with same ID/marker remains bound
name drift emits would_rename_channel
purpose drift is a separate action
inert channel C0BTQ71QEA0 is not implicitly adopted or retried
resource snapshot missing/wrong schema/hash/workspace
resource snapshot incomplete coverage
missing/duplicate resource responsibility row
Project ID mismatch across Initiative/resource inputs
safe observed Linear URL emits bookmark
missing Linear URL emits no bookmark
unsafe Linear host/scheme/port/query/fragment/credentials refuse
private provider/chat surface URL refuses
missing Control Room URL emits no bookmark and typed hold
input ordering does not change byte output or digest
resource observation change changes plan digest
network/socket monkeypatch proves zero network
```

The exact current-checkout suite must be wired through an existing Macro CI owner. Do not create a second Workroom CI plane.

Acceptance remains:

```text
BUILT_NOT_PROVEN / PRODUCTION_INERT
```

No Slack or Linear mutation exists from WR-P0.

---

## 15. Superseded #233 clauses

Explicitly not adopted:

- private Workrooms by default;
- `proj-` as source law;
- Mastermind planner implementation paths instead of the Macro owner;
- a parallel Workroom strategy schema;
- stale zero-Initiative or carrier observations as durable truth;
- stale enrollment-unmerged statements;
- the old operation key/carrier as active;
- any old protected source pin as current.

Explicitly adopted here:

- exact Initiative key/name comparison;
- exclusive reuse of `linear_portfolio_plan.v1`;
- atomic multi-record source provenance;
- planning/apply separation;
- zero actions for review/excluded/missing/ambiguous identity;
- explicit rename action;
- omission of unsafe/null URL actions;
- actuator-only remote-change detection;
- deterministic action order and discriminating tests.

#233 remains immutable historical evidence and is never merged or reopened.

---

## 16. Carrier and dependency ledger

Canonical Workroom carriers:

```text
#240  architecture / rollout / static planner law
#242  WR-R0 platform research and exact inert-effect evidence
#6661 Agent OS decision/discovery/handoff projection
```

Historical/superseded:

```text
#232  closed-unmerged metadata history
#233  closed-unmerged superseded source family
MAS-220 / MAS-221 duplicate projections
```

External prerequisites:

```text
Macro #6662  canonical main-red repair
Macro #6658  Initiative desired-state/drift compiler
Initiative live apply/readback  owned by Initiative session
MAS-64/MAS-66  dedicated Linear Projector actor/apply
MAS-189  selected Issue/comment/update projection
Agent Relay activation/canary  existing owner
AD-CHILD1 identity  existing protected owner
OCR-6 / Steward  existing exclusive compositor
```

Dependency-ordered continuation:

```text
1. protect current #240 source after exact-current-base CI/review and release clearance
2. retarget/reconcile #242 to protected master and accept exact research/evidence
3. reconcile/release #6661 Agent OS records
4. accept #6662 and #6658; consume Initiative post-apply readback
5. create one current read-only Slack/resource fixture with complete typed coverage
6. commission WR-P0 on one fresh Macro carrier
7. accept WR-P0 as production-inert
8. build/accept WR-A0 and WR-A1 under separate security gates
9. run one exact inert public-channel canary through the dedicated app
10. add Home/Radar and exact Workroom dialogue/Linear/Steward joins
11. run three-Project, adversarial multi-operator and small-fleet proof
```

No item authorizes its successor automatically.

---

## 17. Completion boundary

This amendment makes one Workroom source-law family recoverable, removes duplicate architecture and freezes a complete deterministic planner input contract, including safe navigation evidence.

After it lands:

```text
canonical architecture carrier = known
unique planner/source laws      = preserved
navigation-resource input       = closed and source-attributed
duplicate carrier               = terminal history
implementation capability       = unchanged
production capability           = unchanged
```

It does not make #242 accepted, #6661 protected, WR-P0 built, a Slack app installed, the inert channel managed, a Canvas/List created, Initiative rollout complete, Agent Relay live or the Chairman's Workroom experience production-ready.

The Project Workroom program remains incomplete until a real selected Project proves the exact journey:

```text
Agent OS workstream
→ normalized Linear Project / accepted Initiative membership
→ source-attributed safe navigation resources
→ exact Slack Workroom
→ selected operation thread
→ current Executive Attempt/Worker/RuntimeBinding
→ GitHub implementation/proof
→ Steward/Control Room composition
```

with zero duplicate effect, silent orphan, wrong-thread continuation, stale sanctioned worker or false completion.
