from __future__ import annotations

import base64
import stat
import struct
from pathlib import Path

import pytest

from scripts import install_mini_vps_release_authorized_key as key_installer
from scripts import install_mini_vps_release_client as installer
from scripts import mmx_vps_release as client
from scripts import render_mini_vps_release_authorized_key as renderer


ROOT = Path(__file__).resolve().parents[1]
RELAY = ROOT / "ops" / "executive_os" / "mini-vps-release-relay.sh"
INSTALL = ROOT / "ops" / "executive_os" / "install.sh"


def _ed25519_payload() -> str:
    key_type = b"ssh-ed25519"
    key_bytes = b"k" * 32
    blob = (
        struct.pack(">I", len(key_type))
        + key_type
        + struct.pack(">I", len(key_bytes))
        + key_bytes
    )
    return base64.b64encode(blob).decode("ascii")


def test_client_builds_only_fixed_m2_ssh_transport(tmp_path: Path) -> None:
    key = tmp_path / "m2_release"
    key.write_text("private-placeholder\n", encoding="utf-8")
    key.chmod(0o600)
    argv = client._ssh_argv("deploy " + "a" * 40 + " req-001", key)
    assert argv[0] == "/usr/bin/ssh"
    assert argv[1:3] == ["-F", "/dev/null"]
    assert argv[-2] == "m2studio"
    assert argv[-1] == "deploy " + "a" * 40 + " req-001"
    assert "chriswong" in argv
    assert "ClearAllForwardings=yes" in argv
    assert "IdentitiesOnly=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "-T" in argv


def test_client_command_contract_is_closed() -> None:
    parser = client._parser()
    preflight = parser.parse_args(["preflight"])
    assert client._remote_command(preflight, label="mini4") == ("preflight", 30)

    deploy = parser.parse_args(
        ["deploy", "--commit-sha", "a" * 40, "--request-id", "mini4-req-001"]
    )
    command, timeout = client._remote_command(deploy, label="mini4")
    assert command == "deploy " + "a" * 40 + " mini4-req-001"
    assert timeout == 720

    status = parser.parse_args(["status", "--request-id", "mini4-req-001"])
    assert client._remote_command(status, label="mini4") == ("status mini4-req-001", 30)

    with pytest.raises(ValueError):
        client._remote_command(
            parser.parse_args(
                ["deploy", "--commit-sha", "A" * 40, "--request-id", "mini4-req-001"]
            ),
            label="mini4",
        )
    with pytest.raises(ValueError):
        client._remote_command(
            parser.parse_args(["status", "--request-id", "../bad"]), label="mini4"
        )
    with pytest.raises(ValueError, match="bound to this mini"):
        client._remote_command(
            parser.parse_args(["status", "--request-id", "mini3-req-001"]), label="mini4"
        )


def test_client_key_requires_owner_mode_and_single_link(tmp_path: Path, monkeypatch) -> None:
    key = tmp_path / "m2_release"
    key.write_text("placeholder\n", encoding="utf-8")
    key.chmod(0o600)
    monkeypatch.setattr(client, "_KEY", key)
    assert client._key_path() == key
    key.chmod(0o644)
    with pytest.raises(RuntimeError, match="unsafe metadata"):
        client._key_path()


def test_relay_accepts_only_closed_forced_command_grammar() -> None:
    source = RELAY.read_text(encoding="utf-8")
    assert 'COMMAND="${SSH_ORIGINAL_COMMAND:-}"' in source
    assert '[[ "$LABEL" =~ ^mini[1-9][0-9]*$ ]]' in source
    assert '[[ "$request_id" == "$LABEL-"* ]]' in source
    assert "executive.vps.deploy_mastermind" in source
    assert "preflight" in source and "status" in source and "deploy" in source
    assert "eval " not in source
    assert "bash -c" not in source
    assert "sh -c" not in source
    assert "BASH_REMATCH" in source


def test_installer_publishes_stable_root_owned_relay_launcher() -> None:
    source = INSTALL.read_text(encoding="utf-8")
    assert 'MMX_VPS_RELEASE_RELAY="$SYSTEM_ROOT/bin/mmx-vps-release-relay"' in source
    assert "mini-vps-release-relay.sh" in source
    assert '/bin/chmod 0555 "$MMX_VPS_RELEASE_RELAY_TEMP"' in source


def _fake_source(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "mmx_vps_release.py").write_text("print('client')\n", encoding="utf-8")
    return root


