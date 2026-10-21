"""Distinct SDK/Unix/Control selection; installed identities remain explicit fixtures."""
import asyncio
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from integrations import company_consultation_host_transport as transport
from integrations.mastermind_company_mcp import product_acceptance as contract
from tests.test_product_acceptance_host_selection import configured

ARGS = {'purpose': 'PRODUCT_ACCEPTANCE', 'subject_job_id': 'JOB-fixture'}


def test_sdk_advertises_only_the_closed_selector():
    import mcp.types as types
    from mcp.server.lowlevel import NotificationOptions
    from integrations.mastermind_company_mcp.server import build_product_acceptance_mcp_server
    from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
    server = build_product_acceptance_mcp_server(SimpleNamespace())
    assert (server.name, server.version) == (contract.SERVER_IDENTITY, contract.SERVER_VERSION)
    caps = server.get_capabilities(notification_options=NotificationOptions(),experimental_capabilities={})
    assert caps.tools is not None and caps.resources is caps.prompts is None
    result = asyncio.run(server.request_handlers[types.ListToolsRequest](types.ListToolsRequest(method='tools/list')))
    assert [t.name for t in result.root.tools] == [contract.TOOL_NAME]
    row = result.root.tools[0].model_dump(by_alias=True,exclude_none=True)
    assert observed_mcp_tool_schema_digest({'tools':{contract.TOOL_NAME:row}}) == contract.TOOL_SCHEMA_DIGEST
    assert row['inputSchema'] == contract.INPUT_SCHEMA


@pytest.mark.parametrize('mode', ['success','wrong_peer','lost','extra_frame','foreign_identity'])
def test_unix_facet_retains_peer_proof_single_send_and_unknown_effect(short_socket_root, monkeypatch, mode):
    monkeypatch.setattr(transport, 'capture_peer_identity', lambda sock: SimpleNamespace(euid=os.getuid()))
    monkeypatch.setattr(transport, '_current_capture', lambda peer: None)
    async def run():
        frames, done = [], asyncio.Event()
        expected = contract.envelope(data={'state':'DECISION_REQUEST_SENT','message_key':'retained-fixture'})
        async def handle(reader, writer):
            try:
                frames.append(await reader.readline())
                if frames[-1] and mode != 'lost':
                    response = copy.deepcopy(expected)
                    if mode == 'foreign_identity': response['server_identity'] = 'company-consultation-v1'
                    writer.write((json.dumps(response)+'\n').encode()+(b'{}\n' if mode=='extra_frame' else b''))
                    await writer.drain()
            finally:
                writer.close(); await writer.wait_closed(); done.set()
        socket = str(short_socket_root/'accept.sock')
        server = await asyncio.start_unix_server(handle, socket)
        try:
            gateway = transport.UnixProductAcceptanceGateway(socket_path=socket, server_uid=os.getuid()+(mode=='wrong_peer'))
            response = await gateway.call(contract.TOOL_NAME, ARGS)
            await asyncio.wait_for(done.wait(),2)
            if mode=='wrong_peer': assert frames==[b''] and response['error']['code']=='ACCESS_REFUSED'
            else:
                assert len(frames)==1 and contract.decode_request(frames[0])==(contract.TOOL_NAME,ARGS)
                if mode=='success': assert response==expected
                else: assert response['error']['code']=='EFFECT_UNKNOWN'
        finally: server.close(); await server.wait_closed()
    asyncio.run(run())


def selection(armed=True):
    return dict(armed=armed, socket_path='/var/run/mastermind-executive/company-consultation.sock',
                launchd_socket_name='CompanyConsultation')


@pytest.mark.parametrize('value', [None,1,'true',[],{}])
def test_selection_arm_is_boolean(value):
    from scripts import executive_os_phase1c as cli
    with pytest.raises(cli.ServiceError):
        cli.company_consultation_launchd_entry({'company_consultation':selection(False)|{'product_acceptance_armed':value}})


@pytest.mark.parametrize('company,principal', [(False,False),(True,False),(False,True)])
def test_acceptance_selection_requires_both_existing_owners(company, principal):
    from scripts import executive_os_phase1c as cli
    with pytest.raises(cli.ServiceError):
        cli.company_consultation_launchd_entry(dict(company_consultation=selection(company)|{'product_acceptance_armed':True},
            coo_principal_dialogue_armed=principal, control_uid=450, worker_uid=451,worker_gid=451))


