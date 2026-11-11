#!/usr/bin/env python3
"""Move ONE installed Paperclip agent onto its Team conversation (plan V4).

After this runs, Paperclip wakes the agent by starting the wake carrier, and
the carrier does the work in the agent's own thread on the team T3 server.
The agent's earlier run command is saved first and `rollback` puts it back.

    cutover_installed.py check    <spec.json>   read only: is it safe to move?
    cutover_installed.py apply    <spec.json>   save the old setup, then move
    cutover_installed.py rollback <spec.json>   put the saved setup back
    cutover_installed.py refresh-carrier <spec.json>
                                  install this checkout's carrier file for an
                                  agent that is already moved (the file is
                                  shared, so this updates every moved agent)

One agent per spec, on purpose: agents are moved one at a time. Nothing here
creates an agent, a company, an issue or a wake. The principal runs this; a
lane does not (plan V4 section 6).
"""
import hashlib
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from setup_teammate import Http, die, expand, log, write_binding  # noqa: E402

OPEN_STATES = ("todo", "in_progress", "in_review", "blocked")
PREIMAGE_KEYS = ("adapterType", "adapterConfig", "runtimeConfig", "metadata")


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write_private(path, text):
    """Create `path` with mode 0600; refuses to replace an existing file."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)


def rows_of(payload):
    if isinstance(payload, list):
        return payload
    for key in ("items", "issues", "rows", "runs"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def blockers(spec, agent, open_issues, live_runs):
    """Reasons this agent must not be moved right now. Empty list = safe."""
    out = []
    if agent.get("name") != spec["agent_name"]:
        out.append(f"agent name is {agent.get('name')!r}, spec says "
                   f"{spec['agent_name']!r}")
    if agent.get("companyId") != spec["company_id"]:
        out.append("agent belongs to a different company")
    if agent.get("status") != "idle":
        out.append(f"agent status is {agent.get('status')!r}, not idle")
    heartbeat = (agent.get("runtimeConfig") or {}).get("heartbeat") or {}
    if heartbeat.get("enabled"):
        out.append("the agent's timer heartbeat is still on (fence it first)")
    if open_issues:
        out.append(f"{len(open_issues)} open issue(s) assigned: "
                   + ", ".join(str(i.get("identifier")) for i in open_issues[:5]))
    mine = [r for r in live_runs if r.get("agentId") == agent.get("id")]
    if mine:
        out.append(f"{len(mine)} live run(s) for this agent")
    return out


def carrier_config(spec):
    t3 = spec["t3"]
    cfg = {
        "t3_bin": expand(t3["t3_bin"]),
        "t3_home": expand(t3["home"]),
        "t3_port": int(t3["port"]),
        "t3_cwd": expand(t3["cwd"]),
        "pending_timeout_sec": int(spec.get("pending_timeout_sec", 600)),
        "poll_interval_sec": int(spec.get("poll_interval_sec", 5)),
        # The question wait: one carrier run stays with a waiting question
        # for question_wait_sec, never past run_budget_sec from process start
        # (the process adapter allows 1500s), polling every
        # question_poll_interval_sec.
        "question_wait_sec": int(spec.get("question_wait_sec", 900)),
        "run_budget_sec": int(spec.get("run_budget_sec", 1320)),
        "question_poll_interval_sec": int(
            spec.get("question_poll_interval_sec", 10)),
        "teammates": dict(spec.get("teammates") or {}),
    }
    # Optional (R2a finding 4): the carrier defaults to 3 when absent.
    if spec.get("max_asks_per_issue") is not None:
        cfg["max_asks_per_issue"] = int(spec["max_asks_per_issue"])
    if spec.get("issue_url_template"):
        cfg["issue_url_template"] = spec["issue_url_template"]
    if spec.get("thread_url_template"):
        cfg["thread_url_template"] = spec["thread_url_template"]
    return cfg


def adapter_patch(spec, carrier_path, config_path):
    """The agent update. `env: {}` and `replaceAdapterConfig` are deliberate:
    this Paperclip build carries env and cwd over when the run command type
    changes, and the old runtime's environment must not ride into the carrier."""
    return {
        "adapterType": "process",
        "replaceAdapterConfig": True,
        "adapterConfig": {
            "command": spec["python_bin"],
            "args": ["-I", carrier_path, config_path],
            "cwd": expand(spec["agent_dir"]),
            "env": {},
            "timeoutSec": int(spec.get("adapter_timeout_sec", 1500)),
        },
        "runtimeConfig": {"heartbeat": {"enabled": False}},
    }


