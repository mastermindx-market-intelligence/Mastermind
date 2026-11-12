"""GBL-4 ask CLI tests (lane GBL, BUILD_PLAN "Tests first" row GBL-4).

BUILD_PLAN: the CLI ``--wait`` returns the answer or "not yet"; the asker
identity is recorded; token hygiene (no secret in argv/prompts/logs);
``EXPIRED`` on a stale fetch.  The CLI talks ONLY to the bridge's AF_UNIX
socket (peer-uid admission) — never TCP, never Paperclip, and it holds no
token, secret or credential at all.  The bridge side is GBL-2's real
``GblBridge``/``BridgeServer`` on a temp socket, imported unmodified.  All
strings are harmless fixture words.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from common.gbl_contract import build_ask
from integrations.gbl.bridge_service import (
    BridgeServer,
    BridgeServiceConfig,
    GblBridge,
    PrincipalAdmission,
)
from tools.gbl import gbl_ask

BOT = "grok-account-fixture"
QUESTION = "A harmless fixture question about standing priorities."
ANSWER = "A harmless fixture answer."
ASK_ID_LEN = 35


class MemoryStore:
    """The GblAskStore interface, in-memory (the reference fake's shape)."""

    GBL_TEST_DOUBLE = True       # no host delivery lock: see GBL-5 micro 4

    def __init__(self):
        self.asks = {}
        self.created = []
        self.create_calls = 0

    def create_ask(self, ask):
        self.create_calls += 1
        if ask["ask_id"] not in self.asks:
            self.asks[ask["ask_id"]] = {**ask, "events": []}
            self.created.append(
                (ask["principal"], datetime.now(timezone.utc).isoformat()))

    def read_ask(self, ask_id):
        record = self.asks.get(ask_id)
        return dict(record) if record else None

    def append_ask_event(self, ask_id, event):
        record = self.asks[ask_id]
        if event not in record["events"]:
            record["events"].append(dict(event))

    def count_asks(self, principal, since_iso):
        return sum(1 for p, at in self.created
                   if p == principal and at >= since_iso)


@pytest.fixture()
def service(tmp_path):
    store = MemoryStore()
    core = GblBridge(
        store,
        admission_table=(PrincipalAdmission(
            principal=BOT,
            targets=frozenset({BOT}),
            kinds=frozenset({"question"}),
            max_asks_per_hour=20,
        ),),
        now=lambda: datetime.now(timezone.utc),
    )
    config = BridgeServiceConfig(
        socket_path=tmp_path / "bridge.sock",
        allowed_peer_uids=(os.getuid(),),
    )
    server = BridgeServer(config, core).open()
    try:
        yield SimpleNamespace(store=store, core=core, server=server,
                              socket=str(config.socket_path))
    finally:
        server.close()


def run_cli(capsys, service, *args) -> tuple[int, str]:
    command, *rest = args
    rc = gbl_ask.main([command, "--socket", service.socket,
                       "--bot", BOT, *rest])
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


def ask_id_from(output: str) -> str:
    for line in output.splitlines():
        for field in line.split():
            if field.startswith("ask_id="):
                return field[len("ask_id="):]
    raise AssertionError(f"no ask_id in output: {output!r}")


# ── The CLI talks only to the bridge's Unix socket ──────────────────────────


class TestUnixSocketOnly:
    def test_ask_and_fetch_work_with_tcp_sockets_forbidden(
            self, service, capsys, monkeypatch):
        real_socket = socket.socket

        def guarded(family=socket.AF_UNSPEC, *args, **kwargs):
            if family in (socket.AF_INET, socket.AF_INET6):
                raise AssertionError("the CLI opened a TCP socket")
            return real_socket(family, *args, **kwargs)

        monkeypatch.setattr(socket, "socket", guarded)
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION)
        assert rc == 0
        ask_id = ask_id_from(out)
        rc, out = run_cli(capsys, service, "fetch", "--id", ask_id)
        assert rc == 3          # NOT_YET — the socket door answered


# ── ask: record, identity, idempotency ──────────────────────────────────────


