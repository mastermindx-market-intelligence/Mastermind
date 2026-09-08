"""C2 contracts exercised through real collectors, codecs and native boundaries."""
from __future__ import annotations

import copy
import importlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess

import pytest

from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as legacy

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = 'a' * 64


def protocol():
    name = 'integrations.chairman_surfaces.web_sol_census_protocol'
    assert importlib.util.find_spec(name) is not None, 'C2 sibling protocol is not implemented'
    return importlib.import_module(name)


def request(**changes):
    return {'schema': 'mastermind.web_sol_census_request.v1',
            'adapter_instance_id': INSTANCE, 'operation_key': 'c2-fixture',
            'nonce': 'census-fixture-nonce-0001', 'issued_at': '2026-09-08T00:00:00Z',
            'expires_at': '2026-09-08T00:00:10Z', **changes}


def current_request(**changes):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    return request(issued_at=now.isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                   expires_at=(now+timedelta(seconds=10)).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                   **changes)


def snapshot(count=0, unavailable=False):
    # The actual collector runs; only Chrome's external read API is synthetic.
    script = r'''
const core = require('./integrations/chairman_surfaces/web_sol_extension/census_core.js');
const tabs = Array.from({length: Number(process.argv[1])}, (_, i) => ({id:i+1,windowId:1,
 url:'https://chatgpt.com/c/fixture-'+i,status:'complete',discarded:true,frozen:false,
 incognito:false,active:false}));
core.collect({query: async () => {if(process.argv[2]==='true')throw Error('private');return tabs;},
 get:async()=>{throw Error('sleeping tab must not wake');},
 sendMessage:async()=>{throw Error('sleeping tab must not probe');}}, 'a'.repeat(64))
 .then(x=>process.stdout.write(JSON.stringify(x)));
'''
    r = subprocess.run(['node', '-e', script, str(count), str(unavailable).lower()],
                       cwd=ROOT, capture_output=True, text=True, timeout=15, check=True)
    return json.loads(r.stdout)


def receipt(p, s):
    return {'schema': 'mastermind.web_sol_census_receipt.v1', 'adapter_instance_id': INSTANCE,
            'operation_key': 'c2-fixture', 'nonce': 'census-fixture-nonce-0001',
            'status': 'COLLECTED', 'snapshot': p.encode_snapshot(s)}


def test_sibling_request_is_closed_and_does_not_widen_legacy_actions():
    p = protocol()
    assert p.validate_census_request(request()) == request()
    with pytest.raises(legacy.WebSolProtocolError):
        legacy.validate_request(request())
    for change in [{'extra': True}, {'adapter_instance_id': 'a'*63}, {'nonce': True},
                   {'operation_key': 'x y'}, {'expires_at': '2026-09-08T00:00:11Z'},
                   {'issued_at': '2026-09-08T00:00:00Z\n'}, {'nonce': 'x'*129}]:
        with pytest.raises(legacy.WebSolProtocolError):
            p.validate_census_request(request(**change))


@pytest.mark.parametrize('count', [0, 1, 128, 129])
def test_real_collector_lossless_complete_envelope_and_explicit_omission(count):
    p = protocol(); original = snapshot(count); value = receipt(p, original)
    assert p.decode_snapshot(value['snapshot']) == original
    accepted = p.validate_census_receipt(value)
    assert native.read_frame(io.BytesIO(native.encode_frame(accepted))) == value
    assert len(native.encode_frame(value)) - 4 <= 61440
    assert len(original['rows']) == min(count, 128)
    assert original['omitted_tab_count'] == max(count - 128, 0)


def test_unavailable_inventory_is_not_measured_zero_or_forged_empty_success():
    p = protocol(); original = snapshot(unavailable=True)
    accepted = p.validate_census_receipt(receipt(p, original))
    decoded = p.decode_snapshot(accepted['snapshot'])
    assert decoded['initial_tab_count'] is None
    assert decoded['reason'] == 'QUERY_UNAVAILABLE'
    assert p.decode_snapshot(receipt(p, snapshot())['snapshot'])['initial_tab_count'] == 0
    for status in ['COLLECTOR_UNAVAILABLE', 'READ_DEADLINE_EXCEEDED', 'RESULT_TOO_LARGE', 'INVALID_OBSERVATION']:
        value = {**receipt(p, snapshot()), 'status': status, 'snapshot': None}
        assert p.validate_census_receipt(value) == value
        with pytest.raises(legacy.WebSolProtocolError):
            p.validate_census_receipt({**value, 'snapshot': accepted['snapshot']})


