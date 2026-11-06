"""Qualify quota exclusion, pinned bypass and reclamation on one full Broker.

All inputs are existing exact repository fixtures. Only synthetic caches and
SQLite are touched; no provider, installed account, native worker or host probe.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import shutil
import sys

import pytest

from tests.test_native_fabric_protected_broker_composition import (
    BUNDLE, FIXTURES, _apply, _module, complete_broker,
)
from tests.test_native_fabric_quota_admission_composition import current_candidate
from tests import test_native_fabric_quota_admission_composition as quota
from tests import test_native_fabric_pinned_waiter_composition as pinned
from tests import test_native_fabric_pinned_waiter_reclaim as reclaim

PINNED_PATCHES = (
    BUNDLE / "pinned_waiters/pinned_account_eligibility.patch",
    BUNDLE / "pinned_waiters/pinned_account_reclaim.patch",
)


def _methods(source):
    cls = next(n for n in ast.parse(source).body
               if isinstance(n, ast.ClassDef) and n.name == "Broker")
    return {n.name: ast.dump(n, include_attributes=False)
            for n in cls.body if isinstance(n, ast.FunctionDef)}


@pytest.fixture
def joined_candidate(current_candidate, tmp_path):
    original, reader = current_candidate
    root = tmp_path / "quota-pinned-reclaim"
    ext = root / "ext"
    ext.mkdir(parents=True)
    target = ext / "lease_broker.py"
    before = Path(original.__file__).read_text()
    target.write_text(before)
    for patch in PINNED_PATCHES:
        _apply(root, patch)
    for name in ("native_broker_admission", "quota_remote"):
        shutil.copyfile(FIXTURES / (name + ".py.txt"), ext / (name + ".py"))
    name = "_fabric_quota_pinned_reclaim_composed_test"
    previous = sys.modules.get(name)
    try:
        module = _module(name, target)
        module._composition_before = before
        module._composition_after = target.read_text()
        yield module, reader
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def test_same_complete_postimage_in_both_valid_patch_orders(complete_broker, tmp_path):
    outputs = []
    for index, order in enumerate(("quota-first", "quota-last")):
        root = tmp_path / order
        ext = root / "ext"
        ext.mkdir(parents=True)
        target = ext / "lease_broker.py"
        target.write_text(complete_broker._composed_source)
        if index == 0:
            _apply(root, FIXTURES / "glm_quota_admission.patch", "--directory=ext")
        for patch in PINNED_PATCHES:
            _apply(root, patch)
        if index == 1:
            _apply(root, FIXTURES / "glm_quota_admission.patch", "--directory=ext")
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1]
    assert hashlib.sha256(outputs[0]).hexdigest() == "7b185deb7a0a3a8c557a9dc04ad52127a11777479793e5316a34698c83e628cb"


def test_quota_exclusion_still_precedes_all_ranking(joined_candidate, tmp_path, monkeypatch):
    quota.test_quota_exclusion_precedes_utilization_and_expiry(joined_candidate, tmp_path, monkeypatch)


@pytest.mark.parametrize("observation", ["missing", "stale", "future", "passed_reset"])
def test_unknown_quota_policy_is_unchanged(joined_candidate, tmp_path, monkeypatch, observation):
    quota.test_uncertain_quota_does_not_invent_parking(joined_candidate, tmp_path, monkeypatch, observation)


@pytest.mark.parametrize("same_root", [False, True])
def test_ready_work_preserves_blocked_sibling(joined_candidate, tmp_path, same_root):
    pinned.test_other_account_can_work_without_erasing_blocked_head(joined_candidate[0], tmp_path, same_root)


@pytest.mark.parametrize("case", [
    pinned.test_proven_full_pin_does_not_freeze_idle_surplus,
    pinned.test_unpinned_waiter_remains_a_real_capacity_contender,
    pinned.test_native_uncertain_hold_is_not_released_to_help_another_account,
    reclaim.test_full_pinned_demand_still_marks_excess_leases_for_reclaim,
    reclaim.test_ready_other_account_does_not_rearm_pinned_account_surplus,
    reclaim.test_heartbeat_cannot_extend_borrowed_surplus_past_its_granted_step,
])
def test_scheduling_and_retention_on_the_quota_composed_broker(joined_candidate, tmp_path, case):
    case(joined_candidate[0], tmp_path)


def test_quota_and_native_guards_are_not_changed_by_queue_composition(joined_candidate):
    module, _ = joined_candidate
    before = _methods(module._composition_before)
    after = _methods(module._composition_after)
    assert set(after) - set(before) == {"_waiter_pinned_account_full"}
    assert {name for name in before if before[name] != after[name]} == {
        "_below_share_waiters", "_front_of_queue", "_register_demand", "_try_acquire"}
    for name in ("account_cap", "account_model_cap", "grantable_accounts", "pool_cap",
                 "_pick_account", "_fresh_glm_expiring_accounts", "_mark_surplus_nonrenewable",
                 "_ensure_schema", "_gc_locked", "heartbeat", "release", "fair_share"):
        assert before[name] == after[name], name
