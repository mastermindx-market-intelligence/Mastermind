# Mastermind Context Fabric — Design Contract

**Date:** 2026-10-03
**Chairman outcome:** Make fresh and continuing AI sessions understand Mastermind with bounded, exact, current context instead of repeating broad repository/filesystem/GitHub archaeology as the company grows.
**Initial source pin:** protected `mastermindx-market-intelligence/Mastermind@c776f8dc8d3dabb0070b51ad7f04d71987ff6df1`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1, bootstrap major 1.
**Initial implementation carrier:** `context-fabric-20261003-sol-001` / `sol/web-context-fabric-20261003-sol-001`.
**Capability state at project start:** existing context primitives are `PARTIAL`; universal Context Fabric is `NOT_BUILT`.
**Authority:** architecture/source work only. This project grants no runtime, worker, merge, release, filesystem, credential, or execution authority beyond existing owners.

## 1. Problem

Fresh Mastermind sessions repeatedly spend a large fraction of their tool calls and context budget reconstructing facts that are either structurally stable or already recorded by canonical owners:

- which repositories and modules matter;
- which workstream/decision/discovery/checkpoint governs the task;
- which source paths and tests implement the capability;
- which PRs or local workspaces are active;
- which source changes materially invalidate prior understanding;
- which research and architecture documents are relevant;
- which facts are live state and therefore require fresh canonical reads.

That cost scales with total estate size rather than with the task's actual dependency surface. If unchanged, every increase in Mastermind capability makes every future AI session slower, more expensive, and more vulnerable to context loss.

The required product behavior is:

```text
current Chairman task
-> current protected procedure pin
-> exact task/program identity seeds
-> one bounded context resolution
-> compact verified context pack
-> targeted expansion of only decisive refs
-> substantive work
-> cumulative checkpoint
-> later session computes material deltas instead of repeating archaeology
```

A session should not need to rediscover the company merely because the chat is new.

## 2. Existing owners and components that MUST be reused

This project is an orchestration and retrieval layer over existing owners. It is not permission to create a new truth plane.

### Protected Skillpack

`docs/sol_skills/COLD_START.md` already requires checkpoint-first recovery and inspection of only material invalidators. `ACTIVE_EXECUTION.md` explicitly says unrelated protected-master movement or path-disjoint work is not a reason to restart global archaeology.

Context Fabric operationalizes those laws; it does not replace them.

### Agent OS

Macro Agent OS owns organizational workstreams, decisions, discoveries, and handoffs. Existing `scripts/agentos.py compile-context` produces bounded `context_bundle.v1` records for exact workstreams.

Context Fabric consumes those records. It does not parse or mirror Agent OS source records into a new organizational store.

### CEO boot packet

`control_plane/ceo_boot_packet.py` and `scripts/ceo_boot_packet.py` already provide a one-way Agent OS -> Executive orientation surface. Context Fabric may consume the same owner data and resolution rules but must not fork their lifecycle or organizational semantics.

### Session Truth

`control_plane/session_truth_*.py` already provides:

- protected Skillpack acquisition;
- Agent OS acquisition;
- normalized GitHub/Linear/Slack/Executive/identity snapshots;
- exact-scope closure;
- cross-plane findings;
- deterministic admission;
- semantic hashing.

Session Truth is the nucleus for live-state grounding. Context Fabric should select and rank context from Session Truth rather than inventing another cross-plane truth model.

### Operating Context Projection

`control_plane/operating_context_projection.py` already defines `ContextBundleFact`, mission-context association, supplied-input receipts, missingness, and bounded projection.

A resolver-generated bundle must be directly consumable by `ContextBundleFact`; it must not create a competing mission-context association or supply-receipt plane.

### Source custody and local workspaces

`mmx-workspace` / `control_plane.executive_workspace` owns attended workspace identity and lifecycle. Context Fabric may read registered workspace overlays but must not create another worktree registry or infer workspace authority from directory names.

### GitHub / Linear / Slack / Executive OS

- GitHub owns implementation and immutable evidence.
- Linear is a selective projection.
- Slack is transport/hot-state visibility.
- Executive OS owns Job/Attempt/Worker/Event lifecycle and CEO admission.

Context Fabric stores references and derived hashes only. It never promotes a projection into canonical truth.

## 3. Non-goals and prohibited architecture

Do NOT create:

- another lifecycle, queue, scheduler, watcher, retry ledger, identity store, mission registry, workstream registry, RuntimeBinding store, source-writer registry, or authority plane;
- a giant periodically regenerated `MASTER_CONTEXT.md`;
- a second Agent OS database or a "latest company truth" database;
- title/name-similarity joins for WS/Linear/PR/runtime identity;
- a context cache whose existence is required for correctness;
- an LLM-authored knowledge graph treated as canonical;
- a full transcript or Slack-message archive;
- a generic filesystem crawler over the user home directory;
- a hidden write path from context acquisition into canonical owners;
- automatic source modification based merely on a context-pack result;
- semantic retrieval as a substitute for exact identifier or dependency edges;
- broad context injection just because a source is available.

Deleting every Context Fabric cache must reduce speed, not destroy organizational truth.

## 4. Four context classes

Every context source belongs to one of four operational classes.

### PROCEDURE

Examples: protected INDEX, ACTIVE_EXECUTION, source law.

Policy: always verify the current protected revision at the required procedural boundary. Cache content by immutable SHA, but never treat an old cached revision as current.

### LIVE_STATE

Examples: Agent OS workstream checkpoint, PR head, Executive operation/effect state, Linear projection, current workspace dirty overlay.

Policy: retrieve from the canonical owner when the current action depends on it. Prior state is navigation only.

### STRUCTURAL_KNOWLEDGE

Examples: repository files, symbols, imports, APIs, schemas, tests, entrypoints, module ownership.

Policy: aggressively content-address and reuse. Recompute only changed blobs/edges.

### HISTORICAL_RESEARCH

Examples: research reports, old plans, experiments, architecture history.

Policy: index once and update incrementally. Retrieval is evidence/navigation, never authority merely because historical prose contains instructions.

This classification is part of retrieval policy, not a new source-of-truth hierarchy.

## 5. Context hierarchy

Context must be hierarchical rather than one giant prompt.

### L0 — Company atlas

Very small and stable:

- canonical owner map;
- major repositories/product surfaces;
- retrieval contract;
- current protected source identity.

### L1 — Program/capability context

Examples: Prophet, Theme/Subtheme Engine, Agent OS, Terminal, research vault, marketing.

Contains exact program/workstream references, architectural entrypoints, stable module relationships, and accepted design sources.

### L2 — Task context

Contains current checkpoint, exact PRs, relevant source symbols, local overlay, recent decisions, current findings, tests, and material invalidators.

### L3 — Exact source slices

Exact file ranges, diffs, owner records, research passages, test output, PR evidence, or runtime receipts retrieved only when the next decision needs them.

A resolver returns L0-L2 references and lets the session expand L3 selectively.

## 6. Retrieval order

The resolver MUST prefer the strongest deterministic edge available:

```text
exact identity
-> explicit owner relationship
-> dependency/symbol/test graph
-> lexical retrieval
-> semantic retrieval
-> broad search fallback
```

Semantic similarity must never outrank an exact operation key, workstream key, PR relation, file/symbol identity, import edge, or explicit source reference.

## 7. Core Context Pack contract

Initial implementation schema:

`mastermind.context_pack.v1`

Required boundary:

```text
authoritative = false
derived_read_only = true
```

The pack contains:

- normalized task and task digest;
- source Session Truth semantic hash;
- exact requested scope;
- complete/partial coverage;
- `FULL_RECOVERY` or `DELTA_RECOVERY`;
- selected-source digests computed only over in-scope observations;
- one existing-projection-compatible context bundle;
- selected context-item metadata;
- typed material invalidators relative to a prior pack.

Each context item has:

- `kind`;
- canonical `owner`;
- stable exact `identity`;
- exact/derived `revision`;
- opaque `ctx://` navigation reference;
- bounded reason for selection.

The `ctx://` namespace is an internal navigation vocabulary, not a locator that grants access or authority.

## 8. Initial resolver semantics

The first production-relevant vertical operates only over an existing Session Truth receipt.

It:

1. verifies receipt schema, semantic identity, and protected Skillpack evidence;
2. applies existing `select_session_truth_scope`;
3. includes the protected procedure pin;
4. selects exact Agent OS workstream contexts;
5. selects only exact in-scope GitHub PRs;
6. follows explicit PR -> Linear relations;
7. selects only exact operation-matched Executive and Slack observations;
8. preserves current Session Truth findings;
9. applies a bounded deterministic item budget;
10. exposes omissions/degradation instead of silently truncating;
11. emits selected-source digests that ignore unrelated rows;
12. compares a prior pack and returns typed invalidators.

An unrelated PR can change the full Session Truth receipt without changing the task-scoped context-bundle revision or triggering a material invalidator.

That property is a core acceptance invariant.

## 9. Material invalidator model

