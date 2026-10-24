"""Provider-free account-selection method tests after the #1365 expiry patch."""
from __future__ import annotations
import ast
import itertools
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import pytest

BUNDLE = Path(__file__).resolve().parents[1] / 'ops/native_fabric/routing_audit_20261013/account_balance'
BEFORE = os.environ.get('FABRIC_ACCOUNT_TEST_PREIMAGE') == '1'

def load_source():
    text = (BUNDLE/'reference.py.txt').read_text()
    if BEFORE:
        return text
    with tempfile.TemporaryDirectory(prefix='fabric-account-method-') as name:
        root = Path(name); (root/'ext').mkdir()
        target = root/'ext/lease_broker.py'; target.write_text(text)
        result = subprocess.run(['git','apply',str(BUNDLE/'normalized_account_balance.patch')],
                                cwd=root,text=True,capture_output=True)
        assert result.returncode == 0, result.stderr
        return target.read_text()

SOURCE=load_source()
ns={'sqlite3':sqlite3,'Any':Any,'Dict':Dict,'List':List,'Optional':Optional,'Tuple':Tuple}
exec(compile(SOURCE,'<account-method-source>','exec'),ns)

@pytest.fixture
def rig():
    db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE leases(pool TEXT, account TEXT, model TEXT, state TEXT, granted_at REAL)')
    owner=ns['Broker'](); accounts=[]; urgent={}; observed=[]
    owner.provider_name=lambda p: 'bailian' if p=='qwen' else p
    owner.grantable_accounts=lambda _: list(accounts)
    owner.account_model_cap=lambda p,a,m: a.get('model_cap')
    def count(pool, account, model=None):
        query="SELECT COUNT(*) FROM leases WHERE pool=? AND account=? AND state IN ('held','rented')"
        args=[owner.provider_name(pool),account]
        if model is not None: query+=' AND model=?'; args.append(model)
        return db.execute(query,args).fetchone()[0]
    owner._account_held=lambda c,p,a: count(p,a)
    owner._account_model_held=lambda c,p,a,m: count(p,a,m)
    def expiry(names):
        observed.append(set(names))
        return {name:value for name,value in urgent.items() if name in names}
    owner._fresh_glm_expiring_accounts=expiry
    yield owner,db,accounts,urgent,observed
    db.close()

def account(rig,name,cap,held=0,model_cap=None,model_held=None,pool='minimax'):
    owner,db,accounts,_,_=rig
    row={'name':name,'_eff_cap':cap,'model_cap':model_cap}; accounts.append(row)
    for i in range(held):
        model='target' if model_held is None or i<model_held else 'other'
        db.execute('INSERT INTO leases VALUES(?,?,?,?,?)',(owner.provider_name(pool),name,model,'held',float(i)))
    return row

def choose(rig,pool='minimax',preferred=None,override=None):
    owner,db,*_=rig
    before=list(db.iterdump())
    answer=owner._pick_account(db,pool,preferred,model='target',grantable_override=override)
    assert list(db.iterdump())==before, 'selection wrote to the broker database'
    return answer

@pytest.mark.parametrize('pool',['minimax','glm','bailian','grok','cursor'])
def test_choose_normalized_headroom_not_lowest_job_count(rig,pool):
    account(rig,'small',2,held=1,pool=pool)
    account(rig,'large',12,held=2,pool=pool)
    assert choose(rig,pool)=='large'

@pytest.mark.parametrize('pool',['glm','bailian','minimax'])
def test_model_cap_bottleneck_is_part_of_pressure(rig,pool):
    account(rig,'a',12,held=2,model_cap=2,model_held=1,pool=pool)
    account(rig,'b',12,held=3,model_cap=6,model_held=1,pool=pool)
    assert choose(rig,pool)=='b'

@pytest.mark.parametrize('pool',['minimax','glm','grok','cursor','bailian'])
def test_idle_equal_accounts_rotate_using_existing_grant_history(rig,pool):
    account(rig,'a',4,pool=pool); account(rig,'b',4,pool=pool)
    rig[1].execute('INSERT INTO leases VALUES(?,?,?,?,?)',(pool,'a','target','released',100))
    assert choose(rig,pool)=='b'


def test_idle_unequal_accounts_are_not_permanently_name_or_cap_biased(rig):
    account(rig,'large',12); account(rig,'small',2)
    rig[1].execute('INSERT INTO leases VALUES(?,?,?,?,?)',('minimax','large','target','released',100))
    assert choose(rig)=='small'


