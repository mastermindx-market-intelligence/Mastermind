from __future__ import annotations

import base64
import csv
import ctypes
import errno
import hashlib
import io
import json
import os
import pwd
import re
import resource
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

from ops.executive_os import capacity_host_artifacts as artifacts
from ops.executive_os import capacity_source_contract as contract


def _open_fd_inventory() -> frozenset[int]:
    return frozenset(int(name) for name in os.listdir("/dev/fd") if name.isdecimal())


def _overlay_fixture_identity_as_root(
    monkeypatch: pytest.MonkeyPatch, *, device: int
) -> None:
    """Represent a user-owned temporary tree as root-owned production metadata."""

    original_fstat = os.fstat
    original_stat = os.stat
    original_lstat = os.lstat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if info.st_dev == device and info.st_uid == os.getuid():
            return _StatOverlay(info, st_uid=0, st_gid=0)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs)))
    monkeypatch.setattr(os, "lstat", lambda *args, **kwargs: overlay(original_lstat(*args, **kwargs)))


class _StatOverlay:
    def __init__(self, value: os.stat_result, **changes: int) -> None:
        self._value = value
        self._changes = changes

    def __getattr__(self, name: str) -> object:
        if name in self._changes:
            return self._changes[name]
        return getattr(self._value, name)


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


def _legacy_recovery_v1_file_tree_digest(path: Path) -> str:
    info = path.lstat()
    rows = [
        {
            "gid": info.st_gid,
            "mode": f"{stat.S_IMODE(info.st_mode):04o}",
            "nlink": 1,
            "path": ".",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": info.st_size,
            "type": "file",
            "uid": info.st_uid,
        }
    ]
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_pre_flags_recovery_v1_intent(
    archive: Path, sources: tuple[Path, ...]
) -> tuple[dict[str, object], bytes]:
    targets = [
        {
            "destination_name": f"{index}-{source.name}",
            "source_path": os.fspath(source),
            "tree_sha256": _legacy_recovery_v1_file_tree_digest(source),
        }
        for index, source in enumerate(sorted(sources, key=os.fspath), start=1)
    ]
    intent: dict[str, object] = {
        "schema_version": artifacts.RECOVERY_INTENT_SCHEMA,
        "targets": targets,
    }
    encoded = json.dumps(
        intent, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"
    path = archive / "recovery-intent.json"
    path.write_bytes(encoded)
    path.chmod(0o400)
    return intent, encoded


def test_pre_flags_recovery_v1_intent_replays_after_partial_move(
    tmp_path: Path,
) -> None:
    first = tmp_path / "worker-codex-pro-01.json"
    second = tmp_path / "worker-codex-pro-02.json"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    first.chmod(0o400)
    second.chmod(0o400)
    archive = tmp_path / "recovered-carrier"
    archive.mkdir(mode=0o700)
    intent, _intent_bytes = _write_pre_flags_recovery_v1_intent(
        archive, (first, second)
    )

    first_target = intent["targets"][0]
    assert isinstance(first_target, dict)
    first.rename(archive / str(first_target["destination_name"]))

    receipt = artifacts.resume_recovery_archive(
        archive, expected_uid=os.getuid()
    )
    assert receipt["outcome"] == "INTERRUPTED_H0_PARTIAL_RECOVERED"
    assert receipt["recovered_targets"] == intent["targets"]
    assert not first.exists() and not second.exists()


def test_completed_pre_flags_recovery_v1_receipt_replays_idempotently(
    tmp_path: Path,
) -> None:
    source = tmp_path / "worker-codex-pro-01.json"
    source.write_bytes(b"first")
    source.chmod(0o400)
    archive = tmp_path / "recovered-carrier"
    archive.mkdir(mode=0o700)
    intent, intent_bytes = _write_pre_flags_recovery_v1_intent(archive, (source,))
    target = intent["targets"][0]
    assert isinstance(target, dict)
    source.rename(archive / str(target["destination_name"]))
    receipt = {
        "schema_version": artifacts.RECOVERY_RECEIPT_SCHEMA,
        "outcome": "INTERRUPTED_H0_PARTIAL_RECOVERED",
        "intent_sha256": hashlib.sha256(intent_bytes).hexdigest(),
        "recovered_target_count": 1,
        "recovered_targets": intent["targets"],
        "service_state": "labels_disabled_unloaded",
        "socket_state": "nodes_absent",
        "credential_state": "not_read_or_changed",
        "continuation": "same_carrier_preparation_resumed",
    }
    receipt_path = archive / "recovery-receipt.json"
    receipt_path.write_bytes(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    receipt_path.chmod(0o400)

    assert artifacts.resume_recovery_archive(
        archive, expected_uid=os.getuid()
    ) == receipt


def test_recovery_v1_digest_preserves_exact_pre_flags_canonical_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "worker-codex-pro-01.json"
    source.write_bytes(b"first")
    source.chmod(0o400)

    assert artifacts._closed_tree_digest(
        source, expected_uid=os.getuid()
    ) == _legacy_recovery_v1_file_tree_digest(source)


def test_recovery_v1_digest_preserves_committed_nested_pre_flags_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "legacy-tree"
    nested = root / "nested"
    root.mkdir(mode=0o700)
    nested.mkdir(mode=0o700)
    payload = nested / "payload"
    payload.write_bytes(b"payload\n")
    root.chmod(0o700)
    nested.chmod(0o700)
    payload.chmod(0o400)
    original_lstat = Path.lstat
    fixed_metadata = {
        root: {"st_uid": 1234, "st_gid": 5678, "st_nlink": 3, "st_flags": 0},
        nested: {"st_uid": 1234, "st_gid": 5678, "st_nlink": 2, "st_flags": 0},
        payload: {"st_uid": 1234, "st_gid": 5678, "st_nlink": 1, "st_flags": 0},
    }

    def fixed_lstat(path: Path) -> os.stat_result | _StatOverlay:
        info = original_lstat(path)
        changes = fixed_metadata.get(path)
        return _StatOverlay(info, **changes) if changes is not None else info

    monkeypatch.setattr(Path, "lstat", fixed_lstat)

    assert artifacts._closed_tree_digest(root, expected_uid=1234) == (
        "1da4f381e08384e9cc388a87d845788a08cfafb12c0f1c76a1218ffb737c3e70"
    )


def test_recovery_v1_digest_keeps_flags_as_fail_closed_non_identity_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "worker-codex-pro-01.json"
    source.write_bytes(b"first")
    source.chmod(0o400)
    original_lstat = Path.lstat

    def flagged_lstat(path: Path) -> os.stat_result | _StatOverlay:
        info = original_lstat(path)
        if path == source:
            return _StatOverlay(info, st_flags=1)
        return info

    monkeypatch.setattr(Path, "lstat", flagged_lstat)
    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="RECOVERY_OBJECT_INVALID"
    ):
        artifacts._closed_tree_digest(source, expected_uid=os.getuid())


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
            "flags": 0,
        },
        {
            "path": "alpha.txt",
            "type": "file",
            "uid": payload_info.st_uid,
            "gid": payload_info.st_gid,
            "mode": "0400",
            "nlink": 1,
            "flags": 0,
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


def test_closed_tree_digest_refuses_nonzero_mocked_fstat_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    payload.chmod(0o400)
    root.chmod(0o700)
    original_fstat = os.fstat

    class FlaggedStat:
        st_flags = 1

        def __init__(self, value: os.stat_result) -> None:
            self._value = value

        def __getattr__(self, name: str) -> object:
            return getattr(self._value, name)

    monkeypatch.setattr(os, "fstat", lambda descriptor: FlaggedStat(original_fstat(descriptor)))
    with pytest.raises(artifacts.CapacityHostArtifactError, match="FLAGS_INVALID"):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


@pytest.mark.parametrize(
    ("drift", "replacement"),
    (
        ("file-type", stat.S_IFDIR | 0o400),
        ("mode", stat.S_IFREG | 0o600),
        ("uid", os.getuid() + 10000),
        ("gid", os.getgid() + 10000),
        ("link-count", 2),
        ("flags", 1),
    ),
)
def test_closed_tree_digest_refuses_complete_post_read_file_state_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
    replacement: int,
) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    payload.chmod(0o400)
    root.chmod(0o700)
    payload_info = payload.stat()
    payload_identity = (payload_info.st_dev, payload_info.st_ino)
    original_fstat = os.fstat
    original_sha256 = artifacts._descriptor_sha256
    read_complete = False

    def track_read(descriptor: int) -> str:
        nonlocal read_complete
        digest = original_sha256(descriptor)
        read_complete = True
        return digest

    def drifted_fstat(descriptor: int) -> os.stat_result | _StatOverlay:
        info = original_fstat(descriptor)
        if read_complete and (info.st_dev, info.st_ino) == payload_identity:
            field = {
                "file-type": "st_mode",
                "mode": "st_mode",
                "uid": "st_uid",
                "gid": "st_gid",
                "link-count": "st_nlink",
                "flags": "st_flags",
            }[drift]
            return _StatOverlay(info, **{field: replacement})
        return info

    monkeypatch.setattr(artifacts, "_descriptor_sha256", track_read)
    monkeypatch.setattr(os, "fstat", drifted_fstat)
    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="CLOSURE_FILE_DRIFT"
    ):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


@pytest.mark.parametrize("security_drift", ("acl", "xattr"))
def test_closed_tree_digest_rechecks_descriptor_security_after_file_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    security_drift: str,
) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    payload.chmod(0o400)
    root.chmod(0o700)
    payload_info = payload.stat()
    payload_identity = (payload_info.st_dev, payload_info.st_ino)
    original_fstat = os.fstat
    original_sha256 = artifacts._descriptor_sha256
    original_xattrs = artifacts._descriptor_extended_attribute_names
    original_acl = artifacts._descriptor_has_extended_acl
    read_complete = False

    def is_payload(descriptor: int) -> bool:
        info = original_fstat(descriptor)
        return (info.st_dev, info.st_ino) == payload_identity

    def track_read(descriptor: int) -> str:
        nonlocal read_complete
        digest = original_sha256(descriptor)
        read_complete = True
        return digest

    def drifted_xattrs(descriptor: int) -> frozenset[bytes]:
        observed = original_xattrs(descriptor)
        if security_drift == "xattr" and read_complete and is_payload(descriptor):
            return observed | frozenset({b"com.mastermind.test"})
        return observed

    def drifted_acl(descriptor: int) -> bool:
        if security_drift == "acl" and read_complete and is_payload(descriptor):
            return True
        return original_acl(descriptor)

    monkeypatch.setattr(artifacts, "_descriptor_sha256", track_read)
    monkeypatch.setattr(
        artifacts, "_descriptor_extended_attribute_names", drifted_xattrs
    )
    monkeypatch.setattr(artifacts, "_descriptor_has_extended_acl", drifted_acl)
    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="CLOSURE_FILE_DRIFT"
    ):
        artifacts.closed_tree_digest(
            root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


@pytest.mark.skipif(
    sys.platform != "darwin" or not hasattr(os, "chflags") or not hasattr(stat, "UF_NODUMP"),
    reason="native harmless BSD user flag requires macOS",
)
def test_closed_tree_digest_refuses_native_harmless_user_flag(tmp_path: Path) -> None:
    root = tmp_path / "closed"
    root.mkdir(mode=0o700)
    payload = root / "payload"
    payload.write_bytes(b"value")
    payload.chmod(0o400)
    root.chmod(0o700)
    os.chflags(payload, stat.UF_NODUMP)
    try:
        with pytest.raises(artifacts.CapacityHostArtifactError, match="FLAGS_INVALID"):
            artifacts.closed_tree_digest(
                root, expected_uid=os.getuid(), expected_gid=os.getgid()
            )
    finally:
        os.chflags(payload, 0)


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
    artifacts._normalize_complete_repository_modes(checkout)

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


def _zip_offsets(payload: bytes) -> tuple[int, int, int]:
    local = payload.index(b"PK\x03\x04")
    central = payload.index(b"PK\x01\x02")
    eocd = payload.rindex(b"PK\x05\x06")
    return local, central, eocd


def _write_noncanonical_v2_zip(
    valid: Path, invalid: Path, mutation: str
) -> None:
    with zipfile.ZipFile(valid) as archive:
        manifest = archive.read("manifest.json")
        pack = archive.read("payload.pack")
    if mutation in {"archive_comment", "member_comment", "extra", "name", "zip64"}:
        with zipfile.ZipFile(invalid, "w", allowZip64=True) as archive:
            if mutation == "archive_comment":
                archive.comment = b"x"
            for index, (name, body) in enumerate(
                (("manifest.json", manifest), ("payload.pack", pack))
            ):
                if mutation == "name" and index == 0:
                    name = "Manifest.json"
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFREG | 0o400) << 16
                info.file_size = len(body)
                if mutation == "member_comment" and index == 0:
                    info.comment = b"x"
                if mutation == "extra" and index == 0:
                    info.extra = b"\x01\x00\x00\x00"
                if mutation == "zip64" and index == 1:
                    with archive.open(info, "w", force_zip64=True) as target:
                        target.write(body)
                else:
                    archive.writestr(info, body)
        return
    raw = bytearray(valid.read_bytes())
    local, central, eocd = _zip_offsets(raw)
    if mutation == "local_version":
        struct.pack_into("<H", raw, local + 4, 10)
    elif mutation == "local_flag":
        struct.pack_into("<H", raw, local + 6, 0x0800)
    elif mutation == "local_crc":
        struct.pack_into("<I", raw, local + 14, 0)
    elif mutation == "local_size":
        struct.pack_into("<I", raw, local + 18, 1)
    elif mutation == "central_version":
        struct.pack_into("<H", raw, central + 4, 20)
    elif mutation == "central_extract_version":
        struct.pack_into("<H", raw, central + 6, 10)
    elif mutation == "central_flag":
        struct.pack_into("<H", raw, central + 8, 0x0800)
    elif mutation == "central_crc":
        struct.pack_into("<I", raw, central + 16, 0)
    elif mutation == "central_disk":
        struct.pack_into("<H", raw, central + 34, 1)
    elif mutation == "central_internal_attributes":
        struct.pack_into("<H", raw, central + 36, 1)
    elif mutation == "eocd_disk":
        struct.pack_into("<H", raw, eocd + 4, 1)
    elif mutation == "eocd_start_disk":
        struct.pack_into("<H", raw, eocd + 6, 1)
    elif mutation == "eocd_count":
        struct.pack_into("<H", raw, eocd + 8, 1)
    elif mutation == "prefix":
        raw = bytearray(b"x") + raw
    elif mutation == "suffix":
        raw.extend(b"x")
    elif mutation in {"encryption", "data_descriptor", "compression"}:
        flag = 0x0001 if mutation == "encryption" else 0x0008
        if mutation == "compression":
            struct.pack_into("<H", raw, local + 8, zipfile.ZIP_DEFLATED)
            struct.pack_into("<H", raw, central + 10, zipfile.ZIP_DEFLATED)
        else:
            struct.pack_into("<H", raw, local + 6, flag)
            struct.pack_into("<H", raw, central + 8, flag)
    else:
        raise AssertionError(f"unknown mutation: {mutation}")
    invalid.write_bytes(raw)


