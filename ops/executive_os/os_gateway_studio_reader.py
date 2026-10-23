"""Bounded, descriptor-bound observation of the staged Studio Direct publication.

This module observes the fixed ``mastermind-os-publication`` layout without ever
trusting a pathname:

* every traversal starts anchored at ``/`` and descends one component at a
  time, holding every opened ancestor descriptor;
* every descendant is opened relative to a held parent descriptor with
  ``O_NOFOLLOW`` (plus ``O_DIRECTORY`` for directories; ``O_NONBLOCK`` and
  ``O_CLOEXEC`` always);
* before any payload read or enumeration the opened descriptor is fstat'd and
  compared against the parent-relative nofollow pre-open ``os.stat``, and the
  descriptor-bound macOS ACL observation from ``control_plane.fs_security``
  runs against that same pre-open identity, failing closed;
* identities and descriptors are rechecked before and after every read, and
  the whole held ancestry is rechecked deterministically while descending, so
  concurrent mutation refuses instead of being observed;
* every refusal is the fixed, non-echo ``StudioObservationError``
  (``gateway_studio_invalid``); no errno, path, or content is ever echoed.

The fixed observed uid is enforced on every observed object. The group id and
the home location are qualified caller data and carry no authority claim.
Node and backend tool locations come only from the bounded manifest bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PurePath
from typing import Callable, NoReturn

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl

__all__ = [
    "FIXED_OBSERVED_UID",
    "STUDIO_INSTANCE_KEY",
    "StudioFilesObservation",
    "StudioObservationError",
    "observe_studio_files",
]

# The publication runs as this fixed uid; it is enforced on every observed
# object. (Offline tests monkeypatch this constant to the test uid as a
# mechanical filesystem fixture; that is disclosure, not authority.)
FIXED_OBSERVED_UID = 501

# Fixed instance key; no selector may override it.
STUDIO_INSTANCE_KEY = "mastermind-os-publication"

_MANIFEST_NAME = "manifest.json"
_CONFIG_NAME = "config.json"
_DEPENDENCY_ROOT_NAME = "node_modules"
_METADATA_PATH_PARTS = (
    ".local",
    "share",
    "studio-direct-mcp",
    "private",
)
_PLIST_DIRECTORY_PARTS = (
    "Library",
    "LaunchAgents",
)

_METADATA_LIMIT = 1024 * 1024
_NODE_FILE_LIMIT = 256 * 1024 * 1024
_BACKEND_FILE_LIMIT = 16 * 1024 * 1024
_DEPENDENCY_FILE_LIMIT = 128 * 1024 * 1024
_DEPENDENCY_TREE_LIMIT = 512 * 1024 * 1024
_DEPENDENCY_ENTRY_LIMIT = 100_000
_DEPENDENCY_DEPTH_LIMIT = 128
_READ_CHUNK = 256 * 1024

_DIR_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_LEAF_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)

_IDENTITY_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_gid",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


class StudioObservationError(RuntimeError):
    """The fixed, non-echo refusal raised for every rejected observation."""

    def __init__(self) -> None:
        super().__init__("gateway_studio_invalid")


def _refuse() -> NoReturn:
    raise StudioObservationError() from None


@dataclass(frozen=True)
class StudioFilesObservation:
    """Everything one bounded observation of the publication produced."""

    manifest_bytes: bytes
    config_bytes: bytes
    plist_bytes: bytes
    installed_file_hashes: dict[str, str]
    node_sha256: str
    backend_sha256: str
    dependency_tree_sha256: str


def _require_same_object(pre: os.stat_result, post: os.stat_result) -> None:
    """Refuse unless the two stats describe the same unchanged object."""

    for field_name in _IDENTITY_FIELDS:
        if getattr(pre, field_name) != getattr(post, field_name):
            _refuse()


def _same_object(pre: os.stat_result, post: os.stat_result) -> bool:
    for field_name in _IDENTITY_FIELDS:
        if getattr(pre, field_name) != getattr(post, field_name):
            return False
    return True


def _observe_acl(name: str, fd: int, pre: os.stat_result) -> None:
    """Run the descriptor-bound ACL observation; any refusal fails closed."""

    try:
        if has_macos_acl(name, descriptor=fd, expected_identity=pre) is not False:
            _refuse()
    except FilesystemSecurityError:
        _refuse()


def _check_plain_name(name: object) -> str:
    """Accept only a flat, safe basename for a parent-relative open."""

    if not isinstance(name, str) or not name:
        _refuse()
    if "/" in name or "\0" in name or name in (".", ".."):
        _refuse()
    return name


def _check_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _refuse()
    return value


def _check_home(home: object) -> Path:
    if not isinstance(home, PurePath):
        _refuse()
    if not home.is_absolute():
        _refuse()
    parts = [part for part in home.parts if part not in ("/", "")]
    if not parts:
        _refuse()
    for part in parts:
        _check_plain_name(part)
    return home  # type: ignore[return-value]


def _check_source_file_names(source_file_names: object) -> tuple[str, ...]:
    if not isinstance(source_file_names, tuple):
        _refuse()
    if not source_file_names:
        _refuse()
    seen: set[str] = set()
    for name in source_file_names:
        _check_plain_name(name)
        if name in seen:
            _refuse()
        seen.add(name)  # type: ignore[arg-type]
    return source_file_names  # type: ignore[return-value]


def _check_manifest_path(value: object) -> tuple[str, ...]:
    """Accept only an absolute, normalized POSIX path; return its components."""

    if not isinstance(value, str) or not value:
        _refuse()
    if "\0" in value:
        _refuse()
    if not posixpath.isabs(value):
        _refuse()
    if posixpath.normpath(value) != value:
        _refuse()
    parts = [part for part in PurePosixPath(value).parts if part not in ("/",)]
    if not parts:
        _refuse()
    for part in parts:
        _check_plain_name(part)
    return tuple(parts)


class _TreeBudget:
    """Running dependency-tree counters shared by both hashing passes."""

    def __init__(self) -> None:
        self.entries = 1  # the dependency root itself
        self.bytes = 0

    def count_entry(self) -> None:
        self.entries += 1
        if self.entries > _DEPENDENCY_ENTRY_LIMIT:
            _refuse()

    def count_bytes(self, size: int) -> None:
        self.bytes += size
        if self.bytes > _DEPENDENCY_TREE_LIMIT:
            _refuse()


def _policy_root_prefix_dir(info: os.stat_result) -> None:
    """A root-owned, nonwritable, searchable traversal prefix directory.

    The observed uid reaches the owned subtree through the *other* bits, so
    other-execute is required and group/other write is forbidden. Owner read
    is not required here; this directory is never enumerated.
    """

    if info.st_uid != 0:
        _refuse()
    mode = info.st_mode
    if not stat.S_ISDIR(mode):
        _refuse()
    if not mode & stat.S_IXUSR:
        _refuse()
    if not mode & stat.S_IXOTH:
        _refuse()
    if mode & stat.S_IWGRP or mode & stat.S_IWOTH:
        _refuse()


def _make_owned_dir_policy(
    observed_uid: int, gid: int, *, enumerated: bool
) -> Callable[[os.stat_result], None]:
    """Require the observed uid/gid subtree directory policy.

    Owner search is required explicitly, so an 0400 mode refuses. Owner read
    is additionally required when the directory will be enumerated. Group and
    other write are always forbidden.
    """

    def _policy(info: os.stat_result) -> None:
        if info.st_uid != observed_uid or info.st_gid != gid:
            _refuse()
        mode = info.st_mode
        if not stat.S_ISDIR(mode):
            _refuse()
        if not mode & stat.S_IXUSR:
            _refuse()
        if enumerated and not mode & stat.S_IRUSR:
            _refuse()
        if mode & stat.S_IWGRP or mode & stat.S_IWOTH:
            _refuse()

    return _policy


def _make_owned_leaf_policy(
    observed_uid: int, gid: int, *, executable: bool
) -> Callable[[os.stat_result], None]:
    """Require the observed uid/gid regular-leaf policy.

    Leaves are regular, nlink 1, owner readable (owner executable when the
    leaf is an executable tool), with no group/other write.
    """

    def _policy(info: os.stat_result) -> None:
        if info.st_uid != observed_uid or info.st_gid != gid:
            _refuse()
        mode = info.st_mode
        if not stat.S_ISREG(mode):
            _refuse()
        if info.st_nlink != 1:
            _refuse()
        if not mode & stat.S_IRUSR:
            _refuse()
        if executable and not mode & stat.S_IXUSR:
            _refuse()
        if mode & stat.S_IWGRP or mode & stat.S_IWOTH:
            _refuse()

    return _policy


def _make_home_prefix_policy(
    observed_uid: int, gid: int
) -> Callable[[os.stat_result], None]:
    """Ancestor policy strictly above home, which is qualified caller data.

    Those ancestors are not observed payload: a root-owned or observed-uid
    searchable directory is accepted, anything else is a foreign uid and
    refuses. Strictness begins at home itself, where the observed uid/gid
    subtree policy applies.
    """

    def _policy(info: os.stat_result) -> None:
        mode = info.st_mode
        if not stat.S_ISDIR(mode):
            _refuse()
        if info.st_uid == 0:
            _policy_root_prefix_dir(info)
            return
        if info.st_uid == observed_uid:
            _make_owned_dir_policy(observed_uid, gid, enumerated=False)(info)
            return
        _refuse()

    return _policy


def _make_dispatch_dir_policy(
    observed_uid: int, gid: int
) -> Callable[[os.stat_result], None]:
    """Tool-prefix policy: root-owned nonwritable searchable or observed uid.

    This is only ever applied to ancestor components of a tool path from the
    manifest, plus home ancestors being handled by ``_make_home_prefix_policy``.
    A root-owned prefix must be nonwritable and searchable; an observed-uid
    directory uses the owned subtree policy; anything else is a foreign uid
    and refuses.
    """

    def _policy(info: os.stat_result) -> None:
        if info.st_uid == 0:
            _policy_root_prefix_dir(info)
            return
        if info.st_uid == observed_uid:
            _make_owned_dir_policy(observed_uid, gid, enumerated=False)(info)
            return
        _refuse()

    return _policy


class _Walk:
    """Holds every descriptor opened during one observation; closes all."""

    def __init__(self) -> None:
        self._fds: list[int] = []
        self._bindings: dict[int, tuple[int, str, os.stat_result]] = {}
        self._paths: dict[int, tuple[str, ...]] = {}
        self._links: dict[tuple[str, ...], tuple[os.stat_result, str]] = {}
        self._records: dict[tuple[str, ...], tuple[os.stat_result, bool, Callable]] = {}

    def adopt(self, fd: int) -> int:
        self._fds.append(fd)
        return fd

    def close(self, fd: int) -> None:
        try:
            os.close(fd)
        except OSError:
            _refuse()
        finally:
            if fd in self._fds:
                self._fds.remove(fd)
            self._bindings.pop(fd, None)
            self._paths.pop(fd, None)

    def close_all(self) -> None:
        failed = False
        for fd in reversed(self._fds):
            try:
                os.close(fd)
            except OSError:
                failed = True
        self._fds.clear()
        if failed:
            _refuse()

    def open_root(self) -> tuple[int, os.stat_result]:
        """Anchor the traversal at ``/`` with the root-prefix directory policy."""

        try:
            pre = os.stat("/", follow_symlinks=False)
        except OSError:
            _refuse()
        _policy_root_prefix_dir(pre)
        try:
            fd = os.open("/", _DIR_FLAGS)
        except OSError:
            _refuse()
        self.adopt(fd)
        try:
            post = os.fstat(fd)
            _require_same_object(pre, post)
            _policy_root_prefix_dir(post)
            _observe_acl("/", fd, pre)
        except BaseException:
            self.close(fd)
            raise
        self._paths[fd] = ()
        self._root_fd = fd
        self._root_info = post
        return fd, post

    def open_child(
        self,
        parent_fd: int,
        name: str,
        *,
        directory: bool,
        policy: Callable[[os.stat_result], None],
    ) -> tuple[int, os.stat_result]:
        """Open one descendant relative to a held parent descriptor.

        The parent-relative nofollow stat is taken first and policy is applied
        to it before any open, then the descriptor's fstat must describe the
        same unchanged object, then the same policy runs on the opened object,
        then the descriptor-bound ACL observation runs — all before any
        payload read or enumeration by the caller.
        """

        _check_plain_name(name)
        try:
            pre = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            _refuse()
        if directory:
            if not stat.S_ISDIR(pre.st_mode):
                _refuse()
        else:
            if not stat.S_ISREG(pre.st_mode):
                _refuse()
        policy(pre)
        try:
            fd = os.open(name, _DIR_FLAGS if directory else _LEAF_FLAGS, dir_fd=parent_fd)
        except OSError:
            _refuse()
        self.adopt(fd)
        try:
            post = os.fstat(fd)
            _require_same_object(pre, post)
            policy(post)
            _observe_acl(name, fd, pre)
        except BaseException:
            self.close(fd)
            raise
        self._bindings[fd] = (parent_fd, name, post)
        path = self._paths[parent_fd] + (name,)
        self._paths[fd] = path
        previous = self._records.get(path)
        if previous is not None:
            _require_same_object(previous[0], post)
        self._records[path] = (post, directory, policy)
        return fd, post

    def _recheck_binding(self, fd: int) -> None:
        binding = self._bindings.get(fd)
        if binding is not None:
            parent_fd, name, expected = binding
            self._recheck_binding(parent_fd)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            _require_same_object(expected, current)
            _require_same_object(expected, os.fstat(fd))
        else:
            _require_same_object(self._root_info, os.fstat(fd))

    def recheck_all(self) -> None:
        """Reopen recorded names through anchored descriptors, without payload IO."""
        children: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
        for path in self._records.keys() | self._links.keys():
            children.setdefault(path[:-1], []).append(path)
        self._recheck_binding(self._root_fd)
        def visit(parent_fd: int, parent: tuple[str, ...]) -> None:
            for path in sorted(children.get(parent, [])):
                if path in self._links:
                    expected, target = self._links[path]
                    _require_same_object(expected, os.stat(path[-1], dir_fd=parent_fd, follow_symlinks=False))
                    if os.readlink(path[-1], dir_fd=parent_fd) != target:
                        _refuse()
                    _require_same_object(expected, os.stat(path[-1], dir_fd=parent_fd, follow_symlinks=False))
                    continue
                expected, directory, policy = self._records[path]
                current = os.stat(path[-1], dir_fd=parent_fd, follow_symlinks=False)
                _require_same_object(expected, current)
                flags = _DIR_FLAGS if directory else _LEAF_FLAGS
                fd = os.open(path[-1], flags, dir_fd=parent_fd)
                try:
                    _require_same_object(expected, os.fstat(fd))
                    policy(os.fstat(fd))
                    _observe_acl(path[-1], fd, expected)
                    if directory:
                        visit(fd, path)
                    _require_same_object(expected, os.fstat(fd))
                    _require_same_object(expected, os.stat(path[-1], dir_fd=parent_fd, follow_symlinks=False))
                finally:
                    os.close(fd)
        visit(self._root_fd, ())
        self._recheck_binding(self._root_fd)

    def recheck_chain(self, chain: list[tuple[int, os.stat_result]]) -> None:
        """Deterministically recheck every held ancestor descriptor."""

        for fd, expected in chain:
            self._recheck_binding(fd)
            try:
                observed = os.fstat(fd)
            except OSError:
                _refuse()
            if not _same_object(expected, observed):
                _refuse()

    def read_bounded(
        self,
        fd: int,
        expected: os.stat_result,
        *,
        limit: int,
        positive: bool,
    ) -> bytes:
        """Read a metadata or staged leaf with pre/post identity rechecks."""

        try:
            before = os.fstat(fd)
        except OSError:
            _refuse()
        _require_same_object(expected, before)
        if before.st_size > limit:
            _refuse()
        if positive and before.st_size <= 0:
            _refuse()
        chunks: list[bytes] = []
        total = 0
        while True:
            self._recheck_binding(fd)
            _require_same_object(expected, os.fstat(fd))
            _observe_acl("held-leaf", fd, expected)
            try:
                chunk = os.read(fd, _READ_CHUNK)
            except OSError:
                _refuse()
            if not chunk:
                break
            total += len(chunk)
            if total > limit or total > before.st_size:
                _refuse()
            chunks.append(chunk)
        try:
            after = os.fstat(fd)
        except OSError:
            _refuse()
        _require_same_object(expected, after)
        data = b"".join(chunks)
        if len(data) != before.st_size:
            _refuse()
        if positive and not data:
            _refuse()
        return data

    def hash_bounded(
        self,
        fd: int,
        expected: os.stat_result,
        *,
        limit: int,
        budget: _TreeBudget | None = None,
    ) -> tuple[str, int]:
        """Stream a leaf through sha256 within the per-file bound."""

        try:
            before = os.fstat(fd)
        except OSError:
            _refuse()
        _require_same_object(expected, before)
        if before.st_size > limit:
            _refuse()
        hasher = hashlib.sha256()
        total = 0
        while True:
            self._recheck_binding(fd)
            _require_same_object(expected, os.fstat(fd))
            _observe_acl("held-leaf", fd, expected)
            try:
                chunk = os.read(fd, _READ_CHUNK)
            except OSError:
                _refuse()
            if not chunk:
                break
            total += len(chunk)
            if total > limit or total > before.st_size:
                _refuse()
            hasher.update(chunk)
        try:
            after = os.fstat(fd)
        except OSError:
            _refuse()
        _require_same_object(expected, after)
        if total != before.st_size:
            _refuse()
        if budget is not None:
            budget.count_bytes(total)
        return hasher.hexdigest(), total

    def descend(
        self,
        chain: list[tuple[int, os.stat_result]],
        components: tuple[str, ...] | list[str],
        *,
        policy: Callable[[os.stat_result], None],
        recheck: bool = True,
    ) -> list[tuple[int, os.stat_result]]:
        """Descend a chain of directories, holding every ancestor descriptor."""

        extended = list(chain)
        for component in components:
            if recheck:
                self.recheck_chain(extended)
            fd, info = self.open_child(extended[-1][0], component, directory=True, policy=policy)
            extended.append((fd, info))
        return extended

    def open_leaf(
        self,
        chain: list[tuple[int, os.stat_result]],
        name: str,
        *,
        policy: Callable[[os.stat_result], None],
        recheck: bool = True,
    ) -> tuple[int, os.stat_result, list[tuple[int, os.stat_result]]]:
        """Open a leaf off a held chain, rechecking the ancestry first."""

        if recheck:
            self.recheck_chain(chain)
        fd, info = self.open_child(chain[-1][0], name, directory=False, policy=policy)
        return fd, info, chain + [(fd, info)]

    def read_metadata_leaf(
        self,
        chain: list[tuple[int, os.stat_result]],
        name: str,
        *,
        policy: Callable[[os.stat_result], None],
    ) -> bytes:
        fd, info, held = self.open_leaf(chain, name, policy=policy)
        try:
            self.recheck_chain(held)
            return self.read_bounded(fd, info, limit=_METADATA_LIMIT, positive=True)
        finally:
            self.close(fd)


def _resolve_dependency_link(
    entries_map: dict[str, tuple[str, ...]],
    start_dir: str,
    target: str,
) -> None:
    """Resolve one collected relative symlink against collected entries only.

    ``entries_map`` maps every collected in-tree relative path to its kind
    tuple, so resolution never opens, stats, or reads any foreign target —
    the filesystem is not consulted at all. Absolute targets, escapes above
    the dependency root, dangling entries, and cycles all refuse.
    """

    if not isinstance(target, str) or not target:
        _refuse()
    if "\0" in target:
        _refuse()
    if target.startswith("/"):
        _refuse()
    tokens: list[str] = [
        part for part in target.split("/") if part not in ("", ".")
    ]
    jumps = 0
    seen_states: set[tuple[str, tuple[str, ...]]] = set()
    current = start_dir
    while tokens:
        state = (current, tuple(tokens))
        if state in seen_states:
            _refuse()
        seen_states.add(state)
        token = tokens.pop(0)
        if token == "..":
            if current == ".":
                _refuse()
            current = posixpath.dirname(current) or "."
            continue
        candidate = token if current == "." else current + "/" + token
        record = entries_map.get(candidate)
        if record is None:
            _refuse()
        if record[0] != "symlink":
            if tokens and record[0] != "directory":
                _refuse()
            current = candidate
            continue
        jumps += 1
        if jumps > _DEPENDENCY_DEPTH_LIMIT:
            _refuse()
        link_target = record[1]
        if not isinstance(link_target, str) or not link_target:
            _refuse()
        if link_target.startswith("/"):
            _refuse()
        tokens = [
            part for part in link_target.split("/") if part not in ("", ".")
        ] + tokens
    return None


def _dependency_pass(
    walk: _Walk,
    root_fd: int,
    root_info: os.stat_result,
    chain: list[tuple[int, os.stat_result]],
    owned_dir: Callable[[os.stat_result], None],
    owned_leaf: Callable[[os.stat_result], None],
    budget: _TreeBudget,
) -> list[tuple[object, ...]]:
    """Run one bounded, descriptor-bound pass over the dependency tree.

    The collected entries, ordering, tuple shapes, modes, file sizes, and file
    digests are byte-equivalent to the existing private_service dependency
    digest: root entry ``(".", "directory", mode)``, then one
    ``("directory", mode)`` / ``("symlink", mode, target)`` /
    ``("file", mode, size, digest)`` tuple per entry, sorted by relative path,
    JSON-encoded with tight separators. Symlink identity is rechecked around
    every readlink, and symlinks are resolved afterwards against the collected
    entries alone.
    """

    entries: list[tuple[object, ...]] = [
        (".", "directory", stat.S_IMODE(root_info.st_mode))
    ]
    entries_map: dict[str, tuple[str, ...]] = {".": ("directory",)}
    link_dirs: dict[str, str] = {}

    def visit(dir_fd: int, rel: str, depth: int, held: list[tuple[int, os.stat_result]]) -> None:
        walk.recheck_chain(held)
        try:
            names = sorted(os.listdir(dir_fd))
        except OSError:
            _refuse()
        for name in names:
            budget.count_entry()
            _check_plain_name(name)
            child_rel = name if rel == "." else rel + "/" + name
            try:
                pre = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError:
                _refuse()
            mode = stat.S_IMODE(pre.st_mode)
            if stat.S_ISLNK(pre.st_mode):
                if pre.st_uid != root_info.st_uid or pre.st_gid != root_info.st_gid or pre.st_nlink != 1:
                    _refuse()
                walk.recheck_chain(held)
                try:
                    target = os.readlink(name, dir_fd=dir_fd)
                except OSError:
                    _refuse()
                try:
                    after = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                except OSError:
                    _refuse()
                _require_same_object(pre, after)
                if not isinstance(target, str) or not target:
                    _refuse()
                link_path = walk._paths[dir_fd] + (name,)
                prior_link = walk._links.get(link_path)
                if prior_link is not None:
                    _require_same_object(prior_link[0], pre)
                    if prior_link[1] != target:
                        _refuse()
                walk._links[link_path] = (pre, target)
                entries.append((child_rel, "symlink", mode, target))
                entries_map[child_rel] = ("symlink", target)
                link_dirs[child_rel] = rel
            elif stat.S_ISDIR(pre.st_mode):
                if depth + 1 > _DEPENDENCY_DEPTH_LIMIT:
                    _refuse()
                entries.append((child_rel, "directory", mode))
                entries_map[child_rel] = ("directory",)
                fd, info = walk.open_child(
                    dir_fd, name, directory=True, policy=owned_dir
                )
                held.append((fd, info))
                try:
                    walk.recheck_chain(held)
                    visit(fd, child_rel, depth + 1, held)
                    walk.recheck_chain(held)
                finally:
                    held.pop()
                    walk.close(fd)
            elif stat.S_ISREG(pre.st_mode):
                fd, info = walk.open_child(
                    dir_fd, name, directory=False, policy=owned_leaf
                )
                try:
                    walk.recheck_chain(held + [(fd, info)])
                    digest, _size = walk.hash_bounded(
                        fd, info, limit=_DEPENDENCY_FILE_LIMIT, budget=budget
                    )
                finally:
                    walk.close(fd)
                entries.append((child_rel, "file", mode, info.st_size, digest))
                entries_map[child_rel] = ("file",)
            else:
                _refuse()

    visit(root_fd, ".", 0, chain + [(root_fd, root_info)])

    for link_rel in sorted(link_dirs):
        _resolve_dependency_link(
            entries_map, link_dirs[link_rel], entries_map[link_rel][1]
        )
    return entries


def _dependency_entries_payload(entries: list[tuple[object, ...]]) -> bytes:
    """Encode collected entries exactly as the private_service digest does."""

    payload = json.dumps(
        sorted(entries, key=lambda item: str(item[0])),
        sort_keys=False,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return payload


def _dependency_tree_digest(
    walk: _Walk,
    root_fd: int,
    root_info: os.stat_result,
    chain: list[tuple[int, os.stat_result]],
    owned_dir: Callable[[os.stat_result], None],
    owned_leaf: Callable[[os.stat_result], None],
) -> str:
    """Require two identical bounded passes so concurrent drift refuses."""

    first = _dependency_pass(walk, root_fd, root_info, chain, owned_dir, owned_leaf, _TreeBudget())
    first_digest = hashlib.sha256(
        _dependency_entries_payload(first)
    ).hexdigest()
    second = _dependency_pass(walk, root_fd, root_info, chain, owned_dir, owned_leaf, _TreeBudget())
    second_digest = hashlib.sha256(
        _dependency_entries_payload(second)
    ).hexdigest()
    if first_digest != second_digest:
        _refuse()
    return first_digest


def _traverse_tool(
    walk: _Walk,
    root_fd: int,
    components: tuple[str, ...],
    observed_uid: int,
    gid: int,
    home_parts: tuple[str, ...],
    *,
    executable: bool,
) -> tuple[str, int]:
    """Traverse one tool path from ``/`` and stream-hash its owned leaf.

    Components above home use the caller-data home-prefix policy; components
    inside home must be the observed uid/gid subtree; components outside home
    must be a root-owned nonwritable searchable prefix or an already
    transitioned observed-uid directory, never a foreign uid.
    """

    under_home = (
        len(components) > len(home_parts)
        and tuple(components[: len(home_parts)]) == tuple(home_parts)
    )
    home_prefix = _make_home_prefix_policy(observed_uid, gid)
    owned_dir = _make_owned_dir_policy(observed_uid, gid, enumerated=False)
    dispatch = _make_dispatch_dir_policy(observed_uid, gid)
    chain = [(root_fd, os.fstat(root_fd))]
    for index, component in enumerate(components[:-1]):
        if under_home:
            policy = home_prefix if index < len(home_parts) - 1 else owned_dir
        else:
            policy = dispatch
        walk.recheck_chain(chain)
        fd, info = walk.open_child(chain[-1][0], component, directory=True, policy=policy)
        chain.append((fd, info))
    owned_policy = _make_owned_leaf_policy(observed_uid, gid, executable=executable)
    def leaf_policy(info: os.stat_result) -> None:
        if info.st_uid != 0:
            owned_policy(info)
            return
        mode = info.st_mode
        if (not stat.S_ISREG(mode) or info.st_nlink != 1
                or mode & 0o022 or not mode & stat.S_IROTH
                or (executable and not mode & stat.S_IXOTH)):
            _refuse()
    fd, info, held = walk.open_leaf(chain, components[-1], policy=leaf_policy)
    try:
        walk.recheck_chain(held)
        if info.st_size <= 0:
            _refuse()
        digest, _total = walk.hash_bounded(fd, info, limit=_NODE_FILE_LIMIT if executable else _BACKEND_FILE_LIMIT)
    finally:
        walk.close(fd)
    return digest, info.st_size


def _decode_manifest(manifest_bytes: bytes) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Derive node and backend paths only from these same bounded bytes."""

    try:
        decoded = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _refuse()
    if not isinstance(decoded, dict):
        _refuse()
    node_components = _check_manifest_path(decoded.get("node"))
    backend_components = _check_manifest_path(decoded.get("backend"))
    return node_components, backend_components


