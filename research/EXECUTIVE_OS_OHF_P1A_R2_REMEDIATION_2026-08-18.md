# OHF-P1A-R2 → R3 remediation ledger

**Date:** 2026-08-18
**R2 architecture SHA:** `da746a90c93c168ba696944c9197e7699d05e959`
**R2 independent review SHA:** `dad9d187b2364b78108cc3595d06d5e11cb8bef3`
**Typed freeze:** `control_plane/operator_harness_contract.py`
**This memo does not rewrite the R2 review artifact.**

CARDINALITY_B remains accepted. This ledger maps R2 findings to R3 rulings.

## Blockers R2-1 … R2-5

### R2-1 — Attempt session/pid projection contradicts write-once runtime

- **Review finding:** proposed `attempts.provider_session_id` / pid fields as
  current-epoch / current-generation projections while merged `record_process`
  is write-once.
- **R3 ruling:** those columns are LEGACY / SEALED-WORKER-ONLY. Rich OHF must
  not rewrite them. Canonical OHF identity lives in `harness_session_epochs`
  and `process_generations`. `AttemptExecutionMode` is the immutable discriminator.
- **Files:** constitution §2.1/§3.2/§3.3; schema §2/§3.1; contract
  `LEGACY_SEALED_WORKER_ATTEMPT_FIELDS`, `AttemptExecutionMode`.
- **Typed-contract change:** `rich_ohf_may_rewrite_legacy_attempt_field` returns
  false for pid/session columns.
- **Schema-proposal change:** drop Attempt current-epoch/generation pointers;
  add `execution_mode`.
- **Test:** `test_execution_mode_and_legacy_attempt_fields_are_sealed_worker_only`.
- **Remaining gate:** none for this defect. Sealed `record_process` stays.

### R2-2 — Writer fence absent while `provider_session_id` is NULL

- **Review finding:** post-bind unique index does not cover pre-bind creation.
- **R3 ruling:** Layer A `UNIQUE(session_epoch_id) WHERE executive_writer_held=1`
  plus Layer B post-bind realm unique index. Both required.
- **Files:** constitution §5; schema §3.3; contract `may_hold_prebind_epoch_writer`,
  `PROPOSED_SQL_INVARIANTS`.
- **Test:** `test_prebind_second_writer_on_same_epoch_refused`.
- **Remaining gate:** none for the fence hole.

### R2-3 — Adapter can mint Executive epoch/generation/turn IDs

- **Review finding:** `start_session -> SessionEpochRef`, `begin_turn -> TurnRef`.
- **R3 ruling:** Executive allocates IDs in TX-2/TX-5. Adapter receives
  `SessionEpochRef` / `ProcessGenerationRef` / `TurnRef` and returns
  observations.
- **Files:** constitution §3; contract Protocol signatures.
- **Test:** `test_executive_id_ownership_is_on_the_protocol`.
- **Remaining gate:** none.

### R2-4 — OperationId has no durable external-side-effect semantics

- **Review finding:** OperationId was an in-memory type, not bound to
  `events.command_id`, no EFFECT_UNKNOWN law.
- **R3 ruling:** INTENT `command_id = OperationId` on the existing Event plane.
  Derived receipts share aggregate id. Missing APPLIED after a possible call is
  `EFFECT_UNKNOWN` and non-replayable unless local state proves the call never
  began. UNKNOWN process + UNKNOWN effect blocks a successor writer.
- **Files:** constitution §12.1; schema §3.4; contract `OperationId`,
  `resolve_operation_after_crash`, `CRASH_WINDOW_MATRIX`.
- **Test:** `test_operation_id_maps_to_existing_command_id_law`,
  `test_intent_without_applied_is_non_replayable_unless_call_never_started`.
- **Remaining gate:** provider-native idempotency is advertised, not assumed.

### R2-5 — Launch comparator trusts caller verdicts and ALLOWs UNKNOWN model

- **Review finding:** `compare_launch(..., workspace_match=True, ...)` and
  `served_model=None` could ALLOW.
- **R3 ruling:** `compare_launch(requested, observed)` only. Served model
  UNKNOWN refuses. Comparator derives capability, workspace, sandbox, approval,
  network, config, auth, helper-ceiling results.
- **Files:** constitution §7–§8; contract `compare_launch`.
- **Test:** `test_compare_launch_has_no_caller_verdict_escape_hatch`,
  `test_launch_gate_and_served_model_mismatch`.
- **Remaining gate:** providers that cannot attest served model before inference
  cannot satisfy a strict production profile.

## Required-before-merge R2-6 … R2-10

### R2-6 — ReconcileReport asserts Executive-owned truth

- **Ruling:** replaced by `ReconcileObservation`. Resume safety is
  `derive_resume_safety` in Executive code.
- **Disposition:** CLOSED.
- **Test:** `test_reconcile_observation_cannot_assert_executive_facts`.

### R2-7 — Restore collapses historical RELEASED into UNKNOWN

- **Ruling:** `RestoreInvalidationResult` preserves historical provider and
  process evidence; TX-9 clears writer, abandons CURRENT epochs, marks Attempt
  LOST.
- **Disposition:** CLOSED.
- **Test:** `test_restore_preserves_historical_released_evidence`.

### R2-8 — Optional methods and EventCursor not frozen

- **Ruling:** typed extension Protocols; EventCursor requires generation scope
  plus local sequence / optional provider replay cursor.
