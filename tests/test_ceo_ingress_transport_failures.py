"""Causal transport-failure regressions; no installed socket or provider access."""
import asyncio
import tempfile
from pathlib import Path

import pytest
from integrations.mastermind_executive_app import gateway


@pytest.mark.skipif(not hasattr(asyncio, "start_unix_server"), reason="Unix sockets unavailable")
def test_real_unix_oversized_line_returns_unknown_not_value_error():
    async def exercise():
        seen = []
        handlers = set()
        async def peer(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                seen.append(await reader.readline())
                writer.write(b"x" * (gateway._STREAM_LIMIT + 1) + b"\n")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                handlers.discard(task)
        with tempfile.TemporaryDirectory(prefix="mmx-ingress-", dir="/tmp") as root:
            socket = str(Path(root) / "peer.sock")
            server = await asyncio.start_unix_server(peer, path=socket)
            try:
                result = await gateway.CeoIngressClient(connect_timeout=.2, read_timeout=.2).send_frame(
                    socket, {"schema": "test-only-frame"})
                assert result.transport == gateway.TRANSPORT_SENT_UNKNOWN
                assert result.detail == "response exceeded byte ceiling"
                assert len(seen) == 1
            finally:
                server.close()
                await server.wait_closed()
                if handlers:
                    await asyncio.wait_for(asyncio.gather(*handlers), .5)
    asyncio.run(exercise())


class Writer:
    def __init__(self, close_error=None, stall=False, abort_error=False):
        self.writes = []
        self.close_count = self.abort_count = 0
        self.close_error = close_error
        self.stall = stall
        self.abort_error = abort_error
        self.transport = self
        self.wait_settled = False
        self.written = asyncio.Event()
        self.read_started = asyncio.Event()
        self.wait_started = asyncio.Event()
    def write(self, data):
        self.writes.append(data)
        self.written.set()
    async def drain(self):
        pass
    def write_eof(self):
        pass
    def close(self):
        self.close_count += 1
        if self.close_error:
            raise self.close_error
    async def wait_closed(self):
        self.wait_started.set()
        try:
            if self.stall:
                await asyncio.Event().wait()
        finally:
            self.wait_settled = True
    def abort(self):
        self.abort_count += 1
        if self.abort_error:
            raise OSError("synthetic abort failure")


def connection(monkeypatch, writer, payload):
    class ObservedReader(asyncio.StreamReader):
        async def readline(self):
            writer.read_started.set()
            return await super().readline()
    async def open_connection(*args, **kwargs):
        reader = ObservedReader()
        if payload is not None:
            reader.feed_data(payload)
            reader.feed_eof()
        return reader, writer
    monkeypatch.setattr(gateway.asyncio, "open_unix_connection", open_connection)


@pytest.mark.parametrize("payload,transport", [
    (b'{"ok":true,"result":{"request_ref":"same-request"}}\n', gateway.TRANSPORT_SENT_OK),
    (b'{"ok":false,"error":{"code":"authority_refused"}}\n', gateway.TRANSPORT_SENT_OK),
    (b'not-json\n', gateway.TRANSPORT_SENT_UNKNOWN),
    (None, gateway.TRANSPORT_SENT_UNKNOWN),
])
def test_stalled_close_is_bounded_preserves_classification(monkeypatch, payload, transport):
    async def exercise():
        writer = Writer(stall=True)
        connection(monkeypatch, writer, payload)
        client = gateway.CeoIngressClient(connect_timeout=.025, read_timeout=.025)
        result = await asyncio.wait_for(client.send_frame("/synthetic-only", {"schema":"fixture"}), .25)
        assert result.transport == transport
        assert len(writer.writes) == writer.close_count == writer.abort_count == 1
        assert writer.wait_settled
        if result.ok is True:
            assert result.result == {"request_ref":"same-request"}
        if result.ok is False:
            assert result.error == {"code":"authority_refused"}
    asyncio.run(exercise())


@pytest.mark.parametrize("abort_error", [False, True])
def test_close_error_does_not_mask_known_receipt(monkeypatch, abort_error):
    async def exercise():
        writer = Writer(close_error=OSError("synthetic close failure"), abort_error=abort_error)
        connection(monkeypatch, writer, b'{"ok":true,"result":{"request_ref":"same-request"}}\n')
        result = await gateway.CeoIngressClient(connect_timeout=.025, read_timeout=.025).send_frame(
            "/synthetic-only", {"schema":"fixture"})
        assert result.transport == gateway.TRANSPORT_SENT_OK
        assert result.result == {"request_ref":"same-request"}
        assert len(writer.writes) == writer.close_count == writer.abort_count == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("during_close", [False, True])
def test_caller_cancellation_propagates_with_one_send_and_settled_cleanup(monkeypatch, during_close):
    async def exercise():
        writer = Writer(stall=True)
        payload = b'{"ok":true,"result":{}}\n' if during_close else None
        connection(monkeypatch, writer, payload)
        client = gateway.CeoIngressClient(connect_timeout=.05, read_timeout=.2)
        task = asyncio.create_task(client.send_frame("/synthetic-only", {"schema":"fixture"}))
        await asyncio.wait_for((writer.wait_started if during_close else writer.read_started).wait(), .2)
        task.cancel("original-caller-cancellation")
        with pytest.raises(asyncio.CancelledError, match="original-caller-cancellation"):
            await asyncio.wait_for(task, .3)
        assert len(writer.writes) == writer.close_count == writer.abort_count == 1
        assert writer.wait_settled
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    asyncio.run(exercise())


def test_normal_close_returns_original_response_without_abort(monkeypatch):
    async def exercise():
        writer = Writer()
        connection(monkeypatch, writer, b'{"ok":true,"result":{"request_ref":"same-request"}}\n')
        result = await gateway.CeoIngressClient(connect_timeout=.05, read_timeout=.05).send_frame(
            "/synthetic-only", {"schema":"fixture"})
        assert result.transport == gateway.TRANSPORT_SENT_OK
        assert result.result == {"request_ref":"same-request"}
        assert len(writer.writes) == writer.close_count == 1
        assert writer.abort_count == 0
        assert writer.wait_settled
    asyncio.run(exercise())


@pytest.mark.skipif(not hasattr(asyncio, "start_unix_server"), reason="Unix sockets unavailable")
def test_real_backpressured_unix_socket_aborts_after_drain_timeout(monkeypatch):
    import socket as sockets
    async def exercise():
        original_open = asyncio.open_unix_connection
        peer_sockets = []
        writers = []
        async def small_buffer_connection(*args, **kwargs):
            reader, writer = await original_open(*args, **kwargs)
            writer.get_extra_info("socket").setsockopt(sockets.SOL_SOCKET, sockets.SO_SNDBUF, 1024)
            writer.transport.set_write_buffer_limits(high=1, low=0)
            writers.append(writer)
            return reader, writer
        monkeypatch.setattr(gateway.asyncio, "open_unix_connection", small_buffer_connection)
        with tempfile.TemporaryDirectory(prefix="mmx-pressure-", dir="/tmp") as root:
            address = str(Path(root) / "peer.sock")
            listener = sockets.socket(sockets.AF_UNIX, sockets.SOCK_STREAM)
            listener.setsockopt(sockets.SOL_SOCKET, sockets.SO_RCVBUF, 1024)
            listener.setblocking(False)
            listener.bind(address)
            listener.listen(1)
            async def accept_without_reading():
                peer, _ = await asyncio.get_running_loop().sock_accept(listener)
                peer_sockets.append(peer)
            accepted = asyncio.create_task(accept_without_reading())
            try:
                result = await asyncio.wait_for(
                    gateway.CeoIngressClient(connect_timeout=.04, read_timeout=.04).send_frame(
                        address, {"schema":"fixture", "padding":"x" * 7600}), .5)
                await asyncio.wait_for(accepted, .2)
                assert result.transport == gateway.TRANSPORT_SENT_UNKNOWN
                assert result.detail == "send failed after connect: TimeoutError"
                assert len(writers) == len(peer_sockets) == 1
                assert writers[0].transport.is_closing()
                # The timeout cancels StreamWriter's private close waiter;
                # verify the actual descriptor, not re-await that canceled future.
                await asyncio.sleep(0)
                assert writers[0].get_extra_info("socket").fileno() == -1
            finally:
                for peer in peer_sockets:
                    peer.close()
                listener.close()
                if not accepted.done():
                    accepted.cancel()
                    await asyncio.gather(accepted, return_exceptions=True)
                for writer in writers:
                    writer.transport.abort()
    asyncio.run(exercise())
