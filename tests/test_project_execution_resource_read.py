"""Reached current-DATA history and explicit original execution-resource reads.

Actual CREATE/adoption/Git/current DATA/ProjectExecution admission/Runtime
owners run. The incumbent fixture's credential/source seal, physical execution
binding and workspace preparation are declared inert edges. No provider,
socket, installed profile or external repository is touched.
"""
import asyncio
import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
import time

import jwt
import pytest

from common import executive_workspace_contract as workspace_wire
from common import project_execution_private_contract as execution_wire
from common import project_execution_resource_contract as resource_wire
from common.executive_principal_namespace import principal_scope_from_identity
from control_plane import project_execution_admission as execution_source
from control_plane.executive_ceo_ingress import BOOT_PACKET_SCHEMA
from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_runtime import StateConflict
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.project_execution_factory import ProjectExecutionAppFactory
from integrations.mastermind_workspace_app.contract import principal_frame
from tests import test_executive_coo_app as app_tests
from tests.test_coo_project_help_authority import (
    qualified_help, full_joined, owner, env, isolated_git_env, identity,
)
from tests.test_project_execution_factory import invoke
from tests.test_executive_os_phase1fc import _v3_execution_binding


rsa_key = app_tests.rsa_key


def verified(policy, original, rsa_key):
    token = jwt.encode(dict(iss=policy.issuer, sub="inert-chairman", aud=policy.resource,
        client_id="inert-client", scope=" ".join(policy.required_scopes),
        iat=original.issued_at, nbf=original.issued_at, exp=original.expires_at),
        rsa_key, algorithm="RS256", headers={"kid": app_tests.fixture.KID, "typ": "at+jwt"})
    principal = asyncio.run(JwtAuthenticator(policy=policy,
        jwks_cache=app_tests.fixture._FakeJwksCache(rsa_key)).verify_token(token, now=original.issued_at + 5))
    assert principal.subject_digest == original.subject_digest
    assert principal.client_ref == original.client_ref
    return principal


@pytest.fixture
def execution_project(qualified_help, rsa_key, monkeypatch):
    f = qualified_help
    j, planning = f.j, f.j["factory"]
    service, runtime = planning.service, j["runtime"]
    primary = verified(planning.policies.submit, j["args"]["principal"], rsa_key)
    workspace = verified(planning.workspace_policy, j["workspace"], rsa_key)
    initial = runtime.jobs.get_job(f.root)
    assert runtime.jobs.direct_native_provenance(f.root)["project_planning"]["work_ref"] == f.work
    assert not ExecutiveControlService._has_strict_coo_root_identity(initial)
    assert runtime.attempts.list_attempts() == []
    before = asyncio.run(f.workspace.handle_frame(dict(schema=workspace_wire.FRAME_SCHEMA_V2,
        operation="mission_v3", selection=dict(work_ref=f.work, root_job_id=f.root),
        principal=principal_frame(workspace))))
    assert before["ok"] and before["result"]["read_state"]["state"] == "PARTIAL"
    assert before["result"]["transport"]["reason"] == "dispatch_evidence_not_supplied"

    # Existing project execution fixture edges; all source capture, original
    # admission, retained input and root validators remain the actual owners.
    service._service_state = "READY"
    service.config = dataclasses.replace(service.config, coo_foreground_only=False)
    base = service.config.proof_base_sha
    monkeypatch.setattr(service._ceo_ingress_app_binding.grounding_provider, "observe",
        lambda: dict(mastermind_sha=base, macro_sha=j["current"], boot_packet_schema=BOOT_PACKET_SCHEMA))
    binding = {**_v3_execution_binding(), "base_sha": base}
    monkeypatch.setattr(service, "_require_project_execution_binding",
        lambda execution_profile="research_only": copy.deepcopy(binding))
    monkeypatch.setattr(service, "_coo_binding_for_root", lambda root: copy.deepcopy(binding))
    factory = ProjectExecutionAppFactory(planning)
    failures = []
    owner_failures = []
    from control_plane.project_canonical_data import CanonicalProjectDataMode
    original_check = CanonicalProjectDataMode.check
    def check(actual, view, **options):
        try:
            return original_check(actual, view, **options)
        except Exception as error:
            import traceback
            operation = options.get("operation") or view._operation
            owner_failures.append({"type": type(error).__name__,
                "remaining_seconds": round(operation.read_deadline - time.monotonic(), 3),
                "frames": [(row.name, row.lineno) for row in traceback.extract_tb(error.__traceback__)[-10:]]})
            raise
    monkeypatch.setattr(CanonicalProjectDataMode, "check", check)
    original_capture = factory._capture
    def capture(*args, **kwargs):
        try:
            return original_capture(*args, **kwargs)
        except Exception as error:
            import traceback
            failures.append({"type": type(error).__name__, "code": getattr(error, "code", None),
                "frames": [(row.name, row.lineno) for row in traceback.extract_tb(error.__traceback__)[-6:]]})
            raise
    monkeypatch.setattr(factory, "_capture", capture)
    prepared = []
    async def prepare(root, operation):
        operation.require_root(root.job_id)
        assert service._require_project_execution_root(root)
        prepared.append(root.job_id)
    monkeypatch.setattr(factory, "_prepare_workspace", prepare)

    plan = f.workspace._read_project_plan({"work_ref": f.work}, principal_frame(workspace))
    context = execution_wire.context_from_plan(plan)
    assert context["adoption"]["state"] == "AVAILABLE"
    assert context["adoption"]["adopted_source"] == f.source_plan["source"]
    args = dict(operation_key="mmos-project-preview-" + "1" * 40,
        work_ref=f.work, expected_context=context)
    preview = asyncio.run(invoke(factory, primary, args, operation="preview"))
    assert preview["ok"], json.dumps({"preview": preview, "failures": failures, "owner_failures": owner_failures})
    args = dict(work_ref=f.work, expected_context=context,
        context_sha256=preview["data"]["context_sha256"],
        execution_binding_sha256=preview["data"]["execution_binding_sha256"],
        execution_profile="research_only", objective="Continue the original adopted project",
        handoff_text="Keep initial planning and execution roots separate.", continuation_mode="DURABLE")
    scope = principal_scope_from_identity(issuer_digest=primary.issuer_digest,
        subject_digest=primary.subject_digest, client_ref=primary.client_ref, resource=primary.resource)
    args["operation_key"] = execution_wire.operation_key(scope, args)
    result = asyncio.run(invoke(factory, primary, args))
    assert result["ok"], result
    root = runtime.jobs.get_job(result["data"]["receipt"]["job_id"])
    assert root.job_id != f.root and root.root_job_id == root.job_id
    assert ExecutiveControlService._has_strict_coo_root_identity(root)
    assert root.orchestration_role == "aggregation"
    material = execution_source.read_source(runtime, root)
    retained = json.loads(execution_source.read_original_input(factory._supervisor(), material))
    assert retained["project"]["expected_context"] == context
    assert retained["project"]["plan"]["adopted_plan"]["source"] == f.source_plan["source"]
    assert retained["project"]["plan"]["adopted_plan"]["content"].encode() == f.raw_plan
    assert prepared == [root.job_id] and runtime.attempts.list_attempts() == []
    return SimpleNamespace(f=f, root=root, factory=factory, material=material,
        retained=retained, principal=primary, workspace=workspace, args=args, scope=scope,
        initial=initial)


