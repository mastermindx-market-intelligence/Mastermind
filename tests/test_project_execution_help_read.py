"""Original private input -> current DATA adoption -> reached bounded help.

Actual disposable Git, original admission, input artifacts, Runtime, service
namespace and Workspace owners run. The inherited source-seal, physical worker
binding and workspace-preparation fixture edges stay explicit; no provider or
Unix listener is invoked by these owner tests.
"""
import asyncio
import copy
import dataclasses
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import pytest

from common import coo_project_help_contract as wire
from common import executive_workspace_contract as workspace_wire
from common import project_execution_private_contract as execution_wire
from control_plane import project_execution_admission as original_input
from control_plane.coo_principal_host import CooHostProvider
from control_plane.coo_project_help_read import capture_project_help_authority
from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
from integrations.mastermind_workspace_app.contract import principal_frame
from integrations.session_bridge.installed import build_runtime_session_bridge
from tests.test_coo_project_help_authority import (
    qualified_help, full_joined, owner, env, isolated_git_env, identity, _frame,
)
from tests.test_project_execution_resource_read import execution_project, rsa_key
from tests.test_workspace_project_git_publisher import git


@pytest.fixture
def execution_help(execution_project):
    x = execution_project
    f = copy.copy(x.f)
    service, runtime = x.factory.service, f.j["runtime"]
    prior_namespace = service._namespace_custody
    assert prior_namespace is None
    directory = runtime.store.path.parent
    lock, marker = directory / "executive-service.lock", directory / "executive-service.running"
    assert not lock.exists() and not marker.exists()
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker.write_text(json.dumps(dict(instance_id=service.instance_id, pid=os.getpid())))
    marker.chmod(0o600)
    custody = ServiceRuntimeNamespaceCustody(runtime=runtime, service_lock_fd=fd,
        lock_path=lock, marker_path=marker, instance_id=service.instance_id)
    prior_bounded = f.workspace._bounded_runtime
    try:
        custody.start()
        service._namespace_custody = custody
        f.workspace._bounded_runtime = custody.bound_runtime
        f.scope = {**f.scope, "root_job_id": x.root.job_id}
        f.root = x.root.job_id
        f.coo["missions"][0]["project_help"] = copy.deepcopy(f.scope)
        reader = original_input.bind_original_input_reader(service, runtime)
        f.provider = CooHostProvider(f.provider.source, f.workspace,
            project_execution_input_reader=reader)
        f.frame = _frame(f)
        f.execution, f.service, f.input_reader, f.custody = x, service, reader, custody
        yield f
    finally:
        f.workspace._bounded_runtime = prior_bounded
        service._namespace_custody = prior_namespace
        custody.close()
        os.close(fd)
        marker.unlink()
        lock.unlink()


def _events(f):
    return [row.to_dict() for row in f.j["runtime"].events.list_events()]


def test_actual_original_input_bytes_qualify_execution_help_without_promoting_workspace(execution_help, monkeypatch, tmp_path):
    f = execution_help
    before = _events(f)
    calls = []
    read = original_input.read_original_input
    def observed(supervisor, material):
        value = read(supervisor, material)
        calls.append((supervisor, copy.deepcopy(material), hashlib.sha256(value).hexdigest()))
        return value
    monkeypatch.setattr(original_input, "read_original_input", observed)
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "never-opened.sock")
    result = asyncio.run(f.provider.read_project_help(f.frame, session_bridge_owner=bridge))
    assert result["schema"] == wire.EXECUTION_RESULT_SCHEMA
    assert result["scope"] == f.scope
    witness = result["original_execution"]
    assert len(calls) == 2 and all(row[0] is f.service.supervisor for row in calls)
    assert all(row[1] == f.execution.material for row in calls)
    assert witness["original_source_sha256"] == execution_wire.digest(f.execution.material)
    assert witness["input_context_sha256"] == f.execution.material["context_sha256"]
    assert witness["input_payload_sha256"] == calls[0][2] == calls[1][2]
    assert witness["input_reference_sha256"] == execution_wire.digest(f.execution.material["input_reference"])
    assert witness["original_source_plan"] == f.source_plan
    assert witness["current_adoption"] == dict(state="MATCHES_ORIGINAL_ADOPTED_SOURCE_AND_BYTES",
        source_plan_sha256=wire.digest(f.source_plan), project_plan_sha256=result["observation"]["project_plan_sha256"])
    assert result["observation"]["mission"]["qualification"] == wire.EXECUTION_READ_QUALIFICATION
    assert result["observation"]["mission"]["mission_read_state"] == "PARTIAL"
    assert result["observation"]["mission"]["transport"] == dict(dispatch_state="UNKNOWN",
        reason="dispatch_evidence_not_supplied", actionable=False, historical=True)
    assert result["targets"]["state"] == "AVAILABLE" and result["targets"]["items"] == []
    assert result["execution_authority"] is False and witness["execution_authorized"] is False
    assert result["native_origin_attested"] is False
    delivered = wire.encode(result)
    assert f.raw_plan not in delivered
    for private in (b"handoff_text", b"terminal-input://", str(f.input_reader._runs_root).encode()):
        assert private not in delivered
    response = asyncio.run(f.workspace.handle_frame(dict(schema=workspace_wire.FRAME_SCHEMA_V2,
        operation="mission_v3", selection=dict(work_ref=f.work, root_job_id=f.root),
        principal=principal_frame(f.j["workspace"]))))
    assert response["ok"] is True
    mission = response["result"]
    assert mission["read_state"]["state"] == "PARTIAL"
    resource = mission["source"]["owner_observation"]["resource"]
    assert resource["original_input"] == dict(state="UNAVAILABLE", reason="RETAINED_INPUT_AUTHORITY_NOT_COMPOSED")
    assert resource["current_adoption"] == dict(state="NOT_OBSERVED", reason="CURRENT_ADOPTION_NOT_READ")
    from control_plane.coo_principal_mandate import _mission_state
    with pytest.raises(ValueError):
        _mission_state(mission, expected_work_ref=f.work)
    assert f.custody._active is None and _events(f) == before
    Path("execution-help-wire-current.json").write_bytes(wire.encode(result) + b"\n")


