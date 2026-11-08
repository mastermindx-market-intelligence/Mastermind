"""Authenticated project admission with real Runtime, source custody and replay.

Canonical repository observations and physical workspace preparation are inert
fixture seams here. No installed provider, worker START or production service
is exercised. The hierarchy service tests cover actual nested Runtime effects.
"""
import asyncio
import copy
import dataclasses
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import project_execution_private_contract as wire
from common.executive_principal_namespace import principal_scope_from_identity
from control_plane import ceo_intent, project_execution_admission as source_owner
from control_plane.foreground_operation import _project_execution_foreground_dispatch
from integrations.mastermind_executive_app.project_execution_factory import ProjectExecutionAppFactory
from tests.test_project_planning_factory import fixture as planning_fixture
from tests.test_executive_os_phase1fc import _v3_execution_binding


def fixture(tmp_path, monkeypatch, *, mode="DURABLE"):
    planning, old, armed, _ = planning_fixture(tmp_path, monkeypatch)
    service = planning.service
    service._service_state = "READY"
    service.config = dataclasses.replace(service.config, coo_foreground_only=mode == "ATTENDED")
    source_path = service.config.proof_source_repository / source_owner.COMMISSION_PATH
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes((Path(__file__).resolve().parents[1] / source_owner.COMMISSION_PATH).read_bytes())
    subprocess.run(["git","-C",str(service.config.proof_source_repository),"add",source_owner.COMMISSION_PATH],check=True)
    subprocess.run(["git","-C",str(service.config.proof_source_repository),"commit","-qm","project commission"],check=True)
    base = subprocess.check_output(["git","-C",str(service.config.proof_source_repository),"rev-parse","HEAD"],text=True).strip()
    service.config = dataclasses.replace(service.config, proof_base_sha=base)
    from control_plane.executive_ceo_ingress import BOOT_PACKET_SCHEMA
    monkeypatch.setattr(service._ceo_ingress_app_binding.grounding_provider,"observe",lambda:
        dict(mastermind_sha=base,macro_sha="e"*40,boot_packet_schema=BOOT_PACKET_SCHEMA))
    binding = {**_v3_execution_binding(), "base_sha":base}
    monkeypatch.setattr(service,"_require_project_execution_binding",lambda execution_profile="research_only":copy.deepcopy(binding))
    monkeypatch.setattr(service,"_coo_binding_for_root",lambda root:copy.deepcopy(binding))
    view = SimpleNamespace(code_commit="1"*40,data_commit="e"*40,check=lambda:None)
    monkeypatch.setattr(planning,"_canonical_view",lambda *_:view)
    factory = ProjectExecutionAppFactory(planning)
    context = wire.context_from_plan(planning.plan_reader.read(work_ref=old["work_ref"]))
    data = dict(expected_context=context,plan=dict(authored_record="Exact original project",adopted_plan="Exact adopted body"),files=[])
    scope = principal_scope_from_identity(issuer_digest=old["principal"].issuer_digest,
        subject_digest=old["principal"].subject_digest,client_ref=old["principal"].client_ref,resource=old["principal"].resource)
    def capture(principal, args):
        _, _, actual, stamp = factory._authorize(principal,args)
        assert actual == scope
        return dict(data=copy.deepcopy(data),context_sha256=wire.digest(data),workspace_permission=stamp,principal_scope=scope,view=view)
    monkeypatch.setattr(factory,"_capture",capture)
    prepared = []
    async def prepare(root, operation):
        operation.require_root(root.job_id)
        assert service._require_project_execution_root(root)
        prepared.append(root.job_id)
    monkeypatch.setattr(factory,"_prepare_workspace",prepare)
    args = dict(work_ref=old["work_ref"],expected_context=context,context_sha256=wire.digest(data),
        execution_binding_sha256=wire.digest(binding),execution_profile="research_only",
        objective="Complete the exact project",handoff_text="Original private handoff",continuation_mode=mode)
    args["operation_key"] = wire.operation_key(scope,args)
    return factory, old["principal"], args, armed, prepared


