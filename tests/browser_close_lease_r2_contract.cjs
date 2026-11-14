"use strict";
// BR2-R2 CHANGE 2 — the close gate's live lease and unknown-activity rule.
// (i) The shipped lease is a 90-minute CONSTANT (5400000 ms, above the
// longest lawful poll interval of 60 minutes): an operator that opened its
// tab through the bridge and then waits on a long answer makes no bridge
// request for many minutes and must not lose its tab. The constructor
// option stays for tests only; the shipped entry point (background.js)
// passes none — case 17 proves both statically.
// (ii) A record whose owner has NO activity entry uses the record's own
// opened_at as its last activity. A tab is an orphan only when a KNOWN
// time is older than the lease; an unknown activity is never an orphan.
// Every refusal returns before any chrome.tabs.remove (cases 11, 12, 15,
// 16a and the cumulative sweep 18 assert remove was never called).
// Not changed: the opener record is the only source of ownership, a
// caller's statement is never enough, close params stay empty.
// VM contract harness with a chrome stub; the controller is created with
// NO options (the shipped default), and time is controlled by backdating
// the persisted records/activity the controller loads at startup.
// Run one case in isolation: MMX_CLOSE_CASE=<n> node <this file>.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {webcrypto,createHash,randomBytes} = require("node:crypto");
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const {createController,REQUEST_SCHEMA} = require("../integrations/chairman_surfaces/web_sol_extension/browser_control.js");
const hash = value => createHash("sha256").update(value).digest("hex");
const INSTANCE = "a".repeat(64), A = "b".repeat(64), B = "c".repeat(64);
const BOOT = "connection-generation-one";
const SNAP = "snapshot-observation-one";
const MIN = 60000, HOUR = 3600000;
const ONLY = process.env.MMX_CLOSE_CASE ? Number(process.env.MMX_CLOSE_CASE) : null;
function request(action, changes={}) {
  const hasTab = !["status","tabs","open"].includes(action);
  return {schema:REQUEST_SCHEMA,adapter_instance_id:INSTANCE,session_id:A,
    operation_key:"close-lease-r2-contract",nonce:randomBytes(24).toString("hex"),transport_boot_nonce:BOOT,action,
    tab_id:hasTab ? 5 : null,url_fingerprint:hasTab ? hash("https://allowed.test/new") : null,
    snapshot_id:hasTab && !["snapshot","diagnostics"].includes(action) ? SNAP : null,ref:null,params:{},
    issued_at:new Date().toISOString(),expires_at:new Date(Date.now()+45000).toISOString(),...changes};
}
// The page world close validates against after the ownership gate: snapshot
// arms it, validate checks session+snapshot identity. At the fixed head the
// gate refuses before this validate runs; at faa974f32 the defective orphan
// path runs through it to chrome.tabs.remove.
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
function storageStub(shared) {
  return {session:{
    get:async keys=>{const out={};for(const k of keys)if(Object.hasOwn(shared,k))out[k]=shared[k];return out;},
    set:async obj=>{Object.assign(shared,JSON.parse(JSON.stringify(obj)));},
    remove:async keys=>{for(const k of keys)delete shared[k];}
  }};
}
function chromeStub(shared) {
  const tabs = new Map([[9,{id:9,windowId:7,url:"https://allowed.test/operator",title:"Operator",active:true}]]);
  const removed = [];
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
      create:async options=>{throw Error("no open in this suite");},
      update:async(id,value)=>Object.assign(tabs.get(id),value),
      remove:async id=>{removed.push(id);tabs.delete(id);},
      onRemoved:{addListener:()=>{}}
    },
    windows:{update:async()=>{}},
    storage:storageStub(shared)
  };
  return {api,tabs,removed};
}
// The SHIPPED shape: no options object at all (background.js passes none).
const shippedController = stub => createController(stub.api, INSTANCE, ()=>BOOT);
const close = (c,tabId,session) => c.run(request("close",{session_id:session,tab_id:tabId,
  url_fingerprint:hash(tabId===9 ? "https://allowed.test/operator" : "https://allowed.test/new")}),BOOT);
// Arms the page world for the post-gate validate. Every case arms it, so
// at faa974f32 the defective orphan path runs to completion (the tab is
// actually removed); at the fixed head the ownership gate refuses first
// and the remove spy stays empty.
const snap = (c,tabId,session) => c.run(request("snapshot",{session_id:session,tab_id:tabId,
  url_fingerprint:hash("https://allowed.test/new")}),BOOT);
