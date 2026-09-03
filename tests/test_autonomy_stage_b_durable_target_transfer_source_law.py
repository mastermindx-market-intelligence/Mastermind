from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path
from typing import Any, Callable

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
REVISION = "v5.3-post-handoff-aggregation"
RUNTIME_SHA = "c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6"
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


def class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for member in node.body:
                if isinstance(member, ast.FunctionDef) and member.name == method_name:
                    return member
    raise AssertionError(f"missing {class_name}.{method_name}")


def module_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function {name}")


def source_segment(text: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(text, node)
    assert segment is not None
    return segment


def argument_default(function: ast.FunctionDef, name: str) -> ast.expr:
    values: dict[str, ast.expr | None] = {}
    positional = [*function.args.posonlyargs, *function.args.args]
    positional_defaults = [None] * (len(positional) - len(function.args.defaults)) + list(
        function.args.defaults
    )
    for argument, default in zip(positional, positional_defaults, strict=True):
        values[argument.arg] = default
    for argument, default in zip(
        function.args.kwonlyargs, function.args.kw_defaults, strict=True
    ):
        values[argument.arg] = default
    default = values.get(name)
    assert default is not None, f"{function.name}.{name} has no default"
    return default


def create_job_call(function: ast.FunctionDef) -> ast.Call:
    matches = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_job"
    ]
    assert len(matches) == 1
    return matches[0]


