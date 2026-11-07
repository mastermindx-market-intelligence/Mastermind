"""One closed READ exchange on the incumbent App-peer socket."""
import asyncio
import json
from common.executive_workspace_contract import canonical
from common import workspace_host_observation_contract as wire


async def request_host_observation(client, frame):
    checked = wire.validate_frame(frame)
    encoded = canonical(checked) + b"\n"
    async def exchange():
        reader, writer = await asyncio.open_unix_connection(str(client.socket_path), limit=wire.MAX_RESPONSE_BYTES)
        try:
            writer.write(encoded)
            await writer.drain()
            raw = await reader.readuntil(b"\n")
            if len(raw) > wire.MAX_RESPONSE_BYTES:
                raise ValueError("source_unavailable")
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result: raise ValueError("source_unavailable")
                    result[key] = value
                return result
            value = json.loads(raw, object_pairs_hook=pairs)
            if type(value) is not dict:
                raise ValueError("source_unavailable")
            if value.get("ok") is True:
                if set(value) != {"ok", "result"}: raise ValueError("source_unavailable")
                wire.validate_result(value["result"], checked["selection"])
            elif (value.get("ok") is not False or set(value) != {"ok", "status", "error"}
                    or type(value["status"]) is not int or value["status"] not in (400, 403, 404, 503)
                    or type(value["error"]) is not dict or set(value["error"]) != {"code", "message"}):
                raise ValueError("source_unavailable")
            return value
        finally:
            writer.close()
            await writer.wait_closed()
    try:
        return await asyncio.wait_for(exchange(), client.timeout_seconds)
    except Exception:
        raise ValueError("source_unavailable") from None
