"""Media-quoted aggregate expectations are research context, not PIT analyst vintages."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from replay_casebook import MEDIA, PACKETS, build_report, markdown


def _tampered(tmp_path, change):
    exhibit=deepcopy(json.loads(MEDIA.read_text()))
    change(exhibit)
    dst=tmp_path/'modified.json'
    dst.write_text(json.dumps(exhibit))
    return dst


def test_all_seven_cloud_media_witnesses_link_to_real_casebook_event():
    r=build_report()
    assert r['sample_size']==9
    assert r['media_reported_expectation_status']=='PUBLIC_ARTICLE_WITNESSES_ONLY_NOT_ADMITTED_AS_PIT'
    assert r['point_in_time_analyst_consensus']=='NOT_ADMITTED'
    assert len(r['media_reported_expectation_witnesses'])==7
    assert {p['packet_ref'] for p in r['media_reported_expectation_witnesses']} <= {p['packet_ref'] for p in r['cases']}
    assert all(p['consensus_vintage_admitted'] is False for p in r['media_reported_expectation_witnesses'])
    assert all(p['source_ref'].startswith('https://') for p in r['media_reported_expectation_witnesses'])


def test_googl_q2_did_beat_reported_cloud_expectation_but_stock_fell():
    r=build_report()
    rows={p['packet_ref']:p for p in r['media_reported_expectation_witnesses']}
    a=rows['googl_2026q1.json']; b=rows['googl_2026q2.json']
    assert (a['reported_expected_growth_pct'],a['reported_actual_growth_pct'],a['article_reported_gap_pp'])==(50.1,63.0,12.9)
    assert (b['reported_expected_growth_pct'],b['reported_actual_growth_pct'],b['article_reported_gap_pp'])==(64.0,82.0,18.0)
    assert a['stock_reaction_pct']>0 and b['stock_reaction_pct']<0
    assert b['article_reported_gap_pp']>a['article_reported_gap_pp']


def test_msft_amzn_media_surprises_do_not_mimic_buy_signal():
    r=build_report()
    rows={p['packet_ref']:p for p in r['media_reported_expectation_witnesses']}
    assert rows['msft_fy2026q3.json']['article_reported_gap_pp']==0.0
    assert rows['msft_fy2026q3.json']['stock_reaction_pct']<0
    assert rows['amzn_2026q2.json']['article_reported_gap_pp']==5.79
    assert rows['amzn_2026q2.json']['stock_reaction_pct']>15
    assert r['tradeable_alpha_status']=='NOT_ESTABLISHED'
    assert r['prediction_status']=='NOT_TESTED'


def test_revenue_revision_up_eps_revision_down_and_date_only_pit_refusal():
    r=build_report()
    s=r['indicative_expectation_revision_report']
    assert s['revenue_change_billion']==4.2
    assert s['eps_change']==-0.11
    assert s['exact_publication_clock_known'] is False
    assert s['historical_consensus_vintages_admitted'] is False
    assert s['older_eps_asof']=='UNSPECIFIED_IN_ARTICLE'
    report=markdown(r)
    assert 'Media-reported cloud growth consensus witnesses (NOT PIT-admitted)' in report
    assert 'Alphabet Q2 S&P/Visible Alpha revision context (date-only source)' in report
    assert f"[S&P/Visible Alpha research article]({s['source_ref']})" in report
    assert '[report](https://www.investing.com/news/stock-market-news/microsoft-tops-quarterly-cloud-growth-estimates-easing-spending-concerns-4821582)' in report


def test_missing_public_media_evidence_is_explicit_not_zero(tmp_path):
    r=build_report(PACKETS,media_path=tmp_path/'no-file.json')
    assert r['sample_size']==9
    assert r['media_reported_expectation_status']=='MEDIA_REPORTED_EXPECTATIONS_SOURCE_UNAVAILABLE'
    assert r['media_reported_expectation_witnesses']==[]
    assert r['indicative_expectation_revision_report'] is None


@pytest.mark.parametrize('change,reason',[
    (lambda x:x.update(aggregate_pit_status='ADMITTED'),'MEDIA_WITNESS_PROVENANCE_NOT_ADMISSIBLE'),
    (lambda x:x['source_reported_event_expectations'][0].update(underlying_analyst_vintage_utc='2026-01-27T16:00:00Z'),'MEDIA_WITNESS_IMPROPERLY_PROMOTED'),
    (lambda x:x['source_reported_event_expectations'][0].update(fiscal_target='2026Q1'),'MEDIA_WITNESS_EVENT_IDENTITY_MISMATCH'),
    (lambda x:x['source_reported_event_expectations'].append(dict(x['source_reported_event_expectations'][0])),'DUPLICATE_MEDIA_WITNESS'),
    (lambda x:x['indicative_consensus_revision_report'].update(article_pit_eligible=True),'REVISION_PREVIEW_PIT_NOT_QUALIFIED'),
    (lambda x:x['source_reported_event_expectations'][0].update(actual_yoy_growth_pct=1200),'MEDIA_WITNESS_GROWTH_OUT_OF_RANGE'),
    (lambda x:x['source_reported_event_expectations'][0].update(article_first_reported_utc='2026-01-28T20:59:00Z'),'MEDIA_WITNESS_NOT_AFTER_REGULAR_CLOSE'),
    (lambda x:x['source_reported_event_expectations'][0].update(article_first_reported_utc='2026-01-28T16:03:00'),'MEDIA_WITNESS_UTC_REQUIRED'),
    (lambda x:x['source_reported_event_expectations'][0].update(article_source_url='http://example.com'),'MEDIA_WITNESS_SOURCE_URL_REQUIRED'),
])
def test_media_witness_unsafe_promotion_or_invalidity_refused(tmp_path,change,reason):
    with pytest.raises(ValueError,match=reason):
        build_report(PACKETS,media_path=_tampered(tmp_path,change))
