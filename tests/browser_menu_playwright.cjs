"use strict";
// Stepped menu control by ref (BR2 item 1): one menu action opens a menu or
// popover by its opener ref, walks up to three labelled steps, chooses the
// final item, and returns a receipt stating the value read back afterwards.
// Read-back ladder: chosen item's checked/selected state while visible, the
// opener's displayed text when the menu closed on choice, or a reopen that
// reads the chosen item's state. When no channel can read the value back the
// result is EFFECT_UNKNOWN, never success, and the consumed snapshot forbids
// a repeat. General mechanism — ARIA menu button with menuitemradio items
// (the model-menu shape, BR2 item 2), popover listbox, two-step submenu,
// menu that closes on choice, value visible only on reopen. Isolated fixture
// Chromium only.
const assert = require("node:assert/strict");
const path = require("node:path");
const {chromium} = require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE || "playwright");
const SESSION = "b".repeat(64);
const PAGE_JS = path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension/browser_page.js");

// A model-menu shape: button opener, role=menuitemradio items, one checked.
// `mode` decides what the control does on choice:
//  close-label  — menu closes, opener text becomes the chosen label
//  open-checked — menu stays open, chosen item aria-checked=true
//  reopen-only  — menu closes, opener text never changes, state on reopen
//  unreadable   — menu closes, no state anywhere (EFFECT_UNKNOWN)
const menuFixture = mode => `<!doctype html><html><head><title>Menu fixture</title></head><body>
  <button id="opener" aria-haspopup="menu" aria-expanded="false">Model</button>
  <div id="menu" role="menu" hidden>
    <div role="menuitemradio" aria-checked="false" tabindex="-1">GPT-5</div>
    <div role="menuitemradio" aria-checked="true" tabindex="-1">GPT-5 Thinking</div>
    <div role="menuitemradio" aria-checked="false" tabindex="-1">GPT-5 Pro</div>
  </div>
  <script>
    const btn=document.getElementById('opener'), menu=document.getElementById('menu');
    const MODE=${JSON.stringify(mode)};
    btn.addEventListener('click',()=>{const open=menu.hidden;menu.hidden=!open;btn.setAttribute('aria-expanded',String(open));});
    menu.addEventListener('click',e=>{
      const item=e.target.closest('[role=menuitemradio]'); if(!item)return;
      if(MODE!=='unreadable')menu.querySelectorAll('[role=menuitemradio]').forEach(i=>i.setAttribute('aria-checked',String(i===item)));
      if(MODE==='open-checked')return;
      menu.hidden=true;btn.setAttribute('aria-expanded','false');
      if(MODE==='close-label')btn.textContent=item.textContent;
    });
  </script>
</body></html>`;

// Two-step submenu: "Thinking" opens a menu whose "Effort" item opens a
// second menu; choosing "Extra High" closes both and labels the opener.
const submenuFixture = `<!doctype html><html><head><title>Submenu fixture</title></head><body>
  <button id="opener" aria-haspopup="menu" aria-expanded="false">Thinking</button>
  <div id="m1" role="menu" hidden>
    <div role="menuitem" id="effort" aria-haspopup="menu">Effort</div>
    <div role="menuitem">Standard</div>
  </div>
  <div id="m2" role="menu" hidden>
    <div role="menuitemradio" aria-checked="false">High</div>
    <div role="menuitemradio" aria-checked="false">Extra High</div>
  </div>
  <script>
    const btn=document.getElementById('opener'),m1=document.getElementById('m1'),m2=document.getElementById('m2');
    btn.addEventListener('click',()=>{const open=m1.hidden;m1.hidden=!open;m2.hidden=true;btn.setAttribute('aria-expanded',String(open));});
    document.getElementById('effort').addEventListener('click',()=>{m1.hidden=true;m2.hidden=false;});
    m2.addEventListener('click',e=>{
      const item=e.target.closest('[role=menuitemradio]'); if(!item)return;
      m2.querySelectorAll('[role=menuitemradio]').forEach(i=>i.setAttribute('aria-checked',String(i===item)));
      m2.hidden=true;btn.setAttribute('aria-expanded','false');
      btn.textContent='Thinking: '+item.textContent;
    });
  </script>
</body></html>`;

