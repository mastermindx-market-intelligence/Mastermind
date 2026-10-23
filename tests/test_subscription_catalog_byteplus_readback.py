"""Source-only readback projection; never an admission or provider call."""
from __future__ import annotations

import copy
import pytest

from control_plane.subscription_catalog import (
    HarnessBindingError, project_byteplus_plan_readback,
)


def fixture():
    holdings = {"plans": [{"key": "coding-plan", "name": "Coding Plan",
                            "scope": "personal", "tier": "pro", "status": "Running"}]}
    usage = {
        "viewer": {"user_id": "private-id-do-not-project",
                   "account_id": "another-private-identifier"},
        "updated_at": 1792692726,
        "items": [{"product": "coding-plan", "edition": "personal",
                   "subscribed": True, "periods": [
                       {"label": "session", "percent": 0},
                       {"label": "weekly", "percent": 0,
                        "reset_at": "2026-10-26T00:00:00+08:00"},
                       {"label": "monthly", "percent": 0,
                        "reset_at": "2026-11-22T23:59:59+08:00"},
                   ]}],
    }
    return holdings, usage


def test_authentic_shape_whitelisted_but_never_admitted():
    holdings, usage = fixture()
    frozen = copy.deepcopy((holdings, usage))
    row = project_byteplus_plan_readback(holdings, usage)
    assert row["tier_reported"] == "pro"
    assert row["windows"]["session"]["used_percent_rounded"] == 0
    assert row["windows"]["weekly"]["reset_at"] == "2026-10-26T00:00:00+08:00"
    assert row["actual_request_counts_available"] is False
    assert row["actual_concurrency_limit_available"] is False
    assert row["estimated_startable_jobs"] is None
    assert row["suggested_parallelism"] is None
    assert row["live_admission"] is False
    assert row["autonomous_allowed"] is False
    assert row["account_identity_attested"] is False
    assert row["provider_origin_attested"] is False
    assert "private-id" not in str(row)
    assert "another-private" not in str(row)
    assert (holdings, usage) == frozen


@pytest.mark.parametrize(
    "field, value",
    [("tier", "lite"), ("tier", None), ("status", "Cancelled"),
     ("status", None), ("scope", "team")],
)
def test_wrong_plan_identity_never_qualifies(field, value):
    holdings, usage = fixture()
    holdings["plans"][0][field] = value
    with pytest.raises(HarnessBindingError, match="BytePlus readback invalid"):
        project_byteplus_plan_readback(holdings, usage)


@pytest.mark.parametrize("percent", [-1, 101, 0.5, True, None, "0", 110])
def test_rounded_percent_is_not_an_inference_quota(percent):
    holdings, usage = fixture()
    usage["items"][0]["periods"][0]["percent"] = percent
    with pytest.raises(HarnessBindingError, match="percent"):
        project_byteplus_plan_readback(holdings, usage)


@pytest.mark.parametrize(
    "reset", [None, "2026-10-26", "2026-02-30T00:00:00+08:00",
              "2026-10-26T00:00:00", 42],
)
def test_reset_timestamp_must_be_offset_aware(reset):
    holdings, usage = fixture()
    usage["items"][0]["periods"][1]["reset_at"] = reset
    with pytest.raises(HarnessBindingError, match="reset timestamp|offset timestamp"):
        project_byteplus_plan_readback(holdings, usage)


def test_reject_missing_duplicate_window_missing_timestamp_and_partial_subscription():
    holdings, usage = fixture()
    for mutation in ("duplicate", "missing", "missing_updated", "not_subscribed"):
        h,u = fixture()
        if mutation == "duplicate":
            u["items"][0]["periods"][1]["label"] = "session"
        elif mutation == "missing":
            u["items"][0]["periods"].pop()
        elif mutation == "missing_updated":
            u.pop("updated_at")
        else:
            u["items"][0]["subscribed"] = False
        with pytest.raises(HarnessBindingError, match="BytePlus readback invalid"):
            project_byteplus_plan_readback(h, u)


@pytest.mark.parametrize("malformed_label", [[], {}, ["session"], 1, None, True])
def test_malformed_label_fails_closed_with_typed_error(malformed_label):
    holdings, usage = fixture()
    usage["items"][0]["periods"][0]["label"] = malformed_label
    with pytest.raises(HarnessBindingError, match="unexpected or duplicated"):
        project_byteplus_plan_readback(holdings, usage)


def test_mismatched_duplicate_or_other_products_do_not_mint_capacity():
    holdings, usage = fixture()
    other = copy.deepcopy(usage["items"][0])
    usage["items"].append(other)
    with pytest.raises(HarnessBindingError):
        project_byteplus_plan_readback(holdings, usage)
    holdings, usage = fixture()
    usage["items"][0]["product"] = "modelark-payg"
    with pytest.raises(HarnessBindingError):
        project_byteplus_plan_readback(holdings, usage)
