"use strict";

// CDP belongs to the existing profile-native connection. No debugging port,
// browser-wide target discovery, automatic mutation retry or alternate transport.
(function (root) {
  const READ = new Set(["cdp_status", "frames", "accessibility", "dom", "locate", "wait",
    "events", "network", "response_body", "result", "downloads", "capture", "pdf"]);
  const MUTATE = new Set(["cdp_attach", "cdp_detach", "cdp", "evaluate", "interact",
    "upload", "download", "dialog", "emulate", "route"]);
  const ACTIONS = new Set([...READ, ...MUTATE]);
  const NO_SNAPSHOT = new Set([...READ, "cdp_detach", "dialog"]);
  const DOMAINS = new Set(["Accessibility", "Audits", "CacheStorage", "CSS", "DOM",
    "DOMDebugger", "DOMSnapshot", "Emulation", "Fetch", "Input", "Inspector", "IO",
    "Log", "Network", "Overlay", "Page", "Performance", "Runtime", "WebAudio", "WebAuthn"]);
  const RESERVED = new Set(["Page.crash", "Page.close", "Page.setWebLifecycleState",
    "Page.navigateToHistoryEntry", "Page.addScriptToEvaluateOnNewDocument", "Page.setBypassCSP",
    "Page.setDownloadBehavior", "Network.getAllCookies", "Network.getCookies", "Network.setCookie",
    "Network.setCookies", "Network.deleteCookies", "Network.clearBrowserCookies", "Network.clearBrowserCache",
    "Network.setBypassServiceWorker", "DOM.setFileInputFiles", "Runtime.runIfWaitingForDebugger",
    "Fetch.enable", "Fetch.disable", "Fetch.takeResponseBodyAsStream",
    "Fetch.continueWithAuth", "IO.close", "IO.read"]);
  // A domain grant alone does not confine a CDP method to a tab. Enumerate the
  // supported escape hatch; lifecycle, cookies, storage and interception use
  // deliberate typed operations rather than ambient protocol authority.
  const RAW_METHODS = new Set([
    "Accessibility.getFullAXTree","Accessibility.getPartialAXTree","Accessibility.getRootAXNode","Accessibility.getAXNodeAndAncestors","Accessibility.getChildAXNodes","Accessibility.queryAXTree",
    "DOM.getDocument","DOM.getFlattenedDocument","DOM.describeNode","DOM.resolveNode","DOM.requestNode","DOM.querySelector","DOM.querySelectorAll",
    "DOM.getAttributes","DOM.getBoxModel","DOM.getContentQuads","DOM.getOuterHTML","DOM.getNodeForLocation","DOM.getNodesForSubtreeByStyle","DOM.getRelayoutBoundary",
    "DOM.focus","DOM.scrollIntoViewIfNeeded","DOM.setAttributeValue","DOM.setAttributesAsText","DOM.removeAttribute","DOM.setNodeValue","DOM.setOuterHTML","DOM.removeNode","DOM.copyTo","DOM.moveTo",
    "DOMSnapshot.captureSnapshot","DOMSnapshot.getSnapshot","DOMDebugger.getEventListeners",
    "CSS.enable","CSS.getComputedStyleForNode","CSS.getMatchedStylesForNode","CSS.getInlineStylesForNode","CSS.getStyleSheetText","CSS.getPlatformFontsForNode",
    "CSS.setStyleSheetText","CSS.setStyleTexts","CSS.setEffectivePropertyValueForNode","CSS.forcePseudoState","CSS.getMediaQueries",
    "Page.getFrameTree","Page.getLayoutMetrics","Page.getNavigationHistory","Page.getResourceTree","Page.getResourceContent",
    "Page.navigate","Page.reload","Page.stopLoading",
    "Runtime.evaluate","Runtime.callFunctionOn","Runtime.getProperties","Runtime.releaseObject","Runtime.releaseObjectGroup","Runtime.getHeapUsage",
    "Input.dispatchKeyEvent","Input.dispatchMouseEvent","Input.dispatchTouchEvent","Input.insertText","Input.synthesizeScrollGesture","Input.synthesizeTapGesture","Input.synthesizePinchGesture",
    "Network.getResponseBody","Network.getCertificate",
    "Overlay.enable","Overlay.disable","Overlay.highlightNode","Overlay.highlightRect","Overlay.hideHighlight","Overlay.setShowPaintRects","Overlay.setShowLayoutShiftRegions",
    "Performance.enable","Performance.disable","Performance.getMetrics",
    "Log.enable","Log.disable","Log.clear","WebAudio.enable","WebAudio.disable"
  ]);
  const LIMIT = {sessions:8, events:400, requests:160, refs:160, resultBytes:2000000,
    resultCount:6, pageChars:24000, idleMs:300000};
  const text = (v,n=300) => String(v == null ? "" : v).slice(0,n);
  const object = v => v && typeof v === "object" && !Array.isArray(v);
  const plain = v => object(v) && Object.getPrototypeOf(v) === Object.prototype;
  const token = () => root.crypto.randomUUID().replace(/-/g,"");
  const cleanURL = v => {try {const u=new URL(v); return ["http:","https:","ws:","wss:"].includes(u.protocol) ? u.origin+u.pathname : null;} catch (_) {return null;}};
  const siteURL = v => {try{const u=new URL(v);if(u.protocol==="ws:")u.protocol="http:";if(u.protocol==="wss:")u.protocol="https:";return u.href;}catch(_){return v;}};
  const cleanText = v => text(v,1500).replace(/(Bearer\s+)[^\s"']+/ig,"$1[REDACTED]")
    .replace(/((?:api[_-]?key|access[_-]?token|authorization|password|cookie)\s*[:=]\s*)[^\s,;]+/ig,"$1[REDACTED]");
  const integer = (v,lo,hi) => Number.isSafeInteger(v) && v>=lo && v<=hi;
  const methodOK = v => typeof v==="string" && /^[A-Z][A-Za-z]+\.[a-zA-Z][a-zA-Z0-9]+$/.test(v);
  const KEYS = {Enter:13,Tab:9,Escape:27,Backspace:8,Delete:46,Space:32,
    ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40,Home:36,End:35,PageUp:33,PageDown:34};
  function validate(action,p) {
    if (!ACTIONS.has(action) || !plain(p) || JSON.stringify(p).length>30000) return false;
    const fields = {
      cdp_attach:["network","capture_stream_data"], cdp_detach:[], cdp_status:[],
      cdp:["method","params","frame_id"], evaluate:["expression","frame_id","await_promise","world"],
      frames:[], accessibility:["frame_id","limit"], dom:["frame_id","depth","pierce","selector"],
      locate:["frame_id","locator","limit","include_hidden"], interact:["ref","kind","text","key","value","checked","x","y","target_ref"],
      wait:["frame_id","locator","state","timeout_ms"], events:["after","limit","method"],
      network:["limit","request_id"], response_body:["request_id","offset","limit"],
      result:["result_id","offset","limit"], upload:["ref","files"], download:["url","filename"],
      downloads:["download_id"], dialog:["accept","prompt","dialog_ref"], emulate:["viewport","user_agent","media","timezone","reset"],
      route:["rules"], capture:["full_page","format","quality","max_width","max_height"], pdf:["landscape","print_background","scale"]
    };
    if (Object.keys(p).some(k=>!fields[action].includes(k))) return false;
    if (p.frame_id!==undefined && (typeof p.frame_id!=="string" || p.frame_id.length>256)) return false;
    if (p.limit!==undefined && !integer(p.limit,1,action==="response_body"||action==="result"?32000:200)) return false;
    if (p.offset!==undefined && !integer(p.offset,0,LIMIT.resultBytes)) return false;
    if (p.after!==undefined && !integer(p.after,0,Number.MAX_SAFE_INTEGER)) return false;
    if (["cdp","evaluate"].includes(action)) {
      if (action==="cdp" && (!methodOK(p.method) || (p.params!==undefined&&!plain(p.params)))) return false;
      if (action==="evaluate" && (typeof p.expression!=="string" || !p.expression || p.expression.length>20000 ||
          (p.world!==undefined&&!["page","isolated"].includes(p.world)))) return false;
    }
    if (["locate","wait"].includes(action)) {
      if (!plain(p.locator) || !Object.keys(p.locator).length ||
          Object.keys(p.locator).some(k=>!["css","role","name","text","label","testid","exact","index"].includes(k))) return false;
      if (Object.entries(p.locator).some(([k,v])=>k==="exact"?typeof v!=="boolean":k==="index"?!integer(v,0,10000):typeof v!=="string"||v.length>1000)) return false;
      if (p.timeout_ms!==undefined&&!integer(p.timeout_ms,0,8000)) return false;
      if (p.state!==undefined&&!["visible","hidden","attached","detached"].includes(p.state)) return false;
    }
    if (["interact","upload"].includes(action) && (typeof p.ref!=="string"||!/^n[0-9a-f]{24}$/.test(p.ref))) return false;
    if (action==="interact" && !["click","double_click","hover","fill","type","press","select","check","scroll","drag"].includes(p.kind)) return false;
    if (action==="interact" && ((["fill","type"].includes(p.kind)&&typeof p.text!=="string") ||
        (p.kind==="select"&&typeof p.value!=="string") || (p.kind==="check"&&typeof p.checked!=="boolean") ||
        (p.kind==="press"&&typeof p.key!=="string") || (p.kind==="drag"&&!/^n[0-9a-f]{24}$/.test(p.target_ref||"")))) return false;
    if (action==="dialog" && (typeof p.accept!=="boolean"||!/^d[0-9a-f]{32}$/.test(p.dialog_ref||""))) return false;
    if (action==="emulate") {
      if(p.viewport!==undefined){const v=p.viewport;if(!plain(v)||Object.keys(v).some(k=>!["width","height","mobile","device_scale_factor"].includes(k))||!integer(v.width,200,4096)||!integer(v.height,200,8192)||typeof v.mobile!=="boolean"||!Number.isFinite(v.device_scale_factor)||v.device_scale_factor<0.5||v.device_scale_factor>4)return false;}
      if(p.user_agent!==undefined&&(typeof p.user_agent!=="string"||p.user_agent.length>1000))return false;
      if(p.media!==undefined&&!["screen","print",""].includes(p.media))return false;
      if(p.timezone!==undefined&&(typeof p.timezone!=="string"||p.timezone.length>100))return false;
    }
    if (p.text!==undefined&&(typeof p.text!=="string"||p.text.length>16000||p.text.includes("\0"))) return false;
    if (p.key!==undefined&&(typeof p.key!=="string"||p.key.length>80)) return false;
    if (p.value!==undefined&&(typeof p.value!=="string"||p.value.length>1000)) return false;
    if (p.checked!==undefined&&typeof p.checked!=="boolean") return false;
    if (["x","y"].some(k=>p[k]!==undefined&&(!Number.isFinite(p[k])||Math.abs(p[k])>10000))) return false;
    if (action==="upload" && (!Array.isArray(p.files)||!p.files.length||p.files.length>16||
        p.files.some(f=>typeof f!=="string"||!f.startsWith("/")||f.length>4096||/[\0\r\n]/.test(f)))) return false;
    if (action==="download" && (typeof p.url!=="string"||!cleanURL(p.url)||
        (p.filename!==undefined&&(typeof p.filename!=="string"||!/^[a-zA-Z0-9][a-zA-Z0-9 ._-]{0,119}$/.test(p.filename)||p.filename.includes(".."))))) return false;
    if (action==="route" && (!Array.isArray(p.rules)||p.rules.length>16||p.rules.some(rule=>
        !plain(rule)||Object.keys(rule).some(k=>!["url_pattern","action"].includes(k))||
        typeof rule.url_pattern!=="string"||rule.url_pattern.length>1000||!/^https?:\/\//.test(rule.url_pattern)||
        !["continue","block"].includes(rule.action)))) return false;
    for (const key of ["network","capture_stream_data","await_promise","exact","pierce","include_hidden","accept","full_page","landscape","print_background","reset"])
      if(p[key]!==undefined&&typeof p[key]!=="boolean") return false;
    if (p.quality!==undefined&&!integer(p.quality,10,100)) return false;
    if (p.format!==undefined&&!["jpeg","png"].includes(p.format)) return false;
    if (["max_width","max_height"].some(k=>p[k]!==undefined&&!integer(p[k],64,4096))) return false;
    if (p.depth!==undefined&&!integer(p.depth,0,8)) return false;
    if (p.prompt!==undefined&&(typeof p.prompt!=="string"||p.prompt.length>2000)) return false;
    if (p.scale!==undefined&&(!Number.isFinite(p.scale)||p.scale<0.1||p.scale>2)) return false;
    return true;
  }

  // This function executes in a CDP isolated world, traversing open shadow roots.
  // It returns actual nodes; node IDs never come from model-generated guesses.
  function queryNodes(locator,limit,visibleOnly) {
    const trim=v=>String(v||"").replace(/\s+/g," ").trim();
    const roots=[document],nodes=[],seen=new Set();let visited=0;
    const roleOf=e=>e.getAttribute("role")||({BUTTON:"button",A:e.hasAttribute("href")?"link":"",
      SELECT:"combobox",TEXTAREA:"textbox",IMG:"img",H1:"heading",H2:"heading",H3:"heading",
      INPUT:({checkbox:"checkbox",radio:"radio",range:"slider",button:"button",submit:"button"})[e.type]||"textbox"})[e.tagName]||"";
    const labelOf=e=>trim(e.getAttribute("aria-label")||(e.getAttribute("aria-labelledby")||"").split(/\s+/)
      .map(id=>document.getElementById(id)?.textContent||"").join(" ")||
      (e.labels?Array.from(e.labels).map(l=>l.textContent).join(" "):"")||e.getAttribute("alt")||e.getAttribute("placeholder")||
      (e.tagName==="INPUT"&&/^(button|submit)$/.test(e.type)?e.value:"")||e.innerText||e.textContent);
    const match=(a,b)=>locator.exact===false?a.toLowerCase().includes(b.toLowerCase()):a===b;
    while(roots.length&&visited<15000&&nodes.length<limit) {
      const scope=roots.shift();
      const walker=document.createTreeWalker(scope,NodeFilter.SHOW_ELEMENT);
      let e;
      while((e=walker.nextNode())&&++visited<15000) {
        if(e.shadowRoot) roots.push(e.shadowRoot);
        if(seen.has(e)) continue;seen.add(e);
        if(locator.css) {try {if(!e.matches(locator.css))continue;}catch(_){throw new Error("INVALID_SELECTOR");}}
        if(locator.role&&roleOf(e)!==locator.role)continue;
        if(locator.name&&!match(labelOf(e),locator.name))continue;
        if(locator.label&&(!e.matches("input,textarea,select,button,meter,output,progress,[contenteditable=true],[role=textbox]")||!match(labelOf(e),locator.label)))continue;
        if(locator.testid&&e.getAttribute("data-testid")!==locator.testid)continue;
        if(locator.text&&!match(trim(e.innerText||e.textContent),locator.text))continue;
        if(e.tagName==="INPUT"&&/^(password|hidden)$/.test(e.type))continue;
        if(visibleOnly) {const b=e.getBoundingClientRect(),s=getComputedStyle(e);if(!e.isConnected||!b.width||!b.height||s.visibility==="hidden"||s.display==="none")continue;}
        nodes.push(e);if(nodes.length>=limit)break;
      }
    }
    return locator.index===undefined?nodes:(nodes[locator.index]?[nodes[locator.index]]:[]);
  }
  function nodeInfo() {
    const e=this,b=e.getBoundingClientRect(),s=getComputedStyle(e);
    const name=(e.getAttribute("aria-label")||e.getAttribute("placeholder")||
      (e.labels?Array.from(e.labels).map(x=>x.textContent).join(" "):"")||e.innerText||e.textContent||"").replace(/\s+/g," ").trim().slice(0,200);
    const sensitive=e.tagName==="INPUT"&&(/^(password|hidden)$/.test(e.type)||/password|one-time-code|cc-|credit.card/i.test(e.autocomplete||""));
    return {tag:e.tagName.toLowerCase(),type:e.type||null,role:e.getAttribute("role"),name,
      identity:[e.id,e.getAttribute("href"),e.getAttribute("formaction"),e.getAttribute("aria-label"),e.getAttribute("name"),e.getAttribute("role"),!!e.isContentEditable],
      connected:e.isConnected,visible:!!(b.width&&b.height&&s.display!=="none"&&s.visibility!=="hidden"),
      disabled:!!(e.disabled||e.getAttribute("aria-disabled")==="true"),sensitive,
      value:sensitive?undefined:("value" in e?String(e.value).slice(0,1000):undefined),
      checked:"checked" in e?!!e.checked:undefined,bounds:{x:b.x,y:b.y,width:b.width,height:b.height}};
  }

  function create(chrome,host) {
    const sessions=new Map();
    let lastAttachFailure=null;
    const connectionLive=s=>!host.connectionActive||host.connectionActive(s.boot);
    const usable=s=>sessions.get(s.tabId)===s&&!s.closing&&!s.invalidated&&!s.uncertain&&connectionLive(s);
    const requestKey=(child,id)=>(child||"root")+":"+id;
    const debuggee=(s,child=null)=>child?{tabId:s.tabId,sessionId:child}:{tabId:s.tabId};
    const emit=(s,method,data,child=null)=>{
      if(!usable(s))return;
      s.events.push({sequence:++s.sequence,at:new Date().toISOString(),method,frame_session:child||null,data});
      if(s.events.length>LIMIT.events){s.events.shift();s.dropped++;}
    };
    function check(s,r) {
      host.current(r);
      if(!s||sessions.get(s.tabId)!==s||s.owner!==r.session_id||s.boot!==r.transport_boot_nonce)throw new Error("CDP_SESSION_REQUIRED");
      if(s.closing||s.uncertain||s.invalidated||!connectionLive(s))throw new Error("CDP_RECONCILIATION_REQUIRED");
      s.lastUsed=Date.now();
    }
    async function send(s,method,params={},child=null) {
      if(sessions.get(s.tabId)!==s||s.closing||s.uncertain||s.invalidated||!connectionLive(s))throw new Error("CDP_RECONCILIATION_REQUIRED");
      let timer;
      try {const result=await Promise.race([chrome.debugger.sendCommand(debuggee(s,child),method,params),
          new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error("CDP_COMMAND_TIMEOUT")),9000);})]);
        if(sessions.get(s.tabId)!==s||s.closing||s.uncertain||s.invalidated||!connectionLive(s))throw new Error("CDP_TARGET_LOST");return result;}
      catch(error) {const msg=String(error&&error.message||error);
        if(msg==="CDP_COMMAND_TIMEOUT"){release(s,"command_timeout").catch(()=>{});throw error;}
        if(method==="DOM.setFileInputFiles"&&/not allowed|access denied/i.test(msg)){
          const denied=new Error("UPLOAD_FILE_ACCESS_REQUIRED");denied.detail=cleanText(msg);denied.knownNotApplied=true;throw denied;
        }
        if(/not attached|No tab|closed|Session with given id not found|target.*closed/i.test(msg))throw new Error("CDP_TARGET_LOST");
        const e=new Error("CDP_COMMAND_FAILED"); e.detail=cleanText(msg);throw e;
      }finally{clearTimeout(timer);}
    }
    const call=async(s,objectId,fn,args=[],child=null)=> {
      const v=await send(s,"Runtime.callFunctionOn",{objectId,functionDeclaration:fn.toString(),
        arguments:args.map(value=>({value})),returnByValue:true,awaitPromise:false},child);
      if(v.exceptionDetails)throw new Error("CDP_EVALUATION_FAILED");return v.result?.value;
    };
    async function frameTree(s) {
      const epoch=s.epoch;
      const rows=new Map();
      async function tree(child) {
        const data=await send(s,"Page.getFrameTree",{},child);
        function visit(n,parent=null) {
          if(!n?.frame)return;
          const f=n.frame,prior=rows.get(f.id)||s.frames.get(f.id);
          rows.set(f.id,{id:f.id,parent:f.parentId||parent||prior?.parent||null,url:f.url,
            name:text(f.name,100),loaderId:f.loaderId,child:child||prior?.child||null,epoch});
          for(const c of n.childFrames||[])visit(c,f.id);
        }
        visit(data.frameTree);
      }
      await tree(null);
      for(const child of s.children.keys()) {try {await tree(child);}catch(_){}}
      if(s.epoch!==epoch)throw new Error("FRAME_CHANGED");
      s.frames=rows;s.framesStale=false;
      s.mainFrame=[...rows.values()].find(f=>!f.parent&&!f.child)?.id||s.mainFrame;
      return rows;
    }
    async function frameFor(s,id) {
      if(s.framesStale||!s.frames.size||!s.frames.has(id||s.mainFrame))await frameTree(s);
      const f=s.frames.get(id||s.mainFrame);
      if(!f||(!cleanURL(f.url)&&!["about:blank","about:srcdoc"].includes(f.url)))throw new Error("FRAME_UNAVAILABLE");
      let permissionFrame=f,depth=0;
      while(!cleanURL(permissionFrame.url)&&permissionFrame.parent&&++depth<16)permissionFrame=s.frames.get(permissionFrame.parent)||permissionFrame;
      if(!await host.granted(permissionFrame.url))throw new Error("FRAME_PERMISSION_REQUIRED");
      frameCurrent(s,f);
      return f;
    }
    function frameCurrent(s,f){if(s.epoch!==f.epoch||sessions.get(s.tabId)!==s)throw new Error("FRAME_CHANGED");}
    async function world(s,f) {
      frameCurrent(s,f);
      const prior=s.worlds.get(f.id);
      if(prior&&prior.loader===f.loaderId&&prior.child===f.child&&prior.epoch===s.epoch)return prior.id;
      const v=await send(s,"Page.createIsolatedWorld",{frameId:f.id,worldName:"mastermind-browser-"+s.token,
        grantUniveralAccess:false},f.child);
      frameCurrent(s,f);
      s.worlds.set(f.id,{id:v.executionContextId,loader:f.loaderId,child:f.child,epoch:s.epoch});return v.executionContextId;
    }
    function pack(s,data) {
      const serialized=JSON.stringify(data);
      if(serialized.length<=LIMIT.pageChars)return data;
      if(new TextEncoder().encode(serialized).length>LIMIT.resultBytes)throw new Error("CDP_RESULT_TOO_LARGE");
      const id=token();s.results.set(id,serialized);
      while(s.results.size>LIMIT.resultCount)s.results.delete(s.results.keys().next().value);
      return {result_id:id,total_characters:serialized.length,offset:0,text:serialized.slice(0,LIMIT.pageChars),
        next_offset:LIMIT.pageChars,truncated:true,format:"json",content_is_untrusted:true};
    }
    function invalidate(s) {
      s.invalidated=true;s.refs.clear();s.events.length=0;s.requests.clear();s.results.clear();s.worlds.clear();
      s.objects?.clear();s.contexts?.clear();s.children.clear();s.frames.clear();s.deniedRequests.clear();
      s.downloads.clear();s.routes=[];s.dialog=null;
    }
    function release(s,reason="released") {
      if(sessions.get(s.tabId)!==s)return Promise.resolve({tab_id:s.tabId,released:true,reason:"detached_event_observed"});
      if(s.releasePromise)return s.releasePromise;
      invalidate(s);s.closing=true;
      s.releasePromise=(async()=>{
        let timer;
        try {
          // A disconnect can happen while attach is unresolved. Reserve/fence
          // that tab now, then detach only our proven successful attachment.
          // The cleanup continuation survives a timeout and never dispatches twice.
          s.cleanupPromise=(async()=>{
            if(s.attachPromise)await s.attachPromise;
            if(sessions.get(s.tabId)!==s)return;
            s.detachStarted=true;
            await chrome.debugger.detach({tabId:s.tabId});
            if(sessions.get(s.tabId)===s)sessions.delete(s.tabId);
            if(chrome.action)chrome.action.setBadgeText({tabId:s.tabId,text:""}).catch(()=>{});
          })();
          await Promise.race([s.cleanupPromise,new Promise((_,reject)=>{
            timer=setTimeout(()=>reject(new Error("detach timeout")),3000);
          })]);
        } catch(e) {
          if(sessions.get(s.tabId)!==s)return {tab_id:s.tabId,released:true,reason:"detached_event_observed"};
          s.closing=false;s.uncertain=true;s.cleanupError=cleanText(e?.message||e);
          return {tab_id:s.tabId,released:false,reason:"CDP_RECONCILIATION_REQUIRED",detail:s.cleanupError};
        } finally {clearTimeout(timer);}
        if(chrome.action)chrome.action.setBadgeText({tabId:s.tabId,text:""}).catch(()=>{});
        return {tab_id:s.tabId,released:true,reason};
      })();
      return s.releasePromise;
    }
    async function reconcileRelease(s) {
      if(sessions.get(s.tabId)!==s)return {tab_id:s.tabId,released:true,reason:"detached_event_observed"};
      if(!s.uncertain||s.attaching||!chrome.debugger.getTargets)return release(s);
      // Read-only reconciliation. Never repeat an uncertain detach.
      let timer;
      try{
        const targets=await Promise.race([chrome.debugger.getTargets(),new Promise((_,reject)=>{
          timer=setTimeout(()=>reject(new Error("reconciliation timeout")),1500);
        })]);
        const target=targets.find(t=>t.tabId===s.tabId);
        if(!target||target.attached===false){
          if(sessions.get(s.tabId)===s)sessions.delete(s.tabId);
          return {tab_id:s.tabId,released:true,reason:"detachment_observed"};
        }
      }catch(_){}finally{clearTimeout(timer);}
      return release(s);
    }
    function releaseAll(reason) {
      const all=[...sessions.values()];
      // Fence every session before the first detach can yield.
      for(const s of all)invalidate(s);
      return Promise.all(all.map(s=>s.uncertain?reconcileRelease(s):release(s,reason)));
    }
    async function attach(r,p,mark) {
      const prior=sessions.get(r.tab_id);
      if(prior){check(prior,r);return {session:prior.token,already_attached:true,ownership:"this Hermes session",epoch:prior.epoch};}
      if(sessions.size>=LIMIT.sessions)throw new Error("CDP_SESSION_LIMIT");
      const tab=await host.tabFor(r);
      if(!await host.granted(tab.url,["debugger"]))throw new Error("DEBUGGER_PERMISSION_REQUIRED");
      host.current(r);
      // A permission check can yield across a disconnect/new connection.
      // Never replace a session admitted while that check was pending.
      const afterGrant=sessions.get(r.tab_id);
      if(afterGrant){check(afterGrant,r);return {session:afterGrant.token,already_attached:true,epoch:afterGrant.epoch};}
      const s={tabId:r.tab_id,owner:r.session_id,boot:r.transport_boot_nonce,token:token(),epoch:token(),
        mainFrame:null,frames:new Map(),worlds:new Map(),children:new Map(),refs:new Map(),results:new Map(),
        events:[],sequence:0,dropped:0,requests:new Map(),deniedRequests:new Set(),objects:new Map(),downloads:new Map(),routes:[],lastUsed:Date.now(),
        streamData:p.capture_stream_data===true,network:p.network!==false,closing:false,uncertain:false,attaching:true};
      mark();
      sessions.set(r.tab_id,s);
      let attachTimer;
      try{
        s.attachPromise=chrome.debugger.attach({tabId:r.tab_id},"1.3");
        s.attachPromise.then(()=>{s.attaching=false;},()=>{s.attaching=false;});
        await Promise.race([s.attachPromise,new Promise((_,reject)=>{
          attachTimer=setTimeout(()=>reject(new Error("CDP_ATTACH_TIMEOUT")),9000);
        })]);
      }
      catch(cause){
        const detail=cleanText(cause?.message||cause);
        const error=new Error(/another debugger|already attached/i.test(detail)?"CDP_ALREADY_ATTACHED":
          /developer mode/i.test(detail)?"CDP_DEVELOPER_MODE_REQUIRED":
          /policy|restricted|not allowed|cannot access/i.test(detail)?"CDP_POLICY_RESTRICTED":"CDP_ATTACH_UNAVAILABLE");
        error.detail=detail;
        error.knownNotApplied=/another debugger|already attached|developer mode|policy|restricted|not allowed|cannot access|No tab|No target|protocol version/i.test(detail);
        lastAttachFailure={at:new Date().toISOString(),tab_id:r.tab_id,reason:error.message,detail};
        if(error.knownNotApplied){if(sessions.get(s.tabId)===s)sessions.delete(s.tabId);}
        else{invalidate(s);s.uncertain=true;release(s,"attach_failed").catch(()=>{});}
        throw error;
      }finally{clearTimeout(attachTimer);}
      lastAttachFailure=null;
      if(chrome.action)chrome.action.setBadgeText({tabId:r.tab_id,text:"CDP"}).catch(()=>{});
      try{
        await host.tabFor(r);
        await send(s,"Page.enable");await send(s,"Runtime.enable");
        if(s.network)await send(s,"Network.enable",{maxTotalBufferSize:2000000,maxResourceBufferSize:500000,maxPostDataSize:0});
        try{await send(s,"Log.enable");}catch(_){}
        await frameTree(s);
        try{await send(s,"Target.setAutoAttach",{autoAttach:true,waitForDebuggerOnStart:false,flatten:true,
          filter:[{type:"iframe",exclude:false},{exclude:true}]});s.relatedFrames=true;}
        catch(_){s.relatedFrames=false;}
        check(s,r);
        emit(s,"Mastermind.attached",{version:chrome.runtime.getManifest().version,scope:"selected tab"});
        return {session:s.token,epoch:s.epoch,network:s.network,related_frames:s.relatedFrames,
          idle_timeout_ms:LIMIT.idleMs,ownership:"this Hermes session; other sessions are refused",
          raw_cdp_scope:"Chrome debugger-supported domains in this tab and permitted related frames"};
      }catch(e){await release(s,"attach_failed");throw e;}
    }
    async function find(s,p,visible=true) {
      const f=await frameFor(s,p.frame_id),contextId=await world(s,f);
      const count=p.limit||40;
      const response=await send(s,"Runtime.evaluate",{expression:"("+queryNodes.toString()+")("+JSON.stringify(p.locator)+","+Math.min(200,Math.max(count,p.locator.index===undefined?count:p.locator.index+1))+","+JSON.stringify(visible)+")",
        contextId,returnByValue:false,objectGroup:"mmx-"+s.token,silent:true},f.child);
      frameCurrent(s,f);
      if(response.exceptionDetails)throw new Error("INVALID_SELECTOR");
      if(!response.result?.objectId)throw new Error("CDP_EVALUATION_FAILED");
      const properties=await send(s,"Runtime.getProperties",{objectId:response.result.objectId,ownProperties:true},f.child);
      const elements=[];
      for(const prop of properties.result||[]) {
        if(!/^\d+$/.test(prop.name)||!prop.value?.objectId||elements.length>=count)continue;
        const objectId=prop.value.objectId,info=await call(s,objectId,nodeInfo,[],f.child);
        if(!info||info.sensitive)continue;
        const described=await send(s,"DOM.describeNode",{objectId},f.child);
        const ref="n"+token().slice(0,24);
        s.refs.set(ref,{objectId,backendNodeId:described.node.backendNodeId,frameId:f.id,child:f.child,
          loader:f.loaderId,epoch:s.epoch,signature:JSON.stringify([info.tag,info.type,info.name,info.identity])});
        const {identity,...publicInfo}=info;
        elements.push({ref,frame_id:f.id,...publicInfo});
        while(s.refs.size>LIMIT.refs) {
          const oldest=s.refs.keys().next().value,entry=s.refs.get(oldest);s.refs.delete(oldest);
          send(s,"Runtime.releaseObject",{objectId:entry.objectId},entry.child).catch(()=>{});
        }
      }
      await send(s,"Runtime.releaseObject",{objectId:response.result.objectId},f.child);
      frameCurrent(s,f);
      return {elements,count:elements.length,limit:count,epoch:s.epoch,frame_id:f.id,content_is_untrusted:true};
    }
    async function target(s,ref) {
      const n=s.refs.get(ref);
      if(!n||n.epoch!==s.epoch)throw new Error("STALE_NODE_REF");
      await frameTree(s);const f=await frameFor(s,n.frameId);
      if(f.loaderId!==n.loader)throw new Error("STALE_NODE_REF");
      const info=await call(s,n.objectId,nodeInfo,[],n.child);
      if(!info?.connected||info.sensitive||JSON.stringify([info.tag,info.type,info.name,info.identity])!==n.signature)throw new Error("STALE_NODE_REF");
      if(info.disabled)throw new Error("TARGET_DISABLED");
      return {n,f,info};
    }
    async function point(s,n,f) {
      const local=await call(s,n.objectId,function(){
        const b=this.getBoundingClientRect(),x=b.left+b.width/2,y=b.top+b.height/2;
        let hit=this.getRootNode().elementFromPoint?.(x,y)||document.elementFromPoint(x,y);
        return {x,y,width:b.width,height:b.height,hit:!!hit&&(hit===this||this.contains(hit)),
          viewport_width:innerWidth,viewport_height:innerHeight};
      },[],n.child);
      if(!local?.hit||!local.width||!local.height||local.x<0||local.y<0||local.x>=local.viewport_width||local.y>=local.viewport_height)throw new Error("TARGET_OBSCURED");
      let x=local.x,y=local.y,cursor=f,depth=0;
      while(cursor.parent&&++depth<16){
        const parent=await frameFor(s,cursor.parent);
        const owner=await send(s,"DOM.getFrameOwner",{frameId:cursor.id},parent.child);
        const resolved=await send(s,"DOM.resolveNode",{backendNodeId:owner.backendNodeId},parent.child);
        const offset=await call(s,resolved.object.objectId,function(x,y){
          const b=this.getBoundingClientRect(),matrix=new DOMMatrix(getComputedStyle(this).transform);
          if(!matrix.is2D||Math.abs(matrix.b)>0.001||Math.abs(matrix.c)>0.001||matrix.a<=0||matrix.d<=0)return {hit:false};
          const sx=b.width/(this.offsetWidth||b.width),sy=b.height/(this.offsetHeight||b.height);
          const px=b.left+(this.clientLeft+x)*sx,py=b.top+(this.clientTop+y)*sy;
          const hit=this.getRootNode().elementFromPoint?.(px,py)||document.elementFromPoint(px,py);
          return {x:px,y:py,hit:hit===this&&px>=0&&py>=0&&px<innerWidth&&py<innerHeight};
        },[x,y],parent.child);
        await send(s,"Runtime.releaseObject",{objectId:resolved.object.objectId},parent.child);
        if(!offset?.hit)throw new Error("TARGET_OBSCURED");x=offset.x;y=offset.y;cursor=parent;
      }
      return {x,y};
    }
    async function key(s,spec) {
      const pieces=spec.split("+"),k=pieces.pop(),mods=pieces.reduce((m,x)=>m|({Alt:1,Ctrl:2,Control:2,Meta:4,Cmd:4,Shift:8})[x],0);
      if(pieces.some(x=>!["Alt","Ctrl","Control","Meta","Cmd","Shift"].includes(x)))throw new Error("INVALID_KEY");
      const actual=k==="Space"?" ":k;
      if(!Object.hasOwn(KEYS,k)&&k.length!==1)throw new Error("INVALID_KEY");
      const c=KEYS[k]||(k.length===1?k.toUpperCase().charCodeAt(0):0);
      const printable=mods===0&&(k.length===1||k==="Space"||k==="Enter");
      const data={key:actual,code:k.length===1?"Key"+k.toUpperCase():k,modifiers:mods,windowsVirtualKeyCode:c};
      await send(s,"Input.dispatchKeyEvent",{type:"keyDown",...data,...(printable?{text:k==="Enter"?"\r":actual}:{})});
      await send(s,"Input.dispatchKeyEvent",{type:"keyUp",...data});
    }
    async function interact(s,p,mark) {
      const {n,f}=await target(s,p.ref);
      if(["fill","type"].includes(p.kind)&&typeof p.text!=="string")throw new Error("INPUT_INVALID");
      if(p.kind==="select"&&typeof p.value!=="string")throw new Error("INPUT_INVALID");
      if(p.kind==="check"&&typeof p.checked!=="boolean")throw new Error("INPUT_INVALID");
      if(p.kind==="press"&&typeof p.key!=="string")throw new Error("INPUT_INVALID");
      mark();s.refs.delete(p.ref);
      await call(s,n.objectId,function(){this.scrollIntoView({block:"center",inline:"center",behavior:"instant"});return true;},[],n.child);
      if(["click","double_click","hover","drag","check"].includes(p.kind)) {
        const pos=await point(s,n,f);
        if(p.kind==="check") {
          const state=await call(s,n.objectId,function(){return {type:this.type,checked:this.checked};},[],n.child);
          if(!["checkbox","radio"].includes(state.type))throw new Error("INPUT_INVALID");
          if(state.checked===p.checked)return {changed:false,verified_checked:state.checked};
        }
        await send(s,"Input.dispatchMouseEvent",{type:"mouseMoved",...pos});
        if(p.kind!=="hover"){
          if(p.kind==="drag"){
            const other=await target(s,p.target_ref);const end=await point(s,other.n,other.f);
            await send(s,"Input.dispatchMouseEvent",{type:"mousePressed",...pos,button:"left",buttons:1,clickCount:1});
            for(let step=1;step<=8;step++)await send(s,"Input.dispatchMouseEvent",{type:"mouseMoved",x:pos.x+(end.x-pos.x)*step/8,y:pos.y+(end.y-pos.y)*step/8,button:"left",buttons:1});
            await send(s,"Input.dispatchMouseEvent",{type:"mouseReleased",...end,button:"left",buttons:0,clickCount:1});
          }else for(let c=1;c<=(p.kind==="double_click"?2:1);c++){
            await send(s,"Input.dispatchMouseEvent",{type:"mousePressed",...pos,button:"left",buttons:1,clickCount:c});
            await send(s,"Input.dispatchMouseEvent",{type:"mouseReleased",...pos,button:"left",buttons:0,clickCount:c});
          }
        }
      }else if(p.kind==="scroll"){
        await call(s,n.objectId,function(x,y){this.scrollBy({left:x,top:y,behavior:"instant"});return {left:this.scrollLeft,top:this.scrollTop};},[p.x||0,p.y||0],n.child);
      }else{
        const focus=await call(s,n.objectId,function(){
          this.focus();return this===this.getRootNode().activeElement||this===document.activeElement;
        },[],n.child);
        if(!focus)throw new Error("FOCUS_NOT_CONFIRMED");
        if(p.kind==="press")await key(s,p.key);
        if(p.kind==="type")await send(s,"Input.insertText",{text:p.text});
        if(["fill","select"].includes(p.kind)) {
          const out=await call(s,n.objectId,function(kind,value){
            if(this.readOnly||this.disabled)return {ok:false};
            if(kind==="select"){
              if(this.tagName!=="SELECT"||!Array.from(this.options).some(o=>o.value===value&&!o.disabled))return {ok:false};
              this.value=value;
            }else if(this.isContentEditable){this.textContent=value;}
            else{
              if(!["INPUT","TEXTAREA"].includes(this.tagName)||this.type==="file"||this.type==="password")return {ok:false};
              const proto=this.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
              Object.getOwnPropertyDescriptor(proto,"value").set.call(this,value);
            }
            this.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:value}));
            this.dispatchEvent(new Event("change",{bubbles:true}));
            return {ok:true,value:String(this.isContentEditable?this.textContent:this.value).slice(0,1000)};
          },[p.kind,p.kind==="select"?p.value:p.text],n.child);
          if(!out?.ok)throw new Error("INPUT_INVALID");
          return {refresh_required:true,readback:out};
        }
      }
      return {refresh_required:true,verification_required:true};
    }
    async function guardRaw(s,f,method,p) {
      if(!RAW_METHODS.has(method)||!DOMAINS.has(method.split(".")[0])||RESERVED.has(method))throw new Error("CDP_METHOD_OUT_OF_SCOPE");
      if(["DOM","DOMSnapshot","CSS","Accessibility"].includes(method.split(".")[0])){
        await frameTree(s);
        for(const sub of s.frames.values())if(sub.child===f.child)await frameFor(s,sub.id);
      }
      if(method==="Network.getResponseBody"){
        const req=s.requests.get(requestKey(f.child,p.requestId));
        if(s.networkTainted||!req||s.deniedRequests.has(req.request_id)||!req.complete||!await host.granted(siteURL(req.rawUrl)))throw new Error("RESPONSE_NOT_AVAILABLE");
      }
      if(method==="Page.getResourceContent"&&(!cleanURL(p.url)||!await host.granted(p.url)))throw new Error("SITE_PERMISSION_REQUIRED");
      if(method==="Network.getCertificate"&&(!cleanURL(p.origin)||new URL(p.origin).origin!==new URL(f.url).origin))throw new Error("SITE_PERMISSION_REQUIRED");
      if(method==="Page.navigate"){
        if(!cleanURL(p.url)||!await host.granted(p.url)||p.frameId&&p.frameId!==f.id)throw new Error("SITE_PERMISSION_REQUIRED");
      }
      if(Object.keys(p).some(k=>["sessionId","targetId","browserContextId","executionContextId","contextId","uniqueContextId","frameId"].includes(k))){
        if(!(method==="Page.navigate"&&p.frameId===f.id&&Object.keys(p).filter(k=>["sessionId","targetId","browserContextId","executionContextId","contextId","uniqueContextId"].includes(k)).length===0))
          throw new Error("CDP_TARGET_OVERRIDE_REFUSED");
      }
      if(method==="Runtime.evaluate"){
        const context=await world(s,f);p={...p,contextId:context,returnByValue:true,timeout:5000,objectGroup:"mmx-"+s.token};
      }
      if(["Page.navigate","Page.getResourceContent","Accessibility.getFullAXTree","Accessibility.getRootAXNode"].includes(method))p={...p,frameId:f.id};
      if(["Page.reload","Page.stopLoading"].includes(method)&&f.parent&&!f.child)throw new Error("CDP_METHOD_FRAME_SCOPE");
      function ownedObjects(value){
        if(!value||typeof value!=="object")return;
        for(const [key,item] of Object.entries(value)){
          if(key==="objectId"){
            const known=s.objects.get(item);if(!known||known.epoch!==s.epoch||known.child!==f.child)throw new Error("CDP_OBJECT_UNOWNED");
          }else if(item&&typeof item==="object")ownedObjects(item);
        }
      }
      ownedObjects(p);
      if(method==="Runtime.releaseObjectGroup"&&p.objectGroup!=="mmx-"+s.token)throw new Error("CDP_OBJECT_UNOWNED");
      frameCurrent(s,f);
      return p;
    }
    async function execute(r,mark) {
      const p=r.params,action=r.action;
      if(action==="cdp_attach")return {status:"OK",data:await attach(r,p,mark),effect:"APPLIED"};
      const s=sessions.get(r.tab_id);
      if(action==="cdp_status"){
        if(!s)return {status:"OK",data:{attached:false}};
        if(s.owner!==r.session_id||s.boot!==r.transport_boot_nonce)return {status:"CDP_OWNED_BY_ANOTHER_SESSION",data:{attached:true,owned:false}};
        return {status:"OK",data:{attached:true,owned:true,session:s.token,epoch:s.epoch,uncertain:s.uncertain,
          invalidated:!!s.invalidated,cleanup_pending:s.closing,cleanup_error:s.cleanupError||null,
          related_frames:s.relatedFrames,events:s.events.length,dropped_events:s.dropped,network_requests:s.requests.size,
          raw_methods:[...RAW_METHODS].sort(),minimum_chrome_version:125}};
      }
      if(action==="cdp_detach"){
        if(!s)return {status:"OK",data:{attached:false,released:true}};
        if(s.owner!==r.session_id||s.boot!==r.transport_boot_nonce)throw new Error("CDP_OWNED_BY_ANOTHER_SESSION");
        mark();const result=await reconcileRelease(s);
        return {status:result.released?"OK":"ACTION_EFFECT_UNKNOWN",data:result,
          effect:result.released?"APPLIED":"EFFECT_UNKNOWN"};
      }
      check(s,r);await host.tabFor(r);
      let data;
      if(action==="frames"){
        await frameTree(s);const frames=[];let excluded=0;
        for(const f of s.frames.values()){try{await frameFor(s,f.id);frames.push({frame_id:f.id,parent_id:f.parent,url:cleanURL(f.url)||f.url,name:f.name,related_target:!!f.child,loader_id:f.loaderId});}catch(_){excluded++;}}
        data={frames,excluded,epoch:s.epoch};
      }else if(action==="accessibility"){
        const f=await frameFor(s,p.frame_id);
        const out=await send(s,"Accessibility.getFullAXTree",{frameId:f.id},f.child);
        const nodes=(out.nodes||[]).filter(n=>!n.ignored).slice(0,p.limit||100).map(n=>({
          node_id:n.nodeId,backend_node_id:n.backendDOMNodeId,role:n.role?.value,name:cleanText(n.name?.value),
          value:n.role?.value==="textbox"?"[use explicit node inspection]":cleanText(n.value?.value),
          children:n.childIds?.slice(0,100),properties:(n.properties||[]).map(x=>({name:x.name,value:x.value?.value}))}));
        data={nodes,frame_id:f.id,total_nodes:out.nodes?.length||0,truncated:(out.nodes?.length||0)>nodes.length,content_is_untrusted:true};
      }else if(action==="dom"){
        const f=await frameFor(s,p.frame_id);
        if(p.pierce!==false)for(const sub of s.frames.values())if(sub.child===f.child)await frameFor(s,sub.id);
        const contextId=await world(s,f);
        const exp=p.selector?"document.querySelector("+JSON.stringify(p.selector)+")":"document.documentElement";
        const node=await send(s,"Runtime.evaluate",{expression:exp,contextId,returnByValue:false,objectGroup:"mmx-"+s.token},f.child);
        if(!node.result?.objectId)throw new Error("TARGET_NOT_FOUND");
        data=await send(s,"DOM.describeNode",{objectId:node.result.objectId,depth:p.depth??2,pierce:p.pierce!==false},f.child);
        frameCurrent(s,f);
      }else if(action==="locate"){data=await find(s,p,p.include_hidden!==true);}
      else if(action==="wait"){
        const until=Date.now()+(p.timeout_ms??5000),state=p.state||"visible";let matched=false,observation;
        do{
          host.current(r);await host.tabFor(r);
          observation=await find(s,{...p,limit:1},state==="visible"||state==="hidden");
          matched=["hidden","detached"].includes(state)?observation.count===0:observation.count>0;
          if(matched)break;
          if(Date.now()>=until)break;
          await new Promise(resolve=>setTimeout(resolve,Math.min(150,Math.max(0,until-Date.now()))));
        }while(Date.now()<=until);
        data={matched,state,observation,timed_out:!matched};
      }else if(action==="events"){
        const after=p.after||0,available=s.events.filter(e=>e.sequence>after&&(!p.method||e.method.startsWith(p.method)));
        const rows=available.slice(0,p.limit||60);
        data={events:rows,next_after:rows.at(-1)?.sequence||after,latest_sequence:s.sequence,has_more:available.length>rows.length,
          dropped_total:s.dropped,gap:!!s.events.length&&after<s.events[0].sequence-1,content_is_untrusted:true};
      }else if(action==="network"){
        const rows=[...s.requests.values()].filter(x=>!p.request_id||x.request_id===p.request_id).slice(-(p.limit||60)).map(x=>({...x,child:undefined,rawUrl:undefined}));
        data={requests:rows,observed_since_attach:true,headers_and_request_bodies_omitted:true,content_is_untrusted:true};
      }else if(action==="response_body"){
        const req=s.requests.get(p.request_id);if(s.networkTainted||s.deniedRequests.has(p.request_id)||!req||!req.complete)throw new Error("RESPONSE_NOT_AVAILABLE");
        if(!await host.granted(siteURL(req.rawUrl)))throw new Error("SITE_PERMISSION_REQUIRED");
        const out=await send(s,"Network.getResponseBody",{requestId:req.id},req.child);
        const offset=p.offset||0,limit=p.limit||16000;
        data={request_id:req.request_id,body:out.body.slice(offset,offset+limit),base64_encoded:out.base64Encoded,
          offset,total_characters:out.body.length,next_offset:offset+limit<out.body.length?offset+limit:null,
          content_is_untrusted:true};
      }else if(action==="result"){
        const value=s.results.get(p.result_id);if(value===undefined)throw new Error("RESULT_EXPIRED");
        const offset=p.offset||0,limit=p.limit||LIMIT.pageChars;
        data={result_id:p.result_id,text:value.slice(offset,offset+limit),offset,total_characters:value.length,
          next_offset:offset+limit<value.length?offset+limit:null,format:"json",content_is_untrusted:true};
      }else if(action==="evaluate"||action==="cdp"){
        const f=await frameFor(s,p.frame_id);let method,params;
        if(action==="evaluate"){
          method="Runtime.evaluate";
          const context=p.world==="page"?[...s.contexts?.values()||[]].find(c=>c.frameId===f.id&&c.child===f.child&&c.isDefault):null;
          if(p.world==="page"&&!context)throw new Error("PAGE_WORLD_UNAVAILABLE");
          params={expression:p.expression,contextId:context?.id||await world(s,f),returnByValue:true,awaitPromise:p.await_promise!==false,
            timeout:5000,objectGroup:"mmx-"+s.token,userGesture:false};
        }else {method=p.method;params=await guardRaw(s,f,method,{...(p.params||{})});}
        frameCurrent(s,f);mark();data=await send(s,method,params,f.child);
        if(!["Page.navigate","Page.reload"].includes(method))frameCurrent(s,f);
        if(action==="cdp"){
          const remember=value=>{if(!value||typeof value!=="object")return;for(const [key,item] of Object.entries(value)){
            if(key==="objectId"&&typeof item==="string")s.objects.set(item,{child:f.child,epoch:s.epoch});
            else if(item&&typeof item==="object")remember(item);
          }};remember(data);while(s.objects.size>2000)s.objects.delete(s.objects.keys().next().value);
        }
        data={result:data,frame_id:f.id,content_is_untrusted:true,verification_required:true};
      }else if(action==="interact"){data=await interact(s,p,mark);}
      else if(action==="upload"){
        if(chrome.extension?.isAllowedFileSchemeAccess && !await chrome.extension.isAllowedFileSchemeAccess())
          throw new Error("UPLOAD_FILE_ACCESS_REQUIRED");
        check(s,r);
        const {n}=await target(s,p.ref);
        const info=await call(s,n.objectId,function(){return {tag:this.tagName,type:this.type,multiple:this.multiple};},[],n.child);
        if(info.tag!=="INPUT"||info.type!=="file"||!info.multiple&&p.files.length>1)throw new Error("INPUT_INVALID");
        mark();s.refs.delete(p.ref);await send(s,"DOM.setFileInputFiles",{files:p.files,backendNodeId:n.backendNodeId},n.child);
        const readback=await call(s,n.objectId,function(){return Array.from(this.files).map(f=>({name:f.name,size:f.size,type:f.type}));},[],n.child);
        data={files:readback,verification_required:true};
      }else if(action==="download"){
        if(!await host.granted(p.url,["downloads"]))throw new Error("DOWNLOAD_PERMISSION_REQUIRED");
        check(s,r);
        mark();const id=await chrome.downloads.download({url:p.url,filename:"Mastermind/"+(p.filename||"download-"+Date.now()),saveAs:false});
        s.downloads.set(id,true);data={download_id:id,status:"started",verification_required:true};
      }else if(action==="downloads"){
        if(!await chrome.permissions.contains({permissions:["downloads"]}))throw new Error("DOWNLOAD_PERMISSION_REQUIRED");
        const ids=p.download_id===undefined?[...s.downloads.keys()]:[p.download_id];const rows=[];
        for(const id of ids.slice(-30)){
          if(!s.downloads.has(id))throw new Error("DOWNLOAD_NOT_OWNED");
          const found=await chrome.downloads.search({id});for(const x of found)rows.push({download_id:x.id,state:x.state,
            filename:x.filename,bytes_received:x.bytesReceived,total_bytes:x.totalBytes,error:x.error,danger:x.danger});
        }data={downloads:rows};
      }else if(action==="dialog"){
        if(!s.dialog||s.dialog.ref!==p.dialog_ref)throw new Error("STALE_DIALOG_REF");
        const dialog=s.dialog;s.dialog=null;
        mark();await send(s,"Page.handleJavaScriptDialog",{accept:p.accept,promptText:p.prompt||""},dialog.child);data={handled:true,dialog_ref:p.dialog_ref};
      }else if(action==="route"){
        mark();s.routes=p.rules;
        if(p.rules.length)await send(s,"Fetch.enable",{patterns:p.rules.map(x=>({urlPattern:x.url_pattern,requestStage:"Request"}))});
        else await send(s,"Fetch.disable");
        data={rules:p.rules,scope:"this attached tab; unhandled or ungranted requests continue",removed_on_detach:true};
      }else if(action==="emulate"){
        mark();
        if(p.reset){await send(s,"Emulation.clearDeviceMetricsOverride");await send(s,"Emulation.setEmulatedMedia",{media:"",features:[]});await send(s,"Emulation.setTimezoneOverride",{timezoneId:""});await send(s,"Emulation.setUserAgentOverride",{userAgent:""});}
        if(p.viewport){
          const v=p.viewport;if(!plain(v)||!integer(v.width,200,4096)||!integer(v.height,200,8192)||typeof v.mobile!=="boolean"||!Number.isFinite(v.device_scale_factor)||v.device_scale_factor<0.5||v.device_scale_factor>4)throw new Error("INPUT_INVALID");
          await send(s,"Emulation.setDeviceMetricsOverride",{width:v.width,height:v.height,mobile:v.mobile,deviceScaleFactor:v.device_scale_factor});
        }
        if(p.user_agent!==undefined){if(typeof p.user_agent!=="string"||p.user_agent.length>1000)throw new Error("INPUT_INVALID");await send(s,"Emulation.setUserAgentOverride",{userAgent:p.user_agent});}
        if(p.media!==undefined){if(!["screen","print",""].includes(p.media))throw new Error("INPUT_INVALID");await send(s,"Emulation.setEmulatedMedia",{media:p.media});}
        if(p.timezone!==undefined){if(typeof p.timezone!=="string"||p.timezone.length>100)throw new Error("INPUT_INVALID");await send(s,"Emulation.setTimezoneOverride",{timezoneId:p.timezone});}
        data={applied:true,reset_on_detach:true,verification_required:true};
      }else if(action==="capture"){
        const metrics=await send(s,"Page.getLayoutMetrics"),v=p.full_page?metrics.cssContentSize:metrics.cssVisualViewport;
        const width=v.width||v.clientWidth,height=v.height||v.clientHeight;
        if(!width||!height)throw new Error("SCREENSHOT_UNAVAILABLE");
        const scale=Math.min(1,(p.max_width||1600)/width,(p.max_height||(p.full_page?4096:1200))/height);
        const out=await send(s,"Page.captureScreenshot",{format:p.format||"jpeg",...(p.format==="png"?{}:{quality:p.quality||65}),
          fromSurface:true,captureBeyondViewport:!!p.full_page,clip:{x:p.full_page?0:v.pageX,y:p.full_page?0:v.pageY,width,height,scale}});
        if(out.data.length>700000)throw new Error("SCREENSHOT_TOO_LARGE");
        data={base64:out.data,mime_type:p.format==="png"?"image/png":"image/jpeg",scope:p.full_page?"full page":"viewport",
          width:Math.round(width*scale),height:Math.round(height*scale)};
      }else if(action==="pdf"){
        const out=await send(s,"Page.printToPDF",{landscape:!!p.landscape,printBackground:p.print_background!==false,scale:p.scale||1,transferMode:"ReturnAsBase64"});
        if(out.data.length>700000)throw new Error("PDF_TOO_LARGE");
        data={base64:out.data,mime_type:"application/pdf",scope:"selected document"};
      }
      await host.tabFor(r);check(s,r);
      return {status:"OK",data:["capture","pdf"].includes(action)?data:pack(s,data),
        effect:MUTATE.has(action)&&!["capture","pdf"].includes(action)?"APPLIED":"NOT_APPLIED"};
    }
    async function event(source,method,p,s) {
      if(!s||!usable(s))return;
      const child=source.sessionId||null;
      if(method==="Target.attachedToTarget"){
        const t=p.targetInfo;if(t?.type!=="iframe"||!await host.granted(t.url)){try{await send(s,"Target.detachFromTarget",{sessionId:p.sessionId},child);}catch(_){}return;}
        if(!usable(s))return;
        s.children.set(p.sessionId,{targetId:t.targetId,url:t.url});
        try{await send(s,"Page.enable",{},p.sessionId);await send(s,"Runtime.enable",{},p.sessionId);
          if(s.network)await send(s,"Network.enable",{maxTotalBufferSize:1000000,maxResourceBufferSize:500000,maxPostDataSize:0},p.sessionId);
          await send(s,"Target.setAutoAttach",{autoAttach:true,waitForDebuggerOnStart:false,flatten:true,filter:[{type:"iframe",exclude:false},{exclude:true}]},p.sessionId);
        }catch(_){emit(s,"Mastermind.frame_unavailable",{target_id:t.targetId});}
        s.frames.clear();return;
      }
      if(method==="Target.detachedFromTarget"){
        s.children.delete(p.sessionId);s.epoch=token();s.refs.clear();s.frames.clear();s.worlds.clear();s.objects.clear();s.framesStale=true;
        for(const [key,c] of s.contexts||[])if(c.child===p.sessionId)s.contexts.delete(key);return;
      }
      if(method==="Runtime.executionContextCreated"){
        s.contexts??=new Map();const c=p.context;s.contexts.set((child||"")+":"+c.id,{id:c.id,frameId:c.auxData?.frameId,origin:c.origin,isDefault:!!c.auxData?.isDefault,child});return;
      }
      if(method==="Runtime.executionContextDestroyed"){s.contexts?.delete((child||"")+":"+p.executionContextId);s.worlds.clear();return;}
      if(method==="Runtime.executionContextsCleared"){s.worlds.clear();if(!child)s.contexts?.clear();else for(const [k,v] of s.contexts||[])if(v.child===child)s.contexts.delete(k);return;}
      if(method==="Page.frameNavigated"){
        // Invalidate before any permission await. A child navigation must never
        // inherit its previous document's origin, context or node authority.
        s.epoch=token();s.refs.clear();s.worlds.clear();s.objects.clear();s.framesStale=true;
        if(!p.frame?.parentId&&!child)s.mainFrame=p.frame?.id;
        if(p.frame?.url&&!await host.granted(p.frame.url)){
          if(!child&&!p.frame.parentId){try{await release(s,"site_permission_changed");}catch(_){}return;}
        }
        emit(s,method,{frame_id:p.frame?.id,url:cleanURL(p.frame?.url)},child);return;
      }
      if(method==="Page.frameDetached"){s.epoch=token();s.refs.clear();s.worlds.clear();s.objects.clear();s.framesStale=true;return;}
      if(method==="Fetch.requestPaused"){
        const deadline=setTimeout(()=>{release(s,"interception_deadline").catch(()=>{});},2500);
        try{
          let allowed=false;try{allowed=await host.granted(p.request?.url);}catch(_){}
          const block=allowed&&s.routes.some(rule=>{
            const pattern=rule.url_pattern.replace(/[.+?^$(){}|[\]\\]/g,"\\$&").replace(/\*/g,".*");
            return rule.action==="block"&&new RegExp("^"+pattern+"$").test(p.request.url);
          });
          await send(s,block?"Fetch.failRequest":"Fetch.continueRequest",{requestId:p.requestId,...(block?{errorReason:"BlockedByClient"}:{})},child);
        }catch(_){emit(s,"Mastermind.interception_uncertain",{request_id:p.requestId});try{await release(s,"interception_failed");}catch(_){}}
        finally{clearTimeout(deadline);}
        return;
      }
      if(method.startsWith("Network.")){
        const id=p.requestId,identity=requestKey(child,id);let request=s.requests.get(identity);
        if(method==="Network.requestWillBeSent"||method==="Network.webSocketCreated"){
          const address=p.request?.url||p.url;
          s.requests.delete(identity);
          if(s.deniedRequests.has(identity))return;
          let permitted=false;try{permitted=await host.granted(siteURL(address));}catch(_){}
          if(!usable(s))return;
          if(!permitted){s.deniedRequests.add(identity);if(s.deniedRequests.size>1000){s.deniedRequests.clear();s.networkTainted=true;}return;}
          request={id,request_id:identity,url:cleanURL(address),rawUrl:address,method:p.request?.method||"GET",
            type:method==="Network.webSocketCreated"?"WebSocket":p.type,started_at:Date.now(),last_activity_at:Date.now(),received_bytes:0,stream_messages:0,complete:false,child};
          s.requests.set(identity,request);
          while(s.requests.size>LIMIT.requests)s.requests.delete(s.requests.keys().next().value);
        }
        if(!request)return;
        request.last_activity_at=Date.now();
        if(method==="Network.responseReceived"){
          let permitted=false;try{permitted=await host.granted(siteURL(p.response?.url));}catch(_){}
          if(!usable(s))return;
          if(!permitted){s.requests.delete(identity);s.deniedRequests.add(identity);if(s.deniedRequests.size>1000){s.deniedRequests.clear();s.networkTainted=true;}return;}
          request.rawUrl=p.response.url;request.url=cleanURL(p.response.url);request.status=p.response.status;request.mime_type=p.response.mimeType;request.protocol=p.response.protocol;request.from_cache=!!p.response.fromDiskCache;
        }
        if(method==="Network.dataReceived")request.received_bytes+=(p.dataLength||0);
        if(method==="Network.loadingFinished"){request.complete=true;request.received_bytes=p.encodedDataLength||request.received_bytes;}
        if(method==="Network.loadingFailed"){request.failed=true;request.error=cleanText(p.errorText);}
        if(method==="Network.eventSourceMessageReceived"||method==="Network.webSocketFrameReceived"||method==="Network.webSocketFrameSent"){
          request.stream_messages++;emit(s,method,{request_id:identity,event_name:p.eventName||null,
            characters:(p.data||p.response?.payloadData||"").length,...(s.streamData?{sample:cleanText(p.data||p.response?.payloadData)}:{})},child);
        }else if(!["Network.dataReceived","Network.requestWillBeSentExtraInfo","Network.responseReceivedExtraInfo"].includes(method)){
          emit(s,method,{request_id:identity,url:request.url,status:request.status,mime_type:request.mime_type,error:request.error},child);
        }return;
      }
      if(method==="Runtime.consoleAPICalled"||method==="Runtime.exceptionThrown"){
        const id=p.executionContextId||p.exceptionDetails?.executionContextId,c=s.contexts?.get((child||"")+":"+id);
        if(!c?.frameId||!cleanURL(c.origin)||!await host.granted(c.origin))return;
        await frameFor(s,c.frameId);
      }
      if(method==="Log.entryAdded"&&(!cleanURL(p.entry?.url)||!await host.granted(p.entry.url)))return;
      if(!usable(s))return;
      if(method==="Runtime.consoleAPICalled")emit(s,method,{level:p.type,text:(p.args||[]).map(x=>cleanText(x.value??x.description??x.type)).join(" ").slice(0,2000)},child);
      else if(method==="Runtime.exceptionThrown")emit(s,method,{text:cleanText(p.exceptionDetails?.text),description:cleanText(p.exceptionDetails?.exception?.description)},child);
      else if(method==="Log.entryAdded")emit(s,method,{level:p.entry?.level,text:cleanText(p.entry?.text),url:cleanURL(p.entry?.url)},child);
      else if(method==="Page.javascriptDialogOpening"){s.dialog={ref:"d"+token(),child};emit(s,method,{dialog_ref:s.dialog.ref,type:p.type,message:cleanText(p.message),url:cleanURL(p.url)},child);}
      else if(method==="Page.javascriptDialogClosed")s.dialog=null;
      else if(["Page.loadEventFired","Page.domContentEventFired","Inspector.targetCrashed"].includes(method))emit(s,method,{},child);
    }
    chrome.debugger.onEvent.addListener((source,method,p)=>{
      const s=sessions.get(source.tabId);if(!s||s.closing||s.invalidated||!connectionLive(s))return;
      if(method.startsWith("Target.")||method.startsWith("Runtime.executionContext")||
          ["Page.frameNavigated","Page.frameDetached","Page.javascriptDialogOpening","Page.javascriptDialogClosed"].includes(method)){
        event(source,method,p,s).catch(()=>{});return;
      }
      // Keep request/response/context events ordered across asynchronous permission checks.
      // Interception must resolve promptly even under a noisy page's event load.
      if(method==="Fetch.requestPaused"){event(source,method,p,s).catch(()=>{});return;}
      s.pendingEvents??=0;
      if(s.pendingEvents>=512){s.dropped++;s.sequence++;return;}
      s.pendingEvents++;
      s.eventTail=(s.eventTail||Promise.resolve()).then(()=>event(source,method,p,s)).catch(()=>{}).finally(()=>{s.pendingEvents--;});
    });
    chrome.debugger.onDetach.addListener(source=>{const s=sessions.get(source.tabId);if(s){invalidate(s);sessions.delete(source.tabId);}
      if(chrome.action)chrome.action.setBadgeText({tabId:source.tabId,text:""}).catch(()=>{});});
    chrome.permissions.onRemoved.addListener(()=>{for(const s of sessions.values())chrome.tabs.get(s.tabId)
      .then(t=>host.granted(t.url,["debugger"])).then(ok=>{if(!ok)return release(s,"permission_removed");}).catch(()=>{});});
    if(chrome.alarms){
      chrome.alarms.create("mmx-browser-cdp-resource-cleanup",{periodInMinutes:1});
      chrome.alarms.onAlarm.addListener(a=>{if(a.name==="mmx-browser-cdp-resource-cleanup")
        for(const s of sessions.values())if(!s.invalidated&&Date.now()-s.lastUsed>LIMIT.idleMs)release(s,"idle_expired").catch(()=>{});});
    }
    async function withDebugger(r,fn){
      const prior=sessions.get(r.tab_id);
      if(prior){check(prior,r);return fn((method,params)=>{check(prior,r);return send(prior,method,params);});}
      const attached=await attach(r,{network:false},()=>{});
      const s=sessions.get(r.tab_id);
      if(!s||s.token!==attached.session)throw new Error("CDP_TARGET_LOST");
      try{check(s,r);return await fn((method,params)=>{check(s,r);return send(s,method,params);});}
      finally{const result=await release(s);if(!result.released)throw new Error("CDP_RECONCILIATION_REQUIRED");}
    }
    return {execute,withDebugger,has:tabId=>sessions.has(tabId),owned:(tabId,session)=>sessions.get(tabId)?.owner===session,
      uiStatus:()=>[...sessions.values()].map(s=>({tab_id:s.tabId,owner:s.owner.slice(0,10),events:s.events.length,
        last_used:new Date(s.lastUsed).toISOString(),uncertain:s.uncertain,cleanup_pending:s.closing,invalidated:!!s.invalidated,
        cleanup_error:s.cleanupError||null})),
      diagnostics:()=>({last_attach_failure:lastAttachFailure,cleanup_pending:[...sessions.values()].filter(s=>s.closing).length,
        cleanup_uncertain:[...sessions.values()].filter(s=>s.uncertain).length}),
      releaseAll:()=>releaseAll("user_released"),
      reset:()=>releaseAll("connection_changed")};
  }
  root.MMXBrowserCDP={ACTIONS,READ,NO_SNAPSHOT,validate,create,queryNodes};
  if(typeof module!=="undefined"&&module.exports)module.exports=root.MMXBrowserCDP;
})(globalThis);
