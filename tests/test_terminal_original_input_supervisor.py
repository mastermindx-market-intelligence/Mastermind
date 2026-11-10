"""Actual Supervisor/Runtime input custody; all filesystem/worker data is inert."""
import asyncio
import json
import os

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.terminal_original_input_artifacts import TerminalInputError
from tests.test_executive_supervisor import (
    FakeAdapter,
    FakeInspector,
    _runtime_and_job,
    _supervisor,
)

COMMAND = "terminal-original:source-command"
ISSUER = "1a" * 32
FINGERPRINT = "2b" * 32
PRIVATE = b'{"synthetic_private_source":"private-owner-body-canary"}'


def prepare(owner, **changes):
    arguments = dict(command_id=COMMAND, issuer_scope_sha256=ISSUER,
                     fingerprint_sha256=FINGERPRINT, payload=PRIVATE)
    arguments.update(changes)
    return owner.prepare_terminal_original_input(**arguments)


def empty_owner(tmp_path, *, runs_root=None):
    # Nested fixture roots must meet the real custody owner's private-parent contract.
    # Existing parents are not chmod-repaired; unsafe ones still fail closed.
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    runtime = Runtime.at(tmp_path / "runtime")
    adapter = FakeAdapter(FakeInspector())
    owner = ExecutiveSupervisor(runtime, adapter, runs_root=runs_root or tmp_path / "runs")
    return runtime, owner, adapter


def test_new_nested_fixture_owner_root_is_private_before_preparation(tmp_path):
    root = tmp_path / "nested-custody"
    runtime, owner, adapter = empty_owner(root)
    assert root.stat().st_mode & 0o777 == 0o700
    assert prepare(owner) is not None
    assert runtime.jobs.list_jobs() == [] and runtime.store.list_events() == []
    assert adapter.spec is None


def test_prepare_reconciles_same_private_artifact_without_job_or_worker(tmp_path):
    runtime, owner, adapter = empty_owner(tmp_path)
    first = prepare(owner)
    paths = list((tmp_path / "runs" / "terminal-original-input").glob("*/input.bin"))
    assert len(paths) == 1
    inode = paths[0].stat().st_ino
    assert prepare(owner).to_dict() == first.to_dict()
    assert paths[0].stat().st_ino == inode
    assert runtime.jobs.list_jobs() == []
    assert runtime.store.list_events() == []
    assert adapter.spec is None
    assert "private-owner-body-canary" not in json.dumps(first.to_dict())


def test_existing_original_job_is_reconciled_before_any_input_preparation(tmp_path):
    runtime, owner, adapter = empty_owner(tmp_path)
    original = runtime.jobs.create_job("Original operation", requested_authorities=["READ"],
                                       command_id=COMMAND)
    events = [event.to_dict() for event in runtime.store.list_events()]
    assert prepare(owner) is None
    assert not (tmp_path / "runs").exists()
    assert runtime.jobs.get_job(original.job_id).to_dict() == original.to_dict()
    assert [event.to_dict() for event in runtime.store.list_events()] == events
    assert adapter.spec is None


@pytest.mark.parametrize("changes", [
    {"command_id": "../other"}, {"issuer_scope_sha256": "email@example.test"},
    {"fingerprint_sha256": "not-a-digest"}, {"payload": b""},
    {"payload": b"x" * (256 * 1024 + 1)},
])
def test_invalid_private_preparation_does_not_allocate_or_insert(tmp_path, changes):
    runtime, owner, adapter = empty_owner(tmp_path)
    with pytest.raises(TerminalInputError) as error:
        prepare(owner, **changes)
    assert str(error.value) == "TERMINAL_INPUT_INVALID"
    assert not (tmp_path / "runs").exists()
    assert runtime.jobs.list_jobs() == []
    assert runtime.store.list_events() == []
    assert adapter.spec is None


def test_unsafe_parent_is_not_repaired_and_no_job_is_inserted(tmp_path):
    parent = tmp_path / "unsafe"
    parent.mkdir(mode=0o777)
    os.chmod(parent, 0o777)
    runtime, owner, adapter = empty_owner(tmp_path, runs_root=parent / "runs")
    with pytest.raises(TerminalInputError) as error:
        prepare(owner)
    assert str(error.value) == "TERMINAL_INPUT_UNAVAILABLE"
    assert not (parent / "runs").exists()
    assert parent.stat().st_mode & 0o777 == 0o777
    assert runtime.jobs.list_jobs() == []
    assert adapter.spec is None


def test_private_input_is_denied_and_absent_from_actual_worker_publication(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    adapter = FakeAdapter(FakeInspector())
    owner = _supervisor(runtime, tmp_path, adapter)
    prepare(owner)
    result = asyncio.run(owner.run_once(job_id))
    assert (tmp_path / "runs" / "terminal-original-input").resolve() in adapter.spec.forbidden_paths
    public = json.dumps({
        "job": result.job.to_dict(),
        "events": [event.to_dict() for event in runtime.store.list_events()],
        "prompt": adapter.spec.prompt,
        "schema": adapter.spec.result_schema_path.read_text(),
    })
    assert "private-owner-body-canary" not in public
    assert result.job.job_id == job_id
