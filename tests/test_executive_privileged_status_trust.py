"""Broker status -> real CLI trust-boundary tests; no privileged I/O."""
from __future__ import annotations

import copy
import hashlib
import json
import socket
import threading

import pytest

from control_plane import executive_privileged_broker as broker
from control_plane import executive_privileged_client as client
from control_plane.executive_privileged_action import REQUEST_SCHEMA, canonical_request_bytes, validate_request
from scripts import mmx_admin


REQUEST_ID = "req-status-trust-001"
EXTRA_SENTINEL = "UNREVIEWED_STATUS_FIELD"


def _receipt(*, failed: bool = False) -> dict:
    request = validate_request({"schema": REQUEST_SCHEMA, "request_id": REQUEST_ID,
                                "action": "executive.services.start", "args": {}})
    empty_digest = hashlib.sha256(b"").hexdigest()
    return {
        "schema": broker.RECEIPT_SCHEMA,
        "request_id": REQUEST_ID,
        "request_sha256": hashlib.sha256(canonical_request_bytes(request)).hexdigest(),
        "action": "executive.services.start", "effect_class": "SERVICE_CONTROL",
        "started_at": "2026-09-17T00:00:00Z", "finished_at": "2026-09-17T00:00:01Z",
        "exit_code": 65 if failed else 0, "outcome": "FAILED" if failed else "SUCCEEDED",
        "release_sha": "b" * 40, "broker_version": "1",
        "stdout_bytes": 0, "stdout_sha256": empty_digest, "stdout_excerpt": "",
        "stderr_bytes": 0, "stderr_sha256": empty_digest, "stderr_excerpt": "",
    }


def _reply(status: str, *, failed: bool = False) -> dict:
    projection = {"status": status, "request_id": REQUEST_ID, "installed_release_sha": "a" * 40}
    if status == "TERMINAL":
        projection["receipt"] = _receipt(failed=failed)
    elif status == "EFFECT_UNKNOWN":
        projection["marker_release_sha"] = "b" * 40
    return broker._wire_status(projection)


@pytest.mark.parametrize("status,expected_exit", [("TERMINAL", 0), ("EFFECT_UNKNOWN", 75), ("NOT_FOUND", 4)])
@pytest.mark.parametrize("failed", [False, True])
def test_owner_status_wire_reaches_real_cli_without_effect_or_history_rewrite(monkeypatch, capsys, status, expected_exit, failed):
    reply = _reply(status, failed=failed)
    original = copy.deepcopy(reply)
    queried = []
    def status_only(request, **kwargs):
        queried.append(request)
        return reply
    def no_effect(*args, **kwargs):
        raise AssertionError("status lookup must never submit an effect")
    monkeypatch.setattr(mmx_admin, "send_status_request", status_only)
    monkeypatch.setattr(mmx_admin, "send_request", no_effect)
    assert mmx_admin.main(["status", "--request-id", REQUEST_ID]) == expected_exit
    output = capsys.readouterr()
    assert json.loads(output.out) == original
    assert len(queried) == 1 and queried[0]["request_id"] == REQUEST_ID
    assert reply == original
    if status == "TERMINAL":
        assert json.loads(output.out)["receipt"]["release_sha"] == "b" * 40


