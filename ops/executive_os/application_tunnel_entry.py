"""Fixed application-purpose reverse client; the OS relay entry is untouched.

This is a thin transport owner on the same incumbent Chisel server. It selects
the APPLICATION purpose internally: callers cannot select a purpose, a host, a
destination, a port, an executable, a command, a proxy, a SOCKS remote or a
credential source. The reverse listener and the native target are source
constants; the credential is read only from the fixed root-private application
file and reaches Chisel only through the AUTH environment, never through argv,
the plist, a receipt, a log or an error.

The existing OS transport files are never opened here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.executive_os import os_tunnel_entry
from control_plane.fs_security import FilesystemSecurityError, has_macos_acl

CONFIG = os_tunnel_entry.ROOT / "config/application-tunnel.json"
CREDENTIAL = os_tunnel_entry.ROOT / "config/application-tunnel.auth"


def _application_acl(path, before, *, descriptor):
    try:
        if has_macos_acl(path, expected_identity=before, descriptor=descriptor):
            raise ValueError("application transport ACL refused")
    except FilesystemSecurityError as exc:
        raise ValueError("application transport ACL observation refused") from exc


def _read_application_sealed(path, *, limit, private=False):
    return os_tunnel_entry._read_sealed(path, limit=limit, private=private,
                                       acl_observer=_application_acl)


def _config(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate application configuration key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite application configuration")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _main_for_purpose(purpose) -> int:
    """Shared sealed entry mechanism; standalone entrypoints fix the purpose."""
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    config_path = CONFIG if purpose is os_tunnel_entry.FABRIC_APPLICATION else (
        os_tunnel_entry.ROOT / "config/deepseek-tunnel.json")
    credential_path = CREDENTIAL if purpose is os_tunnel_entry.FABRIC_APPLICATION else (
        os_tunnel_entry.ROOT / "config/deepseek-tunnel.auth")
    compile_spec = (os_tunnel_entry.application_launch_spec
                    if purpose is os_tunnel_entry.FABRIC_APPLICATION
                    else os_tunnel_entry.deepseek_launch_spec)
    try:
        if len(sys.argv) != 1 or not sys.flags.isolated or not sys.dont_write_bytecode or os.geteuid() != 0:
            raise ValueError("fixed root invocation required")
        config = _config(_read_application_sealed(config_path, limit=4096))
        binary, argv, env = compile_spec(
            config, _read_application_sealed(credential_path, limit=1024, private=True))
        encoded = _read_application_sealed(Path(binary), limit=64 * 1024 * 1024)
        if hashlib.sha256(encoded).hexdigest() != config["binary_sha256"]:
            raise ValueError("application tunnel executable changed")
        # No shell, inherited environment, unpinned server, listener widening,
        # proxy, SOCKS remote or fallback tunnel.
        os.execve(binary, argv, env)
    except Exception:
        sys.stderr.write("Application transport refused\n")
        return 1
    return 0


def main() -> int:
    return _main_for_purpose(os_tunnel_entry.FABRIC_APPLICATION)


if __name__ == "__main__":
    raise SystemExit(main())