@pytest.mark.parametrize(
    "mutation",
    (
        "local_version",
        "local_flag",
        "local_crc",
        "local_size",
        "central_version",
        "central_extract_version",
        "central_flag",
        "central_crc",
        "central_disk",
        "central_internal_attributes",
        "eocd_disk",
        "eocd_start_disk",
        "eocd_count",
        "name",
        "prefix",
        "suffix",
        "archive_comment",
        "member_comment",
        "extra",
        "encryption",
        "compression",
        "data_descriptor",
        "zip64",
    ),
)
def test_complete_transport_v2_refuses_every_noncanonical_zip_record_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    valid = tmp_path / "canonical.zip"
    artifacts.build_source_transport_v2(source, valid, commit=commit)
    invalid = tmp_path / f"noncanonical-{mutation}.zip"
    _write_noncanonical_v2_zip(valid, invalid, mutation)
    with pytest.raises(
        (artifacts.CapacityHostArtifactError, zipfile.BadZipFile, RuntimeError)
    ):
        artifacts.extract_source_transport_v2(
            invalid,
            tmp_path / f"extract-{mutation}",
            expected_commit=commit,
        )


def test_v2_zip32_effective_boundary_refuses_before_python_writes_zip64(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep the artificial limit above the complete small archive framing so this
    # isolates Python's 1.05 member-size preflight rather than its EOCD offset.
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 10_000)
    safe_payload = tmp_path / "safe.pack"
    safe_payload.write_bytes(b"s" * 9_523)
    safe_output = tmp_path / "safe.zip"
    artifacts._write_transport_v2_archive(safe_output, {}, safe_payload)
    with zipfile.ZipFile(safe_output) as archive:
        assert all(info.extra == b"" for info in archive.infolist())

    unsafe_payload = tmp_path / "unsafe.pack"
    unsafe_payload.write_bytes(b"u" * 9_524)
    unsafe_output = tmp_path / "unsafe.zip"
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="TRANSPORT_V2_ZIP32_LIMIT_EXCEEDED",
    ):
        artifacts._write_transport_v2_archive(unsafe_output, {}, unsafe_payload)
    assert not unsafe_output.exists()


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


def _source_repair_intent_fields(*, filesystem_device: int = 1) -> dict[str, object]:
    return {
        "source_closure_repair_commit": "d" * 40,
        "generation_repair_commit": "d" * 40,
        "expected_uid": 0,
        "expected_gid": 0,
        "filesystem_device": filesystem_device,
        "observed_old_source_tree_sha256": "3" * 64,
        "candidate_transport_sha256": "4" * 64,
        "candidate_transport_manifest_sha256": "5" * 64,
        "candidate_object_count": 17,
        "candidate_object_inventory_sha256": "1" * 64,
        "candidate_source_tree_sha256": "2" * 64,
    }


def test_source_repair_intent_builder_owns_fixed_fields_and_identity() -> None:
    intent = artifacts.build_source_repair_intent(**_source_repair_intent_fields())
    assert contract.validate_source_repair_intent(intent) == intent
    identity = dict(intent)
    intent_id = identity.pop("intent_id")
    assert intent_id == hashlib.sha256(artifacts.canonical_json(identity)).hexdigest()


def test_source_repair_intent_publication_is_canonical_lf_and_idempotent(
    tmp_path: Path,
) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(filesystem_device=tmp_path.stat().st_dev)
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)
    observed = artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    payload = artifacts.canonical_json(intent) + b"\n"
    assert observed == hashlib.sha256(payload).hexdigest()
    assert (archive / "source-repair-intent.json").read_bytes() == payload
    assert artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    ) == observed


def test_source_repair_intent_publication_refuses_prefix_or_changed_same_id(
    tmp_path: Path,
) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(filesystem_device=tmp_path.stat().st_dev)
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)
    candidate = archive / ".source-repair-intent.json.candidate"
    candidate.write_bytes(b"attacker-prefix")
    candidate.chmod(0o400)
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.publish_source_repair_intent(
            archive,
            intent,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )

    candidate.unlink()
    artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    changed = dict(intent)
    changed["candidate_transport_sha256"] = "6" * 64
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.publish_source_repair_intent(
            archive,
            changed,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_source_repair_publication_refuses_device_mismatch(tmp_path: Path) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(
            filesystem_device=tmp_path.stat().st_dev + 1
        )
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_DEVICE_MISMATCH",
    ):
        artifacts.publish_source_repair_intent(
            archive,
            intent,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert list(archive.iterdir()) == []


def test_source_repair_move_refuses_existing_destination_without_fallback(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "source-evidence").write_bytes(b"source\n")
    (destination / "destination-evidence").write_bytes(b"destination\n")

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_DESTINATION_EXISTS",
    ):
        artifacts._move_source_repair_tree(source, destination)
    assert (source / "source-evidence").read_bytes() == b"source\n"
    assert (destination / "destination-evidence").read_bytes() == b"destination\n"


@pytest.mark.parametrize(
    "reason",
    ("SOURCE_REPAIR_DEVICE_MISMATCH", "NO_REPLACE_RENAME_UNAVAILABLE"),
)
def test_source_repair_move_has_no_exdev_or_unavailable_rename_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "evidence").write_bytes(b"preserved\n")

    def refuse_rename(*_arguments: object) -> None:
        raise artifacts.CapacityHostArtifactError(reason)

    monkeypatch.setattr(artifacts, "_rename_exclusive", refuse_rename)
    with pytest.raises(artifacts.CapacityHostArtifactError, match=reason):
        artifacts._move_source_repair_tree(source, destination)
    assert (source / "evidence").read_bytes() == b"preserved\n"
    assert not destination.exists()


