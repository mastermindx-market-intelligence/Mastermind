"""Prospective response framing; synthetic Codex events, no provider or credentials."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'integrations/session_bridge/qwen_terminal_output'
SOURCE = PACKAGE / ('base' if os.environ.get('QWEN_FRAMING_BASE') else 'candidate')


def module(legacy=False):
    path = PACKAGE/'base/legacy_stream.py' if legacy or os.environ.get('QWEN_FRAMING_BASE') else PACKAGE/'final_response_stream.py'
    spec = importlib.util.spec_from_file_location('inert_keys', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def message(text, **extra):
    return {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': text, **extra}}


def events(*items):
    return [{'type': 'thread.started', 'thread_id': 'inert-thread'},
            {'type': 'turn.started'}, *items, {'type': 'turn.completed'}]


def project(tmp_path, rows):
    raw = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    out = io.StringIO()
    mod = module()
    fn = (getattr(mod, 'stream_final_jsonl', None) or mod.stream_jsonl)
    fn(io.StringIO(raw), out, str(tmp_path / 'thread'), str(tmp_path / 'raw'))
    assert (tmp_path / 'raw').read_text() == raw
    assert (tmp_path / 'thread').read_text() == 'inert-thread\n'
    return out.getvalue()


def test_large_tool_transcript_does_not_inflate_final_response(tmp_path):
    final = 'STATUS: COMPLETE\nREQUEST_CHANGES\n' + 'bounded finding\n' * 300
    rows = events(
        {'type': 'item.completed', 'item': {'type': 'error', 'message': 'metadata warning'}},
        message('I am checking the packet.'),
        {'type': 'item.completed', 'item': {'type': 'command_execution',
            'command': 'python inert_fixture.py', 'aggregated_output': 'tool transcript\n' * 8000,
            'exit_code': 0}}, message(final))
    assert project(tmp_path, rows) == final


def test_typed_tool_output_cannot_supply_terminal_answer(tmp_path):
    rows = events({'type': 'item.completed', 'item': {'type': 'command_execution',
        'aggregated_output': 'STATUS: COMPLETE\nPASS\n', 'exit_code': 0}})
    with pytest.raises(ValueError, match='UNCONFIRMED'):
        project(tmp_path, rows)


@pytest.mark.parametrize('bad', ['truncated', 'failed', 'error', 'duplicate_end',
                                 'post_end_message', 'invalid_item', 'invalid_text', 'non_object'])
def test_incomplete_or_ambiguous_stream_never_publishes(tmp_path, bad):
    rows = events(message('STATUS: COMPLETE\nPASS'))
    if bad == 'truncated': rows.pop()
    elif bad == 'failed': rows.insert(-1, {'type': 'turn.failed', 'error': {'message': 'failed'}})
    elif bad == 'error': rows.insert(-1, {'type': 'error', 'message': 'HTTP 429 rate limit'})
    elif bad == 'duplicate_end': rows.append({'type': 'turn.completed'})
    elif bad == 'post_end_message': rows.append(message('later'))
    elif bad == 'invalid_item': rows.insert(-1, {'type': 'item.completed', 'item': []})
    elif bad == 'invalid_text': rows.insert(-1, message({'untrusted': 'text'}))
    elif bad == 'non_object': rows.insert(-1, ['not an event'])
    out = io.StringIO(); mod = module(); fn = (getattr(mod, 'stream_final_jsonl', None) or mod.stream_jsonl)
    with pytest.raises((ValueError, AttributeError), match='UNCONFIRMED|rstrip'):
        fn(io.StringIO(''.join(json.dumps(r)+'\n' for r in rows)), out,
           str(tmp_path/'thread'), str(tmp_path/'raw'))
    assert out.getvalue() == ''


def test_unstructured_input_is_not_published(tmp_path):
    mod = module(); fn = (getattr(mod, 'stream_final_jsonl', None) or mod.stream_jsonl); out = io.StringIO()
    with pytest.raises(ValueError, match='UNCONFIRMED'):
        fn(io.StringIO('STATUS: COMPLETE\n'), out, str(tmp_path/'thread'), str(tmp_path/'raw'))
    assert out.getvalue() == ''
    assert (tmp_path/'raw').read_text() == 'STATUS: COMPLETE\n'


def test_response_is_not_truncated_to_make_a_bound_pass(tmp_path):
    final = 'STATUS: COMPLETE\n' + '原文 ' * 5000
    assert project(tmp_path, events(message(final))) == final + '\n'


def test_explicit_commentary_after_final_is_not_the_result(tmp_path):
    assert project(tmp_path, events(message('STATUS: BLOCKED\nExact blocker'),
            message('Transport commentary', phase='commentary'))) == 'STATUS: BLOCKED\nExact blocker\n'


def test_legacy_stream_mode_keeps_its_original_transcript_contract(tmp_path):
    mod = module(legacy=True); out = io.StringIO()
    mod.stream_jsonl(io.StringIO(json.dumps({'type': 'item.completed', 'item': {
        'type': 'command_execution', 'command': 'echo fixture',
        'aggregated_output': 'fixture', 'exit_code': 0}})+'\n'), out, '', None)
    assert out.getvalue() == '$ echo fixture\nfixture\n(exit 0)\n'


KEY_STUB = '''import sys
from pathlib import Path
cmd=sys.argv[1]
if cmd=='pick':print('FixtureAccount')
elif cmd=='env':print("export BAILIAN_API_KEY='SYNTHETIC_FIXTURE_ONLY'")
elif cmd=='model':print(sys.argv[2])
elif cmd=='stream':
 import framing
 sys.exit(framing.cmd_stream(sys.argv[2:]))
elif cmd in ('seconds_until_offpeak','next_usable_in'):print(0)
'''

CODEX_STUB = '''import json,os,sys
from pathlib import Path
sys.stdin.read()
p=Path(os.environ['CALLS']);n=int(p.read_text())+1 if p.exists() else 1;p.write_text(str(n))
def emit(row):print(json.dumps(row))
emit({'type':'thread.started','thread_id':'inert-thread'})
emit({'type':'turn.started'})
emit({'type':'item.completed','item':{'type':'command_execution','command':'inert check',
 'aggregated_output':'tool output '*10000,'exit_code':0}})
mode=os.environ['CASE']
text='Progress only' if mode=='continue' and n==1 else 'STATUS: COMPLETE\\nVERIFIED'
emit({'type':'item.completed','item':{'type':'agent_message','text':text}})
if mode!='truncated':emit({'type':'turn.completed'})
sys.exit(7 if mode=='provider_failure' else 0)
'''


@pytest.mark.parametrize('case,rc,calls', [('normal',0,1),('continue',0,2),
                                          ('truncated',77,1),('provider_failure',7,1)])
def test_wrapper_publishes_only_once_after_final_success(tmp_path, case, rc, calls):
    ext=tmp_path/'ext';ext.mkdir();shutil.copyfile(SOURCE/'qwen_exec.sh',ext/'qwen_exec.sh')
    shutil.copyfile(PACKAGE/'base/legacy_stream.py',ext/'framing.py')
    (ext/'bailian_keys.py').write_text(KEY_STUB);(ext/'pool_ledger.py').write_text('pass\n')
    projection=ext/'studio_mcp_projection.sh';projection.write_text('#!/bin/sh\nexit 0\n');projection.chmod(0o700)
    binary=tmp_path/'bin';binary.mkdir();(binary/'python3').symlink_to(sys.executable)
    codex=binary/'codex';codex.write_text('#!'+sys.executable+'\n'+CODEX_STUB);codex.chmod(0o700)
    prompt=tmp_path/'prompt';prompt.write_text('Inert bounded task')
    conf=tmp_path/'lanes/codex_bailian/config.toml';conf.parent.mkdir(parents=True);conf.write_text('model="qwen3.8-flash"\n')
    env={'PATH':str(binary)+':/usr/bin:/bin','HOME':str(tmp_path),'TMPDIR':str(tmp_path),
         'QWEN_EXEC_SLOTTED':'1','LANE_LEASED':'1','POOL_ACCOUNT':'FixtureAccount',
         'POOL_LEASE_ID':'','QWEN_EXEC_KEY_WAIT':'0','CALLS':str(tmp_path/'calls'),'CASE':case}
    result=subprocess.run(['/bin/bash',str(ext/'qwen_exec.sh'),str(tmp_path),'qwen3.8-flash',str(prompt)],
                          env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode == rc,result.stderr
    assert int((tmp_path/'calls').read_text()) == calls
    assert result.stdout == ('STATUS: COMPLETE\nVERIFIED\n' if rc==0 else '')
    assert 'SYNTHETIC_FIXTURE_ONLY' not in result.stdout+result.stderr


def test_embedded_formatter_is_exact_scanned_python_source():
    wrapper=(PACKAGE/'candidate/qwen_exec.sh').read_text()
    start="cat > \"$FINAL_STREAM_FILE\" <<'QWEN_FINAL_RESPONSE_STREAM_PY' || exit 78\n"
    embedded=wrapper.split(start,1)[1].split('QWEN_FINAL_RESPONSE_STREAM_PY\n',1)[0]
    assert embedded == (PACKAGE/'final_response_stream.py').read_text()
    assert 'chmod 600 "$FINAL_STREAM_FILE"' in wrapper
