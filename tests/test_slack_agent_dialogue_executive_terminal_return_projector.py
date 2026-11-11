from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import inspect
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

import pytest

from common.commission_ref import CommissionRef
from control_plane import ceo_intent, ceo_request
from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    JobStatus,
    Runtime,
    StateConflict,
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
from control_plane.session_targets import route_obligation
from control_plane.wake_dispatcher import WakePreSubmitError
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_events import mint_obligation
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.slack_agent_dialogue.contract_v2 import (
    PARENT_SCHEMA_V2,
    build_message_v2,
    build_parent_v2,
    parse_message_frame_v2,
    render_message_v2,
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
    RuntimeTerminalReturnBindingResolver,
    TerminalReturnProjectionError,
    _build_message,
)
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.persisted_wake_carrier import (
    PersistedWakeCarrier,
)
from integrations.slack_agent_dialogue.service import (
    AgentDialogueService,
    CONTROL_VERSION_V2,
    DialogueServiceError,
    EXACT_SEND_PROTOCOL,
    ServiceConfig,
    call_service,
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
from tests.test_executive_os_phase1fc import (
    _complete_ohf_role,
    _cycle_through_completed_work,
    _review_body,
)
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
        result_envelope_digest="b" * 64,
        terminal_evidence_digest=terminal_digest,
        artifact_receipt_digest="c" * 64,
        validation_receipt_digest="d" * 64,
        effective_grant_digest="e" * 64,
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


def test_runtime_dialogue_source_refuses_hostile_commission_ref_subclass() -> None:
    class HostileCommissionRef(CommissionRef):
        def to_dict(self) -> dict[str, str]:
            return {
                **super().to_dict(),
                "content_sha256": "f" * 64,
            }

    with pytest.raises(StateConflict, match="commission_ref is invalid"):
        ExecutiveDialogueSource(
            schema_version="mastermind.executive_dialogue_source/v1",
            work_ref="WS:WORKER-PRESENCE",
            commission_ref=HostileCommissionRef(
                repository=REPO,
                commit="c" * 40,
                path="research/commission.md",
                content_sha256="d" * 64,
            ),
            watch_mode="turn_watch_v1",
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


def _read_response(
    candidate: TerminalReturnCandidate,
    messages: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "ok": True,
        "result": {
            "thread_ts": _binding(candidate).thread_ts,
            "messages": messages,
            "historical_messages": [],
            "ineligible_count": 0,
            "mutated_count": 0,
        },
    }


def _empty_read_response(candidate: TerminalReturnCandidate) -> dict[str, object]:
    return _read_response(candidate, [])


async def _projected_message(candidate: TerminalReturnCandidate) -> dict[str, object]:
    """Exercise the real projector while replacing only the AF_UNIX boundary."""

    captured: dict[str, object] = {}

    async def service_call(_socket_path: Path, request, **kwargs):
        before_write = kwargs.pop("before_write", None)
        assert kwargs == {}
        if request["operation"] == "bind_or_verify_relay_parent_thread":
            assert before_write is None
            return _bind_response(candidate)
        if request["operation"] == "read_thread":
            assert before_write is None
            return _empty_read_response(candidate)
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
                "thread_ts": _binding(candidate).thread_ts,
                "parent_author_user_id": BOT,
                "parent_fingerprint": "e" * 64,
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


def _canonical_synopsis(
    candidate: TerminalReturnCandidate,
    *,
    outcome: str,
    include_summary: bool,
) -> str:
    value: dict[str, str] = {
        "schema": "mastermind.executive_terminal_result_synopsis/v1",
        "role": candidate.role,
        "outcome": outcome,
        "result_envelope_digest": candidate.result_envelope_digest,
        "terminal_evidence_digest": candidate.terminal_evidence_digest,
        "artifact_receipt_digest": candidate.artifact_receipt_digest,
        "validation_receipt_digest": candidate.validation_receipt_digest,
        "effective_grant_digest": candidate.effective_grant_digest,
    }
    if include_summary:
        value["summary"] = candidate.summary
    else:
        value["summary_sha256"] = hashlib.sha256(
            candidate.summary.encode("utf-8")
        ).hexdigest()
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def test_projector_always_projects_the_five_digest_canonical_result_synopsis() -> None:
    candidate = _candidate()

    message = asyncio.run(_projected_message(candidate))

    assert message["message_type"] == "RESULT"
    assert message["body"] == {
        "status": "PASS",
        "result": _canonical_synopsis(
            candidate,
            outcome="PASS",
            include_summary=True,
        ),
    }
    assert message["requires_response"] is False


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
            if operation == "read_thread":
                return _empty_read_response(candidate)
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "POSTED",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
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
        assert receipt.thread_ts == _binding(candidate).thread_ts
        assert receipt.parent_author_user_id == BOT
        assert receipt.parent_fingerprint == "e" * 64
        assert operations == [
            "bind_or_verify_relay_parent_thread",
            "read_thread",
            "send_message",
        ]

    asyncio.run(scenario())


def test_projector_refuses_a_send_receipt_attested_to_a_different_parent() -> None:
    async def scenario() -> None:
        candidate = _candidate()

        async def service_call(_socket_path: Path, request):
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if request["operation"] == "read_thread":
                return _empty_read_response(candidate)
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "POSTED",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "f" * 64,
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as refused:
            await projector.project(candidate)
        assert refused.value.code == "EFFECT_UNKNOWN"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field",
    [
        "result_envelope_digest",
        "terminal_evidence_digest",
        "artifact_receipt_digest",
        "validation_receipt_digest",
        "effective_grant_digest",
    ],
)
def test_projector_binds_each_terminal_digest_into_the_message_fingerprint(
    field: str,
) -> None:
    candidate = _candidate()
    changed = dataclasses.replace(
        candidate,
        **{field: "f" * 64},
        message_key=(
            f"asd-exec-result-{'f' * 64}"
            if field == "terminal_evidence_digest"
            else candidate.message_key
        ),
    )

    baseline = asyncio.run(_projected_message(candidate))
    projected = asyncio.run(_projected_message(changed))

    assert projected["fingerprint"] != baseline["fingerprint"]
    assert projected["body"] != baseline["body"]


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
            if operation == "read_thread":
                return _empty_read_response(candidate)
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
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        receipt = await projector.project(candidate)

        assert receipt.action == "POSTED"
        assert operations == [
            "bind_or_verify_relay_parent_thread",
            "read_thread",
            "send_message",
        ]

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
            if request["operation"] == "read_thread":
                return _empty_read_response(candidate)
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "POSTED",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
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
        assert len(calls) == 3
        assert calls[1][1]["operation"] == "read_thread"
        socket_path, request = calls[2]
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
            "result": _canonical_synopsis(
                candidate,
                outcome="PASS",
                include_summary=True,
            ),
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
            if request["operation"] == "read_thread":
                assert kwargs == {}
                return _empty_read_response(candidate)
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
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
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


@pytest.mark.parametrize(
    "verdict,expected_status",
    [
        pytest.param("approve", "PASS", id="approve-pass"),
        pytest.param("reject", "FAIL", id="reject-fail"),
    ],
)
def test_projector_preserves_exact_review_outcome_at_900_characters(
    verdict: str,
    expected_status: str,
) -> None:
    """Completion is RESULT; the canonical verdict alone selects PASS or FAIL."""

    summary = "r" * 900
    candidate = dataclasses.replace(
        _candidate(),
        role="review",
        summary=summary,
        review_verdict=verdict,
    )

    message = asyncio.run(_projected_message(candidate))

    assert message["body"] == {
        "status": expected_status,
        "result": _canonical_synopsis(
            candidate,
            outcome=expected_status,
            include_summary=False,
        ),
    }
    assert summary not in message["body"]["result"]


@pytest.mark.parametrize(
    "verdict",
    [
        pytest.param(None, id="missing"),
        pytest.param("", id="empty"),
        pytest.param("unknown", id="unknown"),
        pytest.param(1, id="integer"),
        pytest.param([], id="unhashable-list"),
    ],
)
def test_projector_refuses_noncanonical_review_verdict_before_relay_call(
    verdict: object,
) -> None:
    async def scenario() -> None:
        candidate = dataclasses.replace(
            _candidate(),
            role="review",
            review_verdict=verdict,  # type: ignore[arg-type]
        )
        service_calls = 0
        before_write_calls = 0

        async def service_call(*_args, **_kwargs):
            nonlocal service_calls
            service_calls += 1
            raise AssertionError("invalid review verdict reached Agent Relay")

        async def before_write() -> None:
            nonlocal before_write_calls
            before_write_calls += 1

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as refused:
            await projector.project(candidate, before_write=before_write)

        assert refused.value.code == "DIALOGUE_REFUSED"
        assert service_calls == 0
        assert before_write_calls == 0

    asyncio.run(scenario())


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
    expected = _canonical_synopsis(
        candidate,
        outcome="PASS",
        include_summary=False,
    )

    first = asyncio.run(_projected_message(candidate))
    second = asyncio.run(_projected_message(candidate))

    assert first["body"] == {"status": "PASS", "result": expected}
    assert second == first
    assert first["evidence_refs"] == []
    assert len(expected) <= 900
    assert summary not in expected


@pytest.mark.parametrize(
    "summary,include_summary",
    [
        pytest.param(" leading whitespace", True, id="leading-whitespace"),
        pytest.param("trailing whitespace ", True, id="trailing-whitespace"),
        pytest.param("line one\nline two", True, id="control-newline"),
        pytest.param("unsafe\u2028separator", True, id="unicode-line-separator"),
        pytest.param("notify <@U12345678>", False, id="slack-mention"),
        pytest.param("xoxb-1234567890ABCDEF", False, id="secret-shaped"),
    ],
)
def test_projector_replaces_unsafe_runtime_summary_with_nonleaking_digest_synopsis(
    summary: str, include_summary: bool,
) -> None:
    """Unsafe raw text must neither cross Agent Dialogue nor become invented prose."""

    candidate = dataclasses.replace(_candidate(), summary=summary)
    expected = _canonical_synopsis(
        candidate,
        outcome="PASS",
        include_summary=include_summary,
    )

    message = asyncio.run(_projected_message(candidate))

    assert message["body"] == {"status": "PASS", "result": expected}
    assert message["evidence_refs"] == []
    assert ("summary" in json.loads(expected)) is include_summary


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
            if request["operation"] == "read_thread":
                return _empty_read_response(candidate)
            message = request["args"]["message"]
            result = {
                "action": "POSTED",
                "message_key": message["message_key"],
                "fingerprint": message["fingerprint"],
                "message_ts": "1787961600.000002",
                "duplicate_timestamps": [],
                "thread_ts": _binding(candidate).thread_ts,
                "parent_author_user_id": BOT,
                "parent_fingerprint": "e" * 64,
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
            if request["operation"] == "read_thread":
                return _empty_read_response(candidate)
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


def test_projector_preserves_known_zero_transport_unavailability() -> None:
    async def scenario() -> None:
        candidate = _candidate()

        async def service_call(_socket_path, request):
            if request["operation"] == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if request["operation"] == "read_thread":
                return _empty_read_response(candidate)
            raise DialogueServiceError("TRANSPORT_UNAVAILABLE")

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.project(candidate)
        assert raised.value.code == "TRANSPORT_UNAVAILABLE"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "role,verdict,expected_status",
    [
        pytest.param("work", None, "PASS", id="work-pass"),
        pytest.param("review", "approve", "PASS", id="review-approve-pass"),
        pytest.param("review", "reject", "FAIL", id="review-reject-fail"),
    ],
)
def test_projector_reconciles_effect_unknown_by_read_without_a_second_send(
    role: str,
    verdict: str | None,
    expected_status: str,
) -> None:
    async def scenario() -> None:
        candidate = dataclasses.replace(
            _candidate(),
            role=role,
            review_verdict=verdict,
        )
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
            if sent_message is None:
                # Pre-send read: nothing has been committed yet.
                return _empty_read_response(candidate)
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
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.project(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

        # Restart-equivalent: a fresh projector instance must recover the
        # exact previously-sent RESULT by read, never issue a second send.
        restarted_projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        recovered = await restarted_projector.reconcile(candidate)

        assert recovered is not None
        assert recovered.action == "RECOVERED"
        assert recovered.message_key == candidate.message_key
        assert sent_message is not None
        assert sent_message["message_type"] == "RESULT"
        assert sent_message["body"]["status"] == expected_status
        assert recovered.fingerprint == sent_message["fingerprint"]
        assert recovered.thread_ts == _binding(candidate).thread_ts
        assert recovered.parent_author_user_id == BOT
        assert recovered.parent_fingerprint == "e" * 64
        assert operations == [
            "bind_or_verify_relay_parent_thread",
            "read_thread",
            "send_message",
            "bind_or_verify_relay_parent_thread",
            "read_thread",
        ]

    asyncio.run(scenario())


def test_projector_does_not_reconcile_stale_pass_for_rejecting_review() -> None:
    async def scenario() -> None:
        candidate = dataclasses.replace(
            _candidate(),
            role="review",
            review_verdict="reject",
        )
        stale_pass = await _projected_message(
            dataclasses.replace(candidate, review_verdict="approve")
        )
        operations: list[str] = []

        async def service_call(_socket_path, request):
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            assert operation == "read_thread"
            return {
                "ok": True,
                "result": {
                    "thread_ts": _binding(candidate).thread_ts,
                    "messages": [
                        {
                            "message": stale_pass,
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
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        with pytest.raises(TerminalReturnProjectionError) as refused:
            await projector.reconcile(candidate)

        assert refused.value.code == "EFFECT_UNKNOWN"
        assert operations == ["bind_or_verify_relay_parent_thread", "read_thread"]

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
            if projected_message is None:
                return _empty_read_response(candidate)
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
            if request["operation"] == "read_thread":
                return _empty_read_response(candidate)
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "DUPLICATE",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate)),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
        )
        assert await projector(candidate) is None

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Source-only repair: canonical C pull ``root_job_id`` locator + v1/v2
# restart/rollback reconciliation across the existing Dialogue owner.
# ---------------------------------------------------------------------------
# These tests pin the integration seam that the read-only GLM review flagged
# (F1 root locator absent; F2 version-pinning semantics unpinned) without
# inventing a second ledger, retry queue, or per-host version store.  They
# only exercise the existing projector, the existing engine predicate via the
# real ``send_message`` -> ``read_thread`` path, and the existing closed
# contract.  The repair carries the canonical candidate ``root_job_id`` into
# every new v2 RESULT synopsis while leaving v1 byte-identical and refusing
# tampered or version-mismatched persisted messages without any second send.


def test_projector_v2_result_carries_canonical_root_job_id_locator() -> None:
    """A new v2 message must carry the canonical candidate ``root_job_id``."""

    candidate = _candidate()

    message = asyncio.run(_projected_message_v2(candidate))
    payload = json.loads(message["body"]["result"])

    assert payload["root_job_id"] == candidate.root_job_id
    assert payload["root_job_id"] == "JOB-001"


def test_projector_v1_result_remains_byte_identical_after_root_locator_repair() -> None:
    """A v1 message must be byte-identical after the v2 repair."""

    candidate = _candidate()

    message = asyncio.run(_projected_message(candidate))
    payload = json.loads(message["body"]["result"])

    assert "root_job_id" not in payload
    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v1"
    assert message["body"]["result"] == _canonical_synopsis(
        candidate,
        outcome="PASS",
        include_summary=True,
    )


async def _projected_message_v2(candidate: TerminalReturnCandidate) -> dict[str, object]:
    """Variant of ``_projected_message`` that exercises the v2 synopsis path."""

    captured: dict[str, object] = {}

    async def service_call(_socket_path: Path, request, **kwargs):
        before_write = kwargs.pop("before_write", None)
        assert kwargs == {}
        if request["operation"] == "bind_or_verify_relay_parent_thread":
            assert before_write is None
            return _bind_response(candidate)
        if request["operation"] == "read_thread":
            assert before_write is None
            return _empty_read_response(candidate)
        assert request["operation"] == "send_message"
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
                "thread_ts": _binding(candidate).thread_ts,
                "parent_author_user_id": BOT,
                "parent_fingerprint": "e" * 64,
            },
        }

    projector = ExecutiveTerminalReturnProjector(
        _Resolver(_binding(candidate), expected_candidate=candidate),
        socket_path=Path("/tmp/mastermind-terminal-return.sock"),
        service_call=service_call,
        result_synopsis_version="v2",
    )
    await projector.project(candidate)
    message = captured.get("message")
    assert isinstance(message, dict)
    return message


def test_projector_v2_committed_rebuild_after_restart_is_byte_identical() -> None:
    """A v2 message committed in one process must rebuild byte-identical after restart."""

    async def scenario() -> None:
        candidate = _candidate()
        first_message = await _projected_message_v2(candidate)

        async def service_call(_socket_path: Path, request, **kwargs):
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
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
                },
            }

        # Simulated process restart: fresh projector, identical binding + version.
        restarted_projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        rebuilt_message = restarted_projector._resolve(candidate)[2]
        assert rebuilt_message["fingerprint"] == first_message["fingerprint"]
        assert rebuilt_message["body"] == first_message["body"]
        assert rebuilt_message["message_key"] == first_message["message_key"]

    asyncio.run(scenario())


