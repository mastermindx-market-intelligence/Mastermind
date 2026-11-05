"""The APPLICATION reverse compiler and its thin entry.

The incumbent OS relay entry keeps its own constants, defaults and main
semantics. The APPLICATION purpose is a separately named closed compiler on the
same transport owner: purpose, host, destination, port, executable, command,
proxy, SOCKS remote and credential source are not selectable.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile

import pytest

from ops.executive_os import application_tunnel_entry
from ops.executive_os import os_tunnel_entry
from tests.test_application_tunnel_control import sealed_root  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
OS_CONFIG = {"schema": os_tunnel_entry.SCHEMA, "binary_sha256": "a" * 64,
             "server_fingerprint": "a" * 43 + "=", "relay_port": 49152}
OS_SECRET = b"mastermind-os:" + b"x" * 48
APP_CONFIG = {"schema": os_tunnel_entry.APPLICATION_SCHEMA, "binary_sha256": "b" * 64,
              "server_fingerprint": "b" * 43 + "="}
APP_SECRET = b"mastermind-fabric-app:" + b"y" * 48


def _isolated_entry(monkeypatch, *, isolated=1, argv=None, euid=0):
    """Explicit invocation data; not proof of actual root-owned file access."""
    stub = SimpleNamespace(
        argv=["application_tunnel_entry.py"] if argv is None else argv,
        flags=SimpleNamespace(isolated=isolated),
        dont_write_bytecode=1,
        stderr=sys.stderr,
    )
    monkeypatch.setattr(application_tunnel_entry, "sys", stub)
    monkeypatch.setattr(os, "geteuid", lambda: euid)
    return stub


def test_os_launch_spec_semantics_are_unchanged():
    binary, argv, env = os_tunnel_entry.launch_spec(OS_CONFIG, OS_SECRET)
    assert binary == str(os_tunnel_entry.ROOT / "transports/chisel" / ("a" * 64) / "chisel")
    assert argv == [binary, "client", "--fingerprint", OS_CONFIG["server_fingerprint"],
                    "--keepalive", "20s", os_tunnel_entry.SERVER,
                    "R:127.0.0.1:49152:127.0.0.1:8443"]
    assert env == {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": OS_SECRET.decode()}
    assert os_tunnel_entry.SCHEMA == "mastermind.os_public_tunnel.v1"
    assert os_tunnel_entry.CONFIG.name == "os-public-tunnel.json"
    assert os_tunnel_entry.CREDENTIAL.name == "os-public-tunnel.auth"


def test_application_reverse_fixes_the_exact_listener_and_native_target():
    binary, argv, env = os_tunnel_entry.application_launch_spec(APP_CONFIG, APP_SECRET)
    assert binary == str(os_tunnel_entry.ROOT / "transports/chisel" / ("b" * 64) / "chisel")
    assert argv == [binary, "client", "--fingerprint", APP_CONFIG["server_fingerprint"],
                    "--keepalive", "20s", os_tunnel_entry.SERVER,
                    "R:127.0.0.1:50142:127.0.0.1:4142"]
    assert env == {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": APP_SECRET.decode()}
    assert APP_SECRET.decode() not in json.dumps([binary, argv, APP_CONFIG])
    assert "8443" not in " ".join(argv)
    assert os_tunnel_entry.APPLICATION_RELAY_PORT == 50142
    assert os_tunnel_entry.APPLICATION_TARGET_PORT == 4142
    assert os_tunnel_entry.APPLICATION_REMOTE_REGEX == r"^R:127\.0\.0\.1:50142$"


def test_application_config_carries_no_port_host_or_executable_selector():
    for field, value in (("relay_port", 50142), ("target_port", 4142), ("server", "http://foreign"),
                         ("command", "sh"), ("executable", "/bin/sh"), ("credential", "inline"),
                         ("proxy", "socks5://x"), ("socks", True), ("remote", "R:0.0.0.0:1"),
                         ("purpose", "other"), ("label", "other")):
        config = {**APP_CONFIG, field: value}
        with pytest.raises(ValueError):
            os_tunnel_entry.application_launch_spec(config, APP_SECRET)


@pytest.mark.parametrize("field,value", [
    ("schema", "mastermind.os_public_tunnel.v1"), ("binary_sha256", "../escape"),
    ("binary_sha256", "B" * 64), ("server_fingerprint", ""), ("server_fingerprint", "unverified"),
    ("server_fingerprint", "a" * 42 + "="),
])
def test_application_configuration_refuses_a_malformed_or_foreign_value(field, value):
    config = {**APP_CONFIG, field: value}
    with pytest.raises(ValueError):
        os_tunnel_entry.application_launch_spec(config, APP_SECRET)


@pytest.mark.parametrize("secret", [
    b"", b"other:" + b"x" * 48, b"mastermind-os:" + b"x" * 48,
    APP_SECRET + b"\nextra", APP_SECRET + b"\x00", APP_SECRET + b" ",
    b"mastermind-fabric-app:short", b"mastermind-fabric-app:" + b"x" * 129,
    b"mastermind-fabric-app:" + b"x" * 31,
])
def test_application_credential_is_the_dedicated_fabric_app_identity(secret):
    with pytest.raises(ValueError):
        os_tunnel_entry.application_launch_spec(APP_CONFIG, secret)


def test_one_private_newline_is_accepted_without_mutating_the_grant():
    config = dict(APP_CONFIG)
    assert os_tunnel_entry.application_launch_spec(config, APP_SECRET + b"\n")[2]["AUTH"] \
        == APP_SECRET.decode()
    assert config == APP_CONFIG


def test_application_configuration_rejects_duplicate_and_nonfinite_json_before_secret(monkeypatch):
    _isolated_entry(monkeypatch)
    opened = []
    raw = json.dumps(APP_CONFIG).encode()
    duplicate = raw[:-1] + b', "schema": "mastermind.application_tunnel.v1"}'
    def read(path, **kwargs):
        opened.append(Path(path))
        assert Path(path) == application_tunnel_entry.CONFIG
        return duplicate
    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", read)
    assert application_tunnel_entry.main() == 1
    assert opened == [application_tunnel_entry.CONFIG]
    with pytest.raises(ValueError, match="nonfinite"):
        application_tunnel_entry._config(b'{"value": NaN}')


def test_application_entry_uses_only_the_fixed_application_paths():
    assert application_tunnel_entry.CONFIG.name == "application-tunnel.json"
    assert application_tunnel_entry.CREDENTIAL.name == "application-tunnel.auth"
    assert application_tunnel_entry.CONFIG != os_tunnel_entry.CONFIG
    assert application_tunnel_entry.CREDENTIAL != os_tunnel_entry.CREDENTIAL
    assert application_tunnel_entry.CONFIG.parent == os_tunnel_entry.CONFIG.parent
    source = (REPO / "ops/executive_os/application_tunnel_entry.py").read_text()
    assert "os-public-tunnel" not in source


def test_application_entry_opens_no_incumbent_os_file(monkeypatch):
    opened = []
    payload = b"chisel bytes"
    config = {**APP_CONFIG, "binary_sha256": hashlib.sha256(payload).hexdigest()}

    def fake_read(path, *, limit, private=False, acl_observer=None):
        opened.append(Path(path))
        if Path(path) == application_tunnel_entry.CONFIG:
            return json.dumps(config).encode()
        if Path(path) == application_tunnel_entry.CREDENTIAL:
            return APP_SECRET
        return payload

    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", fake_read)
    monkeypatch.setattr(os, "execve", lambda binary, argv, env: None)
    _isolated_entry(monkeypatch)
    assert application_tunnel_entry.main() == 0
    assert application_tunnel_entry.CONFIG in opened
    assert application_tunnel_entry.CREDENTIAL in opened
    assert os_tunnel_entry.CONFIG not in opened
    assert os_tunnel_entry.CREDENTIAL not in opened


def test_application_entry_refuses_a_non_root_caller(monkeypatch):
    _isolated_entry(monkeypatch, euid=1000)
    assert application_tunnel_entry.main() == 1


def test_application_entry_refuses_extra_arguments(monkeypatch):
    _isolated_entry(monkeypatch, argv=["application_tunnel_entry.py", "--anything"])
    assert application_tunnel_entry.main() == 1


def test_application_entry_refuses_a_non_isolated_interpreter(monkeypatch):
    _isolated_entry(monkeypatch, isolated=0)
    assert application_tunnel_entry.main() == 1


def test_application_entry_refuses_a_binary_that_changed(monkeypatch):
    config = {**APP_CONFIG, "binary_sha256": "b" * 64}
    opened = []
    executed = []

    def fake_read(path, *, limit, private=False, acl_observer=None):
        opened.append(Path(path))
        if Path(path) == application_tunnel_entry.CONFIG:
            return json.dumps(config).encode()
        if Path(path) == application_tunnel_entry.CREDENTIAL:
            return APP_SECRET
        return b"different bytes"

    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", fake_read)
    monkeypatch.setattr(os, "execve", lambda *args: executed.append(args))
    _isolated_entry(monkeypatch)
    assert application_tunnel_entry.main() == 1
    assert opened[:2] == [application_tunnel_entry.CONFIG, application_tunnel_entry.CREDENTIAL]
    assert len(opened) == 3
    assert executed == []


@pytest.mark.parametrize("failure", ["directory", "file", "observer"])
def test_actual_application_reader_checks_descriptor_acls_before_secret_use(sealed_root, monkeypatch, failure):
    with tempfile.TemporaryDirectory(prefix="entry-acl-", dir=sealed_root) as directory:
        parent = Path(directory)
        config = parent / "application-tunnel.json"
        config.write_text(json.dumps(APP_CONFIG))
        config.chmod(0o444)
        credential = parent / "application-tunnel.auth"
        observed = []
        def acl(path, *, expected_identity, descriptor):
            path = Path(path)
            actual = os.fstat(descriptor)
            assert (actual.st_dev, actual.st_ino) == (expected_identity.st_dev, expected_identity.st_ino)
            observed.append(path)
            if failure == "observer" and path == config:
                raise application_tunnel_entry.FilesystemSecurityError("synthetic observer failure")
            return path == (parent if failure == "directory" else config)
        monkeypatch.setattr(application_tunnel_entry, "has_macos_acl", acl)
        monkeypatch.setattr(application_tunnel_entry, "CONFIG", config)
        monkeypatch.setattr(application_tunnel_entry, "CREDENTIAL", credential)
        _isolated_entry(monkeypatch)
        monkeypatch.setattr(os, "execve", lambda *a: pytest.fail("exec after ACL refusal"))
        assert application_tunnel_entry.main() == 1
        assert parent in observed
        assert credential not in observed


def test_actual_application_reader_accepts_owned_private_file_without_acl(sealed_root, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="entry-private-", dir=sealed_root) as directory:
        path = Path(directory) / "application-tunnel.auth"
        # This reader checks ownership, permissions and descriptor ACLs.
        # Dedicated credential syntax is covered by the launch-spec tests above.
        fixture_payload = b"private reader fixture"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o400)
            handle.write(fixture_payload)
        observed = []
        def acl(node, *, expected_identity, descriptor):
            observed.append(Path(node))
            assert os.fstat(descriptor).st_ino == expected_identity.st_ino
            return False
        monkeypatch.setattr(application_tunnel_entry, "has_macos_acl", acl)
        assert application_tunnel_entry._read_application_sealed(path, limit=1024, private=True) == fixture_payload
        assert observed.count(path) == 2
