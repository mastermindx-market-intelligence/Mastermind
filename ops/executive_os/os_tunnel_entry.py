"""Fixed public OS relay client; consumes an installed grant, never creates one.

Uses the incumbent VPS Chisel server and its verified HTTPS endpoint. The
credential is read only from the fixed root-private file and supplied via
Chisel's AUTH environment; it never appears in argv, output or a staged plist.
Installation and server-side exact reverse-port authorization remain separate.
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


def _read_sealed(path: Path, *, limit: int, private: bool = False) -> bytes:
    """Bind every component and final read to descriptors; never follow links."""
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise ValueError("sealed path required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("sealed directory required")
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(file_fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != 0
                    or before.st_mode & (0o077 if private else 0o022)
                    or not 0 < before.st_size <= limit):
                raise ValueError("sealed file required")
            with os.fdopen(file_fd, "rb", closefd=False) as stream:
                raw = stream.read(limit + 1)
            after = os.fstat(file_fd)
            stable = lambda v: (v.st_dev, v.st_ino, v.st_mode, v.st_uid, v.st_gid,
                                v.st_nlink, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
            if len(raw) != before.st_size or stable(before) != stable(after):
                raise ValueError("sealed file changed")
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
