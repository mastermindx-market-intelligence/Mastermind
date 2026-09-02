# Autonomy Stage B — Durable Sol Action-Target Assignment and Transfer

**Original date:** 2026-09-01  
**Protected-source correction:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Original operation:** `autonomy-stage-b-durable-target-transfer-f0-20260901-sol-001`  
**Correction operation:** `autonomy-stage-b0-protected-source-correction-r1-20260902-sol-001`  
**Correction basis:** `mastermindx-market-intelligence/Mastermind@162af533a4bcf380125895d225b6962987c3c582`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED_SOURCE_CORRECTION_REQUIRED`

## 0. Protected-source incident and controlling correction

The original Stage-B0 v1 records were merged before a later exact-head adversarial review reached its
final verdict. That post-merge review found five implementation-blocking defects:

1. `authority_source_ref` named no exact accepted authority owner or fingerprint law;
2. materialization, acknowledgement, release, and terminal evidence were represented as generic
   caller-supplied command IDs instead of closed owner contracts;
3. the records implied ChatGPT-Web support although current protected RuntimeBinding projection
   accepts only `openai-codex -> codex`;
4. the root-binding “overlay” prose ignored that `with_root_job_bindings` replaces the complete
   mapping and could erase unrelated roots or sibling seats; and
5. the replay prose described changed semantics under one fully derived command identity, which is
   not a normal possible wire case.

The protected v1 source law must not be implemented. Its merge proves only that records were durable;
it does not make unsafe or underspecified instructions authoritative. This correction supersedes v1
for every Stage-B implementation decision. Where v2 is narrower, v2 wins. Where v2 holds a mode, a
worker must stop rather than infer the missing owner from old prose, Slack, a model, a RuntimeBinding,
or a convenient provider state.

The repaired architecture preserves the full program outcome while narrowing the first source wave to
what current protected owners can actually prove:

```text
STAGE-B1
  Codex INITIAL_ASSIGNMENT only when an existing root/ceo SessionTarget binding already owns alias choice
  Codex SAME_ALIAS_GENERATION_SUCCESSION only after a valid current Stage-B assignment
  no cross-alias transfer
  no ChatGPT-Web succession
  no provider or deployment action

later separately frozen waves
  accepted cross-alias authority receipt owner
  accepted ChatGPT-Web RuntimeBinding writer and semantic ACK owner
  real target-transfer canary and Control Room projection
