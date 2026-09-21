from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane.visible_turn_projection import VisibleTurnProjection
import scripts.ohf.laboratory as laboratory
from scripts.ohf.laboratory import AppServerClient, JsonRpcError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "ohf_raw_app_server.py"
SECRET = "sk-raw-turn-fixture-ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _client(tmp_path: Path, *, mode: str = "normal") -> AppServerClient:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(REPO_ROOT),
        "OHF_RAW_FIXTURE_MODE": mode,
    }
    client = AppServerClient(
        [sys.executable, str(FIXTURE)], env=env, cwd=tmp_path
    )
    client.start()
    return client


def test_ordinary_response_remains_redacted_but_raw_page_is_one_shot(tmp_path):
    client = _client(tmp_path)
    try:
        ordinary = client.request("thread/turns/list", {"threadId": "THREAD"})
        assert SECRET not in repr(ordinary)

        page = client.request_raw_turn_page(
            thread_id="THREAD", native_turn_id="TURN-RAW"
        )
        assert repr(page) == "<private-raw-turn-page>"
        assert str(page) == "<private-raw-turn-page>"
        assert SECRET not in repr(page)
        consumed = page.consume()
        assert consumed["data"][0]["items"][0]["text"] == SECRET
        with pytest.raises(JsonRpcError, match="already consumed"):
            page.consume()
        assert SECRET not in client.stderr_text()
        assert SECRET not in repr(client.notifications)
    finally:
        client.close()


@pytest.mark.parametrize("mode", ["invalid_utf8", "malformed"])
def test_malformed_raw_transport_fails_constant_without_secret(tmp_path, mode):
    client = _client(tmp_path, mode=mode)
    try:
        with pytest.raises(JsonRpcError) as excinfo:
            client.request_raw_turn_page(
                thread_id="THREAD", native_turn_id="TURN-RAW", timeout=2
            )
        assert SECRET not in str(excinfo.value)
        assert SECRET not in repr(excinfo.value)
    finally:
        client.close()


def test_oversized_raw_frame_compromises_transport_without_retaining_frame(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(laboratory, "APP_SERVER_MAX_FRAME_BYTES", 256)
    client = _client(tmp_path, mode="oversized")
    try:
        with pytest.raises(JsonRpcError, match="transport compromised") as excinfo:
            client.request_raw_turn_page(
                thread_id="THREAD", native_turn_id="TURN-RAW", timeout=2
            )
        assert "padding" not in str(excinfo.value)
        assert client.alive() is False
    finally:
        client.close()


def test_raw_method_is_hard_wired_to_closed_page_contract(tmp_path):
    client = _client(tmp_path)
    try:
        with pytest.raises(JsonRpcError, match="identity"):
            client.request_raw_turn_page(thread_id="", native_turn_id="TURN-RAW")
        with pytest.raises(TypeError):
            client.request_raw_turn_page(  # type: ignore[call-arg]
                thread_id="THREAD", native_turn_id="TURN-RAW", method="account/read"
            )
    finally:
        client.close()


def test_lc1_extraction_publishes_after_demux_and_never_retains_raw_pages(tmp_path):
    projection = VisibleTurnProjection()
    client = _client(tmp_path)
    client.visible_projection = projection
    try:
        ordinary = client.request("thread/turns/list", {"threadId": "THREAD"})
        assert isinstance(ordinary, dict)
        assert projection.parser_gaps() == ()
        assert projection.active_prebind_request_id() is None
        assert isinstance(client.notifications, list)
    finally:
        client.close()


def test_observer_extraction_fault_does_not_escape_receiver_demux(monkeypatch):
    projection = VisibleTurnProjection()
    client = AppServerClient([], env={}, cwd=Path("."))
    client.proc = None
    client.visible_projection = projection
    first = json.loads(
        '{"method":"item/updated","params":{"item":{"id":"observer-fault",'
        '"sequence":1,"type":"agentMessage","text":"valid frame"}}}'
    )
    second = json.loads(
        '{"method":"item/updated","params":{"item":{"id":"observer-fault",'
        '"sequence":2,"type":"agentMessage","text":"following frame"}}}'
    )
    terminal = json.loads(
        '{"method":"turn/completed","params":{"turn":{"id":"terminal"}}}'
    )

    def fail_once(operation):
        original = getattr(projection, operation)

        def failing(*args, **kwargs):
            if failing.calls == 0:
                failing.calls += 1
                raise RuntimeError("observer fixture failure")
            return original(*args, **kwargs)

        failing.calls = 0
        monkeypatch.setattr(projection, operation, failing)

    fail_once("publish_demultiplexed")
    stdout_data = (
        json.dumps(first)
        + "\n"
        + json.dumps(second)
        + "\n"
        + json.dumps(terminal)
        + "\n"
    ).encode("utf-8")
    client.proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).resolve().parent),
    )
    assert client.proc.stdin is not None and client.proc.stdout is not None
    client.proc.stdin.write(stdout_data)
    client.proc.stdin.close()
    client._read_stdout()

    assert client.notifications == [first, second, terminal]
    assert client.observer_faults == (
        laboratory.ObserverFault("publish_demultiplexed", "RuntimeError"),
    )
    assert projection._viewers_by_turn == {}


def test_request_preserves_typed_send_failure_before_payload_exists(monkeypatch):
    client = AppServerClient([], env={}, cwd=Path("."))

    def fail_send(_message):
        raise JsonRpcError("sentinel send failure")

    monkeypatch.setattr(client, "_send", fail_send)

    with pytest.raises(JsonRpcError, match="sentinel send failure"):
        client.request("account/read", timeout=0.01)

    assert client._responses == {}


def test_request_preserves_typed_timeout_before_payload_exists(monkeypatch):
    client = AppServerClient([], env={}, cwd=Path("."))
    monkeypatch.setattr(client, "_send", lambda _message: None)

    with pytest.raises(JsonRpcError, match="timeout waiting for account/read"):
        client.request("account/read", timeout=0.001)

    assert client._responses == {}
