"""Offline qualification for the Responses-wire OAuth route (no network).

Covers: closed request/response/stream translation, exhausted-account
admission, JWT account-id extraction, refresh peer-adoption under the
incumbent auth.json lock, 429 bench-and-rotate, and x-api-key acceptance.
No credentials are read; the Hermes auth store is a fixture on disk.
"""
from __future__ import annotations

import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx  # noqa: E402

from ops.native_fabric.unified_router import codex_oauth  # noqa: E402
from ops.native_fabric.unified_router.gateway import (  # noqa: E402
    Settings, create_app)
from ops.native_fabric.unified_router.routes import (  # noqa: E402
    Route, WIRE_RESPONSES)
from ops.native_fabric.unified_router.wire import (  # noqa: E402
    ResponsesStreamTranslator, WireTranslationError,
    anthropic_to_responses, responses_to_anthropic)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _codex_jwt(account_id: str = "acct-1") -> str:
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    claims = {"sub": "u", "exp": 9999999999,
              "https://api.openai.com/auth": {
                  "chatgpt_account_id": account_id,
                  "chatgpt_plan_type": "pro"}}
    payload = _b64url(json.dumps(claims).encode())
    return f"{header}.{payload}.{_b64url(b'sig')}"


class FabricTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestTranslation(FabricTestCase):
    def test_request_text_system_tools(self):
        body = {"model": "gpt-5.6-luna", "max_tokens": 64, "system": "be brief",
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "tool_use", "id": "t1", "name": "f",
                         "input": {"a": 1}}]},
                    {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "t1",
                         "content": "42"}]}],
                "tools": [{"name": "f", "description": "d",
                           "input_schema": {"type": "object"}}]}
        out = anthropic_to_responses(body)
        assert out["model"] == "gpt-5.6-luna"
        assert out["max_output_tokens"] == 64
        assert out["instructions"] == "be brief"
        assert out["store"] is False
        kinds = [item.get("type") or item.get("role") for item in out["input"]]
        assert "function_call_output" in kinds
        assert any(item.get("role") == "assistant" for item in out["input"])
        assert out["tools"][0]["name"] == "f"

    def test_request_closed_on_unknown_block(self):
        body = {"model": "m", "max_tokens": 8, "messages": [
            {"role": "user", "content": [{"type": "server_tool_use"}]}]}
        with self.assertRaises(WireTranslationError):
            anthropic_to_responses(body)

    def test_response_translation(self):
        payload = {"id": "resp_1", "status": "completed", "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [
                {"type": "output_text", "text": "ok"}]},
            {"type": "function_call", "call_id": "c1", "name": "f",
             "arguments": '{"a":1}'}],
            "usage": {"input_tokens": 5, "output_tokens": 7}}
        out = responses_to_anthropic(payload, model="gpt")
        assert out["content"][0] == {"type": "text", "text": "ok"}
        assert out["content"][1]["type"] == "tool_use"
        assert out["stop_reason"] == "tool_use"
        assert out["usage"]["output_tokens"] == 7

    def test_stream_translator(self):
        t = ResponsesStreamTranslator(model="gpt")
        events: list[tuple[str, str]] = []
        events.append(t.message_start())
        for chunk in [
            {"type": "response.output_text.delta", "delta": "he"},
            {"type": "response.output_text.delta", "delta": "y"},
            {"type": "response.output_item.added",
             "item": {"type": "function_call", "call_id": "c1", "name": "f"}},
            {"type": "response.function_call_arguments.delta",
             "call_id": "c1", "delta": '{"x":2}'},
            {"type": "response.completed",
             "response": {"status": "completed",
                          "usage": {"input_tokens": 3, "output_tokens": 4}}}]:
            events.extend(t.feed(chunk))
        events.extend(t.finish())
        names = [e for e, _ in events]
        assert names[0] == "message_start"
        assert "content_block_delta" in names
        assert names[-1] == "message_stop"
        by_event: dict[str, str] = {}
        for e, d in events:
            by_event.setdefault(e, d)
        assert json.loads(by_event["message_delta"])[
            "delta"]["stop_reason"] == "tool_use"
        tool_start = json.loads(by_event["content_block_start"])
        if tool_start["content_block"]["type"] == "tool_use":
            assert tool_start["content_block"]["id"] == "c1"


