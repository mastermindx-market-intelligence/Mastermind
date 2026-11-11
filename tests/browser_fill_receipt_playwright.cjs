"use strict";
// Honest fill receipts (e1#1 HIGH + e1#4): the fill outcome must compare what
// the box holds after the fill with what was asked. A mismatch is a typed
// FILL_MISMATCH with both lengths and the first differing offset, never
// APPLIED. Normalizations the editor provably performs are listed in the
// receipt; nothing else is normalized. Isolated fixture Chromium only — this
// harness never touches an installed profile. Includes the positive-control
// probe that a fill cannot press Enter (no key/beforeinput events fire).
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const fixture = `<!doctype html><html><head><title>Fill receipt fixture</title></head><body>
  <div id="plain" contenteditable="true" role="textbox" aria-label="plain editable"></div>
  <div id="append" contenteditable="true" role="textbox" aria-label="appending editor"></div>
  <div id="grow" contenteditable="true" role="textbox" aria-label="growing editor"></div>
  <div id="revert" contenteditable="true" role="textbox" aria-label="reverting editor"></div>
  <div id="truncate" contenteditable="true" role="textbox" aria-label="truncating editor"></div>
  <div id="merge" contenteditable="true" role="textbox" aria-label="merging editor"></div>
  <textarea id="area" aria-label="plain textarea"></textarea>
</body></html>`;
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:700}});
    await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
    await page.goto("https://fixture.test/page");
    await page.addScriptTag({path:path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js")});
    await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
    await page.evaluate(()=>{
      const byId=id=>document.getElementById(id);
      // appending editor: the first insertText lands at the end instead of
      // replacing the selection, so the box keeps old text and appends.
      const appendBox=byId("append"); appendBox.textContent="old";
      const orig=document.execCommand.bind(document);
      document.execCommand=(cmd,ui,val)=>{
        const sel=document.getSelection();
        if(cmd==="insertText" && sel && appendBox.contains(sel.anchorNode) && !appendBox.dataset.done){
          appendBox.dataset.done="1";
          sel.collapse(appendBox,appendBox.childNodes.length);
        }
        return orig(cmd,ui,val);
      };
      // growing editor: every input event appends a character (mention stand-in).
      byId("grow").addEventListener("input",e=>{if(!e._fill)e.target.append("!");});
      // reverting editor: a model-owning editor that restores its own content.
      const revertBox=byId("revert"); revertBox.textContent="KEEPME";
      revertBox.addEventListener("input",()=>{revertBox.textContent="KEEPME";});
      // truncating editor: keeps only the first five characters.
      byId("truncate").addEventListener("input",e=>{
        const n=e.target; if(n.textContent.length>5)n.textContent=n.textContent.slice(0,5);});
      // merging editor: collapses empty paragraph blocks on every input.
      byId("merge").addEventListener("input",e=>{
        e.target.querySelectorAll("p,div").forEach(b=>{
          if(!b.textContent.trim() && b.parentElement) b.remove();});});
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
    const box=id=>page.evaluate(i=>document.getElementById(i).innerText,id);

    // An empty fill that leaves stale text is a mismatch, never APPLIED.
    await page.evaluate(()=>document.getElementById("plain").textContent="hello");
    {
      const r=await fill("plain editable","");
      assert.equal(r.code,"FILL_MISMATCH","stale text after empty fill");
      assert.equal(r.effect,"NOT_APPLIED");
      assert.equal(r.data.asked_characters,0);
      assert.equal(r.data.box_characters,5);
      assert.equal(r.data.first_diff_offset,0);
      assert.equal(await box("plain"),"hello","box untouched by the refusal to claim success");
    }
    // An append where a replace was asked is a mismatch from offset 0.
    {
      const r=await fill("appending editor","NEW");
      assert.equal(r.code,"FILL_MISMATCH","append is not a replace");
      assert.equal(r.effect,"NOT_APPLIED");
      assert.equal(r.data.asked_characters,3);
      assert.equal(r.data.box_characters,6); // "oldNEW"
      assert.equal(r.data.first_diff_offset,0);
    }
    // Text the editor rewrote (grew) — the length check must apply on both sides.
    {
      const r=await fill("growing editor","hello world");
      assert.equal(r.code,"FILL_MISMATCH","editor-appended characters are a mismatch");
      assert.equal(r.data.first_diff_offset,11);
      assert.equal(r.data.box_characters>11,true);
    }
    // Text the editor truncated — shorter box is equally a mismatch.
    {
      const r=await fill("truncating editor","a longer text");
      assert.equal(r.code,"FILL_MISMATCH","truncated box is a mismatch");
      assert.equal(r.data.box_characters,5);
      assert.equal(r.data.first_diff_offset,5);
    }
    // An editor that reverts the write keeps its own content: mismatch.
    {
      const r=await fill("reverting editor","typed text");
      assert.equal(r.code,"FILL_MISMATCH","reverted write is a mismatch");
      assert.equal(await box("revert"),"KEEPME");
    }
    // Empty-line drift: a merged blank line is lost content, not normalization.
    {
      const r=await fill("merging editor","a\n\nb");
      assert.equal(r.code,"FILL_MISMATCH","a dropped blank line is a mismatch");
      assert.equal(r.effect,"NOT_APPLIED");
      assert.equal((r.data.normalizations||[]).includes("blank-line-render"),false,
        "a real dropped line must not hide behind the render artifact normalization");
    }
    // CRLF: the editor pipeline breaks on it (execCommand treats CR as a
    // paragraph), so this fill runs the byte-exact whole-text fallback and
    // the receipt verifies it through textContent — the actual carrier — not
    // through innerText, which only renders the break as a space.
    {
      const r=await fill("plain editable","a\r\nb");
      assert.equal(r.effect,"APPLIED","byte-exact fallback holds the CRLF");
      assert.equal(r.data.insertion_path,"fallback");
      assert.equal(r.data.read_back,"textContent");
      assert.deepEqual(r.data.normalizations,[]);
      assert.equal(await page.evaluate(()=>document.getElementById("plain").textContent),"a\r\nb");
    }
    // Tab: the editor pipeline inserts it literally — the DOM text holds the
    // real tab — and innerText renders the tab as a space, so the receipt
    // names whitespace-run-collapse instead of pretending exactness.
    {
      const r=await fill("plain editable","x\ty");
      assert.equal(r.effect,"APPLIED","the tab is in the box; the render collapses it");
      assert.equal(r.data.insertion_path,"editor");
      assert.equal(r.data.read_back,"innerText");
      assert.deepEqual(r.data.normalizations,["whitespace-run-collapse"]);
      assert.equal(await page.evaluate(()=>document.getElementById("plain").textContent),"x\ty");
    }
    // Render drift the editor channel provably performs is named in the
    // receipt, not counted as a mismatch: an empty paragraph renders a doubled
    // break, and a trailing paragraph break drifts.
    {
      const r=await fill("plain editable","a\n\nb");
      assert.equal(r.effect,"APPLIED","blank line preserved as a block");
      assert.equal(r.data.insertion_path,"editor");
      assert.deepEqual(r.data.normalizations,["blank-line-render"]);
      assert.equal((await box("plain")).replace(/\n/g,"").length,2,"both lines present in the render");
    }
    {
      const r=await fill("plain editable","abc\n");
      assert.equal(r.effect,"APPLIED","trailing break renders with drift");
      assert.deepEqual(r.data.normalizations,["trailing-newline-drift"]);
    }
    // A faithful fill applies and the receipt says what, if anything, was normalized.
    {
      const r=await fill("plain editable","one\n two\n three");
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.insertion_path,"editor");
      assert.deepEqual((r.data.normalizations||[]).slice().sort(),["line-edge-spaces","nbsp-render"],
        "leading spaces render as U+00A0 in the editor's own pipeline");
      assert.equal(typeof r.data.asked_characters,"number");
      assert.equal(typeof r.data.box_characters,"number");
    }
    // The textarea channel: CRLF is the value API's own normalization; tabs and
    // trailing spaces are preserved exactly, so nothing else may be normalized.
    {
      const r=await fill("plain textarea","a\r\nb\tc ");
      assert.equal(r.effect,"APPLIED");
      assert.deepEqual(r.data.normalizations,["crlf-to-lf"]);
      const value=await page.evaluate(()=>document.getElementById("area").value);
      assert.equal(value,"a\nb\tc ");
    }
    // Positive control: a fill fires no key or beforeinput events, so no
    // composer that sends on Enter can be made to send by filling.
    {
      const events=await page.evaluate(()=>{
        window.__fillEvents=[];
        const n=document.getElementById("plain");
        for(const kind of ["keydown","keyup","beforeinput"]) n.addEventListener(kind,e=>window.__fillEvents.push(kind));
        return true;
      });
      const r=await fill("plain editable","line one\nline two\nline three");
      assert.equal(r.effect,"APPLIED");
      const seen=await page.evaluate(()=>window.__fillEvents);
      assert.deepEqual(seen,[],"fill must not synthesize key or beforeinput events");
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["stale empty fill","append-not-replace","editor rewrote (grew)","editor truncated",
             "editor reverted","blank-line dropped is a mismatch",
             "CRLF/tab byte-exact fallback verified through textContent",
             "blank-line render + trailing-break drift named as normalizations",
             "faithful apply carries receipt fields (nbsp render named)",
             "textarea CRLF normalized + tab/trailing-space preserved",
             "no key/beforeinput events (Enter cannot send)"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
