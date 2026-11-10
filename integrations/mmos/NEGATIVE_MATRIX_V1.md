# MMOS V1 — Negative-Case Matrix (§6), V1 (2026-11-10 L5 update)

One row per §6 failure case of `~/.hermes/profiles/engineering/mmos/T3_HANDOFF_V2.md`
(read-only), split per assignment for compound rows: coordinator restart →
before/after ACK (NM-01/02); gateway busy vs disconnected vs stopped → three
rows (NM-04/05/06). V1 (Director H) proved 6/20 with 5 PARTIAL, 1 GAP and 8
rows owned by then-running director lanes. This update (lane L5, hardening +
proof, operating method V2) closes the matrix: the A3/C-owned designs landed
on the trunk and are now cited with their real tests; the remaining source
gaps were closed by L5 leaves; every cited test was run this session on this
branch.

Verification environment (this branch, this session):
`env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q <file>`;
vitest via `cd app/mastermind_os && npx vitest run <file>` (node_modules
installed via `npm ci`). TS evidence suites were run this session too.

Status legend — `PROVEN_BY_TEST`: a real adversarial test at the exact
mutation boundary exists, was run, and passes. `LIVE_ONLY`: the remaining
proof needs a live service step named in the row; the closest source-level
law is proven and cited.

## Totals

| Status | Rows | Count |
|---|---|---|
| PROVEN_BY_TEST | NM-01 … NM-09, NM-11 … NM-20 | 19 |
| PROVEN_BY_TEST (source) + LIVE_ONLY remainder | NM-10 | 1 |
| **Total** | | **20** |

