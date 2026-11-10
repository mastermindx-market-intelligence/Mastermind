"""Unit tests for the MMOS lane T2 wake carrier — no server, fakes only.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     tests/test_mmos_teammate_carrier.py
"""
import importlib.util
import json
import os
import sys

import pytest

CARRIER = os.path.join(os.path.dirname(__file__), "..", "tools",
                       "mmos_teammate", "wake_carrier.py")
spec = importlib.util.spec_from_file_location("wake_carrier", CARRIER)
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)


class FakePaperclip:
    """Records calls; answers like the dev instance would for one issue."""

    def __init__(self, agent_id="ag-1", issues=None, comments=None,
                 interactions=None, metadata=None, fail=()):
        self.agent_id = agent_id
        self.run_id = "run-9"
        self.issues = issues or {}
        self.comment_rows = dict(comments or {})
        self.interaction_rows = list(interactions or [])
        self.documents = {}
        self.child_rows = {}
        self.calls = []
        self.fail = set(fail)
        self.metadata = metadata

    def _guard(self, name):
        if name in self.fail:
            raise wc.CarrierError(f"{name} failed (fake)")

    def me(self):
        self._guard("me")
        binding = self.metadata if self.metadata is not None \
            else {"primaryThreadId": "th-1"}
        return {"id": self.agent_id, "metadata": metadata_with(binding)}

    def inbox(self):
        self._guard("inbox")
        return [{"id": iid, "identifier": row.get("identifier", iid),
                 "status": row["status"], "updatedAt": row.get("updatedAt", ""),
                 "activeRun": row.get("activeRun"),
                 "dependencyReady": row.get("dependencyReady", True)}
                for iid, row in self.issues.items()]

    def issue(self, issue_id):
        return dict(self.issues[issue_id], id=issue_id)

    def checkout(self, issue_id, agent_id, allow_blocked=False):
        self._guard("checkout")
        self.calls.append(("checkout", issue_id, agent_id, allow_blocked))
        row = self.issues[issue_id]
        allowed = ("todo", "in_progress", "blocked") if allow_blocked \
            else ("todo", "in_progress")
        assert row["status"] in allowed, "expectedStatuses would refuse"
        if row["status"] != "blocked":
            row["status"] = "in_progress"

    def comments(self, issue_id):
        return self.comment_rows.get(issue_id, [])

    def add_comment(self, issue_id, body):
        self._guard("comment")
        self.calls.append(("comment", issue_id, body))
        self.comment_rows.setdefault(issue_id, []).append(
            {"body": body, "authorType": "agent"})

    def interactions(self, issue_id):
        return [dict(row) for row in self.interaction_rows]

    def request_confirmation(self, issue_id, idem_key, prompt, target=None):
        self._guard("interaction")
        # Real dev-server behavior (verified live 2026-11-10): a re-POST of an
        # idempotencyKey that exists from ANOTHER run is 409, not a dedupe.
        if any(row.get("idempotencyKey") == idem_key for row in self.interaction_rows):
            raise wc.CarrierError(
                f"POST /api/issues/{issue_id}/interactions -> HTTP 409 "
                '{"error":"Interaction idempotency key already exists"}')
        self.interaction_rows.append(
            {"id": f"ix-{len(self.interaction_rows) + 1}", "kind": "request_confirmation",
             "status": "pending", "idempotencyKey": idem_key,
             "payloadTarget": target})
        self.calls.append(("interaction", issue_id, idem_key))
        return {"id": "ix-1"}

    def set_status(self, issue_id, status):
        self._guard("status")
        self.calls.append(("status", issue_id, status))
        self.issues[issue_id]["status"] = status

    def issue_document(self, issue_id, key):
        self._guard("document")
        return self.documents.get((issue_id, key))

    def put_issue_document(self, issue_id, key, title, body):
        self._guard("document")
        self.documents[(issue_id, key)] = {"key": key, "title": title,
                                           "body": body}
        self.calls.append(("document", issue_id, key))

    def children(self, issue_id):
        # mirrors the real surface: company issues filtered by parentId
        return [dict(c) for c in self.child_rows.get(issue_id, [])]

    def create_issue(self, company_id, payload):
        self._guard("create_issue")
        iid = f"child-{len(self.child_rows.get(payload.get('parentId'), [])) + 1}"
        row = {"id": iid, "identifier": f"MMO-C{len(self.calls)}",
               "parentId": payload.get("parentId"),
               "assigneeAgentId": payload.get("assigneeAgentId"),
               "title": payload.get("title"),
               "description": payload.get("description"),
               "status": payload.get("status", "todo")}
        self.child_rows.setdefault(payload.get("parentId"), []).append(row)
        self.calls.append(("create_issue", payload.get("parentId"), iid))
        return dict(row)

    def block_issue(self, issue_id, blocker_ids, owner_agent_id, action):
        self._guard("block")
        self.calls.append(("block", issue_id, tuple(blocker_ids),
                           owner_agent_id))
        self.issues[issue_id]["status"] = "blocked"


class FakeT3:
    """Thread memory + a send() that appends the marker turn and answers.
    Each send() gets its own runId, exactly like real T3 turns."""

    def __init__(self, replies=None, messages=None, send_error=None):
        self.messages_store = list(messages or [])
        self.replies = list(replies or [])
        self.send_error = send_error
        self.sends = []
        self._auto = 0
        self._runs = 0

    def send(self, message):
        if self.send_error:
            raise wc.CarrierError(self.send_error)
        self.sends.append(message)
        self._runs += 1
        run = f"r{self._runs}"
        self.messages_store.append(("user", run, message))
        if self.replies:
            reply = self.replies.pop(0)
        else:
            self._auto += 1
            reply = "fake answer" if self._auto == 1 else f"fake answer {self._auto}"
        self.messages_store.append(("assistant", run, reply))
        return {"status": "completed", "reply": self.messages_store[-1][2],
                "error": None}

    def messages(self, count=60):
        return {"threadId": "th-1"}, list(self.messages_store)


def metadata_with(binding):
    return {"teammate": {"t3": binding}}


def one_issue():
    return {"is-1": {"identifier": "MMO-1", "status": "todo",
                     "title": "Summarize file X",
                     "description": "Write a three-line summary."}}