```

This is not vision shrinkage. It is the no-false-authority boundary required to reach the full
unattended responsibility loop without creating a second control plane.

---

## 1. Outcome and owner model

For one canonical root Executive Job, Mastermind needs a durable, correction-safe answer to:

> Which exact logical Sol alias and RuntimeBinding generation is currently action-authoritative for
> this root responsibility?

Stage A already resolves action authority from an exact root, complete target policy, complete
RuntimeBinding evidence, and an actor binding. Stage B adds only an immutable assignment history and
its deterministic fold. It does not become a provider session manager, Capacity selector,
RuntimeBinding registry, Wake ledger, or organizational authority store.

The one-system composition is:

```text
Executive Runtime root Job
+ SessionTargetRegistry policy-owned root/ceo alias
+ Runtime current-writer facts
+ exact Wake TARGET_ACKNOWLEDGED evidence
+ exact source-generation release evidence when succession is requested
+ current Stage-B assignment history
-> one command-derived BEGIN IMMEDIATE transaction
-> zero or one immutable root-Job Stage-B event
-> deterministic full-registry projection
-> unchanged Stage-A action-target resolver
```

Canonical ownership remains:

| Fact or effect | Existing owner | Stage-B use |
|---|---|---|
| root responsibility and lifecycle | Executive Runtime Job/Attempt/Worker/Event | exact root identity; no second responsibility |
| transaction, event lookup, append | `control_plane.executive_runtime.RuntimeStore` | one `BEGIN IMMEDIATE` command-first transaction |
| current admitted Codex writer | `Runtime.current_harness_binding_source` through `runtime_binding_projection` | derive destination facts on the same connection |
| logical root/seat alias policy | `SessionTargetRegistry` | authorize only an already-owned initial alias and unchanged same-alias continuity |
| target acknowledgement | Wake ACK ingress and Wake ledger | consume exact `TARGET_ACKNOWLEDGED`; never write ACK |
| source generation release | Executive Runtime process-generation evidence | prove old generation `PROVEN_DEAD / RELEASED` for succession |
| durable Stage-B assignment history | Runtime Events on root Job aggregate | append/fold exact revisions |
| action enforcement | `resolve_sol_action_target` | real downstream consumer; unchanged public signature |
| code/evidence | GitHub | implementation and proof truth |
| organizational workstreams | Agent OS | durable decision/handoff only |
| visibility/transport | Slack/Linear | never target or lifecycle authority |

A Stage-B event is evidence, not a reusable authority token. Every action-time consumer must reread
current assignment, current RuntimeBinding evidence, target policy, and actor identity.

---

## 2. Machine-readable v2 architecture freeze

<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->
```json
{
  "schema": "mastermind.autonomy_stage_b_f0_contract.v2",
  "correction_operation": "autonomy-stage-b0-protected-source-correction-r1-20260902-sol-001",
  "supersedes_schema": "mastermind.autonomy_stage_b_f0_contract.v1",
  "protected_source_disposition": "PROTECTED_SOURCE_CORRECTION_REQUIRED / V1_NOT_IMPLEMENTATION_AUTHORITY",
  "first_implementation_wave": "STAGE-B1",
  "implementation_gate": "HELD_UNTIL_V2_CORRECTION_PROTECTED",
  "command_schema": "mastermind.sol_action_target_command.v2",
  "event_schema": "mastermind.sol_action_target_event.v2",
  "snapshot_schema": "mastermind.sol_action_target_snapshot.v2",
  "event_aggregate_type": "job",
  "event_types": [
    "SOL_ACTION_TARGET_ASSIGNED",
    "SOL_ACTION_TARGET_TRANSFERRED"
  ],
  "supported_reasoning_surfaces": [
    "codex"
  ],
  "held_reasoning_surfaces": [
    {
      "reasoning_surface": "chatgpt-web",
      "state": "HELD_NOT_PROVEN",
      "missing_owners": [
        "accepted_current_runtime_binding_writer",
        "exact_semantic_ack_owner"
      ]
    }
  ],
  "mode_support": {
    "INITIAL_ASSIGNMENT": {
      "state": "SUPPORTED_WITH_EXISTING_ROOT_BINDING",
      "stage": "STAGE-B1",
      "reasoning_surfaces": [
        "codex"
      ],
      "authority_owner": "control_plane.session_targets.SessionTargetRegistry.policy_digest",
      "required_preconditions": [
        "root Job exists",
        "root_job_bindings[root_job_id][ceo] already exists",
        "caller destination alias equals the policy-owned alias",
        "destination is one exact current Codex RuntimeBinding",
        "destination has exact TARGET_ACKNOWLEDGED evidence"
      ],
      "refusal_when_missing": "INITIAL_AUTHORITY_OWNER_UNRESOLVED"
    },
    "SAME_ALIAS_GENERATION_SUCCESSION": {
      "state": "SUPPORTED_AFTER_VALID_INITIAL_ASSIGNMENT",
      "stage": "STAGE-B1",
      "reasoning_surfaces": [
        "codex"
      ],
      "authority_owner": "current Stage-B assignment + unchanged SessionTargetRegistry root/ceo alias",
      "required_preconditions": [
        "contiguous current Stage-B assignment exists",
        "source and destination session_alias are identical",
        "registry root/ceo alias is unchanged",
        "source process generation is PROVEN_DEAD and RELEASED",
        "destination generation is strictly greater and current",
        "destination has exact TARGET_ACKNOWLEDGED evidence"
      ],
      "refusal_when_missing": "SUCCESSION_EVIDENCE_UNRESOLVED"
    },
    "CROSS_ALIAS_RESPONSIBILITY_TRANSFER": {
      "state": "HELD_OWNER_UNRESOLVED",
      "stage": "NOT_AUTHORIZED_FOR_STAGE-B1",
      "reasoning_surfaces": [],
      "authority_owner": "NONE_ACCEPTED_IN_CURRENT_PROTECTED_SOURCE",
      "required_preconditions": [
        "future accepted receipt binds root_job_id",
        "future accepted receipt binds source and destination aliases",
        "future accepted receipt binds transfer mode and scope",
        "future accepted receipt proves current Chairman/Executive authority",
        "future implementation revalidates that receipt inside the Runtime transaction"
      ],
      "refusal_when_missing": "CROSS_ALIAS_AUTHORITY_OWNER_UNRESOLVED"
    }
  },
  "command_wire": {
    "caller_fields": [
      "schema",
      "root_job_id",
      "mode",
      "expected_assignment_revision",
      "expected_previous_target",
      "expected_destination",
      "session_target_policy_digest",
      "destination_wake_id",
      "source_process_generation_id"
    ],
    "caller_may_supply_command_id": false,
    "canonical_digest_fields": [
      "schema",
      "root_job_id",
      "mode",
      "expected_assignment_revision",
      "expected_previous_target",
      "expected_destination",
      "session_target_policy_digest",
      "destination_wake_id",
      "source_process_generation_id"
    ],
    "derived_command_id": "SOL-TARGET-<first-32-lowercase-hex-of-sha256-canonical-command-semantics>",
    "identical_replay": "same canonical semantics -> same derived id -> return identical existing event",
    "occupied_derived_id": "foreign or corrupt event at the derived id -> COMMAND_REPLAY_CONFLICT",
    "different_semantics_same_revision": "different derived ids serialize; one append may win and the other returns EXPECTED_REVISION_MISMATCH",
    "transport_claimed_id_rule": "if transport carries a claimed id, exact recomputation equality is required before lookup"
  },
  "authority_evidence_by_mode": {
    "INITIAL_ASSIGNMENT": {
      "state": "SUPPORTED_WITH_EXISTING_ROOT_BINDING",
      "owner": "control_plane.session_targets.SessionTargetRegistry",
      "source_ref_format": "session-target-policy:<policy_digest>:root:<root_job_id>:seat:ceo",
      "fingerprint_fields": [
        "policy_digest",
        "root_job_id",
        "target_seat",
        "session_alias",
        "reasoning_surface"
      ],
      "action_time_revalidation": [
        "root Job exists in Runtime",
        "root_job_bindings[root_job_id][ceo] exists",
        "target alias exists and target_seat is ceo",
        "target reasoning_surface is codex",
        "caller destination alias equals the policy-owned alias",
        "policy digest is recomputed inside the transaction input boundary"
      ]
    },
    "SAME_ALIAS_GENERATION_SUCCESSION": {
      "state": "SUPPORTED_AFTER_VALID_INITIAL_ASSIGNMENT",
      "owner": "current Stage-B assignment event + control_plane.session_targets.SessionTargetRegistry",
      "source_ref_format": "sol-target-assignment:<root_job_id>:revision:<assignment_revision>",
      "fingerprint_fields": [
        "root_job_id",
        "assignment_revision",
        "current_assignment_event_command_id",
        "session_target_policy_digest",
        "session_alias"
      ],
      "action_time_revalidation": [
        "current assignment history is contiguous and unique",
        "previous target equals the folded current assignment",
        "source and destination aliases are identical",
        "registry root/ceo alias remains identical",
        "destination binding generation is strictly greater",
        "source generation release and destination ACK are exact and effect-known"
      ]
    },
    "CROSS_ALIAS_RESPONSIBILITY_TRANSFER": {
      "state": "HELD_OWNER_UNRESOLVED",
      "owner": "NONE_ACCEPTED_IN_CURRENT_PROTECTED_SOURCE",
      "source_ref_format": null,
      "fingerprint_fields": [],
      "action_time_revalidation": [
        "refuse: no current receipt schema binds root, source alias, destination alias, mode, scope, and Chairman/Executive authority",
        "refuse Slack prose, actor labels, RuntimeBinding identity, target aliases, Stage-B events, and placement results as substitute authority"
      ]
    }
  },
  "evidence_contracts": {
    "root_job": {
      "owner": "control_plane.executive_runtime.Runtime",
      "lookup": "jobs row by exact root_job_id on the Stage-B transaction connection",
      "aggregate_type": "job",
      "event_type": "JOB_CREATED",
      "command_id_law": "read existing event identity; caller supplies no Job event command id",
      "schema_or_typed_shape": "control_plane.executive_runtime.Job",
      "required_identity": [
        "root_job_id",
        "root_job_id equals Job.root_job_id",
        "Job is not malformed or foreign"
      ],
      "effect_known_rule": "missing or unreadable root Job refuses before any append"
    },
    "session_target_policy": {
      "owner": "control_plane.session_targets.SessionTargetRegistry",
      "lookup": "policy_digest() + root_job_bindings[root_job_id][ceo] + targets[session_alias]",
      "aggregate_type": null,
      "event_type": null,
      "command_id_law": "not an Event; persist the recomputed policy digest and derived source_ref",
      "schema_or_typed_shape": "control_plane.session_targets.SessionTargetRegistry",
      "required_identity": [
        "policy_digest",
        "root_job_id",
        "target_seat=ceo",
        "session_alias",
        "reasoning_surface=codex"
      ],
      "effect_known_rule": "absent, changed, malformed, or non-Codex policy refuses"
    },
    "destination_current_binding": {
      "owner": "control_plane.runtime_binding_projection.active_operator_binding_facts + project_runtime_binding",
      "lookup": "Runtime.current_harness_binding_source(attempt_id, connection=tx) then canonical projection",
      "aggregate_type": "process_generation",
      "event_type": "ORCHESTRATION_WORK_ADMITTED + unique OHF_LAUNCH_DECISION(ALLOW)",
      "command_id_law": "work admission is ohf-work-admit:<process_generation_id>; launch decision is selected by exact aggregate/event uniqueness, never a caller id",
      "schema_or_typed_shape": "control_plane.executive_runtime.ActiveOperatorBindingFacts",
      "required_identity": [
        "attempt_id",
        "session_epoch_id",
        "process_generation_id",
        "generation_number",
        "provider=openai-codex",
        "owner_seat=ceo",
        "provider_session_id",
        "account_label",
        "observed_attestation_digest"
      ],
      "effect_known_rule": "canonical Runtime validator must return exactly one current admitted generation; provider_session_id is consumed transiently but never persisted by Stage B"
    },
    "destination_target_ack": {
      "owner": "control_plane.wake_ack_ingress.WakeAckIngressOperation + control_plane.wake_ledger",
      "lookup": "derive ledger_command_id(destination_wake_id, TARGET_ACKNOWLEDGED) and read exact wake aggregate",
      "aggregate_type": "wake",
      "event_type": "TARGET_ACKNOWLEDGED",
      "command_id_law": "<destination_wake_id>:ACK; caller cannot override",
      "schema_or_typed_shape": "mastermind.wake_consumption_ack/v1",
      "required_identity": [
        "destination_wake_id",
        "target_seat=ceo",
        "session_alias",
        "binding_id",
        "binding_generation",
        "delivered_command_id",
        "consumed_turn_reference",
        "acknowledgement_token"
      ],
      "effect_known_rule": "ACK must causally follow exact ACCEPTED or DELIVERED command and match destination alias/id/generation; missing, conflicting, or EFFECT_UNKNOWN history refuses"
    },
    "source_generation_release": {
      "owner": "control_plane.executive_runtime.Runtime",
      "lookup": "exact prior process_generation row plus its unique OHF_RECONCILE_OBSERVATION on tx",
      "aggregate_type": "process_generation",
      "event_type": "OHF_RECONCILE_OBSERVATION",
      "command_id_law": "read the existing event command id after exact aggregate lookup; caller supplies process_generation_id only as a comparison claim",
      "schema_or_typed_shape": "mastermind.operator_harness_reconcile_observation/v1",
      "required_identity": [
        "source_process_generation_id",
        "attempt_id",
        "session_epoch_id",
        "generation_number",
        "process_liveness=PROVEN_DEAD",
        "provider_writer_state=RELEASED",
        "exact observed process identity"
      ],
      "effect_known_rule": "one exact release observation and ended prior generation are required; absent, duplicate, contradictory, or effect-unknown evidence refuses"
    },
    "current_assignment_history": {
      "owner": "control_plane.executive_runtime.RuntimeStore events on the root Job aggregate",
      "lookup": "read all Stage-B event types for root_job_id on tx and fold assignment_revision from one",
      "aggregate_type": "job",
      "event_type": "SOL_ACTION_TARGET_ASSIGNED | SOL_ACTION_TARGET_TRANSFERRED",
      "command_id_law": "SOL-TARGET-<first-32-lowercase-hex-of-sha256-canonical-command-semantics>",
      "schema_or_typed_shape": "mastermind.sol_action_target_event.v2",
      "required_identity": [
        "root_job_id",
        "target_seat=ceo",
        "assignment_revision",
        "previous_target",
        "current_target",
        "command_fingerprint",
        "authority_fingerprint",
        "evidence_fingerprints"
      ],
      "effect_known_rule": "revision gaps, duplicates, wrong previous links, unsupported modes, or changed event semantics make the history CONFLICT"
    }
  },
  "projection_merge_algorithm": [
    "copy every existing root and every existing seat map from registry.root_job_bindings",
    "copy the selected root seat map or create an empty map only for that root",
    "replace only selected_root[ceo] with the folded Stage-B session_alias",
    "preserve every unrelated root and every non-ceo seat byte-semantically",
    "call with_root_job_bindings exactly once with the complete mapping"
  ],
  "transaction_order": [
    "validate exact command schema and recompute command_id",
    "RuntimeStore.transaction -> BEGIN IMMEDIATE",
    "lookup derived command_id before mutable assignment or binding reads",
    "identical replay returns; corrupt occupancy conflicts",
    "read exact root Job and fold contiguous Stage-B history",
    "compare expected revision and previous target",
    "revalidate mode authority and SessionTarget policy",
    "read destination binding through current_harness_binding_source on tx",
    "read exact Wake ACK and source release evidence on tx",
    "derive observed destination and compare caller claims",
    "append one immutable event",
    "commit; response ambiguity reconciles only by the same derived command_id"
  ],
  "failure_states": [
    "APPLIED",
    "REPLAYED",
    "NO_ASSIGNMENT",
    "COMMAND_REPLAY_CONFLICT",
    "ASSIGNMENT_HISTORY_CONFLICT",
    "EXPECTED_REVISION_MISMATCH",
    "INITIAL_AUTHORITY_OWNER_UNRESOLVED",
    "SUCCESSION_EVIDENCE_UNRESOLVED",
    "CROSS_ALIAS_AUTHORITY_OWNER_UNRESOLVED",
    "UNSUPPORTED_REASONING_SURFACE",
    "SOURCE_TARGET_MISMATCH",
    "SOURCE_RELEASE_MISSING",
    "DESTINATION_TARGET_INVALID",
    "DESTINATION_RUNTIME_UNAVAILABLE",
    "DESTINATION_RUNTIME_CONFLICT",
    "DESTINATION_ACK_MISSING",
    "AUTHORITY_SOURCE_NOT_CURRENT",
    "EFFECT_UNKNOWN_RECONCILE_FIRST",
    "RUNTIME_TRANSACTION_UNAVAILABLE"
  ],
  "no_rebuild": {
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
  },
  "truthful_maximum_stage_b1_claim": "BUILT_NOT_PROVEN / CODEX_INITIAL_AND_SAME_ALIAS_SOURCE_ONLY / PRODUCTION_DISARMED"
}
```
<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->

The JSON block is normative. A worker may not use surrounding prose to widen a held mode, add a
reasoning surface, substitute an authority source, or weaken an evidence identity.

---

## 3. Command and event model

### 3.1 Root aggregate

Every Stage-B event uses the existing Executive Runtime Event owner:

```text
aggregate_type = job
aggregate_id   = <exact root_job_id>
```

The root Job remains the responsibility identity. Stage B creates no responsibility ID, target row,
current-target table, transfer table, or mutable pointer.

### 3.2 Closed caller command

The caller supplies the exact v2 fields in the contract and no others. `command_id` is not a caller
field. The implementation validates and canonicalizes all fields, then derives the command ID. A
transport wrapper may carry a claimed ID only as a duplicate-detection checksum; Runtime must
recompute it and refuse any mismatch before event lookup.

The command contains comparison claims only:

- `expected_destination` is compared with policy-owned alias and Runtime-derived binding facts;
- `session_target_policy_digest` is recomputed from the current registry;
- `destination_wake_id` derives the ACK command identity;
- `source_process_generation_id` is permitted only for same-alias succession and is rejoined to the
  exact previous assignment and Runtime generation evidence;
- cross-alias mode fails before mutable evidence reads because its authority owner is unresolved.

### 3.3 Replay truth

Identical semantics derive the same ID. A foreign or corrupt event occupying that derived ID is a
replay conflict. Different semantics derive different IDs; if they race from one expected assignment
revision, `BEGIN IMMEDIATE` lets at most one append and the other returns
`EXPECTED_REVISION_MISMATCH`. There is no fictional normal case where changed canonical semantics
somehow share one correctly derived command ID.

Response loss is reconciled only by the same derived command ID on the same logical carrier. There is
no automatic retry at the new assignment revision, no new operation key, and no failover to another
alias or provider.

### 3.4 Persisted event

The event schema persists stable public identity and evidence fingerprints only:

```text
schema
mode
root_job_id
target_seat = ceo
assignment_revision
command_id
command_fingerprint
authority_source_ref
authority_fingerprint
session_target_policy_digest
previous_target | null
current_target
destination_wake_id
destination_ack_command_id
destination_ack_event_id
destination_ack_fingerprint
source_process_generation_id | null
source_release_event_id | null
source_release_event_command_id | null
source_release_fingerprint | null
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

