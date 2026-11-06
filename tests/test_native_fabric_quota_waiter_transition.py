"""An existing quota-parked pin must not block unrelated ready-account work.

Full composed broker/reader, synthetic cache and SQLite. This never migrates the
blocked request or relaxes its own account/provider/host/native admission.
"""
from __future__ import annotations

import ast
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

import pytest
import yaml

from tests.test_native_fabric_protected_broker_composition import (
    BUNDLE, _apply, _module, broker, complete_broker, native_binding,
)
from tests.test_native_fabric_quota_admission_composition import current_candidate
from tests.test_native_fabric_quota_pinned_reclaim_composition import joined_candidate
from tests.test_native_fabric_advisory_reset_boundary import advisory_reader, state, NOW


@pytest.fixture
def quota_yield_candidate(joined_candidate, advisory_reader, tmp_path, monkeypatch):
    original, _ = joined_candidate
    root = tmp_path / "quota-waiter-transition"
    (root / "ext").mkdir(parents=True)
    target = root / "ext/lease_broker.py"
    before = Path(original.__file__).read_text()
    target.write_text(before)
    if os.environ.get("FABRIC_QUOTA_WAITER_PREIMAGE") != "1":
        _apply(root, BUNDLE / "pinned_waiters/pinned_quota_waiter.patch")
    monkeypatch.setitem(sys.modules, "quota_remote", advisory_reader)
    name = "_fabric_quota_waiter_transition_test"
    previous = sys.modules.get(name)
    try:
        value = _module(name, target)
        value._before_transition = before
        value._after_transition = target.read_text()
        yield value, advisory_reader
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def setup_queue(candidate, tmp_path, monkeypatch, *, occupied=True, native=False):
    module, reader = candidate
    br, clock = broker(module, tmp_path)
    Path(br.accounts_path).write_text(yaml.safe_dump({"providers": {"glm": {
        "enabled": True, "accounts": [
            {"name": "busy", "per_account_cap": 1, "per_model_caps": {"glm-5.3": 1}},
            {"name": "free", "per_account_cap": 3, "per_model_caps": {"glm-5.3": 3}},
        ]}}}))
    br.external_gates = True
    cache = tmp_path / "transition-cache.json"
    cache.write_text("{}")
    monkeypatch.setattr(reader, "CACHE_PATH", str(cache))
    binding = None
    if native:
        binding = {**native_binding(), "pool": "glm", "account": "busy",
                   "model": "glm-5.3", "task_class": "review"}
        held = br.acquire_native_admission(binding)
        assert held["state"] == "RETAINED"
        lid = held["grant"]["lease_id"]
    else:
        held = br.acquire("holder", "glm", account="busy", task_class="review",
                          job_class="review", request_id="held", model="glm-5.3")
        assert held.ok
        lid = held.lease_id
    blocked = br.acquire("waiting", "glm", account="busy", task_class="review",
                         job_class="heal", request_id="blocked", model="glm-5.3")
    assert not blocked.ok and blocked.reason == "account_unavailable"
    if not occupied:
        assert br.release(lid, "holder")
    return br, reader, cache, clock, lid, binding


def publish_quota(reader, cache, *, observation="fresh", remaining=2.0):
    observed = NOW - 1000 if observation == "stale" else NOW + 10 if observation == "future" else NOW - 1
    reset = NOW - 1 if observation == "passed_reset" else NOW + 60
    record = asdict(state(reader, observed=observed, reset=reset, remaining=remaining))
    doc = {} if observation == "missing" else {"glm": {"accounts": {"busy": {
        "refreshed_at": observed, "states": [record],
    }}}}
    cache.write_text(json.dumps(doc))


def acquire_ready(br, rid="ready"):
    return br.acquire("ready", "glm", account="free", task_class="review",
                      job_class="review", request_id=rid, model="glm-5.3")


