"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

import concurrent.futures
import configparser
import contextvars
import copy
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping

from control_plane import ceo_boot_packet, executive_ceo_ingress, executive_inbox
from integrations.executive_mcp.adapter import (
    ExecutiveMcpGateway, GatewayConfig, _open_readonly_runtime,
)
from integrations.executive_mcp.schemas import (
    ERROR_CODES, GatewayError, MODIFYING_TOOL, READ_TIMEOUT_SECONDS, ServerMode,
    bound_document, bound_job_document, canonical_json, result_envelope,
    validate_tool_arguments,
)


PacketRunner = Callable[..., Mapping[str, Any]]


_default_packet_runner = ceo_boot_packet.bounded_subprocess_runner
_CANONICAL_PROJECT_DATA = contextvars.ContextVar("installed_canonical_project_data", default=None)
_CANONICAL_PROJECT_COMPILATION = contextvars.ContextVar("installed_canonical_project_compilation", default=None)
_PACKET_SETTLEMENT_MARGIN_SECONDS = 0.75
_INSTALLED_PACKET_TOTAL_TIMEOUT_SECONDS = READ_TIMEOUT_SECONDS - 2.0
# Bound each independent input below the observed 48k-object timeout case.
# This preserves the complete object set and two-probe concurrency; fitting the
# installed cumulative deadline still requires actual host qualification.
_OBJECT_TYPE_PROBE_SHARD_SIZE = 24_000


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


# ---------------------------------------------------------------------------
# installed packet error diagnostics
# ---------------------------------------------------------------------------

#: Approved repository labels for diagnostic recognition. Other observation
#: labels remain unclassified; no caller-supplied label enters the projection.
_INSTALLED_DIAGNOSTIC_LABELS = (
    "Mastermind source",
    "Macro source",
    "materialized Macro source",
)

#: Broad stage of a packet read in which a recognized refusal is authored.
#: Deliberately coarse: the projection derives the stage from the refusal
#: text alone and never claims exact pre/post checkpoint telemetry.
_INSTALLED_DIAGNOSTIC_STAGES = (
    "SOURCE",
    "MACRO_PLAN",
    "MATERIALIZATION",
    "INNER_PACKET",
    "PACKET_BINDING",
    "POST_SEAL",
    "UNKNOWN",
)

#: Immediate-cause class labels.  Class identity and the stdlib hierarchy
#: only; ``__name__``, ``args``, ``str`` and ``repr`` never participate.
_INSTALLED_DIAGNOSTIC_CAUSE_CLASSES = (
    "NONE",
    "GATEWAY_ERROR",
    "PERMISSION_ERROR",
    "TIMEOUT_ERROR",
    "OS_ERROR",
    "VALUE_ERROR",
    "TYPE_ERROR",
    "OTHER",
)

#: Source-authored tails of ``installed {label} <tail>`` refusal messages,
#: each with the broad stage its family is observed in.  Every tail is
#: copied verbatim from an existing GatewayError message expression in this
#: module.
_INSTALLED_DIAGNOSTIC_TAIL_STAGES: Mapping[str, str] = MappingProxyType({
    "repository topology is unsafe": "SOURCE",
    "observation failed": "SOURCE",
    "HEAD is unavailable": "SOURCE",
    "HEAD changed": "SOURCE",
    "repository objects are incomplete": "SOURCE",
    "worktree path set differs": "SOURCE",
    "worktree bytes differ": "SOURCE",
    "worktree observation failed": "SOURCE",
    "admitted worktree omits read bytes": "SOURCE",
    "admitted worktree is incomplete": "SOURCE",
    "admitted worktree differs": "SOURCE",
    "symlinks are unsupported": "SOURCE",
    "tree is malformed": "SOURCE",
    "tree is unsupported": "SOURCE",
    "checkout is not clean": "SOURCE",
    "content scope is invalid": "SOURCE",
    "identity is ambiguous": "SOURCE",
    "generation seal is unavailable": "SOURCE",
    "generation seal failed": "SOURCE",
    "exceeded its cumulative deadline": "SOURCE",
})

#: Exact non-templated refusal messages this module authors, each with its
#: broad stage; the authored text itself is the category.  Refusals whose
#: text coincides with a templated instantiation above inherit that mapping
#: and are not repeated here.
_INSTALLED_DIAGNOSTIC_EXACT_STAGES: Mapping[str, str] = MappingProxyType({
    "installed Macro repository topology is unsafe": "SOURCE",
    "installed Macro materialization plan is unavailable": "MACRO_PLAN",
    "installed Macro path-list frontmatter is unsupported": "MACRO_PLAN",
    "installed Macro materialization SHA differs": "MATERIALIZATION",
    "installed Macro materialization failed": "MATERIALIZATION",
    "installed Macro verified snapshot is unavailable": "MACRO_PLAN",
    "installed boot-packet collector failed": "INNER_PACKET",
    "installed boot-packet collector emitted invalid JSON": "INNER_PACKET",
    "installed boot-packet collector emitted the wrong schema":
        "INNER_PACKET",
    "installed boot-packet collector exceeded its cumulative deadline":
        "UNKNOWN",
    "installed Context record unavailable": "INNER_PACKET",
    "installed boot-packet roots changed": "PACKET_BINDING",
    "installed boot-packet roots differ": "PACKET_BINDING",
    "installed boot-packet SHA binding differs": "PACKET_BINDING",
    "installed Macro source SHA changed": "SOURCE",
    "installed Mastermind source SHA changed": "SOURCE",
    "installed source changed during boot-packet read": "POST_SEAL",
    "installed materialized Macro changed during boot-packet read":
        "POST_SEAL",
    "installed snapshot seal is unavailable": "SOURCE",
    "installed repository topology is unsafe": "SOURCE",
})

#: Frozen recognition table: exact refusal text -> (stage, category).
#: Templated refusals are instantiated with the approved labels only, so the
#: table is a finite constant fixed at import time.
_INSTALLED_DIAGNOSTIC_TABLE: Mapping[str, tuple[str, str]] = MappingProxyType({
    **{
        f"installed {label} {tail}": (stage, tail)
        for label in _INSTALLED_DIAGNOSTIC_LABELS
        for tail, stage in _INSTALLED_DIAGNOSTIC_TAIL_STAGES.items()
    },
    **{
        message: (stage, message)
        for message, stage in _INSTALLED_DIAGNOSTIC_EXACT_STAGES.items()
    },
})


def _installed_diagnostic_message(error: BaseException) -> str | None:
    """Return the exact authored refusal text, or ``None`` when unusable.

    Only the exact GatewayError type and a plain string message are read.
    Exception args and string-subclass hooks never participate.
    """
    if type(error) is not GatewayError:
        return None
    message = getattr(error, "message", None)
    return message if type(message) is str else None


def _installed_diagnostic_cause_class(cause: object) -> str:
    """Classify the immediate cause only; never walk the cause chain."""
    if cause is None:
        return "NONE"
    cause_type = type(cause)
    if issubclass(cause_type, GatewayError):
        return "GATEWAY_ERROR"
    if issubclass(cause_type, PermissionError):
        return "PERMISSION_ERROR"
    if issubclass(cause_type, TimeoutError):
        return "TIMEOUT_ERROR"
    if issubclass(cause_type, OSError):
        return "OS_ERROR"
    if issubclass(cause_type, ValueError):
        return "VALUE_ERROR"
    if issubclass(cause_type, TypeError):
        return "TYPE_ERROR"
    return "OTHER"


def installed_packet_error_diagnostic(
    error: BaseException,
) -> Mapping[str, str]:
    """Project a raised error onto the bounded installed-packet vocabulary.

    Pure observation of an already-raised exception.  The return value is an
    ordinary mapping carrying exactly four finite fields: ``error_code``,
    ``stage``, ``category`` and ``cause_class``.  Recognition is exact
    membership against refusal messages this module authors; any other text
    -- prefix, suffix, newline, path, token, case change or partial match --
    stays ``UNKNOWN``/``UNCLASSIFIED`` and is never echoed.  The error is
    not mutated, ``str()``/``repr()`` are never called, the cause chain is
    not walked beyond the immediate cause, and no secondary exception is
    raised; malformed or tampered input fails closed to finite values.
    """
    error_code = "internal_error"
    stage = "UNKNOWN"
    category = "UNCLASSIFIED"
    cause_class = "NONE"
    if type(error) is not GatewayError:
        return {
            "error_code": error_code, "stage": stage,
            "category": category, "cause_class": cause_class,
        }
    try:
        message = _installed_diagnostic_message(error)
    except Exception:
        message = None
    if message is not None:
        entry = _INSTALLED_DIAGNOSTIC_TABLE.get(message)
        if entry is not None:
            stage, category = entry
    try:
        code = getattr(error, "code", None)
        if type(code) is str and code in ERROR_CODES:
            error_code = code
    except Exception:
        error_code = "internal_error"
    try:
        cause_class = _installed_diagnostic_cause_class(
            getattr(error, "__cause__", None)
        )
    except Exception:
        cause_class = "NONE"
    return {
        "error_code": error_code,
        "stage": stage,
        "category": category,
        "cause_class": cause_class,
    }


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
        git_metadata / "info" / "grafts",
        objects_root / "info" / "alternates",
        objects_root / "info" / "http-alternates",
    )
    try:
        if any(marker.exists() or marker.is_symlink() for marker in fixed_markers):
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository topology is unsafe"
            )

        worktrees_root = git_metadata / "worktrees"
        try:
            worktrees_stat = worktrees_root.lstat()
        except FileNotFoundError:
            worktrees_stat = None
        if worktrees_stat is not None:
            if (
                not stat.S_ISDIR(worktrees_stat.st_mode)
                or stat.S_ISLNK(worktrees_stat.st_mode)
            ):
                raise GatewayError(
                    "backend_unavailable", f"installed {label} repository topology is unsafe"
                )
            with os.scandir(worktrees_root) as worktree_entries:
                if next(worktree_entries, None) is not None:
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


def _remaining_deadline_seconds(
    deadline: float | None, *, label: str, ceiling: float | None = None,
) -> float:
    if deadline is None:
        return float(ceiling if ceiling is not None else 10.0)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"installed {label} exceeded its cumulative deadline")
    return min(remaining, ceiling) if ceiling is not None else remaining


def _check_deadline(deadline: float | None, *, label: str) -> None:
    _remaining_deadline_seconds(deadline, label=label)


def _git_generation_seal(
    git_metadata: Path, *, worktree_seal: str, deadline: float | None,
    label: str,
) -> str:
    """Seal mutation-sensitive Git/worktree metadata without re-walking history."""
    digest = hashlib.sha256()
    digest.update(("worktree\0" + worktree_seal + "\n").encode("ascii"))

    def seal_path(path: Path, rel: str) -> os.stat_result | None:
        _check_deadline(deadline, label=label)
        try:
            observed = path.lstat()
        except FileNotFoundError:
            digest.update(("missing\0" + rel + "\n").encode("utf-8"))
            return None
        kind = (
            "directory" if stat.S_ISDIR(observed.st_mode)
            else "regular" if stat.S_ISREG(observed.st_mode)
            else "symlink" if stat.S_ISLNK(observed.st_mode)
            else "other"
        )
        _seal_stat(digest, rel=rel, kind=kind, observed=observed)
        return observed

    seal_path(git_metadata, ".git")
    for name in ("HEAD", "config", "packed-refs"):
        seal_path(git_metadata / name, f".git/{name}")

    refs_root = git_metadata / "refs"
    if (refs_stat := seal_path(refs_root, ".git/refs")) is not None:
        if not stat.S_ISDIR(refs_stat.st_mode) or stat.S_ISLNK(refs_stat.st_mode):
            raise OSError("installed Git refs topology is unsafe")
        stack: list[tuple[Path, str]] = [(refs_root, ".git/refs")]
        while stack:
            directory, prefix = stack.pop()
            _check_deadline(deadline, label=label)
            with os.scandir(directory) as raw_entries:
                entries = sorted(raw_entries, key=lambda entry: os.fsencode(entry.name))
            for entry in entries:
                rel = f"{prefix}/{entry.name}"
                observed = seal_path(Path(entry.path), rel)
                if observed is not None and stat.S_ISDIR(observed.st_mode):
                    if stat.S_ISLNK(observed.st_mode):
                        raise OSError("installed Git refs topology is unsafe")
                    stack.append((Path(entry.path), rel))

    objects_root = git_metadata / "objects"
    objects_stat = seal_path(objects_root, ".git/objects")
    if objects_stat is None or not stat.S_ISDIR(objects_stat.st_mode):
        raise OSError("installed Git object topology is unsafe")
    with os.scandir(objects_root) as raw_entries:
        entries = sorted(raw_entries, key=lambda entry: os.fsencode(entry.name))
    for entry in entries:
        rel = f".git/objects/{entry.name}"
        observed = seal_path(Path(entry.path), rel)
        if observed is None:
            continue
        if entry.name in {"pack", "info"}:
            if not stat.S_ISDIR(observed.st_mode) or stat.S_ISLNK(observed.st_mode):
                raise OSError("installed Git object topology is unsafe")
            with os.scandir(entry.path) as nested_entries:
                nested = sorted(nested_entries, key=lambda child: os.fsencode(child.name))
            for child in nested:
                seal_path(Path(child.path), f"{rel}/{child.name}")
    return digest.hexdigest()


def _worktree_path_sets(
    root: Path, *, deadline: float | None = None, label: str = "worktree",
) -> tuple[dict[str, str], set[str], str]:
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
        _check_deadline(deadline, label=label)
        directory, prefix = stack.pop()
        with os.scandir(directory) as raw_entries:
            entries = sorted(raw_entries, key=lambda entry: os.fsencode(entry.name))
        for entry in entries:
            _check_deadline(deadline, label=label)
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


def _raw_worktree_blob_oid(
    path: Path, *, mode: str, deadline: float | None = None, label: str = "worktree",
) -> str:
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
            _check_deadline(deadline, label=label)
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
    "scripts/agentos_direction.py",
    "scripts/agentos_project_archive.py",
    "scripts/agentos_project_plan_contract.py",
    "scripts/project_knowledge_recipes.py",
    "scripts/agentos_standing_instructions.py",
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
_AGENTOS_CONTEXT_CONFIG = frozenset({"config/compiled_kill_registry.yml", "config/context_index.yml"})


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




@dataclass(frozen=True)
class _VerifiedRepositorySnapshot:
    """One complete repository proof reusable inside a single packet build."""

    root: Path
    head: str
    expected: Mapping[str, tuple[str, str]]
    worktree_seal: str
    generation_seal: str
    sealed_to_caller: bool = False


_CANONICAL_CODE_CAPTURE = object()

@dataclass(frozen=True)
class _CanonicalCodeCapture:
    """One collector's verified immutable CODE objects, never live authority."""
    seal: object
    owner: object
    binding: tuple
    observations: tuple
    macro_snapshot: _VerifiedRepositorySnapshot
    view: object = None
    view_identity: tuple | None = None


@dataclass(frozen=True)
class _MacroMaterializationPlan:
    """Exact sparse worktree required by ``agentos.py brief --json --no-remember``."""

    head: str
    files: frozenset[str]
    directories: frozenset[str]
    file_objects: Mapping[str, tuple[str, str]]


