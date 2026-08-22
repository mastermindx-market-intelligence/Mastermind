"""scripts/chairman_control_room.py — Chairman Control Room P0, Wave C.

A **loopback-only, ephemeral, local presentation process** (architecture doc
``research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_P0_ARCHITECTURE_AND_FABLE00_
COMMISSION_2026-08-21.md`` §8). It composes the read-only
``mastermind.chairman_control_room.v1`` document (Wave A, :mod:`control_plane.
chairman_control_room`), offers one-click navigation to a bound surface (Wave
B, :mod:`integrations.chairman_surfaces`), and lets the Chairman bind/unbind a
navigation-only local surface address (:mod:`control_plane.surface_bindings`).

Everything canonical stays read-only.  The **only** disk write anywhere in
this process is the atomic, ``0600`` surface-bindings save
(:func:`control_plane.surface_bindings.save_bindings`), reached from exactly
two endpoints: ``POST /api/bind`` and ``POST /api/unbind`` (plus one
``last_verified_at`` write-back from a successful ``POST /api/open``, which is
the SAME file, the SAME atomic writer). No canonical Agent OS / Executive OS /
GitHub / Macro state is ever written by this process — see the module-level
design laws in ``control_plane/chairman_control_room.py`` and
``control_plane/surface_bindings.py``, both reused, never re-implemented, here.

Runtime shape (architecture §8.2/§8.3)
---------------------------------------
* binds ``127.0.0.1`` ONLY — there is no ``--host`` flag, and the server
  refuses to start (``assert``) if the bound socket is ever not loopback;
* no background scheduler, no durable event loop — every ``GET`` recomputes
  state fresh from canonical readers (`Fresh composition on every call`);
* the one exception, by design (P0 acceptance row 28 — restart-forgets
  proof): a successful ``POST /api/refresh-builds`` stores its live
  ``project_active_builds.v1`` document in **process memory only**
  (``ServerConfig.live_cache``); a process restart forgets it, exactly like
  every other piece of server state;
* every request is loopback + Host-header gated; every mutating (``POST``)
  request additionally requires the ``X-CCR-Token`` minted fresh at process
  start and, when an ``Origin`` header is present, an exact match against the
  server's own origin;
* static assets are served from a closed, explicit ``{name: (path, mime)}``
  map — a request path is only ever used as a dict LOOKUP key, never
  concatenated into a filesystem path, so path traversal has no code path to
  reach;
* ``POST /api/open`` accepts only a ``binding_id`` — never a URL, argv, path,
  or profile from the browser; the actual navigation argv is built entirely
  server-side by :mod:`integrations.chairman_surfaces`.

Usage
-----
    python3 scripts/chairman_control_room.py
    python3 scripts/chairman_control_room.py --port 8888 --open
    python3 scripts/chairman_control_room.py --check
"""
from __future__ import annotations

import argparse
import http.server
import ipaddress
import json
import os
import secrets
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

_REPO_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_REPO_ROOT))

from control_plane import ceo_boot_packet  # noqa: E402  (after sys.path bootstrap)
from control_plane import chairman_control_room as ccr  # noqa: E402
from control_plane import executive_inbox  # noqa: E402
from control_plane import surface_bindings as sb  # noqa: E402
from integrations.chairman_surfaces import capability, chatgpt, contract  # noqa: E402
from integrations.chairman_surfaces import runner as surfaces_runner  # noqa: E402

#: Default static asset directory (Wave C's private, non-public UI).
DEFAULT_STATIC_DIR = _REPO_ROOT / "app" / "static" / "chairman_control"

#: Default ephemeral loopback port.
DEFAULT_PORT = 8787

#: Host is hard-coded, never a flag — see module docstring / architecture §8.2.
HOST = "127.0.0.1"

#: Every Host header value this server accepts (with or without ``:<port>``).
_ALLOWED_HOSTNAMES = ("127.0.0.1", "localhost")

#: Bound applied to a POST JSON body before it is even parsed.
_MAX_BODY_BYTES = 64 * 1024

#: Timeout for the Macro active-builds refresh subprocess (frozen spec).
_REFRESH_BUILDS_TIMEOUT = 180.0

#: Timeout for the discover-tabs AppleScript probe — short, this is a
#: read-only local enumeration a human is waiting on synchronously.
_DISCOVER_TABS_TIMEOUT = 10.0

#: Cap applied to both discovery listings (claude_code_sessions, codex_sessions).
_DISCOVER_CAP = 40