def run(pc, t3, opts=None, agent_env="ag-1"):
    os.environ["PAPERCLIP_AGENT_ID"] = agent_env
    return wc.run_carrier(pc, lambda tid: t3, opts or {})


def test_happy_path_one_send_one_comment_confirmation_status():
    pc, t3 = FakePaperclip(issues=one_issue()), FakeT3(replies=["line1\nline2\nline3"])
    assert run(pc, t3) == 0
    assert len(t3.sends) == 1
    kinds = [(c[0], c[2] if c[0] == "status" else None) for c in pc.calls]
    assert ("status", "in_review") in kinds
    # ordering: comment -> interaction -> status
    seq = [c[0] for c in pc.calls]
    assert seq.index("comment") < seq.index("interaction") < seq.index("status")
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies == ["line1\nline2\nline3"]  # comment == thread answer, exactly


def test_message_carries_marker_title_and_body():
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    msg = wc.build_message("MMO-1", "Summarize file X",
                           "Write a three-line summary.", op)
    assert f"[{op}]" in msg and "MMO-1" in msg and "three-line" in msg


def test_issue_link_is_config_driven_and_loopback_only():
    tpl = "http://127.0.0.1:3100/MAS/issues/{identifier}"
    assert wc.issue_link(tpl, "MAS-12") == \
        "[MAS-12](http://127.0.0.1:3100/MAS/issues/MAS-12)"
    msg = wc.build_message("MAS-12", "t", "b", "pc-x-1",
                           link=wc.issue_link(tpl, "MAS-12"))
    assert "[MAS-12](http://127.0.0.1:3100/MAS/issues/MAS-12)" in msg
    assert msg.startswith("[pc-x-1]")
    # no template, a non-loopback host, a hostile identifier: no link at all
    assert wc.issue_link(None, "MAS-12") is None
    assert wc.issue_link("https://example.com/{identifier}", "MAS-12") is None
    assert wc.issue_link("http://127.0.0.1.evil.test:80/{identifier}", "MAS-12") is None
    assert wc.issue_link(tpl, "MAS-12)](http://x") is None
    assert wc.issue_link("http://127.0.0.1:3100/MAS/issues/", "MAS-12") is None
    assert "Issue page" not in wc.build_message("MAS-12", "t", "b", "pc-x-1")


def test_ask_help_names_other_teammates_only():
    roster = {"Assurance": "a-1", "Design Lead": "a-2", "bad`name\n": "a-3"}
    text = wc.ask_help(roster, "a-1")
    assert "Design Lead" in text and "Assurance" not in text and "bad" not in text
    msg = wc.build_message("MAS-1", "t", "b", "pc-x-1", asking=text)
    # the example quoted back by a teammate is never taken as a real ask
    assert "```paperclip-ask" in msg and wc.parse_ask_block(msg) is None
    real = msg.replace("<short title>", "Check the copy")
    assert wc.parse_ask_block(real)["assignee"] == "Design Lead"
    assert wc.ask_help({"Assurance": "a-1"}, "a-1") is None
    assert wc.ask_help({}, "a-1") is None
    assert "paperclip-ask" not in wc.build_message("MAS-1", "t", "b", "pc-x-1")


