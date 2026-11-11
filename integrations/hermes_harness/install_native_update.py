"""Pinned native Hermes replacement under Hermes' existing publication lock.

Run with the installed Hermes Python. Source removal, scanner, dependency
admission, registration and activation remain owned by the native runtime.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from integrations.hermes_harness.install_browser import digest, json_bytes, read_owned, write_owned


def update(spec):
    required={"profile_home","hermes_runtime","package","package_commit","descriptor","expected"}
    if not isinstance(spec,dict) or set(spec)!=required:raise RuntimeError("invalid native update specification")
    profile=Path(spec["profile_home"]);package=Path(spec["package"])
    if not profile.is_absolute() or not profile.is_dir() or not package.is_absolute():raise RuntimeError("invalid native installation path")
    os.environ["HERMES_HOME"]=str(profile)
    sys.path.insert(0,spec["hermes_runtime"])
    import hermes_bootstrap
    from hermes_cli import plugins_cmd as pc,plugins_cmd_catalog as catalog
    from hermes_cli.plugins_cmd_install import _install_plugin_core,recorded_install
    from hermes_cli.plugins_auto_update import plugin_update_lock
    from hermes_cli.plugins_activation import activate_plugin_now
    from pm.workspace import enabled_plugin_dirs
    import hermes_constants
    if Path(hermes_constants.get_hermes_home()).resolve()!=profile.resolve():raise RuntimeError("native profile selection mismatch")
    target=profile/"plugins/mastermind-browser"
    source=package.as_uri();expected=spec["expected"]
    descriptor=spec["descriptor"]
    if descriptor.get("profile_home")!=str(profile):raise RuntimeError("descriptor profile mismatch")
    next_descriptor=json_bytes(descriptor)
    git_url,_=pc._resolve_git_url(source)
    catalog.raise_if_removed(source,git_url)
    with plugin_update_lock(target):
        prior=pc._read_install_metadata().get("mastermind-browser")
        if not isinstance(prior,dict) or set(expected)!={"source","package_commit","runtime_sha256"}:
            raise RuntimeError("native prior installation required")
        head=subprocess.check_output(["git","-C",str(target),"rev-parse","HEAD"],text=True).strip()
        if (prior.get("source")!=expected["source"] or prior.get("revision")!=expected["package_commit"]
                or head!=expected["package_commit"] or digest(read_owned(target/"_runtime.json"))!=expected["runtime_sha256"]):
            raise RuntimeError("native prior installation changed")
        local,tracked=catalog._local_changes(target)
        if tracked:raise RuntimeError("native tracked plugin code has local edits")
        was_enabled=target.resolve() in enabled_plugin_dirs()
        # Preserve a recoverable descriptor outside the scanned plugin slot.
        backup=profile/"plugins-backup"/("mastermind-browser-"+expected["package_commit"][:12])
        write_owned(backup/"_runtime.json",read_owned(target/"_runtime.json"))
        def before_swap(manifest,tree):
            if manifest.get("name")!="mastermind-browser":raise RuntimeError("native package identity mismatch")
            merged=catalog._carry_user_files(target,tree,local)
            runtime=tree/"_runtime.json"
            write_owned(runtime,next_descriptor,expected=digest(read_owned(runtime)) if runtime.exists() else None)
            module_spec=importlib.util.spec_from_file_location("mmx_candidate_browser_runtime",tree/"__init__.py")
            module=importlib.util.module_from_spec(module_spec);sys.modules[module_spec.name]=module
            module_spec.loader.exec_module(module)
            module.load_runtime()
            return sorted(set(merged or [])|{"_runtime.json"})
        target,manifest,name=recorded_install(lambda:_install_plugin_core(source,force=True,
            accept_caution=False,ref=spec["package_commit"],assume_deps_consent=True,before_swap=before_swap),
            identifier=source,catalog_name=None)
        after=pc._read_install_metadata().get(name,{})
        if (after.get("source")!=source or after.get("revision")!=spec["package_commit"]
                or digest(read_owned(target/"_runtime.json"))!=digest(next_descriptor)):
            raise RuntimeError("native installation readback mismatch")
        if was_enabled and target.resolve() not in enabled_plugin_dirs():raise RuntimeError("native selection was not preserved")
        if not was_enabled:pc._set_plugin_enabled(name,enable=True,console=pc._console())
    activation=activate_plugin_now(name,in_process=False)
    return {"state":"NATIVE_PACKAGE_INSTALLED","profile":str(profile),"package_commit":spec["package_commit"],
        "source_commit":descriptor["release_commit"],"descriptor_sha256":digest(next_descriptor),
        "activation_requested":True,"python_tool_session_requirement":"fresh native session",
        "activation_result":str(activation)[:2000]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--spec",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True);args=parser.parse_args()
    result=update(json.loads(read_owned(args.spec)))
    write_owned(args.receipt,json_bytes(result))
    print(json.dumps(result))


if __name__=="__main__":main()
