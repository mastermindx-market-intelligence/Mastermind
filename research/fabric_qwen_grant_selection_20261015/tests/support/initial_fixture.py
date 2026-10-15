"""Initial-request terminal contract. Synthetic fixtures only: no provider,
credential, real `codex` or production path; TMPDIR/HOME/PATH/CODEX config are
private per test and QWEN_EXEC_SLOTTED=1 keeps the slot pool out of it."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

EXT = Path(__file__).resolve().parents[1]
MARKER = "TERMINAL RESPONSE CONTRACT"
THREAD = "fixture-thread"

# pick/env/model/stream shapes match the sibling account/signal suites, so the
# existing fences stay applicable to this file's wrapper copy.
KEY_STUB = '''import json,os,sys
from pathlib import Path
with Path(os.environ['EVENTS']).open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
cmd=sys.argv[1]
if cmd=='pick':print(os.environ.get('SELECTED_ACCOUNT','FixtureAccount'))
elif cmd=='env':print("export BAILIAN_API_KEY='SYNTHETIC_FIXTURE_ONLY'")
elif cmd=='model':print(sys.argv[2])
elif cmd=='stream':
 data=sys.stdin.read();Path(sys.argv[2]).write_text('fixture-thread');Path(sys.argv[3]).write_text(data);print(data)
elif cmd=='seconds_until_offpeak':print('1')
elif cmd=='next_usable_in':print('0')
'''
LEDGER_STUB = '''import json,os,sys
from pathlib import Path
with Path(os.environ['EVENTS']).open('a') as f:f.write(json.dumps(['ledger']+sys.argv[1:])+'\\n')
'''

# Fake Codex: closes ONLY when it actually received the contract, so a missing
# or rerouted contract cannot pass by luck.
CODEX_STUB = '''import glob,json,os,sys
from pathlib import Path
MARKER='TERMINAL RESPONSE CONTRACT'
PROGRESS=('Reviewed the packet in full and it reads as a complete ordinary '
          'review. No further changes needed.')
argv=sys.argv[1:]
stdin=sys.stdin.read()
packet=Path(os.environ['PACKET']).read_text()
calls=Path(os.environ['CALLS'])
probe=[]
for hit in sorted(glob.glob(str(Path(os.environ['TMPDIR'])/'qwen_exec.*'/'initial_prompt.md'))):
    p=Path(hit)
    probe.append({'path':str(p),
      'file_mode':oct(p.stat().st_mode & 0o777)[-3:],
      'dir_mode':oct(p.parent.stat().st_mode & 0o777)[-3:],
      'is_the_packet':os.path.realpath(str(p))==os.path.realpath(os.environ['PACKET']),
      'starts_with_packet':p.read_text().startswith(packet)})
with calls.open('a') as fh:
    fh.write(json.dumps({'mode':'resume' if 'resume' in argv else 'new',
      'argv':argv,'packet_len':len(packet),'stdin_len':len(stdin),
      'stdin_head_is_packet':stdin.startswith(packet),
      'marker_count':stdin.count(MARKER),
      'account':os.environ.get('POOL_ACCOUNT',''),
      'thread_arg':argv[2] if 'resume' in argv else '','probe':probe})+'\\n')
first=sum(1 for _ in calls.open())==1
behavior=os.environ['SYNTH_BEHAVIOR']
def complete():
    print('STATUS: COMPLETE')
    print('REVIEW: the packet is sound.')
    print('VERDICT')
def blocked():
    print('STATUS: BLOCKED')
    print('REVIEW: cannot close without the outer verdict owner.')
    print('VERDICT')
if behavior=='contract_gated':
    if first and MARKER not in stdin: print(PROGRESS)
    else: complete()
elif behavior=='blocked_gated':
    if first and MARKER not in stdin: print(PROGRESS)
    else: blocked()
elif behavior=='progress_then_complete':
    if first: print(PROGRESS)
    else: complete()
elif behavior=='never_status':
    print(PROGRESS)
'''

LONG_PACKET = ('TASK: review the packet below and return findings within the '
               'output limit.\n' + 'REVIEW BODY fixture line\n' * 4000 +
               'VERDICT TOKEN REQUIRED: VERDICT\n')


def run_fixture(tmp_path, behavior='contract_gated',
                packet=LONG_PACKET, selected='FixtureAccount',
                max_continues='', complexity=''):
    ext = tmp_path / 'ext'
    ext.mkdir()
    shutil.copy2(EXT / 'qwen_exec.sh', ext / 'qwen_exec.sh')
    shutil.copy2(EXT / 'codex_usage.py', ext / 'codex_usage.py')
    projection = ext / 'studio_mcp_projection.sh'
    projection.write_text('#!/bin/sh\nexit 0\n')
    projection.chmod(0o700)
    (ext / 'bailian_keys.py').write_text(KEY_STUB)
    (ext / 'pool_ledger.py').write_text(LEDGER_STUB)
    home = tmp_path / 'userhome'
    conf = home / 'lanes/codex_bailian/config.toml'
    conf.parent.mkdir(parents=True)
    conf.write_text('model = "qwen3.8-flash"\n')
    conf.chmod(0o600)
    binary = tmp_path / 'bin'
    binary.mkdir()
    (binary / 'python3').symlink_to(sys.executable)
    cli = binary / 'codex'
    cli.write_text('#!%s\n' % sys.executable + CODEX_STUB)
    cli.chmod(0o700)
    prompt = tmp_path / 'prompt'
    prompt.write_text(packet)
    prompt.chmod(0o644)
    env = {'PATH': str(binary) + ':/usr/bin:/bin', 'HOME': str(home),
           'TMPDIR': str(tmp_path), 'EVENTS': str(tmp_path / 'events'),
           'CALLS': str(tmp_path / 'calls'), 'PACKET': str(prompt),
           'SYNTH_BEHAVIOR': behavior,
           'QWEN_EXEC_SLOTTED': '1', 'LANE_LEASED': '1',
           'POOL_ACCOUNT': 'FixtureAccount', 'SELECTED_ACCOUNT': selected,
           'POOL_LEASE_ID': '', 'QWEN_EXEC_KEY_WAIT': '0',
           'QWEN_EXEC_MAX_CONTINUES': max_continues,
           'POOL_TASK_COMPLEXITY': complexity, 'PYTHONWARNINGS': 'ignore'}
    result = subprocess.run(
        ['/bin/bash', str(ext / 'qwen_exec.sh'), str(tmp_path),
         'qwen3.8-flash', str(prompt)],
        env=env, capture_output=True, text=True, timeout=30)
    calls, events = [], []
    for name, sink in (('calls', calls), ('events', events)):
        path = tmp_path / name
        if path.exists():
            sink.extend(json.loads(line) for line in path.read_text().splitlines())
    assert 'SYNTHETIC_FIXTURE_ONLY' not in result.stdout + result.stderr
    return result, events, calls, prompt


def test_initial_request_carries_contract_and_closes_in_one_paid_call(tmp_path):
    result, events, calls, prompt = run_fixture(tmp_path)
    assert result.returncode == 0, result.stderr
    # Exactly one CLI call: no AUTO_CONTINUE, no second paid return.
    assert [c['mode'] for c in calls] == ['new']
    assert 'AUTO_CONTINUE' not in result.stderr
    assert 'STATUS: COMPLETE' in result.stdout
    assert len([e for e in events if e[0] == 'pick']) == 1
    assert any(e[0] == 'ledger' and '--rc' in e and e[e.index('--rc') + 1] == '0'
               for e in events)
    assert any(e[:2] == ['release', 'FixtureAccount'] for e in events)
    assert 'done key=FixtureAccount thread=%s rc=0' % THREAD in result.stderr
    first = calls[0]
    # The contract reached the INITIAL request, exactly once.
    assert first['marker_count'] == 1
    assert first['account'] == 'FixtureAccount'
    # Packet verbatim and first: the contract is only appended, so the task,
    # verdict token and output bounds are not rewritten.
    assert first['stdin_head_is_packet'] is True
    assert first['stdin_len'] > first['packet_len']
    # Prompt never reaches argv.
    assert first['argv'][-1] == '-'
    joined = ' '.join(first['argv'])
    assert 'REVIEW BODY fixture line' not in joined
    assert str(prompt) not in joined
    # Caller packet untouched.
    assert prompt.read_text() == LONG_PACKET
    assert MARKER not in prompt.read_text()
    # Private temp dir, tightened modes, never the caller's file.
    assert len(first['probe']) == 1
    probe = first['probe'][0]
    assert probe['file_mode'] == '600' and probe['dir_mode'] == '700'
    assert probe['is_the_packet'] is False
    assert probe['starts_with_packet'] is True
    assert probe['path'] != str(prompt)
    # Private temp cleanup retained.
    assert list(tmp_path.glob('qwen_exec.*')) == []



def test_blocked_first_response_is_terminal(tmp_path):
    result, events, calls, _ = run_fixture(tmp_path, behavior='blocked_gated')
    assert result.returncode == 0, result.stderr
    assert [c['mode'] for c in calls] == ['new']
    assert 'STATUS: BLOCKED' in result.stdout
    assert 'AUTO_CONTINUE' not in result.stderr
    assert len([e for e in events if e[0] == 'pick']) == 1


def test_genuine_progress_still_resumes_the_same_thread_once(tmp_path):
    """Genuinely unfinished work keeps the same-account continuation path."""
    result, events, calls, _ = run_fixture(
        tmp_path, behavior='progress_then_complete')
    assert result.returncode == 0, result.stderr
    assert [c['mode'] for c in calls] == ['new', 'resume']
    assert 'AUTO_CONTINUE 1/2' in result.stderr
    assert 'AUTO_CONTINUE_EXHAUSTED' not in result.stderr
    assert 'STATUS: COMPLETE' in result.stdout
    # Same thread, same granted account, one key: no rotation or re-lease.
    assert calls[1]['thread_arg'] == THREAD
    assert calls[1]['account'] == 'FixtureAccount'
    assert len([e for e in events if e[0] == 'pick']) == 1
    # The resume prompt is untouched and still demands the close.
    assert 'STATUS: COMPLETE or STATUS: BLOCKED' in calls[1]['argv'][-1]


def test_non_status_prose_is_never_accepted_and_still_exhausts(tmp_path):
    """Guard not weakened: status-less prose never passes as completion."""
    result, events, calls, _ = run_fixture(
        tmp_path, behavior='never_status', max_continues='1')
    assert result.returncode == 77, result.stderr
    assert [c['mode'] for c in calls] == ['new', 'resume']
    assert calls[0]['marker_count'] == 1
    assert 'STATUS: COMPLETE' not in result.stdout
    assert 'STATUS: BLOCKED' not in result.stdout
    assert 'AUTO_CONTINUE_EXHAUSTED rc=77 reason=terminal_status_missing' in result.stderr
    # A progress note is no provider limit: no cooldown, one account.
    assert not any(e[0] == 'cooldown' for e in events)
    assert len([e for e in events if e[0] == 'pick']) == 1


def test_outer_account_fence_still_refuses_before_any_call(tmp_path):
    """No way to substitute an account or re-lease through the contract."""
    result, events, calls, _ = run_fixture(tmp_path, selected='Intruder')
    assert result.returncode == 75, result.stderr
    assert 'OUTER_LEASE_ACCOUNT_MISMATCH' in result.stderr
    assert 'NO_USABLE_KEY' in result.stderr
    assert calls == []
    assert not any(e[0] in ('env', 'codex') for e in events)


def test_complexity_budget_still_applies_after_the_initial_contract(tmp_path):
    result, events, calls, _ = run_fixture(
        tmp_path, behavior='never_status', complexity='C2_COMPLEX_BOUNDED')
    assert result.returncode == 77, result.stderr
    assert [c['mode'] for c in calls] == ['new', 'resume', 'resume', 'resume', 'resume']
    assert 'AUTO_CONTINUE 4/4' in result.stderr
