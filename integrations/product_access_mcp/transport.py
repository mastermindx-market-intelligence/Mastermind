"""Fixed public HTTP reads, without inherited credentials, cookies or retries."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from urllib.parse import urlencode

import httpx

from .contracts import ENDPOINTS, MAX_BODY_BYTES, HttpObservation, symbols_checked

REQUEST_TIMEOUT_SECONDS = 6.0


class PublicTransport:
    """Inert transport. Optional trusted transport injection supports offline qualification.

    The MCP caller never sees or controls this constructor. Production composition
    must use the default transport, not a fixture bridge. Each call owns and closes
    its client; Set-Cookie state cannot carry into another observation or user.
    """

    def __init__(self, *, transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None):
        if transport_factory is not None and not callable(transport_factory):
            raise TypeError("transport factory must be callable")
        self._transport_factory = transport_factory

    async def read(self, endpoint: str, *, symbols: tuple[str, ...] = ()) -> HttpObservation:
        if type(endpoint) is not str or endpoint not in ENDPOINTS:
            raise ValueError("invalid_endpoint")
        url = ENDPOINTS[endpoint]
        if endpoint == "market_pulse":
            url += "?" + urlencode({"symbols": ",".join(symbols_checked(symbols))})
        elif symbols:
            raise ValueError("unexpected_symbols")
        status = None
        try:
            transport = self._transport_factory() if self._transport_factory else httpx.AsyncHTTPTransport(retries=0, trust_env=False)
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                             timeout=REQUEST_TIMEOUT_SECONDS,
                                             headers={"Accept": "application/json", "Accept-Encoding": "identity"}) as client:
                    async with client.stream("GET", url) as response:
                        status = response.status_code
                        content_type = response.headers.get("Content-Type")
                        if 300 <= status < 400:
                            return HttpObservation(status=status, error="redirect_refused")
                        if status != 200:
                            return HttpObservation(status=status, content_type=content_type)
                        # Bound bytes before decoding; a compressed chunk can expand
                        # far beyond the cap before an aiter_bytes size check runs.
                        if response.headers.get("Content-Encoding", "identity").strip().lower() != "identity":
                            return HttpObservation(status=status, error="content_encoding_refused")
                        if not content_type or content_type.split(";")[0].strip().lower() != "application/json":
                            return HttpObservation(status=status, error="invalid_content_type")
                        length = response.headers.get("Content-Length")
                        if length is not None:
                            if not length.isascii() or not length.isdecimal():
                                return HttpObservation(status=status, error="invalid_content_length")
                            if int(length) > MAX_BODY_BYTES:
                                return HttpObservation(status=status, error="response_too_large")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_BODY_BYTES:
                                return HttpObservation(status=status, error="response_too_large")
                            body.extend(chunk)
                        return HttpObservation(status=status, body=bytes(body), content_type=content_type)
        except (TimeoutError, httpx.TimeoutException):
            return HttpObservation(status=status, error="timeout")
        except Exception:
            # Do not expose exception text, proxy settings, URLs or credential-bearing headers.
            return HttpObservation(status=status, error="backend_unavailable")
