"""Actual config-reader to sealed-policy join; no host or provider effects."""
import dataclasses
import json
import os

import pytest

from scripts import executive_os_phase1c_worker as worker
from tests.test_fabric_attended_probe_join import finite_definition
from tests.test_subscription_worker_config import _config, ALIBABA_BINDING


def read(tmp_path, value):
    path = tmp_path / 'worker.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return worker._load_config(path, require_root_owner=False)


def test_actual_finite_reader_reaches_sealed_policy(tmp_path):
    value = finite_definition()
    value.update(worker_uid=os.geteuid(), worker_gid=os.getegid(),
                 allowed_supplementary_gids=[])
    for field in ('workspace_root', 'run_root', 'provider_home'):
        path = tmp_path / field
        path.mkdir(mode=0o700)
        value[field] = str(path)
    loaded = read(tmp_path, value)
    policy = dataclasses.replace(worker._broker_policy(loaded), require_assignment_seal=True)
    assert policy.require_assignment_seal and not policy.allowed_supplementary_gids


@pytest.mark.parametrize('groups', [[12, 61, 100], [12, 61, 100, 396], [20]])
def test_finite_reader_refuses_any_supplementary_groups(tmp_path, groups):
    value = finite_definition()
    value['allowed_supplementary_gids'] = groups
    with pytest.raises(worker.WorkerConfigError, match='supplementary'):
        read(tmp_path, value)


@pytest.mark.parametrize('groups', [None, {}, [True], [0], [460], [12, 12]])
def test_finite_reader_keeps_group_shape_checks(tmp_path, groups):
    value = finite_definition()
    value['allowed_supplementary_gids'] = groups
    with pytest.raises(worker.WorkerConfigError, match='supplementary'):
        read(tmp_path, value)


@pytest.mark.parametrize('schema,binding', [
    (worker.CONFIG_SCHEMA_VERSION, None),
    (worker.SUBSCRIPTION_CONFIG_SCHEMA_VERSION, ALIBABA_BINDING),
])
def test_ordinary_realms_keep_reviewed_ambient_contract(tmp_path, schema, binding):
    value = _config(tmp_path, schema=schema, binding_id=binding)
    assert read(tmp_path, value)['allowed_supplementary_gids'] == [12, 61, 100]
    value['allowed_supplementary_gids'] = []
    with pytest.raises(worker.WorkerConfigError, match='supplementary'):
        read(tmp_path, value)
