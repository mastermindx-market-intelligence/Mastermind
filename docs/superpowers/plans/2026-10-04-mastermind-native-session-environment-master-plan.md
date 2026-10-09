# Mastermind Native Session Environment — Hardened Master Plan

**Status:** integration program / source candidate / not production proof  
**Prepared:** 2026-10-04  
**Protected source pin used for this plan:** `1c435eb9b079ea36ac8cebceb6b0666946804030`  
**Mission:** make Dot, ChatGPT Web, Pro, and other attended sessions operate like Mastermind-native coding agents: immediately oriented, repository-aware, operation-bound, able to inspect/edit/test through governed workspaces, able to delegate through Executive Session Bridge, and resilient when one plugin or host service is unavailable.

## 1. North Star

A fresh session should not begin by rediscovering the filesystem, repository layout, worktree topology, active branches, current mission, source law, plugin health, or worker/delegation routes.

The desired journey is:

```text
session starts
  -> receives bounded current context
  -> knows exact mission/repositories/operation/source pin
  -> attaches or acquires the exact governed workspace
  -> receives semantic repository map and material delta
  -> reads/edits/tests in that workspace
  -> commits/publishes through the existing publication owner
  -> delegates separable work through Executive Session Bridge when useful
  -> receives/consumes returns
  -> persists a compact material delta
```

The experience should approach Codex/Claude/Work ergonomics without giving an attended web session unrestricted host-wide authority or forcing every task through Studio Direct.

## 2. Current truth and root causes

### 2.1 Context/orientation is still expensive

PR #1205, **Context Fabric F0**, is the correct direction and already has a bounded resolver and end-to-end design. It is still an open draft candidate. It is read-only and authority-neutral by design, which is correct. The missing work is live owner composition, Project Atlas, workspace overlay, typed material invalidation, plugin delivery, evaluation, cold-start enrollment, and production proof.

Until that program reaches production, sessions repeatedly spend tool calls reconstructing state that should have been supplied as a bounded Context Pack.

### 2.2 Native workspace support is substantially built but not live

PR #685, **managed multi-repository mmx-workspace**, has already implemented closed repository bindings for Mastermind, Macro, and Terminal, operation/lane-bound workspace reuse, source-custody preservation, and dirty/unpublished fail-closed behavior. Its focused campaign reports 153 passing tests.

The important gap is not the core workspace allocator. The gap is its attended-session consumer and installation/proof path. The multi-repository source is not installed and therefore cannot yet be treated as a live default environment.

### 2.3 Executive V3 is source-complete for Session Bridge exposure but installation is stale

PR #1197 is merged. Protected source now defines Web CEO V3 server version **1.4.0** and composes:

- existing V3 Executive readers;
- `session_targets`;
- `session_send`;
- `session_summon`;
- MDM telemetry;
- `submit_ceo_intent`.

However, the currently installed Executive MCP configuration is:

```text
profile: web_ceo_v3
release_sha: f3e683036307f7d5c2478dac08e71135b442a821
```

Direct inspection of that installed release shows:

```text
WEB_CEO_V3_SERVER_VERSION = "1.3.1"
Session Bridge tools absent
```

That explains the present discrepancy. “V3 is done” is true at merged-source level, but false at installed live-tool level.

This program must therefore treat these as separate gates:

```text
SOURCE
-> REVIEWED/ACCEPTED
-> RELEASED
-> INSTALLED
-> PROFILE_SELECTED
-> PLUGIN CONNECTED
-> TOOL ENUMERATION MATCHES EXPECTED CONTRACT
-> REAL-PATH CANARY
-> PRODUCTION-PROVEN
```

No future plan may collapse those gates into “done.”

### 2.4 Studio Direct is powerful but should not be a normal dependency

Studio Direct currently proves useful raw host filesystem and shell capability. That is valuable for administrator/recovery work, but it has three properties that make it a poor foundation for every attended session:

1. it exposes host-level power rather than an exact operation workspace;
2. it requires substantial model orientation to choose the right root/worktree/process;
3. it can be degraded or blocked independently by the platform.

A Studio Direct failure must not remove Context, GitHub, Executive, workspace, semantic, or delegation capability.

## 3. Architectural decision: federated capability mesh, not one giant plugin

The session environment should be presented as a coherent product but implemented as **independent failure domains**.

The user-facing mental model is “Mastermind Native Session.” The implementation must remain federated across existing canonical owners.

### 3.1 Recommended plugin/service boundaries

#### A. Context plugin — read-mostly, low-risk, always-on

Owns no truth. It composes current owners into a bounded Context Pack.

Primary functions:

- `context_bootstrap`
- `context_delta`
- `repo_map`
- `mission_context`
- `capability_summary`

Dependencies should be limited to approved read paths and caches. It must continue working when Studio Direct is down.