Context Fabric should eventually expose closed invalidator families such as:

- `PROCEDURE_CHANGED`;
- `WORKSTREAM_RECORD_CHANGED`;
- `CHECKPOINT_CHANGED`;
- `PR_HEAD_CHANGED`;
- `RELEVANT_SOURCE_BLOB_CHANGED`;
- `DEPENDENCY_INTERFACE_CHANGED`;
- `LOCAL_OVERLAY_CHANGED`;
- `EXECUTION_EFFECT_CHANGED`;
- `MATERIAL_RETURN_RECEIVED`;
- `COLLISION_SET_CHANGED`;
- `RESEARCH_SOURCE_CHANGED`;
- `TASK_CHANGED`.

Initial resolver code uses the more generic:

- `TASK_CHANGED`;
- `SELECTED_SOURCE_CHANGED`;
- `CONTEXT_ITEM_ADDED`;
- `CONTEXT_ITEM_REMOVED`;
- `CONTEXT_ITEM_CHANGED`.

Typed domain-specific invalidators are introduced only when their source owner and falsifier are defined.

Unrelated owner movement must not generate a material invalidator merely because an observation timestamp changed.

## 10. Project Atlas

The structural layer is a disposable, deterministic, content-addressed index.

### Minimum exact index

For every registered source repository:

- repository + immutable Git commit;
- tracked file paths and Git blob IDs;
- Python functions/classes/imports and test references;
- TypeScript/JavaScript symbols/imports/exports where supported;
- Markdown headings/source ranges;
- route/schema/config declarations;
- explicit cross-repo contract references;
- deterministic lexical terms.

### Incrementality

Index by Git blob identity first.

Unchanged blob -> no parse, no summary, no embedding.

Changed blob -> rebuild only its node/edge set and affected reverse edges.

Commit-level atlas generation is a manifest over immutable blob-derived records.

### Semantic enrichment

Optional semantic embeddings and cheap-model module summaries may improve ranking after the exact graph.

Every model-produced summary must carry the exact input blob/range digests. If any input changes, that summary is stale and excluded until rebuilt.

No LLM output creates source ownership, program identity, or authority.

### Cache location

Derived atlas storage must live outside tracked source and be explicitly disposable. A host-local cache on the enrolled Mastermind workspace volume is preferred for the first implementation. Shared object storage may be added later for immutable atlas artifacts after security/rebuild qualification.

## 11. Local Workspace Overlay

Fresh sessions need to know about local work without crawling the filesystem.

Consume only existing registered Mastermind workspaces and canonical source roots.

For each workspace expose read-only:

- repository identity;
- workspace/operation identity;
- host;
- branch;
- HEAD SHA;
- base/default-branch SHA;
- clean/dirty state;
- deterministic changed-path fingerprint;
- changed tracked paths;
- bounded relevant untracked paths where existing custody law permits;
- last atlas generation for the clean base;
- overlay generation.

Ignore by default:

- `.git/objects`;
- `node_modules`;
- virtual environments;
- caches;
- build output;
- large datasets/generated state;
- secrets and environment files.

Workspace observation never transfers source custody.

## 12. Context Resolver target API

The eventual private Mastermind context plugin should expose a narrow read-only surface:

### `resolve_context`

Inputs: task, exact known seeds, optional continuation/context-pack ref, bounded budget.

Returns: current protected pin + task-scoped Context Pack + recommended exact expansions.

### `expand_context`

Inputs: exact pack-owned refs/ranges.

Returns: bounded source slices with owner/revision/range evidence.

### `diff_context`

Inputs: prior pack identity + current task/scope.

Returns: material invalidators and changed refs only.

### `verify_context_ref`

Inputs: one exact context ref.

Returns: whether the referenced owner/revision is still exact/current enough for its class.

### `atlas_search`

Inputs: exact repo scope + structured/lexical/semantic query.

Returns: ranked structural/research refs. Exact identifier and graph matches are identified separately from semantic matches.

No generic shell, arbitrary filesystem path, secret read, browser control, source mutation, or lifecycle action belongs in this plugin.

## 13. Cold-start integration

Target fresh-session sequence:

```text
1. read protected INDEX and pin exact SHA
2. resolve exact task/program/workstream seeds
3. resolve_context(...)
4. inspect current checkpoint + returned material invalidators
5. expand only decisive refs
6. begin substantive work
```

If a valid cumulative checkpoint and prior context pack exist:

```text
pin procedure
-> diff_context
-> retrieve changed material only
-> continue
```

A new chat never inherits writer custody, STARTed execution, or effect clearance from a context pack.