def test_projector_v1_committed_rebuild_after_v2_host_rollback_is_byte_identical() -> None:
    """A v1-committed message must rebuild byte-identical after a v2 host rolls back to v1."""

    async def scenario() -> None:
        candidate = _candidate()
        v1_first = await _projected_message(candidate)

        # v2 host attempts to rebuild (cross-process restart): same binding.
        async def service_call(_socket_path: Path, request, **kwargs):
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
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
                },
            }

        v2_projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        v2_message = v2_projector._resolve(candidate)[2]
        # The v2 message carries root_job_id and has a different fingerprint.
        assert json.loads(v2_message["body"]["result"])["root_job_id"] == "JOB-001"
        assert v2_message["fingerprint"] != v1_first["fingerprint"]

        # Rollback: same projector, v1 synopsis.  Rebuild must be byte-identical
        # to the originally-committed v1 message.
        v1_projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v1",
        )
        v1_rebuilt = v1_projector._resolve(candidate)[2]
        assert v1_rebuilt["fingerprint"] == v1_first["fingerprint"]
        assert v1_rebuilt["body"] == v1_first["body"]
        assert "root_job_id" not in json.loads(v1_rebuilt["body"]["result"])

    asyncio.run(scenario())


def test_projector_v2_activation_and_reconcile_after_v1_committed_recovers_without_send() -> None:
    """F2: a v2 host after a v1-committed message must reuse it, never resend.

    The ``message_key`` derives only from the terminal evidence digest, so the
    legacy v1 wire already holds the key.  Validation is against every
    supported synopsis shape, so the persisted v1 message is recovered with
    its original fingerprint even though a new message would carry the v2
    synopsis.  Activation (``project``) must not submit the regenerated v2
    body against it.
    """

    async def scenario() -> None:
        candidate = _candidate()
        v1_committed = await _projected_message(candidate)
        operations: list[str] = []
        send_attempts = 0

        async def service_call(_socket_path: Path, request, **kwargs):
            nonlocal send_attempts
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if operation == "send_message":
                send_attempts += 1
                raise AssertionError(
                    "a validated committed message must never be re-sent"
                )
            assert operation == "read_thread"
            return _read_response(
                candidate,
                [
                    {
                        "message": v1_committed,
                        "primary_ts": "1787961600.000002",
                        "duplicate_timestamps": [],
                    }
                ],
            )

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        receipt = await projector.project(candidate)

        # Activation completes without a write: the committed v1 identity is
        # returned with its original fingerprint.
        assert receipt.action == "DUPLICATE"
        assert receipt.message_key == candidate.message_key
        assert receipt.fingerprint == v1_committed["fingerprint"]
        assert receipt.message_ts == "1787961600.000002"
        assert receipt.duplicate_timestamps == ()
        assert receipt.thread_ts == _binding(candidate).thread_ts

        # A restart-equivalent fresh projector running v2 reconciles the same
        # persisted v1 message to RECOVERED, still with the v1 fingerprint.
        restarted = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        recovered = await restarted.reconcile(candidate)
        assert recovered is not None
        assert recovered.action == "RECOVERED"
        assert recovered.message_key == candidate.message_key
        assert recovered.fingerprint == v1_committed["fingerprint"]
        assert recovered.message_ts == "1787961600.000002"

        # Zero sends across activation, restart, and reconcile.
        assert send_attempts == 0
        assert "send_message" not in operations
        assert operations == [
            "bind_or_verify_relay_parent_thread",
            "read_thread",
            "bind_or_verify_relay_parent_thread",
            "read_thread",
        ]

    asyncio.run(scenario())


