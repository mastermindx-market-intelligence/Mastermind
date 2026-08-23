"""integrations.chairman_surfaces.nonseat_canary_vendors — live vendor shells.

Live counterparts to :mod:`integrations.chairman_surfaces.nonseat_canary`'s
hermetic fakes: a keychain credential reader, a DevTools-HTTP navigator, the
GoLogin/Multilogin lifecycle shells, a benign loopback origin server for the
canary's own navigation targets, and a live process probe. Every endpoint
constant cites the documented vendor surface it addresses.

Refuses closed. Every path this module cannot prove against a documented
vendor surface raises :class:`~integrations.chairman_surfaces.
nonseat_canary.CanaryRefusal` rather than improvising. BUILT_NOT_PROVEN until
an operator provisions a disposable credential and profile and runs this
against them for real — no test in this repository ever calls a real vendor
endpoint.

The ONLY DevTools verbs used anywhere in this module are the version/list/new
endpoints (and here, only list/new — :class:`DevToolsNavigator` never even
calls ``/json/version``): there is structurally no pointer, keyboard, or
script evaluation surface reachable through this module.
"""
from __future__ import annotations

import http.server
import importlib.util
import re
import threading

import httpx

from . import nonseat_canary as _core
from . import runner as _runner_module

#: Official Multilogin X local launcher API (multilogin.com/help "API basics
#: — key terms & concepts"; "Learn CLI commands").
_LAUNCHER_V2 = "https://launcher.mlx.yt:45001/api/v2"

#: Official GoLogin REST profile-status endpoint (api.gologin.com/docs-json).
_GOLOGIN_API_BASE = "https://api.gologin.com"

_USER_DATA_DIR_RE = re.compile(r"--user-data-dir=(\S+)")


# ---------------------------------------------------------------------------
# keychain
# ---------------------------------------------------------------------------


def keychain_credential_reader(vendor: str, run=None):
    """Build a zero-arg callable reading the disposable canary credential
    from the macOS keychain. Never logs/prints; argv carries only service
    labels, never the secret."""
    runner = run if run is not None else _runner_module.run_argv
    service = _core.KEYCHAIN_SERVICE_TEMPLATE.format(vendor=vendor)

    def _read():
        argv = [
            _core.SECURITY_BIN, "find-generic-password", "-w",
            "-s", service, "-a", _core.KEYCHAIN_ACCOUNT,
        ]
        try:
            result = runner(argv, timeout=5.0)
        except Exception:  # noqa: BLE001 — a probe failure must never propagate
            return None
        if not isinstance(result, dict) or result.get("code") != 0:
            return None
        stdout = result.get("stdout")
        if not isinstance(stdout, str):
            return None
        stripped = stdout.strip()
        return stripped or None

    return _read


# ---------------------------------------------------------------------------
# DevTools navigator — list/new only
# ---------------------------------------------------------------------------


class DevToolsNavigator:
    """Public surface: list_pages, open_url. No other methods."""

    def list_pages(self, port) -> list:
        try:
            resp = httpx.get(f"http://127.0.0.1:{port}/json/list", timeout=5.0)
        except httpx.HTTPError:
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []
        if not isinstance(data, list):
            return []
        return [
            item.get("url") for item in data
            if isinstance(item, dict) and item.get("type") == "page" and isinstance(item.get("url"), str)
        ]

    def open_url(self, port, url: str) -> bool:
        endpoint = f"http://127.0.0.1:{port}/json/new"
        try:
            resp = httpx.put(endpoint, params={"url": url}, timeout=10.0)
        except httpx.HTTPError:
            return False
        if resp.status_code == 405:
            try:
                resp = httpx.get(endpoint, params={"url": url}, timeout=10.0)
            except httpx.HTTPError:
                return False
        return resp.status_code == 200


# ---------------------------------------------------------------------------
# Multilogin
# ---------------------------------------------------------------------------


