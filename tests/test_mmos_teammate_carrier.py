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

    def __init__(self, replies=None, messages=None, send_error=None,
                 pending_requests=0):
        self.pending_requests = pending_requests
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
        return ({"threadId": "th-1",
                 "pendingRequestCount": self.pending_requests},
                list(self.messages_store))


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
    # a REAL ask ends the reply (the help text says so; R2a finding 18's
    # guard makes the rule hold): take the block up to its closing fence
    real = msg.replace("<short title>", "Check the copy")
    fence = real.rindex("```paperclip-ask")
    real = real[:real.index("```", fence + 3) + 3]
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
    pending = [("user", "r0", f"[{op}]\n\nold wake")]
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
    msgs = [("user", "r0", "[pc-is-1-abc]\n\nq"), ("assistant", "r0", "partial"),
            ("assistant", "r0", "final answer")]
    assert wc.scan_marker(msgs, "pc-is-1-abc") == ("reply", "final answer")
    assert wc.scan_marker([("user", "r0", "[pc-is-1-abc]\n\nq")], "pc-is-1-abc") == \
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
        ("user", "r1", f"[{op}]\n\nthe task"),
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
    messages = [("user", "r1", f"[{op}]\n\nthe task"),
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
    t3.messages_store = [("user", "r1", f"[{real_op}]\n\ntask"),
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


def test_ask_block_strips_the_description_label_from_the_first_line():
    # R2a finding 28: the block format shows `description:` as a labeled
    # field; a teammate that labels it must not deliver the label itself in
    # the child issue's description. `description: please` -> `please`.
    block = ("```paperclip-ask\nassignee: Atlas-TEST\n"
             "title: Count lines\ndescription: please\n```")
    assert wc.parse_ask_block(block)["description"] == "please"
    multi = ("```paperclip-ask\nassignee: Atlas-TEST\n"
             "title: Count lines\ndescription: please\nalso soon\n```")
    assert wc.parse_ask_block(multi)["description"] == "please\nalso soon"
    unlabeled = ("```paperclip-ask\nassignee: Atlas-TEST\n"
                 "title: Count lines\nplease\n```")
    assert wc.parse_ask_block(unlabeled)["description"] == "please"


def test_ask_block_with_words_after_the_fence_is_not_an_ask():
    # R2a finding 18: an ask block counts only when it ends the reply. Words
    # after the closing fence mean the teammate kept talking — a block they
    # reconsidered or wrapped in prose is not a live ask; the reply is
    # delivered as a plain answer.
    block = ("```paperclip-ask\nassignee: Atlas-TEST\n"
             "title: Count lines\ndescription: please\n```")
    assert wc.parse_ask_block(
        block + "\nwait — never mind, I'll do it myself.") is None
    assert wc.parse_ask_block(block)["assignee"] == "Atlas-TEST"
    assert wc.parse_ask_block(block + "\n\n")["assignee"] == "Atlas-TEST"


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
    # The ask op is the one the carrier computes from the parent's content —
    # structural detection (R2a finding 3) matches only that. The child
    # description keeps the pre-2026-11-11 shape on purpose: children the
    # old carrier created must still be recognised.
    ask_op = wc.op_id("is-1", "Report the line count\nAsk an engineer for "
                              "the count.") + "-ask"
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
    # the child's answer is the assignee's own comment (R2a finding 17)
    pc.comment_rows["ch-1"] = [{"body": "t45_alpha.txt has 12 lines",
                                "authorType": "agent",
                                "author": {"id": "ag-atlas"}}]
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
    t3 = FakeT3(messages=[("user", "r1", f"[{ret_op}]\n\nthe ask came back"),
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


# --- a blocked task whose turn was in flight finishes (marker-gated) ---------

def blocked_issue():
    return {"is-1": {"identifier": "MMO-1", "status": "blocked",
                     "dependencyReady": True, "title": "Wait on infra",
                     "description": "Waiting on a deploy"}}


def test_blocked_task_with_answered_marker_finishes():
    # Item 5, scan state "reply": the issue was blocked while the teammate's
    # turn ran; the blockers_resolved wake finds the marker answered and the
    # normal path delivers it — comment, confirmation, in_review — with no
    # second send.
    op = wc.op_id("is-1", "Wait on infra\nWaiting on a deploy")
    pc = FakePaperclip(issues=blocked_issue())
    t3 = FakeT3(messages=[("user", "r1", f"[{op}]\n\nthe task"),
                          ("assistant", "r1", "deploy done, answer ready")])
    assert run_with_roster(pc, t3, {}) == 0
    assert t3.sends == []
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies == ["deploy done, answer ready"]
    assert "interaction" in [c[0] for c in pc.calls]
    assert pc.issues["is-1"]["status"] == "in_review"


def test_blocked_task_with_pending_question_stays_with_it():
    # Item 5, scan state "pending" on a question: the carrier stays with the
    # question, says the waiting line once, and at the deadline leaves the
    # issue blocked (nothing released, nothing un-blocked).
    op = wc.op_id("is-1", "Wait on infra\nWaiting on a deploy")
    asked = [("user", "r1", f"[{op}]\n\nthe task"),
             ("assistant", "r1", "which environment?")]
    t3 = ScriptedT3(states=[(th(active="r1", latest="r1", pending=1), asked)])
    pc = FakePaperclip(issues=blocked_issue())
    opts = wait_opts(Clock(), t3, question_wait_sec=30)
    with pytest.raises(wc.NeedsHuman):
        run_with_roster(pc, t3, {}, opts)
    assert t3.sends == []
    assert [c[2] for c in pc.calls if c[0] == "comment"] == \
        [wc.waiting_note(opts, "th-1")]
    assert pc.issues["is-1"]["status"] == "blocked"


def test_blocked_task_with_slow_marker_waits_then_releases():
    # Item 5, scan state "pending" with no question: the slow-turn wait runs;
    # at its deadline the issue is released for a person (todo, release note).
    op = wc.op_id("is-1", "Wait on infra\nWaiting on a deploy")
    t3 = ScriptedT3(states=[(th(latest="r1", pending=0),
                             [("user", "r1", f"[{op}]\n\nthe task")])])
    pc = FakePaperclip(issues=blocked_issue())
    clock = Clock()

    def nap(seconds):
        clock.nap(seconds)
        t3.nap(seconds)
    opts = {"clock": clock.time, "sleep": nap,
            "pending_timeout_sec": 20, "poll_interval_sec": 10}
    with pytest.raises(wc.CarrierError):
        run_with_roster(pc, t3, {}, opts)
    assert t3.sends == []
    assert any("did not complete" in (c[2] if c[0] == "comment" else "")
               for c in pc.calls)
    # R2a finding 21 changed this end: release moves only in_progress ->
    # todo. A blocked issue keeps its block (its ask children are real
    # blockers); the release note is what makes it visible to a person.
    assert pc.issues["is-1"]["status"] == "blocked"


def test_blocked_issue_with_board_feedback_and_marker_revises():
    # Item 5: board feedback on a blocked issue is handled the same way — the
    # marker gate admits it, and the normal feedback round runs.
    op = fb_op()
    issues = {"is-1": {"identifier": "MMO-1", "status": "blocked",
                       "dependencyReady": True, "title": "Summarize file X",
                       "description": "Write a three-line summary."}}
    pc = FakePaperclip(issues=issues)
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "the numbers were wrong", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "line count is off"}}]
    t3 = FakeT3(messages=[("user", "r1", f"[{op}]\n\ntask"),
                          ("assistant", "r1", "answer v1")],
                replies=["answer v2, now correct"])
    assert run_with_roster(pc, t3, {}) == 0
    assert len(t3.sends) == 1 and f"[{op}-rev1]" in t3.sends[0]
    assert pc.issues["is-1"]["status"] == "in_review"


def test_blocked_issue_with_feedback_but_no_marker_is_left():
    # ...and with no marker in the thread the same issue stays with a person.
    issues = {"is-1": {"identifier": "MMO-1", "status": "blocked",
                       "dependencyReady": True, "title": "Summarize file X",
                       "description": "Write a three-line summary."}}
    pc = FakePaperclip(issues=issues)
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "the numbers were wrong", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "line count is off"}}]
    t3 = FakeT3()
    assert run_with_roster(pc, t3, {}) == 0
    assert t3.sends == []
    assert pc.issues["is-1"]["status"] == "blocked"


def ask_child_issue(ask_op):
    """An issue that IS the carrier's ask child: parented on par-1, whose
    content computes exactly `ask_op` (structural detection)."""
    return FakePaperclip(issues={
        "par-1": {"identifier": "MMO-1", "status": "done",
                  "title": "Report the line count",
                  "description": "Ask an engineer for the count."},
        "is-1": {"identifier": "MMO-2", "status": "in_progress",
                 "parentId": "par-1", "assigneeAgentId": "ag-1",
                 "title": "Count lines",
                 "description": f"Run wc -l.\n\nAsked by Mira on MMO-1\n[{ask_op}]"}})


def test_ask_child_delivers_done_without_board_confirmation():
    # Atlas's inbox: the child created by Mira's ask (the carrier's marker,
    # structurally matched to the parent)
    ask_op = wc.op_id("par-1", "Report the line count\nAsk an engineer for "
                               "the count.") + "-ask"
    pc = ask_child_issue(ask_op)
    t3 = FakeT3(replies=["The file has 12 lines"])
    assert run_with_roster(pc, t3, {}) == 0
    kinds = [c[0] for c in pc.calls]
    # no board confirmation: the asker consumes the answer; the issue goes to
    # done so the asker's issue_blockers_resolved wake can fire
    assert "comment" in kinds and "interaction" not in kinds
    assert pc.issues["is-1"]["status"] == "done"


