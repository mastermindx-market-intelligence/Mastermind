"use strict";
// Straggler-tab close on the bridge's OWN opener record (BR2 item 3,
// CRITICAL). A tab is closable only when the extension's own persisted
// record says the bridge opened it: the requesting session opened it, or
// the opener session is silent past the live lease (an orphan). Operator
// tabs and tabs with no record are refused TAB_NOT_BRIDGE_OPENED; a tab of
// another LIVE session is refused TAB_OWNER_SESSION_LIVE — both stay open.
// Records survive a service-worker restart (chrome.storage.session); with
// no storage they are memory-only and fail closed across a restart. The
// caller cannot forge a close: params stay empty and identity is the
// host-verified session. VM contract harness with a chrome stub.
const assert = require("node:assert/strict");
const {webcrypto,createHash,randomBytes} = require("node:crypto");
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const {createController,REQUEST_SCHEMA} = require("../integrations/chairman_surfaces/web_sol_extension/browser_control.js");
const hash = value => createHash("sha256").update(value).digest("hex");
const INSTANCE = "a".repeat(64), A = "b".repeat(64), B = "c".repeat(64);
const BOOT = "connection-generation-one";
const SNAP = "snapshot-observation-one";
const LEASE = 60;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function request(action, changes={}) {
  const hasTab = !["status","tabs","open"].includes(action);
  return {schema:REQUEST_SCHEMA,adapter_instance_id:INSTANCE,session_id:A,
    operation_key:"orphan-close-contract",nonce:randomBytes(24).toString("hex"),transport_boot_nonce:BOOT,action,
    tab_id:hasTab ? 5 : null,url_fingerprint:hasTab ? hash("https://allowed.test/new") : null,
    snapshot_id:hasTab && !["snapshot","diagnostics"].includes(action) ? SNAP : null,ref:null,params:{},
    issued_at:new Date().toISOString(),expires_at:new Date(Date.now()+45000).toISOString(),...changes};
}
function storageStub(shared) {
  return {session:{
    get:async keys=>{const out={};for(const k of keys)if(Object.hasOwn(shared,k))out[k]=shared[k];return out;},
    set:async obj=>{Object.assign(shared,JSON.parse(JSON.stringify(obj)));},
    remove:async keys=>{for(const k of keys)delete shared[k];}
  }};
}
// The page world close validates against: snapshot arms it, validate checks
// session+snapshot identity. Nothing else is dispatched in these cases.
function worldDispatch(state) {
  return message => {
    if (message.action === "snapshot") {
      state.session = message.session_id; state.snapshot = SNAP;
      return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{snapshot_id:SNAP}};
    }
    if (message.session_id !== state.session || message.snapshot_id !== state.snapshot)
      return {ok:false,code:"STALE_SNAPSHOT",effect:"NOT_APPLIED",data:null};
    if (message.action === "validate") return {ok:true,code:"OK",effect:"NOT_APPLIED",data:{}};
    return {ok:false,code:"INVALID_REQUEST",effect:"NOT_APPLIED",data:null};
  };
}
// Minimal chrome surface for open/snapshot/close/status. Tab ids start at 5;
// tab 9 is an operator tab the bridge never opened.
function chromeStub(shared, {withStorage=true}={}) {
  const tabs = new Map([[9,{id:9,windowId:7,url:"https://allowed.test/operator",title:"Operator",active:true}]]);
  let nextId = 5;
  const removed = [];
  let removedListener = null;
  const state = {session:null,snapshot:null};
  const dispatch = worldDispatch(state);
  const api = {
    permissions:{contains:async query=>(query.permissions||[]).every(p=>["tabs","scripting"].includes(p)) &&
      (query.origins||[]).every(p=>p==="https://allowed.test/*")},
    runtime:{getManifest:()=>({version:"0.4.1"}),getURL:leaf=>"chrome-extension://fixture/"+leaf},
    scripting:{executeScript:async options=>{
      if (options.files) {assert.deepEqual(options.files,["browser_page.js"]);return [{documentId:"document-one"}];}
      assert.equal(options.world,"ISOLATED");assert.equal(typeof options.func,"function");
      globalThis.__MMX_BROWSER_PAGE_V1__ = {dispatch};
      const value = options.func(...options.args);
      return [{result:(value && typeof value.then === "function") ? await value : value}];
    }},
    tabs:{
      get:async id=>{if(!tabs.has(id))throw Error("missing");return {...tabs.get(id)};},
      query:async()=>[...tabs.values()],
      create:async options=>{const id=nextId++;const tab={id,windowId:7,...options};tabs.set(id,tab);return tab;},
      update:async(id,value)=>Object.assign(tabs.get(id),value),
      remove:async id=>{removed.push(id);tabs.delete(id);if(removedListener)removedListener(id);},
      onRemoved:{addListener:fn=>{removedListener=fn;}}
    },
    windows:{update:async()=>{}}
  };
  if (withStorage) api.storage = storageStub(shared);
  return {api,tabs,removed,state,fireRemoved:id=>{tabs.delete(id);if(removedListener)removedListener(id);}};
}
function controller(stub) {
  return createController(stub.api, INSTANCE, ()=>BOOT, {sessionLiveLeaseMs:LEASE});
}
const open = (c,session=A) => c.run(request("open",{session_id:session,params:{url:"https://allowed.test/new"}}),BOOT);
const snap = (c,tabId,session) => c.run(request("snapshot",{session_id:session,tab_id:tabId,
  url_fingerprint:hash("https://allowed.test/new")}),BOOT);