- **Disposition:** CLOSED.
- **Test:** `test_optional_protocols_require_operation_id`,
  `test_event_cursor_is_generation_scoped`.

### R2-9 — start_session combines session create and process launch

- **Ruling:** combined start remains valid. Ownership is explicit: Executive
  preallocates IDs and binds S1; adapter returns observations only. Not split
  because splitting would not improve the crash window once INTENT+EFFECT_UNKNOWN
  exist.
- **Disposition:** CLOSED (combined, ownership corrected).

### R2-10 — Named transaction groups missing

- **Ruling:** TX-1…TX-9 frozen in `TRANSACTION_GROUPS` with crash-window matrix.
- **Disposition:** CLOSED.
- **Test:** `test_transaction_groups_and_crash_windows_are_frozen`.

## H13–H34

| ID | R2 result | R3 disposition | Evidence |
|---|---|---|---|
| H13 Attempt.provider_session_id vs write-once | CONFIRMED_DEFECT | CLOSED | LEGACY_ONLY; no OHF rewrite |
| H14 Attempt pid projection | CONFIRMED_DEFECT | CLOSED | LEGACY_ONLY; OHF `adopt_attempt` uses epoch/generation state |
| H15 pre-bind writer | CONFIRMED_DEFECT | CLOSED | epoch unique held-writer index |
| H16 ID allocation | CONFIRMED_DEFECT | CLOSED | Protocol receives refs, returns observations |
| H17 durable OperationId | CONFIRMED_DEFECT | CLOSED | events.command_id INTENT + derived receipts |
| H18 caller-supplied verdicts | CONFIRMED_DEFECT | CLOSED | compare_launch two positional inputs |
| H19 capability precision | CONFIRMED_DEFECT | CLOSED | ObservedCapabilityIdentity + classifier |
| H20 served_model UNKNOWN | CONFIRMED_DEFECT | CLOSED | REFUSE_SERVED_MODEL_UNKNOWN |
| H21 binary/sandbox/approval/config | CONFIRMED_DEFECT | CLOSED | comparator compares structures |
| H22 auth_realm_match default True | CONFIRMED_DEFECT | CLOSED | AuthRealmRequirement; SLOT_BOUND_V1 explicit |
| H23 optional Protocol signatures | CONFIRMED_DEFECT | CLOSED | OPTIONAL_ADAPTER_PROTOCOLS |
| H24 ReconcileReport Executive facts | CONFIRMED_DEFECT | CLOSED | ReconcileObservation field set |
| H25 restore RELEASED→UNKNOWN | CONFIRMED_DEFECT | CLOSED | RestoreInvalidationResult preserves history |
| H26 atomic epoch/writer txns | CONFIRMED_DEFECT | CLOSED | TX-1…TX-9 |
| H27 CREATING state | NEEDS_AMENDMENT | CLOSED | CURRENT+NULL plus H15 fence; no extra state |
| H28 lifetime session unique | NOT_A_DEFECT | CLOSED | kept worker+session unique for epoch lifetime |
| H29 worker_id stability | PRODUCTION_GATE_ONLY | GATE_PRESERVED | WORKER_SLOT_AUTH_BINDING_PRODUCTION_INVARIANT |
| H30 start_session width | CONFIRMED_DEFECT | CLOSED | combined start kept; Executive allocates IDs and binds S1 |
| H31 generation.provider_session_id copy | NEEDS_AMENDMENT | CLOSED | labeled INDEX PROJECTION; mismatch is StateConflict |
| H32 Attempt current pointers | NEEDS_AMENDMENT | CLOSED | both proposed pointers removed |
| H33 EventCursor sequence | CONFIRMED_DEFECT | CLOSED | generation-scoped local_sequence |
| H34 all methods idempotent | CONFIRMED_DEFECT | CLOSED | OperationIdempotencyClass; state-changing methods require OperationId |

H13–H28 and H30–H34 are contract closures. H29 remains a production
activation invariant, not a P1A architecture blocker.

## Preserved gates (unchanged)

- ACCOUNT_REALM_ATTESTATION_UNPROVEN
- residual Codex capabilities write-canary / production
- native helper ceiling on write-capable profiles
- transitive orphan cleanup UNKNOWN
- host reboot live proof UNKNOWN
- multi-host identity postponed
- worker-slot auth-binding production invariant

## R3.1 (2026-08-19)

Does not reopen R2-1…R2-5 or CARDINALITY_B.

- **Same-epoch generation recovery:** TX-10 atomically releases the dead
  generation's Executive writer, allocates G2 on the existing CURRENT epoch,
  acquires the writer, and commits the resume OperationId INTENT before
  `resume_session`. Tests:
  `test_hard_dead_released_same_epoch_g2_is_lawful`,
  `test_hard_dead_held_or_unknown_provider_writer_refuses_g2`,
  `test_unknown_process_refuses_same_epoch_g2`,
  `test_duplicate_same_epoch_recovery_hits_writer_and_operation_id`,
  `test_tx10_intent_crash_has_deterministic_replay_disposition`.
- **OperationId receipt closure:** `OperationId` rejects any base id whose
  derived `:{applied,refused,effect-unknown,reconciled}` receipts would miss
  `_COMMAND_ID_RE`. Test: `test_operation_id_receipt_closure_at_max_and_one_beyond`.