def _events(f):
    return [row.to_dict() for row in f.j["runtime"].events.list_events()]


def _programs(x):
    result = asyncio.run(x.f.workspace.handle_frame(dict(schema=workspace_wire.FRAME_SCHEMA,
        operation="programs", selection=None, principal=principal_frame(x.workspace))))
    assert result["ok"], result
    return result["result"]


def _mission(x, root, work=None):
    return asyncio.run(x.f.workspace.handle_frame(dict(schema=workspace_wire.FRAME_SCHEMA_V2,
        operation="mission_v3", selection=dict(work_ref=work or x.f.work, root_job_id=root),
        principal=principal_frame(x.workspace))))


def test_actual_history_preserves_planning_and_scopes_only_original_execution(execution_project):
    x, f = execution_project, execution_project.f
    events = _events(f)
    programs = _programs(x)
    assert programs["schema"] == "mastermind.workspace_programs.v3"
    project = next(row for row in programs["canonical_projects"] if row["work_ref"] == f.work)
    card = project["control_room"]["autonomy"]["responsibilities"][0]
    assert card["root_job_candidates"] == sorted([f.root, x.root.job_id])
    assert card["runtime_root_state"] == "CONFLICT" and card["root_job_id"] is None
    history = resource_wire.validate_history(project["root_history"], work_ref=f.work)
    planning, execution = [next(row for row in history["roots"] if row["root_job_id"] == job)
        for job in (f.root, x.root.job_id)]
    assert (planning["kind"], planning["purpose"], planning["execution"]) == ("DIRECT_NATIVE_CEO", "PLANNING", None)
    assert (execution["kind"], execution["purpose"]) == ("STRICT_V2_CEO", "PROJECT_EXECUTION")
    assert execution["execution"]["source_sha256"] == execution_wire.digest(x.material)
    assert execution["execution"]["input_reference_sha256"] == execution_wire.digest(x.material["input_reference"])
    response = _mission(x, x.root.job_id)
    assert response["ok"], response
    mission = response["result"]
    assert mission["mission"]["root_job_id"] == x.root.job_id
    assert mission["read_state"]["state"] == "PARTIAL"
    assert mission["transport"]["reason"] == "dispatch_evidence_not_supplied"
    owner = mission["source"]["owner_observation"]
    assert owner["schema"] == "mastermind.workspace_source_observation.v3" and owner["state"] == "SAME"
    selected = dict(work_ref=f.work, root_job_id=x.root.job_id)
    resource = resource_wire.validate_resource(owner["resource"], **selected)
    assert resource["history"]["roots"] == history["roots"]
    assert resource["original_execution"] == execution["execution"]
    assert resource["original_input"] == dict(state="UNAVAILABLE", reason="RETAINED_INPUT_AUTHORITY_NOT_COMPOSED")
    assert resource["current_adoption"] == dict(state="NOT_OBSERVED", reason="CURRENT_ADOPTION_NOT_READ")
    assert resource["execution_authorized"] is False
    from control_plane.coo_principal_mandate import _mission_state
    with pytest.raises(ValueError):
        _mission_state(mission, expected_work_ref=f.work)
    # The original supervisor can still prove the retained input; the read
    # resource does not pretend that this independent authority was composed.
    retained = json.loads(execution_source.read_original_input(x.factory._supervisor(), x.material))
    assert retained["project"]["plan"]["adopted_plan"]["content"].encode() == f.raw_plan
    assert f.j["runtime"].jobs.get_job(f.root) == x.initial
    assert _events(f) == events
    Path("selection-wire-current.json").write_text(json.dumps(dict(programs=programs,
        mission=mission, selection=selected), indent=2, sort_keys=True) + "\n")


