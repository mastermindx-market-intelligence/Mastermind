"""Fixed-file writer for the incumbent Studio commission preparation owner.

The caller supplies an already-qualified mmx-workspace receipt, never a web path.
Every component is opened without following links; the only creatable file is
research/executive_commissions/COMMISSION.md. Existing different bytes are never
overwritten. No Git, credential, workspace allocator or request listener lives here.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

MAX_BYTES = 512 * 1024
PARTS = ("research", "executive_commissions", "COMMISSION.md")


class CommissionFileRefused(ValueError):
    pass


def _directory(parent: int, name: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        os.close(descriptor)
        raise CommissionFileRefused("commission directory refused")
    return descriptor


def _root(workspace: Path) -> int:
    if not workspace.is_absolute() or any(part in ("", ".", "..") for part in workspace.parts[1:]):
        raise CommissionFileRefused("workspace path refused")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in workspace.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_fd
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise CommissionFileRefused("workspace owner refused")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read(parent: int) -> bytes | None:
    try:
        descriptor = os.open(PARTS[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o022
                or not 0 < info.st_size <= MAX_BYTES):
            raise CommissionFileRefused("commission file refused")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(MAX_BYTES + 1)
        after = os.fstat(descriptor)
        stable = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(content) != info.st_size or stable(after) != stable(info):
            raise CommissionFileRefused("commission file changed")
        return content
    finally:
        os.close(descriptor)


def commission_file(workspace: Path, content: bytes | None = None) -> dict:
    """Read-only reconcile when content=None; otherwise one exclusive write.

    The parent owner must authorize and requalify custody before invoking this.
    Any exception after invocation is uncertainty; this function never cleans up,
    overwrites, retries, publishes, or classifies an absent Job.
    """
    if content is not None:
        if type(content) is not bytes or not 0 < len(content) <= MAX_BYTES or b"\0" in content:
            raise CommissionFileRefused("commission bytes refused")
        try:
            content.decode("utf-8", errors="strict")
        except UnicodeError:
            raise CommissionFileRefused("commission encoding refused") from None
    descriptors = [_root(workspace)]
    try:
        for name in PARTS[:-1]:
            try:
                descriptors.append(_directory(descriptors[-1], name, create=content is not None))
            except FileNotFoundError:
                return {"status": "absent"}
        existing = _read(descriptors[-1])
        if existing is not None:
            digest = hashlib.sha256(existing).hexdigest()
            if content is not None and existing != content:
                return {"status": "conflict", "content_sha256": digest}
            return {"status": "matched", "content_sha256": digest}
        if content is None:
            return {"status": "absent"}
        file_fd = os.open(PARTS[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                          dir_fd=descriptors[-1])
        with os.fdopen(file_fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(descriptors[-1])
        observed = _read(descriptors[-1])
        if observed != content:
            raise CommissionFileRefused("commission write unqualified")
        return {"status": "written", "content_sha256": hashlib.sha256(content).hexdigest()}
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def main() -> int:
    import base64
    import json
    import sys
    try:
        if len(sys.argv) != 1:
            raise CommissionFileRefused("fixed invocation required")
        raw = sys.stdin.buffer.read(720_897)
        if len(raw) > 720_896:
            raise CommissionFileRefused("input budget")
        value = json.loads(raw)
        if (type(value) is not dict or set(value) != {"workspace_path", "content_base64"}
                or type(value["workspace_path"]) is not str or type(value["content_base64"]) is not str):
            raise CommissionFileRefused("closed writer input required")
        result = commission_file(Path(value["workspace_path"]), base64.b64decode(value["content_base64"], validate=True))
        sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
        return 0
    except Exception:
        sys.stdout.write('{"status":"effect_unknown"}\n')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