def test_source_repair_reconcile_refuses_wrong_gid_extra_member_and_two_intents(
    tmp_path: Path,
) -> None:
    intent = artifacts.build_source_repair_intent(
        **_source_repair_intent_fields(filesystem_device=tmp_path.stat().st_dev)
    )
    archive = tmp_path / f"source-closure-repair-{intent['intent_id']}"
    archive.mkdir(mode=0o700)
    artifacts.publish_source_repair_intent(
        archive,
        intent,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    position = artifacts.reconcile_source_repair(
        archive,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    assert position.intent_id == intent["intent_id"]
    assert position.archived_source is False
    assert position.archived_generation is False
    assert position.receipt_digest is None

    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.reconcile_source_repair(
            archive,
            expected_uid=os.getuid(),
            expected_gid=os.getgid() + 1,
        )
    (archive / "extra").write_bytes(b"unexpected")
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.reconcile_source_repair(
            archive,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    (archive / "extra").unlink()
    (archive / "second-source-repair-intent.json").write_bytes(
        (archive / "source-repair-intent.json").read_bytes()
    )
    with pytest.raises(artifacts.CapacityHostArtifactError):
        artifacts.reconcile_source_repair(
            archive,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def _repair_host_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str, dict[str, object]]:
    source, commit, _ = _complete_repository(tmp_path, monkeypatch)
    monkeypatch.setattr(contract, "PRODUCER_COMMIT", commit)
    transport = tmp_path / "operator-transport.zip"
    manifest = artifacts.build_source_transport_v2(source, transport, commit=commit)
    system_root = tmp_path / "host"
    for relative, mode in (
        ("capacity-sources/macro", 0o755),
        ("capacity-generations", 0o755),
        ("capacity-staging", 0o700),
        ("capacity-archive", 0o700),
        ("locks", 0o700),
    ):
        path = system_root / relative
        path.mkdir(parents=True, mode=mode, exist_ok=True)
        path.chmod(mode)
    lock = system_root / "locks" / "cf2-h0.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)

    old_source = system_root / "capacity-sources" / "macro" / commit
    old_source.mkdir(mode=0o700)
    old_payload = old_source / "promisor-source"
    old_payload.write_bytes(b"old incomplete source remains evidence\n")
    old_payload.chmod(0o444)
    old_source.chmod(0o700)

    old_generation_payloads = {
        "broker-topology.json": b'{"preserved":"topology"}',
        "components.json": b'{"old":"components"}',
        "host-preparation-receipt.json": b'{"old":"receipt"}',
        "rollback-contract.json": b'{"preserved":"rollback"}',
        "rollback-drill-receipt.json": b'{"preserved":"drill"}\n',
        "source-config.json": b'{"old":"source-config"}',
    }
    old_digest = hashlib.sha256(old_generation_payloads["source-config.json"]).hexdigest()
    old_hashes = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in old_generation_payloads.items()
    }
    monkeypatch.setattr(artifacts, "PRIOR_GENERATION_DIGEST", old_digest)
    monkeypatch.setattr(contract, "PRIOR_GENERATION_DIGEST", old_digest)
    monkeypatch.setattr(artifacts, "PRIOR_GENERATION_ARTIFACT_SHA256", old_hashes)
    monkeypatch.setattr(contract, "PRIOR_GENERATION_ARTIFACT_SHA256", old_hashes)
    generation = system_root / "capacity-generations" / old_digest
    generation.mkdir(mode=0o700)
    for name, payload in old_generation_payloads.items():
        path = generation / name
        path.write_bytes(payload)
        path.chmod(0o444)
    generation.chmod(0o700)
    return system_root, transport, commit, manifest


def _scoped_tree_snapshot(root: Path) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        rows.append(
            (
                relative,
                stat.S_IFMT(info.st_mode),
                stat.S_IMODE(info.st_mode),
                info.st_uid,
                info.st_gid,
                info.st_nlink,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
                digest,
            )
        )
    return rows


def _scoped_metadata_observation(
    root: Path,
) -> tuple[dict[str, tuple[object, ...]], dict[str, int]]:
    protected: dict[str, tuple[object, ...]] = {}
    access_times: dict[str, int] = {}
    paths = (root, *sorted(root.rglob("*")))
    for path in paths:
        info = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        link_target = os.readlink(path) if path.is_symlink() else None
        xattrs: tuple[tuple[bytes, str | None], ...]
        extended_acl: bool | None = None
        if not path.is_symlink():
            descriptor = os.open(
                path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
            try:
                extended_acl = artifacts._descriptor_has_extended_acl(descriptor)
                rows: list[tuple[bytes, str | None]] = []
                libc = ctypes.CDLL(None, use_errno=True)
                fgetxattr = libc.fgetxattr
                fgetxattr.argtypes = [
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_void_p,
                    ctypes.c_size_t,
                    ctypes.c_uint32,
                    ctypes.c_int,
                ]
                fgetxattr.restype = ctypes.c_ssize_t
                for name in sorted(
                    artifacts._descriptor_extended_attribute_names(descriptor)
                ):
                    required = fgetxattr(descriptor, name, None, 0, 0, 0)
                    assert required >= 0
                    value = ctypes.create_string_buffer(required)
                    observed = fgetxattr(descriptor, name, value, required, 0, 0)
                    assert observed == required
                    rows.append(
                        (name, hashlib.sha256(value.raw[:observed]).hexdigest())
                    )
                xattrs = tuple(rows)
            finally:
                os.close(descriptor)
        else:
            xattrs = tuple(
                (name, None)
                for name in sorted(artifacts._extended_attribute_names(path))
            )
        protected[relative] = (
            stat.S_IFMT(info.st_mode),
            stat.S_IMODE(info.st_mode),
            info.st_uid,
            info.st_gid,
            info.st_nlink,
            info.st_size,
            info.st_dev,
            info.st_ino,
            getattr(info, "st_flags", 0),
            info.st_mtime_ns,
            info.st_ctime_ns,
            getattr(info, "st_birthtime_ns", None),
            link_target,
            xattrs,
            extended_acl,
        )
        access_times[relative] = info.st_atime_ns
    return protected, access_times


def _scoped_content_observation(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _assert_only_kernel_atime_may_advance(
    before: tuple[dict[str, tuple[object, ...]], dict[str, int]],
    after: tuple[dict[str, tuple[object, ...]], dict[str, int]],
) -> None:
    before_protected, before_atime = before
    after_protected, after_atime = after
    assert after_protected == before_protected
    assert set(after_atime) == set(before_atime)
    assert all(after_atime[name] >= before_atime[name] for name in before_atime)


def _repair_arguments(
    system_root: Path, transport: Path, commit: str
) -> dict[str, object]:
    return {
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


@pytest.mark.parametrize(
    "drift",
    (
        "intermediate-symlink",
        "parent-mode",
        "parent-xattr",
        "parent-acl",
        "parent-flags",
    ),
)
def test_source_repair_parent_graph_refuses_untrusted_intermediate_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    capacity_sources = system_root / "capacity-sources"
    cleanup_xattr: tuple[Path, bytes] | None = None
    cleanup_acl = False
    cleanup_flags = False
    if drift == "intermediate-symlink":
        moved = system_root / "real-capacity-sources"
        capacity_sources.rename(moved)
        capacity_sources.symlink_to(moved, target_is_directory=True)
    elif drift == "parent-mode":
        capacity_sources.chmod(0o777)
    elif drift == "parent-xattr":
        name = b"com.mastermind.test" if sys.platform == "darwin" else b"user.mastermind-test"
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["/usr/bin/xattr", "-w", name.decode(), "unsafe", capacity_sources],
                    check=True,
                    capture_output=True,
                )
            else:
                os.setxattr(capacity_sources, name, b"unsafe", follow_symlinks=False)
        except (AttributeError, OSError, subprocess.CalledProcessError):
            pytest.skip("extended attribute fixture is unavailable")
        cleanup_xattr = (capacity_sources, name)
    elif drift == "parent-acl":
        if sys.platform != "darwin":
            pytest.skip("macOS ACL fixture is unavailable")
        subprocess.run(
            [
                "/bin/chmod",
                "+a",
                f"{pwd.getpwuid(os.getuid()).pw_name} allow read",
                capacity_sources,
            ],
            check=True,
            capture_output=True,
        )
        cleanup_acl = True
    else:
        if sys.platform != "darwin" or not hasattr(os, "chflags"):
            pytest.skip("macOS BSD flags fixture is unavailable")
        os.chflags(capacity_sources, stat.UF_NODUMP)
        cleanup_flags = True
    try:
        with pytest.raises(
            (artifacts.CapacityHostArtifactError, OSError),
            match="SOURCE_REPAIR_(PARENT|ROOT)|Too many levels|Not a directory",
        ):
            artifacts._open_source_repair_parents(
                system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
            )
    finally:
        if cleanup_xattr is not None:
            if sys.platform == "darwin":
                subprocess.run(
                    [
                        "/usr/bin/xattr",
                        "-d",
                        cleanup_xattr[1].decode(),
                        cleanup_xattr[0],
                    ],
                    check=True,
                    capture_output=True,
                )
            else:
                os.removexattr(*cleanup_xattr, follow_symlinks=False)
        if cleanup_acl:
            subprocess.run(["/bin/chmod", "-N", capacity_sources], check=True)
        if cleanup_flags:
            os.chflags(capacity_sources, 0)


def test_source_repair_parent_graph_detects_synchronized_system_root_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    retained = system_root.with_name("retained-host")
    try:
        system_root.rename(retained)
        system_root.mkdir(mode=0o755)
        with pytest.raises(artifacts.CapacityHostArtifactError, match="PARENT_DRIFT"):
            parents.revalidate()
    finally:
        parents.close()


def _ancestor_overlay_changes(drift: str, info: os.stat_result) -> dict[str, int]:
    if drift == "flags":
        return {"st_flags": 1}
    if drift == "uid":
        return {"st_uid": os.getuid() + 10000}
    if drift == "gid":
        return {"st_gid": os.getgid() + 10000}
    if drift == "mode":
        return {"st_mode": stat.S_IFDIR | 0o777}
    if drift == "device":
        return {"st_dev": info.st_dev + 1}
    if drift == "link-count":
        return {"st_nlink": 0}
    return {}


def _overlay_stable_ancestor_flags(
    monkeypatch: pytest.MonkeyPatch,
    ancestor: Path,
    flags: int,
) -> None:
    ancestor_info = ancestor.stat()
    ancestor_identity = (ancestor_info.st_dev, ancestor_info.st_ino)
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == ancestor_identity:
            return _StatOverlay(info, st_flags=flags)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )


@pytest.mark.skipif(
    not hasattr(stat, "UF_NODUMP"), reason="BSD user flag constant is unavailable"
)
def test_source_repair_traversal_ancestor_refuses_stable_user_flag_at_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    _overlay_stable_ancestor_flags(monkeypatch, tmp_path, stat.UF_NODUMP)
    parents: artifacts.SourceRepairParents | None = None
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError,
            match="SOURCE_REPAIR_PARENT_INVALID",
        ):
            parents = artifacts._open_source_repair_parents(
                system_root,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )
    finally:
        if parents is not None:
            parents.close()


@pytest.mark.skipif(
    sys.platform != "darwin", reason="observed platform flags are macOS-specific"
)
@pytest.mark.parametrize(
    "platform_flags",
    (
        pytest.param(
            getattr(stat, "SF_NOUNLINK", 0x00100000),
            id="root-var-folders-library",
        ),
        pytest.param(
            getattr(stat, "SF_RESTRICTED", 0x00080000)
            | getattr(stat, "UF_HIDDEN", 0x00008000),
            id="var",
        ),
        pytest.param(
            getattr(stat, "SF_NOUNLINK", 0x00100000)
            | getattr(stat, "UF_HIDDEN", 0x00008000),
            id="private",
        ),
    ),
)
def test_source_repair_traversal_ancestor_accepts_observed_platform_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform_flags: int,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    _overlay_stable_ancestor_flags(monkeypatch, tmp_path, platform_flags)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    try:
        parents.revalidate()
    finally:
        parents.close()


@pytest.mark.parametrize(
    ("phase", "drift"),
    (
        *(("open", drift) for drift in ("uid", "gid", "mode", "device", "link-count", "acl", "xattr")),
        *(("revalidation", drift) for drift in ("flags", "uid", "gid", "mode", "device", "link-count", "acl", "xattr")),
    ),
)
def test_source_repair_true_traversal_ancestor_obeys_complete_security_law(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    drift: str,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    ancestor_info = tmp_path.stat()
    ancestor_identity = (ancestor_info.st_dev, ancestor_info.st_ino)
    parents: artifacts.SourceRepairParents | None = None
    if phase == "revalidation":
        parents = artifacts._open_source_repair_parents(
            system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
        )
    original_fstat = os.fstat
    original_stat = os.stat
    original_xattrs = artifacts._descriptor_extended_attribute_names
    original_acl = artifacts._descriptor_has_extended_acl

    def is_ancestor(info: os.stat_result) -> bool:
        return (info.st_dev, info.st_ino) == ancestor_identity

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        changes = _ancestor_overlay_changes(drift, info)
        return _StatOverlay(info, **changes) if changes and is_ancestor(info) else info

    def stable_fstat(descriptor: int) -> os.stat_result | _StatOverlay:
        return overlay(original_fstat(descriptor))

    def stable_stat(*args: object, **kwargs: object) -> os.stat_result | _StatOverlay:
        return overlay(original_stat(*args, **kwargs))

    def ancestor_xattrs(descriptor: int) -> frozenset[bytes]:
        observed = original_xattrs(descriptor)
        if drift == "xattr" and is_ancestor(original_fstat(descriptor)):
            return observed | frozenset({b"com.mastermind.test"})
        return observed

    def ancestor_acl(descriptor: int) -> bool:
        if drift == "acl" and is_ancestor(original_fstat(descriptor)):
            return True
        return original_acl(descriptor)

    monkeypatch.setattr(os, "fstat", stable_fstat)
    monkeypatch.setattr(os, "stat", stable_stat)
    monkeypatch.setattr(
        artifacts, "_descriptor_extended_attribute_names", ancestor_xattrs
    )
    monkeypatch.setattr(artifacts, "_descriptor_has_extended_acl", ancestor_acl)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError,
            match="SOURCE_REPAIR_PARENT_(INVALID|DRIFT)",
        ):
            if phase == "open":
                parents = artifacts._open_source_repair_parents(
                    system_root,
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                )
            else:
                assert parents is not None
                parents.revalidate()
    finally:
        if parents is not None:
            parents.close()


def test_source_repair_traversal_ancestor_tolerates_positive_link_count_churn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    ancestor_info = tmp_path.stat()
    ancestor_identity = (ancestor_info.st_dev, ancestor_info.st_ino)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == ancestor_identity:
            return _StatOverlay(info, st_nlink=info.st_nlink + 1)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    try:
        parents.revalidate()
    finally:
        parents.close()


def test_source_repair_fixed_system_root_freezes_exact_link_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    root_info = system_root.stat()
    root_identity = (root_info.st_dev, root_info.st_ino)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == root_identity:
            return _StatOverlay(info, st_nlink=info.st_nlink + 1)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="SOURCE_REPAIR_PARENT_DRIFT"
        ):
            parents.revalidate()
    finally:
        parents.close()


def test_source_repair_fixed_parent_freezes_exact_approved_xattr_name_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    target = parents.generation
    initial = dict(parents.security_xattr_states)[target]
    changed = (
        frozenset()
        if initial
        else frozenset({b"com.apple.provenance"})
    )
    original = artifacts._descriptor_extended_attribute_names

    def observed(descriptor: int) -> frozenset[bytes]:
        return changed if descriptor == target else original(descriptor)

    monkeypatch.setattr(artifacts, "_descriptor_extended_attribute_names", observed)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="SOURCE_REPAIR_PARENT_DRIFT"
        ):
            parents.revalidate()
    finally:
        parents.close()


