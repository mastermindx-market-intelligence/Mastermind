# Mastermind Context Fabric — End-to-End Master Plan

> Execute by capability slices. Checkpoints are saves, not completion. Do not create a second truth/control plane.

**Date:** 2026-10-03  
**Design:** `docs/superpowers/specs/2026-10-03-mastermind-context-fabric-design.md`  
**Project operation:** `context-fabric-20261003-sol-001`  
**Planning source:** protected Mastermind `c776f8dc8d3dabb0070b51ad7f04d71987ff6df1`, Skillpack v1.0.1. Re-pin at every modifying decision boundary required by current procedure.

## North Star

A fresh or rotated AI session should stop spending its frontier reasoning budget rebuilding a mental model of Mastermind.

For a known program/capability, the normal path should be:

```text
protected source pin
-> exact task identity seeds
-> one context resolve
-> at most a few exact expansions
-> first substantive action
```

For a continuing task:

```text
protected source pin
-> prior cumulative checkpoint/context identity
-> material-invalidators diff
-> changed exact expansions only
-> continuation
```

Mastermind may grow by orders of magnitude while per-session startup context remains bounded by the task's dependency surface.

## Done when

The parent project is done only when all of the following are production-proven:

1. one read-only Context Resolver composes existing canonical owners instead of requiring manual archaeology;
2. registered code repositories expose deterministic content-addressed structural indexes;
3. registered local workspaces expose exact Git/local overlays without filesystem crawling;
4. cumulative continuation can distinguish relevant from irrelevant source movement;
5. approved ChatGPT/Claude/Codex surfaces can access the resolver through a narrow tool/plugin surface;
6. cold-start procedure is separately accepted after real-path proof;
7. benchmark sessions preserve 100% safety-critical source/carrier/effect/collision recall while materially reducing tool calls and retrieved context;
8. deleting every derived Context Fabric cache does not delete company truth or prevent canonical recovery.

## Current state at initiation

### Existing capabilities to reuse

- `COLD_START.md`: checkpoint-first bounded recovery.
- `ACTIVE_EXECUTION.md`: material-invalidator reconciliation rule.
- Agent OS `compile-context`: exact workstream context.
- CEO boot packet: one-way organizational orientation.
- Session Truth: protected pin, exact-scope closure, cross-plane normalization, findings and admission.
- `OperatingContextProjection`: ContextBundle/SuppliedInputReceipt semantics.
- `mmx-workspace`: attended source-custody/workspace owner.
- Context-rotation law: chat succession and durable-continuation boundaries.

### Missing capabilities

- universal task-scoped resolver entrypoint;
- direct/current live acquisition composition for all required owner observations;
- structural Project Atlas;
- workspace dirty-overlay projection;
- persistent but disposable content-addressed cache;
- domain-typed material invalidators;
- private plugin actions;
- cold-start integration;
- controlled baseline evaluation and production acceptance.

### Initial implementation in this project branch

The first bounded vertical has been started in:

- `control_plane/context_resolver.py`
- `scripts/context_resolver.py`
- `tests/test_context_resolver.py`

It consumes one Session Truth receipt, applies the existing exact-scope selector, produces a `mastermind.context_pack.v1`, emits a `ContextBundleFact`-compatible bundle, and computes selected-scope invalidators. It intentionally performs no live acquisition or persistence.

## Global invariants

Every slice must preserve:

- GitHub = implementation/evidence owner.
- Agent OS = durable organizational context owner.
- Executive OS = execution lifecycle/admission owner.
- Linear = selective projection.
- Slack = transport/hot-state projection.
- existing RuntimeBinding/session-target owners retain runtime identity.
- Context Fabric = derived read-only retrieval/navigation only.

No project slice may create another lifecycle, queue, retry store, watcher owner, identity registry, workstream registry, runtime-binding store, source-writer store, priority queue, or authoritative memory system.

Every modifying source wave uses one source-custody workspace/carrier until reconciled.

## Release DAG

```text
CF-F0 design + resolver contract
      |
      +--> CF-R1 live owner acquisition
      |
      +--> CF-A1 deterministic Project Atlas
      |          |
      |          +--> CF-W1 workspace overlay
      |
      +----------+--> CF-D1 material invalidation / continuation
                         |
                         +--> CF-P1 private plugin
                                  |
                                  +--> CF-E1 evaluation
                                           |
                                           +--> CF-K1 cold-start enrollment
                                                    |
                                                    +--> CF-PROD1
```