// Popover listbox: combobox opener, role=option items with aria-selected.
const listboxFixture = `<!doctype html><html><head><title>Listbox fixture</title></head><body>
  <button id="opener" role="combobox" aria-expanded="false" aria-controls="lb">Sort</button>
  <div id="lb" role="listbox" hidden>
    <div role="option" aria-selected="false">Newest</div>
    <div role="option" aria-selected="true">Oldest</div>
  </div>
  <script>
    const btn=document.getElementById('opener'),lb=document.getElementById('lb');
    btn.addEventListener('click',()=>{const open=lb.hidden;lb.hidden=!open;btn.setAttribute('aria-expanded',String(open));});
    lb.addEventListener('click',e=>{
      const item=e.target.closest('[role=option]'); if(!item)return;
      lb.querySelectorAll('[role=option]').forEach(i=>i.setAttribute('aria-selected',String(i===item)));
      lb.hidden=true;btn.setAttribute('aria-expanded','false');btn.textContent=item.textContent;
    });
  </script>
</body></html>`;

async function mount(browser, html) {
  const page = await browser.newPage({viewport:{width:1100,height:700}});
  await page.route("https://fixture.test/**",route=>route.fulfill({contentType:"text/html",body:html}));
  await page.goto("https://fixture.test/page");
  await page.addScriptTag({path:PAGE_JS});
  await page.evaluate(()=>{window.browserFixturePage=window.MMXBrowserPageFactory(window);});
  const send=async(action,ref=null,params=null,snapshot=null)=>page.evaluate(r=>window.browserFixturePage.dispatch(r),
    {kind:"MMX_BROWSER_PAGE_V1",action,session_id:SESSION,snapshot_id:snapshot,ref,params:params===null?{}:params,
     expires_at:new Date(Date.now()+60000).toISOString()});
  const snapshot=async()=>{const r=await send("snapshot");assert.equal(r.ok,true,JSON.stringify(r));return r.data;};
  const openerRef=async s=>{const el=s.elements.find(e=>e.name==="Model"||e.name==="Thinking"||e.name==="Sort");
    assert.ok(el,"opener is observable");return el.ref;};
  return {page,send,snapshot,openerRef};
}