class MultiloginClient:
    """Multilogin X launcher shell. Credential absent -> AUTH_MISSING before
    any HTTP. No retries; timeout 10.0."""

    LAUNCHER_V2 = _LAUNCHER_V2

    def __init__(self, credential):
        self._credential = credential
        #: profile_id we last started and have not since stopped/forgotten —
        #: profile-SCOPED ownership, not a client-wide boolean. ``None`` when
        #: we hold no profile.
        self._started_profile_id = None

    def _require_credential(self) -> None:
        if not self._credential.present:
            raise _core.CanaryRefusal("AUTH_MISSING")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._credential.expose()}"}

    def start(self, profile_ref: dict) -> dict:
        self._require_credential()
        profile_id = profile_ref.get("profile_id")
        if self._started_profile_id == profile_id:
            # Identity-echo second-order repeat-start: we already hold this
            # exact profile — refuse BEFORE any HTTP, never re-ask the vendor.
            raise _core.CanaryRefusal("BUSY_PROFILE")
        folder_id = profile_ref.get("folder_id")
        url = f"{self.LAUNCHER_V2}/profile/f/{folder_id}/p/{profile_id}/start"
        transport_error = False
        resp = None
        try:
            resp = httpx.get(url, params={"automation_type": "puppeteer"}, headers=self._headers(), timeout=10.0)
        except Exception:  # noqa: BLE001 — refuse closed on ANY transport failure, not just httpx.HTTPError
            transport_error = True
        if transport_error:
            # Raised OUTSIDE the except block so CPython never auto-chains
            # the transport exception onto __context__ (see nonseat_canary.
            # NonSeatCanaryActuator.acquire() for the same pattern).
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code == 404:
            raise _core.CanaryRefusal("PROFILE_NOT_FOUND")
        if resp.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        try:
            payload = resp.json()
        except ValueError:
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        if not isinstance(payload, dict):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        status = payload.get("status")
        if isinstance(status, dict) and "already" in str(status.get("message", "")).lower():
            raise _core.CanaryRefusal("BUSY_PROFILE")
        port = payload.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        self._started_profile_id = profile_id
        return {"profile_id": profile_id, "port": port}

    def stop(self, profile_ref: dict) -> None:
        self._require_credential()
        folder_id = profile_ref.get("folder_id")
        profile_id = profile_ref.get("profile_id")
        url = f"{self.LAUNCHER_V2}/profile/f/{folder_id}/p/{profile_id}/stop"
        transport_error = False
        resp = None
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=10.0)
        except Exception:  # noqa: BLE001 — refuse closed on ANY transport failure
            transport_error = True
        if transport_error:
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code not in (200, 404):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        self._started_profile_id = None

    def forget_ownership(self) -> None:
        """Owner-loss simulation hook: forget our own started-profile
        bookkeeping. Never calls the vendor."""
        self._started_profile_id = None

    def _status(self, profile_ref: dict):
        self._require_credential()
        folder_id = profile_ref.get("folder_id")
        profile_id = profile_ref.get("profile_id")
        url = f"{self.LAUNCHER_V2}/profile/f/{folder_id}/p/{profile_id}/status"
        transport_error = False
        resp = None
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=10.0)
        except Exception:  # noqa: BLE001 — refuse closed on ANY transport failure
            transport_error = True
        if transport_error:
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        return resp

    def profile_exists(self, profile_ref: dict) -> bool:
        resp = self._status(profile_ref)
        if resp.status_code == 404:
            return False
        if resp.status_code == 200:
            return True
        raise _core.CanaryRefusal("VENDOR_ERROR")

    def is_running_externally(self, profile_ref: dict) -> bool:
        resp = self._status(profile_ref)
        if resp.status_code == 404:
            return False
        if resp.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        try:
            payload = resp.json()
        except ValueError:
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        active = bool(isinstance(payload, dict) and payload.get("active"))
        return active and self._started_profile_id != profile_ref.get("profile_id")


# ---------------------------------------------------------------------------
# GoLogin
# ---------------------------------------------------------------------------


class GoLoginClient:
    """GoLogin shell. The official lifecycle is SDK-owned (the "gologin"
    package on PyPI/npm); this repository does not depend on that SDK, so
    start/stop/is_running_externally always refuse UNSUPPORTED_SURFACE —
    never an unofficial REST-start improvisation. profile_exists uses
    GoLogin's documented REST profile-status endpoint, which is independent
    of the SDK-owned lifecycle."""

    PINNED_GOLOGIN_SDK = "gologin"
    PINNED_GOLOGIN_SDK_VERSION = "not-installed-unpinned"

    def __init__(self, credential):
        self._credential = credential

    @staticmethod
    def _sdk_available() -> bool:
        try:
            return importlib.util.find_spec(GoLoginClient.PINNED_GOLOGIN_SDK) is not None
        except (ImportError, ValueError):
            return False

    def start(self, profile_ref: dict) -> dict:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")

    def stop(self, profile_ref: dict) -> None:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")

    def is_running_externally(self, profile_ref: dict) -> bool:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")

    def forget_ownership(self) -> None:
        """No-op: GoLoginClient never starts/stops anything (see class
        docstring), so it has no started-profile bookkeeping to forget.
        Exists only for uniform shape with MultiloginClient."""
        return None

    def profile_exists(self, profile_ref: dict) -> bool:
        if not self._credential.present:
            raise _core.CanaryRefusal("AUTH_MISSING")
        profile_id = profile_ref.get("profile_id")
        transport_error = False
        resp = None
        try:
            resp = httpx.get(
                f"{_GOLOGIN_API_BASE}/browser/{profile_id}",
                headers={"Authorization": f"Bearer {self._credential.expose()}"},
                timeout=10.0,
            )
        except Exception:  # noqa: BLE001 — refuse closed on ANY transport failure
            transport_error = True
        if transport_error:
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code == 404:
            return False
        if resp.status_code == 200:
            return True
        raise _core.CanaryRefusal("VENDOR_ERROR")