const close = (c,tabId,session) => c.run(request("close",{session_id:session,tab_id:tabId,
  url_fingerprint:hash("https://allowed.test/new")}),BOOT);
const closeOperator = (c,session) => c.run(request("close",{session_id:session,tab_id:9,
  url_fingerprint:hash("https://allowed.test/operator")}),BOOT);

(async()=>{
  // 1. Same-session close still works, with no orphan flag.
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const opened=await open(c);assert.equal(opened.effect,"APPLIED");
    const tabId=opened.data.tab_id;
    assert.equal((await snap(c,tabId,A)).effect,"NOT_APPLIED");
    const closed=await close(c,tabId,A);
    assert.equal(closed.effect,"APPLIED",JSON.stringify(closed));
    assert.equal(closed.data.orphan_close,undefined);
    assert.deepEqual(stub.removed,[tabId]);
  }
  // 2. Another LIVE session's tab: refused, stays open.
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const opened=await open(c,A);const tabId=opened.data.tab_id;
    await snap(c,tabId,B);
    const refused=await close(c,tabId,B);
    assert.equal(refused.status,"TAB_OWNER_SESSION_LIVE",JSON.stringify(refused));
    assert.equal(refused.effect,"NOT_APPLIED");
    assert.deepEqual(stub.removed,[]);
    assert.equal(stub.tabs.has(tabId),true);
  }
  // 3. Orphan: opener silent past the lease -> closable, disclosed.
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const opened=await open(c,A);const tabId=opened.data.tab_id;
    await snap(c,tabId,B);
    await sleep(LEASE+30);
    const closed=await close(c,tabId,B);
    assert.equal(closed.effect,"APPLIED",JSON.stringify(closed));
    assert.equal(closed.data.orphan_close,true);
    assert.deepEqual(stub.removed,[tabId]);
  }
  // 4. Operator tab (no record): refused, stays open.
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const refused=await closeOperator(c,B);
    assert.equal(refused.status,"TAB_NOT_BRIDGE_OPENED",JSON.stringify(refused));
    assert.equal(refused.effect,"NOT_APPLIED");
    assert.deepEqual(stub.removed,[]);
    assert.equal(stub.tabs.has(9),true);
  }
  // 5. Records survive a service-worker restart: a fresh controller with
  //    the same storage closes the orphan after the lease. The tab itself
  //    outlives the worker, so the new stub keeps it.
  {
    const shared={};const stub1=chromeStub(shared);const c1=controller(stub1);
    const opened=await open(c1,A);const tabId=opened.data.tab_id;
    const stub2=chromeStub(shared);
    stub2.tabs.set(tabId,{id:tabId,windowId:7,url:"https://allowed.test/new",title:"Opened",active:false});
    const c2=controller(stub2);
    await snap(c2,tabId,B);
    await sleep(LEASE+30);
    const closed=await close(c2,tabId,B);
    assert.equal(closed.effect,"APPLIED","persisted opener record authorizes the orphan close: "+JSON.stringify(closed));
    assert.equal(closed.data.orphan_close,true);
  }
  // 6. No storage API: memory-only records fail closed across a restart.
  {
    const stub1=chromeStub({},{withStorage:false});const c1=controller(stub1);
    const opened=await open(c1,A);const tabId=opened.data.tab_id;
    const stub2=chromeStub({},{withStorage:false});
    stub2.tabs.set(tabId,{id:tabId,windowId:7,url:"https://allowed.test/new",title:"Opened",active:false});
    const c2=controller(stub2);
    await snap(c2,tabId,B);
    await sleep(LEASE+30);
    const refused=await close(c2,tabId,B);
    assert.equal(refused.status,"TAB_NOT_BRIDGE_OPENED",JSON.stringify(refused));
    assert.deepEqual(stub2.removed,[]);
  }
  // 7. onRemoved clears the record (memory and persistence).
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const opened=await open(c,A);const tabId=opened.data.tab_id;
    await snap(c,tabId,A);
    stub.fireRemoved(tabId);
    await sleep(10);
    const records=shared.mmxOpenerRecords||{};
    assert.equal(Object.hasOwn(records,String(tabId)),false,"record removed from persistence");
    const refused=await close(c,tabId,A);
    assert.equal(refused.status,"TARGET_NOT_FOUND","the tab itself is gone");
  }
  // 8. Any request refreshes the opener's liveness; silence past the lease
  //    is what makes an orphan.
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const opened=await open(c,A);const tabId=opened.data.tab_id;
    await snap(c,tabId,B);
    await sleep(LEASE-20);
    await c.run(request("status",{session_id:A}),BOOT);
    await sleep(LEASE-20);
    const refused=await close(c,tabId,B);
    assert.equal(refused.status,"TAB_OWNER_SESSION_LIVE","recent activity keeps the tab protected: "+JSON.stringify(refused));
    await sleep(LEASE+30);
    const closed=await close(c,tabId,B);
    assert.equal(closed.effect,"APPLIED",JSON.stringify(closed));
  }
  // 9. Same-session close is unaffected by the lease.
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const opened=await open(c,A);const tabId=opened.data.tab_id;
    await snap(c,tabId,A);
    await sleep(LEASE+30);
    const closed=await close(c,tabId,A);
    assert.equal(closed.effect,"APPLIED",JSON.stringify(closed));
    assert.equal(closed.data.orphan_close,undefined);
  }
  // 10. The caller cannot forge an orphan close: close params stay empty.
  {
    const shared={};const stub=chromeStub(shared);const c=controller(stub);
    const opened=await open(c,A);const tabId=opened.data.tab_id;
    await snap(c,tabId,B);
    const forged=await c.run(request("close",{session_id:B,tab_id:tabId,
      url_fingerprint:hash("https://allowed.test/new"),params:{orphan:true}}),BOOT);
    assert.equal(forged,null,"invalid params never reach the close gate");
    assert.deepEqual(stub.removed,[]);
  }
  console.log(JSON.stringify({state:"PASS",proof:"vm contract harness with chrome storage stub",
    cases:["same-session close unchanged","live opener's tab refused TAB_OWNER_SESSION_LIVE and stays open",
             "orphan past the lease closable with orphan_close disclosure",
             "operator tab refused TAB_NOT_BRIDGE_OPENED and stays open",
             "records survive a service-worker restart","no storage fails closed across a restart",
             "onRemoved clears memory and persistence","activity refreshes liveness",
             "same-session close ignores the lease","forged close params refused"]}));
})().catch(error=>{console.error(error);process.exitCode=1;});