"""Read-only nine-event research report; no forecast, publication, or trading authority.

Usage: python3 replay_casebook.py --format markdown
       python3 replay_casebook.py --format json

The report is reproducible from checked-in retrospective public-source packets. It
preserves publication proof class and refuses unqualified replays via reaction_replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal as D
import json
from pathlib import Path

from reaction_replay import replay

RESEARCH_AUTHORITY = 'RESEARCH_ONLY_NO_TRADING'
PACKETS = Path(__file__).parent / 'sourced_event_packets'
GUIDANCE = Path(__file__).parent / 'amazon_management_guidance_cases.json'
MEDIA = Path(__file__).parent / 'media_reported_expectations.json'


def build_report(folder: Path = PACKETS, guidance_path: Path = GUIDANCE, media_path: Path = MEDIA) -> dict:
    entries = []
    for path in sorted(folder.glob('*.json')):
        packet = json.loads(path.read_text(encoding='utf-8'))
        outcome = replay(packet)
        status = outcome['reaction']['status']
        if outcome['authority'] != RESEARCH_AUTHORITY:
            raise ValueError('UNEXPECTED_REPLAY_AUTHORITY')
        start = outcome.get('unaffected_last_close_session')
        end = outcome.get('first_affected_session')
        closing_clock = next((ses['close_utc'] for ses in packet['sessions'] if ses['date'] == start), None)
        ret = outcome['reaction'].get('returns') if status == 'AVAILABLE' else None
        entries.append({
            'event_ref': outcome['event_ref'],
            'issuer_ref': outcome['issuer_ref'],
            'fiscal_target': outcome['fiscal_target'],
            'packet_ref': path.name,
            'unaffected_last_close_session': start,
            'unaffected_last_close_utc': closing_clock,
            'first_affected_close_session': end,
            'market_ticker': packet['price_series']['market'].get('ticker'),
            'sector_ticker': packet['price_series']['sector'].get('ticker'),
            'release_clock_quality': outcome['clock_quality'],
            'release_witness_utc': outcome['observed_public_by_utc'],
            'reaction_status': status,
            'issuer_return_pct': round(ret['issuer'] * 100, 4) if ret else None,
            'market_return_pct': round(ret['market'] * 100, 4) if ret else None,
            'sector_return_pct': round(ret['sector'] * 100, 4) if ret else None,
            'issuer_minus_market_pp': round(ret['issuer_minus_market'] * 100, 4) if ret else None,
            'issuer_minus_sector_pp': round(ret['issuer_minus_sector'] * 100, 4) if ret else None,
            'first_public_release_exact': outcome['first_published_utc'],
            'h5_status': outcome['drift']['H5']['status'],
            'h20_status': outcome['drift']['H20']['status'],
        })
    entries.sort(key=lambda x: ((x['unaffected_last_close_session'] or ''), x['issuer_ref'], x['fiscal_target']))
    guidance = []
    guidance_state = 'GUIDANCE_SOURCE_UNAVAILABLE'
    if guidance_path.is_file():
        exhibit = json.loads(guidance_path.read_text(encoding='utf-8'))
        if (exhibit.get('forecast_channel') != 'COMPANY_MANAGEMENT_GUIDANCE_NOT_ANALYST_CONSENSUS'
                or exhibit.get('analyst_consensus_status') != 'NOT_ADMITTED'
                or exhibit.get('metric') != 'CONSOLIDATED_NET_SALES'
                or exhibit.get('unit') != 'USD_BILLION'
                or exhibit.get('basis') != 'AS_REPORTED_INCLUDES_FOREIGN_EXCHANGE'):
            raise ValueError('GUIDANCE_CHANNEL_OR_BASIS_INVALID')
        by_event = {item['event_ref']: item for item in entries}
        seen_targets: set[str] = set()
        for obs in exhibit['observations']:
            target = obs['fiscal_target']
            if target in seen_targets:
                raise ValueError('DUPLICATE_GUIDANCE_TARGET')
            seen_targets.add(target)
            match = by_event.get(obs['market_event_ref'])
            if match is not None and (match['fiscal_target'] != target or match['issuer_ref'] != exhibit['issuer_ref']):
                raise ValueError('GUIDANCE_EVENT_IDENTITY_MISMATCH')
            if date.fromisoformat(obs['prior_guidance_release_date']) >= date.fromisoformat(obs['actual_release_date']):
                raise ValueError('GUIDANCE_NOT_PRIOR_TO_ACTUAL')
            low, high, actual = (D(str(obs[k])) for k in ('low', 'high', 'actual'))
            if not (0 < low < high and actual > 0):
                raise ValueError('GUIDANCE_RANGE_INVALID')
            mid = (low + high) / 2
            guidance.append({
                'fiscal_target': obs['fiscal_target'],
                'forecast_channel': exhibit['forecast_channel'],
                'unit': exhibit['unit'],
                'guidance_source': obs['prior_guidance_source'],
                'actual_source': obs['actual_source'],
                'prior_guidance_release_date': obs['prior_guidance_release_date'],
                'actual_release_date': obs['actual_release_date'],
                'guidance_midpoint_billion': float(mid),
                'actual_billion': float(actual),
                'actual_minus_high_billion': float(actual-high),
                'actual_minus_midpoint_billion': float(actual-mid),
                'actual_minus_midpoint_pct': round(float((actual/mid-1)*100), 4),
                'issuer_return_pct': match['issuer_return_pct'] if match else None,
                'issuer_reaction_status': match['reaction_status'] if match else 'NOT_IN_COHORT',
            })
        guidance_state = 'AVAILABLE_COMPANY_MANAGEMENT_GUIDANCE_ONLY'
    media = []
    media_state = 'MEDIA_REPORTED_EXPECTATIONS_SOURCE_UNAVAILABLE'
    revision = None
    if media_path.is_file():
        exhibit = json.loads(media_path.read_text(encoding='utf-8'))
        if (exhibit.get('authority') != 'RESEARCH_DISPLAY_ONLY_NO_BASELINE_ADMISSION'
                or exhibit.get('aggregate_pit_status') != 'NOT_ADMITTED'
                or exhibit.get('metric') != 'SEGMENT_REVENUE_YEAR_OVER_YEAR_GROWTH'
                or exhibit.get('value_unit') != 'PERCENTAGE_POINTS'):
            raise ValueError('MEDIA_WITNESS_PROVENANCE_NOT_ADMISSIBLE')
        by_packet = {entry['packet_ref']: entry for entry in entries}
        seen_packets = set()
        for obs in exhibit['source_reported_event_expectations']:
            if (obs.get('observation_class') != 'POST_EVENT_ARTICLE_QUOTED_ANALYST_AGGREGATE_NOT_ADMITTED'
                    or obs.get('aggregation_basis') != 'AS_REPORTED_IN_ARTICLE_NOT_INDEPENDENTLY_NORMALIZED'
                    or obs.get('underlying_analyst_vintage_utc') is not None):
                raise ValueError('MEDIA_WITNESS_IMPROPERLY_PROMOTED')
            packet_ref = obs['packet_ref']
            if packet_ref in seen_packets:
                raise ValueError('DUPLICATE_MEDIA_WITNESS')
            seen_packets.add(packet_ref)
            event = by_packet.get(packet_ref)
            if (event is None or obs['event_ref'] != event['event_ref']
                    or obs['issuer_ref'] != event['issuer_ref']
                    or obs['fiscal_target'] != event['fiscal_target']):
                raise ValueError('MEDIA_WITNESS_EVENT_IDENTITY_MISMATCH')
            source_url = obs.get('article_source_url')
            if not isinstance(source_url, str) or not source_url.startswith('https://'):
                raise ValueError('MEDIA_WITNESS_SOURCE_URL_REQUIRED')
            article_time = obs.get('article_first_reported_utc')
            if not isinstance(article_time, str) or not article_time.endswith('Z'):
                raise ValueError('MEDIA_WITNESS_UTC_REQUIRED')
            try:
                published = datetime.fromisoformat(article_time.replace('Z', '+00:00'))
                close_utc = datetime.fromisoformat(event['unaffected_last_close_utc'].replace('Z', '+00:00'))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError('MEDIA_WITNESS_CLOCK_MALFORMED') from exc
            if (published.tzinfo is None or published.utcoffset() != timezone.utc.utcoffset(published)
                    or published <= close_utc):
                raise ValueError('MEDIA_WITNESS_NOT_AFTER_REGULAR_CLOSE')
            expected = D(str(obs['expected_yoy_growth_pct']))
            actual = D(str(obs['actual_yoy_growth_pct']))
            if not (-100 < expected < 1000 and -100 < actual < 1000):
                raise ValueError('MEDIA_WITNESS_GROWTH_OUT_OF_RANGE')
            media.append({
                'event_ref': event['event_ref'],
                'packet_ref': packet_ref,
                'source_ref': obs['article_source_url'],
                'source_publication_utc': obs['article_first_reported_utc'],
                'segment_name': obs['segment_name'],
                'reported_provider': obs['provider_attribution_in_article'],
                'reported_expected_growth_pct': float(expected),
                'reported_actual_growth_pct': float(actual),
                'article_reported_gap_pp': float(actual - expected),
                'stock_reaction_pct': event['issuer_return_pct'],
                'consensus_vintage_admitted': False,
                'observation_class': obs['observation_class'],
            })
        old = exhibit['indicative_consensus_revision_report']
        if (old.get('event_ref') != 'earnings:CIK:1652044:2026Q2'
                or old.get('article_pit_eligible') is not False
                or old.get('article_published_utc') is not None):
            raise ValueError('REVISION_PREVIEW_PIT_NOT_QUALIFIED')
        revenue_older = D(str(old['consolidated_revenue_consensus_older_billion']))
        revenue_current = D(str(old['consolidated_revenue_consensus_current_billion']))
        eps_older = D(str(old['eps_consensus_older_per_share']))
        eps_current = D(str(old['eps_consensus_current_per_share']))
        revision = {
            'source_ref': old['article_source_url'],
            'fiscal_target': '2026Q2',
            'issuer_ref': 'CIK:1652044',
            'revenue_estimate_older_billion': float(revenue_older),
            'revenue_estimate_current_billion': float(revenue_current),
            'revenue_change_billion': float(revenue_current - revenue_older),
            'eps_estimate_older': float(eps_older),
            'eps_estimate_current': float(eps_current),
            'eps_change': float(eps_current-eps_older),
            'exact_publication_clock_known': False,
            'historical_consensus_vintages_admitted': False,
            'older_eps_asof': old['eps_consensus_older_asof'],
        }
        media_state = 'PUBLIC_ARTICLE_WITNESSES_ONLY_NOT_ADMITTED_AS_PIT'
    return {
        'schema': 'earnings.reaction_replay.casebook_report.research.v1',
        'authority': RESEARCH_AUTHORITY,
        'sample_size': len(entries),
        'per_issuer_counts': dict(sorted(Counter(e['issuer_ref'] for e in entries).items())),
        'point_in_time_analyst_consensus': 'NOT_ADMITTED',
        'management_guidance_status': guidance_state,
        'management_guidance_comparisons': guidance,
        'media_reported_expectation_status': media_state,
        'media_reported_expectation_witnesses': media,
        'indicative_expectation_revision_report': revision,
        'prediction_status': 'NOT_TESTED',
        'tradeable_alpha_status': 'NOT_ESTABLISHED',
        'methodology': 'Retrospective two-session adjusted close/close total return; simple issuer minus SPY and issuer minus sector ETF in percentage points. Comparators are not factor-neutral or ex-issuer; publication windows corroborated but earliest public instant unknown.',
        'cases': entries,
    }


def markdown(report: dict) -> str:
    lines = [
        '# Retrospective Earnings Reaction Casebook',
        '',
        '> **Research-only, not a predictive trading signal.** Numbers below are observed two-session adjusted returns, not expectations, alpha, or causal effect estimates.',
        '',
        '| Event | After-close release session → first affected close | Issuer | SPY | Sector | Issuer−SPY | Issuer−sector |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    for e in report['cases']:
        def fmt(value, unit):
            return f'{value:+.2f}{unit}' if value is not None else 'unavailable'
        lines.append('| ' + ' | '.join([
            e['event_ref'],
            f"{e['unaffected_last_close_session']} → {e['first_affected_close_session']}",
            fmt(e['issuer_return_pct'], '%'), fmt(e['market_return_pct'], '%'),
            f"{e['sector_ticker']}: {fmt(e['sector_return_pct'], '%')}",
            fmt(e['issuer_minus_market_pp'], ' pp'), fmt(e['issuer_minus_sector_pp'], ' pp'),
        ]) + ' |')
    lines.extend(['', f"**Count:** {report['sample_size']} reported events; historical consensus: {report['point_in_time_analyst_consensus']}; predictive validation: {report['prediction_status']}.", '', report['methodology'], ''])
    if report['management_guidance_comparisons']:
        lines.extend([
            '## Public management-guidance comparisons (NOT analyst consensus)',
            '',
            '| Target | Prior guide midpoint | Reported revenue | Above midpoint | Above range high | Stock reaction |',
            '|---|---:|---:|---:|---:|---:|',
        ])
        for row in report['management_guidance_comparisons']:
            reaction = f"{row['issuer_return_pct']:+.2f}%" if row['issuer_return_pct'] is not None else 'not in cohort'
            above_high = row['actual_minus_high_billion']
            above_high_fmt = f"{'+' if above_high >= 0 else '-'}${abs(above_high):.1f}B"
            lines.append(
                f"| {row['fiscal_target']} | ${row['guidance_midpoint_billion']:.1f}B | "
                f"${row['actual_billion']:.1f}B | {row['actual_minus_midpoint_pct']:+.3f}% | "
                f"{above_high_fmt} | {reaction} |"
            )
        lines.extend(['', 'Both comparisons use prior issuer guidance for as-reported consolidated net sales, which includes FX. Neither is a historical Street-consensus baseline, unique market belief or predictive-trading result.', ''])
    if report['media_reported_expectation_witnesses']:
        lines.extend([
            '## Media-reported cloud growth consensus witnesses (NOT PIT-admitted)',
            '',
            '| Event | Segment | Reported expected YoY | Reported actual YoY | Reported gap | Stock reaction | Source |',
            '|---|---|---:|---:|---:|---:|---|',
        ])
        for row in report['media_reported_expectation_witnesses']:
            reaction = f"{row['stock_reaction_pct']:+.2f}%" if row['stock_reaction_pct'] is not None else 'unavailable'
            lines.append(
                f"| {row['event_ref']} | {row['segment_name']} | "
                f"{row['reported_expected_growth_pct']:.2f}% | {row['reported_actual_growth_pct']:.2f}% | "
                f"{row['article_reported_gap_pp']:+.2f} pp | {reaction} | [report]({row['source_ref']}) |"
            )
        lines.extend(['', 'Every consensus figure is quoted by a dated news article after the result; it is NOT an independently verified prior-vintage forecast for a historical prediction.', ''])
    if report['indicative_expectation_revision_report']:
        r = report['indicative_expectation_revision_report']
        lines.extend([
            '## Alphabet Q2 S&P/Visible Alpha revision context (date-only source)',
            '',
            f"The [S&P/Visible Alpha research article]({r['source_ref']}) describes revenue-consensus movement ${r['revenue_estimate_older_billion']:.1f}B → ${r['revenue_estimate_current_billion']:.1f}B ({r['revenue_change_billion']:+.1f}B), alongside EPS-consensus movement ${r['eps_estimate_older']:.2f} → ${r['eps_estimate_current']:.2f} ({r['eps_change']:+.2f}). Exact publication clock and original estimate vintages are not admitted; this is qualitative disagreement evidence, not a usable model feature.",
            '',
        ])
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Print a read-only sourced earnings casebook')
    parser.add_argument('--format', choices=('json', 'markdown'), default='markdown')
    parser.add_argument('--packets', type=Path, default=PACKETS)
    args = parser.parse_args(argv)
    report = build_report(args.packets)
    if args.format == 'json':
        print(json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False))
    else:
        print(markdown(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
