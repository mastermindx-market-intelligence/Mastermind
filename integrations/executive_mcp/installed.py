"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

import concurrent.futures
import configparser
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
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
    GatewayError, MODIFYING_TOOL, READ_TIMEOUT_SECONDS, ServerMode,
    validate_tool_arguments,
)


PacketRunner = Callable[..., Mapping[str, Any]]


_default_packet_runner = ceo_boot_packet.bounded_subprocess_runner
_PACKET_SETTLEMENT_MARGIN_SECONDS = 0.75
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




@dataclass(frozen=True)
class _VerifiedRepositorySnapshot:
    """One complete repository proof reusable inside a single packet build."""

    root: Path
    head: str
    expected: Mapping[str, tuple[str, str]]
    worktree_seal: str
    generation_seal: str
    sealed_to_caller: bool = False


@dataclass(frozen=True)
class _MacroMaterializationPlan:
    """Exact sparse worktree required by ``agentos.py brief --json --no-remember``."""

    head: str
    files: frozenset[str]
    directories: frozenset[str]
    file_objects: Mapping[str, tuple[str, str]]


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
    object_input = ("\n".join(sorted(expected_types)) + "\n").encode("ascii")
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
            len(parts) != 2
            or not _valid_sha(parts[0])
            or parts[1] not in {"blob", "commit", "tree", "tag"}
            or parts[0] in observed_objects
        ):
            raise GatewayError(
                "backend_unavailable", f"installed {label} repository objects are incomplete"
            )
        observed_objects[parts[0]] = parts[1]
    if set(observed_objects) != set(expected_types) or any(
        observed_objects.get(object_id) != expected_type
        for object_id, expected_type in expected_types.items()
    ):
        raise GatewayError(
            "backend_unavailable", f"installed {label} repository objects are incomplete"
        )


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
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
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
    body = lines[1:end]
    targets = {"repos", "artifacts", "owns_paths"}
    out = {field: [] for field in targets}
    seen: set[str] = set()
    index = 0
    while index < len(body):
        line = body[index]
        if not line or line.lstrip().startswith("#") or line[0].isspace() or ":" not in line:
            index += 1
            continue
        key, raw_value = line.split(":", 1)
        key = _frontmatter_scalar(key)
        if key not in targets:
            index += 1
            continue
        if key in seen:
            raise ValueError(f"duplicate {key} field")
        seen.add(key)
        value = raw_value.strip()
        if value.startswith("#"):
            value = ""
        if value:
            if value == "[]":
                index += 1
                continue
            if key != "repos" or not (value.startswith("[") and value.endswith("]")):
                raise ValueError(f"unsupported inline {key} field")
            inner = value[1:-1].strip()
            out[key] = [] if not inner else [
                _frontmatter_scalar(item) for item in inner.split(",")
            ]
            index += 1
            continue
        items: list[str] = []
        cursor = index + 1
        item_indent: int | None = None
        while cursor < len(body):
            candidate = body[cursor]
            if not candidate.strip() or candidate.lstrip().startswith("#"):
                cursor += 1
                continue
            # YAML permits an indentless sequence directly below a mapping key.
            if not candidate[0].isspace() and not candidate.startswith("- "):
                break
            stripped = candidate.lstrip(" ")
            indent = len(candidate) - len(stripped)
            if not stripped.startswith("- ") or (item_indent is not None and indent != item_indent):
                raise ValueError(f"unsupported nested {key} field")
            item_indent = indent
            items.append(_frontmatter_scalar(stripped[2:]))
            cursor += 1
        out[key] = items
        index = cursor
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


