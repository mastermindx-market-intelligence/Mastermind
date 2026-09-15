"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

import json
import os
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
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": os.fspath(macro_root),
        # Macro Agent OS reads P0 state from the immutable installed release,
        # never from the control-owned administrative checkout.
        "MACRO_MASTERMIND_REPO": os.fspath(code_root),
    }


def _clean_git_snapshot(
    path: Path, *, runner: PacketRunner, env: Mapping[str, str], label: str,
) -> str:
    """Return exact HEAD only when the checkout has no hidden or visible dirt."""
    # Repository-local config and index hints belong to the owner-writable data root,
    # so neither may weaken the cleanliness observation. In particular a local
    # fsmonitor can execute during ``git status`` and assume-unchanged/skip-worktree
    # can make changed bytes disappear from ordinary porcelain output.
    git_metadata = path / ".git"
    real_checkout = git_metadata.exists() or git_metadata.is_symlink()
    git_prefix = ["git"]
    if real_checkout:
        git_prefix.extend([
            "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "-c", "core.hooksPath=/dev/null",
        ])

    def observe(args: list[str], *, max_bytes: int) -> str:
        try:
            result = runner(
                [*git_prefix, *args], cwd=path, timeout=10.0,
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

    # Hermetic unit tests may inject a synthetic Git runner over plain directories.
    # A real installed checkout always carries .git metadata, so production takes
    # this additional index-hint fence while fixture-only runners retain their
    # existing single-status contract.
    if real_checkout:
        index_view = observe(["ls-files", "-v", "-z"], max_bytes=4 * 1024 * 1024)
        for entry in index_view.split("\0"):
            if not entry:
                continue
            if len(entry) < 3 or entry[1] != " ":
                raise GatewayError(
                    "backend_unavailable", f"installed {label} index observation failed"
                )
            # Normal tracked entries are H. Lower-case tags are assume-unchanged;
            # S is skip-worktree. Other non-H states are likewise not a clean,
            # canonical installed data-root observation.
            if entry[0] != "H":
                raise GatewayError(
                    "backend_unavailable", f"installed {label} index hint is not clean"
                )

    stdout = observe(
        ["status", "--porcelain=v2", "--branch", "--untracked-files=all"],
        max_bytes=256 * 1024,
    )
    oid: str | None = None
    dirty = False
    for line in stdout.splitlines():
        if line.startswith("# branch.oid "):
            if oid is not None:
                raise GatewayError("backend_unavailable", f"installed {label} identity is ambiguous")
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
        )
        macro_sha = _clean_git_snapshot(
            self._macro_root, runner=self._runner, env=env, label="Macro source",
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
