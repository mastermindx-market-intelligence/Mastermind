"""Capacity host crash replay cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _complete_repository,
    _repository_fixture_fingerprint,
    _repair_host_fixture,
    artifacts,
    hashlib,
    os,
    pytest,
)


@pytest.fixture(scope="module")
def _crash_producer_seed(tmp_path_factory):
    # Only immutable producer construction is shared; each case builds its real transport.
    with pytest.MonkeyPatch.context() as seed_patch:
        seed = _complete_repository(tmp_path_factory.mktemp("crash-producer-seed"), seed_patch)
    before = _repository_fixture_fingerprint(seed[0])
    yield seed
    assert _repository_fixture_fingerprint(seed[0]) == before


@pytest.mark.parametrize(
    "crash_at",
    (
        "after_transport_fsync",
        "after_candidate_verify",
        "after_intent_fsync",
        "after_old_source_move",
        "after_candidate_install",
        "after_old_generation_move",
        "after_repair_receipt_fsync",
        "after_generation_file_1_fsync",
        "after_generation_file_2_fsync",
        "after_generation_file_3_fsync",
        "after_generation_file_4_fsync",
        "after_generation_file_5_fsync",
        "after_generation_file_6_fsync",
        "after_hidden_generation_directory_fsync",
        "before_final_rename",
        "after_final_rename_before_parent_fsync",
        "after_parent_fsync_before_stdout",
    ),
)
def test_every_repair_crash_position_replays_to_one_verified_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_at: str, _crash_producer_seed
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch, producer_seed=_crash_producer_seed
    )
    arguments = {
        "mode": "repair",
        "system_root": system_root,
        "lock_file": system_root / "locks" / "cf2-h0.lock",
        "expected_repair_commit": "d" * 40,
        "expected_source_commit": commit,
        "operator_uid": os.getuid(),
        "transport": transport,
        "transport_sha256": hashlib.sha256(transport.read_bytes()).hexdigest(),
        "test_adapter": True,
    }
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at=crash_at)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    visible = [
        path
        for path in (system_root / "capacity-generations").iterdir()
        if not path.name.startswith(".")
    ]
    assert len(visible) == 1
    archive = next((system_root / "capacity-archive").iterdir())
    assert (archive / "archived-source" / "promisor-source").is_file()
    assert (archive / "archived-generation").is_dir()


def test_definite_precommit_failure_restores_only_digest_bound_old_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _crash_producer_seed
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch, producer_seed=_crash_producer_seed
    )
    original_publish = artifacts.publish_source_repair_receipt

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="INJECTED_RECEIPT_REFUSAL"
    ):
        artifacts.run_source_repair_host(
            mode="repair",
            system_root=system_root,
            lock_file=system_root / "locks" / "cf2-h0.lock",
            expected_repair_commit="d" * 40,
            expected_source_commit=commit,
            operator_uid=os.getuid(),
            transport=transport,
            transport_sha256=hashlib.sha256(transport.read_bytes()).hexdigest(),
            test_adapter=True,
        )
    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", original_publish)
    restored_source = system_root / "capacity-sources" / "macro" / commit
    assert (restored_source / "promisor-source").is_file()
    assert (system_root / "capacity-generations" / artifacts.PRIOR_GENERATION_DIGEST).is_dir()
    archive = next((system_root / "capacity-archive").iterdir())
    failure_namespace = archive / f"failure-{archive.name.removeprefix('source-closure-repair-')}"
    assert (failure_namespace / "installed-source").is_dir()
    assert not (archive / "archived-source").exists()
    assert not (archive / "archived-generation").exists()
    position = artifacts.reconcile_source_repair(
        archive,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    assert position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
