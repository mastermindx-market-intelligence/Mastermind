"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from control_plane import ceo_boot_packet, executive_ceo_ingress, executive_inbox
from integrations.executive_mcp.adapter import (
    ExecutiveMcpGateway, GatewayConfig, _open_readonly_runtime,
)
from integrations.executive_mcp.schemas import (
    GatewayError, MODIFYING_TOOL, ServerMode, validate_tool_arguments,
)


class InstalledExecutiveReaders(ExecutiveMcpGateway):
    """Reuse all four projections with one explicit, host-owned Runtime root."""

    def __init__(
        self, *, repo_root: Path, macro_root: Path, runtime_root: Path,
        boot_python: Path | None = None,
    ) -> None:
        if not all(Path(p).is_absolute() for p in (repo_root, macro_root, runtime_root)):
            raise ValueError("installed read roots must be absolute")
        if boot_python is not None and not Path(boot_python).is_absolute():
            raise ValueError("installed boot interpreter must be absolute")
        self._installed_runtime_root = Path(runtime_root).resolve()
        self._source_root = Path(repo_root).resolve()
        self._macro_root = Path(macro_root).resolve()
        self._boot_python = Path(boot_python).resolve() if boot_python is not None else None
        super().__init__(
            GatewayConfig(
                mode=ServerMode.READONLY, repo_root=self._source_root,
                macro_root_flag=str(self._macro_root),
                max_response_bytes=executive_ceo_ingress.MAX_RESPONSE_BYTES // 2,
            ),
            packet_builder=self._installed_packet,
            inbox_builder=self._canonical_inbox,
            runtime_factory=lambda _root: _open_readonly_runtime(self._installed_runtime_root),
        )

    def _fallback_packet(self, *, reason: str, **kwargs: Any) -> dict[str, Any]:
        packet = ceo_boot_packet.build_packet(**kwargs)
        degraded = [f"installed boot helper unavailable: {reason}"]
        degraded.extend(str(item) for item in (packet.get("degraded") or []))
        packet["degraded"] = degraded
        return packet

    def _installed_packet(self, **kwargs: Any) -> dict[str, Any]:
        """Build the packet in the sealed YAML-capable read interpreter."""
        if self._boot_python is None:
            return self._fallback_packet(reason="interpreter_not_configured", **kwargs)
        requested_repo = Path(kwargs.get("repo_root", self._source_root)).resolve()
        requested_macro = Path(kwargs.get("macro_root_flag", self._macro_root)).resolve()
        if requested_repo != self._source_root or requested_macro != self._macro_root:
            return self._fallback_packet(reason="source_binding_mismatch", **kwargs)
        timeout = float(kwargs.get("timeout", ceo_boot_packet.DEFAULT_TIMEOUT))
        argv = [
            os.fspath(self._boot_python), "-I", "-B",
            os.fspath(self._source_root / "scripts" / "ceo_boot_packet.py"),
            "--json", "--macro-root", os.fspath(self._macro_root),
            "--timeout", str(timeout),
        ]
        now = kwargs.get("now")
        if now is not None:
            argv.extend(["--now", str(now)])
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": os.fspath(self._source_root),
            "GIT_CONFIG_KEY_1": "safe.directory",
            "GIT_CONFIG_VALUE_1": os.fspath(self._macro_root),
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "MACRO_MASTERMIND_REPO": os.fspath(self._source_root),
        }
        try:
            process = subprocess.run(
                argv, cwd=os.fspath(self._source_root), env=env,
                capture_output=True, text=True, check=False,
                timeout=timeout + 10.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return self._fallback_packet(reason="process_unavailable", **kwargs)
        if process.returncode != 0:
            return self._fallback_packet(reason="process_failed", **kwargs)
        try:
            packet = json.loads(process.stdout)
        except (TypeError, ValueError):
            return self._fallback_packet(reason="invalid_json", **kwargs)
        if not isinstance(packet, dict) or packet.get("schema") != ceo_boot_packet.SCHEMA:
            return self._fallback_packet(reason="schema_mismatch", **kwargs)
        expected_mastermind = ceo_boot_packet.git_sha(self._source_root)
        expected_macro = ceo_boot_packet.git_sha(self._macro_root)
        if (
            not expected_mastermind or not expected_macro
            or (packet.get("mastermind") or {}).get("sha") != expected_mastermind
            or (packet.get("macro") or {}).get("sha") != expected_macro
        ):
            return self._fallback_packet(reason="grounding_mismatch", **kwargs)
        return packet

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
        result = {
            "mastermind_sha": ceo_boot_packet.git_sha(self._source_root),
            "macro_sha": ceo_boot_packet.git_sha(self._macro_root),
            "boot_packet_schema": executive_ceo_ingress.BOOT_PACKET_SCHEMA,
        }
        validated = executive_ceo_ingress._coerce_grounding_shape(result)
        if validated is None:
            raise ValueError("installed grounding is unavailable")
        return validated
