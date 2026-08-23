from __future__ import annotations

import pytest

from integrations.slack_agent_dialogue.metadata_verifier import (
    HttpResult,
    MetadataExpectation,
    MetadataVerificationError,
    SLACK_AUTH_TEST_URL,
    verify_metadata,
)

TOKEN = "".join(("xo", "xb-", "123456789012-", "abcdefghijklmnopqrstuvwxyz"))
EXPECTATION = MetadataExpectation(
    team_id="T0BRD2AQXQV",
    bot_user_id="U0BST4WG996",
    scopes=("groups:history", "chat:write"),
)


class FakeTransport:
    def __init__(self, result: object) -> None:
        self.result = result

    def request(self, *, token: str) -> object:
        assert token == TOKEN
        return self.result


def result(body: bytes) -> HttpResult:
    return HttpResult(
        status_code=200,
        final_url=SLACK_AUTH_TEST_URL,
        headers={"x-oauth-scopes": "groups:history, chat:write"},
        body=body,
    )


@pytest.mark.parametrize(
    "body",
    [
        b'{"ok":false,"ok":true,"team_id":"T0BRD2AQXQV","user_id":"U0BST4WG996","bot_id":"B0BST4WG996"}',
        b'{"ok":true,"team_id":"T0BRD2AQXQV","user_id":"U0BST4WG996","bot_id":"B0BST4WG996","unknown":NaN}',
        b'{"ok":true,"team_id":"T0BRD2AQXQV","user_id":"U0BST4WG996","bot_id":"B0BST4WG996","nested":{"x":1,"x":2}}',
    ],
)
def test_ambiguous_or_nonfinite_json_refuses(body: bytes) -> None:
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=EXPECTATION,
            transport=FakeTransport(result(body)),  # type: ignore[arg-type]
        )
    assert exc.value.code == "METADATA_RESPONSE_REFUSED"


def test_non_normalized_transport_result_refuses() -> None:
    with pytest.raises(MetadataVerificationError) as exc:
        verify_metadata(
            token=TOKEN,
            expectation=EXPECTATION,
            transport=FakeTransport({"ok": True}),  # type: ignore[arg-type]
        )
    assert exc.value.code == "METADATA_RESPONSE_REFUSED"
