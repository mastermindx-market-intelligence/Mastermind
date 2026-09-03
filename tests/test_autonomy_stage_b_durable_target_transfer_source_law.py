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
EXECUTIVE_RUNTIME = ROOT / "control_plane" / "executive_runtime.py"
RUNTIME_BINDING = ROOT / "control_plane" / "runtime_binding_projection.py"
STAGE_A = ROOT / "control_plane" / "sol_action_target.py"
TARGETS = ROOT / "config" / "wake_session_targets.json"

BEGIN = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->"
END = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->"
GATE_BEGIN = "<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->"
GATE_END = "<!-- STAGE_B1_CORRECTION_GATE_END -->"

REVISION = "v6.1-split-initial-and-reuse"
OPERATION = "stage-b0-r2-alias-carrier-correction-20260903-sol-001"
PROTECTED_SHA = "642fa62540f0f2565ccc484a350f2cd0a2259015"
RECORD_PATHS = [
    "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md",
    "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md",
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


def argument_default(function: ast.FunctionDef, name: str) -> ast.expr:
    positional = [*function.args.posonlyargs, *function.args.args]
    defaults: dict[str, ast.expr | None] = {}
    positional_defaults = [None] * (len(positional) - len(function.args.defaults)) + list(
        function.args.defaults
    )
    for argument, default in zip(positional, positional_defaults, strict=True):
        defaults[argument.arg] = default
    for argument, default in zip(
        function.args.kwonlyargs, function.args.kw_defaults, strict=True
    ):
        defaults[argument.arg] = default
    value = defaults.get(name)
    assert value is not None, f"{function.name}.{name} has no default"
    return value


def one_create_job_call(function: ast.FunctionDef) -> ast.Call:
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_job"
    ]
    assert len(calls) == 1
    return calls[0]


