from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path


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


def test_status_ready_validation_is_bound_to_exact_slot_without_identity_output(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load()
    slot = _slot(module, tmp_path)
    slot.provider_home.mkdir(mode=0o700)
    slot.auth_path.write_bytes(b"opaque")
    slot.auth_path.chmod(0o600)
    slot.readiness_receipt.write_text("{}", encoding="utf-8")
    slot.readiness_receipt.chmod(0o400)
    captured = {}

    monkeypatch.setattr(module, "_receipt_metadata_valid", lambda _path: True)

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
    slot.provider_home.mkdir(mode=0o700)
    slot.auth_path.write_bytes(b"opaque")
    slot.auth_path.chmod(0o600)
    slot.readiness_receipt.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "_receipt_metadata_valid", lambda _path: True)

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
