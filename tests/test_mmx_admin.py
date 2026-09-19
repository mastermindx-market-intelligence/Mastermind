from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    STATUS_REQUEST_SCHEMA,
    PrivilegedActionError,
)
from scripts import mmx_admin
from scripts.mmx_admin import build_request, build_status_request, send_request, send_status_request


def test_client_builds_verify_ready_request() -> None:
    request = build_request(
        [
            "executive.worker_auth.verify_ready",
            "--slot-id",
            "codex-pro-01",
            "--credential-expires-at",
            "2026-09-14T00:00:00Z",
            "--request-id",
            "req-ready-001",
        ]
    )
    assert request == {
        "schema": REQUEST_SCHEMA,
        "request_id": "req-ready-001",
        "action": "executive.worker_auth.verify_ready",
        "args": {
            "slot_id": "codex-pro-01",
            "credential_expires_at": "2026-09-14T00:00:00Z",
        },
    }


def test_client_builds_company_verify_ready_request() -> None:
    request = build_request(
        [
            "executive.worker_auth.verify_ready",
            "--expected-credential-kind",
            "service-account",
            "--workspace-binding-class",
            "company-workspace-admin-attested",
            "--credential-expires-at",
            "2026-09-14T00:00:00Z",
            "--request-id",
            "req-company-001",
        ]
    )
    assert request["args"] == {
        "expected_credential_kind": "service-account",
        "workspace_binding_class": "company-workspace-admin-attested",
        "credential_expires_at": "2026-09-14T00:00:00Z",
    }


def test_service_action_cannot_accept_arbitrary_command_or_path() -> None:
    with pytest.raises(SystemExit):
        build_request(["executive.services.start", "--command", "/bin/sh"])


def test_unknown_action_refuses_in_argparse() -> None:
    with pytest.raises(SystemExit):
        build_request(["shell", "--request-id", "req-bad-001"])


def test_client_builds_fixed_secondary_host_power_policy_request() -> None:
    request = build_request(
        [
            "executive.host.prepare_secondary_power_policy",
            "--request-id",
            "req-power-001",
        ]
    )
    assert request == {
        "schema": REQUEST_SCHEMA,
        "request_id": "req-power-001",
        "action": "executive.host.prepare_secondary_power_policy",
        "args": {},
    }


def test_secondary_host_power_policy_refuses_caller_arguments() -> None:
    with pytest.raises(PrivilegedActionError, match="host policy action arguments"):
        build_request(
            [
                "executive.host.prepare_secondary_power_policy",
                "--slot-id",
                "codex-pro-01",
                "--request-id",
                "req-power-bad-001",
            ]
        )


def test_generated_request_id_is_contract_safe() -> None:
    request = build_request(["executive.services.stop"])
    assert request["request_id"].startswith("req-")
    assert 3 <= len(request["request_id"]) <= 64


def test_client_timeout_exceeds_installed_privileged_broker_budget() -> None:
    install = (Path(__file__).resolve().parents[1] / "ops" / "executive_os" / "install.sh").read_text()
    assert '"timeout_seconds": 600' in install
    assert mmx_admin.DEFAULT_CLIENT_TIMEOUT_SECONDS > 600


def test_main_prints_stable_request_id_before_transport_failure(monkeypatch, capsys) -> None:
    def fail_send(*_args, **_kwargs):
        raise TimeoutError("simulated transport loss")

    monkeypatch.setattr(mmx_admin, "send_request", fail_send)
    rc = mmx_admin.main(["executive.services.start", "--request-id", "req-visible-001"])
    captured = capsys.readouterr()
    assert rc == 69
    assert "request_id=req-visible-001" in captured.err
    assert "transport failure" in captured.err