async def invoke(factory, principal, args, operation="submit", *, raise_errors=False):
    p = dataclasses.asdict(principal); p["scopes"] = list(p["scopes"])
    w = dataclasses.asdict(factory.planning._test_workspace_principal); w["scopes"] = list(w["scopes"])
    frame = dict(schema=wire.SCHEMA,operation=operation,arguments=copy.deepcopy(args),
        principal=p,workspace_principal=w)
    async with _project_execution_foreground_dispatch(factory.service._require_runtime(),frame,lambda:None):
        if raise_errors:
            return dict(ok=True,data=await factory.submit(principal,args))
        return await factory.handle_frame(frame)


def test_composed_submit_retains_input_and_replays_before_current_source(tmp_path,monkeypatch):
    factory, principal, args, _, prepared = fixture(tmp_path,monkeypatch)
    first = asyncio.run(invoke(factory,principal,args,raise_errors=True))
    assert first["ok"], first
    receipt = first["data"]["receipt"]
    assert receipt["schema"] == ceo_intent.RECEIPT_SCHEMA_V2
    runtime = factory.service._require_runtime()
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root.orchestration_role == "aggregation" and root.root_job_id == root.job_id
    assert root.constraints["operator_harness_armed"] is False
    material = source_owner.read_source(runtime,root)
    private = json.loads(source_owner.read_original_input(factory._supervisor(),material))
    assert private["request"]["handoff_text"] == "Original private handoff"
    assert private["project"]["plan"]["adopted_plan"] == "Exact adopted body"
    assert private["grounding"]["macro_sha"] == "e"*40
    assert source_owner.input_for_job(factory._supervisor(),root) == wire.canonical(private).decode()
    assert prepared == [root.job_id] and runtime.attempts.list_attempts() == []
    def forbidden(*_,**__): raise AssertionError("replay consulted fresh launch data")
    monkeypatch.setattr(factory,"_capture",forbidden)
    monkeypatch.setattr(factory,"_binding",forbidden)
    monkeypatch.setattr(factory,"_fixed_source",forbidden)
    again = asyncio.run(invoke(factory,principal,args))
    assert again["ok"] and again["data"]["receipt"]["job_id"] == root.job_id
    assert len(runtime.jobs.list_jobs()) == 1 and prepared == [root.job_id]
    status = asyncio.run(invoke(factory,principal,{k:args[k] for k in ("operation_key","work_ref")},"status"))
    assert status["ok"] and status["data"]["receipt"]["job_id"] == root.job_id


def test_changed_original_handoff_conflicts_without_second_root(tmp_path,monkeypatch):
    factory, principal, args, _, _ = fixture(tmp_path,monkeypatch)
    assert asyncio.run(invoke(factory,principal,args))["ok"]
    changed = {**args,"handoff_text":"Different private handoff"}
    result = asyncio.run(invoke(factory,principal,changed))
    assert not result["ok"] and result["error"]["code"] == "operation_conflict"
    assert len(factory.service.runtime.jobs.list_jobs()) == 1


def test_current_authority_withdrawal_rolls_back_job_and_event(tmp_path,monkeypatch):
    factory, principal, args, armed, _ = fixture(tmp_path,monkeypatch)
    store = factory.service.runtime.store
    original = store.append_event
    def withdraw(connection,**event):
        result = original(connection,**event)
        if event.get("event_type") == "JOB_CREATED": armed[0] = False
        return result
    monkeypatch.setattr(store,"append_event",withdraw)
    result = asyncio.run(invoke(factory,principal,args))
    assert not result["ok"], result
    assert factory.service.runtime.jobs.list_jobs() == []
    with store.read() as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE event_type='JOB_CREATED'").fetchone()[0] == 0


def test_post_commit_failure_reconciles_original_without_restarting(tmp_path,monkeypatch):
    factory, principal, args, _, _ = fixture(tmp_path,monkeypatch)
    async def fail(*_): raise RuntimeError("lost workspace response")
    monkeypatch.setattr(factory,"_prepare_workspace",fail)
    result = asyncio.run(invoke(factory,principal,args))
    assert not result["ok"] and result["error"]["code"] == "effect_unknown"
    root = factory.service.runtime.jobs.list_jobs()[0]
    status = asyncio.run(invoke(factory,principal,{k:args[k] for k in ("operation_key","work_ref")},"status"))
    assert status["ok"] and status["data"]["receipt"]["job_id"] == root.job_id
    assert len(factory.service.runtime.jobs.list_jobs()) == 1


