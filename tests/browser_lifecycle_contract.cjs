"use strict";
const assert=require("node:assert/strict");
const {webcrypto,createHash,randomBytes}=require("node:crypto");
globalThis.crypto??=webcrypto;
const CDP=require("../integrations/chairman_surfaces/web_sol_extension/browser_cdp.js");
const CONTROL=require("../integrations/chairman_surfaces/web_sol_extension/browser_control.js");
const hash=x=>createHash("sha256").update(x).digest("hex");
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const URL="https://fixture.test/",SESSION="b".repeat(64),INSTANCE="a".repeat(64);
function fixture(){
  const state={boot:"connection-generation-one",attach:0,detach:0,sends:[],downloads:0,targets:true,
    grant:null,attachHook:null,detachHook:null,sendHook:null,pageHook:null};
  const listeners={};
  const api={runtime:{getManifest:()=>({version:"0.4.1"}),getURL:leaf=>"chrome-extension://fixture/"+leaf},
    action:{setBadgeText:async()=>{}},
    permissions:{contains:async()=>true,onRemoved:{addListener:fn=>{listeners.permission=fn;}}},
    alarms:{create:()=>{},onAlarm:{addListener:()=>{}}},
    downloads:{download:async()=>{state.downloads++;return 99;}},
    tabs:{get:async()=>({id:1,url:URL,windowId:1}),query:async()=>[{id:1,url:URL}],
      onRemoved:{addListener:()=>{}},sendMessage:async(_id,m)=>{
        if(state.pageHook)await state.pageHook(m);
        return {ok:true,code:"OK",effect:"NOT_APPLIED",data:m.action==="snapshot"?{snapshot_id:"snapshot-observation-one"}:{}};
      }},
    scripting:{executeScript:async()=>[{documentId:"document-one"}]},
    debugger:{onEvent:{addListener:fn=>{listeners.event=fn;}},onDetach:{addListener:fn=>{listeners.detach=fn;}},
      attach:async()=>{state.attach++;if(state.attachHook)return state.attachHook();},
      detach:async()=>{state.detach++;if(state.detachHook)return state.detachHook();},
      getTargets:async()=>[{tabId:1,attached:state.targets}],
      sendCommand:async(_target,method,params)=>{
        state.sends.push(method);if(state.sendHook){const v=await state.sendHook(method,params);if(v!==undefined)return v;}
        if(method==="Page.getFrameTree")return {frameTree:{frame:{id:"main",url:URL,loaderId:"loader-one"}}};
        return {};
      }}
  };
  const host={current:r=>{if(r.transport_boot_nonce!==state.boot)throw Error("CONNECTION_CHANGED");},
    connectionActive:boot=>state.boot===boot,
    tabFor:async r=>{host.current(r);return {id:1,url:URL};},
    granted:async(url,extra)=>state.grant?state.grant(url,extra):true};
  const cdp=CDP.create(api,host);
  const req=(action,params={},boot=state.boot)=>({action,params,tab_id:1,session_id:SESSION,transport_boot_nonce:boot});
  const run=(action,params={},boot=state.boot)=>cdp.execute(req(action,params,boot),()=>{});
  return {state,api,host,cdp,req,run,listeners};
}
async function controllerFixture(){
  const f=fixture();const controller=CONTROL.createController(f.api,INSTANCE,()=>f.state.boot);
  const request=(action,params={})=>({schema:CONTROL.REQUEST_SCHEMA,adapter_instance_id:INSTANCE,session_id:SESSION,
    operation_key:"lifecycle-proof",nonce:randomBytes(24).toString("hex"),transport_boot_nonce:f.state.boot,action,
    tab_id:action==="status"?null:1,url_fingerprint:action==="status"?null:hash(URL),
    snapshot_id:["status","snapshot","cdp_status","cdp_detach","frames"].includes(action)?null:"snapshot-observation-one",
    ref:null,params,issued_at:new Date().toISOString(),expires_at:new Date(Date.now()+45000).toISOString()});
  const run=(a,p)=>controller.run(request(a,p),f.state.boot);
  await run("snapshot");return {...f,controller,run};
}

