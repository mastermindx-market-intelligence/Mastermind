# Autonomy Stage-B0-R1 / Stage-B1 — Corrected Durable Sol Action-Target Plan

**Original date:** 2026-09-01  
**Correction date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Correction operation:** `autonomy-stage-b0-protected-source-correction-r1-20260902-sol-001`  
**Protected source basis:** `mastermindx-market-intelligence/Mastermind@162af533a4bcf380125895d225b6962987c3c582`  
**Skillpack:** `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1  
**Governing design:** `docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED_SOURCE_CORRECTION_REQUIRED`

## 1. Why this correction exists

The original Stage-B0 source was protected before a later exact-head review completed. That review
proved the source was not implementation-grade: authority references had no owner, evidence references
were generic command IDs, ChatGPT-Web support was overstated, the registry overlay could delete other
roots/seats, and replay semantics contradicted a fully derived command ID.

Do not start Stage-B1 from the protected v1 source law. This Stage-B0-R1 records carrier replaces its
implementation authority with a v2 contract. The broader product goal remains unchanged: one durable
Sol responsibility must survive context/runtime rotation without stale actors, duplicate provider
writes, or Chairman message shuttling. The first code wave is narrower because current protected
owners support only Codex initial assignment and same-alias generation succession.

Cross-alias responsibility transfer remains held until an exact accepted authority receipt owner
exists. ChatGPT-Web remains held until one accepted current RuntimeBinding writer and exact semantic
ACK owner exist.

---

## 2. Observable records mission

Protect exactly one correction where:

- every supported transfer mode names its current canonical authority owner;
- every evidence requirement names an owner, lookup, aggregate/event, command law, schema/typed shape,
  identity closure, and effect-known rule;
- command identity is derived and caller-inaccessible;
- same-revision races produce one append and one revision refusal, not a fictional same-ID conflict;
- Stage-B projection preserves all unrelated roots and sibling seats;
- current source support is Codex-only;
- unsupported cross-alias and Web journeys are explicit held states;
- Stage-B1 cannot start until the correction itself is protected.

The records carrier changes only the existing design, plan, and source-law test. It produces no
Runtime, provider, Wake, target, host, or production effect.

---

## 3. Machine-readable implementation gate

<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b1_correction_gate.v1",
  "requires_protected_design_schema": "mastermind.autonomy_stage_b_f0_contract.v2",
  "v1_implementation_authority": "REVOKED_BY_POST_MERGE_REVIEW",
  "stage_b1_state": "HELD_UNTIL_V2_CORRECTION_PROTECTED",
  "authorized_modes_after_gate": [
    "INITIAL_ASSIGNMENT",
    "SAME_ALIAS_GENERATION_SUCCESSION"
  ],
  "held_modes": [
    "CROSS_ALIAS_RESPONSIBILITY_TRANSFER"
  ],
  "supported_reasoning_surfaces": [
    "codex"
  ],
  "held_reasoning_surfaces": [
    "chatgpt-web"
  ],
  "requires_exact_evidence_contracts": true,
  "requires_full_root_binding_merge_preservation": true,
  "requires_derived_command_id": true,
  "production_arming": false
}
```
<!-- STAGE_B1_CORRECTION_GATE_END -->

A records merge does not automatically open Stage-B1. The implementation worker must fresh-read
protected master and prove that this v2 schema, not v1, is the current protected law.

---

## 4. Capability ledger

### `PROVEN_LIVE`

None of Stage B.

### `BUILT_NOT_PROVEN`

- deterministic Stage-A action-target resolver;
- SessionTargetRegistry target/root-binding policy and projection interface;
- Runtime transaction/event primitives;
- Codex current-writer RuntimeBinding projection;
- Wake ACK ingress and causal Wake ledger;
- Operator Harness generation release/reconciliation evidence.

### `SPEC_ONLY`

- this corrected Stage-B0-R1 source until protected;
- broader cross-alias and Web-Sol continuity journeys.

### `NOT_BUILT`

