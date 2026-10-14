#!/usr/bin/env python3
"""Offline controller request routing and original invocation contract."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

STAGE=Path(__file__).resolve().parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location('staged_fabric_task',STAGE/'fabric_task.py')
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
commit='a'*40
captures=[]
def fake_spawn(argv,env=None,**kw):
    assert argv[0:2]==['/bin/bash',str(STAGE/'remote_sub.sh')]
    assert Path(argv[4]).is_file()
    captures.append({'argv':argv[:],'packet':Path(argv[4]).read_text(),'env':env})
    return SimpleNamespace(returncode=0)
def call(**kwargs):
    return mod.request('sparse-new-test','mechanical',cwd='~/lanes/repos/macro',
          packet=None,stdin_bytes=b'OBJECTIVE: new clean sparse worker',root_id='root-1',
          parent_run_id='parent-1',task_complexity='C0_MECHANICAL',**kwargs)
with patch.object(mod.pick,'format_pick',return_value='POOL=glm MODEL=glm-5.3 HOST=ubuntu2 MODE=glm') as router, \
     patch.object(mod.pick,'launch_policy',return_value={'allowed':True}),\
     patch.object(mod.subprocess,'run',side_effect=fake_spawn):
    assert call(new_macro_worktree=commit)==0
    assert len(captures)==1
    assert captures[-1]['argv'][-2:]==['--new-macro-worktree',commit]
    assert captures[-1]['argv'][5]=='~/lanes/repos/macro'
    assert captures[-1]['packet'].startswith('OBJECTIVE:')
    assert captures[-1]['env']['POOL_PARENT_RUN_ID']=='parent-1'
    assert captures[-1]['env']['POOL_ORCHESTRATOR_ID']=='root-1'
    assert router.call_args.kwargs['required_platforms']==['linux']
    assert call(new_macro_worktree=None)==0
    assert len(captures)==2
    assert '--new-macro-worktree' not in captures[-1]['argv']
    for kwargs in [
        {'new_macro_worktree':'badscope'},
        {'new_macro_worktree':commit,'cwd':'~'},
        {'new_macro_worktree':commit,'root_id':None},
        {'new_macro_worktree':commit,'parent_run_id':None},
        {'new_macro_worktree':commit,'artifact_names':['x.txt']},
    ]:
        args={'new_macro_worktree':commit,'cwd':'~/lanes/repos/macro',
              'root_id':'root-1','parent_run_id':'parent-1','artifact_names':None}
        args.update(kwargs)
        try:
            mod.request('sparse-new-test','mechanical',
              packet=None,stdin_bytes=b'safe',task_complexity='C0_MECHANICAL',**args)
        except mod.FabricTaskError as ex:
            assert str(ex)=='FABRIC_NEW_MACRO_WORKTREE_SCOPE_REFUSED',str(ex)
        else:raise AssertionError('INVALID_REQUEST_NOT_REFUSED '+str(kwargs))
    assert len(captures)==2
    router.return_value='POOL=grok MODEL=grok-4.6 HOST=ubuntu2 MODE=grok'
    try:call(new_macro_worktree=commit)
    except mod.FabricTaskError as ex:
        assert str(ex)=='FABRIC_SPARSE_MODE_NOT_YET_QUALIFIED'
    else:raise AssertionError('UNQUALIFIED_MODEL_NOT_REFUSED')
    router.return_value='POOL=glm MODEL=glm-5.3 HOST=m2 MODE=glm'
    try:call(new_macro_worktree=commit)
    except mod.FabricTaskError as ex:
        assert str(ex)=='FABRIC_SPARSE_HOST_REFUSED'
    else:raise AssertionError('UNQUALIFIED_HOST_NOT_REFUSED')
print('CONTROLLER_TYPED_REQUEST_FIXTURES_PASS',len(captures),'mocked no-provider spawns')
