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
from typing import NamedTuple

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


class ApplicationPurpose(NamedTuple):
    """Only the two source-defined application purposes may reach the owner."""

    purpose: str
    schema_stem: str
    operation_prefix: str
    audience: str
    relay_port: int
    target_port: int
    label: str
    path_stem: str
    entry: str

    @property
    def client_schema(self):
        return "mastermind." + self.schema_stem + ".v1"

    @property
    def control_schema(self):
        return "mastermind." + self.schema_stem + "_control.v1"

    @property
    def bundle_schema(self):
        return "mastermind." + self.schema_stem + "_server_bundle.v1"

    @property
    def receipt_schema(self):
        return "mastermind." + self.schema_stem + "_receipt.v1"

    @property
    def remote_address(self):
        return "R:127.0.0.1:%d" % self.relay_port

    @property
    def remote_regex(self):
        return r"^R:127\.0\.0\.1:%d$" % self.relay_port

    @property
    def reverse_target(self):
        return self.remote_address + ":127.0.0.1:%d" % self.target_port

    @property
    def import_closure(self):
        common = (self.entry, "ops/executive_os/os_tunnel_entry.py",
                  "ops/executive_os/application_tunnel_control.py",
                  "control_plane/fs_security.py")
        if self is FABRIC_APPLICATION:
            return common
        return common + ("ops/executive_os/application_tunnel_entry.py",
                         "ops/executive_os/deepseek_tunnel_control.py")

    @property
    def template_path(self):
        # One existing parameter-free transport template, selected by source.
        return "ops/executive_os/com.mastermind.executive.fabric-application-tunnel.plist.template"


FABRIC_APPLICATION = ApplicationPurpose(
    "fabric-application-transport", "application_tunnel", "app-tunnel-",
    APPLICATION_AUDIENCE, APPLICATION_RELAY_PORT, APPLICATION_TARGET_PORT,
    "com.mastermind.executive.fabric-application-tunnel", "application-tunnel",
    "ops/executive_os/application_tunnel_entry.py",
)
DEEPSEEK_APPLICATION = ApplicationPurpose(
    "deepseek-attended-transport", "deepseek_tunnel", "dsh-tunnel-",
    "mastermind-deepseek-app", 4181, 4180,
    "com.mastermind.executive.deepseek-tunnel", "deepseek-tunnel",
    "ops/executive_os/deepseek_tunnel_entry.py",
)


def closed_application_purpose(purpose):
    if purpose is not FABRIC_APPLICATION and purpose is not DEEPSEEK_APPLICATION:
        raise ValueError("source-defined application purpose required")
    return purpose


def _application_launch_spec(config, credential, purpose):
    purpose = closed_application_purpose(purpose)
    if (type(config) is not dict or set(config) != {"schema", "binary_sha256", "server_fingerprint"}
            or config["schema"] not in ((purpose.client_schema, APPLICATION_ROLE_SCHEMA)
                    if purpose is FABRIC_APPLICATION else (purpose.client_schema,))
            or type(config["binary_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", config["binary_sha256"])
            or type(config["server_fingerprint"]) is not str
            or not re.fullmatch(r"[A-Za-z0-9+/]{43}=", config["server_fingerprint"])):
        raise ValueError("application tunnel configuration refused")
    if type(credential) is not bytes or not 32 <= len(credential) <= 1024:
        raise ValueError("application tunnel credential refused")
    auth = credential.decode("ascii", errors="strict").removesuffix("\n")
    if not re.fullmatch(re.escape(purpose.audience) + r":[A-Za-z0-9_-]{32,128}", auth):
        raise ValueError("application tunnel credential refused")
    binary = str(ROOT / "transports/chisel" / config["binary_sha256"] / "chisel")
    remotes = APPLICATION_ROLE_TARGETS if config["schema"] == APPLICATION_ROLE_SCHEMA else (purpose.reverse_target,)
    argv = [binary, "client", "--fingerprint", config["server_fingerprint"],
            "--keepalive", "20s", SERVER, *remotes]
    return binary, argv, {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": auth}


def application_launch_spec(config: dict, credential: bytes) -> tuple[str, list[str], dict[str, str]]:
    """The incumbent Fabric compiler keeps its exact fixed identity and reverse."""
    return _application_launch_spec(config, credential, FABRIC_APPLICATION)


def deepseek_launch_spec(config: dict, credential: bytes) -> tuple[str, list[str], dict[str, str]]:
    """Closed DSH compiler: only its distinct identity and 4181 -> 4180 reverse."""
    return _application_launch_spec(config, credential, DEEPSEEK_APPLICATION)


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