def test_ask_child_is_never_offered_the_coding_job_block():
    # R4b finding 5: a teammate answering an ask child works delegated work;
    # the asker owns the coding-job decision, so the message never teaches
    # the block — whatever the door config says.
    ask_op = wc.op_id("par-1", "Report the line count\nAsk an engineer for "
                               "the count.") + "-ask"
    pc = ask_child_issue(ask_op)
    t3 = FakeT3(replies=["The file has 12 lines"])
    opts = {"coding_job_door": "/tmp/a-configured-door.sock"}
    assert run_with_roster(pc, t3, {}, opts) == 0
    assert len(t3.sends) == 1
    assert "paperclip-coding-job" not in t3.sends[0]
    # the same door key on a PLAIN task still teaches the block
    pc2, t3b = FakePaperclip(issues=one_issue()), FakeT3(replies=["x"])
    assert run(pc2, t3b, opts) == 0
    assert "paperclip-coding-job" in t3b.sends[0]


def test_resumed_parent_after_children_completed_runs_return():
    # Paperclip's issue_children_completed wake may move the parent out of
    # blocked before the asker's run starts; the done child is the signal
    issues, ask_op, child = blocked_parent_with_done_child()
    issues["is-1"]["status"] = "in_progress"
    pc = FakePaperclip(issues=issues)
    pc.child_rows["is-1"] = [dict(child)]
    pc.comment_rows["ch-1"] = [{"body": "t45_beta.txt has 30 lines",
                                "authorType": "agent",
                                "author": {"id": "ag-atlas"}}]
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
    t3 = FakeT3(messages=[("user", "r1", f"[{real_op}]\n\ntask"),
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
    t3 = FakeT3(messages=[("user", "r1", f"[{op}-rev1]\n\nboard declined"),
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
    t3 = FakeT3(messages=[("user", "r1", f"[{op}-rev1]\n\nboard declined"),
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
    t3 = FakeT3(messages=[("user", "r1", f"[{op}]\n\ntask"),
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
    t3 = FakeT3(messages=[("user", "r1", f"[{op}]\n\ntask"),
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


# --- machine comments are never a person's words (R4b findings 4/5) ---------
#
# The installed Paperclip records every loopback write as authorType "user",
# so text written by the door, the result transport or this carrier reaches
# the board and a teammate as if a person wrote it. The agreed lane line with
# T4c: door/transport comments start with `[coding-job]`, carrier notes with
# `[t2-carrier]`. The reader trusts the prefix, never the authorType.


def test_is_machine_comment_recognises_the_lane_prefixes_only():
    assert wc.is_machine_comment("[coding-job] result: job-42 sealed") is True
    assert wc.is_machine_comment("[t2-carrier] coding job blocked — WAIT") is True
    assert wc.is_machine_comment("  [coding-job] indented") is True
    assert wc.is_machine_comment("\n[t2-carrier] on its own line") is True
    assert wc.is_machine_comment("[coding-job]") is True
    assert wc.is_machine_comment("a person wrote this") is False
    assert wc.is_machine_comment("fine start\n[coding-job] later line") is False
    assert wc.is_machine_comment("") is False
    assert wc.is_machine_comment(None) is False
    # the pre-T4c door prefix is NOT in the lane line; pinned deliberately
    assert wc.is_machine_comment("[t4b-door] old door blocker") is False


def test_machine_comments_are_never_board_notes_or_feedback():
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "[coding-job] result: job-42 sealed", "authorType": "user"},
        {"body": "[t2-carrier] waiting for your answer", "authorType": "user"},
        {"body": "use lines, not words", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "wrong unit"}}]
    # notes and feedback both skip the machine rows whatever their authorType
    assert wc.board_notes(pc, pc.issue("is-1")) == ["use lines, not words"]
    assert wc.board_feedback(pc, pc.issue("is-1")) == ("wrong unit",
                                                       "use lines, not words")
    # machine words alone are never the board's comment
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "[coding-job] result: job-42 sealed", "authorType": "user"}]
    assert wc.board_feedback(pc, pc.issue("is-1")) == ("wrong unit", None)


def test_last_result_comment_skips_machine_comments():
    # R2a finding 17: the reader takes the child row; the comment must be
    # the assignee's own (authorType agent, author id matching).
    pc = FakePaperclip(issues=one_issue())
    child = {"id": "is-1", "assigneeAgentId": "ag-1"}
    pc.comment_rows["is-1"] = [
        {"body": "the real answer", "authorType": "agent",
         "author": {"id": "ag-1"}},
        {"body": "[coding-job] result: job-42 sealed", "authorType": "user",
         "author": {"id": "ag-1"}}]
    assert wc.last_result_comment(pc, child) == "the real answer"
    pc.comment_rows["is-1"] = [
        {"body": "[t2-carrier] waiting for your answer", "authorType": "user",
         "author": {"id": "ag-1"}}]
    assert wc.last_result_comment(pc, child) == \
        "(no answer comment on the child issue)"


def test_last_result_comment_prefers_the_asked_teammates_own_answer():
    # R2a finding 17: a NEWER bystander comment must never displace the
    # assignee's own answer — the child's assignee is who was asked.
    pc = FakePaperclip(issues=one_issue())
    child = {"id": "ch-1", "assigneeAgentId": "ag-atlas"}
    pc.comment_rows["ch-1"] = [
        {"body": "anyone have the count?", "authorType": "user",
         "author": {"id": "ag-other"}},
        {"body": "t45_alpha.txt has 12 lines", "authorType": "agent",
         "author": {"id": "ag-atlas"}},
        {"body": "thanks! closing this out", "authorType": "user",
         "author": {"id": "ag-other"}},
    ]
    assert wc.last_result_comment(pc, child) == "t45_alpha.txt has 12 lines"


def test_last_result_comment_fallback_says_whose_comment_it_is():
    # R2a finding 17: with no assignee comment at all, the newest comment is
    # returned only under a prefix that says it is not the asked teammate's
    # own answer — the asker must know whose words these are.
    pc = FakePaperclip(issues=one_issue())
    child = {"id": "ch-1", "assigneeAgentId": "ag-atlas"}
    pc.comment_rows["ch-1"] = [
        {"body": "I poked Atlas in chat; they said 12 lines",
         "authorType": "user", "author": {"id": "ag-other"}}]
    got = wc.last_result_comment(pc, child)
    assert got.startswith("(")
    assert got.endswith("I poked Atlas in chat; they said 12 lines")
    assert "not" in got  # the prefix states the mismatch plainly


# --- every comment this carrier writes is a machine comment ------------------

def test_coding_job_admission_comment_carries_the_lane_prefix(monkeypatch):
    # Item 2: the admission/replay comment is a carrier note, so it must
    # start with `[t2-carrier]` — the reader-side filter of item 1 relies on
    # every carrier-written comment carrying the prefix.
    class FakeDoor:
        def __init__(self, socket_path):
            pass

        def _request(self, method, path, body=None):
            return 200, {"result": {"state": "ADMITTED", "job_id": "job-42"}}
    monkeypatch.setattr(wc, "DoorClient", FakeDoor)
    pc = FakePaperclip(issues=one_issue())
    wc.handle_coding_job(pc, pc.issue("is-1"), "the answer",
                         {"key": "coding-job-1"}, {"coding_job_door": "/x/sock"})
    assert len(pc.calls) == 1
    body = pc.calls[0][2]
    assert body.startswith("[t2-carrier] coding job ")
    assert "job-42" in body and "ADMITTED" in body
    assert wc.is_machine_comment(body) is True

    class ReplayDoor(FakeDoor):
        def _request(self, method, path, body=None):
            return 200, {"result": {"state": "REPLAY", "job_id": "job-42"}}
    monkeypatch.setattr(wc, "DoorClient", ReplayDoor)
    pc2 = FakePaperclip(issues=one_issue())
    wc.handle_coding_job(pc2, pc2.issue("is-1"), "the answer",
                         {"key": "coding-job-1"}, {"coding_job_door": "/x/sock"})
    replay = pc2.calls[0][2]
    assert replay.startswith("[t2-carrier] coding job ")
    assert wc.is_machine_comment(replay) is True


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
    t3b = FakeT3(messages=[("user", "r1", f"[{op}]\n\ntask"),
                           ("assistant", "r1", "answer v1")],
                 replies=["answer v2"])
    assert run_bound(pc2, t3b) == 0
    assert "Write a three-line summary." not in t3b.sends[0]


# --- a question in the teammate's conversation (MAS-9, 2026-11-10) ----------
#
# Three faults seen on the installed app: nobody woke the task after the
# person answered; half-finished text of a run that had not ended was
# delivered as the answer; the waiting line told the reader nothing to do.
# The carrier now stays with a waiting question in the same run, a run that
# has not ended is never a reply, and the waiting line says what to do.


class Clock:
    """A fake clock: nap(seconds) advances it. No real sleeping anywhere."""

    def __init__(self, start=0.0):
        self.now = float(start)

    def time(self):
        return self.now

    def nap(self, seconds):
        self.now += seconds


def th(active=None, latest=None, pending=0):
    """A T3 thread dict shaped like `t3 thread show --json`: activeRunId and
    latestRunId are null when no turn is live."""
    return {"threadId": "th-1", "activeRunId": active, "latestRunId": latest,
            "pendingRequestCount": pending}


class ScriptedT3(FakeT3):
    """A thread whose state advances one step per sleep and per send. Each
    state is a (thread dict, messages) snapshot served to every read until
    the next advance; the last state persists. ask_on_send makes send() stop
    on a question exactly like `t3 thread send --wait` exiting 2 after the
    message went in."""

    def __init__(self, states, replies=None, ask_on_send=False):
        super().__init__(replies=replies)
        assert states, "a scripted thread needs at least one state"
        self.states = list(states)
        self.step = 0
        self.ask_on_send = ask_on_send
        self.thread_id = "th-1"

    def _state(self):
        return self.states[min(self.step, len(self.states) - 1)]

    def messages(self, count=60):
        thread, msgs = self._state()
        return dict(thread), [tuple(m) for m in msgs]

    def nap(self, seconds):
        self.step += 1

    def send(self, message):
        self.step += 1  # a send is a turn: the thread moves on
        if self.ask_on_send:
            self.sends.append(message)
            raise wc.NeedsHuman("th-1")
        return FakeT3.send(self, message)


def wait_opts(clock, t3, **over):
    """Opts for the question wait: an injected clock and sleep (each sleep
    advances both), so a test scripts time and thread state together."""
    def nap(seconds):
        clock.nap(seconds)
        t3.nap(seconds)
    opts = {"clock": clock.time, "sleep": nap,
            "question_wait_sec": 300, "question_poll_interval_sec": 10,
            "roster": {"Assurance": "ag-1"}}
    opts.update(over)
    return opts


def test_scan_marker_run_not_ended_is_never_a_reply():
    # Rule A (fault 2, MAS-9): assistant text of a run that has not ended is
    # mid-turn prose, never the answer.
    op = "pc-is-1-abc"
    msgs = [("user", "r1", f"[{op}]\n\nthe task"),
            ("assistant", "r1", "I've exhausted every reachable source")]
    # the marker's run is still the thread's active run -> pending
    assert wc.scan_marker(msgs, op, th(active="r1", latest="r1")) == \
        ("pending", None)
    # a question waits and the marker's run is the latest -> pending
    assert wc.scan_marker(msgs, op, th(latest="r1", pending=1)) == \
        ("pending", None)
    # the run ended (no active run, no question) -> the text is the reply
    assert wc.scan_marker(msgs, op, th(latest="r1", pending=0)) == \
        ("reply", "I've exhausted every reachable source")
    assert wc.scan_marker(msgs, op, th(active="r2", latest="r1", pending=0)) == \
        ("reply", "I've exhausted every reachable source")
    # a thread dict without the fields behaves as before
    assert wc.scan_marker(msgs, op, {"threadId": "th-1"}) == \
        ("reply", "I've exhausted every reachable source")
    assert wc.scan_marker([("user", "r1", f"[{op}]\n\nt")], op,
                          th(active="r1")) == ("pending", None)
    # no thread dict at all (old call shape) behaves as before
    assert wc.scan_marker(msgs, op) == ("reply", "I've exhausted every reachable source")


def test_question_during_turn_carrier_stays_and_finishes():
    # Rule B, entry 1: the send itself stops on a question. One waiting line,
    # the question answered on the third poll, the final reply delivered
    # once, exactly one send.
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    asked = [("user", "r1", f"[{op}]\n\nthe task"),
             ("assistant", "r1", "I've exhausted every reachable source")]
    answered = asked + [("assistant", "r1", "the final answer")]
    t3 = ScriptedT3(states=[
        (th(pending=0), []),                                  # before the send
        (th(active="r1", latest="r1", pending=1), asked),     # mid-turn question
        (th(active="r1", latest="r1", pending=1), asked),     # poll 1
        (th(active="r1", latest="r1", pending=1), asked),     # poll 2
        (th(latest="r1", pending=0), answered),               # poll 3: done
    ], ask_on_send=True)
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(), t3)
    assert run(pc, t3, opts) == 0
    assert len(t3.sends) == 1                       # exactly one send
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies[0] == wc.waiting_note(opts, "th-1")   # one waiting line
    assert bodies[1:] == ["the final answer"]       # delivered once
    assert pc.issues["is-1"]["status"] == "in_review"


def test_question_waiting_before_send_clears_then_sends_once():
    # Rule B, entry 3: a question was already waiting, so send_once raised
    # before sending. The carrier waits for the clear, then sends exactly once.
    t3 = ScriptedT3(states=[
        (th(active="r0", latest="r0", pending=1),
         [("user", "r0", "an older question")]),
        (th(latest="r0", pending=0),
         [("user", "r0", "an older question"),
          ("assistant", "r0", "older answer")]),
    ], replies=["fresh answer"])
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(), t3)
    assert run(pc, t3, opts) == 0
    assert len(t3.sends) == 1          # sent only after the question cleared
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies[0] == wc.waiting_note(opts, "th-1")
    assert bodies[1:] == ["fresh answer"]


def test_marker_sent_by_another_wake_means_zero_sends():
    # Rule B, entry 3, the other half: the question cleared and another wake
    # had already sent the marker meanwhile, so this run sends nothing.
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    other = [("user", "r1", f"[{op}]\n\nthe task"),
             ("assistant", "r1", "done by the other wake")]
    t3 = ScriptedT3(states=[
        (th(active="r0", latest="r0", pending=1),
         [("user", "r0", "an older question")]),
        (th(latest="r1", pending=0), other),
    ], replies=["SHOULD NOT SEND"])
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(), t3)
    assert run(pc, t3, opts) == 0
    assert t3.sends == []              # nothing sent; the marker rule holds
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies[1:] == ["done by the other wake"]
    assert pc.issues["is-1"]["status"] == "in_review"


def test_question_wait_deadline_is_needs_human_and_releases_nothing():
    # Rule C: question_wait_sec ends the wait with NeedsHuman; the issue is
    # NOT released (no release note, status stays in_progress) and the
    # waiting line was said exactly once.
    t3 = ScriptedT3(states=[(th(active="r0", latest="r0", pending=1),
                             [("user", "r0", "waiting on a person")])])
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(), t3, question_wait_sec=30)
    with pytest.raises(wc.NeedsHuman):
        run(pc, t3, opts)
    assert t3.sends == []
    notes = [c for c in pc.calls if c[0] == "comment"]
    assert len(notes) == 1 and notes[0][2] == wc.waiting_note(opts, "th-1")
    assert "did not complete" not in notes[0][2]
    assert pc.issues["is-1"]["status"] == "in_progress"  # not released


def test_run_budget_is_the_nearer_question_deadline():
    # Rule C: run_budget_sec from process start caps the wait even when
    # question_wait_sec would allow much longer.
    t3 = ScriptedT3(states=[(th(active="r0", latest="r0", pending=1),
                             [("user", "r0", "waiting on a person")])])
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(1000.0), t3, question_wait_sec=900,
                     run_budget_sec=50, run_start=1000.0)
    with pytest.raises(wc.NeedsHuman):
        run(pc, t3, opts)
    assert t3.sends == []
    notes = [c for c in pc.calls if c[0] == "comment"]
    assert len(notes) == 1 and notes[0][2] == wc.waiting_note(opts, "th-1")
    assert pc.issues["is-1"]["status"] == "in_progress"


