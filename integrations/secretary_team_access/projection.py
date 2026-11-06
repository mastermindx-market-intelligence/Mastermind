"""Stateless, bounded projection of the existing COO-scoped paid Fabric read.

The native catalog is PARTIAL by its owner contract. This code neither creates
an observer registry nor upgrades coverage, admission or acceptance.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from common.executive_workspace_contract import bounded_canonical, canonical
from common.executive_workspace_fabric_contract import (
    MAX_ROWS, status_metadata, validate_catalog,
)

SCHEMA = "mastermind.secretary_team_native_summary.v1"
STATUS_SCHEMA = "mastermind.secretary_team_native_status.v1"
MAX_OUTPUT_BYTES = 16_384
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def summarize_native_catalog(
    body: Any, *, previous_fingerprint: str | None = None, limit: int = 8,
) -> dict[str, Any]:
    """A partial EXPLICIT_RUN_SET view; timestamp churn does not imply change."""
    if type(limit) is not int or not 0 <= limit <= MAX_ROWS:
        raise ValueError("invalid_limit")
    if previous_fingerprint is not None and (
        type(previous_fingerprint) is not str
        or _DIGEST.fullmatch(previous_fingerprint) is None
    ):
        raise ValueError("invalid_previous_fingerprint")
    valid = validate_catalog(body)
    rows = []
    for item in valid["items"]:
        if item["status"] is None:
            rows.append({"run_id": item["run_id"], "status": None,
                         "reason_code": item["reason_code"]})
        else:
            row = item["status"]
            rows.append({
                "run_id": item["run_id"],
                "status": {
                    "state": row["state"], "rc": row["rc"], "signal": row["signal"],
                    "root_id": row["root_id"], "parent_run_id": row["parent_run_id"],
                    "result_available": row["result_available"],
                    "result_bytes": row["result_bytes"],
                    "accepted": row["accepted"], "accepted_by": row["accepted_by"],
                    "acceptance_state": row["acceptance_state"],
                    "acceptance_reason": row["acceptance_reason"],
                },
                "reason_code": None,
            })
    rows.sort(key=lambda item: item["run_id"])
    source = valid["source"]
    scope = {
        "source_revision": source["revision"],
        "source_owner": source["owner"],
        "observation_kind": source["observation_kind"],
        "source_scope": source["scope"],
        "atomic": source["atomic"],
        "coverage": valid["coverage"],
        "reasons": sorted(valid["reason_codes"]),
        "items": rows,
    }
    fingerprint = _fingerprint(scope)
    changed = None if previous_fingerprint is None else fingerprint != previous_fingerprint
    visible = [] if changed is False else rows[:limit]
    out = {
        "schema": SCHEMA, "availability": "PARTIAL", "full_fleet": False,
        "scan_complete": False, "source": {
            "owner": source["owner"], "revision": source["revision"],
            "scope": source["scope"], "atomic": False,
            "time_basis": source["time_basis"],
            "observed_at": valid["observed_at"],
        },
        "coverage": dict(valid["coverage"]), "reason_codes": sorted(valid["reason_codes"]),
        "fingerprint": fingerprint, "changed": changed,
        "items": visible, "items_visible": len(visible),
        "items_total_in_snapshot": len(rows),
        "omitted_detail_count": len(rows) - len(visible),
        "unseen_population": "UNKNOWN",
    }
    bounded_canonical(out, limit=MAX_OUTPUT_BYTES)
    return out


def summarize_native_status(body: Any, *, root_id: str, run_id: str) -> dict[str, Any]:
    """Expose only current owner-approved status fields; do not invent START."""
    from common.executive_workspace_fabric_contract import selection
    selected = selection({"root_id": root_id, "run_id": run_id})
    status = status_metadata(body, root_id=selected["root_id"], run_id=selected["run_id"])
    out = {"schema": STATUS_SCHEMA, "scope": "EXACT_RUN", "source_currentness": "UNATTESTED",
           "status": dict(status),
           "execution_is_not_acceptance": True}
    bounded_canonical(out, limit=MAX_OUTPUT_BYTES)
    return out
