# Mastermind Project Workroom Convergence — Slack + Linear Operating Fabric

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `SPEC_ONLY / CHAIRMAN-APPROVED / IMPLEMENTATION-NOT-YET-PROVEN`  
**Operation key:** `project-workroom-convergence-20260829-sol-001`  
**Carrier:** `Mastermind:sol/project-workroom-convergence-20260829`  
**Protected procedure pin:** `mastermindx-market-intelligence/Mastermind@2962759e8abf6bf722a8582f92af8f84013f5f40`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1 compatible  
**Parent source law:** protected Mastermind #214 / `14056772bda2add31f1596bd89cebd6bf0c31de3`, protected autonomous-delegation amendment #227 / `edc10addbb6dd827929a6661d6ec125d2967ac3e`, protected Agent Relay runtime #231 / `2962759e8abf6bf722a8582f92af8f84013f5f40`, protected Linear Initiative architecture #229/#230  
**Related organizational owner:** existing `WS:CHAIRMAN-CONTROL-ROOM` / Operating-Surface Convergence and Autonomous AI Organization Initiative; this document creates no new Agent OS workstream.

This document freezes the product, authority, identity, data-flow, failure and rollout architecture for turning Slack Project channels plus Linear Projects into a coherent AI-company collaboration surface while preserving Agent OS, Executive OS, GitHub, Linear and Slack as distinct canonical/projection layers.

It does **not** create a Job, Attempt, Worker, Slack channel, Canvas, List, Workflow, Linear Issue, Initiative, app credential, queue, database, scheduler, retry plane, runtime binding, provider session or production capability by itself.

---

## 1. Chairman outcome

The Chairman must be able to open Linear or Chairman Control Room, choose a material program, enter one coherent Slack Project Workroom when dialogue detail is useful, and understand:

1. the program mission and strategic Initiative;
2. the exact canonical Agent OS workstream;
3. the current selected waves, gates, deliverables and decisions;
4. the logical Sol/COO/worker responsibility for each current operation;
5. what is actually executing versus merely planned or delivered;
6. what GitHub implementation/proof exists;
7. whose semantic turn is next;
8. what is blocked, degraded, returned or effect-unknown;
9. what exact lawful action moves the program forward; and
10. how multiple operators are working concurrently without duplicate effects or carrier confusion.

The Chairman must not need to:

- reconstruct the company from `#agent-dispatch` history;
- search for the correct Slack thread among unrelated projects;
- infer whether a Canvas/List card is truthful;
- manually copy messages between Sol, COO and worker sessions;
- choose routine provider accounts;
- decide which of two duplicate threads is authoritative;
- treat a Slack `RESULT`, Linear `Done` or GitHub merge as universal completion;
- repair local watchers merely to keep a program alive; or
- determine which stale provider tab still has write authority.

The target experience is:

```text
Linear Initiative
  -> strategic outcome

Linear Project + Agent OS WS:<KEY>
  -> durable project/program

Slack Project Workroom
  -> persistent collaboration room and project-detail drill-down

Linear Issue + Slack operation thread
  -> selected human-relevant child wave/gate/deliverable

Executive Job / Attempt / Worker / RuntimeBinding
  -> actual execution

GitHub
  -> implementation, CI and proof

Executive Steward / Control Room
  -> source-attributed current-state and attention composition
```

The acceptance statement is:

> One logical Sol Project Steward can govern a material program while multiple COO-grade operators and workers execute disjoint bounded operations in the same Project Workroom; every operation retains one exact organizational identity, Linear projection, Slack carrier, runtime binding and GitHub evidence path; no Slack or Linear convenience surface becomes another control plane.

---

## 2. Current estate and capability ledger

At the protected pin used for this design:

| Capability | State | Current owner / evidence |
|---|---|---|
| Operating-Surface / project-management source law | `SPEC_ONLY` protected | Mastermind #214 |
| Autonomous delegation operational-fluency law | `SPEC_ONLY` protected | Mastermind #227 |
| Long-running private Agent Relay runtime | `BUILT_NOT_PROVEN / production-disarmed` protected | Mastermind #231 |
| Agent Relay native enrollment/install ceremony | `BUILT_NOT_PROVEN`, open and blocked on bounded rollback repair / release sequencing | Mastermind #223 |
| Executive Steward pure read core | `BUILT_NOT_PROVEN`, open release carrier | Mastermind #228 |
| Linear Initiative architecture | `SPEC_ONLY / Chairman-approved / protected` | Mastermind #229/#230 |
| Live Linear Initiative rollout | externally owned by another active Sol carrier; do not duplicate | live Linear read still showed zero Initiatives during this design census |
| Agent OS -> Linear Project deterministic compiler | existing selected owner | MAS-65 / Macro #6182 lane |
| Dedicated Linear Projector app actor | `NOT_BUILT / Admin prerequisite` | MAS-64 |
| Linear project-only read/diff/apply | `SPEC_ONLY` | MAS-66 |
| Selected wave/gate Issue/comment projection | `SPEC_ONLY` | MAS-189 / OSC-C1 |
| Slack Project Workroom binding/planner | `NOT_BUILT` | this architecture |
| Managed Workroom Home Canvas / Radar List | `NOT_BUILT` | this architecture |
| Multi-workroom Agent Relay | `NOT_BUILT`; current client is fixed to one channel | downstream bounded Relay evolution |
| Multi-operator Project Workroom production proof | `NOT_BUILT` | downstream canary |

The current protected Slack Web API client is intentionally bound to one configured channel and only supports:

```text
conversations.history
conversations.replies
chat.postMessage
```

The protected Agent Relay runtime therefore cannot yet serve multiple Project Workrooms. It must be evolved after the exact A2 single-channel canary and enrollment path are accepted, not widened during their current release/repair cycle.

The current `control_plane.surface_bindings` owner is navigation-only for provider/chat/session surfaces. Its source law explicitly forbids project/runtime/status/authority semantics. Project Workroom binding must not be added there.

---

## 3. Chosen approach and rejected alternatives

### 3.1 Selected: federated Project Workroom fabric

Use Slack as the persistent project collaboration room and Linear as the durable human project/portfolio surface, joined through deterministic projections over existing Agent OS / Executive OS / GitHub owners.

Two least-privilege Slack principals are permitted:

1. **Mastermind Agent Relay** — exact dialogue read/write only;
2. **Mastermind Workroom Projector** — channel/Canvas/List/bookmark managed projection only.

The official Linear Slack integration remains a third-party convenience/projection layer for selected project updates, rich unfurls and carefully chosen synchronized discussions.

Multiple app principals do not imply multiple organizational systems. They are authority-separated actuators over one accepted architecture.

### 3.2 Rejected: make Agent Relay a Slack superbot

Rejected because combining executive dialogue with channel creation, Canvas/List mutation, workflow configuration and navigation management would give the communication principal unnecessary workspace-wide authority and create an excessive blast radius.

### 3.3 Rejected: use Slack Lists as the project database

Rejected because Slack Lists would then compete with Agent OS workstream truth, Linear project state and Executive runtime state. Manual List edits, Slack outage and Canvas/List retention behavior would become company-state hazards.

### 3.4 Rejected: make Linear canonical runtime truth

Rejected because Linear status cannot prove Job admission, Attempt claim, worker execution, provider session health, GitHub merge, production proof or Sol acceptance.

### 3.5 Rejected: add Notion, Confluence, Airtable, Asana, ClickUp or monday.com as another operating layer

Rejected because each would introduce another task, project, workflow or organizational-memory plane beside Agent OS + Linear.

### 3.6 Rejected: one channel per provider account, agent or child operation

Rejected because provider accounts and sessions are ephemeral runtime placement facts. Child operations are threads and Linear Issues under a durable project room, not channels.

---

## 4. Canonical ownership and no-rebuild law

| Fact | Canonical owner |
|---|---|
| durable program/workstream/wave/decision/discovery/handoff identity | Agent OS |
| ranked company priority / accepted strategy | current strategic-state owner / Improvement Agenda |
| Job / Attempt / Worker / Event lifecycle, leases, fences and retry/requeue | Executive OS |
| provider/account/host eligibility and capacity evidence | Capacity Fabric / Shared AI Provider Control / Model Router |
| exact provider-native process/session execution evidence | Worker/Operator Harness + provider adapter |
| exact current runtime/session binding | RuntimeBinding / Operator Continuity |
| dialogue parent/messages and Slack delivery | Agent Dialogue / Agent Relay / Slack |
| wake obligation, delivery, ACK and source resolution | Executive Wake Fabric |
| implementation, branch, PR, CI, merge and proof | GitHub |
| human strategic/project/selected-issue projection | Linear |
| project collaboration room, Canvas/List/workflow presentation | Slack Project Workroom projection |
| source-attributed current-state and attention composition | Executive Steward / Chairman Control Room |

Forbidden additions include:

- Project Workroom database;
- Slack task queue;
- Slack lifecycle or retry table;
- Canvas/List completion authority;
- second Linear synchronizer;
- duplicate Agent OS workstream registry;
- provider-session registry;
- Sol election table;
- per-channel Agent Relay daemon;
- per-project credential/token;
- one watcher database per operation;
- channel-name authority; or
- fuzzy project/thread/worker matching.

---

## 5. Organizational model: Sol Project Steward plus bounded operators

### 5.1 Sol Project Steward

Every promoted, materially active Project Workroom has one logical **Sol Project Steward responsibility**.

This is not:

- one permanent browser tab;
- one Slack principal;
- one provider account;
- one chat URL;
- one process title; or
- a new durable role registry.

It is derived from existing Agent OS accountability and exact Executive/RuntimeBinding action targeting. One Sol reasoning surface may steward several projects. Each unresolved child turn still has exactly one action-authoritative Sol target under protected #214/#227 law.

When the current Sol surface becomes unavailable, a successor may act only after exact canonical action-binding reconciliation/transfer. Newest timestamp, visible responder, Slack identity or apparent health never elects a successor.

### 5.2 COO-grade operators and workers

Multiple Fable, CTO Sol, Terra, Opus, Grok, Luna/mechanical or other governed workers may operate inside one Project Workroom concurrently, but they own **bounded operations**, not an undifferentiated project.

Every modifying operation retains:

```text
one responsibility/workstream
one stable operation identity
one selected Linear Issue binding
one Slack parent/thread
one current Executive child Job
one current Attempt/Worker/runtime generation
one GitHub implementation/evidence carrier
one action-authoritative operator
one action-authoritative Sol turn
```

A worker’s provider account/session may change only through current Capacity/RuntimeBinding/continuation law. The Project Workroom and operation identity remain stable.

### 5.3 Parallelism law

Cross-root parallel execution is governed by protected #227.

Broad intra-root simultaneous write-capable children remain held until separately proven:

- per-child worktree/branch isolation;
- declared changed-path ownership;
- deterministic overlap detection;
- integration/review order;
- failure/cancellation isolation;
- stale-worker fencing; and
- truthful Control Room projection of multiple current children.

