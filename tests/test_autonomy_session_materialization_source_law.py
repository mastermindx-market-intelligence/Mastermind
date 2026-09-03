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
SERVICE = ROOT / "control_plane/executive_service.py"
SUPERVISOR = ROOT / "control_plane/executive_operator_supervisor.py"
ORCHESTRATOR = ROOT / "control_plane/operator_harness_orchestrator.py"
PORT = ROOT / "control_plane/executive_operator_harness_port.py"
RUNTIME = ROOT / "control_plane/executive_runtime.py"
REMOTE = ROOT / "control_plane/remote_codex_operator_adapter.py"
BROKER = ROOT / "control_plane/executive_worker_broker.py"
CODEX = ROOT / "control_plane/codex_operator_adapter.py"
TARGETS = ROOT / "control_plane/session_targets.py"
STAGE_A = ROOT / "control_plane/sol_action_target.py"
TERMINAL = ROOT / "control_plane/executive_terminal_return.py"

RECORD_PATHS = [
    "docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md",
    "docs/superpowers/plans/2026-09-02-autonomy-session-materialization-mat-c1.md",
    "tests/test_autonomy_session_materialization_source_law.py",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(path: Path, begin: str, end: str) -> dict:
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


def _validate_contract(value: dict) -> None:
    assert value["schema"] == "mastermind.session_materialization_f0_contract.v2"
    assert value["operation"] == (
        "autonomy-session-materialization-mat-f0-architecture-freeze-20260902-sol-001"
    )
    assert value["protected_source_sha"] == "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12"
    assert value["records_wave"] == "MAT-F0"
    assert value["implementation_wave"] == "MAT-C1"
    assert value["first_vertical"] == {
        "provider": "openai-codex",
        "surface": "codex-app-server",
        "job_role": "plan",
        "authority": ["READ"],
        "write_capable": False,
        "production_armed": False,
    }
    assert value["materialization_operation_commands"] == {
        "start_session": "ohf-op:start:<attempt_id>",
        "resume_session": "ohf-op:recover-resume:<attempt_id>",
    }
    assert value["runtime_bind_owners"] == {
        "start_session": "TX-3 / bind_start_result",
        "resume_session": "TX-11 / bind_resume_result",
        "attestation_and_principal": "TX-4 / seal_attestation",
    }
    assert value["provider_call_inside_runtime_transaction"] is False
    assert value["provider_native_idempotency"] is False
    assert value["maximum_generation"] == 2

    receipt = value["worker_receipt"]
    assert receipt["schema"] == "mastermind.operator_materialization_receipt/v1"
    assert receipt["authority"] == "EVIDENCE_ONLY"
    assert receipt["root_owner"] == (
        "control_plane.executive_worker_broker.BrokerPolicy.run_root"
    )
    assert receipt["write_owner"].endswith("ExecutiveWorkerBroker._ohf_start")
    assert receipt["operation_kinds"] == ["start_session", "resume_session"]
    assert receipt["path"] == (
        ".operator-materializations/<sha256(operation_command_id)>/receipt.json"
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
    assert "current generation" in receipt["forbidden_authority"]

    assert value["unbound_formulas"] == {
        "G1_START_UNBOUND": [
            "exact start INTENT exists",
            "exact start provider-dispatch commitment exists",
            "exact start worker receipt exists",
            "matching TX-3 APPLIED is absent",
        ],
        "G2_RESUME_UNBOUND": [
            "exact resume INTENT exists",
            "exact resume provider-dispatch commitment exists",
            "exact resume worker receipt exists",
            "matching TX-11 APPLIED is absent",
        ],
    }
    assert "TX-3 bind exact historical start observation" in value["import_law"][
        "G1_START_UNBOUND"
    ]
    assert "TX-11 bind exact historical resume observation" in value["import_law"][
        "G2_RESUME_UNBOUND"
    ]
    assert "recover current G2 directly; never allocate G3" in value["import_law"][
        "G2_RESUME_UNBOUND"
    ]

    effect = value["effect_unknown_law"]
    assert effect["same_carrier"] is True
    assert effect["status_read_before_modifying_replay"] is True
    assert effect["blind_retry"] is False
    assert effect["cross_worker_failover"] is False
    assert effect["second_attempt"] is False
    assert effect["second_start"] is False
    assert effect["second_resume"] is False
    assert effect["missing_receipt_after_committed_dispatch"] == (
        "MATERIALIZATION_IDENTITY_UNKNOWN / QUARANTINE"
    )

    restart = value["restart_law"]
    assert "same provider session as G2" in restart["G1_receipt_only"]
    assert "dead G2 cannot create G3" in restart["G2_receipt_only"]
    assert restart["process_absence_proves_remote_thread_absence"] is False

    teardown = value["teardown_acceptance"]
    assert teardown["process_group_absence_alone"] is False
    assert "wait task terminal or cancelled-and-joined" in teardown["required"]
    assert "stdout and stderr pumps terminal with closed descriptors" in teardown[
        "required"
    ]
    assert teardown["incomplete_state"] == (
        "CLEANUP_INCOMPLETE / NO_ATTEMPT_COMPLETION"
    )

    assert value["stage_b_separate"] is True
    assert value["wake_ack_separate"] is True
    assert value["capacity_selection_separate"] is True
    assert value["no_rebuild"] == {
        "new_tables": [],
        "new_migrations": [],
        "new_lifecycle_states": [],
        "new_queues": [],
        "new_schedulers": [],
        "new_target_registries": [],
        "new_retry_plane": [],
        "runtime_binding_rows_written_outside_existing_owner": False,
    }
    assert value["production_arming"] is False
    assert value["next"] == (
        "MAT-C1_EFFECT_CERTAIN_G1_G2_RECEIPT_AND_RECONCILIATION"
    )


def test_mat_f0_contract_and_mutations_are_discriminating() -> None:
    contract = _block(
        DESIGN, "<!-- MAT_F0_CONTRACT_BEGIN -->", "<!-- MAT_F0_CONTRACT_END -->"
    )
    _validate_contract(contract)

    mutations = [
        (("materialization_operation_commands", "resume_session"), "ohf-op:start:<attempt_id>"),
        (("provider_call_inside_runtime_transaction",), True),
        (("provider_native_idempotency",), True),
        (("maximum_generation",), 3),
        (("worker_receipt", "authority"), "CURRENT_SESSION_AUTHORITY"),
        (("worker_receipt", "operation_kinds"), ["start_session"]),
        (("worker_receipt", "overwrite"), True),
        (("effect_unknown_law", "blind_retry"), True),
        (("effect_unknown_law", "second_start"), True),
        (("effect_unknown_law", "second_resume"), True),
        (
            ("effect_unknown_law", "missing_receipt_after_committed_dispatch"),
            "RETRY_PROVIDER",
        ),
        (("restart_law", "process_absence_proves_remote_thread_absence"), True),
        (("teardown_acceptance", "process_group_absence_alone"), True),
        (("stage_b_separate",), False),
        (("no_rebuild", "new_tables"), ["materializations"]),
        (("production_arming",), True),
    ]
    for path, replacement in mutations:
        changed = copy.deepcopy(contract)
        cursor = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = replacement
        with pytest.raises(AssertionError):
            _validate_contract(changed)


def test_mat_c1_gate_covers_both_operations_and_transitions_source_law() -> None:
    gate = _block(PLAN, "<!-- MAT_C1_GATE_BEGIN -->", "<!-- MAT_C1_GATE_END -->")
    assert gate["schema"] == "mastermind.session_materialization_mat_c1_gate.v2"
    assert gate["architecture_schema"] == (
        "mastermind.session_materialization_f0_contract.v2"
    )
    assert gate["protected_source_basis"] == (
        "2c59fc6a987b02b2ca3db4e59fb90a5246eaed12"
    )
    assert gate["records_only"] is True
    assert gate["runtime_effect"] is False
    assert gate["provider_effect"] is False
    assert gate["production_armed"] is False
    assert gate["implementation_state"].startswith("HELD_UNTIL_MAT_F0_PROTECTED")
    assert gate["canonical_operations"] == {
        "G1_START": "ohf-op:start:<attempt_id>",
        "G2_RESUME": "ohf-op:recover-resume:<attempt_id>",
    }
    assert gate["provider_native_idempotency"] is False
    assert gate["maximum_generation"] == 2
    assert gate["stage_b"] == "SEPARATE_AND_HELD"
    assert "tests/test_autonomy_session_materialization_source_law.py" in gate[
        "candidate_paths"
    ]
    assert "control_plane/operator_harness_orchestrator.py" in gate[
        "protected_paths"
    ]
    assert "MAT-F0 protected" in gate["implementation_predecessors"]
    assert "accepted complete teardown lifecycle" in gate[
        "production_canary_predecessors"
    ]

    plan = _text(PLAN)
    assert plan.index("### Task 1 — Pure receipt contract") < plan.index(
        "### Task 5 — G1 import"
    ) < plan.index("### Task 6 — G2 import")
    assert "replace the current `materialization-status` absence" not in plan
    assert "source-law test is a required transition path" in plan


def test_current_control_chain_orders_provider_after_runtime_for_start_and_resume() -> None:
    service = _text(SERVICE)
    supervisor_start = _definition(
        SUPERVISOR, "ExecutiveOperatorSupervisor.start_cycle_job"
    )
    run_claimed = _definition(SUPERVISOR, "ExecutiveOperatorSupervisor._run_claimed")
    recover_one = _definition(SUPERVISOR, "ExecutiveOperatorSupervisor._recover_one")
    recovery_session = _definition(
        SUPERVISOR, "ExecutiveOperatorSupervisor._recovery_session"
    )
    start = _definition(ORCHESTRATOR, "OperatorHarnessOrchestrator.start_attempt")
    resume = _definition(ORCHESTRATOR, "OperatorHarnessOrchestrator.resume")
    port = _text(PORT)

    assert "coo_operator_harness_armed: bool = False" in service
    assert "coo_autonomy_armed: bool = False" in service
    assert 'job.orchestration_role != "plan"' in supervisor_start
    assert "dispatch_cycle_job" in supervisor_start
    assert 'OperationId(f"ohf-op:start:{attempt_id}")' in run_claimed
    assert 'f"ohf-op:recover-resume:{attempt_id}"' in recover_one
    assert 'int(row["generation_number"]) != 1' in recovery_session

    start_order = [
        "begin_operator_session(",
        "commit_operator_provider_dispatch(",
        "self.adapter.start_session(",
        "bind_operator_session(",
    ]
    resume_order = [
        "begin_operator_resume(",
        "commit_operator_provider_dispatch(",
        "resume(",
        "bind_operator_resume(",
    ]
    assert [start.index(token) for token in start_order] == sorted(
        start.index(token) for token in start_order
    )
    assert [resume.index(token) for token in resume_order] == sorted(
        resume.index(token) for token in resume_order
    )
    assert "_mark_effect_unknown" in start
    assert "_mark_effect_unknown" in resume

    for method in (
        "begin_operator_session",
        "bind_operator_session",
        "begin_operator_resume",
        "bind_operator_resume",
        "record_operator_effect_unknown",
        "commit_operator_provider_dispatch",
    ):
        assert f"def {method}" in port


def test_current_worker_chain_exposes_symmetric_unbound_gap() -> None:
    remote = _definition(REMOTE, "RemoteCodexOperatorAdapter.describe_capabilities")
    broker = _text(BROKER)
    broker_init = _definition(BROKER, "ExecutiveWorkerBroker.__init__")
    broker_start = _definition(BROKER, "ExecutiveWorkerBroker._ohf_start")
    codex_start = _definition(CODEX, "CodexOperatorAdapter.start_session")
    codex_resume = _definition(CODEX, "CodexOperatorAdapter.resume_session")
    codex_process = _definition(CODEX, "CodexOperatorAdapter._start_process")

    assert "supports_provider_native_idempotency=False" in remote
    assert 'operation == "ohf-start"' in broker
    assert "self._ohf_start(payload, resume=False)" in broker
    assert 'operation == "ohf-resume"' in broker
    assert "self._ohf_start(payload, resume=True)" in broker
    assert "ohf-materialization-status" not in broker
    assert "self._operator_run" in broker_init
    assert "self._operator_terminal" in broker_init
    assert "self._operator_session_attempts" in broker_init
    assert "self._operator_run = state" in broker_start
    assert "del operation_id" in codex_start
    assert "del operation_id" in codex_resume
    assert '"thread/start"' in codex_process
    assert '"thread/resume"' in codex_process


def test_existing_owners_stay_separate_and_records_do_not_arm_runtime() -> None:
    contract = _block(
        DESIGN, "<!-- MAT_F0_CONTRACT_BEGIN -->", "<!-- MAT_F0_CONTRACT_END -->"
    )
    combined = _text(DESIGN) + _text(PLAN)

    for path in (RUNTIME, TARGETS, STAGE_A, TERMINAL):
        assert path.is_file()
    assert contract["stage_b_separate"] is True
    assert contract["wake_ack_separate"] is True
    assert contract["capacity_selection_separate"] is True
    assert '"production_arming": true' not in combined
    assert "MaterializeExecutionSurface" not in combined
    assert RECORD_PATHS == [
        "docs/superpowers/specs/2026-09-02-autonomy-session-materialization-mat-f0-design.md",
        "docs/superpowers/plans/2026-09-02-autonomy-session-materialization-mat-c1.md",
        "tests/test_autonomy_session_materialization_source_law.py",
    ]
