#!/usr/bin/env python3
"""teammate_gate — the PRIMARY fence for every MMOS teammate session.

Installed by ``team_roster.py apply`` at ``<server root>/bin/teammate_gate.py``
(a folder no teammate can write) and wired into each teammate's
tool-limits.json as a PreToolUse hook with matcher ``*``:

    {"matcher": "*", "hooks": [{"type": "command",
     "command": "<root>/bin/teammate_gate.py --config <config path>"}]}

Live-proved on the RL dev server (2026-11-11, evidence 12): hooks in the
--settings file fire inside teammate turns, exit 2 BLOCKS the tool call with
stderr shown to the model, and exit 0 allows. A hook that exits any other
code, or is missing entirely, lets the call THROUGH (fail-open, proved live)
— which is why this program wraps every path in a fail-closed handler and
``apply``/``status`` verify its presence and sha256 loudly.

Policy (per ruling, repair round 1): resolve the real path (symlinks, ``..``,
``//``, ``/./``, case on a case-insensitive volume, Unicode form), then

- writes (Write/Edit/NotebookEdit/MultiEdit): only inside the teammate's own
  home, never a protected (config/locked) name; with ``write_names`` set,
  only those names. Everything else is refused.
- reads (Read): only inside the home and the spec's read roots, minus the
  deny list (checked after resolution).
- searches (Glob/Grep): the search root must itself pass the read policy and
  must not sit at or above a denied folder; patterns must be relative and
  stay inside the root (no leading / ~, no ``..``).
- web (WebFetch and any web-reader tool): the host is resolved by address;
  loopback, link-local, private, reserved and non-http(s) targets refused.
- unknown tool or unparseable input: refused.

Deny-list entries may end with ``*`` for a prefix family (e.g. the
``window-dev*`` folders). Stdlib only; no logging (attempted paths are not
ours to persist). Exit 2 = refuse, 0 = allow.
"""
import ipaddress
import json
import os
import signal
import socket
import sys
import unicodedata
import urllib.parse

# Mirrors HOME_LOCKED/HOME_CONFIG in team_roster.py plus the backup name a
# restart honors (probe 5). tests/test_mmos_teammate_gate.py asserts the two
# constant sets stay in sync.
PROTECTED_NAMES = frozenset({
    # team_roster.HOME_LOCKED
    "tool-limits.json", "CHARTER.md", "carrier.json",
    "cutover-preimage.json", "cutover-result.json",
    # team_roster.HOME_CONFIG
    "settings.json", "settings.local.json", "managed-settings.json",
    ".claude.json", ".mcp.json", ".credentials.json", "keybindings.json",
    "CLAUDE.local.md", ".claude", "plugins", "skills", "agents", "commands",
    "hooks", "rules", "output-styles", "backups", "sessions", "projects",
    "todos", "shell-snapshots", "statsig", "ide",
    # restart-honored / belt (probe 5)
    ".claude.json.backup", "CLAUDE.md.backup",
})

UNREADABLE_NAMES = frozenset({"cutover-preimage.json"})

PATH_WRITE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit", "MultiEdit"})
READ_TOOLS = frozenset({"Read"})
SEARCH_TOOLS = frozenset({"Glob", "Grep"})
WEB_TOOLS = frozenset({"WebFetch", "mcp__web_reader__webReader"})
FREE_TOOLS = frozenset({"TodoWrite", "WebSearch", "ToolSearch"})


def refuse(reason):
    print(f"teammate_gate: {reason}", file=sys.stderr)
    raise SystemExit(2)


def norm(text):
    """Comparison key: macOS volumes are case-insensitive and store names
    in NFD, while a tool call may spell NFC (or any case) — both name the
    same file, so both keys must collide."""
    return unicodedata.normalize("NFC", text).casefold()


def canon_case(path):
    """The true on-disk spelling of every component (``~/.SSH`` -> the real
    ``.ssh``); components that do not exist keep their given spelling and
    are compared through ``norm`` by callers."""
    parts = [p for p in path.split("/") if p]
    current = "/"
    real = []
    for part in parts:
        try:
            names = os.listdir(current)
        except OSError:
            names = []
        key = norm(part)
        chosen = part
        for name in names:
            if norm(name) == key:
                chosen = name
                break
        real.append(chosen)
        current = os.path.join(current, chosen)
    return "/" + "/".join(real) if real else "/"