class TestCodexOauth(FabricTestCase):
    def _store(self, *, exhausted: bool = False) -> Path:
        entry = {"id": "a1", "label": "pro-1", "access_token": _codex_jwt(),
                 "refresh_token": "rt-1", "source": "manual:device_code"}
        if exhausted:
            entry.update({"last_status": "exhausted",
                          "last_error_reset_at": time.time() + 3600})
        document = {"credential_pool": {"openai-codex": [entry]}}
        store = self.tmp_path / "auth.json"
        store.write_text(json.dumps(document))
        (self.tmp_path / "auth.json.lock").touch()
        return store

    def test_read_accounts_and_exhaustion(self):
        store = self._store()
        accounts = codex_oauth.read_accounts(store, "openai-codex")
        assert accounts[0].label == "pro-1" and not accounts[0].exhausted
        store = self._store(exhausted=True)
        accounts = codex_oauth.read_accounts(store, "openai-codex")
        assert accounts[0].exhausted

    def test_account_id_header(self):
        assert codex_oauth.account_id_header(_codex_jwt("acct-9")) == {
            "ChatGPT-Account-ID": "acct-9"}
        assert codex_oauth.account_id_header("not-a-jwt") == {}

    def test_refresh_peer_adoption(self):
        store = self._store()
        account = codex_oauth.read_accounts(store, "openai-codex")[0]
        # A peer rotates the single-use grant after we read the row.
        document = json.loads(store.read_text())
        document["credential_pool"]["openai-codex"][0][
            "refresh_token"] = "rt-rotated-by-peer"
        store.write_text(json.dumps(document))
        client = MagicMock()
        adopted = codex_oauth.refresh_account(
            store, "openai-codex", account,
            token_url="https://auth.openai.com/oauth/token",
            client_id="cid", client=client)
        assert adopted.refresh_token == "rt-rotated-by-peer"
        client.post.assert_not_called()

    def test_refresh_rotation_commit(self):
        store = self._store()
        account = codex_oauth.read_accounts(store, "openai-codex")[0]
        response = MagicMock(status_code=200)
        response.json.return_value = {"access_token": "at-2",
                                      "refresh_token": "rt-2"}
        client = MagicMock()
        client.post.return_value = response
        refreshed = codex_oauth.refresh_account(
            store, "openai-codex", account,
            token_url="https://auth.openai.com/oauth/token",
            client_id="cid", client=client)
        assert refreshed.access_token == "at-2"
        row = json.loads(store.read_text())["credential_pool"][
            "openai-codex"][0]
        assert row["access_token"] == "at-2" and row["refresh_token"] == "rt-2"
        assert "last_status" not in row

    def test_bench_row(self):
        store = self._store()
        codex_oauth.bench_row(store, "openai-codex", "a1",
                              reset_at=123.0, reason="http_429 cap")
        row = json.loads(store.read_text())["credential_pool"][
            "openai-codex"][0]
        assert row["last_status"] == "exhausted"
        assert row["last_error_reset_at"] == 123.0


def _oauth_route() -> Route:
    return Route(route_id="codex_pool", kind="oauth_pool", pool="openai-codex",
                 base_url="https://chatgpt.com/backend-api/codex",
                 wire=WIRE_RESPONSES, priority=10,
                 models=("gpt-5.6-luna", "gpt-6.1-sol"),
                 token_url="https://auth.openai.com/oauth/token",
                 client_id="cid", originator="hermes-agent")