def _scoped_worktree_path_sets(
    root: Path, *, files: set[str], directories: set[str],
    deadline: float | None, label: str, verify_record_namespaces: bool = False,
) -> tuple[dict[str, str], set[str], str]:
    """Seal only paths that can be observed by one admitted sparse consumer."""
    if files & directories:
        raise OSError("scoped worktree files and directories overlap")
    seal = hashlib.sha256()
    root_stat = root.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise OSError("installed worktree root is not a direct directory")
    _seal_stat(seal, rel="", kind="directory", observed=root_stat)

    actual_types: dict[str, str] = {}
    actual_directories: set[str] = set()
    # Parents must be proven as direct directories before any descendant path is
    # observed. Otherwise a live directory->symlink substitution could make a
    # later ``lstat(root / child)`` resolve outside the admitted Macro root.
    ordered_paths = sorted(
        files | directories,
        key=lambda rel: (len(rel.split("/")), os.fsencode(rel)),
    )
    for rel in ordered_paths:
        _check_deadline(deadline, label=label)
        if not rel or rel.startswith("/") or "\x00" in rel or "\\" in rel:
            raise OSError("scoped worktree path is unsafe")
        parts = rel.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise OSError("scoped worktree path is unsafe")
        observed = (root / rel).lstat()
        if rel in directories:
            if not stat.S_ISDIR(observed.st_mode) or stat.S_ISLNK(observed.st_mode):
                raise OSError("scoped worktree directory topology differs")
            kind = "directory"
            actual_directories.add(rel)
        elif stat.S_ISLNK(observed.st_mode):
            kind = "symlink"
            actual_types[rel] = kind
        elif stat.S_ISREG(observed.st_mode):
            kind = "regular"
            actual_types[rel] = kind
        else:
            raise OSError("scoped worktree file topology differs")
        _seal_stat(seal, rel=rel, kind=kind, observed=observed)

    if verify_record_namespaces:
        for prefix in _MACRO_RECORD_DIRS:
            directory_rel = prefix.removesuffix("/")
            expected_names = {
                rel[len(prefix):]
                for rel in files
                if rel.startswith(prefix)
                and "/" not in rel[len(prefix):]
                and rel[len(prefix):].endswith(".md")
            }
            if directory_rel not in directories and not expected_names:
                continue
            _check_deadline(deadline, label=label)
            with os.scandir(root / directory_rel) as raw_entries:
                actual_names = {
                    entry.name for entry in raw_entries if entry.name.endswith(".md")
                }
            if actual_names != expected_names:
                raise OSError("installed Macro record namespace differs")

    return actual_types, actual_directories, seal.hexdigest()


def _bounded_git_text(
    path: Path, args: list[str], *, runner: PacketRunner, env: Mapping[str, str],
    deadline: float | None, label: str, max_bytes: int,
) -> str:
    try:
        result = runner(
            ["git", *args], cwd=path,
            timeout=_remaining_deadline_seconds(deadline, label=label, ceiling=10.0),
            max_bytes=max_bytes, env=env,
        )
    except Exception as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} observation failed"
        ) from exc
    if (
        not isinstance(result, Mapping)
        or any(
            result.get(flag) is True
            for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
        )
        or result.get("code") != 0
        or type(result.get("stdout")) is not str
    ):
        raise GatewayError("backend_unavailable", f"installed {label} observation failed")
    return result["stdout"]


def _macro_plan_generation_observation(
    path: Path, *, plan: _MacroMaterializationPlan, runner: PacketRunner,
    env: Mapping[str, str], deadline: float | None,
) -> tuple[str, str]:
    """Seal the canonical Macro paths that the sparse child can actually observe."""
    label = "Macro source"
    git_metadata = _direct_git_directory(path, label=label)
    if git_metadata is None:
        raise GatewayError(
            "backend_unavailable", "installed Macro repository topology is unsafe"
        )
    head = _bounded_git_text(
        path, ["rev-parse", "--verify", "HEAD^{commit}"],
        runner=runner, env=env, deadline=deadline, label=label, max_bytes=256,
    ).strip()
    if head != plan.head:
        raise GatewayError("backend_unavailable", "installed Macro source SHA changed")
    try:
        actual_types, actual_directories, worktree_seal = _scoped_worktree_path_sets(
            path, files=set(plan.files), directories=set(plan.directories),
            deadline=deadline, label=label, verify_record_namespaces=True,
        )
    except (OSError, TimeoutError) as exc:
        raise GatewayError(
            "backend_unavailable", "installed Macro source worktree observation failed"
        ) from exc
    expected_types = {rel: "regular" for rel in plan.files}
    if actual_types != expected_types or actual_directories != set(plan.directories):
        raise GatewayError(
            "backend_unavailable", "installed Macro source worktree path set differs"
        )
    for rel in sorted(plan.files):
        mode, expected_oid = plan.file_objects[rel]
        try:
            observed_oid = _raw_worktree_blob_oid(
                path / rel, mode=mode, deadline=deadline, label=label,
            )
        except (OSError, TimeoutError) as exc:
            raise GatewayError(
                "backend_unavailable", "installed Macro source worktree observation failed"
            ) from exc
        if observed_oid != expected_oid:
            raise GatewayError(
                "backend_unavailable", "installed Macro source worktree bytes differ"
            )
    post_head = _bounded_git_text(
        path, ["rev-parse", "--verify", "HEAD^{commit}"],
        runner=runner, env=env, deadline=deadline, label=label, max_bytes=256,
    ).strip()
    if post_head != head:
        raise GatewayError("backend_unavailable", "installed Macro source HEAD changed")
    try:
        generation_seal = _git_generation_seal(
            git_metadata, worktree_seal=worktree_seal, deadline=deadline, label=label,
        )
    except (OSError, TimeoutError) as exc:
        raise GatewayError(
            "backend_unavailable", "installed Macro source generation seal failed"
        ) from exc
    return head, generation_seal


def _git_head_tree(
    path: Path, *, runner: PacketRunner, env: Mapping[str, str],
    deadline: float | None, label: str,
) -> tuple[str, dict[str, tuple[str, str]]]:
    if _direct_git_directory(path, label=label) is None:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        )
    head = _bounded_git_text(
        path, ["rev-parse", "--verify", "HEAD^{commit}"], runner=runner, env=env,
        deadline=deadline, label=label, max_bytes=256,
    ).strip()
    if not _valid_sha(head):
        raise GatewayError("backend_unavailable", f"installed {label} HEAD is unavailable")
    tree = _bounded_git_text(
        path, ["ls-tree", "-r", "-z", "--full-tree", head], runner=runner, env=env,
        deadline=deadline, label=label, max_bytes=32 * 1024 * 1024,
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
    if _bounded_git_text(
        path, ["rev-parse", "--verify", "HEAD^{commit}"], runner=runner, env=env,
        deadline=deadline, label=label, max_bytes=256,
    ).strip() != head:
        raise GatewayError("backend_unavailable", f"installed {label} HEAD changed")
    return head, expected


def _require_git_object_types(
    path: Path, expected_types: Mapping[str, str], *, runner: PacketRunner,
    env: Mapping[str, str], deadline: float | None, label: str,
) -> None:
    """Prove exact object existence/type without inflating packed object headers."""
    if not expected_types:
        return

    ordered_ids = sorted(expected_types)
    shards = [
        ordered_ids[offset:offset + _OBJECT_TYPE_PROBE_SHARD_SIZE]
        for offset in range(0, len(ordered_ids), _OBJECT_TYPE_PROBE_SHARD_SIZE)
    ]

    def probe(object_ids: list[str]) -> dict[str, str]:
        object_input = ("\n".join(object_ids) + "\n").encode("ascii")
        try:
            object_result = runner(
                [
                    "git", "cat-file", "--buffer",
                    "--batch-check=%(objectname) %(objecttype)",
                ],
                cwd=path,
                timeout=_remaining_deadline_seconds(
                    deadline, label=label, ceiling=10.0,
                ),
                max_bytes=32 * 1024 * 1024, env=env, input_bytes=object_input,
            )
        except Exception as exc:
            raise GatewayError(
                "backend_unavailable",
                f"installed {label} repository objects are incomplete",
            ) from exc
        if not isinstance(object_result, Mapping) or any(
            object_result.get(flag) is True
            for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
        ):
            raise GatewayError(
                "backend_unavailable",
                f"installed {label} repository objects are incomplete",
            )
        object_stdout = object_result.get("stdout")
        if object_result.get("code") != 0 or type(object_stdout) is not str:
            raise GatewayError(
                "backend_unavailable",
                f"installed {label} repository objects are incomplete",
            )
        observed: dict[str, str] = {}
        for line in object_stdout.splitlines():
            parts = line.split()
            if (
                len(parts) != 2
                or not _valid_sha(parts[0])
                or parts[1] not in {"blob", "commit", "tree", "tag"}
                or parts[0] in observed
            ):
                raise GatewayError(
                    "backend_unavailable",
                    f"installed {label} repository objects are incomplete",
                )
            observed[parts[0]] = parts[1]
        if set(observed) != set(object_ids) or any(
            observed.get(object_id) != expected_types[object_id]
            for object_id in object_ids
        ):
            raise GatewayError(
                "backend_unavailable",
                f"installed {label} repository objects are incomplete",
            )
        return observed

    if len(shards) == 1:
        probe(shards[0])
        return

    failures: list[BaseException] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(2, len(shards)),
        thread_name_prefix="mmx-object-types",
    ) as executor:
        futures = [executor.submit(probe, shard) for shard in shards]
        for future in futures:
            try:
                future.result()
            except BaseException as exc:  # noqa: BLE001 - re-raised fail-closed below
                failures.append(exc)
    if failures:
        failure = failures[0]
        if isinstance(failure, GatewayError):
            raise failure
        raise GatewayError(
            "backend_unavailable",
            f"installed {label} repository objects are incomplete",
        ) from failure

def _frontmatter_scalar(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("empty list item")
    if value[0] == "'":
        # YAML doubles apostrophes inside single quotes. Python literal parsing
        # would instead concatenate the pieces and silently change a path.
        match = re.fullmatch(r"'((?:[^']|'')*)'(?:[ \t]+#.*)?", value)
        if match is None or not match.group(1):
            raise ValueError("invalid single-quoted list item")
        return match.group(1).replace("''", "'")
    if value[0] == '"':
        # JSON's double-quoted subset has identical YAML string semantics.
        # Other YAML escapes are explicitly refused instead of guessed.
        try:
            parsed, end = json.JSONDecoder().raw_decode(value)
        except ValueError as exc:
            raise ValueError("invalid quoted list item") from exc
        tail = value[end:]
        if tail and not re.fullmatch(r"[ \t]+#.*", tail):
            raise ValueError("unsupported quoted list item suffix")
        if not isinstance(parsed, str) or not parsed:
            raise ValueError("list item is not a non-empty string")
        return parsed
    if value[0] in "[{>|&*!":
        raise ValueError("structured YAML list item is unsupported")
    value = re.split(r"[ \t]+#", value, maxsplit=1)[0].rstrip()
    if not value:
        raise ValueError("empty list item")
    return value


def _frontmatter_lists(payload: bytes) -> dict[str, list[str]]:
    """Parse only the closed string-list subset used by path-existence checks."""
    try:
        lines = payload.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("frontmatter is not UTF-8") from exc
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter opening fence is missing")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise ValueError("frontmatter closing fence is missing") from exc
    # A root block mapping is mandatory. Consumed fields have a closed string-
    # list grammar; unrelated metadata may own an indented block, but cannot
    # hide a root field inside an unfinished quoted/flow value. This is a path
    # extractor, not a second YAML implementation for waves or narrative prose.
    tokens = [
        (len(line) - len(line.lstrip(" ")), line.lstrip(" "))
        for line in lines[1:end]
        if line.strip()
    ]
    entry_pattern = re.compile(
        r"^([A-Za-z_][A-Za-z0-9_-]*|'(?:[^']|'')*'|\"(?:[^\"\\]|\\.)*\")"
        r"[ \t]*:(?:[ \t]+(.*))?$"
    )
    flow_item_pattern = re.compile(
        r"\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^']|'')*'|[^,\[\]{}]+)\s*(?:,|$)"
    )
    targets = {"repos", "artifacts", "owns_paths"}
    out = {field: [] for field in targets}

    def refuse() -> None:
        raise ValueError("unsupported YAML structure in path-list frontmatter")

    def skip_comments(index: int) -> int:
        # Call only at a structural boundary, never inside a quoted scalar.
        # A hash-prefixed continuation may contain the scalar's closing quote.
        while index < len(tokens) and tokens[index][1].lstrip().startswith("#"):
            index += 1
        return index

    def string_item(raw: str) -> str:
        value = _frontmatter_scalar(raw)
        if raw[0] not in "\"'" and (
            value.lower() in {"null", "~", "true", "false", "yes", "no", "on", "off",
                              ".inf", "+.inf", "-.inf", ".nan"}
            or re.match(r"[-+]?(?:[0-9]|\.[0-9])", value)
            or re.search(r":(?:[ \t]|$)", value)
            or value.startswith(("? ", "- ")) or value in {"?", "-"}
            or value[0] in "]}%@`#"
        ):
            refuse()
        return value

    # Metadata aliases are never expanded or used as path fields. Remember only
    # names declared by metadata so undefined/forward aliases and duplicate
    # properties cannot turn malformed YAML into an accepted path projection.
    metadata_anchors: set[str] = set()
    property_pattern = re.compile(r"([&*])([A-Za-z0-9_-]{1,128})(?=[ \t\n,\[\]{}]|$)")

    def metadata_property(text: str) -> tuple[str, bool]:
        if not text or text[0] not in "&*":
            if text and text[0] in "!%@`":
                refuse()
            return text, False
        match = property_pattern.match(text)
        if match is None:
            refuse()
        kind, name = match.groups()
        rest = text[match.end():].lstrip()
        if kind == "*":
            if name not in metadata_anchors or (rest and not rest.startswith("#")):
                refuse()
            return "", True
        if name in metadata_anchors or len(metadata_anchors) >= 256:
            refuse()
        metadata_anchors.add(name)
        if rest.startswith("#"):
            rest = ""
        if rest and rest[0] in "&*!%@`":
            refuse()
        return rest, False

    def metadata_value_end(index: int, raw: str, *, owner_indent: int = 0) -> tuple[int, str]:
        # Properties belong to the following node, not to a whole opaque line.
        # Continue checking quoted/flow boundaries after an anchor prefix. An
        # alias is one complete metadata node; it never supplies materialized
        # paths, and consumed fields still use their original closed grammar.
        raw, alias = metadata_property(raw)
        if alias:
            index = skip_comments(index)
            if index < len(tokens) and tokens[index][0] > owner_indent:
                refuse()
            return index, "*"
        if raw and raw[0] in "\"'[{":
            stack: list[str] = []
            quote: str | None = None
            quote_start = 0
            text = raw
            cursor = 0
            finished = False
            node_start = True
            previous_nonspace = ""
            while not finished:
                while cursor < len(text):
                    character = text[cursor]
                    boundary = cursor == 0 or text[cursor - 1] in " \t\n[{,:"
                    if quote is not None:
                        if quote == '\"' and character == "\\":
                            cursor += 2
                            continue
                        if character == quote:
                            if quote == "'" and cursor + 1 < len(text) and text[cursor + 1] == "'":
                                cursor += 2
                                continue
                            quoted = text[quote_start:cursor + 1]
                            if (text[cursor + 1:].lstrip().startswith(":")
                                    and _frontmatter_scalar(quoted) == "<<"):
                                refuse()
                            quote = None
                    elif character == "#" and boundary:
                        # Comments cannot close an unfinished flow/quoted node.
                        newline = text.find("\n", cursor)
                        cursor = len(text) if newline == -1 else newline + 1
                        continue
                    elif character in "!%@`" and node_start:
                        refuse()
                    elif node_start and re.match(r"<<[ \t]*:", text[cursor:]):
                        refuse()
                    elif character in "&*" and node_start:
                        match = property_pattern.match(text, cursor)
                        if match is None:
                            refuse()
                        kind, name = match.groups()
                        if kind == "&":
                            if name in metadata_anchors or len(metadata_anchors) >= 256:
                                refuse()
                            metadata_anchors.add(name)
                        elif name not in metadata_anchors:
                            refuse()
                        cursor = match.end()
                        # Alias keys and chained node properties are outside
                        # this metadata subset, even though no alias is expanded.
                        tail = text[cursor:].lstrip()
                        if tail.startswith(("&", "*", "!", "%", "@", "`")):
                            refuse()
                        if kind == "*" and tail and tail[0] not in ",]}#":
                            refuse()
                        node_start = kind == "&"
                        continue
                    elif character in "\"'":
                        quote = character
                        quote_start = cursor
                    elif character in "[{":
                        stack.append(character)
                    elif character in "]}":
                        if not stack or stack.pop() != ("[" if character == "]" else "{"):
                            refuse()
                    if quote is None:
                        # Whitespace within a plain scalar does not start a new
                        # node. A non-separating colon (urn:&name) is prose too.
                        if character in "[{,":
                            node_start = True
                        elif character == ":" and (
                            previous_nonspace in {"\"", "'"}
                            or cursor + 1 == len(text)
                            or text[cursor + 1].isspace()
                            or text[cursor + 1] in "[]{},"
                        ):
                            node_start = True
                        elif not character.isspace():
                            node_start = False
                    if not character.isspace():
                        previous_nonspace = character
                    cursor += 1
                    if quote is None and not stack:
                        if text[cursor:].strip() and not text[cursor:].lstrip().startswith("#"):
                            refuse()
                        finished = True
                        break
                if not finished:
                    if quote is None:
                        index = skip_comments(index)
                    if index >= len(tokens) or tokens[index][0] == 0:
                        refuse()
                    text += "\n" + tokens[index][1]
                    index += 1
            index = skip_comments(index)
            if index < len(tokens) and tokens[index][0] > owner_indent:
                refuse()
        return index, raw

    def metadata_end(index: int, raw: str) -> int:
        index, raw = metadata_value_end(index, raw)
        # Every remaining continuation is explicitly owned by this unconsumed
        # root entry. Indentless sequences belong only to a block-valued entry.
        prose_indent: int | None = 0 if raw.startswith(("|", ">")) else None
        while index < len(tokens):
            index = skip_comments(index)
            if index == len(tokens):
                break
            indent, text = tokens[index]
            if not (indent > 0 or (not raw and (text == "-" or text.startswith("- ")))):
                break
            if raw == "*":
                refuse()  # a complete alias cannot own a continuation block
            index += 1
            if prose_indent is not None and indent > prose_indent:
                continue
            prose_indent = None
            sequence_item = text.startswith("- ")
            sequence_column = indent
            if sequence_item:
                after_dash = text[1:]
                sequence_column += 1 + len(after_dash) - len(after_dash.lstrip(" "))
                text = after_dash.strip()
            nested = entry_pattern.fullmatch(text)
            node_indent = sequence_column if sequence_item and nested else indent
            if ((nested and _frontmatter_scalar(nested.group(1)) == "<<")
                    or re.match(r"<<[ \t]*:", text)):
                refuse()
            nested_value = (nested.group(2) or "").strip() if nested else text
            index, nested_value = metadata_value_end(index, nested_value, owner_indent=node_indent)
            if nested_value.startswith(("|", ">")):
                prose_indent = node_indent
        return index

    if not tokens:
        refuse()
    seen: set[str] = set()
    index = skip_comments(0)
    if index == len(tokens):
        refuse()
    while index < len(tokens):
        index = skip_comments(index)
        if index == len(tokens):
            break
        indent, text = tokens[index]
        match = entry_pattern.fullmatch(text) if indent == 0 else None
        if match is None:
            refuse()
        key = _frontmatter_scalar(match.group(1))
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key) is None or key in seen:
            refuse()
        seen.add(key)
        raw = (match.group(2) or "").strip()
        if raw.startswith("#"):
            raw = ""
        index += 1
        if key not in targets:
            index = metadata_end(index, raw)
            continue
        if raw:
            if not (raw.startswith("[") and raw.endswith("]")):
                refuse()
            inner = raw[1:-1].strip()
            cursor = 0
            while cursor < len(inner):
                item = flow_item_pattern.match(inner, cursor)
                if item is None:
                    refuse()
                out[key].append(string_item(item.group(1).strip()))
                cursor = item.end()
            continue
        item_indent: int | None = None
        while index < len(tokens):
            index = skip_comments(index)
            if index == len(tokens):
                break
            indent, text = tokens[index]
            if indent == 0 and not text.startswith("- "):
                break
            if not text.startswith("- ") or (item_indent is not None and indent != item_indent):
                refuse()
            item_indent = indent
            out[key].append(string_item(text[2:].strip()))
            index += 1
        if item_indent is None:
            refuse()
    return out


