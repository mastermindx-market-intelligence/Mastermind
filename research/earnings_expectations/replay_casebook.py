"""Read-only nine-event research report; no forecast, publication, or trading authority.

Usage: python3 replay_casebook.py --format markdown
       python3 replay_casebook.py --format json

The report is reproducible from checked-in retrospective public-source packets. It
preserves publication proof class and refuses unqualified replays via reaction_replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from reaction_replay import replay

RESEARCH_AUTHORITY = 'RESEARCH_ONLY_NO_TRADING'
PACKETS = Path(__file__).parent / 'sourced_event_packets'


def build_report(folder: Path = PACKETS) -> dict:
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
    return {
        'schema': 'earnings.reaction_replay.casebook_report.research.v1',
        'authority': RESEARCH_AUTHORITY,
        'sample_size': len(entries),
        'per_issuer_counts': dict(sorted(Counter(e['issuer_ref'] for e in entries).items())),
        'point_in_time_analyst_consensus': 'NOT_ADMITTED',
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
