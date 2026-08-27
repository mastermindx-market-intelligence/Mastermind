from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ops.executive_os import capacity_host_artifacts as artifacts
from ops.executive_os import capacity_source_contract as contract


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.mark.parametrize("state", ("true", "disabled"))
def test_launchctl_disabled_parser_accepts_both_exact_macos_spellings(state: str) -> None:
    label = "com.mastermind.executive.worker.codex-pro-01"
    output = f'disabled services = {{\n    "{label}" => {state}\n}}\n'
    assert artifacts.parse_launchctl_disabled(output, label) == {
        "label": label,
        "normalized_state": "disabled",
        "observed_state": state,
    }


@pytest.mark.parametrize(
    "output",
    (
        '"com.mastermind.executive.worker.codex-pro-01" => false\n',
        '"com.mastermind.executive.worker.codex-pro-01" => enabled\n',
        '"com.mastermind.executive.worker.codex-pro-01-extra" => disabled\n',
        '"com.mastermind.executive.worker.codex-pro-01" => disabled extra\n',
        '"com.mastermind.executive.worker.codex-pro-01" => disabled\n'
        '"com.mastermind.executive.worker.codex-pro-01" => true\n',
    ),
)
def test_launchctl_disabled_parser_rejects_false_ambiguous_or_inexact_state(output: str) -> None:
    with pytest.raises(artifacts.CapacityHostArtifactError, match="LAUNCHCTL_DISABLED_STATE_INVALID"):
        artifacts.parse_launchctl_disabled(
            output,
            "com.mastermind.executive.worker.codex-pro-01",
        )


def test_cli_emits_safe_typed_refusal_code(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO('"com.mastermind.executive.worker.codex-pro-01" => false\n'),
    )
    assert artifacts.main(
        [
            "check-launchctl-disabled",
            "--label",
            "com.mastermind.executive.worker.codex-pro-01",
        ]
    ) == 65
    assert capsys.readouterr().err == (
        "capacity host artifact refused: LAUNCHCTL_DISABLED_STATE_INVALID\n"
    )


def _repository(tmp_path: Path) -> tuple[Path, str, tuple[str, ...]]:
    root = tmp_path / "source"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    paths = ("engine/provider_capacity.py", "scripts/build_provider_capacity.py")
    for index, relative in enumerate(paths):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture-{index}\n", encoding="utf-8")
        if relative.startswith("scripts/"):
            path.chmod(0o755)
    ignored = root / "ignored-secret.txt"
    ignored.write_text("must-not-cross\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored-secret.txt\n", encoding="utf-8")
    hook = root / ".git" / "hooks" / "post-checkout"
    hook.write_text("#!/bin/sh\nprintf operator-hook-secret\n", encoding="utf-8")
    hook.chmod(0o700)
    _git(root, "add", ".gitignore", *paths)
    _git(root, "commit", "-qm", "fixture")
    return root, _git(root, "rev-parse", "HEAD"), paths


def test_source_transport_contains_only_manifest_and_git_pack(tmp_path: Path) -> None:
    source, commit, paths = _repository(tmp_path)
    output = tmp_path / "transport.zip"
    manifest = artifacts.build_source_transport(
        source, output, commit=commit, material_paths=paths
    )
    assert manifest["commit"] == commit
    with zipfile.ZipFile(output) as archive:
        assert sorted(archive.namelist()) == ["manifest.json", "payload.pack"]
        encoded = b"".join(archive.read(name) for name in archive.namelist())
    assert b"must-not-cross" not in encoded
    assert b"operator-hook-secret" not in encoded
    extracted = tmp_path / "extracted"
    assert artifacts.extract_source_transport(
        output, extracted, expected_commit=commit, material_paths=paths
    ) == manifest
    assert sorted(path.name for path in extracted.iterdir()) == ["manifest.json", "payload.pack"]
    checkout = tmp_path / "installed"
    assert artifacts.materialize_source_transport(
        output, checkout, expected_commit=commit, material_paths=paths
    ) == manifest
    artifacts.verify_materialized_source(checkout, manifest=manifest)
    installed_config = _git(checkout, "config", "--local", "--list")
    assert "user.name" not in installed_config
    assert "user.email" not in installed_config
    assert not _git(checkout, "remote")
    assert not any(path.is_file() and os.access(path, os.X_OK) for path in (checkout / ".git" / "hooks").glob("*"))
    assert sorted(
        path.relative_to(checkout).as_posix()
        for path in checkout.rglob("*")
        if ".git" not in path.relative_to(checkout).parts and path.is_file()
    ) == list(paths)


