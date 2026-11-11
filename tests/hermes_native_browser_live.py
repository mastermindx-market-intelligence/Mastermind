"""Actual Hermes registration -> subprocess -> Unix socket -> native host -> Chrome proof."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]


def native_probe(args):
    # Reuse the installed runtime's admitted dependencies, then select the
    # disposable profile before constructing native registration/context owners.
    os.environ["HERMES_HOME"]=str(Path.home()/".hermes")
    sys.path.insert(0,str(args.hermes_runtime))
    import hermes_bootstrap  # Install the native runtime's dependency paths.
    sys.path.insert(0,str(ROOT))
    os.environ["HERMES_HOME"]=str(args.profile)
    from hermes_cli.plugins import PluginContext,PluginManager,PluginManifest
    from tools.registry import registry
    original=ROOT/"integrations/hermes_harness/browser_plugin"
    plugin=args.profile/"plugins/mastermind-browser"
    shutil.copytree(original,plugin,ignore=shutil.ignore_patterns("__pycache__"))
    spec=importlib.util.spec_from_file_location("mastermind_native_live",plugin/"__init__.py")
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    upload=args.profile/"upload.txt";upload.write_text("native Hermes upload proof")
    descriptor=dict(schema=module.RUNTIME_SCHEMA,release_commit=args.source_commit,source_root=str(ROOT),
        python_executable=sys.executable,profile_home=str(args.profile),bindings_path=str(args.inventory),
        source_files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in module.SOURCE_FILES},
        upload_roots=[str(args.profile)],artifact_root=str(args.profile/"artifacts"))
    if args.host_ref:descriptor["host_ref"]="m2"
    (plugin/"_runtime.json").write_text(json.dumps(descriptor));(plugin/"_runtime.json").chmod(0o600)
    manifest=PluginManifest(name="mastermind-browser",version="0.5.0",source="user",path=str(plugin),provides_tools=["mmx_browser"])
    manager=PluginManager(scope_key=str(args.profile));ctx=PluginContext(manifest,manager)
    handle=module.register(ctx)
    entry=registry.snapshot_registration("mmx_browser",scope=manager.scope_key)
    assert entry is not None
    skills=manager.list_plugin_skills("mastermind-browser")
    assert len(skills)==3,skills
    cases=["native_hermes_plugin_and_skills"]
    identity=dict(browser_id=args.instance)
    if args.host_ref:identity["host_ref"]=args.host_ref
    selected={}
    session="actual-hermes-native-browser-proof-"+secrets.token_hex(12)
    snapshot=None
    def call(action,options=None,*,unbound=False,**extra):
        nonlocal snapshot
        from integrations.chairman_surfaces import web_sol_browser_protocol as protocol
        params=dict(action=action)
        if action!="browsers":params.update(identity)
        if action in protocol.TAB_ACTIONS:params.update(selected)
        if action in protocol.TAB_ACTIONS-protocol.NO_SNAPSHOT:params["snapshot_id"]=snapshot
        if action in protocol.ADVANCED_ACTIONS:params["options"]=options or {}
        params.update(extra)
        raw=entry.handler(params,**({} if unbound else {"session_id":session}))
        if isinstance(raw,dict) and raw.get("_multimodal"):return raw
        out=json.loads(raw)
        if action=="browsers":return out
        assert out.get("state")=="RECEIPT",out
        receipt=out["receipt"];assert receipt["status"] in ("OK","ACTION_DISPATCHED"),receipt
        data=receipt["data"]
        if action=="snapshot":snapshot=data["snapshot_id"]
        return data
    refusal=json.loads(entry.handler({"action":"browsers"}))
    assert refusal["reason"]=="NATIVE_SESSION_UNBOUND",refusal
    assert call("browsers")["browsers"]
    status=call("status")
    assert status["package_version"]=="0.4.1" and status["advanced_cdp_available"],status
    count=3 if args.host_ref else 20
    for _ in range(count):assert call("status")["connection_id"]==status["connection_id"]
    cases.append(str(count)+"_sequential_native_handshakes")
    identity["connection_id"]=status["connection_id"]
    tabs=call("tabs")["tabs"]
    row=next(x for x in tabs if x["url_fingerprint"]==hashlib.sha256(args.fixture_url.encode()).hexdigest())
    selected.update(tab_id=row["tab_id"],url_fingerprint=row["url_fingerprint"])
    call("snapshot")
    call("cdp_attach",{"network":True})
    cases.append("real_native_handshake_and_persistent_cdp")
    ref=call("locate",{"locator":{"name":"Increment","role":"button"}})["elements"][0]["ref"]
    call("snapshot");call("interact",{"ref":ref,"kind":"click"})
    call("snapshot")
    readback=call("evaluate",{"expression":"document.querySelector('#counter').dataset.count"})
    assert readback["result"]["result"]["value"]=="1",readback
    cases.append("actual_native_hermes_click_and_verified_result")
    ref=call("locate",{"locator":{"css":"input[type=file]"}})["elements"][0]["ref"]
    refused=json.loads(entry.handler(dict(action="upload",**identity,**selected,snapshot_id=snapshot,
        options={"ref":ref,"files":[args.upload_denied or str(ROOT/"integrations/__init__.py")]}),session_id=session))
    assert refused["reason"]=="UPLOAD_FILE_OUTSIDE_ROOTS",refused
    if args.skip_upload:
        assert status.get("upload_file_access_allowed") is False,status
        cases.append("destination_upload_root_refusal_and_observed_Chrome_file_permission_gate")
    else:
        call("snapshot");uploaded=call("upload",{"ref":ref,"files":[args.browser_upload or str(upload)]})
        assert uploaded["files"][0]["name"]=="upload.txt",uploaded
        cases.append("native_upload_root_refusal_and_actual_upload")
    image=call("capture",{"max_width":900,"max_height":700})
    assert image["_multimodal"] and image["content"][1]["type"]=="image_url"
    cases.append("native_hermes_multimodal_screenshot")
    pdf=call("pdf",{"print_background":True})
    artifact=Path(pdf["artifact_path"])
    assert artifact.is_relative_to(args.profile/"artifacts") and artifact.read_bytes().startswith(b"%PDF-")
    if args.host_ref:assert pdf["artifact_host_ref"]=="m2" and pdf["browser_host_ref"]==args.host_ref,pdf
    cases.append("native_browser_pdf_artifact")
    call("cdp_detach")
    assert call("cdp_status")["attached"] is False
    handle.dispose()
    assert json.loads(entry.handler({"action":"browsers"},session_id=session))["reason"]=="NATIVE_REGISTRATION_STALE"
    cases.append("native_release_and_registration_unload")
    proof=dict(state="PASS",proof="real native Hermes -> subprocess -> Unix socket -> native host -> Chrome",
        cases=cases,count=len(cases),skills=skills,extension_version="0.4.1",plugin_version="0.5.0",source_commit=args.source_commit,
        browser_host_ref=args.host_ref or "local",remote_ssh=bool(args.host_ref),
        upload="Chrome_file_access_permission_required" if args.skip_upload else "verified",
        user_profiles_touched=False,production_chrome_loaded=False)
    print(json.dumps(proof))


async def browser_parent(args):
    from playwright.async_api import async_playwright
    from advanced_browser_live import Fixture
    from http.server import ThreadingHTTPServer
    from integrations.chairman_surfaces.web_sol_deployment import WebSolRelease,render_instance_bundle
    server=ThreadingHTTPServer(("127.0.0.1",0),Fixture);Fixture.port=server.server_port
    threading.Thread(target=server.serve_forever,daemon=True).start()
    native_manifest=None
    try:
        with tempfile.TemporaryDirectory(prefix="mastermind-native-proof-") as directory:
            stage=Path(directory)
            instance=hashlib.sha256(("mastermind-native-proof-"+secrets.token_hex(20)).encode()).hexdigest()
            release=WebSolRelease("0.4.0",args.source_commit,ROOT,args.hermes_python,stage/"bridge")
            bundle=render_instance_bundle(instance,release)
            for artifact in bundle.artifacts:
                artifact.destination.parent.mkdir(parents=True,exist_ok=True)
                artifact.destination.write_bytes(artifact.content);artifact.destination.chmod(artifact.mode)
            extension=stage/"extension"
            shutil.copytree(ROOT/"integrations/chairman_surfaces/web_sol_extension",extension)
            manifest=json.loads((extension/"manifest.json").read_text())
            manifest["permissions"]=["nativeMessaging","alarms","debugger","tabs","scripting","downloads"]
            manifest["host_permissions"]=["http://127.0.0.1/*","http://localhost/*"]
            manifest["optional_permissions"]=[];manifest["optional_host_permissions"]=[]
            (extension/"manifest.json").write_text(json.dumps(manifest))
            shutil.copyfile(next(a.destination for a in bundle.artifacts if a.kind=="instance_config"),extension/"instance_config.js")
            native=next(a for a in bundle.artifacts if a.kind=="native_host_manifest")
            # Chrome derives user-level native hosts from the active user-data-dir,
            # which is this disposable fixture profile rather than the default path.
            native_root=stage/"chrome/NativeMessagingHosts"
            native_root.mkdir(parents=True,exist_ok=True)
            native_manifest=native_root/native.destination.name
            # This random fixture host has no existing owner; never overwrite one.
            with native_manifest.open("xb") as stream:stream.write(native.content)
            native_manifest.chmod(0o600)
            inventory=stage/"inventory.json"
            inventory.write_text(json.dumps(dict(schema="mastermind.browser_deployments.v1",profiles=[dict(
                browser_id=instance,label="Isolated native qualification",manager="chrome",extension_path=str(extension),
                native_host_manifest=str(native_manifest))])))
            profile=stage/"hermes";profile.mkdir()
            async with async_playwright() as pw:
                browser=await pw.chromium.launch_persistent_context(str(stage/"chrome"),executable_path=args.chrome,
                    headless=True,ignore_default_args=["--disable-extensions"],
                    args=["--no-sandbox","--disable-extensions-except="+str(extension),"--load-extension="+str(extension)])
                try:
                    worker=browser.service_workers[0] if browser.service_workers else await browser.wait_for_event("serviceworker")
                    fixture="http://127.0.0.1:"+str(server.server_port)+"/"
                    page=await browser.new_page();await page.goto(fixture)
                    settings=await browser.new_page()
                    await settings.goto("chrome-extension://"+worker.url.split("/")[2]+"/browser.html")
                    for attempt in range(40):
                        state=await settings.evaluate("chrome.runtime.sendMessage({kind:'MMX_BROWSER_UI_STATUS'})")
                        if state and state.get("ready"):break
                        await asyncio.sleep(.1)
                    assert state and state.get("ready"),state
                    child=await asyncio.create_subprocess_exec(str(args.hermes_python),str(Path(__file__).resolve()),
                        "--probe","--profile",str(profile),"--instance",instance,"--inventory",str(inventory),
                        "--fixture-url",fixture,"--source-commit",args.source_commit,"--hermes-runtime",str(args.hermes_runtime),
                        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    out,err=await asyncio.wait_for(child.communicate(),timeout=90)
                    print(out.decode())
                    if child.returncode:
                        raise RuntimeError(err.decode()[-10000:])
                    proof=json.loads(out)
                    evidence=ROOT/"evidence";evidence.mkdir(exist_ok=True)
                    (evidence/"hermes-native-browser-live.json").write_text(json.dumps(proof,indent=2)+"\n")
                finally:
                    await browser.close()
    finally:
        if native_manifest and native_manifest.exists():
            native_manifest.unlink()
        server.shutdown()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--probe",action="store_true")
    parser.add_argument("--skip-upload",action="store_true")
    for name in ("profile","inventory","hermes-runtime","hermes-python"):
        parser.add_argument("--"+name,type=Path)
    for name in ("instance","fixture-url","source-commit","chrome","host-ref","browser-upload","upload-denied"):
        parser.add_argument("--"+name)
    args=parser.parse_args()
    if args.probe:native_probe(args)
    else:asyncio.run(browser_parent(args))


if __name__=="__main__":
    main()
