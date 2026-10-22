"""Transport-only proof for the closed VPS inference frame budget."""
import asyncio

from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane import executive_inference_ingress as service
from integrations.mastermind_executive_app import gateway


def test_inference_frame_budget_is_additive_and_schema_closed(tmp_path):
    async def exercise():
        seen = []
        handlers = set()

        async def peer(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                seen.append(await reader.readline())
                writer.write(b'{"ok":true,"result":{}}\n')
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                handlers.discard(task)

        socket = tmp_path / "service-inference.sock"
        server = await asyncio.start_unix_server(peer, path=str(socket))
        try:
            client = gateway.CeoIngressClient(
                connect_timeout=0.2, read_timeout=0.2
            )
            service_frame = {
                "schema": service.SUBMIT_SCHEMA,
                "padding": "x" * (ceo_ingress.MAX_REQUEST_BYTES + 1024),
            }
            accepted = await client.send_frame(socket, service_frame)
            assert accepted.transport == gateway.TRANSPORT_SENT_OK
            assert accepted.ok is True
            assert len(seen) == 1
            assert ceo_ingress.MAX_REQUEST_BYTES < len(seen[0])
            assert len(seen[0]) <= service.MAX_FRAME_BYTES

            legacy_frame = {
                "schema": ceo_ingress.SUBMIT_SCHEMA,
                "padding": "x" * (ceo_ingress.MAX_REQUEST_BYTES + 1024),
            }
            legacy = await client.send_frame(socket, legacy_frame)
            assert legacy.transport == gateway.TRANSPORT_NOT_SENT
            assert len(seen) == 1

            oversized_service = {
                "schema": service.SUBMIT_SCHEMA,
                "padding": "x" * service.MAX_FRAME_BYTES,
            }
            oversized = await client.send_frame(socket, oversized_service)
            assert oversized.transport == gateway.TRANSPORT_NOT_SENT
            assert len(seen) == 1
        finally:
            server.close()
            await server.wait_closed()
            if handlers:
                await asyncio.wait_for(
                    asyncio.gather(*handlers, return_exceptions=True), 0.5
                )

    asyncio.run(exercise())
