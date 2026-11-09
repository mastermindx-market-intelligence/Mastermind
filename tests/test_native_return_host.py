"""Distinct native facet, fail-closed registration, and authenticated host composition."""
import asyncio
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from common.company_consultation_host_contract import encode_json_frame, MAX_REQUEST_BYTES
from integrations.company_consultation_host import CompanyConsultationHost
from integrations.session_bridge.schemas import BridgeError
from tests.test_company_consultation_host_authorization import connected

ARGS = dict(operation_key='original-operation', in_reply_to='asd-request', text='Finding', next_step='Return')


def native():
    from integrations.mastermind_company_mcp import native_return
    return native_return


def host(connected, tmp_path, **kwargs):
    args = connected['args']
    return CompanyConsultationHost(runtime=args['runtime'], repository_root=tmp_path,
        worker_uid=args['worker_uid'], inspector=args['inspector'],
        relay_socket_path=Path('/private/tmp/not-a-live-relay.sock'),
        workspace_id='T1234567890', channel_id='C1234567890', **kwargs)


def test_native_facet_is_not_consultation_grant():
    from integrations.mastermind_company_mcp import consultation
    n = native()
    assert n.SERVER_IDENTITY != consultation.COMPANY_CONSULTATION_SERVER_IDENTITY
    assert n.TOOL_SCHEMA_DIGEST != consultation.COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST
    assert n.TOOL_NAME == 'native.reply'
    assert n.validate_arguments(ARGS) == ARGS


@pytest.mark.parametrize('extra', ['native_session_id', 'binding_id', 'process_generation_id',
                                   'parent', 'worker_uid', 'channel_id', 'grant'])
def test_model_cannot_supply_authority(extra):
    with pytest.raises(BridgeError):
        native().validate_arguments(ARGS | {extra: 'forged'})


def test_native_frame_uses_separate_versioned_schema():
    n = native()
    frame = json.loads(n.encode_request(n.TOOL_NAME, ARGS))
    from common.company_consultation_host_contract import HOST_REQUEST_SCHEMA
    assert frame['schema'] != HOST_REQUEST_SCHEMA
    assert frame['arguments'] == ARGS


def test_host_default_refuses_native_before_any_authority_lookup(connected, tmp_path):
    n = native()
    h = host(connected, tmp_path)
    result = json.loads(asyncio.run(h.call(connected['args']['peer'], n.encode_request(n.TOOL_NAME, ARGS))))
    assert result['error']['code'] == 'ACCESS_REFUSED'
    assert not connected['calls']


def test_host_enabled_still_refuses_consultation_only_capability(connected, tmp_path):
    n = native()
    h = host(connected, tmp_path, native_return_armed=True)
    result = json.loads(asyncio.run(h.call(connected['args']['peer'], n.encode_request(n.TOOL_NAME, ARGS))))
    assert result['error']['code'] == 'ACCESS_REFUSED'


def test_native_authority_binds_separate_grant_and_transaction(connected):
    from integrations.native_reply_host import NativeReturnCallerAuthority
    from control_plane.operator_harness_contract import CapabilityIdentity, ObservedCapabilityIdentity
    n = native()
    cap = replace(connected['facts'].requested_capability, name=n.CONFIG_NAME,
        mcp_server_identity=n.SERVER_IDENTITY, mcp_server_version=n.SERVER_VERSION,
        tool_schema_digest=n.TOOL_SCHEMA_DIGEST)
    raw = asdict(cap)
    raw.pop('harness_binary_digest')
    connected['facts'] = replace(connected['facts'], requested_capability=cap,
                                observed_capability=ObservedCapabilityIdentity(**raw))
    authority = NativeReturnCallerAuthority(**connected['args'])
    with connected['args']['runtime'].store.transaction() as conn:
        assert authority.revalidate(connection=conn) == connected['facts']
        assert connected['calls'][-1][1]['connection'] is conn
        assert connected['calls'][-1][1]['config_name'] == n.CONFIG_NAME
    authority.close()
    with pytest.raises(Exception):
        authority.revalidate()


def test_native_profile_is_separate_and_source_eligible_without_production_arm():
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles['operator.appserver.interactive.native-return.v1']
    assert profile.enabled and not registry.production_armed
    assert profile.mcp_servers == ('native-return-mcp-v1',)
    assert profile.skills == profile.plugins == profile.resource_grants == ()
    grant = profile.mcp_server_grants[0]
    n = native()
    assert (grant.config_name, grant.server_identity, grant.server_version, grant.tool_schema_digest) == (
        n.CONFIG_NAME,n.SERVER_IDENTITY,n.SERVER_VERSION,n.TOOL_SCHEMA_DIGEST)
    assert grant.enabled_tools == (n.TOOL_NAME,) and grant.required
    assert 'native-stdio' in grant.args[-1]
    assert observed_mcp_tool_schema_digest({'tools': {n.TOOL_NAME: {
        'name': n.TOOL_NAME, 'inputSchema': n.INPUT_SCHEMA, 'annotations': n.ANNOTATIONS}}}) == n.TOOL_SCHEMA_DIGEST
    company = registry.profiles['operator.appserver.interactive.company-mcp.v1']
    assert company.mcp_servers == ('company-consultation-mcp-v1',)
    assert company.expected_config_digest != profile.expected_config_digest


@pytest.mark.parametrize('field,value', [
    ('command','/tmp/foreign'), ('args',['-c','pass']), ('config_name','company-consultation-v1'),
    ('server_identity','foreign'), ('server_version','2.0.0'), ('enabled_tools',['company.reply']),
    ('tool_schema_digest','0'*64), ('auth_status','bearerToken'), ('default_tools_approval_mode','prompt'),
])
def test_native_grant_is_frozen(tmp_path, field, value):
    from control_plane.executive_agent_capabilities import CapabilityPolicyError, ExecutionCapabilityRegistry
    raw = json.loads((Path(__file__).parents[1]/'config/executive_agent_capabilities.json').read_text())
    raw['mcp_servers']['native-return-mcp-v1'][field] = value
    path = tmp_path/'policy.json'
    path.write_text(json.dumps(raw))
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path)
