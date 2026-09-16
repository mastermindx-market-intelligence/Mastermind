"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

from pathlib import Path
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

    def _installed_packet(self, **kwargs: Any) -> dict[str, Any]:
        """Build the packet through the canonical sealed boot-packet reader."""
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
            boot_python=self._boot_python,
            repo_root=self._source_root,
            macro_root=self._macro_root,
            timeout=float(kwargs.get("timeout", ceo_boot_packet.DEFAULT_TIMEOUT)),
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
        result = {
            "mastermind_sha": ceo_boot_packet.git_sha(self._source_root),
            "macro_sha": ceo_boot_packet.git_sha(self._macro_root),
            "boot_packet_schema": executive_ceo_ingress.BOOT_PACKET_SCHEMA,
        }
        validated = executive_ceo_ingress._coerce_grounding_shape(result)
        if validated is None:
            raise ValueError("installed grounding is unavailable")
        return validated
