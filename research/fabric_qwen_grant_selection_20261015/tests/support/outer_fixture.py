import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

EXT=Path(__file__).resolve().parents[1]
KEY_STUB='''import json,os,sys
from pathlib import Path
log=Path(os.environ['EVENTS'])
with log.open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
cmd=sys.argv[1]
if cmd=='pick':print(os.environ['SELECTED_ACCOUNT'])
elif cmd=='env':print("export BAILIAN_API_KEY='SYNTHETIC_FIXTURE_ONLY'")
elif cmd=='model':print(sys.argv[2])
elif cmd=='stream':
 data=sys.stdin.read();Path(sys.argv[2]).write_text('fixture-thread');Path(sys.argv[3]).write_text(data);print(data)
elif cmd=='seconds_until_offpeak':print('1')
elif cmd=='next_usable_in':print('0')
'''
CODEX_STUB='''import os,sys,json
from pathlib import Path
is_resume = 'resume' in sys.argv
with Path(os.environ['EVENTS']).open('a') as f:
    f.write(json.dumps(['codex',os.environ.get('POOL_ACCOUNT'),'resume' if is_resume else 'new'])+'\\n')
# Confirm Qwen catalog and flag scope without contacting a provider.
overrides=[sys.argv[i+1] for i in range(len(sys.argv)-1) if sys.argv[i]=='-c'
           and sys.argv[i+1].startswith('model_catalog_json=')]
if overrides:
    catalog_path=Path(json.loads(overrides[0].split('=',1)[1]))
    if not catalog_path.is_file():
        sys.exit(91)
    model=json.loads(catalog_path.read_text())['models'][0]
    with Path(os.environ['EVENTS']).open('a') as f:
        f.write(json.dumps(['catalog',model['slug'],model['context_window'],
                            model['default_reasoning_level'],
                            str(catalog_path),len(overrides)])+'\\n')
sys.stdin.read()
if os.environ.get('SYNTH_NATIVE_USAGE')=='1':
    p=Path(os.environ['CODEX_HOME'])/'sessions/fixture.jsonl'
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a') as f:
        f.write(json.dumps({'type':'session_meta','payload':{'id':'only-this-run'}})+'\\n')
        f.write(json.dumps({'type':'event_msg','payload':{'type':'token_count','info':{
            'total_token_usage':{'input_tokens':120,'cached_input_tokens':15,'output_tokens':22,'total_tokens':142}}}})+'\\n')
if os.environ.get('CODEX_FAIL')=='1':print('HTTP 429 rate limit');sys.exit(1)
if os.environ.get('CODEX_PROGRESS')=='1':
    if is_resume and os.environ.get('CODEX_RESUME_NEVER')!='1':
        print('STATUS: COMPLETE')
        print('RESULT: finished after resume')
    else:
        print('Still working on the fixture')
else:
    print('STATUS: COMPLETE')
    print('RESULT: fixture complete')
'''


def run_fixture(tmp_path,account='Ryan',selected='Ryan',leased='1',failed=False,
                progress=False,resume_never=False,complexity='',max_continues='',usage=False):
    ext=tmp_path/'ext';ext.mkdir()
    shutil.copy2(EXT/'qwen_exec.sh',ext/'qwen_exec.sh')
    shutil.copy2(EXT/'codex_usage.py',ext/'codex_usage.py')
    fake_home=tmp_path/'userhome'
    conf=fake_home/'lanes/codex_bailian/config.toml'
    conf.parent.mkdir(parents=True)
    conf.write_text('model = "qwen3.8-flash"\n')
    conf.chmod(0o600)
    projection=ext/'studio_mcp_projection.sh'
    projection.write_text('#!/bin/bash\nexit 0\n')
    projection.chmod(0o700)
    (ext/'bailian_keys.py').write_text(KEY_STUB)
    (ext/'pool_ledger.py').write_text('pass\n')
    binary=tmp_path/'bin';binary.mkdir()
    (binary/'python3').symlink_to(sys.executable)
    cli=binary/'codex';cli.write_text(f'#!{sys.executable}\n'+CODEX_STUB);cli.chmod(0o700)
    prompt=tmp_path/'prompt';prompt.write_text('fixture')
    events=tmp_path/'events'
    env={**os.environ,'HOME':str(fake_home),'PATH':str(binary)+':/usr/bin:/bin','EVENTS':str(events),'QWEN_EXEC_SLOTTED':'1','LANE_LEASED':leased,'POOL_ACCOUNT':account,'SELECTED_ACCOUNT':selected,'CODEX_FAIL':'1' if failed else '0','CODEX_PROGRESS':'1' if progress else '0','CODEX_RESUME_NEVER':'1' if resume_never else '0','POOL_TASK_COMPLEXITY':complexity,'QWEN_EXEC_MAX_CONTINUES':max_continues,'QWEN_EXEC_KEY_WAIT':'0','TMPDIR':str(tmp_path),'POOL_LEASE_ID':''}
    if usage:
        env['SYNTH_NATIVE_USAGE']='1'
        env['POOL_USAGE_RUN_ID']='qwen-test-run'
        env['POOL_USAGE_FILE']=str(tmp_path/'qwen-test-run.usage.json')
    result=subprocess.run(['bash',str(ext/'qwen_exec.sh'),str(tmp_path),'qwen3.8-flash',str(prompt)],env=env,capture_output=True,text=True,timeout=10)
    data=[json.loads(l) for l in events.read_text().splitlines()] if events.exists() else []
    assert 'SYNTHETIC_FIXTURE_ONLY' not in result.stdout+result.stderr
    return result,data