def _reader_arguments(f):
    plan = f.workspace._read_project_plan({"work_ref": f.work}, principal_frame(f.j["workspace"]))
    return dict(selected_scope=copy.deepcopy(f.scope),
        expected_source_sha256=execution_wire.digest(f.execution.material),
        adopted_content=plan["continuity"]["adoption"]["content"],
        project_plan_sha256=execution_wire.digest(plan))


def test_original_input_owner_refuses_foreign_metadata_and_real_missing_or_corrupt_bytes(execution_help):
    from control_plane import terminal_original_input_artifacts as artifacts
    f = execution_help
    before = _events(f)
    arguments = _reader_arguments(f)
    for fault in ("root", "source", "contract", "bytes"):
        changed = copy.deepcopy(arguments)
        if fault == "root":
            changed["selected_scope"]["root_job_id"] = f.execution.f.root
        elif fault == "source":
            changed["expected_source_sha256"] = "0" * 64
        elif fault == "contract":
            changed["selected_scope"]["source_plan"]["contract_sha256"] = "0" * 64
        else:
            # Identical claimed source/contract hashes cannot replace the
            # actual retained bytes compared against the current Plan body.
            changed["adopted_content"] += "\nChanged actual adopted bytes.\n"
        with pytest.raises(ValueError):
            f.input_reader.read(**changed)
    material = f.execution.material
    key = artifacts._stable_key(material["command_id"], material["principal_scope_sha256"])
    path = Path(f.input_reader._runs_root) / artifacts.PRIVATE_SUBDIR / key / artifacts.ARTIFACT_FILENAME
    held = path.with_name("original-held.bin")
    path.rename(held)
    try:
        with pytest.raises(artifacts.TerminalInputError):
            f.input_reader.read(**arguments)
    finally:
        held.rename(path)
    original = path.read_bytes()
    path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    try:
        with pytest.raises(artifacts.TerminalInputError):
            f.input_reader.read(**arguments)
    finally:
        path.write_bytes(original)
    assert f.input_reader.read(**arguments)["input_payload_sha256"] == material["input_reference"]["payload_sha256"]
    f.provider.project_execution_input_reader = None
    with pytest.raises(ValueError):
        capture_project_help_authority(f.provider, f.frame)
    assert f.custody._active is None and _events(f) == before


@pytest.mark.parametrize("fault", ["binding_identity", "workspace_permission", "source_scope", "reader_identity"])
def test_late_original_input_or_authority_change_withholds_the_help_read(execution_help, monkeypatch, fault):
    f = execution_help
    before, calls = _events(f), []
    read = original_input.read_original_input
    def changed(supervisor, material):
        value = read(supervisor, material)
        calls.append(material["command_id"])
        if len(calls) == 1:
            if fault == "binding_identity":
                monkeypatch.setattr(f.service, "_ceo_ingress_app_binding",
                    dataclasses.replace(f.service._ceo_ingress_app_binding))
            elif fault == "workspace_permission":
                document = f.j["document"]
                document["profiles"][document["primary_profile"]]["enabled"] = False
            elif fault == "source_scope":
                f.coo["missions"][0]["project_help"]["root_job_id"] = f.execution.f.root
            else:
                monkeypatch.setattr(f.provider, "project_execution_input_reader", dataclasses.replace(f.input_reader))
        return value
    monkeypatch.setattr(original_input, "read_original_input", changed)
    with pytest.raises(ValueError):
        asyncio.run(f.provider.read_project_help(f.frame))
    assert len(calls) == 1 and f.custody._active is None and _events(f) == before


