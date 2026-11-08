"""Isolation contract for the optional crash-module producer fixture seed."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    _complete_repository,
    _git,
    _repair_host_fixture,
    _repository_fixture_fingerprint,
    artifacts,
    contract,
    pytest,
)


def test_producer_seed_copies_keep_independent_git_and_transport_state(tmp_path, monkeypatch):
    seed_parent = tmp_path / "seed"
    seed_parent.mkdir()
    missing = object()
    original_commit = getattr(artifacts, "PRODUCER_COMMIT", missing)
    with pytest.MonkeyPatch.context() as seed_patch:
        seed = _complete_repository(seed_parent, seed_patch)
    assert getattr(artifacts, "PRODUCER_COMMIT", missing) == original_commit
    seed_root, commit, nonmaterial_oid = seed
    before = _repository_fixture_fingerprint(seed_root)
    real_builder = artifacts.build_source_transport_v3
    sources = []

    def build_real_transport(source, *args, **kwargs):
        sources.append(source)
        return real_builder(source, *args, **kwargs)

    monkeypatch.setattr(artifacts, "build_source_transport_v3", build_real_transport)
    copies, transports, manifests = [], [], []
    for name in ("first", "second"):
        case = tmp_path / name
        case.mkdir()
        with pytest.MonkeyPatch.context() as case_patch:
            _, transport, copied_commit, manifest = _repair_host_fixture(
                case, case_patch, producer_seed=seed
            )
            assert artifacts.PRODUCER_COMMIT == contract.PRODUCER_COMMIT == commit
        source = case / "complete-source"
        assert copied_commit == _git(source, "rev-parse", "HEAD") == commit
        assert _git(source, "rev-list", "--count", "HEAD") == "2"
        assert _git(source, "rev-parse", f"{commit}:docs/nonmaterial-history.txt") == nonmaterial_oid
        assert _repository_fixture_fingerprint(source) == before
        copies.append(source)
        transports.append(transport)
        manifests.append(manifest)
    assert sources == copies
    assert transports[0] != transports[1] and all(path.is_file() for path in transports)
    assert manifests[0] is not manifests[1] and manifests[0] == manifests[1]

    inode_sets = [
        {(path.stat().st_dev, path.stat().st_ino) for path in root.rglob("*") if path.is_file()}
        for root in (seed_root, *copies)
    ]
    assert all(
        not inode_sets[i].intersection(inode_sets[j])
        for i in range(3)
        for j in range(i + 1, 3)
    )
    material = copies[0] / contract.PRODUCER_MATERIAL_PATHS[0]
    material.write_bytes(b"case-local mutation\n")
    (copies[0] / ".git" / "HEAD").write_text("ref: refs/heads/case-local-mutation\n")
    manifests[0]["case_local_mutation"] = True
    assert "case_local_mutation" not in manifests[1]
    assert _repository_fixture_fingerprint(seed_root) == before
    assert _repository_fixture_fingerprint(copies[1]) == before
    assert _git(seed_root, "rev-parse", "HEAD") == commit
    assert _git(copies[1], "rev-parse", "HEAD") == commit
