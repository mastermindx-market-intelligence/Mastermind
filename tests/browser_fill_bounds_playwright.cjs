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
  <div id="trickle" contenteditable="true" role="textbox" aria-label="trickle editor"></div>
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
      const orig=document.execCommand.bind(document);
      // slow editor: every editor-pipeline execCommand call costs ~4ms, so a
      // few hundred lines outlast the insertion time bound.
      const slow=document.getElementById("slow");
      document.execCommand=(cmd,ui,val)=>{
        const sel=document.getSelection();
        if((cmd==="insertText"||cmd==="insertParagraph") && sel && slow.contains(sel.anchorNode)){
          const until=performance.now()+4; while(performance.now()<until){/* busy */}
        }
        return orig(cmd,ui,val);
      };
      // The trickle editor uses a deterministic synthetic clock, not a busy
      // wait. Date.now is wrapped: it freezes at the first trickle call
      // (machine load then cannot leak real elapsed time into the bound) and
      // the trickle phase (calls past 3840 = lines past 1920) advances it by
      // exactly 12 synthetic ms per call. Every checkpoint up to line 1920
      // sees zero added clock, and the final checkpoint — after the last of
      // 1984 lines was inserted — is the only one past the 1500 ms bound, on
      // any machine load. (Literals here because page.evaluate carries no
      // Node bindings.)
      const trickle=document.getElementById("trickle");
      const realNow=Date.now.bind(Date);
      window.__clockExtra=0;
      window.__clockFrozenAt=0;
      Date.now=()=>(window.__clockFrozenAt||realNow())+window.__clockExtra;
      let trickleCalls=0;
      const slowAwareExec=document.execCommand;
      document.execCommand=(cmd,ui,val)=>{
        const sel=document.getSelection();
        if((cmd==="insertText"||cmd==="insertParagraph") && sel && trickle.contains(sel.anchorNode)){
          if(!window.__clockFrozenAt)window.__clockFrozenAt=realNow();
          trickleCalls+=1;
          if(trickleCalls>3840)window.__clockExtra+=12;
        }
        return slowAwareExec(cmd,ui,val);
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
    // Ruling 13 / p2#2: a stop at the time bound AFTER everything was
    // inserted reports what the read-back saw — APPLIED with the bound
    // disclosed — never a false NOT_APPLIED that invites a duplicate fill.
    // The trickle editor passes every checkpoint inside the bound and only
    // exceeds it at the last line's checkpoint, with all 1984 lines in.
    {
      const s=await snapshot();
      const el=await element("trickle editor",s);
      const text=Array.from({length:1984},(_,i)=>"trickle "+i).join("\n");
      const r=await send("fill",el.ref,text,s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r.data).slice(0,200));
      assert.equal(r.code,"OK");
      assert.equal(r.effect,"APPLIED","everything inserted: the read-back decides the effect");
      assert.equal(r.data.time_bound_exceeded,true,"the receipt still discloses the bound");
      assert.equal(r.data.lines_inserted,1984,"all lines were inserted before the stop");
      assert.equal(r.data.box_characters,r.data.asked_characters,"the box holds the whole asked text");
      assert.equal(r.data.first_diff_offset,undefined);
      assert.equal(await page.evaluate(()=>document.getElementById("trickle").innerText.replace(/\n+$/,"")),
        text.replace(/\n+$/,""),"the box genuinely holds every line");
      // The genuinely partial stop above still stays NOT_APPLIED.
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["30,000-newline fill refused pre-insertion, snapshot intact",
             "cap boundary: 2000 lines fill, 2001 refused",
             "slow editor stops under the time bound with typed FILL_TIME_BOUND and honest partial state",
             "bound exceeded after everything inserted: APPLIED with time_bound_exceeded, never a false NOT_APPLIED"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
