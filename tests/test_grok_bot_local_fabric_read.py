"""Refusal, bounded transport, and non-effect tests for Grok Mac read client."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

from integrations.grok_bot_local_fabric import read as client


RUN = "grok-secretary-local-canary-20261020-01"
ROOT = "grok-secretary-local-canary-20261020-root"


def _status(**changes):
    value = {
        "schema": client.STATUS_SCHEMA,
        "run_id": RUN,
        "root_id": ROOT,
        "parent_run_id": ROOT,
        "state": "TERMINAL",
        "rc": 0,
        "signal": "ok",
        "result_available": True,
        "accepted": True,
        "accepted_by": "deterministic",
        "acceptance_state": "ACCEPTED",
    }
    value.update(changes)
    return value


def _capture(monkeypatch, tmp_path, *, status=None, result=b"OK\n", rc=0):
    adapter = tmp_path / "fabric_task.py"
    adapter.write_text("safe test fixture only\n")
    seen = []

    def fake_run(argv, max_bytes):
        seen.append((argv, {"max_bytes": max_bytes}))
        assert argv[:2] == [sys.executable, str(adapter)]
        payload = json.dumps(_status() if status is None else status).encode()
        if argv[2] == "result":
            payload = result
        elif argv[2] != "status":
            pytest.fail("no action except incumbent status/result may be called")
        if rc != 0:
            raise client.Refused("ADAPTER_READ_REFUSED")
        return payload

    monkeypatch.setattr(client, "_run_bounded", fake_run)
    return adapter, seen


def test_status_returns_only_bounded_fields_and_is_not_authorization(monkeypatch, tmp_path):
    adapter, seen = _capture(monkeypatch, tmp_path)
    response = client.status(adapter, RUN, ROOT)
    assert response["schema"] == client.SCHEMA
    assert response["correlation_not_authentication"] is True
    assert response["may_retry_request"] is False
    assert response["status"]["root_id"] == ROOT
    assert set(response["status"]) == set(client.STATUS_FIELDS)
    assert len(seen) == 1
    assert seen[0][0][2:] == ["status", RUN]


def test_result_consumes_only_terminal_matching_root(monkeypatch, tmp_path):
    adapter, seen = _capture(monkeypatch, tmp_path)
    response = client.result(adapter, RUN, ROOT)
    assert response["text"] == "OK\n"
    assert response["result_sha256"] == hashlib.sha256(b"OK\n").hexdigest()
    assert response["result_bytes"] == 3
    assert response["accepted"] is True
    assert [a[0][2] for a in seen] == ["status", "result"]
    assert seen[-1][0][3:] == [RUN, "--max-bytes", str(client.DEFAULT_RESULT_BYTES)]


@pytest.mark.parametrize("value", [
    "../invalid", "bad id", "", ";rm -rf /", "\n", "x" * 129
])
def test_run_ids_fail_before_call(monkeypatch, tmp_path, value):
    adapter, seen = _capture(monkeypatch, tmp_path)
    with pytest.raises(client.Refused, match="INVALID_ID"):
        client.status(adapter, value, ROOT)
    assert seen == []


def test_mismatched_or_unverified_root_cannot_read_result(monkeypatch, tmp_path):
    adapter, seen = _capture(monkeypatch, tmp_path, status=_status(root_id=None))
    with pytest.raises(client.Refused, match="ROOT_NOT_VERIFIED"):
        client.result(adapter, RUN, ROOT)
    assert len(seen) == 1


@pytest.mark.parametrize("changes", [
    {"state": "ACTIVE_OR_WAITING", "result_available": False, "rc": None},
    {"state": "TERMINAL", "rc": 1},
    {"state": "TERMINAL", "result_available": False},
])
def test_nonterminal_or_unsuccessful_result_refused(monkeypatch, tmp_path, changes):
    adapter, seen = _capture(monkeypatch, tmp_path, status=_status(**changes))
    with pytest.raises(client.Refused, match="RESULT_NOT_READY"):
        client.result(adapter, RUN, ROOT)
    assert len(seen) == 1


def test_not_found_is_observation_only(monkeypatch, tmp_path):
    adapter, seen = _capture(monkeypatch, tmp_path, status=_status(state="NOT_FOUND", root_id=None, rc=None, result_available=False))
    value = client.status(adapter, RUN, ROOT)
    assert value["status"]["state"] == "NOT_FOUND"
    assert value["may_retry_request"] is False
    assert len(seen) == 1


@pytest.mark.parametrize("bad", [
    b"not-json", b"{}", b'{"schema":"unknown","run_id":"x","state":"TERMINAL"}'
])
def test_invalid_status_is_not_canonical(monkeypatch, tmp_path, bad):
    adapter, seen = _capture(monkeypatch, tmp_path)
    orig = client._call
    monkeypatch.setattr(client, "_call", lambda *_: bad)
    with pytest.raises(client.Refused, match="STATUS_INVALID"):
        client.status(adapter, RUN, ROOT)
    assert seen == []
    monkeypatch.setattr(client, "_call", orig)


def test_result_bounds_and_invalid_utf8_fail_closed(monkeypatch, tmp_path):
    adapter, seen = _capture(monkeypatch, tmp_path, result=b"\xff")
    with pytest.raises(client.Refused, match="RESULT_BOUND_INVALID"):
        client.result(adapter, RUN, ROOT, client.MAX_RESULT_BYTES + 1)
    assert seen == []
    with pytest.raises(client.Refused, match="RESULT_NOT_UTF8"):
        client.result(adapter, RUN, ROOT)
    assert len(seen) == 2


def test_status_payload_too_large_refuses_without_echo(monkeypatch, tmp_path):
    adapter, _ = _capture(monkeypatch, tmp_path)
    monkeypatch.setattr(client, "_run_bounded", lambda *_: b"A" * (client.MAX_STATUS_BYTES + 1))
    with pytest.raises(client.Refused, match="RESPONSE_TOO_LARGE"):
        client.status(adapter, RUN, ROOT)


def test_nonzero_exit_does_not_echo_adapter_stderr(monkeypatch, tmp_path):
    adapter, seen = _capture(monkeypatch, tmp_path, rc=17)
    with pytest.raises(client.Refused) as exc:
        client.status(adapter, RUN, ROOT)
    assert str(exc.value) == "ADAPTER_READ_REFUSED"
    assert "secret" not in str(exc.value).lower()


def test_adapter_symlink_is_not_invoked(monkeypatch, tmp_path):
    adapter, seen = _capture(monkeypatch, tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(adapter)
    with pytest.raises(client.Refused, match="ADAPTER_UNAVAILABLE"):
        client.status(alias, RUN, ROOT)
    assert seen == []


def test_cli_has_no_dispatch_or_accept_endpoint(tmp_path):
    adapter = tmp_path / "fabric_task.py"
    adapter.write_text("no execution")
    with pytest.raises(SystemExit) as exc:
        client.main(["--adapter", str(adapter), "request", "--run-id", RUN, "--root-id", ROOT])
    assert exc.value.code == 2


def test_process_reader_bounds_output_before_unlimited_collection():
    with pytest.raises(client.Refused, match="RESPONSE_TOO_LARGE"):
        client._run_bounded(
            [sys.executable, "-c", "import sys;sys.stdout.write('a' * 999999)"],
            128,
        )


def test_process_reader_timeout_kills_exact_process_group(monkeypatch):
    monkeypatch.setattr(client, "TIMEOUT_SECONDS", 0.15)
    with pytest.raises(client.Refused, match="ADAPTER_OBSERVATION_UNAVAILABLE"):
        client._run_bounded([sys.executable, "-c", "import time;time.sleep(10)"], 128)


def test_process_reader_refuses_nonzero_exit_without_echoing_stderr():
    with pytest.raises(client.Refused, match="ADAPTER_READ_REFUSED"):
        client._run_bounded(
            [sys.executable, "-c", "import sys;sys.stderr.write('private secret');sys.exit(22)"],
            128,
        )
