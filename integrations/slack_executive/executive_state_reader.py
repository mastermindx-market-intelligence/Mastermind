"""Read the existing Executive CeoIngress diagnostic state frame for C1.

This integrations-layer reader has exactly one operation: send the accepted
no-input ``mastermind.executive_ceo_ingress_state.v1`` frame to the already
owned CeoIngress AF_UNIX listener and return one validated
``mastermind.executive_hot_state.v1`` result. It owns no Runtime, listener,
retry queue, discovery path, submit/status request, or business mutation
authority.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from common.executive_hot_state_contract import (
    STATE_REQUEST_SCHEMA,
    validate_hot_state_document,
)

_DEFAULT_TIMEOUT_SECONDS = 5.0
_MAX_RESPONSE_BYTES = 32768


class CeoIngressStateReader:
    """One-shot read-only client for the dedicated CeoIngress state frame."""

    def __init__(
        self,
        *,
        socket_path: str | Path,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(
            timeout_seconds, bool
        ):
            raise ValueError("timeout_seconds must be numeric")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._socket_path = path
        self._timeout_seconds = float(timeout_seconds)

    async def read_state(self) -> dict[str, Any]:
        writer: asyncio.StreamWriter | None = None
        raw: bytes
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(
                    str(self._socket_path),
                    limit=_MAX_RESPONSE_BYTES + 1,
                ),
                timeout=self._timeout_seconds,
            )
            request = json.dumps(
                {"schema": STATE_REQUEST_SCHEMA},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            writer.write(request)
            await asyncio.wait_for(writer.drain(), timeout=self._timeout_seconds)
            try:
                raw = await asyncio.wait_for(
                    reader.readuntil(b"\n"), timeout=self._timeout_seconds
                )
            except (asyncio.LimitOverrunError, asyncio.IncompleteReadError):
                raise RuntimeError("EXECUTIVE_STATE_INVALID_RESPONSE") from None
        except RuntimeError:
            raise
        except (OSError, asyncio.TimeoutError, ConnectionError):
            raise RuntimeError("EXECUTIVE_STATE_UNAVAILABLE") from None
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, ConnectionError):
                    pass

        if not raw or len(raw) > _MAX_RESPONSE_BYTES or not raw.endswith(b"\n"):
            raise RuntimeError("EXECUTIVE_STATE_INVALID_RESPONSE")
        try:
            response: Any = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("EXECUTIVE_STATE_INVALID_RESPONSE") from None
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise RuntimeError("EXECUTIVE_STATE_INVALID_RESPONSE")
        result = response.get("result")
        if not isinstance(result, dict) or not validate_hot_state_document(result):
            raise RuntimeError("EXECUTIVE_STATE_INVALID_RESPONSE")
        return result