class TestGatewayResponsesRoute(FabricTestCase):
    TOKEN = "t" * 32

    def _settings(self):
        return Settings(proxy_token=self.TOKEN,
                        state_dir=self.tmp_path / "state",
                        routes=(_oauth_route(),),
                        auth_store=self.tmp_path / "auth.json")

    def _prepare_store(self, *, exhausted: bool = False) -> None:
        entry = {"id": "a1", "label": "pro-1", "access_token": _codex_jwt(),
                 "refresh_token": "rt-1"}
        if exhausted:
            entry.update({"last_status": "exhausted",
                          "last_error_reset_at": time.time() + 3600})
        document = {"credential_pool": {"openai-codex": [entry]}}
        (self.tmp_path / "auth.json").write_text(json.dumps(document))
        (self.tmp_path / "auth.json.lock").touch()

    def _client(self, handler):
        import fastapi.testclient
        app = create_app(self._settings(), transport=httpx.MockTransport(handler))
        # The router admits loopback peers only; pin the synthetic client
        # address so the admission path is exercised faithfully.
        return fastapi.testclient.TestClient(app, client=("127.0.0.1", 50000))

    def test_x_api_key_models_listing(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"output": []})

        with self._client(handler) as client:
            reply = client.get("/v1/models",
                               headers={"x-api-key": self.TOKEN})
            assert reply.status_code == 200
            ids = [row["id"] for row in reply.json()["data"]]
            assert "gpt-5.6-luna" in ids and "gpt-6.1-sol" in ids
            assert reply.json()["data"][0]["owned_by"] == "capacity-fabric"
            assert client.get("/v1/models", headers={
                "x-api-key": "wrong"}).status_code == 401

    def test_nonstream_message_translated(self):
        self._prepare_store()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/responses")
            assert request.headers["authorization"].startswith("Bearer ")
            assert request.headers.get("ChatGPT-Account-ID") == "acct-1"
            return httpx.Response(200, json={
                "id": "resp_9", "status": "completed", "output": [
                    {"type": "message", "content": [
                        {"type": "output_text", "text": "CODEX-VIA-FABRIC"}]}],
                "usage": {"input_tokens": 4, "output_tokens": 6}})

        with self._client(handler) as client:
            reply = client.post("/v1/messages",
                                headers={"x-api-key": self.TOKEN},
                                json={"model": "gpt-5.6-luna", "max_tokens": 32,
                                      "messages": [
                                          {"role": "user", "content": "hi"}]})
            assert reply.status_code == 200
            body = reply.json()
            assert body["content"][0]["text"] == "CODEX-VIA-FABRIC"
            assert body["usage"]["output_tokens"] == 6

    def test_429_benches_row_and_refuses(self):
        self._prepare_store()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, json={"error": {"message": "usage limit reached"}},
                headers={"retry-after": "3600"})

        with self._client(handler) as client:
            reply = client.post("/v1/messages",
                                headers={"x-api-key": self.TOKEN},
                                json={"model": "gpt-5.6-luna", "max_tokens": 32,
                                      "messages": [
                                          {"role": "user", "content": "hi"}]})
            assert reply.status_code == 503
            row = json.loads((self.tmp_path / "auth.json").read_text())[
                "credential_pool"]["openai-codex"][0]
            assert row["last_status"] == "exhausted"

    def test_exhausted_pool_refuses_before_send(self):
        self._prepare_store(exhausted=True)

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no upstream call may happen")

        with self._client(handler) as client:
            reply = client.post("/v1/messages",
                                headers={"x-api-key": self.TOKEN},
                                json={"model": "gpt-5.6-luna", "max_tokens": 32,
                                      "messages": [
                                          {"role": "user", "content": "hi"}]})
            assert reply.status_code == 503
            assert reply.json()["error"]["code"] == "FABRIC_OAUTH_ACCOUNTS_EXHAUSTED"


if __name__ == "__main__":
    unittest.main()
