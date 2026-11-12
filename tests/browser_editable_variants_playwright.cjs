"use strict";
// Contenteditable exclusion variants (SCORE p1#2): contenteditable="",
// "TRUE" and "plaintext-only" all make isContentEditable true, but the read
// walker and the snapshot page selector matched only the literal attribute
// value "true" — editor text leaked into the paged read and the snapshot
// pageText while the reply declared the exclusion, and the variant editors
// were invisible to the snapshot as fill targets. Every editable variant is
// excluded from page text and discovered as an editable element. Isolated
// fixture Chromium only.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const fixture = `<!doctype html><html><head><title>Editable variants fixture</title></head><body>
  <article id="wrap" role="article" aria-label="answer wrap">
    <p>visible answer text</p>
    <div id="empty" contenteditable="" role="textbox" aria-label="empty attr editor">EDIT_EMPTY_ATTR</div>
    <div id="upper" contenteditable="TRUE" role="textbox" aria-label="upper editor">EDIT_TRUE_UPPER</div>
    <div id="plainonly" contenteditable="plaintext-only" role="textbox" aria-label="plaintext editor">EDIT_PLAINTEXT_ONLY</div>
    <p>more visible answer text</p>
  </article>
</body></html>`;
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:700}});
    await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
    await page.goto("https://fixture.test/page");
    await page.addScriptTag({path:path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js")});
    await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
    const send=async(action,ref=null,params={},snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params,
       expires_at:new Date(Date.now()+60000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
    const element=async(label,s)=>s.elements.find(e=>e.name===label);
    const markers=["EDIT_EMPTY_ATTR","EDIT_TRUE_UPPER","EDIT_PLAINTEXT_ONLY"];

    // The snapshot's page text excludes every editable variant's editor text.
    {
      const s=await snapshot();
      for(const marker of markers)
        assert.equal(s.text.includes(marker),false,`${marker} leaked into snapshot pageText`);
      assert.equal(s.text.includes("visible answer text"),true,"ordinary text is present");
      // ...and every variant is discovered as an editable fill target with
      // its editor value exposed to the operator.
      for(const label of ["empty attr editor","upper editor","plaintext editor"]) {
        const el=await element(label,s);
        assert.ok(el,`${label} is a snapshot element (fill target)`);
        assert.equal(el.editable,true,`${label} is editable`);
        assert.equal(typeof el.value,"string",`${label} exposes its editor value`);
      }
    }
    // The paged read excludes the same variants from a wrapping element.
    {
      const s=await snapshot();
      const wrap=await element("answer wrap",s);
      assert.ok(wrap,"the wrapper is observable by ref");
      const r=await send("read",wrap.ref,{offset:0},s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r).slice(0,200));
      const whole=[];let offset=0;
      for(;;){
        const page_at=offset===0?r:await send("read",wrap.ref,{offset},s.snapshot_id);
        whole.push(page_at.data.content);
        if(page_at.data.next_offset===null)break;
        offset=page_at.data.next_offset;
      }
      const text=whole.join("");
      for(const marker of markers)
        assert.equal(text.includes(marker),false,`${marker} leaked into the paged read`);
      assert.equal(text.includes("visible answer text"),true);
      assert.equal(text.includes("more visible answer text"),true);
    }
    // The variants are real fill targets: filling one applies through the
    // editor channel and the settle read-back verifies it.
    {
      const s=await snapshot();
      const el=await element("plaintext editor",s);
      const r=await send("fill",el.ref,{text:"typed into a variant editor"},s.snapshot_id);
      assert.equal(r.effect,"APPLIED",JSON.stringify(r).slice(0,200));
      assert.equal(await page.evaluate(()=>document.getElementById("plainonly").innerText),
        "typed into a variant editor");
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["contenteditable=''/'TRUE'/'plaintext-only' excluded from snapshot pageText",
             "every variant discovered as an editable element and fill target",
             "paged read excludes the same variants inside a wrapper",
             "a variant editor fills and verifies through the settle read-back"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
