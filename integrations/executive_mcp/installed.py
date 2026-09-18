"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

import configparser
import ctypes
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from control_plane import ceo_boot_packet, executive_ceo_ingress, executive_inbox
from integrations.executive_mcp.adapter import (
    ExecutiveMcpGateway, GatewayConfig, _open_readonly_runtime,
)
from integrations.executive_mcp.schemas import (
    GatewayError, MODIFYING_TOOL, READ_TIMEOUT_SECONDS, ServerMode,
    validate_tool_arguments,
)


PacketRunner = Callable[..., Mapping[str, Any]]


_default_packet_runner = ceo_boot_packet.bounded_subprocess_runner
_PACKET_SETTLEMENT_MARGIN_SECONDS = 2.0
_INSTALLED_PACKET_TOTAL_TIMEOUT_SECONDS = READ_TIMEOUT_SECONDS - 2.0


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _direct_git_directory(path: Path, *, label: str) -> Path | None:
    git_metadata = path / ".git"
    try:
        metadata_stat = git_metadata.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        ) from exc
    if not stat.S_ISDIR(metadata_stat.st_mode):
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        )
    objects_root = git_metadata / "objects"
    try:
        objects_stat = objects_root.lstat()
    except OSError as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        ) from exc
    if not stat.S_ISDIR(objects_stat.st_mode) or stat.S_ISLNK(objects_stat.st_mode):
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        )

    fixed_markers = (
        git_metadata / "commondir",
        git_metadata / "shallow",
        objects_root / "info" / "alternates",
        objects_root / "info" / "http-alternates",
    )
    try:
        if any(marker.exists() or marker.is_symlink() for marker in fixed_markers):
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository topology is unsafe"
            )

        config_path = git_metadata / "config"
        config_stat = config_path.lstat()
        if not stat.S_ISREG(config_stat.st_mode) or config_stat.st_size > 256 * 1024:
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository topology is unsafe"
            )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        config_fd = os.open(config_path, flags)
        try:
            before = os.fstat(config_fd)
            payload = bytearray()
            while len(payload) <= 256 * 1024:
                chunk = os.read(config_fd, 64 * 1024)
                if not chunk:
                    break
                payload.extend(chunk)
            after = os.fstat(config_fd)
        finally:
            os.close(config_fd)
        if len(payload) > 256 * 1024 or (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode
        ):
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository topology is unsafe"
            )
        parser = configparser.RawConfigParser(
            interpolation=None, strict=False, allow_no_value=True,
        )
        parser.read_string(bytes(payload).decode("utf-8", errors="strict"))
        for section in parser.sections():
            normalized = " ".join(section.lower().split())
            keys = {key.lower() for key, _value in parser.items(section, raw=True)}
            if normalized == "include" or normalized.startswith("includeif "):
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )
            if normalized == "extensions" and keys & {"partialclone", "worktreeconfig"}:
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )
            if normalized.startswith("remote ") and keys & {
                "partialclonefilter", "promisor", "receivepack", "uploadpack", "vcs",
            }:
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )
            if normalized.startswith("credential") and "helper" in keys:
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )
            if normalized == "core" and keys & {"gitproxy", "sshcommand"}:
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )

        pack_dir = git_metadata / "objects" / "pack"
        if pack_dir.exists():
            if not pack_dir.is_dir() or pack_dir.is_symlink():
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )
            if any(entry.name.endswith(".promisor") for entry in os.scandir(pack_dir)):
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )
    except GatewayError:
        raise
    except OSError as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        ) from exc
    return git_metadata


def _installed_child_env(*, code_root: Path, macro_root: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": os.fspath(macro_root),
        # Macro Agent OS reads P0 state from the immutable installed release,
        # never from the control-owned administrative checkout.  Pin Terminal to a
        # deliberately absent child so ambient sibling discovery cannot make the
        # installed brief depend on another checkout outside this composition.
        "MACRO_MASTERMIND_REPO": os.fspath(code_root),
        "MACRO_TERMINAL_REPO": os.fspath(code_root / ".executive-no-terminal-repo"),
    }


