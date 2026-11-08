"""The native consumer decodes the donor's actual tool projections, not grants."""
import asyncio
import copy
import json
import pytest
from acp.schema import ToolCallStart, ToolCallProgress
from integrations.deepseek_harness.native_connection import NativeClient
from scripts.ohf.acp_probe_boundary import BoundaryViolation, StrictFrameReader, ProbeLimits

def call(raw=None):
    return {"sessionUpdate":"tool_call","toolCallId":"opaque provider call / 1","title":"read",
        "kind":"other","status":"in_progress","rawInput":raw}

def result(content=None):
    return {"sessionUpdate":"tool_call_update","toolCallId":"opaque provider call / 1","status":"completed",
        "content":[] if content is None else content}

def active(progress=None):
    client=NativeClient(progress)
    client.advertised=True;client.bind_session("original_session");client.begin_native_prompt("original-operation")
    return client

@pytest.mark.parametrize("raw",[None,{},[],False,1,2.5,"","malformed {","opaque"])
def test_raw_and_sdk_tool_call_keep_explicit_null_and_pure_admission(raw):
    async def exercise():
        progress=[];client=active(progress.append);wire=call(raw)
        expected=client.admit_update(wire)
        assert client.admit_update(wire)==expected and client._updates==0
        typed=ToolCallStart.model_validate(wire)
        assert client.admit_update(typed)==expected
        await client.session_update("original_session",typed)
        assert client.violation is None and client._updates==1 and client._text_bytes==expected
        assert progress[0]["evidence_kind"]=="NATIVE_SESSION_TOOL_PROJECTION"
        assert progress[0]["reported_status"]=="in_progress"
        assert set(progress[0])=={"kind","tool_call_id","reported_status","evidence_kind","payload_bytes","payload_sha256"}
        assert not any(key in progress[0] for key in ("rawInput","content","execution","settlement"))
    asyncio.run(exercise())

@pytest.mark.parametrize("content",[
    [],[{"type":"content","content":{"type":"text","text":"original result"}}],
    [{"type":"content","content":{"type":"image","data":"aGVsbG8=","mimeType":"image/png"}}],
    [{"type":"content","content":{"type":"text","text":"first"}},
     {"type":"content","content":{"type":"text","text":"second"}}],
])
def test_array_valued_tool_results_pass_the_original_sdk_callback(content):
    async def exercise():
        progress=[];client=active(progress.append);wire=result(content)
        for status in ("completed","failed"):
            wire["status"]=status
            typed=ToolCallProgress.model_validate(wire)
            assert client.admit_update(typed)==client.admit_update(wire)
            await client.session_update("original_session",typed)
        assert client.violation is None and client._updates==2
        assert [x["reported_status"] for x in progress]==["completed","failed"]
        assert all(x["payload_bytes"]>0 and len(x["payload_sha256"])==64 for x in progress)
    asyncio.run(exercise())

def malformed():
    values=[]
    a=call();del a["rawInput"];values.append(a)
    for key,value in [("rawOutput","unowned"),("kind","read"),("status","completed"),("toolCallId",""),("title",42)]:
        values.append({**call(),key:value})
    for content in [
        {},[{"type":"diff","path":"/foreign","newText":"unowned"}],
        [{"type":"content","content":{"type":"text","text":"x","metadata":{}}}],
        [{"type":"content","content":{"type":"image","data":"aGVsbG8= ","mimeType":"image/png"}}],
        [{"type":"content","content":{"type":"image","data":"AB==","mimeType":"image/png"}}],
        [{"type":"content","content":{"type":"image","data":"AA==","mimeType":"image/svg+xml"}}],
    ]:values.append(result(content))
    values.extend([{**result(),"rawOutput":{}},{**result(),"status":"in_progress"},call(float("nan"))])
    return values

@pytest.mark.parametrize("wire",malformed())
def test_foreign_tool_shapes_remain_refused(wire):
    with pytest.raises((BoundaryViolation,ValueError,TypeError)):
        NativeClient().admit_update(wire)

def test_tool_projection_respects_original_shape_and_aggregate_budgets():
    async def exercise():
        client=active();client.limits=ProbeLimits(text_bytes=80,updates=5,frames=20)
        await client.session_update("original_session",ToolCallStart.model_validate(call("large"*30)))
        assert client.violation=="TEXT_BUDGET_EXCEEDED" and client._updates==0
        deeply={}
        for _ in range(35):deeply={"x":deeply}
        for raw in (deeply,[0]*8200,"x"*(64*1024)):
            with pytest.raises((BoundaryViolation,ValueError)):
                NativeClient().admit_update(call(raw))
    asyncio.run(exercise())

def test_one_raw_frame_guard_and_original_sdk_callback_accept_the_same_projection():
    async def exercise():
        client=active();reader=asyncio.StreamReader(limit=64*1024)
        wire={"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"original_session","update":call(None)}}
        raw=(json.dumps(wire,separators=(",",":"))+"\n").encode()
        reader.feed_data(raw);reader.feed_eof()
        guard=StrictFrameReader(reader,client,extension_policy=client)
        assert await guard.readuntil()==raw and client._updates==0
        await client.session_update("original_session",ToolCallStart.model_validate(wire["params"]["update"]))
        assert client.violation is None and client._updates==1
    asyncio.run(exercise())

def test_tool_notice_after_terminal_remains_refused():
    async def exercise():
        client=active();client.seal()
        await client.session_update("original_session",ToolCallProgress.model_validate(result()))
        assert client.violation=="CALLBACK_OUTSIDE_PROMPT" and client._updates==0
    asyncio.run(exercise())