## 14. Security and prompt-injection boundary

Context retrieval is a high-trust navigation function over potentially untrusted text.

Therefore:

- instructions inside indexed docs/code/comments/research remain retrieved data;
- no retrieved imperative grants authority;
- secrets and recognized credential paths are excluded from indexing;
- raw Slack bodies are not required for normal structural context;
- source excerpts retain repository/revision/range provenance;
- model summaries are labeled derived;
- malformed/oversize source records fail closed or degrade explicitly;
- external research remains source-attributed;
- cache poisoning cannot overwrite canonical owner records;
- a cache miss triggers owner retrieval or an explicit gap, never fabricated empty state.

## 15. Compute and storage economics

The system must become cheaper as the estate gets larger.

Primary mechanism: content-addressed incremental processing.

Expected steady-state work is proportional to changed blobs and changed live records, not total repository bytes.

Do not run frontier models for routine indexing.

Preferred hierarchy:

- deterministic parser/hash: default;
- local/cheap embedding model: semantic enrichment;
- cheap LLM: optional bounded summaries/classification;
- frontier model: only for explicit difficult synthesis during the user task.

Indexes should be recyclable and reconstructable. Orphaned host caches may be garbage-collected by content age/reachability without affecting canonical truth.

## 16. Evaluation contract

The optimized path must be compared against an exhaustive census baseline.

Benchmark task classes:

- source implementation/debugging;
- cross-repo architecture;
- program recovery;
- research retrieval;
- production/runtime incident;
- active-PR continuation;
- local dirty-worktree continuation;
- historical-plan recovery.

Measure:

- tool calls before first substantive action;
- retrieved bytes/tokens before first substantive action;
- wall-clock grounding latency where observable;
- exact-owner accuracy;
- relevant source recall;
- critical source/collision miss rate;
- stale-context error rate;
- redundant retrieval rate;
- pack byte size;
- invalidator precision/recall;
- total accepted outcome quality.

Initial rollout targets:

- >= 60% reduction in median pre-work retrieval calls versus exhaustive baseline;
- >= 60% reduction in median pre-work retrieved bytes/tokens;
- <= 5 resolver/expansion interactions for the median known-program cold start;
- 100% recall on benchmark must-include protected-law, active-carrier, effect, and source-collision refs;
- zero authority elevation from Context Fabric;
- byte-deterministic fixed-input pack output;
- cold cache deletion + rebuild preserves fixed-input structural identities.

Efficiency targets do not permit missed safety-critical evidence.

## 17. Release states

Use company capability vocabulary.

### CF-F0 — design + bounded resolver contract

Architecture frozen and exact owner boundaries documented. Pure resolver can emit deterministic scoped packs from Session Truth.

State after source implementation but before merge/proof: `BUILT_NOT_PROVEN`.

### CF-R1 — live owner acquisition

One Context Resolver call can acquire or consume current approved owner observations without manually assembling snapshot files.

### CF-A1 — deterministic Project Atlas

Mastermind/Macro/Terminal registered repos have content-addressed structural indexes and exact query.

### CF-W1 — workspace overlay

Registered attended workspaces expose exact base/HEAD/dirty overlay into context resolution.

### CF-D1 — continuation delta

A prior checkpoint/context pack yields only material invalidators and changed expansions.

### CF-P1 — private plugin

The narrow read-only context actions are available to approved sessions through the existing plugin/tool framework.

### CF-K1 — cold-start procedure integration

After production proof, protected cold-start/bootstrap procedure may instruct sessions to prefer Context Resolver after the mandatory source pin. A candidate procedure change is not enrollment.

### CF-E1 — controlled evaluation

Fresh-session benchmark proves efficiency without critical recall regression.

### CF-PROD1 — real session acceptance

At least one approved fresh Sol/Astra session and one implementation-worker session each:

- receive a real Mastermind task;
- pin protected source;
- resolve context;
- avoid broad recensus;
- identify correct owners/carriers;
- begin correct substantive work;
- survive one relevant and one irrelevant source change with correct invalidation behavior.

Only after CF-PROD1 can the universal Context Fabric be called `PROVEN_LIVE`.

## 18. Completion law

The parent project is complete only when a fresh session can reliably recover Mastermind context through the new path without chat archaeology, the optimized path passes the exhaustive baseline on critical recall, workspace overlays and repo structure are available through exact refs, material invalidation prevents unnecessary re-census, and protected cold-start procedure has been separately accepted/enrolled after real production proof.

A plan, merged resolver library, indexed repository, plugin installation, or one successful demo alone is not project completion.