#### B. Workspace plugin — operation-bound source environment

Composes `mmx-workspace`, Workbench semantics/action surfaces, and exact repository bindings.

Primary functions:

- `workspace_repositories`
- `workspace_acquire`
- `workspace_status`
- `workspace_read`
- `workspace_search`
- `workspace_patch`
- `workspace_command`
- `workspace_diff`
- `workspace_release`

This plugin must not depend on Studio Direct for ordinary operation. Studio Direct may be used by administrators to repair the underlying host, not as the session’s routine execution API.

#### C. Executive plugin — runtime/delegation

Existing V3 should remain its own plugin/service boundary.

Primary functions include:

- Executive state/inbox/job/fabric readers;
- `session_targets`;
- `session_send`;
- `session_summon`;
- CEO intent submission where separately armed.

An Executive outage should not remove workspace or GitHub capability.

#### D. GitHub plugin — repository publication/evidence

Keep the GitHub connected app independent. It remains the authoritative remote implementation/PR/CI/evidence surface.

#### E. Code Intelligence plugin/service — semantic acceleration

CodeIntel is advisory infrastructure, not a source-of-truth or editor.

Primary functions should eventually include:

- symbol search;
- references/implementations;
- dependency neighborhood;
- changed-surface analysis;
- diagnostics;
- semantic repository discovery.

It must be keyed by repository + exact commit/workspace identity so that stale semantics can be detected rather than silently trusted.

#### F. Studio Direct — admin/recovery escape hatch

Keep Studio Direct independent and optional for ordinary sessions.

Use cases:

- host diagnostics;
- installation and service repair;
- bounded administrator ceremonies;
- emergency inspection where a canonical product surface is unavailable.

Its loss should degrade only the admin lane.

### 3.2 Why this is safer and more reliable than a unified plugin

A single plugin can create a catastrophic common failure domain: if one high-risk capability triggers a platform block, authentication issue, tunnel outage, or server crash, the model can lose every unrelated tool.

The federated design instead provides graceful degradation:

| Failure | Capabilities that should remain |
|---|---|
| Studio Direct blocked | Context, GitHub, Executive, Workspace, CodeIntel |
| Workspace service down | Context, GitHub, Executive, CodeIntel |
| Executive down | Context, GitHub, Workspace, CodeIntel |
| CodeIntel stale/down | Context, GitHub, Workspace, Executive |
| Context service down | direct GitHub/Workspace/Executive still usable |
| GitHub transient outage | existing bound workspace, Context cache, Executive |

The session bootstrap should report degradation; it must not centrally gate all other plugins.

## 4. One shared contract without one shared runtime

Independent plugins still need enough interoperability to feel native.

The common contract should be a small immutable **Session Environment Descriptor**, assembled from canonical owner data but not stored as a new authority.

Example conceptual fields:

```text
session_environment:
  context_pack_ref
  operation_ref
  repository_set
  workspace_ref
  protected_skillpack_sha
  source_base_sha
  branch/head
  dirty_unpublished_summary
  current_prs
  material_delta
  semantic_index_revision
  executive_runtime_ref
  available_capabilities
  degraded_capabilities
  do_not_redo
```

Rules:

- it is a projection/reference bundle, not a lifecycle store;
- each field identifies its canonical owner;
- a plugin can operate when unrelated descriptor fields are unavailable;
- absence of one plugin cannot invalidate other independently proven bindings;
- capability health is observed, not inferred from installation docs.

## 5. Native workspace execution model

### 5.1 Host access is not workspace access

The default attended interface should never be “here is the Mac filesystem; find your project.”

Instead:

```text
operation identity
  -> repository alias
  -> exact base SHA
  -> governed workspace path
  -> allowed source roots
  -> process sandbox
  -> bounded publication path
```

### 5.2 Shell-like freedom belongs inside the workspace sandbox

The experience should be much less restrictive than a handful of predeclared recipes. Native coding agents need to run test commands, package managers, linters, code generators, grep/ripgrep, build tools, and repository scripts.

But “general shell” must mean:

> general command execution inside an exact operation-bound sandbox

not:

> arbitrary host-wide shell inherited from Studio Direct.

Required controls:

- CWD fixed under the operation workspace;
- no arbitrary source-root selection;
- no ambient access to user secrets/keychains/browser stores;
- controlled credential injection;
- separate publication credentials from build/test identity where practical;
- CPU/memory/time/output bounds;
- network policy/allowlist where the operation requires it;
- effect-unknown reconciliation for modifying external commands;
- process ownership tied to the existing operation/Attempt identity.

Linux workers can use containers/microVMs. Attended Mac sessions may use the existing managed worktree model plus a dedicated restricted process wrapper. Containerization is an implementation choice, not the North Star.

## 6. Context Fabric completion requirements

Context Fabric should become the session’s startup brain.