def test_source_transport_materialization_normalizes_modes_under_root_umask(
    tmp_path: Path,
) -> None:
    source, commit, paths = _repository(tmp_path)
    output = tmp_path / "transport.zip"
    manifest = artifacts.build_source_transport(
        source, output, commit=commit, material_paths=paths
    )
    checkout = tmp_path / "installed-root-umask"

    previous_umask = os.umask(0o077)
    try:
        assert artifacts.materialize_source_transport(
            output, checkout, expected_commit=commit, material_paths=paths
        ) == manifest
    finally:
        os.umask(previous_umask)

    for row in manifest["material"]:
        expected_mode = 0o755 if row["mode"] == "100755" else 0o644
        assert stat.S_IMODE((checkout / row["path"]).stat().st_mode) == expected_mode
    artifacts.verify_materialized_source(checkout, manifest=manifest)


def test_source_transport_rejects_extra_archive_member_and_manifest_drift(tmp_path: Path) -> None:
    source, commit, paths = _repository(tmp_path)
    valid = tmp_path / "valid.zip"
    artifacts.build_source_transport(source, valid, commit=commit, material_paths=paths)
    invalid = tmp_path / "invalid.zip"
    with zipfile.ZipFile(valid) as source_zip, zipfile.ZipFile(invalid, "w") as target:
        for name in source_zip.namelist():
            target.writestr(name, source_zip.read(name))
        target.writestr("auth.json", b"secret")
    with pytest.raises(artifacts.CapacityHostArtifactError, match="INVENTORY"):
        artifacts.extract_source_transport(
            invalid,
            tmp_path / "bad-extract",
            expected_commit=commit,
            material_paths=paths,
        )


def test_source_transport_rejects_noncanonical_trailing_bytes(tmp_path: Path) -> None:
    source, commit, paths = _repository(tmp_path)
    valid = tmp_path / "valid.zip"
    artifacts.build_source_transport(source, valid, commit=commit, material_paths=paths)
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(valid.read_bytes() + b"operator-secret-tail")
    with pytest.raises(artifacts.CapacityHostArtifactError, match="NONCANONICAL"):
        artifacts.extract_source_transport(
            invalid,
            tmp_path / "bad-extract",
            expected_commit=commit,
            material_paths=paths,
        )


def test_closed_input_copy_binds_open_descriptor_owner_mode_and_digest(tmp_path: Path) -> None:
    source = tmp_path / "operator-input"
    source.write_bytes(b"closed-input")
    source.chmod(0o600)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "root-stage"
    assert artifacts.copy_closed_input(
        source,
        destination,
        operator_uid=os.getuid(),
        expected_sha256=expected,
    ) == {"sha256": expected, "size": 12}
    assert destination.read_bytes() == b"closed-input"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o400

    linked = tmp_path / "linked-input"
    os.link(source, linked)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="METADATA"):
        artifacts.copy_closed_input(
            source,
            tmp_path / "linked-stage",
            operator_uid=os.getuid(),
            expected_sha256=expected,
        )
    linked.unlink()
    source.chmod(0o622)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="METADATA"):
        artifacts.copy_closed_input(
            source,
            tmp_path / "writable-stage",
            operator_uid=os.getuid(),
            expected_sha256=expected,
        )


