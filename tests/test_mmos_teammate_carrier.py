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
                 "dependencyReady": True}
                for iid, row in self.issues.items()]

    def issue(self, issue_id):
        return dict(self.issues[issue_id], id=issue_id)

    def checkout(self, issue_id, agent_id):
        self._guard("checkout")
        self.calls.append(("checkout", issue_id, agent_id))
        row = self.issues[issue_id]
        assert row["status"] in ("todo", "in_progress"), "expectedStatuses would refuse"
        row["status"] = "in_progress"

    def comments(self, issue_id):
        return self.comment_rows.get(issue_id, [])

    def add_comment(self, issue_id, body):
        self._guard("comment")
        self.calls.append(("comment", issue_id, body))
        self.comment_rows.setdefault(issue_id, []).append({"body": body})

    def interactions(self, issue_id):
        return [dict(row) for row in self.interaction_rows]

    def request_confirmation(self, issue_id, idem_key, prompt):
        self._guard("interaction")
        # Real dev-server behavior (verified live 2026-11-10): a re-POST of an
        # idempotencyKey that exists from ANOTHER run is 409, not a dedupe.
        if any(row.get("idempotencyKey") == idem_key for row in self.interaction_rows):
            raise wc.CarrierError(
                f"POST /api/issues/{issue_id}/interactions -> HTTP 409 "
                '{"error":"Interaction idempotency key already exists"}')
        self.interaction_rows.append(
            {"id": f"ix-{len(self.interaction_rows) + 1}", "kind": "request_confirmation",
             "status": "pending", "idempotencyKey": idem_key})
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

    def checkout_409_once(issue_id, agent_id):
        checkout_calls.append(issue_id)
        if len(checkout_calls) == 1:
            raise wc.CarrierError(
                "POST /api/issues/is-1/checkout -> HTTP 409 "
                '{"error":"issue already checked out"}')
        return original_checkout(issue_id, agent_id)
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
    t3.messages_store = [("user", "r1", "task"), ("assistant", "r1", ASK_REPLY)]
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
