"""GBL-2 bridge core + loopback socket service tests (lane GBL, BUILD_PLAN).

BUILD_PLAN "Tests first" for GBL-2: the socket admits peer-uid only;
admission refusals (unknown principal/target/kind, over-ceiling →
RATE_LIMITED); an issue-create timeout reconciles by read-back, never a
second create (EFFECT_UNKNOWN law); a redelivered nudge gives no second job
(ASK_NOT_FOUND no-op); ANSWER_UNCONSUMED surfaces; one re-nudge per
cooldown.  Paperclip is faked (the GblAskStore interface GBL-4 will
implement); no network, no real server, no real t3.  All strings are
harmless fixture words.
"""
from __future__ import annotations

import copy
import os
import socket
from datetime import datetime, timedelta, timezone

import pytest

from common.gbl_contract import (
    GBLContractError,
    mint_ask_id,
)
from integrations.gbl.bridge_service import (
    DEFAULT_ADMISSION_TABLE,
    GblBridge,
    GblBridgeError,
    GblCreateEffectUnknown,
    PrincipalAdmission,
    RENUDGE_COOLDOWN_SECONDS,
)
from integrations.gbl.bridge_service import BridgeServer, BridgeServiceConfig

PRINCIPAL = "grok-account-main"
OTHER_PRINCIPAL = "grok-account-second"
ASK_ID = mint_ask_id(PRINCIPAL, "secretary", "gb-ask-0001")
T0 = datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc)


class FakeStore:
    """The GblAskStore interface GBL-4 implements over Paperclip."""

    def __init__(self, clock=None):
        self.asks: dict[str, dict] = {}
        self.created: list[tuple[str, str]] = []
        self.create_calls = 0
        self.timeout_mode = "none"       # none | landed | absent
        self.clock = clock or (lambda: T0)

    def create_ask(self, ask):
        self.create_calls += 1
        if self.timeout_mode == "landed":
            self._store(ask)
            raise GblCreateEffectUnknown("create response timed out")
        if self.timeout_mode == "absent":
            raise GblCreateEffectUnknown("create request timed out")
        self._store(ask)

    def _store(self, ask):
        if ask["ask_id"] not in self.asks:
            self.asks[ask["ask_id"]] = {**ask, "events": []}
            self.created.append((ask["principal"], self.clock().isoformat()))

    def read_ask(self, ask_id):
        record = self.asks.get(ask_id)
        return copy.deepcopy(record) if record else None

    def append_ask_event(self, ask_id, event):
        record = self.asks[ask_id]
        if event not in record["events"]:
            record["events"].append(dict(event))

    def count_asks(self, principal, since_iso):
        return sum(1 for p, at in self.created if p == principal and at >= since_iso)

    def seed_answer(self, ask_id, text="A harmless fixture answer."):
        self.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32, "text": text})
        self.append_ask_event(ask_id, {"type": "state", "state": "ANSWERED"})


class FakeNudgeSender:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    def send(self, ask_id, state, native_handle):
        self.calls.append((ask_id, state, native_handle))
        return "receipt-fixture"


def admission(**over):
    row = PrincipalAdmission(
        principal=PRINCIPAL,
        targets=frozenset({"secretary", "assurance"}),
        kinds=frozenset({"question", "delegate"}),
        max_asks_per_hour=20,
    )
    for key, value in over.items():
        object.__setattr__(row, key, value)
    return row


def bridge(store=None, *, table=None, clock=None, sender=None) -> GblBridge:
    return GblBridge(
        store if store is not None else FakeStore(),
        admission_table=table if table is not None else (admission(),),
        nudge_sender=sender,
        routine_handle_resolver=lambda principal: "routine-handle-fixture",
        now=clock or (lambda: T0),
    )


def submit(**over):
    args = {
        "principal": PRINCIPAL, "kind": "question", "target": "secretary",
        "title": "Weekly standing check",
        "body": "Please summarize the standing priorities.",
        "idempotency_key": "gb-ask-0001",
    }
    args.update(over)
    return args


# ── Admission (BUILD_PLAN: unknown principal/target/kind, over-ceiling) ─────