def read_state(http, spec):
    agent = http.get(f"/api/agents/{spec['agent_id']}")
    cid = spec["company_id"]
    open_issues = []
    for state in OPEN_STATES:
        open_issues += rows_of(http.get(
            f"/api/companies/{cid}/issues?assigneeAgentId={spec['agent_id']}"
            f"&status={state}&limit=50"))
    live = rows_of(http.get(f"/api/companies/{cid}/live-runs"))
    return agent, open_issues, live


def carrier_paths(spec):
    carrier = os.path.join(expand(spec["carrier_install_dir"]), "wake_carrier.py")
    config = os.path.join(expand(spec["agent_dir"]), "carrier.json")
    return carrier, config


def is_ours(agent, carrier_path):
    """True only when the agent already runs THIS tool's carrier. `process`
    is a generic run type: any other process command still gets saved."""
    if agent.get("adapterType") != "process":
        return False
    args = (agent.get("adapterConfig") or {}).get("args") or []
    return len(args) >= 2 and args[1] == carrier_path


def same(a, b):
    return (a or None) == (b or None)


def cmd_check(spec):
    http = Http(spec["paperclip_base"])
    agent, open_issues, live = read_state(http, spec)
    found = blockers(spec, agent, open_issues, live)
    print(json.dumps({
        "agent": agent.get("name"), "adapterType": agent.get("adapterType"),
        "status": agent.get("status"), "openIssues": len(open_issues),
        "liveRuns": len(live), "blockers": found,
        "alreadyMoved": is_ours(agent, carrier_paths(spec)[0])}, indent=2))
    return 1 if found else 0


def cmd_apply(spec):
    http = Http(spec["paperclip_base"])
    agent, open_issues, live = read_state(http, spec)
    found = blockers(spec, agent, open_issues, live)
    if found:
        die("not moving: " + "; ".join(found))
    agent_dir = expand(spec["agent_dir"])
    os.makedirs(agent_dir, mode=0o700, exist_ok=True)
    carrier_path, config_path = carrier_paths(spec)
    preimage = os.path.join(agent_dir, "cutover-preimage.json")
    if not is_ours(agent, carrier_path):
        if os.path.exists(preimage):
            die(f"{preimage} already exists but the agent is not moved; "
                "inspect it before trying again")
        # Holds the old run command and its environment: private, never printed.
        write_private(preimage, json.dumps(
            {k: agent.get(k) for k in PREIMAGE_KEYS}, indent=2))
        log(f"old setup saved to {preimage} (0600)")

    os.makedirs(os.path.dirname(carrier_path), mode=0o700, exist_ok=True)
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "wake_carrier.py")
    if not os.path.exists(carrier_path) or \
            sha256_file(carrier_path) != sha256_file(source):
        shutil.copyfile(source, carrier_path)
    with open(config_path, "w") as fh:
        json.dump(carrier_config(spec), fh, indent=2)

    # Look again right before the change: a wake may have started meanwhile.
    # (The server has no conditional update, so this narrows the gap only.)
    found = blockers(spec, *read_state(http, spec))
    if found:
        die("not moving, state changed while preparing: " + "; ".join(found))
    try:
        http.patch(f"/api/agents/{spec['agent_id']}",
                   adapter_patch(spec, carrier_path, config_path))
        after = http.get(f"/api/agents/{spec['agent_id']}")
        cfg = after.get("adapterConfig") or {}
        if after.get("adapterType") != "process" or cfg.get("env") or \
                cfg.get("args") != ["-I", carrier_path, config_path]:
            die("agent read-back does not match the requested run command; "
                "run rollback")
        binding = write_binding(http, spec["agent_id"], dict(spec["binding"]))
    except BaseException:
        log("the move may be half done (run command changed, conversation "
            "not linked): run `apply` again to finish it - that is safe. If "
            "apply stops at the saved-setup check, the change never took: "
            "run `rollback`. Until then every wake of this agent may fail.")
        raise
    result = {
        "agentId": spec["agent_id"], "agent": after.get("name"),
        "movedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "carrierPath": carrier_path,
        "carrierSha256": sha256_file(carrier_path),
        "configPath": config_path, "binding": binding,
        "adapterConfigKeys": sorted(cfg.keys()),
    }
    with open(os.path.join(agent_dir, "cutover-result.json"), "w") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
    return 0