def test_wait_for_reply_deadline_with_question_is_needs_human():
    # Rule C: a pending marker whose turn is simply slow stays CarrierError
    # at the deadline; a question waiting at that deadline is NeedsHuman.
    op = "pc-is-1-wait"
    msgs = [("user", "r1", f"[{op}]\n\nthe task")]
    t3 = ScriptedT3(states=[
        (th(latest="r1", pending=0), msgs),                  # slow, no question
        (th(active="r1", latest="r1", pending=1), msgs),     # then it asked
    ])
    clock = Clock()

    def nap(seconds):
        clock.nap(seconds)
        t3.nap(seconds)
    opts = {"clock": clock.time, "sleep": nap,
            "pending_timeout_sec": 20, "poll_interval_sec": 10}
    with pytest.raises(wc.NeedsHuman):
        wc.wait_for_reply(t3, op, opts)


def test_wait_for_reply_deadline_without_question_is_carrier_error():
    op = "pc-is-1-wait"
    t3 = ScriptedT3(states=[(th(latest="r1", pending=0),
                             [("user", "r1", f"[{op}]\n\nthe task")])])
    clock = Clock()

    def nap(seconds):
        clock.nap(seconds)
        t3.nap(seconds)
    opts = {"clock": clock.time, "sleep": nap,
            "pending_timeout_sec": 20, "poll_interval_sec": 10}
    with pytest.raises(wc.CarrierError):
        wc.wait_for_reply(t3, op, opts)


def test_waiting_note_with_template_and_without():
    # Rule D, reworded (item 7): the line names the teammate as an AI
    # teammate, links the conversation when a loopback template is
    # configured, and says what to do, for how long, and how to wake it later.
    os.environ["PAPERCLIP_AGENT_ID"] = "ag-1"
    tpl = "http://127.0.0.1:3774/thread/{thread}"
    note = wc.waiting_note({"roster": {"Assurance": "ag-1", "Design Lead": "ag-2"},
                            "question_wait_sec": 900,
                            "thread_url_template": tpl}, "mcp:a-1")
    assert note == (
        "[t2-carrier] Assurance, an AI teammate, needs your answer to "
        "continue this task. Open its chat: "
        "http://127.0.0.1:3774/thread/mcp%3Aa-1 and reply there. If you "
        "answer within 15 minutes the task continues by itself. Later than "
        "that, add any comment here and Assurance picks the work up again.")
    plain = wc.waiting_note({"roster": {"Assurance": "ag-1"},
                             "question_wait_sec": 900}, "mcp:a-1")
    assert plain == (
        "[t2-carrier] Assurance, an AI teammate, needs your answer to "
        "continue this task. Open its chat in the Team list and reply there. "
        "If you answer within 15 minutes the task continues by itself. "
        "Later than that, add any comment here and Assurance picks the work "
        "up again.")
    # a non-loopback template is ignored, never followed
    bad = wc.waiting_note({"roster": {"Assurance": "ag-1"},
                           "question_wait_sec": 900,
                           "thread_url_template": "https://chat.example/t/{thread}"},
                          "mcp:a-1")
    assert bad == plain
    # no roster entry for this agent -> the generic name; minutes follow the key
    generic = wc.waiting_note({"roster": {}, "question_wait_sec": 1200}, "t-1")
    assert generic.startswith("[t2-carrier] The teammate, an AI teammate,")
    assert "within 20 minutes" in generic and "http" not in generic
    assert generic.endswith("The teammate picks the work up again.")


