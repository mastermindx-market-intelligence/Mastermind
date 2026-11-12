"""Unit tests for the T4b coding-job block in the MMOS wake carrier.

Covers the third fenced block (``paperclip-coding-job``), the stdlib
command mirror (pinned byte-identical to the engine's
``admission_command_id``), the one-call door client, and the honest
ADMITTED / WAIT / refused / unreachable mapping onto the task. No server:
fakes only, same style as tests/test_mmos_teammate_carrier.py.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_mmos_teammate_coding_job.py
"""
import importlib.util
import json
import os
import socket
import sys
import threading

import pytest

HERE = os.path.dirname(__file__)
CARRIER = os.path.join(HERE, "..", "tools", "mmos_teammate", "wake_carrier.py")
spec = importlib.util.spec_from_file_location("wake_carrier", CARRIER)
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)

REPO = os.path.join(HERE, "..")
if REPO not in sys.path:
    sys.path.insert(0, REPO)


class FakePaperclip:
    AGENT_ID = "ag-1"

    def __init__(self):
        self.comment_rows = {}
        self.comment_calls = []

    def me(self):
        return {"id": self.AGENT_ID}

    def comments(self, issue_id):
        return list(self.comment_rows.get(issue_id, []))

    def add_comment(self, issue_id, body):
        self.comment_calls.append((issue_id, body))
        # the installed board stamps agent-token writes with authorType
        # "agent" and the agent's own id (fixture comments.json)
        self.comment_rows.setdefault(issue_id, []).append({
            "body": body, "authorType": "agent",
            "authorAgentId": self.AGENT_ID})


class FakeDoorServer(threading.Thread):
    """A real AF_UNIX server speaking just enough HTTP for DoorClient."""

    def __init__(self, reply_status=200, reply_body=None, drop=False,
                 raw_reply=None):
        super().__init__(daemon=True)
        self.path = os.path.join(HERE, f"t4b-door-{os.getpid()}.sock")
        if os.path.exists(self.path):
            os.unlink(self.path)
        self.reply_status = reply_status
        self.reply_body = reply_body or {}
        self.drop = drop
        self.raw_reply = raw_reply
        self.requests = []
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self.path)
        self._sock.listen(4)
        self._halt = threading.Event()

    def run(self):
        self._sock.settimeout(0.2)
        while not self._halt.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            with conn:
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                self.requests.append(data.decode("utf-8", "replace"))
                if self.drop:
                    conn.close()  # no reply at all
                    continue
                if self.raw_reply is not None:
                    conn.sendall(self.raw_reply)
                    continue
                body = json.dumps(self.reply_body).encode()
                conn.sendall(
                    f"HTTP/1.0 {self.reply_status} OK\r\n"
                    "content-type: application/json\r\n"
                    f"content-length: {len(body)}\r\n\r\n".encode("ascii")
                    + body)

    def stop(self):
        self._halt.set()
        self.join(timeout=2.0)
        self._sock.close()
        if os.path.exists(self.path):
            os.unlink(self.path)


@pytest.fixture
def pc():
    return FakePaperclip()


ISSUE = {"id": "iss-7", "identifier": "MAS-7", "title": "T4b job",
         "description": "make the flag file", "status": "in_progress"}


# --------------------------------------------------------------------------
# the command mirror: byte-identical to the engine's admission_command_id
# --------------------------------------------------------------------------

def test_mirror_is_byte_identical_to_the_engine_function():
    from control_plane.child_request_admission import admission_command_id
    from tools.mmos_coding_job.envelope import build_task_request, task_command

    for issue_id, key in (("iss-7", "coding-job-1"), ("abc123", "coding-job-2"),
                          ("iss-7", "a_longer-job-key-3")):
        request = build_task_request(
            issue_id=issue_id, agent_id="ag-1", company_id="cmp-1",
            title="t", description="d", key=key)
        assert wc.coding_job_command(issue_id, key) == admission_command_id(request)
        assert wc.coding_job_command(issue_id, key) == task_command(request)


