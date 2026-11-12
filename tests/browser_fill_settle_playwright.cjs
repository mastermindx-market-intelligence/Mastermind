"use strict";
// Fill settle (deputy ruling 13, SCORE p2#1): APPLIED means the box held the
// asked content when it was read again after the page's pending microtasks and
// one settle interval (at most 500 ms, stated in the receipt). A model-owning
// editor that reverts the box on a microtask after the fill must be caught by
// the receipt (FILL_MISMATCH, box-unchanged) instead of being answered APPLIED
// synchronously; a page that changes the box later than the interval is
// outside the receipt and APPLIED stands. Isolated fixture Chromium only.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const SETTLE = 250;
const fixture = `<!doctype html><html><head><title>Fill settle fixture</title></head><body>
  <div id="reverting" contenteditable="true" role="textbox" aria-label="reverting editor"></div>
  <div id="late" contenteditable="true" role="textbox" aria-label="late editor"></div>
  <div id="plain" contenteditable="true" role="textbox" aria-label="plain editor"></div>
  <textarea id="area" aria-label="settling textarea"></textarea>
</body></html>`;
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:700}});
    await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
    await page.goto("https://fixture.test/page");
    await page.addScriptTag({path:path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js")});
    await page.evaluate(()=>{
      window.browserFixturePage=window.MMXBrowserPageFactory(window);
      // A model-owning editor: one MutationObserver microtask after any write
      // into #reverting, the editor's own model rewrites the box back. The
      // guard flag stops the observer from fighting its own revert.
      const box=document.getElementById("reverting");
      const original=box.textContent;
      let armed=true;
      new MutationObserver(()=>{
        if(!armed) return;
        armed=false;
        box.textContent=original;
      }).observe(box,{childList:true,characterData:true,subtree:true});
      // A late editor: reverts the box long after the settle interval, so the
      // change is outside the receipt by ruling 13.
      const late=document.getElementById("late");
      let lateArmed=true;
      new MutationObserver(()=>{
        if(!lateArmed) return;
        lateArmed=false;
        // 650ms is past the 250ms settle interval; a literal here because
        // page.evaluate carries no Node-scope bindings.
        setTimeout(()=>{late.textContent="reverted far later";},650);
      }).observe(late,{childList:true,characterData:true,subtree:true});
    });
    const send=async(action,ref=null,text=null,snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params:text===null?{}:{text},
       expires_at:new Date(Date.now()+60000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
    const element=async(label,s)=>s.elements.find(e=>e.name===label);

    // A revert one microtask after the write is inside the receipt: the fill
    // must answer FILL_MISMATCH naming the reverted box, never APPLIED.
    {
      const s=await snapshot();
      const el=await element("reverting editor",s);
      const r=await send("fill",el.ref,"typed by the bridge",s.snapshot_id);
      assert.equal(r.ok,false,`revert must be caught, got ${JSON.stringify(r.data&&r.data.read_back)}`);
      assert.equal(r.code,"FILL_MISMATCH","a microtask revert is a mismatch");
      assert.equal(r.effect,"NOT_APPLIED");
      assert.equal(r.data.mismatch_kind,"box-unchanged","the editor reverted the box to its own model");
      assert.equal(r.data.settle_interval_ms,SETTLE,"the receipt states the settle interval");
      assert.equal(await page.evaluate(()=>document.getElementById("reverting").textContent),"",
        "the box really was reverted");
      // An editor that instead rewrites the box to different text of its own
      // is answered content-differs — either way, never APPLIED.
      const rewrite=await page.evaluate(()=>{
        const b=document.getElementById("reverting");
        b.textContent="seed";return b.textContent;
      });
      const s2=await snapshot();
      const el2=await element("reverting editor",s2);
      await page.evaluate(()=>{
        const b=document.getElementById("reverting");
        let once=true;
        new MutationObserver(()=>{if(!once)return;once=false;b.textContent="the model rewrote this";})
          .observe(b,{childList:true,characterData:true,subtree:true});
      });
      const rewritten=await send("fill",el2.ref,"operator text",s2.snapshot_id);
      assert.equal(rewritten.code,"FILL_MISMATCH");
      assert.equal(rewritten.data.mismatch_kind,"content-differs");
      assert.equal(rewrite,"seed");
    }
    // A change later than the settle interval is outside the receipt: APPLIED
    // stands, with the interval stated so the operator knows the window.
    {
      const s=await snapshot();
      const el=await element("late editor",s);
      const r=await send("fill",el.ref,"answered within the window",s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(r.effect,"APPLIED","a later-than-interval change is outside the receipt");
      assert.equal(r.data.settle_interval_ms,SETTLE);
      // Headless timer slop can run a few hundred ms late; poll for the late
      // revert instead of racing one fixed wait.
      let reverted=false;
      for(let i=0;i<40 && !reverted;i++) {
        await page.waitForTimeout(100);
        reverted=await page.evaluate(()=>document.getElementById("late").textContent==="reverted far later");
      }
      assert.equal(reverted,true,"the late revert did eventually happen — after the receipt's window");
    }
    // An honest fill waits the interval before reading back: the receipt
    // states the interval and the dispatch really took at least that long.
    {
      const s=await snapshot();
      const el=await element("plain editor",s);
      const started=Date.now();
      const r=await send("fill",el.ref,"settled truth",s.snapshot_id);
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.settle_interval_ms,SETTLE);
      assert.equal(Date.now()-started>=SETTLE-25,true,"the read-back happened after the settle interval");
    }
    // The value channel settles the same way (async frameworks rewrite
    // textarea values on input events).
    {
      const s=await snapshot();
      const area=await element("settling textarea",s);
      const r=await send("fill",area.ref,"value channel settles too",s.snapshot_id);
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.settle_interval_ms,SETTLE);
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["microtask revert answered FILL_MISMATCH box-unchanged, never APPLIED",
             "later-than-interval change outside the receipt: APPLIED stands",
             "receipt states settle_interval_ms and the dispatch really waits",
             "value-channel fills settle identically"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
