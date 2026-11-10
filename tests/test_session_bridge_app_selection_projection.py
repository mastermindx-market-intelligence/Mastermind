"""Canonical Mission association is projected from the existing Runtime owner."""
from tests.test_session_bridge_runtime_owner import projector
from integrations.session_bridge.runtime_owner import RuntimeCodexTarget


def test_fabric_projection_carries_exact_canonical_mission_association():
    owner, _ = projector()
    target = owner.list_targets()[0]
    public = target.public_projection()
    assert public.get("work_ref") == target.source.work_ref
    assert public.get("root_job_id") == target.epoch.root_job_id
    assert set(public) == {"target_ref", "kind", "generation", "addressable",
                           "continuation_operation_key", "work_ref", "root_job_id"}


def test_codex_projection_remains_separate_without_mission_fields():
    owner, _ = projector()
    target = RuntimeCodexTarget(owner.list_targets()[0])
    public = target.public_projection()
    assert "work_ref" not in public and "root_job_id" not in public