def test_mini_client_installer_is_inert_without_release_key(tmp_path: Path) -> None:
    root = _fake_source(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    receipt = installer.install(source_root=root, home=home, require_key=False)
    assert receipt["key_ready"] is False
    assert Path(receipt["wrapper"]).is_file()
    assert Path(receipt["payload"]).is_file()

    with pytest.raises(installer.InstallError, match="not provisioned"):
        installer.install(source_root=root, home=home, require_key=True)


def test_mini_client_installer_accepts_preprovisioned_mode_600_key(tmp_path: Path) -> None:
    root = _fake_source(tmp_path)
    home = tmp_path / "home"
    key = home / ".ssh" / "m2_release"
    key.parent.mkdir(parents=True)
    key.write_text("placeholder\n", encoding="utf-8")
    key.chmod(0o600)
    known_hosts = home / ".ssh" / "known_hosts"
    known_hosts.write_text(
        f"m2studio ssh-ed25519 {_ed25519_payload()}\n", encoding="ascii"
    )
    known_hosts.chmod(0o600)

    receipt = installer.install(source_root=root, home=home, require_key=True)
    assert receipt["key_ready"] is True
    assert receipt["host_key_ready"] is True
    assert stat.S_IMODE(Path(receipt["wrapper"]).stat().st_mode) == 0o555


def test_mini_client_installer_requires_pinned_m2_host_key(tmp_path: Path) -> None:
    root = _fake_source(tmp_path)
    home = tmp_path / "home"
    key = home / ".ssh" / "m2_release"
    key.parent.mkdir(parents=True)
    key.write_text("placeholder\n", encoding="utf-8")
    key.chmod(0o600)

    with pytest.raises(installer.InstallError, match="host key"):
        installer.install(source_root=root, home=home, require_key=True)


def test_authorized_key_renderer_forces_stable_relay_and_restrictions(tmp_path: Path) -> None:
    payload = _ed25519_payload()
    public_key = tmp_path / "m2_release.pub"
    public_key.write_text(f"ssh-ed25519 {payload} generated\n", encoding="ascii")

    line = renderer.render(public_key, "mini4")

    assert line.startswith(
        'restrict,command="/Library/Application Support/MastermindExecutive/bin/mmx-vps-release-relay mini4" '
    )
    assert f"ssh-ed25519 {payload}" in line
    assert line.endswith("mastermind-release-mini4")


def test_authorized_key_renderer_rejects_non_ed25519_wire_blob(tmp_path: Path) -> None:
    public_key = tmp_path / "bad.pub"
    public_key.write_text(
        "ssh-ed25519 " + base64.b64encode(b"x" * 48).decode("ascii") + "\n",
        encoding="ascii",
    )
    with pytest.raises(renderer.RenderError, match="OpenSSH|Ed25519"):
        renderer.render(public_key, "mini4")


@pytest.mark.parametrize("label", ["mini", "m2", "mini 4", "../mini4", "Mini4"])
def test_authorized_key_renderer_rejects_unbounded_labels(tmp_path: Path, label: str) -> None:
    payload = _ed25519_payload()
    public_key = tmp_path / "key.pub"
    public_key.write_text(f"ssh-ed25519 {payload}\n", encoding="ascii")
    with pytest.raises(renderer.RenderError):
        renderer.render(public_key, label)


def test_m2_authorized_key_installer_is_idempotent_and_refuses_label_rebind(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(key_installer, "_assert_m2_operator", lambda: None)
    authorized = tmp_path / "authorized_keys"
    authorized.write_text("ssh-ed25519 existing existing\n", encoding="utf-8")
    authorized.chmod(0o600)

    payload = _ed25519_payload()
    public_key = tmp_path / "mini4.pub"
    public_key.write_text(f"ssh-ed25519 {payload}\n", encoding="ascii")

    first = key_installer.install(public_key, "mini4", path=authorized)
    second = key_installer.install(public_key, "mini4", path=authorized)
    assert first["changed"] is True
    assert second["changed"] is False
    assert authorized.read_text().count("mastermind-release-mini4") == 1

    other_blob = (
        struct.pack(">I", len(b"ssh-ed25519"))
        + b"ssh-ed25519"
        + struct.pack(">I", 32)
        + b"z" * 32
    )
    other = tmp_path / "other.pub"
    other.write_text(
        "ssh-ed25519 " + base64.b64encode(other_blob).decode("ascii") + "\n",
        encoding="ascii",
    )
    with pytest.raises(key_installer.InstallError, match="already owns"):
        key_installer.install(other, "mini4", path=authorized)