def _write_inert_release_fixture(
    release: Path,
    *,
    tree_sha: str,
    payload: bytes = b"self-authored release payload\n",
) -> bytes:
    release.mkdir(mode=0o755)
    release.chmod(0o755)
    installed = release / "payload.txt"
    installed.write_bytes(payload)
    installed.chmod(0o444)
    manifest = {
        "schema_version": "mastermind.executive_release_manifest/v1",
        "commit_sha": artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        "tree_sha": tree_sha,
        "entries": [
            {
                "path": "payload.txt",
                "mode": 0o444,
                "uid": os.getuid(),
                "gid": os.getgid(),
                "type": "file",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    manifest_path = release / ".executive-release-manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_path.chmod(0o444)
    return manifest_bytes


def _canonical_e4_manifest_from_git_objects() -> tuple[str, bytes, int]:
    """Derive the installed e4 manifest without importing release code."""

    repository = Path(__file__).resolve().parents[1]
    commit = artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    tree = _git(repository, "rev-parse", f"{commit}^{{tree}}")
    listing = subprocess.run(
        ["git", "-C", str(repository), "ls-tree", "-r", "-t", "-z", commit],
        check=True,
        capture_output=True,
    ).stdout
    objects: list[tuple[str, str, str, str]] = []
    blob_oids: list[str] = []
    for record in listing.split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", 1)
        encoded_mode, encoded_kind, encoded_oid = metadata.split(b" ")
        mode = encoded_mode.decode("ascii")
        kind = encoded_kind.decode("ascii")
        oid = encoded_oid.decode("ascii")
        path = encoded_path.decode("utf-8", "strict")
        objects.append((mode, kind, oid, path))
        if kind == "blob":
            blob_oids.append(oid)

    batch = subprocess.Popen(
        ["git", "-C", str(repository), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert batch.stdin is not None
    assert batch.stdout is not None
    batch.stdin.write("".join(f"{oid}\n" for oid in blob_oids).encode("ascii"))
    batch.stdin.close()
    blob_bytes: dict[str, bytes] = {}
    for oid in blob_oids:
        header = batch.stdout.readline().removesuffix(b"\n").split()
        assert header[:2] == [oid.encode("ascii"), b"blob"]
        size = int(header[2])
        blob_bytes[oid] = batch.stdout.read(size)
        assert batch.stdout.read(1) == b"\n"
    assert batch.wait() == 0

    by_parent: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for mode, kind, oid, path in objects:
        parent, _separator, name = path.rpartition("/")
        by_parent.setdefault(parent, []).append((name, mode, kind, oid, path))

    entries: list[dict[str, object]] = []

    def visit(parent: str) -> None:
        children = by_parent.get(parent, [])
        directories = sorted(
            (row for row in children if row[2] == "tree"),
            key=lambda row: row[0],
        )
        nondirectories = sorted(
            (row for row in children if row[2] != "tree"),
            key=lambda row: row[0],
        )
        for _name, mode, kind, oid, path in (*directories, *nondirectories):
            installed_mode = (
                0o755
                if kind == "tree" or mode in {"100755", "120000"}
                else 0o644
            )
            common: dict[str, object] = {
                "path": path,
                "mode": installed_mode,
                "uid": 0,
                "gid": 0,
            }
            if kind == "tree":
                entries.append({**common, "type": "directory"})
            elif mode == "120000":
                entries.append(
                    {
                        **common,
                        "type": "symlink",
                        "target": blob_bytes[oid].decode("utf-8", "strict"),
                    }
                )
            else:
                payload = blob_bytes[oid]
                entries.append(
                    {
                        **common,
                        "type": "file",
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
        for _name, _mode, _kind, _oid, path in directories:
            visit(path)

    visit("")
    document = {
        "schema_version": "mastermind.executive_release_manifest/v1",
        "commit_sha": commit,
        "tree_sha": tree,
        "entries": entries,
    }
    manifest_bytes = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    return tree, manifest_bytes, len(entries)


def test_trusted_e4_release_manifest_identity_is_derived_from_git_objects() -> None:
    tree, manifest_bytes, entry_count = _canonical_e4_manifest_from_git_objects()
    assert tree == artifacts._TRUSTED_E4_RELEASE_TREE
    assert len(manifest_bytes) == artifacts._TRUSTED_E4_MANIFEST_SIZE
    assert entry_count == artifacts._TRUSTED_E4_MANIFEST_ENTRY_COUNT
    assert (
        hashlib.sha256(manifest_bytes).hexdigest()
        == artifacts._TRUSTED_E4_MANIFEST_SHA256
    )


def test_inert_release_refuses_self_authored_payload_and_matching_manifest_under_e4_basename(
    tmp_path: Path,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    _write_inert_release_fixture(
        release,
        tree_sha="ee1b95af3341a49151890cec1a6a31997f632aec",
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_inert_release_refuses_valid_manifest_shape_with_wrong_trusted_e4_tree(
    tmp_path: Path,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    _write_inert_release_fixture(release, tree_sha="f" * 40)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_inert_release_revalidates_basename_relation_after_root_is_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(release, tree_sha="a" * 40)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40, raising=False)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes), raising=False
    )
    monkeypatch.setattr(
        artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1, raising=False
    )
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o755)
    replacement.chmod(0o755)
    displaced = tmp_path / "displaced-release"
    manifest_inode = (release / ".executive-release-manifest.json").stat().st_ino
    root_before = release.stat()
    root_inode = root_before.st_ino
    original_read = artifacts._read_descriptor
    original_fstat = os.fstat
    swapped = False

    def swap_release_basename(descriptor: int, maximum_bytes: int) -> bytes:
        nonlocal swapped
        if not swapped and os.fstat(descriptor).st_ino == manifest_inode:
            release.rename(displaced)
            replacement.rename(release)
            swapped = True
        return original_read(descriptor, maximum_bytes)

    monkeypatch.setattr(artifacts, "_read_descriptor", swap_release_basename)
    monkeypatch.setattr(
        os,
        "fstat",
        lambda descriptor: (
            _StatOverlay(
                original_fstat(descriptor),
                st_ctime_ns=root_before.st_ctime_ns,
            )
            if swapped and original_fstat(descriptor).st_ino == root_inode
            else original_fstat(descriptor)
        ),
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert swapped


def test_inert_release_refuses_unrelated_retained_view_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_parent = tmp_path / "expected-parent"
    injected_parent = tmp_path / "injected-parent"
    expected_parent.mkdir(mode=0o755)
    injected_parent.mkdir(mode=0o755)
    expected_release = expected_parent / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    injected_release = injected_parent / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(expected_release, tree_sha="a" * 40)
    _write_inert_release_fixture(injected_release, tree_sha="a" * 40)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1)
    expected_parent_descriptor = os.open(
        expected_parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    injected_view = artifacts._RepositoryView(
        injected_release,
        allow_symlinks=True,
    )
    try:
        with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
            artifacts._verify_inert_release_manifest(
                expected_release,
                expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                parent_descriptor=expected_parent_descriptor,
                retained_view=injected_view,
            )
    finally:
        injected_view.close()
        os.close(expected_parent_descriptor)


def test_retained_semantic_read_refuses_approved_xattr_name_set_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "xattr-state"
    root.mkdir(mode=0o755)
    evidence = root / "evidence.json"
    evidence.write_bytes(b"{}\n")
    evidence.chmod(0o444)
    view = artifacts._RepositoryView(root)
    target = view.descriptors["evidence.json"]
    initial_names = view.xattr_states["evidence.json"]
    drifted_names = (
        frozenset()
        if initial_names
        else frozenset({b"com.apple.provenance"})
    )
    original_names = artifacts._descriptor_extended_attribute_names
    original_read = artifacts._read_descriptor
    drifted = False

    def observed_names(descriptor: int) -> frozenset[bytes]:
        if drifted and descriptor == target:
            return drifted_names
        return original_names(descriptor)

    def drift_after_read(descriptor: int, maximum_bytes: int) -> bytes:
        nonlocal drifted
        payload = original_read(descriptor, maximum_bytes)
        if descriptor == target:
            drifted = True
        return payload

    monkeypatch.setattr(artifacts, "_descriptor_extended_attribute_names", observed_names)
    monkeypatch.setattr(artifacts, "_read_descriptor", drift_after_read)
    try:
        with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_VIEW_DRIFT"):
            view.read_bytes("evidence.json", maximum_bytes=1024)
    finally:
        view.close()


def test_retained_parent_proves_optional_absence_without_path_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "optional-parent"
    parent.mkdir(mode=0o755)
    view = artifacts._RepositoryView(parent, recursive=False)

    def forbid_lexists(*args: object, **kwargs: object) -> bool:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(artifacts, "_path_lexists", forbid_lexists)
    try:
        assert view.is_absent("optional-evidence.json")
        view.revalidate()
    finally:
        view.close()


def test_absolute_view_refuses_forbidden_stable_ancestor_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "ancestor-policy.json"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    ancestor = tmp_path.parent.stat()
    ancestor_identity = (ancestor.st_dev, ancestor.st_ino)
    original_fstat = os.fstat
    original_stat = os.stat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        if (info.st_dev, info.st_ino) == ancestor_identity:
            return _StatOverlay(info, st_flags=1)
        return info

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os,
        "stat",
        lambda *args, **kwargs: overlay(original_stat(*args, **kwargs)),
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(evidence)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed root aliases")
@pytest.mark.parametrize("alias", (Path("/var"), Path("/tmp")))
def test_absolute_view_authenticates_fixed_macos_root_alias_component(
    alias: Path,
) -> None:
    if alias == Path("/tmp"):
        with tempfile.TemporaryDirectory(prefix="mmx-retained-", dir="/tmp") as root:
            os.chown(root, os.getuid(), os.getgid())
            evidence = Path(root) / "evidence.json"
            evidence.write_bytes(b"evidence\n")
            evidence.chmod(0o444)
            view = artifacts._RepositoryView(evidence)
            try:
                assert view.read_bytes(".", maximum_bytes=1024) == b"evidence\n"
            finally:
                view.close()
    else:
        view = artifacts._RepositoryView(alias, recursive=False)
        try:
            assert stat.S_ISDIR(os.fstat(view.root_descriptor).st_mode)
            view.revalidate()
        finally:
            view.close()


@pytest.mark.parametrize(
    "semantic_role",
    ("runtime", "generation", "topology", "rollback", "legacy"),
)
def test_preserved_semantic_reads_use_retained_descriptors_during_restored_path_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    semantic_role: str,
) -> None:
    root = tmp_path / semantic_role
    root.mkdir(mode=0o755)
    trusted = root / "evidence.json"
    trusted.write_bytes(b'{"trusted":true}\n')
    trusted.chmod(0o444)
    replacement = tmp_path / f"{semantic_role}-replacement"
    replacement.mkdir(mode=0o755)
    attacker = replacement / "evidence.json"
    attacker.write_bytes(b'{"trusted":false}\n')
    attacker.chmod(0o444)
    displaced = tmp_path / f"{semantic_role}-displaced"
    view = artifacts._RepositoryView(root)
    original_read = artifacts._read_descriptor
    target_descriptor = view.descriptors["evidence.json"]
    root_before = root.stat()
    root_inode = root_before.st_ino
    swapped = False
    original_fstat = os.fstat
    original_stat = os.stat

    def restored_swap(descriptor: int, maximum_bytes: int) -> bytes:
        nonlocal swapped
        if descriptor == target_descriptor and not swapped:
            root.rename(displaced)
            replacement.rename(root)
            try:
                payload = original_read(descriptor, maximum_bytes)
            finally:
                root.rename(replacement)
                displaced.rename(root)
            swapped = True
            return payload
        return original_read(descriptor, maximum_bytes)

    def forbid_pathname_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(artifacts, "_read_descriptor", restored_swap)
    monkeypatch.setattr(Path, "read_bytes", forbid_pathname_read)
    monkeypatch.setattr(
        os,
        "fstat",
        lambda descriptor: (
            _StatOverlay(
                original_fstat(descriptor),
                st_ctime_ns=root_before.st_ctime_ns,
            )
            if (original_fstat(descriptor).st_dev, original_fstat(descriptor).st_ino)
            == (root_before.st_dev, root_inode)
            else original_fstat(descriptor)
        ),
    )
    monkeypatch.setattr(
        os,
        "stat",
        lambda *args, **kwargs: (
            _StatOverlay(
                original_stat(*args, **kwargs),
                st_ctime_ns=root_before.st_ctime_ns,
            )
            if (
                original_stat(*args, **kwargs).st_dev,
                original_stat(*args, **kwargs).st_ino,
            )
            == (root_before.st_dev, root_inode)
            else original_stat(*args, **kwargs)
        ),
    )
    try:
        assert view.read_bytes("evidence.json", maximum_bytes=1024) == (
            b'{"trusted":true}\n'
        )
        assert swapped
        view.revalidate()
    finally:
        view.close()


def test_absolute_evidence_view_opens_every_component_from_retained_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "absolute-evidence.json"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    original_open = os.open
    absolute_opens: list[str] = []

    def observe_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        encoded = os.fspath(path)
        if "dir_fd" not in kwargs and os.path.isabs(encoded):
            absolute_opens.append(encoded)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observe_open)
    view = artifacts._RepositoryView(evidence)
    try:
        assert view.read_bytes(".", maximum_bytes=1024) == b"evidence\n"
    finally:
        view.close()
    assert absolute_opens == ["/"]


def test_repository_view_full_revalidation_walks_retained_parent_capability_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "linear-revalidation"
    for branch_index in range(3):
        nested = root / f"branch-{branch_index}" / "middle" / "leaf"
        nested.mkdir(parents=True)
        for file_index in range(3):
            evidence = nested / f"evidence-{file_index}.json"
            evidence.write_bytes(f"{branch_index}:{file_index}\n".encode("ascii"))
            evidence.chmod(0o444)
    view = artifacts._RepositoryView(root)
    parent_checks = 0
    object_xattr_checks = {descriptor: 0 for descriptor in view.descriptors.values()}
    original_parent = artifacts._RepositoryView._revalidate_parent_capability
    original_xattrs = artifacts._descriptor_extended_attribute_names

    def observed_parent_capability(received: artifacts._RepositoryView) -> None:
        nonlocal parent_checks
        parent_checks += 1
        original_parent(received)

    def observed_xattrs(descriptor: int) -> frozenset[bytes]:
        if descriptor in object_xattr_checks:
            object_xattr_checks[descriptor] += 1
        return original_xattrs(descriptor)

    monkeypatch.setattr(
        artifacts._RepositoryView,
        "_revalidate_parent_capability",
        observed_parent_capability,
    )
    monkeypatch.setattr(
        artifacts,
        "_descriptor_extended_attribute_names",
        observed_xattrs,
    )
    try:
        view.revalidate()
        assert parent_checks == 2
        assert set(object_xattr_checks.values()) == {1}
    finally:
        view.close()


def test_repository_view_closes_guard_descriptor_when_initial_guard_audit_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    opened_root: list[int] = []
    closed_root: list[int] = []
    original_open = os.open
    original_close = os.close

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(path, flags, *args, **kwargs)
        if os.fspath(path) == "/" and "dir_fd" not in kwargs:
            opened_root.append(descriptor)
        return descriptor

    def observed_close(descriptor: int) -> None:
        if descriptor in opened_root:
            closed_root.append(descriptor)
        original_close(descriptor)

    def refuse_guard(*args: object, **kwargs: object) -> None:
        raise artifacts.CapacityHostArtifactError("SOURCE_METADATA_INVALID")

    monkeypatch.setattr(os, "open", observed_open)
    monkeypatch.setattr(os, "close", observed_close)
    monkeypatch.setattr(artifacts, "_require_source_repair_ancestor", refuse_guard)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(evidence)
    assert opened_root
    assert closed_root == opened_root


def test_preserved_fd_budget_uplifts_soft_limit_in_subprocess() -> None:
    script = """
import json, resource, tempfile
from pathlib import Path
from ops.executive_os import capacity_host_artifacts as a
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
if hard < a._PRESERVED_H0_REQUIRED_NOFILE:
    raise SystemExit(77)
resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
observed = a._ensure_preserved_h0_fd_budget()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary) / 'exact-scale'
    root.mkdir(mode=0o755)
    for index in range(a._TRUSTED_E4_MANIFEST_ENTRY_COUNT):
        child = root / f'evidence-{index:04d}'
        child.write_bytes(b'evidence\\n')
        child.chmod(0o444)
    view = a._RepositoryView(root)
    try:
        count = len(view.descriptors)
        peak = len([name for name in __import__('os').listdir('/dev/fd') if name.isdecimal()])
        view.revalidate()
    finally:
        view.close()
print(json.dumps({'observed': observed, 'actual': resource.getrlimit(resource.RLIMIT_NOFILE)[0], 'count': count, 'peak': peak}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if completed.returncode == 77:
        pytest.skip("host hard RLIMIT_NOFILE is below the reviewed H0 bound")
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["observed"] >= artifacts._PRESERVED_H0_REQUIRED_NOFILE
    assert observed["actual"] >= artifacts._PRESERVED_H0_REQUIRED_NOFILE
    assert observed["count"] == artifacts._TRUSTED_E4_MANIFEST_ENTRY_COUNT + 1
    assert observed["peak"] >= observed["count"]


def test_preserved_fd_budget_refuses_low_hard_limit_before_graph_in_subprocess() -> None:
    script = """
import resource
from ops.executive_os import capacity_host_artifacts as a
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
limit = min(1024, hard)
resource.setrlimit(resource.RLIMIT_NOFILE, (limit, limit))
try:
    a._ensure_preserved_h0_fd_budget()
except a.CapacityHostArtifactError as exc:
    print(str(exc))
    raise SystemExit(0)
raise SystemExit(1)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "SOURCE_REPAIR_FD_LIMIT_INVALID" in completed.stdout


def test_preserved_fd_budget_refuses_setrlimit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource,
        "getrlimit",
        lambda limit: (256, artifacts._PRESERVED_H0_REQUIRED_NOFILE * 2),
    )

    def refused(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EPERM, "injected")

    monkeypatch.setattr(resource, "setrlimit", refused)
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FD_LIMIT_INVALID",
    ):
        artifacts._ensure_preserved_h0_fd_budget()


@pytest.mark.parametrize(
    "component",
    ("", ".", "..", "slash/name", "nul\x00name"),
)
def test_absolute_component_validation_refuses_before_open(
    monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    opened = False

    def forbidden_open(*args: object, **kwargs: object) -> int:
        nonlocal opened
        opened = True
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(os, "open", forbidden_open)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._validate_absolute_components(("private", component, "evidence"))
    assert not opened


@pytest.mark.parametrize("failure_stage", ("fstat", "xattrs", "readlink", "acl"))
def test_native_alias_descriptor_is_owned_before_every_audit_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    before_fds = _open_fd_inventory()
    evidence = tmp_path / "evidence"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    alias_fd: int | None = None
    closed: list[int] = []
    original_open_alias = artifacts._open_release_symlink
    original_fstat = os.fstat
    original_xattrs = artifacts._descriptor_extended_attribute_names
    original_readlink = os.readlink
    original_acl = artifacts._descriptor_has_extended_acl
    original_close = os.close

    def opened_alias(parent: int, name: str) -> int:
        nonlocal alias_fd
        alias_fd = original_open_alias(parent, name)
        return alias_fd

    def refuse_fstat(fd: int) -> os.stat_result:
        if failure_stage == "fstat" and fd == alias_fd:
            raise OSError(errno.EIO, "injected")
        return original_fstat(fd)

    def refuse_xattrs(fd: int) -> frozenset[bytes]:
        if failure_stage == "xattrs" and fd == alias_fd:
            raise OSError(errno.EIO, "injected")
        return original_xattrs(fd)

    def refuse_readlink(*args: object, **kwargs: object) -> str:
        if failure_stage == "readlink":
            raise OSError(errno.EIO, "injected")
        return original_readlink(*args, **kwargs)

    def refuse_acl(fd: int) -> bool:
        if failure_stage == "acl" and fd == alias_fd:
            raise OSError(errno.EIO, "injected")
        return original_acl(fd)

    def observe_close(fd: int) -> None:
        if fd == alias_fd:
            closed.append(fd)
        original_close(fd)

    monkeypatch.setattr(artifacts, "_open_release_symlink", opened_alias)
    monkeypatch.setattr(os, "fstat", refuse_fstat)
    monkeypatch.setattr(artifacts, "_descriptor_extended_attribute_names", refuse_xattrs)
    monkeypatch.setattr(os, "readlink", refuse_readlink)
    monkeypatch.setattr(artifacts, "_descriptor_has_extended_acl", refuse_acl)
    monkeypatch.setattr(os, "close", observe_close)
    with pytest.raises((artifacts.CapacityHostArtifactError, OSError)):
        artifacts._RepositoryView(Path("/var"), recursive=False)
    assert alias_fd is not None
    assert closed == [alias_fd]
    assert _open_fd_inventory() == before_fds


@pytest.mark.parametrize("mode,links", ((0o666, 1), (0o444, 2)))
def test_repository_view_rejects_stably_unsafe_regular_file_before_snapshot(
    tmp_path: Path,
    mode: int,
    links: int,
) -> None:
    root = tmp_path / "unsafe"
    root.mkdir(mode=0o755)
    evidence = root / "evidence"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(mode)
    if links == 2:
        os.link(evidence, root / "second-link")
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(root)


def test_generation_parent_capability_is_bound_to_exact_lifecycle_position(
    tmp_path: Path,
) -> None:
    generation_parent = tmp_path / "capacity-generations"
    archive = tmp_path / "archive"
    generation_parent.mkdir()
    archive.mkdir()
    visible = generation_parent / artifacts.PRIOR_GENERATION_DIGEST
    archived = archive / artifacts._ARCHIVED_GENERATION_NAME
    generation_fd = os.open(generation_parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    archive_fd = os.open(archive, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    parents = artifacts.SourceRepairParents(
        source_path=tmp_path,
        source=os.dup(generation_fd),
        generation_path=generation_parent,
        generation=generation_fd,
        staging_path=tmp_path,
        staging=os.dup(generation_fd),
        archive_path=tmp_path,
        archive=os.dup(generation_fd),
        device=tmp_path.stat().st_dev,
        intent_archive_path=archive,
        intent_archive=archive_fd,
    )
    try:
        assert artifacts._retained_generation_parent(parents, visible) == generation_fd
        assert artifacts._retained_generation_parent(parents, archived) == archive_fd
        with pytest.raises(artifacts.CapacityHostArtifactError, match="PARENT_INVALID"):
            artifacts._retained_generation_parent(parents, archive / artifacts.PRIOR_GENERATION_DIGEST)
        parents.intent_archive = None
        assert artifacts._retained_generation_parent(parents, visible) == generation_fd
        with pytest.raises(artifacts.CapacityHostArtifactError, match="PARENT_INVALID"):
            artifacts._retained_generation_parent(parents, archived)
    finally:
        if parents.intent_archive is None:
            parents.intent_archive = archive_fd
        parents.close()


def test_retained_prior_generation_authenticates_fixed_inventory_and_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / artifacts.PRIOR_GENERATION_DIGEST
    root.mkdir(mode=0o755)
    payloads = {name: f"{name}\n".encode() for name in artifacts.PRIOR_GENERATION_ARTIFACT_SHA256}
    for name, payload in payloads.items():
        path = root / name
        path.write_bytes(payload)
        path.chmod(0o444)
    root.chmod(0o555)
    monkeypatch.setattr(
        artifacts,
        "PRIOR_GENERATION_ARTIFACT_SHA256",
        {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()},
    )
    view = artifacts._RepositoryView(root)
    try:
        artifacts._verify_retained_prior_generation(
            view,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
            expected_device=root.stat().st_dev,
        )
    finally:
        view.close()
    root.chmod(0o755)
    extra = root / "extra"
    extra.write_bytes(b"extra")
    extra.chmod(0o444)
    root.chmod(0o555)
    invalid_view = artifacts._RepositoryView(root)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="PRIOR_GENERATION_INVALID"
        ):
            artifacts._verify_retained_prior_generation(
                invalid_view,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                expected_device=root.stat().st_dev,
            )
    finally:
        invalid_view.close()


def test_retained_prior_generation_swap_refuses_before_external_topology_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_root, _transport, _commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    generation = (
        system_root / "capacity-generations" / artifacts.PRIOR_GENERATION_DIGEST
    )
    artifacts._validate_prior_generation(
        generation,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    topology = generation / "broker-topology.json"
    topology.chmod(0o600)
    topology.write_bytes(
        b'{"brokers":[{"config_path":"/tmp/untrusted-topology-open"}]}'
    )
    topology.chmod(0o444)
    generation.chmod(0o555)
    runtime_parent = system_root / "capacity-runtimes"
    runtime = runtime_parent / "cf1-pyyaml-6.0.3-cp312-arm64"
    runtime.mkdir(parents=True, mode=0o755)
    runtime.chmod(0o555)
    runtime_parent.chmod(0o755)
    parents = artifacts._open_source_repair_parents(
        system_root, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    opened_external = False
    original_init = artifacts._RepositoryView.__init__

    def observed_init(
        received: artifacts._RepositoryView,
        source_root: Path,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal opened_external
        if source_root == Path("/tmp/untrusted-topology-open"):
            opened_external = True
        original_init(received, source_root, *args, **kwargs)

    monkeypatch.setattr(artifacts._RepositoryView, "__init__", observed_init)
    _overlay_fixture_identity_as_root(monkeypatch, device=parents.device)
    try:
        with pytest.raises(
            artifacts.CapacityHostArtifactError, match="PRIOR_GENERATION_INVALID"
        ):
            artifacts._verify_preserved_h0_invariants(
                system_root,
                generation,
                test_adapter=False,
                parents=parents,
            )
        assert not opened_external
    finally:
        parents.close()


@pytest.mark.parametrize("field", ("st_uid", "st_gid", "st_dev"))
def test_role_policy_rejects_wrong_identity_before_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    root = tmp_path / "role-policy"
    root.mkdir(mode=0o755)
    evidence = root / "evidence"
    evidence.write_bytes(b"evidence\n")
    evidence.chmod(0o444)
    target = evidence.stat()
    identity = (target.st_dev, target.st_ino)
    original_fstat = os.fstat

    def overlaid_fstat(descriptor: int) -> os.stat_result | _StatOverlay:
        info = original_fstat(descriptor)
        if (info.st_dev, info.st_ino) == identity:
            return _StatOverlay(info, **{field: getattr(info, field) + 1})
        return info

    monkeypatch.setattr(os, "fstat", overlaid_fstat)
    policy = artifacts._RepositorySecurityPolicy(
        role="test-evidence",
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        expected_device=root.stat().st_dev,
        directory_modes=frozenset({0o755}),
        file_modes=frozenset({0o444}),
    )
    with pytest.raises(artifacts.CapacityHostArtifactError, match="SOURCE_METADATA_INVALID"):
        artifacts._RepositoryView(root, security_policy=policy)


def test_bad_release_manifest_refuses_before_any_payload_child_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    _write_inert_release_fixture(release, tree_sha="a" * 40)
    giant = release / "giant-untrusted-child"
    giant.write_bytes(b"x" * 1024)
    giant.chmod(0o444)
    opened: list[str] = []
    original_open = os.open

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(os.fspath(path))
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observed_open)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert "giant-untrusted-child" not in opened
    assert "ops" not in opened


def test_authenticated_release_inventory_refuses_unexpected_child_without_opening_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(release, tree_sha="a" * 40)
    unexpected = release / "unexpected-giant"
    unexpected.write_bytes(b"x" * 1024)
    unexpected.chmod(0o444)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1)
    opened: list[str] = []
    original_open = os.open

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(os.fspath(path))
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observed_open)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert "unexpected-giant" not in opened
    assert "payload.txt" not in opened


def test_release_metadata_mismatch_refuses_before_payload_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    manifest_bytes = _write_inert_release_fixture(release, tree_sha="a" * 40)
    (release / "payload.txt").chmod(0o400)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "a" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", 1)

    def forbidden_hash(*args: object, **kwargs: object) -> str:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(artifacts, "_descriptor_sha256", forbidden_hash)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=artifacts.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def test_real_mode_visible_prior_generation_receives_retained_generation_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    _overlay_fixture_identity_as_root(monkeypatch, device=system_root.stat().st_dev)

    class Observed(Exception):
        pass

    def observed(
        received_root: Path,
        generation: Path,
        *,
        test_adapter: bool,
        parents: artifacts.SourceRepairParents | None = None,
    ) -> None:
        assert received_root == system_root
        assert not test_adapter
        assert parents is not None
        assert parents.intent_archive is None
        assert generation == parents.generation_path / artifacts.PRIOR_GENERATION_DIGEST
        assert artifacts._retained_generation_parent(parents, generation) == parents.generation
        raise Observed

    monkeypatch.setattr(artifacts, "_verify_preserved_h0_invariants", observed)
    arguments = _repair_arguments(system_root, transport, commit)
    arguments["test_adapter"] = False
    with pytest.raises(Observed):
        artifacts.run_source_repair_host(**arguments)


@pytest.mark.parametrize("mode", ("repair", "verify-only"))
def test_real_mode_archived_and_verify_only_receive_same_retained_archive_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    archive = next((system_root / "capacity-archive").iterdir())
    intent = json.loads((archive / artifacts._SOURCE_REPAIR_INTENT_NAME).read_bytes())
    receipt = json.loads((archive / artifacts._SOURCE_REPAIR_RECEIPT_NAME).read_bytes())
    installed_manifest, installed_evidence = artifacts._verify_installed_repair_source(
        system_root / "capacity-sources" / "macro" / commit,
        commit,
    )
    _overlay_fixture_identity_as_root(monkeypatch, device=system_root.stat().st_dev)

    def preserved_tree_digest(path: Path, **kwargs: object) -> str:
        if path.name == artifacts._ARCHIVED_SOURCE_NAME:
            return intent["observed_old_source_tree_sha256"]
        if path.name == artifacts._ARCHIVED_GENERATION_NAME:
            return receipt["archived_generation_tree_sha256"]
        return "0" * 64

    monkeypatch.setattr(artifacts, "closed_tree_digest", preserved_tree_digest)
    monkeypatch.setattr(
        artifacts,
        "_validate_prior_generation",
        lambda *args, **kwargs: receipt["archived_generation_tree_sha256"],
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_installed_repair_source",
        lambda *args, **kwargs: (installed_manifest, installed_evidence),
    )

    class Observed(Exception):
        pass

    def observed(
        received_root: Path,
        generation: Path,
        *,
        test_adapter: bool,
        parents: artifacts.SourceRepairParents | None = None,
    ) -> None:
        assert received_root == system_root
        assert not test_adapter
        assert parents is not None
        assert parents.intent_archive is not None
        assert generation == parents.intent_archive_path / artifacts._ARCHIVED_GENERATION_NAME
        assert (
            artifacts._retained_generation_parent(parents, generation)
            == parents.intent_archive
        )
        raise Observed

    monkeypatch.setattr(artifacts, "_verify_preserved_h0_invariants", observed)
    with pytest.raises((Observed, artifacts.SourceRepairIncomplete)) as caught:
        artifacts.run_source_repair_host(
            mode=mode,
            system_root=system_root,
            lock_file=system_root / "locks" / "cf2-h0.lock",
            expected_repair_commit="d" * 40,
            expected_source_commit=commit,
            transport=transport if mode == "repair" else None,
            transport_sha256=(
                hashlib.sha256(transport.read_bytes()).hexdigest()
                if mode == "repair"
                else None
            ),
            operator_uid=os.getuid() if mode == "repair" else None,
            test_adapter=False,
        )
    if isinstance(caught.value, artifacts.SourceRepairIncomplete):
        assert isinstance(caught.value.__cause__, Observed)


class _FakePreservedView:
    def __init__(
        self,
        payloads: dict[str, bytes] | None = None,
        *,
        absent: frozenset[str] = frozenset(),
    ) -> None:
        self.payloads = payloads or {}
        self.absent = absent

    def read_bytes(self, relative: str, *, maximum_bytes: int) -> bytes:
        payload = self.payloads[relative]
        assert len(payload) <= maximum_bytes
        return payload

    def sha256(self, relative: str) -> str:
        return hashlib.sha256(self.payloads[relative]).hexdigest()

    def is_absent(self, name: str) -> bool:
        return name in self.absent

    def revalidate(self) -> None:
        return None


def test_preserved_verifier_body_uses_only_supplied_retained_semantic_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root = tmp_path / "system"
    generation = system_root / "capacity-generations" / ("a" * 64)
    archive = system_root / "capacity-archive" / "rollback-drill-fixture"
    labels = (
        "com.mastermind.executive.control",
        "com.mastermind.executive.worker.codex",
        "com.mastermind.executive.worker.codex-pro-01",
        "com.mastermind.executive.worker.codex-pro-02",
        "com.mastermind.executive.worker.codex-pro-03",
    )
    topology_payloads: dict[Path, bytes] = {}
    brokers: list[dict[str, object]] = []
    artifacts_rows: list[dict[str, str]] = []
    rollback_payloads: dict[str, bytes] = {}
    for index in range(9):
        path = tmp_path / f"topology-{index}.json"
        payload = f"topology-{index}\n".encode("ascii")
        topology_payloads[path] = payload
    for broker_index in range(3):
        offset = broker_index * 3
        brokers.append(
            {
                "config_path": str(tuple(topology_payloads)[offset]),
                "config_sha256": hashlib.sha256(
                    topology_payloads[tuple(topology_payloads)[offset]]
                ).hexdigest(),
                "attestation_path": str(tuple(topology_payloads)[offset + 1]),
                "attestation_sha256": hashlib.sha256(
                    topology_payloads[tuple(topology_payloads)[offset + 1]]
                ).hexdigest(),
                "plist_path": str(tuple(topology_payloads)[offset + 2]),
                "plist_sha256": hashlib.sha256(
                    topology_payloads[tuple(topology_payloads)[offset + 2]]
                ).hexdigest(),
            }
        )
    for index in range(9):
        name = f"artifact-{index}.json"
        payload = f"rollback-{index}\n".encode("ascii")
        rollback_payloads[name] = payload
        artifacts_rows.append(
            {"name": name, "sha256": hashlib.sha256(payload).hexdigest()}
        )
    legacy_paths = (
        system_root / "config" / "control.json",
        system_root / "config" / "worker-codex.json",
        Path("/Library/LaunchDaemons/com.mastermind.executive.control.plist"),
        Path("/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist"),
    )
    legacy_lines = [f"{path}=absent\n" for path in legacy_paths]
    legacy_lines.extend(
        f"{label}:disabled=true:loaded=false\n" for label in labels[:2]
    )
    topology = {
        "brokers": brokers,
        "legacy_phase1c_state_digest": hashlib.sha256(
            "".join(legacy_lines).encode("utf-8")
        ).hexdigest(),
    }
    drill = {
        "outcome": "SHRINK_ONLY_ROLLBACK_PASS",
        "moved_artifact_count": 9,
        "artifacts": artifacts_rows,
        "archive_root": str(archive),
    }
    drill_bytes = json.dumps(drill).encode("utf-8")
    rollback_payloads["rollback-receipt.json"] = drill_bytes
    generation_view = _FakePreservedView(
        {
            "broker-topology.json": json.dumps(topology).encode("utf-8"),
            "rollback-drill-receipt.json": drill_bytes,
        }
    )
    topology_views = {
        path: _FakePreservedView({".": payload})
        for path, payload in topology_payloads.items()
    }
    views = artifacts._PreservedH0Views(
        runtime=_FakePreservedView(),
        generation=generation_view,
        telemetry=_FakePreservedView(),
        release=_FakePreservedView(),
        rollback_archive=_FakePreservedView(rollback_payloads),
        topology=topology_views,
        legacy={path: None for path in legacy_paths},
        socket_parent=_FakePreservedView(absent=frozenset({"mastermind-executive"})),
        socket_directory=None,
    )
    observed_helpers: list[str] = []
    monkeypatch.setattr(
        artifacts,
        "_verify_runtime_view",
        lambda view: observed_helpers.append("runtime"),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_telemetry_view",
        lambda view: observed_helpers.append("telemetry"),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_preserved_service_principal_state",
        lambda received_labels: observed_helpers.append("services"),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts,
        "_verify_inert_release_manifest",
        lambda *args, **kwargs: observed_helpers.append("release") or {},
    )

    def forbidden_path_reopen(*args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(Path, "read_bytes", forbidden_path_reopen)
    monkeypatch.setattr(Path, "rglob", forbidden_path_reopen)
    monkeypatch.setattr(Path, "lstat", forbidden_path_reopen)
    monkeypatch.setattr(artifacts, "sha256_file", forbidden_path_reopen)
    monkeypatch.setattr(artifacts, "_path_lexists", forbidden_path_reopen)
    artifacts._verify_preserved_h0_invariants_body(
        system_root,
        generation,
        test_adapter=False,
        retained_views=views,
    )
    assert observed_helpers == ["runtime", "telemetry", "release", "services"]


def test_inert_release_manifest_verifier_never_executes_installed_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = tmp_path / contract.PRESERVED_TOPOLOGY_RELEASE_COMMIT
    script = release / "ops" / "executive_os" / "release_manifest.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(b"# reviewed release verifier placeholder\n")
    script.chmod(0o444)
    for directory in (release, release / "ops", script.parent):
        directory.chmod(0o755)
    original = script.read_bytes()
    entries = [
        {
            "path": "ops",
            "mode": 0o755,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "type": "directory",
        },
        {
            "path": "ops/executive_os",
            "mode": 0o755,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "type": "directory",
        },
        {
            "path": "ops/executive_os/release_manifest.py",
            "mode": 0o444,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "type": "file",
            "size": len(original),
            "sha256": hashlib.sha256(original).hexdigest(),
        },
    ]
    manifest = release / ".executive-release-manifest.json"
    manifest_bytes = (
        json.dumps(
            {
                "schema_version": "mastermind.executive_release_manifest/v1",
                "commit_sha": contract.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
                "tree_sha": "f" * 40,
                "entries": entries,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    manifest.write_bytes(manifest_bytes)
    manifest.chmod(0o444)
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_RELEASE_TREE", "f" * 40)
    monkeypatch.setattr(
        artifacts,
        "_TRUSTED_E4_MANIFEST_SHA256",
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_SIZE", len(manifest_bytes))
    monkeypatch.setattr(artifacts, "_TRUSTED_E4_MANIFEST_ENTRY_COUNT", len(entries))
    sentinel = tmp_path / "installed-code-executed"
    script.chmod(0o600)
    script.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    script.chmod(0o444)

    def subprocess_is_forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("installed release code must never be launched")

    monkeypatch.setattr(artifacts.subprocess, "run", subprocess_is_forbidden)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="RELEASE_INVALID"):
        artifacts._verify_inert_release_manifest(
            release,
            expected_commit=contract.PRESERVED_TOPOLOGY_RELEASE_COMMIT,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    assert not sentinel.exists()


def test_privileged_git_environment_is_closed_to_ambient_execution_and_network() -> None:
    environment = artifacts._git_environment()
    assert environment == {
        "HOME": "/var/empty",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_LOCAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_EXTERNAL_DIFF": "/usr/bin/false",
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_CONFIG_COUNT": "6",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "core.attributesFile",
        "GIT_CONFIG_VALUE_2": "/dev/null",
        "GIT_CONFIG_KEY_3": "protocol.allow",
        "GIT_CONFIG_VALUE_3": "never",
        "GIT_CONFIG_KEY_4": "protocol.file.allow",
        "GIT_CONFIG_VALUE_4": "always",
        "GIT_CONFIG_KEY_5": "diff.external",
        "GIT_CONFIG_VALUE_5": "/usr/bin/false",
    }


def test_hardened_git_does_not_execute_local_include_fsmonitor_diff_or_textconv(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    payload = repository / "payload.txt"
    payload.write_text("one\n", encoding="utf-8")
    (repository / ".gitattributes").write_text(
        "payload.txt diff=hostile\n", encoding="utf-8"
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "fixture")
    payload.write_text("two\n", encoding="utf-8")

    sentinel = tmp_path / "external-code-ran"
    hostile = tmp_path / "hostile.sh"
    hostile.write_text(
        f"#!/bin/sh\n/usr/bin/touch {str(sentinel)!r}\nexit 1\n",
        encoding="utf-8",
    )
    hostile.chmod(0o700)
    included = tmp_path / "included.config"
    included.write_text(
        f"[diff \"hostile\"]\n\texternal = {hostile}\n\ttextconv = {hostile}\n",
        encoding="utf-8",
    )
    _git(repository, "config", "core.fsmonitor", str(hostile))
    _git(repository, "config", "include.path", str(included))
    _git(repository, "config", "diff.hostile.external", str(hostile))
    _git(repository, "config", "diff.hostile.textconv", str(hostile))

    artifacts._run_git(repository, "status", "--porcelain=v1")
    artifacts._run_git(
        repository, "diff", "--no-ext-diff", "--no-textconv", "--", "payload.txt"
    )
    assert not sentinel.exists()


def test_root_created_carrier_is_immune_to_preopened_operator_write_descriptor(
    tmp_path: Path,
) -> None:
    operator_source = tmp_path / "operator-source"
    operator_source.write_bytes(b"reviewed carrier bytes\n")
    writable_descriptor = os.open(operator_source, os.O_RDWR)
    carrier = tmp_path / "carrier"
    executive_os = carrier / "ops" / "executive_os"
    executive_os.mkdir(parents=True, mode=0o700)
    for directory in (carrier, carrier / "ops", executive_os):
        directory.chmod(0o700)
    files = {
        ".repair-carrier-commit": (b"d" * 40 + b"\n", 0o400),
        "ops/executive_os/repair-capacity-source-closure.sh": (
            operator_source.read_bytes(),
            0o500,
        ),
        "ops/executive_os/capacity_host_artifacts.py": (b"# reviewed\n", 0o400),
        "ops/executive_os/capacity_source_contract.py": (b"# reviewed\n", 0o400),
    }
    for relative, (payload, mode) in files.items():
        destination = carrier / relative
        destination.write_bytes(payload)
        destination.chmod(mode)
    if sys.platform == "darwin":
        for path in (carrier, carrier / "ops", executive_os):
            subprocess.run(["/usr/bin/xattr", "-c", path], check=True, capture_output=True)
        for relative, (_payload, mode) in files.items():
            path = carrier / relative
            path.chmod(0o600)
            subprocess.run(["/usr/bin/xattr", "-c", path], check=True, capture_output=True)
            path.chmod(mode)
    try:
        os.lseek(writable_descriptor, 0, os.SEEK_SET)
        os.write(writable_descriptor, b"attacker mutation\n")
        os.ftruncate(writable_descriptor, len(b"attacker mutation\n"))
        assert artifacts.verify_repair_carrier(
            carrier,
            expected_commit="d" * 40,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )["commit_sha"] == "d" * 40
        assert (carrier / "ops/executive_os/repair-capacity-source-closure.sh").read_bytes() == (
            b"reviewed carrier bytes\n"
        )
    finally:
        os.close(writable_descriptor)

    linked = tmp_path / "carrier-hardlink"
    os.link(carrier / "ops/executive_os/capacity_host_artifacts.py", linked)
    with pytest.raises(artifacts.CapacityHostArtifactError, match="REPAIR_CARRIER_INVALID"):
        artifacts.verify_repair_carrier(
            carrier,
            expected_commit="d" * 40,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


def _verify_arguments(system_root: Path, commit: str) -> dict[str, object]:
    return {
        "mode": "verify-only",
        "system_root": system_root,
        "lock_file": system_root / "locks" / "cf2-h0.lock",
        "expected_repair_commit": "d" * 40,
        "expected_source_commit": commit,
        "transport": None,
        "transport_sha256": None,
        "test_adapter": True,
    }


def _rollback_started_empty_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, object], Path]:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    with monkeypatch.context() as failure:
        failure.setattr(
            artifacts, "publish_source_repair_receipt", refuse_receipt
        )
        with pytest.raises(
            artifacts.SourceRepairIncomplete,
            match="after_failure_namespace_parent_fsync",
        ):
            artifacts.run_source_repair_host(
                **arguments,
                crash_at="after_failure_namespace_parent_fsync",
            )

    archive = next((system_root / "capacity-archive").iterdir())
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert position.phase is artifacts.SourceRepairPhase.ROLLBACK_STARTED
    assert position.failure_layout is artifacts.SourceRepairFailureLayout.EMPTY
    return system_root, arguments, archive


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


@pytest.mark.parametrize(
    "observation_name",
    (
        "_observe_source_repair_source",
        "_observe_source_repair_archived_generation",
        "_expected_source_repair_receipt",
        "_generation_values",
    ),
)
def test_committed_replay_early_observation_failure_never_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_name: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    archive = next((system_root / "capacity-archive").iterdir())

    def fail_committed_observation(*args: object, **kwargs: object) -> object:
        raise artifacts.CapacityHostArtifactError("INJECTED_COMMITTED_OBSERVATION")

    monkeypatch.setattr(artifacts, observation_name, fail_committed_observation)
    with pytest.raises(
        artifacts.SourceRepairIncomplete,
        match="POST_COMMIT_RECONCILIATION_REQUIRED",
    ):
        artifacts.run_source_repair_host(**arguments)

    visible_generations = [
        child
        for child in (system_root / "capacity-generations").iterdir()
        if not child.name.startswith(".")
    ]
    assert len(visible_generations) == 1
    assert not any(child.name.startswith("failure-") for child in archive.iterdir())
    assert (archive / "archived-source").is_dir()
    assert (archive / "archived-generation").is_dir()


@pytest.mark.parametrize(
    "fault_site",
    (
        "transition_reconcile",
        "initial_classification",
        "classification_entry_observation",
        "generation_parent_inventory",
    ),
)
def test_committed_replay_structural_fault_before_recovery_authorization_is_effect_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_site: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    archive = next((system_root / "capacity-archive").iterdir())
    injected = artifacts.CapacityHostArtifactError(
        f"INJECTED_STRUCTURAL_FAULT_{fault_site.upper()}"
    )
    original_restore = artifacts._restore_digest_bound_precommit_state
    restore_calls = 0
    fault_triggered = False

    def observed_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        original_restore(*args, **kwargs)

    with monkeypatch.context() as replay_fault:
        replay_fault.setattr(
            artifacts, "_restore_digest_bound_precommit_state", observed_restore
        )
        if fault_site == "transition_reconcile":
            original_reconcile = artifacts.reconcile_source_repair
            reconcile_calls = 0

            def fault_transition_reconcile(*args: object, **kwargs: object) -> object:
                nonlocal fault_triggered, reconcile_calls
                reconcile_calls += 1
                if reconcile_calls == 2:
                    fault_triggered = True
                    raise injected
                return original_reconcile(*args, **kwargs)

            replay_fault.setattr(
                artifacts, "reconcile_source_repair", fault_transition_reconcile
            )
        elif fault_site == "initial_classification":
            original_classify = artifacts._classify_source_repair_position

            def fault_initial_classification(
                *args: object, **kwargs: object
            ) -> object:
                nonlocal fault_triggered
                if not fault_triggered:
                    fault_triggered = True
                    raise injected
                return original_classify(*args, **kwargs)

            replay_fault.setattr(
                artifacts,
                "_classify_source_repair_position",
                fault_initial_classification,
            )
        elif fault_site == "classification_entry_observation":
            original_entry_info = artifacts._descriptor_entry_info

            def fault_classification_entry_observation(
                *args: object, **kwargs: object
            ) -> object:
                nonlocal fault_triggered
                if not fault_triggered:
                    fault_triggered = True
                    raise injected
                return original_entry_info(*args, **kwargs)

            replay_fault.setattr(
                artifacts,
                "_descriptor_entry_info",
                fault_classification_entry_observation,
            )
        elif fault_site == "generation_parent_inventory":
            original_directory_names = artifacts._descriptor_directory_names
            generation_info = (system_root / "capacity-generations").stat()
            generation_identity = (generation_info.st_dev, generation_info.st_ino)

            def fault_generation_parent_inventory(descriptor: int) -> list[str]:
                nonlocal fault_triggered
                descriptor_info = os.fstat(descriptor)
                if (
                    not fault_triggered
                    and (descriptor_info.st_dev, descriptor_info.st_ino)
                    == generation_identity
                ):
                    fault_triggered = True
                    raise injected
                return original_directory_names(descriptor)

            replay_fault.setattr(
                artifacts,
                "_descriptor_directory_names",
                fault_generation_parent_inventory,
            )
        else:
            raise AssertionError(fault_site)

        with pytest.raises(
            artifacts.SourceRepairIncomplete,
            match="POST_COMMIT_RECONCILIATION_REQUIRED",
        ) as raised:
            artifacts.run_source_repair_host(**arguments)

    assert fault_triggered
    assert raised.value.__cause__ is injected
    assert restore_calls == 0
    assert not any(child.name.startswith("failure-") for child in archive.iterdir())
    assert (archive / "archived-source").is_dir()
    assert (archive / "archived-generation").is_dir()
    visible_generations = [
        child
        for child in (system_root / "capacity-generations").iterdir()
        if not child.name.startswith(".")
    ]
    assert len(visible_generations) == 1
    assert not (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).exists()
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )


def test_exact_precommit_classification_pre_authorizes_table_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    original_classify = artifacts._classify_source_repair_position
    original_transition_for = artifacts._source_repair_transition_for
    original_restore = artifacts._restore_digest_bound_precommit_state
    events: list[tuple[object, ...]] = []
    injected = artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    def observed_classify(*args: object, **kwargs: object) -> object:
        phase = original_classify(*args, **kwargs)
        events.append(("classified", phase))
        return phase

    def observed_transition_for(
        mode: artifacts.SourceRepairMode,
        phase: artifacts.SourceRepairPhase,
        failure_layout: artifacts.SourceRepairFailureLayout,
    ) -> artifacts.SourceRepairTransition:
        transition = original_transition_for(mode, phase, failure_layout)
        events.append(("transition", mode, phase, failure_layout, transition))
        return transition

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        events.append(("fault", injected))
        raise injected

    def observed_restore(*args: object, **kwargs: object) -> None:
        events.append(("restore", kwargs["transition"]))
        original_restore(*args, **kwargs)

    monkeypatch.setattr(
        artifacts, "_classify_source_repair_position", observed_classify
    )
    monkeypatch.setattr(
        artifacts, "_source_repair_transition_for", observed_transition_for
    )
    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    monkeypatch.setattr(
        artifacts, "_restore_digest_bound_precommit_state", observed_restore
    )

    with pytest.raises(
        artifacts.CapacityHostArtifactError, match="INJECTED_RECEIPT_REFUSAL"
    ) as raised:
        artifacts.run_source_repair_host(**arguments)
    assert raised.value is injected

    classified_index = next(
        index
        for index, event in enumerate(events)
        if event == ("classified", artifacts.SourceRepairPhase.GENERATION_ARCHIVED)
    )
    recovery_index = next(
        index
        for index, event in enumerate(events)
        if event[:4]
        == (
            "transition",
            artifacts.SourceRepairMode.RECOVERY,
            artifacts.SourceRepairPhase.GENERATION_ARCHIVED,
            artifacts.SourceRepairFailureLayout.NONE,
        )
    )
    fault_index = next(
        index for index, event in enumerate(events) if event[0] == "fault"
    )
    restore_index = next(
        index for index, event in enumerate(events) if event[0] == "restore"
    )
    assert classified_index < recovery_index < fault_index < restore_index
    assert not any(
        event[0] == "classified" for event in events[fault_index + 1 : restore_index]
    )
    recovery_transition = events[recovery_index][4]
    assert isinstance(recovery_transition, artifacts.SourceRepairTransition)
    assert recovery_transition.action is artifacts.SourceRepairAction.RECOVER_PRECOMMIT
    assert events[restore_index][1] is recovery_transition
    assert sum(event[0] == "restore" for event in events) == 1
    restored_source = system_root / "capacity-sources" / "macro" / commit
    assert restored_source.is_dir()
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()


def test_direct_recovery_consumes_grant_before_single_restore_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, arguments, archive = _rollback_started_empty_fixture(
        tmp_path, monkeypatch
    )
    original_restore = artifacts._restore_digest_bound_precommit_state
    restore_transitions: list[artifacts.SourceRepairTransition] = []

    def observed_restore(*args: object, **kwargs: object) -> None:
        transition = kwargs["transition"]
        assert isinstance(transition, artifacts.SourceRepairTransition)
        restore_transitions.append(transition)
        original_restore(*args, **kwargs)

    monkeypatch.setattr(
        artifacts, "_restore_digest_bound_precommit_state", observed_restore
    )
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)

    assert len(restore_transitions) == 1
    direct_transition = artifacts.SOURCE_REPAIR_TRANSITIONS[
        (
            artifacts.SourceRepairMode.REPAIR,
            artifacts.SourceRepairPhase.ROLLBACK_STARTED,
            artifacts.SourceRepairFailureLayout.EMPTY,
        )
    ]
    assert restore_transitions[0] is direct_transition
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        position.failure_layout
        is artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE
    )
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()


def test_direct_recovery_typed_incomplete_is_single_attempt_and_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, arguments, archive = _rollback_started_empty_fixture(
        tmp_path, monkeypatch
    )
    restore_calls = 0
    injected_cause = OSError(errno.EIO, "injected recovery interruption")
    injected = artifacts.SourceRepairIncomplete(
        "INJECTED_RECOVERY_INCOMPLETE"
    )

    def interrupt_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        raise injected from injected_cause

    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            artifacts, "_restore_digest_bound_precommit_state", interrupt_restore
        )
        with pytest.raises(
            artifacts.SourceRepairIncomplete,
            match="INJECTED_RECOVERY_INCOMPLETE",
        ) as raised:
            artifacts.run_source_repair_host(**arguments)

    assert raised.value is injected
    assert raised.value.__cause__ is injected_cause
    assert restore_calls == 1
    interrupted_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert interrupted_position.phase is artifacts.SourceRepairPhase.ROLLBACK_STARTED
    assert (
        interrupted_position.failure_layout
        is artifacts.SourceRepairFailureLayout.EMPTY
    )

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)
    replayed_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert replayed_position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        replayed_position.failure_layout
        is artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE
    )
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()


def test_direct_recovery_durability_uncertain_is_single_attempt_and_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, arguments, archive = _rollback_started_empty_fixture(
        tmp_path, monkeypatch
    )
    restore_calls = 0
    injected_cause = OSError(errno.EIO, "injected recovery durability")
    injected = artifacts.SourceRepairRenameDurabilityUncertain(
        "INJECTED_RECOVERY_DURABILITY_UNCERTAIN"
    )

    def interrupt_restore(*args: object, **kwargs: object) -> None:
        nonlocal restore_calls
        restore_calls += 1
        raise injected from injected_cause

    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            artifacts, "_restore_digest_bound_precommit_state", interrupt_restore
        )
        with pytest.raises(
            artifacts.SourceRepairRenameDurabilityUncertain,
            match="INJECTED_RECOVERY_DURABILITY_UNCERTAIN",
        ) as raised:
            artifacts.run_source_repair_host(**arguments)

    assert raised.value is injected
    assert raised.value.__cause__ is injected_cause
    assert restore_calls == 1
    interrupted_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert interrupted_position.phase is artifacts.SourceRepairPhase.ROLLBACK_STARTED
    assert (
        interrupted_position.failure_layout
        is artifacts.SourceRepairFailureLayout.EMPTY
    )

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_PRECOMMIT_RESTORED",
    ):
        artifacts.run_source_repair_host(**arguments)
    replayed_position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert replayed_position.phase is artifacts.SourceRepairPhase.ROLLED_BACK
    assert (
        replayed_position.failure_layout
        is artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE
    )
    assert (
        system_root
        / "capacity-generations"
        / artifacts.PRIOR_GENERATION_DIGEST
    ).is_dir()


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


def test_source_repair_transition_table_is_exhaustive_and_terminal_states_are_distinct() -> None:
    table = artifacts.SOURCE_REPAIR_TRANSITIONS
    for mode in artifacts.SourceRepairMode:
        assert {
            phase
            for table_mode, phase, _failure_layout in table
            if table_mode is mode
        } == set(artifacts.SourceRepairPhase)
    assert {transition.action for transition in table.values()} == set(
        artifacts.SourceRepairAction
    )
    assert all(
        isinstance(transition.permitted_next_states, frozenset)
        for transition in table.values()
    )
    for mode in artifacts.SourceRepairMode:
        for phase in (
            artifacts.SourceRepairPhase.ROLLBACK_STARTED,
            artifacts.SourceRepairPhase.ROLLBACK_GENERATION_RESTORED,
            artifacts.SourceRepairPhase.ROLLED_BACK,
        ):
            for layout in (
                artifacts.SourceRepairFailureLayout.EMPTY,
                artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE,
                artifacts.SourceRepairFailureLayout.STAGED_SOURCE,
            ):
                assert (mode, phase, layout) in table
    assert table[
        (
            artifacts.SourceRepairMode.REPAIR,
            artifacts.SourceRepairPhase.ROLLED_BACK,
            artifacts.SourceRepairFailureLayout.INSTALLED_SOURCE,
        )
    ].action is artifacts.SourceRepairAction.REFUSE_ROLLED_BACK
    assert table[
        (
            artifacts.SourceRepairMode.VERIFY_ONLY,
            artifacts.SourceRepairPhase.COMMITTED,
            artifacts.SourceRepairFailureLayout.NONE,
        )
    ].action is artifacts.SourceRepairAction.VERIFY_COMMITTED


@pytest.mark.parametrize("authority_change", ("removed", "refused"))
def test_repair_transition_table_is_the_executable_authority_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority_change: str,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at="after_intent_fsync")
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        artifacts.SourceRepairPhase.INTENT_DURABLE,
        artifacts.SourceRepairFailureLayout.NONE,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    if authority_change == "removed":
        transitions.pop(key)
    else:
        transitions[key] = artifacts.SourceRepairTransition(
            artifacts.SourceRepairAction.REFUSE_UNKNOWN, frozenset()
        )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_TRANSITION_(UNKNOWN|REFUSED)",
    ):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