def _build_macro_materialization_plan(
    source: Path, *, runner: PacketRunner, env: Mapping[str, str],
    deadline: float | None,
    verified_snapshot: _VerifiedRepositorySnapshot | None = None,
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
        tracked_paths = set(expected)
        files = _macro_brief_content_paths(tracked_paths)
        tree_directories = _tree_directory_paths(tracked_paths)
        probe_directories: set[str] = set()
        for rel in sorted(
            path for path in files if path.startswith("agentos/workstreams/")
        ):
            mode, expected_oid = expected[rel]
            if mode == "120000":
                raise ValueError("workstream record is a symlink")
            payload = (source / rel).read_bytes()
            if _git_blob_oid(payload) != expected_oid:
                raise ValueError("workstream bytes differ from HEAD")
            parsed = _frontmatter_lists(payload)
            repos = parsed["repos"]
            for field in ("artifacts", "owns_paths"):
                for entry in parsed[field]:
                    stem = _static_macro_probe(entry, repos)
                    if stem is None:
                        continue
                    if stem in expected:
                        if expected[stem][0] == "120000":
                            raise ValueError("path-existence probe is a symlink")
                        files.add(stem)
                    elif stem in tree_directories:
                        probe_directories.add(stem)
        if any(expected[rel][0] == "120000" for rel in files):
            raise ValueError("materialized read closure contains a symlink")
        directories = _tree_directory_paths(files) | _directory_closure(probe_directories)
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

    ancestry_commits: set[str] = set()
    if verify_repository_closure:
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
            path, {object_id: "commit" for object_id in ancestry_commits},
            runner=runner, env=env, deadline=deadline, label=label,
        )
        _require_git_object_types(
            path, {object_oid: "blob" for _rel, (_mode, object_oid) in expected.items()},
            runner=runner, env=env, deadline=deadline, label=label,
        )
        if content_scope == "macro_brief":
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

    def _worktree_inventory() -> tuple[dict[str, str], set[str], str]:
        try:
            return _worktree_path_sets(path, deadline=deadline, label=label)
        except (OSError, TimeoutError) as exc:
            raise GatewayError(
                "backend_unavailable", f"installed {label} worktree observation failed"
            ) from exc

    # The exact HEAD/tree and both complete inventories are decoded above, so the
    # object closure and the raw path/metadata enumeration are independent and
    # overlap for the rest of this one invocation.  Path-set comparison, content
    # verification, seal capture and materialization all wait for both.
    _object_proof, (actual_types, actual_directories, metadata_seal) = (
        _overlap_full_proofs(
            object_closure=_object_closure if verify_repository_closure else None,
            worktree_inventory=_worktree_inventory,
        )
    )

    all_tree_directories = _tree_directory_paths(set(expected))
    if admitted_worktree_files is None and admitted_worktree_directories is None:
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

    def _generation_pair(
        self, env: Mapping[str, str], *, deadline: float | None,
    ) -> tuple[str, str, str, str]:
        source_observation, macro_observation = self._repository_observation_pair(
            lambda: _snapshot_generation_observation(
                self._source_root, runner=self._runner, env=env,
                label="Mastermind source", deadline=deadline,
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
            ),
            lambda: _snapshot_generation_observation(
                self._macro_root, runner=self._runner, env=env,
                label="Macro source", deadline=deadline,
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
            ),
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
        deadline = time.monotonic() + total_timeout

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
        pre_source_sha, pre_macro_sha, pre_source_seal, pre_macro_seal = (
            self._snapshot_pair(
                live_env, deadline=deadline,
                snapshot_capture=(
                    None if self._allow_synthetic_fixture else macro_snapshots
                ),
            )
        )
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
            )
            if materialization_plan.head != pre_macro_sha:
                raise GatewayError(
                    "backend_unavailable", "installed Macro materialization SHA differs"
                )
        with _materialized_macro_root(
            self._macro_root, timeout=remaining(), plan=materialization_plan,
            _allow_synthetic_fixture=self._allow_synthetic_fixture,
        ) as packet_macro_root:
            child_env = _installed_child_env(
                code_root=self._code_root, macro_root=packet_macro_root,
            )
            materialized_observation: tuple[str, str] | None = None
            if packet_macro_root != self._macro_root:
                if materialization_plan is None:
                    raise GatewayError(
                        "backend_unavailable",
                        "installed Macro materialization plan is unavailable",
                    )
                materialized_observation = _verify_materialized_macro_root(
                    packet_macro_root, plan=materialization_plan,
                    runner=self._runner, env=child_env, deadline=deadline,
                )
                if materialized_observation[0] != pre_macro_sha:
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
            try:
                result = self._runner(
                    argv, cwd=self._code_root, timeout=remaining(),
                    max_bytes=ceo_boot_packet.DEFAULT_MAX_OUTPUT_BYTES, env=child_env,
                )
            except Exception as exc:
                raise GatewayError("backend_unavailable", "installed boot-packet collector failed") from exc
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
                self._generation_pair(live_env, deadline=deadline)
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
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
            )
            macro_sha = _clean_git_snapshot(
                self._macro_root, runner=self._read_runner, env=env,
                label="Macro source",
                _allow_synthetic_fixture=self._allow_synthetic_fixture,
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
