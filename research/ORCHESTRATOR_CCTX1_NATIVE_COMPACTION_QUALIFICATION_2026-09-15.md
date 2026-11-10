# CCTX-1 — native compaction qualification over the protected OHF checkpoint seam

**2026-09-15 | RECORDS_ONLY / INTEGRATION_INTAKE / PRODUCTION_INERT**

Parent research operation: `orchestrator-native-harness-parity-20260914-sol-001`.
Existing organizational home: `WS:EXECUTIVE-CAPACITY-FABRIC`.
Existing integration principal: `agent-fabric-end-to-end-fable-integration-20260913-sol-001`.
Current protected Mastermind source/procedure: `19b6111891ffd742ceec7c96f437a2a890847c92` (`mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1).
Upstream Codex release qualified here: `rust-v0.154.0`, annotated tag object `36eab01061df3cde5f95ec20a526777b430091ba`, commit `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`.

This record updates the earlier context/cache/compaction research after CCTX-0 and heterogeneous placement moved into protected source. It creates no provider call, native thread, checkpoint, Job, credential effect, route, Worker, runtime activation, cache store, transcript store, new event reader, or source implementation commission by itself.

## Current truth — retire the stale CCTX-0 gap

CCTX-0 is no longer `NOT_BUILT`.

Mastermind PR #643 `[CCTX-0] Generation-bound OHF checkpoint path` merged as protected commit `bb96e8381870c864720318293462c4332ab7d453`. Protected source now contains:

- generation-bound `begin_operator_checkpoint(...)` / `apply_operator_checkpoint(...)` RuntimePort methods;
- an `OperatorHarnessOrchestrator.checkpoint(...)` path that reserves Executive intent before calling the provider adapter;
- current Attempt / current epoch / process generation / writer / fence / lease / operation matching;
- existing monotonic `checkpoint_sequence`, `checkpoint_json`, `CHECKPOINTED` state and `JOB_CHECKPOINTED` durability;
- same-operation duplicate reconciliation;
- provider-side ambiguity -> `EFFECT_UNKNOWN` with no blind replay;
- restart/reacquire behavior without a new durable table or checkpoint plane.

The Codex adapter intentionally still advertises `supports_checkpoint=False`. CCTX-0 therefore proves the provider-neutral authority/effect seam; it does **not** prove native Codex compaction.

Mastermind PR #630 is also protected. `mastermind.execution_plan/v2` now carries closed per-WORK placement requirements and Runtime projects them under the root-authorized ceiling. Context lifecycle must not be folded into that placement contract.

## Exact Codex 0.154.0 native semantics

The installed research probe previously identified Codex `0.154.0`; this amendment checked the exact upstream tagged source rather than extrapolating from current main.

### Method exists in the exact release

`codex-rs/app-server-protocol/src/protocol/common.rs` registers:

```text
ThreadCompactStart => "thread/compact/start"
params: ThreadCompactStartParams
serialization: thread_id(params.thread_id)
response: ThreadCompactStartResponse
```

So the exact installed-version family has a native compaction actuator. The governed Mastermind adapter is simply not exposing it yet.

### Request response means start accepted, not compaction completed

In exact `rust-v0.154.0`, `thread_compact_start_inner(...)`:

```text
load_thread(thread_id)
ensure_direct_input_allowed(thread)
submit_core_op(..., Op::Compact)
return ThreadCompactStartResponse {}
```

The response is an empty object. It confirms that the core operation was submitted successfully. It is not sufficient evidence that compaction completed durably.

`ensure_direct_input_allowed` only rejects direct app-server input to multi-agent-v2 spawned sub-agents. It is **not** itself a general "thread is idle" fence. Mastermind should therefore retain its own exact current-turn/writer safety check rather than infer safe checkpoint timing from this native helper.

### Completion has a concrete native event pair

Codex's exact v0.154.0 compaction tests require:

```text
item/started   ThreadItem::ContextCompaction { id }
item/completed ThreadItem::ContextCompaction { same id }
turn/completed for the compaction turn
```

The manual compaction test reads the empty `thread/compact/start` response first, then separately waits for the `ContextCompaction` started item, raw response completion, matching completed item, and compaction turn completion.

This distinction is load-bearing for Mastermind effect handling:

- RPC accepted -> provider effect may now exist;
- matching native completion -> provider compaction completed;
- transport loss / timeout after submission but before completion can be proven -> `EFFECT_UNKNOWN`, not "retry compact".

### Resume continuity is tested upstream

The exact v0.154.0 manual test changes thread cwd on a prior turn, manually compacts, completes a follow-up turn, gracefully shuts down App Server, starts a new App Server, resumes the same thread and verifies that the updated cwd survives. This is useful evidence that native compaction participates in persisted thread continuity; Mastermind still must bind that provider continuity to its own current RuntimeBinding / session epoch / generation and checkpoint authority.

### Usage exists separately from completion

The manual test receives `RawResponseCompletedNotification` with usage fields including total/input/cached/cache-write/output/reasoning token counts. This is useful telemetry, not authority and not by itself checkpoint completion.

## CCTX-1 ruling

Implement native Codex compaction only as a provider implementation of the **already-protected** CCTX-0 checkpoint operation.

Do not add:

- a context database;
- a prompt-cache registry;
- a transcript memory plane;
- a second compaction protocol;
- another provider event reader;
- another session registry;
- another checkpoint table;
- a provider-specific lifecycle outside Executive Runtime.

The first native vertical is:

```text
Executive generation-bound checkpoint INTENT
 -> exact current Codex RuntimeBinding + provider thread
 -> Mastermind idle/current-writer fence
 -> thread/compact/start
 -> existing authoritative App Server event reader observes ContextCompaction started/completed
 -> compaction turn terminal
 -> adapter emits bounded CheckpointObservation candidate
 -> Executive applies CCTX-0 checkpoint APPLIED
 -> SAME_ATTEMPT continuation / lawful resume
```

## Exact provider adapter contract

### Before dispatch

The adapter/orchestrator path must refuse unless all of these are current and exact:

- current Attempt;
- current session epoch;
- current process generation;
- current Executive writer;
- exact Codex provider session/thread identity belonging to that generation;
- no incompatible active Mastermind turn for that thread;
- exact adapter capability attestation for the supported Codex release/profile;
- the CCTX-0 checkpoint operation has been reserved first.

Do not let a caller supply a thread id independent of the current RuntimeBinding/session observation.

### Provider submission

Use exactly one `thread/compact/start` for the current thread under one CCTX-0 `OperationId`.

After submission is possible, any lost/ambiguous reply is effect uncertainty. No second compact, thread switch, account switch, host switch, new Attempt, or replacement provider session is allowed until the original operation is reconciled.

### Native completion

Do not mark the Executive checkpoint APPLIED from the empty RPC response alone.

Require the existing authoritative Codex event path to observe a matching native compaction lifecycle for the same provider thread:

1. one `ContextCompaction` item started;
2. the same native item id completed;
3. its compaction turn reaches the expected terminal state.

If Codex emits a provider failure/turn failure after accepted start, persist/refuse according to the existing checkpoint operation and failure classification; do not fabricate an accepted checkpoint.

The provider event stream has one owner. CCTX-1 consumes/extends the existing reader and cursor semantics; observability and context-pressure projections must not drain or race provider notifications independently.

### Checkpoint candidate

The adapter's `CheckpointObservation.checkpoint_candidate` should be bounded continuity evidence, not a transcript dump and not hidden chain-of-thought.

At minimum it should bind already-existing identities/facts sufficient for safe same-Attempt continuation, such as:

- provider/session/thread identity already bound by the current generation;
- native compaction item id / compaction turn id or bounded digest/reference to the exact observed completion;
- current provider continuation coordinates required by the existing resume path;
- exact operation/cursor evidence required to prevent double-consumption;
- observed usage/cache fields when actually exposed;
- any bounded context-pressure observation used to justify compaction, explicitly marked observed vs locally estimated.

Do **not** duplicate Executive Job/Attempt/generation/lease authority inside an adapter-owned store. Executive already persists the checkpoint candidate with the checkpoint sequence.

## Capability advertisement law

Keep `CodexOperatorAdapter.supports_checkpoint=False` until all of the following exist on one immutable implementation head:

1. actual adapter `checkpoint(...)` implementation using `thread/compact/start`;
2. exact current-thread/current-generation binding rather than caller-selected thread identity;
3. one authoritative event-consumption path for native completion;
4. CCTX-0 ambiguity/replay/restart semantics preserved end-to-end;
5. provider-free exact-version protocol tests plus hermetic adapter tests;
6. independent exact-head review and current protected-source compatibility proof.

A method existing in upstream Codex does not by itself qualify the governed Mastermind profile.

## Required discriminators

### N1 — accepted-start is not completion

Make the fake/native peer return the empty `thread/compact/start` response but never emit matching ContextCompaction completion. Executive checkpoint must not advance to APPLIED / `JOB_CHECKPOINTED`.

### N2 — exact native item pairing

Started id A + completed id B must refuse/hold rather than credit completion. Duplicate completion for A must not advance checkpoint sequence twice.

### N3 — wrong thread / wrong generation

A valid compaction event from another provider thread or stale generation cannot satisfy the current operation.

### N4 — busy/current-turn fence

Checkpoint request while the governed thread has an incompatible active turn refuses before native compaction submission. Prove no `thread/compact/start` was sent.

### N5 — post-submit ambiguity

Lose transport after native submission before completion proof. Result must be `EFFECT_UNKNOWN`; retry with the same OperationId must hit the existing replay fence rather than submit another native compaction.

### N6 — provider failure

Native compaction turn failure after accepted start must not emit an Executive accepted checkpoint or erase the prior checkpoint.

### N7 — restart continuity

After one accepted checkpoint, restart/reacquire through existing RuntimeBinding/session recovery. Prove the same logical provider thread can be resumed with the accepted checkpoint facts and that checkpoint sequence remains monotonic.

### N8 — no transcript authority

Checkpoint candidate must remain under existing size/schema bounds and omit raw transcript/chain-of-thought. Current owner facts re-read after resume override any stale compacted summary.

### N9 — observer non-interference

A concurrent visible-turn/context-pressure observer cannot steal the compaction started/completed events or cause the controller to miss terminal completion.

### N10 — cache telemetry honesty

If cached-input/cache-write usage is absent, preserve unknown/unobserved semantics where material. If present, record it through existing usage/cost owners; never infer a cache hit from reduced latency alone.

### N11 — upstream boundary

An unsupported/changed Codex profile/version keeps checkpoint capability false until requalified. Do not silently assume future/older App Server notification shapes match 0.154.0.

### N12 — no-orphan composition

A long-running worker that compacts while a nonterminal `BLOCKED` / `DECISION_REQUEST` responsibility exists must preserve that obligation across checkpoint/resume. CCTX-1 itself does not invent the semantic-yield/wake plane; it composes later with the existing AD-RET2 / Dialogue / Wake owner so the same responsibility remains actionable after compaction.

## Relationship to AD-RET2 and the autonomy close loop

CCTX-0/CCTX-1 and sustained semantic return are orthogonal dependencies.

Context continuity answers:

> Can the same logical responsibility survive pressure, compaction, rotation and restart without replaying effects or forgetting critical state?

AD-RET2 answers:

> Can a live operator's material `BLOCKED` / `DECISION_REQUEST` become durable provider-neutral attention to the exact Sol action target without voluntary Slack prose being the only source?

Full no-orphan acceptance needs both:

```text
live governed worker
 -> material nonterminal yield
 -> durable exact Sol attention
 -> Sol CONTINUE / repair / STOP
 -> same logical worker consumes it
 -> context pressure + governed native checkpoint/compaction
 -> restart/resume
 -> unresolved obligation and effect identities still exact
 -> worker proceeds without Chairman relay/account selection
```

Do not make CCTX-1 wait on AD-RET2 source implementation if provider-free native qualification is otherwise source-disjoint, but do not claim autonomous closed-loop acceptance until the composed real path is proven.

## Context projection and cache economics stay separate from native compaction

Native compaction is not the entire context system.

Continue to prefer this ladder:

1. progressive disclosure / load only relevant evidence;
2. replace immutable bulk with exact references and discriminating facts;
3. bounded child context rather than parent-transcript inheritance;
4. stable reusable prefix before volatile owner-derived facts;
5. provider-native cache observation through existing usage/cost telemetry;
6. native compaction only under actual pressure;
7. lawful resume/rotation only when needed.

A successful compaction does not certify cache efficiency, context sufficiency, semantic correctness or fresh company truth.

## Implementation ownership and routing

Fable remains the incumbent fabric integration/adjudication principal.

CCTX-1 implementation is now a bounded, architecture-frozen engineering vertical. Preferred route when a fresh source child is lawfully placed:

```text
COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT
CHAT_REASONING_MODE: NON_PRO_DEFAULT
PREFERRED_AVENUE: Terra
WHY: bounded Codex adapter/event/runtime implementation with exact discriminators over a frozen architecture
WHY NOT FABLE: principal capacity is needed for integration/adjudication, not this mechanical provider implementation
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement until a concrete eligible receiver exists
```

Escalate to CTO Sol only if exact event/recovery behavior reveals a difficult bounded integration defect. Do not create a worker-facing OPEN_PICKUP packet while no receiver exists.

Current active W1-H2 strict-v2 admission/install-enabler work and current source writers retain precedence. Before CCTX-1 source `START`, fresh-check collisions in `control_plane/codex_operator_adapter.py`, App Server client/event-reader paths, RuntimeBinding owners and their tests. Do not race an active writer merely because #623 and #630 themselves are protected.

## Capability ledger at current pin

- provider-neutral no-rebuild context/checkpoint architecture: **BUILT_NOT_PROVEN**;
- generation-bound Executive/OHF checkpoint authority (CCTX-0): **BUILT_NOT_PROVEN / PROTECTED**, provider-free; not a production provider proof;
- native Codex `thread/compact/start` existence at exact 0.154.0 source: **BUILT upstream / QUALIFIED AS SOURCE EVIDENCE**, not Mastermind implementation;
- governed Codex checkpoint adapter: **NOT_BUILT** (`supports_checkpoint=False`);
- native compaction event/completion mapping into Mastermind checkpoint: **NOT_BUILT**;
- deterministic bounded context projection / narrow child packets: **PARTIAL** across existing seams, no single production-proof vertical yet;
- rich-OHF cache usage normalization: **PARTIAL**;
- sustained provider-neutral nonterminal semantic return (AD-RET2): **SPEC_ONLY / REQUIRED FOR NO-ORPHAN ACCEPTANCE**;
- full context + semantic-return autonomous closed loop: **NOT_BUILT / NOT_PROVEN**.

## Exact next action

Do not replay CCTX-0.

First, preserve the current root's W1-H2 admission/install-enabler critical path and active source custody. In parallel when a source-disjoint receiver is available, commission **CCTX-1** as one bounded Codex-native checkpoint implementation over the protected #643 seam, using exact 0.154.0 protocol semantics and N1–N12 as the release discriminators.

The first implementation return must include: immutable head; exact changed paths; provider-free RED→GREEN receipts; exact fake/native event evidence; current-base collision/material-source proof; hosted test/security; independent non-author review; and an explicit statement that no real provider thread/canary was invoked unless a later separate authority edge permits it.
