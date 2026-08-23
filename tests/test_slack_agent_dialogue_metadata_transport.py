from __future__ import annotations

import json
from dataclasses import dataclass
from email.message import Message

import pytest

import integrations.slack_agent_dialogue.metadata_verifier as verifier

TOKEN = "".join(("xo", "xb-", "123456789012-", "abcdefghijklmnopqrstuvwxyz"))


@dataclass
class FakeResponse:
    body: bytes
    content_type: str = "application/json; charset=utf-8"
    extra_header: str = ""
    status: int = 200
    final_url: str = verifier.SLACK_AUTH_TEST_URL

    def __post_init__(self) -> None:
        headers = Message()
        headers["Content-Type"] = self.content_type
        headers["X-OAuth-Scopes"] = "groups:history, chat:write"
        if self.extra_header:
            headers["X-Extra"] = self.extra_header
        self.headers = headers

    def read(self, limit: int) -> bytes:
        return self.body[:limit]

    def geturl(self) -> str:
        return self.final_url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, timeout: float):  # type: ignore[no-untyped-def]
        self.request = request
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def valid_body() -> bytes:
    return json.dumps(
        {
            "ok": True,
            "team_id": "T0BRD2AQXQV",
            "user_id": "U0BST4WG996",
            "bot_id": "B0BST4WG996",
        }
    ).encode("utf-8")


def test_concrete_transport_disables_ambient_proxy_and_uses_fixed_request(monkeypatch) -> None:
    opener = FakeOpener(response=FakeResponse(valid_body()))
    handlers: tuple[object, ...] = ()

    def build_opener(*values: object) -> FakeOpener:
        nonlocal handlers
        handlers = values
        return opener

    monkeypatch.setattr(verifier.urllib.request, "build_opener", build_opener)
    result = verifier.UrllibSlackAuthTestTransport(timeout_seconds=3).request(token=TOKEN)

    proxy_handlers = [value for value in handlers if isinstance(value, verifier.urllib.request.ProxyHandler)]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}
    assert any(isinstance(value, verifier._NoRedirectHandler) for value in handlers)
    assert result.status_code == 200
    assert opener.request.full_url == verifier.SLACK_AUTH_TEST_URL
    assert opener.request.method == "POST"
    assert opener.request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert opener.timeout == 3


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(valid_body(), content_type="text/html"),
        FakeResponse(valid_body(), extra_header="x" * 4097),
    ],
)
def test_concrete_transport_refuses_untrusted_response_shapes(monkeypatch, response: FakeResponse) -> None:
    monkeypatch.setattr(
        verifier.urllib.request,
        "build_opener",
        lambda *handlers: FakeOpener(response=response),
    )
    with pytest.raises(verifier.MetadataVerificationError) as exc:
        verifier.UrllibSlackAuthTestTransport().request(token=TOKEN)
    assert exc.value.code in {"METADATA_RESPONSE_REFUSED", "SLACK_AUTH_UNAVAILABLE"}
    assert TOKEN not in str(exc.value)


def test_concrete_transport_collapses_third_party_exception(monkeypatch) -> None:
    monkeypatch.setattr(
        verifier.urllib.request,
        "build_opener",
        lambda *handlers: FakeOpener(error=RuntimeError(f"leaked {TOKEN}")),
    )
    with pytest.raises(verifier.MetadataVerificationError) as exc:
        verifier.UrllibSlackAuthTestTransport().request(token=TOKEN)
    assert exc.value.code == "SLACK_AUTH_UNAVAILABLE"
    assert TOKEN not in str(exc.value)
