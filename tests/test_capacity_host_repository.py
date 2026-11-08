"""Capacity host repository cases; shared helpers retain their original owner."""
from __future__ import annotations

from tests.test_capacity_host_artifacts import (
    Path,
    _complete_repository,
    _create_closed_file,
    _git,
    _replace_closed_file,
    _repository,
    _v2_checkout,
    artifacts,
    contract,
    os,
    pytest,
    subprocess,
)


@pytest.mark.parametrize(
    "case",
    (
        "promisor",
        "alternate",
        "shallow",
        "remote",
        "partial_clone",
        "filter",
        "loose_replace",
        "packed_replace",
        "graft",
        "attached",
        "dirty",
        "twelfth_file",
        "linked_material",
        "wrong_mode",
    ),
)
def test_complete_repository_refuses_forbidden_or_unsafe_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    checkout, manifest, commit = _v2_checkout(tmp_path, monkeypatch)
    git_dir = checkout / ".git"
    pack_dir = git_dir / "objects" / "pack"
    if case == "promisor":
        pack = next(pack_dir.glob("*.pack"))
        _create_closed_file(pack.with_suffix(".promisor"))
    elif case == "alternate":
        _create_closed_file(git_dir / "objects" / "info" / "alternates", b"/tmp/objects\n")
    elif case == "shallow":
        _create_closed_file(git_dir / "shallow", f"{commit}\n".encode("ascii"))
    elif case in {"remote", "partial_clone", "filter"}:
        config = (git_dir / "config").read_bytes()
        addition = {
            "remote": b'[remote "origin"]\n\turl = file:///tmp/source\n',
            "partial_clone": b"[extensions]\n\tpartialClone = origin\n",
            "filter": b'[filter "unsafe"]\n\tclean = /bin/false\n',
        }[case]
        _replace_closed_file(git_dir / "config", config + addition)
    elif case == "loose_replace":
        _create_closed_file(git_dir / "refs" / "replace" / commit, f"{commit}\n".encode("ascii"))
    elif case == "packed_replace":
        _create_closed_file(git_dir / "packed-refs", f"{commit} refs/replace/{commit}\n".encode("ascii"))
    elif case == "graft":
        _create_closed_file(git_dir / "info" / "grafts", f"{commit}\n".encode("ascii"))
    elif case == "attached":
        _create_closed_file(git_dir / "refs" / "heads" / "fixture", f"{commit}\n".encode("ascii"))
        _replace_closed_file(git_dir / "HEAD", b"ref: refs/heads/fixture\n")
    elif case == "dirty":
        material = checkout / contract.PRODUCER_MATERIAL_PATHS[0]
        _replace_closed_file(material, b"dirty\n")
    elif case == "twelfth_file":
        _create_closed_file(checkout / "unexpected.txt", b"unexpected\n")
    elif case == "linked_material":
        material = checkout / contract.PRODUCER_MATERIAL_PATHS[0]
        outside = tmp_path / "outside-link"
        outside.write_bytes(material.read_bytes())
        material.parent.chmod(0o755)
        material.chmod(0o600)
        material.unlink()
        os.link(outside, material)
        material.chmod(0o444)
        material.parent.chmod(0o555)
    else:
        (checkout / contract.PRODUCER_MATERIAL_PATHS[0]).chmod(0o644)
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.verify_complete_repository(checkout, manifest)


