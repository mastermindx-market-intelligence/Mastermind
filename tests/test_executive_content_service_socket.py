"""Service-socket proofs for the corrected CONTROL_INTEGRATION patch.

Every case drives the real ``ExecutiveControlService`` over real AF_UNIX
sockets (the CeoIngress listener and the generic Operator control listener),
using the fixtures of ``test_executive_ceo_ingress`` /
``test_executive_app_peer_binding``.  No callback-only substitution stands in
for the socket path:

* a ~48 KiB content page succeeds through the widened page ceiling only for
  the authorized installed App peer — the C1 peer and unknown peers are
  refused before any content handling;
* an oversized page reply is refused closed (``response_too_large``), never
  truncated, and the connection terminates;
* legacy ingress replies keep the unchanged 32 KiB ceiling and
  ``_send_dialogue_observation`` keeps its original signature;
* the explicit content lifecycle commands are control-UID-only on the
  generic control socket.
"""
import asyncio
import inspect
import json
import os
import tempfile
from pathlib import Path

import pytest

from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane.executive_service import (
    CEO_APP_READ_SCHEMA,
    CONTROL_PROTOCOL_VERSION,
    CeoIngressAppBinding,
    ExecutiveControlService,
)
from integrations.executive_content_contract import (
    ACCESS_SCHEMA,
    MAX_PAGE_BYTES,
    PAGE_SCHEMA,
)

from tests.test_executive_ceo_ingress import (
    _FakeGrounding,
    _FakeSupervisor,
    _config,
    _raw_ceo_request,
    short_socket_root,  # noqa: F401
)
from test_steward_content_integration import fixture


class _StubReads:
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        return self._result

    async def aclose(self):
        return None


class _StubContentProvider:
    def __init__(self, frame_result):
        self._frame_result = frame_result
        self.frames = []

    async def handle_frame(self, frame):
        self.frames.append(frame)
        return self._frame_result


def _same_runtime_provider(expected_runtime, observer):
    def provide(actual_runtime):
        assert actual_runtime is expected_runtime
        assert observer.runtime is actual_runtime
        return observer
    return provide


def _content_binding(**overrides):
    values = dict(
        peer_uid=os.geteuid(),
        armed=True,
        grounding_provider=_FakeGrounding(),
    )
    values.update(overrides)
    return CeoIngressAppBinding(**values)


