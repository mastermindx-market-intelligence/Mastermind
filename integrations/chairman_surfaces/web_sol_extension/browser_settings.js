"use strict";

// Permission requests originate only in an explicit click in this extension page.
// The model/native transport has no permission-request operation.
(function () {
  const status = document.getElementById("status");
  const requiredSites = new Set(["https://chat.openai.com/*", "https://chatgpt.com/*"]);
  async function render(message="") {
    const permissions = await chrome.permissions.getAll();
    const control = ["tabs", "scripting"].every(p => permissions.permissions.includes(p));
    const visual = control && permissions.permissions.includes("debugger");
    status.textContent = message || `Page controls ${control ? "enabled" : "paused"}. Screenshots and native keys ${visual ? "enabled" : "disabled"}.`;
    document.getElementById("enable").disabled = control;
    document.getElementById("pause").disabled = !control && !visual;
    document.getElementById("downloads").disabled = permissions.permissions.includes("downloads");
    const files=await chrome.extension.isAllowedFileSchemeAccess();
    document.getElementById("file-access").textContent=files?"Chrome file access is enabled. Uploads remain limited to the host folders configured for Hermes.":
      "For uploads, open this extension’s Chrome Details and enable Allow access to file URLs.";
    document.getElementById("file-access-details").hidden=files;
    const list = document.getElementById("sites");
    list.replaceChildren();
    for (const origin of (permissions.origins || []).slice(0,128)) {
      const row = document.createElement("li");
      row.textContent = origin + (requiredSites.has(origin) ? " (existing ChatGPT adapter)" : "");
      list.append(row);
    }
  }
  async function connection() {
    try{
      const value=await chrome.runtime.sendMessage({kind:"MMX_BROWSER_UI_STATUS"});
      document.getElementById("version").textContent=value.version;
      document.getElementById("connection").textContent=value.ready?"Connected to the installed Hermes bridge.":"Native bridge: "+value.connection+". "+(value.native_error||"Load the matching runtime and extension version.");
      const failure=value.cdp_diagnostics?.last_attach_failure;
      document.getElementById("diagnostic").textContent=failure?"Last CDP attachment: "+failure.reason+". "+failure.detail:"";
      const list=document.getElementById("sessions");list.replaceChildren();
      for(const session of value.sessions){
        const row=document.createElement("li");
        row.textContent="Tab "+session.tab_id+" · Hermes session "+session.owner+" · "+session.events+" observations"+(session.uncertain?" · Needs reconciliation":"");
        list.append(row);
      }
      if(!value.sessions.length){const row=document.createElement("li");row.textContent="No attached tabs.";list.append(row);}
      document.getElementById("release").disabled=!value.sessions.length;
    }catch(_){document.getElementById("connection").textContent="The extension is not ready. Reload it in Chrome extensions, then refresh this page.";}
  }
  async function report(promise) {
    try {const approved = await promise;await render(approved ? "" : "Chrome did not grant the requested permission.");}
    catch (_) {await render("The permission change was unavailable. Check this extension's Chrome settings.");}
  }
  document.getElementById("enable").addEventListener("click",()=>report(chrome.permissions.request({permissions:["tabs","scripting"]})));
  document.getElementById("allow-all").addEventListener("click",()=>report(chrome.permissions.request({permissions:["tabs","scripting"],origins:["http://*/*","https://*/*"]})));
  document.getElementById("pause").addEventListener("click",()=>report(chrome.permissions.remove({permissions:["tabs","scripting","downloads"]})));
  document.getElementById("downloads").addEventListener("click",()=>report(chrome.permissions.request({permissions:["downloads"]})));
  document.getElementById("file-access-details").addEventListener("click",()=>chrome.tabs.create({url:"chrome://extensions/?id="+chrome.runtime.id}));
  document.getElementById("refresh").addEventListener("click",()=>{render();connection();});
  document.getElementById("release").addEventListener("click",async()=>{
    try{const result=await chrome.runtime.sendMessage({kind:"MMX_BROWSER_UI_RELEASE"});await connection();
      await render(result.results?.some(x=>!x.released)?"A debugger attachment still needs reconciliation.":"Attached tabs released.");}
    catch(_){await render("Release could not be confirmed. Check Chrome's debugger notice.");}
  });
  document.getElementById("clear-sites").addEventListener("click",async()=>{
    try {
      const permissions = await chrome.permissions.getAll();
      const origins = (permissions.origins || []).filter(p=>!requiredSites.has(p));
      if (origins.length) await chrome.permissions.remove({origins});
      await render();
    } catch (_) {await render("Website permissions could not be removed. Check Chrome's extension settings.");}
  });
  document.getElementById("site-form").addEventListener("submit",event=>{
    event.preventDefault();
    let website;
    try {
      website = new URL(document.getElementById("site").value);
      if (!["http:","https:"].includes(website.protocol) || website.username || website.password) throw new Error();
    } catch (_) {status.textContent = "Enter an HTTP or HTTPS website address without account credentials.";return;}
    report(chrome.permissions.request({permissions:["tabs","scripting"],origins:[website.protocol+"//"+website.hostname+"/*"]}));
  });
  const config = globalThis.MMX_WEB_SOL_INSTANCE;
  document.getElementById("profile").textContent = config && config.instanceId
    ? "Browser ID: " + config.instanceId : "This extension needs its installed profile configuration.";
  chrome.permissions.onAdded.addListener(()=>render());
  chrome.permissions.onRemoved.addListener(()=>render());
  render().catch(()=>{status.textContent = "Chrome permission information is unavailable.";});
  connection();
})();
