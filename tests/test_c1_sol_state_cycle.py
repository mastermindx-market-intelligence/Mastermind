from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest

from common import executive_hot_state_contract as hot_contract
from integrations.slack_executive import sol_state
from integrations.slack_executive.sol_state import PublicationReceipt


NOW = datetime(2026, 8, 27, 5, 30, 0, tzinfo=timezone.utc)


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.c1_cycle")
    except ModuleNotFoundError:
        pytest.fail("C1 SOL_STATE cycle is not implemented")


class _Reader:
    def __init__(self, value=None, *, error: Exception | None = None):
        self.value = value
        self.error = error
        self.calls = 0

    async def read_state(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


class _SequenceReader:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    async def read_state(self):
        value = self.values[self.calls]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return value


class _Publisher:
    def __init__(self):
        self.calls = []
        self.recover_calls = 0

    async def recover(self):
        self.recover_calls += 1
        return "1787800000.000001"

    async def publish(self, executive_state, *, relay_checked_at):
        self.calls.append((executive_state, relay_checked_at))
        return PublicationReceipt(
            action="updated",
            message_ts="1787800000.000001",
            state_hash="a" * 64,
            byte_count=321,
        )


def test_run_once_publishes_fresh_reader_result_with_injected_clock():
    c1_cycle = _module()
    state = {"schema": "mastermind.executive_hot_state.v1", "fixture": "fresh"}
    reader = _Reader(state)
    publisher = _Publisher()

    receipt = asyncio.run(
        c1_cycle.run_once(reader=reader, publisher=publisher, now=lambda: NOW)
    )

    assert reader.calls == 1
    assert publisher.calls == [(state, NOW)]
    assert receipt.action == "updated"


def test_run_once_publishes_degraded_none_when_executive_read_is_unavailable():
    c1_cycle = _module()
    reader = _Reader(error=RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"))
    publisher = _Publisher()

    receipt = asyncio.run(
        c1_cycle.run_once(reader=reader, publisher=publisher, now=lambda: NOW)
    )

    assert reader.calls == 1
    assert publisher.calls == [(None, NOW)]
    assert receipt.state_hash == "a" * 64


def test_service_recovers_once_then_change_immediate_and_unchanged_heartbeat_only():
    c1_cycle = _module()
    reader = _SequenceReader(
        [
            RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"),
            RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"),
            RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"),
            {"schema": "wrong-shape"},
        ]
    )
    publisher = _Publisher()

    async def exercise():
        service = c1_cycle.C1RelayService(
            reader=reader,
            publisher=publisher,
            heartbeat_seconds=60,
            max_executive_age_seconds=120,
            relay_version="c1-test",
        )
        await service.recover()
        first = await service.poll_once(now=lambda: NOW)
        skipped = await service.poll_once(now=lambda: NOW + timedelta(seconds=30))
        heartbeat = await service.poll_once(now=lambda: NOW + timedelta(seconds=60))
        changed = await service.poll_once(now=lambda: NOW + timedelta(seconds=75))
        return first, skipped, heartbeat, changed

    first, skipped, heartbeat, changed = asyncio.run(exercise())

    assert publisher.recover_calls == 1
    assert first is not None
    assert skipped is None
    assert heartbeat is not None
    assert changed is not None
    assert [state for state, _when in publisher.calls] == [None, None, {"schema": "wrong-shape"}]
    assert [when for _state, when in publisher.calls] == [
        NOW,
        NOW + timedelta(seconds=60),
        NOW + timedelta(seconds=75),
    ]


# These cases exercise the real validator, wire hash, publisher and cycle.
# Only the external Executive/Slack transports and clocks are inert.
_BOT = "U-C1-CYCLE-TEST"
_CHANNEL = "C-C1-CYCLE-TEST"


def _valid_state(when, *, marker="a", job_count=0):
    value = {
        "schema": hot_contract.HOT_STATE_SCHEMA,
        "generated_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_hash": "0" * 64,
        "grounding": {
            "mastermind_sha": marker * 40,
            "macro_sha": "2" * 40,
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
        },
        "service": {"service_state": "READY", "ceo_admission": "READY"},
        "generic_operator_mutations": "AVAILABLE",
        "runtime": {
            "projection_state": "OK",
            "jobs": {"total": 0, "by_status": dict.fromkeys(hot_contract.JOB_STATUS_VALUES, 0)},
            "attempts": {"total": 0, "by_status": dict.fromkeys(hot_contract.ATTEMPT_STATUS_VALUES, 0)},
            "workers": {"total": 0, "by_status": dict.fromkeys(hot_contract.WORKER_STATUS_VALUES, 0)},
        },
        "degraded": [],
        "do_not_submit": False,
    }
    value["runtime"]["jobs"]["total"] = job_count
    value["runtime"]["jobs"]["by_status"][hot_contract.JOB_STATUS_VALUES[0]] = job_count
    value["snapshot_hash"] = hot_contract.semantic_snapshot_hash(value)
    assert hot_contract.validate_hot_state_document(value)
    return value


class _MemorySlack:
    def __init__(self):
        self.messages = []
        self.writes = []
        self.history_calls = 0
        self.create_calls = 0
        self.fail_next_update = False
        self.lose_create_ack = False
        self.closed = False

    async def fetch_history(self, *, channel_id, limit):
        self.history_calls += 1
        return sol_state.HistoryPage(tuple(self.messages), True)

    async def create_message(self, *, channel_id, text):
        self.create_calls += 1
        message = sol_state.StateMessage(str(self.create_calls), _BOT, text)
        self.messages.append(message)
        self.writes.append(message)
        if self.lose_create_ack:
            self.lose_create_ack = False
            raise RuntimeError("synthetic acknowledgement loss after create")
        return message

    async def update_message(self, *, channel_id, message_ts, text):
        if self.fail_next_update:
            self.fail_next_update = False
            raise RuntimeError("synthetic publication refusal before update")
        for index, old in enumerate(self.messages):
            if old.ts == message_ts:
                message = sol_state.StateMessage(message_ts, _BOT, text)
                self.messages[index] = message
                self.writes.append(message)
                return message
        raise AssertionError("update target does not exist")

    async def aclose(self):
        self.closed = True


def _real_service(reader, client):
    publisher = sol_state.SolStatePublisher(
        client, channel_id=_CHANNEL, bot_user_id=_BOT,
        max_executive_age_seconds=120, relay_version="c1-cycle-test",
    )
    return _module().C1RelayService(
        reader=reader, publisher=publisher, heartbeat_seconds=60,
        max_executive_age_seconds=120, relay_version="c1-cycle-test",
    )


def _wire(message):
    discriminator, payload = message.text.split("\n", 1)
    assert discriminator == sol_state.DISCRIMINATOR
    document = json.loads(payload)
    assert document["state_hash"] == sol_state.semantic_sol_state_hash(document)
    assert document["do_not_submit"] is True
    return document


def test_valid_equal_semantics_skip_thirty_second_poll_but_keep_fresh_heartbeat():
    states = [_valid_state(NOW + timedelta(seconds=s)) for s in (0, 30, 60)]
    assert len({state["snapshot_hash"] for state in states}) == 1
    client = _MemorySlack()
    service = _real_service(_SequenceReader(states), client)

    async def exercise():
        return [await service.poll_once(now=lambda: NOW + timedelta(seconds=s))
                for s in (0, 30, 60)]

    first, skipped, heartbeat = asyncio.run(exercise())
    assert first is not None
    assert skipped is None
    assert heartbeat is not None
    assert len(client.writes) == 2
    assert client.create_calls == 1
    assert len(client.messages) == 1
    first_wire, last_wire = [_wire(message) for message in client.writes]
    assert first_wire["executive"] == states[0]
    assert last_wire["executive"] == states[2]
    assert first.state_hash == first_wire["state_hash"]
    assert heartbeat.state_hash == last_wire["state_hash"]
    # The public integrity hash still covers nested Executive generation time.
    assert first.state_hash != heartbeat.state_hash


def test_valid_runtime_change_publishes_immediately_before_heartbeat():
    client = _MemorySlack()
    states = [_valid_state(NOW), _valid_state(NOW + timedelta(seconds=1), job_count=1)]
    service = _real_service(_SequenceReader(states), client)

    async def exercise():
        await service.poll_once(now=lambda: NOW)
        return await service.poll_once(now=lambda: NOW + timedelta(seconds=1))

    assert asyncio.run(exercise()) is not None
    assert len(client.writes) == 2
    assert _wire(client.writes[-1])["executive"]["runtime"]["jobs"]["total"] == 1


def test_distinct_degradation_and_recovery_publish_without_cached_green():
    states = [
        _valid_state(NOW),
        RuntimeError("unavailable"),
        {"schema": "wrong"},
        _valid_state(NOW - timedelta(seconds=200)),
        _valid_state(NOW + timedelta(seconds=1000)),
        _valid_state(NOW + timedelta(seconds=50)),
    ]
    client = _MemorySlack()
    service = _real_service(_SequenceReader(states), client)

    async def exercise():
        return [await service.poll_once(now=lambda: NOW + timedelta(seconds=10 * i))
                for i in range(len(states))]

    assert all(receipt is not None for receipt in asyncio.run(exercise()))
    documents = [_wire(message) for message in client.writes]
    assert [document["relay_degraded"] for document in documents] == [
        [], ["EXECUTIVE_STATE_UNAVAILABLE"], ["EXECUTIVE_STATE_INVALID"],
        ["EXECUTIVE_STATE_STALE"], ["EXECUTIVE_STATE_INVALID"], [],
    ]
    assert all(document["executive"] is None for document in documents[1:5])
    assert documents[-1]["executive"] == states[-1]


@pytest.mark.parametrize("age,reason", [(-1, "EXECUTIVE_STATE_INVALID"), (120, None),
                                        (121, "EXECUTIVE_STATE_STALE")])
def test_real_future_and_stale_refusal_bounds_are_unchanged(age, reason):
    state = _valid_state(NOW - timedelta(seconds=age))
    client = _MemorySlack()
    service = _real_service(_Reader(state), client)
    asyncio.run(service.poll_once(now=lambda: NOW))
    document = _wire(client.messages[0])
    assert document["relay_degraded"] == ([] if reason is None else [reason])
    assert (document["executive"] is not None) == (reason is None)


def test_failed_heartbeat_does_not_advance_successful_publication_clock():
    client = _MemorySlack()
    service = _real_service(_Reader(_valid_state(NOW)), client)

    async def exercise():
        await service.poll_once(now=lambda: NOW)
        client.fail_next_update = True
        with pytest.raises(sol_state.SolStateError, match="STATE_PUBLICATION_REFUSED"):
            await service.poll_once(now=lambda: NOW + timedelta(seconds=60))
        return await service.poll_once(now=lambda: NOW + timedelta(seconds=61))

    assert asyncio.run(exercise()) is not None
    assert len(client.writes) == 2
    assert _wire(client.writes[-1])["relay_checked_at"] == "2026-08-27T05:31:01Z"


def test_ambiguous_create_recovers_same_message_before_next_publication():
    client = _MemorySlack()
    client.lose_create_ack = True
    service = _real_service(_Reader(_valid_state(NOW)), client)

    async def exercise():
        with pytest.raises(sol_state.SolStateError, match="STATE_PUBLICATION_REFUSED"):
            await service.poll_once(now=lambda: NOW)
        return await service.poll_once(now=lambda: NOW + timedelta(seconds=1))

    receipt = asyncio.run(exercise())
    assert receipt.action == "updated"
    assert client.create_calls == 1
    assert client.history_calls == 2
    assert len(client.messages) == 1


@pytest.mark.parametrize("poll_count", [1, 2])
def test_production_initial_and_loop_reads_use_completion_time(monkeypatch, poll_count):
    entrypoint = importlib.import_module("scripts.c1_sol_state_relay")
    clock = [NOW + timedelta(microseconds=900000)]
    client = _MemorySlack()
    expected = []

    class StopServe(Exception):
        pass

    class AdvancingReader:
        async def read_state(self):
            generated = NOW + timedelta(seconds=1 + 30 * len(expected))
            state = _valid_state(generated, marker="a" if not expected else "b")
            expected.append(state)
            clock[0] = generated + timedelta(microseconds=100000)
            return state

    async def identity(**kwargs):
        return None

    async def sleep(_seconds):
        if len(expected) >= poll_count:
            raise StopServe()
        clock[0] = NOW + timedelta(seconds=30, microseconds=900000)

    config = SimpleNamespace(
        slack_token_file="unused-test-token-path", slack_workspace_id="T-TEST",
        slack_bot_user_id=_BOT, slack_channel_id=_CHANNEL,
        executive_socket="unused-test-socket-path", max_executive_age_seconds=120,
        relay_version="c1-cycle-test", heartbeat_seconds=60, poll_seconds=30,
    )
    monkeypatch.setattr(entrypoint, "assert_relay_principal", lambda: None)
    monkeypatch.setattr(entrypoint, "load_config", lambda _path: config)
    monkeypatch.setattr(entrypoint, "read_token_file", lambda _path: "synthetic-test-token")
    monkeypatch.setattr(entrypoint, "verify_slack_identity", identity)
    monkeypatch.setattr(entrypoint, "CeoIngressStateReader", lambda **_kwargs: AdvancingReader())
    monkeypatch.setattr(entrypoint, "SlackWebApiStateClient", lambda **_kwargs: client)
    monkeypatch.setattr(entrypoint, "_utc_now", lambda: clock[0])
    monkeypatch.setattr(entrypoint.asyncio, "sleep", sleep)
    with pytest.raises(StopServe):
        asyncio.run(entrypoint.serve("unused-test-config-path"))
    assert client.closed
    assert len(expected) == poll_count
    assert [_wire(message)["executive"] for message in client.writes] == expected
    assert all(_wire(message)["relay_degraded"] == [] for message in client.writes)
