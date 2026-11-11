"""Explicit integration probe using the installed Hermes Python environment.

Creates one temporary Hermes profile and uses real PluginContext/registry APIs.
The bridge reads only an existing browser inventory; no browser action, plugin
installation, provider call, account credential or persistent config is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--bindings",required=True,type=Path)
    parser.add_argument("--source-commit",required=True)
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="mmx-hermes-browser-proof-") as directory:
        profile=Path(directory).resolve()
        os.environ["HERMES_HOME"]=str(profile)
        from hermes_cli.plugins import PluginContext,PluginManager,PluginManifest
        from tools.registry import registry
        plugin=profile/"plugins/mastermind-browser";plugin.mkdir(parents=True)
        for name in ("__init__.py","plugin.yaml"):
            shutil.copyfile(source/"integrations/hermes_harness/browser_plugin"/name,plugin/name)
        shutil.copytree(source/"integrations/hermes_harness/browser_plugin/skills",plugin/"skills")
        spec=importlib.util.spec_from_file_location("mmx_browser_registry_probe",plugin/"__init__.py")
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        descriptor=dict(schema=module.RUNTIME_SCHEMA,release_commit=args.source_commit,
            source_root=str(source),python_executable=sys.executable,profile_home=str(profile),bindings_path=str(args.bindings),
            source_files={p:hashlib.sha256((source/p).read_bytes()).hexdigest() for p in module.SOURCE_FILES})
        (plugin/"_runtime.json").write_text(json.dumps(descriptor));(plugin/"_runtime.json").chmod(0o600)
        manifest=PluginManifest(name="mastermind-browser",version="0.5.0",source="user",path=str(plugin),provides_tools=["mmx_browser"])
        manager=PluginManager(scope_key=str(profile));ctx=PluginContext(manifest,manager)
        handle=module.register(ctx)
        entry=registry.snapshot_registration("mmx_browser",scope=manager.scope_key)
        assert entry is not None and entry.toolset=="mastermind_browser"
        assert manager.list_plugin_skills("mastermind-browser")==["hermes-browser","hermes-browser-debug","hermes-browser-files"]
        refusal=json.loads(entry.handler({"action":"browsers"}))
        assert refusal["reason"]=="NATIVE_SESSION_UNBOUND"
        observed=json.loads(entry.handler({"action":"browsers"},session_id="native-registry-qualification"))
        assert observed["state"]=="OBSERVED",observed
        rows=observed["browsers"]
        assert len({(row.get("host_ref"),row["browser_id"]) for row in rows})==len(rows)
        handle.dispose()
        assert registry.snapshot_registration("mmx_browser",scope=manager.scope_key) is None
        assert json.loads(entry.handler({"action":"browsers"},session_id="native-registry-qualification"))["reason"]=="NATIVE_REGISTRATION_STALE"
        print(json.dumps({"state":"PASS","proof":"installed Hermes registry in temporary profile",
            "registered_tool":"mmx_browser","inventory_count":len(rows),"unbound_session_refused":True,
            "native_unload_verified":True,"skills_registered":3,"browser_actions_dispatched":0,"production_plugin_installed":False}))


if __name__=="__main__":
    main()
