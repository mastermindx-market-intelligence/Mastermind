from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops" / "executive_os" / "fleet_filevault_unlock.sh"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_shell_syntax_is_valid() -> None:
    result = subprocess.run(
        ["/bin/bash", "-n", str(SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_is_closed_to_four_enrolled_minis() -> None:
    text = _source()
    assert 'if [ "$#" -ne 1 ]' in text
    assert 'mini1|mini2|mini3|mini4) HOST="$1"' in text
    assert 'ALIAS="mmx-$HOST"' in text
    for forbidden in (
        "--host",
        "--user",
        "--password",
        "--identity",
        "--command",
        "--port",
        "--proxy",
    ):
        assert forbidden not in text


def test_password_boundary_is_interactive_only() -> None:
    text = _source()
    assert '[ ! -t 0 ] || [ ! -t 1 ]' in text
    assert "INTERACTIVE_TTY_REQUIRED" in text
    assert "unset SSH_ASKPASS SSH_ASKPASS_REQUIRE DISPLAY" in text
    assert text.count("BatchMode=no") == 1
    assert text.count("NumberOfPasswordPrompts=1") == 1
    assert "security find-" not in text
    assert "sshpass" not in text
    assert "password=" not in text.lower()


def test_preboot_must_be_proven_before_interactive_effect() -> None:
    text = _source()
    preflight = text.index("PASSWORD_AUTH_NOT_ADVERTISED")
    interactive = text.index("BatchMode=no")
    assert preflight < interactive
    assert "INTERACTIVE_AUTH_NOT_ADVERTISED" in text[preflight:interactive]
    assert '"$HOST.local" 5900' in text[preflight:interactive]
    assert '"$HOST.local" 3283' in text[preflight:interactive]
    assert "GUI_RECOVERY_REACHABLE" in text[preflight:interactive]


def test_host_identity_is_fail_closed() -> None:
    text = _source()
    assert text.count("StrictHostKeyChecking=yes") >= 2
    assert "StrictHostKeyChecking=accept-new" not in text
    assert "StrictHostKeyChecking=no" not in text
    assert "UserKnownHostsFile=/dev/null" not in text


def test_unlock_is_never_replayed_and_reconciles_with_key_auth() -> None:
    text = _source()
    effect = text.index("BatchMode=no")
    reconcile = text.index("for attempt in {1..24}", effect)
    assert text.count("BatchMode=no", effect, reconcile) == 1
    assert "BatchMode=no" not in text[reconcile:]
    assert '"$SSH" "${SSH_COMMON[@]}" "$ALIAS" /usr/bin/true' in text[reconcile:]
    assert "UNLOCK_CONFIRMED" in text[reconcile:]
    assert "UNLOCK_EFFECT_UNKNOWN" in text[reconcile:]
    assert "exit 75" in text[reconcile:]


def _patched_script(
    tmp_path: Path,
    *,
    ssh_body: str,
    nc_body: str = "#!/bin/sh\nexit 1\n",
) -> Path:
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_text(ssh_body, encoding="utf-8")
    fake_ssh.chmod(0o755)
    fake_nc = tmp_path / "nc"
    fake_nc.write_text(nc_body, encoding="utf-8")
    fake_nc.chmod(0o755)
    script = _source()
    script = script.replace('SSH="/usr/bin/ssh"', f'SSH="{fake_ssh}"')
    script = script.replace('NC="/usr/bin/nc"', f'NC="{fake_nc}"')
    script = script.replace(
        'DEBUG_LOG="$($MKTEMP "/private/tmp/mastermind-filevault-preflight.$HOST.XXXXXX")"',
        f'DEBUG_LOG="{tmp_path}/debug.log"',
    )
    path = tmp_path / "unlock.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_already_booted_short_circuits_without_password(tmp_path: Path) -> None:
    script = _patched_script(
        tmp_path,
        ssh_body="#!/bin/sh\nexit 0\n",
    )
    result = subprocess.run(
        ["/bin/bash", str(script), "mini2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "ALREADY_BOOTED host=mini2" in result.stdout
    assert "Enter the mini2 login password" not in result.stdout


def test_plain_key_failure_is_not_promoted_to_filevault(tmp_path: Path) -> None:
    script = _patched_script(
        tmp_path,
        ssh_body=(
            "#!/bin/sh\n"
            "echo 'debug1: Authentications that can continue: publickey' >&2\n"
            "echo 'Permission denied (publickey).' >&2\n"
            "exit 255\n"
        ),
    )
    result = subprocess.run(
        ["/bin/bash", str(script), "mini2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 65
    assert "PASSWORD_AUTH_NOT_ADVERTISED" in result.stderr
    assert "Enter the mini2 login password" not in result.stdout


def test_preboot_signature_without_tty_stops_before_password_effect(
    tmp_path: Path,
) -> None:
    script = _patched_script(
        tmp_path,
        ssh_body=(
            "#!/bin/sh\n"
            "echo 'debug1: Authentications that can continue: publickey,password,keyboard-interactive' >&2\n"
            "echo 'Permission denied (publickey,password,keyboard-interactive).' >&2\n"
            "exit 255\n"
        ),
    )
    result = subprocess.run(
        ["/bin/bash", str(script), "mini2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 66
    assert "FILEVAULT_PREBOOT_CONFIRMED_FOR_INTERACTIVE_UNLOCK" in result.stdout
    assert "INTERACTIVE_TTY_REQUIRED" in result.stderr


def test_gui_reachable_refuses_preboot_unlock(tmp_path: Path) -> None:
    script = _patched_script(
        tmp_path,
        ssh_body=(
            "#!/bin/sh\n"
            "echo 'debug1: Authentications that can continue: publickey,password,keyboard-interactive' >&2\n"
            "exit 255\n"
        ),
        nc_body="#!/bin/sh\nexit 0\n",
    )
    result = subprocess.run(
        ["/bin/bash", str(script), "mini2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 65
    assert "GUI_RECOVERY_REACHABLE" in result.stderr
    assert "Enter the mini2 login password" not in result.stdout