The Context Pack should be deliberately bounded and include references rather than copying entire documents.

Minimum content:

1. exact repository aliases and roots;
2. exact protected Skillpack pin;
3. mission/workstream/operation identity;
4. current repositories, base/head, branch, PRs and active source custody;
5. workspace identity and dirty/unpublished summary;
6. relevant architecture/owner map;
7. current dependencies and active child/return obligations;
8. material changes since prior accepted Context Pack;
9. plugin/service capability health;
10. expected build/test/publication commands or references;
11. DO_NOT_REDO;
12. exact evidence references.

### Material invalidation

Recompute context on changes that can affect the current decision or code path, such as:

- governing source/procedure changes;
- current repository/base/branch changes;
- material dependency changes;
- operation or workspace identity changes;
- runtime/effect-state changes;
- capability/service changes relevant to the next action.

Do not invalidate on unrelated repository movement.

## 7. Executive V3 repair and integration

### E0 — prove current installed state

Record:

- installed release SHA;
- selected MCP profile;
- live server version;
- live tool enumeration;
- CeoIngress/service state;
- Session Bridge provider composition;
- current target projection readiness.

Current evidence already establishes:

```text
installed profile = web_ceo_v3
installed release = f3e683...
installed V3 version = 1.3.1
session_* tools = absent
protected source after #1197 = V3 1.4.0
```

### E1 — release current accepted source through existing Executive owner

Do not manually copy files into the installed release.

Use the existing reviewed Executive release/install path, preserving installed host-specific configuration and current authority gates.

Acceptance:

- installed release contains V3 1.4.0 or later accepted compatible version;
- selected profile remains `web_ceo_v3`;
- no unrelated optional mount is accidentally armed.

### E2 — plugin tool enumeration proof

From a fresh connected ChatGPT session, enumerate Executive tools.

Required minimum:

```text
executive_state
executive_inbox
executive_job
executive_fabric
ceo_intent_status
session_targets
session_send
session_summon
executive_mdm
submit_ceo_intent
```

### E3 — live Session Bridge canary

Prove:

```text
authenticated web session
  -> session_targets
  -> one exact eligible target
  -> session_send or session_summon under existing law
  -> native receiver evidence
  -> useful return
  -> same parent consumes return
```

Do not claim completion from tool enumeration alone.

### E4 — separate Session Bridge from automatic worker execution

PR #1197 correctly notes that Session Bridge exposure does not prove queue-to-worker automatic dispatch.

Treat these as separate capabilities:

- direct exact-session delegation;
- Executive Job admission;
- Capacity/COO/worker automatic execution;
- return consumption.

This Native Session project needs direct Session Bridge working. It may consume automatic worker execution when that existing program becomes proven, but it must not invent a second scheduler to obtain it.

## 8. Delivery program

### Phase P0 — architectural freeze and truth ledger

Deliverables:

- this integration plan accepted;
- current owner/capability matrix;
- failure-domain contract;
- exact acceptance matrix.

Exit condition: no team can “solve” this by building a giant replacement MCP/plugin.

### Phase P1 — finish and accept Context Fabric F0/R1

Continue #1205 under its existing source custody.

Work:

- review/merge F0;
- live owner read composition;
- exact Context Pack generation;
- prior-pack delta;
- capability/degradation reporting.

Proof:

- fresh session can recover exact relevant state with bounded calls;
- unrelated estate movement does not trigger broad recensus.

### Phase P2 — finish, review, install, and prove multi-repo mmx-workspace

Continue #685 under its existing source custody.

Work:

- complete Studio/attended consumer without making Studio Direct a runtime dependency;
- independent review/current-base proof;
- install accepted source;
- prove Mastermind/Macro/Terminal workspace acquisition and reuse;
- prove dirty/unpublished preservation;
- add operation-bound command wrapper.

Proof:

- fresh session acquires the correct workspace from repository alias + operation + exact base;
- it never chooses an arbitrary host path;
- edit/test/commit/push/readback works on at least one accepted real path per repository class.

### Phase P3 — Executive V3 release/install correction

Use §7.

Proof:

- live plugin exposes V3 1.4.0-compatible Session Bridge surface;
- direct session canary succeeds.

### Phase P4 — CodeIntel workspace awareness

Continue existing Code Intelligence program rather than creating a new semantic backend.

Work:

- index protected repositories;
- exact SHA/workspace overlay;
- repository map;
- symbol/reference/implementation queries;
- dependency neighborhood;
- changed-surface/diagnostic endpoints.

Proof:

- session can answer “where does this behavior live?” without filesystem census;
- exact workspace edits are reflected or explicitly reported stale.

### Phase P5 — private Context and Workspace plugins

Expose the narrow product surfaces independently.

Design rule:

- Context plugin is read-oriented and highly available;
- Workspace plugin is operation-bound and higher risk;
- Executive stays separate;
- Studio Direct stays separate;
- GitHub stays separate.