def test_thread_url_template_law():
    tpl = "http://localhost:3939/team/{thread}"
    assert wc.thread_url(tpl, "run:th:1") == \
        "http://localhost:3939/team/run%3Ath%3A1"
    assert wc.thread_url(None, "t") is None
    assert wc.thread_url(tpl, None) is None
    assert wc.thread_url("https://127.0.0.1:80/{thread}", "t") is None
    assert wc.thread_url("http://127.0.0.1.evil.test:80/{thread}", "t") is None
    assert wc.thread_url("http://127.0.0.1:3774/thread/", "t") is None
    assert wc.thread_url("http://127.0.0.1:3774/{thread}/{thread}", "t") is None
    # the port must be followed by a "/", exactly as issue_link demands: a
    # userinfo trick would otherwise smuggle a real foreign host through
    assert wc.thread_url("http://127.0.0.1:80@example.com/{thread}", "t") is None


def test_feedback_round_waits_with_the_question_too():
    # Rule B on the board-feedback path, including the bound in_review route
    # that runs before run_carrier's try block: the waiting line is posted
    # there too.
    op = fb_op()
    pc = FakePaperclip(issues=feedback_issue())
    pc.comment_rows["is-1"] = [
        {"body": "answer v1", "authorType": "agent"},
        {"body": "the numbers were wrong", "authorType": "user"}]
    pc.interaction_rows = [
        {"kind": "request_confirmation", "status": "rejected",
         "result": {"reason": "line count is off"}}]
    asked = [("user", "r1", f"[{op}-rev1]\n\nboard declined")]
    answered = asked + [("assistant", "r1", "answer v2, now correct")]
    t3 = ScriptedT3(states=[
        (th(pending=0), [("user", "r0", f"[{op}]\n\nthe task"),
                         ("assistant", "r0", "answer v1")]),
        (th(active="r1", latest="r1", pending=1), asked),
        (th(latest="r1", pending=0), answered),
    ], ask_on_send=True)
    opts = wait_opts(Clock(), t3)
    assert run_bound(pc, t3, opts) == 0
    assert len(t3.sends) == 1 and f"[{op}-rev1]" in t3.sends[0]
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies[0] == wc.waiting_note(opts, "th-1")
    assert bodies[1:] == ["answer v2, now correct"]
    assert pc.issues["is-1"]["status"] == "in_review"


def test_return_wake_waits_with_the_question_too():
    # Rule B on the issue_blockers_resolved return path.
    issues, ask_op, child = blocked_parent_with_done_child()
    ret_op = f"{ask_op}-ret"
    pc = FakePaperclip(issues=issues)
    pc.child_rows["is-1"] = [dict(child)]
    # the child's answer is the assignee's own comment (R2a finding 17)
    pc.comment_rows["ch-1"] = [{"body": "t45_alpha.txt has 12 lines",
                                "authorType": "agent",
                                "author": {"id": "ag-atlas"}}]
    asked = [("user", "r1", f"[{ret_op}]\n\nthe ask came back")]
    answered = asked + [("assistant", "r1", "FINAL: the file has 12 lines")]
    t3 = ScriptedT3(states=[
        (th(pending=0), []),
        (th(active="r1", latest="r1", pending=1), asked),
        (th(latest="r1", pending=0), answered),
    ], ask_on_send=True)
    opts = wait_opts(Clock(), t3)
    assert run_with_roster(pc, t3, {}, opts) == 0
    assert len(t3.sends) == 1 and f"[{ret_op}]" in t3.sends[0]
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert bodies[0] == wc.waiting_note(opts, "th-1")
    assert bodies[1:] == ["FINAL: the file has 12 lines"]


def test_mid_turn_text_is_never_delivered_mas9():
    # Fault 2 exactly as it happened (MAS-9): assistant text of the marker's
    # run exists, the run is still active with a question waiting. Nothing is
    # delivered; the run stays with the question to its deadline.
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    msgs = [("user", "r1", f"[{op}]\n\nthe task"),
            ("assistant", "r1", "I've exhausted every reachable source")]
    t3 = ScriptedT3(states=[(th(active="r1", latest="r1", pending=1), msgs)])
    pc = FakePaperclip(issues={
        "is-1": {"identifier": "MMO-1", "status": "in_progress",
                 "title": "Summarize file X",
                 "description": "Write a three-line summary."}})
    opts = wait_opts(Clock(), t3, question_wait_sec=30)
    with pytest.raises(wc.NeedsHuman):
        run(pc, t3, opts)
    assert t3.sends == []
    bodies = [c[2] for c in pc.calls if c[0] == "comment"]
    assert len(bodies) == 1 and bodies[0] == wc.waiting_note(opts, "th-1")
    assert "exhausted every reachable source" not in "".join(bodies)
    assert pc.issues["is-1"]["status"] == "in_progress"


def test_nothing_is_sent_while_a_question_waits_and_the_note_is_said_once():
    # Faults 1 and 3 (MAS-9): while a question waits nothing is sent, the
    # waiting line is said once, and the deadline leaves the issue in_progress.
    # The carrier used to exit at once; it now stays with the question, so
    # the clock and sleep are injected and the wait is bounded by
    # question_wait_sec.
    pc = FakePaperclip(issues=one_issue())
    t3 = ScriptedT3(states=[(th(active="r0", latest="r0", pending=1),
                             [("user", "r0", "an older question")])])
    opts = wait_opts(Clock(), t3, question_wait_sec=60)
    for _ in range(3):
        with pytest.raises(wc.NeedsHuman):
            run(pc, t3, opts)
    assert t3.sends == []
    notes = [c for c in pc.calls if c[0] == "comment"]
    assert len(notes) == 1 and notes[0][2] == wc.waiting_note(opts, "th-1")
    # once the question is answered the task goes out exactly once
    t3.states.append((th(latest="r0", pending=0),
                      [("user", "r0", "an older question"),
                       ("assistant", "r0", "asked and answered")]))
    assert run(pc, t3, opts) == 0
    assert len(t3.sends) == 1


def test_waiting_note_is_repeated_after_the_board_writes():
    pc = FakePaperclip(issues=one_issue())
    t3 = ScriptedT3(states=[(th(active="r0", latest="r0", pending=1),
                             [("user", "r0", "an older question")])])
    opts = wait_opts(Clock(), t3, question_wait_sec=60)
    with pytest.raises(wc.NeedsHuman):
        run(pc, t3, opts)
    pc.comment_rows["is-1"].append({"body": "any news?", "authorType": "user"})
    with pytest.raises(wc.NeedsHuman):
        run(pc, t3, opts)
    assert [c[2] for c in pc.calls if c[0] == "comment"] == \
        [wc.waiting_note(opts, "th-1")] * 2


# --- the run options come from one place (config file + environ) -------------

def test_build_opts_maps_every_key_and_reads_the_door_from_config_only():
    # Item 4: one function builds the opts. The coding-job door comes from
    # the CONFIG FILE only — absent means dormant, exactly as before — and
    # every other key keeps its default when the config does not carry it.
    cfg = {
        "pending_timeout_sec": 700, "poll_interval_sec": 6,
        "question_wait_sec": 800, "run_budget_sec": 1300,
        "question_poll_interval_sec": 12,
        "teammates": {"Assurance": "ag-1"},
        "issue_url_template": "http://127.0.0.1:3100/MAS/issues/{identifier}",
        "thread_url_template": "http://127.0.0.1:3780/x/{thread}",
        "coding_job_door": "/path/to/door.sock",
    }
    opts = wc.build_opts(cfg, {"MMOS_T2_CARRIER_CRASH_AFTER": "pre-comment"},
                         1234.5)
    assert opts == {
        "crash_after": "pre-comment",
        "pending_timeout_sec": 700,
        "poll_interval_sec": 6,
        "question_wait_sec": 800,
        "run_budget_sec": 1300,
        "question_poll_interval_sec": 12,
        "roster": {"Assurance": "ag-1"},
        "max_asks_per_issue": 3,
        "issue_url_template": "http://127.0.0.1:3100/MAS/issues/{identifier}",
        "thread_url_template": "http://127.0.0.1:3780/x/{thread}",
        "coding_job_door": "/path/to/door.sock",
        "run_start": 1234.5,
        "delivery_reserve_sec": 120,
    }
    # an empty config: every default, and the door stays dormant
    minimal = wc.build_opts({}, {}, 0.0)
    assert minimal == {
        "crash_after": None,
        "pending_timeout_sec": 600,
        "poll_interval_sec": 5,
        "question_wait_sec": 900,
        "run_budget_sec": 1320,
        "question_poll_interval_sec": 10,
        "roster": {},
        "max_asks_per_issue": 3,
        "issue_url_template": None,
        "thread_url_template": None,
        "coding_job_door": None,
        "run_start": 0.0,
        "delivery_reserve_sec": 120,
    }
    # the door never comes from the environment
    env_door = wc.build_opts({}, {"coding_job_door": "/env/door.sock"}, 0.0)
    assert env_door["coding_job_door"] is None


# --- item 8: the three behaviors named untested in the first return ---------
#
# Task 1 implemented these; no test proved them. They pin the behavior, not
# a change: a reader that fails once or twice must not end a wait, three in a
# row must; the run budget caps the slow-turn wait too; and a stay that
# already sent once never sends again when the marker fails to appear.

class GlitchT3(ScriptedT3):
    """A scripted thread whose reads raise CarrierError for the first
    `glitches` calls (a transient t3 failure), then serve the states."""

    def __init__(self, states, glitches=0, **kw):
        super().__init__(states, **kw)
        self.glitches = glitches
        self.failed_reads = 0

    def messages(self, count=60):
        if self.glitches > 0:
            self.glitches -= 1
            self.failed_reads += 1
            raise wc.CarrierError("t3 thread show failed (exit 1): glitch")
        return super().messages(count)


