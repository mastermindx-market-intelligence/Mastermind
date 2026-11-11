"use strict";

// Existing native port, exact profile/session, optional site grants and scoped CDP.
(function (root) {
  const SCHEMA = "mastermind.web_sol_browser_request.v1";
  const RECEIPT = "mastermind.web_sol_browser_receipt.v1";
  const IDENTITY = ["adapter_instance_id", "session_id", "operation_key", "nonce", "transport_boot_nonce", "action"];
  const FIELDS = ["schema", ...IDENTITY, "tab_id", "url_fingerprint", "snapshot_id", "ref", "params", "issued_at", "expires_at"];
  const CDP = root.MMXBrowserCDP;
  const READ = new Set(["status", "tabs", "snapshot", "screenshot", "diagnostics", ...(CDP ? CDP.READ : [])]);
  const PAGE = new Set(["click", "fill", "select", "press", "scroll"]);
  const ACTIONS = new Set([...READ, ...PAGE, "open", "navigate", "reload", "back", "forward", "close", "focus", ...(CDP ? CDP.ACTIONS : [])]);
  const NO_SNAPSHOT = new Set(["snapshot", "diagnostics", ...(CDP ? CDP.NO_SNAPSHOT : [])]);
  const TAB = new Set([...ACTIONS].filter(a => !["status", "tabs", "open"].includes(a)));
  const KEY_CODES = {Enter:13, Tab:9, Escape:27, ArrowUp:38, ArrowDown:40, ArrowLeft:37,
    ArrowRight:39, Home:36, End:35, Backspace:8, Delete:46, Space:32};
  const hex = x => typeof x === "string" && /^[0-9a-f]{64}$/.test(x);
  const bounded = (x, low=1, high=128) => typeof x === "string" && x.length >= low && x.length <= high && !/[\x00-\x1f\x7f]/.test(x);
  // Receipt detail channel: error name plus the first characters of the native
  // message, every URL cut to 48 characters, the whole string cut to 180.
  const URL_CUT = /(https?:\/\/[^\s"'<>\\]{1,300})/g;
  function boundedDetail(text, limit=180) {
    const clipped = String(text || "").replace(URL_CUT, m => m.slice(0, 48)).replace(/\s+/g, " ").trim();
    return clipped ? clipped.slice(0, limit) : null;
  }
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
    if (TAB.has(r.action) && !NO_SNAPSHOT.has(r.action)) {if (!bounded(r.snapshot_id,16)) return false;}
    else if (r.action === "diagnostics") {if (!(r.snapshot_id === null || bounded(r.snapshot_id,16))) return false;}
    else if (r.snapshot_id !== null) return false;
    if (PAGE.has(r.action)) {if (!bounded(r.ref,1,32)) return false;} else if (r.ref !== null) return false;
    const p = r.params;
    if (CDP && CDP.ACTIONS.has(r.action)) {if (!CDP.validate(r.action,p)) return false;}
    else if (["open", "navigate"].includes(r.action)) {if (!exact(p,["url"]) || !url(p.url)) return false;}
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
    let busy = null, debuggerUncertain = false, observedBoot = null;
    let cleanupPromise=Promise.resolve([]);
    // Ring buffer of the last 20 error receipts this worker produced, so a
    // person never has to open DevTools to read why actions failed.
    const errorRing = [];
    function recordError(action, code, detail) {
      errorRing.push({at:new Date().toISOString(), action, code, ...(detail ? {detail} : {})});
      if (errorRing.length > 20) errorRing.splice(0, errorRing.length - 20);
    }
    const liveBoot = connection || (()=>observedBoot);
    function current(r) {
      if (liveBoot() !== r.transport_boot_nonce) throw new Error("CONNECTION_CHANGED");
      if (Date.parse(r.expires_at) <= Date.now()) throw new Error("REQUEST_EXPIRED");
    }
    function receipt(r, status, data=null, effect="NOT_APPLIED") {
      const value = {schema: RECEIPT, ...Object.fromEntries(IDENTITY.map(k=>[k,r[k]])), status, effect,
        observed_at: new Date().toISOString(), data};
      if (new TextEncoder().encode(JSON.stringify(value)).length > 800000) {
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
      if (advanced && advanced.has(r.tab_id) && !advanced.owned(r.tab_id,r.session_id)) throw new Error("CDP_OWNED_BY_ANOTHER_SESSION");
      let tab;
      try {tab = await chrome.tabs.get(r.tab_id);} catch (_) {throw new Error("TARGET_NOT_FOUND");}
      if (!tab || tab.incognito || !url(tab.url) || tab.pendingUrl || tab.discarded || tab.frozen) throw new Error("TARGET_UNAVAILABLE");
      if (await fingerprint(tab.url) !== r.url_fingerprint) throw new Error("TARGET_CHANGED");
      if (!await granted(tab.url)) throw new Error("SITE_PERMISSION_REQUIRED");
      current(r);
      return tab;
    }
    const PAGE_READ_RETRY = new Set(["snapshot", "diagnostics"]);
    async function pageWorld(tab) {
      if (!documents.has(tab.id) && documents.size >= 128) throw new Error("TAB_LIMIT");
      const installed = await chrome.scripting.executeScript({target:{tabId:tab.id,frameIds:[0]},
        files:["browser_page.js"],world:"ISOLATED"});
      const documentId = installed && installed[0] ? installed[0].documentId : null;
      if (!bounded(documentId,1,128)) throw new Error("DOCUMENT_ID_UNAVAILABLE");
      documents.set(tab.id,documentId);
      return documentId;
    }
    // One executeScript(func) round trip instead of a cached documentId plus
    // tabs.sendMessage: a recycled isolated world or a lost page listener can
    // no longer leave a tab permanently unreachable, and a native rejection
    // keeps its own text instead of collapsing to BROWSER_UNAVAILABLE.
    async function page(r, action=r.action, params=r.params, beforeSend=null) {
      const tab = await tabFor(r);
      const payload = {kind:"MMX_BROWSER_PAGE_V1",action,session_id:r.session_id,
        snapshot_id:r.snapshot_id||null,ref:r.ref||null,params:params||{},expires_at:r.expires_at};
      const call = async () => {
        const out = await chrome.scripting.executeScript({target:{tabId:tab.id,frameIds:[0]},world:"ISOLATED",
          func: ds => {
            const p = globalThis.__MMX_BROWSER_PAGE_V1__;
            if (!p) return {ok:false,code:"PAGE_WORLD_UNAVAILABLE",data:null,effect:"NOT_APPLIED"};
            try { return p.dispatch(ds); }
            catch (e) {
              // A dispatch that died mid-flight cannot prove NOT_APPLIED for a
              // mutation; report it as uncertain, reads as safely unapplied.
              const read = /^(snapshot|validate|validate_focus|consume|diagnostics)$/.test(ds && ds.action || "");
              return {ok:false,code:"PAGE_DISPATCH_FAILED",
                data:{detail:boundedDetail(String(e && e.message || e).slice(0,160))},
                effect: read ? "NOT_APPLIED" : "EFFECT_UNKNOWN"};
            }
          }, args:[payload]});
        return out && out[0] ? out[0].result : null;
      };
      let value = null;
      try {
        // Reads re-inject the page world; a mutation without a live world
        // entry (for example after a transport reconnect cleared it) must
        // stay STALE_SNAPSHOT, never silently re-arm against an old snapshot.
        if (action === "snapshot" || action === "diagnostics") await pageWorld(tab);
        else if (!documents.has(tab.id)) throw new Error("STALE_SNAPSHOT");
        await tabFor(r); current(r); if (beforeSend) beforeSend();
        value = await call();
        if (PAGE_READ_RETRY.has(action) && (!value || value.code === "PAGE_WORLD_UNAVAILABLE")) {
          await pageWorld(tab); await tabFor(r); current(r); value = await call();
        }
      } catch (error) {
        const text = String(error && error.message || error);
        // Precise allow-listed failures from pageWorld()/tabFor()/current()
        // pass through unchanged; only unknown failures are wrapped below.
        if (/^(TAB_LIMIT|DOCUMENT_ID_UNAVAILABLE|STALE_SNAPSHOT|REQUEST_EXPIRED|CONNECTION_CHANGED|TARGET_[A-Z_]+|SITE_PERMISSION_REQUIRED|CDP_[A-Z_]+)$/.test(text)) throw error;
        const wrapped = new Error(/Cannot access contents|cannot be scripted|Missing host permission|permission to access the respective host/i.test(text)
          ? "SITE_PERMISSION_REQUIRED" : "PAGE_INJECT_FAILED");
        wrapped.knownNotApplied = true;
        wrapped.detail = boundedDetail(`inject ${(error && error.name) || "Error"}: ${text}` +
          ` tab=${String(tab.url || "").slice(0,48)} doc=${documents.get(tab.id) || "-"}`);
        throw wrapped;
      }
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
      if(advanced)return advanced.withDebugger(r,fn);
      if (debuggerUncertain) throw new Error("DEBUGGER_RECONCILIATION_REQUIRED");
      const tab = await tabFor(r);
      if (!await granted(tab.url,["debugger"])) throw new Error("DEBUGGER_PERMISSION_REQUIRED");
      const target = {tabId:r.tab_id};
      current(r);
      const send=async(method,params)=>{current(r);const value=await chrome.debugger.sendCommand(target,method,params);current(r);return value;};
      let attached = false, value, failure;
      try {
        await chrome.debugger.attach(target,"1.3"); attached = true;
        await tabFor(r);
        const verified = await page(r,"validate",{});
        if (!verified.ok) throw new Error(verified.code);
        value = await fn(send);
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
      if (observedBoot !== boot) {
        documents.clear();
        busy=null;
        if(observedBoot && advanced)cleanupPromise=advanced.reset();
        observedBoot = boot;
      }
      await cleanupPromise;
      if(liveBoot()!==r.transport_boot_nonce)return receipt(r,"CONNECTION_CHANGED");
      if (busy) return receipt(r,"BUSY");
      const now = Date.now();
      for (const [nonce,expiry] of nonces) if (expiry <= now) nonces.delete(nonce);
      if (nonces.has(r.nonce)) return receipt(r,"NONCE_REUSED");
      if (nonces.size >= 2048) return receipt(r,"NONCE_LIMIT");
      nonces.set(r.nonce,Date.parse(r.expires_at));
      const running={boot};busy=running;
      let attempted = false;
      try {
        if (r.action === "status") return receipt(r,"OK",{
          connection_id:boot,adapter_instance_id:instanceId,
          package_version:chrome.runtime.getManifest().version,
          control_enabled:await chrome.permissions.contains({permissions:["tabs","scripting"]}),
          screenshot_enabled:await chrome.permissions.contains({permissions:["tabs","scripting","debugger"]}),
          advanced_cdp_available:Boolean(advanced), downloads_enabled:await chrome.permissions.contains({permissions:["downloads"]}),
          upload_file_access_allowed:chrome.extension?.isAllowedFileSchemeAccess?await chrome.extension.isAllowedFileSchemeAccess():null,
          actions:[...ACTIONS].sort(),permissions_url:chrome.runtime.getURL("browser.html"),
          scope:"this installed browser profile; permitted HTTP/S tabs only",exclusive_control:false,
          recent_errors:errorRing.slice(),
          cdp_diagnostics:advanced?advanced.diagnostics():null});
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
        if (advanced && CDP.ACTIONS.has(r.action)) {
          if (!["cdp_status","cdp_detach"].includes(r.action)) await tabFor(r);
          if (!NO_SNAPSHOT.has(r.action)) {
            const proof=await page(r,"validate",{});
            if(!proof.ok)return receipt(r,proof.code);
            const consumed=await page(r,"consume",{});
            if(!consumed.ok)return receipt(r,consumed.code);
          }
          const outcome=await advanced.execute(r,()=>{attempted=true;});
          return receipt(r,outcome.status,outcome.data,outcome.effect||"NOT_APPLIED");
        }
        const tab = await tabFor(r);
        if (r.action === "snapshot") {
          const response = await page(r);
          await tabFor(r);
          return receipt(r,response.code,response.data,response.effect);
        }
        if (r.action === "diagnostics") {
          // Callable without any prior snapshot, and still answers when the
          // page world is unreachable: that state is exactly what it diagnoses.
          try {
            const response = await page(r);
            await tabFor(r);
            if (!response.ok) throw new Error(response.code);
            return receipt(r,"OK",{...response.data,page_world:"ok",recent_errors:errorRing.slice()});
          } catch (error) {
            const text = String(error && error.message || error);
            if (/^(TARGET_NOT_FOUND|TARGET_UNAVAILABLE|TARGET_CHANGED|CONNECTION_CHANGED|REQUEST_EXPIRED)$/.test(text)) throw error;
            recordError("diagnostics", text.slice(0,64), boundedDetail(error && error.detail || text));
            return receipt(r,"OK",{page_world:"unavailable",page_error:text.slice(0,64),
              worker:{documents_tracked:documents.size,debugger_uncertain:debuggerUncertain},
              recent_errors:errorRing.slice()});
          }
        }
        const verified = await page(r,"validate",{});
        if (!verified.ok) return receipt(r,verified.code);
        if (r.action === "screenshot") {
          const data = await withDebugger(r,async send => {
            const metrics = await send("Page.getLayoutMetrics",{});
            const v = metrics.cssVisualViewport;
            if (!v || ![v.pageX,v.pageY,v.clientWidth,v.clientHeight].every(Number.isFinite) || v.clientWidth <= 0 || v.clientHeight <= 0) throw new Error("SCREENSHOT_UNAVAILABLE");
            const captured = await send("Page.captureScreenshot",{format:"jpeg",quality:35,fromSurface:true,captureBeyondViewport:false,
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
          await withDebugger(r,async send => {
            const focused = await page(r,"focus_ref",{},()=>{attempted=true;});
            if (!focused.ok) {attempted = focused.effect !== "NOT_APPLIED";throw new Error(focused.code);}
            await tabFor(r);
            const confirmed = await page(r,"validate_focus",{token:focused.data.focus_token});
            if (!confirmed.ok) throw new Error(confirmed.code);
            current(r);
            const key = r.params.key === "Space" ? " " : r.params.key;
            const code = r.params.key, keyCode = KEY_CODES[code];
            await send("Input.dispatchKeyEvent",{type:"keyDown",key,code,windowsVirtualKeyCode:keyCode,nativeVirtualKeyCode:keyCode,...(code === "Enter" ? {text:"\r"} : code === "Space" ? {text:" "} : {})});
            await send("Input.dispatchKeyEvent",{type:"keyUp",key,code,windowsVirtualKeyCode:keyCode,nativeVirtualKeyCode:keyCode});
          });
          return receipt(r,"ACTION_DISPATCHED",{refresh_required:true},"APPLIED");
        }
        if (r.action === "back" || r.action === "forward") {
          await withDebugger(r,async send => {
            const history = await send("Page.getNavigationHistory",{});
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
            await send("Page.navigateToHistoryEntry",{entryId:entry.id});
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
          "DEBUGGER_PERMISSION_REQUIRED","DEBUGGER_RECONCILIATION_REQUIRED","SCREENSHOT_UNAVAILABLE","SCREENSHOT_TOO_LARGE","HISTORY_UNAVAILABLE","FOCUS_NOT_CONFIRMED",
          "PAGE_INJECT_FAILED","PAGE_DISPATCH_FAILED","PAGE_WORLD_UNAVAILABLE"]);
        const code = allowed.has(error && error.message) || /^(CDP_|FRAME_|STALE_NODE_|RESPONSE_|RESULT_|UPLOAD_|DOWNLOAD_|PAGE_|INPUT_|INVALID_|TARGET_OBSCURED|PDF_|EVALUATE_|NETWORK_|ROUTE_|EMULATE_)/.test(error?.message||"")
          ? error.message : "BROWSER_UNAVAILABLE";
        const possible=attempted&&!error?.knownNotApplied;
        // An unexpected error is never again reduced to a bare BROWSER_UNAVAILABLE:
        // the receipt carries a bounded detail and the ring keeps the last 20.
        const detail = error?.detail || boundedDetail(`${(error && error.name) || "Error"}: ${(error && error.message) || error}`);
        recordError(r.action, possible ? "ACTION_EFFECT_UNKNOWN" : code, detail);
        return receipt(r,possible ? "ACTION_EFFECT_UNKNOWN" : code,
          {reason:code,...(detail?{detail}:{})},possible ? "EFFECT_UNKNOWN" : "NOT_APPLIED");
      } finally {if(busy===running)busy=null;}
    }
    const advanced = CDP ? CDP.create(chrome,{current,granted,tabFor,connectionActive:boot=>liveBoot()===boot}) : null;
    if (chrome.tabs.onRemoved) chrome.tabs.onRemoved.addListener(id=>{documents.delete(id);createdTabs.delete(id);});
    return {run,uiStatus:()=>advanced?advanced.uiStatus():[],diagnostics:()=>advanced?advanced.diagnostics():null,
      transportDisconnected:()=>{documents.clear();busy=null;cleanupPromise=advanced?advanced.reset():Promise.resolve([]);return cleanupPromise;},
      releaseAll:()=>advanced?advanced.releaseAll():Promise.resolve([])};
  }
  const api = {REQUEST_SCHEMA:SCHEMA,createController,valid,publicUrl};
  root.MMXBrowserControl = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
