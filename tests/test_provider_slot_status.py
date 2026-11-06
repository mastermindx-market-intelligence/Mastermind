from __future__ import annotations

import errno
import importlib.util
import json
import os
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "provider-slot-status.py"
RUNBOOK = ROOT / "ops" / "executive_os" / "HOST_PREREQUISITES.md"


def _load():
    spec = importlib.util.spec_from_file_location("provider_slot_status_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _slot(module, tmp_path: Path):
    home = tmp_path / "provider-home"
    receipt = tmp_path / "readiness.json"
    return replace(
        module.worker_slots.get_slot("codex-pro-01"),
        worker_uid=os.getuid(),
        worker_gid=os.getgid(),
        provider_home=home,
        readiness_receipt=receipt,
    )


def test_status_missing_receipt_is_sanitized_and_never_opens_credential(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load()
    slot = _slot(module, tmp_path)
    # This test verifies only status rendering, not OS-principal admission.
    # Its unprivileged runner UID/GID cannot impersonate an Executive worker.
    # Dedicated negative tests below retain the real strict custody checks.
    monkeypatch.setattr(module, "_directory_metadata_valid", lambda *_a, **_kw: True)
    monkeypatch.setattr(module, "_credential_metadata_valid", lambda *_a, **_kw: True)
    slot.provider_home.mkdir(mode=0o700)
    slot.auth_path.write_bytes(b"must-never-be-read")
    slot.auth_path.chmod(0o600)

    original_open = Path.open
    opened: list[Path] = []

    def guarded_open(path: Path, *args, **kwargs):
        opened.append(path)
        if path == slot.auth_path:
            raise AssertionError("credential bytes were opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    result = module.inspect_slot(slot, process_probe=lambda _uid: False)

    assert result == {
        "slot_id": "codex-pro-01",
        "oauth_seat_ref": "chatgpt1",
        "provider_home_present": True,
        "provider_home_metadata_valid": True,
        "credential_present": True,
        "credential_metadata_valid": True,
        "readiness_receipt_present": False,
        "readiness_receipt_metadata_valid": False,
        "readiness_state": "missing",
        "readiness_refusal": "readiness_receipt_missing",
        "worker_process_present": False,
    }
    assert slot.auth_path not in opened
    rendered = json.dumps(result, sort_keys=True)
    assert "must-never-be-read" not in rendered
    assert str(slot.provider_home) not in rendered
    assert "_mastermind_codex_01" not in rendered


def test_personal_pro_receipt_metadata_uses_exact_slot_reader_contract(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load()
    slot = module.worker_slots.get_slot("codex-pro-01")
    captured = {}

    def lstat_identity(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {"ok": 1}

    monkeypatch.setattr(module.readiness, "lstat_identity", lstat_identity)
    monkeypatch.setattr(module.readiness, "_assert_no_macos_acl", lambda _path: None)

    assert module._receipt_metadata_valid(
        tmp_path / "receipt.json",
        workspace_binding_class=slot.workspace_binding_class,
        worker_gid=slot.worker_gid,
    ) is True
    assert captured["expected_uid"] == 0
    assert captured["expected_gid"] == 454
    assert captured["expected_mode"] == 0o440
    assert captured["require_nonempty"] is True


def test_status_ready_validation_is_bound_to_exact_slot_without_identity_output(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load()
    slot = _slot(module, tmp_path)
    # This test verifies only status rendering, not OS-principal admission.
    # Its unprivileged runner UID/GID cannot impersonate an Executive worker.
    # Dedicated negative tests below retain the real strict custody checks.
    monkeypatch.setattr(module, "_directory_metadata_valid", lambda *_a, **_kw: True)
    monkeypatch.setattr(module, "_credential_metadata_valid", lambda *_a, **_kw: True)
    slot.provider_home.mkdir(mode=0o700)
    slot.auth_path.write_bytes(b"opaque")
    slot.auth_path.chmod(0o600)
    slot.readiness_receipt.write_text("{}", encoding="utf-8")
    slot.readiness_receipt.chmod(0o400)
    captured = {}

    monkeypatch.setattr(module, "_receipt_metadata_valid", lambda _path, **_kwargs: True)

    def validate_receipt_file(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {"passed": True}

    monkeypatch.setattr(
        module.readiness, "validate_receipt_file", validate_receipt_file
    )
    result = module.inspect_slot(slot, process_probe=lambda uid: uid == os.getuid())

    assert result["readiness_state"] == "ready"
    assert result["readiness_refusal"] is None
    assert result["worker_process_present"] is True
    assert captured == {
        "path": slot.readiness_receipt,
        "auth_path": slot.auth_path,
        "expected_kind": "device-auth",
        "workspace_binding_class": slot.workspace_binding_class,
        "worker_uid": slot.worker_uid,
        "worker_gid": slot.worker_gid,
    }
    assert set(result) == module.STATUS_FIELDS
    assert not any(
        forbidden in json.dumps(result)
        for forbidden in ("account", "email", "profile", "workspace", "auth.json", "/var/")
    )


def test_status_maps_unreviewed_exception_text_to_bounded_refusal(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load()
    slot = _slot(module, tmp_path)
    # This test verifies only status rendering, not OS-principal admission.
    # Its unprivileged runner UID/GID cannot impersonate an Executive worker.
    # Dedicated negative tests below retain the real strict custody checks.
    monkeypatch.setattr(module, "_directory_metadata_valid", lambda *_a, **_kw: True)
    monkeypatch.setattr(module, "_credential_metadata_valid", lambda *_a, **_kw: True)
    slot.provider_home.mkdir(mode=0o700)
    slot.auth_path.write_bytes(b"opaque")
    slot.auth_path.chmod(0o600)
    slot.readiness_receipt.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "_receipt_metadata_valid", lambda _path, **_kwargs: True)

    def refuse(*_args, **_kwargs):
        raise module.readiness.ReadinessError(
            "unsafe /private/path provider@example.invalid"
        )

    monkeypatch.setattr(module.readiness, "validate_receipt_file", refuse)
    result = module.inspect_slot(slot, process_probe=lambda _uid: False)
    assert result["readiness_state"] == "not_ready"
    assert result["readiness_refusal"] == "readiness_invalid"
    assert "/private/path" not in json.dumps(result)
    assert "provider@example.invalid" not in json.dumps(result)


def test_status_source_and_cli_expose_no_arbitrary_path_or_identity_switches() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "slot.auth_path.read" not in source
    assert "open(slot.auth_path" not in source
    assert "--auth" not in source
    assert "--provider-home" not in source
    assert "--receipt" not in source
    assert "--worker-uid" not in source
    assert "--worker-user" not in source
    assert "stdout=subprocess.DEVNULL" in source
    assert "stderr=subprocess.DEVNULL" in source
    assert stat.S_IMODE(SCRIPT.stat().st_mode) & 0o111
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_runbook_maps_each_personal_pro_slot_to_one_isolated_browser_seat() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "### Three isolated Personal Pro readiness slots" in runbook
    assert "provider-slot-status.py" in runbook
    for index in range(1, 4):
        slot_id = f"codex-pro-{index:02d}"
        assert f"`{slot_id}`" in runbook
        assert f"`chatgpt{index}`" in runbook
        assert f"--slot-id {slot_id} --reauthorize-device" in runbook
        assert f"--slot-id {slot_id} --verify-ready" in runbook
    assert "normal Mac Codex app" in runbook
    assert "not routed" in runbook
    assert "--replace-existing" in runbook


def test_unprivileged_fixture_is_never_accepted_as_enrolled_worker(tmp_path: Path) -> None:
    """The live UID/GID gate must reject an ordinary runner's temporary files.

    The other status tests mock this independent gate so they can test sanitized
    output, refusal normalization and exact arguments without root privileges.
    """
    module = _load()
    slot = module.worker_slots.get_slot("codex-pro-01")
    home = tmp_path / "provider-home"
    home.mkdir(mode=0o700)
    auth = home / "auth.json"
    auth.write_bytes(b"not-an-actual-provider-token")
    auth.chmod(0o600)
    assert module._directory_metadata_valid(
        home, uid=slot.worker_uid, gid=slot.worker_gid
    ) is False
    assert module._credential_metadata_valid(
        auth, worker_uid=slot.worker_uid, worker_gid=slot.worker_gid
    ) is False
    assert module._bounded_refusal(
        module.readiness.ReadinessError("unsafe /path: secret")
    ) == "readiness_invalid"

def test_status_permission_denied_is_not_reported_as_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """An unreadable protected realm is UNKNOWN, never proof of absence."""
    module = _load()
    hidden = tmp_path / "protected-worker-home"
    normal_lstat = Path.lstat

    def lstat_with_denied(path: Path, *args, **kwargs):
        if path == hidden:
            raise PermissionError(errno.EACCES, "denied", str(path))
        return normal_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat_with_denied)
    assert module._lstat_present(tmp_path / "genuinely-absent") is False
    with pytest.raises(RuntimeError, match="worker_slot_visibility_unavailable"):
        module._lstat_present(hidden)


def test_status_cli_permission_failure_has_no_partial_json_or_paths(
    monkeypatch, capsys
) -> None:
    module = _load()

    def refuse(_path: Path) -> bool:
        raise module.WorkerStatusVisibilityError("worker_slot_visibility_unavailable")

    monkeypatch.setattr(module, "_lstat_present", refuse)
    assert module.main(["--slot-id", "codex-pro-01"]) == 2
    observed = capsys.readouterr()
    assert observed.out == ""
    assert "worker_slot_visibility_unavailable" in observed.err
    for forbidden in ("/var/", "provider-home", "auth.json", "email", "account_id"):
        assert forbidden not in observed.err