def test_c2_worker_preserves_python_unicode_length_and_whitespace_domain():
    p = protocol()
    cases = [request(operation_key=c*256, nonce=c*128) for c in ['a', 'é', '😀', '\ufeff']]
    cases += [request(operation_key='😀'*257), request(nonce='😀'*129),
              request(operation_key=''), request(nonce='x'*15)]
    # Python's exact whitespace set, including C0 separators/NEL absent from JS \s,
    # and BOM above, which JS \s rejects but Python deliberately accepts.
    whitespace = [chr(i) for i in range(0x110000) if chr(i).isspace()]
    for c in whitespace:
        cases += [request(operation_key=c), request(nonce='n'*15+c)]
    expected = []
    for value in cases:
        try:
            assert p.validate_census_request(value) == value
            expected.append(True)
        except legacy.WebSolProtocolError:
            expected.append(False)
    run = subprocess.run(['node', str(ROOT/'tests/web_sol_native_census.test.cjs'), '--validate-requests'],
        input=json.dumps(cases), text=True, capture_output=True, cwd=ROOT, timeout=15, check=True)
    assert json.loads(run.stdout) == expected, 'C2 correlation domain must agree without normalization'
    assert expected[:4] == [True]*4 and not any(expected[4:])


@pytest.mark.parametrize('character', ['é', '😀', '\ufeff'])
def test_c2_maximum_unicode_correlations_round_trip_actual_worker(character):
    p = protocol(); req = current_request(operation_key=character*256, nonce=character*128)
    assert p.validate_census_request(req) == req
    run = subprocess.run(['node', str(ROOT/'tests/web_sol_native_census.test.cjs'), '--fixture'],
        input=json.dumps({'request':req,'count':0}), text=True,
        capture_output=True, cwd=ROOT, timeout=15, check=True)
    value = p.validate_census_receipt(json.loads(run.stdout))
    assert all(value[key] == req[key] for key in p.IDENTITY_FIELDS)
    assert p.decode_snapshot(value['snapshot'])['initial_tab_count'] == 0


@pytest.mark.parametrize('changes', [
    {'reason':'QUERY_UNAVAILABLE', 'inventory_coverage':'UNAVAILABLE'},
    {'reason':'ADAPTER_UNCONFIGURED'}, {'unobserved_added_count':1},
    {'final_tab_count':1}, {'consistency':'UNKNOWN'},
    {'reason':'INVENTORY_CHANGED'},
])
def test_contradictory_receipt_inventory_claims_are_rejected(changes):
    p = protocol(); original = snapshot()
    baseline = receipt(p, original)
    assert p.validate_census_receipt(baseline) == baseline
    # Mutate the actual wire table after encoding, so the receipt decoder itself
    # must refuse the three reported contradictions and adjacent count claims.
    malformed = copy.deepcopy(baseline)
    for key, value in changes.items():
        malformed['snapshot']['header'][p.HEADER_FIELDS.index(key)] = value
    with pytest.raises(legacy.WebSolProtocolError): p.validate_census_receipt(malformed)
    with pytest.raises(legacy.WebSolProtocolError): p.encode_snapshot({**original, **changes})


@pytest.mark.parametrize('mode', ['unavailable','invalid','overflow','final_failure',
    'changed','duplicates','empty','invalid_tab','tab_limit_final_failure'])