def test_t3_cli_gets_the_port_and_never_the_run_token(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setenv("PAPERCLIP_RUN_ID", "run-1")
    monkeypatch.delenv("T3CODE_PORT", raising=False)
    env_bin = "/usr/bin/env"
    with_port = wc.T3Thread(env_bin, str(tmp_path), "th-1", str(tmp_path),
                            t3_port=3780)._run([]).stdout
    assert "T3CODE_PORT=3780" in with_port.splitlines()
    assert f"T3CODE_HOME={tmp_path}" in with_port.splitlines()
    assert "PAPERCLIP_" not in with_port
    without = wc.T3Thread(env_bin, str(tmp_path), "th-1", str(tmp_path))._run([]).stdout
    assert "T3CODE_PORT" not in without and "PAPERCLIP_" not in without


def test_no_ready_issue_is_a_clean_exit():
    pc, t3 = FakePaperclip(issues={"is-1": {"identifier": "MMO-1",
                                            "status": "done",
                                            "title": "t", "description": "d"}}), FakeT3()
    assert run(pc, t3) == 0
    assert t3.sends == [] and pc.calls == []


def test_reentry_after_marker_does_not_resend():
    pc, t3 = FakePaperclip(issues=one_issue()), FakeT3()
    assert run(pc, t3) == 0
    first_sends = len(t3.sends)
    pc2 = FakePaperclip(issues={"is-1": {"identifier": "MMO-1", "status": "todo",
                                         "title": "Summarize file X",
                                         "description": "Write a three-line summary."}})
    assert run(pc2, t3) == 0
    assert len(t3.sends) == first_sends  # no second send
    bodies = [c[2] for c in pc2.calls if c[0] == "comment"]
    assert bodies == ["fake answer"]  # reconciled from the thread, once


def test_reentry_pending_marker_waits_then_reconciles_no_resend():
    pc = FakePaperclip(issues=one_issue())
    content = "Summarize file X\nWrite a three-line summary."
    op = wc.op_id("is-1", content)
    pending = [("user", "r0", f"[{op}] old wake")]
    t3 = FakeT3(messages=pending)
    opts = {"poll_interval_sec": 0, "pending_timeout_sec": 1}
    # Simulate the server-side turn finishing during the wait.
    class LaterT3(FakeT3):
        def messages(self, count=60):
            if not self.messages_store[-1][0] == "assistant":
                self.messages_store.append(("assistant", "r0", "late answer"))
            return {"threadId": "th-1"}, list(self.messages_store)
    assert run(pc, LaterT3(messages=pending), opts) == 0
    assert t3.sends == []
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies == ["late answer"]


def test_t3_down_releases_issue_and_fails():
    pc = FakePaperclip(issues=one_issue())
    t3 = FakeT3(send_error="t3 thread send failed (exit 1): unreachable")
    with pytest.raises(wc.CarrierError):
        run(pc, t3)
    kinds = [c[0] for c in pc.calls]
    assert "comment" in kinds  # release note posted
    assert pc.issues["is-1"]["status"] == "todo"  # released, visible


def test_new_task_on_same_issue_gets_new_marker_and_sends():
    pc, t3 = FakePaperclip(issues=one_issue()), FakeT3()
    assert run(pc, t3) == 0
    pc2 = FakePaperclip(issues={"is-1": {"identifier": "MMO-1", "status": "todo",
                                         "title": "Summarize file X",
                                         "description": "Now do it in five lines."}})
    assert run(pc2, t3) == 0
    assert len(t3.sends) == 2  # different content hash -> a new operation


def test_agent_identity_mismatch_is_fatal():
    pc, t3 = FakePaperclip(agent_id="ag-other", issues=one_issue()), FakeT3()
    with pytest.raises(wc.CarrierError):
        run(pc, t3, agent_env="ag-1")
    assert t3.sends == []


def test_binding_missing_is_fatal_before_any_checkout():
    pc = FakePaperclip(issues=one_issue(),
                       metadata={"primaryThreadId": None, "bindingRevision": 1})
    with pytest.raises(wc.CarrierError):
        run(pc, FakeT3())
    assert pc.calls == []


def test_choose_issue_skips_active_blocked_and_dependencies():
    rows = [
        {"id": "a", "status": "todo", "activeRun": {"id": "r1"}, "updatedAt": "1"},
        {"id": "b", "status": "in_progress", "activeRun": {"id": "r2"}, "updatedAt": "2"},
        {"id": "c", "status": "todo", "activeRun": None,
         "dependencyReady": False, "updatedAt": "3"},
        {"id": "d", "status": "todo", "activeRun": None, "updatedAt": "4"},
        {"id": "e", "status": "in_progress", "activeRun": None, "updatedAt": "5"},
        {"id": "f", "status": "blocked", "activeRun": None, "updatedAt": "6"},
    ]
    # assignment automation may have moved e to in_progress; still eligible
    assert [r["id"] for r in wc.choose_issue(rows)] == ["d", "e"]


def test_choose_issue_takes_own_active_run_and_ignores_str_shape():
    rows = [
        # this run's own assignment wake: activeRun IS us -> eligible
        {"id": "a", "status": "in_progress", "activeRun": {"id": "run-9"},
         "updatedAt": "1"},
        # another live run holds it -> not ours
        {"id": "b", "status": "todo", "activeRun": {"id": "run-x"},
         "updatedAt": "2"},
        # activeRun as a bare string is handled too
        {"id": "c", "status": "todo", "activeRun": "run-9", "updatedAt": "3"},
    ]
    assert [r["id"] for r in wc.choose_issue(rows, "run-9")] == ["a", "c"]
    assert [r["id"] for r in wc.choose_issue(rows, "run-9")][:1] == ["a"]


def test_choose_issue_prefers_own_bound_issue_over_older_unbound():
    # Observed live (MMO-11/12, 2026-11-10): the assignment wake is bound to
    # the NEW issue, but an older unbound in_progress issue sorts first by
    # updatedAt. The run must take the issue bound to IT, not the older one.
    rows = [
        {"id": "old", "status": "in_progress", "activeRun": None,
         "updatedAt": "1"},
        {"id": "bound", "status": "in_progress", "activeRun": {"id": "run-9"},
         "updatedAt": "2"},
    ]
    order = [r["id"] for r in wc.choose_issue(rows, "run-9")]
    assert order.index("bound") < order.index("old")


def test_assignment_wake_run_does_the_work_on_own_active_run():
    # Item 1: the assignment wake binds the issue to THIS run before the
    # carrier starts (activeRun == pc.run_id). The carrier must do the work,
    # not skip it. A checkout 409 because it is already ours is not a refusal.
    issues = {"is-1": {"identifier": "MMO-12", "status": "in_progress",
                       "title": "T45 task", "description": "Reply: OK"}}
    pc = FakePaperclip(issues=issues)
    pc.inbox_rows_override = [{"id": "is-1", "identifier": "MMO-12",
                               "status": "in_progress",
                               "activeRun": {"id": pc.run_id}, "updatedAt": "1",
                               "dependencyReady": True}]
    original_inbox = pc.inbox

    def inbox_with_active_run():
        return [dict(r) for r in pc.inbox_rows_override]
    pc.inbox = inbox_with_active_run
    checkout_calls = []
    original_checkout = pc.checkout

    def checkout_409_once(issue_id, agent_id, allow_blocked=False):
        checkout_calls.append(issue_id)
        if len(checkout_calls) == 1:
            raise wc.CarrierError(
                "POST /api/issues/is-1/checkout -> HTTP 409 "
                '{"error":"issue already checked out"}')
        return original_checkout(issue_id, agent_id, allow_blocked)
    pc.checkout = checkout_409_once
    t3 = FakeT3(replies=["ASSIGNMENT-WAKE-OK"])
    assert run(pc, t3) == 0
    assert len(t3.sends) == 1                      # the work was sent once
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies == ["ASSIGNMENT-WAKE-OK"]        # delivered once
    assert pc.issues["is-1"]["status"] == "in_review"


def test_assignment_moved_in_progress_issue_is_picked_up():
    # Paperclip moves a freshly assigned issue to in_progress and wakes the
    # agent; the carrier must still check it out and complete it.
    issues = {"is-1": {"identifier": "MMO-1", "status": "in_progress",
                       "title": "Summarize file X",
                       "description": "Write a three-line summary."}}
    pc, t3 = FakePaperclip(issues=issues), FakeT3(replies=["done"])
    assert run(pc, t3) == 0
    assert len(t3.sends) == 1
    assert pc.issues["is-1"]["status"] == "in_review"


def test_scan_marker_states():
    msgs = [("user", "r0", "[pc-is-1-abc] q"), ("assistant", "r0", "partial"),
            ("assistant", "r0", "final answer")]
    assert wc.scan_marker(msgs, "pc-is-1-abc") == ("reply", "final answer")
    assert wc.scan_marker([("user", "r0", "[pc-is-1-abc] q")], "pc-is-1-abc") == \
        ("pending", None)
    assert wc.scan_marker(msgs, "pc-is-1-zzz") == (None, None)


def test_crash_switch_exits_hard_before_comment(monkeypatch):
    # os._exit would kill pytest itself; swap it for an exception with the code.
    def fake_exit(code):
        raise SystemExit(code)
    monkeypatch.setattr(wc.os, "_exit", fake_exit)
    pc = FakePaperclip(issues=one_issue())
    t3 = FakeT3()
    with pytest.raises(SystemExit) as exc:
        run(pc, t3, opts={"crash_after": "pre-comment"})
    assert exc.value.code == 97
    assert len(t3.sends) == 1
    assert [c for c in pc.calls if c[0] == "comment"] == []  # died before comment


def test_reply_already_commented_is_not_posted_twice():
    pc, t3 = FakePaperclip(issues=one_issue()), FakeT3()
    assert run(pc, t3) == 0
    pc2 = FakePaperclip(issues={"is-1": {"identifier": "MMO-1", "status": "todo",
                                         "title": "Summarize file X",
                                         "description": "Write a three-line summary."}},
                        comments={"is-1": [{"body": "fake answer"}]})
    assert run(pc2, t3) == 0
    assert [c for c in pc2.calls if c[0] == "comment"] == []
    # reconciliation still completes delivery: interaction + status ensured
    seq = [c[0] for c in pc2.calls]
    assert "interaction" in seq and ("status", "in_review") in \
        [(c[0], c[2] if c[0] == "status" else None) for c in pc2.calls]


def test_unexpected_exception_still_releases_the_issue():
    # e.g. FileNotFoundError from a bad t3_bin: not a CarrierError, but the
    # checked-out issue must not be left silently held.
    class CrashingT3(FakeT3):
        def messages(self, count=60):
            raise FileNotFoundError("no such t3 binary")
    pc = FakePaperclip(issues=one_issue())
    with pytest.raises(FileNotFoundError):
        run(pc, CrashingT3())
    kinds = [c[0] for c in pc.calls]
    assert "comment" in kinds  # release note posted
    assert pc.issues["is-1"]["status"] == "todo"  # released, visible


def test_t3thread_run_passes_str_stdin_and_expands_paths(tmp_path):
    # real subprocess: /bin/cat echoes stdin back; catches the text=True +
    # bytes-input crash the fakes cannot see, and the ~ expansion.
    th = wc.T3Thread("~/_no_such_home_bin", "~", "th-1", str(tmp_path))
    assert th._bin == os.path.expanduser("~/_no_such_home_bin")
    cat = wc.T3Thread("/bin/cat", "~", "th-1", str(tmp_path))
    proc = cat._run(["-"], stdin_text="hello carrier")
    assert proc.returncode == 0
    assert proc.stdout == "hello carrier"


def test_side_message_after_answer_never_replaces_the_reply():
    # Adversarial finding 2026-11-10 (MMO-7): crash after send, then an
    # unrelated later turn answers differently in the thread. The marker's
    # answer is bound to the marker's runId; the newer text must NOT become
    # the reconciled reply (it used to be posted as a second comment).
    content = "Summarize file X\nWrite a three-line summary."
    op = wc.op_id("is-1", content)
    messages = [
        ("user", "r1", f"[{op}] the task"),
        ("assistant", "r1", "ADVERSARY-5"),          # the real answer
        ("user", "r2", "Side note from the operator"),
        ("assistant", "r2", "a completely newer text"),
    ]
    t3 = FakeT3(messages=messages)
    pc = FakePaperclip(issues={"is-1": {"identifier": "MMO-1", "status": "in_progress",
                                         "title": "Summarize file X",
                                         "description": "Write a three-line summary."}})
    assert run(pc, t3) == 0
    assert t3.sends == []  # reconciled, never resent
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies == ["ADVERSARY-5"]  # exactly one answer comment, the bound reply
    assert pc.issues["is-1"]["status"] == "in_review"


def test_confirmation_replay_is_skipped_not_409():
    # Adversarial finding 2026-11-10 (run 98e3f054): a re-POST of this op's
    # confirmation key from a later run is 409, which failed the run, released
    # the delivered issue and attracted more wakes. deliver() must see the
    # existing interaction and skip the POST.
    content = "Summarize file X\nWrite a three-line summary."
    op = wc.op_id("is-1", content)
    messages = [("user", "r1", f"[{op}] the task"),
                ("assistant", "r1", "fake answer")]
    t3 = FakeT3(messages=messages)
    pc = FakePaperclip(
        issues={"is-1": {"identifier": "MMO-1", "status": "in_progress",
                         "title": "Summarize file X",
                         "description": "Write a three-line summary."}},
        comments={"is-1": [{"body": "fake answer"}]},   # crash after comment
        interactions=[{"id": "ix-1", "kind": "request_confirmation",
                       "status": "pending",
                       "idempotencyKey": f"{op}-confirm"}])  # and after confirmation
    assert run(pc, t3) == 0
    assert [c for c in pc.calls if c[0] == "interaction"] == []  # no re-POST, no 409
    assert [c for c in pc.calls if c[0] == "comment"] == []      # no release note
    assert pc.issues["is-1"]["status"] == "in_review"            # completes cleanly


def test_parse_output_block_takes_last_wellformed_block():
    reply = ("Summary text.\n\n"
             "```paperclip-output\nkey: summary\ntitle: One-pager\nline one\nline two\n```\n")
    doc = wc.parse_output_block(reply)
    assert doc == {"key": "summary", "title": "One-pager",
                   "body": "line one\nline two\n"}
    # a later block wins over an earlier one
    two = ("```paperclip-output\nkey: first\ntitle: A\nx\n```\n"
           "middle\n"
           "```paperclip-output\nkey: second\ntitle: B\ny\n```\n")
    assert wc.parse_output_block(two)["key"] == "second"


def test_parse_output_block_malformed_is_none_never_throws():
    assert wc.parse_output_block("no block here") is None
    assert wc.parse_output_block("```paperclip-output\nno key\n```\n") is None
    assert wc.parse_output_block("```paperclip-output\nkey: bad key!\nx\n```\n") is None
    assert wc.parse_output_block("```paperclip-output\nkey: k\nnever closed") is None
    assert wc.parse_output_block(None) is None


def test_output_block_becomes_issue_document_once():
    reply = ("Wrote outputs/summary.md\n\n"
             "```paperclip-output\nkey: mmo-summary\ntitle: Summary\n# S\nbody\n```\n")
    pc, t3 = FakePaperclip(issues=one_issue()), FakeT3(replies=[reply])
    assert run(pc, t3) == 0
    docs = [c for c in pc.calls if c[0] == "document"]
    assert [(c[1], c[2]) for c in docs] == [("is-1", "mmo-summary")]
    assert pc.documents[("is-1", "mmo-summary")]["body"] == "# S\nbody\n"
    # a re-run with the same thread answer does not write it again
    pc2 = FakePaperclip(issues={"is-1": {"identifier": "MMO-1", "status": "in_progress",
                                         "title": "Summarize file X",
                                         "description": "Write a three-line summary."}},
                        comments={"is-1": [{"body": reply}]},
                        interactions=[{"id": "ix-1", "kind": "request_confirmation",
                                       "status": "pending",
                                       "idempotencyKey":
                                       wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.") + "-confirm"}])
    pc2.documents[("is-1", "mmo-summary")] = {"key": "mmo-summary",
                                              "title": "Summary",
                                              "body": "# S\nbody\n"}
    t3.messages_store = [("user", "r1", "task"),
                         ("assistant", "r1", reply)]
    assert run(pc2, t3) == 0
    assert [c for c in pc2.calls if c[0] == "document"] == []  # idempotent


def test_reply_without_output_block_writes_no_document():
    pc, t3 = FakePaperclip(issues=one_issue()), FakeT3(replies=["plain answer"])
    assert run(pc, t3) == 0
    assert [c for c in pc.calls if c[0] == "document"] == []


ASK_REPLY = ("I need Atlas for the line count.\n\n"
             "```paperclip-ask\n"
             "assignee: Atlas-TEST\n"
             "title: Count lines in t45_alpha.txt\n"
             "description: Run wc -l on t45_alpha.txt and report the number.\n"
             "```\n")


def run_with_roster(pc, t3, roster, opts=None):
    os.environ["PAPERCLIP_AGENT_ID"] = "ag-1"
    os.environ["PAPERCLIP_COMPANY_ID"] = "co-1"
    merged = {"roster": roster}
    merged.update(opts or {})
    return wc.run_carrier(pc, lambda tid: t3, merged)


def test_ask_block_creates_child_and_blocks_parent():
    roster = {"Atlas-TEST": "ag-atlas"}
    pc = FakePaperclip(issues=one_issue())
    t3 = FakeT3(replies=[ASK_REPLY])
    assert run_with_roster(pc, t3, roster) == 0
    creates = [c for c in pc.calls if c[0] == "create_issue"]
    assert len(creates) == 1
    parent_id, child_id = creates[0][1], creates[0][2]
    assert pc.child_rows[parent_id][0]["assigneeAgentId"] == "ag-atlas"
    assert pc.child_rows[parent_id][0]["title"] == "Count lines in t45_alpha.txt"
    blocks = [c for c in pc.calls if c[0] == "block"]
    assert len(blocks) == 1 and blocks[0][2] == (child_id,)
    # the unblock owner is the acting agent itself — this build 403s an
    # agent naming another agent as unblock owner
    assert blocks[0][3] == "ag-1"
    # the asking reply is the parent comment; no confirmation, not in_review
    kinds = [c[0] for c in pc.calls]
    assert "comment" in kinds and "interaction" not in kinds
    assert pc.issues["is-1"]["status"] == "blocked"


def test_ask_replay_creates_no_second_child():
    roster = {"Atlas-TEST": "ag-atlas"}
    pc = FakePaperclip(issues=one_issue())
    t3 = FakeT3(replies=[ASK_REPLY])
    assert run_with_roster(pc, t3, roster) == 0
    # second run (crash-replay): the marker rule reconciles the same reply;
    # the existing child is reused, the parent is not double-blocked
    child_ident = pc.child_rows["is-1"][0]["identifier"]
    pc2 = FakePaperclip(issues={"is-1": {"identifier": "MMO-1",
                                         "status": "blocked",
                                         "unblockDescriptor": {"owner": {"agentId": "ag-1"},
                                                               "action": f"Atlas-TEST completes {child_ident}: x"},
                                         "title": "Summarize file X",
                                         "description": "Write a three-line summary."}})
    pc2.child_rows = pc.child_rows
    pc2.comment_rows = {"is-1": [{"body": ASK_REPLY}]}  # first run posted it
    real_op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    t3.messages_store = [("user", "r1", f"[{real_op}] task"),
                         ("assistant", "r1", ASK_REPLY)]
    assert run_with_roster(pc2, t3, roster) == 0
    assert [c for c in pc2.calls if c[0] == "create_issue"] == []
    assert [c for c in pc2.calls if c[0] == "block"] == []
    assert [c for c in pc2.calls if c[0] == "comment"] == []  # already posted


def test_ask_for_unknown_or_foreign_teammate_is_plain_reply():
    roster = {"Atlas-TEST": "ag-atlas"}  # Mira-TEST deliberately absent
    pc = FakePaperclip(issues=one_issue())
    foreign = ASK_REPLY.replace("Atlas-TEST", "Somebody-Else")
    t3 = FakeT3(replies=[foreign])
    assert run_with_roster(pc, t3, roster) == 0
    assert [c for c in pc.calls if c[0] == "create_issue"] == []
    # delivered as a normal answer instead: comment + confirmation + in_review
    kinds = [c[0] for c in pc.calls]
    assert "interaction" in kinds
    assert pc.issues["is-1"]["status"] == "in_review"


def test_malformed_ask_block_is_plain_reply_never_error():
    roster = {"Atlas-TEST": "ag-atlas"}
    for bad in ("```paperclip-ask\nno assignee\n```\n",
                "```paperclip-ask\nassignee: Atlas-TEST\nnever closed",
                "```paperclip-ask\nassignee: Atlas-TEST\ntitle: \n```\n"):
        pc = FakePaperclip(issues=one_issue())
        t3 = FakeT3(replies=[bad])
        assert run_with_roster(pc, t3, roster) == 0
        assert [c for c in pc.calls if c[0] == "create_issue"] == []
        assert pc.issues["is-1"]["status"] == "in_review"


def test_choose_issue_blocked_ready_vs_waiting():
    rows = [
        {"id": "b1", "identifier": "MMO-B", "status": "blocked",
         "dependencyReady": True, "updatedAt": "2026-11-10T10:00:00Z"},
        {"id": "b2", "identifier": "MMO-C", "status": "blocked",
         "dependencyReady": False, "updatedAt": "2026-11-10T09:00:00Z"},
        {"id": "b3", "identifier": "MMO-D", "status": "blocked",
         "updatedAt": "2026-11-10T08:00:00Z"},
    ]
    picked = [r["id"] for r in wc.choose_issue(rows, my_run_id="run-9")]
    # ready-blocked is eligible (the blockers_resolved return wake); a
    # blocked issue without an explicit ready flag or still waiting is not
    assert picked == ["b1"]


def blocked_parent_with_done_child():
    ask_op = "pc-is1-abc123def0-ask"
    issues = {"is-1": {"identifier": "MMO-1", "status": "blocked",
                       "dependencyReady": True,
                       "title": "Report the line count",
                       "description": "Ask an engineer for the count.",
                       "unblockDescriptor": {"owner": {"agentId": "ag-1"},
                                             "action": "Atlas completes MMO-2"}}}
    child = {"id": "ch-1", "identifier": "MMO-2", "parentId": "is-1",
             "assigneeAgentId": "ag-atlas", "title": "Count lines",
             "status": "done",
             "description": f"Asked by Mira on MMO-1 [{ask_op}]"}
    return issues, ask_op, child


def test_return_wake_sends_result_and_finishes_parent():
    issues, ask_op, child = blocked_parent_with_done_child()
    pc = FakePaperclip(issues=issues)
    pc.child_rows["is-1"] = [dict(child)]
    pc.comment_rows["ch-1"] = [{"body": "t45_alpha.txt has 12 lines"}]
    t3 = FakeT3(replies=["FINAL: the file has 12 lines"])
    assert run_with_roster(pc, t3, {}) == 0
    # exactly one send, carrying the child result and the return marker
    assert len(t3.sends) == 1
    assert f"[{ask_op}-ret]" in t3.sends[0]
    assert "12 lines" in t3.sends[0] and "MMO-2" in t3.sends[0]
    # checkout was allowed for a blocked issue and the parent finished like
    # any task: reply comment, board confirmation, in_review
    checkouts = [c for c in pc.calls if c[0] == "checkout"]
    assert checkouts and checkouts[0][3] is True
    kinds = [c[0] for c in pc.calls]
    assert "comment" in kinds and "interaction" in kinds
    assert pc.issues["is-1"]["status"] == "in_review"


def test_return_replay_never_resends_or_duplicates():
    issues, ask_op, child = blocked_parent_with_done_child()
    ret_op = f"{ask_op}-ret"
    pc = FakePaperclip(issues=issues)
    pc.child_rows["is-1"] = [dict(child)]
    pc.comment_rows["is-1"] = [{"body": "FINAL: the file has 12 lines"}]
    t3 = FakeT3(messages=[("user", "r1", f"[{ret_op}] the ask came back"),
                          ("assistant", "r1", "FINAL: the file has 12 lines")],
                replies=["SHOULD NOT SEND"])
    pc.interaction_rows = [{"id": "ix-1", "kind": "request_confirmation",
                            "status": "pending",
                            "idempotencyKey": f"{ret_op}-confirm"}]
    assert run_with_roster(pc, t3, {}) == 0
    assert t3.sends == []  # marker rule: reconcile, never resend
    assert [c for c in pc.calls if c[0] == "comment"] == []  # already posted
    assert [c for c in pc.calls if c[0] == "interaction"] == []  # exists
    assert pc.issues["is-1"]["status"] == "in_review"


def test_blocked_issue_without_ask_child_is_left_alone():
    issues = {"is-1": {"identifier": "MMO-1", "status": "blocked",
                       "dependencyReady": True, "title": "Wait on infra",
                       "description": "Waiting on a deploy"}}
    pc = FakePaperclip(issues=issues)
    t3 = FakeT3()
    assert run_with_roster(pc, t3, {}) == 0
    assert t3.sends == []
    assert pc.issues["is-1"]["status"] == "blocked"


def test_ask_child_delivers_done_without_board_confirmation():
    # Atlas's inbox: the child created by Mira's ask (marker in description)
    ask_op = "pc-is1-abc123def0-ask"
    pc = FakePaperclip(issues={"is-1": {
        "identifier": "MMO-2", "status": "in_progress",
        "title": "Count lines", "assigneeAgentId": "ag-1",
        "description": f"Run wc -l.\n\nAsked by Mira on MMO-1 [{ask_op}]"}})
    t3 = FakeT3(replies=["The file has 12 lines"])
    assert run_with_roster(pc, t3, {}) == 0
    kinds = [c[0] for c in pc.calls]
    # no board confirmation: the asker consumes the answer; the issue goes to
    # done so the asker's issue_blockers_resolved wake can fire
    assert "comment" in kinds and "interaction" not in kinds
    assert pc.issues["is-1"]["status"] == "done"


def test_resumed_parent_after_children_completed_runs_return():
    # Paperclip's issue_children_completed wake may move the parent out of
    # blocked before the asker's run starts; the done child is the signal
    issues, ask_op, child = blocked_parent_with_done_child()
    issues["is-1"]["status"] = "in_progress"
    pc = FakePaperclip(issues=issues)
    pc.child_rows["is-1"] = [dict(child)]
    pc.comment_rows["ch-1"] = [{"body": "t45_beta.txt has 30 lines"}]
    t3 = FakeT3(replies=["FINAL: 30 lines"])
    assert run_with_roster(pc, t3, {}) == 0
    assert len(t3.sends) == 1 and f"[{ask_op}-ret]" in t3.sends[0]
    assert "30 lines" in t3.sends[0]
    assert pc.issues["is-1"]["status"] == "in_review"


def test_blocked_parent_with_pending_child_reconciles_ask_not_return():
    issues, _, child = blocked_parent_with_done_child()
    real_op = wc.op_id("is-1", "Report the line count\nAsk an engineer for the count.")
    ask_op = f"{real_op}-ask"  # the marker handle_ask actually matches
    child["status"] = "todo"  # the teammate has not finished yet
    child["description"] = f"Run wc -l.\n\nAsked by Mira on MMO-1 [{ask_op}]"
    pc = FakePaperclip(issues=issues)
    pc.child_rows["is-1"] = [dict(child)]
    # the ask reply is already in the thread (marker rule reconciles it)
    real_op = wc.op_id("is-1", "Report the line count\nAsk an engineer for the count.")
    t3 = FakeT3(messages=[("user", "r1", f"[{real_op}] task"),
                          ("assistant", "r1", ASK_REPLY)])
    assert run_with_roster(pc, t3, {"Atlas-TEST": "ag-atlas"}) == 0
    assert t3.sends == []  # no return send while the child is not done
    assert [c for c in pc.calls if c[0] == "create_issue"] == []


# --- item 5: board feedback (reject-with-comment) on an in_review issue -----

def feedback_issue():
    return {"is-1": {"identifier": "MMO-1", "status": "in_review",
                     "title": "Summarize file X",
                     "description": "Write a three-line summary."}}


def fb_op():
    return wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")


def run_bound(pc, t3, opts=None):
    """run_carrier with the wake bound to issue is-1 (PAPERCLIP_ISSUE_ID)."""
    os.environ["PAPERCLIP_AGENT_ID"] = "ag-1"
    os.environ["PAPERCLIP_ISSUE_ID"] = "is-1"
    try:
        return wc.run_carrier(pc, lambda tid: t3, opts or {})
    finally:
        os.environ.pop("PAPERCLIP_ISSUE_ID", None)


def test_board_feedback_detection():
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "the numbers were wrong", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "line count is off"}}]
    issue = pc.issue("is-1")
    assert wc.board_feedback(pc, issue) == ("line count is off",
                                            "the numbers were wrong")
    # a rejection with no board comment is still feedback
    pc.comment_rows["is-1"] = [{"body": "answer v1", "authorType": "agent"}]
    assert wc.board_feedback(pc, issue) == ("line count is off", None)
    # a pending confirmation means the current round already answered: no-op
    pc.interaction_rows.append(
        {"kind": "request_confirmation", "status": "pending",
         "idempotencyKey": "pc-is-1-x-rev1-confirm"})
    assert wc.board_feedback(pc, issue) is None
    # no rejection at all -> a user comment alone is not a round trigger
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "pending",
         "idempotencyKey": "k"}]
    assert wc.board_feedback(pc, issue) is None