def validate_contract(contract: dict[str, Any]) -> None:
    assert contract["schema"] == "mastermind.autonomy_stage_b_f0_contract.v5"
    assert contract["architecture_revision"] == REVISION
    assert contract["protected_runtime_sha"] == RUNTIME_SHA
    assert contract["architecture_operation"] == (
        "stage-b0-r1-real-owner-gap-repair-20260902-sol-001"
    )
    assert contract["supersedes"][-1] == (
        "mastermind.autonomy_stage_b_f0_contract.v5.2"
    )

    current = contract["current_state"]
    assert current == {
        "claim": "SPEC_ONLY / PREDECESSORS_HELD / SOURCE_NOT_BUILT / PRODUCTION_INERT",
        "authorized_modes_now": [],
        "source_implementation_authorized_now": False,
        "production_armed": False,
        "runtime_effect": False,
        "provider_effect": False,
    }

    future = contract["future_supported_mode"]
    assert future["mode"] == "INITIAL_ASSIGNMENT"
    assert future["seat"] == "ceo"
    assert future["reasoning_surface"] == "codex"
    assert future["held_until"] == [
        "COO_AGGREGATION_HANDOFF_VALIDATED",
        "CAPACITY_C1_PROTECTED",
        "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
        "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
        "EXACT_CURRENT_OHF_WRITER_MATERIALIZED",
    ]

    root = contract["production_root_owner"]
    assert root["root_kind"] == "CEO_V2_AGGREGATION_ROOT"
    assert root["stored_owner_seat"] == "coo"
    assert root["orchestration_role"] == "aggregation"
    assert root["authority_source"] == "accepted mastermind.ceo_intent.v2 provenance"
    assert root["call_path"] == [
        "CeoIngress v2",
        "ExecutiveControlService._submit_service_intent",
        "ceo_intent.submit_intent",
        "Runtime.jobs.create_v2_orchestration_root",
    ]
    for fact in (
        "Runtime.jobs.create_cycle_planner",
        "Runtime.jobs.admit_cycle_plan",
        "canonical work review and repair children",
        "COO_AGGREGATION_HANDOFF_READY",
        "Runtime._validated_aggregation_handoff",
    ):
        assert fact in root["pre_claim_lifecycle"]
    for fact in (
        "stored owner_seat equals coo",
        "orchestration_role equals aggregation",
        "root status equals QUEUED",
        "current_attempt_id is null",
        "all planner work review and repair children are terminal",
        "one exact validated aggregation handoff is current",
    ):
        assert fact in root["claim_readiness"]
    assert "pre-handoff root claim" in root["forbidden_substitutes"]
    assert "root_job_bindings overlay" in root["forbidden_substitutes"]
    assert "caller-created Job" in root["forbidden_substitutes"]

    commitment = contract["placement_commitment_owner"]
    assert commitment["status"] == "MISSING_PREDECESSOR"
    assert commitment["owner"] == (
        "CAPACITY_C2_EXISTING_EXECUTIVE_TRANSACTION_AND_CLAIM_OWNER"
    )
    assert commitment["event_type"] == "CAPACITY_PLACEMENT_COMMITTED"
    assert commitment["event_schema"] == (
        "mastermind.capacity_placement_commitment/v1"
    )
    assert commitment["aggregate_id"] == "aggregation root_job_id"
    for fact in (
        "exact root_job_id",
        "exact aggregation_handoff_command_id",
        "exact aggregation_handoff_digest",
        "exact plan_attempt_id",
        "exact plan_digest",
        "selection_document_digest",
        "selection_evidence_digest",
        "selected_worker_id",
        "selected_quota_class",
        "committed_attempt_id",
        "committed_placement_snapshot_digest",
        "commitment_command_id",
        "commitment_evidence_digest",
        "canonical aggregation Worker and Attempt claim already committed",
    ):
        assert fact in commitment["required"]
    for forbidden in (
        "committed_runtime_binding_id",
        "committed_runtime_binding_generation",
        "provider_session_id",
        "native_handle",
        "account_label",
    ):
        assert forbidden in commitment["forbidden"]
        assert forbidden not in commitment["required"]
    for law in (
        "BEGIN IMMEDIATE in existing Executive Runtime",
        "revalidate exact current aggregation handoff before capacity mutation",
        "recompute and compare the C1 selection",
        "claim existing canonical aggregation Worker and Attempt owners",
        "rollback Job Attempt quota and Event together on any failure",
        "do not select a second candidate inside the same modifying operation",
    ):
        assert law in commitment["transaction_law"]
    assert commitment["pre_handoff_mutation_allowed"] is False
    assert commitment["c1_selection_is_authority"] is False
    assert commitment["runtime_binding_alone_is_authority"] is False
    assert commitment["caller_destination_is_authority"] is False

    target = contract["target_definition_owner"]
    assert target["status"] == "SEPARATE_DISABLED_SOURCE_PREREQUISITE"
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
    assert materialization["owner"] == (
        "EXISTING_OPERATOR_HARNESS_AND_RUNTIME_BINDING_PROJECTION"
    )
    assert materialization["starts_provider_work"] is False
    assert materialization["consumes_existing_current_writer_only"] is True
    assert materialization["requires_aggregation_attempt_id_from_c2"] is True
    assert materialization["not_ready"] == "TARGET_RUNTIME_NOT_MATERIALIZED"
    assert materialization["effect_unknown"] == "EFFECT_UNKNOWN_RECONCILE_FIRST"

    assignment = contract["assignment_owner"]
    assert assignment["owner"] == "Executive Runtime Event plane"
    assert assignment["aggregate_id"] == "aggregation root_job_id"
    assert assignment["event_type"] == "SOL_ACTION_TARGET_ASSIGNED"
    assert assignment["first_revision"] == 1
    assert assignment["event_actor_is_authority"] is False
    assert assignment["separate_assignment_table"] is False
    assert assignment["implicit_generation_advance"] is False

    caller = contract["production_call_path"]
    assert caller["owner"] == "ExecutiveControlService"
    assert caller["entry"] == (
        "successful or identically replayed exact current-writer materialization "
        "after post-handoff C2 commitment"
    )
    assert caller["assignment_function"] == (
        "sol_action_target_assignment.assign_initial_target"
    )
    assert caller["caller_exposed_destination_fields"] == []
    assert caller["caller_may_invoke_assignment_directly"] is False
    assert caller["caller_may_supply_actor_label"] is False
    assert caller["caller_may_supply_actor_binding"] is False
    assert caller["caller_may_supply_worker_attempt_or_runtime_binding"] is False
    assert "accepted post-handoff CEO v2 aggregation root" in caller["authority"]
    assert "exact validated aggregation handoff bound by C2" in caller["authority"]
    assert "exact protected C2 root-bound claim commitment Event" in caller["authority"]
    assert "exact current RuntimeBinding projected after OHF materialization" in caller["authority"]
    assert caller["new_daemon_or_scheduler"] is False

    command = contract["command"]
    for key in (
        "caller_may_supply_command_id",
        "caller_may_supply_target_carrier_job_id",
        "caller_may_supply_worker_id",
        "caller_may_supply_attempt_id",
        "caller_may_supply_runtime_binding",
        "caller_may_supply_provider_account_or_native_handle",
    ):
        assert command[key] is False
    assert command["expected_assignment_revision"] == 0
    assert command["expected_session_alias"] == "EXECUTIVE-CEO-CODEX-A"
    assert command["identical_replay"] == (
        "revalidate current truth then return the identical Event"
    )
    assert command["changed_payload"] == "COMMAND_REPLAY_CONFLICT"
    assert "EXPECTED_REVISION_MISMATCH" in command["same_root_race"]
    assert "no retry or failover" in command["effect_unknown"]

    replay = contract["trusted_replay"]
    assert replay["lookup_order"] == "derived assignment command id before mutable reads"
    for fact in (
        "active post-handoff CEO v2 aggregation root and immutable authority provenance",
        "exact aggregation handoff identity bound by the C2 commitment",
        "exact root-bound C2 claim commitment Event and digest",
        "canonical current aggregation Worker and Attempt identities from the commitment",
        "exact target definition fingerprint",
        "current RuntimeBinding id generation and reasoning surface projected from the committed Attempt",
    ):
        assert fact in replay["must_revalidate"]
    assert replay["stale_or_moved_binding"] == "STALE_ASSIGNED_BINDING"
    assert replay["historical_success_is_reusable_authority"] is False

    projection = contract["projection_and_stage_a"]
    assert projection["stage_a_signature_changed"] is False
    assert "reread active post-handoff CEO v2 aggregation root" in projection["action_time"]
    assert (
        "reread and validate the exact C2 claim commitment and bound aggregation handoff"
        in projection["action_time"]
    )
    assert (
        "require the committed aggregation Attempt remains the canonical current Attempt"
        in projection["action_time"]
    )
    assert "copy complete root_job_bindings and replace only selected root ceo" in projection["action_time"]
    assert "call unchanged require_sol_action_authority with the actual actor RuntimeBinding" in projection["action_time"]
    assert "exact RuntimeBinding identity" in projection["stage_a_actor_rule"]

    for failure in (
        "ROOT_JOB_NOT_AGGREGATION_ROOT",
        "ROOT_NOT_READY_FOR_AGGREGATION_CLAIM",
        "AGGREGATION_HANDOFF_MISSING",
        "AGGREGATION_HANDOFF_CONFLICT",
        "PLACEMENT_COMMITMENT_MISSING",
        "PLACEMENT_COMMITMENT_CONFLICT",
        "TARGET_RUNTIME_NOT_MATERIALIZED",
        "TARGET_ALIAS_ALREADY_BINDS_DIFFERENT_RUNTIME",
        "EXPECTED_REVISION_MISMATCH",
        "COMMAND_REPLAY_CONFLICT",
        "STALE_ASSIGNED_BINDING",
    ):
        assert failure in contract["failures"]

    source = contract["source_wave"]
    assert source["status"] == "HELD_PREDECESSORS"
    assert source["name"] == "STAGE_B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL"
    assert source["paths"] == SOURCE_PATHS
    assert source["maximum_paths"] == 6
    assert "config/wake_session_targets.json" not in source["paths"]
    assert source["target_definition_is_separate_predecessor"] is True
    assert source["release_claim"] == (
        "BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED"
    )

    no_rebuild = contract["no_rebuild"]
    for key in ("tables", "migrations", "registries", "lifecycles", "queues", "leases"):
        assert no_rebuild[key] == []
    for key in (
        "job_attempt_worker_owners_duplicated",
        "coo_cycle_or_handoff_owner_duplicated",
        "capacity_commitment_owner_duplicated",
        "runtime_binding_owner_duplicated",
        "wake_owner_duplicated",
        "provider_or_slack_calls_in_transaction",
        "production_armed",
    ):
        assert no_rebuild[key] is False