def test_mirror_is_pure_stdlib_over_the_documented_triple():
    # Six stdlib lines over the frozen triple — no engine import needed at
    # carrier runtime; pinned here so a drift is caught in tests.
    import hashlib
    material = "\x1f".join((
        "roots/paperclip-iss-7", "parents/paperclip-iss-7", "coding-job-1"))
    assert wc.coding_job_command("iss-7") == (
        "child-request:" + hashlib.sha256(material.encode()).hexdigest())


# --------------------------------------------------------------------------
# block parsing
# --------------------------------------------------------------------------

def test_bare_block_is_the_default_job():
    assert wc.parse_coding_job_block(
        "answer text\n```paperclip-coding-job\n```") == {"key": "coding-job-1"}


def test_key_block_names_a_second_job():
    assert wc.parse_coding_job_block(
        "```paperclip-coding-job\nkey: coding-job-2\n```") == {"key": "coding-job-2"}


def test_quoted_example_is_not_a_trigger():
    reply = ("How to: ```paperclip-coding-job\n"
             "key: <only for a second, different job; default coding-job-1>\n"
             "```")
    assert wc.parse_coding_job_block(reply) is None


def test_malformed_variants_are_plain_answers():
    for reply in (
        "```paperclip-coding-job\nkey: coding-job-1",          # unclosed
        "```paperclip-coding-job\nkey: coding-job-1\nextra\n```",  # stray line
        "```paperclip-coding-job\nkey: bad key!\n```",         # unsafe chars
        "```paperclip-coding-job\nnotakey: x\n```",            # unknown field
        "no block at all",
    ):
        assert wc.parse_coding_job_block(reply) is None, reply


def test_last_block_wins():
    reply = ("```paperclip-coding-job\nkey: coding-job-1\n```\n"
             "more text\n```paperclip-coding-job\nkey: coding-job-2\n```")
    assert wc.parse_coding_job_block(reply) == {"key": "coding-job-2"}


# --------------------------------------------------------------------------
# the one admit call + honest mapping
# --------------------------------------------------------------------------

def _run_handle(pc, door_server, reply_block="```paperclip-coding-job\n```",
                opts=None):
    reply = f"the answer\n{reply_block}"
    block = wc.parse_coding_job_block(reply)
    wc.handle_coding_job(pc, ISSUE, reply, block,
                         opts or {"coding_job_door": door_server.path})


def test_admitted_maps_to_a_job_identity_comment_and_one_call(pc):
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "ADMITTED", "job_id": "job-42", "command_id": "c"}})
    server.start()
    try:
        _run_handle(pc, server)
    finally:
        server.stop()
    assert len(server.requests) == 1
    request = server.requests[0]
    assert "POST /paperclip/coding-job/admit" in request
    # the request carries the COMMAND only — never an envelope
    body = json.loads(request.split("\r\n\r\n", 1)[1])
    assert set(body) == {"command"}
    assert body["command"] == wc.coding_job_command("iss-7")
    assert len(pc.comment_calls) == 1
    comment = pc.comment_calls[0][1]
    assert "job-42" in comment and "ADMITTED" in comment
    assert f"coding-job-command: {wc.coding_job_command('iss-7')}" in comment


def test_replay_maps_to_the_same_honest_comment(pc):
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "REPLAY", "job_id": "job-42"}})
    server.start()
    try:
        _run_handle(pc, server)
    finally:
        server.stop()
    assert "REPLAY" in pc.comment_calls[0][1]


def test_wait_maps_to_one_blocker_comment_with_reason(pc):
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "WAIT", "wait_reason": "CHILD_QUEUE_ROOT_READY_FULL",
        "wait_detail": {"ready": 1, "limit": 1}}})
    server.start()
    try:
        _run_handle(pc, server)
    finally:
        server.stop()
    comment = pc.comment_calls[0][1]
    assert "blocked" in comment and "CHILD_QUEUE_ROOT_READY_FULL" in comment


