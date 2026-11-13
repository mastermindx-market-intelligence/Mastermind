#!/usr/bin/env python3
"""GBL-RETURN: the Grok Bridge agent's board-wake handler (SHIPPED).

This script is the ``process`` adapter command of the Grok Bridge agent on
the Paperclip board.  The board runs it when the agent is woken — an ask
record assigned to the bridge, or (the return edge) the ask record's
``issue_blockers_resolved`` wake when the dispatched child is marked done.

The law it obeys:

* A wake carries the ASK ID and nothing else.  This handler extracts the
  ``[gb-<32hex>]`` token from issue titles and sends the bridge
  ``{"op": "return", "arguments": {"ask_id": …}}`` over the loopback AF_UNIX
  door — never an answer, never a child id, never waker-supplied text.  The
  answer is taken by the bridge from its OWN board read behind that door
  (:meth:`GblBridge.return_delegate`).
* It is NEVER an error run.  Every failure — missing config, mismatched
  pin, unreadable board row, unreachable bridge — is logged and the process
  exits 0.  A lost or failed wake is recovered by the bridge's own bounded
  read (``return_scan``), not by the board re-running an adapter that
  failed.  An ask-record issue assigned to the bridge with nothing to do
  (a question ask) is the harmless ``NOT_A_DELEGATE`` no-op.
* The config path is a REQUIRED argument.  The script never defaults to a
  real root when the argument is missing (that default would be a finding);
  it logs and exits.
* The config's ``paperclip_base`` pin must equal the wake environment's
  ``PAPERCLIP_API_URL`` (trailing slash stripped) — the same pin law the RF
  carrier enforces — or the handler refuses to act on a mismatched board.
* GET-only against the board; the API key is used for the Bearer header and
  is never printed, logged or echoed.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

# The ask token is exact by construction (``gb-`` + 32 hex, contract shape),
# so a closing bracket can never belong to a longer id.
ASK_TOKEN_RE = re.compile(r"\[(gb-[0-9a-f]{32})\]")
# Only a board-safe segment is ever interpolated into a GET path.
SEGMENT_RE = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")

INBOX_SCAN_MAX_ROWS = 10          # the bounded lost-wake backstop read
HTTP_TIMEOUT_SECONDS = 15.0
REPLY_TIMEOUT_SECONDS = 30.0
RESPONSE_MAX_BYTES = 4 * 1024 * 1024

REQUIRED_ENV = ("PAPERCLIP_API_URL", "PAPERCLIP_API_KEY", "PAPERCLIP_RUN_ID",
                "PAPERCLIP_AGENT_ID", "PAPERCLIP_COMPANY_ID")


def log(message: str) -> None:
    print(f"[board-wake] {message}", flush=True)


def _get_json(pin: str, api_key: str, path: str):
    """One GET against the pinned board, or None (logged) on any failure.
    No redirects are followed (http.client never does); an oversized or
    unparseable body is a skipped read, never a crash.  R1 item 4: the pin
    is parsed INSIDE the try — a corrupt installer pin (e.g. an
    unterminated IPv6 literal) is a logged, skipped read like every other
    failure, never a raw ValueError that would exit non-zero and break the
    "never an error run" law."""
    try:
        parts = urlsplit(pin)
        connection = http.client.HTTPConnection(
            parts.hostname, parts.port, timeout=HTTP_TIMEOUT_SECONDS)
        try:
            connection.request(
                "GET", path,
                headers={"authorization": f"Bearer {api_key}",
                         "accept": "application/json"})
            response = connection.getresponse()
            body = response.read(RESPONSE_MAX_BYTES + 1)
            status = response.status
        finally:
            connection.close()
        if status != 200 or len(body) > RESPONSE_MAX_BYTES:
            log(f"GET {path} -> HTTP {status}; row skipped")
            return None
        parsed = json.loads(body)
        return parsed if isinstance(parsed, (dict, list)) else None
    except (OSError, ValueError) as exc:
        log(f"GET {path} failed ({type(exc).__name__}); row skipped")
        return None


def _ask_ids_in(title, ask_id_re) -> list[str]:
    if not isinstance(title, str):
        return []
    return [token for token in ASK_TOKEN_RE.findall(title)
            if ask_id_re.fullmatch(token)]


def _call_bridge(socket_path: str, ask_id: str,
                 encode_frame, decode_frame) -> None:
    """Send the one return op for this ask id and log the bridge's verdict.
    The wake is attention only: whatever happens here — refusal, no reply,
    a down bridge — is logged and left to return_scan recovery."""
    request = {"schema": "mastermind.gbl.request.v1", "op": "return",
               "arguments": {"ask_id": ask_id}}
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(REPLY_TIMEOUT_SECONDS)
    buffer = b""
    try:
        try:
            client.connect(socket_path)
            client.sendall(encode_frame(request))
            while not buffer.endswith(b"\n"):
                chunk = client.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > RESPONSE_MAX_BYTES:
                    raise ValueError("oversized reply frame")
        finally:
            client.close()
        if not buffer.strip():
            log(f"{ask_id}: no reply frame from the bridge; "
                "return_scan will recover")
            return
        reply = decode_frame(buffer)
        if reply.get("ok") is True:
            result = reply.get("result")
            status = result.get("status") if isinstance(result, dict) else None
            log(f"{ask_id}: bridge result {status}")
        else:
            error = reply.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            log(f"{ask_id}: bridge refusal {code}")
    except (OSError, ValueError, socket.timeout) as exc:
        log(f"{ask_id}: bridge call failed ({type(exc).__name__}); "
            "return_scan will recover")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        log("config path argument is required; this handler never defaults "
            "to a root — nothing to do")
        return 0
    try:
        config = json.loads(Path(argv[1]).read_text())
    except (OSError, ValueError) as exc:
        log(f"config unreadable ({type(exc).__name__}); nothing to do")
        return 0
    if not isinstance(config, dict):
        log("config must be a JSON object; nothing to do")
        return 0
    repo = config.get("repo")
    socket_path = config.get("bridge_socket")
    pin = config.get("paperclip_base")
    if not (isinstance(repo, str) and repo.startswith("/")
            and Path(repo, "common", "gbl_contract.py").is_file()):
        log("config.repo must be an absolute checkout carrying "
            "common/gbl_contract.py; nothing to do")
        return 0
    if not isinstance(socket_path, str) or not socket_path.startswith("/"):
        log("config.bridge_socket must be an absolute path; nothing to do")
        return 0
    if not isinstance(pin, str) or not pin.startswith("http://"):
        log("config.paperclip_base must be an http:// pin; nothing to do")
        return 0
    for name in REQUIRED_ENV:
        if not os.environ.get(name):
            log(f"{name} is missing from the wake environment; nothing to do")
            return 0
    api_url = os.environ["PAPERCLIP_API_URL"]
    api_key = os.environ["PAPERCLIP_API_KEY"]
    if pin != api_url.rstrip("/"):
        log("config pin does not match the wake's PAPERCLIP_API_URL; "
            "refusing to act on a mismatched board")
        return 0

    sys.path.insert(0, repo)
    try:
        from common.gbl_contract import (
            ASK_ID_RE, decode_gbl_frame, encode_gbl_frame)
    except Exception as exc:                       # noqa: BLE001 - log & exit 0
        log(f"contract import failed ({type(exc).__name__}); nothing to do")
        return 0

    ask_ids: list[str] = []

    def collect(title) -> None:
        for token in _ask_ids_in(title, ASK_ID_RE):
            if token not in ask_ids:
                ask_ids.append(token)

    # The wake-bound issue first: an ask record assigned to the bridge, or
    # the blockers-resolved wake on the ask record when its child finished.
    bound = os.environ.get("PAPERCLIP_ISSUE_ID", "")
    if SEGMENT_RE.fullmatch(bound):
        row = _get_json(pin, api_key, f"/api/issues/{bound}")
        if isinstance(row, dict):
            collect(row.get("title"))
    elif bound:
        log("PAPERCLIP_ISSUE_ID is not a board-safe segment; skipped")

    # The bounded inbox backstop: a lost wake still shows as an open
    # assigned row.  inbox-lite serves todo/in_progress/blocked rows; a
    # projection without a usable title costs one full read per row,
    # capped at INBOX_SCAN_MAX_ROWS rows.
    inbox = _get_json(pin, api_key, "/api/agents/me/inbox-lite")
    rows = inbox
    if isinstance(inbox, dict):
        rows = next((inbox[key] for key in ("issues", "rows", "items")
                     if isinstance(inbox.get(key), list)), None)
    if isinstance(rows, list):
        for row in rows[:INBOX_SCAN_MAX_ROWS]:
            if not isinstance(row, dict):
                continue
            title = row.get("title")
            if not isinstance(title, str) or not title:
                issue_id = row.get("id")
                if isinstance(issue_id, str) and SEGMENT_RE.fullmatch(issue_id):
                    full = _get_json(pin, api_key, f"/api/issues/{issue_id}")
                    if isinstance(full, dict):
                        title = full.get("title")
            collect(title)

    if not ask_ids:
        log("no ask token on the bound issue or in the bounded inbox; "
            "harmless no-op")
        return 0
    for ask_id in ask_ids:
        _call_bridge(socket_path, ask_id, encode_gbl_frame, decode_gbl_frame)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
