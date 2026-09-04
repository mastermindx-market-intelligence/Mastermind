from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-02-autonomy-session-materialization-mat-c1.md"
CONTRACT = ROOT / "control_plane/operator_harness_contract.py"
RUNTIME = ROOT / "control_plane/executive_runtime.py"
ORCHESTRATOR = ROOT / "control_plane/operator_harness_orchestrator.py"
PORT = ROOT / "control_plane/executive_operator_harness_port.py"
BROKER = ROOT / "control_plane/executive_worker_broker.py"
REMOTE = ROOT / "control_plane/remote_codex_operator_adapter.py"
SUPERVISOR = ROOT / "control_plane/executive_operator_supervisor.py"
BINDING = ROOT / "control_plane/runtime_binding_projection.py"

RECORD_PATHS = [
    "docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md",
    "docs/superpowers/plans/2026-09-02-autonomy-session-materialization-mat-c1.md",
    "tests/test_autonomy_session_materialization_source_law.py",
]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block(path: Path, begin: str, end: str) -> dict:
    found = re.search(
        re.escape(begin) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(end),
        text(path),
        re.DOTALL,
    )
    assert found is not None
    return json.loads(found.group(1))


def definition(path: Path, dotted: str) -> str:
    source = text(path)
    nodes = ast.parse(source).body
    selected: ast.AST | None = None
    for part in dotted.split("."):
        selected = next(
            node
            for node in nodes
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == part
        )
        nodes = selected.body if isinstance(selected, ast.ClassDef) else []
    assert selected is not None
    return ast.get_source_segment(source, selected) or ""


