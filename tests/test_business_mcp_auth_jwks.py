from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import (
    JWKS_TIMEOUT_SECONDS,
    MAX_JWKS_BYTES,
    BoundedJwksCache,
    HttpxJwksFetcher,
)


def _policy():
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-steward-v1",
            "resource": "https://mcp.example.test/mcp/steward/v1",
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                "oauth-protected-resource/mcp/steward/v1"
            ),
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": ["mastermind.steward.read"],
            "allowed_subject_digests": [
                subject_digest(issuer=issuer, subject="chairman-opaque")
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _key(kid: str = "kid-a", **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "kid": kid,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": "AQAB",
        "e": "AQAB",
    }
    value.update(overrides)
    return value


def _jwks(*keys: Mapping[str, object]) -> bytes:
    return json.dumps({"keys": list(keys)}, separators=(",", ":")).encode()


def _run(coroutine):
    return asyncio.run(coroutine)


class _Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _Fetcher:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        self.calls.append(
            {
                "url": url,
                "timeout_seconds": timeout_seconds,
                "max_bytes": max_bytes,
            }
        )
        await asyncio.sleep(0)
        if not self.responses:
            raise RuntimeError("unexpected fetch")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_empty_cache_fetches_once_and_fresh_match_reuses_cache() -> None:
    clock = _Clock()
    fetcher = _Fetcher(_jwks(_key()))
    cache = BoundedJwksCache(
        policy=_policy(),
        fetcher=fetcher,
        monotonic=clock.monotonic,
    )

    first = _run(cache.key_for("kid-a"))
    second = _run(cache.key_for("kid-a"))

    assert dict(first) == _key()
    assert dict(second) == _key()
    assert fetcher.calls == [
        {
            "url": _policy().jwks_uri,
            "timeout_seconds": JWKS_TIMEOUT_SECONDS,
            "max_bytes": MAX_JWKS_BYTES,
        }
    ]


def test_concurrent_first_requests_share_one_inflight_fetch() -> None:
    clock = _Clock()
    fetcher = _Fetcher(_jwks(_key()))
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=clock.monotonic
    )

    async def scenario():
        return await asyncio.gather(
            cache.key_for("kid-a"),
            cache.key_for("kid-a"),
            cache.key_for("kid-a"),
        )

    results = _run(scenario())
    assert [dict(item) for item in results] == [_key(), _key(), _key()]
    assert len(fetcher.calls) == 1


def test_expired_cache_refreshes_atomically_to_new_generation() -> None:
    clock = _Clock()
    fetcher = _Fetcher(_jwks(_key("kid-a")), _jwks(_key("kid-b")))
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=clock.monotonic
    )

    assert dict(_run(cache.key_for("kid-a"))) == _key("kid-a")
    clock.advance(61)
    assert dict(_run(cache.key_for("kid-b"))) == _key("kid-b")
    with pytest.raises(AuthError) as caught:
        _run(cache.key_for("kid-a"))
    assert caught.value.code is AuthErrorCode.KEY_NOT_FOUND
    assert len(fetcher.calls) == 2


def test_random_unknown_kids_trigger_one_refresh_per_cooldown() -> None:
    clock = _Clock()
    fetcher = _Fetcher(
        _jwks(_key("kid-a")),
        _jwks(_key("kid-a")),
        _jwks(_key("kid-a")),
    )
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=clock.monotonic
    )
    assert dict(_run(cache.key_for("kid-a"))) == _key("kid-a")

    with pytest.raises(AuthError) as first:
        _run(cache.key_for("unknown-1"))
    assert first.value.code is AuthErrorCode.KEY_NOT_FOUND

    for index in range(2, 100):
        with pytest.raises(AuthError) as caught:
            _run(cache.key_for(f"unknown-{index}"))
        assert caught.value.code is AuthErrorCode.KEY_NOT_FOUND
    assert len(fetcher.calls) == 2

    clock.advance(30)
    with pytest.raises(AuthError) as after_cooldown:
        _run(cache.key_for("unknown-100"))
    assert after_cooldown.value.code is AuthErrorCode.KEY_NOT_FOUND
    assert len(fetcher.calls) == 3


