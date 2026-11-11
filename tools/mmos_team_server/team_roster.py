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
import urllib.error
import urllib.parse
import urllib.request

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
    if spec.get("assets_dir"):
        # Proved live 2026-11-11 on the RL dev server: a --settings file
        # outside the teammate home loads, but its Read/Glob/Grep deny
        # rules silently do not bind — the teammate reads everything the
        # spec denies. Evidence: rl-20261111/10-rule-semantics-round2.md.
        die("spec key 'assets_dir' is refused: limits outside the teammate "
            "home silently disable Read/Glob/Grep deny rules (live-proved "
            "2026-11-11); tool-limits.json stays in the home, protected by "
            "the HOME_LOCKED write denies")
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
    if spec.get("paperclip_base"):
        # Parsed, never prefix-compared: a userinfo or subdomain trick must
        # not smuggle a foreign host past the loopback requirement.
        try:
            parsed = urllib.parse.urlparse(spec["paperclip_base"])
            hostname = parsed.hostname
            scheme = parsed.scheme
        except ValueError:
            hostname, scheme = None, None
        if scheme != "http" or hostname not in ("127.0.0.1", "localhost",
                                                "::1"):
            die(f"paperclip_base {spec['paperclip_base']!r} is not a "
                f"loopback http URL (for example http://127.0.0.1:3100)")
    if not isinstance(spec["teammates"], list) or not spec["teammates"]:
        die("spec.teammates must be a non-empty list")
    names, instances, slugs, colors = set(), set(), set(), set()
    for i, mate in enumerate(spec["teammates"]):
        where = f"teammates[{i}]"
        for key in ("name", "slug", "role", "role_line", "accent_color",
                    "instance", "charter"):
            if not mate.get(key):
                die(f"{where} missing required key '{key}'")
        agent_id = mate.get("paperclip_agent_id")
        if agent_id is not None and (
                not isinstance(agent_id, str) or not agent_id.strip()
                or "/" in agent_id or agent_id != agent_id.strip()):
            die(f"{where}.paperclip_agent_id must be a plain id without "
                f"slashes or padding, got {agent_id!r}")
        if mate["name"] in names:
            die(f"duplicate teammate name {mate['name']!r}")
        if mate["instance"] in instances:
            die(f"duplicate instance id {mate['instance']!r}")
        if mate["slug"] in slugs:
            die(f"duplicate slug {mate['slug']!r}")
        if mate["accent_color"].lower() in colors:
            die(f"duplicate accent_color {mate['accent_color']!r}")
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


def atomic_write(path, text, mode):
    """Replace ``path`` with ``text`` atomically (review R2a, finding 11).

    The running server watches settings.json and reloads it about 100 ms
    after a change, and a teammate process reads tool-limits.json and
    CHARTER.md when it starts; a truncate-then-write in place can be read
    half-written. The replacement is a same-directory temporary (so
    os.replace never crosses a filesystem), created 0600 and fsynced before
    it is moved into place. A failure leaves the destination untouched and
    removes the temporary.
    """
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    tmp = os.path.join(directory, f".{os.path.basename(path)}.tmp."
                       f"{os.getpid()}")
    fd = None
    for attempt in (0, 1):
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            if attempt:  # stale temp from a crashed run of this same pid slot
                raise
            try:
                os.unlink(tmp)
            except OSError:
                pass
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_if_changed(path, text, mode):
    changed = True
    if os.path.exists(path) and open(path).read() == text:
        changed = False
    else:
        atomic_write(path, text, mode)
    os.chmod(path, mode)
    return changed


# Entries of the server root a teammate never needs to read. `run` holds the
# pairing file, the server log and the paired browser profile; `home` is the
# T3 server's own state (sessions, secrets, settings).
SERVER_PRIVATE = ("run", "home", "config", "claude-home", "fabric.env")

# Files in a teammate's own home that are config or credentials, not memory.
# The teammate may not change them; the preimage it may not even read.
HOME_LOCKED = ("tool-limits.json", "CHARTER.md", "carrier.json",
               "cutover-preimage.json", "cutover-result.json")
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

