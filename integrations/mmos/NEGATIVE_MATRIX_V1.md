# MMOS V1 — Negative-Case Matrix (§6), V1

Director H (test/verification lead). One row per §6 failure case of
`~/.hermes/profiles/engineering/mmos/T3_HANDOFF_V2.md` (read-only), split per
assignment for compound rows: coordinator restart → before/after ACK (NM-01/02);
gateway busy vs disconnected vs stopped → three rows (NM-04/05/06).
Adapter rows defer to the authoritative invariant table in
`integrations/t3/docs/AUDIT_T3_DURABLE_ADAPTER_OPUS_20261109.md` (verdict
NEEDS_REWORK).

Verification environment (this branch, this session):
`env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q <file>`;
vitest via `cd app/mastermind_os && npx vitest run <file>` (node_modules
installed once via `npm ci`). **Every cited test was run in this session.**
Result: all cited suites pass except one PRE-EXISTING, unrelated failure —
`tests/test_provider_quota_observation.py::test_producer_without_observations_path_is_byte_identical_to_before`
(golden byte-identity drift at tests/test_provider_quota_observation.py:489,
fails on the clean branch before any Director H edit; no matrix citation
points at it). No live gateway, T3 desktop, or Executive was contacted; every
new test injects fakes or uses tmp-path stores only.

Status legend — `PROVEN_BY_TEST`: a real adversarial test at the exact
mutation boundary exists, was run, and passes (or xfails strictly where the
defect is the documented finding). `PARTIAL`: the free portion is proven and
the remainder sits in a concurrently-owned path (hand-off written).
`GAP`: no in-repo mutation boundary exists. `OWNED_BY_RUNNING_DIRECTOR`: the
boundary module is owned by a running director lane; design below, not
implemented here.

## Totals

| Status | Rows | Count |
|---|---|---|
| PROVEN_BY_TEST | NM-04, NM-05, NM-12, NM-13, NM-18, NM-20 | 6 |
| PARTIAL | NM-06, NM-09, NM-16, NM-17, NM-19 | 5 |
| GAP | NM-10 | 1 |
| OWNED_BY_RUNNING_DIRECTOR | NM-01, NM-02, NM-03, NM-07, NM-08, NM-11, NM-14, NM-15 | 8 |
| **Total** | | **20** |

New adversarial tests: `tests/test_mmos_negative_matrix.py` — **5 passed,
1 xfailed (strict)**. No vitest file was created: the only free non-React TS
boundary (auth-navigation-guard) already has an adversarial suite, verified
this session (3 passed); every remaining TS surface is D/B-owned (hand-off,
not mine to test).

## Matrix