def test_legal_partial_inventory_states_round_trip_real_collector(mode):
    script = r'''
const core=require('./integrations/chairman_surfaces/web_sol_extension/census_core.js');
const mode=process.argv[1];let calls=0;
const tab={id:1,windowId:1,url:'https://chatgpt.com/c/one',discarded:true};
const rows=mode==='empty'?[]:mode==='duplicates'?[tab,{...tab,id:2}]:
 mode==='invalid_tab'?[{...tab,id:null}]:mode==='tab_limit_final_failure'
 ?Array.from({length:129},(_,i)=>({...tab,id:i+1})):[tab];
core.collect({query:async()=>{calls++;
 if(mode==='unavailable'||calls===2&&['final_failure','tab_limit_final_failure'].includes(mode))throw Error('fixture');
 if(mode==='invalid')return {};if(mode==='overflow')return Array(4097).fill(tab);
 return mode==='changed'&&calls===2?[tab,{...tab,id:2}]:rows;},
 get:async()=>{throw Error('discarded');},sendMessage:async()=>{throw Error('discarded');}},'a'.repeat(64))
 .then(x=>process.stdout.write(JSON.stringify(x)));
'''
    run = subprocess.run(['node','-e',script,mode],cwd=ROOT,text=True,capture_output=True,timeout=15,check=True)
    p=protocol(); original=json.loads(run.stdout)
    value=receipt(p,original)
    assert p.decode_snapshot(p.validate_census_receipt(value)['snapshot']) == original
    expected={'unavailable':('QUERY_UNAVAILABLE',None,None),'invalid':('INVALID_INVENTORY',None,None),
        'overflow':('INVENTORY_LIMIT',None,None),'final_failure':('FINAL_QUERY_UNAVAILABLE',1,None),
        'changed':('INVENTORY_CHANGED',1,2),'duplicates':('NONE',2,2),'empty':('NONE',0,0),
        'invalid_tab':('INVALID_TAB',1,1),'tab_limit_final_failure':('TAB_LIMIT',129,None)}
    assert tuple(original[k] for k in ['reason','initial_tab_count','final_tab_count']) == expected[mode]


def test_malformed_snapshot_types_counts_and_private_fields_are_rejected():
    p = protocol(); valid = snapshot(1)
    for key, value in [('initial_tab_count', True), ('initial_tab_count', 0),
                       ('omitted_tab_count', 1), ('probed_tab_count', 1),
                       ('adapter_instance_id', 'b'*64), ('reason', 'secret free text')]:
        changed = copy.deepcopy(valid); changed[key] = value
        with pytest.raises(legacy.WebSolProtocolError):
            p.validate_census_receipt(receipt(p, changed))
    for key, value in [('slot', True), ('slot', 2), ('selected_model', 'guessed'),
                       ('document_binding', 'VERIFIED'), ('discarded', 0),
                       ('conversation_fingerprint', 'g'*64), ('duplicate_count', 2),
                       ('observed_at', '2026-09-08T00:00:00Z\n'), ('url', 'private')]:
        changed = copy.deepcopy(valid); changed['rows'][0][key] = value
        with pytest.raises(legacy.WebSolProtocolError):
            p.encode_snapshot(changed)
    table = p.encode_snapshot(valid)
    for changed in [{**table, 'extra': True}, {**table, 'rows': [table['rows'][0][:-1]]},
                    {**table, 'rows': table['rows']*129}]:
        with pytest.raises(legacy.WebSolProtocolError): p.decode_snapshot(changed)


def test_existing_native_byte_boundary_and_duplicate_key_guard_remain_real():
    n = 65536-len(b'{"pad":""}')
    valid = {'pad':'x'*n}
    assert native.read_frame(io.BytesIO(native.encode_frame(valid))) == valid
    with pytest.raises(native.NativeHostError, match='frame_too_large'):
        native.encode_frame({'pad':'x'*(n+1)})
    payload = b'{"schema":"one","schema":"two"}'
    with pytest.raises(native.NativeHostError):
        native.read_frame(io.BytesIO(len(payload).to_bytes(4,'little')+payload))


@pytest.mark.parametrize('mode,count', [('observed',128), ('mixed',5)])
def test_actual_worker_table_mixed_rows_and_maximum_escaped_correlation(mode, count):
    p = protocol()
    req = current_request(operation_key='\x00'*256, nonce='\x00'*128)
    run = subprocess.run(['node', str(ROOT/'tests/web_sol_native_census.test.cjs'), '--fixture'],
        input=json.dumps({'request':req,'count':count,'mode':mode}), text=True,
        capture_output=True, cwd=ROOT, timeout=15, check=True)
    value = p.validate_census_receipt(json.loads(run.stdout)); decoded = p.decode_snapshot(value['snapshot'])
    assert value['operation_key'] == req['operation_key'] and value['nonce'] == req['nonce']
    assert p.encode_snapshot(decoded) == value['snapshot']
    assert len(value['snapshot']['header']) == 20
    assert all(len(row) == 19 for row in value['snapshot']['rows'])
    assert len(native.encode_frame(value))-4 <= 61440
    if mode == 'observed':
        assert decoded['probed_tab_count'] == 128
        assert decoded['probe_coverage'] == 'COMPLETE_IN_SCOPE'
    else:
        assert decoded['consistency'] == 'CHANGED'
        assert decoded['final_tab_count'] == 4
        assert decoded['duplicate_tab_count'] == 1
        assert [row['status'] for row in decoded['rows']] == [
            'OBSERVED','DISCARDED','PROBE_UNAVAILABLE','FROZEN','TARGET_CHANGED']
    assert all(row[field] is None for row in decoded['rows']
               for field in ['selected_model','selected_effort','served_model'])