def test_recovery_intent_resumes_after_interruption_and_is_idempotent(tmp_path: Path) -> None:
    first = tmp_path / "worker-codex-pro-01.json"
    second = tmp_path / "worker-codex-pro-02.json"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    first.chmod(0o400)
    second.chmod(0o400)
    assert artifacts.verify_approved_xattrs(first)["inspected_object_count"] == 1
    archive = tmp_path / "recovered-carrier"
    archive.mkdir(mode=0o700)
    intent = artifacts.create_recovery_intent(
        archive,
        (first, second),
        expected_uid=os.getuid(),
    )
    assert len(intent["targets"]) == 2

    # Simulate SIGKILL after the first atomic move but before receipt creation.
    first.rename(archive / intent["targets"][0]["destination_name"])
    receipt = artifacts.resume_recovery_archive(archive, expected_uid=os.getuid())
    assert receipt["outcome"] == "INTERRUPTED_H0_PARTIAL_RECOVERED"
    assert receipt["recovered_target_count"] == 2
    assert not first.exists() and not second.exists()
    assert (archive / "recovery-receipt.json").is_file()
    assert artifacts.resume_recovery_archive(archive, expected_uid=os.getuid()) == receipt


def test_recovery_publications_resume_partial_candidates_and_fsync_moves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "worker-codex-pro-01.json"
    source.write_bytes(b"first")
    source.chmod(0o400)
    archive = tmp_path / "recovered-carrier"
    archive.mkdir(mode=0o700)
    original_publish = artifacts._publish_resumable_canonical_file

    def interrupt_intent(path: Path, payload: bytes, **kwargs: object) -> None:
        candidate = path.with_name(f".{path.name}.candidate")
        artifacts._write_bytes_exclusive(candidate, payload[: len(payload) // 2], 0o600)
        artifacts._fsync_directory(candidate.parent)
        raise artifacts.CapacityHostArtifactError("SIMULATED_INTENT_KILL")

    monkeypatch.setattr(artifacts, "_publish_resumable_canonical_file", interrupt_intent)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="INTENT_KILL"):
        artifacts.create_recovery_intent(archive, (source,), expected_uid=os.getuid())
    assert source.exists()
    assert not (archive / "recovery-intent.json").exists()
    assert (archive / ".recovery-intent.json.candidate").is_file()

    monkeypatch.setattr(artifacts, "_publish_resumable_canonical_file", original_publish)
    artifacts.create_recovery_intent(archive, (source,), expected_uid=os.getuid())
    assert (archive / "recovery-intent.json").is_file()
    assert not (archive / ".recovery-intent.json.candidate").exists()

    fsynced: list[Path] = []
    original_fsync = artifacts._fsync_directory

    def record_fsync(path: Path) -> None:
        fsynced.append(path)
        original_fsync(path)

    def interrupt_receipt(path: Path, payload: bytes, **kwargs: object) -> None:
        if path.name != "recovery-receipt.json":
            original_publish(path, payload, **kwargs)
            return
        candidate = path.with_name(f".{path.name}.candidate")
        artifacts._write_bytes_exclusive(candidate, payload[: len(payload) // 2], 0o600)
        record_fsync(candidate.parent)
        raise artifacts.CapacityHostArtifactError("SIMULATED_RECEIPT_KILL")

    monkeypatch.setattr(artifacts, "_fsync_directory", record_fsync)
    monkeypatch.setattr(artifacts, "_publish_resumable_canonical_file", interrupt_receipt)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RECEIPT_KILL"):
        artifacts.resume_recovery_archive(archive, expected_uid=os.getuid())
    assert not source.exists()
    assert (archive / ".recovery-receipt.json.candidate").is_file()
    assert source.parent in fsynced and archive in fsynced

    monkeypatch.setattr(artifacts, "_publish_resumable_canonical_file", original_publish)
    receipt = artifacts.resume_recovery_archive(archive, expected_uid=os.getuid())
    assert receipt["outcome"] == "INTERRUPTED_H0_PARTIAL_RECOVERED"
    assert not (archive / ".recovery-receipt.json.candidate").exists()
    assert (archive / "recovery-receipt.json").is_file()


def test_closed_tree_rejects_caller_controlled_extended_attributes(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"closed")
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["/usr/bin/xattr", "-w", "com.mastermind.test", "unsafe", candidate],
                check=True,
                capture_output=True,
            )
        elif hasattr(os, "setxattr"):
            os.setxattr(candidate, b"user.mastermind-test", b"unsafe", follow_symlinks=False)
        else:
            pytest.skip("extended attribute fixture is unavailable")
    except OSError:
        pytest.skip("test filesystem does not support extended attributes")
    candidate.chmod(0o400)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="UNAPPROVED"):
        artifacts.verify_approved_xattrs(candidate)


def _record_line(path: str, payload: bytes) -> list[str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    return [path, f"sha256={digest}", str(len(payload))]


def _wheel(path: Path, *, extra: tuple[str, bytes] | None = None) -> None:
    files = {
        "yaml/__init__.py": b"__version__ = '6.0.3'\n",
        "_yaml/__init__.py": b"from yaml import *\n",
        "pyyaml-6.0.3.dist-info/METADATA": b"Name: PyYAML\nVersion: 6.0.3\n",
    }
    if extra is not None:
        files[extra[0]] = extra[1]
    rows = [_record_line(name, payload) for name, payload in files.items()]
    rows.append(["pyyaml-6.0.3.dist-info/RECORD", "", ""])
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    files["pyyaml-6.0.3.dist-info/RECORD"] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)


def test_wheel_extraction_is_pip_free_record_closed_and_tree_bound(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    python = runtime / "bin" / "python3.12"
    python.write_bytes(b"python")
    os.chmod(python, 0o555)
    wheel = tmp_path / "pyyaml.whl"
    _wheel(wheel)
    artifacts.extract_pyyaml_wheel(wheel, runtime)
    record_digest = artifacts.verify_pyyaml_record(runtime)
    before = artifacts.runtime_tree_digest(runtime)
    assert len(record_digest) == 64 and len(before) == 64
    drifted = runtime / "lib/python3.12/site-packages/yaml/__init__.py"
    os.chmod(drifted, 0o644)
    drifted.write_bytes(b"drift")
    with pytest.raises(artifacts.CapacityHostArtifactError, match="HASH_MISMATCH"):
        artifacts.verify_pyyaml_record(runtime)
    assert artifacts.runtime_tree_digest(runtime) != before


@pytest.mark.parametrize(
    "name",
    ["../escape.py", "sitecustomize.py", "yaml/../../escape.py"],
)
def test_wheel_extraction_rejects_path_and_site_injection(tmp_path: Path, name: str) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    wheel = tmp_path / "bad.whl"
    _wheel(wheel, extra=(name, b"bad"))
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.extract_pyyaml_wheel(wheel, runtime)


def test_runtime_tree_digest_rejects_symlinks_and_hardlinks(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    payload = runtime / "payload"
    payload.write_bytes(b"value")
    os.link(payload, runtime / "hardlink")
    with pytest.raises(artifacts.CapacityHostArtifactError, match="OBJECT_INVALID"):
        artifacts.runtime_tree_digest(runtime)
    (runtime / "hardlink").unlink()
    (runtime / "link").symlink_to(payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SYMLINK"):
        artifacts.runtime_tree_digest(runtime)


def test_v2_transport_schema_is_explicit_and_does_not_reinterpret_v1() -> None:
    assert artifacts.TRANSPORT_SCHEMA == "mastermind.capacity_source_transport/v1"
    assert artifacts.TRANSPORT_SCHEMA_V2 == "mastermind.capacity_source_transport/v2"


def test_closed_tree_digest_uses_exact_canonical_rows_and_descriptor_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "alpha.txt"
    payload.write_bytes(b"alpha\n")
    payload.chmod(0o400)
    root.chmod(0o700)
    root_info = root.stat()
    payload_info = payload.stat()
    rows = [
        {
            "path": ".",
            "type": "directory",
            "uid": root_info.st_uid,
            "gid": root_info.st_gid,
            "mode": "0700",
            "nlink": root_info.st_nlink,
        },
        {
            "path": "alpha.txt",
            "type": "file",
            "uid": payload_info.st_uid,
            "gid": payload_info.st_gid,
            "mode": "0400",
            "nlink": 1,
            "size": 6,
            "sha256": hashlib.sha256(b"alpha\n").hexdigest(),
        },
    ]
    expected = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    def pathname_access_forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("public v2 closure must not use pathname tree reads")

    monkeypatch.setattr(Path, "rglob", pathname_access_forbidden)
    monkeypatch.setattr(Path, "lstat", pathname_access_forbidden)
    monkeypatch.setattr(Path, "read_bytes", pathname_access_forbidden)
    assert artifacts.closed_tree_digest(
        root,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    ) == expected


def test_closed_tree_digest_refuses_directory_mutation_during_child_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    payload.chmod(0o400)
    root.chmod(0o700)
    original_sha256 = artifacts._descriptor_sha256
    mutation_done = False

    def mutate_after_child_read(descriptor: int) -> str:
        nonlocal mutation_done
        digest = original_sha256(descriptor)
        if not mutation_done:
            mutation_done = True
            late = root / "late"
            late.write_bytes(b"late")
            late.chmod(0o400)
        return digest

    monkeypatch.setattr(artifacts, "_descriptor_sha256", mutate_after_child_read)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="DIRECTORY_DRIFT"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


def test_closed_tree_digest_refuses_wrong_owner_group_mode_links_and_types(
    tmp_path: Path,
) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    payload.chmod(0o400)
    root.chmod(0o700)

    with pytest.raises(artifacts.CapacityHostArtifactError, match="OWNER_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid() + 1, expected_gid=os.getgid()
        )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="OWNER_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid() + 1
        )

    payload.chmod(0o600)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="MODE_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )
    payload.chmod(0o400)

    hardlink = root / "hardlink"
    os.link(payload, hardlink)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="LINK_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )
    hardlink.unlink()

    symlink = root / "symlink"
    symlink.symlink_to(payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="TYPE_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )
    symlink.unlink()

    fifo = root / "fifo"
    os.mkfifo(fifo, 0o400)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="TYPE_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


def test_closed_tree_digest_refuses_unapproved_xattrs(tmp_path: Path) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    root.chmod(0o700)
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["/usr/bin/xattr", "-w", "com.mastermind.test", "unsafe", payload],
                check=True,
                capture_output=True,
            )
        elif hasattr(os, "setxattr"):
            os.setxattr(payload, b"user.mastermind-test", b"unsafe", follow_symlinks=False)
        else:
            pytest.skip("extended attribute fixture is unavailable")
    except OSError:
        pytest.skip("test filesystem does not support extended attributes")
    payload.chmod(0o400)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="XATTR_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS xattr name contract")
def test_closed_tree_digest_refuses_newline_bearing_unapproved_xattr_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    subprocess.run(
        [
            "/usr/bin/xattr",
            "-w",
            "com.apple.provenance\n",
            "unsafe",
            payload,
        ],
        check=True,
        capture_output=True,
    )
    payload.chmod(0o400)
    root.chmod(0o700)

    with pytest.raises(artifacts.CapacityHostArtifactError, match="XATTR_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS ACL contract")
def test_closed_tree_digest_refuses_extended_acl(tmp_path: Path) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    payload.chmod(0o400)
    root.chmod(0o700)
    subprocess.run(
        ["/bin/chmod", "+a", f"{pwd.getpwuid(os.getuid()).pw_name} allow read", payload],
        check=True,
        capture_output=True,
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="ACL_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


def _complete_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, str]:
    """Create one commit whose closure is strictly wider than the CF1 projection."""

    root = tmp_path / "complete-source"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    for index, relative in enumerate(contract.PRODUCER_MATERIAL_PATHS):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"material-{index}\n", encoding="utf-8")
        if relative.startswith("scripts/"):
            path.chmod(0o755)
    history = root / "docs" / "nonmaterial-history.txt"
    history.parent.mkdir(parents=True)
    history.write_bytes((b"old nonmaterial payload\n" * 4096) + b"old\n")
    _git(root, "add", *contract.PRODUCER_MATERIAL_PATHS, history.relative_to(root).as_posix())
    _git(root, "commit", "-qm", "fixture parent")
    history.write_bytes((b"new nonmaterial payload\n" * 4096) + b"new\n")
    _git(root, "add", history.relative_to(root).as_posix())
    _git(root, "commit", "-qm", "fixture complete")
    commit = _git(root, "rev-parse", "HEAD")
    nonmaterial_oid = _git(root, "rev-parse", f"{commit}:docs/nonmaterial-history.txt")
    monkeypatch.setattr(artifacts, "PRODUCER_COMMIT", commit, raising=False)
    return root, commit, nonmaterial_oid


def _inventory_bytes(rows: object) -> bytes:
    return b"".join(
        f"{row.oid} {row.object_type} {row.size}\n".encode("ascii")
        for row in rows  # type: ignore[union-attr]
    )


def _write_v2_archive(path: Path, manifest: dict[str, object], payload: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, body in (
            ("manifest.json", artifacts.canonical_json(manifest)),
            ("payload.pack", payload),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o400) << 16
            archive.writestr(info, body)


def _v2_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, object], str]:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive = tmp_path / "complete-transport.zip"
    manifest = artifacts.build_source_transport_v2(
        source, archive, commit=commit
    )
    checkout = tmp_path / "complete-checkout"
    artifacts.materialize_source_transport_v2(
        archive, checkout, expected_commit=commit
    )
    return checkout, manifest, commit


