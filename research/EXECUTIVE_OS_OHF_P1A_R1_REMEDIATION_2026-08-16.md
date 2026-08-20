# OHF-P1A-R1 findings — R2 author remediation map

**Date:** 2026-08-16
**Architecture reviewed by R1:** `f3c1cdb7d3b40103450cf3f845ac0648479585e7`
**Independent review artifact:** `3f1ee290ba147313d3bee3a1192e18b21313f88d`
**This memo does not review itself and does not amend the independent review file.**

Typed freeze: `control_plane/operator_harness_contract.py`
Author contracts updated: constitution, durable identity/schema, adversarial
packet. Minimal-surface evidence: gate classification only.

| ID | Review class | Disposition |
|---|---|---|
| R1 | ARCH_BLOCKER | REMEDIATED |
| R2 | ARCH_BLOCKER | REMEDIATED |
| R3 | ARCH_BLOCKER | REMEDIATED |
| R4 | ARCH_BLOCKER | REMEDIATED |
| R5 | ARCH_BLOCKER | REMEDIATED |
| R6 | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED |
| R7 | ARCH_BLOCKER | REMEDIATED |
| R8 | P1B/PRODUCTION gate | GATE_PRESERVED |
| R9 | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED |
| R10 | WRITE_CANARY_GATE | GATE_PRESERVED |
| R11 | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED |
| R12 | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED |
| R13 | NONBLOCKING / WRITE_CANARY | GATE_PRESERVED |
| R14 | postpone v3 extras | REMEDIATED / POSTPONED |

No finding is DISPUTED.

## R1 — CARDINALITY_B

- **Old rule:** Attempt 1:1 primary HarnessSession; context rotation = NEW_ATTEMPT.
- **Review:** burns `attempt_limit`; Attempt is a placement/retry slot.
- **New rule:** Attempt 1:N sequential primary `HarnessSessionEpoch`s; at most one CURRENT; rotation = new epoch, same Attempt.
- **Files:** constitution §2–§4; contract `CARDINALITY` / `ATTEMPT_BOUNDARY_MATRIX`; schema `harness_session_epochs`.
- **Remaining:** none for this identity choice. Independent R2 must still attack it.

## R2 — writer realm key

- **Old rule:** conceptual `(provider, account_label, native_session_id)`; SQL `UNIQUE(native_session_id)`.
- **Review:** opaque ids; `account_label` not unique.
- **New rule:** `(worker_id, provider_session_id)`; unique held writer and unique epoch binding per worker.
- **Files:** constitution §5; schema §3.2–§3.3; contract `writer_realm_key`.
- **Remaining:** authenticated account realm still unproven (R8).

## R3 — process death vs writer

- **Old rule:** open generation = `ended_at IS NULL`; terminalization ended open generations.
- **Review:** P0 SIGKILL writer remains after process death.
- **New rule:** four facts; `ended_at` is process evidence only; `executive_writer_held` survives unclean death; abandonment ≠ RELEASED; S2 allowed.
- **Files:** constitution §5; schema §3.3; contract `process_end_does_not_release_writer` / `abandon_epoch`.
- **Remaining:** none as architecture. Live steal API still unused.

## R4 — live App Server adoption

- **Old rule:** adopt live process if pid+start+boot match.
- **Review:** stdio owned by spawning process; `adopt_attempt` is lease-only.
- **New rule:** LIVE APP SERVER PROCESS ADOPTION = NOT_SUPPORTED. Lease adoption ≠ process adoption ≠ provider session resume.
- **Files:** constitution §6; contract `LIVE_APP_SERVER_ADOPTION` / `derive_resume_safety(live_transport_adoptable=True)` always false.
- **Remaining:** future broker transport is a different commission.

## R5 — profile seal

- **Old rule:** one immutable ExecutionProfile mixing requested and observed.
- **Review:** no legal seal point; work before attestation.
- **New rule:** RequestedExecutionProfile sealed pre-start; ObservedHarnessAttestation sealed pre-work; LaunchDecision gate.
- **Files:** constitution §7; contract dataclasses + `compare_launch`.
- **Remaining:** providers that only reveal served model on first inference are incapable of pre-work attestation unless a bounded probe exists.