The Workroom UI may display many planned or reviewed children without authorizing simultaneous writes.

---

## 6. Hierarchy and exact identity mapping

```text
Linear Initiative
  = one company-level strategic outcome

Agent OS WS:<KEY>
  <-> one normalized Linear Project
  <-> zero or one promoted Slack Project Workroom in V1

selected Agent OS wave/gate/deliverable/admin action
  <-> one Linear Issue when OSC-C1 selection law admits it
  <-> zero or one canonical Slack operation parent/thread

Executive child Job
  -> one canonical operation identity
  -> one canonical dialogue parent
  -> zero or more sequential Attempts
  -> at most one current action-authoritative Attempt
```

Exact joins only:

- `WS:<KEY>` must match byte-for-byte;
- Linear Project binds by immutable Project ID after exact WS identity resolution;
- Slack Workroom binds by immutable workspace/channel ID and a managed marker carrying exact work reference + Linear Project ID;
- operation/thread binds through deterministic Executive child/dialogue identity, never title similarity;
- provider runtime binds through current Attempt/Worker/RuntimeBinding generation;
- GitHub evidence binds through accepted operation/workstream/PR linkage, never newest related-looking PR.

The unresolved `Mastermind-X Linear OS` Project and compatibility redirect `WS:WATCHLIST-PORTFOLIO-CEO` receive no Workroom until their protected Initiative/organizational rulings permit one.

---

## 7. Workroom eligibility and promotion

A Linear Project does not automatically deserve a Slack channel.

V1 promotion requires all of:

1. exact canonical `WS:<KEY>` parent;
2. truthful normalized Linear Project binding;
3. materially active or intentionally observable state;
4. multi-wave or sustained duration;
5. meaningful Sol/COO/multi-worker collaboration need;
6. enough human value that the Chairman may inspect it;
7. no duplicate/superseded/compatibility-only project identity;
8. no current effect-unknown carrier migration requirement; and
9. one explicit strategy row in the static workroom strategy companion.

A small bug, one-time migration, isolated PR review or mechanical task stays under an existing project’s operation thread or remains machine-managed without a dedicated Workroom.

### 7.1 V1 shadow pilot candidates

The initial strategy companion may contain these exact **shadow-only** candidates:

```text
WS:CHAIRMAN-CONTROL-ROOM
WS:AGENT-OS
WS:RATES-INFLATION-COMMAND
WS:BIOCATALYST-CORE-PRODUCT
WS:FINANCIAL-INTELLIGENCE-FABRIC
WS:STOCK-IDENTITY
```

Shadow membership authorizes desired-state planning only. It does not create channels, reactivate parked work, start a worker, alter Initiative membership or move an existing carrier.

Before any live canary, the planner must consume the final protected Linear Initiative rollout receipt and fresh normalized Linear Project state. A pilot row whose canonical/Linear state no longer qualifies becomes a typed hold, not an automatic channel.

### 7.2 Workroom lifecycle

Workroom presentation states are derived projection facts:

```text
SHADOW
CANARY
ACTIVE
READ_ONLY_HISTORY
ARCHIVE_CANDIDATE
DEGRADED
```

They are not Executive lifecycle states.

A completed/parked project may retain a read-only historical Workroom. Archiving a Slack channel never completes or parks the canonical workstream. Project reactivation requires canonical Agent OS/strategy action, not unarchiving a channel.

---

## 8. Machine-readable strategy and binding contract

### 8.1 Static strategy companion

Create one repository-owned static projection configuration:

```text
mastermind.project_workroom_strategy.v1
```

Allowed fields:

```text
schema
source_design
workspace_id
channel_prefix
workrooms[]
  work_ref
  channel_slug
  privacy
  rollout_mode
  required_surfaces
  allow_linear_project_updates
  allow_linear_thread_sync
```

V1 values:

```text
privacy = private
rollout_mode = shadow | canary | active
channel_prefix = proj-
required_surfaces = home_canvas, project_radar, linear_bookmark, control_room_bookmark
allow_linear_project_updates = false until dedicated canary
allow_linear_thread_sync = false unless an exact selected collaboration thread is separately admitted
```

The strategy contains no live channel IDs, Job/Attempt/Worker state, provider account, Slack cursor, retries, completion, priority or secrets.

### 8.2 Read-only snapshots

The pure planner consumes explicit snapshots:

```text
mastermind.project_workroom_linear_snapshot.v1
mastermind.project_workroom_slack_snapshot.v1
```

Linear snapshot rows include only immutable Project ID, exact managed WS binding, name, lifecycle projection, Initiative membership, resource links and observation/version evidence.

Slack snapshot rows include only workspace/channel IDs, name, privacy, archived state, managed purpose marker, app membership, Canvas/List/bookmark metadata and observation/version evidence.

### 8.3 Desired-state plan

The planner emits:

```text
mastermind.project_workroom_plan.v1
```

Per workroom:

```text
work_ref
linear_project_id
initiative_id
channel_slug
privacy
rollout_mode
desired_surfaces
observed_channel_id
observed_surface_ids
actions[]
refusals[]
source_refs
observation_hash
```

Action vocabulary:

```text
would_create_channel
would_update_managed_purpose
would_create_home_canvas
would_create_project_radar
would_add_linear_bookmark
would_add_control_room_bookmark
would_update_managed_canvas_block
would_update_managed_radar_rows
would_archive_after_acceptance
noop
```

Refusal/degradation vocabulary includes:

