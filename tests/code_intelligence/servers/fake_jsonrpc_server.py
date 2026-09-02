"""Hostile fake JSON-RPC stdio server used to falsify the client.

Mode is argv[1]. Each mode exercises one failure the client must survive.
This file is corpus/harness, never a production server.
"""

from __future__ import annotations

import json
import os
import sys
import time


def _write(data: bytes) -> None:
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _frame(obj: object) -> bytes:
    body = json.dumps(obj).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


def _read_message() -> dict | None:
    headers = b""
    while not headers.endswith(b"\r\n\r\n"):
        char = sys.stdin.buffer.read(1)
        if not char:
            return None
        headers += char
    length = 0
    for line in headers.decode("ascii", "replace").split("\r\n"):
        if line.lower().startswith("content-length"):
            length = int(line.split(":", 1)[1].strip())
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body)


def main() -> None:
    mode = sys.argv[1]

    if mode == "exit":
        return

    if mode == "badlen":
        _write(b"Content-Length: not-a-number\r\n\r\n{}")
        time.sleep(5)
        return

    if mode == "huge":
        _write(b"Content-Length: 99999999\r\n\r\n")
        time.sleep(5)
        return

    if mode == "noheader":
        _write(b"garbage without a content length\r\n\r\n")
        time.sleep(5)
        return

    cancelled: list[int] = []

    while True:
        message = _read_message()
        if message is None:
            return
        method = message.get("method")
        request_id = message.get("id")

        if method == "$/cancelRequest":
            cancelled.append(message["params"]["id"])
            continue

        if request_id is None:
            continue  # a notification we do not answer

        if mode == "silent_log":
            if method == "report":
                _write(_frame({"jsonrpc": "2.0", "id": request_id, "result": {"cancelled": cancelled}}))
            continue

        if mode == "split":
            body = json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}}).encode()
            header = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
            for index in range(0, len(header), 4):
                _write(header[index : index + 4])
                time.sleep(0.01)
            for index in range(0, len(body), 5):
                _write(body[index : index + 5])
                time.sleep(0.01)
            continue

        if mode == "batch2":
            _write(
                _frame({"jsonrpc": "2.0", "method": "window/logMessage", "params": {"m": 1}})
                + _frame({"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}})
            )
            continue

        if mode == "notify":
            payload = b"".join(
                _frame({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"n": i}})
                for i in range(50)
            )
            _write(payload + _frame({"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}}))
            continue

        if mode == "stderr":
            sys.stderr.buffer.write(b"E" * (200 * 1024))
            sys.stderr.buffer.flush()
            _write(_frame({"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}}))
            continue

        if mode == "env":
            _write(
                _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"env_keys": sorted(os.environ)},
                    }
                )
            )
            continue

        if mode == "error":
            _write(
                _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "method not found"},
                    }
                )
            )
            continue

        if mode == "crash_after":
            _write(_frame({"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}}))
            sys.stdout.buffer.close()
            os._exit(3)

        if mode == "silent":
            time.sleep(30)
            continue

        # default: echo
        _write(
            _frame(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"method": method, "params": message.get("params")},
                }
            )
        )


if __name__ == "__main__":
    main()
