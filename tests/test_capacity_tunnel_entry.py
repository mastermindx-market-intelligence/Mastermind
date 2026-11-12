"""The additive CAPACITY reverse compiler and its thin entry.

The OS-public relay and the APPLICATION transport keep their own constants,
paths, credentials, ACLs and main semantics. The CAPACITY purpose is a third,
separately named closed compiler on the same transport owner: purpose, host,
listener, native target, port, executable, command, proxy, SOCKS remote and
credential source are not selectable, and the identity is the dedicated
least-privilege ``mastermind-capacity`` principal rather than the APPLICATION
principal.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from ops.executive_os import capacity_tunnel_entry
from ops.executive_os import os_tunnel_entry
from tests.test_capacity_tunnel_control import sealed_root  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
CAPACITY_CONFIG = {"schema": os_tunnel_entry.CAPACITY_SCHEMA, "binary_sha256": "d" * 64,
                   "server_fingerprint": "e" * 43 + "="}
CAPACITY_SECRET = b"mastermind-capacity:" + b"z" * 48
OS_CONFIG = {"schema": os_tunnel_entry.SCHEMA, "binary_sha256": "a" * 64,
             "server_fingerprint": "a" * 43 + "=", "relay_port": 49152}
OS_SECRET = b"mastermind-os:" + b"x" * 48
APP_CONFIG = {"schema": os_tunnel_entry.APPLICATION_SCHEMA, "binary_sha256": "b" * 64,
              "server_fingerprint": "b" * 43 + "="}
APP_SECRET = b"mastermind-fabric-app:" + b"y" * 48

# The bytes before the CAPACITY marker in os_tunnel_entry.py. Editing the
# OS-public or APPLICATION contract would change this digest; the capacity
# purpose is additive only.
OS_CONTRACT_PREFIX_SHA256 = "2751451eb8db0ccc6f9fee2b5e16054ac97cb0c9dea3a3c2c8729780dda24d74"
CAPACITY_MARKER = b"# ---------------------------------------------------------------- CAPACITY"


def _isolated_entry(monkeypatch, *, isolated=1, argv=None, euid=0):
    """Explicit invocation data; not proof of actual root-owned file access."""
    stub = SimpleNamespace(
        argv=["capacity_tunnel_entry.py"] if argv is None else argv,
        flags=SimpleNamespace(isolated=isolated),
        dont_write_bytecode=1,
        stderr=sys.stderr,
    )
    monkeypatch.setattr(capacity_tunnel_entry, "sys", stub)
    monkeypatch.setattr(os, "geteuid", lambda: euid)
    return stub


# ------------------------------------------------------------- additive proof


def test_os_public_and_application_contract_is_byte_identical_up_to_the_marker():
    raw = (REPO / "ops/executive_os/os_tunnel_entry.py").read_bytes()
    assert raw.count(CAPACITY_MARKER) == 1
    prefix = raw[:raw.index(CAPACITY_MARKER)]
    assert hashlib.sha256(prefix).hexdigest() == OS_CONTRACT_PREFIX_SHA256


def test_os_and_application_launch_specs_still_compile_their_own_reverses():
    binary, argv, env = os_tunnel_entry.launch_spec(OS_CONFIG, OS_SECRET)
    assert argv == [binary, "client", "--fingerprint", OS_CONFIG["server_fingerprint"],
                    "--keepalive", "20s", os_tunnel_entry.SERVER,
                    "R:127.0.0.1:49152:127.0.0.1:8443"]
    assert env == {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": OS_SECRET.decode()}
    binary, argv, env = os_tunnel_entry.application_launch_spec(APP_CONFIG, APP_SECRET)
    assert argv == [binary, "client", "--fingerprint", APP_CONFIG["server_fingerprint"],
                    "--keepalive", "20s", os_tunnel_entry.SERVER,
                    "R:127.0.0.1:50142:127.0.0.1:4142"]
    assert env["AUTH"] == APP_SECRET.decode()


def test_each_purpose_refuses_another_purposes_configuration_and_credential():
    with pytest.raises(ValueError):
        os_tunnel_entry.launch_spec(CAPACITY_CONFIG, CAPACITY_SECRET)
    with pytest.raises(ValueError):
        os_tunnel_entry.application_launch_spec(CAPACITY_CONFIG, CAPACITY_SECRET)
    with pytest.raises(ValueError):
        os_tunnel_entry.capacity_launch_spec(APP_CONFIG, APP_SECRET)
    with pytest.raises(ValueError):
        os_tunnel_entry.capacity_launch_spec(CAPACITY_CONFIG, APP_SECRET)


# --------------------------------------------------------- capacity compiler


def test_capacity_reverse_fixes_loopback_listener_and_loopback_native_target():
    binary, argv, env = os_tunnel_entry.capacity_launch_spec(CAPACITY_CONFIG, CAPACITY_SECRET)
    assert binary == str(os_tunnel_entry.ROOT / "transports/chisel" / ("d" * 64) / "chisel")
    assert argv == [binary, "client", "--fingerprint", CAPACITY_CONFIG["server_fingerprint"],
                    "--keepalive", "20s", os_tunnel_entry.SERVER,
                    "R:127.0.0.1:8313:127.0.0.1:8313"]
    assert env == {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": CAPACITY_SECRET.decode()}
    assert CAPACITY_SECRET.decode() not in json.dumps([binary, argv, CAPACITY_CONFIG])
    assert "50142" not in " ".join(argv)
    assert "4142" not in " ".join(argv)
    assert "8443" not in " ".join(argv)


def test_capacity_constants_are_the_fixed_closed_contract():
    assert os_tunnel_entry.CAPACITY_SCHEMA == "mastermind.capacity_tunnel.v1"
    assert os_tunnel_entry.CAPACITY_AUDIENCE == "mastermind-capacity"
    assert os_tunnel_entry.CAPACITY_RELAY_PORT == 8313
    assert os_tunnel_entry.CAPACITY_TARGET_PORT == 8313
    assert os_tunnel_entry.CAPACITY_REVERSE == "R:127.0.0.1:8313"
    assert os_tunnel_entry.CAPACITY_REVERSE_TARGET == "R:127.0.0.1:8313:127.0.0.1:8313"
    assert os_tunnel_entry.CAPACITY_REMOTE_REGEX == r"^R:127\.0\.0\.1:8313$"


def test_capacity_configuration_carries_no_port_host_or_executable_selector():
    for field, value in (("relay_port", 8313), ("target_port", 8313), ("port", 8313),
                         ("server", "http://foreign"), ("host", "10.0.0.1"),
                         ("command", "sh"), ("executable", "/bin/sh"), ("credential", "inline"),
                         ("proxy", "socks5://x"), ("socks", True), ("remote", "R:0.0.0.0:1"),
                         ("purpose", "other"), ("label", "other"), ("transport", "http")):
        config = {**CAPACITY_CONFIG, field: value}
        with pytest.raises(ValueError):
            os_tunnel_entry.capacity_launch_spec(config, CAPACITY_SECRET)


@pytest.mark.parametrize("config", [
    {}, {"schema": os_tunnel_entry.CAPACITY_SCHEMA},
    {**CAPACITY_CONFIG, "schema": "mastermind.application_tunnel.v1"},
    {**CAPACITY_CONFIG, "schema": "mastermind.application_tunnel.v2"},
    {**CAPACITY_CONFIG, "schema": "mastermind.os_public_tunnel.v1"},
    {**CAPACITY_CONFIG, "binary_sha256": "../escape"},
    {**CAPACITY_CONFIG, "binary_sha256": "D" * 64},
    {**CAPACITY_CONFIG, "binary_sha256": "d" * 63},
    {**CAPACITY_CONFIG, "server_fingerprint": ""},
    {**CAPACITY_CONFIG, "server_fingerprint": "unverified"},
    {**CAPACITY_CONFIG, "server_fingerprint": "e" * 42 + "="},
    {**CAPACITY_CONFIG, "server_fingerprint": "e" * 43 + "=="},
    [("schema", os_tunnel_entry.CAPACITY_SCHEMA)],
    "mastermind.capacity_tunnel.v1",
])
def test_capacity_configuration_refuses_a_malformed_or_foreign_value(config):
    with pytest.raises(ValueError):
        os_tunnel_entry.capacity_launch_spec(config, CAPACITY_SECRET)


@pytest.mark.parametrize("secret", [
    b"", b"other:" + b"x" * 48, b"mastermind-fabric-app:" + b"x" * 48,
    b"mastermind-os:" + b"x" * 48, b"mastermind-capacity:" + b"x" * 31,
    b"mastermind-capacity:" + b"x" * 129, b"mastermind-capacity:short",
    CAPACITY_SECRET + b"\nextra", CAPACITY_SECRET + b"\x00", CAPACITY_SECRET + b" ",
    CAPACITY_SECRET.replace(b"z", b"!"), CAPACITY_SECRET + b"\r\n",
    b"Mastermind-capacity:" + b"x" * 48,
])
def test_capacity_credential_is_the_dedicated_least_privilege_identity(secret):
    with pytest.raises(ValueError):
        os_tunnel_entry.capacity_launch_spec(CAPACITY_CONFIG, secret)


def test_capacity_credential_must_be_bytes_not_a_str():
    for value in (CAPACITY_SECRET.decode(), bytearray(CAPACITY_SECRET), None):
        with pytest.raises(ValueError):
            os_tunnel_entry.capacity_launch_spec(CAPACITY_CONFIG, value)


@pytest.mark.parametrize("size", [b"x" * 31, b"x" * 128, b"x" * 129])
def test_capacity_credential_length_bounds_are_exact(size):
    secret = b"mastermind-capacity:" + size
    if len(size) in (31, 129):
        with pytest.raises(ValueError):
            os_tunnel_entry.capacity_launch_spec(CAPACITY_CONFIG, secret)
    else:
        assert os_tunnel_entry.capacity_launch_spec(CAPACITY_CONFIG, secret)[2]["AUTH"] == secret.decode()


def test_one_private_newline_is_accepted_without_mutating_the_grant():
    config = dict(CAPACITY_CONFIG)
    binary, argv, env = os_tunnel_entry.capacity_launch_spec(config, CAPACITY_SECRET + b"\n")
    assert env["AUTH"] == CAPACITY_SECRET.decode()
    assert CAPACITY_SECRET.decode() not in json.dumps([binary, argv])
    assert config == CAPACITY_CONFIG


# ------------------------------------------------------------------- entry


def test_capacity_entry_uses_only_the_fixed_capacity_paths():
    assert capacity_tunnel_entry.CONFIG.name == "capacity-tunnel.json"
    assert capacity_tunnel_entry.CREDENTIAL.name == "capacity-tunnel.auth"
    assert capacity_tunnel_entry.CONFIG != os_tunnel_entry.CONFIG
    assert capacity_tunnel_entry.CREDENTIAL != os_tunnel_entry.CREDENTIAL
    assert capacity_tunnel_entry.CONFIG.parent == os_tunnel_entry.CONFIG.parent
    application = os_tunnel_entry.ROOT / "config/application-tunnel.json"
    assert capacity_tunnel_entry.CONFIG != application
    source = (REPO / "ops/executive_os/capacity_tunnel_entry.py").read_text()
    assert "os-public-tunnel" not in source
    assert "application-tunnel" not in source


def test_capacity_entry_opens_no_incumbent_os_or_application_file(monkeypatch):
    opened = []
    payload = b"chisel bytes"
    config = {**CAPACITY_CONFIG, "binary_sha256": hashlib.sha256(payload).hexdigest()}

    def fake_read(path, *, limit, private=False, acl_observer=None):
        opened.append(Path(path))
        if Path(path) == capacity_tunnel_entry.CONFIG:
            return json.dumps(config).encode()
        if Path(path) == capacity_tunnel_entry.CREDENTIAL:
            return CAPACITY_SECRET
        return payload

    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", fake_read)
    monkeypatch.setattr(os, "execve", lambda binary, argv, env: None)
    _isolated_entry(monkeypatch)
    assert capacity_tunnel_entry.main() == 0
    assert capacity_tunnel_entry.CONFIG in opened
    assert capacity_tunnel_entry.CREDENTIAL in opened
    assert os_tunnel_entry.CONFIG not in opened
    assert os_tunnel_entry.CREDENTIAL not in opened
    assert os_tunnel_entry.ROOT / "config/application-tunnel.json" not in opened
    assert os_tunnel_entry.ROOT / "config/application-tunnel.auth" not in opened


def test_capacity_entry_refuses_a_non_root_caller(monkeypatch):
    _isolated_entry(monkeypatch, euid=1000)
    assert capacity_tunnel_entry.main() == 1


def test_capacity_entry_refuses_extra_arguments(monkeypatch):
    _isolated_entry(monkeypatch, argv=["capacity_tunnel_entry.py", "--anything"])
    assert capacity_tunnel_entry.main() == 1


def test_capacity_entry_refuses_a_non_isolated_interpreter(monkeypatch):
    _isolated_entry(monkeypatch, isolated=0)
    assert capacity_tunnel_entry.main() == 1


def test_capacity_entry_refuses_a_binary_that_changed(monkeypatch):
    config = {**CAPACITY_CONFIG, "binary_sha256": "d" * 64}
    opened = []
    executed = []

    def fake_read(path, *, limit, private=False, acl_observer=None):
        opened.append(Path(path))
        if Path(path) == capacity_tunnel_entry.CONFIG:
            return json.dumps(config).encode()
        if Path(path) == capacity_tunnel_entry.CREDENTIAL:
            return CAPACITY_SECRET
        return b"different bytes"

    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", fake_read)
    monkeypatch.setattr(os, "execve", lambda *args: executed.append(args))
    _isolated_entry(monkeypatch)
    assert capacity_tunnel_entry.main() == 1
    assert opened[:2] == [capacity_tunnel_entry.CONFIG, capacity_tunnel_entry.CREDENTIAL]
    assert len(opened) == 3
    assert executed == []


def test_capacity_entry_never_prints_the_credential(monkeypatch, capsys):
    config = {**CAPACITY_CONFIG, "binary_sha256": "d" * 64}

    def fake_read(path, *, limit, private=False, acl_observer=None):
        if Path(path) == capacity_tunnel_entry.CONFIG:
            return json.dumps(config).encode()
        if Path(path) == capacity_tunnel_entry.CREDENTIAL:
            return CAPACITY_SECRET
        return b"different bytes"

    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", fake_read)
    monkeypatch.setattr(os, "execve", lambda *args: pytest.fail("exec after a refused binary"))
    _isolated_entry(monkeypatch)
    assert capacity_tunnel_entry.main() == 1
    captured = capsys.readouterr()
    assert CAPACITY_SECRET.decode() not in captured.err + captured.out
    assert "mastermind-capacity" not in captured.err + captured.out
    assert captured.err == "Capacity transport refused\n"


def test_capacity_entry_rejects_duplicate_and_nonfinite_json_before_secret(monkeypatch):
    _isolated_entry(monkeypatch)
    opened = []
    raw = json.dumps(CAPACITY_CONFIG).encode()
    duplicate = raw[:-1] + b', "schema": "mastermind.capacity_tunnel.v1"}'

    def read(path, **kwargs):
        opened.append(Path(path))
        assert Path(path) == capacity_tunnel_entry.CONFIG
        return duplicate

    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", read)
    assert capacity_tunnel_entry.main() == 1
    assert opened == [capacity_tunnel_entry.CONFIG]
    with pytest.raises(ValueError, match="nonfinite"):
        capacity_tunnel_entry._config(b'{"value": NaN}')


def test_capacity_entry_compiles_the_fixed_reverse_through_the_capacity_function(monkeypatch):
    payload = b"qualified chisel bytes"
    config = {**CAPACITY_CONFIG, "binary_sha256": hashlib.sha256(payload).hexdigest()}
    executed = []

    def fake_read(path, *, limit, private=False, acl_observer=None):
        if Path(path) == capacity_tunnel_entry.CONFIG:
            return json.dumps(config).encode()
        if Path(path) == capacity_tunnel_entry.CREDENTIAL:
            return CAPACITY_SECRET
        return payload

    monkeypatch.setattr(os_tunnel_entry, "_read_sealed", fake_read)
    monkeypatch.setattr(os, "execve", lambda binary, argv, env: executed.append((binary, argv, env)))
    _isolated_entry(monkeypatch)
    assert capacity_tunnel_entry.main() == 0
    assert len(executed) == 1
    binary, argv, env = executed[0]
    assert argv[-1] == os_tunnel_entry.CAPACITY_REVERSE_TARGET
    assert env["AUTH"] == CAPACITY_SECRET.decode()
    assert CAPACITY_SECRET.decode() not in " ".join(argv)


# ------------------------------------------------------- sealed reader shape

@pytest.mark.parametrize("path", [
    Path("relative/capacity-tunnel.json"),
    Path("/absolute/../capacity-tunnel.json"),
    Path("../capacity-tunnel.json"),
])
def test_sealed_reader_refuses_a_relative_or_traversing_path(path):
    with pytest.raises(ValueError):
        os_tunnel_entry._read_sealed(path, limit=4096)


def test_sealed_reader_refuses_a_symlinked_component(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "capacity-tunnel.json").write_text("{}")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises((OSError, ValueError)):
        os_tunnel_entry._read_sealed(link / "capacity-tunnel.json", limit=4096)


def test_sealed_reader_refuses_a_world_writable_directory(tmp_path):
    directory = tmp_path / "open"
    directory.mkdir()
    directory.chmod(0o777)
    (directory / "capacity-tunnel.json").write_text("{}")
    with pytest.raises((OSError, ValueError)):
        os_tunnel_entry._read_sealed(directory / "capacity-tunnel.json", limit=4096)
