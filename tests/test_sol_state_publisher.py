from __future__ import annotations

import ast
import asyncio
import functools
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from common import executive_hot_state_contract as hot_contract
from integrations.slack_executive import sol_state


def _sync_test(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapped


BOT = "U-B1-RELAY-FIXTURE"
CHANNEL = "C-B1-DEVELOPMENT-FIXTURE"


def _at(minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 8, 21, 12, minute, second, tzinfo=timezone.utc)


def _executive(*, generated_at: str = "2026-08-21T12:00:00Z", marker: str = "a"):
    value = {
        "schema": sol_state.HOT_STATE_SCHEMA,
        "generated_at": generated_at,
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
            "jobs": {
                "total": 0,
                "by_status": {name: 0 for name in hot_contract.JOB_STATUS_VALUES},
            },
            "attempts": {
                "total": 0,
                "by_status": {
                    name: 0 for name in hot_contract.ATTEMPT_STATUS_VALUES
                },
            },
            "workers": {
                "total": 0,
                "by_status": {
                    name: 0 for name in hot_contract.WORKER_STATUS_VALUES
                },
            },
        },
        "degraded": [],
        "do_not_submit": False,
    }
    value["snapshot_hash"] = hot_contract.semantic_snapshot_hash(value)
    return value


def _document(text: str):
    first, payload = text.split("\n", 1)
    assert first == sol_state.DISCRIMINATOR
    return json.loads(payload)


