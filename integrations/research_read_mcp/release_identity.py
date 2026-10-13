"""Verify installed archive bytes against an independently pinned stage manifest.

The expected digest must come from secure owner configuration. This verifier
does not qualify dependency completeness, install files or create that trust.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat

from .runtime import RuntimeRefused, _identity, _json, read_secure_json

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MANIFEST_FIELDS = frozenset({
    "schema", "state", "mastermind_commit", "mastermind_tree", "macro_commit", "macro_tree",
    "dependency_lock_sha256", "macro_import_closure", "files", "members",
})
_MAX_BYTES = 64 * 1024 * 1024
_MAX_MEMBERS = 8192


def _refuse():
    raise RuntimeRefused("ARCHIVE_IDENTITY_REFUSED")


def _safe_path(value):
    if type(value) is not str or not value or len(value) > 500:
        _refuse()
    path = PurePosixPath(value)
    if (value == "." or path.is_absolute() or str(path) != value or ".." in path.parts
            or any(part in {".git", ".lane"} or part.startswith(".env") for part in path.parts)
            or "\\" in value or "\x00" in value):
        _refuse()
    return path


def _file_digest(path, expected_size, expected_uid):
    descriptor = None
    try:
        before = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != expected_uid
                or before.st_mode & 0o022 or before.st_nlink != 1
                or before.st_size != expected_size):
            _refuse()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if _identity(before) != _identity(os.fstat(descriptor)):
            _refuse()
        digest, count = hashlib.sha256(), 0
        while True:
            chunk = os.read(descriptor, min(65536, expected_size - count + 1))
            if not chunk:
                break
            count += len(chunk)
            if count > expected_size:
                _refuse()
            digest.update(chunk)
        if (count != expected_size or _identity(before) != _identity(os.fstat(descriptor))
                or _identity(before) != _identity(path.stat(follow_symlinks=False))):
            _refuse()
        return digest.hexdigest(), _identity(before)
    except Exception:
        _refuse()
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                raise RuntimeRefused("ARCHIVE_CLOSE_UNCERTAIN") from None


def _walk(root, expected_uid):
    files, directories = set(), {}
    stack = [root]
    while stack:
        directory = stack.pop()
        info = directory.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != expected_uid
                or info.st_mode & 0o022):
            _refuse()
        directories[directory] = _identity(info)
        if len(directories) > _MAX_MEMBERS:
            _refuse()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                _safe_path(relative)
                if entry.is_symlink():
                    _refuse()
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.add(relative)
                else:
                    _refuse()
                if len(files) + len(directories) + len(stack) > _MAX_MEMBERS:
                    _refuse()
    return files, directories


def verify_archive_release(path: str, commit: str, tree: str, *, project: str,
                           manifest_path: str, expected_manifest_sha256: str,
                           manifest_owner_uid: int, release_owner_uid: int = 0):
    """Return a byte-integrity receipt; no deployment/readiness claim is made."""
    try:
        if (project not in {"mastermind", "macro"} or type(project) is not str
                or any(type(value) is not str or _SHA.fullmatch(value) is None
                       for value in (commit, tree))
                or type(expected_manifest_sha256) is not str
                or _DIGEST.fullmatch(expected_manifest_sha256) is None
                or type(release_owner_uid) is not int or release_owner_uid < 0):
            _refuse()
        root = Path(path)
        if (not root.is_absolute() or str(root) != path or root.name != commit
                or any(ancestor.is_symlink() for ancestor in (root, *root.parents))):
            _refuse()
        raw = read_secure_json(manifest_path, expected_owner_uid=manifest_owner_uid,
                               maximum=4 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
            _refuse()
        manifest = _json(raw, 4 * 1024 * 1024)
        if (type(manifest) is not dict or set(manifest) != _MANIFEST_FIELDS
                or manifest["schema"] != "mastermind.research_read_stage.v1"
                or manifest["state"] != "INERT_CANDIDATE"
                or manifest[project + "_commit"] != commit
                or manifest[project + "_tree"] != tree
                or type(manifest["members"]) is not dict
                or set(manifest["members"]) != {"mastermind", "macro"}):
            _refuse()
        rows = manifest["members"][project]
        if type(rows) is not list or not 0 < len(rows) <= _MAX_MEMBERS:
            _refuse()
        expected, total = {}, 0
        for row in rows:
            if type(row) is not dict or set(row) != {"path", "bytes", "sha256"}:
                _refuse()
            name = _safe_path(row["path"]).as_posix()
            size, digest = row["bytes"], row["sha256"]
            if (name in expected or type(size) is not int or not 0 <= size <= _MAX_BYTES
                    or type(digest) is not str or _DIGEST.fullmatch(digest) is None):
                _refuse()
            expected[name] = size, digest
            total += size
        if total > _MAX_BYTES:
            _refuse()
        files, directories = _walk(root, release_owner_uid)
        if files != set(expected):
            _refuse()
        expected_directories = {PurePosixPath(".")}
        for name in expected:
            expected_directories.update(PurePosixPath(name).parents)
        if {PurePosixPath(directory.relative_to(root).as_posix()) for directory in directories} != expected_directories:
            _refuse()
        identities = {}
        for name, (size, digest) in expected.items():
            actual, identity = _file_digest(root / name, size, release_owner_uid)
            if actual != digest:
                _refuse()
            identities[name] = identity
        # A later change cannot be hidden by checking only each file in isolation.
        final_files, final_directories = _walk(root, release_owner_uid)
        if final_files != files or final_directories != directories:
            _refuse()
        for name, identity in identities.items():
            if _identity((root / name).stat(follow_symlinks=False)) != identity:
                _refuse()
        if any(ancestor.is_symlink() for ancestor in (root, *root.parents)):
            _refuse()
        return {"state": "ARCHIVE_BYTES_VERIFIED", "project": project,
                "commit": commit, "tree": tree, "manifest_sha256": expected_manifest_sha256,
                "member_count": len(expected), "bytes": total,
                "dependency_closure": "OWNER_QUALIFICATION_REQUIRED"}
    except RuntimeRefused:
        raise
    except Exception:
        _refuse()
