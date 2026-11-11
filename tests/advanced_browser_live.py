"""Real Chromium/extension qualification in a fresh, disposable browser profile.

The fixture grants only loopback origins. It never visits user pages, changes
production profiles, or claims the fixture is an installed Hermes journey.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


class Fixture(BaseHTTPRequestHandler):
    port = 0
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path.startswith("/redirect-denied"):
            self.send_response(302)
            self.send_header("Location","http://denied.mastermind.test:"+str(self.port)+"/data")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            return
        if self.path.startswith("/events"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for number in range(3):
                    self.wfile.write(("event: proof\ndata: fixture-" + str(number) + "\n\n").encode())
                    self.wfile.flush()
                    time.sleep(.12)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if self.path.startswith("/data"):
            body = json.dumps({"proof": True, "message": "real-network-response", "padding": "z" * 35000}).encode()
            mime = "application/json"
        elif self.path.startswith("/download"):
            body = b"Mastermind deterministic download fixture\n"
            mime = "application/octet-stream"
        elif self.path.startswith("/frame"):
            nested = "" if "nested" in self.path else '<iframe title="Nested" src="http://127.0.0.1:' + str(self.port) + '/frame?nested"></iframe>'
            body = ('<!doctype html><title>Frame fixture</title><style>body{margin:20px}button{padding:14px}</style>'
                    '<button aria-label="Frame action" onclick="this.dataset.clicked=String(Number(this.dataset.clicked||0)+1)">Frame action</button>'
                    '<input aria-label="Frame input"><div id="result">Frame ready</div>' + nested).encode()
            mime = "text/html"
        else:
            body = ('''<!doctype html><html><head><title>Mastermind CDP fixture</title>
            <style>body{font:16px sans-serif;margin:24px;background:#fafafa}button,input,select{margin:5px;padding:12px}iframe{display:block;width:650px;height:280px;margin:12px;border:3px solid #abc}.spacer{height:1300px}</style></head>
            <body><h1>Mastermind browser fixture</h1>
            <button aria-label="Increment" id="counter" onclick="this.dataset.count=String(Number(this.dataset.count||0)+1)">Increment</button>
            <label>Name <input aria-label="Name" id="name"></label>
            <label>Secret <input type="password" value="do-not-export"></label>
            <input type="file" aria-label="Upload fixture" id="upload">
            <input type="file" id="hidden-upload" style="display:none">
            <select aria-label="Choice"><option value="a">Alpha</option><option value="b">Beta</option></select>
            <label><input type="checkbox" aria-label="Accept">Accept</label>
            <button id="fetch" onclick="fetch('/data').then(r=>r.json()).then(x=>document.querySelector('#status').textContent=x.message)">Fetch data</button>
            <div id="status">Ready</div><div id="shadow"></div>
            <iframe title="Same origin" src="/frame?nested"></iframe>
            <iframe title="Cross origin" src="http://localhost:''' + str(self.port) + '''/frame"></iframe>
            <div class="spacer"></div><button aria-label="Bottom action">Bottom action</button>
            <script>
            document.querySelector('#shadow').attachShadow({mode:'open'}).innerHTML='<button aria-label="Shadow action" onclick="this.dataset.clicked=1">Shadow action</button>';
            window.startProof=()=>{console.log('fixture-console');fetch('/data');const e=new EventSource('/events');setTimeout(()=>e.close(),650);};
            </script></body></html>''').encode()
            mime = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


async def main():
    server = ThreadingHTTPServer(("0.0.0.0", 0), Fixture)
    Fixture.port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    with tempfile.TemporaryDirectory(prefix="mastermind-cdp-live-") as directory:
        stage = Path(directory)
        ext = stage / "extension"
        shutil.copytree(ROOT / "integrations/chairman_surfaces/web_sol_extension", ext)
        manifest = json.loads((ext / "manifest.json").read_text())
        manifest["permissions"] = ["nativeMessaging", "alarms", "debugger", "tabs", "scripting", "downloads"]
        manifest["host_permissions"] = ["http://127.0.0.1/*", "http://localhost/*"]
        manifest["optional_permissions"] = []
        manifest["optional_host_permissions"] = []
        (ext / "manifest.json").write_text(json.dumps(manifest))
        from integrations.chairman_surfaces.web_sol_protocol import transport_capability_digest
        instance = "a" * 64
        config = dict(schema="mastermind.web_sol_instance_config.v1",instanceId=instance,
            nativeHost="com.mastermind.web_sol_surface." + instance[:24],protocolMajor=1,
            clientPackageVersion="0.4.0",nativePackageVersion="0.4.0",extensionPackageVersion="0.4.0",
            capabilityDigest=transport_capability_digest())
        (ext / "instance_config.js").write_text("globalThis.MMX_WEB_SOL_INSTANCE=Object.freeze(" + json.dumps(config) + ");")
        upload = stage / "upload.txt"
        upload.write_text("browser upload proof")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch_persistent_context(str(stage / "profile"),
                executable_path=os.environ.get("MMX_BROWSER_TEST_EXECUTABLE","/usr/bin/chromium"),headless=True,accept_downloads=True,
                ignore_default_args=["--disable-extensions"],
                args=["--no-sandbox","--site-per-process","--host-resolver-rules=MAP denied.mastermind.test 127.0.0.1","--disable-extensions-except="+str(ext),"--load-extension="+str(ext)])
            try:
                worker = browser.service_workers[0] if browser.service_workers else await browser.wait_for_event("serviceworker")
                await worker.evaluate("""() => {
                    globalThis.testBoot='fixture-connection-00000000000000';
                    globalThis.testController=MMXBrowserControl.createController(chrome,'a'.repeat(64),()=>globalThis.testBoot);
                    return chrome.runtime.getManifest().version;
                }""")
                page = await browser.new_page()
                url = "http://127.0.0.1:" + str(server.server_port) + "/"
                await page.goto(url)
                await page.wait_for_selector("iframe")
                await asyncio.sleep(.2)
                tabs = await worker.evaluate("chrome.tabs.query({})")
                tab = next(t for t in tabs if t.get("url") == url)
                session = "b" * 64
                snapshot = None
                url_hash = hashlib.sha256(url.encode()).hexdigest()
                from integrations.chairman_surfaces import web_sol_browser_protocol as protocol

                async def call(action, options=None, *, owner=session, use_snapshot=None, **legacy):
                    nonlocal snapshot, url_hash
                    now = datetime.now(timezone.utc)
                    needs = action in protocol.TAB_ACTIONS - protocol.NO_SNAPSHOT
                    request = dict(schema=protocol.REQUEST_SCHEMA,adapter_instance_id=instance,
                        session_id=owner,operation_key="fixture-"+secrets.token_hex(6),nonce=secrets.token_hex(24),
                        transport_boot_nonce="fixture-connection-00000000000000",action=action,
                        tab_id=tab["id"] if action in protocol.TAB_ACTIONS else None,
                        url_fingerprint=url_hash if action in protocol.TAB_ACTIONS else None,
                        snapshot_id=(snapshot if use_snapshot is None else use_snapshot) if needs else None,
                        ref=legacy.pop("ref",None),params=options if action in protocol.ADVANCED_ACTIONS else legacy,
                        issued_at=now.isoformat().replace("+00:00","Z"),expires_at=(now+timedelta(seconds=45)).isoformat().replace("+00:00","Z"))
                    protocol.validate_request(request)
                    out = await worker.evaluate("(r)=>testController.run(r,testBoot)", request)
                    assert out is not None, ("request_not_accepted", action)
                    protocol.validate_receipt(out)
                    if action=="snapshot" and out["status"]=="OK":
                        snapshot=out["data"]["snapshot_id"]
                    return out

                async def ok(action, options=None, **kw):
                    out = await call(action, options, **kw)
                    assert out["status"] in {"OK","ACTION_DISPATCHED"}, (action,out)
                    return out["data"]

                async def mutate(action, options):
                    await ok("snapshot")
                    return await ok(action,options)

                await ok("snapshot")
                attached = await ok("cdp_attach",{"network":True})
                assert attached["related_frames"],attached
                results.append("persistent_attach")
                await asyncio.sleep(.3)
                frames = await ok("frames",{})
                assert len(frames["frames"])>=4,frames
                results.append("main_same_origin_cross_origin_nested_frames")
                collision = await call("cdp_status",{},owner="c"*64)
                assert collision["status"]=="CDP_OWNED_BY_ANOTHER_SESSION",collision
                results.append("session_ownership")
                root_ref=(await ok("locate",{"locator":{"role":"button","name":"Increment"}}))["elements"][0]["ref"]
                await mutate("interact",{"ref":root_ref,"kind":"click"})
                assert await page.locator("#counter").get_attribute("data-count")=="1"
                results.append("native_pointer_click")
                stale=await call("interact",{"ref":root_ref,"kind":"click"})
                assert stale["effect"]=="NOT_APPLIED",stale
                results.append("snapshot_consumption")
                name_ref=(await ok("locate",{"locator":{"label":"Name"}}))["elements"][0]["ref"]
                await mutate("interact",{"ref":name_ref,"kind":"fill","text":"Hermes CDP"})
                assert await page.locator("#name").input_value()=="Hermes CDP"
                shadow=(await ok("locate",{"locator":{"name":"Shadow action"}}))["elements"][0]["ref"]
                await mutate("interact",{"ref":shadow,"kind":"click"})
                assert await page.locator("#shadow").locator("button").get_attribute("data-clicked")=="1"
                results.append("semantic_fill_and_open_shadow_dom")
                cross=next(f for f in frames["frames"] if "localhost" in f["url"])
                found=await ok("locate",{"frame_id":cross["frame_id"],"locator":{"name":"Frame action"}})
                assert found["elements"],found
                await mutate("interact",{"ref":found["elements"][0]["ref"],"kind":"click"})
                cross_page=next(f for f in page.frames if "localhost" in f.url)
                assert await cross_page.locator("button").get_attribute("data-clicked")=="1"
                results.append("cross_origin_frame_native_click")
                frame_name=(await ok("locate",{"frame_id":cross["frame_id"],"locator":{"label":"Frame input"}}))["elements"][0]["ref"]
                await mutate("interact",{"ref":frame_name,"kind":"type","text":"nested target"})
                assert await cross_page.locator("input").input_value()=="nested target"
                results.append("cross_origin_frame_typing")
                upload_ref=(await ok("locate",{"locator":{"css":"input[type=file]"}}))["elements"][0]["ref"]
                up=await mutate("upload",{"ref":upload_ref,"files":[str(upload)]})
                assert up["files"][0]["name"]=="upload.txt",up
                results.append("actual_file_upload")
                hidden_ref=(await ok("locate",{"locator":{"css":"#hidden-upload"},"include_hidden":True}))["elements"][0]["ref"]
                hidden=await mutate("upload",{"ref":hidden_ref,"files":[str(upload)]})
                assert hidden["files"][0]["name"]=="upload.txt",hidden
                results.append("actual_hidden_file_input_upload")
                evaluation=await mutate("evaluate",{"expression":"window.startProof(); 'started'","world":"page"})
                assert evaluation["result"]["result"]["value"]=="started",evaluation
                await asyncio.sleep(.8)
                events=await ok("events",{"limit":120})
                methods={e["method"] for e in events["events"]}
                assert "Runtime.consoleAPICalled" in methods,methods
                assert "Network.eventSourceMessageReceived" in methods,methods
                network=await ok("network",{})
                req=next(x for x in network["requests"] if x["url"].endswith("/data"))
                assert req["complete"],req
                body=await ok("response_body",{"request_id":req["request_id"],"limit":1000})
                assert "real-network-response" in body["body"] and body["next_offset"]==1000,body
                body2=await ok("response_body",{"request_id":req["request_id"],"offset":1000,"limit":1000})
                assert body2["offset"]==1000 and body2["next_offset"]==2000,body2
                results.append("real_console_network_sse_and_body_pagination")
                capture=await ok("capture",{"full_page":True,"max_width":1000,"max_height":2000})
                assert capture["mime_type"]=="image/jpeg" and len(capture["base64"])>1000
                results.append("full_page_screenshot")
                ax=await ok("accessibility",{"limit":40})
                assert ax["nodes"],ax
                dom=await ok("dom",{"depth":1})
                assert dom.get("node") or dom.get("result_id"),dom
                results.append("accessibility_dom")
                await ok("snapshot")
                raw=await ok("cdp",{"method":"Performance.getMetrics"})
                assert "result" in raw,raw
                await ok("snapshot")
                refused=await call("cdp",{"method":"Target.getTargets"})
                assert refused["status"]=="CDP_METHOD_OUT_OF_SCOPE" and refused["effect"]=="NOT_APPLIED",refused
                await ok("snapshot")
                refused=await call("cdp",{"method":"Network.clearBrowserCookies"})
                assert refused["status"]=="CDP_METHOD_OUT_OF_SCOPE",refused
                results.append("raw_cdp_scoped_method_policy")
                wait=await ok("wait",{"locator":{"css":"#status"},"timeout_ms":2000})
                assert wait["matched"],wait
                results.append("bounded_wait")
                await mutate("emulate",{"viewport":{"width":640,"height":900,"mobile":False,"device_scale_factor":1}})
                assert await page.evaluate("innerWidth")==640
                await mutate("emulate",{"reset":True})
                results.append("responsive_emulation_and_reset")
                download=await mutate("download",{"url":url+"download","filename":"proof.txt"})
                await asyncio.sleep(.3)
                state=await ok("downloads",{"download_id":download["download_id"]})
                assert state["downloads"] and state["downloads"][0]["state"]=="complete",state
                results.append("actual_download_completion")
                stale_ref=(await ok("locate",{"locator":{"css":"#counter"}}))["elements"][0]["ref"]
                await page.evaluate("document.querySelector('#counter').replaceWith(document.querySelector('#counter').cloneNode(true))")
                await ok("snapshot")
                refused=await call("interact",{"ref":stale_ref,"kind":"click"})
                assert refused["effect"]=="NOT_APPLIED" and refused["status"]=="STALE_NODE_REF",refused
                results.append("replaced_dom_reference_refused")
                await page.locator('iframe[title="Cross origin"]').scroll_into_view_if_needed()
                covered=(await ok("locate",{"frame_id":cross["frame_id"],"locator":{"name":"Frame action"}}))["elements"][0]["ref"]
                await page.evaluate("const o=document.createElement('div');o.id='cover';o.style='position:fixed;inset:0;background:transparent;z-index:99999';document.body.append(o)")
                await ok("snapshot")
                refused=await call("interact",{"ref":covered,"kind":"click"})
                assert refused["data"]["reason"]=="TARGET_OBSCURED",refused
                assert await cross_page.locator('button').get_attribute('data-clicked')=="1"
                await page.locator('#cover').evaluate('(n)=>n.remove()')
                results.append("cross_frame_ancestor_occlusion_refused")
                # Keep Playwright from automatically dismissing the fixture dialog.
                observed_dialogs=[]
                page.on('dialog',lambda d:observed_dialogs.append(d))
                await mutate("evaluate",{"expression":"setTimeout(()=>alert('fixture-dialog'),120); 'scheduled'","world":"page"})
                await asyncio.sleep(.25)
                opening=(await ok("events",{"method":"Page.javascriptDialogOpening","limit":10}))["events"][-1]
                handled=await ok("dialog",{"dialog_ref":opening["data"]["dialog_ref"],"accept":True})
                assert handled["handled"] and observed_dialogs,handled
                results.append("dialog_recovery_without_blocked_snapshot")
                await mutate("route",{"rules":[{"url_pattern":url+"blocked*","action":"block"}]})
                blocked=await page.evaluate("fetch('/blocked-proof').then(()=>false).catch(()=>true)")
                assert blocked
                await mutate("route",{"rules":[]})
                assert await page.evaluate("fetch('/blocked-proof').then(r=>r.ok)")
                results.append("network_route_block_and_cleanup")
                settings=await browser.new_page()
                await settings.goto('chrome-extension://'+worker.url.split('/')[2]+'/browser.html')
                for width in (1100,420):
                    await settings.set_viewport_size({'width':width,'height':900})
                    assert await settings.locator('#release').count()==1
                    assert await settings.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
                evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
                await settings.set_viewport_size({'width':1100,'height':1000})
                await settings.screenshot(path=str(evidence/'browser-controls.png'),full_page=True)
                await settings.close()
                results.append("browser_controls_desktop_and_mobile_layout")
                same=next(f for f in (await ok("frames",{}))["frames"] if f["parent_id"] and not f["related_target"] and "127.0.0.1" in f["url"])
                root_before=page.url
                await mutate("cdp",{"method":"Page.navigate","frame_id":same["frame_id"],"params":{"url":url+"frame?changed"}})
                await asyncio.sleep(.2)
                assert page.url==root_before
                assert any(f.url==url+"frame?changed" for f in page.frames)
                results.append("raw_navigation_stays_in_selected_frame")
                assert await page.evaluate("fetch('/redirect-denied',{signal:AbortSignal.timeout(3000)}).then(r=>r.status)")==200
                await asyncio.sleep(.25)
                recorded=await ok("events",{"method":"Network.requestWillBeSent","limit":150})
                start=next(e for e in recorded["events"] if e["data"].get("url","").endswith('/redirect-denied'))
                refused=await call("response_body",{"request_id":start["data"]["request_id"]})
                assert refused["effect"]=="NOT_APPLIED" and refused["status"]=="RESPONSE_NOT_AVAILABLE",refused
                results.append("redirect_to_ungranted_origin_body_refused")
                await page.locator('iframe[title="Same origin"]').evaluate("(e,u)=>e.src=u","http://denied.mastermind.test:"+str(server.server_port)+"/frame?nested")
                await asyncio.sleep(.3)
                denied=next(f for f in page.frames if "denied.mastermind.test" in f.url)
                await denied.evaluate("document.body.id='UNGRANTED-NODE-MUST-NOT-APPEAR';console.log('UNGRANTED-CONTENT-MUST-NOT-APPEAR')")
                refused=await call("dom",{"frame_id":same["frame_id"],"pierce":False})
                assert refused["status"] in {"FRAME_PERMISSION_REQUIRED","FRAME_UNAVAILABLE"},refused
                refused=await call("dom",{"pierce":True,"depth":8})
                # Chrome may omit an unattached OOPIF entirely; either refusal
                # or a tree with no unauthorized document is correct.
                assert refused["status"] in {"FRAME_PERMISSION_REQUIRED","OK"},refused
                assert 'UNGRANTED-NODE-MUST-NOT-APPEAR' not in json.dumps(refused)
                observed=await ok("events",{"method":"Runtime.consoleAPICalled","limit":150})
                assert 'UNGRANTED-CONTENT-MUST-NOT-APPEAR' not in json.dumps(observed)
                results.append("navigated_frame_dom_and_console_permissions")
                await ok("cdp_detach",{})
                detached=await ok("cdp_status",{})
                assert not detached["attached"],detached
                results.append("explicit_release")
                proof={"state":"PASS","proof":"actual isolated Chromium extension APIs","cases":results,
                    "count":len(results),"version":manifest["version"],"frames":len(frames["frames"]),
                    "at":datetime.now(timezone.utc).isoformat(),"user_profiles_touched":False,"production_installation_proven":False}
                (evidence/'advanced-browser-live.json').write_text(json.dumps(proof,indent=2)+'\n')
                print(json.dumps(proof))
            except BaseException as error:
                print(json.dumps({"state":"FAIL","passed":results,"error":str(error)[:6000]}))
                raise
            finally:
                await browser.close()
    server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