def test_v5_3_contract_and_false_support_mutations() -> None:
    contract, raw = json_block(DESIGN, BEGIN, END)
    validate_contract(contract)
    assert "owner_seat equals ceo" not in raw
    assert "orchestration_role is null" not in raw
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
        "ceo_stored_owner": set_path(("production_root_owner", "stored_owner_seat"), "ceo"),
        "null_root_role": set_path(("production_root_owner", "orchestration_role"), None),
        "drop_handoff_predecessor": lambda item: item["future_supported_mode"]["held_until"].remove("COO_AGGREGATION_HANDOFF_VALIDATED"),
        "drop_handoff_lifecycle": lambda item: item["production_root_owner"]["pre_claim_lifecycle"].remove("Runtime._validated_aggregation_handoff"),
        "allow_pre_handoff": set_path(("placement_commitment_owner", "pre_handoff_mutation_allowed"), True),
        "drop_handoff_transaction_gate": lambda item: item["placement_commitment_owner"]["transaction_law"].remove("revalidate exact current aggregation handoff before capacity mutation"),
        "binding_in_c2": lambda item: item["placement_commitment_owner"]["required"].append("committed_runtime_binding_id"),
        "provider_start_in_projection": set_path(("writer_materialization_owner", "starts_provider_work"), True),
        "public_assign": set_path(("production_call_path", "caller_may_invoke_assignment_directly"), True),
        "caller_destination": set_path(("placement_commitment_owner", "caller_destination_is_authority"), True),
        "historical_replay": set_path(("trusted_replay", "historical_success_is_reusable_authority"), True),
        "change_stage_a": set_path(("projection_and_stage_a", "stage_a_signature_changed"), True),
        "new_table": set_path(("no_rebuild", "tables"), ["sol_targets"]),
        "duplicate_coo_cycle": set_path(("no_rebuild", "coo_cycle_or_handoff_owner_duplicated"), True),
        "target_config_reintroduced": lambda item: item["source_wave"]["paths"].append("config/wake_session_targets.json"),
    }

    survivors: list[str] = []
    for name, mutate in mutations.items():
        changed = copy.deepcopy(contract)
        mutate(changed)
        try:
            validate_contract(changed)
        except (AssertionError, KeyError, TypeError, ValueError):
            continue
        survivors.append(name)
    assert survivors == [], survivors