def test_question_wait_survives_two_failed_reads():
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    asked = [("user", "r1", f"[{op}]\n\nthe task"),
             ("assistant", "r1", "mid-turn prose")]
    answered = asked + [("assistant", "r1", "the final answer")]
    t3 = GlitchT3(states=[(th(active="r1", latest="r1", pending=1), asked),
                          (th(latest="r1", pending=0), answered)], glitches=2)
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(), t3)
    assert wc.stay_with_question(pc, t3, pc.issue("is-1"), op, opts) == \
        "the final answer"


def test_question_wait_fails_after_three_reads_in_a_row():
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    asked = [("user", "r1", f"[{op}]\n\nthe task")]
    t3 = GlitchT3(states=[(th(active="r1", latest="r1", pending=1), asked)],
                  glitches=99)
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(), t3)
    with pytest.raises(wc.CarrierError):
        wc.stay_with_question(pc, t3, pc.issue("is-1"), op, opts)
    assert t3.failed_reads == 3  # exactly three strikes, not fewer


def test_run_budget_caps_wait_for_reply_too():
    # The slow-turn wait ends at the earlier of pending_timeout_sec and the
    # run budget: here 50s of budget against a 600s timeout.
    op = "pc-is-1-budget"
    t3 = ScriptedT3(states=[(th(latest="r1", pending=0),
                             [("user", "r1", f"[{op}]\n\nthe task")])])
    clock = Clock(1000.0)

    def nap(seconds):
        clock.nap(seconds)
        t3.nap(seconds)
    opts = {"clock": clock.time, "sleep": nap, "pending_timeout_sec": 600,
            "poll_interval_sec": 10, "run_budget_sec": 50, "run_start": 1000.0}
    with pytest.raises(wc.CarrierError):
        wc.wait_for_reply(t3, op, opts)
    # R2a finding 8 (addition) changed this end: the wait now stops at budget
    # end minus the 120s delivery reserve (930), and a 50s budget is smaller
    # than the reserve — so no wait happens at all. A budget that cannot
    # leave room to deliver is not spent on waiting.
    assert clock.now == 1000.0


def test_stay_never_sends_again_when_the_marker_fails_to_appear():
    # The hardening of rule B: when the thread's story is inconsistent (sends
    # stop on a question but the marker never shows, and no question waits
    # afterwards), a stay sends at most once itself — the outer send plus the
    # stay's own, never a third.
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    q1 = [("user", "r9", "unrelated question")]
    a1 = q1 + [("assistant", "r9", "unrelated answer")]
    t3 = ScriptedT3(states=[
        (th(pending=0), []),                              # before the send
        (th(active="r9", latest="r9", pending=1), q1),    # the send asked
        (th(latest="r9", pending=0), a1),                 # answered, no marker
        (th(latest="r10", pending=0), a1),                # still no marker
    ], ask_on_send=True)
    pc = FakePaperclip(issues=one_issue())
    opts = wait_opts(Clock(), t3, question_wait_sec=30)
    with pytest.raises(wc.NeedsHuman):
        run(pc, t3, opts)
    assert len(t3.sends) == 2              # one outer, one from the stay
    assert pc.issues["is-1"]["status"] == "in_progress"  # nothing released


# --- R2a finding 2: the marker is the FIRST LINE of a user message ------------

def test_marker_only_counts_as_the_first_line_of_a_user_message():
    # The carrier always writes the marker as the very first line of its
    # message ("[op]\n\n..."). A marker that appears anywhere else — quoted by
    # the teammate, inside a side message — is someone's words, never a task.
    op = "pc-is-1-aaaabbbbcc"
    real = wc.build_message("MMO-1", "the title", "the body", op)
    quoted = ("you were asked before:\n\n" + real + "\n\nplease redo it")
    msgs = [("user", "r1", real),
            ("assistant", "r1", "the real answer"),
            ("user", "r2", quoted),
            ("assistant", "r2", "answer for the quoter")]
    # the first real marker's answer wins; the quoted one never replaces it
    assert wc.scan_marker(msgs, op) == ("reply", "the real answer")
    # a marker that appears ONLY in someone else's words never counts at all
    only_quoted = [("user", "r9", "earlier I saw [pc-x-1] go by"),
                   ("assistant", "r9", "not a task")]
    assert wc.scan_marker(only_quoted, "pc-x-1") == (None, None)
    # a marker glued to text on the same first line is not the carrier's shape
    space = [("user", "r1", f"[{op}] the task on one line"),
             ("assistant", "r1", "answer")]
    assert wc.scan_marker(space, op) == (None, None)
    # FIRST marker wins when two real-shaped markers exist (rule: never the
    # later turn's text)
    two = [("user", "r1", real), ("assistant", "r1", "first answer"),
           ("user", "r2", real), ("assistant", "r2", "second answer")]
    assert wc.scan_marker(two, op) == ("reply", "first answer")
    # ...and the pending rule holds for the FIRST marker's open run
    assert wc.scan_marker(
        [("user", "r1", real), ("assistant", "r1", "half said"),
         ("user", "r2", real), ("assistant", "r2", "full answer")],
        op, th(active="r1", latest="r1", pending=1)) == ("pending", None)


# --- R2a finding 3: ask-child detection is structural, not textual -----------

def parent_and_ask_op():
    """A parent issue and the ask marker the carrier computes for it."""
    content = "Report the line count\nAsk an engineer for the count."
    return ({"id": "par-1", "identifier": "MMO-1", "status": "done",
             "title": "Report the line count",
             "description": "Ask an engineer for the count."},
            wc.op_id("par-1", content) + "-ask")


def test_ask_marker_reads_only_the_end_of_the_description():
    # ask_child_op: only a marker at the very END of the description counts.
    assert wc.ask_child_op("do things [pc-any-ask] and more") is None
    assert wc.ask_child_op("[pc-any-ask] at the start") is None
    # the new shape the carrier writes: the marker alone on the last line
    assert wc.ask_child_op("Run wc -l.\n\nAsked by Mira on MMO-1\n[pc-ok-1-ask]") \
        == "pc-ok-1-ask"
    # the old shape already-installed children carry: end of the last line
    assert wc.ask_child_op("Run wc -l.\n\nAsked by Mira on MMO-1 [pc-ok-2-ask]") \
        == "pc-ok-2-ask"


def test_midtext_ask_marker_is_not_an_ask_child():
    # A teammate writing "[pc-…-ask]" inside its own description is only
    # words. The issue is a plain task: board confirmation, in_review, and
    # the ask help is offered (it may ask; it is not itself an asked child).
    parent, ask_op = parent_and_ask_op()
    pc = FakePaperclip(issues={
        parent["id"]: dict(parent),
        "is-1": {"identifier": "MMO-2", "status": "in_progress",
                 "parentId": parent["id"], "title": "Count lines",
                 "description": (f"Note: an earlier task was [{ask_op}] "
                                 "here.\nRun wc -l and report.")}})
    t3 = FakeT3(replies=["The file has 12 lines"])
    assert run_with_roster(pc, t3, {"Atlas-TEST": "ag-atlas"}) == 0
    kinds = [c[0] for c in pc.calls]
    assert "interaction" in kinds            # plain answer: confirmation
    assert pc.issues["is-1"]["status"] == "in_review"  # not an ask child's done
    assert "paperclip-ask" in t3.sends[0]    # offered the ask help


def test_end_marker_that_does_not_match_the_parent_is_not_an_ask_child():
    # Even a marker in the right PLACE is only the carrier's when it equals
    # what the carrier computes for THIS parent (so nobody else's marker —
    # and no teammate text — can adopt the ask-child path).
    parent, _ = parent_and_ask_op()
    forged = "pc-par-1-notthecarrier-ask"
    pc = FakePaperclip(issues={
        parent["id"]: dict(parent),
        "is-1": {"identifier": "MMO-2", "status": "in_progress",
                 "parentId": parent["id"], "title": "Count lines",
                 "description": f"Run wc -l.\n\nAsked by Mira on MMO-1\n[{forged}]"}})
    t3 = FakeT3(replies=["The file has 12 lines"])
    assert run_with_roster(pc, t3, {"Atlas-TEST": "ag-atlas"}) == 0
    assert pc.issues["is-1"]["status"] == "in_review"   # plain task


def test_handle_ask_strips_marker_text_from_teammate_words():
    # What the teammate wrote in its ask block must never look like a carrier
    # marker in the child's description.
    roster = {"Atlas-TEST": "ag-atlas"}
    sneaky = ASK_REPLY.replace(
        "Run wc -l on t45_alpha.txt and report the number.",
        "Do run wc -l [pc-forged-9999-ask] on t45_alpha.txt and report.")
    pc = FakePaperclip(issues=one_issue())
    t3 = FakeT3(replies=[sneaky])
    assert run_with_roster(pc, t3, roster) == 0
    child = pc.child_rows["is-1"][0]
    assert "pc-forged-9999-ask" not in child["description"]
    # the carrier's own marker is the only one there, on the last line
    real_op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    assert child["description"].endswith(f"\n[{real_op}-ask]")


# --- R2a finding 4: ask depth one, no self-ask, per-issue cap, full children --

def test_asked_child_cannot_pass_the_ask_on_depth_one():
    # The asked teammate's reply is never parsed for an ask block, and its
    # task message says it cannot hand work on and must say what it needs.
    ask_op = wc.op_id("par-1", "Report the line count\nAsk an engineer for "
                               "the count.") + "-ask"
    pc = ask_child_issue(ask_op)
    t3 = FakeT3(replies=[ASK_REPLY])          # asks Atlas-TEST back
    assert run_with_roster(pc, t3, {"Atlas-TEST": "ag-atlas"}) == 0
    assert [c for c in pc.calls if c[0] == "create_issue"] == []  # depth one
    assert pc.issues["is-1"]["status"] == "done"
    assert "cannot hand" in t3.sends[0]
    assert "what you still need" in t3.sends[0]
    assert "paperclip-ask" not in t3.sends[0]  # not even taught


