"""Actual installed Hermes loader/registry canary; no provider, live profile or grants.

Run with the installed hermes_cli._launchers.runtime_command(code=...) owner.
The temporary profile uses the actual installed OMH interpreter/package for
recommendations and the exact supplied Mastermind source files for proposals.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import sys
import tempfile


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-root',required=True)
    p.add_argument('--omh-python',required=True)
    p.add_argument('--omh-home',required=True)
    p.add_argument('--release-commit',required=True)
    a=p.parse_args()
    root=Path(a.source_root).resolve()
    source=root/'integrations/hermes_omh/plugin'
    spec=importlib.util.spec_from_file_location('_mmx_omh_canary_source',source/'__init__.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    blocked=[]
    original_connect=socket.socket.connect
    def deny_connect(sock,address):
        blocked.append(type(address).__name__)
        raise RuntimeError('No network is permitted in native qualification')
    socket.socket.connect=deny_connect
    try:
        from hermes_cli.plugins import PluginManager
        from tools.registry import registry
        with tempfile.TemporaryDirectory(prefix='mmx-omh-native-canary-') as rawhome:
            home=Path(rawhome).resolve();os.environ['HERMES_HOME']=str(home)
            dest=home/'plugins/mastermind-omh';dest.mkdir(parents=True)
            for name in ('__init__.py','plugin.yaml'):shutil.copyfile(source/name,dest/name)
            descriptor=dict(schema=module.RUNTIME_SCHEMA,release_commit=a.release_commit,source_root=str(root),
                            python_executable=a.omh_python,profile_home=str(home),omh_home=a.omh_home,
                            source_files={r:hashlib.sha256((root/r).read_bytes()).hexdigest() for r in module.SOURCE_FILES})
            (dest/'_runtime.json').write_text(json.dumps(descriptor));(dest/'_runtime.json').chmod(0o600)
            config='plugins:\n  enabled: [mastermind-omh]\n  auto_apply: false\n'
            (home/'config.yaml').write_text(config)
            manager=PluginManager(scope_key=str(home))
            manager.discover_and_load()
            entry=registry.snapshot_registration('mmx_omh',scope=str(home))
            if entry is None:raise AssertionError('Native loader did not register mmx_omh')
            assert entry.toolset=='mmx_omh'
            results={}
            proposal=json.loads((root/'integrations/hermes_omh/example.json').read_text())
            for name,args in (
                ('status',{'action':'status'}),
                ('plan',{'action':'plan','proposal':proposal}),
                ('recommend',{'action':'recommend','message':'Inspect a Python bug and write a regression test','category':'quick'}),
            ):
                raw=registry.dispatch('mmx_omh',args,scope=str(home),session_id='mmx-omh-canary-session',task_id='mmx-omh-canary-task')
                value=json.loads(raw) if isinstance(raw,str) else raw
                if value.get('state')=='REFUSED':raise AssertionError(f'Native {name} refused: {value.get("reason")}')
                assert value['admitted'] is False and value['dispatched'] is False
                results[name]=value
            assert results['plan']['state']=='PREPARED_NOT_ADMITTED'
            assert results['recommend']['state']=='RECOMMENDED_NOT_ADMITTED'
            assert results['recommend']['omh_version']=='4.0.6'
            from hermes_cli.plugin_command_dispatch import invoke_plugin_command
            command=manager._plugin_commands['mmx-omh']['handler']
            command_status=json.loads(invoke_plugin_command(command,'status',session_id='mmx-omh-canary-session',platform='cli'))
            command_advice=json.loads(invoke_plugin_command(command,'quick Inspect a Python bug and write a regression test',session_id='mmx-omh-canary-session',platform='cli'))
            assert command_status['state']=='LOCAL_BRIDGE_READY'
            assert command_advice['state']=='RECOMMENDED_NOT_ADMITTED'
            from hermes_cli.plugins_activation import activation_summaries
            activations=[x for x in activation_summaries(manager) if x['name']=='mastermind-omh']
            assert len(activations)==1 and 'mmx-omh' in activations[0]['activated_now']['gateway_commands']
            assert 'mmx_omh' in activations[0]['deferred']['tools']
            os.environ['HERMES_HOME']=str(home/'foreign')
            denied=json.loads(entry.handler({'action':'status'},session_id='mmx-omh-canary-session'))
            assert denied['state']=='REFUSED' and denied['reason']=='NATIVE_PROFILE_MISMATCH'
            os.environ['HERMES_HOME']=str(home)
            assert (home/'config.yaml').read_text()==config
            assert not blocked
            print(json.dumps({'schema':'mastermind.hermes_omh.native_canary/v1',
                'source_commit':a.release_commit,'source_files_sha256':hashlib.sha256(json.dumps(descriptor['source_files'],sort_keys=True).encode()).hexdigest(),
                'native_loader':'PluginManager.discover_and_load','native_dispatch':'ToolRegistry.dispatch','native_command_dispatch':'invoke_plugin_command',
                'live_command':'mmx-omh','live_command_status':command_status['state'],
                'live_command_advice':command_advice['state'],'tool_activation':'next_session_by_native_contract',
                'status':results['status']['state'],'plan':results['plan']['state'],
                'plan_sha256':results['plan']['plan_sha256'],'recommendation':results['recommend']['state'],
                'model_candidates':results['recommend']['model_candidates'],'skills':results['recommend']['skills'],
                'cross_profile':'REFUSED','profile_config_unchanged':True,'blocked_network_attempts':len(blocked),
                'production_profile_changed':False,'provider_called':False,'admitted':False,'dispatched':False},sort_keys=True))
    finally:socket.socket.connect=original_connect
    return 0


if __name__=='__main__':raise SystemExit(main())