@pytest.mark.parametrize("occupied", [False, True])
def test_fresh_quota_hold_does_not_obstruct_other_account(quota_yield_candidate, tmp_path, monkeypatch, occupied):
    module, _ = quota_yield_candidate
    br, reader, cache, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=occupied)
    publish_quota(reader, cache)
    before = cache.read_bytes()
    result = acquire_ready(br)
    assert result.ok and result.account == "free", result.reason
    with br._conn() as conn:
        rows = list(conn.execute("SELECT * FROM waiters WHERE orchestrator_id='waiting'"))
        assert len(rows) == 1 and rows[0]["account"] == "busy"
        assert rows[0]["id"] == module._request_waiter_id("waiting", "glm", "blocked")
        assert not br._held_by(conn, "waiting", "glm")
    assert cache.read_bytes() == before


def test_quota_hold_can_not_disable_idle_capacity_borrowing(quota_yield_candidate, tmp_path, monkeypatch):
    br, reader, cache, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch)
    publish_quota(reader, cache)
    first = acquire_ready(br, "ready-a")
    assert first.ok, first.reason
    second = acquire_ready(br, "ready-b")
    assert second.ok and second.state == "rented", second.reason
    with br._conn() as conn:
        assert br.fair_share(conn, "glm") == 1
        assert len(br._active_leases(conn, "glm")) == 3


def test_own_parked_request_is_never_rerouted_or_granted(quota_yield_candidate, tmp_path, monkeypatch):
    br, reader, cache, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=False)
    publish_quota(reader, cache)
    result = br.acquire("waiting", "glm", account="busy", task_class="review",
                        job_class="heal", request_id="blocked", model="glm-5.3")
    assert not result.ok
    with br._conn() as conn:
        assert not br._held_by(conn, "waiting", "glm")
        assert len(list(conn.execute("SELECT * FROM waiters WHERE orchestrator_id='waiting'"))) == 1


@pytest.mark.parametrize("observation", ["missing", "stale", "future", "passed_reset", "available"])
def test_unproven_or_reopened_quota_keeps_original_priority(quota_yield_candidate, tmp_path, monkeypatch, observation):
    br, reader, cache, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=False)
    publish_quota(reader, cache, observation=observation, remaining=80.0 if observation == "available" else 2.0)
    result = acquire_ready(br)
    assert not result.ok and result.reason == "priority_wait"


def test_new_available_observation_restores_original_waiter_not_a_new_request(quota_yield_candidate, tmp_path, monkeypatch):
    br, reader, cache, _, lid, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch)
    publish_quota(reader, cache)
    ready = acquire_ready(br)
    assert ready.ok
    assert br.release(lid, "holder")
    publish_quota(reader, cache, remaining=80.0)
    assert not acquire_ready(br, "later-ready").ok
    result = br.acquire("waiting", "glm", account="busy", task_class="review",
                        job_class="heal", request_id="blocked", model="glm-5.3")
    assert result.ok and result.account == "busy"


def test_native_retained_capacity_is_not_recycled_when_pin_yields(quota_yield_candidate, tmp_path, monkeypatch):
    br, reader, cache, _, lid, binding = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, native=True)
    publish_quota(reader, cache)
    assert acquire_ready(br).ok
    assert br.release(lid, "native-root") is False
    assert br.read_native_admission(binding)["lease_state"] in ("held", "rented")


@pytest.mark.parametrize("field,value", [("account", None), ("account", "missing"), ("account", 7)])
def test_unknown_pin_is_not_provider_proof(quota_yield_candidate, tmp_path, monkeypatch, field, value):
    br, reader, cache, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=False)
    publish_quota(reader, cache)
    assert br._waiter_pinned_quota_parked("glm", {field: value}) is False


def test_duplicate_configured_name_is_not_a_unique_pin(quota_yield_candidate, tmp_path, monkeypatch):
    br, reader, cache, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=False)
    publish_quota(reader, cache)
    original = br.provider
    def duplicate(pool):
        doc = original(pool)
        doc["accounts"] = doc["accounts"] + [dict(doc["accounts"][0])]
        return doc
    monkeypatch.setattr(br, "provider", duplicate)
    assert br._waiter_pinned_quota_parked("glm", {"account": "busy"}) is False