def test_transition_permitted_next_states_refuse_forward_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(**arguments, crash_at="after_intent_fsync")
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        artifacts.SourceRepairPhase.INTENT_DURABLE,
        artifacts.SourceRepairFailureLayout.NONE,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    transitions[key] = artifacts.SourceRepairTransition(
        artifacts.SourceRepairAction.ADVANCE_SOURCE, frozenset()
    )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    with pytest.raises(
        artifacts.SourceRepairTransitionError,
        match="SOURCE_REPAIR_NEXT_STATE_REFUSED",
    ):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


def test_transition_permitted_next_states_refuse_rollback_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    with monkeypatch.context() as failure:
        failure.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
        with pytest.raises(artifacts.SourceRepairIncomplete):
            artifacts.run_source_repair_host(
                **arguments, crash_at="after_failure_namespace_parent_fsync"
            )
    archive = next((system_root / "capacity-archive").iterdir())
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        position.phase,
        position.failure_layout,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    transitions[key] = artifacts.SourceRepairTransition(
        artifacts.SourceRepairAction.RECOVER_PRECOMMIT, frozenset()
    )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    with pytest.raises(
        artifacts.SourceRepairTransitionError,
        match="SOURCE_REPAIR_NEXT_STATE_REFUSED",
    ):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


@pytest.mark.parametrize(
    ("crash_at", "phase"),
    (
        (
            "after_intent_fsync",
            artifacts.SourceRepairPhase.INTENT_DURABLE,
        ),
        (
            "after_old_source_move",
            artifacts.SourceRepairPhase.SOURCE_ARCHIVED,
        ),
        (
            "after_candidate_install",
            artifacts.SourceRepairPhase.SOURCE_INSTALLED,
        ),
        (
            "after_old_generation_move",
            artifacts.SourceRepairPhase.GENERATION_ARCHIVED,
        ),
        (
            "after_repair_receipt_fsync",
            artifacts.SourceRepairPhase.RECEIPT_DURABLE,
        ),
        (
            "before_final_rename",
            artifacts.SourceRepairPhase.GENERATION_PREFIX,
        ),
        (
            None,
            artifacts.SourceRepairPhase.COMMITTED,
        ),
    ),
)
def test_repair_transition_table_refusal_controls_each_forward_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_at: str | None,
    phase: artifacts.SourceRepairPhase,
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    if crash_at is None:
        assert artifacts.run_source_repair_host(**arguments) == (
            "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
        )
    else:
        with pytest.raises(artifacts.SourceRepairIncomplete):
            artifacts.run_source_repair_host(**arguments, crash_at=crash_at)
    before = _scoped_tree_snapshot(system_root)
    key = (
        artifacts.SourceRepairMode.REPAIR,
        phase,
        artifacts.SourceRepairFailureLayout.NONE,
    )
    transitions = dict(artifacts.SOURCE_REPAIR_TRANSITIONS)
    transitions[key] = artifacts.SourceRepairTransition(
        artifacts.SourceRepairAction.REFUSE_UNKNOWN, frozenset()
    )
    monkeypatch.setattr(artifacts, "SOURCE_REPAIR_TRANSITIONS", transitions)

    expected_error = (
        artifacts.SourceRepairIncomplete
        if phase is artifacts.SourceRepairPhase.COMMITTED
        else artifacts.SourceRepairTransitionError
    )
    with pytest.raises(expected_error):
        artifacts.run_source_repair_host(**arguments)
    assert _scoped_tree_snapshot(system_root) == before


