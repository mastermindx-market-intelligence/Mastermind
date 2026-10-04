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
            "-I",
            "-B",
            "/Library/Application Support/MastermindExecutive/releases/x/ops/executive_os/executive_mcp_entry.py",
            "--config",
            "/Library/Application Support/MastermindExecutive/config/executive-mcp.json",
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
            "/usr/bin/env",
            "-i",
            f"HOME={home}",
            "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "/opt/homebrew/Cellar/tunnel-client/0.0.14/bin/tunnel-client",
            "run",
            "--config",
            str(home / ".config/tunnel-client/mastermind-executive-production.yaml"),
            "--pid.file",
            str(
                home
                / "Library/Application Support/tunnel-client/health/mastermind-executive-production.pid"
            ),
        ],
    }


def _write(path: Path, value: dict) -> None:
    path.write_bytes(plistlib.dumps(value))


def test_mcp_apply_is_idempotent_and_only_changes_restart_policy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mcp.plist"
    before = _mcp()
    _write(path, before)
    os.chmod(path, 0o644)

    changed, backup = mod.apply(path, "mcp", tmp_path / "backups")

    assert changed is True
    assert backup is not None
    assert plistlib.loads(backup.read_bytes()) == before
    expected = dict(before, KeepAlive=True, ThrottleInterval=10)
    assert plistlib.loads(path.read_bytes()) == expected
    assert path.stat().st_mode & 0o777 == 0o644

    changed, backup = mod.apply(path, "mcp", tmp_path / "backups")
    assert changed is False
    assert backup is None


def test_tunnel_apply_preserves_mode_and_refuses_identity_drift(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tunnel.plist"
    before = _tunnel(tmp_path)
    _write(path, before)
    os.chmod(path, 0o600)

    changed, backup = mod.apply(path, "tunnel", tmp_path / "backups")

    assert changed is True
    assert backup is not None
    assert path.stat().st_mode & 0o777 == 0o600
    after = plistlib.loads(path.read_bytes())
    assert after["KeepAlive"] is True
    assert after["ThrottleInterval"] == 10

    bad = dict(before, Label="com.example.not-executive")
    _write(path, bad)
    with pytest.raises(
        mod.NetworkLaunchdContractError, match="unexpected launchd label"
    ):
        mod.load_and_validate(path, "tunnel")


@pytest.mark.parametrize("fault", ["symlink", "hardlink", "writable"])
def test_plist_identity_refuses_unsafe_files(tmp_path: Path, fault: str) -> None:
    original = tmp_path / "source.plist"
    _write(original, _mcp())
    os.chmod(original, 0o644)
    target = tmp_path / "target.plist"

    if fault == "symlink":
        target.symlink_to(original)
    elif fault == "hardlink":
        os.link(original, target)
    else:
        target.write_bytes(original.read_bytes())
        target.chmod(0o666)

    with pytest.raises(mod.NetworkLaunchdContractError):
        mod.load_and_validate(target, "mcp")


def test_existing_mismatched_preimage_refuses_before_target_write(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mcp.plist"
    before = _mcp()
    _write(path, before)
    os.chmod(path, 0o644)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / "mcp.plist.before-self-heal"
    backup.write_bytes(b"different preimage")
    backup.chmod(0o600)
    original = path.read_bytes()

    with pytest.raises(
        mod.NetworkLaunchdContractError, match="rollback preimage differs"
    ):
        mod.apply(path, "mcp", backup_dir)

    assert path.read_bytes() == original
    assert mod.is_hardened(plistlib.loads(path.read_bytes())) is False


def test_check_accepts_current_production_shapes(tmp_path: Path) -> None:
    mcp = _mcp()
    mcp["KeepAlive"] = True
    mcp["ThrottleInterval"] = 10
    mcp_path = tmp_path / "mcp.plist"
    _write(mcp_path, mcp)
    os.chmod(mcp_path, 0o644)

    tunnel = _tunnel(tmp_path)
    tunnel["KeepAlive"] = True
    tunnel["ThrottleInterval"] = 10
    tunnel_path = tmp_path / "tunnel.plist"
    _write(tunnel_path, tunnel)
    os.chmod(tunnel_path, 0o600)

    assert mod.is_hardened(mod.load_and_validate(mcp_path, "mcp"))
    assert mod.is_hardened(mod.load_and_validate(tunnel_path, "tunnel"))


def test_installed_tunnel_path_is_exact_and_user_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "com.mastermind.executive.tunnel.plist"
    value = _tunnel(tmp_path)
    value["KeepAlive"] = True
    value["ThrottleInterval"] = 10
    _write(path, value)
    path.chmod(0o600)
    monkeypatch.setattr(mod, "_canonical_path", lambda target: path)

    mod._require_installed_path(path, "tunnel")

    other = tmp_path / "lookalike.plist"
    _write(other, value)
    other.chmod(0o600)
    with pytest.raises(
        mod.NetworkLaunchdContractError, match="canonical installed tunnel path"
    ):
        mod._require_installed_path(other, "tunnel")


def test_installed_tunnel_path_refuses_wrong_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "com.mastermind.executive.tunnel.plist"
    _write(path, _tunnel(tmp_path))
    path.chmod(0o644)
    monkeypatch.setattr(mod, "_canonical_path", lambda target: path)

    with pytest.raises(mod.NetworkLaunchdContractError, match="mode must be 0600"):
        mod._require_installed_path(path, "tunnel")