- v2 Stage-B command/event/snapshot module;
- v2 Runtime transaction method;
- full-map Stage-A projection adapter;
- real initial assignment or succession event;
- cross-alias authority receipt owner;
- ChatGPT-Web binding/ACK owner;
- production transfer canary.

### `REJECTED_BY_DESIGN`

- target pointer/current-target table;
- caller-supplied command ID;
- generic evidence command references;
- newest-tab/generation/account/time election;
- Slack/model prose as authority;
- Stage-B-authored ACK or source resolution;
- destructive one-root registry replacement;
- effect-unknown retry/failover.

---

## 5. Exact Stage-B0-R1 source scope

```text
docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md
docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md
tests/test_autonomy_stage_b_durable_target_transfer_source_law.py
```

No fourth path is authorized for this correction. The test must fail if required owner/evidence fields
are deleted, Web is widened, cross-alias is unheld, command ID becomes caller-authored, or full-map
preservation is replaced by a one-root overlay.

---

## 6. Stage-B1 operator handoff

### Mission

Implement one source-only Executive capability that can:

1. persist revision-one assignment for a root whose current SessionTarget policy already owns the
   exact CEO alias; and
2. advance that same alias to a strictly newer admitted Codex RuntimeBinding generation after exact
   old-generation release and exact new-generation target ACK.

The unchanged Stage-A resolver must then make only the exact new binding action-authoritative while
stale/sister actors remain observer-only.

### Why it matters

This closes the durable seam between an already-proven current target and the machine’s one current
Sol action responsibility. It also makes lost transfer responses reconcilable without a second target
store. It does not yet solve cross-alias delegation or Web-Sol context rotation.

### Authority/document precedence

1. current outer Chairman directive to continue the Autonomy program;
2. action-time protected Skillpack and universal source law;
3. protected v2 design schema `mastermind.autonomy_stage_b_f0_contract.v2`;
4. current Runtime, SessionTarget, Wake ACK, RuntimeBinding projection, and Stage-A source;
5. this plan;
6. worker/PR/Slack prose as evidence only.

If protected source materially changes any owner contract, return one finite current-source decision
request before writing. Path-disjoint movement may be joined history-preservingly on the same carrier.

### Expected implementation paths

```text
control_plane/sol_action_target_transfer.py
control_plane/executive_runtime.py
tests/test_sol_action_target_transfer.py
tests/test_sol_action_target.py
tests/test_executive_runtime.py
```

A fresh path census may narrow the list. It may not add an authority/production path without an exact
same-carrier decision request.

### Explicit non-goals

- no target pointer table;
- no second SessionTargetRegistry;
- no second RuntimeBinding owner or registry;
- no provider process or session action;
- no Capacity selection or placement commitment;
- no Stage-B-authored target ACK or source resolution;
- no mutation of Job, Attempt, Worker, RuntimeBinding, Wake, or provider rows;
- no cross-alias responsibility transfer;
- no ChatGPT-Web succession;
- no automatic context rollover;
- no Control Room UI work;
- no Agent OS, Slack, or Linear lifecycle state;
- no deployment, installer, credential, or production target arming;
- no generic retry/failover policy;
- no common provider/worker wire change.

---

## 7. Complete supported journeys

### 7.1 Codex initial assignment

```text
root Job exists
-> current SessionTargetRegistry already maps root/ceo to exact Codex alias
-> Runtime current_harness_binding_source proves one current admitted generation
-> Wake ledger proves exact destination TARGET_ACKNOWLEDGED
-> derived Stage-B command enters one BEGIN IMMEDIATE transaction
-> revision 1 SOL_ACTION_TARGET_ASSIGNED event
-> full root/seat map projected without deletion
-> unchanged Stage-A resolver grants only exact actor binding
```

If root/CEO alias is absent, stop with `INITIAL_AUTHORITY_OWNER_UNRESOLVED`. The command cannot create
or choose an alias.

### 7.2 Codex same-alias succession

