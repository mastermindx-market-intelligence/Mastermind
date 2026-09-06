"""One-shot, read-only Multilogin Profile Search health observation.

This capability deliberately owns no profile lifecycle, browser, loopback,
WebDriver, peer-state, retry, or persistence surface. It validates the fixed
MAS-115 disposable anchor through the existing canonical preflight, acquires
one existing fixed Keychain credential, reuses the existing bounded Profile
Search transport and parser through a capability-minimal proxy, proves
resource cleanup, and emits one closed receipt.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

from control_plane import surface_bindings as _surface_bindings

from . import nonseat_canary as _core
from . import nonseat_canary_vendors as _vendors

RECEIPT_SCHEMA = "mastermind.mas115_profile_search_health.v1"
OPERATION_KEY = "web-sol-realm1-profile-search-read-health-20260905-sol-001"
_RECEIPT_KEYS = frozenset({
    "schema",
    "operation",
    "verdict",
    "effect",
    "code",
    "detail",
    "read_surface_usable",
    "initial_peer_census_diagnostic",
    "initial_peer_census_decode_context",
})
_DISCARD_PROFILE_NAME = object()
_HTTP_CLOSED_ATTR = "_mas115_profile_search_health_closed"


def _receipt(
    code: str,
    *,
    diagnostic: str = "NONE",
    decode_context=None,
) -> dict:
    """Build the exact closed nine-key health receipt."""

    if code not in _core.RESULT_CODES:
        code = "VENDOR_ERROR"
    if diagnostic not in _vendors.INITIAL_PEER_CENSUS_DIAGNOSTICS:
        code = "VENDOR_ERROR"
        diagnostic = "NONE"
        decode_context = None
    try:
        context = _vendors._initial_peer_census_decode_context_tuple(  # noqa: SLF001
            decode_context,
        )
    except (TypeError, ValueError, KeyError):
        code = "VENDOR_ERROR"
        diagnostic = "NONE"
        context = _vendors._INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE  # noqa: SLF001
    if diagnostic == "RESPONSE_DECODE_FAILURE":
        if "NONE" in context:
            code = "VENDOR_ERROR"
            diagnostic = "NONE"
            context = _vendors._INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE  # noqa: SLF001
    elif context != _vendors._INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE:  # noqa: SLF001
        code = "VENDOR_ERROR"
        diagnostic = "NONE"
        context = _vendors._INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE  # noqa: SLF001

    passed = code == "OK" and diagnostic == "NONE"
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "operation": OPERATION_KEY,
        "verdict": "PASS" if passed else "REFUSED",
        "effect": "NONE",
        "code": code,
        "detail": _core.DETAILS[code],
        "read_surface_usable": passed,
        "initial_peer_census_diagnostic": diagnostic,
        "initial_peer_census_decode_context": (
            _vendors._initial_peer_census_decode_context_dict(context)  # noqa: SLF001
        ),
    }
    if set(receipt) != _RECEIPT_KEYS:  # pragma: no cover - import-time contract
        raise RuntimeError("profile-search health receipt key drift")
    return receipt


def _emit(stdout, receipt: dict) -> int:
    stdout.write(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
    stdout.write("\n")
    return 0 if receipt.get("verdict") == "PASS" else 2


def _load_live_preflight():
    """Repeat the complete fixed anchor/binding/census gate before Keychain."""

    try:
        snapshot = _core._seal_current_environment_snapshot(  # noqa: SLF001
            _vendors._coordinator_local_census(),  # noqa: SLF001
        )
    except Exception:  # noqa: BLE001 - one closed local-census refusal
        snapshot = None
    if snapshot is None:
        return None, "BINDINGS_UNAVAILABLE"

    provision, code = _core.load_provision(
        _core.DEFAULT_PROVISION_PATH,
        bindings_loader=_surface_bindings.load_bindings,
        now=datetime.now(timezone.utc),
        current_environment_snapshot=snapshot,
    )
    if provision is None:
        return None, code or "PROVISION_MISSING"
    if provision.get("vendor") != "multilogin":
        return None, "PROVISION_MISSING"
    if provision.get("browser_type") != "mimic":
        return None, "UNSUPPORTED_PORT_STATE"
    local_code = _vendors._local_disposable_preflight(  # noqa: SLF001
        provision,
        current_environment_snapshot=snapshot,
    )
    return (provision, None) if local_code is None else (None, local_code)


def _checked_close_keychain_pipe(pipe) -> bool:
    """Close/reap the exact fixed Keychain child with an exact Boolean result."""

    if type(pipe) is not _vendors._KeychainCredentialPipe:  # noqa: SLF001
        return False
    read_fd = getattr(pipe, "_fd", None)
    if type(read_fd) is not int or read_fd < 0:
        return False

    closed = True
    try:
        os.close(read_fd)
    except OSError:
        closed = False
    pipe._fd = -1  # noqa: SLF001 - make this owner one-shot before waiting

    timeout = _vendors._KEYCHAIN_WAIT_TIMEOUT_SECONDS  # noqa: SLF001
    try:
        if pipe._wait_until(time.monotonic() + timeout):  # noqa: SLF001
            return closed is True
    except Exception:  # noqa: BLE001
        return False

    try:
        pipe._kill(pipe._pid, signal.SIGTERM)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return False
    try:
        if pipe._wait_until(time.monotonic() + timeout):  # noqa: SLF001
            return closed is True
    except Exception:  # noqa: BLE001
        return False

    try:
        pipe._kill(pipe._pid, signal.SIGKILL)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return False
    try:
        reaped = pipe._wait_until(time.monotonic() + timeout)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return False
    return closed is True and reaped is True


def _checked_close_http_client(client) -> bool:
    """Close the exact bounded HTTP owner once, without changing legacy close."""

    if type(client) is not _vendors.BoundedHttpClient:
        return False
    if getattr(client, _HTTP_CLOSED_ATTR, False) is not False:
        return False
    setattr(client, _HTTP_CLOSED_ATTR, True)
    try:
        client._client.close()  # noqa: SLF001 - checked owner beneath legacy close
    except Exception:  # noqa: BLE001
        return False
    return True


class _ProfileSearchOnlyClient:
    """Sealed capability exposing only diagnostic Profile Search."""

    __slots__ = ("_delegate",)

    def __init__(self, delegate):
        if type(delegate) is not _vendors.BoundedHttpClient:
            raise TypeError("bounded Profile Search client required")
        self._delegate = delegate

    def _mlx_profile_search_with_diagnostic(
        self,
        credential,
        folder_id: str,
        *,
        offset: int,
        diagnostic_sink,
    ):
        return self._delegate._mlx_profile_search_with_diagnostic(  # noqa: SLF001
            credential,
            folder_id,
            offset=offset,
            diagnostic_sink=diagnostic_sink,
        )


class _ProfileSearchProxy:
    """Minimum surface required by the existing canonical census parser."""

    __slots__ = ("_credential", "_client")

    def __init__(self, credential, client: _ProfileSearchOnlyClient):
        if type(client) is not _ProfileSearchOnlyClient:
            raise TypeError("sealed Profile Search capability required")
        self._credential = credential
        self._client = client

    def _require_credential(self) -> None:
        if getattr(self._credential, "present", False) is not True:
            raise _core.CanaryRefusal("AUTH_MISSING")

    @staticmethod
    def _safe_call(call, *, diagnostic_sink=None):
        return _vendors.MultiloginClient._safe_call(
            call,
            diagnostic_sink=diagnostic_sink,
        )

    @staticmethod
    def _successful_envelope(
        payload,
        *,
        profile_id=None,
        folder_id=None,
        expected_message="",
    ):
        return _vendors.MultiloginClient._successful_envelope(
            payload,
            profile_id=profile_id,
            folder_id=folder_id,
            expected_message=expected_message,
        )


def _run_profile_search_health(
    *,
    stdout,
    preflight_loader,
    pipe_factory,
    credential_reader,
    pipe_closer,
    client_factory,
    client_closer,
) -> int:
    """Hermetic core; the public wrapper fixes every live dependency owner."""

    try:
        provision, preflight_code = preflight_loader()
    except Exception:  # noqa: BLE001
        provision, preflight_code = None, "BINDINGS_UNAVAILABLE"
    if provision is None:
        return _emit(stdout, _receipt(preflight_code or "PROVISION_MISSING"))
    if (
        not isinstance(provision, dict)
        or provision.get("vendor") != "multilogin"
        or provision.get("browser_type") != "mimic"
        or not isinstance(provision.get("folder_id"), str)
        or not provision.get("folder_id")
    ):
        return _emit(stdout, _receipt("PROVISION_MISSING"))

    pipe = None
    credential = None
    try:
        pipe = pipe_factory()
        credential = credential_reader(pipe)
    except Exception:  # noqa: BLE001
        credential = None
    try:
        pipe_closed = pipe_closer(pipe) if pipe is not None else False
    except Exception:  # noqa: BLE001
        pipe_closed = False
    if pipe_closed is not True:
        return _emit(stdout, _receipt("VENDOR_ERROR"))
    if credential is None or getattr(credential, "present", False) is not True:
        return _emit(stdout, _receipt("AUTH_MISSING"))

    client = None
    try:
        client = client_factory()
    except Exception:  # noqa: BLE001
        client = None
    if type(client) is not _vendors.BoundedHttpClient:
        return _emit(stdout, _receipt("VENDOR_ERROR"))

    sink = _vendors._InitialPeerCensusDiagnosticSink(  # noqa: SLF001
        _vendors._INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,  # noqa: SLF001
    )
    code = "OK"
    try:
        proxy = _ProfileSearchProxy(
            credential,
            _ProfileSearchOnlyClient(client),
        )
        matches = _vendors.MultiloginClient._peer_candidates(  # noqa: SLF001
            proxy,
            folder_id=provision["folder_id"],
            peer_name=_DISCARD_PROFILE_NAME,
            diagnostic_sink=sink,
        )
        if type(matches) is not list or matches:
            code = "VENDOR_ERROR"
    except _core.CanaryRefusal as refusal:
        code = refusal.code if refusal.code in _core.RESULT_CODES else "VENDOR_ERROR"
    except Exception:  # noqa: BLE001
        code = "VENDOR_ERROR"

    try:
        client_closed = client_closer(client)
    except Exception:  # noqa: BLE001
        client_closed = False
    if client_closed is not True:
        code = "VENDOR_ERROR"

    return _emit(
        stdout,
        _receipt(
            code,
            diagnostic=sink.value,
            decode_context=sink.decode_context,
        ),
    )


def run_coordinator_profile_search_health(*, stdout=None) -> int:
    """Trusted live entrypoint with no caller-selected target or transport."""

    return _run_profile_search_health(
        stdout=stdout if stdout is not None else sys.stdout,
        preflight_loader=_load_live_preflight,
        pipe_factory=_vendors._open_keychain_credential_pipe,  # noqa: SLF001
        credential_reader=_vendors._read_direct_pipe_credential,  # noqa: SLF001
        pipe_closer=_checked_close_keychain_pipe,
        client_factory=_vendors.BoundedHttpClient,
        client_closer=_checked_close_http_client,
    )
