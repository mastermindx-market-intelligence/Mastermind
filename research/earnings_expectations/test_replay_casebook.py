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



def test_guidance_is_composed_as_an_explicit_non_consensus_channel():
    report=build_report()
    assert report['management_guidance_status']=='AVAILABLE_COMPANY_MANAGEMENT_GUIDANCE_ONLY'
    assert report['point_in_time_analyst_consensus']=='NOT_ADMITTED'
    q1,q2=report['management_guidance_comparisons']
    assert (q1['fiscal_target'],q1['guidance_midpoint_billion'],q1['actual_billion']) == ('2026Q1',176.0,181.5)
    assert (q2['fiscal_target'],q2['guidance_midpoint_billion'],q2['actual_billion']) == ('2026Q2',196.5,200.6)
    assert q1['actual_minus_high_billion']==3.0
    assert q2['actual_minus_high_billion']==1.6
    assert q1['actual_minus_midpoint_pct']==3.125
    assert q2['actual_minus_midpoint_pct']==2.0865
    assert q1['issuer_return_pct'] < q2['issuer_return_pct']
    assert all('NOT_ANALYST_CONSENSUS' in x['forecast_channel'] for x in (q1,q2))


def test_guidance_markdown_reports_precise_signed_dollars_and_percentages():
    result=markdown(build_report())
    assert 'Public management-guidance comparisons (NOT analyst consensus)' in result
    assert '| 2026Q1 | $176.0B | $181.5B | +3.125% | +$3.0B | +0.77% |' in result
    assert '| 2026Q2 | $196.5B | $200.6B | +2.087% | +$1.6B | +15.32% |' in result
    assert '$+3.0B' not in result


def test_guidance_source_missing_does_not_invent_zero(tmp_path):
    from replay_casebook import PACKETS
    r=build_report(PACKETS,guidance_path=tmp_path/'not-there.json')
    assert r['sample_size']==9
    assert r['management_guidance_status']=='GUIDANCE_SOURCE_UNAVAILABLE'
    assert r['management_guidance_comparisons']==[]


def test_guidance_channel_and_basis_refuse_mislabeling(tmp_path):
    from replay_casebook import PACKETS, GUIDANCE
    original=json.loads(GUIDANCE.read_text())
    for field,value in [('forecast_channel','SELL_SIDE_CONSENSUS'),('analyst_consensus_status','ADMITTED'),('basis','GAAP_EPS')]:
        exhibit=json.loads(json.dumps(original))
        exhibit[field]=value
        p=tmp_path/'bad.json'
        p.write_text(json.dumps(exhibit))
        with pytest.raises(ValueError,match='GUIDANCE_CHANNEL_OR_BASIS_INVALID'):
            build_report(PACKETS,p)


def test_guidance_temporal_identity_and_duplicate_refusals(tmp_path):
    from replay_casebook import PACKETS, GUIDANCE
    original=json.loads(GUIDANCE.read_text())
    for changes,expected in [
        ({'prior_guidance_release_date':'2026-05-01'},'GUIDANCE_NOT_PRIOR_TO_ACTUAL'),
        ({'fiscal_target':'2025Q4'},'GUIDANCE_EVENT_IDENTITY_MISMATCH'),
    ]:
        exhibit=json.loads(json.dumps(original))
        exhibit['observations'][0].update(changes)
        p=tmp_path/'bad.json'
        p.write_text(json.dumps(exhibit))
        with pytest.raises(ValueError,match=expected):
            build_report(PACKETS,p)
    exhibit=json.loads(json.dumps(original))
    exhibit['observations'].append(dict(exhibit['observations'][0]))
    p=tmp_path/'bad.json'
    p.write_text(json.dumps(exhibit))
    with pytest.raises(ValueError,match='DUPLICATE_GUIDANCE_TARGET'):
        build_report(PACKETS,p)
