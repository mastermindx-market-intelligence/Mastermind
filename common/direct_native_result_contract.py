"""Closed direct-native result DATA; validation grants no access or acceptance.

The existing Runtime owns terminal meaning and consumption Events. This module
does not open a source, authenticate a principal, or turn display into consent.
"""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "mastermind.direct_native_result_response.v1"
PRIVATE_SCHEMA = "mastermind.ceo_ingress.direct_native.v1"
MAX_RESPONSE_BYTES = 24576
MAX_REQUEST_BYTES = 4096
RESULT_PATH = "/os/executive/direct-native/result"
CONSUME_PATH = "/os/executive/direct-native/consume"
REASON_CODES = frozenset({
    "INVALID_SELECTION", "AUTHORITY_UNAVAILABLE", "SOURCE_UNAVAILABLE",
    "NOT_TERMINAL", "CONTENT_OVER_BUDGET", "CONSUMPTION_CONFLICT", "EFFECT_UNKNOWN",
})
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SELECTION_KEYS = frozenset({"work_ref", "job_id", "attempt_id"})
PAYLOAD_KEYS = frozenset({"summary", "current_state", "completed_steps", "next_actions"})


class DirectResultContractError(ValueError):
    """Fixed public error without underlying source/credential diagnostics."""


def _refuse():
    raise DirectResultContractError("direct-native result contract refused")


def canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def identifier(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        _refuse()
    return value


def hex_digest(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _refuse()
    return value


def _text(value, limit, *, content=False):
    if type(value) is not str or len(value) > limit:
        _refuse()
    if not content and (not value or value != value.strip()):
        _refuse()
    if any((ord(c) < 32 and not (content and c in "\n\t")) or ord(c) == 127 for c in value):
        _refuse()
    canonical_bytes(value)  # Reject lone surrogates, not just long Python text.
    return value


def validate_selection(value, *, allow_current=False):
    if type(value) is not dict or set(value) != SELECTION_KEYS:
        _refuse()
    return dict(work_ref=_text(value["work_ref"], 512),
                job_id=identifier(value["job_id"]), attempt_id=(None if allow_current and value["attempt_id"] is None else identifier(value["attempt_id"])))


def validate_request(value, *, consume=False):
    keys = SELECTION_KEYS | ({"result_digest", "operation_key"} if consume else set())
    if type(value) is not dict or set(value) != keys:
        _refuse()
    selected = validate_selection({k: value[k] for k in SELECTION_KEYS}, allow_current=not consume)
    if consume:
        selected.update(result_digest=hex_digest(value["result_digest"]),
                        operation_key=identifier(value["operation_key"]))
    if len(canonical_bytes(selected)) > MAX_REQUEST_BYTES:
        _refuse()
    return selected


def validate_private_frame(value):
    """Shape only. Only the actual fixed App peer may supply this frame."""
    if type(value) is not dict or value.get("schema") != PRIVATE_SCHEMA:
        _refuse()
    operation = value.get("operation")
    if operation not in {"result", "consume"}:
        _refuse()
    base = {"schema", "operation", "principal_scope"}
    body = {k: v for k, v in value.items() if k not in base}
    request = validate_request(body, consume=operation == "consume")
    if set(value) != base | set(request):
        _refuse()
    return dict(request, schema=PRIVATE_SCHEMA, operation=operation,
                principal_scope=hex_digest(value["principal_scope"]))


def validate_payload(value):
    if type(value) is not dict or set(value) != PAYLOAD_KEYS:
        _refuse()
    result = {k: _text(value[k], 4096, content=True) for k in ("summary", "current_state")}
    for name in ("completed_steps", "next_actions"):
        items = value[name]
        if type(items) is not list or len(items) > 32:
            _refuse()
        result[name] = [_text(item, 256, content=True) for item in items]
    return result


def validate_consumption(value):
    if type(value) is not dict or set(value) != {"state", "receipt_digest"}:
        _refuse()
    if value["state"] == "UNCONSUMED" and value["receipt_digest"] is None:
        return dict(state="UNCONSUMED", receipt_digest=None)
    if value["state"] == "CONSUMED":
        return dict(state="CONSUMED", receipt_digest=hex_digest(value["receipt_digest"]))
    _refuse()


def validate_response(value):
    if type(value) is not dict or set(value) != {
        "schema", "selection", "availability", "reason_codes", "result", "consumption"
    } or value["schema"] != SCHEMA:
        _refuse()
    selected = validate_selection(value["selection"], allow_current=value["availability"] == "UNAVAILABLE")
    reasons = value["reason_codes"]
    if type(reasons) is not list:
        _refuse()
    if value["availability"] == "AVAILABLE":
        item = value["result"]
        if reasons or type(item) is not dict or set(item) != PAYLOAD_KEYS | {"result_digest"}:
            _refuse()
        result = validate_payload({k: item[k] for k in PAYLOAD_KEYS})
        result["result_digest"] = hex_digest(item["result_digest"])
        consumption = validate_consumption(value["consumption"])
    elif value["availability"] == "UNAVAILABLE":
        if (not reasons or len(reasons) > len(REASON_CODES)
                or any(type(r) is not str or r not in REASON_CODES for r in reasons)
                or len(set(reasons)) != len(reasons)
                or value["result"] is not None or value["consumption"] is not None):
            _refuse()
        result = consumption = None
    else:
        _refuse()
    result = dict(schema=SCHEMA, selection=selected, availability=value["availability"],
                  reason_codes=list(reasons), result=result, consumption=consumption)
    if len(canonical_bytes(result)) > MAX_RESPONSE_BYTES:
        _refuse()
    return result


def unavailable(selection, reason):
    return validate_response(dict(schema=SCHEMA, selection=selection,
        availability="UNAVAILABLE", reason_codes=[reason], result=None, consumption=None))


def available(selection, payload, terminal_digest, consumption):
    return validate_response(dict(schema=SCHEMA, selection=selection,
        availability="AVAILABLE", reason_codes=[],
        result=dict(validate_payload(payload), result_digest=hex_digest(terminal_digest)),
        consumption=consumption))


def decode_response(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE_BYTES:
        _refuse()
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                _refuse()
            obj[key] = value
        return obj
    def nonfinite(_value):
        _refuse()
    try:
        return validate_response(json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                                            parse_constant=nonfinite))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()
