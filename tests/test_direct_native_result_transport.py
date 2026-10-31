"""Inert private-client tests; no real socket, credential or Runtime source."""
import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from common import direct_native_result_contract as c
from integrations.mastermind_executive_app.direct_native import DirectNativeResultClient
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN,
)


class Writer:
    def __init__(self):
        self.frames = []
        self.closed = False
        self.transport = self
    def write(self, raw): self.frames.append(raw)
    async def drain(self): pass
    def write_eof(self): pass
    def close(self): self.closed = True
    def abort(self): self.closed = True
    async def wait_closed(self): pass


class DirectResultTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.body = dict(work_ref="WS:H2", job_id="JOB-h2", attempt_id="ATT-h2")
        self.payload = dict(summary="Findings", current_state="Complete",
                            completed_steps=[], next_actions=[])
        self.result = c.available(self.body, self.payload, "a" * 64,
                                  dict(state="UNCONSUMED", receipt_digest=None))

    async def exchange(self, raw, *, frame=None):
        reader = asyncio.StreamReader(); reader.feed_data(raw); reader.feed_eof()
        writer = Writer()
        client = CeoIngressClient()
        if frame is None:
            frame = dict(self.body, schema=c.PRIVATE_SCHEMA, operation="result", principal_scope="b" * 64)
        with patch("asyncio.open_unix_connection", new=AsyncMock(return_value=(reader, writer))) as opened:
            result = await client.send_frame(Path("/fixture/ceo-ingress.sock"), frame)
        return result, writer, opened.await_count

    async def test_actual_existing_client_sends_exactly_one_closed_frame(self):
        result, writer, calls = await self.exchange(c.canonical_bytes(dict(ok=True, result=self.result)) + b"\n")
        self.assertEqual(result.transport, TRANSPORT_SENT_OK)
        self.assertEqual(result.result, self.result)
        self.assertEqual(calls, 1); self.assertEqual(len(writer.frames), 1)
        self.assertTrue(writer.closed)

    async def test_duplicate_nonfinite_extra_envelope_or_lost_response_unknown(self):
        raws = [b'{"ok":true,"ok":false,"result":{}}\n',
                b'{"ok":true,"result":{"x":NaN}}\n',
                b'{"ok":true,"result":{},"secret_sentinel":"DO_NOT_RETURN"}\n', b'']
        for raw in raws:
            with self.subTest(raw=raw):
                result, writer, calls = await self.exchange(raw)
                self.assertEqual(result.transport, TRANSPORT_SENT_UNKNOWN)
                self.assertIsNone(result.result)
                self.assertNotIn("DO_NOT_RETURN", result.detail)
                self.assertEqual(calls, 1); self.assertEqual(len(writer.frames), 1)

    async def test_malformed_private_frame_refuses_before_connection(self):
        frame = dict(self.body, schema=c.PRIVATE_SCHEMA, operation="result", principal_scope="b" * 64,
                     worker_id="forged")
        result, writer, calls = await self.exchange(b'', frame=frame)
        self.assertEqual(result.transport, TRANSPORT_NOT_SENT)
        self.assertEqual(calls, 0); self.assertEqual(writer.frames, [])

    async def test_adapter_uses_current_caller_scope_without_a_second_send(self):
        existing = CeoIngressClient()
        adapter = DirectNativeResultClient("/fixture/ceo-ingress.sock", existing)
        with patch.object(existing, "send_frame", new=AsyncMock(side_effect=RuntimeError("lost"))) as send:
            with self.assertRaises(RuntimeError):
                await adapter.request(self.body, principal_scope="b" * 64)
        self.assertEqual(send.await_count, 1)
        frame = send.await_args.args[1]
        self.assertEqual(frame["principal_scope"], "b" * 64)
        self.assertEqual(frame["operation"], "result")

    async def test_old_frame_retains_its_original_parser(self):
        # The new duplicate-key check is schema-specific; this pins unchanged
        # historical behavior rather than silently widening a generic parser.
        result, _, calls = await self.exchange(b'{"ok":true,"result":{"x":1,"x":2}}\n',
                                                frame={"schema": "historical"})
        self.assertEqual(result.transport, TRANSPORT_SENT_OK)
        self.assertEqual(result.result, {"x": 2})
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
