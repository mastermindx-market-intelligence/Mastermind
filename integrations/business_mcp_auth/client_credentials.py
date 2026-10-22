"""One bounded Auth0 client-credentials request for an explicitly enrolled client.

This edge stores no credentials, provisions no account or grant, and has no
scheduler or browser operation. The returned token still requires independent
verification by the existing JwtAuthenticator before it can be published.
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit

import httpx

from .contracts import validate_resource_policy

MAX_RESPONSE_BYTES = 32 * 1024
TIMEOUT_SECONDS = 5.0
_TEXT = re.compile(r"[!-~]{1,4096}")


class ClientCredentialsError(RuntimeError):
    def __init__(self):
        super().__init__("CLIENT_CREDENTIALS_UNAVAILABLE")


def token_endpoint(policy):
    selected = validate_resource_policy(policy)
    issuer = urlsplit(selected.issuer)
    if issuer.path not in {"", "/"}:
        raise ClientCredentialsError()
    return selected.issuer.rstrip("/") + "/oauth/token"


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ClientCredentialsError()
            result[key] = value
        return result
    def invalid(_value):
        raise ClientCredentialsError()
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def validate_client_id(value):
    if type(value) is not str or not _TEXT.fullmatch(value) or len(value) > 1024:
        raise ClientCredentialsError()
    return value


async def acquire_client_credentials(*, policy, client_id, client_secret, transport_factory=None):
    """Acquire once, without redirects/retries, and return only the compact token."""
    endpoint = token_endpoint(policy)
    validate_client_id(client_id)
    if type(client_secret) is not str or not _TEXT.fullmatch(client_secret):
        raise ClientCredentialsError()
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            transport = (transport_factory() if transport_factory is not None
                         else httpx.AsyncHTTPTransport(retries=0, trust_env=False))
            async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                         timeout=TIMEOUT_SECONDS) as client:
                async with client.stream(
                        "POST", endpoint, headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                        json={"grant_type": "client_credentials", "client_id": client_id,
                              "client_secret": client_secret, "audience": policy.resource,
                              "scope": " ".join(policy.required_scopes)}) as response:
                    if (response.status_code != 200
                            or response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json"
                            or response.headers.get("content-encoding", "identity").lower() != "identity"):
                        raise ClientCredentialsError()
                    length = response.headers.get("content-length")
                    if length is not None and (not length.isdecimal() or int(length) > MAX_RESPONSE_BYTES):
                        raise ClientCredentialsError()
                    raw = bytearray()
                    async for chunk in response.aiter_raw():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise ClientCredentialsError()
                    value = _decode(raw)
                    if (type(value) is not dict
                            or not {"access_token", "token_type", "expires_in"} <= set(value)
                            or not set(value) <= {"access_token", "token_type", "expires_in", "scope"}
                            or value["token_type"] != "Bearer"
                            or type(value["expires_in"]) is not int or not 1 <= value["expires_in"] < 2**31
                            or type(value["access_token"]) is not str
                            or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value["access_token"])
                            or len(value["access_token"]) > 16 * 1024
                            or ("scope" in value and type(value["scope"]) is not str)):
                        raise ClientCredentialsError()
                    # expires_in is deliberately not used as the artifact expiry.
                    return value["access_token"]
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ClientCredentialsError() from None
