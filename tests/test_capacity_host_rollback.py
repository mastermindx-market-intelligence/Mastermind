"""Capacity host rollback cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _repair_arguments,
    _repair_host_fixture,
    _scoped_tree_snapshot,
    artifacts,
    os,
    pytest,
)


@pytest.mark.parametrize(
    "crash_at",
    (
        "after_failure_namespace_parent_fsync",
        "after_rollback_installed_rename",
        "after_rollback_installed_source_parent_fsync",
        "after_rollback_installed_destination_parent_fsync",
        "after_rollback_generation_rename",
        "after_rollback_generation_source_parent_fsync",
        "after_rollback_generation_destination_parent_fsync",
        "after_rollback_source_rename",
        "after_rollback_source_source_parent_fsync",
        "after_rollback_source_destination_parent_fsync",
    ),
)
def test_every_rollback_prefix_is_unique_and_replays_to_digest_bound_prior_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_at: str
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    original_publish = artifacts.publish_source_repair_receipt

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at=crash_at)
    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", original_publish)

    before_replay = _scoped_tree_snapshot(system_root)
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)
    after_replay = _scoped_tree_snapshot(system_root)
    if crash_at.endswith("destination_parent_fsync") and crash_at.startswith(
        "after_rollback_source_"
    ):
        assert after_replay == before_replay
    restored_source = system_root / "capacity-sources" / "macro" / commit
    assert (restored_source / "promisor-source").is_file()
    assert (
        system_root / "capacity-generations" / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()
    archive = next((system_root / "capacity-archive").iterdir())
    failure_namespace = archive / f"failure-{archive.name.removeprefix('source-closure-repair-')}"
    assert (failure_namespace / "installed-source").is_dir()
    position = artifacts.reconcile_source_repair(
        archive,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    assert position.phase is artifacts.SourceRepairPhase.ROLLED_BACK


@pytest.mark.parametrize(
    "crash_at",
    (
        "after_rollback_staged_rename",
        "fail_rollback_staged_source_parent_fsync",
        "after_rollback_staged_source_parent_fsync",
        "fail_rollback_staged_destination_parent_fsync",
        "after_rollback_staged_destination_parent_fsync",
    ),
)
def test_rollback_staged_every_durability_boundary_replays_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_at: str
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)

    def fail_before_forward_source(*args: object, **kwargs: object) -> object:
        raise artifacts.CapacityHostArtifactError("INJECTED_PRE_SOURCE_FAILURE")

    with monkeypatch.context() as failure:
        failure.setattr(
            artifacts,
            "_advance_source_repair_source_phase",
            fail_before_forward_source,
        )
        with pytest.raises(artifacts.SourceRepairIncomplete):
            artifacts.run_source_repair_host(**arguments, crash_at=crash_at)

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)

    archive = next((system_root / "capacity-archive").iterdir())
    failure_namespace = archive / (
        f"failure-{archive.name.removeprefix('source-closure-repair-')}"
    )
    assert (failure_namespace / "staged-source").is_dir()
    assert not (failure_namespace / "installed-source").exists()
    assert (system_root / "capacity-sources" / "macro" / commit).is_dir()
    visible_generations = [
        child
        for child in (system_root / "capacity-generations").iterdir()
        if not child.name.startswith(".")
    ]
    assert [child.name for child in visible_generations] == [
        artifacts.PRIOR_GENERATION_DIGEST
    ]
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        position.failure_layout
        is artifacts.SourceRepairFailureLayout.STAGED_SOURCE
    )