Stage B never persists `native_handle`, `provider_session_id`, `account_label`, raw model output,
Slack identity, email, path, token, credential, transcript content, or provider exception text.

---

## 4. Exact mode law

### 4.1 Initial assignment

Stage-B1 may establish revision 1 only when `SessionTargetRegistry` already owns the root/CEO alias.
This is a durable materialization of existing target policy, not a caller choosing a destination.

Required conditions:

1. exact root Job exists;
2. no Stage-B assignment event exists;
3. `expected_assignment_revision == 0` and previous target is null;
4. `root_job_bindings[root_job_id]["ceo"]` exists;
5. target alias exists, owns seat `ceo`, and has reasoning surface `codex`;
6. caller destination alias equals that exact policy alias;
7. current Runtime source produces exactly one admitted matching binding;
8. exact destination Wake ACK matches alias, binding ID, generation, and causally prior delivery;
9. policy, binding, ACK, and command evidence remain current on the transaction connection.

A missing root binding is not permission to create one. It returns
`INITIAL_AUTHORITY_OWNER_UNRESOLVED` with no event.

### 4.2 Same-alias generation succession

Stage-B1 may advance revision N to N+1 only after a valid current assignment and only when logical
responsibility remains on the same alias.

Required conditions:

1. current history folds to one exact assignment;
2. caller previous target equals the folded target;
3. source and destination aliases are byte-identical;
4. current SessionTarget policy still maps root/CEO to that alias;
5. destination generation is strictly greater;
6. exact old process generation belongs to prior Attempt/epoch/generation and is ended;
7. one exact Runtime reconcile observation proves `PROVEN_DEAD` and `RELEASED`;
8. current Runtime source produces exactly the new admitted Codex generation;
9. destination Wake ACK matches the new alias/ID/generation;
10. no source, destination, delivery, ACK, or transaction effect is unknown.

