"""Two-phase provider-start boundary counterexamples; synthetic process output only."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import pytest

@pytest.fixture
def two_phase(monkeypatch):
    from brain import codex_bridge
    starts, guards = [], []
    class Process:
        returncode = 0
        def __init__(self, phase):
            self.phase = phase
        async def communicate(self, payload):
            rows = [{"type":"thread.started","thread_id":"fixture-phase-"+str(self.phase)}]
            if self.phase == 2:
                rows.append({"type":"item.completed","item":{"type":"mcp_tool_call",
                    "tool":"mcp__desk__submit_book","status":"completed"}})
            rows.append({"type":"item.completed","item":{"type":"agent_message",
                "text":"Synthetic research" if self.phase == 1 else "Synthetic submission"}})
            rows.append({"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}})
            return "\n".join(json.dumps(x) for x in rows).encode(), b""
    async def process(*argv, **kwargs):
        starts.append({"argv":list(argv),"prompt_env_keys":sorted((kwargs.get("env") or {}).keys())})
        return Process(len(starts))
    monkeypatch.setattr(codex_bridge,"codex_path",lambda:"/synthetic/codex")
    monkeypatch.setattr(codex_bridge,"available",lambda:True)
    monkeypatch.setattr(codex_bridge,"_mcp_secret_bundle",lambda:(None,None))
    monkeypatch.setattr(codex_bridge,"_subprocess_env",lambda:{})
    monkeypatch.setattr(asyncio,"create_subprocess_exec",process)
    def run(guard=None):
        kwargs = {"before_provider_start":guard} if guard is not None else {}
        return asyncio.run(codex_bridge.reason(
            "Synthetic governed-book request; no actual provider or book mutation.",
            allowed_tools=["mcp__desk__get_my_book","mcp__desk__submit_book","Task"],
            mcp_servers={"bot":{},"desk":{}},book="autonomous",**kwargs))
    return run, starts, guards

def test_actual_two_phase_control_without_callback(two_phase):
    run, starts, guards=two_phase
    out=run()
    assert out["ok"] is True, out
    assert out["delegated_research_completed"] is True
    assert out["research_session_id"]=="fixture-phase-1"
    assert out["session_id"]=="fixture-phase-2"
    assert len(starts)==2
    assert "agents.enabled=true" in starts[0]["argv"]
    assert "agents.enabled=false" in starts[1]["argv"]
    assert "mcp__desk__submit_book" in out["tools_used"]
    assert guards==[]

def test_callback_is_rechecked_before_each_actual_phase(two_phase):
    run, starts, guards=two_phase
    def guard():
        guards.append(len(starts))
    out=run(guard)
    assert out["ok"] is True, out
    assert len(starts)==2
    assert guards==[0,1], "The same veto must run before research and sealed submission"

def test_first_phase_denial_prevents_all_process_starts(two_phase):
    from brain.cli_bridge import ProviderStartRefused
    run, starts, guards=two_phase
    def guard():
        guards.append(len(starts))
        raise ValueError("SYNTHETIC PRIVATE DENIAL")
    with pytest.raises(ProviderStartRefused,match="source admission revoked") as caught:
        run(guard)
    assert guards==[0] and starts==[]
    assert "PRIVATE DENIAL" not in str(caught.value)

@pytest.mark.parametrize("verdict",["raise","false","true"])
def test_second_phase_denial_keeps_completed_research_and_stops_submission(two_phase,verdict):
    from brain.cli_bridge import ProviderStartRefused
    run, starts, guards=two_phase
    def guard():
        guards.append(len(starts))
        if len(guards)==1:
            return None
        if verdict=="raise":
            raise ValueError("SYNTHETIC SOURCE EXPIRED AFTER RESEARCH")
        return verdict=="true"
    with pytest.raises(ProviderStartRefused,match="source admission revoked"):
        run(guard)
    assert guards==[0,1]
    assert len(starts)==1

def test_second_phase_cancellation_is_same_exception_without_second_process(two_phase):
    run, starts, guards=two_phase
    interruption=asyncio.CancelledError("synthetic cancellation")
    def guard():
        guards.append(len(starts))
        if len(guards)==2:
            raise interruption
    with pytest.raises(asyncio.CancelledError) as caught:
        run(guard)
    assert caught.value is interruption
    assert guards==[0,1] and len(starts)==1
