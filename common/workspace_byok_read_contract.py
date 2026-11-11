"""Closed metadata-only read for the two installed Hermes roles.

The trusted host supplies one current observation of the pair. This contract
does not discover a host, read credentials, enroll a role, or call a provider.
Configuration evidence is deliberately separate from connection/turn proof.
"""
from __future__ import annotations

import json
import re

from common.executive_workspace_contract import (
    FRAME_SCHEMA as WORKSPACE_SCHEMA, MAX_REQUEST_BYTES, bounded_canonical,
    canonical, validate_frame as validate_workspace_frame,
)

FRAME_SCHEMA = "mastermind.workspace_byok_roles_read.v1"
BODY_SCHEMA = "mastermind.workspace_byok_roles.v1"
OPERATION = "roles"
MAX_RESPONSE_BYTES = 8192
MAX_OBSERVATION_AGE_MS = 30_000
ROLES = ("mmmeta", "mmsecretary")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SHA = re.compile(r"[0-9a-f]{40}")
_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_PROOF_KEYS = frozenset({"credentials_read", "provider_called", "service_observed",
                         "served_model_verified", "credential_enrollment"})
_UNAVAILABLE = frozenset({"SOURCE_UNBOUND", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_STALE"})


def validate_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "principal"}
            or value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION
            or len(canonical(value)) + 1 > MAX_REQUEST_BYTES):
        raise ValueError("invalid_input")
    validate_workspace_frame({"schema": WORKSPACE_SCHEMA, "operation": "programs",
                              "selection": None, "principal": value["principal"]})
    return value


def proof():
    return {"credentials_read": False, "provider_called": False,
            "service_observed": False, "served_model_verified": False,
            "credential_enrollment": "UNVERIFIED"}


def unavailable(reason="SOURCE_UNAVAILABLE"):
    if reason not in _UNAVAILABLE:
        raise ValueError("invalid_input")
    return {"schema": BODY_SCHEMA,
            "state": "SOURCE_UNBOUND" if reason == "SOURCE_UNBOUND" else "UNAVAILABLE",
            "reason_code": reason, "roles": [], "source_observation": None, "proof": proof()}


def _matches(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def validate_body(value):
    """Validate and detach the public document; never project unknown fields."""
    if (type(value) is not dict or set(value) != {
            "schema", "state", "reason_code", "roles", "source_observation", "proof"}
            or value["schema"] != BODY_SCHEMA or type(value["roles"]) is not list):
        raise ValueError("source_unavailable")
    evidence = value["proof"]
    if (type(evidence) is not dict or set(evidence) != _PROOF_KEYS
            or evidence["credential_enrollment"] != "UNVERIFIED"
            or any(evidence[key] is not False for key in _PROOF_KEYS - {"credential_enrollment"})):
        raise ValueError("source_unavailable")
    if value["state"] != "OBSERVED":
        reason = value["reason_code"]
        if (type(reason) is not str or reason not in _UNAVAILABLE
                or value != unavailable(reason)):
            raise ValueError("source_unavailable")
    else:
        if value["reason_code"] != "OBSERVED" or len(value["roles"]) != 2:
            raise ValueError("source_unavailable")
        for expected, row in zip(ROLES, value["roles"]):
            if (type(row) is not dict or set(row) != {
                    "role", "state", "requested_provider", "requested_model"}
                    or row["role"] != expected
                    or type(row["state"]) is not str
                    or row["state"] not in {"ABSENT", "CONFIGURATION_OBSERVED", "UNAVAILABLE"}):
                raise ValueError("source_unavailable")
            if row["state"] == "CONFIGURATION_OBSERVED":
                if not all(_matches(row[key], _IDENTIFIER)
                           for key in ("requested_provider", "requested_model")):
                    raise ValueError("source_unavailable")
            elif row["requested_provider"] is not None or row["requested_model"] is not None:
                raise ValueError("source_unavailable")
        source = value["source_observation"]
        if (type(source) is not dict or set(source) != {
                "host_binding_sha256", "host_boot_id", "implementation_sha",
                "metadata_sha256", "observed_at_ms"}
                or not _matches(source["host_binding_sha256"], _HEX64)
                or not _matches(source["host_boot_id"], _BOOT)
                or not _matches(source["implementation_sha"], _SHA)
                or not _matches(source["metadata_sha256"], _HEX64)
                or type(source["observed_at_ms"]) is not int
                or not 0 < source["observed_at_ms"] <= 9_007_199_254_740_991):
            raise ValueError("source_unavailable")
    encoded = bounded_canonical({"ok": True, "result": value}, limit=MAX_RESPONSE_BYTES - 1)
    return json.loads(encoded)["result"]


def current(value, *, now_ms):
    """A transport timestamp cannot renew the producer's original observation."""
    return (value["state"] != "OBSERVED" or
            (type(now_ms) is int and
             -5_000 <= now_ms - value["source_observation"]["observed_at_ms"] <= MAX_OBSERVATION_AGE_MS))