| Row | §6 failure case | Mutation boundary (exact) | Owning module(s) | Existing adversarial tests (run this session) | Status |
|---|---|---|---|---|---|
| NM-01 | Coordinator restart BEFORE ACK — launch count stays 1, original namespace recovered | `t3_execution_adapter` launch/ack persistence (two-process race: audit inv1, finding #1 BLOCKER) | `control_plane/t3_execution_adapter.py` (A3) | `tests/test_t3_adapter_durability.py::ColdRestartDurabilityTests::test_crash_before_ack_replays_same_key_and_namespace` — PASS (single-process). Audit: two-connection concurrent start UNPROVEN (BLOCKER) | OWNED_BY_RUNNING_DIRECTOR (A3) |
| NM-02 | Coordinator restart AFTER ACK — launch count stays 1, same thread | `t3_execution_adapter` start-reattach idempotency (audit inv1) | `control_plane/t3_execution_adapter.py` (A3) | `…::test_restart_reattaches_same_thread_with_launch_count_one`, `…::test_replay_returning_a_different_thread_is_refused`, `…::test_replay_receipt_echoing_a_foreign_key_is_refused` — PASS (single-process). Audit #1: two-process double-launch remains a BLOCKER | OWNED_BY_RUNNING_DIRECTOR (A3) |
| NM-03 | Restart recovery cursor must never go backwards | `t3_execution_adapter` cursor/cancel ledger replay (audit inv8, finding #8) | `control_plane/t3_execution_adapter.py` (A3) | `…::test_cursor_and_cancel_ledger_survive_restart` — PASS (round-trip). Audit #8: backwards cursor not refused | OWNED_BY_RUNNING_DIRECTOR (A3) |
| NM-04 | Viewer disconnect mid-run — same thread/cursor, no new thread | `hermes_native_continuity.classify_native_continuity` / `classify_error_code` | `integrations/session_bridge/hermes_native_continuity.py` (free) | `tests/test_session_bridge_native_continuity.py::TestNativeResults::test_not_submitted_and_unavailable_are_viewer_disconnected`, `::TestErrorCodes::test_busy_pending_and_viewer_codes_stay_distinct`, `::TestPermittedContinuations::test_only_idle_permits_a_fresh_send` — PASS | PROVEN_BY_TEST |
| NM-05 | Gateway BUSY — distinct label, no auto-retry/remake | `classify_error_code` busy-code table; `permitted_continuations(GATEWAY_BUSY)` | same (free) | `…::TestErrorCodes::test_busy_pending_and_viewer_codes_stay_distinct`, `…::TestNativeResults::test_quiet_session_snapshot_is_idle_and_busy_snapshot_is_not`, `::TestPermittedContinuations::test_only_idle_permits_a_fresh_send` — PASS | PROVEN_BY_TEST |
| NM-06 | Gateway DISCONNECTED vs STOPPED — distinct labels | `classify_error_code` (no stopped-state vocabulary exists) | same (free) + adapter code table (A3) + TS mirror (B) | Disconnected: same tests as NM-04 — PASS. Stopped: `tests/test_mmos_negative_matrix.py::test_nm06_stopped_shaped_code_stays_unknown_carries_code_and_offers_no_mutation` — PASS; `…::test_nm06_gateway_stopped_needs_a_label_distinct_from_busy_and_disconnected` — XFAIL(strict) | PARTIAL |
| NM-07 | Admission succeeded but UI timed out — receipt lookup, no duplicate Job | Executive admission idempotency (root_ref, immediate_parent_run_ref, logical_child_key + request_digest) | `control_plane/executive_runtime.py` (C) | none at that boundary (out of my lane) — design below | OWNED_BY_RUNNING_DIRECTOR (C) |
| NM-08 | Wrong OAuth client / namespace — two clients NEVER the same idempotency key | `t3_execution_adapter` replay binding / namespace isolation (audit inv2, finding #3 fail-open) | `control_plane/t3_execution_adapter.py` (A3) | `…::test_restart_under_a_different_namespace_is_refused` — PASS (attesting path). Audit #3: non-attesting ports fail open | OWNED_BY_RUNNING_DIRECTOR (A3) |
| NM-09 | 429/quota — WAIT/UNKNOWN/REFUSED, no silent cross-account fallback after a possible effect | `provider_quota_observation.observe_provider` status dispatch; `paid_fabric_capacity` validator; admission/retry layer | free: `control_plane/provider_quota_observation.py`, `control_plane/paid_fabric_capacity.py`; C: retry/admission | `tests/test_mmos_negative_matrix.py::test_nm09_rate_limited_429_is_typed_unknown_never_healthy_numbers` — PASS; `tests/test_provider_quota_observation.py::test_observe_provider_maps_statuses_types_and_timeouts`, `::test_unobserved_entries_must_stay_provenance_free_and_number_free` — PASS; `tests/test_paid_fabric_capacity.py::test_active_cooldown_is_offline_yes`, `::test_nonobserved_canonical_status_never_reuses_fresh_old_pair`, `::test_validator_cannot_escalate_any_receipt` — PASS; `…native_continuity.py::TestNativeResults::test_model_quota_and_rate_limit_are_model_limited_never_retryable` — PASS. Admission-layer fallback prohibition: C-owned (NM-07 surface) | PARTIAL |
| NM-10 | update_paused/drain — no service restart to evade | none in repo (gateway/desktop owns the switch; `update_paused` absent from tree) | Hermes gateway / T3 desktop (A3 adapter surface, B runtime) | In-repo analog only: `tests/test_workspace_lease.py::test_readers_never_conflict_with_writer_and_never_blocked` (allocator refuses under disk pressure; `ALLOCATIONS_BLOCKED_DISK_PRESSURE`) and `::test_no_second_sweeper_no_deletion_anywhere` (module provably has no restart/deletion primitive) — PASS | GAP |
| NM-11 | DSH fanout at envelope limit — in-process 8-active/depth-1, cannot counterfeit an independently placed child | `dsh_acp_runtime.py` DSH fanout enforcement | `control_plane/dsh_acp_runtime.py` (lane A) | Free-side envelope law: `tests/test_fabric_placement_policy.py::test_bounded_native_fanout_parent_reserves_envelope_and_children_skip` (child at 999 admitted only against the PARENT's reservation — a self-reserving child cannot counterfeit independent placement), `::test_envelope_folds_into_the_host_slot_demand`, `::test_fabric_per_child_parent_reserves_zero_local_child_slots` — PASS | OWNED_BY_RUNNING_DIRECTOR (lane A) |
| NM-12 | Parent+child host slots — no double envelope/overcommit | `fabric_placement_policy.fanout_envelope_slots` / `inflate_host_slot_demand` / `ChildHeadroomPolicy.admit_against_headroom` / `descendant_admission` | `control_plane/fabric_placement_policy.py` (free) | `…::test_parent_claim_reserves_only_its_own_slot`, `::test_headroom_blocks_parents_from_the_last_reserved_child_slots`, `::test_child_headroom_blocks_a_parent_but_never_a_child`, `::test_fanout_envelope_reserved_at_parents_host_until_settlement`, `::test_descendant_cap_blocks_the_n_plus_oneth_concurrent_child` — PASS | PROVEN_BY_TEST |
| NM-13 | Stale lease — blocks NEW execution; exact-run cancel still allowed | `WorkspaceLeaseStore.acquire_single_writer` / `release` (epoch gate) / `reclaim_eligible` | `control_plane/workspace_lease.py` (free) | NEW `tests/test_mmos_negative_matrix.py::test_nm13_stale_lease_blocks_new_execution_and_only_the_exact_writer_retires`, `::test_nm13_expiry_alone_is_never_reclaim_safety_settlement_is` — PASS; existing `tests/test_workspace_lease.py::test_one_writer_per_mutable_checkout`, `::test_release_with_stale_epoch_refused_with_writer_identity`, `::test_store_driven_reclaim_view_and_pressure_posture`, `::test_concurrent_acquire_single_writer_one_winner_precise_conflict` — PASS | PROVEN_BY_TEST |
| NM-14 | Duplicate/concurrent admissions — replay vs digest-conflict, atomic counts | Executive admission transaction (idempotency triple + request_digest) | `control_plane/executive_runtime.py` (C) | Storage-layer law: `tests/test_workspace_lease.py::test_concurrent_acquire_single_writer_one_winner_precise_conflict` — PASS (two-thread barrier, one winner, precise loser conflict). Admission boundary: design below | OWNED_BY_RUNNING_DIRECTOR (C) |
| NM-15 | #2329 shell shapes — structural refusal, no allowlist bypass | `ops/executive_os/provider_orchestrator_guard.py` | `ops/executive_os/provider_orchestrator_guard.py` (C, #2329) | `tests/test_provider_orchestrator_policy.py` — full suite PASS this session (recorded; not re-derived here). New-shape/bypass designs below | OWNED_BY_RUNNING_DIRECTOR (C) |
| NM-16 | Green-but-unmerged/uninstalled — real stage reported | `github_pr_lifecycle.assess_pr_lifecycle` (python) + stage renderer (TSX) | free: `control_plane/github_pr_lifecycle.py`; D: `app/mastermind_os/src/**/*.tsx` | NEW `tests/test_mmos_negative_matrix.py::test_nm16_green_but_unmerged_never_reports_integrated_or_closable` — PASS; existing `tests/test_github_pr_lifecycle.py::test_known_terminal_work_with_unknown_integration_has_distinct_issue`, `::test_unique_unpreserved_delta_is_not_closed_just_because_it_is_old` — PASS. UI stage rendering: D-owned | PARTIAL |
| NM-17 | Role switch — no cross-profile session/memory leak | python role transport binding + foreign-session refusal; TS session store | free: `integrations/session_bridge/hermes_native.py`, `control_plane/native_continuation.py`; B/D: TS session state | `tests/test_mastermind_os_native_role_transport.py::test_unsupported_older_peer_never_selects_another_role`, `::test_other_valid_native_family_cannot_answer_the_original`, `::test_valid_native_result_still_must_match_the_exact_send_target` — PASS; `tests/test_hermes_primary_session_return.py::test_foreign_native_session_is_refused_before_observation_projection` — PASS; `tests/test_team_roster_projection.py::TestGatewayEvidence::test_identify_beats_lock_and_home_mismatch_never_qualifies` (another home's gateway is never readiness for this profile) — PASS | PARTIAL |
| NM-18 | Unknown host/thermal/quota — shown unknown, never healthy/zero | `t3_environment_projection.project` honesty rules; `paid_fabric_capacity` offline states; `executive_host_capacity` zero-vs-unknown | free: `control_plane/t3_environment_projection.py`, `paid_fabric_capacity.py`, `executive_host_capacity.py` | `tests/test_t3_environment_projection.py::test_missing_observation_facts_are_unknown_never_ready`, `::test_thermal_unknown_propagates_and_blocks_eligibility`, `::test_missing_thermal_field_is_unknown_not_ready`, `::test_stopped_service_degrades_provider_sessions`, `::test_unobserved_provider_listing_is_unknown_not_empty`, `::test_projection_refuses_forged_eligibility` — PASS; `tests/test_paid_fabric_capacity.py::test_membership_unknown_never_fabricates_facts`, `::test_missing_database_is_offline_unknown_broker` — PASS; `tests/test_executive_host_capacity.py::test_observed_zero_is_valid_only_after_successful_observation` — PASS | PROVEN_BY_TEST |
| NM-19 | Sign-out mid-turn — renderer fences, no wrong-principal output | `auth-navigation-guard.ts` (free non-React) + renderer fences (TSX) | free: `app/mastermind_os/src/auth-navigation-guard.ts`; D: renderers | `app/mastermind_os/src/auth-navigation-guard.test.ts` — 3 PASS this session (explicit-logout marker ≠ passive expiry; automatic sign-in gated on owner holds; fail-closed on storage errors). Mid-turn renderer fencing: D-owned | PARTIAL |
| NM-20 | Child returns — parent consumption + explicit CONTINUE/STOP, no orphan wave | `fabric_stop_return.prepare_stop` (write-once receipts) + `hermes_native.validate_public_result` (`parent_consumed` mandatory False) | free: `integrations/session_bridge/fabric_stop_return.py`, `hermes_native.py`, `fabric_reject_outcome.py` | `tests/test_fabric_stop_return.py::test_at_most_one_attempt_even_after_uncertain_delivery` (first Stop → `{"decision":"block"}` = explicit CONTINUE; next turn → `{}` = allow STOP, zero further reads), `::test_exclusive_receipt_creation_race_does_not_duplicate`, `::test_failed_durability_does_not_emit_or_allow_replay` — PASS; `tests/test_hermes_primary_session_return.py::test_current_original_reader_preserves_answer_and_identity`, `::test_observation_uses_the_original_full_admission` — PASS; `tests/test_fabric_reject_outcome.py::test_repeat_refuses_without_second_write`, `::test_unconfirmed_write_never_becomes_accepted_or_retry_permission` (CONSUMED_NOT_ACCEPTED, retry never authorized) — PASS | PROVEN_BY_TEST |

## Row detail — PARTIAL / GAP designs and findings

### NM-06 gateway stopped (PARTIAL — real defect, tripwired)
The continuity vocabulary (`STATES`) has no gateway-stopped member. A
stopped-gateway error code (e.g. `NATIVE_GATEWAY_STOPPED`, the shape the A3
adapter would surface) currently classifies `UNCLASSIFIED` — honest (never
idle, code retained, no mutation offered; proven by the new floor test) but
NOT distinct from busy/disconnected, so §6's "distinct labels" is unmet.
`test_nm06_gateway_stopped_needs_a_label_distinct_from_busy_and_disconnected`
xfails strictly and will flip (strict XPASS = red) the moment a distinct
state exists. Fix path: A3 emits a typed stopped code at the adapter boundary;
B adds the matching state to the TS mirror; the python vocabulary gains the
state (a one-line `STATES` + code-table change with its own label test);
remove the xfail. No auto-retry/remake requirement attaches (permitted
continuations for the new state must be read/status only).

### NM-09 429/quota (PARTIAL — free layers proven; admission layer with C)
Free layers now proven end-to-end: a 429 from the declared endpoint becomes
`observed=False` with NO numbers even when the 429 body advertises
`remaining_percent 99.9` (the dispatch never parses non-200 bodies), probe
evidence `[{"endpoint": …, "status": 429}]` retained, exact account echoed,
exactly one fetch (no endpoint/account fallback probe). The closed reason
vocabulary types it `NOT_EXPOSED` today — honest but imprecise; a future
`RATE_LIMITED` reason code is a labeling refinement, not a safety fix (it
would touch `REASON_CODES` and the "exactly 6 codes" test — deliberately NOT
done here to avoid weakening an existing assertion). Paid-fabric side already
refuses OBSERVED escalation under cooldown/rate-limit (cited). MODEL_LIMITED
continuity already forbids auto-retry/account switch (cited). Remaining:
the admission/retry loop that could silently cross accounts AFTER a possible
effect lives in `executive_runtime` — design with NM-07/C below.

### NM-10 update_paused/drain (GAP — no in-repo boundary)
`update_paused` appears nowhere in this repository; the pause switch and the
restart temptation both belong to the Hermes gateway / T3 desktop process,
outside any module I may test. Honest finding: no mutation boundary exists
here to attack. Closest in-repo law (cited above): an allocator under
pressure must REFUSE (typed `ALLOCATIONS_BLOCKED_DISK_PRESSURE`) — the lease
module provably contains no restart/sweep primitive at all
(`test_no_second_sweeper_no_deletion_anywhere`). Design for A3/B: fake
gateway reporting `update_paused`; adapter must surface a typed
paused/blocked label, and the test asserts zero reconnect/restart attempts
(connection-attempt count stays 0/1) across N polls — no service restart to
evade the pause.

### NM-16 green-but-unmerged (PARTIAL — python proven; UI stage with D)
Python boundary proven: an OPEN unmerged PR whose only "green" fact is CI can
never read as integrated — the facts grammar cannot even express CI greenness
(`ci`/`checks`/`status` field-name pin), so integration knowledge enters only
via `integration_state`, and NOT_INTEGRATED/UNKNOWN both force
RECONCILE_REQUIRED with distinct issues. Remaining §6 wording — "UI reports
the real stage" — is the TSX stage renderer (D-owned). Design for D: component
test feeding `IntegrationState.NOT_INTEGRATED` + green check-run facts;
assert rendered stage ≠ any installed/merged vocabulary; assert
UNKNOWN renders "unknown", never "green/healthy".

### NM-17 role switch (PARTIAL — python proven; TS session store with B/D)
Python transport proven: a role context never guesses/falls back, another
family can never answer the original send, a valid result must match the
exact send target, a foreign native session is refused before projection,
and another home's gateway never qualifies as this profile's readiness
(cited). Remaining: cross-profile session/memory leak inside the TS session
store (B: hermes-native runtime state; D: any UI-held profile memory).
Design for B/D: switch profile A→B with an in-flight turn; assert no
A-session handle, memory entry, or cached answer is reachable from B's
renderer/session store (deep-equal snapshot of stores before/after).

### NM-19 sign-out mid-turn (PARTIAL — free guard proven; fences with D)
`auth-navigation-guard` proves the free boundary: an explicit logout marker
is a security boundary distinct from passive expiry, automatic sign-in is
gated on owner holds, and localStorage errors fail CLOSED (3 tests, run this
session). Remaining §6 wording — renderer fences so an in-flight turn cannot
emit wrong-principal output — lives in TSX render paths (D-owned). Design for
D: fire an explicit sign-out while a result write from the previous principal
is queued; assert the write is dropped/labelled, never attributed to the new
principal; storage-error case must fence, not skip.

## Row detail — OWNED_BY_RUNNING_DIRECTOR designs

### NM-01 restart before ACK (A3)
Existing single-process proof passes (`test_crash_before_ack_replays_same_key_and_namespace`).
The audit's authoritative BLOCKER (#1/inv1) is the TWO-CONNECTION race. Design:
two adapter processes (or one process + second `start()` call on a fresh
adapter sharing the state store) race `start(spec)` against one gateway lease
with interleaving forced after the durability write but before the ACK read;
assert exactly one launch reaches the gateway (counting fake port), the loser
returns the winner's thread ref (not a second thread), launch-count ledger
reads 1. Assert the state store's `clear_launch_attempt` path
(`test_clear_launch_attempt_refuses_when_a_receipt_exists` exists) cannot
reset the ledger while a receipt exists.

### NM-02 restart after ACK (A3)
Existing single-process proof passes (`test_restart_reattaches_same_thread_with_launch_count_one`
+ foreign-thread/foreign-key refusals). Complete inv1 by extending the same
race to the post-ACK window: winner ACKs and writes receipt; a second process
starting concurrently must REPLAY (same key/namespace) and observe
launch_count 1 with no second `start` on the port. Audit #1 stays open until
this two-process form exists.

### NM-03 cursor monotonicity (A3)
Existing test proves round-trip survival, not monotonicity. Design: replay
the event ledger with a persisted cursor at offset N; feed a forged/reordered
stream where the next event carries offset < N; assert refusal (typed) or
no-op with cursor unchanged — never a backwards move; then a valid N+1 event
advances exactly once. Include the cancel-ledger analogue (a cancel replay
for an already-cancelled run must be idempotent, not a second cancel).

### NM-07 admission-timeout receipt lookup (C)
Design (against `executive_runtime` public admission API with a fake
transport): (1) submit admission A (triple T1, digest D1); swallow the reply
before the UI sees it; (2) re-submit T1/D1 → the SAME Job comes back
(replay), `attempt_count` stays 1, total Jobs for the root == 1; (3) submit
T1 with a different digest → typed digest-conflict refusal, still one Job;
(4) concurrent double-submit (thread barrier) → exactly one Job, loser gets
the replay receipt with identical identity, never a partial second attempt;
(5) UI-timeout path performs receipt lookup by triple (no new Job minted).
This also discharges the §6 "no silent cross-account fallback after a
possible effect" clause of NM-09: after an EFFECT_UNKNOWN admission, a
re-route to another account/provider must be refused at this boundary
(typed), with the observation layers (already proven) supplying WAIT/UNKNOWN.

### NM-08 wrong OAuth client/namespace (A3)
Existing attesting-path proof passes (`test_restart_under_a_different_namespace_is_refused`).
Close audit inv2/#3 fail-open: (1) replay the idempotency key under client B
where B's port does NOT attest its namespace → must REFUSE (fail closed), not
proceed unattested; (2) two clients with the same logical_child_key must
never collide on one receipt — assert distinct receipt namespaces and a
refusal when B claims A's key; (3) explicit re-auth path returns a typed
re-auth-required label, never a silent merge.

### NM-11 DSH fanout envelope (lane A)
Design against `dsh_acp_runtime` public fanout API with fake envelopes:
(1) parent at envelope limit (8 active, depth 1): a 9th concurrent child
claim is refused with the envelope reason (no silent queue-drain into
execution); (2) depth-2 attempt (child of child) refused structurally;
(3) counterfeit test: a child claim that arrives carrying its OWN envelope
slots (attempting to impersonate an independently placed child) must have
those slots ignored/refused — admission only against the parent's reservation
(the free-side law it must match is `test_bounded_native_fanout_parent_reserves_envelope_and_children_skip`).

### NM-14 duplicate/concurrent admissions (C)
Covered by NM-07 design steps (3)–(4): concurrent identical triple → one Job
(atomic counts, replay receipt to the loser); digest conflict → typed
refusal; assert persisted counters (`attempt_count`, admission count) never
increment twice for one triple. Storage-layer atomicity law already proven at
`test_concurrent_acquire_single_writer_one_winner_precise_conflict` (cited as
the pattern to replicate at the admission boundary).

### NM-15 #2329 shell shapes (C)
The existing suite (`tests/test_provider_orchestrator_policy.py`, full pass
this session) already locks the current shape grammar. Designs for the
remaining adversarial edges: (1) a NOVEL unlisted shell shape (new flag
combination not in the fixture set) → structural refusal, NOT matched by
nearest-allowlist entry; (2) allowlist-bypass attempt: shape that
string-matches an allowed pattern after normalization (whitespace/case/
unicode homoglyph) → refused pre-normalization equivalence; (3) allowlist
mutation at runtime (attempt to append an entry via any public API) → no
such mutation path exists (assert on public surface).

## Pre-existing failure (recorded, not caused by this lane)

`tests/test_provider_quota_observation.py::test_producer_without_observations_path_is_byte_identical_to_before`
fails on the clean branch (produced preview document ≠ normalized golden at
tests/test_provider_quota_observation.py:489). It is a golden-byte drift in
the quota-economics preview producer, unrelated to any §6 row and untouched
by this lane's edits. Left as-is (fixing it would mean regenerating a golden
owned outside this assignment); flagged for the module's owning lane.