def validate_contract(contract: dict[str, Any]) -> None:
    assert contract["schema"] == "mastermind.autonomy_stage_b_f0_contract.v6"
    assert contract["architecture_revision"] == REVISION
    assert contract["architecture_operation"] == OPERATION
    assert contract["protected_runtime_sha"] == PROTECTED_SHA
    assert contract["supersedes"][-1] == "mastermind.autonomy_stage_b_f0_contract.v5"
    assert contract["record_paths"] == RECORD_PATHS
    assert contract["implementation_dag"] == {
        "C2-R1A_INITIAL_CARRIER_COMMITMENT": ["C2-PURE"],
        "C2-R1B_EXISTING_CARRIER_REUSE": [
            "MAT-S1_ROLE_NULL_CEO_CARRIER_MATERIALIZATION"
        ],
        "MAT-S1_ROLE_NULL_CEO_CARRIER_MATERIALIZATION": [
            "C2-R1A_INITIAL_CARRIER_COMMITMENT"
        ],
        "MULTI_ROOT_REUSE_CANARY": [
            "C2-R1B_EXISTING_CARRIER_REUSE",
            "STAGE-B1_INITIAL_ASSIGNMENT",
        ],
        "STAGE-B1_INITIAL_ASSIGNMENT": [
            "MAT-S1_ROLE_NULL_CEO_CARRIER_MATERIALIZATION"
        ],
    }

    assert contract["current_state"] == {
        "claim": "SPEC_ONLY / CORRECTION_REQUIRED / SOURCE_NOT_BUILT / PRODUCTION_INERT",
        "authorized_modes_now": [],
        "source_implementation_authorized_now": False,
        "production_armed": False,
        "runtime_effect": False,
        "provider_effect": False,
    }

    root = contract["source_responsibility_root"]
    assert root["root_kind"] == "CEO_V2_AGGREGATION_ROOT"
    assert root["stored_owner_seat"] == "coo"
    assert root["escalation_target"] == "coo"
    assert root["orchestration_role"] == "aggregation"
    assert root["authority_source"] == "accepted mastermind.ceo_intent.v2 provenance"
    assert root["remains_unclaimed_by_capacity_c2"] is True
    assert root["remains_stage_b_assignment_aggregate"] is True
    assert root["remains_coo_responsibility_aggregate"] is True
    assert root["ceo_office_assignment_requires_coo_handoff"] is False
    for forbidden in (
        "relabel root to ceo",
        "clear aggregation role",
        "claim root Attempt for CEO carrier",
        "project root Attempt as ceo RuntimeBinding",
        "caller-created root binding overlay",
    ):
        assert forbidden in root["forbidden"]

    target = contract["target_definition_owner"]
    assert target["owner"] == "SessionTargetRegistry"
    assert target["session_alias"] == "EXECUTIVE-CEO-CODEX-A"
    assert target["definition"] == {
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_seat": "ceo",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "allowed_transports": ["codex-app-server"],
        "workstream": "executive",
        "target_enabled": False,
    }
    assert target["global_production_armed"] is False
    assert target["fingerprint_fields"] == [
        "session_alias",
        "target_seat",
        "reasoning_surface",
        "wake_transport",
        "allowed_transports",
        "workstream",
    ]
    assert target["caller_selectable"] is False

    carrier = contract["alias_carrier_owner"]
    assert carrier["owner"] == "Executive Runtime existing Job Attempt Worker Event plane"
    assert carrier["creation_provenance_schema"] == "mastermind.sol_session_carrier/v1"
    assert carrier["creation_command_schema"] == "mastermind.sol_session_carrier_command/v1"
    assert carrier["shape"] == {
        "parent_job_id": None,
        "root_job_id": "self",
        "depth": 0,
        "owner_seat": "ceo",
        "escalation_target": "ceo",
        "orchestration_role": None,
        "requested_authorities": ["READ"],
        "allowed_write_paths": [],
        "validation_commands": [],
        "attempt_limit": 1,
        "carrier_generation": 1,
    }
    assert carrier["identity_scope"] == [
        "session_alias",
        "target_definition_fingerprint",
        "carrier_generation",
    ]
    assert "source_root_job_id" in carrier["identity_excludes"]
    assert carrier["creation_command"].startswith("SOL-CARRIER-")
    assert carrier["cardinality"] == (
        "one initial carrier Job per session_alias and carrier_generation"
    )
    assert carrier["many_source_roots_may_reference_one_carrier"] is True
    assert carrier["one_carrier_per_source_root"] is False
    assert carrier["succession_supported_now"] is False

    c2 = contract["capacity_c2_commitment"]
    assert set(c2) == {
        "aggregate_id",
        "caller_may_supply_carrier_identity",
        "changed_payload",
        "command_schema",
        "event_forbidden",
        "event_required",
        "event_schema",
        "event_type",
        "existing_session_reuse",
        "historical_event_is_current_authority",
        "identical_replay",
        "implementation_waves",
        "mode_disposition",
        "new_session_materialization",
        "optimistic_preconditions",
        "owner",
        "placement_modes",
        "r1a_constraints",
        "r1b_reuse",
        "source_root_claimed",
        "stable_command_fields",
        "status",
    }
    assert c2["owner"] == "CAPACITY_C2_EXISTING_EXECUTIVE_TRANSACTION_AND_CLAIM_OWNER"
    assert c2["status"] == "MISSING_SOURCE_IMPLEMENTATION"
    assert c2["event_type"] == "CAPACITY_PLACEMENT_COMMITTED"
    assert c2["event_schema"] == "mastermind.capacity_placement_commitment/v2"
    assert c2["command_schema"] == "mastermind.capacity_placement_commitment_command/v2"
    assert c2["aggregate_id"] == "source responsibility root_job_id"
    assert c2["placement_modes"] == [
        "new_session_materialization",
        "existing_session_reuse",
    ]
    assert c2["mode_disposition"] == {
        "new_session_materialization": "created",
        "existing_session_reuse": "reused",
    }
    assert c2["event_required"] == [
        "source_root_job_id",
        "source_job_created_command_id",
        "source_authority_fingerprint",
        "placement_mode",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_job_id",
        "carrier_job_created_command_id",
        "carrier_authority_fingerprint",
        "carrier_generation",
        "carrier_disposition",
        "committed_carrier_attempt_id",
        "selected_worker_id",
        "selected_quota_class",
        "committed_placement_snapshot_digest",
        "commitment_command_id",
        "command_fingerprint",
        "commitment_evidence_digest",
    ]
    assert c2["implementation_waves"] == {
        "existing_session_reuse": {
            "disposition": "reused",
            "status": "HELD_MAT_S1_CURRENT_WRITER_OWNER",
            "wave": "C2-R1B_EXISTING_CARRIER_REUSE",
        },
        "new_session_materialization": {
            "disposition": "created",
            "status": "C2-R1A_INITIAL_CARRIER_COMMITMENT",
            "wave": "C2-R1A_INITIAL_CARRIER_COMMITMENT",
        },
    }
    assert c2["r1a_constraints"] == {
        "forbidden": [
            "extend Runtime.current_harness_binding_source",
            "read OHF epoch/generation tables directly",
            "create a role-null current-writer validator",
        ],
        "supported_modes": ["new_session_materialization"],
    }
    assert c2["r1b_reuse"] == {
        "consumes": "MAT-S1 canonical typed role-null carrier/current-writer read owner",
        "mutates": "only the missing source-root commitment",
        "mutates_carrier_job_attempt_quota_lease_or_fence": False,
    }
    assert c2["new_session_materialization"] == {
        "requires_no_existing_alias_carrier": True,
        "creates_carrier_job": True,
        "creates_carrier_attempt": True,
        "claims_selected_worker_and_quota": True,
        "persists_placement_snapshot": True,
        "appends_one_root_commitment": True,
        "atomic_owner": "one existing BEGIN IMMEDIATE Runtime transaction",
    }
    assert c2["existing_session_reuse"] == {
        "requires_one_exact_current_alias_carrier": True,
        "requires_exact_current_carrier_attempt_and_writer": True,
        "creates_carrier_job": False,
        "creates_carrier_attempt": False,
        "changes_quota_or_lease": False,
        "appends_one_root_commitment": True,
    }
    assert "expected_source_root_revision" in c2["optimistic_preconditions"]
    assert c2["stable_command_fields"] == [
        "source_root_job_id",
        "responsibility_ref",
        "placement_mode",
        "selection_document_digest",
        "selection_evidence_digest",
        "selected_worker_id",
        "selected_quota_class",
        "committed_placement_snapshot_digest",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_generation",
        "carrier_job_created_command_id",
    ]
    for field in (
        "source_root_job_id",
        "source_job_created_command_id",
        "source_authority_fingerprint",
        "placement_mode",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_job_id",
        "carrier_job_created_command_id",
        "carrier_authority_fingerprint",
        "carrier_generation",
        "carrier_disposition",
        "committed_carrier_attempt_id",
        "selected_worker_id",
        "selected_quota_class",
        "committed_placement_snapshot_digest",
        "commitment_command_id",
        "command_fingerprint",
        "commitment_evidence_digest",
    ):
        assert field in c2["event_required"]
    for forbidden in (
        "runtime_binding_id",
        "runtime_binding_generation",
        "provider_session_id",
        "native_handle",
        "account_label",
        "actor binding",
        "aggregation_handoff_command_id",
        "aggregation_handoff_digest",
        "plan_attempt_id",
        "plan_digest",
    ):
        assert forbidden in c2["event_forbidden"]
        assert forbidden not in c2["event_required"]
        assert forbidden not in c2["stable_command_fields"]
    assert c2["source_root_claimed"] is False
    assert c2["caller_may_supply_carrier_identity"] is False
    assert c2["historical_event_is_current_authority"] is False
    assert c2["identical_replay"] == (
        "lookup immutable command then revalidate current source and carrier truth"
    )
    assert c2["changed_payload"] == "COMMAND_REPLAY_CONFLICT"

    mat = contract["mat_s1_writer_materialization"]
    assert mat["owner"] == "existing Operator Harness Runtime broker and Codex adapter"
    assert mat["status"] == "MISSING_SOURCE_IMPLEMENTATION"
    assert mat["entry"] == "bounded role-null CEO-carrier materialization"
    assert mat["consumes_attempt"] == "committed_carrier_attempt_id"
    assert mat["uses_plan_only_supervisor"] is False
    assert mat["fabricates_orchestration_work_admission"] is False
    assert mat["uses_mat_f0_normal_and_reconciled_start_semantics"] is True
    assert mat["runtime_binding_source"] == (
        "exact current CEO carrier Attempt after accepted OHF materialization"
    )
    assert mat["current_writer_read_owner"] == {
        "owner": "one canonical Runtime read owner",
        "provenance": "mastermind.sol_session_carrier/v1",
        "required_evidence": [
            "CEO/role-null/READ-only carrier grant",
            "exact C2 commitment",
            "current OHF epoch/generation/writer",
        ],
    }
    assert mat["source_root_runtime_binding_forbidden"] is True
    assert "no retry failover replacement carrier or G3" in mat["effect_unknown"]

    stage_b = contract["stage_b1_assignment"]
    assert stage_b["owner"] == "Executive Runtime Event plane"
    assert stage_b["status"] == "MISSING_SOURCE_IMPLEMENTATION"
    assert stage_b["mode"] == "INITIAL_ASSIGNMENT"
    assert stage_b["command_schema"] == (
        "mastermind.sol_action_target_assignment_command/v2"
    )
    assert stage_b["event_schema"] == "mastermind.sol_action_target_assignment/v2"
    assert stage_b["aggregate_id"] == "source responsibility root_job_id"
    assert stage_b["event_type"] == "SOL_ACTION_TARGET_ASSIGNED"
    assert stage_b["first_revision"] == 1
    for field in (
        "root_job_id",
        "placement_commitment_command_id",
        "expected_placement_commitment_digest",
        "expected_session_alias",
        "carrier_job_id",
        "carrier_attempt_id",
        "expected_binding_id",
        "expected_binding_generation",
        "expected_target_definition_fingerprint",
    ):
        assert field in stage_b["command_fields"]
    assert stage_b["caller_exposed_destination_or_carrier_fields"] == []
    assert stage_b["stage_a_signature_changed"] is False
    assert stage_b["stage_a_owner"] == "unchanged require_sol_action_authority"
    assert stage_b["complete_map_projection"] is True
    assert stage_b["succession_supported_now"] is False
    assert stage_b["cross_alias_transfer_supported_now"] is False

    for failure in (
        "SOURCE_ROOT_NOT_STRICT_V2_AGGREGATION",
        "TARGET_CARRIER_MISSING",
        "TARGET_CARRIER_CARDINALITY_CONFLICT",
        "TARGET_CARRIER_PROVENANCE_INVALID",
        "TARGET_CARRIER_NOT_CEO_OWNED",
        "TARGET_CARRIER_NOT_ROLE_NULL",
        "TARGET_CARRIER_ATTEMPT_MISMATCH",
        "TARGET_CARRIER_NOT_CURRENT",
        "TARGET_CARRIER_SUCCESSION_UNSUPPORTED",
        "PLACEMENT_COMMITMENT_MISSING",
        "TARGET_RUNTIME_NOT_MATERIALIZED",
        "TARGET_ALIAS_ALREADY_BINDS_DIFFERENT_RUNTIME",
        "COMMAND_REPLAY_CONFLICT",
        "EFFECT_UNKNOWN_RECONCILE_FIRST",
    ):
        assert failure in contract["failures"]

    assert contract["no_rebuild"] == {
        "new_tables": [],
        "new_migrations": [],
        "new_lifecycles": [],
        "new_queues": [],
        "new_schedulers": [],
        "new_retry_planes": [],
        "new_target_registries": [],
        "new_runtime_binding_stores": [],
        "new_provider_registries": [],
        "executive_job_attempt_worker_event_owner_duplicated": False,
        "capacity_selector_or_claim_owner_duplicated": False,
        "operator_harness_owner_duplicated": False,
        "stage_a_owner_changed": False,
    }
    assert contract["ordered_waves"] == [
        "STAGE_B_R2_RECORDS_CORRECTION",
        "CAPACITY_C2_V2_PURE_CONTRACT",
        "CAPACITY_C2_R1A_INITIAL_CARRIER_COMMITMENT",
        "MAT_F0_EFFECT_CERTAIN_PREREQUISITE",
        "MAT_S1_ROLE_NULL_CEO_CARRIER_MATERIALIZATION",
        "STAGE_B1_INITIAL_ASSIGNMENT",
        "CAPACITY_C2_R1B_EXISTING_CARRIER_REUSE",
        "LIVE_PRODUCTION_DISARMED_CANARY",
    ]
    assert contract["release_truth"]["green_ci_is_production_proof"] is False


