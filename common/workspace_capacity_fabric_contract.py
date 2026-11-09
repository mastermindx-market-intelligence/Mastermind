"""Closed public READ projection of incumbent Capacity Fabric evidence.

This contract grants no routing, account, reservation, publication or admission
authority. Private source artifacts and their paths never cross this boundary.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

from common.executive_workspace_contract import canonical
from common import workspace_model_configuration_contract as configuration_wire

FRAME_SCHEMA = "mastermind.workspace_capacity_fabric_read.v1"
BODY_SCHEMA = "mastermind.workspace_capacity_fabric.v1"
OPERATION = "capacity_fabric"
MAX_RESPONSE_BYTES = 262_144
MAX_RESOURCES = 256
REASONS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_EXPIRED", "RESPONSE_OVER_BUDGET"})
PRESSURES = frozenset({"UNKNOWN", "HEADROOM_RECORDED", "LOW_ALLOWANCE", "LIMIT_REACHED", "COOLDOWN", "SLOTS_OCCUPIED", "UNAVAILABLE"})
WINDOW_STATES = frozenset({"CURRENT", "EXHAUSTED", "UNKNOWN", "STALE", "UNQUALIFIED"})
CONSUMERS = ("hermes", "deepseek", "t3_code", "website")
RUNTIME_STATES = frozenset({"NOT_OBSERVED", "ENROLLED", "RUNNING", "RESULT_PROVEN"})
ADVICE = frozenset({"UPDATE_USAGE", "CONSERVE_ALLOWANCE", "WAIT_FOR_RESET", "REVIEW_QUEUE", "REVIEW_ROUTING", "MEASURE_DEMAND"})
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,159}\Z")
_SECRET = re.compile(r"(?i)(?:xox[baprs]-|xapp-|github_pat_|gh[pousr]_|sk-[A-Za-z0-9_-]{16,}|bearer)")


def token(value):
    return type(value) is str and _TOKEN.fullmatch(value) is not None and _SECRET.search(value) is None


def timestamp(value):
    if type(value) is not str or len(value) > 40 or not value.endswith(("Z", "+00:00")):
        raise ValueError("invalid_timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("invalid_timestamp")
    return stamp.timestamp()


def number(value, *, maximum=1_000_000, integer=False):
    return (type(value) in ((int,) if integer else (int, float))
            and math.isfinite(value) and 0 <= value <= maximum)


def validate_frame(frame):
    if type(frame) is not dict or frame.get("schema") != FRAME_SCHEMA or frame.get("operation") != OPERATION:
        raise ValueError("invalid_input")
    configuration_wire.validate_frame({**frame, "schema": configuration_wire.FRAME_SCHEMA,
                                       "operation": configuration_wire.OPERATION})
    return frame


def unavailable(reason="SOURCE_UNAVAILABLE"):
    if reason not in REASONS:
        raise ValueError("invalid_reason")
    return {"ok": True, "result": {"schema": BODY_SCHEMA, "availability": "UNAVAILABLE",
            "reason_codes": [reason], "observed_at": None, "expires_at": None,
            "source_revision": None, "resources": [], "consumers": [], "recommendations": [],
            "admission_authorized": False}}


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError("invalid_capacity_shape")


def validate_result(body, *, now=None):
    _keys(body, "schema availability reason_codes observed_at expires_at source_revision resources consumers recommendations admission_authorized")
    if body["schema"] != BODY_SCHEMA or body["admission_authorized"] is not False:
        raise ValueError("invalid_capacity_result")
    if body["availability"] == "UNAVAILABLE":
        reasons = body["reason_codes"]
        if type(reasons) is not list or len(reasons) != 1 or reasons[0] not in REASONS or body != unavailable(reasons[0])["result"]:
            raise ValueError("invalid_capacity_unavailable")
        return body
    if body["availability"] != "AVAILABLE" or body["reason_codes"] != []:
        raise ValueError("invalid_capacity_result")
    observed, expires = timestamp(body["observed_at"]), timestamp(body["expires_at"])
    if not 0 < expires - observed <= 900:
        raise ValueError("invalid_capacity_lifetime")
    if now is not None and (type(now) not in (int, float) or not math.isfinite(now) or not observed <= now < expires):
        raise ValueError("invalid_capacity_clock")
    if not token(body["source_revision"]):
        raise ValueError("invalid_capacity_revision")
    rows = body["resources"]
    if type(rows) is not list or len(rows) > MAX_RESOURCES:
        raise ValueError("capacity_over_budget")
    seen = set()
    for row in rows:
        _keys(row, "resource_ref provider pool allowance_scope identity_qualified readiness configured_concurrency configured_cap_basis active queued cooldown_until pressure reason_codes windows preview_eligible single_window_remaining_pct single_window_observed_at single_window_source")
        if any(not token(row[key]) for key in ("resource_ref", "provider", "pool", "readiness")) or row["resource_ref"] in seen:
            raise ValueError("invalid_capacity_resource")
        seen.add(row["resource_ref"])
        if row["allowance_scope"] is not None and not token(row["allowance_scope"]):
            raise ValueError("invalid_allowance_scope")
        if type(row["identity_qualified"]) is not bool or row["identity_qualified"] != (row["allowance_scope"] is not None):
            raise ValueError("invalid_allowance_identity")
        if row["configured_cap_basis"] not in {"ACCOUNT", "POOL", "UNKNOWN"}:
            raise ValueError("invalid_capacity_basis")
        for key in ("configured_concurrency", "active", "queued"):
            if row[key] is not None and not number(row[key], integer=True):
                raise ValueError("invalid_capacity_count")
        if row["cooldown_until"] is not None:
            timestamp(row["cooldown_until"])
        if row["pressure"] not in PRESSURES or (row["preview_eligible"] is not None and type(row["preview_eligible"]) is not bool):
            raise ValueError("invalid_capacity_pressure")
        if row["single_window_remaining_pct"] is not None and not number(row["single_window_remaining_pct"], maximum=100):
            raise ValueError("invalid_capacity_percent")
        if row["single_window_source"] not in ("RECORDED_OBSERVATION", "LOCAL_ESTIMATE", "UNKNOWN"):
            raise ValueError("invalid_capacity_source")
        if row["single_window_remaining_pct"] is None:
            if row["single_window_observed_at"] is not None:
                raise ValueError("invalid_scalar_observation")
        elif (row["single_window_source"] == "UNKNOWN" or row["single_window_observed_at"] is None
                or not 0 < timestamp(body["expires_at"]) - timestamp(row["single_window_observed_at"]) <= 600):
            raise ValueError("invalid_scalar_observation")
        elif now is not None and timestamp(row["single_window_observed_at"]) > now:
            raise ValueError("invalid_scalar_observation")
        if type(row["reason_codes"]) is not list or len(row["reason_codes"]) > 20 or any(not token(x) for x in row["reason_codes"]):
            raise ValueError("invalid_capacity_reasons")
        if type(row["windows"]) is not list or not 1 <= len(row["windows"]) <= 16:
            raise ValueError("invalid_capacity_windows")
        windows = set()
        for window in row["windows"]:
            _keys(window, "window required remaining_pct observed_at reset_at state reason")
            if not token(window["window"]) or window["window"] in windows or window["state"] not in WINDOW_STATES or not token(window["reason"]):
                raise ValueError("invalid_capacity_window")
            windows.add(window["window"])
            if type(window["required"]) is not bool:
                raise ValueError("invalid_window_requirement")
            pct = window["remaining_pct"]
            if pct is not None and not number(pct, maximum=100):
                raise ValueError("invalid_capacity_percent")
            for key in ("observed_at", "reset_at"):
                if window[key] is not None:
                    timestamp(window[key])
            if window["state"] in {"CURRENT", "EXHAUSTED"}:
                if pct is None or window["observed_at"] is None or (window["state"] == "EXHAUSTED") != (pct == 0):
                    raise ValueError("invalid_current_quota")
                stamp = timestamp(window["observed_at"])
                if (not 0 < expires - stamp <= 600
                        or window["reset_at"] is not None and expires > timestamp(window["reset_at"])
                        or now is not None and stamp > now):
                    raise ValueError("invalid_current_quota_lifetime")
            elif pct is not None:
                raise ValueError("unqualified_quota_must_be_null")
    consumers = body["consumers"]
    if type(consumers) is not list or len(consumers) != len(CONSUMERS):
        raise ValueError("invalid_capacity_consumers")
    if [row.get("consumer") for row in consumers if type(row) is dict] != list(CONSUMERS):
        raise ValueError("invalid_capacity_consumers")
    for row in consumers:
        _keys(row, "consumer source_state runtime_state observed_at evidence_ref")
        if row["source_state"] not in {"BUILT", "SPEC_ONLY"} or row["runtime_state"] not in RUNTIME_STATES:
            raise ValueError("invalid_consumer_state")
        if row["runtime_state"] == "NOT_OBSERVED":
            if row["observed_at"] is not None or row["evidence_ref"] is not None:
                raise ValueError("invalid_consumer_evidence")
        elif row["source_state"] != "BUILT" or not token(row["evidence_ref"]) or row["observed_at"] is None:
            raise ValueError("invalid_consumer_evidence")
        else:
            stamp = timestamp(row["observed_at"])
            if not 0 < expires - stamp <= 900 or now is not None and stamp > now:
                raise ValueError("invalid_consumer_lifetime")
    recommendations = body["recommendations"]
    if type(recommendations) is not list or len(recommendations) > 6 or len(set(recommendations)) != len(recommendations) or any(x not in ADVICE for x in recommendations):
        raise ValueError("invalid_capacity_advice")
    if len(canonical(body)) + 1 > MAX_RESPONSE_BYTES - 128:
        raise ValueError("capacity_over_budget")
    return body
