"""Fixed public OS relay client; consumes an installed grant, never creates one.

Uses the incumbent VPS Chisel server and its verified HTTPS endpoint. The
credential is read only from the fixed root-private file and supplied via
Chisel's AUTH environment; it never appears in argv, output or a staged plist.
Installation and server-side exact reverse-port authorization remain separate.

The APPLICATION-purpose reverse below is a separately named closed compiler on
the same incumbent transport owner. It shares only this module's sealed reader,
the incumbent server endpoint and the fingerprint pinning; the OS constants,
the OS defaults and the OS main semantics are unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path("/Library/Application Support/MastermindExecutive")
CONFIG = ROOT / "config/os-public-tunnel.json"
CREDENTIAL = ROOT / "config/os-public-tunnel.auth"
SERVER = "https://146-190-142-17.sslip.io"
SCHEMA = "mastermind.os_public_tunnel.v1"


def _read_sealed(path: Path, *, limit: int, private: bool = False, acl_observer=None) -> bytes:
    """Bind every component and final read to descriptors; never follow links."""
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise ValueError("sealed path required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        current_path = Path("/")
        if acl_observer is not None:
            acl_observer(current_path, os.fstat(fd), descriptor=fd)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            current_path = current_path / part
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("sealed directory required")
            if acl_observer is not None:
                acl_observer(current_path, info, descriptor=fd)
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(file_fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != 0
                    or before.st_mode & (0o077 if private else 0o022)
                    or not 0 < before.st_size <= limit):
                raise ValueError("sealed file required")
            if acl_observer is not None:
                acl_observer(path, before, descriptor=file_fd)
            with os.fdopen(file_fd, "rb", closefd=False) as stream:
                raw = stream.read(limit + 1)
            after = os.fstat(file_fd)
            stable = lambda v: (v.st_dev, v.st_ino, v.st_mode, v.st_uid, v.st_gid,
                                v.st_nlink, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
            if len(raw) != before.st_size or stable(before) != stable(after):
                raise ValueError("sealed file changed")
            if acl_observer is not None:
                acl_observer(path, after, descriptor=file_fd)
            return raw
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


def launch_spec(config: dict, credential: bytes) -> tuple[str, list[str], dict[str, str]]:
    """Closed pure compiler; bearer/host/path/command selectors are not accepted."""
    if (type(config) is not dict or set(config) != {
            "schema", "binary_sha256", "server_fingerprint", "relay_port"}
            or config["schema"] != SCHEMA
            or type(config["binary_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", config["binary_sha256"])
            or type(config["server_fingerprint"]) is not str
            or not re.fullmatch(r"[A-Za-z0-9+/]{43}=", config["server_fingerprint"])
            or type(config["relay_port"]) is not int
            or not 49152 <= config["relay_port"] <= 50200):
        raise ValueError("tunnel configuration refused")
    if type(credential) is not bytes or not 32 <= len(credential) <= 1024:
        raise ValueError("tunnel credential refused")
    auth = credential.decode("ascii", errors="strict").removesuffix("\n")
    if not re.fullmatch(r"mastermind-os:[A-Za-z0-9_-]{32,128}", auth):
        raise ValueError("tunnel credential refused")
    binary = str(ROOT / "transports/chisel" / config["binary_sha256"] / "chisel")
    argv = [binary, "client", "--fingerprint", config["server_fingerprint"],
            "--keepalive", "20s", SERVER,
            f"R:127.0.0.1:{config['relay_port']}:127.0.0.1:8443"]
    return binary, argv, {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": auth}


APPLICATION_SCHEMA = "mastermind.application_tunnel.v1"
APPLICATION_ROLE_SCHEMA = "mastermind.application_tunnel.v2"
APPLICATION_AUDIENCE = "mastermind-fabric-app"
# Proposed source constants for the closed APPLICATION reverse. They are not an
# observed available or installed grant; a collision is refused, never resolved
# by searching for or choosing another port.
APPLICATION_RELAY_PORT = 50142
APPLICATION_TARGET_PORT = 4142
APPLICATION_REVERSE = f"R:127.0.0.1:{APPLICATION_RELAY_PORT}"
APPLICATION_REVERSE_TARGET = f"{APPLICATION_REVERSE}:127.0.0.1:{APPLICATION_TARGET_PORT}"
# The server-side remote-address ACL names the reverse listener only; the
# sealed client separately fixes the native target.
APPLICATION_REMOTE_REGEX = r"^R:127\.0\.0\.1:50142$"
APPLICATION_ROLE_REVERSES = (APPLICATION_REVERSE, "R:127.0.0.2:50142", "R:127.0.0.3:50142")
APPLICATION_ROLE_TARGETS = tuple(remote + ":127.0.0.1:4142" for remote in APPLICATION_ROLE_REVERSES)
APPLICATION_ROLE_REGEXES = (APPLICATION_REMOTE_REGEX, r"^R:127\.0\.0\.2:50142$", r"^R:127\.0\.0\.3:50142$")


def application_launch_spec(config: dict, credential: bytes) -> tuple[str, list[str], dict[str, str]]:
    """Closed APPLICATION compiler; purpose, host, destination and port are fixed.

    The configuration carries no port, host, executable, command or credential
    selector: the reverse listener, the native target, the server endpoint and
    the hash-addressed binary path are all source constants. Only the observed
    binary digest and the independently pinned server fingerprint are supplied.
    """
    if (type(config) is not dict or set(config) != {"schema", "binary_sha256", "server_fingerprint"}
            or config["schema"] not in (APPLICATION_SCHEMA, APPLICATION_ROLE_SCHEMA)
            or type(config["binary_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", config["binary_sha256"])
            or type(config["server_fingerprint"]) is not str
            or not re.fullmatch(r"[A-Za-z0-9+/]{43}=", config["server_fingerprint"])):
        raise ValueError("application tunnel configuration refused")
    if type(credential) is not bytes or not 32 <= len(credential) <= 1024:
        raise ValueError("application tunnel credential refused")
    auth = credential.decode("ascii", errors="strict").removesuffix("\n")
    if not re.fullmatch(r"mastermind-fabric-app:[A-Za-z0-9_-]{32,128}", auth):
        raise ValueError("application tunnel credential refused")
    binary = str(ROOT / "transports/chisel" / config["binary_sha256"] / "chisel")
    remotes = APPLICATION_ROLE_TARGETS if config["schema"] == APPLICATION_ROLE_SCHEMA else (APPLICATION_REVERSE_TARGET,)
    argv = [binary, "client", "--fingerprint", config["server_fingerprint"],
            "--keepalive", "20s", SERVER, *remotes]
    return binary, argv, {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": auth}


# ---------------------------------------------------------------- CAPACITY
# Additive capacity-purpose reverse on the same incumbent transport owner.
# Everything above this marker is byte-identical to the OS-public and
# APPLICATION contract; tests/test_capacity_tunnel_entry.py pins that prefix.
# A collision is refused, never resolved by searching for another port.
CAPACITY_SCHEMA = "mastermind.capacity_tunnel.v1"
CAPACITY_AUDIENCE = "mastermind-capacity"
# The VPS-side listener and the M2-side native target are both 8313: the
# Capacity Fabric gateway accepts only a loopback peer, so the reverse lands on
# the M2 loopback address where the unified_router listens.
CAPACITY_RELAY_PORT = 8313
CAPACITY_TARGET_PORT = 8313
CAPACITY_REVERSE = f"R:127.0.0.1:{CAPACITY_RELAY_PORT}"
CAPACITY_REVERSE_TARGET = f"{CAPACITY_REVERSE}:127.0.0.1:{CAPACITY_TARGET_PORT}"
CAPACITY_REMOTE_REGEX = r"^R:127\.0\.0\.1:8313$"


def capacity_launch_spec(config: dict, credential: bytes) -> tuple[str, list[str], dict[str, str]]:
    """Closed CAPACITY compiler; purpose, host, listener, target and port are fixed.

    The configuration carries no port, host, executable, command, proxy, SOCKS
    remote or credential selector: the reverse listener, the native target, the
    server endpoint and the hash-addressed binary path are source constants.
    Only the observed binary digest and the independently pinned server
    fingerprint are supplied. The identity is the dedicated least-privilege
    mastermind-capacity principal, never the APPLICATION principal.
    """
    if (type(config) is not dict or set(config) != {"schema", "binary_sha256", "server_fingerprint"}
            or config["schema"] != CAPACITY_SCHEMA
            or type(config["binary_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", config["binary_sha256"])
            or type(config["server_fingerprint"]) is not str
            or not re.fullmatch(r"[A-Za-z0-9+/]{43}=", config["server_fingerprint"])):
        raise ValueError("capacity tunnel configuration refused")
    if type(credential) is not bytes or not 32 <= len(credential) <= 1024:
        raise ValueError("capacity tunnel credential refused")
    auth = credential.decode("ascii", errors="strict").removesuffix("\n")
    if not re.fullmatch(r"mastermind-capacity:[A-Za-z0-9_-]{32,128}", auth):
        raise ValueError("capacity tunnel credential refused")
    binary = str(ROOT / "transports/chisel" / config["binary_sha256"] / "chisel")
    argv = [binary, "client", "--fingerprint", config["server_fingerprint"],
            "--keepalive", "20s", SERVER, CAPACITY_REVERSE_TARGET]
    return binary, argv, {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": auth}


def main() -> int:
    try:
        if len(sys.argv) != 1 or not sys.flags.isolated or not sys.dont_write_bytecode or os.geteuid() != 0:
            raise ValueError("fixed root invocation required")
        config = json.loads(_read_sealed(CONFIG, limit=4096))
        binary, argv, env = launch_spec(config, _read_sealed(CREDENTIAL, limit=1024, private=True))
        encoded = _read_sealed(Path(binary), limit=64 * 1024 * 1024)
        if hashlib.sha256(encoded).hexdigest() != config["binary_sha256"]:
            raise ValueError("tunnel executable changed")
        # No shell, inherited environment, unpinned server, listener widening or fallback.
        os.execve(binary, argv, env)
    except Exception:
        sys.stderr.write("OS public tunnel refused\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

