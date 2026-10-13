"""Real Unix COMMIT transport; no installed host or provider effect is exercised."""
import asyncio
from contextlib import contextmanager
import json
import inspect
import tempfile
from pathlib import Path

import pytest

from integrations.slack_agent_dialogue.service import call_service, DialogueServiceError
from tests.test_slack_agent_dialogue_service import exact_send_request_v2


def exercise(monkeypatch, *, refuse=False, exit_failure=False, lost_response=False):
    state = {"held": False, "writes": [], "guard_calls": 0, "hook_calls": 0}
    original_write = asyncio.StreamWriter.write

    def checked_write(writer, data):
        if json.loads(data).get("commit") == "COMMIT":
            # Observe the real transport boundary, not a fake service method.
            assert state["held"], "COMMIT escaped the host writer fence"
            state["writes"].append(json.loads(data))
        return original_write(writer, data)

    monkeypatch.setattr(asyncio.StreamWriter, "write", checked_write)

    @contextmanager
    def fence():
        state["guard_calls"] += 1
        assert state["hook_calls"] == 1
        if refuse:
            raise ValueError("writer revoked")
        state["held"] = True
        try:
            yield
        finally:
            state["held"] = False
        if exit_failure:
            raise ValueError("fence settlement unavailable")

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="nr-fence-", dir="/tmp") as directory:
            path = Path(directory) / "relay.sock"
            request = exact_send_request_v2()
            fingerprint = request["args"]["message"]["fingerprint"]
            finished = asyncio.Event()
            failures = []

            async def server(reader, writer):
                try:
                    received = json.loads(await reader.readline())
                    assert received == request
                    writer.write(json.dumps({"ok": True, "ready": {"fingerprint": fingerprint}}).encode() + b"\n")
                    await writer.drain()
                    frame = await reader.readline()
                    if frame and not lost_response:
                        assert json.loads(frame) == {"commit": "COMMIT", "fingerprint": fingerprint}
                        writer.write(json.dumps({"ok": True, "result": {"action": "POSTED"}}).encode() + b"\n")
                        await writer.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    writer.close()
                    finished.set()

            async def before_write():
                assert not state["held"], "carrier read must not hold Runtime's write transaction"
                await asyncio.sleep(0)
                state["hook_calls"] += 1

            listener = await asyncio.start_unix_server(server, path)
            try:
                try:
                    # Exercise the unfenced baseline too: a missing hook must
                    # fail for an escaping COMMIT, not an unexpected keyword.
                    options = ({"commit_fence": fence}
                               if "commit_fence" in inspect.signature(call_service).parameters else {})
                    result = await call_service(path, request, timeout_seconds=1,
                                                before_write=before_write, **options)
                    return result, state
                finally:
                    await asyncio.wait_for(finished.wait(), 2)
                    assert not failures
                    assert state["guard_calls"] == 1
                    assert len(state["writes"]) == (0 if refuse else 1)
                    assert state["held"] is False
            finally:
                listener.close()
                await listener.wait_closed()

    return asyncio.run(scenario()), state


def test_fence_encloses_commit_write_and_releases_before_response(monkeypatch):
    (result, state), _ = exercise(monkeypatch)
    assert result == {"ok": True, "result": {"action": "POSTED"}}
    assert state["guard_calls"] == 1 and len(state["writes"]) == 1
    assert state["held"] is False


def test_revoked_writer_never_writes_commit(monkeypatch):
    with pytest.raises(DialogueServiceError) as error:
        exercise(monkeypatch, refuse=True)
    assert error.value.code == "SERVICE_UNAVAILABLE"


@pytest.mark.parametrize("fault", ["exit_failure", "lost_response"])
def test_failure_after_commit_is_unknown_and_never_retried(monkeypatch, fault):
    with pytest.raises(DialogueServiceError) as error:
        exercise(monkeypatch, **{fault: True})
    assert error.value.code == "SEND_EFFECT_UNKNOWN"
