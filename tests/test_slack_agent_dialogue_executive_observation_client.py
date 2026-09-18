from __future__ import annotations

import asyncio
import dataclasses
import json
import tempfile
from collections.abc import Iterator
from contextvars import ContextVar
from pathlib import Path

import pytest

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation,
    DialogueSourceMessage,
    DialogueSourceSnapshot,
)

from control_plane.executive_dialogue_observation import (
    DialogueCandidateReference,
    RECONCILE_WAKE,
    RESPONSE_SCHEMA,
    response_bytes,
    reduce_dialogue_observation,
    terminal_projection_receipt_reference,
    wake_response_bytes,
)
from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from control_plane.executive_runtime import AttemptStatus, WorkerStatus
from control_plane.session_targets import route_digest
from control_plane.wake_events import mint_obligation
from integrations.slack_agent_dialogue.executive_observation_client import (
    ExecutiveDialogueObservationClient,
    ExecutiveObservationClientError,
)
from integrations.slack_agent_dialogue.turn_observer import WakeCarrierState
from tests.test_company_dialogue_runtime_binding import parent as valid_parent
from tests.test_executive_dialogue_observation import (
    _active,
    _candidate_reference,
    _terminal,
    _wake_pair,
)
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
            thread_ts=THREAD_TS,
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
        assert set(request) == {"schema", "request_id", "parent"}
        assert request["request_id"].startswith("observation-")
        assert request["parent"] == parent
        assert resolved.candidate.to_dict() == _candidate_reference(parent)
        assert resolved.target_bindings["ceo"].native_handle is None
        assert resolved.target_bindings["ceo"].account_label is None
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
            thread_ts=THREAD_TS,
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
        expected = _terminal(parent).candidate
        terminal = resolved.terminal_candidate
        assert terminal is not None
        for field in (
            "root_job_id",
            "job_id",
            "attempt_id",
            "worker_id",
            "runtime_status",
            "result_status",
            "result_envelope_digest",
            "terminal_evidence_digest",
            "artifact_receipt_digest",
            "validation_receipt_digest",
            "effective_grant_digest",
            "terminal_at",
            "message_key",
        ):
            assert getattr(terminal, field) == getattr(expected, field)
        assert terminal.summary == ""
        assert terminal.role == "worker"
        assert terminal.review_verdict is None
        assert terminal.dialogue_source == expected.dialogue_source
        assert resolved.terminal_projection_receipt == (
            terminal_projection_receipt_reference(
                _terminal(parent).projection_receipt
            )
        )
        assert resolved.terminal_binding is not None
        assert resolved.terminal_binding.operation_key == parent["operation_key"]
        assert resolved.current_worker is None
        assert resolved.candidate.mode == "TERMINAL_RESULT"
        assert set(resolved.target_bindings) == {"coo", "ceo"}

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


