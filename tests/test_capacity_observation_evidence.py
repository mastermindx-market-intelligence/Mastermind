"""Real Runtime/CLI/artifact custody; fixture clocks never prove installed time."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from control_plane import capacity_observation_evidence as evidence
from scripts import executive_wake_reconcile as cli
from tests.test_capacity_campaign_observation import owner_stream, snapshot
from tests.test_executive_wake_reconcile_observe_cli import image, unchanged_authoritative


@pytest.fixture
def receipt_dir(tmp_path):
    path = tmp_path / 'evidence'
    path.mkdir(mode=0o700)
    return path


def observe(root, path, monkeypatch, capsys):
    monkeypatch.setattr(cli, 'collect_source_snapshot', lambda *a, **kw: snapshot())
    code = cli.main(['--root', str(root), '--observe-only', '--observation-receipt', str(path)])
    return code, capsys.readouterr()


def rewrite(path, update):
    value = json.loads(path.read_text())
    update(value)
    path.chmod(0o600)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    path.chmod(0o400)


def test_real_owner_receipt_and_offline_close_never_mutate_runtime(
    tmp_path, receipt_dir, monkeypatch, capsys,
):
    root = tmp_path / 'runtime'
    runtime, _, _ = owner_stream(root, retry=True)
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    try:
        before = image(root)
        events = tuple(keeper.execute('SELECT * FROM events ORDER BY event_id'))
        target = receipt_dir / 'first.json'
        code, streams = observe(root, target, monkeypatch, capsys)
        assert code == 0
        receipt = json.loads(target.read_text())
        assert receipt['stdout'] == streams.out and receipt['stderr'] == streams.err
        assert receipt['stdout_sha256'] == hashlib.sha256(streams.out.encode()).hexdigest()
        assert receipt['capture_started_at'] <= receipt['capture_finished_at']
        assert receipt['acquisition_monotonic_ns'] >= 0
        assert receipt['execution_provenance'] == 'UNATTESTED_SOURCE_OBSERVATION'
        assert receipt['installed_coverage_claimed'] is receipt['campaign_qualified'] is False
        assert target.stat().st_mode & 0o777 == 0o400
        point = json.loads(streams.out)['capacity_observation']
        assert point['interval_summaries']['request_to_ack_ms']['p95'] == 5000

        def no_runtime(*a, **kw):
            raise AssertionError('offline close must not acquire Runtime')
        monkeypatch.setattr(cli.Runtime, 'at', no_runtime)
        assert cli.main(['--summarize-observations', str(target), '--json']) == 0
        closed = json.loads(capsys.readouterr().out)
        assert closed['observations'][0]['interval_summaries'] == point['interval_summaries']
        assert closed['unproven_requirements']['actual_total_cost_per_accepted_outcome']['value'] is None
        assert closed['max_recorded_gap_seconds'] is None
        assert closed['campaign_qualified'] is False
        unchanged_authoritative(root, before)
        assert tuple(keeper.execute('SELECT * FROM events ORDER BY event_id')) == events
    finally:
        keeper.close()


def test_first_missing_runtime_is_retained_as_failure_not_empty_healthy_point(
    tmp_path, receipt_dir, capsys,
):
    root, target = tmp_path / 'missing', receipt_dir / 'failed.json'
    assert cli.main(['--root', str(root), '--observe-only', '--observation-receipt', str(target)]) == 2
    streams = capsys.readouterr()
    record = json.loads(target.read_text())
    assert record['observer_return_code'] == 2 and record['stderr'] == streams.err
    assert record['stdout'] == '' and not root.exists()
    report = evidence.summarize_observations([target])
    assert report['observer_failure_count'] == 1
    assert report['observations'][0]['point_status'] == 'UNAVAILABLE'
    assert report['observations'][0]['interval_summaries'] is None


def test_receipt_flag_cannot_select_the_mutating_default_path(receipt_dir, monkeypatch):
    monkeypatch.setattr(cli, '_run', lambda *a: pytest.fail('owner invoked'))
    target = receipt_dir / 'not-created.json'
    with pytest.raises(SystemExit):
        cli.main(['--observation-receipt', str(target)])
    assert not target.exists()


def test_offline_summary_rejects_live_or_saved_source_flags(receipt_dir, monkeypatch):
    monkeypatch.setattr(cli, '_run', lambda *a: pytest.fail('owner invoked'))
    for extra in (['--root', '/different'], ['--observe-only'], ['--no-boot-packet'],
                  ['--boot-packet-file', '/saved'], ['--observation-receipt', '/output']):
        with pytest.raises(SystemExit):
            cli.main(['--summarize-observations', str(receipt_dir / 'x.json'), *extra])


def test_existing_receipt_prevents_another_observation(
    tmp_path, receipt_dir, monkeypatch, capsys,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    target = receipt_dir / 'once.json'
    assert observe(root, target, monkeypatch, capsys)[0] == 0
    original = target.read_bytes()
    monkeypatch.setattr(cli, '_run', lambda *a: pytest.fail('duplicate observation'))
    assert cli.main(['--root', str(root), '--observe-only', '--observation-receipt', str(target)]) == 2
    assert target.read_bytes() == original


def test_interrupted_capture_leaves_unusable_original_reservation(receipt_dir):
    path = receipt_dir / 'interrupted.json'
    def interrupted():
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        evidence.capture_observation(path, interrupted, runtime_root=receipt_dir,
            boot_packet_origin='owner_collected', source_files=(Path(__file__),))
    assert path.exists()
    report = evidence.summarize_observations([path])
    assert report['observation_count'] == 0 and report['failures']
    with pytest.raises(FileExistsError):
        evidence.capture_observation(path, lambda: pytest.fail('replayed'), runtime_root=receipt_dir,
            boot_packet_origin='owner_collected', source_files=(Path(__file__),))


def test_explicit_set_reports_gaps_missing_and_duplicate_bytes_deterministically(
    tmp_path, receipt_dir, monkeypatch, capsys,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    first, last = receipt_dir / 'first.json', receipt_dir / 'last.json'
    # Explicitly synthetic clocks cover the dangerous false-qualification case.
    times = iter(['2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:01.000000Z',
                  '2026-01-08T00:00:00.000000Z', '2026-01-08T00:00:01.000000Z'])
    monkeypatch.setattr(evidence, '_utc_now', lambda: next(times))
    assert observe(root, first, monkeypatch, capsys)[0] == 0
    assert observe(root, last, monkeypatch, capsys)[0] == 0
    report = evidence.summarize_observations([last, first])
    assert report == evidence.summarize_observations([first, last])
    assert report['recorded_wall_clock_span_seconds'] == 604801
    assert report['max_recorded_gap_seconds'] == 604799
    assert report['installed_coverage_claimed'] is report['campaign_qualified'] is False
    assert all(row['value'] is None for row in report['unproven_requirements'].values())
    incomplete = evidence.summarize_observations([first, receipt_dir / 'absent.json', first])
    assert incomplete['observation_count'] == 1 and len(incomplete['failures']) == 2
    assert incomplete['recorded_gaps'] == []
    assert {f['reason'] for f in incomplete['failures']} == {'FileNotFoundError', 'DUPLICATE_OBSERVATION_BYTES'}


@pytest.mark.parametrize('change,reason', [
    (lambda d: d.update(capture_started_at='2026-01-01'), 'INVALID_OBSERVATION_TIMESTAMP'),
    (lambda d: d.update(capture_finished_at='2000-01-01T00:00:00.000000Z'), 'OBSERVATION_CLOCK_REGRESSED'),
    (lambda d: d.update(acquisition_monotonic_ns=-1), 'OBSERVATION_CLOCK_REGRESSED'),
    (lambda d: d.update(installed_coverage_claimed=True), 'UNSUPPORTED_PROVENANCE_CLAIM'),
    (lambda d: d.update(campaign_qualified=True), 'UNSUPPORTED_PROVENANCE_CLAIM'),
    (lambda d: d.update(stdout=d['stdout'] + ' '), 'STREAM_DIGEST_MISMATCH'),
    (lambda d: d['source_files_after'].update({'/drifted': '0' * 64}), 'SOURCE_BYTES_CHANGED_DURING_OBSERVATION'),
    (lambda d: d.update(writer_uid=d['writer_uid'] + 1), 'WRITER_CUSTODY_MISMATCH'),
    (lambda d: d.update(extra_claim='installed'), 'INVALID_RECEIPT_FIELDS'),
])
def test_bad_clock_bytes_or_claims_are_not_coverage(
    tmp_path, receipt_dir, monkeypatch, capsys, change, reason,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    path = receipt_dir / 'point.json'
    assert observe(root, path, monkeypatch, capsys)[0] == 0
    rewrite(path, change)
    report = evidence.summarize_observations([path])
    assert report['observation_count'] == 0
    assert report['failures'][0]['reason'] == reason
    assert report['recorded_wall_clock_span_seconds'] is None


@pytest.mark.parametrize('damage', ['mode', 'hardlink', 'symlink', 'directory', 'fifo', 'parent_alias'])
def test_non_direct_or_mutable_receipt_custody_refuses(
    tmp_path, receipt_dir, monkeypatch, capsys, damage,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    path = receipt_dir / 'point.json'
    assert observe(root, path, monkeypatch, capsys)[0] == 0
    if damage == 'mode':
        path.chmod(0o600)
    elif damage == 'hardlink':
        os.link(path, receipt_dir / 'another.json')
    elif damage == 'symlink':
        alias = receipt_dir / 'alias.json'; alias.symlink_to(path); path = alias
    elif damage == 'directory':
        path = receipt_dir / 'directory'; path.mkdir(mode=0o700)
    elif damage == 'fifo':
        path = receipt_dir / 'fifo'; os.mkfifo(path, 0o400)
    else:
        alias = tmp_path / 'alias'; alias.symlink_to(receipt_dir, target_is_directory=True)
        path = alias / path.name
    report = evidence.summarize_observations([path])
    assert report['observation_count'] == 0 and report['failures']


def test_byte_identical_replacement_during_read_is_not_accepted(
    tmp_path, receipt_dir, monkeypatch, capsys,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    path = receipt_dir / 'point.json'
    assert observe(root, path, monkeypatch, capsys)[0] == 0
    raw = path.read_bytes()
    read = evidence.os.read
    replaced = False
    def replace_after_read(fd, size):
        nonlocal replaced
        result = read(fd, size)
        if not replaced:
            replacement = receipt_dir / 'replacement.json'
            replacement.write_bytes(raw); replacement.chmod(0o400)
            replacement.replace(path); replaced = True
        return result
    monkeypatch.setattr(evidence.os, 'read', replace_after_read)
    report = evidence.summarize_observations([path])
    assert report['observation_count'] == 0
    assert report['failures'][0]['reason'] == 'EVIDENCE_FILE_CUSTODY'


def test_source_and_runtime_drift_are_separate_inputs_not_one_installed_campaign(
    tmp_path, receipt_dir, monkeypatch, capsys,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    a, b = receipt_dir / 'a.json', receipt_dir / 'b.json'
    assert observe(root, a, monkeypatch, capsys)[0] == 0
    assert observe(root, b, monkeypatch, capsys)[0] == 0
    rewrite(b, lambda d: d.update(runtime_root='/different/runtime'))
    report = evidence.summarize_observations([a, b])
    assert report['observation_count'] == 2
    assert report['failures'][-1]['reason'] == 'MIXED_RUNTIME_SOURCE_OR_BOOT_INPUTS'
    assert report['campaign_qualified'] is False


def test_bounds_keep_unread_expected_inputs_explicit(
    tmp_path, receipt_dir, monkeypatch, capsys,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    a = receipt_dir / 'a.json'
    assert observe(root, a, monkeypatch, capsys)[0] == 0
    monkeypatch.setattr(evidence, 'MAX_COLLECTION_BYTES', 1)
    report = evidence.summarize_observations([a, receipt_dir / 'b.json'])
    assert report['input_count_requested'] == len(report['inputs']) == 2
    assert report['failures'][1]['reason'] == 'NOT_READ_COLLECTION_BYTES_BOUND'
    with pytest.raises(evidence.ObservationEvidenceError, match='COLLECTION_INPUT_BOUND'):
        evidence.summarize_observations([a] * (evidence.MAX_RECEIPTS + 1))


def test_duplicate_json_and_unavailable_acl_never_become_valid_evidence(
    tmp_path, receipt_dir, monkeypatch, capsys,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    path = receipt_dir / 'point.json'
    assert observe(root, path, monkeypatch, capsys)[0] == 0
    raw = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(raw.replace(b'{', b'{"campaign_qualified":false,', 1))
    path.chmod(0o400)
    assert evidence.summarize_observations([path])['failures'][0]['reason'] == 'DUPLICATE_JSON_KEY'
    def unavailable(*args, **kwargs):
        raise evidence.FilesystemSecurityError('fixture ACL unavailability')
    monkeypatch.setattr(evidence, 'has_macos_acl', unavailable)
    assert evidence.summarize_observations([path])['failures'][0]['reason'] == 'FilesystemSecurityError'


@pytest.mark.parametrize('location', ['document', 'stdout'])
def test_nested_json_remains_an_explicit_offline_input_failure(
    tmp_path, receipt_dir, monkeypatch, capsys, location,
):
    root = tmp_path / 'runtime'
    owner_stream(root)
    valid = receipt_dir / 'valid.json'
    assert observe(root, valid, monkeypatch, capsys)[0] == 0
    # The native decoder's C-stack limit is independent of Python's frame
    # recursion limit on newer interpreters. Stay well within the byte budget.
    nested = '[' * 131072 + '0' + ']' * 131072
    invalid = receipt_dir / 'nested.json'
    if location == 'document':
        raw = nested.encode()
    else:
        value = json.loads(valid.read_text())
        value['stdout'] = nested
        value['stdout_sha256'] = hashlib.sha256(nested.encode()).hexdigest()
        raw = (json.dumps(value) + '\n').encode()
    assert len(raw) < evidence.MAX_RECEIPT_BYTES
    invalid.write_bytes(raw)
    invalid.chmod(0o400)
    monkeypatch.setattr(cli.Runtime, 'at', lambda *a, **kw: pytest.fail('offline Runtime read'))
    report = evidence.summarize_observations([invalid, valid])
    assert report['observation_count'] == 1
    assert report['failures'] == [{'path': str(invalid), 'reason': 'JSON_NESTING_LIMIT'}]
    assert report['state'] == 'INPUTS_INCOMPLETE'
    assert cli.main(['--summarize-observations', str(valid), str(invalid)]) == 2
    streams = capsys.readouterr()
    assert json.loads(streams.out) == report and streams.err == ''
    assert invalid.read_bytes() == raw