def test_send_request_uses_one_newline_delimited_json_frame(short_socket_root: Path) -> None:
    socket_path = short_socket_root / "broker.sock"
    observed = {}
    ready = threading.Event()

    def server() -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        ready.set()
        connection, _ = listener.accept()
        with connection:
            data = b""
            while not data.endswith(b"\n"):
                data += connection.recv(4096)
            observed["raw"] = data
            connection.sendall(b'{"ok":true,"receipt":{"outcome":"SUCCEEDED"}}\n')
        listener.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(2)
    request = build_request(["executive.services.restart", "--request-id", "req-wire-001"])
    response = send_request(request, socket_path=socket_path)
    thread.join(2)
    assert response["ok"] is True
    frame = observed["raw"]
    assert frame.count(b"\n") == 1
    assert json.loads(frame) == request


def test_status_client_builds_exact_status_request() -> None:
    request = build_status_request(["status", "--request-id", "req-status-001"])
    assert request == {"schema": STATUS_REQUEST_SCHEMA, "request_id": "req-status-001"}


def test_status_requires_explicit_request_id_and_never_generates_one() -> None:
    with pytest.raises(SystemExit):
        build_status_request(["status"])


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "--request-id", "req-001", "--slot-id", "codex-pro-01"],
        [
            "status",
            "--request-id", "req-001",
            "--expected-credential-kind", "service-account",
        ],
        [
            "status",
            "--request-id", "req-001",
            "--workspace-binding-class", "company-workspace-admin-attested",
        ],
        [
            "status",
            "--request-id", "req-001",
            "--credential-expires-at", "2026-09-14T00:00:00Z",
        ],
    ],
)
def test_status_rejects_effect_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        build_status_request(argv)


def test_existing_effect_actions_remain_backward_compatible() -> None:
    request = build_request(["executive.services.start", "--request-id", "req-effect-001"])
    assert request["action"] == "executive.services.start"
    assert request["schema"] == REQUEST_SCHEMA


