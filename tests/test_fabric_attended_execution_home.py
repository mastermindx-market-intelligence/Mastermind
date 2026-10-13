"""Inert full-receipt fixtures; no host or canary production."""
import copy
import dataclasses
import importlib.util
from pathlib import Path
import sys

import pytest
from control_plane.executive_fabric_bridge_broker import start_request_sha256
from control_plane.executive_worker_broker import BrokerProtocolError
from test_executive_fabric_adapter import physical, payload, result
from test_fabric_attended_secret_canary import inputs

from control_plane import executive_fabric_adapter as module


def fixture():
    host = dataclasses.replace(physical(), provider='minimax')
    request = payload()
    request['physical_binding_sha256'] = host.digest
    canary, _ = inputs()
    canary['realm_binding'].update(provider_home=host.provider_home,
        physical_binding_sha256=host.digest)
    request['launch_spec'].update(secret_canary_verdict=canary, require_secret_canary=True)
    response = result(request)
    response['physical_binding_sha256'] = host.digest
    response['launch_attestation']['secret_canary_verdict'] = copy.deepcopy(canary)
    response['launch_attestation']['provider_home_identity']['path'] = request['launch_spec']['run_dir'] + '/home'
    return request, response, host


def validate(p, r, h):
    return module.validate_start_result(r, payload=p, physical=h)


def test_actual_execution_home_and_fixed_credential_realm_are_distinct():
    p, r, h = fixture()
    _, att = validate(p, r, h)
    assert att['provider_home_identity']['path'] != h.provider_home
    assert att['secret_canary_verdict']['realm_binding']['provider_home'] == h.provider_home


def test_reporting_credential_realm_as_execution_home_is_rejected():
    p, r, h = fixture()
    r['launch_attestation']['provider_home_identity']['path'] = h.provider_home
    with pytest.raises(BrokerProtocolError):
        validate(p, r, h)


@pytest.mark.parametrize('field', ['run_id', 'job_id', 'worker_id', 'provider_home',
    'physical_binding_sha256', 'execution_profile_id', 'harness_binding_id'])
def test_foreign_realm_cannot_select_execution_home(field):
    p, r, h = fixture()
    p['launch_spec']['secret_canary_verdict']['realm_binding'][field] = 'foreign'
    r['launch_attestation']['secret_canary_verdict'] = copy.deepcopy(p['launch_spec']['secret_canary_verdict'])
    r['request_sha256'] = start_request_sha256(p)
    with pytest.raises(BrokerProtocolError):
        validate(p, r, h)


@pytest.mark.parametrize('path', ['/srv/fabric/runs/another/home', '/srv/fabric/runs/attempt-1/home/child', '/tmp/home'])
def test_wrong_execution_home_is_rejected(path):
    p, r, h = fixture()
    r['launch_attestation']['provider_home_identity']['path'] = path
    with pytest.raises(BrokerProtocolError):
        validate(p, r, h)


def test_canary_bypass_does_not_select_finite_home():
    p, r, h = fixture()
    p['launch_spec']['require_secret_canary'] = False
    r['request_sha256'] = start_request_sha256(p)
    with pytest.raises(BrokerProtocolError):
        validate(p, r, h)


def test_legacy_fixed_home_contract_unchanged():
    p = payload()
    validate(p, result(p), physical())
