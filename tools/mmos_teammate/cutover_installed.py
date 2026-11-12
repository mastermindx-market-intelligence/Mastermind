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
from setup_teammate import (Http, die, expand, log, write_binding,  # noqa: E402
                            blockers, open_assigned_issues, rows_of)

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


def read_live_config(config_path):
    """The live settings file as a dict, {} when absent (panel-2 M10). A
    file that exists but cannot be parsed is REFUSED, not guessed over:
    merging into garbage would silently drop live keys or overwrite them
    without a person seeing. Key names only are ever printed."""
    try:
        with open(config_path) as fh:
            have = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        die(f"{config_path} exists but is not readable JSON; inspect it "
            "before moving or refreshing this agent")
    if not isinstance(have, dict):
        die(f"{config_path} is not a JSON object; inspect it before moving "
            "or refreshing this agent")
    return have


def merged_carrier_config(have, want):
    """The settings the next wake will read. The spec is authority for its
    OWN keys; live keys the spec does not hold are KEPT (panel-2 M10) — a
    wholesale rewrite silently deleted a person's coding_job_door once the
    spec behind it predates the key. No silent drop, ever."""
    out = dict(have or {})
    out.update(want)
    return out


def write_config_file(config_path, data):
    """The live settings write (panel-2 M9): staged, 0600 from creation,
    renamed over in one move — a halfway death never truncates the live
    bytes and never leaves the file world-readable. Same law as the
    preimage and settings writes."""
    staged = f"{config_path}.new-{os.getpid()}"
    try:
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)
        os.replace(staged, config_path)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)


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
    # Optional (R2a finding 8 addition): the stated delivery reserve; the
    # carrier defaults to 120s when absent.
    if spec.get("delivery_reserve_sec") is not None:
        cfg["delivery_reserve_sec"] = int(spec["delivery_reserve_sec"])
    # Optional (R2a finding 13): the pinned loopback base; the carrier
    # refuses a PAPERCLIP_API_URL that differs from it.
    if spec.get("paperclip_base"):
        cfg["paperclip_base"] = spec["paperclip_base"]
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
    # walks pages: an agent with more open work than one 50-row page is
    # still fully seen (setup_teammate.open_assigned_issues)
    open_issues = open_assigned_issues(http, spec["company_id"],
                                       spec["agent_id"], states=OPEN_STATES)
    live = rows_of(http.get(f"/api/companies/{spec['company_id']}/live-runs"))
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