def test_feedback_round_sends_revision_not_original_task():
    op = fb_op()
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "the numbers were wrong", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "line count is off"}}]
    t3 = FakeT3(replies=["answer v2, now correct"])
    assert run_bound(pc, t3) == 0
    assert len(t3.sends) == 1
    assert f"[{op}-rev1]" in t3.sends[0]        # fresh revision marker...
    assert t3.sends[0].count("[pc-") == 1       # ...exactly one marker, one send
    assert "line count is off" in t3.sends[0]   # decline reason reaches the turn
    assert "the numbers were wrong" in t3.sends[0]  # board comment reaches it
    seq = [c[0] for c in pc.calls]
    assert seq.index("comment") < seq.index("interaction") < seq.index("status")
    keys = [c[2] for c in pc.calls if c[0] == "interaction"]
    assert keys == [f"{op}-rev1-confirm"]       # per-round confirmation key
    assert pc.issues["is-1"]["status"] == "in_review"


def test_feedback_replay_after_crash_never_resends():
    op = fb_op()
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "the numbers were wrong", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "line count is off"}}]
    # the rev1 turn already answered, but the crash lost the delivery
    t3 = FakeT3(messages=[("user", "r1", f"[{op}-rev1] board declined"),
                          ("assistant", "r1", "answer v2, now correct")])
    assert run_bound(pc, t3) == 0
    assert t3.sends == []  # marker rule: no resend of the revision
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies == ["answer v2, now correct"]  # delivery repaired exactly once