@pytest.mark.parametrize('selected', [False,True])
def test_actual_control_factory_selects_same_runtime_and_sealed_context(tmp_path, monkeypatch, selected):
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_worker_broker
    from control_plane.executive_runtime import Runtime
    from integrations.company_consultation_host import CompanyConsultationHost
    from integrations.product_acceptance_request_host import ProductAcceptanceRequestHost
    raw, options, fake_sockets = configured(tmp_path, monkeypatch, True)
    prior = cli.activate_launchd_socket
    try:
        Path(raw['proof_source_repository']).mkdir(parents=True,exist_ok=True)
        raw['company_consultation'] = selection()|({'product_acceptance_armed':True} if selected else {})
        captured = {}
        import socket
        # Launchd activation is a fixture; no production listener is opened. The Control Room name gets the fixture's AF_UNIX listener.
        def activated(name):
            if name == 'CompanyConsultation':
                return SimpleNamespace(family=socket.AF_UNIX,
                    getsockname=lambda: raw['company_consultation']['socket_path'], getsockopt=lambda *args: 1)
            return prior(name)
        monkeypatch.setattr(cli, 'activate_launchd_socket', activated)
        monkeypatch.setattr(executive_worker_broker,'WorkerBrokerClient',lambda *a,**kw: object())
        def service(config, **bindings):
            captured.update(bindings)
            return SimpleNamespace(config=config)
        monkeypatch.setattr(cli,'ExecutiveControlService',service)
        instance = cli._service_from_config(raw, **options)
        runtime = Runtime.at(tmp_path/'bound-runtime')
        calls = []
        def bind(actual): assert actual is runtime; calls.append(actual); return actual
        instance._namespace_custody = SimpleNamespace(bound_runtime=bind)
        owner = captured['company_consultation_binding'].host_factory(runtime)
        assert type(owner) is CompanyConsultationHost and owner.runtime is runtime
        assert owner.native_return_armed is False
        if not selected:
            assert owner.product_acceptance_host is None and calls==[]
            return
        request = owner.product_acceptance_host
        assert type(request) is ProductAcceptanceRequestHost
        assert request.runtime is request.principal_authority.workspace.runtime is runtime
        assert request.reader._installed_context_owner._source_root == raw['proof_source_repository']
        assert request.reader._installed_context_owner._macro_root == raw['ceo_ingress_app_macro_root']
        assert request.relay_socket_path == owner.relay_socket_path == cli._CANONICAL_AGENT_RELAY_SOCKET
        assert request.armed is True and calls==[runtime]
        # No caller frame selected a Runtime, Context source or principal.
        assert instance.config.coo_autonomy_armed is False
    finally:
        for listener in fake_sockets.values():
            listener.close()


def test_company_socket_refuses_acceptance_by_default_before_peer_access(tmp_path, monkeypatch):
    from control_plane.executive_runtime import Runtime
    from integrations.company_consultation_host import CompanyConsultationHost
    owner=CompanyConsultationHost(runtime=Runtime.at(tmp_path/'runtime'),repository_root=tmp_path,
        worker_uid=451,relay_socket_path=Path('/private/tmp/relay.sock'),workspace_id='T0BRD2AQXQV',channel_id='C0BSBM78V1N')
    result=contract.validated_response(asyncio.run(owner.call(None,contract.encode_request(contract.TOOL_NAME,ARGS))))
    assert result['error']['code']=='ACCESS_REFUSED'


def test_grant_is_distinct_and_incumbent_profiles_keep_their_identity():
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    registry=ExecutionCapabilityRegistry.load()
    profile=registry.profiles['operator.appserver.interactive.product-acceptance.v1']
    assert profile.enabled and registry.production_armed is False
    assert profile.mcp_servers==('product-acceptance-mcp-v1',)
    assert profile.skills==profile.plugins==profile.resource_grants==()
    grant=profile.mcp_server_grants[0]
    assert (grant.config_name,grant.server_identity,grant.server_version,grant.tool_schema_digest)==(
        contract.CONFIG_NAME,contract.SERVER_IDENTITY,contract.SERVER_VERSION,contract.TOOL_SCHEMA_DIGEST)
    assert grant.enabled_tools==(contract.TOOL_NAME,) and grant.required
    assert 'acceptance-stdio' in grant.args[-1]
    for name,cap in [('company-mcp','company-consultation-mcp-v1'),('native-return','native-return-mcp-v1')]:
        incumbent=registry.profiles[f'operator.appserver.interactive.{name}.v1']
        assert incumbent.mcp_servers==(cap,)
        assert incumbent.expected_config_digest != profile.expected_config_digest


