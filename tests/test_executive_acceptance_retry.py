from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "executive_os" / "acceptance_retry.py"
WRAPPER_PATH = ROOT / "ops" / "executive_os" / "acceptance-retry.sh"
SPEC = importlib.util.spec_from_file_location("executive_acceptance_retry", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
retry_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = retry_module
SPEC.loader.exec_module(retry_module)


SHA = "a" * 40


def _retry(tmp_path: Path):
    system_root = tmp_path / "system"
    runtime_root = tmp_path / "runtime"
    archive_root = tmp_path / "archive"
    release = system_root / "releases" / SHA
    release.mkdir(parents=True)
    runtime_root.mkdir()
    current_uid = os.getuid()
    current_gid = os.getgid()
    return retry_module.AcceptanceRetry(
        expected_sha=SHA,
        release=release,
        layout=retry_module.HostLayout(
            system_root=system_root,
            runtime_root=runtime_root,
            archive_root=archive_root,
        ),
        principals=retry_module.PrincipalIds(
            control_uid=current_uid,
            control_gid=current_gid,
            worker_uid=current_uid,
            worker_gid=current_gid,
            root_uid=current_uid,
            wheel_gid=current_gid,
        ),
    )


def _seed_runtime(retry, tmp_path: Path) -> tuple[Path, Path]:
    for path, uid, gid, mode in retry._active_directory_specs():
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, uid, gid)
        path.chmod(mode)
    for target in retry.archive_targets():
        if target.expected_kind == "directory":
            target.source.mkdir(parents=True, exist_ok=True)
            if target.archive_name == "acceptance-receipts":
                target.source.chmod(0o700)
            (target.source / "evidence.bin").write_bytes(target.archive_name.encode("ascii"))
        else:
            target.source.parent.mkdir(parents=True, exist_ok=True)
            target.source.write_bytes(b"prior-secret-canary")
            target.source.chmod(0o600)

    provider_home = retry.provider_auth.parent
    provider_home.mkdir(parents=True, exist_ok=True)
    auth = retry.provider_auth
    auth.write_bytes(b"credential-bytes-must-not-move")
    auth.chmod(0o600)
    release_marker = retry.release / "release-marker"
    release_marker.write_bytes(b"immutable-release")
    return auth, release_marker


def test_archive_plan_is_exact_sha_scoped_and_excludes_auth_and_release(tmp_path):
    retry = _retry(tmp_path)
    targets = retry.archive_targets()
    sources = {target.source for target in targets}

    assert retry.provider_auth not in sources
    assert retry.provider_auth.parent not in sources
    assert retry.release not in sources
    assert retry.layout.system_root not in sources
    assert retry.layout.runtime_root / "control" / "acceptance" / SHA in sources
    assert not any("auth.json" in os.fspath(path) for path in sources)


def test_archive_moves_evidence_and_recreates_clean_roots_without_touching_auth(tmp_path):
    retry = _retry(tmp_path)
    auth, release_marker = _seed_runtime(retry, tmp_path)
    auth_identity = retry_module._path_identity(auth)
    release_identity = retry_module._path_identity(retry.release)

    destination = retry._create_archive_destination()
    moved = retry._archive_runtime(destination)
    retry._ensure_active_directories()

    assert all(record["status"] == "ARCHIVED" for record in moved)
    for target in retry.archive_targets():
        archived = destination / target.archive_name
        assert archived.exists()
        if target.expected_kind == "directory":
            if target.archive_name == "acceptance-receipts":
                assert not target.source.exists()
            else:
                assert target.source.is_dir()
                children = sorted(item.name for item in target.source.iterdir())
                if target.archive_name == "canary-fixtures":
                    assert children == ["other-worker-home", "production-like"]
                else:
                    assert children == []
        else:
            assert not target.source.exists()
    assert auth.read_bytes() == b"credential-bytes-must-not-move"
    assert retry_module._path_identity(auth) == auth_identity
    assert release_marker.read_bytes() == b"immutable-release"
    assert retry_module._path_identity(retry.release) == release_identity
    assert destination.stat().st_mode & 0o777 == 0o700
    assert all(record["entry_count"] >= 1 for record in moved)