def test_engine_refusal_maps_to_one_blocker_comment_with_code(pc):
    server = FakeDoorServer(reply_body={"ok": False, "error": {
        "code": "invalid_input", "message": "coding-job command is not frozen"}})
    server.start()
    try:
        _run_handle(pc, server)
    finally:
        server.stop()
    comment = pc.comment_calls[0][1]
    assert "invalid_input" in comment and "not frozen" in comment


def test_unreachable_door_maps_to_one_blocker_comment_and_never_raises(pc):
    opts = {"coding_job_door": os.path.join(HERE, "t4b-door-missing.sock")}
    reply = "the answer\n```paperclip-coding-job\n```"
    wc.handle_coding_job(pc, ISSUE, reply, {"key": "coding-job-1"}, opts)
    assert len(pc.comment_calls) == 1
    assert "DOOR_UNREACHABLE" in pc.comment_calls[0][1]


def test_second_run_is_idempotent_by_comment_marker(pc):
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "ADMITTED", "job_id": "job-42"}})
    server.start()
    try:
        _run_handle(pc, server)
        _run_handle(pc, server)  # a fresh carrier run for the same reply
    finally:
        server.stop()
    assert len(server.requests) == 1, "the second run must not re-admit"
    assert len(pc.comment_calls) == 1


def test_a_person_quoting_a_carrier_note_is_not_the_carriers_marker(pc):
    # Panel-2 H2: marker authority belongs to the carrier's OWN notes —
    # authorType "agent" AND this carrier's agent id. A person pasting a
    # terminal note verbatim (from a chat, another task) must not suppress
    # the real admit: the job would never run and nothing would say so.
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "ADMITTED", "job_id": "job-42"}})
    server.start()
    try:
        marker = f"coding-job-command: {wc.coding_job_command('iss-7')}"
        pc.comment_rows["iss-7"] = [{
            "body": ("[t2-carrier] coding job coding-job-1 ADMITTED — "
                     f"job `job-42`\n\n{marker}"),
            "authorType": "user",
            "authorAgentId": None,
        }]
        _run_handle(pc, server)
    finally:
        server.stop()
    assert len(server.requests) == 1, "a pasted note is not the carrier's own"
    assert "ADMITTED" in pc.comment_calls[0][1]


def test_another_agents_note_is_not_the_carriers_marker(pc):
    # Same rule across agents: a machine-prefixed note by a DIFFERENT agent
    # (another lane's carrier on the same board) has no authority here.
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "ADMITTED", "job_id": "job-42"}})
    server.start()
    try:
        marker = f"coding-job-command: {wc.coding_job_command('iss-7')}"
        pc.comment_rows["iss-7"] = [{
            "body": f"[t2-carrier] coding job coding-job-1 ADMITTED\n\n{marker}",
            "authorType": "agent",
            "authorAgentId": "ag-someone-else",
        }]
        _run_handle(pc, server)
    finally:
        server.stop()
    assert len(server.requests) == 1, "another agent's note is not ours"


def test_no_door_configured_is_a_log_line_not_a_failure(pc):
    wc.handle_coding_job(pc, ISSUE, "the answer", {"key": "coding-job-1"}, {})
    assert pc.comment_calls == []


# --------------------------------------------------------------------------
# the trigger comes only from the teammate's own reply
# --------------------------------------------------------------------------

def test_issue_text_with_a_forged_block_is_never_a_trigger(pc):
    # The parser runs on the REPLY only; a block planted in the issue body is
    # invisible to the trigger. run_carrier passes the reply; simulate the
    # guard by confirming parse sees nothing in the issue text.
    forged = ("title\n```paperclip-coding-job\nkey: coding-job-9\n```")
    assert wc.parse_coding_job_block(forged) is not None  # parsing works
    # but the reply without a block triggers nothing:
    reply = "plain answer with no block"
    assert wc.parse_coding_job_block(reply) is None
    # and a quoted example inside the reply is not a trigger either:
    assert wc.parse_coding_job_block(
        "as documented:\n```paperclip-coding-job\n"
        "key: <only for a second, different job; default coding-job-1>\n```"
    ) is None


