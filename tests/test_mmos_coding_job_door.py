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
        "paperclip_allowed": ["127.0.0.1:3199"],
        "paperclip_company_id": "cmp-test",
        "paperclip_service_agent_id": "ag-pf-delivery",
        "teammates": ["ag-1"],
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
        "paperclip_allowed": ["127.0.0.1:3190"],
        "paperclip_company_id": "c",
        "paperclip_service_agent_id": "ag-pf-delivery",
        "teammates": ["ag-1"],
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


# ---------------------------------------------------------------------------
# PF-3 item 1: the delivery writer identity is config law, and no header
# value ever reaches an error text at the door's Paperclip client boundary.
# ---------------------------------------------------------------------------


def test_pf3_config_requires_service_agent_id_when_delivering(scratch):
    """A config that would deliver without a writer identity refuses at
    load with a typed ValueError naming the field; a config that does not
    deliver (register_transport false) does not require it."""
    values = _config(scratch)
    del values["paperclip_service_agent_id"]
    with pytest.raises(ValueError, match="paperclip_service_agent_id"):
        door_mod.DoorConfig(values)
    for bad in ("", "   ", None, 7):
        values["paperclip_service_agent_id"] = bad
        with pytest.raises(ValueError, match="paperclip_service_agent_id"):
            door_mod.DoorConfig(values)
    values = _config(scratch)
    del values["paperclip_service_agent_id"]
    values["register_transport"] = False
    cfg = door_mod.DoorConfig(values)
    assert cfg.register_transport is False


def test_pf3_client_error_never_leaks_header_values(scratch):
    """http.client's putheader rejects a newline-bearing header value with
    a ValueError that QUOTES the value — before any connection is made.
    The door's client logs str(exc) into logs, blocker reasons and the
    frozen record, so the text must be scrubbed at the client boundary."""
    sentinel = "SENTINEL-DOOR-4c8f"
    values = _config(scratch)
    values["paperclip_headers"] = {
        "authorization": f"Bearer {sentinel}\ninjected"}
    client = door_mod.PaperclipLoopbackClient(door_mod.DoorConfig(values))
    with pytest.raises(Exception) as caught:
        client.add_comment("iss-1", "[coding-job] probe")
    assert sentinel not in str(caught.value), \
        "the client's exception text quoted a header value"


# ---------------------------------------------------------------------------
# T4d prep: the dev T3 port range is an EXPLICIT opt-in so a lane can pin its
# own dev range (PF: 3830-3839).  The DEFAULT stays 3790-3810 and every
# refusal stays.  These tests fail on the pre-T4d door (the range is hardcoded
# and `dev_port_range` is ignored).
# ---------------------------------------------------------------------------


def test_t4d_dev_port_range_is_explicit_opt_in_default_unchanged(scratch):
    # DEFAULT stays 3790-3810: a PF port is refused without explicit config.
    with pytest.raises(ValueError, match="dev-server port"):
        door_mod.DoorConfig(_config(scratch, {
            "port": 3830, "proof_base_url": "http://127.0.0.1:3830"}))
    # The canonical dead dev port stays legal by default (no range field).
    door_mod.DoorConfig(_config(scratch, {
        "port": 3799, "proof_base_url": "http://127.0.0.1:3799"}))
    # An EXPLICIT PF range admits its own ports.
    cfg = door_mod.DoorConfig(_config(scratch, {
        "port": 3830, "proof_base_url": "http://127.0.0.1:3830",
        "dev_port_range": [3830, 3839]}))
    assert cfg.t3_port == 3830
    assert (cfg.t3_dev_port_first, cfg.t3_dev_port_last) == (3830, 3839)
    door_mod.DoorConfig(_config(scratch, {
        "port": 3839, "proof_base_url": "http://127.0.0.1:3839",
        "dev_port_range": [3830, 3839]}))
    # Just outside the configured range is still refused.
    for port in (3829, 3840):
        with pytest.raises(ValueError, match="dev-server port"):
            door_mod.DoorConfig(_config(scratch, {
                "port": port, "proof_base_url": f"http://127.0.0.1:{port}",
                "dev_port_range": [3830, 3839]}))
    # A malformed range is refused, never silently widened to a default.
    for bad in ([3839, 3830], [3830], "3830-3839", [3830, 3839, 3840],
                [0, 70000], [3830, True], [3830.0, 3839.0]):
        with pytest.raises(ValueError, match="dev_port_range"):
            door_mod.DoorConfig(_config(scratch, {
                "port": 3830, "proof_base_url": "http://127.0.0.1:3830",
                "dev_port_range": bad}))