(async()=>{
  const browser = await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME ? {executablePath:process.env.MMX_BROWSER_TEST_CHROME} : {})});
  try {
    // 1. Menu that closes on choice; the opener's text shows the value.
    {
      const {page,send,snapshot,openerRef}=await mount(browser,menuFixture("close-label"));
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["GPT-5 Pro"]},s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(r.effect,"APPLIED");
      assert.deepEqual(r.data.menu_path,["GPT-5 Pro"]);
      assert.equal(r.data.read_back.value,"GPT-5 Pro");
      assert.equal(r.data.read_back.source,"opener-text");
      assert.equal(r.data.menu_left_open,false);
      assert.equal(r.data.snapshot_consumed,true);
      assert.equal(r.data.refresh_required,true);
      assert.equal(r.data.content_is_untrusted,true);
      const text=await page.evaluate(()=>document.getElementById("opener").textContent);
      assert.equal(text,"GPT-5 Pro");
      // One snapshot authorizes one menu operation: the observation is gone.
      const again=await send("menu",ref,{path:["GPT-5"]},s.snapshot_id);
      assert.equal(again.ok,false);assert.equal(again.code,"STALE_SNAPSHOT");
      await page.close();
    }
    // 2. Menu that stays open: the chosen item's aria-checked is the read-back.
    {
      const {page,send,snapshot,openerRef}=await mount(browser,menuFixture("open-checked"));
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["GPT-5"]},s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.read_back.source,"item-state");
      assert.equal(r.data.read_back.value,"GPT-5");
      assert.equal(r.data.menu_left_open,true);
      const checked=await page.evaluate(()=>document.querySelector('[role=menuitemradio][aria-checked="true"]').textContent);
      assert.equal(checked,"GPT-5");
      await page.close();
    }
    // 3. Value visible only on reopen: opener text never changes; the
    //    mechanism reopens, reads the chosen item's state, closes again.
    {
      const {page,send,snapshot,openerRef}=await mount(browser,menuFixture("reopen-only"));
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["GPT-5 Pro"]},s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.read_back.source,"reopen-item-state");
      assert.equal(r.data.read_back.value,"GPT-5 Pro");
      assert.equal(r.data.menu_left_open,false);
      const state=await page.evaluate(()=>({label:document.getElementById("opener").textContent,
        hidden:document.getElementById("menu").hidden}));
      assert.equal(state.label,"Model","opener text never changed");
      assert.equal(state.hidden,true,"menu closed again after the read-back");
      await page.close();
    }
    // 4. No channel can read the value back: EFFECT_UNKNOWN, never success,
    //    and the act is not repeated (the snapshot is consumed).
    {
      const {page,send,snapshot,openerRef}=await mount(browser,menuFixture("unreadable"));
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["GPT-5 Pro"]},s.snapshot_id);
      assert.equal(r.ok,false,JSON.stringify(r));
      assert.equal(r.effect,"EFFECT_UNKNOWN");
      assert.equal(r.code,"ACTION_EFFECT_UNKNOWN");
      assert.equal(r.data.read_back,null);
      assert.equal(r.data.snapshot_consumed,true);
      const again=await send("menu",ref,{path:["GPT-5 Pro"]},s.snapshot_id);
      assert.equal(again.code,"STALE_SNAPSHOT","an uncertain menu act is never repeated on the dead snapshot");
      await page.close();
    }
    // 5. Two-step submenu: Thinking -> Effort -> Extra High.
    {
      const {page,send,snapshot,openerRef}=await mount(browser,submenuFixture);
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["Effort","Extra High"]},s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(r.effect,"APPLIED");
      assert.deepEqual(r.data.menu_path,["Effort","Extra High"]);
      assert.equal(r.data.steps_taken,2);
      assert.equal(r.data.read_back.value,"Thinking: Extra High");
      assert.equal(r.data.read_back.source,"opener-text");
      const label=await page.evaluate(()=>document.getElementById("opener").textContent);
      assert.equal(label,"Thinking: Extra High");
      await page.close();
    }
    // 6. Popover listbox with aria-selected options.
    {
      const {page,send,snapshot,openerRef}=await mount(browser,listboxFixture);
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["Newest"]},s.snapshot_id);
      assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(r.effect,"APPLIED");
      assert.equal(r.data.read_back.value,"Newest");
      const selected=await page.evaluate(()=>document.querySelector('[role=option][aria-selected="true"]').textContent);
      assert.equal(selected,"Newest");
      await page.close();
    }
    // 7. Typed refusals: absent item, ambiguous label, opener that opens
    //    nothing, disabled opener, bad params. Refusals before the first
    //    click leave the observation intact; after it, it is consumed.
    {
      const {page,send,snapshot,openerRef}=await mount(browser,menuFixture("close-label"));
      const s=await snapshot(); const ref=await openerRef(s);
      const absent=await send("menu",ref,{path:["Absent"]},s.snapshot_id);
      assert.equal(absent.ok,false);assert.equal(absent.code,"MENU_ITEM_NOT_FOUND");
      assert.equal(absent.effect,"NOT_APPLIED");
      assert.equal(absent.data.snapshot_consumed,true);
      // The refusal restored the menu (best-effort opener re-click).
      assert.equal(absent.data.menu_left_open,false);
      // A fresh observation still works after a refusal.
      const s2=await snapshot();
      const ok=await send("menu",ref,{path:["GPT-5"]},s2.snapshot_id);
      assert.equal(ok.ok,true,JSON.stringify(ok));
      await page.close();
    }
    {
      const html=menuFixture("close-label").replace('<div role="menuitemradio" aria-checked="false" tabindex="-1">GPT-5 Pro</div>',
        '<div role="menuitemradio" aria-checked="false" tabindex="-1">Twin</div><div role="menuitemradio" aria-checked="false" tabindex="-1">Twin</div>');
      const {page,send,snapshot,openerRef}=await mount(browser,html);
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["Twin"]},s.snapshot_id);
      assert.equal(r.ok,false);assert.equal(r.code,"MENU_AMBIGUOUS");assert.equal(r.effect,"NOT_APPLIED");
      await page.close();
    }
    {
      const html=`<!doctype html><html><body><button id="opener">Model</button></body></html>`;
      const {page,send,snapshot,openerRef}=await mount(browser,html);
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["Anything"]},s.snapshot_id);
      assert.equal(r.ok,false);assert.equal(r.code,"MENU_NOT_OPENED");assert.equal(r.effect,"NOT_APPLIED");
      await page.close();
    }
    {
      const {page,send,snapshot,openerRef}=await mount(browser,menuFixture("close-label"));
      await page.evaluate(()=>document.getElementById("opener").setAttribute("aria-disabled","true"));
      const s=await snapshot(); const ref=await openerRef(s);
      const r=await send("menu",ref,{path:["GPT-5"]},s.snapshot_id);
      assert.equal(r.ok,false);assert.equal(r.code,"TARGET_DISABLED");assert.equal(r.effect,"NOT_APPLIED");
      // Bad params never consume the observation.
      await page.evaluate(()=>document.getElementById("opener").removeAttribute("aria-disabled"));
      const s2=await snapshot();
      for(const bad of [{path:[]},{path:["a","b","c","d"]},{path:[1]},{path:[""]},{path:["x".repeat(161)]},
                        {path:["ok"],extra:1},{notpath:["GPT-5"]},{path:"GPT-5"}]) {
        const r2=await send("menu",ref,bad,s2.snapshot_id);
        assert.equal(r2.ok,false,JSON.stringify(bad));assert.equal(r2.code,"INPUT_REFUSED",JSON.stringify(bad));
      }
      const still=await send("validate",null,{},s2.snapshot_id);
      assert.equal(still.ok,true,"bad params left the observation intact");
      await page.close();
    }
    // 8. Offscreen opener: the same viewport gate as click, nothing applied.
    {
      const html=menuFixture("close-label").replace('<button id="opener"',
        '<div style="height:1400px"></div><button id="opener"');
      const {page,send,snapshot}=await mount(browser,html);
      const s=await snapshot();
      const el=s.elements.find(e=>e.name==="Model");
      assert.ok(el,"offscreen opener is still observable");
      const r=await send("menu",el.ref,{path:["GPT-5"]},s.snapshot_id);
      assert.equal(r.ok,false);assert.equal(r.code,"TARGET_OFFSCREEN");assert.equal(r.effect,"NOT_APPLIED");
      const scroll=await page.evaluate(()=>window.scrollY);
      assert.equal(scroll,0,"no scroll happened");
      await page.close();
    }
    console.log(JSON.stringify({state:"PASS",proof:"isolated Chromium DOM fixtures",
      cases:["menuitemradio model menu, close-on-choice with opener-text read-back",
             "open menu with item-state read-back","reopen-only value read-back",
             "unreadable value is EFFECT_UNKNOWN and never repeated",
             "two-step submenu (Effort -> Extra High)","popover listbox aria-selected",
             "typed MENU_ITEM_NOT_FOUND / MENU_AMBIGUOUS / MENU_NOT_OPENED / TARGET_DISABLED / INPUT_REFUSED",
             "one snapshot authorizes one menu operation","offscreen opener refused without scrolling"]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});