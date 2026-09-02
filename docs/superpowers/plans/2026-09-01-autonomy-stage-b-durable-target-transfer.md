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
writes, or Chairman message shuttling. Current protected owners support neither Codex initial assignment
nor same-alias generation succession: the first code wave is a separately commissioned root/CEO
assignment-owner prerequisite in the existing `SessionTargetRegistry` ownership path.

Cross-alias responsibility transfer remains held until an exact accepted authority receipt owner
exists. ChatGPT-Web remains held until one accepted current RuntimeBinding writer and exact semantic
ACK owner exist.

---

## 2. Observable records mission

Protect exactly one correction where:

- every mode whose current authority owner is absent is explicitly held;
- every evidence requirement names an owner, lookup, aggregate/event, command law, schema/typed shape,
  identity closure, and effect-known rule;
- command identity is derived and caller-inaccessible;
- same-revision races produce one append and one revision refusal, not a fictional same-ID conflict;
- Stage-B projection preserves all unrelated roots and sibling seats;
- current source supports no Stage-B1 reasoning surface;
- Codex, cross-alias, and ChatGPT-Web journeys are explicit held states;
- Stage-B1 cannot start until both this correction and the separately commissioned owner prerequisite
  are protected.

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
  "stage_b1_state": "HELD_UNTIL_OWNER_PREREQUISITE_PROTECTED",
  "authorized_modes_after_gate": [],
  "held_modes": [
    "INITIAL_ASSIGNMENT",
    "SAME_ALIAS_GENERATION_SUCCESSION",
    "CROSS_ALIAS_RESPONSIBILITY_TRANSFER"
  ],
  "supported_reasoning_surfaces": [],
  "held_reasoning_surfaces": [
    "codex",
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

## 6. First implementation wave — separate root/CEO assignment-owner prerequisite

### Mission

After this records correction is protected, commission exactly one existing-system extension that can:

1. create an exact durable root/CEO alias assignment receipt/map; and
2. create a compatible Codex CEO SessionTarget policy through the existing `SessionTargetRegistry`
   ownership path.

It must use no second registry or control plane, and it must expose an action-time lookup and independent
receipt/map fingerprint that a later Stage-B1 transaction can consume. This records carrier neither starts
that wave nor selects its code/config paths.

### Why it matters

This closes the missing authority seam before a transaction can safely materialize it. The preserved
Stage-B1 command/replay/evidence/full-map architecture becomes reachable only after the predecessor is
protected. Cross-alias delegation and Web-Sol context rotation remain separately held.

### Authority/document precedence

1. current outer Chairman directive to continue the Autonomy program;
2. action-time protected Skillpack and universal source law;
3. protected v2 design schema `mastermind.autonomy_stage_b_f0_contract.v2`;
4. current Runtime, SessionTarget, Wake ACK, RuntimeBinding projection, and Stage-A source;
5. this plan;
6. worker/PR/Slack prose as evidence only.

If protected source materially changes any owner contract, return one finite current-source decision
request before writing. Path-disjoint movement may be joined history-preservingly on the same carrier.

### Required bounded owner outcome

The separately commissioned extension must prove all of the following before another Stage-B1 commission:

- it owns a durable root/CEO assignment receipt/map, not a test or caller overlay;
- the exact receipt/map has a distinct action-time fingerprint, so `policy_digest()` alone cannot attest
  a root-to-alias choice;
- it creates one compatible Codex CEO SessionTarget policy in the existing registry;
- it has a real producer and consumer, with no second registry, RuntimeBinding owner, or authority map.

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

## 7. Future Stage-B1 journeys — unreachable until the owner prerequisite protects

The following preserve the desired future Stage-B1 behavior. They are not current supported journeys and
must not be implemented on this records carrier.

### 7.1 Future Codex initial assignment

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

Until the owner prerequisite protects, stop with `INITIAL_AUTHORITY_OWNER_UNRESOLVED` before any command.
The later command cannot create or choose an alias.

### 7.2 Future Codex same-alias succession

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

Until valid protected initial assignment can exist, succession is held. Thereafter, missing/unknown/
conflicting release, ACK, current binding, policy, or history appends nothing.

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

## 10. Ordered next operations

<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->
```text
1. PROTECT_STAGE_B0_R1_CORRECTION
2. RE_PIN_AND_COLLISION_FREEZE
3. HOLD_STAGE_B1_FOR_SEPARATE_SESSION_TARGETS_ROOT_CEO_ASSIGNMENT_OWNER_COMMISSION
4. PROTECT_DURABLE_ROOT_CEO_RECEIPT_MAP_AND_COMPATIBLE_CODEX_CEO_POLICY
5. RE_PIN_AND_SEPARATELY_COMMISSION_FUTURE_STAGE_B1_TRANSACTION_WORK
```
<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->

### Step 1 — Protect the correction

Do not commission or start the owner prerequisite until protected master contains the exact corrected v2
design and the source-law suite is green with independent review. The protected v1 merge is not a
substitute.

### Step 2 — Re-pin and collision freeze

Fresh-read protected master and same-SHA Skillpack. Inspect open PRs/branches/worktrees touching the
owner path. Reconcile any existing effect. Return a compact `PATH_FREEZE` and then separate `START` only
when the single-carrier boundary is clean.

### Step 3 — Hold Stage-B1 and commission the missing owner

Do not add Stage-B1 command, event, Runtime, provider, or target code on this carrier. Separately commission
one existing `SessionTargetRegistry` ownership extension that creates:

- an exact durable root/CEO alias assignment receipt/map; and
- one compatible Codex CEO SessionTarget policy;
- an action-time lookup and separate receipt/map fingerprint;
- real producer/consumer evidence, without a second registry or control plane.

### Step 4 — Protect the owner prerequisite

The owner extension must receive its own source, tests, review, and protected-head proof. A test-only or
caller-created `with_root_job_bindings()` overlay, `policy_digest()` absence, RuntimeBinding, Wake ACK,
provider fact, placement result, Slack prose, or Stage-B event is not a substitute.

### Step 5 — Recommission future Stage-B1 only after the prerequisite protects

Only then may a fresh, separately scoped Stage-B1 commission use the preserved command/replay/evidence/
full-map/no-duplicate-registry law. That later commission begins again with RED discriminators for
command authority, replay, exact Runtime/Wake evidence, Stage-A consumer behavior, row integrity, and
all held modes. It remains Codex-only only if the prerequisite has proved the compatible Codex CEO policy;
cross-alias and ChatGPT-Web remain held.

---

## 11. Acceptance tests

### Authority/evidence

- current empty/test-only root bindings, digest omission, absent Codex CEO target, and caller overlay all
  hold initial assignment;
- same-alias succession remains held until a valid protected initial-assignment capability can exist;
- cross-alias always refuses;
- Web always refuses;
- the separately commissioned prerequisite must create the receipt/map and compatible Codex CEO policy
  before a future Stage-B1 transaction is considered.

### Future replay/concurrency after the prerequisite

- identical semantic retry returns same event;
- transport claimed-ID mismatch refuses;
- foreign event occupying derived ID conflicts;
- two different revision-N commands serialize to one append/one mismatch;
- no automatic revision rebase or alias failover.

### Future projection after the prerequisite

- unrelated root survives;
- root’s COO survives;
- root’s Chairman survives;
- only root/CEO alias changes;
- real Stage-A actor authority flips only to exact current binding.

### Future no-mutation/no-leak proof

- Job/Attempt/Worker/RuntimeBinding rows unchanged;
- Wake history unchanged;
- provider state unchanged;
- no native handle, account, provider session, path, token, Slack identity, or raw output in event,
  receipt, error, or test artifact.

### Truthful release

Maximum source claim:

```text
RECORDS_ONLY / OWNER_PREREQUISITE_REQUIRED / STAGE_B1_UNSTARTED / PRODUCTION_DISARMED
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

## 13. Production proof after future owner and Stage-B source releases

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
- explicit statement that Stage-B1 remains unstarted until the separately commissioned owner prerequisite
  protects an exact durable receipt/map and compatible Codex CEO policy;
- exact next operation only after this records correction protects.

After Stage-B1 source release, return the same evidence plus the remaining cross-alias, Web, and
production-canary gates. Green source is a checkpoint, not the finish line.
