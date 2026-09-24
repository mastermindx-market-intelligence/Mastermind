from __future__ import annotations

import json

from integrations.slack_agent_dialogue.metadata_verifier import (
    HttpResult,
    MetadataExpectation,
    SLACK_AUTH_TEST_URL,
    verify_metadata,
)

TOKEN = "".join(("xo", "xb-", "123456789012-", "abcdefghijklmnopqrstuvwxyz"))


class FakeTransport:
    def request(self, *, token: str) -> HttpResult:
        assert token == TOKEN
        return HttpResult(
            status_code=200,
            final_url=SLACK_AUTH_TEST_URL,
            headers={
                "content-type": "application/json",
                "x-oauth-scopes": "groups:history, chat:write",
            },
            body=json.dumps(
                {
                    "ok": True,
                    "team_id": "T0BRD2AQXQV",
                    "user_id": "U0BST4WG996",
                    "bot_id": "B0BST4WG996",
                }
            ).encode("utf-8"),
        )


def test_known_bot_user_can_bootstrap_non_secret_bot_id() -> None:
    receipt = verify_metadata(
        token=TOKEN,
        expectation=MetadataExpectation(
            team_id="T0BRD2AQXQV",
            bot_user_id="U0BST4WG996",
            scopes=("groups:history", "chat:write"),
        ),
        transport=FakeTransport(),
    )
    assert receipt["bot_id"] == "B0BST4WG996"
    assert TOKEN not in json.dumps(receipt)
