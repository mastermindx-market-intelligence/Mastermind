from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest

from common.executive_hot_state_contract import semantic_snapshot_hash


STATE_REQUEST_SCHEMA = "mastermind.executive_ceo_ingress_state.v1"
HOT_STATE_SCHEMA = "mastermind.executive_hot_state.v1"


def _module():
    try:
        return importlib.import_module(
            "integrations.slack_executive.executive_state_reader"
        )
    except ModuleNotFoundError:
        pytest.fail("production CeoIngress state reader is not implemented")


def _valid_state() -> dict[str, object]:
    state: dict[str, object] = {
        "schema": HOT_STATE_SCHEMA,
        "generated_at": "2026-08-27T06:30:00Z",
        "snapshot_hash": "",
        "grounding": {
            "mastermind_sha": None,
            "macro_sha": None,
            "boot_packet_schema": None,
        },
        "service": {
            "service_state": "AWAITING_CANARY",
            "ceo_admission": "UNARMED",
        },
        "generic_operator_mutations": "BLOCKED_AWAITING_CANARY",
        "runtime": {
            "projection_state": "OK",
            "jobs": {"total": 0, "by_status": {
                "QUEUED": 0, "RUNNING": 0, "CHECKPOINTED": 0,
                "RATE_LIMITED": 0, "FAILED": 0, "LOST": 0,
                "CANCEL_REQUESTED": 0, "COMPLETED": 0, "CANCELLED": 0,
            }},
            "attempts": {"total": 0, "by_status": {
                "CLAIMED": 0, "RUNNING": 0, "CHECKPOINTED": 0,
                "CANCEL_REQUESTED": 0, "RATE_LIMITED": 0, "FAILED": 0,
                "LOST": 0, "COMPLETED": 0, "CANCELLED": 0,
            }},
            "workers": {"total": 0, "by_status": {
                "AVAILABLE": 0, "BUSY": 0, "DRAINING": 0,
                "RATE_LIMITED": 0, "OFFLINE": 0, "ERROR": 0,
            }},
        },
        "degraded": ["GROUNDING_UNAVAILABLE"],
        "do_not_submit": True,
    }
    state["snapshot_hash"] = semantic_snapshot_hash(state)
    return state


def test_reader_sends_exact_no_input_state_frame_and_returns_validated_result(tmp_path: Path):
    state_reader = _module()
    socket_path = tmp_path / "ceo-ingress.sock"
    observed_frames: list[dict[str, object]] = []
    expected = _valid_state()

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


def test_reader_refuses_invalid_hot_state_result(tmp_path: Path):
    state_reader = _module()
    socket_path = tmp_path / "ceo-ingress.sock"

    async def exercise():
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            await reader.readline()
            writer.write(
                json.dumps(
                    {"ok": True, "result": {"schema": HOT_STATE_SCHEMA, "fixture": "invalid"}},
                    separators=(",", ":"),
                ).encode("utf-8")
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
            with pytest.raises(RuntimeError, match="EXECUTIVE_STATE_INVALID_RESPONSE"):
                await reader.read_state()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_reader_refuses_oversize_response_without_waiting_for_unbounded_line(tmp_path: Path):
    state_reader = _module()
    socket_path = tmp_path / "ceo-ingress.sock"

    async def exercise():
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            await reader.readline()
            writer.write(b"x" * 40000)
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_unix_server(handle, path=str(socket_path))
        try:
            reader = state_reader.CeoIngressStateReader(
                socket_path=socket_path,
                timeout_seconds=1.0,
            )
            with pytest.raises(RuntimeError, match="EXECUTIVE_STATE_INVALID_RESPONSE"):
                await reader.read_state()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_reader_requires_absolute_socket_path():
    state_reader = _module()
    with pytest.raises(ValueError, match="absolute"):
        state_reader.CeoIngressStateReader(socket_path="relative.sock")