def test_remote_mismatch_releases_candidate_before_key_export(tmp_path):
    r,e=run_fixture(tmp_path,selected='Chris')
    assert r.returncode==75,r.stderr
    assert 'OUTER_LEASE_ACCOUNT_MISMATCH' in r.stderr
    assert not any(x[0] in ('env','codex','next_usable_in') for x in e)
    assert any(x[:2]==['release','Chris'] for x in e)
    assert len([x for x in e if x[0]=='pick'])==1


def test_remote_exact_account_succeeds(tmp_path):
    r,e=run_fixture(tmp_path)
    assert r.returncode==0,r.stderr
    assert ['env','Ryan'] in e
    assert any(x[:2]==['codex','Ryan'] for x in e)
    assert any(x[:2]==['release','Ryan'] for x in e)

@pytest.mark.parametrize('account',['',"Ryan';touch BAD",'Ryan Chris'])
def test_remote_missing_or_invalid_grant_refuses_before_key_access(tmp_path,account):
    r,e=run_fixture(tmp_path,account=account)
    assert r.returncode==78
    assert 'OUTER_LEASE_ACCOUNT_REQUIRED' in r.stderr
    assert e==[]


def test_remote_limit_does_not_rotate_or_repeat(tmp_path):
    r,e=run_fixture(tmp_path,failed=True)
    assert r.returncode==1,r.stderr
    assert len([x for x in e if x[0]=='codex'])==1
    assert len([x for x in e if x[0]=='pick'])==1


def test_nonleased_account_preference_still_allows_existing_fallback(tmp_path):
    r,e=run_fixture(tmp_path,selected='Chris',leased='0')
    assert r.returncode==0,r.stderr
    assert ['env','Chris'] in e


def test_nonleased_existing_failover_budget_remains(tmp_path):
    r,e=run_fixture(tmp_path,leased='0',failed=True)
    assert r.returncode==1,r.stderr
    assert len([x for x in e if x[0]=='codex'])==3


def test_success_progress_resumes_same_qwen_thread_until_status(tmp_path):
    r,e=run_fixture(tmp_path,progress=True)
    assert r.returncode==0,r.stderr
    calls=[x for x in e if x[0]=='codex']
    assert len(calls)==2
    assert calls[0][2]=='new'
    assert calls[1][2]=='resume'
    assert 'AUTO_CONTINUE 1/2' in r.stderr
    assert 'STATUS: COMPLETE' in r.stdout
    assert 'AUTO_CONTINUE_EXHAUSTED' not in r.stderr


def test_qwen_c2_gets_four_bounded_resumes_then_exhausts(tmp_path):
    r,e=run_fixture(
        tmp_path,progress=True,resume_never=True,
        complexity='C2_COMPLEX_BOUNDED',
    )
    assert r.returncode==77,r.stderr
    calls=[x for x in e if x[0]=='codex']
    assert len(calls)==5
    assert [x[2] for x in calls]==['new','resume','resume','resume','resume']
    assert 'AUTO_CONTINUE 4/4' in r.stderr
    assert 'AUTO_CONTINUE_EXHAUSTED rc=77 reason=terminal_status_missing' in r.stderr


def test_qwen_explicit_continue_override_tightens_c3(tmp_path):
    r,e=run_fixture(
        tmp_path,progress=True,resume_never=True,
        complexity='C3_FRONTIER_JUDGMENT',max_continues='1',
    )
    assert r.returncode==77,r.stderr
    assert len([x for x in e if x[0]=='codex'])==2
    assert 'AUTO_CONTINUE 1/1' in r.stderr


def test_qwen_continue_override_is_capped_at_twelve(tmp_path):
    r,e=run_fixture(
        tmp_path,progress=True,resume_never=True,max_continues='999',
    )
    assert r.returncode==77,r.stderr
    assert len([x for x in e if x[0]=='codex'])==13
    assert 'AUTO_CONTINUE 12/12' in r.stderr



def test_remote_usage_is_only_native_per_run(tmp_path):
    r, events=run_fixture(tmp_path,usage=True)
    assert r.returncode==0,r.stderr
    usage=json.loads((tmp_path/'qwen-test-run.usage.json').read_text())
    assert usage['schema']=='mastermind.codex_usage.v2'
    assert usage['status']=='observed'
    assert usage['source']=='codex_native_session'
    assert usage['run_id']=='qwen-test-run'
    assert usage['session_ids']==['only-this-run']
    assert (usage['input_tokens'],usage['cached_tokens'],usage['output_tokens'],usage['total_tokens'])==(120,15,22,142)
    assert usage['native_compaction_records']==0
    assert not (tmp_path/'userhome/lanes/codex_bailian/sessions').exists()

def test_official_qwen_catalog_is_ephemeral_scoped_and_reused_on_resume(tmp_path):
    r,e=run_fixture(tmp_path,progress=True)
    assert r.returncode==0,r.stderr
    entries=[row for row in e if row[0]=='catalog']
    assert len(entries)==2
    assert all(row[1:4]==['qwen3.8-flash',983616,'xhigh'] for row in entries)
    assert entries[0][4]==entries[1][4]
    assert not Path(entries[0][4]).exists()
    assert all(row[5]==1 for row in entries)
    assert not (tmp_path/'userhome/lanes/codex_bailian/qwen-model-catalog.json').exists()
