"use strict";
const assert = require("node:assert/strict");
const {webcrypto,createHash,randomBytes} = require("node:crypto");
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const {createController,REQUEST_SCHEMA} = require("../integrations/chairman_surfaces/web_sol_extension/browser_control.js");
const hash = value => createHash("sha256").update(value).digest("hex");
const INSTANCE = "a".repeat(64), SESSION = "b".repeat(64), BOOT = "connection-generation-one";
const SNAP = "snapshot-observation-one";
const pageActions = new Set(["click","fill","select","press","scroll"]);
function request(action, changes={}) {
  const hasTab = !["status","tabs","open"].includes(action);
  return {schema:REQUEST_SCHEMA,adapter_instance_id:INSTANCE,session_id:SESSION,
    operation_key:"browser-contract",nonce:randomBytes(24).toString("hex"),transport_boot_nonce:BOOT,action,
    tab_id:hasTab ? 1 : null,url_fingerprint:hasTab ? hash("https://allowed.test/page?private=omitted") : null,
    snapshot_id:hasTab && !["snapshot","diagnostics"].includes(action) ? SNAP : null,ref:pageActions.has(action)?"e1":null,
    params:{},issued_at:new Date().toISOString(),expires_at:new Date(Date.now()+45000).toISOString(),...changes};
}
// The isolated-world page object the real func-injection finds as
// globalThis.__MMX_BROWSER_PAGE_V1__. Implements the page protocol inline.
function pageWorldDispatch(f) {
  // The real browser_page.js dispatch is synchronous and never lets an error
  // escape; the fake mirrors that so the controller wrapper sees production shape.
  return message => {
    if(f.state.messageHook) f.state.messageHook(message);
    if(message.action==="snapshot") {
      f.state.session=message.session_id;f.state.snapshot=SNAP;f.state.snapshotCount++;
      return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{snapshot_id:SNAP}};
    }
    if(message.session_id!==f.state.session || message.snapshot_id!==f.state.snapshot)
      return {ok:false,code:"STALE_SNAPSHOT",effect:"NOT_APPLIED",data:null};
    if(message.action==="validate")return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{}};
    if(message.action==="diagnostics")return {ok:true,code:"OK",effect:"NOT_APPLIED",
      data:{errors:[],error_scope:"fixture",resources:[]}};
    if(message.action==="validate_focus")return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{}};
    if(message.action==="focus_ref") {
      f.state.effects.push(["focus"]);
      if(f.state.focusFailure==="lost")throw Error("lost focus reply");
      if(f.state.focusFailure==="uncertain")return {ok:false,code:"ACTION_EFFECT_UNKNOWN",effect:"EFFECT_UNKNOWN",data:null};
      if(f.state.focusFailure==="wrong")return {ok:false,code:"FOCUS_NOT_CONFIRMED",effect:"APPLIED",data:null};
      return {ok:true,code:"OK",effect:"APPLIED",data:{focus_token:"focus-preparation-token"}};
    }
    f.state.effects.push([message.action]);f.state.snapshot=null;
    return {ok:true,code:"OK",effect:"APPLIED",data:{refresh_required:true}};
  };
}
function fixture() {
  const state = {boot:BOOT, effects:[], permissions:new Set(["tabs","scripting","debugger"]),
    sites:new Set(["https://allowed.test/*"]), document:"document-one", session:SESSION, snapshot:null,
    snapshotCount:0, messageHook:null, permissionHook:null, focusFailure:null, detachFailure:false,
    injectFailure:null, filesFailure:null, worldMissing:false, dispatchFailureOn:null, dispatchFailureText:null,
    history:{currentIndex:1,entries:[{id:10,url:"https://denied.test/"},{id:11,url:"https://allowed.test/page"}]}};
  const f = {state};
  const worldDispatch = pageWorldDispatch(f);
  const tabs=new Map([[1,{id:1,windowId:7,url:"https://allowed.test/page?private=omitted",title:"Fixture",active:true}],
    [2,{id:2,windowId:7,url:"https://allowed.test/private",incognito:true}],
    [3,{id:3,windowId:7,url:"https://denied.test/"}], [4,{id:4,url:"chrome://settings/"}]]);
  const api={
    permissions:{contains:async query=>{
      if(state.permissionHook)state.permissionHook(query);
      return (query.permissions||[]).every(p=>state.permissions.has(p)) && (query.origins||[]).every(p=>state.sites.has(p));}},
    runtime:{getURL:leaf=>"chrome-extension://fixture/"+leaf,getManifest:()=>({version:"0.3.0"})},
    scripting:{executeScript:async options=>{
      if(options.files){
        assert.deepEqual(options.files,["browser_page.js"]);assert.equal(options.world,"ISOLATED");
        if(state.filesFailure) {const e=new Error(state.filesFailure);throw e;}
        return [{documentId:state.document}];
      }
      assert.equal(options.world,"ISOLATED");assert.equal(typeof options.func,"function");
      if(state.injectFailure) throw new Error(state.injectFailure);
      // executeScript can reject AFTER the func already ran in the page (tab
      // closed, frame removed or navigated by the very click it performed):
      // when the dispatched message's action matches dispatchFailureOn, run the
      // dispatch, then lose the reply. The pre-dispatch validate still succeeds.
      if(state.dispatchFailureOn && options.args[0] && options.args[0].action === state.dispatchFailureOn) {
        try {options.func(...options.args);} finally {throw new Error(state.dispatchFailureText || "frame removed while injecting");}
      }
      // Real Chrome runs the controller's func wrapper inside the page world;
      // model that here by installing the fake page object on globalThis.
      globalThis.__MMX_BROWSER_PAGE_V1__ = {dispatch: worldDispatch};
      if(state.worldMissing) delete globalThis.__MMX_BROWSER_PAGE_V1__;
      try { return [{result: options.func(...options.args)}]; }
      finally { if(!state.worldMissing) globalThis.__MMX_BROWSER_PAGE_V1__ = {dispatch: worldDispatch}; }
    }},
    tabs:{
      get:async id=>{if(!tabs.has(id))throw Error("missing");return {...tabs.get(id)};},
      query:async()=>[...tabs.values()],
      create:async options=>{state.effects.push(["open",options]);const tab={id:5,windowId:7,...options};tabs.set(5,tab);return tab;},
      update:async(id,value)=>{state.effects.push(["update",id,value]);Object.assign(tabs.get(id),value);},
      reload:async id=>state.effects.push(["reload",id]),
      remove:async id=>{state.effects.push(["close",id]);tabs.delete(id);},
      onRemoved:{addListener:()=>{}},
      sendMessage:async()=>{throw Error("tabs.sendMessage is no longer used by the controller");}
    },
    windows:{update:async(...args)=>state.effects.push(["window",...args])},
    debugger:{
      attach:async()=>{}, detach:async()=>{if(state.detachFailure)throw Error("lost detach");},
      sendCommand:async(target,command,params)=>{
        assert.deepEqual(target,{tabId:1});
        if(command==="Page.getNavigationHistory")return state.history;
        if(command==="Page.getLayoutMetrics")return {cssVisualViewport:{pageX:0,pageY:0,clientWidth:1600,clientHeight:1200}};
        if(command==="Page.captureScreenshot")return {data:"/9j/2Q=="};
        state.effects.push([command,params]);return {};
      }
    }
  };
  const controller=createController(api,INSTANCE,()=>state.boot);
  f.tabs=tabs;f.api=api;f.run=r=>controller.run(r,state.boot);f.snapshot=()=>controller.run(request("snapshot"),state.boot);
  return f;
}