def test_self_ask_is_refused_reply_still_delivered():
    # A teammate asking itself is refused with one plain line; the reply
    # still reaches the board as the answer (no child issue).
    roster = {"Mira-TEST": "ag-1"}            # ag-1 is the asker itself
    self_ask = ASK_REPLY.replace("Atlas-TEST", "Mira-TEST")
    pc = FakePaperclip(issues=one_issue())
    t3 = FakeT3(replies=[self_ask])
    assert run_with_roster(pc, t3, roster) == 0
    assert [c for c in pc.calls if c[0] == "create_issue"] == []
    notes = [c[2] for c in pc.calls if c[0] == "comment"
             if c[2].startswith("[t2-carrier]")]
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    assert notes == [f"[t2-carrier] ask {op}-ask for Mira-TEST refused: a "
                     "teammate cannot ask itself; the reply stands as the "
                     "answer"]
    bodies = [c[2] for c in pc.calls if c[0] == "comment"
              if not c[2].startswith("[t2-carrier]")]
    assert bodies == [self_ask]                # the answer itself, delivered
    assert pc.issues["is-1"]["status"] == "in_review"


def test_ask_cap_default_three_refuses_the_fourth():
    # Three ask children already hang off this issue (different content
    # revisions, so three different markers). The fourth ask is refused with
    # one plain line; the reply is delivered as the plain answer.
    roster = {"Atlas-TEST": "ag-atlas"}
    pc = FakePaperclip(issues=one_issue())
    pc.child_rows["is-1"] = [
        {"id": f"ch-{n}", "identifier": f"MMO-{n}", "parentId": "is-1",
         "assigneeAgentId": "ag-atlas", "title": f"Ask {n}", "status": "done",
         "description": f"Asked by Mira on MMO-1\n[pc-is-1-{'a' * 9}{n}-ask]"}
        for n in (1, 2, 3)]
    t3 = FakeT3(replies=[ASK_REPLY])
    assert run_with_roster(pc, t3, roster) == 0
    assert [c for c in pc.calls if c[0] == "create_issue"] == []
    notes = [c[2] for c in pc.calls if c[0] == "comment"
             if c[2].startswith("[t2-carrier]")]
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    assert notes == [f"[t2-carrier] ask {op}-ask for Atlas-TEST refused: the "
                     "per-issue ask cap (3) is already reached; the reply "
                     "stands as the answer"]
    assert pc.issues["is-1"]["status"] == "in_review"


def test_children_pages_past_the_first_page():
    # The old single 50-row request hid older children. The client now asks
    # for a full page and walks `offset` while the server keeps returning a
    # full page (the real list serves `limit` up to 1000 and honors it).
    calls = []

    class PagedClient(wc.PaperclipClient):
        def __init__(self, n):
            super().__init__("http://127.0.0.1:1", "tok", "run-1")
            self.rows = [{"id": f"c{i}", "parentId": "is-1"} for i in range(n)]

        def _request(self, method, path, body=None):
            calls.append(path)
            limit = int(path.split("limit=")[1].split("&")[0])
            offset = int(path.split("offset=")[1])
            return self.rows[offset:offset + limit]
    # 53 children: one page when the page is 1000 — but the request must not
    # stop at the old 50
    calls.clear()
    rows = PagedClient(53).children("is-1")
    assert len(rows) == 53
    assert "limit=1000" in calls[0]
    # 2500 children: the offset walk follows the pages to the end
    calls.clear()
    rows = PagedClient(2500).children("is-1")
    assert len(rows) == 2500
    assert len(calls) == 3                      # 1000 + 1000 + 500
    assert "offset=1000" in calls[1] and "offset=2000" in calls[2]


# --- R2a finding 6: no blind retries of creates; lost answers read back -------

def test_http_retries_skip_posts(monkeypatch):
    # Only GET/PUT/PATCH are retried. A POST (a create) fails fast: retrying
    # it blind is how duplicate children and duplicate interactions happen.
    import urllib.error
    calls = []
    monkeypatch.setattr(wc.time, "sleep", lambda s: None)

    def flaky(req, timeout=None):
        calls.append(req.get_method())
        raise urllib.error.HTTPError(req.full_url, 503, "unavailable",
                                     hdrs=None, fp=None)
    monkeypatch.setattr(wc.urllib.request, "urlopen", flaky)
    pc = wc.PaperclipClient("http://127.0.0.1:1", "tok", "run-1")
    with pytest.raises(wc.CarrierError):
        pc._request("GET", "/api/x")
    assert calls.count("GET") == 3          # read retried
    calls.clear()
    with pytest.raises(wc.CarrierError):
        pc._request("POST", "/api/x", body={})
    assert calls.count("POST") == 1         # create fails fast


def test_failed_ask_create_reads_children_back_before_failing():
    # The child-issue POST executed on the server but its answer was lost.
    # The carrier reads the children back for its marker and finishes the
    # ask cleanly instead of failing the run.
    roster = {"Atlas-TEST": "ag-atlas"}
    pc = FakePaperclip(issues=one_issue())
    real_create = pc.create_issue
    armed = {"lost": False}

    def create_lost_answer(company_id, payload):
        row = real_create(company_id, payload)   # the server did execute
        if not armed["lost"]:
            armed["lost"] = True
            raise wc.CarrierError(
                "POST /api/companies/co-1/issues -> HTTP 503 lost")
        return row
    pc.create_issue = create_lost_answer
    t3 = FakeT3(replies=[ASK_REPLY])
    assert run_with_roster(pc, t3, roster) == 0
    assert pc.issues["is-1"]["status"] == "blocked"   # the ask was placed
    assert len([c for c in pc.calls if c[0] == "create_issue"]) == 1


def test_confirmation_409_for_this_op_is_success():
    # Another run posted this op's confirmation between our read and our
    # POST. The 409 reads back as "already exists for THIS op": delivery
    # continues; the issue is not released.
    content = "Summarize file X\nWrite a three-line summary."
    op = wc.op_id("is-1", content)
    pc = FakePaperclip(issues={"is-1": {"identifier": "MMO-1",
                                        "status": "in_progress",
                                        "title": "Summarize file X",
                                        "description": "Write a three-line summary."}})
    pc.interaction_rows = [{"id": "ix-1", "kind": "request_confirmation",
                            "status": "pending",
                            "idempotencyKey": f"{op}-confirm"}]
    reads = []

    def blind_once(issue_id):
        reads.append(1)
        if len(reads) == 1:
            return []                      # deliver's pre-check saw nothing
        return [dict(r) for r in pc.interaction_rows]
    pc.interactions = blind_once
    wc.deliver(pc, pc.issue("is-1"), "the answer", op)
    assert pc.issues["is-1"]["status"] == "in_review"   # delivered, not failed
    assert not any("did not complete" in (c[2] if c[0] == "comment" else "")
                   for c in pc.calls)


class _StubResponse:
    """Minimal http.client-style response for the opener chain."""

    def __init__(self, code, headers=None, body=b""):
        self.code = code
        self.status = code
        self.msg = "stub"
        self._headers = dict(headers or {})
        self.headers = self._headers
        self._body = body

    def info(self):
        return self._headers

    def read(self, n=-1):
        return self._body

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_redirect_is_refused_and_token_never_leaves_base(monkeypatch):
    # Finding 23: the per-run bearer token must never leave the pinned
    # loopback base. urllib's default opener follows 3xx and re-sends the
    # Authorization header to the Location target. The client must use an
    # opener that refuses every redirect: a 3xx becomes an HTTPError, so the
    # existing error path raises CarrierError, and nothing is re-sent.
    import urllib.request

    seen = []

    class StubHandler(urllib.request.BaseHandler):
        handler_order = 100

        def http_open(self, req):
            seen.append(req.full_url)
            if len(seen) == 1:
                return _StubResponse(
                    302, {"location": "http://evil.example/steal"})
            return _StubResponse(200, {}, b"{}")

    stub = StubHandler()
    # Drive whichever opener the client actually uses: its own (after the
    # fix) or urllib's default (the defect).
    if getattr(wc, "_OPENER", None) is not None:
        monkeypatch.setattr(
            wc, "_OPENER",
            urllib.request.build_opener(wc._NoRedirect(), stub))
    else:
        monkeypatch.setattr(
            urllib.request, "_opener", urllib.request.build_opener(stub))

    pc = wc.PaperclipClient("http://127.0.0.1:9", "tok-secret", "run-1")
    raised = None
    try:
        pc._request("GET", "/api/x")
    except wc.CarrierError as exc:
        raised = exc
    # Exactly one request, to the original url. Nothing re-sent to Location.
    assert seen == ["http://127.0.0.1:9/api/x"]
    assert raised is not None, "a 3xx must raise CarrierError, not be followed"
    assert "HTTP 302" in str(raised)


def test_comment_read_failure_fails_before_anything_is_posted():
    # R2a finding 20: a failed comments read used to answer False ("not
    # posted yet"), so deliver went on to POST the answer — and a comment
    # POST is unkeyed, so a read failure that hid an already-posted answer
    # turned into a duplicate. The read failure must fail the run before
    # anything is posted.
    pc = FakePaperclip(issues=one_issue())

    def unreadable(issue_id):
        raise wc.CarrierError(
            "GET /api/issues/is-1/comments -> HTTP 503 unreadable")
    pc.comments = unreadable
    with pytest.raises(wc.CarrierError):
        wc.deliver(pc, pc.issue("is-1"), "the answer", "pc-is-1-aaaaa")
    # Nothing was posted at all: no comment, no confirmation, no status write.
    assert pc.calls == []