```text
strategy_wrong_schema
strategy_duplicate_work_ref
strategy_duplicate_channel_slug
strategy_unknown_workstream
initiative_rollout_unavailable
linear_project_missing
linear_project_duplicate
linear_project_unmanaged
linear_project_state_ineligible
unexpected_initiative_membership
slack_workspace_mismatch
duplicate_workroom
workroom_marker_conflict
channel_name_collision
channel_privacy_mismatch
channel_archived_unexpectedly
channel_remote_changed
home_canvas_missing_or_ambiguous
project_radar_missing_or_ambiguous
managed_canvas_block_invalid
managed_radar_schema_invalid
bookmark_duplicate_or_conflict
platform_capability_unavailable
app_scope_refused
manual_remote_change
```

The planner performs zero network calls and zero writes.

### 8.4 Managed marker

Every managed channel purpose contains one exact, non-secret marker:

```text
[MMX-WORKROOM:v1 work_ref=WS:<KEY> linear_project_id=<UUID>]
```

The marker is presentation/binding evidence only. It grants no authority and cannot admit work.

Two channels carrying the same marker produce `duplicate_workroom` and freeze both from automated mutation until Sol reconciliation.

### 8.5 Live binding receipt

After an accepted apply/read-back, preserve a bounded evidence receipt containing:

```text
strategy source SHA/hash
Linear Project ID/version
Slack workspace/channel ID
managed marker
Home Canvas ID
Radar List ID
bookmark IDs
project integration/subscription configuration
app actor identity/scopes
read-back hashes
canary timestamps
rollback/disable path
```

This receipt belongs in repository research/evidence plus a short Agent OS handoff pointer. It is not a mutable Workroom database.

---

## 9. Slack Project Workroom surface contract

### 9.1 Channel

V1 channels are private by default and named:

```text
#proj-<stable-short-slug>
```

The slug is static strategy, not mechanically regenerated from changing Project titles. Project title changes do not silently rename the channel; a managed rename requires a reviewed desired-state change.

Top-level channel messages are limited to high-signal project objects:

- new selected wave/gate cards;
- material project updates;
- decisions;
- major blockers/degradations;
- accepted releases/production proofs;
- Workroom integrity notices.

Raw ACK/START/PROGRESS/RESULT protocol stays in the exact operation thread.

A naked top-level agent command has no execution authority.

### 9.2 Home Canvas

The Workroom Projector creates one tabbed Home Canvas using Slack’s `canvases.create`/Canvas APIs when the app has reviewed `canvases:write` authority.

The Home Canvas contains:

```text
Stable Project Charter
- mission
- strategic Initiative
- canonical WS identity
- outcome / completion ruler
- scope and no-rebuild boundaries
- logical accountability model
- canonical source links

Generated Current Snapshot
- Agent OS state/source/freshness
- selected Linear frontier
- Executive runtime summary
- GitHub evidence summary
- turn owner / attention
- exact next lawful action
- disagreement/degraded reasons
```

Stable charter text is source-controlled/human-reviewed. Generated sections are replaced only inside exact managed markers. Manual text outside the managed block remains immutable to the projector.

Workers cannot hand-edit generated runtime/completion claims and thereby change company truth.

### 9.3 Project Radar List

The Workroom Projector creates one List through Slack Lists APIs with a closed schema.

V1 columns:

```text
work_item             text / primary
linear_issue          link
plan_state            select
runtime_state         select
proof_state           select
turn_owner             select
attention_state       select
logical_owner         text
slack_thread          message/link
github_carrier        link
next_action           text
source_freshness      select
last_projected_at     date/time or text supported by accepted API
```

Do not create one synthetic `status` field.

Managed Radar rows are derived from existing owners and are read-only to ordinary agents. Manual drift in managed columns causes explicit conflict/refusal. Optional noncanonical notes must live in a separate column or Working Notes surface and can never satisfy completion.

### 9.4 Working Notes Canvas

A separate Canvas may be collaboratively edited for scratch research, meeting notes and hypotheses.

It must display:

```text
NONCANONICAL WORKING NOTES
Nothing here changes Agent OS, Executive OS, Linear completion or GitHub proof until promoted through the owning path.
```

Discoveries/decisions requiring durable authority are promoted into Agent OS/repository records through the governed workflow.

### 9.5 Tabs, folders and bookmarks

Slack currently supports up to 15 channel tabs containing Canvases, Lists, Workflows, messages, links and files/folders.

V1 core automation uses APIs with current official support:

- Canvas creation/access/update;
- List creation/schema/items/access;
- channel bookmarks for Linear Project and Control Room links;
- channel/message APIs required for the Workroom and dialogue.

Folder/tab ordering beyond current supported API capability is an optional presentation enhancement. If Slack requires a human Channel Manager action, the Workroom remains truthful with bookmarks/links and reports `platform_capability_unavailable`; it does not invent an unsupported automation.

### 9.6 Workflows

Workflows are structured request surfaces, not authority.

Initial workflow classes:

```text
Propose Wave
Raise Blocker
Request Sol Review
Request Decision
Record Discovery
Escalate Chairman/Admin
```

A workflow submission produces a typed proposal/attention candidate tied to the exact Workroom. It cannot directly create an Executive Job, choose capacity, merge, deploy, close a Linear Issue, mark Agent OS done or retry an effect-unknown action.

Custom Workflow Builder steps/triggers may be added only after app permission/admin capability is proven. Workflow unavailability does not block the core Workroom canary.

### 9.7 Channel templates

