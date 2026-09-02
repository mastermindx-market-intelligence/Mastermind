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
import http.client
import http.server
import importlib.util
import json
import os
import re
import secrets
import select
import signal
import stat
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from . import nonseat_canary as _core
from . import mas115_multilogin_port_policy as _port_policy
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
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

# ---------------------------------------------------------------------------
# REALM1-C1 — MAS-115 one-profile Multilogin peer create/reconcile/remove
# (Mastermind #385). See docs/CHAIRMAN_CONTROL_ROOM.md item 6/7.
# ---------------------------------------------------------------------------

_MLX_PROFILE_CREATE_PATH = "/profile/create"
_MLX_PROFILE_REMOVE_PATH = "/profile/remove"

PEER_OPERATION_KEY = "web-sol-realm1-multilogin-profile-create-owner-20260902-sol-001"
PEER_PROVISION_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_canary_peer.json"
PEER_INTENT_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_peer_create_intent.json"
PEER_INTENT_SCHEMA = "mastermind.mas115_nonseat_peer_create_intent.v1"
PEER_RECEIPT_SCHEMA = "mastermind.mas115_nonseat_peer_lifecycle.v1"
_PEER_NAME_PREFIX = "mas115-peer-"
_PEER_BROWSER_TYPE = "mimic"
_PEER_OS_TYPE = "macos"
_PEER_REMOVE_PERMANENTLY = False  # recoverable; absence is proven against the active census

PEER_EFFECT_CODES = frozenset({
    "NONE", "CREATE_DISPATCHED", "CREATE_APPLIED", "CREATE_EFFECT_UNKNOWN",
    "PROVISION_WRITTEN", "PROFILE_STOPPED_PROVEN", "REMOVE_DISPATCHED",
    "REMOVE_APPLIED", "REMOVE_EFFECT_UNKNOWN", "ROLLBACK_VERIFIED",
})
PEER_EFFECT_DETAILS = {
    "NONE": "no peer-profile effect occurred.",
    "CREATE_DISPATCHED": "a create request for the disposable peer profile was sent to the vendor.",
    "CREATE_APPLIED": "the disposable peer profile exists but its stopped state is not yet proven.",
    "CREATE_EFFECT_UNKNOWN": "whether the disposable peer profile was created could not be determined.",
    "PROVISION_WRITTEN": "the disposable peer profile was created, proven stopped, and its provision was written.",
    "PROFILE_STOPPED_PROVEN": "the disposable peer profile was proven to exist and to be stopped.",
    "REMOVE_DISPATCHED": "a remove request for the disposable peer profile was sent to the vendor.",
    "REMOVE_APPLIED": "the disposable peer profile was removed but its absence is not yet proven.",
    "REMOVE_EFFECT_UNKNOWN": "whether the disposable peer profile was removed could not be determined.",
    "ROLLBACK_VERIFIED": "the disposable peer profile's absence was proven after removal.",
}
if set(PEER_EFFECT_DETAILS) != PEER_EFFECT_CODES:
    raise RuntimeError("nonseat_canary_vendors: PEER_EFFECT_DETAILS keys must exactly match PEER_EFFECT_CODES")

_PEER_PASS_EFFECTS = frozenset({"PROVISION_WRITTEN", "PROFILE_STOPPED_PROVEN", "ROLLBACK_VERIFIED"})
_PEER_HOLD_EFFECTS = frozenset({
    "CREATE_DISPATCHED", "CREATE_APPLIED", "CREATE_EFFECT_UNKNOWN",
    "REMOVE_DISPATCHED", "REMOVE_APPLIED", "REMOVE_EFFECT_UNKNOWN",
})

_PEER_RECEIPT_PREDICATE_KEYS = frozenset({
    "intent_committed", "candidates_before", "dispatched", "reconciled",
    "exact_readback", "stopped_proven", "provision_written",
    "cleanup_lease_retained", "removed_absent",
})
_PEER_BASE_PREDICATES = {
    "intent_committed": False,
    "candidates_before": 0,
    "dispatched": False,
    "reconciled": False,
    "exact_readback": False,
    "stopped_proven": False,
    "provision_written": False,
    "cleanup_lease_retained": False,
    "removed_absent": False,
}


def peer_profile_name(folder_id: str, anchor_profile_id: str) -> str:
    """Pure, deterministic, opaque peer-profile name.

    Same ``(folder_id, anchor_profile_id)`` always yields the same name; the
    caller can never supply a name directly. This is what makes read-back
    reconciliation possible without ever storing a raw vendor identity.
    """
    material = "|".join((PEER_OPERATION_KEY, folder_id, anchor_profile_id))
    return _PEER_NAME_PREFIX + _core.sha256_hex(material)[:16]