def _git_blob_oid(payload: bytes) -> str:
    digest = hashlib.sha1(usedforsecurity=False)  # Git object ids are SHA-1 (40 hex chars).
    digest.update(f"blob {len(payload)}\0".encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


def _seal_stat(digest: Any, *, rel: str, kind: str, observed: os.stat_result) -> None:
    rel_bytes = os.fsencode(rel)
    digest.update(len(rel_bytes).to_bytes(8, "big"))
    digest.update(rel_bytes)
    digest.update(kind.encode("ascii") + b"\0")
    fields = (
        observed.st_dev, observed.st_ino, observed.st_mode, observed.st_nlink,
        observed.st_uid, observed.st_gid, observed.st_size,
        observed.st_mtime_ns, observed.st_ctime_ns, getattr(observed, "st_flags", 0),
    )
    digest.update((",".join(str(value) for value in fields) + "\n").encode("ascii"))


def _worktree_path_sets(root: Path) -> tuple[dict[str, str], set[str], str]:
    """Return raw paths plus a mutation-sensitive metadata generation seal."""
    leaves: dict[str, str] = {}
    directories: set[str] = set()
    seal = hashlib.sha256()
    root_stat = root.lstat()
    if not stat.S_ISDIR(root_stat.st_mode):
        raise OSError("installed worktree root is not a directory")
    _seal_stat(seal, rel="", kind="directory", observed=root_stat)
    stack: list[tuple[Path, str]] = [(root, "")]
    while stack:
        directory, prefix = stack.pop()
        with os.scandir(directory) as raw_entries:
            entries = sorted(raw_entries, key=lambda entry: os.fsencode(entry.name))
        for entry in entries:
            if not prefix and entry.name == ".git":
                continue
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            observed = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(observed.st_mode):
                kind = "directory"
                directories.add(rel)
                stack.append((Path(entry.path), rel))
            elif stat.S_ISLNK(observed.st_mode):
                kind = "symlink"
                leaves[rel] = kind
            elif stat.S_ISREG(observed.st_mode):
                kind = "regular"
                leaves[rel] = kind
            else:
                kind = "other"
                leaves[rel] = kind
            _seal_stat(seal, rel=rel, kind=kind, observed=observed)
    return leaves, directories, seal.hexdigest()


def _tree_directory_paths(leaves: set[str]) -> set[str]:
    """Directories Git implies from tracked leaf paths; Git has no empty-directory objects."""
    directories: set[str] = set()
    for rel in leaves:
        parts = rel.split("/")
        for depth in range(1, len(parts)):
            directories.add("/".join(parts[:depth]))
    return directories


def _raw_worktree_blob_oid(path: Path, *, mode: str) -> str:
    """Hash raw worktree bytes without Git attributes, filters, index, or ignore rules."""
    if mode == "120000":
        st = path.lstat()
        if not stat.S_ISLNK(st.st_mode):
            raise OSError("tracked symlink is not a symlink")
        return _git_blob_oid(os.fsencode(os.readlink(path)))
    if mode not in {"100644", "100755"}:
        raise OSError("unsupported tracked mode")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("tracked file is not regular")
        expected_exec = mode == "100755"
        if bool(before.st_mode & 0o111) != expected_exec:
            raise OSError("tracked executable mode differs")
        digest = hashlib.sha1(usedforsecurity=False)
        digest.update(f"blob {before.st_size}\0".encode("ascii"))
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
        after = os.fstat(fd)
        if total != before.st_size or (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode
        ):
            raise OSError("tracked file moved during observation")
        return digest.hexdigest()
    finally:
        os.close(fd)


_MACRO_BRIEF_FIXED_CONTENT = frozenset({
    "scripts/__init__.py",
    "scripts/agentos.py",
    "scripts/audit_stranded_work.py",
    "config/mastermind_programs.yml",
    "data/governance/active_builds.json",
    "data/governance/.ceo_brief_last",
})
_MACRO_RECORD_DIRS = (
    "agentos/workstreams/",
    "agentos/decisions/",
    "agentos/discoveries/",
    "agentos/handoffs/",
)


def _macro_brief_content_paths(paths: set[str]) -> set[str]:
    """Tracked bytes that ``agentos.py brief --json --no-remember`` can consume."""
    selected = set(paths & _MACRO_BRIEF_FIXED_CONTENT)
    for rel in paths:
        for prefix in _MACRO_RECORD_DIRS:
            if not rel.startswith(prefix):
                continue
            leaf = rel[len(prefix):]
            if leaf.endswith(".md") and "/" not in leaf:
                selected.add(rel)
            break
    return selected


def _content_paths_for_scope(paths: set[str], scope: str) -> set[str]:
    if scope == "all":
        return set(paths)
    if scope == "identity":
        return set()
    if scope == "macro_brief":
        return _macro_brief_content_paths(paths)
    raise ValueError(f"unknown installed snapshot content scope: {scope}")


def _clean_git_snapshot(
    path: Path, *, runner: PacketRunner, env: Mapping[str, str], label: str,
    content_scope: str = "all", include_seal: bool = False,
) -> str | tuple[str, str]:
    """Bind HEAD plus raw path existence, hashing only bytes the named reader consumes."""
    git_metadata = _direct_git_directory(path, label=label)
    real_checkout = git_metadata is not None

    def observe(args: list[str], *, max_bytes: int) -> str:
        try:
            result = runner(
                ["git", *args], cwd=path, timeout=10.0,
                max_bytes=max_bytes, env=env,
            )
        except Exception as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} observation failed"
            ) from exc
        if not isinstance(result, Mapping):
            raise GatewayError("backend_unavailable", f"installed {label} observation failed")
        if any(
            result.get(flag) is True
            for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
        ):
            raise GatewayError("backend_unavailable", f"installed {label} observation failed")
        stdout = result.get("stdout")
        if result.get("code") != 0 or type(stdout) is not str:
            raise GatewayError("backend_unavailable", f"installed {label} observation failed")
        return stdout

    # Synthetic fixture runners use plain directories and retain the historical
    # one-status observation contract. Production installed roots are real checkouts
    # and use the raw object/tree verifier below.
    if not real_checkout:
        stdout = observe(
            ["status", "--porcelain=v2", "--branch", "--untracked-files=all"],
            max_bytes=256 * 1024,
        )
        oid: str | None = None
        dirty = False
        for line in stdout.splitlines():
            if line.startswith("# branch.oid "):
                if oid is not None:
                    raise GatewayError(
                        "backend_unavailable", f"installed {label} identity is ambiguous"
                    )
                oid = line.removeprefix("# branch.oid ").strip()
            elif line.startswith("# ") or not line:
                continue
            else:
                dirty = True
        if dirty:
            raise GatewayError("backend_unavailable", f"installed {label} checkout is not clean")
        if not _valid_sha(oid):
            raise GatewayError("backend_unavailable", f"installed {label} HEAD is unavailable")
        if include_seal:
            synthetic_seal = hashlib.sha256(
                ("synthetic\0" + oid + "\0" + stdout).encode("utf-8")
            ).hexdigest()
            return oid, synthetic_seal
        return oid

    head = observe(["rev-parse", "--verify", "HEAD^{commit}"], max_bytes=256).strip()
    if not _valid_sha(head):
        raise GatewayError("backend_unavailable", f"installed {label} HEAD is unavailable")

    tree = observe(
        ["ls-tree", "-r", "-z", "--full-tree", head],
        max_bytes=32 * 1024 * 1024,
    )
    expected: dict[str, tuple[str, str]] = {}
    for record in tree.split("\0"):
        if not record:
            continue
        meta, sep, rel = record.partition("\t")
        parts = meta.split()
        if not sep or len(parts) != 3:
            raise GatewayError("backend_unavailable", f"installed {label} tree is malformed")
        mode, object_type, oid = parts
        if (
            object_type != "blob"
            or mode not in {"100644", "100755", "120000"}
            or not _valid_sha(oid)
            or not rel
            or rel in expected
        ):
            raise GatewayError("backend_unavailable", f"installed {label} tree is unsupported")
        expected[rel] = (mode, oid)

    object_expectations: dict[str, str] = {head: "commit"}
    for _rel, (_mode, object_oid) in expected.items():
        object_expectations[object_oid] = "blob"
    object_input = ("\n".join(object_expectations) + "\n").encode("ascii")
    try:
        object_result = runner(
            ["git", "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
            cwd=path, timeout=10.0, max_bytes=32 * 1024 * 1024, env=env,
            input_bytes=object_input,
        )
    except Exception as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        ) from exc
    if not isinstance(object_result, Mapping) or any(
        object_result.get(flag) is True
        for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
    ):
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        )
    object_stdout = object_result.get("stdout")
    if object_result.get("code") != 0 or type(object_stdout) is not str:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        )
    observed_objects: dict[str, str] = {}
    for line in object_stdout.splitlines():
        parts = line.split()
        if (
            len(parts) != 3
            or not _valid_sha(parts[0])
            or parts[1] not in {"blob", "commit"}
            or not parts[2].isdigit()
            or parts[0] in observed_objects
        ):
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository objects are incomplete"
            )
        observed_objects[parts[0]] = parts[1]
    if observed_objects != object_expectations:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        )

    expected_leaves = set(expected)
    expected_directories = _tree_directory_paths(expected_leaves)
    expected_types = {
        rel: ("symlink" if mode == "120000" else "regular")
        for rel, (mode, _oid) in expected.items()
    }
    try:
        actual_types, actual_directories, metadata_seal = _worktree_path_sets(path)
    except OSError as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} worktree observation failed"
        ) from exc
    if actual_types != expected_types or actual_directories != expected_directories:
        raise GatewayError("backend_unavailable", f"installed {label} worktree path set differs")
    if content_scope == "macro_brief" and "symlink" in expected_types.values():
        # Agent OS uses Path.exists() across authored artifact/ownership prefixes.
        # A symlink can make that result depend on an external target that HEAD does
        # not bind, so a production Macro snapshot with symlinks needs a separately
        # reviewed projection instead of silently widening this reader.
        raise GatewayError("backend_unavailable", f"installed {label} symlinks are unsupported")

    try:
        content_paths = _content_paths_for_scope(set(expected), content_scope)
    except ValueError as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} content scope is invalid"
        ) from exc
    for rel in sorted(content_paths):
        mode, expected_oid = expected[rel]
        try:
            observed_oid = _raw_worktree_blob_oid(path / rel, mode=mode)
        except OSError as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} worktree observation failed"
            ) from exc
        if observed_oid != expected_oid:
            raise GatewayError("backend_unavailable", f"installed {label} worktree bytes differ")

    post_head = observe(["rev-parse", "--verify", "HEAD^{commit}"], max_bytes=256).strip()
    if post_head != head:
        raise GatewayError("backend_unavailable", f"installed {label} HEAD changed")
    return (head, metadata_seal) if include_seal else head


