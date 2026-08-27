from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest


STATE_REQUEST_SCHEMA = "mastermind.executive_ceo_ingress_state.v1"
HOT_STATE_SCHEMA = "mastermind.executive_hot_state.v1"


def _module():
    try:
        return importlib.import_module(
            "integrations.slack_executive.executive_state_reader"
        )
    except ModuleNotFoundError:
        pytest.fail("production CeoIngress state reader is not implemented")


def test_reader_sends_exact_no_input_state_frame_and_returns_result(tmp_path: Path):
    state_reader = _module()
    socket_path = tmp_path / "ceo-ingress.sock"
    observed_frames: list[dict[str, object]] = []
    expected = {"schema": HOT_STATE_SCHEMA, "fixture": "current"}

    async def exercise():
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            raw = await reader.readline()
            observed_frames.append(json.loads(raw))
            writer.write(
                json.dumps({"ok": True, "result": expected}, separators=(",", ":")).encode(
                    "utf-8"
                )
                + b"\n"
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_unix_server(handle, path=str(socket_path))
        try:
            reader = state_reader.CeoIngressStateReader(
                socket_path=socket_path,
                timeout_seconds=1.0,
            )
            return await reader.read_state()
        finally:
            server.close()
            await server.wait_closed()

    result = asyncio.run(exercise())
    assert result == expected
    assert observed_frames == [{"schema": STATE_REQUEST_SCHEMA}]
