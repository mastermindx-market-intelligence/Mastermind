from __future__ import annotations

import base64
import hashlib
import subprocess
from pathlib import Path

import pytest

from ops.executive_os import fleet_recovery_reachability as probe
from ops.executive_os.fleet_recovery_reachability import (
    EXPECTED_GATEWAY_FINGERPRINT,
    GATEWAY_KEY_BASENAME,
    HOSTS,
    PROBE_PORTS,
    ReachabilityProbeError,
    SshAuthObservation,
    SshConfig,
    _classify_ssh_failure,
    _parse_auth_methods,
    _fingerprint_public_key,
    _resolve_ssh_config,
    main,
    observe,
)


def _public_key_line(payload: bytes = b"test-public-key-blob") -> tuple[str, str]:
    encoded = base64.b64encode(payload).decode("ascii")
    digest = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii").rstrip("=")
    return f"ssh-ed25519 {encoded} test-key\n", f"SHA256:{digest}"


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    ssh = home / ".ssh"
    ssh.mkdir(parents=True)
    line, fingerprint = _public_key_line()
    (ssh / f"{GATEWAY_KEY_BASENAME}.pub").write_text(line, encoding="utf-8")
    (ssh / "known_hosts").write_text("", encoding="utf-8")
    monkeypatch.setattr(probe, "EXPECTED_GATEWAY_FINGERPRINT", fingerprint)
    return home


def _config(alias: str, home: Path) -> SshConfig:
    number = alias.removeprefix("mmx-mini")
    return SshConfig(
        alias=alias,
        hostname=f"mini{number}.local",
        user=f"mini{number}",
        identity_file=f"~/.ssh/{GATEWAY_KEY_BASENAME}",
        identities_only=True,
    )


def test_closed_host_and_port_contract() -> None:
    assert HOSTS == (
        ("mini1", "mmx-mini1", "mini1"),
        ("mini2", "mmx-mini2", "mini2"),
        ("mini3", "mmx-mini3", "mini3"),
        ("mini4", "mmx-mini4", "mini4"),
    )
    assert PROBE_PORTS == {
        "ssh": 22,
        "screen_sharing": 5900,
        "apple_remote_desktop": 3283,
    }
    assert EXPECTED_GATEWAY_FINGERPRINT.startswith("SHA256:")


def test_public_key_fingerprint_is_openssh_sha256(tmp_path: Path) -> None:
    line, expected = _public_key_line(b"known-payload")
    path = tmp_path / "gateway.pub"
    path.write_text(line, encoding="utf-8")
    assert _fingerprint_public_key(path) == expected


@pytest.mark.parametrize(
    "content,code",
    [
        ("", "GATEWAY_PUBLIC_KEY_INVALID"),
        ("ssh-rsa AAAA bad\n", "GATEWAY_PUBLIC_KEY_INVALID"),
        ("ssh-ed25519 *** bad\n", "GATEWAY_PUBLIC_KEY_INVALID"),
    ],
)
def test_public_key_rejects_invalid_material(
    tmp_path: Path, content: str, code: str
) -> None:
    path = tmp_path / "bad.pub"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ReachabilityProbeError, match=code):
        _fingerprint_public_key(path)


def test_ssh_config_resolution_is_closed_and_exact(tmp_path: Path) -> None:
    home = tmp_path / "home"
    seen: list[list[str]] = []

    def runner(argv, **kwargs):
        seen.append(list(argv))
        return subprocess.CompletedProcess(
            argv,
            0,
            (
                b"user mini2\n"
                b"hostname mini2.local\n"
                b"identitiesonly yes\n"
                b"stricthostkeychecking accept-new\n"
                b"identityfile ~/.ssh/mastermind_fleet_gateway_ed25519\n"
            ),
            b"",
        )

    value = _resolve_ssh_config("mmx-mini2", home=home, runner=runner)
    assert value == SshConfig(
        alias="mmx-mini2",
        hostname="mini2.local",
        user="mini2",
        identity_file="~/.ssh/mastermind_fleet_gateway_ed25519",
        identities_only=True,
    )
    assert seen == [["/usr/bin/ssh", "-G", "mmx-mini2"]]


