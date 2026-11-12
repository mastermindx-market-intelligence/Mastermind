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
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# The gate module sits beside this file; make it importable however THIS
# module is loaded (script run, pytest importlib load).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teammate_gate as _gate  # noqa: E402 (path bootstrap above)

RESERVED_PORTS = (3773, 3774)  # the Chairman's own T3 Code app

SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")

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
    for key in ("allow_read_roots", "deny_read_roots", "deny_write_roots",
                "home_write_allow"):
        # repair round 1, P10: a string where a list is expected would be
        # iterated character-by-character, silently granting one-character
        # roots (proved by the panel: "allow_read_roots": "~/x" grants
        # Read($HOME/**))
        value = spec.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            die(f"spec key '{key}' must be a list of paths, got "
                f"{type(value).__name__}")
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                die(f"spec key '{key}' has a non-string entry {entry!r}")
    for name in spec.get("home_write_allow") or []:
        # attack round, finding 10: a locked/config name here would emit an
        # allow for it (only the unconditional deny loop keeps it bound
        # today — do not rely on that coincidence), and an absolute or
        # traversal name joins into an allow string outside the home.
        # repair round 1, P11: compare the rstrip'd name — "settings.json/"
        # passed the raw compare and emitted a grant for a locked name
        base = name[:-1] if name.endswith("/") else name
        if base in HOME_CONFIG or base in HOME_LOCKED:
            die(f"home_write_allow entry {name!r} is a config or locked "
                "name and can never be granted")
        if (not base or name.startswith("/")
                or name.startswith("~") or base != os.path.normpath(base)
                or ".." in base.split(os.sep)):
            die(f"home_write_allow entry {name!r} must be a relative "
                "home-directory name like 'CLAUDE.md' or 'notes/'")
    for entry in spec.get("deny_write_roots") or []:
        # repair round 1, P12: this list used to be the one root list never
        # expand()ed, so a "~" spelling silently emitted a junk rule
        expanded = expand(entry)
        if not os.path.isabs(expanded):
            die(f"deny_write_roots entry {entry!r} does not expand to an "
                f"absolute path ({expanded})")
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
    # repair round 1, P9: the home guard was missing — a spec home at/inside
    # ~/.t3 would merge roster instances straight into the Chairman's real
    # T3 settings.json
    home_real = os.path.realpath(expand(server["home"]))
    if home_real == dot_t3 or home_real.startswith(dot_t3 + os.sep):
        die(f"server home {home_real} is at or inside ~/.t3; refusing")
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
        # repair round 1, P8: the slug becomes a directory name under the
        # server root and part of the launch args — an absolute, traversal,
        # trailing-slash or space-carrying slug re-roots the fence or breaks
        # the launch so no limits load while apply reports success
        if not isinstance(mate["slug"], str) or not SLUG_RE.fullmatch(
                mate["slug"]):
            die(f"{where}.slug must match ^[A-Za-z0-9_-]+$, got "
                f"{mate['slug']!r}")
        if mate["slug"] in slugs:
            die(f"duplicate slug {mate['slug']!r}")
        link = mate.get("memory_link")
        if link is not None:
            # Lane HM: the memory link is one MCP server, wired by a config
            # file under <server root>/config/ (server-private: no teammate
            # can read or rewrite what it launches) and gated by exact tool
            # names in the memory-link namespace only.
            if not isinstance(link, dict) or set(link) != {"mcp_config",
                                                           "tools"}:
                die(f"{where}.memory_link must be an object with exactly "
                    "'mcp_config' and 'tools'")
            tools = link["tools"]
            if (not isinstance(tools, list) or not tools or any(
                    not isinstance(t, str) or not re.fullmatch(
                        r"mcp__memory-link__[a-z_]{1,40}", t)
                    for t in tools)):
                die(f"{where}.memory_link.tools must list exact "
                    "mcp__memory-link__<tool> names")
            cfg_dir = os.path.join(os.path.realpath(expand(server["root"])),
                                   "config", "memory-link")
            target = os.path.realpath(expand(str(link["mcp_config"])))
            if os.path.dirname(target) != cfg_dir or " " in target:
                die(f"{where}.memory_link.mcp_config must be a file directly "
                    f"in {cfg_dir} (no spaces)")
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


# Lane HM finding at server pin 0770446: the server applies a settings.json
# write about a second later (fs.watch, 100 ms debounce, then a provider
# registry rebuild), so a thread start sent in that window is refused as
# "Provider instance ... is disabled for project". No restart is needed: the
# same start succeeds once the reload has landed. Only that refusal is
# retried, a bounded number of times.
SETTINGS_LAG_MARKER = "is disabled for project"
SETTINGS_LAG_ATTEMPTS = 5
SETTINGS_LAG_WAIT_S = 2.0


def start_thread_after_settings(spec, args, what):
    for attempt in range(1, SETTINGS_LAG_ATTEMPTS + 1):
        proc = t3(spec, args)
        text = (proc.stderr or "") + (proc.stdout or "")
        if (proc.returncode != 0 and SETTINGS_LAG_MARKER in text
                and attempt < SETTINGS_LAG_ATTEMPTS):
            log(f"{what}: server has not applied the new settings yet; "
                f"retrying in {SETTINGS_LAG_WAIT_S:g} s "
                f"({attempt}/{SETTINGS_LAG_ATTEMPTS})")
            time.sleep(SETTINGS_LAG_WAIT_S)
            continue
        return t3_json(proc, what)
    return None  # unreachable


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


def atomic_write(path, text, mode, staging_dir=None):
    """Replace ``path`` with ``text`` atomically (review R2a, finding 11).

    The running server watches settings.json and reloads it about 100 ms
    after a change, and a teammate process reads tool-limits.json and
    CHARTER.md when it starts; a truncate-then-write in place can be read
    half-written. The replacement is a temporary created 0600 and fsynced
    before it is moved into place. A failure leaves the destination
    untouched and removes the temporary.

    ``staging_dir``: stage the temporary here instead of next to the
    destination (attack round, finding 5). Next to the destination the
    temp's name matches no deny rule, so a teammate whose Write tool can
    touch the destination directory could poll for the temp name and
    overwrite it between os.open and os.replace, publishing its own bytes
    as the file. Staging under ``<server root>/run`` (Write-denied for
    every teammate) closes the race; os.replace across directories on the
    same volume is still atomic.
    """
    path = os.path.abspath(path)
    directory = staging_dir if staging_dir else os.path.dirname(path)
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


def write_if_changed(path, text, mode, staging_dir=None):
    if os.path.islink(path):
        die(f"refusing to write through symlink {path} — a planted link "
            "would send the bytes (and the chmod) outside the fence")
    changed = True
    if os.path.exists(path) and open(path).read() == text:
        changed = False
    else:
        atomic_write(path, text, mode, staging_dir=staging_dir)
    if not os.path.islink(path):
        os.chmod(path, mode)
    return changed


