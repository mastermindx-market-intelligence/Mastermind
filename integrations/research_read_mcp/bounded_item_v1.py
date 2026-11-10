"""Versioned complete bounded-item display contract shared by HTTP and MCP.

Pure projection only. Canonical descriptor replay, source/visibility qualification
and authority remain with the incumbent resolver and authenticated consumer.
"""
from __future__ import annotations
import json
import re

ORIGIN = "https://mcp.mastermind-x.com"
PREFIX = "/os/research/evidence/"
_ID = re.compile(r"rvitem\.v1\.[0-9a-f]{64}\Z")
ITEM_ID_REGEX = _ID
MAX_WIRE_BYTES = 16000
ITEM_ID_SCHEMA_PATTERN = r"^rvitem\.v1\.[0-9a-f]{64}$"
ITEM_URL_SCHEMA_PATTERN = r"^https://mcp\.mastermind-x\.com/os/research/evidence/rvitem\.v1\.[0-9a-f]{64}$"

class EvidenceResponseRefused(ValueError):
    def __init__(self):
        super().__init__("EVIDENCE_RESPONSE_REFUSED")


def _scalar(value, *, maximum):
    if type(value) is not str or not value or len(value) > maximum:
        raise EvidenceResponseRefused()
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise EvidenceResponseRefused() from None
    if len(raw) > maximum:
        raise EvidenceResponseRefused()
    return value


def evidence_wire(value, item_id, quote_limit):
    """Closed display DTO. Provenance stays inside the reviewed resolver seam.

    Refuse a whole item exceeding the current grant; never trim or normalize it.
    The resolver is responsible for canonical descriptor replay and visibility.
    """
    if (type(value) is not dict or set(value) != {"id", "title", "text", "url", "metadata"}
            or type(item_id) is not str or _ID.fullmatch(item_id) is None
            or value["id"] != item_id or value["url"] != ORIGIN + PREFIX + item_id
            or type(value["metadata"]) is not dict
            or value["metadata"] != {"coverage": "COMPLETE_BOUNDED_ITEM"}
            or type(quote_limit) is not int or quote_limit <= 0):
        raise EvidenceResponseRefused()
    title = _scalar(value["title"], maximum=1000)
    text = _scalar(value["text"], maximum=1000)
    if not title.strip() or len(text) > min(1200, quote_limit):
        raise EvidenceResponseRefused()
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_WIRE_BYTES:
        raise EvidenceResponseRefused()
    return raw



def canonical_item_url(item_id):
    if type(item_id) is not str or _ID.fullmatch(item_id) is None:
        raise EvidenceResponseRefused()
    return ORIGIN + PREFIX + item_id


def item_reference(value):
    """Closed search metadata, using the exact shared identity/title/URL rules."""
    if (type(value) is not dict or set(value) != {"id", "title", "url"}
            or value["url"] != canonical_item_url(value["id"])):
        raise EvidenceResponseRefused()
    title = _scalar(value["title"], maximum=1000)
    if not title.strip():
        raise EvidenceResponseRefused()
    return {"id": value["id"], "title": title, "url": value["url"]}


ITEM_REFERENCE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "title", "url"],
    "properties": {"id": {"type": "string", "pattern": ITEM_ID_SCHEMA_PATTERN},
                   "title": {"type": "string", "minLength": 1, "maxLength": 1000},
                   "url": {"type": "string", "pattern": ITEM_URL_SCHEMA_PATTERN}},
}
COMPLETE_ITEM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "title", "text", "url", "metadata"],
    "properties": {**ITEM_REFERENCE_SCHEMA["properties"],
        "text": {"type": "string", "minLength": 1, "maxLength": 1000},
        "metadata": {"type": "object", "additionalProperties": False,
                     "required": ["coverage"], "properties": {
                         "coverage": {"const": "COMPLETE_BOUNDED_ITEM"}}}},
}
