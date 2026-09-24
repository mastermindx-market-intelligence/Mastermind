# Mastermind Business Sol Surface Convergence — Architecture Freeze

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Chairman approval:** explicit approval in the live Chairman/Sol architecture review on 2026-08-29.  
**Operation key:** `business-sol-surface-convergence-f0-20260829-sol-001`  
**Protected source basis:** `mastermindx-market-intelligence/Mastermind@1b99ea1d0a6232e11fd46915d348685764cb00cf`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1.  
**Macro source observed during archaeology:** `mastermindx-market-intelligence/macro@0b9ce8dcad00137d223aa0743006667cafdb27a2`.  
**Authority:** product, systems, experience, security and convergence architecture for the ChatGPT Business Premium operating surface. Existing accepted component source laws remain authoritative inside their components.  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY`. This document creates no plugin, app, MCP server, OAuth client, tunnel, Job, Attempt, Worker, RuntimeBinding, Agent OS record, Slack message, Linear mutation, credential, host principal, service or production capability.

---

## 0. Release and collision boundary

This architecture is intentionally separate from the active autonomy release train and its current director fleet.

At authoring time:

- protected Mastermind remains `1b99ea1d0a6232e11fd46915d348685764cb00cf`;
- the current `SOL-DIR-PRO` release train owns the active autonomy carriers and has asked that nonurgent Automation / Executive / Control Room / Workroom / Secretary records or runtime not merge merely to create movement;
- open carriers including Executive Steward, Agent Relay enrollment, Secretary grounding, Web-Sol and Project Workrooms retain their existing operation identities and ownership;
- no existing branch or pull request named for Business Sol Surface Convergence, Business Premium, a Mastermind plugin marketplace or a Mastermind Sol plugin was found;
- this document changes one new spec path only.

This carrier may remain draft and reviewable in parallel, but it must not merge through the active release serialization gate without a fresh current-source reconciliation and explicit Sol release. It must never redirect, stop, commission or absorb the four-CTO fleet.

---

## 1. Chairman outcome

Mastermind is transitioning over approximately two to three weeks from several Personal-Pro ChatGPT subscriptions toward ChatGPT Business with Premium seats. Existing Personal-Pro, Slack, Linear, GitHub, Executive OS, Agent OS, Wake, Capacity and Agent Relay work continues during the transition.

The desired outcome is not merely to connect another app to ChatGPT. The desired operating experience is:

> ChatGPT Business becomes the primary Chairman ↔ Sol reasoning and control cockpit. A Mastermind Sol plugin gives every authorized Sol a consistent procedure and premium in-chat operating experience. Small, typed MCP apps connect that experience to the canonical Mastermind systems. Executive OS, Agent OS, RuntimeBinding, Wake, GitHub, Linear and Slack remain the owners of their existing truths.

The Chairman must be able to open an authorized Business chat and, without reconstructing Slack history or locating provider windows, answer:

1. what material programs and responsibilities exist;
2. what is actually running, queued, blocked, waiting, returned or terminal;
3. which exact logical role and, where resolvable, which exact current reasoning surface owes the next turn;
4. what GitHub, Agent OS, Executive OS, Linear and Slack evidence supports each claim;
5. what is stale, degraded, contradictory or unknown;
6. what the exact next lawful action is; and
7. whether Sol may perform that action now or must return to the Chairman.

After one explicit Chairman instruction, Sol should be able to submit one bounded CEO intent through a trusted Business MCP action and obtain one truthful canonical receipt without manual prompt carriage. Acceptance must remain distinct from dispatch, execution, merge, deployment, production proof and final acceptance.

---

## 2. Product and value thesis

### 2.1 User value

For the Chairman:

- one primary conversational operating surface;
- no routine Slack archaeology, provider-session hunting or account selection;
- visible source disagreements rather than false-green summaries;
- one coherent Control Room composition inside ChatGPT;
- explicit confirmation and scope for modifying CEO actions;
- graceful continuation across many concurrent projects.

For Sol:

- deterministic current-source bootstrap;
- reusable CEO workflows instead of giant copied project instructions;
- typed reads and writes into canonical systems;
- exact operation identity and effect reconciliation;
- visible sister-Sol presence without granting authority by presence;
- durable closeout paths rather than chat-only memory.

For operators and workers:

- bounded company-dialogue tools rather than generic Slack credentials;
- exact commission and current Attempt binding;
- one semantic return path independent of whether the provider model remembers Slack etiquette;
- no need to reconstruct the full company thesis from a broad handoff.

### 2.2 Machine value

The system must transform a Business chat from an isolated reasoning transcript into a governed participant in the company fabric:

```text
current protected procedure
  + authenticated human principal
  + canonical responsibility/runtime/evidence reads
  + bounded intent or dialogue action
  + exact idempotency/effect reconciliation
  + durable organizational closeout