def _static_macro_probe(entry: str, repos: list[str]) -> str | None:
    if ":" in entry:
        prefix, rel = entry.split(":", 1)
        if prefix not in {"macro", "terminal", "mastermind"}:
            return None
        repo = prefix
        rel = rel.strip()
    else:
        repo = "macro" if "macro" in repos else (repos[0] if repos else "macro")
        rel = entry.strip()
    if repo != "macro":
        return None
    if not rel or rel.startswith("/") or "\x00" in rel or "\\" in rel:
        raise ValueError("path is not repository-relative")
    parts: list[str] = []
    for segment in rel.split("/"):
        if segment in {"", ".", ".."}:
            if segment == "" and parts and rel.endswith("/"):
                break
            raise ValueError("path contains an unsafe segment")
        if any(character in segment for character in "*?["):
            break
        parts.append(segment)
    return "/".join(parts) or None


def _directory_closure(paths: set[str]) -> set[str]:
    directories = set(paths)
    for rel in list(paths):
        parts = rel.split("/")
        for depth in range(1, len(parts)):
            directories.add("/".join(parts[:depth]))
    return directories


def _macro_read_selection(expected, read_bytes, *, agentos_context=False):
    """One finite source-selection rule for adopted and current context reads.

    The caller owns immutable tree membership and captured bytes. This pure
    selector never reads another source or grants authority to a path.
    """
    tracked_paths = set(expected)
    files = _macro_brief_content_paths(tracked_paths)
    if agentos_context:
        from control_plane.agentos_context_bundle import REQUIRED_COMPILER_PATHS
        files.update(tracked_paths & _AGENTOS_CONTEXT_CONFIG)
        if not REQUIRED_COMPILER_PATHS <= files:
            raise ValueError("required context compiler source is unavailable")
    tree_directories = _tree_directory_paths(tracked_paths)
    probe_directories: set[str] = set()
    for rel in sorted(
        path for path in files if path.startswith("agentos/workstreams/")
    ):
        mode, expected_oid = expected[rel]
        if mode == "120000":
            raise ValueError("workstream record is a symlink")
        payload = read_bytes(rel)
        if _git_blob_oid(payload) != expected_oid:
            raise ValueError("workstream bytes differ from HEAD")
        parsed = _frontmatter_lists(payload)
        repos = parsed["repos"]
        for field in ("artifacts", "owns_paths"):
            for entry in parsed[field]:
                stem = _static_macro_probe(entry, repos)
                if stem is None:
                    continue
                # A tracked symlink can make an otherwise untracked stem
                # exist in the canonical checkout. Refuse every prefix,
                # including glob bases, without following the link target.
                parts = stem.split("/")
                for end in range(1, len(parts) + 1):
                    prefix = "/".join(parts[:end])
                    if prefix in expected and expected[prefix][0] == "120000":
                        raise ValueError("path-existence probe traverses a symlink")
                if stem in expected:
                    files.add(stem)
                elif stem in tree_directories:
                    probe_directories.add(stem)
    if any(expected[rel][0] == "120000" for rel in files):
        raise ValueError("materialized read closure contains a symlink")
    directories = _tree_directory_paths(files) | _directory_closure(probe_directories)
    return files, directories


def _build_macro_materialization_plan(
    source: Path, *, runner: PacketRunner, env: Mapping[str, str],
    deadline: float | None,
    verified_snapshot: _VerifiedRepositorySnapshot | None = None,
    agentos_context: bool = False,
) -> _MacroMaterializationPlan:
    label = "Macro source"
    try:
        if verified_snapshot is None:
            head, expected = _git_head_tree(
                source, runner=runner, env=env, deadline=deadline, label=label,
            )
        else:
            if verified_snapshot.root != source.resolve():
                raise ValueError("verified Macro snapshot root differs")
            head = verified_snapshot.head
            expected = dict(verified_snapshot.expected)
        files, directories = _macro_read_selection(expected, lambda rel: (source / rel).read_bytes(),
                                                     agentos_context=agentos_context)
        return _MacroMaterializationPlan(
            head=head,
            files=frozenset(files),
            directories=frozenset(directories),
            file_objects=MappingProxyType({rel: expected[rel] for rel in files}),
        )
    except GatewayError:
        raise
    except (OSError, TimeoutError, ValueError) as exc:
        raise GatewayError(
            "backend_unavailable", "installed Macro path-list frontmatter is unsupported"
        ) from exc


def _agentos_context_runtime(python: Path, *, runner, remaining):
    """Reuse CF2 qualification, sharing this read's result-acceptance deadline.

The incumbent attestor's filesystem checks are synchronous. They are checked
before/after, not falsely described as cancellable hard wall-clock work.
"""
    try:
        remaining()
        contract = ceo_boot_packet._capacity_runtime_contract()
        def probe(argv, **limits):
            limits["timeout"] = min(limits["timeout"], remaining())
            return runner(argv, **limits)
        site = ceo_boot_packet.attest_capacity_boot_runtime(python, runner=probe)
        remaining()
        if Path(site) != Path(contract.site_packages) or Path(python) != Path(contract.python_binary):
            raise ValueError("runtime selection differs")
        commitment = {
            "owner": "cf2_capacity_runtime", "python_version": contract.python_version,
            "python_binary_sha256": contract.python_binary_sha256, "pyyaml_version": contract.pyyaml_version,
            "pyyaml_record_sha256": contract.pyyaml_record_sha256, "runtime_tree_sha256": contract.runtime_tree_sha256,
        }
        return Path(site), commitment
    except GatewayError:
        raise
    except Exception:
        raise GatewayError("backend_unavailable", "installed context runtime unavailable") from None


def _agentos_context_file(root: Path, plan: _MacroMaterializationPlan, relative: str, *, maximum, remaining):
    """Read one ordinary file from the already held materialization plan."""
    remaining()
    mode, oid = plan.file_objects[relative]
    if mode not in {"100644", "100755"}:
        raise ValueError("invalid context source mode")
    descriptor = os.open(root / relative, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("context source is not ordinary")
        if before.st_size > maximum:
            return None
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (len(raw) != before.st_size or len(raw) > maximum
            or tuple(getattr(before, key) for key in fields) != tuple(getattr(after, key) for key in fields)
            or _git_blob_oid(raw) != oid):
        raise ValueError("context source changed")
    remaining()
    return {"path": relative, "mode": mode, "git_blob": oid,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _agentos_context_sources(root: Path, plan: _MacroMaterializationPlan, *, remaining):
    """Observe the two permitted Macro executable files inside the verified plan."""
    from control_plane.agentos_context_bundle import REQUIRED_COMPILER_PATHS, MAX_COMPILER_SOURCE_BYTES, canonical_digest
    try:
        sources = []
        for relative in sorted(REQUIRED_COMPILER_PATHS):
            source = _agentos_context_file(root, plan, relative,
                maximum=MAX_COMPILER_SOURCE_BYTES, remaining=remaining)
            if source is None:
                raise ValueError("compiler source is unavailable")
            sources.append(source)
        inventory = {"head": plan.head,
            "files": [[path, *plan.file_objects[path]] for path in sorted(plan.files)],
            "directories": sorted(plan.directories)}
        digest = canonical_digest(inventory)
        remaining()
        return sources, digest
    except GatewayError:
        raise
    except (OSError, KeyError, TypeError, ValueError):
        raise GatewayError("backend_unavailable", "installed context compiler source unavailable") from None


def _agentos_selected_record_sources(root: Path, plan: _MacroMaterializationPlan, *, raw, bundle,
                                    work_ref, remaining):
    """Bind selected record contributions to this held DATA snapshot only."""
    from control_plane import agentos_context_bundle as contract
    try:
        uses = contract.selected_record_uses(bundle, work_ref=work_ref)
        selected_items = sum(map(len, uses.values()))
        entries, overflow = [], None
        for relative, positions in uses.items():
            source = _agentos_context_file(root, plan, relative,
                maximum=contract.MAX_RECORD_SOURCE_BYTES, remaining=remaining)
            if source is None:
                overflow = "RECORD_BYTES"
            else:
                entries.append({**source, "uses": positions})
        arguments = {"bundle_sha256": hashlib.sha256(raw).hexdigest(), "data_commit": plan.head,
                     "selected_items": selected_items}
        value = contract.record_source_inventory(**arguments, entries=entries)
        size = len(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")).encode("utf-8"))
        if overflow is not None or size > contract.MAX_RECORD_INVENTORY_BYTES:
            # Preserve the full original context. Evidence alone overflows,
            # explicitly retaining counts and no misleading empty-source claim.
            value = contract.record_source_inventory(**arguments, entries=[],
                overflow_reason=overflow or "INVENTORY_BYTES")
        remaining()
        return contract.validate_record_source_inventory(value, raw=raw, bundle=bundle,
            work_ref=work_ref, data_commit=plan.head)
    except GatewayError:
        raise
    except (OSError, KeyError, TypeError, ValueError, RecursionError):
        raise GatewayError("backend_unavailable", "installed context record sources unavailable") from None


def _clone_git_read_database(source: Path, destination: Path, *, deadline: float) -> None:
    source_stat = source.lstat()
    if not stat.S_ISDIR(source_stat.st_mode) or stat.S_ISLNK(source_stat.st_mode):
        raise OSError("installed Git metadata is not a direct directory")
    destination.mkdir(mode=stat.S_IMODE(source_stat.st_mode))
    for name in ("HEAD", "config", "objects"):
        _clone_tree(source / name, destination / name, deadline=deadline)
    for name in ("packed-refs", "refs"):
        candidate = source / name
        if candidate.exists() or candidate.is_symlink():
            _clone_tree(candidate, destination / name, deadline=deadline)
    shutil.copystat(source, destination, follow_symlinks=False)

def _content_paths_for_scope(paths: set[str], scope: str) -> set[str]:
    if scope == "all":
        return set(paths)
    if scope == "identity":
        return set()
    if scope == "macro_brief":
        return _macro_brief_content_paths(paths)
    raise ValueError(f"unknown installed snapshot content scope: {scope}")


def _overlap_full_proofs(
    *, object_closure: Callable[[], Any] | None,
    worktree_inventory: Callable[[], Any] | None,
) -> tuple[Any, Any]:
    """Run one snapshot's two independent full proofs, overlapping when both exist.

    The complete repository object-closure check and the complete raw worktree
    inventory read disjoint inputs, so within a single ``_clean_git_snapshot``
    invocation they may share the wall clock on at most two local tasks.  Both
    must reach a terminal state before either result is used, and a branch
    failure is raised in the same branch order the serial proof used, so no
    observation work is abandoned silently and nothing downstream starts early.
    """
    if object_closure is None or worktree_inventory is None:
        return (
            object_closure() if object_closure is not None else None,
            worktree_inventory() if worktree_inventory is not None else None,
        )

    results: list[Any] = [None, None]
    failure: BaseException | None = None
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=2, thread_name_prefix="mmx-installed-proof-pair",
    )
    try:
        futures = [
            executor.submit(branch) for branch in (object_closure, worktree_inventory)
        ]
        for index, future in enumerate(futures):
            try:
                results[index] = future.result()
            except BaseException as exc:  # noqa: BLE001 - re-raised unchanged below
                if failure is None:
                    failure = exc
    finally:
        # Joins both workers: a surviving branch settles before the refusal is
        # raised, and a late success can never be mistaken for a completed proof.
        executor.shutdown(wait=True, cancel_futures=True)
    if failure is not None:
        raise failure
    return results[0], results[1]


def _require_git_history_closure(
    path: Path, head: str, *, runner: PacketRunner, env: Mapping[str, str],
    deadline: float | None, label: str, record_trees: bool,
) -> None:
    """Incumbent ancestry and selected record-tree proof for one Git database."""
    ancestry_commits: set[str] = set()
    try:
        history_result = runner(
            ["git", "rev-list", "--parents", head],
            cwd=path,
            timeout=_remaining_deadline_seconds(
                deadline, label=label, ceiling=10.0,
            ),
            max_bytes=32 * 1024 * 1024, env=env,
        )
    except Exception as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        ) from exc
    if not isinstance(history_result, Mapping) or any(
        history_result.get(flag) is True
        for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
    ):
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        )
    history_stdout = history_result.get("stdout")
    if history_result.get("code") != 0 or type(history_stdout) is not str:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        )
    for line in history_stdout.splitlines():
        object_ids = line.split()
        if not object_ids or any(not _valid_sha(object_id) for object_id in object_ids):
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository objects are incomplete"
            )
        ancestry_commits.update(object_ids)
    if head not in ancestry_commits:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        )
    _require_git_object_types(
        path, {object_id: "commit" for object_id in ancestry_commits},
        runner=runner, env=env, deadline=deadline, label=label,
    )

    def historical_record_trees() -> None:
        try:
            record_history = _bounded_git_text(
                path,
                ["rev-list", "--objects", "--no-object-names", "--filter=blob:none",
                 "--full-history", head, "--", *_MACRO_RECORD_DIRS],
                runner=runner, env=env, deadline=deadline, label=label,
                max_bytes=32 * 1024 * 1024,
            )
            historical_trees: dict[str, str] = {}
            for oid in record_history.splitlines():
                if not _valid_sha(oid):
                    raise ValueError("record history contains an invalid object")
                if oid not in ancestry_commits:
                    historical_trees[oid] = "tree"
            _require_git_object_types(
                path, historical_trees, runner=runner, env=env,
                deadline=deadline, label=label,
            )
        except (GatewayError, ValueError) as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository objects are incomplete"
            ) from exc

    if record_trees:
        historical_record_trees()


