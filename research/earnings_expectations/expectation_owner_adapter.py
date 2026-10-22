"""Read-only projection of Macro's existing EXP-1/K3E declared-capture inspection.

No raw captures are edited or imported. The adapter checks the canonical
semantic digest and query pin, then exposes explicit *non-admission* only.
It cannot promote a provider snapshot into sell-side consensus.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re

OWNER_SCHEMA = "k3e.declared_capture_inspection.v1"
SCHEMA = "earnings.expectation_owner_readonly_bridge.v1"
OBS_PATH = "data/revisions/expectation_observations.parquet"
ATT_PATH = "data/revisions/expectation_attempts.parquet"
UNADMITTED = {
    "UNAVAILABLE", "UNESTIMABLE", "STALE_UNAVAILABLE",
    "WITHDRAWN_UNAVAILABLE", "RIGHTS_BLOCKED",
}
CONTINUITY = {
    "ANCHOR_UNAVAILABLE", "SAME_NATIVE_PERIOD",
    "NATIVE_PERIOD_CHANGED_NO_REVISION_INFERENCE",
}


class OwnerContractError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _canonical_digest(value: object) -> str:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise OwnerContractError("INVALID_SOURCE_JSON") from exc
    return sha256(data.encode("utf-8")).hexdigest()


def _asof(value: object) -> str:
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise OwnerContractError("SOURCE_ASOF_UTC_REQUIRED")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OwnerContractError("SOURCE_ASOF_UTC_REQUIRED") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise OwnerContractError("SOURCE_ASOF_UTC_REQUIRED")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def project_owner_inspection(document: dict, *, expected_asof: str | None = None) -> dict:
    """Project a frozen K3E output as *unadmitted* expectation context.

    A future accepted baseline contract must be separately implemented and
    tested; a new non-null source value in the old contract is a refusal here.
    """
    if not isinstance(document, dict) or not isinstance(document.get("semantic_payload"), dict):
        raise OwnerContractError("SOURCE_OWNER_ENVELOPE_REQUIRED")
    payload = document["semantic_payload"]
    if payload.get("schema") != OWNER_SCHEMA:
        raise OwnerContractError("SOURCE_OWNER_SCHEMA_UNSUPPORTED")
    if document.get("semantic_digest") != _canonical_digest(payload):
        raise OwnerContractError("SOURCE_OWNER_DIGEST_MISMATCH")
    source = payload.get("source")
    query = payload.get("query")
    if not isinstance(source, dict) or not isinstance(query, dict):
        raise OwnerContractError("SOURCE_OWNER_PROVENANCE_REQUIRED")
    rev = source.get("source_revision")
    inputs = source.get("inputs")
    if not isinstance(rev, str) or not re.fullmatch(r"[0-9a-f]{40}", rev):
        raise OwnerContractError("IMMUTABLE_SOURCE_REVISION_REQUIRED")
    if not isinstance(inputs, dict):
        raise OwnerContractError("PAIRED_SOURCE_INPUT_PINS_REQUIRED")
    for path in (OBS_PATH, ATT_PATH):
        pin = inputs.get(path)
        if (not isinstance(pin, dict)
                or not isinstance(pin.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])
                or not isinstance(pin.get("git_blob_id"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", pin["git_blob_id"])):
            raise OwnerContractError("PAIRED_SOURCE_INPUT_PINS_REQUIRED")

    dimensions = ("provider", "ticker_compat", "metric", "horizon_label_raw", "as_of")
    if any(not isinstance(query.get(k), str) or not query[k].strip() for k in dimensions):
        raise OwnerContractError("SOURCE_QUERY_DIMENSIONS_REQUIRED")
    if query["metric"] not in {"EPS", "revenue"}:
        raise OwnerContractError("SOURCE_METRIC_UNSUPPORTED")
    cutoff = _asof(query["as_of"])
    if expected_asof is not None and _asof(expected_asof) != cutoff:
        raise OwnerContractError("SOURCE_QUERY_ASOF_MISMATCH")
    expected_query_id = _canonical_digest(
        {"schema": OWNER_SCHEMA, "query": query, "source": source}
    )
    if payload.get("query_identity") != expected_query_id:
        raise OwnerContractError("SOURCE_OWNER_QUERY_IDENTITY_MISMATCH")

    if (payload.get("historical_public_availability_verified") is not False
            or payload.get("historical_repository_visibility_verified") is not False):
        raise OwnerContractError("UNSUPPORTED_HISTORICAL_AVAILABILITY_CLAIM")
    legacy = document.get("input_provenance")
    if not isinstance(legacy, dict) or legacy.get("historical_population") is not False:
        raise OwnerContractError("SOURCE_HISTORY_NOT_ADMITTED")

    baseline = payload.get("normalized_baseline")
    if not isinstance(baseline, dict):
        raise OwnerContractError("SOURCE_BASELINE_BLOCK_REQUIRED")
    if baseline.get("value") is not None:
        raise OwnerContractError("NORMALIZED_BASELINE_PROMOTION_REQUIRES_NEW_CONTRACT")
    status = baseline.get("status")
    reasons = baseline.get("reasons")
    if (status not in UNADMITTED or not isinstance(reasons, list)
            or "NORMALIZED_CONSUMER_ADMISSION_NOT_GRANTED" not in reasons
            or any(not isinstance(v, str) or not v.strip() for v in reasons)):
        raise OwnerContractError("SOURCE_BASELINE_NONADMISSION_INVALID")
    rights = baseline.get("rights_state")
    if rights not in {"UNKNOWN", "RIGHTS_BLOCKED"}:
        raise OwnerContractError("RIGHTS_GRANT_NOT_ESTABLISHED")
    if payload.get("period_continuity") not in CONTINUITY:
        raise OwnerContractError("SOURCE_PERIOD_CONTINUITY_UNSUPPORTED")
    identity = payload.get("identity_gate")
    if not isinstance(identity, dict) or identity.get("contract") != "k3e.identity_gate.v1":
        raise OwnerContractError("SOURCE_IDENTITY_GATE_REQUIRED")
    denom = payload.get("denominators")
    if not isinstance(denom, dict):
        raise OwnerContractError("SOURCE_DENOMINATORS_REQUIRED")
    records = denom.get("capture_clock_bounded_relevant_records")
    if not isinstance(records, int) or isinstance(records, bool) or records < 0:
        raise OwnerContractError("SOURCE_DENOMINATORS_INVALID")

    return {
        "schema": SCHEMA,
        "source_schema": OWNER_SCHEMA,
        "source_revision": rev,
        "source_query_identity": payload["query_identity"],
        "source_digest": document["semantic_digest"],
        "provider": query["provider"],
        "ticker_compat": query["ticker_compat"],
        "metric": query["metric"],
        "horizon_label_raw": query["horizon_label_raw"],
        "source_query_asof_utc": cutoff,
        "issuer_binding": "NOT_ESTABLISHED_BY_TICKER_COMPAT_ALONE",
        "baseline_status": status,
        "baseline_value": None,
        "baseline_use": "NOT_ADMITTED",
        "reason_codes": list(dict.fromkeys(reasons)),
        "rights_state": rights,
        "period_continuity": payload["period_continuity"],
        "identity_gate_status": identity.get("status"),
        "capture_clock_bounded_relevant_records": records,
        "historical_public_availability_verified": False,
        "historical_repository_visibility_verified": False,
        "authority": "RESEARCH_DISPLAY_ONLY_NO_TRADING",
    }