def observe_studio_files(
    *,
    home: Path,
    uid: int,
    gid: int,
    source_file_names: tuple[str, ...],
) -> StudioFilesObservation:
    """Observe the staged publication once, bounded and fail-closed.

    ``uid`` must equal the fixed observed uid. ``gid`` and ``home`` are
    qualified caller data and carry no authority claim: they select which
    staged subtree is observed, never whether observation is permitted.
    ``source_file_names`` are strict, unique, flat staged basenames hashed
    into ``installed_file_hashes``. Every other field is derived from the
    fixed instance layout and the manifest bytes alone.
    """

    for flag_name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_CLOEXEC"):
        flag = getattr(os, flag_name, None)
        if type(flag) is not int or flag <= 0:
            _refuse()
    observed_uid = _check_int(uid)
    if observed_uid != FIXED_OBSERVED_UID:
        _refuse()
    gid_value = _check_int(gid)
    if gid_value < 0:
        _refuse()
    home_path = _check_home(home)
    staged_names = _check_source_file_names(source_file_names)

    home_parts = tuple(
        part for part in home_path.parts if part not in ("/", "")
    )
    plist_name = "com.mastermind.studio-direct-private.%s.plist" % (
        STUDIO_INSTANCE_KEY,
    )

    walk = _Walk()
    try:
        root_fd, _root_info = walk.open_root()

        # Home ancestors strictly above home are qualified caller data; home
        # itself and everything beneath it must be the observed uid/gid.
        above_home = _make_home_prefix_policy(observed_uid, gid_value)
        home_chain = walk.descend(
            [(root_fd, os.fstat(root_fd))],
            home_parts[:-1],
            policy=above_home,
        )
        home_dir = _make_owned_dir_policy(observed_uid, gid_value, enumerated=False)
        home_chain = walk.descend(
            home_chain, home_parts[-1:], policy=home_dir
        )

        metadata_dirs = _make_owned_dir_policy(observed_uid, gid_value, enumerated=False)
        metadata_leaf = _make_owned_leaf_policy(observed_uid, gid_value, executable=False)
        base_chain = walk.descend(
            home_chain, _METADATA_PATH_PARTS + (STUDIO_INSTANCE_KEY,), policy=metadata_dirs
        )

        plist_chain = walk.descend(
            home_chain, _PLIST_DIRECTORY_PARTS, policy=metadata_dirs
        )
        plist_bytes = walk.read_metadata_leaf(
            plist_chain, plist_name, policy=metadata_leaf
        )

        manifest_bytes = walk.read_metadata_leaf(
            base_chain, _MANIFEST_NAME, policy=metadata_leaf
        )
        config_bytes = walk.read_metadata_leaf(
            base_chain, _CONFIG_NAME, policy=metadata_leaf
        )
        node_components, backend_components = _decode_manifest(manifest_bytes)

        installed_file_hashes: dict[str, str] = {}
        for name in sorted(staged_names):
            fd, info, held = walk.open_leaf(base_chain, name, policy=metadata_leaf)
            try:
                walk.recheck_chain(held)
                data = walk.read_bounded(
                    fd, info, limit=_METADATA_LIMIT, positive=False
                )
            finally:
                walk.close(fd)
            installed_file_hashes[name] = hashlib.sha256(data).hexdigest()

        node_digest, _node_size = _traverse_tool(
            walk,
            root_fd,
            node_components,
            observed_uid,
            gid_value,
            home_parts,
            executable=True,
        )
        backend_digest, _backend_size = _traverse_tool(
            walk,
            root_fd,
            backend_components,
            observed_uid,
            gid_value,
            home_parts,
            executable=False,
        )

        dependency_dir = _make_owned_dir_policy(observed_uid, gid_value, enumerated=True)
        dependency_leaf = _make_owned_leaf_policy(observed_uid, gid_value, executable=False)
        dep_fd, dep_info = walk.open_child(
            base_chain[-1][0], _DEPENDENCY_ROOT_NAME, directory=True, policy=dependency_dir
        )
        try:
            dependency_tree_sha256 = _dependency_tree_digest(
                walk,
                dep_fd,
                dep_info,
                base_chain,
                dependency_dir,
                dependency_leaf,
            )
        finally:
            walk.close(dep_fd)

        walk.recheck_all()
        return StudioFilesObservation(
            manifest_bytes=manifest_bytes,
            config_bytes=config_bytes,
            plist_bytes=plist_bytes,
            installed_file_hashes=installed_file_hashes,
            node_sha256=node_digest,
            backend_sha256=backend_digest,
            dependency_tree_sha256=dependency_tree_sha256,
        )
    except StudioObservationError:
        raise
    except FilesystemSecurityError:
        raise StudioObservationError() from None
    except Exception:
        raise StudioObservationError() from None
    finally:
        walk.close_all()
