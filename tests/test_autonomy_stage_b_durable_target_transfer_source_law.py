from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json_block(text: str, begin: str, end: str) -> dict[str, object]:
    pattern = re.compile(
        re.escape(begin) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(end),
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"missing JSON block {begin}"
    value = json.loads(match.group(1))
    assert isinstance(value, dict)
    return value


def _text_block(text: str, begin: str, end: str) -> tuple[str, ...]:
    pattern = re.compile(
        re.escape(begin) + r"\s*```text\s*(.*?)\s*```\s*" + re.escape(end),
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"missing text block {begin}"
    return tuple(line.strip() for line in match.group(1).splitlines() if line.strip())


def test_stage_b_records_are_real_and_completion_honesty_is_explicit() -> None:
    assert DESIGN.is_file()
    assert PLAN.is_file()
    design = _read(DESIGN)
    plan = _read(PLAN)

    assert "autonomy-stage-b-durable-target-transfer-f0-20260901-sol-001" in design
    assert "autonomy-stage-b-durable-target-transfer-f0-20260901-sol-001" in plan
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in design
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in plan
    assert "The correct pre-wave state is `NOT_BUILT`" in plan
    assert "does not make Stage B built" in design
    assert "Only that real path can promote the capability toward `PROVEN_LIVE`" in plan


def test_machine_contract_reuses_existing_runtime_event_owners_and_creates_no_store() -> None:
    contract = _json_block(
        _read(DESIGN),
        "<!-- STAGE_B_F0_CONTRACT_BEGIN -->",
        "<!-- STAGE_B_F0_CONTRACT_END -->",
    )

    assert contract["schema"] == "mastermind.autonomy_stage_b_f0_contract.v1"
    assert contract["records_wave"] == "STAGE-B0"
    assert contract["first_implementation_wave"] == "STAGE-B1"
    assert contract["records_state_after_merge"] == (
        "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED"
    )
    assert contract["event_aggregate_type"] == "job"
    assert contract["event_types"] == [
        "SOL_ACTION_TARGET_ASSIGNED",
        "SOL_ACTION_TARGET_TRANSFERRED",
    ]
    assert contract["transaction_owner"] == (
        "control_plane.executive_runtime.RuntimeStore.transaction"
    )
    assert contract["event_append_owner"] == (
        "control_plane.executive_runtime.RuntimeStore.append_event"
    )
    assert contract["replay_lookup_owner"] == (
        "control_plane.executive_runtime.RuntimeStore.get_event_by_command_id"
    )
    assert contract["binding_read_owner"] == (
        "control_plane.executive_runtime.Runtime.current_harness_binding_source"
    )
    assert contract["command_reconciliation_order"] == "BEFORE_MUTABLE_STATE_READ"
    assert contract["new_tables"] == []
    assert contract["new_migrations"] == []
    assert contract["new_registries"] == []
    assert contract["runtime_binding_rows_mutated"] is False
    assert contract["job_attempt_worker_rows_mutated"] is False
    assert contract["provider_calls_in_transaction"] is False
    assert contract["slack_calls_in_transaction"] is False
    assert contract["ack_written_by_stage_b"] is False
    assert contract["source_resolution_written_by_stage_b"] is False
    assert contract["production_armed_in_stage_b1"] is False


def test_transfer_modes_and_evidence_gates_are_closed() -> None:
    contract = _json_block(
        _read(DESIGN),
        "<!-- STAGE_B_F0_CONTRACT_BEGIN -->",
        "<!-- STAGE_B_F0_CONTRACT_END -->",
    )

    assert contract["transfer_modes"] == [
        "INITIAL_ASSIGNMENT",
        "SAME_ALIAS_GENERATION_SUCCESSION",
        "CROSS_ALIAS_RESPONSIBILITY_TRANSFER",
    ]
    assert contract["required_evidence_by_mode"] == {
        "INITIAL_ASSIGNMENT": [
            "authority_source_ref",
            "destination_materialization_event_command_id",
            "destination_ack_event_command_id",
        ],
        "SAME_ALIAS_GENERATION_SUCCESSION": [
            "authority_source_ref",
            "source_release_event_command_id",
            "destination_materialization_event_command_id",
            "destination_ack_event_command_id",
        ],
        "CROSS_ALIAS_RESPONSIBILITY_TRANSFER": [
            "authority_source_ref",
            "source_terminal_event_command_id",
            "source_release_event_command_id",
            "destination_materialization_event_command_id",
            "destination_ack_event_command_id",
        ],
    }
    assert contract["command_id_derivation"] == (
        "SOL-TARGET-<first-32-hex-of-sha256-canonical-command-semantics>"
    )


def test_persisted_target_identity_is_stable_and_secret_safe() -> None:
    contract = _json_block(
        _read(DESIGN),
        "<!-- STAGE_B_F0_CONTRACT_BEGIN -->",
        "<!-- STAGE_B_F0_CONTRACT_END -->",
    )

    assert contract["persisted_target_identity_fields"] == [
        "attempt_id",
        "binding_generation",
        "binding_id",
        "reasoning_surface",
        "session_alias",
        "session_epoch_id",
    ]
    assert contract["forbidden_persisted_target_fields"] == [
        "account_label",
        "native_handle",
        "provider_session_id",
        "raw_model_output",
        "slack_principal",
    ]
    design = _read(DESIGN)
    assert "The caller supplies expected semantic identity" in design
    assert "comparison claims, not privileged facts" in design
    assert "never raw provider or model output" in design


def test_stage_a_remains_the_real_consumer_without_signature_or_election_widening() -> None:
    contract = _json_block(
        _read(DESIGN),
        "<!-- STAGE_B_F0_CONTRACT_BEGIN -->",
        "<!-- STAGE_B_F0_CONTRACT_END -->",
    )

    assert contract["logical_target_owner"] == (
        "control_plane.session_targets.SessionTargetRegistry.root_job_bindings"
    )
    assert contract["logical_target_projection"] == (
        "control_plane.session_targets.SessionTargetRegistry.with_root_job_bindings"
    )
    assert contract["stage_a_consumer"] == (
        "control_plane.sol_action_target.resolve_sol_action_target"
    )
    assert contract["stage_a_resolver_signature_changed"] is False

    design = _read(DESIGN)
    for rejected in (
        "newest wall clock time",
        "Newest generation wins",
        "Slack principal is never a RuntimeBinding",
        "account identity alone never selects one",
    ):
        assert rejected in design
    assert "A successful Stage-B event is not itself an" in design
    assert "authority token" in design


def test_transaction_order_is_command_first_same_connection_and_single_append() -> None:
    design = _read(DESIGN)
    numbered = [
        "1. derive canonical command semantics and stable command_id",
        "2. RuntimeStore.transaction() -> BEGIN IMMEDIATE",
        "3. get_event_by_command_id(command_id, connection=tx)",
        "10. read destination admitted binding facts using current_harness_binding_source(..., connection=tx)",
        "14. append exactly one immutable Stage-B event with RuntimeStore.append_event(..., connection=tx)",
        "15. COMMIT",
    ]
    positions = [design.index(item) for item in numbered]
    assert positions == sorted(positions)
    assert "At most" in design
    assert "one can append revision N+1" in design
    assert "does not silently rebase itself onto N+1" in design


def test_expected_stage_b1_surface_is_exact_and_duplicate_owners_are_protected() -> None:
    paths = _text_block(
        _read(DESIGN),
        "<!-- STAGE_B1_EXPECTED_PATHS_BEGIN -->",
        "<!-- STAGE_B1_EXPECTED_PATHS_END -->",
    )
    assert paths == (
        "control_plane/sol_action_target_transfer.py",
        "control_plane/executive_runtime.py",
        "tests/test_sol_action_target_transfer.py",
        "tests/test_sol_action_target.py",
        "tests/test_executive_runtime.py",
    )
    design = _read(DESIGN)
    for protected in (
        "control_plane/session_targets.py",
        "control_plane/runtime_binding_projection.py",
        "control_plane/wake_ack_ingress.py",
        "all provider adapters and materializers",
        "all Capacity / Model Router / Worker Browser paths",
    ):
        assert protected in design
    assert "new table, migration, target registry, RuntimeBinding owner" in design


def test_implementation_order_is_complete_and_release_bounded() -> None:
    order = _text_block(
        _read(PLAN),
        "<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->",
        "<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->",
    )
    assert order == (
        "1. RE-PIN_AND_COLLISION_FREEZE",
        "2. RED_COMMAND_EVENT_AND_FOLD_TESTS",
        "3. IMPLEMENT_CLOSED_TYPES_CANONICALIZATION_AND_PROJECTOR",
        "4. RED_RUNTIME_TRANSACTION_AND_REPLAY_TESTS",
        "5. IMPLEMENT_EXISTING_RUNTIMESTORE_TRANSACTION_SEAM",
        "6. RED_STAGE_A_REAL_CONSUMER_TESTS",
        "7. INTEGRATE_ROOT_BINDING_OVERLAY_WITH_UNCHANGED_STAGE_A_RESOLVER",
        "8. RED_CONCURRENCY_EFFECT_UNKNOWN_AND_SECRET_TESTS",
        "9. RUN_MUTATION_AND_FORBIDDEN_PLANE_PROOF",
        "10. RUN_FOCUSED_ADJACENT_FULL_FEASIBLE_AND_STATIC_GATES",
        "11. PUBLISH_ONE_DRAFT_HOLD_CARRIER",
        "12. INDEPENDENT_EXACT_HEAD_REVIEW_AND_HOSTED_CI",
        "13. SOL_RELEASE_ADJUDICATION",
    )
    plan = _read(PLAN)
    assert "BUILT_NOT_PROVEN / TRANSFER_SOURCE_PRODUCTION_DISARMED / PROTECTED" in plan
    assert "No worker-facing open pickup is emitted" in plan
    assert "PLACEMENT_STATE: WAITING_CAPACITY / needs_placement" in plan


def test_adverse_matrix_discriminates_replay_revision_readiness_and_no_mutation() -> None:
    design = _read(DESIGN)
    plan = _read(PLAN)

    for required in (
        "identical replay returns one existing event",
        "changed semantics under the same command identity conflict",
        "response-loss replay succeeds after later target movement",
        "two concurrent revision-N transfers produce one event",
        "multiple current RuntimeBindings",
        "destination materialization or ACK missing refuses",
        "Job, Attempt, Worker, RuntimeBinding, ACK, source-resolution and provider state are byte/row",
        "real Stage-A resolver grants authority to the exact destination",
    ):
        assert required in design

    for mutation in (
        "command-first lookup",
        "expected revision compare",
        "same-transaction binding read",
        "destination ACK gate",
        "actor check in Stage A",
        "forbidden-field filter",
    ):
        assert mutation in plan


def test_stage_b_does_not_absorb_adjacent_capabilities_or_production_proof() -> None:
    plan = _read(PLAN)
    design = _read(DESIGN)

    for non_goal in (
        "no provider process/session creation",
        "no Capacity selection or placement commitment",
        "no target pointer/current-target table",
        "no Control Room UI work",
        "no automatic context rollover",
        "no production route, installer, service, credential, or deployment",
    ):
        assert non_goal in plan

    assert "Stage B does not mark the old binding non-current" in design
    assert "Stage B consumes a canonical ACK event; it does not author acknowledgement" in design
    assert "No provider creation, live context rotation, live responsibility transfer" in design