def test_forged_job_cannot_read_another_root_private_brief(tmp_path,monkeypatch):
    factory, principal, args, _, _ = fixture(tmp_path,monkeypatch)
    result = asyncio.run(invoke(factory,principal,args))
    assert result["ok"], result
    runtime = factory.service.runtime
    root = runtime.jobs.get_job(result["data"]["receipt"]["job_id"])
    foreign = runtime.jobs.create_job("Unrelated job")
    forged = dataclasses.replace(foreign,root_job_id=root.job_id,parent_job_id=root.job_id,depth=1)
    with pytest.raises(ValueError,match="LINEAGE"):
        source_owner.input_for_job(factory._supervisor(),forged)


def test_project_source_cannot_travel_on_legacy_ingress_frame(tmp_path,monkeypatch):
    from control_plane import executive_ceo_ingress as ingress
    factory, _, _, _, _ = fixture(tmp_path,monkeypatch)
    with pytest.raises(ingress.CeoIngressError):
        asyncio.run(ingress.handle_frame({"schema":ingress.STATUS_SCHEMA,"intent_id":"irrelevant"},
            runtime=factory.service.runtime,grounding_provider=factory.app_binding.grounding_provider,
            workspace_root=factory.service.config.proof_workspace_root,project_execution_source={}))


def test_separate_attempt_store_uses_one_explicit_original_input_owner(tmp_path,monkeypatch):
    from control_plane.executive_supervisor import ExecutiveSupervisor
    factory, principal, args, _, _ = fixture(tmp_path,monkeypatch)
    result = asyncio.run(invoke(factory,principal,args,raise_errors=True))
    primary = factory._supervisor()
    root = factory.service.runtime.jobs.get_job(result["data"]["receipt"]["job_id"])
    secondary = ExecutiveSupervisor(primary.runtime,object(),runs_root=tmp_path/"separate-runs",
        inspector=object(),process_controller=object(),instance_id=primary.instance_id,project_input_owner=primary)
    assert source_owner.input_for_job(secondary,root) == source_owner.input_for_job(primary,root)
    assert not (tmp_path/"separate-runs"/"terminal-original-inputs").exists()
    uncomposed = ExecutiveSupervisor(primary.runtime,object(),runs_root=tmp_path/"uncomposed",
        inspector=object(),process_controller=object(),instance_id=primary.instance_id)
    from control_plane.terminal_original_input_artifacts import TerminalInputError
    with pytest.raises(TerminalInputError):
        source_owner.input_for_job(uncomposed,root)

def test_multiline_goal_is_preserved_privately_with_scalar_intent(tmp_path,monkeypatch):
    factory, principal, args, _, _ = fixture(tmp_path,monkeypatch)
    args["objective"] = "Research the project.\nThen build it.\tVerify the result."
    scope = principal_scope_from_identity(issuer_digest=principal.issuer_digest,
        subject_digest=principal.subject_digest,client_ref=principal.client_ref,resource=principal.resource)
    args["operation_key"] = wire.operation_key(scope,args)
    result = asyncio.run(invoke(factory,principal,args,raise_errors=True))
    root = factory.service.runtime.jobs.get_job(result["data"]["receipt"]["job_id"])
    private = json.loads(source_owner.read_original_input(factory._supervisor(),source_owner.read_source(factory.service.runtime,root)))
    assert private["request"]["objective"] == args["objective"]
    assert private["intent"]["objective"] == "Research the project. Then build it. Verify the result."