# Server-root folders that choose which program the team server runs at its
# next start (bin/server_runner.sh is what launchd invokes; config names the
# server binary; runtime holds the pinned packed server; run holds the port
# and launcher state). Whoever can write them owns the next server start,
# and the installer cannot defend against that — the teammate limits must.
# Always denied for Write/Edit, in every spec, new keys or not.
SERVER_INFRASTRUCTURE = ("bin", "config", "runtime", "run")


def limits_paths(spec, mate):
    """(limits_path, charter_path) this teammate's launch args point at.

    Always the teammate home: an assets_dir outside the home was tried and
    REFUSED live (2026-11-11, RL dev server). A --settings file outside the
    home loads, but its Read/Glob/Grep deny rules silently do not bind —
    the teammate then reads everything the spec denies. load_spec refuses
    the assets_dir key for that reason.
    """
    home = teammate_home(spec, mate)
    return (os.path.join(home, "tool-limits.json"),
            os.path.join(home, "CHARTER.md"))


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


READ_TOOLS = ("Read", "Glob", "Grep")


def _read_allow_roots(spec, mate):
    """Absolute real paths reads are rooted to when allow_read_roots is set:
    the teammate's own home plus the spec's roots."""
    roots = [os.path.realpath(teammate_home(spec, mate))]
    roots += [os.path.realpath(expand(r))
              for r in spec.get("allow_read_roots") or []]
    seen, out = set(), []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def rooted_read_denies(spec, mate, tools=READ_TOOLS):
    """Deny rules that make reads (and, with Write/Edit passed as tools,
    writes) allowed ONLY under the rooted roots (Part B Q2/Q3).

    Allow rules cannot restrict in the real launch mode (proved live:
    full-access threads run bypassPermissions, an unmatched tool call is
    silently allowed, and a more-specific allow never beats a deny), so the
    rooting is compiled to deny rules by sibling enumeration: for every
    root chain (/a/b/c), every directory NOT on a chain gets a file and a
    tree deny. Chain directories get NO deny in any form: a deny rule on a
    directory matches the directory's whole subtree (live-proved: the
    refusal text is "File is in a directory that is denied"), so even a
    file-form deny on a chain directory would deny the allowed root below
    it — and deny wins. Residual gap: a Glob/Grep whose path is a chain
    directory runs and enumerates its names, revealing sibling names one
    level above an allowed root (names only, never content; the siblings
    themselves stay denied).
    """
    roots = _read_allow_roots(spec, mate)
    chain = set()
    for root in roots:
        node = root
        while node != "/":
            chain.add(node)
            node = os.path.dirname(node)
    # Sibling enumeration runs only after every chain is known: a directory
    # can sit on root 2's chain while being a mere sibling of root 1's chain
    # (e.g. two roots under the same temp dir), and it must not be denied.
    denied = set()
    for node in chain:
        parent = os.path.dirname(node)
        try:
            names = os.listdir(parent)
        except OSError:
            names = []
        for name in names:
            sib = os.path.join(parent, name)
            if sib not in chain and sib not in roots:
                denied.add(sib)
    rules = []
    for tool in tools:
        for path in sorted(denied):
            rules += [f"{tool}(/{path})", f"{tool}(/{path}/**)"]
    return rules


def _home_write_allow_names(spec):
    return list(spec.get("home_write_allow") or [])