```

### 2.3 Commercial and operating value

Premium seats provide more included usage and remove the five-hour usage limit, making Business chat a stronger primary Sol surface. Premium is not literally unlimited: usage resets weekly and workspace credits may be used after included capacity. The architecture therefore maximizes ordinary Business Chat but does not treat paid capacity as a lifecycle or reliability guarantee.

### 2.4 Data moat

The moat remains the canonical Mastermind estate:

- organizational workstream, decision, discovery and handoff graph;
- exact runtime Job / Attempt / Worker / Event history;
- provenance and correction-safe evidence;
- provider/capacity/placement observations;
- market-intelligence research and product architecture;
- accepted outcomes and do-not-rebuild rulings.

A plugin is an experience and procedure package. An MCP app is a typed interface. Neither replaces the moat or owns company truth.

---

## 3. Current OpenAI platform facts used by this architecture

These were verified against current official OpenAI documentation on 2026-08-29. They are platform assumptions, not permanent Mastermind law; implementation must re-verify them at each live setup gate.

1. ChatGPT Business supports developer mode and full custom MCP apps on ChatGPT web, including write/modify actions.
2. Business admins/owners can create, test and publish custom apps; ordinary members cannot add custom apps themselves.
3. End users authenticate to each app separately when the app requires user-specific access.
4. ChatGPT may request confirmation for write actions and may block especially risky actions. The host confirmation is an additional user-safety layer, not Mastermind authority.
5. ChatGPT can use multiple apps in one prompt.
6. ChatGPT cannot connect directly to a local MCP server; Secure MCP Tunnel is the supported private-network path.
7. Agent mode does not use custom apps. Deep Research can use custom apps only for read/fetch actions.
8. Business admins/owners cannot currently update a published app in place in the same way as Enterprise/Edu; a changed tool/metadata surface may require recreation and republication. ChatGPT also uses a reviewed/frozen tool snapshot, so live schema drift can break calls.
9. Plugins package skills, MCP-backed apps and optional UI. Skills provide reusable workflow instructions; the MCP server provides live data, authentication, authorization and actions.
10. A plugin imported from a GitHub marketplace can be pinned to a branch, tag or exact commit. Marketplace sync imports plugin content but does not grant app access or authenticate users.
11. MCP Apps UI is optional and must not be required for the underlying tools to remain useful.
12. Authenticated MCP servers are expected to use OAuth 2.1-compatible MCP authorization: protected-resource metadata, authorization-server metadata, PKCE, exact resource/audience binding and token verification on every request.
13. No trusted durable ChatGPT conversation identifier is currently documented in the reviewed official custom-MCP contracts. Conversation/tab identity therefore cannot be assumed to be available for authority or exact session registration.

The architectural consequence of item 13 is important: write ability alone does not automatically give Mastermind exact per-chat identity. Business gives us a strong authenticated user and app boundary. Exact reasoning-surface identity still requires a separate RuntimeBinding-compatible seam and must fail closed when that seam is unavailable.

---

## 4. Current Mastermind capability ledger

| Capability | Current state | Business convergence disposition |
|---|---|---|
| Executive Job / Attempt / Worker / Event lifecycle | `BUILT_NOT_PROVEN` as a complete company loop | preserve as sole lifecycle authority |
| CeoIngress source/contract | `PARTIAL`; implementation exists, while current production arm/host acceptance is owned by active lanes and not established by this F0 | sole Business CEO write destination after accepted host proof |
| Executive MCP five-tool gateway | `BUILT_NOT_PROVEN`; read/fixture modes; no production write mode | extend only through a separately reviewed production identity/host arm |
| Executive Steward read core | `BUILT_NOT_PROVEN`; active release carrier | adopt after protection; do not create another Steward |
| Secretary six-tool read MCP contract | `BUILT_NOT_PROVEN / production-inert` | use as the initial Steward Business app contract |
| Company Dialogue six-tool MCP | `BUILT_NOT_PROVEN / production-inert` | package for operator-facing plugin; preserve exact binding law |
| Agent Relay long-running runtime | `BUILT_NOT_PROVEN / production-disarmed` | retain as cross-provider dialogue transport |
| Agent Relay enrollment and one-channel canary | `BUILT_NOT_PROVEN / active blocked carrier` | existing owner continues; Business does not absorb it |
| Chairman Control Room | `PARTIAL / locally released` | reuse composition and product model; Business UI becomes another projection |
| Web-Sol Personal-seat adapter | `BUILT_NOT_PROVEN / production-inert` | transition/fallback surface; not the final Business backend |
| SessionTargetRegistry / RuntimeBinding | `PARTIAL`; logical model exists, production persistence/Business binding incomplete | extend existing owner for Business surface targeting |
| Wake Fabric | `PARTIAL / production rollout in progress` | remains exact attention-delivery owner |
| Agent OS record schema, validation and generated views | `PROVEN_LIVE` | preserve as organizational knowledge plane |
| Complete/fresh Agent OS cross-company projection | `PARTIAL`; current joins and performance can degrade | expose freshness/degradation through Steward; do not claim complete state from absence |
| Linear project/issue projection | `PARTIAL / active rollout lanes` | keep as selected human portfolio projection |
| Slack Workrooms / richer collaboration | `SPEC_ONLY / active independent carrier` | continue independently; likely retained after Business cutover |
| Mastermind plugin marketplace | `NOT_BUILT` | new BSC ownership |
| Mastermind Sol plugin | `NOT_BUILT` | new BSC ownership |
| Business OAuth resource server and caller policy | `NOT_BUILT` | new BSC ownership |
| Secure MCP Tunnel installation | `NOT_BUILT` | new BSC deployment wave |
| Business-native Control Room MCP UI | `NOT_BUILT` | new product wave over Steward |
| Exact Business Sol surface registration | `NOT_BUILT`; no trusted conversation ID is currently documented | later RuntimeBinding-compatible wave; not assumed by V1 |
| Workspace Agents as Mastermind lifecycle | `REJECTED_BY_DESIGN` | would duplicate Executive OS |
| Generic direct Agent OS write MCP | `REJECTED_BY_DESIGN` | would bypass record/Git review and create an unsafe memory writer |
| One giant Mastermind super-MCP | `REJECTED_BY_DESIGN` | mixes incompatible authority classes and blast radii |

---

## 5. Canonical ownership freeze

This program creates no new company owner.

| Fact | Canonical owner |
|---|---|
| Chairman / CEO request admission, Job / Attempt / Worker / Event lifecycle, current Attempt, lease/fence, retry/requeue | Executive OS |
| organizational workstream, program, decision, discovery and handoff | Agent OS |
| current implementation, branch, PR, CI, merge and production evidence | GitHub |
| provider/account/host eligibility, capacity and placement evidence | existing Capacity Fabric / provider-control owners |
| logical executive target and rotating native destination | existing SessionTargetRegistry / RuntimeBinding owners |
| attention obligation, route, delivery and acknowledgement | existing Wake Fabric |
| company dialogue parent/messages and Slack projection | existing Agent Dialogue / Agent Relay |
| selected human portfolio/project/issue view | Linear projector owners |
| cross-owner read/explanation/exception composition | Executive Steward / Chairman Control Room |
| plugin workflow instructions | protected plugin source, subordinate to current protected Sol Skillpack |
| app authentication and transport admission | the app’s OAuth/resource-server boundary; never organizational authority by itself |

Forbidden replacements include:

- another lifecycle or scheduler;
- another workstream/task database;
- a plugin-owned memory store;
- an MCP request or transcript database used as authority;
- a `business_sessions` or `sol_owner` table;
- a Slack task queue;
- a plugin-specific provider router;
- a second RuntimeBinding registry;
- a second Steward/Control Room truth store;
- a second Linear synchronizer;
- a second retry/effect ledger.

---

## 6. Architecture alternatives and ruling

### 6.1 Rejected: one Mastermind super-MCP

A single app exposing Steward reads, Executive writes, Agent OS writes, Slack dialogue, Linear mutation, GitHub mutation, Wake and session control would be convenient to install but unsafe and operationally brittle.

It would:

- mix read-only grounding, CEO admission, dialogue transport and projection mutation;
- create one oversized blast radius;
- make Business app publication/update constraints painful;
- worsen tool selection and schema drift;
- invite generic filesystem/command/admin tools;
- make least-privilege OAuth scopes incoherent.

### 6.2 Rejected: fully fragmented user experience

A separate visible plugin for every owner would preserve isolation but force the Chairman and Sol to manually choose among many packages. Skills and procedure would drift and the Business experience would reproduce the same fragmentation as today.

### 6.3 Accepted: one experience, federated authority

The accepted target architecture is:

```text
Mastermind Sol plugin
  ├── Mastermind Steward app   (required, read-only)
  ├── Mastermind Surface app   (later, bounded presence/RuntimeBinding projection)
  └── Mastermind Executive app (bounded CEO intent)