def test_original_source_validator_is_shared_and_bounded_cache_does_not_alias(execution_project, monkeypatch):
    x, f = execution_project, execution_project.f
    runtime = f.j["runtime"]
    original = runtime.store.unique_root_created_event(x.root.job_id)
    assert execution_source.validate_original_root_source(x.root, original) == x.material
    changed = copy.deepcopy(original.payload)
    changed["provenance"]["project_execution"]["context_sha256"] = "0" * 64
    with pytest.raises(StateConflict, match="PROJECT_EXECUTION_ORIGINAL_SOURCE_INVALID"):
        execution_source.validate_original_root_source(x.root, dataclasses.replace(original, payload=changed))
    before = _events(f)
    def no_reopen(*args, **kwargs):
        pytest.fail("bounded origin reopened the unique-event registry")
    monkeypatch.setattr(runtime.store, "unique_root_created_event", no_reopen)
    bounded = f.workspace._bounded_runtime(runtime)
    with bounded.observe_bounded_read() as observation:
        observation.discover_job_roots_bounded()
        first = next(row for row in observation.classify_root_origins_bounded() if row.job_id == x.root.job_id)
        assert first.project_execution == x.material
        first.project_execution["context_sha256"] = "0" * 64
        again = next(row for row in observation.classify_root_origins_bounded() if row.job_id == x.root.job_id)
        assert again.project_execution == x.material
    assert observation.receipt.state == "SAME" and _events(f) == before


def test_explicit_history_selection_never_chooses_planning_foreign_or_latest(execution_project):
    x, f = execution_project, execution_project.f
    args = {**x.args, "objective": "A second independently admitted execution resource"}
    args["operation_key"] = execution_wire.operation_key(x.scope, args)
    admitted = asyncio.run(invoke(x.factory, x.principal, args))
    assert admitted["ok"], admitted
    second = admitted["data"]["receipt"]["job_id"]
    assert second not in (f.root, x.root.job_id)
    events = _events(f)
    programs = _programs(x)
    history = next(row["root_history"] for row in programs["canonical_projects"] if row["work_ref"] == f.work)
    assert [row["root_job_id"] for row in history["roots"]] == sorted([f.root, x.root.job_id, second])
    for root in (x.root.job_id, second):
        response = _mission(x, root)
        assert response["ok"], response
        resource = response["result"]["source"]["owner_observation"]["resource"]
        assert resource["selection"]["root_job_id"] == root
        assert resource["history"]["roots"] == history["roots"]
    for root, work in ((f.root, None), ("JOB-999999", None), (x.root.job_id, "WS:FOREIGN")):
        assert _mission(x, root, work)["ok"] is False
    assert _events(f) == events


def test_selected_resource_refuses_late_original_workspace_permission_loss(execution_project, monkeypatch):
    from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime
    x, f = execution_project, execution_project.f
    events = _events(f)
    calls = []
    def original_read(*args, **kwargs):
        value = read_fabric_view_v3_from_runtime(*args, **kwargs)
        calls.append(value)
        document = f.j["document"]
        document["profiles"][document["primary_profile"]]["enabled"] = False
        return value
    monkeypatch.setattr(f.workspace, "_mission_v3_acquire", original_read)
    result = _mission(x, x.root.job_id)
    assert calls and result["ok"] is False
    assert _events(f) == events
