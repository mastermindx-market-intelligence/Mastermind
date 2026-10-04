"""Source-only capacity projection tests. No provider, host, lease or queue I/O."""
import copy
import dataclasses
import random
from datetime import datetime, timedelta, timezone

import pytest

from control_plane.capacity_economics_projection import (
    CapacityEconomicsProjectionError,
    CapacityProjectionScope,
    project_capacity_bounded_preference,
    project_quota_preference,
)

NOW = datetime(2026, 10, 4, 20, 30, tzinfo=timezone.utc)
TIERS = (
    {"tier_id": "routine.primary", "model_aliases": ["glm.flash", "glm.full"]},
    {"tier_id": "routine.fallback", "model_aliases": ["other.worker"]},
)
SCOPE = CapacityProjectionScope(
    root_operation_ref="root.mission", operation_ref="child.build",
    quota_domain_ref="glm.account.a", workload_ref="cohort.routine.v1",
    quota_window_refs=("glm.a.five_hour.epoch1", "glm.a.week.epoch3"),
    ancestor_operation_refs=("domain.engineering",),
)


def preview():
    return {
        "schema": "mastermind.quota_economics_preview/v1",
        "as_of": "2026-10-04T20:30:00Z",
        "authority": "NONE_PREVIEW_ONLY", "binding_verification": "NOT_PERFORMED",
        "live_admission": False, "claim_time_revalidation_required": True,
        "status": "PREVIEW_READY", "suggested_option": "glm.a.flash",
        "selected_tier": "routine.primary",
        "options": [{
            "option_id": "glm.a.flash", "provider": "glm", "model_alias": "glm.flash",
            "eligible_in_preview": True, "estimated_startable_jobs": 30,
            "suggested_parallelism": 20, "expiry_pressure_jobs_per_hour": "1.250000",
            "forecasts": [],
        }],
    }


def bound(kind, scope, ref, remaining):
    return {"kind": kind, "scope": scope, "scope_ref": ref,
            "remaining": remaining, "evidence_ref": "owner.fact.v1"}


def envelope():
    refs = {"provider": "glm", "account": SCOPE.quota_domain_ref, "model": "glm.flash",
            "host": "host.worker.1", "root": SCOPE.root_operation_ref,
            "operation": SCOPE.operation_ref, "review": "review.cohort.1"}
    constraints = [bound("concurrency", key, ref, 10) for key, ref in refs.items()]
    constraints += [bound("starts", "root", SCOPE.root_operation_ref, 30),
                    bound("starts", "operation", SCOPE.operation_ref, 25)]
    constraints += [bound("starts", "quota_window", ref, 20) for ref in SCOPE.quota_window_refs]
    for ref in SCOPE.ancestor_operation_refs:
        constraints += [bound("starts", "ancestor", ref, 20),
                        bound("concurrency", "ancestor", ref, 10)]
    return {
        "schema": "mastermind.capacity_owner_envelope/v1",
        "observation_ref": "capacity.snapshot.1",
        "observed_at": "2026-10-04T20:29:45Z", "valid_until": "2026-10-04T20:31:00Z",
        "option_id": "glm.a.flash", "provider": "glm", "model_alias": "glm.flash",
        "root_operation_ref": SCOPE.root_operation_ref, "operation_ref": SCOPE.operation_ref,
        "quota_domain_ref": SCOPE.quota_domain_ref, "workload_ref": SCOPE.workload_ref,
        "constraints": constraints,
    }


def project(doc=None, hint=None, **kwargs):
    params = {"scope": SCOPE, "now": NOW, "max_age_seconds": 60}
    params.update(kwargs)
    return project_capacity_bounded_preference(
        TIERS, preview() if hint is None else hint, envelope() if doc is None else doc, **params,
    )


def edit_bound(doc, kind, category, remaining, ref=None):
    rows = [row for row in doc["constraints"] if row["kind"] == kind
            and row["scope"] == category and (ref is None or row["scope_ref"] == ref)]
    assert rows
    for row in rows:
        row["remaining"] = remaining


def test_flash_model_ceiling_cannot_override_tighter_shared_account_ceiling():
    doc = envelope()
    edit_bound(doc, "concurrency", "model", 20)
    edit_bound(doc, "concurrency", "account", 3)
    result = project(doc)
    assert result.suggested_parallelism == 3
    assert result.estimated_startable_jobs == 20
    assert "concurrency:account:glm.account.a" in result.limiting_constraints


def test_full_model_headroom_remains_a_distinct_constraint():
    doc, hint = envelope(), preview()
    doc["model_alias"] = hint["options"][0]["model_alias"] = "glm.full"
    for row in doc["constraints"]:
        if row["scope"] == "model":
            row.update(scope_ref="glm.full", remaining=2)
    assert project(doc, hint).suggested_parallelism == 2


@pytest.mark.parametrize("category", ["provider", "account", "model", "host", "root", "operation", "review", "ancestor"])
def test_every_concurrency_dimension_can_block_a_wave(category):
    doc = envelope()
    edit_bound(doc, "concurrency", category, 0)
    result = project(doc)
    assert result.status == "WAIT_CAPACITY"
    assert result.suggested_parallelism == 0
    assert result.estimated_startable_jobs == 20