def test_client_refuses_noncanonical_refused_observation_state(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        socket_path = socket_root / "noncanonical-refused.sock"
        server = await _one_shot_server(
            socket_path,
            response_bytes(
                {
                    "schema": RESPONSE_SCHEMA,
                    "state": "REFUSED",
                    "reason": "REQUEST_REFUSED",
                }
            ),
        )
        try:
            with pytest.raises(
                ExecutiveObservationClientError,
                match="RESPONSE_REFUSED",
            ):
                await ExecutiveDialogueObservationClient(socket_path).resolve(
                    parent=valid_parent(),
                    thread_ts=THREAD_TS,
                )
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
            thread_ts=THREAD_TS,
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


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("MISSING", WakeCarrierState.MISSING),
        ("RECORDED", WakeCarrierState.RECORDED),
        ("EFFECT_UNKNOWN", WakeCarrierState.EFFECT_UNKNOWN),
    ],
)
def test_coordination_client_reconciles_with_only_parent_obligation_and_proposed_route(
    socket_root: Path,
    state: str,
    expected: WakeCarrierState,
) -> None:
    async def scenario() -> None:
        socket_path = socket_root / f"wake-{state.lower()}.sock"
        calls: list[bytes] = []
        server = await _one_shot_server(
            socket_path,
            wake_response_bytes(state=state, reason="FIXED_RESULT"),
            calls=calls,
        )
        context = ContextVar("wake_request_context", default=None)
        context.set(
            {
                "parent": valid_parent(),
                "thread_ts": THREAD_TS,
                "candidate": DialogueCandidateReference(**_candidate_reference()),
            }
        )
        client = ExecutiveDialogueObservationClient(
            socket_path,
            timeout_seconds=1.0,
        )
        client.bind_wake_context(context)
        obligation, route = _wake_pair()
        try:
            assert await client.reconcile(obligation, route) is expected
        finally:
            server.close()
            await server.wait_closed()

        assert len(calls) == 1
        request = json.loads(calls[0])
        assert set(request) == {
            "schema",
            "operation",
            "parent",
            "thread_ts",
            "candidate",
            "obligation",
            "route",
        }
        assert request["operation"] == RECONCILE_WAKE
        assert request["obligation"]["obligation_id"] != obligation.obligation_id
        assert request["obligation"]["root_job_id"] == (
            request["candidate"]["root_job_id"]
        )
        assert request["obligation"]["job_id"] == request["candidate"]["job_id"]
        assert request["obligation"]["attempt_id"] == (
            request["candidate"]["attempt_id"]
        )
        assert request["obligation"]["evidence_refs"] == [
            request["obligation"]["source_ref"],
            request["candidate"]["job_id"],
            request["candidate"]["attempt_id"],
            request["candidate"]["root_job_id"],
        ]
        assert request["route"]["obligation_id"] == (
            request["obligation"]["obligation_id"]
        )
        encoded = json.dumps(request, sort_keys=True)
        for forbidden in (
            "native_handle",
            "account_label",
            "provider_home",
        ):
            assert forbidden not in encoded

    asyncio.run(scenario())


def test_wake_source_identity_is_exact_replay_stable_and_candidate_bound(
    socket_root: Path,
) -> None:
    parent = valid_parent()
    candidate = DialogueCandidateReference(**_candidate_reference())
    legacy_obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "a" * 64,
        declared_target_seat="ceo",
        root_job_id=candidate.root_job_id,
        source_workstream=parent["work_ref"],
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:01Z",
    )
    _fixture_obligation, route = _wake_pair()
    context = ContextVar("wake_identity_context", default=None)
    context.set({"parent": parent, "thread_ts": THREAD_TS, "candidate": candidate})
    client = ExecutiveDialogueObservationClient(socket_root / "identity.sock")
    client.bind_wake_context(context)

    first = client._wake_request(
        operation=RECONCILE_WAKE,
        obligation=legacy_obligation,
        route=route,
    )
    replay = client._wake_request(
        operation=RECONCILE_WAKE,
        obligation=legacy_obligation,
        route=route,
    )
    assert replay == first

    changed_candidate = dataclasses.replace(candidate, evidence_digest="f" * 64)
    context.set(
        {"parent": parent, "thread_ts": THREAD_TS, "candidate": changed_candidate}
    )
    changed = client._wake_request(
        operation=RECONCILE_WAKE,
        obligation=legacy_obligation,
        route=route,
    )

    later_attempt = dataclasses.replace(candidate, attempt_id="ATT-" + "3" * 32)
    context.set(
        {"parent": parent, "thread_ts": THREAD_TS, "candidate": later_attempt}
    )
    later = client._wake_request(
        operation=RECONCILE_WAKE,
        obligation=legacy_obligation,
        route=route,
    )

    other_attention = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "b" * 64,
        declared_target_seat="ceo",
        root_job_id=candidate.root_job_id,
        source_workstream=parent["work_ref"],
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:01Z",
    )
    other_route = dataclasses.replace(
        route,
        obligation_id=other_attention.obligation_id,
        route_digest=route_digest(
            obligation_id=other_attention.obligation_id,
            destination=route.destination_digest,
            policy_digest=route.policy_digest,
        ),
    )
    context.set({"parent": parent, "thread_ts": THREAD_TS, "candidate": candidate})
    conflicting_message = client._wake_request(
        operation=RECONCILE_WAKE,
        obligation=other_attention,
        route=other_route,
    )

    identities = {
        item["obligation"]["obligation_id"]
        for item in (first, changed, later, conflicting_message)
    }
    assert len(identities) == 4