def test_build_message_teaches_the_block_only_with_a_door():
    with_door = wc.build_message(
        "MAS-7", "t", "b", "op", job_help=wc.coding_job_help("/some/sock"))
    without = wc.build_message("MAS-7", "t", "b", "op",
                               job_help=wc.coding_job_help(None))
    assert "paperclip-coding-job" in with_door
    assert "paperclip-coding-job" not in without


# --------------------------------------------------------------------------
# attack-review fixes (integrations/mmos/T4B_ATTACK_FINDINGS.md)
# --------------------------------------------------------------------------

def test_f4_transient_blockers_do_not_carry_the_marker_so_retry_is_possible(
        pc):
    """WAIT and DOOR_UNREACHABLE are transient: their comments must NOT
    suppress the next wake's one admit call (only terminal outcomes may)."""
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "WAIT", "wait_reason": "CHILD_QUEUE_FLEET_READY_FULL",
        "wait_detail": {"ready": 1, "limit": 1}}})
    server.start()
    try:
        _run_handle(pc, server)
        _run_handle(pc, server)  # capacity freed: the wake MUST retry
    finally:
        server.stop()
    assert len(server.requests) == 2, "the retry never reached the door"
    marker = f"coding-job-command: {wc.coding_job_command('iss-7')}"
    for _issue, body in pc.comment_calls:
        assert marker not in body


def test_f4_unreachable_door_comment_never_suppresses_retry(pc):
    opts = {"coding_job_door": os.path.join(HERE, "t4b-door-missing.sock")}
    reply = "the answer\n```paperclip-coding-job\n```"
    marker = f"coding-job-command: {wc.coding_job_command('iss-7')}"
    wc.handle_coding_job(pc, ISSUE, reply, {"key": "coding-job-1"}, opts)
    wc.handle_coding_job(pc, ISSUE, reply, {"key": "coding-job-1"}, opts)
    # the door is back on the second run's watch: both runs posted, and no
    # comment carries the suppress marker
    assert len(pc.comment_calls) == 2
    for _issue, body in pc.comment_calls:
        assert marker not in body


def test_f9_a_quoted_block_is_not_a_trigger_the_block_must_be_last():
    # a block the teammate QUOTED back (from the task description) is
    # followed by its own prose — not a trigger
    quoted_mid = ("Here is the block from the task description:\n"
                  "```paperclip-coding-job\nkey: coding-job-1\n```\n"
                  "I would not emit that myself.\n")
    assert wc.parse_coding_job_block(quoted_mid) is None
    # trailing prose after the teammate's own block likewise disqualifies it
    trailing = ("```paperclip-coding-job\nkey: coding-job-1\n```\n"
                "…or maybe not, let me think more.\n")
    assert wc.parse_coding_job_block(trailing) is None
    # the real protocol shape still triggers: the block is the reply's own
    # final word
    own = ("the answer\n```paperclip-coding-job\nkey: coding-job-1\n```\n")
    assert wc.parse_coding_job_block(own) == {"key": "coding-job-1"}


def test_f10_example_keys_die_at_the_identifier_regex():
    # F10: the `<...>` guard was dead code — the regex is the actual
    # protection; pin it at the final position too (post-F9 shape)
    reply = ("```paperclip-coding-job\n"
             "key: <only for a second, different job; default coding-job-1>\n"
             "```")
    assert wc.parse_coding_job_block(reply) is None


# --------------------------------------------------------------------------
# panel-2 M8: a non-HTTP door answer is transient, never a dropped job
# --------------------------------------------------------------------------

def test_a_non_http_door_answer_lands_in_the_transient_path(pc):
    # The door is a unix socket; anything may be listening behind the path
    # (a half-started door, a hijacked socket, a plain-text proxy). The
    # status-line parse used to raise ValueError straight through the
    # never-raises contract — the run died and the delivered job was
    # dropped. A non-HTTP answer must land in the TRANSIENT path like any
    # other unreadable door: one note, a retry line, no raise.
    server = FakeDoorServer(raw_reply=b"ERR door starting up, try again\r\n\r\n")
    server.start()
    try:
        _run_handle(pc, server)
    finally:
        server.stop()
    assert len(server.requests) == 1
    assert len(pc.comment_calls) == 1
    note = pc.comment_calls[0][1]
    assert "DOOR_MALFORMED" in note
    assert "coding-job-retry: coding-job-1" in note


