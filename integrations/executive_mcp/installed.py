"""SDK-free installed read composition, owned by the Executive control process.

The network App receives only existing canonical projections over CeoIngress.
It never receives filesystem access to the Runtime database or worker leases.
Temporary E1/fixture configuration and their production-path fences are unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from control_plane import ceo_boot_packet, executive_ceo_ingress, executive_inbox
from control_plane.chairman_control_room_remote import default_runner as _bounded_runner
from integrations.executive_mcp.adapter import (
    ExecutiveMcpGateway, GatewayConfig, _open_readonly_runtime,
)
from integrations.executive_mcp.schemas import (
    GatewayError, MODIFYING_TOOL, READ_TIMEOUT_SECONDS, ServerMode, validate_tool_arguments,
)


# The installed App transport waits 65s, while the canonical MCP read executor owns
# a 30s budget.  Keep the whole boot-packet operation six seconds inside that
# executor deadline for envelope construction, scheduling and process-group reap.
_INSTALLED_PACKET_RESERVE_SECONDS = 6.0
_INSTALLED_PACKET_BUDGET_SECONDS = READ_TIMEOUT_SECONDS - _INSTALLED_PACKET_RESERVE_SECONDS
# Current canonical ceo_brief.v1 is ~435 KiB before the final MCP projection is
# bounded.  Keep process capture finite with >2x observed headroom; the returned
# envelope is still independently capped by ``self.config.max_response_bytes``.
_INSTALLED_PACKET_PROCESS_MAX_BYTES = 1024 * 1024
assert _INSTALLED_PACKET_BUDGET_SECONDS > 0


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
        # The imported module itself identifies the immutable installed release.
        # Never execute helper code from the mutable admin/grounding checkout.
        self._code_root = Path(__file__).resolve().parents[2]
        # Preserve the literal path: execution-time sealing must be able to detect a
        # symlink even after config-time validation.
        self._boot_python = Path(boot_python) if boot_python is not None else None
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
            raise GatewayError(
                "grounding_unavailable",
                "installed read source binding differs from the host-owned binding",
            )
        return ceo_boot_packet.build_packet_in_interpreter(
            boot_python=self._boot_python,
            code_root=self._code_root,
            repo_root=self._source_root,
            macro_root=self._macro_root,
            # One TOTAL packet deadline, derived from the canonical 30s read executor.
            # Pre/post grounding probes, the child and fallback all consume this same budget.
            timeout=min(
                float(kwargs.get("timeout", ceo_boot_packet.DEFAULT_TIMEOUT)),
                _INSTALLED_PACKET_BUDGET_SECONDS,
            ),
            now=kwargs.get("now"),
            max_output_bytes=_INSTALLED_PACKET_PROCESS_MAX_BYTES,
            runner=_bounded_runner,
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
