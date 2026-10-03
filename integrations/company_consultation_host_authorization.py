"""Request-local Company caller authority from the connected MCP child.

No model-supplied identity is accepted. Runtime remains the capability/current
writer owner and Darwin remains the connection/process identity owner. This
object is valid only while its one accepted request remains open; it does not
issue a reusable credential or remember a route or effect.
"""
from __future__ import annotations

from control_plane.codex_worker import ProcessInspector
from control_plane.company_consultation_peer_identity import (
    immediate_parent_pid,
    require_current_writer_parent,
)
from control_plane.executive_peer_identity import PeerIdentity, _current_capture
from control_plane.executive_runtime import ActiveMcpCapabilityBindingFacts, Runtime, StateConflict
from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_SERVER_IDENTITY,
    COMPANY_CONSULTATION_SERVER_VERSION,
    COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
)

COMPANY_MCP_CONFIG_NAME = "company-consultation-v1"


class CompanyCallerAuthority:
    """Recheck the exact admitted writer and grant before every host edge.

    The host must close this request-local object in its handler finally block.
    Both packet binding resolution and the before-COMMIT callback use
    ``revalidate``; a successful initial check is never a cached permission.
    """

    def __init__(
        self, *, runtime: Runtime, peer: PeerIdentity, worker_uid: int,
        inspector: ProcessInspector | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("Company authority requires the canonical Runtime")
        if type(worker_uid) is not int or worker_uid <= 0:
            raise ValueError("Company authority requires the installed worker UID")
        self._runtime = runtime
        self._peer = peer
        self._worker_uid = worker_uid
        self._inspector = inspector if inspector is not None else ProcessInspector()
        self._closed = False
        self._expected = self._observe()

    def _project(self, parent_pid: int) -> ActiveMcpCapabilityBindingFacts:
        return self._runtime.current_harness_mcp_binding_for_parent_pid(
            parent_pid,
            config_name=COMPANY_MCP_CONFIG_NAME,
            server_identity=COMPANY_CONSULTATION_SERVER_IDENTITY,
            server_version=COMPANY_CONSULTATION_SERVER_VERSION,
            tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
            # Stdio uses the authenticated local channel, not MCP OAuth.
            auth_status="unsupported",
        )

    def _observe(self) -> ActiveMcpCapabilityBindingFacts:
        if self._closed:
            raise StateConflict("Company request is closed")
        # Capture provenance is checked before trusting even the numeric UID.
        _current_capture(self._peer)
        if self._peer.euid != self._worker_uid:
            raise StateConflict("Company caller is not the installed worker")
        parent_pid = immediate_parent_pid(self._peer, inspector=self._inspector)
        current = self._project(parent_pid)
        if type(current) is not ActiveMcpCapabilityBindingFacts:
            raise StateConflict("Company capability projection is unavailable")
        writer = current.binding
        require_current_writer_parent(
            self._peer, writer_pid=writer.pid, writer_pgid=writer.pgid,
            writer_start_identity=writer.process_start_identity,
            writer_boot_id=writer.boot_id,
            writer_unique_id=writer.admitted_unique_id,
            writer_pidversion=writer.admitted_pidversion,
            inspector=self._inspector,
        )
        # Runtime can rotate while the kernel is observed. Never join facts
        # from opposite sides of that rotation into an apparently valid caller.
        if self._project(parent_pid) != current:
            raise StateConflict("Company current writer or capability changed")
        _current_capture(self._peer)
        return current

    def revalidate(self) -> ActiveMcpCapabilityBindingFacts:
        current = self._observe()
        if current != self._expected:
            raise StateConflict("Company request authority changed")
        return current

    def close(self) -> None:
        self._closed = True