def test_v6_alias_carrier_contract_is_complete() -> None:
    contract, raw = json_block(DESIGN, BEGIN, END)
    validate_contract(contract)
    assert json.dumps(contract, sort_keys=True, indent=2) == raw.strip()


def test_plan_gate_matches_the_v6_owner_graph() -> None:
    contract, _ = json_block(DESIGN, BEGIN, END)
    gate, raw = json_block(PLAN, GATE_BEGIN, GATE_END)
    assert json.dumps(gate, sort_keys=True, indent=2) == raw.strip()
    assert gate == {
        "schema": "mastermind.autonomy_stage_b1_gate.v6",
        "architecture_revision": REVISION,
        "architecture_operation": OPERATION,
        "records_paths": RECORD_PATHS,
        "records_path_ceiling": 3,
        "predecessors": [
            "STAGE_B_R2_RECORDS_CORRECTION_PROTECTED",
            "EXECUTIVE_CEO_CODEX_A_TARGET_PROTECTED",
            "CAPACITY_C1_PROTECTED",
            "CAPACITY_C2_V2_COMMITMENT_PROTECTED",
            "MAT_F0_EFFECT_CERTAIN_ARCHITECTURE_PROTECTED",
            "MAT_S1_CURRENT_CEO_CARRIER_WRITER_PROTECTED",
        ],
        "implementation_sequence": [
            "C2-PURE",
            "C2-R1A",
            "MAT-S1",
            "STAGE-B1",
            "C2-R1B",
            "PRODUCTION-DISARMED-CANARY",
        ],
        "implementation_dependencies": {
            "C2-R1A": ["C2-PURE"],
            "C2-R1B": ["MAT-S1"],
            "MAT-S1": ["C2-R1A"],
            "MULTI-ROOT-REUSE-CANARY": ["C2-R1B", "STAGE-B1"],
            "STAGE-B1": ["MAT-S1"],
        },
        "source_root_claimed_by_c2": False,
        "carrier_scope": "one alias-scoped carrier, reusable by many source roots",
        "runtime_binding_source": "carrier Attempt only",
        "stage_a_changed": False,
        "production_armed": False,
    }
    assert contract["record_paths"] == gate["records_paths"]