def peer_receipt(*, effect: str, code: str, verdict: str, digests: dict, **predicates) -> dict:
    """Build one closed, redacted MAS-115 peer lifecycle receipt."""

    if effect not in PEER_EFFECT_CODES:
        raise ValueError(f"unknown peer effect: {effect!r}")
    if code not in _core.RESULT_CODES:
        raise ValueError(f"unknown peer receipt code: {code!r}")
    if verdict not in ("PASS", "HOLD", "REFUSED"):
        raise ValueError(f"unknown peer receipt verdict: {verdict!r}")
    if not isinstance(digests, dict) or set(digests) != {"folder", "peer_name", "peer_profile", "anchor_profile"}:
        raise ValueError("peer receipt digests must carry exactly the fixed digest keys")
    for value in digests.values():
        if value is not None and not (isinstance(value, str) and _HEX64_RE.fullmatch(value)):
            raise ValueError("peer receipt digest values must be a sha256 hex digest or None")
    if set(predicates) != _PEER_RECEIPT_PREDICATE_KEYS:
        raise ValueError("peer receipt predicates must carry exactly the fixed predicate keys")
    for key, value in predicates.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            continue
        raise ValueError(f"peer receipt predicate {key!r} must be bool or int")
    return {
        "schema": PEER_RECEIPT_SCHEMA,
        "operation": PEER_OPERATION_KEY,
        "verdict": verdict,
        "effect": effect,
        "effect_detail": PEER_EFFECT_DETAILS[effect],
        "code": code,
        "detail": _core.DETAILS[code],
        "digests": dict(digests),
        "predicates": dict(predicates),
    }


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

    def _mlx_profile_create(self, credential, folder_id: str, name: str):
        body = {
            "name": name,
            "browser_type": _PEER_BROWSER_TYPE,
            "os_type": _PEER_OS_TYPE,
            "folder_id": folder_id,
            "times": 1,
            "parameters": {
                "flags": {"ports_masking": "mask", "proxy_masking": "disabled"},
                "storage": {"is_local": True, "save_service_worker": True},
                "fingerprint": {},
            },
        }
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, _MLX_PROFILE_CREATE_PATH,
            headers=self._bearer(credential), json_body=body,
        )

    def _mlx_profile_remove(self, credential, profile_id: str):
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, _MLX_PROFILE_REMOVE_PATH,
            headers=self._bearer(credential),
            json_body={"ids": [profile_id], "permanently": _PEER_REMOVE_PERMANENTLY},
        )

    def _mlx_profile_status(self, credential, profile_id: str):
        path = "/api/v1/profile/status/p/" + quote(profile_id, safe="")
        return self._request("GET", _MLX_LAUNCHER_ORIGIN, path, headers=self._bearer(credential))

    def _mlx_profile_metas(self, credential, profile_id: str):
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, "/profile/metas",
            headers=self._bearer(credential), json_body={"ids": [profile_id]},
        )

    def _mlx_configure_canary_port(self, credential, profile_id: str, snapshot):
        body = _port_policy.build_partial_update_body(profile_id, snapshot)
        expected = {
            "profile_id": profile_id,
            "auto_update_core": snapshot.auto_update_core,
            "parameters": {
                "flags": {"ports_masking": "mask"},
                "fingerprint": {"ports": [_port_policy.CANARY_PORT]},
            },
        }
        if body != expected:
            return None
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, "/profile/partial_update",
            headers=self._bearer(credential), json_body=body,
        )

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


def _is_exact_profile_create_success(response) -> bool:
    if response is None or response.status_code not in (200, 201):
        return False
    payload = response.payload
    if not isinstance(payload, dict) or set(payload) != {"status", "data"}:
        return False
    status = payload.get("status")
    data = payload.get("data")
    if not isinstance(status, dict) or set(status) != {"error_code", "http_code", "message"}:
        return False
    if (
        status.get("error_code") != ""
        or status.get("http_code") != response.status_code
        or status.get("message") != "Profile successfully created"
    ):
        return False
    if not isinstance(data, dict) or set(data) != {"ids"}:
        return False
    ids = data.get("ids")
    if not isinstance(ids, list) or len(ids) != 1:
        return False
    only_id = ids[0]
    return isinstance(only_id, str) and bool(only_id)


def _is_exact_profile_remove_success(response) -> bool:
    return (
        response is not None
        and response.status_code == 200
        and response.payload == {
            "status": {
                "error_code": "",
                "http_code": 200,
                "message": "Profile successfully removed",
            },
            "data": None,
        }
    )


def _is_exact_partial_update_success(response) -> bool:
    return (
        response is not None
        and response.status_code == 200
        and response.payload == {
            "status": {
                "error_code": "",
                "http_code": 200,
                "message": "Profile successfully updated",
            },
            "data": None,
        }
    )