Stage B does not terminate or release the old writer. It consumes the existing Runtime evidence after
that owner has done so.

### 4.3 Cross-alias transfer — held

Cross-alias responsibility transfer is not built by Stage-B1. Current protected source has no exact
accepted authority receipt that binds root, source alias, destination alias, transfer mode, scope,
and current Chairman/Executive authority. None of the following may substitute:

- a Slack message or account principal;
- a model-authored statement;
- a RuntimeBinding or provider session;
- a target alias or changed target config alone;
- a Capacity placement result;
- a Stage-B event trying to authorize its own transfer;
- a terminal worker result without a responsibility-transfer decision.

A later records wave must name an existing accepted authority owner or build and independently review
the smallest owner within Executive OS. Until then the only correct outcome is
`CROSS_ALIAS_AUTHORITY_OWNER_UNRESOLVED`.

### 4.4 ChatGPT-Web — held

ChatGPT-Web succession is not built by Stage-B1. Current protected
`runtime_binding_projection.py` maps only `openai-codex` to `codex`, and no accepted exact semantic
ACK owner for a ChatGPT-Web target is production-proven. Titles, visible tabs, browser recency,
account labels, or Chrome-extension presence cannot elect or attest a current writer.

The broader Autonomy program retains Web-Sol context rotation as a required user journey. Its
implementation starts only after the existing Web-Sol lane protects one canonical RuntimeBinding
writer and exact consumption ACK owner.