# Entries of the server root a teammate never needs to read. `run` holds the
# pairing file, the server log and the paired browser profile; `home` is the
# T3 server's own state (sessions, secrets, settings); `bin` and `runtime`
# are the runner script and the pinned server bundle (attack round,
# finding 12).
SERVER_PRIVATE = ("run", "home", "config", "bin", "runtime", "claude-home",
                  "fabric.env")

# Files in a teammate's own home that are config or credentials, not memory.
# The teammate may not change them; the preimage it may not even read.
#
# H-2 (panel 3): all three home-name classes below are DERIVED from the
# gate's one canonical list (teammate_gate.CLAUDE_CONFIG_NAMES and friends)
# so the write fence and the read fence cannot drift apart again — the
# panel found the read fence naming 10 first components while this file
# classed 29 as configuration. The rule layer derives from these tuples;
# the gate derives from the same sets directly.
HOME_LOCKED = tuple(sorted(frozenset({"CHARTER.md"}) |
                           _gate.RUNTIME_PRIVATE_NAMES |
                           # RF-MEMLINK (b): the history archive is read-only
                           # for the teammate (ruling 22 accepts a residual
                           # reader, never a writer), so the rule layer must
                           # carry its deny — a write fence is never held by
                           # the PreToolUse hook alone.
                           _gate.READ_ONLY_NAMES |
                           _gate.RESTART_BACKUP_NAMES))
# What a teammate may not even READ in its own home: the whole Claude
# configuration class plus this deployment's private runtime files (the
# .claude/ subtree is covered by its first component; the gate's
# unreadable_name keeps the .claude.json* / settings*.json families).
HOME_UNREADABLE = tuple(sorted(_gate.UNREADABLE_NAMES))

# A teammate's home is also its Claude configuration folder. A settings file
# or an MCP entry there can name a command to run, and a skill, agent, rule
# or plugin there is loaded as instructions, so a teammate that may create
# files in its home could give itself a shell (found by the principal with
# MAS-15: creating a new file in the home is allowed). The runtime writes
# these itself without the Write tool; the teammate's tools may not.
HOME_CONFIG = tuple(sorted(_gate.CLAUDE_CONFIG_NAMES))

# Server-root folders that choose which program the team server runs at its
# next start (bin/server_runner.sh is what launchd invokes; config names the
# server binary; runtime holds the pinned packed server; run holds the port
# and launcher state; home and claude-home hold the server's own live-reloaded
# settings; fabric.env its launch environment). Whoever can write them owns
# the next server start, and the installer cannot defend against that — the
# teammate limits must. Always denied for Write/Edit, in every spec, new
# keys or not. Kept named through the rule-layer cut (panel 2 Volume).
SERVER_INFRASTRUCTURE = ("bin", "config", "runtime", "run", "home",
                         "claude-home", "fabric.env")

# User-level autoload, credential, config and personal folders a teammate
# never needs, denied for Read/Glob/Grep AND Write/Edit whether or not the
# name exists (repair round 1, P3/P5: the write fence only enumerated
# existing siblings, so an absent ~/.zshenv was creatable, and the
# production spec's curated read list omitted ~/Library/Containers,
# ~/.claude.json, ~/.git-credentials, shell histories, Documents, Desktop
# and Downloads). Entries are user-home-relative; a trailing * is a prefix
# family (the TSHc window-dev* folders).
USER_PROTECTED = (
    # shells load these at every interactive start: writing one is code
    # execution as the user (P3)
    ".zshenv", ".zprofile", ".zshrc", ".zlogin", ".zsh_history",
    ".bash_profile", ".bashrc", ".bash_history", ".profile", ".inputrc",
    ".wgetrc", ".curlrc",
    # credentials and tool config
    ".ssh", ".gnupg", ".aws", ".kube", ".docker", ".config", ".claude",
    ".codex", ".claude.json", ".gitconfig", ".git-credentials", ".netrc",
    ".npmrc", ".t3", ".hermes", ".paperclip",
    # the user's personal folders (P5)
    "Documents", "Desktop", "Downloads",
    # per-user state that carries tokens and secrets
    "Library/Keychains", "Library/Cookies", "Library/Application Support",
    "Library/Containers", "Library/Group Containers", "Library/Preferences",
    "Library/HTTPStorages", "Library/Caches", "Library/Mail", "Library/Logs",
    # a launchd agent planted here runs as the user at next login (TSHc)
    "Library/LaunchAgents",
    # other lane/window surfaces (TSHc panel): window state and every dev
    # team server except this spec's own root
    ".mastermind/window", ".mastermind/mmos_dev/window-dev*",
    ".mastermind/mmos_dev", ".mastermind/t3-team-server",
)

# Bare tool denies for every tool a teammate session is offered that is
# not on its allowlist (repair round 2, M4: the deny layer enumerated only
# a handful, so Task/LS/NotebookRead/SlashCommand/BashOutput/KillShell and
# the MCP tools were offered and unfenced at the rule layer). The census
# list is what a live dev-server teammate session actually offered on
# 2026-11-11 (17 tools incl. Read/Glob/Grep/Write/Edit/WebFetch/ToolSearch
# and two MCP names); the belt adds client tools other builds/configs of
# the same client offer. MCP names are EXACT names: live-proved (N4, dev
# server, transcript-verified forced calls) that no wildcard form binds —
# neither mcp__*, mcp__server__*, nor the bare local name. mcp__
# web_reader__webReader stays denied here even though its execution is
# server-side (see RL_TEAMMATE_LIMITS.md residual: it must also be removed
# from the server build). ToolSearch is deliberately NOT denied: loading a
# tool changes nothing — the gate refuses fetch-capable tools BY NAME at
# call time (decision 2026-11-11, no web access; FETCH_FORBIDDEN_TOOLS).
# The fetch names are DERIVED from the gate's one canonical list so the
# two layers cannot drift (same single-source rule as the unreadable set).
TOOL_DENY_CENSUS = (
    # census: client tools a teammate session is actually offered
    "Agent", "AskUserQuestion", "ListAgents", "ReportFindings",
    "ScheduleWakeup", "Skill", "Workflow",
    # belt: same client, other configurations
    "Bash", "Task", "LS", "NotebookEdit", "NotebookRead", "SlashCommand",
    "BashOutput", "KillShell", "EnterPlanMode", "ExitPlanMode", "Monitor",
    "ReadMcpResource", "ListMcpResources", "MultiEdit", "SendMessage",
    "CronCreate", "CronDelete", "CronList",
    # MCP tools offered to a teammate session, by exact name
    "mcp__t3-code__request_secret", "mcp__web_reader__webReader",
) + tuple(sorted(_gate.FETCH_FORBIDDEN_TOOLS))

