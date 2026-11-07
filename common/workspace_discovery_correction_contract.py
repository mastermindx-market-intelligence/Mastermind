"""Closed discovery-correction values and derived paths, never an owner or grant.

The canonical Macro compiler owns record semantics. This shared boundary keeps
the original Workspace transport, Events and Git publisher on one request and
lookup shape. A digest is an identity check, not source or action authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

ACTION = "correct_project_discovery"
RECIPE_ACTION = "project_discovery_correct"
REQUEST_SCHEMA = "mastermind.project_discovery_correct_request.v1"
REQUEST_PREFIX = "mmos-project-discovery-correct-"
REQUEST_KEYS = frozenset({"schema", "request_id", "work_ref", "source_commit",
    "base_revision", "discovery_ref", "expected_discovery_revision",
    "correction_reason", "replacement"})
LOOKUP_KEYS = frozenset({"action", "request_id", "work_ref", "source_commit",
    "base_revision", "request_sha256", "discovery_ref", "expected_discovery_revision"})
REPLACEMENT_KEYS = frozenset({"claim", "falsifier", "so_what", "kind",
    "confidence", "verified_at", "verified_by", "expires", "body_utf8", "evidence"})
KINDS = frozenset({"architecture", "data", "landmine", "dead_code", "constraint", "runtime"})
MAX_REQUEST_BYTES = 24 * 1024


def _fail():
    raise ValueError("invalid_project_discovery_correction")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hex(value, size):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(size) + r"}", value) is None:
        _fail()


def valid_ref(value, prefix):
    return (type(value) is str and value.startswith(prefix)
        and 2 <= len(value[len(prefix):]) <= 64
        and re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", value[len(prefix):]) is not None)


def _identity(value):
    if (type(value["request_id"]) is not str
            or re.fullmatch(re.escape(REQUEST_PREFIX) + r"[0-9a-f]{40}", value["request_id"]) is None
            or not valid_ref(value["work_ref"], "WS:")
            or not valid_ref(value["discovery_ref"], "DSC:")):
        _fail()
    _hex(value["source_commit"], 40)
    _hex(value["base_revision"], 64)
    _hex(value["expected_discovery_revision"], 64)


def _text(value, limit):
    if (type(value) is not str or not value.strip()
            or len(value.encode("utf-8")) > limit
            or any((ord(c) < 32 and c not in "\n\r\t") or 127 <= ord(c) <= 159 for c in value)):
        _fail()


def validate_request(value):
    try:
        if type(value) is not dict or set(value) != REQUEST_KEYS or value["schema"] != REQUEST_SCHEMA:
            _fail()
        _identity(value)
        _text(value["correction_reason"], 2048)
        replacement = value["replacement"]
        if type(replacement) is not dict or set(replacement) != REPLACEMENT_KEYS:
            _fail()
        for key in ("claim", "falsifier", "so_what", "verified_by"):
            _text(replacement[key], 2048)
        for key in ("verified_at", "expires"):
            value_date = replacement[key]
            if key == "expires" and value_date is None:
                continue
            if type(value_date) is not str or date.fromisoformat(value_date).isoformat() != value_date:
                _fail()
        if replacement["expires"] is not None and replacement["expires"] < replacement["verified_at"]:
            _fail()
        body = replacement["body_utf8"]
        if type(body) is not str or len(body.encode("utf-8")) > 8192:
            _fail()
        if body:
            _text(body, 8192)
        if type(replacement["kind"]) is not str or replacement["kind"] not in KINDS:
            _fail()
        if type(replacement["confidence"]) is not str or replacement["confidence"] not in {"verified", "probable", "suspected"}:
            _fail()
        evidence = replacement["evidence"]
        if type(evidence) is not list or not 1 <= len(evidence) <= 8:
            _fail()
        for item in evidence:
            _text(item, 1024)
        if (len(set(evidence)) != len(evidence) or len(canonical(replacement)) > 16 * 1024
                or len(canonical(value)) > MAX_REQUEST_BYTES):
            _fail()
        return json.loads(canonical(value))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        _fail()


def request_lookup(value):
    value = validate_request(value)
    return {"action": ACTION, **{key: value[key] for key in (
        "request_id", "work_ref", "source_commit", "base_revision",
        "discovery_ref", "expected_discovery_revision")},
        "request_sha256": hashlib.sha256(canonical(value)).hexdigest()}


def validate_lookup(value):
    try:
        if type(value) is not dict or set(value) != LOOKUP_KEYS or value["action"] != ACTION:
            _fail()
        _identity(value)
        _hex(value["request_sha256"], 64)
        return dict(value)
    except (ValueError, TypeError, KeyError, UnicodeError):
        _fail()


def replacement_ref(value, principal_scope):
    _hex(principal_scope, 64)
    material = {"principal_scope": principal_scope, "request_id": value["request_id"],
                "work_ref": value["work_ref"]}
    return "DSC:PROJECT-CORRECTION-" + hashlib.sha256(canonical(material)).hexdigest()[:40].upper()


def expected_paths(value, principal_scope):
    new = replacement_ref(value, principal_scope)
    if new == value["discovery_ref"]:
        _fail()
    return ["agentos/discoveries/DSC-" + value["discovery_ref"][4:] + ".md",
            "agentos/discoveries/DSC-" + new[4:] + ".md",
            "agentos/workstreams/WS-" + value["work_ref"][3:] + ".md"]


def expected_preimages(value, principal_scope):
    old, new, ws = expected_paths(value, principal_scope)
    return {old: value["expected_discovery_revision"], new: None, ws: value["base_revision"]}


def preview_change(value, principal_scope):
    value = validate_request(value)
    return {"kind": "DISCOVERY_CORRECTION", "discovery_ref": value["discovery_ref"],
        "replacement_ref": replacement_ref(value, principal_scope),
        "correction_reason": value["correction_reason"], "replacement": value["replacement"]}


def validate_sources(selection, principal_scope, sources):
    """Public shape only; actual publication remains the original Event proof."""
    if type(sources) is not list or len(sources) != 3:
        _fail()
    paths = {source["path"] for source in sources}
    new = "agentos/discoveries/DSC-" + replacement_ref(selection, principal_scope)[4:] + ".md"
    ws = "agentos/workstreams/WS-" + selection["work_ref"][3:] + ".md"
    others = paths - {ws, new}
    if len(paths) != 3 or ws not in paths or new not in paths or len(others) != 1:
        _fail()
    old = next(iter(others))
    prefix = "agentos/discoveries/DSC-"
    if not old.startswith(prefix) or not old.endswith(".md") or not valid_ref("DSC:" + old[len(prefix):-3], "DSC:"):
        _fail()
