"""Integration tests for the T4b coding-job door (tools/mmos_coding_job).

The real scratch composition, no dev instances needed: an
``ExecutiveControlService`` on a tmp scratch root with the CEO-ingress
socket, the real L4 ``LocalOperatorListener`` serving the carrier's two
routes, host-frozen ``child_request_material`` from the envelope builder,
and the private selected-child admit frame over the real socket. The dev
Paperclip and dev T3 server are deliberately UNREACHABLE — intake and the
executor degrade honestly; this file proves the admission lane.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_mmos_coding_job_door.py
"""
import asyncio
import importlib.util
import json
import os
import socket
import tempfile
from pathlib import Path

import pytest

HERE = os.path.dirname(__file__)
DOOR_SRC = os.path.join(HERE, "..", "tools", "mmos_coding_job", "door.py")
spec = importlib.util.spec_from_file_location("t4b_door", DOOR_SRC)
door_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(door_mod)


def _socket_request(path, method, target, body=None):
    payload = json.dumps(body).encode() if body is not None else b""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(30.0)
    conn.connect(str(path))
    try:
        head = (f"{method} {target} HTTP/1.0\r\nHost: door\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Content-Type: application/json\r\n\r\n").encode("ascii")
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
    status_line, _, resp = raw.partition(b"\r\n\r\n")
    status = int(status_line.split(b" ", 2)[1])
    return status, json.loads(resp or b"{}")


def _make_door(scratch: Path):
    config = door_mod.DoorConfig({
        "scratch_root": str(scratch),
        "paperclip_base_url": "http://127.0.0.1:3199",  # deliberately dead
        "paperclip_company_id": "cmp-test",
        "t3": {
            # A dead port INSIDE the dev range: the pairing CLI leg is pinned
            # to this same server, so no leg can reach the live T3 app.
            "proof_base_url": "http://127.0.0.1:3799",
            "home_dir": str(scratch / "t3home"),
            "port": 3799,
            "token_path": str(scratch / "worker-token.txt"),
            "token_label": "t4b-door-worker",
            "project_id": "proj-test",
            "model_selection": '{"instanceId":"x","model":"m"}',
        },
        "intake_poll_seconds": 60.0,
    })
    return door_mod.CodingJobDoor(config)


def _config(scratch, t3_overrides=None):
    values = {
        "scratch_root": str(scratch),
        "paperclip_base_url": "http://127.0.0.1:3190",
        "paperclip_company_id": "c",
        "t3": {
            "proof_base_url": "http://127.0.0.1:3800",
            "home_dir": str(scratch / "t3home"),
            "port": 3800,
            "token_path": "/x", "project_id": "p",
            "model_selection": "{}"},
    }
    if t3_overrides:
        values["t3"].update(t3_overrides)
    return values


def _issue_row(issue_id="iss-1", title="T4b task", description="do the thing"):
    return {"id": issue_id, "identifier": f"MAS-{issue_id[-1]}",
            "title": title, "description": description,
            "assigneeAgentId": "ag-1", "status": "todo"}


@pytest.fixture
def scratch(tmp_path):
    with tempfile.TemporaryDirectory(prefix="t4b-door-", dir="/tmp") as td:
        yield Path(td)


def test_config_refuses_non_loopback_paperclip(scratch):
    for bad in ("http://paperclip.internal:3100/",
                "https://127.0.0.1:3100/"):  # https is not the dev surface
        values = _config(scratch)
        values["paperclip_base_url"] = bad
        with pytest.raises(ValueError):
            door_mod.DoorConfig(values)


def test_config_requires_the_dev_server_pin(scratch):
    # The pairing helper's CLI leg selects its server by T3CODE_HOME /
    # T3CODE_PORT, not by the base URL; without the pin it silently mints
    # against the LIVE T3 app (the recorded incident).  Config law closes
    # that: home_dir+port required, port inside the dev range, base == port.
    with pytest.raises(ValueError, match="home_dir"):
        door_mod.DoorConfig(_config(scratch, {"home_dir": ""}))
    with pytest.raises(ValueError, match="dev-server port"):
        door_mod.DoorConfig(_config(scratch, {
            "port": 3773,  # the LIVE T3 app — never a legal target
            "proof_base_url": "http://127.0.0.1:3773"}))
    with pytest.raises(ValueError, match="same dev server"):
        door_mod.DoorConfig(_config(scratch, {
            "proof_base_url": "http://127.0.0.1:3801"}))  # != port 3800


