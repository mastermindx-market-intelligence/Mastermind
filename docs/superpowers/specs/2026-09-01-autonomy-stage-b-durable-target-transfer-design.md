# Autonomy Stage B — Durable Sol Action-Target Assignment and Transfer

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `autonomy-stage-b-durable-target-transfer-f0-20260901-sol-001`  
**Records wave:** `STAGE-B0`  
**First implementation wave:** `STAGE-B1`  
**Protected source and Skillpack basis:** `mastermindx-market-intelligence/Mastermind@c6af57d1ce96ed3f5ca8237099f4a5ecfa01d3cf`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

## 0. Executive decision

Mastermind needs one durable, correction-safe answer to this question:

> For one canonical root Executive responsibility, which exact Sol target and RuntimeBinding
> generation is currently action-authoritative?

Stage A already answers the question from an exact `root_job_id`, a `SessionTargetRegistry`, a
complete `RuntimeBindingSnapshot`, and an actor binding. It deliberately owns no persistence or
transfer. The missing Stage-B capability is therefore not another target registry, current-target
row, RuntimeBinding table, session manager, or scheduler. It is one immutable command-bound event
fold inside the existing Executive Runtime transaction and event owners.

The accepted architecture is:

```text
existing root Job responsibility
+ existing logical SessionTarget alias
+ existing admitted RuntimeBinding generation
+ existing terminal/release/materialization/ACK evidence
+ current Chairman/Executive authority source
-> one command-first BEGIN IMMEDIATE transaction
-> zero or one immutable root-job target-assignment event
-> deterministic event fold
-> existing Stage-A resolver input
```

The event fold may establish an initial assignment, move the same logical alias to a successor
RuntimeBinding generation, or transfer the responsibility to another lawful alias. It never creates,
mutates, adopts, resumes, starts, interrupts, or destroys a provider session. It never edits a
RuntimeBinding row. It never writes ACK, source resolution, Job, Attempt, Worker, or placement state.

A merge of this records wave makes only the architecture durable. It does not make Stage B built,
installed, armed, or production-proven.

---

## 1. Canonical owners and source archaeology

| Fact or effect | Existing canonical owner | Stage-B use |
|---|---|---|
| root responsibility identity and lifecycle | Executive OS Job/Attempt/Worker/Event | bind every assignment to one exact `root_job_id`; do not create another responsibility |
| immutable transaction and event append | `control_plane.executive_runtime.RuntimeStore` | reuse `transaction()`, `get_event_by_command_id()`, and `append_event()` |
| admitted current OHF writer facts | `Runtime.current_harness_binding_source()` | read source/destination binding facts on the same Runtime transaction connection |
| logical target alias and seat/surface contract | `control_plane.session_targets.SessionTargetRegistry` | validate the alias and project the folded root binding with `with_root_job_bindings()` |
| rotating current binding identity | RuntimeBinding / Runtime projection | compare exact binding ID and generation; never mutate or copy the native handle into transfer state |
| action-authoritative target resolution | `control_plane.sol_action_target.resolve_sol_action_target()` | remain the real downstream consumer; its public resolution signature and election law stay unchanged |
| target materialization | existing/future accepted provider materialization owner | Stage B consumes a canonical event receipt; it does not start the provider |
| target consumption/readiness | ACK1 / exact target acknowledgement owner | Stage B consumes a canonical ACK event; it does not author acknowledgement |
| predecessor terminal/release state | Executive terminal-return and Runtime writer owners | Stage B consumes exact event evidence before succession/transfer |
| worker/account capacity and placement | Capacity Fabric / Model Router / Executive claim owner | Stage B consumes already-selected/materialized targets; it does not select capacity |
| organizational continuity | Agent OS | record the ruling and continuation; never become execution truth |
| code and proof | GitHub | exact implementation/evidence truth |
| transport visibility | Slack | no lifecycle or target authority |

Current source facts that constrain this design:

1. `control_plane/sol_action_target.py` is deterministic and storeless. It refuses missing roots,
   unknown binding evidence, multiple bindings for one alias, surface mismatch, and sister-session
   election. A constructed resolution is evidence, not an authority token.
