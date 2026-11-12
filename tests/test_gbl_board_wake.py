"""GBL-RETURN board-wake handler tests (integrations/gbl/board_wake.py).

The handler is the Grok Bridge agent's ``process`` adapter command.  The
laws proven here, all against fakes — no real board, no real bridge, no
network beyond one ephemeral loopback HTTP fixture for ``_get_json``:

* a wake carries the ASK ID and NOTHING else: the door frame is exactly
  ``{"schema", "op": "return", "arguments": {"ask_id": …}}``;
* it is NEVER an error run: every failure path logs and exits 0;
* the config path is required — the handler never defaults to a root;
* the config pin must equal ``PAPERCLIP_API_URL`` (trailing slash
  stripped) or the handler refuses to act;
* the API key is used and never printed;
* the inbox backstop is bounded and dedupes; unsafe issue segments and
  lookalike tokens never reach a GET path or the bridge.
"""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from common.gbl_contract import (
    decode_gbl_frame,
    encode_gbl_frame,
    mint_ask_id,
)
from integrations.gbl import board_wake

REPO = str(Path(__file__).resolve().parents[1])
PRINCIPAL = "grok-account-main"
ASK_ID = mint_ask_id(PRINCIPAL, "secretary", "gb-ask-0001")
OTHER_ASK_ID = mint_ask_id(PRINCIPAL, "assurance", "gb-ask-0002")
PIN = "http://127.0.0.1:9"          # fixture pin; board reads are faked
API_KEY = "fixture-key-never-printed"
BOUND_SEG = "9f8e7d6c-5b4a-3928-1706-fixture00001"


class BridgeDoor:
    """A real AF_UNIX loopback server speaking the door frame protocol."""

    def __init__(self, path, reply=None):
        self.path = str(path)
        self.requests: list = []
        self.reply = ({"ok": True, "result": {"status": "NOT_YET"}}
                      if reply is None else reply)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(path))
        self._sock.listen(8)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(10.0)
                buffer = b""
                try:
                    while not buffer.endswith(b"\n"):
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        buffer += chunk
                except (socket.timeout, OSError):
                    pass
                self.requests.append(
                    decode_gbl_frame(buffer) if buffer.strip() else None)
                try:
                    conn.sendall(encode_gbl_frame(self.reply))
                except OSError:
                    pass

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


class FakeBoard:
    """Stands in for board_wake._get_json; records every requested path."""

    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.gets: list[str] = []

    def __call__(self, pin, api_key, path):
        assert pin == PIN
        assert api_key == API_KEY          # used for the Bearer header only
        self.gets.append(path)
        return self.rows.get(path)


def write_config(tmp_path, socket_path, *, repo=REPO, pin=PIN,
                 extra=None):
    config = {"repo": repo, "bridge_socket": str(socket_path),
              "paperclip_base": pin}
    config.update(extra or {})
    path = tmp_path / "board_wake.json"
    path.write_text(json.dumps(config))
    return str(path)


def set_env(monkeypatch, *, url=PIN, issue=None, drop=()):
    values = {"PAPERCLIP_API_URL": url, "PAPERCLIP_API_KEY": API_KEY,
              "PAPERCLIP_RUN_ID": "run-fixture",
              "PAPERCLIP_AGENT_ID": "agent-fixture",
              "PAPERCLIP_COMPANY_ID": "company-fixture"}
    if issue is not None:
        values["PAPERCLIP_ISSUE_ID"] = issue
    for name in list(values) + ["PAPERCLIP_ISSUE_ID"]:
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        if name not in drop:
            monkeypatch.setenv(name, value)


def run_main(monkeypatch, tmp_path, *, board=None, door=None, config=None,
             url=PIN, issue=None, drop=()):
    set_env(monkeypatch, url=url, issue=issue, drop=drop)
    if board is not None:
        monkeypatch.setattr(board_wake, "_get_json", board)
    socket_path = (door.path if door is not None
                   else str(tmp_path / "absent.sock"))
    argv = ["board_wake.py",
            config or write_config(tmp_path, socket_path)]
    return board_wake.main(argv)


def bound_row(title):
    return {"/api/issues/" + BOUND_SEG: {"id": BOUND_SEG, "title": title},
            "/api/agents/me/inbox-lite": {"issues": []}}


def ask_title(ask_id):
    return f"GBL ask record [gbl-ask-v1] [{ask_id}]"


# ── Never an error run; never a defaulted root ──────────────────────────────