def _replace_closed_file(path: Path, payload: bytes) -> None:
    parent = path.parent
    parent.chmod(0o755)
    if path.exists() or path.is_symlink():
        path.chmod(0o600, follow_symlinks=False)
        path.unlink()
    path.write_bytes(payload)
    path.chmod(0o444)
    parent.chmod(0o555)


def _create_closed_file(path: Path, payload: bytes = b"") -> None:
    parents: list[Path] = []
    current = path.parent
    while not current.exists():
        parents.append(current)
        current = current.parent
    current.chmod(0o755)
    for parent in reversed(parents):
        parent.mkdir(mode=0o755)
    path.write_bytes(payload)
    path.chmod(0o444)
    for parent in [path.parent, *reversed(parents[:-1])]:
        parent.chmod(0o555)
    current.chmod(0o555)


def test_complete_transport_v2_binds_nonmaterial_closure_and_exact_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive_path = tmp_path / "complete-v2.zip"

    manifest = artifacts.build_source_transport_v2(
        source, archive_path, commit=commit
    )
    rows = artifacts.enumerate_reachable_objects(source, commit)
    inventory_bytes = _inventory_bytes(rows)
    assert nonmaterial_oid in {row.oid for row in rows}
    assert manifest == {
        "schema_version": "mastermind.capacity_source_transport/v2",
        "repository": "mastermindx-market-intelligence/macro",
        "commit": commit,
        "object_format": "sha1",
        "closure_kind": "complete_reachable_commit_graph",
        "payload_sha256": manifest["payload_sha256"],
        "object_count": len(rows),
        "object_inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "material": manifest["material"],
    }
    assert [row["path"] for row in manifest["material"]] == list(
        contract.PRODUCER_MATERIAL_PATHS
    )

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == ["manifest.json", "payload.pack"]
        assert archive.comment == b""
        for info in infos:
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.flag_bits & 0x1 == 0
            assert info.extra == b""
            assert info.comment == b""
            assert stat.S_IMODE(info.external_attr >> 16) == 0o400

    extracted = tmp_path / "complete-extracted"
    assert artifacts.extract_source_transport_v2(
        archive_path, extracted, expected_commit=commit
    ) == manifest
    checkout = tmp_path / "complete-installed"
    assert artifacts.materialize_source_transport_v2(
        archive_path, checkout, expected_commit=commit
    ) == manifest
    evidence = artifacts.verify_complete_repository(checkout, manifest)
    assert evidence.object_count == manifest["object_count"]
    assert evidence.object_inventory_sha256 == manifest["object_inventory_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", evidence.source_tree_sha256)
    assert not list((checkout / ".git" / "objects" / "pack").glob("*.promisor"))
    assert "partialclone" not in _git(checkout, "config", "--local", "--list").lower()