def test_jwks_outage_uses_bounded_retry_backoff() -> None:
    clock = _Clock()
    fetcher = _Fetcher(RuntimeError("secret upstream detail"), RuntimeError("again"))
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=clock.monotonic
    )

    with pytest.raises(AuthError) as first:
        _run(cache.key_for("kid-a"))
    with pytest.raises(AuthError) as second:
        _run(cache.key_for("kid-a"))
    assert first.value.code is AuthErrorCode.JWKS_UNAVAILABLE
    assert second.value.code is AuthErrorCode.JWKS_UNAVAILABLE
    assert "secret" not in str(first.value)
    assert len(fetcher.calls) == 1

    clock.advance(5)
    with pytest.raises(AuthError) as third:
        _run(cache.key_for("kid-a"))
    assert third.value.code is AuthErrorCode.JWKS_UNAVAILABLE
    assert len(fetcher.calls) == 2


def test_failed_refresh_never_extends_stale_key_trust() -> None:
    clock = _Clock()
    fetcher = _Fetcher(_jwks(_key()), RuntimeError("outage"))
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=clock.monotonic
    )
    assert dict(_run(cache.key_for("kid-a"))) == _key()
    clock.advance(61)

    with pytest.raises(AuthError) as caught:
        _run(cache.key_for("kid-a"))

    assert caught.value.code is AuthErrorCode.JWKS_UNAVAILABLE
    assert len(fetcher.calls) == 2


def test_returned_key_is_a_copy_and_cannot_corrupt_cache() -> None:
    clock = _Clock()
    fetcher = _Fetcher(_jwks(_key()))
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=clock.monotonic
    )

    first = _run(cache.key_for("kid-a"))
    first["n"] = "attacker-change"
    second = _run(cache.key_for("kid-a"))

    assert second["n"] == "AQAB"
    assert len(fetcher.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"[]",
        b"{}",
        b'{"keys":"bad"}',
        b'{"keys":[],"extra":true}',
        _jwks(*[_key(f"kid-{index}") for index in range(17)]),
        _jwks(_key("same"), _key("same")),
        _jwks(_key(kty="EC")),
        _jwks(_key(use="enc")),
        _jwks(_key(alg="HS256")),
        _jwks({"kid": "kid-a", "kty": "RSA", "e": "AQAB"}),
        _jwks({"kid": "kid-a", "kty": "RSA", "n": "AQAB"}),
        _jwks(_key(n="AQAB=")),
        _jwks(_key(e="AQ AB")),
        _jwks(_key(jku="https://attacker.test/jwks")),
        _jwks(_key(x5u="https://attacker.test/cert")),
        _jwks(_key(d="private")),
        _jwks(_key(p="private")),
        _jwks(_key(q="private")),
        _jwks(_key(dp="private")),
        _jwks(_key(dq="private")),
        _jwks(_key(qi="private")),
        _jwks(_key(k="symmetric")),
        _jwks(_key(jwk={"kty": "RSA"})),
        _jwks(_key(unexpected="value")),
    ],
)
def test_malformed_or_unsafe_jwks_is_refused(payload: bytes) -> None:
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=_Fetcher(payload), monotonic=_Clock().monotonic
    )

    with pytest.raises(AuthError) as caught:
        _run(cache.key_for("kid-a"))

    assert caught.value.code is AuthErrorCode.JWKS_REFUSED
    assert caught.value.public_message == "authentication refused"
    assert "attacker.test" not in str(caught.value)


def test_common_certificate_extras_are_preserved_but_not_used_for_selection() -> None:
    key = _key()
    key.pop("use")
    key.pop("alg")
    key.update(
        {
            "x5c": ["certificate-a", "certificate-b"],
            "x5t": "thumbprint-a",
            "x5t#S256": "thumbprint-b",
        }
    )
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=_Fetcher(_jwks(key)), monotonic=_Clock().monotonic
    )

    result = _run(cache.key_for("kid-a"))

    assert dict(result) == key