class TestAdmission:
    def test_default_table_ships_empty_and_refuses_everything(self):
        assert DEFAULT_ADMISSION_TABLE == ()
        core = bridge(table=DEFAULT_ADMISSION_TABLE)
        with pytest.raises(GblBridgeError) as err:
            core.submit_ask(**submit())
        assert err.value.code == "PRINCIPAL_NOT_ALLOWED"

    def test_unknown_principal_refused(self):
        with pytest.raises(GblBridgeError) as err:
            bridge().submit_ask(**submit(principal=OTHER_PRINCIPAL))
        assert err.value.code == "PRINCIPAL_NOT_ALLOWED"

    def test_unknown_target_refused(self):
        with pytest.raises(GblBridgeError) as err:
            bridge().submit_ask(**submit(target="random-desk"))
        assert err.value.code == "TARGET_NOT_ALLOWED"

    def test_disallowed_kind_refused(self):
        row = admission(kinds=frozenset({"question"}))
        with pytest.raises(GblBridgeError) as err:
            bridge(table=(row,)).submit_ask(**submit(kind="delegate"))
        assert err.value.code == "KIND_NOT_ALLOWED"

    def test_over_ceiling_rate_limited(self):
        row = admission(max_asks_per_hour=2)
        store = FakeStore()
        core = bridge(store, table=(row,))
        core.submit_ask(**submit(idempotency_key="gb-ask-a"))
        core.submit_ask(**submit(idempotency_key="gb-ask-b"))
        with pytest.raises(GblBridgeError) as err:
            core.submit_ask(**submit(idempotency_key="gb-ask-c"))
        assert err.value.code == "RATE_LIMITED"
        assert store.create_calls == 2

    def test_ceiling_never_exceeds_contract_maximum(self):
        from common.gbl_contract import MAX_ASKS_PER_HOUR_PER_PRINCIPAL
        with pytest.raises(ValueError):
            PrincipalAdmission(principal=PRINCIPAL, targets=frozenset({"secretary"}),
                               kinds=frozenset({"question"}),
                               max_asks_per_hour=MAX_ASKS_PER_HOUR_PER_PRINCIPAL + 1)


# ── Ask records: mint, idempotency, the Paperclip-only store ────────────────


class TestSubmitAsk:
    def test_created_uses_contract_mint(self):
        store = FakeStore()
        result = bridge(store).submit_ask(**submit())
        assert result["status"] == "CREATED"
        assert result["ask"]["ask_id"] == ASK_ID
        assert store.create_calls == 1
        assert mint_ask_id(PRINCIPAL, "secretary", "gb-ask-0001") == ASK_ID

    def test_same_key_same_content_idempotent_no_second_create(self):
        store = FakeStore()
        core = bridge(store)
        first = core.submit_ask(**submit())
        second = core.submit_ask(**submit())
        assert second["status"] == "IDEMPOTENT"
        assert second["ask"]["ask_id"] == first["ask"]["ask_id"]
        assert store.create_calls == 1

    def test_same_key_changed_content_conflict(self):
        core = bridge(FakeStore())
        core.submit_ask(**submit())
        with pytest.raises(GblBridgeError) as err:
            core.submit_ask(**submit(body="A different brief with different words."))
        assert err.value.code == "CONFLICT"


class TestCreateEffectUnknown:
    def test_timeout_with_landed_effect_reconciles_by_readback(self):
        store = FakeStore()
        store.timeout_mode = "landed"    # server created the issue; reply lost
        result = bridge(store).submit_ask(**submit())
        assert result["status"] == "IDEMPOTENT"
        assert result["ask"]["ask_id"] == ASK_ID
        assert store.create_calls == 1          # never a second create

    def test_timeout_without_effect_is_typed_unknown(self):
        store = FakeStore()
        store.timeout_mode = "absent"     # nothing reached the server
        with pytest.raises(GblBridgeError) as err:
            bridge(store).submit_ask(**submit())
        assert err.value.code == "EFFECT_UNKNOWN"
        assert store.create_calls == 1          # never a second create
        assert store.read_ask(ASK_ID) is None


# ── Question / answer / result lifecycle ────────────────────────────────────


