"""Contract tests for the existing read-only casebook reporting consumer."""
import json
from pathlib import Path

import pytest

from reaction_replay import ReplayError
from replay_casebook import build_report, markdown, main


def test_nine_records_and_issuer_membership_are_source_backed():
    report = build_report()
    assert report['sample_size'] == 9
    assert report['per_issuer_counts'] == {'CIK:1018724':3, 'CIK:1652044':3, 'CIK:789019':3}
    assert report['point_in_time_analyst_consensus'] == 'NOT_ADMITTED'
    assert report['tradeable_alpha_status'] == 'NOT_ESTABLISHED'
    assert all(e['first_public_release_exact'] is None for e in report['cases'])
    assert all(e['h5_status'] == 'INSUFFICIENT_FUTURE_SESSIONS' for e in report['cases'])
    assert all(e['reaction_status'] == 'AVAILABLE' for e in report['cases'])
    assert all(e['market_ticker'] == 'SPY' for e in report['cases'])


def test_april_simultaneous_releases_and_sector_comparator():
    report = build_report()
    april = [x for x in report['cases'] if x['unaffected_last_close_session'] == '2026-04-29']
    assert len(april) == 3
    assert {x['issuer_ref']:x['sector_ticker'] for x in april} == {'CIK:1652044':'XLC','CIK:789019':'XLK','CIK:1018724':'XLY'}
    assert {x['market_return_pct'] for x in april} == {0.9958}
    assert all(e['release_clock_quality'] == 'SESSION_WINDOW_CORROBORATED_EARLIEST_RELEASE_UNKNOWN' for e in report['cases'])


def test_markdown_output_never_uses_bare_unknown_values_as_zero(capsys):
    assert main(['--format','markdown']) == 0
    text = capsys.readouterr().out
    assert '| Event |' in text
    assert 'not a predictive trading signal' in text
    assert 'NOT_ADMITTED' in text
    assert 'unavailable' not in text  # all six price comparisons currently available


def test_json_output_machine_readable_and_signed_returns(capsys):
    assert main(['--format','json']) == 0
    obj=json.loads(capsys.readouterr().out)
    assert obj['sample_size']==9
    a={x['packet_ref']: x for x in obj['cases']}
    assert a['googl_2026q1.json']['issuer_return_pct'] > 0
    assert a['googl_2026q2.json']['issuer_return_pct'] < 0
    assert a['msft_fy2026q2.json']['issuer_return_pct'] < -9
    assert a['amzn_2026q2.json']['issuer_return_pct'] > 15


def test_corrupt_witness_refuses_without_replacing_with_zero(tmp_path):
    from replay_casebook import PACKETS
    fixture=json.loads((PACKETS/'amzn_2026q2.json').read_text())
    fixture['event']['public_by_source_kind']='SEC_ACCEPTANCE'
    (tmp_path/'bad.json').write_text(json.dumps(fixture))
    with pytest.raises(ReplayError) as exc:
        build_report(tmp_path)
    assert exc.value.reason == 'NON_SEC_PUBLIC_RELEASE_WITNESS_REQUIRED'
