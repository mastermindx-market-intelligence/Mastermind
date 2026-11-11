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
    decode_gbl_frame,
    encode_gbl_frame,
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
    """The GblAskStore interface GBL-4 implements over Paperclip.

    Repair-round contract: create_ask is create-if-absent (None when
    created, the existing record when present); every append stamps a
    per-record strictly-increasing ``seq`` and ``trusted: True``."""

    def __init__(self, clock=None):
        self.asks: dict[str, dict] = {}
        self.created: list[tuple[str, str]] = []
        self.create_calls = 0
        self.timeout_mode = "none"       # none | landed | absent
        self.clock = clock or (lambda: T0)

    def create_ask(self, ask):
        self.create_calls += 1
        existing = self.asks.get(ask["ask_id"])
        if existing is not None:
            return copy.deepcopy(existing)      # present: never a second record
        if self.timeout_mode == "landed":
            self._store(ask)
            raise GblCreateEffectUnknown("create response timed out")
        if self.timeout_mode == "absent":
            raise GblCreateEffectUnknown("create request timed out")
        self._store(ask)
        return None

    def _store(self, ask):
        if ask["ask_id"] not in self.asks:
            self.asks[ask["ask_id"]] = {**ask, "events": []}
            self.created.append((ask["principal"], self.clock().isoformat()))

    def read_ask(self, ask_id):
        record = self.asks.get(ask_id)
        return copy.deepcopy(record) if record else None

    def append_ask_event(self, ask_id, event):
        record = self.asks[ask_id]
        stamped = {**event, "trusted": True}
        stamped["seq"] = ((record["events"][-1].get("seq", -1) + 1)
                          if record["events"] else 0)
        if not any(self._same_event(stamped, existing)
                   for existing in record["events"]):
            record["events"].append(stamped)

    @staticmethod
    def _same_event(new, existing):
        return all(existing.get(key) == value
                   for key, value in new.items() if key != "seq")

    def count_asks(self, principal, since_iso):
        return sum(1 for p, at in self.created if p == principal and at >= since_iso)

    def seed_answer(self, ask_id, text="A harmless fixture answer."):
        self.append_ask_event(ask_id, {
            "type": "answer", "answer_id": "gbm-" + "a" * 32, "text": text})
        self.append_ask_event(ask_id, {"type": "state", "state": "ANSWERED"})