#: Content-Security-Policy applied to every HTML response.
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self' data:"
)


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------

def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


#: Default output cap for the cwd-supporting branch of :func:`default_runner`
#: — matches ``integrations.chairman_surfaces.runner``'s own 64 KiB bound
#: (:data:`integrations.chairman_surfaces.runner._MAX_BYTES`) so a caller
#: that does not explicitly widen it (i.e. every adapter-shaped call this
#: branch might ever receive) keeps byte-identical behavior to Wave B.
_DEFAULT_CWD_RUNNER_MAX_BYTES = 65536

#: Output cap for the ONE caller that needs more than 64 KiB: the Macro
#: active-build compiler's ``--json-stdout`` document, which is real
#: organizational data (measured 112,569 bytes in Wave D live proof — see
#: the fix commission) and must never be silently truncated before
#: ``json.loads`` sees it. 4 MiB is a generous multiple of that measured
#: size, not a guess; ``integrations/chairman_surfaces/runner.py`` itself is
#: NOT touched — its 64 KiB cap stays exactly as-is for every adapter call,
#: whose outputs are tiny (osascript/open exit codes and short strings) by
#: design.
_REFRESH_BUILDS_MAX_OUTPUT_BYTES = 4 * 1024 * 1024


def _cap_text(data: bytes | str | None, limit: int = _DEFAULT_CWD_RUNNER_MAX_BYTES) -> str:
    """Bound captured subprocess text to ``limit`` bytes, mirroring ``surfaces_runner._cap``."""
    if not data:
        return ""
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > limit:
        return encoded[:limit].decode("utf-8", errors="ignore")
    return text


def default_runner(
    argv: list[str], *, timeout: float = 20.0, cwd: str | None = None, max_bytes: int | None = None
) -> dict:
    """The server's default subprocess runner.

    Every provider-adapter navigation call dispatched through
    :func:`integrations.chairman_surfaces.contract.open_binding` (i.e. every
    call this function receives WITHOUT a ``cwd``) delegates straight to
    :func:`integrations.chairman_surfaces.runner.run_argv` — the ONE
    subprocess boundary that package's own tests pin — so ``/api/open``'s
    subprocess behavior is byte-identical to Wave B's. ``max_bytes`` is
    IGNORED on this branch (``run_argv`` itself has no such parameter and is
    outside this packet's edit scope; its fixed 64 KiB cap is exactly what
    those small adapter outputs need).

    Only ``/api/refresh-builds`` (invoking Macro's active-build compiler
    script) needs a working directory, and ``run_argv`` has no ``cwd``
    parameter — that module is outside this packet's edit scope (see the
    build commission's OWNED FILES). This branch reuses ``run_argv``'s own
    argv-validation gate (:func:`integrations.chairman_surfaces.runner.
    _validate_argv`) and reproduces its exact safety properties (``shell=
    False``, never raising on subprocess failure), but takes an explicit
    ``max_bytes`` output cap (default matches ``run_argv``'s own 64 KiB;
    ``/api/refresh-builds`` widens it to 4 MiB — Wave D live proof found the
    real ``project_active_builds.v1`` document, 112,569 bytes, silently
    truncated below valid JSON at the old fixed 64 KiB bound).
    """
    if cwd is None:
        return surfaces_runner.run_argv(argv, timeout=timeout)

    limit = max_bytes if max_bytes is not None else _DEFAULT_CWD_RUNNER_MAX_BYTES
    validated = surfaces_runner._validate_argv(argv)  # reuse, not duplicate, the gate
    try:
        completed = subprocess.run(
            validated, shell=False, capture_output=True, timeout=timeout, cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "code": None, "stdout": _cap_text(exc.stdout, limit), "stderr": _cap_text(exc.stderr, limit),
            "timed_out": True,
        }
    except OSError as exc:
        return {"code": None, "stdout": "", "stderr": _cap_text(str(exc), limit), "timed_out": False}
    return {
        "code": completed.returncode,
        "stdout": _cap_text(completed.stdout, limit),
        "stderr": _cap_text(completed.stderr, limit),
        "timed_out": False,
    }


