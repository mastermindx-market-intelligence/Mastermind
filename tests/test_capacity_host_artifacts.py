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
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest
import yaml

from ops.executive_os import capacity_host_artifacts as artifacts
from ops.executive_os import capacity_source_contract as contract


def _open_fd_inventory() -> frozenset[int]:
    return frozenset(int(name) for name in os.listdir("/dev/fd") if name.isdecimal())


def _overlay_fixture_metadata(
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[Path, tuple[int, int] | tuple[int, int, int]],
) -> None:
    """Represent fixture inodes with exact producer UID/GID identities."""

    identities = {
        (path.stat().st_dev, path.stat().st_ino): expected
        for path, expected in metadata.items()
    }
    original_fstat = os.fstat
    original_stat = os.stat
    original_lstat = os.lstat

    def overlay(info: os.stat_result) -> os.stat_result | _StatOverlay:
        expected = identities.get((info.st_dev, info.st_ino))
        if expected is None:
            return info
        return _StatOverlay(info, st_uid=expected[0], st_gid=expected[1])

    monkeypatch.setattr(os, "fstat", lambda descriptor: overlay(original_fstat(descriptor)))
    monkeypatch.setattr(
        os, "stat", lambda *args, **kwargs: overlay(original_stat(*args, **kwargs))
    )
    monkeypatch.setattr(
        os, "lstat", lambda *args, **kwargs: overlay(original_lstat(*args, **kwargs))
    )


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


def _write_metadata_fixture(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


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
    # Keep the ignore rule source-local: a tracked .gitignore would be an
    # intentionally omitted blob in this sparse v1 transport, and Git status
    # would try to lazily fetch it. Keep a tracked nonmaterial payload below
    # so this fixture still tests exclusion of reviewed-out source content.
    (root / ".git" / "info" / "exclude").write_text(
        "ignored-secret.txt\n", encoding="utf-8"
    )
    (root / "source-only.txt").write_bytes(b"tracked-source-only-must-not-cross\n")
    hook = root / ".git" / "hooks" / "post-checkout"
    hook.write_text("#!/bin/sh\nprintf operator-hook-secret\n", encoding="utf-8")
    hook.chmod(0o700)
    _git(root, "add", "source-only.txt", *paths)
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
    assert "source-only.txt" in _git(source, "ls-files").splitlines()
    assert b"tracked-source-only-must-not-cross" not in encoded
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


def test_closed_input_copy_refuses_insufficient_declared_free_space_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "large-input"
    source.write_bytes(b"authenticated transport")
    source.chmod(0o400)
    destination = tmp_path / "staging" / "copied"
    destination.parent.mkdir()

    class NoSpace:
        f_bavail = 1
        f_frsize = 1

    monkeypatch.setattr(os, "statvfs", lambda _path: NoSpace())
    with pytest.raises(
        artifacts.CapacityHostArtifactError,
        match="CLOSED_INPUT_SPACE_INSUFFICIENT",
    ):
        artifacts.copy_closed_input(
            source,
            destination,
            operator_uid=os.getuid(),
            expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            maximum_bytes=1024,
            minimum_free_multiplier=3,
            minimum_free_reserve_bytes=1,
        )
    assert not destination.exists()


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


def test_complete_transport_schemas_are_explicit_and_not_reinterpreted() -> None:
    assert artifacts.TRANSPORT_SCHEMA == "mastermind.capacity_source_transport/v1"
    assert artifacts.TRANSPORT_SCHEMA_V2 == "mastermind.capacity_source_transport/v2"
    assert artifacts.TRANSPORT_SCHEMA_V3 == "mastermind.capacity_source_transport/v3"
    assert artifacts._V3_TRANSPORT_MAX_BYTES > zipfile.ZIP64_LIMIT


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


def _v3_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, object], str]:
    source, commit, _nonmaterial_oid = _complete_repository(tmp_path, monkeypatch)
    archive = tmp_path / "complete-transport-v3.zip"
    manifest = artifacts.build_source_transport_v3(source, archive, commit=commit)
    checkout = tmp_path / "complete-checkout-v3"
    artifacts.materialize_source_transport_v3(
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


def _repository_fixture_fingerprint(root: Path) -> dict[str, tuple[int, str | None]]:
    """Observe fixture bytes and modes without atimes or mutable Git commands."""

    result = {}
    for path in (root, *sorted(root.rglob("*"))):
        assert not path.is_symlink(), path
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        result[relative] = (stat.S_IMODE(path.stat().st_mode), digest)
    return result


def _repair_host_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    producer_seed: tuple[Path, str, str] | None = None,
) -> tuple[Path, Path, str, dict[str, object]]:
    if producer_seed is None:
        source, commit, _ = _complete_repository(tmp_path, monkeypatch)
    else:
        seed_source, commit, _ = producer_seed
        source = tmp_path / "complete-source"
        # copytree creates independent files, including Git refs, index and objects.
        shutil.copytree(seed_source, source)
        monkeypatch.setattr(artifacts, "PRODUCER_COMMIT", commit, raising=False)
    monkeypatch.setattr(contract, "PRODUCER_COMMIT", commit)
    transport = tmp_path / "operator-transport.zip"
    manifest = artifacts.build_source_transport_v3(source, transport, commit=commit)
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
    # Mirror the real producer's umask-077 intermediate source boundary.
    (system_root / "capacity-sources").chmod(0o700)
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