@pytest.mark.parametrize(
    "returncode,stderr,expected",
    [
        (0, b"", "PASS"),
        (255, b"mini2@mini2.local: Permission denied (publickey).", "KEY_REJECTED"),
        (255, b"Host key verification failed.", "HOST_IDENTITY_REJECTED"),
        (255, b"connect to host mini2.local port 22: Connection refused", "TRANSPORT_UNAVAILABLE"),
        (255, b"ssh: connect to host mini2.local port 22: Operation timed out", "TIMEOUT"),
        (255, b"unexpected diagnostic", "PROBE_ERROR"),
    ],
)
def test_ssh_failure_classifier_is_bounded(
    returncode: int, stderr: bytes, expected: str
) -> None:
    assert _classify_ssh_failure(returncode, stderr) == expected


def test_auth_methods_are_bounded_and_deduplicated() -> None:
    stderr = (
        b"debug1: Authentications that can continue: publickey,password,keyboard-interactive\n"
        b"debug1: Authentications that can continue: publickey,password,keyboard-interactive\n"
    )
    assert _parse_auth_methods(stderr) == (
        "keyboard-interactive",
        "password",
        "publickey",
    )


def test_all_ready_requires_exact_key_auth_and_redundant_gui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)

    def resolver(alias: str, *, home: Path) -> SshConfig:
        return _config(alias, home)

    def tcp(hostname: str, port: int) -> str:
        assert hostname.startswith("mini")
        return "OPEN"

    def auth(config: SshConfig, *, home: Path) -> SshAuthObservation:
        assert config.identity_file.endswith(GATEWAY_KEY_BASENAME)
        return SshAuthObservation("PASS", ("publickey",))

    report = observe(
        home=home,
        resolver=resolver,
        tcp_probe=tcp,
        auth_probe=auth,
        now_ms=lambda: 1234,
    )
    assert report["state"] == "READY"
    assert report["degraded_hosts"] == []
    assert report["observed_at_ms"] == 1234
    assert all(row["recovery_state"] == "READY" for row in report["hosts"].values())


def test_mini2_incident_is_not_false_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)

    def resolver(alias: str, *, home: Path) -> SshConfig:
        return _config(alias, home)

    def tcp(hostname: str, port: int) -> str:
        if hostname == "mini2.local" and port in (5900, 3283):
            return "CLOSED"
        return "OPEN"

    def auth(config: SshConfig, *, home: Path) -> SshAuthObservation:
        if config.alias == "mmx-mini2":
            return SshAuthObservation(
                "KEY_REJECTED",
                ("keyboard-interactive", "password", "publickey"),
            )
        return SshAuthObservation("PASS", ("publickey",))

    report = observe(
        home=home,
        resolver=resolver,
        tcp_probe=tcp,
        auth_probe=auth,
        now_ms=lambda: 5678,
    )

    assert report["state"] == "DEGRADED"
    assert report["degraded_hosts"] == ["mini2"]
    mini2 = report["hosts"]["mini2"]
    assert mini2["ssh_listener"] == "OPEN"
    assert mini2["ssh_key_auth"] == "KEY_REJECTED"
    assert mini2["screen_sharing"] == "CLOSED"
    assert mini2["apple_remote_desktop"] == "CLOSED"
    assert mini2["recovery_state"] == "DEGRADED"
    assert mini2["preboot_suspected"] is True
    assert mini2["ssh_auth_methods"] == [
        "keyboard-interactive",
        "password",
        "publickey",
    ]
    assert "SSH_KEY_AUTH_KEY_REJECTED" in mini2["issues"]
    assert "SCREEN_SHARING_UNREACHABLE" in mini2["issues"]
    assert "APPLE_REMOTE_DESKTOP_UNREACHABLE" in mini2["issues"]
    assert "FILEVAULT_PREBOOT_SUSPECTED" in mini2["issues"]