(async()=>{
  const cases=[];
  {
    const f=fixture();f.state.attachHook=()=>Promise.reject(Error("Another debugger is already attached to the tab"));
    await assert.rejects(f.run("cdp_attach"),e=>e.knownNotApplied&&e.message==="CDP_ALREADY_ATTACHED");
    assert.equal(f.cdp.has(1),false);assert.match(f.cdp.diagnostics().last_attach_failure.detail,/Another debugger/);
    cases.push("attach rejection preserves bounded Chrome diagnosis");
  }
  {
    const f=fixture();await f.run("cdp_attach");const wait=deferred();f.state.detachHook=()=>wait.promise;
    const a=f.cdp.releaseAll(),b=f.cdp.releaseAll();await tick();assert.equal(f.state.detach,1);
    wait.reject(Error("detach reply lost"));assert.equal((await a)[0].released,false);assert.equal((await b)[0].released,false);
    const before=f.state.sends.length;
    await assert.rejects(f.cdp.withDebugger(f.req("press"),send=>send("Input.dispatchKeyEvent",{})),/RECONCILIATION/);
    assert.equal(f.state.sends.length,before);
    const result=await f.run("cdp_detach");assert.equal(result.effect,"EFFECT_UNKNOWN");assert.equal(result.status,"ACTION_EFFECT_UNKNOWN");
    assert.equal(f.state.detach,1);f.state.targets=false;
    assert.equal((await f.run("cdp_detach")).data.released,true);assert.equal(f.state.detach,1);assert.equal(f.cdp.has(1),false);
    cases.push("concurrent cleanup, quarantine, uncertainty and read-only reconciliation");
  }
  {
    const f=fixture();const grant=deferred();let first=true;
    f.state.grant=(_url,extra)=>extra?.includes("debugger")&&first?(first=false,grant.promise):true;
    const oldBoot=f.state.boot,old=f.run("cdp_attach");await tick();
    f.state.boot="connection-generation-two";await f.cdp.reset();await f.run("cdp_attach");grant.resolve(true);
    await assert.rejects(old,/CONNECTION_CHANGED/);assert.equal(f.state.attach,1);
    assert.equal((await f.run("cdp_status")).data.owned,true);assert.notEqual(oldBoot,f.state.boot);await f.cdp.releaseAll();
    cases.push("old permission continuation cannot replace new profile connection");
  }
  {
    const f=fixture();const pending=deferred();f.state.attachHook=()=>pending.promise;
    const call=f.run("cdp_attach");await tick();assert.equal(f.cdp.has(1),true);
    f.state.boot="connection-generation-two";const cleanup=f.cdp.reset();pending.resolve();
    await assert.rejects(call);await cleanup;assert.equal(f.state.detach,1);assert.deepEqual(f.state.sends,[]);
    assert.equal(f.cdp.has(1),false);cases.push("pending attach is fenced and cleaned once after disconnect");
  }
  {
    const f=fixture();await f.run("cdp_attach");const wait=deferred();f.state.grant=()=>wait.promise;
    f.listeners.event({tabId:1},"Network.requestWillBeSent",{requestId:"r",request:{url:URL},type:"Document"});await tick();
    f.state.detachHook=()=>Promise.reject(Error("detach unavailable"));f.state.boot="connection-generation-two";await f.cdp.reset();
    wait.resolve(true);await tick();await tick();assert.equal(f.cdp.uiStatus()[0].events,0);
    assert.equal(f.cdp.uiStatus()[0].invalidated,true);cases.push("queued network event cannot repopulate invalidated state");
  }
  {
    const f=fixture();await f.run("cdp_attach");const grant=deferred();f.state.grant=(_url,extra)=>extra?.includes("downloads")?grant.promise:true;
    const call=f.run("download",{url:URL});await tick();f.state.boot="connection-generation-two";await f.cdp.reset();grant.resolve(true);
    await assert.rejects(call,/CONNECTION_CHANGED/);assert.equal(f.state.downloads,0);
    cases.push("download permission wait cannot cross a disconnected session");
  }
  {
    const f=fixture();await f.run("cdp_attach");f.api.extension={isAllowedFileSchemeAccess:async()=>false};
    const count=f.state.sends.length;let effects=0;
    await assert.rejects(f.cdp.execute(f.req("upload",{ref:"n-fixture",files:["/fixture.txt"]}),()=>effects++),/UPLOAD_FILE_ACCESS_REQUIRED/);
    assert.equal(effects,0);assert.equal(f.state.sends.length,count);await f.cdp.releaseAll();
    cases.push("Chrome file permission is checked before upload dispatch");
  }
  {
    const f=fixture();f.state.sendHook=async method=>{if(method==="Target.setAutoAttach"){f.state.boot="connection-generation-two";await f.cdp.reset();}};
    await assert.rejects(f.run("cdp_attach"));assert.equal(f.state.detach,1);
    cases.push("optional frame initialization cannot turn a lost attachment into success");
  }
  {
    const f=await controllerFixture();assert.equal((await f.run("cdp_attach",{})).status,"OK");
    const pending=deferred();f.state.sendHook=method=>method==="Page.getFrameTree"?pending.promise:undefined;
    const old=f.run("frames",{});await tick();f.state.boot="connection-generation-two";await f.controller.transportDisconnected();
    assert.equal((await f.run("status")).status,"OK");
    const page=deferred();f.state.pageHook=()=>page.promise;const fresh=f.run("snapshot");await tick();
    pending.resolve({frameTree:{frame:{id:"main",url:URL}}});await old;
    assert.equal((await f.run("status")).status,"BUSY");page.resolve();await fresh;
    assert.equal((await f.run("status")).status,"OK");
    cases.push("old request cannot hold or clear new connection busy token");
  }
  console.log(JSON.stringify({state:"PASS",count:cases.length,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
