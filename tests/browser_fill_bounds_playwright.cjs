"use strict";
// Fill bounds (SCORE e2#2): a fill can never freeze the tab. Line counts past
// the cap are refused before the snapshot is consumed or the box is touched,
// and the per-line editor insertion loop runs under a time bound that stops
// with a typed FILL_TIME_BOUND outcome naming how far it got. Isolated
// fixture Chromium only.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const fixture = `<!doctype html><html><head><title>Fill bounds fixture</title></head><body>
  <div id="plain" contenteditable="true" role="textbox" aria-label="plain editable"></div>
  <div id="slow" contenteditable="true" role="textbox" aria-label="slow editor"></div>
  <textarea id="area" aria-label="plain textarea"></textarea>
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
      // slow editor: every editor-pipeline execCommand call costs ~4ms, so a
      // few hundred lines outlast the insertion time bound.
      const slow=document.getElementById("slow");
      const orig=document.execCommand.bind(document);
      document.execCommand=(cmd,ui,val)=>{
        const sel=document.getSelection();
        if((cmd==="insertText"||cmd==="insertParagraph") && sel && slow.contains(sel.anchorNode)){
          const until=performance.now()+4; while(performance.now()<until){/* busy */}
        }
        return orig(cmd,ui,val);
      };
    });
    const send=async(action,ref=null,text=null,snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params:text===null?{}:{text},
       expires_at:new Date(Date.now()+60000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
    const element=async(label,s)=>s.elements.find(e=>e.name===label);

    // A 30,000-newline fill is refused up front: typed INPUT_REFUSED, the box
    // untouched, and the snapshot NOT consumed — the same observation still
    // authorizes the next fill.
    {
      const s=await snapshot();
      const el=await element("plain editable",s);
      await page.evaluate(()=>document.getElementById("plain").textContent="sentinel");
      const refused=await send("fill",el.ref,"a\n".repeat(15000),s.snapshot_id);
      assert.equal(refused.code,"INPUT_REFUSED","30,000 newlines never start inserting");
      assert.equal(refused.effect,"NOT_APPLIED");
      assert.equal(await page.evaluate(()=>document.getElementById("plain").textContent),"sentinel",
        "the box is untouched by the refusal");
      const follow=await send("fill",el.ref,"ok",s.snapshot_id);
      assert.equal(follow.effect,"APPLIED","the same snapshot still authorizes a fill");
    }
    // Cap boundary: 2000 normalized line breaks still fill (instantly through
    // the value channel), 2001 is refused.
    {
      const s=await snapshot();
      const area=await element("plain textarea",s);
      const atCap=await send("fill",area.ref,"\n".repeat(2000),s.snapshot_id);
      assert.equal(atCap.effect,"APPLIED","2000 lines is at the cap, not past it");
      const s2=await snapshot();
      const area2=await element("plain textarea",s2);
      const past=await send("fill",area2.ref,"\n".repeat(2001),s2.snapshot_id);
      assert.equal(past.code,"INPUT_REFUSED");
    }
    // A slow editor cannot stretch the insertion loop past the time bound:
    // the fill stops with a typed FILL_TIME_BOUND, says how many lines got in,
    // reports the partial box honestly, and the tab still answers afterwards.
    {
      const s=await snapshot();
      const el=await element("slow editor",s);
      const started=Date.now();
      const r=await send("fill",el.ref,Array.from({length:600},(_,i)=>"line "+i).join("\n"),s.snapshot_id);
      const elapsed=Date.now()-started;
      assert.equal(r.code,"FILL_TIME_BOUND","the loop stops under the bound");
      assert.equal(r.effect,"NOT_APPLIED");
      assert.equal(typeof r.data.lines_inserted,"number");
      assert.equal(r.data.lines_inserted>=64,true,"at least one check interval ran");
      assert.equal(r.data.lines_inserted<600,true,"it stopped before completing");
      assert.equal(typeof r.data.time_bound_ms,"number");
      assert.equal(r.data.box_characters<r.data.asked_characters,true,"the box holds a partial insertion");
      assert.equal(typeof r.data.first_diff_offset,"number","the partial state is reported honestly");
      assert.equal(elapsed<10000,true,`stopped in ${elapsed}ms, not after the full 600-line run`);
      const after=await snapshot();
      const plain=await element("plain editable",after);
      const ok=await send("fill",plain.ref,"still alive",after.snapshot_id);
      assert.equal(ok.effect,"APPLIED","the tab is responsive after the bound stop");
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["30,000-newline fill refused pre-insertion, snapshot intact",
             "cap boundary: 2000 lines fill, 2001 refused",
             "slow editor stops under the time bound with typed FILL_TIME_BOUND and honest partial state"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
