"""Actual Runtime target projection and inherited peer guard; OS observations are fixtures."""
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from control_plane.agentos_product_acceptance_basis import AgentOsProductAcceptanceBasisReader
from control_plane.operator_harness_contract import ObservedCapabilityIdentity
from integrations.product_acceptance_request_host import (
    ProductAcceptanceCallerAuthority, ProductAcceptanceRequestHost, _RequestBinding,
)
from integrations.mastermind_company_mcp import product_acceptance as contract
from tests.test_company_consultation_host_authorization import connected
from tests.test_native_continuation_ack_ingress import native_case


def acceptance_facts(connected):
    cap=replace(connected['facts'].requested_capability,name=contract.CONFIG_NAME,
        mcp_server_identity=contract.SERVER_IDENTITY,mcp_server_version=contract.SERVER_VERSION,
        tool_schema_digest=contract.TOOL_SCHEMA_DIGEST)
    raw=asdict(cap);raw.pop('harness_binary_digest')
    connected['facts']=replace(connected['facts'],requested_capability=cap,
        observed_capability=ObservedCapabilityIdentity(**raw))


def test_inherited_kernel_lineage_guard_binds_distinct_acceptance_grant(connected):
    acceptance_facts(connected)
    authority=ProductAcceptanceCallerAuthority(**connected['args'])
    assert authority.revalidate()==connected['facts']
    assert all(call[1]['config_name']==contract.CONFIG_NAME for call in connected['calls'])
    connected['facts']=replace(connected['facts'],observed_attestation_digest='d'*64)
    with pytest.raises(Exception,match='authority changed'):authority.revalidate()
    authority.close()


@pytest.mark.parametrize('bad_side',['requested_capability','observed_capability'])
def test_authentication_refuses_either_half_of_a_borrowed_grant(connected,bad_side):
    acceptance_facts(connected)
    connected['facts']=replace(connected['facts'],**{bad_side:replace(
        getattr(connected['facts'],bad_side),name='mastermind-native-return')})
    with pytest.raises(Exception,match='capability differs'):
        ProductAcceptanceCallerAuthority(**connected['args'])


@pytest.mark.parametrize('fault',['none','foreign_workspace','foreign_channel','rotated_generation'])
def test_request_binding_projects_actual_current_runtime_target(native_case,tmp_path,fault):
    f=native_case.f
    facts=SimpleNamespace(binding=f.runtime.current_harness_binding_source(f.sealed.attempt_id))
    state={'facts':facts}
    authority=SimpleNamespace(revalidate=lambda:state['facts'])
    host=ProductAcceptanceRequestHost(runtime=f.runtime,reader=AgentOsProductAcceptanceBasisReader(macro_root=tmp_path),
        worker_uid=451,relay_socket_path=Path('/private/tmp/relay.sock'),
        workspace_id='T1BRD2AQXQV' if fault=='foreign_workspace' else 'T0BRD2AQXQV',
        channel_id='C1BSBM78V1N' if fault=='foreign_channel' else 'C0BSBM78V1N',armed=True)
    before=f.runtime.events.list_events()
    if fault.startswith('foreign'):
        with pytest.raises(Exception,match='outside installed scope'):_RequestBinding(host,authority)
    else:
        binding=_RequestBinding(host,authority)
        resolved=binding.resolve()
        assert resolved.applies_to['attempt_id']==f.sealed.attempt_id
        assert resolved.allowed_message_types==('DECISION_REQUEST',)
        if fault=='rotated_generation':
            state['facts']=SimpleNamespace(binding=replace(facts.binding,generation_number=facts.binding.generation_number+1))
            with pytest.raises(Exception,match='changed'):binding.resolve()
        else:
            assert binding.resolve()==resolved
    assert f.runtime.events.list_events()==before