def test_second_feedback_round_gets_rev2():
    op = fb_op()
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "first decline", "authorType": "user"},
        {"body": "answer v2", "authorType": "agent"},
        {"body": "second decline", "authorType": "user"}]
    # round 1 delivered (its confirmation existed) and the board rejected it
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "idempotencyKey": f"{op}-rev1-confirm",
         "result": {"reason": "still off"}}]
    t3 = FakeT3(messages=[("user", "r1", f"[{op}-rev1] board declined"),
                          ("assistant", "r1", "answer v2")],
                replies=["answer v3"])
    assert run_bound(pc, t3) == 0
    assert len(t3.sends) == 1 and f"[{op}-rev2]" in t3.sends[0]
    assert "second decline" in t3.sends[0] and "still off" in t3.sends[0]
    keys = [c[2] for c in pc.calls if c[0] == "interaction"]
    assert keys == [f"{op}-rev2-confirm"]


def test_in_review_without_feedback_is_a_noop():
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [{"body": "answer v1", "authorType": "agent"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "pending",
         "idempotencyKey": "k"}]
    t3 = FakeT3()
    assert run_bound(pc, t3) == 0
    assert t3.sends == [] and pc.calls == []


def test_bound_todo_issue_falls_through_to_the_inbox_path():
    pc = FakePaperclip(issues=one_issue())
    t3 = FakeT3(replies=["line1\nline2\nline3"])
    os.environ["PAPERCLIP_AGENT_ID"] = "ag-1"
    os.environ["PAPERCLIP_ISSUE_ID"] = "is-1"
    try:
        assert wc.run_carrier(pc, lambda tid: t3, {}) == 0
    finally:
        os.environ.pop("PAPERCLIP_ISSUE_ID", None)
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    assert len(t3.sends) == 1 and f"[{op}]" in t3.sends[0]  # original task op
    assert pc.issues["is-1"]["status"] == "in_review"


