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

Renaming also has no stock CLI command. ``apply`` drives
``roster_browser.js rename`` whenever a saved/recovered thread's durable
title differs from its canonical short title. Set ``browser_profile`` to an
isolated, already-paired profile; renames are otherwise reported as pending
and apply exits nonzero without claiming convergence. No credentials or
pairing URLs are put on a command line.

Spec key ``allow_long_titles: true`` switches to the long-title regime: the
starting state on the real server (threads titled ``Name — long role``) and
the principal's undo. Role lines may then be any one line (still no em dash,
no outer whitespace) and titles may exceed the sidebar's 24-character fit
with a warning. Default (absent/false) keeps the one-word short-title rule
and the hard cap. Title-length policy lives here, not in the browser driver.

The server watches settings.json and reloads it live while running
(apps/server/src/serverSettings.ts:1303-1311, debounced 100ms), so instance
edits take effect without a restart; apply still works against a stopped
server.
"""
import argparse
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import time

RESERVED_PORTS = (3773, 3774)  # the Chairman's own T3 Code app

# A teammate's primary thread is titled exactly "Name — one-word-role". The
# sidebar ellipsizes long titles, so the whole title must fit in 24 characters.
TITLE_MAX = 24
ROLE_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def teammate_title(mate):
    """The one canonical title for a teammate's primary thread.

    Exactly ``Name — role_line`` (em dash, single spaces). ``role_line`` is a
    single ASCII word; ``load_spec`` enforces that and the 24-character cap.
    """
    return f"{mate['name']} — {mate['role_line']}"


def die(msg):
    print(f"team_roster: {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg):
    print(f"[team_roster] {msg}", flush=True)


def log_warn(msg):
    """Progress notes on stdout; warnings on stderr so ``status`` JSON on
    stdout stays parseable when load_spec emits a long-title warning."""
    print(f"[team_roster] {msg}", file=sys.stderr, flush=True)


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
        tools = mate.get("tools", {})
        if not isinstance(tools, dict):
            die(f"{where}.tools must be an object")
        for key, value in tools.items():
            if key not in ("browser_use", "computer_use"):
                die(f"{where}.tools has unknown key {key!r}")
            if not isinstance(value, bool):
                die(f"{where}.tools.{key} must be a boolean")
        # Default off: any tool flag the spec does not set is False.
        if "—" in mate["name"] or mate["name"] != mate["name"].strip():
            die(f"{where}.name must not contain an em dash or outer spaces")
        allow_long = spec.get("allow_long_titles") is True
        if allow_long:
            # Long-title regime (the real server's current state, and the
            # principal's undo): role_line may be any one line, but the title
            # must stay exactly "Name — role_line" (one em dash, no padding).
            role = mate["role_line"]
            if (not role or role != role.strip() or "—" in role
                    or "\n" in role or "\r" in role):
                die(f"{where}.role_line must be one non-empty line without an "
                    f"em dash or outer spaces, got {mate['role_line']!r}")
        elif not ROLE_LINE_RE.fullmatch(mate["role_line"]):
            die(f"{where}.role_line must be one ASCII word (letters, digits, "
                f"'_' or '-'), got {mate['role_line']!r}")
        title = teammate_title(mate)
        if len(title) > TITLE_MAX:
            if allow_long:
                log_warn(f"{where}: title {title!r} is {len(title)} characters; "
                         f"the sidebar fits {TITLE_MAX} and will ellipsize it "
                         f"(allow_long_titles)")
            else:
                die(f"{where} title {title!r} is {len(title)} characters; the "
                    f"sidebar fits at most {TITLE_MAX}")
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


def list_threads(spec, project_id):
    """Every live thread in the project, with its durable provider instance.

    ``provider_instance_id`` is the column the server writes for a thread's
    provider instance (``orchestration_v2_projection_threads``); the same value
    is mirrored in ``payload_json.providerInstanceId``. Either is durable
    evidence of which teammate a thread belongs to, independent of its title.
    """
    with db(spec) as conn:
        rows = conn.execute(
            "SELECT thread_id, "
            "COALESCE(title, json_extract(payload_json, '$.title')) AS title, "
            "json_extract(payload_json, '$.pinnedAt') AS pinned_at, "
            "COALESCE(provider_instance_id, "
            "json_extract(payload_json, '$.providerInstanceId')) AS instance "
            "FROM orchestration_v2_projection_threads "
            "WHERE project_id = ? AND deleted_at IS NULL "
            "ORDER BY created_at, thread_id", (project_id,)).fetchall()
    return [{"threadId": r["thread_id"], "title": r["title"],
             "pinnedAt": r["pinned_at"], "instance": r["instance"]}
            for r in rows]


def threads_in_project(spec, project_id):
    """Compatibility view: exact title → {threadId, pinnedAt}."""
    return {t["title"]: {"threadId": t["threadId"], "pinnedAt": t["pinnedAt"]}
            for t in list_threads(spec, project_id)}


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


# Entries of the server root a teammate never needs to read. `run` holds the
# pairing file, the server log and the paired browser profile; `home` is the
# T3 server's own state (sessions, secrets, settings).
SERVER_PRIVATE = ("run", "home", "config", "claude-home", "fabric.env")

# Files in a teammate's own home that are config or credentials, not memory.
# The teammate may not change them; the preimage it may not even read.
HOME_LOCKED = ("tool-limits.json", "CHARTER.md", "carrier.json",
               "cutover-preimage.json", "cutover-result.json",
               "mcp-servers.json")
HOME_UNREADABLE = ("cutover-preimage.json",)

# A teammate's home is also its Claude configuration folder. A settings file
# or an MCP entry there can name a command to run, and a skill, agent, rule
# or plugin there is loaded as instructions, so a teammate that may create
# files in its home could give itself a shell (found by the principal with
# MAS-15: creating a new file in the home is allowed). The runtime writes
# these itself without the Write tool; the teammate's tools may not.
HOME_CONFIG = ("settings.json", "settings.local.json", "managed-settings.json",
               ".claude.json", ".mcp.json", ".credentials.json",
               "keybindings.json", "CLAUDE.local.md", ".claude", "plugins",
               "skills", "agents", "commands", "hooks", "rules",
               "output-styles", "backups", "sessions", "projects", "todos",
               "shell-snapshots", "statsig", "ide")


def _read_deny(path):
    """Deny rules for one path: a directory denies its whole tree."""
    if os.path.isdir(path):
        return [f"Read(/{path}/**)"]
    if os.path.exists(path):
        return [f"Read(/{path})"]
    return [f"Read(/{path})", f"Read(/{path}/**)"]


def deny_read_paths(spec, mate):
    """What a teammate must not read (review R2a, finding 1).

    A teammate runs as the same user as everything else on this Mac, so file
    modes do not protect a credential from it. Text in an issue can ask it to
    read a file and quote it back, and the carrier posts its reply. Deny
    rules win over the plain `Read` allow.
    """
    root = expand(spec["server"]["root"])
    paths = [os.path.join(root, name) for name in SERVER_PRIVATE]
    for other in spec["teammates"]:
        if other["slug"] != mate["slug"]:
            paths.append(teammate_home(spec, other))
    home = teammate_home(spec, mate)
    paths += [os.path.join(home, name) for name in HOME_UNREADABLE]
    paths += [expand(r) for r in spec.get("deny_read_roots", [])]
    if spec.get("deny_read_root_siblings"):
        parent = os.path.dirname(root)
        if os.path.isdir(parent):
            for name in sorted(os.listdir(parent)):
                if name != os.path.basename(root):
                    paths.append(os.path.join(parent, name))
    seen, out = set(), []
    for path in paths:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def tool_limits(spec, mate):
    home = teammate_home(spec, mate)
    deny_roots = [expand(spec["project"]["workspace_root"])]
    deny_roots += [os.path.abspath(r) for r in spec.get("deny_write_roots", [])]
    deny = ["Bash", "Agent", "NotebookEdit"]
    for root in deny_roots:
        deny += [f"Write(/{root}/**)", f"Edit(/{root}/**)"]
    for name in HOME_LOCKED:
        locked = os.path.join(home, name)
        deny += [f"Write(/{locked})", f"Edit(/{locked})"]
    for name in HOME_CONFIG:
        config = os.path.join(home, name)
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{config})", f"{tool}(/{config}/**)"]
    for path in deny_read_paths(spec, mate):
        deny += _read_deny(path)
    allow = [
        "Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
        f"Write(/{home}/**)", f"Edit(/{home}/**)",
    ]
    return {
        "permissions": {"allow": allow, "deny": deny},
        "_note": ("allow/deny enumerations in Claude Code permission syntax; "
                  "deny wins over allow; an unlisted outside-home write raises "
                  "an approval request rather than silently writing"),
    }


def write_file_assets(spec, mate):
    """Home dir, CLAUDE.md seed, CHARTER.md, tool-limits.json,
    and (only when the spec switches tools on) mcp-servers.json.

    CLAUDE.md is the teammate's live long-term memory: created only when
    missing, never rewritten by apply (a rewrite would erase remembered
    facts). CHARTER.md and tool-limits.json are config and follow the spec.
    mcp-servers.json names commands to run, so it is written by the runtime
    only, joins HOME_LOCKED, and exists only for switched-on teammates.
    """
    home = teammate_home(spec, mate)
    os.makedirs(home, exist_ok=True)
    os.chmod(home, 0o700)
    charter = os.path.join(home, "CHARTER.md")
    limits = os.path.join(home, "tool-limits.json")
    seed = ("<!-- Long-term memory of {name}. Append durable facts below; "
            "they persist across conversations and server restarts. -->\n"
            "# {name} — memory\n\n").format(name=mate["name"])
    wrote = []
    memory = os.path.join(home, "CLAUDE.md")
    if not os.path.exists(memory):
        write_if_changed(memory, seed, 0o600)
        wrote.append("CLAUDE.md")
    if write_if_changed(charter, mate["charter"], 0o600):
        wrote.append("CHARTER.md")
    if write_if_changed(limits, json.dumps(tool_limits(spec, mate), indent=2) + "\n",
                        0o600):
        wrote.append("tool-limits.json")
    mcp_path = os.path.join(home, "mcp-servers.json")
    entries = mcp_entries_for(mate)
    if entries:
        if write_if_changed(mcp_path,
                            json.dumps(entries, indent=2) + "\n", 0o600):
            wrote.append("mcp-servers.json")
    elif os.path.exists(mcp_path):
        # Switched off after being on: remove the runtime-written file so a
        # stale registration can never outlive its spec entry.
        os.unlink(mcp_path)
    return wrote


# Tool access is decided by the roster spec, never by the teammate. Entries
# reference the installed adapter files; absolute paths, no environment
# secrets (the session's own environment carries the fabric route).
MCP_TOOL_ENTRIES = {
    "browser_use": ("mmx-browser", {
        "type": "stdio",
        "command": "/Users/chriswong/.local/share/mastermind-runtime/node/bin/node",
        "args": ["/Users/chriswong/.t3/mcp/mmx-browser/server.js"],
    }),
    "computer_use": ("mmos-computer-use", {
        "type": "stdio",
        "command": "/usr/bin/python3",
        "args": ["/Users/chriswong/.t3/mcp/mmos-computer-use/server.py"],
    }),
}


def mcp_entries_for(mate):
    """mcpServers entries for a teammate, or {} when no tool is switched on."""
    tools = mate.get("tools") or {}
    entries = {}
    for flag in sorted(MCP_TOOL_ENTRIES):
        if tools.get(flag) is True:
            name, entry = MCP_TOOL_ENTRIES[flag]
            entries[name] = entry
    return entries


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
    if mcp_entries_for(mate):
        launch_args += ["--mcp-config",
                        os.path.join(home, "mcp-servers.json")]
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


def _recover_thread(mate, live, recorded_by_name):
    """The one live thread that is this teammate's, or ``(None, None)``.

    Evidence, strongest first: the thread id saved in state (a renamed title
    is still the same thread), then the thread's durable provider instance,
    then the stable ``"Name — "`` title prefix. Returns ``(thread, problem)``;
    ``problem`` is a sentence when the evidence is ambiguous or points at
    another teammate. Adopting the wrong thread would put a teammate into
    someone else's conversation, so ambiguity is refused, never guessed.
    """
    name = mate["name"]
    others = {n: tid for n, tid in recorded_by_name.items()
              if n != name and tid}
    by_id = {t["threadId"]: t for t in live}
    recorded = recorded_by_name.get(name)
    if recorded:
        if recorded in others.values():
            return None, (f"saved thread {recorded} is also recorded for "
                          f"another teammate")
        if recorded in by_id:
            found = by_id[recorded]
            if found["instance"] and found["instance"] != mate["instance"]:
                return None, (f"saved thread {recorded} belongs to provider "
                              f"instance {found['instance']!r}, not "
                              f"{mate['instance']!r}")
            return found, None
    candidates = {}
    for t in live:
        if t["threadId"] in others.values():
            continue  # recorded to another teammate
        if t["instance"] == mate["instance"]:
            candidates[t["threadId"]] = t
    prefix = f"{name} — "
    for t in live:
        if t["threadId"] in others.values():
            continue
        if (t["title"] or "").startswith(prefix):
            candidates[t["threadId"]] = t
    if len(candidates) > 1:
        return None, (f"{len(candidates)} threads could be its primary "
                      f"({', '.join(sorted(candidates))})")
    if not candidates:
        return None, None
    found = next(iter(candidates.values()))
    if found["instance"] and found["instance"] != mate["instance"]:
        return None, (f"thread {found['threadId']} is titled for {name} but "
                      f"belongs to provider instance {found['instance']!r}")
    return found, None


def _recovered_by(mate, found, recorded):
    if found["threadId"] == recorded:
        return "state"
    if found["instance"] == mate["instance"]:
        return "instance"
    return "title"


def ensure_threads(spec, project_id):
    state, state_path = load_state(spec)
    live = list_threads(spec, project_id)
    recorded_by_name = {name: (entry or {}).get("threadId")
                        for name, entry in state["teammates"].items()}
    threads = {}
    for mate in spec["teammates"]:
        title = teammate_title(mate)
        recorded = recorded_by_name.get(mate["name"])
        found, problem = _recover_thread(mate, live, recorded_by_name)
        if problem:
            die(f"{mate['name']}: {problem}; refusing to pick or create a "
                f"primary thread")
        if found is not None:
            threads[mate["name"]] = {
                "threadId": found["threadId"], "title": title,
                "created": False, "currentTitle": found["title"],
                "projectId": project_id, "pinnedAt": found["pinnedAt"],
                "recoveredBy": _recovered_by(mate, found, recorded),
                "instance": found["instance"] or mate["instance"],
            }
            if found["title"] != title:
                log(f"{mate['name']}: thread {found['threadId']} is titled "
                    f"{found['title']!r}; the roster title is {title!r}")
            continue
        launched = t3_json(t3(spec, [
            "thread", "start", project_id, "Reply with just: READY",
            "--provider", mate["instance"], "--model", spec["model"],
            "--title", title, "--json"]), "t3 thread start")
        threads[mate["name"]] = {"threadId": launched["threadId"],
                                 "projectId": project_id, "pinnedAt": None,
                                 "currentTitle": title,
                                 "title": title, "created": True,
                                 "recoveredBy": None,
                                 "instance": mate["instance"]}
        log(f"primary thread for {mate['name']}: {launched['threadId']}")
    seen = {}
    for name, info in threads.items():
        if info["threadId"] in seen:
            die(f"{name} and {seen[info['threadId']]} resolved to the same "
                f"thread {info['threadId']}; refusing")
        seen[info["threadId"]] = name
    by_name = {mate["name"]: mate for mate in spec["teammates"]}
    state["teammates"] = {name: {"instance": by_name[name]["instance"],
                                 "threadId": info["threadId"],
                                 "title": info["title"],
                                 "threadInstance": info["instance"],
                                 "recoveredBy": info["recoveredBy"]}
                          for name, info in threads.items()}
    state["appliedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(spec, state, state_path)
    return threads, state_path


def rename_threads(spec, threads):
    """Apply short titles through the web UI, then require DB read-back.

    Every call receives its already-known thread id and current title. No
    operation can target a title prefix or another teammate's thread. The
    profile is supplied by the operator, never inferred from a live server's
    credential files, and no token appears in argv.
    """
    stale = [(mate, threads[mate["name"]]["currentTitle"])
             for mate in spec["teammates"]
             if threads[mate["name"]]["currentTitle"] != teammate_title(mate)]
    if not stale:
        return {mate["name"]: False for mate in spec["teammates"]}, []
    profile = spec.get("browser_profile")
    if not profile:
        log("title renames pending: browser_profile is not configured")
        return ({mate["name"]: False for mate in spec["teammates"]},
                [mate["name"] for mate, _ in stale])
    # A profile is credential-bearing state: require a private directory and
    # an absolute root supplied by the spec (defaults to the server root).
    profile = os.path.realpath(expand(profile))
    allowed_root = os.path.realpath(expand(
        spec.get("browser_profile_root") or spec["server"]["root"]))
    if profile == allowed_root or not profile.startswith(allowed_root + os.sep):
        die("browser_profile must be a private child of browser_profile_root "
            "(default: the team server root)")
    if not os.path.isdir(profile):
        die(f"browser_profile does not exist: {profile}; pair it before apply")
    if os.stat(profile).st_uid != os.getuid():
        die("browser_profile belongs to another user")
    if stat.S_IMODE(os.stat(profile).st_mode) & 0o077:
        die("browser_profile must not be accessible by group or other users")
    driver = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "roster_browser.js")
    env_id = environment_id(spec)
    if not env_id:
        die("environment-id missing from the team home")
    node_bin = spec.get("browser_node") or os.environ.get("TEAM_ROSTER_NODE")
    if not node_bin:
        import shutil
        node_bin = shutil.which("node")
    if not node_bin or not os.access(expand(node_bin), os.X_OK):
        die("no executable Node for roster_browser.js; set browser_node")
    evidence_path = expand(spec.get("rename_evidence_file") or os.path.join(
        spec["server"]["root"], "run", "team_renames.jsonl"))
    os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
    failures = []
    with open(evidence_path, "a") as evidence:
        os.chmod(evidence_path, 0o600)
        for stale_thread in stale:
            mate, current_title = stale_thread
            title = teammate_title(mate)
            tid = threads[mate["name"]]["threadId"]
            url = (f"http://127.0.0.1:{spec['server']['port']}/{env_id}/"
                   f"{tid.replace(':', '%3A')}")
            result_path = (f"{evidence_path}.tmp.{os.getpid()}."
                           f"{mate['slug']}.json")
            proc = subprocess.run(
                [expand(node_bin), driver, "rename", profile, url, tid,
                 current_title, title, result_path],
                cwd="/tmp", capture_output=True, text=True, timeout=120)
            ok = proc.returncode == 0 and os.path.isfile(result_path)
            live = None
            if ok:
                # Re-read the persisted projection; an in-memory or sidebar
                # title update does not prove durable rename completion.
                live = next((t for t in list_threads(
                    spec, threads[mate["name"]]["projectId"])
                    if t["threadId"] == tid), None)
                ok = (live is not None and live["title"] == title and
                      live["pinnedAt"] == threads[mate["name"]]["pinnedAt"])
            row = {"threadId": tid, "oldTitle": current_title,
                   "newTitle": title, "verified": ok,
                   "pinnedAtBefore": threads[mate["name"]]["pinnedAt"],
                   "pinnedAtAfter": (live or {}).get("pinnedAt")}
            if not ok:
                row["error"] = (proc.stderr or proc.stdout or
                                "no durable title read-back")[:300]
                failures.append(mate["name"])
            evidence.write(json.dumps(row) + "\n")
            evidence.flush()
            if os.path.exists(result_path):
                os.unlink(result_path)
            if ok:
                threads[mate["name"]]["title"] = title
                threads[mate["name"]]["renamed"] = True
                log(f"{mate['name']}: renamed {current_title!r} -> {title!r}")
    return {mate["name"]: threads[mate["name"]].get("renamed", False)
            for mate in spec["teammates"]}, failures


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
    renames, rename_failures = rename_threads(spec, threads)
    urls_path = write_urls_file(spec, threads)
    log(f"thread URLs written: {urls_path} (0600, no credentials)")
    report = {
        "projectId": project_id,
        "teammates": [
            {"name": mate["name"], "instance": mate["instance"],
             "home": teammate_home(spec, mate),
             "threadId": threads[mate["name"]]["threadId"],
             "threadTitle": threads[mate["name"]]["title"],
             "threadCreated": threads[mate["name"]]["created"],
             "renamed": renames[mate["name"]]}
            for mate in spec["teammates"]],
        "pin": "not applied by this tool; pin via roster_browser.js pin "
               "(web-client-only action)",
    }
    print(json.dumps(report, indent=2))
    if rename_failures:
        print("team_roster: INCOMPLETE title(s); these threads failed durable "
              "read-back: " + ", ".join(rename_failures), file=sys.stderr)
        return 1
    return 0


def cmd_status(spec):
    project = project_by_root(spec)
    settings = load_settings(spec)
    instances = settings.get("providerInstances", {})
    state, _ = load_state(spec)
    live = list_threads(spec, project["project_id"]) if project else []
    recorded_by_name = {name: (entry or {}).get("threadId")
                        for name, entry in state["teammates"].items()}
    rows = []
    for mate in spec["teammates"]:
        home = teammate_home(spec, mate)
        instance = instances.get(mate["instance"])
        title = teammate_title(mate)
        thread, problem = _recover_thread(mate, live, recorded_by_name)
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
            "threadCurrentTitle": (thread or {}).get("title"),
            "pinned": bool((thread or {}).get("pinnedAt")),
            "recoveryProblem": problem,
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