# The primary fence (repair round 1 design ruling): one PreToolUse hook
# program, stored where no teammate can write, wired into every teammate's
# tool-limits.json. Live-proved on the RL dev server (evidence 12): hooks in
# the --settings file fire inside teammate turns, exit 2 blocks with the
# reason shown to the model, and a missing or crashing hook lets the call
# THROUGH (fail-open) — which is why the gate itself fails closed on every
# internal error and apply/status verify its presence and sha256.
GATE_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "teammate_gate.py")
GATE_INSTALL_NAME = "teammate_gate.py"

# M-R2 (panel 3): the hook interpreter is ONE absolute, validated binary.
# `/usr/bin/env python3` resolved the interpreter through the hook runtime's
# PATH, so any python3 earlier on that PATH would run INSTEAD of the gate —
# different code deciding every tool call, a full fence bypass. The pinned
# binary is verified at apply time (ensure_gate) and by `status`.
GATE_INTERPRETER = "/usr/bin/python3"


def gate_install_path(spec):
    return os.path.join(os.path.realpath(expand(spec["server"]["root"])),
                        "bin", GATE_INSTALL_NAME)


def gate_config_path(spec, mate):
    return os.path.join(os.path.realpath(expand(spec["server"]["root"])),
                        "config", "teammate-gate",
                        f"{mate['slug']}.json")


def _shell_single_quote(text):
    """Always single-quote (repair round 2, R4): shlex.quote leaves a plain
    path bare, and the wired command must stay one parseable command for
    every server root, including roots with spaces."""
    return "'" + text.replace("'", "'\\''") + "'"


def gate_command(spec, mate):
    # R4 (M2 + N1) + M-R2 (panel 3): the PINNED absolute interpreter — no
    # PATH lookup, so nothing earlier on the hook runtime's PATH can run
    # instead of the gate — with -I isolation from PYTHON* env and the
    # user site dir; every non-2 exit of the gate itself (1 on internal
    # error, 126 not executable, 127 missing, timeout kill) becomes a
    # refusal through `|| exit 2` — the hook layer fails CLOSED.
    return (f"{GATE_INTERPRETER} -I "
            f"{_shell_single_quote(gate_install_path(spec))} --config "
            f"{_shell_single_quote(gate_config_path(spec, mate))} || exit 2")


def gate_hook_block(spec, mate):
    return {"PreToolUse": [
        {"matcher": "*",
         "hooks": [{"type": "command", "command": gate_command(spec, mate),
                    "timeout": 20}]}]}


def _user_protected_paths(spec):
    """Absolute USER_PROTECTED paths, minus any entry that is an ancestor
    of (or equal to) a path this spec must keep reachable — the teammate
    homes, the read roots and workspace, the server root and the server
    home. A directory deny matches its whole subtree (live-proved), so an
    unfiltered entry would fence the spec's own tree: the dev spec lives
    under ~/.mastermind/mmos_dev, which is exactly such an entry."""
    base = os.path.realpath(expand("~"))
    keep = set()
    for mate in spec.get("teammates", []):
        keep.add(os.path.realpath(teammate_home(spec, mate)))
    keep.add(os.path.realpath(expand(spec["project"]["workspace_root"])))
    keep.add(os.path.realpath(expand(spec["server"]["root"])))
    keep.add(os.path.realpath(expand(spec["server"]["home"])))
    keep.update(os.path.realpath(expand(r))
                for r in spec.get("allow_read_roots") or [])
    # existing teammate homes too (dropped or not-yet-in-spec slugs): they
    # are fenced as other-homes, not denied as subtrees of their own
    # parent chain
    root = os.path.realpath(expand(spec["server"]["root"]))
    teammates_dir = os.path.join(root, "teammates")
    if os.path.isdir(teammates_dir):
        try:
            for name in os.listdir(teammates_dir):
                keep.add(os.path.realpath(os.path.join(teammates_dir, name)))
        except OSError:
            pass
    out = []
    for name in USER_PROTECTED:
        entry = os.path.join(base, name.rstrip("*").rstrip("/"))
        blocked = any(p == entry or p.startswith(entry + os.sep)
                      for p in keep)
        if not blocked:
            out.append(os.path.join(base, name))
    return out


def other_home_paths(spec, mate):
    """Every OTHER teammate home this teammate must not touch: all spec
    slugs (repair round 1, P1 — a home added by this very apply must be
    fenced in the same run even before its directory exists) plus every
    directory under <root>/teammates that exists on disk (P6 — a dropped
    teammate's home stays fenced)."""
    root = os.path.realpath(expand(spec["server"]["root"]))
    own = os.path.realpath(teammate_home(spec, mate))
    paths = set()
    for other in spec["teammates"]:
        if other["slug"] != mate["slug"]:
            paths.add(os.path.realpath(teammate_home(spec, other)))
    teammates_dir = os.path.join(root, "teammates")
    if os.path.isdir(teammates_dir):
        try:
            for name in os.listdir(teammates_dir):
                candidate = os.path.realpath(os.path.join(teammates_dir,
                                                          name))
                if candidate != own:
                    paths.add(candidate)
        except OSError as exc:
            if os.path.exists(teammates_dir):
                die(f"cannot enumerate {teammates_dir} for the limits "
                    f"fence ({exc}); refusing to emit a fence with holes")
    return sorted(paths)


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


def gate_config(spec, mate):
    """The per-teammate config the gate program reads at every tool call.

    Read policy is ALWAYS rooted (home + the team workspace + the spec's
    allow_read_roots) — this is the P5 fix at the primary-fence level: the
    production spec has no allow_read_roots, and its curated deny list
    alone left Documents, Library/Containers, ~/.claude.json and friends
    readable; the gate roots reads even when the rule layer stays in
    deny-list mode. deny_reads are checked after resolution and carry only
    entries that can still matter inside the roots (spec deny_read_roots
    under a root; the firmlink/case spelling work happens inside the gate).
    write_names mirrors home_write_allow (None = default home-wide write
    minus protected names).
    """
    # M-R1 (panel 3): every config path passes the gate's canonical()
    # (firmlink alias + true case) — a spec spelled in the
    # /System/Volumes/Data form emits the same canonical config as the
    # primary spelling, and the dedupe below is normalization-aware because
    # both spellings of one root canonicalize to one string
    home = _gate.canonical(teammate_home(spec, mate))
    workspace = _gate.canonical(expand(spec["project"]["workspace_root"]))
    read_roots = [workspace]
    for r in spec.get("allow_read_roots") or []:
        candidate = _gate.canonical(expand(r))
        if candidate not in read_roots and candidate != home:
            read_roots.append(candidate)
    def under(path, root):
        return path == root or path.startswith(root.rstrip("/") + "/")
    deny_reads = []
    for r in spec.get("deny_read_roots") or []:
        candidate = _gate.canonical(expand(r))
        if under(candidate, home) or any(under(candidate, root)
                                         for root in read_roots):
            deny_reads.append(candidate)
    write_names = spec.get("home_write_allow")
    if write_names is not None and not write_names:
        write_names = []
    out = {
        "home": home,
        "read_roots": read_roots,
        "deny_reads": deny_reads,
        "write_names": write_names,
    }
    if mate.get("memory_link"):
        out["allow_mcp_tools"] = list(mate["memory_link"]["tools"])
    return out