def test_failed_archive_retains_partial_evidence_and_leaves_runtime_recoverable(
    tmp_path, monkeypatch
):
    retry = _retry(tmp_path)
    auth, _release_marker = _seed_runtime(retry, tmp_path)
    auth_identity = retry_module._path_identity(auth)
    events: list[str] = []

    monkeypatch.setattr(retry, "validate_host", lambda: events.append("validate"))
    monkeypatch.setattr(retry, "_protected_identities", lambda: {"auth": auth_identity})
    monkeypatch.setattr(
        retry,
        "_assert_protected_unchanged",
        lambda before: events.append("protected"),
    )

    def safe_state():
        events.append("safe")
        retry._ensure_active_directories()
        return {"passed": True}

    monkeypatch.setattr(retry, "_leave_stopped_and_recoverable", safe_state)
    monkeypatch.setattr(retry, "_stop_and_quiesce", safe_state)
    real_archive = retry._archive_runtime

    def fail_after_first_move(destination):
        first = retry.archive_targets()[0]
        archived = destination / first.archive_name
        os.rename(first.source, archived)
        retry.moved = [
            {
                "source": os.fspath(first.source),
                "archive_name": first.archive_name,
                "status": "ARCHIVED_INVENTORY_PENDING",
            }
        ]
        raise retry_module.RetryError("simulated interruption")

    monkeypatch.setattr(retry, "_archive_runtime", fail_after_first_move)

    with pytest.raises(retry_module.RetryError, match="simulated interruption"):
        retry.run()

    assert events == ["validate", "safe", "safe", "protected"]
    assert retry.archive_path is not None
    assert (retry.archive_path / "control-db" / "evidence.bin").is_file()
    assert (retry.layout.runtime_root / "control" / "db").is_dir()
    assert list((retry.layout.runtime_root / "control" / "db").iterdir()) == []
    incomplete = json.loads(
        (retry.archive_path / "archive-incomplete.json").read_text(encoding="utf-8")
    )
    assert incomplete["status"] == "INCOMPLETE"
    assert auth.read_bytes() == b"credential-bytes-must-not-move"
    assert real_archive is not None  # retain a direct reference for mutation-order coverage


def test_wrapper_uses_only_installed_control_python():
    source = WRAPPER_PATH.read_text(encoding="utf-8")
    assert "acceptance-retry.sh must run as root" in source
    assert "PlistBuddy -c 'Print :ProgramArguments:0'" in source
    assert 'exec "$PYTHON_BINARY" -I -S -B' in source
    assert "acceptance_retry.py" in source
    assert "release_manifest.py" in source
    assert "installed release ownership or modes drifted" in source


def test_retry_helper_has_no_recursive_delete_or_credential_target():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "rmtree" not in source
    assert ".unlink(" not in source
    assert "os.remove(" not in source
    assert '"auth.json", "' not in source
    assert "mastermind-executive-acceptance-archive" in source
    assert "_preflight_archive_layout" in source
    assert "_has_acl(self.provider_auth)" in source


def test_unsafe_archive_target_fails_before_service_stop(tmp_path, monkeypatch):
    retry = _retry(tmp_path)
    _seed_runtime(retry, tmp_path)
    target = retry.archive_targets()[0].source
    retained = target.with_name(target.name + "-retained")
    target.rename(retained)
    target.symlink_to(retained, target_is_directory=True)
    stopped: list[bool] = []

    monkeypatch.setattr(retry, "validate_host", lambda: None)
    monkeypatch.setattr(
        retry,
        "_stop_and_quiesce",
        lambda: stopped.append(True),
    )

    with pytest.raises(retry_module.RetryError, match="symlinked runtime target"):
        retry.run()
    assert stopped == []
    assert not retry.layout.archive_root.exists()