## R6 — typed adapter

- **Old rule:** method names without types/side effects.
- **Review:** P1B would invent the contract.
- **New rule:** dataclasses, Protocol, METHOD_CONTRACTS, prepare rejected, reconcile observational, OperationId idempotency, EventCursor.
- **Files:** `control_plane/operator_harness_contract.py`; `tests/test_ohf_p1a_operator_harness_contract.py`; constitution §12.
- **Remaining:** no production adapter implementation (intentional).

## R7 — backup/restore

- **Old rule:** partially UNKNOWN.
- **Review:** restored active writers can resurrect.
- **New rule:** Option A; restore invalidates held; abandon current epochs; Attempt LOST; do not invent RELEASED.
- **Files:** constitution §13; schema §6; contract `restore_invalidation`.
- **Remaining:** host-reboot live behavior still UNKNOWN.

## R8 — account_label

- **Old rule:** account_label as fencing identity.
- **Review:** not unique, not authenticated.
- **New rule:** fence on worker_id; ACCOUNT_REALM_ATTESTATION_UNPROVEN preserved.
- **Files:** constitution §9; AuthRealmFact.
- **Remaining gate:** multi-account activation and production arming.

## R9 — one source of truth

- **Old rule:** native_session_id synonym; mixed profile blob; recovery on Attempt and generation.
- **Review:** P7 violation.
- **New rule:** reuse `provider_session_id`; projections documented; recovery generation-scoped.
- **Files:** schema §2; constitution §15 table.
- **Remaining:** implementation must keep projections in one transaction (P1B/schema later).

## R10 — native helpers

- **Old rule:** V1 helpers “read-only explore” by prompt.
- **Review:** parent write tools inherit.
- **New rule:** write-capable helpers disabled unless `supports_subagent_capability_ceiling` is proven. Prompt is not a boundary. Helpers ≠ review.
- **Files:** constitution §10; contract `native_helpers_allowed`.
- **Remaining gate:** write-capable-helper until a harness proves the ceiling.

## R11 — harness binary

- **Old rule:** patch-compatible versions could stay in one Attempt.
- **Review:** contradictory with Attempt identity.
- **New rule:** exact binary digest is Attempt-immutable. Change → NEW_ATTEMPT.
- **Files:** constitution §4; boundary matrix.
- **Remaining:** none for V1.

## R12 — Phase 1F quality tradeoff

- **Old rule:** implied no cost.
- **Review:** native planner context is lost.
- **New rule:** V1_QUALITY_TRADEOFF_ACCEPTED; no parked leader; later parity measurement required.
- **Files:** constitution §11; contract constant.
- **Remaining:** measurement is future work, not an architecture hole.

## R13 — residual plugins

- **Old rule:** unclassified, refuse write profiles (correct).
- **Review:** keep as write-canary gate; do not fake allowlist.
- **New rule:** same. Not added to ALLOWED_AMBIENT. Optional plugins spike not run.
- **Files:** minimal-surface §6; constitution §8.
- **Remaining gate:** write-capable Codex canary and production arming.

## R14 — postpone speculative schema

- **Old rule:** `native_subordinates_json`, hostname-hash `host_id` in v3.
- **Review:** postpone unless restart-required.
- **New rule:** both postponed. Forks in events. No hostname-hash identity.
- **Files:** schema §2 / §9.
- **Remaining:** future multi-host identity commission.

## Preserved open gates

ACCOUNT_REALM_ATTESTATION_UNPROVEN;
residual Codex plugin/template skills (write-canary / production);
native-helper capability ceiling (write-capable-helper);
transitive orphan cleanup UNKNOWN;
host reboot live UNKNOWN;
multi-host identity future;
writer-steal API unused;
structured MCP item events not universal;
live App Server adoption NOT_SUPPORTED.
