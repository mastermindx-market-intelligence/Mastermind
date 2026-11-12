"""Bounded SSE framing shared by the incumbent router's three wire adapters."""
from __future__ import annotations

from .wire import WireTranslationError


class SSEDecoder:
    """Decode LF/CRLF and multiline data without treating keep-alives as content.

    The bound covers a whole unfinished event, including comments and unknown
    fields. No prompt/response content is retained beyond the current frame.
    """

    def __init__(self, max_event_bytes: int):
        self.limit = max_event_bytes
        self.buffer = b""
        self.event = ""
        self.data: list[bytes] = []
        self.size = 0

    def feed(self, chunk: bytes) -> list[tuple[str, str]]:
        self.buffer += chunk
        out = []
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            self.size += len(line) + 1
            if self.size > self.limit:
                raise WireTranslationError("FABRIC_STREAM_EVENT_TOO_LARGE")
            line = line.removesuffix(b"\r")
            if not line:
                if self.data:
                    try:
                        out.append((self.event, b"\n".join(self.data).decode("utf-8")))
                    except UnicodeDecodeError:
                        raise WireTranslationError("FABRIC_STREAM_INVALID_UTF8") from None
                self.event, self.data, self.size = "", [], 0
                continue
            field, separator, value = line.partition(b":")
            if value.startswith(b" "):
                value = value[1:]
            if field == b"data":
                self.data.append(value if separator else b"")
            elif field == b"event":
                try:
                    self.event = value.decode("utf-8")
                except UnicodeDecodeError:
                    raise WireTranslationError("FABRIC_STREAM_INVALID_UTF8") from None
        if self.size + len(self.buffer) > self.limit:
            raise WireTranslationError("FABRIC_STREAM_EVENT_TOO_LARGE")
        return out

    def finish(self) -> None:
        if self.buffer.strip() or self.data:
            raise WireTranslationError("FABRIC_STREAM_TRUNCATED")


async def events(response, *, max_event_bytes: int, max_response_bytes: int):
    decoder = SSEDecoder(max_event_bytes)
    received = 0
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > max_response_bytes:
            raise WireTranslationError("FABRIC_RESPONSE_TOO_LARGE")
        for event in decoder.feed(chunk):
            yield event
    decoder.finish()


async def read_bounded(response, limit: int) -> bytes:
    data = bytearray()
    async for chunk in response.aiter_bytes():
        if len(data) + len(chunk) > limit:
            raise WireTranslationError("FABRIC_RESPONSE_TOO_LARGE")
        data.extend(chunk)
    return bytes(data)
