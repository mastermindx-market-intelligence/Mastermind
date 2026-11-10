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
    snapshot_id:hasTab && action !== "snapshot" ? SNAP : null,ref:pageActions.has(action)?"e1":null,
    params:{},issued_at:new Date().toISOString(),expires_at:new Date(Date.now()+45000).toISOString(),...changes};
}
function fixture() {
  const state = {boot:BOOT, effects:[], permissions:new Set(["tabs","scripting","debugger"]),
    sites:new Set(["https://allowed.test/*"]), document:"document-one", session:SESSION, snapshot:null,
    snapshotCount:0, messageHook:null, permissionHook:null, focusFailure:null, detachFailure:false,
    history:{currentIndex:1,entries:[{id:10,url:"https://denied.test/"},{id:11,url:"https://allowed.test/page"}]}};
  const tabs=new Map([[1,{id:1,windowId:7,url:"https://allowed.test/page?private=omitted",title:"Fixture",active:true}],
    [2,{id:2,windowId:7,url:"https://allowed.test/private",incognito:true}],
    [3,{id:3,windowId:7,url:"https://denied.test/"}], [4,{id:4,url:"chrome://settings/"}]]);
  const api={
    permissions:{contains:async query=>{
      if(state.permissionHook)state.permissionHook(query);
      return (query.permissions||[]).every(p=>state.permissions.has(p)) && (query.origins||[]).every(p=>state.sites.has(p));}},
    runtime:{getURL:leaf=>"chrome-extension://fixture/"+leaf,getManifest:()=>({version:"0.3.0"})},
    scripting:{executeScript:async options=>{
      assert.deepEqual(options.files,["browser_page.js"]);assert.equal(options.world,"ISOLATED");
      return [{documentId:state.document}];}},
    tabs:{
      get:async id=>{if(!tabs.has(id))throw Error("missing");return {...tabs.get(id)};},
      query:async()=>[...tabs.values()],
      create:async options=>{state.effects.push(["open",options]);const tab={id:5,windowId:7,...options};tabs.set(5,tab);return tab;},
      update:async(id,value)=>{state.effects.push(["update",id,value]);Object.assign(tabs.get(id),value);},
      reload:async id=>state.effects.push(["reload",id]),
      remove:async id=>{state.effects.push(["close",id]);tabs.delete(id);},
      onRemoved:{addListener:()=>{}},
      sendMessage:async(id,message,options)=>{
        assert.equal(options.documentId,state.document,"must use observed document");
        if(state.messageHook)await state.messageHook(message);
        if(message.action==="snapshot") {
          state.session=message.session_id;state.snapshot=SNAP;state.snapshotCount++;
          return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{snapshot_id:SNAP}};
        }
        if(message.session_id!==state.session || message.snapshot_id!==state.snapshot)
          return {ok:false,code:"STALE_SNAPSHOT",effect:"NOT_APPLIED",data:null};
        if(message.action==="validate")return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{}};
        if(message.action==="validate_focus")return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{}};
        if(message.action==="focus_ref") {
          state.effects.push(["focus"]);
          if(state.focusFailure==="lost")throw Error("lost focus reply");
          if(state.focusFailure==="uncertain")return {ok:false,code:"ACTION_EFFECT_UNKNOWN",effect:"EFFECT_UNKNOWN",data:null};
          if(state.focusFailure==="wrong")return {ok:false,code:"FOCUS_NOT_CONFIRMED",effect:"APPLIED",data:null};
          return {ok:true,code:"OK",effect:"APPLIED",data:{focus_token:"focus-preparation-token"}};
        }
        state.effects.push([message.action]);state.snapshot=null;
        return {ok:true,code:"OK",effect:"APPLIED",data:{refresh_required:true}};
      }
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
  return {state,tabs,api,run:r=>controller.run(r,state.boot),snapshot:()=>controller.run(request("snapshot"),state.boot)};
}

(async()=>{
  {
    const f=fixture();const status=await f.run(request("status"));
    assert.equal(status.data.connection_id,BOOT);assert.equal(status.data.control_enabled,true);
    assert.equal(status.data.package_version,"0.3.0");
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
  for (const [message,category] of [
    ["Cannot access contents of url https://allowed.test/private?secret=value", "ACCESS_REJECTED"],
    ["Could not load file: browser_page.js", "SCRIPT_UNAVAILABLE"],
    ["Extension context invalidated.", "CONTEXT_INVALIDATED"],
    ["No frame with id 0 in tab 1", "DOCUMENT_UNAVAILABLE"],
    ["unexpected failure with private data", "API_REJECTED"]
  ]) {
    const f=fixture();let calls=0;
    f.api.scripting.executeScript=async()=>{calls++;throw Error(message);};
    const result=await f.snapshot();
    assert.equal(calls,1,"failed injection must not be replayed");
    assert.equal(result.status,"BROWSER_UNAVAILABLE");assert.equal(result.effect,"NOT_APPLIED");
    assert.deepEqual(result.data,{detail:{stage:"SCRIPT_INJECTION",api:"chrome.scripting.executeScript",category}});
    assert.ok(!JSON.stringify(result).includes(message));assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();delete f.api.scripting;
    const result=await f.snapshot();
    assert.equal(result.data.detail.category,"API_UNAVAILABLE");assert.equal(result.effect,"NOT_APPLIED");
  }
  {
    const f=fixture();let calls=0;
    f.state.messageHook=()=>{calls++;throw Error("Could not establish connection. Receiving end does not exist.");};
    const result=await f.snapshot();assert.equal(calls,1);
    assert.equal(result.status,"BROWSER_UNAVAILABLE");assert.equal(result.effect,"NOT_APPLIED");
    assert.deepEqual(result.data,{detail:{stage:"DOCUMENT_MESSAGE",api:"chrome.tabs.sendMessage",category:"RECEIVER_MISSING"}});
    assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();await f.snapshot();let clicks=0;
    f.state.messageHook=message=>{if(message.action==="click") {clicks++;throw Error("The message port closed before a response was received.");}};
    const result=await f.run(request("click"));assert.equal(clicks,1);
    assert.equal(result.status,"ACTION_EFFECT_UNKNOWN");assert.equal(result.effect,"EFFECT_UNKNOWN");
    assert.equal(result.data.detail.category,"MESSAGE_PORT_CLOSED");
  }
  {
    const f=fixture();f.state.sites.clear();
    f.api.scripting.executeScript=()=>{throw Error("must not inject without permission");};
    const result=await f.snapshot();assert.equal(result.status,"SITE_PERMISSION_REQUIRED");assert.equal(result.data,null);
    assert.equal(f.state.effects.length,0);
  }
  {
    const f=fixture();f.api.tabs.sendMessage=async()=>({ok:"malformed",code:"OK",effect:"NOT_APPLIED"});
    const result=await f.snapshot();assert.equal(result.status,"PAGE_RESPONSE_INVALID");assert.equal(result.data,null);
  }
  console.log("browser controller contract passed");
})().catch(error=>{console.error(error);process.exitCode=1;});

