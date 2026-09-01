# Autonomy Stage-B0 / Stage-B1 — Durable Sol Action-Target Transfer Implementation Plan

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `autonomy-stage-b-durable-target-transfer-f0-20260901-sol-001`  
**Protected source and Skillpack basis:** `mastermindx-market-intelligence/Mastermind@c6af57d1ce96ed3f5ca8237099f4a5ecfa01d3cf`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1  
**Governing design:** `docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

## 1. Observable mission

Deliver one deterministic, command-reconcilable Executive capability where an existing root Job’s
current Sol target can be initially assigned, advanced to a successor RuntimeBinding generation, or
transferred to another lawful Sol alias through one immutable Runtime event—and the unchanged Stage-A
resolver immediately consumes that folded assignment without a second target store or provider action.

## 2. Why this is the next dependency

Mastermind now has separate pieces for logical SessionTargets, RuntimeBinding projection, exact action
authority, Capacity selection, ACK, terminal return, and context-rotation law. The missing seam is the
durable handoff between “the successor exists and acknowledged” and “this exact successor is now the
one Sol allowed to act for the root responsibility.”

Without Stage B:

- a fresh session may exist but remain observer-only;
- a stale root binding may survive context rotation;
- a UI or operator may be tempted to choose the newest visible tab;
- lost transfer responses cannot be reconciled safely;
- responsibility transfer remains manual Slack archaeology rather than a canonical Executive fact.

Stage B closes only this seam. Provider materialization, capacity selection, ACK, terminal return,
Control Room deployment, and production canaries remain independent capabilities.

## 3. Authority and document precedence

Highest specificity first:

1. current explicit Chairman directive to continue the Autonomy completion program;
2. current protected Skillpack and universal source laws at the action-time protected SHA;
3. `docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md`;
4. `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`;
5. `docs/superpowers/specs/2026-08-29-organizational-continuity-sol-action-authority-amendment.md`;
6. current `control_plane/sol_action_target.py`, `session_targets.py`,
   `runtime_binding_projection.py`, and `executive_runtime.py`;
7. this implementation plan;
8. worker PR prose and transport messages as evidence only.

A newer protected source that changes Runtime transaction, target authority, RuntimeBinding, ACK,
terminal-return, or context-rotation semantics must be reconciled before implementation. Path-disjoint
data, research, evaluation, or publication movement may be joined history-preservingly without
regenerating accepted Stage-B source.

## 4. Verified current state

### `PROVEN_LIVE`

None of the Stage-B transfer capability is production-proven.

### `BUILT_NOT_PROVEN`

- exact action-target Stage-A deterministic resolver;
- Executive Runtime immutable event/transaction primitives;
- Runtime current-harness binding facts;
- SessionTarget and RuntimeBinding contracts.

### `SPEC_ONLY`

- Web-Sol context-rotation succession law;
- this Stage-B records wave until protected.

### `NOT_BUILT`

- durable root-job target assignment/transfer event family;
- command-first transfer transaction;
- Stage-B projector into the Stage-A consumer;
- real successor-session transfer canary.

### Material disagreement repaired by this records wave

Earlier local reports described Stage-B0 and Stage-B1 as built or staged, but canonical GitHub had no
branch, PR, or operation-key carrier. The correct pre-wave state is `NOT_BUILT`. This plan creates the
first real records carrier and does not reuse those failed reports as implementation evidence.

## 5. Exact Stage-B0 records scope

This records wave changes exactly:

```text
docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md
docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md
tests/test_autonomy_stage_b_durable_target_transfer_source_law.py
```

It creates no code path, service, migration, configuration, route, provider process, Runtime row, or
production effect.

## 6. Stage-B1 operator handoff

### Routing receipt

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
ROUTE: Codex-backed bounded architecture-sensitive engineering worker
WHY: the transaction, event, replay, projection and concurrency boundaries are frozen and require disciplined repository implementation and adversarial tests
WHY NOT FABLE: no unresolved product thesis or cross-repository principal ambiguity remains after STAGE-B0; scarce principal capacity is unnecessary
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

No worker-facing open pickup is emitted merely because automated placement is incomplete. Once a
concrete eligible receiver is lawfully assigned, delivery is the assignment edge and the worker must
ACK, read current source, arm continuation, and separately START when gates are clear.

### Exact expected implementation paths

```text
control_plane/sol_action_target_transfer.py
control_plane/executive_runtime.py
tests/test_sol_action_target_transfer.py
tests/test_sol_action_target.py
tests/test_executive_runtime.py
```

A fresh collision census may narrow these paths. A required sixth authority/production path, new
migration, new table, provider adapter, or common worker-wire change requires a finite
`DECISION_REQUEST` before edit.

### Explicit non-goals

- no provider process/session creation, resume, wake, stop, or cleanup;
- no Capacity selection or placement commitment;
- no mutation of Job, Attempt, Worker, RuntimeBinding, ACK, or source-resolution rows;
- no target pointer/current-target table;
- no second SessionTargetRegistry or RuntimeBinding registry;
- no Slack/Linear/Agent OS lifecycle state;
- no Control Room UI work;
- no automatic context rollover;
- no production route, installer, service, credential, or deployment;
- no generic retry/failover policy;
- no CAP-S1, ACK1, terminal-return, or materialization implementation absorbed into this PR.

## 7. Data and contract behavior

### Identity

The root Job is the durable responsibility. Target identity is the tuple:

```text
session_alias
binding_id
binding_generation
attempt_id
session_epoch_id
reasoning_surface
```

Provider-native handles, provider session IDs, account labels, Slack principals, raw model text, and
filesystem paths are excluded from Stage-B persistence.

### Time and freshness

Stage B does not read wall-clock time to elect a target. Currentness comes from canonical source state
inside the Runtime transaction and current authority/evidence events. Timestamps may be retained by
the existing Event owner but never rank candidates or choose the latest session.

### Nulls

- `previous_target` is null only for `INITIAL_ASSIGNMENT`;
- source terminal/release evidence is null only where the mode explicitly permits it;
- missing destination materialization or ACK is a typed wait/refusal, never a guessed positive;
- missing current binding is unavailable, not zero-generation or default alias.

### Replay

The stable command ID is derived from canonical semantics. Identical replay returns the existing event
before mutable-state reads. Changed semantics conflict. A lost response never authorizes a second
operation key, carrier, target, or transfer.

### Correction

Events are immutable. Correction is a new transfer at the next expected assignment revision after
current-state reconciliation. No update/delete/rewrite path is introduced.

## 8. Deterministic versus model-generated behavior

Deterministic first-party code owns:

- command normalization and digest;
- transaction and command lookup;
- event-history fold;
- revision and source/destination comparison;
- RuntimeBinding read and validation;
- evidence-event identity checks;
- event append;
- snapshot projection;
- Stage-A consumer invocation;
- error mapping and secret-safe output.

Model output has zero authority to select a target, claim an ACK/release, choose a revision, construct
a binding, resolve a replay, or widen scope. A model may help write code or propose a transfer, but the
Runtime transaction independently re-derives and validates every privileged fact.

## 9. Ordered implementation sequence

<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->
```text
1. RE-PIN_AND_COLLISION_FREEZE
2. RED_COMMAND_EVENT_AND_FOLD_TESTS
3. IMPLEMENT_CLOSED_TYPES_CANONICALIZATION_AND_PROJECTOR
4. RED_RUNTIME_TRANSACTION_AND_REPLAY_TESTS
5. IMPLEMENT_EXISTING_RUNTIMESTORE_TRANSACTION_SEAM
6. RED_STAGE_A_REAL_CONSUMER_TESTS
7. INTEGRATE_ROOT_BINDING_OVERLAY_WITH_UNCHANGED_STAGE_A_RESOLVER
8. RED_CONCURRENCY_EFFECT_UNKNOWN_AND_SECRET_TESTS
9. RUN_MUTATION_AND_FORBIDDEN_PLANE_PROOF
10. RUN_FOCUSED_ADJACENT_FULL_FEASIBLE_AND_STATIC_GATES
11. PUBLISH_ONE_DRAFT_HOLD_CARRIER
12. INDEPENDENT_EXACT_HEAD_REVIEW_AND_HOSTED_CI
13. SOL_RELEASE_ADJUDICATION
```
<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->

### Step 1 — Re-pin and freeze

- load current protected Skillpack and governing sources at one SHA;
- read the complete commission carrier;
- inspect all open PRs and branches touching the expected five paths;
- verify STAGE-B0 is protected;
- identify exact current Runtime transaction, binding, ACK, terminal-return, and materialization event
  owners;
- return `PATH_FREEZE` before source edits;
- emit separate `START` only when no duplicate owner/effect exists.

### Step 2 — RED command/event/fold tests

Write failing tests for strict fields, canonical key ordering, deterministic command identity,
initial assignment, valid succession/transfer, history gaps, duplicate revisions, wrong previous
links, unsupported modes, forbidden persisted fields, and immutable correction behavior.

### Step 3 — Closed types and projector

Implement one Python-stdlib-only module with immutable dataclasses/enums, exact wire parsing,
canonical JSON, stable digest, event fold, root-binding overlay, and snapshot projection. It owns no
I/O except through explicitly injected current source rows.

### Step 4 — RED Runtime transaction tests

Prove command lookup occurs before mutable assignment and binding reads, same-command replay survives
later session movement, changed replay conflicts, stale expected revision refuses, and all evidence is
read on the same connection.

### Step 5 — RuntimeStore composition

Add the smallest Runtime method that:

- opens `RuntimeStore.transaction()`;
- checks `get_event_by_command_id()` first;
- folds the root Job’s target events;
- calls `current_harness_binding_source(..., connection=tx)`;
- validates exact evidence events;
- appends one event with `append_event(..., connection=tx)`.

Do not add a table, migration, cursor, cache, transaction owner, or provider call.

### Step 6 — RED Stage-A consumer tests

Use the real `resolve_sol_action_target()` API. Prove the destination actor becomes authoritative only
after the folded root binding and exact RuntimeBinding snapshot agree, while source/sister/stale actors
remain observer-only.

### Step 7 — Integration

Create the registry overlay through `SessionTargetRegistry.with_root_job_bindings()` and feed a
complete RuntimeBinding snapshot to Stage A. Preserve the exact Stage-A public signature and all prior
negative behavior.

### Step 8 — Concurrency and failure law

Prove concurrent revision-N transfers serialize; one append wins and the other refuses without
rebasing. Prove effect-unknown evidence, response loss, missing ACK/materialization/release/terminal
records, stale authority, Runtime conflict, and transaction unavailability all fail closed.

### Step 9 — Mutation and forbidden-plane proof

Individually remove or bypass:

- command-first lookup;
- expected revision compare;
- previous-target compare;
- same-transaction binding read;
- source release gate;
- source terminal gate;
- destination materialization gate;
- destination ACK gate;
- actor check in Stage A;
- forbidden-field filter.

Each mutation must make its intended discriminator fail. Census source for forbidden table/migration,
provider/network/Slack/Agent OS writes, and secret/native-handle leakage.

### Step 10 — Repository proof

Run focused and adjacent tests, all feasible repository tests, compile, diff check, secret scan, and
static ownership census. Local environment gaps must be named; hosted CI is the release receipt.

### Step 11 — One carrier

Publish one Draft/HOLD PR from one branch and one operation key. Never replace it because protected
master moves. Join path-disjoint current source history-preservingly, preserve implementation blobs,
and rerun only the proof invalidated by movement.

### Step 12 — Independent review

Reviewer must evaluate the original capability, not merely syntax. Required questions:

- does the real Stage-A consumer see exactly one current target?
- can an identical replay succeed after the old writer is gone?
- can changed payload or stale revision create a second event?
- did any path mutate RuntimeBinding or provider state?
- can a caller/model smuggle privileged binding data?
- is a source law/spec being called production proof?

### Step 13 — Sol adjudication

Merge only an exact current-base head with green hosted checks, empty blocking threads, bounded path
surface, accepted independent review, and truthful `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` state.

## 10. Acceptance matrix

### Truth

- exact root Job and assignment revision;
- exact SessionTarget alias and target seat;
- exact current RuntimeBinding ID/generation;
- exact materialization, ACK, source terminal/release, and authority evidence references;
- command-first replay and immutable event history;
- correction-safe next-revision behavior.

### Intelligence and authority

- deterministic mode/precondition classification;
- no newest-tab/account/title/timestamp election;
- caller/model claims independently re-derived;
- effect uncertainty blocks transfer;
- no transfer before successor readiness.

### Product/machine capability

- one real Stage-A resolver call changes from source-authoritative to destination-authoritative after
  the event fold;
- source/sister actors remain observer-only;
- absent/conflict/unknown state is visible and typed;
- restart/replay produces no second transfer.

### Learning/evidence

- exact immutable head and path set;
- focused/adjacent/full feasible counts;
- mutation kills bound to named laws;
- hosted CI/security receipts;
- explicit zero-row-mutation and zero-provider-action proof;
- next production canary gate recoverable without chat history.

## 11. Required adverse cases

At minimum:

```text
no prior assignment
valid initial assignment
initial static-root mismatch
valid same-alias succession
same generation or lower generation
source release missing
valid cross-alias transfer
source terminal missing
source alias equals destination in cross-alias mode
missing destination materialization
missing destination ACK
missing destination RuntimeBinding
two destination bindings
surface mismatch
stale authority
EFFECT_UNKNOWN
stale expected revision
wrong previous target
identical command replay
changed semantic replay
lost response after commit
concurrent same-revision commands
history revision gap
history duplicate revision
history wrong previous link
unsupported mode
forbidden persisted field injection
actor/source/sister authority separation
key/list/input permutation determinism
```

## 12. Stop states

Return to Sol without widening on:

```text
STAGE_B0_NOT_PROTECTED
ACTIVE_WRITER_COLLISION
CURRENT_SOURCE_MOVED_MATERIALLY
RUNTIME_TRANSACTION_OWNER_UNRESOLVED
ACK_EVIDENCE_OWNER_UNRESOLVED
MATERIALIZATION_EVIDENCE_OWNER_UNRESOLVED
TARGET_EVENT_AGGREGATE_CONFLICT
NEW_TABLE_OR_MIGRATION_REQUIRED
SIXTH_AUTHORITY_PATH_REQUIRED
COMMON_WIRE_SCOPE_COLLISION
EFFECT_UNKNOWN
PROVIDER_ACTION_REQUIRED
```

A deterministic pre-effect defect inside the frozen five paths may be repaired on the same carrier.
A response ambiguity or possible modifying effect must be reconciled on that carrier before any
retry or receiver change.

## 13. Release and completion boundary

### STAGE-B0 release

One exact-current-base records PR, source-law tests, hosted CI/security, independent review, and
expected-head merge. Result only:

```text
SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED
```

### STAGE-B1 release

One exact-current-base implementation PR, all blockers closed, real Stage-A consumer proof, hosted
CI/security, independent review, expected-head merge. Result only:

```text
BUILT_NOT_PROVEN / TRANSFER_SOURCE_PRODUCTION_DISARMED / PROTECTED
```

### Production proof later

A separate bounded canary must prove:

```text
existing source target
-> terminal/continuity and release evidence
-> successor materialization
-> successor RuntimeBinding
-> successor ACK1
-> Stage-B event
-> Stage-A destination authority
-> bounded useful turn
-> predecessor cleanup
-> restart replay
-> Control Room visibility
```

Only that real path can promote the capability toward `PROVEN_LIVE`.

## 14. Continuation handoff required from Stage-B1 worker

Return on the exact carrier with:

- protected base, exact head, tree, parents, branch and PR;
- exact changed paths and active-writer census;
- command/event/snapshot field sets;
- transaction ordering and owner methods;
- RED-to-GREEN counts and named mutation kills;
- concurrent/replay/effect-unknown proof;
- real Stage-A consumer result;
- Job/Attempt/Worker/RuntimeBinding/ACK/source-resolution/provider zero-mutation evidence;
- compile/diff/secret/forbidden-plane results;
- hosted CI/security and independent review status;
- local, remote, runtime, provider and production effects;
- exact live-canary predecessor and next action;
- watcher state.

After a worker `RESULT`, Sol must issue one explicit same-carrier `STOP` or repair continuation. Silence
is not terminal.
