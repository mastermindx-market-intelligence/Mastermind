#!/usr/bin/env python3
"""Tiny stdlib-only client for the Executive local-operator socket (L4).

For the Paperclip module worker (L8) to copy. No third-party imports: the
socket itself is the admission (the gateway checks the kernel peer uid of
the connection), so the client sends no token and no special headers.

    python3 local_operator_client.py /path/to/local-operator.sock \
        POST /os/executive/context '{}'

Response body is printed to stdout; the HTTP status line to stderr.
"""
from __future__ import annotations

import json
import socket
import sys


def request(socket_path: str, method: str, path: str, body: str = "") -> tuple[str, bytes]:
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(30.0)
    conn.connect(socket_path)
    try:
        payload = body.encode("utf-8")
        head = (
            f"{method} {path} HTTP/1.0\r\n"
            "Host: mcp.mastermind-x.com\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Content-Type: application/json\r\n\r\n"
        ).encode("ascii")
        conn.sendall(head + payload)
        chunks = []
        while True:
            data = conn.recv(65536)
            if not data:
                break
            chunks.append(data)
    finally:
        conn.close()
    raw = b"".join(chunks)
    status_line, _, response = raw.partition(b"\r\n\r\n")
    return status_line.decode("ascii", "replace"), response


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(__doc__, file=sys.stderr)
        return 2
    socket_path, method, path = argv[1], argv[2].upper(), argv[3]
    body = argv[4] if len(argv) == 4 else "{}"
    status, response = request(socket_path, method, path, body)
    print(status, file=sys.stderr)
    try:
        print(json.dumps(json.loads(response), indent=2, sort_keys=True))
    except ValueError:
        sys.stdout.write(response.decode("utf-8", "replace"))
    return 0 if " 200" in status else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