---

## 5. Evidence contracts

### 5.1 Root Job

The root is read from Runtime on the same transaction connection. A caller cannot supply a Job event
command ID or a substitute responsibility ID. The row must exist and identify itself as its own root.
Malformed or foreign lineage refuses before assignment fold.

### 5.2 SessionTarget policy

`SessionTargetRegistry.policy_digest()` plus the exact root/CEO alias and target object is the initial
assignment authority source. It is not an Event. Stage B persists the recomputed digest and derived
source reference so the decision is explainable without inventing a policy registry.

### 5.3 Destination current binding

`active_operator_binding_facts()` and `project_runtime_binding()` remain the only accepted projection
for Stage-B1. They consume `Runtime.current_harness_binding_source(..., connection=tx)`, including the
unique admitted process generation and `OHF_LAUNCH_DECISION(ALLOW)` evidence. Stage B never parses a
caller-provided native handle and never persists the provider session or account label.

### 5.4 Destination target ACK

The command supplies `destination_wake_id`, not an ACK command ID. Runtime derives
`<destination_wake_id>:ACK`, reads the exact Wake aggregate, validates
`mastermind.wake_consumption_ack/v1`, and requires exact alias/ID/generation and delivery command
causality. Stage B never writes target acknowledgement or source resolution.

### 5.5 Source generation release