def rooted_home_write_rules(spec, mate):
    """(allow, deny) rules replacing the home-wide write allow (Part B Q3).

    Only the named home-relative entries stay writable (a bare name is one
    file; a trailing slash is a subtree). Everything else in the home is
    denied: every existing child at apply time plus every HOME_CONFIG and
    HOME_LOCKED name whether or not it exists. A brand-new top-level name
    that is in neither list stays creatable but nothing loads it (the
    loading surface is HOME_CONFIG, all denied) — stated plainly in
    RL_TEAMMATE_LIMITS.md.
    """
    home = teammate_home(spec, mate)
    names = _home_write_allow_names(spec)
    allowed_files = {n for n in names if not n.endswith("/")}
    allowed_dirs = {n.rstrip("/") for n in names if n.endswith("/")}
    allow = []
    for name in names:
        target = os.path.join(home, name.rstrip("/"))
        if name.endswith("/"):
            allow += [f"Write(/{target})", f"Write(/{target}/**)",
                      f"Edit(/{target})", f"Edit(/{target}/**)"]
        else:
            allow += [f"Write(/{target})", f"Edit(/{target})"]
    deny = []
    for tool in ("Write", "Edit"):
        for name in sorted(set(HOME_LOCKED + HOME_CONFIG)):
            if name in allowed_files or name in allowed_dirs:
                continue  # never granted: locked/config names are not
                # writable even if a spec mistakenly lists them
            target = os.path.join(home, name)
            deny += [f"{tool}(/{target})", f"{tool}(/{target}/**)"]
        try:
            children = os.listdir(home)
        except OSError:
            children = []
        for name in sorted(children):
            if name in allowed_files or name in allowed_dirs:
                continue
            target = os.path.join(home, name)
            deny += [f"{tool}(/{target})", f"{tool}(/{target}/**)"]
    return allow, deny


