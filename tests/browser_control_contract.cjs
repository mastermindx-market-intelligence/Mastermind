"use strict";
const assert = require("node:assert/strict");
const vm = require("node:vm");
const {webcrypto,createHash,randomBytes} = require("node:crypto");
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const {createController,REQUEST_SCHEMA} = require("../integrations/chairman_surfaces/web_sol_extension/browser_control.js");
const hash = value => createHash("sha256").update(value).digest("hex");
const INSTANCE = "a".repeat(64), SESSION = "b".repeat(64), BOOT = "connection-generation-one";
const SNAP = "snapshot-observation-one";
const pageActions = new Set(["click","fill","select","press","scroll","read"]);
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
  // The real browser_page.js dispatch never lets an error escape; fill
  // returns a promise (settled read-back) while everything else answers
  // synchronously. Chrome's executeScript awaits settled results, and the
  // scripting stub below mirrors that, so the fake can model both shapes.
  return message => {
    if(f.state.messageHook) f.state.messageHook(message);
    // A malformed page reply (ok is not a boolean): the controller's own
    // validation throws a bare PAGE_RESPONSE_INVALID — no flags attached.
    if(f.state.invalidResponseOn && message.action===f.state.invalidResponseOn)
      return {ok:"yes",code:"OK"};
    if(message.action==="snapshot") {
      f.state.session=message.session_id;f.state.snapshot=SNAP;f.state.snapshotCount++;
      return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{snapshot_id:SNAP}};
    }
    // diagnostics is exempt from the staleness gate in the real page protocol
    // (validate() short-circuits it before the session/snapshot check).
    if(message.action==="diagnostics") {
      if(Object.keys(message.params||{}).length)return {ok:false,code:"INVALID_REQUEST",effect:"NOT_APPLIED",data:null};
      return {ok:true,code:"OK",effect:"NOT_APPLIED",
        data:{errors:[],error_scope:"fixture",resources:[],content_is_untrusted:true}};
    }
    if(message.session_id!==f.state.session || message.snapshot_id!==f.state.snapshot)
      return {ok:false,code:"STALE_SNAPSHOT",effect:"NOT_APPLIED",data:null};
    if(message.action==="validate")return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{}};
    if(message.action==="validate_focus")return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{}};
    // Fill answers after a settle in production: model the promise shape the
    // real page module now returns, so the controller path proves it settles.
    if(message.action==="fill") {
      f.state.effects.push(["fill"]);f.state.snapshot=null;
      return Promise.resolve({ok:true,code:"OK",effect:"APPLIED",
        data:{refresh_required:true,snapshot_consumed:true,settle_interval_ms:250}});
    }
    // read is a pure read: no effect recorded, snapshot not consumed.
    if(message.action==="read")
      return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{offset:message.params.offset,
        total_characters:0,next_offset:null,content:"",content_is_untrusted:true}};
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
    injectFailure:null, filesFailure:null, worldMissing:false, dispatchFailureOn:null, dispatchFailureText:null, invalidResponseOn:null,
    keyEventDetail:null, captureFunc:false, lastFunc:null, filesInstalls:0,
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
        state.filesInstalls+=1;
        if(state.filesFailure) {const e=new Error(state.filesFailure);throw e;}
        return [{documentId:state.document}];
      }
      assert.equal(options.world,"ISOLATED");assert.equal(typeof options.func,"function");
      if(state.captureFunc) state.lastFunc=options.func;
      if(state.injectFailure) throw new Error(state.injectFailure);
      // executeScript can reject AFTER the func already ran in the page (tab
      // closed, frame removed or navigated by the very click it performed):
      // when the dispatched message's action matches dispatchFailureOn, run the
      // dispatch, then lose the reply. The pre-dispatch validate still succeeds.
      if(state.dispatchFailureOn && options.args[0] && options.args[0].action === state.dispatchFailureOn) {
        try {options.func(...options.args);} finally {throw new Error(state.dispatchFailureText || "frame removed while injecting");}
      }
      // Real Chrome runs the controller's func wrapper inside the page world
      // and awaits a promise the func returns (executeScript resolves with
      // the settled value); model both here.
      globalThis.__MMX_BROWSER_PAGE_V1__ = {dispatch: worldDispatch};
      if(state.worldMissing) delete globalThis.__MMX_BROWSER_PAGE_V1__;
      try {
        const value = options.func(...options.args);
        return [{result: (value && typeof value.then === "function") ? await value : value}];
      }
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
        if(command==="Input.dispatchKeyEvent" && state.keyEventDetail){
          const e=new Error("Input.interprocessHostRenderMetadataMismatch");e.detail=state.keyEventDetail;throw e;}
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
    assert.ok(Array.isArray(status.data.recent_errors.entries),"status reports the worker error ring");
    assert.equal(status.data.recent_errors.entries.length,0);
    assert.equal(status.data.recent_errors.content_is_untrusted,true,"ring is labeled untrusted");
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
  // Fill answers after a settle interval (ruling 13): the page dispatch
  // returns a promise, executeScript resolves with the settled receipt, and
  // the controller forwards it unchanged — no PAGE_RESPONSE_INVALID from an
  // unresolved thenable, no wedged effect.
  {
    const f=fixture();await f.snapshot();
    const result=await f.run(request("fill",{params:{text:"settled"}}));
    assert.equal(result.status,"ACTION_DISPATCHED");assert.equal(result.effect,"APPLIED");
    assert.equal(result.data.settle_interval_ms,250);
    assert.deepEqual(f.state.effects,[["fill"]]);
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
    const f=fixture();await f.snapshot();assert.equal((await f.run(request("close"))).status,"TAB_NOT_BRIDGE_OPENED");
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
  // Detail hygiene: URLs appear as origin+path only (no query, no fragment,
  // however short), whole detail bounded, no page text.
  {
    const f=fixture();
    f.state.injectFailure="cannot script https://allowed.test/very/long/path/with/many/segments?secret=1&more=2 right now";
    const result=await f.snapshot();
    const detail=String(result.data.detail);
    assert.ok(detail.length<=180,`detail bounded: ${detail.length}`);
    const urls=detail.match(/https?:\/\/[^\s]+/g)||[];
    for(const u of urls) assert.ok(!/[?#]/.test(u),`url is origin+path only: ${u}`);
  }
  // A short URL must not slip a query string or fragment through: the cut is
  // origin+path, not a positional 48-character slice.
  {
    const f=fixture();
    f.state.injectFailure="failed https://short.test/p?ticket=abc123 and https://short.test/p#section-2 today";
    const result=await f.snapshot();
    const detail=String(result.data.detail);
    assert.ok(detail.includes("https://short.test/p"),"origin+path kept");
    assert.ok(!detail.includes("ticket="),`query omitted: ${detail}`);
    assert.ok(!detail.includes("abc123"),`query value omitted: ${detail}`);
    assert.ok(!detail.includes("#"),`fragment omitted: ${detail}`);
  }
  // The tab= field itself is origin+path: the fixture tab URL carries a query
  // (?private=omitted) that must never reach the detail.
  {
    const f=fixture();
    f.state.injectFailure="Extension process crashed while injecting";
    const result=await f.snapshot();
    const detail=String(result.data.detail);
    assert.ok(detail.includes("tab=https://allowed.test/page"),`tab= is origin+path: ${detail}`);
    assert.ok(!detail.includes("private=omitted"),`tab= query omitted: ${detail}`);
  }
  // The worker error ring: recorded failures surface in status, capped at 20.
  {
    const f=fixture();f.state.injectFailure="first failure text";
    await f.snapshot();
    f.state.injectFailure=null;
    const status=await f.run(request("status"));
    assert.equal(status.data.recent_errors.entries.length,1);
    const record=status.data.recent_errors.entries[0];
    assert.equal(record.action,"snapshot");assert.equal(record.code,"PAGE_INJECT_FAILED");
    assert.ok(typeof record.at==="string" && /Z$/.test(record.at));
    assert.ok(String(record.detail).includes("first failure text"));
    for(let i=0;i<25;i+=1){
      f.state.injectFailure="burst "+i;
      await f.run(request("snapshot",{nonce:randomBytes(24).toString("hex")}));
    }
    f.state.injectFailure=null;
    const after=await f.run(request("status"));
    assert.equal(after.data.recent_errors.entries.length,20);
    assert.ok(String(after.data.recent_errors.entries[0].detail).includes("burst 5"), "oldest kept record is burst 5");
    assert.ok(String(after.data.recent_errors.entries[19].detail).includes("burst 24"), "newest kept record is burst 24");
    for(const record of after.data.recent_errors.entries) {
      assert.ok(Object.keys(record).every(k=>["at","session_id","action","code","detail"].includes(k)));
      assert.ok(String(record.detail||"").length<=180);
    }
  }
  // The ring never crosses a transport reconnect: a boot-generation change clears it.
  {
    const f=fixture();f.state.injectFailure="first failure text";
    await f.snapshot();
    f.state.injectFailure=null;
    assert.equal((await f.run(request("status"))).data.recent_errors.entries.length,1);
    f.state.boot="connection-generation-two";
    const after=await f.run(request("status",{transport_boot_nonce:f.state.boot}));
    assert.equal(after.data.recent_errors.entries.length,0,"boot change clears the ring");
  }
  // A session is served only its own ring entries, each carrying its session id.
  {
    const f=fixture();f.state.injectFailure="first failure text";
    await f.snapshot();
    f.state.injectFailure=null;
    const other=await f.run(request("status",{session_id:"c".repeat(64)}));
    assert.equal(other.data.recent_errors.entries.length,0,"another session sees none of them");
    const mine=await f.run(request("status"));
    assert.equal(mine.data.recent_errors.entries.length,1,"the failing session still sees its entry");
    assert.equal(mine.data.recent_errors.entries[0].session_id,SESSION,"entries carry the session id");
  }
  // A CDP failure detail is bounded and URL-cut like every other detail.
  {
    const f=fixture();await f.snapshot();
    f.state.keyEventDetail="cdp internal "+("x".repeat(150))+" https://allowed.test/p?secret=1 "+("y".repeat(1400));
    const result=await f.run(request("press",{params:{key:"Enter"}}));
    assert.equal(result.status,"ACTION_EFFECT_UNKNOWN");
    assert.equal(result.effect,"EFFECT_UNKNOWN");
    const detail=String(result.data.detail);
    assert.ok(detail.length<=180,`cdp detail bounded: ${detail.length}`);
    assert.ok(!detail.includes("secret=1"),`cdp detail url-cut: ${detail}`);
    const status=await f.run(request("status"));
    const entries=status.data.recent_errors.entries;
    assert.ok(String(entries[entries.length-1].detail).length<=180,"ring entry bounded too");
    assert.ok(!String(entries[entries.length-1].detail).includes("secret=1"),"ring entry url-cut too");
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
    const entries=status.data.recent_errors.entries;
    assert.equal(entries[entries.length-1].code,"ACTION_EFFECT_UNKNOWN");
  }
  {
    const f=fixture();f.state.dispatchFailureOn="snapshot";
    const result=await f.snapshot();
    assert.equal(result.status,"PAGE_INJECT_FAILED");
    assert.equal(result.effect,"NOT_APPLIED");
  }
  // A pure read whose reply is lost after dispatch is never wedged as
  // EFFECT_UNKNOWN: reads apply nothing, so pagination may safely continue
  // (a read must not become an "uncertain action" that can never repeat).
  {
    const f=fixture();await f.snapshot();
    f.state.dispatchFailureOn="read";
    const lost=await f.run(request("read",{params:{offset:0}}));
    assert.equal(lost.status,"PAGE_INJECT_FAILED");
    assert.equal(lost.effect,"NOT_APPLIED");
    f.state.dispatchFailureOn=null;
    const next=await f.run(request("read",{nonce:randomBytes(24).toString("hex"),params:{offset:0}}));
    assert.equal(next.status,"ACTION_DISPATCHED","the next page read is not blocked");
  }
  // Ruling 15 item 1: the bare PAGE_RESPONSE_INVALID rethrow (the page
  // replied, but the reply shape is invalid — for example a frame swapped
  // between send and answer) carries neither flag, and `possible` must not
  // wedge a pure read as an uncertain action: reads apply nothing, so the
  // read stays NOT_APPLIED and retryable. A write hitting the same rethrow
  // keeps the conservative uncertain verdict.
  {
    const f=fixture();await f.snapshot();
    f.state.invalidResponseOn="read";
    const bad=await f.run(request("read",{params:{offset:0}}));
    assert.equal(bad.status,"PAGE_RESPONSE_INVALID");
    assert.equal(bad.effect,"NOT_APPLIED","a pure read is never uncertain on an invalid reply");
    f.state.invalidResponseOn=null;
    const next=await f.run(request("read",{nonce:randomBytes(24).toString("hex"),params:{offset:0}}));
    assert.equal(next.status,"ACTION_DISPATCHED","the read can be retried at once");
  }
  {
    const f=fixture();await f.snapshot();
    f.state.invalidResponseOn="fill";
    const bad=await f.run(request("fill",{params:{text:"x"}}));
    assert.equal(bad.status,"ACTION_EFFECT_UNKNOWN");
    assert.equal(bad.effect,"EFFECT_UNKNOWN","a write stays conservative on an invalid reply");
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
  // After an applied focus_ref, a lost validate_focus reply must not report
  // the press as NOT_APPLIED: focus moved and the snapshot was consumed.
  {
    const f=fixture();await f.snapshot();
    f.state.dispatchFailureOn="validate_focus";
    const result=await f.run(request("press",{params:{key:"Enter"}}));
    assert.equal(result.status,"ACTION_EFFECT_UNKNOWN");
    assert.equal(result.effect,"EFFECT_UNKNOWN");
    assert.deepEqual(f.state.effects,[["focus"]],"focus applied, key events not provably sent");
  }
  // The injected func is serialized into the page world (executeScript re-parses
  // its source): re-evaluate it exactly that way — from source, in a bare
  // context with no module bindings — and prove its safety net still fires.
  {
    const f=fixture();f.state.captureFunc=true;
    await f.snapshot();
    assert.equal(typeof f.state.lastFunc,"function");
    const source=f.state.lastFunc.toString();
    assert.ok(!/\bboundedDetail\b|\bpublicUrl\b|\bdocuments\b/.test(source),
      "injected func carries no controller-scope names");
    // The page world always provides URL; a bare vm context does not, so hand
    // it in — and a second, URL-less context proves the fallback also cuts.
    const context=vm.createContext({URL});
    vm.runInNewContext("globalThis.__MMX_BROWSER_PAGE_V1__={dispatch:function(){throw new Error('world died at https://short.test/p?token=z1')}}",context);
    const deserialized=vm.runInNewContext("("+source+")",context);
    const failed=deserialized({action:"click"});
    assert.equal(failed.ok,false);assert.equal(failed.code,"PAGE_DISPATCH_FAILED");
    assert.equal(failed.effect,"EFFECT_UNKNOWN");
    assert.ok(String(failed.data.detail).includes("world died"),"inlined bounder keeps native text");
    assert.ok(!String(failed.data.detail).includes("token="),`inlined bounder cuts urls: ${failed.data.detail}`);
    assert.ok(String(failed.data.detail).length<=180);
    const failedRead=deserialized({action:"snapshot"});
    assert.equal(failedRead.code,"PAGE_DISPATCH_FAILED");assert.equal(failedRead.effect,"NOT_APPLIED");
    const bareContext=vm.createContext({});
    vm.runInNewContext("globalThis.__MMX_BROWSER_PAGE_V1__={dispatch:function(){throw new Error('died at https://short.test/p?token=z2')}}",bareContext);
    const withoutUrl=vm.runInNewContext("("+source+")",bareContext)({action:"click"});
    assert.equal(withoutUrl.code,"PAGE_DISPATCH_FAILED");
    assert.ok(!String(withoutUrl.data.detail).includes("token="),`fallback cut works without URL: ${withoutUrl.data.detail}`);
  }
  // diagnostics is callable without any prior snapshot and survives a dead page world.
  {
    const f=fixture();
    const result=await f.run(request("diagnostics",{snapshot_id:null}));
    assert.equal(result.status,"OK");
    assert.equal(result.data.page_world,"ok");
    assert.ok(Array.isArray(result.data.errors));
    assert.ok(Array.isArray(result.data.recent_errors.entries));
    const compat=await f.run(request("diagnostics")); // still accepts a snapshot id
    assert.equal(compat.status,"OK");
    assert.equal(result.data.content_is_untrusted,true,"page-authored errors[] labeled untrusted");
  }
  {
    const f=fixture();f.state.injectFailure="Missing host permission for the tab";
    const result=await f.run(request("diagnostics",{snapshot_id:null}));
    assert.equal(result.status,"OK");
    assert.equal(result.data.page_world,"unavailable");
    assert.equal(result.data.page_error,"SITE_PERMISSION_REQUIRED");
    assert.ok(result.data.recent_errors.entries.length>=1);
  }
  // A snapshot-free diagnostics must not re-arm the post-reconnect mutation
  // gate (its pageWorld install runs, but nothing persists into documents),
  // and it consumes none of the 128 documents slots (atk#5): a later
  // mutation with the pre-disconnect snapshot stays STALE_SNAPSHOT.
  {
    const f=fixture();await f.snapshot();
    f.state.boot="connection-generation-two";
    await f.run(request("status",{transport_boot_nonce:f.state.boot})); // reconnect clears documents
    const installsBefore=f.state.filesInstalls;
    const d=await f.run(request("diagnostics",{transport_boot_nonce:f.state.boot}));
    assert.equal(d.status,"OK");assert.equal(d.data.page_world,"ok");
    assert.ok(f.state.filesInstalls>installsBefore,"the pageWorld injection did run");
    const blocked=await f.run(request("click",{transport_boot_nonce:f.state.boot}));
    assert.equal(blocked.status,"STALE_SNAPSHOT","diagnostics did not re-arm the gate");
    assert.equal(blocked.effect,"NOT_APPLIED");
    assert.equal(f.state.effects.length,0,"nothing dispatched");
    // A fresh snapshot after the reconnect re-arms the gate the intended way.
    const fresh=await f.run(request("snapshot",{transport_boot_nonce:f.state.boot}));
    assert.equal(fresh.status,"OK");
    const click=await f.run(request("click",{transport_boot_nonce:f.state.boot}));
    assert.equal(click.effect,"APPLIED");
  }
  console.log("browser controller contract passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
