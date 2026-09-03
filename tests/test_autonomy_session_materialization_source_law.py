from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DESIGN = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-09-02-autonomy-session-materialization-mat-f0-design.md"
)
PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-09-02-autonomy-session-materialization-mat-c1.md"
)
SERVICE = ROOT / "control_plane" / "executive_service.py"
SUPERVISOR = ROOT / "control_plane" / "executive_operator_supervisor.py"
ORCHESTRATOR = ROOT / "control_plane" / "operator_harness_orchestrator.py"
PORT = ROOT / "control_plane" / "executive_operator_harness_port.py"
RUNTIME = ROOT / "control_plane" / "executive_runtime.py"
REMOTE = ROOT / "control_plane" / "remote_codex_operator_adapter.py"
BROKER = ROOT / "control_plane" / "executive_worker_broker.py"
CODEX = ROOT / "control_plane" / "codex_operator_adapter.py"
TARGETS = ROOT / "control_plane" / "session_targets.py"
STAGE_A = ROOT / "control_plane" / "sol_action_target.py"
TERMINAL = ROOT / "control_plane" / "executive_terminal_return.py"

RECORD_PATHS = [
    "docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md",
    "docs/superpowers/plans/2026-09-02-autonomy-session-materialization-mat-c1.md",
    "tests/test_autonomy_session_materialization_source_law.py",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json_block(path: Path, begin: str, end: str) -> dict:
    match = re.search(
        re.escape(begin) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(end),
        _text(path),
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def _definition(path: Path, dotted_name: str) -> str:
    source = _text(path)
    nodes = ast.parse(source).body
    selected: ast.AST | None = None
    for part in dotted_name.split("."):
        selected = next(
            node
            for node in nodes
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == part
        )
        nodes = selected.body if isinstance(selected, ast.ClassDef) else []
    assert selected is not None
    return ast.get_source_segment(source, selected) or ""


def _validate_contract(contract: dict) -> None:
    assert contract["schema"] == "mastermind.session_materialization_f0_contract.v1"
    assert (
        contract["operation"]
        == "autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001"
    )
    assert contract["protected_source_sha"] == "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12"
    assert contract["records_wave"] == "MAT-F0"
    assert contract["implementation_wave"] == "MAT-C1"
    assert contract["first_vertical"] == {
        "provider": "openai-codex",
        "surface": "codex-app-server",
        "job_role": "plan",
        "authority": ["READ"],
        "write_capable": False,
        "production_armed": False,
    }
    assert contract["materialization_operation_command"] == "ohf-op:start:<attempt_id>"
    assert contract["provider_call_inside_runtime_transaction"] is False
    assert contract["provider_native_idempotency"] is False

    receipt = contract["worker_receipt"]
    assert receipt["schema"] == "mastermind.operator_materialization_receipt/v1"
    assert receipt["authority"] == "EVIDENCE_ONLY"
    assert (
        receipt["root_owner"]
        == "control_plane.executive_worker_broker.BrokerPolicy.run_root"
    )
    assert (
        receipt["path"]
        == ".operator-materializations/<sha256(operation_command_id)>/receipt.json"
    )
    assert receipt["atomic_create"] is True
    assert receipt["overwrite"] is False
    assert receipt["canonical_digest"] is True
    assert receipt["max_bytes"] == 262144
    assert receipt["fields"] == [
        "schema",
        "operation_command_id",
        "operation_kind",
        "attempt_id",
        "worker_id",
        "session_epoch_id",
        "process_generation_id",
        "generation_number",
        "requested_profile_digest",
        "provider_session_id",
        "process_identity",
        "observed_attestation",
        "process_credentials",
        "provider_home_identity",
        "created_at",
        "receipt_digest",
    ]
    assert "retry permission" in receipt["forbidden_authority"]

    assert contract["materialized_unbound_formula"] == [
        "exact Runtime start INTENT exists",
        "exact Runtime provider-dispatch commitment exists",
        "exact immutable worker materialization receipt exists",
        "matching Runtime bind/APPLIED receipt is absent",
    ]
    assert contract["effect_unknown_law"]["blind_retry"] is False
    assert contract["effect_unknown_law"]["cross_worker_failover"] is False
    assert contract["effect_unknown_law"]["second_attempt"] is False
    assert contract["effect_unknown_law"]["second_provider_start"] is False
    assert (
        contract["effect_unknown_law"]["missing_receipt_after_dispatch"]
        == "MATERIALIZATION_IDENTITY_UNKNOWN / QUARANTINE"
    )
    assert (
        contract["restart_law"]["process_absence_proves_remote_thread_absence"]
        is False
    )
    assert contract["teardown_acceptance"]["process_group_absence_alone"] is False
    assert "wait task terminal or cancelled-and-joined" in contract[
        "teardown_acceptance"
    ]["required"]
    assert (
        contract["teardown_acceptance"]["incomplete_state"]
        == "CLEANUP_INCOMPLETE / NO_ATTEMPT_COMPLETION"
    )
    assert contract["stage_b_separate"] is True
    assert contract["wake_ack_separate"] is True
    assert contract["capacity_selection_separate"] is True
    assert contract["no_rebuild"] == {
        "new_tables": [],
        "new_migrations": [],
        "new_lifecycle_states": [],
        "new_queues": [],
        "new_schedulers": [],
        "new_target_registries": [],
        "new_retry_plane": [],
        "runtime_binding_rows_written_outside_existing_owner": False,
    }
    assert contract["production_arming"] is False
    assert (
        contract["next"]
        == "MAT-C1_EFFECT_CERTAIN_UNBOUND_RECEIPT_AND_RECONCILIATION"
    )


def test_mat_f0_contract_and_mutations_are_discriminating() -> None:
    contract = _json_block(
        DESIGN, "<!-- MAT_F0_CONTRACT_BEGIN -->", "<!-- MAT_F0_CONTRACT_END -->"
    )
    _validate_contract(contract)

    mutations = [
        (("materialization_operation_command",), "MAT-START-<attempt_id>"),
        (("provider_call_inside_runtime_transaction",), True),
        (("provider_native_idempotency",), True),
        (("worker_receipt", "authority"), "LIFECYCLE_AUTHORITY"),
        (("worker_receipt", "overwrite"), True),
        (("effect_unknown_law", "blind_retry"), True),
        (("effect_unknown_law", "second_provider_start"), True),
        (
            ("effect_unknown_law", "missing_receipt_after_dispatch"),
            "RETRY_PROVIDER_START",
        ),
        (
            ("restart_law", "process_absence_proves_remote_thread_absence"),
            True,
        ),
        (("teardown_acceptance", "process_group_absence_alone"), True),
        (("stage_b_separate",), False),
        (("no_rebuild", "new_tables"), ["materializations"]),
        (("production_arming",), True),
    ]
    for path, value in mutations:
        changed = copy.deepcopy(contract)
        cursor = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        with pytest.raises(AssertionError):
            _validate_contract(changed)


def test_mat_c1_gate_is_records_only_and_orders_protection_first() -> None:
    gate = _json_block(PLAN, "<!-- MAT_C1_GATE_BEGIN -->", "<!-- MAT_C1_GATE_END -->")
    assert gate["schema"] == "mastermind.session_materialization_mat_c1_gate.v1"
    assert gate["architecture_schema"] == (
        "mastermind.session_materialization_f0_contract.v1"
    )
    assert gate["protected_source_basis"] == (
        "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12"
    )
    assert gate["records_only"] is True
    assert gate["runtime_effect"] is False
    assert gate["provider_effect"] is False
    assert gate["production_armed"] is False
    assert gate["implementation_state"].startswith("HELD_UNTIL_MAT_F0_PROTECTED")
    assert gate["canonical_start_command"] == "ohf-op:start:<attempt_id>"
    assert gate["provider_native_idempotency"] is False
    assert gate["stage_b"] == "SEPARATE_AND_HELD"
    assert "MAT-F0 protected" in gate["implementation_predecessors"]
    assert "accepted complete teardown lifecycle" in gate[
        "production_canary_predecessors"
    ]

    plan = _text(PLAN)
    assert plan.index("### Task 0 — Re-pin and reconcile") < plan.index(
        "### Task 2 — Worker-side atomic persistence"
    )
    assert plan.index("This plan is not authority") < plan.index(
        "## 8. Ordered implementation"
    )


def test_current_control_chain_is_real_and_provider_is_after_runtime_intent() -> None:
    service = _text(SERVICE)
    supervisor = _definition(SUPERVISOR, "ExecutiveOperatorSupervisor.start_cycle_job")
    run_claimed = _definition(SUPERVISOR, "ExecutiveOperatorSupervisor._run_claimed")
    start = _definition(ORCHESTRATOR, "OperatorHarnessOrchestrator.start_attempt")
    port = _text(PORT)

    assert "coo_operator_harness_armed: bool = False" in service
    assert "coo_autonomy_armed: bool = False" in service
    assert "job.orchestration_role != \"plan\"" in supervisor
    assert "dispatch_cycle_job" in supervisor
    assert 'OperationId(f"ohf-op:start:{attempt_id}")' in run_claimed
    assert "orchestrator.start_attempt" in run_claimed

    order = [
        "begin_operator_session(",
        "commit_operator_provider_dispatch(",
        "self.adapter.start_session(",
        "bind_operator_session(",
    ]
    positions = [start.index(token) for token in order]
    assert positions == sorted(positions)
    assert "_mark_effect_unknown" in start

    for method in (
        "begin_operator_session",
        "bind_operator_session",
        "record_operator_effect_unknown",
        "commit_operator_provider_dispatch",
    ):
        assert f"def {method}" in port


def test_current_worker_chain_exposes_the_unbound_restart_gap() -> None:
    remote = _definition(REMOTE, "RemoteCodexOperatorAdapter.describe_capabilities")
    broker_init = _definition(BROKER, "ExecutiveWorkerBroker.__init__")
    broker_start = _definition(BROKER, "ExecutiveWorkerBroker._ohf_start")
    codex_start = _definition(CODEX, "CodexOperatorAdapter.start_session")
    codex_process = _definition(CODEX, "CodexOperatorAdapter._start_process")
    recovery = _definition(SUPERVISOR, "ExecutiveOperatorSupervisor._recovery_session")
    restart = _definition(SUPERVISOR, "ExecutiveOperatorSupervisor.reconcile_restart")

    assert "supports_provider_native_idempotency=False" in remote
    assert "self._operator_run" in broker_init
    assert "self._operator_terminal" in broker_init
    assert "self._operator_session_attempts" in broker_init
    assert "self._operator_run = state" in broker_start
    assert "materialization-status" not in _text(BROKER)
    assert "del operation_id" in codex_start
    assert '"thread/start"' in codex_process
    assert '"thread/resume"' in codex_process
    assert "operator recovery process identity is incomplete" in recovery
    assert "requeue_lost" in restart
    assert "del requeue_lost" in restart


def test_existing_owners_remain_separate_and_no_records_file_arms_runtime() -> None:
    contract = _json_block(
        DESIGN, "<!-- MAT_F0_CONTRACT_BEGIN -->", "<!-- MAT_F0_CONTRACT_END -->"
    )
    combined = _text(DESIGN) + _text(PLAN)

    assert TARGETS.is_file()
    assert STAGE_A.is_file()
    assert TERMINAL.is_file()
    assert RUNTIME.is_file()
    assert contract["stage_b_separate"] is True
    assert contract["wake_ack_separate"] is True
    assert "production_armed\": true" not in combined
    assert "new materialization service" not in combined.lower()
    assert "MaterializeExecutionSurface" not in combined
    assert RECORD_PATHS == [
        "docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md",
        "docs/superpowers/plans/2026-09-02-autonomy-session-materialization-mat-c1.md",
        "tests/test_autonomy_session_materialization_source_law.py",
    ]