def _clean_git_snapshot(
    path: Path, *, runner: PacketRunner, env: Mapping[str, str], label: str,
    content_scope: str = "all", include_seal: bool = False,
    verify_repository_closure: bool = True, deadline: float | None = None,
    admitted_worktree_files: set[str] | None = None,
    admitted_worktree_directories: set[str] | None = None,
    snapshot_capture: list[_VerifiedRepositorySnapshot] | None = None,
    _allow_synthetic_fixture: bool = False,
) -> str | tuple[str, str]:
    """Bind one explicitly admitted direct repository to its raw consumed bytes."""
    if snapshot_capture is not None and not include_seal:
        raise ValueError("snapshot capture requires include_seal")
    git_metadata = _direct_git_directory(path, label=label)
    if git_metadata is None and not _allow_synthetic_fixture:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        )
    real_checkout = git_metadata is not None

    def observe(args: list[str], *, max_bytes: int) -> str:
        try:
            result = runner(
                ["git", *args], cwd=path,
                timeout=_remaining_deadline_seconds(
                    deadline, label=label, ceiling=10.0,
                ),
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
        meta, sep, rel = record.partition("	")
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

    # Commit graphs can enumerate missing parents as bare object IDs, so every
    # ancestry commit still crosses the no-lazy-fetch object database boundary.
    # Current HEAD blobs stay fully checked. Agent OS also consumes historical
    # record trees for git log -- <record> dates, but not millions of unrelated
    # historical blobs/trees; prove that path-limited tree closure separately.
    def _object_closure() -> None:
        _require_git_object_types(
            path,
            {object_oid: "blob" for _rel, (_mode, object_oid) in expected.items()},
            runner=runner, env=env, deadline=deadline, label=label,
        )

    def _history_closure() -> None:
        _require_git_history_closure(path, head, runner=runner, env=env,
            deadline=deadline, label=label, record_trees=content_scope == "macro_brief")

    scoped_capture_files = (
        _macro_brief_content_paths(set(expected))
        if content_scope == "macro_brief" and snapshot_capture is not None
        else None
    )
    scoped_capture_directories = (
        _tree_directory_paths(scoped_capture_files)
        if scoped_capture_files is not None
        else None
    )

    def _worktree_inventory() -> tuple[dict[str, str], set[str], str]:
        try:
            if scoped_capture_files is not None and scoped_capture_directories is not None:
                observed = _scoped_worktree_path_sets(
                    path, files=set(scoped_capture_files),
                    directories=set(scoped_capture_directories),
                    deadline=deadline, label=label, verify_record_namespaces=True,
                )
            else:
                observed = _worktree_path_sets(path, deadline=deadline, label=label)
        except (OSError, TimeoutError) as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} worktree observation failed"
            ) from exc

        # This branch reuses the inventory worker for ancestry and record-tree
        # proof. Current blobs can progress on the other worker without adding
        # another proof thread or exposing either result before the join.
        if verify_repository_closure:
            _history_closure()
        return observed

    # The fixed HEAD tree makes current-blob proof independent of ancestry.
    # Reuse the existing two workers: blobs on one, inventory then history on
    # the other. Path-set comparison, byte verification, seal capture and
    # materialization still wait for all proofs to finish.
    _object_proof, (actual_types, actual_directories, metadata_seal) = (
        _overlap_full_proofs(
            object_closure=_object_closure if verify_repository_closure else None,
            worktree_inventory=_worktree_inventory,
        )
    )

    all_tree_directories = _tree_directory_paths(set(expected))
    if scoped_capture_files is not None and scoped_capture_directories is not None:
        expected_leaves = set(scoped_capture_files)
        expected_directories = set(scoped_capture_directories)
    elif admitted_worktree_files is None and admitted_worktree_directories is None:
        expected_leaves = set(expected)
        expected_directories = all_tree_directories
    elif admitted_worktree_files is None or admitted_worktree_directories is None:
        raise GatewayError(
            "backend_unavailable", f"installed {label} admitted worktree is incomplete"
        )
    else:
        expected_leaves = set(admitted_worktree_files)
        expected_directories = set(admitted_worktree_directories)
        implied_directories = _tree_directory_paths(expected_leaves)
        if (
            not expected_leaves <= set(expected)
            or not expected_directories <= all_tree_directories
            or not implied_directories <= expected_directories
        ):
            raise GatewayError(
                "backend_unavailable", f"installed {label} admitted worktree differs"
            )
    expected_types = {
        rel: ("symlink" if expected[rel][0] == "120000" else "regular")
        for rel in expected_leaves
    }
    if actual_types != expected_types or actual_directories != expected_directories:
        raise GatewayError("backend_unavailable", f"installed {label} worktree path set differs")
    try:
        content_paths = _content_paths_for_scope(set(expected), content_scope)
    except ValueError as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} content scope is invalid"
        ) from exc
    if not content_paths <= expected_leaves:
        raise GatewayError(
            "backend_unavailable", f"installed {label} admitted worktree omits read bytes"
        )
    byte_paths = expected_leaves if admitted_worktree_files is not None else content_paths
    if content_scope == "macro_brief" and any(
        expected[rel][0] == "120000" for rel in byte_paths
    ):
        # Agent OS dereferences the authored paths it actually consumes.  A symlink
        # in that read closure can therefore make the brief depend on target bytes
        # HEAD does not bind.  Tracked symlinks elsewhere remain fully path/type
        # bound but cannot influence this scoped reader.
        raise GatewayError("backend_unavailable", f"installed {label} symlinks are unsupported")
    for rel in sorted(byte_paths):
        mode, expected_oid = expected[rel]
        try:
            observed_oid = _raw_worktree_blob_oid(
                path / rel, mode=mode, deadline=deadline, label=label,
            )
        except (OSError, TimeoutError) as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} worktree observation failed"
            ) from exc
        if observed_oid != expected_oid:
            raise GatewayError("backend_unavailable", f"installed {label} worktree bytes differ")

    post_head = observe(["rev-parse", "--verify", "HEAD^{commit}"], max_bytes=256).strip()
    if post_head != head:
        raise GatewayError("backend_unavailable", f"installed {label} HEAD changed")
    if include_seal:
        refreshed_git_metadata = _direct_git_directory(path, label=label)
        if refreshed_git_metadata is None or refreshed_git_metadata != git_metadata:
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository topology is unsafe"
            )
        try:
            generation_seal = _git_generation_seal(
                refreshed_git_metadata, worktree_seal=metadata_seal,
                deadline=deadline, label=label,
            )
        except (OSError, TimeoutError) as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} generation seal failed"
            ) from exc
        if snapshot_capture is not None:
            if snapshot_capture:
                raise ValueError("snapshot capture must be empty")
            snapshot_capture.append(
                _VerifiedRepositorySnapshot(
                    root=path.resolve(),
                    head=head,
                    expected=MappingProxyType(dict(expected)),
                    worktree_seal=metadata_seal,
                    generation_seal=generation_seal,
                    sealed_to_caller=scoped_capture_files is not None,
                )
            )
        return head, generation_seal
    return head


def _snapshot_generation_observation(
    path: Path, *, runner: PacketRunner, env: Mapping[str, str], label: str,
    deadline: float | None = None, _allow_synthetic_fixture: bool = False,
) -> tuple[str, str]:
    """Re-read one already-verified repository's mutation generation cheaply."""
    git_metadata = _direct_git_directory(path, label=label)
    if git_metadata is None:
        observed = _clean_git_snapshot(
            path, runner=runner, env=env, label=label,
            content_scope="identity", include_seal=True,
            verify_repository_closure=False, deadline=deadline,
            _allow_synthetic_fixture=_allow_synthetic_fixture,
        )
        if not isinstance(observed, tuple):
            raise GatewayError(
                "backend_unavailable", f"installed {label} generation seal is unavailable"
            )
        return observed

    def observe_head() -> str:
        try:
            result = runner(
                ["git", "rev-parse", "--verify", "HEAD^{commit}"],
                cwd=path,
                timeout=_remaining_deadline_seconds(
                    deadline, label=label, ceiling=10.0,
                ),
                max_bytes=256, env=env,
            )
        except Exception as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} observation failed"
            ) from exc
        if (
            not isinstance(result, Mapping)
            or any(
                result.get(flag) is True
                for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
            )
            or result.get("code") != 0
            or type(result.get("stdout")) is not str
        ):
            raise GatewayError(
                "backend_unavailable", f"installed {label} observation failed"
            )
        head = result["stdout"].strip()
        if not _valid_sha(head):
            raise GatewayError(
                "backend_unavailable", f"installed {label} HEAD is unavailable"
            )
        return head

    head = observe_head()
    try:
        _actual_types, _actual_directories, worktree_seal = _worktree_path_sets(
            path, deadline=deadline, label=label,
        )
        generation_seal = _git_generation_seal(
            git_metadata, worktree_seal=worktree_seal,
            deadline=deadline, label=label,
        )
    except (OSError, TimeoutError) as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} generation seal failed"
        ) from exc
    if observe_head() != head:
        raise GatewayError("backend_unavailable", f"installed {label} HEAD changed")
    return head, generation_seal


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


def _verify_materialized_macro_root(
    path: Path, *, plan: _MacroMaterializationPlan, runner: PacketRunner,
    env: Mapping[str, str], deadline: float | None,
) -> tuple[str, str]:
    """Verify the sparse child root against the already-proved canonical tree."""
    label = "materialized Macro source"
    git_metadata = _direct_git_directory(path, label=label)
    if git_metadata is None:
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository topology is unsafe"
        )
    head = _bounded_git_text(
        path, ["rev-parse", "--verify", "HEAD^{commit}"],
        runner=runner, env=env, deadline=deadline, label=label, max_bytes=256,
    ).strip()
    if head != plan.head:
        raise GatewayError(
            "backend_unavailable", "installed Macro materialization SHA differs"
        )
    _require_git_object_types(
        path, {oid: "blob" for _mode, oid in plan.file_objects.values()},
        runner=runner, env=env, deadline=deadline, label=label,
    )
    expected_types = {rel: "regular" for rel in plan.files}
    try:
        actual_types, actual_directories, worktree_seal = _worktree_path_sets(
            path, deadline=deadline, label=label,
        )
    except (OSError, TimeoutError) as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} worktree observation failed"
        ) from exc
    if actual_types != expected_types or actual_directories != set(plan.directories):
        raise GatewayError(
            "backend_unavailable", f"installed {label} worktree path set differs"
        )
    for rel in sorted(plan.files):
        mode, expected_oid = plan.file_objects[rel]
        try:
            observed_oid = _raw_worktree_blob_oid(
                path / rel, mode=mode, deadline=deadline, label=label,
            )
        except (OSError, TimeoutError) as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} worktree observation failed"
            ) from exc
        if observed_oid != expected_oid:
            raise GatewayError(
                "backend_unavailable", f"installed {label} worktree bytes differ"
            )
    post_head = _bounded_git_text(
        path, ["rev-parse", "--verify", "HEAD^{commit}"],
        runner=runner, env=env, deadline=deadline, label=label, max_bytes=256,
    ).strip()
    if post_head != head:
        raise GatewayError("backend_unavailable", f"installed {label} HEAD changed")
    try:
        generation_seal = _git_generation_seal(
            git_metadata, worktree_seal=worktree_seal, deadline=deadline, label=label,
        )
    except (OSError, TimeoutError) as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} generation seal failed"
        ) from exc
    return head, generation_seal


@contextmanager
def _materialized_macro_root(
    source: Path, *, timeout: float, plan: _MacroMaterializationPlan | None = None,
    _allow_synthetic_fixture: bool = False,
) -> Iterator[Path]:
    git_metadata = _direct_git_directory(source, label="Macro source")
    if git_metadata is None:
        if _allow_synthetic_fixture:
            yield source
            return
        raise GatewayError(
            "backend_unavailable", "installed Macro source repository topology is unsafe"
        )
    if plan is None:
        raise GatewayError(
            "backend_unavailable", "installed Macro materialization plan is unavailable"
        )
    try:
        budget = float(timeout)
        if budget <= 0:
            raise TimeoutError("repository materialization has no remaining budget")
        deadline = time.monotonic() + budget
        with tempfile.TemporaryDirectory(prefix="mmx-executive-macro-") as temporary:
            temporary_root = Path(temporary).resolve()
            if _IS_DARWIN and temporary_root.stat().st_dev != source.stat().st_dev:
                raise OSError("copy-on-write materialization requires one filesystem")
            materialized = temporary_root / "macro"
            source_stat = source.lstat()
            materialized.mkdir(mode=stat.S_IMODE(source_stat.st_mode))
            _clone_git_read_database(
                git_metadata, materialized / ".git", deadline=deadline,
            )
            for rel in sorted(
                plan.directories, key=lambda value: (len(value.split("/")), value)
            ):
                _check_deadline(deadline, label="Macro materialization")
                source_directory = source / rel
                destination_directory = materialized / rel
                source_directory_stat = source_directory.lstat()
                if (
                    not stat.S_ISDIR(source_directory_stat.st_mode)
                    or stat.S_ISLNK(source_directory_stat.st_mode)
                ):
                    raise OSError("materialized Macro directory topology differs")
                destination_directory.mkdir(mode=stat.S_IMODE(source_directory_stat.st_mode))
                shutil.copystat(
                    source_directory, destination_directory, follow_symlinks=False,
                )
            for rel in sorted(plan.files):
                _clone_tree(source / rel, materialized / rel, deadline=deadline)
            shutil.copystat(source, materialized, follow_symlinks=False)
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


