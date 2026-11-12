"""Exercise typed Executive errors through the authenticated MCP wire."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from tests import test_mastermind_executive_app_asgi as auth


@pytest.mark.parametrize(
    ("failure", "arguments", "expected_code", "attempt_count"),
    [
        ("missing", {}, "backend_unavailable", 1),
        ("missing", {"unexpected": True}, "invalid_input", 0),
        ("refused", {}, "backend_refused", 1),
        ("lost", {}, "backend_unavailable", 1),
    ],
)
def test_error_has_identical_structured_payload_without_retry(
    tmp_path, monkeypatch, failure, arguments, expected_code, attempt_count,
):
    from integrations.executive_mcp import server
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app import gateway

    attempts = []
    frames = []
    original_client = gateway.CeoIngressClient

    class ObservedClient(original_client):
        async def send_frame(self, socket_path, frame):
            attempts.append(frame)
            return await super().send_frame(socket_path, frame)

    class Sink:
        def emit(self, event):
            pass

    monkeypatch.setattr(gateway, "CeoIngressClient", ObservedClient)
    key = auth.rsa_key.__wrapped__()

    async def exercise(socket_path):
        async def backend(reader, writer):
            try:
                frame = json.loads(await reader.readline())
                frames.append(frame)
                if failure == "refused":
                    writer.write(json.dumps({
                        "ok": False,
                        "error": {
                            "code": "authority_refused",
                            "message": "PRIVATE_BACKEND_DETAIL_MUST_NOT_LEAK",
                        },
                    }).encode() + b"\n")
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        listener = None
        if failure in ("refused", "lost"):
            listener = await asyncio.start_unix_server(backend, path=socket_path)
        settings = AppSettings(
            policies=gateway.AppPolicies(
                read=auth._read_policy(), submit=auth._submit_policy(),
            ),
            mastermind_root=tmp_path / "unused-source",
            macro_root_flag=None,
            environ={},
            ceo_ingress_socket_path=socket_path,
            read_from_ceo_ingress=True,
            jwks_cache=auth._FakeJwksCache(key),
            clock=lambda: auth.NOW,
        )
        app = server.build_personal_read_mcp_app(settings, audit_sink=Sink())
        outer = app._app
        headers = {
            "authorization": f"Bearer {auth._read_token(key)}",
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18",
        }
        try:
            async with outer.router.lifespan_context(outer):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                ) as client:
                    initialized = await client.post("/mcp", headers=headers, json={
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "error-contract-proof", "version": "1"},
                        },
                    })
                    assert initialized.status_code == 200
                    response = await client.post("/mcp", headers=headers, json={
                        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "executive_state", "arguments": arguments},
                    })
                    assert response.status_code == 200
                    result = response.json()["result"]
                    payload = json.loads(result["content"][0]["text"])
                    assert result["isError"] is True
                    assert payload["error"]["code"] == expected_code
                    assert result.get("structuredContent") == payload
                    assert payload["ok"] is False and payload["data"] is None
                    assert payload["grounding"] == {}
                    assert "PRIVATE_BACKEND_DETAIL" not in response.text
                    assert socket_path not in response.text
                    assert len(response.content) < server.MAX_RESPONSE_BYTES
                    if failure == "missing" and not arguments:
                        assert "request was not sent" in payload["error"]["message"]
                    if failure == "lost":
                        assert "after the read request was attempted" in payload["error"]["message"]
        finally:
            if listener is not None:
                listener.close()
                await listener.wait_closed()

    # A short native socket path also exercises macOS's real path-length limit.
    with tempfile.TemporaryDirectory(prefix="mmx-result-") as directory:
        asyncio.run(exercise(str(Path(directory) / "reader.sock")))
    assert len(attempts) == attempt_count
    assert len(frames) == (1 if failure in ("refused", "lost") else 0)