_IS_DARWIN = os.uname().sysname == "Darwin"
_DARWIN_CLONEFILE: Any | None = None


def _clonefile_callable() -> Any:
    global _DARWIN_CLONEFILE
    if _DARWIN_CLONEFILE is None:
        library = ctypes.CDLL(None, use_errno=True)
        clonefile = library.clonefile
        clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        clonefile.restype = ctypes.c_int
        _DARWIN_CLONEFILE = clonefile
    return _DARWIN_CLONEFILE


def _clone_regular_file(source: Path, destination: Path) -> None:
    if _IS_DARWIN:
        clonefile = _clonefile_callable()
        if clonefile(os.fsencode(source), os.fsencode(destination), 0) != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, os.strerror(error_number), os.fspath(source))
        return
    shutil.copy2(source, destination, follow_symlinks=False)


def _clone_tree(source: Path, destination: Path, *, deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise TimeoutError("repository materialization exceeded its deadline")
    source_stat = source.lstat()
    if stat.S_ISDIR(source_stat.st_mode):
        destination.mkdir(mode=stat.S_IMODE(source_stat.st_mode))
        with os.scandir(source) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            _clone_tree(Path(entry.path), destination / entry.name, deadline=deadline)
        shutil.copystat(source, destination, follow_symlinks=False)
        return
    if stat.S_ISREG(source_stat.st_mode):
        _clone_regular_file(source, destination)
        return
    if stat.S_ISLNK(source_stat.st_mode):
        destination.symlink_to(os.readlink(source), target_is_directory=False)
        return
    raise OSError(f"unsupported repository materialization entry: {source}")


@contextmanager
def _materialized_macro_root(source: Path, *, timeout: float) -> Iterator[Path]:
    if not (source / ".git").is_dir() or (source / ".git").is_symlink():
        yield source
        return
    try:
        with tempfile.TemporaryDirectory(prefix="mmx-executive-macro-") as temporary:
            temporary_root = Path(temporary).resolve()
            if _IS_DARWIN and temporary_root.stat().st_dev != source.stat().st_dev:
                raise OSError("copy-on-write materialization requires one filesystem")
            materialized = temporary_root / "macro"
            budget = max(0.25, min(8.0, float(timeout) / 2.0))
            _clone_tree(source, materialized, deadline=time.monotonic() + budget)
            yield materialized
    except GatewayError:
        raise
    except (OSError, TimeoutError) as exc:
        raise GatewayError(
            "backend_unavailable", "installed Macro materialization failed"
        ) from exc


def _project_macro_identity(
    packet: dict[str, Any], *, materialized_root: Path, canonical_root: Path,
) -> dict[str, Any]:
    if materialized_root == canonical_root:
        return packet
    projected = dict(packet)
    raw_macro = packet.get("macro")
    macro_doc = dict(raw_macro) if isinstance(raw_macro, Mapping) else {}
    macro_doc["root"] = os.fspath(canonical_root)
    raw_candidates = macro_doc.get("candidates_tried")
    if isinstance(raw_candidates, list):
        candidates: list[Any] = []
        for item in raw_candidates:
            if isinstance(item, Mapping):
                candidate = dict(item)
                if candidate.get("path") == os.fspath(materialized_root):
                    candidate["path"] = os.fspath(canonical_root)
                candidates.append(candidate)
            else:
                candidates.append(item)
        macro_doc["candidates_tried"] = candidates
    projected["macro"] = macro_doc
    return projected


def _inner_packet_timeout(total_timeout: float) -> float:
    if total_timeout <= 0:
        raise GatewayError("backend_unavailable", "installed boot-packet timeout is invalid")
    margin = min(_PACKET_SETTLEMENT_MARGIN_SECONDS, max(0.05, total_timeout / 3.0))
    return max(0.01, total_timeout - margin)


class InstalledBootPacketCollector:
    """Build one canonical packet from immutable code plus stable clean data roots."""

    def __init__(
        self, *, source_root: Path, macro_root: Path, code_root: Path,
        python_executable: Path, runner: PacketRunner | None = None,
        expected_source_sha: str | None = None,
    ) -> None:
        self._source_root = Path(source_root).resolve()
        self._macro_root = Path(macro_root).resolve()
        self._code_root = Path(code_root).resolve()
        # Preserve the configured environment entrypoint. Resolving a venv-style
        # symlink to its base interpreter would silently drop that environment's
        # site-packages under -I and recreate the missing-dependency failure.
        self._python = Path(python_executable).absolute()
        self._runner = runner or _default_packet_runner
        if not all(
            path.is_absolute()
            for path in (
                self._source_root, self._macro_root, self._code_root, self._python,
            )
        ):
            raise ValueError("installed boot-packet coordinates must be absolute")
        if expected_source_sha is not None and not _valid_sha(expected_source_sha):
            raise ValueError("expected installed source SHA must be lowercase hexadecimal")
        self._expected_source_sha = expected_source_sha

    def _snapshot_pair(self, env: Mapping[str, str]) -> tuple[str, str, str, str]:
        source_observation = _clean_git_snapshot(
            self._source_root, runner=self._runner, env=env, label="Mastermind source",
            content_scope="identity", include_seal=True,
        )
        macro_observation = _clean_git_snapshot(
            self._macro_root, runner=self._runner, env=env, label="Macro source",
            content_scope="macro_brief", include_seal=True,
        )
        if not isinstance(source_observation, tuple) or not isinstance(macro_observation, tuple):
            raise GatewayError("backend_unavailable", "installed snapshot seal is unavailable")
        source_sha, source_seal = source_observation
        macro_sha, macro_seal = macro_observation
        if self._expected_source_sha is not None and source_sha != self._expected_source_sha:
            raise GatewayError("backend_unavailable", "installed Mastermind source SHA changed")
        return source_sha, macro_sha, source_seal, macro_seal

    def __call__(self, *, repo_root: Path, macro_root_flag: str | None,
                 now: str | None, timeout: float, **_ignored: Any) -> dict[str, Any]:
        repo = Path(repo_root).resolve()
        macro = Path(macro_root_flag).resolve() if macro_root_flag else None
        if repo != self._source_root or macro != self._macro_root:
            raise GatewayError("backend_unavailable", "installed boot-packet roots changed")
        live_env = _installed_child_env(
            code_root=self._code_root, macro_root=self._macro_root,
        )
        pre_source_sha, pre_macro_sha, pre_source_seal, pre_macro_seal = (
            self._snapshot_pair(live_env)
        )
        with _materialized_macro_root(self._macro_root, timeout=float(timeout)) as packet_macro_root:
            child_env = _installed_child_env(
                code_root=self._code_root, macro_root=packet_macro_root,
            )
            if packet_macro_root != self._macro_root:
                materialized_sha = _clean_git_snapshot(
                    packet_macro_root, runner=self._runner, env=child_env,
                    label="materialized Macro source", content_scope="macro_brief",
                )
                if materialized_sha != pre_macro_sha:
                    raise GatewayError(
                        "backend_unavailable", "installed Macro materialization SHA differs"
                    )
            inner_timeout = _inner_packet_timeout(float(timeout))
            argv = [os.fspath(self._python), "-I", "-B",
                    os.fspath(self._code_root / "scripts" / "ceo_boot_packet.py"),
                    "--json", "--repo-root", os.fspath(repo),
                    "--macro-root", os.fspath(packet_macro_root),
                    "--timeout", f"{inner_timeout:g}"]
            if now is not None:
                argv.extend(["--now", now])
            try:
                result = self._runner(
                    argv, cwd=self._code_root, timeout=float(timeout),
                    max_bytes=ceo_boot_packet.DEFAULT_MAX_OUTPUT_BYTES, env=child_env,
                )
            except Exception as exc:
                raise GatewayError("backend_unavailable", "installed boot-packet collector failed") from exc
            if not isinstance(result, Mapping) or result.get("code") != 0:
                raise GatewayError("backend_unavailable", "installed boot-packet collector failed")
            if any(result.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8")):
                raise GatewayError("backend_unavailable", "installed boot-packet collector failed")
            stdout = result.get("stdout")
            if type(stdout) is not str:
                raise GatewayError("backend_unavailable", "installed boot-packet collector failed")
            try:
                packet = json.loads(stdout)
            except ValueError as exc:
                raise GatewayError("backend_unavailable", "installed boot-packet collector emitted invalid JSON") from exc
            if not isinstance(packet, dict) or packet.get("schema") != ceo_boot_packet.SCHEMA:
                raise GatewayError("backend_unavailable", "installed boot-packet collector emitted the wrong schema")
            mastermind = packet.get("mastermind")
            macro_doc = packet.get("macro")
            try:
                packet_repo = (
                    Path(mastermind["root"]).resolve()
                    if isinstance(mastermind, Mapping) else None
                )
                packet_macro = (
                    Path(macro_doc["root"]).resolve()
                    if isinstance(macro_doc, Mapping) else None
                )
                packet_source_sha = mastermind.get("sha") if isinstance(mastermind, Mapping) else None
                packet_macro_sha = macro_doc.get("sha") if isinstance(macro_doc, Mapping) else None
            except (KeyError, TypeError, OSError):
                packet_repo = packet_macro = None
                packet_source_sha = packet_macro_sha = None
            if packet_repo != self._source_root or packet_macro != packet_macro_root:
                raise GatewayError("backend_unavailable", "installed boot-packet roots differ")
            if packet_source_sha != pre_source_sha or packet_macro_sha != pre_macro_sha:
                raise GatewayError("backend_unavailable", "installed boot-packet SHA binding differs")

            post_source_sha, post_macro_sha, post_source_seal, post_macro_seal = (
                self._snapshot_pair(live_env)
            )
            if (
                post_source_sha != pre_source_sha
                or post_macro_sha != pre_macro_sha
                or post_source_seal != pre_source_seal
                or post_macro_seal != pre_macro_seal
            ):
                raise GatewayError("backend_unavailable", "installed source changed during boot-packet read")
            packet = _project_macro_identity(
                packet, materialized_root=packet_macro_root, canonical_root=self._macro_root,
            )
        return packet


class InstalledExecutiveReaders(ExecutiveMcpGateway):
    """Reuse all four projections with one explicit, host-owned Runtime root."""

    def __init__(
        self, *, repo_root: Path, macro_root: Path, runtime_root: Path,
        boot_python: Path | None = None, packet_runner: PacketRunner | None = None,
        code_root: Path | None = None, expected_source_sha: str | None = None,
    ) -> None:
        if not all(Path(p).is_absolute() for p in (repo_root, macro_root, runtime_root)):
            raise ValueError("installed read roots must be absolute")
        if boot_python is not None and not Path(boot_python).is_absolute():
            raise ValueError("installed boot interpreter must be absolute")
        if boot_python is not None and code_root is None:
            raise ValueError("dependency-complete installed reads require immutable code_root")
        if code_root is not None and not Path(code_root).is_absolute():
            raise ValueError("installed code root must be absolute")
        if expected_source_sha is not None and not _valid_sha(expected_source_sha):
            raise ValueError("expected installed source SHA must be lowercase hexadecimal")
        self._installed_runtime_root = Path(runtime_root).resolve()
        self._source_root = Path(repo_root).resolve()
        self._macro_root = Path(macro_root).resolve()
        self._code_root = Path(code_root).resolve() if code_root is not None else self._source_root
        self._expected_source_sha = expected_source_sha
        self._boot_python = Path(boot_python).absolute() if boot_python is not None else None
        self._read_runner = packet_runner or _default_packet_runner
        packet_builder = self._installed_packet
        if self._boot_python is not None:
            packet_builder = InstalledBootPacketCollector(
                source_root=self._source_root, macro_root=self._macro_root,
                code_root=self._code_root, python_executable=self._boot_python,
                runner=packet_runner, expected_source_sha=expected_source_sha,
            )
        elif packet_runner is not None:
            raise ValueError("packet_runner requires boot_python")
        super().__init__(
            GatewayConfig(
                mode=ServerMode.READONLY, repo_root=self._source_root,
                macro_root_flag=str(self._macro_root),
                boot_packet_timeout=_INSTALLED_PACKET_TOTAL_TIMEOUT_SECONDS,
                max_response_bytes=executive_ceo_ingress.MAX_RESPONSE_BYTES // 2,
            ),
            packet_builder=packet_builder, inbox_builder=self._canonical_inbox,
            runtime_factory=lambda _root: _open_readonly_runtime(self._installed_runtime_root),
        )

    def _installed_packet(self, **kwargs: Any) -> dict[str, Any]:
        """Preserve #697's optional degraded path when no boot runtime is bound."""
        requested_repo = Path(kwargs.get("repo_root", self._source_root)).resolve()
        requested_macro = Path(kwargs.get("macro_root_flag", self._macro_root)).resolve()
        if requested_repo != self._source_root or requested_macro != self._macro_root:
            packet = ceo_boot_packet.build_packet(**kwargs)
            packet["degraded"] = [
                "installed boot helper unavailable: source_binding_mismatch",
                *(str(item) for item in (packet.get("degraded") or [])),
            ]
            return packet
        return ceo_boot_packet.build_packet_in_interpreter(
            boot_python=None, repo_root=self._source_root, macro_root=self._macro_root,
            timeout=float(kwargs.get("timeout", _INSTALLED_PACKET_TOTAL_TIMEOUT_SECONDS)),
            now=kwargs.get("now"),
        )

    def _canonical_inbox(self, **kwargs: Any) -> dict[str, Any]:
        return executive_inbox.build_inbox(
            **kwargs, runtime_root=self._installed_runtime_root,
        )

    def _runtime_label(self) -> str:
        return "readonly:installed-executive-runtime"

    async def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name == MODIFYING_TOOL:
            raise GatewayError("authority_refused", "installed reader is read-only")
        validate_tool_arguments(name, arguments)
        return await super().call(name, arguments)

    def observe(self) -> dict[str, str]:
        """Fresh source identities; the admission owner independently rechecks."""
        env = _installed_child_env(
            code_root=self._code_root, macro_root=self._macro_root,
        )
        try:
            mastermind_sha = _clean_git_snapshot(
                self._source_root, runner=self._read_runner, env=env,
                label="Mastermind source",
            )
            macro_sha = _clean_git_snapshot(
                self._macro_root, runner=self._read_runner, env=env,
                label="Macro source",
            )
        except GatewayError as exc:
            raise ValueError("installed grounding is unavailable") from exc
        if self._expected_source_sha is not None and mastermind_sha != self._expected_source_sha:
            raise ValueError("installed grounding source SHA changed")
        result = {
            "mastermind_sha": mastermind_sha,
            "macro_sha": macro_sha,
            "boot_packet_schema": executive_ceo_ingress.BOOT_PACKET_SCHEMA,
        }
        validated = executive_ceo_ingress._coerce_grounding_shape(result)
        if validated is None:
            raise ValueError("installed grounding is unavailable")
        return validated
