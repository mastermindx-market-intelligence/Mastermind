#!/usr/bin/env python3
"""Preview fixed Linux package caches for the EXISTING storage-sweeper owner.

No deletion, cleanup eligibility grant, worker, network or process-control action.
A preview is an expiring observation, never an apply token. Production entry uses
only the current user's fixed roots; fixture injection is available in Python.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

SCHEMA = "mastermind.linux_cache_preview.v1"
MAX_ENTRIES = 20000
MAX_DEPTH = 12
MAX_SECONDS = 5.0
MAX_BYTES = 256 * 1024 ** 3
MAX_JOURNAL_BYTES = 2 * 1024 * 1024
CACHE_ROOTS = {"pip": (".cache/pip", {"http", "http-v2", "wheels", "selfcheck"}),
               "npm": (".npm/_cacache", {"content-v2", "index-v5", "tmp"})}


class PreviewHeld(ValueError):
    pass


def _signature(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _owned(s, uid, *, directory=False):
    if s.st_uid != uid or s.st_mode & 0o022:
        raise PreviewHeld("ownership_or_write_mode")
    if directory and not stat.S_ISDIR(s.st_mode):
        raise PreviewHeld("directory_identity")


def _directory(path, uid):
    """O_NOFOLLOW on EACH component, not just the final cache name."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise PreviewHeld("path_identity")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=fd)
            os.close(fd)
            fd = new
        _owned(os.fstat(fd), uid, directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _home_path(home, relative, uid):
    current = Path(home)
    for part in Path(relative).parts[:-1]:
        current /= part
        try:
            _owned(current.lstat(), uid, directory=True)
        except FileNotFoundError:
            return Path(home) / relative
    return current / Path(relative).name


def _journal_unknown(state_dir, home, uid):
    """Reuse the existing maintenance journal; no second effect registry."""
    path = state_dir / "generated-cache-trim.jsonl"
    if not os.path.lexists(path):
        return set()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        _owned(before, uid)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_JOURNAL_BYTES:
            raise PreviewHeld("maintenance_journal_unknown")
        raw = os.read(fd, MAX_JOURNAL_BYTES + 1)
        if _signature(before) != _signature(os.fstat(fd)) or len(raw) != before.st_size:
            raise PreviewHeld("maintenance_journal_unknown")
    finally:
        os.close(fd)
    latest = {}
    try:
        for line in raw.splitlines():
            row = json.loads(line)
            if type(row) is not dict or row.get("event") not in {"PREPARE", "VERIFIED"} or type(row.get("path")) is not str:
                raise ValueError()
            latest[row["path"]] = row["event"]
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise PreviewHeld("maintenance_journal_unknown") from None
    return {name for name, (relative, _) in CACHE_ROOTS.items()
            if any(event == "PREPARE" and
                   (Path(p) == home / relative or home / relative in Path(p).parents
                    or Path(p) in (home / relative).parents)
                   for p, event in latest.items())}


def _live_paths(uid, *, proc=Path("/proc")):
    """Same-user cwd/exe/open-FD paths. Any incomplete census holds preview."""
    result = set()
    deadline = time.monotonic() + MAX_SECONDS
    try:
        processes = list(proc.iterdir())
        if len(processes) > MAX_ENTRIES:
            raise PreviewHeld("live_use_unknown")
        for pid in processes:
            if time.monotonic() > deadline:
                raise PreviewHeld("live_use_unknown")
            if not pid.name.isdigit() or int(pid.name) == os.getpid():
                continue
            try:
                owner = pid.stat()
            except FileNotFoundError:
                continue  # Exited before this process was selected.
            if owner.st_uid != uid:
                continue
            start = (pid / "stat").read_text()
            if start[start.rfind(")") + 2:].split()[0] in {"Z", "X"}:
                continue
            links = [pid / "cwd", pid / "exe"]
            links += list((pid / "fd").iterdir())
            if len(links) > MAX_ENTRIES:
                raise PreviewHeld("live_use_unknown")
            for link in links:
                try:
                    value = os.readlink(link)
                except FileNotFoundError:
                    # A changing same-user process/FD is not a complete census.
                    raise PreviewHeld("live_use_unknown") from None
                if value.startswith("/"):
                    result.add(value.removesuffix(" (deleted)"))
            if (pid / "stat").read_text() != start:
                # CPU counters change normally; compare PID start identity only.
                def identity(text):
                    return text[text.rfind(")") + 2:].split()[19]
                if identity((pid / "stat").read_text()) != identity(start):
                    raise PreviewHeld("live_use_unknown")
    except (OSError, ValueError, IndexError):
        raise PreviewHeld("live_use_unknown") from None
    return result


def _names(fd, deadline):
    names = []
    with os.scandir(fd) as scan:
        for entry in scan:
            if len(names) >= MAX_ENTRIES or time.monotonic() > deadline:
                raise PreviewHeld("inventory_bound")
            names.append(entry.name)
    return sorted(names)


def _inventory(fd, uid, allowed, deadline):
    entries, logical, allocated = 0, 0, 0
    digest = hashlib.sha256()
    root = os.fstat(fd)
    seen = set()

    def walk(directory, prefix, depth):
        nonlocal entries, logical, allocated
        if depth > MAX_DEPTH or time.monotonic() > deadline:
            raise PreviewHeld("inventory_bound")
        before = os.fstat(directory)
        names = _names(directory, deadline)
        if depth == 0 and any(name not in allowed for name in names):
            raise PreviewHeld("unrecognized_cache_layout")
        for name in names:
            entries += 1
            if entries > MAX_ENTRIES or time.monotonic() > deadline:
                raise PreviewHeld("inventory_bound")
            if not name or name in {".", ".."} or "lock" in name.casefold():
                raise PreviewHeld("cache_lock_or_unknown_entry")
            s = os.stat(name, dir_fd=directory, follow_symlinks=False)
            _owned(s, uid)
            if s.st_dev != root.st_dev:
                raise PreviewHeld("filesystem_changed")
            rel = prefix + name
            if stat.S_ISDIR(s.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
                try:
                    if _signature(s) != _signature(os.fstat(child)):
                        raise PreviewHeld("inventory_changed")
                    walk(child, rel + "/", depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(s.st_mode) and s.st_nlink == 1:
                inode = (s.st_dev, s.st_ino)
                if inode in seen:
                    raise PreviewHeld("hardlink_or_duplicate")
                seen.add(inode)
                logical += s.st_size
                allocated += s.st_blocks * 512
                if max(logical, allocated) > MAX_BYTES:
                    raise PreviewHeld("inventory_bound")
            else:
                raise PreviewHeld("symlink_hardlink_or_special")
            digest.update(json.dumps([rel, _signature(s)], ensure_ascii=True).encode())
        if _signature(before) != _signature(os.fstat(directory)):
            raise PreviewHeld("inventory_changed")
    walk(fd, "", 0)
    return {"entries": entries, "logical_bytes": logical,
            "allocated_bytes": allocated, "inventory_sha256": digest.hexdigest()}


def _admission_current(home, active, active_fd, active_before, lock_fd, lock_before, uid):
    """Rejoin the named namespace after all blocking readers/inventory finish."""
    if (home / "lanes/ext/active").resolve(strict=True) != active:
        raise PreviewHeld("directory_identity")
    named_fd = _directory(active, uid)
    try:
        # The held directory must still be the one reached through its name.
        for current in (os.fstat(active_fd), os.fstat(named_fd)):
            if _signature(current)[:4] != _signature(active_before)[:4]:
                raise PreviewHeld("directory_identity")
        named_lock = os.stat(".admission.lock", dir_fd=named_fd, follow_symlinks=False)
        if (_signature(lock_before) != _signature(os.fstat(lock_fd))
                or _signature(lock_before) != _signature(named_lock)):
            raise PreviewHeld("admission_lock_identity")
        if set(os.listdir(named_fd)) != {".admission.lock"}:
            raise PreviewHeld("active_lane_or_reconciliation_hold")
        # Also withhold a transient namespace change whose entry was removed.
        if any(_signature(os.fstat(fd)) != _signature(active_before)
               for fd in (active_fd, named_fd)):
            raise PreviewHeld("directory_identity")
    finally:
        os.close(named_fd)


def preview(*, home=None, uid=None, platform=None, live_reader=None):
    home = Path.home() if home is None else Path(home)
    uid = os.getuid() if uid is None else uid
    platform = sys.platform if platform is None else platform
    result = {"schema": SCHEMA, "preview_only": True, "cleanup_authorized": False,
              "observed_at": time.time(), "status": "HELD", "reasons": [], "caches": []}
    if platform != "linux" or uid == 0:
        result["reasons"] = ["linux_nonroot_owner_required"]
        return result
    lock_fd = active_fd = None
    try:
        home_fd = _directory(home, uid)
        os.close(home_fd)
        # Use the SAME physical lane lock; never create it or clear a marker.
        # A symlinked lanes root is resolved by its existing owner, not retargeted.
        active = (home / "lanes/ext/active").resolve(strict=True)
        active_fd = _directory(active, uid)
        lock_fd = os.open(".admission.lock", os.O_RDWR | os.O_NOFOLLOW,
                          dir_fd=active_fd)
        lock = os.fstat(lock_fd)
        _owned(lock, uid)
        if not stat.S_ISREG(lock.st_mode) or lock.st_nlink != 1:
            raise PreviewHeld("admission_lock_identity")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PreviewHeld("admission_busy") from None
        if _signature(lock) != _signature(os.stat(".admission.lock", dir_fd=active_fd, follow_symlinks=False)):
            raise PreviewHeld("admission_lock_identity")
        # Every extra entry, including reconciliation/policy/unknown markers,
        # conservatively holds this first preview subset.
        if set(os.listdir(active_fd)) != {".admission.lock"}:
            raise PreviewHeld("active_lane_or_reconciliation_hold")
        active_before = os.fstat(active_fd)
        state = home / ".local/state/mastermind/storage-cleanup"
        if state.exists():
            state_fd = _directory(state, uid)
            os.close(state_fd)
        unknown = _journal_unknown(state, home, uid)
        reader = live_reader or (lambda: _live_paths(uid))
        live = reader()
        deadline = time.monotonic() + MAX_SECONDS
        for name, (relative, allowed) in CACHE_ROOTS.items():
            row = {"cache": name, "relative_root": relative, "status": "HELD"}
            result["caches"].append(row)
            try:
                if name in unknown:
                    raise PreviewHeld("maintenance_effect_unknown")
                target = _home_path(home, relative, uid)
                if not os.path.lexists(target):
                    row["status"] = "ABSENT"
                    continue
                if any(p == str(target) or p.startswith(str(target) + "/") for p in live):
                    raise PreviewHeld("live_use")
                fd = _directory(target, uid)
                try:
                    before = os.fstat(fd)
                    if before.st_dev != os.fstat(active_fd).st_dev:
                        raise PreviewHeld("different_worker_filesystem")
                    volume = os.fstatvfs(fd)
                    row["filesystem_available_bytes"] = volume.f_bavail * volume.f_frsize
                    row.update(_inventory(fd, uid, allowed, deadline))
                    current = reader()
                    if any(p == str(target) or p.startswith(str(target) + "/") for p in current):
                        raise PreviewHeld("live_use")
                    if name in _journal_unknown(state, home, uid):
                        raise PreviewHeld("maintenance_effect_unknown")
                    if _signature(before) != _signature(target.lstat()):
                        raise PreviewHeld("inventory_changed")
                finally:
                    os.close(fd)
                row["status"] = "PREVIEWED"
            except (OSError, PreviewHeld):
                exc = sys.exc_info()[1]
                row.clear()
                row.update(cache=name, relative_root=relative, status="HELD",
                           reason=str(exc) if isinstance(exc, PreviewHeld) else "filesystem_unavailable")
        _admission_current(home, active, active_fd, active_before, lock_fd, lock, uid)
        if any(r["status"] == "PREVIEWED" for r in result["caches"]):
            result["status"] = "PREVIEWED"
    except (OSError, PreviewHeld):
        exc = sys.exc_info()[1]
        result["reasons"] = [str(exc) if isinstance(exc, PreviewHeld) else "owner_or_lock_unavailable"]
        # No earlier cache observation remains publishable after scope drift.
        result["status"] = "HELD"
        result["caches"] = [dict(cache=row["cache"], relative_root=row["relative_root"],
                                 status="HELD", reason=result["reasons"][0])
                            for row in result["caches"]]
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        if active_fd is not None:
            os.close(active_fd)
    return result


def retain_preview(result, *, home=None, uid=None):
    """One new receipt in the EXISTING sweeper state directory, no apply record."""
    home = Path.home() if home is None else Path(home)
    uid = os.getuid() if uid is None else uid
    relative = ".local/state/mastermind/storage-cleanup"
    directory = _directory(home, uid)
    try:
        for part in Path(relative).parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            try:
                _owned(os.fstat(child), uid, directory=True)
            except BaseException:
                os.close(child)
                raise
            os.close(directory)
            directory = child
    except BaseException:
        os.close(directory)
        raise
    name = "linux-cache-preview-" + uuid.uuid4().hex + ".json"
    raw = (json.dumps(result, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(raw) > 32768:
        os.close(directory)
        raise PreviewHeld("receipt_bound")
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    return {"receipt": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__)
    parser.add_argument("--expected-source-sha", required=True)
    args = parser.parse_args(argv)
    expected = args.expected_source_sha
    if (len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected)
            or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != expected):
        raise SystemExit("preview source mismatch")
    result = preview()
    receipt = retain_preview(result)
    print(json.dumps({**result, **receipt}, sort_keys=True))
    return 0 if result["status"] == "PREVIEWED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