R1 and A1 can advance in parallel after F0 because they touch different owners. W1 depends on atlas identity semantics. D1 depends on exact live/structural identities. Protected procedure enrollment waits for production evidence.

---

# CF-F0 — Freeze design and prove the bounded resolver nucleus

## Outcome

A deterministic read-only resolver can turn an existing Session Truth receipt into a bounded context bundle without broadening authority or treating unrelated source movement as material.

## Source scope

Create:

- `control_plane/context_resolver.py`
- `scripts/context_resolver.py`
- `tests/test_context_resolver.py`
- design and this plan.

Do not change protected Skillpack in F0.

## Contract

`mastermind.context_pack.v1`:

- `authoritative: false`
- `derived_read_only: true`
- task/task digest
- exact scope
- selected-source digests
- existing-projection-compatible context bundle
- selected item metadata
- continuation mode
- typed initial invalidators

## Required tests

- exact scoped rows selected;
- unrelated rows excluded;
- `ContextBundleFact` compatibility;
- explicit budget omissions;
- deterministic fixed-input output;
- scoped PR head change produces invalidator;
- unrelated PR head change produces no material invalidator and no bundle revision churn;
- task change forces full recovery;
- malformed receipt fails closed;
- prior pack cannot claim authority;
- library and CLI produce identical JSON;
- inputs are not mutated.

## Acceptance

F0 source may be called `BUILT_NOT_PROVEN` after local tests. It is not `PROVEN_LIVE` until merged and exercised through later real-path phases.

---

# CF-R1 — Live owner acquisition and single-call resolution

## Problem

The initial resolver still assumes a Session Truth receipt already exists. Today `scripts/session_truth_receipt.py` requires prepared GitHub/Linear/Slack/Executive/identity snapshot files. That is too much ceremony for a fresh session.

## Outcome

A supported read-only acquisition path can produce the exact owner observations needed by a resolver request without the model manually assembling snapshots.

## Architecture

Extend existing Session Truth acquisition/snapshot seams; do not put network clients inside pure reconciliation modules.

Preferred split:

```text
owner adapters / approved plugin reads
-> normalized Session Truth inputs
-> Session Truth receipt
-> Context Resolver
```

The pure resolver remains zero-network.

## Tasks

- [ ] census current approved GitHub/Linear/Slack/Executive read actions and exact schemas;
- [ ] define one bounded acquisition request carrying explicit scope seeds;
- [ ] acquire only sources required by that scope;
- [ ] preserve unavailable vs healthy-empty distinctions;
- [ ] preserve observed source revision/digest;
- [ ] reject secrets/credential-bearing keys using existing snapshot rules;
- [ ] avoid Slack body retrieval when operation/message identity metadata suffices;
- [ ] produce one Session Truth receipt and one Context Pack in a single top-level command/tool call;
- [ ] add source-specific negative tests;
- [ ] prove no canonical mutation.

## Acceptance

One supported call using real current owners can resolve a bounded known workstream without pre-created snapshot files, and a missing owner is explicit rather than silently empty.

---

# CF-A1 — Deterministic Project Atlas

## Outcome

Mastermind, Macro and Terminal structural knowledge is retrievable by immutable Git/blob identity without rescanning unchanged repositories.

## Phase A1.1 — Atlas contract

Define derived schemas:

```text
atlas.repo_manifest.v1
atlas.blob_record.v1
atlas.symbol_record.v1
atlas.edge_record.v1
atlas.query_result.v1
```

Each record carries repository, commit/blob identity, parser version and content digest.

No record carries authority.

## Phase A1.2 — Python exact index

Parse tracked Python blobs using stdlib AST:

- modules;
- classes/functions;
- imports;
- decorators;
- route declarations where deterministic;
- constants/config references where bounded;
- test-to-symbol/file references where explicit.

Tests must prove:

- unchanged blob is not reparsed;
- rename/changed blob invalidates exact edges;
- syntax error degrades one blob, not whole repo;
- generated/cache/secret paths are excluded;
- index output is deterministic for a fixed tree.

## Phase A1.3 — Markdown/document index

Index:

- path;
- heading hierarchy;
- bounded section ranges;
- explicit file/PR/issue/WS/MAS references;
- content digest.

Retrieved imperatives stay data.

## Phase A1.4 — JS/TS

Use an approved deterministic parser/Tree-sitter/LSP seam if already available. Do not add a heavyweight runtime merely for convenience without measuring it.

Index exports/imports/components/routes/tests.

## Phase A1.5 — Cross-repo edges

Only exact edges:

- explicit repository/path refs;
- pinned contracts;
- package/import references;
- generated contract IDs;
- documented canonical relationships.

No title similarity.

## Phase A1.6 — cache and incremental builder

Preferred host path:

`/Volumes/Mastermind/context-cache/`

The cache must be:

- ignored/untracked;
- content-addressed;
- versioned by schema/parser;
- rebuildable;
- garbage-collectable;
- never a prerequisite for canonical owner access.

A clean rebuild over a frozen source tree must reproduce the same manifest identities.

## Phase A1.7 — lexical + semantic retrieval

Exact graph and lexical search ship first.

Add embeddings only after exact retrieval works.

Model-produced summaries:

- optional;
- cheap/local model by default;
- source-digest bound;
- excluded when stale;
- labeled derived.

## Acceptance

A query for a known symbol/capability returns the correct defining paths/tests/docs from the frozen repo without directory archaeology and without model-generated authority.

---

# CF-W1 — Registered Workspace Overlay

## Outcome

Context resolution sees local in-progress changes through existing workspace custody rather than crawling the host filesystem.

## Tasks

- [ ] consume `mmx-workspace census/status` or the underlying existing owner through a read-only adapter;
- [ ] map workspace -> repository/base/HEAD/branch/operation;
- [ ] compute deterministic tracked-diff fingerprint;
- [ ] expose changed tracked paths;
- [ ] expose only bounded safe untracked paths when existing custody law permits;
- [ ] exclude secrets/caches/build output/generated data;
- [ ] bind overlay to base atlas manifest;
- [ ] generate overlay symbol/document deltas only for changed files;
- [ ] represent dirty/unavailable/unknown explicitly;
- [ ] never infer writer authority from an observed workspace.

## Acceptance

A session continuing a dirty attended worktree receives exact changed paths and overlay generation, while an unrelated workspace does not enter the pack.

---

# CF-D1 — Material Invalidation and Continuation

## Outcome

A continuing session can reuse accepted context and fetch only facts whose material identity changed.

## Inputs

- cumulative checkpoint/continuation reference from existing owner;
- prior Context Pack;
- current protected source;
- current owner observations;
- current atlas/workspace generations.

## Domain invalidators

Implement only with exact falsifiers:

- procedure pin change;
- workstream/checkpoint digest change;
- selected PR head change;
- relevant Git blob/symbol edge change;
- imported dependency-interface change;
- local overlay change;
- relevant Executive effect/status change;
- material worker return;
- relevant collision-set change;
- relevant research-source revision change.

## Negative invariant

Changes outside the exact selected dependency closure do not trigger a global recensus.

## Compatibility check

When protected master changes, compare affected governing paths and selected dependencies. Path-disjoint movement should preserve accepted structural context.

## Acceptance

Replay benchmark:

1. build prior pack;
2. change an unrelated source path/PR;
3. resolver returns no material invalidator;
4. change a relevant interface/PR/checkpoint;
5. resolver names the exact invalidator and changed refs;
6. session can continue from those refs without full recovery.

---

# CF-P1 — Private Mastermind Context Plugin

## Outcome

Approved AI sessions can use Context Fabric without shell knowledge or repository-path discovery.

## Tool surface

Read-only, narrow actions only:

- `resolve_context`
- `expand_context`
- `diff_context`
- `verify_context_ref`
- `atlas_search`

## Tool prohibitions

No:

- arbitrary shell;
- arbitrary filesystem paths;
- generic browser control;
- credential access;
- source writes;
- PR mutation;
- runtime dispatch;
- Linear mutation;
- Slack send;
- lifecycle/admission mutation.

## Deployment

Use the existing private plugin framework and approved host/service route. Do not create a separate authentication plane if an existing Mastermind plugin principal/resource binding can be reused.

## Acceptance

Fresh approved ChatGPT session can resolve and expand exact Mastermind context using only the plugin surface and the current protected procedure.

---

# CF-E1 — Evaluation and hardening

## Benchmark corpus

Create a fixed evaluation set containing real historical task shapes without secrets:

- known implementation task;
- cross-repo architecture task;
- existing workstream continuation;
- task with unrelated open PR noise;
- task with relevant source collision;
- local dirty-workspace continuation;
- research-heavy task;
- runtime incident;
- task after protected procedure movement;
- task after unrelated protected master movement.

For each benchmark record must-include refs and acceptable optional refs.

## Baselines

### Exhaustive baseline

Current safe full census procedure with exact canonical reads.

### Optimized candidate