def test_protected_runtime_proves_aggregation_root_and_handoff_before_claim() -> None:
    runtime_text = read(EXECUTIVE_RUNTIME)
    tree = ast.parse(runtime_text)

    create_v2 = class_method(tree, "JobRegistry", "create_v2_orchestration_root")
    create_job = class_method(tree, "JobRegistry", "create_job")
    call = create_job_call(create_v2)
    keywords = {item.arg: item.value for item in call.keywords if item.arg is not None}
    assert ast.literal_eval(keywords["orchestration_role"]) == "aggregation"
    assert "owner_seat" not in keywords
    assert ast.literal_eval(argument_default(create_job, "owner_seat")) == "coo"

    planner = source_segment(
        runtime_text, class_method(tree, "JobRegistry", "create_cycle_planner")
    )
    assert 'root.orchestration_role != "aggregation"' in planner
    assert 'provenance.get("creator") != "ceo_intent"' in planner

    admission = source_segment(
        runtime_text, class_method(tree, "JobRegistry", "admit_cycle_plan")
    )
    assert "_assert_cycle_root_open_for_child_mutation(connection, root)" in admission
    assert "plan admission requires an eligible strict-v2 root" in admission
    assert "COO_PLAN_ADMITTED" in admission

    handoff = source_segment(
        runtime_text, module_function(tree, "_validated_aggregation_handoff")
    )
    assert "COO_AGGREGATION_HANDOFF_READY" in handoff
    assert "aggregation handoff refuses living child Jobs" in handoff

    dispatch = source_segment(
        runtime_text, module_function(tree, "_assert_orchestration_dispatch_eligible")
    )
    assert 'if role == "aggregation"' in dispatch
    assert "_validated_aggregation_handoff(connection, job_row)" in dispatch
    assert "aggregation dispatch requires an eligible queued root" in dispatch

    claim = source_segment(runtime_text, class_method(tree, "AttemptRegistry", "claim_job"))
    gate_index = claim.index("_assert_orchestration_dispatch_eligible(connection, job_row)")
    quota_index = claim.index("UPDATE worker_quota_classes")
    assert gate_index < quota_index


