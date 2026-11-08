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
    const list = document.getElementById("sites");
    list.replaceChildren();
    for (const origin of (permissions.origins || []).slice(0,128)) {
      const row = document.createElement("li");
      row.textContent = origin + (requiredSites.has(origin) ? " (existing ChatGPT adapter)" : "");
      list.append(row);
    }
  }
  async function report(promise) {
    try {const approved = await promise;await render(approved ? "" : "Chrome did not grant the requested permission.");}
    catch (_) {await render("The permission change was unavailable. Check this extension's Chrome settings.");}
  }
  document.getElementById("enable").addEventListener("click",()=>report(chrome.permissions.request({permissions:["tabs","scripting"]})));
  document.getElementById("allow-all").addEventListener("click",()=>report(chrome.permissions.request({permissions:["tabs","scripting"],origins:["http://*/*","https://*/*"]})));
  document.getElementById("pause").addEventListener("click",()=>report(chrome.permissions.remove({permissions:["tabs","scripting"]})));
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
})();