@dataclass
class _PacketCollection:
    future: concurrent.futures.Future[dict[str, Any]]
    subscribers: int = 0
    physical: int = 0
    started: bool = False


class InstalledBootPacketCollector:
    """Build one canonical packet from immutable code plus stable clean data roots."""

    def __init__(
        self, *, source_root: Path, macro_root: Path, code_root: Path,
        python_executable: Path, runner: PacketRunner | None = None,
        expected_source_sha: str | None = None,
        _allow_synthetic_fixture: bool = False,
    ) -> None:
        self._source_root = Path(source_root).resolve()
        self._macro_root = Path(macro_root).resolve()
        self._code_root = Path(code_root).resolve()
        # Preserve the configured environment entrypoint. Resolving a venv-style
        # symlink to its base interpreter would silently drop that environment's
        # site-packages under -I and recreate the missing-dependency failure.
        self._python = Path(python_executable).absolute()
        self._runner = runner or _default_packet_runner
        self._allow_synthetic_fixture = bool(_allow_synthetic_fixture)
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
        self._collection_lock = threading.Lock()
        self._collections: dict[tuple[str | None, float], _PacketCollection] = {}
        self._request_collection: contextvars.ContextVar[
            tuple[tuple[str | None, float], _PacketCollection] | None
        ] = contextvars.ContextVar("installed_packet_request", default=None)

    @contextmanager
    def canonical_project_compilation_scope(self, view, *, work_ref):
        """Select DATA for physical compiler captures, never for publication.

        Each fixed compiler call below enters its own full READ bracket. This
        enclosing source-action scope deliberately cannot extend the issued
        view's deadline across Git publication or a human Review.
        """
        from control_plane.project_canonical_data import CanonicalProjectDataView
        if type(view) is not CanonicalProjectDataView or view._code_root != self._macro_root:
            raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        view._require_work(work_ref)
        token = _CANONICAL_PROJECT_COMPILATION.set((self, view, work_ref))
        try:yield
        finally:_CANONICAL_PROJECT_COMPILATION.reset(token)

    @contextmanager
    def canonical_project_data_scope(self, view, *, work_ref):
        """Private installed composition; no serialized view can enter here."""
        from control_plane.project_canonical_data import CanonicalProjectDataView
        from common.workspace_project_journal_contract import validate_selection
        validate_selection({"work_ref": work_ref})
        if type(view) is not CanonicalProjectDataView or view._code_root != self._macro_root:
            raise ValueError("CANONICAL_DATA_UNAVAILABLE")
        view._require_work(work_ref)
        view.check()
        token = _CANONICAL_PROJECT_DATA.set((self, view, work_ref))
        try:
            yield
            view.check()
        finally:
            _CANONICAL_PROJECT_DATA.reset(token)

    def _discard_unused_collection(self, key, collection):
        if (not collection.started and collection.subscribers == 0
                and collection.physical == 0 and self._collections.get(key) is collection):
            del self._collections[key]

    @contextmanager
    def request_scope(self, *, now: str | None, timeout: float):
        """Join before executor admission, without starting any physical work.

        Only already-overlapping requests retain this future after publication.
        A later request cannot discover a completed packet in the collection map.
        asyncio.to_thread in the existing executor carries this request context.
        """
        key = (now, float(timeout))
        with self._collection_lock:
            collection = self._collections.get(key)
            if collection is None:
                collection = _PacketCollection(concurrent.futures.Future())
                self._collections[key] = collection
            collection.subscribers += 1
        token = self._request_collection.set((key, collection))
        try:
            yield
        finally:
            self._request_collection.reset(token)
            with self._collection_lock:
                collection.subscribers -= 1
                self._discard_unused_collection(key, collection)

    @contextmanager
    def physical_scope(self):
        """Keep an admitted thread's subscription through real physical drain."""
        bound = self._request_collection.get()
        if bound is None:
            yield
            return
        key, collection = bound
        with self._collection_lock:
            collection.physical += 1
        try:
            yield
        finally:
            with self._collection_lock:
                collection.physical -= 1
                self._discard_unused_collection(key, collection)

    def _repository_observation_pair(
        self, source_observer: Callable[[], tuple[str, str]],
        macro_observer: Callable[[], tuple[str, str]], *,
        deadline: float | None, label: str,
    ) -> tuple[tuple[str, str], tuple[str, str]]:
        if self._allow_synthetic_fixture:
            return source_observer(), macro_observer()

        # Reject unsafe/missing topology before dispatch.  The observers repeat the
        # checks while binding the exact generation; this first pass only decides
        # whether the real direct-Git path is eligible for bounded parallel reads.
        if (
            _direct_git_directory(self._source_root, label="Mastermind source") is None
            or _direct_git_directory(self._macro_root, label="Macro source") is None
        ):
            raise GatewayError(
                "backend_unavailable", "installed repository topology is unsafe"
            )
        try:
            timeout = _remaining_deadline_seconds(deadline, label=label)
        except TimeoutError as exc:
            raise GatewayError(
                "backend_unavailable",
                f"installed {label} exceeded its cumulative deadline",
            ) from exc

        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="mmx-installed-proof",
        )
        source_future = executor.submit(source_observer)
        macro_future = executor.submit(macro_observer)
        futures = {source_future, macro_future}
        pending: set[concurrent.futures.Future[tuple[str, str]]] = set(futures)
        wait_for_workers = True
        try:
            done, pending = concurrent.futures.wait(
                futures, timeout=timeout,
                return_when=concurrent.futures.FIRST_EXCEPTION,
            )
            failures: list[BaseException] = []
            for future in done:
                failure = future.exception()
                if failure is not None:
                    failures.append(failure)
            if failures:
                # A peer may still be completing a security-relevant topology
                # transition (including removal of a direct .git directory).
                # Join only within the existing deadline before choosing which
                # failure to report; never dispatch the helper on a failed read.
                if pending:
                    try:
                        remaining = _remaining_deadline_seconds(deadline, label=label)
                    except TimeoutError:
                        remaining = 0.0
                    _, pending = concurrent.futures.wait(pending, timeout=remaining)
                wait_for_workers = not pending
                # Concurrency can expose a lower-level Git error after repository
                # metadata disappears.  Recheck the direct topology before returning
                # the worker failure so the canonical, actionable cause remains stable.
                for root, root_label in (
                    (self._source_root, "Mastermind source"),
                    (self._macro_root, "Macro source"),
                ):
                    if _direct_git_directory(root, label=root_label) is None:
                        raise GatewayError(
                            "backend_unavailable",
                            f"installed {root_label} repository topology is unsafe",
                        )
                failure = failures[0]
                if isinstance(failure, GatewayError):
                    raise failure
                raise GatewayError(
                    "backend_unavailable", f"installed {label} observation failed"
                ) from failure
            if pending:
                wait_for_workers = False
                raise GatewayError(
                    "backend_unavailable",
                    f"installed {label} exceeded its cumulative deadline",
                )
            return source_future.result(), macro_future.result()
        finally:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=wait_for_workers, cancel_futures=True)

    def _snapshot_pair(
        self, env: Mapping[str, str], *, deadline: float | None,
        snapshot_capture: list[_VerifiedRepositorySnapshot] | None = None,
    ) -> tuple[str, str, str, str]:
        source_observation, macro_observation = self._repository_observation_pair(
            lambda: _clean_git_snapshot(
                self._source_root, runner=self._runner, env=env,
                label="Mastermind source", content_scope="identity", include_seal=True,
                deadline=deadline,
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
            ),
            lambda: _clean_git_snapshot(
                self._macro_root, runner=self._runner, env=env,
                label="Macro source", content_scope="macro_brief", include_seal=True,
                deadline=deadline,
                snapshot_capture=snapshot_capture,
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
            ),
            deadline=deadline, label="snapshot pair",
        )
        if not isinstance(source_observation, tuple) or not isinstance(macro_observation, tuple):
            raise GatewayError("backend_unavailable", "installed snapshot seal is unavailable")
        source_sha, source_seal = source_observation
        macro_sha, macro_seal = macro_observation
        if self._expected_source_sha is not None and source_sha != self._expected_source_sha:
            raise GatewayError("backend_unavailable", "installed Mastermind source SHA changed")
        return source_sha, macro_sha, source_seal, macro_seal

    def _canonical_code_capture_binding(self):
        return (self._source_root,self._macro_root,self._code_root,self._expected_source_sha,
                self._python,self._runner,self._allow_synthetic_fixture)

    def _capture_canonical_code(self):
        snapshots=[]
        observations=self._snapshot_pair(_installed_child_env(code_root=self._code_root,
            macro_root=self._macro_root),deadline=time.monotonic()+15.0,snapshot_capture=snapshots)
        if self._allow_synthetic_fixture or len(snapshots)!=1:
            raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        return _CanonicalCodeCapture(_CANONICAL_CODE_CAPTURE,self,
            self._canonical_code_capture_binding(),observations,snapshots[0])

    def _bind_canonical_code_capture(self,capture,view):
        from control_plane.project_canonical_data import CanonicalProjectDataView
        if (type(capture) is not _CanonicalCodeCapture or capture.seal is not _CANONICAL_CODE_CAPTURE
                or capture.owner is not self or capture.binding!=self._canonical_code_capture_binding()
                or capture.view is not None or capture.view_identity is not None
                or type(view) is not CanonicalProjectDataView
                or capture.observations[1]!=view.code_commit or capture.macro_snapshot.root!=self._macro_root):
            raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        view._owner._validate_view(view)
        view._owner._permission_guard(view._operation)
        view._verified_facts[_CANONICAL_CODE_CAPTURE]=_CanonicalCodeCapture(capture.seal,self,
            capture.binding,capture.observations,capture.macro_snapshot,view,view._owner._view_identity(view))

    def _discard_canonical_code_capture(self,view):
        view._verified_facts.pop(_CANONICAL_CODE_CAPTURE,None)

    def _take_canonical_code_capture(self,view,env,*,deadline):
        # Single use: even an unsuccessful build cannot lend this snapshot to
        # another scope/view. Current source/config generation is never cached.
        capture=view._verified_facts.pop(_CANONICAL_CODE_CAPTURE,None)
        if capture is None:return None
        if (type(capture) is not _CanonicalCodeCapture or capture.seal is not _CANONICAL_CODE_CAPTURE
                or capture.owner is not self or capture.view is not view
                or capture.view_identity!=view._owner._view_identity(view)
                or capture.binding!=self._canonical_code_capture_binding()
                or capture.observations[1]!=view.code_commit):
            raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        view.check()
        snapshot=capture.macro_snapshot
        # _snapshot_pair's captured Macro proof uses the exact brief scope,
        # rather than the unrelated whole checkout inventory. Compare the
        # current generation under that SAME scope before consuming it.
        files=_macro_brief_content_paths(set(snapshot.expected))
        plan=_MacroMaterializationPlan(snapshot.head,frozenset(files),
            frozenset(_tree_directory_paths(files)),
            MappingProxyType({path:snapshot.expected[path] for path in files}))
        if self._generation_pair(env,deadline=deadline,macro_plan=plan)!=capture.observations:
            raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        return capture

    def _generation_pair(
        self, env: Mapping[str, str], *, deadline: float | None,
        macro_plan: _MacroMaterializationPlan | None = None,
    ) -> tuple[str, str, str, str]:
        macro_observer: Callable[[], tuple[str, str]]
        if macro_plan is None or self._allow_synthetic_fixture:
            macro_observer = lambda: _snapshot_generation_observation(
                self._macro_root, runner=self._runner, env=env,
                label="Macro source", deadline=deadline,
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
            )
        else:
            macro_observer = lambda: _macro_plan_generation_observation(
                self._macro_root, plan=macro_plan, runner=self._runner,
                env=env, deadline=deadline,
            )
        source_observation, macro_observation = self._repository_observation_pair(
            lambda: _snapshot_generation_observation(
                self._source_root, runner=self._runner, env=env,
                label="Mastermind source", deadline=deadline,
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
            ),
            macro_observer,
            deadline=deadline, label="generation pair",
        )
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
        total_timeout = float(timeout)
        if total_timeout <= 0:
            raise GatewayError("backend_unavailable", "installed boot-packet timeout is invalid")
        # Share only overlapping identical source observations. The existing read
        # executor still owns admission and physical capacity; every caller builds
        # its own fresh Runtime/inbox projection after this packet is returned.
        # Remove the entry before publication, so completed packets and failures
        # are never cached or reused by a later call.
        key = (now, total_timeout)
        bound = self._request_collection.get()
        with self._collection_lock:
            collection = (bound[1] if bound is not None and bound[0] == key
                          else self._collections.get(key))
            if collection is None:
                collection = _PacketCollection(concurrent.futures.Future())
                self._collections[key] = collection
            owner = not collection.started
            if owner:
                collection.started = True
            future = collection.future
        if not owner:
            try:
                return copy.deepcopy(future.result(timeout=total_timeout))
            except concurrent.futures.TimeoutError as exc:
                raise GatewayError(
                    "backend_unavailable",
                    "installed boot-packet collector exceeded its cumulative deadline",
                ) from exc
        try:
            packet = self._collect_packet(repo=repo, now=now, timeout=total_timeout)
            shared_packet = copy.deepcopy(packet)
        except BaseException as exc:
            with self._collection_lock:
                if self._collections.get(key) is collection:
                    del self._collections[key]
                future.set_exception(exc)
            raise
        with self._collection_lock:
            if self._collections.get(key) is collection:
                del self._collections[key]
            future.set_result(shared_packet)
        return packet

    def product_acceptance_basis_reader(self, *, macro_root: Path):
        """Compose the core consumer at its existing installed-owner boundary."""
        from control_plane import agentos_product_acceptance_basis as basis

        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve()
                or self._code_root != basis._SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("installed Context requires the exact sealed source collector")
        reader = basis.AgentOsProductAcceptanceBasisReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        return reader

    def read_product_acceptance_basis(
        self, *, work_ref: str, execution_commission_ref: Any,
        root_objective: str, timeout: float = 15.0,
    ):
        """Read one workstream through the same sealed physical source owner.

        Only the trusted host supplies these Runtime-derived identities. This
        is not an MCP tool or authority grant, and cannot share the global
        boot-packet collection key. The protected workstream CLI must exist.
        """
        import math
        from common.commission_ref import CommissionRef
        from control_plane.agentos_product_acceptance_basis import ProductAcceptanceBasisUnavailable
        if (type(work_ref) is not str
                or re.fullmatch(r"WS:[A-Z0-9][A-Z0-9-]{1,63}", work_ref) is None
                or type(execution_commission_ref) is not CommissionRef
                or type(root_objective) is not str
                or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or not 0 < timeout <= 15.0
                or self._expected_source_sha is None):
            raise ProductAcceptanceBasisUnavailable("BASIS_BINDING_UNAVAILABLE")
        return self._collect_packet(
            repo=self._source_root, now=None, timeout=float(timeout),
            acceptance_request=(work_ref, execution_commission_ref, root_objective),
        )

    def project_instructions_reader(self, *, macro_root: Path):
        """Issue content-only facade from this same qualified installed owner."""
        from control_plane.agentos_project_instructions import AgentOsProjectInstructionsReader, _SOURCE_ROOT
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("installed project instructions source is unavailable")
        reader = AgentOsProjectInstructionsReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        reader._installed_reader_binding = _issue_installed_project_read(reader, owner=self, kind="project_instructions",
            qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector)
        return reader

    def read_project_instructions(self, *, work_ref: str, timeout: float = 15.0):
        from common.workspace_project_instructions_contract import validate_selection
        import math
        validate_selection({"work_ref": work_ref})
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 15 or self._expected_source_sha is None):
            raise ValueError("installed project instructions source is unavailable")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
            project_instructions_request=work_ref)

    def agentos_context_reader(self, *, macro_root: Path):
        """Issue one adopted-snapshot content reader; grant no public capability."""
        from control_plane.agentos_context_bundle import AgentOsContextBundleReader, _SOURCE_ROOT
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("SOURCE_UNAVAILABLE")
        reader = AgentOsContextBundleReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        reader._installed_reader_binding = _issue_installed_project_read(reader, owner=self, kind="agentos_context",
            qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector)
        return reader

    def read_agentos_context(self, *, work_ref: str, timeout: float = 25.0):
        from common.workspace_project_plan_contract import validate_selection
        import math
        validate_selection({"work_ref": work_ref})
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 25
                or self._expected_source_sha is None or self._allow_synthetic_fixture
                or _CANONICAL_PROJECT_DATA.get() is not None or _CANONICAL_PROJECT_COMPILATION.get() is not None):
            raise ValueError("SOURCE_UNAVAILABLE")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout), agentos_context_request=work_ref)

    def read_current_agentos_context(self, *, work_ref: str, timeout: float = 25.0):
        """Read current DATA only inside the original nominal installed view.

        This method neither selects a principal nor acquires publication or
        latest-DATA authority. The existing installed DATA owner supplies both.
        """
        from common.workspace_project_plan_contract import validate_selection
        import math
        validate_selection({"work_ref": work_ref})
        bound = _CANONICAL_PROJECT_DATA.get()
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 25
                or self._expected_source_sha is None or self._allow_synthetic_fixture
                or type(bound) is not tuple or len(bound) != 3
                or bound[0] is not self or bound[2] != work_ref
                or _CANONICAL_PROJECT_COMPILATION.get() is not None):
            raise ValueError("SOURCE_UNAVAILABLE")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
                                    agentos_context_request=work_ref, agentos_context_current=True)

    def project_plan_reader(self, *, macro_root: Path):
        """Issue a read facade bound to this exact installed source owner."""
        from control_plane.agentos_project_plan import AgentOsProjectPlanReader, _SOURCE_ROOT
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("installed project plan source is unavailable")
        reader = AgentOsProjectPlanReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        reader._installed_reader_binding = _issue_installed_project_read(
            reader, owner=self, kind="project_plan",
            qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector,
        )
        return reader

    def read_project_plan(self, *, work_ref: str, timeout: float = 15.0):
        from common.workspace_project_plan_contract import validate_selection
        import math
        validate_selection({"work_ref": work_ref})
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 15 or self._expected_source_sha is None):
            raise ValueError("installed project plan source is unavailable")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
                                    project_plan_request=work_ref)

    def read_project_discovery(self, *, work_ref: str, observed_at_ms: int, timeout: float = 15.0):
        """One exact current-DATA WS compiled by the pinned canonical owner."""
        from common.workspace_project_plan_contract import validate_selection
        validate_selection({'work_ref': work_ref})
        bound = _CANONICAL_PROJECT_DATA.get()
        if (bound is None or bound[0] is not self or bound[2] != work_ref
                or type(observed_at_ms) is not int
                or bound[1].witness()['canonical_observed_at_ms'] != observed_at_ms
                or type(timeout) not in (int, float) or not 0 < timeout <= 15
                or self._expected_source_sha is None):
            raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
            project_discovery_request=(work_ref, observed_at_ms))

    def project_archive_reader(self, *, macro_root: Path):
        from control_plane.agentos_project_archive import AgentOsProjectArchiveReader, _SOURCE_ROOT
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("SOURCE_UNAVAILABLE")
        reader = AgentOsProjectArchiveReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        reader._installed_reader_binding = _issue_installed_project_read(reader, owner=self, kind="project_archive",
            qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector)
        return reader

    def read_project_archive(self, *, work_refs, expected_current_macro_sha, timeout: float = 15.0):
        from common import workspace_project_archive_contract as wire
        import math
        refs = wire.validate_refs(work_refs)
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 15
                or not wire._hex(expected_current_macro_sha, 40) or self._expected_source_sha is None):
            raise ValueError("SOURCE_UNAVAILABLE")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
            project_archive_request=(refs, expected_current_macro_sha))

    def project_direction_reader(self, *, macro_root: Path):
        """Issue the fixed Direction facade after exact installed qualification."""
        from control_plane.agentos_project_direction import AgentOsProjectDirectionReader, _SOURCE_ROOT
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("SOURCE_UNAVAILABLE")
        reader = AgentOsProjectDirectionReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        reader._installed_reader_binding = _issue_installed_project_read(
            reader, owner=self, kind="project_direction",
            qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector,
        )
        return reader

    def read_project_direction(self, *, work_ref: str, timeout: float = 15.0):
        from common.workspace_project_direction_contract import selection
        import math
        selection({"work_ref": work_ref})
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 15 or self._expected_source_sha is None):
            raise ValueError("SOURCE_UNAVAILABLE")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
                                    project_direction_request=work_ref)

    def project_journal_reader(self, *, macro_root: Path):
        """Issue a read facade bound to this exact installed source owner."""
        from control_plane.agentos_project_journal import AgentOsProjectJournalReader, _SOURCE_ROOT
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("installed project journal source is unavailable")
        reader = AgentOsProjectJournalReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        reader._installed_reader_binding = _issue_installed_project_read(
            reader, owner=self, kind="project_journal",
            qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector,
        )
        return reader

    def read_project_journal(self, *, work_ref: str, timeout: float = 15.0):
        from common.workspace_project_journal_contract import validate_selection
        import math
        validate_selection({"work_ref": work_ref})
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 15 or self._expected_source_sha is None):
            raise ValueError("installed project journal source is unavailable")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
                                    project_journal_request=work_ref)

    def _project_knowledge_reader(self, *, macro_root, reader_type, kind):
        from control_plane import installed_project_knowledge_readers as readers
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        root = Path(macro_root)
        allowed = {
            "project_knowledge_catalogue": readers.AgentOsProjectKnowledgeCatalogueReader,
            "project_knowledge_memory": readers.AgentOsProjectKnowledgeMemoryReader,
            "project_knowledge_source": readers.AgentOsProjectKnowledgeSourceReader,
            "project_discovery_source": readers.AgentOsProjectDiscoverySourceReader,
        }
        if (allowed.get(kind) is not reader_type or not root.is_absolute()
                or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != readers._SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("installed project knowledge source is unavailable")
        reader = reader_type(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        reader._installed_reader_binding = _issue_installed_project_read(reader, owner=self,
            kind=kind, qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector)
        return reader

    def project_knowledge_catalogue_reader(self, *, macro_root):
        from control_plane.installed_project_knowledge_readers import AgentOsProjectKnowledgeCatalogueReader
        return self._project_knowledge_reader(macro_root=macro_root,
            reader_type=AgentOsProjectKnowledgeCatalogueReader, kind="project_knowledge_catalogue")

    def project_knowledge_memory_reader(self, *, macro_root):
        from control_plane.installed_project_knowledge_readers import AgentOsProjectKnowledgeMemoryReader
        return self._project_knowledge_reader(macro_root=macro_root,
            reader_type=AgentOsProjectKnowledgeMemoryReader, kind="project_knowledge_memory")

    def project_knowledge_source_reader(self, *, macro_root):
        from control_plane.installed_project_knowledge_readers import AgentOsProjectKnowledgeSourceReader
        return self._project_knowledge_reader(macro_root=macro_root,
            reader_type=AgentOsProjectKnowledgeSourceReader, kind="project_knowledge_source")

    def project_discovery_source_reader(self, *, macro_root):
        from control_plane.installed_project_knowledge_readers import AgentOsProjectDiscoverySourceReader
        return self._project_knowledge_reader(macro_root=macro_root,
            reader_type=AgentOsProjectDiscoverySourceReader, kind="project_discovery_source")

    def _read_project_knowledge(self, *, operation, selected, timeout):
        import math
        from common.workspace_project_knowledge_read_contract import selection
        selected = selection(selected, operation=operation)
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 15 or self._expected_source_sha is None):
            raise ValueError("installed project knowledge source is unavailable")
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
            project_knowledge_request=(operation, selected))

    def read_project_knowledge_catalogue(self, *, work_ref, timeout=15.0):
        return self._read_project_knowledge(operation="project_knowledge_catalogue",
            selected={"work_ref": work_ref}, timeout=timeout)

    def read_project_knowledge_memory(self, *, work_ref, timeout=15.0):
        return self._read_project_knowledge(operation="project_knowledge_memory",
            selected={"work_ref": work_ref}, timeout=timeout)

    def read_project_knowledge_source(self, *, work_ref, source_ref, expected_revision, timeout=15.0):
        return self._read_project_knowledge(operation="project_knowledge_source",
            selected={"work_ref": work_ref, "source_ref": source_ref,
                      "expected_revision": expected_revision}, timeout=timeout)

    def read_project_discovery_source(self, *, work_ref, discovery_ref, expected_source_commit, timeout=15.0):
        return self._read_project_knowledge(operation="project_discovery_source",
            selected={"work_ref": work_ref, "discovery_ref": discovery_ref,
                      "expected_source_commit": expected_source_commit}, timeout=timeout)

    def project_creation_source_reader(self, *, macro_root: Path):
        from control_plane.agentos_project_creation_source import AgentOsProjectCreationReader, _SOURCE_ROOT
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("installed project creation source is unavailable")
        reader = AgentOsProjectCreationReader(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        reader._installed_reader_binding = _issue_installed_project_read(reader, owner=self,
            kind="project_creation_source", qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector)
        return reader

    def read_project_creation_source(self, *, work_ref, record_commit, expected_current_macro_sha=None, timeout=15.0):
        from common.workspace_project_journal_contract import validate_selection
        from common.workspace_project_session_contract import _hex
        import math
        validate_selection({"work_ref": work_ref})
        if (not _hex(record_commit, 40) or not _hex(expected_current_macro_sha, 40)
                or type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 15 or self._expected_source_sha is None):
            raise ValueError("installed project creation source is unavailable")
        packet = self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
            project_creation_request=(work_ref, record_commit, expected_current_macro_sha))
        if packet["availability"] != "AVAILABLE":
            raise ValueError(packet["reason"].lower())
        return packet["source"]

    def project_knowledge_recipe_reader(self, *, macro_root: Path):
        from control_plane.installed_project_knowledge_compiler import InstalledProjectKnowledgeCompiler, _SOURCE_ROOT
        from control_plane.installed_project_read_binding import _issue_installed_project_read
        root = Path(macro_root)
        if (not root.is_absolute() or type(self) is not InstalledBootPacketCollector
                or self._macro_root != root.resolve() or self._code_root != _SOURCE_ROOT.resolve()
                or self._expected_source_sha is None or self._allow_synthetic_fixture):
            raise ValueError("installed project knowledge compiler unavailable")
        reader = InstalledProjectKnowledgeCompiler(macro_root=root)
        reader._installed_context_owner = self
        reader._installed_context_binding = reader._context_binding(self)
        reader._installed_reader_binding = _issue_installed_project_read(reader, owner=self,
            kind="project_knowledge_recipe", qualified_owner=lambda owner: type(owner) is InstalledBootPacketCollector)
        return reader

    def read_project_knowledge_recipe(self, *, mode, request, actor_ref,
            permission_binding_digest, decision_date, initial_snapshot=None, source_binding=None, timeout=15.0):
        import math
        from datetime import date
        if (type(mode) is not str or mode not in {"prepare", "restore"}
                or type(request) is not dict or type(actor_ref) is not str
                or re.fullmatch(r"workspace:[0-9a-f]{64}", actor_ref) is None
                or type(permission_binding_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", permission_binding_digest) is None
                or type(decision_date) is not str
                or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", decision_date) is None
                or type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 15 or self._expected_source_sha is None
                or (mode == "prepare" and (initial_snapshot is not None or source_binding is not None))
                or (mode == "restore" and (type(initial_snapshot) is not dict or type(source_binding) is not dict))):
            raise ValueError("installed project knowledge compiler unavailable")
        date.fromisoformat(decision_date)
        body = {"schema": "mastermind.project_knowledge_recipe_capture_request.v1", "request": request,
                "trusted": {"actor_ref": actor_ref, "permission_binding_digest": permission_binding_digest,
                            "decision_date": decision_date}}
        if mode == "restore":
            body.update(initial_snapshot=initial_snapshot, source_binding=source_binding)
        try:
            encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
            if len(encoded) > 524288:
                raise ValueError()
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ValueError("installed project knowledge compiler unavailable") from None
        bound = _CANONICAL_PROJECT_COMPILATION.get()
        if bound is not None:
            if bound[0] is not self or bound[2] != request['work_ref']:
                raise ValueError('CANONICAL_DATA_UNAVAILABLE')
            # Compilation/restoration is a pure capture. Keep its immutable
            # C/N facts inside the existing original-budget capture scope;
            # the later publisher effect remains outside this scope.
            with bound[1].capture_scope():
                with self.canonical_project_data_scope(bound[1], work_ref=bound[2]):
                    return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
                        project_knowledge_recipe_request=(mode, body, encoded))
        return self._collect_packet(repo=self._source_root, now=None, timeout=float(timeout),
                                    project_knowledge_recipe_request=(mode, body, encoded))

    def _collect_packet(self, *, repo: Path, now: str | None,
                        timeout: float, acceptance_request: tuple | None = None,
                        agentos_context_request: str | None = None,
                        agentos_context_current: bool = False,
                        project_plan_request: str | None = None,
                        project_journal_request: str | None = None,
                        project_creation_request: tuple | None = None,
                        project_direction_request: str | None = None,
                        project_archive_request: tuple | None = None,
                        project_knowledge_recipe_request: tuple | None = None,
                        project_knowledge_request: tuple | None = None,
                        project_instructions_request: str | None = None,
                        project_discovery_request: tuple | None = None) -> Any:
        if sum(x is not None for x in (acceptance_request, agentos_context_request, project_plan_request, project_journal_request, project_creation_request, project_direction_request, project_archive_request, project_knowledge_recipe_request, project_knowledge_request, project_instructions_request, project_discovery_request)) > 1:
            raise ValueError("ambiguous installed source read")
        bound_data = _CANONICAL_PROJECT_DATA.get()
        if type(agentos_context_current) is not bool or (agentos_context_current and agentos_context_request is None):
            raise ValueError("SOURCE_UNAVAILABLE")
        if agentos_context_request is not None:
            from common.workspace_project_plan_contract import validate_selection
            validate_selection({"work_ref": agentos_context_request})
            if (self._allow_synthetic_fixture
                    or (bound_data is None if agentos_context_current else bound_data is not None)
                    or _CANONICAL_PROJECT_COMPILATION.get() is not None):
                raise ValueError("SOURCE_UNAVAILABLE")
        data_view = None
        if project_discovery_request is not None and bound_data is None:
            raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        if bound_data is not None:
            if (bound_data[0] is not self or self._allow_synthetic_fixture
                    or (project_knowledge_request is None and project_knowledge_recipe_request is None
                        and project_plan_request is None and project_discovery_request is None
                        and not agentos_context_current)):
                raise ValueError("CANONICAL_DATA_UNAVAILABLE")
            selected_work = (project_knowledge_request[1]["work_ref"] if project_knowledge_request is not None
                             else project_plan_request if project_plan_request is not None
                             else project_discovery_request[0] if project_discovery_request is not None
                             else agentos_context_request if agentos_context_current
                             else project_knowledge_recipe_request[1]["request"].get("work_ref"))
            if selected_work != bound_data[2]:
                raise ValueError("CANONICAL_DATA_UNAVAILABLE")
            data_view = bound_data[1]
            data_view._require_work(selected_work)
            data_view.check()
        deadline = time.monotonic() + timeout
        if data_view is not None:
            # The collector/child cannot acquire another observation lifetime.
            # Reserve all source/materialization work from the issued view's
            # original remaining budget, including compiler restoration.
            deadline = min(deadline, data_view._operation.read_deadline)

        def remaining() -> float:
            try:
                return _remaining_deadline_seconds(
                    deadline, label="boot-packet collector",
                )
            except TimeoutError as exc:
                raise GatewayError(
                    "backend_unavailable",
                    "installed boot-packet collector exceeded its cumulative deadline",
                ) from exc

        live_env = _installed_child_env(
            code_root=self._code_root, macro_root=self._macro_root,
        )
        macro_snapshots: list[_VerifiedRepositorySnapshot] = []
        retained = None if data_view is None else self._take_canonical_code_capture(data_view,live_env,deadline=deadline)
        if retained is not None:
            pre_source_sha,pre_macro_sha,pre_source_seal,pre_macro_seal=retained.observations
            macro_snapshots.append(retained.macro_snapshot)
        else:
            pre_source_sha, pre_macro_sha, pre_source_seal, pre_macro_seal = self._snapshot_pair(
                live_env, deadline=deadline,
                snapshot_capture=(
                    None if self._allow_synthetic_fixture else macro_snapshots
                ),
            )
        if project_creation_request is not None and pre_macro_sha != project_creation_request[2]:
            raise GatewayError("backend_unavailable", "project catalogue source changed")
        if project_archive_request is not None and pre_macro_sha != project_archive_request[1]:
            raise GatewayError("backend_unavailable", "project catalogue source changed")
        if (project_knowledge_recipe_request is not None and project_knowledge_recipe_request[0] == "prepare"
                and project_knowledge_recipe_request[1]["request"].get("source_commit") != (pre_macro_sha if data_view is None else data_view.data_commit)):
            raise GatewayError("backend_unavailable", "project knowledge source changed")
        materialization_plan = None
        if not self._allow_synthetic_fixture:
            if len(macro_snapshots) != 1:
                raise GatewayError(
                    "backend_unavailable",
                    "installed Macro verified snapshot is unavailable",
                )
            materialization_plan = _build_macro_materialization_plan(
                self._macro_root, runner=self._runner, env=live_env, deadline=deadline,
                verified_snapshot=macro_snapshots[0],
                **({"agentos_context": True} if agentos_context_request is not None else {}),
            )
            if materialization_plan.head != pre_macro_sha:
                raise GatewayError(
                    "backend_unavailable", "installed Macro materialization SHA differs"
                )
            pre_macro_sha, pre_macro_seal = _macro_plan_generation_observation(
                self._macro_root, plan=materialization_plan, runner=self._runner,
                env=live_env, deadline=deadline,
            )
        if data_view is not None and data_view.code_commit != pre_macro_sha:
            raise GatewayError("backend_unavailable", "configured CODE source changed")
        expected_packet_macro_sha = pre_macro_sha if data_view is None else data_view.data_commit
        @contextmanager
        def materialization():
            if data_view is None:
                with _materialized_macro_root(self._macro_root, timeout=remaining(), plan=materialization_plan,
                        _allow_synthetic_fixture=self._allow_synthetic_fixture) as root:
                    yield root, materialization_plan
            else:
                from integrations.executive_mcp.project_data_materialization import materialized_project_data
                with materialized_project_data(data_view, pinned_macro_root=self._macro_root, deadline=deadline,
                                               agentos_context=agentos_context_current) as pair:
                    yield pair
        with materialization() as (packet_macro_root, packet_plan):
            child_env = _installed_child_env(
                code_root=self._code_root, macro_root=packet_macro_root,
            )
            materialized_observation: tuple[str, str] | None = None
            if packet_macro_root != self._macro_root:
                if packet_plan is None:
                    raise GatewayError(
                        "backend_unavailable",
                        "installed Macro materialization plan is unavailable",
                    )
                materialized_observation = _verify_materialized_macro_root(
                    packet_macro_root, plan=packet_plan,
                    runner=self._runner, env=child_env, deadline=deadline,
                )
                if materialized_observation[0] != expected_packet_macro_sha:
                    raise GatewayError(
                        "backend_unavailable", "installed Macro materialization SHA differs"
                    )
            inner_timeout = _inner_packet_timeout(remaining())
            argv = [os.fspath(self._python), "-I", "-B",
                    os.fspath(self._code_root / "scripts" / "ceo_boot_packet.py"),
                    "--json", "--repo-root", os.fspath(repo),
                    "--macro-root", os.fspath(packet_macro_root),
                    "--timeout", f"{inner_timeout:g}"]
            if now is not None:
                argv.extend(["--now", now])
            if acceptance_request is not None:
                argv.extend(["--workstream", acceptance_request[0][3:],
                             "--expected-macro-sha", expected_packet_macro_sha])
            if project_instructions_request is not None:
                argv = [os.fspath(self._python), "-I", "-B",
                    os.fspath(self._code_root / "scripts" / "agentos_project_instructions_entry.py"),
                    "--macro-root", os.fspath(packet_macro_root), "--expected-macro-sha", pre_macro_sha,
                    "--work-ref", project_instructions_request, "--timeout", f"{inner_timeout:g}"]
            if agentos_context_request is not None:
                if materialized_observation is None or packet_plan is None:
                    raise GatewayError("backend_unavailable", "installed context materialization unavailable")
                context_sources, context_inventory = _agentos_context_sources(packet_macro_root, packet_plan, remaining=remaining)
                context_current = None
                if agentos_context_current:
                    # The installed compiler bytes, helper and fixed context
                    # configuration must remain identical at C and N. Current
                    # DATA supplies records/probes, never new executable code.
                    code_sources, _ = _agentos_context_sources(self._macro_root, materialization_plan, remaining=remaining)
                    if (context_sources != code_sources or any(
                            materialization_plan.file_objects.get(path) != packet_plan.file_objects.get(path)
                            for path in _AGENTOS_CONTEXT_CONFIG)):
                        raise GatewayError("backend_unavailable", "context CODE compatibility differs")
                    witness = data_view.witness()
                    if "data_continuity" in witness:
                        # The older Knowledge closure alone does not cover
                        # all context records/config/probes or Git-derived
                        # dates. Even equal file blobs cannot certify its full
                        # inputs. This version needs C=N or the original
                        # same-principal canonical publication Event.
                        raise GatewayError("backend_unavailable", "context DATA continuity is unqualified")
                    # N has an independent Git object database. Reuse the
                    # original path-limited history proof before the compiler
                    # may silently turn a failed per-record git log into None.
                    _require_git_history_closure(packet_macro_root, expected_packet_macro_sha,
                        runner=self._runner, env=child_env, deadline=deadline,
                        label="current context DATA", record_trees=True)
                    context_current = {"data_observation": witness}
                context_site, context_runtime = _agentos_context_runtime(self._python, runner=self._runner, remaining=remaining)
                argv = [os.fspath(self._python), "-I", "-S", "-B",
                    os.fspath(self._code_root / "scripts/agentos_context_bundle_entry.py"),
                    "--macro-root", os.fspath(packet_macro_root), "--work-ref", agentos_context_request,
                    "--site-packages", os.fspath(context_site)]
            if project_plan_request is not None:
                argv = [os.fspath(self._python), "-I", "-B",
                        os.fspath(self._code_root / "scripts" / "agentos_project_plan_entry.py"),
                        "--macro-root", os.fspath(packet_macro_root),
                        "--expected-macro-sha", expected_packet_macro_sha,
                        "--work-ref", project_plan_request,
                        "--continuity",
                        "--timeout", f"{inner_timeout:g}"]
            if project_discovery_request is not None:
                argv = [os.fspath(self._python), '-I', '-B',
                    os.fspath(self._code_root / 'scripts' / 'agentos_project_discovery_entry.py'),
                    '--macro-root', os.fspath(packet_macro_root), '--expected-macro-sha', expected_packet_macro_sha,
                    '--work-ref', project_discovery_request[0], '--observed-at-ms', str(project_discovery_request[1]),
                    '--timeout', f'{inner_timeout:g}']
            if project_journal_request is not None:
                argv = [os.fspath(self._python), "-I", "-B",
                        os.fspath(self._code_root / "scripts" / "agentos_project_journal_entry.py"),
                        "--macro-root", os.fspath(packet_macro_root),
                        "--expected-macro-sha", expected_packet_macro_sha,
                        "--work-ref", project_journal_request,
                        "--timeout", f"{inner_timeout:g}"]
            if project_creation_request is not None:
                argv = [os.fspath(self._python), "-I", "-B",
                    os.fspath(self._code_root / "scripts" / "agentos_project_creation_source_entry.py"),
                    "--macro-root", os.fspath(packet_macro_root), "--expected-macro-sha", expected_packet_macro_sha,
                    "--work-ref", project_creation_request[0], "--record-commit", project_creation_request[1],
                    "--timeout", f"{inner_timeout:g}"]
            if project_direction_request is not None:
                argv = [os.fspath(self._python), "-I", "-B",
                        os.fspath(self._code_root / "scripts" / "agentos_project_direction_entry.py"),
                        "--macro-root", os.fspath(packet_macro_root),
                        "--expected-macro-sha", pre_macro_sha,
                        "--work-ref", project_direction_request,
                        "--timeout", f"{inner_timeout:g}"]
            if project_archive_request is not None:
                argv = [os.fspath(self._python), "-I", "-B",
                    os.fspath(self._code_root / "scripts" / "agentos_project_archive_entry.py"),
                    "--macro-root", os.fspath(packet_macro_root), "--expected-macro-sha", pre_macro_sha,
                    "--work-refs-json", json.dumps(project_archive_request[0], separators=(",", ":")),
                    "--timeout", f"{inner_timeout:g}"]
            if project_knowledge_recipe_request is not None:
                argv = [os.fspath(self._python), "-I", "-B",
                    os.fspath(self._code_root / "scripts" / "agentos_project_knowledge_recipe_entry.py"),
                    "--macro-root", os.fspath(packet_macro_root), "--expected-macro-sha", expected_packet_macro_sha,
                    "--mode", project_knowledge_recipe_request[0], "--timeout", f"{inner_timeout:g}"]
            if project_knowledge_request is not None:
                operation, selected = project_knowledge_request
                from common.workspace_project_knowledge_read_contract import selection
                selection(selected, operation=operation)
                argv = [os.fspath(self._python), "-I", "-B",
                    os.fspath(self._code_root / "scripts" / "agentos_project_knowledge_entry.py"),
                    "--macro-root", os.fspath(packet_macro_root), "--expected-macro-sha", expected_packet_macro_sha,
                    "--operation", operation, "--work-ref", selected["work_ref"],
                    "--timeout", f"{inner_timeout:g}"]
                if operation == "project_knowledge_source":
                    argv.extend(["--source-ref", selected["source_ref"],
                                 "--expected-revision", selected["expected_revision"]])
                elif operation == "project_discovery_source":
                    argv.extend(["--discovery-ref", selected["discovery_ref"],
                                 "--expected-source-commit", selected["expected_source_commit"]])
            if data_view is not None:
                argv.extend(["--code-root", os.fspath(self._macro_root), "--code-commit", data_view.code_commit])
            output_limit = (131072 if project_archive_request is not None else
                            65536 if project_direction_request is not None else
                            262144 if acceptance_request is not None or project_plan_request is not None or project_journal_request is not None or project_discovery_request is not None
                            else ceo_boot_packet.DEFAULT_MAX_OUTPUT_BYTES)
            if project_instructions_request is not None:
                output_limit = 32768
            if agentos_context_request is not None:
                from control_plane.agentos_context_bundle import MAX_BUNDLE_BYTES
                output_limit = MAX_BUNDLE_BYTES
            if project_creation_request is not None:
                output_limit = 4096
            if project_knowledge_request is not None:
                output_limit = 131072
            if project_knowledge_recipe_request is not None:
                output_limit = 524288
            try:
                extra = {} if project_knowledge_recipe_request is None else {"input_bytes": project_knowledge_recipe_request[2]}
                result = self._runner(
                    argv, cwd=self._code_root, timeout=remaining(),
                    max_bytes=output_limit, env=child_env, **extra,
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
            if agentos_context_request is not None:
                from control_plane import agentos_context_bundle as context_contract
                from ops.fabric_launch.agentos import validate_bundle
                try:
                    if (type(result.get("code")) is not int or type(result.get("stderr")) is not str
                            or any(type(result.get(flag)) is not bool for flag in ("timed_out", "limit_exceeded", "invalid_utf8"))):
                        raise ValueError("invalid context result")
                    raw = stdout.encode("utf-8", "strict")
                    bundle = validate_bundle(raw, agentos_context_request)
                    if (bundle.get("repo_sha") != expected_packet_macro_sha or type(bundle.get("token_budget")) is not int
                            or bundle["token_budget"] != context_contract.TOKEN_BUDGET):
                        raise ValueError("context identity differs")
                    receipt = {"schema": (context_contract.CURRENT_RECEIPT_SCHEMA_V2 if agentos_context_current else context_contract.RECEIPT_SCHEMA), "owner": "agent_os",
                        "source_mode": (context_contract.CURRENT_SOURCE_MODE if agentos_context_current else context_contract.SOURCE_MODE), "workstream": agentos_context_request,
                        "token_budget": context_contract.TOKEN_BUDGET, "bundle_sha256": hashlib.sha256(raw).hexdigest(),
                        "source_script_sha256": next(item["sha256"] for item in context_sources if item["path"] == "scripts/agentos.py"),
                        "compiler_sources": context_sources, "compiler_sources_scope": "fixed_macro_entry_and_helper",
                        "source_inventory_sha256": context_inventory, "source_inventory_files": len(packet_plan.files),
                        "compiler_closure_sha256": context_contract.compiler_closure_digest(context_sources, context_runtime, context_inventory),
                        "mastermind_source_sha": pre_source_sha, "compiler_code_commit": pre_macro_sha,
                        "data_commit": expected_packet_macro_sha, "repo_sha": expected_packet_macro_sha, "runtime_commitment": context_runtime,
                        "import_policy": context_contract.IMPORT_POLICY, "deadline_semantics": context_contract.DEADLINE_SEMANTICS,
                        "source_observation": {"mastermind_generation": pre_source_seal, "macro_generation": pre_macro_seal,
                                               "materialized_generation": materialized_observation[1]},
                        "generated_at": bundle.get("generated_at"), "degraded_count": len(bundle["degraded"]),
                        "omitted_count": len(bundle["omitted_due_to_budget"]), "execution_authority": False}
                    if agentos_context_current:
                        receipt.update(context_current)
                        receipt["selected_record_sources"] = _agentos_selected_record_sources(
                            packet_macro_root, packet_plan, raw=raw, bundle=bundle,
                            work_ref=agentos_context_request, remaining=remaining)
                    validator = (context_contract.validate_current_context_read if agentos_context_current
                                 else context_contract.validate_context_read)
                    packet = validator(raw, receipt, work_ref=agentos_context_request)
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed context bundle unavailable") from None
                if _agentos_context_runtime(self._python, runner=self._runner, remaining=remaining) != (context_site, context_runtime):
                    raise GatewayError("backend_unavailable", "installed context runtime changed")
            elif project_knowledge_recipe_request is not None:
                try:
                    def unique_recipe_object(pairs):
                        value = {}
                        for key, item in pairs:
                            if key in value: raise ValueError()
                            value[key] = item
                        return value
                    def nonfinite_recipe(_value):
                        raise ValueError()
                    packet = json.loads(stdout, object_pairs_hook=unique_recipe_object, parse_constant=nonfinite_recipe)
                    if (type(packet) is not dict or set(packet) != {"schema", "recipe", "initial_snapshot", "source_binding"}
                            or packet["schema"] != "mastermind.project_knowledge_recipe_capture.v1"
                            or any(type(packet[key]) is not dict for key in ("recipe", "initial_snapshot", "source_binding"))):
                        raise ValueError()
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed project knowledge compiler unavailable") from None
            elif project_creation_request is not None:
                from common.workspace_project_session_contract import validate_source_observation
                try:
                    def unique_creation_object(pairs):
                        value = {}
                        for key, item in pairs:
                            if key in value: raise ValueError("duplicate creation field")
                            value[key] = item
                        return value
                    packet = validate_source_observation(json.loads(stdout, object_pairs_hook=unique_creation_object),
                        work_ref=project_creation_request[0], record_commit=project_creation_request[1])
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed project creation source unavailable") from None
            elif project_archive_request is not None:
                from common.workspace_project_archive_contract import validate_sample
                try:
                    def unique_archive_object(pairs):
                        result = {}
                        for key, value in pairs:
                            if key in result: raise ValueError("SOURCE_UNAVAILABLE")
                            result[key] = value
                        return result
                    packet = validate_sample(json.loads(stdout, object_pairs_hook=unique_archive_object),
                        project_archive_request[0], pre_macro_sha)
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed archive source unavailable") from None
            elif project_direction_request is not None:
                from common.workspace_project_direction_contract import validate_body
                try:
                    def unique_direction_object(pairs):
                        result = {}
                        for key, item in pairs:
                            if key in result:
                                raise ValueError("SOURCE_UNAVAILABLE")
                            result[key] = item
                        return result
                    packet = validate_body(json.loads(stdout, object_pairs_hook=unique_direction_object))
                    if (packet["selection"] != {"work_ref": project_direction_request}
                            or packet["availability"] == "AVAILABLE" and packet["source"]["commit"] != pre_macro_sha):
                        raise ValueError("SOURCE_UNAVAILABLE")
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed Direction source unavailable") from None
            elif project_knowledge_request is not None:
                from common.workspace_project_knowledge_read_contract import validate_body, result_selection
                operation, selected = project_knowledge_request
                try:
                    def unique_knowledge_object(pairs):
                        result = {}
                        for key, item in pairs:
                            if key in result: raise ValueError("duplicate knowledge field")
                            result[key] = item
                        return result
                    packet = validate_body(json.loads(stdout, object_pairs_hook=unique_knowledge_object), operation=operation)
                    expected_selection = result_selection(selected)
                    if packet["selection"] != expected_selection:
                        raise ValueError("knowledge selection changed")
                    if packet.get("source") is not None and packet["source"]["commit"] != expected_packet_macro_sha:
                        raise ValueError("knowledge source changed")
                    if (operation == "project_knowledge_source" and packet["availability"] == "AVAILABLE"
                            and packet["source"]["revision"] != selected["expected_revision"]):
                        raise ValueError("knowledge revision changed")
                    if (operation == "project_discovery_source" and packet["availability"] == "AVAILABLE"
                            and packet["source"]["commit"] != selected["expected_source_commit"]):
                        raise ValueError("discovery DATA changed")
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed project knowledge source unavailable") from None
            elif project_instructions_request is not None:
                from common.workspace_project_instructions_contract import validate_body
                try:
                    def unique_instruction_object(pairs):
                        value = {}
                        for key, item in pairs:
                            if key in value:
                                raise ValueError("invalid instruction read")
                            value[key] = item
                        return value
                    packet = validate_body(json.loads(stdout, object_pairs_hook=unique_instruction_object),
                        {"work_ref": project_instructions_request})
                    if packet["availability"] == "AVAILABLE" and packet["source"]["commit"] != pre_macro_sha:
                        raise ValueError("instruction source changed")
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed project instructions source unavailable") from None
            elif project_journal_request is not None:
                from common.workspace_project_journal_contract import BODY_SCHEMA, validate_body
                try:
                    def unique_plan_object(pairs):
                        result = {}
                        for key, item in pairs:
                            if key in result:
                                raise ValueError("invalid project journal")
                            result[key] = item
                        return result
                    packet = validate_body(json.loads(stdout, object_pairs_hook=unique_plan_object))
                    if (type(packet) is not dict or packet.get("schema") != BODY_SCHEMA
                            or packet.get("selection") != {"work_ref": project_journal_request}):
                        raise ValueError("project journal response invalid")
                    if packet.get("availability") == "AVAILABLE":
                        source = packet["source"]
                        if source["commit"] != expected_packet_macro_sha:
                            raise ValueError("project journal source changed")
                    elif packet.get("availability") != "UNAVAILABLE":
                        raise ValueError("project journal availability invalid")
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed project journal source unavailable") from None
            elif project_discovery_request is not None:
                from common.project_discovery_contract import validate_record
                try:
                    def unique_discovery_object(pairs):
                        result = {}
                        for key, value in pairs:
                            if key in result: raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
                            result[key] = value
                        return result
                    packet = validate_record(json.loads(stdout, object_pairs_hook=unique_discovery_object),
                        work_ref=project_discovery_request[0], code_commit=pre_macro_sha,
                        data_commit=expected_packet_macro_sha)
                    if packet['observed_at_ms'] != project_discovery_request[1]:
                        raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError('backend_unavailable', 'installed project discovery unavailable') from None
            elif project_plan_request is not None:
                from common.workspace_project_plan_contract import BODY_SCHEMAS, validate_source, validate_body
                try:
                    def unique_plan_object(pairs):
                        result = {}
                        for key, item in pairs:
                            if key in result:
                                raise ValueError("invalid project plan")
                            result[key] = item
                        return result
                    packet = validate_body(json.loads(stdout, object_pairs_hook=unique_plan_object))
                    if (type(packet) is not dict or packet.get("schema") not in BODY_SCHEMAS
                            or packet.get("selection") != {"work_ref": project_plan_request}):
                        raise ValueError("project plan response invalid")
                    if packet.get("availability") == "AVAILABLE":
                        source = validate_source(packet.get("source"), project_plan_request)
                        if source["commit"] != expected_packet_macro_sha:
                            raise ValueError("project plan source changed")
                    elif packet.get("availability") != "UNAVAILABLE":
                        raise ValueError("project plan availability invalid")
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise GatewayError("backend_unavailable", "installed project plan source unavailable") from None
            elif acceptance_request is not None:
                from common.commission_ref import normalize_commission_ref
                from control_plane.agentos_product_acceptance_basis import (
                    AgentOsProductAcceptanceBasisReader, ProductAcceptanceBasisUnavailable,
                )

                def unique_object(pairs):
                    value = {}
                    for key, item in pairs:
                        if key in value:
                            raise ValueError("duplicate Context key")
                        value[key] = item
                    return value

                def nonfinite(_value):
                    raise ValueError("nonfinite Context value")

                try:
                    bundle = json.loads(stdout, object_pairs_hook=unique_object,
                                        parse_constant=nonfinite)
                    work_ref, execution_ref, root_objective = acceptance_request
                    packet = AgentOsProductAcceptanceBasisReader._select(
                        bundle, expected_sha=expected_packet_macro_sha, work_ref=work_ref,
                        execution_ref=execution_ref, root_objective=root_objective,
                    )
                    source = normalize_commission_ref(packet.entry["source_record_ref"])
                    try:
                        record = self._runner(
                            ["git", "-C", os.fspath(packet_macro_root), "show",
                             f"{source.commit}:{source.path}"],
                            cwd=packet_macro_root, timeout=remaining(),
                            max_bytes=output_limit, env=child_env,
                        )
                    except Exception:
                        raise GatewayError("backend_unavailable", "installed Context record unavailable") from None
                    if (not isinstance(record, Mapping) or record.get("code") != 0
                            or type(record.get("stdout")) is not str
                            or any(record.get(flag) is True for flag in
                                   ("timed_out", "limit_exceeded", "invalid_utf8"))):
                        raise GatewayError("backend_unavailable", "installed Context record unavailable")
                    if (hashlib.sha256(record["stdout"].encode("utf-8")).hexdigest()
                            != source.content_sha256):
                        raise ProductAcceptanceBasisUnavailable("CONTEXT_SOURCE_CHANGED")
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise ProductAcceptanceBasisUnavailable("BASIS_UNAVAILABLE") from None
            else:
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
                    observed_packet_macro_sha = macro_doc.get("sha") if isinstance(macro_doc, Mapping) else None
                except (KeyError, TypeError, OSError):
                    packet_repo = packet_macro = None
                    packet_source_sha = observed_packet_macro_sha = None
                if packet_repo != self._source_root or packet_macro != packet_macro_root:
                    raise GatewayError("backend_unavailable", "installed boot-packet roots differ")
                if packet_source_sha != pre_source_sha or observed_packet_macro_sha != expected_packet_macro_sha:
                    raise GatewayError("backend_unavailable", "installed boot-packet SHA binding differs")
            if materialized_observation is not None:
                try:
                    post_materialized = _snapshot_generation_observation(
                        packet_macro_root, runner=self._runner, env=child_env,
                        label="materialized Macro source", deadline=deadline,
                        _allow_synthetic_fixture=self._allow_synthetic_fixture,
                    )
                except GatewayError as exc:
                    raise GatewayError(
                        "backend_unavailable",
                        "installed materialized Macro changed during boot-packet read",
                    ) from exc
                if (
                    not isinstance(post_materialized, tuple)
                    or post_materialized != materialized_observation
                ):
                    raise GatewayError(
                        "backend_unavailable",
                        "installed materialized Macro changed during boot-packet read",
                    )

            try:
                post_source_sha, post_macro_sha, post_source_seal, post_macro_seal = (
                    self._generation_pair(
                        live_env, deadline=deadline, macro_plan=materialization_plan
                    )
                )
            except GatewayError as exc:
                source_drift_messages = {
                    "installed Mastermind source SHA changed",
                    "installed Mastermind source HEAD changed",
                    "installed Macro source SHA changed",
                    "installed Macro source HEAD changed",
                    "installed Macro source worktree path set differs",
                    "installed Macro source worktree bytes differ",
                }
                if (
                    exc.code == "backend_unavailable"
                    and exc.message in source_drift_messages
                ):
                    raise GatewayError(
                        "backend_unavailable",
                        "installed source changed during boot-packet read",
                    ) from exc
                raise
            if (
                post_source_sha != pre_source_sha
                or post_macro_sha != pre_macro_sha
                or post_source_seal != pre_source_seal
                or post_macro_seal != pre_macro_seal
            ):
                raise GatewayError("backend_unavailable", "installed source changed during boot-packet read")
            if acceptance_request is None and agentos_context_request is None and project_plan_request is None and project_journal_request is None and project_creation_request is None and project_direction_request is None and project_archive_request is None and project_knowledge_recipe_request is None and project_knowledge_request is None and project_instructions_request is None and project_discovery_request is None:
                packet = _project_macro_identity(
                    packet, materialized_root=packet_macro_root, canonical_root=self._macro_root,
                )
        if project_knowledge_request is not None:
            packet = dict(packet, code_context={"schema": "mastermind.project_knowledge_code_context.v1",
                "work_ref": project_knowledge_request[1]["work_ref"],
                "executable_macro_commit": pre_macro_sha, "reader_source_commit": pre_source_sha})
        if data_view is not None:
            data_view.check()
            if project_knowledge_request is not None:
                packet = dict(packet, data_observation=data_view.witness())
        remaining()
        return packet


class InstalledExecutiveReaders(ExecutiveMcpGateway):
    """Reuse all four projections with one explicit, host-owned Runtime root."""

    def __init__(
        self, *, repo_root: Path, macro_root: Path, runtime_root: Path,
        boot_python: Path | None = None, packet_runner: PacketRunner | None = None,
        code_root: Path | None = None, expected_source_sha: str | None = None,
        _allow_synthetic_fixture: bool = False,
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
        self._allow_synthetic_fixture = bool(_allow_synthetic_fixture)
        packet_builder = self._installed_packet
        if self._boot_python is not None:
            packet_builder = InstalledBootPacketCollector(
                source_root=self._source_root, macro_root=self._macro_root,
                code_root=self._code_root, python_executable=self._boot_python,
                runner=packet_runner, expected_source_sha=expected_source_sha,
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
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

    async def _run_read_attempt(self, name, arguments, generated_at):
        collector = self._packet_builder
        if isinstance(collector, InstalledBootPacketCollector) and name in {
            "executive_state", "executive_inbox",
        }:
            with collector.request_scope(now=self.config.now,
                                         timeout=self.config.boot_packet_timeout):
                return await super()._run_read_attempt(name, arguments, generated_at)
        return await super()._run_read_attempt(name, arguments, generated_at)

    def _read(self, name, arguments, generated_at):
        collector = self._packet_builder
        if isinstance(collector, InstalledBootPacketCollector):
            with collector.physical_scope():
                return super()._read(name, arguments, generated_at)
        return super()._read(name, arguments, generated_at)

    def _read_envelope(self, name, generated_at, data, grounding, degraded):
        """Use the actual remaining ingress budget, preserving its 32 KiB cap.

        Grounding, warnings, bounding receipts, the outer success frame and its
        newline all share that cap. The old half-budget rejected intact Inbox
        rows even when their complete wire response fit. Unboundable topology
        still refuses; no rows, identities or evidence are silently omitted.
        """
        envelope = result_envelope(
            name, mode=self.config.mode, generated_at=generated_at,
            data=None, grounding=grounding, degraded=degraded,
        )
        overhead = len(canonical_json({"ok": True, "result": envelope})) + 1
        # bound_document counts receipt growth beyond the existing empty list.
        available = executive_ceo_ingress.MAX_RESPONSE_BYTES - overhead + len(b"null")
        if available < 0:
            raise GatewayError("output_too_large", "read metadata exceeds the ingress byte limit")
        bound = bound_job_document if name == "executive_job" else bound_document
        envelope["data"], envelope["bounded"] = bound(data, limit=available)
        if len(canonical_json({"ok": True, "result": envelope})) + 1 > executive_ceo_ingress.MAX_RESPONSE_BYTES:
            raise GatewayError("output_too_large", "read response exceeds the ingress byte limit")
        return envelope

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
            with executive_ceo_ingress.grounding_observation_scope() as deadline:
                mastermind_sha = _clean_git_snapshot(
                    self._source_root, runner=self._read_runner, env=env,
                    label="Mastermind source", content_scope="all", deadline=deadline,
                    _allow_synthetic_fixture=self._allow_synthetic_fixture,
                )
                macro_sha = _clean_git_snapshot(
                    self._macro_root, runner=self._read_runner, env=env,
                    label="Macro source", content_scope="all", deadline=deadline,
                    _allow_synthetic_fixture=self._allow_synthetic_fixture,
                )
                executive_ceo_ingress._require_grounding_budget()
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
