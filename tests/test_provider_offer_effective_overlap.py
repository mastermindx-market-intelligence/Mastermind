"""Effective dates and recurring windows must overlap at the same real instant.

All offers are fictional fixtures. No quota, subscription or execution grant.
"""
from dataclasses import replace
from decimal import Decimal

import pytest

from control_plane.provider_model_economics import ApiRateCard, ModelEconomicsError
from control_plane.provider_offer_economics import (
    ReviewedApiOffer, TimeBoundRate, quote_temporal_offer,
)

OFFER_DIGEST = "c" * 64
REQUEST_DIGEST = "d" * 64
MONDAY = ((0, 1440),)
MONDAY_THURSDAY = ((0, 1440), (3 * 1440, 4 * 1440))


def rate(name, start, end, windows=MONDAY):
    return TimeBoundRate(
        ApiRateCard(name, "reviewed_fixture", 0, None,
                    Decimal("0.15"), Decimal("0.015"), None, Decimal("0.60")),
        start, end, windows,
    )


def quote(rates, now):
    offer = ReviewedApiOffer(
        "fixture.model", "fixture", "Model-1", "reviewed_fixture",
        OFFER_DIGEST, "2027-01-01T00:00:00Z", tuple(rates),
    )
    return quote_temporal_offer(
        offer, expected_offer_digest=OFFER_DIGEST,
        expected_model_key="fixture.model", expected_surface="reviewed_fixture",
        request_digest=REQUEST_DIGEST, now=now,
        context_tokens=1000, input_tokens=1000, output_tokens=100,
    )


@pytest.mark.parametrize("now,expected", [
    ("2026-11-02T12:00:00Z", "first"),
    ("2026-11-05T12:00:00Z", "second"),
    ("2026-11-09T12:00:00Z", "second"),
    ("2026-11-09T07:00:00-05:00", "second"),
])
def test_overlapping_date_ranges_with_no_actual_weekly_collision(now, expected):
    first = rate("first", "2026-11-02T00:00:00Z", "2026-11-04T00:00:00Z")
    second = rate("second", "2026-11-03T00:00:00Z", "2026-11-10T00:00:00Z",
                  MONDAY_THURSDAY)
    # Date intersection is Tuesday-Wednesday; the common weekly window is Monday.
    result = quote([first, second], now)
    assert result.rate_id == expected
    assert result.estimated_usage_usd == Decimal("0.00021")


def test_still_rejects_a_real_collision_in_a_future_week():
    first = rate("first", "2026-11-02T00:00:00Z", "2026-11-11T00:00:00Z")
    second = rate("second", "2026-11-03T00:00:00Z", "2026-11-10T00:00:00Z")
    with pytest.raises(ModelEconomicsError, match="overlapping time/context"):
        quote([first, second], "2026-11-02T12:00:00Z")


@pytest.mark.parametrize("extra_microsecond,ambiguous", [(False, False), (True, True)])
def test_half_open_effective_boundary_at_weekly_start(extra_microsecond, ambiguous):
    end = "2026-11-09T01:00:00.000001Z" if extra_microsecond else "2026-11-09T01:00:00Z"
    windows = ((60, 120),)
    first = rate("first", "2026-11-02T00:00:00Z", end, windows)
    second = rate("second", "2026-11-09T00:00:00Z", "2026-11-17T00:00:00Z", windows)
    if ambiguous:
        with pytest.raises(ModelEconomicsError, match="overlapping time/context"):
            quote([first, second], "2026-11-02T01:30:00Z")
    else:
        assert quote([first, second], "2026-11-02T01:30:00Z").rate_id == "first"
        assert quote([first, second], "2026-11-09T01:00:00Z").rate_id == "second"


def test_context_disjoint_variants_remain_compatible():
    first = rate("short", "2026-11-02T00:00:00Z", "2026-11-30T00:00:00Z")
    second = rate("long", "2026-11-02T00:00:00Z", "2026-11-30T00:00:00Z")
    first = replace(first, card=replace(first.card, max_context_tokens=1000))
    second = replace(second, card=replace(second.card, min_context_tokens=1001))
    assert quote([first, second], "2026-11-02T12:00:00Z").rate_id == "short"


def test_periodic_intersection_matches_concrete_calendar_reference():
    from datetime import datetime, timedelta, timezone
    from random import Random
    from control_plane.provider_offer_economics import _has_effective_weekly_overlap

    rng = Random(20261110)
    monday = datetime(2026, 11, 2, tzinfo=timezone.utc)

    def windows():
        points = sorted(rng.sample(range(10081), rng.choice((2, 4, 8))))
        return tuple(zip(points[::2], points[1::2]))

    def concrete(start, end, left, right):
        week = monday
        while week < end:
            for a, b in left:
                for c, d in right:
                    lo = max(start, week + timedelta(minutes=a), week + timedelta(minutes=c))
                    hi = min(end, week + timedelta(minutes=b), week + timedelta(minutes=d))
                    if lo < hi:
                        return True
            week += timedelta(days=7)
        return False

    for _ in range(1000):
        left, right = windows(), windows()
        start = monday + timedelta(minutes=rng.randrange(3 * 10080), microseconds=rng.randrange(1000000))
        end = start + timedelta(minutes=rng.randrange(1, 3 * 10080), microseconds=rng.randrange(1000000))
        expected = concrete(start, end, left, right)
        assert _has_effective_weekly_overlap(start, end, left, right) is expected
        assert _has_effective_weekly_overlap(start, end, right, left) is expected


def test_calendar_extremes_and_empty_intervals_do_not_overflow():
    from datetime import datetime, timezone
    from control_plane.provider_offer_economics import _has_effective_weekly_overlap

    low = datetime.min.replace(tzinfo=timezone.utc)
    high = datetime.max.replace(tzinfo=timezone.utc)
    all_week = ((0, 10080),)
    assert _has_effective_weekly_overlap(low, high, ((60, 61),), ((60, 61),))
    assert _has_effective_weekly_overlap(high.replace(hour=0), high, all_week, all_week)
    assert not _has_effective_weekly_overlap(low, high, ((0, 60),), ((60, 120),))
    assert not _has_effective_weekly_overlap(high, high, all_week, all_week)
    assert not _has_effective_weekly_overlap(high, low, all_week, all_week)