def test_publickey_only_rejection_is_not_misclassified_as_preboot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)

    def tcp(hostname: str, port: int) -> str:
        if hostname == "mini2.local" and port in (5900, 3283):
            return "CLOSED"
        return "OPEN"

    def auth(config: SshConfig, *, home: Path) -> SshAuthObservation:
        if config.alias == "mmx-mini2":
            return SshAuthObservation("KEY_REJECTED", ("publickey",))
        return SshAuthObservation("PASS", ("publickey",))

    report = observe(
        home=home,
        resolver=lambda alias, *, home: _config(alias, home),
        tcp_probe=tcp,
        auth_probe=auth,
    )
    mini2 = report["hosts"]["mini2"]
    assert mini2["recovery_state"] == "DEGRADED"
    assert mini2["preboot_suspected"] is False
    assert "FILEVAULT_PREBOOT_SUSPECTED" not in mini2["issues"]
    assert "SSH_KEY_AUTH_KEY_REJECTED" in mini2["issues"]


def test_one_gui_route_is_sufficient_when_ssh_recovery_is_proven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)

    def tcp(hostname: str, port: int) -> str:
        return "CLOSED" if port == 3283 else "OPEN"

    report = observe(
        home=home,
        resolver=lambda alias, *, home: _config(alias, home),
        tcp_probe=tcp,
        auth_probe=lambda config, *, home: SshAuthObservation(
            "PASS", ("publickey",)
        ),
    )
    assert report["state"] == "READY"
    assert all(row["recovery_state"] == "READY" for row in report["hosts"].values())
    assert all(
        "APPLE_REMOTE_DESKTOP_UNREACHABLE" in row["issues"]
        for row in report["hosts"].values()
    )


def test_wrong_alias_identity_refuses_without_network_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)
    called = 0

    def tcp(hostname: str, port: int) -> str:
        nonlocal called
        called += 1
        return "OPEN"

    def resolver(alias: str, *, home: Path) -> SshConfig:
        value = _config(alias, home)
        if alias == "mmx-mini2":
            return SshConfig(
                alias=alias,
                hostname=value.hostname,
                user=value.user,
                identity_file="~/.ssh/not-the-gateway-key",
                identities_only=True,
            )
        return value

    report = observe(
        home=home,
        resolver=resolver,
        tcp_probe=tcp,
        auth_probe=lambda config, *, home: SshAuthObservation(
            "PASS", ("publickey",)
        ),
    )
    assert report["state"] == "DEGRADED"
    assert report["hosts"]["mini2"]["ssh_config"] == "INVALID"
    assert report["hosts"]["mini2"]["issues"] == ["SSH_CONFIG_INVALID"]
    # Three valid hosts x three ports.  The invalid host opens no socket.
    assert called == 9


def test_wrong_gateway_public_key_fails_closed_before_host_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, "EXPECTED_GATEWAY_FINGERPRINT", "SHA256:not-the-key")

    with pytest.raises(ReachabilityProbeError, match="GATEWAY_KEY_IDENTITY_MISMATCH"):
        observe(
            home=home,
            resolver=lambda alias, *, home: pytest.fail("resolver must not run"),
            tcp_probe=lambda hostname, port: pytest.fail("tcp probe must not run"),
            auth_probe=lambda config, *, home: pytest.fail("auth probe must not run"),
        )


def test_cli_refuses_arguments_without_observation(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--host", "mini2"]) == 64
    captured = capsys.readouterr()
    assert "accepts no arguments" in captured.err
    assert captured.out == ""


def test_source_uses_no_shell_and_returns_no_raw_ssh_stderr() -> None:
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "os.system" not in source
    assert '.decode("utf-8"' in source
    assert '"stderr"' not in source
