"""Closed metadata syntax/framing; these helpers authenticate nobody."""
from __future__ import annotations
import hashlib
import json
import re

SCHEMA = "mastermind.native_authorization_identity.v1"
SUBJECT_SCHEMA = "mastermind.native_authorization_subject.v1"
MAX_RESPONSE_BYTES = 1024
KINDS = frozenset({"ACQUISITION", "CONTENT"})
ROUTES = {"ACQUISITION": "/workspace/native-authorization-identity/acquisition/current",
          "CONTENT": "/workspace/native-authorization-identity/content/current"}
RESOURCES = {"ACQUISITION": "https://mcp.mastermind-x.com/workspace/read",
             "CONTENT": "https://mcp.mastermind-x.com/workspace/window/current"}
_HASH = re.compile(r"[0-9a-f]{64}\Z")

def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def comparable_account_digest(issuer_digest, subject_digest, client_ref):
    """Frame only. The integration owner MUST supply a verified principal's values.

    The resource and scopes deliberately do not participate in account identity.
    Caller dictionaries, raw subjects and unverified claims are never authority.
    """
    if not all(_hash(v) for v in (issuer_digest, subject_digest, client_ref)):
        raise ValueError("IDENTITY_INVALID")
    return hashlib.sha256(canonical({"schema": SUBJECT_SCHEMA, "issuer_digest": issuer_digest,
        "subject_digest": subject_digest, "client_ref": client_ref})).hexdigest()

def validate_body(value, expected_resource):
    """Validate/copy a bounded body; currentness and authorization remain owners'."""
    if (type(expected_resource) is not str or expected_resource not in KINDS
        or type(value) is not dict or set(value) != {"schema", "resource", "account_digest", "expires_at_ms"}
        or value["schema"] != SCHEMA or value["resource"] != expected_resource
        or not _hash(value["account_digest"]) or type(value["expires_at_ms"]) is not int
        or not 1 <= value["expires_at_ms"] <= 8_640_000_000_000_000):
        raise ValueError("IDENTITY_INVALID")
    body = dict(value)
    if len(canonical(body)) > MAX_RESPONSE_BYTES:
        raise ValueError("IDENTITY_INVALID")
    return body