def test_delivery_reserve_is_stated_and_shortens_wait_deadlines():
    # R2a finding 8 (addition): the run budget keeps a stated reserve for
    # delivery. Every wait deadline stops that much earlier than the budget
    # end: budget ends at 1100, reserve 120 -> the question wait may not run
    # past 980 even though question_wait_sec would allow 1900.
    opts = {"clock": lambda: 1000.0, "question_wait_sec": 900,
            "run_budget_sec": 100, "run_start": 1000.0,
            "delivery_reserve_sec": 120}
    assert wc.question_wait_deadline(opts) == 980.0
    # The default reserve (120) applies when the config says nothing.
    opts2 = {"clock": lambda: 1000.0, "question_wait_sec": 900,
             "run_budget_sec": 100, "run_start": 1000.0}
    assert wc.question_wait_deadline(opts2) == 980.0


def test_run_budget_reserve_caps_wait_for_reply():
    # The slow-turn wait stops at budget end minus the same stated reserve:
    # budget 200s -> the wait ends at 1080, not 1200.
    op = "pc-is-1-res"
    t3 = ScriptedT3(states=[(th(latest="r1", pending=0),
                             [("user", "r1", f"[{op}]\n\nthe task")])])
    clock = Clock(1000.0)

    def nap(seconds):
        clock.nap(seconds)
        t3.nap(seconds)
    opts = {"clock": clock.time, "sleep": nap, "pending_timeout_sec": 600,
            "poll_interval_sec": 10, "run_budget_sec": 200, "run_start": 1000.0}
    with pytest.raises(wc.CarrierError):
        wc.wait_for_reply(t3, op, opts)
    assert clock.now == 1080.0  # budget end 1200 minus the 120s delivery reserve


def test_http_timeout_and_retry_sleep_capped_by_remaining_budget(monkeypatch):
    # R2a finding 8 (addition): every HTTP timeout and every retry sleep is
    # capped by what is left of the run budget before the delivery reserve.
    # With 2s left: the 30s stock timeout becomes 2s and the second retry's
    # 3s sleep becomes 2s. The floor of 1s keeps delivery itself alive when
    # the reserve is being spent.
    import urllib.error
    caps, sleeps, attempts = [], [], {"n": 0}
    monkeypatch.setattr(wc.time, "sleep", lambda s: sleeps.append(s))

    def flaky(req, timeout=None):
        attempts["n"] += 1
        caps.append(timeout)
        if attempts["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "unavailable",
                                         hdrs=None, fp=None)
        return _StubResponse(200, {}, b"{}")
    monkeypatch.setattr(wc.urllib.request, "urlopen", flaky)
    pc = wc.PaperclipClient("http://127.0.0.1:1", "tok", "run-1",
                            budget_left=lambda: 2.0)
    assert pc._request("GET", "/api/x") == {}
    assert caps == [2, 2, 2]
    assert sleeps == [1.5, 2.0]


def test_t3_send_timeout_comes_from_the_run_budget(monkeypatch, tmp_path):
    # R2a finding 8: the t3 CLI subprocess timeout is not a free-standing
    # 1200s — it is capped by what is left of the run budget before the
    # delivery reserve, and never above the stock 1200s.
    seen = []

    class FakeProc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(argv, **kw):
        seen.append(kw.get("timeout"))
        return FakeProc()
    monkeypatch.setattr(wc.subprocess, "run", fake_run)
    t3 = wc.T3Thread("/bin/true", str(tmp_path), "th-1", str(tmp_path),
                     budget_left=lambda: 77.0)
    t3._run([])
    assert seen == [77]
    t3b = wc.T3Thread("/bin/true", str(tmp_path), "th-1", str(tmp_path),
                      budget_left=lambda: 9999.0)
    t3b._run([])
    assert seen == [77, 1200]  # the stock cap still applies


def test_public_error_strips_bodies_and_stderr():
    # R2a finding 13: what goes ON an issue as a failure note is the error
    # type and its status line only. HTTP error bodies (server text) and the
    # t3 command's stderr never belong on a person's board; the full message
    # still goes to the carrier log.
    http = wc.CarrierError(
        "POST /api/issues/is-1/comments -> HTTP 503 "
        "{\"error\":\"internal SECRET-BODY boom\"}")
    assert wc.public_error(http) == \
        "CarrierError: POST /api/issues/is-1/comments -> HTTP 503"
    t3err = wc.CarrierError(
        "t3 thread send failed (exit 1): BOOM-STDERR-TEXT "
        "with task words in it")
    assert wc.public_error(t3err) == \
        "CarrierError: t3 thread send failed (exit 1)"
    unreachable = wc.CarrierError("GET /api/x unreachable: connection refused")
    assert wc.public_error(unreachable) == \
        "CarrierError: GET /api/x unreachable: connection refused"


def test_release_note_on_a_failed_run_carries_no_error_body():
    # A failed run still leaves its one release note, but the note carries
    # the type and status only — not the t3 stderr the failure wrapped.
    pc = FakePaperclip(issues=one_issue())

    class ExplodingT3(FakeT3):
        def send(self, message):
            raise wc.CarrierError(
                "t3 thread send failed (exit 1): BOOM-STDERR-WORDS")
    with pytest.raises(wc.CarrierError):
        run(pc, ExplodingT3(replies=[]))
    notes = [c for c in pc.calls if c[0] == "comment"]
    assert notes, "the release note was posted"
    assert all("BOOM-STDERR-WORDS" not in c[2] for c in notes)
    assert any("exit 1" in c[2] for c in notes)


def test_base_is_pinned_by_the_config_and_loopback_only():
    # R2a finding 13: the carrier's Paperclip address comes from the config
    # (paperclip_base, loopback only). A PAPERCLIP_API_URL that differs from
    # the pinned base is refused before any request is made.
    cfg = {"paperclip_base": "http://127.0.0.1:3100"}
    assert wc.base_pin_error(cfg, {"PAPERCLIP_API_URL":
                                   "http://127.0.0.1:3100"}) is None
    assert wc.base_pin_error(cfg, {"PAPERCLIP_API_URL":
                                   "http://127.0.0.1:3100/"}) is None
    assert wc.base_pin_error(cfg, {"PAPERCLIP_API_URL":
                                   "http://127.0.0.1:9999"}) is not None
    # a non-loopback base is refused even when the env agrees with it
    bad = wc.base_pin_error({"paperclip_base": "http://10.0.0.5:3100"},
                            {"PAPERCLIP_API_URL": "http://10.0.0.5:3100"})
    assert bad is not None and "loopback" in bad
    # no pinned base in the config: nothing to compare, as before
    assert wc.base_pin_error({}, {"PAPERCLIP_API_URL":
                                  "http://127.0.0.1:3100"}) is None


def test_return_edge_on_an_ask_child_completes_done():
    # R2a finding 5: the asker here is ITSELF an ask child (of gp-1). Its
    # return-edge delivery must carry the ask-child flag: done, no board
    # confirmation — so the grandparent's blocker resolves. Without the flag
    # the child goes in_review and the asker above stays blocked until the
    # board accepts.
    gp_marker = wc.op_id("gp-1", "Top task\nAsk someone mid-level.") + "-ask"
    par_desc = ("Ask an engineer for the count.\n\n"
                f"Asked by Mira on MMO-0\n[{gp_marker}]")
    ask_op = wc.op_id("is-1", "Report the line count\n" + par_desc) + "-ask"
    pc = FakePaperclip(issues={
        # the grandparent is itself blocked on is-1 (not ready, not this run's)
        "gp-1": {"identifier": "MMO-0", "status": "blocked",
                 "dependencyReady": False,
                 "title": "Top task",
                 "description": "Ask someone mid-level."},
        "is-1": {"identifier": "MMO-1", "status": "blocked",
                 "dependencyReady": True, "parentId": "gp-1",
                 "title": "Report the line count",
                 "description": par_desc,
                 "unblockDescriptor": {"owner": {"agentId": "ag-1"},
                                       "action": "Atlas completes MMO-2"}}})
    pc.child_rows["is-1"] = [{
        "id": "ch-1", "identifier": "MMO-2", "parentId": "is-1",
        "assigneeAgentId": "ag-atlas", "title": "Count lines",
        "status": "done",
        "description": f"Asked by Mira on MMO-1 [{ask_op}]"}]
    # the child's answer is the assignee's own comment (R2a finding 17)
    pc.comment_rows["ch-1"] = [{"body": "t45_alpha.txt has 12 lines",
                                "authorType": "agent",
                                "author": {"id": "ag-atlas"}}]
    ret_op = f"{ask_op}-ret"
    asked = [("user", "r1", f"[{ret_op}]\n\nthe ask came back")]
    answered = asked + [("assistant", "r1", "FINAL: the file has 12 lines")]
    t3 = ScriptedT3(states=[
        (th(pending=0), []),
        (th(latest="r1", pending=0), answered),
    ], ask_on_send=True)
    assert run_with_roster(pc, t3, {}, wait_opts(Clock(), t3)) == 0
    assert pc.issues["is-1"]["status"] == "done"          # not in_review
    assert [c for c in pc.calls if c[0] == "interaction"] == []  # no board gate


def test_feedback_edge_on_an_ask_child_completes_done():
    # R2a finding 5, feedback path: an ask child whose (pre-fix) answer sits
    # in in_review and was rejected. The revision delivery must carry the
    # ask-child flag: done, and no NEW confirmation — otherwise the child
    # re-enters review and the asker stays blocked on it.
    gp_marker = wc.op_id("gp-1", "Top task\nAsk someone mid-level.") + "-ask"
    child_desc = f"Run wc -l.\n\nAsked by Mira on MMO-0\n[{gp_marker}]"
    op = wc.op_id("is-1", "Count lines\n" + child_desc)
    pc = FakePaperclip(issues={
        "gp-1": {"identifier": "MMO-0", "status": "blocked",
                 "dependencyReady": False,
                 "title": "Top task", "description": "Ask someone mid-level."},
        "is-1": {"identifier": "MMO-2", "status": "in_review",
                 "parentId": "gp-1", "title": "Count lines",
                 "description": child_desc}})
    pc.interaction_rows = [
        {"id": "ix-1", "kind": "request_confirmation", "status": "rejected",
         "idempotencyKey": f"{op}-confirm",
         "result": {"reason": "the count is wrong"}}]
    pc.comment_rows["is-1"] = [
        {"body": "the count is 10", "authorType": "agent", "createdAt": "1"},
        {"body": "No: it is 12.", "authorType": "user", "createdAt": "2"}]
    rev = f"{op}-rev1"
    asked = [("user", "r1", f"[{rev}]\n\nboard sent it back")]
    answered = asked + [("assistant", "r1", "FINAL: 12 lines")]
    t3 = ScriptedT3(states=[
        (th(pending=0), []),
        (th(latest="r1", pending=0), answered),
    ], ask_on_send=True)
    assert run_bound(pc, t3, wait_opts(Clock(), t3)) == 0
    assert pc.issues["is-1"]["status"] == "done"   # re-done, not back in_review
    keys = [row["idempotencyKey"] for row in pc.interaction_rows]
    assert keys == [f"{op}-confirm"]        # no new confirmation for the round


