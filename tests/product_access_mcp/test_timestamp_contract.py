"""Offline regression: exact reader output must fit its advertised MCP schema.

Only an in-memory fixture transport is used. No sockets, credentials, browser,
SDK server, source-repository writes, or production requests are involved.
"""
import asyncio
import json
from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from integrations.product_access_mcp.contracts import HttpObservation, time_observation
from integrations.product_access_mcp.reader import ProductReader
from integrations.product_access_mcp.schemas import STAMP, TOOL_SPECS

NOW = datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc)
GOOD = "2026-10-09T20:59:00Z"
NON_RFC3339 = [
    "20261009T205900Z",
    "2026-W41-5T20:59:00Z",
    "2026-10-09 20:59:00+00:00",
    "2026-10-09X20:59:00Z",
    "2026-10-09\n20:59:00Z",
    "2026-10-09T20:59Z",
    "2026-10-09T20:59:00+0000",
    "2026-10-09T20:59:00+00",
    "2026-10-09T20:59:00,5Z",
    "2026-10-09T20:59:00+00:00:15",
    "2026-10-09T20:59:00+00:60",
    "2026-10-09T20:59:00+01:99",
]
VALID = [GOOD, "2026-10-09T20:59:00+00:00", "2026-10-09T16:59:00-04:00",
         "2026-10-09T20:59:00.123Z", "2026-10-09t20:59:00z",
         "2026-10-09T20:59:00z", "2026-10-09t20:59:00Z"]


def validate(tool, result):
    spec = next(row for row in TOOL_SPECS if row["name"] == tool)
    Draft202012Validator(spec["outputSchema"], format_checker=FormatChecker()).validate(result)


class FixturePort:
    """The real reader consumes fixture bytes through its documented port."""
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    async def read(self, endpoint, *, symbols=()):
        self.calls.append((endpoint, symbols))
        return HttpObservation(status=200, body=json.dumps(self.payloads[endpoint]).encode(),
                               content_type="application/json")


def pulse():
    return {"schema": "intelligence_hub.market_pulse.v1",
            "projection": "intelligence_hub.market_pulse", "snapshot_id": "a" * 16,
            "generated_at": GOOD, "source_owner": "terminal-market-data", "source_view": "regular",
            "state": {"availability": "available", "freshness": "delayed", "session": "regular", "coverage": "complete"},
            "coverage": {"requested": 1, "resolved": 1, "live": 0, "delayed": 1, "stale": 0, "missing": 0},
            "items": [{"symbol": "SPY", "price": 500.0, "change_abs": 0.0, "change_pct": 0.0,
                       "currency": "USD", "session": "regular", "freshness": "delayed",
                       "observed_at": GOOD, "received_at": None, "published_at": GOOD,
                       "regular_session_date": "2026-10-09", "revision": "b" * 16}], "errors": []}


@pytest.mark.parametrize("stamp", NON_RFC3339)
def test_non_rfc3339_is_local_invalid_observation(stamp):
    result = time_observation(stamp, NOW)
    assert result == {"value": None, "status": "invalid", "age_seconds": None}
    Draft202012Validator(STAMP, format_checker=FormatChecker()).validate(result)


@pytest.mark.parametrize("stamp", VALID)
def test_rfc3339_value_is_preserved(stamp):
    result = time_observation(stamp, NOW)
    assert result["status"] == "observed"
    assert result["value"] == stamp
    Draft202012Validator(STAMP, format_checker=FormatChecker()).validate(result)


@pytest.mark.parametrize("stamp", NON_RFC3339)
def test_one_bad_diagnostic_stamp_does_not_break_entire_mcp_result(stamp):
    port = FixturePort({
        "health": {"status": "ok", "commit": "a" * 40, "checkout": "a" * 40},
        "status": {"status": "ok", "commit": "a" * 40,
                   "checks": {"quotes": {"built": stamp, "resolved": 0},
                              "risk_state": {"built": GOOD}}},
    })
    result = asyncio.run(ProductReader(transport=port, now=lambda: NOW).diagnostics())
    # This is the exact full output-schema validator used by app.py.
    validate("product_diagnostics", result)
    health, status = result["observations"]
    assert health["state"] == "observed"
    assert status["data"]["checks"]["quotes"]["source_time"]["status"] == "invalid"
    assert status["data"]["checks"]["quotes"]["counts"]["resolved"] == 0
    assert status["data"]["checks"]["risk_state"]["source_time"]["status"] == "observed"
    assert port.calls == [("health", ()), ("status", ())]


@pytest.mark.parametrize("field", ["generated_at", "observed_at", "received_at", "published_at"])
def test_one_bad_quote_stamp_does_not_break_entire_mcp_result(field):
    payload = pulse()
    target = payload if field == "generated_at" else payload["items"][0]
    target[field] = NON_RFC3339[2]
    result = asyncio.run(ProductReader(transport=FixturePort({"market_pulse": payload}),
                                     now=lambda: NOW).market_pulse(["SPY"]))
    validate("product_market_pulse", result)
    observation = result["observations"][0]
    data = observation["data"]
    stamp = data[field] if field == "generated_at" else data["items"][0][field]
    assert stamp["status"] == "invalid"
    assert observation["state"] == "observed"
    assert data["items"][0]["price"] == 500.0
    # received_at is optional under the pre-existing qualification contract.
    if field != "received_at":
        assert data["items"][0]["timestamp_qualified"] is False


@pytest.mark.parametrize("value, state", [
    (None, "unknown"), (False, "invalid"), (123, "invalid"), ("bad", "invalid"),
    ("2026-02-30T20:59:00Z", "invalid"), ("2026-10-09T20:59:00", "invalid"),
    ("2026-10-09T20:59:00+24:00", "invalid"),
    ("2099-01-01T00:00:00Z", "future"),
])
def test_unknown_invalid_and_future_semantics_are_preserved(value, state):
    result = time_observation(value, NOW)
    assert result["status"] == state
    Draft202012Validator(STAMP, format_checker=FormatChecker()).validate(result)