def _is_explicit_partial_update_rejection(response) -> bool:
    if response is None or response.status_code in (401, 403):
        return False
    if not isinstance(response.status_code, int) or not 400 <= response.status_code <= 599:
        return False
    payload = response.payload
    if not isinstance(payload, dict) or set(payload) != {"status", "data"}:
        return False
    status = payload.get("status")
    return (
        payload.get("data") is None
        and isinstance(status, dict)
        and set(status) == {"error_code", "http_code", "message"}
        and isinstance(status.get("error_code"), str)
        and bool(status.get("error_code"))
        and status.get("http_code") == response.status_code
        and isinstance(status.get("message"), str)
    )


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
        #: Resolved id of the peer profile the most recent
        #: :meth:`create_peer_profile` proved into existence — set only from
        #: an exact read-back, never from a caller or a vendor response
        #: alone. The CLI layer reads this to write the peer provision; it
        #: is never placed in a receipt.
        self._peer_profile_id = None

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

    # -----------------------------------------------------------------
    # REALM1-C1 — one-profile peer create/reconcile/remove (Mastermind #385)
    # -----------------------------------------------------------------

    def peer_candidates(self, *, folder_id: str, peer_name: str) -> list:
        """Read-only census of every profile in ``folder_id`` named exactly
        ``peer_name``. Mirrors :meth:`_profile_inventory_item`'s pagination,
        duplicate-id, and auth/shape guards; never mutates anything."""
        self._require_credential()
        offset = 0
        expected_total = None
        seen_ids = set()
        matches = []
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
                if not isinstance(item, dict) or not {"id", "folder_id", "name"}.issubset(item):
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                item_id = item.get("id")
                item_folder = item.get("folder_id")
                item_name = item.get("name")
                if (
                    not isinstance(item_id, str)
                    or not isinstance(item_folder, str)
                    or not isinstance(item_name, str)
                ):
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                if item_id in seen_ids:
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                seen_ids.add(item_id)
                if item_name == peer_name:
                    if item_folder != folder_id:
                        raise _core.CanaryRefusal("VENDOR_ERROR")
                    if not isinstance(item.get("browser_type"), str) or not isinstance(item.get("os_type"), str):
                        # We cannot prove identity we cannot see.
                        raise _core.CanaryRefusal("VENDOR_ERROR")
                    matches.append(dict(item))
            offset += len(profiles)
            if offset == total:
                return matches
            if not profiles or offset > total:
                raise _core.CanaryRefusal("VENDOR_ERROR")
        raise _core.CanaryRefusal("VENDOR_ERROR")

    @staticmethod
    def _peer_identity_matches(record, *, folder_id: str, peer_name: str, require_unowned: bool = False) -> bool:
        if not isinstance(record, dict):
            return False
        ok = (
            record.get("folder_id") == folder_id
            and record.get("browser_type") == _PEER_BROWSER_TYPE
            and record.get("os_type") == _PEER_OS_TYPE
            and record.get("name") == peer_name
        )
        if not ok:
            return False
        if require_unowned:
            if record.get("in_use_by") != "":
                return False
            if "locked_by" in record and record.get("locked_by") != "":
                return False
        return True

    @staticmethod
    def _peer_digests(folder_id: str, anchor_profile_id: str, peer_name: str, *, peer_profile_id=None) -> dict:
        return {
            "folder": _core.sha256_hex(folder_id),
            "peer_name": _core.sha256_hex(peer_name),
            "peer_profile": _core.sha256_hex(peer_profile_id) if peer_profile_id else None,
            "anchor_profile": _core.sha256_hex(anchor_profile_id),
        }

    def create_peer_profile(self, *, folder_id, anchor_profile_id, intent_present, commit_intent) -> dict:
        """Create the one missing stopped disposable peer profile.

        At most ONE create dispatch, ever. The vendor response never decides
        the effect — a single read-only census read-back always does. This
        method performs NO file I/O: ``intent_present``/``commit_intent`` are
        supplied by the caller (the CLI layer in :func:`main`).
        """
        peer_name = peer_profile_name(folder_id, anchor_profile_id)
        digests = self._peer_digests(folder_id, anchor_profile_id, peer_name)
        intent_committed = bool(intent_present)

        def _receipt(effect, code, verdict, **overrides):
            predicates = dict(_PEER_BASE_PREDICATES)
            predicates["intent_committed"] = intent_committed
            predicates.update(overrides)
            return peer_receipt(effect=effect, code=code, verdict=verdict, digests=digests, **predicates)

        if not self._credential.present:
            return _receipt("NONE", "AUTH_MISSING", "REFUSED")

        try:
            candidates = self.peer_candidates(folder_id=folder_id, peer_name=peer_name)
        except _core.CanaryRefusal as refusal:
            return _receipt("NONE", refusal.code, "REFUSED")

        candidates_before = len(candidates)
        dispatched = False
        reconciled = False

        if candidates_before >= 1 and not intent_present:
            # A name-colliding profile we did not create is a conflict; we
            # never adopt it.
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        if intent_present and candidates_before == 1:
            if not self._peer_identity_matches(candidates[0], folder_id=folder_id, peer_name=peer_name):
                return _receipt("NONE", "VENDOR_ERROR", "REFUSED", candidates_before=candidates_before)
            dispatched = False
            reconciled = True
        elif intent_present and candidates_before != 1:
            # A committed intent means a create may already have been
            # dispatched; zero or many candidates is uncertainty, never
            # permission to dispatch again.
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=False, reconciled=True,
            )
        elif not intent_present and candidates_before == 0:
            try:
                committed = commit_intent()
            except Exception:  # noqa: BLE001 — a raising commit is a failed commit
                committed = False
            if committed is not True:
                return _receipt(
                    "NONE", "PROVISION_MISSING", "REFUSED", candidates_before=0, dispatched=False,
                )
            intent_committed = True
            response = None
            try:
                response = self._client._mlx_profile_create(self._credential, folder_id, peer_name)
            except Exception:  # noqa: BLE001 — never echo a dynamic transport error
                response = None
            if response is not None and response.status_code in (401, 403):
                # Auth rejection precedes creation; the ONLY pre-effect exit
                # after commit.
                return _receipt(
                    "NONE", "AUTH_EXPIRED", "REFUSED", candidates_before=0, dispatched=False,
                )
            exact = _is_exact_profile_create_success(response)
            dispatched = True
            reconciled = not exact
        else:  # pragma: no cover — every (intent_present, candidates_before)
            # combination is covered by the three branches above; this exists
            # only so a future mutation cannot silently fall through to a
            # dispatch with no guard.
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        # Read-back reconciliation: ALWAYS exactly one census read. The
        # create response never decides the effect by itself.
        try:
            after = self.peer_candidates(folder_id=folder_id, peer_name=peer_name)
        except _core.CanaryRefusal as refusal:
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", refusal.code, "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=False,
            )

        if len(after) != 1:
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=False,
            )

        record = after[0]
        if not self._peer_identity_matches(
            record, folder_id=folder_id, peer_name=peer_name, require_unowned=True,
        ):
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=False,
            )

        resolved_id = record["id"]
        self._peer_profile_id = resolved_id
        digests["peer_profile"] = _core.sha256_hex(resolved_id)

        try:
            state = self._profile_state({"profile_id": resolved_id, "folder_id": folder_id})
        except _core.CanaryRefusal:
            state = None

        if state != "stopped":
            return _receipt(
                "CREATE_APPLIED", "BUSY_PROFILE", "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=True, stopped_proven=False, cleanup_lease_retained=True,
            )

        return _receipt(
            "PROFILE_STOPPED_PROVEN", "OK", "HOLD",
            candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
            exact_readback=True, stopped_proven=True, cleanup_lease_retained=True,
        )

    def remove_peer_profile(self, *, folder_id, anchor_profile_id, peer_profile_id) -> dict:
        """Remove ONLY the exact stopped, unowned, operation-created peer
        profile. At most ONE remove dispatch, ever; the vendor response
        never decides the effect on its own."""
        peer_name = peer_profile_name(folder_id, anchor_profile_id)
        digests = self._peer_digests(
            folder_id, anchor_profile_id, peer_name, peer_profile_id=peer_profile_id,
        )

        def _receipt(effect, code, verdict, **overrides):
            predicates = dict(_PEER_BASE_PREDICATES)
            predicates.update(overrides)
            return peer_receipt(effect=effect, code=code, verdict=verdict, digests=digests, **predicates)

        if not self._credential.present:
            return _receipt("NONE", "AUTH_MISSING", "REFUSED")

        try:
            candidates = self.peer_candidates(folder_id=folder_id, peer_name=peer_name)
        except _core.CanaryRefusal as refusal:
            return _receipt("NONE", refusal.code, "REFUSED")

        candidates_before = len(candidates)
        if candidates_before == 0:
            return _receipt("NONE", "PROFILE_NOT_FOUND", "REFUSED", candidates_before=0)

        exact_target = (
            candidates_before == 1
            and candidates[0].get("id") == peer_profile_id
            and self._peer_identity_matches(
                candidates[0], folder_id=folder_id, peer_name=peer_name, require_unowned=True,
            )
        )
        if not exact_target:
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        try:
            state = self._profile_state({"profile_id": peer_profile_id, "folder_id": folder_id})
        except _core.CanaryRefusal:
            state = None
        if state != "stopped":
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        response = None
        try:
            response = self._client._mlx_profile_remove(self._credential, peer_profile_id)
        except Exception:  # noqa: BLE001 — never echo a dynamic transport error
            response = None
        if response is not None and response.status_code in (401, 403):
            return _receipt(
                "NONE", "AUTH_EXPIRED", "REFUSED", candidates_before=candidates_before,
            )
        exact = _is_exact_profile_remove_success(response)

        try:
            after = self.peer_candidates(folder_id=folder_id, peer_name=peer_name)
        except _core.CanaryRefusal:
            return _receipt(
                "REMOVE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=True, reconciled=True,
            )

        if len(after) == 0:
            return _receipt(
                "ROLLBACK_VERIFIED", "OK", "PASS",
                candidates_before=candidates_before, dispatched=True,
                reconciled=not exact, removed_absent=True,
            )
        if exact:
            return _receipt(
                "REMOVE_DISPATCHED", "VENDOR_ERROR", "REFUSED",
                candidates_before=candidates_before, dispatched=True, reconciled=False,
            )
        return _receipt(
            "REMOVE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
            candidates_before=candidates_before, dispatched=True, reconciled=True,
        )

    def port_policy_snapshot(self, profile_ref: dict):
        """Read and classify the exact stopped disposable profile policy."""

        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        profile = self._profile_inventory_item(profile_ref)
        if profile is None:
            raise _core.CanaryRefusal("PROFILE_NOT_FOUND")
        if profile.get("browser_type") != "mimic":
            raise _core.CanaryRefusal("UNSUPPORTED_PORT_STATE")
        if profile.get("in_use_by") != "":
            if isinstance(profile.get("in_use_by"), str) and profile.get("in_use_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if "locked_by" in profile and profile.get("locked_by") != "":
            if isinstance(profile.get("locked_by"), str) and profile.get("locked_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if self._profile_state(profile_ref) != "stopped":
            raise _core.CanaryRefusal("BUSY_PROFILE")

        response = self._safe_call(
            lambda: self._client._mlx_profile_metas(
                self._credential, profile_ref["profile_id"],
            ),
        )
        if response is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if response.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if response.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        try:
            return _port_policy.classify_profile_metas(
                response.payload,
                profile_id=profile_ref["profile_id"],
                folder_id=profile_ref["folder_id"],
            )
        except _port_policy.PortPolicyRefusal as refusal:
            code = (
                "UNSUPPORTED_PORT_STATE"
                if refusal.code == _port_policy.UNSUPPORTED_PORT_STATE
                else "VENDOR_ERROR"
            )
            raise _core.CanaryRefusal(code) from None

    @staticmethod
    def _config_receipt(code: str, **flags) -> dict:
        return _port_policy.configuration_receipt(code, **flags)

    def _post_configuration_receipt(
        self, before, profile_ref: dict, *, response_was_ambiguous: bool,
    ) -> dict:
        try:
            after = self.port_policy_snapshot(profile_ref)
        except _core.CanaryRefusal:
            return self._config_receipt(
                "EFFECT_UNKNOWN", updated=False, reconciled=response_was_ambiguous,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=False,
            )
        preservation_unchanged = after.preservation_digest == before.preservation_digest
        auto_update_unchanged = after.auto_update_core == before.auto_update_core
        if not preservation_unchanged or not auto_update_unchanged:
            return self._config_receipt(
                "PRESERVATION_DRIFT", updated=False, reconciled=response_was_ambiguous,
                preservation_unchanged=preservation_unchanged,
                auto_update_unchanged=auto_update_unchanged,
                exact_profile_stopped=True,
            )
        if after.state != _port_policy.EXACT_CONFIGURED:
            return self._config_receipt(
                "EFFECT_UNKNOWN" if response_was_ambiguous else "VENDOR_ERROR",
                updated=False, reconciled=response_was_ambiguous,
                preservation_unchanged=True, auto_update_unchanged=True,
                exact_profile_stopped=True,
            )
        return self._config_receipt(
            "CONFIGURED_AFTER_RECONCILIATION" if response_was_ambiguous else "CONFIGURED",
            updated=True, reconciled=response_was_ambiguous,
            preservation_unchanged=True, auto_update_unchanged=True,
            exact_profile_stopped=True,
        )

    def configure_canary_port(self, profile_ref: dict) -> dict:
        """Perform at most one exact update, followed only by read-back."""

        try:
            before = self.port_policy_snapshot(profile_ref)
        except _core.CanaryRefusal as refusal:
            code = (
                "UNSUPPORTED_PORT_STATE"
                if refusal.code == "UNSUPPORTED_PORT_STATE"
                else "AUTH_EXPIRED_NO_PROOF"
                if refusal.code == "AUTH_EXPIRED"
                else "VENDOR_ERROR"
            )
            return self._config_receipt(
                code, updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=False,
            )
        if before.state == _port_policy.EXACT_CONFIGURED:
            return self._config_receipt(
                "ALREADY_CONFIGURED", updated=False, reconciled=False,
                preservation_unchanged=True, auto_update_unchanged=True,
                exact_profile_stopped=True,
            )
        if before.state != _port_policy.DEFAULT_MASKED:
            return self._config_receipt(
                "UNSUPPORTED_PORT_STATE", updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=True,
            )
        try:
            response = self._client._mlx_configure_canary_port(
                self._credential, profile_ref["profile_id"], before,
            )
        except Exception:  # noqa: BLE001 — reconcile read-only after ambiguous write
            response = None
        if response is not None and response.status_code in (401, 403):
            return self._config_receipt(
                "AUTH_EXPIRED_NO_PROOF", updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=True,
            )
        if _is_exact_partial_update_success(response):
            return self._post_configuration_receipt(
                before, profile_ref, response_was_ambiguous=False,
            )
        if _is_explicit_partial_update_rejection(response):
            return self._config_receipt(
                "REJECTED_NO_PROOF", updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=True,
            )
        return self._post_configuration_receipt(
            before, profile_ref, response_was_ambiguous=True,
        )


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
        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", _port_policy.CANARY_PORT), _CanaryRequestHandler,
        )
        if self._server.server_address[:2] != ("127.0.0.1", _port_policy.CANARY_PORT):
            self._server.server_close()
            raise _core.CanaryRefusal("CANARY_PORT_UNAVAILABLE")
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
        return _port_policy.CANARY_ORIGIN

    def self_test(self) -> bool:
        """Prove the fixed loopback listener and clear the probe observation."""

        connection = http.client.HTTPConnection(
            "127.0.0.1", _port_policy.CANARY_PORT, timeout=2.0,
        )
        try:
            connection.request("GET", "/auth")
            response = connection.getresponse()
            body = response.read(64)
            healthy = (
                response.status == 401
                and response.getheader("WWW-Authenticate") == 'Basic realm="mas115-canary"'
                and body == b"unauthorized"
            )
        except Exception:  # noqa: BLE001 — local self-test has one closed result
            healthy = False
        finally:
            connection.close()
            with self._lock:
                self._seen_paths.discard("/auth")
        return healthy

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


def _local_disposable_preflight(provision: dict, environment_loader=None):
    """Require one exact locally stopped Multilogin profile before secrets."""

    if environment_loader is None:
        from integrations.chairman_surfaces import chatgpt as _chatgpt

        environment_loader = _chatgpt.list_local_environments
    try:
        census = environment_loader()
    except Exception:  # noqa: BLE001 — local uncertainty has one fixed result
        return "VENDOR_ERROR"
    if not isinstance(census, dict) or not isinstance(census.get("multilogin"), list):
        return "VENDOR_ERROR"
    profile_id = provision["profile_id"]
    folder_id = provision["folder_id"]
    matches = []
    for row in census["multilogin"]:
        if not isinstance(row, dict):
            return "VENDOR_ERROR"
        row_profile = row.get("profile_id")
        row_folder = row.get("folder_id")
        if isinstance(row_profile, str) and row_profile.lower() == profile_id:
            if not isinstance(row_folder, str) or row_folder.lower() != folder_id:
                return "VENDOR_ERROR"
            matches.append(row)
    if not matches:
        return "PROFILE_NOT_FOUND"
    if len(matches) != 1 or type(matches[0].get("running")) is not bool:
        return "VENDOR_ERROR"
    return "BUSY_PROFILE" if matches[0]["running"] else None


def atomic_private_json(doc: dict, path) -> None:
    """Write ``doc`` to ``path`` as private (0600) JSON, atomically.

    The single implementation (moved here from ``scripts/mas115_setup.py``
    per the REALM1-C1 spec §3.10): parent mkdir 0700, tmp file in the same
    directory, fchmod 0600, write/flush/fsync, ``os.replace``, chmod 0600,
    unlink the tmp file on any failure.
    """
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
    tmp = tempfile.NamedTemporaryFile(
        dir=os.fspath(target.parent), prefix=f".{target.name}.", suffix=".tmp", delete=False,
    )
    try:
        os.fchmod(tmp.fileno(), 0o600)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    try:
        os.replace(tmp.name, target)
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def _peer_intent_present(path, *, peer_name: str) -> bool:
    """True iff ``path`` holds an exact, schema/operation/peer_name-matching
    intent document. A malformed or mismatched file is treated as NOT
    present (see :func:`_commit_peer_intent`, which additionally refuses to
    silently overwrite such a file)."""
    target = Path(path).expanduser()
    try:
        if not target.is_file():
            return False
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(doc, dict)
        and doc.get("schema") == PEER_INTENT_SCHEMA
        and doc.get("operation") == PEER_OPERATION_KEY
        and doc.get("peer_name") == peer_name
    )


