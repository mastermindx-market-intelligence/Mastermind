"""First-party management guidance is never presented as analyst consensus."""
from datetime import date
from decimal import Decimal as D
import json
from pathlib import Path

from reaction_replay import replay

ROOT=Path(__file__).parent


def cases():
    return json.loads((ROOT/'amazon_management_guidance_cases.json').read_text())


def test_two_real_amazon_guidance_vintages_are_on_matched_fiscal_targets():
    report=cases()
    assert report['issuer_ref']=='CIK:1018724'
    assert report['metric']=='CONSOLIDATED_NET_SALES'
    assert report['basis']=='AS_REPORTED_INCLUDES_FOREIGN_EXCHANGE'
    assert report['unit']=='USD_BILLION'
    assert report['forecast_channel']=='COMPANY_MANAGEMENT_GUIDANCE_NOT_ANALYST_CONSENSUS'
    assert report['analyst_consensus_status']=='NOT_ADMITTED'
    assert len(report['observations'])==2
    assert {r['fiscal_target'] for r in report['observations']}=={'2026Q1','2026Q2'}
    assert 'CONSENSUS' not in report['schema']
    for item in report['observations']:
        assert date.fromisoformat(item['prior_guidance_release_date']) < date.fromisoformat(item['actual_release_date'])
        assert item['low'] < item['high'] < item['actual']
        assert item['prior_guidance_source'].startswith('https://')
        assert item['actual_source'].startswith('https://')


def test_prior_guidance_midpoint_differences_are_exact_and_distinct():
    q1,q2=cases()['observations']
    def delta(row):
        low,hi,actual=[D(str(row[k])) for k in ('low','high','actual')]
        mid=(low+hi)/2
        return mid,actual-hi,actual-mid,(actual/mid-1)*100
    assert delta(q1)[:3] == (D('176.0'),D('3.0'),D('5.5'))
    assert delta(q2)[:3] == (D('196.5'),D('1.6'),D('4.1'))
    assert round(delta(q1)[3],4)==D('3.1250')
    assert round(delta(q2)[3],4)==D('2.0865')
    assert delta(q1)[3]>delta(q2)[3]


def test_larger_management_guide_exceedance_was_not_larger_stock_reaction():
    src=cases()['observations']
    market=[]
    for item in src:
        path=ROOT/'sourced_event_packets'/('amzn_'+item['fiscal_target'].lower()+'.json')
        p=json.loads(path.read_text())
        out=replay(p)
        assert out['event_ref']==item['market_event_ref']
        assert out['first_published_utc'] is None
        market.append(out['reaction']['returns']['issuer'])
    assert market[0] < market[1]  # Q1 +0.77%, Q2 +15.32%; descriptive only
    assert all(a > 0 for a in market)