class TestHarmlessExits:
    def test_missing_config_argument_exits_zero(self, capsys):
        assert board_wake.main(["board_wake.py"]) == 0
        assert "required" in capsys.readouterr().out

    def test_unreadable_config_exits_zero(self):
        assert board_wake.main(["board_wake.py", "/nonexistent/cfg.json"]) == 0

    def test_non_object_config_exits_zero(self, tmp_path):
        path = tmp_path / "cfg.json"
        path.write_text("[1, 2]")
        assert board_wake.main(["board_wake.py", str(path)]) == 0

    def test_repo_without_the_contract_exits_zero(self, monkeypatch, tmp_path):
        door_path = tmp_path / "bridge.sock"
        config = write_config(tmp_path, door_path, repo=str(tmp_path))
        assert run_main(monkeypatch, tmp_path, config=config) == 0

    def test_relative_socket_path_exits_zero(self, monkeypatch, tmp_path):
        config = write_config(tmp_path, "relative.sock")
        assert run_main(monkeypatch, tmp_path, config=config) == 0

    def test_non_http_pin_exits_zero(self, monkeypatch, tmp_path):
        config = write_config(tmp_path, tmp_path / "b.sock",
                              pin="https://example.invalid")
        assert run_main(monkeypatch, tmp_path, config=config) == 0

    def test_missing_env_var_exits_zero_without_any_read(
            self, monkeypatch, tmp_path):
        board = FakeBoard()
        assert run_main(monkeypatch, tmp_path, board=board,
                        drop=("PAPERCLIP_COMPANY_ID",)) == 0
        assert board.gets == []

    def test_pin_mismatch_refuses_to_act(self, monkeypatch, tmp_path, capsys):
        # a trailing slash on the wake URL still matches the pin: it acts
        board = FakeBoard(bound_row(ask_title(ASK_ID)))
        assert run_main(monkeypatch, tmp_path, board=board,
                        url=PIN + "/") == 0
        assert board.gets == ["/api/agents/me/inbox-lite"]
        # a genuinely different board is refused before ANY read
        board2 = FakeBoard(bound_row(ask_title(ASK_ID)))
        assert run_main(monkeypatch, tmp_path, board=board2,
                        url="http://127.0.0.1:8") == 0
        assert board2.gets == []
        assert "mismatched board" in capsys.readouterr().out

    def test_api_key_never_reaches_the_log(self, monkeypatch, tmp_path,
                                           capsys):
        board = FakeBoard(bound_row(ask_title(ASK_ID)))
        run_main(monkeypatch, tmp_path, board=board)
        assert API_KEY not in capsys.readouterr().out

    def test_bridge_socket_down_logs_and_exits_zero(self, monkeypatch,
                                                    tmp_path, capsys):
        board = FakeBoard(bound_row(ask_title(ASK_ID)))
        assert run_main(monkeypatch, tmp_path, board=board,
                        issue=BOUND_SEG) == 0            # no door listening
        assert "return_scan will recover" in capsys.readouterr().out


# ── The wake carries the ask id and nothing else ────────────────────────────


class TestReturnOp:
    def test_bound_issue_token_sends_exactly_one_return_op(
            self, monkeypatch, tmp_path):
        door = BridgeDoor(tmp_path / "bridge.sock")
        try:
            board = FakeBoard(bound_row(ask_title(ASK_ID)))
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door, issue=BOUND_SEG) == 0
            assert len(door.requests) == 1
            request = door.requests[0]
            assert request["schema"] == "mastermind.gbl.request.v1"
            assert request["op"] == "return"
            # the ask id and NOTHING else — no answer, no child id, no text
            assert request["arguments"] == {"ask_id": ASK_ID}
        finally:
            door.close()

    def test_no_token_anywhere_is_a_harmless_noop(self, monkeypatch,
                                                  tmp_path, capsys):
        door = BridgeDoor(tmp_path / "bridge.sock")
        try:
            board = FakeBoard({
                "/api/issues/" + BOUND_SEG: {"title": "An ordinary issue"},
                "/api/agents/me/inbox-lite": {
                    "issues": [{"id": "row-1", "title": "Another issue"}]},
            })
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door, issue=BOUND_SEG) == 0
            assert door.requests == []
            assert "harmless no-op" in capsys.readouterr().out
        finally:
            door.close()

    def test_inbox_backstop_recovers_a_lost_wake(self, monkeypatch, tmp_path):
        door = BridgeDoor(tmp_path / "bridge.sock")
        try:
            board = FakeBoard({
                "/api/agents/me/inbox-lite": {
                    "issues": [{"id": "row-1",
                                "title": ask_title(OTHER_ASK_ID)}]},
            })
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door) == 0
            assert [r["arguments"]["ask_id"] for r in door.requests] == \
                [OTHER_ASK_ID]
        finally:
            door.close()

    def test_projection_without_title_costs_one_full_read(
            self, monkeypatch, tmp_path):
        door = BridgeDoor(tmp_path / "bridge.sock")
        try:
            board = FakeBoard({
                "/api/agents/me/inbox-lite": {"issues": [{"id": "row-9"}]},
                "/api/issues/row-9": {"title": ask_title(ASK_ID)},
            })
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door) == 0
            assert "/api/issues/row-9" in board.gets
            assert [r["arguments"]["ask_id"] for r in door.requests] == \
                [ASK_ID]
        finally:
            door.close()

    def test_same_token_on_both_sources_dedupes_to_one_call(
            self, monkeypatch, tmp_path):
        door = BridgeDoor(tmp_path / "bridge.sock")
        try:
            board = FakeBoard({
                "/api/issues/" + BOUND_SEG: {"title": ask_title(ASK_ID)},
                "/api/agents/me/inbox-lite": {
                    "issues": [{"id": "row-1", "title": ask_title(ASK_ID)}]},
            })
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door, issue=BOUND_SEG) == 0
            assert len(door.requests) == 1
        finally:
            door.close()

    def test_two_distinct_tokens_call_the_door_twice_in_order(
            self, monkeypatch, tmp_path):
        door = BridgeDoor(tmp_path / "bridge.sock")
        try:
            board = FakeBoard({
                "/api/issues/" + BOUND_SEG: {
                    "title": f"asks [{ASK_ID}] and [{OTHER_ASK_ID}]"},
                "/api/agents/me/inbox-lite": {"issues": []},
            })
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door, issue=BOUND_SEG) == 0
            assert [r["arguments"]["ask_id"] for r in door.requests] == \
                [ASK_ID, OTHER_ASK_ID]
        finally:
            door.close()

    def test_refusal_reply_is_logged_not_fatal(self, monkeypatch, tmp_path,
                                               capsys):
        door = BridgeDoor(tmp_path / "bridge.sock",
                          reply={"ok": False,
                                 "error": {"code": "ASK_NOT_FOUND"}})
        try:
            board = FakeBoard(bound_row(ask_title(ASK_ID)))
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door, issue=BOUND_SEG) == 0
            assert "ASK_NOT_FOUND" in capsys.readouterr().out
        finally:
            door.close()


