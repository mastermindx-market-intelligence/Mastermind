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
                 metadata=None, fail=()):
        self.agent_id = agent_id
        self.run_id = "run-9"
        self.issues = issues or {}
        self.comment_rows = dict(comments or {})
        self.interaction_keys = []
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

    def request_confirmation(self, issue_id, idem_key, prompt):
        self._guard("interaction")
        if idem_key in self.interaction_keys:  # server dedupes by idem key
            return {"id": "dup", "deduped": True}
        self.interaction_keys.append(idem_key)
        self.calls.append(("interaction", issue_id, idem_key))
        return {"id": "ix-1"}

    def set_status(self, issue_id, status):
        self._guard("status")
        self.calls.append(("status", issue_id, status))
        self.issues[issue_id]["status"] = status


class FakeT3:
    """Thread memory + a send() that appends the marker turn and answers."""

    def __init__(self, replies=None, messages=None, send_error=None):
        self.messages_store = list(messages or [])
        self.replies = list(replies or [])
        self.send_error = send_error
        self.sends = []
        self._auto = 0

    def send(self, message):
        if self.send_error:
            raise wc.CarrierError(self.send_error)
        self.sends.append(message)
        self.messages_store.append(("user", "r1", message))
        if self.replies:
            reply = self.replies.pop(0)
        else:
            self._auto += 1
            reply = "fake answer" if self._auto == 1 else f"fake answer {self._auto}"
        self.messages_store.append(("assistant", "r1", reply))
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
