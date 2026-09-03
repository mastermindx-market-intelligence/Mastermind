from __future__ import annotations

import asyncio
import dataclasses
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from control_plane.executive_dialogue_observation import (
    RESPONSE_SCHEMA,
    response_bytes,
    reduce_dialogue_observation,
)
from control_plane.executive_runtime import AttemptStatus, WorkerStatus
from integrations.slack_agent_dialogue.executive_observation_client import (
    ExecutiveDialogueObservationClient,
    ExecutiveObservationClientError,
)
from tests.test_company_dialogue_runtime_binding import parent as valid_parent
from tests.test_executive_dialogue_observation import _active, _terminal
from control_plane.executive_dialogue_observation import DialogueObservationFacts


THREAD_TS = "1787961600.000001"


@pytest.fixture
def socket_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="mmx-observation-", dir="/tmp") as raw:
        yield Path(raw)


async def _one_shot_server(
    path: Path,
    response: bytes | None,
    *,
    delay: float = 0.0,
    calls: list[bytes] | None = None,
) -> asyncio.AbstractServer:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        raw = await reader.readline()
        if calls is not None:
            calls.append(raw)
        if delay:
            await asyncio.sleep(delay)
        if response is not None:
            writer.write(response)
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_unix_server(handler, path=str(path))