def test_invalid_kid_refuses_before_fetch() -> None:
    fetcher = _Fetcher(_jwks(_key()))
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=_Clock().monotonic
    )
    with pytest.raises(AuthError) as caught:
        _run(cache.key_for("bad/kid"))
    assert caught.value.code is AuthErrorCode.KEY_NOT_FOUND
    assert fetcher.calls == []


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content_type: str | None = "application/json",
        chunks: tuple[bytes, ...] = (b'{"keys":[]}',),
    ) -> None:
        self.status_code = status_code
        self.headers = {} if content_type is None else {"content-type": content_type}
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeAsyncClient:
    created: list["_FakeAsyncClient"] = []
    response = _FakeResponse()

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.requests: list[dict[str, object]] = []
        type(self).created.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        return type(self).response


def test_httpx_fetcher_uses_exact_url_no_redirects_or_environment_proxy(monkeypatch) -> None:
    from integrations.business_mcp_auth import jwks as module

    _FakeAsyncClient.created = []
    _FakeAsyncClient.response = _FakeResponse(chunks=(b"one", b"two"))
    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)
    fetcher = HttpxJwksFetcher(_policy())

    result = _run(
        fetcher.fetch(
            url=_policy().jwks_uri,
            timeout_seconds=JWKS_TIMEOUT_SECONDS,
            max_bytes=MAX_JWKS_BYTES,
        )
    )

    assert result == b"onetwo"
    assert len(_FakeAsyncClient.created) == 1
    client = _FakeAsyncClient.created[0]
    assert client.kwargs == {
        "follow_redirects": False,
        "trust_env": False,
        "timeout": JWKS_TIMEOUT_SECONDS,
    }
    assert client.requests == [
        {
            "method": "GET",
            "url": _policy().jwks_uri,
            "headers": {"Accept": "application/json"},
        }
    ]


def test_httpx_fetcher_refuses_wrong_url_before_client_creation(monkeypatch) -> None:
    from integrations.business_mcp_auth import jwks as module

    _FakeAsyncClient.created = []
    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)
    fetcher = HttpxJwksFetcher(_policy())

    with pytest.raises(AuthError) as caught:
        _run(
            fetcher.fetch(
                url="https://attacker.test/jwks",
                timeout_seconds=JWKS_TIMEOUT_SECONDS,
                max_bytes=MAX_JWKS_BYTES,
            )
        )

    assert caught.value.code is AuthErrorCode.JWKS_UNAVAILABLE
    assert _FakeAsyncClient.created == []


@pytest.mark.parametrize(
    "response",
    [
        _FakeResponse(status_code=302),
        _FakeResponse(status_code=500),
        _FakeResponse(content_type="text/html"),
        _FakeResponse(content_type="application/octet-stream"),
        _FakeResponse(chunks=(b"a" * (MAX_JWKS_BYTES + 1),)),
    ],
)
def test_httpx_fetcher_maps_remote_or_size_failures_without_leakage(
    monkeypatch, response
) -> None:
    from integrations.business_mcp_auth import jwks as module

    _FakeAsyncClient.created = []
    _FakeAsyncClient.response = response
    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)
    fetcher = HttpxJwksFetcher(_policy())

    with pytest.raises(AuthError) as caught:
        _run(
            fetcher.fetch(
                url=_policy().jwks_uri,
                timeout_seconds=JWKS_TIMEOUT_SECONDS,
                max_bytes=MAX_JWKS_BYTES,
            )
        )

    assert caught.value.code is AuthErrorCode.JWKS_UNAVAILABLE
    assert "identity.example.test" not in str(caught.value)


def test_httpx_fetcher_accepts_jwk_set_media_type_and_optional_charset(monkeypatch) -> None:
    from integrations.business_mcp_auth import jwks as module

    _FakeAsyncClient.created = []
    _FakeAsyncClient.response = _FakeResponse(
        content_type="application/jwk-set+json; charset=utf-8",
        chunks=(b'{"keys":[]}',),
    )
    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)
    fetcher = HttpxJwksFetcher(_policy())

    assert _run(
        fetcher.fetch(
            url=_policy().jwks_uri,
            timeout_seconds=JWKS_TIMEOUT_SECONDS,
            max_bytes=MAX_JWKS_BYTES,
        )
    ) == b'{"keys":[]}'
