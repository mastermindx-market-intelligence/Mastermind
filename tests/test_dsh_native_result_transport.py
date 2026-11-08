"""The existing broker wire carries exactly the profile-selected result kind."""
import asyncio
import copy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from control_plane.executive_worker_broker import ExecutiveWorkerBroker, BrokerProtocolError
from control_plane.native_conversation_result import (
    DSH_NATIVE_RESULT_CONTRACT, ROLE_RESULT_CONTRACT, NativeConversationResultError,
    result_contract_for_profile,
)
from control_plane.operator_harness_wire import native_conversation_result_observation, to_wire
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from tests.test_dsh_native_operator import fixture, start, begin, cursor


async def collected(tmp_path, monkeypatch):
    f = await fixture(tmp_path, monkeypatch)
    await start(f)
    await begin(f)
    f.adapter.native.done.set()
    # Exercise the incumbent collection transaction without constructing another
    # process/session owner. Lifecycle admission is covered separately.
    broker = object.__new__(ExecutiveWorkerBroker)
    broker._state_lock = asyncio.Lock()
    state = SimpleNamespace(adapter=f.adapter, requested=f.requested, retained_plain_turns={},
                            generation=f.generation, collection_task=None)
    result = await broker._operator_collection_transaction(state, f.turn, cursor(f), 30)
    return f, result


def proxy(f, response, *, contract=DSH_NATIVE_RESULT_CONTRACT):
    class Client:
        def request_sync(self, method, payload, **kwargs):
            assert method == "ohf-collect-turn"
            assert payload["turn"]["turn_id"] == f.turn.turn_id
            return json.loads(json.dumps(response))
    return RemoteOperatorHarnessAdapter(Client(), turn_input_loader=lambda _turn: "",
        capabilities=f.adapter.describe_capabilities(), result_contract=contract)


def test_existing_broker_and_remote_preserve_closed_native_observation(tmp_path, monkeypatch):
    async def exercise():
        f, response = await collected(tmp_path, monkeypatch)
        assert set(response) == {"events", "cursor", "candidate", "native_conversation_result"}
        native = response["native_conversation_result"]
        assert native["native_claim"]["requestId"] == 1
        assert "request_id" not in native["native_claim"]
        observed = native_conversation_result_observation(native)
        assert to_wire(observed) == native
        remote = proxy(f, response)
        events, next_cursor = await asyncio.to_thread(remote.read_events, cursor(f))
        assert events and next_cursor.local_sequence == len(events)
        assert remote.observe_native_conversation_result(f.turn) == observed
        assert remote.collect_candidate_result(f.turn).artifact_digest == observed.provider_turn_artifact_digest
        with pytest.raises(BrokerProtocolError):
            remote.observe_raw_role_result(f.turn)
        with pytest.raises(BrokerProtocolError, match="another turn binding"):
            remote.collect_candidate_result(replace(f.turn, process_generation_id="foreign-generation"))
        assert result_contract_for_profile(f.requested) == DSH_NATIVE_RESULT_CONTRACT
        with pytest.raises(NativeConversationResultError):
            result_contract_for_profile(replace(f.requested, provider="foreign-provider"))
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ("mixed", "missing", "wrong-contract", "digest", "foreign-turn", "request-type", "retained-plain"))
def test_native_collection_cannot_substitute_result_or_authority(tmp_path, monkeypatch, case):
    async def exercise():
        f, response = await collected(tmp_path, monkeypatch)
        response = copy.deepcopy(response)
        contract = DSH_NATIVE_RESULT_CONTRACT
        if case == "mixed":
            response["raw_role_result"] = {}
        elif case == "missing":
            response.pop("native_conversation_result")
        elif case == "wrong-contract":
            contract = ROLE_RESULT_CONTRACT
        elif case == "digest":
            response["candidate"]["artifact_digest"] = "0"*64
        elif case == "foreign-turn":
            response["native_conversation_result"]["turn_id"] = "foreign-turn"
        elif case == "request-type":
            response["native_conversation_result"]["native_terminal"]["requestId"] = "1"
        else:
            response["retained_plain_input_evidence"] = {}
        remote = proxy(f, response, contract=contract)
        with pytest.raises(BrokerProtocolError):
            await asyncio.to_thread(remote.read_events, cursor(f))
        assert remote._turn_results == {}
    asyncio.run(exercise())