class TestAsk:
    def test_ask_creates_a_question_record_for_the_bot(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION)
        assert rc == 0
        ask_id = ask_id_from(out)
        assert ask_id.startswith("gb-") and len(ask_id) == ASK_ID_LEN
        assert "status=CREATED" in out
        record = service.store.read_ask(ask_id)
        assert record["kind"] == "question"
        assert record["principal"] == BOT
        assert record["target"] == BOT
        assert record["body"] == QUESTION

    def test_asker_identity_is_recorded_verbatim(self, service, capsys):
        rc, out = run_cli(
            capsys, service, "ask", "--question", QUESTION,
            "--asker-environment-id", "env-fixture",
            "--asker-thread-id", "thread-fixture",
            "--asker-session-label", "session-fixture")
        assert rc == 0
        record = service.store.read_ask(ask_id_from(out))
        assert record["asker"] == {
            "side": "t3_thread",
            "environment_id": "env-fixture",
            "thread_id": "thread-fixture",
            "session_label": "session-fixture",
        }

    def test_partial_asker_identity_is_refused(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION,
                          "--asker-environment-id", "env-fixture")
        assert rc == 2
        assert service.store.create_calls == 0

    def test_asker_identity_from_environment(self, service, capsys,
                                             monkeypatch):
        monkeypatch.setenv("GBL_ASKER_ENVIRONMENT_ID", "env-fixture")
        monkeypatch.setenv("GBL_ASKER_THREAD_ID", "thread-fixture")
        monkeypatch.setenv("GBL_ASKER_SESSION_LABEL", "session-fixture")
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION)
        assert rc == 0
        record = service.store.read_ask(ask_id_from(out))
        assert record["asker"]["thread_id"] == "thread-fixture"

    def test_same_idempotency_key_replays_idempotent_one_record(
            self, service, capsys):
        args = ("ask", "--question", QUESTION, "--idempotency-key", "k-1")
        assert run_cli(capsys, service, *args)[0] == 0
        rc, out = run_cli(capsys, service, *args)
        assert rc == 0
        assert "status=IDEMPOTENT" in out
        assert service.store.create_calls == 1
        assert len(service.store.asks) == 1

    def test_socket_required(self, monkeypatch, capsys):
        monkeypatch.delenv("GBL_BRIDGE_SOCKET", raising=False)
        rc = gbl_ask.main(["ask", "--bot", BOT, "--question", QUESTION])
        captured = capsys.readouterr()
        assert rc == 2
        assert service_like_refusal(captured.out + captured.err)

    def test_socket_from_environment(self, service, capsys, monkeypatch):
        monkeypatch.setenv("GBL_BRIDGE_SOCKET", service.socket)
        rc = gbl_ask.main(["ask", "--bot", BOT, "--question", QUESTION])
        capsys.readouterr()
        assert rc == 0

    def test_unreachable_socket_is_a_clean_error(self, tmp_path, capsys):
        rc = gbl_ask.main([
            "status", "--socket", str(tmp_path / "absent.sock"),
            "--bot", BOT, "--id", "gb-" + "0" * 32])
        out = capsys.readouterr()
        assert rc == 2
        assert "BRIDGE_UNREACHABLE" in out.out + out.err


def service_like_refusal(text: str) -> bool:
    return "--socket" in text or "socket" in text.lower()


# ── --wait: the answer, or "not yet" ────────────────────────────────────────


class TestWait:
    def test_wait_returns_the_answer(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION,
                          "--idempotency-key", "k-w")
        ask_id = ask_id_from(out)

        def answer_later():
            time.sleep(0.4)
            service.core.post_answer(
                principal=BOT, ask_id=ask_id, answer=ANSWER,
                idempotency_key="ans-1")

        worker = threading.Thread(target=answer_later)
        worker.start()
        try:
            rc, out = run_cli(
                capsys, service, "ask", "--question", QUESTION,
                "--idempotency-key", "k-w", "--wait",
                "--poll-seconds", "0.1", "--deadline-seconds", "10")
        finally:
            worker.join()
        assert rc == 0
        assert ANSWER in out

    def test_wait_returns_not_yet_without_an_answer(self, service, capsys):
        rc, out = run_cli(
            capsys, service, "ask", "--question", QUESTION,
            "--idempotency-key", "k-ny", "--wait",
            "--poll-seconds", "0.1", "--deadline-seconds", "0.5")
        assert rc == 3
        assert "NOT_YET" in out

    def test_wait_flag_on_fetch_is_accepted(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION,
                          "--idempotency-key", "k-f")
        ask_id = ask_id_from(out)
        rc, out = run_cli(capsys, service, "fetch", "--id", ask_id, "--wait",
                          "--poll-seconds", "0.1", "--deadline-seconds", "0.4")
        assert rc == 3


# ── fetch / status / expiry ─────────────────────────────────────────────────


