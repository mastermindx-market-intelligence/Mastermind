"""Fixed bounded workspace client of the existing App-peer CeoIngress socket.

This is transport composition only: no owner, enrollment, token acquisition,
Runtime path, cache lifecycle, retry, or installation state is created here.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .contract import MAX_RESPONSE_BYTES, canonical, validate_frame


class CeoIngressWorkspaceClient:
    def __init__(self, socket_path, *, timeout_seconds=10):
        self.socket_path = Path(socket_path)
        if (not self.socket_path.is_absolute() or type(timeout_seconds) not in (int, float)
                or not 0.1 <= timeout_seconds <= 30):
            raise ValueError("invalid_input")
        self.timeout_seconds = timeout_seconds

    async def request(self, frame):
        validate_frame(frame)
        encoded = canonical(frame) + b"\n"

        async def exchange():
            reader, writer = await asyncio.open_unix_connection(str(self.socket_path), limit=MAX_RESPONSE_BYTES)
            try:
                writer.write(encoded)
                await writer.drain()
                raw = await reader.readuntil(b"\n")
                if len(raw) > MAX_RESPONSE_BYTES:
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
