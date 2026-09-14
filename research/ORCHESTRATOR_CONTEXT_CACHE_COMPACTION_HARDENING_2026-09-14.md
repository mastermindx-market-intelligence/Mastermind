# Orchestrator context caching and compaction hardening

**2026-09-14 | RECORDS_ONLY / RESEARCH_INTAKE / PRODUCTION_INERT**

Research operation: `orchestrator-native-harness-parity-20260914-sol-001`.
Existing organizational home: `WS:EXECUTIVE-CAPACITY-FABRIC`.
Existing integration operation: `agent-fabric-end-to-end-fable-integration-20260913-sol-001`.
Protected source/procedure pin: `bffe2ca8506346ea278c8ee469bf1ac30a4de008` (Skillpack 1.0.1 / bootstrap 1).

This amendment reconciles context caching, compaction and subagent context economics with current protected Mastermind source. It changes no runtime, provider profile, credential, lifecycle, Agent OS state, routing, queue, transcript store or production registration. Existing source writers remain authoritative.

## Ruling

Do **not** create a `ContextService`, cache daemon, conversation database, prompt-memory store, provider-local lifecycle or second checkpoint ledger.

Context handling is one composed capability across existing owners:

- canonical organizational truth: Agent OS and declared repository authorities;
- Job/Attempt/effect/checkpoint truth: Executive Runtime;
- exact current session/process identity: RuntimeBinding / Operator Continuity;
- model/provider/account suitability and capacity: existing Router/Capacity owners;
- capability/tool/skill material: existing capability package and resource owners;
- rich provider session operations: `OperatorHarnessAdapter` and its provider implementation;
- bounded worker/result evidence: existing orchestration result and dialogue owners;
- cost/cache usage accounting: existing cost/usage telemetry owners.

Provider caches and compacted conversation summaries are accelerators/working state. They never become current authority merely because they are cheap to reuse or survive a provider session.

## Reconciled protected-source seams

| Seam | Current protected behavior | Consequence |
| --- | --- | --- |
| Attempt boundary | `operator_harness_contract.ATTEMPT_BOUNDARY_MATRIX` classifies `context_compaction` and `context_rotation` as `SAME_ATTEMPT` | Compaction/rotation must not manufacture a new Job or increment Attempt merely to manage context. |
| Optional checkpoint operation | `SupportsCheckpoint` already exists | Do not add a second `SupportsContextCompaction` protocol merely to name the same provider effect. |
| Checkpoint method law | Existing `checkpoint` contract permits `emit checkpoint candidate for Executive to persist` and `provider compaction`; it is `NON_REPLAYABLE_ON_UNKNOWN_EFFECT` | Native compaction belongs behind the existing checkpoint operation when a provider implementation actually qualifies it. |
| Executive persistence | Jobs/Attempts already carry `checkpoint_json`; Attempts carry monotonic `checkpoint_sequence`; `checkpoint_attempt()` persists and emits `JOB_CHECKPOINTED` | Reuse this authority rather than creating a context/checkpoint database. |
| Rich-OHF gap | Legacy `checkpoint_attempt()` refuses orchestration OHF checkpoints and explicitly requires a generation-bound API; current `RuntimePort`/`OperatorHarnessOrchestrator` has no checkpoint method | **Primary implementation gap:** add the missing generation-bound Executive checkpoint transaction and RuntimePort/orchestrator plumbing under the incumbent owner. |
| Codex rich adapter | `CodexOperatorAdapter.describe_capabilities()` currently advertises `supports_checkpoint=False` | No Codex native-compaction claim is allowed until the actual App Server path is qualified and implemented. |
| Turn input | Codex already accepts `str | CodexTurnInputEnvelope` through `TurnInputLoader` | Context packaging can evolve through an existing closed turn-input seam; do not widen the provider-neutral harness method contract just to pass context. |
| Result return | Existing orchestration result contracts bind canonical result/evidence digests and size bounds | Parent agents should consume bounded canonical results and selectively expand evidence, not replay worker transcripts. |
| Cost accounting | Existing cost telemetry records input/output plus cache-read/cache-creation tokens | Extend normalization into this owner; do not create a context-cost database. |
| Live turn observation | Active PR #623 owns bounded visible-turn projection/cursors on Codex | Context-pressure observation must consume/extend that owner later; it must not create a second provider event reader. |

