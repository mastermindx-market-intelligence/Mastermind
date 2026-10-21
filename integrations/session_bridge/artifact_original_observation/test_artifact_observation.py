"""Inert original-parent admission and remote read-contract falsifiers."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest
import artifact_delivery as delivery
import artifact_production as production
import artifact_reader as reader
import fabric_task
import run_observation as remote
import run_observation_delivery as observation

REAL_VALIDATOR_SELECTOR = delivery.original_validator_context


def digest(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def original(tmp_path, monkeypatch):
    root, parent, rid = 'original-root', 'assigning-parent', 'ordinary-artifact-run'
    state = tmp_path/'state/remote_sub'
    state.mkdir(parents=True)
    # Public code hashes only. Validator seam parses the real artifact contract.
    manifest = {name:digest(name.encode()) for name in remote.ARTIFACT_SUPPORT_FILES}
    support = digest(reader.canonical({'schema':'remote-support-code.v1','files':manifest}))
    packet = production.encode_packet('bounded input', root=root, parent=parent,
        run_id=rid, names=['patch.diff'], support_digest=support).encode()
    binding = dict(schema='mastermind.fabric_launch_binding.v1', run_id=rid,
        root=root, parent=parent, host='ubuntu0', mode='glm', pool='glm',
        requested_model='glm-5.3-flash', account='account-one', lease_id='a'*12,
        packet_sha256=digest(packet), support_digest=support,
        acquire_response_sha256='b'*64, source='controller_original_acquire_return',
        phase='PRE_LAUNCH')
    events=['RUN_RESERVED explicit=1','LEASE_OK pool=glm',
        f'SCP packet={rid}.packet.original support=executor-surface',
        f'SUPPORT_VERSION_READY digest={support} policy='+('c'*64),
        'LAUNCH_BINDING '+json.dumps(binding),
        f'LAUNCH stdout=lanes_{rid}.stdout rc_file=ext/lanes_{rid}.rc cwd=~',
        'LAUNCH_ATTEMPT attempt=1','POLL_PENDING poll=1']
    def log_bytes():
        return ''.join(f'2026-10-16T00:00Z [remote_sub id={rid} host=ubuntu0] {e}\n'
                       for e in events).encode()
    log = state/(rid+'.log'); log.write_bytes(log_bytes())
    packet_path=state/(rid+'.packet.original');packet_path.write_bytes(packet)
    (state/(rid+'.support.json')).write_bytes(reader.canonical(manifest))
    (tmp_path/'hosts.json').write_text(json.dumps({'ubuntu0':{'ssh_alias':'ubuntu0','allowed_modes':['glm']}}))
    (tmp_path/'run_observation.py').write_bytes(Path(remote.__file__).read_bytes())
    lease={'id':'a'*12,'orchestrator_id':root,'host':'ubuntu0','pool':'glm',
           'account':'account-one','model':'glm-5.3-flash','state':'active'}
    monkeypatch.setattr(delivery,'HERE',tmp_path)
    monkeypatch.setattr(fabric_task,'HERE',tmp_path)
    monkeypatch.setattr(delivery,'local_file',lambda path,limit=1048576: Path(path).read_bytes())
    monkeypatch.setattr(delivery,'original_validator_context',lambda _:production)
    monkeypatch.setattr(delivery,'retained_lease',lambda *a,**k:lease)
    monkeypatch.setattr(delivery,'assert_capsule_family',lambda _:None)
    monkeypatch.setenv('CODEX_THREAD_ID',parent)
    monkeypatch.setenv('POOL_ORCHESTRATOR_ID',root)
    def forbidden(*a,**k):
        pytest.fail('qualification performed transport or destination mutation')
    monkeypatch.setattr(delivery,'transport',forbidden)
    monkeypatch.setattr(delivery,'reserve_destination',forbidden)
    return dict(root=root,parent=parent,rid=rid,state=state,packet=packet,
        packet_path=packet_path,manifest=manifest,support=support,binding=binding,
        events=events,log=log,log_bytes=log_bytes,lease=lease,home=tmp_path)


def request(o):
    return observation.request_for(o['rid'],o['root'],original_parent=o['parent'])


def test_general_original_parent_without_per_run_allowlist(original):
    o=original; req=request(o)
    assert o['rid'] not in observation.SCOPES
    assert req['kind']=='ordinary_artifact' and req['parent']==o['parent']
    assert req['observe_pid'] is False
    evidence=observation.qualify(req)
    assert evidence['account_binding']=='retained_original_broker_row'
    assert 'lease_id' not in req and 'account' not in req
    assert req['artifact']['packet_sha256']==digest(o['packet'])


def test_current_producer_uses_incumbent_default_validator(original,monkeypatch):
    # The real selector returns None when the installed producer matches the
    # support manifest. Only historical generations return a context object.
    monkeypatch.setattr(delivery,'original_validator_context',lambda _:None)
    o=original
    req=request(o)
    assert req['artifact']['contract']==production.parse_packet(o['packet'].decode())


def test_current_producer_real_selector_contract(original,monkeypatch):
    o=original
    for module in (production,reader):
        path=Path(module.__file__)
        raw=path.read_bytes()
        (o['home']/path.name).write_bytes(raw)
        o['manifest'][path.name]=digest(raw)
    support=digest(reader.canonical({'schema':'remote-support-code.v1','files':o['manifest']}))
    packet=production.encode_packet('bounded input',root=o['root'],parent=o['parent'],
        run_id=o['rid'],names=['patch.diff'],support_digest=support).encode()
    o['packet_path'].write_bytes(packet)
    (o['state']/(o['rid']+'.support.json')).write_bytes(reader.canonical(o['manifest']))
    o['binding'].update(packet_sha256=digest(packet),support_digest=support)
    o['events'][3]=f'SUPPORT_VERSION_READY digest={support} policy='+('c'*64)
    o['events'][4]='LAUNCH_BINDING '+json.dumps(o['binding'])
    o['log'].write_bytes(o['log_bytes']())
    monkeypatch.setattr(delivery,'original_validator_context',REAL_VALIDATOR_SELECTOR)
    assert REAL_VALIDATOR_SELECTOR(o['manifest']) is None
    assert request(o)['artifact']['contract']==production.parse_packet(packet.decode())


def test_legacy_unknown_scope_remains_closed(original):
    with pytest.raises(observation.ObservationScopeNotAdmitted):
        observation.request_for(original['rid'],original['root'])


def test_poll_append_does_not_change_source_identity(original):
    o=original; req=request(o); before=observation.qualify(req)
    o['events'].append('POLL_PENDING poll=2');o['log'].write_bytes(o['log_bytes']())
    assert observation.qualify(req)==before


@pytest.mark.parametrize('mutation',['writable','hardlink','incomplete'])
def test_original_log_custody_rejected(original,mutation):
    o=original
    if mutation=='writable':o['log'].chmod(0o666)
    elif mutation=='hardlink':os.link(o['log'],o['state']/'second-link')
    else:o['log'].write_bytes(o['log'].read_bytes()[:-1])
    with pytest.raises(ValueError):request(o)


@pytest.mark.parametrize('mutation',[
    'root','parent','inherited_root','missing_parent','packet','plain_packet',
    'support','host','duplicate_launch','repeat_attempt','refusal','effect_unknown',
    'foreign_line','terminal','wrong_packet_path','lease_root','lease_host',
    'lease_account','lease_model','lease_pool','lease_missing',
])
def test_mismatch_refuses_before_destination_or_transport(original,monkeypatch,mutation):
    o=original
    if mutation=='root':o['root']='foreign-root'
    elif mutation=='parent':monkeypatch.setenv('CODEX_THREAD_ID','foreign-parent')
    elif mutation=='inherited_root':monkeypatch.setenv('POOL_ORCHESTRATOR_ID','foreign-root')
    elif mutation=='missing_parent':monkeypatch.delenv('CODEX_THREAD_ID')
    elif mutation in ('packet','plain_packet'):
        o['packet_path'].write_bytes(b'plain' if mutation=='plain_packet' else o['packet']+b'changed')
    elif mutation=='support':
        (o['state']/(o['rid']+'.support.json')).write_text('{"../../secret":"'+('d'*64)+'"}')
    elif mutation=='host':
        (o['home']/'hosts.json').write_text('{"ubuntu0":{"ssh_alias":"bad alias","allowed_modes":["glm"]}}')
    elif mutation=='duplicate_launch':o['events'].append(o['events'][5])
    elif mutation=='repeat_attempt':o['events'].append('LAUNCH_ATTEMPT attempt=2')
    elif mutation=='refusal':o['events'].append('PERMISSION_REFUSED')
    elif mutation=='effect_unknown':o['events'].append('EFFECT_UNKNOWN')
    elif mutation=='foreign_line':o['log'].write_bytes(o['log'].read_bytes()+b'foreign log\n')
    elif mutation=='terminal':o['events'].append('REMOTE_DONE rc=0')
    elif mutation=='wrong_packet_path':o['events'][2]='SCP packet=../../secret support=executor-surface'
    elif mutation=='lease_missing':monkeypatch.setattr(delivery,'retained_lease',lambda *a,**k:None)
    elif mutation.startswith('lease_'):
        key={'lease_root':'orchestrator_id','lease_host':'host','lease_account':'account',
             'lease_model':'model','lease_pool':'pool'}[mutation]
        o['lease'][key]='foreign'
    if mutation in {'duplicate_launch','repeat_attempt','refusal','effect_unknown','terminal','wrong_packet_path'}:
        o['log'].write_bytes(o['log_bytes']())
    with pytest.raises((ValueError,observation.ObservationScopeNotAdmitted)):
        request(o)


def test_known_historical_scope_cannot_be_reinterpreted(original):
    rid=next(iter(observation.SCOPES))
    with pytest.raises(observation.ObservationScopeNotAdmitted):
        observation.artifact_snapshot(rid,observation.SCOPES[rid]['root'])
    assert observation.request_for(rid,observation.SCOPES[rid]['root']).get('kind') is None


class PacketReader:
    def __init__(self,packet,rid):self.packet,self.rid,self.reads=packet,rid,[]
    def read(self,parts,limit,**kwargs):
        self.reads.append(parts)
        assert parts==('lanes','tmp',self.rid+'.txt')
        return self.packet,None


def test_remote_packet_binding_is_checked_without_stdout_read(original):
    o=original;req=request(o);r=PacketReader(o['packet'],o['rid'])
    remote.artifact_packet(r,o['rid'],o['support'],req['artifact'])
    assert r.reads==[('lanes','tmp',o['rid']+'.txt')]


@pytest.mark.parametrize('fault',[None,'manifest','code','manifest_changed'])
def test_exact_remote_support_closure(original,fault):
    o=original; files=dict(o['manifest']); data={'schema':'remote-support-code.v1',
        'files':files,'digest':o['support']}
    class CodeReader:
        def __init__(self):self.manifest_reads=0
        def read(self,parts,limit,**kw):
            assert parts[:3]==('lanes','support-releases',o['support'])
            if parts[-1]=='RELEASE.json':
                assert kw=={'mode':0o444};self.manifest_reads+=1
                value=dict(data)
                if fault=='manifest' or fault=='manifest_changed' and self.manifest_reads==2:
                    value['files']={**files,'outside.py':'0'*64}
                return reader.canonical(value),None
            assert parts[3]=='ext' and parts[-1] in files and kw=={'mode':0o555}
            return (b'changed' if fault=='code' else parts[-1].encode()),None
    if fault is None:
        result=remote.support(CodeReader(),o['support'],expected_files=files)
        assert result['verified_code_files']==31
        assert result['running_process_source_identity_proven'] is False
    else:
        with pytest.raises(remote.Invalid):
            remote.support(CodeReader(),o['support'],expected_files=files)


@pytest.mark.parametrize('mutation',['packet','root','parent','support','arbitrary_file','arbitrary_artifact','pid'])
def test_remote_negative_contracts(original,mutation):
    o=original;req=request(o);a=req['artifact'];packet=o['packet']
    if mutation=='packet':packet+=b'changed'
    elif mutation in ('root','parent'):a['contract'][mutation]='foreign'
    elif mutation=='support':a['contract']['support_digest']='d'*64
    elif mutation=='arbitrary_file':a['support_files']['../../secret']='d'*64
    elif mutation=='arbitrary_artifact':a['contract']['names']=['../../secret']
    if mutation=='pid':
        with pytest.raises(remote.Invalid,match='pid_probe'):
            remote.observe(o['rid'],o['support'],observe_pid=True,artifact=a)
    else:
        with pytest.raises(remote.Invalid):
            remote.artifact_packet(PacketReader(packet,o['rid']),o['rid'],o['support'],a)


def test_embedded_observer_uses_qualified_packet_and_no_pid(original):
    o=original;req=request(o)
    code=observation.code_for_request(req,expected_hash=digest((o['home']/'run_observation.py').read_bytes()))
    compile(code,'embedded-observer','exec')
    assert 'observe_pid=False,artifact=req["artifact"]' in code
    with pytest.raises(ValueError,match='embedded_source_mismatch'):
        observation.code_for_request(req,expected_hash='0'*64)


def test_requalify_rejects_request_or_source_change(original):
    o=original;req=request(o);req['artifact']['contract']['parent']='foreign'
    with pytest.raises(ValueError):observation.qualify(req)


def test_metadata_response_preserves_unknowns_and_validates_file_count(original):
    o=original;req=request(o)
    rows={name:{'status':'absent','reason':'missing_at_observation'}
          for name in ('marker','returncode','stdout','process_receipt')}
    rows['support']={'status':'observed','digest':o['support'],'verified_code_files':31,
        'verification':'manifest_and_fixed_code_hashes','running_process_source_identity_proven':False,
        'release_links_verified':False}
    report={'schema':'mastermind.run_observation.v1','run_id':o['rid'],
        'expected_support_digest':o['support'],'status':'observed','observations':rows,
        'limits':observation.LIMITS,'observed_at':'2026-10-16T00:00:00+00:00'}
    env={'schema':req['schema'],'request_sha256':digest(reader.canonical(req)),'report':report}
    assert observation.validate_response(reader.canonical(env),req)==report
    rows['support']['verified_code_files']=24
    with pytest.raises(ValueError,match='support_shape'):
        observation.validate_response(reader.canonical(env),req)


def test_adapter_forwards_explicit_parent_without_reinterpreting_legacy(original,monkeypatch):
    calls=[]
    class Result:returncode=0
    monkeypatch.setattr(fabric_task.subprocess,'run',lambda argv:(calls.append(argv) or Result()))
    args=['observe-run',original['rid'],'--root',original['root'],'--destination','/inert/destination']
    assert fabric_task.main(args+['--parent',original['parent']])==0
    assert calls[-1][-2:]==['--parent',original['parent']]
    assert fabric_task.main(args)==0 and '--parent' not in calls[-1]


def test_broker_snapshot_error_is_bounded_refusal_before_effect(original,monkeypatch,capsys):
    def broken(*a,**kw):raise sqlite3.DatabaseError('inert broken snapshot')
    monkeypatch.setattr(delivery,'retained_lease',broken)
    o=original
    assert observation.main([o['rid'],'--root',o['root'],'--parent',o['parent'],
        '--destination','/inert/not-created'])==75
    value=json.loads(capsys.readouterr().out)
    assert value=={'state':'REFUSED','reason':'original_run_observation_unconfirmed'}


def test_permission_denial_stops_observation_without_alternate_read(original,monkeypatch):
    o=original;req=request(o);calls=[]
    class Denied:
        def __init__(self,*a,**k):
            calls.append('reader');raise PermissionError(13,'denied')
    monkeypatch.setattr(remote,'Reader',Denied)
    report=remote.observe(o['rid'],o['support'],artifact=req['artifact'])
    assert report['status']=='unavailable' and report['reason']=='os_permission_denied'
    assert report['request_stopped'] is True and calls==['reader']
    envelope={'schema':req['schema'],'request_sha256':digest(reader.canonical(req)),'report':report}
    assert observation.validate_response(reader.canonical(envelope),req)==report


def test_one_broker_snapshot_per_qualification(original,monkeypatch):
    o=original;req=request(o);calls=[]
    monkeypatch.setattr(delivery,'retained_lease',lambda *a,**k:(calls.append(a) or o['lease']))
    observation.qualify(req)
    assert len(calls)==1


def test_remote_and_local_report_limits_match(original,monkeypatch):
    class Denied:
        def __init__(self,*a,**k):raise PermissionError(13,'inert refusal')
    monkeypatch.setattr(remote,'Reader',Denied)
    o=original
    assert remote.observe(o['rid'],o['support'])['limits']==observation.LIMITS
    for name in ('SUPPORT_METADATA_LIMITS','SUPPORT_METADATA_RUN','SUPPORT_METADATA_MAX_COMPONENTS'):
        assert getattr(remote,name)==getattr(observation,name)


def test_maximum_valid_contract_fits_fixed_transport(original):
    o=original;req=request(o);contract=req['artifact']['contract']
    for key in ('root','parent','run_id'):
        contract[key]='r'*128;req[key]=contract[key]
    req['host']='h'*128
    contract['names']=[str(i)+'n'*127 for i in range(8)]
    production.validate_contract(contract)
    assert len(reader.canonical(req))<=8192
