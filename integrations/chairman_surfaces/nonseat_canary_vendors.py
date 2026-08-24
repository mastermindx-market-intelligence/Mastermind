"""Narrow secret-owning helper for the MAS-115 disposable non-seat canary.

The model-visible coordinator in :mod:`nonseat_canary` cannot read a live
credential or construct a live client.  A human operator invokes this module
directly.  This helper validates the provision and affirmative non-seat
binding census first; only then does it spawn the fixed Keychain command with
stdout wired directly into its own secret input through an anonymous OS pipe.
There is no eager external shell producer, captured stdout, or returned raw
value.  The helper then owns the credential, the single bounded HTTP client,
and the live matrix for the remainder of the process.

Refuses closed. Every path this module cannot prove against a documented
vendor surface raises :class:`~integrations.chairman_surfaces.
nonseat_canary.CanaryRefusal` rather than improvising. BUILT_NOT_PROVEN until
an operator provisions a disposable credential and profile and runs this
against them for real — no test in this repository ever calls a real vendor
endpoint.

The ONLY WebDriver operations used anywhere in this module are create a
session, navigate the selected page, enumerate/switch window handles, and
read the current URL.  There is structurally no pointer, keyboard, form,
script-evaluation, cookie, storage, download, or arbitrary-command surface.
"""
from __future__ import annotations

import argparse
import http.server
import importlib.util
import json
import os
import re
import secrets
import select
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from . import nonseat_canary as _core
#: Frozen official Multilogin X surfaces.  Launcher profile status/stop are
#: v1; profile start is v2; existence is proven by a bounded cloud folder
#: census rather than by launcher 404 (which is ambiguous after Agent restart).
_MLX_LAUNCHER_ORIGIN = "https://launcher.mlx.yt:45001"
_MLX_CLOUD_ORIGIN = "https://api.multilogin.com"
_MAX_RESPONSE_BYTES = 64 * 1024
# Keep each cloud-inventory response comfortably below the independent 64 KiB
# transport cap even when profile metadata is several KiB per row. The census
# remains complete and bounded by `_MAX_PROFILE_CENSUS`; only its page size is
# reduced.
_PROFILE_PAGE_SIZE = 10
_MAX_PROFILE_CENSUS = 1000
_MAX_STDIN_BYTES = 16 * 1024
_KEYCHAIN_READ_TIMEOUT_SECONDS = 15.0
_KEYCHAIN_WAIT_TIMEOUT_SECONDS = 2.0
_CLEANUP_PROCESS_TIMEOUT_SECONDS = 15.0
_CLEANUP_PROCESS_POLL_SECONDS = 0.1
_SECURITY_BIN = "/usr/bin/security"
_KEYCHAIN_SERVICE = "mastermind.mas115.multilogin.disposable"
_KEYCHAIN_ACCOUNT = "mastermind-mas115-canary"
_MLX_STATUS_DATA_KEYS = frozenset({
    "browser_type", "core_version", "folder_id", "in_use_by", "is_quick",
    "last_launched_at", "last_launched_by", "last_launched_on", "message",
    "name", "profile_id", "status", "timestamp", "workspace_id",
})

_USER_DATA_DIR_RE = re.compile(r"--user-data-dir=(\S+)")
_WEBDRIVER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_WEBDRIVER_MISSING = object()


# ---------------------------------------------------------------------------
# bounded HTTP transport
# ---------------------------------------------------------------------------


class _BoundedResponse:
    __slots__ = ("status_code", "payload")

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload


class BoundedHttpClient:
    """One fail-closed transport for cloud, launcher, and loopback calls.

    No caller can supply a URL or method.  Every public method below binds a
    fixed method/origin/path; redirects and ambient proxy/TLS environment are
    disabled at client construction; response bodies are capped before JSON
    parsing.  Dynamic transport errors and response bodies never escape.
    """

    def __init__(self, *, client=None):
        self._client = client if client is not None else httpx.Client(
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — cleanup cannot expand the error surface
            return

    def _request(self, method, origin, path, *, headers=None, params=None, json_body=None):
        chunks = []
        size = 0
        try:
            with self._client.stream(
                method, origin + path, headers=headers, params=params, json=json_body,
            ) as response:
                status_code = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        return None
                    chunks.append(chunk)
        except Exception:  # noqa: BLE001 — never echo a dynamic transport error
            return None
        try:
            payload = json.loads(b"".join(chunks)) if chunks else None
        except (UnicodeDecodeError, ValueError):
            return None
        return _BoundedResponse(status_code, payload)

    @staticmethod
    def _bearer(credential) -> dict:
        return {"Authorization": f"Bearer {credential.expose()}"}

    def _mlx_profile_search(self, credential, folder_id: str, *, offset: int):
        body = {
            "is_removed": False,
            "limit": _PROFILE_PAGE_SIZE,
            "offset": offset,
            "search_text": "",
            "storage_type": "all",
            "order_by": "created_at",
            "sort": "asc",
            "folder_id": folder_id,
        }
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, "/profile/search",
            headers=self._bearer(credential), json_body=body,
        )

    def _mlx_profile_status(self, credential, profile_id: str):
        path = "/api/v1/profile/status/p/" + quote(profile_id, safe="")
        return self._request("GET", _MLX_LAUNCHER_ORIGIN, path, headers=self._bearer(credential))

    def _mlx_profile_start(self, credential, folder_id: str, profile_id: str):
        path = (
            "/api/v2/profile/f/" + quote(folder_id, safe="")
            + "/p/" + quote(profile_id, safe="") + "/start"
        )
        return self._request(
            "GET", _MLX_LAUNCHER_ORIGIN, path,
            headers=self._bearer(credential),
            params={"automation_type": "selenium", "headless_mode": "false"},
        )

    def _mlx_profile_stop(self, credential, profile_id: str):
        path = "/api/v1/profile/stop/p/" + quote(profile_id, safe="")
        return self._request("GET", _MLX_LAUNCHER_ORIGIN, path, headers=self._bearer(credential))

    @staticmethod
    def _webdriver_origin(port: int):
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port <= 65535:
            return None
        return f"http://127.0.0.1:{port}"

    def _webdriver_create_session(self, port: int, browser_type: str):
        origin = self._webdriver_origin(port)
        browser_name = {"mimic": "chrome", "stealthfox": "firefox"}.get(browser_type)
        if origin is None or browser_name is None:
            return None
        always_match = {
            "acceptInsecureCerts": False,
            "browserName": browser_name,
            "pageLoadStrategy": "normal",
            "unhandledPromptBehavior": "dismiss and notify",
        }
        if browser_type == "mimic":
            always_match["goog:chromeOptions"] = {}
        else:
            always_match["moz:firefoxOptions"] = {}
        return self._request(
            "POST", origin, "/session",
            json_body={"capabilities": {"alwaysMatch": always_match, "firstMatch": [{}]}},
        )

    def _webdriver_session_address(self, port: int, session_id: str):
        origin = self._webdriver_origin(port)
        if origin is None or not isinstance(session_id, str) or not _WEBDRIVER_ID_RE.fullmatch(session_id):
            return None
        return origin, "/session/" + quote(session_id, safe="")

    def _webdriver_navigate(self, port: int, session_id: str, url: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None or not isinstance(url, str):
            return None
        origin, path = address
        return self._request("POST", origin, path + "/url", json_body={"url": url})

    def _webdriver_current_url(self, port: int, session_id: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None:
            return None
        origin, path = address
        return self._request("GET", origin, path + "/url")

    def _webdriver_current_window(self, port: int, session_id: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None:
            return None
        origin, path = address
        return self._request("GET", origin, path + "/window")

    def _webdriver_window_handles(self, port: int, session_id: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None:
            return None
        origin, path = address
        return self._request("GET", origin, path + "/window/handles")

    def _webdriver_switch_window(self, port: int, session_id: str, handle: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None or not isinstance(handle, str) or not _WEBDRIVER_ID_RE.fullmatch(handle):
            return None
        origin, path = address
        return self._request("POST", origin, path + "/window", json_body={"handle": handle})


# ---------------------------------------------------------------------------
# W3C WebDriver navigator — navigation and URL observation only
# ---------------------------------------------------------------------------


class WebDriverNavigator:
    """Public surface: list_pages, open_url. No other methods."""

    def __init__(self, client: BoundedHttpClient, provision: dict):
        self._client = client
        self._provision = provision
        self._sessions: dict[int, str] = {}

    @staticmethod
    def _valid_port(port) -> bool:
        return isinstance(port, int) and not isinstance(port, bool) and 0 < port <= 65535

    @staticmethod
    def _value(resp):
        if resp is None or resp.status_code != 200 or not isinstance(resp.payload, dict):
            return _WEBDRIVER_MISSING
        if set(resp.payload) != {"value"}:
            return _WEBDRIVER_MISSING
        return resp.payload.get("value")

    def _session_for(self, port: int):
        existing = self._sessions.get(port)
        if existing is not None:
            return existing
        resp = self._client._webdriver_create_session(port, self._provision.get("browser_type"))
        value = self._value(resp)
        if not isinstance(value, dict) or not {"sessionId", "capabilities"}.issubset(value):
            return None
        session_id = value.get("sessionId")
        capabilities = value.get("capabilities")
        expected = {"mimic": "chrome", "stealthfox": "firefox"}.get(
            self._provision.get("browser_type")
        )
        if (
            not isinstance(session_id, str)
            or not _WEBDRIVER_ID_RE.fullmatch(session_id)
            or not isinstance(capabilities, dict)
            or capabilities.get("browserName") != expected
        ):
            return None
        self._sessions[port] = session_id
        return session_id

    def _forget(self, port) -> None:
        if self._valid_port(port):
            self._sessions.pop(port, None)

    def list_pages(self, port) -> list:
        if not self._valid_port(port):
            return []
        session_id = self._sessions.get(port)
        if session_id is None:
            return []
        handles = self._value(
            self._client._webdriver_window_handles(port, session_id)
        )
        current = self._value(self._client._webdriver_current_window(port, session_id))
        if (
            not isinstance(handles, list)
            or not handles
            or not all(isinstance(handle, str) and _WEBDRIVER_ID_RE.fullmatch(handle) for handle in handles)
            or not isinstance(current, str)
            or current not in handles
        ):
            return []
        urls = []
        for handle in handles:
            switched = self._value(
                self._client._webdriver_switch_window(port, session_id, handle)
            )
            if switched is not None:
                return []
            current_url = self._value(
                self._client._webdriver_current_url(port, session_id)
            )
            if not isinstance(current_url, str):
                return []
            urls.append(current_url)
        restored = self._value(
            self._client._webdriver_switch_window(port, session_id, current)
        )
        return urls if restored is None else []

    def open_url(self, port, url: str) -> bool:
        if not self._valid_port(port) or not _core.allowed_url(self._provision, url):
            return False
        session_id = self._session_for(port)
        if session_id is None:
            return False
        value = self._value(
            self._client._webdriver_navigate(port, session_id, url)
        )
        return value is None


# ---------------------------------------------------------------------------
# Multilogin
# ---------------------------------------------------------------------------


class MultiloginClient:
    """Frozen Multilogin cloud/launcher contract; no prose inference."""

    def __init__(self, credential, client: BoundedHttpClient, *, browser_type: str = "mimic"):
        self._credential = credential
        self._client = client
        if browser_type not in ("mimic", "stealthfox"):
            raise _core.CanaryRefusal("PROVISION_MISSING")
        self._browser_type = browser_type
        #: profile_id we last started and have not since stopped/forgotten —
        #: profile-SCOPED ownership, not a client-wide boolean. ``None`` when
        #: we hold no profile.
        self._started_profile_id = None
        #: Exact teardown lease minted immediately before this client sends
        #: its one preflighted start request. Unlike operational owner state,
        #: it survives ambiguous responses and C5's simulated owner loss and
        #: cannot be redirected to a caller-supplied profile.
        self._cleanup_profile_ref = None

    def _require_credential(self) -> None:
        if not self._credential.present:
            raise _core.CanaryRefusal("AUTH_MISSING")

    @staticmethod
    def _safe_call(call):
        failed = False
        response = None
        try:
            response = call()
        except Exception:  # noqa: BLE001 — dynamic errors never cross the shell
            failed = True
        if failed:
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        return response

    @staticmethod
    def _valid_ref(profile_ref) -> bool:
        return (
            isinstance(profile_ref, dict)
            and isinstance(profile_ref.get("profile_id"), str)
            and bool(profile_ref.get("profile_id"))
            and isinstance(profile_ref.get("folder_id"), str)
            and bool(profile_ref.get("folder_id"))
        )

    @staticmethod
    def _successful_envelope(payload, *, profile_id=None, folder_id=None, expected_message=""):
        if not isinstance(payload, dict) or set(payload) != {"status", "data"}:
            return None
        status = payload.get("status")
        data = payload.get("data")
        if (
            not isinstance(status, dict)
            or set(status) != {"error_code", "http_code", "message"}
            or not isinstance(data, dict)
        ):
            return None
        if status.get("error_code") != "" or status.get("http_code") != 200:
            return None
        message = status.get("message")
        if not isinstance(message, str):
            return None
        # Multilogin Profile Search has changed this human-readable success
        # prose while retaining the documented success codes and exact data
        # contract.  ``None`` makes prose advisory for that one read-only
        # census surface; lifecycle and launch responses remain exact.
        if expected_message is not None and message != expected_message:
            return None
        if profile_id is not None and data.get("profile_id") != profile_id:
            return None
        if folder_id is not None and data.get("folder_id") != folder_id:
            return None
        return data

    def _profile_state(self, profile_ref: dict) -> str:
        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        profile_id = profile_ref["profile_id"]
        folder_id = profile_ref["folder_id"]
        resp = self._safe_call(lambda: self._client._mlx_profile_status(self._credential, profile_id))
        if resp is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code != 200:
            # Launcher 404 can mean its Agent restarted and lost the session
            # table; it is never evidence that the profile is closed.
            raise _core.CanaryRefusal("VENDOR_ERROR")
        data = self._successful_envelope(
            resp.payload, profile_id=profile_id, folder_id=folder_id,
        )
        if (
            data is None
            or set(data) != _MLX_STATUS_DATA_KEYS
            or data.get("browser_type") != self._browser_type
            or not isinstance(data.get("core_version"), int)
            or isinstance(data.get("core_version"), bool)
            or data.get("core_version") <= 0
            or not isinstance(data.get("in_use_by"), str)
            or not isinstance(data.get("is_quick"), bool)
            or not all(isinstance(data.get(key), str) for key in (
                "last_launched_at", "last_launched_by", "last_launched_on",
                "message", "name", "workspace_id",
            ))
            or not isinstance(data.get("timestamp"), int)
            or isinstance(data.get("timestamp"), bool)
            or data.get("timestamp") <= 0
        ):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        state = data.get("status")
        if state not in ("browser_running", "stopped"):
            # Includes transitional/error states and every renamed state.
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if state == "stopped" and data.get("in_use_by") != "":
            # A closed lifecycle state paired with a claimed Agent owner is
            # contradictory.  Contradiction is uncertainty, not permission.
            raise _core.CanaryRefusal("VENDOR_ERROR")
        return state

    def start(self, profile_ref: dict) -> dict:
        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        profile_id = profile_ref.get("profile_id")
        folder_id = profile_ref.get("folder_id")
        if self._started_profile_id is not None or self._cleanup_profile_ref is not None:
            raise _core.CanaryRefusal("BUSY_PROFILE")

        # Direct callers cannot bypass the actuator's preflight: exact cloud
        # identity and exact launcher-closed state are re-proven immediately
        # before the only launch request.
        profile = self._profile_inventory_item(profile_ref)
        if profile is None:
            raise _core.CanaryRefusal("PROFILE_NOT_FOUND")
        if profile.get("browser_type") != self._browser_type:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        # The cloud census must positively say that no other vendor session
        # owns or locks this profile.  Missing or renamed ownership fields are
        # uncertainty, never permission to launch.
        if profile.get("in_use_by") != "":
            if isinstance(profile.get("in_use_by"), str) and profile.get("in_use_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if "locked_by" in profile and profile.get("locked_by") != "":
            if isinstance(profile.get("locked_by"), str) and profile.get("locked_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        state = self._profile_state(profile_ref)
        if state != "stopped":
            raise _core.CanaryRefusal("BUSY_PROFILE")

        # Once the request is sent, the effect can be ambiguous even if the
        # transport/response is lost or malformed. Retain one exact-profile
        # cleanup lease before the request; clear it only for definitive
        # no-effect auth/not-found responses.
        self._cleanup_profile_ref = dict(profile_ref)
        resp = self._safe_call(
            lambda: self._client._mlx_profile_start(self._credential, folder_id, profile_id),
        )
        if resp is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if resp.status_code in (401, 403):
            self._cleanup_profile_ref = None
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code == 404:
            self._cleanup_profile_ref = None
            raise _core.CanaryRefusal("PROFILE_NOT_FOUND")
        if resp.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        data = self._successful_envelope(
            resp.payload, expected_message="Profile started successfully",
        )
        if (
            data is None
            or set(data) != {"browser_type", "core_version", "id", "is_quick", "port"}
            or data.get("id") != profile_id
            or data.get("browser_type") != self._browser_type
            or not isinstance(data.get("core_version"), int)
            or isinstance(data.get("core_version"), bool)
            or data.get("core_version") <= 0
            or data.get("is_quick") is not False
        ):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        raw_port = data.get("port")
        if isinstance(raw_port, str) and raw_port.isascii() and raw_port.isdigit():
            port = int(raw_port)
        elif isinstance(raw_port, int) and not isinstance(raw_port, bool):
            port = raw_port
        else:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if not 0 < port <= 65535:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        self._started_profile_id = profile_id
        return {"profile_id": profile_id, "port": port}

    def _stop_cleanup_ref(self, profile_ref: dict) -> None:
        profile_id = profile_ref["profile_id"]
        resp = self._safe_call(lambda: self._client._mlx_profile_stop(self._credential, profile_id))
        if resp is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        payload = resp.payload
        if not isinstance(payload, dict) or set(payload) != {"status"}:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        status = payload.get("status")
        if (
            not isinstance(status, dict)
            or set(status) != {"error_code", "http_code", "message"}
            or status.get("error_code") != ""
            or status.get("http_code") != 200
            or status.get("message") != ""
        ):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        self._started_profile_id = None
        self._cleanup_profile_ref = None

    def stop(self, profile_ref: dict) -> None:
        self._require_credential()
        if (
            not self._valid_ref(profile_ref)
            or self._started_profile_id != profile_ref.get("profile_id")
            or self._cleanup_profile_ref != profile_ref
        ):
            raise _core.CanaryRefusal("UNOWNED_RUNNING_PROFILE")
        self._stop_cleanup_ref(profile_ref)

    def _cleanup_started_profile(self) -> bool:
        """Stop only the exact profile targeted by this client's start request."""
        self._require_credential()
        profile_ref = self._cleanup_profile_ref
        if profile_ref is None:
            return False
        self._stop_cleanup_ref(profile_ref)
        return True

    def forget_ownership(self) -> None:
        """Forget operational ownership only; never call the vendor.

        The private exact-profile teardown lease remains so the outer canary
        boundary can still contain C5 and early matrix failures.
        """
        self._started_profile_id = None

    def _profile_inventory_item(self, profile_ref: dict):
        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        target_id = profile_ref["profile_id"]
        folder_id = profile_ref["folder_id"]
        offset = 0
        expected_total = None
        seen_ids = set()
        found = None
        while offset < _MAX_PROFILE_CENSUS:
            resp = self._safe_call(
                lambda: self._client._mlx_profile_search(self._credential, folder_id, offset=offset),
            )
            if resp is None:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if resp.status_code in (401, 403):
                raise _core.CanaryRefusal("AUTH_EXPIRED")
            if resp.status_code != 200:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            data = self._successful_envelope(resp.payload, expected_message=None)
            if data is None or set(data) != {"profiles", "total_count"}:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            profiles = data.get("profiles")
            total = data.get("total_count")
            if not isinstance(profiles, list) or not isinstance(total, int) or isinstance(total, bool):
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if total < 0 or total > _MAX_PROFILE_CENSUS:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if expected_total is None:
                expected_total = total
            if total != expected_total or len(profiles) > _PROFILE_PAGE_SIZE:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            for item in profiles:
                if not isinstance(item, dict) or not {"id", "folder_id"}.issubset(item):
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                item_id = item.get("id")
                item_folder = item.get("folder_id")
                if not isinstance(item_id, str) or not isinstance(item_folder, str):
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                if item_id in seen_ids:
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                seen_ids.add(item_id)
                if item_id == target_id:
                    if item_folder != folder_id:
                        raise _core.CanaryRefusal("VENDOR_ERROR")
                    found = dict(item)
            offset += len(profiles)
            if offset == total:
                return found
            if not profiles or offset > total:
                raise _core.CanaryRefusal("VENDOR_ERROR")
        raise _core.CanaryRefusal("VENDOR_ERROR")

    def profile_exists(self, profile_ref: dict) -> bool:
        return self._profile_inventory_item(profile_ref) is not None

    def is_running_externally(self, profile_ref: dict) -> bool:
        state = self._profile_state(profile_ref)
        if state == "stopped":
            return False
        return self._started_profile_id != profile_ref.get("profile_id")


# ---------------------------------------------------------------------------
# GoLogin
# ---------------------------------------------------------------------------


class GoLoginClient:
    """GoLogin shell. The official lifecycle is SDK-owned (the "gologin"
    package on PyPI/npm); this repository does not depend on that SDK, so
    every method refuses UNSUPPORTED_SURFACE — never an unofficial REST
    lifecycle or partial existence improvisation."""

    PINNED_GOLOGIN_SDK = "gologin"
    PINNED_GOLOGIN_SDK_VERSION = "not-installed-unpinned"

    def __init__(self, credential, client=None):
        self._credential = credential
        self._client = client

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

    def _cleanup_started_profile(self) -> bool:
        return False

    def profile_exists(self, profile_ref: dict) -> bool:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")


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

    # PUT is unused by the benign origin itself. Preserve a closed response
    # if an old inert harness sends the former DevTools-shaped method.
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


def _settled_cleanup_probe(
    process_probe, *, monotonic=time.monotonic, sleep=time.sleep,
    timeout_seconds=_CLEANUP_PROCESS_TIMEOUT_SECONDS,
):
    """Wait boundedly for the exact disposable process group to disappear."""
    def _probe():
        deadline = monotonic() + timeout_seconds
        latest = process_probe()
        while (
            isinstance(latest, dict)
            and isinstance(latest.get("this_profile"), int)
            and not isinstance(latest.get("this_profile"), bool)
            and latest.get("this_profile") > 0
            and monotonic() < deadline
        ):
            sleep(_CLEANUP_PROCESS_POLL_SECONDS)
            latest = process_probe()
        return latest

    return _probe


# ---------------------------------------------------------------------------
# operator-only secret pipe + entrypoint
# ---------------------------------------------------------------------------


class _KeychainCredentialPipe:
    """One bounded anonymous pipe from fixed Keychain stdout to this helper.

    The producer is started by ``posix_spawn`` file actions, not a process
    wrapper carrying stdout: fd 1 is the pipe's integer write FD, while this
    object owns only the read FD.  Dynamic child errors and output never cross
    the helper's closed result boundary.
    """

    __slots__ = ("_fd", "_pid", "_waitpid", "_kill")

    def __init__(self, read_fd: int, pid: int, *, waitpid=os.waitpid, kill=os.kill):
        self._fd = read_fd
        self._pid = pid
        self._waitpid = waitpid
        self._kill = kill

    def read(self, limit: int):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            return b""
        deadline = time.monotonic() + _KEYCHAIN_READ_TIMEOUT_SECONDS
        chunks = []
        remaining = limit
        while remaining > 0:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                return b""
            try:
                ready, _, _ = select.select([self._fd], [], [], timeout)
            except Exception:  # noqa: BLE001 — fixed absent result only
                return b""
            if not ready:
                return b""
            try:
                chunk = os.read(self._fd, min(4096, remaining))
            except OSError:
                return b""
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _wait_until(self, deadline: float) -> bool:
        while True:
            try:
                waited_pid, _status = self._waitpid(self._pid, os.WNOHANG)
            except ChildProcessError:
                return True
            except Exception:  # noqa: BLE001 — cleanup remains fixed and bounded
                return False
            if waited_pid == self._pid:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass
        if self._wait_until(time.monotonic() + _KEYCHAIN_WAIT_TIMEOUT_SECONDS):
            return
        try:
            self._kill(self._pid, signal.SIGTERM)
        except Exception:  # noqa: BLE001 — cleanup of our fixed child only
            pass
        if self._wait_until(time.monotonic() + _KEYCHAIN_WAIT_TIMEOUT_SECONDS):
            return
        try:
            self._kill(self._pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001 — never expand the result surface
            pass
        self._wait_until(time.monotonic() + _KEYCHAIN_WAIT_TIMEOUT_SECONDS)


def _open_keychain_credential_pipe(*, spawn=os.posix_spawn, waitpid=os.waitpid, kill=os.kill):
    """Open the fixed Keychain producer only after the caller's preflights.

    The secret producer's stdout is an anonymous integer FD, never the
    library's captured-pipe sentinel and never a returned stdout value.
    """
    read_fd, write_fd = os.pipe()
    argv = [
        _SECURITY_BIN, "find-generic-password", "-w",
        "-s", _KEYCHAIN_SERVICE, "-a", _KEYCHAIN_ACCOUNT,
    ]
    try:
        pid = spawn(
            _SECURITY_BIN,
            argv,
            {},
            file_actions=[
                (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                (os.POSIX_SPAWN_DUP2, write_fd, 1),
                (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0),
                (os.POSIX_SPAWN_CLOSE, read_fd),
                (os.POSIX_SPAWN_CLOSE, write_fd),
            ],
        )
    except Exception:  # noqa: BLE001 — dynamic spawn errors never escape
        try:
            os.close(read_fd)
        except OSError:
            pass
        raise _core.CanaryRefusal("AUTH_MISSING") from None
    finally:
        try:
            os.close(write_fd)
        except OSError:
            pass
    return _KeychainCredentialPipe(read_fd, pid, waitpid=waitpid, kill=kill)


def _read_direct_pipe_credential(stream) -> _core.Credential:
    """Read one bounded anonymous-pipe credential into this helper's holder.

    The raw value is never returned: the only successful return is the
    redacting :class:`Credential` object.  Callers must run every non-secret
    preflight before invoking this function.
    """
    source = getattr(stream, "buffer", stream)
    try:
        raw = source.read(_MAX_STDIN_BYTES + 1)
    except Exception:  # noqa: BLE001 — pipe failure has one fixed refusal
        return _core.Credential(None, "absent")
    if isinstance(raw, bytes):
        if len(raw) > _MAX_STDIN_BYTES:
            return _core.Credential(None, "absent")
        try:
            value = raw.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            return _core.Credential(None, "absent")
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > _MAX_STDIN_BYTES:
            return _core.Credential(None, "absent")
        value = raw.strip()
    else:
        return _core.Credential(None, "absent")
    return _core.Credential(value, "stdin") if value else _core.Credential(None, "absent")


def _emit_refusal(out, vendor: str, code: str) -> int:
    print(json.dumps(_core._refused_payload(vendor, code), indent=2, sort_keys=True), file=out)
    return 2


def main(
    argv=None, *, stdout=None, bindings_loader=None, credential_stream_factory=None,
    client_factory=BoundedHttpClient, origin_factory=LoopbackBenignOrigin,
    now=None,
) -> int:
    """Run the operator-only helper.

    ``credential_stream_factory`` is a hermetic test seam.  The CLI/live path
    cannot set it and always uses the fixed post-preflight Keychain pipe.
    No repository test calls a real credential store or vendor endpoint.
    """
    parser = argparse.ArgumentParser(prog="nonseat_canary_vendors")
    parser.add_argument("--vendor", required=True, choices=("gologin", "multilogin"))
    parser.add_argument("--provision-path", required=True)
    args = parser.parse_args(argv)
    out = stdout if stdout is not None else sys.stdout

    # GoLogin stays completely unsupported until a pinned SDK contract is
    # separately accepted.  Refuse before provision I/O, Keychain, HTTP, browser,
    # origin, or process inspection.
    if args.vendor != "multilogin":
        return _emit_refusal(out, args.vendor, "UNSUPPORTED_SURFACE")

    reference_time = now if now is not None else datetime.now(timezone.utc)
    provision, code = _core.load_provision(
        args.provision_path, bindings_loader=bindings_loader, now=reference_time,
    )
    if provision is None:
        return _emit_refusal(out, args.vendor, code)
    if provision.get("vendor") != args.vendor:
        return _emit_refusal(out, args.vendor, "PROVISION_MISSING")

    # This is intentionally after every provision and non-seat-collision
    # preflight.  A refusal above cannot spawn/read Keychain or construct any
    # live HTTP/browser/origin object.  Production has no external-stdin path:
    # that would let an eager ``security | helper`` producer run too early.
    credential_stream = None
    try:
        factory = credential_stream_factory or _open_keychain_credential_pipe
        credential_stream = factory()
        credential = _read_direct_pipe_credential(credential_stream)
    except _core.CanaryRefusal as refusal:
        return _emit_refusal(out, args.vendor, refusal.code)
    except Exception:  # noqa: BLE001 — fixed absence result only
        return _emit_refusal(out, args.vendor, "AUTH_MISSING")
    finally:
        if credential_stream is not None:
            try:
                credential_stream.close()
            except Exception:  # noqa: BLE001 — fixed cleanup boundary
                pass
    if not credential.present:
        return _emit_refusal(out, args.vendor, "AUTH_MISSING")

    client = None
    origin = None
    try:
        client = client_factory()
        token = "mas115-live-" + secrets.token_hex(16)
        origin = origin_factory(token=token)
        live_provision = dict(provision)
        live_provision["benign_origin"] = origin.base_url
        vendor_client = MultiloginClient(
            credential, client, browser_type=live_provision["browser_type"],
        )
        navigator = WebDriverNavigator(client, live_provision)

        def _clock() -> str:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        process_probe = live_process_probe(live_provision)
        receipts = _core.run_matrix(
            vendor_client=vendor_client,
            navigator=navigator,
            provision=live_provision,
            credential=credential,
            process_probe=process_probe,
            origin_probe=origin,
            clock=_clock,
            canary_token=token,
            cleanup_probe=_settled_cleanup_probe(process_probe),
        )
    except _core.CanaryRefusal as refusal:
        return _emit_refusal(out, args.vendor, refusal.code)
    except Exception:  # noqa: BLE001 — never echo a dynamic error or payload
        return _emit_refusal(out, args.vendor, "VENDOR_ERROR")
    finally:
        if origin is not None:
            try:
                origin.close()
            except Exception:  # noqa: BLE001 — fixed cleanup boundary
                pass
        if client is not None:
            client.close()

    print(json.dumps(receipts, indent=2, sort_keys=True), file=out)
    return 0 if receipts.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
