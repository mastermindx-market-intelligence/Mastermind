"""Compiled Fleet UI proof using synthetic fixtures and an ephemeral loopback origin."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import argparse
import json
import time
from playwright.sync_api import sync_playwright, expect

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--build-dir",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    assert (args.build_dir/"fleet-browser-proof.html").is_file()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self,*_args): pass
    server=ThreadingHTTPServer(("127.0.0.1",0),partial(QuietHandler,directory=str(args.build_dir)))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f"http://127.0.0.1:{server.server_port}"
    errors=[]
    started=time.time()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(viewport={"width":1440,"height":1100},device_scale_factor=1)
            context.route("**/*",lambda route: route.continue_() if route.request.url.startswith(origin+"/") else route.abort())
            page=context.new_page()
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(origin+"/fleet-browser-proof.html?work_ref=WS%3AFABRIC&root_job_id=JOB-001",wait_until="networkidle")
            page.set_default_timeout(10000)
            page.locator("summary").filter(has_text="Advanced").click()
            page.get_by_role("button",name="Fleet & Capacity workspace",exact=True).click()
            region=page.get_by_role("region",name="Fleet hardware health")
            expect(region.get_by_role("button",name="Inspect Ubuntu 2",exact=True)).to_be_visible()
            expect(region.get_by_role("button",name="Inspect M1 Studio",exact=True)).to_be_visible()
            text=region.inner_text()
            assert "0%" in text and "stale" in text.lower(),text
            region.get_by_role("button",name="30d",exact=True).click()
            expect(region.get_by_role("button",name="30d",exact=True)).to_have_attribute("aria-pressed","true")
            expect(region.get_by_role("button",name="Inspect Ubuntu 2",exact=True)).to_be_visible()
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(args.output_dir/"fleet-desktop-synthetic.png"),full_page=True)
            page.set_viewport_size({"width":390,"height":844})
            page.evaluate("window.scrollTo(0,0)")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"),"horizontal page overflow"
            page.screenshot(path=str(args.output_dir/"fleet-mobile-synthetic.png"),full_page=True)
            page.get_by_role("button",name="Synthetic sign out",exact=True).click()
            expect(region).to_have_count(0)
            expect(page.get_by_role("button",name="Inspect Ubuntu 2",exact=True)).to_have_count(0)
            assert not errors,errors
            receipt={"proof":"compiled App browser execution with explicitly synthetic host/auth fixtures",
                "installed_service_proof":False,"cross_uid_proof":False,"host_effects":False,
                "checks":["actual Resources/Fleet navigation","measured zero","stale host and missing sensors",
                    "fixed 30d window selector","390px page width","auth revocation removes hardware region"],
                "elapsed_seconds":round(time.time()-started,2),"console_page_errors":errors,
                "viewports":[[1440,1100],[390,844]]}
            (args.output_dir/"browser-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
            print(json.dumps(receipt),flush=True)
            context.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=="__main__": main()