class TestFetchQuestion:
    def test_unknown_ask_not_found(self):
        with pytest.raises(GblBridgeError) as err:
            bridge().fetch_question(principal=PRINCIPAL, ask_id="gb-" + "9" * 32)
        assert err.value.code == "ASK_NOT_FOUND"

    def test_returns_body_for_own_ask(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        result = bridge(store).fetch_question(principal=PRINCIPAL, ask_id=ASK_ID)
        assert result["question"] == "Please summarize the standing priorities."

    def test_wrong_principal_refused(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        with pytest.raises(GblBridgeError) as err:
            bridge(store).fetch_question(principal=OTHER_PRINCIPAL, ask_id=ASK_ID)
        assert err.value.code == "ASK_NOT_FOR_PRINCIPAL"


class TestPostAnswer:
    def test_answer_records_state_and_deterministic_id(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        result = bridge(store).post_answer(
            principal=PRINCIPAL, ask_id=ASK_ID,
            answer="A harmless fixture answer.", idempotency_key="gb-ans-0001")
        assert result["status"] == "ANSWERED"
        assert result["answer_id"].startswith("gbm-")
        again = bridge(store).post_answer(
            principal=PRINCIPAL, ask_id=ASK_ID,
            answer="A harmless fixture answer.", idempotency_key="gb-ans-0001")
        assert again["answer_id"] == result["answer_id"]

    def test_replay_same_key_is_idempotent(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        core = bridge(store)
        first = core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                                 answer="First words.", idempotency_key="gb-ans-0001")
        second = core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                                  answer="First words.", idempotency_key="gb-ans-0001")
        assert second["status"] == "IDEMPOTENT"
        assert second["answer_id"] == first["answer_id"]
        answered = [e for e in store.asks[ASK_ID]["events"] if e["type"] == "answer"]
        assert len(answered) == 1

    def test_same_key_changed_text_conflict(self):
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())
        core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                         answer="First words.", idempotency_key="gb-ans-0001")
        with pytest.raises(GblBridgeError) as err:
            core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                             answer="Changed words.", idempotency_key="gb-ans-0001")
        assert err.value.code == "CONFLICT"

    def test_answer_to_expired_ask_refused(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())      # expires 2026-11-12T12:00:00Z
        later = lambda: T0 + timedelta(days=2)
        with pytest.raises(GblBridgeError) as err:
            bridge(store, clock=later).post_answer(
                principal=PRINCIPAL, ask_id=ASK_ID,
                answer="Too late.", idempotency_key="gb-ans-0001")
        assert err.value.code == "EXPIRED"