def test_board_accept_completes_the_issue():
    # native_completion_review accept: the build hands the issue back to todo;
    # the carrier sees its op's confirmation accepted and finishes it
    op = fb_op()
    issues = feedback_issue()
    issues["is-1"]["status"] = "todo"  # resumed by the accept
    pc = FakePaperclip(issues=issues)
    pc.comment_rows["is-1"] = [{"body": "answer v1", "authorType": "agent"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "accepted",
         "idempotencyKey": f"{op}-confirm"}]
    t3 = FakeT3(messages=[("user", "r1", f"[{op}] task"),
                          ("assistant", "r1", "answer v1")])
    assert run(pc, t3) == 0
    assert t3.sends == []  # no second send of the original task
    statuses = [c for c in pc.calls if c[0] == "status"]
    assert statuses == [("status", "is-1", "done")]
    assert pc.issues["is-1"]["status"] == "done"


def test_deliver_requests_a_completion_review_target():
    op = fb_op()
    pc = FakePaperclip(issues=feedback_issue())
    pc.issues["is-1"]["status"] = "todo"
    t3 = FakeT3(replies=["answer v1"])
    assert run(pc, t3) == 0
    rows = [r for r in pc.interaction_rows
            if r.get("idempotencyKey") == f"{op}-confirm"]
    assert rows and rows[0].get("payloadTarget") == \
        {"type": "custom", "key": "native_completion_review"}