def _expected_wrapper_state_hash(document: dict) -> str:
    semantic = dict(document)
    semantic.pop("generated_at")
    semantic.pop("relay_checked_at")
    semantic.pop("state_hash")
    return hashlib.sha256(
        json.dumps(
            semantic,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _assert_outer_wrapper_hash(document: dict) -> None:
    state_hash = document["state_hash"]
    assert isinstance(state_hash, str)
    assert re.fullmatch(r"[0-9a-f]{64}", state_hash) is not None
    assert state_hash == _expected_wrapper_state_hash(document)


class _FakeClient:
    def __init__(self, messages=(), *, complete: bool = True):
        self.messages = list(messages)
        self.complete = complete
        self.history_calls = []
        self.creates = []
        self.updates = []
        self._next_ts = 1

    async def fetch_history(self, *, channel_id: str, limit: int):
        self.history_calls.append((channel_id, limit))
        return sol_state.HistoryPage(tuple(self.messages), self.complete)

    async def create_message(self, *, channel_id: str, text: str):
        self.creates.append((channel_id, text))
        message = sol_state.StateMessage(str(self._next_ts), BOT, text)
        self._next_ts += 1
        self.messages.append(message)
        return message

    async def update_message(self, *, channel_id: str, message_ts: str, text: str):
        self.updates.append((channel_id, message_ts, text))
        for index, message in enumerate(self.messages):
            if message.ts == message_ts:
                updated = sol_state.StateMessage(message_ts, BOT, text)
                self.messages[index] = updated
                return updated
        raise AssertionError("publisher attempted to update an absent message")


@_sync_test
async def test_zero_history_creates_one_state_message_and_receipt_exposes_outer_wrapper_hash():
    client = _FakeClient()
    executive = _executive()
    publisher = sol_state.SolStatePublisher(
        client, channel_id=CHANNEL, bot_user_id=BOT
    )
    receipt = await publisher.publish(executive, relay_checked_at=_at())
    assert receipt.action == "created"
    assert receipt.message_ts == "1"
    assert receipt.byte_count <= sol_state.MAX_MESSAGE_BYTES
    assert len(client.messages) == 1
    assert len(client.creates) == 1
    assert client.updates == []
    document = _document(client.messages[0].text)
    assert document["status"] == "OK"
    _assert_outer_wrapper_hash(document)
    assert receipt.state_hash == document["state_hash"]
    assert receipt.state_hash != executive["snapshot_hash"]
    assert document["relay"] == {
        "state_publisher": "READY",
        "command_transport": "NOT_INSTALLED",
        "reconciliation": "NOT_REQUIRED",
        "version": sol_state.DEFAULT_RELAY_VERSION,
    }
    assert document["do_not_submit"] is True


@_sync_test
async def test_one_exact_message_recovers_and_updates_without_duplicate():
    old = sol_state.StateMessage(
        "9", BOT, sol_state.render_sol_state(_executive(), relay_checked_at=_at())
    )
    client = _FakeClient([old])
    publisher = sol_state.SolStatePublisher(
        client, channel_id=CHANNEL, bot_user_id=BOT
    )
    changed = _executive(marker="b")
    receipt = await publisher.publish(changed, relay_checked_at=_at(1))
    assert receipt.action == "updated"
    assert receipt.message_ts == "9"
    assert len(client.messages) == 1
    assert client.creates == []
    assert len(client.updates) == 1
    document = _document(client.messages[0].text)
    _assert_outer_wrapper_hash(document)
    assert document["state_hash"] != changed["snapshot_hash"]


@_sync_test
async def test_restart_recovers_created_message_and_never_duplicates():
    client = _FakeClient()
    first = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    await first.publish(_executive(), relay_checked_at=_at())

    restarted = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    receipt = await restarted.publish(_executive(), relay_checked_at=_at(1))
    assert receipt.action == "updated"
    assert len(client.messages) == 1
    assert len(client.creates) == 1
    assert len(client.updates) == 1


@_sync_test
async def test_concurrent_first_publishes_serialize_to_one_message():
    client = _FakeClient()
    publisher = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    receipts = await asyncio.gather(
        publisher.publish(_executive(), relay_checked_at=_at()),
        publisher.publish(_executive(marker="b"), relay_checked_at=_at(1)),
    )
    assert {receipt.action for receipt in receipts} == {"created", "updated"}
    assert len(client.messages) == 1
    assert len(client.creates) == 1
    assert len(client.updates) == 1


@_sync_test
async def test_recovery_filters_exact_bot_and_exact_discriminator():
    exact = sol_state.StateMessage(
        "3", BOT, sol_state.render_sol_state(_executive(), relay_checked_at=_at())
    )
    other_bot = sol_state.StateMessage("4", "U-OTHER", exact.text)
    wrong_discriminator = sol_state.StateMessage(
        "5", BOT, "MMX/SOL_STATE_V10\n{}"
    )
    no_payload_line = sol_state.StateMessage("6", BOT, sol_state.DISCRIMINATOR)
    client = _FakeClient([other_bot, wrong_discriminator, no_payload_line, exact])
    publisher = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    assert await publisher.recover() == "3"


@_sync_test
async def test_more_than_one_exact_message_fails_closed_ambiguous():
    text = sol_state.render_sol_state(_executive(), relay_checked_at=_at())
    client = _FakeClient(
        [
            sol_state.StateMessage("1", BOT, text),
            sol_state.StateMessage("2", BOT, text),
        ]
    )
    publisher = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    with pytest.raises(sol_state.SolStateError) as caught:
        await publisher.publish(_executive(), relay_checked_at=_at())
    assert caught.value.code == "STATE_MESSAGE_AMBIGUOUS"
    assert client.creates == []
    assert client.updates == []


@_sync_test
async def test_incomplete_history_fails_closed_before_create_or_update():
    client = _FakeClient(complete=False)
    publisher = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    with pytest.raises(sol_state.SolStateError) as caught:
        await publisher.publish(_executive(), relay_checked_at=_at())
    assert caught.value.code == "STATE_HISTORY_INCOMPLETE"
    assert client.creates == []
    assert client.updates == []


def test_clock_only_wrapper_change_keeps_outer_hash_and_executive():
    executive = _executive()
    first = _document(
        sol_state.render_sol_state(executive, relay_checked_at=_at(0, 30))
    )
    heartbeat = _document(
        sol_state.render_sol_state(executive, relay_checked_at=_at(1, 30))
    )
    assert first["relay_checked_at"] != heartbeat["relay_checked_at"]
    _assert_outer_wrapper_hash(first)
    _assert_outer_wrapper_hash(heartbeat)
    assert first["state_hash"] == heartbeat["state_hash"]
    assert first["generated_at"] == heartbeat["generated_at"]
    assert first["executive"] == heartbeat["executive"]
    first_without_clock = {k: v for k, v in first.items() if k != "relay_checked_at"}
    heartbeat_without_clock = {
        k: v for k, v in heartbeat.items() if k != "relay_checked_at"
    }
    assert first_without_clock == heartbeat_without_clock


def test_outer_generated_at_is_excluded_from_wrapper_hash():
    document = _document(
        sol_state.render_sol_state(_executive(), relay_checked_at=_at())
    )
    changed_generated_at = dict(document)
    changed_generated_at["generated_at"] = "2026-08-21T12:59:59Z"
    assert _expected_wrapper_state_hash(document) == _expected_wrapper_state_hash(
        changed_generated_at
    )
    assert document["state_hash"] == sol_state.semantic_sol_state_hash(
        changed_generated_at
    )


def test_nested_executive_generated_at_change_updates_outer_hash():
    first_executive = _executive(generated_at="2026-08-21T11:59:58Z")
    changed_executive = _executive(generated_at="2026-08-21T11:59:59Z")
    assert hot_contract.validate_hot_state_document(first_executive)
    assert hot_contract.validate_hot_state_document(changed_executive)
    assert first_executive["snapshot_hash"] == changed_executive["snapshot_hash"]

    first = _document(sol_state.render_sol_state(first_executive, relay_checked_at=_at()))
    changed = _document(
        sol_state.render_sol_state(changed_executive, relay_checked_at=_at())
    )
    _assert_outer_wrapper_hash(first)
    _assert_outer_wrapper_hash(changed)
    assert first["generated_at"] != changed["generated_at"]
    assert first["executive"]["generated_at"] != changed["executive"]["generated_at"]
    assert first["state_hash"] != changed["state_hash"]


def test_valid_rehashed_executive_semantic_change_updates_outer_hash():
    first_executive = _executive()
    changed_executive = _executive(marker="b")
    assert hot_contract.validate_hot_state_document(first_executive)
    assert hot_contract.validate_hot_state_document(changed_executive)
    assert first_executive["snapshot_hash"] != changed_executive["snapshot_hash"]
    first = _document(sol_state.render_sol_state(first_executive, relay_checked_at=_at()))
    changed = _document(
        sol_state.render_sol_state(changed_executive, relay_checked_at=_at())
    )
    _assert_outer_wrapper_hash(first)
    _assert_outer_wrapper_hash(changed)
    assert first["state_hash"] != changed["state_hash"]
    assert first["executive"] != changed["executive"]


def test_same_executive_relay_version_change_updates_outer_hash():
    executive = _executive()
    first = _document(sol_state.render_sol_state(executive, relay_checked_at=_at()))
    changed = _document(
        sol_state.render_sol_state(
            executive,
            relay_checked_at=_at(),
            relay_version="mas-108-b1-development-next",
        )
    )
    _assert_outer_wrapper_hash(first)
    _assert_outer_wrapper_hash(changed)
    assert first["executive"] == changed["executive"] == executive
    assert first["relay"]["version"] != changed["relay"]["version"]
    assert first["state_hash"] != changed["state_hash"]


def test_semantic_change_with_stale_claimed_hash_fails_closed_invalid():
    executive = _executive()
    executive["service"]["service_state"] = "QUARANTINED"
    document = _document(
        sol_state.render_sol_state(executive, relay_checked_at=_at())
    )
    assert document["status"] == "DEGRADED"
    assert document["executive"] is None
    _assert_outer_wrapper_hash(document)
    assert document["relay_degraded"] == ["EXECUTIVE_STATE_INVALID"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state["grounding"].update(mastermind_sha="not-a-sha"),
        lambda state: state["grounding"].update(boot_packet_schema="wrong"),
        lambda state: state["service"].update(service_state="TOTALLY_READY"),
        lambda state: state["runtime"]["jobs"].update(by_status={}),
        lambda state: state["degraded"].append("ARBITRARY_PROVIDER_DIAGNOSIS"),
        lambda state: state.update(do_not_submit=True),
    ],
    ids=[
        "bad-grounding-sha",
        "bad-boot-schema",
        "open-service-vocabulary",
        "missing-enum-census",
        "open-degradation-vocabulary",
        "inconsistent-submit-policy",
    ],
)
def test_self_hashed_but_contract_invalid_state_fails_closed(mutate):
    executive = _executive()
    mutate(executive)
    executive["snapshot_hash"] = hot_contract.semantic_snapshot_hash(executive)

    document = _document(
        sol_state.render_sol_state(executive, relay_checked_at=_at())
    )

    assert document["status"] == "DEGRADED"
    assert document["executive"] is None
    _assert_outer_wrapper_hash(document)
    assert document["relay_degraded"] == ["EXECUTIVE_STATE_INVALID"]
    assert document["do_not_submit"] is True


@pytest.mark.parametrize(
    ("executive", "checked", "code"),
    [
        (None, _at(), "EXECUTIVE_STATE_UNAVAILABLE"),
        ({"schema": "wrong"}, _at(), "EXECUTIVE_STATE_INVALID"),
        (_executive(), _at(3), "EXECUTIVE_STATE_STALE"),
        (_executive(generated_at="2026-08-21T12:01:00Z"), _at(), "EXECUTIVE_STATE_INVALID"),
    ],
)
def test_unavailable_stale_or_invalid_state_replaces_old_green_values(
    executive, checked, code
):
    document = _document(
        sol_state.render_sol_state(executive, relay_checked_at=checked)
    )
    assert document["status"] == "DEGRADED"
    assert document["executive"] is None
    _assert_outer_wrapper_hash(document)
    assert document["relay_degraded"] == [code]
    assert document["do_not_submit"] is True


def test_degraded_null_executive_has_deterministic_non_null_outer_hash():
    first = _document(sol_state.render_sol_state(None, relay_checked_at=_at()))
    heartbeat = _document(sol_state.render_sol_state(None, relay_checked_at=_at(1)))
    assert first["status"] == heartbeat["status"] == "DEGRADED"
    assert first["executive"] is heartbeat["executive"] is None
    _assert_outer_wrapper_hash(first)
    _assert_outer_wrapper_hash(heartbeat)
    assert first["state_hash"] == heartbeat["state_hash"]


def test_4500_byte_ceiling_refuses_without_truncation():
    with pytest.raises(sol_state.SolStateError) as caught:
        sol_state.render_sol_state(
            _executive(),
            relay_checked_at=_at(),
            relay_version="界" * sol_state.MAX_MESSAGE_BYTES,
        )
    assert caught.value.code == "SOL_STATE_TOO_LARGE"


def test_ascii_relay_version_accepts_exact_4500_bytes_and_refuses_4501():
    single_character_text = sol_state.render_sol_state(
        None,
        relay_checked_at=_at(),
        relay_version="a",
    )
    relay_version = "a" * (
        sol_state.MAX_MESSAGE_BYTES - len(single_character_text.encode("utf-8")) + 1
    )
    fixed_message_bytes = len(single_character_text.encode("utf-8")) - 1
    assert fixed_message_bytes + len(relay_version) == sol_state.MAX_MESSAGE_BYTES
    assert fixed_message_bytes + len(relay_version) + 1 == (
        sol_state.MAX_MESSAGE_BYTES + 1
    )

    accepted = sol_state.render_sol_state(
        None,
        relay_checked_at=_at(),
        relay_version=relay_version,
    )
    assert len(accepted.encode("utf-8")) == sol_state.MAX_MESSAGE_BYTES

    with pytest.raises(sol_state.SolStateError) as caught:
        sol_state.render_sol_state(
            None,
            relay_checked_at=_at(),
            relay_version=f"{relay_version}a",
        )
    assert caught.value.code == "SOL_STATE_TOO_LARGE"


@_sync_test
async def test_malformed_write_receipt_fails_closed():
    class _WrongAuthor(_FakeClient):
        async def create_message(self, *, channel_id: str, text: str):
            return sol_state.StateMessage("1", "U-WRONG", text)

    client = _WrongAuthor()
    publisher = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    with pytest.raises(sol_state.SolStateError) as caught:
        await publisher.publish(_executive(), relay_checked_at=_at())
    assert caught.value.code == "STATE_PUBLICATION_REFUSED"


@_sync_test
async def test_client_dependency_exceptions_are_fixed_fail_closed_codes():
    class _HistoryFailure(_FakeClient):
        async def fetch_history(self, *, channel_id: str, limit: int):
            raise RuntimeError("/Users/operator/private xoxb-secret")

    publisher = sol_state.SolStatePublisher(
        _HistoryFailure(), channel_id=CHANNEL, bot_user_id=BOT
    )
    with pytest.raises(sol_state.SolStateError) as caught:
        await publisher.publish(_executive(), relay_checked_at=_at())
    assert caught.value.code == "STATE_HISTORY_INCOMPLETE"
    assert "/Users/operator" not in str(caught.value)
    assert "xoxb-secret" not in str(caught.value)


@_sync_test
async def test_effect_unknown_create_rerecovers_before_retry_and_never_duplicates():
    class _CreateAckLoss(_FakeClient):
        def __init__(self):
            super().__init__()
            self.fail_once = True

        async def create_message(self, *, channel_id: str, text: str):
            message = await super().create_message(channel_id=channel_id, text=text)
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("remote create committed but response was lost")
            return message

    client = _CreateAckLoss()
    publisher = sol_state.SolStatePublisher(client, channel_id=CHANNEL, bot_user_id=BOT)
    with pytest.raises(sol_state.SolStateError) as caught:
        await publisher.publish(_executive(), relay_checked_at=_at())
    assert caught.value.code == "STATE_PUBLICATION_REFUSED"
    assert len(client.messages) == 1

    receipt = await publisher.publish(_executive(), relay_checked_at=_at(1))
    assert receipt.action == "updated"
    assert len(client.messages) == 1
    assert len(client.creates) == 1
    assert len(client.updates) == 1


def test_publisher_static_no_store_no_raw_sql_no_inbound_fences():
    path = Path(sol_state.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.names[0].name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "sqlite3" not in imports
    assert "sqlalchemy" not in imports
    assert not any(name.startswith("control_plane") for name in imports)
    assert "slack_sdk" not in imports
    assert "SELECT " not in source
    assert "PRAGMA " not in source
    assert "EXECOS/CEO_REQUEST_V1" not in source
    assert "SocketMode" not in source
    assert "replay_cursor" not in source
    assert "message_ts_path" not in source
