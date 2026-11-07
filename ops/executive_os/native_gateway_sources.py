"""Native dependency qualification subordinate to the Executive release owner.

The release manifest selects this inventory. This module publishes no state,
admits no work, loads no native package, and never discovers expected hashes
from the live environment. The existing owner holds the inventory and root
namespaces; bounded transient descriptors verify the selected complete trees.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

SCHEMA = "mastermind.hermes_native_dependencies/v1"
MAX_INVENTORY_BYTES = 8 * 1024 * 1024
MAX_MEMBERS = 32768
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")


class NativeSourceRefusal(ValueError):
    pass


def _refuse():
    raise NativeSourceRefusal("native dependency custody refused")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _refuse()
        result[key] = value
    return result


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _relative(value):
    if (type(value) is not str or not 1 <= len(value) <= 4096
            or value.startswith("/") or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in {"", ".", ".."} for p in value.split("/"))
            or PurePosixPath(value).as_posix() != value):
        _refuse()
    return value


def _qualified(fd, acl_check, *, directory, expected=None):
    info = os.fstat(fd)
    if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            or info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
            or info.st_mode & 0o7000 or (not directory and info.st_nlink != 1)
            or (stat.S_IMODE(info.st_mode) & (0o005 if directory else 0o004))
               != (0o005 if directory else 0o004)):
        _refuse()
    acl_check(fd, directory)
    if expected is not None and stat.S_IMODE(info.st_mode) != expected["mode"]:
        _refuse()
    return info


class NativeSourceClosure:
    """One verified closure inside one existing held release context.

    Only root-owned, single-link regular files and root-owned directories
    are accepted. The role cannot change them. Checks compare every saved
    inode/ctime and complete directory membership; hashing streams once,
    without using the first-party source cache or retaining one fd per file.
    """

    def __init__(self, owner, recipe, acl_check):
        self.owner = owner
        self.recipe = recipe
        self.acl_check = acl_check
        self.roots = tuple(Path(p) for p in recipe["import_roots"])
        self.closed = False
        self.snapshots = {}
        self.directories = {}
        self.expected = {}
        self.root_fds = {}
        self.total = 0
        inventory = recipe["dependency_inventory"]
        raw = owner.read(Path(inventory["path"]), MAX_INVENTORY_BYTES)
        if (len(raw) != inventory["size"]
                or hashlib.sha256(raw).hexdigest() != inventory["sha256"]):
            _refuse()
        try:
            document = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, UnicodeError, RecursionError):
            _refuse()
        if (type(document) is not dict or set(document) != {"schema", "roots"}
                or document["schema"] != SCHEMA or type(document["roots"]) is not list
                or len(document["roots"]) != len(self.roots)):
            _refuse()
        count = 0
        for root, row in zip(self.roots, document["roots"]):
            if (type(row) is not dict or set(row) != {"path", "entries"}
                    or row["path"] != str(root) or type(row["entries"]) is not list):
                _refuse()
            entries = {}
            for entry in row["entries"]:
                if type(entry) is not dict:
                    _refuse()
                relative = _relative(entry.get("path"))
                kind = entry.get("type")
                extra = {"size", "sha256"} if kind == "file" else set()
                if (kind not in {"file", "directory"}
                        or set(entry) != {"path", "type", "mode"} | extra
                        or relative in entries or type(entry["mode"]) is not int
                        or not 0 <= entry["mode"] <= 0o777 or entry["mode"] & 0o022):
                    _refuse()
                if kind == "file" and (
                    type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_FILE_BYTES
                    or type(entry["sha256"]) is not str or not _SHA.fullmatch(entry["sha256"])
                ):
                    _refuse()
                entries[relative] = entry
                count += 1
                if count > MAX_MEMBERS:
                    _refuse()
            if not entries:
                _refuse()
            for relative in entries:
                parent = PurePosixPath(relative).parent.as_posix()
                if parent != "." and (parent not in entries or entries[parent]["type"] != "directory"):
                    _refuse()
            self.expected[root] = entries
            self.root_fds[root] = owner.hold(root, directory=True)
            found = set()
            self._walk(root, self.root_fds[root], "", first=True, found=found)
            if found != set(entries):
                _refuse()
        owner.check()

    def _qualified(self, fd, *, directory, expected=None):
        return _qualified(fd, self.acl_check, directory=directory, expected=expected)

    def _walk(self, root, fd, relative, *, first, found):
        before = self._qualified(fd, directory=True,
                                 expected=self.expected[root].get(relative))
        key = (root, relative)
        names = tuple(sorted(os.listdir(fd)))
        if first:
            self.directories[key] = (names, _identity(before))
        elif self.directories.get(key) != (names, _identity(before)):
            _refuse()
        for name in names:
            child = f"{relative}/{name}" if relative else name
            entry = self.expected[root].get(child)
            if entry is None:
                _refuse()
            found.add(child)
            directory = entry["type"] == "directory"
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            child_fd = os.open(name, flags, dir_fd=fd)
            try:
                info = self._qualified(child_fd, directory=directory, expected=entry)
                if directory:
                    self._walk(root, child_fd, child, first=first, found=found)
                else:
                    child_key = (root, child)
                    if info.st_size != entry["size"]:
                        _refuse()
                    if first:
                        self.total += info.st_size
                        if self.total > MAX_TOTAL_BYTES:
                            _refuse()
                        digest = hashlib.sha256()
                        size = 0
                        while True:
                            data = os.read(child_fd, 65536)
                            if not data:
                                break
                            size += len(data)
                            if size > entry["size"]:
                                _refuse()
                            digest.update(data)
                        if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                            _refuse()
                        self.snapshots[child_key] = _identity(info)
                    elif self.snapshots.get(child_key) != _identity(info):
                        _refuse()
                if (_identity(os.fstat(child_fd)) != _identity(info)
                        or _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(info)):
                    _refuse()
            finally:
                os.close(child_fd)
        if _identity(os.fstat(fd)) != _identity(before):
            _refuse()

    def check(self):
        if self.closed:
            _refuse()
        for root, fd in self.root_fds.items():
            found = set()
            self._walk(root, fd, "", first=False, found=found)
            if found != set(self.expected[root]):
                _refuse()

    def close(self):
        self.closed = True


def _readable_path(owner, path, acl_check, *, directory):
    fd = owner.hold(path, directory=directory)
    _qualified(fd, acl_check, directory=directory)
    for parent in path.parents:
        info = os.fstat(owner.hold(parent, directory=True))
        # Native roles are neither root nor members of root's group.
        if not stat.S_IMODE(info.st_mode) & 0o001:
            _refuse()
    return fd


def candidate_inventory(owner, roots, acl_check):
    """Deterministic candidate DATA; never supplies its own expected digest."""
    rows, count, total = [], 0, 0

    def walk(fd, prefix, entries):
        nonlocal count, total
        before = _qualified(fd, acl_check, directory=True)
        names = tuple(sorted(os.listdir(fd)))
        for name in names:
            relative = _relative(f"{prefix}/{name}" if prefix else name)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            directory = stat.S_ISDIR(info.st_mode)
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            member = os.open(name, flags, dir_fd=fd)
            try:
                opened = _qualified(member, acl_check, directory=directory)
                if _identity(opened) != _identity(info):
                    _refuse()
                count += 1
                if count > MAX_MEMBERS:
                    _refuse()
                entry = {"path": relative, "type": "directory" if directory else "file",
                         "mode": stat.S_IMODE(info.st_mode)}
                if directory:
                    walk(member, relative, entries)
                else:
                    if not 0 <= info.st_size <= MAX_FILE_BYTES:
                        _refuse()
                    total += info.st_size
                    if total > MAX_TOTAL_BYTES:
                        _refuse()
                    digest, size = hashlib.sha256(), 0
                    while True:
                        block = os.read(member, 65536)
                        if not block:
                            break
                        size += len(block)
                        if size > info.st_size:
                            _refuse()
                        digest.update(block)
                    if size != info.st_size:
                        _refuse()
                    entry.update(size=size, sha256=digest.hexdigest())
                entries.append(entry)
                if (_identity(os.fstat(member)) != _identity(info)
                        or _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(info)):
                    _refuse()
            finally:
                os.close(member)
        if _identity(os.fstat(fd)) != _identity(before) or tuple(sorted(os.listdir(fd))) != names:
            _refuse()

    for value in roots:
        root = Path(value)
        entries = []
        walk(_readable_path(owner, root, acl_check, directory=True), "", entries)
        if not entries:
            _refuse()
        rows.append({"path": str(root), "entries": sorted(entries, key=lambda row: row["path"])})
    raw = (json.dumps({"schema": SCHEMA, "roots": rows}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    if len(raw) > MAX_INVENTORY_BYTES:
        _refuse()
    owner.check()
    return raw


def prepare_inventory(owner, recipe, acl_check):
    """Publish/adopt exact frozen bytes, then qualify them through the owner.

    Invoked by the existing root enrollment transaction after immutable source
    publication and before any unit/config selection. No live tree is repaired;
    no expected digest is inferred. A missing artifact is materialized only
    if its complete candidate bytes match the independently frozen commitment.
    """
    if os.getuid() != 0 or os.geteuid() != 0:
        _refuse()
    inventory = recipe["dependency_inventory"]
    path = Path(inventory["path"])
    if path == owner.root or owner.root in path.parents:
        _refuse()
    parent = _readable_path(owner, path.parent, acl_check, directory=True)
    try:
        os.stat(path.name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        raw = candidate_inventory(owner, recipe["import_roots"], acl_check)
        if len(raw) != inventory["size"] or hashlib.sha256(raw).hexdigest() != inventory["sha256"]:
            _refuse()
        fd, name = tempfile.mkstemp(prefix=".hermes-native-inventory-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                os.fchmod(stream.fileno(), 0o444)
                os.fchown(stream.fileno(), 0, 0)
                stream.flush()
                os.fsync(stream.fileno())
            owner.check()
            try:
                # Atomic no-replace publication. An existing name is adopted
                # only by the exact-byte/identity verifier below.
                os.link(temporary.name, path.name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
            except FileExistsError:
                pass
            temporary.unlink()
            os.fsync(parent)
        finally:
            temporary.unlink(missing_ok=True)
    _readable_path(owner, path, acl_check, directory=False)
    closure = NativeSourceClosure(owner, recipe, acl_check)
    try:
        closure.check()
        owner.check()
    finally:
        closure.close()
