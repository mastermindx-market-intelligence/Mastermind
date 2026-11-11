#!/usr/bin/env python3
"""MMOS lane T2 — create a teammate from a small spec file, or rotate its
primary thread.

A teammate = one Paperclip agent row (the record) + one T3 provider instance
(driver claudeAgent, own homePath, launchArgs carrying the charter via
--append-system-prompt-file) + one primary thread + a `teammate.t3` binding
key inside the agent's existing `metadata` JSON. No new table or registry.

Dev-instance only: the Paperclip base URL comes from the spec and this script
refuses anything that is not loopback. T3 settings edits happen in the dev
root's settings.json while the dev T3 server is STOPPED (a running server may
not reload the file); the script checks the pid file.

Usage:
  setup_teammate.py create <spec.json>
  setup_teammate.py rotate  <spec.json> --title "..." [--message "..."]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def die(msg):
    print(f"setup_teammate: {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg):
    print(f"[setup_teammate] {msg}", flush=True)


def expand(path):
    return os.path.abspath(os.path.expanduser(path))


class Http:
    """Dev-instance Paperclip client (board actor via local_trusted header)."""

    def __init__(self, base):
        # R2a finding 29: the base is pinned by the urlsplit law, not string
        # splits — the local_trusted header rides every call this client
        # makes, so the base must be a plain loopback http origin with a
        # port: scheme http, host 127.0.0.1/localhost/::1, no username or
        # password, a real port, and no path, query or fragment. This is the
        # same law the carrier's loopback_base_error holds for
        # carrier.json's paperclip_base (R2a finding 13).
        parts = urllib.parse.urlsplit(base)
        try:
            port = parts.port
        except ValueError:
            port = None
        host = (parts.hostname or "").lower()
        if (parts.scheme != "http" or host not in ("127.0.0.1", "localhost",
                                                   "::1")
                or parts.username or parts.password or port is None
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            die(f"refusing Paperclip base {base!r}: it must be plain "
                "loopback http with a port, like http://127.0.0.1:3100")
        self.base = base.rstrip("/")

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"x-instance-role": "local_trusted"}
        if data:
            headers["content-type"] = "application/json"
        req = urllib.request.Request(f"{self.base}{path}", data=data,
                                     method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            die(f"{method} {path} -> HTTP {exc.code}: {detail}")

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body):
        return self.call("POST", path, body)

    def patch(self, path, body):
        return self.call("PATCH", path, body)


def write_binding(http, agent_id, binding):
    """The decision-2 write discipline: read, check bindingRevision equals the
    expected value, write with revision+1, read back and compare. Paperclip's
    agent update has no expected-revision field, so this is checked, not
    atomic — a concurrent writer between our read and write is not prevented,
    only detected afterwards by the read-back."""
    agent = http.get(f"/api/agents/{agent_id}")
    current = (agent.get("metadata") or {}).get("teammate", {}).get("t3")
    expected_rev = 0 if current is None else int(current.get("bindingRevision", 0))
    new = dict(binding)
    new["bindingRevision"] = expected_rev + 1
    new["rotatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    merged = dict(agent.get("metadata") or {})
    merged["teammate"] = {"t3": new}
    http.patch(f"/api/agents/{agent_id}", {"metadata": merged})
    after = http.get(f"/api/agents/{agent_id}")
    got = (after.get("metadata") or {}).get("teammate", {}).get("t3") or {}
    if got.get("primaryThreadId") != new["primaryThreadId"] or \
            got.get("bindingRevision") != new["bindingRevision"]:
        die("binding read-back mismatch after write")
    log(f"binding written: revision {expected_rev} -> {new['bindingRevision']} "
        f"(read-back verified)")
    return new


def config_revisions(http, agent_id):
    rows = http.get(f"/api/agents/{agent_id}/config-revisions")
    if isinstance(rows, dict):
        rows = rows.get("revisions") or rows.get("rows") or []
    return rows


def t3_cli(spec, args, stdin_text=None):
    t3 = spec["t3"]
    env = dict(os.environ)
    env["T3CODE_HOME"] = expand(t3["dev_home"])
    proc = subprocess.run([expand(t3["t3_bin"]), *args], input=stdin_text,
                          capture_output=True, text=True,
                          cwd=expand(t3.get("t3_cwd") or "/tmp"), env=env,
                          timeout=900)
    return proc


def t3_output_json(proc, what):
    payload = None
    for line in proc.stdout.splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
    if proc.returncode != 0 or payload is None:
        die(f"{what} failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
    return payload


def ensure_t3_instance(spec):
    """Add the provider instance to the dev settings.json (server stopped)."""
    t3 = spec["t3"]
    home = expand(t3["dev_home"])
    pid_file = os.path.join(expand(t3["dev_root"]), "run", "server.pid")
    if os.path.exists(pid_file):
        pid = open(pid_file).read().strip()
        try:
            os.kill(int(pid), 0)
            die("dev T3 server is running; stop it before editing settings.json")
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    settings_path = os.path.join(home, "userdata", "settings.json")
    settings = json.load(open(settings_path))
    source = settings["providerInstances"].get("capacity_fabric") or \
        next(iter(settings["providerInstances"].values()))
    launch_args = list(t3.get("launch_args") or [])
    charter = expand(t3["charter_path"])
    if "--append-system-prompt-file" in launch_args:
        idx = launch_args.index("--append-system-prompt-file")
        launch_args[idx + 1] = charter
    else:
        launch_args = ["--append-system-prompt-file", charter, *launch_args]
    if t3.get("settings_file"):
        launch_args = [*launch_args, "--settings", expand(t3["settings_file"])]
    instance = {
        "driver": source.get("driver", "claudeAgent"),
        "displayName": t3.get("display_name", spec["name"]),
        "enabled": True,
        "environment": [],
        "config": {
            "homePath": expand(t3["home_path"]),
            # launchArgs is ONE shell-style string in ClaudeSettings
            "launchArgs": " ".join(launch_args),
            "customModels": (source.get("config") or {}).get("customModels"),
        },
    }
    settings.setdefault("providerInstances", {})[t3["instance_id"]] = instance
    # R2a finding 11: the dev server watches settings.json and reloads about
    # 100ms after a change, so the file is swapped in by ONE rename from a
    # staged file that is 0600 from creation — never truncated in place. A
    # failed write leaves the original bytes untouched and removes the
    # staged file; a reader sees the old settings or the new ones, never
    # half of either.
    staged = f"{settings_path}.new-{os.getpid()}"
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(settings, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(staged, settings_path)
    except BaseException:
        try:
            os.unlink(staged)
        except OSError:
            pass
        raise
    log(f"provider instance {t3['instance_id']} in {settings_path} "
        f"(home {t3['home_path']})")


def write_charter_and_home(spec):
    t3 = spec["t3"]
    home = expand(t3["home_path"])
    os.makedirs(home, exist_ok=True)
    os.chmod(home, 0o700)
    charter_path = expand(t3["charter_path"])
    os.makedirs(os.path.dirname(charter_path), exist_ok=True)
    with open(charter_path, "w") as fh:
        fh.write(t3["charter_text"])
    log(f"charter written: {charter_path} ({len(t3['charter_text'])} chars)")
    if t3.get("settings_file"):
        path = expand(t3["settings_file"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(t3["settings_json"], fh, indent=2)
        os.chmod(path, 0o600)
        log(f"enforcement settings written: {path}")


def start_primary_thread(spec):
    t3 = spec["t3"]
    proc = t3_cli(spec, [
        "thread", "start", spec["project_id"],
        spec["primary_thread"].get("message", "Reply with just: READY"),
        "--provider", t3["instance_id"], "--model", t3.get("model", "glm-5.3-flash"),
        "--title", spec["primary_thread"].get("title", f"{spec['name']} primary"),
        "--json"])
    return t3_output_json(proc, "t3 thread start")


def write_carrier_config(spec, agent_dir):
    t3 = spec["t3"]
    cfg = {
        "t3_bin": expand(t3["t3_bin"]),
        "t3_home": expand(t3["dev_home"]),
        "t3_cwd": expand(t3.get("t3_cwd") or "/tmp"),
        "pending_timeout_sec": int(spec.get("pending_timeout_sec", 600)),
        "poll_interval_sec": int(spec.get("poll_interval_sec", 5)),
    }
    # Same-company teammate roster (display name -> agent id) for the carrier's
    # ask block; a name not in this map cannot become a child issue.
    if spec.get("teammates"):
        cfg["teammates"] = dict(spec["teammates"])
    # Optional (R2a finding 4): the carrier defaults to 3 when absent.
    if spec.get("max_asks_per_issue") is not None:
        cfg["max_asks_per_issue"] = int(spec["max_asks_per_issue"])
    # Optional (R2a finding 8 addition): the carrier defaults to 120s absent.
    if spec.get("delivery_reserve_sec") is not None:
        cfg["delivery_reserve_sec"] = int(spec["delivery_reserve_sec"])
    # Optional (R2a finding 13): the pinned loopback base.
    if spec.get("paperclip_base"):
        cfg["paperclip_base"] = spec["paperclip_base"]
    path = os.path.join(agent_dir, "carrier.json")
    with open(path, "w") as fh:
        json.dump(cfg, fh, indent=2)
    return path


def cmd_create(spec_path):
    spec = json.load(open(spec_path))
    write_charter_and_home(spec)
    ensure_t3_instance(spec)
    log("files and provider instance ready; start the dev T3 server, then run "
        "the 'threads' step")
    return 0


def cmd_threads(spec_path):
    """Second step: with the dev T3 server running, mint the primary thread,
    create the Paperclip agent, write the binding (revision discipline)."""
    spec = json.load(open(spec_path))
    http = Http(spec["paperclip_base"])
    t3 = spec["t3"]
    launched = start_primary_thread(spec)
    thread_id = launched["threadId"]
    log(f"primary thread: {thread_id} (instance {t3['instance_id']})")

    agent_dir = expand(spec["agent_dir"])
    os.makedirs(agent_dir, exist_ok=True)
    carrier_cfg = write_carrier_config(spec, agent_dir)
    adapter_config = {
        "command": spec["python_bin"],
        "args": ["-I", expand(spec["carrier_path"]), carrier_cfg],
        "cwd": agent_dir,
        "timeoutSec": int(spec.get("adapter_timeout_sec", 1500)),
    }
    if spec.get("adapter_env"):
        adapter_config["env"] = spec["adapter_env"]
    payload = {
        "name": spec["name"],
        "role": spec.get("role", "engineer"),
        "adapterType": "process",
        "adapterConfig": adapter_config,
        "instructionsBundle": {"files": {
            spec.get("charter_entry", "CHARTER.md"): t3["charter_text"]}},
        "runtimeConfig": {"heartbeat": {"enabled": False}},
        "metadata": {},
    }
    agent = http.post(f"/api/companies/{spec['company_id']}/agents", payload)
    agent_id = agent.get("id") or (agent.get("agent") or {}).get("id")
    if not agent_id:
        die(f"agent create returned no id: {json.dumps(agent)[:300]}")
    log(f"Paperclip agent: {agent_id} ({spec['name']}, process adapter, "
        "heartbeat off)")

    before_rows = config_revisions(http, agent_id)
    binding = {
        "environmentId": spec["environment_id"],
        "projectId": spec["project_id"],
        "providerInstanceId": t3["instance_id"],
        "primaryThreadId": thread_id,
    }
    write_binding(http, agent_id, binding)
    after_rows = config_revisions(http, agent_id)
    log(f"agent_config_revisions rows: {len(before_rows)} -> {len(after_rows)}")
    result = {"agentId": agent_id, "threadId": thread_id,
              "revisionRowsBefore": len(before_rows),
              "revisionRowsAfter": len(after_rows),
              "binding": binding}
    with open(os.path.join(agent_dir, "setup_result.json"), "w") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
    return 0


def cmd_rotate(spec_path, title, message):
    """DONE_WHEN 3: mint a new primary thread, bump the binding revision."""
    spec = json.load(open(spec_path))
    http = Http(spec["paperclip_base"])
    agent_dir = expand(spec["agent_dir"])
    result = json.load(open(os.path.join(agent_dir, "setup_result.json")))
    agent_id = result["agentId"]
    t3 = dict(spec["t3"])
    rotate_spec = dict(spec)
    rotate_spec["primary_thread"] = {"title": title,
                                     "message": message or "Reply with just: READY"}
    launched = start_primary_thread(rotate_spec)
    binding = dict(result["binding"])
    binding["primaryThreadId"] = launched["threadId"]
    new = write_binding(http, agent_id, binding)
    rows = config_revisions(http, agent_id)
    print(json.dumps({"agentId": agent_id, "oldThreadId": result["binding"]["primaryThreadId"],
                      "newThreadId": launched["threadId"],
                      "binding": new, "revisionRows": len(rows)}, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["create", "threads", "rotate"])
    ap.add_argument("spec")
    ap.add_argument("--title")
    ap.add_argument("--message")
    args = ap.parse_args()
    if args.command == "create":
        return cmd_create(args.spec)
    if args.command == "threads":
        return cmd_threads(args.spec)
    return cmd_rotate(args.spec, args.title, args.message)


if __name__ == "__main__":
    sys.exit(main())