# ---------------------------------------------------------------------------
# benign loopback origin
# ---------------------------------------------------------------------------


class _CanaryRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format_str, *args) -> None:  # noqa: A002 — stdlib signature
        return

    def _origin(self) -> "LoopbackBenignOrigin":
        return self.server.canary_origin  # type: ignore[attr-defined]

    def _respond(self, status: int, body: bytes, extra_headers=None) -> None:
        self.send_response(status)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — stdlib method name
        origin = self._origin()
        path = self.path.split("?", 1)[0]
        origin._record(path)

        if path in ("/a", "/b"):
            self._respond(200, b"ok")
            return
        if path == "/state/set":
            self._respond(200, b"ok", {"Set-Cookie": f"mas115_canary={origin.token}; Path=/"})
            return
        if path == "/state/check":
            cookie_header = self.headers.get("Cookie", "") or ""
            if f"mas115_canary={origin.token}" in cookie_header:
                origin._mark_cookie_seen()
            self._respond(200, b"ok")
            return
        if path == "/auth":
            self._respond(401, b"unauthorized", {"WWW-Authenticate": 'Basic realm="mas115-canary"'})
            return
        self._respond(404, b"not found")

    # PUT is unused by the benign origin itself, but present so a stray
    # DevTools-shaped PUT never falls through to the base class's 501.
    do_PUT = do_GET  # noqa: N815


class LoopbackBenignOrigin:
    """Stdlib ``ThreadingHTTPServer`` serving only the five canary paths."""

    def __init__(self, token: str = "mas115-loopback-token"):
        self.token = token
        self._seen_paths: set = set()
        self._cookie_seen = False
        self._lock = threading.Lock()
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CanaryRequestHandler)
        self._server.canary_origin = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def _record(self, path: str) -> None:
        with self._lock:
            self._seen_paths.add(path)

    def _mark_cookie_seen(self) -> None:
        with self._lock:
            self._cookie_seen = True

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def saw(self, path: str) -> bool:
        with self._lock:
            return path in self._seen_paths

    def cookie_seen(self, token: str) -> bool:
        with self._lock:
            return self._cookie_seen and token == self.token

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ---------------------------------------------------------------------------
# live process probe
# ---------------------------------------------------------------------------


def _matches_this_profile(parts: list, vendor: str, folder_id, profile_id) -> bool:
    if vendor == "multilogin":
        return len(parts) >= 2 and parts[-2] == folder_id and parts[-1] == profile_id
    if vendor == "gologin":
        return profile_id in parts
    return False


def live_process_probe(provision: dict):
    """Build a zero-arg process probe -> ``{"this_profile": int, "other_profiles": int}``.

    Raw process-argument lines never leave this function — only the two
    integer counts are returned (ARGV-PRIVACY LAW, see
    :mod:`integrations.chairman_surfaces.chatgpt`)."""
    from integrations.chairman_surfaces import chatgpt as _chatgpt

    vendor = provision.get("vendor")
    profile_id = provision.get("profile_id")
    folder_id = provision.get("folder_id")

    def _probe() -> dict:
        try:
            lines = _chatgpt._default_process_args_reader()
        except Exception:  # noqa: BLE001 — a probe failure must never propagate
            lines = []
        if not isinstance(lines, list):
            lines = []

        this_profile = 0
        other_profiles = 0
        for line in lines:
            if not isinstance(line, str):
                continue
            match = _USER_DATA_DIR_RE.search(line)
            if not match:
                continue
            raw_path = match.group(1)
            parts = [part for part in raw_path.split("/") if part]
            if _matches_this_profile(parts, vendor, folder_id, profile_id):
                this_profile += 1
                continue
            if "/mlx/profiles/" in raw_path or "/GoLogin/profiles/" in raw_path:
                other_profiles += 1

        return {"this_profile": this_profile, "other_profiles": other_profiles}

    return _probe