def test_t4d_real_ports_stay_refused_under_the_pf_range(scratch):
    # The PF door points at 3830-3839.  Every real / neighbour port must stay
    # refused as a T3 target under that range — the configurable range can
    # never be used to reach a live service or another lane's port.
    for port in (3773, 3774, 3780, 3100, 3190, 3193, 3796, 3800):
        with pytest.raises(ValueError, match="dev-server port"):
            door_mod.DoorConfig(_config(scratch, {
                "port": port, "proof_base_url": f"http://127.0.0.1:{port}",
                "dev_port_range": [3830, 3839]}))
    # The reserved Paperclip neighbour refusals are unchanged (F9): these are
    # refused as Paperclip targets even when explicitly allowlisted.
    for port in (3100, 3179, 3773, 3774, 3780):
        values = _config(scratch)
        values["paperclip_base_url"] = f"http://127.0.0.1:{port}"
        values["paperclip_allowed"] = [f"127.0.0.1:{port}"]
        with pytest.raises(ValueError, match="reserved"):
            door_mod.DoorConfig(values)


def test_t4d_a_wide_custom_range_cannot_reach_a_real_port(scratch):
    # A configured range that SPANS a real port must not make it legal: the
    # range widens dev ports, never the real ones.  (Lead review: a range
    # such as [3770, 3810] would otherwise admit the live team server 3780.)
    for port in (3773, 3774, 3780, 3784, 3100, 3179, 3190, 3193, 3796, 3800):
        with pytest.raises(ValueError, match="real service"):
            door_mod.DoorConfig(_config(scratch, {
                "port": port, "proof_base_url": f"http://127.0.0.1:{port}",
                "dev_port_range": [3000, 3900]}))
    for port in (45003, 54329):
        with pytest.raises(ValueError, match="real service"):
            door_mod.DoorConfig(_config(scratch, {
                "port": port, "proof_base_url": f"http://127.0.0.1:{port}",
                "dev_port_range": [1024, 65535]}))


def test_t4d_a_disabled_config_is_refused(scratch):
    # `enabled: false` is a REAL refusal, not an inert label: a prepared
    # example can never construct a runnable door.  The principal switches
    # it on by removing the flag (a deliberate act), never by accident.
    values = _config(scratch)
    values["enabled"] = False
    with pytest.raises(ValueError, match="disabled"):
        door_mod.DoorConfig(values)
    # The example shipped in the repo is disabled and is refused as-is.
    example = (Path(HERE) / ".." / "integrations" / "mmos" / "pf"
               / "t4d_door.pf.example.json").resolve()
    data = json.loads(example.read_text(encoding="utf-8"))
    assert data["enabled"] is False
    with pytest.raises(ValueError, match="disabled"):
        door_mod.DoorConfig(data)
    # REV-DOOR F2: a falsy or mistyped flag is a refusal too.
    for bad in ("false", 0, None, "true", 1):
        values["enabled"] = bad
        with pytest.raises(ValueError, match="disabled"):
            door_mod.DoorConfig(values)
    # REV-DOOR F5: the file path (DoorConfig.load) refuses the example as well.
    on_disk = scratch / "t4d_door.example.json"
    on_disk.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="disabled"):
        door_mod.DoorConfig.load(str(on_disk))
    # `enabled: true` (or absent) is not a refusal — the flag only blocks when
    # explicitly false; every other boundary still applies.
    values["enabled"] = True
    door_mod.DoorConfig(values)