// Backdate the persisted opener record and (optionally) the owner's activity
// entry, then register the tab itself. The controller loads both at startup.
function seed(stub, shared, tabId, {openedAgo, activityAgo, owner=A}) {
  shared.mmxOpenerRecords = {...(shared.mmxOpenerRecords||{}),
    [String(tabId)]:{session_id:owner,opened_at:Date.now()-openedAgo}};
  shared.mmxSessionActivity = {...(shared.mmxSessionActivity||{})};
  if (activityAgo !== null) shared.mmxSessionActivity[owner] = Date.now()-activityAgo;
  stub.tabs.set(tabId,{id:tabId,windowId:7,url:"https://allowed.test/new",title:"Opened",active:false});
}
const cases = [
  // 11. Owner idle 10 minutes: inside the 90-minute lease the tab is NOT an
  //     orphan. At faa974f32 (120 s lease) this closes the tab — the defect.
  [11, async()=>{
    const shared={};const stub=chromeStub(shared);
    seed(stub,shared,5,{openedAgo:10*MIN,activityAgo:10*MIN});
    const c=shippedController(stub);
    assert.equal((await snap(c,5,B)).effect,"NOT_APPLIED");
    const refused=await close(c,5,B);
    assert.equal(refused.status,"TAB_OWNER_SESSION_LIVE",JSON.stringify(refused));
    assert.equal(refused.effect,"NOT_APPLIED");
    assert.deepEqual(stub.removed,[],"refusal must return before any chrome.tabs.remove");
    assert.equal(stub.tabs.has(5),true,"the tab stays open");
  }],
  // 12. No activity entry, opened_at 10 minutes ago: the record's own
  //     opened_at is the owner's last activity — refused, not an orphan.
  //     At faa974f32 the missing entry falls through to orphan close.
  [12, async()=>{
    const shared={};const stub=chromeStub(shared);
    seed(stub,shared,5,{openedAgo:10*MIN,activityAgo:null});
    const c=shippedController(stub);
    assert.equal((await snap(c,5,B)).effect,"NOT_APPLIED");
    const refused=await close(c,5,B);
    assert.equal(refused.status,"TAB_OWNER_SESSION_LIVE",JSON.stringify(refused));
    assert.equal(refused.effect,"NOT_APPLIED");
    assert.deepEqual(stub.removed,[],"refusal must return before any chrome.tabs.remove");
    assert.equal(stub.tabs.has(5),true);
  }],
  // 13. No activity entry, opened_at 2 hours ago: a KNOWN time older than
  //     the 90-minute lease — orphan close, disclosed. (Passes at base too;
  //     regression guard for the fallback's other side.)
  [13, async()=>{
    const shared={};const stub=chromeStub(shared);
    seed(stub,shared,5,{openedAgo:2*HOUR,activityAgo:null});
    const c=shippedController(stub);
    assert.equal((await snap(c,5,B)).effect,"NOT_APPLIED");
    const closed=await close(c,5,B);
    assert.equal(closed.effect,"APPLIED",JSON.stringify(closed));
    assert.equal(closed.data.orphan_close,true);
    assert.deepEqual(stub.removed,[5]);
  }],
  // 14. Activity entry pruned after 24 h: the prune drops the owner's
  //     entry, the opened_at fallback (25 h, a known old time) still makes
  //     it an orphan. The persisted ledger must no longer carry the owner.
  [14, async()=>{
    const shared={};const stub=chromeStub(shared);
    seed(stub,shared,5,{openedAgo:25*HOUR,activityAgo:25*HOUR});
    const c=shippedController(stub);
    assert.equal((await snap(c,5,B)).effect,"NOT_APPLIED");
    const closed=await close(c,5,B);
    assert.equal(closed.effect,"APPLIED",JSON.stringify(closed));
    assert.equal(closed.data.orphan_close,true);
    assert.deepEqual(stub.removed,[5]);
    assert.equal(Object.hasOwn(shared.mmxSessionActivity||{},A),false,
      "the 24 h prune must drop the owner's stale activity entry");
  }],
  // 15. Operator tab (no record): TAB_NOT_BRIDGE_OPENED, unchanged.
  [15, async()=>{
    const shared={};const stub=chromeStub(shared);
    const c=shippedController(stub);
    const refused=await close(c,9,B);
    assert.equal(refused.status,"TAB_NOT_BRIDGE_OPENED",JSON.stringify(refused));
    assert.equal(refused.effect,"NOT_APPLIED");
    assert.deepEqual(stub.removed,[],"refusal must return before any chrome.tabs.remove");
    assert.equal(stub.tabs.has(9),true);
  }],
  // 16. The lease boundary is exactly 90 minutes: 89 minutes idle is still
  //     live (refused); 91 minutes idle is an orphan (closable, disclosed).
  [16, async()=>{
    const shared={};const stub=chromeStub(shared);
    seed(stub,shared,5,{openedAgo:89*MIN,activityAgo:89*MIN});
    const c=shippedController(stub);
    assert.equal((await snap(c,5,B)).effect,"NOT_APPLIED");
    const refused=await close(c,5,B);
    assert.equal(refused.status,"TAB_OWNER_SESSION_LIVE","89 min < 90 min lease: "+JSON.stringify(refused));
    assert.deepEqual(stub.removed,[],"refusal must return before any chrome.tabs.remove");
    const shared2={};const stub2=chromeStub(shared2);
    seed(stub2,shared2,5,{openedAgo:91*MIN,activityAgo:91*MIN});
    const c2=shippedController(stub2);
    assert.equal((await snap(c2,5,B)).effect,"NOT_APPLIED");
    const closed=await close(c2,5,B);
    assert.equal(closed.effect,"APPLIED","91 min > 90 min lease: "+JSON.stringify(closed));
    assert.equal(closed.data.orphan_close,true);
    assert.deepEqual(stub2.removed,[5]);
  }],
  // 17. Static proof of (i): the shipped entry point passes NO options, and
  //     the default lease in code is the 90-minute constant. Nothing a
  //     caller, an environment variable or a file can set shortens it: the
  //     request schema has no lease field (close params stay empty) and the
  //     option is reachable only from createController's caller.
  [17, async()=>{
    const ext = path.join(__dirname,"..","integrations/chairman_surfaces/web_sol_extension");
    const background = fs.readFileSync(path.join(ext,"background.js"),"utf8");
    assert.match(background,
      /createController\(chrome, INSTANCE_CONFIG\.instanceId, \(\) => transportBootNonce\)/,
      "the shipped entry point must call createController with exactly three arguments");
    assert.doesNotMatch(background,/createController\([^)]*,[^)]*,[^)]*,/,
      "no shipped createController call may pass a fourth (options) argument");
    const control = fs.readFileSync(path.join(ext,"browser_control.js"),"utf8");
    const lease = control.match(/SESSION_LIVE_LEASE_MS = Number\.isInteger\(options\.sessionLiveLeaseMs\) && options\.sessionLiveLeaseMs >= 0\s*\?\s*options\.sessionLiveLeaseMs\s*:\s*(\d+);/);
    assert.ok(lease,"the lease must stay a constant default in code");
    assert.equal(Number(lease[1]),90*60*1000,"the shipped lease is 90 minutes");
    assert.ok(Number(lease[1]) > 60*60*1000,"above the longest lawful poll interval (60 min)");
  }],
  // 18. Cumulative sweep: every refusal shape returns before any
  //     chrome.tabs.remove — the remove spy stays empty across all of them.
  [18, async()=>{
    const shared={};const stub=chromeStub(shared);
    seed(stub,shared,5,{openedAgo:10*MIN,activityAgo:null});
    seed(stub,shared,6,{openedAgo:10*MIN,activityAgo:10*MIN});
    seed(stub,shared,7,{openedAgo:89*MIN,activityAgo:89*MIN,owner:"d".repeat(64)});
    const c=shippedController(stub);
    for (const tabId of [5,6,7]) assert.equal((await snap(c,tabId,B)).effect,"NOT_APPLIED");
    for (const tabId of [9,5,6,7]) {
      const refused=await close(c,tabId,B);
      assert.equal(refused.effect,"NOT_APPLIED","tab "+tabId+": "+JSON.stringify(refused));
      assert.ok(["TAB_NOT_BRIDGE_OPENED","TAB_OWNER_SESSION_LIVE"].includes(refused.status));
      assert.deepEqual(stub.removed,[],"no chrome.tabs.remove before or at a refusal (tab "+tabId+")");
    }
    assert.equal(stub.tabs.has(5)&&stub.tabs.has(6)&&stub.tabs.has(7)&&stub.tabs.has(9),true);
  }],
];
(async()=>{
  const ran=[];
  for (const [n,fn] of cases) {
    if (ONLY!==null && ONLY!==n) continue;
    await fn();
    ran.push(n);
  }
  console.log(JSON.stringify({state:"PASS",proof:"vm contract harness, shipped default lease (no options), backdated persisted records/activity",
    cases:ran,lease:"90-minute constant; opened_at is the last activity when the owner's activity is unknown; every refusal precedes chrome.tabs.remove"}));
})().catch(error=>{console.error(error);process.exitCode=1;});
