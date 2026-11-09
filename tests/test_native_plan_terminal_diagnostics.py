"""Fixed native-plan failure diagnosis; all operations use disposable fixtures."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import shutil
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'ops/native_fabric/provider_plans/terminal_diagnostics'
META = json.loads((COMPONENT / 'component.json').read_text())
PARENT = ROOT / 'ops/native_fabric/quota_continuity/candidate/native_plan_worker.py'


def materialize(destination, raw):
    assert hashlib.sha256(raw).hexdigest() == META['before'], 'fixed parent required'
    patch = COMPONENT / META['patch']
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == META['patch_sha256']
    path = destination / META['member']
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=destination, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=destination, check=True)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == META['after']
    return path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def owner(tmp_path, monkeypatch):
    path = materialize(tmp_path / 'native', PARENT.read_bytes())
    module = load('fixture_native_plan', path)
    outcome = load('fixture_outcome', ROOT / 'ops/native_fabric/quota_continuity/candidate/provider_outcome.py')
    monkeypatch.setitem(sys.modules, 'provider_outcome', outcome)
    appended = []
    monkeypatch.setitem(sys.modules, 'pool_ledger', SimpleNamespace(append=lambda **kw: appended.append(kw) or True))
    state = path.parent / 'state/remote_sub'; state.mkdir(parents=True)
    (path.parent / 'lanes').mkdir()
    run, root, parent = 'fixture-run', 'fixture-private-root', 'fixture-private-parent'
    pool, model = 'byteplus', 'fixture-private-model'
    packet = state / (run + '.request.packet'); packet.write_bytes(b'inert private sentinel packet')
    request = dict(schema='mastermind.fabric_request_artifact.v1', run_id=run, root_id=root,
                   parent_run_id=parent, task_class='fix_build', cwd=str(tmp_path),
                   packet_sha256=outcome.digest(packet.read_bytes()))
    request_path = state / (run + '.request.json'); outcome.write_new(request_path, request)
    launch = dict(schema='mastermind.fabric_request_launch.v1', run_id=run, root_id=root,
                  parent_run_id=parent, state='LAUNCH_ATTEMPT_RESERVED',
                  request_sha256=outcome.digest(request_path.read_bytes()),
                  packet_sha256=request['packet_sha256'], route=dict(POOL=pool, MODEL=model))
    launch_path = state / (run + '.request-launch.json'); outcome.write_new(launch_path, launch)
    env = dict(POOL_RUN_ID=run, POOL_ORCHESTRATOR_ID=root, POOL_PARENT_RUN_ID=parent,
               POOL_TASK_CLASS='fix_build')
    monkeypatch.setattr(module.os, 'environ', env)
    output = path.parent / 'lanes' / (run + '.remote.stdout')
    log = state / (run + '.log'); log.touch(mode=0o600)
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=76))
    def call():
        return module.local_controller(pool, model, str(tmp_path), str(packet), str(output), str(log), 'inert-no-exec')
    return SimpleNamespace(m=module, outcome=outcome, path=path, state=state, run=run,
        root=root, parent=parent, pool=pool, model=model, packet=packet, request=request_path,
        launch=launch_path, env=env, log=log, output=output, appended=appended, call=call,
        witness=state/(run+'.local-terminal-diagnostic.json'))


def test_fixed_parent_and_postimage_no_foreign_parent(tmp_path):
    materialize(tmp_path/'valid', PARENT.read_bytes())
    with pytest.raises(AssertionError, match='fixed parent'):
        materialize(tmp_path/'foreign', PARENT.read_bytes()+b'\n# changed\n')


def test_actual_refusal_predicates_and_returns_are_unchanged(owner):
    old = ast.parse(PARENT.read_bytes()); new = ast.parse(owner.path.read_bytes())
    def get(tree):
        return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_local_terminal_facts')
    after = get(new)
    for n in ast.walk(after):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'TerminalQualificationRefused':
            n.func.id = 'ValueError'
    assert ast.dump(get(old), include_attributes=False) == ast.dump(after, include_attributes=False)


def test_other_existing_worker_definitions_are_exact(owner):
    old={n.name:n for n in ast.parse(PARENT.read_bytes()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    new={n.name:n for n in ast.parse(owner.path.read_bytes()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    changed={'original_request','local_controller','_local_terminal_facts'}
    for name,node in old.items():
        if name not in changed:
            assert ast.dump(node,include_attributes=False)==ast.dump(new[name],include_attributes=False),name


def test_old_controller_loses_reason_but_new_retains_bound_unknown(owner, monkeypatch):
    r = owner
    oldext = r.path.parent.parent / 'oldext'
    (oldext/'state/remote_sub').mkdir(parents=True)
    (oldext/'lanes').mkdir()
    oldpath=oldext/'native_plan_worker.py';oldpath.write_bytes(PARENT.read_bytes())
    for p in (r.request,r.launch,r.packet):
        shutil.copyfile(p,oldext/'state/remote_sub'/p.name)
    oldlog=oldext/'state/remote_sub'/(r.run+'.log');oldlog.touch(mode=0o600)
    old=load('fixture_old_worker',oldpath)
    # Execute the genuine preimage with the same valid original and inert subprocess.
    cwd=json.loads(r.request.read_text())['cwd']
    assert old.local_controller(r.pool,r.model,cwd,str(r.packet),
        str(oldext/'lanes'/(r.run+'.remote.stdout')),str(oldlog),'inert-no-exec')==76
    assert 'phase=terminal_qualification' in oldlog.read_text()
    assert ' reason=' not in oldlog.read_text()
    assert not (oldext/'state/remote_sub'/(r.run+'.local-terminal-diagnostic.json')).exists()
    assert r.call() == 76
    event = r.log.read_text()
    assert 'reason=PLAN_LOCAL_EFFECT_UNCERTAIN diagnostic=retained' in event
    row = json.loads(r.witness.read_text())
    assert row['state'] == 'EFFECT_UNKNOWN' and row['qualification'] == 'NOT_RECONCILED'
    assert row['terminal_authorized'] is row['replay_allowed'] is False
    assert r.appended == []
    for private in (r.root, r.parent, r.model, str(r.packet), 'inert private sentinel packet'):
        assert private not in json.dumps(row) and private not in event
    anchor = r.m._terminal_diagnostic_anchor(r.pool, r.model, json.loads(r.request.read_text()),
                                            r.request.read_bytes(), r.launch.read_bytes())
    expected = r.outcome.digest(json.dumps(anchor, sort_keys=True, separators=(',', ':')).encode())
    assert row['binding_sha256'] == expected


@pytest.mark.parametrize('fault', ['stale-request', 'cross-root', 'source-drift'])
def test_changed_binding_withholds_diagnostic_and_stays_unknown(owner, monkeypatch, fault):
    r = owner
    def returned(*a, **kw):
        if fault == 'stale-request': r.request.write_text('{}')
        elif fault == 'cross-root': kw['env']['POOL_ORCHESTRATOR_ID'] = 'different-root'
        else: r.path.write_text(r.path.read_text()+'\n# changed after original validation\n')
        return SimpleNamespace(returncode=76)
    monkeypatch.setattr(r.m.subprocess, 'run', returned)
    assert r.call() == 76 and r.appended == [] and not r.witness.exists()
    assert 'diagnostic=unavailable' in r.log.read_text()


@pytest.mark.parametrize('fault,reason', [('physical','PLAN_PHYSICAL_CUSTODY_UNSETTLED'),
    ('process','PLAN_PROCESS_RETURN_AMBIGUOUS'),('quota','PLAN_PROVIDER_CUSTODY_UNSETTLED'),
    ('cross-provider-root','PLAN_PROVIDER_RETURN_BINDING')])
def test_real_terminal_guard_failures_never_become_terminal(owner, monkeypatch, fault, reason, tmp_path):
    r=owner
    monkeypatch.setattr(r.m.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    if fault == 'physical':
        active=r.path.parent/'active';active.mkdir()
        key='plan-'+hashlib.sha256((r.root+'\n'+r.run+'\n'+r.pool).encode()).hexdigest()[:40]
        (active/key).touch()
    else:
        value=dict(root_id=r.root,provider=r.pool,model=r.model,source_generation=hashlib.sha256(r.path.read_bytes()).hexdigest(),
                   lease_id='private-lease',account='private-account',host='m2')
        if fault == 'cross-provider-root':value['root_id']='different-root'
        raw=json.dumps(value).encode();(r.state/(r.run+'.provider.json')).write_bytes(raw)
        (r.state/(r.run+'.process.jsonl')).write_text('{}\n{}\n' if fault=='process' else '{}\n')
        monkeypatch.setattr(r.outcome,'validate_receipt',lambda *a:None)
        (r.state/(r.run+'.task-cli-started.json')).write_text(json.dumps(dict(
            schema='mastermind.task_cli_start_reserved.v1',run_id=r.run,root_id=r.root,pool=r.pool,model=r.model,
            request_sha256=r.outcome.digest(r.request.read_bytes()),lease_id=value['lease_id'],account=value['account'])))
        if fault == 'quota':
            db=tmp_path/'disposable.db'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE leases(id TEXT,orchestrator_id TEXT,pool TEXT,model TEXT,account TEXT,host TEXT,state TEXT,quota_outcome_sha256 TEXT)')
                conn.execute('INSERT INTO leases VALUES(?,?,?,?,?,?,?,?)',('private-lease',r.root,r.pool,r.model,'private-account','m2','held',r.outcome.digest(raw)))
            monkeypatch.setitem(sys.modules,'lease_broker',SimpleNamespace(DEFAULT_DB=db))
    assert r.call()==76 and r.appended==[]
    row=json.loads(r.witness.read_text());assert row['reason']==reason
    assert row['state']=='EFFECT_UNKNOWN' and row['terminal_authorized'] is False
    assert 'private-lease' not in r.witness.read_text() and 'private-account' not in r.witness.read_text()


def test_malformed_receipt_is_closed_without_raw_error_or_body(owner,monkeypatch):
    r=owner
    monkeypatch.setattr(r.m.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0))
    (r.state/(r.run+'.provider.json')).write_text('private invalid json sentinel')
    assert r.call()==76 and r.appended==[]
    assert json.loads(r.witness.read_text())['reason']=='PLAN_TERMINAL_RECEIPT_MALFORMED'
    assert 'private invalid json sentinel' not in r.log.read_text()+r.witness.read_text()


@pytest.mark.parametrize('exc',[ValueError('PLAN_LOCAL_EFFECT_UNCERTAIN'),RuntimeError('private message'),
    PermissionError('private/path'),KeyError('private identity')])
def test_untrusted_exceptions_never_copy_messages(owner,exc):
    reason=owner.m._terminal_failure_reason(exc)
    assert reason.startswith('PLAN_TERMINAL_')
    assert 'private' not in reason and '/' not in reason


def test_forged_or_malformed_typed_reason_remains_generic(owner):
    for value in ([], {}, 'PRIVATE_UNREVIEWED_CODE'):
        assert owner.m._terminal_failure_reason(owner.m.TerminalQualificationRefused(value)) == 'PLAN_TERMINAL_QUALIFICATION_UNAVAILABLE'


def test_original_request_default_contract_unchanged(owner):
    r=owner
    cwd=json.loads(r.request.read_text())['cwd']
    assert r.m.original_request(r.pool,r.model,cwd,str(r.packet),r.env)==(r.run,r.state)
    assert not r.witness.exists() and r.appended==[]


def test_foreign_reason_cannot_create_a_diagnostic(owner):
    r=owner
    anchor=r.m._terminal_diagnostic_anchor(r.pool,r.model,json.loads(r.request.read_text()),
        r.request.read_bytes(),r.launch.read_bytes())
    for reason in ([], 'PRIVATE_REASON'):
        assert r.m._retain_terminal_diagnostic(r.pool,r.model,r.run,r.state,r.env,anchor,reason) is False
    assert not r.witness.exists()


def test_unknown_witness_is_once_only_and_not_overwritten(owner):
    r=owner
    assert r.call()==76;before=r.witness.read_bytes();log=r.log.read_bytes()
    assert r.call()==76 and r.witness.read_bytes()==before and r.log.read_bytes()==log
    assert r.appended==[]


def test_diagnostic_write_failure_preserves_unknown(owner,monkeypatch):
    r=owner
    monkeypatch.setattr(r.outcome,'write_new',lambda *a,**kw: (_ for _ in ()).throw(OSError('private disk detail')))
    assert r.call()==76 and r.appended==[] and not r.witness.exists()
    assert 'diagnostic=unavailable' in r.log.read_text() and 'private disk detail' not in r.log.read_text()


def test_late_drift_never_reports_retained_or_terminal(owner,monkeypatch):
    r=owner;real=r.outcome.write_new
    def write(path,value):
        real(path,value);r.request.write_text('{}')
    monkeypatch.setattr(r.outcome,'write_new',write)
    assert r.call()==76 and r.appended==[]
    assert 'diagnostic=unavailable' in r.log.read_text()
    row=json.loads(r.witness.read_text());assert row['qualification']=='NOT_RECONCILED'
    assert row['state']=='EFFECT_UNKNOWN' and row['terminal_authorized'] is False


def test_preexisting_qualified_success_path_does_not_write_diagnostic(owner,monkeypatch):
    r=owner
    monkeypatch.setattr(r.m.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0))
    monkeypatch.setattr(r.m,'_local_terminal_facts',lambda *a,**kw:('ok','provider_success',{}))
    assert r.call()==0 and len(r.appended)==1 and not r.witness.exists()
    assert 'DONE rc=0 signal=ok' in r.log.read_text()