class TestFetchStatusExpiry:
    def test_fetch_returns_the_answer_once(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION,
                          "--idempotency-key", "k-x")
        ask_id = ask_id_from(out)
        service.core.post_answer(principal=BOT, ask_id=ask_id,
                                 answer=ANSWER, idempotency_key="ans-x")

        rc, out = run_cli(capsys, service, "fetch", "--id", ask_id)
        assert rc == 0
        assert ANSWER in out
        consumed = lambda record: [                       # noqa: E731
            e for e in record["events"]
            if e.get("type") == "state" and e.get("state") == "CONSUMED"]
        assert len(consumed(service.store.read_ask(ask_id))) == 1

        rc, out = run_cli(capsys, service, "fetch", "--id", ask_id)
        assert rc == 0                 # repeatable read of the same answer
        assert len(consumed(service.store.read_ask(ask_id))) == 1

    def test_fetch_not_yet(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION,
                          "--idempotency-key", "k-n")
        ask_id = ask_id_from(out)
        rc, out = run_cli(capsys, service, "fetch", "--id", ask_id)
        assert rc == 3
        assert "NOT_YET" in out

    def test_expired_on_stale_fetch(self, service, capsys):
        envelope = build_ask(kind="question", principal=BOT, target=BOT,
                             idempotency_key="k-exp",
                             title="Expiry fixture",
                             body="An ask that expires immediately.",
                             ttl_seconds=1, now=datetime.now(timezone.utc))
        service.store.create_ask(envelope)
        time.sleep(1.2)
        rc, out = run_cli(capsys, service, "fetch", "--id",
                          envelope["ask_id"])
        assert rc == 4
        assert "EXPIRED" in out

    def test_status_reports_state(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION,
                          "--idempotency-key", "k-s")
        ask_id = ask_id_from(out)
        rc, out = run_cli(capsys, service, "status", "--id", ask_id)
        assert rc == 0
        assert "state=OPEN" in out

    def test_unknown_ask_is_a_typed_error(self, service, capsys):
        rc, out = run_cli(capsys, service, "status", "--id",
                          "gb-" + "0" * 32)
        assert rc == 5
        assert "ASK_NOT_FOUND" in out


# ── Token hygiene: no secret in argv, prompts or logs ───────────────────────


BANNED = ("token", "secret", "password", "bearer", "authorization",
          "credential", "api_key", "api-key")


# ── Repair 1: the wait survives transient bridge hiccups; honest exits ──────


class ScriptedBridge:
    """A BridgeSocketClient stand-in with a canned request script, for the
    wait-loop resilience tests (panel B N1/N3/L10/L11)."""

    def __init__(self, socket_path,
                 timeout=gbl_ask.REQUEST_TIMEOUT_SECONDS, script=()):
        self.script: list[tuple] = list(script)
        self.calls: list[tuple[str, dict]] = []

    def request(self, op: str, arguments: dict) -> dict:
        self.calls.append((op, dict(arguments)))
        if not self.script:
            raise gbl_ask.AskCliError("BRIDGE_UNREACHABLE", "scripted")
        step = self.script.pop(0)
        if step[0] == "raise":
            raise gbl_ask.AskCliError(step[1], "scripted")
        return dict(step[1])


def run_scripted(capsys, monkeypatch, script, *args) -> tuple[int, str]:
    import functools
    monkeypatch.setattr(gbl_ask, "BridgeSocketClient",
                        functools.partial(ScriptedBridge, script=script))
    command, *rest = args
    rc = gbl_ask.main([command, "--socket", "/tmp/gbl-fixture.sock",
                       "--bot", BOT, *rest])
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


NOT_YET = {"status": "NOT_YET", "ask_id": "gb-" + "1" * 32}
ANSWERED = {"status": "ANSWER_UNCONSUMED", "ask_id": "gb-" + "1" * 32,
            "answer_id": "gbm-" + "2" * 32, "answer": ANSWER}