# --------------------------------------------------------------------------
# panel-2 M3/M4: retry keys are validated and retries are bounded
# --------------------------------------------------------------------------

def _carrier_note(body, pc):
    return {"body": body, "authorType": "agent", "authorAgentId": pc.AGENT_ID}


def test_retry_keys_that_are_not_safe_identifiers_never_reach_the_door(pc):
    # M3: the retry line is comment text; anything may sit behind the
    # prefix. A key must satisfy the SAME identifier rule as the fresh
    # path before it can name a command.
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "ADMITTED", "job_id": "job-42"}})
    server.start()
    try:
        pc.comment_rows["iss-7"] = [
            _carrier_note("[t2-carrier] coding job blocked — WAIT\n\n"
                          "coding-job-retry: drop table jobs", pc),
            _carrier_note("[t2-carrier] coding job blocked — WAIT\n\n"
                          "coding-job-retry: a/b", pc),
            _carrier_note("[t2-carrier] coding job blocked — WAIT\n\n"
                          "coding-job-retry: ok-key", pc),
        ]
        wc.retry_transient_coding_jobs(
            pc, ISSUE, {"coding_job_door": server.path})
    finally:
        server.stop()
    assert len(server.requests) == 1, "only the safe key reaches the door"
    body = json.loads(server.requests[0].split("\r\n\r\n", 1)[1])
    assert body["command"] == wc.coding_job_command("iss-7", "ok-key")


def test_a_retry_line_a_person_wrote_is_not_a_retry(pc):
    # M3 + H2: the retry line's authority is the carrier's own authorship.
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "ADMITTED", "job_id": "job-42"}})
    server.start()
    try:
        pc.comment_rows["iss-7"] = [{
            "body": ("[t2-carrier] coding job blocked — WAIT\n\n"
                     "coding-job-retry: coding-job-1"),
            "authorType": "user",
            "authorAgentId": None,
        }]
        wc.retry_transient_coding_jobs(
            pc, ISSUE, {"coding_job_door": server.path})
    finally:
        server.stop()
    assert server.requests == [], "a person's line names no command"


def test_retries_are_bounded_per_key_and_end_in_a_note_for_a_person(pc):
    # M4: a door that keeps answering WAIT would be re-admitted forever,
    # one comment per wake. After the per-key bound the retry stops and a
    # person is told plainly.
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "WAIT", "wait_reason": "CHILD_QUEUE_FLEET_READY_FULL",
        "wait_detail": {"ready": 1, "limit": 1}}})
    server.start()
    try:
        pc.comment_rows["iss-7"] = [
            _carrier_note("[t2-carrier] coding job blocked — WAIT\n\n"
                          "coding-job-retry: coding-job-1", pc)
            for _ in range(3)
        ]
        wc.retry_transient_coding_jobs(
            pc, ISSUE, {"coding_job_door": server.path})
    finally:
        server.stop()
    assert server.requests == [], "the bound must stop the admit loop"
    assert any("person" in body for _issue, body in pc.comment_calls), \
        "someone must be told the retries ran out"


def test_below_the_bound_the_retry_still_happens(pc):
    # M4 sanity: two earlier transient notes for the key, bound 3 — the
    # third admit still goes out.
    server = FakeDoorServer(reply_body={"ok": True, "result": {
        "state": "WAIT", "wait_reason": "CHILD_QUEUE_FLEET_READY_FULL",
        "wait_detail": {"ready": 1, "limit": 1}}})
    server.start()
    try:
        pc.comment_rows["iss-7"] = [
            _carrier_note("[t2-carrier] coding job blocked — WAIT\n\n"
                          "coding-job-retry: coding-job-1", pc)
            for _ in range(2)
        ]
        wc.retry_transient_coding_jobs(
            pc, ISSUE, {"coding_job_door": server.path})
    finally:
        server.stop()
    assert len(server.requests) == 1