```text
valid current Stage-B assignment revision N
-> exact old process generation is ended
-> unique Runtime reconcile observation proves PROVEN_DEAD / RELEASED
-> current SessionTarget policy still owns the same alias
-> Runtime proves one strictly newer current admitted generation
-> Wake ledger proves exact new-generation TARGET_ACKNOWLEDGED
-> derived Stage-B command compares revision and previous target
-> revision N+1 SOL_ACTION_TARGET_TRANSFERRED event
-> full mapping projection
-> Stage A fences stale binding and grants exact successor
```

If release, ACK, current binding, policy, or history is missing/unknown/conflicting, append nothing.

### 7.3 Lost response

```text
one semantic command may commit
-> transport loses response
-> caller reuses same logical carrier and same semantic command
-> Runtime recomputes same command ID
-> command lookup occurs before mutable reads
-> exact existing event returns REPLAYED
-> no second event and no new revision
```

### 7.4 Held cross-alias journey

```text
request source alias A -> destination alias B
-> no accepted exact responsibility-transfer authority receipt owner
-> CROSS_ALIAS_AUTHORITY_OWNER_UNRESOLVED
-> zero event, zero provider effect, zero failover
```

### 7.5 Held Web journey

```text
request chatgpt-web target/succession
-> no accepted current RuntimeBinding writer and exact semantic ACK owner
-> UNSUPPORTED_REASONING_SURFACE / HELD_NOT_PROVEN
-> zero event
```

---

## 8. Data, null, time, and correction law

### Data

Persist only root/seat, assignment revision, stable target identity, command/authority/evidence
digests, exact Wake ID/ACK identity, and exact source-release event identity. Never persist native
handle, provider session, account label, token, email, path, model output, Slack identity, or private
transcript.

### Nulls

- previous target is null only at valid revision-zero initial assignment;
- `source_process_generation_id` and source release evidence are null only for initial assignment;
- destination Wake ID/ACK is never null for a supported append;
- missing root binding is unresolved authority, not a default alias;
- missing binding generation is unavailable, not zero;
- cross-alias authority source remains null and therefore held.

### Time

Wall-clock time does not rank or elect a target. Currentness comes from exact Runtime/Event/registry
facts on the transaction connection. Existing Event timestamps may be retained by Runtime but are not
command identity or transfer authority.

### Correction

Events are immutable. A mistaken/obsolete assignment is corrected only by another lawfully supported
next-revision event. Stage-B1 cannot use cross-alias mode for correction because that mode is held.
Where a correction requires another alias, the operation stops for the future authority-owner wave.

---

## 9. Deterministic versus model-generated work

Deterministic code owns:

- exact schema/key/type validation;
- canonical JSON and command derivation;
- command-first replay lookup;
- root Job and Stage-B history fold;
- policy digest and root/CEO alias resolution;
- current RuntimeBinding projection;
- Wake ACK lookup and causality validation;
- old-generation release validation;
- expected revision and previous-target comparison;
- one event append;
- full registry-map projection;
- Stage-A invocation;
- fixed secret-safe errors.

Model-generated text may propose work or help implement code. It cannot select an alias, create
currentness, claim release/ACK, author command ID, choose a revision, widen a held mode, retry an
ambiguous effect, or make a source-only merge production-proven.

---

## 10. Ordered implementation sequence

<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->
```text
1. PROTECT_STAGE_B0_R1_CORRECTION
2. RE_PIN_AND_COLLISION_FREEZE
3. RED_COMMAND_AUTHORITY_EVIDENCE_AND_FOLD_TESTS
4. IMPLEMENT_CLOSED_TYPES_AND_FULL_MAPPING_PROJECTOR
5. RED_RUNTIME_TRANSACTION_REPLAY_AND_RELEASE_TESTS
6. IMPLEMENT_EXISTING_RUNTIME_TRANSACTION_SEAM
7. RED_REAL_STAGE_A_CONSUMER_TESTS
8. INTEGRATE_CODEX_ONLY_INITIAL_AND_SAME_ALIAS_MODES
9. RUN_MUTATION_FORBIDDEN_PLANE_AND_ROW_INTEGRITY_PROOF
10. RUN_FOCUSED_ADJACENT_FULL_AND_SECURITY_GATES
11. PUBLISH_ONE_DRAFT_HOLD_CARRIER
12. INDEPENDENT_EXACT_HEAD_REVIEW
13. SOL_EXPECTED_HEAD_SOURCE_RELEASE
```
<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->

