from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from control_plane.executive_privileged_action import REQUEST_SCHEMA
from scripts.mmx_admin import build_request, send_request


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


def test_generated_request_id_is_contract_safe() -> None:
    request = build_request(["executive.services.stop"])
    assert request["request_id"].startswith("req-")
    assert 3 <= len(request["request_id"]) <= 64


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