def test_actual_adoption_movement_after_original_input_withholds_the_bracketed_result(execution_help, monkeypatch):
    f = execution_help
    before, moved = _events(f), []
    read = original_input.read_original_input
    def changed(supervisor, material):
        value = read(supervisor, material)
        if not moved:
            moved.append(material["command_id"])
            source = f.source_plan["source"]
            path = f.j["integrator"] / source["path"]
            raw = path.read_bytes()
            amended = raw.replace(b"Observe original project help", b"Observe revised project help")
            assert raw != amended
            path.write_bytes(amended)
            git(f.j["integrator"], "add", source["path"])
            git(f.j["integrator"], "commit", "-m", "Fixture next original-input comparison plan")
            revision = git(f.j["integrator"], "rev-parse", "HEAD").strip()
            decision = f.j["integrator"] / "agentos/decisions/DEC-EG2-HELP.md"
            body = decision.read_text()
            assert source["commit"] in body and source["content_sha256"] in body
            decision.write_text(body.replace(source["commit"], revision).replace(
                source["content_sha256"], hashlib.sha256(amended).hexdigest()))
            git(f.j["integrator"], "add", str(decision.relative_to(f.j["integrator"])))
            git(f.j["integrator"], "commit", "-m", "Fixture actual later adopted source")
            git(f.j["integrator"], "push", "origin", "main")
        return value
    monkeypatch.setattr(original_input, "read_original_input", changed)
    with pytest.raises(ValueError):
        asyncio.run(f.provider.read_project_help(f.frame))
    assert moved and f.custody._active is None and _events(f) == before


def test_input_read_deadline_prevents_next_physical_read_after_expiry(execution_help, monkeypatch):
    from control_plane.executive_runtime import RuntimeStore
    f = execution_help
    before = _events(f)
    arguments = _reader_arguments(f)
    calls, sources = [], []
    read, source = original_input.read_original_input, RuntimeStore.unique_root_created_event
    deadline = time.monotonic() + 2
    def read_original(supervisor, material):
        value = read(supervisor, material)
        calls.append(material["command_id"])
        # Actual elapsed time, no clock substitution and no extended cap.
        while time.monotonic() <= deadline:
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        return value
    def source_original(store, *args, **kwargs):
        sources.append(args[0])
        return source(store, *args, **kwargs)
    monkeypatch.setattr(original_input, "read_original_input", read_original)
    monkeypatch.setattr(RuntimeStore, "unique_root_created_event", source_original)
    with pytest.raises(ValueError, match="read deadline expired"):
        f.input_reader.read(**arguments, deadline=deadline)
    assert len(calls) == 1 and len(sources) == 1
    calls.clear(); sources.clear()
    with pytest.raises(ValueError, match="read deadline expired"):
        f.input_reader.read(**arguments, deadline=time.monotonic() - 1)
    assert not calls and not sources and f.custody._active is None and _events(f) == before


def test_cancellation_joins_the_original_input_read_and_leaves_no_target_stage(execution_help, monkeypatch, tmp_path):
    from common.session_bridge_private_contract import SessionBridgeIngressOwner
    f = execution_help
    before = _events(f)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    reads, targets = [], []
    read, target = original_input.read_original_input, SessionBridgeIngressOwner.handle_frame
    def held(supervisor, material):
        entered.set()
        try:
            assert release.wait(5), "original input read was not released by its live caller"
            value = read(supervisor, material)
            reads.append(material["command_id"])
            return value
        finally:
            finished.set()
    async def observed(owner, frame):
        targets.append(frame["tool"])
        return await target(owner, frame)
    monkeypatch.setattr(original_input, "read_original_input", held)
    monkeypatch.setattr(SessionBridgeIngressOwner, "handle_frame", observed)
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "never-opened.sock")
    async def run():
        task = asyncio.create_task(f.provider.read_project_help(f.frame, session_bridge_owner=bridge))
        try:
            assert await asyncio.to_thread(entered.wait, 25), "original read was not reached"
            marker = []
            asyncio.get_running_loop().call_soon(marker.append, "loop progressed")
            await asyncio.sleep(0)
            assert marker == ["loop progressed"]
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and not finished.is_set()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(run())
    assert finished.is_set() and len(reads) == 1 and targets == []
    assert f.custody._active is None and _events(f) == before