New L5 tests this pass: `tests/test_mmos_nm06_gateway_stopped.py` (4),
`tests/test_mmos_nm09_nm10.py` (4), `tests/test_guard_r13_documented_limits.py`
(2, the REVIEW9 r13 MINORs pinned as documented limits). Product fix:
`hermes_native_continuity` gained the `gateway_stopped` state (§6 "distinct
labels" — previously a real gap, pinned by strict-xfail tripwire).

## Matrix

| Row | §6 failure case | Mutation boundary (exact) | Owning module(s) | Adversarial tests (run this session) | Status |
|---|---|---|---|---|---|
| NM-01 | Coordinator restart BEFORE ACK — launch count stays 1, original namespace recovered | `SQLiteT3AdapterStateStore.claim_launch_intent` atomic claim (audit #1 BLOCKER fixed: `ON CONFLICT DO NOTHING` in `BEGIN IMMEDIATE`; claimant-conditional clear) | `control_plane/t3_execution_adapter.py` | `tests/test_t3_adapter_durability.py::test_nm01_two_connections_race_start_exactly_one_launch`, `::test_nm01_two_processes_race_start_exactly_one_launch`, `::test_clear_launch_attempt_refuses_when_a_receipt_exists`, `::test_clear_launch_attempt_is_claimant_conditional` — PASS | PROVEN_BY_TEST |
| NM-02 | Coordinator restart AFTER ACK — launch count stays 1, same thread | start-reattach idempotency; loser replays the winner's receipt | same | `…::test_nm02_loser_during_in_flight_launch_replays_the_winner`, `…::test_restart_reattaches_same_thread_with_launch_count_one`, `…::test_replay_returning_a_different_thread_is_refused`, `…::test_replay_receipt_echoing_a_foreign_key_is_refused` — PASS | PROVEN_BY_TEST |
| NM-03 | Restart recovery cursor never goes backwards | `_merge_cursor` rank gate; cancel ledger replay | same | `…::test_nm03_cursor_never_moves_backwards_across_writers`, `…::test_nm03_status_read_with_empty_or_lower_cursor_never_rewinds`, `…::test_cursor_and_cancel_ledger_survive_restart` — PASS | PROVEN_BY_TEST |
| NM-04 | Viewer disconnect mid-run — same thread/cursor, no new thread | `classify_native_continuity` / `classify_error_code` | `integrations/session_bridge/hermes_native_continuity.py` | `tests/test_session_bridge_native_continuity.py::TestNativeResults::test_not_submitted_and_unavailable_are_viewer_disconnected`, `::TestPermittedContinuations::test_only_idle_permits_a_fresh_send` — PASS | PROVEN_BY_TEST |
| NM-05 | Gateway BUSY — distinct label, no auto-retry/remake | busy-code table; `permitted_continuations(GATEWAY_BUSY)` | same | `…::TestErrorCodes::test_busy_pending_and_viewer_codes_stay_distinct`, `…::TestNativeResults::test_quiet_session_snapshot_is_idle_and_busy_snapshot_is_not` — PASS | PROVEN_BY_TEST |
| NM-06 | Gateway DISCONNECTED vs STOPPED — distinct labels | `_STOPPED_CODES` closed table → `GATEWAY_STOPPED` state (L5 product fix; was UNCLASSIFIED, strict-xfail tripwire) | same (TS mirror display parity → L2) | NEW `tests/test_mmos_nm06_gateway_stopped.py` (distinct label; read/status-only continuations; stopped-beats-pending; both codes; busy/viewer/auth/unknown regression pins) — PASS; `tests/test_mmos_negative_matrix.py::test_nm06_gateway_stopped_needs_a_label_distinct_from_busy_and_disconnected` (xfail REMOVED, now asserts and passes), `::test_nm06_stopped_code_is_typed_gateway_stopped_and_offers_no_mutation` — PASS | PROVEN_BY_TEST |
| NM-07 | Admission succeeded but UI timed out — receipt lookup, no duplicate Job | admission idempotency triple + digest (`compose_child_execution`) | `control_plane/child_request_execution_composition.py`, `executive_runtime.py` | `tests/test_mmos_admission_to_t3_native_e2e.py::test_nm07_admission_ui_timeout_receipt_lookup_no_duplicate` — PASS | PROVEN_BY_TEST |
| NM-08 | Wrong OAuth client / namespace — two clients NEVER the same idempotency key | namespace attestation on launch/replay/reattach (audit #3 fail-open closed: unattested ports refused) | `control_plane/t3_execution_adapter.py` | `tests/test_t3_adapter_durability.py::test_nm08_unattested_port_cannot_launch`, `::test_nm08_unattested_port_cannot_reattach_a_principal_scoped_run`, `::test_nm08_unattested_port_cannot_replay_a_crash_zone_intent`, `::test_restart_under_a_different_namespace_is_refused`; `tests/test_t3_execution_adapter.py::test_other_oauth_client_is_refused_with_zero_mutating_calls` — PASS | PROVEN_BY_TEST |
| NM-09 | 429/quota — WAIT/UNKNOWN/REFUSED, no silent cross-account fallback after a possible effect | observation layers + admission/execution arbitration after an effect-unknown launch | `provider_quota_observation.py`, `paid_fabric_capacity.py`, composition + adapter | NEW `tests/test_mmos_nm09_nm10.py::test_nm09_effect_unknown_then_different_route_is_refused_no_second_job` (lose-ACK start → `T3LaunchEffectUnknownError`, intent retained; different-route replacement → REPLAY, no new Job, original route survives, ONE launch envelope forever; same-principal replay recovers the ORIGINAL thread), `::test_nm09_effect_unknown_never_switches_account_at_the_adapter` (other OAuth client: `T3LaunchClaimConflictError` before any native call; reattach → `PRINCIPAL_MISMATCH`; persisted intent still names the original principal) — PASS; free layers: `test_nm09_rate_limited_429_is_typed_unknown_never_healthy_numbers`, `test_paid_fabric_capacity.py` + `native_continuity` MODEL_LIMITED never-retry rows (V1 citations, re-run) — PASS. Observation for the RC review: a route-only change under the same triple reconciles silently as REPLAY (the digest covers the request envelope, not the spec route); the no-fallback invariant is carried by one-Job-per-triple arbitration plus the claimed binding pinning the launch — pinned end-to-end by the new test | PROVEN_BY_TEST |
| NM-10 | update_paused/drain — no service restart to evade | no in-repo switch (gateway-owned); closest source laws | `hermes_native_continuity.py`, `t3_execution_adapter.py` | NEW `tests/test_mmos_nm09_nm10.py::test_nm10_continuation_vocabulary_has_no_restart_or_reconnect` (every classified state's operations ⊆ {recover, read, status, send}; send only from IDLE; recover only for EFFECT_UNKNOWN; no continuation key/value can name restart/reconnect/remake/resubmit/relaunch), `::test_nm10_outage_produces_typed_errors_and_never_relaunches` (5× status under outage → typed errors, launch_count stays 1, replay_count 0, original thread only, cursor never advances) — PASS. LIVE_ONLY remainder (exact step): flip the live Hermes gateway's `update_paused` drain switch with a live adapter session and observe the typed label with zero reconnect/restart attempts across N polls | PROVEN_BY_TEST (source) + LIVE_ONLY |
| NM-11 | DSH fanout at envelope limit — in-process 8-active/depth-1, cannot counterfeit an independently placed child | `DshDescendantPolicy` construction + enforcement; lineage chain | `control_plane/dsh_acp_runtime.py` | `tests/test_dsh_acp_runtime.py::test_observed_children_account_inside_the_envelope` (9th child → violation), `::test_two_level_chain_carries_the_same_root_to_the_grandchild` + `::test_lineage_refuses_re_rooting_and_level_skips` (depth-2 refused structurally), `::test_per_child_reservation_on_a_bounded_lane_is_double_counting` + `::test_reserve_descendant_slot` rows (counterfeit per-child slots refused), `::test_policy_is_bounded_native_fanout_chosen_by_evidence`; free-side envelope law `tests/test_fabric_placement_policy.py::test_bounded_native_fanout_parent_reserves_envelope_and_children_skip` — PASS | PROVEN_BY_TEST |
| NM-12 | Parent+child host slots — no double envelope/overcommit | `fabric_placement_policy` headroom/envelope/descendant admission | `control_plane/fabric_placement_policy.py` | `tests/test_fabric_placement_policy.py::test_parent_claim_reserves_only_its_own_slot`, `::test_headroom_blocks_parents_from_the_last_reserved_child_slots`, `::test_child_headroom_blocks_a_parent_but_never_a_child`, `::test_fanout_envelope_reserved_at_parents_host_until_settlement`, `::test_descendant_cap_blocks_the_n_plus_oneth_concurrent_child` — PASS | PROVEN_BY_TEST |
| NM-13 | Stale lease — blocks NEW execution; exact-run cancel still allowed | `WorkspaceLeaseStore.acquire_single_writer` / `release` epoch gate / `reclaim_eligible`; adapter cancel with expired binding | `control_plane/workspace_lease.py`, `t3_execution_adapter.py` | `tests/test_mmos_negative_matrix.py::test_nm13_stale_lease_blocks_new_execution_and_only_the_exact_writer_retires`, `::test_nm13_expiry_alone_is_never_reclaim_safety_settlement_is`; `tests/test_workspace_lease.py::test_one_writer_per_mutable_checkout`, `::test_concurrent_acquire_single_writer_one_winner_precise_conflict`; `tests/test_t3_execution_adapter.py::test_cancel_allowed_with_expired_binding_lease` — PASS | PROVEN_BY_TEST |
| NM-14 | Duplicate/concurrent admissions — replay vs digest-conflict, atomic counts | admission transaction (triple + digest); concurrent composition | `child_request_execution_composition.py`, `executive_runtime.py` | `tests/test_mmos_admission_to_t3_native_e2e.py::test_nm14_replayed_handoff_never_mints_a_second_job_or_launch`, `::test_nm14_different_digest_same_triple_is_typed_conflict`, `::test_nm14_concurrent_composition_is_atomic_one_job` (thread barrier, one Job) — PASS | PROVEN_BY_TEST |
| NM-15 | #2329 shell shapes — structural refusal, no allowlist bypass | `ops/executive_os/provider_orchestrator_guard.py` r13 (ACCEPT, re-check #9) | guard (closed; docs+pins only) | `tests/test_provider_orchestrator_policy.py` full suite (1299 incl. r12/r13 structural tables, `test_r12_mutation_fuzz_has_no_armed_or_scanner_escape`, `test_r11_mutation_fuzz_has_no_sealed_shell_escape`, homoglyph pinned doc-limit); `tests/test_mmos_admission_to_t3_native_e2e.py::test_nm15_shell_shapes_refused_with_a_valid_claimed_binding`, `::test_nm15_lawful_direct_shape_reaches_the_binding_gate` — PASS; NEW `tests/test_guard_r13_documented_limits.py` pins the two REVIEW9 MINORs (below) | PROVEN_BY_TEST |
| NM-16 | Green-but-unmerged/uninstalled — real stage reported | `github_pr_lifecycle.assess_pr_lifecycle` (py) + execution-return stage grammar (TS) | `control_plane/github_pr_lifecycle.py`; TS contract mirror | py: `tests/test_github_pr_lifecycle.py::test_known_terminal_work_with_unknown_integration_has_distinct_issue`, `tests/test_mmos_negative_matrix.py::test_nm16_green_but_unmerged_never_reports_integrated_or_closable` — PASS. TS: `app/mastermind_os/src/hermes-native/execution-return-contract.test.ts` ("advances only as far as evidence proves; unknown never green", "refuses a re-forged consistent record whose stage outruns its evidence", Python-fixture vocabulary equality) + `src/projects/ProjectDeliveryPanel.test.tsx` — PASS (vitest, this session) | PROVEN_BY_TEST |
| NM-17 | Role switch — no cross-profile session/memory leak | python role transport binding + foreign-session refusal; TS conversation state | `integrations/session_bridge/hermes_native.py`, `control_plane/native_continuation.py`; TS panel | py: `tests/test_mastermind_os_native_role_transport.py::test_unsupported_older_peer_never_selects_another_role`, `::test_other_valid_native_family_cannot_answer_the_original`, `::test_valid_native_result_still_must_match_the_exact_send_target`; `tests/test_hermes_primary_session_return.py::test_foreign_native_session_is_refused_before_observation_projection`; `tests/test_team_roster_projection.py::TestGatewayEvidence::test_identify_beats_lock_and_home_mismatch_never_qualifies` — PASS. TS: `src/hermes-native/HermesNativePanel.test.tsx` "clears private conversation state when authentication changes" + "reconnects after a proven before-dispatch auth change without inventing an uncertain send" — PASS (vitest, this session) | PROVEN_BY_TEST |
| NM-18 | Unknown host/thermal/quota — shown unknown, never healthy/zero | `t3_environment_projection` honesty rules; `paid_fabric_capacity` offline; `executive_host_capacity` zero-vs-unknown | free modules cited in V1 | `tests/test_t3_environment_projection.py::test_missing_observation_facts_are_unknown_never_ready`, `::test_thermal_unknown_propagates_and_blocks_eligibility`, `::test_projection_refuses_forged_eligibility`; `tests/test_paid_fabric_capacity.py::test_membership_unknown_never_fabricates_facts`; `tests/test_executive_host_capacity.py::test_observed_zero_is_valid_only_after_successful_observation` — PASS | PROVEN_BY_TEST |
| NM-19 | Sign-out mid-turn — renderer fences, no wrong-principal output | `auth-navigation-guard.ts` (free) + renderer fences (TSX) | `app/mastermind_os/src/auth-navigation-guard.ts`; App work-recovery path | guard: `src/auth-navigation-guard.test.ts` (3: explicit-logout marker ≠ passive expiry; automatic sign-in gated on owner holds; fail-closed on storage errors) — PASS. Renderer: `src/App.work-recovery.test.tsx::"aborts the retried read on sign-out and ignores its late result"` (sign-out aborts the in-flight read; the late result is dropped, never rendered), `::"uses the actual native read adapter and rejects a retry result from an older same-label auth epoch"` — PASS (vitest, this session) | PROVEN_BY_TEST |
| NM-20 | Child returns — parent consumption + explicit CONTINUE/STOP, no orphan wave | `fabric_stop_return.prepare_stop` write-once receipts; `validate_public_result` (`parent_consumed` mandatory False) | free modules cited in V1 | `tests/test_fabric_stop_return.py::test_at_most_one_attempt_even_after_uncertain_delivery`, `::test_exclusive_receipt_creation_race_does_not_duplicate`, `::test_failed_durability_does_not_emit_or_allow_replay`; `tests/test_fabric_reject_outcome.py::test_repeat_refuses_without_second_write`, `::test_unconfirmed_write_never_becomes_accepted_or_retry_permission`; `tests/test_hermes_primary_session_return.py::test_current_original_reader_preserves_answer_and_identity` — PASS | PROVEN_BY_TEST |

## Guard #2329 — lane closed; REVIEW9 MINORs pinned as documented limits

Re-check #9 (`REVIEW9_GUARD_R13_OPUS_20261110.md`) returned ACCEPT on r13.
Per the review rule in `OPERATING_METHOD_V2.md` there is no r14; the two
MINORs are pinned by `tests/test_guard_r13_documented_limits.py` and the
guard module docstring now carries a "Documented limits (r13, REVIEW9
re-check #9)" block (docstring only — zero behaviour change, unarmed
byte-identity unaffected, no sha256 pin moved):

- MINOR #1 (`env -S` escape decoding): the sealed-shell-proven spellings
  (sq: three literal backslashes; dq: five — the outer double quotes collapse
  `\\`→`\` before env -S decodes) launch the fake wrapper in both zsh and
  bash while armed r13 allows them unjudged (construct-free, literally
  unnamed). Pinned allow/gate-unreached with sealed-launch proof; the NAMED
  `env -S 'pool …'` form is pinned refused `R6_PREFIX_FORM`.
- MINOR #2 (escaped-quote-before-newline over-refusal): the six REVIEW9 §C
  shapes pinned deny/deny with the gate unreached (structural, assembled
  continuation); the honest single-line control
  `git commit -m "Fix \"quoted\"⏎⏎Body"` pinned allow (in scope, admitted).

## Row notes

- NM-06 product fix scope: `hermes_native_continuity` (classification
  vocabulary) only. The TS mirror (`hermes-native/continuity.ts`) display
  parity member is a one-line L2 follow-up; the row's classification law is
  proven python-side.
- NM-09 observation for the release-candidate CRITICAL review: route-only
  changes under the same admission triple reconcile as REPLAY without a
  typed route-conflict (digest covers the request envelope, not the spec
  route). Not a bypass — one-Job-per-triple arbitration plus the claimed
  binding pinning the launch are what enforce no-fallback, now pinned
  end-to-end — but worth a reviewer's eye at the RC bundle.
- NM-10 is the only LIVE_ONLY remainder in the matrix: the exact live step
  is flipping the Hermes gateway `update_paused` drain switch against a
  live adapter session and observing the typed label with zero
  reconnect/restart attempts. Source-side, the vocabulary cannot express a
  restart and the adapter provably never re-launches under outage.

## Pre-existing failure note (V1) — RESOLVED

V1 recorded `tests/test_provider_quota_observation.py::test_producer_without_observations_path_is_byte_identical_to_before`
as a clean-branch failure. It PASSES on the current trunk head this session
(fixed upstream since V1 was written); the note is closed.
