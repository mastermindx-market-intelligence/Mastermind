"use strict";

// A closed command family on the existing native port. No listener, account,
// browser launcher, credentials, arbitrary script, or raw CDP endpoint.
(function (root) {
  const SCHEMA = "mastermind.web_sol_browser_request.v1";
  const RECEIPT = "mastermind.web_sol_browser_receipt.v1";
  const IDENTITY = ["adapter_instance_id", "session_id", "operation_key", "nonce", "transport_boot_nonce", "action"];
  const FIELDS = ["schema", ...IDENTITY, "tab_id", "url_fingerprint", "snapshot_id", "ref", "params", "issued_at", "expires_at"];
  const READ = new Set(["status", "tabs", "snapshot", "screenshot", "diagnostics"]);
  const PAGE = new Set(["click", "fill", "select", "press", "scroll"]);
  const ACTIONS = new Set([...READ, ...PAGE, "open", "navigate", "reload", "back", "forward", "close", "focus"]);
  const TAB = new Set([...ACTIONS].filter(a => !["status", "tabs", "open"].includes(a)));
  const KEY_CODES = {Enter:13, Tab:9, Escape:27, ArrowUp:38, ArrowDown:40, ArrowLeft:37,
    ArrowRight:39, Home:36, End:35, Backspace:8, Delete:46, Space:32};
  const hex = x => typeof x === "string" && /^[0-9a-f]{64}$/.test(x);
  const bounded = (x, low=1, high=128) => typeof x === "string" && x.length >= low && x.length <= high && !/[\x00-\x1f\x7f]/.test(x);
  const exact = (x, keys) => x && typeof x === "object" && !Array.isArray(x) && Object.keys(x).length === keys.length && keys.every(k => Object.hasOwn(x, k));
  function url(value) {
    if (!bounded(value, 1, 4096) || /\s/.test(value)) return null;
    try { const u = new URL(value); return ["http:", "https:"].includes(u.protocol) && !u.username && !u.password && u.port !== "0" ? u : null; }
    catch (_) { return null; }
  }
  const publicUrl = value => {const u = url(value); return u ? u.origin + u.pathname : null;};
  // Chrome match patterns cover every port on the selected scheme/host.
  const originPattern = value => {const u = url(value); return u ? u.protocol + "//" + u.hostname + "/*" : null;};
  async function fingerprint(value) {
    const digest = await root.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
  }
  function valid(r, instance, boot) {
    if (!exact(r, FIELDS) || r.schema !== SCHEMA || r.adapter_instance_id !== instance ||
        !hex(r.adapter_instance_id) || !hex(r.session_id) || !bounded(r.operation_key) || !bounded(r.nonce,16) ||
        !ACTIONS.has(r.action) || r.transport_boot_nonce !== boot || !bounded(boot,16)) return false;
    if (TAB.has(r.action)) {
      if (!Number.isInteger(r.tab_id) || r.tab_id < 0 || r.tab_id > 2147483647 || !hex(r.url_fingerprint)) return false;
    } else if (r.tab_id !== null || r.url_fingerprint !== null) return false;
    if (TAB.has(r.action) && r.action !== "snapshot") {if (!bounded(r.snapshot_id,16)) return false;}
    else if (r.snapshot_id !== null) return false;
    if (PAGE.has(r.action)) {if (!bounded(r.ref,1,32)) return false;} else if (r.ref !== null) return false;
    const p = r.params;
    if (["open", "navigate"].includes(r.action)) {if (!exact(p,["url"]) || !url(p.url)) return false;}
    else if (r.action === "fill") {if (!exact(p,["text"]) || typeof p.text !== "string" || p.text.length > 8000 || p.text.includes("\u0000")) return false;}
    else if (r.action === "select") {if (!exact(p,["value"]) || !bounded(p.value,0,512)) return false;}
    else if (r.action === "press") {if (!exact(p,["key"]) || !Object.hasOwn(KEY_CODES,p.key)) return false;}
    else if (r.action === "scroll") {if (!exact(p,["x","y"]) || ![p.x,p.y].every(x=>Number.isInteger(x)&&Math.abs(x)<=3000)) return false;}
    else if (!exact(p,[])) return false;
    const ts = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;
    if (typeof r.issued_at !== "string" || typeof r.expires_at !== "string" || !ts.test(r.issued_at) || !ts.test(r.expires_at)) return false;
    const start = Date.parse(r.issued_at), end = Date.parse(r.expires_at), now = Date.now();
    return Number.isFinite(start) && Number.isFinite(end) && end > now && end > start && end-start <= 60000 && start-now <= 5000;
  }
  function createController(chromeApi, instanceId, connection) {
    const chrome = chromeApi;
    const documents = new Map();
    const nonces = new Map();
    const createdTabs = new Map();
    let busy = false, debuggerUncertain = false, observedBoot = null;
    const liveBoot = connection || (()=>observedBoot);
    function current(r) {
      if (liveBoot() !== r.transport_boot_nonce) throw new Error("CONNECTION_CHANGED");
      if (Date.parse(r.expires_at) <= Date.now()) throw new Error("REQUEST_EXPIRED");
    }
    function receipt(r, status, data=null, effect="NOT_APPLIED") {
      const value = {schema: RECEIPT, ...Object.fromEntries(IDENTITY.map(k=>[k,r[k]])), status, effect,
        observed_at: new Date().toISOString(), data};
      if (new TextEncoder().encode(JSON.stringify(value)).length > 60000) {
        value.status = "RESULT_TOO_LARGE"; value.data = null;
      }
      return value;
    }
    async function granted(value, extra=[]) {
      const origin = originPattern(value);
      return Boolean(origin && await chrome.permissions.contains({permissions:["tabs","scripting",...extra],origins:[origin]}));
    }
    async function tabFor(r) {
      current(r);
      let tab;
      try {tab = await chrome.tabs.get(r.tab_id);} catch (_) {throw new Error("TARGET_NOT_FOUND");}
      if (!tab || tab.incognito || !url(tab.url) || tab.pendingUrl || tab.discarded || tab.frozen) throw new Error("TARGET_UNAVAILABLE");
      if (await fingerprint(tab.url) !== r.url_fingerprint) throw new Error("TARGET_CHANGED");
      if (!await granted(tab.url)) throw new Error("SITE_PERMISSION_REQUIRED");
      current(r);
      return tab;
    }
    async function page(r, action=r.action, params=r.params, beforeSend=null) {
      const tab = await tabFor(r);
      let documentId = documents.get(tab.id);
      if (action === "snapshot") {
        if (!documents.has(tab.id) && documents.size >= 128) throw new Error("TAB_LIMIT");
        const installed = await chrome.scripting.executeScript({target:{tabId:tab.id,frameIds:[0]},files:["browser_page.js"],world:"ISOLATED"});
        documentId = installed && installed[0] && installed[0].documentId;
        if (!bounded(documentId,1,128)) throw new Error("DOCUMENT_ID_UNAVAILABLE");
        documents.set(tab.id,documentId);
      }
      if (!documentId) throw new Error("STALE_SNAPSHOT");
      await tabFor(r);
      current(r);
      if (beforeSend) beforeSend();
      const value = await chrome.tabs.sendMessage(tab.id,{kind:"MMX_BROWSER_PAGE_V1",action,
        session_id:r.session_id,snapshot_id:r.snapshot_id,ref:r.ref,params,expires_at:r.expires_at},{documentId});
      if (!value || typeof value.ok !== "boolean" || !bounded(value.code,1,64) ||
          !["APPLIED","NOT_APPLIED","EFFECT_UNKNOWN"].includes(value.effect)) throw new Error("PAGE_RESPONSE_INVALID");
      return value;
    }
    async function listed(tab) {
      return {tab_id:tab.id,window_id:tab.windowId,title:String(tab.title||"").slice(0,160),
        url:publicUrl(tab.url),url_fingerprint:await fingerprint(tab.url),active:Boolean(tab.active),
        loading:tab.status === "loading",discarded:Boolean(tab.discarded),frozen:Boolean(tab.frozen)};
    }
    async function withDebugger(r, fn) {
      if (debuggerUncertain) throw new Error("DEBUGGER_RECONCILIATION_REQUIRED");
      const tab = await tabFor(r);
      if (!await granted(tab.url,["debugger"])) throw new Error("DEBUGGER_PERMISSION_REQUIRED");
      const target = {tabId:r.tab_id};
      let attached = false, value, failure;
      try {
        await chrome.debugger.attach(target,"1.3"); attached = true;
        await tabFor(r);
        const verified = await page(r,"validate",{});
        if (!verified.ok) throw new Error(verified.code);
        value = await fn(target);
      } catch (e) {failure = e;}
      finally {
        if (attached) try {await chrome.debugger.detach(target);} catch (_) {
          debuggerUncertain = true; failure = new Error("DEBUGGER_RECONCILIATION_REQUIRED");
        }
      }
      if (failure) throw failure;
      return value;
    }
    async function run(r, boot) {
      if (!valid(r,instanceId,boot)) return null;
      if (observedBoot !== boot) {documents.clear();observedBoot = boot;}
      if (busy) return receipt(r,"BUSY");
      const now = Date.now();
      for (const [nonce,expiry] of nonces) if (expiry <= now) nonces.delete(nonce);
      if (nonces.has(r.nonce)) return receipt(r,"NONCE_REUSED");
      if (nonces.size >= 2048) return receipt(r,"NONCE_LIMIT");
      nonces.set(r.nonce,Date.parse(r.expires_at));
      busy = true;
      let attempted = false;
      try {
        if (r.action === "status") return receipt(r,"OK",{
          connection_id:boot,adapter_instance_id:instanceId,
          package_version:chrome.runtime.getManifest().version,
          control_enabled:await chrome.permissions.contains({permissions:["tabs","scripting"]}),
          screenshot_enabled:await chrome.permissions.contains({permissions:["tabs","scripting","debugger"]}),
          actions:[...ACTIONS].sort(),permissions_url:chrome.runtime.getURL("browser.html"),
          scope:"this installed browser profile; permitted HTTP/S tabs only",exclusive_control:false});
        if (r.action === "tabs") {
          if (!await chrome.permissions.contains({permissions:["tabs","scripting"]})) return receipt(r,"BROWSER_PERMISSION_REQUIRED");
          const all = await chrome.tabs.query({});
          const rows = []; let excluded = 0, omitted = 0;
          const existing = new Set(all.map(t=>t.id));
          for (const id of documents.keys()) if (!existing.has(id)) {documents.delete(id);createdTabs.delete(id);}
          for (const tab of all.slice(0,512)) {
            if (tab.incognito || !url(tab.url) || !await granted(tab.url)) {excluded++;continue;}
            if (rows.length >= 100) {omitted++;continue;}
            rows.push(await listed(tab));
          }
          return receipt(r,"OK",{tabs:rows,excluded_count:excluded,omitted_count:omitted+Math.max(0,all.length-512)});
        }
        if (r.action === "open") {
          if (!await granted(r.params.url)) return receipt(r,"SITE_PERMISSION_REQUIRED",{origin:originPattern(r.params.url)});
          if (createdTabs.size >= 128) return receipt(r,"TAB_LIMIT");
          current(r);
          attempted = true;
          const tab = await chrome.tabs.create({url:r.params.url,active:false});
          createdTabs.set(tab.id,r.session_id);
          return receipt(r,"ACTION_DISPATCHED",{tab_id:tab.id,refresh_required:true},"APPLIED");
        }
        const tab = await tabFor(r);
        if (r.action === "snapshot" || r.action === "diagnostics") {
          const response = await page(r);
          await tabFor(r);
          return receipt(r,response.code,response.data,response.effect);
        }
        const verified = await page(r,"validate",{});
        if (!verified.ok) return receipt(r,verified.code);
        if (r.action === "screenshot") {
          const data = await withDebugger(r,async target => {
            const metrics = await chrome.debugger.sendCommand(target,"Page.getLayoutMetrics",{});
            const v = metrics.cssVisualViewport;
            if (!v || ![v.pageX,v.pageY,v.clientWidth,v.clientHeight].every(Number.isFinite) || v.clientWidth <= 0 || v.clientHeight <= 0) throw new Error("SCREENSHOT_UNAVAILABLE");
            const captured = await chrome.debugger.sendCommand(target,"Page.captureScreenshot",{format:"jpeg",quality:35,fromSurface:true,captureBeyondViewport:false,
              clip:{x:v.pageX,y:v.pageY,width:v.clientWidth,height:v.clientHeight,scale:Math.min(1,1024/v.clientWidth,768/v.clientHeight)}});
            if (!captured || typeof captured.data !== "string" || captured.data.length > 45000 || !/^[A-Za-z0-9+/]+={0,2}$/.test(captured.data)) throw new Error("SCREENSHOT_TOO_LARGE");
            await tabFor(r);
            const again = await page(r,"validate",{});
            if (!again.ok) throw new Error(again.code);
            return {mime_type:"image/jpeg",base64:captured.data,scope:"selected tab viewport"};
          });
          return receipt(r,"OK",data);
        }
        if (r.action === "press") {
          await withDebugger(r,async target => {
            const focused = await page(r,"focus_ref",{},()=>{attempted=true;});
            if (!focused.ok) {attempted = focused.effect !== "NOT_APPLIED";throw new Error(focused.code);}
            await tabFor(r);
            const confirmed = await page(r,"validate_focus",{token:focused.data.focus_token});
            if (!confirmed.ok) throw new Error(confirmed.code);
            current(r);
            const key = r.params.key === "Space" ? " " : r.params.key;
            const code = r.params.key, keyCode = KEY_CODES[code];
            await chrome.debugger.sendCommand(target,"Input.dispatchKeyEvent",{type:"keyDown",key,code,windowsVirtualKeyCode:keyCode,nativeVirtualKeyCode:keyCode,...(code === "Enter" ? {text:"\r"} : code === "Space" ? {text:" "} : {})});
            await chrome.debugger.sendCommand(target,"Input.dispatchKeyEvent",{type:"keyUp",key,code,windowsVirtualKeyCode:keyCode,nativeVirtualKeyCode:keyCode});
          });
          return receipt(r,"ACTION_DISPATCHED",{refresh_required:true},"APPLIED");
        }
        if (r.action === "back" || r.action === "forward") {
          await withDebugger(r,async target => {
            const history = await chrome.debugger.sendCommand(target,"Page.getNavigationHistory",{});
            if (!history || !Array.isArray(history.entries) || !Number.isInteger(history.currentIndex)) throw new Error("HISTORY_UNAVAILABLE");
            const entry = history.entries[history.currentIndex + (r.action === "back" ? -1 : 1)];
            if (!entry || !Number.isInteger(entry.id) || !url(entry.url)) throw new Error("HISTORY_UNAVAILABLE");
            if (!await granted(entry.url)) throw new Error("SITE_PERMISSION_REQUIRED");
            await tabFor(r);
            const current = await page(r,"validate",{});
            if (!current.ok) throw new Error(current.code);
            if (liveBoot() !== r.transport_boot_nonce || Date.parse(r.expires_at) <= Date.now()) throw new Error("CONNECTION_CHANGED");
            attempted = true;
            documents.delete(tab.id);
            await chrome.debugger.sendCommand(target,"Page.navigateToHistoryEntry",{entryId:entry.id});
          });
          return receipt(r,"ACTION_DISPATCHED",{refresh_required:true},"APPLIED");
        }
        if (PAGE.has(r.action)) {
          const response = await page(r,r.action,r.params,()=>{attempted=true;});
          return receipt(r,response.ok ? "ACTION_DISPATCHED" : response.code,response.data,response.effect);
        }
        if (r.action === "navigate" && !await granted(r.params.url)) return receipt(r,"SITE_PERMISSION_REQUIRED",{origin:originPattern(r.params.url)});
        if (r.action === "close" && createdTabs.get(tab.id) !== r.session_id) return receipt(r,"TAB_NOT_CREATED_BY_SESSION");
        await tabFor(r);
        current(r);
        attempted = true;
        documents.delete(tab.id);
        if (r.action === "navigate") await chrome.tabs.update(tab.id,{url:r.params.url});
        if (r.action === "reload") await chrome.tabs.reload(tab.id,{});
        if (r.action === "close") {await chrome.tabs.remove(tab.id);createdTabs.delete(tab.id);}
        if (r.action === "focus") {await chrome.tabs.update(tab.id,{active:true});await chrome.windows.update(tab.windowId,{focused:true});}
        return receipt(r,"ACTION_DISPATCHED",{refresh_required:true},"APPLIED");
      } catch (error) {
        const allowed = new Set(["TARGET_NOT_FOUND","TARGET_UNAVAILABLE","TARGET_CHANGED","SITE_PERMISSION_REQUIRED",
          "BROWSER_PERMISSION_REQUIRED","STALE_SNAPSHOT","DOCUMENT_ID_UNAVAILABLE","PAGE_RESPONSE_INVALID","TAB_LIMIT","CONNECTION_CHANGED","REQUEST_EXPIRED",
          "DEBUGGER_PERMISSION_REQUIRED","DEBUGGER_RECONCILIATION_REQUIRED","SCREENSHOT_UNAVAILABLE","SCREENSHOT_TOO_LARGE","HISTORY_UNAVAILABLE","FOCUS_NOT_CONFIRMED"]);
        const code = allowed.has(error && error.message) ? error.message : "BROWSER_UNAVAILABLE";
        return receipt(r,attempted ? "ACTION_EFFECT_UNKNOWN" : code,null,attempted ? "EFFECT_UNKNOWN" : "NOT_APPLIED");
      } finally {busy = false;}
    }
    if (chrome.tabs.onRemoved) chrome.tabs.onRemoved.addListener(id=>{documents.delete(id);createdTabs.delete(id);});
    return {run};
  }
  const api = {REQUEST_SCHEMA:SCHEMA,createController,valid,publicUrl};
  root.MMXBrowserControl = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