def _commit_peer_intent(path, *, folder_id: str, anchor_profile_id: str, peer_name: str) -> bool:
    """Atomically write the intent sidecar BEFORE any create dispatch.

    Idempotent: an existing file that already byte-matches the candidate
    document is treated as already committed. Any other existing file
    (malformed, foreign, or from a different operation) blocks — it is
    never silently overwritten.
    """
    target = Path(path).expanduser()
    candidate = {
        "schema": PEER_INTENT_SCHEMA,
        "operation": PEER_OPERATION_KEY,
        "folder_digest": _core.sha256_hex(folder_id),
        "anchor_profile_digest": _core.sha256_hex(anchor_profile_id),
        "peer_name": peer_name,
        "browser_type": _PEER_BROWSER_TYPE,
        "os_type": _PEER_OS_TYPE,
    }
    try:
        if target.is_file():
            existing = json.loads(target.read_text(encoding="utf-8"))
            return existing == candidate
    except (OSError, ValueError):
        return False
    try:
        atomic_private_json(candidate, target)
    except Exception:  # noqa: BLE001 — a write failure is a failed commit
        return False
    return True


def _write_peer_provision(
    path, *, profile_id: str, folder_id: str, bindings_loader, now,
):
    """Write (or reconcile) the peer provision, then require it re-validates.

    Returns ``(written, loaded_or_none)``. An already-present, byte-different
    file refuses rather than overwriting; a written-but-invalid document
    also reports ``written=False`` — both collapse to the same HOLD/
    PROVISION_MISSING outcome the caller applies to the receipt.
    """
    target = Path(path).expanduser()
    doc = {
        "schema": _core.PROVISION_SCHEMA,
        "vendor": "multilogin",
        "profile_id": profile_id,
        "folder_id": folder_id,
        "browser_type": _PEER_BROWSER_TYPE,
        "origin_policy": _port_policy.ORIGIN_POLICY,
        "disposable_ack": _core.REQUIRED_ACK,
    }
    try:
        if target.is_file():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing != doc:
                return False, None
        else:
            atomic_private_json(doc, target)
    except Exception:  # noqa: BLE001 — any write/read failure is a failed write
        return False, None
    loaded, _code = _core.load_provision(str(target), bindings_loader=bindings_loader, now=now)
    return (loaded is not None), loaded


