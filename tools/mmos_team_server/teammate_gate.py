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
import re
import socket
import sys
import threading
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

# One unreadable set (repair round 2, R3 + M5) used by Read, Glob and Grep
# alike: files in the teammate's OWN home that carry config, credentials or
# session transcripts. Panel 2 H3: Grep rooted at the home returned the
# cut-over preimage's content while Read of it refused; M5: .claude.json,
# .credentials.json, carrier.json and projects/ were fully readable. The
# families cover every spelling: anything starting with .claude.json (the
# backups a restart could honor) and settings*.json.
UNREADABLE_NAMES = frozenset({
    "cutover-preimage.json", ".credentials.json", ".claude.json",
    ".claude.json.backup", "carrier.json", "tool-limits.json",
    "settings.json", "settings.local.json", "managed-settings.json",
    "projects",
})


def unreadable_name(name):
    """True if a home-relative first component is in the unreadable set."""
    key = norm(name)
    exact = {norm(n) for n in UNREADABLE_NAMES}
    if key in exact:
        return True
    return (key.startswith(norm(".claude.json")) or
            (key.startswith(norm("settings")) and key.endswith(".json")))

PATH_WRITE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit", "MultiEdit"})
READ_TOOLS = frozenset({"Read"})
SEARCH_TOOLS = frozenset({"Glob", "Grep"})
WEB_TOOLS = frozenset({"WebFetch", "mcp__web_reader__webReader"})
FREE_TOOLS = frozenset({"TodoWrite", "WebSearch", "ToolSearch"})


def refuse(reason):
    # R4 (panel 2 M2): a broken stderr pipe (EPIPE while the reason is
    # printed) must not turn a refusal into exit 1 — which the client would
    # treat as allow. The refusal itself must survive.
    try:
        print(f"teammate_gate: {reason}", file=sys.stderr)
    except BaseException:
        pass
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
    if comp is not None and unreadable_name(comp):
        return (f"{comp} in the teammate home is not readable by the "
                "teammate (config/credentials/transcripts)")
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


# R5 (panel 2 N2): the client resolves @path import lines in files it loads
# by itself (user/project memory), so a written import would read outside
# every tool fence without a tool call ever happening.
IMPORT_LINE_RE = re.compile(r"(?m)^[ \t]*@\S")


def _new_content_strings(tool_input):
    out = []
    if isinstance(tool_input.get("content"), str):
        out.append(tool_input["content"])
    if isinstance(tool_input.get("new_string"), str):
        out.append(tool_input["new_string"])
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"),
                                                     str):
                out.append(edit["new_string"])
    return out


def check_import_lines(path, tool_input, cfg):
    """Refuse new content that puts an @ import line into a file the client
    loads by itself inside the teammate home: CLAUDE.md, CLAUDE.local.md,
    anything under a rules folder."""
    home = cfg["home"]
    if not under(path, home):
        return None
    base = norm(path.rstrip("/").rsplit("/", 1)[-1])
    home_comps = [c for c in home.split("/") if c]
    path_comps = [c for c in path.split("/") if c]
    rel = path_comps[len(home_comps):] if len(path_comps) > len(home_comps) \
        else []
    loaded = base in {norm("CLAUDE.md"), norm("CLAUDE.local.md")} or \
        any(norm(c) == norm("rules") for c in rel)
    if not loaded:
        return None
    for text in _new_content_strings(tool_input):
        if IMPORT_LINE_RE.search(text):
            return (f"an @ import line written into {path} would be "
                    "resolved by the client outside the tool fence; write "
                    "the content inline instead")
    return None


def check_pattern(pattern):
    if not isinstance(pattern, str) or not pattern or "\x00" in pattern:
        return "missing or invalid search pattern"
    if pattern.startswith("/") or pattern.startswith("~"):
        return f"search pattern must be relative ({pattern})"
    if ".." in pattern.split("/"):
        return f"search pattern must not climb (..) ({pattern})"
    # R3 (panel 2 M3): a brace alternative can be absolute or a climb
    # ({a,/etc/*}, {..}), and whether the client's glob engine expands it
    # into a real climb is not ours to bet on — braces and backslashes are
    # refused outright
    if "{" in pattern or "}" in pattern:
        return f"brace patterns are not permitted in search patterns " \
               f"({pattern})"
    if "\\" in pattern:
        return f"backslash is not permitted in search patterns ({pattern})"
    return None


def _searchable_hints(cfg):
    """Folders the teammate MAY search, for refusal texts: the workspace and
    home subfolders whose first component is not unreadable."""
    hints = []
    for root in cfg.get("read_roots") or []:
        if os.path.isdir(root):
            hints.append(root)
    home = cfg["home"]
    try:
        children = sorted(os.listdir(home))
    except OSError:
        children = []
    for name in children:
        if len(hints) >= 4:
            break
        if unreadable_name(name):
            continue
        if norm(name) in {norm(n) for n in PROTECTED_NAMES}:
            continue  # client config folders are not search targets either
        if os.path.isdir(os.path.join(home, name)):
            hints.append(os.path.join(home, name))
    return hints


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
    home = cfg["home"]
    # R3 (panel 2 H3/M5): a search whose root is, or is an ancestor of, any
    # unreadable path would enumerate or read it — the unreadable set is one
    # set for Read, Glob and Grep alike. The home itself always contains
    # unreadable names (tool-limits.json, projects/), so a search rooted at
    # the home is refused outright and the text names searchable folders.
    unreadable = [os.path.join(home, n) for n in UNREADABLE_NAMES]
    for path in unreadable:
        if under(path, root):
            hints = ", ".join(_searchable_hints(cfg)[:3]) or "(none)"
            return (f"search root {root} sits at or above protected "
                    f"teammate files ({os.path.basename(path)} and the "
                    f"other unreadable home names); search instead: {hints}")
    # a search may not start AT or ABOVE a denied folder: enumerating a
    # denied folder's parent leaks its names, and a search rooted above one
    # walks into it (repair round 1, P4)
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


