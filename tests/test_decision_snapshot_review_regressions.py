"""Causal regression cases from independent review of committed 806c65c29."""
from copy import deepcopy
import os
from pathlib import Path
import stat
import pytest
from portfolio import decision_snapshot as snapshots
from portfolio import decision_snapshot_contracts as c
from test_decision_snapshot import capture,sealed
from test_decision_snapshot_contracts import receipt


def compose(bundle, *, priors=(), recorded='2026-09-15T20:01:00Z'):
    return snapshots.compose_snapshot('autonomous',decision_cutoff='2026-09-15T20:00:00Z',recorded_at=recorded,capture=bundle,same_cutoff_prior_snapshot_ids=priors)


@pytest.mark.parametrize('source_status',['FUTURE_AT_CUTOFF','RIGHTS_BLOCKED','UNQUALIFIED_CLOCK','MALFORMED','INVALID'])
def test_partial_section_cannot_carry_rows_from_ineligible_source(source_status):
    b=capture();r=b['sources'][0];s=b['sections']['book_truth']
    r.update(status=source_status,coverage_state='PARTIAL',freshness_state='UNKNOWN',error_code=source_status)
    s['coverage_state']='PARTIAL'
    if source_status=='FUTURE_AT_CUTOFF':
        r.update(known_at='2026-09-16T00:00:00Z',generated_at='2026-09-16T00:00:00Z')
    if source_status=='RIGHTS_BLOCKED':r['rights_class']='BLOCKED'
    s['rows'][0]['future_marker']='must never enter a point-in-time packet'
    with pytest.raises(snapshots.SnapshotInvalidRequest):compose(b)


def test_future_source_receipt_can_be_recorded_as_a_gap_without_its_rows():
    b=capture();r=b['sources'][0];s=b['sections']['book_truth']
    r.update(status='FUTURE_AT_CUTOFF',coverage_state='PARTIAL',freshness_state='UNKNOWN',known_at='2026-09-16T00:00:00Z',error_code='FUTURE_AT_CUTOFF',rows_total=0,rows_returned=0,omitted_rows=0)
    s.update(coverage_state='PARTIAL',rows=[],rows_total=0,rows_returned=0,omitted_rows=0)
    p=compose(b);assert not p['sections']['book_truth']['rows']
    assert p['sources'][0]['status']=='FUTURE_AT_CUTOFF'


def test_complete_domain_cannot_omit_a_declared_required_missing_source():
    b=capture();missing=receipt();missing.update(source_id='book.positions',status='MISSING',coverage_state='BLOCKED',freshness_state='UNKNOWN',artifact_digest=None,correction_generation=None,known_at=None,clock_basis='UNKNOWN',bytes=0,rows_total=0,rows_returned=0,omitted_rows=0,error_code='MISSING')
    b['sources'].append(missing)
    assert b['sections']['book_truth']['coverage_state']=='COMPLETE'
    assert missing['source_id'] not in b['sections']['book_truth']['source_ids']
    with pytest.raises(snapshots.SnapshotInvalidRequest):compose(b)


def test_optional_absence_does_not_force_a_complete_domain_to_include_empty_receipts():
    b=capture();missing=receipt();missing.update(source_id='book.pending_optional',required=False,status='ABSENT_OPTIONAL',coverage_state='UNKNOWN',freshness_state='UNKNOWN',artifact_digest=None,correction_generation=None,known_at=None,clock_basis='UNKNOWN',bytes=0,rows_total=0,rows_returned=0,omitted_rows=0)
    b['sources'].append(missing)
    assert compose(b)['sections']['book_truth']['coverage_state']=='COMPLETE'


def test_observation_cannot_postdate_snapshot_recording():
    b=capture();b['sources'][0]['observed_at']='2027-01-01T00:00:00Z'
    with pytest.raises(snapshots.SnapshotInvalidRequest):compose(b)


def test_same_second_correction_outranks_predecessor_regardless_of_digest(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshots,'_ROOT',tmp_path)
    original=sealed();snapshots.persist_snapshot(original);corrected=None
    for i in range(1,128):
        b=capture();b['sources'][0]['correction_generation']='sha256:'+f'{i:064x}'
        p=compose(b,priors=[original['snapshot_id']])
        if p['snapshot_id']<original['snapshot_id']:
            corrected=p;break
    assert corrected is not None,'fixture must discriminate the old lexical ordering'
    snapshots.persist_snapshot(corrected)
    assert snapshots.list_snapshots('autonomous',limit=1)[0]['snapshot_id']==corrected['snapshot_id']
    assert snapshots.latest_snapshot('autonomous')['snapshot_id']==corrected['snapshot_id']
    assert snapshots.read_projection('autonomous',snapshot_id=None,section_id=None,offset=0,limit=20)['snapshot']['snapshot_id']==corrected['snapshot_id']


def test_correction_cannot_be_recorded_before_its_predecessor(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshots,'_ROOT',tmp_path)
    original=sealed(recorded_at='2026-09-15T20:10:00Z');snapshots.persist_snapshot(original)
    p=sealed(prior=[original['snapshot_id']],generation='b',recorded_at='2026-09-15T20:01:00Z')
    with pytest.raises(snapshots.SnapshotInvalidRequest):snapshots.persist_snapshot(p)
    assert len(snapshots.list_snapshots('autonomous'))==1


def test_same_identity_retry_must_resolve_containing_directory_durability(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshots,'_ROOT',tmp_path);p=sealed()
    directory=snapshots.snapshot_dir('autonomous');directory.mkdir(parents=True)
    inode=directory.stat().st_ino;original_fsync=os.fsync;calls=[]
    def failing_leaf_sync(fd):
        info=os.fstat(fd)
        if stat.S_ISDIR(info.st_mode) and info.st_ino==inode:
            calls.append(info.st_ino);raise OSError('injected leaf durability failure')
        return original_fsync(fd)
    with monkeypatch.context() as patch:
        patch.setattr(snapshots.os,'fsync',failing_leaf_sync)
        with pytest.raises(snapshots.SnapshotWriteUncertain):snapshots.persist_snapshot(p)
        first_calls=len(calls)
        assert snapshots.load_snapshot('autonomous',p['snapshot_id'])==p
        with pytest.raises(snapshots.SnapshotWriteUncertain):snapshots.persist_snapshot(p)
        assert len(calls)>first_calls
    result=snapshots.persist_snapshot(p)
    assert result['created'] is False


def test_missing_correction_predecessor_is_not_hidden_by_manifest_sort(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshots,'_ROOT',tmp_path)
    original=sealed();record=snapshots.persist_snapshot(original)
    p=sealed(prior=[original['snapshot_id']],generation='b',recorded_at='2026-09-15T20:10:00Z');snapshots.persist_snapshot(p)
    Path(record['path']).unlink()
    with pytest.raises(snapshots.SnapshotCorrupt):snapshots.list_snapshots('autonomous')