def test_admit_replay_conflict_wait_and_unfrozen_round_trip(scratch,
                                                            monkeypatch):
    """The whole admission lane over the real operator socket: freeze →
    ADMITTED → REPLAY (same job) → digest conflict → WAIT (queue full) →
    unfrozen command refused."""
    async def exercise():
        d = _make_door(scratch)
        await d.start()

        def ask(method, target, body=None):
            # Off the loop thread: the door's listener serves on THIS loop,
            # and a blocking socket read on the loop thread would deadlock.
            return _socket_request(scratch / "run" / "local-operator.sock",
                                   method, target, body)

        try:
            operator = scratch / "run" / "local-operator.sock"
            assert operator.exists()

            # unfrozen command first: precise refusal, nothing admitted
            status, body = await asyncio.to_thread(
                ask, "POST", "/paperclip/coding-job/admit",
                {"command": "child-request:" + "0" * 64})
            assert status == 200 and body["ok"] is False
            assert body["error"]["code"] == "invalid_input"

            # freeze two tasks at intake (registration, not admission)
            command_one = d.freeze_issue(_issue_row("iss-1"))
            command_two = d.freeze_issue(_issue_row("iss-2"))
            assert command_one and command_two and command_one != command_two
            assert command_one in d.frozen

            # one admit: ADMITTED with a job id
            status, body = await asyncio.to_thread(
                ask, "POST", "/paperclip/coding-job/admit",
                {"command": command_one})
            assert status == 200 and body["ok"] is True
            result = body["result"]
            assert result["state"] == "ADMITTED"
            assert result["job_id"]
            job_one = result["job_id"]
            assert d.frozen[command_one]["job_id"] == job_one
            # the admit lane durably records request and outcome (F3
            # narrowed after the live default-journey re-run — registration
            # alone must never become admission)
            assert d.frozen[command_one]["admit_requested_at"]
            assert d.frozen[command_one]["admit_outcome"] == "ADMITTED"
            assert d._entry_action(d.frozen[command_one]) == "execute"

            # same command again: REPLAY names the SAME job, never a second
            status, body = await asyncio.to_thread(
                ask, "POST", "/paperclip/coding-job/admit",
                {"command": command_one})
            assert status == 200 and body["result"]["state"] == "REPLAY"
            assert body["result"]["job_id"] == job_one

            # a DIFFERENT VALID envelope re-frozen under the same triple
            # (the task-edited-after-intake case): precise conflict, never a
            # silent re-admission.  Tampering a field in place would break
            # the envelope's own request_digest and answer invalid_input.
            from tools.mmos_coding_job.envelope import build_task_request
            edited = build_task_request(
                issue_id="iss-1", agent_id="ag-1",
                company_id=d.config.paperclip_company_id,
                title="T4b task EDITED", description="do the thing",
                key="coding-job-1")
            d.frozen[command_one]["envelope"] = edited.to_dict()
            d._refreeze_binding()
            status, body = await asyncio.to_thread(
                ask, "POST", "/paperclip/coding-job/admit",
                {"command": command_one})
            assert status == 200 and body["ok"] is False
            assert body["error"]["code"] == "conflict"

            # state read carries the admitted identity
            status, body = await asyncio.to_thread(
                ask, "GET",
                f"/paperclip/coding-job/state/{command_one}")
            assert status == 200
            assert body["job_id"] == job_one and body["issue"]["id"] == "iss-1"

            # queue-full: the FLEET ready cap binds across roots (the
            # per-root cap cannot: one job key per root); one queued job
            # + fleet limit 1 makes the second task's admit a precise WAIT
            monkeypatch.setenv("MMOS_CHILD_FLEET_READY_LIMIT", "1")
            status, body = await asyncio.to_thread(
                ask, "POST", "/paperclip/coding-job/admit",
                {"command": command_two})
            assert status == 200 and body["ok"] is True
            assert body["result"]["state"] == "WAIT"
            assert body["result"]["wait_reason"] == "CHILD_QUEUE_FLEET_READY_FULL"
            assert body["result"]["wait_detail"]
            assert not d.frozen[command_two].get("job_id")
            # a WAIT was answered: the executor must not re-ask it (the
            # carrier's next wake owns the retry)
            assert d.frozen[command_two]["admit_requested_at"]
            assert d.frozen[command_two]["admit_outcome"] == "WAIT"
            assert d._entry_action(d.frozen[command_two]) == "skip"
        finally:
            await d.stop()
    asyncio.run(exercise())