class TestFetchResult:
    def test_unknown_ask_not_found(self):
        with pytest.raises(GblBridgeError) as err:
            bridge().fetch_result(principal=PRINCIPAL, ask_id="gb-" + "9" * 32)
        assert err.value.code == "ASK_NOT_FOUND"

    def test_open_ask_returns_not_yet(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        result = bridge(store).fetch_result(principal=PRINCIPAL, ask_id=ASK_ID)
        assert result["status"] == "NOT_YET"
        assert "answer" not in result

    def test_answered_ask_surfaces_unconsumed_then_consumes(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        bridge(store).post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                                  answer="A harmless fixture answer.",
                                  idempotency_key="gb-ans-0001")
        core = bridge(store)
        # Before the fetch, status surfaces ANSWER_UNCONSUMED honestly.
        assert core.ask_status(principal=PRINCIPAL, ask_id=ASK_ID)["status"] == "ANSWER_UNCONSUMED"
        result = core.fetch_result(principal=PRINCIPAL, ask_id=ASK_ID)
        assert result["status"] == "ANSWER_UNCONSUMED"
        assert result["answer"] == "A harmless fixture answer."
        assert core.ask_status(principal=PRINCIPAL, ask_id=ASK_ID)["status"] == "CONSUMED"
        again = core.fetch_result(principal=PRINCIPAL, ask_id=ASK_ID)
        assert again["status"] == "CONSUMED"
        assert again["answer"] == "A harmless fixture answer."

    def test_expired_ask_returns_expired_never_silence(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        store.seed_answer(ASK_ID)
        later = lambda: T0 + timedelta(days=2)
        with pytest.raises(GblBridgeError) as err:
            bridge(store, clock=later).fetch_result(principal=PRINCIPAL, ask_id=ASK_ID)
        assert err.value.code == "EXPIRED"


# ── Nudge ingress guard: redelivery gives no second job ─────────────────────


class TestNudgeDelivery:
    def test_unknown_ask_is_ask_not_found_noop(self):
        store = FakeStore()
        core = bridge(store)
        wake = {"schema": "mastermind.gbl.wake.v1",
                "ask_id": "gb-" + "9" * 32, "state": "ANSWERED"}
        assert core.handle_nudge_delivery(wake) == {"status": "ASK_NOT_FOUND"}
        assert store.create_calls == 0
        assert not store.created

    def test_known_ask_acknowledges_without_creating_work(self):
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())
        events_before = list(store.asks[ASK_ID]["events"])
        wake = {"schema": "mastermind.gbl.wake.v1", "ask_id": ASK_ID,
                "state": "ANSWERED"}
        assert core.handle_nudge_delivery(wake) == {"status": "OK"}
        assert store.create_calls == 1            # only the submit's create
        assert store.asks[ASK_ID]["events"] == events_before

    def test_wake_body_stays_closed_key(self):
        core = bridge(FakeStore())
        bad = {"schema": "mastermind.gbl.wake.v1", "ask_id": ASK_ID,
               "state": "ANSWERED", "text": "extra prose"}
        with pytest.raises(GBLContractError):
            core.handle_nudge_delivery(bad)


# ── Re-nudge policy: one per cooldown, bounded by the contract budget ───────


class TestRenudge:
    def _answered(self, store):
        bridge(store).submit_ask(**submit())
        bridge(store).post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                                  answer="A harmless fixture answer.",
                                  idempotency_key="gb-ans-0001")

    def test_not_answered_is_noop(self):
        store = FakeStore()
        sender = FakeNudgeSender()
        core = bridge(store, sender=sender)
        core.submit_ask(**submit())
        result = core.maybe_renudge(ask_id=ASK_ID)
        assert result["status"] == "OPEN"
        assert sender.calls == []

    def test_one_renudge_per_cooldown_then_exhausted(self):
        assert RENUDGE_COOLDOWN_SECONDS == 900
        store = FakeStore()
        sender = FakeNudgeSender()
        tick = {"now": T0}

        def clock():
            return tick["now"]

        core = bridge(store, sender=sender, clock=clock)
        self._answered(store)
        first = core.maybe_renudge(ask_id=ASK_ID)
        assert first["status"] == "RENUDGED" and len(sender.calls) == 1
        assert sender.calls[0] == (ASK_ID, "ANSWERED", "routine-handle-fixture")

        # Same cooldown window: refused.
        tick["now"] = T0 + timedelta(seconds=60)
        with pytest.raises(GblBridgeError) as err:
            core.maybe_renudge(ask_id=ASK_ID)
        assert err.value.code == "RENUDGE_COOLDOWN"

        # After the cooldown: second, third, then the budget is spent.
        tick["now"] = T0 + timedelta(seconds=RENUDGE_COOLDOWN_SECONDS + 1)
        assert core.maybe_renudge(ask_id=ASK_ID)["status"] == "RENUDGED"
        tick["now"] = T0 + timedelta(seconds=2 * RENUDGE_COOLDOWN_SECONDS + 2)
        assert core.maybe_renudge(ask_id=ASK_ID)["status"] == "RENUDGED"
        tick["now"] = T0 + timedelta(seconds=3 * RENUDGE_COOLDOWN_SECONDS + 3)
        with pytest.raises(GblBridgeError) as err:
            core.maybe_renudge(ask_id=ASK_ID)
        assert err.value.code == "RENUDGE_BUDGET_EXHAUSTED"
        assert len(sender.calls) == 3

    def test_unknown_ask_not_found(self):
        with pytest.raises(GblBridgeError) as err:
            bridge(sender=FakeNudgeSender()).maybe_renudge(ask_id="gb-" + "9" * 32)
        assert err.value.code == "ASK_NOT_FOUND"


# ── The loopback socket door: kernel peer uid only ──────────────────────────


class FakeCore:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, op):
        def method(**arguments):
            self.calls.append((op, (), dict(arguments)))
            return {"status": "FIXTURE"}
        return method

    def __getattr__(self, name):
        if name in {"submit_ask", "fetch_question", "post_answer",
                    "fetch_result", "ask_status"}:
            return self._record(name)
        raise AttributeError(name)


