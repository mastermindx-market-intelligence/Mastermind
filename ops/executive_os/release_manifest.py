"""Create or verify the root-owned exact-SHA Executive release manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mastermind.executive_release_manifest/v1"
MANIFEST_NAME = ".executive-release-manifest.json"


class ReleaseManifestError(RuntimeError):
    pass


def _has_acl(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    completed = subprocess.run(
        ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        raise ReleaseManifestError(f"cannot inspect release ACL: {path.name}")
    return b"+" in completed.stdout


def _validate_owned_info(info: os.stat_result, *, label: str) -> None:
    if info.st_uid != 0 or info.st_gid != 0:
        raise ReleaseManifestError(f"release object is not root:wheel: {label}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseManifestError(f"release object is writable by group or other: {label}")


def _release_root(path: Path) -> Path:
    lexical = Path(path)
    info = lexical.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ReleaseManifestError("release root must be a direct real directory")
    _validate_owned_info(info, label=".")
    if stat.S_IMODE(info.st_mode) & 0o055 != 0o055:
        raise ReleaseManifestError("release root must be traversable by both service UIDs")
    if _has_acl(lexical):
        raise ReleaseManifestError("release root has a filesystem ACL")
    return lexical.resolve(strict=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entries(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        names.sort()
        filenames.sort()
        for name in [*names, *filenames]:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative == MANIFEST_NAME:
                continue
            info = path.lstat()
            _validate_owned_info(info, label=relative)
            if _has_acl(path):
                raise ReleaseManifestError(f"release object has a filesystem ACL: {relative}")
            common = {
                "path": relative,
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
            }
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                if os.path.isabs(target):
                    raise ReleaseManifestError(f"absolute release symlink is forbidden: {relative}")
                resolved = (path.parent / target).resolve(strict=False)
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ReleaseManifestError(
                        f"release symlink escapes the release root: {relative}"
                    ) from exc
                result.append({**common, "type": "symlink", "target": target})
            elif stat.S_ISDIR(info.st_mode):
                result.append({**common, "type": "directory"})
            elif stat.S_ISREG(info.st_mode):
                result.append(
                    {
                        **common,
                        "type": "file",
                        "size": info.st_size,
                        "sha256": _sha256_file(path),
                    }
                )
            else:
                raise ReleaseManifestError(f"unsupported release object: {relative}")
    return result


def _document(root: Path, commit_sha: str, tree_sha: str) -> dict[str, Any]:
    if len(commit_sha) != 40 or len(tree_sha) != 40:
        raise ReleaseManifestError("release commit and tree identities must be exact SHA-1 values")
    return {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "entries": _entries(root),
    }


def create(root: Path, commit_sha: str, tree_sha: str) -> Path:
    root = _release_root(root)
    manifest = root / MANIFEST_NAME
    if manifest.exists() or manifest.is_symlink():
        raise ReleaseManifestError("release manifest already exists")
    value = _document(root, commit_sha, tree_sha)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{MANIFEST_NAME}.", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o444)
        if os.geteuid() == 0:
            os.chown(temporary, 0, 0)
        temporary.replace(manifest)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return manifest


def verify(root: Path, commit_sha: str, tree_sha: str) -> dict[str, Any]:
    root = _release_root(root)
    manifest = root / MANIFEST_NAME
    info = manifest.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ReleaseManifestError("release manifest is not a regular file")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseManifestError("release manifest is writable by group or other")
    _validate_owned_info(info, label=MANIFEST_NAME)
    if _has_acl(manifest):
        raise ReleaseManifestError("release manifest has a filesystem ACL")
    try:
        persisted = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError("release manifest is invalid") from exc
    observed = _document(root, commit_sha, tree_sha)
    if persisted != observed:
        raise ReleaseManifestError("installed release differs from its exact-SHA manifest")
    return persisted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--tree-sha", required=True)
    args = parser.parse_args()
    if args.command == "create":
        create(args.root, args.commit_sha, args.tree_sha)
    else:
        verify(args.root, args.commit_sha, args.tree_sha)
    print(json.dumps({"ok": True, "commit_sha": args.commit_sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
