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
        "paperclip_service_agent_id": "ag-pf-delivery",
        "paperclip_service_agent_token_path": str(scratch / "service-agent.bearer"),
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
    # the installed Paperclip (3100/3179), the live T3 app (3773/3774), the
    # team server (3780) and — REV-CODE F2 — the neighbour dev listeners
    # 3796 (another lane) / 3800 (reserved) are never legal Paperclip targets
    for port in (3100, 3179, 3773, 3774, 3780, 3796, 3800):
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
    import uuid
    from control_plane.paperclip_result_delivery import build_return_comment
    # REV-CODE F1: the comment builder now takes the deterministic uuid5
    # request id (it rides in the whole marker line on agent rows)
    request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "paperclip-return:att-1"))
    worker_text = ("I did the thing.\n```\nThe board must believe me\n```"
                   "\nfinal line")
    payload = {"stage": "sealed",
               "attempt": {"attempt_id": "att-1", "root_id": "r"},
               "result": {"text": worker_text, "artifact_refs": ["branch:b"]}}
    body = build_return_comment(payload, "att-1", request_id)
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
         "result": {"text": "plain words"}}, "att-1", request_id)
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
        prompt=d._worker_prompt(aid, "t3/mmos-t4b-job-deadbeef"),
        workspace=scratch / "run" / "jobs" / "job-f3-ws")
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
    # the ASSIGNEE's own word (_issue_row assigns "ag-1"): the R1 gate binds
    # the authorizing comment's authorAgentId to the assignee
    return {"authorType": "agent", "authorAgentId": "ag-1",
            "body": body, "createdAt": at}


def _agent_of(agent_id, body, at):
    return {"authorType": "agent", "authorAgentId": agent_id,
            "body": body, "createdAt": at}


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


# ---------------------------------------------------------------------------
# Step 3 — F15 (R4b finding 15) + attack F8: ONE owner for recovery, the
# engine.  The door composes the real t3-native supervisor, drives
# reconcile_restart at start and on a cadence, and finishes from the
# engine's recovered ActiveRun; its own record_process+adopt_attempt block
# is gone.  Every test here failed on the Step-2 code for the finding's
# reason (the door adopted itself / composed no supervisor / blocked
# startup on the mint).
# ---------------------------------------------------------------------------


def test_step3_source_law_the_door_owns_no_recovery_of_its_own():
    """F15: recovery has exactly one owner — the engine.  The door source
    contains no DoorSupervisor, no record_process call and no adopt_attempt
    call; the service's supervisor_factory composes the real supervisor."""
    src = Path(DOOR_SRC).read_text(encoding="utf-8")
    assert "class DoorSupervisor" not in src
    assert "record_process(" not in src
    assert "adopt_attempt(" not in src
    assert "self._compose_supervisor(" in src  # the factory's owner


def test_step3_compose_supervisor_builds_the_real_engine_owner(
        scratch, monkeypatch, tmp_path):
    """Enrolled: ``_compose_supervisor`` returns the composed t3-native
    supervisor (boundary adapter + wired provider_receipt_reader).  Not
    enrolled (no token — the dev server was down at start): the PLAIN
    primary comes back, never an exception."""
    from control_plane import t3_native_composition as composition_mod
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, _job, _attempt = _runtime_and_job(tmp_path)

    class _FakeComposedAdapter:
        adapter_id = "t3-native"

        def __init__(self):
            self.inspector = SimpleNamespace()

        def launch_receipt(self, run_id):
            return None

        def retained_original_ref(self, run_id):
            return None

    seen = {}

    def fake_adapter_compose(runtime_arg, **kwargs):
        seen["kwargs"] = kwargs
        return SimpleNamespace(
            composed=True, status="T3_COMPOSED", reason="",
            adapter=_FakeComposedAdapter())

    monkeypatch.setattr(composition_mod, "compose_t3_native_adapter",
                        fake_adapter_compose)
    d = _attack_door(scratch, monkeypatch)
    composed = d._compose_supervisor(
        runtime, port_factory=d._reconcile_only_port_factory)
    # the composed t3 owner: the boundary adapter + the wired receipt reader
    from control_plane.t3_native_composition import SupervisorBoundaryT3Adapter
    assert isinstance(composed.adapter, SupervisorBoundaryT3Adapter)
    assert composed._provider_receipt_reader is not None
    # the composition shares the door's durable adapter store (the crashed
    # door's receipts are the recovery's evidence)
    assert "state_store" in seen["kwargs"]

    # not enrolled: the typed fail-closed result, never an exception — the
    # plain primary serves while no token exists
    def not_enrolled(runtime_arg, **kwargs):
        return SimpleNamespace(composed=False, status="T3_NOT_ENROLLED",
                               reason="no token file", adapter=None)

    monkeypatch.setattr(composition_mod, "compose_t3_native_adapter",
                        not_enrolled)
    plain = d._compose_supervisor(
        runtime, port_factory=d._reconcile_only_port_factory)
    assert plain.adapter is None and plain._provider_receipt_reader is None
    assert plain.process_controller is not None


def test_step3_start_mints_only_against_a_ready_pinned_server(
        scratch, monkeypatch):
    """``start()`` mints the worker token ONCE before the service composes,
    and NEVER blocks door startup on a down dev server: the pairing CLI is
    withheld (finding 8 — it would fall back to the live app), the
    executor's mint loop owns the retry, and the service composes plain."""
    d = _attack_door(scratch, monkeypatch)

    def forbidden(*_a, **_k):
        raise AssertionError("the pairing CLI must never run against an "
                             "unready or unpinned server")

    monkeypatch.setattr(
        "integrations.t3.live_proof.t3_live_proof.obtain_mcp_access_token",
        forbidden)
    monkeypatch.setattr(d, "_dev_server_ready", lambda: False)
    asyncio.run(asyncio.wait_for(d._ensure_worker_token(), timeout=5.0))
    # no token file was minted by the withheld path
    assert not Path(d.config.t3_token_path).exists()

    minted = {}

    def fake_mint(path, label, *, base_url, home_dir):
        minted.update(path=path, label=label, base_url=base_url,
                      home_dir=home_dir)

    monkeypatch.setattr(
        "integrations.t3.live_proof.t3_live_proof.obtain_mcp_access_token",
        fake_mint)
    monkeypatch.setattr(d, "_dev_server_ready", lambda: True)
    asyncio.run(asyncio.wait_for(d._ensure_worker_token(), timeout=5.0))
    assert minted["path"] == str(d.config.t3_token_path)
    assert minted["base_url"] == d.config.t3_proof_base
    assert minted["home_dir"] == d.config.t3_home_dir


def test_step3_reconcile_routes_a_recovered_run_to_its_entry(
        scratch, monkeypatch):
    """The periodic/restart reconcile adopts nothing itself: it drains the
    engine's recovered ActiveRuns and routes each one to its frozen entry —
    engine fence/token/ref, phase reattached, executor woken, cadence
    stamped."""
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-rc"))
    entry = d.frozen[command]
    entry.update({"job_id": "JOB-RC", "attempt_id": "ATT-RC",
                  "phase": "awaiting-lease-expiry"})
    run = SimpleNamespace(
        lease=SimpleNamespace(
            attempt=SimpleNamespace(attempt_id="ATT-RC", fence_generation=7),
            lease_token="engine-token"),
        process_ref=SimpleNamespace(provider_session_id="mcp:engine-reattach"))
    d._supervisor = SimpleNamespace(
        reconcile_restart=lambda **_kw: [SimpleNamespace(
            attempt_id="ATT-RC", status=SimpleNamespace(
                name="RECEIPT_RECOVERED"), error="")],
        take_recovered_runs=lambda: [run])
    before = d._last_reconcile
    outcomes = d._reconcile(object())
    assert len(outcomes) == 1
    assert d._last_reconcile > before
    assert entry["phase"] == "reattached"
    assert entry["fence_generation"] == 7
    assert entry["lease_token"] == "engine-token"
    assert entry["provider_session_id"] == "mcp:engine-reattach"
    assert d._wake.is_set()