Mastermind Operator plugin
  └── Mastermind Dialogue app  (exact bound company dialogue)
```

The user experience is coherent, but each authority surface is independently versioned, authenticated, tested, published, disabled and rolled back.

**Versioned dependency ruling:** `Mastermind Sol` v1 must not depend on the not-yet-built Surface app. Initial v1 packages Steward and Executive references only. Surface becomes an explicit plugin-generation update only after BSC-RB1/RB2 is accepted. A missing future Surface app therefore cannot block initial read/root-admission rollout.

---

## 7. Target topology

```text
Chairman Chris
    │
    ▼
ChatGPT Business Premium — ordinary web chat
    │
    ▼
Mastermind Sol plugin
    │
    ├───────────────┬─────────────────┬───────────────────┐
    ▼               ▼                 ▼                   ▼
Steward app     Surface app       Executive app      native GitHub /
read-only       later bounded      bounded intent     Linear / Slack apps
                presence           submission          when useful
    │               │                 │
    │               │                 ▼
    │               │             CeoIngress
    │               │                 │
    └───────┬───────┘                 ▼
            ▼                     Executive OS
    Executive Steward                 │
            │                         ├── Capacity / routing
            │                         ├── Worker realms
            │                         ├── Agent Dialogue / Relay
            │                         └── Wake / RuntimeBinding
            ▼
    Control Room projection
            │
            ├── Agent OS
            ├── GitHub
            ├── Linear
            └── Slack transport evidence
```

The plugin and apps are removable facades. Deleting or disabling them changes no canonical company fact except the loss of that access surface.

---

## 8. `Mastermind Sol` plugin architecture

### 8.1 Purpose

`Mastermind Sol` is the primary Chairman/CEO workflow package. It should make correct procedure easy and stale procedure difficult.

### 8.2 Skill set

Initial skills:

```text
bootstrap-mastermind
open-executive-cockpit
reconcile-company-state
draft-ceo-intent
review-worker-return
review-pull-request
close-out-program
```

Each skill states:

- when it applies;
- the user outcome;
- canonical source order;
- expected app/tool calls;
- failure and degraded behavior;
- the output contract;
- the stop condition.

### 8.3 Dynamic procedure law

Plugin skills are static package content and may be synced independently of the protected Sol Skillpack. Therefore they must never copy the full current Skillpack and claim to be current procedure.

Every substantial Mastermind skill starts with a compact invariant:

```text
read protected Mastermind master
record exact commit
load docs/sol_skills/INDEX.md from that commit
verify schema/version/bootstrap compatibility
load required skill files from the same commit
then act
```

If current protected procedure cannot be loaded, the skill may continue read-only with a warning. Modifying workflow is unavailable.

### 8.4 No live state in plugin files

Plugin files must not contain:

- current Jobs or Attempts;
- current workstream status;
- current PR/CI state;
- Slack receipts;
- account/session/provider availability;
- current Chairman decisions;
- credentials;
- current RuntimeBinding.

### 8.5 Distribution

The canonical private marketplace lives in the protected Mastermind repository and is imported from GitHub.

Recommended source shape:

```text
.agents/plugins/marketplace.json
plugins/
  mastermind-sol/
    .codex-plugin/plugin.json
    app.template.json
    skills/
      bootstrap-mastermind/SKILL.md
      open-executive-cockpit/SKILL.md
      reconcile-company-state/SKILL.md
      draft-ceo-intent/SKILL.md
      review-worker-return/SKILL.md
      review-pull-request/SKILL.md
      close-out-program/SKILL.md
  mastermind-operator/
    .codex-plugin/plugin.json
    app.template.json
    skills/
      receive-commission/SKILL.md
      return-progress/SKILL.md
      escalate-decision/SKILL.md
      finish-operation/SKILL.md