@pytest.mark.parametrize("category", ["root", "operation", "ancestor", "quota_window"])
def test_every_start_budget_can_block_a_wave_even_when_slots_are_free(category):
    doc = envelope()
    edit_bound(doc, "starts", category, 0)
    result = project(doc)
    assert (result.status, result.estimated_startable_jobs, result.suggested_parallelism) == ("WAIT_CAPACITY", 0, 0)


def test_weekly_budget_is_not_added_to_or_replaced_by_short_window_budget():
    doc = envelope()
    edit_bound(doc, "starts", "quota_window", 1, SCOPE.quota_window_refs[1])
    result = project(doc)
    assert result.estimated_startable_jobs == result.suggested_parallelism == 1


@pytest.mark.parametrize("index", range(len(envelope()["constraints"])))
def test_unknown_in_any_required_dimension_blocks_positive_projection(index):
    doc = envelope()
    doc["constraints"][index]["remaining"] = None
    result = project(doc)
    assert result.status == "WAIT_EVIDENCE"
    assert result.estimated_startable_jobs is None
    assert result.suggested_parallelism == 0
    assert len(result.unknown_constraints) == 1


@pytest.mark.parametrize("index", range(len(envelope()["constraints"])))
def test_dropping_any_required_axis_window_or_ancestor_is_refused(index):
    doc = envelope()
    del doc["constraints"][index]
    with pytest.raises(CapacityEconomicsProjectionError):
        project(doc)


@pytest.mark.parametrize("bad", [-1, True, False, 0.5, "4", float("nan"), float("inf"), {}, []])
def test_remaining_must_be_nonnegative_integer_or_explicit_unknown(bad):
    doc = envelope()
    doc["constraints"][0]["remaining"] = bad
    with pytest.raises(CapacityEconomicsProjectionError, match="non-negative integer"):
        project(doc)


@pytest.mark.parametrize("key", ["option_id", "provider", "model_alias", "root_operation_ref", "operation_ref", "quota_domain_ref", "workload_ref"])
def test_candidate_account_operation_and_workload_binding_cannot_be_transplanted(key):
    doc = envelope()
    doc[key] = "foreign.scope"
    with pytest.raises(CapacityEconomicsProjectionError, match="binding mismatch"):
        project(doc)


@pytest.mark.parametrize("category", ["provider", "account", "model", "root", "operation"])
def test_constraint_reference_must_match_its_bound_owner_scope(category):
    doc = envelope()
    row = next(row for row in doc["constraints"] if row["scope"] == category)
    row["scope_ref"] = "foreign.scope"
    with pytest.raises(CapacityEconomicsProjectionError, match="binding mismatch"):
        project(doc)


def test_duplicate_constraints_and_unexpected_ancestors_are_refused():
    doc = envelope()
    doc["constraints"].append(copy.deepcopy(doc["constraints"][0]))
    with pytest.raises(CapacityEconomicsProjectionError, match="duplicate"):
        project(doc)
    doc = envelope()
    doc["constraints"].append(bound("starts", "ancestor", "unrelated.domain", 10))
    with pytest.raises(CapacityEconomicsProjectionError, match="ancestor set"):
        project(doc)


def test_unknown_window_is_not_a_substitute_for_an_exhausted_required_window():
    doc = envelope()
    row = next(row for row in doc["constraints"] if row["scope_ref"] == SCOPE.quota_window_refs[1])
    row["scope_ref"] = "glm.a.week.future_epoch"
    row["remaining"] = 1000
    with pytest.raises(CapacityEconomicsProjectionError, match="window set"):
        project(doc)


@pytest.mark.parametrize("field,value", [
    ("observed_at", "2026-10-04T20:30:01Z"),
    ("observed_at", "2026-10-04T20:28:59Z"),
    ("observed_at", "2026-10-04T20:30:00"),
    ("observed_at", "2026-13-04T20:30:00Z"),
    ("observed_at", "tomorrow"),
    ("valid_until", "2026-10-04T20:30:00Z"),
    ("valid_until", "2026-10-04T20:29:00Z"),
])
def test_future_stale_expired_naive_and_invalid_evidence_is_refused(field, value):
    doc = envelope()
    doc[field] = value
    with pytest.raises(CapacityEconomicsProjectionError):
        project(doc)


@pytest.mark.parametrize("timestamp", ["2026-10-04T20:28:59Z", "2026-10-04T20:30:01Z", "next reset"])
def test_preview_itself_must_also_be_fresh(timestamp):
    hint = preview()
    hint["as_of"] = timestamp
    with pytest.raises(CapacityEconomicsProjectionError):
        project(hint=hint)


def test_freshness_boundary_and_equivalent_timezone_are_deterministic():
    doc = envelope()
    doc["observed_at"] = "2026-10-04T13:29:00-07:00"
    assert project(doc).suggested_parallelism == 10
    with pytest.raises(CapacityEconomicsProjectionError):
        project(doc, now=NOW + timedelta(microseconds=1))