(async()=>{
  {
    const f=fixture();const status=await f.run(request("status"));
    assert.equal(status.data.connection_id,BOOT);assert.equal(status.data.control_enabled,true);
    assert.equal(status.data.package_version,"0.3.0");
    assert.ok(Array.isArray(status.data.recent_errors),"status reports the worker error ring");
    assert.equal(status.data.recent_errors.length,0);
    const tabs=await f.run(request("tabs"));assert.equal(tabs.data.tabs.length,1);
    assert.equal(tabs.data.tabs[0].url,"https://allowed.test/page");assert.equal(tabs.data.excluded_count,3);
    f.state.permissions.delete("tabs");assert.equal((await f.run(request("tabs"))).status,"BROWSER_PERMISSION_REQUIRED");
    assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();await f.snapshot();const click=request("click");
    const first=await f.run(click);assert.equal(first.effect,"APPLIED");
    assert.equal((await f.run(click)).status,"NONCE_REUSED");
    assert.equal((await f.run(request("click"))).status,"STALE_SNAPSHOT");
    assert.deepEqual(f.state.effects,[["click"]]);
  }
  {
    const f=fixture();await f.snapshot();f.tabs.get(1).url="https://allowed.test/changed";
    assert.equal((await f.run(request("click"))).status,"TARGET_CHANGED");assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();await f.snapshot();f.state.boot="connection-generation-two";
    await f.run(request("status",{transport_boot_nonce:f.state.boot}));
    const result=await f.run(request("click",{transport_boot_nonce:f.state.boot}));
    assert.equal(result.status,"STALE_SNAPSHOT");assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();await f.snapshot();f.state.messageHook=message=>{
      if(message.action==="validate")f.state.boot="connection-generation-two";};
    const result=await f.run(request("click"));assert.equal(result.effect,"NOT_APPLIED");
    assert.equal(result.status,"CONNECTION_CHANGED");assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();await f.snapshot();const original=Date.now;
    f.state.permissionHook=()=>{Date.now=()=>original()+60000;};
    try {const result=await f.run(request("click"));assert.equal(result.status,"REQUEST_EXPIRED");assert.equal(result.effect,"NOT_APPLIED");}
    finally {Date.now=original;}
    assert.equal(f.state.effects.length,0);
  }
  for(const failure of ["lost","uncertain","wrong"]) {
    const f=fixture();await f.snapshot();f.state.focusFailure=failure;
    const result=await f.run(request("press",{params:{key:"Enter"}}));
    assert.equal(result.effect,"EFFECT_UNKNOWN");assert.deepEqual(f.state.effects,[["focus"]]);
  }
  {
    const f=fixture();await f.snapshot();f.state.messageHook=message=>{
      if(message.action==="validate_focus")throw Error("same URL document replaced");};
    const result=await f.run(request("press",{params:{key:"Enter"}}));
    assert.equal(result.effect,"EFFECT_UNKNOWN");assert.deepEqual(f.state.effects,[["focus"]]);
  }
  {
    const f=fixture();await f.snapshot();const result=await f.run(request("press",{params:{key:"Enter"}}));
    assert.equal(result.effect,"APPLIED");assert.equal(f.state.effects[1][0],"Input.dispatchKeyEvent");
    assert.equal(f.state.effects[1][1].type,"keyDown");assert.equal(f.state.effects[2][1].type,"keyUp");
  }
  {
    const f=fixture();await f.snapshot();const result=await f.run(request("back"));
    assert.equal(result.status,"SITE_PERMISSION_REQUIRED");assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();await f.snapshot();const result=await f.run(request("screenshot"));
    assert.equal(result.status,"OK");assert.equal(result.data.mime_type,"image/jpeg");
    f.state.detachFailure=true;await f.run(request("screenshot"));
    f.state.detachFailure=false;assert.equal((await f.run(request("screenshot"))).status,"DEBUGGER_RECONCILIATION_REQUIRED");
  }
  {
    const f=fixture();await f.snapshot();assert.equal((await f.run(request("close"))).status,"TAB_NOT_CREATED_BY_SESSION");
    const opened=await f.run(request("open",{params:{url:"https://allowed.test/new"}}));assert.equal(opened.effect,"APPLIED");
    const tab={tab_id:5,url_fingerprint:hash("https://allowed.test/new")};
    await f.run(request("snapshot",tab));assert.equal((await f.run(request("close",tab))).effect,"APPLIED");
  }
  // Opaque-failure contract: a native rejection must never collapse to a bare
  // BROWSER_UNAVAILABLE. Host-permission texts map to SITE_PERMISSION_REQUIRED.
  {
    const f=fixture();f.state.injectFailure="Missing host permission for the tab";
    const result=await f.snapshot();
    assert.equal(result.status,"SITE_PERMISSION_REQUIRED");
    assert.equal(result.effect,"NOT_APPLIED");
    assert.ok(String(result.data.detail).includes("Missing host permission"),"detail keeps native text");
    const again=await f.run(request("snapshot",{nonce:randomBytes(24).toString("hex")}));
    assert.equal(again.status,"SITE_PERMISSION_REQUIRED");assert.equal(again.effect,"NOT_APPLIED");
  }
  // Any other native text keeps its own code and a bounded detail.
  {
    const f=fixture();f.state.injectFailure="Extension process crashed while injecting";
    const result=await f.snapshot();
    assert.equal(result.status,"PAGE_INJECT_FAILED");
    assert.equal(result.effect,"NOT_APPLIED");
    assert.ok(/Extension process crashed/.test(String(result.data.detail)));
    assert.ok(String(result.data.detail).length<=180);
  }
  // A recycled page world is re-injected once for read actions, then reports.
  {
    const f=fixture();f.state.worldMissing=true;
    const result=await f.snapshot();
    assert.equal(f.state.snapshotCount>=1 || result.status!=="BROWSER_UNAVAILABLE",true);
    f.state.worldMissing=false;f.state.injectFailure="Cannot access contents of the page";
    const denied=await f.run(request("snapshot",{nonce:randomBytes(24).toString("hex")}));
    assert.equal(denied.status,"SITE_PERMISSION_REQUIRED");
  }
  // Detail hygiene: no URL beyond 48 characters, whole detail bounded, no page text.
  {
    const f=fixture();
    f.state.injectFailure="cannot script https://allowed.test/very/long/path/with/many/segments?secret=1&more=2 right now";
    const result=await f.snapshot();
    const detail=String(result.data.detail);
    assert.ok(detail.length<=180,`detail bounded: ${detail.length}`);
    const urls=detail.match(/https?:\/\/[^\s]+/g)||[];
    for(const u of urls) assert.ok(u.length<=48,`url truncated to 48: ${u}`);
  }
  // The worker error ring: recorded failures surface in status, capped at 20.
  {
    const f=fixture();f.state.injectFailure="first failure text";
    await f.snapshot();
    f.state.injectFailure=null;
    const status=await f.run(request("status"));
    assert.equal(status.data.recent_errors.length,1);
    const record=status.data.recent_errors[0];
    assert.equal(record.action,"snapshot");assert.equal(record.code,"PAGE_INJECT_FAILED");
    assert.ok(typeof record.at==="string" && /Z$/.test(record.at));
    assert.ok(String(record.detail).includes("first failure text"));
    for(let i=0;i<25;i+=1){
      f.state.injectFailure="burst "+i;
      await f.run(request("snapshot",{nonce:randomBytes(24).toString("hex")}));
    }
    f.state.injectFailure=null;
    const after=await f.run(request("status"));
    assert.equal(after.data.recent_errors.length,20);
    assert.ok(String(after.data.recent_errors[0].detail).includes("burst 5"), "oldest kept record is burst 5");
    assert.ok(String(after.data.recent_errors[19].detail).includes("burst 24"), "newest kept record is burst 24");
    for(const record of after.data.recent_errors) {
      assert.ok(Object.keys(record).every(k=>["at","action","code","detail"].includes(k)));
      assert.ok(String(record.detail||"").length<=180);
    }
  }
  // A dispatch that ran in the page but whose reply was lost is UNCERTAIN for a
  // mutation (the click may have landed: never invite a repeat) and safely
  // NOT_APPLIED for a read. The pre-dispatch validate succeeds in both cases.
  {
    const f=fixture();await f.snapshot();
    f.state.dispatchFailureOn="click";
    const result=await f.run(request("click"));
    assert.equal(result.status,"ACTION_EFFECT_UNKNOWN");
    assert.equal(result.effect,"EFFECT_UNKNOWN");
    assert.ok(String(result.data.detail).includes("frame removed"),"detail keeps native text");
    assert.deepEqual(f.state.effects,[["click"]],"the page world did run the click");
    const status=await f.run(request("status"));
    assert.equal(status.data.recent_errors[status.data.recent_errors.length-1].code,"ACTION_EFFECT_UNKNOWN");
  }
  {
    const f=fixture();f.state.dispatchFailureOn="snapshot";
    const result=await f.snapshot();
    assert.equal(result.status,"PAGE_INJECT_FAILED");
    assert.equal(result.effect,"NOT_APPLIED");
  }
  // The pre-dispatch failures stay NOT_APPLIED (nothing was sent).
  {
    const f=fixture();await f.snapshot();
    f.state.injectFailure="Extension process crashed while injecting";
    const result=await f.run(request("click"));
    assert.equal(result.status,"PAGE_INJECT_FAILED");
    assert.equal(result.effect,"NOT_APPLIED");
    assert.deepEqual(f.state.effects,[],"nothing dispatched");
  }
  // diagnostics is callable without any prior snapshot and survives a dead page world.
  {
    const f=fixture();
    const result=await f.run(request("diagnostics",{snapshot_id:null}));
    assert.equal(result.status,"OK");
    assert.equal(result.data.page_world,"ok");
    assert.ok(Array.isArray(result.data.errors));
    assert.ok(Array.isArray(result.data.recent_errors));
    const compat=await f.run(request("diagnostics")); // still accepts a snapshot id
    assert.equal(compat.status,"OK");
  }
  {
    const f=fixture();f.state.injectFailure="Missing host permission for the tab";
    const result=await f.run(request("diagnostics",{snapshot_id:null}));
    assert.equal(result.status,"OK");
    assert.equal(result.data.page_world,"unavailable");
    assert.equal(result.data.page_error,"SITE_PERMISSION_REQUIRED");
    assert.ok(result.data.recent_errors.length>=1);
  }
  console.log("browser controller contract passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
