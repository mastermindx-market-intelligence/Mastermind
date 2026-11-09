import asyncio
import os
import tempfile
from pathlib import Path
import pytest
from control_plane.executive_worker_broker import WorkerBrokerClient, PeerAuthorizationError


def test_wrong_service_uid_receives_no_request(tmp_path):
    directory = tempfile.TemporaryDirectory(prefix='fb-', dir='/tmp')
    path = str(Path(directory.name) / 's')
    received = []
    async def run():
        done = asyncio.Event()
        async def handler(reader, writer):
            received.append(await reader.read())
            writer.close()
            await writer.wait_closed()
            done.set()
        server = await asyncio.start_unix_server(handler, path)
        async with server:
            with pytest.raises(PeerAuthorizationError):
                await WorkerBrokerClient(path, expected_peer_uid=os.geteuid()+1).request('status', {'run_id':'private-attempt'})
            await asyncio.wait_for(done.wait(), 2)
    asyncio.run(run())
    assert received == [b'']


@pytest.mark.parametrize('uid',[True,-1,'501'])
def test_peer_uid_is_exact_integer(uid):
    with pytest.raises(ValueError):
        WorkerBrokerClient('/var/run/mastermind/fabric.sock', expected_peer_uid=uid)
