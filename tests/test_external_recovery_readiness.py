"""Tests for the read-only external recovery-route probe."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ops.executive_os.external_recovery_readiness import (
    SCHEMA,
    ExternalRecoveryProbeError,
    build_route_spec,
    canonical_json,
    gateway_command,
    probe_external_recovery,
    target_command,
)


def _identity(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    ssh = home / ".ssh"
    ssh.mkdir(parents=True)
    key = ssh / "recovery_ed25519"
    key.write_text("test-key-material\n", encoding="utf-8")
    key.chmod(0o600)
    return home, key


def _spec(tmp_path: Path):
    home, key = _identity(tmp_path)
    return build_route_spec(
        route_ref="route-" + "a" * 64,
        gateway_host="gateway.ts.net",
        gateway_user="operator",
        gateway_host_key_alias="100.64.0.8",
        target_host="worker.local",
        target_user="worker",
        identity_file=str(key),
        target_host_key_alias="worker-trust",
        home=home,
    )


def _completed(command, rc: int, stderr: bytes = b""):
    return subprocess.CompletedProcess(command, rc, b"", stderr)


class QueueRunner:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def __call__(self, command):
        self.calls.append(list(command))
        rc, stderr = self.rows.pop(0)
        return _completed(command, rc, stderr)


def test_commands_are_public_key_only_strict_and_fixed(tmp_path: Path) -> None:
    spec = _spec(tmp_path)

    gateway = gateway_command(spec)
    target = target_command(spec)

    assert gateway[0] == "/usr/bin/ssh"
    assert gateway[-1] == "/usr/bin/true"
    assert "BatchMode=yes" in gateway
    assert "PasswordAuthentication=no" in gateway
    assert "KbdInteractiveAuthentication=no" in gateway
    assert "PreferredAuthentications=publickey" in gateway
    assert "StrictHostKeyChecking=yes" in gateway
    assert "UpdateHostKeys=no" in gateway
    assert "HostKeyAlias=100.64.0.8" in gateway

    assert target[0] == "/usr/bin/ssh"
    assert "HostKeyAlias=worker-trust" in target
    assert target[-1] == "/usr/bin/true"
    proxy = next(value for value in target if value.startswith("ProxyCommand="))
    assert "/usr/bin/ssh" in proxy
    assert "BatchMode=yes" in proxy
    assert "PasswordAuthentication=no" in proxy
    assert "StrictHostKeyChecking=yes" in proxy
    assert "UpdateHostKeys=no" in proxy
    assert "-W %h:%p" in proxy


def test_ready_requires_both_gateway_and_target_key_auth(tmp_path: Path) -> None:
    runner = QueueRunner([(0, b""), (0, b"")])
    report = probe_external_recovery(
        _spec(tmp_path), runner=runner, now_ms=lambda: 123
    )

    assert report == {
        "schema": SCHEMA,
        "route_ref": "route-" + "a" * 64,
        "observed_at_ms": 123,
        "route_state": "READY",
        "human_secret_required": False,
        "gateway": {
            "status": "OK",
            "code": "GATEWAY_PUBLIC_KEY_AUTH_OK",
        },
        "target": {
            "status": "OK",
            "code": "TARGET_PUBLIC_KEY_AUTH_OK",
        },
    }
    assert len(runner.calls) == 2


def test_target_key_refusal_is_human_recovery_not_offline(tmp_path: Path) -> None:
    runner = QueueRunner(
        [
            (0, b""),
            (
                255,
                b"worker@worker.local: Permission denied "
                b"(publickey,password,keyboard-interactive).\r\n",
            ),
        ]
    )
    report = probe_external_recovery(
        _spec(tmp_path), runner=runner, now_ms=lambda: 456
    )

    assert report["route_state"] == "HUMAN_RECOVERY_REQUIRED"
    assert report["human_secret_required"] is True
    assert report["gateway"]["code"] == "GATEWAY_PUBLIC_KEY_AUTH_OK"
    assert report["target"] == {
        "status": "HUMAN_ACTION",
        "code": "TARGET_SSH_REACHABLE_KEY_AUTH_UNAVAILABLE",
    }


@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        (b"Host key verification failed.\r\n", "GATEWAY_HOST_KEY_REFUSED"),
        (
            b"ssh: Could not resolve hostname gateway.ts.net: nodename nor servname provided\r\n",
            "GATEWAY_NAME_RESOLUTION_FAILED",
        ),
        (b"ssh: connect to host gateway port 22: Operation timed out\r\n", "GATEWAY_UNREACHABLE"),
        (b"operator@gateway: Permission denied (publickey).\r\n", "GATEWAY_PUBLIC_KEY_AUTH_REFUSED"),
    ],
)
def test_gateway_failure_blocks_target_probe(
    tmp_path: Path, stderr: bytes, code: str
) -> None:
    runner = QueueRunner([(255, stderr)])
    report = probe_external_recovery(_spec(tmp_path), runner=runner)

    assert report["route_state"] == "NOT_READY"
    assert report["human_secret_required"] is False
    assert report["gateway"]["code"] == code
    assert report["target"] == {
        "status": "SKIPPED",
        "code": "TARGET_NOT_PROBED",
    }
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        (b"Host key verification failed.\r\n", "TARGET_HOST_KEY_REFUSED"),
        (
            b"ssh: Could not resolve hostname worker.local: nodename nor servname provided\r\n",
            "TARGET_NAME_RESOLUTION_FAILED",
        ),
        (
            b"Connection timed out during banner exchange\r\n",
            "TARGET_SSH_UNREACHABLE",
        ),
        (b"ssh: connect to host worker.local port 22: Connection refused\r\n", "TARGET_SSH_UNREACHABLE"),
    ],
)
def test_target_route_failures_are_not_ready(
    tmp_path: Path, stderr: bytes, code: str
) -> None:
    runner = QueueRunner([(0, b""), (255, stderr)])
    report = probe_external_recovery(_spec(tmp_path), runner=runner)

    assert report["route_state"] == "NOT_READY"
    assert report["human_secret_required"] is False
    assert report["target"]["code"] == code


def test_unknown_failure_fails_closed_without_raw_stderr(tmp_path: Path) -> None:
    secretish = b"unexpected provider detail private-token-value"
    runner = QueueRunner([(0, b""), (255, secretish)])
    report = probe_external_recovery(_spec(tmp_path), runner=runner)

    assert report["route_state"] == "UNKNOWN"
    payload = canonical_json(report)
    assert b"private-token-value" not in payload
    assert b"gateway.ts.net" not in payload
    assert b"worker.local" not in payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gateway_host", "gateway;touch /tmp/x"),
        ("gateway_user", "operator $(id)"),
        ("target_host", "-oProxyCommand=bad"),
        ("target_user", "worker@evil"),
        ("gateway_host_key_alias", "alias with spaces"),
        ("target_host_key_alias", "alias with spaces"),
    ],
)
def test_route_tokens_reject_shell_or_ssh_option_injection(
    tmp_path: Path, field: str, value: str
) -> None:
    home, key = _identity(tmp_path)
    values = {
        "route_ref": None,
        "gateway_host": "gateway.ts.net",
        "gateway_user": "operator",
        "gateway_host_key_alias": "100.64.0.8",
        "target_host": "worker.local",
        "target_user": "worker",
        "target_host_key_alias": "worker-trust",
        "identity_file": str(key),
        "home": home,
    }
    values[field] = value

    with pytest.raises(ExternalRecoveryProbeError) as excinfo:
        build_route_spec(**values)
    assert str(excinfo.value) == "REFERENCE_INVALID"


def test_identity_must_be_private_regular_file_directly_under_ssh(
    tmp_path: Path,
) -> None:
    home, key = _identity(tmp_path)

    key.chmod(0o644)
    with pytest.raises(ExternalRecoveryProbeError) as excinfo:
        build_route_spec(
            route_ref=None,
            gateway_host="gateway",
            gateway_user="operator",
            gateway_host_key_alias=None,
            target_host="worker",
            target_user="worker",
            identity_file=str(key),
            home=home,
        )
    assert str(excinfo.value) == "IDENTITY_FILE_INVALID"

    key.chmod(0o600)
    nested = home / ".ssh" / "nested"
    nested.mkdir()
    nested_key = nested / "key"
    nested_key.write_text("x", encoding="utf-8")
    nested_key.chmod(0o600)
    with pytest.raises(ExternalRecoveryProbeError) as excinfo:
        build_route_spec(
            route_ref=None,
            gateway_host="gateway",
            gateway_user="operator",
            gateway_host_key_alias=None,
            target_host="worker",
            target_user="worker",
            identity_file=str(nested_key),
            home=home,
        )
    assert str(excinfo.value) == "IDENTITY_FILE_INVALID"


def test_identity_symlink_is_refused(tmp_path: Path) -> None:
    home, key = _identity(tmp_path)
    link = home / ".ssh" / "link"
    link.symlink_to(key)

    with pytest.raises(ExternalRecoveryProbeError) as excinfo:
        build_route_spec(
            route_ref=None,
            gateway_host="gateway",
            gateway_user="operator",
            gateway_host_key_alias=None,
            target_host="worker",
            target_user="worker",
            identity_file=str(link),
            home=home,
        )
    assert str(excinfo.value) == "IDENTITY_FILE_INVALID"


def test_canonical_json_is_deterministic_and_closed(tmp_path: Path) -> None:
    runner = QueueRunner([(0, b""), (0, b"")])
    report = probe_external_recovery(
        _spec(tmp_path), runner=runner, now_ms=lambda: 789
    )

    payload = canonical_json(report)
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")
    assert json.loads(payload) == report
    assert payload == (
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
