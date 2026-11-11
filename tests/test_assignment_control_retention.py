"""Real local receipt/Runtime tests, with explicitly synthetic remote observations."""
import asyncio
import copy
import errno
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import broker_assignment_seal as seal
from control_plane.executive_supervisor import _jsonable, _write_private_json
from control_plane.executive_workspace import _seal_identity
from tests.test_executive_supervisor import (
    _runtime_and_job, _supervisor, RestartCapableFakeAdapter, FakeInspector,
)


def test_admitted_shared_run_mode_and_root_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(seal, "require_worker_principal", lambda policy: None)
    roots = {}
    for label in ("workspace", "run"):
        parent = tmp_path / (label + "s")
        parent.mkdir(mode=0o750)
        path = parent / "assigned"
        path.mkdir(mode=0o770 if label == "run" else 0o750)
        path.chmod(0o770 if label == "run" else 0o750)
        roots[label] = path
    policy = SimpleNamespace(control_uid=os.geteuid(), worker_gid=os.getegid(),
                             workspace_root=roots["workspace"].parent, run_root=roots["run"].parent)
    manifest = {"entries": [{"disposition": "CURRENT_" + label.upper(),
                              "identity": _seal_identity(path, path.lstat())}
                             for label, path in roots.items()]}
    observed = seal.observe_roots(roots, policy, manifest)
    assert observed["run"]["mode"] == 0o770
    changed = copy.deepcopy(manifest)
    changed["entries"][1]["identity"]["inode"] += 1
    with pytest.raises(seal.AssignmentObservationError, match="manifest"):
        seal.observe_roots(roots, policy, changed)
    roots["run"].parent.chmod(0o770)
    with pytest.raises(seal.AssignmentObservationError, match="replacement"):
        seal.observe_roots(roots, policy, manifest)


@pytest.mark.parametrize("number", [errno.ENOENT, errno.EPERM, errno.EIO])
def test_absence_and_other_errors_are_not_worker_denial(monkeypatch, number):
    def fail(*args, **kwargs):
        raise OSError(number, "inert error")
    monkeypatch.setattr(os, "open", fail)
    with pytest.raises(seal.AssignmentObservationError, match="ambiguous"):
        seal._require_denied(Path("/inert/assignment"))


def test_control_private_readback_rejects_changed_or_shared_receipt(tmp_path):
    directory = tmp_path / "control"
    path = directory / "receipt.json"
    record = {"observation": "inert"}
    _write_private_json(path, record)
    seal.verify_control_readback(path, record)
    path.chmod(0o640)
    with pytest.raises(seal.AssignmentObservationError, match="private"):
        seal.verify_control_readback(path, record)
    path.chmod(0o600)
    path.write_text('{"observation":"changed"}')
    with pytest.raises(seal.AssignmentObservationError, match="differs"):
        seal.verify_control_readback(path, record)


