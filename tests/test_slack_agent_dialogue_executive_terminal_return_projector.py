from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import inspect
import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

from control_plane import ceo_intent, ceo_request
from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    JobStatus,
    Runtime,
)
from control_plane.executive_service import (
    ExecutiveControlService,
    send_control_request,
)
from control_plane.executive_terminal_return import (
    TerminalReturnCandidate,
    reduce_terminal_return,
)
from control_plane.executive_workspace import prepare_credentialless_clone
from control_plane.session_targets import RuntimeBinding, load_session_targets
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.slack_agent_dialogue.contract_v2 import (
    PARENT_SCHEMA_V2,
    build_parent_v2,
    parse_message_frame_v2,
    render_parent_v2,
)
from integrations.slack_agent_dialogue.engine import (
    DialogueEngine,
    DialoguePolicy,
    SlackMessage,
)
from integrations.slack_agent_dialogue.engine_v2 import (
    DialogueContextV2,
    DialogueEngineV2,
)
from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
    ExecutiveTerminalReturnProjector,
    TerminalReturnProjectionError,
)
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.persisted_wake_carrier import (
    PersistedWakeCarrier,
)
from integrations.slack_agent_dialogue.service import (
    AgentDialogueService,
    DialogueServiceError,
    EXACT_SEND_PROTOCOL,
    ServiceConfig,
)
from integrations.slack_agent_dialogue.turn_observer import (
    DialogueTurnObserver,
    ObservationOutcome,
)
from integrations.slack_agent_dialogue.turn_watcher import TurnRoutingFacts
from tests.test_executive_wake_persisted_dispatch import (
    _Dispatcher,
    _POLICY,
)
from tests.test_executive_service import _config as _executive_config
from tests.test_executive_supervisor import FakeInspector, _supervisor
from tests.test_executive_terminal_return import _PlannerSealedWorkerAdapter
from tests.test_slack_agent_dialogue_engine_v2 import ExactV2AuthorityPolicy
from tests.test_slack_agent_dialogue_service import wait_for_service_start


REPO = "mastermindx-market-intelligence/Mastermind"
BOT = "U0RELAY001"
SOL = "U0BRETDUAS2"
CHANNEL = "C0DIALOGUE1"
WORKSPACE = "T0DIALOGUE1"


def _candidate() -> TerminalReturnCandidate:
    terminal_digest = "a" * 64
    return TerminalReturnCandidate(
        job_id="JOB-002",
        attempt_id="ATT-002",
        worker_id="worker-a",
        root_job_id="JOB-001",
        role="work",
        operation_key="exec-job-002",
        session_ref="asd-session-exec-job-002",
        runtime_status="COMPLETED",
        result_status="RESULT",
        result_digest="b" * 64,
        terminal_digest=terminal_digest,
        terminal_at="2026-08-30T10:00:00Z",
        message_key=f"asd-exec-result-{terminal_digest}",
        summary="The commissioned work completed with canonical evidence.",
        review_verdict=None,
        dialogue_source=ExecutiveDialogueSource(
            schema_version="mastermind.executive_dialogue_source/v1",
            work_ref="WS:WORKER-PRESENCE",
            commission_ref={
                "repository": REPO,
                "commit": "c" * 40,
                "path": "research/commission.md",
                "content_sha256": "d" * 64,
            },
            watch_mode="turn_watch_v1",
        ),
    )


def _binding(candidate: TerminalReturnCandidate) -> DialogueBinding:
    attempt_ref = {
        "kind": "worker_attempt",
        "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id,
        "worker_id": candidate.worker_id,
    }
    return DialogueBinding(
        actor_ref=attempt_ref,
        work_ref="WS:WORKER-PRESENCE",
        commission_ref={
            "repository": REPO,
            "commit": "c" * 40,
            "path": "research/commission.md",
            "content_sha256": "d" * 64,
        },
        session_ref=candidate.session_ref,
        operation_key=candidate.operation_key,
        watch_mode="turn_watch_v1",
        applies_to={
            "kind": "executive_attempt",
            "job_id": candidate.job_id,
            "attempt_id": candidate.attempt_id,
            "worker_id": candidate.worker_id,
        },
        thread_ts="1787961600.000001",
        allowed_message_types=("RESULT",),
    )