def test_source_repair_host_commits_generation_last_and_verify_is_zero_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    lock_events: list[str] = []
    original_lock = artifacts._source_repair_lock

    def observed_lock(*args: object, **kwargs: object) -> int:
        descriptor = original_lock(*args, **kwargs)
        lock_events.append("locked")
        return descriptor

    def resolve_after_lock(operator_user: str) -> int:
        assert operator_user == "operator"
        assert lock_events == ["locked"]
        return os.getuid()

    monkeypatch.setattr(artifacts, "_source_repair_lock", observed_lock)
    monkeypatch.setattr(
        artifacts, "_resolve_source_repair_operator_uid", resolve_after_lock
    )
    result = artifacts.run_source_repair_host(
        mode="repair",
        system_root=system_root,
        lock_file=system_root / "locks" / "cf2-h0.lock",
        expected_repair_commit="d" * 40,
        expected_source_commit=commit,
        operator_user="operator",
        transport=transport,
        transport_sha256=hashlib.sha256(transport.read_bytes()).hexdigest(),
        test_adapter=True,
    )
    assert result == "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    archives = list((system_root / "capacity-archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "archived-source" / "promisor-source").read_bytes().startswith(
        b"old incomplete"
    )
    assert (archives[0] / "archived-generation").is_dir()
    assert (archives[0] / "source-repair-receipt.json").is_file()
    visible = [path for path in (system_root / "capacity-generations").iterdir()]
    assert len(visible) == 1
    assert not visible[0].name.startswith(".")
    assert sorted(path.name for path in visible[0].iterdir()) == [
        "broker-topology.json",
        "components.json",
        "host-preparation-receipt.json",
        "rollback-contract.json",
        "rollback-drill-receipt.json",
        "source-config.json",
    ]

    content_before = _scoped_content_observation(system_root)
    metadata_before = _scoped_metadata_observation(system_root)
    for _ in range(2):
        assert artifacts.run_source_repair_host(
            mode="verify-only",
            system_root=system_root,
            lock_file=system_root / "locks" / "cf2-h0.lock",
            expected_repair_commit="d" * 40,
            expected_source_commit=commit,
            transport=None,
            transport_sha256=None,
            test_adapter=True,
        ) == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"
    metadata_after = _scoped_metadata_observation(system_root)
    content_after = _scoped_content_observation(system_root)
    _assert_only_kernel_atime_may_advance(metadata_before, metadata_after)
    assert content_after == content_before