def _crash_window_entry(d, runtime, job_id, attempt_id, lease):
    """The frozen entry of a door that died mid-flight: claimed, attempt
    durable, receipt present (so the door's own receipt read routes to the
    engine lane, never the F1/F13 launch windows)."""
    command = d.freeze_issue(_issue_row("iss-cw"))
    entry = d.frozen[command]
    entry.update({"job_id": job_id, "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "launched"})
    d._save_frozen()
    real_spec = d._launch_spec(
        run_id=attempt_id, job_id=job_id,
        prompt=d._worker_prompt(attempt_id, "t3/mmos-t4b-job-deadbeef"),
        workspace=d.root / "run" / "jobs" / "job-cw-ws")
    fake_run = SimpleNamespace(
        spec=real_spec,
        original_ref=SimpleNamespace(provider_session_id="x", pid=None,
                                     run_id=attempt_id))

    class _FakeStore:
        def load_run(self, run_id):
            return fake_run

    import control_plane.t3_execution_adapter as adapter_module
    return entry, _FakeStore, adapter_module


def test_step3_live_lease_defers_to_the_engine_and_retries_on_a_cadence(
        scratch, monkeypatch, tmp_path):
    """Attack F8's wedge, closed: an identity-less claim with a durable
    receipt under a LIVE lease is DEFERRED by the engine
    (AWAITING_LEASE_EXPIRY) — the door records the deferral and re-asks on
    the reconcile cadence; it never adopts, records or launches."""
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    entry, fake_store, adapter_module = _crash_window_entry(
        d, runtime, "JOB-DEF", attempt_id, lease)
    monkeypatch.setattr(adapter_module, "SQLiteT3AdapterStateStore",
                        lambda _path: fake_store())

    def forbidden(*_a, **_k):
        raise AssertionError("the door never records a process or adopts "
                             "a lease itself")

    monkeypatch.setattr(runtime.attempts, "record_process", forbidden)
    monkeypatch.setattr(runtime.attempts, "adopt_attempt", forbidden)

    def engine_defers(_runtime, attempt_ids=None):
        assert attempt_ids == frozenset({attempt_id})
        return [SimpleNamespace(attempt_id=attempt_id,
                                status=SimpleNamespace(
                                    name="AWAITING_LEASE_EXPIRY"),
                                error="")]

    monkeypatch.setattr(d, "_reconcile", engine_defers)
    d._execute(runtime, entry["command"], entry)
    assert entry["phase"] == "awaiting-lease-expiry"
    assert entry["reconcile_last_ask"]
    # retry-gated: a fresh ask is not due yet; an aged one re-executes
    assert d._entry_action(entry) == "skip"
    entry["reconcile_last_ask"] = _iso(3600)
    assert d._entry_action(entry) == "execute"
    # the lease was never fenced by the door
    assert runtime.attempts.get_attempt(attempt_id).lease_owner == (
        "t4b-door-dead")


def test_step3_recovery_branch_seals_from_the_engine_adopted_run(
        scratch, monkeypatch, tmp_path):
    """At lease expiry the ENGINE adopts the same attempt; the door seals
    from the ENGINE's lease and the engine-reattached ref — its own
    fence/token are replaced by the engine's, and the launch port is
    composed only for the seal's terminal read."""
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    entry, fake_store, adapter_module = _crash_window_entry(
        d, runtime, "JOB-ADOPT", attempt_id, lease)
    monkeypatch.setattr(adapter_module, "SQLiteT3AdapterStateStore",
                        lambda _path: fake_store())

    engine_run = SimpleNamespace(
        lease=SimpleNamespace(
            attempt=SimpleNamespace(attempt_id=attempt_id, fence_generation=7),
            lease_token="engine-token"),
        process_ref=SimpleNamespace(provider_session_id="mcp:engine-reattach"))
    asked = []

    def engine_adopts(_runtime, attempt_ids=None):
        asked.append(attempt_ids)
        d._recovered[attempt_id] = engine_run
        return [SimpleNamespace(attempt_id=attempt_id,
                                status=SimpleNamespace(
                                    name="RECEIPT_RECOVERED"), error="")]

    monkeypatch.setattr(d, "_reconcile", engine_adopts)
    sealed = {}

    def fake_seal(_runtime, _entry, _attempt, _adapter, ref, _branch):
        sealed["ref"] = ref

    durable_ref = SimpleNamespace(provider_session_id="mcp:engine-reattach",
                                  run_id=attempt_id)
    monkeypatch.setattr(d, "_seal_and_deliver", fake_seal)
    monkeypatch.setattr(d, "_compose_adapter",
                        lambda *_a, **_k: (SimpleNamespace(
                            retained_original_ref=lambda rid: (
                                durable_ref if rid == attempt_id else None)),
                            {}))
    d._execute(runtime, entry["command"], entry)

    assert asked == [frozenset({attempt_id})]  # scoped to THIS attempt
    assert entry["phase"] == "reattached"
    assert entry["fence_generation"] == 7          # the ENGINE's fence
    assert entry["lease_token"] == "engine-token"  # the ENGINE's token
    assert entry["provider_session_id"] == "mcp:engine-reattach"
    # L4 (crash journey, 2026-11-11): the seal runs on the ADAPTER's durable
    # neutral ref — the engine's ActiveRun ref is the supervisor-boundary
    # twin, which the inner adapter's retained-ref check refuses.
    assert sealed["ref"] is durable_ref


def test_step3_engine_quarantine_parks_the_entry_with_a_typed_blocker(
        scratch, monkeypatch, tmp_path):
    """A typed engine refusal (e.g. STALE_FENCE_QUARANTINED) parks the entry
    with a RECONCILE_<status> blocker and HOLDS its slot — the receipt
    proved a live native execution; the thread budget is not freed."""
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    entry, fake_store, adapter_module = _crash_window_entry(
        d, runtime, "JOB-Q", attempt_id, lease)
    monkeypatch.setattr(adapter_module, "SQLiteT3AdapterStateStore",
                        lambda _path: fake_store())
    assert d._reserve_thread("job:JOB-Q") is True  # the crashed slot

    def engine_quarantines(_runtime, attempt_ids=None):
        return [SimpleNamespace(
            attempt_id=attempt_id,
            status=SimpleNamespace(name="STALE_FENCE_QUARANTINED"),
            error="the fence moved before the adoption")]

    monkeypatch.setattr(d, "_reconcile", engine_quarantines)
    d._execute(runtime, entry["command"], entry)
    assert entry["phase"] == "reconcile-quarantined"
    assert entry["blocker"]["code"] == "RECONCILE_STALE_FENCE_QUARANTINED"
    assert d.paperclip.comments  # surfaced to the task
    # surfaced is terminal for this executor; the slot HOLDS
    assert d._entry_action(entry) == "skip"
    budget = json.loads(d._budget.read_text())
    assert "job:JOB-Q" in budget["reserved"]  # the slot is HELD
    # a FRESH door (frozen.json reload, nothing surfaced yet) routes the
    # parked entry to the blocker branch, which re-surfaces without
    # releasing the slot
    entry["blocker_surfaced"] = None
    assert d._entry_action(entry) == "blocker"  # PARKED_PHASES


def test_step3_engine_owned_phase_executes_and_watches(scratch, monkeypatch):
    """The engine-owned watch: the entry stays executable (the executor
    polls for the terminal row through the ordinary F3 read) and a second
    pass never re-drives reconcile (a live finisher's lease is never
    fenced by a re-ask)."""
    d = _attack_door(scratch, monkeypatch)
    entry = {"phase": "engine-owned", "job_id": "JOB-EO",
             "reconcile_last_ask": _iso(0)}
    assert d._entry_action(entry) == "execute"
    entry["phase"] = "reattached"  # transient engine phases execute too
    assert d._entry_action(entry) == "execute"


def test_step3_placement_job_names_its_workspace(scratch, monkeypatch,
                                                  tmp_path):
    """The worktree gate: a placement Job that cannot name its workspace can
    never be adopted by restart reconciliation, so ``compose_child_execution``
    records the door's job-scoped workspace on the Job."""
    from control_plane.child_request_execution_composition import (
        compose_child_execution,
    )
    from tests.test_executive_supervisor import _runtime_and_job
    from tools.mmos_coding_job.envelope import build_task_request

    runtime, _job, _attempt = _runtime_and_job(tmp_path)
    d = _attack_door(scratch, monkeypatch)
    request = build_task_request(
        issue_id="iss-ws", agent_id="ag-1", company_id="c",
        title="t", description="d", key="coding-job-1")
    composed = compose_child_execution(
        runtime, request=request, spec=d._spec(request), branch="b",
        worktree=str(tmp_path / "ws"))
    job = runtime.jobs.get_job(composed.placement_job.job_id)
    assert job is not None
    assert str(job.worktree) == str(tmp_path / "ws")
    replay = compose_child_execution(
        runtime, request=request, spec=d._spec(request), branch="b",
        worktree=str(tmp_path / "ws"))
    assert replay.placement_job.job_id == composed.placement_job.job_id


def test_step3_launch_spec_writes_the_engine_binding_prompt_name(
        scratch, monkeypatch):
    """The engine's binding rebuild reads ``input/worker-prompt.txt``; the
    door writes BOTH prompt files with the same bytes at 0600."""
    d = _attack_door(scratch, monkeypatch)
    spec = d._launch_spec(run_id="ATT-LP", job_id="JOB-LP",
                          prompt="the worker prompt bytes",
                          workspace=scratch / "run" / "jobs" / "job-lp-ws")
    run_dir = Path(spec.run_dir)
    door_prompt = run_dir / "input" / "prompt.txt"
    engine_prompt = run_dir / "input" / "worker-prompt.txt"
    assert (door_prompt.read_bytes()
            == engine_prompt.read_bytes()
            == b"the worker prompt bytes")
    assert _mode(door_prompt) == 0o600
    assert _mode(engine_prompt) == 0o600


# ---------------------------------------------------------------------------
# Step 4: the after_seal crash window — seal COMMITTED in the engine, the
# frozen entry still "launched" (journey scenario crash-seal; F3's
# terminal-row recovery + the seam's single re-drive own the fresh door)
# ---------------------------------------------------------------------------


def test_step4_after_seal_crash_window_leaves_a_committed_seal_behind(
        scratch, monkeypatch):
    """crash_mode="after_seal" exits 91 AFTER complete_attempt commits and
    BEFORE the frozen "sealed" save — the engine row is terminal while the
    entry still says "launched", exactly the window a FRESH door must
    finish as sealed with the result comment exactly once.  Without the
    crash mode the same call saves "sealed" and proceeds to finish."""
    d = _attack_door(scratch, monkeypatch)
    d.config.crash_mode = "after_seal"

    exited = []

    class _Crashed(Exception):
        """os._exit never returns — the stand-in must not either."""

    def fake_exit(code):
        exited.append(code)
        raise _Crashed(code)

    # os is the shared singleton; the seam name lives in the door module
    # instance type(d) came from (this file loads door.py separately), so
    # patch it through the function's own globals
    monkeypatch.setattr(door_mod.os, "_exit", fake_exit)
    monkeypatch.setattr(d, "_wait_terminal",
                        lambda _a, _r, **_k: (["SUCCEEDED"],
                                              SimpleNamespace(
                                                  value="SUCCEEDED")))
    monkeypatch.setitem(
        type(d)._seal_and_deliver.__globals__,
        "install_execution_return_seam", lambda *a, **k: None)
    sealed_calls = []

    class _Attempts:
        def heartbeat_attempt(self, _attempt_id, **_kwargs):
            return None  # the L5 renewal seam (no-op in this fake)

        def complete_attempt(self, attempt_id, **kwargs):
            sealed_calls.append((attempt_id, kwargs))
            return SimpleNamespace(status=SimpleNamespace(value="succeeded"))

    runtime = SimpleNamespace(attempts=_Attempts())

    async def collect_result(_ref):
        return SimpleNamespace(result=SimpleNamespace(
            structured_output={"text": "done"}))

    adapter = SimpleNamespace(collect_result=collect_result)
    ref = SimpleNamespace(provider_session_id="mcp:t")
    entry = {"attempt_id": "ATT-SEAL", "phase": "launched",
             "fence_generation": 3, "lease_token": "tok"}

    with pytest.raises(_Crashed):
        d._seal_and_deliver(runtime, entry, "ATT-SEAL", adapter, ref, "b")

    # the crash point: exit 91, seal committed, entry NOT saved as sealed
    assert exited == [91]
    assert sealed_calls and sealed_calls[0][0] == "ATT-SEAL"
    assert sealed_calls[0][1]["fence_generation"] == 3
    assert sealed_calls[0][1]["lease_token"] == "tok"
    assert entry["phase"] == "launched"
    marker = d.root / "run" / "crash"
    assert json.loads(marker.read_text())["window"] == "after_seal"

    # counter-law: without the crash mode the same seal SAVES and proceeds
    finished = []
    monkeypatch.setattr(d, "_finish_sealed",
                        lambda _runtime, _entry: finished.append(True))
    d.config.crash_mode = None
    entry2 = {"attempt_id": "ATT-SEAL", "phase": "launched",
              "fence_generation": 3, "lease_token": "tok"}
    d._seal_and_deliver(runtime, entry2, "ATT-SEAL", adapter, ref, "b")
    assert exited == [91]  # no second exit
    assert entry2["phase"] == "sealed"
    assert finished == [True]


def test_step4_reconcile_port_constructs_and_refuses_only_the_launch(
        scratch, monkeypatch):
    """Caught live by the crash journey (2026-11-11): the executor's
    supervisor composition builds its port EAGERLY, so a factory that
    RAISES kills reconcile outright — the recovery door logged "recovery
    must never launch" and never adopted.  The port must CONSTRUCT; reads
    pass through (and reach the census); launches are refused pre-send at
    the port's own launch seam with a clean typed refusal."""
    import base64
    import control_plane.t3_native_composition as composition_mod
    from control_plane.t3_execution_adapter import T3PortRefusalError

    d = _attack_door(scratch, monkeypatch)

    calls = []

    class _FakeTransport:
        def __init__(self, url, token):
            pass

        def call_tool(self, tool, arguments):
            calls.append(tool)
            return {"ok": True}

    monkeypatch.setattr(composition_mod, "T3McpHttpTransport",
                        _FakeTransport)
    claims = base64.urlsafe_b64encode(
        json.dumps({"kind": "session", "sid": "probe-session",
                    "sub": "mcp-client",
                    "method": "bearer-access-token"}).encode()
    ).decode().rstrip("=")
    port = d._reconcile_only_port_factory(claims + ".sig")
    assert port is not None  # construction itself: composition survives

    # reads pass through and reach the census
    payload = port._invoke("t3_thread_read", {"threadId": "mcp:t"},
                           mutating=False)
    assert payload == {"ok": True}
    assert calls == ["t3_thread_read"]
    census = Path(d.launch_census).read_text(encoding="utf-8")
    assert '"t3_thread_read"' in census

    # a launch is refused PRE-SEND, cleanly typed, whatever the envelope
    with pytest.raises(T3PortRefusalError, match="reconcile-only"):
        port._launch(SimpleNamespace(), "launch")
    assert "t3_thread_launch" not in calls  # nothing was sent


def test_step4_launch_spec_carries_the_attempt_s_own_job(
        scratch, monkeypatch, tmp_path):
    """Caught live by the lease-expiry journey (2026-11-11): the door claimed
    its attempt on the PLACEMENT job (JOB-002) but built the launch spec with
    the REQUEST job's id (JOB-001).  The engine's receipt-adoption identity
    check (spec.job_id != attempt.job_id) then refused the door's own durable
    receipt as a foreign execution — the whole service quarantined at startup
    and the recovery door died at register-worker.  The spec handed to
    adapter.start must carry the job the attempt was CLAIMED on, at BOTH
    launch sites (the first claim and the F1 never-attempted relaunch)."""
    from tests.test_executive_supervisor import _runtime_and_job
    import control_plane.t3_execution_adapter as adapter_module

    d = _attack_door(scratch, monkeypatch)
    door_globals = type(d)._execute.__globals__

    launched = []

    class _RecordingAdapter:
        async def start(self, spec):
            launched.append(spec)
            return SimpleNamespace(provider_session_id="mcp:launch:j")

    monkeypatch.setattr(d, "_compose_adapter",
                        lambda *a, **k: (_RecordingAdapter(), {}))
    monkeypatch.setattr(d, "_seal_and_deliver",
                        lambda *a, **k: None)

    # --- leg 1: the fresh claim.  The intake's request job is JOB-REQ; the
    # attempt is claimed on the placement job JOB-PLACE.
    placement = SimpleNamespace(job_id="JOB-PLACE")
    monkeypatch.setitem(door_globals, "compose_child_execution",
                        lambda *a, **k: SimpleNamespace(
                            placement_job=placement))
    command = d.freeze_issue(_issue_row("iss-spec1"))
    entry = d.frozen[command]
    entry["job_id"] = "JOB-REQ"

    def fake_claim_job(job_id, **_kw):
        assert job_id == "JOB-PLACE"  # the claim is on the placement job
        return SimpleNamespace(
            attempt=SimpleNamespace(attempt_id="ATT-SPEC1",
                                    fence_generation=1),
            lease_token="lease-1")

    runtime = SimpleNamespace(attempts=SimpleNamespace(
        claim_job=fake_claim_job))
    d._execute(runtime, command, entry)
    assert len(launched) == 1
    # THE regression: the spec must name the attempt's own job, not the
    # request job — the engine's receipt-adoption check compares them.
    assert launched[0].job_id == "JOB-PLACE"
    assert launched[0].run_id == "ATT-SPEC1"
    # L3 (crash journey, same check family): the placement Job is created
    # by compose_child_execution with the runtime's default READ authority;
    # the launch spec must carry the SAME authority set or the engine's
    # receipt-adoption contract check refuses ("launch contract differs
    # from the durable Job").
    assert tuple(launched[0].authorities) == ("READ",)
    assert tuple(launched[0].allowed_artifact_paths) == ()

    # --- leg 2: the F1 relaunch of an attempt whose launch was never
    # attempted.  The frozen entry still names the request job; the attempt
    # row (a REAL runtime claim) names the job the engine will compare.
    real_runtime, real_job_id, _ = _runtime_and_job(tmp_path)
    lease = real_runtime.broker.claim(real_job_id, lease_owner="t4b-door")
    attempt_id = lease.attempt.attempt_id
    assert attempt_id is not None
    assert real_runtime.attempts.get_attempt(attempt_id).job_id == real_job_id

    monkeypatch.setitem(door_globals, "compose_child_execution",
                        lambda *a, **k: SimpleNamespace(
                            placement_job=SimpleNamespace(
                                job_id=real_job_id)))
    command2 = d.freeze_issue(_issue_row("iss-spec2"))
    entry2 = d.frozen[command2]
    entry2.update({"job_id": "JOB-REQ-2", "attempt_id": attempt_id,
                   "fence_generation": lease.attempt.fence_generation,
                   "lease_token": lease.lease_token, "phase": "claimed"})
    d._save_frozen()
    # no durable receipt: the F1 lane starts the claimed attempt (its first
    # and only launch); no launch-attempted flag exists
    monkeypatch.setattr(adapter_module, "SQLiteT3AdapterStateStore",
                        lambda _p: SimpleNamespace(load_run=lambda _r: None))
    d._execute(real_runtime, command2, entry2)
    assert len(launched) == 2
    assert launched[1].job_id == real_job_id  # the ATTEMPT's job
    assert launched[1].run_id == attempt_id


def test_step4_a_terminal_placement_frees_the_admission_ready_slot(
        scratch, monkeypatch, tmp_path):
    """Caught live by the wait-frees journey (2026-11-11): the admission-
    ledger Job is a record of WHO ASKED (compose_child_execution's own
    docstring) and the runtime's ready count is `QUEUED, never claimed` —
    nothing ever took a DELIVERED request's admission Job out of that
    queue, so fleet capacity never freed and the second task WAITed
    forever.  Finishing a sealed entry must retire its admission Job
    (the runtime's own typed cancel seam), idempotently."""
    from tests.test_executive_supervisor import _runtime_and_job
    from control_plane.child_execution_contracts import ChildExecutionRequest
    from control_plane.child_request_execution_composition import (
        compose_child_execution)

    runtime, _placement_job, _attempt = _runtime_and_job(tmp_path)
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-l2"))
    entry = d.frozen[command]
    request = ChildExecutionRequest.from_dict(dict(entry["envelope"]))
    composed = compose_child_execution(
        runtime, request=request, spec=d._spec(request),
        branch="t3/mmos-t4b-job-l2", worktree=str(scratch / "ws"))
    admission_job_id = composed.admission.job_id
    assert admission_job_id  # the admission record exists, QUEUED, no attempt
    entry.update({"job_id": admission_job_id, "attempt_id": "ATT-SEALED",
                  "phase": "sealed", "envelope": entry["envelope"]})
    d._save_frozen()
    # no delivery receipt exists and the seam re-drive is a no-op: the
    # finish path reports the honest refusal — the admission retirement
    # must still happen (the placement is terminal either way)
    monkeypatch.setattr(d, "_redrive_return_seam", lambda *a, **k: None)
    d._finish_sealed(runtime, entry)
    job = runtime.jobs.get_job(admission_job_id)
    status = getattr(job.status, "value", str(job.status))
    assert status == "CANCELLED"  # out of the ready queue
    # idempotent: replaying the finish path (a crash between seal and
    # finish, recovered twice) errors nothing and stays retired
    d._finish_sealed(runtime, entry)
    job2 = runtime.jobs.get_job(admission_job_id)
    assert getattr(job2.status, "value", str(job2.status)) == "CANCELLED"


def test_step4_a_recovered_run_seals_through_the_durable_neutral_ref(
        scratch, monkeypatch, tmp_path):
    """Caught live by the crash journey (2026-11-11, L4): the engine's
    supervisor-boundary projection hands the door a recovered ActiveRun whose
    process_ref is the TWIN shape (pid/pgid/process_start_identity/
    boot_session_id all None — the runtime's provider-managed recording
    shape), while the door seals through its OWN adapter (the reviewed
    inner adapter, whose start() returns the DURABLE NEUTRAL ref with
    pid=0/pgid=0).  ``_require_run_state`` compares the passed ref against
    the retained neutral ref and refused the door's own recovered run:
    "ref does not match the retained original ref" — the entry froze at
    execute-failed and the reconcile loop spun ALREADY_RECOVERED forever.
    The seal must run on the ADAPTER's durable neutral ref."""
    from dataclasses import replace as dataclass_replace
    from tests.test_executive_supervisor import _runtime_and_job
    from control_plane.t3_execution_adapter import _T3_REMOTE_BINARY_PLACEHOLDER
    from control_plane.worker_execution_contract import WorkerProcessRef
    import control_plane.t3_execution_adapter as adapter_module

    runtime, _job_id, _attempt = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(
        _job_id, lease_owner="t4b-door")
    attempt_id = lease.attempt.attempt_id
    assert attempt_id is not None

    neutral = WorkerProcessRef(
        run_id=attempt_id, pid=0, pgid=0, session_id=None,
        process_start_identity="t3:mcp:launch:twin:run:thread:x",
        boot_session_id="t3-native:mcp:launch:twin",
        launch_nonce="key-l4", provider_session_id="mcp:launch:twin",
        stdout_path="t3://thread/x/events", stderr_path="t3://thread/x/events",
        result_path="t3://thread/x/result", started_at="",
        binary=_T3_REMOTE_BINARY_PLACEHOLDER, base_sha="")
    twin = dataclass_replace(
        neutral, pid=None, pgid=None, process_start_identity=None,
        boot_session_id=None)
    assert twin != neutral  # the boundary projection's recording shape

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-l4"))
    entry = d.frozen[command]
    entry.update({"job_id": _job_id, "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "claimed",
                  "envelope": entry["envelope"]})
    d._save_frozen()

    # the durable receipt exists (the crashed door persisted it), so the
    # execute lane goes to the ENGINE recovery, and the recovered ActiveRun
    # is already in hand carrying the supervisor-boundary TWIN.
    monkeypatch.setattr(adapter_module, "SQLiteT3AdapterStateStore",
                        lambda _p: SimpleNamespace(
                            load_run=lambda _r: SimpleNamespace(
                                spec=object(), original_ref=neutral)))
    d._recovered[attempt_id] = SimpleNamespace(
        lease=SimpleNamespace(
            attempt=SimpleNamespace(fence_generation=2),
            lease_token="lease-recovered"),
        process_ref=twin)

    sealed = []

    class _DurableAdapter:
        def retained_original_ref(self, run_id):
            return neutral if run_id == attempt_id else None

    monkeypatch.setattr(d, "_compose_adapter",
                        lambda *a, **k: (_DurableAdapter(), {}))
    monkeypatch.setattr(d, "_seal_and_deliver",
                        lambda runtime_, entry_, attempt_, adapter_,
                        ref, branch:
                        sealed.append(ref))
    d._execute(runtime, command, entry)
    # THE regression: the seal ran exactly once, on the ADAPTER's durable
    # neutral ref — never on the supervisor-boundary twin (which the inner
    # adapter's retained-ref check refuses).
    assert len(sealed) == 1
    assert sealed[0] == neutral

    # --- leg 2: an adapter whose durable ref is NOT readable never seals a
    # translated or guessed ref — the entry parks with a typed blocker.
    command_b = d.freeze_issue(_issue_row("iss-l4b"))
    entry_b = d.frozen[command_b]
    entry_b.update({"job_id": _job_id, "attempt_id": attempt_id,
                    "fence_generation": 2, "lease_token": "lease-x",
                    "phase": "claimed", "envelope": entry_b["envelope"]})
    d._save_frozen()
    d._recovered[attempt_id] = SimpleNamespace(
        lease=SimpleNamespace(
            attempt=SimpleNamespace(fence_generation=2),
            lease_token="lease-recovered"),
        process_ref=twin)

    class _BlindAdapter:
        def retained_original_ref(self, _run_id):
            return None

    monkeypatch.setattr(d, "_compose_adapter",
                        lambda *a, **k: (_BlindAdapter(), {}))
    surfaced = []
    monkeypatch.setattr(d, "_surface_blocker",
                        lambda *a, **k: surfaced.append(a))
    d._execute(runtime, command_b, entry_b)
    assert sealed == [neutral]  # no second seal
    assert entry_b["phase"] == "reconcile-quarantined"
    assert entry_b["blocker"]["code"] == "RECOVERED_REF_UNREADABLE"


def test_step5_a_wait_longer_than_the_lease_still_seals(scratch, monkeypatch,
                                                        tmp_path):
    """Caught live by the round-4 crash journey (2026-11-11, L5): the engine
    adopts the recovered attempt with a FRESH lease, then the door honestly
    WAITS for the native run to finish — a wait longer than the lease made
    ``complete_attempt`` refuse (``StateConflict: attempt … lease has
    expired``) with the result in hand, and the entry froze execute-failed.
    A live owner extends its lease while its execution runs: the door
    heartbeats through the wait (the runtime's own typed seam), so the seal
    commits on credentials that are still current."""
    import time as _time
    from tests.test_executive_supervisor import _runtime_and_job
    from control_plane.worker_execution_contract import WorkerRunStatus

    runtime, job_id, _ = _runtime_and_job(tmp_path, lease_seconds=1)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    door_globals = type(d)._seal_and_deliver.__globals__
    command = d.freeze_issue(_issue_row("iss-l5"))
    entry = d.frozen[command]
    entry.update({"job_id": job_id, "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "reattached",
                  "envelope": entry["envelope"]})
    d._save_frozen()

    class _SlowAdapter:
        async def status(self, _ref):
            # longer than the 1s lease: without a renewal during the wait,
            # complete_attempt must refuse
            _time.sleep(2.5)
            return WorkerRunStatus.SUCCEEDED

        async def collect_result(self, _ref):
            return SimpleNamespace(result=SimpleNamespace(
                structured_output={"text": "done",
                                   "artifacts": ["branch:b"]}))

    ref = SimpleNamespace(provider_session_id="mcp:launch:l5")
    monkeypatch.setitem(door_globals, "ResultDeliveryRegistry",
                        lambda: SimpleNamespace(
                            register=lambda *a, **k: None))
    monkeypatch.setitem(door_globals, "install_execution_return_seam",
                        lambda *a, **k: None)
    monkeypatch.setitem(door_globals, "GitHubEvidenceSource",
                        lambda **k: None)
    finished = []
    monkeypatch.setattr(d, "_finish_sealed",
                        lambda *a, **k: finished.append(True))

    d._seal_and_deliver(runtime, entry, attempt_id, _SlowAdapter(), ref,
                        "t3/mmos-t4b-job-l5")
    # the seal committed on renewed credentials (an unrenewed 1s lease
    # would have expired 1.5s before complete_attempt)
    assert finished == [True]
    assert entry["phase"] == "sealed"
    assert entry["final_status"] == "COMPLETED"
    row = runtime.attempts.get_attempt(attempt_id)
    assert getattr(getattr(row, "status", None), "value", "") == "COMPLETED"


# ---------------------------------------------------------------------------
# Step 5 — the adversarial pass (deepseek-v4.1-flash, branch head 9bd78e5c9):
# findings F2, F3 and F5 in the door's seal lane and request gate.
# ---------------------------------------------------------------------------


def test_step5_f2_a_failed_native_run_with_a_result_is_sealed_failed(
        scratch, monkeypatch, tmp_path):
    """Attack F2 (MED): the seal lane never branched on the native verdict —
    ``complete_attempt`` unconditionally sealed COMPLETED, so a FAILED run
    that still carried a terminal result ref (the worker's failure text) was
    delivered as a completed job's Result.  The service-side finisher DOES
    branch (``_terminalize``); the two delivery lanes must agree.  A
    non-SUCCEEDED verdict seals FAILED through the same status-aware seam —
    the failure text still delivers, under an honest FAILED seal."""
    from tests.test_executive_supervisor import _runtime_and_job
    from control_plane.worker_execution_contract import WorkerRunStatus

    runtime, job_id, _ = _runtime_and_job(tmp_path, lease_seconds=30)
    lease = runtime.broker.claim(job_id, lease_owner="t4c-door")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    door_globals = type(d)._seal_and_deliver.__globals__
    command = d.freeze_issue(_issue_row("iss-f2"))
    entry = d.frozen[command]
    entry.update({"job_id": job_id, "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "reattached",
                  "envelope": entry["envelope"]})
    d._save_frozen()

    class _FailedRunAdapter:
        async def status(self, _ref):
            return WorkerRunStatus.FAILED

        async def collect_result(self, _ref):
            return SimpleNamespace(result=SimpleNamespace(
                structured_output={"text": "the worker's own failure report",
                                   "artifacts": []}))

    ref = SimpleNamespace(provider_session_id="mcp:launch:f2")
    monkeypatch.setitem(door_globals, "ResultDeliveryRegistry",
                        lambda: SimpleNamespace(
                            register=lambda *a, **k: None))
    monkeypatch.setitem(door_globals, "install_execution_return_seam",
                        lambda *a, **k: None)
    monkeypatch.setitem(door_globals, "GitHubEvidenceSource",
                        lambda **k: None)
    finished = []
    monkeypatch.setattr(d, "_finish_sealed",
                        lambda *a, **k: finished.append(True))

    d._seal_and_deliver(runtime, entry, attempt_id, _FailedRunAdapter(),
                        ref, "t3/mmos-t4b-job-f2")
    # the native verdict governs the seal, never an upgrade
    assert entry["phase"] == "sealed"
    assert entry["final_status"] == "FAILED"
    row = runtime.attempts.get_attempt(attempt_id)
    assert getattr(getattr(row, "status", None), "value", "") == "FAILED"
    job = runtime.jobs.get_job(job_id)
    assert getattr(job, "status", None).value == "FAILED"
    # the payload names the native verdict and still carries the worker's
    # own failure text — honest evidence, delivered
    summary = str((getattr(job, "result", None) or {}).get("summary", ""))
    assert "native run ended FAILED" in summary
    assert "the worker's own failure report" in summary
    # the delivery read still runs: the failure text reaches the task
    # under the FAILED seal (the seam is status-aware)
    assert finished == [True]


def test_step5_f3_a_never_terminal_run_parks_typed_never_polls_forever(
        scratch, monkeypatch, tmp_path):
    """Attack F3 (MED): after ``_wait_terminal``'s deadline it RETURNS the
    non-terminal status (it does not raise); ``_seal_and_deliver`` then
    called ``collect_result`` — which since L8b polls live status FOREVER —
    so one orphaned native thread blocked the door's single executor thread
    indefinitely: no cadence reconcile, no other entry served, no typed
    blocker, the door's own lease lapsing mid-poll.  A non-terminal wait
    now parks the entry with a typed NATIVE_RUN_TIMEOUT blocker and holds
    its slot (the attempt is still live engine-side); collect is never
    entered, and the entry retries on the reconcile cadence."""
    from tests.test_executive_supervisor import _runtime_and_job
    from control_plane.worker_execution_contract import WorkerRunStatus

    runtime, job_id, _ = _runtime_and_job(tmp_path, lease_seconds=30)
    lease = runtime.broker.claim(job_id, lease_owner="t4c-door")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-f3"))
    entry = d.frozen[command]
    entry.update({"job_id": job_id, "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "reattached",
                  "envelope": entry["envelope"]})
    d._save_frozen()

    waited = {}

    def deadline_expired(adapter, ref, *, runtime=None, entry=None,
                         **kwargs):
        # the faithful post-deadline state: _wait_terminal HONORS its
        # deadline (L5-proven) and returns the still-running status
        waited.update(kwargs)
        return (["STARTING", "RUNNING"], WorkerRunStatus.RUNNING)

    monkeypatch.setattr(d, "_wait_terminal", deadline_expired)

    class _OrphanedRunAdapter:
        collect_calls = 0

        async def collect_result(self, _ref):
            # the defect itself, made fast: polling a non-terminal run is
            # exactly what must never happen
            type(self).collect_calls += 1
            raise RuntimeError(
                "F3: collect_result must never poll a non-terminal run")

    surfaced = []
    monkeypatch.setattr(d, "_surface_blocker",
                        lambda *a, **k: surfaced.append(a))
    ref = SimpleNamespace(provider_session_id="mcp:launch:f3")
    d._seal_and_deliver(runtime, entry, attempt_id, _OrphanedRunAdapter(),
                        ref, "t3/mmos-t4b-job-f3")

    # collect was never entered; the park is typed and durable
    assert _OrphanedRunAdapter.collect_calls == 0
    assert entry["phase"] == "run-timeout"
    assert entry["blocker"]["code"] == "NATIVE_RUN_TIMEOUT"
    assert surfaced and surfaced[0][1] == "NATIVE_RUN_TIMEOUT"
    # the attempt is untouched engine-side: still active, never sealed
    row = runtime.attempts.get_attempt(attempt_id)
    assert getattr(getattr(row, "status", None), "value", "") not in (
        "COMPLETED", "FAILED", "LOST", "CANCELLED")
    # the slot HOLDS and the retry is cadence-paced: within the interval
    # the parked entry is not re-executed; once due, the seal is retried
    assert d._entry_action(entry) == "skip"
    entry["reconcile_last_ask"] = _iso(3600)
    assert d._entry_action(entry) == "execute"


def test_step5_f3_the_wait_reads_the_doors_own_deadline_knobs(
        scratch, monkeypatch, tmp_path):
    """Attack F3's config half: the 1800s/15s wait constants were hardcoded
    in the method signature — a canary or journey could not shorten them.
    The door passes its OWN ``wait_deadline_seconds`` /
    ``poll_interval_seconds`` config into the wait."""
    d = _attack_door(scratch, monkeypatch)
    d.config.wait_deadline_seconds = 12.5
    d.config.poll_interval_seconds = 1.5
    seen = {}

    def record(adapter, ref, *, deadline_s=None, interval_s=None, **_kw):
        seen["deadline"] = deadline_s
        seen["interval"] = interval_s
        from control_plane.worker_execution_contract import WorkerRunStatus
        return (["SUCCEEDED"], WorkerRunStatus.SUCCEEDED)

    monkeypatch.setattr(d, "_wait_terminal", record)
    entry = {"attempt_id": "ATT-K", "fence_generation": 1,
             "lease_token": "t", "phase": "reattached"}

    class _OkAdapter:
        async def collect_result(self, _ref):
            return SimpleNamespace(result=SimpleNamespace(
                structured_output={"text": "done", "artifacts": []}))

    runtime = SimpleNamespace(attempts=SimpleNamespace(
        complete_attempt=lambda *a, **k: SimpleNamespace(status="COMPLETED"),
        heartbeat_attempt=lambda *a, **k: None))
    door_globals = type(d)._seal_and_deliver.__globals__
    monkeypatch.setitem(door_globals, "ResultDeliveryRegistry",
                        lambda: SimpleNamespace(
                            register=lambda *a, **k: None))
    monkeypatch.setitem(door_globals, "install_execution_return_seam",
                        lambda *a, **k: None)
    monkeypatch.setitem(door_globals, "GitHubEvidenceSource",
                        lambda **k: None)
    monkeypatch.setattr(d, "_finish_sealed", lambda *a, **k: None)
    d._seal_and_deliver(runtime, entry, "ATT-K", _OkAdapter(),
                        SimpleNamespace(provider_session_id="mcp:k"),
                        "t3/mmos-t4b-job-k")
    assert seen["deadline"] == 12.5
    assert seen["interval"] == 1.5


def test_step5_f5_the_request_gate_refuses_degraded_timestamps(
        scratch, monkeypatch):
    """Attack F5 (LOW): the "newest agent comment" degraded to ARRIVAL order
    when any comment lacked a timestamp — and the carrier lists newest
    first, so ``[-1]`` picked the OLDEST agent comment: a stale request
    block could authorize admission.  An authorization gate refuses on
    degraded ordering evidence; and a timestamp-less BOARD row must not
    degrade the gate when the agent rows' own timestamps are complete."""
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-f5a"))
    entry = d.frozen[command]
    row = dict(_issue_row("iss-f5a"))

    # leg 1 — an agent comment WITHOUT a timestamp: the newest agent
    # request cannot be established, so the gate refuses typed
    d.paperclip = _CommentsPaperclip(row, [
        _agent("withdrew the request — no code needed",
               "2026-11-11T03:00:00Z"),
        {"authorType": "agent", "body": BLOCK},  # no createdAt
        _user("board note", "2026-11-11T01:00:00Z")])
    reply = asyncio.run(d.admit(command))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "TASK_STATE_UNREADABLE"
    assert "no timestamp" in reply["error"]["message"]
    assert "admit_requested_at" not in entry

    # leg 2 — the AGENT rows are fully timestamped: the gate orders by
    # the agent rows' OWN timestamps, so a timestamp-less board row
    # degrades nothing and the lawful newest request stands
    command_b = d.freeze_issue(_issue_row("iss-f5b"))
    d.paperclip = _CommentsPaperclip(dict(_issue_row("iss-f5b")), [
        _agent(BLOCK, "2026-11-11T02:00:00Z"),
        {"authorType": "user", "body": "board note"},  # no createdAt
        _agent("older answer, superseded", "2026-11-11T01:00:00Z")])
    monkeypatch.setattr(d, "_frame_context", lambda: {
        "principal": {}, "principal_context": {},
        "capability_profile_digest": "", "target_digest": ""})
    with pytest.raises(FileNotFoundError):
        # past the gate (the newest AGENT request stands) — the failure is
        # the not-started service socket, i.e. the admission lane itself
        asyncio.run(d.admit(command_b))
    assert d.frozen[command_b].get("admit_requested_at")


def test_r1_the_gate_binds_the_requesting_comment_to_the_assignee(
        scratch, monkeypatch):
    """T4c repair round 1, R1 (panel HIGH, 2026-11-11): the F10 gate never
    compared the authorizing comment's ``authorAgentId`` to the issue's
    assignee — any roster teammate's block-bearing comment authorized a run
    under the assignee's identity.  The gate now requires the NEWEST agent
    comment to be the assignee's own word.  When the newest agent comment is
    another agent's, the NEWEST wins and the gate refuses typed — the newest
    agent comment is the task's current instruction state (the same law the
    F10 newest-wins test already asserts for block semantics), so a foreign
    newer word makes the authorization ambiguous: admitting on an OLDER
    assignee row would mean silently ignoring a teammate's newer words on
    the assignee's task, and the gate cannot know whether that word cancels,
    supersedes or sits beside the request.  Like F5, an authorization gate
    refuses on ambiguous evidence; the refusal persists nothing, so the
    assignee's own newer block admits later."""
    d = _attack_door(scratch, monkeypatch)
    # a second REAL roster teammate, so the refusals below come from the
    # author binding, not the ASSIGNEE_NOT_ENROLLED roster check
    d.config.teammates = list(d.config.teammates) + ["ag-2"]
    assert "ag-2" in d.config.teammates

    # leg 1 — another roster teammate's block-bearing comment on the
    # assignee's issue is NOT the assignee's request: refused typed, and
    # the refusal burned nothing
    command = d.freeze_issue(_issue_row("iss-r1a"))
    entry = d.frozen[command]
    row = dict(_issue_row("iss-r1a"))
    assert row["assigneeAgentId"] == "ag-1"
    d.paperclip = _CommentsPaperclip(row, [
        _user("board note", "2026-11-11T01:00:00Z"),
        _agent_of("ag-2", BLOCK, "2026-11-11T02:00:00Z")])
    reply = asyncio.run(d.admit(command))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "REQUEST_AUTHOR_NOT_ASSIGNEE"
    assert "ag-2" in reply["error"]["message"]
    assert "admit_requested_at" not in entry

    # leg 2 — an agent comment with NO author id is equally foreign (a row
    # that cannot name its author cannot authorize the assignee's run)
    d.paperclip = _CommentsPaperclip(row, [
        {"authorType": "agent", "body": BLOCK,
         "createdAt": "2026-11-11T02:00:00Z"}])
    reply = asyncio.run(d.admit(command))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "REQUEST_AUTHOR_NOT_ASSIGNEE"
    assert "admit_requested_at" not in entry

    # leg 3 — the NEWEST agent comment is another agent's while an OLDER
    # valid one is the assignee's: the newest wins, so the gate refuses —
    # it must not hunt for an older assignee row it likes better
    command_b = d.freeze_issue(_issue_row("iss-r1b"))
    row_b = dict(_issue_row("iss-r1b"))
    d.paperclip = _CommentsPaperclip(row_b, [
        _agent_of("ag-1", BLOCK, "2026-11-11T02:00:00Z"),
        _agent_of("ag-2", "hands off — I am taking this one",
                  "2026-11-11T03:00:00Z")])
    reply = asyncio.run(d.admit(command_b))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "REQUEST_AUTHOR_NOT_ASSIGNEE"
    assert "admit_requested_at" not in d.frozen[command_b]

    # leg 4 — the assignee's OWN newest agent comment carries the block:
    # the gate admits (the failure past the gate is the not-started
    # service socket, the same shape as the F5 lawful-admit leg).  An
    # OLDER teammate comment beside it neither revokes nor authorizes.
    command_c = d.freeze_issue(_issue_row("iss-r1c"))
    row_c = dict(_issue_row("iss-r1c"))
    d.paperclip = _CommentsPaperclip(row_c, [
        _agent_of("ag-2", "old chatter from a teammate",
                  "2026-11-11T01:00:00Z"),
        _agent_of("ag-1", BLOCK, "2026-11-11T02:00:00Z")])
    monkeypatch.setattr(d, "_frame_context", lambda: {
        "principal": {}, "principal_context": {},
        "capability_profile_digest": "", "target_digest": ""})
    with pytest.raises(FileNotFoundError):
        asyncio.run(d.admit(command_c))
    assert d.frozen[command_c].get("admit_requested_at")  # lawful admit


def test_step6_the_launch_spec_names_the_placement_jobs_own_paths(
        scratch, monkeypatch, tmp_path):
    """Caught live by the round-4 lease-expiry journey (2026-11-11, L6): the
    recovery door died at register-worker — the service's startup reconcile
    quarantined on "worker recovery launch contract differs from durable
    Job".  Reproduced read-only on the scratch copy: the ADOPTED attempt's
    bound-path recovery check compares ``spec.workspace_path`` against the
    placement Job's OWN worktree and ``spec.result_schema_path`` against the
    engine's canonical ``worker-result.schema.json`` — but the door's launch
    spec named an attempt-scoped ``{run_id}-ws`` workspace and a bare
    ``schema.json``, so every reconcile AFTER the (successful) adoption
    refused the engine's own recovered run.  The spec must name the
    placement Job's paths at BOTH launch sites."""
    from control_plane.child_execution_contracts import ChildExecutionRequest
    from tests.test_executive_supervisor import _runtime_and_job
    import control_plane.t3_execution_adapter as adapter_module

    d = _attack_door(scratch, monkeypatch)
    door_globals = type(d)._execute.__globals__
    launched = []

    class _RecordingAdapter:
        async def start(self, spec):
            launched.append(spec)
            return SimpleNamespace(provider_session_id="mcp:launch:j")

    monkeypatch.setattr(d, "_compose_adapter",
                        lambda *a, **k: (_RecordingAdapter(), {}))
    monkeypatch.setattr(d, "_seal_and_deliver",
                        lambda *a, **k: None)
    placement = SimpleNamespace(job_id="JOB-PLACE")
    monkeypatch.setitem(door_globals, "compose_child_execution",
                        lambda *a, **k: SimpleNamespace(
                            placement_job=placement))
    command = d.freeze_issue(_issue_row("iss-l6"))
    entry = d.frozen[command]
    entry["job_id"] = "JOB-REQ"

    def fake_claim_job(job_id, **_kw):
        return SimpleNamespace(
            attempt=SimpleNamespace(attempt_id="ATT-SPEC6",
                                    fence_generation=1),
            lease_token="lease-6")

    runtime = SimpleNamespace(attempts=SimpleNamespace(
        claim_job=fake_claim_job))
    d._execute(runtime, command, entry)
    assert len(launched) == 1
    digest = ChildExecutionRequest.from_dict(
        dict(entry["envelope"])).request_digest
    # the placement Job's workspace is job-<digest>-ws (compose_child_
    # execution's worktree), NOT an attempt-scoped path
    assert str(launched[0].workspace_path) == str(
        scratch / "run" / "jobs" / f"job-{digest[:8]}-ws")
    # the engine's canonical result-schema name
    assert str(launched[0].result_schema_path).endswith(
        "worker-result.schema.json")

    # --- leg 2 (F1 relaunch): the spec carries the ATTEMPT's job worktree
    real_runtime, real_job_id, _ = _runtime_and_job(tmp_path)
    lease = real_runtime.broker.claim(real_job_id, lease_owner="t4b-door")
    attempt_id = lease.attempt.attempt_id
    job = real_runtime.jobs.get_job(real_job_id)
    monkeypatch.setitem(door_globals, "compose_child_execution",
                        lambda *a, **k: SimpleNamespace(
                            placement_job=SimpleNamespace(
                                job_id=real_job_id)))
    command2 = d.freeze_issue(_issue_row("iss-l6b"))
    entry2 = d.frozen[command2]
    entry2.update({"job_id": "JOB-REQ-6", "attempt_id": attempt_id,
                   "fence_generation": lease.attempt.fence_generation,
                   "lease_token": lease.lease_token, "phase": "claimed"})
    d._save_frozen()
    monkeypatch.setattr(adapter_module, "SQLiteT3AdapterStateStore",
                        lambda _p: SimpleNamespace(load_run=lambda _r: None))
    d._execute(real_runtime, command2, entry2)
    assert len(launched) == 2
    assert str(launched[1].workspace_path) == str(job.worktree)
    assert str(launched[1].result_schema_path).endswith(
        "worker-result.schema.json")


def test_step7_job_state_counts_native_launches_per_attempt(
        scratch, monkeypatch):
    """Caught live by the round-4 wait-frees journey (2026-11-11, L7): the
    census file is per-SCRATCH, but ``job_state`` answered a COMMAND's
    "native launches" with the whole-file count — two tasks that each
    launched exactly once both reported 2, and the journey's per-task
    exactly-once proof could not pass.  The per-job launch port now tags
    its census rows with the attempt it was composed for, and a command's
    state counts only ITS attempt's tagged launches."""
    d = _attack_door(scratch, monkeypatch)
    command_a = d.freeze_issue(_issue_row("iss-l7a"))
    d.frozen[command_a].update({"job_id": "JOB-A", "attempt_id": "ATT-A"})
    command_b = d.freeze_issue(_issue_row("iss-l7b"))
    d.frozen[command_b].update({"job_id": "JOB-B", "attempt_id": "ATT-B"})
    # one tagged launch per attempt, one untagged row (the service-side
    # port records untagged), and reads never count
    d._record_census("t3_thread_launch", {"clientRequestId": "x"})
    d._record_census("t3_thread_read", {}, attempt_id="ATT-A")
    d._record_census("t3_thread_launch", {"clientRequestId": "a"},
                     attempt_id="ATT-A")
    d._record_census("t3_thread_launch", {"clientRequestId": "b"},
                     attempt_id="ATT-B")
    assert d.job_state(command_a)["native_launches"] == 1
    assert d.job_state(command_b)["native_launches"] == 1
    # an entry with no attempt yet has no launch of its own — never the
    # whole scratch's
    command_c = d.freeze_issue(_issue_row("iss-l7c"))
    assert d.job_state(command_c)["native_launches"] == 0
    # source law: every adapter composition names the attempt it launches
    # (one first claim, three fresh=False compositions: F1 relaunch, the
    # engine-recovered seal, and the return-seam re-drive), so no census
    # row is ever tagged with a guess
    src = Path(DOOR_SRC).read_text(encoding="utf-8")
    assert src.count("self._compose_adapter(") == 4
    assert src.count("fresh=True, attempt_id=attempt_id") == 1
    assert src.count("fresh=False, attempt_id=attempt_id") == 3