@pytest.mark.parametrize("status", ["TERMINAL", "EFFECT_UNKNOWN", "NOT_FOUND"])
@pytest.mark.parametrize("extra_key", ["unreviewed_data", "ready", "replayed"])
def test_status_extra_fields_are_refused_before_cli_output(monkeypatch, capsys, status, extra_key):
    reply = _reply(status)
    reply[extra_key] = EXTRA_SENTINEL
    monkeypatch.setattr(mmx_admin, "send_status_request", lambda *args, **kwargs: reply)
    assert mmx_admin.main(["status", "--request-id", REQUEST_ID]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert EXTRA_SENTINEL not in output.err
    assert "invalid" in output.err


@pytest.mark.parametrize("missing_key", ["schema", "request_sha256", "release_sha", "action", "effect_class", "broker_version", "started_at", "stdout_excerpt"])
def test_status_missing_receipt_fields_never_prove_terminal(missing_key):
    reply = _reply("TERMINAL")
    del reply["receipt"][missing_key]
    with pytest.raises(RuntimeError):
        client.validate_status_response(reply, expected_request_id=REQUEST_ID)


@pytest.mark.parametrize("key,value", [
    ("request_sha256", "not-a-digest"), ("release_sha", "not-a-release"),
    ("action", "unreviewed.action"), ("effect_class", "WRONG_CLASS"),
    ("broker_version", ""), ("started_at", "invalid-time"),
    ("finished_at", "2026-09-16T00:00:00Z"), ("stdout_bytes", -1),
    ("stderr_sha256", "bad"), ("stdout_excerpt", "x" * 301),
])
def test_status_terminal_uses_existing_complete_receipt_validator(key, value):
    reply = _reply("TERMINAL")
    reply["receipt"][key] = value
    with pytest.raises(RuntimeError):
        client.validate_status_response(reply, expected_request_id=REQUEST_ID)


@pytest.mark.parametrize("value", [None, True, "", "a" * 39, "A" * 40, "x" * 40])
def test_status_unknown_refuses_invalid_marker_release(value):
    reply = _reply("EFFECT_UNKNOWN")
    reply["marker_release_sha"] = value
    with pytest.raises(RuntimeError):
        client.validate_status_response(reply, expected_request_id=REQUEST_ID)


def test_status_unknown_requires_marker_release():
    reply = _reply("EFFECT_UNKNOWN")
    del reply["marker_release_sha"]
    with pytest.raises(RuntimeError):
        client.validate_status_response(reply, expected_request_id=REQUEST_ID)


@pytest.mark.parametrize("status", ["EFFECT_UNKNOWN", "NOT_FOUND"])
def test_status_nonterminal_refuses_receipt(status):
    reply = _reply(status)
    reply["receipt"] = _receipt()
    with pytest.raises(RuntimeError):
        client.validate_status_response(reply, expected_request_id=REQUEST_ID)


def test_status_terminal_refuses_extra_receipt_data_at_cli_boundary(monkeypatch, capsys):
    reply = _reply("TERMINAL")
    reply["receipt"]["unreviewed_data"] = EXTRA_SENTINEL
    monkeypatch.setattr(mmx_admin, "send_status_request", lambda *args, **kwargs: reply)
    assert mmx_admin.main(["status", "--request-id", REQUEST_ID]) == 1
    output = capsys.readouterr()
    assert output.out == "" and EXTRA_SENTINEL not in output.err


@pytest.mark.parametrize("reply", [None, [], "TERMINAL", 1])
def test_status_non_mapping_refuses_with_controlled_error(reply):
    with pytest.raises(RuntimeError):
        client.validate_status_response(reply, expected_request_id=REQUEST_ID)


@pytest.mark.parametrize("status,expected_exit", [("TERMINAL", 0), ("EFFECT_UNKNOWN", 75), ("NOT_FOUND", 4)])
@pytest.mark.parametrize("extra", [False, True])
def test_real_socket_status_frame_reaches_cli_without_resubmit_or_extra_output(
    short_socket_root, monkeypatch, capsys, status, expected_exit, extra
):
    reply = _reply(status, failed=True)
    if extra:
        reply["unreviewed_data"] = EXTRA_SENTINEL
    path = short_socket_root / "status-trust.sock"
    seen = []
    errors = []
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.settimeout(5)
    listener.bind(str(path))
    listener.listen(1)

    def serve_once():
        try:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(5)
                data = b""
                while not data.endswith(b"\n"):
                    part = connection.recv(4096)
                    if not part or len(data) + len(part) > 8192:
                        raise AssertionError("invalid bounded status request frame")
                    data += part
                seen.append(json.loads(data))
                connection.sendall(json.dumps(reply).encode() + b"\n")
        except Exception as exc:
            errors.append(exc)
        finally:
            listener.close()

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    monkeypatch.setattr(mmx_admin, "DEFAULT_SOCKET", path)
    def no_effect(*args, **kwargs):
        raise AssertionError("status recovery may not resubmit an effect")
    monkeypatch.setattr(mmx_admin, "send_request", no_effect)
    try:
        result = mmx_admin.main(["status", "--request-id", REQUEST_ID])
    finally:
        thread.join(6)
        listener.close()
    assert not thread.is_alive() and errors == []
    assert seen == [{"schema": "mastermind.executive_privileged_action_status_request.v1",
                     "request_id": REQUEST_ID}]
    output = capsys.readouterr()
    assert result == (1 if extra else expected_exit)
    if extra:
        assert output.out == "" and EXTRA_SENTINEL not in output.err
    else:
        assert json.loads(output.out) == reply


@pytest.mark.parametrize("failed", [False, True])
def test_validated_historical_receipt_preserves_original_release_and_outcome(failed):
    reply = _reply("TERMINAL", failed=failed)
    original = copy.deepcopy(reply)
    result = client.validate_status_response(reply, expected_request_id=REQUEST_ID)
    assert result == original and reply == original
    assert result["receipt"] is not reply["receipt"]
    assert result["receipt"]["release_sha"] != result["installed_release_sha"]


def test_validated_unknown_marker_keeps_historical_release():
    reply = _reply("EFFECT_UNKNOWN")
    original = copy.deepcopy(reply)
    assert client.validate_status_response(reply, expected_request_id=REQUEST_ID) == original
    assert reply == original