# ── Input hardening: unsafe segments, lookalikes, bounds ────────────────────


class TestHardening:
    def test_unsafe_bound_segment_never_reaches_a_get(
            self, monkeypatch, tmp_path):
        board = FakeBoard(bound_row(ask_title(ASK_ID)))
        assert run_main(monkeypatch, tmp_path, board=board,
                        issue="../../etc/passwd") == 0
        assert board.gets == ["/api/agents/me/inbox-lite"]

    def test_lookalike_tokens_are_ignored(self, monkeypatch, tmp_path):
        door = BridgeDoor(tmp_path / "bridge.sock")
        try:
            title = ("[gb-" + "a" * 31 + "] [gb-" + "Z" * 32 + "] "
                     "[gb-" + "b" * 33 + "] gb-" + "c" * 32)
            board = FakeBoard(bound_row(title))
            assert run_main(monkeypatch, tmp_path, board=board,
                            door=door, issue=BOUND_SEG) == 0
            assert door.requests == []
        finally:
            door.close()

    def test_inbox_scan_is_capped_at_ten_rows(self, monkeypatch, tmp_path):
        rows = [{"id": f"row-{i}"} for i in range(15)]    # no titles
        board = FakeBoard({"/api/agents/me/inbox-lite": {"issues": rows}})
        for i in range(15):
            board.rows[f"/api/issues/row-{i}"] = {"title": "no token here"}
        assert run_main(monkeypatch, tmp_path, board=board) == 0
        full_reads = [p for p in board.gets if p.startswith("/api/issues/")]
        assert len(full_reads) == board_wake.INBOX_SCAN_MAX_ROWS == 10

    def test_unparseable_board_rows_are_skipped(self, monkeypatch, tmp_path):
        board = FakeBoard({"/api/issues/" + BOUND_SEG: None,
                           "/api/agents/me/inbox-lite": "junk"})
        assert run_main(monkeypatch, tmp_path, board=board,
                        issue=BOUND_SEG) == 0


# ── _get_json itself, against one ephemeral loopback HTTP fixture ───────────


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            body = b'{"title": "fixture row"}'
            self.send_response(200)
        elif self.path == "/junk":
            body = b"not json at all"
            self.send_response(200)
        else:
            body = b'{"error": "nope"}'
            self.send_response(500)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestGetJson:
    @pytest.fixture()
    def server(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()
        httpd.server_close()

    def test_ok_row_is_parsed(self, server):
        assert board_wake._get_json(server, "k", "/ok") == \
            {"title": "fixture row"}

    def test_error_status_is_none(self, server):
        assert board_wake._get_json(server, "k", "/missing") is None

    def test_unparseable_body_is_none(self, server):
        assert board_wake._get_json(server, "k", "/junk") is None

    def test_unreachable_board_is_none(self):
        # ephemeral port 1 on loopback: connection refused, logged, None
        assert board_wake._get_json("http://127.0.0.1:9", "k", "/ok") is None