Slack templates can bundle Canvas, Lists and Workflows, but Slack’s current help documentation states that custom templates cannot be created or edited as of 2026-08-20.

Therefore custom templates are not a load-bearing implementation dependency. The projector provisions reviewed components directly. A future custom template may become a convenience layer only after capability returns and exact parity is proven.

---

## 10. Linear integration contract

### 10.1 Linear Project remains the human project hub

Each Workroom links to exactly one normalized Linear Project for the same exact `WS:<KEY>` identity.

The Linear Project exposes:

- Initiative membership;
- human project summary and state;
- selected milestones/issues;
- Project Workroom link;
- Control Room link;
- source/evidence resources;
- Project updates.

Linear remains selective projection and cannot prove execution or completion outside its declared semantic owner.

### 10.2 Project channel auto-creation remains disabled

Linear can automatically create one **public** Slack channel per new Project, invite all Project members and add a Project bookmark.

Mastermind V1 rejects global auto-creation because:

- not every Project deserves a Workroom;
- Workrooms are private by default;
- current Linear estate requires normalization;
- custom Home/Radar/projection surfaces are required;
- exact app attribution/read-back and duplicate refusal are required;
- automatic rename behavior is not accepted as authority.

The Workroom Projector owns selected provisioning. The official Linear integration may later bind an existing accepted Workroom for Project updates if supported and canaried.

### 10.3 Project updates

Project updates may post into the Workroom after a controlled canary.

The update body must be a Sol/Steward-authored human summary grounded in canonical evidence. Native progress rollups are navigational only. Comments may sync between the Linear Project update and Slack thread when the exact update is intended as human collaboration.

### 10.4 Linear Issues and Slack operation threads

OSC-C1 / MAS-189 remains the sole selected wave/gate Issue/comment projection owner.

The Workroom program adds these constraints to that future promotion:

- an admitted selected work object binds to the Project’s exact Workroom;
- exactly one operation parent/thread is ensured;
- raw Agent Dialogue protocol is not copied into Linear comments;
- selected human discussion may synchronize only under an explicit per-item flag;
- Slack `RESULT` never changes Linear completion without owning proof law;
- GitHub merge never false-closes a production-proof gate;
- no fuzzy `@Linear` contextual selection is used by autonomous agents.

Humans may use official `@Linear` conveniences, but agent-originated mutations must use exact Project/Issue IDs and reviewed typed integrations.

### 10.5 Current Initiative owner boundary

The concurrent Linear Initiative session exclusively owns Initiative creation, Project membership and rollout receipts.

This Workroom carrier:

- does not create or edit Initiatives;
- does not reclassify Project membership;
- consumes the final protected strategy SHA and live read-back;
- fails closed when the Initiative rollout is unavailable or conflicts with the strategy companion.

---

## 11. Slack app/principal and permission architecture

### 11.1 Mastermind Agent Relay

Purpose:

```text
read exact allowed dialogue channel/thread
post exact bound dialogue parent/reply
validate actor, operation, lineage and applicability
```

It does not create channels, Canvases, Lists, bookmarks or Workflows.

Current protected A2 permission floor remains narrow. Multi-workroom evolution requires separately reviewed scopes and one allowlist-aware client/runtime; no arbitrary caller-selected channel.

### 11.2 Mastermind Workroom Projector

Purpose:

```text
read exact selected channel/surface state
create/update selected private Workrooms
create/update managed Home Canvas and Radar List
manage exact approved bookmarks/resources
read back and reconcile ambiguous effects
```

It receives no Agent Dialogue RULING, Executive lifecycle, Wake, provider, capacity, merge, deploy or worker-tool authority.

Expected least-privilege capability families, subject to exact current Slack app review:

```text
conversations read/create/manage for selected private channels
canvases read/write
lists read/write
bookmarks read/write
chat write only for bounded Workroom integrity/update notices
files read only if required to resolve managed Canvas/List entities
```

No workspace admin, user management, broad history export, global search, DMs, credential discovery or arbitrary external messaging.

### 11.3 Official Linear Slack app

Purpose:

- safe rich unfurls;
- selected Project/Issue notifications;
- selected Project update/comment synchronization;
- human convenience actions.

It does not admit Executive work or own Workroom projection.

### 11.4 Credential law

Each app uses one dedicated non-human app identity and the existing reviewed native host credential pattern:

- stdin/no-echo enrollment;
- no secret in chat, Slack, GitHub, Linear, argv, environment, temporary files or model-visible output;
- exact workspace/app/bot/scopes qualification;
- owner/mode/traversal/link checks;
- production-disarmed install before canary;
- revocation/rotation receipt;
- no personal ChatGPT1/2/3 or employee token fallback.

The Workroom Projector credential boundary must be separately isolated from Agent Relay and Linear Projector credentials.

---

## 12. Agent Relay multi-workroom evolution

### 12.1 Preserve the protected A2 foundation

Protected #231 remains the sole long-running Agent Relay runtime foundation. Open #223 remains the sole current enrollment/install carrier.

Do not widen #223 or its A2 canary to multi-workroom operation.

Required sequence:

```text
#223 repair/reconcile/release
-> hidden credential enrollment / verify
-> exact one-channel A2 live canary
-> Sol acceptance
-> separate multi-workroom architecture/implementation child
```

### 12.2 One service, one token, reviewed allowlist

The accepted multi-workroom design is:

```text
one private Agent Relay process
one dedicated Relay app/token
one immutable/configured workspace
one reviewed set of allowed Workroom channel IDs
exact operation -> expected Workroom resolution
```

Forbidden:

