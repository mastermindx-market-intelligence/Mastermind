"""The existing complete source owner admits one closed native material profile."""
import copy
import json
import stat
from pathlib import Path

import pytest

from ops.executive_os import capacity_host_artifacts as artifacts
from ops.executive_os import capacity_source_contract as contract
from tests.test_capacity_host_artifacts import _complete_repository, _git


@pytest.fixture
def native_source(tmp_path, monkeypatch):
    source, _, nonmaterial = _complete_repository(tmp_path, monkeypatch)
    paths = artifacts.NATIVE_PRODUCER_MATERIAL_PATHS
    for relative in set(paths) - set(contract.PRODUCER_MATERIAL_PATHS):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'"""Fixture material; never executed."""\n')
    _git(source, "add", *paths)
    _git(source, "commit", "-qm", "fixture native source")
    commit = _git(source, "rev-parse", "HEAD")
    monkeypatch.setattr(artifacts, "NATIVE_PRODUCER_COMMIT", commit)
    return source, commit, nonmaterial


@pytest.fixture
def native_checkout(native_source, tmp_path):
    source, commit, nonmaterial = native_source
    archive = tmp_path / "native.zip"
    manifest = artifacts.build_native_source_transport(source, archive, commit=commit)
    checkout = tmp_path / "native-checkout"
    artifacts.materialize_native_source_transport(archive, checkout, expected_commit=commit)
    return checkout, manifest, commit, archive


def test_native_profile_is_closed_and_keeps_legacy_identity():
    assert artifacts.NATIVE_PRODUCER_COMMIT == "084ac334a2bf4beb76bd22b5bf7d37a8eb93e051"
    assert artifacts.NATIVE_TRANSPORT_SCHEMA == "mastermind.capacity_source_transport/native_v1"
    assert set(artifacts.NATIVE_PRODUCER_MATERIAL_PATHS) == set(contract.PRODUCER_MATERIAL_PATHS) | {
        "config/provider_native_capabilities.v1.json",
        "engine/provider_native_capabilities.py",
        "engine/provider_native_capability_source.py",
        "engine/provider_capacity_v2.py",
        "scripts/build_provider_native_capability_registration.py",
        "scripts/build_provider_capacity_v2.py",
    }
    assert artifacts.PRODUCER_COMMIT == contract.PRODUCER_COMMIT
    assert artifacts.TRANSPORT_SCHEMA_V3 == "mastermind.capacity_source_transport/v3"


def test_native_roundtrip_proves_exact_git_material_and_complete_closure(native_checkout):
    checkout, manifest, commit, _ = native_checkout
    assert manifest["schema_version"] == artifacts.NATIVE_TRANSPORT_SCHEMA
    assert [row["path"] for row in manifest["material"]] == list(artifacts.NATIVE_PRODUCER_MATERIAL_PATHS)
    retained, evidence = artifacts._verify_installed_repair_source(checkout, commit)
    assert retained == manifest
    assert evidence.object_count == manifest["object_count"]
    assert evidence.object_inventory_sha256 == manifest["object_inventory_sha256"]
    assert _git(checkout, "rev-parse", "HEAD") == commit
    assert _git(checkout, "remote") == ""
    assert _git(checkout, "status", "--porcelain") == ""
    assert not (checkout / "docs/nonmaterial-history.txt").exists()
    _git(checkout, "cat-file", "-e", commit + ":docs/nonmaterial-history.txt")
    for row in manifest["material"]:
        path = checkout / row["path"]
        assert artifacts.sha256_file(path) == row["sha256"]
        assert stat.S_IMODE(path.stat().st_mode) == (0o555 if row["mode"] == "100755" else 0o444)


@pytest.mark.parametrize("rewrite_manifest", [False, True])
def test_native_producer_substitution_with_safe_metadata_refuses(native_checkout, rewrite_manifest):
    checkout, manifest, commit, _ = native_checkout
    producer = checkout / "engine/provider_capacity_v2.py"
    producer.chmod(0o644)
    producer.write_bytes(b"substituted producer\n")
    producer.chmod(0o444)
    if rewrite_manifest:
        altered = copy.deepcopy(manifest)
        row = next(row for row in altered["material"] if row["path"] == "engine/provider_capacity_v2.py")
        row["sha256"] = artifacts.sha256_file(producer)
        row["size"] = producer.stat().st_size
        record = checkout / ".git/cf2-h0-transport-manifest.json"
        record.chmod(0o644)
        record.write_bytes(artifacts.canonical_json(altered))
        record.chmod(0o444)
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts._verify_installed_repair_source(checkout, commit)


@pytest.mark.parametrize("fault", ["missing", "extra", "duplicate", "symlink-mode", "bool-size", "wrong-commit"])
def test_native_manifest_refuses_unqualified_material(native_checkout, fault):
    _, manifest, commit, _ = native_checkout
    value = copy.deepcopy(manifest)
    if fault == "missing":
        value["material"].pop()
    elif fault == "extra":
        value["material"].append(dict(value["material"][0], path="caller.py"))
    elif fault == "duplicate":
        value["material"].append(dict(value["material"][0]))
    elif fault == "symlink-mode":
        value["material"][0]["mode"] = "120000"
    elif fault == "bool-size":
        value["material"][0]["size"] = True
    elif fault == "wrong-commit":
        value["commit"] = "0" * 40
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.validate_complete_transport_manifest(value, expected_commit=commit)


def test_native_archive_is_not_legacy_v3(native_checkout, tmp_path):
    _, _, commit, archive = native_checkout
    destination = tmp_path / "legacy-refused"
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.extract_source_transport_v3(archive, destination, expected_commit=commit)
    assert not destination.exists()


def test_legacy_archive_is_not_native_v1(tmp_path, monkeypatch):
    source, commit, _ = _complete_repository(tmp_path, monkeypatch)
    archive = tmp_path / "legacy.zip"
    artifacts.build_source_transport_v3(source, archive, commit=commit)
    monkeypatch.setattr(artifacts, "NATIVE_PRODUCER_COMMIT", commit)
    destination = tmp_path / "native-refused"
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.extract_native_source_transport(archive, destination, expected_commit=commit)
    assert not destination.exists()


def test_native_builder_refuses_foreign_commit_before_writing(native_source, tmp_path):
    source, _, _ = native_source
    archive = tmp_path / "must-not-exist.zip"
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.build_native_source_transport(source, archive, commit="0" * 40)
    assert not archive.exists()


def test_native_materializer_preserves_occupied_destination(native_checkout, tmp_path):
    _, _, commit, archive = native_checkout
    destination = tmp_path / "occupied"
    destination.mkdir()
    sentinel = destination / "sentinel"
    sentinel.write_bytes(b"original")
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.materialize_native_source_transport(archive, destination, expected_commit=commit)
    assert sentinel.read_bytes() == b"original"


def test_native_cli_has_no_material_or_source_profile_override():
    parser = artifacts._parser()
    for command, args in [
        ("build-native-source-transport", ["--source-repository", "source", "--output", "archive"]),
        ("extract-native-source-transport", ["--archive", "archive", "--destination", "output"]),
        ("materialize-native-source-transport", ["--archive", "archive", "--destination", "output"]),
    ]:
        complete = [command, *args, "--commit", artifacts.NATIVE_PRODUCER_COMMIT]
        assert parser.parse_args(complete).command == command
        with pytest.raises(SystemExit):
            parser.parse_args([*complete, "--material-path", "caller.py"])
