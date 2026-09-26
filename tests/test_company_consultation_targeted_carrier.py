"""P1-R1 source-only carrier proof; target facts below are hermetic fixtures.

The real AF_UNIX service/engine are exercised, but no live Slack, provider,
Runtime admission, peer discovery, or production target resolver is claimed.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import importlib
import importlib.util
import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from control_plane.executive_runtime import StateConflict
from integrations.company_consultation_dispatch import (
    ConsultationPacketCarrierUnknown,
    ConsultationPacketCommitAborted,
    ConsultationPacketEffectUnknown,
)
from integrations.slack_agent_dialogue.service import DialogueServiceError
from tests.test_company_inbox_iac1 import (
    _binding,
    _BoundedInMemorySlackClient,
    _dialogue_binding,
    _packet_frame,
    _relay_parent,
    _relay_policy,
    _start_relay_service,
    _StaticDialogueBindingResolver,
    _stop_relay_service,
)


def _api():
    name = "integrations.company_consultation_targets"
    assert importlib.util.find_spec(name) is not None, (
        "P1-R1 has no trusted distinct-parent packet carrier yet"
    )
    return importlib.import_module(name)


def _parties():
    a = ("job-requester", "attempt-requester", "worker-requester", _binding("a"))
    b = ("job-recipient", "attempt-recipient", "worker-recipient", _binding("b"))
    c = ("job-foreign", "attempt-foreign", "worker-foreign", _binding("c"))
    bindings = (
        _dialogue_binding(a),
        _dialogue_binding(
            b, session_ref="asd-session-iac1-p1-recipient-0002",
            operation_key="iac-p1r1-recipient-20260926-sol-001",
            thread_ts="1787961700.000001",
        ),
        _dialogue_binding(c),
    )
    return a, b, c, bindings


def _target(binding):
    api = _api()
    facts = {
        "actor_ref": dict(binding.actor_ref),
        "work_ref": binding.work_ref,
        "commission_ref": dict(binding.commission_ref),
        "session_ref": binding.session_ref,
        "operation_key": binding.operation_key,
        "watch_mode": binding.watch_mode,
        "thread_ts": binding.thread_ts,
    }
    return api.ConsultationDeliveryTarget(
        **facts,
        evidence_digest=hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest(),
    )


class _ExactFixtureAccess:
    """Test-only stand-in for exact persisted Executive/Wake party facts."""

    def __init__(self, question, bindings):
        self.question = copy.deepcopy(question)
        self.bindings = bindings
        self.calls = 0
        self.transform = None

    def resolve(self, consultation_id, *, purpose, frame=None):
        self.calls += 1
        assert consultation_id == self.question["consultation_id"]
        access = _api().ConsultationPacketAccess(
            target=_target(self.bindings[1 if purpose == "QUESTION" else 0]),
            requester_actor_ref=self.question["requester_actor_ref"],
            recipient_actor_ref=self.question["recipient_actor_ref"],
        )
        return self.transform(access, self.calls) if self.transform else access


class _Service:
    def __init__(self, frame=None, *, error=None):
        self.frame = frame
        self.error = error
        self.calls = []
        self.commits = 0
        self.after_read = None

    async def __call__(self, socket_path, request, *, before_write=None, **kwargs):
        self.calls.append(copy.deepcopy(request))
        if before_write is not None:
            await before_write()
            self.commits += 1
        if self.error:
            raise DialogueServiceError(self.error)
        if request["operation"] == "send_consultation_packet":
            packet = request["args"]["message"]
            return {"ok": True, "result": {
                "message_key": packet["message_key"],
                "fingerprint": packet["fingerprint"],
                "thread_ts": request["args"]["thread_ts"],
            }}
        if self.after_read:
            self.after_read()
        return {"ok": True, "result": None if self.frame is None else {
            "packet": self.frame,
            "primary_ts": "1787961700.000002",
            "duplicate_timestamps": [],
        }}


async def _noop():
    return None


def _setup(*, purpose="QUESTION", actor=None, frame=None, error=None):
    a, b, c, bindings = _parties()
    packet = _packet_frame(a, b, purpose=purpose)
    question = _packet_frame(a, b)
    caller = actor if actor is not None else (0 if purpose == "QUESTION" else 1)
    binding = _StaticDialogueBindingResolver(bindings[caller])
    targets = _ExactFixtureAccess(question, bindings)
    service = _Service(frame=frame, error=error)
    carrier = _api().TargetedAgentDialogueConsultationPacketCarrier(
        binding_resolver=binding, targets=targets,
        socket_path=Path("/tmp/iac-p1r1-test-only.sock"), service_call=service,
    )
    return carrier, service, targets, binding, packet, bindings


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_sender_authority_and_physical_destination_are_separate(purpose):
    carrier, service, targets, binding, packet, bindings = _setup(purpose=purpose)
    asyncio.run(getattr(carrier, "put_" + purpose.lower())(
        packet["consultation_id"], packet, before_commit=_noop,
    ))
    args = service.calls[0]["args"]
    destination = bindings[1 if purpose == "QUESTION" else 0]
    assert args["thread_ts"] == destination.thread_ts
    assert args["context"]["operation_key"] == destination.operation_key
    assert args["context"]["actor_ref"] == dict(destination.actor_ref)
    assert args["message"] == packet
    assert service.commits == 1


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
@pytest.mark.parametrize("actor", ["destination", "foreign"])
def test_destination_or_foreign_binding_never_grants_sender_authority(purpose, actor):
    wrong = 2 if actor == "foreign" else (1 if purpose == "QUESTION" else 0)
    carrier, service, targets, binding, packet, bindings = _setup(purpose=purpose, actor=wrong)
    with pytest.raises(StateConflict):
        asyncio.run(getattr(carrier, "put_" + purpose.lower())(
            packet["consultation_id"], packet, before_commit=_noop,
        ))
    assert service.calls == []
    assert service.commits == 0


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_wrong_target_actor_is_refused_before_transport(purpose):
    carrier, service, targets, binding, packet, bindings = _setup(purpose=purpose)
    targets.transform = lambda access, count: dataclasses.replace(access, target=_target(bindings[2]))
    with pytest.raises(StateConflict):
        asyncio.run(getattr(carrier, "put_" + purpose.lower())(
            packet["consultation_id"], packet, before_commit=_noop,
        ))
    assert service.calls == []


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
@pytest.mark.parametrize("present", [False, True])
def test_nonparty_read_cannot_probe_absence_or_fetch_packet(purpose, present):
    a, b, _, _ = _parties()
    frame = _packet_frame(a, b, purpose=purpose) if present else None
    carrier, service, _, _, packet, _ = _setup(purpose=purpose, actor=2, frame=frame)
    with pytest.raises(StateConflict):
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert service.calls == []


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
@pytest.mark.parametrize("caller", [0, 1])
def test_either_exact_party_reads_original_destination_without_route_cache(purpose, caller):
    a, b, _, _ = _parties()
    frame = _packet_frame(a, b, purpose=purpose)
    carrier, service, _, _, _, bindings = _setup(purpose=purpose, actor=caller, frame=frame)
    assert asyncio.run(getattr(carrier, "get_" + purpose.lower())(frame["consultation_id"])) == frame
    assert service.calls[0]["args"]["thread_ts"] == bindings[1 if purpose == "QUESTION" else 0].thread_ts
    assert service.commits == 0


@pytest.mark.parametrize("stage", ["ready", "after_intent"])
@pytest.mark.parametrize("change", ["caller", "target"])
def test_binding_change_before_commit_aborts_without_packet(stage, change):
    carrier, service, targets, binding, packet, bindings = _setup()
    admitted = []

    def change_identity():
        if change == "caller":
            binding.binding = bindings[2]
        else:
            targets.transform = lambda access, count: dataclasses.replace(
                access, target=dataclasses.replace(access.target, thread_ts="1787961800.000001")
            )

    if stage == "ready":
        original = targets.resolve
        def resolve(*args, **kwargs):
            access = original(*args, **kwargs)
            if targets.calls == 1:
                change_identity()
            return access
        targets.resolve = resolve

    async def admit():
        admitted.append("INTENT")
        if stage == "after_intent":
            change_identity()

    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        asyncio.run(carrier.put_question(packet["consultation_id"], packet, before_commit=admit))
    assert service.commits == 0
    assert admitted == ([] if stage == "ready" else ["INTENT"])


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_missing_or_ambiguous_target_facts_do_not_become_absence(purpose):
    carrier, service, targets, _, packet, _ = _setup(purpose=purpose)
    def unavailable(*args, **kwargs):
        raise RuntimeError("AMBIGUOUS_PRIVATE_SOURCE")
    targets.resolve = unavailable
    with pytest.raises(ConsultationPacketCarrierUnknown) as caught:
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert "PRIVATE" not in str(caught.value)
    assert service.calls == []


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_tampered_packet_parties_are_not_returned(purpose):
    a, b, c, _ = _parties()
    frame = _packet_frame(a, c, purpose=purpose)
    carrier, service, _, _, packet, _ = _setup(purpose=purpose, frame=frame)
    with pytest.raises(ConsultationPacketCarrierUnknown):
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert service.commits == 0


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_read_identity_drift_suppresses_even_absence(purpose):
    carrier, service, _, binding, packet, bindings = _setup(purpose=purpose)
    service.after_read = lambda: setattr(binding, "binding", bindings[2])
    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert service.commits == 0


@pytest.mark.parametrize("error,expected", [
    ("SEND_EFFECT_UNKNOWN", ConsultationPacketEffectUnknown),
    ("SERVICE_UNAVAILABLE", ConsultationPacketCarrierUnknown),
])
def test_transport_uncertainty_is_not_reclassified_as_safe_absence(error, expected):
    carrier, service, _, _, packet, _ = _setup(error=error)
    with pytest.raises(expected):
        asyncio.run(carrier.put_question(packet["consultation_id"], packet, before_commit=_noop))
    assert len(service.calls) == 1


def test_new_question_preintent_read_uses_frame_without_remembering_route():
    carrier, service, _, _, packet, bindings = _setup()
    assert asyncio.run(carrier.get_question_for(packet)) is None
    assert service.calls[0]["args"]["thread_ts"] == bindings[1].thread_ts
    assert service.commits == 0


def test_owner_abort_is_preserved_without_commit():
    carrier, service, _, _, packet, _ = _setup()
    async def abort():
        raise ConsultationPacketCommitAborted("intent lost the race")
    with pytest.raises(ConsultationPacketCommitAborted):
        asyncio.run(carrier.put_question(packet["consultation_id"], packet, before_commit=abort))
    assert service.commits == 0


def test_delivery_target_is_immutable_and_is_not_a_dialogue_grant():
    _, _, _, _, _, bindings = _setup()
    target = _target(bindings[1])
    with pytest.raises(TypeError):
        target.actor_ref["worker_id"] = "wrong"
    with pytest.raises(TypeError):
        target.commission_ref["path"] = "wrong"
    assert not hasattr(target, "allowed_message_types")
    assert not hasattr(target, "binding_id")


def test_real_af_unix_distinct_parent_roundtrip_and_restart():
    api = _api()
    a, b, _, bindings = _parties()
    question = _packet_frame(a, b)
    answer = _packet_frame(a, b, purpose="ANSWER")

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="iac-r1-", dir="/tmp") as root:
            socket = Path(root) / "r.sock"
            client = _BoundedInMemorySlackClient(
                relay_bot_user_id=_relay_policy().relay_bot_user_id,
                next_timestamp=Decimal("1787961900.000001"),
            )
            for binding in bindings[:2]:
                client.add_parent(_relay_parent(binding, _relay_policy()))
            admitted = []
            async def gate():
                admitted.append("admitted")

            def carrier(index):
                return api.TargetedAgentDialogueConsultationPacketCarrier(
                    binding_resolver=_StaticDialogueBindingResolver(bindings[index]),
                    targets=_ExactFixtureAccess(question, bindings),
                    socket_path=socket, timeout_seconds=2,
                )

            service, task = await _start_relay_service(socket_path=socket, client=client)
            try:
                await carrier(0).put_question(question["consultation_id"], question, before_commit=gate)
                assert await carrier(1).get_question(question["consultation_id"]) == question
            finally:
                await _stop_relay_service(service, task)

            service, task = await _start_relay_service(socket_path=socket, client=client)
            try:
                assert await carrier(1).get_question(question["consultation_id"]) == question
                await carrier(1).put_answer(answer["consultation_id"], answer, before_commit=gate)
                assert await carrier(0).get_answer(answer["consultation_id"]) == answer
                # Exact replay uses the Relay's existing deduplication, not a carrier cache.
                await carrier(0).put_question(question["consultation_id"], question, before_commit=gate)
                await carrier(1).put_answer(answer["consultation_id"], answer, before_commit=gate)
                assert admitted == ["admitted", "admitted"]
                page_a = await client.fetch_thread(channel_id=_relay_policy().channel_id,
                    thread_ts=bindings[0].thread_ts, limit=100)
                page_b = await client.fetch_thread(channel_id=_relay_policy().channel_id,
                    thread_ts=bindings[1].thread_ts, limit=100)
                assert len(page_a.messages) == 2  # A parent + ANSWER only.
                assert len(page_b.messages) == 2  # B parent + QUESTION only.
            finally:
                await _stop_relay_service(service, task)

    asyncio.run(scenario())


def test_targeted_adapters_add_no_second_control_plane():
    import ast
    import re

    root = Path(__file__).resolve().parents[1]
    forbidden_suffix = re.compile(r"(Store|Cache|Registry|Queue|Retry|Scheduler|Daemon|Listener|Server)$")
    forbidden_calls = {"transaction", "execute", "write_text", "write_bytes", "mkdir", "start_unix_server", "create_task"}
    for name in ("company_consultation_targets.py", "company_consultation_target_resolution.py"):
        tree = ast.parse((root / "integrations" / name).read_text())
        symbols = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
        assert not {name for name in symbols if forbidden_suffix.search(name)}
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        assert not calls.intersection(forbidden_calls)
        imported = {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
        assert "sqlite3" not in imported
        if name.endswith("_resolution.py"):
            assert "integrations.workspace_agent_runtime_binding" in imported


# ---------------------------------------------------------------------------
# P1-R1 repair: deterministic destination conflicts are not carrier outages
# ---------------------------------------------------------------------------


class _EnvelopeService:
    """Return a Relay error envelope verbatim, as ``call_service`` really does.

    ``terminal_response`` returns ``{"ok": false, "error": {"code": ...}}`` for
    any engine code, on the read edge and after COMMIT alike, so a carrier that
    only inspects raised ``DialogueServiceError`` never sees these at all.
    """

    def __init__(self, code, *, operation):
        self.code = code
        self.operation = operation
        self.calls = []
        self.commits = 0

    async def __call__(self, socket_path, request, *, before_write=None, **kwargs):
        self.calls.append(copy.deepcopy(request))
        if before_write is not None:
            await before_write()
            self.commits += 1
        if request["operation"] == self.operation:
            return {"ok": False, "error": {"code": self.code}}
        return {"ok": True, "result": None}


def _envelope_setup(code, *, operation, purpose="QUESTION"):
    a, b, _, bindings = _parties()
    packet = _packet_frame(a, b, purpose=purpose)
    service = _EnvelopeService(code, operation=operation)
    carrier = _api().TargetedAgentDialogueConsultationPacketCarrier(
        binding_resolver=_StaticDialogueBindingResolver(
            bindings[0 if purpose == "QUESTION" else 1]
        ),
        targets=_ExactFixtureAccess(_packet_frame(a, b), bindings),
        socket_path=Path("/tmp/iac-p1r1-test-only.sock"), service_call=service,
    )
    return carrier, service, packet


@pytest.mark.parametrize("code", ["THREAD_CONTEXT_MISMATCH", "THREAD_BINDING_AMBIGUOUS"])
def test_returned_destination_refusal_is_deterministic_on_the_send_edge(code):
    api = _api()
    carrier, service, packet = _envelope_setup(code, operation="send_consultation_packet")
    admitted = []

    async def admit():
        admitted.append("INTENT")

    with pytest.raises(api.ConsultationTargetConflict) as caught:
        asyncio.run(carrier.put_question(
            packet["consultation_id"], packet, before_commit=admit,
        ))
    # A closed owner adjudication, never the retryable carrier-outage bucket.
    assert isinstance(caught.value, StateConflict)
    assert not isinstance(caught.value, ConsultationPacketCarrierUnknown)
    assert not isinstance(caught.value, ConsultationPacketEffectUnknown)
    assert code in str(caught.value)
    assert len(service.calls) == 1


@pytest.mark.parametrize("code", ["THREAD_CONTEXT_MISMATCH", "THREAD_BINDING_AMBIGUOUS"])
def test_returned_destination_refusal_is_deterministic_on_the_read_edge(code):
    api = _api()
    carrier, service, packet = _envelope_setup(code, operation="read_consultation_packet")
    with pytest.raises(api.ConsultationTargetConflict) as caught:
        asyncio.run(carrier.get_question(packet["consultation_id"]))
    assert isinstance(caught.value, StateConflict)
    assert not isinstance(caught.value, ConsultationPacketCarrierUnknown)
    assert code in str(caught.value)
    assert service.commits == 0


@pytest.mark.parametrize("operation", ["send_consultation_packet", "read_consultation_packet"])
def test_a_non_destination_envelope_still_reconciles_as_unknown(operation):
    """Positive control: the closed mapping was not widened to every envelope."""
    api = _api()
    carrier, service, packet = _envelope_setup("THREAD_NOT_FOUND", operation=operation)
    call = (
        carrier.put_question(packet["consultation_id"], packet, before_commit=_noop)
        if operation == "send_consultation_packet"
        else carrier.get_question(packet["consultation_id"])
    )
    with pytest.raises(ConsultationPacketCarrierUnknown) as caught:
        asyncio.run(call)
    assert not isinstance(caught.value, api.ConsultationTargetConflict)


@pytest.mark.parametrize(
    "kind, code",
    [
        ("context_mismatch", "THREAD_CONTEXT_MISMATCH"),
        ("binding_ambiguous", "THREAD_BINDING_AMBIGUOUS"),
    ],
)
def test_real_af_unix_inconsistent_destination_refuses_with_no_effect(kind, code):
    """The real service returns the engine envelope; nothing is written.

    BOTH deterministic destination refusals are provoked through the real
    AF_UNIX service rather than a synthetic envelope: ``context_mismatch``
    sends B's context down A's thread, and ``binding_ambiguous`` leaves two
    parents carrying the destination identity so the engine's own parent scan
    finds two exact matches (``_scan_parent_history``, ``len(matches) > 1``).
    Neither is rigged absence: each is a destination the owner cannot name.
    """
    api = _api()
    a, b, _, bindings = _parties()
    question = _packet_frame(a, b)

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="iac-r1-conflict-", dir="/tmp") as root:
            socket = Path(root) / "r.sock"
            client = _BoundedInMemorySlackClient(
                relay_bot_user_id=_relay_policy().relay_bot_user_id,
                next_timestamp=Decimal("1787962200.000001"),
            )
            for binding in bindings[:2]:
                client.add_parent(_relay_parent(binding, _relay_policy()))
            twin = None
            if kind == "binding_ambiguous":
                # A QUESTION is destined for bindings[1]; a second parent
                # carrying that same identity makes the destination ambiguous.
                twin = dataclasses.replace(
                    _relay_parent(bindings[1], _relay_policy()),
                    ts="1787962100.000009",
                )
                client.add_parent(twin)
            admitted = []

            async def gate():
                admitted.append("INTENT")

            access = _ExactFixtureAccess(question, bindings)
            if kind == "context_mismatch":
                # An internally inconsistent destination: B's context, A's thread.
                access.transform = lambda acc, count: dataclasses.replace(
                    acc, target=dataclasses.replace(acc.target, thread_ts=bindings[0].thread_ts),
                )
            carrier = api.TargetedAgentDialogueConsultationPacketCarrier(
                binding_resolver=_StaticDialogueBindingResolver(bindings[0]),
                targets=access, socket_path=socket, timeout_seconds=5,
            )
            service, task = await _start_relay_service(socket_path=socket, client=client)
            try:
                with pytest.raises(api.ConsultationTargetConflict) as caught:
                    await carrier.put_question(
                        question["consultation_id"], question, before_commit=gate,
                    )
                assert code in str(caught.value)
                assert not isinstance(caught.value, ConsultationPacketCarrierUnknown)
                # Zero INTENT, zero COMMIT, zero packet, zero Wake.
                assert admitted == []
                threads = [binding.thread_ts for binding in bindings[:2]]
                if twin is not None:
                    threads.append(twin.ts)
                for thread_ts in threads:
                    page = await client.fetch_thread(
                        channel_id=_relay_policy().channel_id,
                        thread_ts=thread_ts, limit=100,
                    )
                    assert len(page.messages) == 1, "only the parent may exist"
            finally:
                await _stop_relay_service(service, task)

    asyncio.run(scenario())


def test_production_composition_cannot_grant_an_arbitrary_resolver():
    """R4 pin: production stays disarmed, and no arbitrary read grant can ship.

    The Protocol seam stays open for tests. What is pinned is that no
    non-test module composes the targeted carrier with anything but the
    canonical resolver built from the incumbent owners.
    """
    import ast

    from integrations.company_consultation_dispatch import PRODUCTION_PACKET_CARRIAGE

    assert PRODUCTION_PACKET_CARRIAGE == "UNAVAILABLE"

    root = Path(__file__).resolve().parents[1]
    carrier_name = "TargetedAgentDialogueConsultationPacketCarrier"
    canonical = "ExecutiveConsultationPacketTargetResolver"
    compositions = 0
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if relative.parts[0] in {"tests", "vendor", "build"} or "test_" in relative.name:
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name != carrier_name:
                continue
            compositions += 1
            targets = [kw.value for kw in node.keywords if kw.arg == "targets"]
            assert len(targets) == 1, (str(relative), node.lineno)
            supplied = targets[0]
            assert isinstance(supplied, ast.Call), (str(relative), node.lineno)
            supplied_func = supplied.func
            supplied_name = (
                supplied_func.attr if isinstance(supplied_func, ast.Attribute)
                else getattr(supplied_func, "id", None)
            )
            assert supplied_name == canonical, (str(relative), node.lineno, supplied_name)
    # Truthful today: the seam is pinned before it exists, not asserted to exist.
    assert compositions == 0, (
        "a production composition appeared; the carriage marker must be "
        "re-adjudicated before arming"
    )
