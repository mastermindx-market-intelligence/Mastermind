"""Observe-turn grants must match an independently derived full TurnKey."""
from __future__ import annotations

import asyncio
import copy
import dataclasses

import pytest

from control_plane.executive_worker_broker import BrokerStateError
from control_plane.operator_harness_contract import (
    OperationId,
    ProcessGenerationRef,
    SessionEpochRef,
    TurnRef,
    compare_launch,
)
from control_plane.operator_harness_wire import to_wire
from tests.test_executive_operator_broker import (
    _fixture,
    _lc1_broker_turn,
    _materialization_payload,
    _observer_payload,
    _request,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt_id", "ATT-BOUNDARY-OTHER"),
        ("session_epoch_id", "epoch-boundary-other"),
        ("process_generation_id", "generation-boundary-other"),
        ("generation_number", 2),
        ("worker_id", "codex-other"),
        ("local_turn_id", "turn-other"),
    ],
)
def test_ohf_observe_turn_rejects_each_grant_key_identity_mutation(
    tmp_path, field, value
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "key-mutation", "bound viewer"
        )
        projection = adapters[-1].visible_turn_projection
        exact_grant = adapters[-1].mint_observer_grant(turn)
        expected_key = projection.check_grant(exact_grant)
        assert expected_key is not None
        mutated_key = dataclasses.replace(expected_key, **{field: value})
        grant = projection.mint_grant(mutated_key)

        with pytest.raises(BrokerStateError, match="GENERATION_INVALID"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(turn, grant),
                    f"key-{field}",
                ),
                peer=peer,
            )

        assert projection.check_grant(grant) == mutated_key
        assert broker._observer_refusals[-1] == (mutated_key, "GENERATION_INVALID")
        assert mutated_key != expected_key

    asyncio.run(scenario())


def test_ohf_observe_turn_exact_key_read_and_viewer_path_do_not_mutate_worker(
    tmp_path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "exact-key", "exact bound viewer"
        )
        adapter = adapters[-1]
        grant = adapter.mint_observer_grant(turn)
        adapter.publish_visible("visible exact key", "partial")
        lifecycle_before = list(adapter.lifecycle)
        prompts_before = list(adapter.prompts)

        observed = await broker.execute(
            _request("ohf-observe-turn", _observer_payload(turn, grant), "exact"),
            peer=peer,
        )

        assert [item["text"] for item in observed["result"]["items"]] == [
            "visible exact key"
        ]
        assert observed["result"]["terminal"] is False
        assert adapter.lifecycle == lifecycle_before
        assert adapter.prompts == prompts_before
        assert adapter.visible_turn_projection.check_grant(grant) is not None

    asyncio.run(scenario())


def test_ohf_observe_turn_rejects_changed_native_turn_id_with_shared_projection_record(
    tmp_path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "native-shared", "native turn viewer"
        )
        adapter = adapters[-1]
        projection = adapter.visible_turn_projection
        exact_key = projection.check_grant(adapter.mint_observer_grant(turn))
        assert exact_key is not None
        shared_native_key = dataclasses.replace(exact_key, local_turn_id="turn-shared")
        projection.publish(
            dataclasses.replace(
                shared_native_key, native_turn_id=exact_key.native_turn_id
            ),
            method="item/completed",
            params={
                "item": {
                    "type": "agentMessage",
                    "id": "shared-turn-item",
                    "sequence": 1,
                    "text": "shared native identity",
                }
            },
        )
        grant = projection.mint_grant(shared_native_key)

        with pytest.raises(BrokerStateError, match="GENERATION_INVALID"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(turn, grant),
                    "native-shared",
                ),
                peer=peer,
            )

        assert broker._observer_refusals[-1] == (
            shared_native_key,
            "GENERATION_INVALID",
        )

    asyncio.run(scenario())


def test_ohf_observe_turn_rejects_unbound_changed_native_turn_id(tmp_path) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "native-unbound", "native turn viewer"
        )
        adapter = adapters[-1]
        projection = adapter.visible_turn_projection
        exact_key = projection.check_grant(adapter.mint_observer_grant(turn))
        assert exact_key is not None
        grant = projection.mint_grant(
            dataclasses.replace(exact_key, native_turn_id="native-turn-other")
        )

        with pytest.raises(BrokerStateError, match="TURN_NOT_BOUND"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(turn, grant),
                    "native-unbound",
                ),
                peer=peer,
            )

        assert broker._observer_refusals[-1][1] == "TURN_NOT_BOUND"

    asyncio.run(scenario())


