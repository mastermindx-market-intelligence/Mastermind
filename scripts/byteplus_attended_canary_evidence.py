#!/usr/bin/env python3
"""Offline, non-authoritative evidence completeness check for attended BytePlus.

This intentionally does NOT mint canary, Capacity, ProviderRealm, quota, or
production receipts. Inputs are operator-supplied/redacted. No network or
credential access, no subprocess, no provider call and no permanent state.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Mapping

from control_plane.subscription_provider_profiles import get_profile

SCHEMA = "mastermind.byteplus_attended_coding_evidence.v1"
BINDING = "byteplus-coding-plan-personal.claude-code-anthropic"
ENDPOINT = "https://ark.ap-southeast.bytepluses.com/api/coding"
WINDOWS = ("session", "weekly", "monthly")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class CanaryEvidenceInputError(ValueError):
    """Untrusted operator evidence cannot be safely parsed."""


def _keys(value: Any, expected: set[str], where: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise CanaryEvidenceInputError(f"invalid {where} structure")
    return value


def _hash_or_none(value: Any, where: str) -> None:
    if value is not None and (type(value) is not str or not HEX64.fullmatch(value)):
        raise CanaryEvidenceInputError(f"invalid {where} digest")


def _stamp_or_none(value: Any, where: str) -> None:
    if value is not None and (type(value) is not int or value <= 0):
        raise CanaryEvidenceInputError(f"invalid {where} timestamp")


def _reset_or_none(value: Any) -> None:
    if value is None:
        return
    if type(value) is not str or len(value) > 45:
        raise CanaryEvidenceInputError("invalid window reset")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CanaryEvidenceInputError("invalid window reset") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise CanaryEvidenceInputError("timezone required for window reset")


def _snapshot(raw: Any, label: str) -> Mapping[str, Any]:
    row = _keys(raw, {"observed_at_unix", "used_percent_rounded", "reset_at"}, label)
    _stamp_or_none(row["observed_at_unix"], label)
    for field in ("used_percent_rounded", "reset_at"):
        values = _keys(row[field], set(WINDOWS), label + "." + field)
        for period in WINDOWS:
            value = values[period]
            if field == "used_percent_rounded":
                if value is not None and (type(value) is not int or not 0 <= value <= 100):
                    raise CanaryEvidenceInputError("invalid quota percentage")
            else:
                _reset_or_none(value)
    return row


def inspect_attended_evidence(document: Any) -> dict[str, Any]:
    """Validate exact redacted shape; NEVER attest an evidence source.

    Even a full synthetic or self-reported document cannot enable provider
    admission, prove a provider debit, or grant a worker slot.
    """
    d = _keys(document, {"schema", "binding_id", "client", "attempt", "before", "after", "provider_receipt_sha256"}, "top-level")
    if d["schema"] != SCHEMA or d["binding_id"] != BINDING:
        raise CanaryEvidenceInputError("unsupported evidence schema or binding")
    cli = _keys(d["client"], {"name", "version", "endpoint", "binary_sha256"}, "client")
    if cli["name"] != "Claude Code" or cli["endpoint"] != ENDPOINT:
        raise CanaryEvidenceInputError("unsupported coding tool or endpoint")
    if cli["version"] is not None and (type(cli["version"]) is not str or len(cli["version"]) > 64 or not cli["version"]):
        raise CanaryEvidenceInputError("invalid client version")
    _hash_or_none(cli["binary_sha256"], "client")
    row = _keys(d["attempt"], {
        "operation_id", "attended", "started_at_unix", "ended_at_unix",
        "requested_model", "served_model", "terminal_outcome", "artifact_sha256",
    }, "attempt")
    if row["operation_id"] is not None and (type(row["operation_id"]) is not str or not OPERATION.fullmatch(row["operation_id"])):
        raise CanaryEvidenceInputError("invalid attempt identifier")
    if type(row["attended"]) is not bool:
        raise CanaryEvidenceInputError("invalid attendance declaration")
    _stamp_or_none(row["started_at_unix"], "start")
    _stamp_or_none(row["ended_at_unix"], "end")
    if row["started_at_unix"] is not None and row["ended_at_unix"] is not None and row["ended_at_unix"] < row["started_at_unix"]:
        raise CanaryEvidenceInputError("reversed attempt timestamps")
    profile = get_profile("byteplus-coding-plan-personal")
    permitted = frozenset(profile.models.values())
    for name in ("requested_model", "served_model"):
        v = row[name]
        if v is not None and (type(v) is not str or v not in permitted):
            raise CanaryEvidenceInputError("unreviewed served or requested model")
    if row["terminal_outcome"] not in (None, "success", "failure", "unknown"):
        raise CanaryEvidenceInputError("invalid outcome declaration")
    _hash_or_none(row["artifact_sha256"], "result")
    _hash_or_none(d["provider_receipt_sha256"], "provider")
    before = _snapshot(d["before"], "before")
    after = _snapshot(d["after"], "after")
    a, b = before["observed_at_unix"], after["observed_at_unix"]
    if a is not None and b is not None and b <= a:
        raise CanaryEvidenceInputError("nonmonotonic management observation timestamps")

    needs = []
    for name, valid in (
        ("client_version", cli["version"] is not None),
        ("client_binary_digest", cli["binary_sha256"] is not None),
        ("attended_session", row["attended"] is True),
        ("operation_id", row["operation_id"] is not None),
        ("bounded_attempt_times", row["started_at_unix"] is not None and row["ended_at_unix"] is not None),
        ("requested_model", row["requested_model"] is not None),
        ("served_model", row["served_model"] is not None),
        ("successful_terminal_result", row["terminal_outcome"] == "success"),
        ("tested_result_digest", row["artifact_sha256"] is not None),
        ("before_management_snapshot", a is not None),
        ("after_management_snapshot", b is not None),
    ):
        if not valid:
            needs.append(name)

    # Snapshots that fail to enclose the attempted coding call cannot
    # support even an operator-level before/after completeness claim.
    if a is not None and row["started_at_unix"] is not None and a > row["started_at_unix"]:
        needs.append("pre_attempt_management_snapshot")
    if b is not None and row["ended_at_unix"] is not None and b < row["ended_at_unix"]:
        needs.append("post_attempt_management_snapshot")

    # The official BytePlus Ark usage snapshot may omit the five-hour
    # session reset entirely, even when both long-window resets are known.
    # This is a non-authoritative evidence candidate: permit structurally
    # complete long-window observations, but mark session comparability
    # UNKNOWN rather than pretending they prove a model-specific debit.
    long_windows_comparable = True
    for name in ("weekly", "monthly"):
        reset_before, reset_after = before["reset_at"][name], after["reset_at"][name]
        pct_before, pct_after = before["used_percent_rounded"][name], after["used_percent_rounded"][name]
        if reset_before is None or reset_after is None or reset_before != reset_after or pct_before is None or pct_after is None:
            long_windows_comparable = False
    if not long_windows_comparable:
        needs.append("comparable_management_windows")
    session_values_present = all(
        snapshot["used_percent_rounded"]["session"] is not None
        for snapshot in (before, after)
    )
    if not session_values_present:
        needs.append("session_window_percentages")
    session_before, session_after = before["reset_at"]["session"], after["reset_at"]["session"]
    session_comparable = (
        session_values_present and session_before is not None
        and session_before == session_after
    )
    caveats: list[str] = []
    if session_before is None and session_after is None:
        caveats.append("session_reset_not_reported")
    elif not session_comparable:
        needs.append("session_window_reset_discontinuity")
    same_window = long_windows_comparable and session_comparable
    if row["requested_model"] is not None and row["served_model"] is not None and row["requested_model"] != row["served_model"]:
        needs.append("requested_served_model_match")
    # A source-independent provider receipt checksum is only an operator's
    # representation until a real issuer verifies signature, account and call.
    return {
        "schema": "mastermind.byteplus_attended_evidence_inspection.v1",
        "evidence_scope": "OPERATOR_SUPPLIED_UNVERIFIED",
        "source_binding": BINDING,
        "candidate_fields_complete": not needs,
        "missing_or_inconclusive": sorted(set(needs)),
        "quota_snapshot_windows_comparable": same_window,
        "weekly_monthly_windows_comparable": long_windows_comparable,
        "session_window_comparable": session_comparable,
        "inconclusive_caveats": caveats,
        "provider_receipt_digest_supplied": d["provider_receipt_sha256"] is not None,
        "served_model_proven_by_issuer": False,
        "individual_request_debit_proven": False,
        "provider_origin_attested": False,
        "capacity_fact_issued": False,
        "autonomous_start_authorized": False,
        "actual_concurrent_worker_limit": None,
        "estimated_startable_jobs": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a redacted attended BytePlus evidence candidate (NO admission).")
    ap.add_argument("evidence_json", type=Path)
    args = ap.parse_args()
    try:
        # Limit memory consumption and accidental sensitive transcript ingestion.
        if args.evidence_json.stat().st_size > 16384:
            raise CanaryEvidenceInputError("evidence file too large")
        raw = json.loads(args.evidence_json.read_text(encoding="utf-8"))
        result = inspect_attended_evidence(raw)
    except (CanaryEvidenceInputError, OSError, ValueError, TypeError, json.JSONDecodeError):
        print(json.dumps({"schema": "mastermind.byteplus_attended_evidence_inspection.v1",
                          "status": "INVALID_OPERATOR_EVIDENCE", "capacity_fact_issued": False,
                          "autonomous_start_authorized": False}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