def _resolve_macro_root_simple(
    flag: str | None, environ: Mapping[str, str], repo_root: Path
) -> str | None:
    """Locate a Macro checkout directory for THIS server's own direct reads.

    Deliberately NOT :func:`control_plane.ceo_boot_packet.resolve_macro_root`
    — that ladder additionally requires ``scripts/agentos.py`` AND an
    ``agentos/`` store to consider a candidate "usable", which is a Agent-OS
    -specific concern unrelated to whether a Macro checkout carries
    ``scripts/build_project_active_build_map.py`` (the ONLY thing
    ``/api/refresh-builds`` and the live-active-builds override path need).
    Same candidate ORDER (flag -> env -> sibling "../Macro Dashboard" ->
    vendor/macro), existence-only test.
    """
    candidates = [
        flag,
        environ.get("MASTERMIND_MACRO_ROOT"),
        os.fspath(repo_root.parent / "Macro Dashboard"),
        os.fspath((repo_root / "vendor" / "macro").resolve()),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return candidate
    return None


def _unknown_key(data: dict, allowed: set) -> str | None:
    for key in data.keys():
        if key not in allowed:
            return key
    return None


# ---------------------------------------------------------------------------
# server configuration (injection seams)
# ---------------------------------------------------------------------------

@dataclass
class ServerConfig:
    """Everything a request handler needs, injected so tests never touch the
    real filesystem/subprocess/clock beyond what they explicitly opt into.
    """

    repo_root: Path
    macro_root: str | None
    bindings_path: str | Path | None
    token: str
    origin: str
    port: int
    static_dir: Path = DEFAULT_STATIC_DIR
    runner: Callable[..., dict] = default_runner
    now_fn: Callable[[], str] = _utc_now_z
    open_binding_fn: Callable[[dict, Callable], dict] = contract.open_binding
    #: Process-memory-only live active-builds cache — see module docstring.
    #: A fresh ``ServerConfig`` (i.e. a process restart) always starts empty.
    live_cache: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# state composition — reuses build_control_room/compose_control_room
# ---------------------------------------------------------------------------

def _compose_state_doc(config: ServerConfig) -> dict[str, Any]:
    """Fresh ``mastermind.chairman_control_room.v1`` document for ``/api/state``.

    No live-active-builds cache -> a plain, un-duplicated call to
    :func:`control_plane.chairman_control_room.build_control_room` (the
    common case; zero gather-layer duplication).

    A live cache present (from a prior ``/api/refresh-builds``) -> hand it to
    :func:`control_plane.chairman_control_room.compose_control_room` IN PLACE
    of a fresh active-builds file read (frozen spec: "passes it INTO the
    composition in place of the artifact read"). ``build_control_room``
    exposes no injection point for this (and ``chairman_control_room.py`` is
    out of this packet's edit scope), so :func:`_compose_with_live_active_builds`
    replicates that function's own gather-layer sequencing for this one path.
    """
    generated_at = config.now_fn()
    live_active_builds = config.live_cache.get("active_builds")
    if live_active_builds is None:
        return ccr.build_control_room(
            repo_root=config.repo_root,
            macro_root_flag=config.macro_root,
            environ=os.environ,
            now=generated_at,
            timeout=ceo_boot_packet.DEFAULT_TIMEOUT,
            bindings_path=config.bindings_path,
        )
    return _compose_with_live_active_builds(config, live_active_builds, generated_at)


def _compose_with_live_active_builds(
    config: ServerConfig, live_active_builds: dict[str, Any], generated_at: str
) -> dict[str, Any]:
    root = config.repo_root

    packet: dict[str, Any] | None = None
    packet_failure: str | None = None
    try:
        packet = ceo_boot_packet.build_packet(
            repo_root=root, macro_root_flag=config.macro_root, environ=os.environ,
            now=generated_at, timeout=ceo_boot_packet.DEFAULT_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 — gather layer never raises
        packet_failure = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"

    inbox: dict[str, Any] | None = None
    inbox_failure: str | None = None
    try:
        inbox = executive_inbox.build_inbox(
            repo_root=root, boot_packet=packet, environ=os.environ,
            now=generated_at, timeout=ceo_boot_packet.DEFAULT_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 — gather layer never raises
        inbox_failure = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"

    # Same macro-root preference ccr.build_control_room itself uses: reuse the
    # packet's own reported root first, fall back to Macro's own ladder
    # function only when the packet gave us nothing (receipt: chairman_
    # control_room.py build_control_room(), "Resolve the Macro root exactly
    # like the packet does").
    macro_root_resolved: str | None = None
    if isinstance(packet, dict):
        macro = packet.get("macro")
        if isinstance(macro, dict):
            macro_root_resolved = macro.get("root")
    if not macro_root_resolved:
        resolved, _via, _candidates = ceo_boot_packet.resolve_macro_root(
            config.macro_root, os.environ, root
        )
        if resolved is not None:
            macro_root_resolved = os.fspath(resolved)

    agent_os_state, agent_os_state_failure = ccr._read_agent_os_state(macro_root_resolved)
    runtime_jobs, runtime_jobs_failure = ccr._read_runtime_jobs(root)
    bindings, binding_problems = sb.load_bindings(config.bindings_path)

    doc = ccr.compose_control_room(
        inbox=inbox,
        boot_packet=packet,
        active_builds=live_active_builds,
        agent_os_state=agent_os_state,
        runtime_jobs=runtime_jobs,
        bindings=bindings,
        binding_problems=binding_problems,
        generated_at=generated_at,
    )

    extra_degraded: list[str] = []
    if packet_failure:
        extra_degraded.append(f"boot_packet: unavailable — {packet_failure}")
    if inbox_failure:
        extra_degraded.append(f"executive_inbox: unavailable — {inbox_failure}")
    if agent_os_state_failure:
        extra_degraded.append(f"agent_os_state: {agent_os_state_failure}")
    if runtime_jobs_failure:
        extra_degraded.append(f"executive_runtime: {runtime_jobs_failure}")
    if extra_degraded:
        doc = dict(doc)
        doc["degraded"] = sorted(list(doc["degraded"]) + extra_degraded)
    return doc


# ---------------------------------------------------------------------------
# discovery — candidate surfaces, zero ownership conferred
# ---------------------------------------------------------------------------

#: Fixed AppleScript source enumerating every open Chrome tab's URL + title,
#: tab-separated, one per line. Filtering to ChatGPT hosts happens
#: SERVER-SIDE in :func:`_chatgpt_tabs`, never inside the script. Returns an
#: empty string (never launches Chrome) when Chrome is not running — same
#: "check before touching the app" discipline as
#: ``integrations.chairman_surfaces.chatgpt.APPLESCRIPT_FOCUS``.
DISCOVER_TABS_APPLESCRIPT = """\
on run argv
    if application "Google Chrome" is not running then
        return ""
    end if
    set outputLines to {}
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                set end of outputLines to ((URL of t as string) & tab & (title of t as string))
            end repeat
        end repeat
    end tell
    set AppleScript's text item delimiters to linefeed
    set outputText to outputLines as string
    set AppleScript's text item delimiters to ""
    return outputText
end run
"""

#: Hosts a discovered ChatGPT tab may report — mirrors
#: ``integrations.chairman_surfaces.chatgpt._CHATGPT_HOSTS`` (repeated, not
#: imported, since that name is private to a different package and this is a
#: one-line constant, not shared validation logic).
_CHATGPT_DISCOVER_HOSTS = frozenset({"chatgpt.com", "chat.openai.com"})


def _discover_tabs_argv() -> list[str]:
    argv = ["osascript"]
    for line in DISCOVER_TABS_APPLESCRIPT.splitlines():
        argv.append("-e")
        argv.append(line)
    return argv


def _chatgpt_tabs(config: ServerConfig) -> list[dict[str, Any]]:
    result = config.runner(_discover_tabs_argv(), timeout=_DISCOVER_TABS_TIMEOUT)
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return []
    stdout = (result.get("stdout") or "").strip("\n")
    if not stdout:
        return []
    tabs: list[dict[str, Any]] = []
    for line in stdout.split("\n"):
        if "\t" not in line:
            continue
        url, _, title = line.partition("\t")
        host = (urlsplit(url).hostname or "").lower()
        if host in _CHATGPT_DISCOVER_HOSTS:
            tabs.append({"profile": None, "url": url, "title": title})
    return tabs


def _decode_claude_project_slug(slug: str) -> str:
    """Best-effort reverse of Claude Code's ``/`` -> ``-`` project-dir slug.

    Only trusted when the reconstructed path actually exists on disk;
    otherwise the raw slug is returned unchanged (frozen spec: "decode the
    slug to a path only if trivially derivable, else return the slug").
    """
    if slug.startswith("-"):
        candidate = slug.replace("-", "/")
        if Path(candidate).is_dir():
            return candidate
    return slug


def _claude_code_sessions() -> list[dict[str, Any]]:
    root = Path("~/.claude/projects").expanduser()
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    try:
        project_dirs = list(root.iterdir())
    except OSError:
        return []
    for project_dir in project_dirs:
        if not project_dir.is_dir():
            continue
        decoded = _decode_claude_project_slug(project_dir.name)
        try:
            jsonl_files = list(project_dir.glob("*.jsonl"))
        except OSError:
            continue
        for jsonl_file in jsonl_files:
            try:
                mtime = jsonl_file.stat().st_mtime
            except OSError:
                continue
            entries.append({
                "project_dir": decoded, "session_id": jsonl_file.stem, "mtime": mtime,
            })
    entries.sort(key=lambda e: e["mtime"], reverse=True)
    return entries[:_DISCOVER_CAP]


def _codex_sessions() -> list[dict[str, Any]]:
    root = Path("~/.codex/sessions").expanduser()
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    try:
        year_dirs = sorted((d for d in root.iterdir() if d.is_dir()), reverse=True)
    except OSError:
        return []
    for year_dir in year_dirs:
        try:
            month_dirs = sorted((d for d in year_dir.iterdir() if d.is_dir()), reverse=True)
        except OSError:
            continue
        for month_dir in month_dirs:
            try:
                day_dirs = sorted((d for d in month_dir.iterdir() if d.is_dir()), reverse=True)
            except OSError:
                continue
            for day_dir in day_dirs:
                date_str = f"{year_dir.name}-{month_dir.name}-{day_dir.name}"
                try:
                    files = sorted(day_dir.iterdir())
                except OSError:
                    continue
                for f in files:
                    if f.is_file():
                        entries.append({"session_id": f.stem, "date": date_str})
            if len(entries) >= _DISCOVER_CAP:
                break
        if len(entries) >= _DISCOVER_CAP:
            break
    return entries[:_DISCOVER_CAP]


def _discover_document(config: ServerConfig) -> dict[str, Any]:
    """Zero-write candidate-surface census. Confers zero ownership/binding."""
    profiles = chatgpt.list_profiles()
    chatgpt_profiles = [{"dir": d, "name": n} for d, n in sorted(profiles.items())]
    return {
        "chatgpt_profiles": chatgpt_profiles,
        "chatgpt_tabs": _chatgpt_tabs(config),
        "claude_code_sessions": _claude_code_sessions(),
        "codex_sessions": _codex_sessions(),
        "cursor": {
            "supported": False,
            "note": (
                "Cursor native thread discovery is not built in P0 (architecture "
                "§6.3/§21 Wave B); locate the thread in Cursor's own UI, then bind "
                "it manually."
            ),
        },
    }


# ---------------------------------------------------------------------------
# static assets — explicit closed map, never a filesystem path built from
# request input
# ---------------------------------------------------------------------------

def _static_assets(static_dir: Path) -> dict[str, tuple[Path, str]]:
    return {
        "index.html": (static_dir / "index.html", "text/html; charset=utf-8"),
        "control_room.js": (static_dir / "control_room.js", "application/javascript; charset=utf-8"),
        "control_room.css": (static_dir / "control_room.css", "text/css; charset=utf-8"),
    }


#: Fixed request-path -> static-asset-name map. A request path that is not a
#: literal key here NEVER reaches the filesystem via this route.
_STATIC_NAME_BY_PATH = {
    "/": "index.html",
    "/static/control_room.js": "control_room.js",
    "/static/control_room.css": "control_room.css",
}


# ---------------------------------------------------------------------------
# security gates
# ---------------------------------------------------------------------------

def _client_is_loopback(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def _host_allowed(host_header: str | None, port: int) -> bool:
    if not host_header:
        return False
    parsed = urlsplit("//" + host_header)
    hostname = (parsed.hostname or "").lower()
    if hostname not in _ALLOWED_HOSTNAMES:
        return False
    if parsed.port is not None and parsed.port != port:
        return False
    return True


# ---------------------------------------------------------------------------
# request handler
# ---------------------------------------------------------------------------

class ChairmanControlRoomHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ChairmanControlRoom/1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # local single-operator tool; keep stdout to the one startup line

    # -- shared response helpers -------------------------------------------------

    def _common_headers(self, *, content_type: str, length: int, csp: bool = False, no_store: bool = False) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        if csp:
            self.send_header("Content-Security-Policy", _CSP)
        if no_store:
            self.send_header("Cache-Control", "no-store")

    def _write(self, status: int, body: bytes, *, content_type: str, csp: bool = False, no_store: bool = False) -> None:
        try:
            self.send_response(status)
            self._common_headers(content_type=content_type, length=len(body), csp=csp, no_store=no_store)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, status: int, payload: Any, *, no_store: bool = False) -> None:
        self._write(status, json.dumps(payload).encode("utf-8"), content_type="application/json", no_store=no_store)

    def _forbidden(self, detail: str) -> None:
        self._send_json(403, {"error": "forbidden", "detail": detail}, no_store=True)

    def _not_found(self) -> None:
        self._send_json(404, {"error": "not_found"}, no_store=True)

    def _bad_request(self, detail: str) -> None:
        self._send_json(400, {"error": "bad_request", "detail": detail}, no_store=True)

    # -- security ------------------------------------------------------------

    def _loopback_and_host_ok(self) -> bool:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        if not _client_is_loopback(self.client_address[0]):
            self._forbidden("client address is not loopback")
            return False
        if not _host_allowed(self.headers.get("Host"), config.port):
            self._forbidden("Host header not allowed")
            return False
        return True

    def _post_auth_ok(self) -> bool:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        token = self.headers.get("X-CCR-Token")
        if token != config.token:
            self._forbidden("missing or invalid X-CCR-Token")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != config.origin:
            self._forbidden("Origin header does not match this server's own origin")
            return False
        return True

    def _read_json_body(self) -> tuple[dict | None, str | None]:
        length_header = self.headers.get("Content-Length")
        try:
            length = int(length_header) if length_header is not None else 0
        except ValueError:
            return None, "invalid Content-Length"
        if length < 0 or length > _MAX_BODY_BYTES:
            return None, "request body exceeds 64 KiB"
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}, None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, "request body is not valid JSON"
        if not isinstance(data, dict):
            return None, "request body must be a JSON object"
        return data, None

    # -- GET -------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if not self._loopback_and_host_ok():
            return
        path = urlsplit(self.path).path

        static_name = _STATIC_NAME_BY_PATH.get(path)
        if static_name == "index.html":
            return self._serve_index()
        if static_name is not None:
            return self._serve_static(static_name)
        if path == "/favicon.ico":
            self.send_response(204)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return
        if path == "/api/state":
            return self._handle_state()
        if path == "/api/discover":
            return self._handle_discover()
        self._not_found()

    def _serve_index(self) -> None:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        file_path, _mime = _static_assets(config.static_dir)["index.html"]
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            return self._not_found()
        body = content.replace("__CCR_TOKEN__", config.token).encode("utf-8")
        self._write(200, body, content_type="text/html; charset=utf-8", csp=True)

    def _serve_static(self, name: str) -> None:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        file_path, mime = _static_assets(config.static_dir)[name]
        try:
            body = file_path.read_bytes()
        except OSError:
            return self._not_found()
        self._write(200, body, content_type=mime)

    def _handle_state(self) -> None:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        doc = _compose_state_doc(config)
        body = {
            "control_room": doc,
            "capabilities": capability.census(runner=config.runner),
            "live_builds_active": config.live_cache.get("active_builds") is not None,
        }
        self._send_json(200, body, no_store=True)

    def _handle_discover(self) -> None:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        self._send_json(200, _discover_document(config), no_store=True)

    # -- POST ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        if not self._loopback_and_host_ok():
            return
        if not self._post_auth_ok():
            return
        path = urlsplit(self.path).path
        if path == "/api/open":
            return self._handle_open()
        if path == "/api/bind":
            return self._handle_bind()
        if path == "/api/unbind":
            return self._handle_unbind()
        if path == "/api/refresh-builds":
            return self._handle_refresh_builds()
        self._not_found()

    def _handle_open(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, {"binding_id"})
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")
        binding_id = data.get("binding_id")
        if not isinstance(binding_id, str) or not binding_id:
            return self._bad_request("binding_id: required (non-empty string)")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        doc, problems = sb.load_bindings(config.bindings_path)
        if doc is None:
            if problems:
                outcome = contract.refused(
                    "unknown", binding_id, "invalid_binding", "the bindings file failed validation"
                )
            else:
                outcome = contract.refused(
                    "unknown", binding_id, "not_found", "no bindings file is present"
                )
            return self._send_json(200, outcome, no_store=True)

        binding = next(
            (row for row in doc.get("bindings", []) if isinstance(row, dict) and row.get("binding_id") == binding_id),
            None,
        )
        if binding is None:
            outcome = contract.refused("unknown", binding_id, "not_found", "no binding with this id exists")
            return self._send_json(200, outcome, no_store=True)

        outcome = config.open_binding_fn(binding, config.runner)
        if outcome.get("ok"):
            now = config.now_fn()
            for row in doc["bindings"]:
                if isinstance(row, dict) and row.get("binding_id") == binding_id:
                    row["last_verified_at"] = now
            sb.save_bindings(doc, config.bindings_path)
        self._send_json(200, outcome, no_store=True)

    _BIND_ALLOWED_KEYS = frozenset({"work_ref", "role", "provider", "seat_ref", "locator"})

    def _handle_bind(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, self._BIND_ALLOWED_KEYS)
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")

        work_ref = data.get("work_ref")
        role = data.get("role")
        provider = data.get("provider")
        seat_ref = data.get("seat_ref")
        locator = data.get("locator")

        if not isinstance(work_ref, str) or not isinstance(role, str) or not isinstance(provider, str):
            return self._bad_request("work_ref, role, and provider must be strings")
        if not isinstance(locator, dict):
            return self._bad_request("locator must be an object")
        if seat_ref is not None and not isinstance(seat_ref, str):
            return self._bad_request("seat_ref must be a string or null")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        # sb._PROVIDER_LOCATOR_KIND is the same module's own provider->kind
        # map — reused, not re-derived, so a new provider added there never
        # needs a matching edit here. An unknown provider maps to itself,
        # which validate_bindings_document then names as a "must be one of"
        # problem — never a crash.
        locator_kind = sb._PROVIDER_LOCATOR_KIND.get(provider, provider)
        binding = sb.new_binding(
            work_ref=work_ref, role=role, provider=provider, locator_kind=locator_kind,
            locator=locator, observed_at=config.now_fn(), seat_ref=seat_ref,
        )

        existing_doc, load_problems = sb.load_bindings(config.bindings_path)
        if existing_doc is None and load_problems:
            return self._send_json(200, {"ok": False, "problems": load_problems}, no_store=True)
        if existing_doc is None:
            existing_doc = {"schema": sb.SCHEMA, "bindings": []}

        new_doc = {
            "schema": existing_doc.get("schema", sb.SCHEMA),
            "bindings": list(existing_doc.get("bindings", [])) + [binding],
        }
        problems = sb.validate_bindings_document(new_doc)
        if problems:
            return self._send_json(200, {"ok": False, "problems": problems}, no_store=True)

        sb.save_bindings(new_doc, config.bindings_path)
        self._send_json(200, {"ok": True, "binding_id": binding["binding_id"]}, no_store=True)

    def _handle_unbind(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, {"binding_id"})
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")
        binding_id = data.get("binding_id")
        if not isinstance(binding_id, str) or not binding_id:
            return self._bad_request("binding_id: required (non-empty string)")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        doc, _problems = sb.load_bindings(config.bindings_path)
        if doc is None:
            return self._send_json(200, {"ok": False}, no_store=True)

        rows = doc.get("bindings", [])
        remaining = [r for r in rows if not (isinstance(r, dict) and r.get("binding_id") == binding_id)]
        if len(remaining) == len(rows):
            return self._send_json(200, {"ok": False}, no_store=True)

        new_doc = {"schema": doc.get("schema", sb.SCHEMA), "bindings": remaining}
        sb.save_bindings(new_doc, config.bindings_path)
        self._send_json(200, {"ok": True}, no_store=True)

    def _handle_refresh_builds(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, set())
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        macro_root = config.macro_root
        if not macro_root:
            return self._send_json(200, {"ok": False, "detail": "no macro root resolved"}, no_store=True)

        script_path = Path(macro_root) / "scripts" / "build_project_active_build_map.py"
        if not script_path.is_file():
            return self._send_json(
                200,
                {"ok": False, "detail": "--json-stdout seam not present at macro root"},
                no_store=True,
            )

        argv = [sys.executable, str(script_path), "--json-stdout"]
        # 4 MiB, not the runner's default 64 KiB — the real project_active_
        # builds.v1 document is real organizational data (Wave D live proof:
        # 112,569 bytes) and must never be silently truncated below valid
        # JSON. See _REFRESH_BUILDS_MAX_OUTPUT_BYTES's docstring.
        result = config.runner(
            argv, timeout=_REFRESH_BUILDS_TIMEOUT, cwd=macro_root, max_bytes=_REFRESH_BUILDS_MAX_OUTPUT_BYTES
        )

        if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
            stderr_tail = ""
            if isinstance(result, dict):
                stderr_tail = (result.get("stderr") or "")[-2000:]
            detail = f"build_project_active_build_map.py failed: {stderr_tail}".rstrip(": ")
            return self._send_json(200, {"ok": False, "detail": detail}, no_store=True)

        stdout = result.get("stdout") or ""
        try:
            parsed = json.loads(stdout)
        except ValueError:
            return self._send_json(200, {"ok": False, "detail": "stdout was not valid JSON"}, no_store=True)
        if not isinstance(parsed, dict) or parsed.get("schema") != "project_active_builds.v1":
            return self._send_json(
                200, {"ok": False, "detail": "stdout schema was not project_active_builds.v1"}, no_store=True
            )

        config.live_cache["active_builds"] = parsed
        self._send_json(200, {"ok": True, "collected_at": parsed.get("collected_at")}, no_store=True)


class ControlRoomServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler_cls: type, config: ServerConfig) -> None:
        self.config = config
        super().__init__(server_address, handler_cls)


# ---------------------------------------------------------------------------
# --check mode
# ---------------------------------------------------------------------------

def run_check(config: ServerConfig) -> int:
    """Build one control-room document + capability census; print a compact
    summary (schema, counts, degraded list, capability states) with NO
    urls/session ids anywhere in the output. Always exits 0 — this is the
    operator smoke command, not a correctness gate.
    """
    doc = _compose_state_doc(config)
    capabilities = capability.census(runner=config.runner)

    print(f"schema: {doc['schema']}")
    print(f"generated_at: {doc['generated_at']}")
    print(f"work cards: {len(doc['work'])}")
    print(f"unjoined_open_prs: {len(doc['unjoined_open_prs'])}")
    print(f"unbound_surfaces: {len(doc['unbound_surfaces'])}")
    print(f"binding_conflicts: {len(doc['binding_conflicts'])}")
    attention = doc["attention"]
    print(
        "attention: chairman={0} ceo={1} coo={2}".format(
            len(attention.get("chairman", [])), len(attention.get("ceo", [])), len(attention.get("coo", []))
        )
    )
    if doc["degraded"]:
        print("degraded:")
        for entry in doc["degraded"]:
            print(f"  - {entry}")
    else:
        print("degraded: none")
    print("capabilities:")
    for name in sorted(capabilities):
        print(f"  {name}: {capabilities[name].get('state')}")
    return 0


# ---------------------------------------------------------------------------
# CLI / process lifecycle
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Chairman Control Room P0 — loopback-only local presentation "
            "process. No canonical writes; the only disk write anywhere in "
            "this process is the atomic surface-bindings save."
        ),
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    parser.add_argument("--repo-root", default=None, help="Mastermind checkout root (default: this repo)")
    parser.add_argument("--macro-root", default=None, help="Macro checkout root (default: auto-resolved)")
    parser.add_argument("--bindings-path", default=None, help="surface_bindings.json path (default: platform default)")
    parser.add_argument("--open", action="store_true", help="open the Control Room URL after startup")
    parser.add_argument("--check", action="store_true", help="build one document + capability census, print, exit 0")
    return parser


def _build_config(args: argparse.Namespace) -> ServerConfig:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else _REPO_ROOT
    macro_root = _resolve_macro_root_simple(args.macro_root, os.environ, repo_root)
    bindings_path = Path(args.bindings_path).expanduser() if args.bindings_path else None
    token = secrets.token_urlsafe(32)
    return ServerConfig(
        repo_root=repo_root,
        macro_root=macro_root,
        bindings_path=bindings_path,
        token=token,
        origin=f"http://{HOST}:{args.port}",
        port=args.port,
        static_dir=DEFAULT_STATIC_DIR,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = _build_config(args)

    if args.check:
        return run_check(config)

    httpd = ControlRoomServer((HOST, args.port), ChairmanControlRoomHandler, config)
    bound_ip, bound_port = httpd.server_address[0], httpd.server_address[1]
    assert ipaddress.ip_address(bound_ip).is_loopback, "refusing to serve on a non-loopback bind"

    config.port = bound_port
    config.origin = f"http://{HOST}:{bound_port}"
    url = f"http://{HOST}:{bound_port}/"
    print(f"{url} — loopback-only; no canonical writes; Ctrl-C to stop.")

    if args.open:
        try:
            subprocess.run(["/usr/bin/open", url], check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _sigint_handler(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