def test_protected_target_is_exact_codex_ceo_and_globally_disarmed() -> None:
    payload = json.loads(read(TARGETS))
    assert payload["production_armed"] is False
    target = payload["targets"]["EXECUTIVE-CEO-CODEX-A"]
    assert target == {
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_seat": "ceo",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "allowed_transports": ["codex-app-server"],
        "workstream": "executive",
        "target_enabled": False,
    }
    assert payload["root_job_bindings"] == {}


def test_current_root_is_coo_aggregation_and_cannot_project_as_ceo() -> None:
    runtime_source = read(EXECUTIVE_RUNTIME)
    tree = ast.parse(runtime_source)
    create_v2 = class_method(tree, "JobRegistry", "create_v2_orchestration_root")
    create_job = class_method(tree, "JobRegistry", "create_job")
    call = one_create_job_call(create_v2)
    keywords = {item.arg: item.value for item in call.keywords if item.arg is not None}
    assert ast.literal_eval(keywords["orchestration_role"]) == "aggregation"
    assert "owner_seat" not in keywords
    assert ast.literal_eval(argument_default(create_job, "owner_seat")) == "coo"

    binding_source = read(RUNTIME_BINDING)
    assert "facts.owner_seat != target.target_seat" in binding_source
    assert "facts.provider" in binding_source
    assert '"openai-codex": "codex"' in binding_source


