"""Closed read-only delivery contract for original-owner cleanup records.

This adds no evidence producer. The authenticated backend must retrieve actual
retained bytes twice; it must never census, signal, seal, restamp or release a
lease to answer this status query. Passing is group cleanup, not revocation.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
import hashlib
import json
import math

from control_plane.fabric_cleanup_contract import validate_fabric_cleanup_receipt
from control_plane.worker_execution_contract import WorkerProcessRef

SCOPES = frozenset({"collection", "validation", "terminal", "restart_absence", "unbound_absence"})
SCHEMA = "mastermind.executive_fabric_cleanup_query/v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def stamp(value):
    if type(value) is not str:
        raise ValueError("missing observation time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observation time has no zone")
    return parsed.timestamp()


def validate_query(query, *, run_id):
    if type(query) is not dict or set(query) != {
        "schema_version", "scope", "process_ref", "host_ref", "observed_after", "readback_sha256"
    }:
        raise ValueError("closed cleanup query required")
    if query["schema_version"] != SCHEMA or query["scope"] not in SCOPES:
        raise ValueError("unsupported cleanup query")
    ref = query["process_ref"]
    if (type(ref) is not dict or set(ref) != {f.name for f in dataclasses.fields(WorkerProcessRef)}
            or ref["run_id"] != run_id):
        raise ValueError("foreign cleanup process")
    for field in ("effective_uid", "effective_gid", "pid", "pgid", "session_id"):
        if type(ref[field]) is not int or ref[field] <= 0:
            raise ValueError("incomplete cleanup process")
    for value in (ref["boot_session_id"], ref["process_start_identity"], query["host_ref"]):
        if type(value) is not str or not value or len(value) > 512:
            raise ValueError("incomplete cleanup generation")
    after = query["observed_after"]
    if type(after) not in (int, float) or not math.isfinite(after) or after < stamp(ref["started_at"]):
        raise ValueError("invalid cleanup observation floor")
    sha = query["readback_sha256"]
    if sha is not None and (type(sha) is not str or len(sha) != 64
                            or any(c not in "0123456789abcdef" for c in sha)):
        raise ValueError("invalid cleanup readback selector")
    canonical(query)


def validate_package(package, *, query, binding, physical_digest, observed_before):
    validate_query(query, run_id=binding["attempt_id"])
    if type(package) is not dict or set(package) != {
        "schema_version", "operation", "observed_at", "worker_uid", "worker_gid",
        "receipt", "lane_receipt_utf8"
    }:
        raise ValueError("closed cleanup package required")
    ref = query["process_ref"]
    observed = stamp(package["observed_at"])
    if (package["schema_version"] != "mastermind.executive_fabric_cleanup_evidence/v1"
            or package["operation"] != query["scope"]
            or not query["observed_after"] <= observed <= observed_before
            or type(package["lane_receipt_utf8"]) is not str):
        raise ValueError("stale or foreign cleanup observation")
    for target, source in (("worker_uid", "effective_uid"), ("worker_gid", "effective_gid")):
        if type(package[target]) is not int or package[target] != ref[source]:
            raise ValueError("cleanup principal mismatch")
    identity = {key: ref[key] for key in
                ("boot_session_id", "pid", "pgid", "session_id", "process_start_identity")}
    identity["host_ref"] = query["host_ref"]
    raw = package["lane_receipt_utf8"].encode("utf-8", errors="strict")
    validate_fabric_cleanup_receipt(package["receipt"], expected_binding=binding,
        expected_physical_binding_sha256=physical_digest,
        expected_process_identity=identity, lane_receipt_bytes=raw)
    if stamp(json.loads(raw)["ended_at"]) > observed:
        raise ValueError("observation predates its retained record")
    if query["readback_sha256"] is not None and digest(package) != query["readback_sha256"]:
        raise ValueError("original cleanup readback changed")
    return json.loads(canonical(package))
