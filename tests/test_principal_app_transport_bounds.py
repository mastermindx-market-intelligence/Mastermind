"""Real local client framing; no receiving-service admission or effect proof."""
import asyncio
import json

import pytest

from common.company_dialogue_principal_limits import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES
from integrations.company_dialogue_principal_app_contract import encode_app_request
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN,
)
from tests.test_principal_app_dialogue_contract import caller, arguments


def large_frame():
    args = arguments()
    args.update(decision="原" * 900, rationale="因" * 900)
    prefix = "https://github.com/mastermindx-market-intelligence/Mastermind/blob/" + "a" * 40 + "/"
    args["evidence_refs"] = [prefix + str(i) + "a" * (499 - len(prefix)) for i in range(8)]
    encoded = encode_app_request(caller=caller(), obligation_id="WAKE-" + "d" * 32,
        tool="ruling", arguments=args)
    assert 8192 < len(encoded) < MAX_REQUEST_BYTES
    return json.loads(encoded)


@pytest.mark.parametrize("too_large", [False, True])
def test_exact_principal_schema_uses_its_bounded_request_and_response_limits(tmp_path, too_large):
    async def scenario():
        calls = []
        async def receive(reader, writer):
            try:
                raw = await reader.readuntil(b"\n")
                calls.append(json.loads(raw))
                assert len(raw) <= MAX_REQUEST_BYTES
                size = MAX_RESPONSE_BYTES if too_large else 40_000
                writer.write(json.dumps({"ok": True, "result": {"fixture": "x" * size}}).encode() + b"\n")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        path = tmp_path / "app.sock"
        server = await asyncio.start_unix_server(receive, path=str(path), limit=MAX_REQUEST_BYTES + 1)
        try:
            frame = large_frame()
            result = await CeoIngressClient().send_frame(path, frame)
            assert result.transport == (TRANSPORT_SENT_UNKNOWN if too_large else TRANSPORT_SENT_OK)
            assert calls == [frame]
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["unknown", "old_submit", "extra", "tool", "authority"])
def test_other_or_invalid_frames_cannot_select_principal_limits(monkeypatch, change):
    frame = large_frame()
    if change == "unknown": frame["schema"] = "mastermind.ceo_ingress.unrecognized.v1"
    if change == "old_submit": frame["schema"] = "mastermind.executive_ceo_ingress_submit.v2"
    if change == "extra": frame["source"] = {"trusted": True}
    if change == "tool": frame["tool"] = "stop"
    if change == "authority": frame["arguments"]["authority_class"] = "CHAIRMAN_REQUIRED"
    calls = []
    async def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("invalid or excessive frame must not connect")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    result = asyncio.run(CeoIngressClient().send_frame("/fixture/absent.sock", frame))
    assert result.transport == TRANSPORT_NOT_SENT
    assert calls == []
