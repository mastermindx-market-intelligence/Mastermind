#!/usr/bin/env python3
"""T4b journey — the whole governed coding job, on dev instances, no window.

One command per scenario over the REAL pieces: dev Paperclip (3190), dev T3
server (3790-3810), the scratch Executive door as its own process, the REAL
wake-carrier coding-job act (headless — the teammate's reply text is the only
trigger), ONE native launch through the t3-native adapter, the
execution-return seam with the ``paperclip_task`` transport, and the result
landing on the SAME task it came from.

Scenarios:
  default       task -> one coding job -> sealed -> result comment on the task
  crash         door dies between launch receipt and process record (exit 90);
                a FRESH door recovers the SAME attempt, census stays at ONE
                native launch, the result still lands (L1B3-5)
  wait          fleet queue full: the second task's carrier call gets WAIT and
                posts the blocker comment with the precise reason (the door's
                T3 target is a dead dev-range port in this scenario, so the
                first job provably stays queued and the WAIT is deterministic)
  undeliverable the transport is withheld; the refused receipt is surfaced as
                a blocker comment with its code

Run (from the repo root):
  python3 tools/mmos_coding_job/journey.py --scenario default

Prerequisites (the run book names them): dev Paperclip up
(`tools/mmos_dev/paperclip_dev.sh up`), dev T3 server up
(`tools/mmos_dev/t3_dev.sh start`).  The journey never starts or stops either
itself, never dials 3100/3780/3773/3774, and stops the door it started.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DOOR = REPO_ROOT / "tools" / "mmos_coding_job" / "door.py"
CARRIER = REPO_ROOT / "tools" / "mmos_teammate" / "wake_carrier.py"
_spec = importlib.util.spec_from_file_location("wake_carrier", CARRIER)
wc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wc)

DEV_PAPERCLIP = "http://127.0.0.1:3190"
DEV_T3_PORT = 3790
DEAD_DEV_T3_PORT = 3799  # inside the dev range, never started: for `wait`
DEV_T3_HOME = "~/.mastermind/mmos-dev/t3/home"
PAPERCLIP_STATE = Path(
    "~/.mastermind/mmos-dev/paperclip/instances/mmos-dev/"
    "dev-state.json").expanduser()
T3_PROJECT_ID = "mcp:370a922f-6b11-4fa6-8f37-2d25a2ab37a8"
MODEL_SELECTION = '{"instanceId":"capacity_fabric","model":"glm-5.3-flash"}'
PY = sys.executable or "/opt/homebrew/bin/python3.12"

FAIL = 3
COMPANY: dict[str, str] = {}
# The enrolled teammate every journey task is assigned to (finding 10: the
# door freezes only enrolled assignees and admits only on the task's own
# agent request).
JOURNEY_TEAMMATE = "ag-journey-worker"


def log(msg: str) -> None:
    print(f"[journey] {msg}", flush=True)


def http_json(method: str, url: str, body=None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


class DevPaperclipClient(wc.PaperclipClient):
    """The real carrier client on the dev instance's local-trusted surface.

    Only the transport auth differs: the dev instance admits its implicit
    board actor via the ``x-instance-role`` header, and rejects any bearer it
    cannot verify — so no authorization header is sent at all.  There is no
    per-run token in this journey (that token exists only inside a real
    carrier run and never enters this file).
    """

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"x-instance-role": "local_trusted"}
        if data is not None:
            headers["content-type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base}{path}", data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}


def preflight() -> str:
    """Both dev instances answer; returns the dev company id."""
    try:
        health = http_json("GET", DEV_PAPERCLIP + "/api/health")
    except Exception as exc:
        log(f"FAIL dev Paperclip not answering on {DEV_PAPERCLIP}: "
            f"{type(exc).__name__}: {exc}")
        log("start it: tools/mmos_dev/paperclip_dev.sh up")
        raise SystemExit(FAIL)
    if not (health.get("status") == "ok" or health.get("ok")):
        log(f"FAIL dev Paperclip health: {str(health)[:200]}")
        raise SystemExit(FAIL)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{DEV_T3_PORT}/",
                               timeout=10).read()
    except Exception as exc:
        log(f"FAIL dev T3 server not answering on 127.0.0.1:{DEV_T3_PORT}: "
            f"{type(exc).__name__}: {exc}")
        log("start it: tools/mmos_dev/t3_dev.sh start")
        raise SystemExit(FAIL)
    state = json.loads(PAPERCLIP_STATE.read_text())
    company = state.get("companyId")
    if not company:
        log("FAIL no seeded dev company in paperclip state; rerun "
            "tools/mmos_dev/paperclip_dev.sh up")
        raise SystemExit(FAIL)
    log(f"preflight ok: paperclip {DEV_PAPERCLIP} company {company[:8]}…, "
        f"t3 127.0.0.1:{DEV_T3_PORT}")
    return company


def make_task(title: str, description: str) -> dict:
    # unique title per run: the dev instance dedupes an identical create
    # body into the earlier task, and its already-surfaced marker would
    # make the carrier honestly skip the admit
    stamp = time.strftime("%H%M%S")
    row = http_json("POST",
                    f"{DEV_PAPERCLIP}/api/companies/{COMPANY['id']}/issues",
                    {"title": f"{title} [{stamp}]",
                     "description": description})
    log(f"task created: {row.get('identifier')} ({row.get('id')})")
    return row


def door_config(scratch: Path, *, crash_mode=None, fleet_limit=None,
                register_transport=True, t3_port=DEV_T3_PORT,
                teammates=None) -> Path:
    config = {
        "scratch_root": str(scratch),
        "paperclip_base_url": DEV_PAPERCLIP,
        # R4b finding 9: the explicit host:port allowlist
        "paperclip_allowed": ["127.0.0.1:3190"],
        "paperclip_company_id": COMPANY["id"],
        # the dev instance's implicit board actor (its local-trusted surface);
        # the door's result/blocker comments ride the same header
        "paperclip_headers": {"x-instance-role": "local_trusted"},
        # R4b finding 10: the enrolled-teammate roster; the journey's tasks
        # are assigned to JOURNEY_TEAMMATE before the reply is posted
        "teammates": teammates or [JOURNEY_TEAMMATE],
        "t3": {
            "proof_base_url": f"http://127.0.0.1:{t3_port}",
            "home_dir": os.path.expanduser(DEV_T3_HOME),
            "port": t3_port,
            "token_path": str(scratch / "worker-token.txt"),
            "token_label": "t4b-door-worker",
            "project_id": T3_PROJECT_ID,
            "model_selection": MODEL_SELECTION,
        },
        "intake_poll_seconds": 1.0,
        # R4b finding 12: the door retries a WAIT itself after this interval
        "wait_retry_seconds": 10.0,
    }
    if crash_mode:
        config["crash_mode"] = crash_mode
    if fleet_limit is not None:
        config["child_fleet_ready_limit"] = fleet_limit
    if not register_transport:
        config["register_transport"] = False
    path = scratch / "door.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def start_door(config: Path, scratch: Path) -> subprocess.Popen:
    log_file = open(scratch / "door.log", "ab")
    proc = subprocess.Popen(
        [PY, str(DOOR), "--config", str(config), "serve"],
        stdout=log_file, stderr=subprocess.STDOUT, cwd=str(REPO_ROOT))
    operator = scratch / "run" / "local-operator.sock"
    probe = wc.DoorClient(operator)

    def answering() -> bool:
        # a REAL round-trip, not file existence: after a crash the stale
        # socket file lingers and exists() lies about the fresh listener
        try:
            probe._request("GET", "/paperclip/coding-job/state/probe")
            return True
        except Exception:
            return False

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log(f"FAIL door exited early rc={proc.returncode}; "
                f"see {scratch / 'door.log'}")
            raise SystemExit(FAIL)
        if answering():
            log(f"door up (pid {proc.pid}), operator socket answering")
            return proc
        time.sleep(0.5)
    log("FAIL door operator socket never answered")
    proc.terminate()
    raise SystemExit(FAIL)


def stop_door(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    log(f"door stopped (rc={proc.returncode})")


def door_state(scratch: Path, command: str):
    client = wc.DoorClient(scratch / "run" / "local-operator.sock")
    status, body = client._request(
        "GET", f"/paperclip/coding-job/state/{command}")
    return body if status == 200 else {"error": body, "_status": status}


def frozen_state(scratch: Path, command: str) -> dict:
    """The durable record — the only state source once the door is DEAD
    (its socket is gone with the process); exactly what a fresh door loads."""
    path = scratch / "run" / "frozen.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    return data.get(command) or {}


def carrier_admit(issue: dict, scratch: Path, reply_text: str) -> None:
    """The headless teammate: a reply ending in the block, the REAL carrier
    function, exactly one door call.  Dev Paperclip is local-trusted; the
    token field is a placeholder, never a real credential."""
    pc = DevPaperclipClient(DEV_PAPERCLIP, "dev-local-trusted",
                            f"t4b-journey-{int(time.time())}")
    block = wc.parse_coding_job_block(reply_text)
    if block is None:
        log("FAIL the journey reply failed to parse as a coding-job block")
        raise SystemExit(FAIL)
    wc.handle_coding_job(pc, issue, reply_text, block,
                         {"coding_job_door": str(
                             scratch / "run" / "local-operator.sock")})


def wait_frozen(scratch: Path, issue: dict) -> str:
    command = wc.coding_job_command(str(issue["id"]))
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        state = door_state(scratch, command)
        if (state.get("issue") or {}).get("id") == str(issue["id"]):
            log(f"frozen at intake: {issue.get('identifier')} -> "
                f"{command[:30]}…")
            return command
        time.sleep(1.0)
    log("FAIL the door never froze the new task at intake")
    raise SystemExit(FAIL)


def wait_phase(scratch: Path, command: str, phases, timeout: float):
    deadline = time.monotonic() + timeout
    state = {}
    while time.monotonic() < deadline:
        state = door_state(scratch, command)
        if state.get("phase") in phases:
            return state
        time.sleep(5.0)
    return state


def comments_of(issue_id: str):
    rows = http_json("GET", f"{DEV_PAPERCLIP}/api/issues/{issue_id}/comments")
    return rows if isinstance(rows, list) else rows.get("comments") or []


def result_comment(rows):
    return next((c for c in rows
                 if "paperclip-return-attempt:" in str(c.get("body"))), None)


def blocker_comment(rows):
    return next((c for c in rows
                 if "blocked" in str(c.get("body", ""))), None)


def report(scenario: str, issue: dict, state: dict, extra: str = "") -> None:
    print("\n===== T4b journey result =====")
    print(f"scenario        : {scenario}")
    print(f"task            : {issue.get('identifier')} ({issue.get('id')})")
    print(f"job id          : {state.get('job_id')}")
    print(f"attempt id      : {state.get('attempt_id')}")
    print(f"native launches : {state.get('native_launches')} "
          "(must be 1 for default/crash)")
    print(f"phase           : {state.get('phase')}")
    print(f"delivery        : {state.get('delivery')}")
    if extra:
        print(extra)


def scenario_default(scratch: Path) -> int:
    issue = make_task("T4b journey: add the canary flag file",
                      "Create the job's flag file on its own branch, exactly "
                      "as the worker prompt directs; this task needs code.")
    config = door_config(scratch)
    proc = start_door(config, scratch)
    try:
        command = wait_frozen(scratch, issue)
        carrier_admit(issue, scratch,
                      "answer text\n```paperclip-coding-job\n```")
        state = wait_phase(scratch, command, ("delivered", "delivery-refused",
                                              "surfaced"), 900.0)
        rows = comments_of(issue["id"])
        result = result_comment(rows)
        where = (f"result landed   : comment {result.get('id')} on "
                 f"{issue.get('identifier')} — "
                 + str(result.get("body", ""))[:100].replace("\n", " ")
                 ) if result else "result landed   : NOWHERE"
        report("default", issue, state, where)
        ok = (state.get("phase") == "delivered"
              and state.get("native_launches") == 1 and result is not None)
        log("PASS" if ok else "FAIL")
        return 0 if ok else FAIL
    finally:
        stop_door(proc)


def scenario_crash(scratch: Path) -> int:
    issue = make_task("T4b journey (crash): add the canary flag file",
                      "The door will die between the launch receipt and the "
                      "process record; a fresh door must recover the SAME "
                      "attempt with no second launch.")
    config = door_config(scratch, crash_mode="after_receipt")
    proc = start_door(config, scratch)
    try:
        command = wait_frozen(scratch, issue)
        carrier_admit(issue, scratch,
                      "answer text\n```paperclip-coding-job\n```")
        deadline = time.monotonic() + 300.0  # wait for the crash (exit 90)
        while time.monotonic() < deadline and proc.poll() is None:
            time.sleep(2.0)
        rc = proc.poll()
        state = frozen_state(scratch, command)  # the door is DEAD: durable record
        log(f"door exited rc={rc} at phase={state.get('phase')} "
            f"attempt={state.get('attempt_id')}")
        crashed_ok = rc == 90 and state.get("attempt_id")
        at_crash = state.get("attempt_id")
    finally:
        if proc.poll() is None:
            stop_door(proc)
    if not crashed_ok:
        log(f"FAIL crash window not reached (rc={rc}, state={state})")
        return FAIL

    # fresh door, same scratch, NO crash mode: recovery as the ORIGINAL job
    config2 = door_config(scratch)
    proc = start_door(config2, scratch)
    try:
        state = wait_phase(scratch, command, ("delivered", "delivery-refused",
                                              "surfaced"), 900.0)
        rows = comments_of(issue["id"])
        result = result_comment(rows)
        where = (f"result landed   : comment {result.get('id')} on "
                 f"{issue.get('identifier')}") if result else \
                "result landed   : NOWHERE"
        report("crash", issue, state, where)
        ok = (state.get("phase") == "delivered"
              and state.get("attempt_id") == at_crash
              and state.get("native_launches") == 1 and result is not None)
        log("PASS" if ok else "FAIL")
        return 0 if ok else FAIL
    finally:
        stop_door(proc)


def scenario_wait(scratch: Path) -> int:
    one = make_task("T4b journey (wait): first task",
                    "Fills the one-slot fleet queue so the second task waits.")
    two = make_task("T4b journey (wait): second task",
                    "Must land as a precise WAIT blocker on this task.")
    # dead dev-range T3 port: the executor can never claim job 1, so the
    # fleet slot stays taken and the second admission deterministically WAITs
    config = door_config(scratch, fleet_limit=1, t3_port=DEAD_DEV_T3_PORT)
    proc = start_door(config, scratch)
    try:
        wait_frozen(scratch, one)
        command_two = wait_frozen(scratch, two)
        carrier_admit(one, scratch, "answer\n```paperclip-coding-job\n```")
        time.sleep(1.0)  # the admission commits the queued job
        carrier_admit(two, scratch, "answer\n```paperclip-coding-job\n```")
        time.sleep(2.0)
        rows = comments_of(two["id"])
        blocker = blocker_comment(rows)
        body = str(blocker.get("body", "")) if blocker else ""
        report("wait", two, door_state(scratch, command_two),
               f"blocker on task : {body[:220]!r}")
        ok = ("CHILD_QUEUE_FLEET_READY_FULL" in body
              and door_state(scratch, command_two).get("job_id") is None)
        log("PASS" if ok else "FAIL")
        return 0 if ok else FAIL
    finally:
        stop_door(proc)


def scenario_undeliverable(scratch: Path) -> int:
    issue = make_task("T4b journey (undeliverable): add the flag file",
                      "The transport is withheld; the refused receipt must "
                      "surface as a blocker with its code.")
    config = door_config(scratch, register_transport=False)
    proc = start_door(config, scratch)
    try:
        command = wait_frozen(scratch, issue)
        carrier_admit(issue, scratch,
                      "answer text\n```paperclip-coding-job\n```")
        state = wait_phase(scratch, command, ("delivered", "delivery-refused",
                                              "surfaced"), 900.0)
        rows = comments_of(issue["id"])
        blocker = blocker_comment(rows)
        body = str(blocker.get("body", "")) if blocker else ""
        report("undeliverable", issue, state,
               f"blocker on task : {body[:220]!r}")
        ok = (state.get("phase") == "delivery-refused"
              and "ORIGIN_KIND_UNKNOWN" in body)
        log("PASS" if ok else "FAIL")
        return 0 if ok else FAIL
    finally:
        stop_door(proc)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="default",
                        choices=("default", "crash", "wait", "undeliverable"))
    parser.add_argument("--scratch", default=None,
                        help="scratch root (default: a fresh timestamped one)")
    parser.add_argument("--keep", action="store_true",
                        help="keep the scratch root (printed at the end)")
    args = parser.parse_args(argv)

    COMPANY["id"] = preflight()

    if args.scratch:
        scratch = Path(args.scratch).expanduser()
    else:
        stamp = time.strftime("%Y%m%dT%H%M%S")
        scratch = Path(f"~/.cache/mmos-t4b-journey/"
                       f"{args.scenario}-{stamp}").expanduser()
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "run").mkdir(parents=True, exist_ok=True)
    log(f"scratch: {scratch}")

    rc = {
        "default": scenario_default,
        "crash": scenario_crash,
        "wait": scenario_wait,
        "undeliverable": scenario_undeliverable,
    }[args.scenario](scratch)
    if args.keep:
        log(f"scratch kept at {scratch}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
