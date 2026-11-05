"""Closed ingress and per-request binding; kernel/admission fixtures are explicit."""
import asyncio
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations import product_acceptance_request_host as host_module
from integrations.mastermind_company_mcp import product_acceptance as contract
from tests.test_product_acceptance_request_owner import programme


def frame(job='JOB-fixture'):
    return contract.encode_request(contract.TOOL_NAME,
        {'purpose': 'PRODUCT_ACCEPTANCE', 'subject_job_id': job})


@pytest.mark.parametrize('field,value', [
    ('actor_ref', {}), ('basis_digest', 'a'*64), ('root_job_id', 'JOB-parent'),
    ('macro_root', '/untrusted'), ('decision', 'accept'), ('subject_job_id', '../escape'),
    ('purpose', 'ORDINARY'),
])
def test_selector_rejects_identity_source_and_ruling_inputs(field, value):
    args = {'purpose': 'PRODUCT_ACCEPTANCE', 'subject_job_id': 'JOB-fixture', field: value}
    with pytest.raises(ValueError):
        contract.encode_request(contract.TOOL_NAME, args)


@pytest.mark.parametrize('fault', ['duplicate', 'nan', 'extra', 'multiframe', 'foreign_schema'])
def test_frame_is_closed_before_host_authority(fault):
    raw = frame()
    if fault == 'duplicate': raw = raw.replace(b'"tool":', b'"tool":"request_decision","tool":')
    if fault == 'nan': raw = raw.replace(b'"JOB-fixture"', b'NaN')
    if fault == 'extra': raw = raw.replace(b'"schema":', b'"authenticated":true,"schema":')
    if fault == 'multiframe': raw += frame()
    if fault == 'foreign_schema': raw = raw.replace(contract.REQUEST_SCHEMA.encode(), b'mastermind.native_return_host_request.v1')
    with pytest.raises(ValueError): contract.decode_request(raw)


def test_default_closed_before_any_peer_or_source_access(tmp_path, monkeypatch):
    runtime, owner, *_ = programme(tmp_path, monkeypatch)
    host = host_module.ProductAcceptanceRequestHost(runtime=runtime, reader=owner.reader,
        worker_uid=450, relay_socket_path=Path('/private/tmp/relay.sock'),
        workspace_id='W', channel_id='C')
    def forbidden(**_): pytest.fail('unarmed host must not inspect a caller')
    monkeypatch.setattr(host_module, 'ProductAcceptanceCallerAuthority', forbidden)
    response = contract.validated_response(asyncio.run(host.call(None, frame())))
    assert response['error']['code'] == 'ACCESS_REFUSED'


def test_authentication_requires_distinct_acceptance_grant():
    authority = object.__new__(host_module.ProductAcceptanceCallerAuthority)
    calls = []
    def project(pid, **kwargs):
        calls.append((pid, kwargs))
        raise RuntimeError('fixture: no acceptance grant')
    authority._runtime = SimpleNamespace(current_harness_mcp_binding_for_parent_pid=project)
    with pytest.raises(RuntimeError, match='no acceptance grant'): authority._project(421)
    assert calls == [(421, dict(config_name=contract.CONFIG_NAME,
        server_identity=contract.SERVER_IDENTITY, server_version=contract.SERVER_VERSION,
        tool_schema_digest=contract.TOOL_SCHEMA_DIGEST, auth_status='unsupported'))]
    assert contract.CONFIG_NAME not in {'company-consultation-v1', 'mastermind-native-return'}


@pytest.mark.parametrize('rotate', ['none', 'before_write', 'before_disclosure'])
def test_host_uses_canonical_request_owner_and_closes_request_authority(tmp_path, monkeypatch, rotate):
    runtime, owner, binding, target, basis = programme(tmp_path, monkeypatch)
    host = host_module.ProductAcceptanceRequestHost(runtime=runtime, reader=owner.reader,
        worker_uid=450, relay_socket_path=Path('/private/tmp/relay.sock'),
        workspace_id='W', channel_id='C', armed=True)
    state = {'stage': 'start', 'closed': 0, 'sent': 0}

    class Authority:
        def __init__(self, **_): pass
        def close(self): state['closed'] += 1

    class Binding:
        def __init__(self, *_): pass
        def guard(self):
            if state['stage'] == rotate:
                raise RuntimeError('fixture authority rotated')
        def resolve(self): self.guard(); return binding

    async def service(path, request, *, before_write):
        assert path == host.relay_socket_path
        assert request['operation'] == 'send_message'
        state['stage'] = 'before_write'
        before_write()
        state['sent'] += 1
        state['stage'] = 'before_disclosure'
        return {'ok': True, 'result': {'message_key': request['args']['message']['message_key']}}

    # Only peer/target acquisition and Relay transport are fixtures. prepare()
    # validates actual Runtime/reviewer/source proof and retains one send start.
    monkeypatch.setattr(host_module, 'ProductAcceptanceCallerAuthority', Authority)
    monkeypatch.setattr(host_module, '_RequestBinding', Binding)
    monkeypatch.setattr(host_module, 'call_service', service)
    response = contract.validated_response(asyncio.run(host.call(None, frame(target.job_id))))
    assert state['closed'] == 1
    if rotate == 'none':
        assert response['ok'] is True and state['sent'] == 1
        again = contract.validated_response(asyncio.run(host.call(None, frame(target.job_id))))
        assert again['ok'] is False and state['sent'] == 1
        assert again['data']['message_key'] == response['data']['message_key']
    else:
        assert response['ok'] is False
        assert state['sent'] == (rotate == 'before_disclosure')
        assert response['error']['code'] == ('EFFECT_UNKNOWN' if state['sent'] else 'ACCESS_REFUSED')


def test_request_host_recovers_existing_ruling_without_another_send(tmp_path, monkeypatch):
    from control_plane.coo_principal_host import CooHostProvider
    from tests.test_product_acceptance_ruling_owner import ready, AGGREGATE
    values = ready(tmp_path, monkeypatch)
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = values
    authority = object.__new__(CooHostProvider)
    monkeypatch.setattr(authority, 'guard_dialogue', lambda **_: None)
    closed = []
    class PeerAuthority:
        def __init__(self, **_): pass
        def close(self): closed.append(True)
    class Binding:
        def __init__(self, *_): pass
        def guard(self): pass
        def resolve(self): return binding
    monkeypatch.setattr(host_module, 'ProductAcceptanceCallerAuthority', PeerAuthority)
    monkeypatch.setattr(host_module, '_RequestBinding', Binding)
    monkeypatch.setattr(host_module, 'call_service', relay)
    host = host_module.ProductAcceptanceRequestHost(runtime=runtime, reader=requester.reader,
        worker_uid=450, relay_socket_path=owner.principal_owner.socket_path,
        workspace_id='W', channel_id='C', armed=True, principal_authority=authority)
    response = contract.validated_response(asyncio.run(host.call(None, frame(target.job_id))))
    assert response['ok'] is True, response
    assert response['data']['state'] == 'RULING_QUALIFIED_PARENT_RETURN_PENDING'
    assert len(runtime.events.list_events(aggregate_type=AGGREGATE)) == 1
    assert all(call['operation'] != 'send_message' for call in relay.calls)
    assert closed == [True]
