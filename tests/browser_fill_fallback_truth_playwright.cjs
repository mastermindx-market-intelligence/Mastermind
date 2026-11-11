"use strict";
// Fallback truth (SCORE e1#2): the whole-text textContent fallback is never
// reported APPLIED without a matching read-back through its own carrier, and
// when a model-owning editor reverts the write the receipt says so —
// mismatch_kind distinguishes a box left exactly as it was (the write never
// took) from a box holding different content. Isolated fixture Chromium only.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const fixture = `<!doctype html><html><head><title>Fallback truth fixture</title></head><body>
  <div id="broken-revert" contenteditable="true" role="textbox" aria-label="broken reverting editor"></div>
  <div id="broken-grow" contenteditable="true" role="textbox" aria-label="broken growing editor"></div>
  <div id="broken-plain" contenteditable="true" role="textbox" aria-label="broken plain editor"></div>
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
      // execCommand insertText refuses inside these boxes, forcing the
      // whole-text textContent fallback for every fill.
      const orig=document.execCommand.bind(document);
      document.execCommand=(cmd,ui,val)=>{
        const n=cmd==="insertText"?document.getElementById("broken-revert"):null;
        const boxes=["broken-revert","broken-grow","broken-plain"];
        const sel=document.getSelection();
        const inside=boxes.some(id=>document.getElementById(id).contains(sel.anchorNode));
        return (cmd==="insertText" && inside) ? false : orig(cmd,ui,val);
      };
      const revert=document.getElementById("broken-revert"); revert.textContent="KEEPME";
      revert.addEventListener("input",()=>{revert.textContent="KEEPME";});
      const grow=document.getElementById("broken-grow"); grow.textContent="old";
      grow.addEventListener("input",()=>{grow.append("!");});
    });
    const send=async(action,ref=null,text=null,snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params:text===null?{}:{text},
       expires_at:new Date(Date.now()+45000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
    const fill=async(label,text)=>{
      const s=await snapshot(); const el=s.elements.find(e=>e.name===label);
      const r=await send("fill",el.ref,text,s.snapshot_id);
      assert.equal(r.ok===true||r.code==="FILL_MISMATCH",true,
        `fill ${JSON.stringify(text)} on ${label} was refused: ${JSON.stringify(r)}`);
      return r;
    };
    // A model-owning editor that reverts the fallback write keeps exactly its
    // own content: the receipt says the write never took.
    {
      const r=await fill("broken reverting editor","typed text");
      assert.equal(r.code,"FILL_MISMATCH","a reverted write is never APPLIED");
      assert.equal(r.effect,"NOT_APPLIED");
      assert.equal(r.data.insertion_path,"fallback");
      assert.equal(r.data.read_back,"textContent");
      assert.equal(r.data.box_characters,6,"KEEPME");
      assert.equal(r.data.mismatch_kind,"box-unchanged","the write never took");
      assert.equal(await page.evaluate(()=>document.getElementById("broken-revert").textContent),"KEEPME");
    }
    // A different corruption (the editor appended) is content-differs, not
    // box-unchanged: the box no longer holds what it held before the fill.
    {
      const r=await fill("broken growing editor","typed text");
      assert.equal(r.code,"FILL_MISMATCH");
      assert.equal(r.data.mismatch_kind,"content-differs");
      assert.equal(r.data.box_characters>10,true,"old + typed text + appended marks");
    }
    // The unguarded fallback applies and is verified through textContent —
    // APPLIED only because the read-back matched, never by assumption.
    {
      const r=await fill("broken plain editor","line one\nline two");
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.insertion_path,"fallback");
      assert.equal(r.data.read_back,"textContent");
      assert.equal(await page.evaluate(()=>document.getElementById("broken-plain").textContent),"line one\nline two");
      assert.equal(typeof r.data.mismatch_kind,"undefined","no mismatch kind on an applied fill");
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["reverted fallback write named box-unchanged",
             "corrupted fallback write named content-differs",
             "applied fallback verified through textContent read-back"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
