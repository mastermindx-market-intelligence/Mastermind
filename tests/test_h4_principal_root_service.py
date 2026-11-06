from __future__ import annotations

import dataclasses

import pytest

from control_plane.coo_principal_envelope import (
    PrincipalAdmissionContext,
    derive_principal_orchestration_envelope,
)
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import (
    PRINCIPAL_ORCHESTRATION_ROOT_CREATOR,
    Runtime,
)
from tests.test_executive_service import _config, _service


WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"


def _bundle(base_sha: str):
    return derive_principal_orchestration_envelope(
        {
            "operation_key": "h4-principal-service-root",
            "objective": "Coordinate one governed service-bound orchestration episode.",
            "department": "executive-infrastructure",
            "priority": 6,
            "workstream": WORK_REF,
            "business_impact": "routine",
        },
        context=PrincipalAdmissionContext(
            work_ref=WORK_REF,
            principal_binding_digest="1" * 64,
            mission_authority_ref="authority:coo-principal-v2",
            authority_generation_digest="2" * 64,
        ),
        grounding={
            "mastermind_sha": base_sha,
            "macro_sha": "3" * 40,
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
        },
    )


def _dialogue_source():
    return {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": WORK_REF,
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "4" * 40,
            "path": "docs/commissions/claude-capability-hardening-h4.md",
            "content_sha256": "5" * 64,
        },
        "watch_mode": "turn_watch_v1",
    }


def _bound_service(tmp_path, *, operator_harness_armed=False):
    config = _config(
        tmp_path,
        coo_autonomy_armed=operator_harness_armed,
        coo_operator_harness_armed=operator_harness_armed,
    )
    service, _ = _service(tmp_path, config=config)
    # This source-unit test exercises the service's pure/root-binding methods
    # without opening its Unix listener or starting provider execution.
    service.runtime = Runtime.at(service.config.runtime_root)
    return service


def _principal_root(service):
    binding = service._require_current_coo_binding()
    runtime = service._require_runtime()
    root = runtime.jobs.create_principal_orchestration_root(
        _bundle(str(binding["base_sha"])),
        principal_admission_guard=lambda _value: None,
        workspace_root=service.config.proof_workspace_root,
        execution_binding=binding,
        dialogue_source=_dialogue_source(),
        require_dialogue_source=True,
    )
    return root, binding


def test_service_accepts_current_bound_principal_root_and_planner(tmp_path):
    service = _bound_service(tmp_path, operator_harness_armed=True)
    root, binding = _principal_root(service)

    assert root.orchestration_provenance["creator"] == PRINCIPAL_ORCHESTRATION_ROOT_CREATOR
    assert service._coo_root_creator(root) == PRINCIPAL_ORCHESTRATION_ROOT_CREATOR
    assert service._has_strict_coo_root_identity(root)
    assert service._is_bound_coo_root(root)
    assert service._coo_binding_for_root(root) == binding

    outcome = CooCycle(service._require_runtime()).run_once(root.job_id)
    assert outcome.action == "PLANNER_CREATED"
    planner = service._require_runtime().jobs.get_job(outcome.selected_job_id)
    assert planner is not None
    assert service._require_bound_coo_job(planner).job_id == root.job_id
    assert planner.constraints["execution_profile_id"] == binding["operator_execution_profile_id"]
    assert planner.constraints["provider"] == binding["operator_provider"]
    assert planner.constraints["model"] == binding["operator_model"]


def test_principal_root_never_uses_ceo_maintenance_carry(tmp_path, monkeypatch):
    from ops.executive_os import acceptance_maintenance as maintenance

    service = _bound_service(tmp_path)
    root, original = _principal_root(service)
    assert service._is_bound_coo_root(root)

    service.config = dataclasses.replace(
        service.config,
        proof_base_sha="f" * 40,
    )
    service._coo_execution_binding = service._load_coo_execution_binding()

    monkeypatch.setattr(
        maintenance,
        "descriptor_for",
        lambda _sha: pytest.fail("principal root consulted CEO maintenance carry"),
    )

    assert service._coo_binding_for_root(root)["base_sha"] == "f" * 40
    assert service._coo_binding_for_root(root)["base_sha"] != original["base_sha"]
    assert not service._is_bound_coo_root(root)


@pytest.mark.parametrize(
    "fault",
    ["creator", "base", "placement", "worktree", "branch"],
)
def test_principal_service_binding_refuses_root_identity_or_host_drift(tmp_path, fault):
    service = _bound_service(tmp_path)
    root, _ = _principal_root(service)

    if fault == "creator":
        root = dataclasses.replace(
            root,
            orchestration_provenance={
                **root.orchestration_provenance,
                "creator": "unknown-principal",
            },
        )
    elif fault == "base":
        root = dataclasses.replace(
            root,
            constraints={**root.constraints, "base_sha": "f" * 40},
        )
    elif fault == "placement":
        root = dataclasses.replace(
            root,
            constraints={
                **root.constraints,
                "work_placement_union": [
                    {
                        "provider_realm": "foreign",
                        "quota_class": "foreign",
                    }
                ],
            },
        )
    elif fault == "worktree":
        root = dataclasses.replace(root, worktree=None)
    else:
        root = dataclasses.replace(root, branch=None)

    assert not service._is_bound_coo_root(root)


def test_ceo_root_classifier_remains_distinct_from_principal_root(tmp_path):
    service = _bound_service(tmp_path)
    root, _ = _principal_root(service)
    assert service._coo_root_creator(root) == PRINCIPAL_ORCHESTRATION_ROOT_CREATOR
    assert root.orchestration_provenance["creator"] != "ceo_intent"


def test_h4_service_test_is_in_existing_ci_gate():
    from pathlib import Path
    from scripts.ci_pytest import resolve_gate

    root = Path(__file__).resolve().parents[1]
    gate = resolve_gate(root)
    assert "tests/test_h4_principal_root_service.py" in gate["included"]