- one Relay daemon per channel;
- one token per Project;
- channel ID supplied freely by the model;
- fallback to `#agent-dispatch` when a Workroom is unavailable;
- search-by-channel-name authority;
- automatic channel creation by the Relay.

### 12.3 Routing contract

The caller supplies an exact operation/context identity, not an arbitrary destination.

A pure route resolver consumes:

```text
work_ref
operation identity
selected Linear Issue binding when present
Workroom snapshot/binding evidence
current dialogue parent identity
```

and returns one exact allowed channel or a typed refusal.

The existing V1/V2 Agent Dialogue engine remains the semantic validator. The route layer cannot weaken actor, applicability, reply lineage or one-parent law.

### 12.4 Slack outage

A running Executive Job remains truthful while Slack is unavailable.

The worker may continue only until the next semantic boundary that requires a company return. BLOCKED/DECISION_REQUEST/RESULT is preserved through the governed harness/current Attempt source and projected when transport recovers. No duplicate execution or alternate thread is created.

---

## 13. Operation parent and dialogue law

A Project Workroom channel is a namespace, not the operation carrier.

Every selected operation gets one top-level parent card/thread containing:

```text
human title and mission
exact work_ref
Linear Issue ID/link
stable operation identity
logical owner/avenue
GitHub carrier when known
current projection state
closed Agent Dialogue parent envelope/reference
```

Channel-level ordinary messages cannot originate autonomous responsibility.

AD-DLG2 remains the owner for idempotent exactly-one canonical dialogue parent creation. A parent write timeout becomes `EFFECT_UNKNOWN` and exact-parent reconciliation; never blind-create another message.

Independent next child work always gets a new operation identity, selected Issue binding and fresh parent/thread. A terminal old thread never authorizes the next wave.

---

## 14. Multi-operator concurrency and Git collision fences

Before a write-capable operation enters START, current source/Executive workspace law must prove:

```text
exact operation and carrier
current Attempt/Worker/binding generation
repo/worktree/branch authority
declared changed paths or protected authority surface
active sibling operations for the same root/project
known effect state
integration/review owner
```

Typed outcomes:

```text
DISJOINT_WRITE_ALLOWED
READ_ONLY_PARALLEL_ALLOWED
CROSS_OPERATION_PATH_COLLISION
AUTHORITY_SURFACE_COLLISION
WORKSPACE_COLLISION
INTEGRATION_ORDER_REQUIRED
EFFECT_UNKNOWN
```

A collision pauses before modification and returns to the action-authoritative Sol Project Steward. It does not create another branch or move work to another provider.

One sibling’s merge/result cannot complete another sibling or the parent program.

---

## 15. End-to-end operating flow

```text
1. Chairman/Sol defines or continues company intent.
2. Agent OS exact parent and selected child identity exist.
3. Linear Project and selected Issue are bound or projection defect is explicit.
4. Workroom strategy/snapshot resolves the exact Project channel.
5. AD-DLG2 ensures exactly one operation parent/thread in that Workroom.
6. Executive OS admits the child Job.
7. Capacity/RuntimeBinding claims one current Attempt/Worker.
8. Worker executes through its governed tools/workspace.
9. Provider/harness mechanically projects typed semantic returns.
10. Wake/Steward resolves the exact action-authoritative Sol target.
11. Sol emits CONTINUE / REQUEST_REPAIR / ACCEPTED-STOP.
12. GitHub and Agent OS are updated at their owning completion boundaries.
13. Linear Issue/Project and Slack Home/Radar/update are re-projected.
14. A terminal child with active parent/no successor becomes `PARENT_ACTIVE_NO_SUCCESSOR / needs_sol`.
15. Independent next child requires fresh identity/admission/thread.
```

---

## 16. State and semantic separation

Never flatten these into one field:

```text
Plan / organizational state
Executive runtime state
GitHub implementation/proof state
Dialogue turn state
Attention state
Transport health
Projection freshness
```

Examples:

```text
Linear In Progress != Executive RUNNING
Slack ACK != Executive claim
Slack START != canonical Attempt started unless sourced from Executive/harness evidence
Slack RESULT != completion
GitHub merge != production proof
Canvas/Radar Done != Agent OS done
channel archived != project terminal
Workroom missing != workstream missing
```

Unknown/null/degraded is shown explicitly and never coerced to healthy/empty/complete.

---

## 17. Failure and correction matrix

| Condition | Required behavior |
|---|---|
| two Slack channels claim one Workroom marker | `DUPLICATE_WORKROOM`; freeze both from automated mutation |
| one channel claims two work references | `WORKROOM_MARKER_CONFLICT`; freeze |
| thread exists in wrong Workroom | `WORKROOM_CARRIER_MISMATCH`; no reply/migration |
| same operation has two parent messages | `CARRIER_BINDING_AMBIGUOUS`; no third parent |
| channel renamed manually | immutable ID remains evidence; managed desired-state drift requires explicit update/refusal |
| channel archived/deleted unexpectedly | `WORKROOM_UNAVAILABLE`; no fallback to `#agent-dispatch` |
| Canvas/List managed block malformed | refuse mutation; preserve manual content |
| Canvas/List/manual remote edit after snapshot | optimistic reread -> `REMOTE_CHANGED`; no overwrite |
| channel/Canvas/List/bookmark write response ambiguous | exact read-back; desired state present -> reconcile; absent+unchanged -> at most one same-target idempotent retry; otherwise hold |
| Slack unavailable | Executive/Agent OS/GitHub truth remains; transport degraded |
| Linear unavailable | Workroom remains collaboration-only; projection degraded; no Slack-created project truth |
| worker return not projected to Slack | harness/current Attempt return remains; `WORKER_RETURN_NOT_PROJECTED`; Sol attention cannot be silently lost |
| two workers claim same operation | stale/duplicate worker refused by current Attempt/fence |
| two Sol surfaces observe same return | only exact action target acts; other is observer |
| Sol target unavailable | exact transfer/reconciliation before action |
| GitHub merge without proof completion | Linear/Radar gate remains open |
| Slack RESULT without canonical completion | Linear/Radar remains nonterminal |
| child STOP, parent active, no successor | `PARENT_ACTIVE_NO_SUCCESSOR / needs_sol` |
| no eligible capacity | `WAITING_CAPACITY / needs_placement`; no routine Chairman account choice |
| write-capable interruption effect unknown | no retry/failover/carrier move |
| sibling changed-path overlap | hold before write and adjudicate exact ownership |
| Initiative rollout absent/conflicting | Workroom live apply held; shadow planning may report defect |
| platform lacks folder/tab/workflow automation | core channel/Canvas/List/bookmark stays truthful; optional feature reports unavailable |

