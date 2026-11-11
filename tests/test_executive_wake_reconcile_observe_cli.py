"""Real read-only Runtime/ledger CLI snapshots, not a seven-day campaign proof."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.wake_ledger import SourceReadHealth
from control_plane.wake_reconcile import WakeSourceSnapshot
from control_plane.wake_events import mint_obligation
from scripts import executive_wake_reconcile as cli
from tests.test_executive_wake_fabric import _ceo_pending


def authoritative_image(root):
    # SHM stores reader locks/read marks. A newly created empty WAL is SQLite
    # bookkeeping; any existing WAL's bytes and the database must remain exact.
    return {key: value for key, value in image(root).items()
            if not key.endswith('-shm') and not key.endswith('-wal')}


def unchanged_authoritative(root, before):
    after = image(root)
    assert authoritative_image(root) == {
        key: value for key, value in before.items()
        if not key.endswith('-shm') and not key.endswith('-wal')}
    old_wal = {key: value for key, value in before.items() if key.endswith('-wal')}
    assert {key: after[key] for key in old_wal} == old_wal
    assert all(value[1] == 0 for key, value in after.items()
        if key.endswith('-wal') and key not in before)


def image(root):
    return {str(p.relative_to(root)): (p.stat().st_mode, p.stat().st_size,
        p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in root.rglob('*') if p.is_file()}


def source(*, missing=True, unknown=False):
    item = _ceo_pending()
    obligation = mint_obligation(wake_kind=item['kind'],
        source_kind='executive_inbox_attention', source_ref=item['attention_id'],
        declared_target_seat='ceo', emitted_at='2026-08-16T17:00:00Z')
    health = SourceReadHealth.DEGRADED if unknown else SourceReadHealth.HEALTHY
    return WakeSourceSnapshot(observed=(obligation,) if missing else (),
        runtime_health=health, inbox_runtime_health=health, agentos_health=health,
        degraded=('source unavailable',) if unknown else (), grounding={}, digest='a'*16)


@pytest.mark.parametrize('journal', ['delete', 'wal'])
@pytest.mark.parametrize('state', ['missing', 'empty', 'unknown'])
def test_observation_reports_plan_without_authoritative_writes(
    tmp_path, monkeypatch, capsys, journal, state,
):
    root = tmp_path / 'runtime'
    runtime = Runtime.at(root)
    runtime.jobs.create_job('Observed existing work')
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    try:
        keeper.execute('PRAGMA journal_mode='+journal)
        keeper.execute('PRAGMA wal_autocheckpoint=0')
        # Use the same SQLite connection: Runtime's writable opener itself sets
        # WAL, which would otherwise invalidate the DELETE-mode test label.
        keeper.execute("UPDATE jobs SET objective=objective || ' snapshot'")
        snapshot = source(missing=state=='missing', unknown=state=='unknown')
        monkeypatch.setattr(cli, 'collect_source_snapshot', lambda *a, **kw: snapshot)
        before = image(root)
        events_before = tuple(keeper.execute('SELECT * FROM events ORDER BY event_id'))
        assert cli.main(['--root', str(root), '--json', '--observe-only']) == (2 if state=='unknown' else 0)
        result = json.loads(capsys.readouterr().out)
        assert result['mode'] == 'observe_only' and result['writes_applied'] is False
        assert result['requested'] == result['resolved'] == []
        assert result['planned_request'] == [o.obligation_id for o in snapshot.observed]
        assert result['planned_resolve'] == []
        assert result['runtime_health'] == snapshot.runtime_health.value
        unchanged_authoritative(root, before)
        assert tuple(keeper.execute('SELECT * FROM events ORDER BY event_id')) == events_before
    finally:
        keeper.close()


def test_observation_does_not_create_missing_runtime(tmp_path, capsys):
    before = image(tmp_path)
    assert cli.main(['--root', str(tmp_path/'absent'), '--observe-only', '--json']) == 2
    assert image(tmp_path) == before


def test_observation_reports_acknowledged_resolution_without_applying_it(tmp_path, capsys):
    from tests.test_executive_wake_persist import (
        _completed_review_child, _reconcile, _requested_kind, _ack_as_human_operator,
    )
    runtime = Runtime.at(tmp_path)
    parent, child = _completed_review_child(runtime)
    _reconcile(runtime)
    oid = _requested_kind(runtime, 'review_required')[0].command_id
    runtime.jobs.create_job('Independent review slot', parent_job_id=parent.job_id,
                            reviews_job_id=child.job_id)
    _ack_as_human_operator(runtime, oid)
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    try:
        before = image(tmp_path)
        events_before = tuple(keeper.execute('SELECT * FROM events ORDER BY event_id'))
        # Runtime evidence is available, but deliberately uncollected Agent OS
        # remains degraded. Retain the plan without treating it as a full census.
        assert cli.main(['--root', str(tmp_path), '--observe-only', '--no-boot-packet', '--json']) == 2
        result = json.loads(capsys.readouterr().out)
        assert result['planned_resolve'] == [oid]
        assert result['resolved'] == result['requested'] == []
        assert result['writes_applied'] is False
        assert result['agentos_health'] == SourceReadHealth.DEGRADED.value
        unchanged_authoritative(tmp_path, before)
        assert tuple(keeper.execute('SELECT * FROM events ORDER BY event_id')) == events_before
    finally:
        keeper.close()


def test_observation_unknown_boot_schema_is_degraded_without_changes(tmp_path, capsys):
    runtime = Runtime.at(tmp_path)
    bad = tmp_path/'invalid.json'
    bad.write_text('{"schema":"not-the-boot-schema"}')
    before = image(tmp_path)
    assert cli.main(['--root', str(tmp_path), '--observe-only', '--json', '--boot-packet-file', str(bad)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['degraded'] and result['agentos_health'] == SourceReadHealth.DEGRADED.value
    assert result['writes_applied'] is False
    unchanged_authoritative(tmp_path, before)


def test_observation_source_failure_changes_nothing(tmp_path, monkeypatch):
    Runtime.at(tmp_path)
    def unavailable(*a, **kw):
        raise RuntimeError('fixture source acquisition failed')
    monkeypatch.setattr(cli, 'collect_source_snapshot', unavailable)
    before = image(tmp_path)
    assert cli.main(['--root', str(tmp_path), '--observe-only', '--json']) == 2
    unchanged_authoritative(tmp_path, before)


def test_default_cli_still_applies_existing_reconciliation(tmp_path, monkeypatch, capsys):
    runtime = Runtime.at(tmp_path)
    snapshot = source()
    monkeypatch.setattr(cli, 'reconcile_wakes', __import__(
        'control_plane.wake_reconcile', fromlist=['reconcile_wakes']).reconcile_wakes)
    monkeypatch.setattr(__import__('control_plane.wake_reconcile', fromlist=['collect_source_snapshot']),
        'collect_source_snapshot', lambda *a, **kw: snapshot)
    before = runtime.events.list_events()
    assert cli.main(['--root', str(tmp_path), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['requested'] == [o.obligation_id for o in snapshot.observed]
    assert 'mode' not in result
    assert 'capacity_observation' not in result
    assert len(runtime.events.list_events()) == len(before)+1


def test_cli_consumes_real_owner_intervals_without_authoritative_writes(tmp_path, monkeypatch, capsys):
    from tests.test_capacity_campaign_observation import owner_stream, snapshot
    runtime, _, _ = owner_stream(tmp_path, retry=True)
    monkeypatch.setattr(cli, 'collect_source_snapshot', lambda *a, **kw: snapshot())
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    try:
        before = image(tmp_path)
        events_before = tuple(keeper.execute('SELECT * FROM events ORDER BY event_id'))
        assert cli.main(['--root', str(tmp_path), '--observe-only', '--json']) == 0
        result = json.loads(capsys.readouterr().out)
        observation = result['capacity_observation']
        assert observation['point_status'] == 'OBSERVED'
        assert observation['interval_summaries']['request_to_ack_ms']['p95'] == 5000
        assert observation['acknowledgement_counts']['reasoning_session'] == 1
        assert observation['campaign_qualified'] is False
        assert observation['unavailable_metrics']['original_parent_disposition_consumption']['value'] is None
        assert result['writes_applied'] is False
        unchanged_authoritative(tmp_path, before)
        assert tuple(keeper.execute('SELECT * FROM events ORDER BY event_id')) == events_before
    finally:
        keeper.close()


def test_cli_retains_unfinished_intervals_under_degraded_coverage(tmp_path, monkeypatch, capsys):
    from tests.test_capacity_campaign_observation import owner_stream, snapshot
    _, obligation, _ = owner_stream(tmp_path, pending=True)
    monkeypatch.setattr(cli, 'collect_source_snapshot',
                        lambda *a, **kw: snapshot((obligation,), degraded=True))
    assert cli.main(['--root', str(tmp_path), '--observe-only', '--json']) == 2
    observation = json.loads(capsys.readouterr().out)['capacity_observation']
    assert observation['point_status'] == 'PARTIAL'
    summary = observation['interval_summaries']['request_to_ack_ms']
    assert summary['population'] == 1 and summary['unfinished'] == 1
    assert summary['completed'] == 0 and summary['p95'] is None


@pytest.mark.parametrize('failure,exit_code', [('clock', 2), ('wire', 3)])
def test_cli_measurement_failure_preserves_partial_diagnostics_and_exit_code(
    tmp_path, monkeypatch, capsys, failure, exit_code,
):
    from dataclasses import replace
    from tests.test_capacity_campaign_observation import owner_stream, snapshot
    _, _, ledger = owner_stream(tmp_path)
    item = ledger.events[2]
    damaged = (replace(item, event=replace(item.event, created_at=None)) if failure == 'clock'
               else replace(item, record=replace(item.record, binding_generation=2)))
    ledger = replace(ledger, events=ledger.events[:2] + (damaged,) + ledger.events[3:])
    monkeypatch.setattr(cli, 'collect_source_snapshot', lambda *a, **kw: snapshot())
    monkeypatch.setattr(cli, 'collect_ledger_snapshot', lambda *a, **kw: ledger)
    before = image(tmp_path)
    assert cli.main(['--root', str(tmp_path), '--observe-only', '--json']) == exit_code
    result = json.loads(capsys.readouterr().out)
    summary = result['capacity_observation']['interval_summaries']['request_to_ack_ms']
    assert summary['completed'] == 0 and summary['unavailable'] == 1 and summary['p95'] is None
    unchanged_authoritative(tmp_path, before)