def live_for(http, spec):
    return [r for r in read_state(http, spec)[2]
            if r.get("agentId") == spec["agent_id"]]


def cmd_rollback(spec):
    http = Http(spec["paperclip_base"])
    preimage = os.path.join(expand(spec["agent_dir"]), "cutover-preimage.json")
    if not os.path.exists(preimage):
        die(f"no saved setup at {preimage}")
    with open(preimage) as fh:
        saved = json.load(fh)
    if live_for(http, spec):
        die("a run is live for this agent; wait for it to end")
    http.patch(f"/api/agents/{spec['agent_id']}", {
        "adapterType": saved["adapterType"],
        "replaceAdapterConfig": True,
        "adapterConfig": saved["adapterConfig"] or {},
        "runtimeConfig": saved["runtimeConfig"] or {},
        "metadata": saved["metadata"],
    })
    after = http.get(f"/api/agents/{spec['agent_id']}")
    got, want = after.get("adapterConfig") or {}, saved["adapterConfig"] or {}
    wrong = [k for k in ("command", "args", "env", "cwd")
             if not same(got.get(k), want.get(k))]
    if after.get("adapterType") != saved["adapterType"]:
        wrong.insert(0, "adapterType")
    if wrong:
        # Names only: the values include the old environment.
        die("rollback read-back differs from the saved setup in: "
            + ", ".join(wrong) + f"; the saved setup is still at {preimage}")
    os.replace(preimage, preimage + ".restored-"
               + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    log(f"{after.get('name')} is back on {after.get('adapterType')}")
    return 0


def cmd_refresh_carrier(spec):
    """Replace the installed carrier file with this checkout's copy.

    `apply` refuses while the agent has open work, which is right for a move
    and wrong for a carrier fix: a task waiting on the board would block the
    fix forever. The file is read once when a run starts, and it is swapped in
    one rename, so a run sees the old file or the new one, never half of each.
    It still refuses while any run of the company is live, so no task is
    started by one version and finished by another."""
    http = Http(spec["paperclip_base"])
    agent, _, live = read_state(http, spec)
    carrier_path, config_path = carrier_paths(spec)
    if not is_ours(agent, carrier_path):
        die(f"{agent.get('name')} does not run the carrier at {carrier_path}; "
            "use `apply` to move it")
    if live:
        die(f"{len(live)} run(s) are live in this company; wait for them to end")
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "wake_carrier.py")
    before = sha256_file(carrier_path) if os.path.exists(carrier_path) else None
    after = sha256_file(source)
    if before != after:
        staged = f"{carrier_path}.new-{os.getpid()}"
        shutil.copyfile(source, staged)
        os.replace(staged, carrier_path)
    # This teammate's own settings file follows its spec too: a carrier fix
    # that adds a setting is otherwise installed without it (seen 2026-11-11:
    # the new carrier ran on defaults and without its conversation link).
    # Same one-rename swap. Key names only are printed.
    want = carrier_config(spec)
    try:
        with open(config_path) as fh:
            have = json.load(fh)
    except (OSError, ValueError):
        have = None
    config_keys = sorted(k for k in set(want) | set(have or {})
                         if (have or {}).get(k) != want.get(k))
    if have != want:
        staged = f"{config_path}.new-{os.getpid()}"
        with open(staged, "w") as fh:
            json.dump(want, fh, indent=2)
        os.replace(staged, config_path)
    print(json.dumps({
        "carrierPath": carrier_path, "sha256Before": before,
        "sha256After": sha256_file(carrier_path), "changed": before != after,
        "configPath": config_path, "configChanged": have != want,
        "configKeysChanged": config_keys,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2))
    return 0


COMMANDS = {"check": cmd_check, "apply": cmd_apply, "rollback": cmd_rollback,
            "refresh-carrier": cmd_refresh_carrier}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in COMMANDS:
        die("usage: cutover_installed.py check|apply|rollback|refresh-carrier "
            "<spec.json>")
    spec = json.load(open(sys.argv[2]))
    return COMMANDS[sys.argv[1]](spec)


if __name__ == "__main__":
    sys.exit(main())
