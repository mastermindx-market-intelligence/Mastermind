"""Receiver must reject raw invalid bytes before constructing a READ owner."""
import asyncio
import dataclasses
import json
import tempfile
from pathlib import Path
import pytest
from common import project_conversation_read_contract as wire
from tests.test_fresh_conversation import case, cleanup

@pytest.mark.parametrize('damage',['duplicate','oversize'])
def test_actual_private_socket_refuses_raw_frame_before_provider(tmp_path, damage):
    async def run():
        service,runtime,_,principal,_,_=case(tmp_path)
        calls=[]
        def forbidden(selected):
            calls.append(selected)
            raise ValueError('must not construct provider for malformed bytes')
        service._ceo_ingress_app_binding=dataclasses.replace(service._ceo_ingress_app_binding,
            project_conversation_read_provider_factory=forbidden)
        projection=dataclasses.asdict(principal);projection['scopes']=list(projection['scopes'])
        frame=wire.frame({'schema':wire.SCHEMA,'operation':'catalogue',
            'principal':projection,'arguments':{'work_ref':'WS:ONE'}})
        packet=wire.encode_frame(frame)
        if damage=='duplicate':
            packet=packet[:-2]+b',"arguments":{"work_ref":"WS:ONE"}}\n'
        else:
            packet=b' '*wire.MAX_REQUEST_BYTES+packet
        before=runtime.events.list_events()
        try:
            with tempfile.TemporaryDirectory(prefix='project-read-raw-',dir='/tmp') as directory:
                path=Path(directory)/'s'
                server=await asyncio.start_unix_server(service._handle_ceo_ingress_connection,path=path)
                try:
                    reader,writer=await asyncio.open_unix_connection(str(path))
                    writer.write(packet);await writer.drain();writer.write_eof()
                    result=json.loads(await asyncio.wait_for(reader.readline(),5))
                    assert result['ok'] is False
                    writer.close();await writer.wait_closed()
                finally:
                    server.close();await server.wait_closed()
            assert calls==[]
            assert runtime.events.list_events()==before
        finally:
            await cleanup(service)
            if service._ceo_ingress_tasks:
                await asyncio.wait_for(asyncio.gather(*service._ceo_ingress_tasks),5)
    asyncio.run(run())