def test_projector_v2_reconcile_after_v2_committed_recovers_same_message() -> None:
    """A v2 reconcile after a v2-committed message must RECOVER by read, not resend."""

    async def scenario() -> None:
        candidate = _candidate()
        v2_first = await _projected_message_v2(candidate)
        operations: list[str] = []

        async def service_call(_socket_path: Path, request, **kwargs):
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            assert operation == "read_thread"
            return {
                "ok": True,
                "result": {
                    "thread_ts": _binding(candidate).thread_ts,
                    "messages": [
                        {
                            "message": v2_first,
                            "primary_ts": "1787961600.000002",
                            "duplicate_timestamps": [],
                        }
                    ],
                    "historical_messages": [],
                    "ineligible_count": 0,
                    "mutated_count": 0,
                },
            }

        restarted = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        recovered = await restarted.reconcile(candidate)
        assert recovered is not None
        assert recovered.action == "RECOVERED"
        assert recovered.message_key == candidate.message_key
        assert recovered.fingerprint == v2_first["fingerprint"]
        # No second send.
        assert "send_message" not in operations

    asyncio.run(scenario())


def test_projector_v1_rebuild_after_v2_committed_keeps_v1_byte_identical() -> None:
    """A v1 rebuild after v2-committed must yield the byte-identical v1 body."""

    async def scenario() -> None:
        candidate = _candidate()
        v2_committed = await _projected_message_v2(candidate)

        async def service_call(_socket_path: Path, request, **kwargs):
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
                    "thread_ts": _binding(candidate).thread_ts,
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
                },
            }

        # After restart with v1 selected, _resolve must produce a message whose
        # body matches the canonical v1 synopsis.
        v1_projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v1",
        )
        rebuilt = v1_projector._resolve(candidate)[2]
        rebuilt_payload = json.loads(rebuilt["body"]["result"])
        assert "root_job_id" not in rebuilt_payload
        assert rebuilt_payload["schema"] == (
            "mastermind.executive_terminal_result_synopsis/v1"
        )
        # The v2-committed message and the v1 rebuild must have different
        # fingerprints (one carries root_job_id, the other doesn't) — that's
        # the canonical evidence the repair changed the new v2.
        assert rebuilt["fingerprint"] != v2_committed["fingerprint"]

    asyncio.run(scenario())


