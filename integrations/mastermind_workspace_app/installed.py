"""Fixed bounded workspace client of the existing App-peer CeoIngress socket.

This is transport composition only: no owner, enrollment, token acquisition,
Runtime path, cache lifecycle, retry, or installation state is created here.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .contract import (
    MAX_RESPONSE_BYTES,
    FRAME_SCHEMA_V3, MAX_PLAN_RESPONSE_BYTES, validate_v3_frame,
    MAX_RESULT_RESPONSE_BYTES,
    canonical,
    response_ceiling_for,
    validate_frame,
    validate_v2_frame,
)


class CeoIngressWorkspaceClient:
    def __init__(self, socket_path, *, timeout_seconds=10, acceptance_timeout_seconds=30):
        self.socket_path = Path(socket_path)
        if (not self.socket_path.is_absolute() or type(timeout_seconds) not in (int, float)
                or not 0.1 <= timeout_seconds <= 30
                or type(acceptance_timeout_seconds) not in (int, float)
                or not 0.1 <= acceptance_timeout_seconds <= 30):
            raise ValueError("invalid_input")
        self.timeout_seconds = timeout_seconds
        self.acceptance_timeout_seconds = acceptance_timeout_seconds

    async def request(self, frame):
        # Frozen v2 frames use the exact same wire envelope as v1; only the
        # schema name and selection grammar differ.  Operation-driven response
        # ceiling selection happens BEFORE the socket is opened so a misrouted
        # result frame can never widen into the larger Mission ceiling.
        from control_plane.coo_principal_host import FACT_SCHEMA, validate_facts_frame
        from common.product_acceptance_read_contract import FRAME_SCHEMA as ACCEPTANCE_FRAME_SCHEMA, validate_frame as validate_acceptance_frame
        timeout = self.timeout_seconds
        if isinstance(frame, dict) and frame.get("schema") == ACCEPTANCE_FRAME_SCHEMA:
            from common.product_acceptance_acquisition_contract import (
                OPERATION as ORIGINAL_OPERATION, validate_frame as validate_original_frame,
            )
            if frame.get("operation") == ORIGINAL_OPERATION:
                validate_original_frame(frame)
            else:
                validate_acceptance_frame(frame)
            ceiling = MAX_RESPONSE_BYTES
            # This read includes the sealed source owner's existing 15-second
            # observation, in addition to bounded Runtime proof reads. Keep it
            # inside the existing 30-second client ceiling without changing
            # any old operation or renewing the source owner's own deadline.
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == FACT_SCHEMA:
            validate_facts_frame(frame)
            ceiling = MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == "mastermind.executive_workspace_read.v5":
            from common import executive_workspace_activity_contract as activity
            activity.validate_frame(frame)
            ceiling = activity.MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == FRAME_SCHEMA_V3:
            validate_v3_frame(frame)
            ceiling = MAX_PLAN_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == "mastermind.executive_workspace_read.v2":
            validate_v2_frame(frame)
            ceiling = response_ceiling_for(frame.get("operation"))
        else:
            validate_frame(frame)
            ceiling = MAX_RESPONSE_BYTES
        encoded = canonical(frame) + b"\n"

        async def exchange():
            # The receive limit mirrors the operation's closed ceiling so an
            # oversized socket envelope never materializes in this client.
            reader, writer = await asyncio.open_unix_connection(str(self.socket_path), limit=ceiling)
            try:
                writer.write(encoded)
                await writer.drain()
                raw = await reader.readuntil(b"\n")
                if len(raw) > ceiling:
                    raise ValueError("source_unavailable")
                value = json.loads(raw)
                if type(value) is not dict:
                    raise ValueError("source_unavailable")
                if value.get("ok") is True:
                    if set(value) != {"ok", "result"} or type(value["result"]) is not dict:
                        raise ValueError("source_unavailable")
                elif (value.get("ok") is not False or set(value) != {"ok", "status", "error"}
                      or type(value["status"]) is not int or value["status"] not in (400, 403, 404, 503)
                      or type(value["error"]) is not dict or set(value["error"]) != {"code", "message"}):
                    raise ValueError("source_unavailable")
                return value
            finally:
                writer.close()
                await writer.wait_closed()
        try:
            return await asyncio.wait_for(exchange(), timeout)
        except Exception:
            raise ValueError("source_unavailable") from None


# Re-exported for tests and the App to import the operation-specific ceiling.
__all__ = ["CeoIngressWorkspaceClient", "MAX_RESULT_RESPONSE_BYTES"]