Same-alias succession supplies a process generation ID only as a comparison claim. Runtime joins it
to the previous assignment’s Attempt/epoch/generation, reads the exact process-generation row and its
unique `OHF_RECONCILE_OBSERVATION`, validates
`mastermind.operator_harness_reconcile_observation/v1`, and requires `PROVEN_DEAD / RELEASED` plus
exact observed process identity. The persisted event records the observed event identity and digest,
not a caller-selected command reference.

### 5.6 Assignment history

The fold selects only Stage-B event types on the root Job aggregate. Revisions begin at one and are
contiguous. The event at N+1 must name the exact current target from N as `previous_target`. Duplicate
revision, gap, branch, wrong link, unsupported mode, changed root/seat, or malformed evidence makes the
snapshot `CONFLICT`; it is never repaired by selecting the newest event.

---

## 6. Transaction and concurrency

The exact transaction order is the normative list in the JSON contract. Important invariants:

- command lookup precedes mutable assignment, binding, ACK, and release reads;
- every Runtime-owned evidence query uses the same transaction connection;
- cross-alias mode refuses before any append;
- one append is the only Stage-B write;
- Stage B never mutates RuntimeBinding, Job, Attempt, or Worker rows;
- there is no provider, Slack, browser, filesystem, subprocess, or network call inside the
  transaction;