@pytest.mark.parametrize("age", [0, -1, True, "60", 60.0, None])
def test_observation_age_policy_must_be_explicit_positive_integer(age):
    with pytest.raises(CapacityEconomicsProjectionError):
        project(max_age_seconds=age)


def test_now_must_be_explicit_and_timezone_aware():
    with pytest.raises(CapacityEconomicsProjectionError, match="timezone-aware"):
        project(now=NOW.replace(tzinfo=None))


def test_future_economic_forecast_and_ttl_do_not_replenish_current_capacity():
    doc, hint = envelope(), preview()
    edit_bound(doc, "starts", "quota_window", 0, SCOPE.quota_window_refs[1])
    hint["options"][0]["forecasts"] = [
        {"remaining_starts": 10000, "after_reset": "2026-10-05T00:00:00Z", "lease_ttl": 1}
    ]
    assert project(doc, hint).suggested_parallelism == 0


def test_unknown_or_permission_fields_are_not_silently_accepted():
    doc = envelope()
    doc["live_admission"] = True
    with pytest.raises(CapacityEconomicsProjectionError, match="unsupported fields"):
        project(doc)
    doc = envelope()
    doc["constraints"][0]["after_reset_remaining"] = 100
    with pytest.raises(CapacityEconomicsProjectionError, match="unsupported fields"):
        project(doc)


def test_source_bounds_and_snapshots_are_not_mutated_and_result_is_frozen():
    doc, hint = envelope(), preview()
    before = copy.deepcopy((doc, hint))
    result = project(doc, hint)
    assert (doc, hint) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.suggested_parallelism = 100
    doc["constraints"][0]["remaining"] = 0
    assert result.suggested_parallelism == 10


@pytest.mark.parametrize("remaining", [0, None, 10])
def test_every_output_is_preview_only_not_authentication_or_a_claim(remaining):
    doc = envelope()
    edit_bound(doc, "concurrency", "account", remaining)
    output = project(doc).to_dict()
    assert output["schema"] == "mastermind.capacity_economics_projection/v2"
    assert output["authority"] == "NONE_PREVIEW_ONLY"
    assert output["binding_verification"] == "NOT_PERFORMED"
    assert output["live_admission"] is False
    assert output["selection_is_commitment"] is False
    assert output["claim_time_revalidation_required"] is True


def test_capacity_cannot_promote_an_ineligible_or_later_tier():
    hint = preview()
    hint["selected_tier"] = "routine.fallback"
    hint["options"][0]["model_alias"] = "other.worker"
    with pytest.raises(CapacityEconomicsProjectionError, match="first lawful suitability tier"):
        project(hint=hint)


def test_limits_never_increase_economic_hint():
    hint = preview()
    hint["options"][0].update(estimated_startable_jobs=4, suggested_parallelism=2)
    result = project(hint=hint)
    assert result.estimated_startable_jobs == 4
    assert result.suggested_parallelism == 2


def test_constraint_order_does_not_change_result():
    doc = envelope()
    expected = project(doc).to_dict()
    doc["constraints"].reverse()
    assert project(doc).to_dict() == expected


def test_500_seeded_cases_conserve_every_budget_and_lowering_never_increases_wave():
    rng = random.Random(1042026)
    for _ in range(500):
        doc = envelope()
        for row in doc["constraints"]:
            row["remaining"] = rng.randrange(31)
        result = project(doc)
        assert 0 <= result.suggested_parallelism <= result.estimated_startable_jobs <= 30
        for row in doc["constraints"]:
            value = result.estimated_startable_jobs if row["kind"] == "starts" else result.suggested_parallelism
            assert value <= row["remaining"]
        index = rng.randrange(len(doc["constraints"]))
        doc["constraints"][index]["remaining"] //= 2
        lowered = project(doc)
        assert lowered.suggested_parallelism <= result.suggested_parallelism
        assert lowered.estimated_startable_jobs <= result.estimated_startable_jobs


def test_more_than_80_constraints_is_an_input_refusal_not_a_fleet_limit():
    doc = envelope()
    doc["constraints"] = doc["constraints"] * 7
    with pytest.raises(CapacityEconomicsProjectionError, match="bounded list"):
        project(doc)


@pytest.mark.parametrize("field,value", [
    ("quota_window_refs", ()),
    ("quota_window_refs", ["window.a"]),
    ("quota_window_refs", ("window.a", "window.a")),
    ("ancestor_operation_refs", ("domain.a", "domain.a")),
    ("ancestor_operation_refs", ("root.mission",)),
    ("ancestor_operation_refs", ("child.build",)),
])
def test_scope_requires_complete_immutable_unique_owner_references(field, value):
    with pytest.raises(CapacityEconomicsProjectionError):
        dataclasses.replace(SCOPE, **{field: value})


def test_existing_v1_projection_is_explicitly_preserved_not_silently_relabelled():
    hint = project_quota_preference(TIERS, preview()).to_dict()
    assert hint["schema"] == "mastermind.capacity_economics_projection/v1"
    assert "capacity_scope" not in hint
    assert hint["suggested_parallelism"] == 20
