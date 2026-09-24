from __future__ import annotations

import json

import pytest

from control_plane.executive_privileged_action import REQUEST_SCHEMA
from scripts import mmx_secondary_host_power as client


def test_build_request_is_one_fixed_action_with_empty_args() -> None:
    request = client.build_request(["--request-id", "req-power-001"])
    assert request == {
        "schema": REQUEST_SCHEMA,
        "request_id": "req-power-001",
        "action": "executive.host.prepare_secondary_power_policy",
        "args": {},
    }


def test_request_id_is_mandatory() -> None:
    with pytest.raises(SystemExit):
        client.build_request([])


def test_extra_arguments_cannot_widen_action() -> None:
    with pytest.raises(SystemExit):
        client.build_request(
            ["--request-id", "req-power-001", "--host", "admins-Mini-652"]
        )


def test_success_reuses_mmx_admin_transport_and_trust(monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": True,
        "replayed": False,
        "receipt": {"outcome": "SUCCEEDED"},
    }

    def send(request, *, socket_path):
        seen["request"] = request
        seen["socket_path"] = socket_path
        return response

    def classify(observed, request):
        assert observed is response
        assert request["action"] == client.ACTION
        return 0

    monkeypatch.setattr(client.mmx_admin, "send_request", send)
    monkeypatch.setattr(client.mmx_admin, "_effect_exit_code", classify)

    rc = client.main(["--request-id", "req-power-success"])
    captured = capsys.readouterr()

    assert rc == 0
    assert seen["request"]["request_id"] == "req-power-success"
    assert seen["socket_path"] == client.mmx_admin.DEFAULT_SOCKET
    assert json.loads(captured.out) == response
    assert "request_id=req-power-success" in captured.err


def test_effect_unknown_is_preserved_from_existing_client(monkeypatch, capsys) -> None:
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": False,
        "error": "EFFECT_UNKNOWN",
        "detail": "same-carrier reconciliation required",
    }
    monkeypatch.setattr(
        client.mmx_admin,
        "send_request",
        lambda *_args, **_kwargs: response,
    )
    monkeypatch.setattr(
        client.mmx_admin,
        "_effect_exit_code",
        lambda observed, request: 75,
    )

    rc = client.main(["--request-id", "req-power-unknown"])
    captured = capsys.readouterr()

    assert rc == 75
    assert json.loads(captured.out) == response


def test_transport_failure_does_not_retry(monkeypatch, capsys) -> None:
    calls = 0

    def fail(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise OSError("fixture unavailable")

    monkeypatch.setattr(client.mmx_admin, "send_request", fail)

    assert client.main(["--request-id", "req-power-transport"]) == 69
    assert calls == 1
    assert "transport failure" in capsys.readouterr().err