def test_source_pending_response_is_typed_and_delayed_ack_echoes_exact_source(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        socket_path = socket_root / "delayed-ack.sock"
        calls: list[dict] = []
        source = DialogueSourceObservation(
            workspace_id="T0BRD2AQXQV", channel_id="C0BSBM78V1N",
            thread_ts=THREAD_TS, predecessor_message_key="asd-result-00000001",
            predecessor_message_fingerprint="a" * 64,
        )

        async def handler(reader, writer):
            request = json.loads(await reader.readline())
            calls.append(request)
            if request["operation"] == "RECONCILE_DIALOGUE_SOURCES":
                response = {
                    "schema": "mastermind.dialogue_source_reconcile_response/v1",
                    "state": "ACK_REQUIRED", "reason": "DELIVERED_ACK_PENDING",
                    "source_observation": source.to_dict(),
                }
            else:
                response = {
                    "schema": "mastermind.dialogue_delayed_ack_response/v1",
                    "state": "RECORDED", "reason": "ACK_RECORDED",
                }
            writer.write(json.dumps(response, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        parent = valid_parent()
        context = ContextVar("delayed_ack_context", default=None)
        context.set({
            "parent": parent, "thread_ts": THREAD_TS,
            "candidate": DialogueCandidateReference(**_candidate_reference()),
        })
        client = ExecutiveDialogueObservationClient(socket_path)
        client.bind_wake_context(context)
        snapshot = DialogueSourceSnapshot(
            workspace_id=source.workspace_id, channel_id=source.channel_id,
            thread_ts=source.thread_ts, parent_fingerprint=parent["fingerprint"],
            operation_key=parent["operation_key"], messages=(),
        )
        try:
            pending = await client.reconcile_dialogue_sources(snapshot)
            assert pending["source_observation"] is source or (
                pending["source_observation"] == source
            )
            recorded = await client.reconcile_delayed_ack(
                pending["source_observation"]
            )
        finally:
            server.close()
            await server.wait_closed()
        assert recorded["state"] == "RECORDED"
        assert [call["operation"] for call in calls] == [
            "RECONCILE_DIALOGUE_SOURCES", "RECONCILE_WAKE_ACK",
        ]
        assert calls[1]["source_observation"] == source.to_dict()
        assert calls[1]["parent"] == parent

    asyncio.run(scenario())


@pytest.mark.parametrize("variant", ["missing", "null", "extra", "source_missing"])
def test_source_pending_conditional_shape_refuses_before_ack_request(
    socket_root: Path, variant: str,
) -> None:
    async def scenario() -> None:
        path = socket_root / f"source-shape-{variant}.sock"
        source = {
            "workspace_id": "T0BRD2AQXQV", "channel_id": "C0BSBM78V1N",
            "thread_ts": THREAD_TS, "predecessor_message_key": "asd-result-00000001",
            "predecessor_message_fingerprint": "a" * 64,
        }
        response = {
            "schema": "mastermind.dialogue_source_reconcile_response/v1",
            "state": "ACK_REQUIRED", "reason": "DELIVERED_ACK_PENDING",
            "source_observation": source,
        }
        if variant == "missing":
            response.pop("source_observation")
        elif variant == "null":
            response["source_observation"] = None
        elif variant == "extra":
            response.update(state="RECORDED", reason="SOURCE_ALREADY_RESOLVED")
        else:
            response["source_observation"] = dict(source)
            response["source_observation"].pop("channel_id")
        calls = []
        server = await _one_shot_server(
            path,
            json.dumps(response, sort_keys=True, separators=(",", ":")).encode() + b"\n",
            calls=calls,
        )
        parent = valid_parent()
        context = ContextVar(f"shape_{variant}", default=None)
        context.set({
            "parent": parent, "thread_ts": THREAD_TS,
            "candidate": DialogueCandidateReference(**_candidate_reference()),
        })
        client = ExecutiveDialogueObservationClient(path)
        client.bind_wake_context(context)
        try:
            with pytest.raises(ExecutiveObservationClientError, match="RESPONSE_REFUSED"):
                await client.reconcile_dialogue_sources(DialogueSourceSnapshot(
                    workspace_id="T0BRD2AQXQV", channel_id="C0BSBM78V1N",
                    thread_ts=THREAD_TS, parent_fingerprint=parent["fingerprint"],
                    operation_key=parent["operation_key"], messages=(),
                ))
        finally:
            server.close()
            await server.wait_closed()
        assert len(calls) == 1
        assert json.loads(calls[0])["operation"] == "RECONCILE_DIALOGUE_SOURCES"

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["timeout", "eof", "malformed"])
def test_coordination_submit_is_one_attempt_and_ambiguous_after_write(
    socket_root: Path,
    failure: str,
) -> None:
    async def scenario() -> None:
        socket_path = socket_root / f"wake-submit-{failure}.sock"
        calls: list[bytes] = []
        response = {
            "timeout": wake_response_bytes(state="RECORDED", reason="WAKE_RECORDED"),
            "eof": None,
            "malformed": b'{"schema":"bad"}\n',
        }[failure]
        server = await _one_shot_server(
            socket_path,
            response,
            delay=0.2 if failure == "timeout" else 0.0,
            calls=calls,
        )
        context = ContextVar("wake_submit_context", default=None)
        context.set(
            {
                "parent": valid_parent(),
                "thread_ts": THREAD_TS,
                "candidate": DialogueCandidateReference(**_candidate_reference()),
            }
        )
        client = ExecutiveDialogueObservationClient(
            socket_path,
            timeout_seconds=0.02 if failure == "timeout" else 1.0,
        )
        client.bind_wake_context(context)
        obligation, route = _wake_pair()
        try:
            with pytest.raises(WakeEffectUnknownError):
                await client.submit(obligation, route)
            assert len(calls) == 1
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_coordination_submit_connection_failure_is_known_pre_submit(
    socket_root: Path,
) -> None:
    async def scenario() -> None:
        context = ContextVar("wake_pre_submit_context", default=None)
        context.set(
            {
                "parent": valid_parent(),
                "thread_ts": THREAD_TS,
                "candidate": DialogueCandidateReference(**_candidate_reference()),
            }
        )
        client = ExecutiveDialogueObservationClient(
            socket_root / "absent.sock",
            timeout_seconds=0.1,
        )
        client.bind_wake_context(context)
        obligation, route = _wake_pair()
        with pytest.raises(WakePreSubmitError):
            await client.submit(obligation, route)

    asyncio.run(scenario())


@pytest.mark.parametrize("mismatch", ["thread", "oversized"])
def test_source_reconcile_refuses_context_drift_and_oversize_before_socket_io(
    socket_root: Path,
    mismatch: str,
) -> None:
    async def scenario() -> None:
        parent = valid_parent()
        context = ContextVar("source_reconcile_context", default=None)
        context.set(
            {
                "parent": parent,
                "thread_ts": THREAD_TS,
                "candidate": DialogueCandidateReference(**_candidate_reference()),
            }
        )
        client = ExecutiveDialogueObservationClient(socket_root / "never-opened.sock")
        client.bind_wake_context(context)
        messages = ()
        thread_ts = "1787961600.000002" if mismatch == "thread" else THREAD_TS
        if mismatch == "oversized":
            messages = tuple(
                DialogueSourceMessage.create(
                    {"message_key": f"source-{index:02d}", "padding": "x" * 2000}
                )
                for index in range(40)
            )
        snapshot = DialogueSourceSnapshot(
            workspace_id="T0BRD2AQXQV",
            channel_id="C0BSBM78V1N",
            thread_ts=thread_ts,
            parent_fingerprint=parent["fingerprint"],
            operation_key=parent["operation_key"],
            messages=messages,
        )
        with pytest.raises(ExecutiveObservationClientError, match="RESPONSE_REFUSED"):
            await client.reconcile_dialogue_sources(snapshot)

    asyncio.run(scenario())