def test_content_page_48k_succeeds_only_on_authorized_app_peer(
    tmp_path, short_socket_root
):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def exercise():
        from control_plane.executive_content_observer import ExecutiveContentObserver
        from control_plane.executive_worker_broker import WorkerBrokerClient
        from control_plane.visible_turn_projection import TurnKey

        with tempfile.TemporaryDirectory(prefix="mmsock-", dir="/tmp") as directory:
            broker_path = Path(directory) / "broker.sock"

            async def serve_broker(reader, writer):
                frame = json.loads(await reader.readline())
                try:
                    result = await broker._dispatch(frame["operation"], frame["payload"])
                    reply = dict(schema_version="mastermind.executive_worker_broker_response/v1",
                                 request_id=frame["request_id"], operation=frame["operation"],
                                 ok=True, result=result)
                except Exception:
                    reply = dict(schema_version="mastermind.executive_worker_broker_response/v1",
                                 request_id=frame["request_id"], operation=frame["operation"],
                                 ok=False, error={"code": "state_conflict", "message": "refused"})
                from integrations.executive_content_contract import canonical
                writer.write(canonical(reply) + b"\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            broker_server = await asyncio.start_unix_server(
                serve_broker, path=str(broker_path)
            )
            async with broker_server:
                observer = ExecutiveContentObserver(
                    runtime=runtime,
                    broker_client=WorkerBrokerClient(broker_path),
                    profile_loader=lambda: p,
                    now=lambda: clock.value // 1000,
                )
                service = ExecutiveControlService(
                    _config(tmp_path, socket_root=short_socket_root),
                    runtime_factory=lambda _path: runtime,
                    supervisor_factory=lambda runtime: _FakeSupervisor(),
                    ceo_ingress_socket_path=short_socket_root / "ceo.sock",
                    ceo_ingress_peer_uid=os.geteuid() + 1000,
                    ceo_ingress_grounding_provider=_FakeGrounding(),
                    ceo_ingress_app_binding=_content_binding(
                        content_provider_factory=_same_runtime_provider(runtime, observer),
                    ),
                )
                await service.start()
                try:
                    enrolled = await observer.enroll()
                    assert enrolled["status"] == "ACTIVE"
                    key = TurnKey(**enrolled["turn_key"])
                    for n in range(4):
                        adapter.visible_turn_projection.publish(
                            key,
                            method="item/updated",
                            params={"item": {"type": "agentMessage", "id": str(n),
                                             "sequence": n, "text": "x" * 12000}},
                            native_turn_id="NATIVE-G1",
                        )
                    socket_path = service.ceo_ingress_socket_path
                    access_raw = await _raw_ceo_request(
                        socket_path,
                        (json.dumps(p.frame(ACCESS_SCHEMA)) + "\n").encode(),
                    )
                    assert access_raw["ok"] is True, access_raw
                    ticket = access_raw["access"]["ticket_digest"]
                    page_frame = dict(p.frame(PAGE_SCHEMA),
                                      access_ticket_digest=ticket,
                                      cursor=None, max_items=4)
                    page_raw = await _raw_ceo_request(
                        socket_path,
                        (json.dumps(page_frame) + "\n").encode(),
                    )
                    assert page_raw["ok"] is True, page_raw
                    items = page_raw["page"]["items"]
                    assert [item["byte_length"] for item in items] == [12000] * 4
                    # The reply body is larger than the legacy 32 KiB ceiling:
                    # only the widened page ceiling lets it through.
                    body = json.dumps(page_raw["page"]).encode()
                    assert len(body) > ceo_ingress.MAX_RESPONSE_BYTES
                    assert len(body) < MAX_PAGE_BYTES
                    assert "reader_grant" not in page_raw["page"]

                    # The C1 peer uid cannot obtain the same page: the content
                    # branch is App-peer-only, so its frame is refused by the
                    # CeoIngress admission before any content handling.
                    import control_plane.executive_service as service_module
                    c1_uid = os.geteuid() + 1000
                    original = service_module._peer_uid
                    service_module._peer_uid = lambda sock: c1_uid
                    try:
                        c1 = await _raw_ceo_request(
                            socket_path,
                            (json.dumps(page_frame) + "\n").encode(),
                        )
                        assert c1["ok"] is False
                        assert c1["error"]["code"] in {
                            "peer_denied", "unsupported_ingress_schema"}
                        assert "page" not in c1 and "reader_grant" not in c1
                        # An unknown uid is refused at the identity gate.
                        service_module._peer_uid = lambda sock: os.geteuid() + 2000
                        unknown = await _raw_ceo_request(
                            socket_path,
                            (json.dumps(page_frame) + "\n").encode(),
                        )
                        assert unknown["error"]["code"] == "peer_denied"
                    finally:
                        service_module._peer_uid = original
                finally:
                    await service.close()

    asyncio.run(exercise())


def test_oversized_content_page_is_refused_closed_never_truncated(
    tmp_path, short_socket_root
):
    provider = _StubContentProvider(
        {"ok": True, "page": {"items": [{"text": "x" * (MAX_PAGE_BYTES + 1)}]}}
    )

    async def exercise():
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=_content_binding(
                content_provider_factory=lambda _runtime: provider,
            ),
        )
        await service.start()
        try:
            frame = {"schema": PAGE_SCHEMA, "profile_digest": "a" * 64,
                     "source_ref": "managed-window:canary",
                     "viewer_binding_digest": "b" * 64,
                     "access_ticket_digest": "c" * 64, "cursor": None,
                     "max_items": 4}
            reader, writer = await asyncio.open_unix_connection(
                str(service.ceo_ingress_socket_path), limit=MAX_PAGE_BYTES * 2
            )
            try:
                writer.write((json.dumps(frame) + "\n").encode())
                await writer.drain()
                response = await reader.readline()
                parsed = json.loads(response)
                assert parsed == {"ok": False, "error": {
                    "code": "response_too_large",
                    "message": "response exceeds byte limit"}}
                assert b"xxxx" not in response
                # Exactly one bounded reply, then the connection is closed.
                assert await reader.readline() == b""
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionResetError, BrokenPipeError):
                    pass
            assert provider.frames == [frame]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_legacy_replies_keep_unchanged_ceiling_and_dialogue_signature(
    tmp_path, short_socket_root
):
    big = {"ok": True, "data": {"blob": "y" * 40000}}
    reads = _StubReads(big)

    async def exercise():
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=_content_binding(read_provider=reads),
        )
        await service.start()
        try:
            socket_path = service.ceo_ingress_socket_path
            frame = {"schema": CEO_APP_READ_SCHEMA, "tool": "executive_state",
                     "arguments": {}}
            oversized = await _raw_ceo_request(
                socket_path, (json.dumps(frame) + "\n").encode()
            )
            assert oversized == {"ok": False, "error": {
                "code": "response_too_large",
                "message": "response exceeds byte limit"}}
            # The dialogue observation sender keeps its original shape: the
            # response ceiling belongs to the CeoIngress sender only.
            parameters = list(
                inspect.signature(
                    ExecutiveControlService._send_dialogue_observation
                ).parameters.values()
            )
            assert [p.name for p in parameters] == ["self", "writer", "payload"]
            assert all(
                p.default is inspect.Parameter.empty for p in parameters[1:]
            )
            ingress_signature = inspect.signature(
                ExecutiveControlService._send_ceo_ingress_response
            ).parameters
            assert ingress_signature["response_ceiling"].default \
                is ceo_ingress.MAX_RESPONSE_BYTES
        finally:
            await service.close()
        assert reads.calls == [("executive_state", {})]

    asyncio.run(exercise())


