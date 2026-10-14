"""Read-only nine-event research report; no forecast, publication, or trading authority.

Usage: python3 replay_casebook.py --format markdown
       python3 replay_casebook.py --format json

The report is reproducible from checked-in retrospective public-source packets. It
preserves publication proof class and refuses unqualified replays via reaction_replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from decimal import Decimal as D
import json
from pathlib import Path

from reaction_replay import replay

RESEARCH_AUTHORITY = 'RESEARCH_ONLY_NO_TRADING'
PACKETS = Path(__file__).parent / 'sourced_event_packets'
GUIDANCE = Path(__file__).parent / 'amazon_management_guidance_cases.json'


def build_report(folder: Path = PACKETS, guidance_path: Path = GUIDANCE) -> dict:
    entries = []
    for path in sorted(folder.glob('*.json')):
        packet = json.loads(path.read_text(encoding='utf-8'))
        outcome = replay(packet)
        status = outcome['reaction']['status']
        if outcome['authority'] != RESEARCH_AUTHORITY:
            raise ValueError('UNEXPECTED_REPLAY_AUTHORITY')
        start = outcome.get('unaffected_last_close_session')
        end = outcome.get('first_affected_session')
        ret = outcome['reaction'].get('returns') if status == 'AVAILABLE' else None
        entries.append({
            'event_ref': outcome['event_ref'],
            'issuer_ref': outcome['issuer_ref'],
            'fiscal_target': outcome['fiscal_target'],
            'packet_ref': path.name,
            'unaffected_last_close_session': start,
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
    return {
        'schema': 'earnings.reaction_replay.casebook_report.research.v1',
        'authority': RESEARCH_AUTHORITY,
        'sample_size': len(entries),
        'per_issuer_counts': dict(sorted(Counter(e['issuer_ref'] for e in entries).items())),
        'point_in_time_analyst_consensus': 'NOT_ADMITTED',
        'management_guidance_status': guidance_state,
        'management_guidance_comparisons': guidance,
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
