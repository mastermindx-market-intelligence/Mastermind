#!/usr/bin/env python3
"""MMOS lane T7 — the Team roster on the team T3 server.

apply <spec.json>  Idempotently creates or updates: the Team project (one
                    workspace root), each teammate's home directory (CLAUDE.md
                    memory seed, CHARTER.md, tool-limits.json), the provider
                    instance (displayName = teammate name, accentColor, model
                    list copied from the source instance), and one primary
                    thread titled "Name — role line". Running apply twice
                    changes nothing the second time.
status <spec.json> Read-only report: what exists, thread ids, pin state, deep
                    URLs.

Pinning has no server command or RPC surface (the stock CLI offers only
thread start/send/show/list and project add/remove/rename; pin lives behind
the web client's thread action menu, apps/web/src/components/
threadActionMenu.logic.ts:136). Pin the threads with roster_browser.js pin.

The server watches settings.json and reloads it live while running
(apps/server/src/serverSettings.ts:1303-1311, debounced 100ms), so instance
edits take effect without a restart; apply still works against a stopped
server.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time

RESERVED_PORTS = (3773, 3774)  # the Chairman's own T3 Code app


def die(msg):
    print(f"team_roster: {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg):
    print(f"[team_roster] {msg}", flush=True)


def expand(path):
    return os.path.abspath(os.path.expanduser(path))


def load_spec(path):
    try:
        spec = json.load(open(path))
    except (OSError, ValueError) as exc:
        die(f"cannot read spec {path}: {exc}")
    for key in ("server", "project", "model", "teammates"):
        if key not in spec:
            die(f"spec missing required key '{key}'")
    server, project = spec["server"], spec["project"]
    for key in ("root", "home", "t3_bin", "port"):
        if key not in server:
            die(f"spec.server missing required key '{key}'")
    for key in ("title", "workspace_root"):
        if key not in project:
            die(f"spec.project missing required key '{key}'")
    try:
        server["port"] = int(server["port"])
    except (TypeError, ValueError):
        die(f"server.port is not an integer: {server['port']!r}")
    if server["port"] in RESERVED_PORTS:
        die(f"server.port {server['port']} is reserved for the Chairman's "
            f"T3 Code app; refusing")
    root = os.path.realpath(expand(server["root"]))
    dot_t3 = os.path.realpath(expand("~/.t3"))
    if root == dot_t3 or root.startswith(dot_t3 + os.sep):
        die(f"server root {root} is at or inside ~/.t3; refusing")
    if not isinstance(spec["teammates"], list) or not spec["teammates"]:
        die("spec.teammates must be a non-empty list")
    names, instances, slugs, colors = set(), set(), set(), set()
    for i, mate in enumerate(spec["teammates"]):
        where = f"teammates[{i}]"
        for key in ("name", "slug", "role", "role_line", "accent_color",
                    "instance", "charter"):
            if not mate.get(key):
                die(f"{where} missing required key '{key}'")
        if mate["name"] in names:
            die(f"duplicate teammate name {mate['name']!r}")
        if mate["instance"] in instances:
            die(f"duplicate instance id {mate['instance']!r}")
        if mate["slug"] in slugs:
            die(f"duplicate slug {mate['slug']!r}")
        if mate["accent_color"].lower() in colors:
            die(f"duplicate accent_color {mate['accent_color']!r}")
        names.add(mate["name"])
        instances.add(mate["instance"])
        slugs.add(mate["slug"])
        colors.add(mate["accent_color"].lower())
    return spec


def t3_home(spec):
    return expand(spec["server"]["home"])


def db_path(spec):
    return os.path.join(t3_home(spec), "userdata", "statev2.sqlite")


def t3(spec, args, stdin_text=None, timeout=900):
    server = spec["server"]
    env = dict(os.environ)
    env["T3CODE_HOME"] = t3_home(spec)
    env["T3CODE_PORT"] = str(server["port"])
    return subprocess.run([expand(server["t3_bin"]), *args], input=stdin_text,
                          capture_output=True, text=True, cwd="/tmp", env=env,
                          timeout=timeout)


def t3_json(proc, what):
    payload = None
    for line in proc.stdout.splitlines():
        if line.startswith("{") or line.startswith("["):
            try:
                payload = json.loads(line)
            except ValueError:
                pass
    if proc.returncode != 0 or payload is None:
        die(f"{what} failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:300]}")
    return payload


def db(spec):
    if not os.path.exists(db_path(spec)):
        die(f"no state database at {db_path(spec)}; is this the team home?")
    conn = sqlite3.connect(f"file:{db_path(spec)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def project_by_root(spec):
    root = expand(spec["project"]["workspace_root"])
    with db(spec) as conn:
        row = conn.execute(
            "SELECT project_id, title, workspace_root FROM projection_projects "
            "WHERE workspace_root = ? AND deleted_at IS NULL", (root,)).fetchone()
    return dict(row) if row else None


def threads_in_project(spec, project_id):
    with db(spec) as conn:
        rows = conn.execute(
            "SELECT thread_id, json_extract(payload_json, '$.title') AS title, "
            "json_extract(payload_json, '$.pinnedAt') AS pinned_at, deleted_at "
            "FROM orchestration_v2_projection_threads "
            "WHERE project_id = ? AND deleted_at IS NULL", (project_id,)).fetchall()
    return {r["title"]: {"threadId": r["thread_id"], "pinnedAt": r["pinned_at"]}
            for r in rows}


def ensure_project(spec):
    project = project_by_root(spec)
    if project:
        log(f"project exists: {project['project_id']} "
            f"(title {project['title']!r})")
        return project["project_id"]
    root = expand(spec["project"]["workspace_root"])
    os.makedirs(root, exist_ok=True)
    proc = t3(spec, ["project", "add", root, "--title", spec["project"]["title"]])
    if proc.returncode != 0:
        die(f"t3 project add failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:300]}")
    project = project_by_root(spec)
    if not project:
        die("project add returned success but the project is not in the store")
    log(f"project created: {project['project_id']}")
    return project["project_id"]


def teammate_home(spec, mate):
    return os.path.join(expand(spec["server"]["root"]), "teammates",
                        mate["slug"])


def write_if_changed(path, text, mode):
    changed = True
    if os.path.exists(path) and open(path).read() == text:
        changed = False
    else:
        with open(path, "w") as fh:
            fh.write(text)
    os.chmod(path, mode)
    return changed


def tool_limits(spec, mate):
    home = teammate_home(spec, mate)
    deny_roots = [expand(spec["project"]["workspace_root"])]
    deny_roots += [os.path.abspath(r) for r in spec.get("deny_write_roots", [])]
    deny = ["Bash", "Agent", "NotebookEdit"]
    for root in deny_roots:
        deny += [f"Write(/{root}/**)", f"Edit(/{root}/**)"]
    allow = [
        "Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
        f"Write(/{home}/**)", f"Edit(/{home}/**)",
    ]
    return {
        "permissions": {"allow": allow, "deny": deny},
        "_note": ("allow/deny enumerations in Claude Code permission syntax; "
                  "an unlisted outside-home write raises an approval request "
                  "rather than silently writing"),
    }


def write_file_assets(spec, mate):
    """Home dir, CLAUDE.md seed, CHARTER.md, tool-limits.json."""
    home = teammate_home(spec, mate)
    os.makedirs(home, exist_ok=True)
    os.chmod(home, 0o700)
    charter = os.path.join(home, "CHARTER.md")
    limits = os.path.join(home, "tool-limits.json")
    seed = ("<!-- Long-term memory of {name}. Append durable facts below; "
            "they persist across conversations and server restarts. -->\n"
            "# {name} — memory\n\n").format(name=mate["name"])
    wrote = []
    if write_if_changed(os.path.join(home, "CLAUDE.md"), seed, 0o600):
        wrote.append("CLAUDE.md")
    if write_if_changed(charter, mate["charter"], 0o600):
        wrote.append("CHARTER.md")
    if write_if_changed(limits, json.dumps(tool_limits(spec, mate), indent=2) + "\n",
                        0o600):
        wrote.append("tool-limits.json")
    return wrote


def settings_path(spec):
    return os.path.join(t3_home(spec), "userdata", "settings.json")


def load_settings(spec):
    path = settings_path(spec)
    if not os.path.exists(path):
        die(f"no settings.json at {path}; seed the home first")
    return json.load(open(path))


def instance_for(spec, mate):
    home = teammate_home(spec, mate)
    launch_args = [
        "--append-system-prompt-file", os.path.join(home, "CHARTER.md"),
        "--settings", os.path.join(home, "tool-limits.json"),
    ]
    return {
        "driver": "claudeAgent",
        "displayName": mate["name"],
        "enabled": True,
        "environment": [],
        "accentColor": mate["accent_color"],
        "config": {
            "homePath": home,
            "launchArgs": " ".join(launch_args),
        },
    }


def ensure_instances(spec):
    """Merge each teammate's provider instance into settings.json.

    Preserves every other instance, every unknown key, and the file's 0600
    mode; copies customModels from the source instance at apply time. A
    no-change apply performs no write.
    """
    settings = load_settings(spec)
    source_id = spec["server"].get("provider_source_instance")
    instances = settings.setdefault("providerInstances", {})
    if source_id not in instances:
        die(f"source instance {source_id!r} missing from settings.json")
    source = instances[source_id]
    models = (source.get("config") or {}).get("customModels")
    changed = []
    for mate in spec["teammates"]:
        want = instance_for(spec, mate)
        want["config"]["customModels"] = models
        have = instances.get(mate["instance"])
        if have != want:
            instances[mate["instance"]] = want
            changed.append(mate["instance"])
    if changed:
        with open(settings_path(spec), "w") as fh:
            json.dump(settings, fh, indent=2)
        os.chmod(settings_path(spec), 0o600)
        log(f"provider instances written: {', '.join(changed)} "
            "(settings.json is watched live by the running server)")
    else:
        log("provider instances already up to date; settings.json untouched")
    return changed


def load_state(spec):
    path = expand(spec.get("state_file") or
                  os.path.join(spec["server"]["root"], "run",
                               "team_roster_state.json"))
    if os.path.exists(path):
        return json.load(open(path)), path
    return {"teammates": {}}, path


def save_state(spec, state, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def environment_id(spec):
    path = os.path.join(t3_home(spec), "userdata", "environment-id")
    try:
        return open(path).read().strip()
    except OSError:
        return None


def ensure_threads(spec, project_id):
    state, state_path = load_state(spec)
    existing = threads_in_project(spec, project_id)
    threads = {}
    for mate in spec["teammates"]:
        title = f"{mate['name']} — {mate['role_line']}"
        recorded = (state["teammates"].get(mate["name"]) or {}).get("threadId")
        if recorded and recorded in [v["threadId"] for v in existing.values()]:
            threads[mate["name"]] = {"threadId": recorded, "title": title,
                                     "created": False}
            continue
        if title in existing:  # recovery: thread exists but state was lost
            threads[mate["name"]] = {"threadId": existing[title]["threadId"],
                                     "title": title, "created": False}
            continue
        launched = t3_json(t3(spec, [
            "thread", "start", project_id, "Reply with just: READY",
            "--provider", mate["instance"], "--model", spec["model"],
            "--title", title, "--json"]), "t3 thread start")
        threads[mate["name"]] = {"threadId": launched["threadId"],
                                 "title": title, "created": True}
        log(f"primary thread for {mate['name']}: {launched['threadId']}")
    by_name = {mate["name"]: mate for mate in spec["teammates"]}
    state["teammates"] = {name: {"instance": by_name[name]["instance"],
                                 "threadId": info["threadId"],
                                 "title": info["title"]}
                          for name, info in threads.items()}
    state["appliedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(spec, state, state_path)
    return threads, state_path


def write_urls_file(spec, threads):
    env_id = environment_id(spec)
    if not env_id:
        die("environment-id missing from the team home")
    out = {"environmentId": env_id, "updatedAt":
           time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "teammates": []}
    for mate in spec["teammates"]:
        info = threads[mate["name"]]
        tid = info["threadId"]
        out["teammates"].append({
            "name": mate["name"],
            "instanceId": mate["instance"],
            "threadId": tid,
            "url": f"http://127.0.0.1:{spec['server']['port']}/{env_id}/"
                   f"{tid.replace(':', '%3A')}",
        })
    path = expand(spec.get("urls_file") or
                  os.path.join(spec["server"]["root"], "run", "team_urls.json"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def cmd_apply(spec):
    project_id = ensure_project(spec)
    for mate in spec["teammates"]:
        wrote = write_file_assets(spec, mate)
        home = teammate_home(spec, mate)
        log(f"{mate['name']}: home {home} "
            + (f"(wrote {', '.join(wrote)})" if wrote else "(unchanged)"))
    ensure_instances(spec)
    threads, _ = ensure_threads(spec, project_id)
    urls_path = write_urls_file(spec, threads)
    log(f"thread URLs written: {urls_path} (0600, no credentials)")
    report = {
        "projectId": project_id,
        "teammates": [
            {"name": mate["name"], "instance": mate["instance"],
             "home": teammate_home(spec, mate),
             "threadId": threads[mate["name"]]["threadId"],
             "threadTitle": threads[mate["name"]]["title"],
             "threadCreated": threads[mate["name"]]["created"]}
            for mate in spec["teammates"]],
        "pin": "not applied by this tool; pin via roster_browser.js pin "
               "(web-client-only action)",
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_status(spec):
    project = project_by_root(spec)
    settings = load_settings(spec)
    instances = settings.get("providerInstances", {})
    state, _ = load_state(spec)
    existing = threads_in_project(spec, project["project_id"]) if project else {}
    rows = []
    for mate in spec["teammates"]:
        home = teammate_home(spec, mate)
        instance = instances.get(mate["instance"])
        title = f"{mate['name']} — {mate['role_line']}"
        thread = existing.get(title)
        if thread is None:
            recorded = (state["teammates"].get(mate["name"]) or {}).get("threadId")
            for candidate in existing.values():
                if candidate["threadId"] == recorded:
                    thread = candidate
                    break
        rows.append({
            "name": mate["name"],
            "home": home,
            "homeOk": os.path.isdir(home) and
                      os.path.exists(os.path.join(home, "CHARTER.md")),
            "instance": mate["instance"],
            "instanceOk": instance is not None and
                          instance.get("displayName") == mate["name"] and
                          instance.get("accentColor") == mate["accent_color"],
            "threadTitle": title,
            "threadId": (thread or {}).get("threadId"),
            "pinned": bool((thread or {}).get("pinnedAt")),
        })
    print(json.dumps({"project": project, "teammates": rows,
                      "environmentId": environment_id(spec)}, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["apply", "status"])
    ap.add_argument("spec")
    args = ap.parse_args()
    spec = load_spec(args.spec)
    if args.command == "apply":
        return cmd_apply(spec)
    return cmd_status(spec)


if __name__ == "__main__":
    sys.exit(main())