def _exchange(server: BridgeServer, request: dict) -> dict:
    from common.gbl_contract import decode_gbl_frame, encode_gbl_frame
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(10.0)
    client.connect(str(server.config.socket_path))
    client.sendall(encode_gbl_frame(request))
    buffer = b""
    while not buffer.endswith(b"\n"):
        chunk = client.recv(4096)
        if not chunk:
            break
        buffer += chunk
    client.close()
    return decode_gbl_frame(buffer)


def _server(tmp_path, core, allowed_uids) -> BridgeServer:
    config = BridgeServiceConfig(
        socket_path=tmp_path / "gbl-bridge.sock",
        allowed_peer_uids=allowed_uids,
    )
    server = BridgeServer(config, core)
    server.open()
    return server


REQUEST = {"schema": "mastermind.gbl.request.v1", "op": "status",
           "arguments": {"principal": PRINCIPAL, "ask_id": ASK_ID}}


class TestSocketService:
    def test_admits_kernel_peer_uid(self, tmp_path):
        core = FakeCore()
        server = _server(tmp_path, core, (os.getuid(),))
        try:
            response = _exchange(server, REQUEST)
            assert response["ok"] is True
            assert response["result"] == {"status": "FIXTURE"}
            assert core.calls == [("ask_status", (), {"principal": PRINCIPAL,
                                                      "ask_id": ASK_ID})]
        finally:
            server.close()

    def test_refuses_uid_not_in_table_without_calling_core(self, tmp_path):
        core = FakeCore()
        server = _server(tmp_path, core, (os.getuid() + 1,))
        try:
            response = _exchange(server, REQUEST)
            assert response["ok"] is False
            assert response["error"]["code"] == "PEER_NOT_ALLOWED"
            assert core.calls == []
        finally:
            server.close()

    def test_uid_table_must_be_nonempty_sorted_unique(self, tmp_path):
        with pytest.raises(ValueError):
            BridgeServiceConfig(socket_path=tmp_path / "x.sock", allowed_peer_uids=())
        with pytest.raises(ValueError):
            BridgeServiceConfig(socket_path=tmp_path / "x.sock",
                                allowed_peer_uids=(2, 1))
        with pytest.raises(ValueError):
            BridgeServiceConfig(socket_path=tmp_path / "x.sock", allowed_peer_uids=(1, 1))

    def test_unknown_op_refused(self, tmp_path):
        server = _server(tmp_path, FakeCore(), (os.getuid(),))
        try:
            response = _exchange(server, {**REQUEST, "op": "install"})
            assert response["ok"] is False
            assert response["error"]["code"] == "UNKNOWN_OP"
        finally:
            server.close()

    def test_malformed_frame_refused(self, tmp_path):
        server = _server(tmp_path, FakeCore(), (os.getuid(),))
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(10.0)
            client.connect(str(server.config.socket_path))
            client.sendall(b"not-json\n")
            buffer = b""
            while not buffer.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                buffer += chunk
            client.close()
            from common.gbl_contract import decode_gbl_frame
            response = decode_gbl_frame(buffer)
            assert response["ok"] is False
            assert response["error"]["code"] == "REQUEST_INVALID"
        finally:
            server.close()

    def test_bridge_error_maps_to_typed_error_frame(self, tmp_path):
        class RefusingCore:
            def ask_status(self, **_):
                raise GblBridgeError("ASK_NOT_FOUND", "no such ask")
        server = _server(tmp_path, RefusingCore(), (os.getuid(),))
        try:
            response = _exchange(server, REQUEST)
            assert response["ok"] is False
            assert response["error"]["code"] == "ASK_NOT_FOUND"
        finally:
            server.close()

    def test_real_bridge_over_socket_end_to_end(self, tmp_path):
        store = FakeStore()
        core = bridge(store)
        server = _server(tmp_path, core, (os.getuid(),))
        try:
            response = _exchange(server, {
                "schema": "mastermind.gbl.request.v1", "op": "ask",
                "arguments": submit(),
            })
            assert response["ok"] is True
            assert response["result"]["status"] == "CREATED"
            assert response["result"]["ask"]["ask_id"] == ASK_ID
        finally:
            server.close()
