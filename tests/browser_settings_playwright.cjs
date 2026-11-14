"use strict";
// Actual settings HTML/JS/CSS in an isolated browser; Chrome grants are synthetic.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {chromium}=require(process.env.MMX_BROWSER_TEST_PLAYWRIGHT_MODULE||"playwright");
const root=path.resolve(__dirname,"../integrations/chairman_surfaces/web_sol_extension");
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.MMX_BROWSER_TEST_CHROME?{executablePath:process.env.MMX_BROWSER_TEST_CHROME}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1100,height:1000}});
    await page.addInitScript(()=>{
      const permissions=new Set(["nativeMessaging","alarms","debugger","storage"]),origins=new Set(["https://chatgpt.com/*","https://chat.openai.com/*"]);
      const added=[],removed=[];window.settingsFixtureCalls=[];
      window.chrome={permissions:{
        getAll:async()=>({permissions:[...permissions],origins:[...origins]}),
        request:async query=>{window.settingsFixtureCalls.push({action:"request",query});for(const p of query.permissions||[])permissions.add(p);for(const o of query.origins||[])origins.add(o);for(const f of added)f();return true;},
        remove:async query=>{window.settingsFixtureCalls.push({action:"remove",query});for(const p of query.permissions||[])permissions.delete(p);for(const o of query.origins||[])origins.delete(o);for(const f of removed)f();return true;},
        onAdded:{addListener:f=>added.push(f)},onRemoved:{addListener:f=>removed.push(f)}
      }};
    });
    await page.route("https://settings.fixture.test/**",route=>{
      const file=new URL(route.request().url()).pathname.slice(1);
      if(file==="instance_config.js")return route.fulfill({contentType:"application/javascript",body:'globalThis.MMX_WEB_SOL_INSTANCE={instanceId:"'+"a".repeat(64)+'"};'});
      if(!["browser.html","browser_settings.js","census.css"].includes(file))return route.abort();
      return route.fulfill({contentType:file.endsWith(".js")?"application/javascript":file.endsWith(".css")?"text/css":"text/html",body:fs.readFileSync(path.join(root,file),"utf8")});
    });
    const errors=[];page.on("pageerror",e=>errors.push(e.message));
    await page.goto("https://settings.fixture.test/browser.html");
    await page.locator("#status").filter({hasText:"Page controls paused"}).waitFor();
    await page.getByRole("button",{name:"Enable page controls",exact:true}).click();
    await page.locator("#status").filter({hasText:"Page controls enabled"}).waitFor();
    await page.getByLabel("Website address").fill("https://example.test:8443/path");
    await page.getByRole("button",{name:"Allow website",exact:true}).click();
    await page.locator("#sites").filter({hasText:"https://example.test/*"}).waitFor();
    let calls=await page.evaluate(()=>window.settingsFixtureCalls);
    assert.deepEqual(calls[0].query,{permissions:["tabs","scripting"]});
    assert.deepEqual(calls[1].query,{permissions:["tabs","scripting"],origins:["https://example.test/*"]});
    await page.screenshot({path:"/tmp/hermes-browser-settings-desktop-20261107.png",fullPage:true});
    await page.getByRole("button",{name:"Pause all controls",exact:true}).click();
    await page.locator("#status").filter({hasText:"Page controls paused"}).waitFor();
    calls=await page.evaluate(()=>window.settingsFixtureCalls);
    assert.deepEqual(calls.at(-1).query,{permissions:["tabs","scripting"]});
    await page.getByText("Allow access across websites",{exact:true}).click();
    await page.getByRole("button",{name:"Allow all websites",exact:true}).click();
    calls=await page.evaluate(()=>window.settingsFixtureCalls);
    assert.deepEqual(calls.at(-1).query.origins,["http://*/*","https://*/*"]);
    assert.equal(calls.some(c=>(c.query.permissions||[]).includes("debugger")),false);
    await page.getByRole("button",{name:"Remove added websites",exact:true}).click();
    await page.locator("#sites").filter({hasNotText:"example.test"}).waitFor();
    const before=(await page.evaluate(()=>window.settingsFixtureCalls)).length;
    await page.getByLabel("Website address").fill("javascript:alert(1)");
    await page.getByRole("button",{name:"Allow website",exact:true}).click();
    assert.equal((await page.evaluate(()=>window.settingsFixtureCalls)).length,before);
    assert.match(await page.locator("#status").innerText(),/HTTP or HTTPS/);
    await page.getByLabel("Website address").fill("https://example.com");
    await page.setViewportSize({width:390,height:1000});
    assert.equal(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),true);
    await page.screenshot({path:"/tmp/hermes-browser-settings-mobile-20261107.png",fullPage:true});
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({state:"PASS",proof:"settings UI with synthetic Chrome permission boundary",desktop_width:1100,mobile_width:390,
      cases:["explicit control grant","specific host and port normalization","pause","explicit all-sites grant","required debugger not toggled","remove added sites","invalid scheme refused","no horizontal overflow"]}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