@pytest.mark.parametrize("fault", ["fake", "issuer_subclass", "foreign_service", "foreign_runtime", "foreign_operation"])
def test_core_source_issuer_cannot_change_actual_service_or_foreground_owner(tmp_path, monkeypatch, fault):
    from control_plane.executive_service import ExecutiveControlService
    from control_plane.executive_runtime import Runtime
    factory, principal, args, _, _ = fixture(tmp_path, monkeypatch)
    issuer = factory._source_issuer
    if fault == "fake":
        factory._source_issuer = SimpleNamespace(service=factory.service)
    elif fault == "issuer_subclass":
        class OtherIssuer(source_owner.ProjectExecutionIssuer):
            pass
        factory._source_issuer = OtherIssuer(issuer._seal, factory.service)
    elif fault in {"foreign_service", "foreign_runtime"}:
        other = ExecutiveControlService(dataclasses.replace(factory.service.config,
            coo_autonomy_armed=False, coo_operator_harness_armed=False, ceo_submit_armed=False))
        other.runtime = (factory.service.runtime if fault == "foreign_service"
                         else Runtime.at(tmp_path / "other-runtime"))
        factory._source_issuer = source_owner.bind_issuer(other)
    else:
        original = source_owner.issue_source
        def different_operation(bound, operation, material, guard):
            # An exact nominal operation from another identity is still not
            # the current request, even if its copied fields look identical.
            return original(bound, copy.copy(operation), material, guard)
        monkeypatch.setattr(source_owner, "issue_source", different_operation)
    refused = asyncio.run(invoke(factory, principal, args))
    assert not refused["ok"]
    assert factory.service.runtime.jobs.list_jobs() == []


def test_core_source_issuer_rejects_fake_and_subclass_services(tmp_path, monkeypatch):
    from control_plane.executive_service import ExecutiveControlService
    with pytest.raises(ValueError, match="ISSUER_REQUIRED"):
        source_owner.bind_issuer(SimpleNamespace())
    class OtherService(ExecutiveControlService):
        pass
    with pytest.raises(ValueError, match="ISSUER_REQUIRED"):
        source_owner.bind_issuer(object.__new__(OtherService))


def test_status_distinguishes_authorized_absence_from_refused_lookup(tmp_path, monkeypatch):
    factory, principal, args, _, prepared = fixture(tmp_path, monkeypatch)
    lookup = {key: args[key] for key in ("operation_key", "work_ref")}
    absent = asyncio.run(invoke(factory, principal, lookup, "status"))
    assert absent["ok"] and absent["data"]["state"] == "NOT_FOUND"
    assert absent["data"]["receipt"] is None

    factory.planning._test_bindings[0]["profiles"]["member-0"]["enabled"] = False
    refused = asyncio.run(invoke(factory, principal, lookup, "status"))
    assert not refused["ok"] and refused["data"] is None
    assert refused["error"] == {
        "code": "refused",
        "message": "Project execution is unavailable for this request",
    }
    runtime = factory.service._require_runtime()
    assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []
    assert prepared == []


def test_failed_status_read_returns_opaque_refusal_without_another_store_read(tmp_path, monkeypatch):
    factory, principal, args, _, prepared = fixture(tmp_path, monkeypatch)
    runtime = factory.service._require_runtime()
    reads = []

    def unavailable(command):
        reads.append(command)
        raise ConnectionError("private storage failure must not escape the response")

    async def read_status():
        p = dataclasses.asdict(principal); p["scopes"] = list(p["scopes"])
        w = dataclasses.asdict(factory.planning._test_workspace_principal)
        w["scopes"] = list(w["scopes"])
        frame = dict(schema=wire.SCHEMA, operation="status",
            arguments={key: args[key] for key in ("operation_key", "work_ref")},
            principal=p, workspace_principal=w)
        async with _project_execution_foreground_dispatch(runtime, frame, lambda: None):
            # The existing foreground owner has admitted this read. Fail the
            # original-status lookup, not its earlier authorization boundary.
            monkeypatch.setattr(runtime.store, "find_event_by_command_id", unavailable)
            return await factory.handle_frame(frame)

    refused = asyncio.run(read_status())
    assert not refused["ok"] and refused["data"] is None
    assert refused["error"] == {
        "code": "refused",
        "message": "Project execution is unavailable for this request",
    }
    assert len(reads) == 1
    assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []
    assert prepared == []


