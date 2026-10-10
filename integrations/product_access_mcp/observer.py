"""Bounded source observations with independent transport and representation truth.

Only owner-configured public endpoints are read. An HTTP 200 is never itself
proof of valid JSON or qualified market intelligence. This module creates no
transport listener, bearer forwarding, scheduler, browser or persistence.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from .contracts import (
    BODY_CAP, PROFILE, RESULT_SCHEMA, SOURCES,
    ProductCaller, ProductRefused, canonical_result,
)

UTC = timezone.utc
MARKET_TZ = ZoneInfo("America/New_York")
HEADERS = ("content-type", "content-length", "etag", "last-modified",
           "date", "age", "cache-control")
BANNED_REQUEST_HEADERS = ("authorization", "cookie", "proxy-authorization")
MAX_COMPONENTS = 12
MAX_COMPONENT_KEYS = 14


@dataclass(frozen=True)
class HttpPayload:
    """Exact observed transport status and retained bytes, not parsed success."""
    status: int
    body: bytes
    headers: Mapping[str, str]
    truncated: bool = False

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 100 <= self.status <= 599:
            raise ValueError("bad HTTP status")
        if not isinstance(self.body, bytes) or len(self.body) > BODY_CAP + 1:
            raise ValueError("bad body bounds")


HttpGetter = Callable[[str, int], HttpPayload]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_public_source(url: str, cap: int = BODY_CAP) -> HttpPayload:
    """Reference fetch only; the admitting host owns executor/time budget.

    This function accepts ONLY one of the two exact product owner URLs. It
    follows no redirect and sends no product-user/OAuth/website credentials.
    It does not let the MCP request supply URL, headers, or redirects.
    """
    if type(url) is not str or url not in {x[1] for x in SOURCES.values()}:
        raise ProductRefused("INVALID_REQUEST")
    if type(cap) is not int or not 1 <= cap <= BODY_CAP:
        raise ProductRefused("INVALID_REQUEST")
    opener = build_opener(_NoRedirect)
    req = Request(url, method="GET", headers={
        "Accept": "application/json",
        "User-Agent": "mastermind-product-read/0.1",
        "Cache-Control": "no-cache",
    })
    assert not any(k.lower() in BANNED_REQUEST_HEADERS for k in req.headers)
    try:
        try:
            response = opener.open(req, timeout=6)
        except HTTPError as err:
            response = err
        with response:
            headers = {k: response.headers.get(k) for k in HEADERS
                       if response.headers.get(k) is not None}
            data = response.read(cap + 1)
            return HttpPayload(
                status=response.status, body=data, headers=headers,
                truncated=len(data) > cap,
            )
    except (URLError, TimeoutError, OSError) as exc:
        # Never return exception detail, destination IP, or proxy environment.
        raise ProductRefused("READ_UNAVAILABLE") from None


def _clock(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace(" UTC", "+00:00").replace("Z", "+00:00")
        result = datetime.fromisoformat(text)
        return result.astimezone(UTC) if result.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _scalar(value: object) -> bool | int | float | str | None:
    if isinstance(value, bool):
        return value
    if type(value) in (int, float) and math.isfinite(value):
        return value
    if type(value) is str:
        return value[:180]
    return None


def _select_fields(raw: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: _scalar(raw[k]) for k in keys if k in raw and _scalar(raw[k]) is not None}


def _macro(raw: Any, now: datetime) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(raw, dict) or type(raw.get("status")) is not str:
        return "INVALID", {}, {"qualified": False, "reasons": ["invalid_status_contract"]}
    checks = raw.get("checks")
    if not isinstance(checks, dict):
        return "PARTIAL", {"reported_status": raw["status"][:50]}, {
            "qualified": False, "reasons": ["missing_checks"]}
    names = ("site", "overlay", "risk_state", "china_risk_state",
             "breadth", "prophet_live", "terminal_data", "flow_pulse",
             "basket_pulse", "orchestrator", "release_publications", "quotes")
    selected = {}
    ages = {}
    for name in names[:MAX_COMPONENTS]:
        entry = checks.get(name)
        if not isinstance(entry, dict):
            continue
        fields = _select_fields(entry, (
            "schema", "built", "as_of", "asof", "age_min", "stale",
            "fresh", "freshness", "commit", "source_asof", "pack_as_of",
            "pack_ok", "expected_now", "session_et", "status",
            "usable", "n", "coverage_pct",
        )[:MAX_COMPONENT_KEYS])
        selected[name] = fields
        if type(entry.get("age_min")) in (int, float) and math.isfinite(entry["age_min"]):
            ages[name] = entry["age_min"]
    data = {
        "reported_status": raw["status"][:50],
        "reported_service_commit": _scalar(raw.get("commit")),
        "reported_site_commit": _scalar(checks.get("site", {}).get("commit"))
        if isinstance(checks.get("site"), dict) else None,
        "checks": selected,
    }
    reasons = ["per_component_cadence_unqualified"]
    if not selected:
        reasons.append("empty_checks")
    # Age is observed but requires producer and market-session-specific policy.
    return "PARTIAL", data, {
        "qualified": False, "reasons": reasons,
        "reported_age_minutes": ages,
        "clock_basis": "producer_reported; no inferred whole-product freshness",
    }


def _risk(raw: Any, now: datetime) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(raw, dict) or raw.get("schema") != "market_risk/v1":
        return "INVALID", {}, {"qualified": False, "reasons": ["invalid_risk_schema"]}
    verdict = raw.get("verdict")
    if verdict not in ("RISK_ON", "MIXED", "RISK_OFF"):
        return "INVALID", {}, {"qualified": False, "reasons": ["invalid_verdict"]}
    score = raw.get("score")
    if score is not None and (
        type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100
    ):
        return "INVALID", {}, {"qualified": False, "reasons": ["invalid_score"]}
    asof = _day(raw.get("asof"))
    if asof is None or asof > now.astimezone(MARKET_TZ).date():
        return "INVALID", {}, {"qualified": False, "reasons": ["invalid_or_future_session"]}
    if type(raw.get("stale")) is not bool:
        return "PARTIAL", {}, {"qualified": False, "reasons": ["unknown_owner_freshness"]}
    observed_expiry = _clock(raw.get("stale_after"))
    built = _clock(raw.get("built"))
    event = _clock(raw.get("source_event_time"))
    reasons = []
    if built is not None and built > now:
        reasons.append("future_build")
    if event is not None and event > now:
        reasons.append("future_source_event")
    if observed_expiry is not None and observed_expiry <= now:
        reasons.append("elapsed_expiry")
    if observed_expiry is None:
        reasons.append("unqualified_intraday_expiry")
    owner_reasons = raw.get("stale_reasons")
    if isinstance(owner_reasons, list):
        reasons += [x[:100] for x in owner_reasons[:8] if type(x) is str]
    if raw["stale"]:
        reasons.append("owner_stale")
    out = _select_fields(raw, ("schema", "verdict", "score", "asof", "built",
                               "source_event_time", "stale_after",
                               "source_basis", "cause_basis", "stale"))
    out["stale_reasons"] = sorted(set(reasons))
    out["display_only"] = True
    has_hard_reason = any(r in reasons for r in (
        "future_build", "future_source_event", "elapsed_expiry", "owner_stale",
    ))
    status = "STALE" if has_hard_reason else "PARTIAL" if reasons else "OK"
    return status, out, {
        "qualified": not reasons, "reasons": sorted(set(reasons)),
        "source_session": asof.isoformat(),
        "market_timezone": "America/New_York",
        "owner_stale": raw["stale"],
    }


def _base(*, tool: str, caller: ProductCaller, now: datetime,
          status: str, source: dict[str, Any] | None,
          freshness: dict[str, Any], data: dict[str, Any],
          error: str | None = None) -> dict[str, Any]:
    return canonical_result({
        "schema": RESULT_SCHEMA, "profile": PROFILE, "tool": tool,
        "status": status, "observed_at": now.isoformat().replace("+00:00", "Z"),
        "caller": caller.public_identity(), "source": source,
        "freshness": freshness, "data": data, "error": error,
    })


def product_manifest(caller: ProductCaller, now: datetime) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ProductRefused("RESULT_UNVERIFIED")
    now = now.astimezone(UTC)
    return _base(
        tool="product_manifest", caller=caller, now=now,
        status="OK", source=None,
        freshness={"qualified": False, "reasons": ["discovery_not_observation"]},
        data={"views": [
            {"product": p, "view": v, "source_id": src,
             "evidence_class": "public_upstream"}
            for (p, v), (src, _) in SOURCES.items()
        ], "mode": "readonly", "private_product_user_grant_proven": False},
    )


def product_observe(caller: ProductCaller, request: Mapping[str, str],
                    now: datetime, getter: HttpGetter) -> dict[str, Any]:
    if now.tzinfo is None or not callable(getter):
        raise ProductRefused("RESULT_UNVERIFIED")
    now = now.astimezone(UTC)
    if set(request) != {"product", "view"} or (request["product"], request["view"]) not in SOURCES:
        raise ProductRefused("INVALID_REQUEST")
    source_id, url = SOURCES[request["product"], request["view"]]
    # The configured target is never supplied by a model or derived from an ID.
    try:
        payload = getter(url, BODY_CAP)
    except ProductRefused:
        return _base(tool="product_observe", caller=caller, now=now,
                     status="DEPENDENCY_UNAVAILABLE",
                     source={"source_id": source_id, "evidence_class": "public_upstream",
                             "representation": "not_observed"},
                     freshness={"qualified": False, "reasons": ["read_unavailable"]},
                     data={}, error="READ_UNAVAILABLE")
    if not isinstance(payload, HttpPayload):
        raise ProductRefused("RESULT_UNVERIFIED")
    meta = {
        "source_id": source_id, "evidence_class": "public_upstream",
        "http_status": payload.status,
        "body_bytes": len(payload.body),
        "body_sha256": hashlib.sha256(payload.body).hexdigest(),
        "content_type": str(payload.headers.get("content-type", ""))[:110],
        "etag": str(payload.headers.get("etag", ""))[:140] or None,
        "last_modified": str(payload.headers.get("last-modified", ""))[:140] or None,
        "cache_age_seconds": _scalar(payload.headers.get("age")),
        "representation": "retained_prefix" if payload.truncated else "complete",
    }
    if 300 <= payload.status <= 399:
        return _base(tool="product_observe", caller=caller, now=now, status="INVALID",
                     source=meta, freshness={"qualified": False, "reasons": ["redirect_refused"]},
                     data={}, error="REDIRECT_REFUSED")
    if payload.status in (401, 403):
        return _base(tool="product_observe", caller=caller, now=now,
                     status="UNAUTHORIZED" if payload.status == 401 else "FORBIDDEN",
                     source=meta, freshness={"qualified": False, "reasons": ["upstream_access_refused"]},
                     data={}, error="UPSTREAM_ACCESS_REFUSED")
    if payload.status == 404 or payload.status == 204:
        return _base(tool="product_observe", caller=caller, now=now,
                     status="MISSING", source=meta,
                     freshness={"qualified": False, "reasons": ["missing_publication"]},
                     data={}, error=None)
    if payload.status != 200:
        return _base(tool="product_observe", caller=caller, now=now,
                     status="DEPENDENCY_UNAVAILABLE", source=meta,
                     freshness={"qualified": False, "reasons": ["bad_upstream_status"]},
                     data={}, error="UPSTREAM_UNAVAILABLE")
    content_type = payload.headers.get("content-type", "").lower().split(";", 1)[0].strip()
    content_len = payload.headers.get("content-length")
    if (payload.truncated or not payload.body
        or content_type != "application/json"
        or (content_len is not None and (
            not content_len.isdecimal() or int(content_len) != len(payload.body)
        ))):
        return _base(tool="product_observe", caller=caller, now=now,
                     status="INVALID", source=meta,
                     freshness={"qualified": False, "reasons": ["invalid_json_representation"]},
                     data={}, error="INVALID_REPRESENTATION")
    try:
        decoded = json.loads(payload.body)
    except (ValueError, UnicodeError):
        return _base(tool="product_observe", caller=caller, now=now,
                     status="INVALID", source=meta,
                     freshness={"qualified": False, "reasons": ["invalid_json_representation"]},
                     data={}, error="INVALID_REPRESENTATION")
    status, data, freshness = (
        _macro(decoded, now) if request["product"] == "macro" else _risk(decoded, now)
    )
    return _base(tool="product_observe", caller=caller, now=now,
                 status=status, source=meta, freshness=freshness, data=data)
