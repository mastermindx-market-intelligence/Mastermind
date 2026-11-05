"""Daily benchmark selection must ignore co-located price-history sidecars."""
import json

import pytest

from brain import benchmark_ledger as B


@pytest.fixture
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(B, '_BENCH_DIR', tmp_path)
    return tmp_path


def write_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def test_latest_ignores_scheduler_and_backfill_sidecars(ledger_dir):
    expected = {'as_of': '2026-10-02', 'bogeys': {'spy': {'return_pct': 10.0}}}
    write_json(ledger_dir / '2026-10-01.json', {'as_of': '2026-10-01'})
    write_json(ledger_dir / '2026-10-02.json', expected)
    write_json(ledger_dir / '_series.json', {'SPY': {'2026-10-02': 110.0}})
    write_json(ledger_dir / '_series_meta.json', {'SPY': {'2026-10-02': 'yahoo'}})
    assert B.latest() == expected


def test_latest_selects_latest_date_independent_of_creation_order(ledger_dir):
    write_json(ledger_dir / '2026-10-02.json', {'as_of': '2026-10-02'})
    write_json(ledger_dir / '2026-10-01.json', {'as_of': '2026-10-01'})
    assert B.latest()['as_of'] == '2026-10-02'


@pytest.mark.parametrize('name', [
    '_series.json', '_series_meta.json', 'notes.json', '2026-10-02.backup.json',
    '20261002.json', '2026-W40-5.json', '2026-1-02.json', '2026-02-30.json',
    '2026-13-02.json', '2026-00-02.json', '2026-10-00.json', '2026-10-02-extra.json',
])
def test_latest_does_not_treat_noncanonical_names_as_ledgers(ledger_dir, name):
    write_json(ledger_dir / name, {'unrelated': True})
    assert B.latest() == {}


@pytest.mark.parametrize('day', ['1999-12-31', '2000-02-29', '2024-02-29', '2026-10-02'])
def test_latest_accepts_valid_calendar_dates(ledger_dir, day):
    expected = {'as_of': day, 'bogeys': {}}
    write_json(ledger_dir / f'{day}.json', expected)
    assert B.latest() == expected


def test_latest_keeps_corrupt_newest_unavailable_instead_of_stale_fallback(ledger_dir):
    write_json(ledger_dir / '2026-10-01.json', {'as_of': '2026-10-01'})
    (ledger_dir / '2026-10-02.json').write_text('{broken', encoding='utf-8')
    write_json(ledger_dir / '_series.json', {'SPY': {'2026-10-02': 110.0}})
    assert B.latest() == {}


def test_latest_keeps_unreadable_newest_unavailable(ledger_dir, monkeypatch):
    from pathlib import Path
    write_json(ledger_dir / '2026-10-01.json', {'as_of': '2026-10-01'})
    write_json(ledger_dir / '2026-10-02.json', {'as_of': '2026-10-02'})
    read_text = Path.read_text
    def unreadable(path, *args, **kwargs):
        if path.name == '2026-10-02.json':
            raise PermissionError('synthetic unreadable newest ledger')
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', unreadable)
    assert B.latest() == {}


def test_latest_empty_directory_is_unavailable(ledger_dir):
    assert B.latest() == {}


def test_latest_does_not_select_nested_regional_ledgers(ledger_dir):
    write_json(ledger_dir / '2026-10-01.json', {'as_of': '2026-10-01'})
    regional = ledger_dir / 'china'
    regional.mkdir()
    write_json(regional / '2026-10-02.json', {'as_of': '2026-10-02', 'book_id': 'china'})
    assert B.latest() == {'as_of': '2026-10-01'}


def test_latest_missing_directory_is_unavailable(ledger_dir, monkeypatch):
    monkeypatch.setattr(B, '_BENCH_DIR', ledger_dir / 'not-created')
    assert B.latest() == {}
