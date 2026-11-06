"""Pure closed receipt law for the existing Runtime workstream admission gate.

Actor labels identify requests and confer no authorization. Only the original
Runtime transaction may publish a committed receipt. There is no store, clock,
controller, resume operation or default permission in this module.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import wraps

REQUEST_SCHEMA = "mastermind.workstream_admission_suspension.request.v1"
PAYLOAD_SCHEMA = "mastermind.workstream_admission_suspension.v1"
RECEIPT_SCHEMA = "mastermind.workstream_admission_suspension_receipt.v1"
ERROR = "WORKSTREAM_SUSPENSION_INVALID"
_WORK = re.compile(r"WS:[A-Z0-9][A-Za-z0-9._-]{1,63}")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def _closed(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, OverflowError, RecursionError, KeyError):
            raise ValueError(ERROR) from None
    return checked


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _token(value):
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise ValueError(ERROR)
    return value


@_closed
def canonical_work_ref(value):
    if type(value) is not str or _WORK.fullmatch(value) is None:
        raise ValueError(ERROR)
    return value


@_closed
def make_pause_request(work_ref, command_id, actor):
    return {"schema": REQUEST_SCHEMA, "operation": "pause", "work_ref": canonical_work_ref(work_ref),
            "command_id": _token(command_id), "actor": _token(actor)}


def _request(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "work_ref", "command_id", "actor"}
            or value["schema"] != REQUEST_SCHEMA or value["operation"] != "pause"):
        raise ValueError(ERROR)
    return make_pause_request(value["work_ref"], value["command_id"], value["actor"])


@_closed
def request_digest(request):
    return hashlib.sha256(_canonical(_request(request))).hexdigest()


@_closed
def make_pause_payload(request):
    checked = _request(request)
    return {"schema": PAYLOAD_SCHEMA, "state": "PAUSED", "work_ref": checked["work_ref"],
            "request_digest": request_digest(checked)}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(ERROR)
        result[key] = value
    return result


@_closed
def parse_suspension_event(event):
    if type(event) is not dict or set(event) != {
            "event_id", "aggregate_type", "aggregate_id", "event_type", "command_id", "actor", "payload_json", "created_at_ms"}:
        raise ValueError(ERROR)
    work_ref = canonical_work_ref(event["aggregate_id"])
    command, actor = _token(event["command_id"]), _token(event["actor"])
    if (event["aggregate_type"] != "workstream" or event["event_type"] != "WORKSTREAM_ADMISSION_SUSPENDED"
            or type(event["event_id"]) is not int or event["event_id"] <= 0
            or type(event["created_at_ms"]) is not int or event["created_at_ms"] < 0
            or type(event["payload_json"]) is not str):
        raise ValueError(ERROR)
    raw = event["payload_json"].encode("utf-8")
    if len(raw) > 4096:
        raise ValueError(ERROR)
    payload = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError(ERROR)))
    expected = make_pause_payload(make_pause_request(work_ref, command, actor))
    if payload != expected or _canonical(payload) != raw:
        raise ValueError(ERROR)
    return {"schema": RECEIPT_SCHEMA, "work_ref": work_ref, "state": "PAUSED",
            "event_id": event["event_id"], "command_id": command,
            "request_digest": expected["request_digest"], "committed_at_ms": event["created_at_ms"]}
