"""W3: retained plain-input digest evidence over the existing turn transport.

These tests prove the broker/proxy transport only: the retained plain-input
digest reaches the Executive through the *existing* ohf-begin-turn /
ohf-collect-turn path, selected by the ``ohf-op:continuation:`` operation-id
prefix, with no new request flag, no new RPC, and no second store.  The
accepted extractor itself (byte-identical in ``codex_operator_adapter``) keeps
its own native-evidence suite; here the collector is a fake so no provider,
process, ACK, or other runtime effect is possible.  Absence is always the
explicit unavailable answer and the prefix never asserts ACK authority.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from typing import Any

import pytest

from control_plane.codex_operator_adapter import (
    CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST,
    CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION,
    CONSUMPTION_EVIDENCE_SCOPE,
    CONSUMPTION_EVIDENCE_SHAPE,
    RetainedPlainInputEvidence as _ExtractorOwnedEvidence,
)
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.executive_worker_broker import (
    BrokerProtocolError,
    BrokerStateError,
    ExecutiveWorkerBroker,
)
from control_plane.operator_harness_contract import (
    CandidateResult,
    EventCursor,
    OperationId,
    ProcessGenerationRef,
    SessionEpochRef,
    TurnRef,
    TurnStartObservation,
)
from control_plane.operator_harness_wire import (
    CONTINUATION_OPERATION_PREFIX,
    OperatorHarnessWireError,
    RetainedPlainInputEvidence,
    retained_plain_input_evidence,
    to_wire,
)
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from tests.test_executive_operator_broker import (
    _OperatorAdapter,
    _fixture as _broker_fixture,
    _request,
)
from tests.test_remote_operator_harness_adapter import _capabilities

PROMPT = "Rendered Executive instruction: transport this exact plain input — W3 中文 marker."
EPOCH = SessionEpochRef("epoch-1", "ATT-1", "codex-01", 1)
GENERATION = ProcessGenerationRef("generation-1", "epoch-1", 1, "codex-01")
TURN = TurnRef("turn-1", "epoch-1", "generation-1", "ATT-1")
CURSOR = EventCursor("ATT-1", "epoch-1", "generation-1", turn_id="turn-1")


def _retained_evidence(
    turn: TurnRef = TURN,
    *,
    generation: str | None = None,
    prompt: str = PROMPT,
) -> RetainedPlainInputEvidence:
    encoded = prompt.encode("utf-8")
    return RetainedPlainInputEvidence(
        attempt_id=turn.attempt_id,
        session_epoch_id=turn.session_epoch_id,
        process_generation_id=generation or turn.process_generation_id,
        turn_id=turn.turn_id,
        provider_session_id="thread-1",
        provider_native_turn_id="native-turn-1",
        retained_input_digest=hashlib.sha256(encoded).hexdigest(),
        retained_input_byte_length=len(encoded),
        input_shape=CONSUMPTION_EVIDENCE_SHAPE,
        harness_version=CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION,
        harness_binary_digest=CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST,
        scope=CONSUMPTION_EVIDENCE_SCOPE,
    )


# ---------------------------------------------------------------------------
# Closed digest-only wire codec
# ---------------------------------------------------------------------------


def test_wire_type_is_exactly_the_accepted_extractor_value_object():
    # The transport may not invent a second evidence shape: the codec
    # reconstructs the byte-identical extractor's own frozen class.
    assert RetainedPlainInputEvidence is _ExtractorOwnedEvidence
    names = {field.name for field in dataclasses.fields(RetainedPlainInputEvidence)}
    assert names == {
        "attempt_id",
        "session_epoch_id",
        "process_generation_id",
        "turn_id",
        "provider_session_id",
        "provider_native_turn_id",
        "retained_input_digest",
        "retained_input_byte_length",
        "input_shape",
        "harness_version",
        "harness_binary_digest",
        "scope",
    }
    assert not names & {
        "accepted",
        "model_accepted",
        "text",
        "prompt",
        "input",
        "expected_text",
        "build_attestation",
        "ack",
        "authority",
    }


def test_retained_plain_input_evidence_round_trips_without_shape_loss():
    evidence = _retained_evidence()
    encoded = to_wire(evidence)
    assert retained_plain_input_evidence(encoded) == evidence
    assert retained_plain_input_evidence(encoded) is not evidence
    assert PROMPT not in json.dumps(encoded)
    assert encoded["scope"] == CONSUMPTION_EVIDENCE_SCOPE


def test_closed_wire_refuses_missing_and_unexpressable_fields():
    encoded = to_wire(_retained_evidence())
    missing = dict(encoded)
    missing.pop("retained_input_digest")
    with pytest.raises(OperatorHarnessWireError, match="fields drifted"):
        retained_plain_input_evidence(missing)
    # An acceptance boolean, retained text, an expected text, and a caller
    # build attestation are all "unknown fields": the closed grammar cannot
    # carry any of them.
    for key, value in (
        ("accepted", True),
        ("model_accepted", True),
        ("retained_input_text", PROMPT),
        ("expected_text", PROMPT),
        ("build_attestation", "attested"),
        ("ack_authority", "ACK-1"),
    ):
        grown = dict(encoded)
        grown[key] = value
        with pytest.raises(OperatorHarnessWireError, match="fields drifted"):
            retained_plain_input_evidence(grown)


@pytest.mark.parametrize(
    "field",
    [
        "attempt_id",
        "session_epoch_id",
        "process_generation_id",
        "turn_id",
        "provider_session_id",
        "provider_native_turn_id",
    ],
)
def test_closed_wire_refuses_empty_identities(field):
    mutated = dataclasses.replace(_retained_evidence(), **{field: ""})
    with pytest.raises(OperatorHarnessWireError, match="identities"):
        retained_plain_input_evidence(to_wire(mutated))


@pytest.mark.parametrize(
    "digest",
    ["A" * 64, "a" * 63, "g" * 64, "", "a" * 64 + "\n", 123, None],
)
def test_closed_wire_refuses_noncanonical_input_digest(digest):
    mutated = dataclasses.replace(_retained_evidence(), retained_input_digest=digest)
    with pytest.raises(OperatorHarnessWireError, match="lowercase SHA-256"):
        retained_plain_input_evidence(to_wire(mutated))


@pytest.mark.parametrize(
    "length", [True, False, 0, -1, 1.0, "11", None]
)
def test_closed_wire_refuses_bool_and_nonpositive_byte_length(length):
    mutated = dataclasses.replace(
        _retained_evidence(), retained_input_byte_length=length
    )
    with pytest.raises(OperatorHarnessWireError, match="byte length"):
        retained_plain_input_evidence(to_wire(mutated))


def test_closed_wire_refuses_wrong_pin_digest_shape_and_scope():
    evidence = _retained_evidence()
    with pytest.raises(OperatorHarnessWireError, match="harness version pin"):
        retained_plain_input_evidence(
            to_wire(
                dataclasses.replace(
                    evidence, harness_version="drifted/other-build"
                )
            )
        )
    with pytest.raises(OperatorHarnessWireError, match="harness binary pin"):
        retained_plain_input_evidence(
            to_wire(
                dataclasses.replace(
                    evidence, harness_binary_digest="b" * 64
                )
            )
        )
    with pytest.raises(OperatorHarnessWireError, match="shape constant"):
        retained_plain_input_evidence(
            to_wire(dataclasses.replace(evidence, input_shape="single_plain_text/v0"))
        )
    with pytest.raises(OperatorHarnessWireError, match="scope constant"):
        retained_plain_input_evidence(
            to_wire(
                dataclasses.replace(
                    evidence,
                    scope=(
                        "retained-input acceptance and capsule consumption: a much"
                        " stronger claim than the accepted extractor ever makes"
                    ),
                )
            )
        )


def test_continuation_prefix_is_the_shared_transport_vocabulary():
    # The parent delivers trusted capsules under the same prefix; the constant
    # is one closed transport fact, and it is not an ACK of any kind.
    assert CONTINUATION_OPERATION_PREFIX == "ohf-op:continuation:"


# ---------------------------------------------------------------------------
# Broker side: collector reuse is prefix-selected on the existing path
# ---------------------------------------------------------------------------


class _EvidenceAdapter(_OperatorAdapter):
    """Fake OHF adapter whose only addition is the accepted collector seam."""

    def __init__(self, requested, provider_home, prompt_loader, *, evidence, failure):
        super().__init__(requested, provider_home, prompt_loader)
        self.evidence = evidence
        self.failure = failure
        self.collector_turns: list[TurnRef] = []

    def collect_retained_plain_text_evidence(self, turn):
        self.collector_turns.append(turn)
        if self.failure is not None:
            raise RuntimeError(self.failure)
        if self.evidence is None:
            raise RuntimeError("retained_plain_input_evidence_unavailable")
        return self.evidence


def _evidence_broker(tmp_path, *, evidence=None, failure=None):
    broker, peer, profile, _sweeper, _adapters = _broker_fixture(tmp_path)
    made: list[_EvidenceAdapter] = []

    def factory(_workspace, prompt_loader, requested):
        adapter = _EvidenceAdapter(
            requested,
            tmp_path / "provider-home",
            prompt_loader,
            evidence=evidence,
            failure=failure,
        )
        made.append(adapter)
        return adapter

    broker.operator_adapter_factory = factory
    return broker, peer, profile, made


async def _start_generation(broker, peer, profile):
    await broker.execute(
        _request(
            "ohf-start",
            {
                "operation_id": to_wire(OperationId("ohf-op:start:ATT-1")),
                "requested": to_wire(profile),
                "epoch": to_wire(EPOCH),
                "generation": to_wire(GENERATION),
            },
            "start",
        ),
        peer=peer,
    )
    observed = broker._operator_run.adapter.observed_attestation(GENERATION)
    from control_plane.operator_harness_contract import compare_launch

    return compare_launch(profile, observed)


async def _begin(broker, peer, generation, launch, turn, command_id):
    return await broker.execute(
        _request(
            "ohf-begin-turn",
            {
                "operation_id": to_wire(OperationId(command_id)),
                "turn": to_wire(turn),
                "generation": to_wire(generation),
                "launch": to_wire(launch),
                "prompt": PROMPT,
            },
            "begin",
        ),
        peer=peer,
    )


async def _collect(broker, peer, turn):
    return (
        await broker.execute(
            _request(
                "ohf-collect-turn",
                {
                    "turn": to_wire(turn),
                    "cursor": to_wire(
                        EventCursor(
                            turn.attempt_id,
                            turn.session_epoch_id,
                            turn.process_generation_id,
                            turn_id=turn.turn_id,
                        )
                    ),
                    "timeout_seconds": 30.0,
                },
                "collect",
            ),
            peer=peer,
        )
    )["result"]


def test_tagged_turn_collects_the_accepted_digest_evidence_once(tmp_path):
    async def scenario():
        evidence = _retained_evidence()
        broker, peer, profile, made = _evidence_broker(tmp_path, evidence=evidence)
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        result = await _collect(broker, peer, TURN)
        assert made[-1].collector_turns == [TURN]
        transported = result["retained_plain_input_evidence"]
        assert transported["retained_input_digest"] == hashlib.sha256(
            PROMPT.encode("utf-8")
        ).hexdigest()
        assert retained_plain_input_evidence(transported) == evidence
        # The existing candidate/raw/event behavior is untouched.
        assert set(result) == {
            "events",
            "cursor",
            "candidate",
            "raw_role_result",
            "retained_plain_input_evidence",
        }
        assert result["candidate"]["attempt_id"] == "ATT-1"

    asyncio.run(scenario())


def test_ordinary_turn_never_calls_the_collector_and_stays_key_exact(tmp_path):
    async def scenario():
        evidence = _retained_evidence()
        broker, peer, profile, made = _evidence_broker(tmp_path, evidence=evidence)
        launch = await _start_generation(broker, peer, profile)
        await _begin(broker, peer, GENERATION, launch, TURN, "ohf-op:turn-1")
        result = await _collect(broker, peer, TURN)
        assert made[-1].collector_turns == []
        # The ordinary wire keeps its exact previous shape: no key at all, not
        # a fabricated evidence value.
        assert set(result) == {
            "events",
            "cursor",
            "candidate",
            "raw_role_result",
        }

    asyncio.run(scenario())


def test_mark_and_observation_do_not_leak_across_turns_in_one_generation(tmp_path):
    async def scenario():
        evidence = _retained_evidence()
        broker, peer, profile, made = _evidence_broker(tmp_path, evidence=evidence)
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        other = dataclasses.replace(TURN, turn_id="turn-2")
        await _begin(broker, peer, GENERATION, launch, other, "ohf-op:turn-2")
        marked = await _collect(broker, peer, TURN)
        ordinary = await _collect(broker, peer, other)
        assert made[-1].collector_turns == [TURN]
        assert "retained_plain_input_evidence" in marked
        assert "retained_plain_input_evidence" not in ordinary

    asyncio.run(scenario())


def test_mark_is_bound_to_the_exact_immutable_turn_identity(tmp_path):
    async def scenario():
        evidence = _retained_evidence()
        broker, peer, profile, made = _evidence_broker(tmp_path, evidence=evidence)
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        # A TurnRef that differs in any one identity component was never
        # marked: a foreign Attempt/epoch is refused by the existing active
        # generation guard, and the same-generation look-alike collects
        # exactly like an ordinary turn.
        for foreign in (
            dataclasses.replace(TURN, attempt_id="ATT-OTHER"),
            dataclasses.replace(TURN, session_epoch_id="epoch-other"),
        ):
            with pytest.raises((BrokerProtocolError, BrokerStateError)):
                await _collect(broker, peer, foreign)
        result = await _collect(
            broker, peer, dataclasses.replace(TURN, turn_id="turn-2")
        )
        assert "retained_plain_input_evidence" not in result
        # No spliced identity ever reached the accepted collector.
        assert made[-1].collector_turns == []

    asyncio.run(scenario())


def test_no_supported_method_adapter_stays_explicitly_unavailable(tmp_path):
    async def scenario():
        broker, peer, profile, _sweeper, _adapters = _broker_fixture(tmp_path)
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        result = await _collect(broker, peer, TURN)
        assert result["retained_plain_input_evidence"] is None

    asyncio.run(scenario())


def test_extraction_failure_is_unavailable_without_prompt_or_cause(tmp_path):
    async def scenario():
        failure = f"failed to retain {PROMPT!r} (cause: secrets)"
        broker, peer, profile, made = _evidence_broker(
            tmp_path, failure=failure
        )
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        result = await _collect(broker, peer, TURN)
        assert made[-1].collector_turns == [TURN]
        assert result["retained_plain_input_evidence"] is None
        encoded = json.dumps(result)
        assert PROMPT not in encoded
        assert "cause" not in encoded
        assert "RuntimeError" not in encoded

    asyncio.run(scenario())


def test_out_of_contract_collector_output_is_unavailable(tmp_path):
    async def scenario():
        # A positively wrong scope is refused by the closed wire codec, so the
        # transport degrades to explicit unavailable instead of shipping it.
        drifted = dataclasses.replace(_retained_evidence(), scope="not-the-scope")
        broker, peer, profile, made = _evidence_broker(
            tmp_path, evidence=drifted
        )
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        result = await _collect(broker, peer, TURN)
        assert result["retained_plain_input_evidence"] is None

        # An untyped look-alike that is not the accepted value object is
        # equally unavailable.
        class _NotTheEvidence:
            pass

        made[-1].evidence = _NotTheEvidence()
        made[-1].collector_turns.clear()
        result = await _collect(broker, peer, TURN)
        assert result["retained_plain_input_evidence"] is None
        assert made[-1].collector_turns == [TURN]

    asyncio.run(scenario())


def test_marks_die_with_the_generation_and_prefix_relaxes_no_guard(tmp_path):
    async def scenario():
        evidence = _retained_evidence()
        broker, peer, profile, made = _evidence_broker(tmp_path, evidence=evidence)
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        # The prefix adds no request flag: an extra field is still refused.
        with pytest.raises(BrokerProtocolError, match="payload fields"):
            await broker.execute(
                _request(
                    "ohf-begin-turn",
                    {
                        "operation_id": to_wire(
                            OperationId("ohf-op:continuation:ATT-1:turn-1")
                        ),
                        "turn": to_wire(TURN),
                        "generation": to_wire(GENERATION),
                        "launch": to_wire(launch),
                        "prompt": PROMPT,
                        "retained_plain_input_evidence": True,
                    },
                    "begin-with-flag",
                ),
                peer=peer,
            )
        # A marked turn still needs the ordinary cursor binding.
        with pytest.raises(BrokerProtocolError, match="cursor"):
            await broker.execute(
                _request(
                    "ohf-collect-turn",
                    {
                        "turn": to_wire(TURN),
                        "cursor": to_wire(
                            EventCursor(
                                "ATT-OTHER",
                                "epoch-1",
                                "generation-1",
                                turn_id="turn-1",
                            )
                        ),
                        "timeout_seconds": 30.0,
                    },
                    "collect-spliced-cursor",
                ),
                peer=peer,
            )
        result = await _collect(broker, peer, TURN)
        assert result["retained_plain_input_evidence"] is not None
        await broker.execute(
            _request(
                "ohf-stop",
                {
                    "operation_id": to_wire(OperationId("ohf-op:stop-1")),
                    "generation": to_wire(GENERATION),
                },
                "stop",
            ),
            peer=peer,
        )
        # The transient mark did not survive the terminal generation, and the
        # stale generation is refused outright.
        with pytest.raises(BrokerStateError, match="not active"):
            await _collect(broker, peer, TURN)
        assert made[-1].collector_turns == [TURN]

    asyncio.run(scenario())


def test_prefix_grants_no_ack_authority_or_new_operation(tmp_path):
    async def scenario():
        broker, peer, profile, _made = _evidence_broker(
            tmp_path, evidence=_retained_evidence()
        )
        launch = await _start_generation(broker, peer, profile)
        await _begin(
            broker,
            peer,
            GENERATION,
            launch,
            TURN,
            "ohf-op:continuation:ATT-1:turn-1",
        )
        # The closed broker vocabulary gains no ACK/acceptance operation for
        # the prefix: acceptance is never an Executive-assertable boolean.
        for invented in ("ohf-ack", "ohf-continuation-ack", "ohf-accept-evidence"):
            with pytest.raises(BrokerProtocolError, match="not allowed"):
                await broker.execute(
                    _request(invented, {}, "invented-ack"),
                    peer=peer,
                )
        # The observation scope itself is the only claim, and it claims no
        # authority at all.
        assert "no capsule consumption" in CONSUMPTION_EVIDENCE_SCOPE
        assert "grants no authority" in CONSUMPTION_EVIDENCE_SCOPE

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Proxy side: strictly decoded cache against the full TurnRef
# ---------------------------------------------------------------------------


class _ScriptedBrokerClient:
    def __init__(self, collect_responses: list[dict[str, Any]]):
        self.collect_responses = list(collect_responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def request_sync(self, operation, payload, **_kwargs):
        self.calls.append((operation, dict(payload)))
        if operation == "ohf-begin-turn":
            return {"observation": to_wire(TurnStartObservation("native-turn-1", True))}
        if operation == "ohf-collect-turn":
            return self.collect_responses.pop(0)
        raise AssertionError(f"unexpected broker operation {operation}")


def _collect_response(*evidence):
    response = {
        "events": [],
        "cursor": to_wire(
            EventCursor("ATT-1", "epoch-1", "generation-1", turn_id="turn-1")
        ),
        "candidate": to_wire(
            CandidateResult("ATT-1", "epoch-1", "generation-1", "e" * 64, "bounded")
        ),
        "raw_role_result": to_wire(
            RawRoleResultObservation(
                attempt_id="ATT-1",
                session_epoch_id="epoch-1",
                process_generation_id="generation-1",
                turn_id="turn-1",
                provider_session_id="thread-1",
                provider_native_turn_id="native-turn-1",
                provider_turn_artifact_digest="e" * 64,
                canonical_result_json="{}",
                canonical_result_digest=hashlib.sha256(b"{}").hexdigest(),
                canonical_result_byte_length=2,
            )
        ),
    }
    for extra in evidence:
        response.update(extra)
    return response


def _proxy(client) -> RemoteOperatorHarnessAdapter:
    return RemoteOperatorHarnessAdapter(
        client,
        turn_input_loader=lambda _turn: PROMPT,
        capabilities=_capabilities(),
    )


def _begin_turn(proxy, turn=TURN, *, generation=GENERATION, command_id=None):
    return proxy.begin_turn(
        operation_id=OperationId(
            command_id or "ohf-op:continuation:ATT-1:turn-1"
        ),
        turn=turn,
        generation=generation,
        launch=None,
    )


def test_proxy_returns_decoded_evidence_bound_to_the_requested_turn():
    client = _ScriptedBrokerClient(
        [_collect_response({"retained_plain_input_evidence": to_wire(_retained_evidence())})]
    )
    proxy = _proxy(client)
    _begin_turn(proxy)
    proxy.read_events(CURSOR)
    evidence = proxy.collect_retained_plain_text_evidence(TURN)
    assert evidence == _retained_evidence()
    # No new request flag: the begin payload keeps its exact closed shape.
    begin_payload = next(
        payload for operation, payload in client.calls if operation == "ohf-begin-turn"
    )
    assert set(begin_payload) == {
        "operation_id",
        "turn",
        "generation",
        "launch",
        "prompt",
    }


def test_proxy_absent_and_unsupported_stay_explicitly_unavailable():
    for response in (
        _collect_response(),
        _collect_response({"retained_plain_input_evidence": None}),
    ):
        client = _ScriptedBrokerClient([response])
        proxy = _proxy(client)
        _begin_turn(proxy)
        proxy.read_events(CURSOR)
        assert proxy.collect_retained_plain_text_evidence(TURN) is None
    # An ordinary (never-marked) turn is equally explicit, and an uncollected
    # turn is a protocol error instead of a fabricated answer.
    client = _ScriptedBrokerClient([_collect_response()])
    proxy = _proxy(client)
    with pytest.raises(BrokerProtocolError, match="protocol order"):
        proxy.collect_retained_plain_text_evidence(TURN)
    _begin_turn(proxy, command_id="ohf-op:turn-1")
    proxy.read_events(CURSOR)
    assert proxy.collect_retained_plain_text_evidence(TURN) is None


def test_proxy_refuses_positive_evidence_an_ordinary_turn_never_requested():
    client = _ScriptedBrokerClient(
        [_collect_response({"retained_plain_input_evidence": to_wire(_retained_evidence())})]
    )
    proxy = _proxy(client)
    _begin_turn(proxy, command_id="ohf-op:turn-1")
    with pytest.raises(BrokerProtocolError, match="not requested for this turn"):
        proxy.read_events(CURSOR)


@pytest.mark.parametrize(
    "field",
    [
        "attempt_id",
        "session_epoch_id",
        "process_generation_id",
        "turn_id",
        "provider_session_id",
        "provider_native_turn_id",
    ],
)
def test_proxy_refuses_evidence_with_empty_or_spliced_binding(field):
    # An empty binding component is outside the closed wire grammar outright.
    spliced = dataclasses.replace(_retained_evidence(), **{field: ""})
    client = _ScriptedBrokerClient(
        [_collect_response({"retained_plain_input_evidence": to_wire(spliced)})]
    )
    proxy = _proxy(client)
    _begin_turn(proxy)
    with pytest.raises(BrokerProtocolError, match="retained input evidence"):
        proxy.read_events(CURSOR)


def test_proxy_refuses_malformed_and_nonobject_positive_claims():
    malformed = to_wire(_retained_evidence())
    malformed["accepted"] = True
    for bad in (
        {"retained_plain_input_evidence": malformed},
        {"retained_plain_input_evidence": True},
        {"retained_plain_input_evidence": "digest-only"},
        {"retained_plain_input_evidence": 0},
        {
            "retained_plain_input_evidence": {
                **to_wire(_retained_evidence()),
                "retained_input_byte_length": True,
            }
        },
    ):
        client = _ScriptedBrokerClient([_collect_response(bad)])
        proxy = _proxy(client)
        _begin_turn(proxy)
        with pytest.raises(BrokerProtocolError, match="retained input evidence"):
            proxy.read_events(CURSOR)


def test_proxy_cache_splice_across_turn_identity_is_refused():
    client = _ScriptedBrokerClient(
        [_collect_response({"retained_plain_input_evidence": to_wire(_retained_evidence())})]
    )
    proxy = _proxy(client)
    _begin_turn(proxy)
    proxy.read_events(CURSOR)
    for spliced in (
        TurnRef("turn-1", "epoch-1", "generation-1", "ATT-OTHER"),
        TurnRef("turn-1", "epoch-other", "generation-1", "ATT-1"),
        TurnRef("turn-other", "epoch-1", "generation-1", "ATT-1"),
    ):
        with pytest.raises(BrokerProtocolError, match="protocol order"):
            proxy.collect_retained_plain_text_evidence(spliced)


def test_proxy_refuses_evidence_bound_to_a_different_generation():
    drifted = _retained_evidence(generation="generation-other")
    client = _ScriptedBrokerClient(
        [_collect_response({"retained_plain_input_evidence": to_wire(drifted)})]
    )
    proxy = _proxy(client)
    _begin_turn(proxy)
    proxy.read_events(CURSOR)
    with pytest.raises(BrokerProtocolError, match="bound to a different turn"):
        proxy.collect_retained_plain_text_evidence(TURN)


def test_proxy_stale_generation_never_answers_a_new_generation_turn():
    first = _collect_response(
        {"retained_plain_input_evidence": to_wire(_retained_evidence())}
    )
    second_turn = TurnRef("turn-1", "epoch-1", "generation-2", "ATT-1")
    second = dict(_collect_response())
    second["cursor"] = to_wire(
        EventCursor("ATT-1", "epoch-1", "generation-2", turn_id="turn-1")
    )
    second["retained_plain_input_evidence"] = None
    client = _ScriptedBrokerClient([first, second])
    proxy = _proxy(client)
    _begin_turn(proxy)
    proxy.read_events(CURSOR)
    # The stale generation's cache entry cannot answer a new-generation turn
    # sharing the same turn_id: it must be collected on its own TurnRef.
    with pytest.raises(BrokerProtocolError, match="protocol order"):
        proxy.collect_retained_plain_text_evidence(second_turn)
    _begin_turn(
        proxy,
        turn=second_turn,
        generation=ProcessGenerationRef("generation-2", "epoch-1", 2, "codex-01"),
        command_id="ohf-op:continuation:ATT-1:turn-1:g2",
    )
    proxy.read_events(
        EventCursor("ATT-1", "epoch-1", "generation-2", turn_id="turn-1")
    )
    assert proxy.collect_retained_plain_text_evidence(second_turn) is None
    # And the old TurnRef still reads only its own generation's evidence.
    assert proxy.collect_retained_plain_text_evidence(TURN) == _retained_evidence()


def test_proxy_preserves_the_existing_candidate_and_raw_behavior():
    client = _ScriptedBrokerClient(
        [_collect_response({"retained_plain_input_evidence": to_wire(_retained_evidence())})]
    )
    proxy = _proxy(client)
    _begin_turn(proxy)
    proxy.read_events(CURSOR)
    candidate = proxy.collect_candidate_result(TURN)
    raw = proxy.observe_raw_role_result(TURN)
    assert candidate.attempt_id == "ATT-1"
    assert raw.provider_native_turn_id == "native-turn-1"


def test_executive_worker_broker_owns_the_collect_evidence_emission():
    import inspect

    entry = inspect.getsource(ExecutiveWorkerBroker._ohf_collect_turn)
    assert entry.count("self._operator_collection_transaction(") == 1
    assert "asyncio.shield(task)" in entry
    source = inspect.getsource(ExecutiveWorkerBroker._operator_collection_transaction)
    # The accepted collector is reached only behind the transient mark, and
    # only through the guarded helper, never directly off the adapter.
    assert "retained_plain_turns.get(turn) == state.generation" in source
    assert source.index(
        "retained_plain_turns.get(turn) == state.generation"
    ) < source.index('"retained_plain_input_evidence"')
    assert "state.adapter.collect_retained_plain_text_evidence" not in source
    helper = inspect.getsource(ExecutiveWorkerBroker._retained_plain_input_evidence)
    assert "collect_retained_plain_text_evidence" in helper
    assert "wire_retained_plain_input_evidence(encoded)" in helper


@pytest.mark.parametrize("acknowledged,native_id", [(False, "native-turn-1"), (True, "")])
def test_refused_begin_never_selects_broker_retained_input(tmp_path, acknowledged, native_id):
    async def scenario():
        broker, peer, profile, made = _evidence_broker(tmp_path, evidence=_retained_evidence())
        launch = await _start_generation(broker, peer, profile)
        original = made[-1].begin_turn
        made[-1].begin_turn = lambda **kwargs: dataclasses.replace(
            original(**kwargs), acknowledged=acknowledged, provider_native_turn_id=native_id)
        await _begin(broker, peer, GENERATION, launch, TURN,
                     "ohf-op:continuation:ATT-1:turn-1")
        result = await _collect(broker, peer, TURN)
        assert made[-1].collector_turns == []
        assert "retained_plain_input_evidence" not in result
    asyncio.run(scenario())


@pytest.mark.parametrize("acknowledged,native_id", [(False, "native-turn-1"), (True, "")])
def test_refused_begin_never_selects_proxy_retained_input(acknowledged, native_id):
    class RefusedClient(_ScriptedBrokerClient):
        def request_sync(self, operation, payload, **kwargs):
            if operation == "ohf-begin-turn":
                return {"observation": to_wire(TurnStartObservation(native_id, acknowledged))}
            return super().request_sync(operation, payload, **kwargs)
    proxy = _proxy(RefusedClient([
        _collect_response({"retained_plain_input_evidence": to_wire(_retained_evidence())})]))
    _begin_turn(proxy)
    with pytest.raises(BrokerProtocolError):
        proxy.read_events(CURSOR)
        proxy.collect_retained_plain_text_evidence(TURN)


@pytest.mark.parametrize("field,value", [
    ("provider_native_turn_id", "native-spliced"),
    ("provider_session_id", "thread-spliced"),
])
def test_proxy_evidence_must_match_acknowledged_native_turn_and_raw_binding(field, value):
    evidence = dataclasses.replace(_retained_evidence(), **{field: value})
    proxy = _proxy(_ScriptedBrokerClient([
        _collect_response({"retained_plain_input_evidence": to_wire(evidence)})]))
    _begin_turn(proxy)
    with pytest.raises(BrokerProtocolError):
        proxy.read_events(CURSOR)
        proxy.collect_retained_plain_text_evidence(TURN)