2. `control_plane/session_targets.py` owns aliases and root-job binding projection, but not durable
   target-transfer effects. Checked-in root bindings may be empty and must not become a new mutable
   config-write workflow.
3. `control_plane/runtime_binding_projection.py` accepts an already-open Runtime connection and
   projects exact current binding facts without persistence.
4. `control_plane/executive_runtime.py` already provides `BEGIN IMMEDIATE`, immutable events, unique
   command IDs, in-transaction command replay lookup, causal aggregate sequencing, and exact admitted
   current-writer facts.
5. `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md` requires successor materialization, readiness,
   CAS/ABA-safe succession, no newest-tab election, and no blind duplicate creation.
6. `docs/superpowers/specs/2026-08-29-organizational-continuity-sol-action-authority-amendment.md`
   requires exactly one action-authoritative Sol edge and rejects Slack/model/title/recency election.

These owners are sufficient. Creating a target pointer table would duplicate the event owner and
make correction/replay harder, not safer.

---

## 2. Machine-readable architecture freeze

<!-- STAGE_B_F0_CONTRACT_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b_f0_contract.v1",
  "records_wave": "STAGE-B0",
  "records_state_after_merge": "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED",
  "first_implementation_wave": "STAGE-B1",
  "command_schema": "mastermind.sol_action_target_command.v1",
  "event_schema": "mastermind.sol_action_target_event.v1",
  "snapshot_schema": "mastermind.sol_action_target_snapshot.v1",
  "event_aggregate_type": "job",
  "event_types": [
    "SOL_ACTION_TARGET_ASSIGNED",
    "SOL_ACTION_TARGET_TRANSFERRED"
  ],
  "transfer_modes": [
    "INITIAL_ASSIGNMENT",
    "SAME_ALIAS_GENERATION_SUCCESSION",
    "CROSS_ALIAS_RESPONSIBILITY_TRANSFER"
  ],
  "command_id_derivation": "SOL-TARGET-<first-32-hex-of-sha256-canonical-command-semantics>",
  "command_reconciliation_order": "BEFORE_MUTABLE_STATE_READ",
  "transaction_owner": "control_plane.executive_runtime.RuntimeStore.transaction",
  "event_append_owner": "control_plane.executive_runtime.RuntimeStore.append_event",
  "replay_lookup_owner": "control_plane.executive_runtime.RuntimeStore.get_event_by_command_id",
  "binding_read_owner": "control_plane.executive_runtime.Runtime.current_harness_binding_source",
  "logical_target_owner": "control_plane.session_targets.SessionTargetRegistry.root_job_bindings",
  "logical_target_projection": "control_plane.session_targets.SessionTargetRegistry.with_root_job_bindings",
  "stage_a_consumer": "control_plane.sol_action_target.resolve_sol_action_target",
  "persisted_target_identity_fields": [
    "attempt_id",
    "binding_generation",
    "binding_id",
    "reasoning_surface",
    "session_alias",
    "session_epoch_id"
  ],
  "forbidden_persisted_target_fields": [
    "account_label",
    "native_handle",
    "provider_session_id",
    "raw_model_output",
    "slack_principal"
  ],
  "required_evidence_by_mode": {
    "INITIAL_ASSIGNMENT": [
      "authority_source_ref",
      "destination_materialization_event_command_id",
      "destination_ack_event_command_id"
    ],
    "SAME_ALIAS_GENERATION_SUCCESSION": [
      "authority_source_ref",
      "source_release_event_command_id",
      "destination_materialization_event_command_id",
      "destination_ack_event_command_id"
    ],
    "CROSS_ALIAS_RESPONSIBILITY_TRANSFER": [
      "authority_source_ref",
      "source_terminal_event_command_id",
      "source_release_event_command_id",
      "destination_materialization_event_command_id",
      "destination_ack_event_command_id"
    ]
  },
  "new_tables": [],
  "new_migrations": [],
  "new_registries": [],
  "runtime_binding_rows_mutated": false,
  "job_attempt_worker_rows_mutated": false,
  "provider_calls_in_transaction": false,
  "slack_calls_in_transaction": false,
  "ack_written_by_stage_b": false,
  "source_resolution_written_by_stage_b": false,
  "stage_a_resolver_signature_changed": false,
  "production_armed_in_stage_b1": false
}
```
<!-- STAGE_B_F0_CONTRACT_END -->

The JSON block is normative. Prose may explain it but may not silently widen it.

---

## 3. Durable model: immutable root-job assignment history

### 3.1 Aggregate

Every target assignment event is appended to:

```text
aggregate_type = "job"
aggregate_id   = <exact root_job_id>
```

The existing root Job remains the responsibility identity. No `responsibility_id` alias, target
record ID, transfer row ID, or new aggregate is introduced.

The event stream may contain many unrelated Job events. Stage-B assignment revision is therefore
not equal to the raw aggregate sequence. The projector selects only the two Stage-B event types and
requires their payload `assignment_revision` values to be exactly contiguous from one.

### 3.2 Event types

`SOL_ACTION_TARGET_ASSIGNED` establishes revision 1 when no prior Stage-B assignment event exists.

`SOL_ACTION_TARGET_TRANSFERRED` establishes revision N+1 from exactly one current revision N.

Events are immutable. A correction is another authorized transfer at the next revision; it is never
an update, delete, replacement row, force rewrite, or history erasure.

### 3.3 Event payload

Every persisted event uses `mastermind.sol_action_target_event.v1` and contains only deterministic,
secret-safe data:

```text
schema
mode
root_job_id
target_seat = "ceo"
assignment_revision
command_id
command_fingerprint
authority_source_ref
authority_fingerprint
previous_target | null
current_target
source_terminal_event_command_id | null
source_release_event_command_id | null
destination_materialization_event_command_id
destination_ack_event_command_id
```

`previous_target` and `current_target` contain exactly:

```text
session_alias
binding_id
binding_generation
attempt_id
session_epoch_id
reasoning_surface
```

The persisted event does not copy provider-native handles, provider session IDs, account labels,
emails, filesystem paths, raw model output, Slack principals, tokens, credentials, or transcript
content. Existing owner events remain the detailed evidence; Stage-B stores their stable command IDs.

### 3.4 Command versus observed fact

The caller supplies expected semantic identity and evidence references. Those fields are comparison
claims, not privileged facts. Inside the Runtime transaction, deterministic code derives the actual
current destination from `current_harness_binding_source()` plus the canonical SessionTarget alias,
then persists the observed stable identity only after exact comparison.

A model, Slack message, account number, title, newest timestamp, remembered quota, or visible tab may
never choose the destination or fill a missing binding field.

### 3.5 Stable command identity

The implementation canonicalizes all command semantics except `command_id`, hashes the canonical
bytes, and derives:

```text
SOL-TARGET-<first 32 lowercase hex characters of SHA-256>
```

An identical retry derives the identical command ID. The Runtime transaction looks up that command
before reading mutable assignment/binding state.

- existing event + identical canonical semantics -> return the existing event with `inserted=false`;
- existing event + changed canonical semantics -> `COMMAND_REPLAY_CONFLICT`;
- no event -> continue the one transaction;
- unavailable/ambiguous lookup -> fail closed; never submit another carrier.

This ordering lets a caller reconcile a lost response even if the source session later terminates or
the current target advances again.

---

## 4. Transfer modes

### 4.1 `INITIAL_ASSIGNMENT`

Preconditions:

- no Stage-B assignment event exists for the root Job;
- `expected_assignment_revision == 0`;
- `previous_target == null`;
- destination alias is a valid CEO target in the current `SessionTargetRegistry`;
- if a static/current root binding already exists, it equals the destination alias;
- otherwise the current authority source explicitly binds this root Job to the destination alias;
- destination materialization and exact target ACK events exist and match the destination;
- destination RuntimeBinding is current, exact, and unique.

Effect: append `SOL_ACTION_TARGET_ASSIGNED` at revision 1.

The event does not provision or wake the target. It records only that an already-materialized,
already-acknowledged target is now action-authoritative for this responsibility.

### 4.2 `SAME_ALIAS_GENERATION_SUCCESSION`

Use for context/session generation rotation while the logical alias remains constant.

Preconditions:

- current folded assignment matches `previous_target` exactly;
- source and destination `session_alias` are equal;
- destination `binding_generation` is strictly greater than the previous generation;
- an exact source release/fence event proves the previous binding is no longer the current writer;
- destination materialization and ACK events match the destination;
- the current Runtime transaction resolves exactly the destination binding for the alias;
- no second current binding for the alias exists in the complete snapshot;
- no source or destination effect is unknown.

Effect: append `SOL_ACTION_TARGET_TRANSFERRED` at revision N+1.

Stage B does not mark the old binding non-current. That must already have occurred through the
existing Runtime writer/generation owner. “Newest generation wins” is forbidden; exact release plus
exact destination evidence is required.

### 4.3 `CROSS_ALIAS_RESPONSIBILITY_TRANSFER`

Use when the root responsibility moves to a different lawful logical target.

Preconditions:

- current folded assignment matches `previous_target` exactly;
- source and destination aliases differ;
- exact source terminal-return and source release/fence events exist and match the prior target;
- destination alias is a valid CEO target under current registry policy;
- destination materialization and ACK events exist and match the destination;
- the current Runtime transaction resolves exactly the destination binding;
- current Chairman/Executive authority explicitly permits the transfer;
- no effect is unknown.

Effect: append `SOL_ACTION_TARGET_TRANSFERRED` at revision N+1 and project the root Job’s CEO alias to
the destination.

Capacity preference, provider availability, account family, or Slack presence cannot independently
trigger this mode.

---

## 5. One transaction, exact ordering

The implementation transaction is closed and ordered:

```text
1. derive canonical command semantics and stable command_id
2. RuntimeStore.transaction() -> BEGIN IMMEDIATE
3. get_event_by_command_id(command_id, connection=tx)
4. identical existing event -> replay return; changed event -> conflict
5. verify root Job exists and is an eligible current responsibility
6. fold all Stage-B assignment events for the root Job
7. reject malformed/gapped/branched/duplicate revision history
8. compare expected_assignment_revision and exact previous target
9. validate current authority source and transfer mode
10. read destination admitted binding facts using current_harness_binding_source(..., connection=tx)
11. construct the exact RuntimeBinding through the existing projection/formula owner
12. validate evidence event command IDs and their bound identities
13. recheck all mode-specific source/destination conditions
14. append exactly one immutable Stage-B event with RuntimeStore.append_event(..., connection=tx)
15. COMMIT
16. return inserted event or reconcile by command_id after any response ambiguity
```

There is no provider, Slack, GitHub, Agent OS, Capacity, browser, filesystem, subprocess, network,
watcher, ACK, source-resolution, or deployment call inside the transaction.

Two concurrent transfers for the same expected revision serialize under `BEGIN IMMEDIATE`. At most
one can append revision N+1. The other observes the changed fold and returns
`EXPECTED_REVISION_MISMATCH`; it does not silently rebase itself onto N+1.

---

## 6. Deterministic fold and existing Stage-A consumer

The Stage-B snapshot projector reads the immutable event stream and returns:

```text
schema = mastermind.sol_action_target_snapshot.v1
root_job_id
target_seat = ceo
assignment_revision
session_alias
binding_id
binding_generation
attempt_id
session_epoch_id
reasoning_surface
assignment_event_id
assignment_event_command_id
history_digest
state = CURRENT | ABSENT | CONFLICT | UNKNOWN
reason
```

Projection rules:

- no assignment events -> `ABSENT`;
- one valid contiguous history -> `CURRENT` at the final event;
- duplicate revision, revision gap, wrong previous target, changed root, unsupported mode, or semantic
  branch -> `CONFLICT`;
- unreadable/incomplete source -> `UNKNOWN`;
- event order is deterministic by assignment revision and stable event identity, never newest wall
  clock time.

For a `CURRENT` snapshot, the adapter:

1. creates a root binding overlay with `SessionTargetRegistry.with_root_job_bindings()`;
2. obtains a complete current RuntimeBinding snapshot from the existing Runtime owner;
3. calls `resolve_sol_action_target(root_job_id, registry, binding_snapshot, actor_binding)` unchanged.

The real machine consumer is therefore Stage A. A successful Stage-B event is not itself an
authority token. Stage A still verifies that the actor matches the exact current binding.

---

## 7. Complete journeys

### 7.1 Initial action target

```text
root Executive Job exists
-> target materializer creates exact provider surface under its own owner
-> Runtime commits exact current binding
-> ACK1 proves target consumption/readiness
-> Stage-B INITIAL_ASSIGNMENT command
-> one immutable assignment event
-> Stage-B projector overlays root binding
-> Stage-A resolver grants action authority only to the exact current binding
```

### 7.2 Web-Sol context rollover

```text
current target reaches accepted context boundary
-> terminal/continuity packet and exact release/fence evidence
-> fresh Capacity selection under Capacity owner
-> successor materialization under provider owner
-> successor RuntimeBinding
-> successor ACK1
-> SAME_ALIAS_GENERATION_SUCCESSION
-> Stage-A resolves only successor generation
-> predecessor cleanup under its existing owner
```

If the successor is not materialized or ACKed, the old target remains current and Stage B returns a
wait/refusal state. It never transfers first and hopes the successor becomes usable later.

### 7.3 Cross-alias transfer

```text
source target terminal-return accepted
-> exact source release/fence event
-> authorized destination already materialized and ACKed
-> CROSS_ALIAS_RESPONSIBILITY_TRANSFER
-> root binding projects to destination alias
-> sister/source sessions become observer-only
```

### 7.4 Lost response

```text
client submits one Stage-B command
-> Runtime may commit
-> client loses response
-> same semantic command derives same command_id
-> command lookup occurs before current-state validation
-> existing event returned inserted=false
-> zero second transfer event
```

### 7.5 Correction

```text
current assignment later proven wrong or obsolete
-> do not edit/delete prior event
-> reconcile current revision and evidence
-> issue a new authorized transfer at revision N+1
-> immutable history explains both states
```

---

## 8. Failure vocabulary

The implementation must preserve at least these typed outcomes or stricter accepted equivalents:

```text
APPLIED
REPLAYED
NO_ASSIGNMENT
COMMAND_REPLAY_CONFLICT
ASSIGNMENT_HISTORY_CONFLICT
EXPECTED_REVISION_MISMATCH
INITIAL_BINDING_CONFLICT
SOURCE_TARGET_MISMATCH
SOURCE_TERMINAL_MISSING
SOURCE_RELEASE_MISSING
DESTINATION_TARGET_INVALID
DESTINATION_RUNTIME_UNAVAILABLE
DESTINATION_RUNTIME_CONFLICT
DESTINATION_MATERIALIZATION_MISSING
DESTINATION_ACK_MISSING
AUTHORITY_SOURCE_NOT_CURRENT
AUTHORITY_SCOPE_REFUSED
EFFECT_UNKNOWN_RECONCILE_FIRST
UNSUPPORTED_TRANSFER_MODE
RUNTIME_TRANSACTION_UNAVAILABLE
```

Failure behavior:

- missing destination materialization -> no event and visible wait;
- missing destination ACK -> no event and visible wait;
- source terminal/release missing where required -> no event;
- stale authority -> no event;
- expected revision mismatch -> no automatic retry at the new revision;
- multiple current RuntimeBindings -> conflict, never “highest generation wins”;
- effect-unknown source/destination/provider state -> no event and no failover;
- malformed prior history -> conflict, never repair by skipping an event;
- transaction response ambiguity -> command lookup on the same logical carrier;
- unknown exception text -> fixed typed error; no secret/path/provider leakage.

---

## 9. Security, rights, and authority boundaries

- Persist stable opaque identity only; never raw provider or model output.
- Caller/model values are comparison claims until re-derived from current canonical owners.
- Runtime binding IDs and generations do not grant authority without root responsibility, current
  alias, actor match, and current authority source.
- A Slack principal is never a RuntimeBinding.
- A provider account may host multiple sessions; account identity alone never selects one.
- No cross-account/session failover after a started or effect-unknown operation.
- No credential, token, auth file, home path, environment variable, browser state, or transcript is
  read or written by Stage B.
- A Stage-B event may not mark target ACK, source resolution, production deployment, or provider
  cleanup complete.
- Production activation requires a separately reviewed adapter/service/canary wave.

---

## 10. Stage-B1 expected implementation surface

The first implementation carrier is one bounded Mastermind PR. Current-source archaeology may narrow
implementation detail, but widening requires a finite Sol decision request before edit.

<!-- STAGE_B1_EXPECTED_PATHS_BEGIN -->
```text
control_plane/sol_action_target_transfer.py
control_plane/executive_runtime.py
tests/test_sol_action_target_transfer.py
tests/test_sol_action_target.py
tests/test_executive_runtime.py
```
<!-- STAGE_B1_EXPECTED_PATHS_END -->

Expected responsibilities:

- `sol_action_target_transfer.py`: closed command/event/snapshot types, canonicalization, fold,
  projection adapter, and fixed error vocabulary;
- `executive_runtime.py`: the smallest transaction-composed read/compare/append method over existing
  RuntimeStore and binding facts;
- tests: source/event hostile matrix, concurrency/replay, zero-row-mutation proof, and real Stage-A
  consumer integration.

Protected no-edit unless a current collision ruling explicitly changes the freeze:

```text
control_plane/session_targets.py
control_plane/runtime_binding_projection.py
control_plane/operator_harness_contract.py
control_plane/wake_ack_ingress.py
control_plane/wake_ledger.py
control_plane/wake_persist.py
all provider adapters and materializers
all Capacity / Model Router / Worker Browser paths
all Agent OS / Linear / Slack transport paths
all deployment / installer / credential paths
```

If implementation requires a new table, migration, target registry, RuntimeBinding owner, provider
call, common worker-wire change, or sixth production/authority path, stop with a finite decision
request instead of silently widening.

---

## 11. Required discriminating proof

Stage-B1 must prove:

1. initial assignment from revision zero;
2. same-alias generation N to N+1 only after exact release and destination ACK;
3. cross-alias transfer only after source terminal/release and destination ACK;
4. identical replay returns one existing event;
5. changed semantics under the same command identity conflict;
6. response-loss replay succeeds after later target movement without old-writer liveness;
7. two concurrent revision-N transfers produce one event and one revision conflict;
8. stale expected revision refuses;
9. static root binding mismatch refuses initial assignment;
10. missing/unknown destination RuntimeBinding refuses;
11. two bindings for one alias conflict; no highest-generation election;
12. source release missing refuses succession;
13. source terminal missing refuses cross-alias transfer;
14. destination materialization or ACK missing refuses;
15. stale/unknown authority source refuses;
16. effect-unknown evidence refuses and produces no retry/failover;
17. prior history gaps, duplicate revisions, or wrong previous-target links conflict;
18. persisted event omits every forbidden target field;
19. Job, Attempt, Worker, RuntimeBinding, ACK, source-resolution and provider state are byte/row
    unchanged by the transfer transaction;
20. real Stage-A resolver grants authority to the exact destination and keeps source/sister actors
    observer-only;
21. command/event/key ordering permutations produce identical canonical digest and result;
22. removing command-first replay, same-transaction binding read, expected-revision compare, ACK gate,
    release gate, or Stage-A actor check makes the intended test fail.

Hosted repository CI, CodeQL/security, exact diff, and independent exact-head review are required.
Production proof is not part of Stage-B1 unless a later explicit source law adds a bounded canary.

---

## 12. Completion and stop law

### STAGE-B0

Complete only when this design, its implementation plan, and source-law tests merge at an exact
reviewed current-base head. Result:

```text
STAGE-B0 = SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED
```

### STAGE-B1

May start only after STAGE-B0 is protected and a fresh five-path collision census is clean. It stops
at one immutable current-base Draft/HOLD candidate:

```text
BUILT_NOT_PROVEN / TRANSFER_SOURCE_PRODUCTION_DISARMED
```

No provider creation, live context rotation, live responsibility transfer, deployment, broad route
arming, fleet claim, or final Autonomy acceptance is authorized by source protection.

### Program completion

The broader program requires a real successor target journey:

```text
materialize successor
-> commit exact RuntimeBinding
-> successor ACK1
-> Stage-B transfer
-> Stage-A exact action-authority resolution
-> bounded useful turn
-> predecessor cleanup
-> restart/replay proof
-> Control Room visibility
```

Until that real path is proven, Stage B is not `PROVEN_LIVE`.
