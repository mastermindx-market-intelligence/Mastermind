"""RED-first contract for the bounded Grok routine webhook client."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
)
from integrations.executive_wake.grok_bot_http import (
    GROK_WAKE_SCHEMA,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    POST_TIMEOUT_SECONDS,
    BoundedHttpResult,
    GrokRoutineCredential,
    GrokRoutineHttpClient,
    grok_routine_target_digest,
    grok_wake_payload,
)
from integrations.executive_wake.grok_bot_routine import GrokBotRoutineWakeDispatcher


NATIVE_HANDLE = "grok-routine-opaque-123"
NUDGE_ID = "NUDGE-" + "b" * 32
BINDING_ID = "bind-grokroutine01"
BINDING_GENERATION = 4
TOKEN = "secret-token-value.not-for-logs"
URL = "https://grok.example.test/hooks/wake"
OPAQUE_IDS = (
    "WAKE-" + "a" * 32,
    "WAKE-" + "a" * 32 + ":delivery:1",
)


def _target_digest(native_handle: str = NATIVE_HANDLE) -> str:
    return hashlib.sha256(
        json.dumps(
            {"native_handle": native_handle},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _credential(**overrides) -> GrokRoutineCredential:
    values = {
        "url": URL,
        "bearer_token": TOKEN,
        "generation": BINDING_GENERATION,
        "target_digest": _target_digest(),
    }
    values.update(overrides)
    return GrokRoutineCredential(**values)


@dataclasses.dataclass
class _CredentialSource:
    credential: object = dataclasses.field(default_factory=_credential)
    fail: BaseException | None = None
    calls: list[str] = dataclasses.field(default_factory=list)

    def resolve(self, native_handle: str):
        self.calls.append(native_handle)
        if self.fail is not None:
            raise self.fail
        return self.credential


@dataclasses.dataclass
class _Poster:
    result: object = dataclasses.field(
        default_factory=lambda: BoundedHttpResult(
            status_code=200,
            body=b'{"accepted":true}',
            request_id="request-opaque-1",
        )
    )
    fail: BaseException | None = None
    calls: list[dict[str, object]] = dataclasses.field(default_factory=list)

    async def post_json(
        self,
        *,
        url,
        headers,
        body,
        timeout_seconds,
        max_response_bytes,
    ):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        if self.fail is not None:
            raise self.fail
        return self.result


def _client(
    *, source=None, poster=None
) -> tuple[GrokRoutineHttpClient, _CredentialSource, _Poster]:
    resolved_source = source or _CredentialSource()
    resolved_poster = poster or _Poster()
    return (
        GrokRoutineHttpClient(resolved_source, resolved_poster),
        resolved_source,
        resolved_poster,
    )


def _deliver(client: GrokRoutineHttpClient, **overrides):
    values = {
        "native_handle": NATIVE_HANDLE,
        "nudge_id": NUDGE_ID,
        "binding_id": BINDING_ID,
        "binding_generation": BINDING_GENERATION,
        "opaque_ids": OPAQUE_IDS,
    }
    values.update(overrides)
    return asyncio.run(client.deliver_wake(**values))


def _wake(**overrides) -> WakeNudge:
    value = {
        "session_alias": "EXECUTIVE-COO-GROK-A",
        "reasoning_surface": "grok-bot",
        "wake_transport": "grok-computer",
        "binding_id": BINDING_ID,
        "binding_generation": BINDING_GENERATION,
        "native_handle": NATIVE_HANDLE,
        "account_label": "must-not-be-sent",
        "destination_digest": "d" * 16,
        "obligation_ids": (OPAQUE_IDS[0],),
        "attempt_command_ids": (OPAQUE_IDS[1],),
        "nudge_id": NUDGE_ID,
    }
    value.update(overrides)
    return WakeNudge(**value)


def test_constants_are_closed_to_the_approved_wire_contract():
    assert GROK_WAKE_SCHEMA == "mastermind.grok_bot_wake.v1"
    assert MAX_REQUEST_BYTES == 16 * 1024
    assert MAX_RESPONSE_BYTES == 16 * 1024
    assert POST_TIMEOUT_SECONDS == 15.0


def test_target_digest_is_full_canonical_sha256_of_exact_native_handle():
    assert grok_routine_target_digest(NATIVE_HANDLE) == _target_digest()
    assert len(grok_routine_target_digest(NATIVE_HANDLE)) == 64
    assert grok_routine_target_digest("other-handle") != _target_digest()


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"url": None}, "HTTPS"),
        ({"url": "https://grok.example.test:bad/hooks/wake"}, "HTTPS"),
        ({"url": "http://grok.example.test/hooks/wake"}, "HTTPS"),
        ({"url": "https://user@grok.example.test/hooks/wake"}, "credentials"),
        ({"url": "https://grok.example.test/hooks/wake?x=1"}, "query"),
        ({"url": "https://grok.example.test/hooks/wake#fragment"}, "fragment"),
        ({"url": " https://grok.example.test/hooks/wake"}, "URL"),
        ({"bearer_token": None}, "token"),
        ({"bearer_token": ""}, "token"),
        ({"bearer_token": "   "}, "token"),
        ({"bearer_token": "line1\nline2"}, "token"),
        ({"bearer_token": "token with space"}, "token"),
        ({"generation": 0}, "generation"),
        ({"generation": True}, "generation"),
        ({"target_digest": "not-a-digest"}, "digest"),
        ({"target_digest": "A" * 64}, "digest"),
    ],
)
def test_credential_validation_is_closed_and_secret_free(overrides, match):
    values = {
        "url": URL,
        "bearer_token": TOKEN,
        "generation": BINDING_GENERATION,
        "target_digest": _target_digest(),
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=match) as captured:
        GrokRoutineCredential(**values)

    rendered = repr(captured.value)
    assert TOKEN not in rendered
    assert "line1" not in rendered


def test_credential_repr_never_contains_url_or_bearer_token():
    credential = _credential()
    rendered = repr(credential)

    assert URL not in rendered
    assert TOKEN not in rendered
    assert "Bearer" not in rendered


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"status_code": True}, "status"),
        ({"status_code": 99}, "status"),
        ({"status_code": 600}, "status"),
        ({"body": "not-bytes"}, "body"),
        ({"request_id": "bad\nrequest"}, "request"),
    ],
)
def test_bounded_http_result_rejects_untyped_metadata_without_exposing_body(kwargs, match):
    values = {"status_code": 200, "body": b"secret-response-body", "request_id": "request-1"}
    values.update(kwargs)

    with pytest.raises(ValueError, match=match) as captured:
        BoundedHttpResult(**values)

    assert "secret-response-body" not in repr(captured.value)


def test_bounded_http_result_repr_redacts_response_body():
    result = BoundedHttpResult(200, b"secret-response-body", "request-1")
    assert "secret-response-body" not in repr(result)


@pytest.mark.parametrize("status_code", [100, 599])
def test_bounded_http_result_accepts_status_boundaries(status_code):
    result = BoundedHttpResult(status_code, b"", None)

    assert result.status_code == status_code


def test_payload_is_exact_canonical_json_and_contains_only_opaque_correlation():
    body = grok_wake_payload(
        native_handle=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        binding_id=BINDING_ID,
        binding_generation=BINDING_GENERATION,
        opaque_ids=OPAQUE_IDS,
    )

    assert body == (
        b'{"binding_generation":4,"binding_id":"bind-grokroutine01",'
        b'"native_handle":"grok-routine-opaque-123",'
        b'"nudge_id":"NUDGE-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
        b'"opaque_ids":["WAKE-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"WAKE-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:delivery:1"],'
        b'"schema":"mastermind.grok_bot_wake.v1"}'
    )
    decoded = json.loads(body)
    assert set(decoded) == {
        "schema",
        "nudge_id",
        "binding_id",
        "binding_generation",
        "native_handle",
        "opaque_ids",
    }
    rendered = body.decode("ascii")
    assert TOKEN not in rendered
    assert URL not in rendered
    assert NATIVE_HANDLE in rendered
    assert "company_consultation_server" not in rendered
    assert "mastermind-company-consultation-mcp" not in rendered
    assert "account" not in rendered


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"native_handle": None}, "native handle"),
        ({"native_handle": " bad"}, "native handle"),
        ({"nudge_id": "bad"}, "nudge"),
        ({"binding_id": None}, "binding"),
        ({"binding_id": " bad"}, "binding"),
        ({"binding_generation": 0}, "generation"),
        ({"opaque_ids": "not-a-sequence-of-ids"}, "opaque"),
        ({"opaque_ids": ()}, "opaque"),
        ({"opaque_ids": tuple(f"id-{i}" for i in range(257))}, "opaque"),
        ({"opaque_ids": ("bad\nid",)}, "opaque"),
    ],
)
def test_payload_rejects_unbounded_or_untyped_inputs(overrides, match):
    values = {
        "native_handle": NATIVE_HANDLE,
        "nudge_id": NUDGE_ID,
        "binding_id": BINDING_ID,
        "binding_generation": BINDING_GENERATION,
        "opaque_ids": OPAQUE_IDS,
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=match):
        grok_wake_payload(**values)


def test_payload_rejects_request_larger_than_sixteen_kibibytes():
    huge_ids = tuple(f"opaque-{index:03d}-" + "x" * 235 for index in range(80))

    with pytest.raises(ValueError, match="request ceiling"):
        grok_wake_payload(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            binding_id=BINDING_ID,
            binding_generation=BINDING_GENERATION,
            opaque_ids=huge_ids,
        )


def test_client_requires_explicit_secret_source_and_poster():
    source = _CredentialSource()
    poster = _Poster()

    with pytest.raises(ValueError, match="credential source"):
        GrokRoutineHttpClient(None, poster)
    with pytest.raises(ValueError, match="poster"):
        GrokRoutineHttpClient(source, None)


def test_exact_http_200_returns_accepted_typed_observation_and_one_post():
    client, source, poster = _client()

    observation = _deliver(client)

    assert observation.native_handle == NATIVE_HANDLE
    assert observation.nudge_id == NUDGE_ID
    assert observation.accepted is True
    assert observation.request_id == "request-opaque-1"
    assert source.calls == [NATIVE_HANDLE]
    assert len(poster.calls) == 1
    call = poster.calls[0]
    assert call["url"] == URL
    assert call["headers"] == {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TOKEN}",
    }
    assert call["timeout_seconds"] == POST_TIMEOUT_SECONDS
    assert call["max_response_bytes"] == MAX_RESPONSE_BYTES
    assert call["body"] == grok_wake_payload(
        native_handle=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        binding_id=BINDING_ID,
        binding_generation=BINDING_GENERATION,
        opaque_ids=OPAQUE_IDS,
    )


@pytest.mark.parametrize("status_code", [201, 204, 301, 302, 400, 401, 404, 409, 429, 500, 503])
def test_every_non_200_status_is_definite_no_start_without_retry(status_code):
    poster = _Poster(
        result=BoundedHttpResult(
            status_code=status_code,
            body=b"provider detail that must not escape",
            request_id="request-no-start",
        )
    )
    client, source, _ = _client(poster=poster)

    with pytest.raises(WakePreSubmitError) as captured:
        _deliver(client)

    assert captured.value.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert captured.value.reason_code == "target_unavailable"
    assert "provider detail" not in repr(captured.value)
    assert source.calls == [NATIVE_HANDLE]
    assert len(poster.calls) == 1


def test_credential_target_digest_mismatch_refuses_before_post():
    source = _CredentialSource(credential=_credential(target_digest="0" * 64))
    client, _, poster = _client(source=source)

    with pytest.raises(WakePreSubmitError, match="target"):
        _deliver(client)

    assert source.calls == [NATIVE_HANDLE]
    assert poster.calls == []


def test_credential_generation_mismatch_refuses_before_post():
    source = _CredentialSource(credential=_credential(generation=BINDING_GENERATION + 1))
    client, _, poster = _client(source=source)

    with pytest.raises(WakePreSubmitError, match="generation"):
        _deliver(client)

    assert source.calls == [NATIVE_HANDLE]
    assert poster.calls == []


def test_credential_resolution_failure_is_typed_no_start_and_redacted():
    source = _CredentialSource(fail=RuntimeError(TOKEN))
    client, _, poster = _client(source=source)

    with pytest.raises(WakePreSubmitError, match="credential unavailable") as captured:
        _deliver(client)

    assert TOKEN not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert source.calls == [NATIVE_HANDLE]
    assert poster.calls == []


def test_credential_resolution_cancellation_is_typed_no_start_and_redacted():
    secret = "secret-credential-cancellation-detail.not-for-logs"
    source = _CredentialSource(fail=asyncio.CancelledError(secret))
    client, _, poster = _client(source=source)

    with pytest.raises(WakePreSubmitError, match="credential unavailable") as captured:
        _deliver(client)

    assert secret not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert source.calls == [NATIVE_HANDLE]
    assert poster.calls == []


def test_post_cancellation_propagates_sanitized_after_one_attempt():
    secret = "secret-post-cancellation-detail.not-for-logs"
    poster = _Poster(fail=asyncio.CancelledError(secret))
    client, source, _ = _client(poster=poster)

    with pytest.raises(asyncio.CancelledError) as captured:
        _deliver(client)

    assert secret not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert source.calls == [NATIVE_HANDLE]
    assert len(poster.calls) == 1


def test_invalid_payload_is_typed_no_start_and_never_calls_secret_source_or_poster():
    client, source, poster = _client()

    with pytest.raises(WakePreSubmitError, match="payload"):
        _deliver(client, nudge_id="bad")

    assert source.calls == []
    assert poster.calls == []


def test_untyped_credential_source_result_is_typed_no_start():
    source = _CredentialSource(credential=object())
    client, _, poster = _client(source=source)

    with pytest.raises(WakePreSubmitError, match="credential unavailable"):
        _deliver(client)

    assert poster.calls == []


def test_poster_exception_is_redacted_after_one_call_for_dispatcher_effect_unknown():
    poster = _Poster(fail=TimeoutError(f"{TOKEN} {URL} response lost after write"))
    client, source, _ = _client(poster=poster)

    with pytest.raises(RuntimeError, match="result is unavailable") as captured:
        _deliver(client)

    assert TOKEN not in repr(captured.value)
    assert URL not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert source.calls == [NATIVE_HANDLE]
    assert len(poster.calls) == 1

    dispatcher = GrokBotRoutineWakeDispatcher(client)
    with pytest.raises(WakeEffectUnknownError, match="effect is unknown") as unknown:
        asyncio.run(dispatcher.nudge(_wake()))
    assert TOKEN not in repr(unknown.value)
    assert URL not in repr(unknown.value)
    assert unknown.value.__cause__ is None
    assert unknown.value.__context__ is None
    assert len(poster.calls) == 2


def test_oversized_200_response_is_effect_unknown_not_pre_submit_failure():
    poster = _Poster(
        result=BoundedHttpResult(
            status_code=200,
            body=b"x" * (MAX_RESPONSE_BYTES + 1),
            request_id="request-oversized",
        )
    )
    client, _, _ = _client(poster=poster)
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="effect is unknown"):
        asyncio.run(dispatcher.nudge(_wake()))
    assert len(poster.calls) == 1


def test_untyped_post_result_is_effect_unknown_after_exactly_one_post():
    poster = _Poster(result=object())
    client, _, _ = _client(poster=poster)
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="effect is unknown"):
        asyncio.run(dispatcher.nudge(_wake()))
    assert len(poster.calls) == 1


def test_non_200_through_dispatcher_is_target_unavailable_not_effect_unknown():
    poster = _Poster(result=BoundedHttpResult(503, b"unavailable", None))
    client, _, _ = _client(poster=poster)
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    receipt = asyncio.run(dispatcher.nudge(_wake()))

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert len(poster.calls) == 1


def test_http_source_contains_no_concrete_network_library_or_retry_loop():
    import ast
    from pathlib import Path

    source = Path("integrations/executive_wake/grok_bot_http.py").read_text()
    tree = ast.parse(source)
    forbidden_modules = {
        "aiohttp",
        "http",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib3",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(forbidden_modules)
    assert not any(isinstance(node, (ast.For, ast.AsyncFor, ast.While)) for node in ast.walk(tree))
    assert "company_consultation_server" not in source
    assert "mastermind-company-consultation-mcp" not in source