def test_executor_survives_dead_dev_instances_and_door_stops_clean(scratch):
    """The intake poller and the executor thread degrade honestly against
    unreachable dev instances; stop() closes the service and the socket."""
    async def exercise():
        env_keys = ("T3_PROOF_BASE_URL", "T3CODE_HOME", "T3CODE_PORT")
        before = {k: os.environ.get(k) for k in env_keys}
        d = _make_door(scratch)
        await d.start()
        operator = scratch / "run" / "local-operator.sock"
        await asyncio.to_thread(d.intake_poll_once)  # dead: log line only
        assert d._executor_thread.is_alive()
        await d.stop()
        assert not d._executor_thread.is_alive()
        assert not operator.exists()
        # in-process use restores the ambient T3 selection env
        assert {k: os.environ.get(k) for k in env_keys} == before
    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# attack-review fixes (integrations/mmos/T4B_ATTACK_FINDINGS.md)
# ---------------------------------------------------------------------------


class _FakePaperclip:
    """Records blocker comments without a live dev Paperclip."""

    def __init__(self):
        self.comments: list[tuple[str, str]] = []

    def add_comment(self, issue_id, body):
        self.comments.append((issue_id, body))
        return {"ok": True}


def _attack_door(scratch, monkeypatch):
    d = _make_door(scratch)
    d.paperclip = _FakePaperclip()  # type: ignore[assignment]
    return d


def test_f5_atomic_frozen_save_never_loses_the_last_good_state(
        scratch, monkeypatch):
    import os as _os
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-a"))
    d.frozen[command]["job_id"] = "JOB-KEEP"
    d._save_frozen()
    good = d.frozen_path.read_text(encoding="utf-8")

    def boom(*_a, **_k):
        raise OSError("crash exactly at the rename point")

    monkeypatch.setattr(_os, "replace", boom)
    with pytest.raises(OSError):
        d._save_frozen()  # a later mutation dies at the rename
    # the durable file still holds the LAST GOOD state — the old
    # truncate-in-place write destroyed it exactly here
    assert d.frozen_path.read_text(encoding="utf-8") == good
    assert "JOB-KEEP" in json.loads(good)[command]["job_id"]