def validate_contract(value: dict) -> None:
    assert value["schema"] == "mastermind.session_materialization_f0_contract.v3"
    assert value["operation"] == (
        "autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001"
    )
    assert value["repair_operation"] == (
        "autonomy-session-materialization-mat-f0-effect-resolution-repair-20260903-sol-001"
    )
    assert value["supersedes"] == [
        "mastermind.session_materialization_f0_contract.v1",
        "mastermind.session_materialization_f0_contract.v2",
    ]
    assert value["protected_source_sha"] == (
        "caa47c1e66fe36dc3521299c918f4b9e7b2a47ca"
    )
    assert value["claim"] == (
        "SPEC_ONLY / EFFECT_RESOLUTION_FROZEN / IMPLEMENTATION_HELD / PRODUCTION_INERT"
    )
    assert value["first_vertical"] == {
        "authority": ["READ"],
        "job_role": "plan",
        "production_armed": False,
        "provider": "openai-codex",
        "surface": "codex-app-server",
        "write_capable": False,
    }
    assert value["materialization_operation_commands"] == {
        "resume_session": "ohf-op:recover-resume:<attempt_id>",
        "start_session": "ohf-op:start:<attempt_id>",
    }
    assert value["provider_call_inside_runtime_transaction"] is False
    assert value["provider_native_idempotency"] is False
    assert value["maximum_generation"] == 2

    receipt = value["worker_receipt"]
    assert receipt["schema"] == "mastermind.operator_materialization_receipt/v1"
    assert receipt["authority"] == "EVIDENCE_ONLY"
    assert receipt["root_owner"].endswith("BrokerPolicy.run_root")
    assert receipt["write_owner"].endswith("ExecutiveWorkerBroker._ohf_start")
    assert receipt["status_owner"].endswith(
        "ExecutiveWorkerBroker._ohf_materialization_status"
    )
    assert receipt["path"] == (
        ".operator-materializations/<sha256(operation_command_id)>/receipt.json"
    )
    assert receipt["atomic_create"] is True
    assert receipt["overwrite"] is False
    assert receipt["canonical_digest"] == (
        "sha256(canonical JSON of every field except receipt_digest)"
    )
    assert "current generation authority" in receipt["forbidden_authority"]
    assert "retry permission" in receipt["forbidden_authority"]

    resolution = value["operation_resolution"]
    assert resolution["terminal_election_owner"].endswith(
        "OperatorHarnessRegistry._materialization_terminal_receipt"
    )
    assert resolution["normal_success"]["receipts"] == ["INTENT", "APPLIED"]
    assert resolution["normal_success"]["admission_schema"].endswith("/v1")
    assert resolution["reconciled_success"] == {
        "admission_schema": "mastermind.orchestration_work_admission/v2",
        "original_applied_receipt": False,
        "receipts": ["INTENT", "EFFECT_UNKNOWN", "RECONCILED"],
        "resolution": "APPLIED",
    }
    assert resolution["reconciled_command_id"] == "<operation_command_id>:reconciled"
    assert resolution["effect_unknown_preserved"] is True
    assert resolution["allowed_success_sets"] == [
        ["INTENT", "APPLIED"],
        ["INTENT", "EFFECT_UNKNOWN", "RECONCILED"],
    ]
    assert ["INTENT", "EFFECT_UNKNOWN", "APPLIED"] in resolution["forbidden_sets"]
    assert ["INTENT", "APPLIED", "RECONCILED"] in resolution["forbidden_sets"]
    assert resolution["ordering"].index("EFFECT_UNKNOWN") < resolution[
        "ordering"
    ].index("RECONCILED")

    runtime = value["runtime_reconciliation"]
    assert runtime["start_owner"].endswith(
        "OperatorHarnessRegistry.reconcile_start_result"
    )
    assert runtime["resume_owner"].endswith(
        "OperatorHarnessRegistry.reconcile_resume_result"
    )
    assert "exact EFFECT_UNKNOWN receipt" in runtime["preconditions"]
    assert "APPLIED absent" in runtime["preconditions"]
    assert any("append exactly one OPERATOR_OPERATION_RECONCILED" in item for item in runtime["atomic_effects"])
    assert any("append no OPERATOR_OPERATION_APPLIED" in item for item in runtime["atomic_effects"])
    assert runtime["matching_replay"] == "NO_OP / SAME_RECONCILED_EVENT"
    assert runtime["changed_replay"] == "STATE_CONFLICT"
    assert runtime["missing_receipt"] == (
        "MATERIALIZATION_IDENTITY_UNKNOWN / QUARANTINE"
    )

    reconciled = value["reconciled_payload"]
    assert reconciled["schema"] == (
        "mastermind.operator_materialization_reconciled/v1"
    )
    assert reconciled["receipt_kind"] == "RECONCILED"
    assert reconciled["resolution"] == "APPLIED"
    assert reconciled["authority"] == "EVIDENCE_RESOLUTION_ONLY"
    assert reconciled["fields"] == [
        "schema_version",
        "operation_kind",
        "resolution",
        "attempt_id",
        "session_epoch_id",
        "process_generation_id",
        "worker_id",
        "provider_session_id",
        "effect_unknown_command_id",
        "materialization_receipt_digest",
        "requested_profile_digest",
    ]

    admission = value["work_admission"]
    assert admission["normal"] == {
        "receipt_field": "tx3_applied_command_id",
        "schema": "mastermind.orchestration_work_admission/v1",
        "terminal_receipt_kind": "APPLIED",
    }
    assert admission["reconciled"]["schema"].endswith("/v2")
    assert admission["reconciled"]["terminal_receipt_kind"] == "RECONCILED"
    assert admission["normal_path_byte_compatible"] is True
    assert admission["mixed_schema_or_mixed_receipt_fields"] == "REFUSE"

    assert value["unbound_formulas"]["G1_START_UNBOUND"][-1] == (
        "matching APPLIED and RECONCILED are absent"
    )
    assert value["unbound_formulas"]["G2_RESUME_UNBOUND"][-1] == (
        "matching APPLIED and RECONCILED are absent"
    )
    for mode in ("G1_START_UNBOUND", "G2_RESUME_UNBOUND"):
        assert any(
            "append RECONCILED and preserve EFFECT_UNKNOWN; never append APPLIED"
            in item
            for item in value["import_law"][mode]
        )
    assert any(
        "never allocate G3" in item
        for item in value["import_law"]["G2_RESUME_UNBOUND"]
    )

    binding = value["current_binding_law"]
    assert binding["owner"].endswith("Runtime.current_harness_binding_source")
    assert binding["projection_owner_unchanged"].endswith(
        "runtime_binding_projection.project_runtime_binding"
    )
    assert len(binding["accepted_lineages"]) == 2
    assert "EFFECT_UNKNOWN without RECONCILED" in binding["rejected_lineages"]
    assert "RECONCILED without EFFECT_UNKNOWN" in binding["rejected_lineages"]

    unresolved = value["unresolved_effect_unknown"]
    assert unresolved["definition"] == (
        "EFFECT_UNKNOWN with no exact later RECONCILED receipt for the same operation"
    )
    assert unresolved["blocks_runtime_binding"] is True
    assert unresolved["blocks_retry_or_failover"] is True
    assert unresolved["deletion_or_overwrite"] is False

    assert value["restart_law"]["process_absence_proves_remote_thread_absence"] is False
    assert value["restart_law"]["worker_receipt_alone_proves_currentness"] is False
    assert value["teardown_acceptance"]["process_group_absence_alone"] is False
    assert "wait task terminal or cancelled-and-joined" in value[
        "teardown_acceptance"
    ]["required"]
    assert value["teardown_acceptance"]["incomplete_state"] == (
        "CLEANUP_INCOMPLETE / NO_ATTEMPT_COMPLETION"
    )
    assert value["stage_b_separate"] is True
    assert value["wake_ack_separate"] is True
    assert value["capacity_selection_separate"] is True
    assert value["no_rebuild"] == {
        "new_lifecycle_states": [],
        "new_migrations": [],
        "new_queues": [],
        "new_retry_plane": [],
        "new_schedulers": [],
        "new_tables": [],
        "new_target_registries": [],
        "runtime_binding_rows_written_outside_existing_owner": False,
    }
    assert value["production_arming"] is False