def test_after_delivery_failure_never_changes_status():
    # R2a finding 22: the reply WAS delivered (comment + confirmation +
    # in_review). A later step — here the coding-job note after an
    # unreachable door — fails. The delivered answer stands: no release, no
    # status change, one machine note if it can be posted, and the run ends
    # 0.
    reply = ("The answer.\n\n```paperclip-coding-job\nkey: coding-job-1\n```")
    pc = FakePaperclip(issues=one_issue())
    real_add = pc.add_comment
    counter = {"n": 0}

    def add_twice_then_fail(issue_id, body):
        counter["n"] += 1
        if counter["n"] > 1:
            raise wc.CarrierError(
                "POST /api/issues/is-1/comments -> HTTP 503 later failure")
        return real_add(issue_id, body)
    pc.add_comment = add_twice_then_fail
    t3 = FakeT3(replies=[reply])
    opts = {"coding_job_door": "/nonexistent/door.sock"}
    assert run(pc, t3, opts) == 0
    assert pc.issues["is-1"]["status"] == "in_review"   # never moved back
    assert not any("did not complete" in (c[2] if c[0] == "comment" else "")
                   for c in pc.calls)


def test_output_block_with_words_after_the_fence_is_ignored():
    # R2a finding 27: an output block counts only when it ends the reply.
    # Words after the closing fence mean the teammate kept talking — the
    # block is not written as an issue document; the reply is still
    # delivered as a plain comment.
    block = "```paperclip-output\nkey: summary\ntitle: T\nline one\n```"
    assert wc.parse_output_block(
        block + "\nwait, that summary is wrong, ignore it") is None
    assert wc.parse_output_block(block)["key"] == "summary"
    assert wc.parse_output_block(block + "\n\n")["key"] == "summary"


def test_output_doc_key_is_ascii_identifier_only():
    # R2a finding 22: str.isalnum accepts accented letters ("café"); a
    # document key must be ASCII letters, digits, hyphen and underscore.
    assert wc.parse_output_block(
        "```paperclip-output\nkey: café\ntitle: T\nx\n```") is None
    assert wc.parse_output_block(
        "```paperclip-output\nkey: good-key_2\ntitle: T\nx\n```"
    )["key"] == "good-key_2"


def test_deliver_never_moves_a_done_or_cancelled_issue():
    # R2a finding 21: every status write reads the status first. A replay
    # wake on an issue the board already closed (done here, cancelled in the
    # second half) must not reopen it: the comment and the confirmation are
    # already there (dedupe), and the status write is skipped.
    op = "pc-is-1-done1"
    pc = FakePaperclip(issues={
        "is-1": {"identifier": "MMO-1", "status": "done",
                 "title": "Summarize file X",
                 "description": "Write a three-line summary."}})
    pc.comment_rows["is-1"] = [{"body": "the answer"}]
    pc.interaction_rows = [{"id": "ix-1", "kind": "request_confirmation",
                            "status": "pending",
                            "idempotencyKey": f"{op}-confirm"}]
    wc.deliver(pc, pc.issue("is-1"), "the answer", op)
    assert pc.issues["is-1"]["status"] == "done"
    assert [c for c in pc.calls if c[0] == "status"] == []

    pc2 = FakePaperclip(issues={
        "is-1": {"identifier": "MMO-1", "status": "cancelled",
                 "title": "Summarize file X",
                 "description": "Write a three-line summary."}})
    pc2.comment_rows["is-1"] = [{"body": "the answer"}]
    pc2.interaction_rows = [{"id": "ix-1", "kind": "request_confirmation",
                             "status": "pending",
                             "idempotencyKey": f"{op}-confirm"}]
    wc.deliver(pc2, pc2.issue("is-1"), "the answer", op)
    assert pc2.issues["is-1"]["status"] == "cancelled"
    assert [c for c in pc2.calls if c[0] == "status"] == []


def test_release_moves_only_in_progress_to_todo():
    # R2a finding 21: release_issue moves only in_progress -> todo. A done
    # or cancelled issue keeps its status; the note is still posted.
    pc = FakePaperclip(issues={
        "is-1": {"identifier": "MMO-1", "status": "done",
                 "title": "T", "description": "D"}})
    wc.release_issue(pc, "is-1", "CarrierError: x")
    assert pc.issues["is-1"]["status"] == "done"
    assert any(c[0] == "comment" for c in pc.calls)

    pc2 = FakePaperclip(issues={
        "is-1": {"identifier": "MMO-1", "status": "in_progress",
                 "title": "T", "description": "D"}})
    wc.release_issue(pc2, "is-1", "CarrierError: x")
    assert pc2.issues["is-1"]["status"] == "todo"


class WindowedT3(FakeT3):
    """Serves only the latest `count` messages, like the real thread read."""

    def messages(self, count=60):
        thread, msgs = super().messages(count)
        return thread, (list(msgs[-count:]) if count else [])


class BottomlessT3(FakeT3):
    """Never returns a short page: the lookback cannot prove absence."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._pad = 0

    def messages(self, count=60):
        thread, msgs = super().messages(count)
        while len(msgs) < count:
            self._pad += 1
            msgs = [("user", f"pad-{self._pad}",
                     f"older side message {self._pad}")] + list(msgs)
        return thread, list(msgs[-count:])


def test_marker_beyond_the_window_is_found_by_looking_back():
    # R2a finding 16: the thread read returns the latest 60 messages. Here
    # the task turn sits under 61 newer ones: a second wake used to miss the
    # marker and send the task again. The lookback walks back in steps, sees
    # the whole thread, finds the answered marker — no second send.
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    answer = "line1\nline2\nline3"
    msgs = [("user", "r1", f"[{op}]\n\nthe task"),
            ("assistant", "r1", answer)]
    side = [("user", f"s{i}", f"side message {i}") for i in range(61)]
    t3 = WindowedT3(messages=msgs + side)
    pc = FakePaperclip(
        issues=one_issue(), comments={"is-1": [{"body": answer}]},
        interactions=[{"id": "ix-1", "kind": "request_confirmation",
                       "status": "pending",
                       "idempotencyKey": f"{op}-confirm"}])
    assert run(pc, t3) == 0
    assert t3.sends == []                     # exactly no second send
    assert pc.issues["is-1"]["status"] == "in_review"


def test_window_exhausted_send_is_recorded_and_never_repeated():
    # R2a finding 16, the bound: t3 never serves a short page, so absence
    # cannot be proven. The first send is recorded on the issue; a second
    # wake sees the record and does not send again.
    op = wc.op_id("is-1", "Summarize file X\nWrite a three-line summary.")
    answer = "the answer"
    t3 = BottomlessT3()
    pc = FakePaperclip(issues=one_issue())
    assert run(pc, t3) == 0
    assert len(t3.sends) == 1
    records = [c for c in pc.calls if c[0] == "comment"
               and "sent task" in c[2]]
    assert len(records) == 1                  # the send record was posted

    # second wake: the answer is on the issue, the record names the send
    pc2 = FakePaperclip(
        issues={"is-1": {"identifier": "MMO-1", "status": "in_progress",
                         "title": "Summarize file X",
                         "description": "Write a three-line summary."}},
        comments={"is-1": [{"body": answer}]},
        interactions=[{"id": "ix-1", "kind": "request_confirmation",
                       "status": "pending",
                       "idempotencyKey": f"{op}-confirm"}])
    pc2.comment_rows["is-1"].append({"body": records[0][2]})
    t3_second = BottomlessT3(messages=[("user", "r1", t3.sends[0]),
                                       ("assistant", "r1", answer)])
    assert run(pc2, t3_second) == 0
    assert t3_second.sends == []              # the record stopped the resend


def test_return_marker_beyond_the_window_is_found_by_looking_back():
    # R2a finding 16 on the return edge: the return turn sits under 61 newer
    # messages. The wake reconciles the asker's answer instead of sending
    # the return message a second time.
    issues, ask_op, child = blocked_parent_with_done_child()
    ret_op = f"{ask_op}-ret"
    final = "FINAL: the file has 12 lines"
    pc = FakePaperclip(issues=issues)
    pc.child_rows["is-1"] = [dict(child)]
    # the child's answer is the assignee's own comment (R2a finding 17)
    pc.comment_rows["ch-1"] = [{"body": "t45_alpha.txt has 12 lines",
                                "authorType": "agent",
                                "author": {"id": "ag-atlas"}}]
    pc.comment_rows["is-1"] = [{"body": final}]
    pc.interaction_rows = [{"id": "ix-1", "kind": "request_confirmation",
                            "status": "pending",
                            "idempotencyKey": f"{ret_op}-confirm"}]
    msgs = [("user", "r1", f"[{ret_op}]\n\nthe ask came back"),
            ("assistant", "r1", final)]
    side = [("user", f"s{i}", f"side message {i}") for i in range(61)]
    t3 = WindowedT3(messages=msgs + side)
    assert run_with_roster(pc, t3, {}) == 0
    assert t3.sends == []
    assert pc.issues["is-1"]["status"] == "in_review"