class TestWaitResilience:
    def test_wait_retries_past_a_transient_unreachable(self, capsys,
                                                       monkeypatch):
        rc, out = run_scripted(
            capsys, monkeypatch,
            [("result", NOT_YET), ("raise", "BRIDGE_UNREACHABLE"),
             ("result", ANSWERED)],
            "fetch", "--id", "gb-" + "1" * 32, "--wait",
            "--poll-seconds", "0.05", "--deadline-seconds", "10")
        assert rc == 0                        # not 5: a hiccup is not a verdict
        assert ANSWER in out

    def test_wait_unreachable_at_the_deadline_exits_2(self, capsys,
                                                      monkeypatch):
        rc, out = run_scripted(
            capsys, monkeypatch, [("raise", "BRIDGE_UNREACHABLE")],
            "fetch", "--id", "gb-" + "1" * 32, "--wait",
            "--poll-seconds", "0.05", "--deadline-seconds", "0.3")
        assert rc == 2                        # unreachable, not a typed ask error
        assert "BRIDGE_UNREACHABLE" in out

    def test_wait_invalid_response_is_transient_then_retried(self, capsys,
                                                             monkeypatch):
        rc, out = run_scripted(
            capsys, monkeypatch,
            [("raise", "BRIDGE_RESPONSE_INVALID"), ("result", ANSWERED)],
            "fetch", "--id", "gb-" + "1" * 32, "--wait",
            "--poll-seconds", "0.05", "--deadline-seconds", "10")
        assert rc == 0

    def test_wait_still_exits_5_on_a_typed_ask_error(self, capsys,
                                                     monkeypatch):
        rc, out = run_scripted(
            capsys, monkeypatch, [("raise", "ASK_NOT_FOUND")],
            "fetch", "--id", "gb-" + "1" * 32, "--wait",
            "--poll-seconds", "0.05", "--deadline-seconds", "10")
        assert rc == 5

    def test_ask_reply_without_a_usable_ask_id_is_refused(self, capsys,
                                                          monkeypatch):
        rc, out = run_scripted(
            capsys, monkeypatch, [("ask", {"status": "CREATED"})],
            "ask", "--question", QUESTION)
        assert rc == 5
        assert "BRIDGE_RESPONSE_INVALID" in out
        assert "ask_id=None" not in out

    def test_ask_wait_never_silently_skips_on_a_bad_reply(self, capsys,
                                                          monkeypatch):
        rc, out = run_scripted(
            capsys, monkeypatch, [("ask", {"status": "CREATED"})],
            "ask", "--question", QUESTION, "--wait",
            "--poll-seconds", "0.05", "--deadline-seconds", "1")
        assert rc == 5
        assert "BRIDGE_RESPONSE_INVALID" in out

    @pytest.mark.parametrize("bad", ["nan", "-inf", "inf", "-1", "-0.5"])
    def test_nonfinite_or_negative_deadline_is_a_usage_error(self, capsys,
                                                             monkeypatch,
                                                             bad):
        rc, _ = run_scripted(
            capsys, monkeypatch, [("result", NOT_YET)],
            "fetch", "--id", "gb-" + "1" * 32, "--wait",
            "--poll-seconds", "0.05", "--deadline-seconds", bad)
        assert rc == 2

    @pytest.mark.parametrize("bad", ["nan", "0", "-0.5", "inf"])
    def test_nonpositive_poll_interval_is_a_usage_error(self, capsys,
                                                        monkeypatch, bad):
        rc, _ = run_scripted(
            capsys, monkeypatch, [("result", NOT_YET)],
            "fetch", "--id", "gb-" + "1" * 32, "--wait",
            "--poll-seconds", bad, "--deadline-seconds", "1")
        assert rc == 2


# ── Round 2 (GBL contract): status carries expires_at; reconcile op ─────────


def run_raw(capsys, *args) -> tuple[int, str]:
    """Drive the CLI verbatim (no injected --socket/--bot), for the cases
    whose flag surface differs from the common shape."""
    rc = gbl_ask.main(list(args))
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


EXPIRED_STATUS = {"ask_id": "gb-" + "1" * 32, "state": "EXPIRED",
                  "status": "EXPIRED", "expires_at": "2026-11-11T12:00:00Z"}


class TestStatusContract:
    def test_status_prints_expires_at(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION)
        ask_id = ask_id_from(out)
        rc, out = run_cli(capsys, service, "status", "--id", ask_id)
        assert rc == 0
        assert "expires_at=" in out
        assert "expires_at=None" not in out

    def test_status_reports_expired_with_rc_4(self, capsys, monkeypatch):
        rc, out = run_scripted(capsys, monkeypatch,
                               [("status", EXPIRED_STATUS)],
                               "status", "--id", "gb-" + "1" * 32)
        assert rc == 4
        assert "status=EXPIRED" in out
        assert "expires_at=2026-11-11T12:00:00Z" in out

    def test_status_expired_over_the_real_door(self, service, capsys):
        envelope = build_ask(kind="question", principal=BOT, target=BOT,
                             idempotency_key="k-exp2",
                             title="Expiry fixture",
                             body="An ask that expires immediately.",
                             ttl_seconds=1, now=datetime.now(timezone.utc))
        service.store.create_ask(envelope)
        time.sleep(1.2)
        rc, out = run_cli(capsys, service, "status", "--id",
                          envelope["ask_id"])
        assert rc == 4
        assert "EXPIRED" in out