def test_contract_and_false_support_mutations() -> None:
    value = block(
        DESIGN, "<!-- MAT_F0_CONTRACT_BEGIN -->", "<!-- MAT_F0_CONTRACT_END -->"
    )
    validate_contract(value)
    mutations = [
        (("provider_native_idempotency",), True),
        (("maximum_generation",), 3),
        (("worker_receipt", "authority"), "CURRENT_SESSION_AUTHORITY"),
        (("worker_receipt", "overwrite"), True),
        (
            ("operation_resolution", "reconciled_success", "original_applied_receipt"),
            True,
        ),
        (
            ("operation_resolution", "reconciled_success", "receipts"),
            ["INTENT", "EFFECT_UNKNOWN", "APPLIED"],
        ),
        (
            ("runtime_reconciliation", "start_owner"),
            "OperatorHarnessRegistry.bind_start_result",
        ),
        (("reconciled_payload", "receipt_kind"), "APPLIED"),
        (("work_admission", "normal_path_byte_compatible"), False),
        (("unresolved_effect_unknown", "deletion_or_overwrite"), True),
        (("current_binding_law", "accepted_lineages"), ["receipt exists"]),
        (("teardown_acceptance", "process_group_absence_alone"), True),
        (("no_rebuild", "new_tables"), ["materializations"]),
        (("production_arming",), True),
    ]
    for path, replacement in mutations:
        changed = copy.deepcopy(value)
        cursor = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = replacement
        with pytest.raises(AssertionError):
            validate_contract(changed)