---

## 18. Security, privacy and access

V1 Workrooms are private unless a later explicit policy approves public visibility.

Never copy into Slack Canvas/List/message projection:

- credentials/tokens/cookies;
- private browser/session URLs not approved for the audience;
- raw provider-native session IDs when not needed by humans;
- customer/private licensed payloads;
- secret-bearing settings screenshots;
- full runtime environment or argv;
- private transcripts;
- unrestricted GitHub/Linear payloads.

Projector logs/receipts use exact object IDs and normalized hashes, not full private content.

A Slack user/app identity is transport attribution, not Sol/worker authority. Logical actor labels derive from existing Executive/RuntimeBinding/Agent Dialogue sources.

App membership in a channel and technical ability to post never grant permission to admit or continue work.

---

## 19. Platform capability and graceful degradation

Current official platform capabilities used by this architecture include:

- Slack channel tabs for Canvases, Lists, Workflows, messages, links/files/folders;
- Slack Canvas create/access/update APIs;
- Slack Lists create/schema/item/access APIs;
- Slack bookmark read/write APIs;
- Slack Workflow Builder/custom steps and webhook triggers, subject to admin/plan restrictions;
- Linear Project Slack channels, Project updates, rich unfurls and selected thread synchronization.

Every capability is verified at action time against current plan/admin/scopes.

A missing optional platform feature does not justify a custom duplicate system. The projector emits a typed capability defect and preserves the smallest truthful Workroom.

---

## 20. Optional plugin integrations

### 20.1 Sentry — allowed later as read-only incident evidence

A future Sentry connector may provide recent issue/event evidence to Steward/Control Room and link relevant incidents into a Workroom.

It receives no project/lifecycle/retry/completion authority and cannot automatically originate or close work.

### 20.2 Google Drive — optional read-only external evidence

Allowed only for external documents that lawfully cannot live in GitHub. It never replaces repository architecture, Agent OS decisions or Linear project state.

### 20.3 Explicitly rejected operating plugins

Do not add Notion, Confluence/Jira, Airtable, Asana, ClickUp or monday.com as another Mastermind project/organizational operating plane.

---

## 21. Rollout modes

### SHADOW

- pure desired-state/drift planner only;
- zero Slack/Linear writes;
- Initiative/Project/Slack census and refusal calibration;
- compare intended Workrooms against real estate.

### CANARY

- one inert private Workroom;
- exact channel, Home Canvas, Radar List and bookmarks;
- no real project dialogue or Linear thread sync;
- create/read/update/noop/manual-drift/effect-unknown/rollback proof.

### PILOT

- three real Projects;
- new operations only;
- no migration of existing active/effect-unknown `#agent-dispatch` carriers;
- one Sol Project Steward plus several disjoint operators;
- selected Linear Project updates after canary.

### SMALL FLEET

- ten to fifteen promoted Workrooms;
- many independent roots/workers;
- exact return projection, Wake and Steward attention;
- ordinary new project work stops entering `#agent-dispatch`.

### FULL FABRIC

- Linear + Control Room are normal Chairman operating surfaces;
- Slack Workrooms are collaboration/detail drill-down;
- `#agent-dispatch` is forensic/legacy transport only;
- zero routine Chairman Slack archaeology, account allocation, watcher repair or message shuttling.

### ADVANCED INTRA-ROOT PARALLELISM

- only after separate workspace/path/integration proof;
- not authorized by Workroom appearance or multiple operator availability.

---

## 22. Required acceptance canaries

### A. Workroom identity and duplicate race

Create one intended Workroom twice concurrently under the same exact strategy/snapshot.

Expected:

```text
one private channel
one Home Canvas
one Radar List
one exact bookmark set
same read-back receipt
zero duplicate surface
```

Changed normalized desired state under the same action identity must conflict/refuse.

### B. Manual remote drift

A human edits the managed purpose/Canvas/List between snapshot and apply.

Expected: optimistic reread detects movement; zero overwrite; manual content preserved.

### C. Project rename

Rename the Linear Project.

Expected: immutable Project/channel binding remains; no automatic new channel; desired presentation change is explicit.

### D. Same Slack principal, distinct operations

Several native sessions share one Slack principal while executing distinct accepted operations.

Expected: separate RuntimeBindings/operations succeed; Slack principal never becomes runtime identity.

### E. Same operation, duplicate native sessions

Two sessions claim the same operation.