## Context lifecycle

The provider-neutral policy should be deterministic wherever possible:

```text
recover current canonical facts
  -> construct smallest sufficient context projection
  -> order stable reusable prefix before volatile state
  -> execute one governed turn
  -> observe usage/context pressure from qualified provider evidence
  -> drop or replace deterministic bulk with exact evidence references
  -> if needed, checkpoint/compact through the existing OHF checkpoint operation
  -> persist accepted checkpoint through Executive Runtime
  -> continue in SAME_ATTEMPT / current epoch when valid
  -> rotate/resume under existing RuntimeBinding and writer-transfer law when necessary
```

This policy is **not** a model-driven loop. A model may decide what evidence is semantically material within its mission; lifecycle identity, checkpoint sequencing, effect handling, freshness and provider-writer ownership remain deterministic owner responsibilities.

## Context projection rules

A worker or operator should not receive an inherited parent transcript by default. Construct a bounded projection in this order where supported by the target runtime:

1. constitutional/authority envelope and exact current procedure identity;
2. stable capability, tool, MCP and skill/package material required for this mission;
3. exact mission, acceptance ruler, scope, non-goals and source/workspace identities;
4. accepted decisions and rejected alternatives that materially constrain the task;
5. immutable evidence references and only the raw evidence required for this decision;
6. current owner-derived hot state, with freshness and unknowns preserved;
7. recent working context that has not yet been durably represented;
8. current instruction/turn input.

Stable material should remain byte-stable where practical so provider-native prefix caching can work. Volatile runtime facts belong late and must be re-read from their owner; copying them into a cached prefix does not refresh them.

Child context is a projection of the admitted mission and capability ceiling, not a clone of the parent context. Independently effectful child work still uses existing Executive child admission. Native helper cognition remains parent-bounded and inherits only its approved capability/budget ceiling.

## Cache law

Mastermind should **plan for provider-native caching without owning provider cache state**.

- No canonical `cache_entries` table or cache registry.
- A cache hit is performance/cost evidence, never freshness or authority evidence.
- Provider cache identity, TTL and eviction remain provider behavior unless a reviewed harness exposes stronger guarantees.
- Context ordering should maximize stable-prefix reuse without weakening invocation-time permission checks.
- Changed capability package/tool schema/skill generation/model/harness profile must naturally invalidate reuse through changed content or provider configuration; do not preserve a revoked capability because a prior prompt was cached.
- Provider/account/session changes must not be performed merely to chase a warmer cache.
- Existing cache-read/cache-creation token fields should receive normalized observed values when the provider exposes them; absent values remain unknown/not-observed rather than invented zero when that distinction is material.

A useful diagnostic digest may be derived from already-authoritative identities (for example exact model/harness/profile/package/tool/context bytes), but the digest is evidence about one prepared context, not another identity or authority plane.

## Checkpoint and compaction law

Compaction is potentially provider-state-changing and therefore keeps the existing checkpoint operation semantics:

- one stable `OperationId`;
- intent/dispatch before provider mutation through the existing Executive operation path;
- lost/ambiguous response after possible provider submission => `EFFECT_UNKNOWN` on the same operation/carrier;
- no blind second compaction, new provider session, account switch or host failover while effect is unknown;
- adapter returns a checkpoint **candidate**; only Executive Runtime persists canonical checkpoint state;
- a provider-generated summary may be stored inside the accepted checkpoint payload only as working continuity material, never as a replacement for owner facts or evidence identities;
- checkpoint content must not contain hidden chain-of-thought.