def resolve(path, cwd):
    if not isinstance(path, str) or not path or "\x00" in path:
        return None
    expanded = os.path.expanduser(path)
    if not expanded.startswith("/"):
        expanded = os.path.join(cwd if isinstance(cwd, str) and
                                cwd.startswith("/") else "/", expanded)
    real = os.path.realpath(expanded)
    # firmlink canonicalization (live-proved 2026-11-11: realpath keeps the
    # /System/Volumes/Data spelling while naming the SAME file): prefer the
    # firmlink-root spelling so every comparison sees one form
    data_prefix = "/System/Volumes/Data"
    if real.startswith(data_prefix + "/"):
        alias = real[len(data_prefix):]
        if os.path.exists(alias):
            real = alias
    return canon_case(real)


def under(path, root):
    root = root.rstrip("*").rstrip("/") or "/"
    return norm(path) == norm(root) or \
        norm(path).startswith(norm(root) + "/")


def deny_hit(path, entries, home):
    """True if ``path`` falls under a deny entry. An entry that is a strict
    ancestor of the home (e.g. the whole server root) does not deny paths
    inside the home itself — the home has its own protected-name rules."""
    for entry in entries:
        base = entry[:-1] if entry.endswith("*") else entry
        if entry.endswith("*"):
            if norm(path).startswith(norm(base)):
                return True
            continue
        if under(path, base) and not (base != home and under(home, base)
                                      and under(path, home)):
            return True
    return False


def load_config(argv):
    if len(argv) != 3 or argv[1] != "--config":
        refuse("wired without --config; refusing")
    try:
        with open(argv[2]) as fh:
            config = json.load(fh)
    except (OSError, ValueError) as exc:
        refuse(f"cannot read gate config {argv[2]} ({exc}); refusing")
    if not isinstance(config, dict):
        refuse("gate config is not an object; refusing")
    for key in ("home",):
        if not isinstance(config.get(key), str) or not config[key]:
            refuse(f"gate config missing '{key}'; refusing")
    for key in ("read_roots", "deny_reads", "write_names"):
        value = config.get(key)
        if value is not None and not isinstance(value, list):
            refuse(f"gate config '{key}' is not a list; refusing")
    return config


def rel_first_component(path, home):
    """First path component inside the home, or None if not inside."""
    key = norm(path)
    root = norm(home)
    if key == root:
        return None
    if not key.startswith(root + "/"):
        return None
    rest = key[len(root) + 1:]
    return rest.split("/", 1)[0] if rest else None


def check_path_read(path, cfg):
    home = cfg["home"]
    roots = cfg.get("read_roots")
    if roots is None:
        # deny-list mode (spec without allow_read_roots): every path not on
        # the deny list is readable, exactly like today's rule semantics
        inside = True
    else:
        # rooted mode: reads only inside the home and the spec's roots
        inside = under(path, home) or any(under(path, r) for r in roots)
    if not inside:
        return f"path {path} is outside the readable roots"
    if deny_hit(path, cfg.get("deny_reads") or [], home):
        return f"path {path} is on the deny list"
    comp = rel_first_component(path, home)
    if comp is not None and comp in {norm(n) for n in UNREADABLE_NAMES}:
        return "the preimage is not readable by the teammate"
    return None


def check_path_write(path, cfg):
    home = cfg["home"]
    if not under(path, home):
        return f"writes are fenced to the teammate home ({path})"
    comp = rel_first_component(path, home)
    if comp is None:
        return "the home directory itself is not writable"
    if comp in {norm(n) for n in PROTECTED_NAMES}:
        return f"{comp} is a protected teammate file"
    names = cfg.get("write_names")
    if names is not None:
        allowed = set()
        for name in names:
            if not isinstance(name, str) or not name:
                refuse("gate config write_names entry is not a name")
            allowed.add(norm(name.rstrip("/")))
        if comp not in allowed:
            return f"only the named home entries are writable ({comp})"
    return None