Expected: one current worker; stale/duplicate session refused before effect; one thread/PR carrier.

### F. Multiple operators in one Workroom

One Sol Project Steward supervises at least three disjoint operations with multiple COO/worker sessions.

Expected: correct independent threads/Issues/PRs; no cross-thread message or path collision; only exact Sol target adjudicates each return.

### G. Path collision

Two operations declare/attempt an overlapping write path.

Expected: collision before second modification; no duplicate branch/effect.

### H. Slack outage

Interrupt Slack during healthy execution and again at a RESULT boundary.

Expected: runtime remains truthful; semantic return preserved; projection degraded; no duplicate execution/thread.

### I. Linear outage

Interrupt Linear during Workroom activity.

Expected: collaboration continues as noncanonical; no Slack-created project truth; later projection reconciles without duplication.

### J. False-completion controls

Test GitHub merge without production proof and Slack RESULT without canonical acceptance.

Expected: Linear Issue/Radar remains open at the correct gate.

### K. Sol loss and transfer

Kill the action-authoritative Sol surface after worker return.

Expected: no sister Sol acts until exact transfer; then one continuation edge.

### L. Parent active / child terminal

STOP a child while the parent remains active and has no admitted successor.

Expected: Workroom/Steward/Linear surfaces show `needs_sol`; no automatic next child.

### M. Archive/history

Park or complete a project with an accepted Workroom.

Expected: Workroom becomes read-only/archive candidate after canonical state; archiving never changes canonical truth; reactivation requires a new canonical ruling.

---

## 23. Completion ruler

The Project Workroom program is not complete when:

- architecture/docs merge;
- channels exist;
- Canvases/Lists look attractive;
- Linear links unfurl;
- workers can post messages;
- one PR is green;
- one Project update syncs;
- the Agent Relay is installed; or
- `#agent-dispatch` is quieter.

It is complete only when a real multi-project interval proves:

```text
truthful normalized Linear Projects/Initiatives
+ exact selected Workroom bindings
+ managed Canvas/Radar surfaces
+ one canonical operation thread per child
+ mechanically projected returns
+ exact Sol action targeting
+ multi-worker collision/fence behavior
+ Slack/Linear outage correction
+ no false completion
+ Control Room/Linear normal Chairman use
= coherent AI-company operating fabric
```

---

## 24. Non-goals

This program does not:

- create a new Mastermind OS or Agent OS;
- replace Linear with Slack;
- replace Slack with Linear;
- create a project channel for every task;
- migrate active/effect-unknown carriers;
- turn Canvases or Lists into canonical stores;
- authorize global Linear automatic project-channel creation;
- allow autonomous contextual `@Linear` issue selection;
- allow arbitrary Workroom/channel selection by a model;
- create one app/token/daemon per project;
- grant broad intra-root parallel writes;
- implement provider routing/capacity/retry;
- weaken Executive, GitHub, Agent OS or production-proof laws;
- add another project-management SaaS; or
- make optional folders/tabs/templates a substitute for truthful core behavior.

---

## 25. Existing owner subtraction and implementation sequence

Preserve and consume:

```text
#214  organizational continuity / project-management / Sol action authority
#227  autonomous delegation operational fluency
#229/#230 Linear Initiative architecture + approval receipt
#231  protected Agent Relay runtime foundation
#223  current Agent Relay enrollment/install + single-channel canary owner
#228  current Executive Steward read-core release carrier
MAS-65/MAS-64/MAS-66 Linear Project projection chain
MAS-189 selected Issue/comment/update projection
AD-ID1 / AD-CHILD1 / AD-DLG2 / AD-RET1/2 / AD-SOL1 / AD-FLEET1 / AD-CR1 / AD-CUTOVER
```

New bounded waves created by this architecture are:

```text
WR-R0  current estate/platform/app/scope/read-only census
WR-P0  pure Workroom strategy/snapshot/desired-state planner
WR-A0  Workroom Projector app + secret-safe enrollment boundary
WR-C0  inert Workroom channel/Home/Radar/bookmark canary
WR-D0  one Agent Relay -> reviewed multi-workroom allowlist
WR-D1  operation identity -> correct Workroom parent ensure
WR-L0  consume OSC-C1 selected Issue/update projection in Workrooms
WR-M0  one real multi-operator project pilot
WR-S0  failure/adversarial stress matrix
WR-P1  three-project production pilot
WR-P2  small-fleet expansion
WR-CUTOVER final ordinary-work cutover
```

Each implementation wave gets one independently useful capability, one carrier and its own exact proof. This records carrier authorizes no implementation mutation by itself.

---

## 26. Precedence and exact next action

For Project Workroom channel/Canvas/List/bookmark/Linear-binding architecture, this document has narrow precedence over generic wording that treats Slack only as one global `#agent-dispatch` transport channel.

It does not supersede:

- canonical ownership in #214/#227;
- one-carrier/effect-unknown law;
- Agent Relay A2 release/canary sequence;
- Linear Initiative external carrier ownership;
- MAS-64/MAS-66/MAS-189 prerequisites;
- Executive runtime/Capacity/Wake authority; or
- full production acceptance law.

After this design and its implementation plan are protected, the exact first code wave is **WR-P0**: build the pure zero-network Workroom strategy/snapshot/desired-state planner and hostile fixtures. It may proceed independently of the live Initiative apply only if it performs zero Slack/Linear writes and treats the absent/finalizing Initiative rollout as an explicit input defect; live canary WR-C0 remains held until the Initiative and Linear Project normalization receipts are consumed.