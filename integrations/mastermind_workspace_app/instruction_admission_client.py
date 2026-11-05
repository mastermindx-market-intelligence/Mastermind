"""One fixed instruction-control exchange on the incumbent App-peer socket."""
import asyncio
import json
from common.executive_workspace_contract import canonical
from common import workspace_instruction_admission_contract as wire
from control_plane.workspace_owned_task import await_owned


async def request_instruction_admission(client, frame):
    checked = wire.validate_frame(frame)
    encoded = canonical(checked) + b"\n"
    attempted, received = False, None
    mode = wire.SCHEMAS[checked['schema']]
    timeout = client.action_timeout_seconds if mode == "pause" else client.acceptance_timeout_seconds
    async def exchange():
        nonlocal attempted, received
        reader, writer = await asyncio.open_unix_connection(str(client.socket_path), limit=wire.MAX_RESPONSE_BYTES)
        try:
            attempted = True
            writer.write(encoded)
            await writer.drain()
            raw = await reader.readuntil(b"\n")
            if len(raw) > wire.MAX_RESPONSE_BYTES:
                raise ValueError("source_unavailable")
            def pairs(items):
                result = {}
                for key, item in items:
                    if key in result:
                        raise ValueError("source_unavailable")
                    result[key] = item
                return result
            received = wire.validate_envelope(json.loads(raw, object_pairs_hook=pairs), checked)
        finally:
            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), timeout=min(1.0, timeout))
            except (Exception, asyncio.CancelledError):
                pass
    async def bounded():
        try:
            await asyncio.wait_for(exchange(), timeout=timeout)
        except Exception:
            pass
        if received is not None:
            return received
        return wire.withheld(checked, attempted=attempted)
    # One connection/write only. Cancellation cannot turn a possibly committed
    # mutation into NOT_DISPATCHED or authorize a replacement command.
    return await await_owned(asyncio.create_task(bounded()))
