"""Original correction note projection: retained custody, never current DATA."""
from __future__ import annotations

import hashlib
import json
import re

from common import workspace_discovery_correction_contract as correction
from common.workspace_project_knowledge_contract import MAX_SOURCE_BODY

SCHEMA = "mastermind.workspace_project_discovery_original.v1"
MAX_RESPONSE_BYTES = 128 * 1024


def validate(value, *, lookup, principal_scope):
    """Only the authenticated owner may supply the witness and exact old body."""
    from common.workspace_source_operation_wire import validate_witness
    selected = correction.validate_lookup(lookup)
    if (type(principal_scope) is not str or re.fullmatch(r"[0-9a-f]{64}", principal_scope) is None
            or type(value) is not dict
            or set(value) != {"schema", "selection", "owner_context", "custody", "original"}
            or value["schema"] != SCHEMA or value["selection"] != selected
            or value["owner_context"] != {"principal_scope": principal_scope}):
        raise ValueError("invalid_discovery_original")
    custody, original = value["custody"], value["original"]
    if (type(custody) is not dict or set(custody) != {"kind", "original_input", "recipe_fingerprint_sha256"}
            or custody["kind"] != "ORIGINAL_CORRECTION_INPUT"):
        raise ValueError("invalid_discovery_original")
    validate_witness({key: custody[key] for key in ("original_input", "recipe_fingerprint_sha256")})
    if custody["recipe_fingerprint_sha256"] == selected["request_sha256"]:
        raise ValueError("invalid_discovery_original")
    if (type(original) is not dict
            or set(original) != {"source_commit", "discovery_ref", "content_sha256", "workstream_sha256", "media_type", "content_utf8"}
            or original["source_commit"] != selected["source_commit"]
            or original["discovery_ref"] != selected["discovery_ref"]
            or original["workstream_sha256"] != selected["base_revision"]
            or original["content_sha256"] != selected["expected_discovery_revision"]
            or original["media_type"] != "text/markdown" or type(original["content_utf8"]) is not str):
        raise ValueError("invalid_discovery_original")
    raw = original["content_utf8"].encode("utf-8")
    if (not 0 < len(raw) <= MAX_SOURCE_BODY or hashlib.sha256(raw).hexdigest() != original["content_sha256"]
            or any((ord(c) < 32 and c not in "\r\n\t") or 127 <= ord(c) <= 159 for c in original["content_utf8"])):
        raise ValueError("invalid_discovery_original")
    encoded = correction.canonical(value)
    if len(encoded) + 1 > MAX_RESPONSE_BYTES:
        raise ValueError("invalid_discovery_original")
    return json.loads(encoded)