def test_complete_transport_v2_semantic_inventory_survives_different_pack_layouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    first_path = tmp_path / "first.zip"
    first = artifacts.build_source_transport_v2(source, first_path, commit=commit)
    rows = artifacts.enumerate_reachable_objects(source, commit)
    object_input = b"".join(f"{row.oid}\n".encode("ascii") for row in rows)
    alternate_payload = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-C",
            str(source),
            "pack-objects",
            "--stdout",
            "--window=0",
            "--depth=0",
        ],
        input=object_input,
        check=True,
        capture_output=True,
        env=artifacts._git_environment(),
    ).stdout
    with zipfile.ZipFile(first_path) as archive:
        first_payload = archive.read("payload.pack")
    assert alternate_payload != first_payload

    second = dict(first)
    second["payload_sha256"] = hashlib.sha256(alternate_payload).hexdigest()
    second_path = tmp_path / "second.zip"
    _write_v2_archive(second_path, second, alternate_payload)
    first_checkout = tmp_path / "first-checkout"
    second_checkout = tmp_path / "second-checkout"
    artifacts.materialize_source_transport_v2(first_path, first_checkout, expected_commit=commit)
    artifacts.materialize_source_transport_v2(second_path, second_checkout, expected_commit=commit)
    first_evidence = artifacts.verify_complete_repository(first_checkout, first)
    second_evidence = artifacts.verify_complete_repository(second_checkout, second)
    assert first_evidence.object_count == second_evidence.object_count
    assert (
        first_evidence.object_inventory_sha256
        == second_evidence.object_inventory_sha256
    )
    assert first["payload_sha256"] != second["payload_sha256"]
    assert hashlib.sha256(first_path.read_bytes()).hexdigest() != hashlib.sha256(
        second_path.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    "field,value",
    (
        ("object_count", 1),
        ("object_inventory_sha256", "f" * 64),
    ),
)
def test_complete_materializer_refuses_manifest_object_inventory_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    with zipfile.ZipFile(valid_path) as archive:
        payload = archive.read("payload.pack")
    drifted = dict(manifest)
    drifted[field] = value
    drifted_path = tmp_path / f"drifted-{field}.zip"
    _write_v2_archive(drifted_path, drifted, payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="OBJECT_INVENTORY"):
        artifacts.materialize_source_transport_v2(
            drifted_path,
            tmp_path / f"drifted-{field}",
            expected_commit=commit,
        )