def test_real_expiry_precedence_survives_normalization(rig):
    account(rig,'urgent',12,held=11,pool='glm'); account(rig,'idle',12,pool='glm')
    rig[3]['urgent']=100
    assert choose(rig,'glm')=='urgent'
    assert rig[4]==[{'urgent','idle'}]

@pytest.mark.parametrize('constraint',['account_full','model_full','not_grantable'])
def test_expiry_never_promotes_ineligible_account(rig,constraint):
    urgent=account(rig,'urgent',2,held=2 if constraint=='account_full' else 1,
                   model_cap=1 if constraint=='model_full' else None,pool='glm')
    fallback=account(rig,'fallback',2,pool='glm'); rig[3]['urgent']=100
    override=[fallback] if constraint=='not_grantable' else None
    assert choose(rig,'glm',override=override)=='fallback'
    assert rig[4]==[{'fallback'}]


def test_earlier_expiry_still_beats_later_expiry(rig):
    account(rig,'earlier',4,held=3,pool='glm'); account(rig,'later',4,pool='glm')
    rig[3].update(earlier=100,later=200)
    assert choose(rig,'glm')=='earlier'

@pytest.mark.parametrize('preferred,expected',[('busy','busy'),('missing',None),('full',None)])
def test_pinned_account_remains_sticky(rig,preferred,expected):
    account(rig,'busy',4,held=3); account(rig,'idle',12); account(rig,'full',1,held=1)
    assert choose(rig,preferred=preferred)==expected


def test_host_compatible_override_is_not_expanded(rig):
    account(rig,'outside',10); allowed=account(rig,'allowed',2,held=1)
    assert choose(rig,override=[allowed])=='allowed'
    assert choose(rig,override=[]) is None


def test_model_specific_cap_refusal_remains(rig):
    account(rig,'blocked',10,held=1,model_cap=1,model_held=1)
    assert choose(rig) is None


def test_expired_released_history_rotates_but_does_not_count_as_load(rig):
    account(rig,'a',2); account(rig,'b',2,held=1)
    for _ in range(20):rig[1].execute('INSERT INTO leases VALUES(?,?,?,?,?)',('minimax','a','target','expired',500))
    assert choose(rig)=='a'


def test_other_pool_history_cannot_bias_account_choice(rig):
    account(rig,'a',2); account(rig,'b',2)
    rig[1].execute('INSERT INTO leases VALUES(?,?,?,?,?)',('another','a','target','released',999))
    assert choose(rig)=='a'


def test_same_pressure_history_tie_uses_capacity_then_name(rig):
    account(rig,'z-large',8); account(rig,'a-small',4)
    assert choose(rig)=='z-large'
    rig[2][0]['_eff_cap']=4
    assert choose(rig)=='a-small'


def test_many_sequential_equal_accounts_do_not_starve(rig):
    for n in 'abc':account(rig,n,4)
    choices=[]
    for timestamp in range(12):
        picked=choose(rig); choices.append(picked)
        rig[1].execute('INSERT INTO leases VALUES(?,?,?,?,?)',('minimax',picked,'target','released',timestamp))
    assert choices==list('abc'*4)


def test_capacity_matrix_never_picks_saturated_or_higher_pressure_account(rig):
    owner,db,accounts,_,_=rig
    for cap_a,cap_b in itertools.product(range(1,6),repeat=2):
        for held_a,held_b in itertools.product(range(cap_a+1),range(cap_b+1)):
            accounts.clear();db.execute('DELETE FROM leases')
            account(rig,'a',cap_a,held_a); account(rig,'b',cap_b,held_b)
            result=choose(rig)
            eligible=[(held_a/cap_a,'a')] if held_a<cap_a else []
            if held_b<cap_b:eligible.append((held_b/cap_b,'b'))
            if not eligible:assert result is None
            else:assert dict((name,load) for load,name in eligible)[result]==min(load for load,name in eligible)


def test_patch_is_independent_of_class_offset():
    before=(BUNDLE/'reference.py.txt').read_text()
    with tempfile.TemporaryDirectory(prefix='fabric-account-offset-') as name:
        root=Path(name);(root/'ext').mkdir()
        target=root/'ext/lease_broker.py';target.write_text('# prior native methods\n'*750+before)
        result=subprocess.run(['git','apply',str(BUNDLE/'normalized_account_balance.patch')],cwd=root,text=True,capture_output=True)
        assert result.returncode==0,result.stderr
        ast.parse(target.read_text())
