# CCTX-1 effect/concurrency hardening

**2026-09-15 | RECORDS_ONLY / IMPLEMENTATION_FREEZE / PRODUCTION_INERT**

Parent: `ORCHESTRATOR_CCTX1_NATIVE_COMPACTION_QUALIFICATION_2026-09-15.md`.
Protected Mastermind basis: `19b6111891ffd742ceec7c96f437a2a890847c92`.
This amendment is source analysis and implementation freeze only. It authorizes no child START, provider call, credential use, route, install, merge, or production claim.

## Why this amendment exists

The exact protected CCTX-0 seam exposed a correctness gap that only becomes relevant when a real provider implementation is added.

`OperatorHarnessOrchestrator.checkpoint()` currently commits checkpoint INTENT first, then calls `adapter.checkpoint(...)`. Every exception from that adapter call is currently recorded as `EFFECT_UNKNOWN`.

That is correct after provider submission may have happened. It is too strong for a **proven local refusal before provider I/O** such as:

- current work turn still active;
- current attention/wake turn still active;
- local process identity changed before dispatch;
- stale/mismatched provider session binding observed before dispatch;
- provider-operation mutex already held;
- stale compaction notification baseline makes causality ambiguous before submission.

Turning these zero-provider-effect refusals into `EFFECT_UNKNOWN` would poison an otherwise healthy Same-Attempt responsibility and undermine the no-orphan objective.

The frozen OHF vocabulary already has the right terminal receipt: `OperationReceiptKind.REFUSED` / `OPERATOR_OPERATION_REFUSED`. `resolve_operation_after_crash()` already distinguishes `REFUSED` from `EFFECT_UNKNOWN`. Reuse that owner; do not invent a checkpoint-preflight lifecycle or a second compaction protocol.

## Current source findings

### CCTX-0 reserve does not own provider idleness

Protected `reserve_checkpoint_operation(...)` validates current generation, current epoch, Executive writer, fence/lease, provider session and checkpoint sequence, then commits INTENT. It does **not** prove that the native provider thread is idle.

That is reasonable: provider/native activity is adapter/session state, not SQLite lifecycle truth.

### Codex already has a useful idle model

Protected `CodexOperatorAdapter.deliver_attention(...)` refuses provider I/O while:

- `attention_inflight` is true; or
- any Executive work turn in `state.turns` lacks a normalized `turn/completed` event.

It also verifies current process identity and liveness before its final provider I/O boundary. CCTX-1 should reuse the same semantics rather than create a second definition of "idle".

### But CCTX-1 also needs mutual exclusion

A pure "check idle" followed by `thread/compact/start` is TOCTOU-unsafe. A work turn or Wake attention turn could enter between the check and native compact submission.

Therefore one generation-local provider-operation gate must serialize **provider turn admission vs checkpoint/compaction dispatch** inside the existing Codex adapter instance.

This is not a new lifecycle or lock service. It is an in-memory mutex protecting the already-single current provider writer.

### Current event consumption is work-TurnRef-bound

`CodexOperatorAdapter.read_events()` and `_ingest_turn_notifications()` bind notifications to an Executive work `TurnRef`. Native manual compaction creates its own Codex provider turn but is **not** an Executive work turn.

Do not mint/fake an Executive work Turn merely to consume compaction notifications. That would pollute TX-5 cardinality/result semantics.

The existing `AppServerClient` remains the sole stdout reader. It already demultiplexes RPC responses and provider notifications. CCTX-1 needs a **selective consumption primitive on that same reader**, not another reader/thread/event queue.

## Frozen CCTX-1 transaction behavior

### 1. INTENT remains before provider effect

Keep the protected ordering:

```text
checkpoint INTENT
 -> adapter checkpoint implementation
 -> native provider submission
 -> exact completion observation
 -> checkpoint APPLIED
```

Do not move Executive INTENT after provider submission.

### 2. Add exact checkpoint REFUSED resolution

Add a checkpoint-specific RuntimePort/Runtime terminal refusal path using existing `OperationReceiptKind.REFUSED`.

A refusal is legal only when the adapter exception explicitly proves that no provider compaction submission was attempted.

Recommended shape (names may follow local conventions):

```text
RuntimePort.refuse_operator_checkpoint(attempt_id, generation, operation_id, refusal)
Runtime.operator_harness.refuse_checkpoint_operation(...)
```

The durable transaction must:

- require the exact committed checkpoint INTENT;
- require the exact current Attempt/generation/writer/fence/lease;
- reject if APPLIED or EFFECT_UNKNOWN already exists;
- be idempotent for the same refusal payload;
- write one `OPERATOR_OPERATION_REFUSED` receipt;
- not advance `checkpoint_sequence`;
- not mutate `checkpoint_json`;
- not emit `JOB_CHECKPOINTED`;
- carry only bounded deterministic refusal metadata (for example failure class/reason code), never provider text.

Do not add a new table or receipt family.

### 3. Orchestrator distinguishes zero-effect refusal from ambiguity

Checkpoint exception handling becomes three-way:

```text
adapter returned CheckpointObservation
 -> apply checkpoint

adapter raised explicit no-provider-effect refusal
 -> durable REFUSED
 -> return/raise typed refusal, NOT OperatorEffectUnknown

adapter may have crossed provider I/O boundary
 -> existing EFFECT_UNKNOWN path
```

Do not infer safety from exception type alone. The adapter error must carry an explicit effect classification; current `CodexAdapterError.effect_unknown` can supply this if tightened so every provider-I/O path marks `True` and local validation paths remain `False`.

If the REFUSED persistence itself cannot be committed after a proven local refusal, fail closed. Absence of a terminal receipt after INTENT is not permission to resend provider work.

### 4. One provider-operation gate inside Codex generation state

Add one generation-local non-reentrant provider-operation gate/mutex owned by `CodexOperatorAdapter` state.

The gate covers provider-dispatch admission for:

- normal `begin_turn` submission;
- Wake/attention `turn/start` submission;
- checkpoint `thread/compact/start` submission through terminal compaction observation.

Desired behavior:

- if checkpoint owns the gate, new work/attention turn admission refuses before provider I/O;
- if a work/attention submission owns the gate first, checkpoint either observes an active turn and REFUSES before compact I/O or fails to acquire the gate and REFUSES before compact I/O;
- after `turn/start` is acknowledged, normal work need not hold the mutex for the whole model turn: its durable/adapter active-turn state blocks checkpoint until `turn/completed` is observed;
- checkpoint holds the gate through native compaction terminal observation so no second provider turn can be admitted mid-compaction.

No blocking wait loop is required. Prefer immediate typed conflict/refusal over hidden lock waits that can consume leases.

### 5. Provider activity check must use one definition

Before native compact submission, under the provider-operation gate, require all of:

- current state/generation/session identity;
- `ProviderWriterState.HELD`;
- current process identity equals launch observation and process is alive;
- `attention_inflight == False`;
- every Executive work turn in `state.turns` has a matching normalized `turn/completed` event;
- no existing checkpoint/compaction is inflight for the generation.

Failure before `thread/compact/start` is a deterministic REFUSED checkpoint operation.

### 6. Native compact I/O boundary is exact

Immediately before calling:

```text
thread/compact/start { threadId = current provider_session_id }
```

the implementation must transition its local classification to "provider effect may exist".

From that point onward, transport loss, malformed response, timeout, mismatched completion, process crash, unknown terminal status or inability to prove the exact native completion is `effect_unknown=True` unless the provider itself gives a definitive failure proving no compaction effect.

No automatic retry.

## Notification ownership without a second reader

### Problem

`AppServerClient.wait_notification(method)` removes the first notification with that method. `drain_notifications()` removes everything. Neither is sufficient for a compaction operation that must consume only its own native provider turn while preserving unrelated delayed/account/tool notifications.

Compaction may also emit provider `turn/started` before the empty RPC response returns, so "start listening after response" can miss the causal beginning if the helper destructively drained the queue.

### Required extension to the existing AppServerClient

Extend the **same** AppServerClient stdout/notification owner with bounded selective notification ownership. Do not launch another stdout reader.

Implementation may choose a cursor/watermark or an equivalent exact identity mechanism, but it must support these properties:

1. capture a pre-dispatch notification watermark/baseline under the existing notification lock;
2. wait for/remove a notification **after that watermark** matching an exact predicate without removing nonmatches;
3. after the compaction native turn id is learned, drain/remove only notifications belonging to that exact `(threadId, native_compaction_turn_id)`;
4. leave notifications for unrelated threads/turns/methods available to their existing consumers;
5. never expose raw provider text solely to identify the event; match bounded structured identity fields on redacted notifications;
6. keep current `wait_notification()` / `drain_notifications()` behavior backward-compatible for existing owners.

A private monotonically increasing notification sequence inside `AppServerClient` is acceptable because it is process-local reader bookkeeping, not durable lifecycle state.

### Exact compaction event identity

From Codex 0.154.0, wait for a post-baseline event with:

```text
method = item/started
params.threadId = current provider thread
params.item.type = contextCompaction
```

Capture:

```text
native_compaction_item_id = params.item.id
native_compaction_turn_id = params.turnId (or exact tagged equivalent)
```

Then require post-baseline:

```text
item/completed
same thread
same native compaction turn
item.type = contextCompaction
item.id = native_compaction_item_id
```

and:

```text
turn/completed
same thread
turn.id = native_compaction_turn_id
recognized successful terminal status
```

Any identity ambiguity after provider submission is EFFECT_UNKNOWN, not success and not retry.

After the terminal turn is proven, selectively consume any remaining buffered notifications for that exact compaction turn so they cannot be misattributed by the next Executive work TurnRef.

## Bounded checkpoint candidate

Keep CCTX-1 narrowly about continuity. Do not bundle full cache analytics into the same implementation PR.

The accepted checkpoint candidate should be a small schema/versioned object containing only continuity/effect evidence needed after restart, for example:

```json
{
  "schema_version": "mastermind.codex_compaction_checkpoint/v1",
  "provider_session_id": "<current bound thread>",
  "native_compaction_turn_id": "<id>",
  "native_compaction_item_id": "<id>",
  "completion_digest": "<sha256 over bounded normalized identity/status facts>"
}
```

Exact keys may be adjusted to current JobPayload constraints. Do not store transcript text, hidden reasoning, raw response bodies, credentials, lease tokens, or duplicate Executive authority facts.

Cache-read/cache-write token normalization is a follow-on telemetry slice unless the exact completion already exposes bounded usage with no widening. CCTX-1 acceptance is continuity correctness first.

## Added discriminators

In addition to N1-N12 from the parent packet:

### N13 — zero-effect refusal is not EFFECT_UNKNOWN

Create an active work turn, then request checkpoint. Assert:

- checkpoint INTENT exists;
- adapter sends zero `thread/compact/start` RPCs;
- one exact REFUSED receipt exists;
- no EFFECT_UNKNOWN receipt exists;
- checkpoint sequence/json unchanged;
- a later fresh checkpoint OperationId can succeed after the work turn is terminal.

Repeat for `attention_inflight` and provider-operation-gate contention.

### N14 — race: new turn cannot enter compaction

Barrier the test between checkpoint idle validation and compact submission. Concurrently attempt normal `begin_turn` and attention delivery. Exactly one side may own provider submission; no test schedule may produce overlapping `turn/start` + `thread/compact/start` on the same current thread.

### N15 — race: checkpoint cannot enter a just-started turn

Barrier around `turn/start` acknowledgment. Concurrent checkpoint must REFUSE with zero compact RPC after the work turn wins admission.

### N16 — notification non-stealing

Seed pre-baseline and concurrent unrelated notifications, including another thread's `item/started`, `item/completed`, `turn/completed`, `skills/changed` and account/tool updates. CCTX-1 must consume only its exact compaction turn. Existing consumer must still receive the nonmatches afterward.

### N17 — compaction notifications cannot poison next work turn

After successful checkpoint, start a normal Executive work Turn. Its `NormalizedEvent` set must not contain the prior native compaction turn's started/completed/terminal frames.

### N18 — refusal replay/crash semantics

For an exact REFUSED checkpoint operation, `resolve_operation_after_crash()` must resolve REFUSED rather than EFFECT_UNKNOWN. Reusing that terminal OperationId must not submit provider work; a fresh OperationId may be used once conditions change.

## Minimal implementation surface

Expected production paths for one CCTX-1 implementation wave:

- `control_plane/operator_harness_orchestrator.py` — REFUSED vs EFFECT_UNKNOWN checkpoint handling;
- `control_plane/executive_operator_harness_port.py` — narrow checkpoint refusal bridge;
- `control_plane/executive_runtime.py` — exact REFUSED receipt transaction; optionally reject conflicting unresolved checkpoint INTENT from TX-5 admission if needed by discriminating tests;
- `control_plane/codex_operator_adapter.py` — provider-operation gate, native compaction implementation, exact local effect classification;
- `scripts/ohf/laboratory.py` — same-reader selective post-watermark notification consumption;
- focused existing tests for Runtime/orchestrator/Codex adapter/AppServerClient.

Do not edit placement schemas, Capacity, Agent OS, Wake lifecycle, dialogue state, router, credentials, provider-realm enrollment, Control Room or Workbench merely to land CCTX-1.

If current source has another writer on any expected production path, CCTX-1 waits or is decomposed around the owner; no replacement branch/worktree is authorized by this record.

## Implementation order

1. RED: N13 proves current CCTX-0 misclassifies a local busy refusal as EFFECT_UNKNOWN once a real checkpoint adapter exists.
2. Runtime/orchestrator: add exact checkpoint REFUSED terminal receipt; preserve all existing CCTX-0 ambiguity tests.
3. RED: N14/N15 provider-dispatch races.
4. Codex adapter: generation-local provider-operation gate shared by work, attention and checkpoint admission.
5. RED: N16/N17 notification-stealing/poisoning.
6. AppServerClient: same-reader watermark/selective-consumption primitive.
7. Codex checkpoint: `thread/compact/start` + exact ContextCompaction pairing + successful compaction-turn terminal proof.
8. bounded checkpoint candidate; no transcript.
9. provider-free restart/reacquire proof through existing CCTX-0 checkpoint sequence.
10. only after the complete matrix is green, change Codex capability advertisement to `supports_checkpoint=True` for the exact qualified profile/version boundary.
11. hosted test/security + independent non-author exact-head review + current-base compatibility/collision receipt.

## Stop condition

Stop CCTX-1 when a provider-free governed Codex checkpoint can safely produce exactly one native compaction, classify local refusal vs unknown effect correctly, preserve notification ownership, persist one bounded Executive checkpoint and survive restart/reacquire — while `supports_checkpoint` is truthfully gated to the qualified implementation.

Do not absorb AD-RET2, real credential/provider canaries, cache optimization policy, cross-provider compaction parity, automatic context-pressure heuristics, or UI into this wave.