def test_plan_gate_and_order() -> None:
    gate = block(PLAN, "<!-- MAT_C1_GATE_BEGIN -->", "<!-- MAT_C1_GATE_END -->")
    assert gate["schema"] == "mastermind.session_materialization_mat_c1_gate.v3"
    assert gate["architecture_schema"] == (
        "mastermind.session_materialization_f0_contract.v3"
    )
    assert gate["protected_source_basis"] == (
        "caa47c1e66fe36dc3521299c918f4b9e7b2a47ca"
    )
    assert gate["records_only"] is True
    assert gate["runtime_effect"] is False
    assert gate["provider_effect"] is False
    assert gate["production_armed"] is False
    assert gate["resolution_receipts"] == {
        "normal": ["INTENT", "APPLIED"],
        "recovered": ["INTENT", "EFFECT_UNKNOWN", "RECONCILED"],
    }
    assert gate["runtime_reconciliation_methods"] == [
        "OperatorHarnessRegistry.reconcile_start_result",
        "OperatorHarnessRegistry.reconcile_resume_result",
    ]
    assert gate["work_admission_schemas"] == [
        "mastermind.orchestration_work_admission/v1",
        "mastermind.orchestration_work_admission/v2",
    ]
    assert "control_plane/executive_runtime.py" in gate["candidate_paths"]
    assert "control_plane/executive_operator_harness_port.py" in gate[
        "candidate_paths"
    ]
    assert "control_plane/operator_harness_contract.py" in gate["protected_paths"]
    assert "control_plane/operator_harness_orchestrator.py" in gate[
        "protected_paths"
    ]
    assert "control_plane/runtime_binding_projection.py" in gate[
        "protected_paths"
    ]
    assert "MAT-F0 v3 protected" in gate["implementation_predecessors"]

    plan = text(PLAN)
    assert plan.index("### Task 1 — Pure receipt contract") < plan.index(
        "### Task 5 — Runtime terminal-election helper"
    ) < plan.index("### Task 6 — Runtime G1 reconciliation transaction")
    assert "call the new port reconciliation method, not ordinary TX-3" in plan
    assert "call new G2 reconciliation, not ordinary TX-11" in plan
    assert "Transition source law and return" in plan


def test_existing_contract_owns_reconciliation_vocabulary() -> None:
    enum_source = definition(CONTRACT, "OperationReceiptKind")
    resolution_source = definition(CONTRACT, "OperationResolution")
    receipt_id = definition(CONTRACT, "operation_receipt_command_id")
    crash = definition(CONTRACT, "resolve_operation_after_crash")
    assert 'RECONCILED = "OPERATOR_OPERATION_RECONCILED"' in enum_source
    assert 'RECONCILED = "RECONCILED"' in resolution_source
    assert 'OperationReceiptKind.RECONCILED: "reconciled"' in receipt_id
    assert "terminal_receipt is OperationReceiptKind.RECONCILED" in crash
    assert "return OperationResolution.RECONCILED" in crash


def test_current_runtime_proves_v2_was_impossible_and_v3_is_not_built() -> None:
    receipt = definition(RUNTIME, "OperatorHarnessRegistry._receipt")
    bind_start = definition(RUNTIME, "OperatorHarnessRegistry.bind_start_result")
    bind_resume = definition(RUNTIME, "OperatorHarnessRegistry.bind_resume_result")
    unknown = definition(RUNTIME, "OperatorHarnessRegistry.record_effect_unknown")
    seal = definition(RUNTIME, "OperatorHarnessRegistry.seal_attestation")
    binding_source = definition(RUNTIME, "Runtime.current_harness_binding_source")
    source = text(RUNTIME)

    assert "OperationReceiptKind.APPLIED: OperationReceiptKind.EFFECT_UNKNOWN" in receipt
    assert "OperationReceiptKind.EFFECT_UNKNOWN: OperationReceiptKind.APPLIED" in receipt
    assert "operation cannot have both" in receipt
    assert "kind=OperationReceiptKind.APPLIED" in bind_start
    assert "kind=OperationReceiptKind.APPLIED" in bind_resume
    assert "kind=OperationReceiptKind.EFFECT_UNKNOWN" in unknown
    assert "OperationReceiptKind.APPLIED" in seal
    assert "tx3_applied_command_id" in seal
    assert "OperationReceiptKind.APPLIED" in binding_source
    assert "tx3_applied_command_id" in binding_source
    assert "def reconcile_start_result" not in source
    assert "def reconcile_resume_result" not in source
    assert "def _materialization_terminal_receipt" not in source


