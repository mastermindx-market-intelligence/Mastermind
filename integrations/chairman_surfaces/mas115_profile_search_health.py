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


def run_coordinator_profile_search_health_refusal(*, stdout=None) -> int:
    """Emit the one fixed pre-trusted refusal without touching live dependencies."""

    return _emit(
        stdout if stdout is not None else sys.stdout,
        _receipt("UNSUPPORTED_SURFACE"),
    )


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
    cleanup_error = False
    try:
        reaped = pipe._wait_until(time.monotonic() + timeout)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        cleanup_error = True
        reaped = False
    if reaped is True:
        return closed is True and cleanup_error is False

    try:
        pipe._kill(pipe._pid, signal.SIGTERM)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        cleanup_error = True
    try:
        reaped = pipe._wait_until(time.monotonic() + timeout)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        cleanup_error = True
        reaped = False
    if reaped is True:
        return closed is True and cleanup_error is False

    try:
        pipe._kill(pipe._pid, signal.SIGKILL)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        cleanup_error = True
        reaped = False
    else:
        try:
            reaped = pipe._wait_until(time.monotonic() + timeout)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            cleanup_error = True
            reaped = False
    return closed is True and reaped is True and cleanup_error is False


def _is_exact_profile_search_request(
    method: str,
    origin: str,
    path: str,
    *,
    headers=None,
    params=None,
    json_body=None,
    diagnostic_sink=None,
) -> bool:
    """Return whether a request is exactly one diagnostic Profile Search page."""

    body = json_body
    authorization = headers.get("Authorization") if isinstance(headers, dict) else None
    fixed_body_keys = {
        "is_removed",
        "limit",
        "offset",
        "search_text",
        "storage_type",
        "order_by",
        "sort",
        "folder_id",
    }
    return (
        method == "POST"
        and origin == _vendors._MLX_CLOUD_ORIGIN  # noqa: SLF001
        and path == "/profile/search"
        and params is None
        and isinstance(headers, dict)
        and set(headers) == {"Authorization"}
        and isinstance(authorization, str)
        and authorization.startswith("Bearer ")
        and len(authorization) > len("Bearer ")
        and isinstance(body, dict)
        and set(body) == fixed_body_keys
        and body.get("is_removed") is False
        and body.get("limit") == _vendors._PROFILE_PAGE_SIZE  # noqa: SLF001
        and type(body.get("offset")) is int
        and 0 <= body["offset"] < _vendors._MAX_PROFILE_CENSUS  # noqa: SLF001
        and body.get("search_text") == ""
        and body.get("storage_type") == "all"
        and body.get("order_by") == "created_at"
        and body.get("sort") == "asc"
        and isinstance(body.get("folder_id"), str)
        and bool(body["folder_id"])
        and type(diagnostic_sink) is _vendors._InitialPeerCensusDiagnosticSink  # noqa: SLF001
    )


def _run_profile_search_health(
    *,
    stdout,
    preflight_loader,
    pipe_factory,
    credential_reader,
    pipe_closer,
) -> int:
    """Hermetic core; the public wrapper fixes every live dependency owner."""

    provision = None
    preflight_code = None
    pipe = None
    credential = None
    client = None
    raw_owner = None
    sink = None
    state = None
    response = None
    matches = None
    method = None
    origin = None
    path = None
    headers = None
    params = None
    body = None
    request_sink = None
    client_closed = None
    code = "VENDOR_ERROR"

    try:
        provision, preflight_code = preflight_loader()
    except Exception:  # noqa: BLE001
        provision, preflight_code = None, "BINDINGS_UNAVAILABLE"
    if provision is None:
        code = preflight_code or "PROVISION_MISSING"
    elif (
        not isinstance(provision, dict)
        or provision.get("vendor") != "multilogin"
        or provision.get("browser_type") != "mimic"
        or not isinstance(provision.get("profile_id"), str)
        or not provision.get("profile_id")
        or not isinstance(provision.get("folder_id"), str)
        or not provision.get("folder_id")
    ):
        code = "PROVISION_MISSING"
    else:
        try:
            pipe = pipe_factory()
            credential = credential_reader(pipe)
        except (Exception, KeyboardInterrupt):  # noqa: BLE001
            credential = None
        try:
            pipe_closed = pipe_closer(pipe) if pipe is not None else False
        except Exception:  # noqa: BLE001
            pipe_closed = False
        if pipe_closed is not True:
            code = "VENDOR_ERROR"
        elif credential is None or getattr(credential, "present", False) is not True:
            code = "AUTH_MISSING"
        else:
            try:
                client = _vendors.BoundedHttpClient()
            except Exception:  # noqa: BLE001
                client = None
            if type(client) is not _vendors.BoundedHttpClient:
                code = "VENDOR_ERROR"
            else:
                try:
                    sink = _vendors._InitialPeerCensusDiagnosticSink(  # noqa: SLF001
                        _vendors._INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,  # noqa: SLF001
                    )
                    state = _vendors._ProfileSearchCensusState(  # noqa: SLF001
                        folder_id=provision["folder_id"],
                        peer_name=None,
                    )
                    while not state.complete:
                        (
                            method,
                            origin,
                            path,
                            headers,
                            params,
                            body,
                            request_sink,
                        ) = _vendors._mlx_profile_search_request_arguments(  # noqa: SLF001
                            credential,
                            provision["folder_id"],
                            offset=state.next_offset,
                            diagnostic_sink=sink,
                        )
                        if not _is_exact_profile_search_request(
                            method,
                            origin,
                            path,
                            headers=headers,
                            params=params,
                            json_body=body,
                            diagnostic_sink=request_sink,
                        ):
                            raise _core.CanaryRefusal("VENDOR_ERROR")
                        response = _vendors.BoundedHttpClient._request(  # noqa: SLF001
                            client,
                            method,
                            origin,
                            path,
                            headers=headers,
                            params=params,
                            json_body=body,
                            diagnostic_sink=request_sink,
                        )
                        state.consume(response, diagnostic_sink=sink)
                        response = None
                        method = origin = path = headers = params = body = request_sink = None
                    matches = state.finish()
                    code = "OK" if type(matches) is list and not matches else "VENDOR_ERROR"
                except _core.CanaryRefusal as refusal:
                    code = refusal.code if refusal.code in _core.RESULT_CODES else "VENDOR_ERROR"
                except (Exception, KeyboardInterrupt):  # noqa: BLE001
                    code = "VENDOR_ERROR"

    if type(client) is _vendors.BoundedHttpClient:
        try:
            raw_owner = client._client  # noqa: SLF001 - detach before close
            client._client = None  # noqa: SLF001 - one-shot raw-owner detach
        except Exception:  # noqa: BLE001
            raw_owner = None
        if raw_owner is not None:
            try:
                raw_owner.close()
            except Exception:  # noqa: BLE001
                client_closed = False
            else:
                client_closed = True
        else:
            client_closed = False
        if client_closed is not True:
            code = "VENDOR_ERROR"

    diagnostic = sink.value if sink is not None else "NONE"
    decode_context = sink.decode_context if sink is not None else None
    provision = None
    pipe = None
    credential = None
    client = None
    raw_owner = None
    state = None
    response = None
    matches = None
    method = origin = path = headers = params = body = request_sink = None
    preflight_loader = pipe_factory = credential_reader = pipe_closer = None
    sink = None

    return _emit(
        stdout,
        _receipt(
            code,
            diagnostic=diagnostic,
            decode_context=decode_context,
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
    )
