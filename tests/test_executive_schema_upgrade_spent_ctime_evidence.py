"""Closed16-origin folding over real migration pairs, with explicit synthetic Q/I.

These helper fixtures construct protocol authority payloads; they do not prove
Root issuance or Control continuation. The separate joined fixture must cover
those producers. Actual backup/drill/projection/readers and history validation
remain real; principal/OS/source seals use the inherited offline fixture seams.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from tests.test_executive_persistent_origin import filesystem


@pytest.fixture(autouse=True)
def _current_data_anchor_fixture(filesystem):
    """Explicit raw Root/Darwin facts; real held anchor predicates execute."""
    yield filesystem

from control_plane import executive_backup as b
from ops.executive_os import schema_upgrade_evidence as e
from tests.test_executive_schema_upgrade_pre_census_evidence import _recovered, _ref, _write
from tests.test_executive_schema_upgrade_evidence import _receipt_path
from tests.test_executive_acceptance_v5_to_v7 import _no_external_effects

SPENT='7'*40


def _ctime_chain(tmp_path, monkeypatch):
    runtime, release, qpath, ipath, q = _recovered(tmp_path, monkeypatch)
    pre=json.loads(_receipt_path(runtime,'P56').read_bytes())
    actual=dict(q['recovery_tool'])
    q['recovery_tool']=dict(actual, root=str(Path(actual['root']).parent/SPENT), sha=SPENT)
    _write(qpath,q,0o440)
    old_i=json.loads(ipath.read_bytes())
    old_i.update(qualification_identity=_ref(qpath,q), recovery_tool=q['recovery_tool'])
    _write(ipath,old_i)
    current=dict(q['database'],ctime_ns=q['database']['ctime_ns']+1)
    r=dict(schema_version=b.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_SCHEMA,
        operation_id=q['operation_id'],original_barrier_identity=q['original_barrier']['identity'],
        qualification_identity=_ref(qpath,q),spent_continuation_identity=_ref(ipath,old_i),
        recovery_tool=actual,database=current,created_at='2026-10-23T20:00:00+00:00')
    rpath=qpath.parent/b.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME; _write(rpath,r,0o440)
    intent=dict(schema_version=b.SPENT_PRE_CENSUS_CTIME_CONTINUATION_SCHEMA,
        operation_id=q['operation_id'],original_barrier_identity=q['original_barrier']['identity'],
        qualification_identity=_ref(qpath,q),spent_continuation_identity=_ref(ipath,old_i),
        reconciliation_identity=_ref(rpath,r),recovery_tool=actual,created_at='2026-10-23T20:01:00+00:00')
    new_i=qpath.parent/b.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME; _write(new_i,intent)
    pre['schema_version']=b.SPENT_PRE_CENSUS_CTIME_PREFLIGHT_SCHEMA
    def refresh():
        intent['reconciliation_identity']=_ref(rpath,r)
        _write(new_i,intent)
        pre['pre_census_reconciliation']=dict(qualification_identity=_ref(qpath,q),
            spent_continuation_identity=_ref(ipath,old_i),reconciliation_identity=_ref(rpath,r),
            continuation_identity=_ref(new_i,intent))
        _write(_receipt_path(runtime,'P56'),pre)
        cpath=_receipt_path(runtime,'C56'); c=json.loads(cpath.read_bytes())
        c['preflight_receipt_digest']=b._upgrade_digest(pre); _write(cpath,c)
    refresh()
    return runtime, release, qpath, ipath, q, rpath, r, new_i, intent, refresh


def test_new_sixteen_origin_initial_and_immutable_history(tmp_path,monkeypatch):
    runtime,release,qp,ip,q,rp,r,ni,intent,refresh=_ctime_chain(tmp_path,monkeypatch)
    old={p:(p.read_bytes(),p.stat().st_ino) for p in (qp,ip,rp,ni)}
    with e.open_v5_to_v7_evidence(runtime,release) as view:
        material=copy.deepcopy(view.material)
        assert material['schema_version']==e.SPENT_CTIME_MATERIAL_SCHEMA_VERSION
        assert len(material['origin_records'])==16
        assert {row['role'] for row in material['origin_records']}==set(e._SPENT_CTIME_ROLES)
        assert material['chain']['tool_release']['sha']==release
        assert view.pre_census_qualification['recovery_tool']['sha']==SPENT
        assert material['chain']['pre_census_reconciliation']['original_tool']==q['original_tool']
        assert set(material['chain']['pre_census_reconciliation'])==set(e._SPENT_CTIME_CHAIN_KEYS)
        view.check()
    # Historical mode must derive the identical original INITIAL material.
    with e.open_retained_v5_to_v7_evidence(runtime,release,material) as history:
        assert history.material==material
        history.check()
    assert old=={p:(p.read_bytes(),p.stat().st_ino) for p in old}


@pytest.mark.parametrize('fault',['raw-bytes','same-ctime','old-executor','missing-old-intent',
                                  'missing-new-intent','root-mode','old-14-schema'])
def test_foreign_or_incomplete_epoch_never_folds(tmp_path,monkeypatch,fault):
    runtime,release,qp,ip,q,rp,r,ni,intent,refresh=_ctime_chain(tmp_path,monkeypatch)
    if fault=='raw-bytes': r['database']['sha256']='0'*64
    elif fault=='same-ctime': r['database']['ctime_ns']=q['database']['ctime_ns']
    elif fault=='old-executor': r['recovery_tool']=dict(q['recovery_tool'])
    elif fault=='missing-old-intent': ip.unlink()
    elif fault=='missing-new-intent': ni.unlink()
    elif fault=='root-mode': rp.chmod(0o660)
    else:
        path=_receipt_path(runtime,'P56'); p=json.loads(path.read_bytes())
        p['schema_version']=e._RECOVERED_PREFLIGHT_SCHEMA; _write(path,p)
    if fault in ('raw-bytes','same-ctime','old-executor'):
        _write(rp,r,0o440); refresh()  # Bind actual changed bytes: fail semantic join, not stale ref.
    with pytest.raises((e.SchemaUpgradeEvidenceError,b.ExecutiveSchemaUpgradeError,OSError,ValueError)):
        with e.open_v5_to_v7_evidence(runtime,release):
            pytest.fail('unqualified spent epoch exposed DATA')


def test_new_material_cannot_be_relabelled_old_twelve_or_fourteen(tmp_path,monkeypatch):
    runtime,release,*_= _ctime_chain(tmp_path,monkeypatch)
    with e.open_v5_to_v7_evidence(runtime,release) as view:
        material=copy.deepcopy(view.material)
    for schema in (e.MATERIAL_SCHEMA_VERSION,e.RECOVERED_MATERIAL_SCHEMA_VERSION):
        changed=copy.deepcopy(material); changed['schema_version']=schema
        with pytest.raises(e.RetainedChainInvalid):
            e._validate_pinned_material(changed)
    for role in e._SPENT_CTIME_ROLES[-4:]:
        changed=copy.deepcopy(material)
        changed['origin_records']=[row for row in changed['origin_records'] if row['role']!=role]
        with pytest.raises(e.RetainedChainInvalid): e._validate_pinned_material(changed)
