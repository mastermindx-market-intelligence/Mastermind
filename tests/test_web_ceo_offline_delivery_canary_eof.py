"""Closed canary errors across actual local control-socket EOF responses."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import tempfile
import threading

import pytest

from scripts.web_ceo_offline_delivery_canary import ERROR_SCHEMA, main


@pytest.mark.parametrize("response", [b"", b'{"ok":'], ids=["empty-eof", "partial-eof"])
def test_control_socket_eof_returns_closed_input_refusal(response, capsys):
    errors = []
    with tempfile.TemporaryDirectory(prefix="canary-eof-") as directory:
        root = Path(directory)
        socket_path = root / "control.sock"
        runtime_root = root / "unopened-runtime"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(1)
            listener.settimeout(3)

            def serve_one():
                try:
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(3)
                        request = bytearray()
                        while not request.endswith(b"\n"):
                            chunk = connection.recv(1024)
                            if not chunk:
                                raise AssertionError("client closed before its request")
                            request.extend(chunk)
                            assert len(request) <= 8192
                        assert json.loads(request)["command"] == "offline-delivery-observation"
                        if response:
                            connection.sendall(response)
                        # Close before the required newline: empty or partial EOF.
                except BaseException as exc:
                    errors.append(exc)

            server = threading.Thread(target=serve_one)
            server.start()
            try:
                result = main([
                    "--runtime-root", str(runtime_root),
                    "--control-socket", str(socket_path),
                    "--root-job-id", "JOB-fixture",
                    "--expected-release-sha", "a" * 40,
                ])
            finally:
                server.join(timeout=4)
            assert not server.is_alive()
            assert errors == []
            assert result == 2
            captured = capsys.readouterr()
            assert captured.err == ""
            assert json.loads(captured.out) == {
                "schema": ERROR_SCHEMA,
                "error": "INPUT_REFUSED",
                "root_job_id": "JOB-fixture",
            }
            assert not runtime_root.exists()
