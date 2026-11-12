"use strict";
// Paged whole-answer read (SCORE: snapshot text is capped at 10,000
// characters, so long answers are unreadable through the bridge). The read
// action returns one snapshot element's full visible text by ref, paged by
// offset: each page fits the 32,768-byte envelope measured in UTF-8 bytes of
// the whole reply, offsets never split a surrogate pair, paging is stable
// (concatenation equals the full read), snapshot exclusions hold (no form
// fields, no contenteditable, nothing hidden or sensitive, no script/style),
// and the read never consumes the observation or touches the page. Isolated
// fixture Chromium only.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const ENVELOPE = 32768;
const fixture = `<!doctype html><html><head><title>Conversation fixture</title></head><body>
  <nav aria-label="sidebar"><a href="/a">Sidebar link</a><a href="/b">Second link</a></nav>
  <main>
    <section aria-label="user prompt"><p>The long prompt asking for a detailed answer with code and lists.</p></section>
    <article id="answer" role="article" aria-label="assistant answer"></article>
  </main>
</body></html>`;
(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100,height:700}});
    await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:fixture}));
    await page.goto("https://fixture.test/page");
    await page.addScriptTag({path:path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js")});
    // Conversation shape: paragraphs, an indented code block, a list, astral
    // characters, and excluded content (script, textarea, contenteditable,
    // hidden) — with a subtree far past MAX_NODES so the snapshot's own
    // walker cannot hold it all.
    const shape = await page.evaluate(()=>{
      const answer=document.getElementById("answer");
      const add=(tag,text,parent=answer)=>{const el=document.createElement(tag);if(text!==null)el.textContent=text;parent.append(el);return el;};
      for(let i=0;i<1050;i++)
        add("p",`Paragraph ${i} of the long visible answer with ordinary words and spacing.`);
      const pre=add("pre",null); const code=document.createElement("code");
      code.textContent="def reply():\n    return {\n        \"indented\": True,\n    }\n";
      pre.append(code);
      const ul=add("ul",null); for(let i=0;i<40;i++) add("li",`list item ${i} of the visible reply`,ul);
      add("p","astral run: "+"𝕏".repeat(80));
      const script=document.createElement("script"); script.textContent="window.EXCL_SCRIPT='seen'"; answer.append(script);
      add("textarea","EXCL_TEXTAREA");
      const ce=add("div",null); ce.setAttribute("contenteditable","true"); ce.textContent="EXCL_CONTENTEDITABLE";
      add("div","EXCL_HIDDEN").setAttribute("hidden","");
      for(let i=0;i<1000;i++) add("span",null);   // node bulk without text
      return {elements:answer.querySelectorAll("*").length, text:answer.innerText.length};
    });
    assert.equal(shape.elements>2000,true,"fixture subtree is past MAX_NODES");
    assert.equal(shape.text>60000,true,"fixture answer text is past 60,000 characters");
    await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
    const send=async(action,ref=null,params=null,snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
      {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params:params===null?{}:params,
       expires_at:new Date(Date.now()+60000).toISOString()});
    const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
    const s=await snapshot();
    const el=s.elements.find(e=>e.name==="assistant answer");
    assert.ok(el,"the answer element is observable by ref");

    // Page through the whole answer: every page fits the envelope, offsets
    // advance by the page length in code units, concatenation equals the
    // full read, and no surrogate pair is ever split.
    const pages=[]; let offset=0, guard=0, total=null;
    for(;;){
      assert.equal(++guard<100,true,"paging terminates");
      const r=await send("read",el.ref,{offset},s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r).slice(0,400));
      assert.equal(r.effect,"NOT_APPLIED","a read applies nothing");
      assert.equal(r.data.offset,offset);
      assert.equal(r.data.content_is_untrusted,true);
      total=r.data.total_characters;
      assert.equal(typeof total,"number");
      const bytes=new TextEncoder().encode(JSON.stringify(r)).length;
      assert.equal(bytes<=ENVELOPE,true,`page at ${offset} is ${bytes} bytes`);
      pages.push(r.data.content);
      if(r.data.next_offset===null) break;
      assert.equal(r.data.next_offset,offset+r.data.content.length,"offsets advance in code units");
      offset=r.data.next_offset;
    }
    const whole=pages.join("");
    assert.equal(whole.length,total,"concatenation equals the full read");
    // Exclusions and inclusions of the visible-answer contract.
    for(const excluded of ["EXCL_SCRIPT","EXCL_TEXTAREA","EXCL_CONTENTEDITABLE","EXCL_HIDDEN"])
      assert.equal(whole.includes(excluded),false,`${excluded} is excluded`);
    assert.equal(whole.includes("Paragraph 1049 of the long visible answer"),true,"late paragraphs are included");
    assert.equal(whole.includes("def reply():"),true,"code block is included");
    assert.equal(whole.includes('        "indented": True,'),true,"code indentation is preserved");
    assert.equal(whole.includes("list item 39 of the visible reply"),true,"list items are included");
    assert.equal(whole.includes("astral run: "+"𝕏".repeat(80)),true,"astral characters survive paging");
    // Stability: the same offset twice from the same observation is identical.
    const again=await send("read",el.ref,{offset:0},s.snapshot_id);
    assert.equal(again.data.content,pages[0],"paging is stable against an unchanged page");
    // The empty tail: reading at exactly total_characters is a valid empty page.
    const tail=await send("read",el.ref,{offset:total},s.snapshot_id);
    assert.equal(tail.ok,true);
    assert.equal(tail.data.content,"");
    assert.equal(tail.data.next_offset,null);
    // Typed errors: negative, beyond end, non-integer, and an offset that
    // would split a surrogate pair are all READ_OFFSET_INVALID.
    for(const bad of [-1,total+1,1.5])
      assert.equal((await send("read",el.ref,{offset:bad},s.snapshot_id)).code,"READ_OFFSET_INVALID",
        `offset ${bad} is refused`);
    const pairAt=whole.indexOf("𝕏");
    assert.equal(pairAt>0,true,"astral marker present");
    assert.equal((await send("read",el.ref,{offset:pairAt+1},s.snapshot_id)).code,"READ_OFFSET_INVALID",
      "an offset inside a surrogate pair is refused");
    // Wrong shape is the standard INPUT_REFUSED.
    assert.equal((await send("read",el.ref,{},s.snapshot_id)).code,"INPUT_REFUSED");
    assert.equal((await send("read",el.ref,{offset:"0"},s.snapshot_id)).code,"INPUT_REFUSED");
    // The read consumed nothing and touched nothing: the observation still
    // authorizes reads and mutations, the page did not scroll, focus did not
    // move, and the DOM is unchanged.
    const stillValid=await send("validate",null,{},s.snapshot_id);
    assert.equal(stillValid.ok,true,"the observation is not consumed by reads");
    // text_truncated must reflect the character cap before the cosmetic
    // strips: a joined text past 1,000,000 characters whose capped tail is
    // newline padding strips back below the bound, and the old flag (checked
    // after the strips) said false while the cap had dropped characters.
    {
      await page.evaluate(()=>{
        const pre=document.createElement("pre");
        pre.id="capedge";
        pre.setAttribute("role","code");
        pre.setAttribute("aria-label","cap edge code");
        pre.textContent="a".repeat(999999)+"\n\n\n\n\n\n";
        // body.firstChild: the snapshot walker is node-bounded and this
        // fixture's subtree is already past MAX_NODES, so a body-append
        // would never be scanned.
        document.body.insertBefore(pre,document.body.firstChild);
      });
      const s2=await snapshot();
      const edge=s2.elements.find(e=>e.name==="cap edge code");
      assert.ok(edge,"the cap-edge pre is observable");
      const r=await send("read",edge.ref,{offset:0},s2.snapshot_id);
      assert.equal(r.ok,true);
      assert.equal(r.data.total_characters,999999,"the strip removed the capped trailing newline");
      assert.equal(r.data.text_truncated,true,"the cap dropped characters: truncated is true");
      await page.evaluate(()=>document.getElementById("capedge").remove());
      const control=await snapshot();
      const article=control.elements.find(e=>e.name==="assistant answer");
      const ok2=await send("read",article.ref,{offset:0},control.snapshot_id);
      assert.equal(ok2.data.text_truncated,false,"an ordinary element is not flagged");
    }
    const after=await page.evaluate(()=>({scrollY:window.scrollY,active:document.activeElement===document.body,
      mutated:document.getElementById("answer").querySelectorAll("*").length}));
    assert.equal(after.scrollY,0,"no scroll");
    assert.equal(after.active,true,"no focus change");
    assert.equal(after.mutated,shape.elements,"no DOM change");
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixture",
      cases:["paged read of a 60,000+ character answer past MAX_NODES",
             "every page fits the 32,768-byte envelope in UTF-8",
             "concatenation equals the full read; surrogates never split",
             "script/textarea/contenteditable/hidden excluded; code indentation preserved",
             "stability, empty tail, typed READ_OFFSET_INVALID and INPUT_REFUSED",
             "reads consume no observation and touch no page state"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
