"use strict";
// Insertion structure (SCORE e1#3/e2#4): a correct editor-pipeline insertion
// must not be judged wrong, and must not be destroyed, when innerText
// collapses a run of spaces in the read-back. The whole-text fallback runs
// only when the editor pipeline genuinely fails (execCommand returns false),
// never because a length heuristic mis-read collapsed render text. CRLF is
// normalized on the insertion feed so each line becomes one real paragraph
// instead of a doubled break. Isolated fixture Chromium only.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const fixture = `<!doctype html><html><head><title>Fill structure fixture</title></head><body>
  <div id="plain" contenteditable="true" role="textbox" aria-label="plain editable"></div>
</body></html>`;
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:700}});
    await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
    await page.goto("https://fixture.test/page");
    await page.addScriptTag({path:path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js")});
    await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
    const send=async(action,ref=null,text=null,snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params:text===null?{}:{text},
       expires_at:new Date(Date.now()+45000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
    const fill=async(text)=>{
      const s=await snapshot(); const el=s.elements.find(e=>e.name==="plain editable");
      const r=await send("fill",el.ref,text,s.snapshot_id);
      assert.equal(r.ok===true||r.code==="FILL_MISMATCH",true,
        `fill ${JSON.stringify(text)} was refused: ${JSON.stringify(r)}`);
      return r;
    };
    const dom=()=>page.evaluate(()=>({it:document.getElementById("plain").innerText,
      tc:document.getElementById("plain").textContent,
      blocks:document.getElementById("plain").querySelectorAll("div,p").length}));

    // A space run collapses in innerText, but the insertion is correct: the
    // fill must stay on the editor pipeline (paragraph blocks intact), not be
    // destroyed into a raw text node by a length heuristic.
    {
      const r=await fill("para one\npara  two\npara three");
      assert.equal(r.effect,"APPLIED","the insertion is correct");
      assert.equal(r.data.insertion_path,"editor","no fallback rewrite of a correct insertion");
      const d=await dom();
      assert.equal(d.blocks,2,"paragraph structure preserved");
      assert.deepEqual((r.data.normalizations||[]).slice().sort(),["whitespace-run-collapse"],
        "the receipt names the render collapse instead of destroying the blocks");
      assert.equal(d.tc.replace(/\n/g,""),"para onepara  twopara three",
        "the space run is really in the box");
    }
    // Single-line space run: same protection; the bytes are in the DOM.
    {
      const r=await fill("a  b");
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.insertion_path,"editor");
      assert.equal((await dom()).tc,"a  b");
      assert.deepEqual((r.data.normalizations||[]).slice().sort(),["whitespace-run-collapse"]);
    }
    // CRLF: the insertion feed is normalized to LF first, so each line is one
    // real paragraph — not a doubled break, and not the structureless
    // fallback. crlf-to-lf is named in the receipt.
    {
      const r=await fill("a\r\nb");
      assert.equal(r.effect,"APPLIED","CRLF becomes exactly one break per line");
      assert.equal(r.data.insertion_path,"editor");
      assert.deepEqual((r.data.normalizations||[]).slice().sort(),["crlf-to-lf"]);
      const d=await dom();
      assert.equal(d.blocks,1,"one paragraph block");
      assert.equal(d.it,"a\nb");
    }
    // A genuinely failing editor pipeline (execCommand refuses) still gets the
    // byte-exact whole-text fallback, verified through its own carrier.
    {
      await page.evaluate(()=>{
        const orig=document.execCommand.bind(document);
        document.execCommand=(cmd,ui,val)=>{
          const n=document.getElementById("plain");
          return (cmd==="insertText" && n.contains(document.getSelection().anchorNode)) ? false : orig(cmd,ui,val);
        };
      });
      const r=await fill("line one\nline two");
      assert.equal(r.effect,"APPLIED","fallback is byte-exact");
      assert.equal(r.data.insertion_path,"fallback","fallback only on genuine pipeline failure");
      assert.equal(r.data.read_back,"textContent");
      assert.equal((await dom()).tc,"line one\nline two");
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["space-run insertion keeps paragraph blocks (no length-heuristic destroy)",
             "single-line space run held byte-exact in the DOM",
             "CRLF feed normalized to one paragraph per line",
             "genuine execCommand failure still gets the byte-exact fallback"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
