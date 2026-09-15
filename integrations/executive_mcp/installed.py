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
    GatewayError, MODIFYING_TOOL, ServerMode, validate_tool_arguments,
)


PacketRunner = Callable[..., Mapping[str, Any]]


_default_packet_runner = ceo_boot_packet.bounded_subprocess_runner


def _installed_child_env(*, source_root: Path, macro_root: Path) -> dict[str, str]:
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
        "MACRO_MASTERMIND_REPO": os.fspath(source_root),
    }


def _bounded_git_sha(path: Path, *, runner: PacketRunner, env: Mapping[str, str]) -> str | None:
    try:
        result = runner(
            ["git", "rev-parse", "HEAD"], cwd=path, timeout=10.0,
            max_bytes=64 * 1024, env=env,
        )
    except Exception:
        return None
    if not isinstance(result, Mapping):
        return None
    if any(result.get(flag) is True for flag in ("timed_out", "limit_exceeded", "invalid_utf8")):
        return None
    if result.get("code") != 0 or type(result.get("stdout")) is not str:
        return None
    value = result["stdout"].strip()
    return value or None


class InstalledBootPacketCollector:
    """Build one canonical boot packet in the dependency-complete read runtime."""

    def __init__(self, *, source_root: Path, macro_root: Path,
                 python_executable: Path, runner: PacketRunner | None = None) -> None:
        self._source_root = Path(source_root).resolve()
        self._macro_root = Path(macro_root).resolve()
        # Preserve the configured environment entrypoint. Resolving a venv-style
        # symlink to its base interpreter would silently drop that environment's
        # site-packages under -I and recreate the missing-dependency failure.
        self._python = Path(python_executable).absolute()
        self._runner = runner or _default_packet_runner
        if not all(
            path.is_absolute()
            for path in (self._source_root, self._macro_root, self._python)
        ):
            raise ValueError("installed boot-packet coordinates must be absolute")

    def __call__(self, *, repo_root: Path, macro_root_flag: str | None,
                 now: str | None, timeout: float, **_ignored: Any) -> dict[str, Any]:
        repo = Path(repo_root).resolve()
        macro = Path(macro_root_flag).resolve() if macro_root_flag else None
        if repo != self._source_root or macro != self._macro_root:
            raise GatewayError("backend_unavailable", "installed boot-packet roots changed")
        argv = [os.fspath(self._python), "-I", "-B",
                os.fspath(self._source_root / "scripts" / "ceo_boot_packet.py"),
                "--json", "--repo-root", os.fspath(repo),
                "--macro-root", os.fspath(macro), "--timeout", f"{timeout:g}"]
        if now is not None:
            argv.extend(["--now", now])
        child_env = _installed_child_env(
            source_root=self._source_root, macro_root=self._macro_root,
        )
        try:
            result = self._runner(
                argv, cwd=self._source_root, timeout=timeout,
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
        except (KeyError, TypeError, OSError):
            packet_repo = packet_macro = None
        if packet_repo != self._source_root or packet_macro != self._macro_root:
            raise GatewayError("backend_unavailable", "installed boot-packet roots differ")
        return packet


class InstalledExecutiveReaders(ExecutiveMcpGateway):
    """Reuse all four projections with one explicit, host-owned Runtime root."""

    def __init__(self, *, repo_root: Path, macro_root: Path, runtime_root: Path,
                 packet_python: Path | None = None, packet_runner: PacketRunner | None = None) -> None:
        if not all(Path(p).is_absolute() for p in (repo_root, macro_root, runtime_root)):
            raise ValueError("installed read roots must be absolute")
        if packet_python is not None and not Path(packet_python).is_absolute():
            raise ValueError("installed packet Python must be absolute")
        self._installed_runtime_root = Path(runtime_root).resolve()
        self._source_root = Path(repo_root).resolve()
        self._macro_root = Path(macro_root).resolve()
        self._read_runner = packet_runner or _default_packet_runner
        packet_builder = ceo_boot_packet.build_packet
        if packet_python is not None:
            packet_builder = InstalledBootPacketCollector(
                source_root=self._source_root, macro_root=self._macro_root,
                python_executable=Path(packet_python), runner=packet_runner,
            )
        elif packet_runner is not None:
            raise ValueError("packet_runner requires packet_python")
        super().__init__(
            GatewayConfig(
                mode=ServerMode.READONLY, repo_root=self._source_root,
                macro_root_flag=str(self._macro_root),
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
            source_root=self._source_root, macro_root=self._macro_root,
        )
        result = {
            "mastermind_sha": _bounded_git_sha(
                self._source_root, runner=self._read_runner, env=env,
            ),
            "macro_sha": _bounded_git_sha(
                self._macro_root, runner=self._read_runner, env=env,
            ),
            "boot_packet_schema": executive_ceo_ingress.BOOT_PACKET_SCHEMA,
        }
        validated = executive_ceo_ingress._coerce_grounding_shape(result)
        if validated is None:
            raise ValueError("installed grounding is unavailable")
        return validated
