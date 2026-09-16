"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping

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


def _installed_child_env(*, code_root: Path, macro_root: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
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


def _worktree_path_sets(root: Path) -> tuple[set[str], set[str]]:
    """Return raw leaf and directory paths, excluding only the top-level Git metadata."""
    leaves: set[str] = set()
    directories: set[str] = set()
    stack: list[tuple[Path, str]] = [(root, "")]
    while stack:
        directory, prefix = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if not prefix and entry.name == ".git":
                    continue
                rel = f"{prefix}/{entry.name}" if prefix else entry.name
                if entry.is_dir(follow_symlinks=False):
                    directories.add(rel)
                    stack.append((Path(entry.path), rel))
                else:
                    leaves.add(rel)
    return leaves, directories


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
    content_scope: str = "all",
) -> str:
    """Bind HEAD plus raw path existence, hashing only bytes the named reader consumes."""
    git_metadata = path / ".git"
    real_checkout = git_metadata.exists() or git_metadata.is_symlink()

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

    expected_leaves = set(expected)
    expected_directories = _tree_directory_paths(expected_leaves)
    try:
        actual_leaves, actual_directories = _worktree_path_sets(path)
    except OSError as exc:
        raise GatewayError(
            "backend_unavailable", f"installed {label} worktree observation failed"
        ) from exc
    if actual_leaves != expected_leaves or actual_directories != expected_directories:
        raise GatewayError("backend_unavailable", f"installed {label} worktree path set differs")

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
    return head


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

    def _snapshot_pair(self, env: Mapping[str, str]) -> tuple[str, str]:
        source_sha = _clean_git_snapshot(
            self._source_root, runner=self._runner, env=env, label="Mastermind source",
            content_scope="identity",
        )
        macro_sha = _clean_git_snapshot(
            self._macro_root, runner=self._runner, env=env, label="Macro source",
            content_scope="macro_brief",
        )
        if self._expected_source_sha is not None and source_sha != self._expected_source_sha:
            raise GatewayError("backend_unavailable", "installed Mastermind source SHA changed")
        return source_sha, macro_sha

    def __call__(self, *, repo_root: Path, macro_root_flag: str | None,
                 now: str | None, timeout: float, **_ignored: Any) -> dict[str, Any]:
        repo = Path(repo_root).resolve()
        macro = Path(macro_root_flag).resolve() if macro_root_flag else None
        if repo != self._source_root or macro != self._macro_root:
            raise GatewayError("backend_unavailable", "installed boot-packet roots changed")
        child_env = _installed_child_env(
            code_root=self._code_root, macro_root=self._macro_root,
        )
        pre_source_sha, pre_macro_sha = self._snapshot_pair(child_env)
        inner_timeout = _inner_packet_timeout(float(timeout))
        argv = [os.fspath(self._python), "-I", "-B",
                os.fspath(self._code_root / "scripts" / "ceo_boot_packet.py"),
                "--json", "--repo-root", os.fspath(repo),
                "--macro-root", os.fspath(macro), "--timeout", f"{inner_timeout:g}"]
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
        if packet_repo != self._source_root or packet_macro != self._macro_root:
            raise GatewayError("backend_unavailable", "installed boot-packet roots differ")
        if packet_source_sha != pre_source_sha or packet_macro_sha != pre_macro_sha:
            raise GatewayError("backend_unavailable", "installed boot-packet SHA binding differs")

        post_source_sha, post_macro_sha = self._snapshot_pair(child_env)
        if post_source_sha != pre_source_sha or post_macro_sha != pre_macro_sha:
            raise GatewayError("backend_unavailable", "installed source changed during boot-packet read")
        return packet


class InstalledExecutiveReaders(ExecutiveMcpGateway):
    """Reuse all four projections with one explicit, host-owned Runtime root."""

    def __init__(
        self, *, repo_root: Path, macro_root: Path, runtime_root: Path,
        packet_python: Path | None = None, packet_runner: PacketRunner | None = None,
        code_root: Path | None = None, expected_source_sha: str | None = None,
    ) -> None:
        if not all(Path(p).is_absolute() for p in (repo_root, macro_root, runtime_root)):
            raise ValueError("installed read roots must be absolute")
        if packet_python is not None and not Path(packet_python).is_absolute():
            raise ValueError("installed packet Python must be absolute")
        if packet_python is not None and code_root is None:
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
        self._read_runner = packet_runner or _default_packet_runner
        packet_builder = ceo_boot_packet.build_packet
        if packet_python is not None:
            packet_builder = InstalledBootPacketCollector(
                source_root=self._source_root, macro_root=self._macro_root,
                code_root=self._code_root, python_executable=Path(packet_python),
                runner=packet_runner, expected_source_sha=expected_source_sha,
            )
        elif packet_runner is not None:
            raise ValueError("packet_runner requires packet_python")
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