@pytest.mark.parametrize("authority_change", [
    "unchanged", "execution_disarmed", "workspace_revoked", "expired_token",
])
def test_lost_submit_reopens_original_durable_job_without_fresh_plan_or_dispatch(
    tmp_path, monkeypatch, authority_change,
):
    """H4/H5 source qualification: response loss followed by a cold owner reopen.

    Runtime, Job/Event persistence, private input custody and the authenticated
    request owner are real. Source observations and physical worker preparation
    remain the existing fixture seams; no installed runtime or provider is used.
    """
    from control_plane.workspace_source_operations import SourceOperationEvents
    from integrations.mastermind_executive_app.project_planning_factory import (
        ProjectPlanningAppFactory,
    )
    from tests.test_project_execution_service import _reopen_project_service

    factory, principal, args, armed, _ = fixture(tmp_path, monkeypatch)
    attempts_to_prepare = []

    async def lose_response(root, operation):
        operation.require_root(root.job_id)
        attempts_to_prepare.append(root.job_id)
        raise ConnectionError("response lost after the original Job committed")

    monkeypatch.setattr(factory, "_prepare_workspace", lose_response)
    lost = asyncio.run(invoke(factory, principal, args))
    assert not lost["ok"] and lost["error"]["code"] == "effect_unknown"
    original_runtime = factory.service._require_runtime()
    original_job = original_runtime.jobs.list_jobs()[0]
    original_event = original_runtime.store.unique_root_created_event(original_job.job_id)
    original_source = source_owner.read_source(original_runtime, original_job)
    original_input = source_owner.read_original_input(factory._supervisor(), original_source)
    assert attempts_to_prepare == [original_job.job_id]
    assert original_runtime.attempts.list_attempts() == []

    # Drop the Runtime/Store/Supervisor/App-factory objects that submitted the
    # operation. Recovery must derive its answer from retained original owners.
    old_planning = factory.planning
    restored_service = _reopen_project_service(factory.service)
    restored_service._service_state = "READY"
    restored_service._ceo_ingress_ready = True
    planning = ProjectPlanningAppFactory(
        service=restored_service,
        app_binding=restored_service._ceo_ingress_app_binding,
        policies=old_planning.policies,
        reader=old_planning.reader,
        plan_reader=old_planning.plan_reader,
        events=SourceOperationEvents(restored_service.runtime.store),
        workspace_policy=old_planning.workspace_policy,
        load_workspace_bindings=lambda: copy.deepcopy(old_planning._test_bindings[0]),
        policy_loader=old_planning.policy_loader,
        clock=old_planning.clock,
    )
    planning._test_workspace_principal = old_planning._test_workspace_principal
    recovered = ProjectExecutionAppFactory(planning)

    def forbidden(*_, **__):
        raise AssertionError("original reconciliation consulted fresh plan or dispatch")

    for name in ("_capture", "_binding", "_fixed_source", "_prepare_workspace"):
        monkeypatch.setattr(recovered, name, forbidden)
    monkeypatch.setattr(planning, "_canonical_plan", forbidden)
    monkeypatch.setattr(planning, "_canonical_view", forbidden)

    if authority_change == "execution_disarmed":
        armed[0] = False
    elif authority_change == "workspace_revoked":
        old_planning._test_bindings[0]["profiles"]["member-0"]["enabled"] = False
    elif authority_change == "expired_token":
        principal = dataclasses.replace(principal, expires_at=int(planning.clock()) - 1)

    lookup = {key: args[key] for key in ("operation_key", "work_ref")}
    if authority_change == "expired_token":
        # The existing foreground owner refuses an expired principal before the
        # App factory can read the original event; it is not an unknown effect.
        from control_plane.foreground_operation import ForegroundOperationRefusal

        for selected, operation in ((lookup, "status"), (args, "submit")):
            with pytest.raises(ForegroundOperationRefusal, match="principal window is not live"):
                asyncio.run(invoke(recovered, principal, selected, operation))
    else:
        status = asyncio.run(invoke(recovered, principal, lookup, "status"))
        replay = asyncio.run(invoke(recovered, principal, args))
        if authority_change in {"unchanged", "execution_disarmed"}:
            assert status["ok"] and replay["ok"], (status, replay)
            for response in (status, replay):
                assert response["data"]["receipt"]["job_id"] == original_job.job_id
                assert response["data"]["receipt"]["intent_id"] == original_source["intent_id"]
            changed = {**args, "handoff_text": "A different turn cannot replace the original"}
            conflict = asyncio.run(invoke(recovered, principal, changed))
            assert not conflict["ok"] and conflict["error"]["code"] == "operation_conflict"
        else:
            assert not status["ok"] and not replay["ok"]
            assert status["data"] is None and replay["data"] is None
            assert status["error"] == {
                "code": "refused",
                "message": "Project execution is unavailable for this request",
            }
            # The failed read does not resolve the earlier submission. Its
            # original effect remains uncertain until authority is restored.
            assert replay["error"]["code"] == "effect_unknown"
            old_planning._test_bindings[0]["profiles"]["member-0"]["enabled"] = True
            for selected, operation in ((lookup, "status"), (args, "submit")):
                restored = asyncio.run(invoke(recovered, principal, selected, operation))
                assert restored["ok"], restored
                assert restored["data"]["receipt"]["job_id"] == original_job.job_id
                assert restored["data"]["receipt"]["intent_id"] == original_source["intent_id"]

    runtime = restored_service._require_runtime()
    assert runtime is not original_runtime and runtime.store is not original_runtime.store
    assert runtime.store.path == original_runtime.store.path
    assert [job.job_id for job in runtime.jobs.list_jobs()] == [original_job.job_id]
    assert runtime.attempts.list_attempts() == []
    assert runtime.store.unique_root_created_event(original_job.job_id).to_dict() == original_event.to_dict()
    assert source_owner.read_source(runtime, runtime.jobs.get_job(original_job.job_id)) == original_source
    assert source_owner.read_original_input(recovered._supervisor(), original_source) == original_input
    assert attempts_to_prepare == [original_job.job_id]


