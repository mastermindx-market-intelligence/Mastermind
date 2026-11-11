"use strict";
// Real DOM proof in an isolated fixture browser. Never uses an installed profile.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const fixture = `<!doctype html><html><head><title>Browser control fixture</title></head><body>
  <label>Name <input id="name" value="before"></label>
  <label><input id="agree" type="checkbox"> Agree</label>
  <label>Choice <select id="choice"><option value="first">First</option><option value="second">Second</option></select></label>
  <label>Password <input id="password" type="password" value="SECRET_SENTINEL"></label>
  <label>Card <input id="card" autocomplete="section-checkout billing cc-number" value="CARD_SENTINEL"></label>
  <label>Code <input id="code" autocomplete="one-time-code" value="OTP_SENTINEL"></label>
  <textarea id="multiline" aria-label="Notes">Initial notes</textarea>
  <button id="click" onclick="document.getElementById('result').textContent='Clicked'">Apply</button>
  <div role="button" id="nonfocus">Nonfocusable control</div>
  <div id="result" aria-live="polite">Waiting</div>
  <div style="height:1800px">Long page</div><button id="bottom">Bottom control</button>
</body></html>`;
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:700}});
    await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
    const install=async()=>{
      await page.addScriptTag({path:path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js")});
      await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
    };
    await page.goto("https://fixture.test/page?private=query");await install();
    const send=async(action,snapshot=null,ref=null,params={},session=SESSION)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:session,snapshot_id:snapshot,ref,params,expires_at:new Date(Date.now()+45000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true);return r.data;};
    let s=await snapshot();
    assert.equal(s.url,"https://fixture.test/page");assert.equal(s.scroll_ref,"page");
    assert.equal(JSON.stringify(s).includes("SECRET_SENTINEL"),false);
    assert.equal(JSON.stringify(s).includes("CARD_SENTINEL"),false);
    assert.equal(JSON.stringify(s).includes("OTP_SENTINEL"),false);
    assert.equal(s.elements.some(e=>["Password","Card","Code"].includes(e.name)),false);
    let name=s.elements.find(e=>e.name==="Name");assert.equal(name.value,"before");assert.equal(name.editable,true);
    assert.equal((await send("fill",s.snapshot_id,name.ref,{text:"Hermes changed this"})).effect,"APPLIED");
    assert.equal((await send("click",s.snapshot_id,name.ref)).code,"STALE_SNAPSHOT");
    s=await snapshot();name=s.elements.find(e=>e.name==="Name");assert.equal(name.value,"Hermes changed this");
    assert.equal((await send("fill",s.snapshot_id,name.ref,{text:"wrong session"},"c".repeat(64))).code,"STALE_SNAPSHOT");
    const checkbox=s.elements.find(e=>e.name==="Agree");assert.equal(checkbox.checked,false);
    await send("click",s.snapshot_id,checkbox.ref);s=await snapshot();assert.equal(s.elements.find(e=>e.name==="Agree").checked,true);
    const select=s.elements.find(e=>e.name==="Choice");await send("select",s.snapshot_id,select.ref,{value:"second"});
    s=await snapshot();assert.equal(s.elements.find(e=>e.name==="Choice").value,"second");
    assert.equal(s.elements.find(e=>e.name==="Choice").options.find(o=>o.value==="second").selected,true);
    const button=s.elements.find(e=>e.name==="Apply");await send("click",s.snapshot_id,button.ref);s=await snapshot();assert.match(s.text,/Clicked/);
    const stale=s.elements.find(e=>e.name==="Apply");await page.locator("#click").evaluate(e=>{e.textContent="Different action";});
    assert.equal((await send("click",s.snapshot_id,stale.ref)).code,"TARGET_CHANGED");
    s=await snapshot();const bottom=s.elements.find(e=>e.name==="Bottom control");assert.equal((await send("click",s.snapshot_id,bottom.ref)).code,"TARGET_OFFSCREEN");
    assert.equal((await send("scroll",s.snapshot_id,"page",{x:0,y:600})).effect,"APPLIED");
    assert.ok(await page.evaluate(()=>scrollY)>0);await page.evaluate(()=>scrollTo(0,0));
    s=await snapshot();await page.locator("#name").focus();
    const nonfocus=s.elements.find(e=>e.name==="Nonfocusable control");const unfocused=await send("focus_ref",s.snapshot_id,nonfocus.ref);
    assert.equal(unfocused.ok,false);assert.equal(unfocused.code,"FOCUS_NOT_CONFIRMED");
    s=await snapshot();name=s.elements.find(e=>e.name==="Name");
    const prepared=await send("focus_ref",s.snapshot_id,name.ref);assert.equal(prepared.ok,true);
    assert.equal((await send("validate_focus",s.snapshot_id,name.ref,{token:prepared.data.focus_token})).ok,true);
    await page.locator("#choice").focus();assert.equal((await send("validate_focus",s.snapshot_id,name.ref,{token:prepared.data.focus_token})).code,"FOCUS_NOT_CONFIRMED");
    await page.reload();await install();assert.equal((await send("validate_focus",s.snapshot_id,name.ref,{token:prepared.data.focus_token})).ok,false);
    // diagnostics is a snapshot-independent read: with no snapshot observed yet,
    // with a live snapshot present, and with the matching id, it must answer.
    const d0=await send("diagnostics",null);assert.equal(d0.ok,true,`no-snapshot diagnostics: ${JSON.stringify(d0)}`);
    s=await snapshot();
    const d1=await send("diagnostics",null);assert.equal(d1.ok,true,`live-snapshot null-id diagnostics: ${JSON.stringify(d1)}`);
    const d2=await send("diagnostics",s.snapshot_id);assert.equal(d2.ok,true);
    s=await snapshot();name=s.elements.find(e=>e.name==="Name");await page.locator("#name").evaluate(e=>e.remove());
    assert.equal((await send("fill",s.snapshot_id,name.ref,{text:"must not apply"})).code,"TARGET_CHANGED");
    await page.evaluate(()=>{for(let i=0;i<3000;i++){const b=document.createElement("button");b.textContent="Item "+i;document.body.append(b);}});
    s=await snapshot();assert.ok(s.elements.length<=120);assert.equal(s.elements_truncated,true);
    assert.ok(Buffer.byteLength(JSON.stringify(s))<50000);
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",cases:["sensitive exclusions","form readback","single-use refs","session separation","changed target","offscreen target","page scroll","focus proof","same-URL reload","bounded snapshot"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

