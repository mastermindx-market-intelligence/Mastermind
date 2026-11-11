"use strict";
// Paste-path proof in an isolated fixture browser: fill size ceiling and
// line-break fidelity for both field kinds (textarea and contenteditable).
// Never uses an installed profile. Complements browser_page_playwright.cjs.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const fixture = `<!doctype html><html><head><title>Paste fixture</title></head><body>
  <textarea id="plain-area" rows="4" aria-label="plain textarea"></textarea>
  <div id="editable" contenteditable="true" role="textbox" aria-multiline="true" aria-label="editable box"></div>
</body></html>`;
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:700}});
    await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
    await page.goto("https://fixture.test/page");
    await page.addScriptTag({path:path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js")});
    await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
    const send=async(action,snapshot=null,ref=null,params={})=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params,expires_at:new Date(Date.now()+45000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
    const block=n=>Array.from({length:n},(_,i)=>"line-"+String(i).padStart(4,"0")+" "+"x".repeat(90)).join("\n"); // 100 chars/line
    const newlineCount=s=>(s.match(/\n/g)||[]).length;

    // Size ladder, textarea: every operator size through 24,000 must apply whole.
    for (const size of [2000,4000,8000,16000,24000]) {
      let s=await snapshot();const area=s.elements.find(e=>e.name==="plain textarea");
      const text=block(size/100);
      const r=await send("fill",s.snapshot_id,area.ref,{text});
      assert.equal(r.effect,"APPLIED",`textarea ${size}: ${JSON.stringify(r)}`);
      const dom=await page.evaluate(()=>document.getElementById("plain-area").value);
      assert.equal(dom.length,size+size/100-1,`textarea ${size} length ${dom.length}`);
      assert.equal(newlineCount(dom),size/100-1,`textarea ${size} newlines`);
    }
    // New ceiling is 30,000 characters: applies whole; above it refuses with the box untouched.
    {
      let s=await snapshot();const area=s.elements.find(e=>e.name==="plain textarea");
      const text30k=block(300).slice(0,30000); // exactly 30,000 characters total
      const r=await send("fill",s.snapshot_id,area.ref,{text:text30k});
      assert.equal(r.effect,"APPLIED",`textarea 30000: ${JSON.stringify(r)}`);
      const dom=await page.evaluate(()=>document.getElementById("plain-area").value);
      assert.equal(dom.length,30000,`textarea 30000 length ${dom.length}`);
      s=await snapshot();const again=s.elements.find(e=>e.name==="plain textarea");
      const refused=await send("fill",s.snapshot_id,again.ref,{text:"y".repeat(30001)});
      assert.equal(refused.code,"INPUT_REFUSED","30001 must refuse");
      const kept=await page.evaluate(()=>document.getElementById("plain-area").value);
      assert.equal(kept.length,30000,"refused fill changed nothing");
    }
    // Contenteditable: size ladder with paragraphs that survive in the editor's own model.
    for (const size of [2000,24000]) {
      let s=await snapshot();const box=s.elements.find(e=>e.name==="editable box");
      const text=block(size/100);
      const r=await send("fill",s.snapshot_id,box.ref,{text});
      assert.equal(r.effect,"APPLIED",`editable ${size}: ${JSON.stringify(r)}`);
      const dom=await page.evaluate(()=>{
        const n=document.getElementById("editable");
        return {text:n.textContent,inner:n.innerText,blocks:n.querySelectorAll("p,div,br").length};
      });
      assert.equal(dom.inner.length>=size-((size/100)-1),true,
        `editable ${size} innerText keeps content (${dom.inner.length})`);
      assert.equal(newlineCount(dom.inner),size/100-1,
        `editable ${size} innerText line breaks (${newlineCount(dom.inner)})`);
    }
    // Contenteditable replacement semantics: a second fill replaces, never appends.
    {
      let s=await snapshot();const box=s.elements.find(e=>e.name==="editable box");
      const r=await send("fill",s.snapshot_id,box.ref,{text:"one\n two\n three"});
      assert.equal(r.effect,"APPLIED");
      const inner=await page.evaluate(()=>document.getElementById("editable").innerText);
      assert.equal(newlineCount(inner),2,`replacement fill paragraphs (${JSON.stringify(inner)})`);
    }
    // Read-back honesty: snapshot value reports the box truthfully (truncated flag, no flattening).
    {
      const s=await snapshot();const box=s.elements.find(e=>e.name==="editable box");
      assert.equal(box.value_truncated,false);
      assert.equal(box.value.includes("\n"),true,`read-back keeps paragraphs (${JSON.stringify(box.value)})`);
      assert.equal(box.value.startsWith("one"),true,"read-back value head");
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["textarea ladder 2000..30000","textarea newline fidelity","30001 refusal leaves box unchanged",
             "contenteditable ladder with paragraph preservation","contenteditable replacement semantics"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
