"""R1: real idle predicate over inert incumbent lease DB; no auth/live broker.

Manual leases deliberately have no canonical _operations entry. Old expired
held/rented rows remain protective; stopping never runs GC or refunds a lease.
"""
import sqlite3
import threading
from types import SimpleNamespace

import pytest
from control_plane import paid_fabric_backend as backend


def owner(tmp_path, rows):
    path=tmp_path/'leases.sqlite'
    connection=sqlite3.connect(path)
    connection.execute('CREATE TABLE leases(pool TEXT,state TEXT,expires_at REAL)')
    connection.executemany('INSERT INTO leases VALUES(?,?,?)',rows)
    connection.commit();connection.close()
    value=object.__new__(backend.CanonicalPaidBackend)
    value._http_active=0;value._metadata_active=0;value._operations={}
    value._gateway=SimpleNamespace(_connection=lambda:sqlite3.connect(f'file:{path}?mode=ro',uri=True))
    value._context=SimpleNamespace(account_table=SimpleNamespace(_lock=threading.RLock(),_state={}))
    return value,path


@pytest.mark.parametrize('pool',['glm','glm-frontier'])
@pytest.mark.parametrize('state',['held','rented'])
@pytest.mark.parametrize('expiry',[0.0,99999999999.0])
def test_manual_served_pool_lease_blocks_stop_between_http_requests(tmp_path,pool,state,expiry):
    value,path=owner(tmp_path,[(pool,state,expiry)])
    assert not value._operations and value._http_active==0
    with pytest.raises(backend.PaidOwnerRefused):value._idle_for_stop()
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT pool,state,expires_at FROM leases').fetchall()==[(pool,state,expiry)]


def test_unrelated_provider_lease_does_not_block_this_shim(tmp_path):
    value,_=owner(tmp_path,[('bailian','held',0),('grok','rented',0)])
    value._idle_for_stop()


@pytest.mark.parametrize('which',['http','metadata','operation','pending_status'])
def test_other_original_busy_unknown_guards_remain(tmp_path,which):
    value,_=owner(tmp_path,[])
    if which=='http':value._http_active=1
    elif which=='metadata':value._metadata_active=1
    elif which=='operation':value._operations={'inert':SimpleNamespace(terminal_ready=threading.Event())}
    else:value._context.account_table._state={'inert':{'canonical_status_state':'PENDING'}}
    with pytest.raises(backend.PaidOwnerRefused):value._idle_for_stop()