@pytest.mark.parametrize("operation,boundary,change", [
    ("status", "input", "workspace_revoked"),
    ("submit", "input", "workspace_revoked"),
    ("status", "receipt", "permission_changed"),
    ("submit", "receipt", "permission_changed"),
    ("status", "input", "invocation_closed"),
    ("status", "receipt", "principal_expired"),
    ("status", "receipt", "execution_disarmed"),
])
def test_original_reconciliation_rechecks_read_authority_before_return(
    tmp_path, monkeypatch, operation, boundary, change,
):
    """A lost submit stays original when access changes during its retained read."""
    from control_plane.foreground_operation import current_foreground_operation

    factory, principal, args, armed, prepared = fixture(tmp_path, monkeypatch)

    async def lose_response(root, invocation):
        invocation.require_root(root.job_id)
        prepared.append(root.job_id)
        raise ConnectionError("response lost after original commit")

    monkeypatch.setattr(factory, "_prepare_workspace", lose_response)
    lost = asyncio.run(invoke(factory, principal, args))
    assert not lost["ok"] and lost["error"]["code"] == "effect_unknown"
    runtime = factory.service._require_runtime()
    (root,) = runtime.jobs.list_jobs()
    event = runtime.store.unique_root_created_event(root.job_id).to_dict()
    material = source_owner.read_source(runtime, root)
    retained = source_owner.read_original_input(factory._supervisor(), material)
    before_bindings = copy.deepcopy(factory.planning._test_bindings[0])
    original_time = factory.planning.clock()
    now = [original_time]
    monkeypatch.setattr(factory.planning, "clock", lambda: now[0])

    def forbidden(*_, **__):
        raise AssertionError("original read consulted fresh plan, arm or dispatch")

    for name in ("_capture", "_binding", "_fixed_source", "_prepare_workspace"):
        monkeypatch.setattr(factory, name, forbidden)

    changes = []

    def change_access():
        changes.append(change)
        member = factory.planning._test_bindings[0]["profiles"]["member-0"]
        if change == "workspace_revoked":
            member["enabled"] = False
        elif change == "permission_changed":
            member["binding"]["permission_digest"] = "7" * 64
        elif change == "invocation_closed":
            current_foreground_operation()._mark_source_closed()
        elif change == "principal_expired":
            now[0] = principal.expires_at
        else:
            armed[0] = False

    target, name = ((source_owner, "read_original_input") if boundary == "input"
                    else (ceo_intent, "resolve_intent"))
    actual_read = getattr(target, name)

    def read_then_change(*positional, **keywords):
        result = actual_read(*positional, **keywords)
        change_access()
        return result

    lookup = {key: args[key] for key in ("operation_key", "work_ref")}
    with monkeypatch.context() as during:
        during.setattr(target, name, read_then_change)
        response = asyncio.run(invoke(factory, principal,
            lookup if operation == "status" else args, operation))
    assert changes == [change]
    if change == "execution_disarmed":
        # Reconciliation needs current read access, never a fresh execution arm.
        assert response["ok"] and response["data"]["receipt"]["job_id"] == root.job_id
    else:
        assert not response["ok"] and response["data"] is None, response
        expected_code = ("effect_unknown" if operation == "submit" else
                         "context_changed" if change == "permission_changed" else "refused")
        assert response["error"]["code"] == expected_code
        if operation == "status":
            assert response["error"]["message"] == "Project execution is unavailable for this request"

    factory.planning._test_bindings[0] = before_bindings
    now[0] = original_time
    armed[0] = True
    for selected, original_operation in ((lookup, "status"), (args, "submit")):
        restored = asyncio.run(invoke(factory, principal, selected, original_operation))
        assert restored["ok"], restored
        assert restored["data"]["receipt"]["job_id"] == root.job_id
        assert restored["data"]["receipt"]["intent_id"] == material["intent_id"]
    assert [job.job_id for job in runtime.jobs.list_jobs()] == [root.job_id]
    assert runtime.attempts.list_attempts() == []
    assert runtime.store.unique_root_created_event(root.job_id).to_dict() == event
    assert source_owner.read_source(runtime, runtime.jobs.get_job(root.job_id)) == material
    assert source_owner.read_original_input(factory._supervisor(), material) == retained
    assert prepared == [root.job_id]