At minimum, recoverable checkpoint content must preserve the information already required by the long-run-leader architecture: original outcome/success ruler, accepted decisions and relevant rejected alternatives, exact evidence/source/operation identities, open or ambiguous effects, current worker/dialogue obligations, unresolved risks/falsifiers and one exact next action. The wire shape should be fitted to the existing checkpoint/JobPayload owner rather than introducing a new durable schema casually.

## Deterministic pruning before model summarization

Do not spend a frontier turn compacting content that can be losslessly referenced.

Preferred ladder:

1. avoid loading irrelevant Tier-3/Tier-4 evidence;
2. replace large immutable source/log/test/tool payloads with exact digest/ref + bounded discriminating facts;
3. discard superseded duplicate tool projections while retaining the canonical source reference;
4. retain recent unresolved working state;
5. only then request provider-native/model compaction when actual context pressure warrants it;
6. if continuation still cannot be made safe, use existing rotation/resume rather than silently truncating critical state.

A compact summary must never erase an `EFFECT_UNKNOWN`, source-custody conflict, pending child result, open review/repair obligation or material disagreement simply because it is old.

## Context-pressure and telemetry projection

Do not invent a context-pressure authority before the provider exposes enough evidence. Normalize only observations we can actually bind to the exact turn/generation.

Useful metrics, where observed, include:

- input/output tokens;
- cache-read and cache-creation tokens;
- effective cache hit ratio;
- provider-reported context/window usage or an explicitly labelled local estimate;
- bytes/tokens omitted by deterministic reference pruning;
- pre/post-compaction input size where observable;
- compaction invocation count and provider/model cost where exposed;
- checkpoint/compaction latency;
- continuation/recovery correctness against the frozen mission and evidence set.

Existing cost telemetry remains the accounting owner. New observability should be an additive projection keyed to existing Job/Attempt/turn/generation identities, not a new lifecycle table.

## Implementation sequence inside existing ownership

### CCTX-0 — generation-bound OHF checkpoint plumbing

**Highest-leverage missing dependency.** Under the incumbent Executive/OHF source owner, add the missing generation-bound checkpoint path that the current Runtime already demands. It should:

- verify exact Attempt/current epoch/process generation/current writer;
- allocate/commit the existing checkpoint operation identity before adapter mutation;
- call optional `SupportsCheckpoint` only when the exact adapter advertises/supports it;
- persist the accepted checkpoint candidate through Executive Runtime with monotonic sequencing;
- preserve `EFFECT_UNKNOWN` and same-operation reconciliation;
- prove crash/restart and duplicate-operation behavior;
- add no table, queue, provider broker or transcript store.

Prefer a source slice centered on existing RuntimePort/orchestrator/runtime tests. Do not touch active #623 Codex live-turn paths in this slice.

### CCTX-1 — deterministic context projection / narrow child packet

Integrate a pure context-construction step at the existing worker/turn-input or capability-package owner. Inputs are canonical refs/facts already supplied by existing owners; output is one bounded prepared projection plus evidence/digests. No I/O-owning daemon and no persistence.

Required behavior:

- stable prefix separated from volatile owner-derived state;
- exact source/workspace/profile/package/tool identities;
- progressive disclosure rather than repository/transcript replay;
- child packet is independently sufficient for its bounded mission;
- deterministic refusal when required current facts or capability material are unavailable.

### CCTX-2 — Codex checkpoint/compaction qualification

Only after CCTX-0 and current #623/result-consumption ownership are reconciled, probe the exact installed App Server generation for an actual supported compaction/checkpoint path. If supported, implement it behind existing `SupportsCheckpoint`; if not, keep `supports_checkpoint=False` and rely on bounded context + existing safe rotation/resume. Do not emulate native compaction with a hidden local conversation store.

### CCTX-3 — usage/cache normalization

Map provider-observed cache usage into existing usage/result/cost telemetry. Preserve provider-specific evidence and unknowns. Include compaction sampling/iteration cost when the provider reports it separately so a cheap-looking compacted turn does not hide an extra billed model call.

