"use strict";
// Reach the composer on a long page (BR2 item 4): the snapshot walker stops
// at MAX_ELEMENTS (120), so on a long conversation the composer never gets a
// ref. snapshot params {ensure_role, ensure_name?} reserve a reachable ref
// for the first visible element of that role beyond the cap — without
// scrolling, focusing or changing the page. fill works offscreen through the
// ensured ref; click keeps its viewport gate. Native role semantics count
// (a contenteditable or textarea is a textbox). Isolated fixture Chromium.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const PAGE_JS = path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js");
const fixture = `<!doctype html><html><head><title>Long conversation</title></head><body>
  <main id="thread"></main>
  <div id="composer" contenteditable="true" role="textbox" aria-label="Message composer"></div>
</body></html>`;

async function mount(browser) {
  const page = await browser.newPage({viewport:{width:1100,height:700}});
  await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
  await page.goto("https://fixture.test/page");
  // Conversation shape: well past 120 observable elements before the
  // composer, each a link the snapshot walker must count.
  const shape = await page.evaluate(()=>{
    const thread=document.getElementById("thread");
    for(let i=0;i<150;i++){
      const p=document.createElement("p");
      p.textContent="Turn "+i+" of the long conversation.";
      const a=document.createElement("a");
      a.href="/cite/"+i; a.textContent="Citation "+i;
      p.append(a); thread.append(p);
    }
    return {links:thread.querySelectorAll("a").length,
      composerTop:document.getElementById("composer").getBoundingClientRect().top};
  });
  assert.equal(shape.links>120,true,"fixture has >120 elements before the composer");
  assert.equal(shape.composerTop>700,true,"composer starts below the viewport");
  await page.addScriptTag({path:PAGE_JS});
  await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
  const send=async(action,ref=null,params=null,snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
    {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params:params===null?{}:params,
     expires_at:new Date(Date.now()+60000).toISOString()});
  const snapshot=async(params={})=>{const r=await send("snapshot",null,params);assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
  return {page,send,snapshot};
}

(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    // 1. Plain snapshot: the cap bites and the composer has no ref.
    {
      const {page,send,snapshot}=await mount(browser);
      const s=await snapshot();
      assert.equal(s.elements_truncated,true,"the walk is truncated");
      assert.equal(s.elements.length,120);
      assert.equal(s.elements.some(e=>e.name==="Message composer"),false,"composer is past the cap");
      assert.equal(s.ensure,undefined,"a plain snapshot carries no ensure block");
      await page.close();
    }
    // 2. ensure_role=textbox reserves the composer's ref beyond the cap;
    //    no scroll, no focus, no DOM change; fill works through the ref.
    {
      const {page,send,snapshot}=await mount(browser);
      const s=await snapshot({ensure_role:"textbox"});
      assert.equal(s.ensure.found,true,JSON.stringify(s.ensure));
      assert.equal(s.ensure.role,"textbox");
      assert.ok(s.ensure.ref,"an ensured ref exists");
      const el=s.elements.find(e=>e.ref===s.ensure.ref);
      assert.ok(el,"the ensured ref is in elements");
      assert.equal(el.name,"Message composer");
      assert.equal(el.editable,true);
      assert.equal(s.elements.length,121,"one extra element beyond the cap");
      assert.equal(s.elements_truncated,true,"the walk itself is still truncated");
      const state=await page.evaluate(()=>({scrollY:window.scrollY,
        active:document.activeElement===document.body,
        composerText:document.getElementById("composer").textContent}));
      assert.equal(state.scrollY,0,"no scroll");
      assert.equal(state.active,true,"no focus change");
      assert.equal(state.composerText,"","no DOM change");
      // click keeps its viewport gate: the offscreen composer is refused
      // (checked before any fill — a fill's focus scrolls the box into view).
      const clicked=await send("click",s.ensure.ref,{},s.snapshot_id);
      assert.equal(clicked.ok,false);assert.equal(clicked.code,"TARGET_OFFSCREEN");
      // fill reaches the offscreen composer through a fresh ensured ref.
      const s2=await snapshot({ensure_role:"textbox"});
      const filled=await send("fill",s2.ensure.ref,{text:"Hello from far below the fold"},s2.snapshot_id);
      assert.equal(filled.ok,true,JSON.stringify(filled));
      assert.equal(filled.effect,"APPLIED");
      const held=await page.evaluate(()=>document.getElementById("composer").textContent);
      assert.equal(held,"Hello from far below the fold");
      await page.close();
    }
    // 3. ensure_name disambiguates; a mismatch finds nothing, typed.
    {
      const {page,send,snapshot}=await mount(browser);
      const hit=await snapshot({ensure_role:"textbox",ensure_name:"Message composer"});
      assert.equal(hit.ensure.found,true);
      assert.equal(hit.ensure.name,"Message composer");
      const miss=await snapshot({ensure_role:"textbox",ensure_name:"Absent box"});
      assert.equal(miss.ensure.found,false);
      assert.equal(miss.ensure.ref,null);
      assert.equal(miss.elements.length,120,"a miss adds nothing");
      await page.close();
    }
    // 4. A role already inside the cap reports its existing ref, no extra.
    {
      const {page,send,snapshot}=await mount(browser);
      const s=await snapshot({ensure_role:"link"});
      assert.equal(s.ensure.found,true);
      assert.equal(s.elements.length,120,"no extra element when the role is already present");
      assert.ok(s.elements.some(e=>e.ref===s.ensure.ref));
      await page.close();
    }
    // 5. Native semantics: a textarea with no role attribute is a textbox.
    {
      const {page,send,snapshot}=await mount(browser);
      await page.evaluate(()=>{
        const ta=document.createElement("textarea");
        ta.setAttribute("aria-label","Late textarea");
        document.body.append(ta);
        document.getElementById("composer").removeAttribute("role");
      });
      const s=await snapshot({ensure_role:"textbox"});
      assert.equal(s.ensure.found,true,JSON.stringify(s.ensure));
      const el=s.elements.find(e=>e.ref===s.ensure.ref);
      assert.ok(el.tag==="textarea"||el.name==="Message composer","native textbox semantics match");
      await page.close();
    }
    // 6. Bad ensure params are INVALID_REQUEST and consume nothing.
    {
      const {page,send,snapshot}=await mount(browser);
      for(const bad of [{ensure_role:""},{ensure_role:"x".repeat(41)},{ensure_role:"textbox",extra:1},
                        {ensure_name:"only name"},{ensure_role:"text\nbox"},{ensure_role:5}]) {
        const r=await send("snapshot",null,bad);
        assert.equal(r.ok,false,JSON.stringify(bad));
        assert.equal(r.code,"INVALID_REQUEST",JSON.stringify(bad));
      }
      const s=await snapshot();
      assert.equal(s.elements.length,120,"the page world still works after refusals");
      await page.close();
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["composer past the 120-element cap gets a reachable ref via ensure_role",
             "no scroll, no focus, no DOM change; fill works offscreen through the ref",
             "click keeps TARGET_OFFSCREEN","ensure_name hit and typed miss",
             "role already in cap reports its existing ref","native textarea/contenteditable textbox semantics",
             "bad ensure params are INVALID_REQUEST"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});