def test_fieldwise_conservative_legal_payload_bound_includes_full_envelope():
    # Each slot independently takes its longest legal representation; these
    # combinations need not be jointly reachable, so this overbounds real rows.
    p = protocol()
    header = [p.LOCAL_SCHEMA,'CURRENT_PROFILE_NORMAL_CHATGPT_TABS','f'*64,
        '9999-12-31T23:59:59.999Z','9999-12-31T23:59:59.999Z',10000,
        'COMPLETE_IN_SCOPE','STABLE_AT_BOUNDARIES',max(p.REASONS,key=len),
        *([9007199254740991]*10),'COMPLETE_IN_SCOPE']
    row = [128,'f'*64,'LOCATOR_AND_V1_PROBE','UNVERIFIED',max(p.ROW_STATUSES,key=len),
        'NOT_OBSERVED',False,False,False,'VISIBLE',False,False,128,False,
        '9999-12-31T23:59:59.999Z',None,None,None,'UNVERIFIED']
    assert len(header) == 20 and len(row) == 19
    envelope = {**receipt(p,snapshot()),'operation_key':'\x00'*256,'nonce':'\x00'*128,
        'snapshot':{'schema':p.TABLE_SCHEMA,'header':header,'rows':[row]*128}}
    bound = len(native.encode_frame(envelope))-4
    assert bound < 61440, f'conservative complete-envelope upper bound {bound}'


@pytest.mark.parametrize('mutation,case,marker', [
    ('outer','outer expiry','no actual Chrome acquisition after outer expiry'),
    ('slots','popup and native share','shared actual reads stay bounded'),
    ('sender','content script, foreign','Expected values to be strictly equal'),
    ('late','port disconnect during','disconnected port must not receive completion'),
    ('unknown','configured failed query','Expected values to be strictly equal'),
    ('columns','worker fixed columns','literal status slot'),
])
def test_real_guard_removal_fails_same_positive_and_adverse_assertions(mutation, case, marker):
    import os
    argv=['node','--test','--test-reporter=tap','--test-name-pattern='+case,
          str(ROOT/'tests/web_sol_native_census.test.cjs')]
    baseline=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=15,
                            env={k:v for k,v in os.environ.items() if k!='C2_TEST_MUTATION'})
    changed=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=15,
                           env={**os.environ,'C2_TEST_MUTATION':mutation})
    print(json.dumps({'mutation':mutation,'argv':argv,'baseline_exit':baseline.returncode,
          'mutant_exit':changed.returncode,'baseline_stdout':baseline.stdout,
          'baseline_stderr':baseline.stderr,'mutant_stdout':changed.stdout,'mutant_stderr':changed.stderr}))
    assert baseline.returncode==0 and '# pass 1' in baseline.stdout
    assert changed.returncode!=0 and '# fail 1' in changed.stdout
    assert 'AssertionError' in changed.stdout and marker in changed.stdout
    assert 'one exact mutation anchor' not in changed.stdout
    assert 'SyntaxError' not in changed.stdout and 'ReferenceError' not in changed.stdout


def test_repository_gate_runs_complete_native_census_node_suite():
    import os
    run=subprocess.run(['node','--test','--test-reporter=tap',str(ROOT/'tests/web_sol_native_census.test.cjs')],
        cwd=ROOT,capture_output=True,text=True,timeout=20,
        env={k:v for k,v in os.environ.items() if k!='C2_TEST_MUTATION'})
    assert run.returncode==0, run.stdout+run.stderr
    assert '# tests 16\n' in run.stdout and '# pass 16\n' in run.stdout
    assert '# fail 0\n' in run.stdout and '# cancelled 0\n' in run.stdout
    assert '# skipped 0\n' in run.stdout and not run.stderr


