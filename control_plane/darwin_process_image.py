"""Observe the actual Darwin executable of an already-owned child.

No spawn, signal, peer identity, grant or recovery authority. The process owner
supplies its live child PID and independently compares this observation to its
binary pin. A launcher pathname is never substituted for the kernel image.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

from control_plane.codex_worker import ProcessInspector
from control_plane.codex_provider_realm import _native_open
from control_plane.executive_ambient_process import _proc_pid_path
from control_plane.executive_process_identity import _observe_process_instance

_MAX_IMAGE_BYTES = 1024 * 1024 * 1024


class DarwinProcessImageError(ValueError):
    pass


def _refuse():
    raise DarwinProcessImageError('owned_darwin_image_unqualified')


def _kernel_observation(pid):
    inspector = ProcessInspector()
    boot = inspector.boot_session_id()
    if re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}', boot) is None:
        _refuse()  # never accept the inspector's adapter-local fallback
    first = _observe_process_instance(pid)
    process = inspector.inspect(pid)
    path = _proc_pid_path(pid)
    second = _observe_process_instance(pid)
    if (first != second or path is None or not path.is_absolute()
            or '..' in path.parts or str(path) != os.path.normpath(path)
            or not process.parent_pid or not process.start_identity):
        _refuse()
    return boot, first, process, path


def inspect_owned_darwin_image(pid: int) -> dict:
    """Bracket kernel instance/path and held protected executable bytes."""
    if sys.platform != 'darwin' or type(pid) is not int or not 0 < pid < 2**31:
        _refuse()
    try:
        before = _kernel_observation(pid)
        boot, instance, process, path = before
        # Existing owner-checked no-follow/ACL walk; no user path or symlink
        # fallback. Also rechecks visible leaf and held FD on context exit.
        with _native_open(path) as (fd, info):
            if (not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111
                    or not 0 < info.st_size <= _MAX_IMAGE_BYTES):
                _refuse()
            digest = hashlib.sha256()
            total = 0
            while total <= info.st_size:
                data = os.read(fd, min(1024 * 1024, info.st_size + 1 - total))
                if not data:
                    break
                digest.update(data)
                total += len(data)
            if total != info.st_size or _kernel_observation(pid) != before:
                _refuse()
            image = dict(device=info.st_dev, inode=info.st_ino, mode=info.st_mode,
                uid=info.st_uid, gid=info.st_gid, size=info.st_size,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns,
                sha256=digest.hexdigest(), boot_id=boot,
                executable_path=str(path), exec_instance=dataclasses.asdict(instance),
                process_start_identity='darwin:' + process.start_identity,
                **dataclasses.asdict(process))
        if _kernel_observation(pid) != before:
            _refuse()
        return image
    except DarwinProcessImageError:
        raise
    except Exception as exc:
        raise DarwinProcessImageError('owned_darwin_image_unavailable') from exc