- response ambiguity is reconciled by the same command identity, not replayed under a new revision;
- concurrent different commands from revision N never self-rebase onto N+1.

No event may be appended when evidence is missing, stale, duplicated, contradictory, or effect
unknown.

---

## 7. Full root-binding projection

`SessionTargetRegistry.with_root_job_bindings()` validates and then replaces the supplied complete
mapping. It does not merge one root automatically. Therefore the projector must:

1. deep-copy every root and every seat map from `registry.root_job_bindings`;
2. copy or create only the selected root’s map;
3. replace only its `ceo` alias;
4. preserve every unrelated root and every sibling `coo`/`chairman` seat;
5. call `with_root_job_bindings()` once with the full mapping.

Tests must prove that projecting root A cannot erase root B and cannot erase root A’s COO or Chairman
binding. A destructive partial overlay is a release blocker.

The projected complete registry and a complete RuntimeBinding snapshot feed the unchanged
`resolve_sol_action_target()` consumer. A successful Stage-B append alone never grants actor
authority.

---

## 8. Snapshot and failure behavior

The v2 snapshot contains:

```text
schema
state = CURRENT | ABSENT | CONFLICT | UNKNOWN
reason
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
```

Failure behavior:

- no events -> `ABSENT / NO_ASSIGNMENT`;
- valid contiguous history -> `CURRENT`;
- malformed history -> `CONFLICT / ASSIGNMENT_HISTORY_CONFLICT`;
- incomplete/unreadable source -> `UNKNOWN`;
- root binding absent for initial mode -> owner unresolved, no append;
- Web or unsupported surface -> no append;
- cross-alias mode -> owner unresolved, no append;
- missing release or ACK -> no append;
- binding multiplicity or mismatch -> no append;
- stale expected revision -> no retry;
- effect uncertainty -> reconcile first, no failover;
- unknown exception -> fixed secret-safe error only.

