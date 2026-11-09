"""Replaying a body is not evidence that the real HTTP caller disconnected."""
import asyncio
from integrations.mastermind_executive_app.os_transport import _drive_inner


def test_replayed_request_does_not_fabricate_disconnect_before_inner_response():
    async def exercise():
        async def inner(scope,receive,send):
            body=await receive()
            assert body=={'type':'http.request','body':b'{"arguments":{}}','more_body':False}
            observed=asyncio.create_task(receive())
            await asyncio.sleep(0)
            try:
                assert not observed.done(), 'nested transport fabricated a live caller disconnect'
                await send({'type':'http.response.start','status':200,'headers':[]})
                await send({'type':'http.response.body','body':b'{"ok":true}','more_body':False})
            finally:
                observed.cancel();await asyncio.gather(observed,return_exceptions=True)
        start,body=await _drive_inner(inner,{'type':'http'},b'{"arguments":{}}')
        assert start['status']==200 and body==b'{"ok":true}'
    asyncio.run(exercise())
