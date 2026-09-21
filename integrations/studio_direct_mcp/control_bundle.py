#!/usr/bin/env python3
"""Adopt and verify one exact installed Studio Direct control-helper bundle.

This is deployment plumbing for the existing control surface. It never starts,
stops, restarts, upgrades, or otherwise mutates a Studio Direct seat or tunnel.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

SCHEMA = "mastermind.studio_direct_control_bundle.v1"
CONTROL_FILES = (
    "private_service.py",
    "private_tunnel_service.py",
    "studio_direct_control.py",
)
FILE_MODE = 0o600
DIR_MODE = 0o700


class Refusal(RuntimeError):
    pass


class EffectUnknown(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_regular(path: Path, *, executable: bool = False) -> Path:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Refusal("REGULAR_FILE_REQUIRED")
    if info.st_uid != os.getuid():
        raise Refusal("CURRENT_USER_OWNERSHIP_REQUIRED")
    if executable and not (info.st_mode & stat.S_IXUSR):
        raise Refusal("EXECUTABLE_REQUIRED")
    return path


def _require_private_dir(path: Path) -> Path:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    return path


def _source_files(source: Path) -> dict[str, Path]:
    if source.is_symlink() or not source.is_dir():
        raise Refusal("SOURCE_DIRECTORY_INVALID")
    rows = {}
    for name in CONTROL_FILES:
        rows[name] = _require_regular(source / name)
    return rows


def _manifest_payload(source: Path, files: dict[str, Path], launcher: Path) -> dict:
    return {
        "schema": SCHEMA,
        "files": {name: _sha256(path) for name, path in sorted(files.items())},
        "launcher": str(launcher),
        "launcherHash": _sha256(launcher),
        "source": str(source),
    }


def _read_manifest(path: Path) -> dict:
    _require_regular(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise Refusal("CONTROL_MANIFEST_INVALID") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise Refusal("CONTROL_MANIFEST_INVALID")
    if set(value.get("files", {})) != set(CONTROL_FILES):
        raise Refusal("CONTROL_MANIFEST_INVALID")
    return value


def verify(*, control_root: Path, launcher: Path) -> dict:
    root = _require_private_dir(control_root)
    manifest = _read_manifest(root / "manifest.json")
    _require_regular(launcher, executable=True)
    if manifest.get("launcher") != str(launcher) or manifest.get("launcherHash") != _sha256(launcher):
        raise Refusal("CONTROL_BUNDLE_MISMATCH")
    observed = {}
    for name in CONTROL_FILES:
        path = _require_regular(root / name)
        observed[name] = _sha256(path)
        if manifest["files"].get(name) != observed[name]:
            raise Refusal("CONTROL_BUNDLE_MISMATCH")
    return {
        "state": "CONTROL_BUNDLE_VERIFIED",
        "schema": SCHEMA,
        "files": observed,
        "launcherHash": _sha256(launcher),
        "source": manifest.get("source"),
    }


@contextlib.contextmanager
def _lock(root: Path):
    path = root / ".control-bundle.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, FILE_MODE)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise Refusal("CONTROL_BUNDLE_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal("CONTROL_BUNDLE_BUSY") from exc
        yield
    finally:
        os.close(fd)


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def install(*, source: Path, control_root: Path, launcher: Path) -> dict:
    root = _require_private_dir(control_root)
    _require_regular(launcher, executable=True)
    source_files = _source_files(source)
    payload = _manifest_payload(source, source_files, launcher)
    with _lock(root):
        stage = Path(tempfile.mkdtemp(prefix=".control-bundle.stage-", dir=root))
        stage.chmod(DIR_MODE)
        committed = False
        try:
            for name, src in source_files.items():
                _write_private(stage / name, src.read_bytes())
                if _sha256(stage / name) != payload["files"][name]:
                    raise Refusal("STAGED_HASH_MISMATCH")
            manifest_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
            _write_private(stage / "manifest.json", manifest_bytes)
            for name in CONTROL_FILES:
                os.replace(stage / name, root / name)
                committed = True
            os.replace(stage / "manifest.json", root / "manifest.json")
            dir_fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            result = verify(control_root=root, launcher=launcher)
        except (OSError, Refusal) as exc:
            if committed:
                raise EffectUnknown("CONTROL_BUNDLE_EFFECT_UNKNOWN") from exc
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {**result, "state": "CONTROL_BUNDLE_INSTALLED"}


def _default_paths() -> tuple[Path, Path, Path]:
    source = Path(__file__).resolve().parent
    home = Path.home()
    return (
        source,
        home / ".local" / "share" / "studio-direct-mcp" / "control",
        home / ".local" / "bin" / "studio-direct",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "install"))
    args = parser.parse_args(argv)
    source, control_root, launcher = _default_paths()
    try:
        result = verify(control_root=control_root, launcher=launcher) if args.action == "verify" else install(source=source, control_root=control_root, launcher=launcher)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except EffectUnknown:
        print(json.dumps({"state": "EFFECT_UNKNOWN", "retry_allowed": False, "reconcile_action": "verify"}))
        return 3
    except (Refusal, OSError) as exc:
        state = str(exc) if isinstance(exc, Refusal) else "LOCAL_FAILURE"
        print(json.dumps({"state": state, "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