def test_verify_only_native_read_atime_advance_is_observed_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    installed_index = (
        system_root / "capacity-sources" / "macro" / commit / ".git" / "index"
    )
    expected_index_digest = hashlib.sha256(installed_index.read_bytes()).hexdigest()
    observed = installed_index.stat()
    os.utime(
        installed_index,
        ns=(observed.st_mtime_ns - 1_000_000_000, observed.st_mtime_ns),
    )
    metadata_before = _scoped_metadata_observation(system_root)

    assert artifacts.run_source_repair_host(
        **_verify_arguments(system_root, commit)
    ) == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"
    metadata_after = _scoped_metadata_observation(system_root)
    _assert_only_kernel_atime_may_advance(metadata_before, metadata_after)
    relative_index = installed_index.relative_to(system_root).as_posix()
    assert metadata_after[1][relative_index] > metadata_before[1][relative_index]
    assert hashlib.sha256(installed_index.read_bytes()).hexdigest() == expected_index_digest


def test_verify_only_has_no_reachable_program_mutation_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    content_before = _scoped_content_observation(system_root)
    metadata_before = _scoped_metadata_observation(system_root)
    original_open = os.open

    def read_only_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        forbidden_flags = (
            os.O_WRONLY
            | os.O_RDWR
            | os.O_CREAT
            | os.O_TRUNC
            | os.O_APPEND
            | getattr(os, "O_EXCL", 0)
        )
        assert flags & forbidden_flags == 0, (path, flags)
        return original_open(path, flags, *args, **kwargs)

    def forbidden_mutation(*args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))

    with monkeypatch.context() as mutation_guard:
        mutation_guard.setattr(os, "open", read_only_open)
        for name in (
            "chmod",
            "fchmod",
            "chown",
            "fchown",
            "mkdir",
            "makedirs",
            "rename",
            "replace",
            "unlink",
            "remove",
            "rmdir",
            "link",
            "symlink",
            "utime",
            "truncate",
            "ftruncate",
            "fsync",
            "chflags",
            "fchflags",
            "setxattr",
            "removexattr",
        ):
            if hasattr(os, name):
                mutation_guard.setattr(os, name, forbidden_mutation)
        for name in (
            "_rename_exclusive",
            "publish_source_repair_intent",
            "publish_source_repair_receipt",
            "_build_repaired_generation_candidate",
            "_restore_digest_bound_precommit_state",
            "_durable_source_repair_rename",
            "_write_generation_payload",
            "copy_closed_input",
            "materialize_source_transport_v2",
        ):
            mutation_guard.setattr(artifacts, name, forbidden_mutation)
        assert artifacts.run_source_repair_host(
            **_verify_arguments(system_root, commit)
        ) == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"

    metadata_after = _scoped_metadata_observation(system_root)
    content_after = _scoped_content_observation(system_root)
    _assert_only_kernel_atime_may_advance(metadata_before, metadata_after)
    assert content_after == content_before