def test_existing_provider_chain_records_uncertainty_and_remains_single_owner() -> None:
    start = definition(ORCHESTRATOR, "OperatorHarnessOrchestrator.start_attempt")
    resume = definition(ORCHESTRATOR, "OperatorHarnessOrchestrator.resume")
    marker = definition(ORCHESTRATOR, "OperatorHarnessOrchestrator._mark_effect_unknown")
    port = text(PORT)
    broker_dispatch = definition(BROKER, "ExecutiveWorkerBroker._dispatch")
    broker_start = definition(BROKER, "ExecutiveWorkerBroker._ohf_start")
    broker_status = definition(
        BROKER, "ExecutiveWorkerBroker._ohf_materialization_status"
    )
    remote = definition(REMOTE, "RemoteCodexOperatorAdapter.describe_capabilities")
    remote_status = definition(
        REMOTE, "RemoteCodexOperatorAdapter.materialization_status"
    )
    restart = definition(SUPERVISOR, "ExecutiveOperatorSupervisor.reconcile_restart")
    binding_facts = definition(BINDING, "active_operator_binding_facts")
    projection = definition(BINDING, "project_runtime_binding")

    assert "_mark_effect_unknown" in start
    assert 'phase="start_session"' in start
    assert 'phase="bind_start_result"' in start
    assert "_mark_effect_unknown" in resume
    assert 'phase="resume_session"' in resume
    assert 'phase="bind_resume_result"' in resume
    assert "record_operator_effect_unknown" in marker
    assert "def reconcile_operator_start_result" not in port
    assert "def reconcile_operator_resume_result" not in port
    assert 'operation == "ohf-materialization-status"' in broker_dispatch
    assert "return await self._ohf_materialization_status(payload)" in broker_dispatch
    assert "read_operator_materialization_receipt" in broker_status
    assert "self._receipt_matches_request" in broker_status
    assert 'status = "RECEIPT_CURRENT_IN_LIVE_BROKER"' in broker_status
    assert 'status = "RECEIPT_ONLY_AFTER_RESTART"' in broker_status
    assert broker_status.count("read_operator_materialization_receipt") == 1
    assert '"ohf-materialization-status", payload, timeout_seconds=30' in remote_status
    assert "operator_materialization_status(result)" in remote_status
    assert "receipt.operation_command_id == operation_id.command_id" in remote_status
    assert remote_status.count("request_sync(") == 1
    assert broker_start.count("adapter.start_session") == 1
    assert broker_start.count("adapter.resume_session") == 1
    assert broker_start.index("if existing is not None:") < broker_start.index(
        "provider_dispatch_committed = True"
    )
    assert broker_start.index("provider_dispatch_committed = True") < broker_start.index(
        "adapter.start_session"
    )
    assert "if provider_dispatch_committed and state is None:" in broker_start
    assert broker_start.count('"operator materialization effect unknown"') == 2
    assert "provider dispatch has no durable" in broker_start
    assert "supports_provider_native_idempotency=False" in remote
    assert "Generic automatic requeue is intentionally not" in restart
    assert "runtime.current_harness_binding_source" in binding_facts
    assert "connection=connection" in binding_facts
    assert "active_operator_binding_facts" in projection
    assert "connection=connection" in projection
    assert "RuntimeBinding(" in projection


def test_records_only_scope_and_no_arming() -> None:
    value = block(
        DESIGN, "<!-- MAT_F0_CONTRACT_BEGIN -->", "<!-- MAT_F0_CONTRACT_END -->"
    )
    combined = text(DESIGN) + text(PLAN)
    assert value["stage_b_separate"] is True
    assert value["wake_ack_separate"] is True
    assert value["capacity_selection_separate"] is True
    assert '"production_arming":true' not in combined
    assert RECORD_PATHS == [
        "docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md",
        "docs/superpowers/plans/2026-09-02-autonomy-session-materialization-mat-c1.md",
        "tests/test_autonomy_session_materialization_source_law.py",
    ]
