"""Fixed native MCP entrypoints with no inherited inference credentials.

This replaces this stdio process with the chosen installed tool process. It is
not an agent runner, tool proxy, scheduler, credential owner or daemon manager.
Peekaboo keeps its original background-only Bridge and native permission rules.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import pwd
import stat
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from integrations.t3_harness.runtime import HarnessError, _absolute, _HEX, read_configuration

MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024


def executable_digest(path: Path) -> str:
    """Bounded immutable-descriptor read; not a security sandbox against its owner."""
    if path.is_symlink() or not path.is_absolute() or not os.access(path, os.X_OK):
        raise HarnessError("PEEKABOO_EXECUTABLE_INVALID")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in {0, os.getuid()}
                or before.st_mode & 0o022 or not 0 < before.st_size <= MAX_EXECUTABLE_BYTES):
            raise HarnessError("PEEKABOO_EXECUTABLE_UNSAFE")
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(fd, 1024 * 1024):
            size += len(chunk)
            if size > MAX_EXECUTABLE_BYTES:
                raise HarnessError("PEEKABOO_EXECUTABLE_TOO_LARGE")
            digest.update(chunk)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise HarnessError("PEEKABOO_EXECUTABLE_CHANGED")
        return digest.hexdigest()
    finally:
        os.close(fd)


def launch_spec(mode: str, path: str, expected_sha256: str, environment=None) -> tuple[str, list[str], dict[str, str]]:
    config, sid = read_configuration(path, expected_sha256, environment)
    # Native tools consume their own installed credentials when authorized. A
    # T3 provider's API keys, base URL, NODE_OPTIONS and Python injection paths
    # must not silently select the desktop/vision backend or leak into it.
    env = {"HOME": pwd.getpwuid(os.getuid()).pw_dir,
           "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
           "PYTHONDONTWRITEBYTECODE": "1", "T3CODE_THREAD_ID": sid}
    if mode == "browser":
        executable = str(Path(sys.executable).absolute())
        script = str(Path(config["source_root"]) / "integrations/t3_harness/server.py")
        return executable, [executable, "-I", "-B", script, "--config", path,
                            "--expected-config-sha256", expected_sha256], env
    if mode != "peekaboo":
        raise HarnessError("CLOSED_NATIVE_ENTRYPOINT_REQUIRED")
    selected = config.get("peekaboo")
    if type(selected) is not dict or set(selected) != {"executable", "executable_sha256", "bridge_socket"}:
        raise HarnessError("PEEKABOO_INSTALL_BINDING_MISSING")
    executable = _absolute(selected["executable"])
    expected = selected["executable_sha256"]
    if executable.name != "peekaboo" or type(expected) is not str or _HEX.fullmatch(expected) is None:
        raise HarnessError("PEEKABOO_INSTALL_BINDING_INVALID")
    if executable_digest(executable) != expected:
        raise HarnessError("PEEKABOO_EXECUTABLE_DIGEST_MISMATCH")
    socket = _absolute(selected["bridge_socket"])
    info = socket.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise HarnessError("PEEKABOO_ORIGINAL_BRIDGE_UNAVAILABLE")
    # No local fallback, automatic permission request, foreground flag, browser
    # attachment, model override or alternate socket after an exact refusal.
    args = [str(executable), "mcp", "serve", "--bridge-socket", str(socket)]
    return str(executable), args, env


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("browser", "peekaboo"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        executable, command, env = launch_spec(args.mode, args.config, args.expected_config_sha256)
        os.execve(executable, command, env)
    except (OSError, ValueError, TypeError, RecursionError):
        print("T3_NATIVE_MCP_INSTALL_OR_CONTEXT_UNAVAILABLE", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