@pytest.mark.parametrize(
    "case",
    (
        "alternate_symlink",
        "alternate_hardlink",
        "alternate_lock",
        "shallow_symlink",
        "shallow_hardlink",
        "shallow_lock",
        "promisor_symlink",
        "promisor_hardlink",
        "promisor_lock",
        "config_symlink",
        "config_hardlink",
        "config_lock",
        "packed_refs_symlink",
        "packed_refs_hardlink",
        "packed_refs_lock",
        "graft_symlink",
        "graft_hardlink",
        "graft_lock",
        "pack_symlink",
        "pack_hardlink",
        "pack_lock",
        "index_symlink",
        "index_hardlink",
        "index_lock",
    ),
)
def test_complete_repository_direct_metadata_refusal_precedes_git_fsck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    checkout, manifest, _commit = _v2_checkout(tmp_path, monkeypatch)
    git_dir = checkout / ".git"
    pack_dir = git_dir / "objects" / "pack"
    pack = next(pack_dir.glob("*.pack"))
    index = next(pack_dir.glob("*.idx"))
    base_case, mutation = case.rsplit("_", 1)
    target = {
        "alternate": git_dir / "objects" / "info" / "alternates",
        "shallow": git_dir / "shallow",
        "promisor": pack.with_suffix(".promisor"),
        "config": git_dir / "config",
        "packed_refs": git_dir / "packed-refs",
        "graft": git_dir / "info" / "grafts",
        "pack": pack,
        "index": index,
    }[base_case]
    if mutation == "lock":
        _create_closed_file(target.with_name(f"{target.name}.lock"))
    elif mutation == "hardlink":
        outside = tmp_path / f"{base_case}-outside"
        if target.exists():
            outside.write_bytes(target.read_bytes())
            target.parent.chmod(0o755)
            target.chmod(0o600)
            target.unlink()
        else:
            outside.write_bytes(b"unsafe\n")
            target.parent.chmod(0o755)
        os.link(outside, target)
        target.chmod(0o444)
        target.parent.chmod(0o555)
    else:
        outside = tmp_path / f"{base_case}-symlink-target"
        outside.write_bytes(target.read_bytes() if target.exists() else b"unsafe\n")
        target.parent.chmod(0o755)
        if target.exists():
            target.chmod(0o600)
            target.unlink()
        target.symlink_to(outside)
        target.parent.chmod(0o555)

    def git_must_not_run(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("descriptor-first refusal must precede Git")

    monkeypatch.setattr(artifacts, "_run_git", git_must_not_run)
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.verify_complete_repository(checkout, manifest)


def test_complete_repository_refuses_incomplete_v1_after_promisor_marker_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    v2_archive = tmp_path / "complete.zip"
    v2_manifest = artifacts.build_source_transport_v2(source, v2_archive, commit=commit)
    v1_archive = tmp_path / "incomplete.zip"
    artifacts.build_source_transport(
        source,
        v1_archive,
        commit=commit,
        material_paths=contract.PRODUCER_MATERIAL_PATHS,
    )
    checkout = tmp_path / "incomplete-checkout"
    artifacts.materialize_source_transport(
        v1_archive,
        checkout,
        expected_commit=commit,
        material_paths=contract.PRODUCER_MATERIAL_PATHS,
    )
    promisor = next((checkout / ".git" / "objects" / "pack").glob("*.promisor"))
    promisor.unlink()
    _git(checkout, "config", "--unset", "extensions.partialClone")
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.verify_complete_repository(checkout, v2_manifest)


def test_v2_cli_names_are_separate_and_accept_no_material_override() -> None:
    parser = artifacts._parser()
    build = parser.parse_args(
        [
            "build-source-transport-v2",
            "--source-repository",
            "/operator/macro",
            "--output",
            "/operator/transport.zip",
            "--commit",
            "a" * 40,
        ]
    )
    assert build.command == "build-source-transport-v2"
    assert not hasattr(build, "material_path")
    materialize = parser.parse_args(
        [
            "materialize-source-transport-v2",
            "--archive",
            "/stage/transport.zip",
            "--destination",
            "/stage/source",
            "--commit",
            "a" * 40,
        ]
    )
    assert materialize.command == "materialize-source-transport-v2"
    assert not hasattr(materialize, "material_path")
    extract = parser.parse_args(
        [
            "extract-source-transport-v2",
            "--archive",
            "/stage/transport.zip",
            "--destination",
            "/stage/extracted",
            "--commit",
            "a" * 40,
        ]
    )
    assert extract.command == "extract-source-transport-v2"
    assert not hasattr(extract, "material_path")
    verify = parser.parse_args(
        [
            "verify-complete-repository",
            "--source-root",
            "/installed/source",
            "--manifest",
            "/installed/source/.git/cf2-h0-transport-manifest.json",
            "--commit",
            "a" * 40,
        ]
    )
    assert verify.command == "verify-complete-repository"
    assert not hasattr(verify, "material_path")
    with pytest.raises(SystemExit) as refusal:
        parser.parse_args(
            [
                "build-source-transport-v2",
                "--source-repository",
                "/operator/macro",
                "--output",
                "/operator/transport.zip",
                "--commit",
                "a" * 40,
                "--material-path",
                "attacker-selected.py",
            ]
        )
    assert refusal.value.code == 2


def test_v3_cli_names_are_separate_and_accept_no_material_override() -> None:
    parser = artifacts._parser()
    for command, path_flag in (
        ("build-source-transport-v3", "--source-repository"),
        ("extract-source-transport-v3", "--archive"),
        ("materialize-source-transport-v3", "--archive"),
    ):
        arguments = [
            command,
            path_flag,
            "/operator/input",
            "--output" if command.startswith("build-") else "--destination",
            "/operator/output",
            "--commit",
            "a" * 40,
        ]
        parsed = parser.parse_args(arguments)
        assert parsed.command == command
        assert not hasattr(parsed, "material_path")
        with pytest.raises(SystemExit) as refusal:
            parser.parse_args([*arguments, "--material-path", "attacker-selected.py"])
        assert refusal.value.code == 2


def test_complete_repository_refuses_dangling_loose_object_before_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, manifest, _commit = _v2_checkout(tmp_path, monkeypatch)
    objects = checkout / ".git" / "objects"
    objects.chmod(0o755)
    subprocess.run(
        ["/usr/bin/git", "-C", str(checkout), "hash-object", "-w", "--stdin"],
        input=b"dangling loose object\n",
        check=True,
        capture_output=True,
        env=artifacts._git_environment(),
    )
    artifacts._normalize_complete_repository_modes(checkout, manifest)

    def git_must_not_run(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("physical object namespace must refuse before Git")

    monkeypatch.setattr(artifacts, "_run_git", git_must_not_run)
    monkeypatch.setattr(artifacts, "_run_git_v2", git_must_not_run, raising=False)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="OBJECT_NAMESPACE"):
        artifacts.verify_complete_repository(checkout, manifest)


def test_complete_repository_refuses_transient_restored_index_swap_across_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, manifest, _commit = _v2_checkout(tmp_path, monkeypatch)
    index = checkout / ".git" / "index"
    parked = checkout / ".git" / ".index.parked"
    original_run = artifacts.subprocess.run
    swapped = False

    def transient_swap(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal swapped
        command = args[0]
        if not swapped and isinstance(command, list) and command[:1] == ["/usr/bin/git"]:
            swapped = True
            index.parent.chmod(0o755)
            index.chmod(0o600)
            index.rename(parked)
            index.write_bytes(parked.read_bytes())
            index.chmod(0o444)
            try:
                return original_run(*args, **kwargs)  # type: ignore[arg-type]
            finally:
                index.chmod(0o600)
                index.unlink()
                parked.rename(index)
                index.chmod(0o444)
                index.parent.chmod(0o555)
        return original_run(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(artifacts.subprocess, "run", transient_swap)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_VIEW_DRIFT"):
        artifacts.verify_complete_repository(checkout, manifest)
    assert swapped


@pytest.mark.parametrize(
    "case",
    (
        "sparse_content",
        "sparse_lock",
        "info_attributes",
        "hook",
        "unrelated_lock",
    ),
)
def test_complete_repository_refuses_full_optional_metadata_namespace_before_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    checkout, manifest, _commit = _v2_checkout(tmp_path, monkeypatch)
    git_dir = checkout / ".git"
    sparse = git_dir / "info" / "sparse-checkout"
    if case == "sparse_content":
        _replace_closed_file(sparse, b"/wrong/path\n")
    elif case == "sparse_lock":
        _create_closed_file(sparse.with_name("sparse-checkout.lock"))
    elif case == "info_attributes":
        _create_closed_file(git_dir / "info" / "attributes", b"* -text\n")
    elif case == "hook":
        _create_closed_file(git_dir / "hooks" / "post-checkout", b"#!/bin/sh\n")
    else:
        _create_closed_file(git_dir / "unrelated.lock")

    def git_must_not_run(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("optional metadata namespace must refuse before Git")

    monkeypatch.setattr(artifacts, "_run_git", git_must_not_run)
    monkeypatch.setattr(artifacts, "_run_git_v2", git_must_not_run, raising=False)
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.verify_complete_repository(checkout, manifest)


def test_v1_extract_existing_destination_preserves_file_exists_refusal(
    tmp_path: Path,
) -> None:
    source, commit, paths = _repository(tmp_path)
    archive = tmp_path / "v1-existing-destination.zip"
    artifacts.build_source_transport(
        source, archive, commit=commit, material_paths=paths
    )
    destination = tmp_path / "v1-existing-destination"
    destination.mkdir()
    sentinel = destination / "sentinel"
    sentinel.write_bytes(b"retain-v1-destination")

    with pytest.raises(FileExistsError):
        artifacts.extract_source_transport(
            archive,
            destination,
            expected_commit=commit,
            material_paths=paths,
        )
    assert sentinel.read_bytes() == b"retain-v1-destination"


def test_v2_extract_closes_archive_descriptor_when_destination_mkdir_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive = tmp_path / "v2-existing-destination.zip"
    artifacts.build_source_transport_v2(source, archive, commit=commit)
    destination = tmp_path / "v2-existing-destination"
    destination.mkdir()
    opened_descriptors: list[int] = []
    original_open = artifacts.os.open

    def record_archive_open(path: object, *args: object, **kwargs: object) -> int:
        descriptor = original_open(path, *args, **kwargs)  # type: ignore[arg-type]
        if os.fspath(path) == os.fspath(archive):
            opened_descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(artifacts.os, "open", record_archive_open)
    with pytest.raises(FileExistsError):
        artifacts.extract_source_transport_v2(
            archive, destination, expected_commit=commit
        )

    assert len(opened_descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(opened_descriptors[0])