### Step 1 — Protect the correction

Do not commission or start Stage-B1 until protected master contains the exact v2 design and the
source-law suite is green with independent review. The protected v1 merge is not a substitute.

### Step 2 — Re-pin and collision freeze

Fresh-read protected master and same-SHA Skillpack. Inspect open PRs/branches/worktrees touching the
five expected paths. Reconcile any existing effect. Return a compact `PATH_FREEZE / STAGE-B1` and then
separate `START` only when the single-carrier boundary is clean.

### Step 3 — RED command/authority/evidence/fold tests

Require exact v2 command keys and reject caller command ID. Add discriminating failures for:

- missing root/CEO binding;
- caller alias mismatch;
- Web/cross-alias mode;
- malformed policy digest;
- missing/changed ACK identity;
- missing/changed release identity;
- malformed/gapped/branched assignment history;
- forbidden persisted fields;
- canonical key/list permutations.

### Step 4 — Closed types and full-map projector

Build one stdlib-only module with immutable command/event/snapshot types, exact parsing, canonical
bytes/digest, fold, and complete root-binding map merge. Do not write source owners.

### Step 5 — RED Runtime transaction/replay/release tests

Prove:

- command lookup precedes current-state reads;
- identical response-loss replay succeeds after later state movement;
- corrupt occupancy conflicts;
- different same-revision commands produce one append plus one revision mismatch;
- all Runtime/ACK/release reads use the one transaction connection;
- old-generation release must match exact previous target lineage.

### Step 6 — Existing Runtime seam

Add the smallest method in `executive_runtime.py`. Reuse `RuntimeStore.transaction`, event lookup,
Runtime Job/Event rows, `current_harness_binding_source`, and existing process-generation evidence.
Do not add another table, lock, lease, registry, cursor, cache, or transaction owner.

### Step 7 — Real Stage-A tests

Use `resolve_sol_action_target()` unchanged. Prove:

- before assignment, target is absent/observer-only;
- after valid assignment, exact actor is authoritative;
- after succession, old actor is observer-only and new actor authoritative;
- sister alias remains observer-only;
- missing/unknown/conflict snapshots never grant authority.

### Step 8 — Supported-mode integration

Implement only Codex initial assignment and same-alias succession. A branch containing cross-alias or
ChatGPT-Web behavior violates scope even if tests pass.

### Step 9 — Mutation and row-integrity proof

Kill mutations for command-first lookup, policy-owned alias, expected revision, previous target,
exact ACK, exact release, greater generation, full-map preservation, forbidden fields, and Stage-A
actor check. Snapshot all relevant Runtime/Wake rows before/after and prove Stage B changed only one
Runtime Event row.

### Step 10 — Repository/security gates

Run focused and adjacent tests, all feasible repository tests, compile, diff check, static ownership
scan, secret/private-field scan, and hosted security. A local environment gap is named honestly;
hosted CI remains required.

### Step 11 — One Draft/HOLD carrier

Use one operation, branch, and PR. Path-disjoint protected movement is joined history-preservingly.
Never replace the carrier because CI fails, review finds defects, or master moves.

### Step 12 — Independent review

The reviewer must verify original outcome and exact source law:

- are only supported modes implemented?
- can caller/model choose target or command ID?
- are owner/evidence reads exact and same-transaction?
- can projection delete another root or seat?
- can replay/race create a second event?
- are all adjacent owners untouched?
- is source-only work being misrepresented as production proof?

### Step 13 — Sol release