def binding_core(binding):
    """A binding without its own bookkeeping keys (bindingRevision,
    rotatedAt — write_binding maintains those), so a spec and the agent's
    live binding compare by content."""
    if not isinstance(binding, dict):
        return binding
    return {k: v for k, v in binding.items()
            if k not in ("bindingRevision", "rotatedAt")}


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
            # R2a finding 31: a first apply can stop at the second blockers
            # check AFTER the preimage was saved (a wake started meanwhile) —
            # the move never happened, and the retry used to die on its own
            # saved file. When the agent still carries EXACTLY the saved
            # values for every preimage key, the file describes the agent as
            # it stands: reuse it and finish the move. When any value
            # differs, the file is stale and refusal stands. Values are
            # compared in memory and never printed; nothing is deleted.
            with open(preimage) as fh:
                saved = json.load(fh)
            current = {k: agent.get(k) for k in PREIMAGE_KEYS}
            if any(saved.get(k) != current.get(k) for k in PREIMAGE_KEYS):
                die(f"{preimage} exists and the agent has changed since it "
                    "was saved; inspect it before trying again")
            log(f"{preimage} already matches this agent's saved setup "
                f"exactly; reusing it")
        else:
            # Holds the old run command and its environment: private, never
            # printed.
            write_private(preimage, json.dumps(
                {k: agent.get(k) for k in PREIMAGE_KEYS}, indent=2))
            log(f"old setup saved to {preimage} (0600)")

    os.makedirs(os.path.dirname(carrier_path), mode=0o700, exist_ok=True)
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "wake_carrier.py")
    # R2a finding 9: the carrier file is shared by every moved agent. A NEW
    # move may install it only when it is absent or already identical; a
    # differing file belongs to `refresh-carrier` (which waits out live runs
    # and swaps in one rename) — never an in-place overwrite here.
    if os.path.exists(carrier_path):
        if sha256_file(carrier_path) != sha256_file(source):
            die(f"the shared carrier at {carrier_path} differs from this "
                "checkout's copy; refusing to overwrite it. Run "
                "`refresh-carrier` to update it for every moved agent.")
    else:
        staged = f"{carrier_path}.new-{os.getpid()}"
        shutil.copyfile(source, staged)
        os.replace(staged, carrier_path)

    # R13: an apply on an agent this tool ALREADY moved must not silently
    # rewrite the live conversation binding from a spec that may predate a
    # rotate. The spec is authority only for a first move; afterwards the
    # agent's current binding is the truth — equal means rewrite nothing,
    # different means a rotate (or another writer) happened and a person
    # decides.
    if is_ours(agent, carrier_path):
        current = ((agent.get("metadata") or {}).get("teammate")
                   or {}).get("t3")
        if current is None:
            pass  # a half-done move (adapter changed, link not written):
            # the link step below finishes it — the documented recovery.
        elif binding_core(current) != binding_core(spec["binding"]):
            die("the agent is already moved and its conversation binding "
                "has changed since this spec (rotated?); refresh the spec "
                "or use rotate — refusing to overwrite it")

    # Look again right before the change: a wake may have started meanwhile.
    # (The server has no conditional update, so this narrows the gap only.)
    found = blockers(spec, *read_state(http, spec))
    if found:
        die("not moving, state changed while preparing: " + "; ".join(found))
    # R13: the live config is written only AFTER the final gate — an apply
    # that dies here must leave what the next wake reads untouched. The
    # write itself is staged and renamed, 0600 from creation (panel-2 M9),
    # and it MERGES over the live file (panel-2 M10): keys the spec does
    # not hold survive an apply, named in the log.
    have_cfg = read_live_config(config_path)
    want_cfg = carrier_config(spec)
    kept_cfg = sorted(k for k in have_cfg if k not in want_cfg)
    if kept_cfg:
        log("keeping live settings this spec does not hold: "
            + ", ".join(kept_cfg))
    write_config_file(config_path, merged_carrier_config(have_cfg, want_cfg))
    try:
        patch = adapter_patch(spec, carrier_path, config_path)
        http.patch(f"/api/agents/{spec['agent_id']}", patch)
        after = http.get(f"/api/agents/{spec['agent_id']}")
        cfg = after.get("adapterConfig") or {}
        if after.get("adapterType") != "process" or cfg.get("env") or \
                cfg.get("args") != ["-I", carrier_path, config_path] or \
                not same(cfg.get("cwd"), expand(spec["agent_dir"])):
            die("agent read-back does not match the requested run command; "
                "run rollback")
        if is_ours(agent, carrier_path) and \
                ((agent.get("metadata") or {}).get("teammate")
                 or {}).get("t3") is not None:
            binding = ((agent.get("metadata") or {}).get("teammate")
                       or {}).get("t3")  # unchanged: no rewrite, no churn
        else:
            binding = write_binding(http, spec["agent_id"],
                                    dict(spec["binding"]))
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
        "adapterPatch": patch,   # R14: rollback checks the live agent
        "adapterConfigKeys": sorted(cfg.keys()),
    }
    # Panel-2 M12: staged 0600 write — the record was a plain in-place 0644
    # truncate; a crash mid-write left truncated bytes that silently
    # disabled rollback's drift guard.
    write_config_file(os.path.join(agent_dir, "cutover-result.json"), result)
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
    # R2a finding 10: the SAME blockers as apply. Rolling back while an open
    # issue is assigned — a turn waiting on a question, an ask child — hands
    # that work to the old runtime; live runs are covered here too.
    agent, open_issues, live = read_state(http, spec)
    found = blockers(spec, agent, open_issues, live)
    if found:
        die("not rolling back: " + "; ".join(found))
    # R14: the move recorded the exact patch it wrote; when the live agent
    # no longer matches it (a third party changed the run command or the
    # runtime config after the move), restoring the saved setup would
    # silently overwrite that change. Refuse and let a person look. Moves
    # from before the record carry no adapterPatch and roll back as before.
    # Panel-2 M12: a result file that exists but cannot be parsed is a
    # REFUSAL, not "no record" — a corrupt file silently disabled this
    # guard and let rollback clobber a third-party change as "success".
    result_path = os.path.join(expand(spec["agent_dir"]),
                               "cutover-result.json")
    result_doc = None
    if os.path.exists(result_path):
        try:
            with open(result_path) as fh:
                result_doc = json.load(fh)
        except ValueError:
            die(f"{result_path} exists but is not readable JSON; the drift "
                "guard cannot run — inspect the file before rolling back")
        if not isinstance(result_doc, dict):
            die(f"{result_path} is not a JSON object; the drift guard cannot "
                "run — inspect the file before rolling back")
    recorded = (result_doc or {}).get("adapterPatch")
    if isinstance(recorded, dict):
        drift = []
        if agent.get("adapterType") != recorded.get("adapterType"):
            drift.append("adapterType")
        got_cfg = agent.get("adapterConfig") or {}
        want_cfg = recorded.get("adapterConfig") or {}
        drift += [f"adapterConfig.{k}" for k in
                  ("command", "args", "cwd", "env", "timeoutSec")
                  if not same(got_cfg.get(k), want_cfg.get(k))]
        if not same(agent.get("runtimeConfig"), recorded.get("runtimeConfig")):
            drift.append("runtimeConfig")
        # Panel-2 M11: the teammate binding is part of what the move
        # recorded. A rotate that ran after the move (fresh thread,
        # revision bump) must not vanish under the wholesale teammate pop
        # below — a changed binding core refuses rollback.
        live_binding = ((agent.get("metadata") or {}).get("teammate")
                        or {}).get("t3")
        moved_binding = (result_doc or {}).get("binding")
        if live_binding is not None and isinstance(moved_binding, dict) \
                and binding_core(live_binding) != binding_core(moved_binding):
            drift.append("metadata.teammate.t3 (rotated after the move?)")
        if drift:
            die("the agent changed after the move (" + ", ".join(drift) +
                "); not rolling back over it — inspect the agent and the "
                f"saved setup at {preimage} first")
    # R2a finding 10: restore the run command, never the whole metadata
    # object — binding changes written after the move (a rotate's revision
    # bump, another subsystem's key) would be lost. Only the teammate key
    # this move added is removed; the rest of the CURRENT metadata stands.
    merged = dict(agent.get("metadata") or {})
    merged.pop("teammate", None)
    http.patch(f"/api/agents/{spec['agent_id']}", {
        "adapterType": saved["adapterType"],
        "replaceAdapterConfig": True,
        "adapterConfig": saved["adapterConfig"] or {},
        "runtimeConfig": saved["runtimeConfig"] or {},
        "metadata": merged,
    })
    after = http.get(f"/api/agents/{spec['agent_id']}")
    got, want = after.get("adapterConfig") or {}, saved["adapterConfig"] or {}
    wrong = [k for k in ("command", "args", "env", "cwd", "timeoutSec")
             if not same(got.get(k), want.get(k))]
    if after.get("adapterType") != saved["adapterType"]:
        wrong.insert(0, "adapterType")
    if not same(after.get("runtimeConfig"), saved["runtimeConfig"] or {}):
        wrong.append("runtimeConfig")
    if wrong:
        # Names only: the values include the old environment.
        die("rollback read-back differs from the saved setup in: "
            + ", ".join(wrong) + f"; the saved setup is still at {preimage}")
    # R26: the result file must not keep describing a live move. The
    # rolledBackAt mark is the same staged 0600 write (panel-2 M12) — a
    # crash mid-mark never leaves truncated bytes behind.
    if os.path.exists(result_path):
        try:
            with open(result_path) as fh:
                result = json.load(fh)
            result["rolledBackAt"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_config_file(result_path, result)
        except (ValueError, OSError):
            pass  # the rollback itself stands; the record is best-effort
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
    # Same one-rename swap, staged 0600 (panel-2 M9), and a MERGE over the
    # live file (panel-2 M10): keys the spec does not hold are kept and
    # named, never silently dropped. Key names only are printed.
    want = carrier_config(spec)
    have = read_live_config(config_path)
    kept = sorted(k for k in have if k not in want)
    merged = merged_carrier_config(have, want)
    config_keys = sorted(k for k in set(want) | set(have)
                         if have.get(k) != merged.get(k))
    if have != merged:
        write_config_file(config_path, merged)
    print(json.dumps({
        "carrierPath": carrier_path, "sha256Before": before,
        "sha256After": sha256_file(carrier_path), "changed": before != after,
        "configPath": config_path, "configChanged": have != merged,
        "configKeysChanged": config_keys, "configKeysKept": kept,
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
