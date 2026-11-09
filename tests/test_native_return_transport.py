"""Native stdio advertisement and single-request authenticated socket contract."""
import asyncio
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.company_consultation_host_contract import HostFrameError, encode_json_frame
from integrations import company_consultation_host_transport as transport
from integrations.mastermind_company_mcp import native_return as n
from tests.test_native_return_host import ARGS

RECEIPT = dict(reply_committed=True, action='POSTED', message_key='asd-native-reply-'+'a'*40,
    fingerprint='b'*64, thread_ts='1791660000.000001',in_reply_to=ARGS['in_reply_to'],parent_consumed=False)


@pytest.mark.parametrize('change', [dict(parent_consumed=True), dict(reply_committed=False),
    dict(action='PENDING'), dict(extra='unbounded'), dict(fingerprint='bad'), dict(thread_ts='bad')])
def test_success_receipt_is_closed_and_never_claims_consumption(change):
    with pytest.raises(HostFrameError):
        n.validated_response(encode_json_frame(n.envelope(data=RECEIPT|change),limit=65536))


@pytest.mark.parametrize('mode', ['success','wrong-peer','lost','malformed','extra-frame'])
def test_native_unix_contract_one_request_no_retry(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(transport,'capture_peer_identity',lambda sock:SimpleNamespace(euid=os.getuid()))
    monkeypatch.setattr(transport,'_current_capture',lambda peer:None)
    async def run():
        frames=[]
        done=asyncio.Event()
        async def handle(reader,writer):
            try:
                frames.append(await reader.readline())
                if frames[-1] and mode!='lost':
                    raw=(b'{}\n' if mode=='malformed' else encode_json_frame(n.envelope(data=RECEIPT),limit=65536))
                    writer.write(raw+(b'{}\n' if mode=='extra-frame' else b''))
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                done.set()
        path=str(tmp_path/'native.sock')
        server=await asyncio.start_unix_server(handle,path)
        try:
            gateway=transport.UnixNativeReturnGateway(socket_path=path,server_uid=os.getuid()+(mode=='wrong-peer'))
            result=await gateway.call(n.TOOL_NAME,ARGS)
            await asyncio.wait_for(done.wait(),2)
            if mode=='wrong-peer':
                assert result['error']['code']=='ACCESS_REFUSED' and frames==[b'']
            else:
                assert len(frames)==1 and n.decode_request(frames[0])==(n.TOOL_NAME,ARGS)
                if mode=='success':
                    assert result==n.envelope(data=RECEIPT)
                else:
                    assert result['error']['code']=='EFFECT_UNKNOWN'
        finally:
            server.close(); await server.wait_closed()
    asyncio.run(run())


def test_sdk_advertises_exact_native_tool_and_no_other_capability():
    pytest.importorskip("mcp")
    import mcp.types as types
    from mcp.server.lowlevel import NotificationOptions
    from integrations.mastermind_company_mcp.server import build_native_return_mcp_server
    from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
    server=build_native_return_mcp_server(SimpleNamespace())
    assert server.name==n.SERVER_IDENTITY and server.version==n.SERVER_VERSION
    caps=server.get_capabilities(notification_options=NotificationOptions(),experimental_capabilities={})
    assert caps.tools is not None and caps.resources is caps.prompts is None
    result=asyncio.run(server.request_handlers[types.ListToolsRequest](types.ListToolsRequest(method='tools/list')))
    tools=result.root.tools
    assert [tool.name for tool in tools]==[n.TOOL_NAME]
    row=tools[0].model_dump(by_alias=True,exclude_none=True)
    assert observed_mcp_tool_schema_digest({'tools':{n.TOOL_NAME:row}})==n.TOOL_SCHEMA_DIGEST


@pytest.mark.parametrize('value', [None,1,'true',[],{}])
def test_native_arm_requires_explicit_boolean(value):
    from scripts.executive_os_phase1c import company_consultation_launchd_entry,ServiceError
    config=dict(company_consultation=dict(armed=False,native_return_armed=value,
        socket_path='/var/run/mastermind-executive/company-consultation.sock',launchd_socket_name='CompanyConsultation'))
    with pytest.raises(ServiceError):
        company_consultation_launchd_entry(config)