def test_client_constructs_existing_active_types_from_strict_response(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        parent = valid_parent()
        response = reduce_dialogue_observation(
            parent=parent,
            facts=DialogueObservationFacts(active=(_active(parent),)),
        )
        socket_path = socket_root / "active.sock"
        calls: list[bytes] = []
        server = await _one_shot_server(
            socket_path, response_bytes(response), calls=calls
        )
        try:
            resolved = await ExecutiveDialogueObservationClient(
                socket_path,
                timeout_seconds=1.0,
            ).resolve(parent=parent, thread_ts=THREAD_TS)
        finally:
            server.close()
            await server.wait_closed()

        assert resolved.state == "RESOLVED"
        assert resolved.mode == "ACTIVE_CURRENT_WORKER"
        assert resolved.current_worker is not None
        assert resolved.current_worker.attempt_status is AttemptStatus.RUNNING
        assert resolved.current_worker.worker_status is WorkerStatus.BUSY
        assert resolved.actor is not None
        assert resolved.actor.runtime_binding == resolved.current_worker.runtime_binding
        assert resolved.delegation_identity.job_id == "JOB-101"
        assert resolved.delegation_identity.operation_key == parent["operation_key"]
        assert resolved.thread_ts == THREAD_TS
        assert len(calls) == 1
        request = json.loads(calls[0])
        assert set(request) == {"schema", "parent"}
        assert request["parent"] == parent
        assert resolved.current_worker.runtime_binding.native_handle is None
        assert resolved.current_worker.runtime_binding.account_label is None

    asyncio.run(scenario())


def test_client_constructs_terminal_candidate_receipt_and_binding(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        parent = valid_parent()
        response = reduce_dialogue_observation(
            parent=parent,
            facts=DialogueObservationFacts(terminal=(_terminal(parent),)),
        )
        socket_path = socket_root / "terminal.sock"
        server = await _one_shot_server(socket_path, response_bytes(response))
        try:
            resolved = await ExecutiveDialogueObservationClient(
                socket_path,
                timeout_seconds=1.0,
            ).resolve(parent=parent, thread_ts=THREAD_TS)
        finally:
            server.close()
            await server.wait_closed()

        assert resolved.mode == "TERMINAL_RESULT"
        assert resolved.terminal_candidate == _terminal(parent).candidate
        assert dataclasses.asdict(resolved.terminal_projection_receipt) == (
            dataclasses.asdict(_terminal(parent).projection_receipt)
        )
        assert resolved.terminal_binding is not None
        assert resolved.terminal_binding.operation_key == parent["operation_key"]
        assert resolved.current_worker is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (b'{"schema":"x","schema":"y"}\n', "RESPONSE_REFUSED"),
        (b'{"schema":NaN}\n', "RESPONSE_REFUSED"),
        (b"\xff\n", "RESPONSE_REFUSED"),
        (b"{}\n{}\n", "RESPONSE_REFUSED"),
    ],
)
def test_client_rejects_malformed_response_without_retry(
    socket_root: Path, response: bytes, code: str
) -> None:
    async def scenario() -> None:
        socket_path = socket_root / "malformed.sock"
        calls: list[bytes] = []
        server = await _one_shot_server(socket_path, response, calls=calls)
        try:
            with pytest.raises(ExecutiveObservationClientError) as exc:
                await ExecutiveDialogueObservationClient(
                    socket_path,
                    timeout_seconds=0.2,
                ).resolve(parent=valid_parent(), thread_ts=THREAD_TS)
            assert exc.value.code == code
            assert len(calls) == 1
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_client_timeout_is_one_zero_effect_attempt_with_no_retry(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        socket_path = socket_root / "timeout.sock"
        calls: list[bytes] = []
        server = await _one_shot_server(
            socket_path,
            response_bytes(
                {
                    "schema": RESPONSE_SCHEMA,
                    "state": "UNAVAILABLE",
                    "reason": "PARENT_NOT_EXECUTIVE_BOUND",
                }
            ),
            delay=0.2,
            calls=calls,
        )
        try:
            with pytest.raises(ExecutiveObservationClientError) as exc:
                await ExecutiveDialogueObservationClient(
                    socket_path,
                    timeout_seconds=0.02,
                ).resolve(parent=valid_parent(), thread_ts=THREAD_TS)
            assert exc.value.code == "TRANSPORT_UNAVAILABLE"
            assert len(calls) == 1
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("HELD", "HELD_ZERO_EFFECT"),
        ("UNKNOWN", "UNKNOWN_ZERO_EFFECT"),
        ("UNAVAILABLE", "UNAVAILABLE_ZERO_EFFECT"),
        ("CONFLICT", "CONFLICT_ZERO_EFFECT"),
        ("REFUSED", "REFUSED_ZERO_EFFECT"),
    ],
)
def test_client_preserves_every_closed_nonresolved_state(
    socket_root: Path,
    state: str,
    code: str,
) -> None:
    async def scenario() -> None:
        socket_path = socket_root / f"{state.lower()}.sock"
        server = await _one_shot_server(
            socket_path,
            response_bytes(
                {
                    "schema": RESPONSE_SCHEMA,
                    "state": state,
                    "reason": "ZERO_EFFECT_TEST",
                }
            ),
        )
        try:
            with pytest.raises(ExecutiveObservationClientError) as exc:
                await ExecutiveDialogueObservationClient(
                    socket_path,
                    timeout_seconds=1.0,
                ).resolve(parent=valid_parent(), thread_ts=THREAD_TS)
            assert exc.value.code == code
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_client_rejects_changed_identity_join_and_nonresolved_payload_leak(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        parent = valid_parent()
        response = reduce_dialogue_observation(
            parent=parent,
            facts=DialogueObservationFacts(active=(_active(parent),)),
        )
        changed = json.loads(json.dumps(response))
        changed["observation"]["job_id"] = "JOB-999"
        socket_path = socket_root / "changed.sock"
        server = await _one_shot_server(
            socket_path,
            json.dumps(changed, separators=(",", ":")).encode() + b"\n",
        )
        try:
            with pytest.raises(ExecutiveObservationClientError) as exc:
                await ExecutiveDialogueObservationClient(
                    socket_path,
                    timeout_seconds=1.0,
                ).resolve(parent=parent, thread_ts=THREAD_TS)
            assert exc.value.code == "RESPONSE_REFUSED"
        finally:
            server.close()
            await server.wait_closed()

        leaked = {
            "schema": RESPONSE_SCHEMA,
            "state": "HELD",
            "reason": "PARENT_NOT_EXECUTIVE_BOUND",
            "job_id": "JOB-999",
        }
        socket_path = socket_root / "leaked.sock"
        server = await _one_shot_server(
            socket_path,
            json.dumps(leaked, separators=(",", ":")).encode() + b"\n",
        )
        try:
            with pytest.raises(ExecutiveObservationClientError) as exc:
                await ExecutiveDialogueObservationClient(
                    socket_path,
                    timeout_seconds=1.0,
                ).resolve(parent=parent, thread_ts=THREAD_TS)
            assert exc.value.code == "RESPONSE_REFUSED"
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())