def test_real_admission_materialization_and_stage_a_owners_remain_single() -> None:
    service = read(EXECUTIVE_SERVICE)
    ceo_intent = read(CEO_INTENT)
    runtime = read(EXECUTIVE_RUNTIME)
    projection = read(RUNTIME_BINDING)
    stage_a = read(STAGE_A)
    targets = json.loads(read(TARGETS))

    assert "def _submit_service_intent" in service
    assert "ceo_intent.submit_intent(" in service
    assert "def submit_intent" in ceo_intent
    assert "runtime.jobs.create_v2_orchestration_root(" in ceo_intent
    assert "def create_v2_orchestration_root" in runtime

    assert targets["root_job_bindings"] == {}
    assert "Git stays empty" in targets["notes"]
    assert targets["production_armed"] is False
    codex = targets["targets"].get("EXECUTIVE-CEO-CODEX-A")
    if codex is not None:
        assert codex == {
            "session_alias": "EXECUTIVE-CEO-CODEX-A",
            "target_seat": "ceo",
            "reasoning_surface": "codex",
            "wake_transport": "codex-app-server",
            "allowed_transports": ["codex-app-server"],
            "workstream": "executive",
            "target_enabled": False,
        }

    assert '_PROVIDER_TO_REASONING_SURFACE = {"openai-codex": "codex"}' in projection
    assert "runtime.current_harness_binding_source(" in projection
    assert "connection=connection" in projection
    assert "this function persists nothing" in projection

    assert "Storeless Stage-A resolution" in stage_a
    assert "The registry's root binding wins" in stage_a
    assert "seat/workstream defaults are never consulted" in stage_a
    assert "def require_sol_action_authority" in stage_a
    assert "_binding_identity(actor) == _binding_identity(target)" in stage_a
    assert "is evidence, not a reusable authority" in stage_a


def test_plan_orders_coo_handoff_before_c2_and_stage_b1() -> None:
    gate, raw = json_block(PLAN, GATE_BEGIN, GATE_END)
    assert gate["schema"] == "mastermind.autonomy_stage_b1_correction_gate.v5"
    assert gate["architecture_revision"] == REVISION
    assert gate["protected_runtime_sha"] == RUNTIME_SHA
    assert gate["records_paths"] == RECORD_PATHS
    assert gate["records_only"] is True
    assert gate["architecture_state"] == "FROZEN"
    assert gate["stage_b1_state"] == "HELD_PREDECESSORS"
    assert gate["predecessors"] == [
        "COO_AGGREGATION_HANDOFF_VALIDATED",
        "CAPACITY_C1_PROTECTED",
        "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
        "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
        "EXACT_CURRENT_OHF_WRITER_MATERIALIZED",
    ]
    assert gate["next_program_wave"] == (
        "CAPACITY_C2_POST_HANDOFF_AGGREGATION_CLAIM_VERTICAL"
    )
    assert gate["stage_b1_after_predecessors"] == (
        "STAGE_B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL"
    )
    assert gate["c2_root_role"] == "aggregation"
    assert gate["c2_root_stored_owner_seat"] == "coo"
    assert gate["c2_requires_validated_aggregation_handoff"] is True
    assert gate["c2_pre_handoff_mutation_allowed"] is False
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
        "1. PROTECT_STAGE_B0_V5_3_POST_HANDOFF_ARCHITECTURE",
        "2. PROTECT_CAPACITY_C1_SELECTION",
        "3. COMPLETE_COO_CYCLE_TO_VALIDATED_AGGREGATION_HANDOFF",
        "4. BUILD_CAPACITY_C2_POST_HANDOFF_AGGREGATION_CLAIM_COMMITMENT",
        "5. ADD_DISABLED_EXECUTIVE_CEO_CODEX_A_TARGET",
        "6. MATERIALIZE_EXACT_CURRENT_OHF_WRITER",
        "7. RED_STAGE_B1_PRODUCTION_ROOT_COMMITMENT_AND_BINDING_CHAIN",
    ]
    indexes = [plan.index(item) for item in order]
    assert indexes == sorted(indexes)
    assert "No seventh path" in plan
    assert "Do not modify `config/wake_session_targets.json`" in plan
    assert "Do not modify `control_plane/sol_action_target.py`" in plan
    assert "admission alone is not claim readiness" in plan
    assert "owner_seat equals ceo" not in plan
    assert "orchestration_role is null" not in plan