def test_main_status_terminal_exit_code_is_zero_regardless_of_stored_outcome(monkeypatch, capsys) -> None:
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": True,
        "query": True,
        "status": "TERMINAL",
        "request_id": "req-001",
        "installed_release_sha": "a" * 40,
        "receipt": {"request_id": "req-001", "outcome": "FAILED", "exit_code": 65},
    }
    monkeypatch.setattr(mmx_admin, "send_status_request", lambda *_a, **_k: response)
    rc = mmx_admin.main(["status", "--request-id", "req-001"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == response


def test_main_power_effect_unknown_exit_code_is_75(monkeypatch, capsys) -> None:
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": False,
        "error": "EFFECT_UNKNOWN",
        "detail": "privileged child reported action-level effect uncertainty",
    }
    monkeypatch.setattr(mmx_admin, "send_request", lambda *_a, **_k: response)

    rc = mmx_admin.main(
        [
            "executive.host.prepare_secondary_power_policy",
            "--request-id",
            "req-power-unknown",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 75
    assert "request_id=req-power-unknown" in captured.err
    assert json.loads(captured.out) == response


def test_main_status_effect_unknown_exit_code_is_75(monkeypatch) -> None:
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": True,
        "query": True,
        "status": "EFFECT_UNKNOWN",
        "request_id": "req-001",
        "installed_release_sha": "a" * 40,
    }
    monkeypatch.setattr(mmx_admin, "send_status_request", lambda *_a, **_k: response)
    assert mmx_admin.main(["status", "--request-id", "req-001"]) == 75


def test_main_status_not_found_exit_code_is_4(monkeypatch) -> None:
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": True,
        "query": True,
        "status": "NOT_FOUND",
        "request_id": "req-001",
        "installed_release_sha": "a" * 40,
    }
    monkeypatch.setattr(mmx_admin, "send_status_request", lambda *_a, **_k: response)
    assert mmx_admin.main(["status", "--request-id", "req-001"]) == 4


def test_main_status_refused_response_is_nonzero(monkeypatch) -> None:
    response = {"ok": False, "error": "REFUSED", "detail": "malformed state"}
    monkeypatch.setattr(mmx_admin, "send_status_request", lambda *_a, **_k: response)
    assert mmx_admin.main(["status", "--request-id", "req-001"]) != 0


def test_main_status_transport_failure_keeps_original_request_id_visible(monkeypatch, capsys) -> None:
    def fail_send(*_args, **_kwargs):
        raise TimeoutError("simulated transport loss")

    monkeypatch.setattr(mmx_admin, "send_status_request", fail_send)
    rc = mmx_admin.main(["status", "--request-id", "req-visible-status-001"])
    captured = capsys.readouterr()
    assert rc == 69
    assert "request_id=req-visible-status-001" in captured.err
    assert "transport failure" in captured.err


def test_send_status_request_uses_one_newline_delimited_json_frame(short_socket_root: Path) -> None:
    socket_path = short_socket_root / "broker-status.sock"
    observed = {}
    ready = threading.Event()

    def server() -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        ready.set()
        connection, _ = listener.accept()
        with connection:
            data = b""
            while not data.endswith(b"\n"):
                data += connection.recv(4096)
            observed["raw"] = data
            connection.sendall(
                b'{"ok":true,"query":true,"status":"NOT_FOUND",'
                b'"request_id":"req-status-wire-001",'
                b'"installed_release_sha":"' + b"a" * 40 + b'"}\n'
            )
        listener.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(2)
    request = build_status_request(["status", "--request-id", "req-status-wire-001"])
    response = send_status_request(request, socket_path=socket_path)
    thread.join(2)
    assert response["ok"] is True
    assert response["status"] == "NOT_FOUND"
    frame = observed["raw"]
    assert frame.count(b"\n") == 1
    assert json.loads(frame) == request


@pytest.mark.parametrize("patch", [{"request_id": "other-001"}, {"schema": "unknown"}, {"receipt": None}])
def test_status_client_refuses_uncorrelated_or_malformed_terminal(monkeypatch, patch) -> None:
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1", "ok": True,
        "query": True, "status": "TERMINAL", "request_id": "req-001",
        "installed_release_sha": "a" * 40,
        "receipt": {"request_id": "req-001", "outcome": "FAILED", "exit_code": 65},
    }
    response.update(patch)
    monkeypatch.setattr(mmx_admin, "send_status_request", lambda *_a, **_k: response)
    assert mmx_admin.main(["status", "--request-id", "req-001"]) != 0


def test_cli_rejects_caller_selected_socket_path() -> None:
    with pytest.raises(SystemExit):
        build_request(
            [
                "executive.services.start",
                "--request-id",
                "req-fixed-socket-001",
                "--socket",
                "/tmp/untrusted-broker.sock",
            ]
        )


def test_main_effect_refuses_uncorrelated_success_response(monkeypatch, capsys) -> None:
    response = {
        "schema": "mastermind.executive_privileged_action_response.v1",
        "ok": True,
        "replayed": False,
        "receipt": {
            "schema": "mastermind.executive_privileged_action_receipt.v1",
            "request_id": "req-other-001",
            "request_sha256": "0" * 64,
            "action": "executive.services.start",
            "effect_class": "SERVICE_CONTROL",
            "started_at": "2026-09-14T00:00:00Z",
            "finished_at": "2026-09-14T00:00:01Z",
            "exit_code": 0,
            "outcome": "SUCCEEDED",
            "release_sha": "a" * 40,
            "broker_version": "1",
            "stdout_bytes": 0,
            "stdout_sha256": "0" * 64,
            "stdout_excerpt": "",
            "stderr_bytes": 0,
            "stderr_sha256": "0" * 64,
            "stderr_excerpt": "",
        },
    }
    monkeypatch.setattr(mmx_admin, "send_request", lambda *_a, **_k: response)

    rc = mmx_admin.main(["executive.services.start", "--request-id", "req-bound-001"])
    captured = capsys.readouterr()

    assert rc != 0
    assert "refused or invalid" in captured.err