---

## 9. Stage-B1 implementation surface

The first implementation remains one bounded source PR.

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

- `sol_action_target_transfer.py`: immutable command/event/snapshot types, exact parse/canonicalize,
  command derivation, fold, full-map projection, and typed outcomes;
- `executive_runtime.py`: the smallest connection-aware transaction method and exact prior-generation
  release read using existing rows/events;
- tests: authority/evidence contracts, replay/concurrency, mapping preservation, row integrity, and
  real Stage-A consumer behavior.

Protected read-only owners unless a new exact collision ruling changes the boundary:

```text
control_plane/session_targets.py
control_plane/runtime_binding_projection.py
control_plane/wake_ack_ingress.py
control_plane/wake_ledger.py
control_plane/wake_persist.py
control_plane/sol_action_target.py
all provider adapters and materializers
all Capacity / Model Router / Worker Browser paths
all Agent OS / Linear / Slack transport paths
all deployment / installer / credential paths
```

A new table, migration, registry, provider adapter, Wake schema, RuntimeBinding writer, or sixth
production/authority path requires a finite decision request before edit.

---

## 10. Required proof

Stage-B1 must kill at least these mutations:

1. caller supplies or changes command ID;
2. command lookup occurs after current-state reads;
3. foreign event at derived ID is treated as replay;
4. different same-revision command silently rebases;
5. initial assignment accepts missing root binding;
6. caller alias differs from policy alias;
7. Web surface is accepted;
8. cross-alias mode is accepted;
9. destination RuntimeBinding is missing, stale, duplicated, or wrong surface;
10. destination ACK has wrong wake, seat, alias, ID, generation, delivery command, turn, or token;
11. source generation is not exact prior target lineage;
12. source reconcile event is missing, duplicate, contradictory, alive, or writer-held;
13. destination generation is not strictly greater;
14. assignment history has gap, duplicate, branch, or wrong previous link;
15. projection drops an unrelated root;
16. projection drops a sibling seat;
17. persisted event includes native handle, provider session, account, path, Slack principal, or model
    output;
18. Job/Attempt/Worker/RuntimeBinding/Wake rows are changed by Stage B;
19. Stage-A source, stale, or sister actor becomes authoritative;
20. effect-unknown evidence triggers retry or failover.

Required evidence:

- focused RED→GREEN receipts where executable;
- concurrency proof under real Runtime SQLite transaction behavior;
- mutation discriminators for each authority/evidence gate;
- exact path and blob census;
- full feasible repository test and static/secret scans;
- hosted repository/security checks;
- independent immutable-head adversarial review;
- final current-protected and expected-head reread.

Green CI and a protected merge are not production proof.

---

## 11. Completion boundary

The maximum Stage-B1 source claim is:

```text
BUILT_NOT_PROVEN / CODEX_INITIAL_AND_SAME_ALIAS_SOURCE_ONLY / PRODUCTION_DISARMED
```

It does not make cross-alias transfer, ChatGPT-Web continuity, provider materialization, target ACK,
source resolution, deployment, automatic rotation, or an unattended canary live.

A later production proof must demonstrate with real inputs:

```text
existing policy-bound Codex target
-> exact current RuntimeBinding
-> exact target ACK
-> initial assignment
-> exact old-generation release
-> successor current RuntimeBinding and ACK
-> same-alias succession event
-> full-map Stage-A projection
-> stale actor fenced
-> useful Sol turn
-> restart/replay with zero duplicate event/provider write
-> truthful Control Room visibility
```

Cross-alias and ChatGPT-Web journeys require their own protected source-law predecessors. Stage B
never writes target acknowledgement or source resolution. Stage B never mutates RuntimeBinding, Job,
Attempt, or Worker rows. A source-only merge therefore remains `BUILT_NOT_PROVEN`, not accepted
Autonomy.