def _control_line(command):
    return (
        json.dumps(
            {"version": CONTROL_PROTOCOL_VERSION, "command": command, "args": {}},
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def test_content_lifecycle_commands_are_control_uid_only(
    tmp_path, short_socket_root, monkeypatch
):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def exercise():
        from control_plane.executive_content_observer import ExecutiveContentObserver

        class _DirectBroker:
            async def request(self, operation, payload):
                return await broker._dispatch(operation, dict(payload))

        observer = ExecutiveContentObserver(
            runtime=runtime,
            broker_client=_DirectBroker(),
            profile_loader=lambda: p,
            now=lambda: clock.value // 1000,
        )
        service = ExecutiveControlService(
            _config(
                tmp_path,
                socket_root=short_socket_root,
                allowed_peer_uids=(os.geteuid(), os.geteuid() + 1000),
                socket_path=short_socket_root / "operator.sock",
            ),
            runtime_factory=lambda _path: runtime,
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=_content_binding(
                content_provider_factory=_same_runtime_provider(runtime, observer),
            ),
        )
        await service.start()
        try:
            control_socket = service.config.socket_path
            enroll = await _raw_ceo_request(control_socket, _control_line("content-observer-enroll"))
            assert enroll["ok"] is True, enroll
            assert enroll["result"]["status"] == "ACTIVE"
            assert set(enroll["result"]) == {"status", "binding_digest"}
            assert len(enroll["result"]["binding_digest"]) == 64
            status = await _raw_ceo_request(control_socket, _control_line("content-observer-status"))
            assert status["result"]["status"] == "ACTIVE"
            revoke = await _raw_ceo_request(control_socket, _control_line("content-observer-revoke"))
            assert revoke["result"]["status"] == "REVOKED"

            # An allowed but non-control uid is refused before any lifecycle
            # handling, while the generic dispatch path still serves it.
            monkeypatch.setattr(
                "control_plane.executive_service._peer_uid",
                lambda sock: os.geteuid() + 1000,
            )
            denied = await _raw_ceo_request(control_socket, _control_line("content-observer-enroll"))
            assert denied == {"ok": False, "error": {
                "code": "peer_denied",
                "message": "content enrollment requires control uid"}}
            generic = await _raw_ceo_request(control_socket, _control_line("status"))
            assert generic["ok"] is True, generic

            # A uid outside the allowlist is refused at the identity gate.
            monkeypatch.setattr(
                "control_plane.executive_service._peer_uid",
                lambda sock: os.geteuid() + 2000,
            )
            gate = await _raw_ceo_request(control_socket, _control_line("content-observer-status"))
            assert gate["error"]["code"] == "peer_denied"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_content_lifecycle_without_factory_refuses_closed(tmp_path, short_socket_root):
    async def exercise():
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
        )
        await service.start()
        try:
            reply = await _raw_ceo_request(
                service.config.socket_path, _control_line("content-observer-enroll")
            )
            assert reply == {"ok": False, "error": {
                "code": "content_observer_refused",
                "message": "content observer action refused"}}
        finally:
            await service.close()

    asyncio.run(exercise())
