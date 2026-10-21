"""Real local chmod/receipt bytes; synthetic principals and worker observations.

These are not Linux realm, actual worker denial or production enrollment proofs.
"""
import asyncio
import copy
import dataclasses
import os
from pathlib import Path
import stat

import pytest

from control_plane.broker_assignment_seal import digest
from control_plane.executive_workspace import _seal_identity
from ops.executive_os import remote_assignment_control as control


def fixture(tmp_path):
    binding = control.AssignmentControlBinding(
        worker_id="WORKER-001", control_uid=os.geteuid(), control_gid=os.getegid(),
        worker_uid=os.geteuid() + 1000, worker_gid=os.getegid() + 1000,
        workspace_root=tmp_path / "workspaces", run_root=tmp_path / "runs")
    paths = binding.paths_for("ATT-001")
    for path in paths.values():
        path.parent.mkdir(mode=0o750)
        path.mkdir(mode=0o770)
        path.chmod(0o770)
        # macOS /tmp inherits wheel rather than the test process primary group.
        # These are fresh test-owned roots, never installed assignment paths.
        os.chown(path.parent, -1, os.getegid())
        os.chown(path, -1, os.getegid())
    # The real temporary files use this test process's group; mock only the
    # synthetic worker GID expectation, never claim a real cross-UID denial.
    binding = dataclasses.replace(binding, worker_gid=os.getegid(), control_gid=os.getegid() + 1)
    snapshot = {"schema_version": "mastermind.worker_assignment_seal_prepare/v1",
        "run_id": "ATT-001", "job_id": "JOB-001", "worker_id": "WORKER-001",
        "effective_grant_digest": "a" * 64, "process_ref": {"run_id": "ATT-001"},
        "paths": {label: _seal_identity(path, path.lstat()) for label, path in paths.items()},
        "uid_sweep": {"schema_version": "mastermind.executive_uid_sweep/v2", "passed": True,
            "residual_pids_before": [], "residual_pids_after": [], "found_residuals": False,
            "ambient_pids": [], "ambient_identities": [], "ambient_attribution": "absent",
            "worker_uid": binding.worker_uid, "broker_pid": 9999}}
    request = {"attempt_id": "ATT-001", "job_id": "JOB-001", "worker_id": "WORKER-001",
               "broker_operation": "assignment-seal", "broker_request": {
                   "run_id": "ATT-001", "process_ref": copy.deepcopy(snapshot["process_ref"])}}
    calls = []
    async def broker(operation, payload):
        calls.append((operation, copy.deepcopy(payload)))
        if operation == "assignment-seal-prepare":
            return {"snapshot": copy.deepcopy(snapshot), "snapshot_sha256": digest(snapshot)}
        assert operation == "assignment-seal-commit"
        return {"schema_version": "mastermind.worker_assignment_seal_commit/v1",
                "snapshot": copy.deepcopy(snapshot), "snapshot_sha256": digest(snapshot),
                "control_seal": payload["seal"], "worker_denial": {
                    label: {"open": "EACCES", "traverse": "EACCES", "list": "EACCES"}
                    for label in paths}}
    return binding, paths, snapshot, request, calls, broker


def mock_principal(monkeypatch, binding):
    monkeypatch.setattr(control.os, "getgid", lambda: binding.control_gid)
    monkeypatch.setattr(control.os, "getegid", lambda: binding.control_gid)


def test_control_seals_original_paths_but_never_finalizes_broker(tmp_path, monkeypatch):
    binding, paths, snapshot, request, calls, broker = fixture(tmp_path)
    mock_principal(monkeypatch, binding)
    observation = asyncio.run(control.seal_original_assignment(binding, request, broker))
    assert [op for op, _ in calls] == ["assignment-seal-prepare", "assignment-seal-commit"]
    assert observation["snapshot"] == snapshot
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in paths.values())
    # Lost-response replay is not permission to generate a second seal over
    # changed preimages. The incumbent broker still retains original admission.
    with pytest.raises(Exception, match="seal failed closed"):
        asyncio.run(control.seal_original_assignment(binding, request, broker))
    assert [op for op, _ in calls].count("assignment-seal-commit") == 1


@pytest.mark.parametrize("mutation", ["attempt", "job", "worker", "process", "path", "inode", "cleanup", "extra"])
def test_wrong_original_identity_never_seals(tmp_path, monkeypatch, mutation):
    binding, paths, snapshot, request, calls, broker = fixture(tmp_path)
    mock_principal(monkeypatch, binding)
    if mutation in {"attempt", "job", "worker"}:
        snapshot[{"attempt": "run_id", "job": "job_id", "worker": "worker_id"}[mutation]] = "other"
    elif mutation == "path":
        snapshot["paths"]["run"]["path"] = str(paths["run"].parent / "ATT-other")
    elif mutation == "process":
        snapshot["process_ref"]["run_id"] = "ATT-different"
    elif mutation == "inode":
        snapshot["paths"]["run"]["inode"] += 1
    elif mutation == "cleanup":
        snapshot["uid_sweep"]["passed"] = False
    else:
        request["broker_request"]["path"] = str(paths["run"])
    with pytest.raises(Exception):
        asyncio.run(control.seal_original_assignment(binding, request, broker))
    # The helper attempts all exact boundaries if a root itself changes; no
    # commit/finalize may follow a partial seal. Other failures precede chmod.
    assert not any(op.endswith("commit") for op, _ in calls)
    if mutation != "inode":
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o770 for path in paths.values())


