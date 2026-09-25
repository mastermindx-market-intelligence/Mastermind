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
    MAX_RESULT_RESPONSE_BYTES,
    canonical,
    response_ceiling_for,
    validate_frame,
    validate_v2_frame,
)


class CeoIngressWorkspaceClient:
    def __init__(self, socket_path, *, timeout_seconds=10):
        self.socket_path = Path(socket_path)
        if (not self.socket_path.is_absolute() or type(timeout_seconds) not in (int, float)
                or not 0.1 <= timeout_seconds <= 30):
            raise ValueError("invalid_input")
        self.timeout_seconds = timeout_seconds

    async def request(self, frame):
        # Frozen v2 frames use the exact same wire envelope as v1; only the
        # schema name and selection grammar differ.  Operation-driven response
        # ceiling selection happens BEFORE the socket is opened so a misrouted
        # result frame can never widen into the larger Mission ceiling.
        if isinstance(frame, dict) and frame.get("schema") == "mastermind.executive_workspace_read.v2":
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
            return await asyncio.wait_for(exchange(), self.timeout_seconds)
        except Exception:
            raise ValueError("source_unavailable") from None


# Re-exported for tests and the App to import the operation-specific ceiling.
__all__ = ["CeoIngressWorkspaceClient", "MAX_RESULT_RESPONSE_BYTES"]