async def retained_fixture(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    (tmp_path / "control-receipts").mkdir(mode=0o700)
    supervisor = _supervisor(runtime, tmp_path, RestartCapableFakeAdapter(FakeInspector()),
                             receipts_root=tmp_path / "control-receipts")
    active = await supervisor.start_job(job_id)
    paths = {entry["disposition"].removeprefix("CURRENT_").lower(): dict(entry["identity"])
             for entry in active.launch_spec.isolation_manifest["entries"]
             if entry["disposition"] in {"CURRENT_WORKSPACE", "CURRENT_RUN"}}
    snapshot = {"schema_version": "mastermind.worker_assignment_seal_prepare/v1",
                "run_id": active.lease.attempt.attempt_id, "job_id": job_id,
                "worker_id": active.lease.attempt.worker_id, "effective_grant_digest": None,
                "process_ref": _jsonable(active.process_ref), "paths": paths,
                "uid_sweep": supervisor.adapter.uid_sweep_receipt(active.process_ref)}
    observation = {"schema_version": "mastermind.worker_assignment_seal_commit/v1",
                   "snapshot": snapshot, "snapshot_sha256": seal.digest(snapshot),
                   "control_seal": {"schema_version": "mastermind.executive_assignment_seal/v1",
                        "passed": True, "control_uid": os.geteuid(), "sealed_at": "2026-10-12T00:00:00Z",
                        "paths": {label: {"before": value, "after": {**value, "mode": 0o700},
                                           "worker_traversal_revoked": True} for label, value in paths.items()}},
                   "worker_denial": {label: {"open": "EACCES", "traverse": "EACCES", "list": "EACCES"}
                                      for label in paths}}
    return runtime, supervisor, active, observation


def test_original_runtime_pin_and_private_retention_precede_ack(tmp_path):
    async def run():
        runtime, supervisor, active, observation = await retained_fixture(tmp_path)
        path, ack = supervisor._retain_remote_assignment_observation(active, observation)
        assert json.loads(path.read_bytes()) == seal.control_retention_record(observation)
        assert ack == {"run_id": active.lease.attempt.attempt_id,
                       "observation_sha256": seal.digest(observation),
                       "retention_sha256": seal.digest(seal.control_retention_record(observation))}
        assert supervisor._retain_remote_assignment_observation(active, observation) == (path, ack)
        runtime.attempts.adopt_attempt(active.lease.attempt.attempt_id,
            expected_fence_generation=active.lease.attempt.fence_generation, lease_owner="successor")
        with pytest.raises(Exception, match="stale fence"):
            supervisor._retain_remote_assignment_observation(active, observation)
    asyncio.run(run())


@pytest.mark.parametrize("mutation", ["run", "process", "root", "denial", "write", "readback"])
def test_control_never_acknowledges_wrong_assignment_or_failed_retention(tmp_path, monkeypatch, mutation):
    import control_plane.executive_supervisor as source
    async def run():
        _, supervisor, active, observation = await retained_fixture(tmp_path)
        if mutation == "run":
            observation["snapshot"]["run_id"] = "ATT-other"
        elif mutation == "process":
            observation["snapshot"]["process_ref"]["process_start_identity"] = "different"
        elif mutation == "root":
            observation["snapshot"]["paths"]["run"]["inode"] += 1
        elif mutation == "denial":
            observation["worker_denial"]["run"]["open"] = "ENOENT"
        else:
            def fail(*args, **kwargs):
                raise OSError("inert retention failure")
            monkeypatch.setattr(source if mutation == "write" else seal,
                "_write_or_verify_private_json" if mutation == "write" else "verify_control_readback", fail)
        observation["snapshot_sha256"] = seal.digest(observation["snapshot"])
        with pytest.raises(Exception):
            supervisor._retain_remote_assignment_observation(active, observation)
    asyncio.run(run())


@pytest.mark.parametrize("fail_at", [1, 2])
def test_existing_visible_receipt_is_not_durable_until_file_and_parent_sync(
    tmp_path, monkeypatch, fail_at,
):
    # A previous writer may have failed after writing exact bytes but before
    # fsync. Existing-file equality cannot turn that uncertain write into ACK.
    directory = tmp_path / "control"
    directory.mkdir(mode=0o700)
    path = directory / "receipt.json"
    record = {"observation": "inert partial prior write"}
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)
    calls = []
    def sync(fd):
        calls.append(fd)
        if len(calls) == fail_at:
            raise OSError(errno.EIO, "inert durability failure")
    monkeypatch.setattr(seal.os, "fsync", sync)
    with pytest.raises(OSError, match="durability failure"):
        seal.verify_control_readback(path, record)
    assert len(calls) == fail_at


def test_retained_file_after_readback_failure_cannot_bypass_changed_runtime_fence(
    tmp_path, monkeypatch,
):
    async def run():
        runtime, supervisor, active, observation = await retained_fixture(tmp_path)
        original = seal.verify_control_readback
        def fail(*args):
            raise OSError(errno.EIO, "inert readback failure after write")
        monkeypatch.setattr(seal, "verify_control_readback", fail)
        with pytest.raises(OSError, match="after write"):
            supervisor._retain_remote_assignment_observation(active, observation)
        path = supervisor.receipts_root / active.lease.attempt.attempt_id / "remote-assignment-observation.json"
        retained = path.read_bytes()
        assert json.loads(retained) == seal.control_retention_record(observation)
        runtime.attempts.adopt_attempt(active.lease.attempt.attempt_id,
            expected_fence_generation=active.lease.attempt.fence_generation, lease_owner="successor")
        monkeypatch.setattr(seal, "verify_control_readback", original)
        with pytest.raises(Exception, match="stale fence"):
            supervisor._retain_remote_assignment_observation(active, observation)
        assert path.read_bytes() == retained
    asyncio.run(run())
