"""Installed acceptance must qualify selected quota names without restamping Runtime."""
from itertools import combinations

import pytest

from ops.executive_os.acceptance import AcceptanceError, _validate_operator_harness_policy


QUOTAS = ("quota_class", "coo_quota_class", "coo_default_quota_class", "coo_operator_quota_class")


def policy(armed=False):
    return {
        "quota_class": "codex-native",
        "coo_quota_class": "codex-coo-current-v5",
        "coo_default_quota_class": "codex-coo-default-current-v5",
        "coo_operator_quota_class": "codex-coo-operator-current-v5",
        "coo_operator_model_alias": "coo.operator.readonly",
        "coo_operator_harness_armed": armed,
    }, {"schema_version": "mastermind.executive_worker_broker_config/v4",
        "operator_harness_armed": armed}


@pytest.mark.parametrize("armed", [False, True])
def test_current_distinct_quota_names_pass_without_mutating_config(armed):
    config, worker = policy(armed)
    before = (dict(config), dict(worker))
    _validate_operator_harness_policy(config, worker)
    assert (config, worker) == before


def test_historical_defaults_still_pass():
    config, worker = policy()
    for field in QUOTAS[:-1]:
        del config[field]
    config[QUOTAS[-1]] = "codex-coo-operator"
    _validate_operator_harness_policy(config, worker)


@pytest.mark.parametrize("field", QUOTAS)
@pytest.mark.parametrize("invalid", [None, True, "", "bad/name", " name", "x" * 65])
def test_malformed_or_nonstring_selected_quota_refuses(field, invalid):
    config, worker = policy()
    config[field] = invalid
    with pytest.raises(AcceptanceError):
        _validate_operator_harness_policy(config, worker)


@pytest.mark.parametrize("left,right", list(combinations(QUOTAS, 2)))
def test_quota_collision_refuses(left, right):
    config, worker = policy()
    config[left] = config[right]
    with pytest.raises(AcceptanceError):
        _validate_operator_harness_policy(config, worker)


@pytest.mark.parametrize("target,field,value", [
    ("control", "coo_operator_model_alias", "coo.sealed"),
    ("control", "coo_operator_harness_armed", 0),
    ("control", "coo_operator_harness_armed", None),
    ("worker", "operator_harness_armed", True),
    ("worker", "operator_harness_armed", 0),
    ("worker", "schema_version", "mastermind.executive_worker_broker_config/v3"),
])
def test_wrong_profile_schema_or_arm_refuses(target, field, value):
    config, worker = policy()
    (config if target == "control" else worker)[field] = value
    with pytest.raises(AcceptanceError):
        _validate_operator_harness_policy(config, worker)