def test_stage_a_owner_remains_unchanged_and_alias_carrier_free() -> None:
    source = read(STAGE_A)
    assert "def require_sol_action_authority" in source
    assert "sol_session_carrier" not in source
    assert "capacity_placement_commitment/v2" not in source


def test_obsolete_root_claim_model_is_not_normative() -> None:
    design = read(DESIGN)
    plan = read(PLAN)
    for obsolete in (
        "v5.3-post-handoff-aggregation",
        "C2 atomic aggregation-root claim",
        "CAPACITY_C2_ROOT_BOUND_CLAIM_COMMITMENT_PROTECTED",
        "requires_aggregation_attempt_id_from_c2",
        "claim existing canonical aggregation Worker and Attempt owners",
    ):
        assert obsolete not in design
        assert obsolete not in plan


def test_source_law_is_mutation_discriminating() -> None:
    original, _ = json_block(DESIGN, BEGIN, END)

    def mutate(path: tuple[str, ...], value: Any) -> Callable[[dict[str, Any]], None]:
        def apply(candidate: dict[str, Any]) -> None:
            owner: Any = candidate
            for part in path[:-1]:
                owner = owner[part]
            owner[path[-1]] = value
        return apply

    def append(path: tuple[str, ...], value: Any) -> Callable[[dict[str, Any]], None]:
        def apply(candidate: dict[str, Any]) -> None:
            owner: Any = candidate
            for part in path:
                owner = owner[part]
            owner.append(value)
        return apply

    def add(path: tuple[str, ...], value: Any) -> Callable[[dict[str, Any]], None]:
        def apply(candidate: dict[str, Any]) -> None:
            owner: Any = candidate
            for part in path[:-1]:
                owner = owner[part]
            owner[path[-1]] = value
        return apply

    mutations: list[Callable[[dict[str, Any]], None]] = [
        mutate(("current_state", "authorized_modes_now"), ["INITIAL_ASSIGNMENT"]),
        mutate(("current_state", "production_armed"), True),
        mutate(("source_responsibility_root", "remains_unclaimed_by_capacity_c2"), False),
        mutate(("source_responsibility_root", "ceo_office_assignment_requires_coo_handoff"), True),
        mutate(("source_responsibility_root", "stored_owner_seat"), "ceo"),
        mutate(("alias_carrier_owner", "shape", "owner_seat"), "coo"),
        mutate(("alias_carrier_owner", "shape", "orchestration_role"), "aggregation"),
        mutate(("alias_carrier_owner", "shape", "requested_authorities"), ["READ", "WRITE_BRANCH"]),
        mutate(("alias_carrier_owner", "identity_scope"), [
            "session_alias",
            "target_definition_fingerprint",
            "carrier_generation",
            "source_root_job_id",
        ]),
        mutate(("alias_carrier_owner", "one_carrier_per_source_root"), True),
        mutate(("capacity_c2_commitment", "event_schema"), "mastermind.capacity_placement_commitment/v1"),
        mutate(("capacity_c2_commitment", "placement_modes"), ["new_session_materialization"]),
        mutate(("capacity_c2_commitment", "mode_disposition", "new_session_materialization"), "reused"),
        append(("capacity_c2_commitment", "event_required"), "provider"),
        append(("capacity_c2_commitment", "event_required"), "process_id"),
        append(("capacity_c2_commitment", "event_required"), "model"),
        append(("capacity_c2_commitment", "event_required"), "slack_channel_id"),
        append(("capacity_c2_commitment", "event_required"), "runtime_binding_id"),
        add(("capacity_c2_commitment", "provider_evidence"), {"provider": "codex"}),
        mutate(("implementation_dag", "STAGE-B1_INITIAL_ASSIGNMENT"), ["C2-R1B_EXISTING_CARRIER_REUSE"]),
        mutate(("capacity_c2_commitment", "implementation_waves", "existing_session_reuse", "wave"), "C2-R1A_INITIAL_CARRIER_COMMITMENT"),
        mutate(("capacity_c2_commitment", "r1a_constraints", "forbidden"), []),
        mutate(("capacity_c2_commitment", "r1b_reuse", "mutates"), "the carrier and source-root commitment"),
        mutate(("capacity_c2_commitment", "existing_session_reuse", "creates_carrier_attempt"), True),
        mutate(("capacity_c2_commitment", "source_root_claimed"), True),
        mutate(("mat_s1_writer_materialization", "consumes_attempt"), "source_root_attempt_id"),
        mutate(("mat_s1_writer_materialization", "current_writer_read_owner", "owner"), "C2 private validator"),
        mutate(("mat_s1_writer_materialization", "uses_plan_only_supervisor"), True),
        mutate(("stage_b1_assignment", "aggregate_id"), "carrier_job_id"),
        mutate(("stage_b1_assignment", "stage_a_signature_changed"), True),
        mutate(("stage_b1_assignment", "succession_supported_now"), True),
    ]

    for apply in mutations:
        candidate = copy.deepcopy(original)
        apply(candidate)
        try:
            validate_contract(candidate)
        except AssertionError:
            continue
        raise AssertionError("source-law mutation unexpectedly preserved a valid contract")


def test_contract_forbids_every_known_authority_leak() -> None:
    contract, _ = json_block(DESIGN, BEGIN, END)
    serialized = json.dumps(contract, sort_keys=True)
    c2 = contract["capacity_c2_commitment"]
    for forbidden in c2["event_forbidden"]:
        assert forbidden not in c2["event_required"]
    assert '"caller_exposed_destination_or_carrier_fields": []' in serialized
    assert '"source_root_claimed": false' in serialized
    assert '"one_carrier_per_source_root": false' in serialized