def test_real_native_forwarder_admits_and_correlates_census_sibling():
    from datetime import datetime, timedelta, timezone
    p = protocol(); now = datetime.now(timezone.utc)
    req = request(issued_at=now.isoformat(timespec='milliseconds').replace('+00:00','Z'),
                  expires_at=(now+timedelta(seconds=10)).isoformat(timespec='milliseconds').replace('+00:00','Z'))
    value = receipt(p, snapshot()); sent = []
    assert native.forward_request(req, write_chrome=sent.append,
           read_chrome=lambda remaining:value, timeout_seconds=10) == value
    assert sent == [req]
    with pytest.raises(native.ChromeChannelError, match='receipt_identity_mismatch'):
        native.forward_request(req, write_chrome=lambda _:None,
            read_chrome=lambda remaining:{**value,'nonce':'wrong-correlation-00001'}, timeout_seconds=10)


@pytest.mark.parametrize('stage', ['timely', 'handshake', 'write', 'response'])
def test_client_original_start_acquisition_and_total_deadlines(monkeypatch, stage):
    from integrations.chairman_surfaces import web_sol_client as client
    req=current_request(); value=receipt(protocol(),snapshot()); now=[100.0]; writes=[]; closed=[]
    class Reader(io.BytesIO):
        def read(self,n):
            now[0] = 104.7 if n==4 else (110.1 if stage=='response' else 109.9)
            return super().read(n)
    class Writer(io.BytesIO):
        def write(self,data):
            now[0] = 105.1 if stage=='write' else 104.5
            writes.append(bytes(data));return super().write(data)
    reader=Reader(native.encode_frame(value));writer=Writer()
    class Connection:
        def settimeout(self,value): assert 0 < value <= 10
        def connect(self,path): now[0]=101.0
        def makefile(self,mode,buffering=0): return reader if mode=='rb' else writer
        def close(self): closed.append(True)
    def handshake(*args,deadline,**kwargs):
        assert deadline.ends_at==105.0
        now[0]=105.1 if stage=='handshake' else 104.0
    monkeypatch.setattr(client,'_private_socket',lambda path:None)
    monkeypatch.setattr(client.socket,'socket',lambda *args:Connection())
    monkeypatch.setattr(client,'_complete_transport_handshake',handshake)
    def invoke(): return client._exchange_web_sol_socket(req,path=Path('fixture.sock'),
        expected_instance_id=INSTANCE,monotonic=lambda:now[0])
    if stage=='timely': assert invoke()==value
    else:
        with pytest.raises(client.WebSolExtensionError,match='census_unavailable'): invoke()
    assert len(writes)==(0 if stage=='handshake' else 1)
    assert reader.closed and writer.closed and closed==[True]


@pytest.mark.parametrize('stage', ['timely', 'handshake', 'response'])
def test_native_original_start_budget_and_post_await_withholding(monkeypatch, stage):
    req=current_request();value=receipt(protocol(),snapshot());now=[100.0];forwarded=[];replies=[]
    reader=io.BytesIO(native.encode_frame(req))
    class Writer(io.BytesIO):
        def write(self,data): replies.append(bytes(data));return super().write(data)
    writer=Writer()
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def makefile(self,mode,buffering=0):return reader if mode=='rb' else writer
    def handshake(*args,deadline,**kwargs):
        assert deadline.ends_at==105.0;now[0]=105.1 if stage=='handshake' else 104.0
    def read_chrome(stream,remaining,*,deadline,monotonic):
        assert deadline.ends_at==110.0 and remaining==6.0
        now[0]=110.1 if stage=='response' else 109.9
        return value
    monkeypatch.setattr(native,'complete_server_handshake',handshake)
    monkeypatch.setattr(native,'_write_chrome',lambda stream,document,**kwargs:forwarded.append(document))
    monkeypatch.setattr(native,'_read_chrome_with_timeout',read_chrome)
    def invoke():native._serve_client(Connection(),None,None,timeout_seconds=5,
        expected_instance_id=INSTANCE,boot_nonce='boot-fixture-00000001',monotonic=lambda:now[0])
    if stage=='timely':
        invoke();assert native.read_frame(io.BytesIO(b''.join(replies)))==value
    else:
        with pytest.raises(native.NativeHostError,match='frame_read_timeout|census_timeout'):invoke()
        assert not replies,'late completion must never reach client'
    assert len(forwarded)==(0 if stage=='handshake' else 1)
    assert reader.closed and writer.closed


