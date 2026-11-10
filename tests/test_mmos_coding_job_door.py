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