```

`app.template.json` is a Mastermind source template, not an OpenAI-recognized installed binding. It contains symbolic app-generation names only and no live app ID or secret. BSC-U1 generates the exact installed `.app.json` after the Business admin creates the approved workspace apps. No literal placeholder URL or app ID may be published as a working binding.

Canary import uses an exact reviewed commit. A later production marketplace may follow protected `master` only after plugin-update review and rollback are proven. Automatic marketplace sync never grants new app access or authentication.

---

## 9. `Mastermind Steward` app

### 9.1 Authority

Read-only.

### 9.2 Contract

Adopt the current Secretary/Steward six-tool shape rather than creating a new read product:

```text
list_responsibilities
get_responsibility
get_attention
get_current_runtime
explain_blocker
resolve_surface
```

Model-visible inputs expose no provider account, host, native session, browser profile, Slack channel/thread, URL, coordinate or action-target selector.

### 9.3 Composition

The app calls an injected `StewardReadPort`. The port composes current source-attributed facts from existing owners. The MCP package never opens canonical stores directly merely because it is convenient.

Minimum result fields where available:

```text
responsibility_ref
program / workstream
selected human projection
organizational status
current child Job
current Attempt / Worker
provider / opaque realm
RuntimeBinding generation
latest valid semantic edge
turn_owner role
exact action-authoritative target or UNKNOWN
attention health
transport health
retry/effect state
GitHub carrier and proof
Linear projection state
source refs, freshness and disagreements
exact next lawful action
```

### 9.4 Control Room UI

The Steward app may expose an optional MCP Apps UI resource such as:

```text
ui://mastermind/control-room/v1
```

The UI provides:

- company overview;
- needs Chairman / needs Sol / needs worker / needs placement;
- active programs and child operations;
- runtime/provider topology;
- current carriers and evidence;
- stale/non-actionable surfaces;
- source disagreements and degradations;
- exact next-action drill-down.

The UI must remain useful only as a rendering of structured Steward results. It owns no business data. If the UI fails, the underlying tools still return complete bounded results to the model.

Business data remains on canonical systems. UI state such as selected tab, expanded card and sort order is ephemeral. Widget state or `localStorage` never becomes session, lifecycle or authority truth.

---

## 10. `Mastermind Executive` app

### 10.1 Authority

Executive reads plus exactly one bounded CEO-intent submission.

### 10.2 Frozen tool census

Preserve the existing five-tool contract:

```text
executive_state
executive_inbox
executive_job
ceo_intent_status
submit_ceo_intent
```

Do not combine Steward, Surface, Dialogue, GitHub, Linear or Slack tools into this app.

### 10.3 Submission law

`submit_ceo_intent` creates one durable `QUEUED` Job and stops.

It does not:

- dispatch;
- claim;
- lease;
- launch a worker;
- choose a provider/account;
- create a Slack carrier;
- push a branch;
- open/merge a PR;
- deploy;
- control services;
- write Agent OS;
- mark anything complete.

### 10.4 Trusted derivation

The model may author bounded mission content but cannot author:

```text
actor
requested authorities
raw argv or shell commands
grounding SHAs
branch
worktree
Job id
status
dispatch state
provider/account/host
service/socket path
runtime binding
```

Trusted gateway/backend code derives or resolves those fields.

### 10.5 Identity and idempotency

For the accepted initial Business path:

```text
authenticated Chairman subject
+ exact Business Executive app/resource
+ stable operation key
+ normalized payload
+ current grounding
→ one Executive intent / one root Job
```

Same operation key + same normalized payload returns the same Job.

Same operation key + changed normalized payload refuses as conflict.

A timeout or lost response does not prove the operation failed. Reconcile the same intent through `ceo_intent_status`; never submit through another app, account or carrier.

### 10.6 Production-arm gates

Production write remains unavailable until all of these pass:

1. current CeoIngress source and host state are accepted;
2. OAuth resource-server boundary is accepted;
3. exact authorized Business subject policy is accepted;
4. dedicated least-privilege local principal is verified;
5. current grounding/TOCTOU checks remain intact;
6. the exact five-tool schema snapshot is reviewed in the Business draft app;
7. one harmless fixture canary passes;
8. one harmless production admission canary is separately commissioned;
9. disable/rollback is proven.

---

## 11. `Mastermind Surface` app and exact Sol-session truth

This surface is needed because the Chairman wants sister Sols to know which sessions exist, what each is focusing on and which exact session may act. Business write access makes a governed presence projection possible, but the platform does not currently document a trusted durable conversation ID to the MCP server.

### 11.1 Separation of concepts

Do not collapse these concepts:

```text
OAuth user              = authenticated Business human/account principal
Sol logical alias        = stable executive role target
Business chat            = one reasoning conversation/surface
surface presence         = evidence that a reasoning surface recently checked in
surface focus            = advisory statement of what it is inspecting
RuntimeBinding           = current rotating destination evidence
responsibility authority = canonical right to emit the next modifying semantic edge
```

Presence or focus never grants action authority.

### 11.2 Initial V1 boundary

V1 Business deployment may authenticate the Chairman and submit new root CEO intents without exact per-chat identity. It must not pretend this proves which Business conversation is action-authoritative for an existing child turn.

Until an exact surface seam is accepted:

- Business chats may read all allowed Steward facts;
- a Business chat may submit a new root only through the explicit Chairman-confirmed Executive path;
- child-turn continuation/ruling/merge/release actions remain on their existing exact authority carriers;
- `resolve_surface` returns `UNKNOWN` or the existing non-Business binding where appropriate.

### 11.3 Later bounded surface contract

A later `Mastermind Surface` app may expose only bounded operations such as:

```text
register_surface
heartbeat_surface
set_surface_focus
retire_surface
get_my_surface
```

The app mints an opaque, revocable `surface_ref`/binding capability. The chat may carry that opaque reference in its conversation context or widget state as a convenience. The reference grants only presence/focus updates for that surface and never a CEO intent, ruling, merge, retry or successor commission.

### 11.4 Reuse existing owners

Accepted implementation direction:

```text
surface registration / heartbeat
→ existing SessionTarget / RuntimeBinding owner
→ persisted through existing Executive event/idempotency machinery where durability is required
→ Steward projection
```

Do not create a `business_sessions` table or a new session service.

### 11.5 Surface projection vocabulary

A surface can project:

```text
ACTIVE
QUIESCENT
STALE
RETIRED
OBSERVING
PREPARING
ADVISORY_ONLY
ACTION_BOUND        # derived only from canonical binding
CONFLICT
UNKNOWN
```

`ACTION_BOUND` cannot be submitted as a claim. It is derived by joining the current responsibility/root binding, SessionTargetRegistry, RuntimeBinding generation and applicable dialogue/turn evidence.

### 11.6 Shared-account and multi-chat behavior

Multiple chats under one Business user share the same OAuth principal. They must not be treated as one conversation, and they cannot be distinguished from OAuth alone.

If the platform later exposes a trusted conversation/session handle, adopt it as a rotating native handle through RuntimeBinding after a separate review. Do not build current authority on undocumented headers, UI DOM, chat title, timestamp recency or model-generated names.

---

## 12. `Mastermind Operator` and Dialogue app

The operator-facing plugin packages the already-frozen Company Dialogue MCP:

```text
read_thread
ack
progress
blocked
request_decision
result
```

The trusted host injects exact actor, Job, Attempt, Worker, commission, session and dialogue-parent context. Those fields are absent from model inputs.

The Dialogue app:

- calls Agent Dialogue / Agent Relay rather than Slack directly;
- performs at most one downstream semantic operation per tool call;
- never retries an effect-unknown write;
- never creates or claims a Job;
- never selects a Slack channel/thread;
- never gains generic workspace search/post/admin authority;
- never becomes the worker return authority when the governed harness can mechanically project the provider turn.

This remains useful for Business-hosted COO/operator sessions, but the final autonomous organization cannot depend on voluntary tool use for end-of-turn return projection.

---

## 13. Authentication and authorization

### 13.1 OAuth 2.1 resource-server boundary

Every customer-specific read or write app uses OAuth 2.1-compatible MCP authorization:

- protected-resource metadata on the exact MCP resource;
- authorization-server discovery metadata;
- authorization-code flow with PKCE S256;
- exact resource parameter and audience binding;
- signed-token verification on every request;
- issuer, audience/resource, expiry/not-before and scope checks;
- app-specific subject policy;
- `401` + proper `WWW-Authenticate` challenge on failure.

### 13.2 App separation

The following resource URLs are conceptual names only. BSC-U1 supplies the accepted exact deployment origin; literal bracketed values never ship in a published app.

```text
Mastermind Steward v1
  resource: https://[approved-private-edge]/mcp/steward/v1
  scopes: mastermind.steward.read