# R6a (panel 2 M1): an explicit refusal list, not is_global alone — the
# panel measured 224.0.0.1, ff02::1, ::127.0.0.1 and 64:ff9b::7f00:1 all
# passing is_global. Loopback, private, link-local, unique-local, multicast,
# unspecified, reserved, IPv4-mapped and IPv4-compatible IPv6, NAT64
# (64:ff9b::/96, where this Mac's Tailscale addresses live via 100.64/10),
# 6to4, Teredo and carrier-grade NAT 100.64.0.0/10.
REFUSED_ADDRESS_NETS = tuple(ipaddress.ip_network(net) for net in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
    "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
    "224.0.0.0/4", "240.0.0.0/4",
    "::/96", "::1/128", "64:ff9b::/96", "100::/64", "2001::/32",
    "2001:db8::/32", "2002::/16", "fc00::/7", "fe80::/10", "ff00::/8",
))


def address_reason(ip_text):
    """Refusal reason for one resolved address, or None if it may pass."""
    try:
        ip = ipaddress.ip_address(str(ip_text).split("%", 1)[0])
    except ValueError:
        return f"non-IP address {ip_text}"
    for net in REFUSED_ADDRESS_NETS:
        if ip in net:
            return (f"{ip} falls in the refused range {net} (loopback/"
                    "private/translated/reserved classes are refused)")
    if not ip.is_global:
        return f"{ip} is not a global address"
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None and address_reason(str(mapped)):
            return f"{ip} maps the refused IPv4 {mapped}"
    return None


# R2 (panel 2 H2, principal ruling — deliberately stricter than the score):
# do not try to parse like the client. Only a plain DNS name reaches
# resolution; every address-literal spelling (dotted, decimal, octal, hex,
# IPv6, bracketed), any userinfo, backslash, whitespace, control character,
# percent-encoding or non-ASCII in the authority, any scheme but http/https
# and any non-default port is refused outright.
_DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def _authority_reason(netloc, scheme):
    if netloc.count(":") > 1:
        return f"bare IPv6 literal or extra colon in authority ({netloc!r})"
    if any(ch in netloc for ch in "[]@%\\"):
        return (f"authority {netloc!r} contains an address literal marker, "
                "userinfo, percent-encoding or backslash")
    if any(ord(ch) > 0x7F or ord(ch) < 0x20 for ch in netloc):
        return f"non-ASCII or control character in authority ({netloc!r})"
    host, _, port_text = netloc.partition(":")
    host = host.lower()
    if port_text:
        if not port_text.isdigit():
            return f"port {port_text!r} is not numeric"
        if int(port_text) not in (80, 443):
            return (f"port {port_text} is not a default web port "
                    "(teammates fetch plain http/https only)")
        if (scheme == "https" and int(port_text) == 80) or \
                (scheme == "http" and int(port_text) == 443):
            return f"port {port_text} does not match scheme {scheme}"
    if not host or len(host) > 253:
        return f"missing or over-long host in {netloc!r}"
    labels = host.split(".")
    if any(not _DNS_LABEL_RE.match(label) for label in labels):
        return f"host {host!r} is not a plain DNS name (address literals, " \
               "empty or malformed labels are refused)"
    if any(label.isdigit() for label in labels):
        return (f"host {host!r} has an all-numeric label — the client "
                "family parses those as IPv4 (decimal/octal/hex)")
    if any(label.lower().startswith("0x") for label in labels):
        return f"host {host!r} has a hex-literal label"
    return None


_RESOLVE_JOIN_SECONDS = 5


def _resolve_host(host):
    """DNS in a daemon thread with a hard 5-second join (R4, panel 2 M2):
    signal.alarm does not reliably interrupt a blocked getaddrinfo, and a
    lookup that outlives the client's hook timeout fails OPEN — so the
    thread is abandoned and the call refused instead."""
    box = {}

    def worker():
        try:
            box["infos"] = socket.getaddrinfo(host, None)
        except BaseException as exc:  # noqa: BLE001 - any failure refuses
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(_RESOLVE_JOIN_SECONDS)
    if thread.is_alive() or "infos" not in box:
        return None
    return box["infos"]


def check_web(tool_input):
    # R1 (panel 2 H1): read exactly the url field the fetcher uses — the
    # old scan took the FIRST http(s)-prefixed string, so a public `prompt`
    # hid a loopback `url`.
    url = tool_input.get("url")
    if not isinstance(url, str) or not url:
        return "web tool input has no 'url' string; refusing"
    if url != url.strip():
        return "web url has leading or trailing whitespace; refusing"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return "web url contains a control character; refusing"
    if any(ch.isspace() for ch in url):
        return "web url contains whitespace; refusing"
    if "\\" in url:
        return "web url contains a backslash; refusing"
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return f"unparseable URL {url!r}"
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return f"web tool scheme {scheme!r} is not allowed (http/https only)"
    if not parsed.netloc:
        return f"no authority in {url!r}"
    reason = _authority_reason(parsed.netloc, scheme)
    if reason:
        return reason
    host = parsed.netloc.partition(":")[0].lower()
    infos = _resolve_host(host)
    if infos is None:
        return f"DNS lookup for {host} failed or timed out; refusing"
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return f"no addresses for {host}; refusing"
    for address in sorted(addresses):
        reason = address_reason(address)
        if reason:
            return f"{host} resolves to a refused address ({reason})"
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
        reason = check_path_write(path, cfg)
        if reason:
            return reason
        return check_import_lines(path, tool_input, cfg)
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