RECONCILED = {"status": "RECONCILED_DELIVERED", "ask_id": "gb-" + "1" * 32,
              "nudge_count": 1}


class TestReconcile:
    def test_reconcile_sends_exactly_principal_and_ask_id(self, capsys,
                                                          monkeypatch):
        made: list[ScriptedBridge] = []

        def factory(socket_path, timeout=gbl_ask.REQUEST_TIMEOUT_SECONDS):
            bridge = ScriptedBridge(socket_path,
                                    script=[("ok", RECONCILED)])
            made.append(bridge)
            return bridge

        monkeypatch.setattr(gbl_ask, "BridgeSocketClient", factory)
        rc, out = run_raw(capsys, "reconcile", "--socket",
                          "/tmp/gbl-fixture.sock", "--bot", BOT,
                          "--id", "gb-" + "1" * 32)
        assert rc == 0
        assert "status=RECONCILED_DELIVERED" in out
        # round-2 wire law: reconcile is exactly {principal, ask_id}
        assert made[0].calls == [("reconcile",
                                  {"principal": BOT,
                                   "ask_id": "gb-" + "1" * 32})]

    def test_reconcile_requires_the_bot_flag(self, capsys, monkeypatch):
        made: list[ScriptedBridge] = []

        def factory(socket_path, timeout=gbl_ask.REQUEST_TIMEOUT_SECONDS):
            bridge = ScriptedBridge(socket_path,
                                    script=[("ok", RECONCILED)])
            made.append(bridge)
            return bridge

        monkeypatch.setattr(gbl_ask, "BridgeSocketClient", factory)
        # --bot is required: the op carries the party check like every
        # other mutating op.
        rc, out = run_raw(capsys, "reconcile", "--socket",
                          "/tmp/gbl-fixture.sock", "--id", "gb-" + "1" * 32)
        assert rc == 2                          # argparse usage refusal
        assert made == []                       # nothing was sent

    def test_reconcile_over_the_real_door_is_typed(self, service, capsys):
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION)
        ask_id = ask_id_from(out)
        rc, out = run_raw(capsys, "reconcile", "--socket", service.socket,
                          "--bot", BOT, "--id", ask_id)
        assert rc == 5          # typed: no nudge attempt exists to settle
        assert "NUDGE_ATTEMPT_NOT_FOUND" in out

    def test_reconcile_unknown_ask_is_typed(self, service, capsys):
        rc, out = run_raw(capsys, "reconcile", "--socket", service.socket,
                          "--bot", BOT, "--id", "gb-" + "0" * 32)
        assert rc == 5
        assert "ASK_NOT_FOUND" in out

    def test_reconcile_refuses_a_malformed_ask_id(self, capsys, monkeypatch):
        rc, out = run_raw(capsys, "reconcile", "--socket",
                          "/tmp/gbl-fixture.sock", "--bot", BOT,
                          "--id", "not-an-ask-id")
        assert rc == 2
        assert "INVALID_ASK_ID" in out

    def test_help_lists_reconcile(self):
        help_text = gbl_ask.build_parser().format_help().lower()
        assert "reconcile" in help_text


class TestTokenHygiene:
    def test_help_offers_no_credential_option(self):
        help_text = gbl_ask.build_parser().format_help().lower()
        for word in BANNED:
            assert word not in help_text, f"help mentions {word!r}"

    def test_wire_bytes_carry_no_credential(self, service, capsys,
                                            monkeypatch):
        sent: list[bytes] = []
        real_socket = socket.socket

        class RecordingSocket(real_socket):
            def sendall(self, data):
                sent.append(bytes(data))
                return super().sendall(data)

        monkeypatch.setattr(socket, "socket", RecordingSocket)
        rc, _ = run_cli(capsys, service, "ask", "--question", QUESTION,
                        "--idempotency-key", "k-h")
        assert rc == 0
        assert sent, "no bytes were sent over the socket"
        wire = b"\n".join(sent).lower()
        for word in BANNED:
            assert word.encode() not in wire, f"wire mentions {word!r}"

    def test_output_carries_no_credential(self, service, capsys):
        run_cli(capsys, service, "ask", "--question", QUESTION,
                "--idempotency-key", "k-o")
        rc, out = run_cli(capsys, service, "ask", "--question", QUESTION,
                          "--idempotency-key", "k-o")
        assert rc == 0
        for word in BANNED:
            assert word not in out.lower(), f"output mentions {word!r}"
