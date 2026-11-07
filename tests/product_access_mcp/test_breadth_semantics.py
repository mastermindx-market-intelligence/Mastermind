"""Regression tests for bounded public Macro breadth producer semantics."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from integrations.product_access_mcp.contracts import HttpObservation
from integrations.product_access_mcp.reader import ProductReader
from integrations.product_access_mcp.schemas import TOOL_SPECS

NOW = datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc)
BUILT = "2026-10-09T20:59:00Z"
OLD_SOURCE = "2026-09-09T20:59:00Z"


class FixturePort:
    def __init__(self, values):
        self.values = values
        self.calls = []

    async def read(self, endpoint, *, symbols=()):
        self.calls.append((endpoint, symbols))
        return HttpObservation(
            status=200,
            body=json.dumps(self.values[endpoint]).encode(),
            content_type="application/json",
        )


def fixture(*, usable=True, age=0.0, source=BUILT, feed_status="ok"):
    return {
        "health": {"status": "ok", "commit": "a" * 40, "checkout": "a" * 40},
        "status": {
            "status": "ok",
            "commit": "a" * 40,
            "checks": {
                "breadth": {
                    "schema": "live.breadth.v1", "built": BUILT, "age_min": 0,
                    "usable": usable, "feed_status": feed_status,
                    "source_asof": source, "source_age_min": age,
                    "unusable_reason": "source_stale" if not usable else None,
                    "session": "rth", "producer": "vps:macro-live-breadth",
                    "delay_min": 16, "coverage_n": 1412, "coverage_pct": 94.1,
                    "adv": 705, "dec": 707,
                }
            },
        },
    }


def read(values):
    return asyncio.run(ProductReader(
        transport=FixturePort(values), now=lambda: NOW
    ).diagnostics())


def breadth(response):
    return response["observations"][1]["data"]["checks"]["breadth"]


def validate(response):
    schema = next(
        spec["outputSchema"] for spec in TOOL_SPECS
        if spec["name"] == "product_diagnostics"
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(response)


def test_producer_staleness_cannot_be_erased_by_recent_file_mtime():
    good = read(fixture())
    bad = read(fixture(usable=False, source=OLD_SOURCE, age=43_200))
    validate(good)
    validate(bad)
    healthy, stale = breadth(good), breadth(bad)
    assert healthy["source_time"] == stale["source_time"]
    assert healthy["file_age_minutes"] == stale["file_age_minutes"] == 0
    assert healthy["producer_semantics"]["usable"] is True
    assert stale["producer_semantics"]["usable"] is False
    assert stale["state"] == "unavailable"
    assert healthy["producer_semantics"]["source_asof"]["value"] == BUILT
    assert stale["producer_semantics"]["source_asof"]["value"] == OLD_SOURCE
    assert stale["producer_semantics"]["source_age_minutes"] == 43_200
    assert good["observations"][1]["sha256"] != bad["observations"][1]["sha256"]


def test_feed_failure_preserved_when_source_clock_is_fresh():
    item = breadth(read(fixture(usable=False, feed_status="no_key")))
    assert item["state"] == "unavailable"
    assert item["producer_semantics"]["feed_status"] == "no_key"
    assert item["producer_semantics"]["usable"] is False


@pytest.mark.parametrize("bad", ["true", 1, 0, [], {}])
def test_bogus_producer_boolean_cannot_report_healthy(bad):
    result = read(fixture(usable=bad))
    validate(result)
    item = breadth(result)
    assert item["state"] == "invalid"
    assert item["producer_semantics"]["usable"] is None
    assert item["producer_semantics"]["usable_status"] == "invalid"


@pytest.mark.parametrize("raw,status,expected", [
    (None, "unknown", None), (False, "invalid", None),
    (-4.25, "observed", -4.25), ("43200", "invalid", None),
])
def test_source_age_is_exact_finite_number_and_negative_skew_is_preserved(raw,status,expected):
    values = fixture()
    values["status"]["checks"]["breadth"]["source_age_min"] = raw
    result = read(values)
    validate(result)
    item = breadth(result)
    assert item["producer_semantics"]["source_age_status"] == status
    assert item["producer_semantics"]["source_age_minutes"] == expected
    if status == "invalid":
        assert item["state"] == "invalid"


def test_infinite_source_age_is_an_invalid_http_observation_not_success():
    result = read(fixture(age=float("inf")))
    validate(result)
    assert result["observations"][1]["state"] == "invalid"
    assert result["observations"][1]["data"] is None


def test_known_omitted_fields_are_counted_without_leaking_free_form_values():
    values = fixture()
    values["status"]["checks"]["breadth"]["unusable_reason"] = "PRIVATE_UNTRUSTED_SENTINEL"
    values["status"]["checks"]["breadth"]["unexpected_cookie"] = "PRIVATE_COOKIE_SENTINEL"
    result = read(values)
    validate(result)
    detail = breadth(result)["producer_semantics"]
    assert detail["omitted_known_field_count"] >= 7
    assert detail["unrecognized_field_count"] == 1
    assert "PRIVATE_UNTRUSTED_SENTINEL" not in json.dumps(result)
    assert "PRIVATE_COOKIE_SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize("status,expect", [
    ("ok", "ok"), ("not_authorized", "not_authorized"),
    ("offline", "offline"), ("future_new_status", "other"),
    (None, "unknown"), (True, "invalid"),
])
def test_status_mapped_to_closed_owner_vocabulary(status,expect):
    result = read(fixture(feed_status=status))
    validate(result)
    assert breadth(result)["producer_semantics"]["feed_status"] == expect
    if status is True:
        assert breadth(result)["state"] == "invalid"
    elif expect in {"unknown", "other"}:
        assert breadth(result)["state"] == "unknown"


def test_missing_and_error_cases_stay_distinct_without_false_source_freshness():
    for source,expected in [
        ({"status": "missing"}, "missing"),
        ({"error": "PRIVATE_BACKEND", "age_min": 0}, "unavailable"),
    ]:
        values = fixture()
        values["status"]["checks"]["breadth"] = source
        result = read(values)
        validate(result)
        detail = breadth(result)
        assert detail["state"] == expected
        assert detail["producer_semantics"]["usable"] is None
        assert detail["producer_semantics"]["source_asof"]["status"] == "unknown"
        assert "PRIVATE_BACKEND" not in json.dumps(result)


def test_mismatched_breadth_schema_refuses_to_report_usable():
    values = fixture()
    values["status"]["checks"]["breadth"]["schema"] = "private.other.v1"
    result = read(values)
    validate(result)
    assert breadth(result)["state"] == "invalid"


@pytest.mark.parametrize("bad_timestamp", [
    "2026-10- 1T20:59:00Z", "2026-10-09 20:59:00Z", "2099-01-01T00:00:00Z",
])
def test_invalid_or_future_source_asof_never_looks_like_verified_current(bad_timestamp):
    values = fixture(source=bad_timestamp)
    result = read(values)
    validate(result)
    status = breadth(result)["producer_semantics"]["source_asof"]["status"]
    assert status in {"invalid", "future"}
    if status == "invalid":
        assert breadth(result)["state"] == "invalid"


def test_missing_semantics_must_not_be_classed_as_usable():
    values = fixture()
    values["status"]["checks"]["breadth"].pop("usable")
    result = read(values)
    validate(result)
    detail = breadth(result)
    assert detail["producer_semantics"]["usable"] is None
    assert detail["producer_semantics"]["usable_status"] == "unknown"
    assert detail["state"] == "unknown"


def test_extra_unknown_check_remains_counted_and_hidden():
    values = fixture()
    values["status"]["checks"]["unsupported_check"] = {"cookie": "PRIVATE_SECRET"}
    result = read(values)
    validate(result)
    assert result["observations"][1]["data"]["omitted_check_count"] == 1
    assert "PRIVATE_SECRET" not in json.dumps(result)


def test_catalog_is_versioned_and_within_existing_tool_budget():
    assert len(json.dumps(TOOL_SPECS).encode()) < 16000
    from integrations.product_access_mcp.schemas import SERVER_VERSION
    assert SERVER_VERSION == "1.2.0"
