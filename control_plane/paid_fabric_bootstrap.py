"""Canonical paid-account quota-status bootstrap (bounded, read-only).

SOURCE-ONLY leaf artifact.  ``bootstrap_paid_account(owner, *, account_label)``
performs exactly ONE GET against the fixed Z.ai quota/limit endpoint for the
already-selected paid account named by ``account_label`` and folds a fully
validated 5h + weekly used-percentage pair into the owner's existing
``AccountTable`` state atomically.

Hard boundaries (all deliberate):

* The production ``owner`` must be the EXACT
  ``control_plane.paid_fabric_backend.CanonicalPaidBackend`` class, imported
  at call time (never at module import, to avoid a circular import), and
  ``owner.require_gateway(owner._gateway)`` must accept the bridge both
  BEFORE and AFTER the read.  This helper performs no authorization of its
  own: the parent's kernel-Control-authenticated fixed-scope bridge callsite
  owns authorization.  The parent's real constructor additionally rechecks
  the private incumbent marker/singleton/process/context, so a fake owner
  cannot be constructed in production; this module re-verifies the exact
  type defensively anyway.

* This helper mints nothing: no AVAILABLE verdict, no grants, no leases, no
  Runtime state, no records.  A complete OBSERVED payload is a quota STATUS
  observation only -- never proof of inference readiness.  No webtools are
  modelled or implied.

* Exactly one request: ``Authorization: Bearer <key>`` only, no raw-key
  fallback, no retry, no redirect following, no ambient proxies, no alternate
  endpoints, no quota-cache fallback, no inference, no credential writes.
  Selection is NOT performed here (``table.select()`` and the generic
  ``refresh()`` path are deliberately not used).

* Secrets are never returned, hashed or echoed.  Failures are reported as a
  fixed closed enum with no exception text, URL, body or path fragments, and
  a failed/ambiguous observation always preserves the previous table reading
  untouched so the parent can never mistake it for fresh capacity.
"""

import json
import math
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "SCHEMA",
    "QUOTA_URL",
    "TIMEOUT_S",
    "MAX_BODY_BYTES",
    "STATE_OBSERVED",
    "STATE_AUTH_REFUSED",
    "STATE_RATE_LIMITED",
    "STATE_UNKNOWN",
    "REASON_OBSERVED",
    "bootstrap_paid_account",
    "validate_quota_payload",
]

SCHEMA = "mastermind.paid_quota_bootstrap/v1"

QUOTA_URL = "https://api.z.ai/api/monitor/usage/quota/limit"
TIMEOUT_S = 10
MAX_BODY_BYTES = 262144          # read at most MAX_BODY_BYTES + 1 bytes
MAX_JSON_DEPTH = 12
MAX_JSON_NODES = 4096
MAX_LIMIT_ENTRIES = 32

PCT_MIN = 0.0
PCT_MAX = 100.0
WINDOW_UNITS: Dict[int, str] = {3: "5h", 6: "weekly"}
QUOTA_ENTRY_KINDS = ("CREDIT_LIMIT", "TOKENS_LIMIT")

EXHAUST_PCT = 100.0
EXHAUST_COOLDOWN_CAP_S = 900.0   # bounded hold derived only from a full read
RATE_LIMIT_COOLDOWN_S = 300.0    # bounded cooldown reported on HTTP 429

STATE_OBSERVED = "OBSERVED"
STATE_AUTH_REFUSED = "AUTH_REFUSED"
STATE_RATE_LIMITED = "RATE_LIMITED"
STATE_UNKNOWN = "UNKNOWN"
STATES = (
    STATE_OBSERVED,
    STATE_AUTH_REFUSED,
    STATE_RATE_LIMITED,
    STATE_UNKNOWN,
)

REASON_OBSERVED = "observed_complete_pair"
REASON_INVALID_LABEL = "invalid_account_label"
REASON_OWNER_NOT_CANONICAL = "owner_not_canonical"
REASON_BRIDGE_REFUSED = "gateway_bridge_refused"
REASON_CONTEXT_UNAVAILABLE = "account_context_unavailable"
REASON_TABLE_UNAVAILABLE = "account_table_unavailable"
REASON_LABEL_UNKNOWN = "unknown_account_label"
REASON_CREDENTIAL_UNAVAILABLE = "selected_credential_unavailable"
REASON_CLOCK_UNAVAILABLE = "gateway_clock_unavailable"
REASON_GENERATION_CHANGED = "credential_generation_changed"
REASON_AUTH_REFUSED = "http_auth_refused"
REASON_RATE_LIMITED = "http_rate_limited"
REASON_REDIRECT_REFUSED = "http_redirect_refused"
REASON_BAD_STATUS = "http_bad_status"
REASON_TIMEOUT = "transport_timeout"
REASON_LOST = "transport_lost"
REASON_OVERSIZE = "body_oversize"
REASON_DECODE_FAILED = "body_decode_failed"
REASON_PAYLOAD_REJECTED = "payload_rejected"
REASON_PENDING = "status_read_pending"

