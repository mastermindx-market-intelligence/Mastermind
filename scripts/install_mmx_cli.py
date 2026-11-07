#!/usr/bin/env python3
"""Install a user-level mmx launcher bound to one immutable Executive release."""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Sequence

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from ops.executive_os.release_manifest import (
    MANIFEST_NAME,
    ReleaseManifestError,
    verify as verify_release,
)

RELEASES_ROOT = Path("/Library/Application Support/MastermindExecutive/releases")
PINNED_PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class MmxInstallError(RuntimeError):
    """The requested immutable launcher cannot be installed safely."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install ~/.local/bin/mmx for one exact installed Executive release."
    )
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--target", type=Path, default=Path.home() / ".local/bin/mmx")
    return parser


def _manifest_identity(release_root: Path, expected_sha: str) -> str:
    manifest = release_root / MANIFEST_NAME
    try:
        info = manifest.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise MmxInstallError("Executive release manifest is unavailable")
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except MmxInstallError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise MmxInstallError("Executive release manifest is unavailable") from None
    tree_sha = value.get("tree_sha") if isinstance(value, dict) else None
    commit_sha = value.get("commit_sha") if isinstance(value, dict) else None
    if commit_sha != expected_sha or not isinstance(tree_sha, str) or not _SHA_RE.fullmatch(tree_sha):
        raise MmxInstallError("Executive release manifest identity does not match requested release")
    return tree_sha


def _wrapper(release_root: Path, release_sha: str, tree_sha: str, python: Path) -> str:
    manifest_tool = release_root / "ops/executive_os/release_manifest.py"
    mmx_script = release_root / "scripts/mmx.py"
    return f"""#!/bin/sh
set -eu
release_root={str(release_root)!r}
python={str(python)!r}
manifest_tool={str(manifest_tool)!r}
mmx_script={str(mmx_script)!r}
[ -x "$python" ] || {{ echo "pinned Executive Python is unavailable" >&2; exit 69; }}
[ -f "$manifest_tool" ] && [ ! -L "$manifest_tool" ] || {{ echo "Executive release verifier is unavailable" >&2; exit 69; }}
[ -f "$mmx_script" ] && [ ! -L "$mmx_script" ] || {{ echo "mmx source is unavailable in the installed release" >&2; exit 69; }}
"$python" -I -S -B "$manifest_tool" verify --root "$release_root" --commit-sha "{release_sha}" --tree-sha "{tree_sha}" >/dev/null
exec "$python" -I -S -B "$mmx_script" "$@"
"""


def install(release_sha: str, target: Path) -> Path:
    if not _SHA_RE.fullmatch(release_sha):
        raise MmxInstallError("release SHA must be exact lowercase 40-hex")
    if not target.is_absolute():
        raise MmxInstallError("target path must be absolute")
    release_root = RELEASES_ROOT / release_sha
    try:
        info = release_root.lstat()
    except OSError:
        raise MmxInstallError("requested Executive release is not installed") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise MmxInstallError("requested Executive release is not a direct directory")
    if not PINNED_PYTHON.is_file() or not os.access(PINNED_PYTHON, os.X_OK):
        raise MmxInstallError("pinned Executive Python is unavailable")
    tree_sha = _manifest_identity(release_root, release_sha)
    try:
        verify_release(release_root, release_sha, tree_sha)
    except (OSError, ReleaseManifestError) as exc:
        raise MmxInstallError(f"Executive release verification failed: {exc}") from exc
    source = release_root / "scripts/mmx.py"
    try:
        source_info = source.lstat()
    except OSError:
        raise MmxInstallError("requested Executive release does not contain mmx") from None
    if stat.S_ISLNK(source_info.st_mode) or not stat.S_ISREG(source_info.st_mode):
        raise MmxInstallError("requested Executive release mmx is not a direct file")

    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    body = _wrapper(release_root, release_sha, tree_sha, PINNED_PYTHON)
    fd, raw_tmp = tempfile.mkstemp(prefix=".mmx.", dir=target.parent)
    temporary = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o755)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        target = install(args.release_sha, args.target.expanduser())
    except MmxInstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