def _repository_role_directory_policy(root: Path) -> artifacts._RepositorySecurityPolicy:
    info = root.stat()
    return artifacts._RepositorySecurityPolicy(
        role="test-role-directory",
        expected_uid=info.st_uid,
        expected_gid=info.st_gid,
        expected_device=info.st_dev,
        directory_modes=frozenset({0o755}),
        file_modes=frozenset({0o444}),
    )


def _producer_topology_rows(root: Path) -> tuple[list[dict[str, object]], dict[Path, tuple[int, int, int]]]:
    rows: list[dict[str, object]] = []
    metadata: dict[Path, tuple[int, int, int]] = {}
    for index, worker_gid in enumerate((454, 455, 456), start=1):
        slot = f"codex-pro-0{index}"
        config = root / "config" / f"worker-{slot}.json"
        attestation = root / f"codex-attestation-1.0.0-{slot}.json"
        plist = root / "LaunchDaemons" / f"com.mastermind.executive.worker.{slot}.plist"
        for path, mode in ((config, 0o440), (attestation, 0o440), (plist, 0o644)):
            _write_metadata_fixture(path, f"{path.name}\n".encode("ascii"), mode)
        metadata[config] = (0, worker_gid, 0o440)
        metadata[attestation] = (0, worker_gid, 0o440)
        metadata[plist] = (0, 0, 0o644)
        rows.append(
            {
                "slot_id": slot,
                "worker_gid": worker_gid,
                "config_path": str(config),
                "attestation_path": str(attestation),
                "plist_path": str(plist),
            }
        )
    return rows, metadata


_PRESERVED_LABELS = (
    "com.mastermind.executive.control",
    "com.mastermind.executive.worker.codex",
    "com.mastermind.executive.worker.codex-pro-01",
    "com.mastermind.executive.worker.codex-pro-02",
    "com.mastermind.executive.worker.codex-pro-03",
)


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


def _repair_carrier_git_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, str, dict[str, bytes]]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    payloads = {
        "ops/executive_os/repair-capacity-source-closure.sh": (
            b"#!/bin/bash\n/usr/bin/printf '%s\\n' reviewed\n"
        ),
        "ops/executive_os/capacity_host_artifacts.py": b"# artifacts reviewed\n",
        "ops/executive_os/capacity_source_contract.py": b"# contract reviewed\n",
        "ops/executive_os/provider_worker_slots.py": b"# slots reviewed\n",
        "ops/executive_os/provider_identity_policy.py": b"# identity reviewed\n",
    }
    for relative, payload in payloads.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o755 if relative.endswith(".sh") else 0o644)
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "fixture carrier")
    commit = _git(repository, "rev-parse", "HEAD")

    carrier = tmp_path / "carrier"
    executive_os = carrier / "ops" / "executive_os"
    executive_os.mkdir(parents=True, mode=0o700)
    for directory in (carrier, carrier / "ops", executive_os):
        directory.chmod(0o700)
    files = {".repair-carrier-commit": (f"{commit}\n".encode("ascii"), 0o400)}
    files.update(
        {
            relative: (payload, 0o500 if relative.endswith(".sh") else 0o400)
            for relative, payload in payloads.items()
        }
    )
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
    return repository, carrier, commit, payloads


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


@pytest.fixture
def canonical_native_tmp_leaf():
    """Real owned bytes; never alter the global native temp root."""
    if sys.platform != "darwin":
        pytest.skip("Darwin canonical temporary-root contract")
    with tempfile.TemporaryDirectory(prefix="mmx-canonical-tmp-", dir="/tmp") as raw:
        root = Path(raw)
        # Native temp children can inherit wheel; qualify only our own fixture.
        os.chown(root, os.getuid(), os.getgid())
        root.chmod(0o700)
        leaf = root / "evidence.json"
        leaf.write_bytes(b"same retained source bytes\n")
        leaf.chmod(0o444)
        yield root, leaf
