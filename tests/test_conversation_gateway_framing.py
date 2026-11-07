"""Actual fixed private client parser; no Control/provider/effect invocation."""
import asyncio
import copy
import tempfile
import pytest
from tests.test_fresh_conversation_http import mounted, post, rsa_key
from tests.test_fresh_conversation import cleanup
from integrations.mastermind_executive_app.gateway import CeoIngressClient, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN

@pytest.mark.parametrize("raw,expected",[
    (b'{"ok":true,"result":{},"ok":true}\n',TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{},"extra":true}\n',TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{"nonfinite":NaN}}\n',TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{}}\n',TRANSPORT_SENT_OK),
])
def test_fresh_private_socket_rejects_noncanonical_response_before_mapping(tmp_path,rsa_key,monkeypatch,raw,expected):
    async def run():
        app,token,workspace,service,runtime,request,_,calls,_=await mounted(tmp_path,rsa_key,monkeypatch)
        try:
            code,preview=await post(app,"preview",request,token,workspace)
            assert code==200 and preview["ok"]
            frame=copy.deepcopy(calls[-1]);frame["operation"]="status";frame["workspace_principal"]=None
            frame["arguments"]={k:request[k] for k in ("work_ref","operation_key")}
            before=runtime.events.list_events()
            with tempfile.TemporaryDirectory(prefix="fresh-frame-",dir="/tmp") as directory:
                async def respond(reader,writer):
                    try:
                        await reader.readline();writer.write(raw);await writer.drain()
                    finally:
                        writer.close();await writer.wait_closed()
                path=directory+"/s";server=await asyncio.start_unix_server(respond,path=path)
                try:
                    result=await CeoIngressClient().send_frame(path,frame)
                    assert result.transport==expected
                finally:
                    server.close();await server.wait_closed()
            assert runtime.events.list_events()==before
        finally:
            await cleanup(service)
    asyncio.run(run())