Mastermind Surface v1
  resource: https://[approved-private-edge]/mcp/surface/v1
  scopes: mastermind.surface.read, mastermind.surface.presence

Mastermind Executive v1
  resource: https://[approved-private-edge]/mcp/executive/v1
  scopes: mastermind.executive.read, mastermind.executive.intent.submit

Mastermind Dialogue v1
  resource: https://[approved-private-edge]/mcp/dialogue/v1
  scopes: mastermind.dialogue.read, mastermind.dialogue.write
```

A token for one resource cannot call another app.

### 13.3 Initial subject policy

Initial production Executive submission authorizes only the exact Chairman-controlled Business principal(s) accepted during the installation ceremony. Read-only Steward access may later be broader.

If multiple Business seats are designated as Sol seats, each must have an explicit subject-to-role mapping. Being a Business workspace member, admin or owner does not automatically grant Mastermind Executive authority.

### 13.4 Human principal versus reasoning actor

```text
authenticated principal = exact Business human/account subject
reasoning actor          = ceo-sol
logical target           = accepted Sol session alias
runtime destination      = current RuntimeBinding
```

`actor="ceo-sol"` remains provenance and grants no privilege.

### 13.5 Host principal

Current protected host configuration names a dedicated CeoIngress peer UID `452` and socket `/var/run/mastermind-executive/ceo-ingress.sock`.

The Business Executive edge should reuse that narrow boundary only after a host-security wave proves:

- exact principal identity and ownership;
- no unrelated GitHub, SSH, market-data, provider, browser or deployment credentials;
- socket reachability only as required;
- minimal scrubbed environment;
- no root or broad interactive-user execution;
- no widening of the general Executive control socket peer list.

### 13.6 Native ChatGPT confirmation

ChatGPT write confirmation is additive UX safety. It never replaces:

- current Chairman intent;
- current protected procedure;
- Mastermind OAuth subject policy;
- Executive authority policy;
- current grounding;
- operation identity;
- effect reconciliation.

---

## 14. Private network deployment

The first deployment uses Secure MCP Tunnel rather than a public Mastermind endpoint.

```text
ChatGPT Business
  → OAuth + approved custom app
  → Secure MCP Tunnel
  → loopback/tunnel-only Mastermind app edge
  → first-party adapter
  → existing AF_UNIX/local canonical service