def test_real_native_worker_collector_client_and_cli_vertical(monkeypatch, capsys):
    import os
    import tempfile
    import threading
    import time
    from contextlib import ExitStack
    from integrations.chairman_surfaces import web_sol_client as client
    from integrations.chairman_surfaces import web_sol_instance as instance
    from tests.test_web_sol_fleet_transport import managed_binding
    assert hasattr(client, 'census_via_extension'), 'public C2 binding-only client is missing'
    assert importlib.util.find_spec('scripts.web_sol_census'), 'real C2 CLI is missing'
    cli = importlib.import_module('scripts.web_sol_census')
    root = os.environ.get('MMX_C2_TEST_ROOT', tempfile.gettempdir())
    with tempfile.TemporaryDirectory(prefix='c2-',dir=root) as directory, ExitStack() as stack:
        directory = Path(directory); directory.chmod(0o700)
        first, second = managed_binding(), managed_binding(profile_id='55555555-5555-4555-8555-555555555555',
            binding_id='44444444-4444-4444-8444-444444444444')
        original_path = instance.socket_path
        monkeypatch.setattr(instance, 'socket_path', lambda identity, root=None:
                            original_path(identity, root=directory))
        failures, peers, workers = [], [], []
        for binding, count in [(first,2),(second,1)]:
            identity=instance.adapter_instance_id(binding)
            proc=subprocess.Popen(['node', str(ROOT/'tests/web_sol_native_census.test.cjs'), '--native-pipe',
                    json.dumps({'instance':identity,'count':count})],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,bufsize=0)
            peers.append(proc)
            def serve(proc=proc,identity=identity):
                try: native.run_native_host(proc.stdout,proc.stdin,caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
                        expected_instance_id=identity,socket_root=directory)
                except BaseException as e: failures.append(e)
            worker=threading.Thread(target=serve);workers.append(worker);worker.start()
        try:
            for binding in [first,second]:
                destination=instance.socket_path(instance.adapter_instance_id(binding))
                until=time.monotonic()+5
                while not destination.exists() and time.monotonic()<until:time.sleep(.01)
                assert destination.exists(), ('real host startup failed',failures)
            doc={'schema':'mastermind.surface_bindings.v1','bindings':[first,second]}
            from control_plane import surface_bindings as sb
            doc['schema']=sb.SCHEMA
            bindings=directory/'bindings.json';bindings.write_text(json.dumps(doc));bindings.chmod(0o600)
            results=[]
            for binding in [first,second]:
                assert cli.main(['--bindings',str(bindings),'--binding-id',binding['binding_id'],'--json']) == 0
                results.append(json.loads(capsys.readouterr().out))
            assert [protocol().decode_snapshot(r['snapshot'])['initial_tab_count'] for r in results] == [2,1]
            assert results[0]['adapter_instance_id'] != results[1]['adapter_instance_id']
            assert all(r['status']=='COLLECTED' for r in results)
            assert not failures
        finally:
            for proc in peers:
                proc.stdin.close()
            for worker in workers: worker.join(6)
            for proc in peers:
                if proc.poll() is None:proc.terminate()
                proc.wait(timeout=5);proc.stdout.close();proc.stderr.close()
            assert not any(w.is_alive() for w in workers), 'native fixture worker leaked'
            assert not list(directory.glob('*.sock')), 'native fixture socket leaked'
        # The same consumer after disconnection must replace success with a
        # payload-free unavailable result; there is no saved-snapshot fallback.
        assert cli.main(['--bindings',str(bindings),'--binding-id',first['binding_id'],'--json']) == 2
        assert json.loads(capsys.readouterr().out) == {'status':'UNAVAILABLE','code':'census_unavailable'}
        assert cli.main(['--bindings',str(bindings),'--binding-id','missing','--json']) == 2
        assert json.loads(capsys.readouterr().out) == {'status':'UNAVAILABLE','code':'invalid_binding'}
