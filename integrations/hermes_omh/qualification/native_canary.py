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
    p.add_argument('--capacity-config',help='Existing operator profile config; reuse only its read-only capacity MCP entry')
    a=p.parse_args()
    root=Path(a.source_root).resolve()
    source=root/'integrations/hermes_omh/plugin'
    spec=importlib.util.spec_from_file_location('_mmx_omh_canary_source',source/'__init__.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    capacity=None
    if a.capacity_config:
        import hermes_yaml as yaml
        original=yaml.safe_load(Path(a.capacity_config).read_text())
        capacity=original.get('mcp_servers',{}).get('mastermind-fabric-capacity')
        if type(capacity) is not dict or capacity.get('enabled') is not True:
            raise AssertionError('Existing read-only capacity server is not enabled')
        if set(capacity)-{'command','args','enabled','connect_timeout'}:
            raise AssertionError('Canary does not copy credential, trust or unknown server configuration')
        if ('connect_timeout' in capacity and
                (type(capacity['connect_timeout']) not in (int,float) or not 1<=capacity['connect_timeout']<=60)):
            raise AssertionError('Invalid existing capacity connection timeout')
        if (capacity.get('command')!='/opt/homebrew/bin/python3'
                or capacity.get('args')!=['/Users/chriswong/.hermes/bridges/fabric_capacity_mcp.py']):
            raise AssertionError('Canary supports only the observed existing M2 read-only bridge')
    blocked=[]
    original_connect=socket.socket.connect
    def deny_connect(sock,address):
        blocked.append(type(address).__name__)
        raise RuntimeError('No network is permitted in native qualification')
    socket.socket.connect=deny_connect
    try:
        from hermes_cli.plugins import get_plugin_manager
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
            if capacity is not None:
                config=yaml.safe_dump(dict(
                    plugins=dict(enabled=['mastermind-omh'],auto_apply=False,
                                 entries={'mastermind-omh':dict(mcp_allowlist=['mastermind-fabric-capacity'])}),
                    mcp_servers={'mastermind-fabric-capacity':capacity}))
            (home/'config.yaml').write_text(config)
            manager=get_plugin_manager()
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
            route=None
            if capacity is not None:
                from tools.mcp_tool_discovery import discover_mcp_tools
                discover_mcp_tools(allowed_mcp_names=['mastermind-fabric-capacity'])
                request=dict(action='route',message='Inspect the existing capacity routing contracts',
                             category='quick',task_class='census',complexity='C1_ROUTINE_BOUNDED')
                route=json.loads(registry.dispatch('mmx_omh',request,scope=str(home),
                    session_id='mmx-omh-route-canary',task_id='mmx-omh-route-task'))
                if route.get('state')!='ROUTE_PREVIEW_NOT_ADMITTED':
                    raise AssertionError(f'Native route refused: {route.get("reason")}')
                assert route['routing_requirements']==dict(task_class='census',complexity='C1_ROUTINE_BOUNDED')
                assert route['capacity_preview']['reserved'] is False
                assert route['capacity_preview']['selection_rechecked_at_request'] is True
                assert route['recommendation']['selected_model'] is None
                invalid=dict(request,pool='unqualified-omh-pool')
                invalid_out=json.loads(registry.dispatch('mmx_omh',invalid,scope=str(home),
                    session_id='mmx-omh-route-canary',task_id='mmx-omh-route-task'))
                assert invalid_out['state']=='REFUSED' and invalid_out['reason']=='NATIVE_REQUEST_INVALID'
            from hermes_cli.plugin_command_dispatch import invoke_plugin_command
            command=manager._plugin_commands['mmx-omh']['handler']
            command_status=json.loads(invoke_plugin_command(command,'status',session_id='mmx-omh-canary-session',platform='cli'))
            command_advice=json.loads(invoke_plugin_command(command,'quick Inspect a Python bug and write a regression test',session_id='mmx-omh-canary-session',platform='cli'))
            assert command_status['state']=='LOCAL_BRIDGE_READY'
            assert command_advice['state']=='RECOMMENDED_NOT_ADMITTED'
            command_route=None
            if route is not None:
                command_route=json.loads(invoke_plugin_command(command,
                    'route census C1_ROUTINE_BOUNDED quick Inspect the existing capacity routing contracts',
                    session_id='mmx-omh-canary-session',platform='cli'))
                assert command_route['state']=='ROUTE_PREVIEW_NOT_ADMITTED'
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
                'source_commit':a.release_commit,'canary_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'plugin_sha256':hashlib.sha256((source/'__init__.py').read_bytes()).hexdigest(),
                'source_files_sha256':hashlib.sha256(json.dumps(descriptor['source_files'],sort_keys=True).encode()).hexdigest(),
                'native_loader':'PluginManager.discover_and_load','native_dispatch':'ToolRegistry.dispatch','native_command_dispatch':'invoke_plugin_command',
                'live_command':'mmx-omh','live_command_status':command_status['state'],
                'live_command_advice':command_advice['state'],'tool_activation':'next_session_by_native_contract',
                'status':results['status']['state'],'plan':results['plan']['state'],
                'plan_sha256':results['plan']['plan_sha256'],'recommendation':results['recommend']['state'],
                'model_candidates':results['recommend']['model_candidates'],'skills':results['recommend']['skills'],
                'capacity_client':'PluginContext.call_mcp' if route else None,
                'capacity_server':'mastermind-fabric-capacity' if route else None,
                'capacity_preview':route['capacity_preview'] if route else None,
                'routing_requirements':route['routing_requirements'] if route else None,
                'routing_state':route['state'] if route else None,
                'live_command_routing_state':command_route['state'] if command_route else None,
                'forced_pool':'REFUSED' if route else None,
                'cross_profile':'REFUSED','profile_config_unchanged':True,'blocked_network_attempts':len(blocked),
                'production_profile_changed':False,'provider_called':False,'admitted':False,'dispatched':False},sort_keys=True))
    finally:socket.socket.connect=original_connect
    return 0


if __name__=='__main__':raise SystemExit(main())
