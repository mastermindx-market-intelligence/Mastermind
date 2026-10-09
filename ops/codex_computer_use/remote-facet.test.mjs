import assert from "node:assert/strict";
import test from "node:test";
import {createComputerUseFacet,COMPUTER_USE_FACET_TOOLS} from "./remote-facet.mjs";

const context={session:"s-1",principal:"p-1",host:"trusted-owner-binding"};
const grant=(write=false)=>({
  allowed:true,canRead:true,canWrite:write,
  principalRef:"owner-principal",bindingRef:"owner-runtime-binding",
  operationRef:"owner-operation",
});
test("closed catalog and read-only exposure require fresh bound owner decision",async()=>{
  let seen=[];
  const facet=createComputerUseFacet({
    authorize:async(ctx,req)=>{seen.push(req.mode);return req.mode==="read"?grant():null},
    dispatch:async()=>({content:[]}),
  });
  assert.equal((await facet.listTools(null)).tools.length,0);
  const names=(await facet.listTools(context)).tools.map(x=>x.name);
  assert.deepEqual(names,["cuse_list_apps","cuse_get_app_state"]);
  assert.deepEqual(seen,["read","write"]);
  assert.equal(COMPUTER_USE_FACET_TOOLS.length,5);
});
test("read dispatch uses owner binding and unchanged MCP response",async()=>{
  const calls=[];
  const result={content:[{type:"text",text:"Calculator permitted"}],isError:false};
  const facet=createComputerUseFacet({
    authorize:async(_,req)=>req.mode==="read"?grant():null,
    dispatch:async(x)=>{calls.push(x);return result},
  });
  const output=await facet.callTool({name:"cuse_get_app_state",arguments:{app:"com.apple.calculator"}},context);
  assert.equal(output,result);
  assert.equal(calls[0].toolName,"get_app_state");
  assert.equal(calls[0].bindingRef,"owner-runtime-binding");
  assert.equal(calls[0].operationRef,"owner-operation");
  assert.equal(calls[0].arguments.app,"com.apple.calculator");
});
test("invalid request and machine override are refused before dispatch",async()=>{
  let count=0;
  const facet=createComputerUseFacet({
    authorize:async()=>grant(true),
    dispatch:async()=>{count++;return {content:[]}},
    recordUncertainEffect:async()=>{},
  });
  for(const params of [
    {name:"cuse_click",arguments:{app:"com.apple.calculator",element_index:9}},
    {name:"cuse_click",arguments:{app:"com.apple.calculator"}},
    {name:"cuse_click",arguments:{app:"com.apple.calculator",x:1}},
    {name:"cuse_click",arguments:{app:"com.apple.calculator",x:1,y:999999}},
    {name:"cuse_list_apps",arguments:{machine:"mini4"}},
    {name:"cuse_get_app_state",arguments:{app:"com.apple.calculator",host:"other"}},
    {name:"cuse_type_text",arguments:{app:"com.apple.calculator",text:"x".repeat(2049)}},
    {name:"cuse_run_shell",arguments:{}},
  ])await assert.rejects(()=>facet.callTool(params,context),/FACET_REFUSED/);
  assert.equal(count,0);
});
test("no write owner recorder means no writable tools or dispatch",async()=>{
  let invoked=false;
  const facet=createComputerUseFacet({
    authorize:async()=>grant(true),dispatch:async()=>{invoked=true;return {content:[]}},
  });
  const names=(await facet.listTools(context)).tools.map(t=>t.name);
  assert.deepEqual(names,["cuse_list_apps","cuse_get_app_state"]);
  await assert.rejects(()=>facet.callTool({name:"cuse_click",arguments:{app:"com.apple.calculator",element_index:"9"}},context),/owner unavailable/);
  assert.equal(invoked,false);
});
test("every action requires a fresh owner grant; denied write is not dispatched",async()=>{
  let authCalls=0,dispatchCalls=0;
  const facet=createComputerUseFacet({
    authorize:async()=>{authCalls++;return null},
    dispatch:async()=>{dispatchCalls++;return {content:[]}},
    recordUncertainEffect:async()=>{},
  });
  await assert.rejects(()=>facet.callTool({
    name:"cuse_click",arguments:{app:"com.apple.calculator",element_index:"9"}
  },context),/owner denied/);
  assert.equal(authCalls,1);assert.equal(dispatchCalls,0);
});
test("confirmed click returns once on the same binding; no retry or auto-route",async()=>{
  let invoked=0;
  const facet=createComputerUseFacet({
    authorize:async()=>grant(true),
    dispatch:async(request)=>{invoked++;assert.equal(request.toolName,"click");return {content:[{type:"text",text:"observed"}]};},
    recordUncertainEffect:async()=>{throw Error("should not report known effect")},
  });
  const result=await facet.callTool({
    name:"cuse_click",arguments:{app:"com.apple.calculator",element_index:"9"}
  },context);
  assert.equal(result.content[0].text,"observed");
  assert.equal(invoked,1);
});
test("lost write result triggers original-owner uncertainty, never retries",async()=>{
  let invoked=0;const records=[];
  const facet=createComputerUseFacet({
    authorize:async()=>grant(true),
    dispatch:async()=>{invoked++;throw Error("network timed out")},
    recordUncertainEffect:async(rec)=>records.push(rec),
  });
  await assert.rejects(()=>facet.callTool({
    name:"cuse_type_text",arguments:{app:"com.apple.calculator",text:"7"}
  },context),/EFFECT_UNKNOWN/);
  assert.equal(invoked,1);assert.equal(records.length,1);
  assert.equal(records[0].bindingRef,"owner-runtime-binding");
  assert.equal(records[0].toolName,"type_text");
});
test("unconfirmed tool error is effect-unknown even when recorder fails",async()=>{
  let invoked=0;
  const facet=createComputerUseFacet({
    authorize:async()=>grant(true),
    dispatch:async()=>{invoked++;return {content:[{type:"text",text:"error"}],isError:true}},
    recordUncertainEffect:async()=>{throw Error("owner unavailable")},
  });
  await assert.rejects(()=>facet.callTool({
    name:"cuse_press_key",arguments:{app:"com.apple.calculator",key:"Return"}
  },context),/EFFECT_UNKNOWN/);
  assert.equal(invoked,1);
});

test("pixel, alternate-button, and multiple click escalation need native owner grants",async()=>{
  const calls=[];
  let current={...grant(true)};
  const facet=createComputerUseFacet({
    authorize:async()=>current,
    dispatch:async(req)=>{calls.push(req);return {content:[]}},
    recordUncertainEffect:async()=>{},
  });
  const args={app:"com.apple.calculator",x:100,y:100};
  await assert.rejects(()=>facet.callTool({name:"cuse_click",arguments:args},context),/coordinate click not owner-authorized/);
  await assert.rejects(()=>facet.callTool({name:"cuse_click",arguments:{
    app:"com.apple.calculator",element_index:"9",mouse_button:"right"
  }},context),/alternate button not owner-authorized/);
  await assert.rejects(()=>facet.callTool({name:"cuse_click",arguments:{
    app:"com.apple.calculator",element_index:"9",click_count:2
  }},context),/multiple clicks not owner-authorized/);
  assert.equal(calls.length,0);
  current={...grant(true),allowCoordinateClick:true};
  await facet.callTool({name:"cuse_click",arguments:args},context);
  assert.equal(calls.length,1);
  assert.deepEqual(calls[0].arguments,args);
});
