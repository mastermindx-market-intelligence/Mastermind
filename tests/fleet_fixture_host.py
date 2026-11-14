"""Bounded, attended remote Chrome fixture; no third-party Python dependency.

Only a disposable Chrome for Testing profile receives loopback test grants.
The controlling SSH stdin or a ten-minute deadline owns its lifetime.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from integrations.chairman_surfaces.web_sol_deployment import WebSolRelease,render_instance_bundle
from integrations.chairman_surfaces.web_sol_client import browser_via_extension,WebSolExtensionError
from integrations.hermes_harness import browser_routes as routes

ROOT=Path(__file__).resolve().parents[1]


class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_GET(self):
        body=b'''<!doctype html><title>Isolated fleet proof</title><style>body{font:18px sans-serif;margin:40px}button,input{padding:16px;margin:10px}</style><h1>Mastermind fleet fixture</h1><button id="counter" aria-label="Increment" onclick="this.dataset.count=String(Number(this.dataset.count||0)+1)">Increment</button><label>Upload <input type="file" aria-label="Upload fixture"></label>'''
        self.send_response(200);self.send_header("Content-Type","text/html");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)


def stop(process):
    if process is None or process.poll() is not None:return
    # This isolated process group was created here and contains no user browser.
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


def main(args):
    server=ThreadingHTTPServer(("127.0.0.1",0),Fixture);Fixture.port=server.server_port
    threading.Thread(target=server.serve_forever,daemon=True).start()
    process=None
    try:
        with tempfile.TemporaryDirectory(prefix="mmx-fleet-proof-") as directory:
            stage=Path(directory);instance=hashlib.sha256(secrets.token_bytes(32)).hexdigest()
            release=WebSolRelease("0.4.0",args.source_commit,ROOT,Path(sys.executable),stage/"bridge")
            bundle=render_instance_bundle(instance,release)
            for artifact in bundle.artifacts:
                artifact.destination.parent.mkdir(parents=True,exist_ok=True)
                artifact.destination.write_bytes(artifact.content);artifact.destination.chmod(artifact.mode)
            extension=stage/"extension";shutil.copytree(ROOT/"integrations/chairman_surfaces/web_sol_extension",extension)
            manifest=json.loads((extension/"manifest.json").read_text())
            manifest.update(permissions=["nativeMessaging","alarms","debugger","storage","tabs","scripting","downloads"],
                host_permissions=["http://127.0.0.1/*","http://localhost/*"],optional_permissions=[],optional_host_permissions=[])
            (extension/"manifest.json").write_text(json.dumps(manifest))
            shutil.copyfile(next(a.destination for a in bundle.artifacts if a.kind=="instance_config"),extension/"instance_config.js")
            data=stage/"chrome";native_root=data/"NativeMessagingHosts";native_root.mkdir(parents=True)
            native=next(a for a in bundle.artifacts if a.kind=="native_host_manifest")
            native_path=native_root/native.destination.name;native_path.write_bytes(native.content);native_path.chmod(0o600)
            uploads=stage/"uploads";uploads.mkdir();(uploads/"upload.txt").write_text("remote fleet upload fixture")
            denied=stage/"outside.txt";denied.write_text("outside admitted fixture upload root")
            row=dict(host_ref=args.host_ref,browser_id=instance,alias="isolated-proof",label="Isolated fleet qualification",manager="chrome",
                profile_directory="Default",profile_name="Disposable",account_hint="test fixture",data_directory=str(data),extension_path=str(extension),
                native_host_manifest=str(native_path),chrome_executable=args.chrome,upload_roots=[str(uploads)])
            inventory=stage/"inventory.json";inventory.write_text(json.dumps(dict(schema=routes.SCHEMA,local_host_ref=args.host_ref,
                hosts=[dict(host_ref=args.host_ref,label=args.host_ref,transport="local")],profiles=[row])))
            fixture="http://127.0.0.1:"+str(server.server_port)+"/"
            argv=[args.chrome,"--headless=new","--no-first-run","--no-default-browser-check","--user-data-dir="+str(data),
                "--disable-extensions-except="+str(extension),"--load-extension="+str(extension),fixture]
            # The first clean close lets Chrome persist its own registration.
            # Neither production nor fixture Chrome preferences are edited.
            log=(stage/"chrome.log").open("wb")
            try:
                for boot in range(2):
                    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                    status=None
                    for _ in range(40):
                        if process.poll() is not None:raise RuntimeError("fixture Chrome exited")
                        try:
                            status=browser_via_extension(instance,session_id="b"*64,operation_key="fleet-fixture-readiness",action="status")
                            if status.get("status")=="OK":break
                        except WebSolExtensionError:pass
                        time.sleep(.2)
                    if not status or status.get("status")!="OK":raise RuntimeError("fixture native connection unavailable")
                    if boot==0:stop(process);process=None
                registered=routes.registration(row)
                if registered.get("activation")!="LOADED":raise RuntimeError("fixture Chrome registration: "+json.dumps(registered))
                build_hash=hashlib.sha256((ROOT/"BUILD.json").read_bytes()).hexdigest()
                print(json.dumps(dict(state="FIXTURE_READY",profile=row,host=dict(host_ref=args.host_ref,label=args.host_ref,transport="ssh",
                    ssh_alias=args.ssh_alias,python_executable=sys.executable,source_root=str(ROOT),bindings_path=str(inventory),manifest_sha256=build_hash),
                    fixture_url=fixture,browser_upload=str(uploads/"upload.txt"),upload_denied=str(denied))),flush=True)
                if select.select([sys.stdin],[],[],600)[0]:sys.stdin.buffer.readline()
            finally:
                stop(process);process=None;log.close()
            print(json.dumps({"state":"FIXTURE_CLOSED","user_profiles_touched":False}),flush=True)
    finally:
        stop(process);server.shutdown()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    for name in ("source-commit","host-ref","ssh-alias","chrome"):parser.add_argument("--"+name,required=True)
    main(parser.parse_args())