def check_pattern(pattern):
    if not isinstance(pattern, str) or not pattern or "\x00" in pattern:
        return "missing or invalid search pattern"
    if pattern.startswith("/") or pattern.startswith("~"):
        return f"search pattern must be relative ({pattern})"
    if ".." in pattern.split("/"):
        return f"search pattern must not climb (..) ({pattern})"
    return None


def check_search(tool_input, cwd, cfg):
    root_arg = None
    for key in ("path", "search_root", "root", "directory"):
        if isinstance(tool_input.get(key), str) and tool_input[key]:
            root_arg = tool_input[key]
            break
    root = resolve(root_arg, cwd) if root_arg else \
        resolve(".", cwd)
    if root is None:
        return "unparseable search root"
    reason = check_path_read(root, cfg)
    if reason:
        return reason
    # a search may not start AT or ABOVE a denied folder: enumerating a
    # denied folder's parent leaks its names, and a search rooted above one
    # walks into it (repair round 1, P4)
    home = cfg["home"]
    for entry in cfg.get("deny_reads") or []:
        base = entry[:-1] if entry.endswith("*") else entry
        if base == home:
            continue
        if under(base, root):
            return f"search root {root} sits at or above the denied " \
                   f"folder {base}"
    for key in ("pattern", "glob"):
        if key in tool_input:
            reason = check_pattern(tool_input[key])
            if reason:
                return reason
    return None


class _Alarm(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _Alarm()


def check_web(tool_input):
    url = None
    for key, value in tool_input.items():
        if isinstance(value, str) and value.startswith(("http://",
                                                        "https://")):
            url = value
            break
    if url is None:
        return "no URL in web tool input; refusing"
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return f"unparseable URL {url!r}"
    if parsed.scheme not in ("http", "https"):
        return f"web tool scheme {parsed.scheme!r} is not allowed"
    host = parsed.hostname
    if not host:
        return f"no host in {url!r}"
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return f"unresolvable host {host!r}"
    previous = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(5)
    try:
        infos = socket.getaddrinfo(host, None)
    except _Alarm:
        return f"DNS lookup for {host} timed out; refusing"
    except (socket.gaierror, OSError):
        return f"cannot resolve {host}; refusing"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return f"no addresses for {host}; refusing"
    for address in sorted(addresses):
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            return f"non-IP address {address} for {host}; refusing"
        if not ip.is_global:
            return f"{host} resolves to a non-public address ({address}); " \
                   "loopback and private targets are refused"
    return None


def decide(payload):
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool, str) or not tool:
        return "no tool name in hook input"
    if not isinstance(tool_input, dict):
        return f"unparseable input for {tool}"
    cfg = CONFIG
    cwd = payload.get("cwd")
    if tool in PATH_WRITE_TOOLS:
        path = resolve(tool_input.get("file_path"), cwd)
        if path is None:
            return f"unparseable path for {tool}"
        return check_path_write(path, cfg)
    if tool in READ_TOOLS:
        path = resolve(tool_input.get("file_path"), cwd)
        if path is None:
            return "unparseable path for Read"
        return check_path_read(path, cfg)
    if tool in SEARCH_TOOLS:
        return check_search(tool_input, cwd, cfg)
    if tool in WEB_TOOLS:
        return check_web(tool_input)
    if tool in FREE_TOOLS:
        return None
    return f"tool {tool} is not on this teammate's allowlist"


def main(argv):
    global CONFIG
    try:
        CONFIG = load_config(argv)
        try:
            payload = json.loads(sys.stdin.read())
        except ValueError as exc:
            refuse(f"unparseable hook input ({exc})")
        if not isinstance(payload, dict):
            refuse("hook input is not an object")
        reason = decide(payload)
        if reason:
            refuse(reason)
        return 0
    except SystemExit:
        raise
    except BaseException as exc:  # fail closed: nothing may fall through
        print(f"teammate_gate: internal error ({type(exc).__name__}); "
              "refusing", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
