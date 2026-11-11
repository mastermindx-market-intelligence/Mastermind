"""T4c door repairs (R4b review findings 3, 4(door), 6, 9, 10, 11, 12, 13).

Every test here is the review's reproduction (or its inversion) turned into
a law: it failed on the merged T4b code for the exact reason the finding
names.  The reviewer's reproductions live in
``integrations/mmos/R4B_REVIEW_FINDINGS.md`` (appendix).

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_mmos_coding_job_door_t4c.py
"""
import asyncio
import datetime as dt
import importlib.util
import json
import os
import stat
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_mmos_coding_job_door import (  # noqa: F401
    _attack_door, _issue_row, scratch)

HERE = os.path.dirname(__file__)
DOOR_SRC = os.path.join(HERE, "..", "tools", "mmos_coding_job", "door.py")
spec = importlib.util.spec_from_file_location("t4b_door", DOOR_SRC)
door_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(door_mod)


def _config_t4c(scratch, **overrides):
    """The door config with every T4c boundary field present."""
    values = {
        "scratch_root": str(scratch),
        "paperclip_base_url": "http://127.0.0.1:3199",
        "paperclip_allowed": ["127.0.0.1:3199"],
        "paperclip_company_id": "cmp-test",
        "teammates": ["ag-1"],
        "t3": {
            "proof_base_url": "http://127.0.0.1:3799",
            "home_dir": str(scratch / "t3home"),
            "port": 3799,
            "token_path": str(scratch / "worker-token.txt"),
            "project_id": "proj-test",
            "model_selection": '{"instanceId":"x","model":"m"}',
        },
        "intake_poll_seconds": 60.0,
    }
    for key, value in overrides.items():
        if key.startswith("t3_"):
            values["t3"][key[3:]] = value
        else:
            values[key] = value
    return values