def test_no_quota_reader_failure_can_remove_a_waiter(quota_yield_candidate, tmp_path, monkeypatch):
    br, reader, _, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=False)
    def bad(*args, **kwargs):
        raise ValueError("fixture observation unavailable")
    monkeypatch.setattr(reader, "cached_glm_account_parked", bad)
    assert br._waiter_pinned_quota_parked("glm", {"account": "busy"}) is False


def test_reclamation_view_retains_even_quota_held_demand(quota_yield_candidate, tmp_path, monkeypatch):
    br, reader, cache, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=False)
    publish_quota(reader, cache)
    with br._conn() as conn:
        assert br._below_share_waiters(conn, "glm", "", 1) == []
        rows = br._below_share_waiters(conn, "glm", "", 1, include_full_pins=True)
        assert len(rows) == 1 and rows[0]["orchestrator_id"] == "waiting"


def test_only_read_only_ready_demand_views_change(quota_yield_candidate):
    module, _ = quota_yield_candidate
    def methods(source):
        cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "Broker")
        return {n.name: ast.dump(n, include_attributes=False) for n in cls.body if isinstance(n, ast.FunctionDef)}
    before, after = methods(module._before_transition), methods(module._after_transition)
    assert set(after) - set(before) == {"_waiter_pinned_quota_parked"}
    assert {name for name in before if before[name] != after[name]} == {"_front_of_queue", "_below_share_waiters"}
    for name in ("_try_acquire", "_register_demand", "_mark_surplus_nonrenewable", "_gc_locked",
                 "_ensure_schema", "heartbeat", "release", "fair_share", "account_cap", "_pick_account"):
        assert before[name] == after[name], name


@pytest.mark.parametrize("condition", ["external-disabled", "other-pool", "provider-disabled"])
def test_noneligible_quota_path_is_not_observed(quota_yield_candidate, tmp_path, monkeypatch, condition):
    br, reader, _, _, _, _ = setup_queue(quota_yield_candidate, tmp_path, monkeypatch, occupied=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("quota reader reached outside eligible GLM path")
    monkeypatch.setattr(reader, "cached_glm_account_parked", forbidden)
    pool = "glm"
    if condition == "external-disabled":
        br.external_gates = False
    elif condition == "other-pool":
        pool = "minimax"
    else:
        original = br.provider
        monkeypatch.setattr(br, "provider", lambda p: {**original(p), "enabled": False})
    assert br._waiter_pinned_quota_parked(pool, {"account": "busy"}) is False


@pytest.mark.parametrize("case", [
    "test_full_pinned_demand_still_marks_excess_leases_for_reclaim",
    "test_ready_other_account_does_not_rearm_pinned_account_surplus",
    "test_heartbeat_cannot_extend_borrowed_surplus_past_its_granted_step",
])
def test_previous_reclamation_contract_on_final_component(quota_yield_candidate, tmp_path, case):
    from tests import test_native_fabric_pinned_waiter_reclaim as prior
    getattr(prior, case)(quota_yield_candidate[0], tmp_path)


@pytest.mark.parametrize("case", [
    "test_complete_request_success_retains_sibling_demand",
    "test_native_original_binding_and_ordinary_release_fences_survive",
    "test_native_uncertainty_retains_capacity_while_ordinary_ttl_expires",
    "test_native_grant_still_consumes_shared_capacity",
    "test_normalized_choice_uses_full_broker_account_counts",
])
def test_previous_binding_and_balancing_contract_on_final_component(quota_yield_candidate, tmp_path, case):
    from tests import test_native_fabric_protected_broker_composition as prior
    getattr(prior, case)(quota_yield_candidate[0], tmp_path)


@pytest.mark.parametrize("logical", ["heal", "review", "mechanical"])
def test_ordinary_metadata_is_not_native_binding_in_final_component(quota_yield_candidate, tmp_path, logical):
    from tests import test_native_fabric_protected_broker_composition as prior
    prior.test_complete_ordinary_acquire_never_attaches_native_binding(quota_yield_candidate[0], tmp_path, logical)