def tool_limits(spec, mate):
    home = teammate_home(spec, mate)
    deny_roots = [expand(spec["project"]["workspace_root"])]
    deny_roots += [os.path.abspath(r) for r in spec.get("deny_write_roots", [])]
    deny = ["Bash", "Agent", "NotebookEdit"]
    for root in deny_roots:
        # root itself too: if the folder does not exist (yet), a Write could
        # otherwise create a file at that exact path (server-infrastructure
        # review, 2026-11-11)
        deny += [f"Write(/{root})", f"Write(/{root}/**)",
                 f"Edit(/{root})", f"Edit(/{root}/**)"]
    for name in HOME_LOCKED:
        locked = os.path.join(home, name)
        deny += [f"Write(/{locked})", f"Edit(/{locked})"]
    for name in HOME_CONFIG:
        config = os.path.join(home, name)
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{config})", f"{tool}(/{config}/**)"]
    root = expand(spec["server"]["root"])
    for name in SERVER_INFRASTRUCTURE:
        infra = os.path.join(root, name)
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{infra})", f"{tool}(/{infra}/**)"]
    for path in deny_read_paths(spec, mate):
        deny += _read_deny(path)
    read_rooted = bool(spec.get("allow_read_roots"))
    write_named = bool(spec.get("home_write_allow"))
    if read_rooted:
        deny += rooted_read_denies(spec, mate, READ_TOOLS)
    if write_named:
        deny += rooted_read_denies(spec, mate, ("Write", "Edit"))
    allow = [
        "Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
        f"Write(/{home}/**)", f"Edit(/{home}/**)",
    ]
    if read_rooted:
        allow = [a for a in allow if a not in READ_TOOLS]
        for r in _read_allow_roots(spec, mate):
            allow += [f"Read(/{r}/**)", f"Glob(/{r}/**)", f"Grep(/{r}/**)"]
    if write_named:
        allow = [a for a in allow
                 if a not in (f"Write(/{home}/**)", f"Edit(/{home}/**)")]
        extra_allow, extra_deny = rooted_home_write_rules(spec, mate)
        allow += extra_allow
        deny += extra_deny
    seen = set()
    deny = [d for d in deny if not (d in seen or seen.add(d))]
    note = ("allow/deny enumerations in Claude Code permission syntax. "
            "Proved live on the dev server: deny wins over allow at any "
            "specificity; a bare tool deny removes the tool; and in the "
            "real launch mode (full-access -> bypassPermissions) allow "
            "lists do not restrict — a tool call matching neither allow "
            "nor deny is silently allowed, so every restriction here is a "
            "deny. Limits bind at session-process start, not on file "
            "change (apply reports limitsPendingRestart).")
    if read_rooted or write_named:
        note += (" allow_read_roots/home_write_allow compiled to deny "
                 "rules by sibling enumeration (rooted_read_denies).")
    return {
        "permissions": {"allow": allow, "deny": deny},
        "_note": note,
    }


def write_file_assets(spec, mate):
    """Home dir, CLAUDE.md seed, CHARTER.md, tool-limits.json.

    CLAUDE.md is the teammate's live long-term memory: created only when
    missing, never rewritten by apply (a rewrite would erase remembered
    facts). CHARTER.md and tool-limits.json are config and follow the spec;
    with spec.assets_dir set they live outside the home (Q4) in a
    0700 dir of their own.
    """
    home = teammate_home(spec, mate)
    os.makedirs(home, exist_ok=True)
    os.chmod(home, 0o700)
    limits_path, charter_path = limits_paths(spec, mate)
    seed = ("<!-- Long-term memory of {name}. Append durable facts below; "
            "they persist across conversations and server restarts. -->\n"
            "# {name} — memory\n\n").format(name=mate["name"])
    wrote = []
    memory = os.path.join(home, "CLAUDE.md")
    if not os.path.exists(memory):
        write_if_changed(memory, seed, 0o600)
        wrote.append("CLAUDE.md")
    if write_if_changed(charter_path, mate["charter"], 0o600):
        wrote.append("CHARTER.md")
    if write_if_changed(limits_path,
                        json.dumps(tool_limits(spec, mate), indent=2) + "\n",
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
    limits_path, charter_path = limits_paths(spec, mate)
    launch_args = [
        "--append-system-prompt-file", charter_path,
        "--settings", limits_path,
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
        atomic_write(settings_path(spec), json.dumps(settings, indent=2), 0o600)
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
    atomic_write(path, json.dumps(state, indent=2), 0o600)


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


def paperclip_binding(spec, mate, opener=None):
    """The thread id Paperclip binds this teammate's agent to, or None.

    Review R2a finding 12, roster side. The wake carrier sends each task to
    ``metadata.teammate.t3.primaryThreadId`` on the agent record, while this
    tool tracked threads only in its own state file; if the state file is
    lost, apply could create a second primary thread under a still-bound
    agent. When the spec names a binding source (``paperclip_base`` plus the
    teammate's ``paperclip_agent_id``), this does exactly one GET of the
    agent record; without a source nothing is read and behaviour is
    unchanged. Errors refuse rather than guess: an unreadable binding cannot
    be verified.
    """
    base = spec.get("paperclip_base")
    agent_id = mate.get("paperclip_agent_id")
    if not base or not agent_id:
        return None
    url = f"{base.rstrip('/')}/api/agents/{agent_id}"
    op = opener or urllib.request.build_opener()
    try:
        with op.open(urllib.request.Request(url, method="GET"),
                     timeout=30) as resp:
            payload = json.loads(resp.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        die(f"{mate['name']}: cannot read the Paperclip record of agent "
            f"{agent_id} ({exc}); refusing to create or adopt a thread")
    meta = ((payload.get("metadata") or {}).get("teammate") or {})
    return (meta.get("t3") or {}).get("primaryThreadId")


def ensure_threads(spec, project_id):
    state, state_path = load_state(spec)
    live = list_threads(spec, project_id)
    recorded_by_name = {name: (entry or {}).get("threadId")
                        for name, entry in state["teammates"].items()}
    # One GET per configured agent, before any thread is created (R2a 12).
    bindings = {mate["name"]: paperclip_binding(spec, mate)
                for mate in spec["teammates"]}
    threads = {}
    to_create = []
    for mate in spec["teammates"]:
        title = teammate_title(mate)
        recorded = recorded_by_name.get(mate["name"])
        found, problem = _recover_thread(mate, live, recorded_by_name)
        if problem:
            die(f"{mate['name']}: {problem}; refusing to pick or create a "
                f"primary thread")
        bound = bindings[mate["name"]]
        if bound is not None:
            if found is None:
                die(f"{mate['name']}: Paperclip binds its agent to thread "
                    f"{bound}, which this roster does not know; refusing to "
                    f"create a second primary thread. If {bound} is the real "
                    f"primary, record it in {state_path} (or unbind the agent "
                    f"in Paperclip) and apply again")
            if found["threadId"] != bound:
                die(f"{mate['name']}: Paperclip binds its agent to thread "
                    f"{bound}, but the roster resolved {found['threadId']}; "
                    f"refusing. Reconcile the Paperclip binding and the "
                    f"roster to one thread and apply again")
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
        to_create.append(mate)
    # Every check has passed for every teammate; only now is a thread created,
    # so one teammate's refusal leaves the whole roster untouched.
    for mate in to_create:
        title = teammate_title(mate)
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
    atomic_write(path, json.dumps(out, indent=2), 0o600)
    return path


def session_processes(*paths):
    """Session processes of the teammate identified by ``paths`` (its home,
    its limits/charter paths, and its project workspace root — the spawn
    argv carries the workspace cwd, while the home is an env var and the
    launch-arg flags are consumed by the server, so the workspace marker is
    the one that reliably matches live processes; proved live on the RL dev
    server, 2026-11-11).

    A teammate session is one long-lived process the server starts per
    thread; it reads tool-limits.json and CHARTER.md only when it starts, so
    a limits change binds on the next process start, never mid-session.
    Detection matches any given path in the process list and returns pid and
    start time only — a command line can carry values that are not ours to
    show, so it is read for the match and never returned or printed.
    """
    paths = [os.path.abspath(p) for p in paths if p]
    try:
        proc = subprocess.run(["ps", "-axo", "pid,lstart,command"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    out = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.strip().split(None, 6)
        if len(parts) < 7 or not any(p in parts[6] for p in paths):
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        out.append({"pid": pid, "started": " ".join(parts[1:6])})
    return out


def cmd_apply(spec):
    project_id = ensure_project(spec)
    pending = {}
    for mate in spec["teammates"]:
        wrote = write_file_assets(spec, mate)
        home = teammate_home(spec, mate)
        log(f"{mate['name']}: home {home} "
            + (f"(wrote {', '.join(wrote)})" if wrote else "(unchanged)"))
        # tool-limits.json and CHARTER.md are read when the session process
        # starts, so a running session keeps the old limits until it restarts
        pending[mate["name"]] = [name for name in
                                 ("tool-limits.json", "CHARTER.md")
                                 if name in wrote]
    ensure_instances(spec)
    threads, _ = ensure_threads(spec, project_id)
    renames, rename_failures = rename_threads(spec, threads)
    urls_path = write_urls_file(spec, threads)
    log(f"thread URLs written: {urls_path} (0600, no credentials)")
    workspace = expand(spec["project"]["workspace_root"])
    workspace_sessions = session_processes(workspace)
    for mate in spec["teammates"]:
        changed = pending[mate["name"]]
        if not changed:
            continue
        # Precise markers first (home, limits/charter paths); the spawn argv
        # carries only the workspace cwd (live-proved), so a workspace-only
        # match cannot be attributed to one teammate — report it as such
        # instead of claiming no session is running.
        sessions = session_processes(teammate_home(spec, mate),
                                     *limits_paths(spec, mate))
        if sessions:
            live = "; ".join(f"pid {s['pid']} started {s['started']}"
                             for s in sessions)
            log(f"{mate['name']}: new limits ({', '.join(changed)}) are "
                f"NOT IN FORCE until that teammate's session process "
                f"restarts; running now: {live}")
        elif workspace_sessions:
            log(f"{mate['name']}: new limits ({', '.join(changed)}) are NOT "
                f"IN FORCE until that teammate's session process restarts; "
                f"{len(workspace_sessions)} session process(es) are running "
                f"in the team workspace but cannot be attributed to this "
                f"teammate by process listing — assume a restart is needed")
        else:
            log(f"{mate['name']}: new limits ({', '.join(changed)}) are "
                f"NOT IN FORCE until that teammate's session process starts; "
                f"none is running now")
    report = {
        "projectId": project_id,
        "teammates": [
            {"name": mate["name"], "instance": mate["instance"],
             "home": teammate_home(spec, mate),
             "threadId": threads[mate["name"]]["threadId"],
             "threadTitle": threads[mate["name"]]["title"],
             "threadCreated": threads[mate["name"]]["created"],
             "renamed": renames[mate["name"]],
             "limitsPendingRestart": pending[mate["name"]]}
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