def test_projector_refuses_tampered_persisted_body_without_send() -> None:
    """A tampered persisted body under the candidate key refuses with zero sends."""

    async def scenario() -> None:
        candidate = _candidate()
        committed = await _projected_message_v2(candidate)
        tampered = dict(committed)
        # Same key, foreign body: an external mutation of the persisted wire.
        tampered["body"] = {
            "status": "PASS",
            "result": json.dumps(
                {
                    "schema": "mastermind.executive_terminal_result_synopsis/v1",
                    "role": candidate.role,
                    "outcome": "PASS",
                    "result_envelope_digest": candidate.result_envelope_digest,
                    "terminal_evidence_digest": "f" * 64,
                    "artifact_receipt_digest": candidate.artifact_receipt_digest,
                    "validation_receipt_digest": candidate.validation_receipt_digest,
                    "effective_grant_digest": candidate.effective_grant_digest,
                    "summary_sha256": hashlib.sha256(
                        candidate.summary.encode("utf-8")
                    ).hexdigest(),
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
        }
        operations: list[str] = []
        send_attempts = 0

        async def service_call(_socket_path: Path, request, **kwargs):
            nonlocal send_attempts
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if operation == "send_message":
                send_attempts += 1
                raise AssertionError("tampered evidence must never trigger a send")
            assert operation == "read_thread"
            return _read_response(
                candidate,
                [
                    {
                        "message": tampered,
                        "primary_ts": "1787961600.000002",
                        "duplicate_timestamps": [],
                    }
                ],
            )

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.project(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

        restarted = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        with pytest.raises(TerminalReturnProjectionError) as refused:
            await restarted.reconcile(candidate)
        assert refused.value.code == "EFFECT_UNKNOWN"
        assert send_attempts == 0
        assert "send_message" not in operations

    asyncio.run(scenario())


def test_projector_refuses_foreign_context_persisted_message_without_send() -> None:
    """A persisted message from a foreign context refuses with zero sends."""

    async def scenario() -> None:
        candidate = _candidate()
        committed = await _projected_message_v2(candidate)
        tampered = dict(committed)
        tampered["actor_ref"] = {
            "kind": "worker_attempt",
            "job_id": "JOB-tampered",
            "attempt_id": "ATT-tampered",
            "worker_id": candidate.worker_id,
        }
        operations: list[str] = []
        send_attempts = 0

        async def service_call(_socket_path: Path, request, **kwargs):
            nonlocal send_attempts
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if operation == "send_message":
                send_attempts += 1
                raise AssertionError("foreign-context evidence must never send")
            assert operation == "read_thread"
            return _read_response(
                candidate,
                [
                    {
                        "message": tampered,
                        "primary_ts": "1787961600.000002",
                        "duplicate_timestamps": [],
                    }
                ],
            )

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.project(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

        restarted = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        with pytest.raises(TerminalReturnProjectionError) as refused:
            await restarted.reconcile(candidate)
        assert refused.value.code == "EFFECT_UNKNOWN"
        assert send_attempts == 0
        assert "send_message" not in operations

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "synopsis_version, include_root_job_id",
    [("v1", False), ("v2", False), ("v2", True)],
)
@pytest.mark.parametrize("include_original", [False, True])
@pytest.mark.parametrize("foreign_attempt", [False, True])
def test_owner_seam_same_terminal_under_changed_key_refuses_without_send(
    synopsis_version: str,
    include_root_job_id: bool,
    include_original: bool,
    foreign_attempt: bool,
) -> None:
    """An alternate key cannot make the same terminal result uncommitted."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            projector = _seam_projector(socket_path, candidate, version="v2")
            context = projector._resolve(candidate)[0]
            original = _build_message(
                candidate,
                context,
                synopsis_version=synopsis_version,
                include_root_job_id=include_root_job_id,
            )
            changed = copy.deepcopy(original)
            changed["message_key"] = "asd-exec-result-" + "f" * 64
            changed["fingerprint"] = ""
            if foreign_attempt:
                changed["actor_ref"]["attempt_id"] = "ATT-999"
                changed["applies_to"]["attempt_id"] = "ATT-999"
            changed = build_message_v2(changed)
            assert changed["fingerprint"] != original["fingerprint"]
            assert changed["body"] == original["body"]
            if include_original:
                client.add_reply(
                    SlackMessage(
                        ts="1787961600.000002",
                        author_user_id=BOT,
                        text=render_message_v2(original),
                        thread_ts=_PARENT_TS,
                    )
                )
            client.add_reply(
                SlackMessage(
                    ts="1787961600.000003",
                    author_user_id=BOT,
                    text=render_message_v2(changed),
                    thread_ts=_PARENT_TS,
                )
            )
            original_texts = tuple(
                reply.text for reply in client.thread_messages[_PARENT_TS]
            )
            for version in ("v2", "v1"):
                restarted = _seam_projector(socket_path, candidate, version=version)
                for method in (restarted.reconcile, restarted.project):
                    with pytest.raises(TerminalReturnProjectionError) as refused:
                        await method(candidate)
                    assert refused.value.code == "EFFECT_UNKNOWN"
            assert client.post_call_count == 0
            assert tuple(
                reply.text for reply in client.thread_messages[_PARENT_TS]
            ) == original_texts
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "synopsis_version, include_root_job_id",
    [("v1", False), ("v2", False), ("v2", True)],
)
def test_owner_seam_unrelated_terminal_remains_valid(
    synopsis_version: str,
    include_root_job_id: bool,
) -> None:
    """A distinct attempt and terminal do not block this candidate's send."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            projector = _seam_projector(socket_path, candidate, version="v2")
            other = dataclasses.replace(
                candidate,
                attempt_id="ATT-999",
                terminal_evidence_digest="f" * 64,
                message_key="asd-exec-result-" + "f" * 64,
                result_envelope_digest="1" * 64,
            )
            context = copy.deepcopy(projector._resolve(candidate)[0])
            context["actor_ref"]["attempt_id"] = other.attempt_id
            context["applies_to"]["attempt_id"] = other.attempt_id
            prior = _build_message(
                other,
                context,
                synopsis_version=synopsis_version,
                include_root_job_id=include_root_job_id,
            )
            prior_text = render_message_v2(prior)
            client.add_reply(
                SlackMessage(
                    ts="1787961600.000003",
                    author_user_id=BOT,
                    text=prior_text,
                    thread_ts=_PARENT_TS,
                )
            )
            assert await projector.reconcile(candidate) is None
            receipt = await projector.project(candidate)
            assert receipt.action == "POSTED"
            assert client.post_call_count == 1
            assert client.thread_messages[_PARENT_TS][0].text == prior_text
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_projector_refuses_duplicate_persisted_message_without_send() -> None:
    """Two persisted entries under the candidate key refuse with zero sends."""

    async def scenario() -> None:
        candidate = _candidate()
        committed = await _projected_message_v2(candidate)
        operations: list[str] = []
        send_attempts = 0

        async def service_call(_socket_path: Path, request, **kwargs):
            nonlocal send_attempts
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            if operation == "send_message":
                send_attempts += 1
                raise AssertionError("duplicate evidence must never trigger a send")
            assert operation == "read_thread"
            return _read_response(
                candidate,
                [
                    {
                        "message": committed,
                        "primary_ts": "1787961600.000002",
                        "duplicate_timestamps": [],
                    },
                    {
                        "message": committed,
                        "primary_ts": "1787961600.000003",
                        "duplicate_timestamps": [],
                    },
                ],
            )

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        with pytest.raises(TerminalReturnProjectionError) as raised:
            await projector.project(candidate)
        assert raised.value.code == "EFFECT_UNKNOWN"

        restarted = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        with pytest.raises(TerminalReturnProjectionError) as refused:
            await restarted.reconcile(candidate)
        assert refused.value.code == "EFFECT_UNKNOWN"
        assert send_attempts == 0
        assert "send_message" not in operations

    asyncio.run(scenario())


def test_projector_reconcile_returns_none_when_no_persisted_message_exists() -> None:
    """A clean read with no matching persisted message returns None without send."""

    async def scenario() -> None:
        candidate = _candidate()
        operations: list[str] = []

        async def service_call(_socket_path: Path, request, **kwargs):
            operation = request["operation"]
            operations.append(operation)
            if operation == "bind_or_verify_relay_parent_thread":
                return _bind_response(candidate)
            assert operation == "read_thread"
            return {
                "ok": True,
                "result": {
                    "thread_ts": _binding(candidate).thread_ts,
                    "messages": [],
                    "historical_messages": [],
                    "ineligible_count": 0,
                    "mutated_count": 0,
                },
            }

        projector = ExecutiveTerminalReturnProjector(
            _Resolver(_binding(candidate), expected_candidate=candidate),
            socket_path=Path("/tmp/mastermind-terminal-return.sock"),
            service_call=service_call,
            result_synopsis_version="v2",
        )
        recovered = await projector.reconcile(candidate)
        assert recovered is None
        # bind + read; no send.
        assert operations == ["bind_or_verify_relay_parent_thread", "read_thread"]

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# F2 owner-seam coverage: the actual ExecutiveTerminalReturnProjector over
# the actual AF_UNIX Agent Dialogue service, the actual DialogueEngineV2
# exact-send predicate, and a persisted InMemorySlack thread.  These are the
# decisive positive cases: an immutable committed historical message (legacy
# v1, pre-root-locator v2, or current root-locator v2) is reused across
# activation, fresh-projector restart, and host version rollback with its
# original body/key/fingerprint and zero replacement sends, while tampered,
# duplicate, foreign, or unavailable evidence refuses.
# ---------------------------------------------------------------------------

_PARENT_TS = "1787961600.000001"


def _seam_parent(client: InMemorySlackClient, candidate: TerminalReturnCandidate) -> None:
    """Persist the canonical Relay-owned parent through the existing owner."""

    binding = _binding(candidate)
    parent = build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": binding.work_ref,
            "commission_ref": binding.commission_ref,
            "session_ref": binding.session_ref,
            "operation_key": binding.operation_key,
            "watch_mode": binding.watch_mode,
            "allowed_sol_user_ids": [SOL],
            "created_at": "2026-08-10T23:59:59Z",
        }
    )
    client.add_parent(
        SlackMessage(
            ts=_PARENT_TS,
            author_user_id=BOT,
            text=render_parent_v2(parent),
        )
    )


async def _owner_seam() -> tuple[Path, InMemorySlackClient, asyncio.Task, Path]:
    """Start the real service/engine pair on one AF_UNIX socket.

    The socket must live under a short AF_UNIX path (``/tmp``), mirroring the
    replay test's socket root; pytest's per-test tmp dirs exceed the bound.
    """

    root = Path(tempfile.mkdtemp(prefix="mmx-f2-")).resolve()
    socket_path = root / "dialogue-f2.sock"
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
    service = AgentDialogueService(
        ServiceConfig(
            socket_path=socket_path,
            allowed_peer_uids=(os.geteuid(),),
            request_timeout_seconds=1,
        ),
        DialogueEngine(policy, client, authority_policy=authority),
        engine_v2=DialogueEngineV2(policy, client, authority_policy=authority),
    )
    task = asyncio.create_task(service.serve_forever())
    await wait_for_service_start(task, socket_path)
    return socket_path, client, task, root


def _seam_projector(
    socket_path: Path,
    candidate: TerminalReturnCandidate,
    *,
    version: str = "v1",
) -> ExecutiveTerminalReturnProjector:
    return ExecutiveTerminalReturnProjector(
        _Resolver(_binding(candidate), expected_candidate=candidate),
        socket_path=socket_path,
        result_synopsis_version=version,
    )


async def _stop_seam(task: asyncio.Task, root: Path) -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    shutil.rmtree(root, ignore_errors=True)


def test_owner_seam_v1_committed_survives_v2_activation_restart_and_v1_rollback() -> None:
    """v1 commit -> v2 activation -> fresh v2 restart -> v1 rollback reuses it."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)

            v1 = _seam_projector(socket_path, candidate, version="v1")
            posted = await v1.project(candidate)
            assert posted.action == "POSTED"
            assert posted.message_key == candidate.message_key
            assert client.post_call_count == 1
            replies = client.thread_messages[_PARENT_TS]
            assert len(replies) == 1
            original = parse_message_frame_v2(replies[0].text)
            original_fingerprint = original["fingerprint"]
            original_text = replies[0].text
            assert json.loads(original["body"]["result"])[
                "schema"
            ] == "mastermind.executive_terminal_result_synopsis/v1"

            # v2 activation after the v1 commit must reuse, never resend.
            v2 = _seam_projector(socket_path, candidate, version="v2")
            receipt = await v2.project(candidate)
            assert receipt.action == "DUPLICATE"
            assert receipt.message_key == candidate.message_key
            assert receipt.fingerprint == original_fingerprint
            assert receipt.message_ts == replies[0].ts
            assert receipt.thread_ts == _PARENT_TS

            # Fresh-projector restart under v2 recovers the same identity.
            restarted = _seam_projector(socket_path, candidate, version="v2")
            recovered = await restarted.reconcile(candidate)
            assert recovered is not None
            assert recovered.action == "RECOVERED"
            assert recovered.message_key == candidate.message_key
            assert recovered.fingerprint == original_fingerprint
            assert recovered.message_ts == replies[0].ts

            # Host rollback to v1 still reuses the committed bytes.
            rolled_back = _seam_projector(socket_path, candidate, version="v1")
            rollback_receipt = await rolled_back.project(candidate)
            assert rollback_receipt.action == "DUPLICATE"
            assert rollback_receipt.fingerprint == original_fingerprint

            # Zero replacement sends; persisted bytes untouched.
            assert client.post_call_count == 1
            final_replies = client.thread_messages[_PARENT_TS]
            assert len(final_replies) == 1
            assert final_replies[0].text == original_text
            assert parse_message_frame_v2(final_replies[0].text) == original
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_pre_root_v2_committed_survives_v1_and_v2_hosts() -> None:
    """A pre-root-locator v2 commit (lawful exact-send) is reused by both hosts."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)

            # Commit the historical pre-locator v2 wire through the existing
            # lawful service owner; the engine exact-send predicate runs.
            v2 = _seam_projector(socket_path, candidate, version="v2")
            context = v2._resolve(candidate)[0]
            historical = _build_message(
                candidate,
                context,
                synopsis_version="v2",
                include_root_job_id=False,
            )
            sent = await call_service(
                socket_path,
                {
                    "version": CONTROL_VERSION_V2,
                    "operation": "send_message",
                    "args": {
                        "context": context,
                        "thread_ts": _PARENT_TS,
                        "message": historical,
                        "send_protocol": EXACT_SEND_PROTOCOL,
                    },
                },
            )
            assert sent["ok"] is True, sent
            assert sent["result"]["action"] == "POSTED"
            assert client.post_call_count == 1
            replies = client.thread_messages[_PARENT_TS]
            assert len(replies) == 1
            original = parse_message_frame_v2(replies[0].text)
            original_fingerprint = original["fingerprint"]
            assert original_fingerprint == historical["fingerprint"]
            assert "root_job_id" not in json.loads(original["body"]["result"])

            # v1 host activation: reuse the pre-root v2 message, no resend.
            v1 = _seam_projector(socket_path, candidate, version="v1")
            receipt = await v1.project(candidate)
            assert receipt.action == "DUPLICATE"
            assert receipt.fingerprint == original_fingerprint

            # Fresh-projector restart under v2: same reuse, original bytes.
            restarted = _seam_projector(socket_path, candidate, version="v2")
            recovered = await restarted.reconcile(candidate)
            assert recovered is not None
            assert recovered.action == "RECOVERED"
            assert recovered.fingerprint == original_fingerprint
            again = await restarted.project(candidate)
            assert again.action == "DUPLICATE"
            assert again.fingerprint == original_fingerprint

            assert client.post_call_count == 1
            assert len(client.thread_messages[_PARENT_TS]) == 1
            persisted = parse_message_frame_v2(
                client.thread_messages[_PARENT_TS][0].text
            )
            assert persisted == original
            assert "root_job_id" not in json.loads(persisted["body"]["result"])
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_root_v2_committed_survives_v1_host_and_v2_restart() -> None:
    """A newly committed root-locator v2 message is reused by v1 and v2 hosts."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)

            v2 = _seam_projector(socket_path, candidate, version="v2")
            posted = await v2.project(candidate)
            assert posted.action == "POSTED"
            assert client.post_call_count == 1
            replies = client.thread_messages[_PARENT_TS]
            assert len(replies) == 1
            original = parse_message_frame_v2(replies[0].text)
            original_fingerprint = original["fingerprint"]
            assert (
                json.loads(original["body"]["result"])["root_job_id"] == "JOB-001"
            )

            # v1 host after the root-v2 commit: reuse, never replace.
            v1 = _seam_projector(socket_path, candidate, version="v1")
            receipt = await v1.project(candidate)
            assert receipt.action == "DUPLICATE"
            assert receipt.fingerprint == original_fingerprint

            # v2 restart reconciles and re-activates on the same identity.
            restarted = _seam_projector(socket_path, candidate, version="v2")
            recovered = await restarted.reconcile(candidate)
            assert recovered is not None
            assert recovered.action == "RECOVERED"
            assert recovered.fingerprint == original_fingerprint
            again = await restarted.project(candidate)
            assert again.action == "DUPLICATE"
            assert again.fingerprint == original_fingerprint

            assert client.post_call_count == 1
            assert len(client.thread_messages[_PARENT_TS]) == 1
            assert (
                parse_message_frame_v2(client.thread_messages[_PARENT_TS][0].text)
                == original
            )
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_wrong_digest_persisted_message_refuses_without_send() -> None:
    """A canonical persisted frame carrying wrong digests refuses with zero sends."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            # Same terminal evidence digest -> same message_key, but every
            # other committed digest differs: a well-formed wrong-digest wire.
            wrong = dataclasses.replace(
                candidate,
                result_envelope_digest="f" * 64,
                artifact_receipt_digest="e" * 64,
                validation_receipt_digest="b" * 64,
                effective_grant_digest="c" * 64,
            )
            v2 = _seam_projector(socket_path, candidate, version="v2")
            context = v2._resolve(candidate)[0]
            wrong_message = _build_message(wrong, context, synopsis_version="v1")
            assert wrong_message["message_key"] == candidate.message_key
            client.add_reply(
                SlackMessage(
                    ts="1787472100.000001",
                    author_user_id=BOT,
                    text=render_message_v2(wrong_message),
                    thread_ts=_PARENT_TS,
                )
            )

            with pytest.raises(TerminalReturnProjectionError) as raised:
                await v2.project(candidate)
            assert raised.value.code == "EFFECT_UNKNOWN"

            restarted = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as refused:
                await restarted.reconcile(candidate)
            assert refused.value.code == "EFFECT_UNKNOWN"

            assert client.post_call_count == 0
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_foreign_actor_persisted_message_refuses_without_send() -> None:
    """A persisted frame from a foreign actor under the key refuses, zero sends."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            v2 = _seam_projector(socket_path, candidate, version="v2")
            context = v2._resolve(candidate)[0]
            foreign_context = copy.deepcopy(context)
            foreign_context["actor_ref"] = {
                "kind": "worker_attempt",
                "job_id": candidate.job_id,
                "attempt_id": "ATT-999",
                "worker_id": candidate.worker_id,
            }
            foreign_context["applies_to"]["attempt_id"] = "ATT-999"
            foreign = _build_message(
                candidate, foreign_context, synopsis_version="v1"
            )
            assert foreign["message_key"] == candidate.message_key
            client.add_reply(
                SlackMessage(
                    ts="1787472100.000001",
                    author_user_id=BOT,
                    text=render_message_v2(foreign),
                    thread_ts=_PARENT_TS,
                )
            )

            with pytest.raises(TerminalReturnProjectionError) as raised:
                await v2.project(candidate)
            assert raised.value.code == "EFFECT_UNKNOWN"

            restarted = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as refused:
                await restarted.reconcile(candidate)
            assert refused.value.code == "EFFECT_UNKNOWN"

            assert client.post_call_count == 0
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_foreign_worker_persisted_message_refuses_without_send() -> None:
    """A valid joined foreign worker frame refuses at the projector after reading."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            v2 = _seam_projector(socket_path, candidate, version="v2")
            context = v2._resolve(candidate)[0]
            foreign_context = copy.deepcopy(context)
            foreign_context["applies_to"] = {
                "kind": "executive_attempt",
                "job_id": candidate.job_id,
                "attempt_id": candidate.attempt_id,
                "worker_id": "worker-foreign",
            }
            foreign_context["actor_ref"]["worker_id"] = "worker-foreign"
            foreign = _build_message(
                candidate, foreign_context, synopsis_version="v1"
            )
            client.add_reply(
                SlackMessage(
                    ts="1787472100.000001",
                    author_user_id=BOT,
                    text=render_message_v2(foreign),
                    thread_ts=_PARENT_TS,
                )
            )

            with pytest.raises(TerminalReturnProjectionError) as raised:
                await v2.project(candidate)
            assert raised.value.code == "EFFECT_UNKNOWN"

            restarted = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as refused:
                await restarted.reconcile(candidate)
            assert refused.value.code == "EFFECT_UNKNOWN"

            assert client.post_call_count == 0
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_duplicate_persisted_replies_refuse_without_send() -> None:
    """Two physical replies under one key refuse reconciliation, zero sends."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            v2 = _seam_projector(socket_path, candidate, version="v2")
            context = v2._resolve(candidate)[0]
            committed = _build_message(candidate, context, synopsis_version="v1")
            for ts in ("1787472100.000001", "1787472100.000002"):
                client.add_reply(
                    SlackMessage(
                        ts=ts,
                        author_user_id=BOT,
                        text=render_message_v2(committed),
                        thread_ts=_PARENT_TS,
                    )
                )

            with pytest.raises(TerminalReturnProjectionError) as raised:
                await v2.project(candidate)
            assert raised.value.code == "EFFECT_UNKNOWN"

            restarted = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as refused:
                await restarted.reconcile(candidate)
            assert refused.value.code == "EFFECT_UNKNOWN"

            assert client.post_call_count == 0
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_mutated_persisted_reply_refuses_without_replacement_send() -> None:
    """A physically mutated persisted reply refuses; the original send stands."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            v1 = _seam_projector(socket_path, candidate, version="v1")
            posted = await v1.project(candidate)
            assert posted.action == "POSTED"
            assert client.post_call_count == 1
            reply_ts = client.thread_messages[_PARENT_TS][0].ts
            original_text = client.thread_messages[_PARENT_TS][0].text

            client.mutate_reply(
                thread_ts=_PARENT_TS,
                message_ts=reply_ts,
                text=original_text + " tampered",
            )

            v2 = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as raised:
                await v2.project(candidate)
            assert raised.value.code == "EFFECT_UNKNOWN"

            restarted = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as refused:
                await restarted.reconcile(candidate)
            assert refused.value.code == "EFFECT_UNKNOWN"

            # Only the original lawful send; no replacement was attempted.
            assert client.post_call_count == 1
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_incomplete_thread_history_refuses_without_send() -> None:
    """An unavailable (incomplete) read refuses; absence of proof never sends."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            client.thread_history_complete = False

            v2 = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as raised:
                await v2.project(candidate)
            assert raised.value.code == "DIALOGUE_REFUSED"

            restarted = _seam_projector(socket_path, candidate, version="v2")
            with pytest.raises(TerminalReturnProjectionError) as refused:
                await restarted.reconcile(candidate)
            assert refused.value.code == "DIALOGUE_REFUSED"

            assert client.post_call_count == 0
        finally:
            await _stop_seam(task, root)

    asyncio.run(scenario())


def test_owner_seam_genuine_send_effect_unknown_stays_absent_on_reconcile() -> None:
    """A genuinely unknown send effect leaves absence; reconcile returns None."""

    async def scenario() -> None:
        candidate = _candidate()
        socket_path, client, task, root = await _owner_seam()
        try:
            _seam_parent(client, candidate)
            client.post_behaviors = ["unknown_no_commit"]

            v1 = _seam_projector(socket_path, candidate, version="v1")
            with pytest.raises(TerminalReturnProjectionError) as raised:
                await v1.project(candidate)
            assert raised.value.code == "EFFECT_UNKNOWN"
            assert client.post_call_count == 1
            assert client.thread_messages[_PARENT_TS] == []

            # Absence during reconciliation is never a fresh dispatch.
            restarted = _seam_projector(socket_path, candidate, version="v1")
            assert await restarted.reconcile(candidate) is None
            assert client.post_call_count == 1
            assert client.thread_messages[_PARENT_TS] == []
        finally:
            await _stop_seam(task, root)

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
        # _supervisor assigns its provider home after adapter construction.
        # macOS temp paths may inherit wheel, so align the final fixture home
        # with the sealed worker identity before launch attestation.
        os.chown(self.provider_home, -1, os.getegid())
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
                "path": "README.md",
                "content_sha256": hashlib.sha256(
                    b"# Exact proof base\n"
                ).hexdigest(),
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

            def projector_factory(runtime_getter, socket_path):
                return ExecutiveTerminalReturnProjector(
                    RuntimeTerminalReturnBindingResolver(runtime_getter),
                    socket_path=socket_path,
                )

            return ExecutiveControlService(
                config,
                supervisor_factory=supervisor_factory,
                autonomy_guard=lambda: None,
                ceo_ingress_socket_path=ingress_path,
                ceo_ingress_peer_uid=os.geteuid(),
                ceo_ingress_grounding_provider=grounding,
                ceo_ingress_dialogue_source_provider=(
                    lambda _intent_id, _workstream: source
                ),
                ceo_ingress_armed=True,
                terminal_return_projector_factory=projector_factory,
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
            assert submitted["ok"] is True, submitted
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


def test_offline_web_ceo_aggregation_terminal_obligation_remains_delivered_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import test_executive_os_phase1fc as phase1fc

    def sourced_submit(runtime, payload):
        return ceo_intent.submit_intent(
            runtime,
            {**payload, "workstream": "WS:EXECUTIVE-OS"},
            dialogue_source={
                "schema_version": "mastermind.executive_dialogue_source/v1",
                "work_ref": "WS:EXECUTIVE-OS",
                "commission_ref": {
                    "repository": REPO,
                    "commit": "c" * 40,
                    "path": "docs/commissions/executive-terminal-return.md",
                    "content_sha256": "d" * 64,
                },
                "watch_mode": "turn_watch_v1",
            },
            require_dialogue_source=True,
        )

    original_submit = phase1fc.submit_intent
    monkeypatch.setattr(phase1fc, "submit_intent", sourced_submit)
    runtime, cycle, dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime",
            intent_id="CEO-OFFLINE-AGGREGATION-RETURN",
            review_workers=["worker-b"],
        )
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    review_body = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=str(runtime.jobs.get_job(work.attempt.job_id).plan_digest),
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )
    _complete_ohf_role(runtime, review, review_body, identity_seed=9301)
    assert cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    aggregation = dispatches[-1]
    aggregation_body = {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": root.job_id,
        "handoff_digest": handoff["handoff_digest"],
        "policy_sha": handoff["policy_sha"],
        "plan_attempt_id": handoff["plan_attempt_id"],
        "plan_digest": handoff["plan_digest"],
        "revisions": [
            {key: item[key] for key in {
                "ordinal",
                "plan_step_id",
                "current_job_id",
                "current_attempt_id",
                "current_result_digest",
                "repair_round",
                "review_required",
                "qualifying_review_job_id",
                "qualifying_review_attempt_id",
                "qualifying_review_result_digest",
            }}
            for item in handoff["revisions"]
        ],
        "aggregate_summary": "One bounded reviewed offline result is ready.",
        "evidence_digests": [],
    }
    _complete_ohf_role(
        runtime, aggregation, aggregation_body, identity_seed=9302
    )
    assert original_submit is not None

    material = runtime.validated_role_completion(
        root.job_id,
        expected_attempt_id=aggregation.attempt.attempt_id,
    )
    candidate = reduce_terminal_return(material=material)
    assert candidate.role == "aggregation"
    assert candidate.root_job_id == root.job_id
    assert candidate.job_id == root.job_id

    operations: list[str] = []

    async def service_call(_socket_path, request, **kwargs):
        operations.append(str(request["operation"]))
        if request["operation"] == "bind_or_verify_relay_parent_thread":
            return {
                "ok": True,
                "result": {
                    "attestation": "mastermind.agent_dialogue.relay_parent/v1",
                    "thread_ts": "1787961600.000001",
                    "parent_author_user_id": BOT,
                    "parent_fingerprint": "e" * 64,
                },
            }
        if request["operation"] == "read_thread":
            return {
                "ok": True,
                "result": {
                    "thread_ts": "1787961600.000001",
                    "messages": [],
                    "historical_messages": [],
                    "ineligible_count": 0,
                    "mutated_count": 0,
                },
            }
        if request["operation"] == "send_message":
            before_write = kwargs.pop("before_write")
            result = before_write()
            if inspect.isawaitable(result):
                await result
            assert kwargs == {}
        message = request["args"]["message"]
        return {
            "ok": True,
            "result": {
                "action": "POSTED",
                "message_key": message["message_key"],
                "fingerprint": message["fingerprint"],
                "message_ts": "1787961600.000002",
                "duplicate_timestamps": [],
                "thread_ts": "1787961600.000001",
                "parent_author_user_id": BOT,
                "parent_fingerprint": "e" * 64,
            },
        }

    projector = ExecutiveTerminalReturnProjector(
        RuntimeTerminalReturnBindingResolver(lambda: runtime),
        socket_path=tmp_path / "unavailable-agent-relay.sock",
        service_call=service_call,
    )

    class ProjectingCallback:
        async def project(self, projected, *, before_write):
            receipt = await projector.project(projected, before_write=before_write)
            return dataclasses.asdict(receipt)

        async def reconcile(self, _projected):
            raise AssertionError("an APPLIED projection must reconcile by read")

    async def project_once() -> None:
        projection_service = ExecutiveControlService(
            _executive_config(tmp_path / "projection"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=ProjectingCallback(),
        )
        projection_service.runtime = runtime
        await projection_service._project_terminal_return(
            root.job_id,
            expected_attempt_id=aggregation.attempt.attempt_id,
        )
        assert projection_service._terminal_return_last_diagnostic == (
            "terminal-return:APPLIED"
        ), (
            projection_service._terminal_return_last_diagnostic
        )

    asyncio.run(project_once())
    assert operations == [
        "bind_or_verify_relay_parent_thread",
        "read_thread",
        "send_message",
    ]
    terminal_events = [
        event.event_type
        for event in runtime.events.list_events(
            attempt_id=aggregation.attempt.attempt_id
        )
        if event.event_type.startswith("EXECUTIVE_TERMINAL_RETURN_")
    ]
    assert terminal_events == [
        "EXECUTIVE_TERMINAL_RETURN_PREPARED",
        "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
        "EXECUTIVE_TERMINAL_RETURN_APPLIED",
    ]
    event_count = len(runtime.events.list_events())

    binding = RuntimeBinding(
        session_alias="EXECUTIVE-CEO-A",
        binding_id="bind-offline-aggregation-01",
        binding_generation=1,
        native_handle="thread-offline-aggregation",
        account_label="codex-offline-aggregation",
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
    ).with_root_job_bindings({root.job_id: {"ceo": "EXECUTIVE-CEO-A"}})
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "f" * 64,
        declared_target_seat="ceo",
        job_id=candidate.job_id,
        attempt_id=candidate.attempt_id,
        root_job_id=candidate.root_job_id,
        source_workstream="WS:EXECUTIVE-OS",
        source_created_at="2026-09-14T00:00:01Z",
        emitted_at="2026-09-14T00:00:02Z",
    )
    route = route_obligation(obligation, registry, binding=binding)
    wake_repo = WakeLedgerRepository(runtime)
    dispatcher = _Dispatcher(repo=wake_repo)
    carrier = PersistedWakeCarrier(
        repository=wake_repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
    )
    asyncio.run(carrier.submit(obligation, route))
    delivered = [
        item.record.phase
        for item in wake_repo.list_records(obligation.obligation_id)
    ]
    assert delivered == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]
    assert LedgerPhase.TARGET_ACKNOWLEDGED not in delivered
    assert not [
        event
        for event in runtime.events.list_events()
        if "PRODUCTION_ACCEPT" in event.event_type
    ]

    reopened_runtime = Runtime.at(tmp_path / "runtime")
    reopened_material = reopened_runtime.validated_role_completion(
        root.job_id,
        expected_attempt_id=aggregation.attempt.attempt_id,
    )
    assert reduce_terminal_return(material=reopened_material) == candidate
    replay_service = ExecutiveControlService(
        _executive_config(tmp_path / "replay-service"),
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        terminal_return_projector=ProjectingCallback(),
    )
    replay_service.runtime = reopened_runtime
    asyncio.run(
        replay_service._project_terminal_return(
            root.job_id,
            expected_attempt_id=aggregation.attempt.attempt_id,
        )
    )
    assert replay_service._terminal_return_last_diagnostic == (
        "terminal-return:ALREADY_APPLIED"
    )
    assert operations == [
        "bind_or_verify_relay_parent_thread",
        "read_thread",
        "send_message",
    ]
    reopened_event_ids = [
        event.event_id
        for event in reopened_runtime.events.list_events()
        if event.event_id is not None
    ]
    assert reopened_event_ids[-event_count:] == list(
        range(reopened_event_ids[-1] - event_count + 1, reopened_event_ids[-1] + 1)
    )
    assert len(set(reopened_event_ids)) == len(reopened_event_ids)

    reopened_wake_repo = WakeLedgerRepository(reopened_runtime)
    restarted_dispatcher = _Dispatcher(repo=reopened_wake_repo)
    restarted_carrier = PersistedWakeCarrier(
        repository=reopened_wake_repo,
        dispatchers=WakeDispatcherRegistry(
            {"codex-app-server": restarted_dispatcher}
        ),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
    )
    assert asyncio.run(
        restarted_carrier.reconcile(obligation, route)
    ) is not None
    assert restarted_dispatcher.nudge_calls == 0

    stale_binding = dataclasses.replace(
        binding,
        binding_generation=binding.binding_generation + 1,
    )
    stale_carrier = PersistedWakeCarrier(
        repository=reopened_wake_repo,
        dispatchers=WakeDispatcherRegistry(
            {"codex-app-server": restarted_dispatcher}
        ),
        current_binding_for=lambda _route: stale_binding,
        retry_policy=_POLICY,
    )
    with pytest.raises(WakePreSubmitError, match="current RuntimeBinding"):
        asyncio.run(stale_carrier.submit(obligation, route))
    replayed_wake = [
        item.record.phase
        for item in reopened_wake_repo.list_records(obligation.obligation_id)
    ]
    assert replayed_wake == delivered
    assert restarted_dispatcher.nudge_calls == 0
