"""Capacity host publication cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _repair_arguments,
    _repair_host_fixture,
    _scoped_tree_snapshot,
    _verify_arguments,
    artifacts,
    errno,
    os,
    pytest,
)


@pytest.mark.parametrize(
    "crash_at",
    (
        "after_intent_fsync",
        "after_old_source_move",
        "after_candidate_install",
        "after_old_generation_move",
        "after_repair_receipt_fsync",
        "after_generation_file_1_fsync",
    ),
)
def test_verify_only_refuses_every_incomplete_position_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_at: str
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(
            **_repair_arguments(system_root, transport, commit),
            crash_at=crash_at,
        )
    before = _scoped_tree_snapshot(system_root)

    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.run_source_repair_host(**_verify_arguments(system_root, commit))
    assert _scoped_tree_snapshot(system_root) == before


@pytest.mark.parametrize(
    "crash_at",
    (
        "after_archive_create_intent",
        "fail_archive_parent_fsync_intent",
        *tuple(
            f"{boundary}_{kind}"
            for kind in ("intent", "receipt")
            for boundary in (
                "after_candidate_create",
                "after_candidate_partial_write",
                "after_candidate_file_fsync",
                "after_candidate_rename",
                "before_parent_fsync",
                "after_parent_fsync",
            )
        ),
    ),
)
def test_publication_prefix_crashes_replay_to_one_exact_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_at: str
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at=crash_at)

    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    archive = next((system_root / "capacity-archive").iterdir())
    assert not any(path.name.startswith(".") for path in archive.iterdir())
    assert (archive / "source-repair-intent.json").is_file()
    assert (archive / "source-repair-receipt.json").is_file()


@pytest.mark.parametrize(
    "crash_at",
    tuple(
        f"fail_{move}_{parent}_parent_fsync"
        for move in ("old_source", "candidate_install", "old_generation")
        for parent in ("source", "destination")
    ),
)
def test_visible_move_parent_fsync_failure_reconciles_forward_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_at: str
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at=crash_at)

    archive = next((system_root / "capacity-archive").iterdir())
    assert not any(path.name.startswith("failure-") for path in archive.iterdir())
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )


def test_visible_commit_normalizes_structural_refusal_to_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )

    def refuse_visible_generation(*args: object, **kwargs: object) -> None:
        raise artifacts.CapacityHostArtifactError("INJECTED_VISIBLE_REFUSAL")

    monkeypatch.setattr(
        artifacts, "_verify_repaired_generation", refuse_visible_generation
    )
    with pytest.raises(
        artifacts.SourceRepairIncomplete,
        match="POST_COMMIT_RECONCILIATION_REQUIRED",
    ) as raised:
        artifacts.run_source_repair_host(**arguments)
    assert isinstance(raised.value.__cause__, artifacts.CapacityHostArtifactError)


def test_visible_commit_normalizes_cleanup_failure_to_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    original_close = artifacts.SourceRepairParents.close

    def fail_after_close(parents: artifacts.SourceRepairParents) -> None:
        original_close(parents)
        raise OSError(errno.EIO, "injected retained-parent close failure")

    monkeypatch.setattr(artifacts.SourceRepairParents, "close", fail_after_close)
    with pytest.raises(
        artifacts.SourceRepairIncomplete,
        match="POST_COMMIT_RECONCILIATION_REQUIRED",
    ) as raised:
        artifacts.run_source_repair_host(**arguments)
    assert isinstance(raised.value.__cause__, OSError)


def test_every_forward_rename_uses_the_retained_parent_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    retained: set[int] = set()
    original_open_parents = artifacts._open_source_repair_parents
    original_attach_archive = artifacts._attach_source_repair_archive_parent
    original_rename = artifacts._rename_exclusive

    def record_fixed_parents(*args: object, **kwargs: object) -> object:
        parents = original_open_parents(*args, **kwargs)
        retained.update(
            {parents.source, parents.generation, parents.staging, parents.archive}
        )
        return parents

    def record_intent_archive(*args: object, **kwargs: object) -> None:
        original_attach_archive(*args, **kwargs)
        parents = args[0]
        assert isinstance(parents, artifacts.SourceRepairParents)
        assert parents.intent_archive is not None
        retained.add(parents.intent_archive)

    def require_retained(
        source_parent: int,
        source_name: str,
        destination_parent: int,
        destination_name: str,
    ) -> None:
        assert source_parent in retained
        assert destination_parent in retained
        original_rename(
            source_parent, source_name, destination_parent, destination_name
        )

    monkeypatch.setattr(
        artifacts, "_open_source_repair_parents", record_fixed_parents
    )
    monkeypatch.setattr(
        artifacts, "_attach_source_repair_archive_parent", record_intent_archive
    )
    monkeypatch.setattr(artifacts, "_rename_exclusive", require_retained)
    assert artifacts.run_source_repair_host(
        **_repair_arguments(system_root, transport, commit)
    ) == "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"


@pytest.mark.parametrize("failed_descriptor", (50, 52))
def test_source_repair_parent_cleanup_attempts_every_owned_descriptor_once(
    monkeypatch: pytest.MonkeyPatch, failed_descriptor: int
) -> None:
    parents = artifacts.SourceRepairParents(
        source_path=Path("source"),
        source=50,
        generation_path=Path("generation"),
        generation=51,
        staging_path=Path("staging"),
        staging=52,
        archive_path=Path("archive"),
        archive=53,
        device=1,
        intent_archive_path=Path("intent"),
        intent_archive=54,
    )
    attempted: list[int] = []

    def injected_close(descriptor: int) -> None:
        attempted.append(descriptor)
        if descriptor in {failed_descriptor, 54}:
            raise OSError(errno.EIO, f"close-{descriptor}")

    monkeypatch.setattr(os, "close", injected_close)
    with pytest.raises(OSError, match="close-54"):
        parents.close()
    assert attempted == [54, 53, 52, 51, 50]


def test_source_repair_archive_attachment_closes_new_descriptor_when_fstat_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    archive = system_root / "capacity-archive" / "source-closure-repair-probe"
    archive.mkdir(mode=0o700)
    original_open = os.open
    original_fstat = os.fstat
    original_close = os.close
    opened: list[int] = []
    closed: list[int] = []

    def observed_open(*args: object, **kwargs: object) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def fail_new_descriptor_fstat(descriptor: int) -> os.stat_result:
        if opened and descriptor == opened[-1]:
            raise OSError(errno.EIO, "injected attachment fstat failure")
        return original_fstat(descriptor)

    def observed_close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(os, "fstat", fail_new_descriptor_fstat)
    monkeypatch.setattr(os, "close", observed_close)
    try:
        with pytest.raises(OSError, match="attachment fstat failure"):
            artifacts._attach_source_repair_archive_parent(
                parents,
                archive,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )
        assert len(opened) == 1
        assert closed.count(opened[0]) == 1
        assert parents.intent_archive is None
    finally:
        monkeypatch.setattr(os, "fstat", original_fstat)
        parents.close()


@pytest.mark.parametrize("failed_close_index", (0, 1))
def test_partial_parent_open_cleanup_preserves_initial_error_and_attempts_all_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_close_index: int,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    original_open = os.open
    original_fstat = os.fstat
    original_close = os.close
    opened: list[int] = []
    attempted: list[int] = []

    def observed_open(*args: object, **kwargs: object) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def fail_second_parent_validation(descriptor: int) -> os.stat_result:
        if len(opened) >= 2 and descriptor == opened[1]:
            raise OSError(errno.EIO, "initial parent validation failure")
        return original_fstat(descriptor)

    def fail_one_close(descriptor: int) -> None:
        attempted.append(descriptor)
        original_close(descriptor)
        if descriptor == opened[failed_close_index]:
            raise OSError(errno.EBADF, "injected cleanup close failure")

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(os, "fstat", fail_second_parent_validation)
    monkeypatch.setattr(os, "close", fail_one_close)
    with pytest.raises(OSError, match="initial parent validation failure"):
        artifacts._open_source_repair_parents(
            system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )
    assert attempted == list(reversed(opened[:2]))