def gate_sha256():
    with open(GATE_SOURCE, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def ensure_gate(spec):
    """Install the gate program under <server root>/bin (write-denied for
    every teammate; the gate itself refuses writes outside the home, so it
    protects its own binary). Dies loudly when the source is missing — a
    missing hook lets every tool call through (live-proved fail-open)."""
    if not os.path.isfile(GATE_SOURCE):
        die(f"gate program missing from the installation: {GATE_SOURCE}; "
            "refusing to apply limits whose primary fence cannot exist")
    # M-R2 (panel 3): never wire a hook whose pinned interpreter cannot
    # run — the fence would fail closed on EVERY call (or, wired with a
    # PATH lookup, run whatever python3 comes first)
    if not (os.path.isfile(GATE_INTERPRETER) and
            os.access(GATE_INTERPRETER, os.X_OK)):
        die(f"the pinned hook interpreter {GATE_INTERPRETER} is missing or "
            "not executable; refusing to wire a hook that cannot run")
    root = os.path.realpath(expand(spec["server"]["root"]))
    staging = os.path.join(root, "run")
    os.makedirs(staging, exist_ok=True)
    os.makedirs(os.path.join(root, "bin"), exist_ok=True)
    with open(GATE_SOURCE) as fh:
        text = fh.read()
    expected = gate_sha256()
    target = gate_install_path(spec)
    write_if_changed(target, text, 0o555, staging_dir=staging)
    actual = hashlib.sha256(open(target, "rb").read()).hexdigest()
    if actual != expected:
        die(f"gate at {target} does not match the installation (sha256 "
            f"{actual} != {expected}); refusing")
    os.chmod(target, 0o555)  # not writable even by the owning user
    return expected


def _read_deny(path):
    """Deny rules for one path, for every read tool (repair round 1, P4:
    these used to compile to Read rules only, leaving ~/.ssh, <root>/run
    and other homes open to Grep for content and Glob for names). Always
    the file+tree pair: a directory deny matches its whole subtree, and an
    exact-path rule alone is not trusted to bind for any tool (the
    Write/Edit exact form proved inert live — evidence 10 D3)."""
    rules = []
    for tool in READ_TOOLS:
        rules += [f"{tool}(/{path})", f"{tool}(/{path}/**)"]
    return rules


def firmlink_aliases(path):
    """macOS firmlink spelling variants of a /Users path (attack round,
    finding 7). /Users is a firmlink onto the data volume, so
    /System/Volumes/Data/Users/<user>/... names the SAME file while
    matching no /Users-prefixed deny string — and os.path.realpath does
    not canonicalize it (checked live 2026-11-11: realpath keeps the
    Data spelling). The sibling enumeration denies /System itself, which
    covers Data spellings of enumerated paths; these twins cover
    spec-named roots that live under /Users."""
    if path == "/Users" or path.startswith("/Users/"):
        return ["/System/Volumes/Data" + path]
    return []


def deny_read_paths(spec, mate):
    """What a teammate must not read (review R2a, finding 1).

    A teammate runs as the same user as everything else on this Mac, so file
    modes do not protect a credential from it. Text in an issue can ask it to
    read a file and quote it back, and the carrier posts its reply. Deny
    rules win over the plain `Read` allow.
    """
    root = os.path.realpath(expand(spec["server"]["root"]))
    paths = [os.path.join(root, name) for name in SERVER_PRIVATE]
    # every other teammate home: spec slugs AND directories that exist
    # (P1: a home added by this apply; P6: a dropped teammate's home)
    paths += other_home_paths(spec, mate)
    home = teammate_home(spec, mate)
    paths += [os.path.join(home, name) for name in HOME_UNREADABLE]
    paths += [os.path.realpath(expand(r))
              for r in spec.get("deny_read_roots", [])]
    # always-on user-level protected folders (P5): the production spec has
    # no read rooting, so its only read fence is this curated list — it
    # must cover the credential and personal folders whether or not a
    # later spec remembers to name them
    paths += _user_protected_paths(spec)
    # NOTE (rule-layer cut, repair round 2): the deny_read_root_siblings
    # listing was removed with the sibling enumerations — the gate refuses
    # every read outside the roots at call time; the spec key is inert.
    seen, out = set(), []
    for path in paths:
        for candidate in [path] + firmlink_aliases(path):
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
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
        except OSError as exc:
            # repair round 1, P15: fail CLOSED, like the sibling enumeration
            # — an unlistable existing home silently published a weakened
            # write fence
            if os.path.exists(home):
                die(f"cannot enumerate the teammate home {home} for the "
                    f"write rules ({exc}); refusing to emit a fence with "
                    f"holes")
            children = []
        for name in sorted(children):
            if name in allowed_files or name in allowed_dirs:
                continue
            target = os.path.join(home, name)
            deny += [f"{tool}(/{target})", f"{tool}(/{target}/**)"]
    return allow, deny


def tool_limits(spec, mate):
    home = os.path.realpath(teammate_home(spec, mate))
    deny_roots = [os.path.realpath(expand(spec["project"]["workspace_root"]))]
    deny_roots += [os.path.realpath(expand(r))
                   for r in spec.get("deny_write_roots", [])]
    # symlink spellings must not dodge a deny: the matcher resolves links,
    # so every deny string is built from the real path (attack round,
    # finding 8); /Users paths also get their firmlink twin (finding 7)
    deny_roots += [a for r in deny_roots for a in firmlink_aliases(r)]
    deny = list(TOOL_DENY_CENSUS)
    for root in deny_roots:
        # root itself too: if the folder does not exist (yet), a Write could
        # otherwise create a file at that exact path (server-infrastructure
        # review, 2026-11-11)
        deny += [f"Write(/{root})", f"Write(/{root}/**)",
                 f"Edit(/{root})", f"Edit(/{root}/**)"]
    for name in HOME_LOCKED:
        # file+tree pairs: an exact-path Write deny alone does not bind
        # (live-proved 2026-11-11, evidence 10 D3), and these are the
        # teammate's own limits/charter — the one overwrite that matters,
        # because it binds at the next process start
        locked = os.path.join(home, name)
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{locked})", f"{tool}(/{locked}/**)"]
    for name in HOME_CONFIG:
        config = os.path.join(home, name)
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{config})", f"{tool}(/{config}/**)"]
    # other teammates' homes, Write/Edit too (P1/P6: spec slugs and dropped
    # homes, not only directories that existed before this apply) — a
    # rewrite of another mate's tool-limits.json binds at its next start
    for path in other_home_paths(spec, mate):
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{path})", f"{tool}(/{path}/**)"]
    root = os.path.realpath(expand(spec["server"]["root"]))
    for name in SERVER_INFRASTRUCTURE:
        infra = os.path.join(root, name)
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{infra})", f"{tool}(/{infra}/**)"]
    # the t3 CLI install dir (attack round, finding 3): apply/status
    # themselves execute <t3_bin> with the team home, so a replaced
    # binary is code execution with principal privileges — and the dir
    # need not sit anywhere near the home chain, so it gets its own
    # always-on deny instead of relying on the sibling enumeration
    t3_dir = os.path.dirname(os.path.realpath(expand(spec["server"]["t3_bin"])))
    for tool in ("Write", "Edit"):
        deny += [f"{tool}(/{t3_dir})", f"{tool}(/{t3_dir}/**)"]
    # user-level protected folders, Write/Edit whether or not they exist
    # (P3: the sibling enumeration only covers names that exist at apply
    # time, so an absent ~/.zshenv was creatable — writing one is code
    # execution as the user at the next shell start). The trailing-*
    # entries are prefix families (window-dev*); a * wildcard inside a
    # deny path binds (live-proved, evidence 09)
    for path in _user_protected_paths(spec):
        base = path[:-1] if path.endswith("*") else path
        if path.endswith("*"):
            for tool in ("Write", "Edit"):
                deny += [f"{tool}(/{base}*)", f"{tool}(/{base}*/**)"]
        else:
            for tool in ("Write", "Edit"):
                deny += [f"{tool}(/{base})", f"{tool}(/{base}/**)"]
    for path in deny_read_paths(spec, mate):
        deny += _read_deny(path)
    read_rooted = bool(spec.get("allow_read_roots"))
    write_named = bool(spec.get("home_write_allow"))
    # RULE-LAYER CUT (panel 2, Volume; repair round 2, separate commit so
    # it can be dropped): the two sibling enumerations (rooted_read_denies
    # for reads and for the Write/Edit fence) and the deny_read_root_
    # siblings listing are REMOVED. They produced ~66k rules in tests /
    # 8.6k on the dev spec while duplicating what the gate already decides
    # at call time — including folders created after apply — and they made
    # status flap (q4 F8: a new sibling between apply and status read as
    # a stale fence). The rule layer keeps only the short list the panel
    # ruled sufficient: bare tool denies (census), Write/Edit denies for
    # the named write-sensitive surfaces, Read/Glob/Grep denies for
    # deny_read_paths. Everything outside those names is the gate's call.
    allow = [
        "Read", "Glob", "Grep", "TodoWrite",
        "ToolSearch", f"Write(/{home}/**)", f"Edit(/{home}/**)",
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
    note += (" SECOND LAYER. The primary fence is the PreToolUse hook "
             "below: it resolves every path (symlinks, .., case, Unicode, "
             "firmlinks) at call time and fences reads to the roots, "
             "writes to the home, and refuses every fetch-capable tool "
             "by exact name (no web access, decision 2026-11-11) — including "
             "folders created after this apply. These deny rules are the "
             "short-list backstop for the named sensitive surfaces only "
             "(census bare denies, write-sensitive names, deny_read_paths); "
             "they are regenerated by re-running apply. The hook command "
             "fails closed (|| exit 2); status verifies its presence, "
             "sha256, mode, interpreter, hook enablement and a canary.")
    if read_rooted or write_named:
        note += (" allow_read_roots is enforced by the gate at call time; "
                 "home_write_allow compiles to named Write/Edit rules "
                 "(rooted_home_write_rules).")
    return {
        "permissions": {"allow": allow, "deny": deny},
        "hooks": gate_hook_block(spec, mate),
        "_note": note,
    }


def write_file_assets(spec, mate):
    """Home dir, CLAUDE.md seed, CHARTER.md, tool-limits.json.

    CLAUDE.md is the teammate's live long-term memory: created only when
    missing, never rewritten by apply (a rewrite would erase remembered
    facts). CHARTER.md and tool-limits.json are config and follow the spec,
    always inside the home (an outside assets_dir is refused — see
    limits_paths).

    The atomic-write temporaries are staged under <server root>/run
    (attack round, finding 5): a temp staged next to the destination sits
    at a name no deny rule covers, where a teammate's Write tool could
    poll for it and poison the file between write and rename. run/ is
    Write-denied for every teammate.
    """
    home = teammate_home(spec, mate)
    os.makedirs(home, exist_ok=True)
    os.chmod(home, 0o700)
    root = os.path.realpath(expand(spec["server"]["root"]))
    staging = os.path.join(root, "run")
    os.makedirs(staging, exist_ok=True)
    # the gate config lands under <root>/config/teammate-gate/ (0600):
    # config/ is server-private for reads and infrastructure for writes,
    # so no teammate can alter its own fence policy. Written BEFORE
    # tool-limits.json, which wires the hook that reads it.
    config_dir = os.path.join(root, "config", "teammate-gate")
    os.makedirs(config_dir, exist_ok=True)
    gate_conf = os.path.join(config_dir, f"{mate['slug']}.json")
    write_if_changed(gate_conf,
                     json.dumps(gate_config(spec, mate), indent=2) + "\n",
                     0o600, staging_dir=staging)
    limits_path, charter_path = limits_paths(spec, mate)
    seed = ("<!-- Long-term memory of {name}. Append durable facts below; "
            "they persist across conversations and server restarts. -->\n"
            "# {name} — memory\n\n").format(name=mate["name"])
    wrote = []
    memory = os.path.join(home, "CLAUDE.md")
    if not os.path.exists(memory):
        write_if_changed(memory, seed, 0o600, staging_dir=staging)
        wrote.append("CLAUDE.md")
    if write_if_changed(charter_path, mate["charter"], 0o600,
                        staging_dir=staging):
        wrote.append("CHARTER.md")
    if write_if_changed(limits_path,
                        json.dumps(tool_limits(spec, mate), indent=2) + "\n",
                        0o600, staging_dir=staging):
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
    if mate.get("memory_link"):
        launch_args += ["--mcp-config", os.path.realpath(
            expand(mate["memory_link"]["mcp_config"]))]
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


def ensure_instances(spec, disable=()):
    """Merge each teammate's provider instance into settings.json.

    Preserves every other instance, every unknown key — including unknown
    keys INSIDE a teammate's own instance (repair round 1, P14: the
    wholesale replace silently deleted any field the server had added) —
    and the file's 0600 mode; copies customModels from the source instance
    at apply time. A no-change apply performs no write. ``disable`` names
    instances to disable in place (dropped teammates, P6): their entry and
    every unknown field survive, ``enabled`` turns false, so a dropped
    teammate's instance can no longer be spawned with its stale limits.

    Before the write, the current settings.json is saved as a 0600 preimage
    beside the state file (repair round 1, P19): a mid-apply death has a
    way back. The preimage is never printed and never leaves the server
    root's run/ folder.
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
        if have is None:
            merged = want
        else:
            merged = dict(have)
            for key, value in want.items():
                if key != "config":
                    merged[key] = value
            have_config = have.get("config")
            base_config = dict(have_config) if isinstance(
                have_config, dict) else {}
            base_config.update(want["config"])
            merged["config"] = base_config
        if have != merged:
            instances[mate["instance"]] = merged
            changed.append(mate["instance"])
    for instance_id in disable:
        have = instances.get(instance_id)
        if have is None:
            continue
        if have.get("enabled") is not False:
            merged = dict(have)
            merged["enabled"] = False
            instances[instance_id] = merged
            changed.append(f"{instance_id} (disabled)")
    if changed:
        preimage = os.path.join(
            expand(spec.get("state_file") or
                   os.path.join(spec["server"]["root"], "run",
                                "team_roster_state.json")),
            os.pardir, "team_roster_settings.preimage.json")
        preimage = os.path.normpath(preimage)
        os.makedirs(os.path.dirname(preimage), exist_ok=True)
        with open(settings_path(spec)) as fh:
            previous = fh.read()
        atomic_write(preimage, previous, 0o600)
        atomic_write(settings_path(spec), json.dumps(settings, indent=2), 0o600)
        log(f"provider instances written: {', '.join(changed)} "
            "(settings.json is watched live by the running server; "
            "preimage saved 0600 beside the state file)")
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


def _resolve_bound(mate, bound, by_id, recorded_by_name, state_path):
    """The bound conversation, validated (RF-MEMLINK-R1 item 2(i)).

    The board binding is the authority for the roster's RECORD: a stale state
    entry — including one whose thread sits on another provider instance, the
    Secretary shape on the real root — is followed past, never adopted from,
    and the record moves through this command, never through a hand edit of
    the state file. Two things still refuse, exactly as before: a bound
    thread on ANOTHER provider instance is never adopted, and a bound thread
    the state records for another teammate is ambiguity, not an adoption.
    """
    name = mate["name"]
    owner = next((n for n, tid in recorded_by_name.items()
                  if n != name and tid == bound), None)
    if owner:
        die(f"{name}: Paperclip binds its agent to thread {bound}, which the "
            f"roster state records for {owner}; refusing to pick or create "
            f"a primary thread")
    found = by_id.get(bound)
    if found is None:
        die(f"{name}: Paperclip binds its agent to thread {bound}, which "
            f"this roster does not know; refusing to create a second primary "
            f"thread. If {bound} is the real primary, record it in "
            f"{state_path} (or unbind the agent in Paperclip) and apply again")
    if found["instance"] and found["instance"] != mate["instance"]:
        die(f"{name}: Paperclip binds its agent to thread {bound}, but that "
            f"thread belongs to provider instance {found['instance']!r}, not "
            f"{mate['instance']!r}; a conversation on another provider "
            f"instance is never adopted")
    return found


def resolve_threads(spec, project_id):
    """The check phase of thread recovery (RF-MEMLINK-R1 item 2(ii)).

    Every conversation check — the state file, the live threads and the board
    bindings — runs here and refuses HERE, before cmd_apply has written the
    gate, the limits or settings.json. Nothing is created and no state is
    saved; commit_threads does the writing once every teammate resolved.
    """
    state, state_path = load_state(spec)
    live = list_threads(spec, project_id)
    by_id = {t["threadId"]: t for t in live}
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
        bound = bindings[mate["name"]]
        if bound is not None:
            found = _resolve_bound(mate, bound, by_id, recorded_by_name,
                                   state_path)
            recovered_by = ("state" if found["threadId"] == recorded
                            else "binding")
        else:
            found, problem = _recover_thread(mate, live, recorded_by_name)
            if problem:
                die(f"{mate['name']}: {problem}; refusing to pick or create "
                    f"a primary thread")
            recovered_by = (_recovered_by(mate, found, recorded)
                            if found is not None else None)
        if found is not None:
            threads[mate["name"]] = {
                "threadId": found["threadId"], "title": title,
                "created": False, "currentTitle": found["title"],
                "projectId": project_id, "pinnedAt": found["pinnedAt"],
                "recoveredBy": recovered_by,
                "instance": found["instance"] or mate["instance"],
            }
            if found["title"] != title:
                log(f"{mate['name']}: thread {found['threadId']} is titled "
                    f"{found['title']!r}; the roster title is {title!r}")
            continue
        to_create.append(mate)
    seen = {}
    for name, info in threads.items():
        if info["threadId"] in seen:
            die(f"{name} and {seen[info['threadId']]} resolved to the same "
                f"thread {info['threadId']}; refusing")
        seen[info["threadId"]] = name
    return threads, to_create, state, state_path


def commit_threads(spec, project_id, threads, to_create, state, state_path):
    """The write phase: mint what resolve_threads could not recover, re-run
    the duplicate check over resolved AND created ids, save the state."""
    # Every check has passed for every teammate; only now is a thread created,
    # so one teammate's refusal leaves the whole roster untouched.
    for mate in to_create:
        title = teammate_title(mate)
        launched = start_thread_after_settings(spec, [
            "thread", "start", project_id, "Reply with just: READY",
            "--provider", mate["instance"], "--model", spec["model"],
            "--title", title, "--json"], "t3 thread start")
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
    fresh = {name: {"instance": by_name[name]["instance"],
                    "threadId": info["threadId"],
                    "title": info["title"],
                    "threadInstance": info["instance"],
                    "recoveredBy": info["recoveredBy"]}
             for name, info in threads.items()}
    # P6: a teammate dropped from the spec keeps its state entry (with the
    # thread id and a removal stamp) instead of being silently erased —
    # the entry is the durable evidence of which thread was whose
    for name, entry in state["teammates"].items():
        if name not in fresh and entry:
            kept = dict(entry)
            kept.setdefault("removedAt",
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            fresh[name] = kept
    state["teammates"] = fresh
    state["appliedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(spec, state, state_path)
    return threads, state_path


def ensure_threads(spec, project_id):
    """Recover-then-create in one call — the pre-split behaviour, kept for
    the recovery suites and any caller that does not need cmd_apply's
    refuse-before-first-write ordering."""
    threads, to_create, state, state_path = resolve_threads(spec, project_id)
    return commit_threads(spec, project_id, threads, to_create,
                          state, state_path)


def acquire_apply_lock(spec):
    """One apply at a time per server root (repair round 1, P7/P13): two
    concurrent applies both passed the Paperclip pre-check and created two
    primary threads, wedging recovery and losing a settings.json update.
    The lock is an flock on <root>/run/team_roster.apply.lock held for the
    process lifetime; a second apply refuses loudly instead of waiting."""
    root = os.path.realpath(expand(spec["server"]["root"]))
    lock_dir = os.path.join(root, "run")
    os.makedirs(lock_dir, exist_ok=True)
    path = os.path.join(lock_dir, "team_roster.apply.lock")
    fh = open(path, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        die(f"another team_roster apply holds {path}; refusing to run "
            f"concurrently (the loser would create duplicate primary "
            f"threads and lose the settings.json update)")
    return fh


def dropped_teammates(spec):
    """Names of teammates that exist on disk or in state but left the spec.

    Sources: directories under <root>/teammates whose slug is not in the
    spec, and state entries whose name is not in the spec (P6). A dropped
    teammate's home, instance and thread must never silently lose their
    fences — apply refuses unless the operator confirms each drop."""
    spec_slugs = {mate["slug"] for mate in spec["teammates"]}
    spec_names = {mate["name"] for mate in spec["teammates"]}
    root = os.path.realpath(expand(spec["server"]["root"]))
    teammates_dir = os.path.join(root, "teammates")
    dropped = set()
    if os.path.isdir(teammates_dir):
        try:
            for name in os.listdir(teammates_dir):
                if name not in spec_slugs:
                    dropped.add(name)
        except OSError:
            pass
    state, _ = load_state(spec)
    for name, entry in state["teammates"].items():
        if name not in spec_names and entry and not entry.get("removedAt"):
            dropped.add(name)
    return sorted(dropped)


def confirm_drops(spec, dropped, confirmed):
    unknown = [d for d in confirmed if d not in dropped]
    if unknown:
        die(f"--drop names not recognized as dropped teammates: "
            f"{', '.join(unknown)}; droppable: {', '.join(dropped)}")
    still = [d for d in dropped if d not in confirmed]
    if still:
        die(f"spec drops existing teammate(s) {', '.join(still)}; refusing "
            f"to apply. Their home, instance and thread stay as they are. "
            f"To actually remove them, re-run apply with "
            f"--drop {','.join(dropped)} (their instance is disabled in "
            f"place, their home and state entry are kept, and every other "
            f"teammate's fences keep denying their home)")
    # instance ids for the confirmed drops: from state (by name), else the
    # directory slug as the instance id (the shipped specs use slug ids)
    state, _ = load_state(spec)
    instances = []
    for name in confirmed:
        entry = (state["teammates"].get(name) or {})
        if entry.get("instance"):
            instances.append(entry["instance"])
        else:
            instances.append(name)
    return instances


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
            try:
                # repair round 1, P18: a driver timeout used to crash apply
                # with a raw traceback mid-flight; it is one failed rename,
                # reported like any other
                proc = subprocess.run(
                    [expand(node_bin), driver, "rename", profile, url, tid,
                     current_title, title, result_path],
                    cwd="/tmp", capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                proc = subprocess.CompletedProcess((), 124, "",
                                                   "rename driver timed "
                                                   "out after 120s")
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


def report_pending_restarts(spec, pending):
    """The limitsPendingRestart warning (repair round 1, P16): emitted as
    soon as the file assets are written, BEFORE any stage that can still
    die (Paperclip refusal, ambiguity, rename crash) — a later die() must
    never leave new limits on disk with no warning and no report."""
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


def cmd_apply(spec, drop=()):
    acquire_apply_lock(spec)
    dropped = dropped_teammates(spec)
    disable = confirm_drops(spec, dropped, drop) if dropped else []
    project_id = ensure_project(spec)
    # RF-MEMLINK-R1 item 2(ii): every conversation check — the state file,
    # the live threads and the board bindings — runs and refuses HERE, before
    # the gate, the homes, the limits and settings.json are written. A
    # refusing apply leaves the root untouched; only the commit phase below
    # (after the settings are in place) mints threads and saves the state.
    resolved, to_create, thread_state, thread_state_path = \
        resolve_threads(spec, project_id)
    gate_sha = ensure_gate(spec)
    # every home exists BEFORE any limits are generated (repair round 1,
    # P1): the sibling enumeration of <root>/teammates then sees every
    # home this apply is creating, in this same run
    for mate in spec["teammates"]:
        home = teammate_home(spec, mate)
        os.makedirs(home, exist_ok=True)
        os.chmod(home, 0o700)
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
    report_pending_restarts(spec, pending)
    ensure_instances(spec, disable=disable)
    threads, _ = commit_threads(spec, project_id, resolved, to_create,
                                thread_state, thread_state_path)
    renames, rename_failures = rename_threads(spec, threads)
    urls_path = write_urls_file(spec, threads)
    log(f"thread URLs written: {urls_path} (0600, no credentials)")
    report = {
        "projectId": project_id,
        "gate": {"path": gate_install_path(spec), "sha256": gate_sha},
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


def _fence_status(spec, mate):
    """(limits_ok, gate_ok, problems) for one teammate's FENCE — the thing
    status exists to report (repair round 1, P17: it used to report
    homeOk/instanceOk without checking tool-limits.json, the launch wiring
    or the gate). Verifies, against regeneration from the spec:

    - tool-limits.json exists and is byte-identical to what apply would
      write now (stale content = stale fence);
    - the provider instance's homePath and launchArgs actually point at
      this home and this limits file (an unwired instance loads no
      limits);
    - the gate program exists at <root>/bin, matches the installation's
      sha256 and is exactly what tool-limits.json wires as the
      PreToolUse hook (a missing or altered hook lets every call through
      — live-proved fail-open);
    - the gate's mode is exactly 0555, the pinned interpreter exists
      (M-R2), no settings file that applies to the teammate sets
      disableAllHooks, and a canary call through the exact wired command
      exits 2 (repair round 2, R6c).
    """
    problems = []
    limits_path, _ = limits_paths(spec, mate)
    expected_limits = json.dumps(tool_limits(spec, mate), indent=2) + "\n"
    limits_ok = (os.path.isfile(limits_path) and
                 open(limits_path).read() == expected_limits)
    if not limits_ok:
        problems.append(f"tool-limits.json missing or not what apply would "
                        f"write now: {limits_path}")
    home = teammate_home(spec, mate)
    gate_path = gate_install_path(spec)
    config_path = gate_config_path(spec, mate)
    try:
        with open(GATE_SOURCE, "rb") as fh:
            gate_sha = hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        problems.append(f"gate program missing from the installation: "
                        f"{GATE_SOURCE}")
        gate_sha = None
    sha_ok = False
    if gate_sha is not None:
        if not os.path.isfile(gate_path):
            problems.append(f"gate not installed: {gate_path}")
        else:
            actual = hashlib.sha256(open(gate_path, "rb").read()).hexdigest()
            sha_ok = actual == gate_sha
            if not sha_ok:
                problems.append(f"gate at {gate_path} does not match the "
                                f"installation (sha256 {actual} != "
                                f"{gate_sha}); every tool call would pass "
                                f"through an altered gate")
    config_ok = (os.path.isfile(config_path) and
                 json.loads(open(config_path).read()) ==
                 gate_config(spec, mate))
    if not config_ok:
        problems.append(f"gate config missing or stale: {config_path}")
    wiring_ok = False
    if limits_ok:
        wired = json.loads(open(limits_path).read()).get("hooks") or {}
        commands = [h.get("command") for block in wired.get("PreToolUse", [])
                    for h in block.get("hooks", [])]
        expected_command = gate_command(spec, mate)
        wiring_ok = (any(block.get("matcher") == "*" for block
                         in wired.get("PreToolUse", [])) and
                     expected_command in commands)
        if not wiring_ok:
            problems.append(f"tool-limits.json does not wire the gate hook "
                            f"({expected_command})")
    # R6c (M6): four more things can silently unhook the gate. All four are
    # checked here so `status` exits non-zero on each.
    # 1) mode: the gate must be exactly 0555 — group/other-writable (or a
    #    root that lost its exec bit and relies on the || exit 2 refusal)
    #    is not an installed fence
    mode_ok = False
    if os.path.isfile(gate_path):
        mode = stat.S_IMODE(os.stat(gate_path).st_mode)
        mode_ok = mode == 0o555
        if not mode_ok:
            problems.append(f"gate mode is {mode:04o}, expected 0555: "
                            f"{gate_path}")
    # 2) the pinned hook interpreter exists and is executable (M-R2, panel
    #    3: the command no longer resolves python3 through PATH, so the
    #    exact binary must be present)
    python_ok = (os.path.isfile(GATE_INTERPRETER) and
                 os.access(GATE_INTERPRETER, os.X_OK))
    if not python_ok:
        problems.append(f"the pinned hook interpreter {GATE_INTERPRETER} is "
                        "missing or not executable; the gate hook command "
                        "cannot run and every call would fail closed to a "
                        "refusal — fix the launch environment")
    # 3) hooks disabled in any settings file that applies to the teammate:
    #    disableAllHooks in any one of them kills the PreToolUse fence
    settings_files = [
        os.path.join(home, name) for name in
        ("settings.json", "settings.local.json", "managed-settings.json")]
    settings_files.append(limits_path)
    hooks_enabled = True
    for path in settings_files:
        if not os.path.isfile(path):
            continue
        try:
            data = json.loads(open(path).read())
        except ValueError as exc:
            hooks_enabled = False
            problems.append(f"settings file that applies to the teammate "
                            f"is unparseable (may hide disableAllHooks): "
                            f"{path}: {exc}")
            continue
        if isinstance(data, dict) and data.get("disableAllHooks"):
            hooks_enabled = False
            problems.append(f"disableAllHooks is set in {path}; the "
                            "PreToolUse gate hook would never fire")
    # 4) canary: run the exact wired command with a call the gate must
    #    refuse (Bash is not on any teammate allowlist) and require exit 2
    canary_ok = False
    if os.path.isfile(gate_path) and mode_ok and python_ok and wiring_ok:
        payload = json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "true"},
                              "cwd": home, "hook_event_name": "PreToolUse"})
        try:
            proc = subprocess.run(gate_command(spec, mate), shell=True,
                                  input=payload, capture_output=True,
                                  text=True, timeout=30)
            canary_ok = proc.returncode == 2
        except (OSError, subprocess.TimeoutExpired) as exc:
            canary_ok = False
        if not canary_ok:
            problems.append(f"canary call to the gate did not refuse "
                            f"(expected exit 2, got "
                            f"{getattr(proc, 'returncode', '?')}); the "
                            "installed gate is not the fence")
    gate_ok = bool(gate_sha) and os.path.isfile(gate_path) and sha_ok and \
        config_ok and wiring_ok and mode_ok and python_ok and \
        hooks_enabled and canary_ok
    return limits_ok, gate_ok, problems


def cmd_status(spec):
    project = project_by_root(spec)
    settings = load_settings(spec)
    instances = settings.get("providerInstances", {})
    state, _ = load_state(spec)
    live = list_threads(spec, project["project_id"]) if project else []
    recorded_by_name = {name: (entry or {}).get("threadId")
                        for name, entry in state["teammates"].items()}
    rows = []
    fence_broken = []
    for mate in spec["teammates"]:
        home = teammate_home(spec, mate)
        instance = instances.get(mate["instance"])
        title = teammate_title(mate)
        thread, problem = _recover_thread(mate, live, recorded_by_name)
        limits_ok, gate_ok, problems = _fence_status(spec, mate)
        fence_broken += [f"{mate['name']}: {p}" for p in problems]
        launch = ((instance or {}).get("config") or {}).get("launchArgs", "")
        rows.append({
            "name": mate["name"],
            "home": home,
            "homeOk": os.path.isdir(home) and
                      os.path.exists(os.path.join(home, "CHARTER.md")),
            "instance": mate["instance"],
            "instanceOk": (instance is not None and
                           instance.get("displayName") == mate["name"] and
                           instance.get("accentColor") ==
                           mate["accent_color"] and
                           ((instance.get("config") or {}).get("homePath")
                            == home) and
                           f"--settings {limits_paths(spec, mate)[0]}" in
                           launch and
                           f"--append-system-prompt-file "
                           f"{limits_paths(spec, mate)[1]}" in launch),
            "limitsOk": limits_ok,
            "gateOk": gate_ok,
            "threadTitle": title,
            "threadId": (thread or {}).get("threadId"),
            "threadCurrentTitle": (thread or {}).get("title"),
            "pinned": bool((thread or {}).get("pinnedAt")),
            "recoveryProblem": problem,
        })
    print(json.dumps({"project": project, "teammates": rows,
                      "environmentId": environment_id(spec)}, indent=2))
    if fence_broken:
        # fail LOUDLY (design ruling): a missing or altered hook lets every
        # tool call through (live-proved fail-open), so a quiet yellow row
        # is not an acceptable report
        print("team_roster: FENCE BROKEN for: " + "; ".join(fence_broken),
              file=sys.stderr)
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["apply", "status"])
    ap.add_argument("spec")
    ap.add_argument("--drop", default="",
                    help="comma-separated teammates to actually drop when "
                    "the spec removes them (their instance is disabled in "
                    "place, home and state entry kept, fences kept)")
    args = ap.parse_args()
    spec = load_spec(args.spec)
    if args.command == "apply":
        drop = [d.strip() for d in args.drop.split(",") if d.strip()]
        return cmd_apply(spec, drop=drop)
    return cmd_status(spec)


if __name__ == "__main__":
    sys.exit(main())
