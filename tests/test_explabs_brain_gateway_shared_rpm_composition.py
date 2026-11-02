"""Real localhost TCP integration across Brain, Responses and native Jev gateway.

The upstream is *always* MockTransport. In the Brain-only stacked PR this
test explicitly skips until sibling gateway #1945 source is composed; it
becomes executable when the real shared-gateway source is present.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest

from brain import explabs_pool


SCOPED = "fixture-scoped-local-token-for-shared-account"
UPSTREAM = "fixture-host-owned-upstream-provider-credential"


def test_real_local_tcp_brain_responses_jev_one_shared_sqlite_rpm(tmp_path, monkeypatch):
    path = (Path(__file__).resolve().parents[1]
            / "ops/native_fabric/experiential_proxy/gateway.py")
    if not path.is_file():
        pytest.skip("gateway PR #1945 not yet composed into Brain source")
    uvicorn = pytest.importorskip("uvicorn")
    from ops.native_fabric.experiential_proxy.gateway import Settings, create_app

    observed = []

    def fixture_provider(request: httpx.Request) -> httpx.Response:
        # No public-network transport is configured; the host-only token is
        # never sent back to the Brain client.
        assert request.headers["authorization"] == "Bearer " + UPSTREAM
        assert request.url.host == "api.experientiallabs.ai"
        assert request.url.query == b""
        observed.append((request.method, request.url.path))
        path = request.url.path
        if path == "/api/whoami":
            value = {"org_id": "org-b-fixture", "org_slug": "org-b",
                     "account_key": "SECRET-MUST-NOT-LEAK"}
        elif path == "/v1/models":
            value = {"data": [{"id": "deepseek-v4.1-flash"}]}
        elif path == "/api/v1/key":
            value = {"data": {"limit": 1.0, "limit_remaining": .8,
                              "key_id": "SECRET-MUST-NOT-LEAK"}}
        elif path == "/api/v1/credits":
            value = {"data": {"total_credits": 4600, "total_usage": 0,
                              "account": "SECRET-MUST-NOT-LEAK"}}
        elif path == "/v1/chat/completions":
            body = json.loads(request.content)
            assert body["model"] == "deepseek-v4.1-flash"
            assert body["max_tokens"] == 200
            value = {
                "model": "deepseek-v4.1-flash",
                "choices": [{"message": {"role": "assistant",
                                         "content": "fixture-completed"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8,
                          "cost": .0002, "is_byok": False},
            }
        elif path == "/v1/responses":
            assert json.loads(request.content)["model"] == "deepseek-v4.1-flash"
            value = {"id": "response-fixture", "status": "completed"}
        elif path == "/v1/systemone":
            assert json.loads(request.content)["model"] == "jev-latest"
            value = {"model": "jev-latest",
                     "answers": {"complexity": {"choice": "C1_ROUTINE_BOUNDED"}}}
        else:
            raise AssertionError(f"unrecognized mock route: {path}")
        return httpx.Response(200, headers={"content-type": "application/json"},
                              stream=httpx.ByteStream(json.dumps(value).encode()))

    state_dir = tmp_path / "admissions"
    state_dir.mkdir(mode=0o700)
    app = create_app(
        Settings(api_keys=(UPSTREAM,), proxy_token=SCOPED,
                 state_dir=state_dir, safe_rpm=8, safe_rpm_shared=8,
                 max_inflight_per_key=8, window_s=60.0,
                 max_queue_wait_s=.05, enable_account_metadata=True),
        transport=httpx.MockTransport(fixture_provider),
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(64)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port,
        log_level="critical", access_log=False, lifespan="on",
    ))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True,
    )
    thread.start()
    try:
        deadline = time.monotonic() + 8
        while not server.started:
            assert time.monotonic() < deadline, "localhost gateway did not start"
            time.sleep(.02)

        origin = f"http://127.0.0.1:{port}"
        config = {
            "EXPLABS_POOL_ENABLED": "1",
            "EXPLABS_MODEL": "deepseek-v4.1-flash",
            "EXPLABS_ACCOUNT_1_ENABLED": "0",
            "EXPLABS_ACCOUNT_1_SERVING_VERIFIED": "0",
            "EXPLABS_API_KEY": "disabled-a-not-probed",
            "EXPLABS_ACCOUNT_2_ENABLED": "1",
            # Test-only fixture: production serving gate remains OFF.
            "EXPLABS_ACCOUNT_2_SERVING_VERIFIED": "1",
            "EXPLABS_ACCOUNT_2_ORG_SLUG": "org-b",
            "EXPLABS_ACCOUNT_2_MAX_INFLIGHT": "2",
            "EXPLABS_ACCOUNT_2_DAILY_CAP_USD": "1",
            "EXPLABS_ACCOUNT_2_TRANSPORT": "shared_gateway",
            "EXPLABS_ACCOUNT_2_GATEWAY_ORIGIN": origin,
            "EXPLABS_ACCOUNT_2_GATEWAY_TOKEN": SCOPED,
        }
        for name, value in config.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("EXPLABS_API_KEY_2", raising=False)

        # Deliberately hostile ambient proxies must never receive a local
        # scoped token. Exercise production's default HTTPX path, not merely
        # an explicitly trust_env=False injected test client.
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("NO_PROXY", "")
        with httpx.Client(timeout=10, trust_env=False) as client:
            pool = explabs_pool.AccountPool()
            brain = pool.complete("", "offline Brain fixture", max_tokens=200)
            assert brain.account_slot == "2"
            assert brain.text == "fixture-completed"
            assert brain.is_byok is False and brain.cost_usd == .0002

            headers = {"Authorization": "Bearer " + SCOPED}
            response = client.post(origin + "/v1/responses", headers=headers,
                                   json={"model": "deepseek-v4.1-flash", "input": "fixture"})
            assert response.status_code == 200
            jev = client.post(origin + "/v1/systemone", headers=headers,
                              json={"model": "jev-latest"})
            assert jev.status_code == 200 and jev.json()["model"] == "jev-latest"
            status = client.get(origin + "/statusz", headers=headers).json()
            assert status["shared_used_in_window"] == 8
            assert status["shared_rpm_cap"] == 8

            denied = client.post(origin + "/v1/systemone", headers=headers,
                                 json={"model": "jev-latest"})
            assert denied.status_code == 504
            assert client.get(origin + "/statusz", headers=headers).json()[
                "shared_used_in_window"
            ] == 8
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        assert not thread.is_alive(), "test gateway listener was not stopped"

    assert observed == [
        ("GET", "/api/whoami"),
        ("GET", "/v1/models"),
        ("GET", "/api/v1/key"),
        ("GET", "/api/v1/credits"),
        ("GET", "/api/v1/key"),
        ("POST", "/v1/chat/completions"),
        ("POST", "/v1/responses"),
        ("POST", "/v1/systemone"),
    ]
