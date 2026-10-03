#!/usr/bin/env python3
"""Install the inert mini-side client for the bounded M2 production-release relay."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


INSTALL_SCHEMA = "mastermind.mini_vps_release_client_install/v1"


class InstallError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_sha(source_root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and len(value) == 40 else "unversioned"


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _host_key_ready(home: Path) -> bool:
    path = home / ".ssh" / "known_hosts"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) not in (0o600, 0o644)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_size > 1024 * 1024
    ):
        raise InstallError("known_hosts has unsafe metadata")
    probe = subprocess.run(
        ["/usr/bin/ssh-keygen", "-F", "m2studio", "-f", str(path)],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return probe.returncode == 0


def _key_ready(home: Path) -> bool:
    path = home / ".ssh" / "m2_release"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise InstallError("dedicated M2 release key path is unsafe")
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
        raise InstallError("dedicated M2 release key metadata is unsafe")
    if info.st_uid != os.getuid():
        raise InstallError("dedicated M2 release key owner is not the installing user")
    return True


def install(*, source_root: Path, home: Path, require_key: bool) -> dict[str, object]:
    source = source_root / "scripts" / "mmx_vps_release.py"
    if not source.is_file():
        raise InstallError(f"client source unavailable: {source}")
    key_ready = _key_ready(home)
    host_key_ready = _host_key_ready(home)
    if require_key and not key_ready:
        raise InstallError("dedicated M2 release key is not provisioned")
    if require_key and not host_key_ready:
        raise InstallError("m2studio host key is not pinned in known_hosts")
    source_sha = _source_sha(source_root)
    payload_root = home / ".local" / "share" / "mastermind" / "vps-release" / source_sha
    payload = payload_root / "mmx_vps_release.py"
    wrapper = home / ".local" / "bin" / "mmx-vps-release"

    raw = source.read_bytes()
    if not payload.exists() or payload.read_bytes() != raw:
        _atomic_write(payload, raw, 0o555)
        payload_changed = True
    else:
        payload_changed = False

    wrapper_bytes = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"exec python3 '{payload}' \"$@\"\n"
    ).encode("utf-8")
    if not wrapper.exists() or wrapper.read_bytes() != wrapper_bytes:
        _atomic_write(wrapper, wrapper_bytes, 0o555)
        wrapper_changed = True
    else:
        wrapper_changed = False

    return {
        "schema_version": INSTALL_SCHEMA,
        "source_sha": source_sha,
        "payload": str(payload),
        "payload_sha256": _sha256(payload),
        "wrapper": str(wrapper),
        "wrapper_sha256": _sha256(wrapper),
        "key_ready": key_ready,
        "host_key_ready": host_key_ready,
        "changes": {"payload": payload_changed, "wrapper": wrapper_changed},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--require-key", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = install(
            source_root=Path(args.source_root).expanduser().resolve(),
            home=Path(args.home).expanduser().resolve(),
            require_key=bool(args.require_key),
        )
    except InstallError as exc:
        print(
            json.dumps({"schema_version": INSTALL_SCHEMA, "effect": "NOT_APPLIED", "error": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"schema_version": INSTALL_SCHEMA, "effect": "APPLIED", "receipt": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