def test_f7_thread_budget_is_released_at_terminal_phases(scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    assert d._reserve_thread("job:a") is True
    assert d._reserve_thread("job:b") is True
    assert d._reserve_thread("job:c") is False  # the two-job ceiling
    d._release_thread("job:a")
    assert d._reserve_thread("job:c") is True   # the slot came back
    d._release_thread("job:a")                  # idempotent
    d._release_thread("job:never-reserved")
    budget = json.loads(d._budget.read_text())
    assert sorted(budget["reserved"]) == ["job:b", "job:c"]


def test_f6_entry_action_routes_every_phase_once(scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    assert d._entry_action({"phase": "delivered"}) == "skip"
    assert d._entry_action({"blocker_surfaced": "X"}) == "skip"
    # registration is NOT a request: frozen-but-never-asked entries are
    # never admitted by the door (the live default-journey regression)
    assert d._entry_action({}) == "skip"
    assert d._entry_action({"admit_requested_at": "t"}) == "admit"
    # a WAIT/refusal was already answered — the carrier owns the retry
    assert d._entry_action(
        {"admit_requested_at": "t", "admit_outcome": "WAIT"}) == "skip"
    assert d._entry_action(
        {"admit_requested_at": "t", "admit_outcome": "conflict"}) == "skip"
    assert d._entry_action({"job_id": "J"}) == "execute"     # fresh claim
    assert d._entry_action({"job_id": "J", "phase": "claimed"}) == "execute"
    assert d._entry_action({"job_id": "J", "phase": "launched"}) == "execute"
    assert d._entry_action({"job_id": "J", "phase": "sealed"}) == "finish-sealed"
    for parked in ("delivery-refused", "execute-failed",
                   "launch-uncertain", "admission-refused"):
        assert d._entry_action({"job_id": "J", "phase": parked}) == "blocker"


def test_f6_finish_sealed_reads_the_receipt_and_finishes_the_entry(
        scratch, monkeypatch):
    from types import SimpleNamespace
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-s"))
    entry = d.frozen[command]
    entry.update({"job_id": "JOB-S", "attempt_id": "ATT-S", "phase": "sealed"})

    event = SimpleNamespace(
        attempt_id="ATT-S",
        payload={"delivery": {"state": "delivered",
                              "transport_ref": "paperclip:x:y:z"}})
    runtime = SimpleNamespace(store=SimpleNamespace(
        list_events=lambda **_kw: [event]))
    d._finish_sealed(runtime, entry)
    assert entry["phase"] == "delivered"
    assert entry["delivery"]["transport_ref"] == "paperclip:x:y:z"
    # budget-exhausted is NOT parked: a released slot may revive it later

    # the refused branch parks with the exact refusal code
    entry2 = d.frozen[d.freeze_issue(_issue_row("iss-r"))]
    entry2.update({"job_id": "JOB-R", "attempt_id": "ATT-R",
                   "phase": "sealed"})
    refused = SimpleNamespace(
        attempt_id="ATT-R",
        payload={"delivery": {"state": "refused",
                              "refusal_code": "ORIGIN_KIND_UNKNOWN"}})
    runtime2 = SimpleNamespace(store=SimpleNamespace(
        list_events=lambda **_kw: [refused]))
    d._finish_sealed(runtime2, entry2)
    assert entry2["phase"] == "delivery-refused"
    assert entry2["blocker"]["code"] == "ORIGIN_KIND_UNKNOWN"
    assert d.paperclip.comments and "ORIGIN_KIND_UNKNOWN" in (
        d.paperclip.comments[0][1])


def test_f3_orphaned_admission_is_healed_by_idempotent_replay(
        scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-o"))
    entry = d.frozen[command]
    # the crash window: the carrier's admit was REQUESTED and committed in
    # the engine, but the outcome/job_id never reached the frozen record
    entry["admit_requested_at"] = "2026-11-10T00:00:00+00:00"
    d._save_frozen()
    assert not entry.get("job_id")

    async def fake_admit(cmd):
        assert cmd == command
        # exactly what the real admit() persists on a REPLAY reply
        entry["job_id"] = "JOB-HEALED"
        entry["admit_outcome"] = "REPLAY"
        return {"ok": True, "result": {"state": "REPLAY",
                                       "job_id": "JOB-HEALED"}}

    monkeypatch.setattr(d, "admit", fake_admit)
    d._ensure_admitted(command, entry)
    assert entry["job_id"] == "JOB-HEALED"
    assert json.loads(d.frozen_path.read_text())[command]["job_id"] == (
        "JOB-HEALED")
    assert d._entry_action(entry) == "execute"   # healed; the job proceeds


def test_f3_hard_readmission_refusal_parks_with_the_code(
        scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-p"))
    entry = d.frozen[command]
    entry["admit_requested_at"] = "2026-11-10T00:00:00+00:00"
    d._save_frozen()

    async def fake_admit(_cmd):
        entry["admit_outcome"] = "conflict"   # what the real admit persists
        return {"ok": False, "error": {"code": "conflict",
                                       "message": "digest mismatch"}}

    monkeypatch.setattr(d, "admit", fake_admit)
    d._ensure_admitted(command, entry)
    assert entry["phase"] == "admission-refused"
    assert entry["blocker"]["code"] == "conflict"
    assert d.paperclip.comments and "conflict" in d.paperclip.comments[0][1]
    # a WAIT is transient: answered, no park, no comment; the carrier's
    # next wake owns the retry, not the door
    command2 = d.freeze_issue(_issue_row("iss-w"))
    entry2 = d.frozen[command2]
    entry2["admit_requested_at"] = "2026-11-10T00:00:00+00:00"

    async def wait_admit(_cmd):
        entry2["admit_outcome"] = "WAIT"
        return {"ok": True, "result": {"state": "WAIT",
                                       "wait_reason": "QUEUE_FULL"}}

    monkeypatch.setattr(d, "admit", wait_admit)
    d._ensure_admitted(command2, entry2)
    assert entry2.get("phase") is None
    assert not entry2.get("blocker")
    assert d._entry_action(entry2) == "skip"
    assert len(d.paperclip.comments) == 1  # only the refusal comment


def test_f1_launch_never_attempted_continues_the_same_claimed_attempt(
        scratch, monkeypatch, tmp_path):
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-f1"))
    entry = d.frozen[command]
    entry.update({"job_id": "JOB-F1", "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "claimed"})
    d._save_frozen()
    # crash window: claimed, persisted — but NO receipt (the door's adapter
    # store is empty) and NO launch-attempted flag

    started: list = []

    class _FakeAdapter:
        async def start(self, spec):
            started.append(spec.run_id)
            from types import SimpleNamespace
            return SimpleNamespace(provider_session_id="mcp:launch:new")

    sealed: list = []

    monkeypatch.setattr(d, "_compose_adapter",
                        lambda *_a, **_k: (_FakeAdapter(), {}))
    monkeypatch.setattr(d, "_seal_and_deliver",
                        lambda *a, **k: sealed.append(a[2]))
    d._execute(runtime, command, entry)

    assert started == [attempt_id]        # the SAME attempt, its first launch
    assert sealed == [attempt_id]         # and it continues to the seal
    assert entry["phase"] == "launched"
    # the launch flag is now durable, so a further crash in the same window
    # is classified UNCERTAIN, never launched twice
    assert (scratch / "run" / "jobs" / attempt_id
            / "launch-attempted").exists()
    # exactly one attempt exists — no re-claim, no second job
    attempts = [a for a in runtime.attempts.list_attempts()
                if a.job_id == job_id]
    assert len(attempts) == 1


def test_f1_attempted_launch_without_receipt_parks_never_relaunches(
        scratch, monkeypatch, tmp_path):
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-f1b"))
    entry = d.frozen[command]
    entry.update({"job_id": "JOB-F1B", "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "claimed"})
    d._save_frozen()
    # the crash happened AFTER adapter.start was called but BEFORE the
    # receipt was durable: unknowable, must park
    flag = scratch / "run" / "jobs" / attempt_id / "launch-attempted"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("now", encoding="utf-8")

    def fail(**_kw):
        raise AssertionError("no adapter may be composed for an "
                             "uncertain launch")

    monkeypatch.setattr(d, "_compose_adapter", fail)
    d._execute(runtime, command, entry)

    assert entry["phase"] == "launch-uncertain"
    assert entry["blocker"]["code"] == "LAUNCH_UNCERTAIN"
    assert d.paperclip.comments and "LAUNCH_UNCERTAIN" in (
        d.paperclip.comments[0][1])
    # surfaced blocker = terminal for this executor: never re-executed
    assert d._entry_action(entry) == "skip"


def test_f2_recovery_skips_record_process_when_identity_is_durable(
        scratch, monkeypatch, tmp_path):
    """Crash AFTER record_process, BEFORE adopt/seal: the fresh door must
    reattach and adopt without the StateConflict that misreported a
    succeeded job as EXECUTOR_FAILED."""
    from types import SimpleNamespace
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id
    runtime.attempts.record_process(
        attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="mcp:launch:already-durable")

    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-f2"))
    entry = d.frozen[command]
    entry.update({"job_id": "JOB-F2", "attempt_id": attempt_id,
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token, "phase": "claimed"})
    d._save_frozen()

    class _FakeAdapter:
        async def reattach(self, spec, binding):
            assert binding.process_ref is not None
            return SimpleNamespace(
                provider_session_id="mcp:launch:already-durable")

    # a real WorkerLaunchSpec with its real prompt file — bind() verifies
    # the recovery prompt bytes against the spec
    real_spec = d._launch_spec(
        run_id=attempt_id, job_id="JOB-F2",
        prompt=d._worker_prompt(attempt_id,
                                "t3/mmos-t4b-job-deadbeef"))
    fake_run = SimpleNamespace(
        spec=real_spec,
        original_ref=SimpleNamespace(provider_session_id="x", pid=None,
                                     run_id=attempt_id))

    class _FakeStore:
        def load_run(self, run_id):
            return fake_run

    import control_plane.t3_execution_adapter as adapter_module
    monkeypatch.setattr(adapter_module, "SQLiteT3AdapterStateStore",
                        lambda _path: _FakeStore())
    monkeypatch.setattr(d, "_compose_adapter",
                        lambda *_a, **_k: (_FakeAdapter(), {}))
    monkeypatch.setattr(d, "_seal_and_deliver", lambda *a, **k: None)

    # OLD behavior: record_process raises StateConflict here and the
    # executor records EXECUTOR_FAILED for a job that actually succeeded.
    d._execute(runtime, command, entry)

    row = runtime.attempts.get_attempt(attempt_id)
    assert row.provider_session_id == "mcp:launch:already-durable"
    assert row.lease_owner == "t4b-door-recovery"   # the adoption happened
    assert entry["phase"] == "reattached"