def test_source_repair_replays_forward_after_visible_final_rename_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    with pytest.raises(artifacts.SourceRepairIncomplete):
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
            crash_at="after_final_rename_before_parent_fsync",
        )
    archive = next((system_root / "capacity-archive").iterdir())
    assert (archive / "archived-source").is_dir()
    assert not (system_root / "capacity-generations" / artifacts.PRIOR_GENERATION_DIGEST).exists()
    assert artifacts.run_source_repair_host(
        mode="repair",
        system_root=system_root,
        lock_file=system_root / "locks" / "cf2-h0.lock",
        expected_repair_commit="d" * 40,
        expected_source_commit=commit,
        operator_uid=os.getuid(),
        transport=transport,
        transport_sha256=hashlib.sha256(transport.read_bytes()).hexdigest(),
        test_adapter=True,
    ) == "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    assert (archive / "archived-source").is_dir()


def test_source_repair_replay_after_success_stdout_is_exactly_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
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
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    committed = _scoped_tree_snapshot(system_root)
    assert artifacts.run_source_repair_host(**arguments) == (
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    )
    assert _scoped_tree_snapshot(system_root) == committed


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_at: str
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
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


def _terminal_failure_evidence_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layout: str,
) -> tuple[Path, Path, Path]:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    with monkeypatch.context() as failure:
        if layout not in {"installed-source", "staged-source"}:
            raise AssertionError(layout)

        def refuse_receipt(*args: object, **kwargs: object) -> str:
            raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

        failure.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
        with pytest.raises(artifacts.CapacityHostArtifactError, match="INJECTED_"):
            artifacts.run_source_repair_host(**arguments)
    archive = next((system_root / "capacity-archive").iterdir())
    failure_namespace = archive / f"failure-{archive.name.removeprefix('source-closure-repair-')}"
    installed_evidence = failure_namespace / "installed-source"
    evidence = failure_namespace / layout
    if layout == "staged-source":
        installed_evidence.rename(evidence)
    assert evidence.is_dir()
    return system_root, archive, evidence


@pytest.mark.parametrize("layout", ("installed-source", "staged-source"))
@pytest.mark.parametrize(
    "mutation",
    (
        "type",
        "symlink",
        "mode",
        "ownership",
        "device_identity",
        "hard_link",
        "unexpected_descendant",
        "content_digest",
    ),
)
def test_failure_evidence_layouts_refuse_every_semantic_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layout: str,
    mutation: str,
) -> None:
    _system_root, archive, evidence = _terminal_failure_evidence_fixture(
        tmp_path, monkeypatch, layout
    )
    expected_uid = os.getuid()
    expected_gid = os.getgid()
    if mutation in {"type", "symlink"}:
        preserved = tmp_path / f"preserved-{layout}"
        evidence.rename(preserved)
        if mutation == "type":
            evidence.write_bytes(b"not a repository\n")
        else:
            evidence.symlink_to(preserved, target_is_directory=True)
    elif mutation == "mode":
        evidence.chmod(0o755)
    elif mutation == "ownership":
        alternate_gid = next(gid for gid in os.getgroups() if gid != expected_gid)
        os.chown(evidence, -1, alternate_gid)
    elif mutation == "device_identity":
        original_fstat = os.fstat
        evidence_info = evidence.stat()

        def wrong_device(descriptor: int) -> os.stat_result:
            info = original_fstat(descriptor)
            if info.st_dev == evidence_info.st_dev and info.st_ino == evidence_info.st_ino:
                values = list(info)
                values[2] = info.st_dev + 1
                return os.stat_result(values)
            return info

        monkeypatch.setattr(os, "fstat", wrong_device)
    elif mutation == "hard_link":
        linked = next(path for path in evidence.rglob("*") if path.is_file())
        os.link(linked, tmp_path / f"external-hard-link-{layout}")
    elif mutation == "unexpected_descendant":
        (evidence / "unexpected-evidence").write_bytes(b"unexpected\n")
    elif mutation == "content_digest":
        changed = next(
            path
            for path in evidence.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(evidence).parts
        )
        original_mode = stat.S_IMODE(changed.stat().st_mode)
        changed.chmod(0o600)
        changed.write_bytes(changed.read_bytes() + b"tampered\n")
        changed.chmod(original_mode)
    else:
        raise AssertionError(mutation)

    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FAILURE_(EVIDENCE|NAMESPACE)_INVALID",
    ):
        artifacts.reconcile_source_repair(
            archive, expected_uid=expected_uid, expected_gid=expected_gid
        )


def test_failure_evidence_binds_exact_intent_source_tree_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _system_root, archive, _evidence_path = _terminal_failure_evidence_fixture(
        tmp_path, monkeypatch, "installed-source"
    )
    original_verify = artifacts._verify_installed_repair_source

    def unequal_tree_with_same_inventory(
        *args: object, **kwargs: object
    ) -> tuple[dict[str, object], artifacts.SourceClosureEvidence]:
        manifest, evidence = original_verify(*args, **kwargs)
        return manifest, artifacts.SourceClosureEvidence(
            object_count=evidence.object_count,
            object_inventory_sha256=evidence.object_inventory_sha256,
            source_tree_sha256="0" * 64,
        )

    monkeypatch.setattr(
        artifacts, "_verify_installed_repair_source", unequal_tree_with_same_inventory
    )
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID",
    ):
        artifacts.reconcile_source_repair(
            archive, expected_uid=os.getuid(), expected_gid=os.getgid()
        )


def test_empty_failure_namespace_is_an_explicit_recovery_child_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    with pytest.raises(artifacts.SourceRepairIncomplete):
        artifacts.run_source_repair_host(
            **arguments, crash_at="after_failure_namespace_parent_fsync"
        )
    archive = next((system_root / "capacity-archive").iterdir())
    position = artifacts.reconcile_source_repair(
        archive, expected_uid=os.getuid(), expected_gid=os.getgid()
    )
    assert position.failure_layout is artifacts.SourceRepairFailureLayout.EMPTY


def test_terminal_recovery_revalidates_preserved_failure_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_root, transport, commit, _manifest = _repair_host_fixture(
        tmp_path, monkeypatch
    )
    arguments = _repair_arguments(system_root, transport, commit)
    original_rename = artifacts._durable_source_repair_rename

    def mutate_after_source_restore(*args: object, **kwargs: object) -> object:
        result = original_rename(*args, **kwargs)
        if kwargs.get("move_name") == "rollback_source":
            archive = next((system_root / "capacity-archive").iterdir())
            failure_namespace = archive / (
                f"failure-{archive.name.removeprefix('source-closure-repair-')}"
            )
            evidence = failure_namespace / "installed-source"
            changed = next(
                path
                for path in evidence.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(evidence).parts
            )
            original_mode = stat.S_IMODE(changed.stat().st_mode)
            changed.chmod(0o600)
            changed.write_bytes(changed.read_bytes() + b"late-tamper\n")
            changed.chmod(original_mode)
        return result

    def refuse_receipt(*args: object, **kwargs: object) -> str:
        raise artifacts.CapacityHostArtifactError("INJECTED_RECEIPT_REFUSAL")

    monkeypatch.setattr(
        artifacts, "_durable_source_repair_rename", mutate_after_source_restore
    )
    monkeypatch.setattr(artifacts, "publish_source_repair_receipt", refuse_receipt)
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID",
    ):
        artifacts.run_source_repair_host(**arguments)


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