@pytest.mark.parametrize('field,value', [
    ('command','/tmp/foreign'),('args',['-c','pass']),('config_name','mastermind-native-return'),
    ('server_identity','foreign'),('server_version','2.0.0'),('enabled_tools',['native.reply']),
    ('tool_schema_digest','0'*64),('auth_status','bearerToken'),('default_tools_approval_mode','prompt'),
])
def test_acceptance_grant_cannot_borrow_other_facets(tmp_path, field, value):
    from control_plane.executive_agent_capabilities import CapabilityPolicyError,ExecutionCapabilityRegistry
    raw=json.loads((Path(__file__).parents[1]/'config/executive_agent_capabilities.json').read_text())
    raw['mcp_servers']['product-acceptance-mcp-v1'][field]=value
    path=tmp_path/'policy.json';path.write_text(json.dumps(raw))
    with pytest.raises(CapabilityPolicyError):ExecutionCapabilityRegistry.load(path)


def test_real_socket_dispatches_one_canonical_request_and_never_resends(tmp_path, short_socket_root, monkeypatch):
    from integrations import company_consultation_host as host_module
    from integrations import product_acceptance_request_host as request_module
    from tests.test_product_acceptance_request_owner import programme, AGGREGATE
    runtime, requester, binding, target, basis = programme(tmp_path/'runtime',monkeypatch)
    closed, sent = [], []
    class Authority:
        def __init__(self, **kwargs): pass
        def close(self): closed.append(True)
    class Binding:
        def __init__(self,*args): pass
        def guard(self): pass
        def resolve(self): return binding
    async def relay(path, request, *, before_write):
        before_write();sent.append(request)
        return {'ok':True,'result':{'message_key':request['args']['message']['message_key']}}
    monkeypatch.setattr(request_module,'ProductAcceptanceCallerAuthority',Authority)
    monkeypatch.setattr(request_module,'_RequestBinding',Binding)
    monkeypatch.setattr(request_module,'call_service',relay)
    monkeypatch.setattr(host_module,'capture_peer_identity',lambda sock: SimpleNamespace(euid=os.getuid()))
    monkeypatch.setattr(transport,'capture_peer_identity',lambda sock: SimpleNamespace(euid=os.getuid()))
    monkeypatch.setattr(transport,'_current_capture',lambda peer: None)
    selected=request_module.ProductAcceptanceRequestHost(runtime=runtime,reader=requester.reader,
        worker_uid=os.getuid(),relay_socket_path=Path('/private/tmp/relay.sock'),
        workspace_id='T0BRD2AQXQV',channel_id='C0BSBM78V1N',armed=True)
    host=host_module.CompanyConsultationHost(runtime=runtime,repository_root=tmp_path,
        worker_uid=os.getuid(),relay_socket_path=selected.relay_socket_path,
        workspace_id=selected.workspace_id,channel_id=selected.channel_id,product_acceptance_host=selected)
    async def run():
        socket=str(short_socket_root/'product.sock')
        server=await asyncio.start_unix_server(host.handle_connection,socket)
        try:
            gateway=transport.UnixProductAcceptanceGateway(socket_path=socket,server_uid=os.getuid())
            args=ARGS|{'subject_job_id':target.job_id}
            first=await gateway.call(contract.TOOL_NAME,args)
            second=await gateway.call(contract.TOOL_NAME,args)
            assert first['ok'] is True,first
            assert second['ok'] is False,second
            assert first['data']['message_key']==second['data']['message_key']
        finally: server.close();await server.wait_closed()
    asyncio.run(run())
    assert len(sent)==1 and len(closed)==2
    assert len(runtime.events.list_events(aggregate_type=AGGREGATE))==1


@pytest.mark.parametrize('field', ['runtime','worker_uid','relay_socket_path','workspace_id','channel_id'])
def test_host_rejects_mismatched_acceptance_composition(tmp_path, monkeypatch, field):
    from integrations.company_consultation_host import CompanyConsultationHost
    from integrations.product_acceptance_request_host import ProductAcceptanceRequestHost
    from tests.test_product_acceptance_request_owner import programme
    from control_plane.executive_runtime import Runtime
    runtime, requester, *_=programme(tmp_path/'runtime',monkeypatch)
    args=dict(runtime=runtime,worker_uid=451,relay_socket_path=Path('/private/tmp/relay.sock'),
        workspace_id='T0BRD2AQXQV',channel_id='C0BSBM78V1N')
    changed=args|{field:dict(runtime=Runtime.at(tmp_path/'foreign'),worker_uid=452,
        relay_socket_path=Path('/private/tmp/other.sock'),workspace_id='T1BRD2AQXQV',channel_id='C1BSBM78V1N')[field]}
    selected=ProductAcceptanceRequestHost(**changed,reader=requester.reader)
    with pytest.raises(TypeError,match='exact Company host binding'):
        CompanyConsultationHost(**args,repository_root=tmp_path,product_acceptance_host=selected)