def test_admit_replay_conflict_wait_and_unfrozen_round_trip(scratch,
                                                            monkeypatch):
    """The whole admission lane over the real operator socket: freeze →
    ADMITTED → REPLAY (same job) → digest conflict → WAIT (queue full) →
    unfrozen command refused."""
    async def exercise():
        d = _make_door(scratch)
        # The admission LANE is under test here with a deliberately dead dev
        # Paperclip; the F10 task-shows-request gate (which needs a live
        # task) has its own tests in test_mmos_coding_job_door_t4c.py.
        monkeypatch.setattr(d, "_task_request_error",
                            lambda _cmd, _entry: None)
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
    # a WAIT is retried by the door itself once the retry interval elapses
    # (R4b finding 12 — same command, so still one admission); an
    # unageable timestamp reads as due.  A REFUSAL stays answered: the
    # carrier owns that retry.
    assert d._entry_action(
        {"admit_requested_at": "t", "admit_outcome": "WAIT"}) == "admit"
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
    # F12 (R4b review): the WAIT is stale (asked 2026-11-10) — the door
    # itself now re-asks the same command when the interval elapses
    assert d._entry_action(entry2) == "admit"
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
    # never re-executed — but (R4b finding 13) the entry KEEPS ITS WAKE
    # until the attempt row is reconciled terminal, because its thread
    # slot is held; the blocker branch closes it then and only then
    assert d._entry_action(entry) == "blocker"


def test_f2_durable_identity_routes_to_the_engine_owned_watch_never_adopts(
        scratch, monkeypatch, tmp_path):
    """Crash AFTER the engine recorded the attempt's durable identity
    (provider session id + recovery binding in one transaction), BEFORE the
    finisher sealed: the fresh door must NEVER adopt, reattach, record or
    launch — it routes the entry to the engine-owned watch and waits for
    the terminal row (F15: one recovery owner, the engine).

    The old law (T4b): the DOOR reattached and adopted under its own
    ``t4b-door-recovery`` lease owner, which is exactly the misreporting
    F2 originally chased — a StateConflict against the door's own partial
    record read as EXECUTOR_FAILED for a job that had succeeded.  Step 3
    removed the door's adoption path entirely; identity now lands in one
    engine transaction, so this test pins the routing, not a door-side
    reattach."""
    from types import SimpleNamespace
    from tests.test_executive_supervisor import _runtime_and_job
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    attempt_id = lease.attempt.attempt_id
    # the durable identity exactly as the ENGINE's adoption leaves it
    # (identity lands in the engine's one adoption transaction — the
    # binding is the alternate signal the watch also accepts)
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

    # the durable adapter receipt the engine adopted under (present, so the
    # door's own receipt read cannot fall into the F1/F13 launch windows)
    real_spec = d._launch_spec(
        run_id=attempt_id, job_id="JOB-F2",
        prompt=d._worker_prompt(attempt_id,
                                "t3/mmos-t4b-job-deadbeef"),
        workspace=d.root / "run" / "jobs" / "job-f2-ws")
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

    def forbidden(*_a, **_k):
        raise AssertionError("the door must not adopt, reconcile, launch "
                             "or record an engine-owned attempt itself")

    monkeypatch.setattr(d, "_compose_adapter", forbidden)
    monkeypatch.setattr(d, "_reconcile", forbidden)
    monkeypatch.setattr(d, "_seal_and_deliver", forbidden)
    monkeypatch.setattr(runtime.attempts, "record_process", forbidden)
    monkeypatch.setattr(runtime.attempts, "adopt_attempt", forbidden)

    d._execute(runtime, command, entry)

    row = runtime.attempts.get_attempt(attempt_id)
    assert row.provider_session_id == "mcp:launch:already-durable"
    # the DEAD claimant still owns the lease — the door fenced nothing
    assert row.lease_owner == "t4b-door-dead"
    assert entry["phase"] == "engine-owned"
    # re-executing stays in the watch (no second reconcile drive: a live
    # finisher's lease must never be fenced by a re-ask)
    d._execute(runtime, command, entry)
    assert entry["phase"] == "engine-owned"
    assert runtime.attempts.get_attempt(attempt_id).lease_owner == (
        "t4b-door-dead")