def test_reject_reaches_the_inbox_path_as_feedback():
    # the native_completion_review reject resumes the issue to todo, so the
    # comment wake reaches it through the inbox, not the env binding
    op = fb_op()
    issues = feedback_issue()
    issues["is-1"]["status"] = "todo"
    pc = FakePaperclip(issues=issues)
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "wrong unit", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "idempotencyKey": f"{op}-confirm",
         "result": {"reason": "lines, not words"}}]
    t3 = FakeT3(messages=[("user", "r1", f"[{op}] task"),
                          ("assistant", "r1", "answer v1")],
                replies=["answer v2"])
    assert run(pc, t3) == 0
    assert len(t3.sends) == 1 and f"[{op}-rev1]" in t3.sends[0]
    assert "lines, not words" in t3.sends[0] and "wrong unit" in t3.sends[0]
    assert f"[{op}]\n" not in t3.sends[0]  # never a resend of the original op
    keys = [c[2] for c in pc.calls if c[0] == "interaction"]
    assert keys == [f"{op}-rev1-confirm"]
    assert pc.issues["is-1"]["status"] == "in_review"


# --- a board note on a task with no answer yet is not a revision round ------
# (found on the installed app, MAS-9, 2026-11-10: a task moved to a teammate
# with a board comment reached it as "the board declined the current answer",
# without the task text)

