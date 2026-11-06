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
    monkeypatch.setattr(service,"_require_project_execution_binding",lambda:copy.deepcopy(binding))
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
