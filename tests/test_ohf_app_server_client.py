from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

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
