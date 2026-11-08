"""Finite native READ on the incumbent SDK queue/socket; no native process or provider."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager, suppress
import hashlib
import json
import socket
import time
from types import SimpleNamespace

import pytest

from integrations.deepseek_harness.native_connection import NativeAcpProcess, NativeClient, NativeTransport, NativeWriteGuard
from integrations.deepseek_harness.native_protocol import EXTENSION_V3
from integrations.deepseek_harness.native_read_port import NativeReadUnavailable, RESPONSE_SCHEMA, canonical, native_read_frame
from scripts.ohf.acp_probe_boundary import StrictFrameReader

SESSION = "original-read-session"


def association():
    return dict(schema="mastermind.dsh.native_read_association.v1", work_ref="WS:Original-read",
        root_job_id="JOB-001", native_session_id=SESSION, owner_principal_scope="1"*64,
        composition_sha256="2"*64, native_package_sha256="3"*64,
        donor_sha="687f282e8625c6b8d11ff58211a90524be2e4317")


def request():
    return native_read_frame(association_sha256=hashlib.sha256(canonical(association())).hexdigest(),
        principal_scope="1"*64, issued_at=int(time.time())-1, expires_at=int(time.time())+120,
        request={"kind":"snapshot"})


def response(frame):
    selected = frame["params"]["request"]
    return dict(schema=RESPONSE_SCHEMA, request_id=selected["request_id"],
        association_sha256=selected["association_sha256"], status="READ",
        data={"projections":None,"page":None})


@asynccontextmanager
async def sdk(*, blocked=False):
    import acp
    from acp._transport import NdjsonTransport
    from acp.task import MessageSender, TaskSupervisor
    left, right = socket.socketpair()
    left.setblocking(False); right.setblocking(False)
    reader, writer = await asyncio.open_connection(sock=left, limit=65536)
    peer_reader, peer_writer = await asyncio.open_connection(sock=right, limit=65536)
    h = SimpleNamespace(writes=[], first=asyncio.Event(), release=asyncio.Event(),
                        bound=asyncio.Event(), allowed=True)
    if not blocked: h.release.set()
    class Writer:
        def write(self, data):
            writer.write(data); h.writes.append(data); h.first.set()
        async def drain(self):
            await h.release.wait()
            await writer.drain()
        def __getattr__(self, name):
            return getattr(writer, name)
    wrapped = Writer()
    def before_send(method):
        if method == "_mastermind/native_read": h.bound.set()
    client = NativeClient(before_send=before_send, before_write=lambda: None)
    client.advertised = True; client.bind_session(SESSION)
    native = NativeAcpProcess(client)
    native.resource = object()  # only the physical process principal is inert
    native.provider_session_id = SESSION; native.native_extension = EXTENSION_V3
    native.writer = wrapped
    native._write_guard = NativeWriteGuard(wrapped, client.before_write, client.before_native_read_write)
    tasks = TaskSupervisor(source="original-sdk-native-read-test")
    sender = MessageSender(native._write_guard, tasks)
    transport = NativeTransport(NdjsonTransport(
        StrictFrameReader(reader, client, extension_policy=client), sender), client)
    native.connection = acp.connect_to_agent(client, transport, observers=[client.observe_wire])
    h.native, h.client, h.sender, h.transport = native, client, sender, transport
    h.peer_reader, h.peer_writer = peer_reader, peer_writer
    def current():
        if not h.allowed: raise NativeReadUnavailable()
    h.current = current
    async def read():
        return await native.read_native(association(), request(), require_current=current)
    async def receive():
        return json.loads(await asyncio.wait_for(peer_reader.readline(), 2))
    async def reply(frame, value=None, *, error=None):
        message = {"jsonrpc":"2.0","id":frame["id"]}
        if error is not None: message["error"] = error
        else: message["result"] = response(frame) if value is None else value
        peer_writer.write((json.dumps(message)+"\n").encode()); await peer_writer.drain()
    h.read, h.receive, h.reply = read, receive, reply
    try:
        yield h
    finally:
        h.release.set()
        with suppress(Exception):
            await asyncio.wait_for(native.connection.close(), 2)
        await tasks.shutdown()
        writer.close(); peer_writer.close()
        await asyncio.gather(writer.wait_closed(), peer_writer.wait_closed(), return_exceptions=True)
        owned = tuple(native._tasks)
        for task in owned:
            if not task.done(): task.cancel()
        if owned: await asyncio.gather(*owned, return_exceptions=True)


def test_real_sdk_read_uses_its_original_id_parser_queue_and_no_prompt_owner():
    async def run():
        async with sdk() as h:
            connection = h.native.connection
            pending = asyncio.create_task(h.read())
            wire = await h.receive()
            held = h.client.native_read
            assert wire["method"] == "_mastermind/native_read"
            assert type(wire["id"]) in (int, str) and wire["id"] == held.request_id
            assert held.written and held.send_settled
            await h.reply(wire)
            assert (await pending)["status"] == "READ"
            assert h.native.connection is connection and h.client.native_read is None
            assert h.client.current is None and h.client.turns == 0 and not h.client._active
            assert len(h.writes) == 1
    asyncio.run(run())


@pytest.mark.parametrize("reason", ["expiry", "caller-cancel", "source"])
def test_exact_queued_read_refusal_keeps_original_sender_available(reason):
    async def run():
        async with sdk(blocked=True) as h:
            ordinary = asyncio.create_task(h.sender.send({"jsonrpc":"2.0","method":"fixture/ordinary"}))
            await h.first.wait()
            assert (await h.receive())["method"] == "fixture/ordinary"
            pending = asyncio.create_task(h.read())
            await h.bound.wait()
            held = h.client.native_read
            assert not held.written and not held.send_settled and h.sender._queue.qsize() == 1
            if reason == "expiry": held.deadline = time.monotonic()-1
            elif reason == "source": h.allowed = False
            else:
                pending.cancel()
                with pytest.raises(asyncio.CancelledError): await pending
                assert not held.task.done() and not held.task.cancelled()
            h.release.set(); await ordinary
            with pytest.raises(NativeReadUnavailable): await held.task
            if not pending.done():
                with pytest.raises(NativeReadUnavailable): await pending
            else:
                if not pending.cancelled(): pending.exception()
            assert held.write_refused and not held.written and not held.send_settled
            assert h.client.native_read is None and h.client.violation is None
            assert len(h.writes) == 1 and not h.sender._task.done()
            h.allowed = True
            following = asyncio.create_task(h.read())
            wire = await h.receive()
            assert wire["id"] != held.request_id
            await h.reply(wire)
            assert (await following)["status"] == "READ"
            assert len(h.writes) == 2 and h.client.current is None
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["result", "error"])
def test_response_cannot_settle_a_read_before_its_original_physical_write(kind):
    async def run():
        async with sdk(blocked=True) as h:
            ordinary = asyncio.create_task(h.sender.send({"jsonrpc":"2.0","method":"fixture/ordinary"}))
            await h.first.wait(); await h.receive()
            pending = asyncio.create_task(h.read()); await h.bound.wait()
            held = h.client.native_read
            wire = {"id":held.request_id,"params":held.params}
            if kind == "error": await h.reply(wire, error={"code":-32603,"message":"early"})
            else: await h.reply(wire)
            async def refused():
                while h.client.violation is None: await asyncio.sleep(0)
            await asyncio.wait_for(refused(), 2)
            assert h.client.violation == "NATIVE_READ_RESPONSE_REFUSED"
            h.release.set()
            await asyncio.gather(ordinary, return_exceptions=True)
            await asyncio.wait_for(asyncio.gather(pending, return_exceptions=True), 2)
            assert len(h.writes) == 1 and not held.written
    asyncio.run(run())


def test_cancelled_written_read_keeps_sdk_custody_and_discards_late_reply():
    async def run():
        async with sdk() as h:
            pending = asyncio.create_task(h.read()); wire = await h.receive()
            held = h.client.native_read
            pending.cancel()
            with pytest.raises(asyncio.CancelledError): await pending
            assert held.retired and held.send_settled and not held.task.done()
            assert h.client.native_read is held and held.task in h.native._tasks
            with pytest.raises(NativeReadUnavailable): await h.read()
            # A settled, retired observation cannot reserve the next prompt.
            turn = h.client.begin_native_prompt("next-original-operation")
            assert turn.operation_id == "next-original-operation" and h.client.turns == 1
            await h.reply(wire)
            with pytest.raises(NativeReadUnavailable): await held.task
            assert h.client.native_read is None and h.client.violation is None
            assert len(h.writes) == 1 and h.client.current is turn
    asyncio.run(run())


@pytest.mark.parametrize("changed", ["guard", "read-guard", "callback"])
def test_read_refuses_without_the_original_installed_physical_guard(changed):
    async def run():
        async with sdk() as h:
            if changed == "guard": h.native._write_guard = None
            elif changed == "read-guard": h.native._write_guard.read_guard = None
            else: h.native._write_guard.read_guard = lambda _data: True
            with pytest.raises(NativeReadUnavailable): await h.read()
            assert h.writes == [] and h.client.native_read is None
    asyncio.run(run())


def test_before_send_mutation_is_refused_before_queue_and_releases_only_unsent_read():
    async def run():
        async with sdk() as h:
            def changed(method):
                if method == "_mastermind/native_read":
                    h.client.native_read.params["request"]["read"] = {"kind":"foreign"}
            h.client.before_send = changed
            with pytest.raises(NativeReadUnavailable): await h.read()
            assert h.writes == [] and h.sender._queue.empty()
            assert h.client.native_read is None and h.client.current is None
    asyncio.run(run())


@pytest.mark.parametrize("changed", ["correlation", "association", "size"])
def test_malformed_content_never_passes_the_original_sdk_receive_gate(changed):
    async def run():
        async with sdk() as h:
            pending = asyncio.create_task(h.read()); wire = await h.receive()
            result = response(wire)
            if changed == "correlation": result["request_id"] = "f"*64
            elif changed == "association": result["association_sha256"] = "f"*64
            else: result["data"]["page"] = "x"*33000
            await h.reply(wire, result)
            outcome = await asyncio.wait_for(asyncio.gather(pending, return_exceptions=True), 2)
            assert isinstance(outcome[0], Exception)
            assert h.client.violation == "NATIVE_READ_RESPONSE_REFUSED"
            assert h.client.current is None and h.client.turns == 0
    asyncio.run(run())


def test_written_read_timeout_withholds_late_content_and_keeps_original_future():
    async def run():
        async with sdk() as h:
            pending=asyncio.create_task(h.read())
            wire=await h.receive();held=h.client.native_read
            with pytest.raises(NativeReadUnavailable): await asyncio.wait_for(pending,5)
            assert held.retired and held.send_settled and not held.task.done()
            assert h.client.native_read is held
            turn=h.client.begin_native_prompt("after-original-read-timeout")
            await h.reply(wire)
            with pytest.raises(NativeReadUnavailable): await held.task
            assert h.client.current is turn and h.client.native_read is None
            assert h.client.violation is None and not h.sender._task.done()
    asyncio.run(run())


def test_failed_drain_after_suppression_does_not_revive_a_dead_sdk_sender():
    async def run():
        async with sdk(blocked=True) as h:
            ordinary=asyncio.create_task(h.sender.send({"jsonrpc":"2.0","method":"fixture/ordinary"}))
            await h.first.wait();await h.receive()
            pending=asyncio.create_task(h.read());await h.bound.wait()
            held=h.client.native_read;held.deadline=time.monotonic()-1
            async def failed_drain(): raise OSError("inert original drain failure")
            # The first drain is already executing its original bound method;
            # only the next original sender item encounters this failed drain.
            h.native.writer.drain=failed_drain
            h.release.set();await ordinary
            with pytest.raises(OSError): await pending
            assert held.write_refused and not held.written and not held.send_settled
            assert h.client.violation == "NATIVE_READ_SEND_UNSETTLED"
            assert len(h.writes) == 1
            with pytest.raises(Exception): h.client.begin_native_prompt("cannot-revive-sender")
    asyncio.run(run())