Protected pin + Context Resolver + targeted expansion.

## Metrics

Record through existing evaluation/evidence owners:

- pre-work tool calls;
- pre-work retrieved bytes/tokens;
- time to first substantive action where observable;
- critical ref recall;
- total relevant ref recall;
- false material invalidators;
- missed material invalidators;
- stale-source mistakes;
- wrong-owner mistakes;
- source collision misses;
- accepted task outcome.

Do not create a second telemetry database.

## Release gates

Required before cold-start enrollment:

- 100% must-include protected law/carrier/effect/collision recall;
- zero authority boundary violations;
- >=60% median reduction in pre-work calls;
- >=60% median reduction in retrieved bytes/tokens;
- deterministic fixed-input output;
- cache deletion/rebuild proof;
- independent adversarial review of prompt-injection/cache-poisoning boundaries.

---

# CF-K1 — Cold-start integration

## Gate

Do not modify protected cold-start/bootstrap text merely because F0/A1/P1 exists.

Only after E1 passes and a real approved plugin path is available should a separate protected-procedure change say, conceptually:

```text
after mandatory protected source pin and exact identity seed,
prefer the production-proven Context Resolver for checkpoint/current-state recovery;
expand exact sources as needed;
fall back to the canonical bounded ladder on unavailable/degraded resolver evidence.
```

The Skillpack must retain canonical source ownership and must not embed live context.

## Acceptance

Fresh-session evaluation proves the changed procedure actually uses the resolver correctly. Source merge alone is not native adoption proof.

---

# CF-PROD1 — Production acceptance

Run at least these real-path journeys:

## Journey A — Fresh principal session

- fresh approved Sol/Astra conversation;
- real Mastermind task in a known program;
- protected source pin;
- one context resolution;
- <= few exact expansions;
- correct first substantive action;
- no broad repository census.

## Journey B — Continuing implementation session

- existing cumulative checkpoint/prior context;
- relevant source changed;
- unrelated source also changed;
- diff returns only relevant invalidators;
- session resumes correct workspace/carrier.

## Journey C — Worker/implementation consumer

- worker receives bounded mission;
- context plugin supplies exact source/test/architecture refs;
- worker does not need parent transcript or repository archaeology;
- return evidence remains compact.

## Journey D — Degraded context service

- cache unavailable/corrupt or one owner unavailable;
- resolver degrades/fails closed;
- canonical fallback recovery remains possible;
- no empty state is interpreted as healthy;
- no source modification occurs from degraded context.

Parent project reaches `PROVEN_LIVE` only after these journeys and required evaluation/review pass.

---

# Implementation sequence from current branch

## Immediate F0 tasks

- [x] inspect current protected source and owner law;
- [x] census Session Truth, CEO boot packet, Operating Context and workspace seams;
- [x] confirm no open Context Fabric/Context Resolver PR collision by direct search;
- [x] acquire one governed attended workspace;
- [x] implement pure Context Resolver;
- [x] implement CLI renderer;
- [x] implement exact-scope/delta/budget/authority tests;
- [x] run focused Session Truth + Operating Context compatibility suite;
- [ ] run formatting/static/full relevant tests;
- [ ] review diff for secret/runtime/generated-state contamination;
- [ ] commit via attended workspace owner;
- [ ] push exact branch;
- [ ] open Draft PR carrying design + master plan + F0 implementation;
- [ ] create one GitHub parent issue that points to the design/plan/PR without inventing Agent OS parent identity;
- [ ] consume required CI and independent review;
- [ ] merge only after current release authority/gates permit.

## Next action after F0 publication

Begin CF-R1 owner-adapter census and CF-A1 atlas contract in parallel only if source custody is disjoint. If not delegated, keep one writer and land them as sequential PRs.

## Do not redo

Unless source materially changes:

- do not re-argue whether Context Fabric should become a canonical memory plane: it must not;
- do not replace Agent OS/Session Truth/Operating Context with a new store;
- do not crawl the whole local filesystem to discover workspaces;
- do not use semantic similarity ahead of exact identity/graph edges;
- do not embed live state into protected Skillpack;
- do not equate F0 resolver tests with production cold-start proof.

## Project frontier

At initiation, the highest-value critical path is:

```text
publish CF-F0 candidate
-> exact-head CI/review
-> CF-R1 live acquisition + CF-A1 atlas
-> CF-W1 + CF-D1
-> plugin
-> evaluation
-> protected cold-start enrollment
-> production acceptance
```

Every phase must end in an observable user/machine capability, not merely another planning artifact.
