"""Static, Linux-safe checks for dedicated macOS worker authentication."""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "provision-worker-auth.sh"
RUNBOOK = ROOT / "ops" / "executive_os" / "HOST_PREREQUISITES.md"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_worker_auth_provisioner_is_executable_and_syntax_valid() -> None:
    assert stat.S_IMODE(SCRIPT.stat().st_mode) & 0o111
    completed = subprocess.run(
        ["/bin/bash", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_worker_auth_provisioner_uses_only_dedicated_device_login() -> None:
    source = _source()
    assert 'WORKER_USER="_mastermind_worker"' in source
    assert 'PROVIDER_HOME="/var/db/mastermind-executive/workers/codex-01/provider-home"' in source
    assert "/usr/bin/env -i" in source
    assert 'HOME="$PROVIDER_HOME"' in source
    assert 'CODEX_HOME="$PROVIDER_HOME"' in source
    assert 'run_codex_as_worker login --device-auth' in source
    assert "cli_auth_credentials_store=" in source
    assert "</dev/tty >/dev/tty 2>/dev/tty" in source
    assert "/usr/bin/sudo -n -u \"$WORKER_USER\" -g \"$WORKER_GROUP\"" in source

    # Provisioning must never import the operator's existing login or accept a
    # secret through stdin/argv. The official device flow creates the file.
    forbidden = (
        'cp "$AUTH_PATH"',
        'ditto "$AUTH_PATH"',
        "auth.json).read",
        "OPENAI_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "--with-api-key",
        "--with-access-token",
    )
    assert not any(token in source for token in forbidden)


def test_worker_auth_provisioner_pins_official_native_codex() -> None:
    source = _source()
    assert 'CODEX_VERSION="0.147.0"' in source
    assert 'CODEX_TEAM_ID="2DC432GLL2"' in source
    assert (
        'CODEX_SHA256="19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"'
        in source
    )
    assert "/aarch64-apple-darwin/bin/codex" in source
    assert "/usr/bin/codesign --verify --strict" in source
    assert "TeamIdentifier" in source
    assert "^Mach-O " in source
    assert 'OBSERVED_VERSION="$(run_codex_as_worker --version' in source
    assert '/usr/bin/ditto --noqtn "$CODEX_BINARY" "$PINNED_CODEX_BINARY"' in source
    assert '"0:0:555:1"' in source
    assert '"$PINNED_CODEX_BINARY" "$@"' in source
    assert '"$CODEX_BINARY" --version' not in source
    assert '"$PINNED_CODEX_BINARY" --version' not in source
    assert 'OBSERVED_SHA256="$(/usr/bin/shasum -a 256 "$PINNED_CODEX_BINARY"' in source


def test_worker_auth_verification_is_strict_and_non_disclosing() -> None:
    source = _source()
    assert "--verify-only" in source
    assert 'verify_auth_metadata' in source
    assert 'verify_login_without_output' in source
    assert 'verify_complete_auth' in source
    complete_auth = source.split("verify_complete_auth() {", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert complete_auth.count("verify_auth_metadata") == 2
    assert complete_auth.index("verify_login_without_output") < complete_auth.rindex(
        "verify_auth_metadata"
    )
    assert "run_codex_as_worker login status" in source
    assert "cli_auth_credentials_store=" in source
    assert ">/dev/null 2>&1" in source
    assert '"$WORKER_UID:$WORKER_GID:600:1"' in source
    assert "regular non-symlink file" in source
    assert "unexpected filesystem ACL" in source
    assert "auth file is empty" in source

    # Metadata is enough for the shell; Codex validates the opaque credential.
    # The helper must not place credential bytes on stdout or stderr.
    assert "auth.json" in source
    forbidden_auth_reads = (
        '/bin/cat "$AUTH_PATH"',
        '/usr/bin/cat "$AUTH_PATH"',
        '/usr/bin/jq "$AUTH_PATH"',
        '/usr/bin/sed "$AUTH_PATH"',
        '/usr/bin/grep "$AUTH_PATH"',
        '/usr/bin/head "$AUTH_PATH"',
    )
    assert not any(command in source for command in forbidden_auth_reads)


def test_worker_auth_provisioning_requires_root_macos_and_bootstrap_identity() -> None:
    source = _source()
    assert '"$(/usr/bin/id -u)" -eq 0' in source
    assert '"$(/usr/bin/uname -s)" = "Darwin"' in source
    assert "run bootstrap-host.sh first" in source
    assert "NFSHomeDirectory" in source
    assert 'UserShell)" = "/usr/bin/false"' in source
    assert "AuthenticationAuthority" in source
    assert '"$WORKER_UID:$WORKER_GID:700"' in source


def test_administrator_runbook_explains_bounded_worker_device_login() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "## Stage 1" in runbook and "### Dedicated worker authentication" in runbook
    assert "provision-worker-auth.sh" in runbook
    assert "--verify-only" in runbook
    assert "_mastermind_worker:_mastermind_worker" in runbook
    assert "non-symlink" in runbook and "mode `0600`" in runbook
    assert "never reads or copies" in runbook
    assert "personal `~/.codex/auth.json`" in runbook
    assert "Do not paste a token, API key" in runbook