def test_board_comment_before_any_answer_is_not_feedback():
    issues = feedback_issue()
    issues["is-1"]["status"] = "todo"
    pc = FakePaperclip(issues=issues)
    pc.comment_rows["is-1"] = [
        {"body": "moved here from another teammate", "authorType": "user"}]
    pc.interaction_rows = []
    assert wc.board_feedback(pc, pc.issue("is-1")) is None
    t3 = FakeT3(replies=["three lines"])
    assert run(pc, t3) == 0
    op = fb_op()
    assert len(t3.sends) == 1 and f"[{op}]\n" in t3.sends[0]
    assert "-rev1" not in t3.sends[0]
    assert "Write a three-line summary." in t3.sends[0]   # the task itself
    assert "moved here from another teammate" in t3.sends[0]  # and the note
    assert "declined" not in t3.sends[0]


def test_system_notice_is_not_board_feedback():
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "Automatic recovery blocked", "authorType": "system"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": ""}}]
    assert wc.board_feedback(pc, pc.issue("is-1")) is None
    assert wc.board_notes(pc, pc.issue("is-1")) == []


def test_board_notes_keep_order_and_cap():
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "second", "authorType": "user", "createdAt": "2026-11-10T02"},
        {"body": "first", "authorType": "user", "createdAt": "2026-11-10T01"},
        {"body": "agent words", "authorType": "agent",
         "createdAt": "2026-11-10T03"},
        {"body": "x" * 5000, "authorType": "user", "createdAt": "2026-11-10T04"}]
    notes = wc.board_notes(pc, pc.issue("is-1"))
    assert notes[:2] == ["first", "second"] and len(notes[2]) == 2000
    assert wc.board_notes(pc, pc.issue("is-1"), limit=1) == ["x" * 2000]


def test_feedback_reads_comments_newest_first_as_paperclip_lists_them():
    # the installed app returns comments newest first; the board's words on
    # the declined answer are the ones AFTER the agent's answer in time
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "use lines, not words", "authorType": "user",
         "createdAt": "2026-11-10T22:09:00Z"},
        {"body": "answer v1", "authorType": "agent",
         "createdAt": "2026-11-10T22:07:00Z"},
        {"body": "note from before the answer", "authorType": "user",
         "createdAt": "2026-11-10T22:05:00Z"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "wrong unit"}}]
    assert wc.board_feedback(pc, pc.issue("is-1")) == (
        "wrong unit", "use lines, not words")
    # with no comment after the answer, the old note is not quoted as feedback
    pc.comment_rows["is-1"] = pc.comment_rows["is-1"][1:]
    assert wc.board_feedback(pc, pc.issue("is-1")) == ("wrong unit", None)


def test_revision_carries_the_task_when_the_thread_never_had_it():
    op = fb_op()
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [{"body": "answer v1", "authorType": "agent"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "you never got the task"}}]
    t3 = FakeT3(replies=["three lines"])        # empty thread: no [op] marker
    assert run_bound(pc, t3) == 0
    assert "Write a three-line summary." in t3.sends[0]
    assert t3.sends[0].count("[pc-") == 1       # still one marker, the rev one
    # when the task is in the thread it is not repeated
    pc2 = FakePaperclip(issues=feedback_issue())
    pc2.comment_rows["is-1"] = [{"body": "answer v1", "authorType": "agent"}]
    pc2.interaction_rows = [dict(pc.interaction_rows[0])]
    t3b = FakeT3(messages=[("user", "r1", f"[{op}] task"),
                           ("assistant", "r1", "answer v1")],
                 replies=["answer v2"])
    assert run_bound(pc2, t3b) == 0
    assert "Write a three-line summary." not in t3b.sends[0]