class _Resolver:
    def __init__(
        self,
        binding: DialogueBinding,
        *,
        expected_candidate: TerminalReturnCandidate | None = None,
    ) -> None:
        self.binding = binding
        self.expected_candidate = expected_candidate or _candidate()
        self.calls = 0

    def resolve(self, candidate: TerminalReturnCandidate) -> DialogueBinding:
        self.calls += 1
        assert candidate == self.expected_candidate
        return self.binding


def _bind_response(candidate: TerminalReturnCandidate) -> dict[str, object]:
    return {
        "ok": True,
        "result": {
            "attestation": "mastermind.agent_dialogue.relay_parent/v1",
            "thread_ts": _binding(candidate).thread_ts,
            "parent_author_user_id": BOT,
            "parent_fingerprint": "e" * 64,
        },
    }


async def _projected_message(candidate: TerminalReturnCandidate) -> dict[str, object]:
    """Exercise the real projector while replacing only the AF_UNIX boundary."""

    captured: dict[str, object] = {}

    async def service_call(_socket_path: Path, request, **kwargs):
        before_write = kwargs.pop("before_write", None)
        assert kwargs == {}
        if request["operation"] == "bind_or_verify_relay_parent_thread":
            assert before_write is None
            return _bind_response(candidate)
        assert request["operation"] == "send_message"
        if before_write is not None:
            marked = before_write()
            if inspect.isawaitable(marked):
                await marked
        message = request["args"]["message"]
        captured["message"] = message
        return {
            "ok": True,
            "result": {
                "action": "POSTED",
                "message_key": message["message_key"],
                "fingerprint": message["fingerprint"],
                "message_ts": "1787961600.000002",
                "duplicate_timestamps": [],
            },
        }

    projector = ExecutiveTerminalReturnProjector(
        _Resolver(_binding(candidate), expected_candidate=candidate),
        socket_path=Path("/tmp/mastermind-terminal-return.sock"),
        service_call=service_call,
    )
    await projector.project(candidate)
    message = captured.get("message")
    assert isinstance(message, dict)
    return message


def test_projector_candidate_keys_resolution_and_verifies_parent_before_send() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        resolver = _Resolver(_binding(candidate))
        operations: list[str] = []

        async def service_call(_socket_path: Path, request):
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "POSTED",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            resolver,
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        receipt = await projector.project(candidate)

        assert resolver.calls == 1
        assert receipt.action == "POSTED"
        assert operations == ["bind_or_verify_relay_parent_thread", "send_message"]

    asyncio.run(scenario())


def test_projector_requires_relay_parent_attestation_before_send() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        operations: list[str] = []

        async def service_call(_socket_path: Path, request):
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return {
                    "ok": True,
                    "result": {
                        "attestation": "mastermind.agent_dialogue.relay_parent/v1",
                        "thread_ts": _binding(candidate).thread_ts,
                        "parent_author_user_id": BOT,
                        "parent_fingerprint": "e" * 64,
                    },
                }
            assert operation == "send_message"
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "POSTED",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        receipt = await projector.project(candidate)

        assert receipt.action == "POSTED"
        assert operations == ["bind_or_verify_relay_parent_thread", "send_message"]

    asyncio.run(scenario())


def test_projector_builds_one_deterministic_result_for_the_exact_trusted_binding() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        resolver = _Resolver(_binding(candidate))
        calls: list[tuple[Path, dict[str, object]]] = []

        async def service_call(socket_path: Path, request):
            calls.append((socket_path, request))
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "POSTED",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            resolver,
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        receipt = await projector.project(candidate)

        assert resolver.calls == 1
        assert receipt.action == "POSTED"
        assert receipt.message_key == candidate.message_key
        assert len(calls) == 2
        socket_path, request = calls[1]
        assert socket_path == Path("/tmp/mastermind-terminal-return.sock")
        assert request["version"] == "mastermind.agent_dialogue_control.v2"
        assert request["operation"] == "send_message"
        assert request["args"]["send_protocol"] == EXACT_SEND_PROTOCOL
        assert request["args"]["thread_ts"] == _binding(candidate).thread_ts
        message = request["args"]["message"]
        assert message["message_type"] == "RESULT"
        assert message["message_key"] == candidate.message_key
        assert message["actor_ref"] == _binding(candidate).actor_ref
        assert message["applies_to"] == _binding(candidate).applies_to
        assert message["body"] == {
            "status": "PASS",
            "result": candidate.summary,
        }
        assert message["created_at"] == candidate.terminal_at

    asyncio.run(scenario())


