from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import pwd
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