def _create_peer_profile_cli(
    client: "MultiloginClient", provision: dict, *,
    peer_intent_path, peer_provision_path, bindings_loader, now,
) -> dict:
    """CLI-layer wrapper: owns the intent/provision file I/O that
    :meth:`MultiloginClient.create_peer_profile` deliberately does not."""
    folder_id = provision["folder_id"]
    anchor_profile_id = provision["profile_id"]
    peer_name = peer_profile_name(folder_id, anchor_profile_id)
    intent_present = _peer_intent_present(peer_intent_path, peer_name=peer_name)

    def _commit():
        return _commit_peer_intent(
            peer_intent_path, folder_id=folder_id, anchor_profile_id=anchor_profile_id,
            peer_name=peer_name,
        )

    receipt = client.create_peer_profile(
        folder_id=folder_id, anchor_profile_id=anchor_profile_id,
        intent_present=intent_present, commit_intent=_commit,
    )
    if receipt["effect"] != "PROFILE_STOPPED_PROVEN":
        # A create whose read-back could not prove the profile stopped is NOT
        # a provisionable profile. Writing profile_B here would publish a
        # binding for a profile that may be running or owned, and would let a
        # HOLD masquerade as PASS. The exact cleanup lease stays retained.
        return receipt

    peer_profile_id = client._peer_profile_id  # noqa: SLF001 — CLI/client are one unit here
    written, _loaded = _write_peer_provision(
        peer_provision_path, profile_id=peer_profile_id, folder_id=folder_id,
        bindings_loader=bindings_loader, now=now,
    )
    predicates = dict(receipt["predicates"])
    if written:
        predicates["provision_written"] = True
        predicates["cleanup_lease_retained"] = False
        return peer_receipt(
            effect="PROVISION_WRITTEN", code="OK", verdict="PASS",
            digests=receipt["digests"], **predicates,
        )
    predicates["provision_written"] = False
    predicates["cleanup_lease_retained"] = True
    return peer_receipt(
        effect=receipt["effect"], code="PROVISION_MISSING", verdict="HOLD",
        digests=receipt["digests"], **predicates,
    )


