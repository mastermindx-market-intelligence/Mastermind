#!/usr/bin/env python3
"""CPU scope route and unchanged legacy CLI tests, no provider dispatch."""
from pathlib import Path
import importlib.util
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

STAGE=Path(__file__).resolve().parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location('scoped_fabric_task',STAGE/'fabric_task.py')
controller=importlib.util.module_from_spec(spec);sys.modules[spec.name]=controller;spec.loader.exec_module(controller)
captures=[]
def fake_dispatch(argv,env=None):
    assert argv[:2]==['/bin/bash',str(controller.HERE/'remote_sub.sh')]
    assert Path(argv[4]).is_file()
    captures.append({'argv':argv[:], 'payload':Path(argv[4]).read_bytes(), 'env':env})
    return SimpleNamespace(returncode=0)

with tempfile.TemporaryDirectory(prefix='mmx-cpu-scope-route-') as temp:
    controller.HERE=Path(temp)
    def run(quota=100,root='original-root',parent='original-parent'):
        return controller.request('cpu-scope-new','mechanical',cwd='~',packet=None,
            stdin_bytes=b'OBJECTIVE: fixture no provider',
            root_id=root,parent_run_id=parent,task_complexity='C0_MECHANICAL',
            cpu_scope_percent=quota)
    with patch.object(controller.pick,'format_pick',
        return_value='POOL=glm MODEL=glm-5.3 HOST=ubuntu2 MODE=glm') as pick,\
        patch.object(controller.pick,'launch_policy',return_value={'allowed':True}),\
        patch.object(controller.subprocess,'run',side_effect=fake_dispatch):
        assert run()==0
        assert len(captures)==1
        assert captures[-1]['argv'][-2:]==['--cpu-scope-quota','100']
        assert captures[-1]['env']['POOL_PARENT_RUN_ID']=='original-parent'
        assert captures[-1]['env']['POOL_ORCHESTRATOR_ID']=='original-root'
        assert pick.call_args.kwargs['required_platforms']==['linux']
        assert captures[-1]['payload'].startswith(b'OBJECTIVE:')
        assert run(quota=None)==0
        assert len(captures)==2
        assert '--cpu-scope-quota' not in captures[-1]['argv']
        for invalid in (0, 50, 150, 300, 500, True, '100'):
            try:run(quota=invalid)
            except controller.FabricTaskError as ex:
                assert str(ex)=='CPU_SCOPE_REQUEST_UNQUALIFIED'
            else:raise AssertionError('QUOTA_ACCEPTED '+str(invalid))
        for bad in ({'root':None},{'parent':None}):
            try:run(**bad)
            except controller.FabricTaskError as ex:
                assert str(ex)=='CPU_SCOPE_REQUEST_UNQUALIFIED'
            else:raise AssertionError('PARENT_OR_ROOT_ACCEPTED')
        assert len(captures)==2
        pick.return_value='POOL=glm MODEL=glm-5.3 HOST=ubuntu1 MODE=glm'
        try:run()
        except controller.FabricTaskError as ex:
            assert str(ex)=='CPU_SCOPE_HOST_NOT_QUALIFIED'
        else:raise AssertionError('UNQUALIFIED_HOST_ACCEPTED')
        pick.return_value='POOL=grok MODEL=grok-4.6 HOST=ubuntu2 MODE=grok'
        try:run()
        except controller.FabricTaskError as ex:
            assert str(ex)=='CPU_SCOPE_MODE_NOT_QUALIFIED'
        else:raise AssertionError('UNQUALIFIED_PROVIDER_ACCEPTED')
        assert len(captures)==2
print('CPU_SCOPE_CONTROLLER_ROUTE_PASS',len(captures),
      'no provider, no original controller ledger or run reservation written')