@pytest.mark.parametrize("mutation", ["principal", "writable", "symlink", "store_swap"])
def test_control_custody_is_checked_before_effect(tmp_path, monkeypatch, mutation):
    binding, paths, snapshot, request, calls, broker = fixture(tmp_path)
    mock_principal(monkeypatch, binding)
    if mutation == "principal":
        monkeypatch.setattr(control.os, "geteuid", lambda: binding.worker_uid)
    elif mutation == "writable":
        paths["run"].parent.chmod(0o770)
    elif mutation == "symlink":
        old = paths["run"].parent
        old.rename(tmp_path / "renamed")
        old.symlink_to(tmp_path / "renamed", target_is_directory=True)
    else:
        original = broker
        async def broker(op, payload):
            result = await original(op, payload)
            paths["run"].parent.rename(tmp_path / "renamed")
            paths["run"].parent.mkdir(mode=0o750)
            return result
    with pytest.raises(control.RemoteAssignmentError):
        asyncio.run(control.seal_original_assignment(binding, request, broker))
    assert not any(op.endswith("commit") for op, _ in calls)


def test_failed_denial_or_transport_never_acknowledges(tmp_path, monkeypatch):
    binding, paths, _, request, calls, original = fixture(tmp_path)
    mock_principal(monkeypatch, binding)
    async def broker(op, payload):
        result = await original(op, payload)
        if op == "assignment-seal-commit":
            result["worker_denial"]["run"]["open"] = "ENOENT"
        return result
    with pytest.raises(control.RemoteAssignmentError, match="denial"):
        asyncio.run(control.seal_original_assignment(binding, request, broker))
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in paths.values())
    assert not any(op.endswith("finalize") for op, _ in calls)


def test_gateway_root_config_binding_is_closed_and_digest_bound(tmp_path):
    from tests.test_remote_worker_gateway_service import _fixture, _load, _service_module, _write
    import json
    service = _service_module()
    root, path, document = _fixture(tmp_path)
    before = service.remote_worker_gateway_config_digest(_load(service, root, path))
    document["assignment_control"] = control.AssignmentControlBinding(
        worker_id="codex-pro-01", control_uid=450, control_gid=450, worker_uid=451,
        worker_gid=451, workspace_root=Path("/inert/workspaces"), run_root=Path("/inert/runs")).to_wire()
    document["allowed_operations"] = ["assignment-seal", "assignment-seal-finalize"]
    _write(path, json.dumps(document), 0o440)
    config = _load(service, root, path)
    assert config.assignment_control.to_wire() == document["assignment_control"]
    assert service.remote_worker_gateway_config_digest(config) != before
    document["assignment_control"]["issuer_approved"] = True
    _write(path, json.dumps(document), 0o440)
    with pytest.raises(service.RemoteWorkerGatewayServiceError):
        _load(service, root, path)


def test_assignment_binding_refuses_shared_or_overlapping_roots(tmp_path):
    binding, *_ = fixture(tmp_path)
    for updates in ({"worker_uid": binding.control_uid}, {"worker_gid": binding.control_gid},
                    {"run_root": binding.workspace_root / "nested"}, {"control_uid": True}):
        with pytest.raises(control.RemoteAssignmentError):
            dataclasses.replace(binding, **updates)


def test_real_mtls_gateway_selects_control_producer_and_rejects_retarget(tmp_path, monkeypatch):
    from control_plane.remote_worker_transport import build_request
    from tests.test_remote_worker_gateway import (
        _gateway_fixture, _client_context, _exchange, _close_gateway, IDENTITY,
    )
    async def run():
        binding, paths, _, original_request, calls, broker = fixture(tmp_path)
        mock_principal(monkeypatch, binding)
        gateway = await _gateway_fixture(tmp_path)
        gateway.gateway.config = dataclasses.replace(gateway.config,
            allowed_operations=frozenset({"assignment-seal"}), assignment_control=binding)
        gateway.gateway.broker_call = broker
        context = _client_context(ca=gateway.config.ca_path,
            cert=gateway.control_cert, key=gateway.control_key)
        try:
            wrong = build_request(IDENTITY, "assignment-seal", {"run_id": "ATT-other"})
            refused = await _exchange(gateway.endpoint, context, wrong)
            assert refused["outcome"] == "refused" and calls == []
            response = await _exchange(gateway.endpoint, context,
                build_request(IDENTITY, "assignment-seal", original_request["broker_request"]))
            assert response["outcome"] == "ok"
            assert response["broker_response"]["snapshot"]["run_id"] == "ATT-001"
            assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in paths.values())
            assert [op for op, _ in calls] == ["assignment-seal-prepare", "assignment-seal-commit"]
        finally:
            await _close_gateway(gateway)
    asyncio.run(run())
