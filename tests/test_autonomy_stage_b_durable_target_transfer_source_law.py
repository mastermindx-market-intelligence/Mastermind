from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md"
CEO_INTENT = ROOT / "control_plane" / "ceo_intent.py"
EXECUTIVE_RUNTIME = ROOT / "control_plane" / "executive_runtime.py"
EXECUTIVE_SERVICE = ROOT / "control_plane" / "executive_service.py"
RUNTIME_BINDING = ROOT / "control_plane" / "runtime_binding_projection.py"
STAGE_A = ROOT / "control_plane" / "sol_action_target.py"
TARGETS = ROOT / "config" / "wake_session_targets.json"
BEGIN = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->"
END = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->"
GATE_BEGIN = "<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->"
GATE_END = "<!-- STAGE_B1_CORRECTION_GATE_END -->"
SHA = "0d5c80bba8c69b5d1ed86aa3d32c9003a4252c73"
REVISION = "v5.2-claim-then-materialize-binding"
RECORD_PATHS = [
    "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md",
    "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md",
    "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py",
]
SOURCE_PATHS = [
    "control_plane/executive_runtime.py",
    "control_plane/runtime_binding_projection.py",
    "control_plane/sol_action_target_assignment.py",
    "control_plane/executive_service.py",
    "tests/test_autonomy_stage_b_initial_assignment.py",
    "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def json_block(path: Path, begin: str, end: str) -> tuple[dict[str, Any], str]:
    match = re.search(
        re.escape(begin) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(end),
        read(path),
        re.S,
    )
    assert match, f"missing contract in {path}"
    value = json.loads(match.group(1))
    assert isinstance(value, dict)
    return value, match.group(1)


def validate_contract(contract: dict[str, Any]) -> None:
    assert contract["schema"] == "mastermind.autonomy_stage_b_f0_contract.v5"
    assert contract["architecture_revision"] == REVISION
    assert contract["protected_source_sha"] == SHA
    assert contract["architecture_operation"] == "stage-b0-r1-real-owner-gap-repair-20260902-sol-001"
    assert contract["supersedes"] == [
        "mastermind.autonomy_stage_b_f0_contract.v1",
        "mastermind.autonomy_stage_b_f0_contract.v2",
        "mastermind.autonomy_stage_b_f0_contract.v3",
        "mastermind.autonomy_stage_b_f0_contract.v4",
        "mastermind.autonomy_stage_b_f0_contract.v5.1",
    ]

    current = contract["current_state"]
    assert current["claim"] == "SPEC_ONLY / PREDECESSORS_HELD / SOURCE_NOT_BUILT / PRODUCTION_INERT"
    assert current["authorized_modes_now"] == []
    assert current["source_implementation_authorized_now"] is False
    assert current["production_armed"] is False
    assert current["runtime_effect"] is False
    assert current["provider_effect"] is False

    future = contract["future_supported_mode"]
    assert future == {
        "mode": "INITIAL_ASSIGNMENT",
        "seat": "ceo",
        "reasoning_surface": "codex",
        "held_until": [
            "CAPACITY_C1_PROTECTED",
            "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
            "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
            "EXACT_CURRENT_OHF_WRITER_MATERIALIZED",
        ],
    }

    root = contract["production_root_owner"]
    assert root["root_kind"] == "CEO_V2_ORCHESTRATION_ROOT"
    assert root["call_path"] == [
        "CeoIngress v2",
        "ExecutiveControlService._submit_service_intent",
        "ceo_intent.submit_intent",
        "Runtime.jobs.create_v2_orchestration_root",
    ]
    assert "owner_seat equals ceo" in root["required"]
    assert "accepted mastermind.ceo_intent.v2 provenance" in root["required"]
    assert root["replay_owner"] == "ceo_intent.submit_intent command lookup plus strict v2 root reconstruction"
    assert "root_job_bindings overlay" in root["forbidden_substitutes"]
    assert "caller-created Job" in root["forbidden_substitutes"]

    commitment = contract["placement_commitment_owner"]
    assert commitment["status"] == "MISSING_PREDECESSOR"
    assert commitment["owner"] == "CAPACITY_C2_EXISTING_EXECUTIVE_TRANSACTION_AND_CLAIM_OWNER"
    assert commitment["event_type"] == "CAPACITY_PLACEMENT_COMMITTED"
    assert commitment["event_schema"] == "mastermind.capacity_placement_commitment/v1"
    assert commitment["aggregate_id"] == "responsibility root_job_id"
    for fact in (
        "exact root_job_id",
        "selection_document_digest",
        "selection_evidence_digest",
        "selected_worker_id",
        "selected_quota_class",
        "committed_attempt_id",
        "committed_placement_snapshot_digest",
        "commitment_command_id",
        "commitment_evidence_digest",
        "canonical Worker and Attempt claim already committed",
    ):
        assert fact in commitment["required"]
    for forbidden in (
        "committed_runtime_binding_id",
        "committed_runtime_binding_generation",
        "provider_session_id",
        "native_handle",
    ):
        assert forbidden in commitment["forbidden"]
        assert forbidden not in commitment["required"]
    assert commitment["binding_timing"] == "RUNTIME_BINDING_DOES_NOT_EXIST_UNTIL_OHF_WRITER_MATERIALIZATION"
    assert "BEGIN IMMEDIATE in existing Executive Runtime" in commitment["transaction_law"]
    assert "do not select a second candidate inside the same modifying operation" in commitment["transaction_law"]
    assert commitment["c1_selection_is_authority"] is False
    assert commitment["runtime_binding_alone_is_authority"] is False
    assert commitment["caller_destination_is_authority"] is False

    target = contract["target_definition_owner"]
    assert target["status"] == "ABSENT_PROTECTED_SOURCE"
    assert target["owner"] == "SessionTargetRegistry"
    assert target["required_definition"] == {
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_seat": "ceo",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "allowed_transports": ["codex-app-server"],
        "workstream": "executive",
        "target_enabled": False,
        "production_armed": False,
        "caller_selectable": False,
    }

    materialization = contract["writer_materialization_owner"]
    assert materialization["owner"] == "EXISTING_OPERATOR_HARNESS_AND_RUNTIME_BINDING_PROJECTION"
    assert materialization["starts_provider_work"] is False
    assert materialization["consumes_existing_current_writer_only"] is True
    assert materialization["requires_attempt_id_from_c2"] is True
    assert materialization["not_ready"] == "TARGET_RUNTIME_NOT_MATERIALIZED"
    assert materialization["effect_unknown"] == "EFFECT_UNKNOWN_RECONCILE_FIRST"

    assignment = contract["assignment_owner"]
    assert assignment["owner"] == "Executive Runtime Event plane"
    assert assignment["event_type"] == "SOL_ACTION_TARGET_ASSIGNED"
    assert assignment["first_revision"] == 1
    assert assignment["event_actor_is_authority"] is False
    assert assignment["separate_assignment_table"] is False
    assert assignment["implicit_generation_advance"] is False

    caller = contract["production_call_path"]
    assert caller["owner"] == "ExecutiveControlService"
    assert caller["entry"] == "successful or identically replayed exact current-writer materialization after C2 commitment"
    assert caller["assignment_function"] == "sol_action_target_assignment.assign_initial_target"
    assert caller["caller_exposed_destination_fields"] == []
    assert caller["caller_may_invoke_assignment_directly"] is False
    assert caller["caller_may_supply_actor_label"] is False
    assert caller["caller_may_supply_actor_binding"] is False
    assert caller["caller_may_supply_worker_attempt_or_runtime_binding"] is False
    assert caller["new_daemon_or_scheduler"] is False
    assert "exact protected C2 root-bound claim commitment Event" in caller["authority"]
    assert "exact current RuntimeBinding projected after OHF materialization" in caller["authority"]

    command = contract["command"]
    assert command["caller_may_supply_command_id"] is False
    assert command["caller_may_supply_target_carrier_job_id"] is False
    assert command["caller_may_supply_worker_id"] is False
    assert command["caller_may_supply_attempt_id"] is False
    assert command["caller_may_supply_runtime_binding"] is False
    assert command["caller_may_supply_provider_account_or_native_handle"] is False
    assert "target_carrier_job_id" not in command["fields"]
    assert "worker_id" not in command["fields"]
    assert "attempt_id" not in command["fields"]
    assert command["expected_assignment_revision"] == 0
    assert command["expected_session_alias"] == "EXECUTIVE-CEO-CODEX-A"
    assert command["identical_replay"] == "revalidate current truth then return the identical Event"
    assert command["changed_payload"] == "COMMAND_REPLAY_CONFLICT"
    assert "EXPECTED_REVISION_MISMATCH" in command["same_root_race"]
    assert "no retry or failover" in command["effect_unknown"]

    replay = contract["trusted_replay"]
    assert replay["lookup_order"] == "derived assignment command id before mutable reads"
    for fact in (
        "canonical existing assignment Event shape and command fingerprint",
        "active admitted CEO v2 root and immutable authority provenance",
        "exact root-bound C2 claim commitment Event and digest",
        "canonical current Worker and Attempt identities from the commitment",
        "exact target definition fingerprint",
        "current RuntimeBinding id generation and reasoning surface projected from the committed Attempt",
    ):
        assert fact in replay["must_revalidate"]
    assert replay["stale_or_moved_binding"] == "STALE_ASSIGNED_BINDING"
    assert replay["historical_success_is_reusable_authority"] is False

    for field in (
        "placement_commitment_command_id",
        "placement_commitment_digest",
        "binding_id",
        "binding_generation",
        "command_fingerprint",
        "evidence_fingerprint",
    ):
        assert field in contract["event_required"]
    for field in (
        "native_handle",
        "provider_session_id",
        "account_label",
        "Slack principal",
        "model output",
        "caller actor label",
    ):
        assert field in contract["event_forbidden"]

    projection = contract["projection_and_stage_a"]
    assert projection["stage_a_signature_changed"] is False
    assert "reread and validate the exact C2 claim commitment" in projection["action_time"]
    assert "project current RuntimeBinding from the committed Attempt after OHF materialization" in projection["action_time"]
    assert "copy complete root_job_bindings and replace only selected root ceo" in projection["action_time"]
    assert "call unchanged require_sol_action_authority with the actual actor RuntimeBinding" in projection["action_time"]
    assert "exact RuntimeBinding identity" in projection["stage_a_actor_rule"]

    for failure in (
        "PLACEMENT_COMMITMENT_MISSING",
        "PLACEMENT_COMMITMENT_CONFLICT",
        "PLACEMENT_COMMITMENT_EFFECT_UNKNOWN",
        "TARGET_CATALOG_ENTRY_MISSING",
        "TARGET_RUNTIME_NOT_MATERIALIZED",
        "TARGET_ALIAS_ALREADY_BINDS_DIFFERENT_RUNTIME",
        "EXPECTED_REVISION_MISMATCH",
        "COMMAND_REPLAY_CONFLICT",
        "STALE_ASSIGNED_BINDING",
    ):
        assert failure in contract["failures"]

    assert "never elect a destination by recency" in contract["time_null_correction"]["timestamps"]
    assert contract["time_null_correction"]["automatic_retry"] is False

    source = contract["source_wave"]
    assert source["status"] == "HELD_PREDECESSORS"
    assert source["name"] == "STAGE_B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL"
    assert source["paths"] == SOURCE_PATHS
    assert source["maximum_paths"] == 6
    assert "config/wake_session_targets.json" not in source["paths"]
    assert source["target_definition_is_separate_predecessor"] is True
    assert source["release_claim"] == "BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED"

    no_rebuild = contract["no_rebuild"]
    assert no_rebuild["tables"] == []
    assert no_rebuild["migrations"] == []
    assert no_rebuild["registries"] == []
    assert no_rebuild["lifecycles"] == []
    assert no_rebuild["queues"] == []
    assert no_rebuild["leases"] == []
    assert no_rebuild["job_attempt_worker_owners_duplicated"] is False
    assert no_rebuild["capacity_commitment_owner_duplicated"] is False
    assert no_rebuild["runtime_binding_owner_duplicated"] is False
    assert no_rebuild["wake_owner_duplicated"] is False
    assert no_rebuild["provider_or_slack_calls_in_transaction"] is False
    assert no_rebuild["production_armed"] is False


def test_v5_2_contract_and_false_support_mutations() -> None:
    contract, raw = json_block(DESIGN, BEGIN, END)
    validate_contract(contract)
    assert "chatgpt-web" not in raw

    Mutation = Callable[[dict[str, Any]], None]

    def set_path(path: tuple[str, ...], value: Any) -> Mutation:
        def mutate(item: dict[str, Any]) -> None:
            cursor: Any = item
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value

        return mutate

    mutations: dict[str, Mutation] = {
        "authorize_now": lambda item: item["current_state"]["authorized_modes_now"].append("INITIAL_ASSIGNMENT"),
        "drop_c2_predecessor": lambda item: item["future_supported_mode"]["held_until"].remove("CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED"),
        "drop_materialization_predecessor": lambda item: item["future_supported_mode"]["held_until"].remove("EXACT_CURRENT_OHF_WRITER_MATERIALIZED"),
        "c1_is_commitment": set_path(("placement_commitment_owner", "c1_selection_is_authority"), True),
        "binding_is_authority": set_path(("placement_commitment_owner", "runtime_binding_alone_is_authority"), True),
        "caller_destination": set_path(("placement_commitment_owner", "caller_destination_is_authority"), True),
        "binding_in_c2": lambda item: item["placement_commitment_owner"]["required"].append("committed_runtime_binding_id"),
        "provider_start_in_projection": set_path(("writer_materialization_owner", "starts_provider_work"), True),
        "public_assign": set_path(("production_call_path", "caller_may_invoke_assignment_directly"), True),
        "caller_actor": set_path(("production_call_path", "caller_may_supply_actor_binding"), True),
        "caller_carrier": set_path(("command", "caller_may_supply_target_carrier_job_id"), True),
        "historical_replay": set_path(("trusted_replay", "historical_success_is_reusable_authority"), True),
        "drop_binding_revalidation": lambda item: item["trusted_replay"]["must_revalidate"].remove("current RuntimeBinding id generation and reasoning surface projected from the committed Attempt"),
        "implicit_generation": set_path(("assignment_owner", "implicit_generation_advance"), True),
        "change_stage_a": set_path(("projection_and_stage_a", "stage_a_signature_changed"), True),
        "destructive_map": set_path(("projection_and_stage_a", "action_time"), ["replace selected root only"]),
        "new_table": set_path(("no_rebuild", "tables"), ["sol_targets"]),
        "new_queue": set_path(("no_rebuild", "queues"), ["assignment_queue"]),
        "arm": set_path(("no_rebuild", "production_armed"), True),
        "target_config_reintroduced": lambda item: item["source_wave"]["paths"].append("config/wake_session_targets.json"),
    }

    survivors = []
    for name, mutate in mutations.items():
        changed = copy.deepcopy(contract)
        mutate(changed)
        try:
            validate_contract(changed)
        except (AssertionError, KeyError, ValueError):
            continue
        survivors.append(name)
    assert survivors == [], survivors


def test_current_production_root_and_stage_a_owners_are_real() -> None:
    service = read(EXECUTIVE_SERVICE)
    ceo_intent = read(CEO_INTENT)
    runtime = read(EXECUTIVE_RUNTIME)
    projection = read(RUNTIME_BINDING)
    stage_a = read(STAGE_A)
    targets = json.loads(read(TARGETS))

    assert "def _submit_service_intent" in service
    assert "self._require_current_coo_binding()" in service
    assert "ceo_intent.submit_intent(" in service
    assert "def submit_intent" in ceo_intent
    assert "runtime.jobs.create_v2_orchestration_root(" in ceo_intent
    assert "def create_v2_orchestration_root" in runtime

    assert targets["root_job_bindings"] == {}
    assert "Git stays empty" in targets["notes"]
    assert not any(
        item["target_seat"] == "ceo" and item["reasoning_surface"] == "codex"
        for item in targets["targets"].values()
    )
    assert targets["targets"]["EXECUTIVE-CEO-A"]["reasoning_surface"] == "chatgpt-sol"
    assert targets["production_armed"] is False

    assert '_PROVIDER_TO_REASONING_SURFACE = {"openai-codex": "codex"}' in projection
    assert "runtime.current_harness_binding_source(" in projection
    assert "connection=connection" in projection
    assert "this function persists nothing" in projection
    assert "provider_session_id=str(row[\"epoch_provider_session\"])" in runtime
    assert "session_epoch_id=str(row[\"session_epoch_id\"])" in runtime

    assert "Storeless Stage-A resolution" in stage_a
    assert "The registry's root binding wins" in stage_a
    assert "seat/workstream defaults are never consulted" in stage_a
    assert "def require_sol_action_authority" in stage_a
    assert "_binding_identity(actor) == _binding_identity(target)" in stage_a
    assert "is evidence, not a reusable authority" in stage_a


def test_plan_gate_orders_claim_then_materialization_then_assignment() -> None:
    gate, raw = json_block(PLAN, GATE_BEGIN, GATE_END)
    assert gate["schema"] == "mastermind.autonomy_stage_b1_correction_gate.v5"
    assert gate["architecture_revision"] == REVISION
    assert gate["protected_source_sha"] == SHA
    assert gate["records_paths"] == RECORD_PATHS
    assert gate["records_only"] is True
    assert gate["architecture_state"] == "FROZEN"
    assert gate["stage_b1_state"] == "HELD_PREDECESSORS"
    assert gate["predecessors"] == [
        "CAPACITY_C1_PROTECTED",
        "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
        "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
        "EXACT_CURRENT_OHF_WRITER_MATERIALIZED",
    ]
    assert gate["next_program_wave"] == "CAPACITY_C2_TRANSACTIONAL_CLAIM_COMMITMENT_VERTICAL"
    assert gate["stage_b1_after_predecessors"] == "STAGE_B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL"
    assert gate["production_assignment_caller"] == "ExecutiveControlService exact current-writer materialization/replay path after C2 commitment"
    assert gate["c2_contains_runtime_binding"] is False
    assert gate["destination_session_self_authority"] is False
    assert gate["caller_destination_authority"] is False
    assert gate["trusted_replay_revalidates_current_truth"] is True
    assert gate["requires_exact_binding_generation_fence"] is True
    assert gate["requires_complete_root_map_preservation"] is True
    assert gate["requires_unchanged_stage_a"] is True
    assert gate["runtime_effect"] is False
    assert gate["provider_effect"] is False
    assert gate["production_armed"] is False
    assert "chatgpt-web" not in raw

    plan = read(PLAN)
    for path in RECORD_PATHS + SOURCE_PATHS:
        assert path in plan
    order = [
        "1. PROTECT_STAGE_B0_V5_2_ARCHITECTURE",
        "2. PROTECT_CAPACITY_C1_SELECTION",
        "3. BUILD_CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT",
        "4. ADD_DISABLED_EXECUTIVE_CEO_CODEX_A_TARGET",
        "5. MATERIALIZE_EXACT_CURRENT_OHF_WRITER",
        "6. RED_STAGE_B1_PRODUCTION_ROOT_COMMITMENT_AND_BINDING_CHAIN",
    ]
    indexes = [plan.index(item) for item in order]
    assert indexes == sorted(indexes)
    assert "No seventh path" in plan
    assert "Do not modify `config/wake_session_targets.json`" in plan
    assert "Do not modify `control_plane/sol_action_target.py`" in plan
