from __future__ import annotations

import importlib.util
import os
import plistlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "ops" / "executive_os" / "executive_network_launchd.py"
SPEC = importlib.util.spec_from_file_location("executive_network_launchd", PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def _mcp() -> dict:
    return {
        "Label": "com.mastermind.executive.mcp",
        "RunAtLoad": True,
        "KeepAlive": False,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "Umask": 0o77,
        "UserName": "_mastermind_executive_mcp",
        "GroupName": "_mastermind_executive_mcp",
        "ProgramArguments": [
            "/Library/Application Support/MastermindExecutive/network-runtimes/x/bin/python",
            "-I", "-B",
            "/Library/Application Support/MastermindExecutive/releases/x/ops/executive_os/executive_mcp_entry.py",
            "--config", "/Library/Application Support/MastermindExecutive/config/executive-mcp.json",
        ],
    }


def _tunnel(home: Path) -> dict:
    return {
        "Label": "com.mastermind.executive.tunnel",
        "RunAtLoad": True,
        "KeepAlive": False,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "Umask": 0o77,
        "ProgramArguments": [
            "/usr/bin/env", "-i", f"HOME={home}", "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "/opt/homebrew/bin/tunnel-client", "run", "--config",
            str(home / ".config/tunnel-client/mastermind-executive-production.yaml"),
            "--pid.file", str(home / "Library/Application Support/tunnel-client/health/mastermind-executive-production.pid"),
        ],
    }


def _write(path: Path, value: dict) -> None:
    path.write_bytes(plistlib.dumps(value))


def test_mcp_apply_is_idempotent_and_only_changes_restart_policy(tmp_path: Path) -> None:
    path = tmp_path / "mcp.plist"
    before = _mcp()
    _write(path, before)
    changed, backup = mod.apply(path, "mcp", tmp_path / "backups")
    assert changed is True and backup is not None and backup.exists()
    after = plistlib.loads(path.read_bytes())
    expected = dict(before, KeepAlive=True, ThrottleInterval=10)
    assert after == expected
    changed, backup = mod.apply(path, "mcp", tmp_path / "backups")
    assert changed is False and backup is None


def test_tunnel_apply_preserves_mode_and_refuses_identity_drift(tmp_path: Path) -> None:
    path = tmp_path / "tunnel.plist"
    before = _tunnel(tmp_path)
    _write(path, before)
    os.chmod(path, 0o600)
    changed, _ = mod.apply(path, "tunnel", tmp_path / "backups")
    assert changed is True
    assert path.stat().st_mode & 0o777 == 0o600
    after = plistlib.loads(path.read_bytes())
    assert after["KeepAlive"] is True
    assert after["ThrottleInterval"] == 10
    bad = dict(before, Label="com.example.not-executive")
    _write(path, bad)
    with pytest.raises(mod.NetworkLaunchdContractError, match="unexpected launchd label"):
        mod.load_and_validate(path, "tunnel")
