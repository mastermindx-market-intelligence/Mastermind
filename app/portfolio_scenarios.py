"""Operator-only, non-persistent HTTP consumer of native portfolio what-ifs.

This route consumes supplied snapshots; it never loads an account, receives a
broker credential, fetches prices, stores requests, or executes a trade. The
existing app.auth operator tier owns authentication and rate limiting. Supplied
provenance is not authenticated merely because it passes a numerical contract.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool

from portfolio import global_scenario_account, global_scenario_context

router = APIRouter()
PATH = "/api/portfolio/scenarios/compare"
REQUEST_SCHEMA = "mastermind.global_scenario_request/v1"
RESPONSE_SCHEMA = "mastermind.global_scenario_response/v1"
MAX_BODY_BYTES = 1_000_000
MAX_NODES = 50_000
MAX_DEPTH = 16
_FIELDS = frozenset({"schema", "portfolio_id", "account", "prices", "price_evidence",
                     "snapshot", "mandate", "universe", "alternatives", "scenarios", "as_of"})
_HEADERS = {"Cache-Control": "private, no-store", "Pragma": "no-cache",
            "X-Robots-Tag": "noindex, noarchive"}


@router.get("/portfolio-scenarios.js", include_in_schema=False)
def scenario_script() -> FileResponse:
    """Public application code only; never an account or scenario artifact."""
    return FileResponse(Path(__file__).parent / "static" / "portfolio_scenarios.js",
                        media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"})


@router.get("/portfolio-scenarios.css", include_in_schema=False)
def scenario_styles() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "portfolio_scenarios.css",
                        media_type="text/css", headers={"Cache-Control": "public, max-age=300"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _response(payload: dict[str, Any], code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=code, headers=_HEADERS)


def _error(reason: str, code: int) -> JSONResponse:
    # Never reflect the request, exception message, account values, or credentials.
    return _response({"schema": RESPONSE_SCHEMA, "status": "UNAVAILABLE",
                      "reasons": [reason], "result": None, "display_only": True,
                      "hypothetical_only": True, "no_predictive_claim": True,
                      "authority": dict(global_scenario_context.AUTHORITY)}, code)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise ValueError("duplicate_json_key")
        out[key] = value
    return out


def _reject_constant(_value: str) -> None:
    raise ValueError("nonfinite_json")


def _bounded(value: Any) -> bool:
    """Bound work without recursively traversing a caller-controlled object."""
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            return False
        if isinstance(item, dict):
            if any(len(key) > 128 for key in item):
                return False
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and len(item) > 16_384:
            return False
        elif isinstance(item, float) and not math.isfinite(item):
            return False
    return True


@router.post(PATH)
async def compare_portfolio_scenarios(request: Request) -> JSONResponse:
    """Evaluate bounded hypothetical alternatives through the native account owner.

    The existing operator bearer/serve-only/rate-limit middleware runs before
    this handler. No GET or unauthenticated compute alternative is registered.
    Neither supplied receipt hashes nor an operator token are investment approval.
    """
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return _error("application_json_required", 415)
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            length = int(declared)
            if length < 0:
                return _error("invalid_content_length", 400)
            if length > MAX_BODY_BYTES:
                return _error("request_too_large", 413)
        except ValueError:
            return _error("invalid_content_length", 400)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            return _error("request_too_large", 413)
        body.extend(chunk)
    try:
        data = json.loads(body, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        return _error("invalid_json", 400)
    if not _bounded(data):
        return _error("request_complexity_exceeded", 413)
    if not isinstance(data, dict) or set(data) != _FIELDS or data.get("schema") != REQUEST_SCHEMA:
        return _error("request_contract_invalid", 422)
    now = _now()
    cutoff = global_scenario_account._clock(data.get("as_of"))
    if cutoff is None or cutoff > now:
        return _error("invalid_or_future_as_of", 422)
    inputs = {key: value for key, value in data.items() if key != "schema"}
    try:
        result = await run_in_threadpool(global_scenario_account.compare_account, **inputs)
    except (global_scenario_context.ContractError, TypeError, ValueError, OverflowError, RecursionError):
        return _error("scenario_inputs_unqualified", 422)
    return _response({
        "schema": RESPONSE_SCHEMA,
        "status": result["status"], "result": result,
        "analysis_as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "received_at": now.isoformat().replace("+00:00", "Z"),
        "input_basis": "operator_supplied_snapshot",
        "account_ownership_verified": False,
        "historical_original_availability_proven": False,
        "live_account_read": False, "account_mutation": False,
        "display_only": True, "hypothetical_only": True, "no_predictive_claim": True,
        "authority": dict(global_scenario_context.AUTHORITY),
    })