def test_projector_parent_refusal_happens_before_exact_send_callback() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        callback_calls = 0

        async def before_write() -> None:
            nonlocal callback_calls
            callback_calls += 1

        async def service_call(_socket_path, request, **kwargs):
            assert request["operation"] == "bind_or_verify_relay_parent_thread"
            assert kwargs == {}
            return {
                "ok": False,
                "error": {"code": "THREAD_CONTEXT_MISMATCH"},
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.project(candidate, before_write=before_write)
        assert raised.value.code == "DIALOGUE_BINDING_UNAVAILABLE"
        assert callback_calls == 0

    asyncio.run(scenario())


def test_projector_exact_duplicate_returns_without_attempt_callback() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        callback_calls = 0

        async def before_write() -> None:
            nonlocal callback_calls
            callback_calls += 1

        async def service_call(_socket_path, request, **kwargs):
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                assert kwargs == {}
                return _bind_response(candidate)
            assert request["operation"] == "send_message"
            assert request["args"]["send_protocol"] == EXACT_SEND_PROTOCOL
            assert kwargs == {"before_write": before_write}
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "DUPLICATE",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        receipt = await projector.project(candidate, before_write=before_write)
        assert receipt.action == "DUPLICATE"
        assert callback_calls == 0

    asyncio.run(scenario())


def test_projector_preserves_exact_safe_review_result_at_900_characters() -> None:
    """Deleting raw-summary pass-through or adding verdict prose must fail."""

    summary = "r" * 900
    candidate = dataclasses.replace(
        _candidate(),
        role="review",
        summary=summary,
        review_verdict="approve",
    )

    message = asyncio.run(_projected_message(candidate))

    assert message["body"] == {"status": "PASS", "result": summary}
    assert len(message["body"]["result"]) == 900


@pytest.mark.parametrize(
    "summary",
    [
        pytest.param("x" * 901, id="901-characters"),
        pytest.param("x" * 8192, id="8192-characters"),
    ],
)
def test_projector_uses_digest_synopsis_for_oversize_runtime_summary(
    summary: str,
) -> None:
    """A 901+ character Runtime summary must be represented, never sliced."""

    candidate = dataclasses.replace(_candidate(), summary=summary)
    expected_summary_digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    expected = (
        '{"evidence_ref":"result-envelope-sha256:'
        + str(candidate.result_digest)
        + '","role":"work","status":"RESULT","summary_sha256":"'
        + expected_summary_digest
        + '"}'
    )

    first = asyncio.run(_projected_message(candidate))
    second = asyncio.run(_projected_message(candidate))

    assert first["body"] == {"status": "PASS", "result": expected}
    assert second == first
    assert first["evidence_refs"] == []
    assert len(expected) <= 900
    assert summary not in expected


@pytest.mark.parametrize(
    "summary",
    [
        pytest.param(" leading whitespace", id="leading-whitespace"),
        pytest.param("trailing whitespace ", id="trailing-whitespace"),
        pytest.param("line one\nline two", id="control-newline"),
        pytest.param("unsafe\u2028separator", id="unicode-line-separator"),
        pytest.param("notify <@U12345678>", id="slack-mention"),
        pytest.param("xoxb-1234567890ABCDEF", id="secret-shaped"),
    ],
)
def test_projector_replaces_unsafe_runtime_summary_with_nonleaking_digest_synopsis(
    summary: str,
) -> None:
    """Unsafe raw text must neither cross Agent Dialogue nor become invented prose."""

    candidate = dataclasses.replace(_candidate(), summary=summary)
    expected_summary_digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    expected = (
        '{"evidence_ref":"result-envelope-sha256:'
        + str(candidate.result_digest)
        + '","role":"work","status":"RESULT","summary_sha256":"'
        + expected_summary_digest
        + '"}'
    )

    message = asyncio.run(_projected_message(candidate))

    assert message["body"] == {"status": "PASS", "result": expected}
    assert message["evidence_refs"] == []
    assert summary not in expected


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("operation_key", "exec-foreign"),
        ("session_ref", "asd-session-exec-foreign"),
        (
            "actor_ref",
            {
                "kind": "worker_attempt",
                "job_id": "JOB-002",
                "attempt_id": "ATT-foreign",
                "worker_id": "worker-a",
            },
        ),
    ],
)
def test_projector_refuses_binding_drift_before_any_service_call(
    field: str, replacement: object
) -> None:
    async def scenario() -> None:
        candidate = _candidate()
        binding = _binding(candidate)
        values = dict(binding.__dict__)
        values[field] = replacement
        calls = 0

        async def service_call(_socket_path, _request):
            nonlocal calls
            calls += 1
            raise AssertionError("service call must not occur")

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(DialogueBinding(**values)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector(candidate)
        assert raised.value.code == "DIALOGUE_BINDING_UNAVAILABLE"
        assert calls == 0

    asyncio.run(scenario())


def test_projector_refuses_malformed_binding_collections_as_a_closed_error() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        binding = _binding(candidate)
        values = dict(binding.__dict__)
        values["allowed_message_types"] = (["RESULT"],)
        projector = ExecutiveTerminalReturnProjector(
            _Resolver(DialogueBinding(**values)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=lambda _path, _request: (_ for _ in ()).throw(
                AssertionError("service call must not occur")
            ),
        )

        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector(candidate)
        assert raised.value.code == "DIALOGUE_BINDING_UNAVAILABLE"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "receipt_change",
    [
        {"action": []},
        {"duplicate_timestamps": [{}]},
        {"duplicate_timestamps": ["1787961600.000003"]},
    ],
)
def test_projector_refuses_malformed_service_receipts_as_closed_errors(
    receipt_change: dict[str, object],
) -> None:
    async def scenario() -> None:
        candidate = _candidate()

        async def service_call(_socket_path, request):
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            message = request["args"]["message"]
            result = {
                "action": "POSTED",
                "message_key": message["message_key"],
                "fingerprint": message["fingerprint"],
                "message_ts": "1787961600.000002",
                "duplicate_timestamps": [],
            }
            result.update(receipt_change)
            return {"ok": True, "result": result}

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

    asyncio.run(scenario())


def test_projector_preserves_post_dispatch_effect_unknown() -> None:
    async def scenario() -> None:
        candidate = _candidate()

        async def service_call(_socket_path, request):
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            raise DialogueServiceError("SEND_EFFECT_UNKNOWN")

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

    asyncio.run(scenario())


def test_projector_reconciles_effect_unknown_by_read_without_a_second_send() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        operations: list[str] = []
        sent_message: dict[str, object] | None = None

        async def service_call(_socket_path, request):
            nonlocal sent_message
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if operation == "send_message":
                sent_message = request["args"]["message"]
                raise DialogueServiceError("SEND_EFFECT_UNKNOWN")
            assert operation == "read_thread"
            assert sent_message is not None
            return {
                "ok": True,
                "result": {
                    "thread_ts": _binding(candidate).thread_ts,
                    "messages": [
                        {
                            "message": sent_message,
                            "primary_ts": "1787961600.000002",
                            "duplicate_timestamps": [],
                        }
                    ],
                    "historical_messages": [],
                    "ineligible_count": 0,
                    "mutated_count": 0,
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.project(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

        recovered = await projector.reconcile(candidate)

        assert recovered is not None
        assert recovered.action == "RECOVERED"
        assert recovered.message_key == candidate.message_key
        assert operations == [
            "bind_or_verify_relay_parent_thread",
            "send_message",
            "bind_or_verify_relay_parent_thread",
            "read_thread",
        ]

    asyncio.run(scenario())


def test_projector_reconcile_refuses_noncanonical_duplicate_timestamps() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        projected_message: dict[str, object] | None = None

        async def service_call(_socket_path, request):
            nonlocal projected_message
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if request["operation"] == "send_message":
                projected_message = request["args"]["message"]
                raise DialogueServiceError("SEND_EFFECT_UNKNOWN")
            assert projected_message is not None
            return {
                "ok": True,
                "result": {
                    "thread_ts": _binding(candidate).thread_ts,
                    "messages": [
                        {
                            "message": projected_message,
                            "primary_ts": "1787961600.000002",
                            "duplicate_timestamps": ["1787961600.000003"],
                        }
                    ],
                    "historical_messages": [],
                    "ineligible_count": 0,
                    "mutated_count": 0,
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError):
            await projector.project(candidate)
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.reconcile(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

    asyncio.run(scenario())


def test_projector_callback_preserves_the_none_return_contract() -> None:
    async def scenario() -> None:
        candidate = _candidate()

        async def service_call(_socket_path, request):
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "DUPLICATE",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        assert await projector(candidate) is None

    asyncio.run(scenario())


class _ServicePlannerSealedWorkerAdapter(_PlannerSealedWorkerAdapter):
    """Adapt the SEALED_WORKER fixture to a service-owned real Git base."""

    def __init__(self, inspector: FakeInspector, *, runtime: Runtime) -> None:
        super().__init__(
            inspector,
            root_job_id="deferred-until-runtime-admission",
        )
        self._runtime = runtime

    async def start(self, spec):
        ref = await super().start(spec)
        # FakeAdapter's generic fixture uses b*40.  This vertical instead
        # binds launch evidence to CeoIngress's exact reviewed Git base.
        self.ref = dataclasses.replace(ref, base_sha=spec.expected_base_sha)
        return self.ref

    async def collect_result(self, ref):
        assert self.spec is not None
        job = self._runtime.jobs.get_job(self.spec.job_id)
        assert job is not None and job.root_job_id
        self.root_job_id = job.root_job_id
        receipt = await super().collect_result(ref)
        exact_base = self.spec.expected_base_sha
        return dataclasses.replace(
            receipt,
            result=dataclasses.replace(
                receipt.result,
                git_manifest={"base_sha": exact_base, "head_sha": exact_base},
            ),
        )


class _FixedGrounding:
    def __init__(self, value: dict[str, str]) -> None:
        self.value = dict(value)
        self.calls = 0

    def observe(self) -> dict[str, str]:
        self.calls += 1
        return dict(self.value)


async def _ceo_ingress_round_trip(
    path: Path,
    frame: dict[str, object],
) -> dict[str, object]:
    reader, writer = await asyncio.open_unix_connection(str(path))
    try:
        writer.write(
            json.dumps(
                frame,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
            + b"\n"
        )
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), timeout=2.0)
        assert raw
        response = json.loads(raw)
        assert isinstance(response, dict)
        return response
    finally:
        writer.close()
        await writer.wait_closed()


async def _wait_for_terminal_projection(
    service: ExecutiveControlService,
    planner_id: str,
    *,
    timeout: float = 3.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        runtime = service.runtime
        assert runtime is not None
        planner = runtime.jobs.get_job(planner_id)
        diagnostic = service._terminal_return_last_diagnostic
        if (
            planner is not None
            and planner.status is JobStatus.COMPLETED
            and diagnostic == "terminal-return:APPLIED"
            and not service._dispatch_tasks
        ):
            return
        if diagnostic is not None and diagnostic != "terminal-return:APPLIED":
            pytest.fail(f"terminal projection refused: {diagnostic}")
        if service._dispatch_errors:
            pytest.fail(f"dispatch failed: {service._dispatch_errors!r}")
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(
                f"timed out: job={planner!r} diagnostic={diagnostic!r} "
                f"tasks={list(service._dispatch_tasks)}"
            )
        await asyncio.sleep(0.01)


def test_terminal_candidate_posts_one_result_and_one_persisted_wake_across_replay(
    tmp_path: Path,
) -> None:
    async def scenario(socket_root: Path) -> None:
        relay_path = socket_root / "dialogue.sock"
        ingress_path = socket_root / "ceo-ingress.sock"
        config = _executive_config(
            tmp_path,
            socket_root=socket_root,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=3600.0,
            terminal_return_armed=True,
            terminal_return_socket_path=relay_path,
        )
        grounding_value = {
            "mastermind_sha": config.proof_base_sha,
            "macro_sha": "2" * 40,
            "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
        }
        grounding = _FixedGrounding(grounding_value)
        request_ref = "req-r2-continuous-vertical-20260901-001"
        intent_id = ceo_request.automated_intent_id(request_ref)
        branch = ceo_request.derive_branch(intent_id)
        clone = prepare_credentialless_clone(
            config.proof_source_repository,
            config.proof_workspace_root,
            job_id=intent_id,
            base_sha=config.proof_base_sha,
            branch=branch,
            shared_gid=config.proof_shared_gid,
        )
        assert Path(clone.workspace_path) == config.proof_workspace_root / intent_id

        source = {
            "schema_version": "mastermind.executive_dialogue_source/v1",
            "work_ref": "WS:EXECUTIVE-OS",
            "commission_ref": {
                "repository": REPO,
                "commit": config.proof_base_sha,
                "path": "docs/commissions/executive-terminal-return.md",
                "content_sha256": "d" * 64,
            },
            "watch_mode": "turn_watch_v1",
        }
        ingress_frame = {
            "schema": ceo_ingress.SUBMIT_SCHEMA_V2,
            "request_ref": request_ref,
            "observed_grounding": grounding_value,
            "request": {
                "objective": "Prove one continuous Executive terminal return.",
                "department": "executive-infrastructure",
                "priority": 9,
                "execution_profile": "research_only",
                "workstream": source["work_ref"],
                "attempt_limit": 1,
            },
            "dialogue_source": source,
        }

        client = InMemorySlackClient(relay_bot_user_id=BOT)
        policy = DialoguePolicy(
            workspace_id=WORKSPACE,
            channel_id=CHANNEL,
            relay_bot_user_id=BOT,
            allowed_sol_user_ids=(SOL,),
            allowed_parent_user_ids=(SOL,),
            poll_interval_seconds=0,
            method_timeout_seconds=1,
        )
        authority = ExactV2AuthorityPolicy()

        def new_relay() -> AgentDialogueService:
            return AgentDialogueService(
                ServiceConfig(
                    socket_path=relay_path,
                    allowed_peer_uids=(os.geteuid(),),
                    request_timeout_seconds=1,
                ),
                DialogueEngine(policy, client, authority_policy=authority),
                engine_v2=DialogueEngineV2(
                    policy,
                    client,
                    authority_policy=authority,
                ),
            )

        supervisors: list[
            tuple[Runtime, _ServicePlannerSealedWorkerAdapter]
        ] = []

        def new_executive() -> ExecutiveControlService:
            def supervisor_factory(runtime: Runtime):
                adapter = _ServicePlannerSealedWorkerAdapter(
                    FakeInspector(),
                    runtime=runtime,
                )
                supervisors.append((runtime, adapter))
                return _supervisor(runtime, tmp_path, adapter)

            return ExecutiveControlService(
                config,
                supervisor_factory=supervisor_factory,
                autonomy_guard=lambda: None,
                ceo_ingress_socket_path=ingress_path,
                ceo_ingress_peer_uid=os.geteuid(),
                ceo_ingress_grounding_provider=grounding,
                ceo_ingress_armed=True,
            )

        relay = new_relay()
        relay_task = asyncio.create_task(relay.serve_forever())
        await wait_for_service_start(relay_task, relay_path)
        executive = new_executive()
        restarted: ExecutiveControlService | None = None
        try:
            await executive.start()
            registered = await send_control_request(
                executive.socket_path,
                "register-worker",
                {},
            )
            assert registered["ok"] is True

            submitted = await _ceo_ingress_round_trip(
                ingress_path,
                ingress_frame,
            )
            assert submitted["ok"] is True
            result = submitted["result"]
            assert isinstance(result, dict)
            assert result["duplicate"] is False
            root_id = str(result["job_id"])
            runtime = executive.runtime
            assert runtime is not None
            root = runtime.jobs.get_job(root_id)
            assert root is not None
            creation = runtime.store.find_event_by_command_id(
                ceo_intent.command_id_for(intent_id)
            )
            assert creation is not None
            assert creation["payload"]["provenance"]["dialogue_source"] == source

            created = await send_control_request(
                executive.socket_path,
                "run-coo-cycle",
                {"root_job_id": root_id},
            )
            assert created["ok"] is True
            assert created["result"]["action"] == "PLANNER_CREATED"
            planner_id = created["result"]["selected_job_id"]
            planner = runtime.jobs.get_job(planner_id)
            assert planner is not None
            identity = derive_delegation_identity(planner)

            parent = build_parent_v2(
                {
                    "schema": PARENT_SCHEMA_V2,
                    "work_ref": source["work_ref"],
                    "commission_ref": source["commission_ref"],
                    "session_ref": identity.session_ref,
                    "operation_key": identity.operation_key,
                    "watch_mode": source["watch_mode"],
                    "allowed_sol_user_ids": [SOL],
                    "created_at": "2026-08-10T23:59:59Z",
                }
            )
            parent_ts = "1787961600.000001"
            client.add_parent(
                SlackMessage(
                    ts=parent_ts,
                    author_user_id=BOT,
                    text=render_parent_v2(parent),
                )
            )

            dispatched = await send_control_request(
                executive.socket_path,
                "run-coo-cycle",
                {"root_job_id": root_id},
            )
            assert dispatched["ok"] is True, dispatched
            assert dispatched["result"]["action"] == "DISPATCHED"
            attempt_id = dispatched["result"]["receipt"]["attempt"][
                "attempt_id"
            ]
            await _wait_for_terminal_projection(executive, planner_id)

            material = runtime.validated_role_completion(
                planner_id,
                expected_attempt_id=attempt_id,
            )
            candidate = reduce_terminal_return(material=material)
            assert material.execution_mode == "SEALED_WORKER"
            assert material.attempt.status is AttemptStatus.COMPLETED
            assert material.terminal_receipt["result_evidence"][
                "schema_version"
            ] == "mastermind.sealed_worker_result_evidence/v1"
            assert candidate.root_job_id == root_id
            assert candidate.operation_key == identity.operation_key
            assert candidate.session_ref == identity.session_ref
            assert candidate.dialogue_source is not None
            assert candidate.dialogue_source.to_dict() == source
            assert supervisors[0][1].direct_validation_calls == []

            terminal_events = [
                event.event_type
                for event in runtime.events.list_events(
                    attempt_id=attempt_id
                )
                if event.event_type.startswith("EXECUTIVE_TERMINAL_RETURN_")
            ]
            assert terminal_events == [
                "EXECUTIVE_TERMINAL_RETURN_PREPARED",
                "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
                "EXECUTIVE_TERMINAL_RETURN_APPLIED",
            ]
            assert client.post_call_count == 1
            replies = client.thread_messages[parent_ts]
            assert len(replies) == 1
            message = parse_message_frame_v2(replies[0].text)
            assert message["message_type"] == "RESULT"
            assert message["message_key"] == candidate.message_key
            actor_ref = {
                "kind": "worker_attempt",
                "job_id": planner_id,
                "attempt_id": attempt_id,
                "worker_id": material.attempt.worker_id,
            }
            applies_to = {
                "kind": "executive_attempt",
                "job_id": planner_id,
                "attempt_id": attempt_id,
                "worker_id": material.attempt.worker_id,
            }
            assert message["actor_ref"] == actor_ref
            assert message["applies_to"] == applies_to

            context = DialogueContextV2(
                work_ref=str(source["work_ref"]),
                commission_ref=dict(source["commission_ref"]),
                session_ref=identity.session_ref,
                operation_key=identity.operation_key,
                watch_mode=str(source["watch_mode"]),
                actor_ref=actor_ref,
                applies_to=applies_to,
            )
            routing = TurnRoutingFacts(
                bound_operation_key=identity.operation_key,
                bound_commission_fingerprint=str(parent["fingerprint"]),
                root_job_id=root_id,
                routing_workstream=None,
                source_workstream=str(source["work_ref"]),
                ceo_target_bound=True,
                coo_target_bound=False,
            )
            runtime_binding = RuntimeBinding(
                session_alias="EXECUTIVE-CEO-A",
                binding_id="bind-terminalreturn01",
                binding_generation=1,
                native_handle="thread-terminal-return",
                account_label="codex-terminal-return",
                reasoning_surface="codex",
            )
            registry = load_session_targets()
            target = dataclasses.replace(
                registry.targets["EXECUTIVE-CEO-A"],
                reasoning_surface="codex",
                wake_transport="codex-app-server",
                allowed_transports=("codex-app-server",),
                target_enabled=True,
            )
            registry = dataclasses.replace(
                registry,
                production_armed=True,
                targets={**registry.targets, target.session_alias: target},
            ).with_root_job_bindings(
                {root_id: {"ceo": "EXECUTIVE-CEO-A"}}
            )

            wake_root = tmp_path / "wake-runtime"
            wake_runtime = Runtime.at(wake_root)
            wake_repo = WakeLedgerRepository(wake_runtime)
            dispatcher = _Dispatcher(repo=wake_repo)
            carrier = PersistedWakeCarrier(
                repository=wake_repo,
                dispatchers=WakeDispatcherRegistry(
                    {"codex-app-server": dispatcher}
                ),
                current_binding_for=lambda _route: runtime_binding,
                retry_policy=_POLICY,
            )
            observer = DialogueTurnObserver(
                policy=policy,
                client=client,
                registry=registry,
                wake_carrier=carrier,
                binding_for=(
                    lambda seat: runtime_binding if seat == "ceo" else None
                ),
                emitted_at=lambda: "2026-08-11T00:00:02Z",
            )
            wake = await observer.reconcile_once(
                context=context,
                routing=routing,
            )
            assert wake.outcome is ObservationOutcome.WAKE_SUBMITTED
            assert wake.obligation is not None
            obligation_id = wake.obligation.obligation_id
            assert dispatcher.nudge_calls == 1

            # Restart the Executive service over the same Runtime. Startup
            # replay must consume APPLIED and never re-enter Agent Relay.
            await executive.close()
            restarted = new_executive()
            await restarted.start()
            assert restarted._terminal_return_last_diagnostic == (
                "terminal-return:ALREADY_APPLIED"
            )
            duplicate = await _ceo_ingress_round_trip(
                ingress_path,
                ingress_frame,
            )
            assert duplicate["ok"] is True
            duplicate_result = duplicate["result"]
            assert isinstance(duplicate_result, dict)
            assert duplicate_result["duplicate"] is True
            assert duplicate_result["job_id"] == root_id
            assert client.post_call_count == 1
            assert len(client.thread_messages[parent_ts]) == 1
            restarted_runtime = restarted.runtime
            assert restarted_runtime is not None
            assert len(
                [
                    job
                    for job in restarted_runtime.jobs.list_jobs()
                    if job.parent_job_id is None
                ]
            ) == 1

            # Restart the Wake Runtime/repository/carrier/dispatcher/observer.
            # Its delivered obligation must suppress a second provider nudge.
            restarted_wake_runtime = Runtime.at(wake_root)
            restarted_wake_repo = WakeLedgerRepository(
                restarted_wake_runtime
            )
            restarted_dispatcher = _Dispatcher(repo=restarted_wake_repo)
            restarted_carrier = PersistedWakeCarrier(
                repository=restarted_wake_repo,
                dispatchers=WakeDispatcherRegistry(
                    {"codex-app-server": restarted_dispatcher}
                ),
                current_binding_for=lambda _route: runtime_binding,
                retry_policy=_POLICY,
            )
            restarted_observer = DialogueTurnObserver(
                policy=policy,
                client=client,
                registry=registry,
                wake_carrier=restarted_carrier,
                binding_for=(
                    lambda seat: runtime_binding if seat == "ceo" else None
                ),
                emitted_at=lambda: "2026-08-11T00:00:03Z",
            )
            replay = await restarted_observer.reconcile_once(
                context=context,
                routing=routing,
            )
            assert replay.outcome is ObservationOutcome.DUPLICATE_SUPPRESSED
            assert replay.obligation is not None
            assert replay.obligation.obligation_id == obligation_id
            assert restarted_dispatcher.nudge_calls == 0
            assert [
                item.record.phase
                for item in restarted_wake_repo.list_records(obligation_id)
            ] == [
                LedgerPhase.WAKE_REQUESTED,
                LedgerPhase.DELIVERY_ATTEMPT,
                LedgerPhase.DELIVERED,
            ]
            assert restarted_wake_runtime.jobs.list_jobs() == []
            assert restarted_wake_runtime.attempts.list_attempts() == []
            assert restarted_wake_runtime.workers.list_workers() == []
        finally:
            if restarted is not None:
                await restarted.close()
            else:
                await executive.close()
            relay_task.cancel()
            await asyncio.gather(relay_task, return_exceptions=True)

    with tempfile.TemporaryDirectory(prefix="mmx-r2-", dir="/tmp") as raw:
        socket_root = Path(raw).resolve()
        assert stat.S_IMODE(socket_root.lstat().st_mode) == 0o700
        asyncio.run(scenario(socket_root))