Proof:

- disconnect/disable one plugin at a time and verify unrelated plugins remain available in a fresh session.

### Phase P6 — automatic startup/bootstrap

Once Context/Workspace production proof exists, enroll the startup path so fresh sessions receive the bounded bootstrap automatically or with one deterministic first call.

Avoid copying live state into the protected Skillpack.

Proof:

- fresh-session evaluation requires materially fewer discovery calls and materially less context before first useful action.

### Phase P7 — reliability, lifecycle, and cleanup

Bind environment continuity to the existing operation/Attempt rather than the chat turn.

Rules:

- turn/session end does not destroy dirty/unpublished work;
- same operation can reattach to the same workspace after reconciliation;
- terminal clean/released environments can be recycled;
- orphan detection derives from existing operation/runtime/process owners;
- no new orphan registry/lifecycle database.

## 9. Acceptance matrix

The overall mission is not complete until all of these are demonstrated.

### Orientation

- fresh session receives correct repo/mission/source-law/workspace context;
- bounded startup cost;
- material delta avoids full recensus.

### Filesystem/repository

- exact workspace attachment;
- multi-repo support;
- read/search/edit/test;
- no arbitrary root selection.

### Execution

- shell-like commands inside the governed sandbox;
- process/output bounds;
- secrets and host paths excluded by default.

### Publication

- diff/status;
- commit;
- push;
- GitHub readback;
- PR/CI evidence through canonical owner.

### Semantics

- symbol/dependency navigation;
- exact SHA/workspace freshness.

### Delegation

- Executive V3 live Session Bridge tools;
- exact-session direct send/summon;
- useful return consumed by originating session.

### Failure isolation

The following chaos tests are mandatory:

1. block Studio Direct -> normal source work still possible;
2. stop Executive plugin -> workspace and GitHub still work;
3. stop CodeIntel -> exact workspace work still works;
4. stop Context plugin -> direct exact-owner paths remain available;
5. stop Workspace plugin -> GitHub/Executive/Context remain available.

### Continuity

- same operation survives chat/turn boundary;
- dirty/unpublished work is preserved;
- no blind reuse after effect uncertainty;
- clean terminal environment can be released/recycled.

## 10. Metrics

Track before/after fresh-session cohorts:

- calls until first correct repository identification;
- calls until first useful source action;
- tokens consumed before first useful source action;
- wrong-root/worktree incidents;
- duplicate census calls;
- stale-context incidents;
- tool-unavailability blast radius;
- percentage of sessions with direct workspace capability;
- percentage with successful Context bootstrap;
- Executive delegation success rate;
- reconnect/continuation success rate;
- dirty-work loss incidents: target zero.

The primary optimization target is **verified useful work per session context/tool budget**, not merely fewer calls.

## 11. Explicit anti-goals

Do not:

- create a second lifecycle, queue, retry, workspace registry, or memory store;
- replace GitHub, Executive OS, Agent OS, Linear, or Slack ownership;
- make Studio Direct a mandatory dependency of routine coding work;
- expose unrestricted host-wide shell as the normal Workspace API;
- make Context Fabric an authority plane;
- treat merged source as installed capability;
- treat installed capability as selected/connected plugin capability;
- treat tool enumeration as production acceptance;
- automatically retry effect-unknown writes through a different plugin;
- destroy dirty work when a chat ends.

## 12. Priority order

### P0 — do now

1. finish Context Fabric F0/R1 path;
2. finish/install/prove mmx-workspace multi-repo attended path;
3. correct Executive V3 installed release and prove Session Bridge;
4. define independent plugin failure-domain contract and chaos tests.

### P1 — immediately after P0

5. Workspace command sandbox with native-agent ergonomics;
6. CodeIntel exact-workspace semantic surface;
7. Context + Workspace private plugin productization;
8. automatic startup/bootstrap enrollment.

### P2 — hardening

9. operation-bound reconnect/reuse;
10. environment cleanup/recycling;
11. fresh-session benchmark/evaluation and regression gates;
12. admin/recovery runbooks for Studio Direct without making it a runtime dependency.

## 13. DONE_WHEN

This program is complete only when a fresh attended session, without manual filesystem archaeology, can:

1. obtain exact bounded Mastermind context;
2. attach the correct operation workspace for the relevant repository;
3. inspect and understand source semantically;
4. edit and run meaningful repository commands inside a governed sandbox;
5. publish through existing canonical Git/GitHub paths;
6. delegate to an exact native session through live Executive V3 when useful;
7. survive the loss of any one nonessential plugin without losing unrelated capabilities;
8. reconnect to the same operation without losing dirty/unpublished work;
9. demonstrate materially lower startup/census overhead in fresh-session evaluation.

Until all nine are proven on real paths, report the program as incomplete.
