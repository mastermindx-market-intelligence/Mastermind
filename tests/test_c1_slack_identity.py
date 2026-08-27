from __future__ import annotations

import asyncio
import importlib
import json

import pytest


TOKEN = "INERT-C1-IDENTITY-TOKEN"
WORKSPACE = "T-C1-WORKSPACE-FIXTURE"
BOT = "U-C1-BOT-FIXTURE"


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.c1_runtime")
    except ModuleNotFoundError:
        pytest.fail("C1 runtime module is not implemented")


class _Transport:
    def __init__(self, response_factory):
        self.response_factory = response_factory
        self.calls = []
        self.closed = False

    async def request(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response_factory(dict(kwargs))

    async def aclose(self):
        self.closed = True


def _response(c1_runtime, payload, *, status: int = 200):
    from integrations.slack_executive import slack_web_api

    return slack_web_api.SlackHttpResponse(
        status_code=status,
        final_url=slack_web_api.SLACK_API_ROOT + "auth.test",
        headers={"content-type": "application/json; charset=utf-8"},
        body=json.dumps(payload).encode("utf-8"),
    )


def test_verify_slack_identity_uses_auth_test_and_matches_workspace_and_bot():
    c1_runtime = _module()
    transport = _Transport(
        lambda call: _response(
            c1_runtime,
            {
                "ok": True,
                "team_id": WORKSPACE,
                "user_id": BOT,
                "team": "Fixture Workspace",
                "user": "relay-fixture",
            },
        )
    )

    receipt = asyncio.run(
        c1_runtime.verify_slack_identity(
            token=TOKEN,
            expected_workspace_id=WORKSPACE,
            expected_bot_user_id=BOT,
            transport=transport,
        )
    )

    assert receipt.workspace_id == WORKSPACE
    assert receipt.bot_user_id == BOT
    assert transport.closed is True
    assert transport.calls == [
        {
            "method": "POST",
            "path": "auth.test",
            "token": TOKEN,
        }
    ]


def test_verify_slack_identity_rejects_wrong_workspace_without_raw_payload():
    c1_runtime = _module()
    transport = _Transport(
        lambda call: _response(
            c1_runtime,
            {"ok": True, "team_id": "T-WRONG", "user_id": BOT},
        )
    )

    async def exercise():
        with pytest.raises(RuntimeError) as caught:
            await c1_runtime.verify_slack_identity(
                token=TOKEN,
                expected_workspace_id=WORKSPACE,
                expected_bot_user_id=BOT,
                transport=transport,
            )
        return str(caught.value)

    assert asyncio.run(exercise()) == "C1_SLACK_IDENTITY_REFUSED"