def test_ohf_observe_turn_rejects_wrong_request_attempt(tmp_path) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "wrong-attempt", "wrong attempt viewer"
        )
        grant = adapters[-1].mint_observer_grant(turn)

        with pytest.raises(BrokerStateError, match="GENERATION_INVALID"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(turn, grant, attempt="ATT-OTHER"),
                    "wrong-attempt",
                ),
                peer=peer,
            )

        assert broker._observer_refusals[-1] == (None, "GENERATION_INVALID")

    asyncio.run(scenario())


def test_ohf_observe_turn_rejects_revoked_grant(tmp_path) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "revoked", "revoked viewer"
        )
        grant = adapters[-1].mint_observer_grant(turn)
        adapters[-1].visible_turn_projection.revoke_grant(grant)

        with pytest.raises(BrokerStateError, match="READER_REVOKED"):
            await broker.execute(
                _request("ohf-observe-turn", _observer_payload(turn, grant), "revoked"),
                peer=peer,
            )

        assert broker._observer_refusals[-1] == (None, "READER_REVOKED")

    asyncio.run(scenario())


def test_ohf_observe_turn_rejects_grant_revoked_between_grant_and_read(
    tmp_path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "late-revoke", "late revoke viewer"
        )
        adapter = adapters[-1]
        grant = adapter.mint_observer_grant(turn)
        adapter.publish_visible("never read after revocation", "partial")
        adapter.visible_turn_projection.revoke_grant(grant)

        with pytest.raises(BrokerStateError, match="READER_REVOKED"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(turn, grant),
                    "late-revoke",
                ),
                peer=peer,
            )

        assert adapter.visible_turn_projection.check_grant(grant) is None
        assert broker._observer_refusals[-1] == (None, "READER_REVOKED")

    asyncio.run(scenario())


def test_ohf_observe_turn_rejects_grant_from_earlier_generation(tmp_path) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-transition", "ATT-TRANSITION", "codex-01", 1)
        first_generation = ProcessGenerationRef(
            "generation-transition-1", epoch.session_epoch_id, 1, "codex-01"
        )
        turn = TurnRef(
            "turn-transition",
            epoch.session_epoch_id,
            first_generation.process_generation_id,
            epoch.attempt_id,
        )

        async def start_and_begin(generation, suffix, *, resume):
            await broker.execute(
                _request(
                    "ohf-resume" if resume else "ohf-start",
                    _materialization_payload(
                        profile, epoch, generation, resume=resume
                    ),
                    f"{suffix}-start",
                ),
                peer=peer,
            )
            attestation = adapters[-1].observed_attestation(generation)
            await broker.execute(
                _request(
                    "ohf-begin-turn",
                    {
                        "operation_id": to_wire(
                            OperationId(f"ohf-op:{suffix}-turn")
                        ),
                        "turn": to_wire(
                            turn if not resume else active_turn
                        ),
                        "generation": to_wire(generation),
                        "launch": to_wire(compare_launch(profile, attestation)),
                        "prompt": "generation transition viewer",
                    },
                    f"{suffix}-turn",
                ),
                peer=peer,
            )

        await start_and_begin(first_generation, "one", resume=False)
        stale_grant = adapters[-1].mint_observer_grant(turn)
        stale_key = adapters[-1].visible_turn_projection.check_grant(stale_grant)
        assert stale_key is not None
        stale_key_before_stop = copy.copy(stale_key)
        await broker.execute(
            _request(
                "ohf-stop",
                {
                    "operation_id": to_wire(
                        OperationId("ohf-op:transition-stop-one")
                    ),
                    "generation": to_wire(first_generation),
                },
                "transition-stop-one",
            ),
            peer=peer,
        )
        second_generation = ProcessGenerationRef(
            "generation-transition-2", epoch.session_epoch_id, 2, "codex-01"
        )
        active_turn = dataclasses.replace(
            turn, process_generation_id=second_generation.process_generation_id
        )
        await start_and_begin(second_generation, "two", resume=True)
        projection = adapters[-1].visible_turn_projection
        stale_grant = projection.mint_grant(stale_key_before_stop)

        with pytest.raises(BrokerStateError, match="GENERATION_INVALID"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(active_turn, stale_grant),
                    "generation-transition",
                ),
                peer=peer,
            )

        assert broker._observer_refusals[-1] == (
            stale_key,
            "GENERATION_INVALID",
        )

    asyncio.run(scenario())
