from __future__ import annotations

import asyncio
import importlib

import httpx
import pytest


TOKEN = "INERT-C1-IDENTITY-TOKEN"
WORKSPACE = "T-C1-WORKSPACE-FIXTURE"
BOT = "U-C1-BOT-FIXTURE"


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.c1_runtime")
    except ModuleNotFoundError:
        pytest.fail("C1 runtime module is not implemented")


def test_verify_slack_identity_uses_auth_test_and_matches_workspace_and_bot():
    c1_runtime = _module()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "team_id": WORKSPACE,
                "user_id": BOT,
                "team": "Fixture Workspace",
                "user": "relay-fixture",
            },
            request=request,
        )

    receipt = asyncio.run(
        c1_runtime.verify_slack_identity(
            token=TOKEN,
            expected_workspace_id=WORKSPACE,
            expected_bot_user_id=BOT,
            transport=httpx.MockTransport(handler),
        )
    )

    assert receipt.workspace_id == WORKSPACE
    assert receipt.bot_user_id == BOT
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.scheme == "https"
    assert request.url.host == "slack.com"
    assert request.url.path == "/api/auth.test"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


def test_verify_slack_identity_rejects_wrong_workspace_without_raw_payload():
    c1_runtime = _module()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True, "team_id": "T-WRONG", "user_id": BOT},
            request=request,
        )

    async def exercise():
        with pytest.raises(RuntimeError) as caught:
            await c1_runtime.verify_slack_identity(
                token=TOKEN,
                expected_workspace_id=WORKSPACE,
                expected_bot_user_id=BOT,
                transport=httpx.MockTransport(handler),
            )
        return str(caught.value)

    assert asyncio.run(exercise()) == "C1_SLACK_IDENTITY_REFUSED"