Expected-head merge only after exact current-base head, terminal required checks, independent PASS,
no blocking threads, exact path ceiling, final protected-head reread, and truthful capability state.

---

## 11. Acceptance tests

### Authority/evidence

- existing policy root/CEO alias required for initial assignment;
- current Stage-B assignment plus unchanged alias required for succession;
- cross-alias always refuses;
- Web always refuses;
- exact destination Runtime facts and Wake ACK required;
- exact source release required for succession;
- missing/duplicate/conflicting/effect-unknown evidence appends nothing.

### Replay/concurrency

- identical semantic retry returns same event;
- transport claimed-ID mismatch refuses;
- foreign event occupying derived ID conflicts;
- two different revision-N commands serialize to one append/one mismatch;
- no automatic revision rebase or alias failover.

### Projection

- unrelated root survives;
- root’s COO survives;
- root’s Chairman survives;
- only root/CEO alias changes;
- real Stage-A actor authority flips only to exact current binding.

### No-mutation/no-leak

- Job/Attempt/Worker/RuntimeBinding rows unchanged;
- Wake history unchanged;
- provider state unchanged;
- no native handle, account, provider session, path, token, Slack identity, or raw output in event,
  receipt, error, or test artifact.

### Truthful release

Maximum source claim:

```text
BUILT_NOT_PROVEN / CODEX_INITIAL_AND_SAME_ALIAS_SOURCE_ONLY / PRODUCTION_DISARMED
```

No test or merge may call cross-alias, Web continuity, automatic rotation, provider delivery, ACK,
source resolution, Control Room deployment, or complete Autonomy built/live.

---

## 12. Stop states

Return one finite decision packet without widening on:

```text
STAGE_B0_R1_NOT_PROTECTED
ACTIVE_WRITER_COLLISION
CURRENT_SOURCE_MOVED_MATERIALLY
RUNTIME_TRANSACTION_OWNER_UNRESOLVED
INITIAL_AUTHORITY_OWNER_UNRESOLVED
SUCCESSION_EVIDENCE_UNRESOLVED
CROSS_ALIAS_AUTHORITY_OWNER_UNRESOLVED
UNSUPPORTED_REASONING_SURFACE
ACK_EVIDENCE_OWNER_MOVED
SOURCE_RELEASE_EVIDENCE_OWNER_MOVED
NEW_TABLE_OR_MIGRATION_REQUIRED
SIXTH_AUTHORITY_PATH_REQUIRED
COMMON_WIRE_SCOPE_COLLISION
EFFECT_UNKNOWN
PROVIDER_ACTION_REQUIRED
```

Ordinary deterministic defects, failed tests, reviewer findings, and path-disjoint master movement are
repaired on the same carrier without Chairman intervention.

---

## 13. Production proof after source release

A separate canary operation—not Stage-B1—must use a disposable exact Codex target and prove:

```text
policy-owned root/CEO alias
-> one current admitted binding
-> exact Wake delivery and TARGET_ACKNOWLEDGED
-> initial Stage-B assignment
-> exact source generation release
-> new admitted same-alias generation
-> exact new-generation ACK
-> succession event
-> old actor fenced / new actor authoritative
-> one useful turn
-> restart and replay with zero duplicate event/provider write
-> truthful Control Room projection
```

The canary must disarm/rollback and preserve every negative receipt. It does not authorize cross-alias
or Web-Sol fleet rollout.

---

## 14. Continuation handoff

After this records carrier reaches immutable `RESULT / HOLD-FOR-SOL`, return:

- protected base, exact head/tree/parents;
- exact three paths and blobs;
- old-v1 to v2 decision delta;
- source-law test and mutation receipts;
- hosted repository/security check IDs;
- independent review identity/verdict;
- local/remote/production effects;
- explicit statement that Stage-B1 remains unstarted until expected-head protection;
- exact next operation only after protection.

After Stage-B1 source release, return the same evidence plus the remaining cross-alias, Web, and
production-canary gates. Green source is a checkpoint, not the finish line.