@pytest.mark.parametrize("mutation", ("type", "size"))
def test_complete_materializer_refuses_semantic_object_type_or_size_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "semantic-valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    rows = artifacts.enumerate_reachable_objects(source, commit)
    with zipfile.ZipFile(valid_path) as archive:
        payload = archive.read("payload.pack")
    drifted_rows: list[bytes] = []
    for index, row in enumerate(rows):
        object_type = row.object_type
        size = row.size
        if index == 0 and mutation == "type":
            object_type = "blob" if object_type != "blob" else "tree"
        if index == 0 and mutation == "size":
            size += 1
        drifted_rows.append(f"{row.oid} {object_type} {size}\n".encode("ascii"))
    drifted = dict(manifest)
    drifted["object_inventory_sha256"] = hashlib.sha256(
        b"".join(drifted_rows)
    ).hexdigest()
    drifted_path = tmp_path / f"semantic-{mutation}.zip"
    _write_v2_archive(drifted_path, drifted, payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="OBJECT_INVENTORY"):
        artifacts.materialize_source_transport_v2(
            drifted_path,
            tmp_path / f"semantic-{mutation}",
            expected_commit=commit,
        )


def test_complete_transport_v2_streams_pack_and_refuses_pack_trailer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    with zipfile.ZipFile(valid_path) as archive:
        payload = archive.read("payload.pack") + b"trailer"
    invalid = dict(manifest)
    invalid["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    invalid_path = tmp_path / "trailer.zip"
    _write_v2_archive(invalid_path, invalid, payload)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="PACK"):
        artifacts.extract_source_transport_v2(
            invalid_path, tmp_path / "trailer-extract", expected_commit=commit
        )