@pytest.mark.parametrize("change", ["workspace_revoked", "permission_changed"])
def test_original_absence_requires_authority_through_the_completed_lookup(
    tmp_path, monkeypatch, change,
):
    factory, principal, args, _, prepared = fixture(tmp_path, monkeypatch)
    runtime = factory.service._require_runtime()
    lookup = {key: args[key] for key in ("operation_key", "work_ref")}
    before = copy.deepcopy(factory.planning._test_bindings[0])
    reads = []
    actual_find = runtime.store.find_event_by_command_id

    def find_then_change(command):
        result = actual_find(command)
        assert result is None
        reads.append(command)
        member = factory.planning._test_bindings[0]["profiles"]["member-0"]
        if change == "workspace_revoked":
            member["enabled"] = False
        else:
            member["binding"]["permission_digest"] = "7" * 64
        return result

    async def read_status():
        p = dataclasses.asdict(principal); p["scopes"] = list(p["scopes"])
        w = dataclasses.asdict(factory.planning._test_workspace_principal)
        w["scopes"] = list(w["scopes"])
        frame = dict(schema=wire.SCHEMA, operation="status",
                     arguments=lookup, principal=p, workspace_principal=w)
        async with _project_execution_foreground_dispatch(runtime, frame, lambda: None):
            # Apply the race at the real lookup after this invocation's entry.
            with monkeypatch.context() as during:
                during.setattr(runtime.store, "find_event_by_command_id", find_then_change)
                return await factory.handle_frame(frame)

    refused = asyncio.run(read_status())
    assert not refused["ok"] and refused["data"] is None, refused
    assert refused["error"] == {
        "code": "refused" if change == "workspace_revoked" else "context_changed",
        "message": "Project execution is unavailable for this request",
    }
    assert len(reads) == 1
    factory.planning._test_bindings[0] = before
    restored = asyncio.run(invoke(factory, principal, lookup, "status"))
    assert restored["ok"] and restored["data"]["state"] == "NOT_FOUND"
    assert restored["data"]["receipt"] is None
    assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []
    assert prepared == []
