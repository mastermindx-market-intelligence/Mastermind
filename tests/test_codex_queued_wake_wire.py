"""Actual local Unix WebSocket wire; the vendor implementation is a fixture.

No production socket, provider session or credential is contacted. The adapter
receives an established connection from its owner and never creates one itself.
"""
import asyncio
import copy
import json
import tempfile
from pathlib import Path

import pytest
from websockets.asyncio.client import unix_connect
from websockets.asyncio.server import unix_serve

from control_plane.wake_dispatcher import WakeEffectUnknownError
from integrations.executive_wake.codex_queued_wake import CodexQueuedWakeClient
from test_codex_queued_wake import args, binding, Guard


@pytest.mark.parametrize("lose_add_response", [False, True])
def test_actual_unix_websocket_recovers_original_queued_input_without_reposting(lose_add_response):
    async def exercise(socket_path):
        rows, frames = [], []
        async def handler(connection):
            async for message in connection:
                frame = json.loads(message)
                frames.append(copy.deepcopy(frame))
                assert frame["params"]["threadId"] == binding().native_handle
                if frame["method"] == "thread/queue/add":
                    p = frame["params"]
                    assert set(p) == {"threadId", "input", "clientUserMessageId"}
                    row = {"id": "queue-001", "input": p["input"],
                           "clientUserMessageId": p["clientUserMessageId"]}
                    rows.append(row)
                    if lose_add_response:
                        await connection.close(code=1011, reason="fixture response loss")
                        continue
                    result = {"queuedSubmission": row}
                else:
                    assert frame["method"] == "thread/queue/list"
                    result = {"data": rows, "nextCursor": None}
                await connection.send(json.dumps({"id": frame["id"], "result": result}))
        async with unix_serve(handler, str(socket_path), max_size=65536, close_timeout=1):
            async with unix_connect(str(socket_path), max_size=65536, close_timeout=1) as connection:
                async def rpc(frame):
                    await connection.send(json.dumps(frame))
                    return json.loads(await connection.recv())
                c = CodexQueuedWakeClient(rpc=rpc, runtime_binding=binding(), guard=Guard())
                if lose_add_response:
                    with pytest.raises(WakeEffectUnknownError): await c.deliver_wake(**args())
                else:
                    queued = await c.deliver_wake(**args())
                    assert queued.accepted and not queued.delivered
            # A new caller and connection read exactly the original persisted row.
            async with unix_connect(str(socket_path), max_size=65536, close_timeout=1) as connection:
                async def rpc(frame):
                    await connection.send(json.dumps(frame))
                    return json.loads(await connection.recv())
                recovered = CodexQueuedWakeClient(rpc=rpc, runtime_binding=binding(), guard=Guard())
                fields = args(); fields.pop("instruction")
                receipt = await recovered.reconcile_wake(**fields)
                assert receipt.accepted and not receipt.delivered
                assert receipt.target_ack_projection is None
                assert [f["method"] for f in frames] == ["thread/queue/add", "thread/queue/list"]
                assert len(rows) == 1
        assert all(task is asyncio.current_task() or task.done()
                   for task in asyncio.all_tasks())
    with tempfile.TemporaryDirectory(prefix="mmx-queued-wire-", dir="/tmp") as tmp:
        asyncio.run(exercise(Path(tmp) / "test.sock"))
    assert not Path(tmp).exists()