def _iso(seconds_ago: float) -> str:
    return (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# ---------------------------------------------------------------------------
# F9: the loopback law parses the URL; the Paperclip base is an explicit
# host:port allowlist entry, and reserved neighbour ports are never legal
# ---------------------------------------------------------------------------


def test_f9_loopback_check_parses_the_url_never_a_prefix(scratch):
    # the review's reproduction: userinfo smuggles a real host past a
    # string-prefix check (`http://127.0.0.1:80@example.com` -> example.com)
    with pytest.raises(ValueError):
        door_mod.loopback_only("http://127.0.0.1:80@example.com", "x")
    with pytest.raises(ValueError):
        door_mod.loopback_only("https://127.0.0.1:3199", "x")  # not the dev surface
    with pytest.raises(ValueError):
        door_mod.loopback_only("http://example.com:3199", "x")
    assert door_mod.loopback_only(
        "http://127.0.0.1:3799/", "x") == "http://127.0.0.1:3799"


def test_f9_paperclip_base_must_match_an_explicit_allowlist(scratch):
    with pytest.raises(ValueError, match="paperclip_allowed"):
        door_mod.DoorConfig(_config_t4c(scratch, paperclip_allowed=None))
    with pytest.raises(ValueError, match="allowlist"):
        door_mod.DoorConfig(_config_t4c(
            scratch, paperclip_allowed=["127.0.0.1:3198"]))
    door_mod.DoorConfig(_config_t4c(scratch))  # the pinned dev base: legal


def test_f9_reserved_neighbour_ports_are_refused_even_if_listed(scratch):
    # the installed Paperclip (3100), the live T3 app (3773/3774) and the
    # team server (3780) are never legal Paperclip targets for this door
    for port in (3100, 3179, 3773, 3774, 3780):
        with pytest.raises(ValueError, match="reserved"):
            door_mod.DoorConfig(_config_t4c(
                scratch,
                paperclip_base_url=f"http://127.0.0.1:{port}",
                paperclip_allowed=[f"127.0.0.1:{port}"]))


# ---------------------------------------------------------------------------
# F6: one lock, a unique temp name, fsync — concurrent saves and intake
# never collide or corrupt frozen.json
# ---------------------------------------------------------------------------


def test_f6_two_thread_saves_never_collide_or_corrupt(scratch, monkeypatch):
    # the review's reproduction inverted: two threads x 30 saves over a
    # 3000-key record collided on the shared temp name (FileNotFoundError)
    d = _attack_door(scratch, monkeypatch)
    for i in range(3000):
        d.frozen[f"k{i}"] = {"x": "y" * 100}
    errors = []

    def saver():
        for _ in range(30):
            try:
                d._save_frozen()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
                return

    ts = [threading.Thread(target=saver) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []
    data = json.loads(d.frozen_path.read_text(encoding="utf-8"))
    assert len(data) == 3000
    assert data["k2999"] == {"x": "y" * 100}
    # no stray temp files survive a clean save
    leftovers = [p.name for p in d.frozen_path.parent.iterdir()
                 if p.name.startswith("frozen.json") and p != d.frozen_path]
    assert leftovers == []


def test_f6_intake_mutations_never_break_a_concurrent_save(
        scratch, monkeypatch):
    # the structural race: intake inserts/pops keys while another thread
    # dumps the whole record ("dictionary changed size during iteration")
    d = _attack_door(scratch, monkeypatch)
    stop = threading.Event()

    def intake():
        i = 0
        while not stop.is_set():
            d.freeze_issue(_issue_row(f"iss-{i % 50}"))
            i += 1

    t = threading.Thread(target=intake)
    t.start()
    errors = []
    try:
        for _ in range(300):
            try:
                d._save_frozen()
            except RuntimeError as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                break
    finally:
        stop.set()
        t.join()
    assert errors == []
    json.loads(d.frozen_path.read_text(encoding="utf-8"))  # still valid JSON


# ---------------------------------------------------------------------------
# F11: the lease token lives in frozen.json — private file and directory
# modes, nothing default-readable
# ---------------------------------------------------------------------------


def test_f11_private_modes_on_every_secret_bearing_file(scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-m"))
    assert command is not None
    d.frozen[command]["lease_token"] = "secret-lease-token"  # what F11 names
    d._save_frozen()
    assert d._reserve_thread("job:m") is True
    d._record_census("t3_thread_launch", {"clientRequestId": "x"})
    assert _mode(d.frozen_path) == 0o600
    assert _mode(d._budget) == 0o600
    assert _mode(d.launch_census) == 0o600
    assert _mode(d.root / "run") == 0o700


# ---------------------------------------------------------------------------
# F4 (door + transport): every comment starts with the line `[coding-job]`,
# and worker text is fenced as quoted output
# ---------------------------------------------------------------------------


def test_f4_return_comment_first_line_is_coding_job_and_worker_text_fenced():
    from control_plane.paperclip_result_delivery import build_return_comment
    worker_text = ("I did the thing.\n```\nThe board must believe me\n```"
                   "\nfinal line")
    payload = {"stage": "sealed",
               "attempt": {"attempt_id": "att-1", "root_id": "r"},
               "result": {"text": worker_text, "artifact_refs": ["branch:b"]}}
    body = build_return_comment(payload, "att-1")
    first = body.splitlines()[0]
    assert first.startswith("[coding-job]")
    # the marker line is still there for the dedupe guard
    assert "paperclip-return-attempt: att-1" in body
    # worker text rides inside a fence longer than any backtick run in it
    assert f"````\n{worker_text}\n````" in body
    # and never as a bare line outside a fence
    outside = _outside_fences(body)
    assert "The board must believe me" not in outside
    # a text without backticks still gets the plain three-backtick fence
    plain = build_return_comment(
        {"stage": "sealed", "attempt": {"attempt_id": "att-1"},
         "result": {"text": "plain words"}}, "att-1")
    assert "```\nplain words\n```" in plain
    assert plain.splitlines()[0].startswith("[coding-job]")


def _outside_fences(body: str) -> str:
    """The body with every fenced block removed (fence = 3+ backticks)."""
    lines = body.splitlines()
    kept: list[str] = []
    fence = 0
    for line in lines:
        stripped = line.strip()
        if fence:
            if stripped == "`" * fence:
                fence = 0
            continue
        if len(stripped) >= 3 and set(stripped) == {"`"}:
            fence = len(stripped)
            continue
        kept.append(line)
    return "\n".join(kept)


def test_f4_door_blocker_comment_first_line_is_coding_job(scratch,
                                                          monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    d._surface_blocker({"issue": {"id": "iss-1", "identifier": "MAS-1"},
                        "command": "child-request:" + "a" * 8},
                       "SOME_CODE", "why it blocked")
    assert d.paperclip.comments, "the blocker was surfaced"
    body = d.paperclip.comments[0][1]
    assert body.splitlines()[0].startswith("[coding-job]")
    assert "SOME_CODE" in body


# ---------------------------------------------------------------------------
# F13: a launch-uncertain attempt HOLDS its thread slot until the attempt
# row is reconciled to a terminal state
# ---------------------------------------------------------------------------


def test_f13_launch_uncertain_holds_the_slot_until_reconciled(
        scratch, monkeypatch, tmp_path):
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-u"))
    entry = d.frozen[command]
    entry.update({"job_id": "JOB-U", "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "claimed"})
    d._save_frozen()
    # the crash happened AFTER adapter.start was called but BEFORE the
    # receipt was durable: unknowable
    flag = scratch / "run" / "jobs" / attempt_id / "launch-attempted"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("now", encoding="utf-8")
    assert d._reserve_thread("job:JOB-U") is True

    def fail(**_kw):
        raise AssertionError("no adapter may be composed for an "
                             "uncertain launch")

    monkeypatch.setattr(d, "_compose_adapter", fail)
    d._execute(runtime, command, entry)
    assert entry["phase"] == "launch-uncertain"

    # F13: the slot is HELD — the native thread may still be running
    assert "job:JOB-U" in json.loads(d._budget.read_text())["reserved"]

    # a non-terminal attempt row changes nothing (still being reconciled)
    d._close_launch_uncertainty(runtime, entry)
    assert "job:JOB-U" in json.loads(d._budget.read_text())["reserved"]
    assert not entry.get("uncertainty_closed")

    # the attempt reaching a terminal state is the reconciliation: the slot
    # returns, exactly once, and the entry needs nothing more
    runtime.attempts.record_process(
        attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="mcp:launch:u")
    runtime.attempts.mark_running(
        attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token)
    runtime.attempts.complete_attempt(
        attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload={"summary": "ok", "artifacts": []})
    d._close_launch_uncertainty(runtime, entry)
    assert "job:JOB-U" not in json.loads(d._budget.read_text())["reserved"]
    assert entry["uncertainty_closed"]
    assert d._entry_action(entry) == "skip"
    # idempotent: closing again releases nothing twice, errors nothing
    d._close_launch_uncertainty(runtime, entry)


# ---------------------------------------------------------------------------
# F3: a crash after the seal commit is finished as sealed — never adopted
# into StateConflict, never reported EXECUTOR_FAILED
# ---------------------------------------------------------------------------


def _terminal_attempt(runtime, job_id):
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    aid = lease.attempt.attempt_id
    runtime.attempts.record_process(
        aid, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="mcp:launch:s")
    runtime.attempts.mark_running(
        aid, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token)
    runtime.attempts.complete_attempt(
        aid, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload={"summary": "ok", "artifacts": []})
    return lease, aid


def test_f3_crash_after_seal_commit_finishes_sealed_never_execute_failed(
        scratch, monkeypatch, tmp_path):
    """The review's reproduction: complete_attempt committed (the seam fires
    inside it), the door died before phase='sealed' was saved.  The fresh
    door routed the entry to 'execute' -> recovery -> adopt_attempt on a
    COMPLETED attempt -> StateConflict -> EXECUTOR_FAILED."""
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease, aid = _terminal_attempt(runtime, job_id)

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-x"))
    entry = d.frozen[command]
    entry.update({"job_id": "J", "attempt_id": aid, "phase": "launched",
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token})
    assert d._entry_action(entry) == "execute"  # the crash window: not sealed

    class _A:
        async def reattach(self, spec, binding):
            return SimpleNamespace(provider_session_id="mcp:launch:s")

    real_spec = d._launch_spec(
        run_id=aid, job_id="J",
        prompt=d._worker_prompt(aid, "t3/mmos-t4b-job-deadbeef"))
    fake_run = SimpleNamespace(spec=real_spec,
                               original_ref=SimpleNamespace(
                                   provider_session_id="x", pid=None,
                                   run_id=aid))
    import control_plane.t3_execution_adapter as am
    monkeypatch.setattr(am, "SQLiteT3AdapterStateStore",
                        lambda _p: SimpleNamespace(load_run=lambda _r: fake_run))
    monkeypatch.setattr(d, "_compose_adapter", lambda *a, **k: (_A(), {}))

    # OLD behavior: StateConflict("cannot be adopted from COMPLETED")
    # -> EXECUTOR_FAILED.  NEW: finished as sealed, honestly.
    d._execute(runtime, command, entry)

    assert entry["phase"] in ("delivered", "delivery-refused")
    assert entry["phase"] != "execute-failed"
    assert entry.get("blocker", {}).get("code") != "EXECUTOR_FAILED"
    bodies = [body for _issue, body in d.paperclip.comments]
    assert not any("EXECUTOR_FAILED" in body for body in bodies)
    if entry["phase"] == "delivery-refused":
        # an honest typed blocker, first line [coding-job] (F4)
        assert bodies, "a refusal is surfaced, never silent"
        assert bodies[0].splitlines()[0].startswith("[coding-job]")


def test_f3_a_present_receipt_is_read_never_redriven(scratch, monkeypatch,
                                                     tmp_path):
    """The common crash window: the seam DID land its receipt inside
    complete_attempt.  The fresh door reads it and finishes — the seam is
    NOT driven a second time."""
    from control_plane.execution_return_wiring import (
        EXECUTION_RETURN_DELIVERY_EVENT, execution_return_receipt_command_id,
    )
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    _lease, aid = _terminal_attempt(runtime, job_id)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection, aggregate_type="attempt", aggregate_id=aid,
            event_type=EXECUTION_RETURN_DELIVERY_EVENT, job_id=job_id,
            attempt_id=aid,
            payload={"delivery": {"state": "delivered",
                                  "transport_ref": "paperclip:issue:i:comment:c"}},
            command_id=execution_return_receipt_command_id(aid))

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-y"))
    entry = d.frozen[command]
    entry.update({"job_id": "J2", "attempt_id": aid, "phase": "sealed"})

    def boom(*_a, **_k):
        raise AssertionError("a receipt exists; the seam must not re-drive")

    monkeypatch.setattr(d, "_redrive_return_seam", boom)
    d._finish_sealed(runtime, entry)
    assert entry["phase"] == "delivered"
    assert entry["delivery"]["transport_ref"] == "paperclip:issue:i:comment:c"


def test_f3_a_missing_receipt_redrives_the_seam_once(scratch, monkeypatch,
                                                     tmp_path):
    """complete_attempt committed but the receipt never landed (crash inside
    the post-commit window).  The door re-drives the seam — the receipt
    command id and the comment marker make it idempotent — and finishes
    honestly from whatever the re-drive recorded."""
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    _lease, aid = _terminal_attempt(runtime, job_id)

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-z"))
    entry = d.frozen[command]
    entry.update({"job_id": "J3", "attempt_id": aid, "phase": "sealed"})

    driven = []

    def fake_redrive(runtime_arg, entry_arg):
        driven.append(entry_arg["attempt_id"])
        # what a real re-drive records: an honest receipt event
        from control_plane.execution_return_wiring import (
            EXECUTION_RETURN_DELIVERY_EVENT,
            execution_return_receipt_command_id,
        )
        with runtime_arg.store.transaction() as connection:
            runtime_arg.store.append_event(
                connection, aggregate_type="attempt", aggregate_id=aid,
                event_type=EXECUTION_RETURN_DELIVERY_EVENT, job_id=job_id,
                attempt_id=aid,
                payload={"delivery": {"state": "refused",
                                      "refusal_code": "ORIGIN_KIND_UNKNOWN"}},
                command_id=execution_return_receipt_command_id(aid))

    monkeypatch.setattr(d, "_redrive_return_seam", fake_redrive)
    d._finish_sealed(runtime, entry)
    assert driven == [aid]        # driven exactly once
    assert entry["phase"] == "delivery-refused"
    assert entry["blocker"]["code"] == "ORIGIN_KIND_UNKNOWN"


# ---------------------------------------------------------------------------
# F10: the door freezes only issues assigned to enrolled teammates, and
# admits only when the task itself shows the request
# ---------------------------------------------------------------------------


def test_f10_intake_freezes_only_enrolled_teammates_issues(scratch,
                                                           monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    assert d.freeze_issue(_issue_row("iss-e")) is not None  # ag-1 enrolled
    stranger = _issue_row("iss-n")
    stranger["assigneeAgentId"] = "ag-stranger"
    assert d.freeze_issue(stranger) is None                 # not enrolled
    unassigned = _issue_row("iss-u2")
    unassigned["assigneeAgentId"] = None
    assert d.freeze_issue(unassigned) is None               # unassigned
    assert len(d.frozen) == 1


class _CommentsPaperclip:
    """The door's Paperclip reader with a scripted issue + comments feed."""

    def __init__(self, issue_row, comment_rows):
        self._issue = issue_row
        self._rows = comment_rows

    def issue(self, issue_id):
        return self._issue

    def comments(self, issue_id):
        return {"comments": self._rows}


def _agent(body, at):
    return {"authorType": "agent", "body": body, "createdAt": at}


def _user(body, at):
    return {"authorType": "user", "body": body, "createdAt": at}


BLOCK = "```paperclip-coding-job\n```"


def test_f10_admit_refuses_until_the_task_shows_the_request(scratch,
                                                            monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-g"))
    entry = d.frozen[command]
    row = dict(_issue_row("iss-g"))

    # no agent comment at all
    d.paperclip = _CommentsPaperclip(
        row, [_user("board note", "2026-11-11T01:00:00Z")])
    reply = asyncio.run(d.admit(command))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "TASK_REQUEST_MISSING"
    # the refusal burned nothing: no admission request was persisted
    assert "admit_requested_at" not in entry

    # an agent comment WITHOUT the block is no request
    d.paperclip = _CommentsPaperclip(
        row, [_agent("plain answer, no block", "2026-11-11T01:00:00Z")])
    reply = asyncio.run(d.admit(command))
    assert reply["error"]["code"] == "TASK_REQUEST_MISSING"

    # the block must be the agent comment's OWN last word (the carrier's
    # parser discipline); quoted mid-comment is not a request
    d.paperclip = _CommentsPaperclip(
        row, [_agent(f"{BLOCK}\nbut then I said more",
                     "2026-11-11T01:00:00Z")])
    reply = asyncio.run(d.admit(command))
    assert reply["error"]["code"] == "TASK_REQUEST_MISSING"

    # the NEWEST agent comment governs: a later plain answer supersedes the
    # request the teammate changed its mind about
    d.paperclip = _CommentsPaperclip(row, [
        _agent(BLOCK, "2026-11-11T01:00:00Z"),
        _agent("on reflection, no code needed", "2026-11-11T02:00:00Z")])
    reply = asyncio.run(d.admit(command))
    assert reply["error"]["code"] == "TASK_REQUEST_MISSING"

    # a later BOARD comment does not revoke it (only the agent's own newer
    # words supersede)
    d.paperclip = _CommentsPaperclip(row, [
        _agent(BLOCK, "2026-11-11T01:00:00Z"),
        _user("board note", "2026-11-11T02:00:00Z")])
    monkeypatch.setattr(d, "_frame_context", lambda: {"principal": {}, "principal_context": {},
                                   "capability_profile_digest": "",
                                   "target_digest": ""})
    with pytest.raises(FileNotFoundError):
        # past the gate (the request stands) — the failure is now the
        # not-started service socket, i.e. the admission lane itself
        asyncio.run(d.admit(command))
    assert entry.get("admit_requested_at")  # the request persisted: lawful


def test_f10_admit_refuses_an_unenrolled_live_assignee(scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-h"))
    row = dict(_issue_row("iss-h"))
    row["assigneeAgentId"] = "ag-reassigned"  # enrolled at intake, not now
    d.paperclip = _CommentsPaperclip(
        row, [_agent(BLOCK, "2026-11-11T01:00:00Z")])
    reply = asyncio.run(d.admit(command))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "ASSIGNEE_NOT_ENROLLED"


def test_f10_admit_refuses_an_unreadable_task_state(scratch, monkeypatch):
    class _Dead:
        def issue(self, issue_id):
            raise ConnectionError("dev Paperclip unreachable")

        def comments(self, issue_id):
            raise ConnectionError("dev Paperclip unreachable")

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-i"))
    d.paperclip = _Dead()
    reply = asyncio.run(d.admit(command))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "TASK_STATE_UNREADABLE"
    assert "admit_requested_at" not in d.frozen[command]


def test_f10_recovery_replay_skips_the_gate(scratch, monkeypatch):
    """The F3 crash window: the admission was already REQUESTED (durable) —
    the idempotent REPLAY needs no second authorization from the task."""
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-r"))
    entry = d.frozen[command]
    entry["admit_requested_at"] = "2026-11-11T00:00:00+00:00"
    # nothing on the task would pass the gate now (no comments at all)
    d.paperclip = _CommentsPaperclip(dict(_issue_row("iss-r")), [])
    monkeypatch.setattr(d, "_frame_context", lambda: {"principal": {}, "principal_context": {},
                                   "capability_profile_digest": "",
                                   "target_digest": ""})
    with pytest.raises(FileNotFoundError):
        asyncio.run(d.admit(command))  # straight to the (absent) socket
    assert entry["admit_requested_at"]  # still the original request


# ---------------------------------------------------------------------------
# F12 (door half): a WAIT is retried by the door when the retry interval
# elapses — same command, so still one admission
# ---------------------------------------------------------------------------


def test_f12_a_wait_is_retried_by_the_door_when_the_interval_elapses(
        scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-w"))
    entry = d.frozen[command]
    entry.update({"admit_requested_at": _iso(5), "admit_last_ask": _iso(5),
                  "admit_outcome": "WAIT"})
    # a fresh WAIT was just answered: not yet
    assert d._entry_action(entry) == "skip"

    # the interval elapsed: capacity may have freed — the door re-asks the
    # SAME command (idempotent REPLAY, never a second admission)
    entry["admit_last_ask"] = _iso(3600)
    assert d._entry_action(entry) == "admit"

    # and the retry heals into execution
    async def fake_admit(_cmd):
        entry["job_id"] = "JOB-W"
        entry["admit_outcome"] = "ADMITTED"
        return {"ok": True, "result": {"state": "ADMITTED",
                                       "job_id": "JOB-W"}}

    monkeypatch.setattr(d, "admit", fake_admit)
    d._ensure_admitted(command, entry)
    assert entry["job_id"] == "JOB-W"
    assert d._entry_action(entry) == "execute"


def test_f12_an_unageable_wait_is_retried_not_stranded(scratch, monkeypatch):
    # a WAIT whose timestamps cannot be aged honestly is re-asked: the
    # engine's command-id law makes the re-ask safe
    d = _attack_door(scratch, monkeypatch)
    entry = {"admit_requested_at": "not-a-timestamp",
             "admit_outcome": "WAIT"}
    assert d._entry_action(entry) == "admit"