def main(
    argv=None, *, stdout=None, bindings_loader=None, credential_stream_factory=None,
    client_factory=BoundedHttpClient, origin_factory=LoopbackBenignOrigin,
    environment_loader=None, now=None,
) -> int:
    """Run the operator-only helper.

    ``credential_stream_factory`` is a hermetic test seam.  The CLI/live path
    cannot set it and always uses the fixed post-preflight Keychain pipe.
    No repository test calls a real credential store or vendor endpoint.
    """
    parser = argparse.ArgumentParser(prog="nonseat_canary_vendors")
    parser.add_argument(
        "operation", nargs="?", default="run",
        choices=("run", "configure-canary-port", "create-peer-profile", "rollback-peer-profile"),
    )
    parser.add_argument("--vendor", required=True, choices=("gologin", "multilogin"))
    parser.add_argument("--provision-path", required=True)
    parser.add_argument("--peer-provision-path", default=None)
    parser.add_argument("--peer-intent-path", default=None)
    parser.add_argument("--confirmed", action="store_true")
    args = parser.parse_args(argv)
    peer_ops = ("create-peer-profile", "rollback-peer-profile")
    if args.operation in peer_ops and not args.confirmed:
        parser.error(f"--confirmed is required for {args.operation}")
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
    if provision.get("browser_type") != "mimic":
        return _emit_refusal(out, args.vendor, "UNSUPPORTED_PORT_STATE")
    local_code = _local_disposable_preflight(provision, environment_loader)
    if local_code is not None:
        return _emit_refusal(out, args.vendor, local_code)

    peer_provision_path = args.peer_provision_path or PEER_PROVISION_PATH
    peer_intent_path = args.peer_intent_path or PEER_INTENT_PATH
    peer_provision = None
    if args.operation == "rollback-peer-profile":
        # Rollback needs the PEER provision's profile_id before it can even
        # build a target — a purely local check, so it happens before Keychain.
        peer_provision, peer_code = _core.load_provision(
            peer_provision_path, bindings_loader=bindings_loader, now=reference_time,
        )
        if peer_provision is None:
            return _emit_refusal(out, args.vendor, "PROVISION_MISSING")

    origin = None
    if args.operation not in peer_ops:
        # Bind and self-test the one fixed loopback origin before any secret
        # or vendor transport exists. There is no fallback port. The peer
        # create/rollback operations never launch a browser, so the fixed
        # port origin is irrelevant to them and is skipped entirely.
        token = "mas115-live-" + secrets.token_hex(16)
        try:
            origin = origin_factory(token=token)
            if origin.base_url != _port_policy.CANARY_ORIGIN or origin.self_test() is not True:
                raise _core.CanaryRefusal("CANARY_PORT_UNAVAILABLE")
        except Exception:  # noqa: BLE001 — bind/self-test failures have one static refusal
            if origin is not None:
                try:
                    origin.close()
                except Exception:  # noqa: BLE001 — closed result cannot expand
                    pass
            return _emit_refusal(out, args.vendor, "CANARY_PORT_UNAVAILABLE")

    # This is intentionally after every provision, collision, bind, and local
    # self-test preflight. Production has no external-stdin path: that would
    # let an eager ``security | helper`` producer run too early.
    credential_stream = None
    try:
        factory = credential_stream_factory or _open_keychain_credential_pipe
        credential_stream = factory()
        credential = _read_direct_pipe_credential(credential_stream)
    except _core.CanaryRefusal as refusal:
        if origin is not None:
            origin.close()
        return _emit_refusal(out, args.vendor, refusal.code)
    except Exception:  # noqa: BLE001 — fixed absence result only
        if origin is not None:
            origin.close()
        return _emit_refusal(out, args.vendor, "AUTH_MISSING")
    finally:
        if credential_stream is not None:
            try:
                credential_stream.close()
            except Exception:  # noqa: BLE001 — fixed cleanup boundary
                pass
    if not credential.present:
        if origin is not None:
            origin.close()
        return _emit_refusal(out, args.vendor, "AUTH_MISSING")

    client = None
    try:
        client = client_factory()
        live_provision = dict(provision)
        live_provision["benign_origin"] = _port_policy.CANARY_ORIGIN
        vendor_client = MultiloginClient(
            credential, client, browser_type=live_provision["browser_type"],
        )
        profile_ref = {
            "profile_id": provision["profile_id"],
            "folder_id": provision["folder_id"],
        }
        if args.operation == "create-peer-profile":
            receipt = _create_peer_profile_cli(
                vendor_client, provision,
                peer_intent_path=peer_intent_path, peer_provision_path=peer_provision_path,
                bindings_loader=bindings_loader, now=reference_time,
            )
            print(json.dumps(receipt, indent=2, sort_keys=True), file=out)
            if receipt.get("verdict") == "PASS":
                return 0
            return 3 if receipt.get("verdict") == "HOLD" else 2

        if args.operation == "rollback-peer-profile":
            receipt = vendor_client.remove_peer_profile(
                folder_id=provision["folder_id"], anchor_profile_id=provision["profile_id"],
                peer_profile_id=peer_provision["profile_id"],
            )
            print(json.dumps(receipt, indent=2, sort_keys=True), file=out)
            if receipt.get("verdict") == "PASS":
                return 0
            return 3 if receipt.get("verdict") == "HOLD" else 2

        if args.operation == "configure-canary-port":
            receipt = vendor_client.configure_canary_port(profile_ref)
            print(json.dumps(receipt, indent=2, sort_keys=True), file=out)
            if receipt.get("verdict") == "PASS":
                return 0
            return 3 if receipt.get("verdict") == "HOLD" else 2

        before_policy = vendor_client.port_policy_snapshot(profile_ref)
        if before_policy.state != _port_policy.EXACT_CONFIGURED:
            raise _core.CanaryRefusal("UNSUPPORTED_PORT_STATE")
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
        postflight_ok = False
        try:
            after_policy = vendor_client.port_policy_snapshot(profile_ref)
            postflight_ok = (
                after_policy.state == _port_policy.EXACT_CONFIGURED
                and after_policy.auto_update_core == before_policy.auto_update_core
                and after_policy.preservation_digest == before_policy.preservation_digest
            )
        except _core.CanaryRefusal:
            postflight_ok = False
        if not postflight_ok:
            c10 = next(
                (row for row in receipts.get("rows", []) if row.get("row") == "C10"),
                None,
            )
            if c10 is None:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            c10.update({
                "code": "UNSUPPORTED_PORT_STATE",
                "detail": _core.DETAILS["UNSUPPORTED_PORT_STATE"],
                "ok": False,
            })
            receipts["verdict"] = "FAIL"
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
