"""Stateless Runtime-owned fabric target projection for installed Session Bridge."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import JobStatus
from integrations.session_bridge.schemas import BridgeError
from tests.test_workspace_agent_runtime_binding import (
    OPERATION,
    ATTEMPT,
    JOB,
    WORKER,
    physical,
    source,
    target,
)


class Reads:
    def __init__(self):
        self.targets = []
        self.sources = []
        self.physicals = []

    def target(self, operation_key):
        self.targets.append(operation_key)
        return target()

    def source(self, root_job_id):
        self.sources.append(root_job_id)
        return source()

    def physical(self, operation_key, job_id, attempt_id):
        self.physicals.append((operation_key, job_id, attempt_id))
        return physical()


def projector(reads=None):
    from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector
    reads = reads or Reads()
    job = SimpleNamespace(
        job_id=JOB,
        status=JobStatus.RUNNING,
        current_attempt_id=ATTEMPT,
    )
    identity = SimpleNamespace(operation_key=OPERATION)
    return RuntimeFabricTargetProjector(
        object(),
        job_reader=lambda: [job],
        identity_resolver=lambda value: identity,
        target_reader=reads.target,
        dialogue_source_reader=reads.source,
        physical_source_reader=reads.physical,
    ), reads


def test_fabric_target_is_exact_hash_of_current_runtime_and_physical_carrier():
    p, reads = projector()
    values = p.list_targets()
    assert len(values) == 1
    item = values[0]
    public = item.public_projection()
    assert public["kind"] == "fabric_attempt"
    assert public["target_ref"].startswith("fabric_attempt:")
    assert public["addressable"] is True
    assert public["generation"]
    assert "provider-session" not in repr(public)
    assert reads.targets == [OPERATION, OPERATION]
    assert reads.sources == ["JOB-100"]
    assert reads.physicals == [(OPERATION, JOB, ATTEMPT)]
    assert p.resolve(item.target_ref) == item


def test_fabric_target_ref_changes_when_current_harness_generation_changes():
    from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector

    class Moving(Reads):
        def __init__(self, generation):
            super().__init__()
            self.generation = generation
        def target(self, operation_key):
            self.targets.append(operation_key)
            return target(
                harness_generation_number=self.generation,
                harness_provider_session_id=f"provider-session-{self.generation}",
            )

    def make(reads):
        job = SimpleNamespace(job_id=JOB, status=JobStatus.RUNNING, current_attempt_id=ATTEMPT)
        return RuntimeFabricTargetProjector(
            object(),
            job_reader=lambda: [job],
            identity_resolver=lambda value: SimpleNamespace(operation_key=OPERATION),
            target_reader=reads.target,
            dialogue_source_reader=reads.source,
            physical_source_reader=reads.physical,
        )

    assert make(Moving(7)).list_targets()[0].target_ref != make(Moving(8)).list_targets()[0].target_ref


def test_fabric_target_refuses_runtime_drift_during_projection():
    from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector

    reads = Reads()
    calls = 0
    def moving(operation_key):
        nonlocal calls
        calls += 1
        return target() if calls == 1 else target(fence_generation=5)

    job = SimpleNamespace(job_id=JOB, status=JobStatus.RUNNING, current_attempt_id=ATTEMPT)
    p = RuntimeFabricTargetProjector(
        object(),
        job_reader=lambda: [job],
        identity_resolver=lambda value: SimpleNamespace(operation_key=OPERATION),
        target_reader=moving,
        dialogue_source_reader=reads.source,
        physical_source_reader=reads.physical,
    )
    assert p.list_targets() == []


def test_fabric_target_resolve_never_falls_back_to_another_current_attempt():
    p, _ = projector()
    with pytest.raises(BridgeError) as error:
        p.resolve("fabric_attempt:" + "0" * 64)
    assert error.value.code == "native_target_stale"