### CCTX-4 — rich Claude/GLM and ACP qualification

After their rich OHF ports exist, qualify context behavior per **model + provider + harness + version + profile + realm**, not by provider marketing name. Claude/GLM and Grok/Cursor may use different native cache/compaction/session primitives while obeying the same Mastermind policy and checkpoint authority.

## Collision / owner boundary on 2026-09-14

- `agent-fabric-end-to-end-fable-integration-20260913-sol-001` remains the incumbent integration owner.
- PR #630 owns heterogeneous per-WORK placement / parent-consumption adjacent work; do not fold context lifecycle into its placement schema.
- PR #623 actively owns Codex live-turn projection and touches the Codex adapter/broker; do not create a parallel event reader or competing edits there.
- PR #632 is an unenrolled records-only Web delegation candidate and grants no runtime context capability.
- This research carrier #637 remains DRAFT/HOLD and records-only.
- The Studio primary checkout observed during this research is stale/dirty and must not be used as an implementation writer; an admitted implementation must acquire an owner-issued clean workspace/current source rather than cleaning or resetting that checkout.

## Acceptance journey

The first useful proof is not “a cache field exists.” Use one admitted managed rich-operator canary and show:

```text
current bounded mission/context projection
 -> governed turn(s) with observed usage
 -> context pressure reached under a controlled long-running workload
 -> deterministic bulk removed by refs first
 -> one governed checkpoint/compaction operation
 -> accepted Executive checkpoint sequence
 -> same Attempt continues or validly resumes
 -> exact open obligations/effects/source identities survive
 -> child result arrives as bounded canonical evidence
 -> parent consumes and makes the next decision
```

For a cache proof, repeat an otherwise equivalent stable-prefix workload and report **observed** provider cache usage/latency/cost delta without treating the cache hit as semantic correctness.

## Required falsifiers

1. cache hit with stale Executive/Agent OS fact must not make the stale fact current;
2. revoked/changed capability package must not remain usable because an earlier prompt was cached;
3. compaction response lost after submission must become effect-unknown, not trigger a second compact;
4. restart after accepted checkpoint must recover exact Attempt/generation/session/effect obligations or refuse typed recovery;
5. compacted state must retain an open `EFFECT_UNKNOWN`, pending child/review obligation and exact source identity;
6. adapter without checkpoint support must refuse/choose safe non-native rotation, never fake support;
7. a huge immutable tool/log result must be reference-pruned without losing evidence identity;
8. child context must omit irrelevant parent transcript while still being sufficient to complete acceptance;
9. provider usage with separate compaction/model iterations must account total cost, not only the outer turn;
10. observer/context instrumentation must not become a second reader that steals provider completion/approval events;
11. cached content must not bypass invocation-time permission/profile checks;
12. summary/compaction bytes must never be promoted to Agent OS decision or source truth without the normal owner path.

## Capability state and exact next dependency

At this research pin:

- provider-neutral context ownership/no-rebuild law: **BUILT as architecture/source law, not a runtime feature**;
- Same-Attempt compaction/rotation semantics and optional checkpoint contract: **BUILT_NOT_PROVEN** as source;
- legacy Executive checkpoint persistence: **BUILT** for its existing paths;
- generation-bound OHF checkpoint/compaction path: **NOT_BUILT**;
- Codex governed checkpoint/compaction: **NOT_BUILT** (`supports_checkpoint=False`);
- normalized cache economics in general model workloads: **PARTIAL** (existing cost fields, not rich-OHF fleet proof);
- provider-wide context lifecycle parity: **NOT_BUILT**.

**Exact next action:** the incumbent fabric/OHF integration owner should absorb **CCTX-0** as the first implementation slice after reconciling its source paths against current active writers. Completion is a generation-bound rich-OHF checkpoint operation through the existing Executive Runtime, with provider-free tests proving identity/effect/sequence/restart behavior. Do not wait for Claude/Grok/GLM ports and do not modify Codex #623 paths to complete CCTX-0.