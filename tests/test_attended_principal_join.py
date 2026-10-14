"""Different Control/worker principals; fixture definition, no installed probe."""
import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from control_plane import fabric_attended_canary as probe
from control_plane.executive_worker_broker import BrokerStateError, _launch_spec_to_json
from scripts import executive_os_phase1c as control
from tests.test_executive_fabric_adapter import _fixture, physical


def case(tmp_path, monkeypatch, *, during=None):
    class Client:
        async def request(self, op, payload, **kwargs):
            if during:
                during(self)
            return dict(adapter_id='attended-fabric', binding=payload['binding'],
                physical_binding_sha256=payload['physical_binding_sha256'],
                probe_request_sha256=probe.digest(payload), envelope={'fixture': 'v2'})
    c = Client()
    runtime, job, lease, adapter, original, physical_payload = _fixture(tmp_path, monkeypatch, c)
    verdict = {'fixture': 'validated-v2'}
    c.foreground = SimpleNamespace(_current_claim=lambda *args: None)
    # Use the real preparation source; its external definition/attestation
    # issuers are explicitly fixtures, as is the existing Runtime physical join.
    from control_plane import foreground_operation
    raw = {'fabric_attended_probe': {'worker_config_path': '/fixture/worker'},
           'control_environment_attestation_path': '/fixture/attestation',
           'proof_base_sha': 'a' * 40}
    attestation = {'config_sha256': 'a' * 64}
    from tests.test_fabric_attended_probe_join import finite_definition
    from control_plane import fabric_attended_assignment
    monkeypatch.setattr(fabric_attended_assignment, 'prepare_assignment', lambda spec, worker, job: (spec, {
        'source_workspace':str(spec.workspace_path), 'input_root':str(spec.run_dir / 'input')}))
    definition = {**finite_definition(), 'worker_user': 'remote-worker', 'worker_uid': physical().worker_uid,
                  'worker_gid': physical().worker_gid}
    adapter._attended_probe_source = probe.AttendedControlProbeSource.from_startup(
        tmp_path / 'control.json', raw, attestation)
    monkeypatch.setattr(probe.sys, 'platform', 'darwin')
    monkeypatch.setattr(control, 'load_control_config', lambda path: raw)
    monkeypatch.setattr(control, '_load_control_environment_attestation', lambda *a, **k: attestation)
    monkeypatch.setattr(probe, 'definition', lambda *a: dict(definition))
    monkeypatch.setattr(probe.AttendedControlProbeSource, 'validate', lambda *a: verdict)
    original_get = runtime.jobs.get_job
    monkeypatch.setattr(runtime.jobs, 'get_job', lambda ident: dataclasses.replace(
        original_get(ident), constraints={**job.constraints, 'attended_route': {'fixture': 'route'}}))
    monkeypatch.setattr(foreground_operation, 'current_foreground_operation', lambda: c.foreground)
    original = dataclasses.replace(original, worker_user='control-worker', shared_run_gid=450,
                                   require_secret_canary=True)
    host = dataclasses.replace(physical(), worker_id=original.worker_id, model=original.model)
    def resolve(spec, *, launch):
        return runtime.attempts.get_attempt(spec.run_id), host, {
            **physical_payload, 'launch_spec': _launch_spec_to_json(spec)}
    monkeypatch.setattr(adapter, '_resolve', resolve)
    requests = []
    request = c.request
    async def capture(op, payload, **kwargs):
        requests.append(payload)
        return await request(op, payload, **kwargs)
    monkeypatch.setattr(c, 'request', capture)
    return c, runtime, lease, adapter, original, requests, definition


def test_remote_principal_is_bound_before_probe_without_changing_control_spec(tmp_path, monkeypatch):
    c, runtime, lease, adapter, original, requests, definition = case(tmp_path, monkeypatch)
    final = asyncio.run(adapter.prepare_attended_launch_spec(original, lease=lease))
    assert final.worker_user == definition['worker_user']
    assert final.shared_run_gid == definition['worker_gid']
    assert requests[0]['launch_spec']['worker_user'] == final.worker_user
    assert requests[0]['launch_spec']['shared_run_gid'] == final.shared_run_gid
    assert dataclasses.replace(final, worker_user=original.worker_user,
        shared_run_gid=original.shared_run_gid, secret_canary_verdict=original.secret_canary_verdict) == original
    assert original.worker_user == 'control-worker' and original.shared_run_gid == 450
    assert not runtime.attempts.get_attempt(original.run_id).launch_metadata
    assert not adapter._bound and not adapter._leases


@pytest.mark.parametrize('username', ['', 'other user', None, True])
def test_invalid_worker_definition_principal_never_reaches_probe(tmp_path, monkeypatch, username):
    c, runtime, lease, adapter, original, requests, definition = case(tmp_path, monkeypatch)
    definition['worker_user'] = username
    with pytest.raises(BrokerStateError):
        asyncio.run(adapter.prepare_attended_launch_spec(original, lease=lease))
    assert not requests and not adapter._bound


def test_changed_worker_name_during_probe_cannot_replace_bound_spec(tmp_path, monkeypatch):
    holder = {}
    c, runtime, lease, adapter, original, requests, definition = case(
        tmp_path, monkeypatch, during=lambda _: holder['definition'].update(worker_user='successor'))
    holder['definition'] = definition
    with pytest.raises(BrokerStateError):
        asyncio.run(adapter.prepare_attended_launch_spec(original, lease=lease))
    assert len(requests) == 1
    assert not adapter._bound and not runtime.attempts.get_attempt(original.run_id).launch_metadata