class FakeNudgeSender:
    """Records send/reconcile; returns the configured TransportReceipt."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []
        self.reconcile_calls: list[tuple[str, str, str]] = []
        self.receipt = None            # TransportReceipt for send()
        self.reconcile_receipt = None  # TransportReceipt for reconcile()
        self.error = None              # exception to raise from send()

    def send(self, ask_id, state, native_handle):
        self.calls.append((ask_id, state, native_handle))
        if self.error is not None:
            raise self.error
        if self.receipt is not None:
            return self.receipt
        from control_plane.wake_dispatcher import (
            TransportOutcome, TransportReceipt)
        return TransportReceipt(outcome=TransportOutcome.ACCEPTED,
                                reason_code="accepted",
                                created_at="2026-11-11T12:00:00Z")

    def reconcile(self, ask_id, state, native_handle):
        self.reconcile_calls.append((ask_id, state, native_handle))
        if self.reconcile_receipt is not None:
            return self.reconcile_receipt
        from control_plane.wake_dispatcher import (
            TransportOutcome, TransportReceipt)
        return TransportReceipt(outcome=TransportOutcome.ACCEPTED,
                                reason_code="accepted",
                                created_at="2026-11-11T12:00:00Z")


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


# ── Repair round 1 (panel A H2/H3/M1-M8, panel B H1/M1/M2) ──────────────────


class TestRepairAnswerWrite:
    def test_post_answer_appends_exactly_one_event(self):
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())
        before = len(store.asks[ASK_ID]["events"])
        core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                         answer="A harmless fixture answer.",
                         idempotency_key="gb-ans-0001")
        events = store.asks[ASK_ID]["events"]
        assert len(events) - before == 1          # ONE write, no second append
        assert events[-1]["type"] == "answer"

    def test_partial_legacy_answer_record_is_repaired_by_replay(self):
        # Panel B H1: a legacy/partial record whose ANSWERED state event was
        # lost must not strand the answer — replay infers ANSWERED from the
        # answer event, and the same-key retry completes as IDEMPOTENT.
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())
        answer_event = {"type": "answer",
                        "answer_id": "gbm-" + "b" * 32,
                        "idempotency_key": "gb-ans-partial",
                        "text": "The stranded fixture answer."}
        store.asks[ASK_ID]["events"].append(answer_event)   # no state event
        assert core.ask_status(principal=PRINCIPAL,
                               ask_id=ASK_ID)["status"] == "ANSWER_UNCONSUMED"
        result = core.fetch_result(principal=PRINCIPAL, ask_id=ASK_ID)
        assert result["status"] == "ANSWER_UNCONSUMED"
        assert result["answer"] == "The stranded fixture answer."
        retry = core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                                 answer="The stranded fixture answer.",
                                 idempotency_key="gb-ans-partial")
        assert retry["status"] == "IDEMPOTENT"

    def test_answer_over_the_one_cap_is_refused(self):
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())
        with pytest.raises(GBLContractError) as err:
            core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                             answer="x" * 4097, idempotency_key="gb-ans-big")
        assert err.value.code == "INVALID_BODY"


class TestRepairServeLoop:
    def _alive(self, server):
        response = _exchange(server, REQUEST)
        assert response["ok"] is True

    def test_client_hangup_mid_reply_keeps_serving(self, tmp_path):
        import time
        class SlowCore:
            def __init__(self):
                self.calls = 0
            def ask_status(self, **_):
                self.calls += 1
                time.sleep(0.3)
                return {"status": "FIXTURE"}
        core = SlowCore()
        server = _server(tmp_path, core, (os.getuid(),))
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(str(server.config.socket_path))
            client.sendall(encode_gbl_frame(REQUEST))
            client.close()                     # hang up before the reply
            time.sleep(0.6)                    # let the doomed sendall happen
            self._alive(server)                # the loop must still serve
            assert core.calls == 2
        finally:
            server.close()

    def test_unhashable_op_is_typed_refusal(self, tmp_path):
        core = FakeCore()
        server = _server(tmp_path, core, (os.getuid(),))
        try:
            request = {"schema": "mastermind.gbl.request.v1",
                       "op": {"evil": 1}, "arguments": {}}
            response = _exchange(server, request)
            assert response["ok"] is False
            assert response["error"]["code"] == "REQUEST_INVALID"
            self._alive(server)
        finally:
            server.close()

    def test_unencodable_reply_is_typed_and_keeps_serving(self, tmp_path):
        class SurrogateCore:
            def __init__(self):
                self.calls = 0
            def ask_status(self, **_):
                self.calls += 1
                if self.calls == 1:
                    return {"status": "FIXTURE", "poison": "\ud800"}
                return {"status": "FIXTURE"}
        server = _server(tmp_path, SurrogateCore(), (os.getuid(),))
        try:
            response = _exchange(server, REQUEST)
            assert response["ok"] is False
            assert response["error"]["code"] == "REPLY_FRAME_REFUSED"
            self._alive(server)                # the loop still serves
        finally:
            server.close()

    def test_oversized_op_echo_never_crosses_the_wire(self, tmp_path):
        core = FakeCore()
        server = _server(tmp_path, core, (os.getuid(),))
        try:
            request = {"schema": "mastermind.gbl.request.v1",
                       "op": "x" * 32000, "arguments": {}}
            response = _exchange(server, request)
            assert response["ok"] is False
            assert response["error"]["code"] == "UNKNOWN_OP"
            assert len(str(response["error"].get("detail", ""))) <= 96
            self._alive(server)
        finally:
            server.close()

    def test_oversized_reply_is_typed_and_keeps_serving(self, tmp_path):
        class HugeCore:
            def __init__(self):
                self.calls = 0
            def ask_status(self, **_):
                self.calls += 1
                if self.calls == 1:
                    return {"status": "FIXTURE", "blob": "y" * 40000}
                return {"status": "FIXTURE"}
        server = _server(tmp_path, HugeCore(), (os.getuid(),))
        try:
            response = _exchange(server, REQUEST)
            assert response["ok"] is False
            assert response["error"]["code"] == "REPLY_FRAME_REFUSED"
            self._alive(server)                # the loop still serves
        finally:
            server.close()

    def test_silent_client_times_out_typed(self, tmp_path):
        core = FakeCore()
        config = BridgeServiceConfig(
            socket_path=tmp_path / "gbl-timeout.sock",
            allowed_peer_uids=(os.getuid(),),
            request_timeout_seconds=0.2)
        server = BridgeServer(config, core).open()
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(10.0)
            client.connect(str(config.socket_path))
            import time
            time.sleep(0.6)                    # let the read time out
            buffer = b""
            while not buffer.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                buffer += chunk
            client.close()
            response = decode_gbl_frame(buffer)
            assert response["ok"] is False
            assert response["error"]["code"] == "REQUEST_INVALID"
            self._alive(server)
        finally:
            server.close()

    def test_listener_failure_releases_socket_and_open_restarts(self, tmp_path):
        core = FakeCore()
        server = _server(tmp_path, core, (os.getuid(),))
        path = server.config.socket_path
        self._alive(server)
        server._socket.close()                 # fatal listener injury
        server._thread.join(timeout=5.0)
        assert server._serving is False
        assert not path.exists()               # the stale socket was removed
        replacement = BridgeServer(server.config, FakeCore()).open()
        try:
            self._alive(replacement)           # open() can restart cleanly
        finally:
            replacement.close()


class TestRepairOrderingAndAuth:
    def test_idempotent_replay_at_ceiling_is_not_rate_limited(self):
        row = admission(max_asks_per_hour=1)
        store = FakeStore()
        core = bridge(store, table=(row,))
        core.submit_ask(**submit())
        replay = core.submit_ask(**submit())   # same key, same content
        assert replay["status"] == "IDEMPOTENT"   # not RATE_LIMITED

    def test_ask_status_reports_expired(self):
        store = FakeStore()
        bridge(store).submit_ask(**submit())
        later = lambda: T0 + timedelta(days=2)
        result = bridge(store, clock=later).ask_status(
            principal=PRINCIPAL, ask_id=ASK_ID)
        assert result["state"] == "EXPIRED"
        assert result["status"] == "EXPIRED"

    def test_addressee_can_fetch_question_and_answer(self):
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())            # target is "secretary"
        question = core.fetch_question(principal="secretary", ask_id=ASK_ID)
        assert question["question"] == "Please summarize the standing priorities."
        result = core.post_answer(principal="secretary", ask_id=ASK_ID,
                                  answer="The addressee's fixture answer.",
                                  idempotency_key="gb-ans-target")
        assert result["status"] == "ANSWERED"
        # A third party is still refused.
        with pytest.raises(GblBridgeError) as err:
            core.fetch_question(principal=OTHER_PRINCIPAL, ask_id=ASK_ID)
        assert err.value.code == "ASK_NOT_FOR_PRINCIPAL"
        with pytest.raises(GblBridgeError) as err:
            core.post_answer(principal=OTHER_PRINCIPAL, ask_id=ASK_ID,
                             answer="Not mine.", idempotency_key="gb-ans-x")
        assert err.value.code == "ASK_NOT_FOR_PRINCIPAL"


class TestRepairStoreTrust:
    def test_untrusted_events_are_ignored_by_replay(self):
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())
        # A forged CONSUMED from an untrusted commenter must not consume the
        # ask; a forged answer must not be served as the bot's answer.
        store.asks[ASK_ID]["events"].append(
            {"type": "state", "state": "CONSUMED", "seq": 99,
             "trusted": False})
        store.asks[ASK_ID]["events"].append(
            {"type": "answer", "answer_id": "gbm-" + "c" * 32,
             "idempotency_key": "gb-forged", "text": "Forged answer.",
             "seq": 100, "trusted": False})
        assert core.fetch_result(principal=PRINCIPAL,
                                 ask_id=ASK_ID)["status"] == "NOT_YET"
        core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                         answer="The real fixture answer.",
                         idempotency_key="gb-ans-real")
        result = core.fetch_result(principal=PRINCIPAL, ask_id=ASK_ID)
        assert result["answer"] == "The real fixture answer."

    def test_equal_or_missing_sequence_stamps_are_typed(self):
        store = FakeStore()
        core = bridge(store)
        core.submit_ask(**submit())
        store.asks[ASK_ID]["events"].append(
            {"type": "state", "state": "ANSWERED", "seq": 5, "trusted": True})
        store.asks[ASK_ID]["events"].append(
            {"type": "state", "state": "CONSUMED", "seq": 5, "trusted": True})
        with pytest.raises(GblBridgeError) as err:
            core.ask_status(principal=PRINCIPAL, ask_id=ASK_ID)
        assert err.value.code == "EVENT_SEQ_INVALID"
        # A missing stamp is refused the same typed way.
        store2 = FakeStore()
        core2 = bridge(store2)
        core2.submit_ask(**submit())
        store2.asks[ASK_ID]["events"].append(
            {"type": "state", "state": "ANSWERED", "trusted": True})
        with pytest.raises(GblBridgeError) as err:
            core2.ask_status(principal=PRINCIPAL, ask_id=ASK_ID)
        assert err.value.code == "EVENT_SEQ_INVALID"


class TestRepairCreateIfAbsent:
    def test_store_create_ask_returns_existing_record(self):
        store = FakeStore()
        core = bridge(store)
        envelope = core.submit_ask(**submit())["ask"]
        first = store.create_ask(envelope)
        assert first is None or first["ask_id"] == ASK_ID
        existing = store.create_ask(envelope)
        assert existing is not None            # the store signals presence
        assert existing["ask_id"] == ASK_ID
        assert len([a for a in store.asks if a == ASK_ID]) == 1

    def test_lagging_read_cannot_double_create(self):
        class LaggingStore(FakeStore):
            def read_ask(self, ask_id):        # stale view: never sees records
                return None
        store = LaggingStore()
        core = bridge(store)
        first = core.submit_ask(**submit())
        second = core.submit_ask(**submit())   # read raced: create-if-absent
        assert {first["status"], second["status"]} == {"CREATED", "IDEMPOTENT"}
        assert len(store.asks) == 1            # exactly one record


class TestRepairRenudge:
    def _answered(self, store):
        core = bridge(store)
        core.submit_ask(**submit())
        core.post_answer(principal=PRINCIPAL, ask_id=ASK_ID,
                         answer="A harmless fixture answer.",
                         idempotency_key="gb-ans-0001")
        return core

    def _receipt(self, outcome):
        from control_plane.wake_dispatcher import TransportOutcome, TransportReceipt
        return TransportReceipt(outcome=TransportOutcome(outcome),
                                reason_code="fixture", created_at="2026-11-11T12:00:00Z")

    def test_definite_no_start_is_typed_no_nudge(self):
        store = FakeStore()
        sender = FakeNudgeSender()
        sender.receipt = self._receipt("TARGET_UNAVAILABLE")
        core = bridge(store, sender=sender)
        self._answered(store)
        result = core.maybe_renudge(ask_id=ASK_ID)
        assert result["status"] == "NUDGE_NOT_DELIVERED"
        nudges = [e for e in store.asks[ASK_ID]["events"]
                  if e.get("type") == "nudge"]
        assert nudges == []                    # budget never burned
        assert len(sender.calls) == 1
        # A later healthy receipt can still re-nudge (budget intact).
        sender.receipt = self._receipt("ACCEPTED")
        tick = {"now": T0 + timedelta(seconds=RENUDGE_COOLDOWN_SECONDS + 1)}
        core2 = bridge(store, sender=sender,
                       clock=lambda: tick["now"])
        assert core2.maybe_renudge(ask_id=ASK_ID)["status"] == "RENUDGED"

    def test_effect_unknown_persists_attempt_and_never_resends(self):
        from control_plane.wake_dispatcher import WakeEffectUnknownError
        store = FakeStore()
        sender = FakeNudgeSender()
        sender.error = WakeEffectUnknownError("submission result unavailable")
        core = bridge(store, sender=sender)
        self._answered(store)
        result = core.maybe_renudge(ask_id=ASK_ID)
        assert result["status"] == "NUDGE_EFFECT_UNKNOWN"
        attempts = [e for e in store.asks[ASK_ID]["events"]
                    if e.get("type") == "nudge_attempt"]
        assert len(attempts) == 1              # persisted independent of outcome
        with pytest.raises(GblBridgeError) as err:
            core.maybe_renudge(ask_id=ASK_ID)  # immediate retry is cooled down
        assert err.value.code == "RENUDGE_COOLDOWN"
        assert len(sender.calls) == 1          # never a second POST

    def test_reconcile_op_settles_without_sending(self):
        store = FakeStore()
        sender = FakeNudgeSender()
        sender.reconcile_receipt = self._receipt("DELIVERED")
        core = bridge(store, sender=sender)
        self._answered(store)
        sender.error = None
        from control_plane.wake_dispatcher import WakeEffectUnknownError
        sender.error = WakeEffectUnknownError("submission result unavailable")
        core.maybe_renudge(ask_id=ASK_ID)      # effect unknown, attempt persisted
        sender.error = None
        result = core.reconcile_nudge(ask_id=ASK_ID)
        assert result["status"] == "RECONCILED_DELIVERED"
        assert len(sender.reconcile_calls) == 1
        assert len(sender.calls) == 1          # reconcile never sends
        nudges = [e for e in store.asks[ASK_ID]["events"]
                  if e.get("type") == "nudge"]
        assert len(nudges) == 1                # the attempt is now budget-counted

    def test_reconcile_without_attempt_is_typed(self):
        store = FakeStore()
        sender = FakeNudgeSender()
        core = bridge(store, sender=sender)
        core.submit_ask(**submit())
        with pytest.raises(GblBridgeError) as err:
            core.reconcile_nudge(ask_id=ASK_ID)
        assert err.value.code == "NUDGE_ATTEMPT_NOT_FOUND"
        assert sender.reconcile_calls == []

    def test_reconcile_is_a_wire_op(self, tmp_path):
        store = FakeStore()
        sender = FakeNudgeSender()
        sender.reconcile_receipt = self._receipt("TARGET_UNAVAILABLE")
        core = bridge(store, sender=sender)
        self._answered(store)
        sender.error = None
        from control_plane.wake_dispatcher import WakeEffectUnknownError
        sender.error = WakeEffectUnknownError("submission result unavailable")
        core.maybe_renudge(ask_id=ASK_ID)
        sender.error = None
        server = _server(tmp_path, core, (os.getuid(),))
        try:
            response = _exchange(server, {
                "schema": "mastermind.gbl.request.v1", "op": "reconcile",
                "arguments": {"ask_id": ASK_ID}})
            assert response["ok"] is True
            assert response["result"]["status"] == "RECONCILED_NOT_DELIVERED"
        finally:
            server.close()