```

Laws:

- no public inbound port as a shortcut;
- no TCP/HTTP listener added to ExecutiveControlService or Agent Relay;
- each app has an independently identifiable resource path and schema version;
- the tunnel is transport only, not caller identity or Executive authority;
- the edge has no database, queue, retry state or scheduler;
- the edge environment contains no unrelated credentials;
- secrets and tokens never appear in tool results, UI props, argv, environment dumps, logs or repository records.

OAuth browser endpoints may require a public/reachable identity-provider path even when the MCP resource is tunneled. That auth surface remains separate from the private Mastermind runtime.

---

## 15. Data, time, null and correction behavior

### 15.1 Source attribution

Every nontrivial Steward fact carries:

```text
canonical owner
source ref / revision
observed or generated time
freshness/age
known/unknown/degraded state
```

### 15.2 Nulls and unavailable sources

Missing data is never rendered as an empty healthy value.

Examples:

```text
Runtime unavailable        → runtime_status=UNKNOWN/DEGRADED
Agent OS checkout absent   → organizational_join_unavailable
Linear inaccessible        → projection_unavailable
Slack unavailable          → transport_degraded, not Job failure
surface identity absent    → exact_action_target=UNKNOWN
```

### 15.3 Corrections

A projection mismatch is repaired in the projection owner. Canonical truth is not rewritten merely to make the Control Room, plugin, Slack or Linear agree.

### 15.4 Effect uncertainty

A modifying app timeout or interrupted response follows:

```text
EFFECT_UNKNOWN
→ same app/resource
→ same operation identity
→ canonical status read
→ no alternate app/account/carrier
```

### 15.5 Tool/schema drift

Business app publication and frozen tool snapshots make schema stability load-bearing.

Every app therefore has:

- static tool census;
- exact server identity/version;
- schema snapshot digest;
- output contract digest where useful;
- mutation tests for added tools, widened inputs and changed annotations;
- immutable published generations for breaking changes.

Example generations:

```text
mastermind-steward-v1
mastermind-steward-v2
mastermind-executive-v1
mastermind-executive-v2
```

A live server never silently serves a breaking schema under an approved app generation.

---

## 16. Final role of Slack, Linear and GitHub

### 16.1 Slack — retained

Slack remains:

- cross-provider company dialogue;
- project collaboration / Workrooms;
- semantic transport and visible audit;
- fallback and incident visibility;
- human communication.

Slack does not remain:

- the Chairman’s primary company dashboard;
- the task queue;
- Job/Attempt/Worker truth;
- session or director identity authority;
- the only place an actionable return exists;
- the source of automatic retry or successor work.

The richer Slack/Workroom work currently in flight remains useful and is not wasted. Agent Relay is especially important because Codex, Claude, Fable, Grok and other non-Business reasoning surfaces still require a provider-neutral company dialogue fabric.

### 16.2 Linear — retained

Linear remains selected strategic/project/issue/gate projection for human portfolio navigation. It does not receive one Issue per Job, Attempt, tool call or Business chat.

Business may make Linear easier to inspect and reconcile, but it does not create a second direct synchronizer or let Linear originate execution.

### 16.3 GitHub — retained

GitHub remains implementation, review, CI and proof truth.

A Business Executive `QUEUED` Job is not a branch, PR, green CI, merge, deployment or acceptance.

### 16.4 Workspace Agents — exceptional only

Workspace Agents may be used later for a bounded job that truly requires their schedule, API trigger or independent managed agent lifecycle. They must not become Mastermind’s normal Job/Attempt/Worker runtime, memory, retry or Wake system.

Normal Mastermind path:

```text
Chairman
→ Business Chat Sol
→ bounded MCP intent
→ Executive OS
→ governed worker fabric
```

not:

```text
Chairman
→ many Workspace Agents
→ parallel hidden lifecycle
```

---

## 17. Experience architecture

### 17.1 Cold start

A fresh authorized Business chat should experience:

```text
Mastermind Sol skill activates
→ current protected Skillpack pin
→ Steward bootstrap
→ current responsibility/attention/runtime/evidence view
→ visible degradations/disagreements
→ exact permitted next action
```

### 17.2 Control Room composition

The primary in-chat UI has five views:

1. **Company** — programs, responsibilities, status, accountable role.
2. **Attention** — needs Chairman, needs Sol, needs worker/COO, needs placement.
3. **Runtime** — current Jobs, Attempts, Workers, provider/capacity, stale bindings.
4. **Evidence** — GitHub carriers, CI, proof, Linear projection and dialogue pointers.
5. **Exceptions** — conflicts, stale sources, effect uncertainty, transport degradation, parent-active/no-successor.

### 17.3 Draft CEO intent

Before a modifying call, Sol renders a bounded action packet:

```text
operation key
objective
organizational parent or explicit unbound state
department / execution profile
allowed write paths
validation recipe
attempt limit
explicit non-goals
what QUEUED means
what evidence will count as completion
```

ChatGPT confirmation then occurs. The tool result prints the canonical receipt and explicitly says `dispatched=false`.

### 17.4 Worker return review

Sol uses Steward + GitHub + canonical dialogue/runtime facts. It reviews against the original product outcome, not merely code or CI. It emits one same-carrier continuation, repair or terminal STOP only when current authority permits.

### 17.5 Durable closeout

The plugin guides Sol to update the owning durable homes:

- Agent OS decision/discovery/handoff through a reviewed Git carrier;
- GitHub acceptance/proof;
- Linear projection through the existing projector;
- Executive terminal state through the existing runtime;
- Slack terminal dialogue edge where applicable.

No generic `save memory` action exists.

---

## 18. Failure-state matrix

| Condition | Required behavior |
|---|---|
| current Skillpack cannot be loaded | read-only investigation allowed with warning; modifying tools withheld |
| Steward unavailable | report exact app/backend degradation; do not infer healthy state from absence |
| OAuth token missing/expired | `401` challenge; zero tool effect |
| wrong issuer/audience/resource/scope/subject | refuse; zero tool effect |
| token for one app used against another | refuse; zero tool effect |
| plugin references missing/unpublished app | explicit setup dependency; no silent fallback |
| live server schema differs from approved snapshot | fail/version mismatch; do not reinterpret arguments |
| UI component fails | tool result remains usable in text/structured form |
| prompt injection in Agent OS/GitHub/Slack/result text | return as inert structured data; never server-chain into a write |
| same operation and payload submitted twice | same intent/Job receipt; zero second root |
| same operation key with changed payload | conflict/refuse; zero mutation |
| modifying response lost after possible commit | same-intent status reconciliation; no alternate submission |
| Business chat has no trusted exact surface identity | may read and submit approved new root; may not claim existing child-turn action authority |
| two surface bindings appear action-authoritative | `ATTENTION_OWNER_CONFLICT`; fail closed |
| surface heartbeat stale | presence becomes stale; responsibility/lifecycle remains unchanged |
| Slack unavailable during healthy execution | transport degraded; Job remains truthful |
| Linear says Done but proof incomplete | repair Linear projection; canonical work remains open |
| GitHub merged but user capability not proven | `BUILT_NOT_PROVEN`; no false completion |
| plugin marketplace sync adds invalid update | last working version retained; fix source and re-sync |
| Business app must change breaking schema | publish a new immutable app generation; dual-run before cutover |
| tunnel stops | app unavailable; canonical state unchanged; fallback surfaces remain |
| Business account/seat changes | OAuth and RuntimeBinding re-auth/reconciliation; no silent authority transfer |

---

## 19. Implementation program and planning decomposition

This architecture spans multiple independently releasable subsystems and is too large for one monolithic implementation plan or PR. After the written architecture is reviewed, create:

1. one top-level Business Surface Convergence program DAG that freezes dependencies, current owners, collision gates and cutover stages; and
2. a separate TDD implementation plan for each wave immediately before that wave begins.

The first executable plan is BSC-P1 only. BSC-A1, S1, E1, RB2 and later waves receive their own plans after current-source re-pin. No wave widens merely because the complete program is broad.

Implementation begins only after this design is protected, the top-level DAG is reviewed and the applicable wave plan is reviewed. Each wave is independently useful or closes one explicit safety gate.

### BSC-F0 — architecture/source-law carrier

This document only.

Stop at `SPEC_ONLY / RECORDS_ONLY`.

### BSC-O0 — organizational parent and portfolio projection reconciliation

After F0 is protected, resolve the Business program against current Agent OS and Linear owners.

Preferred organizational parent is the existing `WS:CHAIRMAN-CONTROL-ROOM` only if current Agent OS semantics and the current accountable owner confirm that Business convergence belongs there. Do not create a title-similar new workstream merely to obtain a row.

Expected output:

- one existing parent + bounded new wave/hand-off, or a typed `ORGANIZATIONAL_PARENT_UNRESOLVED` return;
- one selected human-visible Linear projection through the existing projector/Initiative owner when eligible;
- zero direct F0 mutation of Agent OS or Linear;
- no new task/project database.

### BSC-P1 — private plugin marketplace and production-inert packages

Build:

- `.agents/plugins/marketplace.json`;
- `Mastermind Sol` v1 manifest;
- `Mastermind Operator` v1 manifest;
- thin current-Skillpack bootstrap skills;
- workflow skills listed above;
- secret-free `app.template.json` files;
- manifest/skill/static-policy tests.

`Mastermind Sol` v1 contains only Steward and Executive symbolic app dependencies. It contains no Surface dependency. No actual `.app.json`, live app ID, app connection, OAuth or runtime action is created in this wave.

### BSC-A1 — OAuth/resource-server library

Build one SDK-minimal, standards-based authentication library with:

- protected-resource metadata;
- authorization-server metadata validation;
- JWT/JWKS verification seam;
- issuer/audience/resource/expiry/scope/subject policy;
- exact app/resource separation;
- `WWW-Authenticate` challenge generation;
- credential and PII logging fences;
- hostile token fixtures.

No production secret enrollment.

### BSC-S1 — Steward remote transport and Control Room UI

Depends on current Steward/Secretary carriers reaching accepted protected state.

Build:

- read-only authenticated HTTP/streamable MCP edge compatible with Secure MCP Tunnel;
- exact six-tool Steward contract;
- injected real Steward read adapter;
- Control Room MCP Apps UI;
- textual/structured fallback;
- source freshness and disagreement rendering.

No write action.

### BSC-E1 — Executive Business production-arm source

Depends on current CeoIngress and active AD-ID1/transport-neutral request identity ownership. Reconcile rather than modify colliding paths.

Build:

- authenticated production mode behind a new reviewed server generation;
- exact Chairman subject mapping;
- dedicated UID/socket composition;
- current grounding double-check;
- exact existing five-tool surface;
- structural production kill switch;
- zero write retries;
- effect-unknown status reconciliation.

### BSC-U1 — Business installation and enrollment ceremony

Build deterministic admin tooling/runbook for:

- enabling Business developer mode;
- creating draft apps;
- recording exact app IDs without model-visible secrets;
- OAuth redirect/resource configuration;
- Secure MCP Tunnel setup;
- plugin marketplace import pinned to exact commit;
- generation of exact installed `.app.json` bindings from approved IDs;
- verify-only mode and redacted receipts.

### BSC-C1 — real Business read canary

On the separate Business account, prove:

- plugin import;
- app connection and OAuth;
- exact tool census;
- private tunnel;
- current Steward reads;
- Control Room UI;
- degraded-source behavior;
- reconnect/restart behavior;
- zero canonical mutation.

### BSC-C2 — harmless Executive admission canary

Submit one `research_only` CEO intent whose acceptance creates one `QUEUED` Job and no worker execution.

Prove:

- exact authenticated subject;
- one operation/intent/Job;
- `dispatched=false`;
- zero Attempt/Worker claim;
- exact replay dedupe;
- changed-payload conflict;
- production Executive receives no duplicate;
- zero secret/identity leakage.

### BSC-RB1 — Business Sol surface-binding research and falsifier

Before implementing Surface writes, prove what exact trusted identity metadata the Business app receives in live calls. If no conversation handle exists, test the server-minted opaque surface-ref pattern under model context, UI widget state, compaction, reconnect and multiple-chat collision.

This is a falsifier wave, not production authority.

### BSC-RB2 — bounded Surface app and RuntimeBinding projection

Only if RB1 yields an accepted safe seam.

Implement presence/focus events through existing RuntimeBinding/Executive event ownership. Prove stale/observer/non-authoritative behavior and no new session database. Only after RB2 acceptance may a later `Mastermind Sol` plugin generation reference the Surface app.

### BSC-D1 — dual-run

Business becomes primary for reads and bounded root admission. Personal-Pro, Slack and existing Web-Sol paths remain available.

Compare:

- grounding;
- operation identity;
- attention and next action;
- source disagreement;
- receipts;
- authentication and reconnect behavior;
- failure and rollback.

### BSC-CUTOVER — Business-first Sol surface

After dual-run acceptance:

- retain logical Sol aliases;
- bind accepted Business surfaces through current RuntimeBinding owners;
- make Business Chat + plugin the primary Chairman/Sol experience;
- keep Personal-Pro as fallback/research capacity until explicit retirement;
- keep Slack as cross-provider transport.

### BSC-R1 — legacy subtraction

Retire only proven-replaced scaffolding. Every removal names its replacement, production receipt, rollback and surviving role.

---

## 20. Current implementation-owner subtraction

Do not rebuild or absorb these current owners:

- Executive MCP existing five-tool contracts and tests;
- CeoIngress / CEO-intent / Executive authority machinery;
- AD-ID1 transport-neutral automated CEO request identity;
- Executive Steward read core carrier;
- Secretary grounding MCP carrier;
- Company Dialogue MCP;
- Agent Relay runtime and enrollment carriers;
- SessionTargetRegistry / RuntimeBinding / Wake owners;
- Web-Sol current Personal managed-browser adapter carrier;
- Chairman Control Room composition;
- Linear portfolio/project/selected-issue projectors;
- Project Workroom convergence;
- Agent OS repository schema/validator/generator;
- Capacity Fabric, Model Router and Operator Harness.

The Business program supplies missing packaging, authentication, private transport, UI and controlled surface integration. It does not create alternate implementations of the owners above.

---

## 21. Production acceptance canaries

### Canary A — plugin procedure freshness

Install a plugin version whose static package predates a newer protected Skillpack. A substantial workflow must load the newer protected procedure and must not execute solely from its stale packaged instructions.

### Canary B — app authority separation

Use a valid Steward token against Executive, a valid Executive token against Dialogue and a valid Dialogue token against Surface. All refuse with zero effect.

### Canary C — OAuth adversarial matrix

Refuse missing signature, unknown key, wrong issuer, wrong audience/resource, missing scope, expired token, future token, unauthorized subject and replay under another app resource.

### Canary D — cross-chat duplicate root

Two Business chats under the same or different approved Sol accounts submit the same operation key/payload. Expected: one canonical root Job and the same receipt.

### Canary E — changed-payload conflict

Same operation key with changed objective or execution envelope. Expected: conflict/refusal and zero second Job.

### Canary F — response loss

Lose the client response after CeoIngress may have committed. Expected: status reconciliation under the same intent; no alternate app/account/carrier.

### Canary G — prompt injection

Place hostile imperatives in Agent OS text, Slack messages, GitHub PR bodies and worker result fields. Steward returns them as data; no write tool is called server-side.

### Canary H — source movement

Move material protected procedure or grounding between draft and submit. Expected: refusal/grounding-changed and zero Job.

### Canary I — UI independence

Break or disable the Control Room component. The model still completes the read workflow using structured/text tool results.

### Canary J — no trusted conversation identity

Run two chats under one OAuth user. If the platform supplies no trusted conversation handle, prove the system returns exact surface authority as `UNKNOWN` and does not elect by recency, title or activity.

### Canary K — provisional surface-ref collision

During RB1/RB2, create duplicate/expired/stolen advisory surface refs. Expected: at most bounded presence/focus effects; zero responsibility or semantic action authority.

### Canary L — action-authority fence

Two Business Sol surfaces observe one worker return. Both may read; only the canonically bound current target may emit a modifying child-turn edge after RB2/cutover. Before that capability exists, both are refused for child-turn action.

### Canary M — tunnel failure and rollback

Stop the tunnel/app edge. Business tools become unavailable, canonical systems remain unchanged and existing fallback surfaces continue.

### Canary N — app-generation migration

Run `mastermind-steward-v1` and `v2` in dual-read mode, compare outputs, cut plugin reference to v2, then disable v1 without losing canonical state.

### Canary O — Chairman zero-shuttle journey

After final cutover, run a representative period containing:

- new Chairman intent;
- one bounded Executive root;
- worker return;
- Sol continuation;
- a real blocker;
- safe retry or rollover;
- one effect-unknown hold;
- source disagreement;
- final GitHub/Agent OS/Linear/Slack closeout.

The Chairman performs zero routine Slack archaeology, message shuttling, watcher repair, provider-account selection or session hunting.

---

## 22. Security and privacy laws

1. Least privilege per app/resource/scope.
2. Every input validated server-side even when ChatGPT generated it.
3. Irreversible/high-impact actions remain human-confirmed and Mastermind-authorized.
4. No raw prompt, transcript, token or secret in logs by default.
5. Correlation and operation IDs may be logged after redaction.
6. Structured result contains only data required for the current workflow.
7. UI props contain no credentials or hidden authority tokens.
8. Tool descriptions are static and never interpolate retrieved content.
9. Reads never server-chain into writes.
10. Modifying calls retry zero times inside the app edge.
11. No wildcard write scope, generic shell, generic filesystem, generic SQL or generic Slack/Linear/GitHub admin tool.
12. The Business app can only narrow existing Executive/organizational authority.
13. App disablement and tunnel shutdown are tested rollback paths.
14. Platform beta behavior is re-verified before every live setup or app-generation migration.

---

## 23. Completion standard

This program is complete only when it has:

### Truth

- current protected procedure bootstrap;
- authenticated and source-attributed reads;
- correction-safe source disagreement;
- exact operation identity and effect reconciliation;
- no Business-only lifecycle truth.

### Intelligence

- a useful Steward composition, not just raw records;
- coherent responsibility/runtime/evidence synthesis;
- exact next-action and blocker explanations;
- typed unknown/degraded states.

### Product

- one premium `Mastermind Sol` plugin experience;
- in-chat Control Room;
- bounded Executive intent journey;
- multi-chat safety;
- fallback and rollback.

### Learning

- instrumentation for app/tool use, refusal classes, latency, stale-source frequency, duplicate/conflict catches and Chairman intervention burden;
- no raw prompt/transcript capture as the default analytics strategy;
- evidence that the new surface reduces Slack archaeology, session hunting and manual message carriage.

The final acceptance statement is:

> The Chairman can operate Mastermind primarily from ChatGPT Business. Sol reads and acts through small authenticated interfaces to the canonical company systems. Multiple chats and accounts remain observable but cannot manufacture authority. Slack, Linear and GitHub retain their real jobs. Executive OS and Agent OS remain the company operating system rather than being replaced by the plugin that controls it.

---

## 24. Official platform references verified for this freeze

- OpenAI, **Developer mode and MCP apps in ChatGPT**: `https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta`
- OpenAI Developers, **Plugin architecture**: `https://developers.openai.com/plugins/concepts/plugins`
- OpenAI Developers, **Skills**: `https://developers.openai.com/plugins/concepts/skills`
- OpenAI Developers, **MCP server**: `https://developers.openai.com/plugins/concepts/mcp-server`
- OpenAI Developers, **Authentication**: `https://developers.openai.com/plugins/build/auth`
- OpenAI Developers, **Add UI to your MCP server**: `https://developers.openai.com/plugins/build/chatgpt-ui`
- OpenAI Developers, **Package your plugin**: `https://developers.openai.com/plugins/build/plugins`
- OpenAI Developers, **Security & Privacy**: `https://developers.openai.com/plugins/guides/security-privacy`
- OpenAI Help, **Importing and syncing plugin marketplaces from GitHub**: `https://help.openai.com/en/articles/20001504`
- OpenAI Help, **Plugins in ChatGPT and Codex**: `https://help.openai.com/en/articles/20001256-plugins-in-codex`
- OpenAI Developers, **Secure MCP Tunnel**: `https://developers.openai.com/api/docs/guides/secure-mcp-tunnels`
- OpenAI, **Premium seats are coming to ChatGPT Business**, updated 2026-08-25: `https://openai.com/index/premium-seats-chatgpt-business/`
- OpenAI Help, **ChatGPT Workspace Agents for Enterprise and Business**: `https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business`

---

## 25. Stop condition for this carrier

This F0 carrier stops after:

- this single design file is committed;
- placeholder, contradiction, scope and ambiguity review passes;
- the Chairman reviews the written repository artifact;
- a top-level program DAG and first-wave BSC-P1 implementation plan are authored through the required planning procedure;
- current protected source and active carrier collisions are re-pinned before any implementation START.

F0 does not create the plugin or apps, mutate Agent OS/Linear/Slack, arm a tunnel, enroll OAuth, change CeoIngress, claim a Business session identity, commission a worker or merge itself.
