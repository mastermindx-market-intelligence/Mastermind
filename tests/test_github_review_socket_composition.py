"""Dedicated public GitHub webhook host injects a socket port, never Runtime."""
import asyncio
import json

import pytest

from control_plane.executive_runtime import Runtime
from integrations.github_review_host_composition import (
    compose_github_review_host, GitHubReviewHostCompositionUnavailable,
)
from integrations.github_review_socket_client import ExecutiveReviewSocketClient
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient
from test_github_review_host_composition import _settings, Hook

CHANNEL = "C0CAUK8P8S3"


def slack():
    return SlackWebApiDialogueClient(
        token="test-token", workspace_id="T0BRD2AQXQV",
        channel_id=CHANNEL, bot_user_id="U0BT71H4FQE",
    )


def test_public_socket_composition_is_dormant_and_has_no_runtime_database(tmp_path):
    socket = ExecutiveReviewSocketClient(socket_path=str(tmp_path / "unarmed.sock"))
    credential_reads = []
    def private_key_source():
        credential_reads.append(1)
        raise AssertionError("disabled receiver must not read app credentials")
    app = compose_github_review_host(
        settings=_settings(enabled=False),
        app_id=123,
        private_key_source=private_key_source,
        webhook_secret_source=Hook(),
        relay_client=slack(),
        publisher_login="reviewer-bot[bot]", publisher_user_id=9001,
        socket_client=socket,
    )
    assert app._fabric is socket
    assert app._visibility._threads is socket  # exact socket port, no Runtime
    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        sent.append(message)
    asyncio.run(app({
        "type": "http", "method": "POST",
        "path": app._settings.delivery_path,
        "query_string": b"", "scheme": "https", "headers": [],
    }, receive, send))
    assert sent[0]["status"] == 404
    assert json.loads(sent[1]["body"])["status"] == "RECEIVER_DISABLED"
    assert credential_reads == []


def test_mixed_inprocess_and_socket_ports_never_compose(tmp_path):
    socket = ExecutiveReviewSocketClient(socket_path=str(tmp_path / "unused.sock"))
    with pytest.raises(GitHubReviewHostCompositionUnavailable):
        compose_github_review_host(
            settings=_settings(enabled=False), app_id=123,
            private_key_source=lambda: b"not-used",
            webhook_secret_source=Hook(),
            runtime=Runtime.at(tmp_path / "runtime"),
            admission_guard=lambda: None, socket_client=socket,
            relay_client=slack(), publisher_login="reviewer-bot[bot]", publisher_user_id=9001,
        )


def test_no_runtime_or_socket_is_a_configuration_refusal():
    with pytest.raises(GitHubReviewHostCompositionUnavailable):
        compose_github_review_host(
            settings=_settings(enabled=False), app_id=123,
            private_key_source=lambda: b"not-used",
            webhook_secret_source=Hook(), relay_client=slack(),
            publisher_login="reviewer-bot[bot]", publisher_user_id=9001,
        )

def test_public_socket_host_cannot_select_executive_worker_route(tmp_path):
    socket = ExecutiveReviewSocketClient(socket_path=str(tmp_path / "unarmed.sock"))
    with pytest.raises(
        GitHubReviewHostCompositionUnavailable, match="WORKER_ROUTE_OWNER_ONLY"
    ):
        compose_github_review_host(
            settings=_settings(enabled=False), app_id=123,
            private_key_source=lambda: b"unread",
            webhook_secret_source=Hook(),
            relay_client=slack(), publisher_login="reviewer-bot[bot]", publisher_user_id=9001,
            socket_client=socket,
            worker_constraints={"eligible_quota_classes": ["codex-native"]},
        )
