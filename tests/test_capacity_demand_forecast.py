"""Rev5 D9: advisory demand/reset forecast contract.

The forecast may only report what was observed: an unmeasured quota is
``insufficient_observation``, an exhaustion *time* range needs a measured
consumption rate, quota-caused waiting is aggregated per pool, cheap fixes
outrank subscriptions, and nothing in the document can execute a purchase.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from control_plane.capacity_demand_forecast import (
    ACTION_FIX_HOST,
    ACTION_REALLOCATE,
    ACTION_SUBSCRIPTION_LAST,
    AUTHORITY,
    EXHAUSTION_INSUFFICIENT,
    SCHEMA,
    canonical_digest,
    produce_capacity_demand_forecast,
)

OBSERVED_AT = "2026-11-08T15:31:59Z"

#: Keys that would turn an advisory document into an actor.  Matched as
#: substrings, anywhere in the document.
FORBIDDEN_KEY_TOKENS = (
    "purchase",
    "checkout",
    "place_order",
    "buy_",
    "billing_action",
    "charge",
    "card_",
    "auto_execute",
    "execute_action",
    "subscription_purchase",
    "account_change",
    "credential",
    "price_usd",
)


def _resource(ref, pool, **overrides):
    row = {
        "shared_quota_resource_ref": ref,
        "pool_ref": pool,
        "provider_ref": pool,
        "quota_knowledge": "unknown",
        "quota_source": None,
        "quota_observed_at": None,
        "reset_at": None,
        "cooldown_until": None,
        "remaining_quota": None,
        "remaining_quota_basis": None,
        "configured_concurrency_cap": 1,
        "active_slots": 0,
        "reserved_slots": 0,
        "admission_eligibility": False,
        "readiness_state": "ready",
        "reason_codes": ["quota_unknown_no_bounded_unknown_mode_authorized"],
    }
    row.update(overrides)
    return row


def _preview(resources, **overrides):
    doc = {
        "schema": "mastermind.quota_economics_preview/v1",
        "authority": "NONE_PREVIEW_ONLY",
        "observed_at": OBSERVED_AT,
        "expires_at": "2026-11-08T15:46:59Z",
        "knowledge_summary": {"resources_total": len(resources)},
        "resources": resources,
    }
    doc.update(overrides)
    return doc


def _observed_row(ref, pool, *, remaining, cap=7, active=0, reserved=0, reset_at=None, **extra):
    return _resource(
        ref,
        pool,
        quota_knowledge="observed",
        quota_source="provider_api",
        quota_observed_at=OBSERVED_AT,
        reset_at=reset_at or "2026-11-10T00:00:00Z",
        remaining_quota=remaining,
        remaining_quota_basis="percent_of_window_remaining",
        configured_concurrency_cap=cap,
        active_slots=active,
        reserved_slots=reserved,
        admission_eligibility=True,
        reason_codes=["eligible_in_preview"],
        **extra,
    )


def _forecast(preview, *, ready_counts=None, broker=None):
    return produce_capacity_demand_forecast(
        quota_preview=preview,
        ready_counts=ready_counts,
        broker_observation=broker,
        observed_at=OBSERVED_AT,
    )


def _walk_keys(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + (str(key),), value
            yield from _walk_keys(value, path + (str(key),))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_keys(value, path + (str(index),))


def _numbers_under_percent_keys(document):
    hits = []
    for path, value in _walk_keys(document):
        key = path[-1].lower()
        if not any(token in key for token in ("percent", "pct")):
            continue
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            # "percent_of_window_remaining" is a basis string, not a number;
            # a numeric value under a percentage-named key is an invention
            # unless it was forwarded verbatim from the input document.
            hits.append((path, value))
    return hits


# ---------------------------------------------------------------------------
# 1. Unknown quota stays unknown — no percentage anywhere
# ---------------------------------------------------------------------------


def test_unknown_quota_yields_insufficient_observation_and_no_percentage():
    preview = _preview(
        [
            _resource("anthropic-oauth:max-1", "anthropic-oauth", configured_concurrency_cap=1),
            _resource("byteplus:personal-01", "byteplus", readiness_state="missing_credential"),
        ]
    )
    forecast = _forecast(preview)

    assert forecast["schema"] == SCHEMA
    assert forecast["authority"] == AUTHORITY == "ADVISORY_PREVIEW_ONLY"
    assert forecast["advisory_only"] is True
    for row in forecast["resources"]:
        exhaustion = row["exhaustion_forecast"]
        assert exhaustion["state"] == EXHAUSTION_INSUFFICIENT
        assert exhaustion["label"] == "insufficient_observation"
        assert exhaustion["range"] is None
        assert exhaustion["percentages"] is None
        assert exhaustion["confidence"] == "none"
        assert "QUOTA_NOT_OBSERVED" in exhaustion["reason_codes"]
        assert row["observed"]["remaining_quota"] is None

    assert _numbers_under_percent_keys(forecast) == []
    assert forecast["counts"]["observed_quota_resources"] == 0
    assert forecast["recommendations"] == []


def test_unknown_quota_never_becomes_a_rate_or_a_threshold_number():
    preview = _preview([_resource("go:C1", "go", configured_concurrency_cap=3)])
    forecast = _forecast(preview)
    for row in forecast["resources"]:
        exhaustion = row["exhaustion_forecast"]
        assert exhaustion["state"] == "insufficient_observation"
        assert exhaustion["range"] is None
        assert exhaustion.get("rate_bracket") is None
        assert exhaustion["derivation_basis"] is None
        assert exhaustion["confidence"] == "none"
    assert not [
        path for path, value in _walk_keys(forecast["resources"])
        if "rate" in path[-1].lower() and isinstance(value, (int, float))
        and not isinstance(value, bool) and value not in (0, 0.0)
    ]


# ---------------------------------------------------------------------------
# 2. Observed usage + measured rate -> bounded range with derivation basis
# ---------------------------------------------------------------------------


def test_observed_usage_with_measured_rate_yields_bounded_range():
    preview = _preview(
        [
            _observed_row(
                "bailian:Chris",
                "bailian",
                remaining=40.0,
                cap=7,
                active=2,
                reserved=1,
                observed_consumption_rate_per_hour={"lower": 2.0, "upper": 4.0},
            )
        ]
    )
    forecast = _forecast(preview)
    row = forecast["resources"][0]
    exhaustion = row["exhaustion_forecast"]

    assert exhaustion["state"] == "bounded_estimate"
    assert exhaustion["label"] == "estimate"
    assert exhaustion["unit"] == "percent_of_window_remaining"
    assert exhaustion["observed_remaining_quota"] == 40.0

    # 40 points remaining at 4/hour -> 10h; at 2/hour -> 20h.
    assert exhaustion["range"]["kind"] == "seconds_to_exhaustion"
    assert exhaustion["range"]["lower"] == 10 * 3600
    assert exhaustion["range"]["upper"] == 20 * 3600
    assert exhaustion["range"]["clamped_at_reset"] is False
    assert exhaustion["range"]["exhausts_before_reset"] is True

    assert exhaustion["rate_bracket"]["source"] == "provider_api_burn_rate"
    assert exhaustion["rate_bracket"]["lower_per_hour"] == 2.0
    assert exhaustion["rate_bracket"]["upper_per_hour"] == 4.0
    assert exhaustion["rate_bracket"]["unit"] == "percent_of_window_remaining_per_hour"

    basis = exhaustion["derivation_basis"]
    assert basis["formula"] == "seconds_to_exhaustion = remaining_quota / rate_per_hour"
    assert "forward_shipped_rate_bracket_holds_for_the_rest_of_the_window" in basis["assumptions"]
    assert exhaustion["confidence"] == "medium"

    provenance = exhaustion["provenance"]
    assert provenance["quota_source"] == "provider_api"
    assert provenance["quota_observed_at"] == OBSERVED_AT
    assert row["observed"]["configured_concurrency_cap"] == 7
    assert row["observed"]["occupied_slots_upper"] == 3
    assert row["exhaustion_forecast"]["slot_pressure"]["free_slots_upper"] == 4

    # Remaining quota is echoed, never converted into a new unit.
    assert row["observed"]["remaining_quota"] == 40.0
    assert row["observed"]["remaining_quota_basis"] == "percent_of_window_remaining"
    assert any(
        gap["code"] == "CLASS_SPECIFIC_USAGE_NOT_OBSERVED" for gap in forecast["data_gaps"]
    )


def test_observation_series_produces_measured_rate_bracket():
    preview = _preview(
        [
            _observed_row(
                "glm:chairman-max",
                "glm",
                remaining=30.0,
                cap=8,
                quota_observations=[
                    {"observed_at": "2026-11-08T13:31:59Z", "remaining_quota": 50.0},
                    {"observed_at": "2026-11-08T14:31:59Z", "remaining_quota": 42.0},
                    {"observed_at": "2026-11-08T15:31:59Z", "remaining_quota": 30.0},
                ],
            )
        ]
    )
    exhaustion = _forecast(preview)["resources"][0]["exhaustion_forecast"]
    assert exhaustion["rate_bracket"]["source"] == "observation_series"
    assert exhaustion["rate_bracket"]["sample_count"] == 3
    # Segment rates: 8/h then 12/h.
    assert exhaustion["rate_bracket"]["lower_per_hour"] == 8.0
    assert exhaustion["rate_bracket"]["upper_per_hour"] == 12.0
    assert exhaustion["range"]["lower"] == int(round(30.0 / 12.0 * 3600))
    assert exhaustion["range"]["upper"] == int(round(30.0 / 8.0 * 3600))
    assert exhaustion["confidence"] == "medium"


def test_observed_headroom_without_a_rate_reports_slots_and_a_data_gap():
    preview = _preview(
        [_observed_row("bailian:Kris", "bailian", remaining=98.81, cap=7)]
    )
    forecast = _forecast(preview)
    exhaustion = forecast["resources"][0]["exhaustion_forecast"]
    assert exhaustion["state"] == "bounded_estimate"
    assert exhaustion["range"] is None
    assert exhaustion["rate_bracket"] is None
    assert "CONSUMPTION_RATE_NOT_OBSERVED" in exhaustion["reason_codes"]
    assert exhaustion["confidence"] == "low"
    assert any(
        gap["code"] == "CONSUMPTION_RATE_NOT_OBSERVED" for gap in forecast["data_gaps"]
    )
    # The slot range is still a bound built from observed occupancy.
    assert exhaustion["slot_pressure"]["free_slots_lower"] == 7
    assert exhaustion["slot_pressure"]["configured_concurrency_cap"] == 7


def test_stale_reset_window_is_flagged_not_projected():
    preview = _preview(
        [
            _observed_row(
                "grok:default",
                "grok",
                remaining=53.0,
                cap=17,
                reset_at="2026-10-12T05:54:00Z",
                observed_consumption_rate_per_hour={"lower": 1.0, "upper": 2.0},
            )
        ]
    )
    forecast = _forecast(preview)
    exhaustion = forecast["resources"][0]["exhaustion_forecast"]
    assert exhaustion["reset_window"]["reset_in_future"] is False
    assert exhaustion["range"] is None
    assert "RESET_WINDOW_STALE_OR_ABSENT" in exhaustion["reason_codes"]
    assert any(gap["code"] == "RESET_AT_NOT_FUTURE" for gap in forecast["data_gaps"])


# ---------------------------------------------------------------------------
# 3. Quota-caused waiting aggregation
# ---------------------------------------------------------------------------


def test_quota_caused_waiting_aggregates_by_pool_and_resource():
    preview = _preview(
        [
            _observed_row("bailian:Chris", "bailian", remaining=8.0, cap=7),
            _observed_row("bailian:Kris", "bailian", remaining=90.0, cap=7),
        ]
    )
    ready_counts = {
        "observed_at": OBSERVED_AT,
        "per_root": {"root-frontend": 4, "root-backend": 2},
        "fleet_total": 6,
        "wait_reason_counts": {
            "bailian": {
                "roots": {"root-frontend": 3, "root-backend": 1},
                "reasons": {"RESOURCE_QUOTA_WINDOW_EXHAUSTED": 4},
            }
        },
    }
    forecast = _forecast(preview, ready_counts=ready_counts)

    waiting = {
        row["shared_quota_resource_ref"]: row["quota_caused_waiting"]
        for row in forecast["resources"]
    }
    # A pool-keyed wait count is attributed to every resource of that pool;
    # the module does not invent a per-account split.
    assert waiting["bailian:Chris"]["requests"] == 4
    assert waiting["bailian:Kris"]["requests"] == 4
    assert waiting["bailian:Chris"]["roots"] == {"root-frontend": 3, "root-backend": 1}
    assert waiting["bailian:Chris"]["attribution_source"] == "ready_counts.wait_reason_counts"
    assert waiting["bailian:Chris"]["bottleneck_buckets"]["provider_quota"] == 4

    recommendation = forecast["recommendations"][0]
    assert recommendation["affected_roots"] == ["root-backend", "root-frontend"]
    assert recommendation["quota_caused_waiting_requests"] == 4
    assert recommendation["constrained_pool_window"]["pool_ref"] == "bailian"
    assert forecast["demand_observation"]["fleet_ready_total"] == 6
    assert forecast["demand_observation"]["attribution_state"] == "observed"


def test_resource_keyed_wait_counts_do_not_leak_to_sibling_resources():
    preview = _preview(
        [
            _observed_row("bailian:Chris", "bailian", remaining=80.0, cap=7),
            _observed_row("bailian:Ryan", "bailian", remaining=2.0, cap=7),
        ]
    )
    ready_counts = {
        "wait_reason_counts": {"bailian:Ryan": {"root-intake": 2}},
    }
    forecast = _forecast(preview, ready_counts=ready_counts)
    by_ref = {row["shared_quota_resource_ref"]: row for row in forecast["resources"]}
    assert by_ref["bailian:Ryan"]["quota_caused_waiting"]["requests"] == 2
    assert by_ref["bailian:Chris"]["quota_caused_waiting"]["requests"] == 0


# ---------------------------------------------------------------------------
# 4. Recommendation ordering: cheap fixes first, subscription last
# ---------------------------------------------------------------------------


def test_spare_route_reallocation_precedes_subscription_change():
    preview = _preview(
        [
            # Constrained pool, no eligible alternative inside it.
            _observed_row("go:C2", "go", remaining=2.0, cap=3),
            # Eligible spare route elsewhere.
            _observed_row("bailian:Chris", "bailian", remaining=95.0, cap=7),
        ]
    )
    ready_counts = {
        "wait_reason_counts": {"go": {"root-a": 2}},
    }
    forecast = _forecast(preview, ready_counts=ready_counts)
    recommendation = next(
        item for item in forecast["recommendations"]
        if item["constrained_pool_window"]["pool_ref"] == "go"
    )
    assert recommendation["proposed_action"] == ACTION_REALLOCATE
    alternatives = recommendation["eligible_unused_alternatives"]
    assert [item["shared_quota_resource_ref"] for item in alternatives] == ["bailian:Chris"]
    assert alternatives[0]["observed_spare_slots"] == 7
    assert alternatives[0]["remaining_quota"] == 95.0
    assert recommendation["bottleneck_kind"] == "unknown"


def test_subscription_change_is_last_and_only_without_a_spare_route():
    preview = _preview(
        [
            _observed_row("go:C2", "go", remaining=2.0, cap=3),
            _observed_row("bailian:Ryan", "bailian", remaining=1.0, cap=7),
        ]
    )
    ready_counts = {"wait_reason_counts": {"go": {"root-a": 2}}}
    forecast = _forecast(preview, ready_counts=ready_counts)
    recommendation = next(
        item for item in forecast["recommendations"]
        if item["constrained_pool_window"]["pool_ref"] == "go"
    )
    assert recommendation["eligible_unused_alternatives"] == []
    # bailian:Ryan is eligible in the registry but its headroom is not spare.
    assert recommendation["proposed_action"] == ACTION_SUBSCRIPTION_LAST
    assert recommendation["forecast_confidence"] in {"medium", "low", "none"}
    assert recommendation["remaining_uncertainty"]["codes"]
    assert "no eligible route" in recommendation["expected_benefit"]["statement"]


def test_host_bottleneck_orders_before_reallocation_and_subscription():
    preview = _preview(
        [
            _observed_row("anthropic-oauth:max-1", "anthropic-oauth", remaining=60.0, cap=1),
            _observed_row("go:C1", "go", remaining=1.0, cap=3),
            _observed_row("bailian:Chris", "bailian", remaining=95.0, cap=7),
        ]
    )
    ready_counts = {
        "wait_reason_counts": {
            "anthropic-oauth": {
                "roots": {"root-ci": 3},
                "reasons": {"HOST_SATURATED": 3},
            },
            "go": {"roots": {"root-plan": 1}, "reasons": {"RESOURCE_QUOTA_EXHAUSTED": 1}},
        }
    }
    forecast = _forecast(preview, ready_counts=ready_counts)
    actions = [item["proposed_action"] for item in forecast["recommendations"]]
    assert actions == [ACTION_FIX_HOST, ACTION_REALLOCATE]
    host_rec = forecast["recommendations"][0]
    assert host_rec["bottleneck_kind"] == "host"
    assert host_rec["bottleneck_evidence"]["host_wait_requests"] == 3
    assert host_rec["forecast_source"] is None  # no measured burn rate
    assert host_rec["constrained_pool_window"]["pool_ref"] == "anthropic-oauth"


def test_writer_bottleneck_is_distinct_from_provider_quota():
    preview = _preview([_observed_row("cursor:default", "cursor", remaining=50.0, cap=11)])
    ready_counts = {
        "wait_reason_counts": {
            "cursor": {"roots": {"root-web": 2}, "reasons": {"WORKSPACE_WRITER_LOCKED": 2}}
        }
    }
    forecast = _forecast(preview, ready_counts=ready_counts)
    recommendation = forecast["recommendations"][0]
    assert recommendation["bottleneck_kind"] == "workspace_writer"
    assert recommendation["proposed_action"] == "fix_writer_bottleneck"
    assert recommendation["bottleneck_evidence"]["writer_wait_requests"] == 2


def test_no_demand_and_no_spare_route_recommends_nothing():
    preview = _preview([_observed_row("anthropic-oauth:max-2", "anthropic-oauth", remaining=95.0, cap=1)])
    forecast = _forecast(preview)
    assert forecast["recommendations"] == []
    assert forecast["constrained_without_action"] == []


def test_unknown_headroom_alternative_is_never_a_numeric_advantage():
    preview = _preview(
        [
            _observed_row("go:C3", "go", remaining=1.0, cap=3),
            _resource("minimax:default", "minimax", configured_concurrency_cap=7,
                      admission_eligibility=True, readiness_state="ready"),
        ]
    )
    ready_counts = {"wait_reason_counts": {"go": {"root-a": 1}}}
    forecast = _forecast(preview, ready_counts=ready_counts)
    recommendation = next(
        item for item in forecast["recommendations"]
        if item["constrained_pool_window"]["pool_ref"] == "go"
    )
    assert recommendation["eligible_unused_alternatives"] == []
    assert recommendation["eligible_alternatives_without_observed_headroom"] == [
        "minimax:default"
    ]
    assert recommendation["proposed_action"] == ACTION_SUBSCRIPTION_LAST
    assert "ALTERNATIVE_HEADROOM_NOT_OBSERVED" in recommendation["remaining_uncertainty"]["codes"]


# ---------------------------------------------------------------------------
# 5. No purchase / action-execution surface anywhere
# ---------------------------------------------------------------------------


def test_document_contains_no_purchase_or_execution_fields():
    preview = _preview(
        [
            _observed_row("go:C2", "go", remaining=2.0, cap=3),
            _observed_row("bailian:Chris", "bailian", remaining=95.0, cap=7),
        ]
    )
    forecast = _forecast(
        preview,
        ready_counts={"wait_reason_counts": {"go": {"root-a": 1}}},
        broker={"generation": 7, "active_by_quota_scope": {"go:C2": 2},
                "reserved_by_pool_account": {"go:C2": 1}, "cooldowns": []},
    )
    for path, value in _walk_keys(forecast):
        if isinstance(value, bool):
            # Explicit "executed: false" disclaimers are not a purchase surface.
            continue
        lowered = path[-1].lower()
        for token in FORBIDDEN_KEY_TOKENS:
            assert token not in lowered, f"forbidden key at {path}: {path[-1]}"
    assert forecast["purchases_executed"] is False
    assert forecast["account_changes_executed"] is False
    assert forecast["automatic_actions"] is False
    assert forecast["pricing"]["state"] == "NOT_EVALUATED"
    for recommendation in forecast["recommendations"]:
        assert recommendation["advisory_only"] is True
        assert recommendation["proposed_action"] in {
            ACTION_FIX_HOST,
            "fix_writer_bottleneck",
            ACTION_REALLOCATE,
            ACTION_SUBSCRIPTION_LAST,
        }


# ---------------------------------------------------------------------------
# 6. Provenance: digests of exactly the documents that were read
# ---------------------------------------------------------------------------


def test_input_digests_are_recorded_and_match_the_inputs():
    preview = _preview([_observed_row("bailian:Chris", "bailian", remaining=95.0, cap=7)])
    ready_counts = {"per_root": {"root-a": 1}, "fleet_total": 1}
    broker = {"generation": 11, "active_by_quota_scope": {}, "reserved_by_pool_account": {},
              "cooldowns": []}
    forecast = _forecast(preview, ready_counts=ready_counts, broker=broker)

    def expected(document):
        return hashlib.sha256(
            json.dumps(
                document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("utf-8")
        ).hexdigest()

    provenance = forecast["input_provenance"]
    assert provenance["quota_preview"]["sha256"] == expected(preview)
    assert provenance["quota_preview"]["sha256"] == canonical_digest(preview)
    assert provenance["ready_counts"]["sha256"] == expected(ready_counts)
    assert provenance["broker_observation"]["sha256"] == expected(broker)
    assert provenance["broker_observation"]["generation"] == 11
    assert provenance["quota_preview"]["resource_count"] == 1
    # Every resource row points back at the preview it was read from.
    assert (
        forecast["resources"][0]["observed"]["provenance"]["preview_digest"]
        == provenance["quota_preview"]["sha256"]
    )


def test_broker_observation_widens_observed_occupancy():
    preview = _preview([_observed_row("go:C1", "go", remaining=50.0, cap=3, active=0)])
    broker = {
        "generation": 5,
        "active_by_quota_scope": {"go:C1": 3},
        "reserved_by_pool_account": {"go:C1": 1},
        "cooldowns": [{"scope": "go:C1", "until": "2026-11-08T18:00:00Z"}],
    }
    forecast = _forecast(preview, broker=broker)
    row = forecast["resources"][0]
    assert row["observed"]["occupied_slots_lower"] == 0
    assert row["observed"]["occupied_slots_upper"] == 4
    assert row["observed"]["provenance"]["broker"]["active_leases"] == 3
    assert (
        row["observed"]["provenance"]["broker"]["cooldown_until"]
        == "2026-11-08T18:00:00Z"
    )
    assert row["observed"]["cooldown_state"] is None  # preview carries no cooldown
    assert "CONCURRENCY_SATURATED" in row["constraint_reasons"]
    assert not any(
        gap["code"] == "BROKER_SCOPE_MATCHED_NOTHING" for gap in forecast["data_gaps"]
    )


def test_broker_read_that_matches_no_resource_is_reported_as_a_gap():
    preview = _preview([_observed_row("go:C1", "go", remaining=50.0, cap=3)])
    broker = {"generation": 5, "active_by_quota_scope": {"other:scope": 2},
              "reserved_by_pool_account": {}, "cooldowns": []}
    forecast = _forecast(preview, broker=broker)
    assert any(
        gap["code"] == "BROKER_SCOPE_MATCHED_NOTHING" for gap in forecast["data_gaps"]
    )
    row = forecast["resources"][0]
    assert row["observed"]["provenance"]["broker"]["active_leases"] is None
    assert row["observed"]["occupied_slots_upper"] == 0


# ---------------------------------------------------------------------------
# 7. Data gaps: absent ready counts stay unknown
# ---------------------------------------------------------------------------


def test_absent_ready_counts_is_an_explicit_data_gap():
    preview = _preview(
        [
            _observed_row("bailian:Chris", "bailian", remaining=2.0, cap=7),
            _observed_row("go:C1", "go", remaining=80.0, cap=3),
        ]
    )
    forecast = _forecast(preview, ready_counts=None)
    gaps = {gap["code"] for gap in forecast["data_gaps"]}
    assert "READY_COUNTS_ABSENT" in gaps
    assert forecast["demand_observation"]["attribution_state"] == "absent"
    assert forecast["demand_observation"]["fleet_ready_total"] is None
    assert all(
        row["quota_caused_waiting"]["requests"] == 0 for row in forecast["resources"]
    )
    recommendation = forecast["recommendations"][0]
    assert recommendation["quota_caused_waiting_requests"] == 0
    assert recommendation["affected_roots"] == []
    assert recommendation["proposed_action"] == ACTION_REALLOCATE
    assert recommendation["bottleneck_kind"] == "unknown"
    assert "WAIT_ATTRIBUTION_NOT_OBSERVED" in recommendation["remaining_uncertainty"]["codes"]


def test_empty_ready_counts_are_attributed_but_not_reported_as_zero_demand():
    preview = _preview([_observed_row("bailian:Chris", "bailian", remaining=95.0, cap=7)])
    forecast = _forecast(preview, ready_counts={})
    gaps = {gap["code"] for gap in forecast["data_gaps"]}
    assert "WAIT_ATTRIBUTION_NOT_OBSERVED" in gaps
    assert forecast["demand_observation"]["fleet_ready_total"] is None


def test_malformed_inputs_refuse_instead_of_guessing():
    from control_plane.capacity_demand_forecast import CapacityDemandForecastError

    with pytest.raises(CapacityDemandForecastError):
        produce_capacity_demand_forecast(
            quota_preview=_preview([_resource("go:C1", "go")]),
            ready_counts=None,
            broker_observation=None,
            observed_at="2026-11-08 15:31:59",
        )
    with pytest.raises(CapacityDemandForecastError):
        produce_capacity_demand_forecast(
            quota_preview=_preview([_resource("go:C1", "go")]),
            ready_counts={"per_root": {"root-a": "three"}},
            broker_observation=None,
            observed_at=OBSERVED_AT,
        )