REASONS = frozenset({
    REASON_OBSERVED,
    REASON_INVALID_LABEL,
    REASON_OWNER_NOT_CANONICAL,
    REASON_BRIDGE_REFUSED,
    REASON_CONTEXT_UNAVAILABLE,
    REASON_TABLE_UNAVAILABLE,
    REASON_LABEL_UNKNOWN,
    REASON_CREDENTIAL_UNAVAILABLE,
    REASON_CLOCK_UNAVAILABLE,
    REASON_GENERATION_CHANGED,
    REASON_AUTH_REFUSED,
    REASON_RATE_LIMITED,
    REASON_REDIRECT_REFUSED,
    REASON_BAD_STATUS,
    REASON_TIMEOUT,
    REASON_LOST,
    REASON_OVERSIZE,
    REASON_DECODE_FAILED,
    REASON_PAYLOAD_REJECTED,
    REASON_PENDING,
})

_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_bootstrap_result(value):
    """Strict detached non-secret DATA; never a current admission verdict."""
    expected=set(_result(STATE_UNKNOWN,REASON_CONTEXT_UNAVAILABLE,None,0))
    if type(value) is not dict or set(value)!=expected:
        raise ValueError('paid_status_result_invalid')
    if (value['schema']!=SCHEMA or value['state'] not in STATES
            or value['reason'] not in REASONS
            or (value['account_label'] is not None and _vet_label(value['account_label']) is None)
            or type(value['request_count']) is not int or value['request_count'] not in (0,1)):
        raise ValueError('paid_status_result_invalid')
    for key in ('pair_complete','fresh','committed','exhausted_5h','previous_reading_retained'):
        if type(value[key]) is not bool:raise ValueError('paid_status_result_invalid')
    for key in ('observed_at','pct_5h','pct_week','cooldown_until_ts'):
        v=value[key]
        if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v<0):
            raise ValueError('paid_status_result_invalid')
    if value['state']==STATE_OBSERVED:
        if (value['request_count']!=1 or not all(value[k] for k in ('pair_complete','fresh','committed'))
                or value['observed_at'] is None or value['observed_at']<=0
                or any(value[k] is None or value[k]>100 for k in ('pct_5h','pct_week'))):
            raise ValueError('paid_status_result_invalid')
    elif (any(value[k] for k in ('pair_complete','fresh','committed'))
            or any(value[k] is not None for k in ('observed_at','pct_5h','pct_week'))):
        raise ValueError('paid_status_result_invalid')
    return json.loads(json.dumps(value,allow_nan=False))


class _PayloadRejected(ValueError):
    """Fixed internal rejection marker; never carries payload/exception text."""


class _DuplicateKey(ValueError):
    pass


