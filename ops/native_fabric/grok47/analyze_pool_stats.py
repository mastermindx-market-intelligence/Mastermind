#!/usr/bin/env python3
"""Read-only diagnostics for an exported canonical `pool stats` table.

No provider, routing, account, process, registry, or acceptance mutation. Missing
outcomes stay unknown; admission failures are never scored as model rejections.
This is a report over an existing owner, not a second metrics/lifecycle store.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
REQUIRED = frozenset({
    'provider', 'model', 'task_class', 'n', 'n_outcome', 'n_quality_verdict',
    'evaluated_first_pass_acceptance', 'n_admission_refused',
})


def count(value: str, field: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f'invalid nonnegative count: {field}')
    number = int(value)
    if number > 10**9:
        raise ValueError(f'count exceeds report bound: {field}')
    return number


def fraction(value: str) -> float | None:
    if value in ('n/a', 'unknown', '-', 'None'):
        return None
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError('invalid acceptance fraction')
    return number


def analyze(text: str, *, minimum_verdicts: int = 20) -> dict:
    if type(minimum_verdicts) is not int or not 1 <= minimum_verdicts <= 10000:
        raise ValueError('invalid minimum_verdicts')
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('statistics export exceeds report bound')
    header = None
    results = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        cells = line.split()
        if cells[:3] == ['provider', 'model', 'task_class']:
            if header is not None:
                raise ValueError('multiple tables: use a separate report for each cohort')
            if len(cells) != len(set(cells)) or not REQUIRED.issubset(cells):
                raise ValueError('unsupported or duplicated statistics header')
            header = cells
            continue
        if header is None or len(cells) != len(header):
            raise ValueError(f'malformed statistics row at line {number}')
        row = dict(zip(header, cells))
        n = count(row['n'], 'n')
        outcomes = count(row['n_outcome'], 'n_outcome')
        verdicts = count(row['n_quality_verdict'], 'n_quality_verdict')
        admission = count(row['n_admission_refused'], 'n_admission_refused')
        acceptance = fraction(row['evaluated_first_pass_acceptance'])
        if verdicts > outcomes or outcomes > n or admission > n:
            raise ValueError('inconsistent counts: do not infer coverage')
        if verdicts == 0 and acceptance is not None:
            raise ValueError('acceptance without evaluated verdicts')
        flags = []
        if verdicts < minimum_verdicts:
            flags.append('INSUFFICIENT_EVALUATED_SAMPLE')
        if outcomes < n:
            flags.append('OUTCOME_COVERAGE_GAP')
        if verdicts < outcomes:
            flags.append('QUALITY_VERDICT_COVERAGE_GAP')
        if admission:
            flags.append('ADMISSION_FAILURES_SEPARATE_FROM_MODEL_QUALITY')
        if acceptance is not None and acceptance < 0.6 and verdicts >= minimum_verdicts:
            flags.append('INVESTIGATE_MATCHED_TASK_PERFORMANCE_NOT_AUTO_DEMOTION')
        results.append({
            'provider': row['provider'], 'model': row['model'],
            'task_class': row['task_class'], 'observed_runs': n,
            'recorded_outcomes': outcomes, 'evaluated_verdicts': verdicts,
            'admission_refusals': admission,
            'outcome_coverage': outcomes / n if n else None,
            'evaluated_run_coverage': verdicts / n if n else None,
            'evaluated_first_pass_acceptance': acceptance,
            'flags': flags,
        })
    if header is None:
        raise ValueError('missing statistics header')
    return {
        'kind': 'read_only_pool_statistics_audit', 'routing_changed': False,
        'model_ranking_established': False, 'minimum_verdicts': minimum_verdicts,
        'limitations': [
            'Counts and verdicts inherit the canonical statistics owner definitions.',
            'Task mix, reviewer bias, and missing outcomes prevent causal model ranking.',
            'Requested model is not independent provider serving attestation.',
            'Displayed cost estimates are not used as actual subscription spend.',
        ],
        'cohorts': results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stats_export', type=Path)
    parser.add_argument('--minimum-verdicts', type=int, default=20)
    args = parser.parse_args()
    with args.stats_export.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('statistics export exceeds report bound')
    print(json.dumps(analyze(raw.decode('utf-8'), minimum_verdicts=args.minimum_verdicts),
                     sort_keys=True, allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
