"""Fail-closed breadth producer-invariant regressions; no live product calls."""
from __future__ import annotations

from itertools import product

import pytest

from .test_breadth_semantics import fixture, read, breadth, validate


@pytest.mark.parametrize("status", [
    "no_key", "offline", "not_authorized", "no_response", "error", "no_thresholds",
])
def test_contradictory_true_usable_does_not_claim_observed_with_failed_feed(status):
    response = read(fixture(usable=True, feed_status=status))
    validate(response)
    result = breadth(response)
    assert result["producer_semantics"]["usable"] is True
    assert result["producer_semantics"]["feed_status"] == status
    assert result["state"] != "observed"


@pytest.mark.parametrize("field", ["source_age_min", "source_asof", "schema", "session"])
def test_missing_required_producer_truth_cannot_claim_observed(field):
    values = fixture()
    values["status"]["checks"]["breadth"].pop(field)
    response = read(values)
    validate(response)
    assert breadth(response)["state"] != "observed"


def test_closed_session_true_usable_is_contradiction():
    values = fixture()
    values["status"]["checks"]["breadth"]["session"] = "closed"
    response = read(values)
    validate(response)
    assert breadth(response)["state"] != "observed"


def test_future_source_clock_cannot_claim_current_usable():
    response = read(fixture(source="2099-01-01T00:00:00Z", age=-1.0))
    validate(response)
    assert breadth(response)["producer_semantics"]["source_asof"]["status"] == "future"
    assert breadth(response)["state"] != "observed"


def test_healthy_fixture_remains_observed_with_separate_source_time():
    response = read(fixture())
    validate(response)
    data = breadth(response)
    assert data["state"] == "observed"
    assert data["producer_semantics"]["source_asof"]["status"] == "observed"


@pytest.mark.parametrize("feed_status", ["new_unspecified_failure", None])
def test_producer_explicit_unusable_survives_unknown_feed_status(feed_status):
    response = read(fixture(usable=False, feed_status=feed_status))
    validate(response)
    check = breadth(response)
    assert check["producer_semantics"]["usable"] is False
    assert check["state"] == "unavailable"


def test_producer_unusable_survives_absent_optional_schema():
    values = fixture(usable=False)
    values["status"]["checks"]["breadth"].pop("schema")
    response = read(values)
    validate(response)
    assert breadth(response)["state"] == "unavailable"


def test_deterministic_cross_product_never_mints_healthy_producer_state():
    checked = 0
    for usable, feed, age, source, session, schema in product(
        (True, False, None),
        ("ok", "no_key", "future_new_status", None),
        (0.0, None, "bad"),
        ("2026-10-09T20:59:00Z", None, "2099-01-01T00:00:00Z"),
        ("rth", "closed", None),
        ("live.breadth.v1", None),
    ):
        values = fixture(usable=usable, age=age, source=source, feed_status=feed)
        row = values["status"]["checks"]["breadth"]
        if schema is None:
            row.pop("schema")
        row["session"] = session
        result = read(values)
        validate(result)
        check = breadth(result)
        projected = check["producer_semantics"]
        if check["state"] == "observed":
            assert projected["usable"] is True
            assert projected["feed_status"] == "ok"
            assert projected["source_asof"]["status"] == "observed"
            assert projected["source_age_status"] == "observed"
            assert schema == "live.breadth.v1" and session == "rth"
        checked += 1
    assert checked == 3 * 4 * 3 * 3 * 3 * 2