def test_complete_transport_v2_does_not_full_buffer_pack_or_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive_path = tmp_path / "streamed.zip"
    manifest = artifacts.build_source_transport_v2(source, archive_path, commit=commit)
    original_read_bytes = Path.read_bytes
    original_zip_read = zipfile.ZipFile.read

    def reject_full_buffer(path: Path) -> bytes:
        if path.suffix in {".zip", ".pack"}:
            raise AssertionError("v2 transport pack/archive must be streamed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_full_buffer)

    def reject_archive_read(
        archive: zipfile.ZipFile,
        name: object,
        password: bytes | None = None,
    ) -> bytes:
        if name == "payload.pack" or getattr(name, "filename", None) == "payload.pack":
            raise AssertionError("v2 payload must use bounded ZipExtFile reads")
        return original_zip_read(archive, name, password)

    monkeypatch.setattr(zipfile.ZipFile, "read", reject_archive_read)
    artifacts.extract_source_transport_v2(
        archive_path, tmp_path / "streamed-extract", expected_commit=commit
    )
    checkout = tmp_path / "streamed-checkout"
    artifacts.materialize_source_transport_v2(
        archive_path, checkout, expected_commit=commit
    )
    assert artifacts.verify_complete_repository(checkout, manifest).object_count == manifest[
        "object_count"
    ]


def test_complete_materializer_refuses_removed_nonmaterial_blob_without_promisor_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, commit, nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid_path = tmp_path / "complete-valid.zip"
    manifest = artifacts.build_source_transport_v2(source, valid_path, commit=commit)
    rows = tuple(
        row
        for row in artifacts.enumerate_reachable_objects(source, commit)
        if row.oid != nonmaterial_oid
    )
    payload = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "-C",
            str(source),
            "pack-objects",
            "--stdout",
        ],
        input=b"".join(f"{row.oid}\n".encode("ascii") for row in rows),
        check=True,
        capture_output=True,
        env=artifacts._git_environment(),
    ).stdout
    incomplete = dict(manifest)
    incomplete["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    incomplete["object_count"] = len(rows)
    incomplete["object_inventory_sha256"] = hashlib.sha256(
        _inventory_bytes(rows)
    ).hexdigest()
    incomplete_path = tmp_path / "incomplete-nonmaterial.zip"
    _write_v2_archive(incomplete_path, incomplete, payload)

    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.materialize_source_transport_v2(
            incomplete_path,
            tmp_path / "incomplete-nonmaterial",
            expected_commit=commit,
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