class _NonFinite(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirect policy: never follow.  3xx becomes a reported HTTPError."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _build_opener():
    """Fixed transport: no ambient proxies, no redirects, normal TLS verify."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )


def _canonical_backend_class() -> Optional[type]:
    """Exact production backend class, imported at call time.

    Late import keeps this leaf module free of a circular import with
    ``control_plane.paid_fabric_backend``; the parent wires this helper in
    through a private owner method.  Any import failure yields ``None`` and
    the caller reports a fixed refusal -- never a raw exception.
    """
    try:
        from control_plane.paid_fabric_backend import CanonicalPaidBackend
    except Exception:
        return None
    return CanonicalPaidBackend


def _vet_label(account_label: Any) -> Optional[str]:
    """Bound/vet the account label; arbitrary input is never echoed back."""
    if type(account_label) is not str:
        return None
    if not _LABEL_RE.fullmatch(account_label):
        return None
    return account_label


def _bridge(owner: Any) -> Optional[Any]:
    """Run the parent-owned ``require_gateway`` bridge; None on any refusal."""
    try:
        gateway = owner._gateway
        owner.require_gateway(gateway)
    except Exception:
        return None
    return gateway


def _table_shape_ok(table: Any) -> bool:
    return (
        isinstance(getattr(table, "_lock", None), type(threading.Lock()))
        and isinstance(getattr(table, "_accounts", None), dict)
        and isinstance(getattr(table, "_state", None), dict)
        and isinstance(getattr(table, "_last_refresh", None), dict)
    )


def _result(
    state: str,
    reason: str,
    label: Optional[str],
    request_count: int,
    *,
    observed_at: Optional[float] = None,
    pct_5h: Optional[float] = None,
    pct_week: Optional[float] = None,
    pair_complete: bool = False,
    fresh: bool = False,
    committed: bool = False,
    exhausted_5h: bool = False,
    cooldown_until_ts: Optional[float] = None,
    previous_reading_retained: bool = False,
) -> Dict[str, Any]:
    """Build the fixed closed non-secret result DATA.  Fixed keys only."""
    return {
        "schema": SCHEMA,
        "state": state,
        "reason": reason,
        "account_label": label,
        "request_count": int(request_count),
        "observed_at": observed_at,
        "pct_5h": pct_5h,
        "pct_week": pct_week,
        "pair_complete": bool(pair_complete),
        "fresh": bool(fresh),
        "committed": bool(committed),
        "exhausted_5h": bool(exhausted_5h),
        "cooldown_until_ts": cooldown_until_ts,
        "previous_reading_retained": bool(previous_reading_retained),
    }


def _record_refusal(table: Any, label: str, now: float, state_name=STATE_UNKNOWN) -> None:
    """Spend the table's refresh slot on a failed read WITHOUT touching any
    freshness field, so repeated refusals stay throttled and the previous
    reading can never look newly fresh."""
    try:
        with table._lock:
            if label in table._accounts:
                table._last_refresh[label] = float(now)
                state = table._state[label]
                state["canonical_status_state"] = state_name
                state["canonical_status_observed_at"] = None
                if state_name == STATE_RATE_LIMITED:
                    old = state.get("exhausted_until_ts")
                    if type(old) not in (int, float) or not math.isfinite(old):
                        old = 0.0
                    state["exhausted_until_ts"] = max(old, now + RATE_LIMIT_COOLDOWN_S)
    except Exception:
        pass


def _pairs_no_duplicates(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    keys = set()
    for key, _value in pairs:
        if key in keys:
            raise _DuplicateKey("duplicate")
        keys.add(key)
    return dict(pairs)


def _reject_nonfinite(token: str) -> float:
    raise _NonFinite("nonfinite")


def _check_bounds(root: Any) -> Optional[str]:
    """Iterative depth/node/nonfinite walk.  Returns a fixed reason or None."""
    stack: List[Tuple[Any, int]] = [(root, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            return REASON_PAYLOAD_REJECTED
        if isinstance(value, dict):
            if depth >= MAX_JSON_DEPTH:
                return REASON_PAYLOAD_REJECTED
            for child in value.values():
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            if depth >= MAX_JSON_DEPTH:
                return REASON_PAYLOAD_REJECTED
            for child in value:
                stack.append((child, depth + 1))
        elif isinstance(value, float) and not math.isfinite(value):
            return REASON_PAYLOAD_REJECTED
    return None


def _explicit_failure(payload: Dict[str, Any]) -> Optional[str]:
    """Reject an explicit failure envelope (``code``/``success``/``error``)."""
    if "error" in payload:
        error = payload["error"]
        if error is not None and error != "" and error != [] and error != {}:
            return REASON_PAYLOAD_REJECTED
    if "success" in payload and payload["success"] is not True:
        return REASON_PAYLOAD_REJECTED
    if "code" in payload:
        code = payload["code"]
        if isinstance(code, bool) or not isinstance(code, int) or code != 200:
            return REASON_PAYLOAD_REJECTED
    return None


def _evaluate_payload(payload: Any) -> Tuple[bool, Any]:
    """Validate one payload; (True, (pct_5h, pct_week)) or (False, reason).

    Requires a COMPLETE same-response pair: exact declared window units 3
    (5h) and 6 (weekly) inside CREDIT_LIMIT/TOKENS_LIMIT entries, finite and
    within 0..100.  Duplicates, partial pairs, ambiguous units, booleans,
    nonfinite/huge numbers, oversized/deep input and explicit failure
    envelopes are all rejected.  Missing windows are never defaulted to 0
    and never backfilled from any previous reading.
    """
    problem = _check_bounds(payload)
    if problem is not None:
        return (False, problem)
    if not isinstance(payload, dict):
        return (False, REASON_PAYLOAD_REJECTED)
    failure = _explicit_failure(payload)
    if failure is not None:
        return (False, failure)
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload
    limits = data.get("limits")
    if not isinstance(limits, list) or not limits:
        return (False, REASON_PAYLOAD_REJECTED)
    if len(limits) > MAX_LIMIT_ENTRIES:
        return (False, REASON_PAYLOAD_REJECTED)
    seen: Dict[str, float] = {}
    for item in limits:
        if not isinstance(item, dict):
            return (False, REASON_PAYLOAD_REJECTED)
        kind = item.get("type")
        if not isinstance(kind, str):
            return (False, REASON_PAYLOAD_REJECTED)
        if kind.upper() not in QUOTA_ENTRY_KINDS:
            continue
        unit = item.get("unit")
        if isinstance(unit, bool) or not isinstance(unit, int):
            return (False, REASON_PAYLOAD_REJECTED)   # ambiguous unit
        window = WINDOW_UNITS.get(unit)
        if window is None:
            return (False, REASON_PAYLOAD_REJECTED)   # undeclared unit
        if window in seen:
            return (False, REASON_PAYLOAD_REJECTED)   # duplicate window
        pct = item.get("percentage")
        if isinstance(pct, bool) or not isinstance(pct, (int, float)):
            return (False, REASON_PAYLOAD_REJECTED)   # boolean/absent
        value = float(pct)
        if not math.isfinite(value) or value < PCT_MIN or value > PCT_MAX:
            return (False, REASON_PAYLOAD_REJECTED)   # nonfinite/huge/out of bounds
        seen[window] = value
    if "5h" not in seen or "weekly" not in seen:
        return (False, REASON_PAYLOAD_REJECTED)       # partial pair
    return (True, (seen["5h"], seen["weekly"]))


def validate_quota_payload(payload: Any) -> Tuple[float, float]:
    """Pure public validation helper (no transport, no IO).

    Returns the ``(pct_5h, pct_week)`` pair or raises ``_PayloadRejected``.
    """
    ok, value = _evaluate_payload(payload)
    if not ok:
        raise _PayloadRejected(str(value))
    return value  # type: ignore[return-value]


def _parse_body(body: bytes) -> Tuple[str, Any]:
    """Parse a bounded body into ("PAYLOAD", obj) / ("REASON", fixed reason)."""
    try:
        text = bytes(body).decode("utf-8")
    except Exception:
        return ("REASON", REASON_DECODE_FAILED)
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except json.JSONDecodeError:
        return ("REASON", REASON_DECODE_FAILED)
    except (ValueError, TypeError, RecursionError, MemoryError, OverflowError):
        return ("REASON", REASON_PAYLOAD_REJECTED)
    except Exception:
        return ("REASON", REASON_PAYLOAD_REJECTED)
    return ("PAYLOAD", payload)


def _read_quota_once(key: str) -> Tuple[str, Any]:
    """Exactly ONE GET. ("PAYLOAD", obj) | ("STATUS", code) | ("REASON", reason)."""
    try:
        opener = _build_opener()
        request = urllib.request.Request(
            QUOTA_URL,
            method="GET",
            headers={
                "Authorization": "Bearer " + key,
                "Accept": "application/json",
                "Accept-Language": "en-US,en",
                "Content-Type": "application/json",
            },
        )
        deadline = time.monotonic() + TIMEOUT_S
        with opener.open(request, timeout=TIMEOUT_S) as response:
            status = int(getattr(response, "status", 200) or 200)
            body = bytearray()
            while len(body) <= MAX_BODY_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:raise TimeoutError()
                # HTTPResponse.read1 performs one underlying bounded read;
                # reduce the real socket timeout to the remaining deadline.
                read1 = getattr(response, "read1", None)
                if read1 is not None:
                    response.fp.raw._sock.settimeout(remaining)
                    chunk = read1(min(65536,MAX_BODY_BYTES+1-len(body)))
                else:
                    # Inert response fixtures implement only read(); production
                    # stdlib HTTPS responses always expose read1 + the socket.
                    from http.client import HTTPResponse
                    if isinstance(response,HTTPResponse):raise OSError()
                    chunk = response.read(MAX_BODY_BYTES+1)
                body.extend(chunk)
                if time.monotonic() > deadline:raise TimeoutError()
                if not chunk or read1 is None:break
            body=bytes(body)
    except urllib.error.HTTPError as exc:
        try:
            code = int(getattr(exc, "code", 0) or 0)
        except Exception:
            code = 0
        try:
            exc.close()
        except Exception:
            pass
        return ("STATUS", code)
    except (socket.timeout, TimeoutError):
        return ("REASON", REASON_TIMEOUT)
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
            return ("REASON", REASON_TIMEOUT)
        return ("REASON", REASON_LOST)
    except OSError:
        return ("REASON", REASON_LOST)
    except Exception:
        return ("REASON", REASON_LOST)
    if status != 200:
        return ("STATUS", status)
    if len(body) > MAX_BODY_BYTES:
        return ("REASON", REASON_OVERSIZE)
    return _parse_body(body)


def bootstrap_paid_account(owner: Any, *, account_label: Any) -> Dict[str, Any]:
    """One bounded quota-status observation for an already-selected account.

    Keyword-only ``account_label`` must be a bounded vetted identifier that
    already exists in ``owner._context.account_table``; selection itself is
    the parent's job and is never performed here.  Returns the fixed closed
    non-secret DATA described by ``SCHEMA``.  Never raises for refusal,
    transport or payload conditions; never echoes secrets, URLs, bodies,
    paths or exception text.
    """
    label = _vet_label(account_label)
    if label is None:
        return _result(STATE_UNKNOWN, REASON_INVALID_LABEL, None, 0)

    backend_cls = _canonical_backend_class()
    if backend_cls is None or type(owner) is not backend_cls:
        return _result(STATE_UNKNOWN, REASON_OWNER_NOT_CANONICAL, label, 0)

    # --- gateway bridge BEFORE any provider IO (parent owns authorization).
    gateway = _bridge(owner)
    if gateway is None:
        return _result(STATE_UNKNOWN, REASON_BRIDGE_REFUSED, label, 0)

    context = getattr(owner, "_context", None)
    if context is None:
        return _result(STATE_UNKNOWN, REASON_CONTEXT_UNAVAILABLE, label, 0)
    table = getattr(context, "account_table", None)
    if table is None or not _table_shape_ok(table):
        return _result(STATE_UNKNOWN, REASON_TABLE_UNAVAILABLE, label, 0)

    # Actual clock from the gateway; a caller-selected ``now`` is never used.
    try:
        now = float(gateway._clock())
    except Exception:
        return _result(STATE_UNKNOWN, REASON_CLOCK_UNAVAILABLE, label, 0)
    if not math.isfinite(now) or now <= 0.0:
        return _result(STATE_UNKNOWN, REASON_CLOCK_UNAVAILABLE, label, 0)

    # Read the existing selected account ONLY from the live table internals,
    # under the table's own lock.  The private config snapshot (including the
    # secret key) stays in this frame and is never returned or exported.
    with table._lock:
        info = table._accounts.get(label)
        has_state = label in table._state
        config_snapshot = dict(info) if isinstance(info, dict) else None
    if config_snapshot is None:
        return _result(STATE_UNKNOWN, REASON_LABEL_UNKNOWN, label, 0)
    if not has_state:
        return _result(STATE_UNKNOWN, REASON_TABLE_UNAVAILABLE, label, 0)
    key = config_snapshot.get("api_key")
    if not isinstance(key, str) or not key:
        return _result(STATE_UNKNOWN, REASON_CREDENTIAL_UNAVAILABLE, label, 0)

    # Close admission under the EXISTING account-state lock before status IO.
    # Concurrent requests cannot each issue a read, and generic/manual refresh
    # cannot turn an old/partial pair into canonical status provenance.
    with table._lock:
        if dict(table._accounts.get(label, {})) != config_snapshot:
            return _result(STATE_UNKNOWN, REASON_GENERATION_CHANGED, label, 0)
        state = table._state[label]
        if state.get("canonical_status_state") == "PENDING":
            return _result(STATE_UNKNOWN, REASON_PENDING, label, 0)
        state["canonical_status_state"] = "PENDING"
        state["canonical_status_observed_at"] = None
    # --- exactly one provider request -------------------------------------
    acceptance_deadline=time.monotonic()+TIMEOUT_S
    outcome_kind, outcome_value = _read_quota_once(key)
    # The actual private owner must survive every transport outcome, including
    # HTTP refusal and ambiguous/lost responses. No result is source-qualified
    # from the pre-read bridge check alone.
    if _bridge(owner) is None:
        _record_refusal(table, label, now)
        return _result(STATE_UNKNOWN, REASON_BRIDGE_REFUSED, label, 1,
                       previous_reading_retained=True)
    if outcome_kind != "PAYLOAD":
        if outcome_kind == "STATUS":
            code = outcome_value
            if code in (401, 403):
                verdict_state, reason = STATE_AUTH_REFUSED, REASON_AUTH_REFUSED
            elif code == 429:
                verdict_state, reason = STATE_RATE_LIMITED, REASON_RATE_LIMITED
            elif 300 <= code < 400:
                verdict_state, reason = STATE_UNKNOWN, REASON_REDIRECT_REFUSED
            else:
                verdict_state, reason = STATE_UNKNOWN, REASON_BAD_STATUS
        else:
            verdict_state, reason = STATE_UNKNOWN, outcome_value
        # 401/403/429/unknown must never leave the old fields looking newly
        # fresh: only the refresh slot is spent, the refusal travels in the
        # returned DATA alone.
        _record_refusal(table, label, now, verdict_state)
        cooldown_until_ts = (
            now + RATE_LIMIT_COOLDOWN_S if verdict_state == STATE_RATE_LIMITED else None
        )
        return _result(
            verdict_state,
            reason,
            label,
            1,
            cooldown_until_ts=cooldown_until_ts,
            previous_reading_retained=True,
        )

    pair_ok, pair_or_reason = _evaluate_payload(outcome_value)
    if not pair_ok:
        _record_refusal(table, label, now)
        return _result(
            STATE_UNKNOWN,
            pair_or_reason,
            label,
            1,
            previous_reading_retained=True,
        )
    pct_5h, pct_week = pair_or_reason

    # --- gateway bridge AFTER the read ------------------------------------
    if _bridge(owner) is None:
        _record_refusal(table, label, now)
        return _result(
            STATE_UNKNOWN,
            REASON_BRIDGE_REFUSED,
            label,
            1,
            previous_reading_retained=True,
        )

    # --- atomic commit: generation compare + write in ONE table lock ------
    with table._lock:
        info_now = table._accounts.get(label)
        state = table._state.get(label) if isinstance(info_now, dict) else None
        if time.monotonic()>=acceptance_deadline:
            if isinstance(state,dict):
                state["canonical_status_state"]=STATE_UNKNOWN
                state["canonical_status_observed_at"]=None
            return _result(STATE_UNKNOWN,REASON_TIMEOUT,label,1,previous_reading_retained=True)
        if (
            not isinstance(info_now, dict)
            or not isinstance(state, dict)
            or dict(info_now) != config_snapshot
        ):
            # The selected credential/account generation changed during IO:
            # No new percentage/timestamp is committed. Canonical admission
            # stays UNKNOWN even if the old manual reading is still fresh.
            if isinstance(state, dict):
                state["canonical_status_state"] = STATE_UNKNOWN
                state["canonical_status_observed_at"] = None
            return _result(
                STATE_UNKNOWN,
                REASON_GENERATION_CHANGED,
                label,
                1,
                previous_reading_retained=True,
            )
        exhausted_5h = pct_5h >= EXHAUST_PCT
        cooldown_until_ts: Optional[float] = None
        if exhausted_5h:
            cooldown_until_ts = now + EXHAUST_COOLDOWN_CAP_S
            try:
                existing_hold = float(state.get("exhausted_until_ts") or 0.0)
            except (TypeError, ValueError):
                existing_hold = 0.0
            # Raise-only: a still-valid owner hold is never shortened/cleared.
            if cooldown_until_ts > existing_hold:
                state["exhausted_until_ts"] = float(cooldown_until_ts)
        state["last_pct_5h"] = float(pct_5h)
        state["last_pct_week"] = float(pct_week)
        state["observed_at"] = float(now)
        state["canonical_status_state"] = STATE_OBSERVED
        state["canonical_status_observed_at"] = float(now)
        table._last_refresh[label] = float(now)

    return _result(
        STATE_OBSERVED,
        REASON_OBSERVED,
        label,
        1,
        observed_at=float(now),
        pct_5h=float(pct_5h),
        pct_week=float(pct_week),
        pair_complete=True,
        fresh=True,
        committed=True,
        exhausted_5h=bool(exhausted_5h),
        cooldown_until_ts=cooldown_until_ts,
    )
